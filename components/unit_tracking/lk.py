"""Local LK/RANSAC experiment; failed tracks retain their last accepted pose."""

from dataclasses import dataclass

import cv2
import numpy as np

from components.boundary_detection.scale import percent_to_length


@dataclass
class LKConfig:
    max_points: int = 80
    min_points: int = 6
    fb_tolerance_pct: float = 3
    ransac_tolerance_pct: float = 3
    feature_spacing_pct: float = 5
    min_flow_ratio: float = 0.6
    min_inlier_ratio: float = 0.65
    min_point_area_ratio: float = 0.04
    max_scale_change: float = 0.05
    min_appearance_correlation: float = 0.55

    def validate(self):
        for key in ("max_points", "min_points"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 3:
                raise ValueError(f"{key} must be an integer >= 3")
        if self.min_points > self.max_points:
            raise ValueError("min_points must not exceed max_points")
        for key in ("fb_tolerance_pct", "ransac_tolerance_pct", "feature_spacing_pct"):
            percent_to_length(getattr(self, key), 1, name=key)
        for key in ("min_flow_ratio", "min_inlier_ratio", "min_point_area_ratio", "max_scale_change",
                    "min_appearance_correlation"):
            value = getattr(self, key)
            if isinstance(value, bool) or not np.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{key} must be finite and in (0, 1]")


def _gray(frame):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be a uint8 BGR image")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _short_side(corners):
    return float(np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1).min())


def _features(gray, corners, config):
    mask = np.zeros(gray.shape, np.uint8)
    cv2.fillConvexPoly(mask, np.rint(corners).astype(np.int32), 255)
    return cv2.goodFeaturesToTrack(gray, config.max_points, qualityLevel=0.02,
                                  minDistance=percent_to_length(config.feature_spacing_pct, _short_side(corners)),
                                  mask=mask, blockSize=3)


def _patch(gray, corners):
    sides = np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1)
    width, height = 96, max(8, min(384, round(96 * sides[1] / sides[0])))
    target = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    matrix = cv2.getPerspectiveTransform(corners.astype(np.float32), target)
    return cv2.warpPerspective(gray, matrix, (width, height))


class UnitTracker:
    """Track continuous visible motion; reinitialize explicitly after uncertainty.

    `tracked` is a heuristic acceptance state, not an identity or visibility
    guarantee. No mask propagation, automatic recovery or reference updates.
    """

    def __init__(self, config=None):
        self.config = config or LKConfig()
        self.config.validate()
        self.states = {}
        self.frame_index = None
        self.image_shape = None

    def initialize(self, frame, units, *, source_frame_index=0):
        gray = _gray(frame)
        states = {}
        for row in units:
            unit_id = row.get("unit_id")
            corners = np.asarray(row.get("corners_image"), dtype=float)
            if not isinstance(unit_id, str) or not unit_id.strip() or unit_id in states:
                raise ValueError("Initialization needs unique, non-empty unit_id strings")
            if (corners.shape != (4, 2) or not np.isfinite(corners).all()
                    or not cv2.isContourConvex(corners.astype(np.float32)) or _short_side(corners) < 1):
                raise ValueError(f"{unit_id}: expected four cyclic, convex image corners")
            if (corners < 0).any() or (corners[:, 0] > gray.shape[1] - 1).any() or (corners[:, 1] > gray.shape[0] - 1).any():
                raise ValueError(f"{unit_id}: initialization is outside the image")
            points = _features(gray, corners, self.config)
            enough = points is not None and len(points) >= self.config.min_points
            states[unit_id] = {"corners": corners.copy(), "gray": gray, "points": points,
                               "template": _patch(gray, corners), "pose_frame_index": int(source_frame_index),
                               "status": "initialized" if enough else "uncertain",
                               "reason": "manual geometry seed" if enough else "insufficient initial texture",
                               "quality_signals": {"initial_point_count": 0 if points is None else len(points)}}
        if not states:
            raise ValueError("Initialization needs at least one unit")
        self.states, self.frame_index, self.image_shape = states, int(source_frame_index), gray.shape
        return self.observations()

    def observations(self):
        return [{"unit_id": unit_id, "source_frame_index": self.frame_index,
                 "pose_frame_index": state["pose_frame_index"], "status": state["status"],
                 "reason": state["reason"], "corners_image": state["corners"].tolist(),
                 "quality_signals": dict(state["quality_signals"])} for unit_id, state in self.states.items()]

    def update(self, frame, *, source_frame_index):
        gray = _gray(frame)
        if self.frame_index is None or gray.shape != self.image_shape:
            raise ValueError("Initialize the tracker with matching image dimensions first")
        if source_frame_index <= self.frame_index:
            raise ValueError("Source frame indices must increase")
        self.frame_index = int(source_frame_index)
        for state in self.states.values():
            if state["status"] == "uncertain":
                continue
            reason = self._update_one(gray, state)
            if reason is not None:
                state.update(status="uncertain", reason=reason)
        return self.observations()

    def _update_one(self, gray, state):
        config, corners, points = self.config, state["corners"], state["points"]
        short = _short_side(corners)
        padding = np.linalg.norm(corners[2] - corners[0]) * 0.5
        low = np.maximum(0, np.floor(corners.min(axis=0) - padding).astype(int))
        high = np.minimum(gray.shape[::-1], np.ceil(corners.max(axis=0) + padding).astype(int) + 1)
        x0, y0 = low
        x1, y1 = high
        previous = state["gray"][y0:y1, x0:x1]
        current = gray[y0:y1, x0:x1]
        origin = low.astype(np.float32)
        p0 = points - origin
        p1, forward, _ = cv2.calcOpticalFlowPyrLK(previous, current, p0, None, winSize=(21, 21), maxLevel=3)
        if p1 is None:
            return "optical flow failed"
        back, backward, _ = cv2.calcOpticalFlowPyrLK(current, previous, p1, None, winSize=(21, 21), maxLevel=3)
        if back is None:
            return "backward flow failed"
        error = np.linalg.norm((back - p0).reshape(-1, 2), axis=1)
        good = ((forward.ravel() != 0) & (backward.ravel() != 0) & np.isfinite(error)
                & (error <= percent_to_length(config.fb_tolerance_pct, short)))
        state["quality_signals"] = {"point_count": len(points), "flow_pass_ratio": float(good.mean())}
        if good.sum() < config.min_points or good.mean() < config.min_flow_ratio:
            return "insufficient forward/backward-consistent points"
        old = p0.reshape(-1, 2)[good] + origin
        new = p1.reshape(-1, 2)[good] + origin
        matrix, inliers = cv2.estimateAffinePartial2D(
            old, new, method=cv2.RANSAC, ransacReprojThreshold=percent_to_length(config.ransac_tolerance_pct, short))
        if matrix is None or inliers is None or not np.isfinite(matrix).all():
            return "rigid motion fit failed"
        inliers = inliers.ravel().astype(bool)
        scale = float(np.linalg.norm(matrix[:, 0]))
        state["quality_signals"].update(inlier_ratio=float(inliers.mean()), scale=scale)
        if inliers.sum() < config.min_points or inliers.mean() < config.min_inlier_ratio:
            return "inconsistent point motion"
        if abs(scale - 1) > config.max_scale_change:
            return "scale changed; fixed-base assumption failed"
        area_ratio = float(cv2.contourArea(cv2.convexHull(old[inliers])) / cv2.contourArea(corners.astype(np.float32)))
        state["quality_signals"]["point_area_ratio"] = area_ratio
        if area_ratio < config.min_point_area_ratio:
            return "points cover too little of the unit"
        rotation = matrix[:, :2] / scale
        candidate = (corners - old[inliers].mean(axis=0)) @ rotation.T + new[inliers].mean(axis=0)
        if ((candidate < 0).any() or (candidate[:, 0] > gray.shape[1] - 1).any()
                or (candidate[:, 1] > gray.shape[0] - 1).any()):
            return "geometry left the image"
        patch = _patch(gray, candidate)
        if patch.shape != state["template"].shape:
            patch = cv2.resize(patch, state["template"].shape[::-1])
        correlation = (float(cv2.matchTemplate(patch, state["template"], cv2.TM_CCOEFF_NORMED)[0, 0])
                       if min(patch.std(), state["template"].std()) > 1 else -1)
        state["quality_signals"]["appearance_correlation"] = correlation
        if not np.isfinite(correlation) or correlation < config.min_appearance_correlation:
            return "initial appearance no longer matches"
        fresh = _features(gray, candidate, config)
        if fresh is None or len(fresh) < config.min_points:
            return "insufficient texture for next observation"
        state.update(corners=candidate, gray=gray, points=fresh, pose_frame_index=self.frame_index,
                     status="tracked", reason="LK, geometry and appearance checks passed")
        return None
