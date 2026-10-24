# GunnerSight 发布/分发兼容性专项审查报告

- 审查日期：2026-10-24
- 视角：**本地开发环境正常、开源发布或分发到其他机器后出故障**的问题
- 方法：全网状扫描（硬编码路径 / 环境变量 / 子进程 / 平台假设 / 网络 / cwd）+ 逐点源码核实 + 关键项实证（实测 `pip wheel .`、下载 mss wheel 对比、解包检查 dist 产物）
- 性质：只读审查，未改动任何代码

严重程度：**严重** = 标准安装/分发路径直接失败或用户数据丢失；**中** = 特定环境出错或明显发布缺陷；**轻** = 边缘场景 / 一致性。

---

## 〇、先说结论

这个项目「在作者机器上」有三条互不重叠的能跑路径：① `py main.py`（系统 Python + mss 10.2.0）；② tools/build.bat 打包（同样用系统 Python）；③ 以上两者都不走 `uv.lock`。而 README 给新用户指的两条路——`uv sync` 装依赖、以及任何非 `py main.py` 的标准安装——**恰好都是断的**。下面 A/B 两类各有一条「严重」。

---

## 一、安装与构建路径（未声明的依赖 / 打包缺陷）

### P1【严重】`pip install .` 必然失败，pyproject 无构建系统与包发现配置

**位置**：`pyproject.toml`（无 `[build-system]`、无 `[tool.setuptools]` 段）

**实证**（本机实测，非推断）：

```
$ pip wheel . --no-deps
error: Multiple top-level packages discovered in a flat-layout:
       ['gui', 'core', 'logs', 'config', 'frames', 'backups', 'resources'].
```

扁平布局下 setuptools 自动发现把 `logs/ config/ frames/ backups/ resources/` 也当成了包。即使剔掉 gitignore 的目录，fresh clone 上仍有 `core gui tests tools config resources frames` 七个顶级包，同样失败。

**触发条件**：任何不走「仓库根目录 `py main.py`」的场景——`pip install .`、`pipx`、`python -m build`、以及大概率同样调用构建后端的 `uv sync`（README 第 35 行教新用户用的正是这条，注意作者本人没有 .venv、uv 也不在 PATH，这条流程从未被验证过）。

**影响**：OSS 用户按 README 操作，第一步就卡死，报错还指不到根因（是打包配置缺失，不是他们的操作问题）。

**修复建议**：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["core", "gui"]
py-modules = ["main"]
```

`resources/`、`config/` 如需随包装配，用 `[tool.setuptools.package-data]` 或文档说明「数据文件不随 pip 包分发，请从仓库获取」。

**验证方法**：干净环境执行 `pip wheel . --no-deps` 出 wheel；`pip install .` 后 `python -c "import main"` 通过；`uv sync` 在无缓存机器上跑通。

---

### P2【中】打包工具链未声明，tools/build.bat 与 README 工作流脱节

**位置**：`tools/build.bat:21`（`py -m nuitka`）、`pyproject.toml`（无任何 build 依赖组）、`README.md:35`（教 `uv sync`）

三个断裂点：

1. **Nuitka 未在项目任何地方声明**（pyproject 无可选依赖组，无 requirements-dev.txt）。OSS 用户按 README `uv sync` 后执行 `tools/build.bat`，`py -m nuitka` 报 `No module named nuitka`。
2. **解释器脱节**：`uv sync` 创建的是 `.venv`，而 tools/build.bat 用的是 `py` 启动器（系统 Python）。作者的机器上两者恰好是同一个（系统 Python 什么都有），新用户机器上不是。
3. **`--assume-yes-for-downloads`（tools/build.bat:40）**：Nuitka 首次构建会**从互联网下载 MinGW C 编译器**（约百 MB）。离线机器、企业网络拦截环境的构建会以难以解读的方式失败；这也是构建不可复现与供应链面。

**触发条件**：任何非作者机器的构建尝试。

**影响**：构建失败，且失败信息指向「缺包/缺编译器」而非「文档没写全」。

**修复建议**：README 构建章节改为与 uv 工作流一致的一条命令，例如 `uv run --with nuitka python -m nuitka main.py ...`（或把 tools/build.bat 改成调用 `uv run`）；在 pyproject 增加 `[project.optional-dependencies] build = ["nuitka", "zstandard"]`；在 README 明示「首次构建需联网下载 C 编译器」。

**验证方法**：找一台干净 Windows（或干净 VM），严格按 README 从零走：装 uv → `uv sync` → 构建 → 产出 dist。全程记录断点。

---

### P3【轻】tools/build.bat 带 UTF-8 BOM，且并发数硬编码

**位置**：`tools/build.bat:1`（首行 `﻿@echo off`，BOM 存在，已实证）

部分 cmd.exe 版本会把 BOM 拼进首行，`@echo off` 失效 → 整脚本命令被回显（不致命，但输出混乱，且这是历史上 build_err.txt 乱码的同类根源）。另 `--jobs=8` 硬编码 8 线程。

**修复建议**：另存为「UTF-8 无 BOM + CRLF」；`--jobs=%NUMBER_OF_PROCESSORS%`。

**验证方法**：`python -c "print(open('tools/build.bat','rb').read()[:3])"` 应不为 `b'\xef\xbb\xbf'`；在一台未安装过任何 Python 的 Windows 上双击 tools/build.bat，首行无乱码回显。

---

## 二、写盘位置与权限差异（分发的最大风险）

### P4【严重】启动期三处无保护地写 exe 同级目录，只读位置下双击无反应

**位置**：

- `main.py:159` — `open(os.path.join(_log_dir, "startup_log.txt"), "w")`，**裸 open 无 try**
- `main.py:186/201` — `crash_log.txt` 同样裸 open
- `core/logger.py:21` — `log_dir.mkdir(parents=True, exist_ok=True)`，无 try

**触发条件**（任一）：发布版被放进 Program Files 且用户非管理员；公司统管的锁定目录；网络共享/只读介质；OneDrive/Dropbox 同步文件夹（"文件按需"占位文件会让写操作以奇怪方式失败）。

**影响**：`PermissionError` 在 QApplication 创建前抛出，程序直接退。而发布版编译时带了 `--windows-console-mode=disable`（tools/build.bat:41）——**没有控制台，用户看到的就是"双击什么都没发生"**，连错误信息都没有。这是"本地能跑、分发即死"最典型的一条，且完全不可诊断。

**修复建议**：三处写盘全部包 try/except，失败时降级到 `%TEMP%`（`tempfile.gettempdir()`）；启动早期（QApplication 之前）的致命错误用 `ctypes.windll.user32.MessageBoxW` 弹窗，保证任何失败用户都能看见。

**验证方法**：把 `dist/main.dist` 复制到 `C:\Program Files\GunnerSightTest\`，以**标准用户**（非管理员）双击 `GUNNER SIGHT.exe`，应正常启动且日志落到 TEMP；再试OneDrive 同步文件夹内运行。

---

### P5【严重】config/resources 按"绿色便携"固定在 exe 同级，只读安装下设置全部丢失

**位置**：`core/config/base.py:26-38`（`get_app_base_dir()` frozen 返回 `Path(sys.executable).parent`）、`base.py:99-100`（`config_dir.mkdir` / `resources_dir.mkdir` 无保护）

**触发条件**：同 P4 的只读/受保护位置。此外 OneDrive 等同步文件夹会让 `config/config.json` 产生同步冲突副本。

**影响**：两种失败形态——① `mkdir` 抛 PermissionError，ConfigManager 初始化即崩（启动失败）；② 目录恰好已存在则启动成功，但之后每次 `save_config()` 的 `_atomic_write` 异常被 catch + log 静默吞掉，**用户所有设置改完重启即丢**，且无任何提示。

**修复建议**：启动时做一次可写性探测，按「exe 同级（可写时，保持便携）→ `%APPDATA%\GunnerSight`（不可写时降级）」顺序选择数据目录；探测与降级结果写一条日志。至少要把 P4/P5 合并成一次「数据目录决策」并暴露给用户（信息页显示当前数据目录）。

**验证方法**：Program Files 下以标准用户运行 → 改几个设置 → 重启 → 检查设置是否保留（当前预期：不保留）。

---

### P6【中】配置损坏回退路径在只读环境下会静默覆盖原文件

**位置**：`core/config/base.py:171-184`

load 失败 → `rename` 到 `backups/`（`os.makedirs` + rename 都在 try 里，**失败被 `pass` 吞掉**）→ 直接 `self.save_config()` 写最小骨架。

**触发条件**：config.json 损坏 **且** 安装目录不可写（或 backups 创建失败）。

**影响**：备份静默失败后，骨架配置把原（可能只是轻微损坏、尚可手工恢复的）config.json **覆盖**，用户数据永久丢失且无提示。

**修复建议**：rename 失败时先把原文件内容读进内存，确认骨架写入成功后再决定如何处理；任何回退都写 crash/startup 日志并在 UI 弹一次提示。

**验证方法**：构造一个损坏的 config.json + 只读目录，运行后检查原文件是否被覆盖、logs 里有无记录。

---

## 三、依赖声明 vs 实际运行环境

### P7【中】mss 版本矛盾：README 教的路（uv sync）必然拿到会让放大镜失效的版本

**位置**：`core/magnifier.py:49`、`pyproject.toml:12`（`mss>=9.0,<10.0`）、`uv.lock`（锁 9.0.2）、`README.md:35`（`uv sync`）

**事实**（已在 2026-10-24 的 S1 复审中完整实证）：代码 `import mss.windows.gdi` 要求 mss≥10.0；uv.lock 锁的是 9.0.2（无 `mss/windows/gdi.py`）；作者本机不走 uv，系统 Python 装的是 10.2.0 所以本地无感。

**触发条件**：任何按 README `uv sync` 的新用户。

**影响**：放大镜抓屏线程 import 即死，功能静默失效（详见 CODE_REVIEW_2026-10-24.md S1 修订）。

**修复建议**：二选一——① 约束改 `mss>=10.0` 并 `uv lock` 重锁（代码已实质依赖 10.x 模块结构）；② 写 try/except 版本无关导入（注意两版本 CAPTUREBLT 分居 `mss/windows.py` 与 `mss/windows/gdi.py`，`import mss.windows as _gdi` 不能通吃）。

**验证方法**：干净目录 `uv sync` 后 `py main.py`，开放大镜电闸，看 `logs/app_*.log` 有无 `[GrabWorker]` 相关记录、窗口是否有画面。

---

### P8【轻】requires-python 无上界，新版 Python 上依赖解析必败

**位置**：`pyproject.toml:6`（`requires-python = ">=3.10"`）

PyQt5 5.15.x 只为到 CPython 3.13 的版本提供 wheel。用户用 3.14+ 安装时，pip 会尝试**源码编译 PyQt5** 并失败，报错长达几十行且指不到根因。

**修复建议**：改 `>=3.10,<3.14`（或实测支持后放宽），让解析阶段快速失败。

**验证方法**：在 3.14 环境 `pip install .`，期望在依赖解析阶段就看到清晰的 Python 版本不支持提示（修后）；修前则是一堆编译错误。

---

### P9【轻】Windows-only 无平台守卫，非 Windows 下报错是一串 ctypes 堆栈

**位置**：`core/win32_utils.py`（顶层 `ctypes.windll`）、README 已声明 Windows 10 2004+

README 声明了仅 Windows，这本身没问题；但 Linux/macOS 用户 import 时看到的是一条 `AttributeError: module 'ctypes' has no attribute 'windll'` 内部堆栈，而不是"本软件仅支持 Windows"。

**修复建议**：`main.py` 最开头做 `sys.platform != "win32"` 检查，print 明确信息后 `sys.exit(1)`。

**验证方法**：WSL/Ubuntu 下 `python main.py`，看首行输出是否人话。

---

## 四、资源与数据分发

### P10【中】出厂 config.json 是作者的完整使用态（310KB / 79 个载具 / 全部热键绑定）【2026-10-24 修订：`my_beloved` 部分作废】

**位置**：`config/config.json`（git 跟踪中）、`tools/build.bat:37`（`--include-data-dir=config=config` 打进每个发布包）

**实证**：出厂配置含 79 个载具（M1126、T-90、BMP 系列……）、每载具的弹种与热键绑定，以及顶层字段 `my_beloved: "Xiaocheng"`。

**修订说明（2026-10-24 晚，通读 HANDOVER §十后）**：`my_beloved` 是用户**特意保留的署名式字段**，HANDOVER 明文"不要删、不要改、不要当成无用字段清理"——本报告初版"移出个人字段"的建议**作废**。开源前已做过凭据扫描（api_key/secret/token 等 0 匹配），隐私风险仅限"使用者痕迹"层面。

**修订后结论**：唯一待办是"79 个载具的出厂库是否最小化"——这是产品策略，**需用户拍板**。若保留现状（作为出厂数据是合理设计），README 应明示"首次启动自带完整载具库"；若最小化为骨架 + 2-3 个示例载具，完整库改为首次启动可选导入。

**验证方法**：解压任一 dist 成品，`python -c "import json;d=json.load(open('config/config.json'));print(len(d['vehicles']))"` 看是否 79。

---

### P11【轻】中文资源目录名在跨平台压缩/解压下会乱码

**位置**：`resources/其他/`、`resources/分层 临时/`、`resources/单层 临时/`（dist/main.dist/resources 同样存在）

**触发条件**：发布用的 zip 若在 Linux/macOS 上打包（`zip`/`tar` 在非 UTF-8 locale 下不给文件名写 UTF-8 标志），中文目录名解压后乱码 → 对应准星图全部"丢失"（表现为某些载具准星不显示）。

**修复建议**：发布统一用 Windows 侧工具（资源管理器"发送到压缩文件夹"或 PowerShell `Compress-Archive`）；或在 GitHub Actions/CI 打包时确保 `zip -UN=UTF8` 等价行为；README 的下载说明提醒用 7-Zip/WinRAR 而非部分 Linux 工具解压。

**验证方法**：把 dist 打成 zip，在**英文区域 Windows** 与中文 Windows 各解压一次，对照 `resources/` 目录名与文件数。

---

### P12【轻】图标回退链含 PyInstaller 死路径，图标可用性依赖 resources 目录不被裁剪

**位置**：`main.py:64-91`（`sys._MEIPASS` 分支在 Nuitka 下永不命中，无害）；实际生效的是 `exe_dir/resources/app_icon.ico`（已确认 dist 中该文件存在）

**影响**：当前可用。但将来若裁剪 resources 或改打包参数，任务栏图标会静默变默认（只有一条 info 日志）。

**修复建议**：删掉 `_MEIPASS` 死分支；把 `resources/app_icon.ico` 显式加入 tools/build.bat 的 `--include-data-files`（与其它文档同样待遇），不依赖 resources 目录碰巧包含它。

**验证方法**：删掉 dist 里 resources/app_icon.ico 后运行，确认日志有记录（修后应仍从显式数据文件拿到图标）。

---

## 五、外部服务与网络

### P13【轻】两个按钮依赖第三方网站，无声明、无降级

**位置**：`gui/main_window.py:366/371`（`QDesktopServices.openUrl` → squadcalc.app、squad-armor.com）

离线时点击静默无反应；对方站点下线则功能静默死亡。程序本身不做任何网络请求（这点是干净的：无 urllib/requests/socket 使用），仅 Delegates 给浏览器。

**修复建议**：代码注释或 README 标注"外链为第三方服务， availability 不由本项目保证"。

**验证方法**：断网点两个按钮，确认至少浏览器给出错误页而非程序静默。

---

### P14【轻】GS_DEBUG 是唯一环境变量依赖——检查过，此项干净

`core/logger.py:27` 的 `GS_DEBUG` 为可选开关且有 docstring 说明；`tools/` 里的 `QT_QPA_PLATFORM`/`TEMP` 均为开发工具且用法标准。**未发现依赖特定环境变量才能运行的分发问题。**

---

## 六、架构与系统假设

| # | 位置 | 问题 | 程度 |
| --- | --- | --- | --- |
| P15 | tools/build.bat / pyproject | 仅 x64：Nuitka 打什么架构就是什么，Windows on ARM 用户靠 x64 模拟运行 Qt5（多数能跑但无保证），README 无架构声明 | 轻 |
| P16 | README:18 | "Windows 10 2004+" 与 `WDA_EXCLUDEFROMCAPTURE`（放大镜防录屏）的系统要求一致，此项**无问题** | — |
| P17 | tools/build.bat:21 | 假设 `py` 启动器存在且指向装了 PyQt5+Nuitka 的 Python；全新 Windows（仅 Microsoft Store Python）上 `py` 不存在或指向错误解释器。与 P2 合并修复 | 轻 |

---

## 七、修复优先级与总体验证矩阵

**建议顺序**：P4/P5（只读位置启动即死 + 设置丢失）→ P1（pip install 失败）→ P7（mss，OSS 用户必踩）→ P2（打包链）→ P6 → P10 → 其余。

**分发前验收清单**（每项都应在"非作者机器"上过）：

| # | 验收项 | 方法 |
| --- | --- | --- |
| 1 | 标准安装路径 | 干净环境 `uv sync` + `pip install .` 均成功 |
| 2 | 从零构建 | 干净 Windows 按 README 产出 dist（含联网下载编译器场景） |
| 3 | 只读位置运行 | Program Files + 标准用户双击，正常启动、日志降级 TEMP |
| 4 | 设置持久化 | 上述环境下修改设置，重启后保留 |
| 5 | 可选模块全开 | 放大镜/角度仪/测距/吉祥物电闸全开，跑 10 分钟看 logs 无异常 |
| 6 | 压缩包完整性 | 英文 Windows 解压 zip，中文资源目录名与文件数与发布前一致 |
| 7 | 出厂配置 | 解压成品检查 config.json 不含个人痕迹 |
| 8 | 非 Windows 报错 | Linux 下启动给人话错误而非 ctypes 堆栈 |

---

## 总体评价

发布链的断点非常集中：**新用户的标准入口（uv sync / pip install / tools/build.bat）三条全断，而作者本人一条都没走过**——本地能跑依赖的是"系统 Python 恰好装了 10.2.0 的 mss 和 nuitka"这条偶际链路。写盘位置（config/logs/日志全部钉死在 exe 同级且无保护）则让任何"安装到受保护目录"的分发方式直接失去可用性。这两类问题修掉（P1/P2/P4/P5/P7），这个项目的分发健壮性会从"作者机器限定"变成"任何 Windows 10 2004+ 机器可用"。
