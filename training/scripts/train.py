# training/scripts/train.py
import os
import sys
import torch
from pathlib import Path
from ultralytics import YOLO

BASE_DIR  = Path(__file__).parent.parent
DATA_YAML = BASE_DIR / "datasets" / "merged" / "data.yaml"
RUNS_DIR  = BASE_DIR / "runs"


def main():
    # ── Проверки ──────────────────────────────────────────
    if not DATA_YAML.exists():
        print(f"Не найден data.yaml: {DATA_YAML}")
        print("Запусти сначала: python scripts/merge_datasets.py")
        sys.exit(1)

    # ── Железо ────────────────────────────────────────────
    gpu_available = torch.cuda.is_available()
    if gpu_available:
        device  = 0
        vram_gb = torch.cuda.get_device_properties(0).total_mem / 1e9 \
            if hasattr(torch.cuda.get_device_properties(0), 'total_mem') \
            else torch.cuda.get_device_properties(0).total_memory / 1e9
        gpu_name = torch.cuda.get_device_name(0)
        print(f"GPU: {gpu_name}")
        print(f"VRAM: {vram_gb:.1f} GB")

        if vram_gb >= 10:
            batch = 32
            imgsz = 640
        elif vram_gb >= 6:
            batch = 16
            imgsz = 640
        elif vram_gb >= 4:
            batch = 8
            imgsz = 640
        else:
            batch = 4
            imgsz = 416
    else:
        device = "cpu"
        batch  = 4
        imgsz  = 416
        print("GPU не найден, обучение на CPU (очень медленно!)")

    # ── Настройки ─────────────────────────────────────────
    print()
    print(f"Настройки обучения:")
    print(f"  data:    {DATA_YAML}")
    print(f"  device:  {device}")
    print(f"  batch:   {batch}")
    print(f"  imgsz:   {imgsz}")
    print(f"  epochs:  100")
    print()

    # ── Базовая модель ────────────────────────────────────
    # yolov8s.pt — маленькая, быстрая, хороша для начала
    # yolov8m.pt — средняя, точнее, нужно ~8GB VRAM
    # yolov8l.pt — большая, ещё точнее, нужно ~12GB VRAM
    base_model = "yolov8s.pt"
    print(f"Базовая модель: {base_model}")
    model = YOLO(base_model)

    # ── Обучение ──────────────────────────────────────────
    results = model.train(
        # данные
        data=str(DATA_YAML),

        # архитектура
        imgsz=imgsz,

        # обучение
        epochs=100,
        batch=batch,
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3,
        warmup_momentum=0.8,

        # аугментации
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=5.0,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        flipud=0.0,
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,

        # железо
        device=device,
        workers=4 if sys.platform != "win32" else 0,

        # сохранение
        project=str(RUNS_DIR),
        name="carry_detect_v1",
        exist_ok=True,
        save=True,
        save_period=10,

        # early stopping
        patience=20,

        # логи
        plots=True,
        verbose=True,
    )

    # ── Результаты ────────────────────────────────────────
    best_path = Path(results.save_dir) / "weights" / "best.pt"
    last_path = Path(results.save_dir) / "weights" / "last.pt"

    print()
    print(f"{'='*60}")
    print(f"Обучение завершено!")
    print(f"Лучшая модель:  {best_path}")
    print(f"Последняя:      {last_path}")
    print(f"Все результаты: {results.save_dir}")
    print(f"{'='*60}")

    # ── Проверка на val ───────────────────────────────────
    print()
    print("Валидация лучшей модели на val split...")
    best_model = YOLO(str(best_path))
    metrics = best_model.val(
        data=str(DATA_YAML),
        split="val",
        conf=0.25,
        verbose=False,
    )

    print()
    print(f"Метрики:")
    print(f"  mAP50:    {metrics.box.map50:.4f}")
    print(f"  mAP50-95: {metrics.box.map:.4f}")
    print()
    for i, name in enumerate(best_model.names.values()):
        if i < len(metrics.box.ap50):
            print(f"  AP50 [{name:>10}]: {metrics.box.ap50[i]:.4f}")

    print()
    print(f"Для подключения к проекту:")
    print(f"  copy {best_path} ..\\backend\\models\\objects_v1.pt")
    print(f"  (или cp {best_path} ../backend/models/objects_v1.pt)")


if __name__ == "__main__":
    main()