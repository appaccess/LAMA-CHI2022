import configparser
import json
import os
from typing import Any, Dict, List

import pandas as pd
from crawl.post_crawl import RemoveCandidate
from detect.checks import CheckResult
from repair.types import Repair
from tqdm import tqdm

from .db import get_db, insert_many


def sanitize_null(text: str) -> str:
    return text.replace("\x00", "\uFFFD")


def upload_metadata_to_db(
    cfg: configparser.ConfigParser, crawl_ver: str, metadata: pd.DataFrame
) -> None:
    """ Upload app metadata to mars.apps. """
    data = []
    for row in metadata.itertuples():
        data.append(
            (
                crawl_ver,
                row.pkg,
                row.name,
                row.versionName,
                row.versionCode,
                row.category,
                row.numDownloads,
                row.platformBuildVersionName,
                row.sdkVersion,
                row.targetSdkVersion,
            )
        )
    insert_sql = """
        INSERT INTO mars.apps(
            crawl_ver, pkg, name, version_name, version_code, category, num_downloads,
            platform_build_version_name, sdk_version, target_sdk_version)
            VALUES %s
        """
    insert_many(cfg, insert_sql, data)


def upload_crawl_to_db(cfg: configparser.ConfigParser, crawl_ver: str, views_dir: str) -> None:
    """ Upload kept crawled views to mars.views. """

    conn = get_db(cfg, superuser=True)
    cur = conn.cursor()
    data = []
    for pkg_entry in tqdm(
        os.scandir(views_dir),
        total=len(os.listdir(views_dir)),
        desc=f"Ingesting views for {crawl_ver}",
    ):
        cur.execute(
            f"SELECT app_id FROM mars.apps WHERE pkg='{pkg_entry.name}' AND crawl_ver='{crawl_ver}'"
        )
        try:
            app_id = cur.fetchone()[0]
        except TypeError:
            print(f"ERROR: {pkg_entry.name} for {crawl_ver} not found")
            return
        for view_hierarchy_file in os.scandir(pkg_entry.path):
            uuid = view_hierarchy_file.name.replace(".json", "")
            data.append((app_id, uuid))
    cur.close()
    insert_sql = """INSERT INTO mars.views(app_id, uuid) VALUES %s"""
    insert_many(cfg, insert_sql, data)


def upload_removed_log_to_db(
    cfg: configparser.ConfigParser, crawl_ver: str, removed: Dict[str, List[RemoveCandidate]],
):
    """ Upload removed_log to mars.removed_views. """

    conn = get_db(cfg, superuser=True)
    cur = conn.cursor()
    data = []
    for pkg, cands in removed.items():
        cur.execute(f"SELECT app_id FROM mars.apps WHERE pkg='{pkg}' AND crawl_ver='{crawl_ver}'")
        app_id = cur.fetchone()[0]
        for cand in cands:
            data.append((app_id, cand.uuid, cand.repl_uuid, cand.reason))
    cur.close()
    insert_sql = """INSERT INTO mars.removed_views(app_id, uuid, repl_uuid, reason) VALUES %s"""
    insert_many(cfg, insert_sql, data)


def upload_scan_to_db(
    cfg: configparser.ConfigParser, crawl_ver: str, check_results: Dict[str, List[CheckResult]]
) -> None:
    """ Upload results of accessibility scan to mars.failures. """

    conn = get_db(cfg, superuser=True)
    for pkg, results in check_results.items():
        cur = conn.cursor()
        data = []
        cur.execute(f"SELECT app_id FROM mars.apps WHERE pkg='{pkg}' AND crawl_ver='{crawl_ver}'")
        app_id = cur.fetchone()[0]
        for result in results:
            cur.execute(
                f"SELECT view_id FROM mars.views WHERE uuid='{result.view_uuid}' AND app_id='{app_id}'"
            )
            view_id = cur.fetchone()
            data.append(
                (
                    view_id,
                    result.result_id,
                    result.check_name,
                    result.result_code,
                    result.class_name,
                    sanitize_null(result.resource_id),
                    sanitize_null(result.content_desc),
                    sanitize_null(result.text),
                    sanitize_null(result.hint_text),
                    json.dumps(result.fail_bounds),
                    json.dumps(result.parent_bounds),
                    result.path,
                )
            )
        cur.close()
        insert_sql = """
            INSERT INTO mars.failures(
                view_id, uuid, check_name, result_code, class_name,
                resource_id, content_desc, text, hint_text, bounds, parent_bounds, path)
            VALUES %s
            """
        insert_many(cfg, insert_sql, data)
    conn.close()


def upload_cnn_labels_to_db(
    cfg: configparser.ConfigParser, preds: Dict[str, Dict[str, float]]
) -> None:
    conn = get_db(cfg, superuser=True)
    cur = conn.cursor()
    data = []

    source = "resnet18"
    for failure_id, label_conf in preds.items():
        cur.execute(f"SELECT failure_id FROM mars.failures WHERE failure_id='{failure_id}'")
        failure_id = cur.fetchone()[0]
        for label, conf in label_conf.items():
            data.append((failure_id, label, source, conf))
    cur.close()
    insert_sql = """INSERT INTO mars.labels(failure_id, label, source, conf) VALUES %s"""
    insert_many(cfg, insert_sql, data)


def upload_repairs_to_db(cfg: configparser.ConfigParser, repairs: List[Repair]) -> None:
    data = [
        (
            repair.failure_id,
            repair.repaired_cont_desc,
            repair.repaired_text,
            repair.repaired_hint_text,
        )
        for repair in repairs
    ]
    insert_sql = """
        INSERT INTO mars.repairs(failure_id, repaired_cont_desc, repaired_text, repaired_hint_text) VALUES %s
    """
    insert_many(cfg, insert_sql, data)


def upload_clusters_to_db(
    cfg: configparser.ConfigParser,
    crawl_ver: str,
    method: str,
    states: Dict[str, Dict[str, List[str]]],
) -> None:
    conn = get_db(cfg, superuser=True)
    cur = conn.cursor()
    update_sql = f"""
        UPDATE mars.views SET {method}_cluster = %s WHERE uuid = %s AND app_id = %s
    """
    for pkg, clusters in states.items():
        cur.execute(f"SELECT app_id FROM mars.apps WHERE pkg='{pkg}' AND crawl_ver='{crawl_ver}'")
        app_id = cur.fetchone()[0]
        for cluster_id, uuids in clusters.items():
            for uuid in uuids:
                cur.execute(update_sql, (cluster_id, uuid, app_id))
    cur.close()
    conn.commit()
