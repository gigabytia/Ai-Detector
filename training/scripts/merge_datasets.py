# training/scripts/merge_datasets.py
import os
import shutil
import yaml
import random
from pathlib import Path
from tqdm import tqdm

# ══════════════════════════════════════════════════════════
# МАППИНГ КЛАССОВ
# ══════════════════════════════════════════════════════════

DATASET_CLASS_MAP = {
    # forklift-onmnx
    # names: ['Forklift - v1 2023-09-01 5-08pm']
    "forklift-onmnx": {
        0: 2,    # Forklift → forklift (index 2)
    },

    # pallet-detection-atgxn
    # names: ['Pallet']
    "pallet-detection-atgxn": {
        0: 1,    # Pallet → pallet (index 1)
    },

    # warehouse-nmztp
    # names: ['forklift', 'pallet', 'pallet_truck', 'small_load_carrier', 'stillage']
    "warehouse-nmztp": {
        0: 2,    # forklift           → forklift
        1: 1,    # pallet             → pallet
        2: 2,    # pallet_truck       → forklift (тоже техника)
        3: 0,    # small_load_carrier → box
        4: 1,    # stillage           → pallet
    },

    # carrying — раскомментируй когда скачаешь
    # "carrying": {
    #     0: -1,   # person  → ПРОПУСТИТЬ
    #     1: 0,    # box     → box
    # },
}

FINAL_CLASSES = ["box", "pallet", "forklift"]

# ══════════════════════════════════════════════════════════
# ОСТАЛЬНОЙ КОД — НЕ МЕНЯТЬ
# ══════════════════════════════════════════════════════════

BASE_DIR   = Path(__file__).parent.parent
RAW_DIR    = BASE_DIR / "datasets" / "raw"
MERGED_DIR = BASE_DIR / "datasets" / "merged"


def copy_and_remap(src_img_dir, src_lbl_dir, dst_img_dir, dst_lbl_dir,
                   class_map, prefix):
    dst_img_dir.mkdir(parents=True, exist_ok=True)
    dst_lbl_dir.mkdir(parents=True, exist_ok=True)

    img_files = (
        list(src_img_dir.glob("*.jpg")) +
        list(src_img_dir.glob("*.jpeg")) +
        list(src_img_dir.glob("*.png"))
    )

    copied = 0
    for img_path in tqdm(img_files, desc=f"  {prefix}", leave=False):
        stem     = img_path.stem
        lbl_path = src_lbl_dir / f"{stem}.txt"

        if not lbl_path.exists():
            continue

        new_lines = []
        with open(lbl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts  = line.split()
                old_id = int(parts[0])
                new_id = class_map.get(old_id, -1)
                if new_id == -1:
                    continue
                new_lines.append(f"{new_id} {' '.join(parts[1:])}")

        if not new_lines:
            continue

        new_name = f"{prefix}_{stem}"
        dst_ext  = img_path.suffix

        shutil.copy2(img_path, dst_img_dir / f"{new_name}{dst_ext}")
        with open(dst_lbl_dir / f"{new_name}.txt", "w") as f:
            f.write("\n".join(new_lines))

        copied += 1

    return copied


def find_splits(dataset_dir: Path):
    """Находит папки train/val/test в разных возможных структурах."""
    splits = {}

    # Структура 1: dataset/train/images, dataset/valid/images
    for split_name, split_key in [
        ("train", "train"),
        ("valid", "val"),
        ("val",   "val"),
        ("test",  "test"),
    ]:
        img_dir = dataset_dir / split_name / "images"
        lbl_dir = dataset_dir / split_name / "labels"
        if img_dir.exists() and split_key not in splits:
            splits[split_key] = (img_dir, lbl_dir)

    # Структура 2: dataset/images/train, dataset/labels/train
    if not splits:
        for split_name, split_key in [
            ("train", "train"),
            ("valid", "val"),
            ("val",   "val"),
            ("test",  "test"),
        ]:
            img_dir = dataset_dir / "images" / split_name
            lbl_dir = dataset_dir / "labels" / split_name
            if img_dir.exists() and split_key not in splits:
                splits[split_key] = (img_dir, lbl_dir)

    return splits


def main():
    # Очистка предыдущего merge
    if MERGED_DIR.exists():
        print(f"Очищаю предыдущий merged датасет...")
        shutil.rmtree(MERGED_DIR)

    MERGED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Финальные классы: {FINAL_CLASSES}")
    print()

    stats = {"train": 0, "val": 0, "test": 0}
    class_stats = {i: 0 for i in range(len(FINAL_CLASSES))}

    for dataset_name, class_map in DATASET_CLASS_MAP.items():
        dataset_dir = RAW_DIR / dataset_name

        if not dataset_dir.exists():
            print(f"Пропускаю (не найдена папка): {dataset_name}")
            continue

        print(f"Обрабатываю: {dataset_name}")
        print(f"  Маппинг: {class_map}")

        splits = find_splits(dataset_dir)

        if not splits:
            print(f"Не найдены train/val/test папки!")
            print(f"Содержимое: {list(dataset_dir.iterdir())}")
            continue

        prefix = dataset_name[:14].replace("-", "_")

        for split_key, (src_img, src_lbl) in splits.items():
            dst_img = MERGED_DIR / "images" / split_key
            dst_lbl = MERGED_DIR / "labels" / split_key

            n = copy_and_remap(
                src_img, src_lbl,
                dst_img, dst_lbl,
                class_map, prefix
            )

            stats[split_key] = stats.get(split_key, 0) + n
            print(f"  {split_key}: {n} изображений")

        # подсчёт объектов по классам
        for split_key in splits:
            lbl_dir = MERGED_DIR / "labels" / split_key
            if not lbl_dir.exists():
                continue
            for lbl_file in lbl_dir.glob("*.txt"):
                for line in lbl_file.read_text().splitlines():
                    line = line.strip()
                    if line:
                        cls_id = int(line.split()[0])
                        class_stats[cls_id] = class_stats.get(cls_id, 0) + 1

        print()

    # Создаём data.yaml
    yaml_content = {
        "path": str(MERGED_DIR.resolve()),
        "train": "images/train",
        "val":   "images/val",
        "test":  "images/test",
        "nc":    len(FINAL_CLASSES),
        "names": FINAL_CLASSES,
    }

    yaml_path = MERGED_DIR / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_content, f, allow_unicode=True, default_flow_style=False)

    print(f"{'='*50}")
    print(f"Итого изображений:")
    print(f"  train: {stats.get('train', 0)}")
    print(f"  val:   {stats.get('val', 0)}")
    print(f"  test:  {stats.get('test', 0)}")
    print(f"  всего: {sum(stats.values())}")
    print()
    print(f"Объекты по классам:")
    for cls_id, cls_name in enumerate(FINAL_CLASSES):
        count = class_stats.get(cls_id, 0)
        print(f"  [{cls_id}] {cls_name}: {count}")
    print()
    print(f"data.yaml: {yaml_path}")


if __name__ == "__main__":
    main()