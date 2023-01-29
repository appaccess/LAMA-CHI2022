import argparse
import json
import os
import random
import shutil

from PIL import Image, ImageFile
from tqdm import tqdm


def preprocess_dataset(
    data_dir: str, output_dir: str, img_size: int = 64, train_split: float = 0.8
):
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    REMOVED_CLASSES = ["globe", "trophy", "moon"]

    if train_split < 0 or train_split > 1:
        raise Exception(f"train_split cannot be {train_split}")
    if not os.path.exists(data_dir):
        raise Exception(f"data directory {data_dir} cannot be found")

    os.makedirs(output_dir, exist_ok=True)

    filenames = []
    labels = set()
    for label in os.scandir(data_dir):
        if label.name in REMOVED_CLASSES:
            continue
        if os.path.isfile(label.path):
            continue

        labels.add(label.name.replace("_", ""))
        for image in os.scandir(label.path):
            if image.name.endswith(".jpg") and image.name.startswith("_"):
                filenames.append(image.path)

    filenames.sort()
    random.seed(69)
    random.shuffle(filenames)
    split_num = int(train_split * len(filenames))

    filenames_by_split = {"train": filenames[:split_num], "val": filenames[split_num:]}

    class_index_map = {label: i for i, label in enumerate(sorted(list(labels)))}
    class_index_map_file_path = os.path.join(output_dir, "class_index_map.json")
    if not os.path.exists(class_index_map_file_path):
        with open(class_index_map_file_path, "w") as f:
            json.dump(class_index_map, f, indent=2)

    for split in ["train", "val"]:
        output_dir_split = os.path.join(output_dir, split)
        if not os.path.exists(output_dir_split):
            os.makedirs(output_dir_split)
        else:
            print(f"{output_dir_split} split already exists. Skipping...")
            continue

        for filename in tqdm(filenames_by_split[split], desc=f"preprocessing iamges for {split}"):
            image = Image.open(filename)
            image = image.resize((img_size, img_size), Image.BILINEAR)
            label = filename.split("/")[-2].replace("_", "")
            filename = filename.split("/")[-1].replace("_", "")
            image.save(os.path.join(output_dir, split, f"{label}_{filename}"))


def preprocess_target(pred_dir: str, output_dir: str, img_size: int = 64):
    if not os.path.exists(pred_dir):
        print(f"{pred_dir} invalid or missing. Skipping...")
        return

    dim_ratio_thresh = 3
    dim_abs_min = 20
    pred_output_dir = os.path.join(output_dir, "pred")
    if os.path.exists(pred_output_dir):
        shutil.rmtree(pred_output_dir)
    os.makedirs(pred_output_dir)
    for pred_img in tqdm(
        os.scandir(pred_dir),
        total=len(list(os.listdir(pred_dir))),
        desc="Preprocessing images for eval",
    ):
        image = Image.open(pred_img.path)
        width, height = image.size
        if width > height * dim_ratio_thresh or height > width * dim_ratio_thresh:
            continue
        if width < dim_abs_min or height < dim_abs_min:
            continue
        image = image.resize((img_size, img_size), Image.BILINEAR).convert("RGB")
        image.save(os.path.join(pred_output_dir, pred_img.name))
