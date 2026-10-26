"""Image rectification using a four-corner homography."""

from pathlib import Path

import cv2
import numpy as np

from .geometry import compute_homography


def _load_image(path):
    """Read a BGR image, including non-ASCII Windows paths."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        raise ValueError(f"Cannot decode image: {path}")
    return image


def warp_table(image, corners, output_size=None, *, board_size=None):
    """Return a rectified image and the reusable calibration matrices.

    image is a path or an OpenCV uint8 BGR, BGRA, or grayscale array. No files
    are saved by this function. The result's image key holds the warped array.
    """
    if isinstance(image, (str, Path)):
        image = _load_image(image)
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.size == 0
            or image.ndim not in (2, 3) or (image.ndim == 3 and image.shape[2] not in (3, 4))):
        raise ValueError("image must be a non-empty uint8 BGR, BGRA or grayscale image, or a path")
    calibration = compute_homography(corners, output_size, board_size=board_size)
    warped = cv2.warpPerspective(image, calibration["matrix"], calibration["output_size"])
    return {**calibration, "image": warped}
