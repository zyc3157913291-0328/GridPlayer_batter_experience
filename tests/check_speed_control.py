"""MOD: the speed control's fixed width, the gear list, and the gesture guards.

These are requirements a screenshot cannot really check: "the control must not
reflow between 1x and 0.25x" is a layout contract, "the readout goes at the
middle of the video area, one sixth down" is a computed position, and "the list
runs largest to smallest" is an ordering. All are asserted as numbers here.

Two of the guards are checked at the source level, which is the technique
check_quit_when_empty.py already uses for wiring that only exists at runtime:
starting a drag now needs Alt, and a press on a control must not arm the speed
gesture. Neither can be exercised without a real cursor on a real window.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import ROOT, Checker, bootstrap

bootstrap()
c = Checker("speed control")

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.utils.speed_gears import (
    GEARS,
    MULTIPLICATION_SIGN,
    format_rate,
    index_for_rate,
)
from gridplayer.widgets import video_overlay as overlay_module
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_speed import HOVER_CHECK_MS

window = QWidget()
overlay = OverlayBlock(window)

button = overlay.speed_button
popup = overlay.speed_popup
indicator = overlay.speed_indicator

# the strip is only ever inspected as a widget here, never put on the screen
popup.setAttribute(Qt.WA_DontShowOnScreen, True)

# --- the control exists and is wired ---

c.check("the overlay has a speed control", button is not None)
c.check(
    "it sits between the progress bar and the rest of the right-hand controls",
    overlay.bottom_bar.indexOf(button)
    == overlay.bottom_bar.indexOf(overlay.progress_bar) + 1,
    f"bar={overlay.bottom_bar.indexOf(overlay.progress_bar)} "
    f"speed={overlay.bottom_bar.indexOf(button)} "
    f"placeholder={overlay.bottom_bar.indexOf(overlay.progress_bar_placeholder)}",
)
c.check(
    "the button asks the overlay to open the list rather than owning it",
    hasattr(button, "list_requested") and hasattr(overlay, "show_speed_list"),
)
c.check(
    "and a picked gear comes back out as a rate",
    hasattr(overlay, "speed_selected"),
)

# --- the width is fixed, whatever the label says ---

widths = []
for rate in (1.0, 1.25, 0.5, 3.0, 1.1):
    overlay.set_rate(rate)
    widths.append((rate, button.minimumWidth(), button.maximumWidth()))

c.check(
    "the button is exactly as wide as its widest label allows",
    len({w for _, w, _ in widths}) == 1,
    f"{[(r, w) for r, w, _ in widths]}",
)
c.check(
    "and the maximum width is pinned to it, so nothing else can stretch it",
    all(mn == mx for _, mn, mx in widths),
    f"{[(r, mn, mx) for r, mn, mx in widths]}",
)
c.check(
    "so 1x, 0.5x and 1.25x all occupy the same box",
    button.minimumWidth()
    >= max(
        QFontMetrics(button.font()).horizontalAdvance(format_rate(gear))
        for gear in GEARS
    ),
    f"{button.minimumWidth()}",
)

# --- the label follows the rate, including the keyboard's fine steps ---

overlay.set_rate(1.25)
c.check(
    "the button reports the rate it was given", button.rate == 1.25, f"{button.rate}"
)

overlay.set_rate(1.1)
c.check(
    "a rate that is not a gear is still displayed honestly",
    format_rate(button.rate) == f"{MULTIPLICATION_SIGN}1.1",
    f"{format_rate(button.rate)}",
)
c.check(
    "and the widget does not round it onto a gear", button.rate == 1.1, f"{button.rate}"
)
c.check(
    "the list is told about it too, so it can leave every row unselected",
    popup.rate == 1.1 and popup._rate == 1.1,
    f"property {popup.rate}, painted {popup._rate}",
)

# --- the gear list: one strip, largest rate first ---

top_down = popup.rates_top_down

c.check(
    "the list runs from the largest rate down to the smallest",
    top_down == sorted(GEARS, reverse=True),
    f"{top_down}",
)
c.check("it starts at 3x", top_down[0] == 3.0)
c.check("and ends at 0.5x", top_down[-1] == 0.5)
c.check("every gear is in it exactly once", sorted(top_down) == sorted(GEARS))

c.check(
    "the first row is the largest rate",
    popup._row_at(QPoint(5, 0)) == 0 and top_down[popup._row_at(QPoint(5, 0))] == 3.0,
)
c.check(
    "the last row is the smallest rate",
    popup._row_at(QPoint(5, popup.height() - 1)) == len(GEARS) - 1
    and top_down[-1] == 0.5,
    f"row {popup._row_at(QPoint(5, popup.height() - 1))}",
)
c.check(
    "each gear gets one row of its own",
    [popup._row_at(QPoint(5, i * popup.ROW_HEIGHT + 2)) for i in range(len(GEARS))]
    == list(range(len(GEARS))),
)
c.check(
    "a position outside the list selects nothing", popup._row_at(QPoint(5, -1)) is None
)

# --- the row it marks as current is the one it will paint bold ---
#
# Read through _rate rather than the property: an earlier version assigned a
# plain attribute of the same name, so the property read back correctly while
# paintEvent kept bolding the gear the list had started on.


def bold_row(rate):
    overlay.set_rate(rate)
    current = index_for_rate(popup._rate)

    return None if current is None else top_down.index(GEARS[current])


for rate in (3.0, 1.25, 0.5):
    c.check(
        f"the list marks {rate}x as the current row",
        bold_row(rate) == top_down.index(rate),
        f"row {bold_row(rate)} vs {top_down.index(rate)}",
    )

c.check(
    "and marks nothing when the rate is not a gear",
    bold_row(1.1) is None,
    "the keyboard's fine steps leave 1.1 behind",
)
overlay.set_rate(1.25)

# --- placement of the strip: above the speed button, exactly as wide as it ---

bar_top = QRect(20, 300, 46, 23)
popup.show_above(bar_top)

c.check(
    "the strip is exactly as wide as the speed button",
    popup.width() == bar_top.width(),
    f"{popup.width()} vs {bar_top.width()}",
)
c.check(
    "and sits directly above it",
    popup.y() + popup.height() == bar_top.top(),
    f"bottom {popup.y() + popup.height()} vs top {bar_top.top()}",
)
c.check(
    "it is left-aligned with the button", popup.x() == bar_top.left(), f"{popup.x()}"
)
c.check(
    "it is square-cornered and half transparent, like the rest of the overlay",
    popup.OPACITY == 0.5,
    "a wide, rounded, opaque slab read as a foreign window next to the control bar",
)
popup.hide()

# --- the indicator ---

c.check("the overlay owns a gesture indicator", indicator is not None)
c.check(
    "the indicator is a window of its own, so it can sit outside one grid cell",
    indicator.isWindow(),
)
c.check(
    "it cannot swallow the drag it is reporting on",
    bool(indicator.windowFlags() & Qt.WindowTransparentForInput)
    and indicator.testAttribute(Qt.WA_TransparentForMouseEvents),
)
c.check(
    "it stays on top of the video",
    bool(indicator.windowFlags() & Qt.WindowStaysOnTopHint),
)

area = QRect(100, 200, 1600, 900)
indicator.rate = 2.0
indicator.show_at(area)

c.check(
    "centred horizontally on the video area",
    abs(indicator.x() + indicator.width() // 2 - (area.left() + area.width() // 2))
    <= 1,
    f"centre {indicator.x() + indicator.width() // 2} vs {area.left() + area.width() // 2}",
)
c.check(
    "one sixth of the way down the video area",
    indicator.y() == area.top() + area.height() // 6,
    f"y {indicator.y()} vs {area.top() + area.height() // 6}",
)
c.check(
    "and a different area moves it accordingly",
    (indicator.show_at(QRect(0, 0, 800, 600)) or True)
    and indicator.y() == 100
    and indicator.x() + indicator.width() // 2 == 400,
    f"x {indicator.x()} y {indicator.y()}",
)
indicator.hide()

# --- the guards that keep the gesture out of everything else ---

dragger = (ROOT / "gridplayer" / "player" / "managers" / "drag_n_drop.py").read_text(
    encoding="utf-8"
)
block_src = (ROOT / "gridplayer" / "widgets" / "video_block.py").read_text(
    encoding="utf-8"
)

c.check(
    "moving a video around the grid now needs Alt",
    "Qt.AltModifier" in dragger,
    "otherwise a plain drag starts the modal move loop and eats the speed gesture",
)
c.check(
    "the move drag is still there behind that modifier",
    "drag_video.exec()" in dragger,
)
c.check(
    "a press on an overlay control does not arm the speed gesture",
    "is_over_control" in block_src,
    "holding the speed button used to double the speed of the video underneath",
)
c.check(
    "the block takes the mouse for the duration of the gesture",
    "self.grabMouse()" in block_src and "self.releaseMouse()" in block_src,
    "so nothing else can take the moves and the release away",
)
c.check(
    "and it gives up on the first sign the button was released elsewhere",
    "event.buttons() & Qt.LeftButton" in block_src,
    "otherwise the gesture stays stuck on and reacts to later mouse movement",
)
c.check(
    "a drag that does not change gear does not re-send the rate",
    "if steps == 0:" in block_src and "if gear == self._speed_gear:" in block_src,
    "every redundant call makes VLC re-clock its audio output and drop the sound",
)

c.check(
    "the readout follows the gesture's scope",
    "if self._long_press_ctrl:" in block_src
    and "return self._video_area_rect()" in block_src
    and "show_at(self._speed_indicator_rect())" in block_src,
    "one video -> over that video; Ctrl -> over the whole area",
)

# --- the list closes itself once the pointer is on neither of the two ---

window.setAttribute(Qt.WA_DontShowOnScreen, True)
window.resize(640, 400)
window.show()
overlay.setGeometry(0, 0, 640, 400)
QApplication.processEvents()

button_rect = QRect(button.mapToGlobal(QPoint(0, 0)), button.size())
away = button_rect.center() + QPoint(400, 200)

c.check(
    "the pointer on the speed button counts as being on the list",
    overlay.is_over_speed_list(button_rect.center()),
    f"button at {button_rect}",
)
c.check(
    "a point on neither the button nor the list does not",
    not overlay.is_over_speed_list(away),
    f"{away}",
)

popup.show_above(button_rect)
c.check(
    "the open list is a target of its own",
    overlay.is_over_speed_list(popup.mapToGlobal(popup.rect().center())),
    f"list at {popup.geometry()}",
)
c.check(
    "the two touch, so moving between them crosses no dead ground",
    popup.y() + popup.height() == button_rect.top(),
    f"list bottom {popup.y() + popup.height()} vs button top {button_rect.top()}",
)
popup.hide()


class CursorStub:
    """Stands in for the cursor, so the poll can be driven from here."""

    pos_value = QPoint(0, 0)

    @staticmethod
    def pos():
        return CursorStub.pos_value


real_cursor = overlay_module.QCursor
overlay_module.QCursor = CursorStub

overlay.set_rate(1.25)
overlay.show_speed_list()
c.check(
    "opening the list starts the poll",
    popup.isVisible() and overlay.speed_list_hover_timer.isActive(),
)
c.check(
    "the list it opens touches the button it opened from",
    popup.y() + popup.height() == button.mapToGlobal(QPoint(0, 0)).y(),
    f"list bottom {popup.y() + popup.height()} "
    f"vs button top {button.mapToGlobal(QPoint(0, 0)).y()}",
)

CursorStub.pos_value = button_rect.center()
overlay.close_speed_list_when_unhovered()
c.check(
    "a pointer resting on the button keeps it open",
    popup.isVisible(),
    "the button is part of the target",
)

CursorStub.pos_value = popup.mapToGlobal(popup.rect().center())
overlay.close_speed_list_when_unhovered()
c.check("and so does one inside the list", popup.isVisible())

CursorStub.pos_value = away
overlay.close_speed_list_when_unhovered()
c.check(
    "it closes by itself once the pointer is on neither",
    not popup.isVisible(),
    "no gear picked and no click away - the pointer simply left",
)
c.check(
    "and the polling stops with it",
    not overlay.speed_list_hover_timer.isActive(),
)

overlay_module.QCursor = real_cursor
popup.hide()

overlay_src = (ROOT / "gridplayer" / "widgets" / "video_overlay.py").read_text(
    encoding="utf-8"
)

c.check(
    "it polls at a rate the eye reads as immediate",
    overlay.speed_list_hover_timer.interval() == HOVER_CHECK_MS,
    f"{overlay.speed_list_hover_timer.interval()} ms",
)
c.check(
    "and the timer is owned by the overlay, so a closed video takes it down",
    overlay.speed_list_hover_timer.parent() is overlay,
    "a timer outliving its widget would tick on a deleted object",
)
c.check(
    "a popup holding the mouse grab is why this polls, not a leave event",
    "HOVER_CHECK_MS" in overlay_src and "timeout.connect" in overlay_src,
    "the button sees no leave event while the list is open",
)

c.finish()
