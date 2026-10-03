"""Item 3: the single-mode overlay tab strip.

Covers four layers:
  * the tab widgets in both looks (labels, geometry, click zones, rebuilds)
  * the merged look really merging into the video name bar
  * the single-mode manager's tab payload, style switch and switch-to-video
  * the wiring between them (player.py connection table + signal names)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("tab bar")

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import Commands, Context, ManagersManager
from gridplayer.player.managers.single_mode import SingleModeManager, _tab_label
from gridplayer.player.managers.video_blocks import VideoBlocks, VideoBlocksManager
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_tabs import (
    STYLE_BAR,
    STYLE_MERGED,
    OverlayTab,
    OverlayTabBar,
)

# nothing here is ever shown: a hidden host keeps setVisible() from turning an
# orphan widget into a real top level window on the user's desktop
HOST = QWidget()

THREE = [("a", "aaa.mp4"), ("b", "bbb.mp4"), ("c", "ccc.mp4")]


def use_style(style):
    Settings().set("misc/tab_style", style)


def mouse_event(event_type, pos):
    return QMouseEvent(
        event_type, QPointF(*pos), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
    )


def click(widget, pos):
    widget.mousePressEvent(mouse_event(QEvent.MouseButtonPress, pos))
    widget.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, pos))


def at(bar, block_id):
    return {t.block_id: t for t in bar.tabs}[block_id]


# --- 1. the plain look ------------------------------------------------------

use_style(STYLE_BAR)

bar = OverlayTabBar(parent=HOST)

c.check("empty payload hides the strip", (bar.set_tabs([], None), bar.isHidden())[1])

bar.set_tabs(THREE, "b")

c.check(
    "one tab per video",
    len(bar.findChildren(OverlayTab)) == 3,
    f"{len(bar.findChildren(OverlayTab))} tabs",
)
c.check("strip is shown once there is a current video", not bar.isHidden())
c.check(
    "exactly one tab is marked current",
    [t.is_current for t in bar.tabs] == [False, True, False],
)

c.check(
    "every tab carries its filename in the plain look",
    [t._label for t in bar.tabs] == ["aaa.mp4", "bbb.mp4", "ccc.mp4"],
    f"{[t._label for t in bar.tabs]}",
)
c.check(
    "the current tab is the accent one",
    at(bar, "b").colors()[0] == at(bar, "b").color_contrast_mid,
)
c.check(
    "the other tabs are painted on the light background",
    at(bar, "a").colors()[0] == at(bar, "a").color,
)
c.check(
    "every tab identifies itself in the tooltip", at(bar, "b").toolTip() == "bbb.mp4"
)

# --- 2. geometry ------------------------------------------------------------

short = OverlayTab("s", "s.mp4", False, STYLE_BAR, parent=HOST)
long_ = OverlayTab("l", "l" * 60 + ".mp4", False, STYLE_BAR, parent=HOST)
blank = OverlayTab("bl", "b.mp4", True, STYLE_MERGED, parent=HOST)

c.check(
    "a longer filename asks for a wider tab",
    long_.sizeHint().width() > short.sizeHint().width(),
    f"{short.sizeHint().width()} -> {long_.sizeHint().width()}",
)
c.check(
    "tab width is capped",
    long_.sizeHint().width() == long_.maximumWidth(),
    f"{long_.sizeHint().width()}px",
)

use_style(STYLE_MERGED)
c.check(
    "in the merged look the tab on screen carries no filename",
    blank._label == "",
    repr(blank._label),
)
c.check(
    "and collapses back to the minimum width",
    blank.sizeHint().width() == blank.minimumWidth(),
    f"{blank.sizeHint().width()}px",
)

c.check(
    "the merged tab on screen is taller than the others",
    OverlayTab("x", "x.mp4", True, STYLE_MERGED, parent=HOST).height()
    > OverlayTab("y", "y.mp4", False, STYLE_MERGED, parent=HOST).height(),
)

use_style(STYLE_BAR)

# --- 3. click zones ---------------------------------------------------------

tab_a = at(bar, "a")
tab_a.resize(tab_a.sizeHint())

activated = []
closed = []
tab_a.activated.connect(activated.append)
tab_a.close_clicked.connect(closed.append)

c.check(
    "a real tab got a real width",
    tab_a.width() > tab_a.close_rect().width(),
    f"{tab_a.width()}px",
)

click(tab_a, (tab_a.width() // 2 - 6, tab_a.height() // 2))
c.check(
    "clicking the body asks to switch to that video", activated == ["a"], f"{activated}"
)
c.check("clicking the body does not close anything", closed == [])

close_center = tab_a.close_rect().center()
click(tab_a, (close_center.x(), close_center.y()))
c.check("clicking the x asks to close that video", closed == ["a"], f"{closed}")
c.check("the x did not also trigger a switch", activated == ["a"])

press = mouse_event(QEvent.MouseButtonPress, (tab_a.width() // 2, 5))
tab_a.mousePressEvent(press)
c.check(
    "a press on a tab is consumed, so it cannot reach the block and toggle playback",
    press.isAccepted(),
)

dbl = mouse_event(QEvent.MouseButtonDblClick, (tab_a.width() // 2, 5))
tab_a.mouseDoubleClickEvent(dbl)
c.check(
    "a double click on a tab is consumed, so it cannot trigger fullscreen",
    dbl.isAccepted(),
)

# --- 4. rebuild behaviour ---------------------------------------------------

kept = bar.tabs
bar.set_tabs(THREE, "b")
c.check("an unchanged payload is not rebuilt", bar.tabs == kept)

bar.set_tabs(THREE, "a")
c.check("a changed payload is rebuilt", len(bar.tabs) == 3)
c.check(
    "rebuilt strip marks the new current tab",
    [t.is_current for t in bar.tabs] == [True, False, False],
)

use_style(STYLE_MERGED)
bar.set_tabs(THREE, "a")
c.check(
    "switching look rebuilds even though the payload is the same",
    bar.style == STYLE_MERGED and at(bar, "a")._label == "",
    f"style={bar.style} label={at(bar, 'a')._label!r}",
)

use_style(STYLE_BAR)
bar.set_tabs(THREE, "a")
c.check(
    "switching back restores the filenames",
    bar.style == STYLE_BAR and at(bar, "a")._label == "aaa.mp4",
)

bar.set_tabs([], None)
c.check("closing single mode hides the strip again", bar.isHidden())

# --- 5. the merged look really merges ---------------------------------------

use_style(STYLE_MERGED)

host = QWidget()
host.resize(900, 200)

merged_overlay = OverlayBlock(parent=host)
merged_overlay.setGraphicsEffect(None)
merged_overlay.set_label("bbb.mp4")
merged_overlay.set_tabs(THREE, "b")

# the overlay has to be given a size before its layouts will produce anything,
# and grab() is what forces the whole tree - including the tab bar's own layout -
# to settle. Nothing is shown, so this draws offscreen only.
merged_overlay.resize(900, 200)
merged_overlay.layout().activate()
merged_overlay.control_widget.layout().activate()
merged_overlay.grab()

merged_bar = merged_overlay.tab_bar
merged_tab = at(merged_bar, "b")
other_tab = at(merged_bar, "a")

c.check("merged strip is shown", not merged_bar.isHidden())

merged_bottom = merged_tab.mapTo(merged_overlay, QPoint(0, merged_tab.height())).y()
name_top = merged_overlay.label_text.mapTo(merged_overlay, QPoint(0, 0)).y()

c.check(
    "the tab on screen grows straight out of the name bar",
    merged_bottom == name_top,
    f"tab ends at {merged_bottom}, bar starts at {name_top}",
)
c.check(
    "and is painted in the very same colour as that bar",
    merged_tab.colors()[0] == merged_overlay.label_text.color,
    f"{merged_tab.colors()[0].name()} vs {merged_overlay.label_text.color.name()}",
)

other_bottom = other_tab.mapTo(merged_overlay, QPoint(0, other_tab.height())).y()

c.check(
    "the other tabs share the same bottom line",
    other_bottom == merged_bottom,
    f"{other_bottom} vs {merged_bottom}",
)
c.check(
    "but sit lower, i.e. behind",
    other_tab.mapTo(merged_overlay, QPoint(0, 0)).y()
    > merged_tab.mapTo(merged_overlay, QPoint(0, 0)).y(),
)

# --- 6. OverlayBlock plumbing -----------------------------------------------

overlay = OverlayBlock(parent=HOST)
seen = []
overlay.tab_activated.connect(seen.append)
styles_seen = []
overlay.tab_style_changed.connect(styles_seen.append)

c.check("overlay starts with a hidden tab bar", overlay.tab_bar.isHidden())

overlay.set_tabs([("a", "a.mp4"), ("b", "b.mp4")], "a")
c.check("overlay forwards the payload to its tab bar", not overlay.tab_bar.isHidden())

overlay.tab_bar.tab_activated.emit("b")
c.check("tab activation reaches the overlay's own signal", seen == ["b"], f"{seen}")

c.check(
    "the video name bar offers the tab style switch",
    hasattr(overlay.label_text, "tab_style_selected"),
)

overlay.label_text.tab_style_selected.emit(STYLE_MERGED)
c.check(
    "and that reaches the overlay's own signal",
    styles_seen == [STYLE_MERGED],
    f"{styles_seen}",
)

c.check(
    "overlay announces tab signals for the block to forward",
    all(
        hasattr(OverlayBlock, n)
        for n in ("tab_activated", "tab_closed", "tab_style_changed")
    ),
)
c.check(
    "block announces tab signals for the manager to forward",
    all(
        hasattr(VideoBlock, n)
        for n in ("tab_activated", "tab_closed", "tab_style_changed")
    ),
)
c.check(
    "block exposes set_tabs for the manager's fan-out",
    callable(getattr(VideoBlock, "set_tabs", None)),
)

# --- 7. single mode payload -------------------------------------------------

stub_win = QWidget()


def build_blocks(states):
    """states: list of (id, uri, is_visible)"""

    blocks = VideoBlocks()

    for block_id, uri, is_visible in states:
        block = type("StubBlock", (), {})()
        block.id = block_id
        block.video_params = type("StubParams", (), {"uri": uri, "is_paused": False})()
        block.title = f"title-{block_id}"
        block.isVisible = (lambda v: (lambda: v))(is_visible)
        blocks.append(block)

    return blocks


ctx = Context()
ctx.commands = Commands()
ctx.active_block = None
ctx.last_active_block = None
ctx.video_blocks = build_blocks(
    [
        ("a", Path(r"C:\videos\bunny.mp4"), False),
        ("b", Path(r"C:\videos\other.mkv"), True),
    ]
)

sm = SingleModeManager(context=ctx, parent=stub_win)

c.check(
    "no strip while not in single mode",
    sm._tabs_payload() == ([], None),
    f"{sm._tabs_payload()}",
)

ctx.is_single_mode = True

tabs_payload, current_id = sm._tabs_payload()
c.check(
    "strip lists every video",
    [t[0] for t in tabs_payload] == ["a", "b"],
    f"{tabs_payload}",
)
c.check(
    "filenames keep their extension",
    [t[1] for t in tabs_payload] == ["bunny.mp4", "other.mkv"],
)
c.check("the visible block is the current one", current_id == "b", f"{current_id}")

c.check(
    "local file label comes from the uri",
    _tab_label(ctx.video_blocks[0]) == "bunny.mp4",
)

non_local = type("StubBlock", (), {})()
non_local.video_params = type("StubParams", (), {"uri": None})()
non_local.title = "Some Stream"
c.check(
    "non-file label falls back to the title",
    _tab_label(non_local) == "Some Stream",
    _tab_label(non_local),
)

# --- 8. switching to a tab's video ------------------------------------------

switches = []
sm._activate_single_video = lambda cur, nxt: switches.append((cur.id, nxt.id))

sm.switch_to_single_video("a")
c.check(
    "clicking a tab switches to that block", switches == [("b", "a")], f"{switches}"
)

switches.clear()
sm.switch_to_single_video("b")
c.check("clicking the current tab does nothing", switches == [])

switches.clear()
sm.switch_to_single_video("nope")
c.check("an unknown block id does nothing", switches == [])

ctx.is_single_mode = False
switches.clear()
sm.switch_to_single_video("a")
c.check("switching is refused outside single mode", switches == [])

# next/previous must keep working through the same shared helper
ctx.is_single_mode = True
ctx.video_blocks[0].isVisible = lambda: False
ctx.video_blocks[1].isVisible = lambda: True

switches.clear()
sm.next_single_video()
c.check("next wraps around", switches == [("b", "a")], f"{switches}")

switches.clear()
sm.previous_single_video()
c.check("previous wraps around", switches == [("b", "a")], f"{switches}")

# --- 9. the style switch ----------------------------------------------------

pushed = []
sm.tabs_changed.connect(lambda tabs, cid: pushed.append((tabs, cid)))

use_style(STYLE_BAR)
sm.set_tab_style(STYLE_MERGED)
c.check(
    "the chosen look is stored",
    Settings().get("misc/tab_style") == STYLE_MERGED,
    Settings().get("misc/tab_style"),
)
c.check("and the strip is pushed again", len(pushed) == 1, f"{pushed}")

pushed.clear()
sm.set_tab_style("nonsense")
c.check(
    "an unknown look is refused",
    Settings().get("misc/tab_style") == STYLE_MERGED and pushed == [],
)

sm.set_tab_style(STYLE_BAR)
c.check("and it can be switched back", Settings().get("misc/tab_style") == STYLE_BAR)

# --- 10. closing a video from a tab -----------------------------------------

closer_win = QWidget()
vbm = VideoBlocksManager(context=Context(), parent=closer_win)

closed_ids = []


def make_closable(block_id):
    block = type("StubBlock", (), {})()
    block.id = block_id
    block.close = (lambda i: (lambda: closed_ids.append(i)))(block_id)
    return block


vbm._ctx.video_blocks.append(make_closable("a"))
vbm._ctx.video_blocks.append(make_closable("b"))

vbm.close_video("b")
c.check(
    "the x closes the block the tab points at", closed_ids == ["b"], f"{closed_ids}"
)

vbm.close_video("gone")
c.check("an unknown block id closes nothing", closed_ids == ["b"])

# --- 11. wiring -------------------------------------------------------------

player_src = (
    Path(__file__).resolve().parent.parent / "gridplayer" / "player" / "player.py"
).read_text(encoding="utf-8")

for entry in (
    '("tabs_changed", "video_blocks.set_tabs")',
    '("tab_activated_forward", "single_mode.switch_to_single_video")',
    '("tab_closed_forward", "video_blocks.close_video")',
    '("tab_style_changed_forward", "single_mode.set_tab_style")',
):
    c.check(f"player.py wires {entry}", entry in player_src)

# resolve those very strings the way ManagersManager does, so a renamed signal
# or method is caught here rather than at runtime
wiring_win = QWidget()
wiring_ctx = Context()
wiring_ctx.commands = Commands()
wiring_ctx.active_block = None
wiring_ctx.video_blocks = VideoBlocks()


class _Resolver(ManagersManager):
    pass


resolver = _Resolver()
resolver._managers_inst = {
    "single_mode": SingleModeManager(context=wiring_ctx, parent=wiring_win),
    "video_blocks": VideoBlocksManager(context=wiring_ctx, parent=wiring_win),
}

resolved = []
for c_manager, c_sig, c_slot in (
    ("single_mode", "tabs_changed", "video_blocks.set_tabs"),
    ("video_blocks", "tab_activated_forward", "single_mode.switch_to_single_video"),
    ("video_blocks", "tab_closed_forward", "video_blocks.close_video"),
    ("video_blocks", "tab_style_changed_forward", "single_mode.set_tab_style"),
):
    try:
        sig = resolver._get_manager_function(c_manager, c_sig)
        slot = resolver._get_manager_function(c_manager, c_slot)
        sig.connect(slot)
        resolved.append(True)
    except Exception as e:  # noqa: BLE001 - report whatever went wrong
        resolved.append(f"{type(e).__name__}: {e}")

c.check(
    "every new connection resolves and connects",
    resolved == [True, True, True, True],
    f"{resolved}",
)

# --- 12. end to end through the manager signals -----------------------------

fanout = []

fanout_block = type("StubBlock", (), {})()
fanout_block.set_tabs = lambda tabs, cid: fanout.append((tabs, cid))
wiring_ctx.video_blocks.append(fanout_block)

resolver._managers_inst["single_mode"]._update_tabs()
c.check("the manager's signal reaches the fan-out", fanout == [([], None)], f"{fanout}")

# --- 13. tab click -> switch, x click -> close, end to end ------------------

e2e_win = QWidget()
e2e_ctx = Context()
e2e_ctx.commands = Commands()
e2e_ctx.active_block = None

e2e = _Resolver()
e2e._managers_inst = {
    # both managers build their own state, and VideoBlocksManager *replaces*
    # ctx.video_blocks, so the blocks have to go in afterwards
    "single_mode": SingleModeManager(context=e2e_ctx, parent=e2e_win),
    "video_blocks": VideoBlocksManager(context=e2e_ctx, parent=e2e_win),
}

for c_manager, c_sig, c_slot in (
    ("video_blocks", "tab_activated_forward", "single_mode.switch_to_single_video"),
    ("video_blocks", "tab_closed_forward", "video_blocks.close_video"),
):
    sig = e2e._get_manager_function(c_manager, c_sig)
    slot = e2e._get_manager_function(c_manager, c_slot)
    sig.connect(slot)

for block in build_blocks(
    [
        ("a", Path(r"C:\videos\a.mp4"), True),
        ("b", Path(r"C:\videos\b.mp4"), False),
    ]
):
    e2e_ctx.video_blocks.append(block)

e2e_ctx.is_single_mode = True

e2e_switches = []
e2e._managers_inst["single_mode"]._activate_single_video = (
    lambda cur, nxt: e2e_switches.append((cur.id, nxt.id))
)

e2e._managers_inst["video_blocks"].tab_activated_forward.emit("b")
c.check(
    "a tab click on the block side switches the video",
    e2e_switches == [("a", "b")],
    f"{e2e_switches}",
)

e2e_closed = []
e2e_ctx.video_blocks[1].close = lambda: e2e_closed.append("b")

e2e._managers_inst["video_blocks"].tab_closed_forward.emit("b")
c.check(
    "an x click on the block side closes the video",
    e2e_closed == ["b"],
    f"{e2e_closed}",
)

seen_overlay = []

widget_overlay = OverlayBlock(parent=HOST)
widget_overlay.tab_activated.connect(seen_overlay.append)
widget_overlay.set_tabs([("a", "a.mp4"), ("b", "b.mp4")], "a")

clicked_tab = at(widget_overlay.tab_bar, "b")
clicked_tab.resize(clicked_tab.sizeHint())
click(clicked_tab, (clicked_tab.width() // 2, clicked_tab.height() // 2))

c.check(
    "clicking a real tab widget raises the activation signal",
    seen_overlay == ["b"],
    f"{seen_overlay}",
)

# --- 14. what the tabs actually paint ---------------------------------------

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREY_MID = (155, 155, 155)


def count_near(img, rect, rgb, tol=40):
    found = 0

    for y in range(max(rect.top(), 0), min(rect.bottom(), img.height() - 1) + 1):
        for x in range(max(rect.left(), 0), min(rect.right(), img.width() - 1) + 1):
            col = img.pixelColor(x, y)
            if (
                abs(col.red() - rgb[0]) <= tol
                and abs(col.green() - rgb[1]) <= tol
                and abs(col.blue() - rgb[2]) <= tol
            ):
                found += 1

    return found


use_style(STYLE_BAR)

paint_bar = OverlayTabBar(parent=HOST)
paint_bar.set_tabs([("plain", "movie.mp4"), ("cur", "current.mp4")], "cur")

plain_tab = at(paint_bar, "plain")
cur_tab = at(paint_bar, "cur")

for t in (plain_tab, cur_tab):
    t.resize(t.sizeHint())

plain_img = plain_tab.grab().toImage()
cur_img = cur_tab.grab().toImage()

c.check(
    "a normal tab is painted on the light background",
    count_near(plain_img, plain_img.rect(), WHITE) > 200,
    f"{count_near(plain_img, plain_img.rect(), WHITE)} white px",
)
c.check(
    "a normal tab draws its x in the dark foreground",
    count_near(plain_img, plain_tab.close_rect(), BLACK) >= 8,
    f"{count_near(plain_img, plain_tab.close_rect(), BLACK)} dark px in the x zone",
)
c.check(
    "a normal tab draws its filename",
    count_near(plain_img, plain_tab.text_rect(), BLACK) >= 20,
    f"{count_near(plain_img, plain_tab.text_rect(), BLACK)} text px",
)

c.check(
    "the current tab is painted on the accent background",
    count_near(cur_img, cur_img.rect(), GREY_MID) > 200,
    f"{count_near(cur_img, cur_img.rect(), GREY_MID)} grey px",
)
c.check(
    "the current tab draws its filename too, in the plain look",
    count_near(cur_img, cur_tab.text_rect(), WHITE) >= 20,
    f"{count_near(cur_img, cur_tab.text_rect(), WHITE)} text px",
)
c.check(
    "the current tab carries the left accent stripe",
    count_near(cur_img, cur_img.rect().adjusted(0, 0, -cur_img.width() + 3, 0), WHITE)
    >= 3 * 20,
    "px in the stripe",
)

hover_tab = plain_tab
hover_tab._is_close_hovered = True
hover_img = hover_tab.grab().toImage()

c.check(
    "hovering the x paints a dark close box",
    count_near(hover_img, hover_tab.close_rect(), BLACK) > 100,
    f"{count_near(hover_img, hover_tab.close_rect(), BLACK)} dark px",
)
c.check(
    "the hovered x is drawn light, so it stays visible",
    count_near(hover_img, hover_tab.close_rect(), WHITE) >= 8,
    f"{count_near(hover_img, hover_tab.close_rect(), WHITE)} light px",
)

# the merged look must really be a trapezoid: cut corners, full width at the
# bottom edge that meets the name bar
use_style(STYLE_MERGED)

merge_bar = OverlayTabBar(parent=HOST)
merge_bar.set_tabs([("a", "aaa.mp4"), ("b", "bbb.mp4")], "b")

merge_cur = at(merge_bar, "b")
merge_cur.resize(merge_cur.sizeHint())

merge_img = merge_cur.grab().toImage()
merge_w = merge_cur.width()
merge_h = merge_cur.height()

c.check(
    "the merged tab is not a rectangle: its top corners are cut away",
    merge_img.pixelColor(1, 1).name() != "#ffffff"
    and merge_img.pixelColor(merge_w - 2, 1).name() != "#ffffff",
    f"left {merge_img.pixelColor(1, 1).name()}, "
    f"right {merge_img.pixelColor(merge_w - 2, 1).name()}",
)
c.check(
    "but it is full width where it meets the name bar",
    merge_img.pixelColor(1, merge_h - 2).name() == "#ffffff"
    and merge_img.pixelColor(merge_w - 2, merge_h - 2).name() == "#ffffff",
    f"left {merge_img.pixelColor(1, merge_h - 2).name()}, "
    f"right {merge_img.pixelColor(merge_w - 2, merge_h - 2).name()}",
)
c.check(
    "and is filled in between",
    merge_img.pixelColor(merge_w // 2, merge_h // 2).name() == "#ffffff",
)

merge_other = at(merge_bar, "a")
merge_other.resize(merge_other.sizeHint())

other_img = merge_other.grab().toImage()

c.check(
    "the other tabs are the dark ones in the merged look",
    count_near(other_img, other_img.rect(), GREY_MID) > 200,
    f"{count_near(other_img, other_img.rect(), GREY_MID)} grey px",
)
c.check(
    "their filename is drawn light",
    count_near(other_img, merge_other.text_rect(), WHITE) >= 20,
    f"{count_near(other_img, merge_other.text_rect(), WHITE)} text px",
)

use_style(STYLE_BAR)

# --- 15. the floating overlay's opaque mask ---------------------------------
#
# The floating overlay is a separate top level window. In opaque mode it builds
# a paint mask out of its OverlayWidget children, and a tab is a child of the
# tab bar rather than of the overlay, so the mask has to map its geometry up.

from PyQt5.QtCore import QRect

from gridplayer.widgets.video_overlay import OverlayBlockFloating

mask_host = QWidget()
mask_host.setAttribute(Qt.WA_DontShowOnScreen, True)
mask_host.resize(400, 200)

float_ov = OverlayBlockFloating(parent=mask_host)
float_ov.setAttribute(Qt.WA_DontShowOnScreen, True)
float_ov.setGraphicsEffect(None)

mask_host.show()
float_ov.show()

float_ov.is_opaque = True
float_ov.set_tabs([("a", "a.mp4"), ("b", "b.mp4")], "a")

float_ov.paintEvent(None)
regions = float_ov.mask()

float_tab = at(float_ov.tab_bar, "a")
float_bar_origin = float_ov.tab_bar.mapTo(float_ov, QPoint(0, 0))
float_tab_origin = float_tab.mapTo(float_ov, QPoint(0, 0))

# NB: QRegion.contains(QRect) is not usable here - on a union region Qt reported
# a small rect as contained while its own top-left QPoint was not in the region.
# Probe single points instead.
real = QRect(float_tab_origin, float_tab.size())

# where the pre-fix code would have painted it: child.pos(), i.e. relative to
# the tab bar rather than to the overlay
misplaced = QRect(float_tab.pos(), float_tab.size())

miss_probe = QPoint(float_tab.x() + 1, float_tab.y() + float_tab.height() // 2)
gap_probe = QPoint(real.center().x(), float_bar_origin.y() - 6)

c.check("the floating overlay shows its tab bar", not float_ov.tab_bar.isHidden())
c.check(
    "the tab bar is inset from the overlay edge",
    float_bar_origin.y() >= 6,
    f"bar at {float_bar_origin.x()},{float_bar_origin.y()}",
)
c.check(
    "the pre-fix position really is a different place",
    misplaced.contains(miss_probe) and not real.contains(miss_probe),
    f"probe {miss_probe.x()},{miss_probe.y()} real={real} misplaced={misplaced}",
)
c.check(
    "the opaque mask paints the tab where it actually is",
    regions.contains(real.center()),
    f"centre {real.center().x()},{real.center().y()}",
)
c.check(
    "the opaque mask leaves the empty margin above the tab bar alone",
    not regions.contains(gap_probe),
    f"probe {gap_probe.x()},{gap_probe.y()}",
)
c.check(
    "the opaque mask does not paint the tab at its bar-relative position",
    not regions.contains(miss_probe),
    f"probe {miss_probe.x()},{miss_probe.y()}",
)

float_ov.hide()
mask_host.hide()

c.finish()
