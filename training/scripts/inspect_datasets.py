# training/scripts/inspect_datasets.py
import os
import yaml

datasets_dir = os.path.join(os.path.dirname(__file__), "..", "datasets", "raw")

for dataset_name in os.listdir(datasets_dir):
    yaml_path = os.path.join(datasets_dir, dataset_name, "data.yaml")
    if not os.path.exists(yaml_path):
        continue

    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    print(f"\n{'='*40}")
    print(f"Датасет: {dataset_name}")
    print(f"Классы ({cfg.get('nc', '?')}): {cfg.get('names', [])}")

    # считаем изображения
    for split in ["train", "valid", "test"]:
        img_dir = os.path.join(datasets_dir, dataset_name, split, "images")
        if os.path.exists(img_dir):
            count = len([f for f in os.listdir(img_dir)
                        if f.lower().endswith((".jpg", ".png", ".jpeg"))])
            print(f"  {split}: {count} изображений")