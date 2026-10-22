"""Interactive inspection of the shared line/frame pipeline."""

import cv2
import numpy as np

from .pipeline import STAGES, compute_stages
from .config import CONSTRAINTS, PIPELINE, initial_switches
from .io import export_stages
from .visualization import draw_lines, draw_merge_round


class StepViewer:
    def __init__(self, image, args, switches=None, result=None):
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button, CheckButtons, RadioButtons, Slider

        self.image, self.args = image, args
        self.switches = switches if switches is not None else initial_switches(args)
        self.stages, self.report = result if result is not None else compute_stages(image, args, self.switches)
        self.stage = args.stage
        self.merge_round = self.report["merge_diagnostics"].get("pass_count", 0)
        self.figure = plt.figure(figsize=(18, 10))
        self.figure.suptitle(f"LSD stages - {args.image.name}", fontsize=14)
        self.axes = self.figure.add_axes([0.23, 0.31, 0.58, 0.62])
        self.artist = self.axes.imshow(cv2.cvtColor(self.stages[self.stage]["image"], cv2.COLOR_BGR2RGB))
        self.axes.axis("off")
        self.note = self.figure.text(0.23, 0.265, "", fontsize=10, wrap=True)
        self.status = self.figure.text(0.23, 0.015, "", fontsize=9)
        self.pipeline_checks = CheckButtons(self.figure.add_axes([0.012, 0.49, 0.19, 0.44]),
                                           [label for _, label in PIPELINE], [self.switches[k] for k, _ in PIPELINE])
        self.pipeline_checks.ax.set_title("Pipeline switches", fontsize=11)
        self.merge_checks = CheckButtons(self.figure.add_axes([0.012, 0.19, 0.19, 0.26]),
                                        [label for _, label in CONSTRAINTS], [self.switches[k] for k, _ in CONSTRAINTS])
        self.merge_checks.ax.set_title("Merge conditions", fontsize=11)
        self.stage_picker = RadioButtons(self.figure.add_axes([0.825, 0.41, 0.17, 0.52]),
                                         [label for _, label in STAGES], active=[k for k, _ in STAGES].index(self.stage))
        self.stage_picker.ax.set_title("Inspect a stage", fontsize=11)
        for widget in [self.pipeline_checks, self.merge_checks, self.stage_picker]:
            for label in widget.labels:
                label.set_fontsize(10)
        self.pipeline_checks.on_clicked(lambda _: self.on_switches())
        self.merge_checks.on_clicked(lambda _: self.on_switches())
        self.stage_picker.on_clicked(self.on_stage)
        self.round_slider = Slider(self.figure.add_axes([0.88, 0.36, 0.105, 0.02]), "Round",
                                   0, max(1, self.merge_round), valinit=self.merge_round, valstep=1)
        self.round_slider.set_active(self.merge_round > 0)
        self.round_slider.on_changed(self.on_merge_round)
        self.sliders = {}
        controls = [("merge_gap", "Merge gap (px)", 0, 250, 1),
                    ("merge_distance", "Line distance (px)", 1, 60, 1),
                    ("merge_min_length", "Source length (px)", 1, 100, 1),
                    ("merge_angle", "Group angle (deg)", 0, 44, 0.5),
                    ("merge_min_coverage", "Coverage", 0.01, 1, 0.01),
                    ("min_line_length", "Final length (px)", 1, 600, 1)]
        for i, (key, label, minimum, maximum, step) in enumerate(controls):
            value = getattr(args, key)
            slider = Slider(self.figure.add_axes([0.38, 0.225 - i * 0.032, 0.38, 0.018]),
                            label, min(minimum, value), max(maximum, value), valinit=value, valstep=step)
            slider.on_changed(lambda value, key=key: self.on_parameter(key, value))
            self.sliders[key] = slider
        self.save_button = Button(self.figure.add_axes([0.025, 0.105, 0.16, 0.05]), "Save current stages")
        self.save_button.on_clicked(self.save)
        self.figure.text(0.825, 0.265, "Gray = original segments\nCyan = fitted groups\nGreen = retained segments\nOrange = rejected at eligibility", fontsize=10, va="top")
        self.figure._lsd_step_viewer = self
        self.refresh_preview()

    def refresh_preview(self):
        stage = self.stages[self.stage]
        overlay, count, note = stage["image"], stage["count"], stage["note"]
        suffix = ""
        if self.stage == "merged":
            rounds = self.report["merge_diagnostics"].get("rounds", [])
            if 0 < self.merge_round <= len(rounds):
                entry = rounds[self.merge_round - 1]
                overlay = draw_merge_round(self.image, np.asarray(self.report["raw_lines"]).reshape(-1, 4), entry)
                count = len(entry["groups"])
                suffix = f" | pass {self.merge_round}/{len(rounds)}"
                note = (f"Clusters: {entry['input_cluster_count']} -> {entry['output_cluster_count']}; "
                        f"new merges: {entry['merge_operations']}. All original source segments are rechecked.")
            elif self.merge_round == 0:
                overlay = draw_lines(self.image, np.asarray(self.report["raw_lines"]).reshape(-1, 4), (130, 130, 130), 1)
                count, note = 0, "Before merging: raw segments only."
        self.artist.set_data(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
        state = "ON" if stage["enabled"] else "OFF / skipped"
        self.axes.set_title(f"{dict(STAGES)[self.stage]} | count {count} | {state}{suffix}", fontsize=12)
        self.note.set_text(note)
        source = f">= {self.args.merge_min_length:g}px" if self.switches["merge_source_length"] else "length OFF"
        self.status.set_text(f"LSD merge: source {source}; "
                             f"angle {self.args.merge_angle:g}deg; distance {self.args.merge_distance:g}px; "
                             f"gap {self.args.merge_gap:g}px; coverage {self.args.merge_min_coverage:g}")
        self.figure.canvas.draw_idle()

    def recompute(self):
        try:
            self.stages, self.report = compute_stages(self.image, self.args, self.switches)
            self.merge_round = self.report["merge_diagnostics"].get("pass_count", 0)
            self.round_slider.eventson = False
            self.round_slider.valmax = max(1, self.merge_round)
            self.round_slider.ax.set_xlim(0, self.round_slider.valmax)
            self.round_slider.set_val(self.merge_round)
            self.round_slider.set_active(self.merge_round > 0)
            self.round_slider.eventson = True
            self.refresh_preview()
        except (ValueError, cv2.error) as error:
            self.status.set_text(str(error))
            self.figure.canvas.draw_idle()

    def on_switches(self):
        for (key, _), enabled in zip(PIPELINE, self.pipeline_checks.get_status()):
            self.switches[key] = bool(enabled)
        for (key, _), enabled in zip(CONSTRAINTS, self.merge_checks.get_status()):
            self.switches[key] = bool(enabled)
        self.recompute()

    def on_stage(self, label):
        self.stage = next(key for key, title in STAGES if title == label)
        self.report["preview_stage"] = self.stage
        self.refresh_preview()

    def on_merge_round(self, value):
        self.merge_round = int(value)
        self.report["preview_merge_round"] = self.merge_round
        self.refresh_preview()

    def on_parameter(self, key, value):
        setattr(self.args, key, int(value) if key == "min_line_length" else float(value))
        self.recompute()

    def save(self, _=None):
        path = export_stages(self.args, self.stages, self.report)
        self.status.set_text(f"Saved current stages and settings: {path}")
        self.figure.canvas.draw()
        self.figure.savefig(self.args.output_dir / f"{self.args.image.stem}_stage_controls.png", dpi=110)
