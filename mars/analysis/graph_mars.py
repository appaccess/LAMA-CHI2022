from collections import defaultdict
import configparser
import copy
import json
import multiprocessing as mp
import os

from db.db import get_db


__DEBUG = False


CRAWL = '2020.12'
BASE = f'/projects/appaccess/crawl_v{CRAWL}/'

crawl_vers = [
    # "2019.12",
    # "2020.01",
    # "2020.02",
    "2020.03",
    "2020.04",
    "2020.05",
    "2020.06",
    "2020.08",
    "2020.10",
    "2020.11",
    "2020.12",
    "2021.02",
]


state_uuids_all = {}
uuid_state_all = {}
removed_uuids = {}


def load_states():
    global state_uuids_all, uuid_state_all
    with open(os.path.join(BASE, 'clusters_mars.json'), 'r') as f:
        print(os.path.join(BASE, 'clusters_mars.json'))
        state_uuids_all = json.load(f)
        uuid_state_all = {}
        for app, rels in state_uuids_all.items():
            uuid_state_all[app] = {}
            for heuristic_hash, uuids in rels.items():
                for uuid in uuids:
                    uuid_state_all[app][uuid] = heuristic_hash
    # return state_uuids, uuid_state


def load_removed():
    global removed_uuids
    removed_uuids = defaultdict(dict)
    removed_path = os.path.join(BASE, 'removed_log.json')
    if os.path.exists(removed_path):
        with open(removed_path, 'r') as f:
            removed = json.load(f)
            if isinstance(removed, list):   # <= 2020.05: a list
                for item in removed:
                    removed_uuids[item['pkg']][item['uuid']] = None
            else:                           # >= 2020.06: a dict
                for app, items in removed.items():
                    for item in items:
                        removed_uuids[app][item['uuid']] = item['repl_uuid']
    else:
        removed_uuids = {app:[] for app in uuid_state_all.keys()}


def load_broken_connections(app_name):
    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read("config.ini")
    conn = get_db(config)
    cur = conn.cursor()

    missing = defaultdict(set)
    missing_reduce_dupe = defaultdict(set)

    cur.execute(f"SELECT app_id FROM mars.apps WHERE crawl_ver='{CRAWL}' AND pkg='{app_name}'")
    res = cur.fetchone()
    if res is None:
        return {}, {}
    app_id, = res    
    cur.execute(f"SELECT view_id, uuid FROM mars.views WHERE app_id={app_id}")
    uuids = cur.fetchall()
    for view_id, uuid in uuids:
        cur.execute(f"SELECT class_name, resource_id, bounds FROM mars.failures WHERE view_id={view_id} AND result_code='MISSING_SPEAKABLE_TEXT'")
        view_failures = cur.fetchall()
        for class_name, resource_id, bounds in view_failures:
            bounds_str = f'[{bounds["left"]},{bounds["top"]}][{bounds["right"]},{bounds["bottom"]}]'
            failure_desc = (resource_id, class_name, bounds_str)
            if uuid not in uuid_state_all[app_name]:
                # print("NOT FOUND:", app_name, uuid)
                pass
            else:
                state = uuid_state_all[app_name][uuid]
                missing[state].add(failure_desc)
                missing_reduce_dupe[state].add((resource_id, class_name))

    cur.close()

    return missing, missing_reduce_dupe


def count_failure(failures):
    count = 0
    all_failures = set()
    for _, failure_set in failures.items():
        # count += len(failure_set)
        all_failures |= failure_set
    # return count
    return len(all_failures)


def traverse(clusters, graph, missing, uuid_state, state_uuids, app_name):
    encountered = defaultdict(set)

    ever_visited = set()
    visited = {}
    all_visited = {}

    # it's possible for a crawl to contain only one screen (uuid)
    # in which case the graph may be empty
    # we add that uuid to the graph
    if len(uuid_state) == 1 and len(graph) == 0:
        graph[list(uuid_state.keys())[0]] = []
    # traverse the graph
    for src in graph.keys():
        ever_visited.update(visited.keys())
        # a uuid we don't know or we have not visited
        if src not in uuid_state or uuid_state[src] not in ever_visited:
            # print(src)
            visited = {}
            # start from each src uuid
            # `None` is used to track depth level
            queue = [src, None]
            level = 0

            while queue:
                curr = queue.pop(0)
                if curr is None:
                    level += 1
                    queue.append(None)
                    if queue[0] is None:
                        break
                    else:
                        continue

                # a uuid not in the uuid_state mapping was probably removed at crawl time
                # attempt to recover from removed_log (removed_uuids)
                if curr not in uuid_state:
                    if curr in removed_uuids[app_name]:
                        repl_uuid = removed_uuids[app_name][curr]
                        if repl_uuid in uuid_state and repl_uuid is not None:
                            uuid_state[curr] = uuid_state[repl_uuid]
                            state_uuids[uuid_state[repl_uuid]].append(curr)
                    else:
                        clusters[app_name]['unknown_uuid'].add(curr)
                        # print(app_name, curr, 'not found')

                if curr not in uuid_state or uuid_state[curr] not in visited:
                    # equiv_currs: the uuids equivalent to curr according to the heuristic
                    if curr in visited:
                        continue
                    if curr in uuid_state:
                        visited[uuid_state[curr]] = level
                        equiv_currs = state_uuids[uuid_state[curr]]
                    else:   # use the uuid as its own state if we can't find its state
                        visited[curr] = level
                        equiv_currs = [curr]
                    
                    # explore all the equivalent uuids
                    for c in equiv_currs:
                        if c in graph:
                            for dst in graph[c]:
                                if isinstance(dst, str):
                                    dst = json.loads(dst)
                                elem_desc = (dst['resource_id'], dst['class_name'], dst['bounds'])
                                if c in uuid_state and uuid_state[c] in missing and elem_desc in missing[uuid_state[c]]:
                                    # print(c, '->', dst['result_uuid'], elem_str)
                                    encountered[uuid_state[c]].add((dst['resource_id'], dst['class_name']))
                                    continue
                                dst_uuid = dst['result_uuid']
                                queue.append(dst_uuid)
            clusters[app_name]['covered'][src] = len(visited)

            all_visited[src] = visited


    clusters[app_name]['states'] = len(state_uuids) + len(clusters[app_name]['unknown_uuid'])
    
    encountered_count = count_failure(encountered)

    return clusters, all_visited, encountered_count


def cluster_for_app(app_name, logdir):
    clusters = {}
    full = {}
    clusters[app_name] = {}
    # print(app_name)

    clusters[app_name]['covered'] = {}
    clusters[app_name]['unknown_uuid'] = set()
    clusters[app_name]['states'] = 0
    full = copy.deepcopy(clusters)
    with open(os.path.join(logdir, 'graph.json'), 'r') as f:
        graph = json.load(f)

        _uuid_state = uuid_state_all[app_name]
        _state_uuids = state_uuids_all[app_name]
        
        missing, missing_reduce_dupe = load_broken_connections(app_name)
        missing_count = count_failure(missing_reduce_dupe)
        clusters, visited_missing, encountered_count = traverse(clusters, graph, missing, _uuid_state, _state_uuids, app_name)
        full, visited_all, _ = traverse(full, graph, {}, _uuid_state, _state_uuids, app_name)

        deltas = {}

        max_len = 0
        max_len_missing = 0
        max_missing_uuid = ''
        max_len_all = 0
        max_deltas = []

        for uuid, lengths in visited_missing.items():
            if len(lengths) > max_len_missing:
                max_len_missing = len(lengths)
                max_missing_uuid = uuid

        if max_missing_uuid in visited_missing:
            uuid_m = max_missing_uuid
            lengths_m = visited_missing[uuid_m]
            for _, lengths in visited_all.items():
                if len(lengths) > max_len_all:
                    max_len_all = len(lengths)

                intersection = lengths.keys() & lengths_m.keys()
                if len(intersection) > max_len:
                    max_len = len(intersection)
                    deltas[uuid_m] = []
                    for shash, length in lengths.items():
                        if shash in lengths_m:
                            delta = lengths_m[shash] - length
                            if delta > 0:
                                deltas[uuid_m].append(delta)
                    max_deltas = deltas[uuid_m]

        clusters[app_name]['unknown_uuid'] = list(clusters[app_name]['unknown_uuid'])
        clusters[app_name]['all_covered'] = max_len_all
        clusters[app_name]['max_covered'] = max_len_missing
        clusters[app_name]['remained'] = clusters[app_name]['all_covered'] - clusters[app_name]['max_covered']
        clusters[app_name]['missing-speakable-text'] = missing_count
        clusters[app_name]['encountered-failure'] = encountered_count
        clusters[app_name]['max-deltas'] = max_deltas
        clusters[app_name]['max-deltas-sum'] = sum(max_deltas)
        clusters[app_name]['max-deltas-max'] = max(max_deltas) if len(max_deltas) > 0 else 0

    return clusters


clusters = {}
counter = 0

def collect_clusters(cluster):
    global clusters, counter
    clusters = {**clusters, **cluster}
    counter += 1
    print(counter, list(cluster.keys())[0])
    with open(f'analysis/graph/graph_{CRAWL}.json', 'w', encoding='utf-8') as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':

    for CRAWL in crawl_vers:

        BASE = f'/projects/appaccess/crawl_v{CRAWL}/'
        print(f'\n{CRAWL}\n')

        load_states()
        load_removed()

        clusters = {}
        counter = 0

        pool = mp.Pool(processes=mp.cpu_count())
        # pool = mp.Pool(processes=1)
        results = []

        graph_path = os.path.join(BASE, 'graphs')
        if not os.path.exists(graph_path):
            graph_path = os.path.join(BASE, 'logs')
            if not os.path.exists(graph_path):
                print(f'Could not find graph/log files for crawl {CRAWL}')

        for app_name in os.listdir(graph_path):
            logdir = os.path.join(graph_path, app_name)
            viewdir = os.path.join(BASE, 'views', app_name)
            if (not os.path.isdir(logdir)) or (not os.path.isdir(viewdir)) or app_name.startswith('.'):
                continue

            # cluster = cluster_for_app(app_name, logdir)
            # clusters = {**clusters, **cluster}
            r = pool.apply_async(cluster_for_app, args = (app_name, logdir), callback = collect_clusters)
            results.append(r)

        pool.close()
        for r in results:
            r.get()
        pool.join()


        with open(f'analysis/graph/graph_{CRAWL}.json', 'w', encoding='utf-8') as f:
            json.dump(clusters, f, ensure_ascii=False, indent=2)
