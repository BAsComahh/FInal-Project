"""The live presentation always follows the shared match state."""

class LiveController:
    def __init__(self, session):
        self.session = session

    @property
    def presentation(self):
        return self.session.data

    def return_live(self):
        self.session.dirty = True
