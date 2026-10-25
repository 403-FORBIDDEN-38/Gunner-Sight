# GunnerSight 2026-10-24 修复批次 —— 合并处置单

- 生成日期：2026-10-25
- 来源：三轮独立复核合并（DS 篇 / HY4 篇 / HY4 对 DS 篇的交叉审阅）
- 基线：`186faf0`（首个修复批次 `bc22412` 之前的最后提交），与 15:44 源码备份快照逐文件一致；`f5483be` 与本基线在 `core/ gui/ main.py` 上零差异，两者等价
- 性质：**执行单**。不是新的审查报告。

---

## 〇 给执行者的三条前置指令

1. **不要重新审计这 52+17 项。** 下面"已定稿"章节里的结论已经过两套独立基线、三种方法交叉验证，不要推翻、不要重跑。
2. **凡本单给出 `文件:行号` 的，先读那几行再动手。** 行号基于当前工作树（`d0c6c9b` + `config/config.json` 运行期漂移）。
3. **发现代码与本单不符时：停下来报告，不要自行改判。** 上一轮的教训正是"用新判断覆盖旧账本且不留痕"。

---

## 一 已定稿（两轮独立复核一致，不必再审）

| 项 | 结论 |
|---|---|
| S1–S7 | 7 项全部成立。S1 初版定性错误（"功能必然失效"），修订后定性正确（依赖声明与代码要求矛盾） |
| M1–M24 | 24 项中 23 项按行号逐条命中。**M11 定性偏重**（应为轻~中）。M22 成立但不属"源码内可证"（libpng 是 C 层写 fd 2，依赖运行时知识） |
| M24 附注 | 报告称"另外四个工具都用 `Path(__file__)`"是虚的：同仓仅 `audit_docs.py`、`audit_manual.py` 两个如此，另两个无 ROOT 定义 |
| P1–P17 | 方向全部正确。**两处数字错**：P1 称"七个顶级包"（真实 3 个：`core/ gui/ tests/`；`frames/` 在基线全树不存在）；P10 称载具 79（真实 **77**，三份配置一致） |
| 账目 | 逐提交合计 +3753/-357 与 `git show` 吻合；全天净 diff `+4090/-694`（口径不同，两个都对）；26→86 test def、91 passed 复跑一致 |
| 未修 | **S6**（严重）、**M11**、**M22** |
| 半修 | **S5**（信号断了，QObject 未释放）、**M6**（`_enabled` 修了，信号未断）、**P5**（只救 config，未救 resources） |
| 新增风险 | `uv.lock` 全文 **1437 处** `mirrors.aliyun.com`，而 `pyproject.toml` 无 `[[tool.uv.index]]` 声明 |

---

## 二 本轮修正的四条结论（勿沿用旧判）

### 2.1 【推翻】M17 判"已修"是错的 —— 它引入了 P0 回归

前序复核把 M17 记为完成项，理由是"`on_ammo_wheel_ready()` 补偿已落地"。**看到机制存在 ≠ 机制正确。**

```python
# gui/main_window.py:697-706
tab.set_function_active(wheel.is_suspended)

def _on_distance_toggle(checked, w=tab, wh=wheel):
    if checked:
        w.set_function_active(wh.is_suspended)

try:
    tab.enable_check.toggled.disconnect()      # ← 第 702 行，无参
except TypeError:
    pass
tab.enable_check.toggled.connect(_on_distance_toggle)
```

PyQt 的无参 `disconnect()` **清空该信号的全部槽**，不是"只断我自己"。同一信号上还挂着标定测距模块自己的电闸：

```python
# gui/tabs/distance_meter_tab.py:102
self.enable_check.toggled.connect(self._on_enable_toggle)
```

**实测（offscreen，双槽连同一信号，无参 disconnect 后 emit）：两个槽都不再触发。**
触发序列：config 启用标定测距 → 启动预创建该 tab（连上电闸）→ 约 100ms 后 `main.py:366` 调 `on_ammo_wheel_ready()` → 电闸被抹 → 只剩同步槽。
后果：**启用勾选框彻底失效**，不写配置、不起停引擎、不注册热键。91 passed 测不出（`test_wave_c2_signals.py:45-64` 只断言"新连接生效"）。

### 2.2 【推翻】"pyproject 与 build.bat 版本不同源"指控不成立

```toml
# pyproject.toml:7
version = "0.0140300180"  # 与 gui/tabs/info_tab.py 的 APP_VERSION 保持同步（该常量为唯一权威来源）
```
```bat
REM tools/build.bat:37 —— 程序化从 APP_VERSION 派生，非手写
for /f "delims=" %%v in ('%PY_RUN% -c "from gui.tabs.info_tab import APP_VERSION; ..."') do set APP_VER=%%v
```

三者同源，权威源就是 `APP_VERSION`。观察到的 `0.0140300180` vs `0.01.403.180` 是**渲染格式差异**（Nuitka `--product-version` 要求 1–4 段纯数字），不是血缘差异。
**真实的缺口是**：`tests/` 下 `grep APP_VERSION` **零命中**，同步全靠人工 + 注释约定，**无机械校验**。该改的是这个，不是 build.bat。

### 2.3 【修正】M23"无遗漏无多余"过强

tab 侧四条确实对齐。但 `core/cleanup.py` 有**两个** collector，window 侧未被核。四个调用方的实际接线：

| 调用方 | tab 侧 | window 侧 |
|---|---|---|
| `gui/main_window.py:787-788` | ✅ | ✅ |
| `main.py:473-474` | ✅ | ✅ |
| `tests/conftest.py:62-63` | ✅ | ✅ |
| `tools/export_gui_facts.py:230` | ✅ | ❌ **缺** |

### 2.4 【补正】批次 4 的删码清单：点名的组件里有一个是活的

`CODE_REVIEW` 轻级把 `VehicleFilterWidget` 列为死代码，但实测它是**三处共用的活控件**：

```
gui/tabs/angle_meter_tab.py:578   VehicleFilterWidget(mode="check")
gui/tabs/overview_tab.py:93       VehicleFilterWidget(mode="select")
gui/tabs/squad_macro_tab.py:117   VehicleFilterWidget(mode="click")
tests/test_wave_c1_search.py:104,120
```

**但要说准确**：`FIX_PLAN` 批次 4 写的是"`gui/widgets.py` **3 个类**"，与真实的三个死类（`RegionSelector` / `PointPicker` / `CrosshairPreviewWidget`，实测引用数均为 0；另加函数 `make_int_spin`）恰好吻合，**计划本身大概率已避开这个坑**。危险只在源头清单：它自述"四个未用方法"却列了 5 个名字，计数自相矛盾。
→ 处置：批次 4 把这 3 个类**点名写死**，消除歧义。

---

## 三 执行清单

### P0 —— 功能回归 / 严重缺陷，先做这两个

**P0-1 修 `main_window.py:702` 的无参 disconnect**

- 难点：`_on_distance_toggle` 是**闭包**，每次调用新建，**没有引用可供定向断开**。照字面"保留引用再断"改不动。
- 正确改法：把它提成实例方法 —— `self._on_distance_toggle`，然后
  ```python
  try:
      tab.enable_check.toggled.disconnect(self._on_distance_toggle)
  except TypeError:
      pass
  tab.enable_check.toggled.connect(self._on_distance_toggle)
  ```
  备选：`Qt.UniqueConnection`（重复连接返回 False 不抛异常，需处理返回值），但仍要保证不误伤他人。
- 同时修注释：援引的 `HANDOVER §十二`「先无条件断开再 connect」**只适用于自己拥有的连接**；`enable_check` 属于 tab，不属于 main_window。请在 HANDOVER §十二 补一句边界。
- 验收（必须新增，否则同类回归必再来）：断言连接 `_on_distance_toggle` 之后 `_on_enable_toggle` 仍然生效 —— 建议 emit `toggled` 后检查 `_on_module_toggle` 的副作用（配置写入 / 引擎起停），而不是只数连接数。

**P0-2 修 S6（吉祥物 parent）**

- 现状：`gui/tabs/info_tab.py:30` 在 `__init__` 里 `setChecked(...)` **同步触发** toggled → 走创建路径；`:106` 取 `self.window()`，而 `gui/main_window.py:410-421` 十个 tab 工厂**全部不传 parent**，`_ensure_tab` 是先无父构造再 `insertWidget` ⇒ `window()` 返回 tab 自身 ⇒ 桌宠成为页面子控件，切 tab 即消失。基线里 `showEvent` 的兜底判断 `self._mascot is None` 恒假，从未生效。
- 改法（二选一，推荐 A）：
  - A. `__init__` 里用 `blockSignals(True)` 包住 `setChecked`，创建完全交给 `showEvent`，并在创建前断言 `self.window() is not self`
  - B. 在工厂里给 `InfoTab` 传 parent —— **但必须先验证桌宠仍是顶层窗**（parent 会改变窗口语义）
- 验收：离屏断言 `_mascot.parent() is None`

### P1 —— 漏项与半交付

| # | 项 | 动作 |
|---|---|---|
| P1-1 | `uv.lock` 固化阿里云镜像 | `pyproject.toml` 显式声明 `[[tool.uv.index]]` 指向 pypi.org 且 `default = true`，或在不设 `UV_DEFAULT_INDEX` 的干净环境重锁。**注意**：重锁会改动 1437 行 source 字段，做完必须验 `uv sync` 能过 |
| P1-2 | P5 `resources_dir` 未降级 | `core/config/base.py:157` `self.resources_dir = get_app_base_dir() / "resources"` 钉死 exe 同级，而 `:155` 的 config 已走三级降级。让 resources 跟随同一套可写探测；否则 Program Files 标准用户导入 .gsv **静默失败**（批次 2 在 `:164-167` 加的 try/except 只记 info 日志） |
| P1-3 | `tools/export_gui_facts.py:229-230` 缺 window 侧 | 补 `collect_window_cleanup_steps(win)`。顺带把它做成契约测试：**四个调用方必须同时接两个 collector** |
| P1-4 | M22 `_LibpngFilter` | 删除，或注释改为"占位，无实际效果"。它只替换了 `sys.stderr`，拦不住 libpng 的 C 层 `fprintf(fd 2)` |
| P1-5 | M11 `_stop` 竞态 | `join(0.5)` 超时补 warning 日志；定性从"中"降到"轻~中" |

### P2 —— 卫生，可打包一次做完

| # | 项 | 动作 |
|---|---|---|
| P2-1 | S5 QObject 累积 | `_shutdown_engine` 里 `self._up_tuner = None`（`:799`）前补 `deleteLater()`；`_down_tuner` 同（`:802`）。parent 是 tab，不释放则每轮禁用/启用累积一个带 2 个 QTimer 的对象 |
| P2-2 | M6 信号未断 | `core/ammo_wheel_selector.py` `stop()` 只有 `_enabled=False` + `release()` + 3 个 hide；补反向断开 `:236-239` 的四条连接。前两条挂在 `MouseHook.instance()` 单例上，已进退出路径 |
| P2-3 | 批次 4 点名死类 | 把 `RegionSelector` / `PointPicker` / `CrosshairPreviewWidget` 三个类名写进清单；`VehicleFilterWidget` **不得进入** |
| P2-4 | `mss` 上界 | `pyproject.toml:12` `mss>=10.0` 补 `<11`——9→10 的 breaking change 已经咬过一次（S1 的由来） |

### P3 —— 账本纪律

| # | 项 | 动作 |
|---|---|---|
| P3-1 | 版本同步守卫 | 加一条测试：`pyproject.toml` 的 version == `APP_VERSION.lstrip("V")`。比改 build.bat 对症 |
| P3-2 | 编号全集对账 | 开工前机械跑一遍，把报告里所有编号抓出来，逐条映射到批次号或"决定不修 + 理由"：<br>`grep -oE '^#+ [SMP][0-9]+' docs/reviews/*.md \| sort -u`<br>S6 就是这么丢的：自评"严重"，却在"报告→计划"的转写中被静默丢弃，且无"为何不修"记录 |
| P3-3 | 未排期项 | P3 / P8 / P9 / P11–P13 / P15–P17 标"留批次 4"，而批次 4 明写"不单独排期" ⇒ 既不在已完成批次、也不在日程。要么建一个真实存在的批次 4，要么明确标 won't-fix |
| P3-4 | 已顺手修但未入账 | `tools/export_gui_facts.py` 的 `ROOT` 已改成 `Path(__file__).resolve().parent.parent`（即 M24），但**任何批次记录都没提**。补记，否则将来回溯会以为没人管过 |

---

## 四 禁区

1. **不得删 `VehicleFilterWidget`** —— 三处页面 + 两处测试在用。删之前先 `grep -rn "VehicleFilterWidget(" --include=*.py`。
2. **不得对非自己拥有的信号使用无参 `disconnect()`**。这条错误已经犯过一次。
3. **不得用"改动存在"代替"改动正确"**。本轮 5 处错判，全部是这一个病：看到代码落地就判完成，没验行为。
4. **不得在无记录的情况下改判或跳过。** 跳过一项必须在 `FIX_PLAN` 或 `HANDOVER §十一` 留下一行"不修 + 理由"。

---

## 五 测试的普遍缺口（这轮暴露的根因）

91 passed 之所以掩盖了 P0 回归，是因为这批测试的断言方向单一：

> 锁的是「我加的东西在工作」，不锁「我碰过的东西还活着」。

建议在 `tests/` 里加一条通用规矩并写进 `AGENTS.md §4`：**凡修改/断开既有信号、清理方法、注册项的地方，必须有一条断言证明"原有的仍然生效"**，而不只是"新的生效"。

---

_本文件为处置单，未改动任何源代码、配置、测试。执行时按 §〇 三条前置指令行事。_
