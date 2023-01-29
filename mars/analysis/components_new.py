import configparser
import os
import sys
import threading
from glob import glob
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import cv2
import numpy as np

sys.path.append("..")

from db.db import get_db
from detect.check_utils import should_focus_elem
from detect.views import View, ViewHierarchy


N_SCREENS_PER_APP = 1
CRAWL = "2020.12"
PATH = f"/projects/appaccess/crawl_v{CRAWL}"
OUTPUT_DIR = "0207" #"visibility"
IMG_WITHIN = True
IMG_ACROSS = True


class RepeatedView:
    def __init__(self, desc, bound):
        self.desc = desc
        self.bound = bound


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


def calculate_width_height(bounds: Tuple[int, int, int, int]) -> Tuple[int, int]:
    (x1, y1, x2, y2) = bounds
    return x2 - x1, y2 - y1


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


def get_views(view) -> Iterator[View]:
    '''
    Iterator for subviews within a given view
    '''
    queue = [view]
    while queue:
        cur_view = queue.pop(0)
        for child_view in cur_view.children:
            queue.append(child_view)
        yield cur_view


def match_constraints(view1: View, view2: View, desc1, desc2, all_descs = {}) -> Tuple[int, int, int]:
    if desc1.issubset(desc2):
        smaller_view = view1
        larger_view = view2
    else:
        smaller_view = view2
        larger_view = view1

    n_matched = 0
    n_constraints = 0
    n_total = 0
    distance = 0
    bounds_parent_s = trim_view_bounds(smaller_view)
    bounds_parent_l = trim_view_bounds(larger_view)
    width_parent_s, height_parent_s = calculate_width_height(bounds_parent_s)
    width_parent_l, height_parent_l = calculate_width_height(bounds_parent_l)
    for child_s in get_views(smaller_view):
        if not (is_visible(child_s) and child_s.is_visible_to_user):
            continue
        # n_total += 1
        for child_l in get_views(larger_view):
            if not (is_visible(child_l) and child_l.is_visible_to_user):
                continue
            if child_s.class_name == child_l.class_name:
                if child_s.path in all_descs and child_l.path in all_descs:
                    desc_child_s = all_descs[child_s.path]
                    desc_child_l = all_descs[child_l.path]
                else:
                    desc_child_s = get_descendent_desc(child_s)
                    desc_child_l = get_descendent_desc(child_l)
                if get_similarity(desc_child_l, desc_child_s) < 0.5:
                    continue
                n_total += 1
                bounds_child_s = trim_view_bounds(child_s)
                bounds_child_l = trim_view_bounds(child_l)
                width_child_s, height_child_s = calculate_width_height(bounds_child_s)
                width_child_l, height_child_l = calculate_width_height(bounds_child_s)
                bounds_child_s_rel = tuple(c-p for c,p in zip(bounds_child_s, bounds_parent_s))
                bounds_child_l_rel = tuple(c-p for c,p in zip(bounds_child_l, bounds_parent_l))
                constraint_matched = [1 if abs(cs-cl) < 6 else 0 for cs,cl in zip(bounds_child_s_rel,bounds_child_l_rel)]
                # constraint_matched.append(min(width_child_s,width_child_l) / (max(width_child_s,width_child_l)+1))
                # constraint_matched.append(min(height_child_s,height_child_l) / (max(height_child_s,height_child_l)+1))
                n_similar = 0
                for cm in constraint_matched:
                    if cm > 0.9:
                        n_similar += 1
                if child_s.resource_id == child_l.resource_id:
                    n_similar += 1
                if abs(width_child_s / width_parent_s - width_child_l / width_parent_l) < .1:
                    n_similar += 1
                if abs(height_child_s / height_parent_s - height_child_l / height_parent_l) < .1:
                    n_similar += 1
                if n_similar >= 3:
                    n_matched += (calculate_size_ratio(child_s, smaller_view) + calculate_size_ratio(child_l, larger_view)) / 2
                # if True in constraint_matched:
                #     n_matched += 1
                #     n_constraints += sum(constraint_matched)
                #     break
                distance += sum(constraint_matched) / len(constraint_matched)
    # return n_matched, n_constraints, n_total
    return n_matched, distance, n_total


def calculate_overlap(view1, view2):
    (x1, y1, x2, y2) = trim_view_bounds(view1)
    (x3, y3, x4, y4) = trim_view_bounds(view2)
    x_dist = max(min(x2, x4) - max(x1, x3), 0)
    y_dist = max(min(y2, y4) - max(y1, y3), 0)
    s1 = max(x2 - x1, 0) * max(y2 - y1, 0)
    s2 = max(x4 - x3, 0) * max(y4 - y3, 0)
    s_overlap = x_dist * y_dist
    return s_overlap / (min(s1, s2) + 1e-6)


def calculate_size_ratio(view1, view2):
    (x1, y1, x2, y2) = trim_view_bounds(view1)
    (x3, y3, x4, y4) = trim_view_bounds(view2)
    s1 = max(x2 - x1, 0) * max(y2 - y1, 0)
    s2 = max(x4 - x3, 0) * max(y4 - y3, 0)
    ratio = min(s1,s2) / (max(s1,s2) + 1e-6)
    return ratio


def get_similarity(desc1, desc2):
    intersection = desc1 & desc2
    union = desc1 | desc2
    return len(intersection) / len(union)


def get_desc(view: View) -> str:
    return view.class_name + '_' + view.resource_id


def get_descendent_desc(view) -> Set[str]:
    queue = [view]
    descs = set()
    while queue:
        cur_view = queue.pop(0)
        for child_view in cur_view.children:
            queue.append(child_view)
        # if is_visible(cur_view):
        descs.add(get_desc(cur_view))
    return descs


def draw_bounds(pkg: str, ver: str, uuid: str, coord) -> None:
    descs = set()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
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

        if (x1, y1, x2, y2) == coord:
            descs = get_descendent_desc(view)
            print(descs)

    cv2.imwrite(f"{OUTPUT_DIR}/{pkg}_{uuid}_all.jpg", all_views)
    cv2.imwrite(f"{OUTPUT_DIR}/{pkg}_{uuid}_focusable.jpg", focusable)
    cv2.imwrite(f"{OUTPUT_DIR}/{pkg}_{uuid}_imp4access.jpg", access_imp)
    cv2.imwrite(f"{OUTPUT_DIR}/{pkg}_{uuid}_should_focus.jpg", sr_focusable)
    cv2.imwrite(f"{OUTPUT_DIR}/{pkg}_{uuid}_visible.jpg", visible)
    return descs


def get_view_hierarchy(pkg: str, ver: str, uuid: str) -> ViewHierarchy:
    view_path = os.path.join(PATH, "views", pkg, uuid + ".json")
    return ViewHierarchy(view_path)


def is_parent_child(v1, v2) -> bool:
    temp = v2
    while temp.parent:
        if temp == v1:
            return True
        else:
            temp = temp.parent
    return False


def is_parent_child_ex(v1, v2) -> bool:
    temp = v2
    while temp.parent:
        temp = temp.parent
        if temp == v1:
            return True
    return False


def is_parent_a_component(view) -> bool:
    temp = view
    while temp.parent:
        temp = temp.parent
        if temp.shared_comp_index != -1:
            return True
    return False


def draw_rect(img, rect, resize_factor=2):
    (x1, y1, x2, y2) = rect
    img = cv2.rectangle(
        img, (x1 // resize_factor, y1 // resize_factor), (x2 // resize_factor, y2 // resize_factor), (0, 0, 255), 3
    )


def is_under_same_parent(view1, view2) -> bool:
    if view1.parent == view2.parent:
        return True
    lvl = 1
    while view1.parent and view2.parent and get_desc(view1.parent) == get_desc(view2.parent) and lvl < 3:
        view1 = view1.parent
        view2 = view2.parent
        if view1.parent == view2.parent:
            return True
        lvl += 1
    return False


def _mark_nested_components(repeating_views, repeating_bounds, l, s):
    parent_list = set()
    del_bounds = []
    del_child = []
    dont_del = False
    for rv_l in repeating_views[l]:
        for rv_s in repeating_views[s]:
            if is_parent_child_ex(rv_l, rv_s):
                if rv_l.path not in parent_list:
                    parent_list.add(rv_l.path)
                else:
                    dont_del = True
                    break
                del_child.append(rv_s)
                if rv_s.bounds != rv_l.bounds:
                    del_bounds.append(trim_view_bounds(rv_s))
        if dont_del:
            break
    if not dont_del:
        for rv_s in del_child:
            repeating_views[s].remove(rv_s)
        for b_s in del_bounds:
            repeating_bounds[s].remove(b_s)


def _get_components(pkg: str, ver: str, uuid: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if IMG_ACROSS:     # handle img output
        screenshot = load_img(pkg, ver, uuid)
        if screenshot is None:
            print(pkg, ver, uuid, "not exist")
            return
        screenshot = cv2.resize(screenshot, (screenshot.shape[1] // 2, screenshot.shape[0] // 2))
    
    descs = set()
    viewHierarchy = get_view_hierarchy(pkg, ver, uuid)
    encountered = []
    encountered_descs = []
    repeating_bounds = {}
    repeating_views = {}
    all_descs = {}

    for view in viewHierarchy.get_views():
        desc = get_descendent_desc(view)
        all_descs[view.path] = desc

    for view in viewHierarchy.get_views():
        view.shared_comp_index = -1     # for shared view calculations
        desc = all_descs[view.path]
        bounds = trim_view_bounds(view)
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        if width <= 5 or height <= 5:
            continue

        # check if the current views is similar to an encountered view
        found = False
        for i, prev_desc in enumerate(encountered_descs):
            # check if content descs & class names are similar
            iou = get_similarity(desc, prev_desc)
            if iou > 0.2 and is_under_same_parent(view, encountered[i]) and calculate_overlap(view, encountered[i]) < 0.5:
                # check if constraints are similar
                # n_matched, _, n_total = match_constraints(view, encountered[i], desc, prev_desc)
                n_matched, _, n_total = match_constraints(view, encountered[i], desc, prev_desc, all_descs)
                if iou == 1 or n_matched > 0.3: #(n_total >= n_matched > 1 and (n_matched/n_total > 0.75 or n_total - n_matched <= 1)):
                    found = True
                    # save the view and its bounds; use bounds to dedupe
                    if i in repeating_bounds:
                        if bounds not in repeating_bounds[i]:
                            repeating_bounds[i].add(bounds)
                            repeating_views[i].append(view)
                            encountered_descs[i] |= desc
                    else:
                        repeating_bounds[i] = {trim_view_bounds(encountered[i]), bounds}
                        repeating_views[i] = [encountered[i], view]
                        encountered_descs[i] |= desc
                    break
        
        # a unique view not found before
        if not found:
            encountered.append(view)
            encountered_descs.append(desc)
    
    should_show = [True] * len(encountered_descs)
    for k, coords1 in repeating_bounds.items():
        if len(coords1) > 1:
            for m, coords2 in repeating_bounds.items():
                if len(coords2) > 1 and m != k:
                    if encountered_descs[k].issubset(encountered_descs[m]):
                        # if len(coords2) >= len(coords1):
                        #     should_show[k] = False
                        # else:
                            _mark_nested_components(repeating_views, repeating_bounds, m, k)
                            if len(repeating_views[k]) <= 1:
                                should_show[k] = False
                    elif encountered_descs[m].issubset(encountered_descs[k]):
                        # if len(coords1) >= len(coords2):
                        #     should_show[m] = False
                        # else:
                            _mark_nested_components(repeating_views, repeating_bounds, k, m)
                            if len(repeating_views[m]) <= 1:
                                should_show[m] = False
                                if len(repeating_views) == 1:
                                    encountered[k] = repeating_views[0]

    view_groups = []
    single_views = []

    for k, coords in repeating_bounds.items():
        if should_show[k]:
            view_group = []
            for similar_view in repeating_views[k]:
                view_group.append(similar_view)
                if IMG_ACROSS:
                    ss_result = screenshot.copy()
                    for box in coords:
                        draw_rect(ss_result, box, resize_factor=2)
                    cv2.imwrite(f"{OUTPUT_DIR}/{pkg}_{uuid}_repeated_{k}.jpg", ss_result)

            view_groups.append(view_group)

    for k in range(len(encountered)):
        if k in repeating_bounds and should_show[k]:
            continue
        if encountered[k].parent is None:
            continue
        (x1, y1, x2, y2) = trim_view_bounds(encountered[k])
        if (y2 - y1) * (x2 - x1) / 2220 / 1080 > 0.5:
            continue
        skip = False
        for vg in view_groups:
            for v in vg:    # we don't want to identify either parent or child of existing components
                if is_parent_child(encountered[k], v) or is_parent_child(v, encountered[k]):
                    skip = True
                    break
            if skip: break
        if not skip:
            if len(encountered_descs[k]) >= 2:  # at least two layers
                single_views.append(encountered[k])

    return view_groups, single_views


def _get_components_across_screens(pkg: str, ver: str, uuids: List[str]):
    all_view_groups = {}
    all_single_views = {}

    for uuid in uuids:
        view_groups, single_views = _get_components(pkg, ver, uuid)
        all_view_groups[uuid] = view_groups
        all_single_views[uuid] = single_views

    new_components = []
    components_descs = []
    components_uuids = []
    uuid_components = {}

    for u in uuids:
        uuid_components[u] = []

    # for u1 in uuids:
    #     vgs1 = all_view_groups[u1]
    #     for u2 in uuids:
    #         vgs2 = all_view_groups[u2]
    #         for vg1 in vgs1:
    for i, u1 in enumerate(uuids):
        sv1 = all_single_views[u1]
        print(i , '/', len(uuids), ':', len(sv1))
        for j, u2 in enumerate(uuids):
            if i <= j: continue
            sv2 = all_single_views[u2]
            for view1 in sv1:
                # print(u1, get_descendent_desc(view1), trim_view_bounds(view1))
                for view2 in sv2:
                    if (view1.shared_comp_index == -1 or view2.shared_comp_index == -1) and not (is_parent_a_component(view1) or is_parent_a_component(view2)):
                        # if calculate_overlap(view1, view2) > 0.5:
                        desc1 = get_descendent_desc(view1)
                        desc2 = get_descendent_desc(view2)
                        iou = get_similarity(desc1, desc2)
                        if iou > 0.25:
                            n_matched, _, n_total = match_constraints(view1, view2, desc1, desc2)
                            # print(desc1, desc2, n_matched, n_total)
                            if iou == 1 or n_matched > 0.3:#(n_total >= n_matched > 0 and (n_matched/n_total > 0.75 or n_total - n_matched <= 1)):
                                if view1.shared_comp_index != -1:
                                    view2.shared_comp_index = view1.shared_comp_index
                                    new_components[view1.shared_comp_index].append(view2)
                                    components_descs[view1.shared_comp_index] |= desc2
                                    components_uuids[view1.shared_comp_index].add(u2)
                                    uuid_components[u2].append((view1.shared_comp_index, len(new_components[view1.shared_comp_index]) - 1))
                                elif view2.shared_comp_index != -1:
                                    view1.shared_comp_index = view2.shared_comp_index
                                    new_components[view2.shared_comp_index].append(view1)
                                    components_descs[view2.shared_comp_index] |= desc1
                                    components_uuids[view2.shared_comp_index].add(u1)
                                    uuid_components[u1].append((view2.shared_comp_index, len(new_components[view2.shared_comp_index]) - 1))
                                else:
                                    view1.shared_comp_index = view2.shared_comp_index = len(new_components)
                                    components_descs.append(desc1 | desc2)
                                    new_components.append([view1, view2])
                                    components_uuids.append({u1, u2})
                                    uuid_components[u1].append((view1.shared_comp_index, 0))
                                    uuid_components[u2].append((view2.shared_comp_index, 1))

    should_show = [True] * len(new_components)
    for i1, desc1 in enumerate(components_descs):
        for i2, desc2 in enumerate(components_descs):
            if i2 < i1:
                if desc1.issubset(desc2):
                    should_show[i1] = False
                elif desc2.issubset(desc1):
                    should_show[i2] = False


    for i in range(len(components_uuids)):
        if should_show[i]:
            print(components_uuids)

    for uuid in uuids:
        if len(uuid_components[uuid]) > 0:
            if IMG_WITHIN:
                screenshot = load_img(pkg, ver, uuid)
                if screenshot is None:
                    print(pkg, ver, uuid, "not exist")
                    continue
                screenshot = cv2.resize(screenshot, (screenshot.shape[1] // 2, screenshot.shape[0] // 2))
                for idx1, idx2 in uuid_components[uuid]:
                    if not should_show[idx1]:
                        continue
                    view = new_components[idx1][idx2]
                    draw_rect(screenshot, trim_view_bounds(view), resize_factor=2)
                cv2.imwrite(f"{OUTPUT_DIR}/{pkg}_{uuid}_shared.jpg", screenshot)


def get_components(pkg: str, ver: str, uuid: str):
    view_groups = _get_components(pkg, ver, uuid)
    return view_groups


def main():
    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read("../config.ini")
    print("read config")
    conn = get_db(config)
    cur = conn.cursor()
    print("connected")

    cur.execute(f"SELECT app_id, pkg, version_code FROM mars.apps WHERE crawl_ver='{CRAWL}'")
    apps = cur.fetchall()
    print(len(apps))
    screens = []
    pkg_shortlist = {"com.foxsports.android"} # "com.grubhub.android"

    for (app_id, pkg, ver) in apps:
        if pkg in pkg_shortlist or not pkg_shortlist:
            cur.execute(f"SELECT view_id, uuid FROM mars.views WHERE app_id={app_id}")
            uuids = cur.fetchall()
            _uuids = [uuid for view_id, uuid in uuids]
            # _uuids = ['fee619a61e7d4a4e9c35becb216f216d']
            _get_components_across_screens(pkg, ver, _uuids)
            screens += [(pkg, ver, uuid, view_id) for view_id, uuid in uuids]

    cur.close()

    # for (pkg, ver, uuid, _) in screens:
        # paths = get_components(pkg, ver, uuid)
        # print(paths)


if __name__ == "__main__":
    main()
