"""Corner, single-edge and mask-search proposals for a known-size tray."""

from dataclasses import asdict, dataclass
import heapq

import cv2
import numpy as np

from ..lsd import detect_lsd_lines
from ..merge import merge_collinear_segments
from ..geometry import line_intersection, rectangle_corners as rectangle
from ..scale import percent_to_length
from components.homography.geometry import transform_points
from .geometry import make_work_view
from .directional_chamfer import DirectionalChamfer


@dataclass
class TrayConfig:
    mode: str = "auto"
    merge: bool = True
    max_work_size: int = 512
    roi_margin_pct: float = 25
    min_line_length_pct: float = 12
    angle_tolerance_deg: float = 12
    endpoint_gap_pct: float = 18
    edge_tolerance_pct: float = 2.5
    merge_distance_pct: float = 2.5
    merge_gap_pct: float = 30
    corner_dedup_pct: float = 3
    corner_nudge_pct: float = 1
    candidate_dedup_pct: float = 1.5
    max_lines: int = 64
    max_corners: int = 16
    angle_step_deg: float = 5
    search_pct: float = 35
    refine_rounds: int = 6
    min_mask_coverage: float | None = None
    min_corner_edge_support: float = 0.40
    min_single_edge_support: float = 0.20
    top_k: int = 5
    min_visible_fraction: float = 0.80
    min_mask_fill: float = 0.85
    min_adjacent_edge_support: float = 0.65

    def validate(self):
        if self.mode not in ("auto", "corner", "edge", "mask"):
            raise ValueError("mode must be auto, corner, edge or mask")
        for key in ("roi_margin_pct", "min_line_length_pct", "endpoint_gap_pct", "edge_tolerance_pct",
                    "merge_distance_pct", "merge_gap_pct", "corner_dedup_pct", "corner_nudge_pct",
                    "candidate_dedup_pct", "search_pct"):
            percent_to_length(getattr(self, key), 1, name=key)
        if not 0 < self.angle_tolerance_deg < 45 or not 0 < self.angle_step_deg <= 45:
            raise ValueError("Angle tolerance must be in (0,45); angle step in (0,45]")
        for key in ("min_mask_fill", "min_corner_edge_support", "min_single_edge_support"):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"{key} must be in [0,1]")
        if self.min_mask_coverage is not None and not 0 <= self.min_mask_coverage <= 1:
            raise ValueError("min_mask_coverage must be in [0,1]")
        if not 0 < self.min_adjacent_edge_support <= 1:
            raise ValueError("min_adjacent_edge_support must be in (0,1]")
        if not 0 < self.min_visible_fraction <= 1:
            raise ValueError("min_visible_fraction must be in (0,1]")
        for key in ("max_work_size", "max_lines", "max_corners", "top_k"):
            value = getattr(self, key)
            if isinstance(value, bool) or int(value) != value or value < (32 if key == "max_work_size" else 1):
                raise ValueError(f"Invalid {key}")
        if isinstance(self.refine_rounds, bool) or int(self.refine_rounds) != self.refine_rounds or self.refine_rounds < 0:
            raise ValueError("refine_rounds must be a non-negative integer")


def _work_lengths(size, config):
    short_side = float(min(size))
    lengths = {name: percent_to_length(getattr(config, f"{name}_pct"), short_side, name=f"{name}_pct")
               for name in ("min_line_length", "endpoint_gap", "edge_tolerance", "merge_distance", "merge_gap",
                            "corner_dedup", "corner_nudge", "candidate_dedup")}
    lengths["search_width"] = percent_to_length(config.search_pct, float(size[0]), name="search_pct")
    lengths["search_depth"] = percent_to_length(config.search_pct, float(size[1]), name="search_pct")
    return lengths


def _line_pool(view, config, lengths, *, merge=True):
    raw = detect_lsd_lines(view["image"], blur_size=3)
    length = np.linalg.norm(raw[:, 2:] - raw[:, :2], axis=1)
    midpoint = np.rint((raw[:, :2] + raw[:, 2:]) / 2).astype(int)
    inside = view["valid"][midpoint[:, 1], midpoint[:, 0]] != 0
    raw = raw[inside & (length >= lengths["min_line_length"])]
    length = np.linalg.norm(raw[:, 2:] - raw[:, :2], axis=1)
    raw = raw[np.argsort(-length, kind="stable")[:config.max_lines * 2]].astype(float)
    return raw, _merged_pool(raw, config, lengths) if merge else raw[:config.max_lines]


def _merged_pool(raw, config, lengths):
    pool = raw.copy()
    if config.merge and len(raw):
        groups = merge_collinear_segments(raw, min_segment_length=lengths["min_line_length"],
                                          check_source_length=False, check_axis=False,
                                          distance_tolerance=lengths["merge_distance"],
                                          max_gap=lengths["merge_gap"], min_coverage=0.5)
        if groups:
            pool = np.vstack((pool, [group["line"] for group in groups]))
    length = np.linalg.norm(pool[:, 2:] - pool[:, :2], axis=1)
    # Preserve rotated local edges; do not reuse table-border axis/region filters.
    return pool[np.argsort(-length, kind="stable")[:config.max_lines]]


def _corners(lines, config, shape, lengths):
    found = []
    tolerance = lengths["endpoint_gap"]
    for i, a in enumerate(lines):
        u = a[2:] - a[:2]
        u = u / np.linalg.norm(u)
        for j in range(i + 1, len(lines)):
            b = lines[j]
            v = b[2:] - b[:2]
            v = v / np.linalg.norm(v)
            if abs(u @ v) > np.sin(np.radians(config.angle_tolerance_deg)):
                continue
            point = line_intersection(a, b)
            if point is None or not (0 <= point[0] < shape[1] and 0 <= point[1] < shape[0]):
                continue
            gaps = [np.linalg.norm(line.reshape(2, 2) - point, axis=1).min() for line in (a, b)]
            if max(gaps) > tolerance:
                continue
            rays = [line.reshape(2, 2)[np.argmax(np.linalg.norm(line.reshape(2, 2) - point, axis=1))] - point
                    for line in (a, b)]
            rays = [ray / np.linalg.norm(ray) for ray in rays]
            strength = (sum(np.linalg.norm(line[2:] - line[:2]) for line in (a, b))
                        / (lengths["corner_nudge"] + sum(gaps)))
            found.append({"point": point, "rays": rays, "line_indices": [i, j], "strength": float(strength)})
    found.sort(key=lambda item: -item["strength"])
    unique = []
    for item in found:
        if not any(np.linalg.norm(item["point"] - old["point"]) < lengths["corner_dedup"]
                   and abs(item["rays"][0] @ old["rays"][0]) > 0.97 for old in unique):
            unique.append(item)
        if len(unique) >= config.max_corners:
            break
    return unique


class _Scorer:
    def __init__(self, view, raw, image_shape, config, lengths):
        self.view, self.config = view, config
        height, width = image_shape[:2]
        self.frame_polygon = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                                      dtype=np.float32)
        self.thresholds = lengths
        ys, xs = np.nonzero(view["mask"])
        self.all_points = np.column_stack((xs, ys)).astype(float)
        indices = np.linspace(0, len(xs) - 1, min(4096, len(xs))).astype(int)
        self.points = self.all_points[indices]
        self.center = self.all_points.mean(axis=0)
        self.raw = raw
        delta = raw[:, 2:] - raw[:, :2]
        self.lengths = np.linalg.norm(delta, axis=1)
        self.directions = delta / np.maximum(self.lengths[:, None], 1e-9)
        self.tolerance = lengths["edge_tolerance"]
        self.mask_area = len(self.all_points)
        self.area = float(np.prod(view["size"]))
        self._chamfer = None

    @property
    def chamfer(self):
        if self._chamfer is None:
            self._chamfer = DirectionalChamfer(self.view, self.raw, self.tolerance,
                                               np.radians(self.config.angle_tolerance_deg))
        return self._chamfer

    def mask_scores(self, center, angle, points):
        delta = points - center
        u = np.array([np.cos(angle), np.sin(angle)])
        v = np.array([-u[1], u[0]])
        coverage = float(((np.abs(delta @ u) <= self.view["size"][0] / 2)
                          & (np.abs(delta @ v) <= self.view["size"][1] / 2)).mean())
        intersection = min(coverage * self.mask_area, self.area)
        iou = intersection / max(1, self.mask_area + self.area - intersection)
        return coverage, intersection / self.area, iou

    def coarse_score(self, center, angle, method):
        if self.polygons(center, angle) is None:
            return -np.inf
        _, fill, iou = self.mask_scores(center, angle, self.points if method == "mask" else self.points[::4])
        if method == "mask" or not len(self.raw):
            return _fit_score(method, fill, iou, 0.0, 0.0)
        distance = self.chamfer.distances(np.asarray([center]), angle)[0]
        _, edge_support, corner_support = _edge_evidence(np.exp(-0.5 * (distance / self.tolerance) ** 2))
        return _fit_score(method, fill, iou, edge_support, corner_support)

    def polygons(self, center, angle):
        polygon = rectangle(center, angle, self.view["size"])
        height, width = self.view["mask"].shape
        if ((polygon < -1e-6).any() or (polygon[:, 0] > width - 1 + 1e-6).any() or (polygon[:, 1] > height - 1 + 1e-6).any()):
            return None
        image_polygon = transform_points(polygon, self.view["work_to_image"])
        visible_fraction = 1.0
        if ((image_polygon < -1e-6).any() or
                (image_polygon > self.frame_polygon[2] + 1e-6).any()):
            projected = image_polygon.astype(np.float32)
            if not cv2.isContourConvex(projected):
                return None
            area = cv2.contourArea(projected)
            visible_area, _ = cv2.intersectConvexConvex(projected, self.frame_polygon)
            if area <= 0 or visible_area <= 0:
                return None
            visible_fraction = min(visible_area / area, 1.0)
            if visible_fraction + 1e-6 < self.config.min_visible_fraction:
                return None
        return polygon, image_polygon, visible_fraction

    def score(self, proposal, method, *, exact=False):
        center, angle, provenance = proposal
        polygons = self.polygons(center, angle)
        if polygons is None:
            return None
        polygon, image_polygon, visible_fraction = polygons
        coverage, fill, iou = self.mask_scores(center, angle, self.all_points if exact else self.points)
        samples_per_side = np.zeros((4, 24))
        if exact or method != "mask":
            for index, (a, b) in enumerate(zip(polygon, np.roll(polygon, -1, axis=0))):
                direction = (b - a) / np.linalg.norm(b - a)
                aligned = np.abs(self.directions @ direction) >= np.cos(np.radians(self.config.angle_tolerance_deg))
                lines = self.raw[aligned]
                if not len(lines):
                    continue
                samples = a + np.linspace(0.03, 0.97, 24)[:, None] * (b - a)
                x, y = np.rint(samples).astype(int).T
                visible = self.view["visible"][y, x]
                line_delta = lines[:, 2:] - lines[:, :2]
                offset = samples[:, None] - lines[None, :, :2]
                t = np.clip((offset * line_delta).sum(axis=2) / (line_delta ** 2).sum(axis=1), 0, 1)
                nearest = lines[None, :, :2] + t[:, :, None] * line_delta
                distances = np.linalg.norm(samples[:, None] - nearest, axis=2).min(axis=1)
                samples_per_side[index] = np.exp(-0.5 * (distances / self.tolerance) ** 2) * visible
        sides, edge_support, corner_support = _edge_evidence(samples_per_side)
        score = _fit_score(method, fill, iou, edge_support, corner_support)
        return {"method": method, "score": score, "mask_coverage": coverage, "mask_fill": fill,
                "mask_iou": float(iou), "visible_fraction": visible_fraction,
                "edge_support": edge_support, "edge_support_per_side": sides.tolist(),
                "corner_support": corner_support,
                "center_work": np.asarray(center).tolist(), "angle_deg": float(np.degrees(angle) % 180),
                "corners_work": polygon.tolist(), "corners_image": image_polygon.tolist(),
                "corners_plane": transform_points(polygon, self.view["work_to_plane"]).tolist(),
                "center_plane": transform_points(center, self.view["work_to_plane"]).tolist(),
                "provenance": provenance}


def _edge_evidence(samples):
    sides = samples.mean(axis=1)
    # A corner needs two supported sides and visible evidence near their shared vertex.
    supported_sides = np.minimum(sides, np.roll(sides, -1))
    starts = samples[:, :4].mean(axis=1)
    ends = samples[:, -4:].mean(axis=1)
    supported_vertices = np.minimum(ends, np.roll(starts, -1))
    corner = np.minimum(supported_sides, supported_vertices).max()
    return sides, float(sides.mean()), float(corner)


def _fit_score(method, fill, iou, edge_support, corner_support):
    if method == "mask":
        return 0.8 * fill + 0.2 * iou
    return 0.65 * edge_support + 0.20 * corner_support + 0.15 * fill


def _corner_proposals(corners, size):
    for index, item in enumerate(corners):
        rays = (item["rays"],) if size[0] == size[1] else (item["rays"], item["rays"][::-1])
        for first, second in rays:
            angle = np.arctan2(first[1], first[0])
            side = 1 if first[0] * second[1] - first[1] * second[0] > 0 else -1
            across = np.array([-first[1], first[0]]) * side
            center = item["point"] + first * size[0] / 2 + across * size[1] / 2
            yield center, angle, {"corner_index": index}


def _local_proposals(center, angle, lengths, provenance):
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            for degrees in (-2, 0, 2):
                yield (center + np.array([dx, dy]) * lengths["corner_nudge"],
                       angle + np.radians(degrees), provenance)


def _edge_seeds(lines, size, mask_center):
    for index, line in enumerate(lines[:12]):
        u = (line[2:] - line[:2]) / np.linalg.norm(line[2:] - line[:2])
        normal = np.array([-u[1], u[0]])
        on_line = line[:2] + u * ((mask_center - line[:2]) @ u)
        swaps = (False,) if size[0] == size[1] else (False, True)
        for swap in swaps:
            across = size[0] if swap else size[1]
            angle = np.arctan2(u[1], u[0]) + (np.pi / 2 if swap else 0)
            for side in (-1, 1):
                center = on_line + normal * side * across / 2
                yield center, angle, {"line_index": index, "search": "edge_beam"}


_BEAM_MOVES = tuple((x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if x or y)


def _beam_neighbors(center, angle, step):
    for x, y in _BEAM_MOVES:
        yield center + step * np.array([x, y]) / np.hypot(x, y), angle
    for degrees in (-5, 5):
        yield center, angle + np.radians(degrees)


def _search_beam(seeds, scorer, method, rounds):
    width, depth = scorer.view["size"]
    step = 0.10 * min(width, depth)
    period = np.pi / 2 if width == depth else np.pi
    poses, scores = {}, {}

    def add(frontier, center, angle, provenance):
        key = (round(float(center[0]), 7), round(float(center[1]), 7),
               round(float(angle % period), 9) % round(period, 9))
        if key not in scores:
            poses[key] = center, angle, provenance
            scores[key] = scorer.coarse_score(center, angle, method)
        frontier[key] = None

    frontier = {}
    for center, angle, provenance in seeds:
        add(frontier, center, angle, provenance)
    for round_index in range(rounds + 1):
        ranked = sorted(frontier, key=scores.__getitem__, reverse=True)[:3]
        selected = [key for key in ranked if np.isfinite(scores[key])]
        if round_index == rounds or not selected:
            break
        if round_index and set(selected) == set(beam):
            break
        beam = selected
        frontier = dict.fromkeys(beam)
        for key in beam:
            center, angle, provenance = poses[key]
            for position, rotation in _beam_neighbors(center, angle, step):
                add(frontier, position, rotation, provenance)
    return [poses[key] for key in selected], len(scores), round_index


def _mask_seeds(scorer, centers, config):
    width, depth = scorer.view["size"]
    angles = np.arange(0, 90 if width == depth else 180, config.angle_step_deg)
    return ((center, angle, {"search": "mask_beam"}) for center in centers for angle in np.radians(angles))


def _rank(proposals, method, scorer, config):
    heap, count = [], 0

    def offer(item, serial):
        entry = (_reliable_corner(item, method, config), item["score"], serial, item)
        if len(heap) < max(20, config.top_k * 4):
            heapq.heappush(heap, entry)
        elif entry[:3] > heap[0][:3]:
            heapq.heapreplace(heap, entry)

    for index, proposal in enumerate(proposals):
        item = scorer.score(proposal, method)
        if item is None:
            continue
        count += 1
        offer(item, index)
    ranked = []
    for _, _, _, item in heap:
        proposal = (np.asarray(item["center_work"]), np.radians(item["angle_deg"]), item["provenance"])
        if method == "mask":
            exact_item = scorer.score(proposal, method, exact=True)
            if exact_item is not None:
                ranked.append(exact_item)
            continue
        # Only the mask sampling changes at this stage. The original LSD score
        # was already computed for this exact position and angle.
        center, angle, _ = proposal
        coverage, fill, iou = scorer.mask_scores(center, angle, scorer.all_points)
        item.update(mask_coverage=coverage, mask_fill=fill, mask_iou=iou,
                    score=_fit_score(method, fill, iou, item["edge_support"], item["corner_support"]))
        ranked.append(item)
    ranked.sort(key=lambda item: (_acceptance(item, method, config) is not None,
                                  _reliable_corner(item, method, config), item["score"]), reverse=True)
    unique = []
    for item in ranked:
        if not any(np.linalg.norm(np.asarray(item["center_work"]) - old["center_work"]) < scorer.thresholds["candidate_dedup"]
                   and abs(((item["angle_deg"] - old["angle_deg"] + 90) % 180) - 90) < 2 for old in unique):
            unique.append(item)
        if len(unique) >= config.top_k:
            break
    return count, unique


def _reliable_corner(item, method, config):
    return (method != "mask" and config.min_mask_coverage is None
            and item["mask_fill"] > config.min_mask_fill
            and item["corner_support"] >= config.min_adjacent_edge_support)


def _acceptance(item, method, config):
    if item["mask_fill"] <= config.min_mask_fill:
        return None
    edge_ok = item["edge_support"] >= _min_edge_support(method, config)
    if config.min_mask_coverage is not None:
        return "mask_coverage" if edge_ok and item["mask_coverage"] >= config.min_mask_coverage else None
    if edge_ok:
        return "mask_fill"
    return "reliable_corner" if _reliable_corner(item, method, config) else None


def _accepted_candidate(top, method, config):
    return next((item for item in top if _acceptance(item, method, config) is not None), None)


def _min_edge_support(method, config):
    if method in ("corner", "local"):
        return config.min_corner_edge_support
    return config.min_single_edge_support if method == "edge" else 0.0


def _fit_seeds(seeds, method, scorer, config):
    beam, count, rounds = _search_beam(seeds, scorer, method, int(config.refine_rounds))
    diagnostics = []
    for center, angle, provenance in beam:
        proposals = (_local_proposals(center, angle, scorer.thresholds, provenance)
                     if config.refine_rounds else [(center, angle, provenance)])
        evaluated, top = _rank(proposals, method, scorer, config)
        count += evaluated
        if _accepted_candidate(top, method, config):
            return count, top, rounds
        diagnostics.extend(top)
    diagnostics.sort(key=lambda item: -item["score"])
    return count, diagnostics[:config.top_k], rounds


def _rank_local(corners, scorer, config):
    points = transform_points(corners, scorer.view["image_to_work"])
    center = points.mean(axis=0)
    axis = points[1] - points[0]
    angle = np.arctan2(axis[1], axis[0])
    return _fit_seeds([(center, angle, {"initialization": "previous_accepted_corners"})],
                      "local", scorer, config)


def _rank_complete(method, scorer, config, lines, corners):
    if method == "corner":
        return _fit_seeds(_corner_proposals(corners, scorer.view["size"]), method, scorer, config)
    if method == "edge":
        return _fit_seeds(_edge_seeds(lines, scorer.view["size"], scorer.center), method, scorer, config)

    count, top, rounds = _fit_seeds(_mask_seeds(scorer, [scorer.center], config), method, scorer, config)
    if _accepted_candidate(top, method, config):
        return count, top, rounds
    bbox_center = (scorer.all_points.min(axis=0) + scorer.all_points.max(axis=0)) / 2
    offsets = np.array(((0, 0), *_BEAM_MOVES), dtype=float)
    offsets *= [scorer.thresholds["search_width"], scorer.thresholds["search_depth"]]
    retry_count, retry_top, retry_rounds = _fit_seeds(
        _mask_seeds(scorer, bbox_center + offsets, config), method, scorer, config)
    if _accepted_candidate(retry_top, method, config):
        top = retry_top
    else:
        top = sorted(top + retry_top, key=lambda item: -item["score"])[:config.top_k]
    return count + retry_count, top, rounds + retry_rounds


def fit_tray(image, mask, size, *, image_to_plane=None, config=None, initial_corners=None):
    """Fit one rectangular tray; size is in pixels or calibrated plane units.

    Results are geometry proposals requiring visual validation, not measured
    accuracy guarantees. All image corners refer to the original input image.
    """
    config = config or TrayConfig()
    config.validate()
    image = np.asarray(image)
    mask = np.asarray(mask)
    size = np.asarray(size, dtype=float)
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be a uint8 BGR image")
    if mask.ndim != 2 or mask.shape != image.shape[:2] or not np.isfinite(mask).all():
        raise ValueError("mask must be finite and match the original image dimensions")
    mask = mask != 0
    if not mask.any():
        raise ValueError("Cannot fit a tray to an empty mask")
    if size.shape != (2,) or not np.isfinite(size).all() or (size <= 0).any():
        raise ValueError("size must be a positive finite width/depth pair")
    if initial_corners is not None:
        initial_corners = np.asarray(initial_corners, dtype=float)
        if initial_corners.shape != (4, 2) or not np.isfinite(initial_corners).all():
            raise ValueError("initial_corners must be four finite cyclic image points")
    margin = percent_to_length(config.roi_margin_pct, 1, name="roi_margin_pct")
    view = make_work_view(image, mask, size, image_to_plane, config.max_work_size, margin)
    lengths = _work_lengths(view["size"], config)
    local = initial_corners is not None and config.mode == "auto"
    raw, lines = _line_pool(view, config, lengths, merge=not local)
    corners = [] if local else _corners(lines, config, view["mask"].shape, lengths)
    scorer = _Scorer(view, raw, image.shape, config, lengths)
    stages, chosen = [], None
    for method in (("local", "corner", "edge", "mask") if local else ("corner", "edge", "mask")):
        if config.mode != "auto" and config.mode != method:
            continue
        if method == "corner" and local:
            lines = _merged_pool(raw, config, lengths)
            corners = _corners(lines, config, view["mask"].shape, lengths)
        if method == "local":
            count, top, rounds = _rank_local(initial_corners, scorer, config)
        else:
            count, top, rounds = _rank_complete(method, scorer, config, lines, corners)
        accepted_item = _accepted_candidate(top, method, config)
        accepted = accepted_item is not None
        stages.append({"method": method, "candidate_count": count, "beam_rounds": rounds,
                       "accepted": accepted, "top": top,
                       "accepted_index": top.index(accepted_item) if accepted else None})
        if accepted:
            accepted_item["acceptance"] = _acceptance(accepted_item, method, config)
            chosen = accepted_item
            break
    success = chosen is not None
    if chosen is None:
        available = [stage["top"][0] for stage in stages if stage["top"]]
        chosen = max(available, key=lambda item: item["mask_fill"]) if available else None
    return {"success": success, "needs_review": True, "best": chosen,
            "coordinate_space": "image_pixels" if image_to_plane is None else "calibrated_plane",
            "requested_size": size.tolist(), "corner_order": "cyclic; width follows reported angle",
            "config": asdict(config), "stages": stages,
            "percentage_basis": {"local_lengths": "tray_short_side_work_px",
                                 "tray_short_side_work_px": float(min(view["size"])),
                                 "search": "tray_width_and_depth_work_px", "tray_size_work_px": view["size"].tolist(),
                                 "roi_margin": "bbox_max_span_padding_and_tray_diagonal_radius_multiplier"},
            "resolved_lengths_work_px": lengths,
            "image_to_work": view["image_to_work"].tolist(), "work_size": list(view["mask"].shape[::-1]),
            "raw_lines_work": raw.tolist(), "candidate_lines_work": lines.tolist(),
            "corner_candidates_work": [{"point": c["point"].tolist(), "line_indices": c["line_indices"],
                                         "strength": c["strength"]} for c in corners]}
