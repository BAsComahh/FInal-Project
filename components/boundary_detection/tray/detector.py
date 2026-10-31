"""Corner, single-edge and mask-search proposals for a known-size tray."""

from dataclasses import asdict, dataclass
import heapq

import numpy as np

from ..lsd import detect_lsd_lines
from ..merge import merge_collinear_segments
from ..geometry import line_intersection, rectangle_corners as rectangle
from ..scale import percent_to_length
from components.homography.geometry import transform_points
from .geometry import make_work_view


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
    refine_rounds: int = 3
    min_mask_coverage: float = 0.55
    min_corner_edge_support: float = 0.40
    min_single_edge_support: float = 0.20
    top_k: int = 5

    def validate(self):
        if self.mode not in ("auto", "corner", "edge", "mask"):
            raise ValueError("mode must be auto, corner, edge or mask")
        for key in ("roi_margin_pct", "min_line_length_pct", "endpoint_gap_pct", "edge_tolerance_pct",
                    "merge_distance_pct", "merge_gap_pct", "corner_dedup_pct", "corner_nudge_pct",
                    "candidate_dedup_pct", "search_pct"):
            percent_to_length(getattr(self, key), 1, name=key)
        if not 0 < self.angle_tolerance_deg < 45 or not 0 < self.angle_step_deg <= 45:
            raise ValueError("Angle tolerance must be in (0,45); angle step in (0,45]")
        for key in ("min_mask_coverage", "min_corner_edge_support", "min_single_edge_support"):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"{key} must be in [0,1]")
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
        self.view, self.config, self.image_shape = view, config, image_shape
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

    def score(self, proposal, method, *, exact=False):
        center, angle, provenance = proposal
        polygon = rectangle(center, angle, self.view["size"])
        height, width = self.view["mask"].shape
        if ((polygon < -1e-6).any() or (polygon[:, 0] > width - 1 + 1e-6).any() or (polygon[:, 1] > height - 1 + 1e-6).any()):
            return None
        image_polygon = transform_points(polygon, self.view["work_to_image"])
        if ((image_polygon < -1e-6).any() or (image_polygon[:, 0] > self.image_shape[1] - 1 + 1e-6).any()
                or (image_polygon[:, 1] > self.image_shape[0] - 1 + 1e-6).any()):
            return None
        points = self.all_points if exact else self.points
        delta = points - center
        u = np.array([np.cos(angle), np.sin(angle)])
        v = np.array([-u[1], u[0]])
        coverage = float(((np.abs(delta @ u) <= self.view["size"][0] / 2)
                          & (np.abs(delta @ v) <= self.view["size"][1] / 2)).mean())
        area = float(np.prod(self.view["size"]))
        intersection = min(coverage * len(self.all_points), area)
        iou = intersection / max(1, len(self.all_points) + area - intersection)
        support = []
        for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
            direction = (b - a) / np.linalg.norm(b - a)
            aligned = np.abs(self.directions @ direction) >= np.cos(np.radians(self.config.angle_tolerance_deg))
            lines = self.raw[aligned]
            if not len(lines):
                support.append(0.0)
                continue
            samples = a + np.linspace(0.03, 0.97, 24)[:, None] * (b - a)
            line_delta = lines[:, 2:] - lines[:, :2]
            offset = samples[:, None] - lines[None, :, :2]
            t = np.clip((offset * line_delta).sum(axis=2) / (line_delta ** 2).sum(axis=1), 0, 1)
            nearest = lines[None, :, :2] + t[:, :, None] * line_delta
            distances = np.linalg.norm(samples[:, None] - nearest, axis=2).min(axis=1)
            support.append(float(np.exp(-0.5 * (distances / self.tolerance) ** 2).mean()))
        edge_support = float(np.mean(support))
        score = (0.8 * coverage + 0.2 * iou if method == "mask" else
                 0.55 * edge_support + 0.35 * coverage + 0.10 * iou)
        return {"method": method, "score": float(score), "mask_coverage": coverage, "mask_iou": float(iou),
                "edge_support": edge_support, "edge_support_per_side": support,
                "center_work": np.asarray(center).tolist(), "angle_deg": float(np.degrees(angle) % 180),
                "corners_work": polygon.tolist(), "corners_image": image_polygon.tolist(),
                "corners_plane": transform_points(polygon, self.view["work_to_plane"]).tolist(),
                "center_plane": transform_points(center, self.view["work_to_plane"]).tolist(),
                "provenance": provenance}


def _corner_proposals(corners, size, nudge):
    for index, item in enumerate(corners):
        for first, second in (item["rays"], item["rays"][::-1]):
            angle = np.arctan2(first[1], first[0])
            side = 1 if first[0] * second[1] - first[1] * second[0] > 0 else -1
            for shift in (-2.0, 0.0, 2.0):
                theta = angle + np.radians(shift)
                u = np.array([np.cos(theta), np.sin(theta)])
                v = np.array([-u[1], u[0]]) * side
                for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
                    center = item["point"] + np.array([dx, dy]) * nudge + u * size[0] / 2 + v * size[1] / 2
                    yield center, theta, {"corner_index": index}


def _local_proposals(corners, view, lengths):
    points = transform_points(corners, view["image_to_work"])
    center = points.mean(axis=0)
    direction = points[1] - points[0]
    angle = np.arctan2(direction[1], direction[0])
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            for degrees in (-2, 0, 2):
                yield (center + np.array([dx, dy]) * lengths["corner_nudge"],
                       angle + np.radians(degrees), {"initialization": "previous_accepted_corners"})


def _edge_proposals(lines, size, mask_center):
    for index, line in enumerate(lines[:12]):
        u = (line[2:] - line[:2]) / np.linalg.norm(line[2:] - line[:2])
        v = np.array([-u[1], u[0]])
        on_line = line[:2] + u * ((mask_center - line[:2]) @ u)
        for swap in (False, True):
            along, across = size[::-1] if swap else size
            for side in (-1, 1):
                for shift in np.linspace(-0.4, 0.4, 7):
                    center = on_line + u * shift * along + v * side * across / 2
                    for angle_delta in (-2, 0, 2):
                        angle = np.arctan2(u[1], u[0]) + (np.pi / 2 if swap else 0) + np.radians(angle_delta)
                        yield center, angle, {"line_index": index}


def _mask_proposals(scorer, config):
    bbox_center = (scorer.all_points.min(axis=0) + scorer.all_points.max(axis=0)) / 2
    search = np.array([scorer.thresholds["search_width"], scorer.thresholds["search_depth"]])
    for base in (scorer.center, bbox_center):
        for dx in np.linspace(-1, 1, 5):
            for dy in np.linspace(-1, 1, 5):
                center = base + np.array([dx, dy]) * search
                for degrees in np.arange(0, 180, config.angle_step_deg):
                    yield center, np.radians(degrees), {"search": "centroid_and_bbox_translation_rotation"}


def _rank(proposals, method, scorer, config):
    heap, count = [], 0

    def offer(item, serial):
        entry = (item["score"], serial, item)
        if len(heap) < max(20, config.top_k * 4):
            heapq.heappush(heap, entry)
        elif entry[:2] > heap[0][:2]:
            heapq.heapreplace(heap, entry)

    for index, proposal in enumerate(proposals):
        item = scorer.score(proposal, method)
        if item is None:
            continue
        count += 1
        offer(item, index)
    # Coarse-to-fine local search avoids leaving the mask fallback at the
    # relatively sparse initial translation/angle grid resolution.
    serial = max((entry[1] for entry in heap), default=0) + 1
    if method in ("edge", "mask"):
        for round_index in range(config.refine_rounds):
            seeds = [entry[2] for entry in sorted(heap, reverse=True)[:3]]
            translation = (np.array([scorer.thresholds["search_width"], scorer.thresholds["search_depth"]])
                           / (4 * 2 ** round_index))
            angle_step = config.angle_step_deg / (2 * 2 ** round_index)
            for seed in seeds:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for da in (-1, 0, 1):
                            if not (dx or dy or da):
                                continue
                            proposal = (np.asarray(seed["center_work"]) + translation * [dx, dy],
                                        np.radians(seed["angle_deg"] + angle_step * da),
                                        {**seed["provenance"], "refinement_round": round_index + 1})
                            item = scorer.score(proposal, method)
                            if item is None:
                                continue
                            serial += 1
                            count += 1
                            offer(item, serial)
    ranked = []
    for _, _, item in heap:
        proposal = (np.asarray(item["center_work"]), np.radians(item["angle_deg"]), item["provenance"])
        exact_item = scorer.score(proposal, method, exact=True)
        if exact_item is not None:
            ranked.append(exact_item)
    ranked.sort(key=lambda item: -item["score"])
    unique = []
    for item in ranked:
        if not any(np.linalg.norm(np.asarray(item["center_work"]) - old["center_work"]) < scorer.thresholds["candidate_dedup"]
                   and abs(((item["angle_deg"] - old["angle_deg"] + 90) % 180) - 90) < 2 for old in unique):
            unique.append(item)
        if len(unique) >= config.top_k:
            break
    return count, unique


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
        proposals = (_local_proposals(initial_corners, view, lengths) if method == "local" else
                     _corner_proposals(corners, view["size"], lengths["corner_nudge"]) if method == "corner" else
                     _edge_proposals(lines, view["size"], scorer.center) if method == "edge" else
                     _mask_proposals(scorer, config))
        count, top = _rank(proposals, method, scorer, config)
        threshold = (config.min_corner_edge_support if method in ("corner", "local") else
                     config.min_single_edge_support if method == "edge" else 0)
        accepted_item = next((item for item in top if item["mask_coverage"] >= config.min_mask_coverage
                              and item["edge_support"] >= threshold), None)
        accepted = accepted_item is not None
        stages.append({"method": method, "candidate_count": count, "accepted": accepted, "top": top,
                       "accepted_index": top.index(accepted_item) if accepted else None})
        if accepted:
            chosen = accepted_item
            break
    success = chosen is not None
    if chosen is None:
        available = [stage["top"][0] for stage in stages if stage["top"]]
        chosen = max(available, key=lambda item: item["mask_coverage"]) if available else None
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
