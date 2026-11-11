"""Live candidate overlay and A/B existing-instance drag targets."""
import textwrap

import cv2
import numpy as np

from ..registration.unit_panel import UnitPanel
from ..shared.drawing import draw_text
from ..shared.viewport import Viewport


class RecoveryView:
    def __init__(self, controller, match, display):
        self.controller, self.match, self.display = controller, match, display
        self.buttons, self.rows = [], []
        self.offset = {"A": 0, "B": 0}
        self.drag_id = self.drag_position = None
        self.mask_key = self.small_mask = self.drawn_prediction = None
        self.preview_size = None
        self.picking_error = False
        self.pointer_generation = None

    def render(self, preview_size):
        recovery, data = self.controller, self.match.snapshot()
        recovery_state = data.recovery
        self.preview_size = preview_size
        if self.pointer_generation != recovery_state["candidate_generation"]:
            self.picking_error = False
            self.pointer_generation = recovery_state["candidate_generation"]
        width, height = preview_size
        review = recovery_state["review_unit_id"] is not None
        canvas_height = max(height + (240 if review else 200), 360)
        canvas = np.full((canvas_height, width + UnitPanel.WIDTH, 3), 30, np.uint8)
        preview = self.display.render(data, preview_size)
        candidate = recovery_state["preview"]
        key = (id(candidate), preview_size)
        if key != self.mask_key:
            self.mask_key = key
            self.small_mask = (cv2.resize(candidate["prediction"]["masks"][0].astype(np.uint8), preview_size,
                                         interpolation=cv2.INTER_NEAREST).astype(bool) if candidate is not None else None)
        if self.small_mask is not None:
            preview[self.small_mask] = (preview[self.small_mask] * .55 + np.array([40, 210, 245]) * .45).astype(np.uint8)
            contours, _ = cv2.findContours(self.small_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(preview, contours, -1, (40, 220, 255), 2)
        canvas[:height, :width] = preview
        self.drawn_prediction = data.current.prediction
        self.drawn_size = data.current.frame.shape[1::-1]
        self.drawn_inverse = data.board.homography["inverse_matrix"]
        self.drawn_ref = data.source_ref
        self.drawn_generation = recovery_state["candidate_generation"]
        draw_text(canvas, "CANDIDATE REVIEW | Existing IDs only" if review else "MANUAL RECOVERY | Existing IDs only", (12, height + 23), size=15)
        stamp = candidate["metadata"].get("timestamp_seconds") if candidate else None
        text = "Candidate observed: none" if stamp is None else f"Candidate observed: {stamp:.2f}s"
        updating = recovery_state["busy"]
        draw_text(canvas, text + (" | Updating" if updating else " | LIVE"), (12, height + 44), size=12)
        self.buttons = []
        labels = [("clear", "Clear / Retry"), ("report", "Pick tracking error"), ("cancel", "Cancel [Esc]")]
        if review:
            labels = [("correct", "Correct"), ("reject", "No / Search again")] + labels
        columns = 3 if width >= 600 else 2
        button_width = min(190, (width - 10 * (columns + 1)) // columns)
        for i, (action, label) in enumerate(labels):
            x, y = 10 + i % columns * (button_width + 10), height + 56 + i // columns * 34
            rect = (x, y, x + button_width, y + 27)
            cv2.rectangle(canvas, rect[:2], rect[2:], (55, 55, 55) if recovery_state["committing"] else (75, 70, 60), -1)
            draw_text(canvas, label, (x + 5, y + 19), size=11)
            self.buttons.append((rect, action))
        for row, line in enumerate(textwrap.wrap(recovery_state["note"], max(30, width // 7))[:3]):
            draw_text(canvas, line, (12, height + (170 if review else 137) + row * 18), (130, 215, 245), size=12)

        self.rows = []
        labels = recovery_state["labels"]
        draw_text(canvas, "Drag an ID onto the yellow candidate", (width + 12, 25), size=15)
        draw_text(canvas, "A drop confirms one unit and returns live.", (width + 12, 47), size=12)
        count = max(1, (canvas_height - 120) // 70)
        for column, list_id in enumerate(("A", "B")):
            x = width + column * UnitPanel.COLUMN_WIDTH
            ids = [uid for uid in labels if data.units.types[data.units.units[uid]["type_id"]].get("list_id", "A") == list_id]
            start = min(max(0, self.offset[list_id]), max(0, len(ids) - count))
            self.offset[list_id] = start
            draw_text(canvas, f"List {list_id} | {len(ids)} available", (x + 12, 80), size=14)
            for row, uid in enumerate(ids[start:start + count]):
                y = 96 + row * 70
                rect = (x + 8, y, x + UnitPanel.COLUMN_WIDTH - 8, y + 61)
                cv2.rectangle(canvas, rect[:2], rect[2:], (60, 54, 44), -1)
                unit = data.units.units[uid]
                kind = data.units.types[unit["type_id"]]
                draw_text(canvas, UnitPanel._short(f"{uid} | Type {unit['type_id']}", 31), (x + 14, y + 20), size=14)
                name = kind.get("unit_name", kind.get("name", unit["type_id"]))
                draw_text(canvas, UnitPanel._short(name, 35), (x + 14, y + 38), size=11)
                state = ("Draft correction" if uid in recovery.reported else
                         "Reviewing candidate" if uid == recovery_state["review_unit_id"] else
                         "Candidate available" if data.tracking[uid].recovery_phase == "review" else "Manual input needed")
                draw_text(canvas, state, (x + 14, y + 54), (160, 190, 230), size=11)
                self.rows.append((rect, uid))
            if not ids:
                draw_text(canvas, "No units to recover", (x + 14, 119), size=12)
            cv2.line(canvas, (x, 60), (x, canvas_height), (70, 70, 70), 1)
        if self.drag_id is not None and self.drag_position is not None:
            draw_text(canvas, self.drag_id, self.drag_position, (80, 245, 255), size=18)
        return canvas

    def show_receipt(self, receipt):
        if receipt.status == "rejected":
            self.controller.note = receipt.reason

    def _source_point(self, x, y):
        from components.homography import transform_points
        point = Viewport.image_point((x, y), self.drawn_size, self.preview_size)
        return transform_points(point, self.drawn_inverse)

    @staticmethod
    def _inside(rect, x, y):
        return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]

    def _occupied(self, point, unit_id):
        data = self.match.snapshot()
        if self.drawn_prediction is None:
            return False
        x, y = map(int, point)
        for obj, mask in zip(self.drawn_prediction["object_ids"], self.drawn_prediction["masks"]):
            uid = data.units.bindings.get(obj)
            state = data.tracking.get(uid)
            if uid != unit_id and state is not None and state.active and state.status == "tracking" and mask[y, x]:
                return True
        return False

    def on_mouse(self, event, x, y, flags):
        recovery = self.controller
        if self.preview_size is None:
            return
        width, height = self.preview_size
        if event == cv2.EVENT_MOUSEWHEEL and x >= width:
            list_id = "A" if x - width < UnitPanel.COLUMN_WIDTH else "B"
            self.offset[list_id] += -3 if (flags >> 16) > 0 else 3
        elif event == cv2.EVENT_LBUTTONDOWN:
            for rect, action in self.buttons:
                if self._inside(rect, x, y):
                    if not recovery.committing:
                        if action == "clear":
                            recovery.clear_candidate()
                        elif action == "cancel":
                            recovery.cancel()
                        elif action == "correct":
                            self.show_receipt(recovery.bind(recovery.review_unit_id, self.drawn_generation))
                        elif action == "reject":
                            recovery.reject()
                        else:
                            self.picking_error = not self.picking_error
                            recovery.note = "Click an existing unit mask to offer its ID for correction."
                    return
            for rect, uid in self.rows:
                if self._inside(rect, x, y) and not recovery.busy:
                    recovery.select_unit(uid)
                    self.drag_id, self.drag_position = uid, (x, y)
                    return
            if 0 <= x < width and 0 <= y < height:
                if self.picking_error:
                    obj = Viewport.mask_at(x, y, self.match.snapshot(), self.preview_size)
                    if obj is None:
                        raise ValueError("Click an existing unit mask.")
                    self.show_receipt(recovery.report_error(self.match.snapshot().units.bindings.get(obj)))
                else:
                    size = self.drawn_size
                    self.show_receipt(recovery.point(self._source_point(x, y), True, self.drawn_ref))
        elif event == cv2.EVENT_RBUTTONDOWN and 0 <= x < width and 0 <= y < height:
            size = self.drawn_size
            self.show_receipt(recovery.point(self._source_point(x, y), False, self.drawn_ref))
        elif event == cv2.EVENT_MOUSEMOVE and self.drag_id is not None:
            self.drag_position = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.drag_id is not None:
            uid, self.drag_id, self.drag_position = self.drag_id, None, None
            if (0 <= x < width and 0 <= y < height and self.small_mask is not None and self.small_mask[y, x]):
                size = self.drawn_size
                point = Viewport.image_point((x, y), size, self.preview_size)
                if self._occupied(point, uid):
                    raise ValueError("This location belongs to another tracked unit. Its identity cannot be replaced.")
                self.show_receipt(recovery.bind(uid, self.drawn_generation))
            else:
                recovery.note = "Drop the ID inside the current yellow candidate."
