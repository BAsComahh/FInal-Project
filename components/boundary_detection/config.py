"""Pipeline switch definitions and a small, validated TOML configuration."""

from pathlib import Path
from math import isfinite
from dataclasses import dataclass
import tomllib

from .scale import image_short_side, percent_to_length


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).with_name("config.toml")

# Preserve the previously tuned table4 thresholds at its 512-pixel short side.
LENGTH_DEFAULTS_PCT = {"min_line_length_pct": 39.0625, "merge_min_length_pct": 3.90625,
                       "merge_distance_pct": 1.171875, "merge_gap_pct": 9.765625,
                       "connection_distance_pct": 3.90625}


@dataclass
class BoundaryParameters:
    """Algorithm defaults shared by the component API and command-line tool."""

    image: Path | None = None
    config: Path = DEFAULT_CONFIG
    border_region_pct: float | None = None
    min_line_length_pct: float | None = None
    blur_size: int = 5
    refine: str = "std"
    angle_tolerance: float = 15
    merge_min_length_pct: float | None = None
    merge_angle: float = 6
    merge_distance_pct: float | None = None
    merge_gap_pct: float | None = None
    merge_min_coverage: float = 0.5
    connection_distance_pct: float | None = None


def resolve_lengths(args, image_shape):
    """Resolve each geometric percentage once, using one isotropic image scale."""
    reference = image_short_side(image_shape)
    return {key.removesuffix("_pct"): percent_to_length(getattr(args, key, None), reference,
                                                       name=key, allow_zero=key == "merge_gap_pct")
            for key in LENGTH_DEFAULTS_PCT}

PIPELINE = [("blur", "Gaussian blur"), ("detection", "Detect LSD segments"),
            ("lsd_refinement", "LSD refinement"),
            ("merge", "Merge segments"), ("repeat_merge", "Repeat until stable"),
            ("length_filter", "Final length filter"), ("axis_filter", "Final direction filter"),
            ("border_selection", "Select longest sides"), ("search_region", "Limit side regions"),
            ("closure", "Check closed frame"), ("completion", "Complete quadrilateral")]
CONSTRAINTS = [("merge_source_length", "Source length"), ("merge_axis", "Source axis direction"),
               ("merge_angle", "Group angle"), ("merge_distance", "Line distance"),
               ("merge_gap", "Segment gap"), ("merge_coverage", "Observed coverage")]


def load_config(path=DEFAULT_CONFIG):
    """Read a full or partial config; reject unknown keys and invalid types."""
    path = Path(path)
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Invalid config {path}: {error}") from error
    sections = {
        "steps": {key: key for key, _ in PIPELINE},
        "merge_checks": {key.removeprefix("merge_"): key for key, _ in CONSTRAINTS},
    }
    switches = {key: True for key, _ in PIPELINE + CONSTRAINTS}
    switches.update(length_filter=True, merge_source_length=False)
    region_pct = 100 / 3
    geometry = dict(LENGTH_DEFAULTS_PCT)
    for section, settings in data.items():
        if section == "geometry":
            if not isinstance(settings, dict) or set(settings) - geometry.keys():
                raise ValueError("[geometry] accepts only explicit *_pct length settings")
            for key, value in settings.items():
                percent_to_length(value, 1, name=key, allow_zero=key == "merge_gap_pct")
                geometry[key] = value
            continue
        if section == "border_selection":
            if not isinstance(settings, dict) or set(settings) - {"region_pct"}:
                raise ValueError("[border_selection] accepts region_pct (percentage), replacing region_ratio")
            region_pct = settings.get("region_pct", region_pct)
            if (isinstance(region_pct, bool) or not isinstance(region_pct, (int, float))
                    or not isfinite(region_pct) or not 0 < region_pct <= 50):
                raise ValueError("border_selection.region_pct must be in (0, 50]")
            continue
        if section not in sections or not isinstance(settings, dict):
            raise ValueError(f"Unknown config section: {section}")
        for key, value in settings.items():
            if key not in sections[section]:
                raise ValueError(f"Unknown config switch: {section}.{key}")
            if not isinstance(value, bool):
                raise ValueError(f"Config switch {section}.{key} must be true or false")
            switches[sections[section][key]] = value
    return {"switches": switches, "border_region_pct": region_pct, "geometry": geometry}


def initial_switches(args):
    """Command-line overrides take precedence over config defaults."""
    config = load_config(getattr(args, "config", DEFAULT_CONFIG))
    switches = config["switches"]
    for key, default in config["geometry"].items():
        old_key = key.removesuffix("_pct")
        if hasattr(args, old_key):
            raise ValueError(f"{old_key} was pixel-based; replace it with {key} in percent.")
        if getattr(args, key, None) is None:
            setattr(args, key, default)
        percent_to_length(getattr(args, key), 1, name=key, allow_zero=key == "merge_gap_pct")
    if hasattr(args, "border_region_ratio"):
        raise ValueError("Replace border_region_ratio with border_region_pct (0..50 percent).")
    if getattr(args, "border_region_pct", None) is None:
        args.border_region_pct = config["border_region_pct"]
    region_pct = args.border_region_pct
    if (isinstance(region_pct, bool) or not isinstance(region_pct, (int, float))
            or not isfinite(region_pct) or not 0 < region_pct <= 50):
        raise ValueError("border-region-pct must be in (0, 50]")
    for key in switches:
        disabled = getattr(args, "no_" + key, None)
        if disabled is not None:
            switches[key] = not disabled
    return switches


def add_switch_arguments(parser):
    """Keep existing --no-* flags, with matching flags to override config off."""
    for key, label in PIPELINE + CONSTRAINTS:
        name = key.replace("_", "-")
        # Preserve numeric/mode options already using these names.
        enable_name = {"merge_angle": "check-merge-angle",
                       "merge_distance": "check-merge-distance", "merge_gap": "check-merge-gap"}.get(key, name)
        group = parser.add_mutually_exclusive_group()
        group.add_argument(f"--{enable_name}", dest="no_" + key, action="store_false",
                           default=None, help=f"Enable {label.lower()} (override config)")
        aliases = [f"--no-{name}"]
        if key == "repeat_merge":
            aliases.append("--single-pass")
        group.add_argument(*aliases, dest="no_" + key, action="store_true",
                           default=None, help=f"Disable {label.lower()} (override config)")
