"""Application settings edited before starting the video frontend."""

from pathlib import Path

# Source-video seconds of consecutive missing-mask observations before failure.
TRACKING_DISAPPEARANCE_SECONDS = 10.0
DEFAULT_TRACKER = "edgetam"
DEFAULT_INFERENCE_FPS = 1.0
DEFAULT_TRAY_SEARCH = "adaptive"
# Trial mask-stability gates, relative to the last actual rectangle fit.
TRAY_STABLE_CENTROID_PCT = 5.0
TRAY_STABLE_MIN_MASK_IOU = 0.90
TRAY_FAILED_RETRY_SECONDS = 5.0

# User-selected experimental retrieval thresholds, not calibrated probabilities.
AUTO_RECOVERY_ENABLED = True  # EdgeTAM only; other trackers keep their failure display.
AUTO_RECOVERY_SIMILARITY = 0.85
AUTO_RECOVERY_MARGIN = 0.10
AUTO_RECOVERY_PROMPT = "miniature"
AUTO_RECOVERY_DETECTION_THRESHOLD = 0.30

# Experimental tray-motion event thresholds, measured in geometry-source time.
MOTION_POSITION_TOLERANCE_MM = 10.0
MOTION_ROTATION_TOLERANCE_DEG = 10.0
MOTION_SETTLE_SECONDS = 5.0

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/sam3_registration"
FACING_TRACKING_ENABLED = False  # Retain D32 code; current runtime does not use facing.
DVMNET_FACING_ENABLED = True
DVMNET_FACING_CACHE = PROJECT_ROOT / "outputs/model_cache/dvmnet"
# Trial ambiguity guard between tray-edge angular errors; not model confidence.
FACING_EDGE_MARGIN_DEG = 20.0
# Trial lightweight checks; these are not calibrated identity/direction probabilities.
FACING_CHECK_MIN_SIMILARITY = 0.35
FACING_CHECK_ALTERNATIVE_MARGIN = 0.15
FACING_CHECK_CONSECUTIVE = 2
FACING_CHECK_MIN_COVERAGE = 0.25
FACING_RETRY_APPEARANCE_CHANGE = 0.12
FACING_RETRY_MIN_SECONDS = 2.0  # Geometry-source time; new appearance is also required.
DEFAULT_UNITS = PROJECT_ROOT / "inputs/units.video_estimate.json"
DEFAULT_BOARD_SIZE_IN = (72, 48)
