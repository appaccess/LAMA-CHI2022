import configparser
import json
import logging
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Any

import crawl.adb_utils as adb_utils
import crawl.errors as errors

from .graph_objects import Action, State
from .xiaoyi_heuristics import get_xiaoyi_state_id


class Crawler:
    def __init__(self, config: configparser.ConfigParser, device: str, app: str) -> None:
        self.config = config
        self.device = device
        self.app = app
        self.version = adb_utils.get_app_version_code(device, app)

        self.views_dir = self.config["crawl"]["views_path"]
        self.screenshots_dir = self.config["crawl"]["screenshots_path"]
        self.graphs_dir = self.config["crawl"]["graphs_path"]
        for d in [self.views_dir, self.screenshots_dir, self.graphs_dir]:
            os.makedirs(os.path.join(d, self.app), exist_ok=True)

        self.uuids: Dict[str, List[str]] = defaultdict(list)
        self.vertices: Dict[str, State] = {}
        self.edges: Dict[State, List[Tuple[Action, State]]] = defaultdict(list)
        self.out_states: List[str] = []
        self.global_explored_actions: Set[str] = set()

    def prepare_device_for_crawl(self) -> None:
        ondevice_file_path = "/sdcard/Android/data/com.android.accesspull/files/files/view.json"
        adb_utils.remove_file_on_device(self.device, ondevice_file_path)
        self.grant_app_perms()
        adb_utils.unlock_device(self.device)
        adb_utils.send_keycode_event(self.device, "KEYCODE_HOME")
        adb_utils.mute_device(self.device)
        adb_utils.rotate_to_orientation(self.device, "portrait")

    def on_crawl_terminate(self) -> None:
        graph_filename = "graph.json"
        graph_full_path = os.path.join(self.graphs_dir, self.app, graph_filename)
        graph: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        if os.path.exists(graph_full_path):
            with open(graph_full_path, "r") as f:
                prev_data = json.load(f)
                graph.update(prev_data)
        for src, act_state_pairs in self.edges.items():
            for action, _ in act_state_pairs:
                graph[src.uuid].append(action.as_dict())
        with open(graph_full_path, "w") as out:
            json.dump(graph, out, sort_keys=True, indent=2)

        self.log_status()
        adb_utils.stop_app(self.device, self.app)

    def get_num_unexplored_actions(self) -> int:
        return sum(len(state.get_unexplored_actions()) for state in self.vertices.values())

    def get_num_explored_actions(self) -> int:
        return sum(len(state.get_explored_actions()) for state in self.vertices.values())

    def grant_app_perms(self) -> None:
        permissions = adb_utils.get_requested_perms_of_installed_app(self.device, self.app)
        for permission in permissions:
            status = adb_utils.enable_permission(self.device, self.app, permission)
            logging.info(f"[{self.device}] {status} -- {permission}")

    def log_status(self) -> None:
        num_states = len(self.vertices.keys())
        logging.info(
            f"[{self.device}] "
            f"Unexplored actions: {self.get_num_unexplored_actions()}, "
            f"Explored actions: {self.get_num_explored_actions()}, "
            f"States: {num_states}"
        )

    def launch_app(self) -> State:
        not_started_count = 0
        next_state = None
        while not next_state:
            adb_utils.send_keycode_event(self.device, "KEYCODE_HOME")
            adb_utils.stop_app(self.device, self.app)
            adb_utils.start_app(self.device, self.app)
            time.sleep(2 * not_started_count + self.config["crawl"].getint("start_app_delay"))
            uuid = adb_utils.pull_state_info(self.config, self.device, self.app)
            if not uuid:
                adb_utils.send_keycode_event(self.device, "KEYCODE_HOME")
                home_test = adb_utils.pull_state_info(self.config, self.device, self.app)
                # TODO(Raymond): Does this "home test" make sense? Check logic.
                if not home_test:
                    raise errors.MissingAccessibilityButtonError()
                else:
                    continue

            treefile = os.path.join(self.views_dir, self.app, uuid) + ".json"
            screenshot = os.path.join(self.screenshots_dir, self.app, uuid) + ".png"
            state_id = get_xiaoyi_state_id(treefile)
            if not state_id:
                os.remove(treefile)
                os.remove(screenshot)
                continue

            if not self.is_crawl_in_correct_app(treefile):
                logging.info(f"[{self.device}] App {self.app} not started yet.")
                os.remove(treefile)
                os.remove(screenshot)
                not_started_count += 1
                continue

            if state_id not in self.vertices:
                next_state = State(treefile=treefile, state_id=state_id)
                self.vertices[state_id] = next_state
            else:
                next_state = self.vertices[state_id]
        self.uuids[state_id].append(uuid)
        return next_state

    def take_action(self, state: State, action_index: int) -> State:
        # TODO(Raymond): Refactor this action_index thing...
        action = state.actions[action_index]
        action.execute(self.device)
        self.global_explored_actions.add(action.desc)

        back_clicked_count = 0
        next_state = None
        while not next_state:
            time.sleep(self.config["crawl"].getint("exec_action_delay"))
            uuid = adb_utils.pull_state_info(self.config, self.device, self.app)
            if not uuid:
                action.priority = -100
                return self.launch_app()

            treefile = os.path.join(self.views_dir, self.app, uuid) + ".json"
            screenshot = os.path.join(self.screenshots_dir, self.app, uuid) + ".png"
            state_id = get_xiaoyi_state_id(treefile)
            if not state_id:
                os.remove(treefile)
                os.remove(screenshot)
                continue

            if not self.is_crawl_in_correct_app(treefile):
                logging.info(
                    f"[{self.device}] {self.app} v{self.version}: Crawl navigated outside package. Relaunching."
                )
                out_state = State(treefile=treefile, state_id=state_id)
                state.set_result_state(action_index, out_state)
                self.out_states.append(state_id)
                os.remove(treefile)
                os.remove(screenshot)

                if back_clicked_count < 3:
                    adb_utils.send_keycode_event(self.device, "KEYCODE_BACK")
                    back_clicked_count += 1
                    continue
                else:
                    return self.launch_app()

            logging.info(
                f"[{self.device}] {self.app} v{self.version}: taking action {action.desc} "
                f"from {state.state_id} to {state_id}"
            )

            if state_id not in self.vertices:
                next_state = State(treefile=treefile, state_id=state_id)
                self.vertices[state_id] = next_state
            else:
                next_state = self.vertices[state_id]

        if back_clicked_count == 0:
            state.set_result_state(action_index, next_state)
            self.uuids[state_id].append(uuid)
            self.edges[state].append((action, next_state))
        return next_state

    def is_crawl_in_correct_app(self, jsonfile: str) -> bool:
        with open(jsonfile, "r") as f:
            data = json.load(f)
            return str(data["packageName"]) == self.app

    def get_next_states(self, cur_state: State) -> List[State]:
        states = []

        # First, try to get next state that can be reached from the current state AND has an action
        for state in cur_state.get_children():
            if state.state_id not in self.out_states:
                if state.has_next_action():
                    states.append(state)

        # Second, get any state has an action
        if not states:
            for state in self.vertices.values():
                if state.has_next_action():
                    states.append(state)

        return sorted(states, key=lambda s: s.priority, reverse=True)

    def go_to_state(self, plan: List[Action]) -> None:
        for action in plan:
            action.execute(self.device)
            time.sleep(self.config["crawl"].getint("exec_action_delay"))

    def get_path_between_states(self, start_state: State, goal_state: State) -> List[Action]:
        visited = set()
        queue = []

        for action_state in self.edges[start_state]:
            visited.add(action_state[1])
            queue.append([action_state])

        while queue:
            path = queue.pop(0)
            _, state = path[-1]
            if state == goal_state:
                actions = [action_state[0] for action_state in path]
                return actions
            for action_state in self.edges[state]:
                if action_state[1] not in visited:
                    visited.add(action_state[1])
                    new_path = list(path)
                    new_path.append(action_state)
                    queue.append(new_path)
        return []

    def crawl_from_state(self, state: State) -> State:
        while state.has_next_action():
            next_action_index = state.get_next_action(self.global_explored_actions)
            state = self.take_action(state, next_action_index)
        logging.info(
            f"[{self.device}] {self.app} v{self.version}: {state.state_id} has no more unexplored actions"
        )
        time.sleep(2)
        return state

    def prepare_state_for_crawl(self, cur_state: State) -> Optional[State]:
        next_states = self.get_next_states(cur_state)
        while next_states:
            next_state = next_states.pop(0)

            if cur_state == next_state:
                return next_state

            plan = self.get_path_between_states(cur_state, next_state)
            if plan:
                logging.info(
                    f"[{self.device}] {self.app} v{self.version}: Going from {cur_state.state_id} to {next_state.state_id}"
                )
                self.go_to_state(plan)
                return next_state

            cur_state = self.launch_app()
            plan = self.get_path_between_states(cur_state, next_state)
            if plan:
                logging.info(
                    f"[{self.device}] {self.app} v{self.version}: Going from {cur_state.state_id} to {next_state.state_id}"
                )
                self.go_to_state(plan)
                return next_state

        if self.get_num_unexplored_actions() != 0:
            next_state = self.launch_app()
            return next_state
        return None

    def crawl(self) -> None:
        if self.get_num_explored_actions() > 0:
            logging.info(
                f"[{self.device}] Restarting crawl of {self.app} v{self.version} from checkpoint"
            )
            self.log_status()
        else:
            logging.info(f"[{self.device}] Starting crawl of {self.app} v{self.version}")
        start_state = self.launch_app()
        while True:
            end_state = self.crawl_from_state(start_state)
            next_state = self.prepare_state_for_crawl(end_state)
            if next_state:
                start_state = next_state
            else:
                break
        logging.info(f"[{self.device}] Crawl of {self.app} v{self.version} completed")
