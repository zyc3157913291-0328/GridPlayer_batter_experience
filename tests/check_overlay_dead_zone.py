"""MOD: the bottom control row belongs to the overlay, not to the video.

The overlay sits on top of the video and hands on anything it does not use. A
click that gets through lands on the video block, where a release pauses it, a
double click fills the screen and a right click opens the menu. Between and
around the buttons the overlay has nothing of its own, so a click there used to
behave as if it were bare video - clicking next to the controls paused the
video, which reads as a bug when you were aiming at the controls.

The overlay cannot swallow those clicks itself. In the default configuration it
is a translucent window, and Windows hands a click that lands on a fully
transparent pixel straight to the window underneath - the overlay would never
see it. So the overlay only answers "is this position inside my control row?"
and the video block decides what a click there means. The wheel is deliberately
not part of that: scrolling still seeks.

Run: pyenv\\Scripts\\python.exe tests\\check_overlay_dead_zone.py
"""

import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("overlay dead zone")

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent, QWheelEvent
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_overlay import (
    PROPAGATED_EVENTS,
    OverlayBlock,
    OverlayBlockFloating,
)

MARGIN = 2  # a couple of pixels either side of a boundary

REPO = Path(__file__).resolve().parent.parent
OVERLAY_SOURCE = REPO / "gridplayer" / "widgets" / "video_overlay.py"
BLOCK_SOURCE = REPO / "gridplayer" / "widgets" / "video_block.py"


class RecordingParent(QWidget):
    """Stands in for the video block: only counts what reaches it."""

    def __init__(self):
        super().__init__()

        self.seen = []

        # the real block keeps hover working, and Qt only delivers a move with
        # no buttons held to a widget that asked for tracking
        self.setMouseTracking(True)

    def event(self, event):
        self.seen.append(event.type())

        return super().event(event)

    def clear(self):
        self.seen.clear()


class FakeMouseEvent:
    """Just the bits the block's guards touch, so no window is needed."""

    def __init__(self, global_pos, button=Qt.LeftButton):
        self._pos = global_pos
        self._button = button
        self._accepted = True

    def globalPos(self):
        return self._pos

    def button(self):
        return self._button

    def accept(self):
        self._accepted = True

    def ignore(self):
        self._accepted = False

    def isAccepted(self):
        return self._accepted


class TimerStub:
    def __init__(self):
        self.starts = 0

    def start(self, _ms):
        self.starts += 1

    def stop(self):
        pass


class BlockStub:
    """A video block with nothing but what the click guards read."""

    def __init__(self, overlay):
        self.overlay = overlay

        self.is_video_initialized = True
        self._speed_drag = None
        self._long_press_timer = TimerStub()
        self._ctx = SimpleNamespace(is_disable_click_pause=False)

        self.paused = 0

    def _is_over_overlay_controls(self, global_pos):
        return VideoBlock._is_over_overlay_controls(self, global_pos)

    def play_pause(self):
        self.paused += 1


def shown(widget):
    """Lay the widget out without putting a window on screen."""
    widget.setAttribute(Qt.WA_DontShowOnScreen, True)
    widget.show()
    QApplication.processEvents()

    return widget


def real_mouse(kind, global_y, button=Qt.LeftButton, buttons=Qt.LeftButton):
    """A real event, for the overlay's own event() forwarding."""
    return QMouseEvent(
        kind, QPointF(20, 10), QPointF(20, global_y), button, buttons, Qt.NoModifier
    )


def real_wheel(global_y):
    return QWheelEvent(
        QPointF(20, 10),
        QPointF(20, global_y),
        QPoint(),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )


def gy(overlay, y):
    """Global y for a point y pixels down the overlay itself."""
    return overlay.mapToGlobal(QPoint(20, y)).y()


def gx(overlay, x, y):
    """Global position of a point inside the overlay."""
    return overlay.mapToGlobal(QPoint(x, y))


def row_top(overlay):
    """How far down the overlay the control row starts."""
    top = overlay.bottom_bar.geometry().top()

    return overlay.control_widget.mapTo(overlay, QPoint(0, top)).y()


def method_source(path, name):
    """The body of one method, so a call can be looked for in it alone."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^(\s*)def {name}\(", text, re.MULTILINE)

    if match is None:
        return ""

    indent = match.group(1)
    body = text[match.end() :]
    end = re.search(rf"^{indent}def ", body, re.MULTILINE)

    return body if end is None else body[: end.start()]


# --- the overlay's answer: where its control row is --------------------------

recorder = shown(RecordingParent())
recorder.resize(640, 400)

floating = shown(OverlayBlockFloating(recorder))
floating.resize(640, 400)

top = row_top(floating)

c.check(
    "the floating overlay laid out (the control row has a height)",
    floating.progress_bar.height() > 0 and 0 < top < floating.height(),
    f"bar={floating.progress_bar.height()}px row top at y={top} "
    f"overlay={floating.height()}px",
)

bar_slot = (
    floating.progress_bar
    if floating.progress_bar.isVisible()
    else floating.progress_bar_placeholder
)
slot_top = bar_slot.mapTo(floating, QPoint(0, 0)).y()
c.check(
    "the row starts at or above whatever fills the progress bar slot",
    top <= slot_top,
    f"row top={top} slot top={slot_top} slot={bar_slot.__class__.__name__} "
    f"height={bar_slot.height()}px",
)

button_center = floating.play_pause_button.mapToGlobal(
    floating.play_pause_button.rect().center()
)
c.check(
    "a point on a button is inside the control row",
    floating.is_in_dead_zone(button_center),
    f"y={button_center.y()} row top={top}",
)

c.check(
    "the gaps between the buttons are inside the row too",
    floating.is_in_dead_zone(gx(floating, 1, top + MARGIN))
    and floating.is_in_dead_zone(gx(floating, floating.width() - 1, top + MARGIN)),
    f"row top={top} width={floating.width()}",
)

c.check(
    "the pixel above the row is still video",
    not floating.is_in_dead_zone(gx(floating, 20, top - 1)),
    f"y={top - 1}",
)

c.check(
    "the row carries on to the bottom of the overlay",
    floating.is_in_dead_zone(gx(floating, 20, top + MARGIN))
    and floating.is_in_dead_zone(gx(floating, 20, floating.height() - 1)),
    f"bottom={floating.height() - 1} of {floating.height()}",
)

c.check(
    "the video body above the controls is not the row",
    not floating.is_in_dead_zone(gx(floating, 20, floating.height() // 4)),
    f"y={floating.height() // 4}",
)

c.check(
    "a position outside the overlay is never the row",
    not floating.is_in_dead_zone(gx(floating, 20, floating.height() + 50)),
    f"y={floating.height() + 50}",
)

recorder.clear()
QApplication.sendEvent(
    floating, real_mouse(QEvent.MouseButtonRelease, gy(floating, top + MARGIN))
)
c.check(
    "the overlay still forwards whatever it does not use",
    recorder.seen == [QEvent.MouseButtonRelease],
    f"{[str(e) for e in recorder.seen]} - the block does the swallowing",
)

recorder.clear()
QApplication.sendEvent(
    floating,
    real_mouse(
        QEvent.MouseMove,
        gy(floating, top + MARGIN),
        button=Qt.NoButton,
        buttons=Qt.NoButton,
    ),
)
c.check(
    "moving the mouse through the row is still passed on (controls stay up)",
    recorder.seen == [QEvent.MouseMove],
    f"{[str(e) for e in recorder.seen]}",
)

recorder.clear()
QApplication.sendEvent(floating, real_wheel(gy(floating, top + MARGIN)))
c.check(
    "the wheel in the row still seeks, as before",
    recorder.seen == [QEvent.Wheel],
    f"{[str(e) for e in recorder.seen]}",
)

hidden = shown(OverlayBlockFloating(recorder))
hidden.resize(640, 400)
hidden_top = row_top(hidden)
in_row = gx(hidden, 20, hidden_top + MARGIN)

hidden.hide()
c.check(
    "a hidden overlay has no control row at all",
    not hidden.is_in_dead_zone(in_row),
    f"hidden -> {hidden.is_in_dead_zone(in_row)}",
)

shown(hidden)
c.check(
    "showing it again brings the row back",
    hidden.is_in_dead_zone(in_row),
    f"shown -> {hidden.is_in_dead_zone(in_row)}",
)

hidden.hide()


# --- the block's answer: what a click in the row means -----------------------

block = BlockStub(floating)

release = FakeMouseEvent(gx(floating, 20, top + MARGIN))
VideoBlock.mouseReleaseEvent(block, release)
c.check(
    "a release in the control row does not pause the video",
    block.paused == 0 and release.isAccepted(),
    f"paused={block.paused} accepted={release.isAccepted()}",
)

release = FakeMouseEvent(gx(floating, 20, floating.height() // 4))
VideoBlock.mouseReleaseEvent(block, release)
c.check(
    "a release on the video still pauses it",
    block.paused == 1,
    f"paused={block.paused}",
)

press = FakeMouseEvent(gx(floating, 20, top + MARGIN))
VideoBlock.mousePressEvent(block, press)
c.check(
    "a press in the control row is swallowed and arms nothing",
    press.isAccepted() and block._long_press_timer.starts == 0,
    f"accepted={press.isAccepted()} timer starts={block._long_press_timer.starts}",
)

dblclick = FakeMouseEvent(gx(floating, 20, top + MARGIN))
VideoBlock.mouseDoubleClickEvent(block, dblclick)
c.check(
    "a double click in the control row does not fill the screen",
    dblclick.isAccepted(),
    f"accepted={dblclick.isAccepted()}",
)

menu = FakeMouseEvent(gx(floating, 20, top + MARGIN))
VideoBlock.contextMenuEvent(block, menu)
c.check(
    "a right click in the control row does not open the video menu",
    menu.isAccepted(),
    f"accepted={menu.isAccepted()}",
)


# --- the child-widget overlay answers the same question ----------------------

plain = shown(OverlayBlock(recorder))
plain.resize(640, 400)
plain_top = row_top(plain)

c.check(
    "the child-widget overlay laid out too",
    plain.progress_bar.height() > 0 and 0 < plain_top < plain.height(),
    f"bar={plain.progress_bar.height()}px row top at y={plain_top} "
    f"overlay={plain.height()}px",
)

c.check(
    "the child-widget overlay finds the same boundary",
    not plain.is_in_dead_zone(gx(plain, 20, plain_top - 1))
    and plain.is_in_dead_zone(gx(plain, 20, plain_top + MARGIN)),
    f"row top={plain_top}",
)

plain.hide()

narrow = shown(OverlayBlock(recorder))
narrow.resize(120, 400)
narrow.progress_bar.hide()
narrow.progress_bar_placeholder.show()
QApplication.processEvents()

narrow_top = row_top(narrow)

c.check(
    "narrow cell: the boundary is the row's, whatever holds the bar slot",
    not narrow.is_in_dead_zone(gx(narrow, 20, narrow_top - 1))
    and narrow.is_in_dead_zone(gx(narrow, 20, narrow_top + MARGIN)),
    f"row top={narrow_top} bar visible={narrow.progress_bar.isVisible()}",
)

narrow.hide()
floating.hide()


# --- the split of responsibility, read off the sources -----------------------

overlay_text = OVERLAY_SOURCE.read_text(encoding="utf-8")

c.check(
    "the overlay no longer swallows clicks itself",
    "DEAD_ZONE_EVENTS" not in overlay_text
    and "is_in_dead_zone" not in method_source(OVERLAY_SOURCE, "event"),
    "the block decides, the overlay only answers",
)

for name in (
    "mousePressEvent",
    "mouseReleaseEvent",
    "mouseDoubleClickEvent",
    "contextMenuEvent",
):
    c.check(
        f"the block asks the overlay in {name}",
        "_is_over_overlay_controls" in method_source(BLOCK_SOURCE, name),
        f"guard calls found: "
        f"{method_source(BLOCK_SOURCE, name).count('_is_over_overlay_controls')}",
    )

c.check(
    "the wheel is deliberately not shielded - scrolling still seeks",
    "_is_over_overlay_controls" not in method_source(BLOCK_SOURCE, "wheelEvent")
    and QEvent.Wheel in PROPAGATED_EVENTS,
    "wheelEvent untouched, wheel still forwarded by the overlay",
)

c.check(
    "the guard is asked once, through one helper",
    BLOCK_SOURCE.read_text(encoding="utf-8").count("def _is_over_overlay_controls") == 1
    and BLOCK_SOURCE.read_text(encoding="utf-8").count("is_in_dead_zone") == 1,
    "one helper, one delegate",
)

c.finish()
