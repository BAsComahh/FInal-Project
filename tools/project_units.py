"""Display identified tray rectangles on a homography-rectified battlefield."""

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.image_io import load_image, save_image
from components.boundary_detection.io import save_report
from components.homography import compute_homography, rectify_units, render_unit_layers


def _load_masks(units, manifest_path):
    masks = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise ValueError("Each unit must be a geometry record")
        path = unit.get("mask_path")
        if path is None:
            continue
        if not isinstance(path, str) or not path.strip() or not isinstance(unit.get("unit_id"), str):
            raise ValueError("mask_path needs a non-empty path and a string unit_id")
        path = Path(path)
        if not path.is_absolute():
            path = manifest_path.parent / path
        masks[unit["unit_id"]] = load_image(path, mode="gray")
    return masks


def _preview_layers(result, args, save_overlay):
    window = "Battlefield layers - R: rectangles, M: masks, S: save, Esc: close"
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
    cv2.createTrackbar("Rectangles", window, int(args.rectangles), 1, lambda _: None)
    cv2.createTrackbar("Masks", window, int(args.masks), 1, lambda _: None)
    previous, canvas = None, result["overlay"]
    try:
        while cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) >= 1:
            rectangles = bool(cv2.getTrackbarPos("Rectangles", window))
            masks = bool(cv2.getTrackbarPos("Masks", window))
            if masks and not result["masks"] and result["units"]:
                print("No masks loaded. Add mask_path to the unit geometry to enable the mask layer.", flush=True)
                cv2.setTrackbarPos("Masks", window, 0)
                masks = False
            current = (rectangles, masks)
            if current != previous:
                canvas = render_unit_layers(result["rectified"], result["units"], masks=result["masks"],
                                            show_rectangles=rectangles, show_masks=masks, mask_alpha=args.mask_alpha)
                scale = min(1, 1280 / canvas.shape[1], 850 / canvas.shape[0])
                cv2.imshow(window, cv2.resize(canvas, None, fx=scale, fy=scale))
                previous = current
            key = cv2.waitKey(30) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                cv2.setTrackbarPos("Rectangles", window, int(not rectangles))
            elif key in (ord("m"), ord("M")):
                cv2.setTrackbarPos("Masks", window, int(not masks))
            elif key in (ord("s"), ord("S")):
                save_overlay(canvas, rectangles, masks)
    finally:
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Original image, before rectification")
    parser.add_argument("--units", type=Path, required=True,
                        help="Geometry JSON: {units: [{unit_id, corners_image}, ...]}; not the type catalog")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--calibration", type=Path, help="Existing homography JSON for this image")
    source.add_argument("--corners", nargs=8, type=float, metavar="COORD",
                        help="Original-image table corners in TL, TR, BR, BL order")
    parser.add_argument("--size", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"),
                        help="Output pixel size; only with --corners")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "outputs/project_units")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--rectangles", action=argparse.BooleanOptionalAction, default=True,
                        help="Rectangle/ID layer (default: on); --no-rectangles hides it")
    parser.add_argument("--masks", action=argparse.BooleanOptionalAction, default=False,
                        help="Mask layer (default: off); needs per-unit mask_path in geometry JSON")
    parser.add_argument("--mask-alpha", type=float, default=0.4, help="Mask opacity from 0 to 1")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.calibration:
            if args.size is not None:
                raise ValueError("--size cannot override saved calibration; use --corners instead")
            calibration = json.loads(args.calibration.read_text(encoding="utf-8-sig"))
        else:
            calibration = compute_homography(np.asarray(args.corners).reshape(4, 2), args.size)
        manifest = json.loads(args.units.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("units"), list):
            raise ValueError("Geometry JSON must contain a units list with unit_id and corners_image")
        image = load_image(args.image)
        if manifest.get("image_size") is not None and manifest["image_size"] != [image.shape[1], image.shape[0]]:
            raise ValueError("Geometry image_size does not match the original image [width, height]")
        masks = _load_masks(manifest["units"], args.units)
        result = rectify_units(image, manifest["units"], calibration, masks=masks,
                               show_rectangles=args.rectangles, show_masks=args.masks, mask_alpha=args.mask_alpha)
        report = {
            "image": str(args.image.resolve()), "image_size": [image.shape[1], image.shape[0]],
            "geometry_source": str(args.units.resolve()),
            "calibration_source": str(args.calibration.resolve()) if args.calibration else None,
            "matrix": np.asarray(calibration["matrix"]).tolist(),
            "output_size": list(calibration["output_size"]),
            "coordinate_space": "rectified_pixels", "corner_order": "cyclic; input order preserved",
            "layers": {"rectangles": args.rectangles, "masks": args.masks, "mask_alpha": args.mask_alpha},
            "mask_unit_ids": list(result["masks"]),
            "units": result["units"],
        }
        background_path = args.output_dir / f"{args.image.stem}_rectified.png"
        save_image(background_path, result["rectified"])
        print(f"Saved: {background_path.resolve()}")

        def save_overlay(canvas, rectangles, masks):
            path = args.output_dir / f"{args.image.stem}_overlay.png"
            save_image(path, canvas)
            report["layers"].update(rectangles=rectangles, masks=masks)
            report_path = save_report(args.output_dir / f"{args.image.stem}_units.json", report)
            print(f"Saved: {path.resolve()}")
            print(f"Saved: {report_path.resolve()} | units: {len(result['units'])}", flush=True)

        save_overlay(result["overlay"], args.rectangles, args.masks)
        print(f"Layers: rectangles={args.rectangles}, masks={args.masks}; masks loaded: {len(masks)}/{len(result['units'])}")
        if args.show:
            _preview_layers(result, args, save_overlay)
        return 0
    except (OSError, ValueError, TypeError, cv2.error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
