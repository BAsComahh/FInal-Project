"""Qt Quick client of the headless match application."""
from importlib.util import find_spec
from pathlib import Path
import sys

# Support existing local Qt installations in the legacy dependency directory.
if find_spec("PySide6") is None:
    dependencies = Path(__file__).resolve().parents[2] / "outputs/ui_preview/deps"
    if dependencies.is_dir():
        sys.path.insert(0, str(dependencies))
