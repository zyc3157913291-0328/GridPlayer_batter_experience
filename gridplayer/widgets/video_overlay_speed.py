# MOD: new file - the playback speed control, the gear list and the gesture readout.
"""Overlay widgets for playback speed.

Three pieces, all owned by the overlay:

  * OverlaySpeedButton - shows the current rate as a multiplier and opens the
    gear list.
  * OverlaySpeedPopup - that list: one translucent strip in the overlay's own
    grey, rates from the largest at the top to the smallest at the bottom.
  * OverlaySpeedIndicator - the big readout shown while the hold-and-drag
    gesture is running. It is a top-level window of its own rather than a child
    of the overlay, because the gesture may start in one grid cell and continue
    over another, so the readout has to be able to sit outside any single cell.
"""

from PyQt5.QtCore import QEvent, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics, QGuiApplication, QPainter
from PyQt5.QtWidgets import QWidget

from gridplayer.params.static import OVERLAY_ACTIVITY_EVENT
from gridplayer.utils.speed_gears import GEARS, format_rate, index_for_rate
from gridplayer.widgets.video_overlay_buttons import OverlayButton
from gridplayer.widgets.video_overlay_elements import OverlayWidget


class OverlaySpeedPopup(OverlayWidget):
    """The gear list, drawn rather than handed to QMenu.

    A menu would bring its own frame, its own palette and its own idea of a
    list; the request is for something that reads as part of the overlay - the
    same translucent grey, a single rectangle, and the rates in descending
    order. Being a Qt.Popup still gets Qt's own click-away and Esc dismissal.
    """

    rate_selected = pyqtSignal(float)

    ROW_HEIGHT = 26
    OPACITY = 0.5  # what OverlayBlock puts on itself

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.Popup
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._rate = 1.0
        self._hovered = None

        self.setFixedHeight(self.ROW_HEIGHT * len(GEARS))

    @property
    def rates_top_down(self):
        """Largest first, which is the order the list is drawn in."""
        return list(reversed(GEARS))

    @property
    def rate(self):
        return self._rate

    @rate.setter
    def rate(self, rate):
        # paintEvent reads _rate, so this has to be a real property: a plain
        # attribute of the same name reads back correctly while the list keeps
        # highlighting whatever gear it started on.
        self._rate = rate
        self.update()

    def _row_at(self, pos):
        if not 0 <= pos.y() < self.height():
            return None

        return min(pos.y() // self.ROW_HEIGHT, len(GEARS) - 1)

    def paintEvent(self, event):
        painter = QPainter(self)

        # Exactly how the rest of the overlay paints: the colour every overlay
        # widget is handed, filled square, at the 0.5 opacity OverlayBlock puts
        # on itself, with the text in the computed contrast colour. Painting
        # this window opaquely with a hard-coded alpha made it read as a bright
        # slab next to the control bar it belongs to.
        painter.setOpacity(self.OPACITY)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)
        painter.drawRect(self.rect())

        current = index_for_rate(self._rate)
        font = painter.font()

        for row, gear in enumerate(self.rates_top_down):
            rect = QRect(0, row * self.ROW_HEIGHT, self.width(), self.ROW_HEIGHT)

            if row == self._hovered:
                painter.setBrush(self.color_contrast_mid)
                painter.drawRect(rect)
                painter.setBrush(Qt.NoBrush)

            font.setBold(index_for_rate(gear) == current)
            painter.setFont(font)

            painter.setPen(self.color_contrast)
            painter.drawText(rect, Qt.AlignCenter, format_rate(gear))

    def mouseMoveEvent(self, event):
        row = self._row_at(event.pos())

        if row != self._hovered:
            self._hovered = row
            self.update()

        # Browsing the list counts as activity, or the overlay would pack itself
        # away underneath while the list is still open.
        QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))

        event.ignore()

    def mouseReleaseEvent(self, event):
        row = self._row_at(event.pos())

        if event.button() == Qt.LeftButton and row is not None:
            self.rate_selected.emit(self.rates_top_down[row])

        self.hide()

        event.accept()

    def leaveEvent(self, event):
        self._hovered = None
        self.update()

        event.ignore()

    def show_above(self, anchor_rect):
        """As wide as the anchor - the speed button - and sitting just above it."""
        self.setFixedWidth(anchor_rect.width())
        self.move(anchor_rect.left(), anchor_rect.top() - self.height())

        self.show()
        self.raise_()


class OverlaySpeedButton(OverlayButton):
    """A wide, text-only button, reading 1x, 1.25x or 1.1x."""

    rate_selected = pyqtSignal(float)
    list_requested = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._rate = 1.0

        # The base class squares the button off, so the width has to be re-set
        # after it runs. Measuring the widest label up front keeps the control
        # bar from reflowing as the text changes between 1x and 1.25x.
        self._fixed_width = self._measure_width()
        self.setMinimumWidth(self._fixed_width)
        self.setMaximumSize(self._fixed_width, self.minimumHeight())

        self._update_tooltip()

    def _measure_width(self) -> int:
        metrics = QFontMetrics(self.font())
        widest = max(metrics.horizontalAdvance(format_rate(gear)) for gear in GEARS)

        # Same padding as the other overlay controls, plus room for the fine
        # 1.1x style values the keyboard shortcuts can leave behind.
        return max(widest, metrics.horizontalAdvance(format_rate(12.0))) + self.padding

    def icon(self, rect, painter, color_fg, color_bg):
        painter.setPen(color_fg)
        painter.drawText(rect, Qt.AlignCenter, format_rate(self._rate))

    def icon_off(self, rect, painter, color_fg, color_bg): ...

    def mouseReleaseEvent(self, event):
        """Open the list on release.

        The base class emits clicked on press, which would put the list under
        the cursor while the button is still held - and the release would then
        land on whichever entry happened to be there.
        """
        if event.button() == Qt.LeftButton:
            self.list_requested.emit()
            event.accept()
            return

        event.ignore()

    def mousePressEvent(self, event):
        event.ignore()

    def _update_tooltip(self):
        tip = f"Speed: {format_rate(self._rate)}"

        if index_for_rate(self._rate) is None:
            tip += " (set with the keyboard shortcuts)"

        self.setToolTip(tip)

    @property
    def rate(self) -> float:
        return self._rate

    @rate.setter
    def rate(self, rate):
        self._rate = rate
        self._update_tooltip()
        self.update()


class OverlaySpeedIndicator(QWidget):
    """The readout shown at the top of the video area while the gesture runs."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Own top-level window: the readout is placed at the centre of the whole
        # video area, which is not inside any one grid cell.
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._rate = 1.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(Qt.black)
        painter.setPen(Qt.NoPen)
        painter.setOpacity(0.55)
        painter.drawRoundedRect(self.rect(), 8, 8)

        painter.setOpacity(1.0)
        painter.setPen(Qt.white)
        painter.drawText(self.rect(), Qt.AlignCenter, format_rate(self._rate))

    def _resize_to_text(self):
        metrics = QFontMetrics(self.font())

        self.setFixedSize(
            metrics.horizontalAdvance(format_rate(GEARS[-1])) + 40,
            metrics.height() + 24,
        )

    @property
    def rate(self):
        return self._rate

    @rate.setter
    def rate(self, rate):
        self._rate = rate
        self._resize_to_text()
        self.update()

    def show_at(self, area_rect):
        """Centre horizontally on the video area, one sixth down from its top."""
        self._resize_to_text()

        x = area_rect.left() + (area_rect.width() - self.width()) // 2
        y = area_rect.top() + area_rect.height() // 6

        self.move(x, y)
        self.show()
        self.raise_()
