# 对《REVIEW_OF_REVIEWS-DS V41 FLS 1017》的交叉审阅

- 审阅日期：2026-10-25（凌晨）
- 审阅对象：`Desktop/111111/REVIEW_OF_REVIEWS-DS V41 FLS 1017.md`（下称"DS 篇"）
- 背景：DS 篇是对 GunnerSight 三份审查报告 + 修复计划 + 三批次执行的审阅。本轮是对 DS 篇本身的审阅，同时对**同一批事实**做独立复核。
- 方法：以 `186faf0`（首个修复批次 `bc22412` 之前的最后提交）为改动前基线，该 tree 与 15:44 源码备份快照逐文件一致；所有"改动前"断言回读基线，所有"当前状态"断言读工作树 + `git diff`。凡可用命令判定的一律实测（`grep` / `git diff --stat` / `git show` / 计数脚本），不依赖任何一方的转述。
- 性质：只读审阅，未改动任何源代码、配置、测试。

---

## 〇、结论摘要

| 维度 | 判断 |
| --- | --- |
| 基线方法 | **有效**。`f5483be` 与 `186faf0` 仅差 `tools/` 三文件，core/gui/main.py 一行未动，S/M/P 判定不受影响（附一处口径提醒，见 §一） |
| DS 的实证类结论 | **6/6 实测复现**：S6 未修、uv.lock 镜像源、S5 泄漏残留、M6 未断信号、M4 反证、净 diff 口径 |
| DS 的错判 | **1 处**：§四.7「build.bat 与 pyproject 版本号不同源」指控不成立——两者同源，均从 `APP_VERSION` 派生（§三.1） |
| DS 的越界背书 | **1 处**：摘要把"报告可信"推广到全篇，但它**零考察轻级 21 项**；轻级里有一条会造成**删掉活代码**的假发现（§三.2） |
| DS 的半程验证 | **1 处**：M23 只核了 tab 侧四条就宣布"无遗漏无多余"，window 侧第四份实现仍未完全接线（§三.3） |
| DS 的漏检 | **2 项**，其中 1 项严重：批次 3 的 M17 修复引入了新 bug，而 DS 把它判为「✅ 已修」（§四.1） |
| 与我的独立复核的一致性 | S6 未修、M11/M22 未修、91 passed、7 个严重项成立——**完全一致** |

一句话：**DS 篇的实证工作扎实，它自己跑出来的东西都站得住；但它的覆盖面有洞，而且在最关键的一格上把"改动存在"当成了"改动正确"。**

---

## 一、基线选取：有效，但有一处口径值得写明

DS 以 `f5483be` 为对照物。我原本以 `186faf0` 为基线。实测两者差异：

```
$ git diff --stat 186faf0 f5483be -- core gui main.py tools tests
 tools/audit_docs.py       | 19 ++++-------
 tools/build.bat           | 57 +++++++++++++++++++++++++++++
 tools/export_gui_facts.py |  8 +++---
 3 files changed, 68 insertions(+), 16 deletions(-)
```

（`build.bat` 的 57 行是 `bc22412` 的 git mv 被计入两遍所致。）core/、gui/、main.py **零差异**，所以两个基线对 S/M/P 的技术判定完全等价，DS 的选择没有问题。

口径提醒一处：**三份报告的写作时刻不一致**，DS 笼统地说"审查时刻的 HEAD"不精确。实测文件 mtime：

```
CODE_REVIEW_2026-10-24.md       16:21   ← 早于 bc22412(18:27)
RULES_AUDIT_2026-10-24.md       17:51   ← 早于 bc22412
PORTABILITY_REVIEW_2026-10-24.md 21:28  ← 晚于 bc22412
```

严格做法是每份报告各自取写作时刻的 tree。本例中因为 `bc22412` 只搬了 tools/、归档了 docs、且把三份 review 本身入库，没有触碰任何业务代码，所以结论不受影响——但**下一次未必**。叠加 15:44 备份快照三方互证，是更稳的做法。

---

## 二、DS 成立项逐条复核（我独立重跑，不是背书）

| DS 的 Claim | 我的独立实测 | 判定 |
| --- | --- | --- |
| §三.1 **S6 从未修复** | `git diff f5483be d0c6c9b -- gui/tabs/info_tab.py` 只有两处：版本号 177→180、P5 数据目录标签。**S6 相关代码一行未动**。基线 `f5483be:gui/tabs/info_tab.py`：`_connect_ui_signals()` 之后才 `setChecked(...)`；`showEvent` 的 `if ... and self._mascot is None` 兜底在基线里就存在且恒假 | **成立**，且 DS 补的离屏三事实探针比我原本的行号论证更硬 |
| §四.1 **uv.lock 固化阿里云镜像** | `uv.lock` 全文 `mirrors.aliyun.com` 出现 **1437** 次；`pyproject.toml` 无 `[[tool.uv.index]]`、无 `UV_DEFAULT` 相关声明 | **成立**。这一条是我此前遗漏的，DS 抓得对，且这是修复过程新增的风险而非历史债，**价值最高** |
| §四.2 **S5 只断信号未解泄漏** | `angle_meter_tab.py:760-761` `_FineTuner(self, -1, "up", self)` —— parent 即 tab；`_shutdown_engine` 内 `self._up_tuner = None` 前有 `stop()`，**全文无 `deleteLater`、无 `setParent(None)`**（grep 确认） | **成立**。Qt 父子持有 → 每轮禁用→启用累积一个带 2 个 QTimer 的 QObject |
| §四.3 **M6 `stop()` 未断信号** | `stop()` 现为 `self._enabled = False` + `self._hook.release()` + 三个 hide；而 `ammo_wheel_selector.py:236-239` 的 `mouse_wheel`/`mouse_down`/`ammo_type_changed`/`magnification_changed` 四条连接**全未断** | **成立**。前两条挂在 `MouseHook.instance()` 单例上，同进程反复建窗确实累积 |
| §四.6 **M4"症状不可复现"的判断本身不准** | `core/config/base.py:345-361` `_dump_config` 至今保留 `for _ in range(3): try: json.dumps(...) except RuntimeError: sleep(0.05)` | **成立**。代码自己留下的重试疤痕反证了"从未发生"，这个反证方式很漂亮 |
| §五 **净 diff 口径混淆** | `git diff --stat 186faf0 d0c6c9b` = **56 files, +4090/-694**，与 DS 所述完全相同；而逐提交加总 3753/357 也对 | **成立**。两个数字都对但含义不同，DS 提醒得当 |

---

## 三、DS 的三处问题

### 1. §四.7「版本号不同源」——**指控不成立**

DS 原文：

> `pyproject.toml` = `0.0140300180`；build.bat 里那段 `for /f` 把 `V0.0140300180` 转成 `0.01.403.180` 塞给 `--product-version`。**两者对不上**……更低风险的做法是直接在 build.bat 里读 `pyproject` 的 version，**或者反过来让 pyproject 从 `APP_VERSION` 派生**，去掉第二条转换链。

实测三者实况：

```
gui/tabs/info_tab.py:14   APP_VERSION = "V0.0140300180"
pyproject.toml:7          version = "0.0140300180"  # 与 gui/tabs/info_tab.py 的 APP_VERSION
                                                    # 保持同步（该常量为唯一权威来源）
tools/build.bat:37        for /f ... -c "from gui.tabs.info_tab import APP_VERSION; ..."
```

**三者同源，权威源就是 `APP_VERSION`**——pyproject 的注释白纸黑字写着，build.bat 也是程序化从它派生。DS 自己提的补救方案"让 pyproject 从 `APP_VERSION` 派生"**已经是现状**。

DS 观察到的 `0.0140300180` vs `0.01.403.180` 是**渲染格式**差异，不是血缘差异：Nuitka 的 `--product-version` 要求 1-4 段纯数字，而项目版本号是 `V0.<10位定长串>` 的编码方式，所以 build.bat 必须做一次拆段。这是有意的转换，不是漂移。

**真正存在的残余风险**（DS 方向对但定位错了）：`pyproject` 到 `APP_VERSION` 的同步靠**人工 + 注释约定**，`tests/` 下 grep 不到任何 `APP_VERSION` 断言，**没有自动化守卫**。该改的表述是"缺一道版本同步的机械校验"，而不是"不同源"。

### 2. 摘要的背书超出了自己核过的范围——轻级 21 项零考察，其中一条会造成删活代码

DS 在 §〇 写「三份审查报告的技术判定 **基本成立**」，并逐条列了 S 级 7 项、M 级 24 项、部分 P 级。**轻级（CODE_REVIEW 第三节，21 项）一次都没提**。

而轻级里恰恰有一条是我这次判断**最危险**的假发现：

> 死代码（均无调用方）：`gui/widgets.py`：RegionSelector、PointPicker、CrosshairPreviewWidget、make_int_spin、**VehicleFilterWidget** 四个未用方法

实测：

```
gui/tabs/angle_meter_tab.py:43    from ... import VehicleFilterWidget
gui/tabs/angle_meter_tab.py:578   self.link_vf = VehicleFilterWidget(mode="check")
gui/tabs/overview_tab.py:93       self.quick_vf = VehicleFilterWidget(mode="select")
gui/tabs/squad_macro_tab.py:117   self.vf = VehicleFilterWidget(mode="click")
tests/test_wave_c1_search.py      另有 3 处测试实例化
```

**它是三处共用的活控件，不是死代码。**（另外四个：RegionSelector / PointPicker / CrosshairPreviewWidget / make_int_spin 实测确系仅剩定义，指控正确。此处报告还自称"四个"却列了 5 个名字，自身计数也错。）

危险在于：这条**已经进了 `FIX_PLAN` 批次 4 的删除清单**——

> 死代码（`gui/widgets.py` 3 个类、pause 热键、`SKIP_TYPES`、`_update_mag_item_text` 等）

照单执行就是删掉正在被三个页面使用的控件。DS 在 §三 通篇赞扬计划结构正确、并要求"优先级整体合理"，但没有往下翻一格校验计划内容的真实性。

还有一处内部矛盾 DS 没发现：它自己在 §二 M14 一格写"防抖 180ms，**5 处全覆盖含 `VehicleFilterWidget`**"——同一篇文档里，这个控件既是"无调用方的死代码"，又是"被搜索防抖覆盖的五处之一"。两个说法不可能同时为真。这种自相矛盾本身就是信号：把两份结论摆在一起对比，就能反查出至少一处错。

### 3. M23「无遗漏无多余」只核了一半

DS 原文：

> M23 契约对齐：**✅ 已修** | `gui/tabs/` 下恰好 4 个 `shutdown`/`cleanup`，与 `TAB_CLEANUP_STEPS` 四条完全对应，无遗漏无多余

tab 侧四条确实对齐，但 `core/cleanup.py` 有**两个** collector：

- `collect_tab_cleanup_steps`（第 46 行）——tab 侧，DS 核了
- `collect_window_cleanup_steps`（第 66 行）——window 侧：`overlay.shutdown` / `hotkey.shutdown` / `ammo_wheel.stop` / `config.save_config`，**DS 没核**

而 M19 原文点名的四份实现之一就是 `tools/export_gui_facts`。实测它现在的收尾：

```python
# tools/export_gui_facts.py:228-230
from core.cleanup import collect_tab_cleanup_steps, run_cleanup_steps
run_cleanup_steps(collect_tab_cleanup_steps(win))
```

**只 import 了 tab 侧，window 侧没接。** 该文件 226-227 行的注释自述"离屏构造起了放大镜抓屏线程，不清理会报 QThread: Destroyed while thread is still running"——放大镜确实被 tab 清理覆盖了，但 hotkey / overlay / 弹种滚轮走的是另一条 collector。

四个引用点的实测接线情况：

| 调用方 | tab 侧 | window 侧 |
| --- | --- | --- |
| `gui/main_window.py:788` | ✅ | ✅ |
| `main.py:474` | ✅ | ✅ |
| `tests/conftest.py:63` | ✅ | ✅ |
| `tools/export_gui_facts.py:230` | ✅ | ❌ **缺** |

所以是"清单漂移从四份各自为政收敛到三份半"，不是 DS 写的"无遗漏无多余"。实际影响有限（离屏 export 路径下 `ammo_wheel` 大概率未被创建），但**断言的强度超过了证据**。

---

## 四、DS 漏掉的两项（本次最重要）

### 1. 【严重】批次 3 的 M17 修复引入了新 bug，而 DS 把它判为完成项

DS §二 的 M17 一格：

> M17 ammo_wheel 未创建时暂离不生效 | 成立 | **✅ 已修** | `on_ammo_wheel_ready()` 补偿

实测当前 `gui/main_window.py:683-706`：

```python
def on_ammo_wheel_ready(self):
    tab = self.get_tab(self.TAB_DISTANCE_METER)
    ...
    # 先无条件断开旧连接再连（幂等收口，HANDOVER §十二）
    try:
        tab.enable_check.toggled.disconnect()      # ← 第 702 行，无参
    except TypeError:
        pass
    tab.enable_check.toggled.connect(_on_distance_toggle)
```

PyQt 的**无参 `disconnect()` 是清空该信号的全部槽**，不是"断开我自己的"。而同一个 `enable_check.toggled` 上还挂着标定测距 tab 自己的电闸 `_on_enable_toggle`。我实测确认两者都被清掉。

触发序列恰恰就是 M17 想修的场景：**用户配置了启用标定测距 → 启动时 `_precreate_tab` 创建该 tab（建立 `enable_check` → `_on_enable_toggle`）→ 100ms 后 `on_ammo_wheel_ready()` 把全部槽抹掉 → 只连上自己的 `_on_distance_toggle`**。

后果：电闸从"旧的轻微显示不同步"变成"**彻底失效**"——勾选/取消不再控制模块启停。91 passed 测不出（新写的测试只锁"新连接生效"，不锁"原有槽还在"）。

为什么 DS 没抓到：它在 §三/§四 对已修项几乎全部做了"看到改动 = 改好了"的推断，唯独没有对**每条 `disconnect` / `deleteLater` / `stop()` / 置 None** 单独复核一遍。这是"审阅者自己的 reviewer checklist"缺一环，和它正确批评计划制定者"按清单抄不按编号全集对账"是同一类病，只是换了个位置。

同时记一笔：注释援引的 **HANDOVER §十二「先无条件断开再 connect」约定，只适用于自己拥有的连接**。`enable_check` 属于 tab、不属于 main_window，跨所有者信号不能直接套这条约定。

### 2. 【中】P5 只做了一半，`resources_dir` 没有跟着降级

DS 全文未对 P5 的修复做实质验证（§四 的实测表只覆盖了 P1 / P7 / P10 / M23 / S3b）。

实测 `core/config/base.py`：

```python
155:  self.config_dir    = _resolve_portable_config_dir()          # 三级降级：exe同级→%APPDATA%→%TEMP%
156:  self.config_file   = self.config_dir / "config.json"
157:  self.resources_dir = get_app_base_dir() / "resources"        # ← 钉死 exe 同级，无降级
```

`_resolve_portable_config_dir()`（第 77 行）那套"可写探测 + %APPDATA% 降级 + 出厂配置播种"只救了 config，没救 resources。于是 Program Files 下的标准用户导入 .gsv（要往 resources 写目录）**必然失败**，且批次 2 在第 164-167 行加的 try/except 只是记一行 info 日志——**静默失败**。

这条不怪 DS"判错"，它压根没查；但 DS 在摘要里给了"修复执行质量高于平均"的整体评价，缺了这个 caveat 会误导排期。

---

## 五、方法论：两份审阅放一起能提炼出的东西

| 观察 | 说明 |
| --- | --- |
| **实证项命中率远高于推断项** | DS 凡"跑命令跑了出来的"（S6 探针 / pip wheel / uv.lock 计数 / 净 diff）——全对。凡"读代码推断意图的"（版本号同源性 / M17 已修 / M23 无遗漏）——错了 3 处。这提示审阅时应把"可以证明但不能只靠读"的项优先升级为实测 |
| **"改动存在" ≠ "改动正确"** | DS 对 M17 判"✅ 已修"的理由就是"`on_ammo_wheel_ready()` 补偿"——它看到了机制被实现，没验证机制的行为对不对。这是我这次看到的最值得警惕的一格 |
| **跨文档对照能反查内部矛盾** | DS 自己的 M14 备注与 CODE_REVIEW 轻级在同一个控件上互斥。把多份文档的结论摆到一张表上，比逐篇精读更容易暴露假发现 |
| **两轮的盲区不重叠** | 我漏了 uv.lock 镜像源；DS 漏了 M17 回归与 P5 半修。可以说明：单人审阅在这个规模上（5 提交 / 4090 行 / 52 项发现）几乎必然有盲区，**交叉审阅是必要的而不是冗余的** |
| **两轮一致的部分可以定稿** | S6 未修、M11/M22 未修、7 项严重成立、91 passed、账目准确——两个独立基线、两套方法得出同一结论，这部分不必再审第三遍 |

---

## 六、合并两份审阅后的处置顺序

优先级按"后果 × 是否需要立即拦住"排：

| P | 项 | 来源 | 动作 |
| --- | --- | --- | --- |
| **P0** | M17 引入的回归（`main_window.py:702` 无参 disconnect） | 本轮 | 改定向 `disconnect(_on_distance_toggle)` 或 `UniqueConnection`；**并补一条"原有槽仍在"的断言**——否则同类错误还会再来 |
| **P0** | S6 吉祥物 parent 未修 | 两轮一致 | `__init__` 末尾用 `blockSignals` 包住 `setChecked`，创建完全交给 `showEvent`；创建前断言 `self.window() is not self` |
| **P1** | uv.lock 固化阿里云镜像 | DS | pyproject 显式声明 `[[tool.uv.index]]` 指向 pypi.org + `default = true`，或在干净环境（不设 `UV_DEFAULT_INDEX`）重锁 |
| **P1** | P5 `resources_dir` 未降级 | 本轮 | 与 config 共用同一套可写探测，否则 Program Files 标准用户导入 .gsv 静默失败 |
| **P1** | `tools/export_gui_facts.py` 未接 window 侧清理 | 本轮 | 补 `collect_window_cleanup_steps(win)`；顺手把"四调用方必须同时接两个 collector"做成一条契约测试，防止第五份实现出现 |
| **P1** | M22 `_LibpngFilter` 声称有效实则无效 | 两轮一致 | 删除，或注释改为"占位，无实际效果" |
| **P2** | S5 泄漏 / M6 未断信号 | 两轮一致 | 各 1-3 行：`deleteLater()`；`stop()` 里反向断开 236-239 |
| **P2** | **批次 4 清单里的 `VehicleFilterWidget` 必须先剔除** | 本轮 | 它是活代码，**动刀前务必先核这一条** |
| **P2** | M11 `_stop` 竞态 | 两轮一致 | `join` 超时写 warning；定性从"中"降到"轻~中" |
| **P3** | 版本号同步无机械守卫 | 本轮（修正 DS） | 加一条测试断言 `pyproject.version == APP_VERSION.lstrip("V")`——比改 build.bat 更对症 |
| **P3** | P3/P8/P9/P11-P17 未进批次 4 | 两轮一致 | 开工前按编号全集做一次机械对账：把报告里所有编号抓出来（`grep -oE '^#+ [SMP][0-9]+'` 之类），逐条映射批次号或登记"不修" |

---

_本文件为审阅记录（对审阅的审阅），不是执行记录。上面提到的任何改动均未实施。_
