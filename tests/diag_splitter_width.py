"""Diagnostic: does a panel inserted into the splitter actually get width?

Uses WA_DontShowOnScreen so the window lays out for real without appearing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import bootstrap

bootstrap()

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QSplitter, QWidget

from gridplayer.widgets.playlist_panel import PlaylistPanel


def build():
    win = QWidget()
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
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


print("--- case A: panel hidden at insert time (what the app does) ---")
win, splitter, host = build()
panel = PlaylistPanel()
panel.setMinimumWidth(200)
panel.hide()
splitter.insertWidget(0, panel)

win.show()
print(
    f"  after show (panel hidden): panel.width={panel.width()} "
    f"splitter.sizes={splitter.sizes()}"
)

panel.setVisible(True)
win.layout().activate()
print(
    f"  after panel.setVisible(True): panel.width={panel.width()} "
    f"panel.isVisible={panel.isVisible()} sizes={splitter.sizes()}"
)
print(f"  panel.sizeHint={panel.sizeHint()} minimumSizeHint={panel.minimumSizeHint()}")

print()
print("--- case B: panel visible at insert time ---")
win2, splitter2, host2 = build()
panel2 = PlaylistPanel()
panel2.setMinimumWidth(200)
splitter2.insertWidget(0, panel2)
win2.show()
print(f"  panel.width={panel2.width()} sizes={splitter2.sizes()}")

print()
print("--- case C: same as A but with an explicit setSizes() after showing ---")
win3, splitter3, host3 = build()
panel3 = PlaylistPanel()
panel3.setMinimumWidth(200)
panel3.hide()
splitter3.insertWidget(0, panel3)
win3.show()
panel3.setVisible(True)
splitter3.setSizes([280, max(1, 900 - 280)])
win3.layout().activate()
print(f"  panel.width={panel3.width()} sizes={splitter3.sizes()}")
