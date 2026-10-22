"""Pipeline switch definitions and a small, validated TOML configuration."""

from pathlib import Path
from math import isfinite
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).with_name("config.toml")

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
    region_ratio = 1 / 3
    for section, settings in data.items():
        if section == "border_selection":
            if not isinstance(settings, dict) or set(settings) - {"region_ratio"}:
                raise ValueError("[border_selection] accepts only region_ratio")
            region_ratio = settings.get("region_ratio", region_ratio)
            if (isinstance(region_ratio, bool) or not isinstance(region_ratio, (int, float))
                    or not isfinite(region_ratio) or not 0 < region_ratio <= 0.5):
                raise ValueError("border_selection.region_ratio must be in (0, 0.5]")
            continue
        if section not in sections or not isinstance(settings, dict):
            raise ValueError(f"Unknown config section: {section}")
        for key, value in settings.items():
            if key not in sections[section]:
                raise ValueError(f"Unknown config switch: {section}.{key}")
            if not isinstance(value, bool):
                raise ValueError(f"Config switch {section}.{key} must be true or false")
            switches[sections[section][key]] = value
    return {"switches": switches, "border_region_ratio": region_ratio}


def initial_switches(args):
    """Command-line overrides take precedence over config defaults."""
    config = load_config(getattr(args, "config", DEFAULT_CONFIG))
    switches = config["switches"]
    if getattr(args, "border_region_ratio", None) is None:
        args.border_region_ratio = config["border_region_ratio"]
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
