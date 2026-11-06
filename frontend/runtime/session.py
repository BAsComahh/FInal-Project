"""Source clock, one serial model queue and accepted observations/history."""
from pathlib import Path
from time import perf_counter
import cv2
import numpy as np
from components.video_io import VideoSource
from components.tracking.status import validate_disappearance_seconds
from .. import config
from .task_worker import TaskWorker

class MatchSession:
    def __init__(self, video, data, *, model_id="facebook/sam3", device=None, start=0, seconds=10,
                 inference_fps=2, stride=None, output_dir=None,
                 profile=False, tray_search="full", tracker=config.DEFAULT_TRACKER, tracker_model=None, tracker_cache=None):
        if seconds <= 0 or not np.isfinite(seconds):
            raise ValueError("seconds must be positive")
        if inference_fps <= 0 or not np.isfinite(inference_fps):
            raise ValueError("inference-fps must be positive")
        if stride is not None and stride < 1:
            raise ValueError("stride must be positive")
        self.disappearance_seconds = validate_disappearance_seconds(config.TRACKING_DISAPPEARANCE_SECONDS)
        self.data = data
        self.worker = TaskWorker(model_id, device, profile=profile, tray_search=tray_search,
                                 tracker=tracker, tracker_model=tracker_model, tracker_cache=tracker_cache)
        self.worker.submit("load", generation=0)
        self.source = None
        try:
            self.source = VideoSource(video)
            self.data.current.frame = self.source.read_at(start)
        except Exception:
            if self.source is not None:
                self.source.close()
            self.worker.close()
            raise
        self.initial_frame = self.data.current.frame
        self.registration_start_frame = self.source.frame_index
        self.data.board.source_size = self.data.current.frame.shape[1::-1]
        self.start = start
        self.end_index = min(self.source.frame_count - 1, int((start + seconds) * self.source.fps) - 1)
        self.inference_fps = self.source.fps / stride if stride is not None else inference_fps
        self.output_dir = (Path(output_dir) if output_dir is not None else
                           config.PROJECT_ROOT / "outputs/sam3_registration")
        self.load_progress = None
        self.pending_trays = False
        self.generation = 0
        self.needs_reset = False
        self.needs_load = False
        self.needs_prepare = True
        self.startup_ready = False
        self.model_failed = self.closed = self.playing = False
        self.pending_play = False
        self.next_inference_time = 0.0
        self.last_submitted_frame = -1
        self.dirty = True
        self.configure_trays()
        self.note = "Loading SAM3 and preparing the first frame. Confirm the table boundary first."

    @property
    def registration_locked(self):
        return self.data.reference_folder is not None

    def _warp_frame(self, frame):
        if self.data.board.homography is None:
            return frame
        return cv2.warpPerspective(frame, self.data.board.homography["matrix"], self.data.board.homography["output_size"])

    def frame_metadata(self, *, board=None, frame=None):
        board = self.data.board if board is None else board
        frame = self.data.current.frame if frame is None else frame
        metadata = self.source.metadata()
        if board.homography is not None:
            metadata.update(
                coordinate_space="rectified_table_pixels", image_size=list(frame.shape[1::-1]),
                source_image_size=list(board.source_size), calibration_version=board.calibration_version,
                homography={key: value.tolist() if isinstance(value, np.ndarray) else value
                            for key, value in board.homography.items()},
            )
            if board.image_to_plane is not None:
                metadata.update(image_to_plane=board.image_to_plane.tolist(), board_size_mm=list(board.board_size_mm))
        return metadata

    def configure_trays(self):
        sizes = {}
        if self.data.units:
            for object_id, unit_id in self.data.units.bindings.items():
                type_id = self.data.units.units[unit_id]["type_id"]
                dimension = self.data.units.types[type_id].get("dimension", {})
                if "width_mm" in dimension and "depth_mm" in dimension:
                    sizes[object_id] = (dimension["width_mm"], dimension["depth_mm"])
        self.worker.tray_context = ({"image_to_plane": self.data.board.image_to_plane, "sizes": sizes}
                                    if self.data.board.image_to_plane is not None else None)
        request = self.worker.request if self.worker.busy else None
        # A queued result may still carry tray sizes from the replaced list.
        self.pending_trays = self.data.current.prediction is not None or (
            request is not None and request["kind"] in ("click", "replace", "propagate", "trays"))
        if self.data.current.prediction is not None:
            self.data.current.prediction = {**self.data.current.prediction, "trays": {}, "tray_errors": {}}

    def mark_changed(self):
        self.data.current.view_revision += 1
        self.dirty = True

    def tray_status(self):
        if self.data.board.image_to_plane is None:
            return "NO CALIB"
        if not self.worker.tray_context["sizes"]:
            return "NO SIZES"
        if self.data.current.prediction is None:
            return "WAIT MASK"
        trays = self.data.current.prediction.get("trays", {})
        if trays:
            return f"ON ({len(trays)})"
        if self.data.current.prediction.get("tray_errors"):
            return "CHECK FIT"
        if self.pending_trays or self.worker.busy:
            return "FITTING"
        return "NO FIT"

    def start_stream(self):
        self.play_start = perf_counter()
        self.play_start_frame = self.source.frame_index
        self.playing = True
        self.pending_play = False

    def schedule(self, registration, calibration, now=None):
        now = perf_counter() if now is None else now
        if self.worker.busy or self.closed:
            return
        if calibration.context is not None:
            context = calibration.context
            metadata = self.data.current.prediction_metadata
            if (context["draft"] is None and not self.model_failed and metadata is not None
                    and metadata["frame_index"] < context["frame_index"]):
                self.worker.submit("propagate", frame=self._warp_frame(context["frame"]),
                                   metadata=self.frame_metadata(), generation=self.generation)
                self.last_submitted_frame = context["frame_index"]
                self.next_inference_time = now + 1 / self.inference_fps
            return
        if self.needs_reset:
            self.needs_reset = False
            self.worker.submit("reset", generation=self.generation)
        elif self.needs_load:
            self.needs_load = False
            self.worker.submit("load", generation=self.generation)
        elif self.needs_prepare and self.data.board.homography is not None and not self.model_failed:
            self.needs_prepare = False
            self.worker.submit("prepare", frame=self.data.current.frame, metadata=self.frame_metadata(), generation=self.generation)
        elif (request := registration.take_pending_request()) is not None:
            kind, values = request
            self.worker.submit(kind, **values, generation=self.generation)
        elif self.pending_trays and self.data.current.prediction is not None:
            self.pending_trays = False
            self.worker.submit("trays", frame=self.data.current.prediction_frame, metadata=self.data.current.prediction_metadata,
                               prediction=self.data.current.prediction, generation=self.generation)
        elif self.pending_play and not self.worker.tracker_initialized and not self.model_failed:
            self.worker.submit("start_tracker", frame=self.data.current.prediction_frame, metadata=self.data.current.prediction_metadata,
                               prediction=self.data.current.prediction, generation=self.generation)
        elif (self.playing and self.data.current.prediction is not None and not self.model_failed and not registration.updating_points
              and now >= self.next_inference_time and self.source.frame_index > self.last_submitted_frame):
            self.worker.submit("propagate", frame=self.data.current.frame, metadata=self.frame_metadata(), generation=self.generation)
            self.last_submitted_frame = self.source.frame_index
            self.next_inference_time = now + 1 / self.inference_fps

    def advance(self, registration, calibration):
        if self.closed:
            return
        now = perf_counter()
        completed = self.worker.poll()
        if completed is not None:
            request, prediction, error = completed
            if request["generation"] == self.generation:
                registration.accept_prompt_result(request, prediction)
                if error is not None and request["kind"] == "recalibrate":
                    calibration.context["draft"] = None
                    self.note = f"Recalibration failed: {error}. Retry or Esc to cancel."
                elif error is not None:
                    self.model_failed = True
                    self.note = f"Model/tracking error: {error}. R resets the session."
                elif prediction is not None:
                    if request["kind"] == "recalibrate":
                        calibration.commit_recalibration(request)
                    prediction["accepted_at"] = perf_counter()
                    if self.pending_trays:
                        prediction = {**prediction, "trays": {}, "tray_errors": {}}
                    self.data.accept_observation(
                        prediction, request["frame"], request["metadata"],
                        disappearance_seconds=self.disappearance_seconds if self.registration_locked else None)
                    if self.registration_locked and request["kind"] in ("propagate", "recalibrate"):
                        self.data.record_history()
                    if request["kind"] == "click":
                        self.last_submitted_frame = max(self.last_submitted_frame, request["metadata"]["frame_index"])
                        self.next_inference_time = now + 1 / self.inference_fps
                    elif request["kind"] == "replace":
                        self.last_submitted_frame = request["metadata"]["frame_index"]
                        self.next_inference_time = now + 1 / self.inference_fps
                    elif request["kind"] == "start_tracker":
                        self.start_stream()
                    self.mark_changed()
                    times = prediction.get("timings_seconds", {})
                    self.note = (f"Update {prediction['inference_seconds']:.2f}s | "
                                 f"{prediction.get('tracking_backend', 'model')} operation {times.get('worker_operation', 0):.2f}s | "
                                 f"tray {times.get('tray_fit', 0):.2f}s. Latest result held between updates.")
                elif request["kind"] == "replace":
                    self.last_submitted_frame = -1
                    self.note = "Point undone. No objects remain; click to register again."
                elif request["kind"] == "load":
                    self.note = ("Weights loaded. Preparing rectified first-frame features." if self.data.board.homography is not None else
                                 "Weights loaded. Confirm the table corners to focus the battlefield.")
                elif request["kind"] == "prepare":
                    self.startup_ready = True
                    self.note = f"SAM3 and first-frame features ready on {self.worker.predictor.device}. Segment targets; Tab labels."
                self.dirty = True
        if self.playing:
            target = min(self.end_index, self.play_start_frame + int((now - self.play_start) * self.source.fps))
            if target > self.source.frame_index:
                try:
                    self.data.current.frame = self._warp_frame(self.source.read_frame(target))
                    self.dirty = True
                except (OSError, ValueError, cv2.error) as error:
                    self.playing = False
                    self.note = str(error)
            if target >= self.end_index:
                self.playing = False
                self.note = "Video interval complete. Final registration references are already saved."
        self.schedule(registration, calibration, now)

        progress = self.worker.load_progress
        if progress != self.load_progress or progress is not None:
            self.load_progress = progress
            self.dirty = True

    def pause_source(self):
        self.playing = False
        self.dirty = True

    def reset(self):
        self.playing = self.pending_play = False
        self.data.reference_folder = None
        self.data.history.clear()
        self.data.tracking.clear()
        self.data.rules.fronts.clear()
        self.generation += 1
        self.needs_reset = True
        self.needs_load = not self.worker.models_loaded
        self.needs_prepare = True
        self.startup_ready = False
        self.data.current.frame = self._warp_frame(self.source.read_frame(self.registration_start_frame))
        self.data.current.prediction = self.data.current.prediction_frame = self.data.current.prediction_metadata = None
        self.last_submitted_frame = -1
        self.next_inference_time = 0
        self.model_failed = False
        self.mark_changed()
        self.note = "Reset. Old in-flight results will be discarded."

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.playing = False
        self.source.close()
        self.worker.close()
