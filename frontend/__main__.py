"""Register objects in video using click prompts and export reference masks/cutouts."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.window import VideoWindow
from frontend.arguments import video_parser, match_options


def main():
    parser = video_parser(__doc__)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        viewer = VideoWindow(args.video, preview_width=args.preview_width, **match_options(args))
        viewer.show()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
