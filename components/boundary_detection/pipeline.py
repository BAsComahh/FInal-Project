"""LSD pipeline shared by exports, the viewer and table detection."""

from pathlib import Path

import cv2
import numpy as np

from .border_selection import select_longest_sides
from .frame import check_closed_frame, complete_quadrilateral
from .merge import merge_collinear_segments, merge_eligible_mask
from .lsd import detect_lsd_lines
from .visualization import draw_border_lines, draw_completion, draw_frame_connections, draw_lines


STAGES = [("input", "0. Original"), ("preprocess", "1. Preprocessing"),
          ("raw", "2. Raw LSD"), ("eligible", "3. Merge eligibility"),
          ("merged", "4. Merge / fit"), ("length", "5. Length filter"),
          ("axis", "6. Direction filter"), ("borders", "7. Longest side selection"),
          ("closure", "8. Closure check"), ("completed", "9. Line completion")]


def preprocess_image(image, args, switches):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_size = args.blur_size if switches["blur"] else 1
    if blur_size < 1 or blur_size % 2 == 0:
        raise ValueError("blur-size must be a positive odd number")
    return gray if blur_size == 1 else cv2.GaussianBlur(gray, (blur_size, blur_size), 0)


def detect_segments(gray, args, switches):
    """Return raw LSD segments and a description, without post-filtering."""
    if not switches["detection"]:
        return np.empty((0, 4), dtype=np.float32), "Detection OFF; no candidate segments."
    mode = args.refine if switches["lsd_refinement"] else "none"
    return detect_lsd_lines(gray, blur_size=1, refine=mode), f"LSD; mode: {mode}."


def compute_stages(image, args, switches):
    stages = {}

    def add(key, overlay, count, note, enabled=True):
        stages[key] = {"image": overlay, "count": int(count), "enabled": bool(enabled), "note": note}

    add("input", image, 0, "Original image; pixel coordinates are unchanged.")
    blur_size = args.blur_size if switches["blur"] else 1
    blurred = preprocess_image(image, args, switches)
    add("preprocess", cv2.cvtColor(blurred, cv2.COLOR_GRAY2BGR), 0,
        f"Gaussian kernel {blur_size}x{blur_size}; grayscale is required by LSD.", switches["blur"])
    raw, source_note = detect_segments(blurred, args, switches)
    add("raw", draw_lines(image, raw, (0, 150, 255), 1), len(raw), source_note, switches["detection"])
    eligible = merge_eligible_mask(raw, args.merge_min_length, args.angle_tolerance,
                                   switches["merge_source_length"], switches["merge_axis"])
    eligible_overlay = draw_lines(image, raw[~eligible], (0, 150, 255), 1)
    eligible_overlay = draw_lines(eligible_overlay, raw[eligible], (30, 210, 30), 2)
    add("eligible", eligible_overlay, int(eligible.sum()),
        f"Green: allowed into merging; orange: rejected. {int(eligible.sum())}/{len(raw)} eligible.", switches["merge"])
    diagnostics = {}
    groups = []
    if switches["merge"]:
        groups = merge_collinear_segments(
            raw, args.merge_min_length, args.merge_angle, args.merge_distance,
            args.merge_gap, args.merge_min_coverage, args.angle_tolerance,
            check_source_length=switches["merge_source_length"], check_axis=switches["merge_axis"],
            check_angle=switches["merge_angle"], check_distance=switches["merge_distance"],
            check_gap=switches["merge_gap"], check_coverage=switches["merge_coverage"], diagnostics=diagnostics,
            repeat_until_stable=switches["repeat_merge"])
    fits = np.asarray([g["line"] for g in groups], dtype=float).reshape(-1, 4)
    merged_overlay = draw_lines(draw_lines(image, raw, (130, 130, 130), 1), fits, (255, 230, 0), 3)
    add("merged", merged_overlay, len(groups),
        f"Gray: raw; cyan: ALL {len(groups)} fitted groups. Passes: {diagnostics.get('pass_count', 0)}; "
        + diagnostics.get("stop_reason", "merging disabled"), switches["merge"])
    records = ([{"line": line.tolist(), "source": "original", "detector": "lsd", "raw_index": i} for i, line in enumerate(raw)]
               + [{"line": g["line"], "source": "merged", "merge_group": g} for g in groups])
    if switches["length_filter"]:
        records = [r for r in records if np.linalg.norm(np.asarray(r["line"])[2:] - np.asarray(r["line"])[:2]) >= args.min_line_length]
    length_records = records.copy()
    lines = np.asarray([r["line"] for r in records], dtype=float).reshape(-1, 4)
    add("length", draw_lines(image, lines, (30, 210, 30)), len(records),
        (f"Final minimum length: {args.min_line_length}px." if switches["length_filter"]
         else "Length filter OFF; all candidate lengths retained.")
        + " Pool contains original observations plus fitted spans.", switches["length_filter"])
    if switches["axis_filter"]:
        mask = merge_eligible_mask(lines, 0, args.angle_tolerance, check_source_length=False)
        records = [r for r, keep in zip(records, mask) if keep]
    lines = np.asarray([r["line"] for r in records], dtype=float).reshape(-1, 4)
    add("axis", draw_lines(image, lines, (30, 210, 30)), len(records),
        f"Horizontal/vertical tolerance: {args.angle_tolerance:g}deg. Source-axis eligibility is a separate switch.", switches["axis_filter"])
    selected = {side: None for side in ["top", "bottom", "left", "right"]}
    region_ratio = args.border_region_ratio if switches["search_region"] else None
    selection_info = {"status": "disabled", "stop_reason": "side selection disabled",
                      "examined_candidates": 0, "candidate_counts": {side: 0 for side in selected}}
    if switches["border_selection"]:
        found = select_longest_sides(records, image.shape, args.angle_tolerance,
                                      filter_direction=switches["axis_filter"], region_ratio=region_ratio)
        selected, selection_info = found["selected"], found["selection"]
    borders = draw_border_lines(image, selected) if switches["border_selection"] else draw_lines(image, lines, (30, 210, 30))
    add("borders", borders, sum(r is not None for r in selected.values()),
        f"{selection_info['status']}: {selection_info['stop_reason']}; examined {selection_info['examined_candidates']} candidates."
        if switches["border_selection"] else "Side selection is OFF; no selected sides.", switches["border_selection"])
    frame = {"valid": False, "reason": "closure disabled or side selection disabled", "polygon": None,
             "junctions": [], "connected_junctions": 0}
    if switches["closure"] and switches["border_selection"]:
        frame = check_closed_frame(selected, args.connection_distance)
    connected, closed = draw_frame_connections(image, selected, frame)
    closure_overlay = closed if frame["valid"] else connected if switches["border_selection"] else borders
    add("closure", closure_overlay, frame["connected_junctions"], frame["reason"],
        switches["closure"] and switches["border_selection"])
    completion = complete_quadrilateral(selected, frame, enabled=switches["completion"])
    completion_overlay = draw_completion(image, completion) if completion["available"] else closure_overlay
    add("completed", completion_overlay, completion["inferred_junctions"],
        f"{completion['status']}: {completion['reason']}. Green: observed; orange rings / *: inferred.",
        switches["completion"] and completion["available"])
    report = {
        "image": str(args.image.resolve()) if args.image is not None else None,
        "switches": dict(switches),
        "image_size": {"width": image.shape[1], "height": image.shape[0]},
        "opencv_version": cv2.__version__,
        "detector": "lsd",
        "parameters": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "stages": {key: {k: v for k, v in stage.items() if k != "image"} for key, stage in stages.items()},
        "raw_lines": raw.tolist(), "merge_eligible_indices": np.flatnonzero(eligible).tolist(),
        "merged_groups": groups, "merge_diagnostics": diagnostics,
        "after_length": length_records, "after_direction": records,
        "side_selection": selection_info,
        "final_sides": selected, "final_frame": frame,
        "frame_completion": completion,
        "output_polygon": frame["polygon"] if frame["valid"] else completion["polygon"],
        "output_is_estimated": not frame["valid"] and completion["available"] and completion["estimated"],
    }
    return stages, report
