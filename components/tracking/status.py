"""Application-level tracking validity, independent of model session memory."""

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite


@dataclass
class UnitTracking:
    status: str = "tracking"
    visibility: bool | None = None
    disappeared_time: float | None = None
    frame_index: int = -1
    timestamp_seconds: float | None = None
    calibration_version: int = -1
    active: bool = True
    last_accepted_position: dict | None = None


def validate_disappearance_seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError("TRACKING_DISAPPEARANCE_SECONDS must be a positive finite number.")
    return float(value)


def update_tracking(records, roster, prediction, metadata, disappearance_seconds):
    """Annotate raw results; a failed unit cannot recover just by returning a mask."""
    timeout = validate_disappearance_seconds(disappearance_seconds)
    stamp = metadata["timestamp_seconds"]
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not isfinite(stamp) or stamp < 0:
        raise ValueError("Tracking observations require a non-negative finite source timestamp.")
    frame_index = metadata["frame_index"]
    version = metadata.get("calibration_version", 0)
    visible = {obj for obj, mask in zip(prediction["object_ids"], prediction["masks"]) if mask.any()}
    unavailable, estimated, inactive = [], [], []
    for object_id, unit_id in roster.bindings.items():
        unit = roster.units[unit_id]
        profile = {**roster.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
        record = records.setdefault(unit_id, UnitTracking())
        active = profile.get("routed") is not True and profile.get("removed") is not True
        if not active:
            record.active = False
            inactive.append(object_id)
            continue
        if not record.active and record.status != "failed":
            record.status, record.disappeared_time, record.frame_index = "tracking", None, -1
        record.active = True
        if (frame_index > record.frame_index
                or (frame_index == record.frame_index and version > record.calibration_version)):
            record.visibility = object_id in visible
            record.frame_index = frame_index
            record.timestamp_seconds = float(stamp)
            record.calibration_version = version
            if record.status != "failed":
                if record.visibility:
                    record.status, record.disappeared_time = "tracking", None
                else:
                    if record.disappeared_time is None:
                        record.disappeared_time = float(stamp)
                    record.status = "failed" if stamp - record.disappeared_time >= timeout else "pending"
            tray = prediction.get("trays", {}).get(object_id)
            if record.status == "tracking" and record.visibility and tray is not None:
                record.last_accepted_position = {
                    "corners_mm": deepcopy(tray["corners_plane"]), "frame_index": frame_index,
                    "timestamp_seconds": float(stamp), "calibration_version": version,
                }
        if record.status != "tracking" or object_id not in visible:
            unavailable.append(object_id)
        if record.status == "failed" and object_id in visible:
            estimated.append(object_id)
    return {**prediction, "unavailable_ids": unavailable, "estimated_ids": estimated, "inactive_ids": inactive}
