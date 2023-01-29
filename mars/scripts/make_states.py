import argparse
import configparser
import json
import multiprocessing as mp
import os
from collections import defaultdict
from typing import Dict, List, Tuple

from crawl.xiaoyi_heuristics import get_xiaoyi_state_id
from crawl.mars_heuristics import get_mars_state_id
from crawl.rico_heuristics import cluster_for_app
from db.upload import upload_clusters_to_db


def cluster_xiaoyi(cfg: configparser.ConfigParser) -> Dict[str, Dict[str, List[str]]]:
    pkgs = [(pkg.name, pkg.path) for pkg in os.scandir(cfg["crawl"]["views_path"])]
    with mp.Pool(mp.cpu_count() // 3) as p:
        data = p.starmap(cluster_xiaoyi_process, pkgs)
    return dict(data)


def cluster_xiaoyi_process(
    pkg_name: str, pkg_path: str
) -> Tuple[str, Dict[str, List[str]]]:
    states = defaultdict(list)
    for view in os.scandir(pkg_path):
        uuid = os.path.splitext(view.name)[0]
        state_id = get_xiaoyi_state_id(view.path)
        if state_id:
            states[state_id].append(uuid)
    return pkg_name, states


def cluster_rico(cfg: configparser.ConfigParser) -> Dict[str, Dict[str, List[str]]]:
    pkgs = [(pkg.name, pkg.path) for pkg in os.scandir(cfg["crawl"]["views_path"])]
    # pkg_name, states = cluster_rico_process(pkgs[0][0], pkgs[0][1])
    # data = {pkg_name: states}
    # set maxtasksperchild to 1 to improve overall time
    # ref: https://stackoverflow.com/questions/53751050/python-multiprocessing-understanding-logic-behind-chunksize
    with mp.Pool(mp.cpu_count() // 3) as p:
        data = p.starmap(cluster_rico_process, pkgs)
    return dict(data)


def cluster_rico_process(
    pkg_name: str, pkg_path: str
) -> Tuple[str, Dict[str, List[str]]]:
    uuids = []
    for view in os.scandir(pkg_path):
        uuid = os.path.splitext(view.name)[0]
        uuids.append(uuid)
    states = cluster_for_app("", pkg_name, uuids, pkg_path)
    return pkg_name, states


def cluster_mars(cfg: configparser.ConfigParser) -> Dict[str, Dict[str, List[str]]]:
    pkgs = [(pkg.name, pkg.path) for pkg in os.scandir(cfg["crawl"]["views_path"])]
    with mp.Pool(mp.cpu_count() // 3) as p:
        data = p.starmap(cluster_mars_process, pkgs)
    return dict(data)


def cluster_mars_process(
    pkg_name: str, pkg_path: str
) -> Tuple[str, Dict[str, List[str]]]:
    states = defaultdict(list)
    for view in os.scandir(pkg_path):
        uuid = os.path.splitext(view.name)[0]
        state_id = get_mars_state_id(view.path)
        if state_id:
            states[state_id].append(uuid)
    return pkg_name, states


def make_states(
    cfg: configparser.ConfigParser, method: str
) -> Dict[str, Dict[str, List[str]]]:
    if method == "xiaoyi":
        states = cluster_xiaoyi(cfg)
    elif method == "rico":
        states = cluster_rico(cfg)
    elif method == "mars":
        states = cluster_mars(cfg)

    clusters_filename = f"clusters_{method}.json"
    clusters_full_path = os.path.join(config["crawl"]["output_path"], clusters_filename)
    with open(clusters_full_path, "w") as out:
        json.dump(states, out, indent=2, sort_keys=True)

    return states


if __name__ == "__main__":
    METHODS = ["rico", "xiaoyi", "mars"]
    parser = argparse.ArgumentParser(
        description="Cluster captured app screens into states",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--crawl_ver",
        "-c",
        help="Name for version of crawl (<Year>.<Month>)",
        required=True,
    )
    parser.add_argument(
        "--config", help="Path to config file.", default="config.ini", type=str
    )
    parser.add_argument(
        "--upload", "-u", help="Set to upload results to database.", action="store_true"
    )
    parser.add_argument(
        "--method",
        help="Method to use for forming states.",
        choices=METHODS,
        type=str,
        required=True,
    )
    parser.add_argument(
        "--output_path",
        "-o",
        help="Path to root data (output) directory. Overrides value in config file set with --config.",
        type=str,
    )
    args = parser.parse_args()

    config = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation()
    )
    config.read(args.config)
    if args.output_path:
        config.set("crawl", "output_path", args.output_path)

    found_states = make_states(config, args.method)
    if args.upload:
        upload_clusters_to_db(
            cfg=config,
            crawl_ver=args.crawl_ver,
            method=args.method,
            states=found_states,
        )
