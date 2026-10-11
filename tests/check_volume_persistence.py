"""MOD: the volume has to survive the video that carried it.

Reported: closing GridPlayer never changed player/volume in settings.ini.

Cause: the "close the window when the last video goes away" rule means the
window is closed *because* its last video closed. By the time closeEvent runs
the grid is already empty - the block is out of ctx.video_blocks and its
video_params has been cleared - so WindowStateManager._current_volume()
returned None and _save_last_volume() returned without writing anything.

Fix: VideoBlocksManager reads the volume while the blocks are still alive
(close_single / close_all) and keeps it on ctx.last_volume; _current_volume
falls back to it when there is nothing left on screen.

Drives the real managers with stub blocks, so it fails again if that
remembering is dropped or ends up running after the blocks are torn down.
"""

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("volume persistence")

from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import Context
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.player.managers.window_state import WindowStateManager


class StubBlock:
    """Only the parts of VideoBlock the two managers reach for."""

    def __init__(self, block_id, volume):
        self.id = block_id
        self.video_params = SimpleNamespace(volume=volume)

    def forget(self):
        """What VideoBlock.reset()/cleanup() leaves behind."""
        self.video_params = None


class WindowStateStub:
    """WindowStateManager minus the window - the volume methods use _ctx only."""

    def __init__(self, ctx):
        self._ctx = ctx
        self._log = logging.getLogger("WindowStateStub")


window = QWidget()
context = Context()
blocks = VideoBlocksManager(context=context, parent=window)
state = WindowStateStub(context)


def current_volume(grid, active, last):
    context.video_blocks.clear()
    for b in grid:
        context.video_blocks.append(b)
    context.active_block = active
    context.last_active_block = last

    return WindowStateManager._current_volume(state)


c.check(
    "a fresh context has nothing remembered",
    context.last_volume is None,
    f"{context.last_volume!r}",
)

# --- reading the volume of a video that is still on screen (upstream path) ---

one = StubBlock("one", 0.3)
c.check(
    "reads the active video's volume",
    current_volume([one], one, one) == 0.3,
    f"{current_volume([one], one, one)!r}",
)

two = StubBlock("two", 0.25)
c.check(
    "falls back to the last active video when the pointer left it",
    current_volume([one, two], None, two) == 0.25,
    f"{current_volume([one, two], None, two)!r}",
)

c.check(
    "falls back to the last video when nothing was ever active",
    current_volume([one, two], None, None) == 0.25,
    f"{current_volume([one, two], None, None)!r}",
)

# --- the reported case: the grid is empty by the time the window closes ------

context.last_volume = 0.71
c.check(
    "an empty grid still reports the volume of the video that closed it",
    current_volume([], None, None) == 0.71,
    f"{current_volume([], None, None)!r}",
)

context.last_volume = None
c.check(
    "an empty grid with nothing remembered is still nothing to save",
    current_volume([], None, None) is None,
    f"{current_volume([], None, None)!r}",
)

# --- closing one video remembers its volume ---------------------------------

closing = StubBlock("closing", 0.7)
context.video_blocks.clear()
context.video_blocks.append(closing)
context.active_block = None
context.last_active_block = closing

blocks.close_single("closing")
c.check(
    "closing a video remembers the volume it had",
    context.last_volume == 0.7,
    f"{context.last_volume!r}",
)
c.check(
    "the closed block is gone from the grid",
    len(context.video_blocks) == 0,
    f"{len(context.video_blocks)}",
)

context.last_volume = 0.5
blocks._remember_volume([None])
c.check(
    "a block that is already gone leaves the remembered volume alone",
    context.last_volume == 0.5,
    f"{context.last_volume!r}",
)

# --- closing everything remembers the focused video --------------------------

first = StubBlock("first", 0.1)
focused = StubBlock("focused", 0.55)
last = StubBlock("last", 0.2)
grid = [first, focused, last]

context.last_volume = None
current_volume(grid, focused, focused)
blocks.close_all()
c.check(
    "closing every video remembers the focused one",
    context.last_volume == 0.55,
    f"{context.last_volume!r}",
)

context.last_volume = None
current_volume(grid, None, None)
blocks.close_all()
c.check(
    "with no focus it remembers the last video instead",
    context.last_volume == 0.2,
    f"{context.last_volume!r}",
)

# --- and it reads them before the blocks are torn down -----------------------


def tear_down():
    for b in context.video_blocks:
        b.forget()


context.last_volume = None
current_volume(grid, focused, focused)
blocks.close_all_signal.connect(tear_down)
blocks.close_all()
blocks.close_all_signal.disconnect(tear_down)
c.check(
    "the volumes are read before close_all_signal clears the blocks",
    context.last_volume == 0.55,
    f"{context.last_volume!r}",
)

# --- a block that has already cleared itself must not wipe what is kept ------

context.last_volume = 0.5
context.video_blocks.clear()
context.video_blocks.append(StubBlock("empty", None))
context.active_block = None
context.last_active_block = None

blocks.close_single("empty")
c.check(
    "a block with no video_params does not clobber the remembered volume",
    context.last_volume == 0.5,
    f"{context.last_volume!r}",
)

context.last_volume = 0.5
blocks.close_all()
c.check(
    "closing an already empty grid keeps the remembered volume",
    context.last_volume == 0.5,
    f"{context.last_volume!r}",
)

# --- the reported symptom, end to end: the value reaches settings.ini -------

WindowStateManager._save_last_volume(state, 0.71)

from gridplayer.settings import Settings

Settings().sync()

raw = (data_dir / "settings.ini").read_text(encoding="utf-8")
c.check(
    "the remembered volume is written to settings.ini",
    "volume=0.71" in raw,
    [line for line in raw.splitlines() if "volume" in line],
)

c.finish()
