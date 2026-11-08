"""Manually supplied rule inputs and directed-facing estimates, independent of SAM."""

from copy import deepcopy

import numpy as np

from components.homography import transform_points


def edge_headings(corners):
    corners = np.asarray(corners, dtype=float)
    directions = (corners + np.roll(corners, -1, axis=0)) / 2 - corners.mean(axis=0)
    return np.degrees(np.arctan2(directions[:, 1], directions[:, 0]))


class RuleState:
    def __init__(self):
        self.fronts = {}
        self.terrain = []

    @staticmethod
    def _source_ray(front, corners, edge, source_to_plane):
        if source_to_plane is not None:
            centre = corners.mean(axis=0)
            midpoint = (corners[edge] + corners[(edge + 1) % 4]) / 2
            front["source_ray"] = transform_points([centre, midpoint], np.linalg.inv(source_to_plane)).tolist()

    @staticmethod
    def _angle(front, source_to_plane):
        if source_to_plane is not None and front.get("source_ray") is not None:
            ray = transform_points(front["source_ray"], source_to_plane)
            delta = ray[1] - ray[0]
            return float(np.degrees(np.arctan2(delta[1], delta[0])))
        return front["angle_deg"]

    def set_front(self, object_id, tray, point_mm, frame_index, *, source_to_plane=None):
        corners = np.asarray(tray["corners_plane"], dtype=float)
        starts, delta = corners, np.roll(corners, -1, axis=0) - corners
        t = np.clip(((np.asarray(point_mm) - starts) * delta).sum(axis=1) / (delta * delta).sum(axis=1), 0, 1)
        edge = int(np.argmin(np.linalg.norm(starts + t[:, None] * delta - point_mm, axis=1)))
        self.fronts[object_id] = {"angle_deg": float(edge_headings(corners)[edge]), "parity": edge % 2,
                                  "frame_index": frame_index, "source": "manual"}
        self._source_ray(self.fronts[object_id], corners, edge, source_to_plane)

    def observe(self, prediction, frame_index, *, source_to_plane=None):
        unavailable = set(prediction.get("unavailable_ids", [])) | set(prediction.get("inactive_ids", []))
        for object_id, front in self.fronts.items():
            if object_id in unavailable:
                continue
            tray = prediction.get("trays", {}).get(object_id)
            if tray is None:
                continue
            angles = edge_headings(tray["corners_plane"])
            options = range(4) if front["parity"] is None else [front["parity"], front["parity"] + 2]
            reference = self._angle(front, source_to_plane)
            edge = min(options, key=lambda i: abs((angles[i] - reference + 180) % 360 - 180))
            source = front["source"] if front["frame_index"] == frame_index else "estimated_by_rectangle_continuity"
            front.update(angle_deg=float(angles[edge]), parity=edge % 2, frame_index=frame_index, source=source)
            self._source_ray(front, np.asarray(tray["corners_plane"]), edge, source_to_plane)

    def scene(self, roster, prediction, image_to_plane, board_size_mm, metadata, *, source_to_plane=None):
        if image_to_plane is None or board_size_mm is None:
            raise ValueError("Set real board dimensions (--board-size-in W D), or load metric calibration.")
        if roster is None or prediction is None:
            raise ValueError("Register unit masks and bind their types first.")
        units, warnings = [], []
        inactive = set(prediction.get("inactive_ids", []))
        unavailable = set(prediction.get("unavailable_ids", [])) | (roster.bindings.keys() - set(prediction["object_ids"]))
        for object_id in unavailable - inactive:
            warnings.append(f"{roster.bindings[object_id]} has no accepted tracking position; the registered scene is incomplete.")
        for object_id in prediction["object_ids"]:
            if object_id in unavailable or object_id in inactive:
                continue
            unit_id = roster.bindings.get(object_id)
            tray = prediction.get("trays", {}).get(object_id)
            if unit_id is None or tray is None:
                warnings.append(f"Mask {object_id} has no labelled tray; the registered scene is incomplete.")
                continue
            unit = roster.units[unit_id]
            profile = {**roster.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            corners = (transform_points(tray["corners_source"], source_to_plane).tolist()
                       if source_to_plane is not None and tray.get("corners_source") is not None else tray["corners_plane"])
            front = self.fronts.get(object_id)
            edge = None
            if front is not None:
                angles = edge_headings(corners)
                options = range(4) if front["parity"] is None else [front["parity"], front["parity"] + 2]
                reference = self._angle(front, source_to_plane)
                edge = min(options, key=lambda i: abs((angles[i] - reference + 180) % 360 - 180))
                if front["source"] != "manual":
                    warnings.append(f"{unit_id}: facing estimated from rectangle continuity; 180-degree turns are ambiguous.")
                    lengths = np.linalg.norm(np.roll(np.asarray(corners), -1, axis=0) - corners, axis=1)
                    if np.isclose(lengths[0], lengths[1], rtol=.01):
                        warnings.append(f"{unit_id}: a square base also has 90-degree facing ambiguity.")
            units.append({"unit_id": unit_id, "object_id": int(object_id), "corners_mm": corners,
                          "front_edge": edge, "height": profile.get("height"), "speed_in": profile.get("speed_in"),
                          "side": profile.get("side"), "unit_kind": profile.get("unit_kind"),
                          "special_rules": profile.get("special_rules", []),
                          "state": {"engaged": profile.get("engaged"), "wavering": profile.get("wavering")},
                          "facing_source": front["source"] if front else None})
        terrain = [{**item, "polygon_mm": (transform_points(item["polygon_source"], source_to_plane).tolist()
                                          if source_to_plane is not None and item.get("polygon_source") is not None else
                                          transform_points(item["polygon_image"], image_to_plane).tolist())}
                   for item in self.terrain]
        return {"ruleset": "kow4-mini", "board_size_mm": list(board_size_mm), "units": units, "terrain": terrain,
                "warnings": warnings, "snapshot": deepcopy(metadata)}

    def snapshot(self):
        return {"ruleset": "kow4-mini", "fronts": deepcopy(self.fronts), "terrain": deepcopy(self.terrain),
                "facing_assumption": "Rectangle axes remain associated and direction changes by less than 90 degrees between observations; square bases have additional ambiguity."}
