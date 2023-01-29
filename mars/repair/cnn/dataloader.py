import json
import os

import torchvision.transforms as transforms
from PIL import Image
from torch.utils.data import DataLoader, Dataset


class MobileAppIconDataset(Dataset):
    def __init__(self, data_dir, split, transform, class_index_map):
        self.split = split
        self.images = []
        self.labels = []
        for image in os.scandir(data_dir):
            self.images.append(image.path)
            if self.split != "pred":
                self.labels.append(image.name.split("_")[0])
        self.transform = transform
        self.labels = [class_index_map[l] for l in self.labels]

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        result_id = os.path.splitext(os.path.basename(self.images[idx]))[0]
        image = Image.open(self.images[idx])
        image = self.transform(image)
        if self.split != "pred":
            return result_id, image, self.labels[idx]
        else:
            return result_id, image


def fetch_dataloader(types, data_dir, params):
    train_transformer = transforms.Compose(
        [transforms.Resize(64), transforms.RandomHorizontalFlip(), transforms.ToTensor()]
    )

    eval_transformer = transforms.Compose([transforms.Resize(64), transforms.ToTensor()])

    with open(os.path.join(data_dir, "class_index_map.json"), "r") as f:
        class_index_map = json.load(f)

    dataloaders = {}
    for split in types:
        path = os.path.join(data_dir, split)
        if split == "train":
            dataloader = DataLoader(
                MobileAppIconDataset(path, split, train_transformer, class_index_map),
                batch_size=params.batch_size,
                shuffle=True,
                num_workers=params.num_workers,
                pin_memory=params.cuda,
            )
        else:
            dataloader = DataLoader(
                MobileAppIconDataset(path, split, eval_transformer, class_index_map),
                batch_size=params.batch_size,
                shuffle=False,
                num_workers=params.num_workers,
                pin_memory=params.cuda,
            )
        dataloaders[split] = dataloader
    dataloaders["class_index_map"] = class_index_map
    return dataloaders
