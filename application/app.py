"""One match, independent of rendering and native event loops."""
from dataclasses import fields
from pathlib import Path
from time import perf_counter

from components.game_data import GameData
from components.registration import UnitRoster
from .config import DEFAULT_UNITS
from .session import MatchSession
from .registration import Registration
from .calibration import Calibration, configure_board
from .recovery import Recovery
from .replay import Replay
from .geometry import GeometryQueries
from .scene_editing import SceneEditing
from .contracts import (command, CommandReceipt, FrameRef, MatchSnapshot, BoardSnapshot, CurrentSnapshot,
                        RosterSnapshot, RulesSnapshot, TrackingSnapshot, freeze)


class MatchApplication:
    def __init__(self, video, *, units=None, calibration=None, board_size_in=None, registration_archive=None, **options):
        data = GameData()
        configure_board(data, calibration, board_size_in)
        data.units = UnitRoster.load(units if units is not None else DEFAULT_UNITS)
        if units is None or Path(units).resolve() == DEFAULT_UNITS:
            data.units = data.units.with_list("A", data.units.payload, source=str(DEFAULT_UNITS))
        self._session = MatchSession(video, data, **options)
        self.registration = self._session.registration = Registration(self._session)
        self.registration.sample = self.sample
        self.calibration = self._session.calibration = Calibration(self._session)
        self.recovery = Recovery(self._session)
        self.recovery.sample = self.sample
        self.replay = Replay(self._session)
        self.geometry = GeometryQueries(self._session)
        self.scene_editing = SceneEditing(self._session, self.geometry)
        self._snapshot = self._snapshot_key = None
        self._revision = 0
        if registration_archive is not None:
            receipt = self.registration.load_archive(registration_archive)
            if receipt.status == "rejected":
                self.close()
                raise ValueError(receipt.reason)

    def tick(self, now=None):
        if self._session.closed:
            return
        self._session.advance(now)
        replay_changed = self.replay.poll()
        geometry_changed = self.geometry.tick()
        if replay_changed or geometry_changed:
            self._snapshot_key = None

    def frame_ref(self, metadata=None):
        session = self._session
        metadata = session.frame_metadata() if metadata is None else metadata
        return FrameRef(session.generation, metadata["frame_index"], metadata["timestamp_seconds"],
                        tuple(session.data.board.source_size), metadata.get("calibration_version", 0))

    def sample(self, reference):
        session = self._session
        if reference.generation != session.generation or reference.calibration_version != session.data.board.calibration_version:
            raise ValueError("The sampled frame belongs to an expired session or calibration.")
        shown = session.presented_frame
        if shown is not None and reference == self.frame_ref(shown["metadata"]):
            return shown
        if reference == self.frame_ref():
            return session.source_sample()
        raise ValueError("The sampled frame is no longer available; display a new frame before retrying.")

    def present(self, reference):
        self._session.presented_frame = self.sample(reference)

    @command
    def start(self, overlay=None, now=None):
        session = self._session
        if not session.startup_ready or session.model_failed:
            raise ValueError("Wait for models and registration preparation before starting playback")
        if session.source.frame_index >= session.end_index:
            raise ValueError("End of video interval. R restarts.")
        receipt = self.registration.finish_registration(overlay)
        if receipt.status == "rejected":
            return receipt
        session.playback_started = True
        if not session.worker.tracker_initialized:
            session.pending_play = True
            session.note = f"Initializing {session.worker.tracker_name} from registered masks before starting the video."
            session.schedule(now)
        else:
            session.start_stream(now)
        session.mark_changed()
        return CommandReceipt("pending" if session.pending_play else "accepted", request_id=session.generation)

    def set_note(self, note):
        self._session.note = note

    @command
    def set_tray_fitting(self, enabled):
        if self._session.closed:
            raise ValueError("Match is closed.")
        if not isinstance(enabled, bool):
            raise ValueError("Tray fitting must be enabled or disabled.")
        self._session.set_tray_fitting(enabled)
        self.geometry.invalidate()
        return CommandReceipt("accepted")

    def snapshot(self):
        session, data = self._session, self._session.data
        worker = session.worker
        stage = ("recalibrate" if self.calibration._context is not None else "playback" if session.playback_started
                 else "register" if data.board.homography is not None else "table")
        recovery = self.recovery
        key = (data.current.view_revision, session.generation, session.source.frame_index, stage, self.replay.active,
               session.playing, session.pending_play, session.closed, session.startup_ready, session.model_failed,
               worker.models_loaded, worker.tracker_initialized, session.load_progress, session.note, session.history_warning,
               self.registration.next_click_id, len(self.registration.clicks), recovery.active, recovery.busy,
               recovery.candidate_generation, id(recovery._preview), recovery.note, tuple(recovery.labels()))
        if key == self._snapshot_key:
            return self._snapshot
        self._revision += 1
        board = BoardSnapshot(**{f.name: freeze(getattr(data.board, f.name)) for f in fields(BoardSnapshot)})
        current = CurrentSnapshot(**{f.name: freeze(getattr(data.current, f.name)) for f in fields(CurrentSnapshot)})
        roster = data.units
        units = RosterSnapshot(**{name: freeze(getattr(roster, name))
                                  for name in ("types", "units", "bindings", "counters", "payload", "source")},
                               next_ids=freeze({key: roster.next_unit_id(key) for key in roster.types}))
        tracking = freeze({uid: TrackingSnapshot(**{f.name: freeze(getattr(state, f.name))
                                                  for f in fields(TrackingSnapshot)}) for uid, state in data.tracking.items()})
        self._snapshot = MatchSnapshot(
            self._revision, stage, "replay" if self.replay.active else "live", self.frame_ref(), freeze(session.source.frame),
            self.frame_ref(data.current.prediction_metadata) if data.current.prediction_metadata is not None else None,
            board, current, units, RulesSnapshot(freeze(data.rules.fronts), freeze(data.rules.terrain), data.rules.track_facing), tracking,
            data.reference_folder, session.source.fps, session.end_index, session.playing, session.pending_play,
            session.closed, session.registration_locked, session.startup_ready, session.model_failed,
            worker.predictor.model is not None, worker.tracker_name, worker.tracker_initialized,
            worker.facing.error if worker.facing is not None else None, freeze(session.load_progress),
            session.inference_fps, session.history_warning, session.tray_status(), session.note, freeze(self.registration.clicks),
            freeze({"active": recovery.active, "busy": recovery.busy, "committing": recovery.committing,
                    "candidate_generation": recovery.candidate_generation, "preview": recovery._preview,
                    "review_unit_id": recovery.review_unit_id, "labels": recovery.labels(), "note": recovery.note}),
            tray_fitting=session.tray_fitting)
        self._snapshot_key = key
        return self._snapshot

    def input_delay(self):
        session = self._session
        if session.playing:
            next_time = session.play_start + (session.source.frame_index + 1 - session.play_start_frame) / session.source.fps
            return max(1, min(15, int((next_time - perf_counter()) * 1000)))
        return 15

    @command
    def reset(self):
        if self._session.closed:
            return CommandReceipt("rejected", "Match is closed.")
        self.replay.clear()
        self.geometry.clear()
        self.calibration.cancel_recalibration()
        self._session.reset()
        self.registration.reset()
        self._session.configure_trays()
        self._session.schedule()

    @command
    def close(self):
        if self._session.closed:
            return
        self.replay.close()
        self.geometry.close()
        self.calibration.cancel_recalibration()
        self._session.close()
