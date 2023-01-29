import argparse
import configparser
import json
import os
from typing import Dict, List

from crawl import post_crawl
from crawl.post_crawl import RemoveCandidate
from db.upload import upload_crawl_to_db, upload_removed_log_to_db


def clean_crawl(
    cfg: configparser.ConfigParser, out_filepath: str
) -> Dict[str, List[RemoveCandidate]]:
    removed = {}
    for pkg in os.listdir(cfg["crawl"]["views_path"]):
        views_path = os.path.join(cfg["crawl"]["views_path"], pkg)
        screenshots_path = os.path.join(cfg["crawl"]["screenshots_path"], pkg)
        graphs_path = os.path.join(cfg["crawl"]["graphs_path"], pkg)

        removed_for_pkg = []
        removed_for_pkg += post_crawl.check_broken_images(screenshots_path)
        removed_for_pkg += post_crawl.check_orphan_files(views_path, screenshots_path)
        removed_for_pkg += post_crawl.check_identical_screens(views_path, removed_for_pkg)

        graph_file_path = os.path.join(graphs_path, "graph.json")
        post_crawl.fix_graphs(graph_file_path, removed_for_pkg)

        removed[pkg] = removed_for_pkg

    for pkg, cands in removed.items():
        for cand in cands:
            img_path = os.path.join(config["crawl"]["screenshots_path"], pkg, cand.uuid) + ".png"
            view_path = os.path.join(config["crawl"]["views_path"], pkg, cand.uuid) + ".json"
            if os.path.exists(img_path):
                os.remove(img_path)
            if os.path.exists(view_path):
                os.remove(view_path)

    # JSON serialize
    serialized = {pkg: [r.__dict__ for r in vals] for pkg, vals in removed.items()}

    with open(out_filepath, "w") as out:
        json.dump(serialized, out, indent=2)

    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--crawl_ver", "-c", help="Name for version of crawl (<Year>.<Month>)", required=True
    )
    parser.add_argument("--config", help="Path to config file.", default="config.ini", type=str)
    parser.add_argument(
        "--upload", "-u", help="Set to upload results to database.", action="store_true"
    )
    args = parser.parse_args()

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(args.config)

    removed_log_filepath = os.path.join(config["crawl"]["output_path"], "removed_log.json")
    removed_log = clean_crawl(config, removed_log_filepath)

    if args.upload:
        upload_crawl_to_db(
            cfg=config, crawl_ver=args.crawl_ver, views_dir=config["crawl"]["views_path"]
        )
        upload_removed_log_to_db(cfg=config, crawl_ver=args.crawl_ver, removed=removed_log)
