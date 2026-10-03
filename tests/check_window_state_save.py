import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("window state save")

from PyQt5.QtCore import QByteArray
from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import Context
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.settings import Settings


class FakeWindow(QWidget):
    """Minimal stand-in for the Player window."""

    def __init__(self):
        super().__init__()
        self.resize(800, 600)
        self.move(120, 80)


def make_manager():
    ctx = Context()
    win = FakeWindow()
    mgr = WindowStateManager(context=ctx, parent=win)
    return mgr, win


# --- writes all three settings ---
mgr, win = make_manager()
Settings().set("player/window_geometry", "")
Settings().sync()
mgr._save_window_state(mgr.window_state())

geom = Settings().get("player/window_geometry")
c.check("geometry written", bool(geom), f"len={len(geom)}")
c.check(
    "maximized written (windowed -> False)",
    Settings().get("player/window_maximized") is False,
)
c.check(
    "fullscreen written (windowed -> False)",
    Settings().get("player/window_fullscreen") is False,
)

# --- round-trip: the blob decodes back to the same size/position ---
probe = QWidget()
ok = probe.restoreGeometry(QByteArray(base64.b64decode(geom)))
c.check("geometry blob restores", ok is True)
c.check(
    "restored size matches",
    (probe.width(), probe.height()) == (800, 600),
    f"{probe.width()}x{probe.height()}",
)
c.check(
    "restored pos matches",
    (probe.x(), probe.y()) == (120, 80),
    f"{probe.x()},{probe.y()}",
)

# --- the three settings stay consistent with what window_state() reports ---
c.check(
    "saved maximized flag matches window_state()",
    Settings().get("player/window_maximized") == mgr.window_state().is_maximized,
)
c.check(
    "saved fullscreen flag matches window_state()",
    Settings().get("player/window_fullscreen") == mgr.window_state().is_fullscreen,
)

# --- REGRESSION: capture must happen before the close sequence shrinks the window ---
# closeEvent runs close_playlist() first, and playlist_closed is wired to
# window_state.restore_to_minimum(), which resizes the window down to its
# minimum. Reading the geometry after that stored the minimum instead of the
# window the user actually closed - position came out right, size did not.
big = FakeWindow()
big.resize(900, 560)
big.move(300, 200)
mgr_big = WindowStateManager(context=Context(), parent=big)

captured = mgr_big.window_state()  # closeEvent: read BEFORE close_playlist()
big.setMinimumSize(640, 360)
big.resize(big.minimumSize())  # what restore_to_minimum() does
mgr_big._save_window_state(captured)  # closeEvent: write afterwards

written = QWidget()
written.restoreGeometry(
    QByteArray(base64.b64decode(Settings().get("player/window_geometry")))
)
c.check(
    "size survives restore_to_minimum shrinking the window",
    (written.width(), written.height()) == (900, 560),
    f"{written.width()}x{written.height()}",
)

c.finish()
