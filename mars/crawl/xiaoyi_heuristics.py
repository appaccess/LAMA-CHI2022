import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from .utils import bfs

__DEBUG = False


def check_state_equivalency_from_json(file0: str, file1: str) -> bool:
    with open(file0, "r") as f0, open(file1, "r") as f1:
        root0 = json.load(f0)
        root1 = json.load(f1)

    # 1. check activity name
    # activityName was not recorded in the crawl?
    # if root0['activityName'] != ''
    #     and root1['activityName'] != ''
    #     and root0['activityName'] != root1['activityName']:
    #     return False

    # 2. check side menu
    if check_drawer_layout(root0, root1) in ["OneDrawer", "DifferentDrawer"]:
        if __DEBUG:
            print(check_drawer_layout(root0, root1))
        return False

    # 3. check dialog
    # if check_dialog(root0, root1) in ['OneDialog', 'DifferentDialog']:
    #     if __DEBUG : print(check_dialog(root0, root1))
    #     return False

    # 4. check selected tab index
    if has_different_selected_tab(root0, root1):
        if __DEBUG:
            print("DifferentSelectedTab")
        return False

    # 5. check checked radio button index
    if has_different_checked_radio(root0, root1):
        if __DEBUG:
            print("DifferentCheckedRadio")
        return False

    # 6. compare classnames
    if get_class_name_similarity(root0, root1) != 1.0:
        if __DEBUG:
            print("ClassName")
        return False

    # 7. compare visible view id
    if get_resource_id_similarity(root0, root1) != 1.0:
        if __DEBUG:
            print("ResourceId")
        return False

    return True


def generate_xiaoyi_heuristics_obj(view_file: str) -> Dict[str, Any]:
    with open(view_file, "r") as f:
        root = json.load(f)

    class_names = set()
    resource_ids = set()
    for node in bfs(root):
        if is_visible(node):
            class_names.add(node["className"])
            resource_ids.add(node["resourceId"])

    return {
        "drawerResId": get_drawer_res_id(root),
        "tabIndex": get_selected_tab_index(root),
        "radioIndex": get_checked_radio_index(root),
        "classNames": sorted(list(class_names)),
        "resourceIds": sorted(list(resource_ids)),
    }


def get_xiaoyi_state_id(view_file: str) -> Optional[str]:
    try:
        obj = json.dumps(generate_xiaoyi_heuristics_obj(view_file), sort_keys=True)
        return hashlib.md5(obj.encode("utf-8")).hexdigest()
    except json.decoder.JSONDecodeError:
        return None


def get_bounds(node: Any) -> Tuple[int, int, int, int]:
    bounds = node["bounds"]
    tl = bounds.split("][")[0][1:]
    br = bounds.split("][")[1][:-1]
    x0 = int(tl.split(",")[0])
    x1 = int(br.split(",")[0])
    y0 = int(tl.split(",")[1])
    y1 = int(br.split(",")[1])
    return (x0, y0, x1, y1)


def get_width(node: Any) -> int:
    _, y0, _, y1 = get_bounds(node)
    return y1 - y0


def get_height(node: Any) -> int:
    x0, _, x1, _ = get_bounds(node)
    return x1 - x0


def is_visible(node: Any) -> bool:
    x0, y0, x1, y1 = get_bounds(node)
    if x0 >= x1 or y0 >= y1:
        return False
    if x1 > node["screenWidth"] or y1 > node["screenHeight"]:
        return False
    return True


def get_set_similarity(set0: Set[str], set1: Set[str]) -> float:
    intersection = len(set0 & set1)
    union = len(set0 | set1)
    if intersection != union and __DEBUG:
        print((set0 | set1) - (set0 & set1))
    return intersection / union


def get_class_name_similarity(root0: Any, root1: Any) -> float:
    set0, set1 = set(), set()
    for node in bfs(root0):
        if is_visible(node):
            set0.add(node["className"])

    for node in bfs(root1):
        if is_visible(node):
            set1.add(node["className"])

    return get_set_similarity(set0, set1)


def remove_ad_resource_id(id_set: Set[str]) -> Set[str]:
    result = set()
    for resource_id in id_set:
        if "." in resource_id or "/" in resource_id:
            result.add(resource_id)
    return result


def get_resource_id_similarity(root0: Any, root1: Any) -> float:
    set0 = set(
        [node["resourceId"] for node in bfs(root0)]
    )  # if node['isImportantForAccessibility']
    set1 = set(
        [node["resourceId"] for node in bfs(root1)]
    )  # if node['isImportantForAccessibility']
    # should call remove_ad_resource_id on both sets
    # however, per Xiaoyi's code, this function did nothing
    # so it is ignored here
    return get_set_similarity(set0, set1)


# Dialog
def find_dialog_node(root: Any) -> Optional[Any]:
    # Only need to check root node, which is smaller than screen
    # E.g. OfferUp->Invite A Friend, or Message->Advance Setting->Phone#
    # Shouldn't check height, as the threeKeyBar may or may not take height in root view...
    if get_width(root) != root["screenWidth"]:
        return root
    return None


def check_dialog(root0: Any, root1: Any) -> str:
    dialog_node0 = find_dialog_node(root0)
    dialog_node1 = find_dialog_node(root1)
    if dialog_node0 is None and dialog_node1 is None:
        return "NoDialog"
    if dialog_node0 is None or dialog_node1 is None:
        return "OneDialog"

    if (
        get_class_name_similarity(root0, root1) != 1.0
        or get_resource_id_similarity(root0, root1) != 1.0
    ):
        return "DifferentDialog"

    return "SameDialog"


# Drawer
def find_drawer_layout_node(root: Any) -> Optional[Any]:
    for node in bfs(root):
        if "widget.DrawerLayout" in node["className"]:
            if len(node["children"]) > 1:
                sideDrawerNode = node["children"][1]
                node0 = node["children"][0]
                node1 = node["children"][1]
                if get_width(node0) < get_width(node1):
                    sideDrawerNode = node["children"][0]
                return sideDrawerNode
    return None


def check_drawer_layout(root0: Any, root1: Any) -> Optional[Any]:
    drawer_node0 = find_drawer_layout_node(root0)
    drawer_node1 = find_drawer_layout_node(root1)
    if drawer_node0 is None and drawer_node1 is None:
        return "NoDrawer"
    if drawer_node0 is None or drawer_node1 is None:
        return "OneDrawer"

    resourceIds0 = sorted([child["resourceId"] for child in drawer_node0["children"]])
    resourceIds1 = sorted([child["resourceId"] for child in drawer_node1["children"]])

    if resourceIds0 == resourceIds1:
        return "SameDrawer"
    return "DifferentDrawer"


def get_drawer_res_id(root: Any) -> Optional[List[str]]:
    drawer_node = find_drawer_layout_node(root)
    if drawer_node is None:
        return None

    return sorted([child["resourceId"] for child in drawer_node["children"]])


# Selected Tab
def get_selected_tab_index(root: Any) -> int:
    # Does any TabLayout have no HorizontalScrollView? Is view.ViewPager the key?
    for node in bfs(root):
        if "android.widget.HorizontalScrollView" in node["className"]:
            is_infinite_loop = False
            tabNode = node
            while len(tabNode["children"]) == 1 and not is_infinite_loop:
                if tabNode["children"][0]:
                    tabNode = tabNode["children"][0]
                else:
                    is_infinite_loop = True

            for i, child in enumerate(tabNode["children"]):
                if child["isSelected"]:
                    return i
    return -1


def has_different_selected_tab(root0: Any, root1: Any) -> bool:
    # Or we should compare selected/unselected structure?
    selected_idx0 = get_selected_tab_index(root0)
    selected_idx1 = get_selected_tab_index(root1)
    return selected_idx0 != selected_idx1


# Radio Button
def get_checked_radio_index(root: Any) -> int:
    for node in bfs(root):
        if "android.widget.RadioGroup" in node["className"]:
            radio_group_node = node
            for i, child in enumerate(radio_group_node["children"]):
                if child["isChecked"]:
                    return i
    return -1


def has_different_checked_radio(root0: Any, root1: Any) -> bool:
    # Or we should compare selected/unselected structure?
    checked_radio_idx0 = get_checked_radio_index(root0)
    checked_radio_idx1 = get_checked_radio_index(root1)
    return checked_radio_idx0 != checked_radio_idx1
