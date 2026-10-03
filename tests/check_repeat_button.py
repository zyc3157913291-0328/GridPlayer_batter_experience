"""P2 Task 2: the repeat button and its four icons.

Painting is only smoke-tested (each icon must draw without raising); the real
look is verified by screenshot in Task 3. What is asserted properly here is the
button's state machine and its wiring.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("repeat button")

from PyQt5.QtCore import QRect
from PyQt5.QtGui import QColor, QPainter, QPixmap

from gridplayer.params.static import VideoRepeat
from gridplayer.widgets.video_overlay_buttons import OverlayRepeatButton
from gridplayer.widgets.video_overlay_icons import (
    draw_menu,
    draw_repeat_list,
    draw_repeat_pause,
    draw_repeat_shuffle,
    draw_repeat_single,
)

# --- every icon paints without raising ---
icons = {
    "single": draw_repeat_single,
    "list": draw_repeat_list,
    "shuffle": draw_repeat_shuffle,
    "pause": draw_repeat_pause,
    "menu": draw_menu,
}

BACKDROP = QColor("black")

for name, fn in icons.items():
    pm = QPixmap(24, 24)
    pm.fill(BACKDROP)
    p = QPainter(pm)

    try:
        fn(QRect(0, 0, 24, 24), p, QColor("white"), BACKDROP)
        ok, err = True, ""
    except Exception as e:  # noqa: BLE001
        ok, err = False, repr(e)
    finally:
        p.end()

    # Count changed pixels rather than sampling one: the list icon is a ring,
    # so its centre is legitimately empty.
    img = pm.toImage()
    painted_px = sum(
        1 for x in range(24) for y in range(24) if img.pixelColor(x, y) != BACKDROP
    )

    c.check(f"icon paints: {name}", ok, err)
    c.check(
        f"icon actually drew something: {name}", painted_px > 20, f"{painted_px} px"
    )

# --- the button follows its mode and exposes a tooltip ---
btn = OverlayRepeatButton()
c.check(
    "default mode is list loop",
    btn.repeat_mode is VideoRepeat.DIR,
    f"{btn.repeat_mode}",
)

for mode in (
    VideoRepeat.SINGLE_FILE,
    VideoRepeat.PAUSE_AT_END,
    VideoRepeat.DIR_SHUFFLE,
):
    btn.repeat_mode = mode
    c.check(f"button accepts {mode.value}", btn.repeat_mode is mode)

c.check("tooltip is set", bool(btn.toolTip()), f"{btn.toolTip()!r}")

# --- clicking walks the whole cycle ---
btn.repeat_mode = VideoRepeat.DIR
seen = []
for _ in range(4):
    btn.clicked.emit()
    seen.append(btn.repeat_mode)

c.check(
    "button walks the full cycle on click",
    set(seen)
    == set(
        VIDEO_REPEAT_CYCLE := (
            VideoRepeat.DIR,
            VideoRepeat.SINGLE_FILE,
            VideoRepeat.DIR_SHUFFLE,
            VideoRepeat.PAUSE_AT_END,
        )
    ),
    f"{[m.value for m in seen]}",
)
c.check(
    "cycle returns to the start after four clicks",
    btn.repeat_mode is VideoRepeat.DIR,
    f"{btn.repeat_mode}",
)

# --- the button reports the change so VideoBlock can persist it ---
emitted = []
btn.repeat_mode_changed.connect(emitted.append)
btn.clicked.emit()
c.check(
    "clicking emits repeat_mode_changed",
    len(emitted) == 1 and emitted[0] is VideoRepeat.SINGLE_FILE,
    f"{[m.value for m in emitted]}",
)

# --- setting the mode programmatically must NOT re-emit (no feedback loop) ---
emitted.clear()
btn.repeat_mode = VideoRepeat.PAUSE_AT_END
c.check("programmatic set stays silent", emitted == [], f"{emitted}")

c.finish()
