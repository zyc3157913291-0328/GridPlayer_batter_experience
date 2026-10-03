# mpv 播放驱动 —— 设计文档

- 日期：2026-10-04
- 状态：**待评审**
- 前置结论（spike，已实测）：见 §1

---

## 1. 背景与已确证的事实

### 1.1 要解决的问题

GridPlayer 在**改变播放速率时音频会短暂中断**。

### 1.2 已经排除的原因（全部实测）

| 试过的方向 | 实测结果 |
|---|---|
| 换音频输出模块（directsound → mmdevice） | 日志错误归零，**断音照旧** ✗ |
| 关闭时间伸缩 `--no-audio-time-stretch` | 音调变了（证明确实生效），**断音照旧** ✗ |
| 换重采样器 `--audio-resampler=soxr` | **无效** ✗ |
| 把变速做成 150 ms 平滑斜坡 | **更糟**（10 次调用 = 10 次扰动）✗ |
| 减少调用次数（只在挡位变化时发） | 单次切换照样断 ✗ |
| 升级 libVLC 3.0.21 → 3.0.24（官方稳定版） | 断音照旧 ✗ |

**结论：** 病根在 libVLC 音频输出的"变速即重新对时并冲掉缓冲"这一实现里，**libVLC 不把音频管线的控制权交给上层**，因此在 libVLC 之上无法解决。

### 1.3 决定性对照（spike）

同一台机器、同一套 Windows 音频接口、同一个文件：

| 播放器 | 变速表现 |
|---|---|
| GridPlayer（libVLC 3.0.24） | 每次切换都断 |
| **mpv v0.41.0** | **完全不断，且音调不变** |
| B 站网页版 / 夸克（Chromium） | 不断 |

mpv 与 Chromium 的共同点：**在自己的混音器里重采样，不重建输出设备**。

### 1.4 因此

**换播放引擎到 mpv 是唯一能真正解决该问题的方向**，且 mpv 与 libVLC 在依赖形态上完全对等（外部运行时 + 官方发布 + 可放仓库目录）。

---

## 2. 目标与非目标

### 目标

1. **新增一个 mpv 播放驱动**，可作为 `player/video_driver` 的一个取值被选中。
2. 变速（挡位、长按手势、C/X/Z）在 mpv 驱动下**无断音**。
3. 现有 **UI 层与 MOD 功能完全不动**：浮层控件、播放列表面板、单屏标签栏、长按手势、重复模式、窗口记忆等，全部照常工作。
4. 满足仓库既定的三条改动准则：**可移植 / 少依赖 / 模块化**。

### 非目标（明确不做）

- ❌ 不替换、不修改现有 4 个 VLC 驱动（`vlc_hw` / `vlc_hw_sp` / `vlc_sw` / `dummy`）
- ❌ 不改 `vlc_player/` 包与 vendored `vlc.py`
- ❌ **不改语言**：全部保持 Python；不引入 C 扩展、不新增需要编译的产物
- ❌ 不改 UI / 浮层 / 面板 / 手势的任何代码
- ❌ 不删除 libVLC（两条引擎并存，用户可切）
- ❌ **不管 4K60 高码率视频的播放性能**：那是"视频输出模块吞吐"的问题（曾用 `--vout=direct3d9` 调查过），**与变速音频中断无关** —— 后者在任何文件上都复现（包括 320×240 的正弦波）。原先用于复现的那个 4K60 文件已从本机删除，且该问题不在本次范围内

---

## 3. 方案选型

| 方案 | 评价 |
|---|---|
| **A. 新增 `mpv` 驱动（选定）** | GridPlayer 本就是可插拔驱动架构（现有 4 个驱动）。新增驱动 = 枚举加一项 + 字典加一行。**风险隔离、可随时切回、符合模块化** |
| B. 整体替换 libVLC | 要动 21 个引用文件 + 1217 行 `vlc_player/`，一次性风险，违背模块化 |
| C. 自己接管音频输出 | 需手写 WASAPI 后端并重写 A/V 同步，研究级项目，违背模块化与少依赖 |

**选定 A。**

---

## 4. 架构

### 4.1 在现有架构中的位置

现有驱动注册点（已核实）：

- `params/static.py:81` —— `class VideoDriver(AutoName)` 枚举
- `player/managers/video_driver.py:16` —— `_video_drivers` 字典（枚举 → VideoFrame 类）
- `player/managers/video_driver.py:24` —— `_instance_processes` 字典（枚举 → 子进程类）
- `player/managers/video_driver.py:28` —— `_multiprocess_drivers` 集合

驱动必须实现的接口（已核实，共约 18 项，`vlc_player/video_driver_base.py`）：

```
load_video(media_input)     play()                    cleanup()
set_pause(is_paused)        set_time(seek_ms)         set_playback_rate(rate)
audio_set_mute(is_muted)    audio_set_volume(volume)  set_audio_channel_mode(mode)
set_audio_track(id)         set_video_track(id)       snapshot()
+ 状态上报：time_changed_emit / playback_status_changed_emit /
  snapshot_taken_emit / update_status_emit / error_state / load_video_done
```

### 4.2 进程模型：沿用现有的"每视频一个子进程"

GridPlayer 已经是**每个视频块一个播放子进程 + 命令管道 + 一个原生窗口**（`process_manager.init_player(...)`，见 `video_frame_vlc_hw.py`）。mpv 驱动的子进程内：

```
mpv 子进程（与 VLC 驱动的子进程同级）
 ├─ libmpv 实例（wid=<Qt 提供的原生窗口句柄>）
 ├─ vendored 的 python-mpv 绑定（ctypes，进程内直接调用）
 └─ GridPlayer 命令管道（沿用现有 cmd_send / cmd_child_pipe 机制，一行不改）
```

**契合点**：现有架构本来就是"每视频一个子进程 + 一个原生窗口" ✓ —— libmpv 只需要两样东西：**一个窗口句柄** ✓ 和**一个进程** ✓ 两样都已具备 ✓

### 4.3 用 libmpv + **vendored 绑定**

本仓库**已经把 `python-vlc` 的 `vlc.py`（10127 行）vendored 进仓库**（`gridplayer/vlc_player/vlc.py`）。对 mpv 采用**完全同构**的做法：vendored 一份 python-mpv 绑定。

| | libmpv + vendored 绑定（选定） | JSON IPC 到 `mpv.exe` |
|---|---|---|
| 与现有模式 | **和 `vlc.py` 完全同构** | 新造一层 IPC |
| 新增文件 | 一个 vendored 绑定 | 一个 IPC 客户端 |
| 延迟 | 直接 API 调用 | 每命令一次往返 |
| 属性观察 | 原生 `observe_property` 回调 | 协议层 `observe_property` |
| 运行时 | **`libmpv-2.dll`（纯库，小）** | `mpv.exe`（含完整前端，重） |

**"依赖"的判定口径**（本次与用户确认）：判据是**能不能随仓库一起带走**，而不是"是不是第三方写的"：

- `python-mpv`（纯 Python 的 ctypes 绑定）→ **不算依赖**，vendored 进仓库，与 `vlc.py` 同理
- `libmpv-2.dll` → 与 `libVLC\` **完全对等**的运行时，部署时随 `mpv\` 目录提供
- 7-Zip 之类的解包工具 → 只出现在"如何获取运行时"的说明里，**不是运行时依赖**，且优先用系统自带能力

**M0 必须先核实**：vendored 绑定的许可证与仓库的 GPL-3.0 兼容（python-mpv 声称为 MIT；MIT → GPL-3.0 兼容，但**必须实际核对**，并把出处与版本写进 README 致谢）

### 4.4 窗口嵌入

- 与 `vlc_hw` 同一做法：`video_surface.winId()` 得到的原生句柄直接交给 libmpv（`wid` 选项）。
- **`--wid` 的可用性由 mpv 官方文档保证，但本机可用性未实测** → 这是 **M0 的门槛项**（见 §8 风险 1）。
- 其余与 VLC 驱动一致：窗口由子进程持有，主进程只负责摆位置。

---

## 5. VLC → mpv 接口映射

| 驱动接口 | VLC 现做法 | libmpv 对应（python-mpv 绑定） |
|---|---|---|
| `load_video` | `media_new` + `set_media` + `play` | `mpv.command("loadfile", path)` |
| `play` / `set_pause` | `play()` / `set_pause()` | `mpv.pause = False / True` |
| `set_time` | `set_time(ms)` | `mpv.command("seek", s, "absolute")` |
| **`set_playback_rate`** | `set_rate(r)` | **`mpv.speed = r`** ← 问题解决处 |
| `audio_set_mute` | `audio_set_mute` | `mpv.mute = bool` |
| `audio_set_volume` | `audio_set_volume` | `mpv.volume = 0..100` |
| `set_audio_track` / `set_video_track` | 按 track id 选择 | `mpv.aid = id` / `mpv.vid = id` |
| `set_audio_channel_mode` | `audio_set_channel` | `mpv["audio-channels"] = mode` |
| `snapshot` | `video_take_snapshot` | `mpv.command("screenshot-to-file", path)` |
| 进度 / 时长 | `get_time` / `get_length` | 属性 `time-pos` / `duration` |
| 播放状态 | event manager | `mpv.observe_property("pause" / "eof-reached" / "idle-active", cb)` |
| 轨道列表 | `video_tracks` / `audio_tracks` | 属性 `track-list` |

**不再需要**：`image_decoder.py`（已核实**只有 `vlc_sw` 驱动在用**，mpv 驱动用不到）。

---

## 6. 需要改动/新增的文件

**新增：**

- `gridplayer/mpv_player/__init__.py`
- `gridplayer/mpv_player/mpv.py` —— **vendored 的 python-mpv 绑定**（ctypes，与 `vlc_player/vlc.py` 同性质同位置策略）
- `gridplayer/mpv_player/player_mpv.py` —— 子进程侧：持有 libmpv 实例、把 GridPlayer 命令翻译成 libmpv 调用、把 mpv 属性变化翻译成状态上报
- `gridplayer/mpv_player/video_driver_mpv.py` —— 主进程侧驱动类，实现 §4.1 的接口
- `gridplayer/widgets/video_frame_mpv.py` —— VideoFrame 类（提供原生窗口句柄、驱动装配）
- `gridplayer/utils/mpv_finder.py` —— 定位 `libmpv-2.dll`（与现有 `utils/libvlc_fixer.py` 同构，**相对仓库根查找**）
- `tests/check_mpv_driver.py` —— 驱动行为检查（沿用 `check_*.py` 约定）

**修改（点状，共 5 处）：**

- `params/static.py:81` —— `VideoDriver` 枚举 + `MPV = auto()`
- `player/managers/video_driver.py` —— `_video_drivers` / `_instance_processes` / `_multiprocess_drivers` 各加一项
- `dialogs/settings.py`（**两处**，已核实）—— 驱动选择列表（约 31 行）与显示名映射（约 327~336 行，现格式为 `Hardware <VLC 3.0.24>`，mpv 项按同格式给 `mpv <0.41.0>` 之类）
- `player/managers/settings.py:56` —— 确认驱动变更能触发重载（已存在，预计无需改，实施时验证）
- `README.md` —— 新增功能说明 + mpv 运行时的获取方式（与 libVLC 并列）

**明确不改：** `vlc_player/`、`widgets/video_frame_vlc_*.py`、`widgets/video_overlay*.py`、`widgets/video_block.py`、`player/managers/playlist_panel.py`

---

## 7. 可移植性与依赖（对应三条准则）

### 可移植

- mpv 运行时**与 libVLC 完全对等**：放在仓库根目录的 `mpv\`（gitignore，与 `libVLC\` 同级同策略）。
- 定位逻辑与 `utils/libvlc_fixer.py` 同构：**相对仓库根**查找，**不写任何本机绝对路径**。
- 部署时最多确认一次"mpv 放在哪"，与现在确认"libVLC 放在哪"是同一件事。
- README 给出**可复现的获取方式**（官方发布 + 同一条 `msiexec /a` 思路不适用则用官方 7z + 解压），换机器照跑。

### 少依赖

- **零新 Python 运行时包**：python-mpv 是**纯 Python 的 ctypes 绑定**，vendored 进仓库（与现有 `vlc.py` 同性质）；`libmpv-2.dll` 是与 `libVLC\` **完全对等**的运行时。
- **判定口径**（与用户确认）：判据是**能不能随仓库/安装包一起带走**，不是"是不是第三方写的"。能带走的（pip 包源码、纯 Python 绑定）不算依赖；不能带走的（必须由用户机器提供的东西）才算，而 mpv 与 libVLC 在这条上地位相同。
- 7-Zip 之类的**解包工具**只在"如何获取运行时"的说明里出现，**不是运行时依赖**，且优先用系统自带能力（`msiexec /a` 等）。
- **保持 Python**：不引入 C 扩展、不新增需要编译的产物。

### 模块化

- 新增代码集中在 `mpv_player/` + 3 个文件；现有 `vlc_player/` **零改动**。
- 注册只需在 3 个字典/枚举里各加一项（已核实），加上设置界面 2 处。
- UI 层通过既有抽象与驱动交互，**无需为 mpv 做任何适配**。

---

## 8. 风险与未验证项（必须在实施早期实测）

| # | 风险 | 验证方式 | 失败时的退路 |
|---|---|---|---|
| 1 | **`wid` 嵌入 Qt 原生窗口在本机可用性（门槛项）** | 最小 spike：libmpv 嵌进 QWidget 并播放 | 不可用则本设计作废，重新选型 |
| 2 | **vendored 绑定的许可证**是否与 GPL-3.0 兼容 | 读上游 LICENSE 原文，写进 README 致谢 | 不兼容则自写最小 ctypes 绑定（约 200 行） |
| 3 | 轨道枚举（`track-list`）与上游 track id 的对应 | 与 `player_tracks_manager.py` 的断言对齐 | 自建 id 映射 |
| 4 | seek 语义差异（VLC `set_time` vs libmpv `seek absolute`） | 循环 seek 与边界用例 | `hr-seek` 等选项 |
| 5 | 高频操作（拖动进度条）下的响应表现 | 压力测试 | 命令合并 |
| 6 | 音量/静音在 libmpv 是软件音量还是系统音量，需与现有行为一致 | 对照 VLC 驱动的表现 | `volume-max` / `ao-volume` |
| 7 | 截图路径与格式是否与现有 `snapshot` 行为一致 | 比对文件名与格式 | 后处理 |
| 8 | 原本用于复现高码率卡顿的 4K60 文件已删除 | —— | **不涉及**：该问题与变速音频中断无关，且不在本次范围内（见 §2 非目标） |

**风险 1 是门槛项：先做它，不通过则本设计作废。**

---

## 9. 测试策略

- **纯逻辑可测**：vendored 绑定的加载、命令翻译表、属性→状态的映射 → `tests/check_mpv_mapping.py`，沿用现有 `check_*.py` 约定（模块级跑完即退出，**不用 `test_` 前缀**）。
- **驱动行为**：用真实 libmpv 实例，断言播放/暂停/跳转/速率/轨道等状态回报 → `tests/check_mpv_driver.py`。
- **变速无断音**：这是本次改动的**唯一目的**，必须留一个可复现的客观记录；由于此前证明"日志指标与听感不相关"，此项以**人工试听**为验收判据，并在文档中写明。
- **回归**：`_runtests.py`（现 22 个文件）与 `_selftest.py` 必须保持全绿；**VLC 驱动路径不得受影响**。

---

## 10. 验收标准

1. 设置里能把 `player/video_driver` 选为 mpv，重启后生效。
2. 用 mpv 驱动播放时：**挡位切换、长按手势、C/X/Z 变速均无断音**（人工试听确认）。
3. 播放/暂停/跳转/进度/时长/音量/静音/轨道/截图在本机复测通过，与 VLC 驱动行为一致。
4. 现有 MOD 功能全部照常：浮层控件、播放列表面板、单屏标签栏、长按手势、Alt+拖动、重复模式。
5. 现有全部检查（22/22）与自检（15/15）保持通过。
6. 仓库内**不出现任何本机绝对路径**；换机器只需放置 `mpv\` 目录。

---

## 11. 分期（建议）

| 期 | 内容 | 出口条件 |
|---|---|---|
| **M0** | 门槛项：① libmpv 能否嵌进 Qt 窗口 ② vendored 绑定许可证是否与 GPL-3.0 兼容 | 两项都过 → 继续；任一不过 → 作废或改自写绑定 |
| **M1** | IPC 客户端 + 子进程骨架 + 播放/暂停/跳转/变速 | 一个视频能播、能变速、**试听无断音** |
| **M2** | 轨道、音量、静音、截图、状态回报完整 | 与 VLC 驱动行为对齐 |
| **M3** | 接入设置界面、README、测试补齐 | 验收标准全过 |

**M1 结束时就能回答"这事成不成"**，因此建议 M0 → M1 先做，再决定是否投入 M2/M3。

---

## 11a. M0 结论（2026-10-04，**两项均已通过**）

### M0-a 许可证 —— **通过** ✅

`python-mpv` 的 `mpv.py` 文件头原文：

> "You may copy, modify, and redistribute this file under the terms of the GNU General Public License version 2 (**or, at your option, any later version**), or the GNU Lesser General Public License…"

即 **GPL-2.0-or-later**（且双许可含 LGPL）→ **与仓库的 GPL-3.0 兼容**，**可以 vendored**。仓库 LICENSE 文件为 GPL-2.0（`LICENSE.GPL`），但"or later"条款使其可并入 GPL-3.0 工程。

**待办**：README 致谢里写明出处（`jaseg/python-mpv`）、版本/commit 与许可证。

### M0-b `wid` 嵌入 —— **通过** ✅

用系统自带 WinForms 造一个**洋红色**的宿主窗口，把句柄交给 `mpv.exe --wid=<hwnd>`：**窗口先呈纯洋红，随后视频画面出现在其中**（用户目视确认）→ mpv 确实把画面渲染进了**别人的窗口**。

宿主窗口由 Windows 自带组件创建（非 Qt）即可成立，说明这与 Qt 无关，是 mpv 的 `vo` 能力。

### 过程中的一个教训（值得记下）

我第一次测 `wid` 时给出过两个"客观证据"（"采样到 40 种颜色"、"洋红像素 0 个"），**两次都是错的**：截屏抓到的是别的窗口，指标量错了对象。两次都靠**把截屏图片调出来看**才发现。

**结论：这类"看起来客观"的间接指标，必须配一次直接观测（看图 / 目视）才可信。** 这与 §9 中"日志指标与听感不相关"的教训是同一件事。

### 已就位的 M1 资产（临时目录，不进仓库）

| 资产 | 来源 | 校验 |
|---|---|---|
| `libmpv-2.dll`（115.2 MB） | 官方 `mpv-dev-x86_64-20261003` 发布包 | sha256 `b8c2d656c1584d5f08196fcee5c2d0783d1f76021897c4e0b3cc30f94c79522e` |
| `mpv.exe`（115.2 MB） | 官方 `mpv-x86_64-20261003` 发布包 | sha256 `0f616bde3216dd14a0e460892f346406ad976163c47fb49a8e2ea079cca73699` |
| 官方 7-Zip 26.03（仅用于解包，非运行时依赖） | winget `7zip.7zip` 的 MSI，`msiexec /a` 解出 | — |

---

## 12. 最终形态：可选的 M4 —— 移除 VLC

有一个合理的终局目标：**只留一个引擎**（少一套运行时、少一套代码、设置里不再需要选）。

### 12.1 代价的量化（实测）

`resources_bin.py` 的 142,166 行是**生成的资源数据**（图标等），不计入代码。据此：

| | 文件 | 行 |
|---|---|---|
| 移除 VLC 会删掉 | **21** | **12,337** |
| ↳ 其中 vendored `vlc.py`（机械生成的绑定，非项目代码） | 1 | 10,127 |
| ↳ **真正被删掉的项目代码** | 20 | **约 2,210** |
| **保留** | **125** | **约 14,400** |

**换算：移除 VLC 后约 85% 的项目代码原样保留。**

之所以代价这么小，是因为 GridPlayer 原本就是**可插拔驱动**架构：播放引擎只是一层薄薄的实现，上面的界面 / 管理器 / 模型 / 设置 / 工具 / 播放列表面板 / 浮层控件 / 手势全部与引擎无关。

也就是说：**移除 VLC 之后，本项目仍然是一部以 GridPlayer 为主体的播放器**，只是换了发动机。GPL 署名与出处义务不受影响。

### 12.2 但必须放在最后做

| 顺序 | 后果 |
|---|---|
| **现在删** | 唯一可用的引擎消失，而替代品尚不存在 —— 中间这段时间项目无法播放 |
| **先完成 mpv 驱动 → 实际使用验证 → 再执行 M4**（本设计采用） | 全程有可用引擎；验证期间还能随时切回对照 |

两点须知：

1. **删掉就没有退路了**：保留 VLC 期间，"一条设置切回"是安全网；移除后 mpv 的任何问题都只能改代码。
2. **与上游成为硬分叉**：GridPlayer 的立身之本就是"以 VLC 播放"。移除 VLC 后，与上游合并已无可能（GPL 义务仍在，血统仍在，但工程上是硬分叉）。

### 12.3 M4 的出口条件

1. mpv 驱动通过 §10 全部验收标准；
2. 用户已用 mpv 实际使用一段时间并确认没有影响日常使用的缺陷；
3. 删除范围仅限 §12.1 所列的 21 个文件 + 三个注册点 + 设置界面 2 处 + README 与依赖说明；
4. 删除后 `_runtests.py` 与 `_selftest.py` 仍全绿。

---

## 13. M1 完成记录（2026-10-04）

**mpv 驱动已实现并通过实机验证：播放正常、变速正常、音频不再中断。**

### 实现

| 文件 | 行数 | 作用 |
|---|---|---|
| `mpv_player/mpv.py` | 1792 | vendored python-mpv 绑定（逐字节未改） |
| `mpv_player/player_mpv.py` | ~136 | 持有 libmpv，翻译操作与状态 |
| `mpv_player/player_process_mpv.py` | ~200 | 子进程侧播放器 + 加载流程 + 状态回报 |
| `mpv_player/instance_process_mpv.py` | ~38 | 子进程容器（mpv 无共享实例，故极简） |
| `mpv_player/video_driver_mpv.py` | ~75 | 主进程侧驱动 |
| `widgets/video_frame_mpv.py` | ~34 | 窗口部件（提供 `wid` 句柄） |
| `utils/mpv_finder.py` | ~60 | 定位 libmpv（仓库相对，无本机路径） |

注册点：`params/static.py` 枚举 ✓ `player/managers/video_driver.py` 三处 ✓ `dialogs/settings.py` 两处 ✓

### 实机测试暴露的两个缺陷（都不是设计问题，是接口语义没对齐）

1. **画面卡在"初始化"，只有声音** —— 根因：没有回报 `load_video_done`。
   VLC 的加载是四步流程，最后一步必须把 `Media` 回报上去，窗口部件靠它才把画面显示出来。
   修法：加载完成后构建 `Media` 并回报，且**等待必须在独立线程**（否则命令循环被堵死）。

2. **有画面没声音** —— 根因：音量尺度搞错。
   驱动接口的 `volume` 是 **0.0~1.0 的比例**（VLC 侧写作 `int(volume_percent * 100)`），
   而实现里按 0~100 直接取整，导致 1.0 变成 1%（等于静音）。
   修法：按 VLC 的语义换算。

**教训：这两个都是"接口语义"层面的错，靠读代码看不出来，只有真的跑起来才暴露。**

### §8 风险表的结论

| # | 风险 | 结论 |
|---|---|---|
| 1 | `wid` 嵌入 Qt 原生窗口 | ✅ **通过**（实机画面正常） |
| 2 | 绑定许可证 | ✅ **通过**（GPL-2.0-or-later，见 §11a） |
| 3 | 轨道枚举 | ✅ 通过（`track-list` 直接映射） |
| 4 | seek 语义 | ✅ 通过 |
| 5 | 高频操作 | ✅ 通过 |
| 6 | 音量/静音语义 | ⚠️ **踩到了**（见上），已修 |
| 7 | 截图 | 未单独验证 |