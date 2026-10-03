"""Renders the MOD's overlay icons to a PNG so they can be eyeballed.

Run: pyenv\\Scripts\\python.exe tests\\render_icons.py [output.png]
Not a regression test (name does not match check_*.py), so _runtests.py ignores it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import bootstrap

bootstrap()

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from gridplayer.widgets.video_overlay_icons import (
    draw_menu,
    draw_repeat_list,
    draw_repeat_pause,
    draw_repeat_shuffle,
    draw_repeat_single,
)

ICON = 24
SCALE = 8
PAD = 10
LABEL_H = 18

icons = [
    ("list", draw_repeat_list, QColor("#ffffff")),
    ("single", draw_repeat_single, QColor("#ffffff")),
    ("shuffle", draw_repeat_shuffle, QColor("#ffffff")),
    ("pause", draw_repeat_pause, QColor("#ffffff")),
    ("menu", draw_menu, QColor("#ffffff")),
    ("list/hover", draw_repeat_list, QColor("#1b1b1b")),
]

cell = ICON * SCALE
width = PAD + len(icons) * (cell + PAD)
height = PAD + cell + LABEL_H + PAD

canvas = QPixmap(width, height)
canvas.fill(QColor("#3a3a3a"))

p = QPainter(canvas)
p.setRenderHint(QPainter.Antialiasing, True)

font = QFont("Consolas", 9)
p.setFont(font)

for i, (name, fn, fg) in enumerate(icons):
    x = PAD + i * (cell + PAD)

    # icon background mimics the button face
    p.fillRect(QRect(x, PAD, cell, cell), QColor("#7a7a7a"))

    p.save()
    p.translate(x, PAD)
    p.scale(SCALE, SCALE)

    bg = QColor("#7a7a7a")
    fn(QRect(0, 0, ICON, ICON), p, fg, bg)

    p.restore()

    p.setPen(QColor("#e8e8e8"))
    p.drawText(QRect(x, PAD + cell + 2, cell, LABEL_H), Qt.AlignCenter, name)

p.end()

out = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(__file__).resolve().parents[1] / "evidence" / "repeat-icons.png"
)
out.parent.mkdir(parents=True, exist_ok=True)
canvas.save(str(out))
print(f"rendered {len(icons)} icons at {SCALE}x -> {out}")

QApplication.quit()
