"""Shared preview sizing, image-coordinate conversion and topmost-mask hit testing."""
import numpy as np

class Viewport:
    def __init__(self, width_limit=960):
        if width_limit < 320:
            raise ValueError("preview-width must be at least 320")
        self.width_limit = width_limit

    def size(self, frame):
        height, width = frame.shape[:2]
        preview_width = min(self.width_limit, width)
        return preview_width, max(1, round(height * preview_width / width))

    @staticmethod
    def image_point(point, image_size, preview_size):
        return np.asarray(point) * np.asarray(image_size) / np.asarray(preview_size)

    @staticmethod
    def mask_at(x, y, presentation, preview_size):
        width, height = preview_size
        if presentation.current.prediction is None or not (0 <= x < width and 0 <= y < height):
            return None
        source_height, source_width = presentation.current.frame.shape[:2]
        px, py = min(source_width - 1, int(x * source_width / width)), min(source_height - 1, int(y * source_height / height))
        # The last mask is drawn on top when masks overlap.
        for object_id, mask in reversed(list(zip(presentation.current.prediction["object_ids"], presentation.current.prediction["masks"]))):
            if mask[py, px]:
                return object_id
        return None
