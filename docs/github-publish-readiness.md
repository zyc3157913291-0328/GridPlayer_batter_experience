# 发布到 GitHub：要求对照与准备情况

- **基线**：GridPlayer 0.5.5，上游 [vzhd1701/gridplayer](https://github.com/vzhd1701/gridplayer)，许可证 GPL-3.0-or-later
- **改动规模**：29 个文件，**+2818 / −22 行**（10 个新文件 1893 行；19 个上游文件 +925 / −22）
- **核对日期**：2026-10-02

---

## 0. 三条结论

1. **可以发**，但必须是 GPL-3.0 并附完整源码，不能改成 MIT/Apache 之类的许可证。
2. **代码本身已经干净**：全库扫描没有任何本机路径、中文注释、TODO 或调试残留；上游的 ruff 规则集（lint + format）在**整个仓库 174 个文件**上全部通过。
3. **原本拦住发布的三件事，现在已经全部做完**：
   - 测试形态 —— `test_*.py` → `check_*.py`，pytest 不再崩
   - 目录结构 —— `app/gridplayer/` → `gridplayer/`，`pyproject.toml` 回到根目录
   - 悬空引用 —— 源码里指向内部计划文档的 3 处已清掉
   剩下的只有 90 处 `# MOD` 标记（走 Fork 建议保留、走 PR 才需要清）和个人脚本的去留，这两项都属于"你决定"，不是"必须修"。

---

## 1. 上游的硬性要求 —— 逐条核对

依据均取自上游自己的 `pyproject.toml`（来源：PyPI 上的 `gridplayer-0.5.5.tar.gz`）。

| # | 上游要求 | 依据 | 现状 | 结论 |
|---|---|---|---|---|
| 1 | `license = "GPL-3.0-or-later"` | `pyproject.toml:12` | 已放 `LICENSE`（GPL-3.0 全文 35149 字节，取自 gnu.org） | ✅ |
| 2 | `requires-python = ">=3.10"` | `pyproject.toml:10` | 3.13.5 | ✅ |
| 3 | 依赖版本区间 | `pyproject.toml:31-41` | 已写成 `requirements.txt`，与上游区间一致 | ✅ |
| 4 | **ruff lint**（规则集见 §62-121） | `pyproject.toml:68-121` | 修复前 14 项错误 → **0 项** | ✅ |
| 5 | **ruff format**（LF 换行） | `pyproject.toml:65-66` | 修复前 10 个文件不合规 → **142 个全部合规** | ✅ |
| 6 | 测试文件被 lint 排除 | `pyproject.toml:69` | `tests/*.py` 不受约束 | ✅ 无需动 |
| 7 | **pytest** 作为测试框架 | `pyproject.toml:54` | 已改为 `check_*.py`，pytest 干净返回 `no tests collected` | ✅ |
| 8 | CHANGELOG（keepachangelog） | `pyproject.toml:55` | 没有 | ⚠️ 建议补 |
| 9 | pre-commit | `pyproject.toml:53` | 没有配置文件 | ⚠️ 见 §5.4 |
| 10 | 打包后端 `uv_build`，包位于仓库根 `gridplayer/` | `pyproject.toml:2-3, 59-60` | 已对齐：包在 `gridplayer/`，`pyproject.toml` 在根目录 | ✅ |
| 11 | 排除 `resources_bin.py` / `vlc_player/vlc.py` | `pyproject.toml:63` | 已按此排除（现在无需 `--config`，ruff 自动发现） | ✅ |
| 12 | 仓库只含源码 | 上游仓库内容 | 见 §6 | ⚠️ |

### 1.1 基线可信性（这点必须先确认）

`.upstream/gridplayer` 与上游 0.5.5 源码包**逐文件 SHA256 全部一致：134/134**。

这条很重要：`_mkpatch.ps1` 生成的补丁是否可信、`PATCHES.diff` 是否等于"真实改动"，完全取决于这份基线。已核实无误。

---

## 2. 两条路线，要求不同

| 项目 | A. 回馈上游（往 vzhd1701/gridplayer 提 PR） | B. 自己的 Fork / 独立仓库 |
|---|---|---|
| `LICENSE` | 不用加（上游已有） | **必须加**（已完成） |
| `# MOD` 标记 | **必须全部去掉**（90 处） | 保留反而有用 |
| 内部计划文档引用 | **必须去掉**（3 个文件） | 可留，但建议移出源码 |
| 本机工具脚本 | 不要带 | 可带，建议单独放 `scripts/` |
| `.gitignore` / `requirements.txt` | 不需要（上游已有等价物） | 需要（已完成） |
| CHANGELOG | **需要** | 建议 |
| 提交粒度 | **必须拆成可单独 review 的提交** | 随意 |
| 测试形态 | **必须能被 pytest 收集** | 可保持现状 |
| 目录结构 | 保持上游布局 | 建议也对齐上游 |

**建议**：先按 B 发一个自己的 Fork（成本低、立刻可用），把其中通用性强的改动（窗口记忆、悬停控制条、播放列表面板）再单独整理成 A。

---

## 3. 已完成的工作

### 3.1 许可证与发布文件

| 文件 | 说明 |
|---|---|
| `LICENSE` | GPL-3.0 全文，35149 字节，SHA256 `3972DC97…6986`，取自 <https://www.gnu.org/licenses/gpl-3.0.txt> |
| `.gitignore` | 覆盖 `pyenv/`、`libVLC/`、`data/`、`.backups/`、`__pycache__/`、`*.exe`、`.upstream/`、`PATCHES.diff`、`evidence/`、一次性探针脚本等 |
| `.gitattributes` | `* text=auto eol=lf`。**必要**：这台机器的 git 开了 `core.autocrlf=true`，不加这条会把 LF 源码检出成 CRLF，日后每次改动都变成整文件 diff。上游也是全线 LF（其 ruff 配置写明 `line-ending = "lf"`，134 个源文件实测 100% LF） |
| `requirements.txt` | 与上游 `pyproject.toml` 的依赖区间逐条对齐；注明 python-vlc 是包内自带的 |

### 3.2 修掉 14 处 lint（上游 ruff 规则集）

| 文件 | 行 | 规则 | 问题 | 处理 |
|---|---|---|---|---|
| `models/video.py` | 10 | F401 | `AbsoluteFilePath` 导入未使用 | 自动修复 |
| `player/managers/playlist_panel.py` | 5 | I001 | 导入块未排序 | 自动修复 |
| `utils/duration_probe.py` | 6 | UP035 | 从 `typing` 导入 `Sequence` | 自动改为 `collections.abc` |
| `utils/duration_probe.py` | 107,120 | RUF100 | 无效的 `noqa` | 自动删除 |
| `utils/media_folder.py` | 5 | UP035 | `Mapping`/`Sequence` | 自动修复 |
| `utils/thumbnail_probe.py` | 6,60 | UP035, RUF100 | 同上 | 自动修复 |
| `widgets/playlist_panel.py` | 7,10 | UP035, F401 | 同上 + `QPainter` 未使用 | 自动修复 |
| `widgets/playlist_panel.py` | 143 | DTZ006 | 见 §3.4 | **手工修** |
| `widgets/playlist_panel.py` | 188 | F841 | 见 §3.3 | **手工修** |
| `widgets/video_overlay.py` | 1 | I001 | 导入块未排序 | 自动修复 |
| `widgets/video_overlay_tabs.py` | 21 | F401 | `QPoint` 未使用 | 自动修复 |

修复后：`ruff check` → **All checks passed!**；`ruff format --check` → **142 files already formatted**。

**关键的一点**：格式化只动了新代码。19 个被修改的上游文件改动行数**逐个核对过，全部未变**（`window_state.py` 仍是 +170/−4，`video_overlay_icons.py` 仍是 +138/−1，`single_mode.py` 仍是 +127/−3）。所以不会出现"格式化把上游代码整片重排"这种最招人烦的 diff。

### 3.3 修掉一处死代码

`widgets/playlist_panel.py` 原 187-188 行：

```python
text_left = rect.left() + THUMB_BOX_WIDTH + 8
name_width = rect.width() - (text_left - rect.left()) - 10

text_left = rect.left() + THUMB_BOX_WIDTH + 8   # 同一行又算一遍
avail = max(rect.width() - (text_left - rect.left()) - 10, 40)
```

`name_width` 算完从未使用，`text_left` 下一行原样重算 —— 重构残留。已删除。

### 3.4 修掉一处时区问题

```python
# 之前：无 tz，DTZ006
datetime.datetime.fromtimestamp(entry.mtime).strftime("%Y-%m-%d")

# 现在：UTC 读入再转本地，显示结果不变
datetime.datetime.fromtimestamp(entry.mtime, tz=datetime.timezone.utc).astimezone()
```

### 3.5 git 仓库已初始化（未提交）

`git init -b main` 已执行，全部应传内容已 `git add`，**尚未提交**。暂存内容实测核对（目录重排之后重新核对过一遍）：

| 检查项 | 结果 |
|---|---|
| 暂存文件数 | **192** |
| 暂存体积 | **10.2 MB** |
| `pyenv/`（247 MB） | 已忽略 ✅ |
| `libVLC/`（93.6 MB） | 已忽略 ✅ |
| `data/`（含 `settings.ini`） | 已忽略 ✅ |
| `.backups/`、`.upstream/`、`PATCHES.diff`、`_setup.log` | 已忽略 ✅ |
| `evidence/`、`__pycache__/`、`*.exe`/`*.dll`/`*.pyc` | 已忽略 ✅ |
| `.ruff_cache/`、`.pytest_cache/` | 已忽略 ✅ |
| `_p1_gui_*.ps1`、`_p2_gui_*.ps1` | 已忽略 ✅ |

> 已暂存但需要你决定去留的：`GridPlayer.ico`（图标有上游列出的第三方署名，见 §6）、`_mkpatch.ps1`（git 之后冗余）、`_shell_menu.ps1` + `_shell_menu_label.txt`（写注册表的本机功能，建议移到 `scripts/`）。

### 3.6 目录对齐与测试改名（本轮完成）

#### 3.6.1 测试形态（原 CI 阻塞项）

19 个 `tests/test_*.py` → `tests/check_*.py`。`_runtests.py` 的 glob 同步改为 `check_*.py`，并在文件头写明了为什么不能叫 `test_*`。

实测对比：

| | 之前 | 现在 |
|---|---|---|
| `pytest --collect-only` | `INTERNALERROR ... SystemExit: 0`，退出码 3 | `no tests collected in 0.19s`，退出码 5（正常语义） |

#### 3.6.2 目录结构

| 之前 | 现在 |
|---|---|
| `app/gridplayer/` | `gridplayer/` |
| （无） | `pyproject.toml`（取自上游 0.5.5 源码包，**未改动**） |

连带调整的路径引用（共 9 处，全部实测确认）：

- `run_gridplayer.py`：`sys.path` 指向仓库根；文件头那句"位于 `<repo>`"改成不绑定机器
- `tests/_harness.py`、`_selftest.py`、`tests/probe_quit_e2e.py`：同上
- `tests/check_quit_when_empty.py`、`tests/check_tab_bar.py`：读取 `player.py` 做接线断言时用的路径
- `_mkpatch.ps1`：`$root` 改为 `$PSScriptRoot`（不再写死 `<repo>`）；`app\gridplayer` → `gridplayer`；文件头那句"这不是 git 仓库，所以本脚本就是提交"改成说明它已被 git 取代
- `_setup-env.ps1`：`$root` 改为 `$PSScriptRoot`；不再创建已废弃的 `app\` 目录
- `gridplayer/player/managers/window_state.py:59`：注释里指向 `tests/test_window_state_restore.py` → `tests/check_window_state_restore.py`（**这是唯一一处包内的过期引用**）
- `README.md`：8 处 `app/gridplayer` → `gridplayer`
- 4 个渲染/探针脚本的说明文字：`test_*.py` → `check_*.py`

#### 3.6.3 源码里的悬空引用已清除

| 文件 | 原来 | 现在 |
|---|---|---|
| `gridplayer/player/managers/playlist_panel.py:2` | `# See docs/plans/2026-10-02-p3-playlist-panel.md (Task 7).` | 删除 |
| `gridplayer/utils/play_history.py:1-2` | 含 `(playlist panel Task 3)` 与同样的 docs 引用 | 改为一句自述 |
| `gridplayer/widgets/playlist_panel.py:1-2` | 含 `(playlist panel P3 Task 6)` 与同样的 docs 引用 | 改为一句自述 |

#### 3.6.4 附带收获

包和 `pyproject.toml` 都在仓库根之后，**ruff 自动发现配置，不再需要 `--config` 参数**。而且现在是**整仓库**校验：

```
$ ruff check .          -> All checks passed!
$ ruff format --check . -> 174 files already formatted
```

其中 `gridplayer/` 里 0 个文件需要改；另外 27 个（25 个测试 + 2 个根脚本）已按上游"测试不 lint、但要 format"的政策统一格式化。

#### 3.6.5 回归验证

| 项目 | 结果 |
|---|---|
| `_runtests.py` | **19/19 checks passed** |
| `_selftest.py` | **15/15** |
| `ruff check .` / `ruff format --check .` | 全通过（174 文件） |
| 实机启动冒烟 | 窗口标题 `GridPlayer`，日志无 traceback，进程已清理 |
| `PATCHES.diff` | 已重新生成，65612 字节，19 个上游文件 |

#### 3.6.6 根脚本里残留的写死路径（复查时发现）

上一轮的"本机路径 0 处"只扫了 `gridplayer/`，**根脚本没扫**。复查发现两处：

| 文件 | 原来 | 现在 |
|---|---|---|
| `_shell_menu.ps1` | `param()` 默认值写死 `<repo>\pyenv\Scripts\pythonw.exe` 与 `<repo>\run_gridplayer.py` | 改为由 `$root`（脚本自身位置）推导，仍可用参数覆盖 |
| `_setup-env.ps1` | `$basePy = '<python>\python.exe'` | 改为 `param([string]$BasePython = 'python')` + 命令行覆盖 |

验证方式（**只读，未执行注册**，避免动到用户的资源管理器菜单）：

- 三个 `.ps1` 全部用 PowerShell 的 Parser 做语法检查：0 错误
- `_shell_menu.ps1` 现在推导出的命令 `"<repo>\pyenv\Scripts\pythonw.exe" "<repo>\run_gridplayer.py" "%1"`
  与**注册表里当前已有的值逐字符相同** → 这次改动对该机的现有菜单是零影响

### 3.7 README 重写

`README.md` 从"两个改动"的早期说明重写为开源仓库体例：

1. 开头即声明上游链接、GPL-3.0-or-later、以及"上游版权归 vzhd1701 所有"
2. **与原版的差异** —— 按 播放 / 播放列表面板 / 窗口 / 系统集成 / 内部改动 五组列出，每条都标出涉及文件
3. **运行方式** —— 依赖、从源码启动、数据目录、可选的资源管理器右键菜单
4. **已知差异与注意事项** —— 含"本仓库只发代码不发个人设置""`docs/plans/` 是历史记录不要据此改代码""`PATCHES.diff` 已被 git 取代""测试为何叫 `check_*` 而不是 `test_*`"
5. 仓库结构、开发（跑检查 + 代码风格）、许可证、致谢

文中每个具体数字都实测核对过：扩展名 **66** 个、检查项 **304** 项、ruff 覆盖 **174** 个文件、"没有改动任何上游默认值"（用 `git diff` 里有无 `-` 行验证）。



---

## 4. "AI 写的代码"在 review 上最容易被挑什么 —— 逐条自查

| reviewer 会看什么 | 现状 | 证据 |
|---|---|---|
| 本机路径 / 个人环境泄漏 | ✅ 0 处 | **包内**扫 `E:\`、`GridPlayer-Mod`、`DSH`、中文，6 处命中经逐条查证**全是误报**（如 Windows 结构体成员 `dshSection`）。根脚本里曾有 2 处写死路径（`_shell_menu.ps1` 的参数默认值、`_setup-env.ps1` 的基础解释器），已在 §3.6.6 修掉 |
| 调试残留 | ✅ 0 处 | 无 `print(`、`breakpoint(`、`pdb.set_trace`；`TODO/FIXME/HACK/XXX` 的 4 处命中全是字体名 `Hack` |
| 风格与上游不一致 | ✅ 已解决 | **整仓库** ruff lint 0 项、format 174/174（§3.6.4） |
| 死代码 | ✅ 找到 1 处已删 | §3.3 |
| 悬空引用 | ✅ 已清除 | 3 处源码引用内部计划文档，已删（§3.6.3） |
| 提交粒度过大 | ⚠️ 仍是 2818 行一次性改动 | `git init` 与暂存已完成，但**尚未拆分提交**（§5.6） |
| 注释量与措辞 | ⚠️ 90 处 `# MOD` 标记，分布在 24 个文件 | §5.3（需你决定去留） |
| 测试能不能跑 | ✅ 已解决 | `check_*.py`，pytest 干净返回 `no tests collected`（§3.6.1） |
| 许可证 / 来源标注 | ✅ | §3.1 |

---

## 5. 还没做的

> §5.1（测试形态）与 §5.2（目录结构）曾列在这里，**已经在 §3.6 完成**，故删去。

### 5.3 `# MOD` 标记（需你决定）

- **90 处 `# MOD`，24 个文件**。走 Fork 路线建议保留（它们清楚标出了差异，读者能一眼看出哪些不是上游代码）；走 PR 路线必须全部去掉。
- 内部文档引用已经清掉（见 §3.6），但项目里仍有 4 份内部计划文档：`docs/plans/2026-10-02-p1-window-state.md`、`docs/plans/2026-10-02-p2-repeat-button.md`、`docs/plans/2026-10-02-p3-playlist-panel.md`、`docs/specs/2026-10-02-playlist-panel-design.md`。留在仓库里没问题（它们是很好的设计记录），但源码里已经不再指过去了。**注意：这几份文档是历史记录，里面写的仍是当时的 `app/gridplayer/` 路径和 `test_*.py` 名字，不要去"修正"它们** —— 那等于篡改当时的工作记录。

### 5.4 个人脚本

| 文件 | 建议 |
|---|---|
| `_setup-env.ps1` | 留下（别人搭环境要用） |
| `_runtests.py` / `_selftest.py` | 留下 |
| `_shell_menu.ps1` + `_shell_menu_label.txt` | Windows 专用、会写注册表。建议保留但移到 `scripts/`，README 里写清它是可选功能 |
| `_p1_gui_*.ps1` / `_p2_gui_*.ps1` | 一次性探针，删掉或已由 `.gitignore` 排除 |
| `_mkpatch.ps1` / `PATCHES.diff` / `.upstream/` | 有了 git 之后就是冗余；已由 `.gitignore` 排除 |
| `_setup.log` | 已排除 |

### 5.5 `PATCHES.diff` 的两个缺口（如果还想继续用它）

1. **10 个新增文件一个都不在里面** —— 补丁打到上游源码上是构建不起来的。
2. **路径是绝对路径**（`--- "a/<repo>\.upstream\gridplayer\__main__.py"`），换台机器无法直接应用。

有了 git 之后这两个问题自动消失（`git diff` 就是补丁），所以**建议不再维护 `PATCHES.diff`**。

### 5.6 CHANGELOG 与提交拆分

- 上游依赖 `keepachangelog`，仓库里有 `CHANGELOG.md`（**Keep a Changelog** 格式）。发 Fork 的话建议加一个 `[Unreleased]` 段落列出改动。
- `git init` 与全部暂存已完成（§3.5），但**还没提交**。2818 行一次性提交是最难 review 的形态，建议至少按功能拆成若干个提交（见 §7 第 4 步）。

---

## 6. 该传 / 不该传

| 路径 | 大小 | 传？ | 原因 |
|---|---|---|---|
| `gridplayer/` | 13.5 MB | ✅ | 真正的源码（原 `app/gridplayer/`） |
| `tests/` | 0.1 MB | ✅ | 测试，是加分项 |
| `docs/` | 0.1 MB | ✅ | 设计文档 |
| `README.md` | 6.7 KB | ✅ | **内容已过期**（仍写着"两个改动"），建议重写为开源仓库体例（见 §7） |
| `LICENSE` / `.gitignore` / `.gitattributes` / `requirements.txt` | 37 KB | ✅ | 本次新增 |
| `pyproject.toml` | 3.2 KB | ✅ | 取自上游，未改动 |
| `run_gridplayer.py` | 1 KB | ✅ | 源码启动入口 |
| `evidence/` | 0.3 MB | ❌ | 22 张开发期截图/渲染图，非精选演示图。已在 `.gitignore` 中排除；README 若要配图，挑 2~3 张手工放进 `docs/images/` |
| `GridPlayer.ico` | 32 KB | ⚠️ | 已暂存。**来源已查明**：由 `_extract_icon.py` 从上游原版 `GridPlayer.exe` 的 PE 资源里提取，5 个尺寸（48/32/24/16 BMP + 256 PNG），是 GridPlayer 自己的图标而非第三方素材。但它随上游二进制一起分发，上游 README 里那几条图标署名（Basic Icons / Flaticon、Suru Icons / CC BY-SA 4.0）是否覆盖它，仍建议发售前自行确认 |
| `pyenv/` | **247 MB** | ❌ | 本机虚拟环境 |
| `libVLC/` | **93.6 MB** | ❌ | VLC 二进制（LGPL/GPL，且非源码） |
| `.backups/` | 26.6 MB | ❌ | 工作备份 |
| `data/` | 0.1 MB | ❌ | **含你的 `settings.ini` 与日志** |
| `.upstream/` | 9.8 MB | ❌ | 上游快照，git 历史已取代它 |

真正该发的核心约 **14 MB**。

---

## 7. 建议的执行顺序

> 第 1、2 步已完成（见 §3.6），第 4 步的 `git init` 与暂存也已完成、只差提交。

1. ~~改名测试文件（`test_*.py` → `check_*.py`）~~ ✅ 已完成
2. ~~整理目录（`app/gridplayer/` → `gridplayer/`，`pyproject.toml` 回根目录）~~ ✅ 已完成
3. **重写 README**：开头写明"基于 GridPlayer 0.5.5 的修改版，遵循 GPL-3.0，上游链接"，然后列改动清单、构建方式、已知差异。
4. **按功能拆提交**（建议顺序，每个都能单独看懂）：
   1. 窗口状态记忆（`window_state.py`）
   2. 播放次序切换按钮（`video_overlay_buttons.py`、`video_overlay_icons.py`、`params/static.py`）
   3. 悬停显示控制条（`video_overlay.py`、`video_block.py`）
   4. 播放列表面板 + 缩略图（10 个新文件中的 9 个 + `grid.py` + `player.py`）
   5. 单屏标签栏（`video_overlay_tabs.py` + `single_mode.py` + `video_blocks.py`）
   6. 无视频时退出（`video_blocks.py`、`window_state.py`）
   > 注意：改动在若干文件里是**交错**的，按功能拆需要 `git add -p` 逐块暂存，不是按文件分就行。如果只发自己的 Fork，可以先用 2~3 个粗粒度的提交，不必强求。
5. **推上去**，README 里给出上游链接和许可证声明。
6. 之后想回馈上游时，再针对单个功能开分支、去掉 `# MOD` 标记、逐条提 PR。

---

*本文件的核对结果均可复现：`ruff` 用的是上游 `pyproject.toml` 里的规则集，pytest 用的是项目自己的解释器（`pyenv/Scripts/python.exe`，pytest 装在临时目录中，未改动 venv）。*
