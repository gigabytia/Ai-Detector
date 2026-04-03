"""
Отрисовка русского (Unicode) текста на кадрах OpenCV.
cv2.putText() не поддерживает кириллицу — используем Pillow.
"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import platform


def _find_system_font() -> str:
    """
    Ищет системный шрифт с поддержкой кириллицы.
    Возвращает путь к .ttf файлу.
    """
    system = platform.system()

    # Список шрифтов для проверки (в порядке приоритета)
    font_candidates = []

    if system == "Windows":
        fonts_dir = r"C:\Windows\Fonts"
        font_candidates = [
            os.path.join(fonts_dir, "arial.ttf"),
            os.path.join(fonts_dir, "calibri.ttf"),
            os.path.join(fonts_dir, "tahoma.ttf"),
            os.path.join(fonts_dir, "segoeui.ttf"),
            os.path.join(fonts_dir, "times.ttf"),
            os.path.join(fonts_dir, "cour.ttf"),
        ]

    elif system == "Darwin":  # macOS
        font_candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/SFNSText.ttf",
        ]

    elif system == "Linux":
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        ]

    # Проверяем каждый кандидат
    for font_path in font_candidates:
        if os.path.exists(font_path):
            return font_path

    # Если ничего не нашли — пробуем через Pillow
    return None


# Глобальный кеш шрифтов (чтобы не загружать каждый кадр)
_font_cache = {}


def get_font(size: int = 20) -> ImageFont.FreeTypeFont:
    """Получает шрифт нужного размера (с кешированием)."""
    if size in _font_cache:
        return _font_cache[size]

    font_path = _find_system_font()

    if font_path:
        try:
            font = ImageFont.truetype(font_path, size)
        except Exception:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    _font_cache[size] = font
    return font


def put_russian_text(
    frame: np.ndarray,
    text: str,
    position: tuple,
    font_size: int = 20,
    color: tuple = (255, 255, 255),
    bg_color: tuple = None,
    padding: int = 5,
) -> np.ndarray:
    """
    Рисует текст (включая кириллицу) на кадре OpenCV.

    Args:
        frame:     кадр BGR (numpy array)
        text:      текст для отрисовки (любой Unicode)
        position:  (x, y) — левый верхний угол текста
        font_size: размер шрифта в пикселях
        color:     цвет текста в BGR (OpenCV формат)
        bg_color:  цвет фона в BGR (None = без фона)
        padding:   отступ фона от текста

    Returns:
        Кадр с нарисованным текстом
    """
    # Конвертируем BGR → RGB для Pillow
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(frame_rgb)
    draw = ImageDraw.Draw(pil_image)

    # Получаем шрифт
    font = get_font(font_size)

    # Цвет: BGR → RGB
    color_rgb = (color[2], color[1], color[0])

    x, y = position

    # Рисуем фон, если нужен
    if bg_color is not None:
        bg_rgb = (bg_color[2], bg_color[1], bg_color[0])

        # Получаем размер текста
        bbox = draw.textbbox((x, y), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        draw.rectangle(
            [x - padding, y - padding,
             x + text_w + padding, y + text_h + padding],
            fill=bg_rgb,
        )

    # Рисуем текст
    draw.text((x, y), text, font=font, fill=color_rgb)

    # Конвертируем обратно RGB → BGR
    result = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    # Копируем результат обратно в исходный массив
    np.copyto(frame, result)

    return frame


def get_text_size(text: str, font_size: int = 20) -> tuple:
    """
    Возвращает размер текста (width, height) в пикселях.
    Полезно для позиционирования.
    """
    font = get_font(font_size)
    # Создаём временное изображение для измерения
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]