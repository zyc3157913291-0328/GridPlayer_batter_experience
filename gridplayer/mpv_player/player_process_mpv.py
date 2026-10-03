# MOD: new file - the mpv player as it lives inside the child process.
"""Child-process side of the mpv driver.

Mirrors the VLC player process: the same command names arrive over the command
pipe, the same notify_* calls go back up. Two things differ from VLC:

  * commands are dispatched by method name, so the names used here have to match
    what the driver sends - they are the same ones the VLC driver uses
  * VLC pushes events, mpv does not, so the position is polled on its own thread
    at roughly the cadence VLC reports it (four times a second)

The rate path is one property assignment inside PlayerMPV, which is the whole
reason this driver exists.
"""

import logging
import threading
import time

from gridplayer.mpv_player.player_mpv import PlayerMPV
from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.utils.qt import translate
from gridplayer.vlc_player.static import AudioTrack, Media, VideoTrack

# VLC reports the position a few times a second; matching that keeps the
# progress bar's behaviour identical between the two engines
POSITION_POLL_SEC = 0.25

# how long to wait for mpv to parse a file before giving up on it
LOAD_TIMEOUT_SEC = 30


class PlayerProcessMPV(CommandLoopThreaded):
    def __init__(self, player_id, release_callback, init_data, **kwargs):
        super().__init__(**kwargs)

        self.id = player_id
        self.release_callback = release_callback

        self.win_id = init_data["win_id"]
        # the driver may hand libmpv its own options (hardware decoding, vo/ao
        # for tests); they are passed straight through
        self.player_options = init_data.get("player_options", {})

        self._log = logging.getLogger(self.__class__.__name__)
        self._player = None
        self._poll_stop = threading.Event()
        self._poll_thread = None

        self.start()

    def start(self):
        self.cmd_loop_start_thread(self.init_player)

    def init_player(self):
        self._player = PlayerMPV(
            wid=self.win_id, on_state=self._on_state_change, **self.player_options
        )

        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="mpv-position", daemon=True
        )
        self._poll_thread.start()

    # --- commands (names must match what the driver sends) ---

    def load_video(self, media_input):
        # The widget stays on its "initializing" placeholder until it is told
        # the media is loaded, so this has to report back the way the VLC player
        # does. Waiting for mpv to parse must not happen on the command loop, or
        # every other command stalls behind it, so it runs on its own thread.
        self.media_input = media_input

        self.notify_update_status(translate("Video Status", "Parsing media"))

        self._load_thread = threading.Thread(
            target=self._load_worker, args=(media_input,), name="mpv-load", daemon=True
        )
        self._load_thread.start()

    def _load_worker(self, media_input):
        try:
            self._player.load(media_input.uri)

            deadline = time.monotonic() + LOAD_TIMEOUT_SEC

            while time.monotonic() < deadline:
                if self._poll_stop.is_set():
                    return

                if self._player.duration is not None and self._player.tracks:
                    break

                time.sleep(0.1)
            else:
                self.notify_error(translate("Video Error", "Failed to load media"))
                return

            if media_input.is_audio_only:
                self._player.set_video_track(None)

            self.notify_update_status(
                translate("Video Status", "Preparing video output")
            )

            self._apply_initial_state(media_input)

            self.notify_load_video_done(self._media_from_player())
        except Exception as exc:
            self._log.error(f"mpv load failed: {exc}")
            self.notify_error(translate("Video Error", "Failed to load media"))

    def _apply_initial_state(self, media_input):
        if media_input.initial_time:
            self._player.set_time(media_input.initial_time)

        if media_input.video.is_paused:
            self._player.set_pause(True)
        elif media_input.video.is_muted is not None:
            self._player.audio_set_mute(media_input.video.is_muted)

        self._player.audio_set_volume(media_input.video.volume)

    def _media_from_player(self):
        """Build the Media the widget expects from mpv's own track list."""
        video_tracks = {}
        audio_tracks = {}

        for track in self._player.tracks:
            common = {
                "codec": track["codec"] or "",
                "bitrate": 0,
                "language": track["lang"],
                "description": track["title"],
            }

            if track["type"] == "video":
                video_tracks[track["id"]] = VideoTrack(
                    **common, video_dimensions=(0, 0), fps=None
                )
            elif track["type"] == "audio":
                audio_tracks[track["id"]] = AudioTrack(**common, channels=0, rate=0)

        selected_video = next(
            (
                t["id"]
                for t in self._player.tracks
                if t["type"] == "video" and t["selected"]
            ),
            None,
        )
        selected_audio = next(
            (
                t["id"]
                for t in self._player.tracks
                if t["type"] == "audio" and t["selected"]
            ),
            None,
        )

        duration = self._player.duration

        return Media(
            length=-1 if duration is None else duration,
            video_tracks=video_tracks,
            audio_tracks=audio_tracks,
            cur_video_track_id=selected_video,
            cur_audio_track_id=selected_audio,
        )

    def play(self):
        self._player.play()

    def set_pause(self, is_paused):
        self._player.set_pause(is_paused)

    def set_time(self, seek_ms):
        self._player.set_time(seek_ms)

    def set_playback_rate(self, rate):
        self._player.set_playback_rate(rate)

    def audio_set_mute(self, is_muted):
        self._player.audio_set_mute(is_muted)

    def audio_set_volume(self, volume):
        self._player.audio_set_volume(volume)

    def set_audio_track(self, track_id):
        self._player.set_audio_track(track_id)

    def set_video_track(self, track_id):
        self._player.set_video_track(track_id)

    def set_audio_channel_mode(self, mode):
        self._player.set_audio_channel_mode(mode)

    def snapshot(self, snapshot_file):
        self._player.snapshot(snapshot_file)

    def adjust_view(self, size, aspect, scale, crop):
        # mpv scales to the window itself; there is nothing to forward
        self._log.debug(f"adjust_view ignored: {size} {aspect} {scale} {crop}")

    def cleanup(self):
        self._poll_stop.set()

        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2)

        if self._player is not None:
            self._player.terminate()
            self._player = None

        self.release_callback(self.id)

    def cleanup_final(self):
        # InstanceProcess.release_player calls this once the player has reported
        # itself released; stopping the command loop is the last thing to do.
        self.cmd_loop_terminate()

    # --- reporting upwards ---

    def notify_update_status(self, status, percent=0):
        self.cmd_send("update_status_emit", status, percent)

    def notify_error(self, error):
        self.cmd_send("error_state", error)

    def notify_time_changed(self, new_time):
        self.cmd_send("time_changed_emit", new_time)

    def notify_playback_status_changed(self, is_paused):
        self.cmd_send("playback_status_changed_emit", is_paused)

    def notify_load_video_done(self, media_track):
        self.cmd_send("load_video_done", media_track)

    def notify_snapshot_taken(self, snapshot_path):
        self.cmd_send("snapshot_taken_emit", snapshot_path)

    def _on_state_change(self):
        if self._player is None:
            return

        self.notify_playback_status_changed(self._player.is_paused)

    def _poll_loop(self):
        last_time = None

        while not self._poll_stop.is_set():
            time.sleep(POSITION_POLL_SEC)

            if self._player is None:
                continue

            position = self._player.time_pos

            if position is not None and position != last_time:
                last_time = position
                self.notify_time_changed(position)
