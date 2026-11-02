"""Native OpenCV window lifecycle and event loop."""
import cv2
from .app import VideoApplication

class VideoWindow:
    WINDOW = "Battlefield - video registration"

    def __init__(self, video, **options):
        self.app = VideoApplication(video, **options)

    def close(self):
        self.app.close()

    def show(self):
        cv2.namedWindow(self.WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.WINDOW, self.app.on_mouse)
        try:
            while not self.app.session.closed:
                self.app.advance()
                if self.app.dirty or self.app.session.dirty:
                    cv2.imshow(self.WINDOW, self.app.render())
                key = cv2.waitKey(self.app.input_delay())
                if key >= 0:
                    self.app.on_key(key & 0xff)
                if cv2.getWindowProperty(self.WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            self.close()
            cv2.destroyWindow(self.WINDOW)
