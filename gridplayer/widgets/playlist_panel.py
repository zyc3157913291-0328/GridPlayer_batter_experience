# MOD: new file - the playlist side panel.
"""MOD: the per-block playlist side panel."""

import datetime
from collections.abc import Sequence
from pathlib import Path

from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.media_folder import SORT_KEYS, sort_entries
from gridplayer.utils.time_txt import get_time_txt

ROLE_PATH = Qt.UserRole + 1
ROLE_META = Qt.UserRole + 2
ROLE_CURRENT = Qt.UserRole + 3
ROLE_KEY = Qt.UserRole + 4

SORT_TITLES = {
    "name": "名称",
    "size": "大小",
    "mtime": "日期",
    "history": "历史",
    "duration": "时长",
}

ROW_HEIGHT = 120
THUMB_BOX_WIDTH = 200  # fixed column, so every filename starts at the same x
THUMB_BOX_HEIGHT = 114  # row height minus 3px top and bottom
THUMB_PAD = 3  # thumbnail touches the box edge minus this
DEFAULT_PANEL_WIDTH = 360
MIN_VIDEO_WIDTH = 160

ACCENT = QColor("#a8a8a8")  # the "now playing" bar: grey, not amber
CURRENT_BG = QColor("#565656")  # grey row, white filename
CURRENT_BADGE = QColor("#6e6e6e")
BADGE_FG = QColor("#ffffff")
HOVER_BG = QColor(255, 255, 255, 22)
NAME_FG = QColor("#ffffff")
META_FG = QColor("#b9c2cc")


def _empty_icon() -> QPixmap:
    """Transparent placeholder so rows without a thumbnail keep a sane layout."""
    pixmap = QPixmap(1, THUMB_BOX_HEIGHT)
    pixmap.fill(Qt.transparent)

    return pixmap


def _wrap_text(text, metrics, width, max_lines=2):
    """Greedy wrap, preferring to break after a separator.

    The final line is elided, so a very long name still shows its tail rather
    than being cut off silently.
    """
    if not text:
        return [""]

    if metrics.horizontalAdvance(text) <= width:
        return [text]

    lines = []
    rest = text

    while rest and len(lines) < max_lines - 1:
        lo, hi = 1, len(rest)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if metrics.horizontalAdvance(rest[:mid]) <= width:
                lo = mid
            else:
                hi = mid - 1

        cut = max(1, lo)
        for sep in (" ", ".", "_", "-", "["):
            pos = rest.rfind(sep, 0, cut)
            if pos > cut // 2:
                cut = pos + 1
                break

        lines.append(rest[:cut])
        rest = rest[cut:]

    if rest:
        lines.append(metrics.elidedText(rest, Qt.ElideRight, width))

    return lines


def show_in_splitter(splitter, panel, width: int) -> None:
    """Give a panel that was inserted while hidden real room in `splitter`.

    QSplitter records the size of each child when it lays out. A child that was
    hidden at insert time is recorded as 0, and calling setVisible(True) later
    does NOT make the splitter hand it any space - the panel ends up "visible"
    with a width of 0, which looks exactly like the toggle doing nothing.
    Setting the sizes explicitly is what actually opens it.
    """
    panel.setVisible(True)

    total = max(splitter.width(), sum(splitter.sizes()))
    if total <= 0:
        total = DEFAULT_PANEL_WIDTH + MIN_VIDEO_WIDTH

    wanted = max(int(width) or DEFAULT_PANEL_WIDTH, panel.minimumWidth())
    wanted = min(wanted, max(panel.minimumWidth(), total - MIN_VIDEO_WIDTH))

    # The panel sits on whichever side it was added to, so hand it the right
    # slot rather than assuming it is first.
    index = splitter.indexOf(panel)
    sizes = [total - wanted, wanted] if index > 0 else [wanted, total - wanted]

    splitter.setSizes(sizes)


def _size_txt(size: int) -> str:
    value = float(size)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024

    return f"{value:.1f} TB"


def _meta_txt(entry: MediaEntry) -> str:
    date = (
        datetime.datetime.fromtimestamp(entry.mtime, tz=datetime.timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d")
    )
    duration = get_time_txt(entry.duration_ms // 1000) if entry.duration_ms else "—"

    return f"{_size_txt(entry.size)} · {date} · {duration}"


class PlaylistItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(0, ROW_HEIGHT)

    def paint(self, painter, option, index):
        painter.save()
        painter.setClipRect(option.rect)

        rect = option.rect
        is_current = bool(index.data(ROLE_CURRENT))

        if is_current:
            painter.fillRect(rect, CURRENT_BG)
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), ACCENT)
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, HOVER_BG)

        # Fixed thumbnail box -> two clean columns, filenames all left-aligned.
        box = QRect(
            rect.left() + THUMB_PAD,
            rect.top() + (rect.height() - THUMB_BOX_HEIGHT) // 2 + THUMB_PAD,
            THUMB_BOX_WIDTH - THUMB_PAD * 2,
            THUMB_BOX_HEIGHT - THUMB_PAD * 2,
        )

        thumb = index.data(Qt.DecorationRole)
        if thumb is not None and not thumb.isNull() and thumb.width() > 0:
            # Fit inside the box keeping the aspect ratio, then draw at the
            # resulting size (a rect target would stretch it) and centre it.
            scaled = thumb.scaled(
                box.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(
                box.x() + (box.width() - scaled.width()) // 2,
                box.y() + (box.height() - scaled.height()) // 2,
                scaled,
            )

        text_left = rect.left() + THUMB_BOX_WIDTH + 8
        avail = max(rect.width() - (text_left - rect.left()) - 10, 40)

        name_font = QFont(option.font)
        name_font.setPixelSize(13)
        painter.setFont(name_font)
        painter.setPen(NAME_FG)

        lines = _wrap_text(
            index.data(Qt.DisplayRole) or "", QFontMetrics(name_font), avail, 2
        )

        text_top = rect.top() + (rect.height() - (len(lines) * 18 + 16)) // 2

        for i, line in enumerate(lines):
            painter.drawText(
                QRect(text_left, text_top + i * 18, avail, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                line,
            )

        meta_font = QFont(option.font)
        meta_font.setPixelSize(10)
        painter.setFont(meta_font)
        painter.setPen(META_FG)
        painter.drawText(
            QRect(text_left, text_top + len(lines) * 18, avail, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            index.data(ROLE_META) or "",
        )

        if is_current:
            badge = "正在播放"
            badge_font = QFont(option.font)
            badge_font.setPixelSize(11)
            painter.setFont(badge_font)
            badge_w = QFontMetrics(badge_font).horizontalAdvance(badge) + 12
            badge_rect = QRect(
                rect.right() - badge_w - 8, rect.bottom() - 22, badge_w, 16
            )

            painter.setPen(Qt.NoPen)
            painter.setBrush(CURRENT_BADGE)
            painter.drawRoundedRect(badge_rect, 8, 8)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(BADGE_FG)
            painter.drawText(badge_rect, Qt.AlignCenter, badge)

        painter.restore()


class PlaylistPanel(QWidget):
    """Lists the media files next to the current video, sortable like a file manager."""

    entry_activated = pyqtSignal(object)  # Path
    sort_changed = pyqtSignal(str, bool)  # key, desc - user-driven only
    entry_play_next = pyqtSignal(object)  # Path
    entry_new_window = pyqtSignal(object)  # Path
    entry_add_to_grid = pyqtSignal(object)  # Path

    def __init__(self, parent=None):
        super().__init__(parent)

        self._entries: list[MediaEntry] = []
        self._history: dict = {}
        self._current: Path | None = None
        self._thumbnails: dict[str, object] = {}

        self._sort_key = "name"
        self._sort_desc = False
        self._suppress_sort_signal = False

        self._sort_buttons: dict[str, QPushButton] = {}

        self._build_ui()

    # --- construction ---

    def _build_ui(self):
        self.setMinimumWidth(200)

        # A stylesheet background on a plain QWidget subclass is not painted when
        # the widget is drawn as a child of something else - the palette colour
        # shows through instead, which on this app's light palette left the
        # folder label and the sort bar above the list as a pale strip while the
        # list itself stayed dark. WA_StyledBackground is what makes Qt paint the
        # styled background, and autoFillBackground has to go, or the two fight.
        #
        # Note this only shows up when the panel is grabbed from a parent; a grab
        # of the panel on its own takes a different path and looks correct, which
        # is why the offscreen renders missed it for so long.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(False)

        # The panel is deliberately dark so it matches the video overlay, and so
        # the painted row colours below are predictable instead of depending on
        # whatever palette the host application happens to use.
        self.setStyleSheet(
            """
            PlaylistPanel { background: #232323; }
            QLabel { color: #d8d8d8; }
            QPushButton {
                color: #c8c8c8; background: transparent;
                border: none; padding: 2px 5px;
            }
            QPushButton:hover { color: #ffffff; }
            QListWidget { background: #232323; border: none; }
            QScrollBar:vertical { background: #232323; width: 10px; }
            QScrollBar::handle:vertical { background: #4a4a4a; border-radius: 5px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.folder_label = QLabel(self)
        self.folder_label.setContentsMargins(10, 8, 10, 4)
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self.folder_label)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 4)
        header.setSpacing(2)

        for key in SORT_KEYS:
            btn = QPushButton(SORT_TITLES[key], self)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _=False, k=key: self.apply_sort(*self._next_sort(k))
            )
            header.addWidget(btn)
            self._sort_buttons[key] = btn

        header.addStretch()
        outer.addLayout(header)

        self._list = QListWidget(self)
        self._list.setItemDelegate(PlaylistItemDelegate(self._list))
        self._list.setUniformItemSizes(True)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setMouseTracking(True)
        self._list.setFrameShape(QListWidget.NoFrame)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        outer.addWidget(self._list, 1)

        self._refresh_sort_buttons()

    # --- public api ---

    @property
    def sort_key(self) -> str:
        return self._sort_key

    @property
    def sort_desc(self) -> bool:
        return self._sort_desc

    def set_history(self, history: dict):
        self._history = dict(history)
        self._rebuild()

    def set_entries(self, entries: Sequence[MediaEntry], current: Path | None):
        self._entries = list(entries)
        self._current = current
        self._rebuild()

    def set_current(self, current: Path | None):
        """Move the 'now playing' marker without re-scanning the folder."""
        self._current = current
        self._rebuild()

    def count(self) -> int:
        return self._list.count()

    def item(self, row: int) -> QListWidgetItem:
        return self._list.item(row)

    def entry_duration(self, entry_key: str) -> int | None:
        for e in self._entries:
            if e.key == entry_key:
                return e.duration_ms

        return None

    def set_thumbnail(self, entry_key: str, image):
        """Apply a shell thumbnail that arrived from the worker thread.

        Takes a QImage (thread-safe) and converts here, on the GUI thread.
        """
        pixmap = QPixmap.fromImage(image) if image is not None else None
        self._thumbnails[entry_key] = pixmap

        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(ROLE_KEY) == entry_key:
                item.setData(
                    Qt.DecorationRole,
                    pixmap if pixmap is not None else _empty_icon(),
                )
                break

    def update_duration(self, entry_key: str, duration_ms: int | None):
        changed = False

        for i, e in enumerate(self._entries):
            if e.key == entry_key and e.duration_ms != duration_ms:
                self._entries[i] = e.with_duration(duration_ms)
                changed = True

        if changed:
            self._rebuild()

    def activate_row(self, row: int):
        item = self._list.item(row)
        if item is None:
            return

        self.entry_activated.emit(item.data(ROLE_PATH))

    def set_sort(self, key: str, desc: bool):
        """Programmatic: adopt a stored sorting without notifying anyone."""
        self._suppress_sort_signal = True
        try:
            self.apply_sort(key, desc)
        finally:
            self._suppress_sort_signal = False

    def apply_sort(self, key: str, desc: bool):
        """User-driven (a column header was clicked)."""
        self._sort_key = key if key in SORT_KEYS else "name"
        self._sort_desc = bool(desc)

        self._refresh_sort_buttons()
        self._rebuild()

        if not self._suppress_sort_signal:
            self.sort_changed.emit(self._sort_key, self._sort_desc)

    def _next_sort(self, key: str):
        if key == self._sort_key:
            return key, not self._sort_desc

        return key, False

    # --- internals ---

    def _refresh_sort_buttons(self):
        for key, btn in self._sort_buttons.items():
            if key == self._sort_key:
                btn.setText(SORT_TITLES[key] + (" ↓" if self._sort_desc else " ↑"))
                btn.setStyleSheet("font-weight: bold;")
            else:
                btn.setText(SORT_TITLES[key])
                btn.setStyleSheet("")

    def _rebuild(self):
        self._list.clear()

        ordered = sort_entries(
            self._entries, self._sort_key, self._sort_desc, self._history
        )
        current_key = str(self._current).casefold() if self._current else None

        for e in ordered:
            item = QListWidgetItem(e.name)
            item.setData(ROLE_PATH, e.path)
            item.setData(ROLE_KEY, e.key)
            item.setData(ROLE_META, _meta_txt(e))
            item.setData(ROLE_CURRENT, e.key == current_key)

            thumb = self._thumbnails.get(e.key)
            item.setData(
                Qt.DecorationRole, thumb if thumb is not None else _empty_icon()
            )

            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._list.addItem(item)

        if self._current is None:
            self.folder_label.setText("")
        else:
            self.folder_label.setText(str(Path(self._current).parent))

    def _on_item_clicked(self, item: QListWidgetItem):
        self.entry_activated.emit(item.data(ROLE_PATH))

    def _show_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if item is None:
            return

        path = item.data(ROLE_PATH)

        menu = QMenu(self)
        menu.addAction(self.tr("下一个播放"), lambda: self.entry_play_next.emit(path))
        menu.addAction(
            self.tr("在新窗口中播放"), lambda: self.entry_new_window.emit(path)
        )
        menu.addAction(
            self.tr("在网格中添加播放"), lambda: self.entry_add_to_grid.emit(path)
        )
        menu.exec_(self._list.viewport().mapToGlobal(pos))
