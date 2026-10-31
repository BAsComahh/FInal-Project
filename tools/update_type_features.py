"""Update DINOv2 type features from a completed registration reference folder."""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.dinov2 import DinoV2Extractor, load_type_features, update_type_features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_dir", type=Path, help="Completed registration folder containing instances.json")
    parser.add_argument("--output", type=Path, help="NPZ to replace; default: <reference_dir>/type_features.npz")
    parser.add_argument("--model", default="facebook/dinov2-small", help="DINOv2 backbone ID or local model folder")
    parser.add_argument("--device", help="Torch device; defaults to the GPU with the most memory")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--download", action="store_true", help="Allow downloading uncached model files")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        extractor = DinoV2Extractor(args.model, args.device, allow_download=args.download)
        output = update_type_features(args.reference_dir, args.output, extractor=extractor, batch_size=args.batch_size)
        result = load_type_features(output)
        print(f"Updated: {output}")
        print(f"Model: {args.model}; device: {extractor.device}; dimension: {result['sample_features'].shape[1]}")
        for item in result["metadata"]["types"]:
            print(f"Type {item['type_id']}: {item['sample_count']} reference(s)")
        if result["metadata"]["skipped"]:
            print(f"Skipped empty references: {len(result['metadata']['skipped'])}")
        return 0
    except (ImportError, OSError, ValueError, KeyError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
