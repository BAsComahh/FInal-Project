"""Terrain, facing and unfinished terrain-marker drawing."""
import cv2
import numpy as np
from components.homography import transform_points

class SceneEditingView:
    def __init__(self, editor):
        self.editor = editor

    def draw_terrain(self, preview, view):
        scale = np.asarray(preview.shape[1::-1]) / np.asarray(view.current.frame.shape[1::-1])
        for item in view.rules.terrain:
            polygon = (transform_points(item["polygon_source"], view.board.homography["matrix"])
                       if item.get("polygon_source") is not None else np.asarray(item["polygon_image"]))
            points = np.rint(polygon * scale).astype(np.int32)
            cv2.polylines(preview, [points], True, (100, 180, 230), 1, cv2.LINE_AA)

    def draw_inputs(self, preview, view):
        scale = np.asarray(preview.shape[1::-1]) / np.asarray(view.current.frame.shape[1::-1])
        if self.editor.vertices:
            points = np.rint(np.asarray(self.editor.vertices) * scale).astype(np.int32)
            cv2.polylines(preview, [points], False, (0, 220, 255), 2, cv2.LINE_AA)
            for point in points:
                cv2.circle(preview, tuple(point), 4, (0, 220, 255), -1)
        if view.current.prediction is not None and view.board.image_to_plane is not None:
            inverse = np.linalg.inv(view.board.image_to_plane)
            unavailable = set(view.current.prediction.get("unavailable_ids", [])) | set(view.current.prediction.get("inactive_ids", []))
            for object_id, front in view.rules.fronts.items():
                if object_id in unavailable:
                    continue
                tray = view.current.prediction.get("trays", {}).get(object_id)
                if tray is None:
                    continue
                center = np.asarray(tray["center_plane"])
                length = min(np.linalg.norm(np.diff(np.asarray(tray["corners_plane"]), axis=0), axis=1)) * .6
                angle = np.radians(front["angle_deg"])
                points = transform_points([center, center + length * np.array([np.cos(angle), np.sin(angle)])], inverse) * scale
                a, b = np.rint(points).astype(int)
                pending = front.get("appearance", {}).get("recovery_phase") in ("pending", "failed")
                color = (70, 190, 245) if pending else (100, 245, 140)
                cv2.arrowedLine(preview, tuple(a), tuple(b), color, 2, cv2.LINE_AA, tipLength=.3)
