"""P3 Task 5: the grid moves onto a host widget so a side panel can share the window."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("layout host")

from PyQt5.QtWidgets import QSplitter, QWidget

from gridplayer.player.manager import Context
from gridplayer.player.managers.grid import GridManager

ctx = Context()
ctx.video_blocks = []  # _adjust_window() reads it
win = QWidget()
grid = GridManager(context=ctx, parent=win)

c.check("context exposes grid_host", hasattr(ctx, "grid_host"))
c.check("context exposes layout_splitter", hasattr(ctx, "layout_splitter"))

splitter = ctx.layout_splitter
c.check("splitter is a QSplitter", isinstance(splitter, QSplitter))
c.check(
    "window has an outer layout holding the splitter",
    win.layout() is not None and win.layout().indexOf(splitter) >= 0,
    f"{win.layout()}",
)
c.check(
    "grid_host lives inside the splitter",
    splitter.indexOf(ctx.grid_host) >= 0,
    f"index={splitter.indexOf(ctx.grid_host)}",
)
c.check(
    "the grid layout is on grid_host, not on the window",
    ctx.grid_host.layout() is not None,
)
c.check(
    "grid_host is the only widget in the splitter for now",
    splitter.count() == 1,
    f"count={splitter.count()}",
)

# --- the panel is appended, so it sits on the RIGHT of the video area ---
panel = QWidget()
splitter.addWidget(panel)
c.check(
    "grid_host stays first after adding a panel", splitter.widget(0) is ctx.grid_host
)
c.check("panel is last (right side)", splitter.widget(splitter.count() - 1) is panel)

# --- the info label (shown when there are no videos) belongs to the grid host ---
c.check(
    "info label is parented to grid_host",
    grid._info_label.parent() is ctx.grid_host,
    f"{grid._info_label.parent()}",
)

# --- minimum width grows once the panel reserves space ---
panel.setMinimumWidth(200)
grid._adjust_window()
min_with_panel = grid._minimum_size
c.check(
    "minimum width grew by the panel width",
    min_with_panel.width() >= 640 + 200,
    f"{min_with_panel.width()}x{min_with_panel.height()}",
)

panel.hide()
grid._adjust_window()
c.check(
    "hidden panel does not inflate the minimum",
    grid._minimum_size.width() < min_with_panel.width(),
    f"{grid._minimum_size.width()}",
)

c.finish()
