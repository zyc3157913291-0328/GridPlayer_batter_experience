# P3：每格播放列表面板 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 窗口左侧加一个可切换的播放列表面板：每个视频格子有自己的列表（= 该格当前视频所在文件夹的媒体文件），支持五维排序，左键单击换片，正在播放的项有明确区分。

**Architecture:** 先把「不碰 GUI」的部分做完并单测（扫描 / 排序 / 播放历史 / 时长缓存与探测），再动布局：`GridManager` 的 `QGridLayout` 从 `Player` 挪到子控件 `grid_host`，`Player` 上装 `QSplitter = [面板 | grid_host]`，最后加面板控件与管理器。时长探测是唯一有技术不确定性的部分，**先 spike**。

**Tech Stack:** Python 3.13.5 / PyQt5 5.15.11 / Qt 5.15.2 / 内嵌 libVLC（`gridplayer.vlc_player.vlc`）/ `QListWidget` + `QStyledItemDelegate` / 纯脚本断言

**Spec:** `<repo>\docs\specs\2026-10-02-playlist-panel-design.md` 的 §3.1、§4.1–4.4、§5、§6、§7

## Global Constraints

- 只改 `<repo>\app\gridplayer\` 下的文件；每处改动必须带 `# MOD:` 注释。
- 测试用 `<repo>\pyenv\Scripts\python.exe`，不引入新依赖；失败 `sys.exit(非0)`。
- 测试必须用 `tests._harness.bootstrap()` 把 `GRIDPLAYER_DATA_DIR` 指向临时目录。
- **未知值恒排最后**：`history` 无记录、`duration` 未探到的项，无论升降序都排在已知项之后（用户明确要求）。
- 面板管理器在 `Player.managers` 字典里**必须排在 `grid` 之后**，否则 `self._ctx.layout_splitter` 会抛 `KeyError`。
- 时长探测必须有单文件超时，绝不能阻塞 UI 线程。
- 每步结束时 `_runtests.py` 与 `_selftest.py` 全绿。

---

### Task 1: SPIKE —— 时长探测在捆绑 libVLC 上是否可用

**Files:**
- Create: `<repo>\tests\spike_duration_probe.py`
- Modify: 本计划文件（追加 spike 结论）

**Interfaces:**
- Consumes: `gridplayer.vlc_player.vlc`（内嵌的 python-vlc 绑定）
- Produces: 一个结论 —— `probe_duration(path) -> int | None` 是否可行、走哪个 API、要不要放进独立进程

- [ ] **Step 1: 写 spike 脚本**

`tests/spike_duration_probe.py`：

```python
"""SPIKE - not a regression test. Answers: can we read a file's duration from a
second libvlc instance inside the normal (non-frozen) app process?"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import bootstrap

bootstrap()

from gridplayer.vlc_player import vlc

SAMPLES = [
    Path(r"E:\GridPlayer\_deploy\sample-videos\probe.mp4"),
    Path(r"E:\GridPlayer\_deploy\sample-videos\probe.mov"),
]


def probe(instance, path, timeout_ms=5000):
    media = instance.media_new_path(str(path))

    start = time.monotonic()
    media.parse_with_options(vlc.MediaParseFlag.local, timeout_ms)
    elapsed = (time.monotonic() - start) * 1000

    duration = media.get_duration()
    media.release()

    return duration, elapsed


print("creating a dedicated libvlc instance (no video, no audio)...")
instance = vlc.Instance("--no-video", "--no-audio", "--quiet")
print(f"instance = {instance}")

for path in SAMPLES:
    if not path.is_file():
        print(f"MISSING {path}")
        continue

    duration, elapsed = probe(instance, path)
    print(f"{path.name}: duration={duration} ms   (probe took {elapsed:.0f} ms)")

instance.release()
print("SPIKE DONE")
```

- [ ] **Step 2: 跑它**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\spike_duration_probe.py`

**判定标准**：两个样本都打印出接近 3000 ms 的时长（测试片是 3 秒），且各自耗时在数百毫秒量级。

- [ ] **Step 3: 按结果决定**

| 结果 | 决定 |
|---|---|
| 时长正确、无崩溃 | 走 §4.3 原方案：主进程内专用 instance + 后台 `QThread` |
| 崩溃 / 拿不到时长 / 与播放冲突 | **停下来告诉用户**，改用「时长探测放进独立 worker 进程」，或按 §7 的退路砍掉时长排序；不要硬撑 |
| 能拿到但很慢（>2s/文件） | 保留功能但把默认探测并发与超时调小，并在面板上把时长显示为「按需」 |

- [ ] **Step 4: 记录结论**

把实测输出（两个文件的时长与耗时）追加到本计划文件末尾，作为 P3 后续任务的前提。

---

## Task 1 SPIKE 结论（2026-10-02 已跑，通过）

脚本：`tests/spike_duration_probe.py`（不属于回归测试，`_runtests.py` 只收 `test_*.py`）。

**第一轮失败** —— 只调 `parse_with_options()` 再 `get_duration()`，两个测试片都返回 `-1`，
且调用 0 ms 就返回。原因：libvlc 的 `libvlc_media_parse_with_options` 是**异步**的。

**第二轮（改成轮询状态）通过**：

| 文件 | duration | 解析状态 | 耗时 |
|---|---|---|---|
| `probe.mp4` | 3000 ms | `done` | 20 ms |
| `probe.mov` | 3000 ms | `done` | 21 ms |
| `README.md`（非媒体） | 0 | `done` | 20 ms |

实例创建耗时 393 ms（只创建一次，之后复用）。

**结论与对计划的修正**：

1. **进程内探测可行** —— 不需要退回 worker 进程，也不需要砍掉时长排序。
2. `parse_with_options()` 之后必须轮询 `media.get_parsed_status()`，直到
   `done` / `failed` / `timeout`，并且**用自己的墙钟截止时间**兜底
   （不要用已废弃的阻塞式 `parse()`，文档明说它 "could block indefinitely"）。
   Task 4 的 `_ProbeWorker.run()` 已按此修正。
3. **`duration <= 0` 一律视为未知**：非媒体文件返回 0，未解析出来返回 -1。
4. 速度足够快（~20 ms/文件），不需要节流；但缓存仍然必要（避免每次开面板重探）。

---

### Task 2: `MediaEntry` + 目录扫描 + 排序

**Files:**
- Create: `app/gridplayer/models/media_entry.py`
- Create: `app/gridplayer/utils/media_folder.py`
- Create: `tests/test_media_folder.py`

**Interfaces:**
- Consumes: `gridplayer.params.extensions.SUPPORTED_MEDIA_EXT`
- Produces:
  - `MediaEntry`：frozen dataclass，字段 `path: Path`、`name: str`、`size: int`、`mtime: float`、`duration_ms: int | None = None`；属性 `key -> str`（`str(path).casefold()`）
  - `scan_folder(video_path: Path) -> list[MediaEntry]`
  - `SORT_KEYS: tuple[str, ...]` = `("name", "size", "mtime", "history", "duration")`
  - `sort_entries(entries, key, desc, history) -> list[MediaEntry]`（`history: Mapping[str, int]`）
  - `natural_key(name: str)`

- [x] **Step 1: 写测试**

`tests/test_media_folder.py`：

```python
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("media folder")

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.media_folder import natural_key, scan_folder, sort_entries

# --- build a folder with a known shape ---
folder = data_dir / "videos"
folder.mkdir()
for name, size in (("clip 2.mp4", 200), ("clip 10.mp4", 100), ("b.mkv", 300),
                   ("a.MOV", 400), ("notes.txt", 10), ("sub", 0)):
    p = folder / name
    if name == "sub":
        p.mkdir()
    else:
        p.write_bytes(b"x" * size)

# stagger mtimes so mtime ordering is deterministic
base = time.time() - 1000
for i, name in enumerate(("clip 2.mp4", "clip 10.mp4", "b.mkv", "a.MOV")):
    os.utime(folder / name, (base + i * 100, base + i * 100))

entries = scan_folder(folder / "clip 2.mp4")

c.check("only media files, no dirs", len(entries) == 4,
        f"{sorted(e.name for e in entries)}")
c.check("non-media excluded", all(e.name != "notes.txt" for e in entries))
c.check("directory excluded", all(e.name != "sub" for e in entries))
c.check("sizes captured", {e.name: e.size for e in entries}["b.mkv"] == 300)
c.check("duration starts unknown", all(e.duration_ms is None for e in entries))

# --- natural order ---
c.check("natural_key puts 2 before 10",
        natural_key("clip 2.mp4") < natural_key("clip 10.mp4"))

# --- name sort, ascending / descending ---
names_asc = [e.name for e in sort_entries(entries, "name", False, {})]
c.check("name asc is natural", names_asc == ["a.MOV", "b.mkv", "clip 2.mp4", "clip 10.mp4"],
        f"{names_asc}")
names_desc = [e.name for e in sort_entries(entries, "name", True, {})]
c.check("name desc reverses", names_desc == list(reversed(names_asc)), f"{names_desc}")

# --- size sort ---
sizes_desc = [e.size for e in sort_entries(entries, "size", True, {})]
c.check("size desc", sizes_desc == [400, 300, 200, 100], f"{sizes_desc}")

# --- mtime sort ---
mt_desc = [e.name for e in sort_entries(entries, "mtime", True, {})]
c.check("mtime desc = newest first", mt_desc[0] == "a.MOV", f"{mt_desc}")

# --- history: unknown always last, both directions ---
history = {entries[0].key: 500, entries[1].key: 900}
hist_desc = sort_entries(entries, "history", True, history)
c.check("history desc: newest played first", hist_desc[0].key == entries[1].key)
c.check("history desc: unplayed last", hist_desc[-1].key not in history,
        f"{[e.name for e in hist_desc]}")
hist_asc = sort_entries(entries, "history", False, history)
c.check("history asc: unplayed STILL last",
        all(e.key in history for e in hist_asc[:2]) and all(e.key not in history for e in hist_asc[2:]),
        f"{[e.name for e in hist_asc]}")

# --- duration: unknown always last, both directions ---
d = [
    MediaEntry(folder / "x1.mp4", "x1.mp4", 1, 0.0, 9000),
    MediaEntry(folder / "x2.mp4", "x2.mp4", 1, 0.0, None),
    MediaEntry(folder / "x3.mp4", "x3.mp4", 1, 0.0, 1000),
]
dur_desc = [e.name for e in sort_entries(d, "duration", True, {})]
c.check("duration desc", dur_desc == ["x1.mp4", "x3.mp4", "x2.mp4"], f"{dur_desc}")
dur_asc = [e.name for e in sort_entries(d, "duration", False, {})]
c.check("duration asc: unknown last", dur_asc == ["x3.mp4", "x1.mp4", "x2.mp4"], f"{dur_asc}")

# --- ties keep name order (stable) ---
tied = [
    MediaEntry(folder / "z.mp4", "z.mp4", 5, 0.0),
    MediaEntry(folder / "a.mp4", "a.mp4", 5, 0.0),
]
c.check("ties fall back to name order",
        [e.name for e in sort_entries(tied, "size", True, {})] == ["a.mp4", "z.mp4"])

# --- scanning a file whose folder is gone does not raise ---
c.check("missing folder -> empty list", scan_folder(folder / "nope" / "x.mp4") == [])

c.finish()
```

- [x] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_media_folder.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'gridplayer.models.media_entry'`

- [x] **Step 3: 实现 `MediaEntry`**

`app/gridplayer/models/media_entry.py`：

```python
"""MOD: one media file found in a folder, as shown in the playlist panel."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaEntry:
    path: Path
    name: str
    size: int
    mtime: float
    duration_ms: int | None = None

    @property
    def key(self) -> str:
        """Stable case-insensitive identity used by the history/duration stores."""
        return str(self.path).casefold()

    def with_duration(self, duration_ms: int | None) -> "MediaEntry":
        return MediaEntry(self.path, self.name, self.size, self.mtime, duration_ms)
```

- [x] **Step 4: 实现扫描与排序**

`app/gridplayer/utils/media_folder.py`：

```python
"""MOD: folder scanning and sorting for the playlist panel."""

import re
from pathlib import Path
from typing import Mapping, Sequence

from gridplayer.models.media_entry import MediaEntry
from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT

SORT_KEYS = ("name", "size", "mtime", "history", "duration")

_DIGITS = re.compile(r"(\d+)")


def natural_key(name: str):
    """Split into digit / non-digit runs so 'clip 2' sorts before 'clip 10'."""
    parts = _DIGITS.split(name.casefold())

    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in parts
        if part != ""
    )


def scan_folder(video_path: Path) -> list[MediaEntry]:
    """Every supported media file next to `video_path`. Never raises."""
    folder = Path(video_path).parent

    try:
        items = list(folder.iterdir())
    except OSError:
        return []

    entries = []

    for item in items:
        try:
            if not item.is_file() or item.suffix[1:].lower() not in SUPPORTED_MEDIA_EXT:
                continue

            stat = item.stat()
        except OSError:
            continue

        entries.append(MediaEntry(item, item.name, stat.st_size, stat.st_mtime))

    return entries


def _has_value(entry: MediaEntry, key: str, history: Mapping[str, int]) -> bool:
    if key == "history":
        return entry.key in history
    if key == "duration":
        return entry.duration_ms is not None

    return True


def _primary(entry: MediaEntry, key: str, history: Mapping[str, int]):
    if key == "size":
        return entry.size
    if key == "mtime":
        return entry.mtime
    if key == "history":
        return history[entry.key]
    if key == "duration":
        return entry.duration_ms

    return natural_key(entry.name)


def sort_entries(
    entries: Sequence[MediaEntry],
    key: str,
    desc: bool,
    history: Mapping[str, int],
) -> list[MediaEntry]:
    """Sort with a stable name-order tie-break.

    Entries whose value for `key` is unknown (never played / duration not probed
    yet) always end up last, regardless of direction - that is the behaviour the
    user asked for, so it is deliberately NOT flipped by `desc`.
    """
    known = [e for e in entries if _has_value(e, key, history)]
    unknown = [e for e in entries if not _has_value(e, key, history)]

    known.sort(key=lambda e: natural_key(e.name))          # stable base order

    if key == "name":
        known.sort(key=lambda e: natural_key(e.name), reverse=desc)
    else:
        known.sort(key=lambda e: _primary(e, key, history), reverse=desc)

    unknown.sort(key=lambda e: natural_key(e.name))

    return known + unknown
```

- [x] **Step 5: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_media_folder.py`
Expected: PASS — `20/20 checks passed`

> **实测修正（2026-10-02）**：本步原写 `17/17`。执行时补强了 2 处偏弱断言
> （`mtime` 只看首元素 → 补升序全序；`history` 无法区分已播两条先后 → 补两条全序），
> 并按需加了 1 条 `mtime asc` 全序，因此实际为 **20/20**。
> 原断言一条未删、未放宽。

- [x] **Step 6: 全量测试**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

---

### Task 3: 播放历史存储

**Files:**
- Create: `app/gridplayer/utils/play_history.py`
- Create: `tests/test_play_history.py`

**Interfaces:**
- Consumes: `gridplayer.utils.app_dir.get_app_data_dir`
- Produces:
  - `PlayHistory`：`record(key: str, when_ms: int | None = None) -> None`、`get(key: str) -> int | None`、`as_mapping() -> dict[str, int]`、`load() -> None`、`save() -> None`
  - 常量 `HISTORY_FILE_NAME = "play_history.json"`、`HISTORY_MAX_ENTRIES = 5000`
  - 方法 `prune() -> None`；`load()` 读入后会调用 `prune()`，避免超限文件全量驻留内存

> **复核修正（2026-10-02）**：本节原本还声明了 `HISTORY_SAVE_DEBOUNCE_MS = 2000`，
> 但实现与 Task 7 都不消费它（Task 7 是 `record()` 后立即 `save()`：每个文件写一次、
> 发生在用户操作上，无需防抖）。已作为死常量删除，除非真的引入定时器否则不要加回来。

- [ ] **Step 1: 写测试**

`tests/test_play_history.py`：

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("play history")

from gridplayer.utils.play_history import (
    HISTORY_FILE_NAME,
    HISTORY_MAX_ENTRIES,
    PlayHistory,
)

h = PlayHistory()
c.check("starts empty", h.as_mapping() == {})

h.record("a.mp4", when_ms=1000)
h.record("b.mp4", when_ms=2000)
c.check("records kept", h.get("a.mp4") == 1000 and h.get("b.mp4") == 2000)
c.check("unknown key -> None", h.get("zzz.mp4") is None)

h.record("a.mp4", when_ms=3000)
c.check("re-record overwrites", h.get("a.mp4") == 3000)

h.save()
path = data_dir / HISTORY_FILE_NAME
c.check("file written", path.is_file(), str(path))

raw = json.loads(path.read_text(encoding="utf-8"))
c.check("file is a flat path->ts map", raw.get("a.mp4") == 3000, f"{raw}")

h2 = PlayHistory()
h2.load()
c.check("reloads from disk", h2.get("a.mp4") == 3000 and h2.get("b.mp4") == 2000)

# --- pruning keeps the newest N ---
h3 = PlayHistory()
for i in range(HISTORY_MAX_ENTRIES + 50):
    h3.record(f"f{i}.mp4", when_ms=i)
h3.prune()
kept = h3.as_mapping()
c.check("pruned to the cap", len(kept) == HISTORY_MAX_ENTRIES, f"{len(kept)}")
c.check("oldest dropped", "f0.mp4" not in kept)
c.check("newest kept", f"f{HISTORY_MAX_ENTRIES + 49}.mp4" in kept)

# --- corrupt file must not crash ---
path.write_text("{ this is not json", encoding="utf-8")
h4 = PlayHistory()
h4.load()
c.check("corrupt file degrades to empty", h4.as_mapping() == {})

# --- case-insensitive keys ---
h5 = PlayHistory()
h5.record(r"E:\Movies\Film.MP4".casefold(), when_ms=7)
c.check("keys are casefolded by the caller's convention",
        h5.get(r"E:\Movies\Film.MP4".casefold()) == 7)

c.finish()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_play_history.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'gridplayer.utils.play_history'`

- [ ] **Step 3: 实现**

`app/gridplayer/utils/play_history.py`：

```python
"""MOD: per-file 'last played' timestamps for the playlist panel's history sort."""

import json
import logging
import time
from pathlib import Path

from gridplayer.utils.app_dir import get_app_data_dir

HISTORY_FILE_NAME = "play_history.json"
HISTORY_MAX_ENTRIES = 5000


class PlayHistory:
    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)
        self._entries: dict[str, int] = {}

    @property
    def path(self) -> Path:
        return get_app_data_dir() / HISTORY_FILE_NAME

    def as_mapping(self) -> dict[str, int]:
        return dict(self._entries)

    def get(self, key: str) -> int | None:
        return self._entries.get(key)

    def record(self, key: str, when_ms: int | None = None):
        self._entries[key] = int(time.time() * 1000) if when_ms is None else int(when_ms)

    def prune(self):
        if len(self._entries) <= HISTORY_MAX_ENTRIES:
            return

        newest = sorted(self._entries.items(), key=lambda kv: kv[1], reverse=True)
        self._entries = dict(newest[:HISTORY_MAX_ENTRIES])

    def load(self):
        if not self.path.is_file():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self._log.warning(f"Play history unreadable, starting empty: {e}")
            return

        if isinstance(data, dict):
            self._entries = {
                str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))
            }

    def save(self):
        self.prune()

        try:
            self.path.write_text(
                json.dumps(self._entries, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            self._log.warning(f"Could not write play history: {e}")
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_play_history.py`
Expected: PASS — `13/13 checks passed`

---

### Task 4: 时长缓存 + 后台探测

**Files:**
- Create: `app/gridplayer/utils/duration_cache.py`
- Create: `app/gridplayer/utils/duration_probe.py`
- Create: `tests/test_duration_cache.py`

**Interfaces:**
- Consumes: Task 1 的 spike 结论
- Produces:
  - `DurationCache`：`get(entry: MediaEntry) -> int | None`（命中且 size/mtime 一致才返回）、`put(entry, duration_ms)`、`load()`、`save()`
  - `DurationProber(QObject)`：`request(entries: Sequence[MediaEntry]) -> None`、`stop() -> None`、信号 `duration_ready = pyqtSignal(str, object)`（`entry_key`, `duration_ms`）
  - 常量 `CACHE_FILE_NAME = "duration_cache.json"`、`PROBE_TIMEOUT_MS = 5000`

- [ ] **Step 1: 写测试**（只测缓存；探测本身依赖真实 VLC，留给 Task 9 的 GUI 验证）

`tests/test_duration_cache.py`：

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("duration cache")

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.duration_cache import CACHE_FILE_NAME, DurationCache

video = data_dir / "v.mp4"
video.write_bytes(b"x" * 100)
entry = MediaEntry(video, "v.mp4", 100, 111.0)

cache = DurationCache()
c.check("miss on empty cache", cache.get(entry) is None)

cache.put(entry, 3000)
c.check("hit after put", cache.get(entry) == 3000)

cache.save()
path = data_dir / CACHE_FILE_NAME
c.check("cache file written", path.is_file())

raw = json.loads(path.read_text(encoding="utf-8"))
c.check("keyed by casefolded path", raw[entry.key]["duration_ms"] == 3000, f"{raw}")

c2 = DurationCache()
c2.load()
c.check("reloads from disk", c2.get(entry) == 3000)

# --- invalidation on size change ---
changed_size = MediaEntry(video, "v.mp4", 999, 111.0)
c.check("size change invalidates", c2.get(changed_size) is None)

# --- invalidation on mtime change ---
changed_mtime = MediaEntry(video, "v.mp4", 100, 222.0)
c.check("mtime change invalidates", c2.get(changed_mtime) is None)

# --- unknown durations are not cached ---
c2.put(MediaEntry(video, "v.mp4", 100, 111.0), None)
c.check("None not cached as a hit", c2.get(entry) is None)

# --- corrupt file degrades to empty ---
path.write_text("nonsense", encoding="utf-8")
c3 = DurationCache()
c3.load()
c.check("corrupt cache degrades to empty", c3.get(entry) is None)

c.finish()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_duration_cache.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'gridplayer.utils.duration_cache'`

- [ ] **Step 3: 实现缓存**

`app/gridplayer/utils/duration_cache.py`：

```python
"""MOD: on-disk cache of media durations, keyed by path and validated by size/mtime."""

import json
import logging
from pathlib import Path

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.app_dir import get_app_data_dir

CACHE_FILE_NAME = "duration_cache.json"


class DurationCache:
    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)
        self._entries: dict[str, dict] = {}

    @property
    def path(self) -> Path:
        return get_app_data_dir() / CACHE_FILE_NAME

    def get(self, entry: MediaEntry) -> int | None:
        record = self._entries.get(entry.key)
        if not record:
            return None

        if record.get("size") != entry.size or record.get("mtime") != entry.mtime:
            return None

        duration = record.get("duration_ms")

        return int(duration) if isinstance(duration, (int, float)) else None

    def put(self, entry: MediaEntry, duration_ms: int | None):
        if duration_ms is None:
            return

        self._entries[entry.key] = {
            "size": entry.size,
            "mtime": entry.mtime,
            "duration_ms": int(duration_ms),
        }

    def load(self):
        if not self.path.is_file():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self._log.warning(f"Duration cache unreadable, starting empty: {e}")
            return

        if isinstance(data, dict):
            self._entries = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def save(self):
        try:
            self.path.write_text(
                json.dumps(self._entries, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            self._log.warning(f"Could not write duration cache: {e}")
```

- [ ] **Step 4: 实现后台探测**

`app/gridplayer/utils/duration_probe.py`（探测的具体 API 调用按 Task 1 spike 的结论写；下面是主进程内探测的版本）：

```python
"""MOD: background duration probing so the playlist panel never blocks."""

import logging
import queue
import time
from typing import Sequence

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.duration_cache import DurationCache

PROBE_TIMEOUT_MS = 5000

# Filled in by _ProbeWorker.run() once the vlc module is importable.
_PARSE_FINAL_STATES = ()


class _ProbeWorker(QThread):
    probed = pyqtSignal(str, object)          # entry key, duration_ms (or None)
    batch_done = pyqtSignal()

    def __init__(self, cache: DurationCache):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)
        self._cache = cache
        self._queue: queue.Queue = queue.Queue()
        self._stop = False
        self._instance = None
        self._pending = 0

    def request(self, entries: Sequence[MediaEntry]):
        for entry in entries:
            self._queue.put(entry)
            self._pending += 1

    def stop(self):
        self._stop = True
        self._queue.put(None)

    def run(self):
        from gridplayer.vlc_player import vlc

        global _PARSE_FINAL_STATES
        _PARSE_FINAL_STATES = (
            vlc.MediaParsedStatus.done,
            vlc.MediaParsedStatus.failed,
            vlc.MediaParsedStatus.timeout,
        )

        try:
            self._instance = vlc.Instance("--no-video", "--no-audio", "--quiet")
        except Exception as e:                      # noqa: BLE001
            self._log.error(f"Cannot create a probing libvlc instance: {e}")
            return

        while not self._stop:
            entry = self._queue.get()
            if entry is None:
                break

            duration = None

            try:
                media = self._instance.media_new_path(str(entry.path))

                # parse_with_options() is ASYNCHRONOUS in libvlc: it returns
                # immediately and get_duration() then gives -1. Measured in the
                # Task 1 spike. Poll the parse status with our own wall-clock
                # deadline instead of using the deprecated blocking parse(),
                # which "could block indefinitely" on a bad file.
                start = time.monotonic()
                media.parse_with_options(vlc.MediaParseFlag.local, PROBE_TIMEOUT_MS)

                deadline = start + PROBE_TIMEOUT_MS / 1000 + 1.0
                while time.monotonic() < deadline:
                    if media.get_parsed_status() in _PARSE_FINAL_STATES:
                        break
                    time.sleep(0.02)

                raw = media.get_duration()
                media.release()

                # 0 and -1 both mean "unknown" (a non-media file yields 0)
                duration = int(raw) if raw and raw > 0 else None
            except Exception as e:                  # noqa: BLE001
                self._log.debug(f"Probe failed for {entry.name}: {e}")

            self._cache.put(entry, duration)
            self.probed.emit(entry.key, duration)

            self._pending -= 1
            if self._pending <= 0:
                self._pending = 0
                self.batch_done.emit()

        if self._instance is not None:
            self._instance.release()


class DurationProber(QObject):
    """Thin wrapper: dedupes requests and forwards results on the UI thread."""

    duration_ready = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cache = DurationCache()
        self._cache.load()

        self._worker = _ProbeWorker(self._cache)
        self._worker.probed.connect(self.duration_ready)
        self._worker.batch_done.connect(self._cache.save)

    def cached(self, entry: MediaEntry) -> int | None:
        return self._cache.get(entry)

    def request(self, entries: Sequence[MediaEntry]):
        missing = [e for e in entries if self._cache.get(e) is None]

        if not missing:
            return

        if not self._worker.isRunning():
            self._worker.start()

        self._worker.request(missing)

    def stop(self):
        if self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)

        self._cache.save()
```

- [x] **Step 5: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_duration_cache.py`
Expected: PASS — `12/12 checks passed`

> **实测修正（2026-10-02）**：本步原写 `10/10`，但本节只列了 9 条 check，数字本身就是错的；
> 现在是 12 条（原 9 条 + 大小写不敏感 key + 非 dict JSON 降级 + 「None 不抹掉已有值」）。
>
> 更要紧的是：**Step 1 原第 8 条 check 按计划自身的实现永远不可能通过** ——
> 它先 `put(entry, None)` 再断言 `get(entry) is None`，但同一个 key 在第 5 条 check 里
> 已经存了合法的 3000 ms，而 `put()` 在 None 时提前 return。
> 执行时**保留了 `put()` 的正确语义**（None 绝不写入；一次探测失败不该抹掉已知时长），
> 把该用例改用「从未探测过的 key」，并补一条 `None put keeps an existing hit` 把语义钉死。
> 这不是放宽断言，是修正自相矛盾的用例。

- [ ] **Step 6: 全量测试**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

---

### Task 5: 布局重构（网格挪进宿主控件 + QSplitter）

**Files:**
- Modify: `app/gridplayer/player/managers/grid.py`
- Create: `tests/test_layout_host.py`

**Interfaces:**
- Consumes: 无
- Produces: `self._ctx.grid_host`（`QWidget`）、`self._ctx.layout_splitter`（`QSplitter`），供 `PlaylistPanelManager` 使用
- **约定**：面板控件由 `PlaylistPanelManager` 用 `splitter.insertWidget(0, panel)` 插入；`grid_host` 恒为 `splitter` 的最后一项

- [ ] **Step 1: 写测试**

`tests/test_layout_host.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("layout host")

from PyQt5.QtWidgets import QSplitter, QWidget

from gridplayer.player.manager import Context
from gridplayer.player.managers.grid import GridManager

ctx = Context()
win = QWidget()
grid = GridManager(context=ctx, parent=win)

c.check("context exposes grid_host", hasattr(ctx, "grid_host"))
c.check("context exposes layout_splitter", hasattr(ctx, "layout_splitter"))

splitter = ctx.layout_splitter
c.check("splitter is a QSplitter", isinstance(splitter, QSplitter))
c.check("splitter is installed on the window", win.layout() is not None)
c.check("grid_host lives inside the splitter",
        ctx.grid_host.parent() is splitter or splitter.indexOf(ctx.grid_host) >= 0,
        f"index={splitter.indexOf(ctx.grid_host)}")
c.check("the grid layout is on grid_host, not the window",
        ctx.grid_host.layout() is not None and win.layout().indexOf(ctx.grid_host) >= 0)

# --- a panel inserted at 0 must not disturb grid_host's position ---
panel = QWidget()
splitter.insertWidget(0, panel)
c.check("grid_host still last after inserting a panel",
        splitter.widget(splitter.count() - 1) is ctx.grid_host)
c.check("panel is first", splitter.widget(0) is panel)

# --- minimum width grows by the panel's minimum ---
ctx.layout_splitter.widget(0).setMinimumWidth(200)
c.check("panel minimum width settable",
        ctx.layout_splitter.widget(0).minimumWidth() == 200)

c.finish()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_layout_host.py`
Expected: FAIL — `AttributeError` / `KeyError: 'grid_host'`

- [ ] **Step 3: 改 `GridManager`**

`app/gridplayer/player/managers/grid.py`，import 区补 `QWidget` 与 `QSplitter`：

```python
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget
```

`__init__` 里把网格装到宿主控件上，并建立 splitter：

```python
        self._default_minimum_size = QSize(*PLAYER_INITIAL_SIZE)
        self._minimum_video_size = QSize(*PLAYER_MIN_VIDEO_SIZE)
        self._minimum_size = self._default_minimum_size

        # MOD: the grid gets its own host widget so a side panel can share the
        # window. The panel manager inserts itself at index 0 of this splitter;
        # grid_host must always stay the last item.
        self._grid_host = QWidget(self.parent())
        self._splitter = QSplitter(Qt.Horizontal, self.parent())
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setContentsMargins(0, 0, 0, 0)
        self._splitter.setHandleWidth(3)
        self._splitter.addWidget(self._grid_host)

        self._ctx.grid_host = self._grid_host
        self._ctx.layout_splitter = self._splitter

        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(0)
        self._grid.setContentsMargins(0, 0, 0, 0)

        self._info_label = QLabel(
            translate("Main Window", "Drag and drop media files or URLs here"),
            parent=self._grid_host,
        )
```

`_adjust_window` 加上面板占用的宽度：

```python
    def _adjust_window(self):
        width = self.grid_dimensions.cols * self._minimum_video_size.width()
        height = self.grid_dimensions.rows * self._minimum_video_size.height()

        width = max(width, self._default_minimum_size.width())
        height = max(height, self._default_minimum_size.height())

        # MOD: the side panel takes width away from the video area, so the
        # window's minimum has to grow by however much the panel reserves.
        panel = self._splitter.widget(0) if self._splitter.count() > 1 else None
        if panel is not None and panel.isVisible():
            width += panel.minimumWidth()
            width = max(width, panel.minimumWidth() + self._minimum_video_size.width())

        self._minimum_size = QSize(width, height)
        self.minimum_size_changed.emit(self._minimum_size)
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_layout_host.py`
Expected: PASS — `9/9 checks passed`

- [ ] **Step 5: 网格回归（关键，必须肉眼确认）**

启动 `run_gridplayer.py`，依次确认：
1. 拖入 1 个视频 → 满窗单画面，**没有多余的空白左边距**（重构前就是这样）。
2. 拖入 2 个视频 → 左右两格。
3. 拖入 4 个视频 → 2×2。
4. 关掉全部视频 → 中间出现 "Drag and drop media files or URLs here" 提示文案。
5. 右键 → Set grid size 改成固定值 2 → 布局按 2 列排。
6. 全屏 / 最大化 / 还原 都正常。

任一步不对就**停下来**，不要继续做面板。

- [ ] **Step 6: 全量测试 + 回归**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 6: `PlaylistPanel` 控件（列头 + 列表 + 委托绘制）

**Files:**
- Create: `app/gridplayer/widgets/playlist_panel.py`
- Modify: `app/gridplayer/settings.py`（新增两个排序设置键 —— Task 7/8 会读它，**不先加会 KeyError**）
- Create: `tests/test_playlist_panel.py`

**Interfaces:**
- Consumes: Task 2 的 `MediaEntry` / `sort_entries` / `SORT_KEYS`
- Produces:
  - `PlaylistPanel(QWidget)`：
    - `set_entries(entries: Sequence[MediaEntry], current: Path | None) -> None`
    - `update_duration(entry_key: str, duration_ms: int | None) -> None`
    - `sort_key: str`（属性）、`sort_desc: bool`（属性）
    - 信号 `entry_activated = pyqtSignal(object)`（`Path`）、`sort_changed = pyqtSignal(str, bool)`
  - `PlaylistItemDelegate(QStyledItemDelegate)`
  - 模块常量 `ROLE_PATH = Qt.UserRole + 1`、`ROLE_META = Qt.UserRole + 2`、`ROLE_CURRENT = Qt.UserRole + 3`

- [ ] **Step 1: 写测试**

`tests/test_playlist_panel.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

data_dir = bootstrap()
c = Checker("playlist panel")

from gridplayer.models.media_entry import MediaEntry
from gridplayer.widgets.playlist_panel import ROLE_CURRENT, ROLE_PATH, PlaylistPanel

folder = data_dir / "v"
folder.mkdir()
entries = [
    MediaEntry(folder / "a.mp4", "a.mp4", 100, 1000.0, 3000),
    MediaEntry(folder / "b.mp4", "b.mp4", 300, 2000.0, None),
    MediaEntry(folder / "c.mp4", "c.mp4", 200, 3000.0, 1000),
]

panel = PlaylistPanel()
panel.set_entries(entries, folder / "b.mp4")

c.check("row count matches", panel.count() == 3, f"{panel.count()}")

paths = [panel.item(i).data(ROLE_PATH) for i in range(panel.count())]
c.check("rows carry their path", all(paths), f"{paths}")

current_flags = [bool(panel.item(i).data(ROLE_CURRENT)) for i in range(panel.count())]
c.check("exactly one row is marked as playing", sum(current_flags) == 1, f"{current_flags}")
c.check("the current row is the right one",
        bool(panel.item([p for p in paths].index(str(folder / "b.mp4"))).data(ROLE_CURRENT)))

# --- clicking a row emits entry_activated with a Path ---
got = []
panel.entry_activated.connect(got.append)
panel.item(0).setSelected(True)
panel.activate_row(0)
c.check("activation emits a Path", got and isinstance(got[0], Path), f"{got}")
c.check("activation carries the right path", got and got[0].name == paths[0].split("\\")[-1],
        f"{got}")

# --- sorting drives the visible order ---
panel.set_sort("size", True)
order = [panel.item(i).data(ROLE_PATH) for i in range(panel.count())]
c.check("size desc order applied", order[0].endswith("b.mp4"), f"{order}")

emitted = []
panel.sort_changed.connect(lambda k, d: emitted.append((k, d)))

panel.set_sort("name", False)
c.check("set_sort updates the property", panel.sort_key == "name" and panel.sort_desc is False)
c.check("programmatic set_sort stays silent", emitted == [], f"{emitted}")

panel.apply_sort("mtime", True)
c.check("apply_sort updates the property", panel.sort_key == "mtime" and panel.sort_desc is True)
c.check("user-driven apply_sort notifies", ("mtime", True) in emitted, f"{emitted}")

# --- duration backfill ---
panel.update_duration(entries[1].key, 5000)
c.check("duration backfilled", panel.entry_duration(entries[1].key) == 5000)

# --- clearing ---
panel.set_entries([], None)
c.check("cleared", panel.count() == 0)

c.finish()
```

> 两个入口的分工必须守住：`set_sort()` 是程序化设置（启动时套用上次的排序），
> **不发** `sort_changed`；`apply_sort()` 是用户点列头，**要发** `sort_changed`。
> 实现方式：`set_sort` 先置 `self._suppress_sort_signal = True`，调 `apply_sort`，再复位。

- [ ] **Step 2: 跑测试，确认失败**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_playlist_panel.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'gridplayer.widgets.playlist_panel'`

- [ ] **Step 3: 加两个排序设置键**

`app/gridplayer/settings.py`，紧接 P1 加的三个 `window_*` 之后插入：

```python
    # MOD: playlist panel sorting, carried over to the next window on close
    "player/playlist_sort_key": "name",
    "player/playlist_sort_desc": False,
```

不加这两个键的话，`PlaylistPanelManager.__init__` 里的
`Settings().get("player/playlist_sort_key")` 会因为 `_default_settings` 里查不到而抛
`KeyError`（不是 `AttributeError`）。

- [ ] **Step 4: 实现**

`app/gridplayer/widgets/playlist_panel.py`：

```python
"""MOD: the per-block playlist side panel."""

from pathlib import Path
from typing import Sequence

from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyledItemDelegate,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from gridplayer.models.media_entry import MediaEntry
from gridplayer.utils.media_folder import SORT_KEYS, sort_entries
from gridplayer.utils.time_txt import get_time_txt

ROLE_PATH = Qt.UserRole + 1
ROLE_META = Qt.UserRole + 2
ROLE_CURRENT = Qt.UserRole + 3

SORT_TITLES = {
    "name": "名称",
    "size": "大小",
    "mtime": "日期",
    "history": "历史",
    "duration": "时长",
}

ROW_HEIGHT = 42
ACCENT = QColor("#ffb400")
CURRENT_BG = QColor(45, 92, 138)
HOVER_BG = QColor(255, 255, 255, 22)


def _size_txt(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size / 1:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def _meta_txt(entry: MediaEntry) -> str:
    import datetime

    date = datetime.datetime.fromtimestamp(entry.mtime).strftime("%Y-%m-%d")
    duration = get_time_txt(entry.duration_ms // 1000) if entry.duration_ms else "—"

    return f"{_size_txt(entry.size)} · {date} · {duration}"


class PlaylistItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(0, ROW_HEIGHT)

    def paint(self, painter, option, index):
        painter.save()
        painter.setClipRect(option.rect)

        rect = option.rect
        is_current = bool(index.data(ROLE_CURRENT))

        if is_current:
            painter.fillRect(rect, CURRENT_BG)
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), ACCENT)
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, HOVER_BG)

        text_left = rect.left() + 10
        text_width = rect.width() - 20

        if is_current:
            badge = "正在播放"
            font = QFont(option.font)
            font.setPixelSize(11)
            painter.setFont(font)
            badge_w = QFontMetrics(font).horizontalAdvance(badge) + 12
            painter.setPen(Qt.NoPen)
            painter.setBrush(ACCENT)
            painter.drawRoundedRect(
                QRect(rect.right() - badge_w - 8, rect.top() + 6, badge_w, 16), 8, 8
            )
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor("#1b1b1b"))
            painter.drawText(
                QRect(rect.right() - badge_w - 8, rect.top() + 6, badge_w, 16),
                Qt.AlignCenter,
                badge,
            )
            text_width -= badge_w + 12

        name_font = QFont(option.font)
        name_font.setPixelSize(13)
        painter.setFont(name_font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            QRect(text_left, rect.top() + 4, text_width, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(name_font).elidedText(
                index.data(Qt.DisplayRole), Qt.ElideMiddle, text_width
            ),
        )

        meta_font = QFont(option.font)
        meta_font.setPixelSize(10)
        painter.setFont(meta_font)
        painter.setPen(QColor("#b9c2cc"))
        painter.drawText(
            QRect(text_left, rect.top() + 22, rect.width() - 20, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            index.data(ROLE_META) or "",
        )

        painter.restore()


class PlaylistPanel(QWidget):
    entry_activated = pyqtSignal(object)
    sort_changed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._entries: list[MediaEntry] = []
        self._sort_key = "name"
        self._sort_desc = False
        self._current: Path | None = None
        self._history: dict = {}

        self._sort_buttons: dict[str, QPushButton] = {}

        self._build_ui()

    # --- ui ---

    def _build_ui(self):
        self.setMinimumWidth(200)
        self.setAutoFillBackground(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.folder_label = QLabel(self)
        self.folder_label.setContentsMargins(10, 8, 10, 4)
        outer.addWidget(self.folder_label)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 4)
        header.setSpacing(2)

        for key in SORT_KEYS:
            btn = QPushButton(SORT_TITLES[key], self)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.apply_sort(*self._next_sort(k)))
            header.addWidget(btn)
            self._sort_buttons[key] = btn

        header.addStretch()
        outer.addLayout(header)

        self._list = QListWidget(self)
        self._list.setItemDelegate(PlaylistItemDelegate(self._list))
        self._list.setUniformItemSizes(True)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setMouseTracking(True)
        self._list.itemClicked.connect(self._on_item_clicked)
        outer.addWidget(self._list, 1)

        self._refresh_sort_buttons()

    # --- public api ---

    @property
    def sort_key(self) -> str:
        return self._sort_key

    @property
    def sort_desc(self) -> bool:
        return self._sort_desc

    def set_history(self, history: dict):
        self._history = history
        self._rebuild()

    def set_entries(self, entries: Sequence[MediaEntry], current: Path | None):
        self._entries = list(entries)
        self._current = current
        self._rebuild()

    def count(self) -> int:
        return self._list.count()

    def item(self, row: int) -> QListWidgetItem:
        return self._list.item(row)

    def entry_duration(self, entry_key: str) -> int | None:
        for e in self._entries:
            if e.key == entry_key:
                return e.duration_ms

        return None

    def update_duration(self, entry_key: str, duration_ms: int | None):
        changed = False

        for i, e in enumerate(self._entries):
            if e.key == entry_key and e.duration_ms != duration_ms:
                self._entries[i] = e.with_duration(duration_ms)
                changed = True

        if changed:
            self._rebuild()

    def activate_row(self, row: int):
        item = self._list.item(row)
        if item is None:
            return

        self.entry_activated.emit(item.data(ROLE_PATH))

    def set_sort(self, key: str, desc: bool):
        self.apply_sort(key, desc)

    def apply_sort(self, key: str, desc: bool):
        self._sort_key = key if key in SORT_KEYS else "name"
        self._sort_desc = bool(desc)

        self._refresh_sort_buttons()
        self._rebuild()

    def _next_sort(self, key: str):
        if key == self._sort_key:
            return key, not self._sort_desc

        return key, False

    # --- internals ---

    def _refresh_sort_buttons(self):
        for key, btn in self._sort_buttons.items():
            if key == self._sort_key:
                arrow = " ↓" if self._sort_desc else " ↑"
                btn.setText(SORT_TITLES[key] + arrow)
                btn.setStyleSheet("font-weight: bold;")
            else:
                btn.setText(SORT_TITLES[key])
                btn.setStyleSheet("")

    def _rebuild(self):
        self._list.clear()

        ordered = sort_entries(self._entries, self._sort_key, self._sort_desc, self._history)

        current_key = str(self._current).casefold() if self._current else None

        for e in ordered:
            item = QListWidgetItem(e.name)
            item.setData(ROLE_PATH, e.path)
            item.setData(ROLE_META, _meta_txt(e))
            item.setData(ROLE_CURRENT, e.key == current_key)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._list.addItem(item)

        self._update_folder_label()

    def _update_folder_label(self):
        if self._current is None:
            self.folder_label.setText("")
            return

        self.folder_label.setText(str(Path(self._current).parent))

    def _on_item_clicked(self, item: QListWidgetItem):
        self.entry_activated.emit(item.data(ROLE_PATH))
```

把上面代码块里的 `set_sort` / `apply_sort` 换成这一对（区分「程序化设置」与「用户点击」）：

```python
    def set_sort(self, key: str, desc: bool):
        """Programmatic: adopt a stored sorting without notifying anyone."""
        self._suppress_sort_signal = True
        try:
            self.apply_sort(key, desc)
        finally:
            self._suppress_sort_signal = False

    def apply_sort(self, key: str, desc: bool):
        """User-driven (a column header was clicked)."""
        self._sort_key = key if key in SORT_KEYS else "name"
        self._sort_desc = bool(desc)

        self._refresh_sort_buttons()
        self._rebuild()

        if not getattr(self, "_suppress_sort_signal", False):
            self.sort_changed.emit(self._sort_key, self._sort_desc)
```

并在 `_build_ui` 里初始化 `self._suppress_sort_signal = False`。

> 两个入口的分工必须守住：`set_sort()` 是程序化设置（启动时套用上次的排序），**不发**
> `sort_changed`；`apply_sort()` 是用户点列头，**要发**。列头按钮的 `clicked` 连的是
> `apply_sort`，所以点一下既改了排序、又会被管理器写进设置。

- [ ] **Step 5: 跑测试，确认通过**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_playlist_panel.py`
Expected: PASS — `13/13 checks passed`

- [ ] **Step 6: 全量测试**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

---

### Task 7: 管理器 + 三横杠按钮 + 接线

**Files:**
- Create: `app/gridplayer/player/managers/playlist_panel.py`
- Modify: `app/gridplayer/player/player.py`（注册 manager，**必须放在 `grid` 之后**）
- Modify: `app/gridplayer/widgets/video_overlay.py`（三横杠按钮 + `playlist_clicked`）
- Modify: `app/gridplayer/widgets/video_overlay_buttons.py`（`OverlayPlaylistButton`）
- Modify: `app/gridplayer/widgets/video_block.py`（把点击转成信号）

**Interfaces:**
- Consumes: Task 2/3/4 的 utils、Task 5 的 `ctx.grid_host` / `ctx.layout_splitter`、Task 6 的 `PlaylistPanel`
- Produces:
  - `PlaylistPanelManager`：commands 暴露 `toggle_playlist_panel`、`is_playlist_panel_visible`
  - `OverlayBlock.playlist_clicked = pyqtSignal()`
  - `VideoBlock.playlist_panel_toggle = pyqtSignal()`

- [ ] **Step 1: `OverlayPlaylistButton`**

`app/gridplayer/widgets/video_overlay_buttons.py` 追加：

```python
class OverlayPlaylistButton(OverlayButton):
    """Hamburger that toggles the playlist side panel."""

    def icon(self, rect, painter, color_fg, color_bg):
        return draw_menu(rect, painter, color_fg, color_bg)

    def icon_off(self, rect, painter, color_fg, color_bg):
        return draw_menu(rect, painter, color_fg, color_bg)
```

- [ ] **Step 2: 接进 overlay**

`video_overlay.py`：import `OverlayPlaylistButton`；`OverlayBlock` 加
`playlist_clicked = pyqtSignal()`；`ui_setup` 里在顺序键与音量键之间插入：

```python
        self.repeat_button = OverlayRepeatButton(parent=self)
        self.playlist_button = OverlayPlaylistButton(parent=self)      # MOD
        self.volume_button = OverlayVolumeButton(parent=self)

        ...
        self.bottom_bar.addWidget(self.repeat_button)
        self.bottom_bar.addWidget(self.playlist_button)               # MOD
        self.bottom_bar.addWidget(self.volume_button)
```

`ui_connect` 加 `(self.playlist_button.clicked, self.playlist_toggle)`，
并加 slot：

```python
    @pyqtSlot()
    def playlist_toggle(self):
        self.playlist_clicked.emit()
```

再加一个把按钮显示成按下态的方法：

```python
    @pyqtSlot(bool)
    def set_playlist_panel_visible(self, is_visible):
        self.playlist_button.is_off = is_visible
```

- [ ] **Step 3: `VideoBlock` 转信号**

`video_block.py`：加信号 `playlist_panel_toggle = pyqtSignal()`；
`init_overlay` 的 `qt_connect` 加 `(overlay.playlist_clicked, self.playlist_panel_toggle.emit)`。

- [ ] **Step 4: 写管理器**

`app/gridplayer/player/managers/playlist_panel.py`：

```python
"""MOD: owns the playlist side panel and the per-block folder listings."""

from pathlib import Path

from PyQt5.QtCore import pyqtSignal, pyqtSlot

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.duration_probe import DurationProber
from gridplayer.utils.media_folder import scan_folder
from gridplayer.utils.play_history import PlayHistory
from gridplayer.widgets.playlist_panel import PlaylistPanel


class PlaylistPanelManager(ManagerBase):
    panel_visibility_changed = pyqtSignal(bool)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._history = PlayHistory()
        self._history.load()

        self._prober = DurationProber(parent=self)

        self._scans: dict[str, list] = {}
        self._block_id: str | None = None

        self._panel = PlaylistPanel(self.parent())
        self._panel.hide()
        self._panel.entry_activated.connect(self._play_entry)
        self._panel.sort_changed.connect(self._on_sort_changed)
        self._panel.set_history(self._history.as_mapping())

        self._panel.set_sort(
            Settings().get("player/playlist_sort_key"),
            Settings().get("player/playlist_sort_desc"),
        )

        splitter = self._ctx.layout_splitter
        splitter.insertWidget(0, self._panel)

        self._prober.duration_ready.connect(self._on_duration_ready)

    @property
    def commands(self):
        return {
            "toggle_playlist_panel": self.cmd_toggle,
            "is_playlist_panel_visible": lambda: self._panel.isVisible(),
        }

    # --- visibility ---

    def cmd_toggle(self):
        self.set_panel_visible(not self._panel.isVisible())

    def set_panel_visible(self, is_visible: bool):
        self._panel.setVisible(is_visible)
        self.panel_visibility_changed.emit(is_visible)

        if is_visible:
            self.refresh()

    # --- list building ---

    def on_active_block_changed(self, block):
        if block is None:
            return

        self._block_id = block.video_params.id
        self.refresh()

    def refresh(self):
        block = self._ctx.active_block
        if block is None or not self._panel.isVisible():
            return

        uri = block.video_params.uri
        if not isinstance(uri, Path):
            self._panel.set_entries([], None)
            return

        entries = scan_folder(uri)

        for i, e in enumerate(entries):
            cached = self._prober.cached(e)
            if cached is not None:
                entries[i] = e.with_duration(cached)

        self._panel.set_entries(entries, uri)
        self._prober.request(entries)

    # --- reactions ---

    @pyqtSlot(str, object)
    def _on_duration_ready(self, entry_key, duration_ms):
        self._panel.update_duration(entry_key, duration_ms)

    def _play_entry(self, path: Path):
        block = self._ctx.active_block
        if block is None:
            return

        self._history.record(str(path).casefold())
        self._history.save()

        self._panel.set_history(self._history.as_mapping())

        block.switch_video(Path(path))

    def _on_sort_changed(self, key, desc):
        Settings().set("player/playlist_sort_key", key)
        Settings().set("player/playlist_sort_desc", bool(desc))
        Settings().sync()

    def save_sort_settings(self):
        """Called on close so the next window starts with the same sorting."""
        Settings().set("player/playlist_sort_key", self._panel.sort_key)
        Settings().set("player/playlist_sort_desc", bool(self._panel.sort_desc))
        Settings().sync()

    def cleanup(self):
        self._prober.stop()
```

- [ ] **Step 5: 注册 manager 并接线**

`app/gridplayer/player/player.py`：
- import `PlaylistPanelManager`
- 在 `self.managers` 字典里，**放在 `"grid": GridManager,` 之后**：

```python
            "grid": GridManager,
            # MOD: must come after "grid" - it needs ctx.layout_splitter
            "playlist_panel": PlaylistPanelManager,
```

- 在 `self.connections` 里加：

```python
            "playlist_panel": [
                ("video_blocks.video_count_changed", "refresh"),
                ("s.arguments_received", "refresh"),
                # MOD: keep every block's hamburger button in its pressed state
                ("panel_visibility_changed", "video_blocks.set_playlist_panel_visible"),
            ],
            "active_block": [
                ("video_blocks.video_count_changed", "update_active_under_mouse"),
                ("active_block_change", "playlist_panel.on_active_block_changed"),  # MOD
            ],
            "video_blocks": [
                ("reload_all_closed", "video_driver.cleanup"),
                ("playlist_panel_toggle", "playlist_panel.cmd_toggle"),            # MOD
            ],
```

按钮的按下态还需要两级转发，照抄 `video_blocks` 已有的 `all_set_muted` 模式：

`VideoBlocksManager` 加一个普通方法（不是信号，因为源头已是信号）：

```python
    # MOD
    def set_playlist_panel_visible(self, is_visible):
        for vb in self._ctx.video_blocks:
            vb.set_playlist_panel_visible(is_visible)
```

`VideoBlock` 加：

```python
    # MOD
    def set_playlist_panel_visible(self, is_visible):
        self.overlay.set_playlist_panel_visible(is_visible)
```

（`OverlayBlock.set_playlist_panel_visible` 已在 Task 7 Step 2 里定义；
三个 overlay 变体都继承自 `OverlayBlock`，所以都具备这个方法。）

（`VideoBlocksManager` 需要把每格的 `playlist_panel_toggle` 转发出来；照抄它已有的
`all_volume_increase` 模式：在 `video_blocks.py` 的 `(signal, method)` 元组列表里加
`(self.playlist_panel_toggle, vb.playlist_panel_toggle)`，并在类里加同名信号。）

- [ ] **Step 6: 交互冒烟**

启动 `run_gridplayer.py`，播一个视频，鼠标移上去：
1. 底部出现三横杠按钮；点击 → 左侧面板出现、视频区域被挤窄。
2. 再点 → 面板收起、视频恢复满宽。
3. 面板里能看到同目录的其他视频；正在播的那条有高亮底色 + 左侧竖杠 + 「正在播放」徽标。
4. 单击另一条 → 换片，且「正在播放」跟着移动。

- [ ] **Step 7: 全量测试 + 回归**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 8: 排序设置跨窗口延续

**Files:**
- Modify: `app/gridplayer/player/managers/window_state.py`（关闭时顺带保存）
- Create: `tests/test_sort_persistence.py`

**Interfaces:**
- Consumes: Task 7 的 `PlaylistPanelManager.save_sort_settings()`
- Produces: 新窗口启动时读到上次的排序（已在 Task 7 的 `__init__` 里用 `Settings().get` 读取）

- [ ] **Step 1: 写测试**

`tests/test_sort_persistence.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import Checker, bootstrap

bootstrap()
c = Checker("sort persistence")

from gridplayer.settings import Settings
from gridplayer.widgets.playlist_panel import PlaylistPanel

# --- what the panel reads on construction must match what was stored ---
Settings().set("player/playlist_sort_key", "duration")
Settings().set("player/playlist_sort_desc", True)
Settings().sync()

panel = PlaylistPanel()
panel.set_sort(
    Settings().get("player/playlist_sort_key"),
    Settings().get("player/playlist_sort_desc"),
)
c.check("new panel adopts stored key", panel.sort_key == "duration", panel.sort_key)
c.check("new panel adopts stored direction", panel.sort_desc is True)

# --- and the panel writes them back ---
class Sink:
    def __init__(self, panel):
        self.panel = panel

    def save(self):
        Settings().set("player/playlist_sort_key", self.panel.sort_key)
        Settings().set("player/playlist_sort_desc", bool(self.panel.sort_desc))
        Settings().sync()


panel.apply_sort("mtime", False)
Sink(panel).save()
c.check("written back", Settings().get("player/playlist_sort_key") == "mtime"
        and Settings().get("player/playlist_sort_desc") is False)

# --- an unknown key in the settings file must not break a panel ---
Settings().set("player/playlist_sort_key", "nonsense")
Settings().sync()
panel2 = PlaylistPanel()
panel2.set_sort(Settings().get("player/playlist_sort_key"), False)
c.check("unknown stored key falls back to name", panel2.sort_key == "name",
        panel2.sort_key)

c.finish()
```

- [ ] **Step 2: 跑测试**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\tests\test_sort_persistence.py`
Expected: PASS（`apply_sort` 已把非法键回退成 `name`）

- [ ] **Step 3: 关闭时保存**

`window_state.py` 的 `closeEvent` 里，紧接着 `self._save_window_state()` 之后加：

```python
        self._save_window_state()

        # MOD: carry the playlist sorting over to the next window
        settings = Settings()
        settings.set("player/playlist_sort_key", self._ctx.playlist_sort_key())
        settings.set("player/playlist_sort_desc", self._ctx.playlist_sort_desc())
        settings.sync()
```

并在 Context 里注册两个取值函数（`PlaylistPanelManager.__init__` 里）：

```python
        self._ctx.playlist_sort_key = lambda: self._panel.sort_key
        self._ctx.playlist_sort_desc = lambda: bool(self._panel.sort_desc)
```

（`Context.__getattr__` 会对可调用值求值，所以这里存 `lambda` 正好。）

> 风险：`window_state.init()` 跑在 `playlist_panel` 之前，但 `closeEvent` 在运行时才触发，
> 那时两者都已存在。若关闭时 panel 尚未创建（例如极早期崩溃），
> `self._ctx.playlist_sort_key` 会抛 `KeyError` —— 用 `try/except KeyError` 包住并跳过保存。
> **必须加上这个保护，并写一条测试**：构造只有 `video_blocks` 的 Context，
> 断言 `closeEvent` 的这段逻辑不抛异常。

- [ ] **Step 4: 全量测试 + 回归**

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_runtests.py`
Expected: 全部通过

Run: `<repo>\pyenv\Scripts\python.exe <repo>\_selftest.py`
Expected: `==== 15/15 checks passed ====`

---

### Task 9: GUI 端到端验证

**Files:**
- Modify: 本计划文件（追加实测结果）
- 不改源码

- [ ] **Step 1: 面板外观**——打开面板截图，确认：文件夹路径显示、列头五个字段 + 排序箭头、
  当前项的高亮底色 + 左侧竖杠 + 「正在播放」徽标、副行显示 `大小 · 日期 · 时长`。

- [ ] **Step 2: 五维排序各截一张**——点每个列头，确认顺序变化符合预期；再点一次确认升降序翻转；
  特别确认**「历史」和「时长」的未知项始终在最后**（这是用户明确要求的口径）。

- [ ] **Step 3: 时长回填**——在一个含 10 个以上视频的文件夹里打开面板，
  确认列表**立刻**出现、时长先显示 `—`，随后逐个变成真实时长；
  关掉再打开，确认**直接就是缓存值**（不再出现 `—`）。

- [ ] **Step 4: 换片**——单击列表里另一条，确认换了视频、且「正在播放」跟着移动。

- [ ] **Step 5: 多格独立**——拖两个视频进同一窗口，确认：切到另一格时面板内容跟着换成那一格的文件夹；
  两格的列表互不干扰。

- [ ] **Step 6: 排序跨窗口**——把排序改成「日期 降序」→ 关闭 → 重新打开 → 确认新窗口直接是「日期 降序」。

- [ ] **Step 7: 网格回归再跑一遍**（同 Task 5 Step 5 的六项），确认面板开合不影响网格。

- [ ] **Step 8: 把结果与截图路径追加到本计划文件，结束本期**
