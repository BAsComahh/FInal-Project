"""Scene mutations and their history/geometry invalidation."""
from copy import deepcopy
from .contracts import command, CommandReceipt
import numpy as np
from components.homography import transform_points
from components.game_rules.scene import validate_scene, validate_unit_profile

class SceneEditing:
    def __init__(self, session, geometry):
        self._session, self.geometry = session, geometry
        self._data = session.data

    def changed(self, *, refresh_inputs=True):
        if refresh_inputs and self._session.registration_locked:
            self._data.record_history(kind="manual_state", source=self._session.source.metadata())
        self._session.mark_changed()
        self.geometry.invalidate()

    def validate(self, reference):
        if (self._session.closed or reference.generation != self._session.generation or
                reference.calibration_version != self._data.board.calibration_version):
            raise ValueError("Scene edit belongs to an expired session or calibration.")

    @command
    def update_unit_profile(self, unit_id, values, reference):
        self.validate(reference)
        unit = self._data.units.units.get(unit_id)
        if unit is None:
            raise ValueError("Unit is no longer registered.")
        candidate = deepcopy(values)
        validate_unit_profile(candidate, candidate, unit_id)
        unit["attributes"].update({key: candidate[key] for key in values})
        self.changed()
        return CommandReceipt("accepted")

    @command
    def set_front(self, unit_id, source_point, reference):
        self.validate(reference)
        if self._session.registration_locked:
            raise ValueError("Initial facing is locked. Reset registration to mark it again.")
        object_id = self._data.units.object_for(unit_id)
        if object_id is None:
            raise ValueError("Unit is no longer bound to a mask.")
        metadata = self._data.current.prediction_metadata
        if metadata is None or reference.frame_index != metadata["frame_index"]:
            raise ValueError("Facing input requires the displayed observation.")
        tray = self._data.current.prediction.get("trays", {}).get(object_id)
        if tray is None:
            raise ValueError("The selected tray is no longer available.")
        point_mm = transform_points(source_point, self._data.board.source_to_plane)
        self._data.rules.set_front(object_id, tray, point_mm, self._data.current.prediction_metadata["frame_index"],
                                  source_to_plane=self._data.board.source_to_plane)
        self.changed(refresh_inputs=False)
        return CommandReceipt("accepted")

    @command
    def add_terrain(self, source_vertices, values, reference):
        self.validate(reference)
        source = np.asarray(source_vertices, dtype=float)
        if source.ndim != 2 or source.shape[1] != 2 or len(source) < 3 or not np.isfinite(source).all():
            raise ValueError("Terrain requires at least three finite source points.")
        terrain_id = f"T{len(self._data.rules.terrain) + 1}"
        vertices = transform_points(source, self._data.board.homography["matrix"]).tolist()
        if not isinstance(values.get("label"), str) or not values["label"].strip():
            raise ValueError("Enter a terrain label.")
        terrain = validate_scene({"ruleset": "kow4-mini", "board_size_mm": self._data.board.board_size_mm,
            "units": [], "terrain": [{**deepcopy(values), "terrain_id": terrain_id,
                "polygon_mm": transform_points(source, self._data.board.source_to_plane).tolist()}]})["terrain"][0]
        terrain.pop("polygon_mm")
        self._data.rules.terrain.append({**terrain, "terrain_id": terrain_id,
                                       "polygon_source": source.tolist(), "polygon_image": vertices})
        self.changed()
        return CommandReceipt("accepted")

    @command
    def undo_terrain(self):
        if self._data.rules.terrain:
            self._data.rules.terrain.pop()
            self.changed()
        return CommandReceipt("accepted")
