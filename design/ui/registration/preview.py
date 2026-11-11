"""One-window Qt registration study using saved masks, without model inference."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "outputs/ui_preview/deps"))

import cv2
import numpy as np
from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider

DEFAULT_REFERENCE = ROOT / "outputs/sam3_registration/frame_458b250a48ea"


class BoardImage(QQuickImageProvider):
    def __init__(self, image):
        super().__init__(QQuickImageProvider.Image)
        self.image = image

    def requestImage(self, image_id, size, requested_size):
        return self.image


class RegistrationPreview(QObject):
    changed = Signal()

    def __init__(self, reference=DEFAULT_REFERENCE):
        super().__init__()
        frame = cv2.imread(str(reference / "frame.png"))
        if frame is None:
            raise ValueError(f"Saved registration frame unavailable: {reference}")
        self.height, self.width = frame.shape[:2]
        rows = json.loads((reference / "instances.json").read_text(encoding="utf-8"))["instances"]
        self.masks, self.boxes = [], []
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        for row in rows:
            if row["empty"]:
                continue
            mask = cv2.imread(str(reference / Path(row["selection"]).parent / "mask.png"), cv2.IMREAD_GRAYSCALE)
            if mask is None or mask.shape != frame.shape[:2]:
                raise ValueError("The saved mask must match the registration frame.")
            mask = mask > 0
            yy, xx = np.nonzero(mask)
            self.masks.append(mask)
            self.boxes.append(dict(x=int(xx.min()), y=int(yy.min()),
                                   w=int(xx.max() - xx.min() + 1), h=int(yy.max() - yy.min() + 1)))
            rgb[mask] = (rgb[mask] * .72 + np.array([65, 157, 205]) * .28).astype(np.uint8)
        self.image = QImage(rgb.data, self.width, self.height, rgb.strides[0], QImage.Format_RGB888).copy()
        catalog = json.loads((ROOT / "inputs/units.video_estimate.json").read_text(encoding="utf-8"))["unit_types"]
        self.types = [dict(name=f"Type {i + 1}", size=f"{row['dimension']['width_mm']} × {row['dimension']['depth_mm']} mm")
                      for i, row in enumerate(catalog)]
        self.history = []
        self.assignments, self.points = {}, []
        self.selected, self.mode, self.locked = -1, "Assign", False
        self.note = "Choose a mask, then a type from list A or B."

    @Property("QVariantMap", notify=changed)
    def state(self):
        objects = [dict(box, index=i, label=self.assignments.get(i, f"Mask {i + 1}"))
                   for i, box in enumerate(self.boxes)]
        return dict(objects=objects, types=self.types, points=self.points,
                    selected=self.selected, mode=self.mode, locked=self.locked,
                    assigned=len(self.assignments), total=len(self.masks), undo=bool(self.history),
                    note=self.note, width=self.width, height=self.height)

    def remember(self):
        self.history.append((self.assignments.copy(), deepcopy(self.points)))

    @Slot(str)
    def setMode(self, mode):
        if not self.locked:
            self.mode = mode
            self.note = ("Left click: positive. Right click: negative. Prompts are visual only."
                         if mode == "Points" else "Choose a mask, then a type from list A or B.")
            self.changed.emit()

    @Slot(float, float, bool)
    def click(self, x, y, positive):
        if self.locked or not (0 <= x < self.width and 0 <= y < self.height):
            return
        if self.mode == "Points":
            self.remember()
            self.points.append(dict(x=x, y=y, positive=positive))
            self.note = "Prompt added to the preview. Saved masks stay unchanged; SAM is not running."
        else:
            self.selected = next((i for i in reversed(range(len(self.masks))) if self.masks[i][int(y), int(x)]), -1)
            self.note = (f"Mask {self.selected + 1} selected. Choose a type."
                         if self.selected >= 0 else "Click one of the blue masks to assign its type.")
        self.changed.emit()

    @Slot(str, int)
    def assign(self, side, type_index):
        if self.locked or self.selected < 0:
            return
        prefix = f"{side}{type_index + 1}."
        if self.assignments.get(self.selected, "").startswith(prefix):
            return
        self.remember()
        used = set(self.assignments.values())
        number = next(i for i in range(1, len(self.masks) + 2) if f"{prefix}{i}" not in used)
        self.assignments[self.selected] = f"{prefix}{number}"
        self.note = f"Mask {self.selected + 1} → {self.assignments[self.selected]}. This assignment is a local draft."
        self.changed.emit()

    @Slot()
    def undo(self):
        if self.history and not self.locked:
            self.assignments, self.points = self.history.pop()
            self.note = "Last draft change undone."
            self.changed.emit()

    @Slot()
    def reset(self):
        self.assignments, self.points, self.history = {}, [], []
        self.selected, self.mode, self.locked = -1, "Assign", False
        self.note = "Choose a mask, then a type from list A or B."
        self.changed.emit()

    @Slot()
    def finish(self):
        self.locked = True
        self.note = "Preview finished. Nothing was saved. Reset draft to try again."
        self.changed.emit()


def create_preview(app, reference=DEFAULT_REFERENCE, *, visible=True):
    # The Windows offscreen plugin does not discover system fonts itself.
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    preview = RegistrationPreview(reference)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("board", BoardImage(preview.image))
    engine.rootContext().setContextProperty("preview", preview)
    engine.setInitialProperties({"visible": visible})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Registration.qml"))))
    if not engine.rootObjects():
        raise RuntimeError("Registration preview QML failed to load.")
    return engine, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    args = parser.parse_args()
    app = QGuiApplication(sys.argv[:1])
    engine, preview = create_preview(app, args.reference)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
