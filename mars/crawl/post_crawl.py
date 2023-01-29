import json
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

from PIL import Image


@dataclass(frozen=True)
class RemoveCandidate:
    uuid: str
    ext: str
    reason: str
    repl_uuid: Optional[str] = None


def check_broken_images(screenshots_path: str) -> List[RemoveCandidate]:
    cands = []
    for img in os.scandir(screenshots_path):
        try:
            im = Image.open(img.path)
            im.verify()
        except (IOError, SyntaxError):
            uuid, ext = os.path.splitext(img.name)
            cands.append(RemoveCandidate(uuid=uuid, ext=ext, reason="BROKEN_SCREENSHOT"))
    return cands


def check_orphan_files(views_path: str, screenshots_path: str) -> List[RemoveCandidate]:
    cands = []
    for view in os.scandir(views_path):
        uuid, ext = os.path.splitext(view.name)
        ss_path = view.path.replace("screenshots", "views").replace(".png", ".json")
        if not os.path.exists(ss_path):
            cands.append(RemoveCandidate(uuid=uuid, ext=ext, reason="MISSING_VIEW_HIERARCHY"))
    for img in os.scandir(screenshots_path):
        uuid, ext = os.path.splitext(img.name)
        view_path = img.path.replace("views", "screenshots").replace(".json", ".png")
        if not os.path.exists(view_path):
            cands.append(RemoveCandidate(uuid=uuid, ext=ext, reason="MISSING_SCREENSHOT"))
    return cands


def check_identical_screens(
    views_path: str, removed: List[RemoveCandidate]
) -> List[RemoveCandidate]:
    cands = []

    groups = defaultdict(list)
    for view_hierarchy in os.scandir(views_path):
        with open(view_hierarchy.path, "r") as f:
            uuid, ext = os.path.splitext(view_hierarchy.name)
            if ext != ".json":
                continue
            try:
                view = json.load(f)
                sorted_view = json.dumps(view, sort_keys=True)
                groups[sorted_view].append(uuid)
            except json.decoder.JSONDecodeError:
                cands.append(RemoveCandidate(uuid=uuid, ext=ext, reason="BROKEN_VIEW_HIERARCHY"))

    removed_uuids = [c.uuid for c in removed]
    for grp in list(groups.values()):
        if len(grp) <= 1:
            continue
        selected_to_keep = None
        for iden_uuid in grp:
            if iden_uuid not in removed_uuids:
                selected_to_keep = iden_uuid
                break
        for iden_uuid in grp:
            if iden_uuid != selected_to_keep:
                cands.append(
                    RemoveCandidate(
                        uuid=iden_uuid,
                        ext=".json",
                        reason="DUPLICATE_VIEW_HIERARCHY",
                        repl_uuid=selected_to_keep,
                    )
                )
    return cands


def fix_graphs(graph_file_path: str, removed: List[RemoveCandidate]) -> None:
    removed_uuids = {c.uuid: c for c in removed}

    with open(graph_file_path, "r") as f:
        graph = json.load(f)
    remove_keys = []
    for from_uuid in list(graph.keys()):
        if from_uuid in removed_uuids:
            repl_uuid = removed_uuids[from_uuid].repl_uuid
            if repl_uuid:
                graph[repl_uuid] = graph.pop(from_uuid)
            else:
                remove_keys.append(from_uuid)

    graph = {k: v for k, v in graph.items() if k not in remove_keys}

    for actions in graph.values():
        for action in actions:
            result_uuid = action["result_uuid"]
            if result_uuid in removed_uuids:
                action["result_uuid"] = removed_uuids[result_uuid].repl_uuid

    with open(graph_file_path, "w") as fout:
        json.dump(graph, fout, indent=2, sort_keys=True)
