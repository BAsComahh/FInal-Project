"""First-frame corner review, manual correction and table dimension confirmation."""

from concurrent.futures import ThreadPoolExecutor
from textwrap import wrap

import cv2
import numpy as np

from components.homography.geometry import CORNER_NAMES, order_corners
from .annotation_panel import draw_text


class TableSetup:
    def __init__(self, frame, *, board_size_in):
        self.frame = frame.copy()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="table-boundary")
        self.future = None
        self.corners = None
        self.points = []
        self.confirmed = False
        self.buttons = []
        self.board_size_in = tuple(board_size_in)
        self.size_values = [f"{value:g}" for value in board_size_in]
        self.size_focus = 0
        self.size_select_all = True
        self.size_fields = []
        self.corner_mode = None
        self.start_detection()

    def start_detection(self):
        if self.future is not None:
            self.note = "Boundary detection is still running. Manual selection is available."
            return
        self.mode = "detecting"
        self.corners = None
        self.points.clear()
        self.note = "Detecting the table on the first frame..."
        self.future = self.executor.submit(self._detect)

    def _detect(self):
        from components.boundary_detection.table import detect_table

        return detect_table(self.frame)

    def poll(self):
        if self.future is None or not self.future.done():
            return False
        future, self.future = self.future, None
        try:
            result = future.result()
        except Exception as error:
            result = {"success": False, "reason": str(error)}
        # Choosing manual input supersedes any still-running automatic result.
        if self.mode != "detecting" or self.confirmed:
            return False
        if result["success"]:
            self.corners = result["corners"]
            self.mode = "review"
            self.note = "Check the four corner markers. Continue to confirm the table dimensions."
        else:
            self.manual()
            self.note = "Auto detection did not find four usable corners. Select the corners manually, in any order."
        return True

    def manual(self):
        self.mode = "manual"
        self.points.clear()
        self.corners = None
        self.note = "Click four corners in any order. Ctrl+Z / U / right click undoes the last point."

    def undo(self):
        if self.mode == "manual":
            if self.points:
                self.points.pop()
            self.corners = None
            self.note = f"{len(self.points)} / 4 corners selected. Continue in any order."

    def confirm(self):
        if self.corners is None:
            self.note = "Select four valid corners before confirming."
            return
        if self.mode != "dimensions":
            self.corner_mode = self.mode
            self.mode = "dimensions"
            self.size_focus = 0
            self.size_select_all = True
            self.note = "Length spans TL to TR; width spans TL to BL. Enter the table size in inches."
            return
        try:
            size = tuple(float(value) for value in self.size_values)
            if not np.isfinite(size).all() or min(size) <= 0:
                raise ValueError
        except ValueError:
            self.note = "Enter a positive, finite number in both fields."
            return
        self.board_size_in = size
        self.confirmed = True

    def action(self, action):
        if action == "confirm":
            self.confirm()
        elif action in ("manual", "clear"):
            self.manual()
        elif action == "auto":
            self.start_detection()
        elif action == "undo":
            self.undo()
        elif action == "back" and self.mode == "dimensions":
            self.mode = self.corner_mode
            self.note = "Check the corner labels. Continue to confirm dimensions, or correct the corners."

    def on_key(self, key):
        if self.mode == "dimensions":
            if key in (13, 10, ord("c"), ord("C")):
                self.confirm()
            elif key in (ord("b"), ord("B")):
                self.action("back")
            elif key == 9:
                self.size_focus = 1 - self.size_focus
                self.size_select_all = True
            elif key == 1:
                self.size_select_all = True
            elif key in (8, 127):
                value = self.size_values[self.size_focus]
                self.size_values[self.size_focus] = "" if self.size_select_all else value[:-1]
                self.size_select_all = False
            elif ord("0") <= key <= ord("9") or key == ord("."):
                value = "" if self.size_select_all else self.size_values[self.size_focus]
                if len(value) < 14:
                    self.size_values[self.size_focus] = value + chr(key)
                self.size_select_all = False
            return
        actions = {13: "confirm", 10: "confirm", ord("c"): "confirm", ord("y"): "confirm", ord("Y"): "confirm",
                   ord("n"): "manual", ord("N"): "manual", ord("m"): "manual",
                   ord("a"): "auto", 26: "undo", ord("u"): "undo", ord("z"): "undo",
                   8: "undo", 127: "undo", ord("r"): "clear"}
        self.action(actions.get(key))

    def on_mouse(self, event, x, y, preview_size):
        if event == cv2.EVENT_LBUTTONDOWN:
            for rect, action in self.buttons:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    self.action(action)
                    return
            if self.mode == "dimensions":
                for index, rect in enumerate(self.size_fields):
                    if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                        self.size_focus = index
                        self.size_select_all = True
                        return
        width, height = preview_size
        if not (0 <= x < width and 0 <= y < height) or self.mode != "manual":
            return
        if event == cv2.EVENT_RBUTTONDOWN:
            self.undo()
        elif event == cv2.EVENT_LBUTTONDOWN:
            if len(self.points) == 4:
                self.note = "Four points selected. Choose YES to continue, Undo to correct a point, or Clear to start again."
                return
            source_height, source_width = self.frame.shape[:2]
            self.points.append([x * source_width / width, y * source_height / height])
            if len(self.points) == 4:
                try:
                    self.corners = order_corners(self.points)
                    self.note = "Check the corner labels, then continue. Undo remains available to correct any point."
                except ValueError as error:
                    self.corners = None
                    self.note = str(error) + ". Undo or clear to correct the selection."
            else:
                self.note = f"{len(self.points)} / 4 corners selected. Continue in any order."

    def render(self, preview_size):
        width, height = preview_size
        panel = np.full((height + (320 if self.mode == "dimensions" else 280), width, 3),
                        (31, 29, 27), dtype=np.uint8)
        panel[:height] = cv2.resize(self.frame, preview_size)
        scale = np.asarray(preview_size) / np.asarray(self.frame.shape[1::-1])
        if self.corners is not None:
            points = np.rint(np.asarray([self.corners[name] for name in CORNER_NAMES]) * scale).astype(np.int32)
            cv2.polylines(panel[:height], [points], True, (210, 175, 70), 1, cv2.LINE_AA)
            labels = CORNER_NAMES
        else:
            points = np.rint(np.asarray(self.points).reshape(-1, 2) * scale).astype(np.int32)
            labels = [str(i + 1) for i in range(len(points))]
        for label, point in zip(labels, points):
            cv2.circle(panel[:height], tuple(point), 9, (25, 25, 25), -1, cv2.LINE_AA)
            cv2.circle(panel[:height], tuple(point), 6, (210, 175, 70), -1, cv2.LINE_AA)
            draw_text(panel, label, (max(2, min(width - 30, int(point[0]) + 8)),
                                     max(20, min(height - 4, int(point[1]) - 8))), size=18)
        def centered(text, y, size, color=(235, 235, 235), x=0, span=width):
            text_width = (cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, size / 30, 1)[0][0]
                          if text.isascii() else len(text) * size)
            draw_text(panel, text, (x + max(4, (span - text_width) // 2), y), color, size=size)

        if self.mode == "dimensions":
            centered("Confirm the table dimensions", height + 43, min(30, max(14, width // 24)))
            self.size_fields = []
            margin, gap = 24, 16
            field_width = (width - 2 * margin - gap) // 2
            for index, label in enumerate(("Length (in)", "Width (in)")):
                x = margin + index * (field_width + gap)
                rect = (x, height + 88, x + field_width, height + 130)
                self.size_fields.append(rect)
                active = index == self.size_focus
                color = (210, 175, 70) if active else (110, 110, 110)
                draw_text(panel, label, (x, height + 78), size=17)
                cv2.rectangle(panel, rect[:2], rect[2:], (48, 46, 43), -1)
                if active and self.size_select_all:
                    cv2.rectangle(panel, (x + 4, height + 93), (x + field_width - 4, height + 125), (88, 78, 45), -1)
                cv2.rectangle(panel, rect[:2], rect[2:], color, 2 if active else 1)
                draw_text(panel, self.size_values[index] or " ", (x + 12, height + 119), size=24)
            self.buttons = []
            for index, (action, label) in enumerate((("confirm", "Continue [Enter]"), ("back", "Back to corners [B]"))):
                x = margin + index * (field_width + gap)
                rect = (x, height + 150, x + field_width, height + 193)
                cv2.rectangle(panel, rect[:2], rect[2:], (92, 120, 48) if action == "confirm" else (65, 61, 56), -1)
                centered(label, height + 178, min(18, max(10, field_width // 14)), x=x, span=field_width)
                self.buttons.append((rect, action))
            for i, line in enumerate(wrap(self.note, max(20, width // 11))[:2]):
                centered(line, height + 215 + i * 21, 14, (170, 170, 170))
            return panel

        question = "Are the table corners aligned?" if self.corners is not None else (
            "Mark the four table corners" if self.mode == "manual" else "Detecting table corners...")
        centered(question, height + 43, min(30, max(14, width // 24)))
        self.buttons = []
        choices = ([("confirm", "YES", "Continue"), ("undo", "Undo", "Last point [U]"),
                    ("clear", "Clear", "Start again [R]")] if self.mode == "manual" else
                   [("confirm", "YES", "Continue"), ("manual", "NO", "Manual correction")])
        gap, margin = 16, 24
        button_width = (width - 2 * margin - gap * (len(choices) - 1)) // len(choices)
        for i, (action, label, detail) in enumerate(choices):
            x, y = margin + i * (button_width + gap), height + 66
            rect = (x, y, x + button_width, y + 78)
            enabled = not ((action == "confirm" and self.corners is None) or (action == "undo" and not self.points))
            color = (92, 120, 48) if action == "confirm" else (65, 61, 56)
            cv2.rectangle(panel, rect[:2], rect[2:], color if enabled else (44, 43, 42), -1)
            foreground = (245, 245, 245) if enabled else (125, 125, 125)
            centered(label, y + 33, 23, foreground, x, button_width)
            centered(detail, y + 59, min(14, max(9, button_width // 12)), foreground, x, button_width)
            self.buttons.append((rect, action))
        for i, line in enumerate(wrap(self.note, max(20, width // 13))[:2]):
            centered(line, height + 173 + i * 21, 14, (170, 170, 170))
        return panel

    def snapshot(self):
        method = self.corner_mode if self.mode == "dimensions" else self.mode
        return {"corners": self.corners, "corner_order": list(CORNER_NAMES),
                "method": "manual" if method == "manual" else "lsd", "confirmed": self.confirmed,
                "board_size_in": list(self.board_size_in),
                "board_size_mm": [value * 25.4 for value in self.board_size_in],
                "dimensions_confirmed": self.confirmed,
                "coordinate_space": "source_image_pixels"}

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
