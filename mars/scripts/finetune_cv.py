from repair.cnn.build_dataset import preprocess_dataset
from repair.cnn.run_cnn import run_cnn


def main():
    data_dir = "repair/cnn/data/raw"
    parts_dir = "repair/cnn/data/parts"
    params_file = "repair/cnn/params.json"
    restore_dir = "repair/cnn/exp"
    preprocess_dataset(data_dir, parts_dir)
    run_cnn(
        params_file=params_file,
        data_dir=parts_dir,
        restore_dir=restore_dir,
        restore_file=None,
        train=True,
        evaluate=False,
    )


if __name__ == "__main__":
    main()
