"""Owner-thread replay state with detached background history reads."""
from concurrent.futures import ThreadPoolExecutor

from .contracts import command, CommandReceipt, freeze
from components.replay import capture_replay_inputs, read_replay_index, read_replay_scene


class Replay:
    def __init__(self, session):
        self._session = session
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="replay")
        self.active = False
        self.epoch = 0
        self.scene_revision = 0
        self._index = self._scene = None
        self._shown_step = None
        self.steps = ()
        self.selected = 0
        self.error = ""
        self._index_future = self._scene_future = None
        self._boundary_identity = None

    @property
    def scene(self):
        return freeze(self._scene)

    @property
    def loading(self):
        return self._index_future is not None

    @property
    def has_index(self):
        return self._index is not None

    def _identity(self):
        return self._session.generation, self._session.data.history_store

    @command
    def clear(self):
        self.epoch += 1
        self.active = False
        for future in (self._index_future, self._scene_future):
            if future is not None:
                future.cancel()
        self._index_future = self._scene_future = None
        self._index = self._scene = None
        self._shown_step = None
        self.steps = ()
        self.selected = 0
        self.error = ""
        self._boundary_identity = None
        return CommandReceipt("accepted")

    @command
    def open(self):
        if self._session.closed:
            return CommandReceipt("rejected", "Match is closed.")
        self.clear()
        self.active = True
        self._boundary_identity = self._identity()
        return self.refresh()

    @command
    def refresh(self):
        if not self.active:
            return CommandReceipt("rejected", "No active replay request.")
        if self._index_future is not None:
            self._index_future.cancel()
        self.error = ""
        try:
            inputs = capture_replay_inputs(self._session.data)
            self._index_future = self._executor.submit(read_replay_index, inputs)
        except Exception as error:
            self._index_future = None
            self.error = str(error)
        return CommandReceipt("rejected" if self.error else "pending", self.error, request_id=self.epoch)

    @command
    def select(self, index):
        if not self.steps:
            return CommandReceipt("rejected", "No active replay request.")
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("Replay step index must be an integer.")
        selected = max(0, min(len(self.steps) - 1, index))
        if selected != self.selected:
            self.selected = selected
            self.error = ""
            if self._scene_future is not None and self._scene_future.cancel():
                self._scene_future = None
            return CommandReceipt("pending")
        return CommandReceipt("accepted")

    @command
    def navigate(self, delta):
        return self.select(self.selected + delta)

    def poll(self):
        if not self.active:
            return False
        generation, store = self._identity()
        if self._boundary_identity[0] != generation or self._boundary_identity[1] is not store:
            self.clear()
            return True
        changed = False
        if self._index_future is not None and self._index_future.done():
            future, self._index_future = self._index_future, None
            # Navigation can continue while Refresh loads: preserve the event now.
            event_id = self.steps[self.selected]["event_id"] if self.steps else None
            opening = self._index is None
            try:
                index = future.result()
                steps = index.steps
            except Exception as error:
                self.error = str(error)
            else:
                self._index, self.steps = index, freeze(steps)
                self.selected = (max(0, len(steps) - 1) if opening else
                                 next((i for i, step in enumerate(steps) if step["event_id"] == event_id), 0))
                self.error = ""
                if self._scene_future is not None and self._scene_future.cancel():
                    self._scene_future = None
            changed = True
        if self._scene_future is not None and self._scene_future.done():
            future, self._scene_future = self._scene_future, None
            index, selected, epoch = self._scene_request
            if index is self._index and selected == self.selected and epoch == self.epoch:
                try:
                    self._scene = future.result()
                    self._shown_step = index, selected
                    self.scene_revision += 1
                except Exception as error:
                    self.error = str(error)
                changed = True
        if (self._index is not None and self._shown_step != (self._index, self.selected)
                and not self.error and self._scene_future is None):
            self._scene_request = self._index, self.selected, self.epoch
            self._scene_future = self._executor.submit(read_replay_scene, self._index, self.selected)
            changed = True
        return changed

    @command
    def close(self):
        self.clear()
        self._executor.shutdown(wait=False, cancel_futures=True)
        return CommandReceipt("accepted")
