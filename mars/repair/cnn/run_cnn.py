import copy
import json
import logging
import os
import time

import torch
import torch.nn.functional as F
import torch.optim as optim
import torchvision

from repair.cnn.dataloader import fetch_dataloader
from repair.cnn.utils import Params


def run_cnn(params_file, data_dir, restore_dir, restore_file, train=False, evaluate=False):
    assert os.path.isfile(params_file), f"No json configuration file found at {params_file}"
    params = Params(params_file)
    params.cuda = torch.cuda.is_available()
    print("params:", params.__dict__)

    torch.manual_seed(69)
    if params.cuda:
        torch.cuda.manual_seed(69)

    cur_dir = os.path.dirname(__file__)

    log_dir = os.path.join(cur_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_filename = f"cnn-{int(time.time())}.log"
    log_full_path = os.path.join(log_dir, log_filename)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        file_handler = logging.FileHandler(log_full_path)
        file_handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s: %(message)s"))
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(stream_handler)

    logging.info("Loading the datasets...")
    splits = []
    if evaluate:
        splits += ["pred"]
    if train:
        splits += ["train", "val"]
    dataloaders = fetch_dataloader(splits, data_dir, params)
    logging.info("- done.")

    # finetuning on top of pretrained resnet18
    model = torchvision.models.resnet18(pretrained=True)
    try:
        num_ftrs = model.classifier.in_features
    except AttributeError:
        num_ftrs = model.fc.in_features
    model.fc = torch.nn.Linear(num_ftrs, params.num_classes)

    device = torch.device("cuda:0" if params.cuda else "cpu")
    model = model.to(device)
    optimizer = optim.Adam(model.parameters(), lr=params.learning_rate)
    exp_lr_scheduler = optim.lr_scheduler.StepLR(
        optimizer, step_size=params.lr_step_size, gamma=params.lr_gamma
    )
    loss_fn = torch.nn.CrossEntropyLoss()

    loaded_prev_model = False
    if restore_file:
        prev_model_pth = os.path.join(restore_dir, restore_file)
        if os.path.exists(prev_model_pth):
            logging.info(f"Loading saved model weights from {prev_model_pth}...")
            model.load_state_dict(torch.load(prev_model_pth, map_location=device))
            logging.info("- done.")
            loaded_prev_model = True

    if train:
        logging.info("Starting training...")
        model = train(model, dataloaders, loss_fn, optimizer, exp_lr_scheduler, params, restore_dir)

    if evaluate:
        logging.info("Making predictions...")
        preds = predict(model, dataloaders, params)
        with open(os.path.join(cur_dir, "cnn_labels.json"), "w") as out:
            out.write(json.dumps(preds, indent=2, sort_keys=True))
        logging.info("- done.")
        return preds


def train(model, dataloaders, loss_fn, optimizer, scheduler, params, restore_dir):
    since = time.time()
    device = torch.device("cuda:0" if params.cuda else "cpu")

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(params.num_epochs):
        logging.info(f"Epoch {epoch + 1}/{params.num_epochs}")

        # Each epoch has a training and validation phase
        for phase in ["train", "val"]:
            if phase == "train":
                model.train()
            else:
                model.eval()

            running_loss = 0.0
            running_corrects = 0

            # Iterate over data
            for _, inputs_batch, labels_batch in dataloaders[phase]:
                inputs_batch = inputs_batch.to(device)
                labels_batch = labels_batch.to(device)

                # zero the parameter gradients
                optimizer.zero_grad()

                # forward
                # track history if only in train
                with torch.set_grad_enabled(phase == "train"):
                    outputs = model(inputs_batch)
                    _, preds = torch.max(outputs, 1)
                    loss = loss_fn(outputs, labels_batch)

                    # backward + optimize only if in training phase
                    if phase == "train":
                        loss.backward()
                        optimizer.step()

                # statistics
                running_loss += loss.item() * inputs_batch.size(0)
                running_corrects += int(torch.sum(preds == labels_batch.data).item())
            if phase == "train":
                scheduler.step()

            epoch_loss = running_loss / len(dataloaders[phase].dataset)
            epoch_acc = running_corrects / len(dataloaders[phase].dataset)

            logging.info(f"Phase: {phase} Loss: {epoch_loss} Acc: {epoch_acc}")

            # deep copy the model
            if phase == "val" and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

        logging.info("-" * 10)

    time_elapsed = time.time() - since
    logging.info(f"Training complete in {time_elapsed // 60:.0f}m {time_elapsed % 60:.0f}s")
    logging.info(f"Best val accuracy: {best_acc}")

    os.makedirs(restore_dir, exist_ok=True)
    save_file = os.path.join(restore_dir, "best_weights.pth")
    logging.info(f"Saving best model weights to {save_file}")
    torch.save(best_model_wts, save_file)

    # load best model weights
    model.load_state_dict(best_model_wts)
    return model


def predict(model, dataloaders, params):
    pred_dataloader = dataloaders["pred"]
    class_index_map = dataloaders["class_index_map"]
    index_class_map = {idx: cls_ for cls_, idx in class_index_map.items()}
    device = torch.device("cuda:0" if params.cuda else "cpu")

    model.eval()
    predictions = {}

    for id_batch, data_batch in pred_dataloader:
        data_batch = data_batch.to(device)
        output_batch = model(data_batch)
        prob_batch = F.softmax(output_batch, dim=1)
        _, pred_batch = torch.max(output_batch, 1)
        pred_batch = pred_batch.cpu().tolist()
        prob_batch = prob_batch.cpu().tolist()
        for i, result_id in enumerate(id_batch):
            predictions[result_id] = (index_class_map[pred_batch[i]], prob_batch[i][pred_batch[i]])

    predictions = {k: {v[0]: v[1]} for k, v in predictions.items() if v[0] != "negative"}
    return predictions
