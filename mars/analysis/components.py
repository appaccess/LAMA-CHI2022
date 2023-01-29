from glob import glob
from typing import Any, Dict, Iterator, List, Optional, Set
import cv2
import os
import configparser
import zss
import threading
import sys
import numpy as np
sys.path.append('../..')
from refactor.detect.views import View, ViewHierarchy
from refactor.db.db import get_db


PATH = '/projects/appaccess/crawl_v2020.03/crawl/views/com.foxsports.android/4150011'
PKG = 'com.foxsports.android'
CRAWL = '2020.03'
UUID = '9e2533ffe36c445f806628a80148eb13'


class Component:
    view: View
    count: int
    desc: str
    child_comps: List["Component"]
    descriptors: set()
    depth: int
    index: int
    sames: List[str]   # uuid : bounds
    is_visible: bool
    uuid: str

    _counter = 0

    def __init__(self, view: View, uuid: str):
        self.view = view
        self.count = 1
        self.desc = view.class_name + '_' + view.resource_id
        self.child_comps = []
        self.descriptors = { self.desc }
        self.depth = 1
        self.sames = [(uuid, view.bounds)]
        self.is_visible = is_visible(view)
        self.uuid = uuid
        _lock = threading.Lock()
        with _lock:
            Component._counter += 1
            self.index = Component._counter


def get_desc(view: View) -> str:
    return view.class_name + '_' + view.resource_id


def get_children(view: View) -> List[View]:
    return view.children


def get_descendent_desc(view) -> set():
    queue = [view]
    descs = set()
    while queue:
        cur_view = queue.pop(0)
        for child_view in cur_view.children:
            queue.append(child_view)
        if is_visible(cur_view):
            descs.add(get_desc(cur_view))
    return descs


def is_visible(view: View) -> bool:
    (x1, y1, x2, y2) = trim_view_bounds(view)
    return view.is_important_for_accessibility \
        and x1 < x2 and y1 < y2 \
        and ('android' in view.resource_id \
            or view.package_name in view.resource_id)


def _get_bounds(bounds_str: str) -> (int, int, int, int):
    coordinates = bounds_str[1:-1].split('][')
    tl = coordinates[0].split(',')
    br = coordinates[1].split(',')
    x1 = int(tl[0])
    y1 = int(tl[1])
    x2 = int(br[0])
    y2 = int(br[1])
    return (x1, y1, x2, y2)


def is_same_view(view1: View, view2: View) -> int:
    # both components are leaves
    if (not view1.children) and (not view2.children):
        return get_desc(view1) == get_desc(view2)

    return zss.simple_distance(view1, view2, get_children, get_desc) == 0


def compare_sets(s1: set(), s2: set()) -> bool:
    temp = set()
    if len(s1) > len(s2):
        temp = s2 - s1
    else:
        temp = s1 - s2
    return s1.issubset(s2) or s2.issubset(s1)# or len(temp) < 1


def move_coord(x: int, y: int, w: int, h: int) -> (int, int):
    x = max(x, 0)
    y = max(y, 0)
    x = min(x, w)
    y = min(y, h)
    return (x, y)


def trim_bounds(bounds_str: str, dim: (int, int)) -> (int, int, int, int):
    (x1, y1, x2, y2) = _get_bounds(bounds_str)
    w, h = dim
    x1, y1 = move_coord(x1, y1, w, h)
    x2, y2 = move_coord(x2, y2, w, h)
    return (x1, y1, x2, y2)


def trim_view_bounds(view: View) -> (int, int, int, int):
    return trim_bounds(view.bounds, (view.screen_width, view.screen_height))


def load_img(uuid: str, bounds_str: str = "") -> Optional[np.ndarray]:
    ss_path = os.path.join(PATH, uuid + '.png')
    ss_path = ss_path.replace('views', 'screenshots')
    original = cv2.imread(ss_path)
    if bounds_str != "":
        x1, y1, x2, y2 = trim_bounds(bounds_str, (original.shape[1], original.shape[0]))
        if x2 > x1 and y2 > y1:
            cropped = original[y1:y2, x1:x2]
            return cropped
        else:
            return None
    return original


def save_component_imgs(comp: Component, save_path: str) -> None:
    os.makedirs(save_path, exist_ok=True)
    if len(comp.sames) == 1: return
    count = 0
    for uuid, bounds_str in comp.sames:
        count += 1
        if count > 6: break
        if is_visible(comp.view):
            img = load_img(uuid, bounds_str)
            if img is not None:
                cv2.imwrite(os.path.join(save_path, f'{uuid}_{bounds_str}.png'), img)


def get_img_outlines(img: np.ndarray) -> np.ndarray:
    kernel = np.ones((3,3), np.uint8)
    #grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    #hue = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:,:,0]
    #canny1 = cv2.Canny(img[:,:,0], 5, 20)
    #canny2 = cv2.Canny(img[:,:,1], 5, 20)
    #canny3 = cv2.Canny(img[:,:,2], 5, 20)
    #canny = cv2.add(canny1, canny2, canny3)
    canny = cv2.Canny(img, 20, 40)
    dilated = cv2.dilate(canny, kernel)
    return dilated


def calc_matched_outline(img: np.ndarray, bounds: (int, int, int, int)) -> float:
    # ignore outer bounds of the image
    x1, y1, x2, y2 = bounds
    outline_sum = 0
    outline_px = 1
    outline = get_img_outlines(img)
    if x1 != 0:
        outline_sum += np.sum(outline[y1:y2, x1])
        outline_px += y2-y1
    if x2 != img.shape[1]:
        outline_sum += np.sum(outline[y1:y2, x2])
        outline_px += y2-y1
    if y1 != 0:
        outline_sum += np.sum(outline[y1, x1:x2])
        outline_px += x2-x1
    if y2 != img.shape[0]:
        outline_sum += np.sum(outline[y2, x1:x2])
        outline_px += x2-x1
    #print(outline_sum/255, outline_px)
    return outline_sum / 255 / outline_px


class AppComponents:
    components: Dict[int, List[Component]]
    components_l: List[Component]

    def __init__(self, view: View = None):
        self.components = {}
        self.components_l = []
        if view is not None:
            x1,y1,x2,y2 = trim_bounds(view.bounds, (view.screen_width, view.screen_height))
            self.width = x2-x1
            self.height = y2-y1
        else:
            self.width = 1080
            self.height = 2220  # TODO: fix screenshot size

    def get_component(self, view: View, uuid: str) -> Component:
        comp = Component(view, uuid)
        if view.children:
            for child in view.children:
                if is_visible(child) or child.children:
                    child_comp = self.get_component(child, uuid)
                    comp.child_comps.append(child_comp)
                    comp.descriptors |= child_comp.descriptors
            if comp.child_comps:
                comp.depth = 1 + max(cc.depth for cc in comp.child_comps)
            #print(comp.depth)
        new_comp = self.insert_component(comp)
        return new_comp

    def matching(self, i: int, matched2: List[int], visited: List[bool], comp1: Component, comp2: Component):
        for j,cc2 in enumerate(comp2.child_comps):
            if compare_sets(comp1.child_comps[i].descriptors, cc2.descriptors) and not visited[j]:
                visited[j] = True
                if matched2[j] == -1 or self.matching(matched2[j], matched2, visited, comp1, comp2):
                    matched2[j] = i
                    return j
        return -1

    # use comp2 as a template
    def compare_components(self, comp1: Component, comp2: Component) -> (bool, Optional[View]):
        if comp1.desc != comp2.desc:
            return False, None
        if not compare_sets(comp1.descriptors, comp2.descriptors):
            return False, None
        if len(comp1.descriptors) > 10 or len(comp2.descriptors) > 10:
            comp2.descriptors |= comp1.descriptors
            comp2.sames += comp1.sames
            comp2.is_visible |= comp1.is_visible
        return True, comp2
        
        matched1 = {}
        matched2 = [-1] * len(comp2.child_comps)
        for i, cc1 in enumerate(comp1.child_comps):
            visited = [False] * len(comp2.child_comps)
            match_result = self.matching(i, matched2, visited, comp1, comp2)
            if match_result != -1:
                matched1[i] = match_result

        if len(matched1) == len(comp1.child_comps): # all matched to comp2
            for (i,j) in matched1.items():
                comp2.child_comps[j].descriptors |= comp1.child_comps[i].descriptors
                comp2.child_comps[j].sames += comp1.child_comps[i].sames
            comp2.descriptors |= comp1.descriptors
            comp2.sames += comp1.sames
            comp2.is_visible |= comp1.is_visible
            return (True, comp2)
        if len(matched1) == len(comp2.child_comps):
            for (i,j) in matched1.items():
                comp1.child_comps[i].descriptors |= comp2.child_comps[j].descriptors
                comp1.child_comps[i].sames += comp2.child_comps[j].sames
            comp1.descriptors |= comp2.descriptors
            comp1.sames += comp2.sames
            comp1.is_visible |= comp2.is_visible
            return (True, comp1)
        return (False, None)

    def insert_component(self, comp: Component) -> Component:
        cd = comp.depth
        search_seq = [cd, cd+1, cd-1, cd+2, cd-2, cd+3, cd-3]
        for i in search_seq:
            if i in self.components:
                #print(self.components[i])
                for j in range(len(self.components[i])):
                    rst, new_comp = self.compare_components(comp, self.components[i][j])
                    if rst:
                        self.components[i][j] = new_comp
                        return new_comp
        # not found
        if cd in self.components:
            self.components[cd].append(comp)
        else:
            self.components[cd] = [comp]
        return comp

    def update_components_list(self) -> None:
        self.components_l = []
        for _, comps in self.components.items():
            self.components_l += comps

    def calc_overlap(self, view1: View, view2: View) -> (float, float):
        if is_visible(view1) and is_visible(view2):
            ax1, ay1, ax2, ay2 = trim_view_bounds(view1)
            bx1, by1, bx2, by2 = trim_view_bounds(view2)
            s1 = (ax2-ax1) * (ay2-ay1)
            s2 = (bx2-bx1) * (by2-by1)
            x_dist = min(ax2,bx2) - max(ax1,bx1)
            y_dist = min(ay2,by2) - max(ay1,by1)
            if x_dist <= 0 or y_dist <= 0:
                return 0, 0
            overlap = x_dist * y_dist
            return (overlap/s1, overlap/s2)
        return 0    # at least one view is not visible

    # removes overlapping elements in components list
    # returns removed components
    def remove_overlap(self) -> List[Component]:
        self.update_components_list()
        new_comps = list(self.components_l)
        removed = []

        for i, comp1 in enumerate(self.components_l):
            for j, comp2 in enumerate(self.components_l):
                if i != j:
                    if comp1.view.bounds != comp2.view.bounds \
                        and is_visible(comp1.view) and is_visible(comp2.view):
                        ol1, ol2 = self.calc_overlap(comp1.view, comp2.view)
                        #print(ol1,ol2)
                        if min(ol1, ol2) > 0.05 and max(ol1, ol2) < 0.99:  # partial overlap
                            bounds1 = trim_bounds(comp1.view.bounds, (self.width, self.height))
                            bounds2 = trim_bounds(comp2.view.bounds, (self.width, self.height))
                            if (bounds1[3]-bounds1[1] == self.height and bounds1[2]-bounds1[0] == self.width) or (bounds2[3]-bounds2[1] == self.height and bounds2[2]-bounds2[0] == self.width):
                                continue
                            # print(bounds2[3]-bounds2[1], self.height, bounds2[2]-bounds2[0], self.width)
                            img1 = load_img(comp1.uuid)
                            img2 = load_img(comp2.uuid)
                            outline1 = calc_matched_outline(img1, bounds1)
                            outline2 = calc_matched_outline(img2, bounds2)
                            print(comp1.view.bounds, comp2.view.bounds, self.calc_overlap(comp1.view, comp2.view), outline1, outline2)
                            cv2.imwrite(f'{i}_{j}_{comp1.view.bounds}_{ol1}_{outline1}.png', load_img(comp1.uuid, comp1.view.bounds))
                            cv2.imwrite(f'{i}_{j}_{comp2.view.bounds}_{ol2}_{outline2}.png', load_img(comp2.uuid, comp2.view.bounds))



def main():
    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read('../../refactor/config.ini'); print('read config')
    conn = get_db(config)
    cur = conn.cursor(); print('connected')

    cur.execute(
        f"SELECT app_id FROM mars.apps WHERE pkg='{PKG}' AND crawl_ver='{CRAWL}'"
    )
    app_id = cur.fetchone()[0]
    cur.execute(
        f"SELECT uuid FROM mars.views WHERE app_id={app_id}"
    )
    uuids = cur.fetchall()
    cur.close()

    #print(uuids[:10])
    #uuids = [('9e2533ffe36c445f806628a80148eb13',)]

    ac = AppComponents()
    for uuid, in uuids:
        if uuid != UUID: continue #'79f7b059492244898e1043441fb30bf6': continue#'9e2533ffe36c445f806628a80148eb13': continue
        print(uuid)
        vh = ViewHierarchy(os.path.join(PATH, uuid+'.json'), uuid)
        ac.get_component(vh.root, vh.uuid)
        ac.remove_overlap()

    for i, comps in ac.components.items():
        print(i), 
        for c in comps:
            print(len(c.descriptors), len(c.sames), c.sames[:3], c.depth)
            save_component_imgs(c, os.path.join(os.path.expanduser("~"), f'components/{PKG}/{c.depth}_{len(c.sames)}_{c.index}'))


if __name__ == '__main__':
    main()

