# P2：播放顺序按钮 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在播放条右侧加一个按钮，左键单击循环切换该格视频的播放顺序（列表循环 / 单集循环 / 随机播放 / 播完暂停），图标随之变化。

**Architecture:** 上游 `VideoRepeat` 只有三态，先补上第四态 `PAUSE_AT_END` 并让它真的生效；然后照抄上游已有的 overlay 按钮模式（`OverlayButton` 子类 + `QPainter` 手绘图标 + `qt_connect` 接线）加一个 `OverlayRepeatButton`，由 `VideoBlock` 的 per-block `set_repeat_mode` 驱动。

**Tech Stack:** Python 3.13.5 / PyQt5 5.15.11 / Qt 5.15.2 / `QPainter` 手绘图标 / 纯脚本断言

**Spec:** `<repo>\docs\specs\2026-10-02-playlist-panel-design.md` 的 §4.5

## Global Constraints

- 只改 `<repo>\app\gridplayer\` 下的文件；每处改动必须带 `# MOD:` 注释。
- 测试必须用 `<repo>\pyenv\Scripts\python.exe`，不引入新依赖；失败 `sys.exit(非0)`。
- 测试必须设 `GRIDPLAYER_DATA_DIR` 到临时目录（用 `tests._harness.bootstrap()`），不得污染 `<repo>\data`。
- 图标必须沿用 `video_overlay_icons.py` 现有签名 `draw_xxx(rect, painter, color_fg, color_bg)`，不要引入图片资源文件。
- 每个任务结束时，`_runtests.py` 与 `_selftest.py` 都必须全绿。
- **按钮作用范围仅该格**，不要用 `all_set_repeat_mode`。
- **默认仍是列表循环**：用户当前配置 `video_defaults/repeat=dir`，不要改动这个设置的默认值。

---

### Task 1: 第四态 `PAUSE_AT_END` 落地

**Files:**
- Modify: `app/gridplayer/params/static.py`（枚举 + 循环顺序 helper）
- Modify: `app/gridplayer/widgets/video_block.py:670-681`（`loop_end_action`）
- Modify: `app/gridplayer/dialogs/settings.py:306-312`（下拉项）
- Modify: `app/gridplayer/params/actions.py:301` 之后、`:942` 之后（右键菜单两条）
- Create: `tests/test_repeat_mode.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `gridplayer.params.static.VideoRepeat.PAUSE_AT_END`（字符串值 `"pause_at_end"`）
  - `gridplayer.params.static.next_video_repeat(mode: VideoRepeat) -> VideoRepeat`
  - `gridplayer.params.static.VIDEO_REPEAT_CYCLE: tuple[VideoRepeat, ...]`（顺序：`DIR, SINGLE_FILE, DIR_SHUFFLE, PAUSE_AT_END`）

- [ ] **Step 1: 写测试**

`tests/test_repeat_mode.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("repeat mode")

from gridplayer.params.static import (
    VIDEO_REPEAT_CYCLE,
    VideoRepeat,
    next_video_repeat,
)

# --- the new member exists and serialises as expected ---
c.check("PAUSE_AT_END exists", hasattr(VideoRepeat, "PAUSE_AT_END"))
c.check("PAUSE_AT_END value", VideoRepeat.PAUSE_AT_END.value == "pause_at_end")

# --- old config values still parse (backward compatibility) ---
for raw, expected in (
    ("single_file", VideoRepeat.SINGLE_FILE),
    ("dir", VideoRepeat.DIR),
    ("dir_shuffle", VideoRepeat.DIR_SHUFFLE),
    ("pause_at_end", VideoRepeat.PAUSE_AT_END),
):
    c.check(f"parses {raw!r}", VideoRepeat(raw) is expected)

# --- cycle order: default (list loop) first, then a full loop back to it ---
c.check("cycle starts at DIR (list loop)", VIDEO_REPEAT_CYCLE[0] is VideoRepeat.DIR)
c.check("cycle covers all four modes", len(VIDEO_REPEAT_CYCLE) == 4)
c.check("cycle has no duplicates", len(set(VIDEO_REPEAT_CYCLE)) == 4)

seen = [VIDEO_REPEAT_CYCLE[0]]
mode = VIDEO_REPEAT_CYCLE[0]
for _ in range(3):
    mode = next_video_repeat(mode)
    seen.append(mode)
c.check("four clicks walk every mode",
        set(seen) == set(VIDEO_REPEAT_CYCLE), f"{[m.value for m in seen]}")
c.check("fifth click returns to the start",
        next_video_repeat(seen[-1]) is VIDEO_REPEAT_CYCLE[0])

# --- settings round-trip through the real Settings machinery ---
from gridplayer.settings import Settings

Settings().set("video_defaults/repeat", VideoRepeat.PAUSE_AT_END)
Settings().sync()
c.check("PAUSE_AT_END round-trips through settings",
        Settings().get("video_defaults/repeat") is VideoRepeat.PAUSE_AT_END,
        f"{Settings().get('video_defaults/repeat')}")

# --- a Video model built with no explicit repeat picks the configured default ---
from gridplayer.models.video import Video

v = Video(uri=Path("E:/x.mp4"))
c.check("new Video inherits the configured repeat mode",
        v.repeat_mode is VideoRepeat.PAUSE_AT_END, f"{v.repeat_mode}")

c.finish()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_repeat_mode.py`
Expected: FAIL — `ImportError: cannot import name 'VIDEO_REPEAT_CYCLE'`

- [ ] **Step 3: 实现枚举与循环 helper**

`app/gridplayer/params/static.py`，把 `VideoRepeat` 改成：

```python
class VideoRepeat(AutoName):
    SINGLE_FILE = auto()
    DIR = auto()
    DIR_SHUFFLE = auto()
    # MOD: play to the end, then stay paused - no loop, no next file
    PAUSE_AT_END = auto()


# MOD: click order for the overlay repeat button. List loop first because it is
# the default mode (video_defaults/repeat = dir).
VIDEO_REPEAT_CYCLE = (
    VideoRepeat.DIR,
    VideoRepeat.SINGLE_FILE,
    VideoRepeat.DIR_SHUFFLE,
    VideoRepeat.PAUSE_AT_END,
)


def next_video_repeat(mode: VideoRepeat) -> VideoRepeat:
    """MOD: the mode after `mode` in the overlay button's click order."""
    try:
        idx = VIDEO_REPEAT_CYCLE.index(mode)
    except ValueError:
        return VIDEO_REPEAT_CYCLE[0]

    return VIDEO_REPEAT_CYCLE[(idx + 1) % len(VIDEO_REPEAT_CYCLE)]
```

- [ ] **Step 4: 让第四态真的生效**

`app/gridplayer/widgets/video_block.py` 的 `loop_end_action`（约 670-681 行）：

```python
    def loop_end_action(self):
        is_single_file = self.video_params.repeat_mode == VideoRepeat.SINGLE_FILE

        if self.video_params.loop_end is not None or is_single_file:
            if self.video_params.is_start_random:
                self.seek_random()
            else:
                self.seek(self.loop_start)
        elif self.video_params.repeat_mode == VideoRepeat.DIR:
            self.next_video()
        elif self.video_params.repeat_mode == VideoRepeat.DIR_SHUFFLE:
            self.shuffle_video()
        # MOD: VideoRepeat.PAUSE_AT_END intentionally falls through - the media
        # ends and stays paused, which is exactly what that mode means.
        # Explicit loop_end still wins, as it did before this change.
```

- [ ] **Step 5: 补设置对话框与右键菜单**

`app/gridplayer/dialogs/settings.py`，`repeat_modes` 字典（约 306-312 行）加一项：

```python
        repeat_modes = {
            VideoRepeat.SINGLE_FILE: self.tr("Single File"),
            VideoRepeat.DIR: self.tr("Directory"),
            VideoRepeat.DIR_SHUFFLE: self.tr("Directory (Shuffle)"),
            VideoRepeat.PAUSE_AT_END: self.tr("Play Once (Pause at End)"),  # MOD
        }
```

`app/gridplayer/params/actions.py`，在 `"Repeat Directory (Shuffle)": {...}`（约 291-301 行）之后插入：

```python
        # MOD: fourth repeat mode
        "Repeat Once": {
            "title": translate("Actions", "Play Once (Pause at End)"),
            "icon": "loop-once",
            "func": ("active", "set_repeat_mode", VideoRepeat.PAUSE_AT_END),
            "check_if": (
                "is_active_param_set_to",
                "repeat_mode",
                VideoRepeat.PAUSE_AT_END,
            ),
            "show_if": "is_active_local_file",
        },
```

并在 `"Repeat Directory (Shuffle) [ALL]": {...}`（约 937-942 行）之后插入：

```python
        # MOD: fourth repeat mode, applied to every block
        "Repeat Once [ALL]": {
            "title": translate("Actions", "Play Once (Pause at End)"),
            "icon": "loop-once",
            "func": ("all", "set_repeat_mode", VideoRepeat.PAUSE_AT_END),
            "show_if": "is_any_videos_local_file",
        },
```

- [ ] **Step 6: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_repeat_mode.py`
Expected: PASS — `15/15 checks passed`

- [ ] **Step 7: 确认菜单能建起来**（`icon` 名写错、重复快捷键都会在这里炸）

`tests/test_repeat_mode.py` 追加：

```python
# --- the action table is still self-consistent after adding two entries ---
import gridplayer.params.actions as actions_module

c2 = Checker("actions table")
titles = list(actions_module.ACTIONS.keys())
c2.check("Repeat Once registered", "Repeat Once" in titles)
c2.check("Repeat Once [ALL] registered", "Repeat Once [ALL]" in titles)
keys = [c["key"] for c in actions_module.ACTIONS.values() if c.get("key")]
c2.check("no duplicate shortcuts introduced", len(keys) == len(set(keys)))
```

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_repeat_mode.py`
Expected: PASS — 若 `'Repeat Once' not in titles`，说明 `ACTIONS` 的变量名不是 `ACTIONS`，
用 `grep -n "^ACTIONS" app/gridplayer/params/actions.py` 找到真实名字后改测试。

- [ ] **Step 8: 全量测试 + 回归**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 2: 四个图标 + 顺序按钮

**Files:**
- Modify: `app/gridplayer/widgets/video_overlay_icons.py`（追加绘制函数）
- Modify: `app/gridplayer/widgets/video_overlay_buttons.py`（追加按钮类）
- Modify: `app/gridplayer/widgets/video_overlay.py`（加按钮、加信号、加 slot）
- Modify: `app/gridplayer/widgets/video_block.py`（接线 + 切换方法 + 初始化推送）
- Create: `tests/test_repeat_button.py`

**Interfaces:**
- Consumes: Task 1 的 `VideoRepeat.PAUSE_AT_END`、`next_video_repeat`
- Produces:
  - `video_overlay_icons.draw_menu / draw_repeat_single / draw_repeat_list / draw_repeat_shuffle / draw_repeat_pause`
  - `video_overlay_buttons.OverlayRepeatButton`，属性 `repeat_mode: VideoRepeat`（setter 会刷新 tooltip 与重绘）
  - `video_overlay.OverlayBlock.repeat_clicked = pyqtSignal()`、`OverlayBlock.set_repeat_mode(mode)` slot
  - `video_block.VideoBlock.repeat_mode_change = pyqtSignal(VideoRepeat)`
  - **不新增** `VideoBlock.switch_repeat_mode()`：推进逻辑在按钮内部（`OverlayRepeatButton._advance`），
    `VideoBlock` 只负责把收到的模式写回 `video_params` 并广播出去

- [ ] **Step 1: 写测试**（不测像素，测接线与状态机）

`tests/test_repeat_button.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("repeat button")

from gridplayer.params.static import VideoRepeat, next_video_repeat
from gridplayer.widgets.video_overlay_buttons import OverlayRepeatButton
from gridplayer.widgets.video_overlay_icons import (
    draw_repeat_list,
    draw_repeat_pause,
    draw_repeat_shuffle,
    draw_repeat_single,
)

# --- every mode has an icon function and it paints without raising ---
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtCore import QRect

icons = {
    VideoRepeat.SINGLE_FILE: draw_repeat_single,
    VideoRepeat.DIR: draw_repeat_list,
    VideoRepeat.DIR_SHUFFLE: draw_repeat_shuffle,
    VideoRepeat.PAUSE_AT_END: draw_repeat_pause,
}

for mode, fn in icons.items():
    pm = QPixmap(24, 24)
    pm.fill(QColor("black"))
    p = QPainter(pm)
    try:
        fn(QRect(0, 0, 24, 24), p, QColor("white"), QColor("black"))
        ok, err = True, ""
    except Exception as e:                      # noqa: BLE001
        ok, err = False, repr(e)
    finally:
        p.end()
    c.check(f"icon paints: {mode.value}", ok, err)

# --- the button follows its mode and exposes a tooltip ---
btn = OverlayRepeatButton()
c.check("default mode is list loop", btn.repeat_mode is VideoRepeat.DIR,
        f"{btn.repeat_mode}")

for mode in (VideoRepeat.SINGLE_FILE, VideoRepeat.PAUSE_AT_END, VideoRepeat.DIR_SHUFFLE):
    btn.repeat_mode = mode
    c.check(f"button accepts {mode.value}", btn.repeat_mode is mode)

c.check("tooltip is set", bool(btn.toolTip()), f"{btn.toolTip()!r}")

# --- clicking cycles through the whole cycle ---
seen = []
for _ in range(4):
    btn.clicked.emit()
    seen.append(btn.repeat_mode)
c.check("button walks the full cycle on click",
        set(seen) == set([VideoRepeat.DIR, VideoRepeat.SINGLE_FILE,
                          VideoRepeat.DIR_SHUFFLE, VideoRepeat.PAUSE_AT_END]),
        f"{[m.value for m in seen]}")

c.finish()
```

> 注意：最后一段要求按钮**自己**处理点击循环（`clicked` 连到自身的推进逻辑），
> 而不是由 `VideoBlock` 去算下一个模式。这样按钮是自洽可测的，
> `VideoBlock` 只需把按钮的新模式写回 `video_params`。

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_repeat_button.py`
Expected: FAIL — `ImportError: cannot import name 'OverlayRepeatButton'`

- [ ] **Step 3: 写图标**

`app/gridplayer/widgets/video_overlay_icons.py` 末尾追加：

```python
# --- MOD: playlist / repeat icons -----------------------------------------


def _arc_point(box, angle_deg):
    """Point on the ellipse inscribed in `box`, Qt angle convention (CCW, 1/16 deg base)."""
    rad = math.radians(angle_deg)

    return QPointF(
        box.center().x() + (box.width() / 2) * math.cos(rad),
        box.center().y() - (box.height() / 2) * math.sin(rad),
    )


def _draw_cw_arrow(rect, painter, color_fg, gap_deg=75):
    """Clockwise circular arrow with a filled head - the base of every repeat icon."""
    painter.setRenderHint(QPainter.Antialiasing, True)

    box = rect.adjusted(5, 5, -5, -5)

    painter.setPen(QPen(color_fg, 2, Qt.SolidLine, Qt.RoundCap))
    painter.drawArc(box, 0, int((360 - gap_deg) * 16))

    end_deg = 360 - gap_deg
    tip = _arc_point(box, end_deg)

    rad = math.radians(end_deg)
    dx, dy = math.sin(rad), -math.cos(rad)      # tangent pointing along increasing angle
    size = 4.0

    head = QPainterPath()
    head.moveTo(tip.x() + dx * size, tip.y() + dy * size)
    head.lineTo(tip.x() - dy * size * 0.85, tip.y() + dx * size * 0.85)
    head.lineTo(tip.x() + dy * size * 0.85, tip.y() - dx * size * 0.85)
    head.closeSubpath()

    painter.setPen(Qt.NoPen)
    painter.fillPath(head, QBrush(color_fg))


def _badge_patch(rect):
    """Small square at the centre of the arrow, where the inner glyph goes."""
    box = rect.adjusted(5, 5, -5, -5)
    side = 10

    return QRect(
        round(box.center().x() - side / 2),
        round(box.center().y() - side / 2),
        side,
        side,
    )


def _clear_badge(rect, painter, color_bg):
    """Background patch so the arrow doesn't run through the inner glyph."""
    patch = _badge_patch(rect)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color_bg))
    painter.drawEllipse(patch)
    painter.setBrush(Qt.NoBrush)

    return patch


def _badge_text(rect, painter, color_fg, color_bg, text):
    patch = _clear_badge(rect, painter, color_bg)

    font = painter.font()
    font.setPixelSize(9)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(color_fg, 1))
    painter.drawText(patch, Qt.AlignCenter, text)


def draw_repeat_list(rect, painter, color_fg, color_bg):
    """列表循环：顺时针箭头。"""
    _draw_cw_arrow(rect, painter, color_fg)


def draw_repeat_single(rect, painter, color_fg, color_bg):
    """单集循环：顺时针箭头 + 内嵌 1。"""
    _draw_cw_arrow(rect, painter, color_fg)
    _badge_text(rect, painter, color_fg, color_bg, "1")


def draw_repeat_pause(rect, painter, color_fg, color_bg):
    """播完暂停：顺时针箭头 + 内嵌暂停符（两道竖条）。"""
    _draw_cw_arrow(rect, painter, color_fg)

    patch = _clear_badge(rect, painter, color_bg)

    bar_w = 3
    bar_h = 7
    top = patch.center().y() - bar_h // 2

    painter.setPen(Qt.NoPen)
    painter.fillRect(patch.center().x() - bar_w - 1, top, bar_w, bar_h, color_fg)
    painter.fillRect(patch.center().x() + 1, top, bar_w, bar_h, color_fg)


def draw_repeat_shuffle(rect, painter, color_fg, color_bg):
    """随机播放：从左往右的交叉箭头。"""
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(color_fg, 2, Qt.SolidLine, Qt.RoundCap))

    left = rect.x() + 5
    right = rect.x() + rect.width() - 5
    top = rect.y() + 8
    bottom = rect.y() + rect.height() - 8

    painter.drawLine(left, top, right, bottom)
    painter.drawLine(left, bottom, right, top)

    for (x, y, dx, dy) in (
        (right, bottom, 1, 3),
        (right, top, 1, -3),
    ):
        head = QPainterPath()
        head.moveTo(x + 2, y)
        head.lineTo(x - 6, y + dy)
        head.lineTo(x - 6, y - dy)
        head.closeSubpath()

        painter.setPen(Qt.NoPen)
        painter.fillPath(head, QBrush(color_fg))
        painter.setPen(QPen(color_fg, 2, Qt.SolidLine, Qt.RoundCap))


def draw_menu(rect, painter, color_fg, color_bg):
    """三横杠（播放列表面板的入口）。"""
    painter.setRenderHint(QPainter.Antialiasing, False)

    bar_h = 2
    left = rect.x() + 5
    width = rect.width() - 10
    first_top = rect.y() + round(rect.height() / 2) - 6

    for i in range(3):
        painter.fillRect(left, first_top + i * 5, width, bar_h, color_fg)
```

同时在文件顶部把需要的名字补进 import：

```python
from PyQt5.QtCore import QPointF, QRect, Qt
```

（`QPointF` 是新增的；`QRect` 原本已导入。）

- [ ] **Step 4: 写按钮**

`app/gridplayer/widgets/video_overlay_buttons.py`：

import 区补上新图标与枚举：

```python
from gridplayer.params.static import VideoRepeat, next_video_repeat
from gridplayer.widgets.video_overlay_icons import (
    draw_cross,
    draw_menu,
    draw_pause,
    draw_play,
    draw_repeat_list,
    draw_repeat_pause,
    draw_repeat_shuffle,
    draw_repeat_single,
    draw_spin_circle,
    draw_volume_off,
    draw_volume_on,
)
```

文件末尾追加：

```python
# --- MOD: playlist panel + repeat mode buttons -----------------------------

REPEAT_MODE_TITLES = {
    VideoRepeat.DIR: "列表循环",
    VideoRepeat.SINGLE_FILE: "单集循环",
    VideoRepeat.DIR_SHUFFLE: "随机播放",
    VideoRepeat.PAUSE_AT_END: "播完暂停",
}


class OverlayRepeatButton(OverlayButton):
    """Cycles this block's play order. Self-contained: click advances the mode."""

    _ICONS = {
        VideoRepeat.SINGLE_FILE: draw_repeat_single,
        VideoRepeat.DIR: draw_repeat_list,
        VideoRepeat.DIR_SHUFFLE: draw_repeat_shuffle,
        VideoRepeat.PAUSE_AT_END: draw_repeat_pause,
    }

    repeat_mode_changed = pyqtSignal(object)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._repeat_mode = VideoRepeat.DIR
        self.setToolTip(REPEAT_MODE_TITLES[self._repeat_mode])

        self.clicked.connect(self._advance)

    def _advance(self):
        self.repeat_mode = next_video_repeat(self._repeat_mode)

        self.repeat_mode_changed.emit(self._repeat_mode)

    @property
    def repeat_mode(self):
        return self._repeat_mode

    @repeat_mode.setter
    def repeat_mode(self, mode):
        self._repeat_mode = mode
        self.setToolTip(REPEAT_MODE_TITLES.get(mode, str(mode)))
        self.update()

    def icon(self, rect, painter, color_fg, color_bg):
        draw = self._ICONS.get(self._repeat_mode, draw_repeat_list)

        return draw(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg): ...
```

- [ ] **Step 5: 接进 overlay**

`app/gridplayer/widgets/video_overlay.py`：

import 区加 `OverlayRepeatButton`：

```python
from gridplayer.widgets.video_overlay_buttons import (
    OverlayExitButton,
    OverlayPlayPauseButton,
    OverlayRepeatButton,
    OverlayVolumeButton,
)
```

`OverlayBlock` 的信号区加：

```python
    mute_unmute_clicked = pyqtSignal()
    # MOD
    repeat_mode_changed = pyqtSignal(object)
```

`ui_connect` 里加一行：

```python
            (self.volume_bar.position_changed, self.emit_volume_position),
            (self.repeat_button.repeat_mode_changed, self.repeat_mode_changed.emit),
```

`ui_setup` 里创建并安放按钮（放在进度条之后、音量键之前）：

```python
        self.repeat_button = OverlayRepeatButton(parent=self)      # MOD
        self.volume_button = OverlayVolumeButton(parent=self)

        self.bottom_bar.addWidget(self.play_pause_button)
        self.bottom_bar.addWidget(self.label_progress)
        self.bottom_bar.addWidget(self.progress_bar, 1)
        self.bottom_bar.addWidget(self.progress_bar_placeholder, 1)
        self.bottom_bar.addWidget(self.repeat_button)             # MOD
        self.bottom_bar.addWidget(self.volume_button)
```

`OverlayBlock` 加一个 slot：

```python
    @pyqtSlot(object)
    def set_repeat_mode(self, mode):
        self.repeat_button.repeat_mode = mode
```

- [ ] **Step 6: 接进 VideoBlock**

`app/gridplayer/widgets/video_block.py`：

- 信号区加 `repeat_mode_change = pyqtSignal(VideoRepeat)`（`VideoRepeat` 已经导入）。
- `init_overlay` 的 `qt_connect(...)` 里加两条：

```python
        (overlay.mute_unmute_clicked, self.mute_unmute),
        (overlay.repeat_mode_changed, self.set_repeat_mode),   # MOD
        ...
        (self.is_audio_present_change, overlay.set_volume_button_visible),
        (self.repeat_mode_change, overlay.set_repeat_mode),    # MOD
```

- `set_repeat_mode`（约 873 行）改成会广播：

```python
    def set_repeat_mode(self, repeat_mode: VideoRepeat):
        self.video_params.repeat_mode = repeat_mode

        # MOD: keep the overlay's repeat button in sync (also covers changes
        # made from the context menu or the [ALL] actions)
        self.repeat_mode_change.emit(repeat_mode)
```

- 在把初始参数推给驱动/overlay 的地方（`apply_snapshot` 之外、约 794-795 行的
  `self.set_volume(...)` / `self.set_muted(...)` 旁边）加一行初始推送：

```python
        self.set_volume(self.video_params.volume)
        self.set_muted(self.video_params.is_muted)
        self.repeat_mode_change.emit(self.video_params.repeat_mode)   # MOD
```

- [ ] **Step 7: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_repeat_button.py`
Expected: PASS — 若 `button walks the full cycle on click` 失败，检查 `OverlayRepeatButton.__init__`
里 `self.clicked.connect(self._advance)` 是否在 `super().__init__()` **之后**。

- [ ] **Step 8: 全量测试 + 回归**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 3: GUI 验证图标与四态行为

**Files:**
- Modify: 本计划文件（追加实测结果与图标截图路径）
- 不改源码

**Interfaces:**
- Consumes: Task 2 的按钮与图标
- Produces: 四张图标截图 + 播完暂停的行为验证记录

- [ ] **Step 1: 起窗口并截按钮条**

启动 `run_gridplayer.py` 播一个 3 秒测试片，鼠标移到视频上让 overlay 显示，
截取窗口右下角区域放大（沿用 MOD 里已验证过的 `CopyFromScreen` + 最近邻放大的做法）。

- [ ] **Step 2: 四种模式各截一张**

对 `repeat_button` 连点 4 次，每次截图，确认图标依次为
**列表循环（圆弧箭头）→ 单集循环（带 1）→ 随机（交叉箭头）→ 播完暂停（带暂停符）**，
且 tooltip 文案正确。

把四张图存到 `<repo>\evidence\`，命名 `repeat-1-list.png` … `repeat-4-pause.png`。

- [ ] **Step 3: 目视检查箭头形状**

放大到 5 倍看：圆弧是否闭合圆润、箭头是否指向切线方向、内嵌字形是否被背景补丁干净地"掏空"。
若箭头歪斜，调整 `_draw_cw_arrow` 里的 `gap_deg` 与 `size` 后重截。

> 说明：用户原话是"暂停三角形"，本计划先按**标准暂停符（两道竖条）**实现。
> 截图给他看后再决定是否改成三角形。

- [ ] **Step 4: 验证「播完暂停」真的停住**

把模式切到「播完暂停」，播放 3 秒测试片，等它播完，确认：
- 不回到开头（不是单集循环）
- 不跳到同目录下一个文件（不是列表循环）
- 进度条停在末尾、播放键变回"播放"态

对照跑一次「列表循环」，确认它会跳到 `probe.mov`（同目录下一个文件）。

- [ ] **Step 5: 验证右键菜单第四条**

右键视频 → 确认菜单里出现「Play Once (Pause at End)」，
点它之后 overlay 按钮图标同步变成"播完暂停"（验证 `set_repeat_mode` 的广播接线）。

- [ ] **Step 6: 把结果写回本计划文件**

追加实测结论（每种模式的截图文件名 + 播完暂停的行为观察）。结束本期。
