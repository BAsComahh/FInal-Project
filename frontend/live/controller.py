"""An independent held presentation; source playback stays in MatchSession."""
from copy import deepcopy

class LiveController:
    def __init__(self, session):
        self.session = session
        self.snapshot = None

    @property
    def presentation(self):
        return self.snapshot if self.snapshot is not None else self.session.data

    def hold_view(self):
        if self.snapshot is None:
            self.snapshot = self.session.data.snapshot()
        self.session.dirty = True
        return self.snapshot

    def return_live(self):
        self.snapshot = None
        self.session.dirty = True

    def refresh_analysis_inputs(self):
        if self.snapshot is not None:
            self.snapshot.units = deepcopy(self.session.data.units)
            self.snapshot.rules.terrain = deepcopy(self.session.data.rules.terrain)
