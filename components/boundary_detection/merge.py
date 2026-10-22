"""Conservatively join adjacent, nearly collinear LSD segments."""

import numpy as np


def _fit_segments(segments):
    """Length-weighted orthogonal fit; bounds come from observed endpoints."""
    endpoints = segments.reshape(-1, 2)
    lengths = np.linalg.norm(segments[:, 2:] - segments[:, :2], axis=1)
    weights = np.repeat(lengths, 2)
    center = np.average(endpoints, axis=0, weights=weights)
    centered = endpoints - center
    covariance = (centered * weights[:, None]).T @ centered / weights.sum()
    _, vectors = np.linalg.eigh(covariance)
    direction = vectors[:, -1]
    normal = np.array([-direction[1], direction[0]])
    projections = (centered @ direction).reshape(-1, 2)
    intervals = np.sort(projections, axis=1)
    intervals = intervals[np.argsort(intervals[:, 0])]
    start, end = intervals[0]
    covered, largest_gap = 0.0, 0.0
    for lo, hi in intervals[1:]:
        if lo > end:
            covered += end - start
            largest_gap = max(largest_gap, lo - end)
            start, end = lo, hi
        else:
            end = max(end, hi)
    covered += end - start
    low, high = float(projections.min()), float(projections.max())
    return {
        "line": np.concatenate([center + low * direction, center + high * direction]),
        "center": center, "direction": direction, "normal": normal,
        "low": low, "high": high,
        "coverage": float(covered / (high - low)),
        "max_gap_px": float(largest_gap),
        "max_residual_px": float(np.max(np.abs(centered @ normal))),
    }


def merge_eligible_mask(lines, min_segment_length=20, axis_tolerance=15,
                        check_source_length=True, check_axis=True):
    lines = np.asarray(lines, dtype=float).reshape(-1, 4)
    deltas = lines[:, 2:] - lines[:, :2]
    lengths = np.linalg.norm(deltas, axis=1)
    eligible = lengths > 1e-8
    if check_source_length:
        eligible &= lengths >= min_segment_length
    if check_axis:
        angles = np.degrees(np.arctan2(np.abs(deltas[:, 1]), np.abs(deltas[:, 0])))
        eligible &= (angles <= axis_tolerance) | (angles >= 90 - axis_tolerance)
    return eligible


def merge_collinear_segments(lines, min_segment_length=20, angle_tolerance=6,
                             distance_tolerance=6, max_gap=30, min_coverage=0.7,
                             axis_tolerance=15, *, check_source_length=True,
                             check_axis=True, check_angle=True, check_distance=True,
                             check_gap=True, check_coverage=True, diagnostics=None,
                             repeat_until_stable=True):
    """Return merged groups with source indices into the original LSD array.

    Each greedy pass fits the previous pass's clusters, then repeats until no
    clusters can be joined. Every proposal is refitted and checked against ALL
    original source segments, so filled gaps and averaged directions do not
    become invented evidence. The partition only coarsens; any productive pass
    strictly reduces its size, guaranteeing termination without a round limit.
    """
    for name, value in [("merge-min-length", min_segment_length),
                        ("merge-distance", distance_tolerance)]:
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if not np.isfinite(angle_tolerance) or not 0 <= angle_tolerance < 45:
        raise ValueError("merge-angle must be finite and in [0, 45) degrees")
    if not np.isfinite(axis_tolerance) or not 0 <= axis_tolerance < 45:
        raise ValueError("angle-tolerance must be finite and in [0, 45) degrees")
    if not np.isfinite(max_gap) or max_gap < 0:
        raise ValueError("merge-gap must be finite and non-negative")
    if not np.isfinite(min_coverage) or not 0 < min_coverage <= 1:
        raise ValueError("merge-min-coverage must be in (0, 1]")

    lines = np.asarray(lines, dtype=float).reshape(-1, 4)
    if not np.all(np.isfinite(lines)):
        raise ValueError("LSD segments must contain finite coordinates")
    deltas = lines[:, 2:] - lines[:, :2]
    lengths = np.linalg.norm(deltas, axis=1)
    directions = deltas / np.maximum(lengths[:, None], 1e-12)
    eligible = merge_eligible_mask(lines, min_segment_length, axis_tolerance,
                                   check_source_length, check_axis)
    rejected = {key: 0 for key in ["angle", "distance", "gap", "coverage"]}
    cosine = np.cos(np.radians(angle_tolerance))
    clusters = [{"sources": [int(i)], "fit": _fit_segments(lines[[i]]), "formed_in_round": 0}
                for i in np.flatnonzero(eligible)]
    rounds = []

    def describe(cluster):
        members, fitted = cluster["sources"], cluster["fit"]
        return {
            "line": fitted["line"].tolist(), "source_indices": members.copy(),
            "source_count": len(members), "max_source_length_px": float(lengths[members].max()),
            "length_px": fitted["high"] - fitted["low"], "coverage": fitted["coverage"],
            "max_gap_px": fitted["max_gap_px"], "max_residual_px": fitted["max_residual_px"],
            "formed_in_round": cluster["formed_in_round"],
        }

    while clusters:
        round_number = len(rounds) + 1
        spans = np.asarray([c["fit"]["line"] for c in clusters])
        span_delta = spans[:, 2:] - spans[:, :2]
        span_lengths = np.linalg.norm(span_delta, axis=1)
        span_directions = span_delta / span_lengths[:, None]
        available = np.ones(len(clusters), dtype=bool)
        following = []
        for seed in np.argsort(-span_lengths, kind="stable"):
            if not available[seed]:
                continue
            available[seed] = False
            members = clusters[seed]["sources"].copy()
            fit = clusters[seed]["fit"]
            joined_clusters = 1
            while True:
                indices = np.flatnonzero(available)
                if len(indices) == 0:
                    break
                points = spans[indices].reshape(-1, 2, 2) - fit["center"]
                residuals = np.max(np.abs(points @ fit["normal"]), axis=1)
                projected = points @ fit["direction"]
                gaps = np.maximum(0, np.maximum(projected.min(axis=1) - fit["high"],
                                                fit["low"] - projected.max(axis=1)))
                aligned = np.ones(len(indices), dtype=bool)
                if check_angle:
                    aligned &= np.abs(span_directions[indices] @ fit["direction"]) >= cosine - 1e-12
                    aligned &= np.abs(span_directions[indices] @ span_directions[seed]) >= cosine - 1e-12
                distance_ok = (residuals <= distance_tolerance) if check_distance else np.ones(len(indices), dtype=bool)
                gap_ok = (gaps <= max_gap) if check_gap else np.ones(len(indices), dtype=bool)
                rejected["angle"] += int((~aligned).sum())
                rejected["distance"] += int((~distance_ok).sum())
                rejected["gap"] += int((~gap_ok).sum())
                choices = np.flatnonzero(aligned & distance_ok & gap_ok)
                choices = choices[np.lexsort((residuals[choices], gaps[choices]))]
                added = False
                for position in choices:
                    index = int(indices[position])
                    # Clusters partition eligible raw sources; no source is
                    # counted twice, even after several rounds.
                    proposed = members + clusters[index]["sources"]
                    fitted = _fit_segments(lines[proposed])
                    aligned_group, aligned_pairs = True, True
                    if check_angle:
                        aligned_group = np.all(np.abs(directions[proposed] @ fitted["direction"]) >= cosine - 1e-12)
                        aligned_pairs = np.all(np.abs(directions[proposed] @ directions[proposed].T) >= cosine - 1e-12)
                    failures = {
                        "angle": not aligned_group or not aligned_pairs,
                        "distance": check_distance and fitted["max_residual_px"] > distance_tolerance,
                        "gap": check_gap and fitted["max_gap_px"] > max_gap,
                        "coverage": check_coverage and fitted["coverage"] < min_coverage,
                    }
                    for key, failed in failures.items():
                        rejected[key] += int(failed)
                    if any(failures.values()):
                        continue
                    members, fit = proposed, fitted
                    available[index] = False
                    joined_clusters += 1
                    added = True
                    break
                if not added:
                    break
            following.append({"sources": members, "fit": fit,
                              "formed_in_round": round_number if joined_clusters > 1
                              else clusters[seed]["formed_in_round"]})
        operations = len(clusters) - len(following)
        rounds.append({"round": round_number, "input_cluster_count": len(clusters),
                       "output_cluster_count": len(following), "merge_operations": operations,
                       "groups": [describe(c) for c in following if len(c["sources"]) > 1]})
        clusters = following
        if operations == 0 or not repeat_until_stable:
            break
    groups = [describe(c) for c in clusters if len(c["sources"]) > 1]
    if diagnostics is not None:
        converged = not rounds or rounds[-1]["merge_operations"] == 0
        diagnostics.clear()
        diagnostics.update(input_count=len(lines), eligible_count=int(eligible.sum()),
                           rejection_attempts=rejected, merged_group_count=len(groups),
                           repeat_until_stable=bool(repeat_until_stable), converged=converged,
                           rounds=rounds, pass_count=len(rounds),
                           productive_pass_count=sum(r["merge_operations"] > 0 for r in rounds),
                           stop_reason="no further merges" if converged else "single-pass mode")
    return groups
