"""Closing a video while one fills the screen must leave a well formed grid.

Regression for the big blank band at the bottom of the window.

video_count_changed reaches grid.reload_video_grid *before*
single_mode.set_video_count, because that is the order the connection table is
built in. So the grid is rebuilt while the other blocks are still hidden by
single mode: at that moment visible_count is 1, grid_dimensions collapses to
1x1, and _fill_last_row crams every remaining video into one row. Turning single
mode off then shows them again and adapt_grid applies 2x2 stretch factors to a
layout that only ever got one row of items - so the second row is empty and the
bottom half of the window is blank.

The check is a coverage measurement: the visible blocks must tile the grid host.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("grid after close")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import Commands, Context
from gridplayer.player.managers.grid import GridManager
from gridplayer.player.managers.single_mode import SingleModeManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager


class StubParams:
    is_paused = False


class StubBlock(QWidget):
    def __init__(self, block_id):
        super().__init__()

        self.id = block_id
        self.title = None
        self.video_params = StubParams()

    def set_pause(self, paused):
        self.video_params.is_paused = paused


player = QWidget()
player.setAttribute(Qt.WA_DontShowOnScreen, True)
player.resize(1000, 700)

ctx = Context()
ctx.commands = Commands()
ctx.active_block = None
ctx.last_active_block = None

# VideoBlocksManager owns video_count_changed and resets ctx.video_blocks
vbm = VideoBlocksManager(context=ctx, parent=player)
grid = GridManager(context=ctx, parent=player)
sm = SingleModeManager(context=ctx, parent=player)

grid.minimum_size_changed.connect(player.setMinimumSize)

# ManagersManager._register_commands does this for real: single_mode reaches the
# grid through ctx.commands, exactly like its fullscreen() call does
ctx.commands.update(grid.commands)
ctx.commands.update(sm.commands)

# same order as player.py: grid listens before single_mode
vbm.video_count_changed.connect(grid.reload_video_grid)
vbm.video_count_changed.connect(sm.set_video_count)
sm.mode_changed.connect(grid.adapt_grid)

player.show()


def host():
    return ctx.grid_host


def coverage(blocks):
    """Fraction of the grid host covered by visible video blocks."""

    area = host().rect()
    if area.width() <= 0 or area.height() <= 0:
        return 0.0

    rects = [b.geometry() for b in blocks if b.isVisible()]

    step = 4
    hits = 0
    total = 0

    for y in range(0, area.height(), step):
        for x in range(0, area.width(), step):
            total += 1
            if any(r.contains(x, y) for r in rects):
                hits += 1

    return hits / total if total else 0.0


def rows_used(blocks):
    return sorted({b.geometry().top() for b in blocks if b.isVisible()})


blocks = [StubBlock(f"b{i}") for i in range(4)]
for b in blocks:
    ctx.video_blocks.append(b)

# first layout, four videos, not in single mode
vbm.video_count_changed.emit(len(ctx.video_blocks))
player.layout().activate()

c.check(
    "four videos tile the grid",
    coverage(blocks) > 0.97,
    f"coverage {coverage(blocks):.3f}",
)

# one video fills the screen
ctx.active_block = blocks[0]
sm.single_mode_on()
player.layout().activate()

c.check(
    "single mode hides the other three",
    [b.isVisible() for b in blocks] == [True, False, False, False],
    f"{[b.isVisible() for b in blocks]}",
)

# close one of the hidden tabs, exactly as the tab's x does
closing = ctx.video_blocks[3]
ctx.video_blocks.remove(closing)
closing.hide()

vbm.video_count_changed.emit(len(ctx.video_blocks))
player.layout().activate()

remaining = [b for b in ctx.video_blocks]

c.check("single mode is over", ctx.is_single_mode is False)
c.check(
    "all remaining videos are visible",
    all(b.isVisible() for b in remaining),
    f"{[b.isVisible() for b in remaining]}",
)
c.check(
    "three videos tile the grid with no blank band",
    coverage(remaining) > 0.97,
    f"coverage {coverage(remaining):.3f}",
)
c.check(
    "the grid really uses two rows",
    len(rows_used(remaining)) == 2,
    f"rows at {rows_used(remaining)} in a {host().height()}px host",
)

# the same must hold when the video filling the screen is the one closed
ctx.active_block = None
blocks2 = [StubBlock(f"c{i}") for i in range(4)]
ctx.video_blocks.clear()
for b in blocks2:
    ctx.video_blocks.append(b)

vbm.video_count_changed.emit(len(ctx.video_blocks))
ctx.active_block = blocks2[0]
sm.single_mode_on()
player.layout().activate()

closing2 = ctx.video_blocks[0]
ctx.video_blocks.remove(closing2)
closing2.hide()

vbm.video_count_changed.emit(len(ctx.video_blocks))
player.layout().activate()

left = [b for b in ctx.video_blocks]
c.check(
    "closing the video on screen also leaves a full grid",
    coverage(left) > 0.97,
    f"coverage {coverage(left):.3f}",
)

c.finish()
