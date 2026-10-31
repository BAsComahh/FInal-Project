"""Select independent targets, then segment, preview and export them together."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import mkdtemp

import cv2
import numpy as np

from components.image_io import save_image as _save_png


def selection_overlay(image, result):
    return batch_overlay(image, [result])


def batch_overlay(image, results):
    canvas = image.copy()
    rng = np.random.default_rng(42)
    for index, result in enumerate(results, start=1):
        color = tuple(int(v) for v in rng.integers(60, 255, size=3))
        if result is None:
            continue
        mask = result["mask"]
        canvas[mask] = (canvas[mask] * 0.5 + np.asarray(color) * 0.5).astype(np.uint8)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(canvas, contours, -1, color, 1)
        if result["box"] is not None:
            x1, y1, x2, y2 = result["box"]
            cv2.putText(canvas, str(index), (x1, max(15, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return canvas


def cutout_gallery(image, results, *, start_index=1):
    """Show every selected target on a checkerboard, with matching numbers."""
    columns = min(2, max(1, len(results)))
    rows = max(1, (len(results) + columns - 1) // columns)
    tile = 180
    canvas = np.full((rows * tile, columns * tile, 3), 45, dtype=np.uint8)
    for index, result in enumerate(results):
        row, column = divmod(index, columns)
        top, left = row * tile, column * tile
        label = f"{index + start_index}: empty"
        if result is not None and result["box"] is not None:
            x1, y1, x2, y2 = result["box"]
            crop, mask = image[y1:y2, x1:x2], result["mask"][y1:y2, x1:x2]
            scale = min((tile - 16) / crop.shape[1], (tile - 38) / crop.shape[0])
            width, height = max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))
            crop = cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR)
            mask = cv2.resize(mask.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST).astype(bool)
            yy, xx = np.indices((height, width))
            background = np.where((xx // 10 + yy // 10) % 2, 180, 225).astype(np.uint8)
            preview = np.repeat(background[:, :, None], 3, axis=2)
            preview[mask] = crop[mask]
            y, x = top + 30 + (tile - 38 - height) // 2, left + (tile - width) // 2
            canvas[y:y + height, x:x + width] = preview
            if result.get("score") is None:
                label = f"{index + start_index}: polygon"
            else:
                score_name = "score" if result.get("score_type") == "instance_score" else "IoU"
                label = f"{index + start_index}: {score_name} {result['score']:.2f}"
        cv2.putText(canvas, label, (left + 8, top + 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (240, 240, 240), 1, cv2.LINE_AA)
    return canvas


def _write_selection(image, result, output, source):
    output.mkdir(parents=True, exist_ok=True)
    mask = result["mask"].astype(np.uint8) * 255
    _save_png(output / "mask.png", mask)
    _save_png(output / "overlay.png", selection_overlay(image, result))
    cutout_path = None
    if result["box"] is not None:
        x1, y1, x2, y2 = result["box"]
        cutout = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2BGRA)
        cutout[:, :, 3] = mask[y1:y2, x1:x2]
        _save_png(output / "target.png", cutout)
        cutout_path = "target.png"
    metadata = {key: value for key, value in result.items() if key != "mask"}
    metadata.update(image=source, width=image.shape[1], height=image.shape[0],
                    score_type=result.get("score_type", "predicted_iou"), box_format="xyxy_exclusive",
                    mask="mask.png", cutout=cutout_path)
    (output / "selection.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def save_selection(image, result, output_dir, *, source=None):
    """Save one confirmed selection, including a tightly cropped RGBA cutout."""
    if result is None or result["box"] is None:
        raise ValueError("No non-empty selection to save")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = Path(mkdtemp(prefix="selection_", dir=output_dir))
    _write_selection(image, result, output, source)
    return output


def save_selections(image, results, output_dir, *, source=None):
    """Save all targets from one S action under a single batch directory."""
    if any(result is None for result in results):
        raise ValueError("Finish segmenting all targets before saving")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = Path(mkdtemp(prefix="targets_", dir=output_dir))
    instances = []
    for index, result in enumerate(results, start=1):
        name = f"target_{index:03d}"
        _write_selection(image, result, output / name, source)
        instances.append({"index": index, "selection": f"{name}/selection.json",
                          "empty": result["box"] is None})
    _save_png(output / "overlay.png", batch_overlay(image, results))
    _save_png(output / "cutouts.png", cutout_gallery(image, results))
    (output / "instances.json").write_text(
        json.dumps({"image": source, "instances": instances}, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


class PointSegmentationViewer:
    def __init__(self, segmenter, output_dir, *, source=None):
        import matplotlib.pyplot as plt

        # Matplotlib normally reserves S for its figure-save dialog.
        plt.rcParams["keymap.save"] = [key for key in plt.rcParams["keymap.save"] if key != "s"]
        if segmenter.image is None:
            raise ValueError("Call segmenter.set_image before opening the viewer")
        self.segmenter, self.output_dir, self.source = segmenter, output_dir, source
        self.targets, self.history, self.results = [], [], []
        self.busy = False
        self.figure = plt.figure(figsize=(16, 9))
        self.axes = self.figure.add_axes([0.02, 0.13, 0.64, 0.79])
        self.gallery_axes = self.figure.add_axes([0.69, 0.13, 0.29, 0.79])
        self.artist = self.axes.imshow(cv2.cvtColor(segmenter.image, cv2.COLOR_BGR2RGB))
        self.gallery_artist = self.gallery_axes.imshow(np.full((180, 180, 3), 45, dtype=np.uint8))
        self.markers = []
        self.axes.set_title("Selected targets / segmentation")
        self.gallery_axes.set_title("Cutouts appear after S")
        self.axes.axis("off")
        self.gallery_axes.axis("off")
        self.figure.suptitle("Left: new target | Right: exclude from latest target | U: undo | R: reset | S: segment + save | Esc: close")
        self.status = self.figure.text(0.03, 0.035, "Click each target once, then press S.", fontsize=10)
        self.figure.canvas.mpl_connect("button_press_event", self.on_click)
        self.figure.canvas.mpl_connect("key_press_event", self.on_key)
        self.figure._sam3_point_viewer = self

    def refresh(self):
        self.artist.set_data(cv2.cvtColor(batch_overlay(self.segmenter.image, self.results), cv2.COLOR_BGR2RGB))
        for marker in self.markers:
            marker.remove()
        self.markers = []
        for index, target in enumerate(self.targets, start=1):
            for (x, y), label in zip(target["points"], target["labels"]):
                self.markers.append(self.axes.scatter([x], [y], c="lime" if label else "red",
                                                      marker="+" if label else "x", s=90, linewidths=2))
                if label:
                    self.markers.append(self.axes.annotate(str(index), (x, y), xytext=(6, 6),
                                                          textcoords="offset points", color="yellow"))
        gallery = cutout_gallery(self.segmenter.image, self.results)
        self.gallery_artist.set_data(cv2.cvtColor(gallery, cv2.COLOR_BGR2RGB))
        height, width = gallery.shape[:2]
        self.gallery_artist.set_extent((-0.5, width - 0.5, height - 0.5, -0.5))
        self.gallery_axes.set_xlim(-0.5, width - 0.5)
        self.gallery_axes.set_ylim(height - 0.5, -0.5)
        self.gallery_axes.set_title(f"Cutouts ({len(self.results)})" if self.results else "Cutouts appear after S")
        self.figure.canvas.draw_idle()

    def selection_changed(self):
        self.results = []
        self.status.set_text(f"{len(self.targets)} targets selected. Press S to segment all, preview and save.")
        self.refresh()

    def infer_and_save(self):
        import matplotlib.pyplot as plt

        if not self.targets:
            self.status.set_text("Click at least one target before pressing S.")
            self.figure.canvas.draw_idle()
            return
        self.busy = True
        self.results = []
        try:
            for index, target in enumerate(self.targets, start=1):
                self.status.set_text(f"Segmenting target {index}/{len(self.targets)}... first target loads SAM3.")
                self.figure.canvas.draw_idle()
                plt.pause(0.01)
                # Each group describes one independent object, rather than
                # treating all left clicks as foreground points for one mask.
                self.results.append(self.segmenter.segment(target["points"], target["labels"]))
            self.refresh()
            output = save_selections(self.segmenter.image, self.results, self.output_dir, source=self.source)
            count = sum(result["box"] is not None for result in self.results)
            self.status.set_text(f"{count}/{len(self.targets)} targets extracted. Saved: {output}")
            print(f"Saved {count}/{len(self.targets)} targets: {output.resolve()}", flush=True)
        except (ImportError, OSError, ValueError, RuntimeError, cv2.error) as error:
            self.status.set_text(str(error))
            print(f"Segmentation failed: {error}", file=sys.stderr, flush=True)
        finally:
            self.busy = False
            self.refresh()

    def on_click(self, event):
        if self.busy or event.inaxes is not self.axes or event.button not in (1, 3):
            return
        toolbar = getattr(self.figure.canvas, "toolbar", None)
        if toolbar is not None and toolbar.mode:
            return
        if event.xdata is None or event.ydata is None:
            return
        height, width = self.segmenter.image.shape[:2]
        if not (0 <= event.xdata < width and 0 <= event.ydata < height):
            return
        if event.button == 3 and not self.targets:
            self.status.set_text("Select a target with a left click before adding exclusions.")
            self.figure.canvas.draw_idle()
            return
        self.history.append(deepcopy(self.targets))
        point = [float(event.xdata), float(event.ydata)]
        if event.button == 1:
            self.targets.append({"points": [point], "labels": [1]})
        else:
            self.targets[-1]["points"].append(point)
            self.targets[-1]["labels"].append(0)
        self.selection_changed()

    def on_key(self, event):
        import matplotlib.pyplot as plt

        if event.key == "escape":
            plt.close(self.figure)
            return
        if self.busy:
            return
        if event.key == "u" and self.history:
            self.targets = self.history.pop()
            self.selection_changed()
        elif event.key == "r":
            self.targets.clear()
            self.history.clear()
            self.selection_changed()
        elif event.key == "s":
            self.infer_and_save()

    def show(self):
        import matplotlib.pyplot as plt

        plt.show()
