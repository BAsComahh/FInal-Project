"""Cached overlays for accepted geometry queries."""

import cv2
import numpy as np

from components.homography import transform_points


class QueryLayers:
    """Screen overlays cached only for the matching accepted geometry observation."""
    def __init__(self):
        self._key = self._overlay = None

    def draw(self, preview, queries, view):
        if queries.result is None or queries.result_request is None or not queries.result_current(view):
            return
        request, result = queries.result_request, queries.result
        key = (request["epoch"], request["view_revision"], preview.shape)
        if key != self._key:
            self._key = key
            self._overlay = np.zeros_like(preview)
            scale = np.asarray(preview.shape[1::-1]) / np.asarray(view.current.frame.shape[1::-1])
            inverse = np.linalg.inv(request["image_to_plane"])
            project = lambda points: np.rint(transform_points(points, inverse) * scale).astype(np.int32)
            line = result.get("line_mm")
            if "point_a_mm" in result:
                line = [result["point_a_mm"], result["point_b_mm"]]
            if line is not None:
                points = project(line)
                color = (153, 224, 96) if result.get("status") in ("ok", "clear") else (80, 145, 255)
                cv2.line(self._overlay, tuple(points[0]), tuple(points[1]), (18, 26, 34), 5, cv2.LINE_AA)
                cv2.line(self._overlay, tuple(points[0]), tuple(points[1]), color, 2, cv2.LINE_AA)
                for point in points:
                    cv2.circle(self._overlay, tuple(point), 6, (18, 26, 34), -1, cv2.LINE_AA)
                    cv2.circle(self._overlay, tuple(point), 4, color, -1, cv2.LINE_AA)
            poses = result.get("poses", ())
            if poses:
                for index in np.linspace(0, len(poses) - 1, min(12, len(poses)), dtype=int):
                    poly = [project(poses[index]["corners_mm"])]
                    cv2.polylines(self._overlay, poly, True, (18, 26, 34), 3, cv2.LINE_AA)
                    cv2.polylines(self._overlay, poly, True, (240, 190, 60), 1, cv2.LINE_AA)
                for point in project([pose["center_mm"] for pose in poses]):
                    cv2.circle(self._overlay, tuple(point), 4, (18, 26, 34), -1, cv2.LINE_AA)
                    cv2.circle(self._overlay, tuple(point), 2, (255, 220, 100), -1, cv2.LINE_AA)
        pixels = self._overlay.any(axis=2)
        preview[pixels] = (preview[pixels] * .4 + self._overlay[pixels] * .6).astype(np.uint8)
