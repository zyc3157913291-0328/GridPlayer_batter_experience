"""MOD: a playlist click must not depend on where the mouse pointer happens to be.

Reported: after clicking the window title bar or the playlist's sort header,
clicking an entry no longer switched playback, and clicking a video block first
made it work again.

Cause was in PlaylistPanelManager._play_entry: it read ctx.active_block, which
ActiveBlockManager drives from the pointer (update_active_under_mouse /
update_active_reset). With the cursor off the video area that is None, so the
handler returned without doing anything - silently. ctx.last_active_block is the
remembered block for exactly this situation, and window_state.py already reads
`active_block or last_active_block`; the panel manager did not.

This drives the real manager with stub blocks, so it fails if that fallback is
ever dropped again.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("playlist click target")

from PyQt5.QtWidgets import QSplitter, QWidget

from gridplayer.player.manager import Commands, Context
from gridplayer.player.managers.playlist_panel import PlaylistPanelManager

NOWHERE = Path(r"E:\somewhere")


class StubBlock:
    """Only what _play_entry / _play_next touch."""

    def __init__(self, uri):
        self.video_params = SimpleNamespace(uri=Path(uri))
        self.switched = []
        self.next_override = []

    def switch_video(self, path):
        self.switched.append(Path(path))

    def set_next_override(self, path):
        self.next_override.append(Path(path))


window = QWidget()
context = Context()
context.commands = Commands()
context.layout_splitter = QSplitter(window)
context.video_blocks = []
context.active_block = None
context.last_active_block = None

manager = PlaylistPanelManager(context=context, parent=window)

playing = StubBlock(NOWHERE / "playing.mp4")
other = NOWHERE / "other.mp4"

context.video_blocks = [playing]
context.active_block = playing
context.last_active_block = playing

# --- pointer on a video block: the old code worked here ---

manager._play_entry(other)
c.check(
    "switches when the pointer is over the video",
    playing.switched == [other],
    f"{playing.switched}",
)

# --- pointer on the title bar / sort header: active_block is None there ---

playing.switched.clear()
context.active_block = None

manager._play_entry(other)
c.check(
    "switches when the pointer is off the videos (title bar / sort header)",
    playing.switched == [other],
    f"{playing.switched}",
)

# --- and the other entry actions need the same fallback ---

context.active_block = None
manager._play_next(other)
c.check(
    "queue-next also survives the pointer being elsewhere",
    playing.next_override == [other],
    f"{playing.next_override}",
)

# --- with nothing remembered there is genuinely nothing to switch ---

context.active_block = None
context.last_active_block = None
context.video_blocks = [playing, StubBlock(NOWHERE / "second.mp4")]

playing.switched.clear()
manager._play_entry(other)
c.check(
    "still does nothing when there is no block to switch",
    playing.switched == [],
    f"{playing.switched}",
)

manager.cleanup()
c.finish()
