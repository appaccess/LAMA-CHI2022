import configparser
import os
import re
import shutil
from typing import Any, Dict, Iterator, Optional, Tuple


def reset_data_for_app(config: configparser.ConfigParser, app: str) -> None:
    for root, dirs, _ in os.walk(config["crawl"]["output_path"]):
        for d in dirs:
            if d == app:
                app_path = os.path.join(root, d)
                shutil.rmtree(app_path)
    crawler_checkpoint = os.path.join(config["crawl"]["crawlers_path"], app) + ".pkl"
    if os.path.exists(crawler_checkpoint):
        os.remove(crawler_checkpoint)


def bfs(elem: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    queue = [elem]
    while queue:
        node = queue.pop(0)
        yield node
        for child in node["children"]:
            queue.append(child)


def bfs_with_depth(elem: Dict[str, Any]) -> Iterator[Tuple[Dict[str, Any], int]]:
    queue = [(elem, 0)]
    while queue:
        node, depth = queue.pop(0)
        yield node, depth
        for child in node["children"]:
            queue.append((child, depth + 1))


def get_touch_for_node_with_props(
    root: Dict[str, Any], props: Dict[str, Any]
) -> Optional[Dict[str, int]]:
    touch_point = None
    for node in bfs(root):
        if node_satisifies_props(node, props):
            x, y = get_touch_from_bounds(node["bounds"])
            touch_point = {"x": x, "y": y}
            break
    return touch_point


def node_satisifies_props(node: Dict[str, Any], props: Dict[str, Any]) -> bool:
    return all(node[k] == v for k, v in props.items())


def get_touch_from_bounds(bounds: str) -> Tuple[int, int]:
    search = re.search(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if search:
        x1, x2 = int(search.group(1)), int(search.group(3))
        y1, y2 = int(search.group(2)), int(search.group(4))
        midx, midy = (x1 + (x2 - x1) // 2), (y1 + (y2 - y1) // 2)
        return midx, midy
    return -1, -1


def is_valid_bounds(bounds: str) -> bool:
    search = re.search(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", bounds)
    if search:
        x1, x2 = int(search.group(1)), int(search.group(3))
        y1, y2 = int(search.group(2)), int(search.group(4))
        return all(p >= 0 for p in [x1, x2, y1, y2])
    return False
