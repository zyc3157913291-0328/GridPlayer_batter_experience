"""No videos left -> the window closes instead of showing the placeholder.

Upstream keeps the window open with the "Drag and drop media files or URLs
here" label. The rule here is deliberately narrow:

  * only on the way *down* from a non-empty grid, so starting the app with no
    arguments still shows the window (and the single instance listener can hand
    it a file);
  * acted on one event loop turn later, because loading a playlist over the top
    of another one takes the grid through zero and refills it in the same turn.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("quit when empty")

from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.player.manager import Commands, Context
from gridplayer.player.managers.video_blocks import VideoBlocks, VideoBlocksManager
from gridplayer.player.managers.window_state import WindowStateManager


def block(block_id):
    b = type("StubBlock", (), {})()
    b.id = block_id
    return b


def make_vbm(ctx):
    win = QWidget()

    vbm = VideoBlocksManager(context=ctx, parent=win)
    vbm._win = win

    return vbm


# --- 1. when the signal fires -----------------------------------------------

ctx = Context()
ctx.commands = Commands()
vbm = make_vbm(ctx)

events = []
vbm.video_count_changed.connect(lambda n: events.append(("count", n)))
vbm.videos_emptied.connect(lambda: events.append(("emptied", None)))

c.check("starting empty says nothing at all", events == [], f"{events}")

vbm.add_videos([])
c.check(
    "adding nothing does not ask to quit",
    [e for e in events if e[0] == "emptied"] == [],
    f"{events}",
)

ctx.video_blocks.append(block("a"))
ctx.video_blocks.append(block("b"))
events.clear()

vbm.close_single("a")
c.check(
    "closing one of two does not ask to quit",
    [e for e in events if e[0] == "emptied"] == [],
    f"{events}",
)

vbm.close_single("b")
c.check(
    "closing the last one asks to quit",
    [e for e in events if e[0] == "emptied"] == [("emptied", None)],
    f"{events}",
)
c.check(
    "the count is still announced first",
    [e[0] for e in events] == ["count", "count", "emptied"],
    f"{events}",
)

# --- 2. clearing an already empty grid must not ask again -------------------

events.clear()
vbm.close_all()
c.check(
    "clearing an already empty grid does not ask to quit",
    [e for e in events if e[0] == "emptied"] == [],
    f"{events}",
)

ctx.video_blocks.append(block("c"))
events.clear()
vbm.close_all()
c.check(
    "clearing a non-empty grid does ask to quit",
    [e for e in events if e[0] == "emptied"] == [("emptied", None)],
    f"{events}",
)

# --- 3. the window actually closes, one turn later --------------------------

close_calls = []

close_ctx = Context()
close_ctx.commands = Commands()
close_ctx.commands.update({"close": lambda: close_calls.append(True)})
close_ctx.video_blocks = VideoBlocks()

close_win = QWidget()
ws = WindowStateManager(context=close_ctx, parent=close_win)

ws.close_when_empty()
c.check("nothing happens within the same turn", close_calls == [], f"{close_calls}")

QApplication.processEvents()
c.check("an empty grid closes the window", close_calls == [True], f"{close_calls}")

# --- 4. a grid refilled in the same turn wins -------------------------------

close_calls.clear()
close_ctx.video_blocks.append(block("x"))

ws.close_when_empty()
QApplication.processEvents()

c.check(
    "a grid refilled in the same turn keeps the window open",
    close_calls == [],
    f"{close_calls}",
)

# and once it is emptied again, it closes
close_calls.clear()
close_ctx.video_blocks.clear()
ws.close_when_empty()
QApplication.processEvents()

c.check(
    "and it closes again once that video is gone",
    close_calls == [True],
    f"{close_calls}",
)

# --- 5. wiring --------------------------------------------------------------

player_src = (
    Path(__file__).resolve().parent.parent / "gridplayer" / "player" / "player.py"
).read_text(encoding="utf-8")

c.check(
    "player.py wires the empty event to the window",
    '("videos_emptied", "window_state.close_when_empty")' in player_src,
)

c.check("video_blocks announces it", hasattr(VideoBlocksManager, "videos_emptied"))
c.check(
    "window_state handles it",
    callable(getattr(WindowStateManager, "close_when_empty", None)),
)

# --- 6. the real connection resolves and really closes ----------------------

from gridplayer.player.manager import ManagersManager  # noqa: E402


class _Resolver(ManagersManager):
    pass


w_win = QWidget()
w_ctx = Context()
w_ctx.commands = Commands()
w_ctx.video_blocks = VideoBlocks()

hits = []
w_ctx.commands.update({"close": lambda: hits.append(True)})

resolver = _Resolver()
resolver._managers_inst = {
    "window_state": WindowStateManager(context=w_ctx, parent=w_win),
    "video_blocks": VideoBlocksManager(context=w_ctx, parent=w_win),
}

# resolve the very strings player.py uses, so a rename is caught here
sig = resolver._get_manager_function("video_blocks", "videos_emptied")
slot = resolver._get_manager_function("window_state", "close_when_empty")
sig.connect(slot)

resolver._managers_inst["video_blocks"].videos_emptied.emit()
QApplication.processEvents()

c.check(
    "through the real connection an empty grid closes the window",
    hits == [True],
    f"{hits}",
)

# and the guard still holds on that path
hits.clear()
w_ctx.video_blocks.append(block("still-here"))

resolver._managers_inst["video_blocks"].videos_emptied.emit()
QApplication.processEvents()

c.check("and it does not close while a video is there", hits == [], f"{hits}")

c.finish()
