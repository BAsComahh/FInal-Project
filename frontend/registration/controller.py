"""Initial-frame prompt drafts, type binding and one-time reference publication."""
from collections import deque
from pathlib import Path
import cv2
from components.homography import transform_points
from components.registration import UnitRoster, extract_references, save_registration, read_unit_list_pdf

class RegistrationController:
    def __init__(self, session):
        self.session = session
        self.data = session.data
        self.selected_type = next(iter(self.data.units.types)) if self.data.units else None
        self.interaction_mode = "segment"
        self.active_id = 1
        self.clicks = []
        self.pending_clicks = deque()
        self.next_click_id = 0
        self.pending_update = None
        self.updating_points = False

    @property
    def registration_locked(self):
        return self.data.reference_folder is not None

    def known_ids(self):
        ids = {click["object_id"] for click in self.clicks}
        if self.data.current.prediction is not None:
            ids.update(self.data.current.prediction["object_ids"])
        return sorted(ids)

    def can_edit_points(self):
        if self.data.board.homography is None:
            self.session.note = "Confirm the table corners and dimensions before registering units."
            self.session.dirty = True
            return False
        if self.registration_locked:
            self.session.note = "Registration is complete. R starts a new registration."
            self.session.dirty = True
            return False
        if not self.session.startup_ready:
            self.session.note = ("SAM3 preparation failed. R retries." if self.session.model_failed else
                         "Preparing SAM3 and first-frame features. Please wait before adding unit prompts.")
            self.session.dirty = True
            return False
        return True

    def load_units(self, path):
        if not self.can_edit_points():
            return
        roster = UnitRoster.load(path)
        if self.data.units is not None:
            roster.retain_bindings(self.data.units)
        self.data.units = roster
        self.selected_type = next(iter(roster.types))
        self.session.configure_trays()
        self.session.mark_changed()
        self.session.note = f"Loaded {len(roster.types)} types. Select a mask and click a type, or drag a type onto a mask."

    def can_import_list(self):
        if self.data.board.homography is None or self.registration_locked:
            self.session.note = ("Confirm the table corners and dimensions before importing army lists."
                         if self.data.board.homography is None else "Registration is complete. R starts a new registration.")
            self.session.dirty = True
            return False
        return True

    def import_unit_list(self, path, list_id):
        if not self.can_import_list():
            return False
        self.session.pause_source()
        path = Path(path).resolve()
        if path.suffix.lower() == ".pdf":
            payload = read_unit_list_pdf(path, side=list_id)
        elif path.suffix.lower() == ".json":
            payload = UnitRoster.load(path).payload
        else:
            raise ValueError("Choose an army-list PDF or a type-catalog JSON.")
        roster = self.data.units.with_list(list_id, payload, source=str(path))
        cleared = set(self.data.units.bindings) - set(roster.bindings)
        for object_id in cleared:
            self.data.rules.fronts.pop(object_id, None)
        self.data.units = roster
        self.selected_type = next(key for key, row in roster.types.items() if row.get("list_id") == list_id)
        self.session.configure_trays()
        self.session.mark_changed()
        count = sum(row.get("list_id") == list_id for row in roster.types.values())
        self.session.note = f"Imported list {list_id}: {count} types."
        if cleared:
            self.session.note += f" Reassign {len(cleared)} masks from the replaced list."
        return True

    def update_dimensions(self, dimensions):
        if not self.can_import_list():
            return False
        roster = self.data.units.with_dimensions(dimensions)
        changed = {key for key in roster.types
                   if roster.types[key].get("dimension") != self.data.units.types[key].get("dimension")}
        if not changed:
            self.session.note = "Tray dimensions unchanged."
            self.session.dirty = True
            return False
        affected = [object_id for object_id, unit_id in roster.bindings.items()
                    if roster.units[unit_id]["type_id"] in changed]
        for object_id in affected:
            self.data.rules.fronts.pop(object_id, None)
        self.data.units = roster
        self.session.configure_trays()
        self.session.mark_changed()
        self.session.note = f"Updated tray dimensions for {len(changed)} types."
        if affected:
            self.session.note += " Refitting trays; set their front edges again with F."
        return True

    def bind_active(self):
        if not self.can_edit_points():
            return
        self.session.pause_source()
        if self.data.units is None or self.selected_type is None:
            raise ValueError("Load a type catalog and select a type first")
        if self.active_id not in self.known_ids():
            raise ValueError("Click a target before binding its unit")
        previous = self.data.units.bindings.get(self.active_id)
        unit_id = self.data.units.bind(self.active_id, self.selected_type)
        if unit_id != previous:
            self.data.rules.fronts.pop(self.active_id, None)
            self.session.configure_trays()
        self.session.mark_changed()
        self.session.note = f"Mask {self.active_id} -> {unit_id}. Click another type to rebind; N adds another mask."

    def unbind_active(self):
        if not self.can_edit_points():
            return
        self.session.pause_source()
        if self.data.units is not None:
            self.data.units.unbind(self.active_id)
            self.data.rules.fronts.pop(self.active_id, None)
            self.session.configure_trays()
            self.session.mark_changed()
        self.session.note = f"Mask {self.active_id} is unlabelled. Click a type to bind it."

    def select_mask(self, object_id):
        self.active_id = object_id
        if self.data.units and object_id in self.data.units.bindings:
            unit_id = self.data.units.bindings[object_id]
            self.selected_type = self.data.units.units[unit_id]["type_id"]
        self.session.note = (f"Registered mask {object_id}. Registration is complete; R starts again."
                     if self.registration_locked else
                     f"Selected mask {object_id}. Click a type to bind; Tab switches point editing / labelling.")
        self.session.mark_changed()

    def cycle_mask(self, direction):
        ids = self.known_ids()
        if not ids:
            return
        index = ids.index(self.active_id) if self.active_id in ids else -1
        self.select_mask(ids[(index + direction) % len(ids)])

    def unit_action(self, action, unit_id=None):
        try:
            if action == "bind":
                self.bind_active()
            elif action == "unbind":
                self.unbind_active()
            elif action == "undo":
                self.undo_point()
            elif action == "mode":
                if self.can_edit_points():
                    self.interaction_mode = "label" if self.interaction_mode == "segment" else "segment"
                    self.session.note = ("Label mode: click a mask, then a type; or drag a type onto a mask."
                                 if self.interaction_mode == "label" else
                                 "Segment mode: clicks edit prompts. N adds a mask; Tab switches to labelling.")
            elif action == "select":
                if not self.can_edit_points():
                    return
                self.selected_type = unit_id
                self.interaction_mode = "label"
                if self.active_id in self.known_ids():
                    self.bind_active()
                else:
                    self.session.note = "Select a segmented mask, then click the type; or drag the type onto a mask."
        except (OSError, ValueError, RuntimeError) as error:
            self.session.note = str(error)
        self.session.dirty = True

    def new_object(self):
        if not self.can_edit_points():
            return
        self.session.pause_source()
        self.interaction_mode = "segment"
        self.active_id = max(self.known_ids(), default=0) + 1
        self.session.mark_changed()
        self.session.note = f"Left click new mask {self.active_id}. Types can be assigned after all masks are segmented."

    def click(self, x, y, *, positive=True):
        if self.session.closed:
            return
        if not self.can_edit_points():
            return
        height, width = self.data.current.frame.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return
        self.session.pause_source()
        ids = {click["object_id"] for click in self.clicks if click["positive"]}
        if not positive and self.active_id not in ids:
            self.session.note = "Start this object with a positive click."
            return
        click = {"object_id": self.active_id, "point": [float(x), float(y)],
                 "point_source": transform_points([x, y], self.data.board.homography["inverse_matrix"]).tolist(),
                 "positive": positive, "video_frame": self.session.source.frame_index, "session_frame": None,
                 "click_id": self.next_click_id}
        self.next_click_id += 1
        self.clicks.append(click)
        self.pending_clicks.append((self.data.current.frame.copy(), self.session.frame_metadata(), click))
        self.session.model_failed = False
        self.session.note = "Click queued. SAM3 runs in the background; playback remains available."

    def undo_point(self):
        """Undo the most recent positive/negative click across all objects."""
        if not self.can_edit_points():
            return
        self.session.pause_source()
        if not self.clicks:
            self.session.note = "No point to undo."
            return
        removed = self.clicks.pop()
        self.active_id = removed["object_id"]
        if self.data.units and not any(click["object_id"] == self.active_id for click in self.clicks):
            unit_id = self.data.units.bindings.get(self.active_id)
            if unit_id is not None:
                self.selected_type = self.data.units.units[unit_id]["type_id"]
            self.data.units.unbind(self.active_id)
            self.data.rules.fronts.pop(self.active_id, None)
            self.session.configure_trays()
        queued = any(prompt["click_id"] == removed["click_id"] for _, _, prompt in self.pending_clicks)
        if queued and not self.updating_points:
            self.pending_clicks = deque(item for item in self.pending_clicks
                                        if item[2]["click_id"] != removed["click_id"])
            self.session.note = "Undid the queued point."
            return
        # Serialize prompt replacement behind any in-flight inference and
        # discard its stale UI result using the generation counter.
        self.session.generation += 1
        self.pending_clicks.clear()
        self.pending_update = {"frame": self.data.current.frame.copy(), "metadata": self.session.frame_metadata(),
                                "clicks": [dict(click) for click in self.clicks]}
        self.updating_points = True
        self.data.current.prediction = self.data.current.prediction_frame = self.data.current.prediction_metadata = None
        self.session.model_failed = False
        self.session.mark_changed()
        self.session.note = "Point undone. Updating initial-frame prompts; please wait before saving."

    def extract_references(self):
        """Return masks and cutouts from the latest completed inference snapshot."""
        if self.updating_points:
            raise ValueError("Wait for the point update to finish before saving")
        if self.data.current.prediction is None:
            raise ValueError("No completed SAM3 result to extract")
        if self.pending_clicks or (self.session.worker.busy and self.session.worker.request["kind"] == "click"):
            raise ValueError("Wait for the queued click prompts to finish before extracting")
        return extract_references(self.data.current.prediction_frame, self.data.current.prediction, source=self.data.current.prediction_metadata,
                                  roster=self.data.units)

    def finish_registration(self, overlay):
        """Commit final references once; drafts remain editable after save errors."""
        if self.data.board.homography is None:
            raise ValueError("Confirm the table boundary before completing registration")
        if self.data.reference_folder is not None:
            self.session.note = f"Registration already saved: {self.data.reference_folder}"
            self.session.dirty = True
            return self.data.reference_folder
        if self.session.worker.busy or self.pending_clicks or self.session.pending_trays or self.updating_points or self.session.needs_reset or self.session.needs_load or self.session.needs_prepare:
            raise ValueError("Wait for the point prompts to finish before completing registration")
        if self.session.model_failed:
            raise ValueError("Resolve the SAM3 error before completing registration; R resets")
        references = self.extract_references()
        self.session.pause_source()
        metadata = {**self.data.current.prediction_metadata, "object_ids": self.data.current.prediction["object_ids"],
                    "clicks": self.clicks, "inference_fps_limit": self.session.inference_fps,
                    "display_video_frame": self.session.source.frame_index, "model": self.session.worker.predictor.model_id,
                    "tracking_backend": self.session.worker.tracker_name,
                    "tracker_model": self.session.worker.tracker.model_id if self.session.worker.tracker is not None else self.session.worker.predictor.model_id,
                    "session_frame": self.data.current.prediction["frame_idx"], "registration_complete": True,
                    "table_boundary": self.data.board.table_boundary, "rule_inputs": self.data.rules.snapshot()}
        if self.data.board.image_to_plane is not None and self.data.units is not None:
            metadata["rule_scene"] = self.data.rules.scene(self.data.units, self.data.current.prediction, self.data.board.image_to_plane,
                                                          self.data.board.board_size_mm, self.data.current.prediction_metadata,
                                                          source_to_plane=self.data.board.source_to_plane)
        folder = save_registration(self.data.current.prediction_frame, overlay, references, metadata,
                                   self.session.output_dir, roster=self.data.units)
        self.data.reference_folder = folder
        self.session.capture_facing_references()
        self.data.start_history(folder, metadata)
        self.data.accept_observation(self.data.current.prediction, self.data.current.prediction_frame,
                                     self.data.current.prediction_metadata, disappearance_seconds=self.session.disappearance_seconds)
        self.data.record_history(kind="registration")
        print(f"Saved: {folder.resolve()}", flush=True)
        self.session.note = f"Registration complete; final references saved. Space plays. {folder}"
        self.session.dirty = True
        return folder

    def reset(self):
        self.interaction_mode = "segment"
        self.pending_clicks.clear()
        self.pending_update = None
        self.updating_points = False
        self.active_id = 1
        if self.data.units:
            self.data.units.reset_bindings()
            self.selected_type = next(iter(self.data.units.types))
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
