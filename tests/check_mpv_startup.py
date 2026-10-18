"""Checks for the mpv start-up watchdog.

Opening several videos at once occasionally leaves a libmpv core parked at the
start: the media is loaded and the player is not paused, but the seek that
begins playback never finishes, so the position stays at zero for good. Asking
the player to play again does not help, only a fresh seek does - which is what
reloading the video by hand does.

These checks drive PlayerProcessMPV._ensure_playing with a stub player, so they
cover the decision it makes rather than libmpv itself.
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap  # noqa: E402

bootstrap()

from gridplayer.mpv_player import player_process_mpv as mpv_process  # noqa: E402


class PlayerStub:
    def __init__(self, time_pos=0.0, is_paused=False, raises=False):
        self._time_pos = time_pos
        self._is_paused = is_paused
        self._raises = raises
        self.seeks = []
        self.reads = 0

    @property
    def time_pos(self):
        self.reads += 1
        if self._raises:
            raise RuntimeError("libmpv core has been shutdown")
        return self._time_pos

    @property
    def is_paused(self):
        return self._is_paused

    def set_time(self, position):
        self.seeks.append(position)


def make_process(player, stop_set=False):
    process = object.__new__(mpv_process.PlayerProcessMPV)
    process._player = player
    process._poll_stop = threading.Event()
    if stop_set:
        process._poll_stop.set()
    process._log = _NullLogger()
    return process


class _NullLogger:
    def debug(self, *_args, **_kwargs):
        pass


c = Checker("mpv start-up watchdog")

# Keep the checks quick: the real wait is for a freshly loaded player
stall_sec = mpv_process.STARTUP_STALL_SEC
mpv_process.STARTUP_STALL_SEC = 0.05

# a player that never leaves the start is nudged once, with a seek to the start
player = PlayerStub(time_pos=0.0, is_paused=False)
process = make_process(player)
process._ensure_playing()
c.check("parked player is nudged", player.seeks == [0], f"seeks={player.seeks}")

# a player that is already moving is left alone
player = PlayerStub(time_pos=3.5, is_paused=False)
process = make_process(player)
process._ensure_playing()
c.check("moving player is left alone", player.seeks == [], f"seeks={player.seeks}")
c.check("moving player is read once", player.reads == 1, f"reads={player.reads}")

# a player the user asked to start paused is left alone
player = PlayerStub(time_pos=0.0, is_paused=True)
process = make_process(player)
process._ensure_playing()
c.check("paused player is left alone", player.seeks == [], f"seeks={player.seeks}")

# a player that cannot be read must not raise, and must not be nudged blindly
player = PlayerStub(raises=True)
process = make_process(player)
try:
    process._ensure_playing()
    survived = True
except Exception as exc:  # noqa: BLE001
    survived = False
    c.check("unreadable player does not raise", False, repr(exc))
if survived:
    c.check("unreadable player does not raise", True, "")
    c.check(
        "unreadable player is not nudged", player.seeks == [], f"seeks={player.seeks}"
    )

# a shutting-down worker does not wait out the whole stall window
player = PlayerStub(time_pos=0.0, is_paused=False)
process = make_process(player, stop_set=True)
process._ensure_playing()
c.check("stopped worker does not nudge", player.seeks == [], f"seeks={player.seeks}")
c.check("stopped worker returns early", player.reads == 0, f"reads={player.reads}")

# the real window is not the test's shortened one
c.check(
    "stall window is a real wait",
    stall_sec >= 1.0,
    f"STARTUP_STALL_SEC={stall_sec}",
)

# the load also reports the state mpv settled on, or a video that started
# playing on its own keeps showing the play icon in the overlay
sent = []

player = PlayerStub(time_pos=0.0, is_paused=False)
process = make_process(player)
process.cmd_send = lambda *args: sent.append(args)
process._report_playback_status()
c.check(
    "load reports a playing player",
    sent == [("playback_status_changed_emit", False)],
    f"sent={sent}",
)

sent.clear()

player = PlayerStub(time_pos=0.0, is_paused=True)
process = make_process(player)
process.cmd_send = lambda *args: sent.append(args)
process._report_playback_status()
c.check(
    "load reports a paused player",
    sent == [("playback_status_changed_emit", True)],
    f"sent={sent}",
)

# and both reports are wired into the load path, after the media is reported
source = Path(mpv_process.__file__).read_text(encoding="utf-8")
c.check(
    "load worker calls the watchdog",
    source.index("notify_load_video_done") < source.index("self._ensure_playing()"),
    "watchdog must run after the load is reported",
)
c.check(
    "load worker reports the playback state",
    source.index("notify_load_video_done")
    < source.index("self._report_playback_status()")
    < source.index("self._ensure_playing()"),
    "the state mpv settled on must be reported once the media is loaded",
)
c.check(
    "watchdog seeks instead of replaying",
    "set_time(0)" in source
    and "self._player.load(" not in source.split("def _ensure_playing")[1],
    "a seek is what unsticks the player",
)

mpv_process.STARTUP_STALL_SEC = stall_sec

c.finish()
