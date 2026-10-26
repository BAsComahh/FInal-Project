"""Run the official ncnn Vulkan executable without changing Torch packages."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = PROJECT_ROOT / "vendor" / "real_esrgan"
MODEL = "realesrgan-x4plus"
SCALE = 4


def _read_image(image):
    if isinstance(image, (str, Path)):
        path = Path(image)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")
        data = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.size == 0
            or image.ndim not in (2, 3) or (image.ndim == 3 and image.shape[2] not in (3, 4))):
        raise ValueError("image must be a decodable path or non-empty uint8 grayscale, BGR or BGRA array")
    return image


def upscale_image(image, *, runtime_dir=DEFAULT_RUNTIME, gpu_id=0, tile_size=128):
    """Return a 4x enhanced image and run metadata; save no permanent files.

    Input/output arrays follow OpenCV channel order. Alpha is enlarged with
    nearest-neighbor interpolation, preserving an existing binary mask.
    gpu_id is a Vulkan index, independent of the PyTorch device numbering.
    No SAM, DINO, tray detection or physical-size matching is performed here.
    """
    image = _read_image(image)
    if isinstance(gpu_id, bool) or not isinstance(gpu_id, int) or gpu_id < 0:
        raise ValueError("gpu_id must be a non-negative Vulkan device index")
    if isinstance(tile_size, bool) or not isinstance(tile_size, int) or tile_size < 32:
        raise ValueError("tile_size must be an integer of at least 32 pixels")
    runtime = Path(runtime_dir).resolve()
    executable = runtime / "realesrgan-ncnn-vulkan.exe"
    required = [executable, runtime / "models" / f"{MODEL}.param", runtime / "models" / f"{MODEL}.bin"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Real-ESRGAN runtime is incomplete: " + ", ".join(missing)
            + ". See components/real_esrgan/README.md for setup, or pass runtime_dir."
        )
    height, width = image.shape[:2]
    color = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image[:, :, :3]
    with TemporaryDirectory(prefix="board_game_realesrgan_") as temporary:
        folder = Path(temporary)
        input_path, output_path = folder / "input.png", folder / "output.png"
        success, encoded = cv2.imencode(".png", color)
        if not success:
            raise ValueError("Cannot encode input image")
        encoded.tofile(input_path)
        command = [str(executable), "-i", str(input_path), "-o", str(output_path),
                   "-m", str(runtime / "models"), "-n", MODEL, "-s", str(SCALE),
                   "-t", str(tile_size), "-g", str(gpu_id), "-j", "1:1:1"]
        started = perf_counter()
        process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elapsed = perf_counter() - started
        log = process.stdout + process.stderr
        if process.returncode != 0 or not output_path.is_file():
            raise RuntimeError(f"Real-ESRGAN failed (exit {process.returncode}):\n{log[-4000:]}")
        enhanced = _read_image(output_path)
    if enhanced.shape != (height * SCALE, width * SCALE, 3):
        raise RuntimeError(f"Unexpected Real-ESRGAN output shape: {enhanced.shape}")
    if image.ndim == 2:
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    elif image.shape[2] == 4:
        alpha = cv2.resize(image[:, :, 3], (width * SCALE, height * SCALE), interpolation=cv2.INTER_NEAREST)
        enhanced = np.dstack([enhanced, alpha])
    return {"image": enhanced, "scale": SCALE, "input_size": (width, height),
            "output_size": (width * SCALE, height * SCALE), "model": MODEL,
            "backend": "ncnn-vulkan", "gpu_id": gpu_id, "tile_size": tile_size,
            "elapsed_seconds": elapsed, "runtime_dir": str(runtime), "log": log}
