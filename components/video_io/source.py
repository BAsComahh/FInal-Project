"""Read local video frames and timestamps independently of model inference."""

import json
import math
from pathlib import Path

import cv2


class VideoSource:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Video not found: {self.path}")
        self.capture = cv2.VideoCapture(str(self.path))
        self.fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not self.capture.isOpened() or not math.isfinite(self.fps) or self.fps <= 0 or self.frame_count < 1:
            self.close()
            raise ValueError(f"Cannot read video timeline: {self.path}")
        self.duration = self.frame_count / self.fps
        self.frame_index = -1
        self.frame = None
        self.provenance = {}
        sidecar = self.path.with_suffix(".source.json")
        if sidecar.is_file():
            try:
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self.provenance = payload
            except (OSError, ValueError):
                pass

    def read_at(self, seconds):
        if not math.isfinite(seconds) or not 0 <= seconds < self.duration:
            raise ValueError(f"Video time must be in [0, {self.duration:g}) seconds")
        return self.read_frame(min(self.frame_count - 1, int(seconds * self.fps)))

    def read_frame(self, index):
        index = min(self.frame_count - 1, max(0, int(index)))
        next_index = self.frame_index + 1
        if next_index <= index < next_index + self.fps:
            for _ in range(index - next_index):
                if not self.capture.grab():
                    raise ValueError(f"Cannot skip to video frame {index}")
        else:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        success, frame = self.capture.read()
        if not success:
            raise ValueError(f"Cannot decode video frame {index}")
        self.frame_index = index
        self.frame = frame
        return frame

    def metadata(self):
        result = {"type": "video", "video": str(self.path), "frame_index": self.frame_index,
                  "timestamp_seconds": self.frame_index / self.fps, "fps": self.fps}
        offset = self.provenance.get("source_start_seconds")
        if isinstance(offset, (int, float)) and math.isfinite(offset):
            result["source_timestamp_seconds"] = offset + result["timestamp_seconds"]
        if "source_url" in self.provenance:
            result["source_url"] = self.provenance["source_url"]
        return result

    def close(self):
        self.capture.release()
