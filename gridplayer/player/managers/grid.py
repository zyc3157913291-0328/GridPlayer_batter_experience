import contextlib
import math
from typing import NamedTuple

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput
from gridplayer.models.grid_state import GridState
from gridplayer.params.static import (
    FONT_SIZE_BIG_INFO,
    PLAYER_INITIAL_SIZE,
    PLAYER_MIN_VIDEO_SIZE,
    GridMode,
)
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate


class GridDimensions(NamedTuple):
    cols: int
    rows: int

    @property
    def max_size(self):
        return self.cols * self.rows


def _clear_layout(layout):
    for _ in range(layout.count()):
        l_item = layout.takeAt(0)

        sublay = l_item.layout()

        if sublay is not None:
            _clear_layout(sublay)
            sublay.deleteLater()


class GridManager(ManagerBase):
    minimum_size_changed = pyqtSignal(QSize)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.grid_state = self.grid_state

        self._grid_mode = Settings().get("playlist/grid_mode")
        self._is_grid_fit = Settings().get("playlist/grid_fit")
        self._grid_size = Settings().get("playlist/grid_size")

        self._default_minimum_size = QSize(*PLAYER_INITIAL_SIZE)
        self._minimum_video_size = QSize(*PLAYER_MIN_VIDEO_SIZE)
        self._minimum_size = self._default_minimum_size

        # MOD: the grid gets its own host widget so a side panel can share the
        # window (a QWidget can only carry one layout, and this one used to sit
        # directly on the Player). PlaylistPanelManager inserts itself at index 0
        # of the splitter; grid_host must always stay the last item.
        self._grid_host = QWidget(self.parent())
        self._splitter = QSplitter(Qt.Horizontal, self.parent())
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setContentsMargins(0, 0, 0, 0)
        self._splitter.setHandleWidth(3)
        self._splitter.addWidget(self._grid_host)

        # The splitter is a child widget, so the window still needs a layout to
        # make it fill the window - moving the grid layout out of the Player
        # left it with none.
        self._outer = QHBoxLayout(self.parent())
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)
        self._outer.addWidget(self._splitter)

        self._ctx.grid_host = self._grid_host
        self._ctx.layout_splitter = self._splitter

        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(0)
        self._grid.setContentsMargins(0, 0, 0, 0)

        self._info_label = QLabel(
            translate("Main Window", "Drag and drop media files or URLs here"),
            parent=self._grid_host,
        )
        self._info_label.setAlignment(Qt.AlignCenter)
        self._info_label.setWordWrap(True)
        self._info_label.setMargin(20)
        font = QFont("Hack", FONT_SIZE_BIG_INFO, QFont.Bold)
        self._info_label.setFont(font)

    def init(self):
        self.minimum_size_changed.emit(self._minimum_size)
        self.reload_video_grid()

    @property
    def commands(self):
        return {
            "set_grid_mode": self.cmd_set_grid_mode,
            "is_grid_mode_set_to": lambda m: self._grid_mode == m,
            "ask_grid_size": self.cmd_ask_grid_size,
            "get_grid_size": self.cmd_get_grid_size,
            "switch_is_grid_fit": self.cmd_switch_is_grid_fit,
            "is_grid_fit": lambda: self._is_grid_fit,
            # MOD: single_mode needs to rebuild the grid once it has shown the
            # blocks it was hiding - see SingleModeManager.set_video_count
            "reload_video_grid": self.reload_video_grid,
        }

    @property
    def visible_count(self):
        # Visible (already present) or not explicitly hidden
        # to exclude hidden (e.g. during single mode)
        # and include new blocks that are not yet visible
        return sum(
            w.isVisible() or not w.testAttribute(Qt.WA_WState_ExplicitShowHide)
            for w in self._ctx.video_blocks
        )

    @property
    def grid_dimensions(self):
        if self.visible_count <= 1:
            return GridDimensions(1, 1)

        if self._grid_size == 0:
            grid_size = math.ceil(math.sqrt(self.visible_count))
        else:
            grid_size = self._grid_size

        grid_slices = math.ceil(self.visible_count / grid_size)

        if self._grid_mode == GridMode.AUTO_COLS:
            cols, rows = grid_slices, grid_size
        else:
            cols, rows = grid_size, grid_slices

        return GridDimensions(cols, rows)

    @contextlib.contextmanager
    def slow_ui_operation(self):
        self.parent().setUpdatesEnabled(False)
        yield
        self.parent().setUpdatesEnabled(True)

    def grid_state(self):
        return GridState(
            mode=self._grid_mode,
            is_fit=self._is_grid_fit,
            size=self._grid_size,
        )

    def set_grid_state(self, state: GridState) -> None:
        self._grid_mode = state.mode
        self._is_grid_fit = state.is_fit
        self._grid_size = state.size

        self.reload_video_grid()

    def cmd_set_grid_mode(self, mode):
        if self._grid_mode == mode:
            return

        self._grid_mode = mode
        self.reload_video_grid()

    def cmd_ask_grid_size(self):
        size = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=translate("Dialog - Set grid size", "Set grid size", "Header"),
            special_text=translate("Grid Size", "Auto"),
            initial_value=self._grid_size,
            _min=0,
            _max=1000,
        )

        if self._grid_size == size:
            return

        self._grid_size = size
        self.reload_video_grid()

    def cmd_get_grid_size(self):
        if self._grid_size == 0:
            return translate("Grid Size", "Auto")

        return str(self._grid_size)

    def cmd_switch_is_grid_fit(self):
        self._is_grid_fit = not self._is_grid_fit
        self.reload_video_grid()

    def adapt_grid(self):
        self._reset_grid_stretch()

        if self.visible_count > 1:
            self._adjust_grid_stretch()

    def reload_video_grid(self):
        with self.slow_ui_operation():
            self._reset_video_grid()

            if not self._ctx.video_blocks:
                self._grid.activate()
                return

            self._adjust_window()
            self._adjust_cells()

            self._populate_grid()

            self.adapt_grid()

            self._grid.activate()

    def _reset_grid_stretch(self):
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)

        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)

    def _adjust_grid_stretch(self):
        for c in range(self.grid_dimensions.cols):
            self._grid.setColumnStretch(c, 1)

        for r in range(self.grid_dimensions.rows):
            self._grid.setRowStretch(r, 1)

    def _reset_video_grid(self):
        self._info_label.hide()

        _clear_layout(self._grid)

        if not self._ctx.video_blocks:
            self._grid.addWidget(self._info_label, 0, 0)
            self._info_label.show()

            self.adapt_grid()

    def _adjust_window(self):
        width = self.grid_dimensions.cols * self._minimum_video_size.width()
        height = self.grid_dimensions.rows * self._minimum_video_size.height()

        width = max(width, self._default_minimum_size.width())
        height = max(height, self._default_minimum_size.height())

        # MOD: any extra widget in the splitter (the playlist panel today) takes
        # width away from the video area, so the window minimum has to grow by
        # whatever it reserves. Scanned by identity rather than by index so the
        # panel can live on either side, and isHidden() rather than isVisible():
        # a widget that has never been shown reports isVisible() == False, which
        # would ignore a panel that is merely not on screen yet.
        extra = sum(
            self._splitter.widget(i).minimumWidth()
            for i in range(self._splitter.count())
            if self._splitter.widget(i) is not self._grid_host
            and not self._splitter.widget(i).isHidden()
        )
        width += extra

        self._minimum_size = QSize(width, height)
        self.minimum_size_changed.emit(self._minimum_size)

    def _adjust_cells(self):
        for vb in self._ctx.video_blocks:
            vb.setMinimumSize(self._minimum_vb_size())

    def _populate_grid(self):
        odd_cells = self.grid_dimensions.max_size - len(self._ctx.video_blocks)

        if odd_cells == 0 or not self._is_grid_fit:
            self._fill_grid(self._ctx.video_blocks)
        else:
            if self._grid_mode == GridMode.AUTO_COLS:
                straight_cells = self.grid_dimensions.rows * (
                    self.grid_dimensions.cols - 1
                )

                self._fill_grid(self._ctx.video_blocks[:straight_cells])
                self._fill_last_col(self._ctx.video_blocks[straight_cells:])
            else:
                straight_cells = self.grid_dimensions.cols * (
                    self.grid_dimensions.rows - 1
                )

                self._fill_grid(self._ctx.video_blocks[:straight_cells])
                self._fill_last_row(self._ctx.video_blocks[straight_cells:])

    def _fill_grid(self, widgets):
        if self._grid_mode == GridMode.AUTO_COLS:
            grid = (
                (col, row)
                for col in range(self.grid_dimensions.cols)
                for row in range(self.grid_dimensions.rows)
            )
        else:
            grid = (
                (col, row)
                for row in range(self.grid_dimensions.rows)
                for col in range(self.grid_dimensions.cols)
            )

        for (col, row), w in zip(grid, widgets):
            self._grid.addWidget(w, row, col, 1, 1)

    def _fill_last_row(self, widgets):
        last_row = QHBoxLayout()

        for w in widgets:
            last_row.addWidget(w, 1)

        last_row_num = self.grid_dimensions.rows - 1

        self._grid.addLayout(last_row, last_row_num, 0, 1, -1)

    def _fill_last_col(self, widgets):
        last_row = QVBoxLayout()

        for w in widgets:
            last_row.addWidget(w, 1)

        last_col_num = self.grid_dimensions.cols - 1

        self._grid.addLayout(last_row, 0, last_col_num, -1, 1)

    def _minimum_vb_size(self):
        return QSize(
            self._minimum_size.width() // self.grid_dimensions.cols,
            self._minimum_size.height() // self.grid_dimensions.rows,
        )
