# GridPlayer Mod

> 本项目是 [GridPlayer](https://github.com/vzhd1701/gridplayer) **0.5.5** 的修改版，
> 按 **GNU GPL v3.0 或更高版本**（GPL-3.0-or-later）发布。
> 上游版权归 [vzhd1701](https://github.com/vzhd1701) 所有。
>
> This is a modified fork of GridPlayer 0.5.5, released under the GPL-3.0-or-later,
> the same license as upstream. All changes are marked in the source with `# MOD:`.

在 VLC 之上同时播放多个视频的播放器 —— 上游已有的能力这里都有，下面只讲**这个版本多出来的东西**。

改动一共 **29 个文件、约 +2800 行**（其中 10 个是新增文件），全部集中在 `gridplayer/` 里，改动处都有 `# MOD:` 注释。**没有修改任何上游的默认设置值**，只新增了配置键，所以不改 `settings.ini` 的话行为与上游一致。

---

## 改动准则

本仓库对上游的所有改动都遵守这三条；不满足的改动一律不做，宁可问题留着：

1. **可移植** —— 换一台机器 clone 下来就能部署，**不携带任何本机绝对路径**。部署时最多确认一次环境路径（例如 Python 在哪、`libVLC\` 放哪）。**不允许出现"只有这台机器上才有的前置条件"**。
2. **少依赖** —— 只用**操作系统本身**和**仓库内已有依赖**。**不得引用其它软件的组件**（别的播放器/浏览器/微信里带的 DLL 之类），哪怕版本号正好对得上。
3. **模块化** —— 一处改动应当能在一个文件（或一组明确关联的文件）里看完。**不允许"改 A 必须去全仓库搜 B、C、D 否则漏掉"** 这种耦合，也不该为了改一个小功能而通读大量无关代码。

> 反例（曾经做过、已回退）：为解决变速断音，从微信内置播放器里取 `libmmdevice_plugin.dll` 放进 `libVLC\`，并改 `instance.py` 的默认音频输出。
> 违反第 1 条（`libVLC\` 是 gitignore 的，新机器根本没有这个插件）与第 2 条（用了别的软件的组件），而且**问题并未解决**。

## 与原版的差异

### 播放

| 功能 | 说明 | 主要文件 |
|---|---|---|
| **第四种播放次序：播完暂停** | 上游只有单集循环 / 列表循环 / 随机播放，这里补上"播完最后一个就停在暂停"。控制条上的循环按钮依次循环这四种；右键菜单和设置里也多了对应项 | `params/static.py`、`video_overlay_buttons.py`、`video_overlay_icons.py`、`params/actions.py`、`dialogs/settings.py` |
| **悬停即显示控制条** | 上游要点一下才出现。改为鼠标移上去就出现，停止移动约 2 秒后收起，移出画面立刻收起（跟随设置里的 `misc/overlay_timeout` / `misc/overlay_hide`） | `widgets/video_block.py`、`widgets/video_overlay.py` |
| **双击的四种行为** | 单个视频：窗口化（保留原本是否最大化）↔ 全屏；网格里多个视频且未全屏：进全屏；全屏且已放大某一格：从放大退回网格；全屏且正在放大某一格：双击该格占满整个网格 | `player/managers/single_mode.py` |
| **单屏标签栏** | 某个视频占满屏幕时，控制条上方出现一排标签。点标签切换到那个视频，点标签上的 ✕ 关掉那个视频。两种外观：**分离式**（普通一排标签，各自带文件名）与**融合式**（正在播放的那个标签是与文件名长条同色的梯形，从长条里长出来，其余标签更矮、更深色、退在后面）。**在文件名长条上点右键**即可切换，选择会记住 | `widgets/video_overlay_tabs.py`（新）、`single_mode.py`、`video_blocks.py` |
| **倍速控件** | 控制条上、**紧挨进度条右侧**，显示为 `×1` / `×1.25` 这样的倍数。**宽度固定**（按最宽的那个标签量出来），在 `×1` 与 `×1.25` 之间切换时布局不会跳动。单击弹出**一整条半透明灰色挡位条**（与浮层同色），挡位**由大到小自上而下**排列：`3 / 2.5 / 2 / 1.5 / 1.25 / 1 / 0.75 / 0.5`，当前挡位加粗、悬停行高亮。用原版快捷键 C/X/Z 做 ±0.1 微调后，这里会如实显示 `×1.1` 这类非挡位值（此时没有任何一行被选中） | `widgets/video_overlay_speed.py`（新）、`video_overlay.py` |
| **长按拖拽调倍速** | 在画面上**按住左键 0.5 秒**即临时加速到 2 倍速，**横向拖动**按挡位增减，**松开还原**。挡位切换是**棘轮式**的：判定基准点跟着鼠标走，每移动一个步长换一挡。所以**拖到屏幕边缘也不会卡住**，而**从顶挡往回要退满一步才降挡**（顶挡松手前参考点仍在跟，回退一半不算）。拖动时在**视频区水平正中、距顶 1/6** 处显示当前倍率，**不弹出控制条**。按住 **Ctrl** 再长按则对该网格里的**全部视频**生效（单屏模式除外）。单击暂停不受影响 —— 暂停发生在松开时，短按仍是暂停 | `widgets/video_block.py`、`widgets/video_overlay_speed.py`、`utils/speed_gears.py`（新） |
| **音频输出** | 上游在 Windows 上强制 `--aout=directsound`，本仓库**保持原样**。 |
| **网格内移动视频改为 Alt+拖动** | 上游是**直接左键拖动**就移动视频在网格中的位置。改成需要 **Alt**：普通左键拖动被上面的长按倍速手势占用，而移动视频会开一个**模态拖放循环**，把手势需要的移动和松开事件全部吃掉 | `player/managers/drag_n_drop.py` |

### 播放列表面板

| 功能 | 说明 | 主要文件 |
|---|---|---|
| **右侧滑出面板** | 控制条上的三横杠按钮开关。列出当前视频所在文件夹里的全部视频 | `widgets/playlist_panel.py`（新）、`player/managers/playlist_panel.py`（新） |
| **排序** | 按文件名 / 大小 / 修改时间 / 播放历史 / 时长，升降序可切；排序方式跨会话记住 | 同上 + `settings.py` |
| **缩略图** | 走 Windows 自己的缩略图接口（`IShellItemImageFactory::GetImage`），复用资源管理器的缩略图缓存 —— **不自己截帧、不自己存图**，所以在资源管理器里能看到缩略图的文件这里也能看到 | `utils/shell_thumbnail.py`（新）、`utils/thumbnail_probe.py`（新） |
| **时长** | 后台异步探测并缓存到磁盘，不拖累界面 | `utils/duration_probe.py`（新）、`utils/duration_cache.py`（新） |
| **播放历史** | 记录每个文件上次播放的时间，供"播放历史"排序使用 | `utils/play_history.py`（新） |
| **文件夹扫描** | 扫描、过滤出可播放文件 | `utils/media_folder.py`（新）、`models/media_entry.py`（新） |
| **行的右键菜单** | ① **下一个播放** ② **在新窗口中播放** ③ **在网格中添加播放** | `widgets/playlist_panel.py`、`player/managers/add_videos.py` |

> **"下一个播放"是"插入"而不是"跳转"**：顺序原本是 `a b c d e`，播到 `a` 时对 `d` 点"下一个播放"，之后依次播的是 `a → d → b → c → d → e` —— 当前播放不被打断，`d` 只是被提前插入到 `a` 之后。

### 窗口

| 功能 | 说明 | 主要文件 |
|---|---|---|
| **记住窗口状态** | 关闭时记住在哪块屏幕、什么位置、以及是全屏还是窗口化，下次启动原样恢复 | `player/managers/window_state.py`、`settings.py` |
| **记住音量** | 关闭时记住当前活跃视频的音量，下次打开的视频用它播放。只在关闭时写、只在创建视频时读，所以同时开着的多个窗口不会互相覆盖 | `models/video.py`、`player/managers/active_block.py`、`window_state.py` |
| **没有视频就退出** | 关掉最后一个视频时直接关闭窗口，而不是留下一个写着"拖入文件播放"的空壳。**只在"从有到无"时触发** —— 不带参数启动仍然会停在窗口上（否则双击视频文件打开时会在加载前就把自己关掉） | `player/managers/video_blocks.py`、`window_state.py` |

### 与系统集成

| 功能 | 说明 | 主要文件 |
|---|---|---|
| **单实例** | 已经是上游默认行为（`player/one_instance`）。在此之上：一次选中多个文件打开时会**全部**加进网格，而不是只开第一个 | `utils/single_instance.py` |
| **`--new-window`** | 强制开一个新的独立窗口，而不是把文件交给已在运行的实例 —— "在新窗口中播放"用的就是它 | `__main__.py`、`utils/single_instance.py` |
| **数据目录可重定向** | 新增环境变量 `GRIDPLAYER_DATA_DIR`，设置后 `settings.ini` 与日志就写到那里，不写 `%APPDATA%` —— 便携化的基础 | `utils/app_dir.py` |
| **资源管理器右键菜单**（可选，见下） | 在资源管理器里选中若干视频 → 右键 → **"在Grid网格中播放"**，一次性全部打开 | `_shell_menu.ps1`（不在 `gridplayer/` 内，需手动注册） |

### 内部改动与顺手修掉的问题

| 改动 | 说明 | 主要文件 |
|---|---|---|
| **网格移入 QSplitter** | 上游的网格布局直接铺在窗口上（一个 QWidget 只能有一个布局），没法再加侧边面板。改为网格放进一个 host widget，host 与面板一起放进 `QSplitter` | `player/managers/grid.py` |
| **窗口最小宽度跟着面板长** | 面板占的宽度会让视频区变窄，所以窗口最小宽度要把面板的 `minimumWidth()` 一起算进去 | `player/managers/grid.py` |
| 关窗顺序修正 | 上游在 `closeEvent` 里先关播放列表再取音量，而关播放列表会清空视频块 —— 结果什么都没保存。改为先取值、再关列表、最后落盘 | `player/managers/window_state.py` |
| 单屏退出后网格错乱 | `video_count_changed` 先到网格、后到单屏管理器，于是网格是在"其余视频还被藏着"的状态下重建的，全部挤成一行。改为退出单屏后重建一次网格 | `player/managers/single_mode.py`、`player/managers/grid.py` |
| 浮层遮罩坐标 | 硬件浮层的遮罩按子控件的父级相对坐标拼装，嵌套控件（标签栏里的标签）会画错位置 | `widgets/video_overlay.py` |

---

## mpv 播放驱动（可选引擎）

播放引擎可选 **libVLC**（原版）或 **mpv**。引入 mpv 的原因只有一个：**改变播放速率时音频不中断**，libVLC 做不到这一点。

### 使用

1. 把 **`libmpv-2.dll`** 放进仓库根目录的 **`mpv\`**（与 `libVLC\` 同策略，已被 gitignore）
2. 设置 → 播放 → **视频驱动** → 选 **`Hardware (mpv)`**
3. 切回 VLC 就选列表里的 VLC 项 —— 两个引擎并存，随时可切

新安装默认使用 mpv。**macOS 例外**：仍默认 VLC 硬件 SP 模式，因为 mpv 在 macOS 上不支持嵌入外部窗口。

### 获取 libmpv

从 mpv 官方 Windows 构建（shinchiro）下载 **`mpv-dev-x86_64-*.7z`** —— 注意**不是** `mpv-x86_64-*.7z`，那个包里只有 `mpv.exe`，没有 libmpv。解压出其中的 `libmpv-2.dll` 放进 `mpv\` 即可，该目录下只需要这一个文件。

已实测版本：`mpv-dev-x86_64-20261003`，libmpv **v0.41.0-1092**，sha256 `b8c2d656c1584d5f08196fcee5c2d0783d1f76021897c4e0b3cc30f94c79522e`。

### 与 VLC 驱动的差异

| 方面 | 说明 |
|---|---|
| 画面渲染 | 渲染进 Qt 提供的**原生窗口句柄**，与 VLC 硬件模式同一机制，帧不跨进程 |
| 音量语义 | 驱动接口传 **0.0~1.0 比例**，与 VLC 驱动一致 |
| 状态上报 | VLC 推送事件；mpv **轮询属性**（位置 4 Hz，与 VLC 节奏对齐） |
| 字幕 | 由 mpv 自行渲染，样式与 VLC 不同 |

### 风险与已知差异

| 风险 | 说明与应对 |
|---|---|
| **运行时缺失会导致该驱动不可用** | `mpv\libmpv-2.dll` 不存在时，选中 mpv 的视频会报明确的加载错误；把驱动切回任一 VLC 项即可正常使用，不需要改配置文件 |
| **字幕样式与 VLC 不同** | mpv 自行渲染字幕，字体回退、位置与描边都可能不一致 |
| **少见协议与光盘** | 常见网络串流两者都经 FFmpeg 处理；少见的流媒体协议与光盘播放，VLC 更成熟 |
| **截图未做端到端验证** | 驱动已实现截图调用，但没有实际验证过输出文件 |
| **两套引擎并存** | VLC 的四个驱动一行未改；切换引擎只影响此后新打开的视频，正在播放的不受影响 |
| **性能** | 解码与渲染在同一进程内完成，帧不跨进程，与 VLC 同构；未观察到性能差异 |
## 运行

### 需要什么

- **Python 3.10 或更高**（本仓库在 3.13 上开发）
- **VLC 运行库**。两种来源：装一个 VLC，或者直接把上游 Windows 便携版里的 `libVLC\` 目录复制到本仓库根目录（`run_gridplayer.py` 会自动指过去）
  - 建议用**官方稳定版 3.0.24 或更高**：3.0.21（上游便携版自带的那份）在**改变播放速率时音频会短暂中断**，而 3.0.24 的官方构建实测不出现该现象。用 winget 取最省事，且**不必真安装**：
    ```powershell
    winget download VideoLAN.VLC --download-directory .
    msiexec /a ".\VLC media player_*.msi" /qn TARGETDIR=.\_vlc
    # 然后把 _vlc\PFiles\VideoLAN\VLC\ 里的内容放进仓库根的 libVLC\
    ```
    `msiexec /a` 是 Windows 自带的"管理安装"，只解包、**不写注册表、不进开始菜单**

### 从源码启动

```powershell
# 1. 建虚拟环境并装依赖
python -m venv pyenv
pyenv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 启动
pyenv\Scripts\pythonw.exe run_gridplayer.py
```

也可以直接 `pyenv\Scripts\python.exe run_gridplayer.py 某个视频.mp4` 打开指定文件。

### 让文件关联显示 GridPlayer 图标（可选）

如果要把视频格式关联到本程序，**不要**直接把 `pythonw.exe` 写进关联命令 —— Windows 会把"打开方式"列表里那个条目的图标取自命令里的 exe，于是显示成 Python 的图标。改成用一个自带图标的启动器：

```powershell
# 生成 pyenv\Scripts\GridPlayer.exe：pythonw 的副本 + GridPlayer 图标
pyenv\Scripts\python.exe _make_launcher.py
```

然后把关联指到它：

```
shell\open\command = "<仓库>\pyenv\Scripts\GridPlayer.exe" "<仓库>\run_gridplayer.py" "%1"
```

`_make_launcher.py` 做的是：复制 venv 的 `pythonw.exe`（同目录，所以 venv 仍然解析正常），再用 `BeginUpdateResource`/`UpdateResource` 把 `GridPlayer.ico` 的全部尺寸写进去，不需要任何资源编辑器。

`_setup-env.ps1` 把上面第 1 步做成了脚本。它默认用 PATH 上的 `python`；如果那只是个 Microsoft Store 转发器（Windows 上很常见），用 `-BasePython` 指向真正的解释器：

```powershell
powershell -ExecutionPolicy Bypass -File _setup-env.ps1 -BasePython "C:\Python313\python.exe"
```

### 数据与日志

默认写在 `%APPDATA%\gridplayer\`（与上游一致）。`run_gridplayer.py` 会把 `GRIDPLAYER_DATA_DIR` 指向仓库下的 `data\`，让设置和日志留在本地：

- `data\settings.ini` —— 设置
- `data\gridplayer.log` —— 日志

两者都在 `.gitignore` 里，**不会进仓库**。

### 可选：资源管理器右键菜单

`_shell_menu.ps1` 会在 `HKCU\Software\Classes\SystemFileAssociations\<扩展名>\shell\` 下注册一个静态动词，覆盖 66 种视频扩展名，菜单文字取自 `_shell_menu_label.txt`。它**只写当前用户、不需要管理员**，随时可以撤销：

```powershell
# 注册
powershell -ExecutionPolicy Bypass -File _shell_menu.ps1
# 撤销
powershell -ExecutionPolicy Bypass -File _shell_menu.ps1 -Unregister
```

菜单项会调用本仓库的 `run_gridplayer.py`，所以**仓库移动位置后要重新注册一次**。

---

## 播放卡顿时的排查

**如果某个视频卡得厉害，先分清楚是"解不动"还是"显示不出去"** —— 这两者的解法完全不同。`_probe_prores.py` 用播放器自带的那份 libVLC 直接量，并读它自己的计数器：

```powershell
pyenv\Scripts\python.exe _probe_prores.py "<视频路径>" 20
```

它会先跑 8 秒预热再测 20 秒稳态，输出解码帧率、**实际显示帧率**和丢帧数。判据：

- 解码帧率 ≈ 60 但**显示帧率远低于 60 / 丢帧很多** → 瓶颈在显示路径，**改设置救不了**（原因见下节），要么改文件，要么换播放器
- 解码帧率本身就 < 60 → CPU 解不动，任何显示路径都救不了

### 实测案例：4K60 ProRes 严重卡顿

一个 3840×2160@60 的 **Apple ProRes 422 Proxy**（10-bit 4:2:2、237 Mbps）卡到没法看。实测（Ryzen 7 5700X + RTX 3060 Ti）：

| 配置 | 解码 | **实际显示** | 丢帧 |
|---|---|---|---|
| 默认 vout | 67.5 fps | 0.1 fps | 48 |
| `--vout=direct3d11` | 62.0 fps | 0.1 fps | 48 |
| **`--vout=direct3d9`** | 119.7 fps | **59.8 fps** | **0** |

解码一直有 2 倍余量（ProRes 本来就没有消费级硬件解码器，纯 CPU 解），**卡在输出模块处理 10-bit 4:2:2 上**。

### 转码成能硬件解码的格式

ProRes / DNxHR / CineForm 这类**中间格式本来就没有消费级硬件解码器**。如果这类素材多，转码比调播放器省事。目标是让 GPU 能硬解，**有一条硬性要求容易被忽略**：

| 项 | 要求 | 原因 |
|---|---|---|
| 编码 | **H.264 或 HEVC (H.265)** | NVDEC 支持这两种 |
| **色度采样** | **必须是 4:2:0** | **NVDEC 不支持 H.264/HEVC 的 4:2:2** —— 导成 4:2:2 依然无法硬解 |
| 位深 | 8-bit 或 10-bit 均可 | HEVC Main10（10-bit 4:2:0）可硬解 |
| Profile | HEVC **Main / Main10**；H.264 **High** | |
| 分辨率 / 帧率 | 保持 3840×2160 @60 | |

一条可用的命令（**ffmpeg + NVENC**，不需要 Premiere；实测 4K60 约 **1.1× 实时**，4 分半的片子 4 分钟出片）：

```powershell
ffmpeg -i "<源文件>" -map 0:v:0 -map 0:a:0 `
  -c:v hevc_nvenc -preset p5 -tune hq -profile:v main10 -pix_fmt p010le `
  -rc vbr -cq 22 -b:v 80M -maxrate 120M -bufsize 160M `
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 `
  -c:a copy -tag:v hvc1 -movflags +faststart -map_metadata 0 "<输出>.mp4"
```

实测结果（4K60 ProRes 422 Proxy 10-bit 4:2:2 / 237 Mbps → HEVC Main10 4:2:0 / 34 Mbps）：

| 项 | 结果 |
|---|---|
| 文件大小 | 8.16 GB → **1.17 GB** |
| 帧数 | 16493 → **16493**（一帧不差） |
| 播放（自带 libVLC 实测） | **displayed 60.0 fps、丢帧 0、100% 实时** |
| VMAF（15 s / 900 帧） | **mean 97.53**，min 95.10 |
| PSNR | **53.29 dB**（min 52.06） |
| SSIM | **1.000000** |
| 逐像素亮度差（10-bit） | 平均 **1.2~1.5 / 1023**（0.13%），峰值 35~49 |

> 在 Premiere Pro 里也可以：导出 → 格式 **HEVC (H.265)** → Profile 选 **Main10**（**不要选 4:2:2**），勾选**硬件加速编码 (NVENC)**。但 PR 打开 ProRes 母带本身就很慢，纯转码用上面的 ffmpeg 命令更快。

复测用 [`_compare_transcode.py`](_compare_transcode.py)（画质：VMAF/PSNR/SSIM + 同帧截图）和 [`_probe_prores.py`](_probe_prores.py)（帧率：解码/实际显示/丢帧）。

## 已知差异与注意事项
- **本仓库只发代码，不带你的个人设置。** 例如 `playlist/track_changes` 在代码里的默认值仍是上游的 `True`（关闭窗口时会问"要保存播放列表吗"）；想关掉请在设置界面里改，或者写进自己的 `settings.ini`。
- **本机开发目录里的 `settings.ini` 与仓库默认不同**，属于个人配置，不随仓库发布。
- **`docs/plans/` 与 `docs/specs/` 是历史工作记录**，里面写的仍是当时的路径和文件名（例如 `app/gridplayer/`、`test_*.py`），**不是当前状态**，请勿据此改代码。当前状态以本 README 与源码为准。
- **`PATCHES.diff` 已被 git 取代。** 它由 `_mkpatch.ps1` 生成，一不含新增文件、二用的是绝对路径，换台机器无法应用。保留只是为了有个扁平的差异可读；文件本身已 gitignore。
- 测试脚本叫 `check_*.py` 而**不是** `test_*.py` —— 它们是模块级就跑完并 `sys.exit()` 的独立程序，用 `test_` 前缀会让 pytest 在收集阶段直接崩溃。详见 `_runtests.py` 的文件头注释。

---

## 仓库结构

```
gridplayer/          上游 0.5.5 源码 + 本仓库的改动（`# MOD:` 注释标出）
tests/               check_*.py —— 检查脚本，共 19 个、300+ 项检查
                     samples/ —— 自带的小样片（mp4/mov 各 ~10 KB），检查脚本依赖
                     render_*.py / probe_*.py —— 离屏渲染与端到端探针，不参与回归
docs/                设计记录与发布准备文档
run_gridplayer.py    从源码启动的入口
pyproject.toml       取自上游；唯一改动是在 ruff 的 `extend-exclude` 里追加了 vendored 的 `mpv_player/mpv.py`（上游本来就以同一方式排除了 `vlc_player/vlc.py` 与 `resources_bin.py`）
requirements.txt     运行依赖，与上游声明的区间一致
LICENSE              GPL-3.0 全文
GridPlayer.ico       应用图标（5 个尺寸），由 _extract_icon.py 从官方 exe 提取
_shell_menu.ps1      可选的资源管理器右键菜单（注册/撤销）
_runtests.py         依次运行全部 check_*.py
_selftest.py         音量记忆的专项检查
_setup-env.ps1       建 venv + 装依赖
_extract_icon.py     从 exe 提取多尺寸 .ico
_make_launcher.py    生成带 GridPlayer 图标的启动器（见"让文件关联显示 GridPlayer 图标"）
_probe_prores.py     播放性能探针：量解码帧率 / 实际显示帧率 / 丢帧（见"播放卡顿时的排查"）
_compare_transcode.py  转码质量对比：VMAF / PSNR / SSIM + 同帧截图（需要有 ffmpeg 在 PATH 或设 FFMPEG_DIR）
_mkpatch.ps1         生成 PATCHES.diff（已被 git 取代，仅为兼容保留）
```

---

## 开发

### 跑检查

```powershell
pyenv\Scripts\python.exe _runtests.py     # 全部 check_*.py
pyenv\Scripts\python.exe _selftest.py     # 音量记忆专项
```

想只看某个方面就直接跑单个文件，例如 `pyenv\Scripts\python.exe tests\check_tab_bar.py`。

### 代码风格

与上游一致：**ruff**（版本 `>=0.14.10,<0.15.0`），配置就在 `pyproject.toml` 里，无需额外参数：

```powershell
uvx --from "ruff>=0.14.10,<0.15.0" ruff check .
uvx --from "ruff>=0.14.10,<0.15.0" ruff format --check .
```

上游的政策是**测试文件不 lint、但要 format**（`[tool.ruff.lint] exclude = ["tests/*.py"]`），本仓库沿用。当前整个仓库 174 个文件 lint 与 format 均通过。

---

## 许可证

GPL-3.0-or-later，与上游相同。全文见 [LICENSE](LICENSE)。

这意味着你可以自由使用、修改、再分发，但**再分发时必须同样以 GPL-3.0 发布并附上完整源码**。

## 致谢

- [GridPlayer](https://github.com/vzhd1701/gridplayer) —— 上游项目，本仓库的全部基础
- [VLC](https://www.videolan.org/) / libVLC —— 播放内核
- [**mpv**](https://mpv.io/) / libmpv —— 可选播放内核（见"mpv 播放驱动"）
- [**python-mpv**](https://github.com/jaseg/python-mpv) —— libmpv 的 Python 绑定，**已 vendored** 进 `gridplayer/mpv_player/mpv.py`（逐字节未改）。版本 **1.0.8**，commit `93c4de9bb7a0`（2025-04-25），sha256 `c05b55fcca8659486e801b32b70008d47219ffa83181a35db26876e18f89ce4f`。许可证 **GPL-2.0-or-later**（双许可，亦可选 LGPL-2.1-or-later），"or later"使其可并入本仓库的 GPL-3.0
- [Qt](https://www.qt.io/) / [PyQt5](https://riverbankcomputing.com/software/pyqt/) —— 界面
- 上游 README 中列出的图标与字体作者（Hack Font、Basic Icons、Suru Icons 等）
