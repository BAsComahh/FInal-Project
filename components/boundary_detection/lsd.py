"""Raw LSD detection, without post-processing."""

import cv2
import numpy as np


def detect_lsd_lines(image, blur_size=5, refine="std"):
    """Return all LSD segments as an (N, 4) array, without post-filtering."""
    if blur_size < 1 or blur_size % 2 == 0:
        raise ValueError("blur-size must be a positive odd number")
    modes = {"none": cv2.LSD_REFINE_NONE, "std": cv2.LSD_REFINE_STD, "adv": cv2.LSD_REFINE_ADV}
    if refine not in modes:
        raise ValueError("refine must be none, std or adv")
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = gray if blur_size == 1 else cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
    detected, _, _, _ = cv2.createLineSegmentDetector(modes[refine]).detect(blurred)
    return np.empty((0, 4), dtype=np.float32) if detected is None else detected.reshape(-1, 4)
