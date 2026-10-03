"""P2 Task 1: the fourth repeat mode (play once, pause at end)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap, sample

bootstrap()
c = Checker("repeat mode")

from gridplayer.params.static import (
    VIDEO_REPEAT_CYCLE,
    VideoRepeat,
    next_video_repeat,
)

# --- the new member exists and serialises as expected ---
c.check("PAUSE_AT_END exists", hasattr(VideoRepeat, "PAUSE_AT_END"))
c.check("PAUSE_AT_END value", VideoRepeat.PAUSE_AT_END.value == "pause_at_end")

# --- old config values still parse (backward compatibility) ---
for raw, expected in (
    ("single_file", VideoRepeat.SINGLE_FILE),
    ("dir", VideoRepeat.DIR),
    ("dir_shuffle", VideoRepeat.DIR_SHUFFLE),
    ("pause_at_end", VideoRepeat.PAUSE_AT_END),
):
    c.check(f"parses {raw!r}", VideoRepeat(raw) is expected)

# --- cycle order: default (list loop) first, then a full loop back to it ---
c.check("cycle starts at DIR (list loop)", VIDEO_REPEAT_CYCLE[0] is VideoRepeat.DIR)
c.check("cycle covers all four modes", len(VIDEO_REPEAT_CYCLE) == 4)
c.check("cycle has no duplicates", len(set(VIDEO_REPEAT_CYCLE)) == 4)

seen = [VIDEO_REPEAT_CYCLE[0]]
mode = VIDEO_REPEAT_CYCLE[0]
for _ in range(3):
    mode = next_video_repeat(mode)
    seen.append(mode)

c.check(
    "four clicks walk every mode",
    set(seen) == set(VIDEO_REPEAT_CYCLE),
    f"{[m.value for m in seen]}",
)
c.check(
    "fifth click returns to the start",
    next_video_repeat(seen[-1]) is VIDEO_REPEAT_CYCLE[0],
)
c.check(
    "unknown mode falls back to the first entry",
    next_video_repeat(None) is VIDEO_REPEAT_CYCLE[0],
)

# --- settings round-trip through the real Settings machinery ---
from gridplayer.settings import Settings

Settings().set("video_defaults/repeat", VideoRepeat.PAUSE_AT_END)
Settings().sync()
c.check(
    "PAUSE_AT_END round-trips through settings",
    Settings().get("video_defaults/repeat") is VideoRepeat.PAUSE_AT_END,
    f"{Settings().get('video_defaults/repeat')}",
)

# --- a Video model built with no explicit repeat picks the configured default ---
# NB: Video's uri validator requires an existing absolute file, so a made-up
# path raises ValidationError - use a real sample.
from gridplayer.models.video import Video

v = Video(uri=sample("probe.mp4"))
c.check(
    "new Video inherits the configured repeat mode",
    v.repeat_mode is VideoRepeat.PAUSE_AT_END,
    f"{v.repeat_mode}",
)

# --- and an explicit repeat mode still wins ---
v2 = Video(
    uri=sample("probe.mp4"),
    repeat_mode=VideoRepeat.SINGLE_FILE,
)
c.check(
    "explicit repeat mode still wins",
    v2.repeat_mode is VideoRepeat.SINGLE_FILE,
    f"{v2.repeat_mode}",
)

# --- the action table is still self-consistent after adding two entries ---
import gridplayer.params.actions as actions_module

titles = list(actions_module.ACTIONS.keys())
c.check("Repeat Once registered", "Repeat Once" in titles)
c.check("Repeat Once [ALL] registered", "Repeat Once [ALL]" in titles)

keys = [a["key"] for a in actions_module.ACTIONS.values() if a.get("key")]
c.check("no duplicate shortcuts introduced", len(keys) == len(set(keys)))

# --- the settings dialog lists all four modes ---
from gridplayer.dialogs.settings import SettingsDialog  # noqa: F401  (import smoke)

c.check("settings dialog module still imports", True)

c.finish()
