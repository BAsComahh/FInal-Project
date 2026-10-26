"""Enhance an image with Real-ESRGAN for optional tray-edge analysis."""

import argparse
import json
from pathlib import Path
import sys

import cv2

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.real_esrgan import DEFAULT_RUNTIME, upscale_image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
__all__ = ["upscale_image", "main"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--gpu", type=int, default=0, help="Vulkan GPU index; RX 7900 XT is 0 on this machine")
    parser.add_argument("--tile", type=int, default=128, help="Tile size in input pixels (at least 32)")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "real_esrgan")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        result = upscale_image(args.image, runtime_dir=args.runtime_dir, gpu_id=args.gpu, tile_size=args.tile)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        image_path = args.output_dir / f"{args.image.stem}_x4.png"
        success, encoded = cv2.imencode(".png", result["image"])
        if not success:
            raise ValueError(f"Cannot encode output image: {image_path}")
        encoded.tofile(image_path)
        log_path = args.output_dir / f"{args.image.stem}_x4.log"
        log_path.write_text(result["log"], encoding="utf-8")
        metadata = {key: value for key, value in result.items() if key not in ("image", "log")}
        metadata.update(source=str(args.image.resolve()), output=str(image_path.resolve()))
        report_path = args.output_dir / f"{args.image.stem}_x4.json"
        report_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{result['input_size']} -> {result['output_size']} | {result['elapsed_seconds']:.2f}s")
        print(f"Saved: {image_path.resolve()}")
        print(f"Saved: {report_path.resolve()}")
        return 0
    except (OSError, ValueError, RuntimeError, cv2.error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
