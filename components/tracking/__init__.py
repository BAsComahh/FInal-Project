"""Optional video trackers initialized from the same registered instance masks."""

from pathlib import Path
import sys


def create_tracker(name, *, model_id=None, device=None, cache_dir=None):
    cache = Path(cache_dir) if cache_dir is not None else Path(__file__).resolve().parents[2] / "outputs/model_cache"
    if name == "sam3":
        if model_id is not None:
            raise ValueError("Use --segmentor for SAM3; --tracker-model is for Cutie or EdgeTAM")
        return None
    # Expose optional packages before SAM3 imports Transformers and caches their availability.
    dependencies = Path(__file__).resolve().parents[2] / "outputs/tracking_dependencies"
    if dependencies.is_dir() and str(dependencies) not in sys.path:
        sys.path.insert(0, str(dependencies))
    if name == "cutie":
        from .cutie import CutieTracker

        return CutieTracker(model_id, device, cache / "cutie")
    if name == "edgetam":
        from .edgetam import EdgeTamTracker

        return EdgeTamTracker(model_id, device, cache)
    raise ValueError("tracker must be sam3, cutie or edgetam")
