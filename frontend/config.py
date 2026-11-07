"""Application settings edited before starting the video frontend."""

from pathlib import Path

# Source-video seconds of consecutive missing-mask observations before failure.
TRACKING_DISAPPEARANCE_SECONDS = 10.0
DEFAULT_TRACKER = "edgetam"

# Experimental tray-motion event thresholds, measured in geometry-source time.
MOTION_POSITION_TOLERANCE_MM = 10.0
MOTION_ROTATION_TOLERANCE_DEG = 10.0
MOTION_SETTLE_SECONDS = 5.0

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNITS = PROJECT_ROOT / "inputs/units.video_estimate.json"
DEFAULT_BOARD_SIZE_IN = (72, 48)
