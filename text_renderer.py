"""
Быстрый рендер Unicode/русского текста для OpenCV.

Приоритет:
1) cv2.freetype (opencv-contrib-python) — быстро
2) Pillow fallback — рисуем только ROI (не весь кадр)
"""
import os
import platform
import cv2
import numpy as np
from typing import Optional, Tuple

TEXT_BACKEND_NAME = "unknown"


def _find_system_font() -> Optional[str]:
    system = platform.system()
    candidates = []

    if system == "Windows":
        fonts_dir = r"C:\Windows\Fonts"
        candidates = [
            os.path.join(fonts_dir, "arial.ttf"),
            os.path.join(fonts_dir, "calibri.ttf"),
            os.path.join(fonts_dir, "tahoma.ttf"),
            os.path.join(fonts_dir, "segoeui.ttf"),
        ]
    elif system == "Darwin":
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        ]

    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# --- FreeType backend ---
_FT = None
_FT_FONT_PATH = _find_system_font()

if hasattr(cv2, "freetype") and _FT_FONT_PATH:
    try:
        _FT = cv2.freetype.createFreeType2()
        _FT.loadFontData(fontFileName=_FT_FONT_PATH, id=0)
        TEXT_BACKEND_NAME = f"cv2.freetype ({os.path.basename(_FT_FONT_PATH)})"
    except Exception:
        _FT = None

# --- Pillow fallback ---
if _FT is None:
    try:
        from PIL import Image, ImageDraw, ImageFont
        TEXT_BACKEND_NAME = "pillow_roi"
    except Exception:
        Image = ImageDraw = ImageFont = None
        TEXT_BACKEND_NAME = "none"

_font_cache = {}


def _get_pil_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    if ImageFont is None:
        return None

    font_path = _find_system_font()
    if font_path:
        try:
            f = ImageFont.truetype(font_path, size)
        except Exception:
            f = ImageFont.load_default()
    else:
        f = ImageFont.load_default()

    _font_cache[size] = f
    return f


def get_text_size(text: str, font_size: int = 20, thickness: int = 1) -> Tuple[int, int]:
    if _FT is not None:
        (w, h), _ = _FT.getTextSize(text, fontHeight=font_size, thickness=thickness)
        return int(w), int(h)

    if ImageFont is not None:
        font = _get_pil_font(font_size)
        dummy = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.textbbox((0, 0), text, font=font)
        return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])

    return int(len(text) * font_size * 0.6), int(font_size)


def put_russian_text(
    frame: np.ndarray,
    text: str,
    position: tuple,
    font_size: int = 20,
    color: tuple = (255, 255, 255),
    bg_color: Optional[tuple] = None,
    padding: int = 4,
) -> np.ndarray:
    x, y = int(position[0]), int(position[1])

    # FreeType (быстро)
    if _FT is not None:
        if bg_color is not None:
            w, h = get_text_size(text, font_size)
            x1 = max(0, x - padding)
            y1 = max(0, y - padding)
            x2 = min(frame.shape[1] - 1, x + w + padding)
            y2 = min(frame.shape[0] - 1, y + h + padding)
            cv2.rectangle(frame, (x1, y1), (x2, y2), bg_color, -1)

        _FT.putText(
            frame, text, (x, y + font_size),
            fontHeight=font_size,
            color=color,
            thickness=1,
            line_type=cv2.LINE_AA,
            bottomLeftOrigin=False,
        )
        return frame

    # Pillow fallback (ROI)
    if ImageFont is None:
        cv2.putText(frame, text, (x, y + font_size), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
        return frame

    w, h = get_text_size(text, font_size)
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(frame.shape[1], x + w + padding)
    y2 = min(frame.shape[0], y + h + padding)

    if x1 >= x2 or y1 >= y2:
        return frame

    roi = frame[y1:y2, x1:x2]
    roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(roi_rgb)
    draw = ImageDraw.Draw(pil_img)
    font = _get_pil_font(font_size)

    if bg_color is not None:
        bg_rgb = (bg_color[2], bg_color[1], bg_color[0])
        draw.rectangle([0, 0, pil_img.size[0], pil_img.size[1]], fill=bg_rgb)

    color_rgb = (color[2], color[1], color[0])
    draw.text((x - x1, y - y1), text, font=font, fill=color_rgb)

    roi_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    frame[y1:y2, x1:x2] = roi_bgr
    return frame