"""
Run with: python interactive_login.py (pkg_to_start_at)
Interactive opening of apps. Press enter to open the next app.
There is an optional parameter that allows you to start at a certain app in your list.
"""

import argparse
import json
import subprocess
import sys

import crawl.adb_utils as adb_utils


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--crawl_list",
        help="File of apps to crawl, one per line",
        default="crawl/apps.txt",
        type=str,
    )
    parser.add_argument(
        "--skip_list",
        help="File of apps to not crawl, one per line",
        default="crawl/skip.txt",
        type=str,
    )
    parser.add_argument("--start_app", help="which app to start with")
    parser.add_argument("--device", help="device to login for")
    args = parser.parse_args()

    with open(args.crawl_list, "r") as f:
        all_apps = [line.strip() for line in f if line[0] != "#"]
    with open(args.skip_list, "r") as f:
        skip_apps = [line.strip() for line in f if line[0] != "#"]

    apps = [app for app in all_apps if app not in skip_apps]
    devices = adb_utils.get_connected_devices()
    if not devices:
        raise Exception("Error: no connected devices")
    if args.device:
        if args.device not in devices:
            raise Exception(f"{args.device} is an invalid deviceId")
        devices = [args.device]

    if args.start_app:
        if args.start_app in apps:
            start_index = apps.index(args.start_app)
        else:
            raise Exception(f"{args.start_app} not in list of apps")
    else:
        start_index = 0
    i = start_index
    for app in apps[start_index:]:
        for device in devices:
            if not adb_utils.is_app_installed(device, app):
                continue
            adb_utils.unlock_device(device)
            proc = subprocess.Popen(
                [f"adb -s {device} shell monkey -p {app} 1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
            )
            stdout, stderr = proc.communicate()
            print(f"Opening {app} ({i}/{len(apps)})")
            input("Press any key to continue")
        i += 1


if __name__ == "__main__":
    main()
