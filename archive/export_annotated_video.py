import os
import argparse
import cv2
import numpy as np
import torch
from ultralytics import YOLO

# Импортируем готовые функции отрисовки/классификации из app.py
# Важно: в app.py должен быть блок if __name__ == "__main__": main()
# тогда импорт не запустит приложение.
from app import (
    select_device, print_gpu_info,
    classify_pose, smooth_pose,
    draw_skeleton, draw_bbox_and_label, draw_info_panel,
    SHOW_SKELETON, CONFIDENCE, INFERENCE_SIZE, USE_HALF_PRECISION
)

POSE_NAMES_RU = {
    "standing": "Стоит", "sitting": "Сидит",
    "hand_raised": "Рука поднята", "unknown": "???",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Путь к входному видео")
    parser.add_argument("--output", default=None, help="Путь к выходному видео .mp4")
    parser.add_argument("--model", default="yolov8n-pose.pt", help="Модель YOLOv8 pose")
    parser.add_argument("--device", default="auto", help="auto/cuda:0/cpu/mps")
    parser.add_argument("--conf", type=float, default=CONFIDENCE, help="confidence threshold")
    parser.add_argument("--imgsz", type=int, default=INFERENCE_SIZE, help="размер инференса")
    parser.add_argument("--half", action="store_true", help="включить half precision (только CUDA)")
    parser.add_argument("--show", action="store_true", help="показывать окно (не обязательно)")
    args = parser.parse_args()

    src = args.source
    if args.output is None:
        base = os.path.splitext(os.path.basename(src))[0]
        args.output = f"{base}_annotated.mp4"

    device = select_device(args.device)
    print_gpu_info()

    print(f"[INFO] Loading model: {args.model}")
    model = YOLO(args.model)
    model.to(device)

    # half precision
    use_half = False
    if args.half or USE_HALF_PRECISION:
        if device.startswith("cuda"):
            capab = torch.cuda.get_device_capability(0)
            if capab[0] >= 7:
                use_half = True
                print("[INFO] FP16 enabled")
            else:
                print("[WARN] FP16 not supported on this GPU")
        else:
            print("[WARN] FP16 works only on CUDA устройствe")

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {src}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and fps > 0 else 25.0

    # writer
    # mp4v обычно работает везде; если не откроется — попробуй 'avc1'
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(args.output, fourcc, fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError("VideoWriter не открылся. Попробуй другой fourcc (например avc1) или проверь ffmpeg/OpenCV сборку.")

    print(f"[INFO] Input:  {w}x{h} @ {fps:.2f} FPS")
    print(f"[INFO] Output: {args.output}")

    fps_times = []
    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[INFO] End of video")
                break

            frame_count += 1

            # FPS оценки (для панели)
            import time
            fps_times.append(time.time())
            if len(fps_times) > 30:
                fps_times.pop(0)
            fps_now = ((len(fps_times) - 1) / (fps_times[-1] - fps_times[0])
                       if len(fps_times) >= 2 else 0.0)

            results = model.track(
                frame,
                persist=True,
                conf=args.conf,
                verbose=False,
                device=device,
                imgsz=args.imgsz,
                half=use_half,
            )

            result = results[0]
            pose_counts = {}
            total_people = 0

            if (result.boxes is not None and len(result.boxes) > 0 and result.keypoints is not None):
                boxes = result.boxes.xyxy.cpu().numpy()
                kp_data = result.keypoints.data.cpu().numpy()

                if result.boxes.id is not None:
                    track_ids = result.boxes.id.cpu().numpy().astype(int).tolist()
                else:
                    track_ids = list(range(len(boxes)))

                total_people = len(boxes)

                for i in range(len(boxes)):
                    bbox = boxes[i]
                    kps = kp_data[i, :, :2]
                    confs = kp_data[i, :, 2]
                    tid = track_ids[i]

                    pose = classify_pose(kps, confs)
                    pose = smooth_pose(tid, pose)
                    pose_counts[pose] = pose_counts.get(pose, 0) + 1

                    if SHOW_SKELETON:
                        draw_skeleton(frame, kps, confs)
                    draw_bbox_and_label(frame, bbox, tid, pose)

            device_display = device
            if device.startswith("cuda"):
                device_display = f"GPU: {torch.cuda.get_device_name(0)}"
            elif device == "mps":
                device_display = "Apple GPU (MPS)"
            else:
                device_display = "CPU"

            draw_info_panel(frame, pose_counts, total_people, fps_now, device_display)

            writer.write(frame)

            if args.show:
                cv2.imshow("Export annotated", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("[INFO] Stopped by user")
                    break

            if frame_count % 50 == 0:
                print(f"[INFO] frame={frame_count}")

    finally:
        cap.release()
        writer.release()
        if args.show:
            cv2.destroyAllWindows()

    print(f"[INFO] Done. Frames written: {frame_count}")
    print(f"[INFO] Saved: {args.output}")


if __name__ == "__main__":
    main()