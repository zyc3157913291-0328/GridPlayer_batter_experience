"""Regression: a panel inserted while hidden must actually get splitter width.

Reported by the user as "clicking the hamburger does not expand the playlist".
Root cause: QSplitter records each child's size when it lays out; a child that
was hidden at insert time is recorded as 0, and setVisible(True) later does not
make the splitter give it any space - so the panel was 'visible' with width 0.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("panel visibility")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QSplitter, QWidget

from gridplayer.widgets.playlist_panel import (
    DEFAULT_PANEL_WIDTH,
    PlaylistPanel,
    show_in_splitter,
)


def build_splitter():
    win = QWidget()
    win.setAttribute(Qt.WA_DontShowOnScreen, True)  # lays out for real, shows nothing
    win.resize(900, 560)

    outer = QHBoxLayout(win)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    splitter = QSplitter(Qt.Horizontal, win)
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(3)
    outer.addWidget(splitter)

    host = QWidget()
    splitter.addWidget(host)

    return win, splitter, host


# --- the reported failure mode, reproduced then fixed ------------------------
win, splitter, host = build_splitter()
panel = PlaylistPanel()
panel.setMinimumWidth(200)
panel.hide()  # the app hides it at construction
splitter.addWidget(panel)
win.show()

c.check(
    "a hidden-inserted panel really does start at zero width",
    splitter.sizes()[-1] == 0,
    f"{splitter.sizes()}",
)

show_in_splitter(splitter, panel, 0)
win.layout().activate()

sizes = splitter.sizes()
c.check(
    "panel got real width after show_in_splitter",
    sizes[-1] >= panel.minimumWidth(),
    f"{sizes}",
)
c.check(
    "video area keeps the rest",
    sizes[0] > 0 and sum(sizes) > panel.minimumWidth(),
    f"{sizes}",
)
c.check("panel reports itself visible", panel.isVisible())

# --- it respects a remembered width ------------------------------------------
win2, splitter2, host2 = build_splitter()
panel2 = PlaylistPanel()
panel2.setMinimumWidth(200)
panel2.hide()
splitter2.addWidget(panel2)
win2.show()
show_in_splitter(splitter2, panel2, 360)
c.check(
    "remembered width is honoured", splitter2.sizes()[-1] == 360, f"{splitter2.sizes()}"
)

# --- it never squeezes the video area below the floor ------------------------
win3, splitter3, host3 = build_splitter()
panel3 = PlaylistPanel()
panel3.setMinimumWidth(200)
panel3.hide()
splitter3.addWidget(panel3)
win3.show()
show_in_splitter(splitter3, panel3, 5000)  # an absurd remembered width
c.check(
    "absurd width is clamped, video area survives",
    splitter3.sizes()[0] >= 160,
    f"{splitter3.sizes()}",
)

show_in_splitter(splitter3, panel3, 0)
c.check(
    "width 0 falls back to the default",
    splitter3.sizes()[-1] == DEFAULT_PANEL_WIDTH,
    f"{splitter3.sizes()}",
)

c.finish()
