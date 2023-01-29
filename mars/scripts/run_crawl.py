import argparse
import configparser
import logging
import os
import sys

from crawl.crawl_controller import CrawlController


def start_crawl_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Start CLI for an automated Android app crawler.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", help="Path to config file.", default="config.ini", type=str)
    parser.add_argument(
        "--crawl_list",
        help="File of apps to crawl, one per line",
        default="crawl/apps.txt",
        type=str,
    )
    parser.add_argument(
        "--skip_list",
        help="File of apps to skip during crawl, one per line",
        type=str,
        default="crawl/skip.txt",
    )
    parser.add_argument("--app", help="Specific app to crawl. Overrides --crawl_list.", type=str)
    parser.add_argument(
        "--reset", help="Remove previous crawl data if it exists", action="store_true",
    )
    parser.add_argument(
        "--exact",
        help="Set to crawl exactly the apps specified in --crawl_list",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.app and not os.path.exists(args.crawl_list):
        print("Either app or valid app list must be specified")
        sys.exit(1)

    if args.skip_list and not os.path.exists(args.skip_list):
        print(f"Provided skip_list {args.skip_list} could not be found")
        sys.exit(1)

    sys.setrecursionlimit(10000)

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(args.config)

    os.makedirs(config["crawl"]["output_path"], exist_ok=True)

    log_filename = "crawl.log"
    log_file_path = os.path.join(config["crawl"]["output_path"], log_filename)
    logging.basicConfig(
        filename=log_file_path,
        format="%(asctime)s:%(levelname)s:%(process)d: %(message)s",
        level=logging.DEBUG,
    )

    crawl_controller = CrawlController(args, config)


if __name__ == "__main__":
    start_crawl_cli()
