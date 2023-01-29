import argparse
import configparser
import csv
import json
import os

import pandas as pd
from crawl.post_crawl import RemoveCandidate
from db.upload import (
    upload_clusters_to_db,
    upload_crawl_to_db,
    upload_metadata_to_db,
    upload_removed_log_to_db,
    upload_repairs_to_db,
    upload_scan_to_db,
)
from detect.checks import CheckResult
from repair.types import Repair
from tqdm import tqdm

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_type",
        choices=["metadata", "views", "failures", "repairs", "clusters", "all"],
        help="What type of data to ingest.",
        required=True,
    )
    parser.add_argument(
        "--data_path", help="Absolute path to folder containing all data.", required=True
    )
    parser.add_argument("--config", help="Path to config file.", default="config.ini", type=str)
    parser.add_argument("--crawl_ver", "-c", help="Name for crawl version in db.", required=True)
    args = parser.parse_args()

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(args.config)

    metadata_file_path = os.path.join(args.data_path, "metadata.csv")
    views_full_path = os.path.join(args.data_path, "views")
    failures_file_path = os.path.join(args.data_path, "scan_results.json")
    repairs_file_path = os.path.join(args.data_path, "repairs.json")
    removed_file_path = os.path.join(args.data_path, "removed.json")

    if args.data_type == "metadata":
        metadata_df = pd.read_csv(metadata_file_path)
        upload_metadata_to_db(config, args.crawl_ver, metadata_df)

    elif args.data_type == "views":
        upload_crawl_to_db(
            config, args.crawl_ver, views_full_path,
        )
        if os.path.exists(removed_file_path):
            with open(removed_file_path, "r") as f:
                removed_log = json.load(f)
                for pkg, cands in removed_log.items():
                    removed_log[pkg] = [RemoveCandidate(**cand) for cand in cands]
            upload_removed_log_to_db(config, args.crawl_ver, removed_log)

    elif args.data_type == "failures":
        if os.path.exists(failures_file_path):
            with open(failures_file_path, "r") as f:
                scan_results = json.load(f)
            for pkg, results in scan_results.items():
                scan_results[pkg] = [CheckResult(**result) for result in results]
            upload_scan_to_db(config, args.crawl_ver, scan_results)

    elif args.data_type == "repairs":
        if os.path.exists(repairs_file_path):
            with open(failures_file_path, "r") as f:
                repairs_json = json.load(f)
            repairs = [Repair(**repair) for repair in repairs_json]
            upload_repairs_to_db(config, repairs)

    elif args.data_type == "clusters":
        cluster_methods = ["xiaoyi", "rico", "mars"]
        for cluster_method in cluster_methods:
            clusters_file_path = os.path.join(args.data_path, f"clusters_{cluster_method}.json")
            if os.path.exists(clusters_file_path):
                with open(clusters_file_path, "r") as f:
                    clusters = json.load(f)
                upload_clusters_to_db(config, args.crawl_ver, cluster_method, clusters)
