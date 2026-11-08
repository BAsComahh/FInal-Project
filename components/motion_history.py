"""Sample-based translation/rotation events, independent of tracking models and UI."""

from copy import deepcopy
from math import atan2, degrees, hypot, isfinite

import numpy as np
from components.homography import transform_points

_EPSILON = 1e-9
SOURCE_COORDINATE_BASIS = "source_image_pixels"


class MotionRecorder:
    def __init__(self, *, position_tolerance_mm=10.0, rotation_tolerance_deg=10.0, settle_seconds=5.0):
        for name, value in (("position tolerance", position_tolerance_mm),
                            ("rotation tolerance", rotation_tolerance_deg), ("settle time", settle_seconds)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError(f"Motion {name} must be finite and positive")
        if rotation_tolerance_deg >= 45:
            raise ValueError("Motion rotation tolerance must be less than 45 degrees (square-axis symmetry)")
        self.position_tolerance_mm = float(position_tolerance_mm)
        self.rotation_tolerance_deg = float(rotation_tolerance_deg)
        self.settle_seconds = float(settle_seconds)
        self.reset()

    def reset(self):
        self._units = {}
        self._seen = {}
        self._next_id = 0

    @property
    def has_active(self):
        return any(state[kind]["event"] is not None for state in self._units.values()
                   for kind in ("translation", "rotation"))

    @staticmethod
    def _pose(unit, entry, matrix=None, inverse=None):
        corners = unit.get("corners_mm")
        try:
            if matrix is not None and unit.get("corners_source") is not None:
                corners = transform_points(unit["corners_source"], matrix).tolist()
            if len(corners) != 4 or any(len(point) != 2 for point in corners):
                return None
            corners = [[float(value) for value in point] for point in corners]
            if any(not isfinite(value) for point in corners for value in point):
                return None
            edges = [[corners[(i + 1) % 4][j] - corners[i][j] for j in (0, 1)] for i in (0, 1)]
            lengths = [hypot(*edge) for edge in edges]
            if min(lengths) <= 0:
                return None
        except (TypeError, ValueError, OverflowError):
            return None
        square = abs(lengths[0] - lengths[1]) <= 0.01 * max(lengths) + _EPSILON
        period = 90 if square else 180
        edge = edges[0 if lengths[0] >= lengths[1] else 1]
        angle = degrees(atan2(edge[1], edge[0])) % period
        pose = {"sequence": entry["sequence"], "frame_index": entry["observation_frame_index"],
                "timestamp_seconds": entry["observation_timestamp_seconds"],
                "source": deepcopy(entry["observation_source"]), "calibration_version": entry["calibration_version"],
                "center_mm": [sum(point[j] for point in corners) / 4 for j in (0, 1)],
                "corners_mm": corners, "axis_deg": angle, "axis_period_deg": period,
                "unwrapped_axis_deg": angle, "axis_edge_index": 0 if lengths[0] >= lengths[1] else 1}
        if matrix is not None:
            try:
                pose["corners_source"] = (transform_points(corners, inverse).tolist()
                                           if unit.get("corners_source") is None else deepcopy(unit["corners_source"]))
                centre = unit.get("center_source")
                pose["center_source"] = (transform_points(pose["center_mm"], inverse).tolist()
                                           if centre is None else list(centre))
                pose["center_mm"] = transform_points(pose["center_source"], matrix).tolist()
            except (TypeError, ValueError, OverflowError):
                return None
            pose["source_to_plane"] = matrix.tolist()
            pose["source_image_size"] = deepcopy(entry["observation_source"].get("source_image_size"))
        return pose

    @staticmethod
    def _compatible(original, current):
        return (original.get("corners_source") is not None and current.get("source_to_plane") is not None
                and original.get("source_image_size") == current.get("source_image_size")
                and original["source"].get("video") == current["source"].get("video"))

    @classmethod
    def _center_in_frame(cls, original, current):
        if cls._compatible(original, current):
            return transform_points(original["center_source"], current["source_to_plane"])
        return original["center_mm"]

    @classmethod
    def _axis_in_frame(cls, original, current):
        if cls._compatible(original, current):
            points = transform_points(original["corners_source"], current["source_to_plane"])
            edges = np.roll(points, -1, axis=0)[:2] - points[:2]
            delta = edges[int(np.argmax(np.linalg.norm(edges, axis=1)))]
            return degrees(atan2(delta[1], delta[0])) % current["axis_period_deg"]
        return original["axis_deg"]

    @classmethod
    def _touch(cls, event, entry):
        event["updated_sequence"] = entry["sequence"]
        event["recorded_source"] = deepcopy(entry["source"])
        event["last_observed_sequence"] = entry["sequence"]
        start, end = event["start"], event["end"]
        event["calibration_version"] = end["calibration_version"]
        if event["kind"] == "translation":
            event["net_displacement_mm"] = hypot(*(b - a for a, b in zip(cls._center_in_frame(start, end), end["center_mm"])))
        else:
            event["rotation_deg_estimate"] = end["unwrapped_axis_deg"] - start["unwrapped_axis_deg"]

    def _advance(self, unit_id, kind, channel, previous, pose, entry):
        anchor = channel["anchor"]
        if kind == "translation":
            change = hypot(*(b - a for a, b in zip(self._center_in_frame(anchor, pose), pose["center_mm"])))
            tolerance = self.position_tolerance_mm
        else:
            change = abs(pose["unwrapped_axis_deg"] - anchor["unwrapped_axis_deg"])
            tolerance = self.rotation_tolerance_deg
        event = channel["event"]
        if change > tolerance + _EPSILON:
            if event is None:
                self._next_id += 1
                event = {"event_id": f"E{self._next_id}", "unit_id": unit_id, "kind": kind,
                         "status": "ongoing", "calibration_version": pose["calibration_version"],
                         "start": deepcopy(previous), "end": deepcopy(pose),
                         "detected_source": deepcopy(pose["source"]), "confirmed_source": None,
                         "settle_seconds": self.settle_seconds, "tolerance": tolerance,
                         "estimated": True, "start_estimate": "previous_valid_observation"}
                if self._compatible(previous, pose):
                    event["coordinate_basis"] = SOURCE_COORDINATE_BASIS
                if kind == "rotation":
                    event.update(orientation_basis="unoriented_tray_axis", axis_period_deg=pose["axis_period_deg"])
                channel["event"] = event
            event["end"] = deepcopy(pose)
            channel["anchor"] = pose
        elif event is not None and pose["timestamp_seconds"] - anchor["timestamp_seconds"] + _EPSILON >= self.settle_seconds:
            event["end"] = deepcopy(anchor)
            event.update(status="completed", confirmed_source=deepcopy(pose["source"]),
                         confirmed_sequence=entry["sequence"])
            channel["event"] = None
            channel["anchor"] = pose
        if event is not None:
            self._touch(event, entry)
            return deepcopy(event)
        return None

    def _interrupt(self, unit_id, entry, reason):
        state = self._units.pop(unit_id, None)
        updates = []
        if state is not None:
            for kind in ("translation", "rotation"):
                event = state[kind]["event"]
                if event is not None:
                    event.update(status="interrupted", end=deepcopy(state["previous"]),
                                 interruption_reason=reason, interrupted_source=deepcopy(entry["source"]))
                    self._touch(event, entry)
                    event["last_observed_sequence"] = state["previous"]["sequence"]
                    updates.append(deepcopy(event))
        return updates

    def interrupt_all(self, entry, reason):
        updates = []
        for unit_id in list(self._units):
            updates.extend(self._interrupt(unit_id, entry, reason))
        return updates

    def observe(self, entry, *, source_to_plane=None):
        if entry["kind"] not in ("registration", "observation", "recalibration"):
            return []
        stamp, frame = entry["observation_timestamp_seconds"], entry["observation_frame_index"]
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not isfinite(stamp) or stamp < 0:
            raise ValueError("Motion observations require finite non-negative source seconds")
        version = entry["calibration_version"]
        matrix = inverse = None
        if source_to_plane is not None:
            matrix = np.asarray(source_to_plane, dtype=float)
            if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
                raise ValueError("Motion source mapping must be a finite 3x3 matrix")
            inverse = np.linalg.inv(matrix)
        updates = []
        for unit_id, unit in entry["units"].items():
            seen = self._seen.get(unit_id)
            if seen is not None and (version < seen[0] or frame < seen[1] or stamp < seen[2]
                                     or (version == seen[0] and frame == seen[1])):
                continue
            self._seen[unit_id] = (version, frame, stamp)
            if not unit.get("active", True):
                reason = "removed"
            elif unit.get("tracking_status") == "failed":
                reason = "tracking_failure"
            elif unit.get("visibility") is False:
                reason = "mask_missing"
            elif unit.get("position_status") != "available" or unit.get("tracking_status") not in (None, "tracking"):
                reason = "geometry_unavailable"
            else:
                reason = None
            pose = None if reason else self._pose(unit, entry, matrix, inverse)
            if pose is None:
                updates.extend(self._interrupt(unit_id, entry, reason or "geometry_unavailable"))
                continue
            state = self._units.get(unit_id)
            if state is not None and seen is not None and version != seen[0]:
                if not self._compatible(state["previous"], pose):
                    updates.extend(self._interrupt(unit_id, entry, "recalibration"))
                    state = None
                elif frame <= seen[1]:
                    continue
            if state is not None and self._compatible(state["previous"], pose):
                # The same physical tray keeps its symmetry even when a new
                # calibration changes its apparent edge-length ratio.
                pose["axis_period_deg"] = state["previous"]["axis_period_deg"]
                pose["axis_deg"] = self._axis_in_frame(pose, pose)
            if state is not None and state["previous"]["axis_period_deg"] != pose["axis_period_deg"]:
                updates.extend(self._interrupt(unit_id, entry, "geometry_basis_changed"))
                state = None
            if state is None:
                self._units[unit_id] = {"previous": pose, "translation": {"anchor": pose, "event": None},
                                        "rotation": {"anchor": pose, "event": None}}
                continue
            previous = state["previous"]
            period = pose["axis_period_deg"]
            delta = (pose["axis_deg"] - self._axis_in_frame(previous, pose) + period / 2) % period - period / 2
            pose["unwrapped_axis_deg"] = previous["unwrapped_axis_deg"] + delta
            for kind in ("translation", "rotation"):
                event = self._advance(unit_id, kind, state[kind], previous, pose, entry)
                if event is not None:
                    updates.append(event)
            state["previous"] = pose
        return updates
