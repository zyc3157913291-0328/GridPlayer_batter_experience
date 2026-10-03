"""P3 Task 8: playlist sorting carries over to the next window."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("sort persistence")

from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import Context
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.settings import Settings
from gridplayer.widgets.playlist_panel import PlaylistPanel

# --- a new panel adopts whatever was stored ---
Settings().set("player/playlist_sort_key", "duration")
Settings().set("player/playlist_sort_desc", True)
Settings().sync()

panel = PlaylistPanel()
panel.set_sort(
    Settings().get("player/playlist_sort_key"),
    Settings().get("player/playlist_sort_desc"),
)
c.check("new panel adopts the stored key", panel.sort_key == "duration", panel.sort_key)
c.check("new panel adopts the stored direction", panel.sort_desc is True)

# --- an unknown stored key falls back instead of breaking the panel ---
Settings().set("player/playlist_sort_key", "nonsense")
Settings().sync()
panel2 = PlaylistPanel()
panel2.set_sort(Settings().get("player/playlist_sort_key"), False)
c.check(
    "unknown stored key falls back to name", panel2.sort_key == "name", panel2.sort_key
)


# --- close writes the panel's current sorting back ---
class StubPanel:
    sort_key = "mtime"
    sort_desc = True


ctx = Context()
ctx.playlist_sort_key = lambda: "mtime"  # Context evaluates callables
ctx.playlist_sort_desc = lambda: True
mgr = WindowStateManager(context=ctx, parent=QWidget())

Settings().set("player/playlist_sort_key", "name")
Settings().set("player/playlist_sort_desc", False)
Settings().sync()

mgr._save_playlist_sort()
c.check(
    "close persisted the key",
    Settings().get("player/playlist_sort_key") == "mtime",
    Settings().get("player/playlist_sort_key"),
)
c.check(
    "close persisted the direction", Settings().get("player/playlist_sort_desc") is True
)

# --- a window without a panel manager must still be closable ---
bare = Context()
bare.video_blocks = []
mgr_bare = WindowStateManager(context=bare, parent=QWidget())

try:
    mgr_bare._save_playlist_sort()
    survived = True
except Exception as e:  # noqa: BLE001
    survived = False
    print(f"  exception: {e!r}")

c.check("missing panel manager does not raise", survived)
c.check(
    "and leaves the stored value untouched",
    Settings().get("player/playlist_sort_key") == "mtime",
    Settings().get("player/playlist_sort_key"),
)

c.finish()
