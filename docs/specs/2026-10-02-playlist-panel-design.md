# 设计规格：每格播放列表面板 + 播放顺序按钮 + 窗口状态记忆

- 日期：2026-10-02
- 目标工程：`<repo>`（GridPlayer 0.5.5 源码版改版）
- 状态：设计已与用户确认，待实现

---

## 1. 背景与目标

在已改版（记住音量、关闭不询问）的 GridPlayer 上再加三块能力：

1. **每格独立播放列表面板**：窗口左侧的面板，列出该格视频所在文件夹里的所有视频，
   支持五种维度排序，左键单击切换播放，正在播放的项有明确区分。
2. **播放顺序按钮**：播放条右侧的按钮，快捷切换该格视频的播放顺序（四种模式）。
3. **窗口状态记忆**：记住上次关闭时的屏幕/位置，以及是全屏还是窗口。

## 2. 已确认的决策

| 决策点 | 结论 | 来源 |
|---|---|---|
| 列表归属 | **每个视频格子一个列表**，活跃格变化时面板切换到该格的列表 | 用户答复 |
| 播放历史口径 | 按「上次播放时间」倒序；需要跨会话持久化；没播过的排最后 | 用户答复 |
| 时长排序 | 做，**异步探测 + 磁盘缓存**，未探到的显示 `—` 并排最后 | 用户答复 |
| 布局做法 | **做法 A**：网格移到子控件 `grid_host`，`Player` 上装 `QSplitter` | 用户答复 |
| 排序设置持久化 | 每窗口一份，关闭时落盘，下次新窗口沿用（与音量同机制） | 用户要求 |
| 播放顺序默认值 | 列表循环（用户当前配置 `repeat=dir` 已符合） | 用户要求 |
| 面板开关状态 | **不做持久化**，每次启动默认收起 | 本设计 |

## 3. 架构

### 3.1 布局重构（做法 A）

现状：`GridManager.__init__` 里 `self._grid = QGridLayout(self.parent())` —— 网格布局直接装在
`Player` 窗口上（`grid.py:58`），一个 widget 只能有一个布局，所以左侧栏没有位置。

改为：

```
Player
└─ QSplitter(Horizontal)            ← 新建，装在 Player 上
   ├─ PlaylistPanel                 ← 新建，默认宽 280 / 最小 200，可拖动
   └─ grid_host (QWidget)           ← 新建
      └─ QGridLayout                ← 原来是装在 Player 上的那个
```

需要改 `GridManager` 的引用：

| 原引用 | 改为 |
|---|---|
| `QGridLayout(self.parent())` | `QGridLayout(self._grid_host)` |
| `QLabel(..., parent=self.parent())`（`_info_label`） | `parent=self._grid_host` |
| `self.parent().setUpdatesEnabled(...)`（`slow_ui_operation`） | 保持 `self.parent()`（整窗冻结重绘是对的） |
| `minimum_size_changed.emit(...)`（`_adjust_window`） | 保持，但最小宽度要加上面板宽度 |

`GridManager` 负责建立 `QSplitter` 与 `grid_host`，并把两者放进 `self._ctx`
（`grid_host` / `layout_splitter`），供后创建的 `PlaylistPanelManager` 把面板插到索引 0。
这样 `GridManager` 不需要知道面板的存在。

> **隐含约束（必须遵守）**：manager 按 `Player.managers` 字典顺序实例化
> （`player.py:38-58` → `_init_managers_instances`），而 `grid` 目前排第 4。
> 因此 `playlist_panel` 必须排在 `grid` **之后**，否则创建面板时
> `self._ctx.layout_splitter` 尚不存在（`Context.__getattr__` 会抛 `KeyError`，不是 `AttributeError`）。

**最小宽度**：`_adjust_window()` 现在算 `cols × 100`（`PLAYER_MIN_VIDEO_SIZE`），
面板可见时最小宽度需 `+ panel.minimumWidth()`。通过 `minimum_size_changed` 继续走
`window_state.set_minimum_size`。

### 3.2 新增组件

| 组件 | 路径 | 职责 |
|---|---|---|
| `MediaEntry` | `models/media_entry.py` | 目录项数据：`path / name / size / mtime / duration_ms(None 未探到)` |
| 目录扫描 | `utils/media_folder.py` | `scan_folder(video_path) -> list[MediaEntry]`，扩展名判据复用 `params/extensions.py` 的 `SUPPORTED_MEDIA_EXT`（与 `utils/next_file.py::_file_siblings` 一致） |
| 播放历史 | `utils/play_history.py` | 读写 `data/play_history.json`：`路径 -> 最近播放时间戳(ms)`；带上限裁剪 |
| 时长缓存 + 探测 | `utils/duration_probe.py` | 读写 `data/duration_cache.json`；`QThread` 后台逐个探测，逐个发信号回填 |
| 面板控件 | `widgets/playlist_panel.py` | `PlaylistPanel`：列头 + 列表 + 委托绘制 |
| 面板管理 | `player/managers/playlist_panel.py` | `PlaylistPanelManager`：持有面板、按活跃格建/切列表、接线按钮 |
| 两个 overlay 按钮 | `widgets/video_overlay_buttons.py` | `OverlayPlaylistButton`、`OverlayRepeatButton` |
| 四个新图标 | `widgets/video_overlay_icons.py` | `draw_menu`、`draw_repeat_single`、`draw_repeat_list`、`draw_repeat_shuffle`、`draw_repeat_pause` |

### 3.3 数据流

**打开/切换列表**
```
活跃格变化 (ActiveBlockManager.active_block_change)
  → PlaylistPanelManager 取该 block 的 video_params.uri
  → scan_folder(uri)  （按 block id 缓存扫描结果）
  → 按当前排序键排序（含 play_history / duration_ms）
  → PlaylistPanel.set_entries(entries, current_path)
  → DurationProbe 把未知时长的路径入队
  → 探到后 emit(duration_ready) → 面板局部刷新 + 若按长度排序则重排
```

**点击项**
```
PlaylistPanel.entry_activated(path)
  → PlaylistPanelManager 找到对应 block → block.switch_video(path)
  → 现有链路：switch_video → 换片 → 记录播放历史
```

**播放顺序按钮**
```
OverlayRepeatButton.clicked
  → OverlayBlock.repeat_clicked
  → VideoBlock 信号 → VideoBlocksManager
  → block.set_repeat_mode(下一个模式)  （已有的 per-block 方法）
```

**关闭落盘 / 启动回填**
```
closeEvent (已有 _save_last_volume 的位置)
  → 保存 player/volume（已有）
  → 保存 player/playlist_sort_key / _desc
  → 保存 player/window_geometry / _maximized / _fullscreen

WindowStateManager.init()（在 Player.show() 之前）
  → 读三个 window_* → 构造 WindowState → 复用 restore_window_state()
```

## 4. 功能规格

### 4.1 面板与列表

- 位置：窗口左侧，`QSplitter` 左栏；默认 280px，最小 200px，可拖动。
- 面板隐藏时空间自动还给视频（`QSplitter` 对隐藏子控件的行为）。
- 列表内容：该格当前视频所在文件夹下所有受支持媒体文件（不含子目录）。
- 列表项渲染：
  - 主行：文件名，过长按宽度省略。
  - 副行：`大小 · 修改日期 · 时长`（时长未探到显示 `—`）。
  - **正在播放**：高亮底色 + 左侧竖杠 + `正在播放` 徽标（三项同时具备）。
- 交互：左键单击即播放；双击等同单击。
- 面板顶部有一行标题，含当前文件夹名。
- **入口按钮**：`OverlayBlock.bottom_bar` 中，插在进度条与音量键之间（`video_overlay.py:150-154`），
  图标为三横杠，切换式（按下态高亮）。
- 因为 overlay 是每格一个，任一格上的三横杠都切换**同一个窗口级面板**；
  面板内容取决于当前活跃格。

### 4.2 排序

- 五个维度：`name` / `size` / `mtime` / `history` / `duration`。
- 顶部一行可点击列头，点当前列切换升降序，点其他列切字段（默认升序）；箭头指示方向。
- 排序规则：
  - `name`：不区分大小写的**自然序**。实现口径：把文件名切成「数字段 / 非数字段」交替的序列，
    数字段按整数比较、非数字段按 `casefold()` 比较，逐段比较。使 `GridPlayer 2` 排在 `GridPlayer 10` 前。
  - `size` / `mtime`：数值比较。
  - `history`：按最近播放时间戳比较（降序即最近播的在前）。
  - `duration`：按毫秒数值比较。
- **未知值恒排最后**：`history` 无记录的项、`duration` 未探到的项，
  无论升序降序都排在所有已知项之后（这是用户明确要求的口径，不随方向翻转）。
- 并列时以 `name` 自然序做稳定兜底，避免顺序抖动。
- 排序设置每窗口一份（各格列表共用），关闭落盘、下次新窗口沿用。

### 4.3 时长探测（异步 + 缓存）

- 缓存文件 `data/duration_cache.json`：`路径 -> {size, mtime, duration_ms}`；
  `size`/`mtime` 与当前文件不一致即视为失效，重新探测。
- 探测在后台 `QThread` 中逐个进行，主进程内创建一个专用 `vlc.Instance`（`--no-video --no-audio`），
  用 `media_new` + `parse_with_options` + `get_duration`。
- 结果逐个回填面板；写盘做去抖（批量或定时落盘），避免频繁 IO。
- 探测队列去重；面板切换到新文件夹时重排队列，优先探测当前列表。
- 单文件探测超时（默认 5s）即放弃并记为未知，不阻塞队列。

### 4.4 播放历史

- 文件 `data/play_history.json`：`路径 -> 最近播放时间戳(ms)`。
- 写入时机：某格开始播放一个新文件时（`add_videos` 与 `switch_video` 两条路径都要覆盖）。
- 上限：保留最近 5000 条，超出按时间裁剪。
- 路径规范化（绝对路径 + 大小写归一）后作为键，避免同一文件重复记录。

### 4.5 播放顺序按钮

现有 `VideoRepeat` 只有三态（`params/static.py:53`）：

| 现有/新增 | 值 | 语义 | 图标 |
|---|---|---|---|
| 现有 | `SINGLE_FILE` | 单集循环：播完回到 loop_start | 顺时针箭头内嵌 `1` |
| 现有 | `DIR` | 列表循环：播完播目录下一个（到末尾回第一个） | 顺时针箭头 |
| 现有 | `DIR_SHUFFLE` | 随机播放：播完随机切目录里另一个 | 交叉箭头 |
| **新增** | `PAUSE_AT_END` | 播完暂停：播完停住不动作 | 顺时针箭头内嵌暂停三角 |

- `widgets/video_block.py::loop_end_action` 增加分支：`PAUSE_AT_END` 时什么都不做
  （显式 loop_end 的优先级保持最高，与现状一致）。
- 按钮位置：`[播放/暂停][时间][进度条][顺序键][列表键][音量]`。
- 左键单击循环切换四种模式；tooltip 显示当前模式名。
- 作用范围：**仅该格**（用已有的 per-block `set_repeat_mode`）。
- 图标用 `QPainter` 手绘，沿用 `video_overlay_icons.py` 现有的 `draw_*(rect, painter, color_fg, color_bg)` 风格。
- 连带改动：设置对话框的 repeat 下拉（`dialogs/settings.py:306-312`）补第四项；
  `params/actions.py` 的 per-video（276-298）与 all（928-940）各补一条菜单项。

### 4.6 窗口状态记忆

- 新增设置：`player/window_geometry`(str，base64) / `player/window_maximized`(bool) / `player/window_fullscreen`(bool)。
- 关闭时写入（`WindowStateManager.closeEvent`，与音量保存同一处）。
- 启动回填：`WindowStateManager.init()` —— 该处在 `Player.show()` 之前
  （`player.py:158` 的 `self.init()` 是 `__init__` 最后一步），
  读三个设置构造 `WindowState` 后复用已有的 `restore_window_state()`。
- 多显示器：`saveGeometry`/`restoreGeometry` 原生保留屏幕与相对位置。
- **首次运行 / 几何为空**：`player/window_geometry` 为空串时不做任何恢复，走 Qt 默认。
- **保险**：若恢复出的矩形中心不在任何当前屏幕内（显示器拔掉/分辨率变了），
  放弃位置，回落默认尺寸并居中。
- 语义：与音量一致 —— 最后一次关闭的窗口状态生效；同时开着的其他窗口不受影响。

## 5. 新增设置项

| 键 | 类型 | 默认 | 用途 |
|---|---|---|---|
| `player/playlist_sort_key` | str | `"name"` | 排序维度 |
| `player/playlist_sort_desc` | bool | `False` | 是否降序 |
| `player/window_geometry` | str | `""` | 窗口几何（base64） |
| `player/window_maximized` | bool | `False` | 关闭时是否最大化 |
| `player/window_fullscreen` | bool | `False` | 关闭时是否全屏 |

（`_default_settings` 的类型驱动 get/set 只原生支持 str/bool/float/int，
故窗口状态拆成三个基础类型，而不是塞一个 `WindowState` 命名元组。）

## 6. 测试计划

**自动化（扩写 `_selftest.py`，无 GUI）**
- 五种排序键 × 升降序的结果正确性（含并列兜底、未探到时长恒排最后、无历史视为最旧）。
- 自然序排序（`2` 在 `10` 前）。
- 播放历史：写入、读取、上限裁剪、路径规范化。
- 时长缓存：命中、失效（size/mtime 变化）、落盘/读取。
- 窗口状态：三个设置的读写往返；离屏几何的回退判定。
- `PAUSE_AT_END` 加入后 `VideoRepeat` 的字符串值兼容（旧配置仍可解析）。
- 已有 15 项回归全绿。

**GUI 验证**
- 截图：面板打开态（含"正在播放"项的高亮/竖杠/徽标）、四种顺序图标各一张。
- 单击列表项确实换片（日志 + 截图）。
- 活跃格切换时面板内容切换（双画面场景）。
- 窗口记忆：改成非默认位置 + 最大化关闭 → 重开确认；再测全屏。
- 网格回归：1 / 2 / 4 画面、单画面模式、改网格尺寸、面板开合时视频区域尺寸正确。

## 7. 风险与退路

| 风险 | 退路 |
|---|---|
| 主进程内新建 `vlc.Instance` 探测时长与播放器进程冲突 | **先做独立 spike 验证**；不行则把探测移到 worker 进程；再不行砍掉时长排序（其余四项照做，如实告知） |
| 布局重构（做法 A）影响网格尺寸/最小尺寸 | 改完全量跑网格回归；必要时退回做法 B（左边距挤空间） |
| 大目录（>2000 文件）列表卡顿 | 委托绘制 + 按需构建；必要时加虚拟化（`QListView` + model） |
| 新增枚举成员影响旧配置解析 | `AutoName` 按字符串存，旧值仍可解析；加测试覆盖 |

## 8. 实现分期

三块能力彼此独立，按「小 → 中 → 大」分三期落地，每期独立可验证、可交付：

| 期 | 内容 | 依赖 | 可独立验收 |
|---|---|---|---|
| **P1** | 窗口状态记忆（4.6 + 5 中三个 `window_*`） | 无 | 改位置/最大化/全屏关闭 → 重开一致 |
| **P2** | 播放顺序按钮（4.5：新枚举 + `loop_end_action` + 两个 overlay 按钮位置 + 四个图标 + 设置/菜单补项） | 无 | 四态切换 + 图标正确 + 播完行为正确 |
| **P3** | 播放列表面板（3.1 布局重构 + 4.1/4.2/4.3/4.4 + 面板组件与管理器） | 布局重构 | 面板/排序/历史/时长/换片 |

P3 内部再做两步走：先 `utils/` 侧（扫描、历史、时长缓存与探测，可脱离 GUI 用 `_selftest.py` 验证），
再做 UI 侧（面板控件、管理器、布局重构、接线）。

P1/P2 先做，能让改动早点可用，也降低 P3 布局重构出问题时的排查面。

## 9. 不在本次范围

- 面板开关状态的持久化。
- 跨窗口共享的排序/历史设置（本次为每窗口 + 全局落盘）。
- 列表的搜索/过滤、右键菜单（如"在资源管理器中显示"）。
- 拖拽重排列表顺序。
