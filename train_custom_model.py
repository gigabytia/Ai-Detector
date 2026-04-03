"""
Обучение кастомных моделей для определения поз.

Два подхода:
1. Обучение ML-классификатора (RandomForest/GradientBoosting) на фичах из ключевых точек
2. Fine-tuning YOLOv8-pose на собственном датасете
"""
import os
import sys
import numpy as np
from typing import Optional

from config import PoseConfig, TrainingConfig
from pose_ml_classifier import (
    PoseMLClassifier,
    generate_synthetic_training_data,
)
from dataset_creator import PoseDatasetCreator


def train_ml_classifier(
        dataset_path: Optional[str] = None,
        model_save_path: str = "pose_ml_model.pkl",
        model_type: str = "random_forest",
):
    """
    Обучает ML-классификатор поз.

    Args:
        dataset_path:   путь к JSON-файлу с данными (или None для синтетики)
        model_save_path: куда сохранить обученную модель
        model_type:     "random_forest" или "gradient_boosting"
    """
    print("=" * 60)
    print("  Обучение ML-классификатора поз")
    print("=" * 60)

    classifier = PoseMLClassifier(model_type=model_type)

    if dataset_path and os.path.exists(dataset_path):
        # Загрузка реальных данных
        print(f"[INFO] Загрузка данных из: {dataset_path}")
        creator = PoseDatasetCreator()
        creator.load_dataset(dataset_path)
        kps_list, conf_list, labels = creator.get_training_data()
    else:
        # Генерация синтетических данных для демонстрации
        print("[INFO] Реальный датасет не найден. Генерация синтетических данных...")
        kps_list, conf_list, labels = generate_synthetic_training_data(500)

    # Обучение
    metrics = classifier.train(kps_list, conf_list, labels)

    # Сохранение
    classifier.save(model_save_path)

    print(f"\n[RESULT] Точность: {metrics['accuracy']:.4f}")
    print(f"[RESULT] Кросс-валидация: {metrics['cv_mean']:.4f} ± {metrics['cv_std']:.4f}")
    print(f"[RESULT] Модель сохранена: {model_save_path}")

    return classifier


def finetune_yolov8_pose(
        data_yaml: str,
        training_config: TrainingConfig = None,
):
    """
    Fine-tuning YOLOv8-pose на собственном датасете.

    Требуется подготовленный датасет в формате YOLO-pose:
    - images/train/
    - images/val/
    - labels/train/  (формат: class x_center y_center width height kp1_x kp1_y kp1_v ...)
    - data.yaml

    Args:
        data_yaml:        путь к data.yaml
        training_config:  конфигурация обучения
    """
    from ultralytics import YOLO

    config = training_config or TrainingConfig()

    print("=" * 60)
    print("  Fine-tuning YOLOv8-pose")
    print("=" * 60)

    # Загрузка предобученной модели
    model = YOLO(config.PRETRAINED_MODEL)

    # Обучение
    results = model.train(
        data=data_yaml,
        epochs=config.EPOCHS,
        batch=config.BATCH_SIZE,
        imgsz=config.IMAGE_SIZE,
        lr0=config.LEARNING_RATE,
        patience=config.PATIENCE,
        device=config.DEVICE,
        augment=config.AUGMENT,
        project=config.PROJECT_NAME,
        name=config.EXPERIMENT_NAME,
        verbose=True,
        save=True,
        plots=True,
    )

    print(f"\n[RESULT] Обучение завершено!")
    print(f"[RESULT] Лучшая модель: {config.PROJECT_NAME}/{config.EXPERIMENT_NAME}/weights/best.pt")

    return results


def create_yolo_pose_yaml(
        dataset_path: str,
        output_path: str = "pose_data.yaml",
        class_names: list = None,
):
    """
    Создаёт data.yaml для обучения YOLOv8-pose.

    Args:
        dataset_path: корневая папка датасета
        output_path:  путь для сохранения yaml
        class_names:  имена классов
    """
    if class_names is None:
        class_names = ["person"]

    yaml_content = f"""# Конфигурация датасета для YOLOv8-pose
path: {os.path.abspath(dataset_path)}
train: images/train
val: images/val

# Ключевые точки
kpt_shape: [17, 3]  # 17 точек, 3 значения (x, y, visibility)

# Классы
names:
"""
    for i, name in enumerate(class_names):
        yaml_content += f"  {i}: {name}\n"

    # Описание ключевых точек
    yaml_content += """
# Описание ключевых точек (COCO format):
# 0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear,
# 5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow,
# 9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip,
# 13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle

# flip_idx для аугментации (зеркальное отражение)
flip_idx: [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]
"""

    with open(output_path, 'w') as f:
        f.write(yaml_content)

    print(f"[INFO] Создан файл конфигурации: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Обучение модели определения поз")
    parser.add_argument(
        "--mode", type=str, default="ml",
        choices=["ml", "finetune", "synthetic"],
        help="Режим: ml (ML-классификатор), finetune (fine-tuning YOLO), synthetic (синтетика)"
    )
    parser.add_argument("--dataset", type=str, default=None, help="Путь к датасету")
    parser.add_argument("--model-type", type=str, default="random_forest",
                        choices=["random_forest", "gradient_boosting"])
    parser.add_argument("--output", type=str, default="pose_ml_model.pkl")

    args = parser.parse_args()

    if args.mode == "ml":
        train_ml_classifier(args.dataset, args.output, args.model_type)
    elif args.mode == "synthetic":
        train_ml_classifier(None, args.output, args.model_type)
    elif args.mode == "finetune":
        if not args.dataset:
            print("Для fine-tuning необходимо указать --dataset (data.yaml)")
            sys.exit(1)
        finetune_yolov8_pose(args.dataset)