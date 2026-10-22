"""Detect a table boundary using the existing pipeline's default parameters.

Import ``detect_table`` with a BGR uint8 image (or an image path), or run:
    python -m tools.table_detector inputs/table4.png
"""

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

# Direct execution sets sys.path to tools/; include the project for components/.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.boundary_detection.cli import build_parser
from components.boundary_detection.config import DEFAULT_CONFIG, initial_switches
from components.boundary_detection.io import load_image
from components.boundary_detection.pipeline import compute_stages


CORNER_NAMES = ("TL", "TR", "BR", "BL")
SIDE_PAIRS = {"top": (0, 1), "right": (1, 2), "bottom": (2, 3), "left": (3, 0)}


def _boundary_result(polygon, image_shape, *, estimated=False, failure_reason=None):
    """Validate labelled TL/TR/BR/BL corners without reordering or clipping."""
    result = {
        "success": False,
        "corners": None,
        "edges": None,
        "estimated": bool(estimated),
        "needs_manual_correction": True,
        "reason": "",
        "candidate_corners": None,
        "invalid_corners": [],
    }
    if polygon is None:
        result["reason"] = "未能得到完整的四个角点，需要手动矫正。"
        if failure_reason:
            result["reason"] += f" ({failure_reason})"
        return result

    points = np.asarray(polygon, dtype=float)
    if points.shape != (4, 2) or not np.all(np.isfinite(points)):
        result["reason"] = "角点数量或坐标无效，需要手动矫正。"
        return result

    corners = {name: point.tolist() for name, point in zip(CORNER_NAMES, points)}
    height, width = image_shape[:2]
    center_x, center_y = (width - 1) / 2, (height - 1) / 2
    for index, (name, (x, y)) in enumerate(zip(CORNER_NAMES, points)):
        in_image = 0 <= x <= width - 1 and 0 <= y <= height - 1
        correct_x = x < center_x if index in (0, 3) else x > center_x
        correct_y = y < center_y if index in (0, 1) else y > center_y
        if not (in_image and correct_x and correct_y):
            result["invalid_corners"].append(name)
    if result["invalid_corners"]:
        result["candidate_corners"] = corners
        result["reason"] = (
            "角点未处于图像内对应的象限（中心线上的点也视为无效）："
            + ", ".join(result["invalid_corners"]) + "，需要手动矫正。"
        )
        return result

    edges = {side: np.concatenate([points[a], points[b]]).tolist()
             for side, (a, b) in SIDE_PAIRS.items()}
    result.update(success=True, corners=corners, edges=edges,
                  needs_manual_correction=False, reason="检测成功。")
    return result


def detect_table(image, *, config=DEFAULT_CONFIG):
    """Return final corners/edges, or a request for manual correction.

    ``image`` accepts a filesystem path or a uint8 NumPy image in OpenCV BGR,
    grayscale, or BGRA format. Coordinates are original-image pixels.
    ``config`` defaults to components/boundary_detection/config.toml. All other numeric
    parameters come from the existing CLI defaults; no process arguments are
    read and no viewer or export is opened.

    Corners are labelled TL, TR, BR, BL. Edges are top/right/bottom/left, each
    as [x1, y1, x2, y2], joined from the final corners. Inferred corners remain
    identified by ``estimated``. On detection failure, corners/edges are None
    and needs_manual_correction is True. Wrong-quadrant candidates are retained
    separately in candidate_corners for diagnostics or a future correction UI.

    Invalid image inputs and configuration errors raise exceptions rather than
    requesting correction of a table that could not be processed.
    """
    path = Path(image) if isinstance(image, (str, Path)) else None
    image = load_image(path) if path is not None else image
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.size == 0:
        raise ValueError("image must be a non-empty uint8 NumPy image or an image path")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.ndim == 3 and image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    elif image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be grayscale, BGR or BGRA")

    args = build_parser().parse_args([])
    args.config = Path(config)
    args.image = path
    switches = initial_switches(args)
    _, report = compute_stages(image, args, switches)
    return _boundary_result(
        report["output_polygon"], image.shape,
        estimated=report["output_is_estimated"],
        failure_reason=report["final_frame"]["reason"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        result = detect_table(args.image, config=args.config)
    except (OSError, ValueError, cv2.error) as error:
        parser.error(str(error))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
