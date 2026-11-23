"""Run the Qt match console for registration, live playback and replay."""
import sys

from application.app import MatchApplication
from frontend.arguments import match_options, video_parser


def main():
    parser = video_parser(__doc__)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import QCoreApplication, QEvent
        from .window import create_window
    except ModuleNotFoundError as error:
        parser.error(f"{error}. Install project dependencies with python -m pip install -r requirements.txt.")
    match = None
    try:
        app = QGuiApplication(sys.argv[:1])
        match = MatchApplication(args.video, **match_options(args))
        engine, bridge = create_window(app, match, preview_width=args.preview_width)
        try:
            return app.exec()
        finally:
            bridge.close()
            # Destroy the QML objects before their context property.
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    finally:
        if match is not None:
            match.close()


if __name__ == "__main__":
    raise SystemExit(main())
