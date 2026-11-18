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
