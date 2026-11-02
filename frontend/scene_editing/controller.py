"""Manual rule inputs and terrain/front drafts; no SAM prompt edits."""
from copy import deepcopy
import numpy as np
from components.homography import transform_points
from components.registration.polygon import polygon_selection
from .dialogs import edit_terrain, edit_unit_rules

class SceneEditor:
    def __init__(self, session, live, geometry):
        self.session, self.live, self.geometry = session, live, geometry
        self.data = session.data
        self.input_mode = None
        self.vertices = []
        self.note = ""

    def changed(self, *, refresh_inputs=True):
        if refresh_inputs:
            self.live.refresh_analysis_inputs()
            if self.session.registration_locked:
                self.data.record_history()
        self.session.mark_changed()
        self.geometry.invalidate()

    def update_unit_profile(self, object_id, values):
        unit = self.data.units.units[self.data.units.bindings[object_id]]
        unit["attributes"].update(values)
        self.changed()

    def set_front(self, object_id, point):
        tray = self.data.current.prediction.get("trays", {}).get(object_id)
        if tray is None:
            raise ValueError("The selected tray is no longer available.")
        point_mm = transform_points(point, self.data.board.image_to_plane)
        self.data.rules.set_front(object_id, tray, point_mm, self.data.current.prediction_metadata["frame_index"])
        self.changed(refresh_inputs=False)

    def add_terrain(self, vertices, values):
        terrain_id = f"T{len(self.data.rules.terrain) + 1}"
        self.data.rules.terrain.append({"terrain_id": terrain_id, "polygon_image": deepcopy(vertices), **values})
        self.changed()

    def undo_terrain(self):
        if self.vertices:
            self.vertices.pop()
        elif self.data.rules.terrain:
            self.data.rules.terrain.pop()
            self.changed()

    def clear(self):
        self.input_mode = None
        self.vertices.clear()

    def action(self, action, active_id, pause):
        if action == "front":
            if self.input_mode == "front":
                self.input_mode = None
                self.note = "Front input cancelled."
                return
            self.geometry.mode = None
            self.geometry.invalidate()
            object_id = self.geometry.selected[-1] if self.geometry.selected else active_id
            if self.session.registration_locked:
                raise ValueError("Initial facing is locked. Reset registration to mark it again.")
            if self.data.current.prediction is None or object_id not in self.data.current.prediction.get("trays", {}):
                raise ValueError("Select a unit with a fitted tray and real board scale first.")
            self.geometry.selected = [object_id]
            self.input_mode = "front"
            pause()
            self.note = "Click the FRONT EDGE of the selected tray. This is separate from SAM prompts."
        elif action == "profile":
            self.geometry.mode = None
            self.geometry.invalidate()
            self.input_mode = None
            self.vertices.clear()
            object_id = self.geometry.selected[-1] if self.geometry.selected else active_id
            if self.data.units is None or object_id not in self.data.units.bindings:
                raise ValueError("Bind this mask to a unit type before editing its rule information.")
            pause()
            unit = self.data.units.units[self.data.units.bindings[object_id]]
            profile = {**self.data.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            values = edit_unit_rules(profile)
            if values is not None:
                self.update_unit_profile(object_id, values)
                self.note = "Unit rule information updated. States are supplied manually."
        elif action == "terrain":
            if self.data.board.image_to_plane is None:
                raise ValueError("Set the real board scale before annotating terrain.")
            self.geometry.mode = None
            self.geometry.invalidate()
            self.input_mode = None if self.input_mode == "terrain" else "terrain"
            self.vertices.clear()
            pause()
            self.note = ("Terrain: click polygon vertices; click the first point to close. U / right click undoes."
                         if self.input_mode else "Terrain input cancelled.")
        elif action == "undo_terrain":
            self.undo_terrain()

    def click_input(self, point, preview_scale):
        if self.input_mode == "front":
            object_id = self.geometry.selected[-1]
            self.set_front(object_id, point)
            self.input_mode = None
            self.note = "Front edge recorded. Use E to confirm Speed, Height, Side and current states."
        elif self.input_mode == "terrain":
            if len(self.vertices) >= 3 and np.linalg.norm((np.asarray(point) - self.vertices[0]) * preview_scale) <= 12:
                polygon_selection(self.data.current.frame.shape, self.vertices)
                values = edit_terrain()
                if values is not None:
                    self.add_terrain(self.vertices, values)
                self.vertices.clear()
                self.input_mode = None
            else:
                self.vertices.append(list(map(float, point)))
