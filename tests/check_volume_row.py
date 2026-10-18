"""MOD: the switchable volume looks - edge bar versus the control row.

Upstream puts a vertical volume bar against the right edge of every video and
a mute button at the end of the control row. The alternative keeps a mute
button and a horizontal bar in that row instead, immediately left of the
progress bar, where the level is always in sight. Which one is on screen is
picked by misc/volume_in_progress_row; only one is ever built into the layout
at a time, so the two never fight over the same edge of the picture.

Run: pyenv\\Scripts\\python.exe tests\\check_volume_row.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("volume row style")

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QWidget

from gridplayer.settings import Settings
from gridplayer.widgets.video_overlay import VOLUME_ROW_BAR_WIDTH, OverlayBlock


class Recorder:
    """Stands in for a signal and for a slot, so a connection can be watched."""

    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)

    def __call__(self, *args):
        self.calls.append(args)


class CursorStub:
    def __init__(self, pos):
        self._pos = pos

    def pos(self):
        return self._pos


from gridplayer.widgets import video_overlay as overlay_module

window = QWidget()

# --- the default: the original edge look -----------------------------------

Settings().reset("misc/volume_in_progress_row")
c.check(
    "the volume look is a setting, and it defaults to the edge bar",
    Settings().get("misc/volume_in_progress_row") is False,
)

edge_overlay = OverlayBlock(window)

c.check(
    "the edge look keeps the mute button at the end of the control row",
    edge_overlay.volume_button.isHidden() is False,
)
c.check(
    "and leaves the row look out of the layout",
    edge_overlay.volume_button_row.isHidden() is True
    and edge_overlay.volume_bar_row.isHidden() is True,
)
c.check(
    "the edge bar itself is still hover-driven",
    edge_overlay.volume_bar.isHidden() is True,
)

# --- the alternative: the row look -----------------------------------------

Settings().set("misc/volume_in_progress_row", True)

row_overlay = OverlayBlock(window)

c.check(
    "the row look shows its mute button",
    row_overlay.volume_button_row.isHidden() is False,
)
c.check(
    "and its bar, always rather than on hover",
    row_overlay.volume_bar_row.isHidden() is False,
)
c.check(
    "while the original mute button is not on screen",
    row_overlay.volume_button.isHidden() is True,
)
c.check(
    "and neither is the edge bar",
    row_overlay.volume_bar.isHidden() is True,
)

real_cursor = overlay_module.QCursor
try:
    overlay_module.QCursor = CursorStub(
        row_overlay.volume_button.mapToGlobal(QPoint(5, 5))
    )
    row_overlay.update_volume_bar_visibility()

    c.check(
        "hovering where the edge button used to be cannot bring the edge bar back",
        row_overlay.volume_bar.isHidden() is True,
    )
    c.check(
        "and the row bar stays up regardless",
        row_overlay.volume_bar_row.isHidden() is False,
    )
finally:
    overlay_module.QCursor = real_cursor

# --- the row bar is a fixed strip immediately left of the progress bar -----

row = row_overlay.bottom_bar

c.check(
    f"the row bar is {VOLUME_ROW_BAR_WIDTH}px wide",
    row_overlay.volume_bar_row.width() == VOLUME_ROW_BAR_WIDTH,
)
c.check(
    "the row mute button sits directly left of the row bar",
    row.indexOf(row_overlay.volume_button_row) + 1
    == row.indexOf(row_overlay.volume_bar_row),
)
c.check(
    "and the bar sits directly left of the progress bar",
    row.indexOf(row_overlay.volume_bar_row) + 1
    == row.indexOf(row_overlay.progress_bar),
)

# --- both looks are kept in step, since either can be the one on screen -----

row_overlay.set_volume_position(0.4)

c.check(
    "a volume position reaches the row bar",
    row_overlay.volume_bar_row.position == 0.4,
)
c.check(
    "and the edge bar as well",
    row_overlay.volume_bar.position == 0.4,
)

row_overlay.set_is_muted(True)

c.check(
    "muting reaches the row mute button",
    row_overlay.volume_button_row.is_off is True,
)
c.check(
    "and the original one",
    row_overlay.volume_button.is_off is True,
)

row_overlay.set_is_muted(False)

# --- hiding the volume controls for a silent video -------------------------

row_overlay.set_volume_button_visible(False)

c.check(
    "hiding the volume controls hides the row mute button",
    row_overlay.volume_button_row.isHidden() is True,
)

row_overlay.set_volume_button_visible(True)

c.check(
    "and showing them brings it back",
    row_overlay.volume_button_row.isHidden() is False,
)
c.check(
    "without resurrecting the original button",
    row_overlay.volume_button.isHidden() is True,
)

edge_overlay.set_volume_button_visible(False)

c.check(
    "the same call still hides the original button in the edge look",
    edge_overlay.volume_button.isHidden() is True,
)
c.check(
    "and leaves the row look's button out of it",
    edge_overlay.volume_button_row.isHidden() is True,
)

# --- what the row controls drive -------------------------------------------

set_volume = Recorder()
set_volume_global = Recorder()
mute = Recorder()
mute_global = Recorder()

row_overlay.set_volume.connect(set_volume)
row_overlay.set_volume_global.connect(set_volume_global)
row_overlay.mute_unmute_clicked.connect(mute)
row_overlay.mute_unmute_clicked_global.connect(mute_global)

row_overlay.volume_bar_row.position_changed.emit(0.65)

c.check(
    "dragging the row bar asks for this video's level",
    set_volume.calls == [(0.65,)] and set_volume_global.calls == [],
)

row_overlay.volume_bar_row.position_changed_global.emit(0.65)
row_overlay.volume_button_row.clicked.emit()

c.check(
    "and its global gesture for every video's",
    set_volume_global.calls == [(0.65,)],
)
c.check(
    "a left click on the row mute button mutes this video",
    mute.calls == [()] and mute_global.calls == [],
)

row_overlay.volume_button_row.global_requested.emit()

c.check(
    "and its global gesture mutes every video",
    mute_global.calls == [()],
)

# --- switching the look from the settings dialog ---------------------------

from gridplayer.dialogs.settings import SettingsDialog

dialog = SettingsDialog(window)

c.check(
    "the settings dialog carries a row for the volume look",
    dialog.miscVolumeInProgressRow is not None,
)

Settings().set("misc/volume_in_progress_row", True)
dialog.load_settings()

c.check(
    "which reads the setting back in",
    dialog.miscVolumeInProgressRow.isChecked() is True,
)

dialog.miscVolumeInProgressRow.setChecked(False)
dialog.save_settings()

c.check(
    "and writes it out",
    Settings().get("misc/volume_in_progress_row") is False,
)

# --- the switch takes effect without reopening the video -------------------

row_overlay.sync_volume_style()

c.check(
    "turning the row look off restores the original mute button",
    row_overlay.volume_button.isHidden() is False,
)
c.check(
    "and takes the row look out of the layout",
    row_overlay.volume_button_row.isHidden() is True
    and row_overlay.volume_bar_row.isHidden() is True,
)

Settings().set("misc/volume_in_progress_row", True)
row_overlay.sync_volume_style()

c.check(
    "turning it back on restores the row look",
    row_overlay.volume_bar_row.isHidden() is False
    and row_overlay.volume_button.isHidden() is True,
)

# --- source-level guards ---------------------------------------------------

source = (
    Path(__file__).resolve().parent.parent
    / "gridplayer"
    / "widgets"
    / "video_overlay.py"
).read_text(encoding="utf-8")

c.check(
    "the row look is chosen through one function",
    "def apply_volume_style(self):" in source,
)
c.check(
    "and the mode is read from Settings there",
    'Settings().get("misc/volume_in_progress_row")' in source,
)
c.check(
    "the edge bar is never shown while the row look is on",
    "if self.is_volume_in_row:" in source,
)

c.finish()
