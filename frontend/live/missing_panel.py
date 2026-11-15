"""A/B human requests after a single automatic search; internal Missing remains separate."""

import cv2
import numpy as np

from ..registration.unit_panel import UnitPanel
from ..shared.drawing import draw_text


class MissingUnitPanel:
    WIDTH = UnitPanel.WIDTH
    COLUMN_WIDTH = UnitPanel.COLUMN_WIDTH

    def __init__(self):
        self.offset = {"A": 0, "B": 0}
        self.rows = []

    @staticmethod
    def failed_units(data):
        return [unit_id for unit_id, state in data.tracking.items() if state.active and state.status == "failed"
                and state.recovery_phase == "review"]

    def unit_at(self, x, y):
        return next((uid for rect, uid in self.rows if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]), None)

    def scroll(self, x, steps):
        if 0 <= x < self.WIDTH:
            self.offset["A" if x < self.COLUMN_WIDTH else "B"] += steps

    def render(self, height, data):
        canvas = np.full((height, self.WIDTH, 3), 38, np.uint8)
        self.rows = []
        draw_text(canvas, "Recovery needs human input", (12, 24), size=16)
        draw_text(canvas, "Click an ID to review a candidate or add points.", (12, 45), size=12)
        stamp = (data.current.prediction_metadata or {}).get("timestamp_seconds")
        draw_text(canvas, f"Observation: {stamp:.2f}s" if stamp is not None else "Observation: unknown", (12, 65), size=12)
        failed = self.failed_units(data)
        count = max(1, (height - 120) // 100)
        for column, list_id in enumerate(("A", "B")):
            x = column * self.COLUMN_WIDTH
            cv2.line(canvas, (x, 76), (x, height), (65, 65, 65), 1)
            ids = [unit_id for unit_id in failed
                   if data.units.types[data.units.units[unit_id]["type_id"]].get("list_id", "A") == list_id]
            draw_text(canvas, f"List {list_id} | {len(ids)} candidates", (x + 12, 92), size=15)
            start = min(max(0, self.offset[list_id]), max(0, len(ids) - count))
            self.offset[list_id] = start
            for row, unit_id in enumerate(ids[start:start + count]):
                y = 108 + row * 100
                unit = data.units.units[unit_id]
                unit_type = data.units.types[unit["type_id"]]
                profile = {**unit_type.get("attributes", {}), **unit["attributes"]}
                state = data.tracking[unit_id]
                cv2.rectangle(canvas, (x + 8, y), (x + self.COLUMN_WIDTH - 8, y + 91), (55, 48, 40), -1)
                self.rows.append(((x + 8, y, x + self.COLUMN_WIDTH - 8, y + 91), unit_id))
                draw_text(canvas, UnitPanel._short(f"{unit_id} | Type {unit['type_id']}", 34), (x + 14, y + 18), size=14)
                name = unit_type.get("unit_name", unit_type.get("name", unit["type_id"]))
                draw_text(canvas, UnitPanel._short(name, 38), (x + 14, y + 36), size=11)
                damage = profile.get("damage")
                draw_text(canvas, f"Damage: {damage if damage is not None else '?'}", (x + 14, y + 53), size=12)
                text = "Candidate available for review" if state.recovery_phase == "review" else "Manual mask input needed"
                draw_text(canvas, text, (x + 14, y + 70), (110, 190, 245), size=11)
                last = state.last_accepted_position
                text = f"Last position: {last['timestamp_seconds']:.2f}s | v{last['calibration_version']}" if last else "Last position: unavailable"
                draw_text(canvas, text, (x + 14, y + 85), (170, 170, 170), size=10)
            if not ids:
                draw_text(canvas, "No candidates", (x + 14, 131), size=12)
            draw_text(canvas, f"{len(ids)} units | scroll this column", (x + 12, height - 12), (170, 170, 170), size=11)
        return canvas
