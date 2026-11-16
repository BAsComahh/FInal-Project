"""Disposable SAM seed and EdgeTAM candidate; no business IDs or history writes."""
from copy import copy
from threading import Event

import cv2
import numpy as np


class RecoveryCandidate:
    def __init__(self):
        self.cancelled = Event()
        self.backend = None
        self.prediction = None
        self.seed_frame = self.seed_point = None
        self.seed_prompt_added = False
        self.requires_continuity = False

    def seed_mask(self, tracker, frame, mask, source_frame):
        self._check()
        if not mask.any():
            raise ValueError("Recovery seed mask is empty")
        backend = copy(tracker)
        backend.session = None
        backend.reset()
        self.backend = backend
        self.prediction = backend.initialize(frame, [1], mask[None], source_frame=source_frame)
        if not self.prediction["masks"][0].any():
            self.cancel()
            raise ValueError("Edge returned an empty recovery seed")
        self.seed_frame = source_frame
        # A later negative point on this frame still needs a foreground anchor.
        y, x = np.unravel_index(cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3).argmax(), mask.shape)
        self.seed_point = [float(x), float(y)]
        self._check()
        return self.prediction

    def cancel(self):
        self.cancelled.set()

    def release(self):
        if self.backend is not None and getattr(self.backend, "session", None) is not None:
            if self.backend.session.processed_frames is not None:
                self.backend.session.processed_frames.clear()
            self.backend.session.reset_inference_session()
            self.backend.session = None

    def _check(self):
        if self.cancelled.is_set():
            self.release()
            raise ValueError("Recovery draft was cancelled")

    def seed(self, predictor, tracker, frame, point, source_frame):
        self._check()
        sam = copy(predictor)
        sam.reset()
        try:
            initial = sam.click(frame, point, object_id=1, positive=True, source_frame=source_frame)
            self._check()
            if not initial["masks"][0].any():
                raise ValueError("SAM returned no candidate. Clear / Retry on the target.")
            backend = copy(tracker)
            backend.session = None
            backend.reset()
            self.backend = backend
            self.prediction = backend.initialize(frame, [1], initial["masks"][:1], source_frame=source_frame)
            self.seed_frame, self.seed_point = source_frame, list(point)
            self._check()
            return self.prediction
        finally:
            sam.reset()

    def advance(self, frame, source_frame):
        self._check()
        if self.backend is None:
            raise ValueError("Add a positive point to create a candidate first")
        if source_frame < self.backend.source_frame:
            raise ValueError("Candidate is newer than the clicked frame. Retry on the current view.")
        if source_frame > self.backend.source_frame:
            self.prediction = self.backend.propagate(frame, source_frame=source_frame)
        if self.requires_continuity and not self.prediction["masks"][0].any():
            self.cancel()
            self.release()
            raise ValueError("Recovery candidate disappeared. Clear / Retry on the current frame.")
        self._check()
        return self.prediction

    def correct(self, frame, point, positive, source_frame):
        self.advance(frame, source_frame)
        points, labels = [list(point)], [int(positive)]
        if source_frame == self.seed_frame and not self.seed_prompt_added:
            points.insert(0, self.seed_point)
            labels.insert(0, 1)
        self.prediction = self.backend.correct_points(frame, points, labels, source_frame=source_frame)
        self.seed_prompt_added = True
        self._check()
        return self.prediction
