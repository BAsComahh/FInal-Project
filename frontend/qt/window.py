"""Build one QML window for one match, also usable with an injected application."""
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .bridge import MatchBridge


class Appearance(QObject):
    """Window-local light/dark choice; starts dark and is intentionally not persisted."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self._dark = True

    @Property(bool, notify=changed)
    def dark(self):
        return self._dark

    @Slot()
    def toggle(self):
        self._dark = not self._dark
        self.changed.emit()

_WINDOWS_FONTS = (
    "segoeui.ttf",
    "segoeuib.ttf",
    "seguisb.ttf",
    "consola.ttf",
    "consolab.ttf",
    "bahnschrift.ttf",
)


def create_window(app, match, *, visible=True, preview_width=960):
    fonts_dir = Path("C:/Windows/Fonts")
    for filename in _WINDOWS_FONTS:
        font_path = fonts_dir / filename
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    QQuickStyle.setStyle("Basic")
    bridge = MatchBridge(match)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("match", bridge.images)
    engine.rootContext().setContextProperty("ui", bridge)
    engine.rootContext().setContextProperty("flow", bridge.flow)
    appearance = Appearance()
    engine._appearance = appearance  # keep the QObject alive for the engine lifetime
    engine.rootContext().setContextProperty("appearance", appearance)
    engine.setInitialProperties({"visible": visible, "width": max(820, preview_width + 340)})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Main.qml"))))
    if not engine.rootObjects():
        bridge.close()
        raise RuntimeError("Qt registration window failed to load.")
    app.aboutToQuit.connect(bridge.close)
    return engine, bridge
