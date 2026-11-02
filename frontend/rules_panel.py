"""Rule inputs, snapshot queries and independently cached commentary overlays."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import cv2
import numpy as np

from components.homography import transform_points
from components.registration.polygon import polygon_selection
from .annotation_panel import draw_text
from .rule_editor import edit_terrain, edit_unit_rules


def _query(scene, mode, unit_ids):
    from components.game_rules import line_of_sight, measure_distance, reachable_poses

    if mode == "distance":
        return measure_distance(scene, *unit_ids[:2])
    if mode == "los":
        result = line_of_sight(scene, *unit_ids[:2])
        if result.get("status") == "clear" and any("incomplete" in warning for warning in scene.get("warnings", [])):
            result.update(status="uncertain", reason="A registered unit has no valid tray; occlusion geometry is incomplete.")
        return result
    return reachable_poses(scene, unit_ids[0], order=mode)


class RulesPanel:
    ORDERS = ("advance", "back", "sidestep_left", "sidestep_right", "change_facing", "halt")

    def __init__(self):
        self.mode = None
        self.selected = []
        self.input_mode = None
        self.vertices = []
        self.buttons = []
        self.result = self.overlay = self.request = self.future = self.last_key = None
        self.result_request = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game-rules")
        self.epoch = 0
        self.note = "Select a rule tool, then click one or two units. Registered scene only."

    def invalidate(self):
        self.epoch += 1
        self.last_key = self.result = self.overlay = None
        self.result_request = None

    def select(self, object_id):
        if self.mode in ("distance", "los"):
            if object_id in self.selected:
                self.selected.remove(object_id)
            else:
                self.selected = (self.selected + [object_id])[-2:]
        else:
            self.selected = [object_id]
        self.invalidate()

    def action(self, action, flow):
        if action in ("distance", "los", "double"):
            self.mode = None if self.mode == action else action
            if self.mode is not None:
                flow.pause()
            else:
                flow.resume_live()
            self.input_mode = None
            self.vertices.clear()
            self.invalidate()
        elif action == "move":
            flow.pause()
            self.mode = self.ORDERS[(self.ORDERS.index(self.mode) + 1) % len(self.ORDERS)] if self.mode in self.ORDERS else "advance"
            self.input_mode = None
            self.vertices.clear()
            self.invalidate()
        elif action == "front":
            if self.input_mode == "front":
                self.input_mode = None
                self.note = "Front input cancelled."
                return
            self.mode = None
            self.invalidate()
            object_id = self.selected[-1] if self.selected else flow.active_id
            if flow.registration_locked:
                raise ValueError("Initial facing is locked. Reset registration to mark it again.")
            if flow.data.current.prediction is None or object_id not in flow.data.current.prediction.get("trays", {}):
                raise ValueError("Select a unit with a fitted tray and real board scale first.")
            self.selected = [object_id]
            self.input_mode = "front"
            flow.pause()
            self.note = "Click the FRONT EDGE of the selected tray. This is separate from SAM prompts."
        elif action == "profile":
            self.mode = None
            self.invalidate()
            self.input_mode = None
            self.vertices.clear()
            object_id = self.selected[-1] if self.selected else flow.active_id
            if flow.data.units is None or object_id not in flow.data.units.bindings:
                raise ValueError("Bind this mask to a unit type before editing its rule information.")
            flow.pause()
            unit = flow.data.units.units[flow.data.units.bindings[object_id]]
            profile = {**flow.data.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            values = edit_unit_rules(profile)
            if values is not None:
                unit["attributes"].update(values)
                flow.refresh_analysis_inputs()
                flow._prediction_changed()
                self.invalidate()
                self.note = "Unit rule information updated. States are supplied manually."
        elif action == "terrain":
            if flow.data.board.image_to_plane is None:
                raise ValueError("Set the real board scale before annotating terrain.")
            self.mode = None
            self.invalidate()
            self.input_mode = None if self.input_mode == "terrain" else "terrain"
            self.vertices.clear()
            flow.pause()
            self.note = ("Terrain: click polygon vertices; click the first point to close. U / right click undoes."
                         if self.input_mode else "Terrain input cancelled.")
        elif action == "undo_terrain":
            if self.vertices:
                self.vertices.pop()
            elif flow.data.rules.terrain:
                flow.data.rules.terrain.pop()
                flow.refresh_analysis_inputs()
                flow._prediction_changed()
                self.invalidate()

    def click_input(self, point, flow, preview_scale):
        if self.input_mode == "front":
            object_id = self.selected[-1]
            tray = flow.data.current.prediction.get("trays", {}).get(object_id)
            if tray is None:
                raise ValueError("The selected tray is no longer available.")
            point_mm = transform_points(point, flow.data.board.image_to_plane)
            flow.data.rules.set_front(object_id, tray, point_mm, flow.data.current.prediction_metadata["frame_index"])
            self.input_mode = None
            flow._prediction_changed()
            self.invalidate()
            self.note = "Front edge recorded. Use E to confirm Speed, Height, Side and current states."
        elif self.input_mode == "terrain":
            if len(self.vertices) >= 3 and np.linalg.norm((np.asarray(point) - self.vertices[0]) * preview_scale) <= 12:
                polygon_selection(flow.data.current.frame.shape, self.vertices)
                values = edit_terrain()
                if values is not None:
                    terrain_id = f"T{len(flow.data.rules.terrain) + 1}"
                    flow.data.rules.terrain.append({"terrain_id": terrain_id, "polygon_image": deepcopy(self.vertices), **values})
                    flow.refresh_analysis_inputs()
                    flow._prediction_changed()
                    self.invalidate()
                self.vertices.clear()
                self.input_mode = None
            else:
                self.vertices.append(list(map(float, point)))

    def tick(self, flow):
        view = flow.presentation
        changed = False
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            request = self.request
            if request["epoch"] == self.epoch and request["generation"] == flow.generation:
                try:
                    self.result = future.result()
                except Exception as error:
                    self.result = {"status": "unavailable", "reason": str(error)}
                self.result_request = request
                self.overlay = None
                changed = True
        if flow.data.current.prediction is None and self.result is not None:
            self.invalidate()
            changed = True
        if self.mode is None or view.current.prediction is None:
            return changed
        needed = 2 if self.mode in ("distance", "los") else 1
        if len(self.selected) < needed:
            self.note = f"{self.mode}: click {needed} unit{'s' if needed > 1 else ''}."
            return changed
        key = (self.mode, tuple(self.selected), view.current.view_revision, flow.generation, self.epoch)
        if self.future is not None or key == self.last_key:
            return changed
        self.last_key = key
        try:
            scene = view.rules.scene(view.units, view.current.prediction, view.board.image_to_plane,
                                          view.board.board_size_mm, view.current.prediction_metadata)
            ids = [view.units.bindings[object_id] for object_id in self.selected[:needed]]
        except (ValueError, KeyError) as error:
            self.result = {"status": "unavailable", "reason": str(error)}
            self.result_request = None
            self.overlay = None
            return True
        self.request = {"epoch": self.epoch, "generation": flow.generation,
                        "metadata": deepcopy(view.current.prediction_metadata), "image_to_plane": view.board.image_to_plane.copy()}
        self.future = self.executor.submit(_query, scene, self.mode, ids)
        return True

    def controls(self, panel, preview_size, y, flow):
        width = preview_size[0]
        self.buttons = []
        moves = self.mode.replace("_", " ").title() if self.mode in self.ORDERS else "Move"
        items = [("distance", "Distance [D]"), ("los", "LOS [L]"), ("move", f"{moves} [V]"), ("double", "Double [J]"),
                 ("front", "Set front [F]"), ("profile", "Unit rules [E]"), ("terrain", "Terrain [G]"), ("undo_terrain", "Undo terrain")]
        button_width = (width - 50) // 4
        for i, (action, label) in enumerate(items):
            x, top = 10 + (i % 4) * (button_width + 10), y + (i // 4) * 34
            rect = (x, top, x + button_width, top + 28)
            active = self.mode == action or (action == "move" and self.mode in self.ORDERS) or self.input_mode == action
            cv2.rectangle(panel, rect[:2], rect[2:], (90, 100, 45) if active else (55, 55, 55), -1)
            draw_text(panel, label, (x + 6, top + 19), size=max(9, min(13, button_width // 13)))
            self.buttons.append((rect, action))
        text = self.note
        if self.result is not None:
            status = self.result.get("status", "unknown")
            if self.mode == "distance" and "distance_in" in self.result:
                text = f"Distance: {self.result['distance_in']:.2f} in / {self.result['distance_mm']:.1f} mm"
            else:
                text = f"{self.mode}: {status}. {self.result.get('reason', '')}"
            if self.result_request is not None:
                age = max(0, flow.source.frame_index - self.result_request["metadata"]["frame_index"]) / flow.source.fps
                text += f" | snapshot age {age:.2f}s"
            if self.result.get("warnings"):
                text += " | " + "; ".join(self.result["warnings"][:1])
        roster = flow.presentation.units
        selected = ", ".join(roster.bindings.get(i, f"Mask {i}") for i in self.selected) if roster else ""
        draw_text(panel, f"KoW4 mini | Selected: {selected or 'none'} | estimates | Q clears query", (10, y + 86), size=12)
        limit = max(24, width // 7)
        for row in range(2):
            draw_text(panel, text[row * limit:(row + 1) * limit], (10, y + 106 + row * 18), size=12)

    def draw(self, preview, flow):
        view = flow.presentation
        scale = np.asarray(preview.shape[1::-1]) / np.asarray(view.current.frame.shape[1::-1])
        for item in view.rules.terrain:
            points = np.rint(np.asarray(item["polygon_image"]) * scale).astype(np.int32)
            cv2.polylines(preview, [points], True, (100, 180, 230), 1, cv2.LINE_AA)
        if view.current.prediction is not None:
            for object_id in self.selected:
                tray = view.current.prediction.get("trays", {}).get(object_id)
                if tray is not None:
                    points = np.rint(np.asarray(tray["corners_image"]) * scale).astype(np.int32)
                    cv2.polylines(preview, [points], True, (245, 245, 245), 2, cv2.LINE_AA)
        if self.vertices:
            points = np.rint(np.asarray(self.vertices) * scale).astype(np.int32)
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
                cv2.arrowedLine(preview, tuple(a), tuple(b), (100, 245, 140), 2, cv2.LINE_AA, tipLength=.3)
        if self.result is None or self.result_request is None or self.mode is None:
            return
        if self.overlay is None or self.overlay.shape != preview.shape:
            self.overlay = np.zeros_like(preview)
            inverse = np.linalg.inv(self.result_request["image_to_plane"])
            line = self.result.get("line_mm")
            if self.mode == "distance" and "point_a_mm" in self.result:
                line = [self.result["point_a_mm"], self.result["point_b_mm"]]
            if line is not None:
                points = np.rint(transform_points(line, inverse) * scale).astype(int)
                color = (100, 240, 160) if self.result.get("status") in ("ok", "clear") else (0, 190, 240)
                cv2.line(self.overlay, tuple(points[0]), tuple(points[1]), color, 2, cv2.LINE_AA)
            centers = [pose["center_mm"] for pose in self.result.get("poses", [])]
            if centers:
                for point in np.rint(transform_points(centers, inverse) * scale).astype(int):
                    cv2.circle(self.overlay, tuple(point), 2, (230, 160, 60), -1)
        mask = self.overlay.any(axis=2)
        preview[mask] = (preview[mask] * .4 + self.overlay[mask] * .6).astype(np.uint8)

    def reset(self):
        self.mode = self.input_mode = None
        self.selected.clear()
        self.vertices.clear()
        self.invalidate()

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
