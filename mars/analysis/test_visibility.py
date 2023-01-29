import configparser
import os
import sys
import threading
from glob import glob
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import cv2
import numpy as np

from db.db import get_db
from detect.check_utils import should_focus_elem
from detect.views import View, ViewHierarchy

sys.path.append("..")


N_SCREENS_PER_APP = 1
CRAWL = "2020.03"
PATH = f"/projects/appaccess/crawl_v{CRAWL}"


def _get_bounds(bounds_str: str) -> Tuple[int, int, int, int]:
    coordinates = bounds_str[1:-1].split("][")
    tl = coordinates[0].split(",")
    br = coordinates[1].split(",")
    x1 = int(tl[0])
    y1 = int(tl[1])
    x2 = int(br[0])
    y2 = int(br[1])
    return (x1, y1, x2, y2)


def move_coord(x: int, y: int, w: int, h: int) -> Tuple[int, int]:
    x = max(x, 0)
    y = max(y, 0)
    x = min(x, w)
    y = min(y, h)
    return (x, y)


def trim_bounds(bounds_str: str, dim: Tuple[int, int]) -> Tuple[int, int, int, int]:
    (x1, y1, x2, y2) = _get_bounds(bounds_str)
    w, h = dim
    x1, y1 = move_coord(x1, y1, w, h)
    x2, y2 = move_coord(x2, y2, w, h)
    return (x1, y1, x2, y2)


def trim_view_bounds(view: View) -> Tuple[int, int, int, int]:
    return trim_bounds(view.bounds, (view.screen_width, view.screen_height))


def load_img(pkg: str, ver: str, uuid: str, bounds_str: str = "") -> Optional[np.ndarray]:
    ss_path = os.path.join(PATH, "screenshots", pkg, uuid + ".png")
    if not os.path.exists(ss_path):
        return None
    original = cv2.imread(ss_path)
    if bounds_str != "":
        x1, y1, x2, y2 = trim_bounds(bounds_str, (original.shape[1], original.shape[0]))
        if x2 > x1 and y2 > y1:
            cropped = original[y1:y2, x1:x2]
            return cropped
        else:
            return None
    return original


def is_visible(view: View) -> bool:
    (x1, y1, x2, y2) = trim_view_bounds(view)
    return (
        x1 < x2
        and y1 < y2
        and ("android" in view.resource_id or view.package_name in view.resource_id)
    )


def draw_bounds(pkg: str, ver: str, uuid: str) -> None:
    os.makedirs("visibility", exist_ok=True)
    screenshot = load_img(pkg, ver, uuid)
    if screenshot is None:
        print(pkg, ver, uuid, "not exist")
        return
    view_path = os.path.join(PATH, "views", pkg, uuid + ".json")
    viewHierarchy = ViewHierarchy(view_path)
    screenshot = cv2.resize(screenshot, (screenshot.shape[1] // 2, screenshot.shape[0] // 2))
    all_views = screenshot.copy()
    focusable = screenshot.copy()
    access_imp = screenshot.copy()
    sr_focusable = screenshot.copy()
    visible = screenshot.copy()
    for view in viewHierarchy.get_views():
        # if is_visible(view):
        (x1, y1, x2, y2) = trim_view_bounds(view)
        all_views = cv2.rectangle(all_views, (x1 // 2, y1 // 2), (x2 // 2, y2 // 2), (0, 0, 255), 1)
        if view.is_focusable:
            focusable = cv2.rectangle(
                focusable, (x1 // 2, y1 // 2), (x2 // 2, y2 // 2), (0, 0, 255), 1
            )
        if view.is_important_for_accessibility:
            access_imp = cv2.rectangle(
                access_imp, (x1 // 2, y1 // 2), (x2 // 2, y2 // 2), (0, 0, 255), 1
            )
        if should_focus_elem(view):
            sr_focusable = cv2.rectangle(
                sr_focusable, (x1 // 2, y1 // 2), (x2 // 2, y2 // 2), (0, 0, 255), 1
            )
        if view.is_visible_to_user:
            visible = cv2.rectangle(visible, (x1 // 2, y1 // 2), (x2 // 2, y2 // 2), (0, 0, 255), 1)
    cv2.imwrite(f"visibility/{pkg}_{uuid}_all.jpg", all_views)
    cv2.imwrite(f"visibility/{pkg}_{uuid}_focusable.jpg", focusable)
    cv2.imwrite(f"visibility/{pkg}_{uuid}_imp4access.jpg", access_imp)
    cv2.imwrite(f"visibility/{pkg}_{uuid}_should_focus.jpg", sr_focusable)
    cv2.imwrite(f"visibility/{pkg}_{uuid}_visible.jpg", visible)


def main():
    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read("../../refactor/config.ini")
    print("read config")
    conn = get_db(config)
    cur = conn.cursor()
    print("connected")

    cur.execute(f"SELECT app_id, pkg, version_code FROM mars.apps WHERE crawl_ver='{CRAWL}'")
    apps = cur.fetchall()
    screens = []
    for (app_id, pkg, ver) in apps:
        cur.execute(f"SELECT uuid FROM mars.views WHERE app_id={app_id}")
        uuids = cur.fetchmany(N_SCREENS_PER_APP)
        screens += [(pkg, ver, uuid) for uuid, in uuids]
    cur.close()
    screens = [
        ("tat.example.ildar.seer", "", "39e90de8b3c044d9ba1b3b561200102f"),
        ("sixpack.sixpackabs.absworkout", "", "d252e604814e411e9e86f17dcfb52014"),
        ("sg.bigo.live", "", "191f0627afba4b5298fd313cd6a6010f"),
    ]

    for (pkg, ver, uuid) in screens:
        print(pkg, ver, uuid)
        draw_bounds(pkg, ver, uuid)


if __name__ == "__main__":
    main()
