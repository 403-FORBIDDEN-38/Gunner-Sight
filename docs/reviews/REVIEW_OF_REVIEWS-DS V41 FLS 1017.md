# 对三份审查报告 + 修复计划 + 三批次执行的审阅

- 审阅日期：2026-10-24（夜）
- 审阅对象：`CODE_REVIEW_2026-10-24.md`（S/M/L 52 项）、`PORTABILITY_REVIEW_2026-10-24.md`（P1-P17）、`FIX_PLAN_2026-10-24.md`、`RULES_AUDIT_2026-10-24.md`、批次 1-3 的实际代码改动
- 方法：以 `f5483be`（报告基线，审查时刻的 HEAD）为对照物做 `git archive` 快照，逐项按原始行号回读基线代码判定"问题是否真存在"；再以当前工作树判定"是否真修好"。凡可实测的断言一律实测（`pip wheel`、`pytest`、`mss 9.0.2` wheel 解包、离屏构造 InfoTab 探针）。
- 性质：只读审阅。未改动任何源代码、文档、配置。

---

## 〇、结论摘要

| 维度 | 判断 |
| --- | --- |
| 三份审查报告的技术判定 | **基本成立**。S 级 7/7 成立；M 级 24 项中 23 项成立（M11 定性偏重、其余准确）；P 级实测可验者全部成立（P1 基线 `pip wheel` 实测复现失败、P7 下载 9.0.2 wheel 证实无 `mss/windows/gdi.py`） |
| 报告自身瑕疵 | 3 处：章节标题"中（21 项）"实为 24 项；M4 症状描述被执行方误判为"不准"（见 §四.6）；P10 载具数 79→77（报告自己已修订） |
| 修复计划结构 | **正确**。批次划分（正确性 → 发布兼容 → 坏味道 → 墓碑）、硬约束提取、四个拍板项设置均合理，且把"用户决策"与"纯缺陷修复"分开处理是恰当的 |
| 修复计划完整性 | **有一处严重遗漏**：S6 从未进入任何批次（见 §三.1） |
| 修复执行质量 | 高于平均：有"有牙证明"（临时换回 HEAD 版验证测试必红）、有首版方案回退记录、有对审查结论的自我修正。91 passed 实测复现 |
| 遗留问题 | 3 项审查认定成立的问题**至今未修**（S6 严重 / M11 中 / M22 中），其中 S6 已实证 bug 仍在 |
| 新引入的问题 | 4 项（uv.lock 固化镜像源、S5 修复残留对象泄漏、M6 修复不彻底、S2 修复把磁盘 IO 放进锁） |
| 账目 | **准确**。5 个提交行数加总 3753/357 与逐提交 diff 完全吻合；26→86 test def、91 passed 实测一致 |

一句话：**报告可信，计划对路子，执行认真，但漏了一项严重 bug 没修，且有三个"修了但没修透"的地方。**

---

## 一、S 级 7 项逐条核验

| # | 基线代码实况（我在 `f5483be` 快照里看到的） | 判定 | 当前状态 |
| --- | --- | --- | --- |
| S1 | `core/magnifier.py:49` `import mss.windows.gdi`；`pyproject.toml:12` `mss>=9.0,<10.0`。**实测**：`pip download mss==9.0.2` 解包后 windows 相关只有 `mss/windows.py` 单文件，无 `gdi` 子模块 | **成立**（定性为"依赖声明与代码矛盾"，非"功能失效"——附录 B 的自我修正是对的） | ✅ 已修：约束 `mss>=10.0`，lock 重锁 10.2.0（实测 lock 内 `version = "10.2.0"`） |
| S2 | `save_config` 的 `_atomic_write(data)` 在 `with self._save_lock` **块外**；tmp 名固定 `config.json.tmp`（`base.py:233-256`、`276-287`） | **成立** | ✅ 已修：写盘入锁、tmp 名带 `threading.get_ident()`、finally 清 tmp、token 机制 |
| S3a | `vehicle_io.py:305-317` `except Exception: for dst in copied:` —— `copied` 由元组解包赋值，异常时未绑定 | **成立**（`NameError` 必然发生） | ✅ 已修（但修法比计划更进一步，见 §二.2） |
| S3b | `_process_image_dirs` 全程无 `..`/绝对路径校验，`mkdir(parents=True)` + `copy2` 直落盘 | **成立** | ✅ 已修：`is_relative_to(resources_root)` + 文件名 `Path(f).name != f` 双查 |
| S4 | `resource_tab.py:690-694` `action_copy` 分支用 `full_path`，该变量只在 `action_open`/`action_delete` 分支赋值 | **成立**（`rel_path` 取了不用，确系复制漏改） | ✅ 已修 |
| S5 | `_shutdown_engine` 把 `_up_tuner/_down_tuner` 置 `None`；`_init_engine` 的断开循环用 `getattr(self._up_tuner, 'on_pressed', None)` → 恒为 `None` → `continue`。而 `_height_*_tuner` 不在 shutdown 里置 None，所以断开有效——同一份代码三种处理，恰好坏的是 up/down | **成立**（描述精确） | ⚠️ 功能已修（断开前移到 shutdown），**但对象泄漏未解**，见 §四.2 |
| S6 | `info_tab.py:30` `setChecked(config.is_mascot_enabled())` 在 `_connect_ui_signals()` 之后执行；`_create_mascot` 里 `parent = self.window()`；`_ensure_tab` 先无父构造再 `insertWidget` | **成立** | ❌ **未修**，见 §三.1（已实证） |
| S7 | `overlay.py` 构造函数 connect 5 个 StateMachine 信号，全类无 `disconnect` | **成立** | ✅ 已修：`shutdown()` + `core/cleanup.py` 接线 |

---

## 二、M 级 24 项核验

（报告标题写"21 项"，实际列到 M24 —— 这是报告的一个计数笔误，不影响内容，但**影响了下游计划的完整性**，见 §三.2。）

| # | 基线成立性 | 现状态 | 备注 |
| --- | --- | --- | --- |
| M1 refresh_min_max 越权赋值 | 成立（文档写"仅 IDLE"，实现无条件赋 `current_angle`） | ✅ 已修 | 移位正确 |
| M2 bbox Scanner 起停竞态 | **成立**。基线 `submit` 用 `if not self.isRunning(): self.start()`，`run()` 是 `while self._tasks:`——队列判空到 run 返回之间 submit 的任务成了孤儿，且 `_pending_scans[path]=tid` 已登记，该 path 本次会话永不再 submit | ✅ 已修 | 常驻线程 + QWaitCondition，从根上消灭竞态，方案正确 |
| M3 ctypes 缺 argtypes | 成立 | ✅ 已修 | `overlay_base` 经 `from core.win32_utils import user32` 共享同一实例，间接受益成立 |
| M4 BboxCache 无锁 | 成立（见 §四.6：执行方"症状描述不准"的判断本身不准） | ✅ 已修 | 加 RLock 正确 |
| M5 射表每次重建 profile | 成立 | ✅ 已修 | 按 name 缓存 + `table is` 判有效 |
| M6 ammo_wheel.stop 语义错误 | 成立（stop 不置 `_enabled=False`） | ⚠️ 部分修 | 只补 `_enabled`，信号仍未断，见 §四.3 |
| M7 `_do_deferred_save` 无条件清引用 | 成立 | ✅ 已修 | token 比对 |
| M8 `keyboard.unhook_all()` | 成立 | ✅ 已修 | 改 `unhook(hook)` |
| M9 GrabWorker 无异常保护 | 成立 | ✅ 已修 | try/finally 保证 `_cam.close()` |
| M10 全屏整图进 crosshair pixmap 缓存 | 成立 | ✅ 已修 | 仅 `path == _crosshair_path` 构建 |
| M11 MouseHook `_stop` 早于 `_thread_id` 赋值 | 成立（窗口极窄，但 join 超时无警告日志是事实） | ❌ **未修** | 定性"中"偏高，应为"轻~中" |
| M12 重命名三种情况全弹"已存在" | 成立 | ✅ 已修 | |
| M13 倍率列表回写未抑制 | 成立 | ✅ 已修 | try/finally 包 `_suppress_mag_writeback` |
| M14 搜索全量重建 | 成立 | ✅ 已修（防抖 180ms，5 处全覆盖含 `VehicleFilterWidget`） | 增量过滤按决策不做，理由（77 载具规模重建 5-10ms）可接受 |
| M15 adapt_tab 读 window 私有 API | 成立 | ✅ 已修 | 新增 `theme_reapply_requested` 公共信号 |
| M16 热键捕获中销毁 LineEdit 泄漏钩子 | 成立 | ✅ 已修 | `destroyed` 连 lambda 捕获 self（PyQt 坑，记录得当） |
| M17 ammo_wheel 未创建时暂离不生效 | 成立 | ✅ 已修 | `on_ammo_wheel_ready()` 补偿 |
| M18 `_loading` 无 try/finally | 成立 | ✅ 已修 | |
| M19 splitterMoved 逐像素写盘 | 成立 | ✅ 已修 | eventFilter 拦 MouseButtonRelease |
| M20 ammo_wheel.start 的钩子引用永不释放 | 成立（基线 `aboutToQuit` 只清 magnifier） | ✅ 已修 | 进 cleanup 契约 |
| M21 startup_log 裸 open | 成立（基线 `main.py:159` 无 try） | ✅ 已修（作为 P4） | |
| M22 `_LibpngFilter` 设计上不可能生效 | 成立（libpng 是 C 层 `fprintf(fd 2)`，替换 `sys.stderr` 拦不住） | ❌ **未修** | 仍原样存在，注释仍宣称"过滤 stderr 中的 libpng 警告" |
| M23 清理契约四份实现漂移 | 成立 | ✅ 已修 | `core/cleanup.py` SSOT，4 个 tab 与 `TAB_CLEANUP_STEPS` 完全对齐（已核） |
| M24 export_gui_facts `ROOT = Path(".")` | 成立 | ✅ 已修（计划外顺带） | 现为 `Path(__file__).resolve().parent.parent` |

**M 级小计**：成立 24 / 24（M11 定性偏重）；已修 21，部分修 1（M6），未修 2（M11、M22）。

---

## 三、修复计划的正确性审查

### 1. 严重遗漏：S6 从未进入计划，也就从未被修

`FIX_PLAN` 批次 1 列了 10 条：S2+M7、S3a、S3b、S4、S5、S7、M1、M3、M6、M9。**S6 不在其中**，批次 2、3、4 也没有，`HANDOVER §十一` 偏差清单也没登记。

代码侧确认：`git diff f5483be d0c6c9b -- gui/tabs/info_tab.py` 只有两处改动——版本号 + P5 数据目录标签。S6 相关代码**一行没动**。

而报告 S6 描述的 `showEvent` 兜底在**基线里就已经存在**（`f5483be:gui/tabs/info_tab.py:86-89`），它一直是无效的：`__init__` 里 `setChecked(True)` 已经同步跑完 `_create_mascot()`，`showEvent` 的 `if ... and self._mascot is None` 永远不成立。报告其实已经点明了这一点（"创建后 `_mascot is not None`，`showEvent` 不会纠正"），但这条提醒没有被计划吸收。

**实测证明 bug 仍在**（离屏构造真实 `InfoTab`，config 返回 `mascot_enabled=True`）：

```
事实1 window() is self : True                      # 无父 widget 的 window() 就是自己
事实2 setChecked 同步触发 toggled: [True]          # setChecked 在 __init__ 内即触发 toggled
事实3 _mascot.parent() is tab : True | parent类型: InfoTab
事实3 parent() is None(应为顶层): False
```

即：**凡开启过吉祥物的用户，重启后桌宠仍是 InfoTab 的子控件**——切 tab 时消失、被页面边界裁剪、拖动钳制在页面内。问题被原样保留。

严重度评估：不是崩溃，是"常驻桌宠"这一产品设计静默失效，且只对使用该功能的用户可见。按报告自己的分级应保持"严重"（静默失效 + 用户可见的功能破坏）。

### 2. 计划覆盖面：M 级漏 2 项、批次 4 未承接 P 级

- 批次 3 自称"中坏味道 15 项"（GUI 8 + core 5 + main/tools 2）。加批次 1 的 5 个 M（M1/M3/M6/M7/M9）与批次 2 的 M21，合计 21 项。**M11、M22 落在缝里**，既没修，也没登记为"留批次 4"。
- 批次 4 的描述是"死代码 · 命名统一 · 魔法数字"，而 P 报告把 P3/P8/P9/P11-P17 明确标为"留批次 4"，`FIX_PLAN` 批次 4 却没把这几条写进去。执行者按当前批次 4 的描述干活，这些项会继续沉底。

这两个洞的根因是同一个：**计划是按"问题清单"抄的，不是按"报告编号全集"对账的**。报告标题的"21 项"笔误可能加剧了这个偏差。

### 3. 计划里做对的地方（应当保留的做法）

- **把"用户决策"从"缺陷修复"里剥出来**（拍板 A-D）。mss 约束、README 口径、数据目录降级、出厂载具库——这四项确实是产品决策而非 bug，先问再改是对的。
- **1.1 的改法比报告建议更完整**：报告只说"把 `_atomic_write` 纳入锁内或每线程唯一 tmp 名"，计划两条都做（"双保险"），实际还加了 finally 清 tmp。这是正确的过度防御——`os.replace` 失败会留下 302KB 垃圾 tmp。
- **1.2 的执行比计划更对**：计划只写"try 之前 `copied = []`"，执行时发现"仅在调用方预初始化只能挡 NameError，孤儿清理是空转"（因为异常路径上调用方拿不到局部进度），于是把回滚挪进 `_process_image_dirs`。这是靠测试逼出来的正确结论，值得肯定。
- **测试预算节自我作废**：原计划"删弱断言腾额度"是红线时代的产物，红线退役后改为主张"直接新增"，并在文件里保留作废说明。符合 G2"规则退役须明面"。
- **"浪 D 有牙证明"**：临时把 `main_window.py` 换回 HEAD 版验证 `test_close_event_stops_ammo_wheel` 必红，恢复后 md5 一致。这是本项目测试纪律里最硬的一条，做到了。
- **首版方案回退留痕**：bbox Scanner 首版"`_running` 标志 + wait(1000)"把 30s 劣化到 527s，回退过程完整记在 CHANGE_LOG。回退记录比成功记录更有价值，这条做对了。

### 4. 计划的一处口径瑕疵

批次 1 标"8 个文件、净增 ~90 行"，实际 20 文件 +471/-38。预估偏差 5 倍。这不影响正确性，但"预计规模"这种数字如果长期大幅失真，会让后续排期失去参考价值。建议要么不给数字，要么在交付时回填实际值。

---

## 四、执行结果核验 + 新引入的问题

### 已修项的独立验证（不是我信它的说辞，是我自己跑的）

| 验证对象 | 我的实测结果 |
| --- | --- |
| `pytest tests/ -q` | **91 passed**，事实一致（72 + 19） |
| P1 `pip wheel .` | 当前代码：出包成功，wheel 内容 `core`(29) / `gui`(21) / `main.py`，无 `config/resources/tests/tools/backups` 泄漏。**基线代码：实测失败**（"Multiple top-level packages discovered"）→ P1 成立且已修 |
| P7 lock | `uv.lock` 内 `mss 10.2.0`、`pyqt5-qt5 5.15.2`，与 pyproject 约束一致 |
| P10 载具库 | `config.json` 实测 77 个载具、302KB、`my_beloved: "Xiaocheng"` 保留 → 报告的 79→77 修订正确 |
| M23 契约对齐 | `gui/tabs/` 下恰好 4 个 `shutdown`/`cleanup`，与 `TAB_CLEANUP_STEPS` 四条完全对应，无遗漏无多余 |
| S3b 路径校验 | 目录条目走 `is_relative_to`，文件名走 `Path(f).name != f`（`../evil.png` 的 name 是 `evil.png`，被第二条拦下）→ 两处恶意输入都有覆盖 |

### 1. 【中】uv.lock 把作者的镜像源固化进了开源仓库

`uv.lock` 内所有包的 `source` 都是 `registry = "https://mirrors.aliyun.com/pypi/simple/"`，而 `pyproject.toml` 里**没有任何 `[[tool.uv.index]]` 声明**。

后果：任何人克隆仓库跑 `uv sync`，都会按 lock 记录去阿里云拉包；海外或企业网络环境可能解析失败，或 uv 报"lock 与 manifest 的 index 不一致"要求重解析。这与 P 报告的主题（"新用户按 README 一步就卡死"）是同一类矛盾——**声明与实际不符**，只不过这次是新引入的。

执行记录写明了原因（`UV_DEFAULT_INDEX` 指向阿里云"保持镜像来源一致"），说明它是本地偏好渗进了共享产物。建议：pyproject 显式声明 `[[tool.uv.index]]` + `default = true` 指向 pypi.org，或在 lock 前不设 `UV_DEFAULT_INDEX` 重锁。

### 2. 【中】S5 只断了信号，没解决对象累积

`_FineTuner(self, -1, "up", self)` 的 parent 是 tab，`_shutdown_engine` 置 None 后 Qt 仍持有它。断开信号解决了"注入翻倍"（功能正确性），但**每轮禁用→启用仍泄漏一个带 2 个 QTimer 的 QObject**，与审查报告 M 原文指出的"且每轮开关泄漏一个带 2 个 QTimer 的 QObject"不符。

一行可解：`_shutdown_engine` 里 `self._up_tuner.deleteLater()`（或 stop() 内自析构）。当前实现让 S5 从"功能 + 泄漏"降级为"仅泄漏"，值得补完。

### 3. 【中】M6 修了 `_enabled`，没断信号——而它现在真的进了退出路径

`stop()` 现在只补了 `self._enabled = False`。但批次 3 的 M18 让 `stop()` 进了 cleanup 契约（`collect_window_cleanup_steps`），而它挂在 `MouseHook.instance()` 这个**单例**上的 `mouse_wheel`/`mouse_down` 连接、以及 `state.ammo_type_changed` 等连接都没断。

在"进程退出"语境下无害（马上就没进程了）；但 `conftest.py` 的 teardown 走的也是同一份契约——**同一进程内反复建窗/拆窗时，这些槽会持续累积到单例上**，旧窗口对象被信号持有。审查原话"M6 语义错误：信号仍连着"这一半没有被处理。建议 `stop()` 里把这几条 connect 反向断掉。

### 4. 【轻】S2 的修法把磁盘 IO 放进了锁

把 `_atomic_write` 纳入 `_save_lock` 方向正确（消除了"两个线程交替写同一 tmp"），但副作用是：`_dump_config()` 在锁内（含 `RuntimeError` 时 3 次 × 50ms 重试）加上 302KB 落盘，全在锁内。UI 线程的 `request_save()` 若撞上 Timer 线程持锁，会阻塞 UI 线程。

量级上通常是几 ms，可接受；但既然代码里已经保留了"序列化失败重试 150ms"这条路径，极端情况下就是 150ms 的界面卡顿。可行的折中是：锁内只到 `os.replace` 之前（tmp 名已带线程 id，本来就不会互撞），或者把重试移到锁外。不改也不算错，但值得在 HANDOVER 登记一句"这是有意的锁内 IO"。

### 5. 【轻】P1 修好了"装得上"，但装完是空壳

wheel 里没有 `config/`、`resources/`。`pip install .` 后 `import main` 能过，但启动会走"无 config → 建骨架"，且 `resources/` 为空 → 没有任何准星图。README 也完全没有 `pip install` 这条路径的说明（引导的是 `uv sync` + `py main.py` 在仓库根跑）。

所以 P1 的真实价值是"**让 `uv sync` 能过**"（uv 构建当前项目需要 build backend），而不是"pip 安装可用"。P 报告的验证方法第 1 条（`pip install .` 后 `import main` 通过）达成，但"标准安装路径可用"这个目标并未达成。建议要么在 README 明说"本项目按源码仓库分发，不支持 pip 安装为库"，要么补 package-data。

### 6. 【轻】执行方把 M4 的"症状描述"判成不准，判错了

CHANGE_LOG 批次 3 写：

> **审查报告的症状描述不准**：预期的「迭代期增删 RuntimeError」不可复现——CPython 的 `json.dump` 是 C 实现、持 GIL 原子执行。

两个问题：

1. **项目自己的代码反驳了这个判断**。`core/config/base.py::_dump_config` 至今保留着：
   ```python
   for _ in range(3):
       try:
           return json.dumps(self._config, indent=4, ensure_ascii=False)
       except RuntimeError as e:
           last_err = e
           time.sleep(0.05)
   ```
   专门 catch `RuntimeError` 重试 3 次——这正是"dictionary changed size during iteration"的历史疤痕。症状真实发生过，才需要这个重试。
2. **"C 实现持 GIL 原子执行"不成立**。`json.dump` 的实现是 `for chunk in iterencode(obj): fp.write(chunk)`，encode 是生成器，`fp.write` 是 C 层 IO 会释放 GIL，迭代状态跨 yield 保留。它不会在单次 C 调用里原子跑完。

结论（加锁）是对的，价值重述（`_dirty` 复合竞争）也有道理，但**不该把审查的描述判成"不准"**。这条应当改成"症状形态可能不是 RuntimeError，但竞争窗口真实存在，代码里已有对应疤痕"。

### 7. 【轻】build.bat 的版本号提取与 pyproject 不同源

`pyproject.toml` = `0.0140300180`；build.bat 里那段 `for /f` 把 `V0.0140300180` 转成 `0.01.403.180` 塞给 `--product-version`。两者对不上（虽属历史编码方式，且 Nuitka 只要求 4 段数字）。更低风险的做法是直接在 build.bat 里读 `pyproject` 的 version，或者反过来让 pyproject 从 `APP_VERSION` 派生，去掉第二条转换链。

---

## 五、账目核对

| 账目条目 | 核对结果 |
| --- | --- |
| 5 个提交、+3753/-357 | **准确**。逐提交加总：975+8+471+716+1583=3753；44+4+38+70+201=357 |
| 各提交规模 | 全部吻合（16/1/20/15/30 文件） |
| 测试 26 → 86 个函数 | **准确**。基线 `grep -c "def test_"` = 26，当前 = 86 |
| pytest 实跑 91 passed | **准确**（我复跑 91 passed） |
| `config/config.json` 未提交漂移 | 确认（`git status` 只有 ` M config/config.json`），符合"运行期写入保留不动"的约定 |
| AGENTS.md 不在提交里 | 确认（`.gitignore` 排除，磁盘与本机文件为准——本次审阅也是对着磁盘读的） |

一处口径提醒："+3753/-357"是**5 个提交 diff 的算术和**，不是净变化。全天净 diff 是 `186faf0..d0c6c9b` = 56 文件 **+4090/-694**（同一文件被多批改过时每次都要重算）。两个数字都对，但混用会让人误判工作量，建议以后标"提交级合计"或"净 diff"。

---

## 六、建议的处理顺序

1. **补 S6**（严重，未修，已实证）：`_create_mascot` 推迟到「tab 已入栈」之后。最小改法是把 `__init__` 末尾的 `setChecked` 换成不触发 `_create_mascot` 的初始化（如 `blockSignals` 包一层，或直接只设 config 状态），并把创建完全交给 `showEvent`；创建前断言 `self.window() is not self`。配一条离屏契约测试（就是本审阅 §三.1 用的那三行断言）。
2. **补 M22**（中，未修）：删掉 `_LibpngFilter`（或在注释里写明"此机制无效，仅保留占位"）。留着一个自述有效、实际无效的机制，比没有更糟——它会让人以为噪音已治理。
3. **补 M11**（中偏轻，未修）：`_stop` 加"若 `_thread_id` 未就绪则记录并重试/等待"，`join` 超时写 warning。定性建议从"中"降为"轻~中"。
4. **补完 S5 / M6**（各 1-3 行）：`deleteLater()`；`stop()` 断信号。
5. **处理 uv.lock 镜像源**（中，新引入）：显式声明 index，或在干净环境不设 `UV_DEFAULT_INDEX` 重锁。
6. 其余（P3/P8/P9/P11-P17、M22 之后的墓碑清理）按原批次 4 推进，但**先按编号全集对一遍账**，别再让编号掉进缝里。

---

## 七、对审查报告本身的评价

报告质量高，有几处值得记的优点：

- **S1 的自我推翻**（附录 B）是本轮最有价值的部分。初版把"依赖声明矛盾"判成"功能失效"，用户质疑后逐项实证、明确承认三处缺陷（证据缺口 / 逻辑跳跃 / 定性错误），并把定性降级。这种"被推翻后自己写推翻过程"的做法比初版正确更难得。
- **P10 自己修订 79→77**，并在修订说明里撤回"移出个人字段"的建议（因为 HANDOVER §十 明令保留 `my_beloved`）。审查者遵守了被审查项目的既有裁决，没有用自己的价值观覆盖用户决定。
- **每条都带"验证方法"**，且方法是可执行的（`pip wheel . --no-deps`、复制到 Program Files 用标准用户双击、构造含 `../` 的 manifest）。这让"修没修好"变成可判定命题，而不是"我觉得好了"。

需要提防的：

- **计数与编号漂移**是这份报告唯一的结构性问题（"21 项"实为 24 项、批次 3 的 M 编号与 CODE_REVIEW 编号错位）。它已经实际造成了 S6 漏修和 M11/M22 沉底。下次建议在计划阶段加一步机械对账：把报告里所有 `^###? [SMP]\d+` 抓出来，逐条映射到批次号或"已登记不修"，缺一项就不许开工。
- **"不可复现"不等于"不成立"**。M4 的误判就是从这个等式来的。报告写作时可以加一句判据：不可复现先查"是不是症状形态变了"，再决定要不要降级。

---

_本文件为审阅记录，不是执行记录。上面提到的任何改动均未实施。_
