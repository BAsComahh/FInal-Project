"""Build one QML window for one match, also usable with an injected application."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .bridge import MatchBridge


def create_window(app, match, *, visible=True, preview_width=960):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    QQuickStyle.setStyle("Basic")
    bridge = MatchBridge(match)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("match", bridge.images)
    engine.rootContext().setContextProperty("ui", bridge)
    engine.rootContext().setContextProperty("flow", bridge.flow)
    engine.setInitialProperties({"visible": visible, "width": max(820, preview_width + 340)})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Main.qml"))))
    if not engine.rootObjects():
        bridge.close()
        raise RuntimeError("Qt registration window failed to load.")
    app.aboutToQuit.connect(bridge.close)
    return engine, bridge
