# MOD: new file - the widget side of the mpv driver.
"""The video widget for mpv, mirroring VideoFrameVLCHW.

The important part is the same as the VLC hardware path: the video surface is a
plain native window created here in the main process, and its handle is handed
to the player process so mpv renders straight into it. Frames never cross the
process boundary.

There is no crop-border workaround here. That exists because of how VLC paints
into a foreign window; mpv scales to the window itself.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from gridplayer.mpv_player.video_driver_mpv import VideoDriverMPV
from gridplayer.params import env
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLCProcess


class VideoFrameMPV(VideoFrameVLCProcess):
    is_opengl = True

    def driver_setup(self, vlc_options):
        # vlc_options comes from the shared base and means nothing here; mpv's
        # own options are added later, when there is a settings page for them
        return VideoDriverMPV(
            win_id=int(self.video_surface.winId()),
            process_manager=self.process_manager,
            parent=self,
        )

    def ui_video_surface(self):
        if env.IS_MACOS:
            # Drawing into another process's window is not possible on macOS
            # https://stackoverflow.com/questions/583202/
            raise NotImplementedError

        video_surface = QWidget(self)
        video_surface.setMouseTracking(True)
        video_surface.setWindowFlags(Qt.WindowTransparentForInput)
        video_surface.setAttribute(Qt.WA_TransparentForMouseEvents)

        return video_surface
