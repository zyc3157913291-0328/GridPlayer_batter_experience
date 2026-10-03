"""Shell thumbnails for the playlist panel."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import ROOT, SAMPLES, Checker, bootstrap, sample

bootstrap()
c = Checker("shell thumbnail")

from PyQt5.QtGui import QPixmap

from gridplayer.utils.shell_thumbnail import DEFAULT_SIZE, thumbnail_image

SAMPLE = sample("probe.mp4")
NOT_MEDIA = ROOT / "README.md"

# --- a real video yields a real thumbnail ---
img = thumbnail_image(SAMPLE, DEFAULT_SIZE)
c.check("video thumbnail obtained", img is not None and not img.isNull())
c.check(
    "thumbnail has a sane size",
    img is not None and img.width() > 0 and img.height() > 0,
    f"{img.width()}x{img.height()}" if img else "none",
)
c.check(
    "thumbnail is no bigger than requested",
    img is not None and max(img.width(), img.height()) <= DEFAULT_SIZE + 8,
    f"{img.width()}x{img.height()}" if img else "none",
)

# --- it is not a blank image (the shell gave us a frame, not an empty DIB) ---
if img is not None:
    colors = {
        img.pixel(x, y)
        for x in range(0, img.width(), 4)
        for y in range(0, img.height(), 4)
    }
    c.check(
        "thumbnail is not a single flat colour",
        len(colors) > 3,
        f"{len(colors)} colours",
    )

# --- a file the shell has no thumbnail for yields None, not a crash ---
c.check("non-media returns None", thumbnail_image(NOT_MEDIA, DEFAULT_SIZE) is None)

# --- a missing file yields None ---
c.check(
    "missing file returns None",
    thumbnail_image(SAMPLES / "does-not-exist.mp4", DEFAULT_SIZE) is None,
)

# --- the QImage survives conversion to QPixmap on this thread ---
if img is not None:
    pm = QPixmap.fromImage(img)
    c.check("converts to QPixmap", not pm.isNull(), f"{pm.width()}x{pm.height()}")

c.finish()
