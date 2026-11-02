"""Shared text and loading-progress drawing."""

from functools import lru_cache
from time import perf_counter

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=8)
def _font(size):
    return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)


def draw_text(image, text, position, color=(230, 230, 230), size=15):
    text = str(text)
    if text.isascii():
        cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, size / 30, color, 1, cv2.LINE_AA)
    else:
        # Keep channel order unchanged: fill is already BGR/BGRA like the canvas.
        canvas = Image.fromarray(image)
        ImageDraw.Draw(canvas).text(position, text, font=_font(size), fill=color, anchor="ls")
        image[:] = np.asarray(canvas)


def draw_loading_progress(canvas, progress):
    stage, completed, total = progress
    height, width = canvas.shape[:2]
    left, right = 16, width - 16
    top, bottom = max(0, height - 76), height - 12
    cv2.rectangle(canvas, (left - 6, top), (right + 6, bottom), (25, 25, 25), -1)
    bar_top, bar_bottom = bottom - 18, bottom - 7
    cv2.rectangle(canvas, (left, bar_top), (right, bar_bottom), (65, 65, 65), -1)
    if total is not None and total > 0 and completed is not None:
        ratio = min(1.0, max(0.0, completed / total))
        label = f"{stage}: {ratio:.0%} ({completed}/{total})"
        end = left + round((right - left) * ratio)
        if end > left:
            cv2.rectangle(canvas, (left, bar_top), (end, bar_bottom), (210, 160, 80), -1)
    else:
        label = stage + "..."
        span = max(1, (right - left) // 4)
        start = left + int((perf_counter() % 1.5) / 1.5 * (right - left - span))
        cv2.rectangle(canvas, (start, bar_top), (start + span, bar_bottom), (210, 160, 80), -1)
    draw_text(canvas, label, (left + 2, top + 22), size=14)
