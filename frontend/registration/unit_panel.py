"""Cached A/B type catalog sidebar."""

from pathlib import Path
import cv2
import numpy as np
from ..shared.drawing import draw_text

class UnitPanel:
    WIDTH = 520
    COLUMN_WIDTH = WIDTH // 2

    def __init__(self):
        self.offset = {"A": 0, "B": 0}
        self.buttons = []
        self.rows = []
        self.visible_count = 1

    @staticmethod
    def _types(roster, list_id):
        return [key for key, row in roster.types.items() if row.get("list_id", "A") == list_id]

    def reveal(self, roster, type_id):
        if roster is None or type_id not in roster.types:
            return
        list_id = roster.types[type_id].get("list_id", "A")
        ids = self._types(roster, list_id)
        index = ids.index(type_id)
        if not self.offset[list_id] <= index < self.offset[list_id] + self.visible_count:
            self.offset[list_id] = index // self.visible_count * self.visible_count

    def scroll(self, x, steps):
        if 0 <= x < self.WIDTH:
            self.offset["A" if x < self.COLUMN_WIDTH else "B"] += steps

    @staticmethod
    def _short(text, limit=41):
        text = str(text)
        return text if len(text) <= limit else text[:limit - 3] + "..."

    def render(self, height, roster, selected_type, active_id, known_ids, *, locked=False, mode="segment"):
        canvas = np.full((height, self.WIDTH, 3), 38, np.uint8)
        self.buttons, self.rows = [], []
        draw_text(canvas, "Unit annotation [locked]" if locked else "Unit annotation", (12, 23), size=16)
        for action, text, x, y, width in [
            ("import_A", "Import list A [O]", 12, 36, 236), ("import_B", "Import list B [P]", 272, 36, 236),
            ("mode", "Label [Tab]" if mode == "label" else "Segment [Tab]", 12, 100, 128),
            ("calibration", "Calibration [C]", 148, 100, 160),
            ("unbind", "Unbind", 316, 100, 88), ("undo", "Undo [U]", 412, 100, 96),
        ]:
            rect = (x, y, x + width, y + 30)
            disabled = locked
            cv2.rectangle(canvas, rect[:2], rect[2:], (48, 48, 48) if disabled else (72, 72, 72), -1)
            draw_text(canvas, text, (x + 9, y + 21), (120, 120, 120) if disabled else (230, 230, 230), size=13)
            self.buttons.append((rect, action))
        label = roster.bindings.get(active_id, "unlabelled") if roster else "unlabelled"
        draw_text(canvas, f"Active mask {active_id}: {label}", (12, 156), (100, 230, 150), size=16)
        labelled = sum(object_id in roster.bindings for object_id in known_ids) if roster else 0
        draw_text(canvas, f"Labelled masks: {labelled}/{len(known_ids)}", (12, 180), size=13)
        draw_text(canvas, "Click mask + type, or drag type to mask.", (12, 203), size=12)
        top, row_height = 250, 58
        self.visible_count = max(1, (height - top - 30) // row_height)
        cv2.line(canvas, (self.COLUMN_WIDTH, 34), (self.COLUMN_WIDTH, 92), (65, 65, 65), 1)
        cv2.line(canvas, (self.COLUMN_WIDTH, 219), (self.COLUMN_WIDTH, height - 8), (65, 65, 65), 1)
        for list_id, x, accent in (("A", 0, (210, 165, 95)), ("B", self.COLUMN_WIDTH, (95, 165, 225))):
            ids = self._types(roster, list_id) if roster else []
            info = roster.payload.get("lists", {}).get(list_id, {}) if roster else {}
            source = info.get("source") or (roster.source if roster and list_id == "A" else None)
            caption = Path(source).name if source else "Choose a PDF or type JSON"
            draw_text(canvas, self._short(caption, 35), (x + 12, 86), (165, 165, 165), size=11)
            draw_text(canvas, f"List {list_id} / {len(ids)} types", (x + 12, 233), accent, size=15)
            if not ids:
                draw_text(canvas, f"Import list {list_id} to add types.", (x + 12, top + 25), (165, 165, 165), size=12)
                continue
            self.offset[list_id] = min(max(0, self.offset[list_id]), max(0, len(ids) - self.visible_count))
            start = self.offset[list_id]
            for index, type_id in enumerate(ids[start:start + self.visible_count], start=start):
                row = roster.types[type_id]
                y = top + (index - start) * row_height
                rect = (x + 8, y, x + self.COLUMN_WIDTH - 8, y + row_height - 3)
                if type_id == selected_type:
                    cv2.rectangle(canvas, rect[:2], rect[2:], (75, 65, 48) if list_id == "A" else (48, 65, 75), -1)
                number = row.get("type_number", index + 1)
                count = sum(unit["type_id"] == type_id for unit in roster.units.values())
                draw_text(canvas, f"Type {number}", (x + 16, y + 17), accent, size=15)
                draw_text(canvas, f"{count} bound", (x + 172, y + 17), (170, 200, 170), size=11)
                description = row.get("unit_name", row.get("name", type_id))
                if row.get("formation"):
                    description += " / " + row["formation"]
                draw_text(canvas, self._short(description), (x + 16, y + 34), size=11)
                options = row.get("attributes", {}).get("options", [])
                detail = (", ".join(str(option.get("label", option.get("name", ""))) if isinstance(option, dict) else str(option)
                                    for option in options) if isinstance(options, list) else str(options))
                detail = detail or f"Next: {roster.next_unit_id(type_id)}"
                draw_text(canvas, self._short(detail, 44), (x + 16, y + 49), (165, 165, 165), size=10)
                self.rows.append((rect, type_id))
            draw_text(canvas, f"{start + 1}-{min(len(ids), start + self.visible_count)}/{len(ids)} | scroll this column",
                      (x + 12, height - 12), (170, 170, 170), size=10)
        return canvas

    def hit(self, x, y):
        for rect, action in self.buttons:
            if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                return action, None
        for rect, unit_id in self.rows:
            if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                return "select", unit_id
        return None, None
