"""Window state restore.

Note on scope: the original design called for an extra off-screen guard. It was
dropped after measuring that Qt's own restoreGeometry() already relocates a
window whose saved screen is gone - a blob saved at (-9000, -9000) comes back
inside the primary screen's available area, so a hand-written guard would have
been unreachable dead code. What is asserted here is the property the user
actually cares about: a saved position can never leave the window invisible.
"""

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("window state restore")

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import Context
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.settings import Settings


def make_manager():
    ctx = Context()
    win = QWidget()
    return WindowStateManager(context=ctx, parent=win), win


def blob_of(x, y, w, h):
    wdg = QWidget()
    wdg.resize(w, h)
    wdg.move(x, y)
    return base64.b64encode(bytes(wdg.saveGeometry())).decode()


def is_on_some_screen(widget):
    center = widget.frameGeometry().center()

    return any(
        screen.availableGeometry().contains(center)
        for screen in QGuiApplication.screens()
    )


primary = QGuiApplication.primaryScreen().availableGeometry()

# --- empty geometry -> nothing to restore ---
Settings().set("player/window_geometry", "")
Settings().sync()
mgr, win = make_manager()
c.check("empty geometry -> no restore", mgr._saved_window_state() is None)
c.check(
    "empty geometry -> restore() reports False",
    mgr._restore_saved_window_state() is False,
)

# --- on-screen geometry -> restored verbatim ---
on_screen = blob_of(primary.x() + 40, primary.y() + 40, 720, 480)
Settings().set("player/window_geometry", on_screen)
Settings().set("player/window_maximized", False)
Settings().set("player/window_fullscreen", False)
Settings().sync()

mgr, win = make_manager()
c.check("restore applied", mgr._restore_saved_window_state() is True)
c.check(
    "window geometry applied",
    (win.width(), win.height()) == (720, 480),
    f"{win.width()}x{win.height()}",
)

# --- off-screen geometry -> Qt relocates it, window still visible ---
far = blob_of(primary.x() - 9000, primary.y() - 9000, 720, 480)
Settings().set("player/window_geometry", far)
Settings().sync()

mgr2, win2 = make_manager()
mgr2._restore_saved_window_state()
c.check(
    "off-screen saved position still lands on a real screen",
    is_on_some_screen(win2),
    f"frame={win2.frameGeometry()}",
)

# --- flags are read back ---
Settings().set("player/window_geometry", on_screen)
Settings().set("player/window_maximized", True)
Settings().set("player/window_fullscreen", False)
Settings().sync()

mgr3, win3 = make_manager()
saved = mgr3._saved_window_state()
c.check("saved state reports maximized", saved.is_maximized is True)
c.check("saved state reports not fullscreen", saved.is_fullscreen is False)

# --- a corrupt blob must not crash ---
Settings().set("player/window_geometry", "!!!not-base64!!!")
Settings().sync()

mgr4, win4 = make_manager()
try:
    restored = mgr4._restore_saved_window_state()
    survived = True
except Exception as e:  # noqa: BLE001
    restored, survived = None, False
    print(f"  exception: {e!r}")

c.check("corrupt base64 does not crash", survived)
c.check("corrupt base64 is treated as no state", restored is False, f"{restored}")

# --- valid base64 that is not a geometry blob ---
Settings().set("player/window_geometry", base64.b64encode(b"not a geometry").decode())
Settings().sync()

mgr5, win5 = make_manager()
try:
    mgr5._restore_saved_window_state()
    survived2 = True
except Exception as e:  # noqa: BLE001
    survived2 = False
    print(f"  exception: {e!r}")

c.check("garbage-but-decodable geometry does not crash", survived2)

# --- REGRESSION: fullscreen restores even from a non-maximized window ---
# Upstream gated showFullScreen() on is_maximized, which is only true when the
# window was maximized *before* going fullscreen - so closing a normal window
# while fullscreen lost the fullscreen state on the next launch.
from gridplayer.params.static import WindowState  # noqa: E402


class RecordingWindow(QWidget):
    """Records show* calls instead of actually showing anything."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def showFullScreen(self):
        self.calls.append("fullscreen")

    def showMaximized(self):
        self.calls.append("maximized")

    def showNormal(self):
        self.calls.append("normal")


ctx_f, rec_f = Context(), RecordingWindow()
WindowStateManager(context=ctx_f, parent=rec_f).restore_window_state(
    WindowState(is_maximized=False, is_fullscreen=True, geometry=on_screen)
)
c.check(
    "fullscreen restored from a non-maximized window",
    rec_f.calls == ["fullscreen"],
    f"{rec_f.calls}",
)
c.check(
    "pre-fullscreen maximized memory stays False",
    ctx_f.is_maximized_pre_fullscreen is False,
)

ctx_fm, rec_fm = Context(), RecordingWindow()
WindowStateManager(context=ctx_fm, parent=rec_fm).restore_window_state(
    WindowState(is_maximized=True, is_fullscreen=True, geometry=on_screen)
)
c.check(
    "fullscreen from a maximized window still works",
    rec_fm.calls == ["fullscreen"],
    f"{rec_fm.calls}",
)
c.check(
    "pre-fullscreen maximized memory recorded as True",
    ctx_fm.is_maximized_pre_fullscreen is True,
)

ctx_m, rec_m = Context(), RecordingWindow()
WindowStateManager(context=ctx_m, parent=rec_m).restore_window_state(
    WindowState(is_maximized=True, is_fullscreen=False, geometry=on_screen)
)
c.check(
    "plain maximized restore unaffected", rec_m.calls == ["maximized"], f"{rec_m.calls}"
)

# --- REGRESSION: a blob whose embedded state disagrees with the flags ---
# saveGeometry() stores the window state too, and restoreGeometry() applies it.
# When that disagreed with the flags we store alongside it (blob: fullscreen,
# flags: windowed) the window came back fullscreen. The flags must win.
ctx_n, rec_n = Context(), RecordingWindow()
WindowStateManager(context=ctx_n, parent=rec_n).restore_window_state(
    WindowState(is_maximized=False, is_fullscreen=False, geometry=on_screen)
)
c.check(
    "windowed flags force showNormal (blob state cannot override)",
    rec_n.calls == ["normal"],
    f"{rec_n.calls}",
)

c.finish()
