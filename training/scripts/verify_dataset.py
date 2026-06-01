# training/scripts/verify_dataset.py
import os
import yaml
from pathlib import Path
from collections import defaultdict

BASE_DIR    = Path(__file__).parent.parent
MERGED_DIR  = BASE_DIR / "datasets" / "merged"

with open(MERGED_DIR / "data.yaml") as f:
    cfg = yaml.safe_load(f)

print(f"Классы: {cfg['names']}")
print()

for split in ["train", "val", "test"]:
    img_dir = MERGED_DIR / "images" / split
    lbl_dir = MERGED_DIR / "labels" / split

    if not img_dir.exists():
        continue

    imgs = list(img_dir.glob("*.jpg")) + \
           list(img_dir.glob("*.jpeg")) + \
           list(img_dir.glob("*.png"))

    class_counts = defaultdict(int)
    no_label = 0
    empty    = 0

    for img in imgs:
        lbl = lbl_dir / f"{img.stem}.txt"
        if not lbl.exists():
            no_label += 1
            continue
        lines = [l.strip() for l in lbl.read_text().splitlines() if l.strip()]
        if not lines:
            empty += 1
            continue
        for line in lines:
            class_counts[int(line.split()[0])] += 1

    print(f"{'='*35}")
    print(f"Split: {split}")
    print(f"  Изображений: {len(imgs)}")
    print(f"  Без аннотации: {no_label}")
    print(f"  Пустых: {empty}")
    print(f"  Объекты по классам:")
    for cls_id, count in sorted(class_counts.items()):
        name = cfg['names'][cls_id] if cls_id < len(cfg['names']) else f"unknown_{cls_id}"
        print(f"    [{cls_id}] {name}: {count}")