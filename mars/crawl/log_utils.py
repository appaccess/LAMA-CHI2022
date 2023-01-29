import configparser
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterator, List, Set, Tuple

START_PATTERN = r"(?P<ts>[\d :-]+).*Starting crawl of (?P<pkg>\S+)(?: v(?P<ver>\S+))?"
RESTART_PATTERN = r"(?P<ts>[\d :-]+).*Restarting crawl of (?P<pkg>\S+)(?: v(?P<ver>\S+))? from checkpoint"
STATS_PATTERN = r"(?P<ts>[\d :-]+).*Unexplored actions: (?P<unexplored>\d+), Explored actions: (?P<explored>\d+), States: (?P<states>\d+)"
TIMED_OUT_PATTERN = r"(?P<ts>[\d :-]+).*Crawl of (?P<pkg>\S+)(?: v(?P<ver>\S+))? exceeded (?P<seconds>\d*) seconds"
COMPLETED_PATTERN = (
    r"(?P<ts>[\d :-]+).*Crawl of (?P<pkg>\S+)(?: v(?P<ver>\S+))? completed"
)
FORCE_STOP_PATTERN = r"(?P<ts>[\d :-]+).*Crawl of (?P<pkg>\S+)(?: v(?P<ver>\S+))? terminated forcefully by user"
MISSING_ACCESS_BUTTON_PATTERN = r"(?P<ts>[\d :-]+).*Accessibility button missing or obstructed for (?P<pkg>\S+)(?: v(?P<ver>\S+))?"
patterns = [
    START_PATTERN,
    RESTART_PATTERN,
    STATS_PATTERN,
    TIMED_OUT_PATTERN,
    COMPLETED_PATTERN,
    FORCE_STOP_PATTERN,
    MISSING_ACCESS_BUTTON_PATTERN,
]
LOG_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

TIMED_OUT_THRESHOLD = 7100


def get_crawled_summary(config: configparser.ConfigParser) -> Dict[str, List[str]]:
    log_file_path = os.path.join(config["crawl"]["output_path"], "crawl.log")
    split_logs_dir = "split_logs"
    split_log_by_device(log_file_path, split_logs_dir)

    summary = get_apps_status(split_logs_dir)
    if os.path.exists(config["crawl"]["screenshots_path"]):
        apps_with_data = [
            app for app in os.listdir(config["crawl"]["screenshots_path"])
        ]
        for status, apps in summary.items():
            summary[status] = [app for app in apps if app in apps_with_data]

    crawl_times = get_crawl_times(split_logs_dir)
    for app, time in crawl_times.items():
        print(app, time)
    summary["timed_out"] = [
        app
        for app in summary["timed_out"]
        if crawl_times.get(app, 0) >= TIMED_OUT_THRESHOLD
    ]
    summary["failed"] = [
        app
        for app in summary["failed"]
        if app not in summary["completed"]
        and app not in summary["timed_out"]
        and crawl_times.get(app, 0) < TIMED_OUT_THRESHOLD
    ]

    for status, apps in summary.items():
        app_time_pairs = [(app, crawl_times.get(app, 0)) for app in apps]
        app_time_pairs = sorted(app_time_pairs, key=lambda x: x[1])
        summary[status] = [p[0] for p in app_time_pairs]

    shutil.rmtree(split_logs_dir)
    return summary


def get_apps_status(split_logs_dir: str) -> Dict[str, List[str]]:
    failed, completed, timed_out = set(), set(), set()
    for device_logfile in os.scandir(split_logs_dir):
        with open(device_logfile.path, "r") as f:
            for line in f:
                match = re.search(FORCE_STOP_PATTERN, line)
                if match:
                    failed.add(match.group("pkg"))
                    continue

                match = re.search(COMPLETED_PATTERN, line)
                if match:
                    stats_match = re.search(STATS_PATTERN, next(f))
                    if stats_match:
                        num_unexplored_actions = int(stats_match.group("unexplored"))
                        if num_unexplored_actions == 0:
                            completed.add(match.group("pkg"))
                        else:
                            failed.add(match.group("pkg"))
                        continue

                match = re.search(TIMED_OUT_PATTERN, line)
                if match:
                    timed_out.add(match.group("pkg"))
                    continue

                match = re.search(MISSING_ACCESS_BUTTON_PATTERN, line)
                if match:
                    failed.add(match.group("pkg"))

    failed.discard("")
    completed.discard("")
    timed_out.discard("")
    return {
        "failed": list(failed),
        "completed": list(completed),
        "timed_out": list(timed_out),
    }


def get_crawl_times(split_logs_dir: str) -> Dict[str, int]:
    crawl_times: Dict[str, int] = defaultdict(int)
    start_times = {}
    for device_logfile in os.scandir(split_logs_dir):
        with open(device_logfile.path, "r") as f:
            for line in f:
                start_match = re.search(START_PATTERN, line) or re.search(
                    RESTART_PATTERN, line
                )
                if start_match:
                    timestamp, app = start_match.group("ts"), start_match.group("pkg")
                    parsed_time = datetime.strptime(timestamp, LOG_DATETIME_FORMAT)
                    start_times[app] = parsed_time
                else:
                    end_match = (
                        re.search(MISSING_ACCESS_BUTTON_PATTERN, line)
                        or re.search(COMPLETED_PATTERN, line)
                        or re.search(TIMED_OUT_PATTERN, line)
                    )
                    if end_match:
                        timestamp, app = end_match.group("ts"), end_match.group("pkg")
                        parsed_time = datetime.strptime(timestamp, LOG_DATETIME_FORMAT)
                        if app in start_times:
                            crawl_times[app] += int(
                                (parsed_time - start_times[app]).total_seconds()
                            )
                            del start_times[app]
    return crawl_times


def split_log_by_device(log_file_path: str, split_logs_dir: str) -> None:
    if os.path.exists(split_logs_dir):
        shutil.rmtree(split_logs_dir)
    os.makedirs(split_logs_dir)
    with open(log_file_path, "r") as f:
        for line in f:
            match = re.search(r"\d*: \[(?P<device>[A-Z\d]*)\] ", line)
            if match:
                device = match.group("device")
            with open(os.path.join(split_logs_dir, device) + ".log", "a") as out:
                out.write(line)


def get_apps_crawled_by_device(log_file_path: str) -> Dict[str, Set[Tuple[str, str]]]:
    apps: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    with open(log_file_path, "r") as f:
        for line in f:
            match = re.search(
                r"\d*: \[(?P<device>[A-Z\d]*)\] (?P<pkg>\S+)(?: v(?P<ver>[\d\w.]+))",
                line,
            )
            if match:
                device = match.group("device")
                pkg = match.group("pkg")
                ver = match.group("ver")
                apps[device].add((pkg, ver))
    return apps
