"""Owned Qt images built from published data; never mutate application arrays."""
from threading import Lock

import cv2
import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from components.homography import transform_points
from frontend.shared.layers import VideoLayers, QueryLayers


class BoardImages(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self._lock = Lock()
        self._image = QImage()

    def publish(self, frame):
        frame = np.ascontiguousarray(frame)
        height, width = frame.shape[:2]
        image = QImage(frame.data, width, height, frame.strides[0], QImage.Format_BGR888).copy()
        with self._lock:
            self._image = image

    def requestImage(self, image_id, size, requested_size):
        with self._lock:
            return QImage(self._image)


class BoardRenderer:
    def __init__(self):
        self._key = self._layers = self._selection = self._target = None
        self.query_layers = QueryLayers()

    def render(self, state, *, selected, masks, trays, corners=(), points=(), target=None, queries=None):
        size = state.current.frame.shape[1::-1]
        prediction = state.current.prediction
        key = (state.source_ref.generation, state.current.view_revision, selected, target, size, state.stage)
        if key != self._key:
            if self._layers is None or self._layers.size != size:
                self._layers = VideoLayers(size)
            labels = dict(state.units.bindings)
            self._selection = self._target = None
            if prediction is not None and state.stage == "playback":
                for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
                    if object_id in (selected, target):
                        yy, xx = np.nonzero(mask)
                        if len(xx):
                            bounds = (int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max()))
                            if object_id == selected:
                                self._selection = bounds
                            else:
                                self._target = bounds
            self._layers.update(prediction, size, labels)
            self._key = key
        frame = self._layers.render(state.current.frame, show_masks=masks, show_rectangles=trays)
        if self._selection is not None:
            x, y, right, bottom = self._selection
            cv2.rectangle(frame, (x - 4, y - 4), (right + 4, bottom + 4), (150, 100, 40), 5)
            cv2.rectangle(frame, (x - 4, y - 4), (right + 4, bottom + 4), (255, 255, 255), 2)
        if self._target is not None:
            x, y, right, bottom = self._target
            cv2.rectangle(frame, (x - 3, y - 3), (right + 3, bottom + 3), (160, 220, 100), 2)
        if queries is not None:
            self.query_layers.draw(frame, queries, state)
        if trays and prediction is not None:
            for object_id in prediction.get("trays", {}):
                front = state.rules.fronts.get(object_id)
                if front is not None and front.get("source_ray") is not None:
                    ray = np.rint(transform_points(front["source_ray"], state.board.homography["matrix"])).astype(int)
                    cv2.arrowedLine(frame, tuple(ray[0]), tuple(ray[1]), (70, 240, 160), 3, cv2.LINE_AA, tipLength=.3)
        for prompt in state.registration_prompts:
            if prompt["object_id"] == selected and state.stage == "register":
                point = tuple(np.rint(prompt["point"]).astype(int))
                cv2.drawMarker(frame, point, (90, 225, 85) if prompt["positive"] else (90, 80, 235), cv2.MARKER_CROSS, 16, 2)
        if corners:
            polygon = np.rint(list(corners.values())).astype(np.int32)
            cv2.polylines(frame, [polygon], True, (80, 215, 235), 3, cv2.LINE_AA)
            for name, point in corners.items():
                x, y = np.rint(point).astype(int)
                cv2.circle(frame, (x, y), 7, (255, 255, 255), -1)
                cv2.putText(frame, name, (x + 10, max(22, y - 12)), cv2.FONT_HERSHEY_SIMPLEX, .8, (80, 215, 235), 2)
        else:
            for point in points:
                cv2.circle(frame, tuple(np.rint(point).astype(int)), 7, (80, 215, 235), -1)
        return frame
