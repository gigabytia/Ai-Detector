#!/usr/bin/env python3
"""
Главный файл проекта — трекинг людей с определением поз.

Примеры:
    python main.py
    python main.py --source video.mp4
    python main.py --source image.jpg --mode image
    python main.py --source video.mp4 --save output.mp4
"""
import argparse
import cv2

from config import PoseConfig
from tracker import PoseTracker


def run_tracking(args):
    """Запуск трекинга (камера или видео)."""
    config = PoseConfig()

    if args.model:
        config.MODEL_NAME = args.model
    if args.confidence:
        config.DETECTION_CONFIDENCE = args.confidence

    tracker = PoseTracker(config)

    source = args.source
    if source is None or source == "0":
        source = 0
    elif isinstance(source, str) and source.isdigit():
        source = int(source)

    save_path = args.save if args.save else None

    tracker.process_video(
        source=source,
        show=not args.no_display,
        save_path=save_path,
        generate_report=not args.no_report,
        open_report=not args.no_open_report,
    )


def run_image(args):
    """Обработка одного изображения."""
    config = PoseConfig()

    if args.model:
        config.MODEL_NAME = args.model

    tracker = PoseTracker(config)

    _, detections = tracker.process_image(
        image_path=args.source,
        save_path=args.save,
        show=not args.no_display,
    )

    print(f"\nОбнаружено {len(detections)} человек:")
    pose_ru = {
        "standing": "Стоит",
        "sitting": "Сидит",
        "hand_raised": "Рука поднята",
        "unknown": "Неизвестно",
    }

    for d in detections:
        print(f"  ID {d['track_id']}: {pose_ru.get(d['pose'], d['pose'])}")


def run_demo(args):
    """Демонстрационный режим с выводом информации."""
    config = PoseConfig()
    tracker = PoseTracker(config)

    source = 0 if args.source is None else args.source
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print("Не удалось открыть источник!")
        return

    print("=" * 60)
    print("  ДЕМО: Трекинг людей с определением поз")
    print("=" * 60)
    print("  Позы: Стоит | Сидит | Рука поднята")
    print("  Клавиши: q=выход, s=скриншот, p=пауза")
    print("=" * 60)

    paused = False
    annotated = None

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break

            annotated, detections = tracker.process_frame(frame)

            h, w = annotated.shape[:2]
            help_text = "q=выход | s=скриншот | p=пауза"
            cv2.putText(
                annotated,
                help_text,
                (max(10, w - 400), h - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1,
            )

            cv2.imshow("Pose Tracker Demo", annotated)

        key = cv2.waitKey(1 if not paused else 100) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('p'):
            paused = not paused
            print(f"  {'⏸ Пауза' if paused else '▶ Продолжение'}")
        elif key == ord('s') and annotated is not None:
            screenshot = f"demo_screenshot_{tracker.frame_count}.jpg"
            cv2.imwrite(screenshot, annotated)
            print(f"  Скриншот: {screenshot}")

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="Трекинг людей с определением поз (YOLOv8)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py
  python main.py --source video.mp4
  python main.py --source 0
  python main.py --source photo.jpg --mode image
  python main.py --save output.mp4
  python main.py --mode demo
        """,
    )

    parser.add_argument(
        "--mode",
        type=str,
        default="track",
        choices=["track", "image", "demo"],
        help="Режим работы",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Источник (камера ID, путь к видео/изображению)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Модель YOLOv8-pose",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="Порог уверенности детекции (0.0-1.0)",
    )
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="Путь для сохранения результата",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Не показывать окно",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Не генерировать итоговый отчёт",
    )
    parser.add_argument(
        "--no-open-report",
        action="store_true",
        help="Не открывать отчёт автоматически",
    )

    args = parser.parse_args()

    mode_handlers = {
        "track": run_tracking,
        "image": run_image,
        "demo": run_demo,
    }

    handler = mode_handlers.get(args.mode)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()