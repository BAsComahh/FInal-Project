"""Window-local selection; never owns tracking, facing or Missing state."""
def unit_uncertainties(state, object_id):
    """Attention flags, independent of the algorithm's retained provenance."""
    prediction = state.current.prediction or {}
    unit_id = state.units.bindings.get(object_id)
    tracking = state.tracking.get(unit_id)
    if (object_id in prediction.get("inactive_ids", ()) or
            tracking is not None and (not tracking.active or tracking.status == "failed" and
                                      tracking.recovery_phase in ("queued", "searching"))):
        return {}
    issues = {}
    if object_id in prediction.get("estimated_ids", ()):
        issues["mask"] = "Estimated"
    elif tracking is not None and tracking.status == "failed" and tracking.recovery_phase == "review":
        issues["mask"] = "Candidate ready for review"
    if "mask" in issues and tracking is not None and tracking.status == "failed" and tracking.recovery_note:
        issues["mask"] += f" · {tracking.recovery_note}"
    if not state.rules.track_facing:
        return issues
    front = state.rules.fronts.get(object_id)
    if (front is None or object_id in prediction.get("unavailable_ids", ()) or
            tracking is not None and tracking.status == "failed"):
        issues["facing"] = "Unknown"
    else:
        phase = front.get("appearance", {}).get("recovery_phase")
        if phase in ("pending", "failed", "waiting"):
            label = "recovery failed" if phase == "failed" else phase
            issues["facing"] = f"Estimated · {label}"
        elif phase != "tracking" and front.get("source") != "manual":
            issues["facing"] = "Estimated · unchecked"
    return issues


class RegistrationSelection:
    def __init__(self, match):
        self.match = match
        self.reset()

    def reset(self):
        self.active_id = 1
        self.interaction_mode = "segment"
        self.selected_type = next(iter(self.match.snapshot().units.types), None)

    def select_mask(self, object_id):
        state = self.match.snapshot()
        self.active_id = object_id
        if state.units and object_id in state.units.bindings:
            unit_id = state.units.bindings[object_id]
            self.selected_type = state.units.units[unit_id]["type_id"]
        self.match.set_note(f"Registered mask {object_id}. Registration is complete; R starts again."
                     if state.registration_locked else
                     f"Selected mask {object_id}. Click a type to bind; Tab switches point editing / labelling.")

    def cycle_mask(self, direction):
        ids = self.match.registration.known_ids()
        if not ids:
            return
        index = ids.index(self.active_id) if self.active_id in ids else -1
        self.select_mask(ids[(index + direction) % len(ids)])

    def unit_action(self, action, unit_id=None):
        if action == "bind":
            self.match.registration.bind(self.active_id, self.selected_type)
        elif action == "unbind":
            self.match.registration.unbind(self.active_id)
        elif action == "undo":
            self.undo_point()
        elif action == "mode":
            if self.match.registration.can_edit_points():
                self.interaction_mode = "label" if self.interaction_mode == "segment" else "segment"
                self.match.set_note("Label mode: click a mask, then a type; or drag a type onto a mask."
                             if self.interaction_mode == "label" else
                             "Segment mode: clicks edit prompts. N adds a mask; Tab switches to labelling.")
        elif action == "select":
            if not self.match.registration.can_edit_points():
                return
            self.selected_type = unit_id
            self.interaction_mode = "label"
            if self.active_id in self.match.registration.known_ids():
                self.match.registration.bind(self.active_id, self.selected_type)
            else:
                self.match.set_note("Select a segmented mask, then click the type; or drag the type onto a mask.")

    def new_object(self):
        if not self.match.registration.can_edit_points():
            return
        self.interaction_mode = "segment"
        self.active_id = max(self.match.registration.known_ids(), default=0) + 1
        self.match.set_note(f"Left click new mask {self.active_id}. Types can be assigned after all masks are segmented.")

    def undo_point(self):
        prompts = self.match.snapshot().registration_prompts
        if prompts:
            self.select_mask(prompts[-1]["object_id"])
        self.match.registration.undo_point()


class GeometrySelection:
    ORDERS = ("advance", "back", "sidestep_left", "sidestep_right", "change_facing", "halt")

    def __init__(self, match):
        self.match = match
        self.mode = None
        self.selected = []
        self.note = "Select a rule tool, then click one or two units. Registered scene only."

    def invalidate(self):
        state = self.match.snapshot()
        ids = [state.units.bindings[obj] for obj in self.selected if obj in state.units.bindings]
        receipt = self.match.geometry.query(self.mode, ids, state.observation_ref, state.current.view_revision)
        if receipt.reason:
            self.note = receipt.reason

    def select(self, object_id):
        if self.mode in ("distance", "los"):
            if object_id in self.selected:
                self.selected.remove(object_id)
            else:
                self.selected = (self.selected + [object_id])[-2:]
        else:
            self.selected = [object_id]
        self.invalidate()

    def query(self, mode):
        if mode == "move":
            self.mode = self.ORDERS[(self.ORDERS.index(self.mode) + 1) % len(self.ORDERS)] if self.mode in self.ORDERS else "advance"
        else:
            self.mode = None if self.mode == mode else mode
        self.invalidate()

    def clear(self):
        self.mode = None
        self.selected.clear()
        self.match.geometry.clear()
