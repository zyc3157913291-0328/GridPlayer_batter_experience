"""Offscreen render of the playlist panel for visual checking.

QWidget.grab() draws the widget without showing it, so this needs no desktop
interaction. Not a regression check (name is not check_*.py).

The panel is grabbed through a PARENT on purpose. Grabbing it on its own takes a
different path in Qt and happily renders a styled background that the widget
never actually paints when it is drawn as a child - so a standalone grab once
showed a dark panel while the running app had a pale strip above the list.
Putting it in a splitter inside a host, with the style the app sets, is what the
real window does.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import bootstrap

bootstrap()

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QSplitter,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)

from gridplayer.models.media_entry import MediaEntry
from gridplayer.widgets.playlist_panel import PlaylistPanel

# main/init_app.py does this, and the style changes how buttons are drawn
QApplication.instance().setStyle(QStyleFactory.create("Fusion"))

folder = Path(r"E:\Movies\Some Folder With A Long Name")

names = [
    ("Interstellar.2014.2160p.BluRay.x265.mkv", 48_200_000_000, 8880),
    ("clip 2.mp4", 210_000_000, 754),
    ("clip 10.mp4", 1_400_000_000, 3900),
    ("a very long file name that should get elided somewhere.mov", 96_000_000, None),
    ("episode-03.mkv", 640_000_000, 1450),
    ("episode-04.mkv", 651_000_000, 1466),
]

now = time.time()
entries = [
    MediaEntry(folder / n, n, size, now - i * 86400, dur)
    for i, (n, size, dur) in enumerate(names)
]

host = QWidget()
host.resize(560, 460)

split = QSplitter(Qt.Horizontal, host)
split.addWidget(QWidget(split))  # stands in for the video area
panel = PlaylistPanel(split)
split.addWidget(panel)
split.setSizes([200, 360])

layout = QVBoxLayout(host)
layout.setContentsMargins(0, 0, 0, 0)
layout.addWidget(split)

panel.set_history({entries[3].key: 1})  # give the "history" sort something to chew on
panel.set_entries(entries, folder / "clip 10.mp4")

OUT_DIR = Path(__file__).resolve().parents[1] / "evidence"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def shot(name):
    path = OUT_DIR / name
    host.grab().save(str(path))
    print(f"rendered -> {path}")
    return path


shot("p3-panel-preview.png")

# a second shot with a duration sort, to show the header state changes
panel.set_sort("duration", True)
shot("p3-panel-preview-duration-sort.png")
