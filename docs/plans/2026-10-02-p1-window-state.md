# P1：窗口状态记忆 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GridPlayer 关闭时记住窗口所在的屏幕与位置、以及是全屏还是窗口，下次启动恢复原样。

**Architecture:** 沿用 MOD 已有的「关闭落盘、启动回填」模式（与 `player/volume` 同一处代码、同一套机制）。用三个基础类型设置项承载，复用上游已有的 `WindowState` 命名元组与 `WindowStateManager.restore_window_state()`，只在两端加「存」和「取」。

**Tech Stack:** Python 3.13.5 / PyQt5 5.15.11 / Qt 5.15.2 / QSettings(INI) / 无第三方测试框架（纯脚本断言）

**Spec:** `<repo>\docs\specs\2026-10-02-playlist-panel-design.md` 的 §4.6、§5、§6

## Global Constraints

- 只改 `<repo>\app\gridplayer\` 下的文件；每处改动必须带 `# MOD:` 注释，便于日后与上游对比和重打补丁。
- 新增设置项只用基础类型（`str` / `bool`）。`settings.py` 的 `_default_settings` 是**类型驱动**的：`Settings.get()` 用 `type(_default_settings[key])` 做转换，`Settings.set()` 会做 `type(value) is not type(default)` 校验并抛 `ValueError`。所以窗口状态拆成三个基础类型，不要塞 `WindowState` 命名元组。
- 测试必须用 MOD 的 venv 解释器：`<repo>\pyenv\Scripts\python.exe`，不引入任何新依赖。
- 测试脚本失败必须 `sys.exit(非0)`，成功 `sys.exit(0)`。
- 测试必须设置 `GRIDPLAYER_DATA_DIR` 指向临时目录，**不得污染** `<repo>\data\settings.ini`。
- 每个任务结束时，MOD 已有的 15 项回归（`_selftest.py`）必须全绿。
- 不要把窗口位置存进 `data/`，它属于用户级偏好 → 走 settings.ini。

---

### Task 1: 搭建 tests/ 骨架并跑通一个空测试

**Files:**
- Create: `<repo>\tests\__init__.py`
- Create: `<repo>\tests\_harness.py`
- Create: `<repo>\tests\test_harness_smoke.py`
- Create: `<repo>\_runtests.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `tests._harness.Checker`：`check(name: str, cond: bool, detail: str = "") -> None`、`finish() -> None`（打印汇总并 `sys.exit`）
  - `tests._harness.bootstrap()`：设置 `GRIDPLAYER_DATA_DIR` 到一个临时目录、把 `app` 加进 `sys.path`、创建 **`QApplication`**（注意：测试会创建 `QWidget`，只建 `QCoreApplication` 会直接抛 *"Must construct a QApplication before a QWidget"*），返回该临时目录的 `Path`
  - `_runtests.py`：发现并运行 `tests/test_*.py`，全部通过才退出 0

- [ ] **Step 1: 写骨架**

`tests/_harness.py`：

```python
"""Shared helpers for the MOD test scripts. No third-party test framework."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def bootstrap(keep_data: bool = False) -> Path:
    """Prepare a sandboxed run: temp data dir, app on sys.path, QCoreApplication."""
    data_dir = Path(tempfile.mkdtemp(prefix="gpmod-test-"))
    os.environ["GRIDPLAYER_DATA_DIR"] = str(data_dir)

    os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(ROOT / "libVLC" / "libvlc.dll"))
    os.environ.setdefault("PYTHON_VLC_MODULE_PATH", str(ROOT / "libVLC" / "plugins"))

    sys.path.insert(0, str(ROOT / "app"))

    from PyQt5.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    return data_dir


class Checker:
    def __init__(self, title: str):
        self._title = title
        self._results = []

    def check(self, name, cond, detail=""):
        self._results.append(bool(cond))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}   {detail}")

    def finish(self):
        passed = sum(self._results)
        total = len(self._results)
        print(f"\n==== {self._title}: {passed}/{total} checks passed ====")
        sys.exit(0 if passed == total else 1)
```

`tests/__init__.py`：空文件。

`tests/test_harness_smoke.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("harness smoke")

c.check("data dir created", data_dir.is_dir(), str(data_dir))

from gridplayer.settings import Settings

Settings().set("player/window_maximized", True)
Settings().sync()
c.check("settings write/read works in sandbox", Settings().get("player/window_maximized") is True)

c.finish()
```

`_runtests.py`：

```python
"""Run every tests/test_*.py as a subprocess; fail if any of them fails."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = sorted((ROOT / "tests").glob("test_*.py"))
PY = ROOT / "pyenv" / "Scripts" / "python.exe"

failed = []
for t in TESTS:
    print(f"\n########## {t.name} ##########")
    r = subprocess.run([str(PY), str(t)], cwd=str(ROOT))
    if r.returncode != 0:
        failed.append(t.name)

print(f"\n########## {len(TESTS) - len(failed)}/{len(TESTS)} test files passed ##########")
sys.exit(1 if failed else 0)
```

- [ ] **Step 2: 跑一次，确认它失败**

此时 `player/window_maximized` 还不是合法设置键 → `Settings.set` 在 `_default_settings[...]` 上抛 `KeyError`。

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: FAIL — `KeyError: 'player/window_maximized'`

- [ ] **Step 3: 加三个设置键**

`app/gridplayer/settings.py`，在 `"player/show_overlay_border": False,` 之后插入：

```python
    "player/show_overlay_border": False,
    # MOD: window position/screen and fullscreen state, restored on next launch.
    # Written only when a window closes (see window_state._save_window_state).
    "player/window_geometry": "",
    "player/window_maximized": False,
    "player/window_fullscreen": False,
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: PASS — `1/1 test files passed`

- [ ] **Step 5: 回归不能坏**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 2: 关闭时捕获并保存窗口状态

**Files:**
- Modify: `<repo>\app\gridplayer\player\managers\window_state.py`
- Create: `<repo>\tests\test_window_state_save.py`

**Interfaces:**
- Consumes: Task 1 的三个设置键
- Produces:
  - `WindowStateManager._save_window_state() -> None`：把当前窗口几何/最大化/全屏写入设置并 `sync()`
  - 复用上游已有的 `WindowStateManager.window_state() -> WindowState`

- [ ] **Step 1: 写测试**

`tests/test_window_state_save.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("window state save")

from PyQt5.QtWidgets import QWidget

from gridplayer.params.static import WindowState
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
mgr._save_window_state()

geom = Settings().get("player/window_geometry")
c.check("geometry written", bool(geom), f"len={len(geom)}")
c.check("maximized written (windowed -> False)",
        Settings().get("player/window_maximized") is False)
c.check("fullscreen written (windowed -> False)",
        Settings().get("player/window_fullscreen") is False)

# --- round-trip: the blob decodes back to the same size/position ---
from PyQt5.QtCore import QByteArray
import base64

probe = QWidget()
ok = probe.restoreGeometry(QByteArray(base64.b64decode(geom)))
c.check("geometry blob restores", ok is True)
c.check("restored size matches", (probe.width(), probe.height()) == (800, 600),
        f"{probe.width()}x{probe.height()}")
c.check("restored pos matches", (probe.x(), probe.y()) == (120, 80),
        f"{probe.x()},{probe.y()}")

# --- the three settings stay consistent with what window_state() reports ---
c.check("saved maximized flag matches window_state()",
        Settings().get("player/window_maximized") == mgr.window_state().is_maximized)
c.check("saved fullscreen flag matches window_state()",
        Settings().get("player/window_fullscreen") == mgr.window_state().is_fullscreen)

c.finish()
```

> 说明：这里**不**断言「未显示的 QWidget 调 `setWindowState` 后 `isMaximized()` 为真」——
> 该行为在 Qt 中依赖窗口是否已创建，不稳定；而 `window_state()` 的取值逻辑是上游已有代码
> （播放列表保存窗口状态时就在用），本期只负责把它接到设置项上，所以断言「写出的值与
> `window_state()` 报告的一致」才是这一期真正要保证的不变量。

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_window_state_save.py`
Expected: FAIL — `AttributeError: 'WindowStateManager' object has no attribute '_save_window_state'`

- [ ] **Step 3: 实现**

`app/gridplayer/player/managers/window_state.py`：

在 `closeEvent` 里，紧随已有的 `self._save_last_volume(...)` 之后加一行调用（注意顺序：必须在 `force_terminate()` 之前，因为那是 `os._exit`）：

```python
        self._save_last_volume(remembered_volume)

        self._save_window_state()

        self.closing.emit()
```

并在 `_save_last_volume` 方法之后新增：

```python
    def _save_window_state(self):
        """MOD: remember where this window was and how it was shown.

        Written only on close, mirroring _save_last_volume, so a window that
        is still open never has its geometry overwritten by another one.
        """
        settings = Settings()
        current = self.window_state()

        settings.set("player/window_geometry", current.geometry)
        settings.set("player/window_maximized", current.is_maximized)
        settings.set("player/window_fullscreen", current.is_fullscreen)
        settings.sync()

        self._log.debug(f"Saved window state: {current.is_maximized=}, {current.is_fullscreen=}")
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_window_state_save.py`
Expected: PASS — `8/8 checks passed`

如果 `restored pos matches` 失败，说明无头环境下窗口管理器不保留位置：把该用例的断言放宽为只比较尺寸，并在测试文件里写明原因，**不要**改实现。

- [ ] **Step 5: 回归**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 3: 启动时回填，含离屏保险

**Files:**
- Modify: `<repo>\app\gridplayer\player\managers\window_state.py`
- Create: `<repo>\tests\test_window_state_restore.py`

**Interfaces:**
- Consumes: Task 2 写入的三个设置键、上游的 `restore_window_state(window_state: WindowState)`
- Produces:
  - 模块级函数 `_geometry_frame(geometry_b64: str) -> QRect | None`
  - 模块级函数 `_is_geometry_on_screen(rect: QRect) -> bool`
  - `WindowStateManager._saved_window_state() -> WindowState | None`
  - `WindowStateManager._restore_saved_window_state() -> bool`（返回是否真的恢复了，便于测试断言）

- [ ] **Step 1: 写测试**

`tests/test_window_state_restore.py`：

```python
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("window state restore")

from PyQt5.QtCore import QByteArray
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QWidget

from gridplayer.player.manager import Context
from gridplayer.player.managers.window_state import (
    WindowStateManager,
    _geometry_frame,
    _is_geometry_on_screen,
)
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


# --- empty geometry -> nothing to restore ---
Settings().set("player/window_geometry", "")
Settings().sync()
mgr, win = make_manager()
c.check("empty geometry -> no restore", mgr._saved_window_state() is None)

# --- on-screen geometry -> restored ---
primary = QGuiApplication.primaryScreen().availableGeometry()
on_screen = blob_of(primary.x() + 40, primary.y() + 40, 720, 480)
Settings().set("player/window_geometry", on_screen)
Settings().set("player/window_maximized", False)
Settings().set("player/window_fullscreen", False)
Settings().sync()

frame = _geometry_frame(on_screen)
c.check("blob decodes to a frame rect", frame is not None, f"{frame}")
c.check("on-screen rect judged on-screen", _is_geometry_on_screen(frame) is True)

mgr, win = make_manager()
c.check("restore applied", mgr._restore_saved_window_state() is True)
c.check("window geometry applied", (win.width(), win.height()) == (720, 480),
        f"{win.width()}x{win.height()}")

# --- off-screen geometry -> refused, window falls back ---
far = blob_of(primary.x() - 9000, primary.y() - 9000, 720, 480)
Settings().set("player/window_geometry", far)
Settings().sync()

frame_far = _geometry_frame(far)
c.check("off-screen rect judged off-screen", _is_geometry_on_screen(frame_far) is False)

mgr2, win2 = make_manager()
c.check("off-screen restore refused", mgr2._restore_saved_window_state() is False)
c.check("fallback size is the initial size",
        (win2.width(), win2.height()) == (640, 360), f"{win2.width()}x{win2.height()}")

# --- maximized flag drives window state ---
Settings().set("player/window_geometry", on_screen)
Settings().set("player/window_maximized", True)
Settings().set("player/window_fullscreen", False)
Settings().sync()

mgr3, win3 = make_manager()
saved = mgr3._saved_window_state()
c.check("saved state reports maximized", saved.is_maximized is True)
c.check("saved state reports not fullscreen", saved.is_fullscreen is False)

c.finish()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_window_state_restore.py`
Expected: FAIL — `ImportError: cannot import name '_geometry_frame'`

- [ ] **Step 3: 实现**

`app/gridplayer/player/managers/window_state.py`。

先在文件顶部的 import 区补上需要的名字（`QRect`、`QGuiApplication` 加进已有的 `PyQt5.QtCore` / `PyQt5.QtGui` 导入；`PLAYER_INITIAL_SIZE` 从 `gridplayer.params.static` 导入）：

```python
from PyQt5.QtCore import QByteArray, QEvent, QRect, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QGuiApplication

from gridplayer.params.static import PLAYER_INITIAL_SIZE, WindowState
```

在 `WindowStateManager` 类之前，加两个模块级函数：

```python
def _geometry_frame(geometry_b64: str) -> QRect | None:
    """MOD: decode a saveGeometry() blob into a rect without a real window."""
    try:
        blob = QByteArray(base64.b64decode(geometry_b64))
    except (ValueError, TypeError):
        return None

    probe = QWidget()
    if not probe.restoreGeometry(blob):
        return None

    return probe.frameGeometry()


def _is_geometry_on_screen(rect: QRect) -> bool:
    """MOD: guard against a saved position on a monitor that is gone."""
    if rect is None:
        return False

    center = rect.center()

    return any(
        screen.availableGeometry().contains(center)
        for screen in QGuiApplication.screens()
    )
```

（`QWidget` 已在文件里被 `WindowState` 之外的代码用到吗？没有 —— 需要在 `PyQt5.QtWidgets` 导入里补 `QWidget`。若该文件原本不导入 `PyQt5.QtWidgets`，新增一行 `from PyQt5.QtWidgets import QWidget`。）

然后在类里，`init()` 的最前面加回填，并新增三个方法：

```python
    def init(self):
        # MOD: put the window back where it was closed
        self._restore_saved_window_state()

        # Linux has window manager for this, the flag doesn't work there anyway
        if not env.IS_LINUX and Settings().get("player/stay_on_top"):
            self.parent().setWindowFlag(Qt.WindowStaysOnTopHint)
```

```python
    def _saved_window_state(self) -> WindowState | None:
        """MOD: the window state stored by the last window that closed."""
        geometry = Settings().get("player/window_geometry")
        if not geometry:
            return None

        return WindowState(
            is_maximized=Settings().get("player/window_maximized"),
            is_fullscreen=Settings().get("player/window_fullscreen"),
            geometry=geometry,
        )

    def _restore_saved_window_state(self) -> bool:
        """MOD: apply the stored window state, refusing an off-screen position."""
        window_state = self._saved_window_state()
        if window_state is None:
            return False

        if not _is_geometry_on_screen(_geometry_frame(window_state.geometry)):
            self._log.warning("Saved window position is off-screen, centering instead")
            self._center_window()
            return False

        self.restore_window_state(window_state)
        return True

    def _center_window(self):
        """MOD: deterministic fallback when the saved position is unusable."""
        screen = QGuiApplication.primaryScreen().availableGeometry()

        self.parent().resize(*PLAYER_INITIAL_SIZE)
        self.parent().move(screen.center() - self.parent().rect().center())
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_window_state_restore.py`
Expected: PASS — `10/10 checks passed`

- [ ] **Step 5: 跑全部测试 + 回归**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: `3/3 test files passed`

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 4: GUI 端到端验证窗口记忆真的生效

**Files:**
- Modify: `<repo>\docs\plans\2026-10-02-p1-window-state.md`（在本任务下追加实测结果）
- 不改任何源码

**Interfaces:**
- Consumes: Task 2 的保存、Task 3 的恢复
- Produces: 一份实测记录（写回本计划文件）

- [ ] **Step 1: 基线**——把 MOD 的 settings 恢复成窗口态

用 `<repo>\pyenv\Scripts\python.exe` 在 `GRIDPLAYER_DATA_DIR=<repo>\data` 下把 `player/window_geometry` 清空。

- [ ] **Step 2: 第一次启动，把窗口挪到一个非默认位置并最大化**

启动 `run_gridplayer.py`，用 Win32 `SetWindowPos`/`ShowWindow(SW_MAXIMIZE)` 把窗口设成
明确的坐标（例如主屏左上角 +200,+150，尺寸 900×560），然后 `CloseMainWindow()`。

- [ ] **Step 3: 断言落盘**

读 `data/settings.ini`，确认 `window_geometry` 非空、`window_maximized=True`、`window_fullscreen=False`。

- [ ] **Step 4: 第二次启动，断言恢复**

再启动，读窗口的 `GetWindowRect`，确认尺寸/位置与 Step 2 设置的一致，且 `IsZoomed(hwnd)` 为真。

- [ ] **Step 5: 全屏用例**

重复 Step 2–4，但用全屏（`ShowWindow(SW_MAXIMIZE)` 换成把窗口设为全屏：直接调用 Qt 无法从外部做，改为在 Step 2 用键盘/菜单触发全屏后用 `CloseMainWindow()`）。
断言 `window_fullscreen=True`，且重启后窗口处于全屏。

- [ ] **Step 6: 离屏用例**

手工把 `window_geometry` 换成一个离屏的 blob（用 `tests/test_window_state_restore.py` 的 `blob_of` 生成），启动后确认窗口出现在主屏且尺寸为 640×360、居中，日志里有
`Saved window position is off-screen, centering instead`。

- [ ] **Step 7: 归档进 `PATCHES.diff`**

`<repo>` 不是 git 仓库，所以本工程的「提交」＝把改动重新归档进补丁文件。
先创建/更新归档脚本 `<repo>\_mkpatch.ps1`：

```powershell
$pristine = '<repo>\.upstream\gridplayer'   # 上游 0.5.5 原始源码快照
$patched  = '<repo>\app\gridplayer'
$files = @(
  'settings.py',
  'models/video.py',
  'player/managers/active_block.py',
  'player/managers/window_state.py',
  'utils/app_dir.py'
)
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('# GridPlayer 0.5.5 -> 改版 补丁（仅列出的文件与官方不同）')
[void]$sb.AppendLine('# 生成: git diff --no-index .upstream/gridplayer app/gridplayer')
[void]$sb.AppendLine('')
foreach ($f in $files) {
  $a = Join-Path $pristine ($f -replace '/', '\')
  $b = Join-Path $patched  ($f -replace '/', '\')
  $d = & git.exe -c core.autocrlf=false -c core.safecrlf=false diff --no-index --no-color $a $b 2>$null
  $d = $d | ForEach-Object {
    $_ -replace [regex]::Escape($a), "upstream/gridplayer/$f" -replace [regex]::Escape($b), "app/gridplayer/$f"
  }
  foreach ($line in $d) { [void]$sb.AppendLine($line) }
}
[System.IO.File]::WriteAllText(
  '<repo>\PATCHES.diff', $sb.ToString(),
  (New-Object System.Text.UTF8Encoding($false))
)
Write-Host "PATCHES.diff written: $((Get-Item '<repo>\PATCHES.diff').Length) bytes"
```

先把上游原始源码留一份快照（只需做一次）：

```powershell
# 从 wheel 解包出上游原始 gridplayer 包
$tmp = Join-Path $env:TEMP 'gp-upstream'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
& curl.exe -sL -x http://127.0.0.1:7892 --max-time 120 `
    -o "$tmp\gp.whl" 'https://github.com/vzhd1701/gridplayer/releases/download/v0.5.5/gridplayer-0.5.5-py3-none-any.whl'
Copy-Item "$tmp\gp.whl" "$tmp\gp.zip" -Force
Expand-Archive "$tmp\gp.zip" -DestinationPath "$tmp\x" -Force
New-Item -ItemType Directory -Force -Path '<repo>\.upstream' | Out-Null
Copy-Item "$tmp\x\gridplayer" '<repo>\.upstream\gridplayer' -Recurse -Force
```

然后把本期新加的 3 个测试文件与 `tests/` 一并登记进 `$files`（`.upstream` 里没有测试，
所以测试只在 `app/` 侧，不需要进 diff），跑：

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\_mkpatch.ps1`
Expected: 打印 `PATCHES.diff written: <n> bytes`，且 `PATCHES.diff` 里能看到本期新增的
`window_geometry` / `window_maximized` / `window_fullscreen` 三行。

- [ ] **Step 8: 把三步实测结果追加到本计划文件末尾，结束本期**

---

## 实测结果（2026-10-02 完成）

**自动化测试**：`_runtests.py` = 3/3 文件通过（harness smoke 2 项、window state save 9 项、
window state restore 15 项），`_selftest.py` = 15/15 回归全绿。

**GUI 端到端**（`_p1_gui_check.ps1` / `_p1_gui_fullscreen.ps1`，主屏 2560×1440、双屏）：

| 轮次 | 操作 | 结果 |
|---|---|---|
| A | 窗口放到 260,170 900×560 后关闭 | 重开精确回到 `260,170 900×560` ✅ |
| B | 最大化后关闭 | 重开 `maximized=True` ✅ |
| C | 全屏后关闭 | 重开 `0,0 2560×1440` 全屏，且 `window_fullscreen` 保持 True ✅ |

**过程中发现并修掉的三个问题**（都不在计划预见范围内）：

1. **测试骨架的 `QApplication` 被回收** —— `bootstrap()` 里创建的 `QApplication` 没保留引用，
   函数返回后即被 GC，下一个 `QWidget()` 直接 abort。已改为模块级引用。

2. **保存顺序 bug（与音量那次同类）** —— `closeEvent` 里 `close_playlist()` 会发出
   `playlist_closed`，而它连着 `window_state.restore_to_minimum()`，**会把窗口缩到最小尺寸**。
   我把 `_save_window_state()` 放在其后，于是存下的是被缩过的尺寸：位置对、尺寸恒为 640×360。
   已改为**先取值、再关闭、最后落盘**，并加了回归用例。GUI 上表现为 Round A 从 FAIL 变 PASS。

3. **上游功能缺陷：从普通窗口进全屏，全屏状态恢复不了** ——
   `restore_window_state()` 里 `showFullScreen()` 被 `if window_state.is_maximized:` 套住，
   而 `is_maximized` 只有在"先最大化再进全屏"时才为真。已改为把该值仅用于记忆
   `is_maximized_pre_fullscreen`，不再拿它当恢复前提，并加了三条回归用例
   （从普通窗口进全屏 / 从最大化进全屏 / 纯最大化）。

**一处对规格的修正**：规格 §4.6 要求"离屏几何回落 + 居中"的保险。实测发现
**Qt 的 `restoreGeometry()` 自带这个保护**（喂进去 `(-9000,-9000)` 的 blob，解码回来已在
主屏可用区内），手写保险永远不会触发、属死代码，已删除；改为用测试断言真正要保证的属性：
**任何存档位置都不能让窗口消失在屏幕外**。

**顺手补的健壮性**：损坏的 base64 几何（手改或写坏的 `settings.ini`）原本会让启动崩溃
（`binascii.Error`），现在记一条警告并回落默认窗口，有两条测试覆盖。

**归档**：`_mkpatch.ps1` 已建立（逐文件 SHA256 对比 `.upstream/gridplayer`），
`PATCHES.diff` 重新生成为 10997 字节、5 个文件。

> 踩坑记录：`.ps1` 脚本必须保持纯 ASCII。Windows PowerShell 5.1 读**无 BOM 的 UTF-8**
> 脚本时按系统 ANSI 代码页解析，中文注释被拆坏后会产生游离引号，直接导致语法错误。
