"""P3 Task 6: the playlist side panel widget."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("playlist panel")

from gridplayer.models.media_entry import MediaEntry
from gridplayer.widgets.playlist_panel import ROLE_CURRENT, ROLE_PATH, PlaylistPanel

folder = data_dir / "v"
folder.mkdir()

entries = [
    MediaEntry(folder / "a.mp4", "a.mp4", 100, 1000.0, 3000),
    MediaEntry(folder / "b.mp4", "b.mp4", 300, 2000.0, None),
    MediaEntry(folder / "c.mp4", "c.mp4", 200, 3000.0, 1000),
]

panel = PlaylistPanel()
panel.set_entries(entries, folder / "b.mp4")

c.check("row count matches", panel.count() == 3, f"{panel.count()}")

paths = [panel.item(i).data(ROLE_PATH) for i in range(panel.count())]
c.check("rows carry their path", all(isinstance(p, Path) for p in paths), f"{paths}")

flags = [bool(panel.item(i).data(ROLE_CURRENT)) for i in range(panel.count())]
c.check("exactly one row is marked as playing", sum(flags) == 1, f"{flags}")
c.check(
    "the marked row is the current file",
    flags[[p.name for p in paths].index("b.mp4")] is True,
)

# --- activating a row emits its Path ---
got = []
panel.entry_activated.connect(got.append)
panel.activate_row(0)
c.check("activation emits a Path", len(got) == 1 and isinstance(got[0], Path), f"{got}")
c.check(
    "activation carries the right path",
    got and got[0].name == panel.item(0).data(ROLE_PATH).name,
    f"{got}",
)

# --- sorting drives the visible order ---
panel.set_sort("size", True)
order = [panel.item(i).data(ROLE_PATH).name for i in range(panel.count())]
c.check("size desc order applied", order == ["b.mp4", "c.mp4", "a.mp4"], f"{order}")

# --- programmatic vs user-driven sorting ---
emitted = []
panel.sort_changed.connect(lambda k, d: emitted.append((k, d)))

panel.set_sort("name", False)
c.check(
    "set_sort updates the properties",
    panel.sort_key == "name" and panel.sort_desc is False,
    f"{panel.sort_key}/{panel.sort_desc}",
)
c.check("programmatic set_sort stays silent", emitted == [], f"{emitted}")

panel.apply_sort("mtime", True)
c.check(
    "apply_sort updates the properties",
    panel.sort_key == "mtime" and panel.sort_desc is True,
    f"{panel.sort_key}/{panel.sort_desc}",
)
c.check("user-driven apply_sort notifies", ("mtime", True) in emitted, f"{emitted}")

# --- an unknown sort key falls back instead of blowing up ---
panel.apply_sort("nonsense", False)
c.check("unknown sort key falls back to name", panel.sort_key == "name", panel.sort_key)

# --- duration backfill ---
panel.update_duration(entries[1].key, 5000)
c.check(
    "duration backfilled",
    panel.entry_duration(entries[1].key) == 5000,
    f"{panel.entry_duration(entries[1].key)}",
)

# --- clearing ---
panel.set_entries([], None)
c.check("cleared", panel.count() == 0, f"{panel.count()}")

# --- the panel's own background must actually reach the sort bar ------------
#
# Regression: a stylesheet `background` on a plain QWidget subclass is NOT
# painted when the widget is drawn as a child of something else - only
# Qt.WA_StyledBackground makes that happen. Without it the folder label and the
# sort buttons above the list showed whatever palette colour the host app had
# (a pale #f0f0f0 under this app's Fusion/light palette) while the list below
# stayed dark, so the sort bar looked like a different theme.
#
# The grab has to go through a PARENT. Grabbing the panel on its own takes a
# different code path in Qt and renders correctly even when broken, which is
# exactly why the offscreen previews missed this.

import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import (
    QApplication,
    QSplitter,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)

QApplication.instance().setStyle(QStyleFactory.create("Fusion"))

style_panel = PlaylistPanel()
style_host = QWidget()
style_host.resize(560, 700)

style_split = QSplitter(Qt.Horizontal, style_host)
style_split.addWidget(QWidget(style_split))  # stands in for the video area
style_split.addWidget(style_panel)
style_split.setSizes([200, 360])

style_layout = QVBoxLayout(style_host)
style_layout.setContentsMargins(0, 0, 0, 0)
style_layout.addWidget(style_split)

style_panel.set_entries(entries, folder / "b.mp4")

declared = re.search(
    r"PlaylistPanel \{ background: (#[0-9a-fA-F]{6});", style_panel.styleSheet()
)
c.check("the panel declares a background colour", declared is not None)

expected = declared.group(1) if declared else "#232323"

shot = QImage(style_host.grab().toImage())
origin = style_panel.mapTo(style_host, style_panel.rect().topLeft())
sample_x = origin.x() + style_panel.width() - 30


def sample(dy):
    return shot.pixelColor(sample_x, origin.y() + dy).name()


sort_bar = sample(30)  # the folder label / sort button strip
list_bg = sample(style_panel.height() - 20)  # below the last row

c.check(
    "the sort bar is painted in the panel's own dark colour",
    sort_bar == expected,
    f"got {sort_bar}, expected {expected}",
)
c.check(
    "and the list behind it is the same colour",
    list_bg == expected,
    f"got {list_bg}, expected {expected}",
)

c.finish()
