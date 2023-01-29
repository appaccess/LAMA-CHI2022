import argparse
import configparser
import json
import os
from collections import defaultdict
from typing import Dict, List

from db.upload import upload_scan_to_db
from detect.checks import (
    CheckResult,
    DuplicateSpeakableTextCheck,
    EditableTextHasHintTextCheck,
    GraphicalViewHasSpeakableTextCheck,
    RedundantDescCheck,
    UninformativeLabelCheck,
)
from detect.views import ViewHierarchy
from tqdm import tqdm


def run_accessibility_scan(cfg: configparser.ConfigParser) -> Dict[str, List[CheckResult]]:
    num_pkgs = len(os.listdir(cfg["crawl"]["views_path"]))
    results: Dict[str, List[CheckResult]] = defaultdict(list)
    for pkg in tqdm(
        os.scandir(cfg["crawl"]["views_path"]),
        total=num_pkgs,
        desc="Scanning for accessibility failures",
    ):
        requested_checks = [
            GraphicalViewHasSpeakableTextCheck,
            EditableTextHasHintTextCheck,
            RedundantDescCheck,
            # UninformativeLabelCheck,
            # DuplicateSpeakableTextCheck,
        ]
        check_objs = [check() for check in requested_checks]
        for view_hierarchy in os.scandir(pkg.path):
            vh_obj = ViewHierarchy(filepath=view_hierarchy.path)
            for check in check_objs:
                results[pkg.name] += check.run(view_hierarchy=vh_obj)

    results_serialized = {}
    for pkg_name, res in results.items():
        results_serialized[pkg_name] = [x.__dict__ for x in res]

    results_filename = "scan_results.json"
    results_file_path = os.path.join(cfg["crawl"]["output_path"], results_filename)
    with open(results_file_path, "w") as out:
        json.dump(results_serialized, out, indent=2, sort_keys=True)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect accessibility failures within apps.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--crawl_ver", "-c", help="Name for version of crawl (<Year>.<Month>)", required=True
    )
    parser.add_argument(
        "--output_path", "-o", help="Path to root data (output) directory. Overrides value in config file set with --config.", type=str
    )
    parser.add_argument("--config", help="Path to config file.", default="config.ini", type=str)
    parser.add_argument(
        "--upload", "-u", help="Set to upload results to database.", action="store_true"
    )
    args = parser.parse_args()

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(args.config)
    if args.output_path:
        config.set("crawl", "output_path", args.output_path)

    check_results = run_accessibility_scan(config)

    if args.upload:
        upload_scan_to_db(cfg=config, crawl_ver=args.crawl_ver, check_results=check_results)
