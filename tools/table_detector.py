"""Detect table corners with default boundary parameters: python -m tools.table_detector IMAGE."""

import argparse
import json
from pathlib import Path
import sys

import cv2

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.boundary_detection.config import DEFAULT_CONFIG
from components.boundary_detection.table import detect_table


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
