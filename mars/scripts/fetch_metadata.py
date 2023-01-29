import argparse
import configparser
import os
import subprocess

import pandas as pd
import requests
from bs4 import BeautifulSoup

from db.upload import upload_metadata_to_db


def get_playstore_metadata(row: pd.Series) -> pd.Series:
    URL = "https://play.google.com/store/apps/details?id={}&hl=en".format(row["pkg"])
    r = requests.get(URL)
    soup = BeautifulSoup(r.text, "html.parser")
    try:
        row["name"] = soup.find("h1", itemprop="name").find("span").text
        row["category"] = soup.find("a", itemprop="genre").text
        num_downloads = soup.find("div", text="Installs").findNext("span", class_="htlgb").text
        num_downloads = int(num_downloads.replace("+", "").replace(",", ""))
        row["numDownloads"] = num_downloads
    except AttributeError:
        print(f"failed to get playstore metadata for {row['pkg']}")
    return row


def get_apk_metadata(row: pd.Series, apks_path: str) -> pd.Series:
    fields = ["package", "sdkVersion", "targetSdkVersion"]

    apk_file_path = os.path.join(apks_path, f'{row["pkg"]}__{row["versionCode"]}.apk')
    with subprocess.Popen(
        ["aapt dump badging {}".format(apk_file_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=True,
    ) as proc:
        if not proc.stdout:
            return row
        output = proc.stdout.read().replace("'", "").split("\n")
        for attr in output:
            if ":" not in attr:
                continue
            try:
                field_name, value = attr.split(":")
                if field_name in fields:
                    if " " in value:
                        for sub_attr in value.strip().split(" "):
                            if "=" in sub_attr:
                                sub_field_name, sub_value = sub_attr.split("=")
                                if sub_field_name not in ["name", "versionCode"]:
                                    row[sub_field_name] = sub_value
                    else:
                        row[field_name] = value
            except ValueError:
                continue
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch metadata for apks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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

    to_fetch = []
    for apk_filename in os.listdir(config["crawl"]["apks_path"]):
        apk = os.path.splitext(apk_filename)[0]
        pkg, ver = apk.split("__")
        to_fetch.append((pkg, int(ver)))

    metadata_filename = "metadata.csv"
    metadata_file_path = os.path.join(config["crawl"]["output_path"], metadata_filename)
    if os.path.exists(metadata_file_path):
        prev_df = pd.read_csv(metadata_file_path)
        fetched = set(tuple(zip(prev_df["pkg"], prev_df["versionCode"])))
        to_fetch = [t for t in to_fetch if t not in fetched]

    meta_df = pd.DataFrame(to_fetch, columns=["pkg", "versionCode"])
    meta_df = meta_df.apply(get_playstore_metadata, axis=1)
    meta_df = meta_df.apply(get_apk_metadata, apks_path=config["crawl"]["apks_path"], axis=1)
    if os.path.exists(metadata_file_path):
        meta_df = pd.concat(
            [prev_df, meta_df], ignore_index=True, verify_integrity=True, sort=False
        )
    meta_df.sort_values(by=["pkg"], inplace=True)
    meta_df.to_csv(metadata_file_path, index=False, header=True)

    if args.upload:
        upload_metadata_to_db(cfg=config, crawl_ver=args.crawl_ver, metadata=meta_df)
