import argparse
import configparser
import os
from typing import List

import crawl.adb_utils as adb_utils
import crawl.log_utils as log_utils


def fetch_apks(apps: List[str], savedir: str) -> None:
    os.makedirs(savedir, exist_ok=True)
    devices = adb_utils.get_connected_devices()
    for app in apps:
        for device in devices:
            if adb_utils.is_app_installed(device, app):
                adb_utils.pull_apk_from_device(device, app, savedir, verbose=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch all your specified apks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--list", help="List of apks to fetch, one per line", type=str, required=True
    )
    parser.add_argument("--config", help="Path to config file.", default="config.ini", type=str)
    args = parser.parse_args()

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(args.config)

    with open(args.list, "r") as f:
        app_list = [line.strip() for line in f if line[0] != "#"]
    fetch_apks(app_list, config["crawl"]["apks_path"])
