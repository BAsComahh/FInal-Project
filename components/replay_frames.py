"""Rectified source-frame files shared by history recording and replay."""
from pathlib import Path
from uuid import uuid4

from components.image_io import save_image


def replay_frame_path(history_path, key):
    version, sequence = key
    return Path(history_path).parent / "replay_frames" / f"v{version}_s{sequence}.jpg"


def save_replay_frame(history_path, key, frame):
    path = replay_frame_path(history_path, key)
    temporary = path.with_name(f".{path.stem}_{uuid4().hex}.jpg")
    try:
        save_image(temporary, frame)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
