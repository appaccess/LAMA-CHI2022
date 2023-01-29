import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from .utils import bfs
from .xiaoyi_heuristics import (
    get_drawer_res_id,
    get_selected_tab_index,
    get_checked_radio_index,
    is_visible,
)


def generate_mars_heuristics_obj(view_file: str) -> Dict[str, Any]:
    with open(view_file, "r") as f:
        root = json.load(f)

    pkg = view_file.split("/")[-2]

    class_names = set()
    resource_ids = set()
    for node in bfs(root):
        if is_visible(node):
            class_names.add(node["className"])
            res_id = node["resourceId"]
            if "android" in res_id or pkg in res_id:
                resource_ids.add(res_id)

    return {
        "drawerResId": get_drawer_res_id(root),
        "tabIndex": get_selected_tab_index(root),
        "radioIndex": get_checked_radio_index(root),
        "classNames": sorted(list(class_names)),
        "resourceIds": sorted(list(resource_ids)),
    }


def get_mars_state_id(view_file: str) -> Optional[str]:
    try:
        obj = json.dumps(generate_mars_heuristics_obj(view_file), sort_keys=True)
        return hashlib.md5(obj.encode("utf-8")).hexdigest()
    except json.decoder.JSONDecodeError:
        return None
