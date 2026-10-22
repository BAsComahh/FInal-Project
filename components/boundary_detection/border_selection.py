"""Select the longest eligible line for each side of the image."""

import numpy as np


SIDES = ("top", "bottom", "left", "right")


def side_search_regions(image_shape, region_ratio=1 / 3):
    """Return per-side midpoint bounds; None removes the outer-region filter."""
    if region_ratio is None:
        return None
    if not np.isfinite(region_ratio) or not 0 < region_ratio <= 0.5:
        raise ValueError("border-region-ratio must be finite and in (0, 0.5]")
    height, width = image_shape[:2]
    return {
        "top": (0.0, (height - 1) * region_ratio),
        "bottom": ((height - 1) - (height - 1) * region_ratio, float(height - 1)),
        "left": (0.0, (width - 1) * region_ratio),
        "right": ((width - 1) - (width - 1) * region_ratio, float(width - 1)),
    }


def select_longest_sides(candidates, image_shape, angle_tolerance=15,
                         filter_direction=True, region_ratio=1 / 3):
    """Inspect every candidate once; select by length, then boundary proximity.

    Horizontal observations belong to the top or bottom half, vertical ones to
    the left or right half. The optional outer-region filter narrows those
    halves to the outer thirds by default. There is no closure search.
    """
    if not np.isfinite(angle_tolerance) or not 0 <= angle_tolerance < 45:
        raise ValueError("angle-tolerance must be finite and in [0, 45)")
    height, width = image_shape[:2]
    regions = side_search_regions(image_shape, region_ratio)
    selected = {side: None for side in SIDES}
    counts = {side: 0 for side in SIDES}
    rejected = {side: 0 for side in SIDES}
    for index, candidate in enumerate(candidates):
        line = np.asarray(candidate["line"], dtype=float)
        if line.shape != (4,) or not np.all(np.isfinite(line)):
            continue
        delta = line[2:] - line[:2]
        length = float(np.linalg.norm(delta))
        if length < 1e-8:
            continue
        angle = float(np.degrees(np.arctan2(abs(delta[1]), abs(delta[0]))))
        midpoint = (line[:2] + line[2:]) / 2
        horizontal = angle <= (angle_tolerance if filter_direction else 45)
        vertical = angle >= 90 - angle_tolerance if filter_direction else angle > 45
        if horizontal:
            coordinate, extent, axis_angle = 1, height, 0
            side = "top" if midpoint[1] <= (height - 1) / 2 else "bottom"
        elif vertical:
            coordinate, extent, axis_angle = 0, width, 90
            side = "left" if midpoint[0] <= (width - 1) / 2 else "right"
        else:
            continue
        if regions is not None and not regions[side][0] <= midpoint[coordinate] <= regions[side][1]:
            rejected[side] += 1
            continue
        counts[side] += 1
        boundary = 0 if side in {"top", "left"} else extent - 1
        record = dict(candidate)
        record.update(candidate_index=index, length_px=length,
                      axis_deviation_degrees=abs(angle - axis_angle),
                      border_distance_px=float(abs(midpoint[coordinate] - boundary)))
        previous = selected[side]
        if previous is None or (length, -record["border_distance_px"]) > (
                previous["length_px"], -previous["border_distance_px"]):
            selected[side] = record

    missing = [side for side in SIDES if selected[side] is None]
    info = {
        "method": "longest_per_side", "status": "missing candidates" if missing else "selected",
        "stop_reason": "missing sides: " + ", ".join(missing) if missing
                       else "all candidates examined; longest line selected for each side",
        "examined_candidates": len(candidates), "candidate_counts": counts,
        "selected_lengths_px": {s: r["length_px"] if r else None for s, r in selected.items()},
        "region_enabled": regions is not None, "region_ratio": region_ratio,
        "region_bounds_px": regions, "region_rejected_counts": rejected,
        "tie_breaker": "nearest image boundary; input order for exact ties",
    }
    return {"selected": selected, "selection": info}
