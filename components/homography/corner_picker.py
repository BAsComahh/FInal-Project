"""Pick four original-image pixel coordinates without detecting corners."""

import json
from pathlib import Path

import cv2
import numpy as np

from .geometry import CORNER_NAMES, compute_homography
from .image import _load_image


class CornerPicker:
    def __init__(self, image_path, output_path):
        import matplotlib.pyplot as plt

        plt.rcParams["keymap.save"] = [key for key in plt.rcParams["keymap.save"] if key != "s"]
        self.image_path, self.output_path = Path(image_path), Path(output_path)
        self.image = _load_image(self.image_path)
        self.points, self.labels = [], []
        self.figure, self.axes = plt.subplots(figsize=(14, 9))
        self.figure.subplots_adjust(bottom=0.19)
        self.axes.imshow(cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB))
        self.line, = self.axes.plot([], [], "o-", color="yellow", markersize=6)
        self.axes.set_title("Click TL -> TR -> BR -> BL | U / right click: undo | R: reset | S: save | Esc: close")
        self.axes.set_xlabel("x: pixels from the left")
        self.axes.set_ylabel("y: pixels from the top")
        self.note = self.figure.text(0.06, 0.045, "", fontsize=10)
        self.figure.canvas.mpl_connect("button_press_event", self.on_click)
        self.figure.canvas.mpl_connect("key_press_event", self.on_key)
        self.figure._homography_corner_picker = self
        self.refresh()

    def command(self):
        # Quote for PowerShell, including image paths containing apostrophes.
        quoted_path = "'" + str(self.image_path).replace("'", "''") + "'"
        coordinates = " ".join(str(value) for point in self.points for value in point)
        return ("conda run --no-capture-output -n sam3-demo python -m tools.homography "
                + quoted_path + " --corners " + coordinates)

    def refresh(self, message=None):
        for label in self.labels:
            label.remove()
        self.labels = []
        if self.points:
            polygon = self.points + self.points[:1] if len(self.points) == 4 else self.points
            points = np.asarray(polygon)
            self.line.set_data(points[:, 0], points[:, 1])
            for name, point in zip(CORNER_NAMES, self.points):
                self.labels.append(self.axes.annotate(f"{name} {tuple(point)}", point, xytext=(8, 8),
                                                     textcoords="offset points", color="yellow"))
        else:
            self.line.set_data([], [])
        coordinates = " | ".join(f"{name}: ({x}, {y})" for name, (x, y) in zip(CORNER_NAMES, self.points))
        if message is None:
            message = f"Next: {CORNER_NAMES[len(self.points)]}" if len(self.points) < 4 else "Four points selected. Press S to save and print the Homography command."
        self.note.set_text(coordinates + "\n" + message)
        self.figure.canvas.draw_idle()

    def on_click(self, event):
        if event.inaxes is not self.axes:
            return
        toolbar = getattr(self.figure.canvas, "toolbar", None)
        if toolbar is not None and toolbar.mode:
            return
        if event.button == 3:
            self.undo()
            return
        if event.button != 1 or event.xdata is None or event.ydata is None:
            return
        if len(self.points) == 4:
            self.refresh("Four points already selected. U to undo, R to reset, S to save.")
            return
        height, width = self.image.shape[:2]
        if not (-0.5 <= event.xdata < width - 0.5 and -0.5 <= event.ydata < height - 0.5):
            return
        point = [int(np.clip(round(event.xdata), 0, width - 1)),
                 int(np.clip(round(event.ydata), 0, height - 1))]
        self.points.append(point)
        print(f"{CORNER_NAMES[len(self.points) - 1]}: {point}", flush=True)
        self.refresh()

    def undo(self):
        if self.points:
            self.points.pop()
        self.refresh()

    def save(self):
        if len(self.points) != 4:
            raise ValueError("Select all four corners in TL, TR, BR, BL order first")
        compute_homography(self.points)  # Reuse the mapping component's geometry validation.
        payload = {"image": str(self.image_path.resolve()), "corner_order": list(CORNER_NAMES),
                   "corners": dict(zip(CORNER_NAMES, self.points)), "command": self.command()}
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {self.output_path.resolve()}\n{self.command()}", flush=True)
        self.refresh(f"Saved: {self.output_path}. Copy the printed command from the terminal.")
        return payload

    def on_key(self, event):
        import matplotlib.pyplot as plt

        if event.key == "escape":
            plt.close(self.figure)
        elif event.key == "u":
            self.undo()
        elif event.key == "r":
            self.points.clear()
            self.refresh()
        elif event.key == "s":
            try:
                self.save()
            except (OSError, ValueError, cv2.error) as error:
                self.refresh(str(error))

    def show(self):
        import matplotlib.pyplot as plt

        plt.show()
