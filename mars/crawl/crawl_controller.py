import argparse
import configparser
import json
import logging
import multiprocessing as mp
import os
import queue
import signal
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, NoReturn

import dill
from tqdm import tqdm

import crawl.adb_utils as adb_utils
import crawl.errors as errors
import crawl.log_utils as log_utils
import crawl.timeout as timeout
import crawl.utils as utils

from .crawler import Crawler


class CrawlWorker:
    def __init__(
        self, config: configparser.ConfigParser, device: str, task_queue: mp.Queue, reset: bool,
    ) -> None:
        self.config = config
        self.device = device
        self.task_queue = task_queue
        self.reset = reset

        self.process = mp.Process(target=self.crawl_process)
        self.app = mp.Array("c", 300)
        self.version = mp.Array("c", 300)
        self.pid = mp.Value("i", -1)
        self.status = mp.Array("c", 300)

        self.status.value = b"not started"

        self.apks_path = self.config["crawl"]["apks_path"]
        self.crawlers_path = self.config["crawl"]["crawlers_path"]
        self.full_crawl_timeout = self.config["crawl"].getint("full_crawl_timeout")

        adb_utils.sync_accesspull_service(config, device)
        adb_utils.enable_accesspull_service(device)

    def unlock(self) -> None:
        adb_utils.unlock_device(self.device)

    def reboot(self) -> None:
        adb_utils.reboot_device(self.device)

    def mute(self) -> None:
        adb_utils.send_keycode_event(self.device, 164)

    def start(self) -> None:
        self.status.value = b"crawling"
        if not self.process.is_alive():
            self.process.start()
        else:
            print(f"{self.process} is already alive.")

    def stop(self) -> None:
        self.process.terminate()
        adb_utils.send_keycode_event(self.device, "KEYCODE_HOME")
        logging.error(
            f"[{self.device}] Crawl of {self.app.value.decode()} v{self.version.value.decode()} "
            f"terminated forcefully by user. Crawl stopped."
        )
        self.status.value = b"not started"
        self.app.value = b""
        self.version.value = b""

    def skip(self) -> None:
        self.stop()
        self.start()

    def crawl_process(self) -> None:
        # Gracefully handle process killed with stop()
        # This allows the "finally" block to perform crawler cleanup
        def sigterm_handler(_signo: int, _stack_frame: Any) -> NoReturn:
            sys.exit(0)

        signal.signal(signal.SIGTERM, sigterm_handler)

        self.pid.value = os.getpid()
        os.makedirs(self.crawlers_path, exist_ok=True)
        while True:
            try:
                app = self.task_queue.get_nowait()
            except queue.Empty:
                adb_utils.send_keycode_event(self.device, "KEYCODE_HOME")
                logging.info(f"All apps crawled on {self.device}")
                self.status.value = b"finished"
                self.app.value = b""
                self.version.value = b""
                break

            if self.reset:
                utils.reset_data_for_app(self.config, app)

            # os.makedirs(self.apks_path, exist_ok=True)
            # adb_utils.pull_apk_from_device(self.device, app, self.apks_path, verbose=False)

            with timeout.Timeout(seconds=self.full_crawl_timeout):
                try:
                    crawler_checkpoint = f"{self.crawlers_path}/{app}.pkl"
                    if os.path.exists(crawler_checkpoint):
                        crawl_instance = dill.load(open(crawler_checkpoint, "rb"))
                    else:
                        crawl_instance = Crawler(self.config, self.device, app)

                    self.app.value = crawl_instance.app.encode()
                    self.version.value = crawl_instance.version.encode()

                    crawl_instance.prepare_device_for_crawl()
                    crawl_instance.crawl()
                except TimeoutError:
                    logging.error(
                        f"[{self.device}] Crawl of {app} v{self.version.value.decode()} exceeded "
                        f"{self.full_crawl_timeout} seconds. Crawl stopped."
                    )
                except KeyboardInterrupt:
                    pass
                except errors.MissingAccessibilityButtonError:
                    logging.error(
                        f"[{self.device}] Accessibility button missing or obstructed for "
                        f"{app} v{self.version.value.decode()}. Crawl stopped."
                    )
                    self.reboot()
                    time.sleep(60)
                finally:
                    crawl_instance.on_crawl_terminate()
                    dill.dump(crawl_instance, open(crawler_checkpoint, "wb"))


class CrawlController:
    def __init__(self, args: argparse.Namespace, config: configparser.ConfigParser) -> None:
        self.args = args
        self.config = config

        self.devices = adb_utils.get_connected_devices()
        self.workers = self.get_workers()
        self.start_event_handler()

    def init_tasks(self) -> Dict[str, mp.Queue]:
        if self.args.app:
            apps = [self.args.app]
        else:
            apps = self.get_apps_to_crawl()

        task_queues: Dict[str, mp.Queue] = {device: mp.Queue() for device in self.devices}
        apps_missing = []
        staging = defaultdict(list)
        apps_on_mult = defaultdict(list)
        for app in tqdm(apps):
            devices_with_app = []
            for device in self.devices:
                if adb_utils.is_app_installed(device, app):
                    devices_with_app.append(device)
            if len(devices_with_app) == 0:
                apps_missing.append(app)
            elif len(devices_with_app) == 1:
                staging[devices_with_app[0]].append(app)
            else:
                apps_on_mult[app] = devices_with_app

        for app, devices in apps_on_mult.items():
            device_with_fewest = min(
                [(device, len(apps)) for device, apps in staging.items() if device in devices],
                key=lambda x: x[1],
            )[0]
            staging[device_with_fewest].append(app)

        for device, apps in staging.items():
            for app in apps:
                task_queues[device].put(app)

        if apps_missing:
            print(
                f"These apps were not found on any connected device: "
                f"{json.dumps(apps_missing, indent=2, sort_keys=True)}"
            )
        return task_queues

    def get_apps_to_crawl(self) -> List[str]:
        if self.args.skip_list:
            with open(self.args.skip_list, "r") as f:
                apps_skip = [line.strip() for line in f if line[0] != "#"]
        else:
            apps_skip = []

        with open(self.args.crawl_list, "r") as f:
            apps = [line.strip() for line in f if line[0] != "#"]

        if not self.args.exact:
            crawled_summary = log_utils.get_crawled_summary(self.config)
            with open(
                os.path.join(self.config["crawl"]["output_path"], "crawl_summary.json"), "w"
            ) as out:
                json.dump(crawled_summary, out, indent=2)
            apps = [
                app
                for app in apps
                if app not in crawled_summary["completed"]
                and app not in apps_skip
                and app not in crawled_summary["timed_out"]
            ]
        return apps

    def get_workers(self) -> List[CrawlWorker]:
        task_queues = self.init_tasks()
        workers = [
            CrawlWorker(self.config, device, task_queues[device], self.args.reset)
            for device in self.devices
        ]
        return workers

    def start_event_handler(self) -> NoReturn:
        while True:
            try:
                command = input("> ").strip().split(" ")

                if command[0] == "exit":
                    for worker in self.workers:
                        if worker.status.value.decode() == "crawling":
                            worker.stop()
                    sys.exit()

                if command[0] == "status":
                    if not self.devices:
                        print("No connected devices.")

                    # qsize not implemented on OS X
                    if sys.platform == "darwin":
                        for worker in self.workers:
                            print(
                                f"[{worker.pid.value}] {worker.device} | {worker.status.value.decode()} | "
                                f" {worker.app.value.decode()} | {worker.version.value.decode()}"
                            )
                    else:
                        for worker in self.workers:
                            print(
                                f"[{worker.pid.value}] {worker.device} | "
                                f"{worker.status.value.decode()} | {worker.task_queue.qsize()} | "
                                f"{worker.app.value.decode()} | {worker.version.value.decode()}"
                            )

                elif command[0] == "start":
                    if len(command) < 2:
                        print('start [all | "device"]')
                        continue
                    if command[1] == "all":
                        for worker in self.workers:
                            if worker.status.value.decode() != "crawling":
                                worker.start()
                    elif command[1] in self.devices:
                        worker = [w for w in self.workers if w.device == command[1]][0]
                        if worker.status.value.decode() != "crawling":
                            worker.start()
                    else:
                        print(f'Unrecognized command: {" ".join(command)}')
                        continue

                elif command[0] == "unlock":
                    if len(command) < 2:
                        print('unlock [all | "device"]')
                        continue
                    if command[1] == "all":
                        for worker in self.workers:
                            worker.unlock()
                    elif command[1] in self.devices:
                        worker = [w for w in self.workers if w.device == command[1]][0]
                        worker.unlock()
                    else:
                        print(f'Unrecognized command: {" ".join(command)}')
                        continue

                elif command[0] == "mute":
                    if len(command) < 2:
                        print('mute [all | "device"]')
                        continue
                    if command[1] == "all":
                        for worker in self.workers:
                            worker.mute()
                    elif command[1] in self.devices:
                        worker = [w for w in self.workers if w.device == command[1]][0]
                        worker.mute()
                    else:
                        print(f'Unrecognized command: {" ".join(command)}')
                        continue

                elif command[0] == "reboot":
                    if len(command) < 2:
                        print('reboot [all | "device"]')
                        continue
                    if command[1] == "all":
                        for worker in self.workers:
                            if worker.status.value.decode() == "crawling":
                                worker.stop()
                            worker.reboot()
                        time.sleep(60)
                    elif command[1] in self.devices:
                        worker = [w for w in self.workers if w.device == command[1]][0]
                        if worker.status.value.decode() == "crawling":
                            worker.stop()
                        worker.reboot()
                        time.sleep(60)
                    else:
                        print(f'Unrecognized command: {" ".join(command)}')
                        continue

                elif command[0] == "stop":
                    if len(command) < 2:
                        print('stop [all | "device"]')
                        continue
                    if command[1] == "all":
                        for worker in self.workers:
                            if worker.status.value.decode() == "crawling":
                                worker.stop()
                    elif command[1] in self.devices:
                        worker = [w for w in self.workers if w.device == command[1]][0]
                        if worker.status.value.decode() == "crawling":
                            worker.stop()
                    else:
                        print(f'Unrecognized command: {" ".join(command)}')
                        continue

                elif command[0] == "skip":
                    if len(command) < 2:
                        print('skip "device"')
                        continue
                    if command[1] in self.devices:
                        worker = [w for w in self.workers if w.device == command[1]][0]
                        if worker.status.value.decode() == "crawling":
                            worker.skip()
                    else:
                        print(f'Unrecognized command: {" ".join(command)}')
                        continue
                else:
                    print(f'Unrecognized command: {" ".join(command)}')
            except KeyboardInterrupt:
                print("Use command exit to quit.")
