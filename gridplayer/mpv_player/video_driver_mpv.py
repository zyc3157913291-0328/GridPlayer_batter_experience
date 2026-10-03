# MOD: new file - the main-process half of the mpv driver.
"""The mpv driver, as the main process sees it.

A thin translation layer, exactly like the VLC driver: every call becomes a
command over the pipe, and every report coming back arrives as a command whose
name matches one of the emit helpers below, which is what turns it into a Qt
signal.

The signal/emit half is taken from the VLC driver rather than copied. Those
declarations are engine-neutral - they say "the position changed", not "VLC says
so" - and copying them would mean two places to keep in step. Nothing in
vlc_player is modified by using it.
"""

from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver


class VideoDriverMPV(CommandLoopThreaded, VLCVideoDriver):
    def __init__(self, win_id, process_manager, mpv_options=None, **kwargs):
        super().__init__(**kwargs)

        self.crash_func = self.crash_thread
        self.cmd_loop_start_thread()

        init_data = {
            "win_id": win_id,
            "player_options": mpv_options or {},
        }

        process_manager.init_player(init_data, self.cmd_child_pipe(), {})

    def crash_thread(self, traceback_txt):
        self.crash.emit(traceback_txt)

    def cleanup(self):
        self.cmd_send("cleanup")
        self.cmd_loop_terminate()

    def load_video(self, media_input):
        self.cmd_send("load_video", media_input)

    def snapshot(self):
        self.cmd_send("snapshot")

    def play(self):
        self.cmd_send("play")

    def set_pause(self, is_paused):
        self.cmd_send("set_pause", is_paused)

    def set_time(self, seek_ms):
        self.cmd_send("set_time", seek_ms)

    def set_playback_rate(self, rate):
        # the reason this driver exists: mpv changes speed without dropping the
        # sound, and without shifting pitch
        self.cmd_send("set_playback_rate", rate)

    def audio_set_mute(self, is_muted):
        self.cmd_send("audio_set_mute", is_muted)

    def audio_set_volume(self, volume):
        self.cmd_send("audio_set_volume", volume)

    def set_audio_track(self, track_id):
        self.cmd_send("set_audio_track", track_id)

    def set_video_track(self, track_id):
        self.cmd_send("set_video_track", track_id)

    def set_audio_channel_mode(self, mode):
        self.cmd_send("set_audio_channel_mode", mode)

    def adjust_view(self, size, aspect, scale, crop):
        # mpv scales to the window it was given; there is nothing to forward
        self._log.debug(f"adjust_view ignored: {size} {aspect} {scale} {crop}")
