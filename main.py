#!/usr/bin/env python3
"""
Главный файл проекта — трекинг людей с определением поз.

Использование:
    # Камера (по умолчанию):
    python main.py

    # Видеофайл:
    python main.py --source video.mp4

    # Изображение:
    python main.py --source image.jpg --mode image

    # С сохранением результата:
    python main.py --source video.mp4 --save output.mp4

    # С ML-классификатором:
    python main.py --classifier ml --ml-model pose_ml_model.pkl

    # Сбор данных:
    python main.py --mode collect

    # Обучение ML-модели:
    python main.py --mode train --dataset datasets/pose_data/data.json
"""
import argparse
import sys
import os
import cv2
import numpy as np

from config import PoseConfig
from tracker import PoseTracker
from pose_classifier import PoseClassifier
from pose_ml_classifier import PoseMLClassifier
from dataset_creator import PoseDatasetCreator


def run_tracking(args):
    """Запуск трекинга (камера или видео)."""
    config = PoseConfig()

    # Настройка модели
    if args.model:
        config.MODEL_NAME = args.model
    if args.confidence:
        config.DETECTION_CONFIDENCE = args.confidence

    # Создание трекера
    tracker = PoseTracker(config)

    # Определение источника
    source = args.source
    if source is None or source == "0":
        source = 0  # Камера
    elif source.isdigit():
        source = int(source)

    # Запуск
    save_path = args.save if args.save else None
    tracker.process_video(
        source=source,
        show=not args.no_display,
        save_path=save_path,
    )


def run_image(args):
    """Обработка одного изображения."""
    config = PoseConfig()
    if args.model:
        config.MODEL_NAME = args.model

    tracker = PoseTracker(config)

    annotated, detections = tracker.process_image(
        image_path=args.source,
        save_path=args.save,
        show=not args.no_display,
    )

    # Вывод результатов
    print(f"\nОбнаружено {len(detections)} человек:")
    for d in detections:
        pose_ru = {
            "standing": "Стоит",
            "sitting": "Сидит",
            "hand_raised": "Рука поднята",
            "unknown": "Неизвестно",
        }
        print(f"  ID {d['track_id']}: {pose_ru.get(d['pose'], d['pose'])}")


def run_data_collection(args):
    """Запуск сборщика данных."""
    creator = PoseDatasetCreator(
        output_dir=args.dataset or "datasets/pose_data",
    )
    source = int(args.source) if args.source and args.source.isdigit() else 0
    creator.collect_from_camera(source)


def run_training(args):
    """Запуск обучения ML-модели."""
    from train_custom_model import train_ml_classifier

    train_ml_classifier(
        dataset_path=args.dataset,
        model_save_path=args.save or "pose_ml_model.pkl",
        model_type=args.model_type or "random_forest",
    )


def run_demo(args):
    """Демонстрационный режим с выводом информации."""
    config = PoseConfig()
    tracker = PoseTracker(config)

    source = 0  # Камера

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print("Не удалось открыть камеру!")
        return

    print("=" * 60)
    print("  ДЕМО: Трекинг людей с определением поз")
    print("=" * 60)
    print("  Позы: Стоит | Сидит | Рука поднята")
    print("  Клавиши: q=выход, s=скриншот, p=пауза")
    print("=" * 60)

    paused = False

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break

            annotated, detections = tracker.process_frame(frame)

            # Добавляем подсказки на экран
            h, w = annotated.shape[:2]
            help_text = "q=выход | s=скриншот | p=пауза"
            cv2.putText(
                annotated, help_text,
                (w - 400, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1,
            )

            cv2.imshow("Pose Tracker Demo", annotated)

        key = cv2.waitKey(1 if not paused else 100) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('p'):
            paused = not paused
            print(f"  {'⏸ Пауза' if paused else '▶ Продолжение'}")
        elif key == ord('s'):
            screenshot = f"demo_screenshot_{tracker.frame_count}.jpg"
            cv2.imwrite(screenshot, annotated)
            print(f"     Скриншот: {screenshot}")

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="Трекинг людей с определением поз (YOLOv8)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                              # Камера (демо)
  python main.py --source video.mp4           # Видеофайл
  python main.py --source 0                   # Камера #0
  python main.py --source photo.jpg --mode image  # Изображение
  python main.py --mode collect               # Сбор данных
  python main.py --mode train --dataset data.json  # Обучение
  python main.py --save output.mp4            # С сохранением
        """,
    )

    parser.add_argument(
        "--mode", type=str, default="track",
        choices=["track", "image", "collect", "train", "demo"],
        help="Режим работы",
    )
    parser.add_argument(
        "--source", type=str, default=None,
        help="Источник (камера ID, путь к видео/изображению)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Модель YOLOv8-pose (по умолчанию yolov8n-pose.pt)",
    )
    parser.add_argument(
        "--confidence", type=float, default=None,
        help="Порог уверенности детекции (0.0-1.0)",
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Путь для сохранения результата",
    )
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="Путь к датасету (для train/collect)",
    )
    parser.add_argument(
        "--model-type", type=str, default="random_forest",
        choices=["random_forest", "gradient_boosting"],
        help="Тип ML-модели для обучения",
    )
    parser.add_argument(
        "--no-display", action="store_true",
        help="Не показывать окно (для серверов)",
    )

    args = parser.parse_args()

    # Маршрутизация по режимам
    mode_handlers = {
        "track": run_tracking,
        "image": run_image,
        "collect": run_data_collection,
        "train": run_training,
        "demo": run_demo,
    }

    handler = mode_handlers.get(args.mode)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()