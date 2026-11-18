"""Window-local selection; never owns tracking, facing or Missing state."""
def unit_uncertainties(state, object_id):
    """Attention flags, independent of the algorithm's retained provenance."""
    prediction = state.current.prediction or {}
    unit_id = state.units.bindings.get(object_id)
    tracking = state.tracking.get(unit_id)
    if (object_id in prediction.get("inactive_ids", ()) or
            tracking is not None and (not tracking.active or tracking.status == "pending")):
        return {}
    issues = {}
    if tracking is not None and tracking.status == "failed":
        phase = tracking.recovery_phase
        if tracking.recovery_update_error:
            issues["mask"] = f"Recovery failed: {tracking.recovery_update_error}"
            if phase == "review":
                issues["mask"] += " · Candidate ready for review"
        elif phase in ("queued", "searching"):
            return {}
        elif phase == "review":
            issues["mask"] = "Candidate ready for review"
        elif tracking.visibility is False:
            issues["mask"] = "Estimated"
        if ("mask" in issues and tracking.recovery_note and
                (not tracking.recovery_update_error or tracking.recovery_update_error not in tracking.recovery_note)):
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
