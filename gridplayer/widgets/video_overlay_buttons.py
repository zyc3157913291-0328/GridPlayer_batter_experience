from abc import ABC, abstractmethod

from PyQt5.QtCore import QPropertyAnimation, Qt, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QPainter
from PyQt5.QtWidgets import qApp

from gridplayer.params.static import VideoRepeat, next_video_repeat
from gridplayer.utils.qt import QABC
from gridplayer.widgets.video_overlay_elements import OverlayWidget
from gridplayer.widgets.video_overlay_icons import (
    draw_cross,
    draw_menu,
    draw_pause,
    draw_play,
    draw_repeat_list,
    draw_repeat_pause,
    draw_repeat_shuffle,
    draw_repeat_single,
    draw_spin_circle,
    draw_volume_off,
    draw_volume_on,
)


class OverlayButton(OverlayWidget, metaclass=QABC):
    clicked = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMouseTracking(True)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumSize(self.minimumWidth(), self.minimumHeight())

        self._is_off = False

    @abstractmethod
    def icon(self, rect, painter, color_fg, color_bg): ...

    @abstractmethod
    def icon_off(self, rect, painter, color_fg, color_bg): ...

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.underMouse():
            color_bg = self.color_contrast_mid
            color_fg = self.color
        else:
            color_bg = self.color
            color_fg = self.color_contrast_mid

        painter.fillRect(self.rect(), color_bg)

        self.draw_icon(painter, color_fg, color_bg)

    def draw_icon(self, painter: QPainter, color_fg: QColor, color_bg: QColor):
        if self._is_off:
            self.icon_off(self.rect(), painter, color_fg, color_bg)
        else:
            self.icon(self.rect(), painter, color_fg, color_bg)

    def underMouse(self):
        return qApp.widgetAt(QCursor.pos()) is self

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        """Consume to avoid parent event"""

        if event.button() == Qt.LeftButton:
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

        event.ignore()

    def mouseDoubleClickEvent(self, event):
        """Consume to avoid parent event"""
        self.mousePressEvent(event)

        event.accept()

    @property
    def is_off(self):
        return self._is_off

    @is_off.setter
    def is_off(self, is_off):
        self._is_off = is_off
        self.update()


class OverlayButtonDynamic(OverlayButton, ABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._is_in_progress = False
        self._icon_spin = 0

        self._animation = QPropertyAnimation(self, b"icon_spin")
        self._animation.setDuration(500)
        self._animation.setStartValue(0)
        self._animation.setEndValue(360)
        self._animation.setLoopCount(-1)

    @pyqtProperty(int)
    def icon_spin(self):
        return self._icon_spin

    @icon_spin.setter
    def icon_spin(self, icon_spin):
        self._icon_spin = icon_spin
        self.update()

    def draw_icon(self, painter, color_fg, color_bg):
        if self._is_in_progress:
            draw_spin_circle(self.rect(), painter, color_fg, color_bg, self._icon_spin)
        else:
            super().draw_icon(painter, color_fg, color_bg)

    @property
    def is_in_progress(self):
        return self._is_in_progress

    @is_in_progress.setter
    def is_in_progress(self, is_in_progress):
        self._is_in_progress = is_in_progress

        if is_in_progress:
            self._animation.start()
        else:
            self._animation.stop()

        self.update()

    @OverlayButton.is_off.setter
    def is_off(self, is_off):
        self.is_in_progress = False

        OverlayButton.is_off.fset(self, is_off)


class OverlayExitButton(OverlayButton):
    def icon(self, rect, painter, color_fg, color_bg):
        return draw_cross(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg): ...


class OverlayPlayPauseButton(OverlayButtonDynamic):
    def icon(self, rect, painter, color_fg, color_bg):
        return draw_play(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg):
        return draw_pause(rect, painter, color_fg, color_bg)


class OverlayVolumeButton(OverlayButton):
    def icon(self, rect, painter, color_fg, color_bg):
        return draw_volume_on(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg):
        return draw_volume_off(rect, painter, color_fg, color_bg)


# --- MOD: repeat-mode button and playlist-panel toggle -----------------------

REPEAT_MODE_TITLES = {
    VideoRepeat.DIR: "列表循环",
    VideoRepeat.SINGLE_FILE: "单集循环",
    VideoRepeat.DIR_SHUFFLE: "随机播放",
    VideoRepeat.PAUSE_AT_END: "播完暂停",
}


class OverlayRepeatButton(OverlayButton):
    """Cycles this block's play order.

    Self-contained: a click advances the mode and announces it. VideoBlock only
    has to write the new value back onto video_params.
    """

    repeat_mode_changed = pyqtSignal(object)

    _ICONS = {
        VideoRepeat.SINGLE_FILE: draw_repeat_single,
        VideoRepeat.DIR: draw_repeat_list,
        VideoRepeat.DIR_SHUFFLE: draw_repeat_shuffle,
        VideoRepeat.PAUSE_AT_END: draw_repeat_pause,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._repeat_mode = VideoRepeat.DIR
        self.setToolTip(REPEAT_MODE_TITLES[self._repeat_mode])

        self.clicked.connect(self._advance)

    def _advance(self):
        self.repeat_mode = next_video_repeat(self._repeat_mode)

        self.repeat_mode_changed.emit(self._repeat_mode)

    @property
    def repeat_mode(self):
        return self._repeat_mode

    @repeat_mode.setter
    def repeat_mode(self, mode):
        self._repeat_mode = mode
        self.setToolTip(REPEAT_MODE_TITLES.get(mode, str(mode)))
        self.update()

    def icon(self, rect, painter, color_fg, color_bg):
        draw = self._ICONS.get(self._repeat_mode, draw_repeat_list)

        return draw(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg): ...


class OverlayPlaylistButton(OverlayButton):
    """Hamburger that toggles the playlist side panel."""

    def icon(self, rect, painter, color_fg, color_bg):
        return draw_menu(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg):
        return draw_menu(rect, painter, color_fg, color_bg)
