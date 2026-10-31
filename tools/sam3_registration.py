"""Compatibility command for the desktop frontend."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
