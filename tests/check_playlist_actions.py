"""Playlist context-menu actions: the "play next" override and the new-window flag."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("playlist actions")

from gridplayer.utils.single_instance import NEW_WINDOW_FLAG
from gridplayer.widgets.playlist_panel import PlaylistPanel
from gridplayer.widgets.video_block import VideoBlock


# --- "play next" is a one-shot override ------------------------------------
# Tested against the real methods without building a VideoBlock (which needs a
# video driver): the logic lives entirely in these two methods.
class FakeBlock:
    _next_override = None
    _resume_after_override = None
    set_next_override = VideoBlock.set_next_override
    _take_next_override = VideoBlock._take_next_override
    _take_resume_override = VideoBlock._take_resume_override


blk = FakeBlock()
c.check("no override to begin with", blk._take_next_override() is None)

blk.set_next_override(r"E:\some\clip.mp4")
taken = blk._take_next_override()
c.check("override is returned once", taken == Path(r"E:\some\clip.mp4"), f"{taken}")
c.check("override is consumed, not sticky", blk._take_next_override() is None)

# a fresh block must not inherit another block's override
c.check(
    "class-level default keeps blocks independent",
    FakeBlock()._take_next_override() is None,
)

# it accepts a Path as well as a str
blk.set_next_override(Path(r"E:\some\other.mkv"))
c.check("accepts a Path", blk._take_next_override() == Path(r"E:\some\other.mkv"))

# --- "play next" INSERTS; the original order resumes afterwards ------------
# order a b c d e, d requested while a plays -> a d b c d e
c.check("resume slot starts empty", blk._take_resume_override() is None)

blk._resume_after_override = Path(r"E:\some\b.mp4")  # what next_video() would arm
c.check(
    "resume slot is consumed once",
    blk._take_resume_override() == Path(r"E:\some\b.mp4"),
)
c.check("resume slot does not persist", blk._take_resume_override() is None)

# a block must not inherit another block's pending resume
c.check("resume is per-block, not shared", FakeBlock()._take_resume_override() is None)

# --- the panel exposes the three actions ------------------------------------
panel = PlaylistPanel()
for name in ("entry_play_next", "entry_new_window", "entry_add_to_grid"):
    c.check(f"panel has signal {name}", hasattr(panel, name))

got = []
panel.entry_play_next.connect(got.append)
panel.entry_new_window.connect(got.append)
panel.entry_add_to_grid.connect(got.append)
c.check("signals are connectable", len(got) == 0)

# --- the flag is a real constant, not a magic string ------------------------
c.check(
    "new-window flag is defined", NEW_WINDOW_FLAG == "--new-window", NEW_WINDOW_FLAG
)

c.finish()
