"""MOD: Control (or the right button) on a control means "every video".

The overlay's controls are drawn per video, but several of them stand for a
setting the whole grid shares: volume, speed, play order, the progress bar. The
request is that using one of them with Control held - or with the right button -
applies it to every video, while a plain left click keeps working on its own
video. Only the close button is left out - it has nothing to mean for the
others. Play/pause joins in, but it never toggles each video on its own: the
video the click landed on decides the new state and every video is put into it,
so a grid of mixed states cannot come out of one gesture.

Only the step that finishes the interaction is asked, so a drag that starts one
way and ends the other follows its last step.

Run: pyenv\\Scripts\\python.exe tests\\check_global_controls.py
"""

import re
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("global controls")

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.params.static import SeekSyncMode, VideoRepeat, next_video_repeat
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_elements import is_global_gesture


def mouse(kind, widget, pos, button, modifiers=Qt.NoModifier):
    return QMouseEvent(
        kind,
        QPointF(pos),
        QPointF(widget.mapToGlobal(pos)),
        button,
        button,
        modifiers,
    )


def send(widget, event):
    QApplication.sendEvent(widget, event)

    return event


class Recorder:
    """Stands in for a pyqtSignal, or for a driver method that is only called."""

    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)

    def __call__(self, *args):
        self.calls.append(args)


class CommandStub:
    def __init__(self):
        self.calls = []

    def all(self, *args):
        self.calls.append(args)

    def all_play(self):
        self.calls.append(("all_play",))

    def all_pause(self):
        self.calls.append(("all_pause",))


window = QWidget()
overlay = OverlayBlock(window)

bar = overlay.progress_bar
volume_bar = overlay.volume_bar
repeat_button = overlay.repeat_button
volume_button = overlay.volume_button
play_pause_button = overlay.play_pause_button
speed_button = overlay.speed_button
speed_popup = overlay.speed_popup

bar.resize(200, 20)
volume_bar.resize(20, 200)

# --- which gestures ask for every video --------------------------------------


def gesture(button, modifiers=Qt.NoModifier):
    ev = mouse(QEvent.MouseButtonPress, bar, QPoint(1, 1), button, modifiers)

    return is_global_gesture(ev)


c.check(
    "a plain left gesture stays local",
    gesture(Qt.LeftButton) is False,
)
c.check(
    "Control held makes it global",
    gesture(Qt.LeftButton, Qt.ControlModifier) is True,
)
c.check(
    "the right button is global on its own",
    gesture(Qt.RightButton) is True,
)
c.check(
    "Control plus modifiers still reads as global",
    gesture(Qt.LeftButton, Qt.ControlModifier | Qt.ShiftModifier) is True,
)
c.check(
    "an unrelated modifier is not global",
    gesture(Qt.LeftButton, Qt.ShiftModifier) is False,
)

# --- the two bars ------------------------------------------------------------

local = []
global_ = []

bar.position_changed.connect(lambda pos: local.append(pos))
bar.position_changed_global.connect(lambda pos: global_.append(pos))

send(bar, mouse(QEvent.MouseButtonPress, bar, QPoint(100, 10), Qt.LeftButton))
c.check(
    "left click on the progress bar is the local signal",
    len(local) == 1 and not global_,
)
c.check("and it carries the position under the cursor", local and local[-1] == 0.5)

send(bar, mouse(QEvent.MouseButtonPress, bar, QPoint(50, 10), Qt.RightButton))
c.check(
    "right click on the progress bar is the global signal",
    len(global_) == 1 and len(local) == 1,
)
c.check("and it carries its own position too", global_ and global_[-1] == 0.25)

send(
    bar,
    mouse(
        QEvent.MouseButtonPress, bar, QPoint(200, 10), Qt.LeftButton, Qt.ControlModifier
    ),
)
c.check(
    "Control plus left click is global as well",
    len(global_) == 2 and len(local) == 1,
)

# one step at a time: a position asked for globally must not also go out locally
c.check(
    "a global position is not repeated as a local one",
    len(local) == 1 and len(global_) == 2,
)

volume_local = []
volume_global = []

volume_bar.position_changed.connect(lambda pos: volume_local.append(pos))
volume_bar.position_changed_global.connect(lambda pos: volume_global.append(pos))

send(
    volume_bar,
    mouse(
        QEvent.MouseButtonPress,
        volume_bar,
        QPoint(10, volume_bar.height() // 4),
        Qt.LeftButton,
    ),
)
c.check(
    "left click on the volume bar is the local signal",
    len(volume_local) == 1 and not volume_global,
)
c.check("and the level reads bottom-up", volume_local and volume_local[-1] == 0.75)

send(
    volume_bar,
    mouse(
        QEvent.MouseButtonPress,
        volume_bar,
        QPoint(10, volume_bar.height() * 3 // 4),
        Qt.RightButton,
    ),
)
c.check(
    "right click on the volume bar is the global signal",
    len(volume_global) == 1 and len(volume_local) == 1,
)
c.check(
    "and the level reads bottom-up there too",
    volume_global and volume_global[-1] == 0.25,
)

send(
    volume_bar,
    mouse(
        QEvent.MouseButtonPress,
        volume_bar,
        QPoint(10, volume_bar.height() // 2),
        Qt.LeftButton,
        Qt.ControlModifier,
    ),
)
c.check(
    "Control plus left click on the volume bar is global",
    len(volume_global) == 2 and len(volume_local) == 1,
)

# moving with the button held follows the same rule the press did
volume_global.clear()
volume_local.clear()

send(
    volume_bar,
    mouse(
        QEvent.MouseMove,
        volume_bar,
        QPoint(10, volume_bar.height() // 2),
        Qt.NoButton,
        Qt.ControlModifier,
    ),
)
c.check(
    "a moved position is not emitted without a button held",
    not volume_global and not volume_local,
)

# --- the buttons -------------------------------------------------------------

# play/pause joins the global set through its own button
play_clicks = []
play_globals = []
play_pause_button.clicked.connect(lambda: play_clicks.append(1))
play_pause_button.global_requested.connect(lambda: play_globals.append(1))

send(
    play_pause_button,
    mouse(
        QEvent.MouseButtonPress,
        play_pause_button,
        QPoint(5, 5),
        Qt.LeftButton,
        Qt.ControlModifier,
    ),
)
c.check("a Control click on play/pause asks for every video", play_globals == [1])
c.check("and does not play this one on its own", play_clicks == [])

send(
    play_pause_button,
    mouse(QEvent.MouseButtonPress, play_pause_button, QPoint(5, 5), Qt.RightButton),
)
c.check("the right button on it asks for every video too", play_globals == [1, 1])
c.check("still nothing plays on its own", play_clicks == [])

send(
    play_pause_button,
    mouse(QEvent.MouseButtonPress, play_pause_button, QPoint(5, 5), Qt.LeftButton),
)
c.check("a plain left click still plays just this one", play_clicks == [1])

volume_globals = []
volume_clicks = []

volume_button.global_requested.connect(lambda: volume_globals.append(1))
volume_button.clicked.connect(lambda: volume_clicks.append(1))

c.check(
    "the volume button takes the global gesture",
    volume_button.wants_global_gesture is True,
)

send(
    volume_button,
    mouse(
        QEvent.MouseButtonPress,
        volume_button,
        QPoint(5, 5),
        Qt.LeftButton,
        Qt.ControlModifier,
    ),
)
c.check(
    "Control plus left click mutes every video",
    volume_globals == [1] and not volume_clicks,
)

send(
    volume_button,
    mouse(QEvent.MouseButtonPress, volume_button, QPoint(5, 5), Qt.LeftButton),
)
c.check(
    "and a plain left click still toggles this one",
    volume_clicks == [1] and volume_globals == [1],
)

send(
    volume_button,
    mouse(QEvent.MouseButtonPress, volume_button, QPoint(5, 5), Qt.RightButton),
)
c.check(
    "the right button on the volume button mutes every video",
    volume_globals == [1, 1] and volume_clicks == [1],
)

mode_locals = []
mode_globals = []

repeat_button.repeat_mode_changed.connect(lambda mode: mode_locals.append(mode))
repeat_button.repeat_mode_changed_global.connect(lambda mode: mode_globals.append(mode))

repeat_button.repeat_mode = VideoRepeat.DIR

send(
    repeat_button,
    mouse(QEvent.MouseButtonPress, repeat_button, QPoint(5, 5), Qt.LeftButton),
)
c.check(
    "a plain click still cycles this video only",
    mode_locals == [next_video_repeat(VideoRepeat.DIR)] and not mode_globals,
)
c.check(
    "and the button shows the mode it just moved to",
    repeat_button.repeat_mode == next_video_repeat(VideoRepeat.DIR),
)

repeat_button.repeat_mode = VideoRepeat.DIR

send(
    repeat_button,
    mouse(
        QEvent.MouseButtonPress,
        repeat_button,
        QPoint(5, 5),
        Qt.LeftButton,
        Qt.ControlModifier,
    ),
)
c.check(
    "Control plus left click asks every video for the next mode",
    mode_globals == [next_video_repeat(VideoRepeat.DIR)],
)
c.check(
    "and it is an absolute mode, not a step taken locally first",
    repeat_button.repeat_mode == VideoRepeat.DIR,
)
c.check(
    "so the grid cannot end up split across modes",
    mode_locals == [next_video_repeat(VideoRepeat.DIR)],
)

send(
    repeat_button,
    mouse(QEvent.MouseButtonPress, repeat_button, QPoint(5, 5), Qt.RightButton),
)
c.check(
    "the right button asks for it too",
    mode_globals == [next_video_repeat(VideoRepeat.DIR)] * 2,
)

# --- the speed control -------------------------------------------------------

speed_locals = []
speed_globals = []

speed_button.rate_selected.connect(lambda rate: speed_locals.append(rate))
speed_button.rate_selected_global.connect(lambda rate: speed_globals.append(rate))
speed_popup.rate_selected.connect(lambda rate: speed_locals.append(rate))
speed_popup.rate_selected_global.connect(lambda rate: speed_globals.append(rate))

speed_button.rate = 1.5

send(
    speed_button,
    mouse(QEvent.MouseButtonRelease, speed_button, QPoint(5, 5), Qt.RightButton),
)
c.check(
    "right click on the speed control puts every video on this speed",
    speed_globals == [1.5] and not speed_locals,
)

listed = []
speed_button.list_requested.connect(lambda: listed.append(1))

send(
    speed_button,
    mouse(QEvent.MouseButtonRelease, speed_button, QPoint(5, 5), Qt.LeftButton),
)
c.check("a left click still opens the gear list", listed == [1])

row = 2
row_y = row * speed_popup.ROW_HEIGHT + speed_popup.ROW_HEIGHT // 2
expected_rate = speed_popup.rates_top_down[row]

send(
    speed_popup,
    mouse(QEvent.MouseButtonRelease, speed_popup, QPoint(10, row_y), Qt.LeftButton),
)
c.check(
    "picking a gear with the left button is this video's",
    speed_locals == [expected_rate] and speed_globals == [1.5],
    f"locals={speed_locals} globals={speed_globals} rate={expected_rate}",
)
c.check("and the list closes right after", speed_popup.isVisible() is False)

send(
    speed_popup,
    mouse(
        QEvent.MouseButtonRelease,
        speed_popup,
        QPoint(10, row_y),
        Qt.LeftButton,
        Qt.ControlModifier,
    ),
)
c.check(
    "a Control click on a gear is every video's",
    speed_globals == [1.5, expected_rate] and speed_locals == [expected_rate],
)

send(
    speed_popup,
    mouse(QEvent.MouseButtonRelease, speed_popup, QPoint(10, row_y), Qt.RightButton),
)
c.check(
    "and so is a right click on a gear",
    speed_globals == [1.5, expected_rate, expected_rate],
    f"globals={speed_globals} locals={speed_locals} rate={expected_rate}",
)

# --- the overlay forwards each pair to its own signal ------------------------

paired = [
    (
        "set_vid_pos",
        "set_vid_pos_global",
        bar.position_changed,
        bar.position_changed_global,
        0.3,
    ),
    (
        "set_volume",
        "set_volume_global",
        volume_bar.position_changed,
        volume_bar.position_changed_global,
        0.4,
    ),
]

for local_name, global_name, local_signal, global_signal, value in paired:
    seen = []

    getattr(overlay, local_name).connect(lambda *_a, _s=seen: _s.append("local"))
    getattr(overlay, global_name).connect(lambda *_a, _s=seen: _s.append("global"))

    local_signal.emit(value)
    c.check(
        f"the overlay passes {local_name} on as itself",
        seen == ["local"],
    )

    seen.clear()
    global_signal.emit(value)
    c.check(
        f"and {global_name} separately",
        seen == ["global"],
    )

mute_seen = []
overlay.mute_unmute_clicked_global.connect(lambda: mute_seen.append(1))
volume_button.global_requested.emit()
c.check("the volume button's global click reaches the block side", mute_seen == [1])

mode_seen = []
overlay.repeat_mode_changed_global.connect(lambda mode: mode_seen.append(mode))
repeat_button.repeat_mode_changed_global.emit(VideoRepeat.SINGLE_FILE)
c.check("so does the repeat button's", mode_seen == [VideoRepeat.SINGLE_FILE])

rate_seen = []
overlay.speed_selected_global.connect(lambda rate: rate_seen.append(rate))
speed_popup.rate_selected_global.emit(2.0)
speed_button.rate_selected_global.emit(3.0)
c.check(
    "both halves of the speed control feed one global signal",
    rate_seen == [2.0, 3.0],
)

c.check(
    "the overlay declares the five global variants",
    all(
        hasattr(overlay, name)
        for name in (
            "set_vid_pos_global",
            "set_volume_global",
            "mute_unmute_clicked_global",
            "repeat_mode_changed_global",
            "speed_selected_global",
        )
    ),
)

# --- the block side ----------------------------------------------------------


def make_block(is_muted=False, rate=1.0, volume=0.5):
    block = SimpleNamespace(
        is_video_initialized=True,
        is_live=False,
        video_params=SimpleNamespace(is_muted=is_muted, rate=rate, volume=volume),
        video_driver=SimpleNamespace(
            audio_set_mute=Recorder(),
            audio_set_volume=Recorder(),
            set_playback_rate=Recorder(),
            length=100000,
        ),
        _ctx=SimpleNamespace(
            commands=CommandStub(), seek_sync_mode=SeekSyncMode.DISABLED
        ),
        seek_percent=Recorder(),
        sync_others_percent=Recorder(),
        sync_others_time=Recorder(),
        sync_percent=Recorder(),
        sync_time=Recorder(),
        sync_paused=Recorder(),
        volume_change=Recorder(),
        is_muted_change=Recorder(),
        rate_change=Recorder(),
        repeat_mode_change=Recorder(),
        info_change=Recorder(),
        video_tracks=[],
        position=0.5,
    )
    block.commands = block._ctx.commands
    # mute_unmute is real code that has to reach the real set_muted
    block.set_muted = MethodType(VideoBlock.set_muted, block)

    return block


block = make_block()

VideoBlock.set_volume(block, 0.4, is_global=True)
c.check(
    "a global volume set asks the manager to cover the grid",
    block.commands.calls == [("set_volume", 0.4)],
)
c.check(
    "and does not also set this video by hand",
    not block.video_driver.audio_set_volume.calls,
)

block = make_block()
VideoBlock.set_volume(block, 0.4)
c.check(
    "a local volume set goes straight to the driver",
    block.video_driver.audio_set_volume.calls == [(0.4,)] and not block.commands.calls,
)

block = make_block()
VideoBlock.set_rate(block, 2.0, is_global=True)
c.check(
    "a global speed set asks the manager as well",
    block.commands.calls == [("set_rate", 2.0)]
    and not block.video_driver.set_playback_rate.calls,
)

block = make_block()
VideoBlock.set_rate(block, 2.0)
c.check(
    "a local speed set is this video's alone",
    block.video_driver.set_playback_rate.calls == [(2.0,)] and not block.commands.calls,
)

block = make_block(is_muted=False)
VideoBlock.mute_unmute(block, is_global=True)
c.check(
    "a global mute reads this video's state and applies it to all",
    block.commands.calls == [("set_muted", True)],
)

block = make_block(is_muted=True)
VideoBlock.mute_unmute(block, is_global=True)
c.check(
    "so a muted video unmutes the grid rather than flipping each one",
    block.commands.calls == [("set_muted", False)],
)

block = make_block(is_muted=False)
VideoBlock.mute_unmute(block)
c.check(
    "and the local mute is still a local one",
    block.video_driver.audio_set_mute.calls == [(True,)] and not block.commands.calls,
)

block = make_block()
block.video_params.is_paused = False
VideoBlock.play_pause(block, is_global=True)
c.check(
    "a global play/pause pauses the grid when this video plays",
    block.commands.calls == [("all_pause",)],
)

block = make_block()
block.video_params.is_paused = True
block.set_pause = Recorder()
VideoBlock.play_pause(block, is_global=True)
c.check(
    "and plays the grid when this video is paused",
    block.commands.calls == [("all_play",)],
)
c.check(
    "without setting this video by hand",
    not block.set_pause.calls,
)

block = make_block()
block.video_params.is_paused = True
block.set_pause = Recorder()
VideoBlock.play_pause(block)
c.check(
    "a plain play/pause still only touches this video",
    block.set_pause.calls == [(False,)] and not block.commands.calls,
)

# a point on a control belongs to the overlay, not to the video behind it


class OverlayStub:
    def __init__(self, over_control, in_dead_zone):
        self._over_control = over_control
        self._in_dead_zone = in_dead_zone

    def is_over_control(self, global_pos):
        return self._over_control

    def is_in_dead_zone(self, global_pos):
        return self._in_dead_zone


def over_stub(over_control, in_dead_zone):
    return SimpleNamespace(overlay=OverlayStub(over_control, in_dead_zone))


c.check(
    "a point on a control counts as the overlay",
    VideoBlock._is_over_overlay_controls(over_stub(True, False), QPoint(5, 5)),
)
c.check(
    "a point in the row's gaps still counts as the overlay",
    VideoBlock._is_over_overlay_controls(over_stub(False, True), QPoint(5, 5)),
)
c.check(
    "and a point on the video itself does not",
    not VideoBlock._is_over_overlay_controls(over_stub(False, False), QPoint(5, 5)),
)

block = make_block()
VideoBlock.set_repeat_mode(block, VideoRepeat.SINGLE_FILE, is_global=True)
c.check(
    "the play order is sent as an absolute mode",
    block.commands.calls == [("set_repeat_mode", VideoRepeat.SINGLE_FILE)],
)
c.check(
    "so this video is not moved to it first",
    block.video_params.repeat_mode
    if hasattr(block.video_params, "repeat_mode")
    else None is None,
)

block = make_block()
VideoBlock.set_repeat_mode(block, VideoRepeat.SINGLE_FILE)
c.check(
    "a local play-order change is written to this video",
    block.video_params.repeat_mode == VideoRepeat.SINGLE_FILE,
)

block = make_block()
VideoBlock.manual_seek(block, "seek_percent", 0.5, is_global=True)
c.check(
    "a global seek goes out through the manager's forced sync",
    block.sync_others_percent.calls == [()],
)
c.check(
    "and not through the ordinary sync",
    not block.sync_percent.calls and not block.sync_time.calls,
)

block = make_block()
block._ctx.seek_sync_mode = SeekSyncMode.TIMECODE
VideoBlock.manual_seek(block, "seek_percent", 0.5, is_global=True)
c.check(
    "in timecode sync mode the global seek speaks timecode",
    block.sync_others_time.calls == [()] and not block.sync_others_percent.calls,
)

block = make_block()
VideoBlock.manual_seek(block, "seek_percent", 0.5)
c.check(
    "a local seek still follows the playlist's own sync setting",
    not block.sync_others_percent.calls and not block.sync_others_time.calls,
)

# --- the manager's side ------------------------------------------------------

c.check(
    "the manager declares absolute volume and speed setters",
    hasattr(VideoBlocksManager, "all_set_volume")
    and hasattr(VideoBlocksManager, "all_set_rate"),
)


class ManagerStub:
    all_set_volume = Recorder()
    all_set_rate = Recorder()


manager = ManagerStub()
VideoBlocksManager.cmd_all(manager, "set_volume", 0.4)
VideoBlocksManager.cmd_all(manager, "set_rate", 2.0)
c.check(
    "and cmd_all turns a command name into that signal",
    manager.all_set_volume.calls == [(0.4,)] and manager.all_set_rate.calls == [(2.0,)],
)

source = (
    Path(__file__).resolve().parent.parent
    / "gridplayer"
    / "player"
    / "managers"
    / "video_blocks.py"
).read_text(encoding="utf-8")
c.check(
    "the two setters are wired to every block",
    "(self.all_set_volume, vb.set_volume)" in source
    and "(self.all_set_rate, vb.set_rate)" in source,
)

c.check(
    "and cmd_all is what fans a command out",
    'getattr(self, f"all_{command}").emit(*args)' in source,
)

# --- what must not have changed ----------------------------------------------

overlay_source = (
    Path(__file__).resolve().parent.parent
    / "gridplayer"
    / "widgets"
    / "video_overlay.py"
).read_text(encoding="utf-8")
c.check(
    "play/pause has a global twin as well",
    "play_pause_clicked_global = pyqtSignal()" in overlay_source,
)

block_source = (
    Path(__file__).resolve().parent.parent / "gridplayer" / "widgets" / "video_block.py"
).read_text(encoding="utf-8")


def method_source(text, name):
    start = text.index(f"def {name}(")
    end = text.find("\n    def ", start + 1)

    return text[start : end if end != -1 else len(text)]


c.check(
    "the video's right click defers to a control under it",
    "_is_over_overlay_controls(" in method_source(block_source, "contextMenuEvent"),
)
c.check(
    "and the control row is covered by the same predicate",
    "self.overlay.is_over_control("
    in method_source(block_source, "_is_over_overlay_controls"),
)

sent = set(re.findall(r'commands\.all\("(\w+)"', block_source))
c.check(
    "every name the block sends through cmd_all has a signal to land on",
    sent and all(hasattr(VideoBlocksManager, f"all_{name}") for name in sent),
    f"names={sorted(sent)}",
)
c.check(
    "and play/pause takes the manager's absolute commands instead",
    "commands.all_play()" in block_source and "commands.all_pause()" in block_source,
)
c.check(
    "which the manager really registers",
    '"all_play": self.cmd_all_play' in source
    and '"all_pause": self.cmd_all_pause' in source,
)
c.check(
    "the plain signals are all still there",
    all(
        f"{name} = pyqtSignal" in overlay_source
        for name in (
            "set_vid_pos",
            "set_volume",
            "mute_unmute_clicked",
            "repeat_mode_changed",
            "speed_selected",
        )
    ),
)

c.finish()
