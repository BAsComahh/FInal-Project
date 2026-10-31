"""Image rectification using a four-corner homography."""

from pathlib import Path

import cv2
from components.image_io import load_image as _load_image
from .geometry import compute_homography


def warp_table(image, corners, output_size=None, *, board_size=None):
    """Return a rectified image and the reusable calibration matrices.

    image is a path or an OpenCV uint8 BGR, BGRA, or grayscale array. No files
    are saved by this function. The result's image key holds the warped array.
    """
    image = _load_image(image, mode="color" if isinstance(image, (str, Path)) else "unchanged")
    calibration = compute_homography(corners, output_size, board_size=board_size)
    warped = cv2.warpPerspective(image, calibration["matrix"], calibration["output_size"])
    return {**calibration, "image": warped}
