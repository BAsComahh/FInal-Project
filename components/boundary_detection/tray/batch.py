"""Apply the existing tray fitter to a matching frame and object masks."""

import cv2

from .detector import fit_tray


def fit_registered_trays(frame, prediction, context):
    """Return observed proposals keyed by SAM object ID, plus per-unit errors.

    context has image_to_plane and sizes (object_id -> width/depth in mm).
    Missing dimensions and empty masks produce no tray; no boxes are invented.
    """
    trays, errors = {}, {}
    for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
        size = context["sizes"].get(object_id)
        if size is None or not mask.any():
            continue
        try:
            result = fit_tray(frame, mask, size, image_to_plane=context["image_to_plane"])
            if result["success"]:
                trays[object_id] = result["best"]
            else:
                errors[object_id] = "Tray fit needs review"
        except (ValueError, cv2.error) as error:
            errors[object_id] = str(error)
    return trays, errors
