"""Owner-thread replay state with detached background history reads."""
from concurrent.futures import ThreadPoolExecutor

from components.replay import capture_replay_inputs, read_replay_index, read_replay_scene


class ReplayController:
    def __init__(self, session):
        self.session = session
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="replay")
        self.active = False
        self.epoch = 0
        self.index = self.scene = None
        self.steps = ()
        self.selected = 0
        self.error = ""
        self.index_future = self.scene_future = None
        self.identity = None

    def _identity(self):
        return self.session.generation, self.session.data.history_store

    def clear(self):
        self.epoch += 1
        self.active = False
        for future in (self.index_future, self.scene_future):
            if future is not None:
                future.cancel()
        self.index_future = self.scene_future = None
        self.index = self.scene = None
        self.steps = ()
        self.selected = 0
        self.error = ""
        self.identity = None

    def open(self):
        self.clear()
        self.active = True
        self.identity = self._identity()
        self.refresh()

    def refresh(self):
        if not self.active:
            return
        if self.index_future is not None:
            self.index_future.cancel()
        self.error = ""
        try:
            inputs = capture_replay_inputs(self.session.data)
            self.index_future = self.executor.submit(read_replay_index, inputs)
        except Exception as error:
            self.index_future = None
            self.error = str(error)

    def navigate(self, delta):
        if not self.steps:
            return
        selected = max(0, min(len(self.steps) - 1, self.selected + delta))
        if selected != self.selected:
            self.selected = selected
            self.scene = None
            self.error = ""
            if self.scene_future is not None and self.scene_future.cancel():
                self.scene_future = None

    def poll(self):
        if not self.active:
            return False
        generation, store = self._identity()
        if self.identity[0] != generation or self.identity[1] is not store:
            self.clear()
            return True
        changed = False
        if self.index_future is not None and self.index_future.done():
            future, self.index_future = self.index_future, None
            # Navigation can continue while Refresh loads: preserve the event now.
            event_id = self.steps[self.selected]["event_id"] if self.steps else None
            try:
                index = future.result()
                steps = index.steps
            except Exception as error:
                self.error = str(error)
            else:
                self.index, self.steps = index, steps
                self.selected = next((i for i, step in enumerate(steps)
                                      if step["event_id"] == event_id), 0)
                self.scene = None
                self.error = ""
                if self.scene_future is not None and self.scene_future.cancel():
                    self.scene_future = None
            changed = True
        if self.scene_future is not None and self.scene_future.done():
            future, self.scene_future = self.scene_future, None
            index, selected, epoch = self.scene_request
            if index is self.index and selected == self.selected and epoch == self.epoch:
                try:
                    self.scene = future.result()
                except Exception as error:
                    self.error = str(error)
                changed = True
        if self.index is not None and self.scene is None and not self.error and self.scene_future is None:
            self.scene_request = self.index, self.selected, self.epoch
            self.scene_future = self.executor.submit(read_replay_scene, self.index, self.selected)
            changed = True
        return changed

    def close(self):
        self.clear()
        self.executor.shutdown(wait=False, cancel_futures=True)
