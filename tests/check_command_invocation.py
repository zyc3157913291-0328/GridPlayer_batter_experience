"""Manager commands must be called through ctx.commands, not ctx.<name>().

Regression for a crash: single_mode called self._ctx.fullscreen(), which raised
KeyError because commands live in a Commands object (ctx.commands), not at the
top level of the context.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("command invocation")

from gridplayer.player.manager import Commands, Context
from gridplayer.player.managers.window_state import WindowStateManager

# --- the Commands API shape ---
cmds = Commands()
cmds.update({"fullscreen": lambda: "toggled"})
c.check(
    "commands are reached via attribute then called", cmds.fullscreen() == "toggled"
)

c.check("Commands is iterable", "fullscreen" in list(cmds))

# --- window_state really does register 'fullscreen' ---
from PyQt5.QtWidgets import QWidget

# keep the parent alive: the manager is a QObject child of it, and a temporary
# QWidget would be garbage collected (taking the manager with it)
_win = QWidget()
mgr = WindowStateManager(context=Context(), parent=_win)
registered = mgr.commands
c.check(
    "window_state registers 'fullscreen'",
    "fullscreen" in registered,
    f"{sorted(registered)}",
)
c.check(
    "'fullscreen' is callable through the Commands wrapper",
    callable(registered["fullscreen"]),
)

# --- and the context top level must NOT be expected to hold it ---
ctx = Context()
ctx.commands = Commands()
ctx.commands.update({"fullscreen": lambda: "toggled"})

try:
    ctx.fullscreen
    top_level_works = True
except KeyError:
    top_level_works = False

c.check(
    "ctx.<name> does NOT resolve commands (why the crash happened)",
    top_level_works is False,
)
c.check(
    "ctx.commands.<name>() is the working form", ctx.commands.fullscreen() == "toggled"
)

c.finish()
