"""MOD: the volume bar is a hover control, with the mute button as its handle.

The bar used to sit permanently against the right edge of the video, taking a
strip of the picture from every video whether or not anyone was touching the
volume. The request is that it appears while the pointer is on the mute button
and goes away again afterwards - with the button's own left click still just
muting.

The button and the bar are two separate widgets, so leaving one starts a short
grace period instead of hiding on the spot; the same position is then re-checked
against both.

Run: pyenv\\Scripts\\python.exe tests\\check_volume_bar_hover.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("volume bar hover")

from PyQt5.QtCore import QEvent, QPoint
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.widgets import video_overlay as overlay_module
from gridplayer.widgets.video_overlay import VOLUME_HOVER_GRACE_MS, OverlayBlock

window = QWidget()
overlay = OverlayBlock(window)

bar = overlay.volume_bar
button = overlay.volume_button


class CursorStub:
    """Stands in for QCursor so a position can be named without moving a mouse."""

    def __init__(self, pos):
        self._pos = pos

    def pos(self):
        return self._pos


def on(widget, point):
    """A global position that falls inside the widget."""

    return CursorStub(widget.mapToGlobal(point))


def away(widget):
    """A global position just outside the widget, to the lower right."""

    return CursorStub(
        widget.mapToGlobal(QPoint(widget.width() + 20, widget.height() + 20))
    )


real_cursor = overlay_module.QCursor
real_module_cursor = overlay_module.QCursor

try:
    # isHidden() rather than isVisible(): nothing here is ever put on screen,
    # and isVisible() would be False for every widget in the test.
    c.check("the volume bar starts hidden", bar.isHidden() is True)
    c.check(
        "nothing about the bar's level is lost while it is hidden",
        bar.position is not None,
    )

    overlay.update_volume_bar_visibility()
    c.check(
        "and it stays hidden when the pointer is nowhere near",
        bar.isHidden() is True,
    )

    # --- hovering the mute button reveals it ---

    overlay_module.QCursor = on(button, QPoint(5, 5))
    QApplication.sendEvent(button, QEvent(QEvent.Enter))

    c.check("hovering the mute button shows the bar", bar.isHidden() is False)

    # --- leaving the button does not hide it on the spot ---

    QApplication.sendEvent(button, QEvent(QEvent.Leave))

    c.check(
        "leaving starts the grace period",
        overlay.volume_bar_hover_timer.isActive() is True,
    )
    c.check("and the bar is still up during it", bar.isHidden() is False)

    # --- landing on the bar keeps it, and the timer is called off ---

    overlay_module.QCursor = on(bar, QPoint(2, 2))
    QApplication.sendEvent(bar, QEvent(QEvent.Enter))

    c.check(
        "reaching the bar calls the grace period off",
        overlay.volume_bar_hover_timer.isActive() is False,
    )
    c.check("and the bar is still up", bar.isHidden() is False)

    overlay.update_volume_bar_visibility()
    c.check(
        "a position on the bar counts as hovering it",
        bar.isHidden() is False,
    )

    # --- leaving both takes it away ---

    overlay_module.QCursor = away(bar)
    QApplication.sendEvent(bar, QEvent(QEvent.Leave))
    overlay.update_volume_bar_visibility()

    c.check(
        "leaving the bar as well takes it away",
        bar.isHidden() is True,
    )

    # --- hovering the bar itself brings it up ---

    overlay_module.QCursor = on(bar, QPoint(2, 2))
    overlay.update_volume_bar_visibility()
    c.check("a hovering position over the bar shows it", bar.isHidden() is False)

    # --- the grace period is short and one-shot ---

    c.check(
        f"the grace period is {VOLUME_HOVER_GRACE_MS}ms",
        overlay.volume_bar_hover_timer.interval() == VOLUME_HOVER_GRACE_MS,
    )
    c.check(
        "and it fires only once",
        overlay.volume_bar_hover_timer.isSingleShot() is True,
    )
    c.check(
        "owning the timer by the overlay keeps it off deleted widgets",
        overlay.volume_bar_hover_timer.parent() is overlay,
    )

    # --- a muted video has no level to show ---

    overlay_module.QCursor = on(button, QPoint(5, 5))
    overlay.set_is_muted(True)

    c.check("muting takes the bar away", bar.isHidden() is True)

    overlay.update_volume_bar_visibility()
    c.check(
        "and it stays away while the pointer sits on the button",
        bar.isHidden() is True,
    )

    QApplication.sendEvent(button, QEvent(QEvent.Enter))
    c.check(
        "not even entering brings it back while muted",
        bar.isHidden() is True,
    )

    overlay.set_is_muted(False)
    c.check(
        "unmuting under the pointer brings it straight back", bar.isHidden() is False
    )

    overlay_module.QCursor = away(button)
    overlay.set_is_muted(True)
    overlay.set_is_muted(False)
    c.check(
        "unmuting with the pointer away leaves it hidden",
        bar.isHidden() is True,
    )

    # --- the mute button's own click is unchanged ---

    clicks = []
    button.clicked.connect(lambda: clicks.append(1))

    from PyQt5.QtCore import QPointF
    from PyQt5.QtGui import QMouseEvent

    QApplication.sendEvent(
        button,
        QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(QPoint(5, 5)),
            QPointF(button.mapToGlobal(QPoint(5, 5))),
            overlay_module.Qt.LeftButton,
            overlay_module.Qt.LeftButton,
            overlay_module.Qt.NoModifier,
        ),
    )
    c.check("a left click on it still just mutes", clicks == [1])

finally:
    overlay_module.QCursor = real_cursor

source = (
    Path(__file__).resolve().parent.parent
    / "gridplayer"
    / "widgets"
    / "video_overlay.py"
).read_text(encoding="utf-8")

c.check(
    "the bar is hidden when the overlay is built",
    "self.volume_bar.hide()" in source,
)
c.check(
    "muting no longer pins its visibility by hand",
    "self.volume_bar.setHidden(" not in source,
)
c.check(
    "the overlay filters the events of both controls",
    "self.volume_button.installEventFilter(self)" in source
    and "self.volume_bar.installEventFilter(self)" in source,
)

c.finish()
