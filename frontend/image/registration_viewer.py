"""Review text detections, add missed targets with points, and remove clutter."""

import cv2
import numpy as np

from .point_viewer import PointSegmentationViewer, batch_overlay, cutout_gallery, save_selections
from components.registration.polygon import polygon_selection


def detection_selections(detection):
    """Convert text detections to the shared single-target export format."""
    results = []
    for mask, score in zip(detection["masks"], detection["scores"]):
        ys, xs = np.nonzero(mask)
        if not len(xs):
            continue
        results.append({
            "mask": mask, "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
            "score": float(score), "score_type": "instance_score", "origin": "automatic",
            "prompt": detection["prompt"], "threshold": detection["threshold"],
            "points": [], "labels": [],
        })
    return results


class RegistrationViewer(PointSegmentationViewer):
    """One retained segmentation per registered target; no semantic labels yet."""

    PAGE_SIZE = 8

    def __init__(self, segmenter, detection, output_dir, *, source=None):
        from matplotlib.widgets import RadioButtons

        super().__init__(segmenter, output_dir, source=source)
        self.initial_results = detection_selections(detection)
        self.results = list(self.initial_results)
        self.page = 0
        self.mode = "SAM point"
        self.vertices = []
        self.vertex_labels = []
        self.polygon_line, = self.axes.plot([], [], "o-", color="yellow", markersize=5, linewidth=1.5)
        self.start_marker = self.axes.scatter([], [], s=220, facecolors="none", edgecolors="yellow", linewidths=2)
        self.figure.suptitle("Left: add / draw | Right: remove | U: undo | C: cancel polygon | R: restore | S: save | Esc: close")
        self.mode_picker = RadioButtons(self.figure.add_axes([0.03, 0.015, 0.14, 0.085]), ["SAM point", "Polygon"])
        self.mode_picker.on_clicked(self.on_mode)
        self.status.set_position((0.19, 0.045))
        self.status.set_wrap(True)
        self.axes.set_title("Registered targets")
        self.status.set_text(f"{len(self.results)} automatic targets. Left click to add; right click a mask or cutout to remove.")
        self.figure.canvas.mpl_connect("scroll_event", self.on_scroll)
        self.figure.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.refresh()

    def refresh(self):
        self.artist.set_data(cv2.cvtColor(batch_overlay(self.segmenter.image, self.results), cv2.COLOR_BGR2RGB))
        for label in self.vertex_labels:
            label.remove()
        self.vertex_labels = []
        if self.vertices:
            points = np.asarray(self.vertices)
            self.polygon_line.set_data(points[:, 0], points[:, 1])
            self.start_marker.set_offsets(points[:1])
            for index, point in enumerate(points):
                label = chr(65 + index) if index < 26 else str(index + 1)
                self.vertex_labels.append(self.axes.annotate(label, point, xytext=(6, 6),
                                                           textcoords="offset points", color="yellow"))
        else:
            self.polygon_line.set_data([], [])
            self.start_marker.set_offsets(np.empty((0, 2)))
        pages = max(1, (len(self.results) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page = min(max(0, self.page), pages - 1)
        start = self.page * self.PAGE_SIZE
        gallery = cutout_gallery(self.segmenter.image, self.results[start:start + self.PAGE_SIZE], start_index=start + 1)
        self.gallery_artist.set_data(cv2.cvtColor(gallery, cv2.COLOR_BGR2RGB))
        height, width = gallery.shape[:2]
        self.gallery_artist.set_extent((-0.5, width - 0.5, height - 0.5, -0.5))
        self.gallery_axes.set_xlim(-0.5, width - 0.5)
        self.gallery_axes.set_ylim(height - 0.5, -0.5)
        self.gallery_axes.set_title(f"{len(self.results)} targets | page {self.page + 1}/{pages} (scroll)")
        self.figure.canvas.draw_idle()

    def on_mode(self, mode):
        if self.busy:
            return
        self.mode = mode
        self.vertices.clear()
        message = "Click vertices in order, then click A again to close and register." if mode == "Polygon" else "Left click to add with SAM; right click to remove a target."
        self.status.set_text(message)
        self.refresh()

    def on_motion(self, event):
        if self.busy or self.mode != "Polygon" or not self.vertices:
            return
        if event.inaxes is self.axes and event.xdata is not None and event.ydata is not None:
            points = np.asarray(self.vertices + [[event.xdata, event.ydata]])
        else:
            points = np.asarray(self.vertices)
        self.polygon_line.set_data(points[:, 0], points[:, 1])
        self.figure.canvas.draw_idle()

    def polygon_click(self, x, y):
        # A screen-space tolerance keeps closing equally easy when zoomed.
        near_start = (self.vertices and np.linalg.norm(
            self.axes.transData.transform([x, y]) - self.axes.transData.transform(self.vertices[0])) <= 12)
        if near_start:
            if len(self.vertices) < 3:
                self.status.set_text("At least three vertices are required before clicking A to close.")
            else:
                try:
                    result = polygon_selection(self.segmenter.image.shape, self.vertices)
                    self.history.append(list(self.results))
                    self.results.append(result)
                    self.vertices.clear()
                    self.page = (len(self.results) - 1) // self.PAGE_SIZE
                    self.status.set_text(f"Registered polygon target {len(self.results)}. Draw another or press S to save.")
                except ValueError as error:
                    self.status.set_text(str(error))
        else:
            self.vertices.append([x, y])
            self.status.set_text(f"{len(self.vertices)} vertices. Click A to close; U to undo a vertex; C to cancel.")
        self.refresh()

    def on_scroll(self, event):
        if self.busy or event.inaxes is not self.gallery_axes:
            return
        self.page += 1 if event.button == "down" else -1
        self.refresh()

    def remove(self, index):
        self.history.append(list(self.results))
        self.results.pop(index)
        self.status.set_text(f"Removed target {index + 1}. {len(self.results)} retained. U to undo; S to save.")
        self.refresh()

    def on_click(self, event):
        import matplotlib.pyplot as plt

        if self.busy or event.button not in (1, 3) or event.xdata is None or event.ydata is None:
            return
        toolbar = getattr(self.figure.canvas, "toolbar", None)
        if toolbar is not None and toolbar.mode:
            return
        if event.inaxes is self.gallery_axes:
            if event.button == 3 and event.xdata >= 0 and event.ydata >= 0:
                start = self.page * self.PAGE_SIZE
                columns = min(2, max(1, len(self.results) - start))
                column, row = int(event.xdata // 180), int(event.ydata // 180)
                index = start + row * columns + column
                if column < columns and start <= index < min(len(self.results), start + self.PAGE_SIZE):
                    self.remove(index)
            return
        if event.inaxes is not self.axes:
            return
        height, width = self.segmenter.image.shape[:2]
        x, y = float(event.xdata), float(event.ydata)
        if not (0 <= x < width and 0 <= y < height):
            return
        if self.mode == "Polygon" and event.button == 1:
            self.polygon_click(x, y)
            return
        hits = [i for i, result in enumerate(self.results) if result["mask"][int(y), int(x)]]
        if hits:
            # Prefer the smaller region if several candidate masks overlap.
            index = min(hits, key=lambda i: np.count_nonzero(self.results[i]["mask"]))
            if event.button == 3:
                self.remove(index)
            else:
                self.page = index // self.PAGE_SIZE
                self.status.set_text(f"Target {index + 1} is already registered. Right click to remove it.")
                self.refresh()
            return
        if event.button != 1:
            return
        self.busy = True
        self.status.set_text("Segmenting the clicked target... first manual addition loads the point model.")
        self.figure.canvas.draw_idle()
        plt.pause(0.01)
        try:
            result = self.segmenter.segment([[x, y]])
            if result["box"] is None:
                self.status.set_text("No mask at this point. Try clicking further inside the target.")
            else:
                result.update(origin="manual", score_type="predicted_iou")
                self.history.append(list(self.results))
                self.results.append(result)
                self.page = (len(self.results) - 1) // self.PAGE_SIZE
                self.status.set_text(f"Added target {len(self.results)}. Review the cutout; S to save all targets.")
        except (ImportError, OSError, ValueError, RuntimeError, cv2.error) as error:
            self.status.set_text(str(error))
            print(f"Cannot add target: {error}", flush=True)
        finally:
            self.busy = False
            self.refresh()

    def on_key(self, event):
        import matplotlib.pyplot as plt

        if event.key == "escape":
            plt.close(self.figure)
            return
        if self.busy:
            return
        if event.key == "c":
            self.vertices.clear()
            self.status.set_text("Unfinished polygon cancelled.")
        elif event.key == "u" and self.vertices:
            self.vertices.pop()
            self.status.set_text(f"Vertex undone. {len(self.vertices)} vertices remain.")
        elif event.key == "u" and self.history:
            self.results = self.history.pop()
            self.status.set_text(f"Undone. {len(self.results)} targets retained.")
        elif event.key == "r":
            self.vertices.clear()
            self.history.append(list(self.results))
            self.results = list(self.initial_results)
            self.page = 0
            self.status.set_text(f"Restored {len(self.results)} automatic detections.")
        elif event.key == "s":
            if self.vertices:
                self.status.set_text("Polygon is not closed. Click A to register it, or C to cancel before saving.")
                self.refresh()
                return
            try:
                output = save_selections(self.segmenter.image, self.results, self.output_dir, source=self.source)
                self.status.set_text(f"Saved {len(self.results)} registered targets: {output}")
                print(f"Saved {len(self.results)} registered targets: {output.resolve()}", flush=True)
            except (OSError, ValueError, cv2.error) as error:
                self.status.set_text(str(error))
        self.refresh()
