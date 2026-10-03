"""Offscreen render of the playlist panel with real shell thumbnails.

Not a regression test (name is not check_*.py). Uses QWidget.grab(), so no
desktop interaction is needed.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import SAMPLES, bootstrap

bootstrap()

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from gridplayer.utils.shell_thumbnail import DEFAULT_SIZE, thumbnail_image
from gridplayer.widgets.playlist_panel import DEFAULT_PANEL_WIDTH, PlaylistPanel

# a real folder, so at least some rows get genuine shell thumbnails
sample_dir = SAMPLES

from gridplayer.utils.media_folder import scan_folder

entries = scan_folder(sample_dir / "probe.mp4")
print(f"scanned {len(entries)} real file(s) in {sample_dir}")

# pad with fabricated siblings so layout/eliding is visible too
from gridplayer.models.media_entry import MediaEntry

now = time.time()
entries += [
    MediaEntry(Path(r"E:\Movies") / name, name, size, now - i * 86400, dur)
    for i, (name, size, dur) in enumerate(
        [
            ("Interstellar.2014.2160p.BluRay.x265.mkv", 48_200_000_000, 8880),
            (
                "a very long file name that should get elided somewhere.mov",
                96_000_000,
                None,
            ),
            ("episode-03.mkv", 640_000_000, 1450),
        ]
    )
]

panel = PlaylistPanel()
panel.resize(DEFAULT_PANEL_WIDTH + 20, 900)

first_image = None
for e in entries:
    print(f"  fetching thumbnail: {e.name}")
    img = thumbnail_image(e.path, DEFAULT_SIZE)
    if img is not None and first_image is None:
        first_image = (e.name, img)
    panel.set_thumbnail(e.key, img)

# dump one thumbnail enlarged, to check orientation against the source video
if first_image is not None:
    name, img = first_image
    big = img.scaled(
        img.width() * 4, img.height() * 4, Qt.KeepAspectRatio, Qt.FastTransformation
    )
    zoom_path = Path(__file__).resolve().parents[1] / "evidence" / "p3-thumb-zoom.png"
    big.save(str(zoom_path))
    print(f"  zoomed thumbnail ({name}) -> {zoom_path}")

panel.set_history({entries[-1].key: 1})
panel.set_entries(entries, sample_dir / "probe.mp4")

out = Path(__file__).resolve().parents[1] / "evidence" / "p3-panel-thumbnails.png"
panel.grab().save(str(out))
print(f"rendered -> {out}")
