# MOD: checks for the playlist panel's folder bar and the reveal action.
import re
import sys
import tempfile
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._harness import Checker, bootstrap  # noqa: E402

bootstrap()

from PyQt5.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PyQt5.QtGui import QMouseEvent  # noqa: E402

from gridplayer.player.managers.playlist_panel import PlaylistPanelManager  # noqa: E402
from gridplayer.utils import file_manager  # noqa: E402
from gridplayer.widgets.playlist_panel import ClickableLabel, PlaylistPanel  # noqa: E402

c = Checker("playlist panel folder")

SRC = Path(__file__).resolve().parents[1] / "gridplayer"


def method_source(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^(\s*)def {name}\(", text, re.MULTILINE)
    if match is None:
        return ""
    indent = len(match.group(1))
    rest = text[match.end() :]
    stop = re.search(rf"^\s{{0,{indent}}}def ", rest, re.MULTILINE)
    return rest if stop is None else rest[: stop.start()]


# ---------------------------------------------------------------- the command
if file_manager.sys.platform == "win32":
    assert_cmd = ["explorer", f"/select,{Path('C:/videos/clip.mp4')}"]
    c.check(
        "windows reveals by selecting the file",
        file_manager.reveal_command(Path("C:/videos/clip.mp4")) == assert_cmd,
        file_manager.reveal_command(Path("C:/videos/clip.mp4")),
    )
    c.check(
        "the selection flag carries no space",
        "/select," in assert_cmd[1] and "/select, " not in assert_cmd[1],
        assert_cmd[1],
    )

posix_file = Path("/videos/clip.mp4")
posix_folder = Path("/videos")

with mock.patch.object(file_manager.sys, "platform", "darwin"):
    c.check(
        "macOS uses open -R",
        file_manager.reveal_command(posix_file) == ["open", "-R", str(posix_file)],
        file_manager.reveal_command(posix_file),
    )

with mock.patch.object(file_manager.sys, "platform", "linux"):
    c.check(
        "linux opens the containing folder",
        file_manager.reveal_command(posix_file) == ["xdg-open", str(posix_folder)],
        file_manager.reveal_command(posix_file),
    )

with mock.patch.object(file_manager.subprocess, "Popen", side_effect=OSError("no fm")):
    try:
        file_manager.reveal_path(Path("C:/videos/clip.mp4"))
    except OSError:
        raised = True
    else:
        raised = False

c.check("a missing file manager does not raise", not raised, raised)

# ------------------------------------------------------------------- the bar
panel = PlaylistPanel()

c.check(
    "the path bar is a clickable label",
    isinstance(panel.folder_label, ClickableLabel),
    type(panel.folder_label).__name__,
)
c.check(
    "the path bar shows a pointing hand",
    panel.folder_label.cursor().shape() == Qt.PointingHandCursor,
    panel.folder_label.cursor().shape(),
)
c.check(
    "the path bar explains itself",
    "文件夹" in panel.folder_label.toolTip(),
    panel.folder_label.toolTip(),
)

requests = []
panel.folder_browse_requested.connect(lambda: requests.append(True))

label = panel.folder_label
label.resize(120, 24)
global_pos = label.mapToGlobal(QPoint(5, 5))
click = QMouseEvent(
    QEvent.MouseButtonRelease,
    QPoint(5, 5),
    global_pos,
    Qt.LeftButton,
    Qt.NoButton,
    Qt.NoModifier,
)
label.mouseReleaseEvent(click)
c.check("clicking the path bar asks for a folder", requests == [True], requests)

right = QMouseEvent(
    QEvent.MouseButtonRelease,
    QPoint(5, 5),
    global_pos,
    Qt.RightButton,
    Qt.NoButton,
    Qt.NoModifier,
)
label.mouseReleaseEvent(right)
c.check("a right click does not ask for a folder", requests == [True], requests)

# ------------------------------------------------------- the folder shown
video_a = Path("C:/videos/a/clip.mp4")
video_b = Path("C:/videos/b/other.mp4")
panel.set_entries([], video_a)
c.check(
    "the bar follows the playing file's folder",
    panel.folder_label.text() == str(video_a.parent),
    panel.folder_label.text(),
)

panel.set_folder(video_b.parent)
c.check(
    "a chosen folder wins over the playing file",
    panel.folder_label.text() == str(video_b.parent),
    panel.folder_label.text(),
)

panel.set_entries([], video_a)
c.check(
    "the chosen folder survives a list refresh",
    panel.folder_label.text() == str(video_b.parent),
    panel.folder_label.text(),
)

panel.set_folder(None)
c.check(
    "clearing the choice follows playback again",
    panel.folder_label.text() == str(video_a.parent),
    panel.folder_label.text(),
)

# --------------------------------------------------------------- the manager


class PanelRecorder:
    def __init__(self):
        self.folders = []
        self.entries = []
        self.history = []

    def isHidden(self):
        return False

    def set_history(self, history):
        self.history.append(dict(history))

    def set_folder(self, folder):
        self.folders.append(folder)

    def set_entries(self, entries, current):
        self.entries.append(([e.name for e in entries], current))


class ProberStub:
    def cached(self, entry):
        return None

    def request(self, entries):
        pass


class ThumbsStub:
    def request(self, entries):
        pass


class HistoryStub:
    def __init__(self):
        self.recorded = []

    def as_mapping(self):
        return {}

    def record(self, key, when_ms=None):
        self.recorded.append(key)

    def save(self):
        pass


def make_manager(block, folder=None):
    m = SimpleNamespace()
    m._ctx = SimpleNamespace(video_blocks=[block] if block is not None else [])
    m._panel = PanelRecorder()
    m._prober = ProberStub()
    m._thumbs = ThumbsStub()
    m._history = HistoryStub()
    m._last_remembered = None
    m._browsed_folder = folder
    m._pin_video = None
    m.tr = lambda text: text
    m.parent = lambda: None
    m._show_folder = MethodType(PlaylistPanelManager._show_folder, m)
    m._browse_folder = MethodType(PlaylistPanelManager._browse_folder, m)
    m.refresh = MethodType(PlaylistPanelManager.refresh, m)
    m._remember = MethodType(PlaylistPanelManager._remember, m)
    m._target_block = MethodType(lambda self: block, m)
    return m


tmp = Path(tempfile.mkdtemp(prefix="gpmod-folder-"))
folder_one = tmp / "one"
folder_two = tmp / "two"
folder_one.mkdir(parents=True, exist_ok=True)
folder_two.mkdir(parents=True, exist_ok=True)
(folder_one / "a.mp4").write_bytes(b"")
(folder_one / "b.mp4").write_bytes(b"")
(folder_two / "c.mp4").write_bytes(b"")

block = SimpleNamespace(
    video_params=SimpleNamespace(uri=folder_one / "a.mp4"),
)

manager = make_manager(block)
manager.refresh()
names, current = manager._panel.entries[-1]
c.check(
    "a plain refresh lists the playing file's folder",
    names == ["a.mp4", "b.mp4"] and current == folder_one / "a.mp4",
    (names, current),
)
c.check(
    "a plain refresh pins nothing",
    manager._panel.folders[-1] is None,
    manager._panel.folders[-1],
)

with mock.patch(
    "gridplayer.player.managers.playlist_panel.QFileDialog.getExistingDirectory",
    return_value=str(folder_two),
):
    manager._browse_folder()

names, current = manager._panel.entries[-1]
c.check(
    "browsing lists the chosen folder",
    names == ["c.mp4"] and current is None,
    (names, current),
)
c.check(
    "browsing pins the folder",
    manager._panel.folders[-1] == folder_two,
    manager._panel.folders[-1],
)
c.check(
    "browsing leaves playback alone",
    block.video_params.uri == folder_one / "a.mp4",
    block.video_params.uri,
)

manager.refresh()
names, current = manager._panel.entries[-1]
c.check(
    "a refresh keeps the pinned folder while the video stays put",
    names == ["c.mp4"] and manager._browsed_folder == folder_two,
    (names, manager._browsed_folder),
)

block.video_params.uri = folder_one / "b.mp4"
manager.refresh()
names, current = manager._panel.entries[-1]
c.check(
    "a new video in the same folder releases the pin",
    manager._browsed_folder is None and names == ["a.mp4", "b.mp4"],
    (manager._browsed_folder, names),
)

manager._browsed_folder = folder_two
manager._pin_video = folder_one / "b.mp4"
block.video_params.uri = folder_two / "c.mp4"
manager.refresh()
names, current = manager._panel.entries[-1]
c.check(
    "playing from the pinned folder marks the row",
    names == ["c.mp4"] and current == folder_two / "c.mp4",
    (names, current),
)

# a video outside the pinned folder releases the pin
manager._browsed_folder = folder_two
manager._pin_video = folder_one / "b.mp4"
block.video_params.uri = folder_one / "a.mp4"
manager.refresh()
names, current = manager._panel.entries[-1]
c.check(
    "playing elsewhere releases the pin",
    manager._browsed_folder is None and names == ["a.mp4", "b.mp4"],
    (manager._browsed_folder, names),
)

with mock.patch(
    "gridplayer.player.managers.playlist_panel.QFileDialog.getExistingDirectory",
    return_value="",
):
    manager._browse_folder()

c.check(
    "cancelling the dialog changes nothing",
    manager._browsed_folder is None,
    manager._browsed_folder,
)

empty = make_manager(None)
empty.refresh()
c.check(
    "no video and no pin lists nothing",
    empty._panel.entries[-1] == ([], None),
    empty._panel.entries,
)

# ------------------------------------------------------------ source checks
panel_src = SRC / "widgets" / "playlist_panel.py"
c.check(
    "the path bar is rewired, not text-selectable",
    "TextSelectableByMouse" not in panel_src.read_text(encoding="utf-8"),
    "TextSelectableByMouse",
)
c.check(
    "the context menu offers the file manager",
    "reveal_path(" in method_source(panel_src, "_show_context_menu"),
    method_source(panel_src, "_show_context_menu")[-200:],
)
c.check(
    "the bar label falls back to the playing folder",
    "self._folder" in method_source(panel_src, "_rebuild"),
    method_source(panel_src, "_rebuild")[-200:],
)

import shutil

shutil.rmtree(tmp, ignore_errors=True)

c.finish()
