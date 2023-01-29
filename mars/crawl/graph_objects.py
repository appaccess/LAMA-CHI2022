import json
import os
import string
from collections import defaultdict
from itertools import groupby
from operator import itemgetter
from typing import Any, Iterator, List, Optional, Set, Dict

import crawl.adb_utils as adb_utils
import crawl.utils as utils


class Action:
    text_input_map = {
        "search": "sushi",
        "location": "seattle",
        "address": "seattle",
        "name": "john",
        "default": "buffalo",
        "email": "mobileaccessrepair@gmail.com",
        "username": "mobileaccessrepair",
        "age": "30",
        "city": "seattle",
        "state": "washington",
        "zip": "98101",
    }

    def __init__(
        self,
        desc: str,
        class_name: str,
        resource_id: str,
        action_type: str,
        input_type: str,
        bounds: str,
        result_state: Optional["State"],
        priority: int,
    ) -> None:
        self.desc = desc
        self.class_name = class_name
        self.resource_id = resource_id
        self.action_type = action_type
        self.input_type = input_type
        self.bounds = bounds
        self.result_state = result_state
        self.priority = priority
        self.touchx, self.touchy = utils.get_touch_from_bounds(self.bounds)
        self.text = self.get_input_text()

    def as_dict(self) -> Dict[str, Any]:
        r = {k: v for k, v in self.__dict__.items() if k != "result_state"}
        r["result_state"] = None if not self.result_state else self.result_state.state_id
        r["result_uuid"] = None if not self.result_state else self.result_state.uuid
        return r

    def execute(self, device: str) -> None:
        if self.input_type == "touch":
            adb_utils.send_touch_event(device, self.touchx, self.touchy)
        elif self.input_type == "text":
            adb_utils.send_text_event(device, self.text)

    def get_input_text(self) -> str:
        if self.input_type == "text":
            for k, v in Action.text_input_map.items():
                if k in self.desc:
                    return v
            return Action.text_input_map["default"]
        else:
            return ""


class State:
    def __init__(self, treefile: str, state_id: str, priority: Optional[int] = 0) -> None:
        self.treefile = treefile
        self.uuid = os.path.splitext(os.path.basename(treefile))[0]
        self.state_id = state_id
        self.priority = priority
        self.priority_words = {
            "blacklist": [
                "login",
                "facebook",
                "fb",
                "gmail",
                "error",
                "share",
                "call",
                "sign out",
                "log out",
                "sign in",
                "join",
            ],
            "negative": [
                "dismiss",
                "reject",
                "skip",
                "deny",
                "no",
                "never",
                "cancel",
                "later",
                "close",
                "finish",
                "next",
            ],
            "positive": ["accept", "allow", "yes", "okay", "ok", "save",],
        }
        self.actions: List[Action] = []
        self.init_actions()

    def __hash__(self) -> int:
        return int(self.state_id, 16)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, State):
            return NotImplemented
        return self.state_id == other.state_id

    def assign_priority_to_action(self, action: Action, prio_cls: str, priority: int) -> None:
        def get_shingles(size: int, sent: List[str]) -> Iterator[Any]:
            for i in range(0, len(sent) - size + 1):
                yield tuple(sent[i : i + size])

        action_text = action.desc.split(" ")
        for prio_words in self.priority_words[prio_cls]:
            words = prio_words.split(" ")
            # single word
            if len(words) == 1:
                if words[0] in action_text:
                    action.priority = priority
            # phrase
            else:
                if len(words) <= len(action_text):
                    if tuple(words) in get_shingles(len(words), action_text):
                        action.priority = priority

    def get_unexplored_actions(self) -> List[int]:
        return [i for i, x in enumerate(self.actions) if x.priority >= 0 and not x.result_state]

    def get_explored_actions(self) -> List[int]:
        return [i for i, x in enumerate(self.actions) if x.priority >= 0 and x.result_state]

    def sort_actions_by_priority(self, action_indices: List[int]) -> List[int]:
        return sorted(action_indices, key=lambda i: self.actions[i].priority, reverse=True)

    def has_next_action(self) -> bool:
        return len(self.get_unexplored_actions()) > 0

    def get_next_action(self, global_explored_actions: Set[str]) -> int:
        # De-prioritize actions that have been seen before in any state
        for action in self.actions:
            if action.priority >= 5:
                continue
            if action.desc in global_explored_actions:
                action.priority = 1

        # Return index into list of actions, sorted by priority
        action_indices = self.get_unexplored_actions()
        action_indices = self.sort_actions_by_priority(action_indices)
        return action_indices[0]

    def _get_best_text(self, elem: Any) -> str:
        best_text = ""
        if elem["contentDesc"]:
            best_text = elem["contentDesc"]
        elif elem["text"]:
            best_text = elem["text"]
        elif elem["hintText"]:
            best_text = elem["hintText"]
        else:
            child_text = []
            for child in elem["children"]:
                child_best = self._get_best_text(child)
                if child_best:
                    child_text.append(child_best)
            labeled_children = [c for c in child_text if elem["packageName"] not in c]
            if labeled_children:
                best_text = " ".join(sorted(set(labeled_children)))
            else:
                best_text = " ".join(sorted(set(child_text)))

        if not best_text:
            best_text = elem["resourceId"]

        # Sanitize unless contains resourceId
        if elem["packageName"] not in best_text:
            best_text = best_text.translate(str.maketrans("", "", string.punctuation))
            best_text = best_text.lower().strip()
        return best_text

    def get_children(self) -> List["State"]:
        action_indices = self.get_explored_actions()
        actions = [self.actions[i] for i in action_indices]
        return [action.result_state for action in actions if action.result_state]

    def init_actions(self) -> None:
        def init_action_for_elem(elem: Any) -> None:
            if is_actionable(elem):
                if not has_actionable_children(elem):
                    best_text = self._get_best_text(elem)
                    if best_text:
                        elem["desc"] = best_text
                        self.add_action(elem)
                else:
                    for child in elem["children"]:
                        init_action_for_elem(child)

        with open(self.treefile, "r") as fp:
            json_data = json.load(fp)
        for elem in utils.bfs(json_data):
            init_action_for_elem(elem)

        # If there are multiple things with exactly the same bounds on a screen,
        # smartly select one of these actions per unique set of bounds.
        action_bounds_map = defaultdict(list)
        for action in self.actions:
            action_bounds_map[action.bounds].append(action)
        deduped_actions = []
        for actions in action_bounds_map.values():
            actions_with_resourceids = [a for a in actions if a.resource_id != ""]
            if len(actions_with_resourceids):
                seen_descs = set()
                for a in actions_with_resourceids:
                    if a.desc not in seen_descs:
                        deduped_actions.append(a)
                        seen_descs.add(a.desc)
            else:
                deduped_actions.append(actions[0])
        self.actions = deduped_actions
        self.detect_and_remove_calendar()

    def detect_and_remove_calendar(self) -> None:
        # detect and remove actions if a calendar is detected
        descs_with_ints, actions_with_ints = [], []
        for action in self.actions:
            try:
                descs_with_ints.append(int(action.desc))
                actions_with_ints.append(action)
            except ValueError:
                continue
        consecutive_ints = []
        for _, g in groupby(enumerate(descs_with_ints), lambda ix: ix[0] - ix[1]):
            consecutive_ints.append(list(map(itemgetter(1), g)))
        if consecutive_ints:
            longest_seq = max(consecutive_ints, key=len)
            if len(longest_seq) >= 7:
                if all(1 <= x <= 31 for x in longest_seq):
                    self.actions = [
                        action for action in self.actions if action not in actions_with_ints
                    ]
                    keep_action = [
                        action for action in actions_with_ints if int(action.desc) == longest_seq[0]
                    ][0]
                    self.actions.append(keep_action)

    def add_action(self, elem: Any) -> None:
        if utils.is_valid_bounds(elem["bounds"]):
            if elem["className"] == "android.widget.EditText" and elem["isFocused"]:
                action = self.create_action(elem, input_type="text", priority=1)
            else:
                action = self.create_action(elem, input_type="touch", priority=3)
            self.actions.append(action)

    def create_action(self, elem: Any, input_type: str, priority: int) -> Action:
        action = Action(
            desc=elem["desc"],
            class_name=elem["className"],
            resource_id=elem["resourceId"],
            action_type="clickable",
            input_type=input_type,
            bounds=elem["bounds"],
            result_state=None,
            priority=priority,
        )
        # Give first priority to NEGATIVE words.
        self.assign_priority_to_action(action, "negative", 10)
        # Give second priority to POSITIVE words
        self.assign_priority_to_action(action, "positive", 5)
        # Give lowest priority to BLACKLIST words
        self.assign_priority_to_action(action, "blacklist", -1)
        return action

    def set_result_state(self, action_index: int, result_state: "State") -> None:
        self.actions[action_index].result_state = result_state


def is_actionable(elem: Any) -> bool:
    # TODO(Raymond): Add long-clickable functionality
    actionable = elem["isClickable"] or elem["isFocusable"]
    visible = elem["isVisibleToUser"] and elem["isImportantForAccessibility"]
    return bool(actionable) and bool(visible)


def has_actionable_children(elem: Any) -> bool:
    for child in elem["children"]:
        for child_elem in utils.bfs(child):
            if is_actionable(child_elem):
                return True
    return False
