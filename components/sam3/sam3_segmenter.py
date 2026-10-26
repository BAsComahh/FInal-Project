"""Segment an image with SAM3; the default text prompt is miniature."""

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from components.sam3 import Sam3Segmenter
from components.sam3.visualization import draw_segmentation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
__all__ = ["Sam3Segmenter", "segment_image", "main"]


def segment_image(image, prompt="miniature", *, threshold=0.5, segmenter=None):
    """Segment one image. Pass a shared Sam3Segmenter to reuse loaded weights."""
    if segmenter is None:
        segmenter = Sam3Segmenter()
    return segmenter.segment(image, prompt, threshold=threshold)


def _save_png(path, image):
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError(f"Cannot encode output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--prompt", default="miniature")
    parser.add_argument("--threshold", type=float, default=0.5, help="Instance score threshold (0 to 1)")
    parser.add_argument("--device", help="Torch device; by default choose the GPU with the most memory")
    parser.add_argument("--model", default="facebook/sam3", help="Cached model ID or local model directory")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "sam3")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        segmenter = Sam3Segmenter(model_id=args.model, device=args.device)
        result = segment_image(args.image, args.prompt, threshold=args.threshold, segmenter=segmenter)
        # Each run owns its folder, so old masks cannot be mistaken for new detections.
        from tempfile import mkdtemp
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output = Path(mkdtemp(prefix=f"{args.image.stem}_", dir=args.output_dir))
        _save_png(output / "overlay.png", draw_segmentation(result))
        instances = []
        for index, (mask, box, score) in enumerate(zip(result["masks"], result["boxes"], result["scores"])):
            mask_path = f"masks/{index:03d}.png"
            _save_png(output / mask_path, mask.astype(np.uint8) * 255)
            instances.append({"index": index, "box": box.tolist(), "score": float(score), "mask": mask_path})
        metadata = {"image": str(args.image.resolve()), "width": result["width"], "height": result["height"],
                    "prompt": result["prompt"], "threshold": result["threshold"],
                    "model": args.model, "device": segmenter.device, "instances": instances}
        (output / "instances.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Device: {segmenter.device}")
        print(f"Found: {len(instances)} instances (prompt: {result['prompt']})")
        print(f"Saved: {output.resolve()}")
        return 0
    except (OSError, ValueError, RuntimeError, cv2.error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
