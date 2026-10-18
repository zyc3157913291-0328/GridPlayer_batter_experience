from PyQt5.QtCore import QEvent, QPoint, QRect, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QCursor, QGuiApplication, QPalette, QRegion
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
    qApp,
)

from gridplayer.params.static import OVERLAY_ACTIVITY_EVENT
from gridplayer.settings import Settings
from gridplayer.utils.qt import qt_connect
from gridplayer.utils.time_txt import get_time_txt
from gridplayer.widgets.video_overlay_buttons import (
    OverlayButton,
    OverlayExitButton,
    OverlayPlaylistButton,
    OverlayPlayPauseButton,
    OverlayRepeatButton,
    OverlayVolumeButton,
)
from gridplayer.widgets.video_overlay_elements import (
    OverlayBar,
    OverlayBorder,
    OverlayProgressBar,
    OverlayShortLabel,
    OverlayShortLabelFloating,
    OverlayVolumeBar,
    OverlayWidget,
)
from gridplayer.widgets.video_overlay_speed import (  # MOD
    HOVER_CHECK_MS,
    OverlaySpeedButton,
    OverlaySpeedIndicator,
    OverlaySpeedPopup,
)
from gridplayer.widgets.video_overlay_tabs import (  # MOD
    OverlayTabBar,
    OverlayTabStyleLabel,
)

PROPAGATED_EVENTS = (
    QEvent.MouseButtonRelease,
    QEvent.MouseButtonPress,
    QEvent.MouseMove,
    QEvent.MouseButtonDblClick,
    QEvent.Wheel,
    QEvent.ContextMenu,
    QEvent.DragEnter,
    # MOD: so the block can hide the controls the moment the pointer leaves the
    # video, instead of waiting for the hide timer to run out.
    QEvent.Leave,
)

PROPAGATED_EVENTS_FILTERED = (
    QEvent.DragMove,
    QEvent.DragLeave,
    QEvent.Drop,
)

# MOD: how long the volume bar stays up after the pointer has left the mute
# button, so that it can be reached.
VOLUME_HOVER_GRACE_MS = 150

# MOD: the length of the horizontal volume bar in the control row.
VOLUME_ROW_BAR_WIDTH = 100


class OverlayBlock(QWidget):
    set_vid_pos = pyqtSignal(float)
    set_volume = pyqtSignal(float)

    exit_clicked = pyqtSignal()
    play_pause_clicked = pyqtSignal()
    mute_unmute_clicked = pyqtSignal()
    # MOD
    repeat_mode_changed = pyqtSignal(object)
    speed_selected = pyqtSignal(float)
    playlist_clicked = pyqtSignal()
    tab_activated = pyqtSignal(str)
    tab_closed = pyqtSignal(str)
    tab_style_changed = pyqtSignal(str)

    # MOD: the same five controls again, meant for every video. Emitted when
    # the control was used with Control held or with the right button.
    set_vid_pos_global = pyqtSignal(float)
    set_volume_global = pyqtSignal(float)
    mute_unmute_clicked_global = pyqtSignal()
    repeat_mode_changed_global = pyqtSignal(object)
    speed_selected_global = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

        self._set_opacity(0.5)

        self.ui_setup()

        self.ui_customize_dynamic()

        self.ui_connect()

    def ui_customize_dynamic(self):
        self.label_info_hide_timer = QTimer()
        self.label_info_hide_timer.setSingleShot(True)
        self.label_info_hide_timer.timeout.connect(self.label_info.hide)

        # MOD: an open gear list closes itself once the pointer is no longer on
        # the button or on the list. See close_speed_list_when_unhovered().
        # Owned by the overlay: a closing video takes the overlay down with it,
        # and a timer left running would then tick on a deleted widget.
        self.speed_list_hover_timer = QTimer(self)
        self.speed_list_hover_timer.setInterval(HOVER_CHECK_MS)
        self.speed_list_hover_timer.timeout.connect(
            self.close_speed_list_when_unhovered
        )

        self.label_info.hide()
        self.floating_progress.hide()

        self.label_progress.hide()
        self.progress_bar.hide()
        self.progress_bar_placeholder.show()

        # MOD: the volume bar shows while the pointer is on the mute button or
        # on the bar itself. Leaving one starts a short grace period rather than
        # hiding straight away, so crossing the small gap between the two - or
        # stepping over the bar's edge - does not blink it out.
        self.volume_bar_hover_timer = QTimer(self)
        self.volume_bar_hover_timer.setSingleShot(True)
        self.volume_bar_hover_timer.setInterval(VOLUME_HOVER_GRACE_MS)
        self.volume_bar_hover_timer.timeout.connect(self.update_volume_bar_visibility)

        self.volume_button.installEventFilter(self)
        self.volume_bar.installEventFilter(self)

        self.volume_bar.hide()

        # MOD: the other volume look - a mute button and a horizontal bar that
        # stay in the control row, immediately left of the progress bar. Both
        # looks are always built; apply_volume_style() decides which one shows.
        self.volume_button_row = OverlayVolumeButton(parent=self)
        self.volume_bar_row = OverlayProgressBar(parent=self)
        self.volume_bar_row.setFixedWidth(VOLUME_ROW_BAR_WIDTH)

        row_index = self.bottom_bar.indexOf(self.progress_bar)
        self.bottom_bar.insertWidget(row_index, self.volume_button_row)
        self.bottom_bar.insertWidget(row_index + 1, self.volume_bar_row)

        self.is_volume_in_row = Settings().get("misc/volume_in_progress_row")
        self.apply_volume_style()

    def ui_connect(self):
        qt_connect(
            (self.progress_bar.mouse_over, self.floating_progress.on_mouse_over),
            (self.progress_bar.mouse_left, self.floating_progress.on_mouse_left),
            (self.exit_button.clicked, self.exit),
            (self.play_pause_button.clicked, self.play_pause),
            (self.progress_bar.position_changed, self.emit_position),
            (self.volume_button.clicked, self.mute_unmute),
            (self.volume_bar.position_changed, self.emit_volume_position),
            # MOD: the repeat button announces its own mode changes
            (self.repeat_button.repeat_mode_changed, self.repeat_mode_changed.emit),
            # MOD: and the speed control opens its gear list, whose entries come
            # back out as the same "a rate was picked" signal
            (self.speed_button.list_requested, self.show_speed_list),
            (self.speed_popup.rate_selected, self.speed_selected.emit),
            # MOD: the same controls, when the gesture asked for every video
            (self.progress_bar.position_changed_global, self.emit_position_global),
            (self.volume_bar.position_changed_global, self.emit_volume_position_global),
            (self.volume_button.global_requested, self.mute_unmute_global),
            (self.volume_button_row.clicked, self.mute_unmute),
            (self.volume_button_row.global_requested, self.mute_unmute_global),
            (self.volume_bar_row.position_changed, self.emit_volume_position),
            (
                self.volume_bar_row.position_changed_global,
                self.emit_volume_position_global,
            ),
            (
                self.repeat_button.repeat_mode_changed_global,
                self.repeat_mode_changed_global.emit,
            ),
            (self.speed_popup.rate_selected_global, self.speed_selected_global.emit),
            (self.speed_button.rate_selected_global, self.speed_selected_global.emit),
            (self.playlist_button.clicked, self.playlist_toggle),
        )

    def ui_setup(self):
        layout_main = QStackedLayout(self)

        layout_main.setContentsMargins(0, 0, 0, 0)
        layout_main.setStackingMode(QStackedLayout.StackAll)

        self.control_widget = QWidget(self)
        self.control_widget.setMouseTracking(True)

        self.border_widget = OverlayBorder(parent=self)
        self.border_widget.hide()

        layout_control = QVBoxLayout(self.control_widget)
        layout_control.setContentsMargins(10, 10, 10, 10)

        layout_main.addWidget(self.control_widget)
        layout_main.addWidget(self.border_widget)

        self.top_bar = QVBoxLayout()
        # MOD: no gap between the tab strip and the name bar, so a merged tab
        # can grow straight out of that bar. The strip carries its own bottom
        # margin instead, which is what separates them in the plain style.
        self.top_bar.setSpacing(0)
        self.middle = QHBoxLayout()
        self.bottom_bar = QHBoxLayout()

        layout_control.addLayout(self.top_bar)
        layout_control.addLayout(self.middle, 1)
        layout_control.addLayout(self.bottom_bar)

        self.label_text = OverlayTabStyleLabel(parent=self)  # MOD
        self.exit_button = OverlayExitButton(parent=self)

        # MOD: right clicking the name bar switches the tab strip look
        self.label_text.tab_style_selected.connect(self.tab_style_changed.emit)

        self.title_bar = QHBoxLayout()
        self.title_bar.addWidget(self.label_text, 1)
        self.title_bar.addWidget(self.exit_button)

        self.label_info = OverlayShortLabel(parent=self)

        self.info_bar = QHBoxLayout()
        self.info_bar.addWidget(self.label_info)
        self.info_bar.addStretch()

        # MOD: tab strip, shown only while one video fills the screen. It sits
        # above the title bar, i.e. above the big bar that already carries the
        # name of the video on screen.
        self.tab_bar = OverlayTabBar(parent=self)
        self.tab_bar.tab_activated.connect(self.tab_activated.emit)
        self.tab_bar.tab_closed.connect(self.tab_closed.emit)
        self.tab_bar.hide()

        self.top_bar.addWidget(self.tab_bar)  # MOD
        self.top_bar.addLayout(self.title_bar)
        self.top_bar.addLayout(self.info_bar)

        self.right_bar = QVBoxLayout()

        self.middle.addStretch()
        self.middle.addLayout(self.right_bar)

        self.volume_bar = OverlayVolumeBar(parent=self)

        self.right_bar.addStretch()
        self.right_bar.addWidget(self.volume_bar, 1)

        self.play_pause_button = OverlayPlayPauseButton(parent=self)
        self.label_progress = OverlayShortLabel(parent=self)
        self.progress_bar = OverlayProgressBar(parent=self)
        self.progress_bar_placeholder = QWidget(parent=self)
        self.repeat_button = OverlayRepeatButton(parent=self)  # MOD
        # MOD: the speed control sits between the progress bar and the rest of
        # the right-hand controls, i.e. closest to the bar.
        self.speed_button = OverlaySpeedButton(parent=self)
        self.speed_popup = OverlaySpeedPopup(parent=self)
        self.speed_indicator = OverlaySpeedIndicator(parent=self.parent())
        self.playlist_button = OverlayPlaylistButton(parent=self)  # MOD
        self.volume_button = OverlayVolumeButton(parent=self)

        self.bottom_bar.addWidget(self.play_pause_button)
        self.bottom_bar.addWidget(self.label_progress)
        self.bottom_bar.addWidget(self.progress_bar, 1)
        self.bottom_bar.addWidget(self.speed_button)  # MOD
        self.bottom_bar.addWidget(self.progress_bar_placeholder, 1)
        self.bottom_bar.addWidget(self.repeat_button)  # MOD
        self.bottom_bar.addWidget(self.playlist_button)  # MOD
        self.bottom_bar.addWidget(self.volume_button)

        self.floating_progress = OverlayShortLabelFloating(parent=self)

    def customEvent(self, event):
        if event.type() == OVERLAY_ACTIVITY_EVENT:
            QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))

    def resizeEvent(self, event):
        too_narrow_to_fit = 250
        is_wide = event.size().width() > too_narrow_to_fit

        self.label_progress.setVisible(is_wide or not self.progress_bar.isEnabled())

    @pyqtSlot(int, int)
    def set_position(self, position, length):
        position = max(0, position)

        if length <= 0:
            position_txt = get_time_txt(position // 1000)

            self.floating_progress.hide()

            self.progress_bar.setEnabled(False)
            self.progress_bar.hide()

            self.progress_bar_placeholder.show()

            self.label_progress.text = f"{position_txt}"
            self.label_progress.show()

            return

        position_percent = position / length
        position_txt = get_time_txt(position // 1000, length // 1000)
        length_txt = get_time_txt(length // 1000)

        self.progress_bar.setEnabled(True)
        self.progress_bar.show()

        self.progress_bar_placeholder.hide()

        self.floating_progress.length = length
        self.label_progress.text = f"{position_txt} / {length_txt}"
        self.progress_bar.position = position_percent

    @pyqtSlot(float)
    def set_loop_start(self, position):
        self.progress_bar.loop_start = position

    @pyqtSlot(float)
    def set_loop_end(self, position):
        self.progress_bar.loop_end = position

    @pyqtSlot(str)
    def set_label(self, label):
        self.label_text.label = label

    @pyqtSlot(str)
    def set_color(self, color):
        for widget in self.findChildren(OverlayWidget):
            widget.color = color

        # MOD: the gear strip is a window rather than a child, so findChildren
        # does not reach it and it would otherwise keep the default white.
        self.speed_popup.color = color

    @pyqtSlot(str)
    def set_info_label(self, info_text):
        self.label_info.text = info_text
        self.label_info.show()
        self.label_info_hide_timer.start(1000 * 2)

    @pyqtSlot()
    def set_is_in_progress(self):
        self.play_pause_button.is_in_progress = True

    @pyqtSlot(bool)
    def set_is_paused(self, is_paused):
        self.play_pause_button.is_off = not is_paused

    @pyqtSlot(bool)
    def set_is_muted(self, is_muted):
        self.volume_button.is_off = is_muted
        # MOD: the row look carries its own mute button, and only one of the
        # two is on screen, so both are kept in step.
        self.volume_button_row.is_off = is_muted

        # MOD: the bar is hover-driven now, so muting only takes the hovered
        # state into account instead of pinning it hidden or visible.
        self.update_volume_bar_visibility()

    @pyqtSlot(float)
    def set_volume_position(self, position):
        self.volume_bar.position = position
        self.volume_bar_row.position = position

    def eventFilter(self, obj, event):
        """MOD: the mute button and the volume bar behave as one hover target."""
        if obj is self.volume_button or obj is self.volume_bar:
            if event.type() == QEvent.Enter:
                self.volume_bar_hover_timer.stop()
                self.update_volume_bar_visibility()
            elif event.type() == QEvent.Leave:
                self.volume_bar_hover_timer.start()

        return super().eventFilter(obj, event)

    def update_volume_bar_visibility(self):
        """MOD: shows the edge volume bar while the pointer is on either control.

        A muted video keeps it hidden, the same way it used to: the bar is the
        level control, and there is no level to show while muted. When the row
        look is on, this bar is not used at all.
        """
        if self.is_volume_in_row:
            self.volume_bar.setVisible(False)
            return

        is_hovered = self._is_within(
            self.volume_button, QCursor.pos()
        ) or self._is_within(self.volume_bar, QCursor.pos())

        self.volume_bar.setVisible(is_hovered and not self.volume_button.is_off)

    def apply_volume_style(self):
        """MOD: shows whichever of the two volume looks Settings asks for."""
        self.volume_button_row.setVisible(self.is_volume_in_row)
        self.volume_bar_row.setVisible(self.is_volume_in_row)

        self.volume_button.setVisible(not self.is_volume_in_row)

        self.update_volume_bar_visibility()

    def sync_volume_style(self):
        """MOD: picks up a change of the volume look without reopening the video.

        The controls are shown on every mouse move over the video, so asking
        again there is enough to make the switch take effect right away.
        """
        is_in_row = Settings().get("misc/volume_in_progress_row")

        if is_in_row == self.is_volume_in_row:
            return

        self.is_volume_in_row = is_in_row
        self.apply_volume_style()

    def showEvent(self, event):
        self.sync_volume_style()

        super().showEvent(event)

    @pyqtSlot()
    def exit(self):
        self.exit_clicked.emit()

    @pyqtSlot()
    def play_pause(self):
        self.play_pause_clicked.emit()

    @pyqtSlot()
    def mute_unmute(self):
        self.mute_unmute_clicked.emit()

    @pyqtSlot(float)
    def emit_position(self, position):
        self.set_vid_pos.emit(position)

    @pyqtSlot(float)
    def emit_volume_position(self, position):
        self.set_volume.emit(position)

    @pyqtSlot(float)
    def emit_position_global(self, position):
        self.set_vid_pos_global.emit(position)

    @pyqtSlot(float)
    def emit_volume_position_global(self, position):
        self.set_volume_global.emit(position)

    @pyqtSlot()
    def mute_unmute_global(self):
        self.mute_unmute_clicked_global.emit()

    @pyqtSlot(bool)
    def set_is_active(self, is_active):
        self.border_widget.setVisible(is_active)

    @pyqtSlot(bool)
    def set_volume_button_visible(self, is_visible):
        # MOD: either the row look's mute button or the original one is the
        # one on screen, so each follows its own style as well.
        self.volume_button.setVisible(is_visible and not self.is_volume_in_row)
        self.volume_button_row.setVisible(is_visible and self.is_volume_in_row)

    # MOD
    @pyqtSlot(object)
    def set_repeat_mode(self, mode):
        self.repeat_button.repeat_mode = mode

    # MOD
    def set_rate(self, rate):
        self.speed_button.rate = rate
        self.speed_popup.rate = rate

    # MOD
    def show_speed_list(self):
        """Open the gear list directly above the speed button.

        As wide as that button, not as wide as the overlay: stretching it across
        the whole cell made it a slab covering the picture.
        """
        anchor = QRect(
            self.speed_button.mapToGlobal(QPoint(0, 0)),
            self.speed_button.size(),
        )

        self.speed_popup.show_above(anchor)
        self.speed_list_hover_timer.start()

    # MOD
    @staticmethod
    def _is_within(widget, global_pos) -> bool:
        return widget.rect().contains(widget.mapFromGlobal(global_pos))

    # MOD
    def is_over_speed_list(self, global_pos) -> bool:
        """Is this position on the speed button, or on the gear list itself?

        The two belong together: the list opens directly above the button and
        is exactly as wide, so moving from one to the other never crosses a
        gap that belongs to neither.
        """
        return self._is_within(self.speed_button, global_pos) or self._is_within(
            self.speed_popup, global_pos
        )

    # MOD
    def close_speed_list_when_unhovered(self):
        """Close the gear list once the pointer is on neither of the two.

        Picking a gear and clicking away both still close it; this only adds
        the case the list used to leave open, where the pointer simply wanders
        off and the list sits there until something else dismisses it.
        """
        if not self.speed_popup.isVisible():
            self.speed_list_hover_timer.stop()
            return

        if self.is_over_speed_list(QCursor.pos()):
            return

        self.speed_popup.hide()
        self.speed_list_hover_timer.stop()

    # MOD
    def is_over_control(self, global_pos) -> bool:
        """Is one of the interactive controls under this global position?

        The overlay forwards its mouse events to the video block, so a press on
        a control reaches the block too - and would arm the hold-and-drag speed
        gesture. Holding the speed button to browse its list, or holding the
        progress bar to seek, then doubled the speed of the video underneath.
        Ask the window manager what is really under the cursor instead of trying
        to reason about the forwarding.
        """
        widget = qApp.widgetAt(global_pos)

        while widget is not None and widget is not self:
            if isinstance(widget, (OverlayButton, OverlayBar)):
                return True

            widget = widget.parent()

        return False

    # MOD
    def is_in_dead_zone(self, global_pos) -> bool:
        """Is this position inside the bottom control row?

        The row and the margin under it read as part of the controls, yet a
        click there used to reach the video underneath and pause it - or fill
        the screen, on a double click. The row spans the video, and so does the
        overlay, so the width needs no test: only the row's top edge has to be
        found, and the layout knows it.

        The overlay only answers the question. What a click there means is the
        video block's call, because a translucent overlay window never sees a
        click that lands on its transparent pixels - Windows hands it straight
        to whatever is underneath.
        """
        if not self.isVisible():
            return False

        # a hidden overlay is parked outside the screen, so an unrelated
        # position must not be measured against its geometry
        if not self.rect().contains(self.mapFromGlobal(global_pos)):
            return False

        row_top = self.bottom_bar.geometry().top()

        return global_pos.y() >= self.control_widget.mapToGlobal(QPoint(0, row_top)).y()

    @pyqtSlot()
    def playlist_toggle(self):
        self.playlist_clicked.emit()

    @pyqtSlot(bool)
    def set_playlist_panel_visible(self, is_visible):
        self.playlist_button.is_off = is_visible

    # MOD
    def set_tabs(self, tabs, current_id):
        self.tab_bar.set_tabs(tabs, current_id)

    def _set_opacity(self, opacity):
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(opacity)
        self.setGraphicsEffect(effect)


class OverlayBlockFloating(OverlayBlock):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ensure_black_text()

        self.init_flags()

        if Settings().get("internal/opaque_hw_overlay"):
            self.make_opaque()
        else:
            self.is_opaque = False

        self.parent().window().installEventFilter(self)

    def ensure_black_text(self):
        """Some window managers make text look gray when window is out of focus"""

        pal = self.palette()
        col = pal.color(QPalette.Active, QPalette.ButtonText)
        pal.setColor(QPalette.Inactive, QPalette.Text, col)
        self.setPalette(pal)

    def init_flags(self):
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Prevent from shooting up on top of other windows on show()
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Allow window to move beyond screen edge
        self.setAttribute(Qt.WA_X11NetWmWindowTypeDesktop)

        # Don't allow overlay to receive focus
        self.setAttribute(Qt.WA_X11DoNotAcceptFocus)

        # Drag and drop doesn't get through floating overlay
        # need to redirect drag events to Player window
        self.setAcceptDrops(True)

        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )

    def make_opaque(self):
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.setGraphicsEffect(None)

        self.floating_progress.is_opaque = True
        self.is_opaque = True

    def setGeometry(self, rect):
        new_pos = self.parent().mapToGlobal(QPoint())
        rect.moveTopLeft(new_pos)

        self.setFixedSize(rect.size())

        super().setGeometry(rect)

    def moveEvent(self, event):
        self.move_to_parent()

        event.accept()

    def paintEvent(self, event):
        if self.is_opaque:
            # 0 coord to keep children from sliding off
            mask = QRegion(QRect(0, 0, 1, 1))

            for child in self.findChildren(OverlayWidget):
                if child.isVisible():
                    # MOD: an overlay widget is not necessarily a direct child
                    # of this overlay - the tabs live inside the tab bar - so
                    # its geometry has to be mapped up rather than read as if
                    # it were already overlay relative. For a direct child this
                    # is exactly child.pos(), so nothing else changes.
                    offset = child.mapTo(self, QPoint(0, 0))

                    if child.mask():
                        mask += child.mask().translated(offset)
                    else:
                        mask += QRegion(QRect(offset, child.size()))

            if not self.border_widget.isVisible():
                mask -= QRegion(QRect(0, 0, 1, 1))

            self.setMask(mask)

    def move_to_parent(self):
        new_pos = self.parent().mapToGlobal(QPoint())

        if new_pos != self.pos():
            self.move(new_pos)

    def eventFilter(self, event_object, event) -> bool:
        """Track parent window move events and follow it"""

        if event_object == self.parent().window():
            if event.type() == QEvent.Move:
                QApplication.sendEvent(self, event)
            if event.type() == QEvent.LayoutRequest:
                self.move_to_parent()
        if event_object == self.parent() and event.type() == QEvent.Hide:
            self.hide()

        return super().eventFilter(event_object, event)

    def event(self, event):
        """Events are not propagated for independent windows (like this one),
        so have to do it manually to emulate regular child widget behaviour.

        https://stackoverflow.com/a/3184510/13100286
        https://forum.qt.io/post/352629

        Also drag events create recursion, so they are filtered separately"""

        if event.type() in PROPAGATED_EVENTS:
            QApplication.sendEvent(self.parent(), event)
        elif event.type() in PROPAGATED_EVENTS_FILTERED:
            self.parent().window().filter_event(event)

        return super().event(event)


class OverlayFakeInvisible(OverlayBlockFloating):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_visible = False

    def show(self):
        if not self.isVisible():
            self.setVisible(True)

        self._is_visible = True

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.update()

    def hide(self):
        if not self.isVisible():
            self.setVisible(True)

        self._is_visible = False

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.update()

    def move_beyond_screen(self):
        self.move(QPoint(-self.width(), -self.height()))

    def move_to_parent(self):
        if not self._is_visible:
            return self.move_beyond_screen()

        super().move_to_parent()

    def paintEvent(self, event):
        if not self._is_visible and self.windowOpacity() != 0:
            self.move_beyond_screen()
            self.setMask(QRegion(0, 0, 1, 1))
            self.setWindowOpacity(0)
            return

        if self.windowOpacity() == 0:
            self.clearMask()
            self.setWindowOpacity(1)

        super().paintEvent(event)
