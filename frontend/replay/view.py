"""Historical source images projected onto the millimetre board with unit IDs."""
import textwrap

import cv2
import numpy as np

from ..shared.drawing import draw_text


class ReplayView:
    def __init__(self, controller):
        self.controller = controller
        self.buttons = []

    def render(self, preview_size):
        replay = self.controller
        width, height = max(320, preview_size[0]), max(220, preview_size[1])
        scene = replay.scene
        unavailable = []
        valid = []
        projected = None
        background_note = scene.get("background_note", "") if scene is not None else ""
        if scene is not None:
            dimensions = np.asarray(scene["board_size_mm"], dtype=float)
            scale = min((width - 40) / dimensions[0], (height - 62) / dimensions[1])
            size = np.maximum(1, np.rint(dimensions * scale).astype(int))
            background = scene.get("background")
            if background is not None:
                try:
                    matrix = np.asarray(scene["calibration"]["board"]["image_to_plane"], dtype=float)
                    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
                        raise ValueError("Invalid image calibration")
                    projected = cv2.warpPerspective(background, np.diag([scale, scale, 1.0]) @ matrix,
                                                    (int(size[0]) + 1, int(size[1]) + 1))
                except (KeyError, TypeError, ValueError, cv2.error):
                    background_note = "Step image alignment unavailable."
        if scene is not None:
            for unit_id, unit in scene["units"].items():
                corners = unit.get("corners_mm")
                try:
                    points = np.asarray(corners, dtype=float) if corners is not None else np.empty((0, 2))
                except (TypeError, ValueError):
                    points = np.empty((0, 2))
                if (unit.get("active", True) and unit.get("position_status") == "available"
                        and points.shape == (4, 2) and np.isfinite(points).all()):
                    valid.append((unit_id, points))
                else:
                    reason = "inactive" if not unit.get("active", True) else "unavailable"
                    unavailable.append(f"{unit_id} ({reason})")
        lines = []
        if replay.steps:
            step = replay.steps[replay.selected]
            lines.append(f"Step {replay.selected}/{len(replay.steps) - 1}: "
                         f"{step['label']} {step['unit_id'] or ''} | end {step['end_timestamp_seconds']:.2f}s")
        else:
            lines.append("Replay | Loading history..." if replay.loading else "Replay")
        if scene is not None:
            observation = scene["observation"]
            geometry = observation.get("observation_timestamp_seconds")
            record = observation.get("timestamp_seconds")
            stamp = lambda value: "unknown" if value is None else f"{value:.2f}s"
            lines.append(f"Geometry {stamp(geometry)} | state record {stamp(record)} | calibration v{observation['calibration_version']}")
        elif replay.steps and not replay.error:
            lines.append("Loading selected board...")
        if replay.has_index:
            lines.append("Refresh to include newly completed actions.")
            if len(replay.steps) == 1:
                lines.append("No completed moves or rotations yet.")
        if replay.loading and replay.has_index:
            lines.append("Refreshing history; navigation remains available.")
        if replay.error:
            lines.append("Replay error: " + replay.error)
        if unavailable:
            lines.append("No position: " + ", ".join(unavailable))
        if background_note:
            lines.append(background_note)
        wrapped = [part for line in lines if line for part in textwrap.wrap(line, max(30, width // 7))]
        columns = 4 if width >= 640 else 2
        rows = (4 + columns - 1) // columns
        footer = 16 + rows * 36 + 22 * len(wrapped) + 24
        panel = np.full((height + footer, width, 3), 30, dtype=np.uint8)
        draw_text(panel, "HISTORICAL BOARD (mm)", (14, 22), size=15)
        if scene is not None:
            origin = np.array(((width - size[0]) // 2, 42 + (height - 62 - size[1]) // 2))
            board = projected if projected is not None else np.full((size[1] + 1, size[0] + 1, 3), (45, 57, 45), dtype=np.uint8)
            cv2.rectangle(board, (0, 0), tuple(size), (125, 145, 125), 1)
            highlight = scene["step"]["unit_id"]
            for unit_id, points in valid:
                polygon = np.rint(points * scale).astype(np.int32)
                color = (70, 215, 250) if unit_id == highlight else (215, 210, 150)
                cv2.polylines(board, [polygon], True, color, 3 if unit_id == highlight else 2, cv2.LINE_AA)
                centre = np.clip(np.rint(polygon.mean(axis=0)).astype(int), (2, 14), np.maximum((2, 14), size - (12, 3)))
                draw_text(board, unit_id, tuple(centre), color, size=14)
            panel[origin[1]:origin[1] + size[1] + 1, origin[0]:origin[0] + size[0] + 1] = board
            draw_text(panel, f"{dimensions[0]:g} x {dimensions[1]:g} mm", (14, height - 8), size=12)
        else:
            draw_text(panel, "Board unavailable" if replay.error else "Loading historical board...", (16, height // 2), size=15)
        labels = (("previous", "Previous [Left / A]"), ("next", "Next [Right / D]"),
                  ("refresh", "Refresh"), ("live", "Back to Live [Esc]"))
        self.buttons = []
        button_width = (width - 10 * (columns + 1)) // columns
        for i, (action, label) in enumerate(labels):
            x, y = 10 + i % columns * (button_width + 10), height + 8 + i // columns * 36
            rect = (x, y, x + button_width, y + 28)
            cv2.rectangle(panel, rect[:2], rect[2:], (65, 65, 65), -1)
            draw_text(panel, label, (x + 5, y + 19), size=max(10, min(13, button_width // 12)))
            self.buttons.append((rect, action))
        for i, line in enumerate(wrapped):
            draw_text(panel, line, (10, height + 16 + rows * 36 + i * 22),
                      (110, 170, 245) if line.startswith("Replay error") else (225, 225, 225), size=12)
        return panel
