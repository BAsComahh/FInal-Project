"""Endpoint closure, line-extension completion, and local frame refinement."""

from itertools import product

import cv2
import numpy as np

ADJACENT = [("TL", "top", "left"), ("TR", "top", "right"),
            ("BR", "bottom", "right"), ("BL", "bottom", "left")]
SIDE_CORNERS = {"top": (0, 1), "right": (1, 2), "bottom": (3, 2), "left": (0, 3)}
MIN_IMPROVEMENT_PX = 0.1


def check_closed_frame(selected, connection_distance=20):
    if not np.isfinite(connection_distance) or connection_distance <= 0:
        raise ValueError("connection-distance must be finite and positive")
    missing = [side for side, record in selected.items() if record is None]
    junctions = []
    for name, side_a, side_b in [
        ("TL", "top", "left"), ("TR", "top", "right"),
        ("BR", "bottom", "right"), ("BL", "bottom", "left"),
    ]:
        record = {"name": name, "sides": [side_a, side_b], "connected": False,
                  "point": None}
        junctions.append(record)
        if selected[side_a] is None or selected[side_b] is None:
            record["reason"] = "missing adjacent side"
            continue
        a = np.asarray(selected[side_a]["line"], dtype=float).reshape(2, 2)
        b = np.asarray(selected[side_b]["line"], dtype=float).reshape(2, 2)
        differences = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
        ia, ib = np.unravel_index(np.argmin(differences), differences.shape)
        record["endpoint_gap_px"] = float(differences[ia, ib])
        record["endpoint_indices"] = {side_a: int(ia), side_b: int(ib)}
        directions = np.column_stack([a[1] - a[0], -(b[1] - b[0])])
        if abs(np.linalg.det(directions)) < 1e-8:
            record["reason"] = "parallel or degenerate sides"
            continue
        t, _ = np.linalg.solve(directions, b[0] - a[0])
        point = a[0] + t * (a[1] - a[0])
        endpoint_distances = [float(np.linalg.norm(point - a[ia])), float(np.linalg.norm(point - b[ib]))]
        record["intersection_endpoint_distances_px"] = endpoint_distances
        # Infinite lines always intersect unless parallel; require the observed
        # segments to reach that intersection, allowing only a small pixel gap.
        if record["endpoint_gap_px"] > connection_distance or max(endpoint_distances) > connection_distance:
            record["reason"] = "segment endpoints are too far apart"
            continue
        record["connected"] = True
        record["point"] = point.tolist()
        record["reason"] = "endpoints connected within tolerance"

    valid = False
    polygon = None
    if missing:
        reason = "missing sides: " + ", ".join(missing)
    elif not all(j["connected"] for j in junctions):
        reason = "unconnected junctions: " + ", ".join(j["name"] for j in junctions if not j["connected"])
    else:
        each_end_connected = all(
            sorted(j["endpoint_indices"][side] for j in junctions if side in j["sides"]) == [0, 1]
            for side in selected
        )
        points = np.asarray([j["point"] for j in junctions], dtype=np.float32)
        if not each_end_connected:
            reason = "an edge connects twice at the same endpoint"
        elif not cv2.isContourConvex(points) or abs(cv2.contourArea(points)) <= 1:
            reason = "junctions do not form a non-degenerate convex frame"
        else:
            valid = True
            polygon = points.tolist()
            reason = "four sides connected at both endpoints"
    return {"valid": valid, "reason": reason, "polygon": polygon,
            "junctions": junctions, "connected_junctions": sum(j["connected"] for j in junctions)}


def complete_quadrilateral(selected, strict_frame, enabled=True, min_connected=2):
    """Use four observed side directions, with at least two connected corners.

    Missing corners are intersections of adjacent infinite lines. This assumes
    neither a rectangle nor a parallelogram. The strict frame is not modified:
    inferred corners remain distinguishable from observed endpoint connections.
    """
    if min_connected not in (2, 3, 4):
        raise ValueError("min_connected must be 2, 3 or 4")
    result = {"available": False, "estimated": False, "status": "skipped",
              "reason": "completion disabled", "polygon": None, "junctions": [],
              "observed_junctions": strict_frame["connected_junctions"], "inferred_junctions": 0,
              "strict_frame_valid": strict_frame["valid"], "method": "adjacent infinite-line intersections"}
    if not enabled:
        return result
    if any(selected.get(side) is None for _, a, b in ADJACENT for side in [a, b]):
        result["reason"] = "all four side lines are required"
        return result
    if strict_frame["connected_junctions"] < min_connected:
        result["reason"] = f"at least {min_connected} observed corner connections are required"
        return result
    observed = {j["name"]: j for j in strict_frame["junctions"]}
    points, junctions = [], []
    for name, side_a, side_b in ADJACENT:
        a = np.asarray(selected[side_a]["line"], dtype=float).reshape(2, 2)
        b = np.asarray(selected[side_b]["line"], dtype=float).reshape(2, 2)
        da, db = a[1] - a[0], b[1] - b[0]
        lengths = np.linalg.norm(da) * np.linalg.norm(db)
        matrix = np.column_stack([da, -db])
        if lengths < 1e-12 or abs(np.linalg.det(matrix)) / lengths < 1e-8:
            result["reason"] = f"{name}: adjacent lines are parallel or degenerate"
            return result
        t, _ = np.linalg.solve(matrix, b[0] - a[0])
        point = a[0] + t * da
        if not np.all(np.isfinite(point)):
            result["reason"] = f"{name}: non-finite line intersection"
            return result
        supported = bool(observed[name]["connected"])
        if supported:
            point = np.asarray(observed[name]["point"], dtype=float)
        points.append(point)
        junctions.append({"name": name, "point": point.tolist(), "sides": [side_a, side_b],
                          "observed": supported, "inferred": not supported,
                          "source": "connected endpoints" if supported else "extended-line intersection"})
    polygon = np.asarray(points, dtype=np.float64)
    # A consistent turn at all four corners rejects crossings and degeneracy.
    edges = np.roll(polygon, -1, axis=0) - polygon
    following = np.roll(edges, -1, axis=0)
    turns = edges[:, 0] * following[:, 1] - edges[:, 1] * following[:, 0]
    area = abs(np.sum(polygon[:, 0] * np.roll(polygon[:, 1], -1)
                      - polygon[:, 1] * np.roll(polygon[:, 0], -1))) / 2
    if (not np.all(np.isfinite(turns)) or not np.isfinite(area)
            or not (np.all(turns > 1e-8) or np.all(turns < -1e-8)) or area <= 1):
        result["reason"] = "intersections do not form a non-degenerate convex quadrilateral"
        return result
    inferred = sum(j["inferred"] for j in junctions)
    result.update(available=True, estimated=bool(inferred),
                  status="completed" if inferred else "already closed",
                  reason=f"{len(junctions) - inferred} observed corners; {inferred} inferred by line extension",
                  polygon=polygon.tolist(), junctions=junctions, inferred_junctions=inferred)
    return result


def _endpoint_distances(line, anchors):
    points = np.asarray(line, dtype=float).reshape(2, 2)
    forward = np.linalg.norm(points - anchors, axis=1)
    reverse = np.linalg.norm(points[::-1] - anchors, axis=1)
    return forward if forward.sum() <= reverse.sum() else reverse


def refine_closed_frame(selected, frame, candidates, search_radius=30,
                        angle_tolerance=10, max_candidates=12,
                        connection_distance=20, enabled=True,
                        axis_tolerance=15, check_axis=True):
    """Keep the initial frame unless a better endpoint-connected set is found.

    Anchors stay fixed during this one-pass local search. Every candidate must
    reach both reference corners. Minimize the four adjacent endpoint gaps;
    use distance to initial anchors only to break equal-gap ties. The anchors
    constrain locality rather than favoring the original edges. Improvements
    below 0.1px are ignored. Closure and convexity remain hard constraints.
    """
    if not np.isfinite(search_radius) or search_radius <= 0:
        raise ValueError("refine-radius must be finite and positive")
    if not np.isfinite(angle_tolerance) or not 0 <= angle_tolerance < 45:
        raise ValueError("refine-angle must be finite and in [0, 45) degrees")
    if max_candidates < 1:
        raise ValueError("refine-max-candidates must be positive")
    if not np.isfinite(axis_tolerance) or not 0 <= axis_tolerance < 45:
        raise ValueError("angle-tolerance must be finite and in [0, 45) degrees")
    result = {"selected": selected, "frame": frame, "status": "skipped",
              "reason": "disabled" if not enabled else "no initial closed frame",
              "anchors": frame["polygon"], "changed_sides": [],
              "local_candidate_indices": {side: [] for side in SIDE_CORNERS},
              "local_candidate_counts_before_limit": {side: 0 for side in SIDE_CORNERS},
              "checked_combinations": 0,
              "initial_mean_anchor_distance_px": None, "final_mean_anchor_distance_px": None,
              "initial_mean_endpoint_gap_px": None, "final_mean_endpoint_gap_px": None,
              "max_corner_shift_px": 0.0,
              "optimization_priority": ["mean_endpoint_gap_px", "mean_anchor_distance_px"],
              "minimum_improvement_px": MIN_IMPROVEMENT_PX}
    if not enabled or not frame["valid"]:
        return result

    anchors = np.asarray(frame["polygon"], dtype=float)
    initial_score = sum(_endpoint_distances(selected[side]["line"], anchors[list(pair)]).sum()
                        for side, pair in SIDE_CORNERS.items()) / 8
    initial_gap = np.mean([j["endpoint_gap_px"] for j in frame["junctions"]])
    best_score, best_gap = float(initial_score), float(initial_gap)
    result.update(initial_mean_anchor_distance_px=best_score,
                  initial_mean_endpoint_gap_px=best_gap,
                  final_mean_anchor_distance_px=best_score,
                  final_mean_endpoint_gap_px=best_gap,
                  status="unchanged", reason="no better local closed combination")
    local = {}
    cosine = np.cos(np.radians(angle_tolerance))
    for side, pair in SIDE_CORNERS.items():
        reference = anchors[list(pair)]
        direction = reference[1] - reference[0]
        direction /= np.linalg.norm(direction)
        choices = []
        original = None
        for index, candidate in enumerate(candidates):
            line = np.asarray(candidate["line"], dtype=float)
            delta = line[2:] - line[:2]
            length = np.linalg.norm(delta)
            if length <= 1e-8 or abs(np.dot(delta / length, direction)) < cosine - 1e-12:
                continue
            axis_angle = np.degrees(np.arctan2(abs(delta[1]), abs(delta[0])))
            deviation = axis_angle if side in {"top", "bottom"} else 90 - axis_angle
            if check_axis and deviation > axis_tolerance:
                continue
            distances = _endpoint_distances(line, reference)
            if np.max(distances) > search_radius:
                continue
            choice = {"index": index, "record": candidate, "score": float(distances.sum())}
            choices.append(choice)
            if np.allclose(line, selected[side]["line"], rtol=0, atol=1e-6):
                original = choice
        choices.sort(key=lambda c: c["score"])
        result["local_candidate_counts_before_limit"][side] = len(choices)
        limited = choices[:max_candidates]
        # Preserve the initial option when it satisfies the local constraints.
        if original is not None and all(c["index"] != original["index"] for c in limited):
            limited[-1] = original
        local[side] = limited
        result["local_candidate_indices"][side] = [c["index"] for c in limited]
    if any(not choices for choices in local.values()):
        result["reason"] = "a side has no candidates reaching both reference corners"
        return result

    sides = list(SIDE_CORNERS)
    # Cheap adjacency prefilter. Exact intersection distances, distinct endpoint
    # usage, and convexity are checked for each promising full combination.
    adjacency = []
    for side, next_side in zip(sides, sides[1:] + sides[:1]):
        compatible = np.zeros((len(local[side]), len(local[next_side])), dtype=bool)
        for i, a in enumerate(local[side]):
            points_a = np.asarray(a["record"]["line"]).reshape(2, 2)
            for j, b in enumerate(local[next_side]):
                points_b = np.asarray(b["record"]["line"]).reshape(2, 2)
                gap = np.linalg.norm(points_a[:, None] - points_b[None, :], axis=2).min()
                compatible[i, j] = gap <= connection_distance
        adjacency.append(compatible)
    for indices in product(*(range(len(local[side])) for side in sides)):
        if not all(adjacency[k][indices[k], indices[(k + 1) % 4]] for k in range(4)):
            continue
        choices = [local[side][index] for side, index in zip(sides, indices)]
        score = sum(c["score"] for c in choices) / 8
        if len({c["index"] for c in choices}) != 4:
            continue
        proposal = {side: dict(choice["record"]) for side, choice in zip(sides, choices)}
        result["checked_combinations"] += 1
        checked = check_closed_frame(proposal, connection_distance)
        if not checked["valid"]:
            continue
        shifts = np.linalg.norm(np.asarray(checked["polygon"]) - anchors, axis=1)
        if np.max(shifts) > search_radius:
            continue
        gap = float(np.mean([j["endpoint_gap_px"] for j in checked["junctions"]]))
        if (gap < best_gap - MIN_IMPROVEMENT_PX
                or (abs(gap - best_gap) <= 1e-6 and score < best_score - MIN_IMPROVEMENT_PX)):
            best_score, best_gap = float(score), gap
            result.update(selected=proposal, frame=checked, status="improved",
                          reason="tighter endpoint connections within the initial-corner neighborhood",
                          final_mean_anchor_distance_px=best_score,
                          final_mean_endpoint_gap_px=best_gap,
                          max_corner_shift_px=float(np.max(shifts)))
    result["changed_sides"] = [side for side in sides if not np.allclose(
        result["selected"][side]["line"], selected[side]["line"], rtol=0, atol=1e-6)]
    return result
