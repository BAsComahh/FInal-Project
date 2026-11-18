"""Command-line options for the Qt video client."""
import argparse
from pathlib import Path

from application.config import DEFAULT_INFERENCE_FPS, DEFAULT_TRACKER, DEFAULT_UNITS, PROJECT_ROOT


def video_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("video", type=Path)
    parser.add_argument("--registration", dest="registration_archive", type=Path,
                        help="Load a completed registration directory or prompts.json; its saved frame sets the start")
    parser.add_argument("--units", type=Path, default=DEFAULT_UNITS,
                        help="JSON unit-type catalog (default: ABC test catalog, inputs/units.video_estimate.json)")
    parser.add_argument("--start", type=float, default=0, help="Local clip start in seconds")
    parser.add_argument("--seconds", type=float, help="Optional playback interval; omitted plays to the end of the video")
    parser.add_argument("--inference-fps", type=float, default=DEFAULT_INFERENCE_FPS,
                        help=f"Tracking update rate limit in Hz (default: {DEFAULT_INFERENCE_FPS:g} Hz = 1.0s interval)")
    parser.add_argument("--preview-width", type=int, default=960, help="Preview width; prompts and masks use full rectified-frame coordinates")
    parser.add_argument("--device", help="Torch device; automatically choose the GPU with the most memory")
    parser.add_argument("--segmentor", default="facebook/sam3", help="SAM3 checkpoint or model ID for initial segmentation")
    parser.add_argument("--tracker", choices=("sam3", "cutie", "edgetam"), default=DEFAULT_TRACKER,
                        help=f"Video propagation backend (default: {DEFAULT_TRACKER}); first-frame registration always uses SAM3")
    parser.add_argument("--tracker-model", help="Optional local checkpoint or HF model ID for the selected candidate")
    parser.add_argument("--tracker-cache", type=Path, help="Candidate model cache root (default: outputs/model_cache)")
    parser.add_argument("--profile", action="store_true", help="Synchronize GPU phase timing; may add profiling overhead")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs/sam3_registration")
    return parser


def match_options(args):
    values = vars(args).copy()
    values["model_id"] = values.pop("segmentor")
    values["tray_search"] = "adaptive"
    values.pop("video")
    values.pop("preview_width")
    return values
