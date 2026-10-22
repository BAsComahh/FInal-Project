"""Endpoint closure diagnostics and selected-side line extension."""

import cv2
import numpy as np

ADJACENT = [("TL", "top", "left"), ("TR", "top", "right"),
            ("BR", "bottom", "right"), ("BL", "bottom", "left")]


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


def complete_quadrilateral(selected, strict_frame, enabled=True):
    """Intersect the four selected side lines without a connected-corner gate.

    Missing corners are intersections of adjacent infinite lines. This assumes
    neither a rectangle nor a parallelogram. The strict frame is not modified:
    inferred corners remain distinguishable from observed endpoint connections.
    """
    result = {"available": False, "estimated": False, "status": "skipped",
              "reason": "completion disabled", "polygon": None, "junctions": [],
              "observed_junctions": strict_frame["connected_junctions"], "inferred_junctions": 0,
              "strict_frame_valid": strict_frame["valid"], "method": "adjacent infinite-line intersections"}
    if not enabled:
        return result
    if any(selected.get(side) is None for _, a, b in ADJACENT for side in [a, b]):
        result["reason"] = "all four side lines are required"
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
        supported = bool(observed.get(name, {}).get("connected", False))
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
