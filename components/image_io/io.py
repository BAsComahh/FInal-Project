"""Unicode-safe uint8 image I/O in OpenCV channel order."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np


def load_image(image, *, mode="color"):
    """Read a path or normalize an array: color (BGR), gray or unchanged.

    unchanged preserves grayscale/BGR/BGRA channels. Arrays are returned
    without copying when conversion is unnecessary; uint8 is required.
    """
    flags = {"color": cv2.IMREAD_COLOR, "gray": cv2.IMREAD_GRAYSCALE,
             "unchanged": cv2.IMREAD_UNCHANGED}
    if mode not in flags:
        raise ValueError("mode must be color, gray or unchanged")
    if isinstance(image, (str, Path)):
        path = Path(image)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")
        data = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(data, flags[mode]) if data.size else None
        if image is None:
            raise ValueError(f"Cannot decode image: {path}")
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8 or not image.size
            or image.ndim not in (2, 3) or (image.ndim == 3 and image.shape[2] not in (3, 4))):
        raise ValueError("image must be a non-empty uint8 grayscale, BGR or BGRA image, or a decodable path")
    if mode == "color":
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    elif mode == "gray" and image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
    return image


def save_image(path, image):
    """Encode using the filename extension, creating the parent directory."""
    path = Path(path)
    try:
        success, encoded = cv2.imencode(path.suffix or ".png", image)
    except cv2.error as error:
        raise ValueError(f"Cannot encode output image: {path}") from error
    if not success:
        raise ValueError(f"Cannot encode output image: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
