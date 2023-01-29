import argparse
import configparser
import json
import multiprocessing as mp
import os
import shutil
from collections import defaultdict
from typing import Dict, Iterator, List

import psycopg2
from PIL import Image

from db.db import get_db
from db.upload import upload_cnn_labels_to_db, upload_repairs_to_db
from repair.cnn.build_dataset import preprocess_dataset, preprocess_target
from repair.cnn.run_cnn import run_cnn
from repair.types import Repair


def crop(screenshot_path: str, output_dir: str, fail: psycopg2.extras.DictRow) -> None:
    img_path = os.path.join(screenshot_path, fail["pkg"], fail["view_uuid"] + ".png")
    img = Image.open(img_path)
    try:
        segment = img.crop(
            (
                fail["bounds"]["left"],
                fail["bounds"]["top"],
                fail["bounds"]["right"],
                fail["bounds"]["bottom"],
            )
        )
        segment_out = os.path.join(output_dir, str(fail["failure_id"])) + ".png"
        segment.save(segment_out)
    except SystemError:
        # Happens when crop dims not well defined (e.g., larger than img dims, negative)
        print(fail)


def prepare_failure_crops_for_cv(
    cfg: configparser.ConfigParser, output_dir: str, fails: List[psycopg2.extras.DictRow]
) -> None:
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    fails = [(cfg["crawl"]["screenshots_path"], output_dir, fail) for fail in fails]
    with mp.Pool(mp.cpu_count() - 1) as p:
        p.starmap(crop, fails)


def get_failures(
    cfg: configparser.ConfigParser, crawl_ver: str
) -> Iterator[psycopg2.extras.DictRow]:
    conn = get_db(cfg, superuser=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        f"""
        SELECT
            failures.failure_id,
            failures.uuid as failure_uuid,
            failures.result_code,
            failures.class_name,
            failures.resource_id,
            failures.content_desc,
            failures.text,
            failures.hint_text,
            failures.bounds,
            failures.path,
            views.uuid as view_uuid,
            apps.pkg
        FROM
            mars.failures
        JOIN
            mars.views ON (failures.view_id = views.view_id)
        JOIN
            mars.apps ON (views.app_id = apps.app_id)
        WHERE
            result_code != 'PASSED' AND
            result_code != 'CLICKABLE_SAME_SPEAKABLE_TEXT' AND
            apps.crawl_ver = '{crawl_ver}'
        ORDER BY
            failures.failure_id ASC
        """
    )
    for row in cur.fetchall():
        yield row
    cur.close()


def triage_failures(
    scan_results: Iterator[psycopg2.extras.DictRow],
) -> Dict[str, List[psycopg2.extras.DictRow]]:
    triaged = defaultdict(list)
    for row in scan_results:
        result_code = row["result_code"]
        if result_code in [
            "MISSING_SPEAKABLE_TEXT",
            "MISSING_HINT_TEXT",
            "UNINFORMATIVE_DESC",
        ]:
            triaged["not_simple"].append(row)
        elif result_code in [
            "REDUNDANT_DESC",
            "MISSING_HINT_TEXT_WITH_CONT_DESC",
            "HINT_TEXT_WITH_CONT_DESC",
        ]:
            triaged["simple"].append(row)
    return triaged


def make_repairs(
    cfg: configparser.ConfigParser, triaged: Dict[str, List[psycopg2.extras.DictRow]],
) -> List[Repair]:
    conn = get_db(cfg, superuser=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    CV_CONF_THRESH = 0.95
    repairs = []

    for fail in triaged["not_simple"]:
        # TODO(Raymond): Update to handle other label sources such as crowd, textual
        # heuristics, etc. Need to think about aggregation, prioritization, and confidence.
        failure_id = fail["failure_id"]
        result_code = fail["result_code"]
        cur.execute(
            f"SELECT * from mars.labels WHERE failure_id='{failure_id}'"
            f"AND source='resnet18' ORDER BY conf DESC"
        )
        top_label = cur.fetchone()
        if not top_label:
            continue
        if not top_label["conf"] or top_label["conf"] < CV_CONF_THRESH:
            continue

        if result_code in ["MISSING_SPEAKABLE_TEXT", "UNINFORMATIVE_DESC"]:
            repairs.append(
                Repair(
                    failure_id=failure_id,
                    repaired_cont_desc=top_label["label"],
                    repaired_text=None,
                    repaired_hint_text=None,
                )
            )
        elif result_code == "MISSING_HINT_TEXT":
            repairs.append(
                Repair(
                    failure_id=failure_id,
                    repaired_cont_desc=None,
                    repaired_text=None,
                    repaired_hint_text=top_label["label"],
                )
            )

    for fail in triaged["simple"]:
        failure_id = fail["failure_id"]
        result_code = fail["result_code"]
        if result_code == "MISSING_HINT_TEXT_WITH_CONT_DESC":
            repaired_hint_text = fail["content_desc"]
            repairs.append(
                Repair(
                    failure_id=failure_id,
                    repaired_cont_desc=None,
                    repaired_text=None,
                    repaired_hint_text=repaired_hint_text,
                )
            )
        elif result_code == "HINT_TEXT_WITH_CONT_DESC":
            repairs.append(
                Repair(
                    failure_id=failure_id,
                    repaired_cont_desc=None,
                    repaired_text=None,
                    repaired_hint_text=fail["hint_text"],
                )
            )
        elif result_code == "REDUNDANT_DESC":
            fixed_desc = None
            split_desc = fail["content_desc"].split(" ")
            if split_desc[-1] == "button":
                fixed_desc = " ".join(split_desc[:-1])
            elif split_desc[-1] == "checked":
                if split_desc[-2] == "not":
                    fixed_desc = " ".join(split_desc[:-2])
                else:
                    fixed_desc = " ".join(split_desc[:-1])
            if fixed_desc:
                repairs.append(
                    Repair(
                        failure_id=failure_id,
                        repaired_cont_desc=fixed_desc,
                        repaired_text=None,
                        repaired_hint_text=None,
                    )
                )
    return repairs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_dir",
        default="repair/cnn/data/raw",
        help="Directory containing unprocessed training dataset",
    )
    parser.add_argument(
        "--pred_dir",
        default="repair/cnn/data/pred",
        help="Directory containing unprocessed images for evaluation",
    )
    parser.add_argument(
        "--parts_dir",
        default="repair/cnn/data/parts",
        help="Directory for preprocessed dataset and images for evaluation",
    )
    parser.add_argument(
        "--params_file",
        default="repair/cnn/params.json",
        help="JSON file containing experiment params",
    )
    parser.add_argument(
        "--restore_dir",
        default="repair/cnn/exp",
        help="Directory containing files for previously trained model weights",
    )
    parser.add_argument(
        "--restore_file",
        default="best_weights.pth",
        help="Name of the file containing weights of previously trained model",
    )
    parser.add_argument(
        "--crawl_ver", "-c", help="Name for version of crawl (<Year>.<Month>)", required=True
    )
    parser.add_argument("--config", help="Path to config file.", default="config.ini", type=str)
    parser.add_argument(
        "--upload", "-u", help="Set to upload results to database.", action="store_true"
    )
    args = parser.parse_args()

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(args.config)

    scan_results = get_failures(config, args.crawl_ver)
    triaged = triage_failures(scan_results)

    # Generate labels with CV
    prepare_failure_crops_for_cv(cfg=config, output_dir=args.pred_dir, fails=triaged["not_simple"])
    preprocess_dataset(args.data_dir, args.parts_dir)
    preprocess_target(args.pred_dir, args.parts_dir)
    preds = run_cnn(
        args.params_file,
        args.parts_dir,
        args.restore_dir,
        args.restore_file,
        train=False,
        evaluate=True,
    )
    upload_cnn_labels_to_db(config, preds)

    # Upload final repairs, exactly one per failure
    repairs = make_repairs(config, triaged)
    repairs_serialized = [r.__dict__ for r in repairs]
    repairs_filename = "scan_results.json"
    results_file_path = os.path.join(config["crawl"]["output_path"], repairs_filename)
    with open(results_file_path, "w") as out:
        json.dump(repairs_serialized, out, indent=2)

    if args.upload:
        upload_repairs_to_db(config, repairs)
