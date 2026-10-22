"""Search from outermost sides inward, replacing only one side per move."""

import heapq
from itertools import count

import numpy as np

from .frame import check_closed_frame


SIDES = ("top", "bottom", "left", "right")


def search_border_frame(candidates, image_shape, angle_tolerance=15,
                        connection_distance=20,
                        filter_direction=True, enabled=True,
                        max_candidates=0, max_states=5000):
    """Best-first search of inward ranks, with a reconstructable one-side path.

    Each state has four ranks into boundary-distance-sorted candidate lists.
    A child increments exactly one rank. Branches retain other possibilities,
    rather than permanently discarding three good sides after a failed trial.
    The first closed frame popped is outermost by summed normalized boundary
    distance within the searched lists. Limits are explicitly reported.
    """
    if not np.isfinite(angle_tolerance) or not 0 <= angle_tolerance < 45:
        raise ValueError("angle-tolerance must be finite and in [0, 45)")
    if max_candidates < 0 or max_states < 1:
        raise ValueError("border-search-candidates must be non-negative; border-search-limit must be positive")
    height, width = image_shape[:2]
    pools = {side: [] for side in SIDES}
    for index, candidate in enumerate(candidates):
        line = np.asarray(candidate["line"], dtype=float)
        delta = np.abs(line[2:] - line[:2])
        if not np.all(np.isfinite(line)) or np.linalg.norm(delta) < 1e-8:
            continue
        angle = float(np.degrees(np.arctan2(delta[1], delta[0])))
        midpoint = (line[:2] + line[2:]) / 2
        horizontal = angle <= (angle_tolerance if filter_direction else 45)
        vertical = angle >= 90 - angle_tolerance if filter_direction else angle > 45
        for side, coordinate, extent, axis_angle in [
            ("top", 1, height, 0), ("bottom", 1, height, 0),
            ("left", 0, width, 90), ("right", 0, width, 90),
        ]:
            if not (horizontal if coordinate == 1 else vertical):
                continue
            boundary = 0 if side in {"top", "left"} else extent - 1
            record = dict(candidate)
            record.update(candidate_index=index,
                          axis_deviation_degrees=abs(angle - axis_angle),
                          border_distance_px=float(abs(midpoint[coordinate] - boundary)))
            pools[side].append(record)
    for first, last, coordinate, extent in [("top", "bottom", 1, height), ("left", "right", 0, width)]:
        if len(pools[first]) == 1:
            midpoint = np.asarray(pools[first][0]["line"]).reshape(2, 2).mean(axis=0)[coordinate]
            pools[last if midpoint <= (extent - 1) / 2 else first] = []
    available_counts = {side: len(pool) for side, pool in pools.items()}
    for side in SIDES:
        pools[side].sort(key=lambda r: r["border_distance_px"])
        if max_candidates:
            pools[side] = pools[side][:max_candidates]
        for rank, record in enumerate(pools[side]):
            record["inward_rank"] = rank
    truncated = any(available_counts[s] > len(pools[s]) for s in SIDES)

    def selection(state):
        return {side: pools[side][rank] if pools[side] else None for side, rank in zip(SIDES, state)}

    def cost(state):
        return sum(pools[side][rank]["border_distance_px"] / max(1, (height - 1 if i < 2 else width - 1))
                   for i, (side, rank) in enumerate(zip(SIDES, state)))

    origin = (0, 0, 0, 0)
    outer = selection(origin)
    outer_frame = check_closed_frame(outer, connection_distance)
    info = {"enabled": bool(enabled), "found": False, "status": "disabled",
            "candidate_counts": available_counts, "searched_candidate_counts": {s: len(pools[s]) for s in SIDES},
            "candidate_limit": max_candidates, "state_limit": max_states, "candidate_lists_truncated": truncated,
            "checked_states": 1, "visited": [], "trace": [], "selected_ranks": list(origin)}

    def entry(state, parent, changed_side, checked):
        return {"ranks": list(state), "parent": list(parent) if parent is not None else None,
                "changed_side": changed_side, "connected_junctions": checked["connected_junctions"],
                "valid": checked["valid"], "reason": checked["reason"]}

    origin_entry = entry(origin, None, None, outer_frame)
    info["visited"].append(origin_entry)
    if not enabled or any(not pool for pool in pools.values()):
        info.update(found=outer_frame["valid"], status="disabled" if not enabled else "missing candidates",
                    stop_reason="inward search disabled" if not enabled else "a side has no candidates")
        info["trace"] = [{**origin_entry, "selected": outer, "frame": outer_frame}]
        return {"selected": outer, "frame": outer_frame, "search": info}

    queue = [(cost(origin), 0, 0, origin)]
    serial = count(1)
    parents = {origin: (None, None)}
    frames = {origin: outer_frame}
    best, best_frame = origin, outer_frame
    best_key = (-outer_frame["connected_junctions"], cost(origin))
    checked_count = 0
    found = False
    while queue and checked_count < max_states:
        _, _, _, state = heapq.heappop(queue)
        selected = selection(state)
        # Once opposite sides cross, moving either side further inward cannot
        # restore their order, so this branch need not be expanded.
        centers = {s: np.asarray(r["line"]).reshape(2, 2).mean(axis=0) for s, r in selected.items()}
        if centers["top"][1] >= centers["bottom"][1] or centers["left"][0] >= centers["right"][0]:
            continue
        checked = frames.get(state)
        if checked is None:
            checked = check_closed_frame(selected, connection_distance)
            if len({r["candidate_index"] for r in selected.values()}) != 4:
                checked.update(valid=False, polygon=None, reason="a candidate is reused for opposite sides")
            frames[state] = checked
        checked_count += 1
        parent, side = parents[state]
        if state != origin:
            info["visited"].append(entry(state, parent, side, checked))
        key = (-checked["connected_junctions"], cost(state))
        if key < best_key:
            best, best_frame, best_key = state, checked, key
        if checked["valid"]:
            best, best_frame, found = state, checked, True
            break
        for i, side in enumerate(SIDES):
            if state[i] + 1 >= len(pools[side]):
                continue
            next_state = list(state)
            next_state[i] += 1
            next_state = tuple(next_state)
            if next_state in parents:
                continue
            parents[next_state] = (state, side)
            heapq.heappush(queue, (cost(next_state), sum(next_state), next(serial), next_state))
    path = []
    current = best
    while current is not None:
        parent, side = parents[current]
        checked = frames[current]
        path.append({**entry(current, parent, side, checked), "selected": selection(current), "frame": checked})
        current = parent
    info["trace"] = path[::-1]
    status = "closed" if found else "state limit" if queue else "candidate limit" if truncated else "exhausted"
    reason = {"closed": "closed frame found", "state limit": "state limit reached; remaining combinations unsearched",
              "candidate limit": "searched candidate lists exhausted; deeper candidates excluded by limit",
              "exhausted": "all candidate combinations exhausted without a closed frame"}[status]
    info.update(found=found, status=status, stop_reason=reason,
                checked_states=checked_count, selected_ranks=list(best))
    return {"selected": selection(best), "frame": best_frame, "search": info}


def select_border_lines(lines, image_shape, angle_tolerance=15, filter_direction=True):
    """Choose distinct, axis-compatible segments nearest the image borders."""
    if not np.isfinite(angle_tolerance) or not 0 <= angle_tolerance < 45:
        raise ValueError("angle-tolerance must be finite and in [0, 45) degrees")
    height, width = image_shape[:2]
    lines = np.asarray(lines, dtype=np.float64).reshape(-1, 4)
    midpoints = (lines[:, :2] + lines[:, 2:]) / 2
    delta = np.abs(lines[:, 2:] - lines[:, :2])
    angles = np.degrees(np.arctan2(delta[:, 1], delta[:, 0]))
    selected = {side: None for side in ["top", "bottom", "left", "right"]}

    def retain(side, index, coordinate, boundary, axis_angle):
        selected[side] = {
            "line": lines[index].tolist(),
            "axis_deviation_degrees": float(abs(angles[index] - axis_angle)),
            "border_distance_px": float(abs(midpoints[index, coordinate] - boundary)),
        }

    for indices, coordinate, first, last, extent, axis_angle in [
        (np.flatnonzero(angles <= (angle_tolerance if filter_direction else 45)), 1, "top", "bottom", height - 1, 0),
        (np.flatnonzero(angles >= 90 - angle_tolerance) if filter_direction else np.flatnonzero(angles > 45),
         0, "left", "right", width - 1, 90),
    ]:
        if len(indices) == 0:
            continue
        ordered = indices[np.argsort(midpoints[indices, coordinate], kind="stable")]
        if len(ordered) == 1:
            index = ordered[0]
            if midpoints[index, coordinate] <= extent / 2:
                retain(first, index, coordinate, 0, axis_angle)
            else:
                retain(last, index, coordinate, extent, axis_angle)
        else:
            retain(first, ordered[0], coordinate, 0, axis_angle)
            retain(last, ordered[-1], coordinate, extent, axis_angle)
    return selected
