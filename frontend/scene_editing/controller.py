"""Manual rule inputs and terrain/front drafts; no SAM prompt edits."""
from copy import deepcopy
import numpy as np
from components.homography import transform_points
from components.registration.polygon import polygon_selection
from .dialogs import edit_terrain, edit_unit_rules

class SceneEditor:
    def __init__(self, match, geometry):
        self.match, self.geometry = match, geometry
        self.input_mode = None
        self.vertices = []
        self.note = ""
        self.dialog = self.dialog_request = None

    def undo_terrain(self):
        if self.vertices:
            self.vertices.pop()
        else:
            self.match.scene_editing.undo_terrain()

    def clear(self):
        if self.dialog is not None:
            self.dialog.close()
        self.dialog = self.dialog_request = None
        self.input_mode = None
        self.vertices.clear()

    def open_dialog(self, dialog, **request):
        state = self.match.snapshot()
        if self.dialog is not None:
            self.dialog.close()
        self.dialog = dialog
        self.dialog_request = {**request, "generation": state.source_ref.generation,
                               "calibration_version": state.board.calibration_version,
                               "reference": state.source_ref}

    def poll(self):
        state = self.match.snapshot()
        if self.dialog is None:
            return False
        request = self.dialog_request
        if (request["generation"] != state.source_ref.generation or
                request["calibration_version"] != state.board.calibration_version):
            self.clear()
            return True
        if not self.dialog.poll():
            return False
        values = self.dialog.result
        self.dialog = self.dialog_request = None
        if values is not None:
            if request["kind"] == "profile":
                if state.units.bindings.get(request["object_id"]) != request["unit_id"]:
                    self.note = "Unit selection changed; the old edit was discarded."
                    return True
                receipt = self.match.scene_editing.update_unit_profile(request["unit_id"], values, request["reference"])
                self.note = receipt.reason if receipt.status == "rejected" else "Unit rule information updated."
            else:
                receipt = self.match.scene_editing.add_terrain(request["vertices"], values, request["reference"])
                self.note = receipt.reason if receipt.status == "rejected" else "Terrain registered."
        return True

    def action(self, action, active_id):
        state = self.match.snapshot()
        if action == "front":
            if self.input_mode == "front":
                self.input_mode = None
                self.note = "Front input cancelled."
                return
            self.geometry.mode = None
            self.geometry.invalidate()
            object_id = self.geometry.selected[-1] if self.geometry.selected else active_id
            if state.registration_locked:
                raise ValueError("Initial facing is locked. Reset registration to mark it again.")
            if state.current.prediction is None or object_id not in state.current.prediction.get("trays", {}):
                raise ValueError("Select a unit with a fitted tray and real board scale first.")
            self.geometry.selected = [object_id]
            self.input_mode = "front"
            self.note = "Click the FRONT EDGE of the selected tray. This is separate from SAM prompts."
        elif action == "profile":
            self.geometry.mode = None
            self.geometry.invalidate()
            self.input_mode = None
            self.vertices.clear()
            object_id = self.geometry.selected[-1] if self.geometry.selected else active_id
            if state.units is None or object_id not in state.units.bindings:
                raise ValueError("Bind this mask to a unit type before editing its rule information.")
            unit = state.units.units[state.units.bindings[object_id]]
            profile = {**state.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            self.open_dialog(edit_unit_rules(profile), kind="profile", object_id=object_id,
                             unit_id=state.units.bindings[object_id])
            self.note = "Edit unit information in the separate window; live playback continues."
        elif action == "terrain":
            if state.board.image_to_plane is None:
                raise ValueError("Set the real board scale before annotating terrain.")
            self.geometry.mode = None
            self.geometry.invalidate()
            self.input_mode = None if self.input_mode == "terrain" else "terrain"
            self.vertices.clear()
            self.note = ("Terrain: click polygon vertices; click the first point to close. U / right click undoes."
                         if self.input_mode else "Terrain input cancelled.")
        elif action == "undo_terrain":
            self.undo_terrain()

    def click_input(self, point, preview_scale):
        state = self.match.snapshot()
        if self.input_mode == "front":
            object_id = self.geometry.selected[-1]
            state = state
            receipt = self.match.scene_editing.set_front(state.units.bindings[object_id],
                transform_points(point, state.board.homography["inverse_matrix"]), state.observation_ref)
            self.input_mode = None
            self.note = receipt.reason if receipt.status == "rejected" else "Front edge recorded. Use E to confirm Speed, Height, Side and current states."
        elif self.input_mode == "terrain":
            if len(self.vertices) >= 3 and np.linalg.norm((np.asarray(point) - self.vertices[0]) * preview_scale) <= 12:
                polygon_selection(state.current.frame.shape, self.vertices)
                self.open_dialog(edit_terrain(), kind="terrain", vertices=transform_points(
                    self.vertices, state.board.homography["inverse_matrix"]).tolist())
                self.vertices.clear()
                self.input_mode = None
            else:
                self.vertices.append(list(map(float, point)))
