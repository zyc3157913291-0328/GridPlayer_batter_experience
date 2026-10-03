# MOD: new file - holds one libmpv instance and speaks the driver's vocabulary.
"""The libmpv side of the mpv driver.

One instance per video, living in the same child process the VLC drivers use.
Everything the driver needs is expressed here in plain terms - load, play,
pause, seek, rate, tracks, volume, snapshot - so the driver class above it
stays a thin translation layer.

Why this driver exists at all: libVLC re-clocks its audio output on every rate
change and drops the sound for a moment; mpv changes speed without a gap and
without shifting pitch. The rate path here is therefore the point of the whole
exercise, and it is one property assignment.
"""

import logging

from gridplayer.utils.mpv_finder import missing_runtime_message, prepare_import

RUNTIME_DIR = prepare_import()

mpv = None
LIBMPV_ERROR = None

if RUNTIME_DIR is None:
    LIBMPV_ERROR = missing_runtime_message()
else:
    try:
        from gridplayer.mpv_player import mpv  # type: ignore[no-redef]
    except OSError as exc:  # pragma: no cover - depends on the local runtime
        LIBMPV_ERROR = f"{missing_runtime_message()} ({exc})"


LIBMPV_AVAILABLE = mpv is not None

# mpv's own channel layouts, keyed by the names GridPlayer's settings use
CHANNEL_MODES = {
    "mono": "mono",
    "stereo": "stereo",
    "auto": "auto",
    "left": "fl",
    "right": "fr",
}


class PlayerMPV:
    """A single mpv playback instance."""

    def __init__(self, wid=None, on_state=None, **extra_options):
        if not LIBMPV_AVAILABLE:
            raise RuntimeError(LIBMPV_ERROR or "libmpv is unavailable")

        self._log = logging.getLogger(self.__class__.__name__)
        self._on_state = on_state
        self._shutting_down = False

        options = {
            "idle": "yes",
            "keep_open": "yes",
            # GridPlayer draws its own controls; mpv must not draw any
            "osc": "no",
            "input_default_bindings": "no",
            "input_vo_keyboard": "no",
            "terminal": "no",
        }

        if wid is not None:
            options["wid"] = str(int(wid))

        # callers may override or add; vo/ao are the usual ones in tests
        options.update(extra_options)

        self._player = mpv.MPV(**options)

        if on_state is not None:
            self._player.observe_property("pause", self._state_changed)
            self._player.observe_property("idle-active", self._state_changed)
            self._player.observe_property("eof-reached", self._state_changed)

    @property
    def raw(self):
        """The underlying python-mpv instance, for things not wrapped here."""
        return self._player

    # --- transport ---

    def load(self, uri):
        self._player.play(str(uri))

    def play(self):
        self._player.pause = False

    def set_pause(self, is_paused):
        self._player.pause = bool(is_paused)

    def set_time(self, seek_ms):
        self._player.command("seek", float(seek_ms) / 1000, "absolute")

    def set_playback_rate(self, rate):
        # the whole point: one property assignment, no output reconfiguration
        self._player.speed = float(rate)

    def stop(self):
        self._player.command("stop")

    def terminate(self):
        # Observers fire while libmpv tears itself down, and calling back into a
        # half-destroyed instance is an access violation, not an exception this
        # process can catch. Silencing them first is what makes shutdown clean;
        # python-mpv wants the handler to unregister, so nulling the callback
        # and letting _state_changed bail out is both simpler and sufficient.
        self._shutting_down = True
        self._on_state = None

        self._player.terminate()

    # --- audio ---

    def audio_set_mute(self, is_muted):
        self._player.mute = bool(is_muted)

    def audio_set_volume(self, volume):
        # the driver passes a 0.0-1.0 fraction, the same as the VLC driver does
        # (it converts with int(volume_percent * 100)); mpv wants 0-100
        self._player.volume = max(0, min(100, round(float(volume) * 100)))

    def set_audio_channel_mode(self, mode):
        self._player["audio-channels"] = CHANNEL_MODES.get(mode, "auto")

    # --- tracks ---

    def set_video_track(self, track_id):
        self._player.vid = "no" if track_id is None else track_id

    def set_audio_track(self, track_id):
        self._player.aid = "no" if track_id is None else track_id

    @property
    def tracks(self):
        """mpv's track list, normalised to what the driver reports upwards."""
        return [
            {
                "id": track.get("id"),
                "type": track.get("type"),
                "selected": bool(track.get("selected")),
                "title": track.get("title"),
                "lang": track.get("lang"),
                "codec": track.get("codec"),
            }
            for track in self._player.track_list or []
        ]

    # --- snapshots ---

    def snapshot(self, path):
        self._player.command("screenshot-to-file", str(path), "video")

    # --- state ---

    @property
    def is_paused(self):
        return bool(self._player.pause)

    @property
    def time_pos(self):
        value = self._player.time_pos

        return None if value is None else int(value * 1000)

    @property
    def duration(self):
        value = self._player.duration

        return None if value is None else int(value * 1000)

    @property
    def is_playing(self):
        return not self._player.idle_active and not self._player.eof_reached

    @property
    def version(self):
        return self._player.mpv_version

    def _state_changed(self, _name, _value):
        if self._shutting_down or self._on_state is None:
            return

        self._on_state()
