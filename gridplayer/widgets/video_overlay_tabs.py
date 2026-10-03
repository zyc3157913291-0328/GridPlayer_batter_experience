"""MOD: tab strip shown while one video fills the screen.

Two looks, switchable at runtime by right clicking the video name bar:

"bar"
    A plain row of tabs sitting above the name bar. Every tab carries its
    filename; the tab of the video on screen is painted in the accent colour
    (plus a left stripe) so it still reads as "you are here".

"merged"
    Browser style. The name bar runs the full width and the tab of the video on
    screen grows straight out of it - a trapezoid in the same colour, so the two
    melt into one shape - while the other tabs sit behind it, shorter and
    darker, like bookmarks. That tab therefore carries no filename: the name is
    already on the bar it is growing out of.

Either way, clicking a tab brings that video to the screen and the small x on a
tab closes that video and drops it out of the grid.
"""

from PyQt5.QtCore import QEvent, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QCursor,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt5.QtWidgets import QHBoxLayout, QMenu, QSizePolicy, QWidget, qApp

from gridplayer.params.static import OVERLAY_ACTIVITY_EVENT
from gridplayer.settings import Settings
from gridplayer.widgets.video_overlay_elements import OverlayLabel, OverlayWidget

STYLE_BAR = "bar"
STYLE_MERGED = "merged"

STYLES = (STYLE_BAR, STYLE_MERGED)

STYLE_TITLES = {
    STYLE_BAR: "分离式标签栏",
    STYLE_MERGED: "融合式标签栏",
}


def tab_style_setting():
    style = Settings().get("misc/tab_style")

    return style if style in STYLES else STYLE_BAR


# height of the tab of the video on screen, height of the others, gap between
# tabs, gap left between the strip and the name bar below it, and how far the
# sides of a merged tab slope in
STYLE_METRICS = {
    STYLE_BAR: {
        "height": 24,
        "inactive_height": 24,
        "spacing": 4,
        "bottom_gap": 6,
        "slant": 0,
    },
    STYLE_MERGED: {
        "height": 26,
        "inactive_height": 20,
        "spacing": 0,
        "bottom_gap": 0,
        "slant": 10,
    },
}


class OverlayTab(OverlayWidget):
    activated = pyqtSignal(str)
    close_clicked = pyqtSignal(str)

    min_width = 46
    max_width = 220
    close_zone = 22
    close_mark_size = 5

    def __init__(self, block_id, label, is_current, style, **kwargs):
        super().__init__(**kwargs)

        self.block_id = block_id
        self.is_current = is_current
        self.style = style if style in STYLES else STYLE_BAR

        metrics = STYLE_METRICS[self.style]

        # in merged style the tab of the video on screen is the name bar growing
        # upwards, so repeating the name inside it would just double it up
        self._label = "" if (is_current and self.style == STYLE_MERGED) else label

        self._is_close_hovered = False

        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumWidth(self.min_width + 2 * self.slant)
        self.setMaximumWidth(self.max_width + 2 * self.slant)
        self.setFixedHeight(
            metrics["height"] if is_current else metrics["inactive_height"]
        )

        self.setToolTip(label)

    # -- geometry -------------------------------------------------------------

    @property
    def slant(self):
        return STYLE_METRICS[self.style]["slant"]

    def sizeHint(self):
        text_width = 0
        if self._label:
            text_width = QFontMetrics(self.font()).size(0, self._label).width()

        width = text_width + self.close_zone + self.padding * 2 + 2 * self.slant

        return QSize(
            max(self.minimumWidth(), min(width, self.maximumWidth())),
            self.height(),
        )

    def close_rect(self):
        size = self.close_zone
        right = self.width() - 1 - self.slant // 2

        return QRect(right - size + 1, (self.height() - size) // 2, size, size)

    def text_rect(self):
        left = self.padding // 2 + self.slant
        width = max(self.width() - self.close_zone - left - self.slant, 10)

        return QRect(left, 0, width, self.height())

    def is_in_close_zone(self, pos):
        return self.close_rect().contains(pos)

    def shape(self):
        """Trapezoid outline used by the merged style; the bottom edge is flush
        with the widget so it lines up with the name bar underneath."""

        rect = self.rect()
        slant = self.slant

        path = QPainterPath()

        path.moveTo(rect.left() + slant, rect.top())
        path.lineTo(rect.right() + 1 - slant, rect.top())
        path.lineTo(rect.right() + 1, rect.bottom() + 1)
        path.lineTo(rect.left(), rect.bottom() + 1)
        path.closeSubpath()

        return path

    # -- painting -------------------------------------------------------------

    @property
    def color_hover(self):
        """A shade lighter than the mid grey, for hovering an inactive tab."""

        return QColor.fromHsl(
            self.color.hue(),
            self.color.saturation(),
            max(self.color.lightness() - 55, 0),
        )

    def colors(self):
        if self.style == STYLE_MERGED:
            if self.is_current:
                return self.color, self.color_contrast
            if self.underMouse():
                return self.color_hover, self.color_contrast
            return self.color_contrast_mid, self.color

        if self.is_current or self.underMouse():
            return self.color_contrast_mid, self.color

        return self.color, self.color_contrast

    def paintEvent(self, event):
        painter = QPainter(self)

        color_bg, color_fg = self.colors()

        if self.style == STYLE_MERGED:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.fillPath(self.shape(), color_bg)
        else:
            painter.fillRect(self.rect(), color_bg)

        if self.is_current and self.style == STYLE_BAR:
            # left accent stripe: this is the video on screen right now
            accent = QRect(self.rect())
            accent.setWidth(3)

            painter.fillRect(accent, self.color)

        if self._label:
            self.draw_label(painter, color_fg)

        self.draw_close(painter, color_fg)

    def draw_label(self, painter, color_fg):
        text_rect = self.text_rect()

        label = QFontMetrics(self.font()).elidedText(
            self._label, Qt.ElideMiddle, text_rect.width()
        )

        painter.setPen(color_fg)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

    def draw_close(self, painter, color_fg):
        close = self.close_rect()

        if self._is_close_hovered:
            painter.fillRect(close, self.color_contrast)
            pen_color = self.color
        else:
            pen_color = color_fg

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(pen_color, 2))

        center = close.center()
        size = self.close_mark_size

        painter.drawLine(
            center.x() - size, center.y() - size, center.x() + size, center.y() + size
        )
        painter.drawLine(
            center.x() + size, center.y() - size, center.x() - size, center.y() + size
        )

    # -- interaction ----------------------------------------------------------

    def underMouse(self):
        """Floating overlays are separate top level windows, so QWidget's own
        underMouse() is not reliable there - same workaround as OverlayButton."""

        return qApp.widgetAt(QCursor.pos()) is self

    def enterEvent(self, event):
        self.update()

        event.ignore()

    def leaveEvent(self, event):
        self._is_close_hovered = False
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        is_close_hovered = self.is_in_close_zone(event.pos())

        if is_close_hovered != self._is_close_hovered:
            self._is_close_hovered = is_close_hovered
            self.update()

        # ignore, so the block still sees the movement and keeps the controls
        # on screen instead of letting the hide timer run out
        event.ignore()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        # consume, so a click on a tab does not reach the video block, where it
        # would toggle playback
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        event.accept()

        if self.is_in_close_zone(event.pos()):
            self.close_clicked.emit(self.block_id)
        else:
            self.activated.emit(self.block_id)

    def mouseDoubleClickEvent(self, event):
        """Consume, so double clicking a tab does not reach the block and
        trigger fullscreen / zoom."""

        event.accept()


class OverlayTabBar(QWidget):
    tab_activated = pyqtSignal(str)
    tab_closed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)

        self._layout.addStretch()

        self._tabs = []

        self._tabs_data = None
        self._current_id = None
        self._style = None

    def set_tabs(self, tabs, current_id, style=None):
        """tabs is a list of (block_id, label); current_id is the block that
        fills the screen, or None when the strip should not be shown at all."""

        if style is None:
            style = tab_style_setting()

        if style not in STYLES:
            style = STYLE_BAR

        if (tabs, current_id, style) == (
            self._tabs_data,
            self._current_id,
            self._style,
        ):
            return

        self._tabs_data = list(tabs)
        self._current_id = current_id
        self._style = style

        metrics = STYLE_METRICS[style]

        self._layout.setSpacing(metrics["spacing"])
        self._layout.setContentsMargins(0, 0, 0, metrics["bottom_gap"])

        self.clear()

        for block_id, label in tabs:
            tab = OverlayTab(
                block_id=block_id,
                label=label,
                is_current=block_id == current_id,
                style=style,
                parent=self,
            )

            tab.activated.connect(self.tab_activated.emit)
            tab.close_clicked.connect(self.tab_closed.emit)

            # inserted before the trailing stretch, so the tabs stay left
            # aligned and only grow into however much room there is
            self._layout.insertWidget(len(self._tabs), tab)
            # taller tabs grow upwards, keeping every bottom edge on the same line
            self._layout.setAlignment(tab, Qt.AlignBottom)

            self._tabs.append(tab)

        current = self.current_tab()
        if current is not None:
            current.raise_()

        self.setVisible(current_id is not None)

    def clear(self):
        for tab in self._tabs:
            self._layout.removeWidget(tab)

            # detach before deleting, so the dead tab stops showing up in
            # findChildren() - the floating overlay walks that list to build its
            # mask - and cannot linger as a hidden child until deleteLater runs
            tab.hide()
            tab.setParent(None)
            tab.deleteLater()

        self._tabs = []

    def current_tab(self):
        return next((t for t in self._tabs if t.is_current), None)

    @property
    def tabs(self):
        return list(self._tabs)

    @property
    def style(self):
        return self._style


class OverlayTabStyleLabel(OverlayLabel):
    """The big video name bar, which doubles as the tab style switch.

    OverlayLabel is transparent to the mouse so the video underneath keeps
    receiving everything. This one has to see the right click, so it takes mouse
    events and passes all of them straight back on - except the context menu,
    which it answers itself instead of letting the video's own menu open.
    """

    tab_style_selected = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        self._menu = None

    def mousePressEvent(self, event):
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        event.ignore()

    def contextMenuEvent(self, event):
        menu = self._menu_for_current_style()

        menu.popup(event.globalPos())

        # and keep the controls on screen while the menu is up, otherwise the
        # strip that is about to change disappears from under the menu
        QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))

        event.accept()

    def _menu_for_current_style(self):
        """One menu, rebuilt each time: a fresh QMenu per right click would pile
        up as children of this label."""

        if self._menu is None:
            self._menu = QMenu(self)
            self._menu.triggered.connect(self._on_menu_triggered)

        self._menu.clear()

        current_style = tab_style_setting()

        for style in STYLES:
            action = self._menu.addAction(STYLE_TITLES[style])
            action.setCheckable(True)
            action.setChecked(style == current_style)
            action.setData(style)

        return self._menu

    def _on_menu_triggered(self, action):
        style = action.data()

        QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))

        if style is not None:
            self.tab_style_selected.emit(style)
