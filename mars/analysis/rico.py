import configparser
import cv2
import numpy as np
import json

import os
import sys
import re
import shutil
import multiprocessing as mp

sys.path.append("..")
from db.db import get_db
from detect.check_utils import should_focus_elem
from detect.views import View, ViewHierarchy


ALPHA = 0.002
BETA = 1
__DEBUG = False

HASH_W = 8
HASH_H = 16

CRAWL = '2020.12'   # for debug only
ROOT = '/projects/appaccess/'

class ScreenInfo:
    def __init__(self, uuid, json_path):
        self.uuid = uuid
        self.json_path = json_path
        self.screenshot_path = json_path.replace('views', 'screenshots').replace('json', 'png')
        self.resids = set()
        self.imgdesc = np.array([])
        self.viewHierarchy = ViewHierarchy(json_path)
        self.compared = False


def different_by_screenshot(ss0, ss1):
    screenshot0 = cv2.imread(ss0)
    screenshot1 = cv2.imread(ss1)
    
    diff = cv2.compare(screenshot0, screenshot1, cv2.CMP_NE)
    diff_1d = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    
    count_ne = cv2.countNonZero(diff_1d)
    return count_ne / np.size(diff_1d) > ALPHA


def get_set_diff_count(set0, set1):
    intersection = len(set0 & set1)
    union = len(set0 | set1)
    if intersection != union and __DEBUG: print((set0|set1)-(set0&set1))
    return union - intersection


# breadth-first search
def bfs_yield(root):
    queue = [root]
    while len(queue):
        elem = queue.pop(0)
        yield elem
        for child in elem['children']:
            queue.append(child)


def get_resids(view):
    return set([node['resourceId'] for node in bfs_yield(view)])


def different_by_res_id(root0, root1):
    set0 = get_resids(root0)
    set1 = get_resids(root1)
    return get_set_diff_count(set0, set1) > BETA


def different_by_res_id_set(set0, set1):
    return get_set_diff_count(set0, set1) > BETA


def get_img_descriptor(img):
    shrunk = cv2.resize(img, (HASH_W, HASH_H), interpolation = cv2.INTER_AREA)
    gray = cv2.cvtColor(shrunk, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    packed = np.packbits(thresh)
    return packed


def check_state_equivalency_rico(cver, pkg, uuid0, uuid1):
    crawl = f"crawl_v{cver}"
    file0 = os.path.join(ROOT, crawl, "views", pkg, uuid0 + ".json")
    ss0 = os.path.join(ROOT, crawl, "screenshots", pkg, uuid0 + ".png")
    file1 = os.path.join(ROOT, crawl, "views", pkg, uuid1 + ".json")
    ss1 = os.path.join(ROOT, crawl, "screenshots", pkg, uuid1 + ".png")

    if different_by_screenshot(ss0, ss1):
        with open(file0, 'r') as f0, open(file1, 'r') as f1:
            root0 = json.load(f0)
            root1 = json.load(f1)
            if different_by_res_id(root0, root1):
                return False

    return True


def check_state_equivalency_rico_fast(screen1, screen2):
    if not np.array_equal(screen1.imgdesc, screen2.imgdesc):
        if different_by_res_id_set(screen1.resids, screen2.resids):
            return False
    elif different_by_screenshot(screen1.screenshot_path, screen2.screenshot_path):
        if different_by_res_id_set(screen1.resids, screen2.resids):
            return False
    
    return True


def cluster_for_app(cver, pkg, uuids):
    crawl = f"crawl_v{cver}"
    clusters = {}
    all_screens = []
    
    for uuid in uuids:
        json_path = os.path.join(ROOT, crawl, "views", pkg, uuid + ".json")
        info = ScreenInfo(uuid, json_path)
        all_screens.append(info)

    for screen in all_screens:
        img = cv2.imread(screen.screenshot_path)
        screen.imgdesc = get_img_descriptor(img)
        if __DEBUG: print(screen.screenshot_path, screen.imgdesc)

        screen.resids = get_resids(screen.viewHierarchy.root)

    idx = 0

    for i, screen1 in enumerate(all_screens):
        print(i, len(all_screens))
        if not screen1.compared:
            screen1.compared = True
            clusters[screen1.uuid] = idx

            for j, screen2 in enumerate(all_screens):
                if i < j and not screen2.compared:
                    if check_state_equivalency_rico_fast(screen1, screen2):
                        clusters[screen2.uuid] = idx
                        if __DEBUG: print(screen2.uuid, idx)
                        screen2.compared = True

            idx += 1
    return clusters


def main():
    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read("../config.ini")
    print("read config")
    conn = get_db(config)
    cur = conn.cursor()
    print("connected")

    cur.execute(f"SELECT app_id, pkg, version_code FROM mars.apps WHERE crawl_ver='{CRAWL}'")
    apps = cur.fetchall()
    print("fetched", len(apps), f"apps from {CRAWL} crawl")
    screens = []
    pkg_shortlist = {"com.grubhub.android"} # "com.foxsports.android"

    for (app_id, pkg, ver) in apps:
        if pkg in pkg_shortlist or not pkg_shortlist:
            cur.execute(f"SELECT view_id, uuid FROM mars.views WHERE app_id={app_id}")
            uuids = cur.fetchall()
            _uuids = [uuid for view_id, uuid in uuids]
            clusters = cluster_for_app(CRAWL, pkg, _uuids)
            print(clusters)
            screens += [(pkg, ver, uuid, view_id) for view_id, uuid in uuids]

    cur.close()


if __name__ == "__main__":
    main()
