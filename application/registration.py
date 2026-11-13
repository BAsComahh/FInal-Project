"""Initial-frame prompt drafts, type binding and one-time reference publication."""
from .contracts import CommandReceipt, command
from collections import deque
from pathlib import Path
import cv2
from components.homography import transform_points
from components.registration import UnitRoster, extract_references, save_registration, read_unit_list_pdf

class Registration:
    def __init__(self, session):
        self._session = session
        self.sample = None
        self._data = session.data
        self.clicks = []
        self.pending_clicks = deque()
        self.next_click_id = 0
        self.pending_update = None
        self.updating_points = False

    @property
    def registration_locked(self):
        return self._data.reference_folder is not None

    def known_ids(self):
        ids = {click["object_id"] for click in self.clicks}
        if self._data.current.prediction is not None:
            ids.update(self._data.current.prediction["object_ids"])
        return sorted(ids)

    def can_edit_points(self):
        if self._session.closed:
            self._session.note = "Match is closed."
            return False
        if self._data.board.homography is None:
            self._session.note = "Confirm the table corners and dimensions before registering units."
            return False
        if self.registration_locked:
            self._session.note = "Registration is complete. R starts a new registration."
            return False
        if not self._session.startup_ready:
            self._session.note = ("SAM3 preparation failed. R retries." if self._session.model_failed else
                         "Preparing SAM3 and first-frame features. Please wait before adding unit prompts.")
            return False
        return True

    @command
    def load_units(self, path):
        if not self.can_edit_points():
            return CommandReceipt("rejected", self._session.note)
        roster = UnitRoster.load(path)
        if self._data.units is not None:
            roster.retain_bindings(self._data.units)
        self._data.units = roster
        self._session.configure_trays()
        self._session.mark_changed()
        self._session.note = f"Loaded {len(roster.types)} types. Select a mask and click a type, or drag a type onto a mask."
        return CommandReceipt("accepted")

    def can_import_list(self):
        if self._session.closed or self._data.board.homography is None or self.registration_locked:
            self._session.note = ("Confirm the table corners and dimensions before importing army lists."
                         if self._data.board.homography is None else "Registration is complete. R starts a new registration.")
            return False
        return True

    @command
    def import_unit_list(self, path, list_id):
        if not self.can_import_list():
            return CommandReceipt("rejected", self._session.note)
        self._session.pause_source()
        path = Path(path).resolve()
        if path.suffix.lower() == ".pdf":
            payload = read_unit_list_pdf(path, side=list_id)
        elif path.suffix.lower() == ".json":
            payload = UnitRoster.load(path).payload
        else:
            raise ValueError("Choose an army-list PDF or a type-catalog JSON.")
        roster = self._data.units.with_list(list_id, payload, source=str(path))
        cleared = set(self._data.units.bindings) - set(roster.bindings)
        for object_id in cleared:
            self._data.rules.fronts.pop(object_id, None)
        self._data.units = roster
        self._session.configure_trays()
        self._session.mark_changed()
        count = sum(row.get("list_id") == list_id for row in roster.types.values())
        self._session.note = f"Imported list {list_id}: {count} types."
        if path.suffix.lower() == ".pdf":
            sized = sum("dimension" in row for row in payload["unit_types"])
            self._session.note += f" Tray sizes filled: {sized}/{count}; check unit-specific base sizes."
            if sized < count:
                self._session.note += f" {count - sized} sizes unavailable; check the unit profiles or import a catalog with explicit sizes."
        if cleared:
            self._session.note += f" Reassign {len(cleared)} masks from the replaced list."
        return CommandReceipt("accepted", value=True)

    @command
    def update_dimensions(self, dimensions):
        if not self.can_import_list():
            return CommandReceipt("rejected", self._session.note)
        roster = self._data.units.with_dimensions(dimensions)
        changed = {key for key in roster.types
                   if roster.types[key].get("dimension") != self._data.units.types[key].get("dimension")}
        if not changed:
            self._session.note = "Tray dimensions unchanged."
            return CommandReceipt("rejected", self._session.note)
        affected = [object_id for object_id, unit_id in roster.bindings.items()
                    if roster.units[unit_id]["type_id"] in changed]
        for object_id in affected:
            self._data.rules.fronts.pop(object_id, None)
        self._data.units = roster
        self._session.configure_trays()
        self._session.mark_changed()
        self._session.note = f"Updated tray dimensions for {len(changed)} types."
        if affected:
            self._session.note += " Refitting trays; set their front edges again with F."
        return CommandReceipt("accepted", value=True)

    @command
    def bind(self, object_id, type_id):
        if not self.can_edit_points():
            return CommandReceipt("rejected", self._session.note)
        self._session.pause_source()
        if self._data.units is None or type_id is None:
            raise ValueError("Load a type catalog and select a type first")
        if object_id not in self.known_ids():
            raise ValueError("Click a target before binding its unit")
        previous = self._data.units.bindings.get(object_id)
        unit_id = self._data.units.bind(object_id, type_id)
        if unit_id != previous:
            self._data.rules.fronts.pop(object_id, None)
            self._session.configure_trays()
        self._session.mark_changed()
        self._session.note = f"Mask {object_id} -> {unit_id}. Click another type to rebind; N adds another mask."
        return CommandReceipt("accepted")

    @command
    def unbind(self, object_id):
        if not self.can_edit_points():
            return CommandReceipt("rejected", self._session.note)
        self._session.pause_source()
        if self._data.units is not None:
            self._data.units.unbind(object_id)
            self._data.rules.fronts.pop(object_id, None)
            self._session.configure_trays()
            self._session.mark_changed()
        self._session.note = f"Mask {object_id} is unlabelled. Click a type to bind it."
        return CommandReceipt("accepted")

    @command
    def point(self, object_id, source_point, reference, *, positive=True):
        if self._session.closed:
            return CommandReceipt("rejected", self._session.note)
        if not self.can_edit_points():
            return CommandReceipt("rejected", self._session.note)
        if isinstance(object_id, bool) or not isinstance(object_id, int) or object_id < 1:
            raise ValueError("Registration object ID must be a positive integer.")
        snapshot = self.sample(reference)
        x, y = transform_points(source_point, self._data.board.homography["matrix"])
        height, width = self._data.current.frame.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return CommandReceipt("rejected", self._session.note)
        self._session.pause_source()
        ids = {click["object_id"] for click in self.clicks if click["positive"]}
        if not positive and object_id not in ids:
            self._session.note = "Start this object with a positive click."
            return CommandReceipt("rejected", self._session.note)
        click = {"object_id": object_id, "point": [float(x), float(y)],
                 "point_source": transform_points([x, y], self._data.board.homography["inverse_matrix"]).tolist(),
                 "positive": positive, "video_frame": self._session.source.frame_index, "session_frame": None,
                 "click_id": self.next_click_id}
        self.next_click_id += 1
        self.clicks.append(click)
        self.pending_clicks.append((snapshot["frame"], snapshot["metadata"], click))
        self._session.model_failed = False
        self._session.note = "Click queued. SAM3 runs in the background; playback remains available."
        return CommandReceipt("pending", request_id=click["click_id"])

    @command
    def undo_point(self):
        """Undo the most recent positive/negative click across all objects."""
        if not self.can_edit_points():
            return CommandReceipt("rejected", self._session.note)
        self._session.pause_source()
        if not self.clicks:
            self._session.note = "No point to undo."
            return CommandReceipt("rejected", self._session.note)
        removed = self.clicks.pop()
        object_id = removed["object_id"]
        if self._data.units and not any(click["object_id"] == object_id for click in self.clicks):
            self._data.units.unbind(object_id)
            self._data.rules.fronts.pop(object_id, None)
            self._session.configure_trays()
        queued = any(prompt["click_id"] == removed["click_id"] for _, _, prompt in self.pending_clicks)
        if queued and not self.updating_points:
            self.pending_clicks = deque(item for item in self.pending_clicks
                                        if item[2]["click_id"] != removed["click_id"])
            self._session.note = "Undid the queued point."
            return CommandReceipt("accepted")
        # Serialize prompt replacement behind any in-flight inference and
        # discard its stale UI result using the generation counter.
        self._session.generation += 1
        self.pending_clicks.clear()
        self.pending_update = {"frame": self._data.current.frame.copy(), "metadata": self._session.frame_metadata(),
                                "clicks": [dict(click) for click in self.clicks]}
        self.updating_points = True
        self._data.current.prediction = self._data.current.prediction_frame = self._data.current.prediction_metadata = None
        self._session.model_failed = False
        self._session.mark_changed()
        self._session.note = "Point undone. Updating initial-frame prompts; please wait before saving."
        return CommandReceipt("pending")

    def extract_references(self):
        """Return masks and cutouts from the latest completed inference snapshot."""
        if self.updating_points:
            raise ValueError("Wait for the point update to finish before saving")
        if self._data.current.prediction is None:
            raise ValueError("No completed SAM3 result to extract")
        if self.pending_clicks or (self._session.worker.busy and self._session.worker.request["kind"] == "click"):
            raise ValueError("Wait for the queued click prompts to finish before extracting")
        return extract_references(self._data.current.prediction_frame, self._data.current.prediction, source=self._data.current.prediction_metadata,
                                  roster=self._data.units)

    @command
    def finish_registration(self, overlay=None):
        """Commit final references once; drafts remain editable after save errors."""
        if self._session.closed:
            raise ValueError("Match is closed.")
        if self._data.board.homography is None:
            raise ValueError("Confirm the table boundary before completing registration")
        if self._data.reference_folder is not None:
            self._session.note = f"Registration already saved: {self._data.reference_folder}"
            return CommandReceipt("accepted", value=self._data.reference_folder)
        if self._session.worker.busy or self.pending_clicks or self._session.pending_trays or self.updating_points or self._session.needs_reset or self._session.needs_load or self._session.needs_prepare:
            raise ValueError("Wait for the point prompts to finish before completing registration")
        if self._session.model_failed:
            raise ValueError("Resolve the SAM3 error before completing registration; R resets")
        references = self.extract_references()
        self._session.pause_source()
        metadata = {**self._data.current.prediction_metadata, "object_ids": self._data.current.prediction["object_ids"],
                    "clicks": self.clicks, "inference_fps_limit": self._session.inference_fps,
                    "display_video_frame": self._session.source.frame_index, "model": self._session.worker.predictor.model_id,
                    "tracking_backend": self._session.worker.tracker_name,
                    "tracker_model": self._session.worker.tracker.model_id if self._session.worker.tracker is not None else self._session.worker.predictor.model_id,
                    "session_frame": self._data.current.prediction["frame_idx"], "registration_complete": True,
                    "table_boundary": self._data.board.table_boundary, "rule_inputs": self._data.rules.snapshot()}
        if self._data.board.image_to_plane is not None and self._data.units is not None:
            metadata["rule_scene"] = self._data.rules.scene(self._data.units, self._data.current.prediction, self._data.board.image_to_plane,
                                                          self._data.board.board_size_mm, self._data.current.prediction_metadata,
                                                          source_to_plane=self._data.board.source_to_plane)
        if overlay is None:
            import numpy as np
            overlay = self._data.current.prediction_frame.copy()
            for obj, mask in zip(self._data.current.prediction["object_ids"], self._data.current.prediction["masks"]):
                color = np.random.default_rng(obj).integers(60, 255, 3)
                overlay[mask] = (overlay[mask] * .5 + color * .5).astype(np.uint8)
        folder = save_registration(self._data.current.prediction_frame, overlay, references, metadata,
                                   self._session.output_dir, roster=self._data.units)
        self._data.reference_folder = folder
        self._session.capture_facing_references()
        self._data.start_history(folder, metadata)
        self._data.accept_observation(self._data.current.prediction, self._data.current.prediction_frame,
                                     self._data.current.prediction_metadata, disappearance_seconds=self._session.disappearance_seconds)
        self._data.record_history(kind="registration")
        print(f"Saved: {folder.resolve()}", flush=True)
        self._session.note = f"Registration complete; final references saved. Space plays. {folder}"
        return CommandReceipt("accepted", value=folder)

    def reset(self):
        self.pending_clicks.clear()
        self.pending_update = None
        self.updating_points = False
        if self._data.units:
            self._data.units.reset_bindings()
        self.clicks.clear()

    def take_pending_request(self):
        if self.pending_update is not None:
            request, self.pending_update = self.pending_update, None
            return "replace", request
        if self.pending_clicks:
            frame, metadata, prompt = self.pending_clicks.popleft()
            return "click", {"frame": frame, "metadata": metadata, "prompt": prompt}
        return None

    def accept_prompt_result(self, request, prediction):
        if request["kind"] == "replace":
            self.updating_points = False
        if prediction is None:
            return
        if request["kind"] == "click":
            request["prompt"]["session_frame"] = prediction["frame_idx"]
        elif request["kind"] == "replace":
            by_id = {click["click_id"]: click for click in request["clicks"]}
            for click in self.clicks:
                if click["click_id"] in by_id:
                    click["session_frame"] = by_id[click["click_id"]]["session_frame"]
