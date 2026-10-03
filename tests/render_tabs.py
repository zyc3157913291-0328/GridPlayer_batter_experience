"""Offscreen render of the single-mode tab strip for visual checking.

QWidget.grab() draws without showing anything, so this needs no desktop
interaction and steals no screen content. Not a regression test (the name is
not check_*.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import bootstrap

bootstrap()

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QWidget

from gridplayer.settings import Settings
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_tabs import OverlayTab

OUT = Path(__file__).resolve().parents[1] / "evidence"
OUT.mkdir(parents=True, exist_ok=True)

VIDEOS = [
    ("b1", "Interstellar.2014.2160p.BluRay.x265.mkv"),
    ("b2", "clip 2.mp4"),
    ("b3", "a quite long episode file name.mkv"),
    ("b4", "episode-04.mov"),
]

CURRENT = "b2"


def build(width, height, style):
    Settings().set("misc/tab_style", style)

    host = QWidget()
    host.setAutoFillBackground(True)

    palette = host.palette()
    palette.setColor(QPalette.Window, QColor("#2b2b2b"))
    host.setPalette(palette)

    host.resize(width, height)

    overlay = OverlayBlock(parent=host)
    overlay.setGeometry(0, 0, width, height)

    # the live overlay is drawn at 50% opacity over live video; against a flat
    # backdrop that just washes the preview out
    overlay.setGraphicsEffect(None)

    overlay.set_label(dict((i, n) for i, n in VIDEOS)[CURRENT])
    overlay.set_position(96_000, 600_000)

    overlay.set_tabs(VIDEOS, CURRENT)

    return host, overlay


def render(overlay, host, name, hover=None):
    out = OUT / name
    host.grab().save(str(out))

    print(f"rendered -> {out}   style={overlay.tab_bar.style}")

    bar_y = overlay.tab_bar.mapTo(overlay, overlay.tab_bar.rect().topLeft()).y()
    title_y = overlay.label_text.mapTo(overlay, overlay.label_text.rect().topLeft()).y()
    bar_bottom = bar_y + overlay.tab_bar.height()

    print(f"    tab bar  y={bar_y}..{bar_bottom}  (h={overlay.tab_bar.height()})")
    print(
        f"    name bar y={title_y}  h={overlay.label_text.height()}"
        f"  -> gap {title_y - bar_bottom}px"
    )

    for t in overlay.tab_bar.tabs:
        origin = t.mapTo(overlay, t.rect().topLeft())
        print(
            f"    tab {t.block_id}: x={origin.x()} y={origin.y()} "
            f"{t.width()}x{t.height()} cur={t.is_current} label={t._label!r}"
        )

    if hover:
        tabs = {t.block_id: t for t in overlay.tab_bar.tabs}
        tabs[hover].underMouse = lambda: True
        tabs[hover].update()

        host.grab().save(str(out.with_name(out.stem + "-hover.png")))
        print(f"rendered -> {out.with_name(out.stem + '-hover.png')}")

    return out


for style in ("bar", "merged"):
    host, overlay = build(1200, 260, style)
    overlay.tab_bar.layout().activate()

    render(overlay, host, f"p3-tabs-{style}.png", hover="b3")

print(f"\ntab count: {len(overlay.tab_bar.findChildren(OverlayTab))}")
