# 对 step5 审查报告与三批修复的独立复核

- 复核日期：2026-10-25
- 复核对象：`docs/reviews/` 下三份诊断报告（CODE_REVIEW / RULES_AUDIT / PORTABILITY_REVIEW）+ FIX_PLAN + 三个批次的实际落地代码
- 方法：先把报告写作时刻的代码完整还原成只读基线，再用 `git diff` 逐行核对该基线与每一个修复批次
- 性质：**只读复核，未改动任何业务代码**

---

## 〇、先说清楚证据来源

三份报告写在改动之前，而当前工作区已是改动后产物，**不能拿当前代码去验证那些诊断**。做法是先把「报告写作那一刻」的代码完整还原：

```
git archive 186faf0 | tar -x -C <基线目录>
diff -rq <基线目录> backups/GunnerSight_src_20261024_154439
   → 除 AGENTS.md / 两份报告 / edit_demo.py / startup_log.txt（均未跟踪）
     和 config/config.json（运行期漂移）外，逐文件完全一致
```

`186faf0` 是当天第一个修改批次（`bc22412`）之前的最后一个提交；15:44 的备份快照是 step5 自己留的，比第一份报告还早 37 分钟。两者互证 ⇒ 该基线就是报告写作时的代码状态，报告里的行号可直接对应。

「修复是否正确」则一律用 `git diff <批次>~1 <批次> -- <file>` 核对真实落地的代码，**不采信 CHANGE_LOG 的自述**。

---

# 第一部分：诊断成立吗

## 1.1 严重级 7 项

| # | 结论 | 关键证据 |
|---|---|---|
| S1 | **初版错误、修订后成立** | 初版断言"放大镜功能必然失效"是错的——本机实际运行的是 mss 10.2.0，`mss.windows.gdi` 存在，功能可用。附录 B 的自我修正方向正确：真正的问题是**依赖声明（`mss>=9.0,<10.0`）与代码实质要求（≥10.0）矛盾**，属环境依赖型脆弱而非功能失效 |
| S2 | **成立** | `core/config/base.py:233-249`：`save_config` 在 `with self._save_lock:` 释放**之后**才调 `_atomic_write`；`_atomic_write` 的 tmp 名是**固定**的 `config.json.tmp`。主线程立即保存与 Timer 线程防抖保存撞车时，确实存在两个线程交替写同一 tmp 的可能 |
| S3 | **成立，且报告说轻了** | ① `copied` 未绑定时 `for dst in copied` 抛的是 `UnboundLocalError`（NameError 的子类），定性无错；② 路径穿越：除 `../` 外，**绝对路径同样逃逸**——`image_list` 条目为 `/X/evil.png` 时 `resources_dir / "/X/..."` 直接落到其他盘符位置。报告只提了相对路径，实际面更宽 |
| S4 | **成立** | 同上，抛的是 `UnboundLocalError`（`full_path` 在同函数 687/698 行有赋值 ⇒ 是局部变量而非全局） |
| S5 | **成立** | 关键佐证在类定义里：`_FineTuner.stop()`（`angle_meter_tab.py:122-127`）**只停两个 QTimer，不做 disconnect**。而 `_shutdown_engine` 把 `_up_tuner/_down_tuner` 置 None，使 `_init_engine` 的"先断再连"循环里 `getattr(None, 'on_pressed', None)` → None → `continue`，对旧 tuner 是空操作。报告说"同一份代码里三种处理方式，恰好反的那两个是坏的"——逐条对照后完全属实 |
| S6 | **成立** | `main_window.py:410-421` 十个 tab 工厂**全部不传 parent**（`lambda: InfoTab(config=..., resources=...)`），而 `_ensure_tab` 是"先无父构造 → 写 `_tab_cache` → `insertWidget`"的顺序 ⇒ `InfoTab.__init__` 里 `self.window()` 返回 tab 自身。后果描述准确 |
| S7 | **成立** | `OverlayRenderer.__init__` 连 5 个 StateMachine 信号，全文件 `grep disconnect` **零命中**。报告自评为"结构性隐患、当前未爆发"，没有夸大症状 |

## 1.2 中级 24 项 —— 23 项成立

| # | 结论 | 证据 / 备注 |
|---|---|---|
| M1 | 成立 | `core/angle_meter.py:237-243` docstring 说"IDLE 状态时"更新，实现是**先无条件覆写 `current_angle` 再判 state 才 emit** |
| M2 | 成立 | `core/bbox_crop.py:268-270/279-281`：入队 → `if not self.isRunning(): start()`；`run()` 里 `while self._tasks:` 判空即退。落在"队列已空、线程未结束"窗口的任务成孤儿，且 `overlay.py:206-208` 的 `_pending_scans` 守卫让它本次会话再也提不出来 |
| M3 | 成立 | 对照很清楚：`core/mouse_hook.py:24-51` 给全部十个 API 设了严格签名，而 `core/win32_utils.py:274/286` 的 `Get/SetWindowLongW` 与 `core/overlay_base.py:54` 的调用没有 |
| M4 | 成立 | `BboxCache` 全文件 `grep "threading\|Lock"` **零命中**，裸 dict 跨线程读写 |
| M5 | 成立，**引错了文件** | 现象属实（`angle_changed` 每次回调都在 `core/config/angle_meter.py:118-132` 重建 BallisticProfile，且 `:125` 在函数体内 import）；但报告引的 `angle_meter.py:126` 是错的路径 |
| M6 | 成立 | `core/ammo_wheel_selector.py:247-251` `stop()` 只有 `release()` + 三个 `hide()`，`_enabled` 仍是 True。配合 `core/mouse_hook.py:128-133` 的引用计数（≤0 才真停）和 `core/hotkey_manager.py:535` 的第二份 acquire，确实停不掉钩子 |
| M7 | 成立 | `core/config/base.py:276-278` 无条件 `self._save_timer = None`，无 timer 身份比对 |
| M8 | 成立 | 调用链写实：`reload_hotkeys`(:742) → `_register_all_hotkeys` → `_unregister_all_keyboard_hotkeys`(:242) → `keyboard.unhook_all()`(:235)。而 `:423` 明明保存了 `self._keyboard_global_hook` 却没用它 |
| M9 | 成立 | `core/magnifier.py:47-79` `run()` 全程无 try，`mss.MSS()` / `grab()` / `QImage()` 任一抛异常则 `self._cam.close()` 永不执行 |
| M10 | 成立 | `core/overlay.py:225` 无条件 `QPixmap.fromImage`，直到 `:232` 才判是不是当前准星路径 |
| M11 | 成立 | `core/mouse_hook.py:143-161`：`_thread_id` 在 `_loop` 内才赋值，`_stop()` 抢先则既不 Post WM_QUIT（线程阻塞在 `GetMessageW` 唤不醒），`join(0.5)` 超时**也没有任何日志** |
| M12 | 成立 | `gui/tabs/vehicle_config_tab.py:542-553` 是单 `if/elif/else`，取消 / 空名 / 同名三路全落 else 弹"已存在" |
| M13 | 成立 | `:725-727` 裸 `setCurrentRow`；对照组：载具 `:495-501`、弹种 `:629-635` 都包了 try/finally flag |
| M14 | 成立，**给了三个错行号** | "5 处"属实（连接行是 `angle_meter_tab.py:396`、`magnifier_tab.py:148`、`resource_tab.py:181`、`vehicle_config_tab.py:325`、`widgets.py:144`），但报告列的三个位置是**处理函数**不是 connect 行 |
| M15 | 成立 | `gui/tabs/adapt_tab.py:270-273` 两处访问私有 API |
| M16 | 成立 | `gui/hotkey_widgets.py` 全文件 `grep closeEvent/destroyed` **零命中**，`hotkey_tab.py:85-90` 的 `deleteLater()` 确实会在捕获态下丢掉 release |
| M17 | 成立 | `main_window.py:656-658` wheel 为 None 时跳过连接，全文件再无补偿路径 |
| M18 | 成立 | `angle_meter_tab.py:854` → `:871` → `:877`，无 try/finally |
| M19 | 成立 | `vehicle_config_tab.py:309`、`resource_tab.py:170` 直连 `splitterMoved` |
| M20 | 成立 | 全仓 `grep "ammo_wheel"` 只有 `tests/test_ammo_wheel_selector.py:44` 一处 `.stop()`；closeEvent 和 `_cleanup` 都不碰它 |
| M21 | 成立 | `main.py:158` 裸 open 早于 `:185` 的 excepthook 生效 |
| M22 | 成立，但**不是源码内可证的事实** | `_LibpngFilter`(:28-49) 确实只替换了 `sys.stderr`；"libpng 是 C 层 fprintf(fd 2) 拦不住"依赖仓库外的运行时知识。方向可信，但不该当成已实证结论 |
| M23 | **成立，且这条最值钱** | 四份实现逐份列出来是：① `main.py:420-427` 仅 `cleanup()`（1 名）；② `main_window.py:748-761` `shutdown()`×3 + `cleanup()` + `hotkey.shutdown()` + `config.save_config()`（4 项）；③ `conftest.py:55-62` `("shutdown","cleanup")`（2 名）；④ `export_gui_facts.py:228-229` `("shutdown","cleanup","_shutdown_engine","_destroy_engine","_shutdown_macro")`（5 名，含两个私有名）。覆盖范围各不相同，且无测试锁定一致性 |
| M24 | 成立，**但"另外四个工具"是虚的** | `ROOT = Path(".").resolve()` 依赖 CWD 属实（`:14`），但同仓只有 `audit_docs.py:15`、`audit_manual.py:14` 两个用 `Path(__file__)`，`check_mpo_support.py`、`ui_access_test.py` **根本没有 ROOT 定义** |

### 轻级里 4 条应当撤回的假发现

| 假发现 | 实际情况 |
|---|---|
| `gui/widgets.py` 的 `VehicleFilterWidget` 是死代码 | **正在被实例化**：`angle_meter_tab.py:573`（`mode="check"`）、`overview_tab.py:93`（`mode="select"`）。且报告自述"四个未用方法"却列了 5 个名字，计数也错。这条最危险——照它去删会删掉活代码 |
| `main.py` 的 `get_app_base_dir()` 已导入未复用 | **`main.py:99` 明确用了它**（`resources_dir = get_app_base_dir() / "resources"`） |
| `ammo_wheel_selector.py` 的 `update_highlight` 未被调用 | `:402` **有调用**（外部弹种变更路径）。准确说法是"滚轮路径没走增量接口" |
| `HANDOVER.md:86` 出厂值口径漂移 | `export_gui_facts.py:183` 的注释已自陈"与发布包一致"并给出理由，是**表述口径差异**而非实现违背文档，定性偏重 |

## 1.3 移植性报告 17 项 —— 方向全对，两处硬 factual error

| # | 结论 | 证据 / 偏差 |
|---|---|---|
| P1 | **部分成立（数字有误）** | "无 `[build-system]` / 无 `[tool.setuptools]`" 属实，`pip install .` 必然触发扁平布局多包报错。**但"七个顶级包"是错的**：① `frames/` 目录在基线全树**根本不存在**（grep 只在 `main.py:399-412` 的局部变量命中）；② `logs/`、`backups/` 被 gitignore 排除；③ 带 `__init__.py` 的顶级目录只有 `core/ gui/ tests/` 三个。真实口径是 2~3 个——**照样 >1，所以结论不变**，但支撑它的那条"实证输出"是作者本机工作区（有开发残留目录）的产物，不是 fresh clone 的场景 |
| P2 | **成立**（路径并无问题） | 三个断裂点属实：`build.bat:21` 确为 `py -m nuitka`、pyproject 无 build 依赖组、README 教 `uv sync`、`:40` 确有 `--assume-yes-for-downloads`。**补充一点：`tools/build.bat` 这个路径是对的**——`bc22412`（18:27）已做 `build.bat → tools/build.bat` 的 git mv，而 PORTABILITY_REVIEW 写于 21:28，此时该路径完全正确 |
| P3 | **成立（CRLF 部分多虑）** | BOM 实证存在：`od -c -N8` → `357 273 277 @ e c h o`；`--jobs=8` 确在 `:38`。**但该文件已经是全 CRLF**（53 个 CRLF / 0 个裸 LF），报告把 CRLF 也列为待办是多虑；文件 7-8 行的注释自己写着"必须保持 CRLF…build_err.txt 的乱码根源"，说明作者已知，报告未提 |
| P4 | **成立（措辞夸大）** | 行号全中：`main.py:159` / `:186` / `:201` / `core/logger.py:21`。**但"三处都是启动即死"不准**：186 在 excepthook 内、201 在 except 块内，都不是启动必经路径，失败后果是丢了 traceback 而非"双击无反应"。真正致命的只有 `:159` 和 `logger.py:21`（后者是**模块级**执行，import 即 mkdir，比报告写的还早） |
| P5 | **成立（行号偏移 2）** | frozen 分支确为 `Path(sys.executable).parent`；`save_config` 两处 `logger.info` 静默吞异常属实。**mkdir 实际在 `:101-102`**，报告写 `:99-100` |
| P6 | **成立（本报告证据质量最高的一条）** | `core/config/base.py:171-185` 与报告逐行吻合：`os.makedirs` + `rename` 在同一个 try 里、失败被 `pass` 吞、随后无条件 `save_config()` 覆盖原文件。这条从头到尾没有一处夸大 |
| P7 | **成立** | `pyproject.toml:12` `mss>=9.0,<10.0`、`magnifier.py:49` `import mss.windows.gdi`、`uv.lock` 锁 9.0.2、README:35 `uv sync` —— 四处全对 |
| P8 | **成立（行号差 1）** | 无上界属实，但位置是第 **5** 行不是第 6 行 |
| P9 | 成立 | `win32_utils.py` 顶层三处 `ctypes.windll.*` |
| P10 | **部分成立（核心数字错了）** | **实测三份配置都是 77**（基线 committed / 当前 HEAD committed / 当前工作区），不是 79。310KB ✓、`my_beloved: "Xiaocheng"` ✓、`:37` `--include-data-dir=config=config` ✓。报告正文用"**实证**"二字下了错数字，直到篇末才悄悄改成 77——这一条的性质比 P1 严重，它动摇的是"实证"这个标签本身的可信度 |
| P11 | **成立（风险面被低估）** | 三个中文目录属实；但 `resources/` 下还有 **22 个含空格/逗号的英文目录**（如 `USMC, LAV-25`、`RGF AFU GFI INS IMF, MTLB PKT ZU-23`），在 shell / 打包脚本里的脆弱性不亚于中文名，报告只盯着中文 |
| P12 | 成立 | `main.py:64` 的 `_MEIPASS` 在 Nuitka 下永不命中 ✓（报告写"64-91"是整个函数体，分支实际是 64-67） |
| P13 | 成立，行号分毫不差 | `main_window.py:366/371`；另实证了"确无主动网络请求"：`grep urllib\|requests\|socket\|http.client` 在 core/gui/main.py 下 = 0 |
| P14 | 成立（干净项） | `logger.py:27` 可选开关 + 有 docstring |
| P15 | 成立（轻） | build.bat 无 arch 参数，README 无架构声明 |
| P16 | 成立 | `README.md:18` 实测为"Windows 10 2004 或更高" |
| P17 | 成立 | `build.bat:21` 用 `py` 启动器 |

## 1.4 规矩审计的判断质量

52 条规矩过堂、按 A/B/C/D 四分类处理，这套框架是**有序的判断输出**，不是流水账：

- **R23（测试红线 ≤30）判 D 退役：妥当。** 为守上限而被迫砍掉真正在防 bug 的断言（FIX_PLAN 里打算先删 `test_cleanup_isolation.py:98` 的顺序断言来"腾额度"）本身就是自残
- **R27/F2（换行符示例漂移）：判得准。** 实测 63 个 .py 里 CRLF 39 / LF 24，"以 config_manager.py 为唯一例外"的表述确实失真
- **G1（依赖变更实测纪律）：建议本身对，但来路写岔了。** 它表面是"改 pyproject 后要实测"，实质是"lock 锁了什么 ≠ 环境装了什么"——而这恰恰就是 S1 初版翻车的原因。应该把它写成 S1 教训的**直接产物**，而不是一条通用建议
- **F4（AGENTS.md 是无理由判决书）：建议加括号指针指向依据是正解。** 宪法要短是对的，但短到无法被审查时，它就变成了不可讨论之物

---

# 第二部分：修复对了吗

## 2.1 批次 1（`ac94329`）—— 技术质量最高，但把 S6 弄丢了

改到点子上的：

- **S2/M7 是本批最扎实的一处。** `_atomic_write` 纳入锁内、tmp 名带 `threading.get_ident()`、`finally` 清理残 tmp、`_save_token` 做 timer 身份比对——四层防御都在回答"两个线程如何不撞车"。`_do_deferred_save(token)` 在 token 不匹配时"不清引用但照常落盘"的取舍也是对的（脏数据必须写，否则用户改了的东西会丢）
- **S3 比计划做得更多。** 计划只说"`copied=[]` 在 try 之前初始化"，实际还在 copy 循环里加了**失败即回滚**，把"孤儿文件"从源头掐断——说明动手时想明白了：`copied` 只防 NameError，防不住半途失败
- **S5 处理干净。** 把 up/down 的 disconnect 从 `_init_engine`（对 None 空转）前移到 `_shutdown_engine`（置 None **之前**），同时保留 height tuner 的"先断再连"循环——因为 height tuner 常驻不重建，两条不同生命周期用不同处理是对的
- **M3 一处可能的疑问已排除。** commit 里没有 `core/overlay_base.py`，但该文件 `:14` 是 `from core.win32_utils import ... user32`——共享同一个 user32 对象，`win32_utils` 里设的 argtypes 对全进程序生效，**所以不是漏改**

**批次 1 唯一但严重的问题：S6 不见了。**

FIX_PLAN 批次 1 的十条覆盖 S2+M7 / S3a / S3b / S4 / S5 / S7 / M1 / M3 / M6 / M9。**S6（配置启用吉祥物时被 parent 到页面内部）既没进计划，也没进任何批次，CHANGE_LOG 和 HANDOVER 里也找不到"决定不修"的记录。** 现状原封不动：

```
gui/main_window.py:424   TAB_INFO: lambda: InfoTab(config=..., resources=...)   ← 仍无 parent
gui/tabs/info_tab.py:30  self.mascot_enable_check.setChecked(...)                ← __init__ 内同步触发
gui/tabs/info_tab.py:106 parent = self.window()                                  ← 仍取 tab 自身
```

一个自评为"严重"、且**我已经在基线上逐行复验成立**的诊断，就这样在从报告到计划的转写过程中被静默丢弃了。**这是本次复核发现的最严重的流程缺陷，比任何一条具体 bug 都严重**：写诊断的人的职责是让它进账本；进不了账本至少要留下"为什么不进"。连痕迹都不留，同样的 content loss 下次还会重演。

## 2.2 批次 2（`2d372de`）—— 方向正确，P5 只做了一半

- **P6 的三级降级写得漂亮**：rename 到 backups → 同目录改名 → 内容写成恢复副本（配置目录优先、%TEMP% 兜底）→ 全失败则**原地保留不覆盖**。每一步都写日志、`recovery_notices` 登记，`main.py:347-349` 在窗口显示后 800ms 弹一次 QMessageBox —— **接了线**，不是死代码
- **P4** 三处 try + %TEMP% 降级 + frozen 下 MessageBoxW 齐全
- **P1** 的 `[tool.setuptools] packages.find include=["core*","gui*"]` + `py-modules=["main"]` 是正解

三点可以更好：

1. **P5 只修了 config，没修 resources。** `_resolve_portable_config_dir()` 只决策 config 目录，`self.resources_dir = get_app_base_dir() / "resources"` **仍钉死在 exe 同级**（只把 mkdir 包了 try）。于是：安装到 Program Files 的标准用户 → config 乖乖降到 %APPDATA%，但 resources 仍在只读目录 → **导入 .gsv 载具（要往 resources 写图）必然失败**，而且是 `copy2` 抛异常被 `logger.exception` 吞掉，UI 上只会看到一句"图片复制失败"。报告 P5 原文是"config/resources 按绿色便携固定在 exe 同级"，落地只有一半
2. `mss>=10.0` **没有上界**。既然 9→10 的 breaking change 已经咬过一次（正是 S1 的由来），加个 `<11` 成本为零
3. `[tool.setuptools.packages.find]` 的注释里还留着从报告继承来的 `frames`——这个目录不存在，注释会把下一个人带偏

另外 P8 / P9 / P11–P13 / P15–P17 在 FIX_PLAN 里标为"留批次 4"，而批次 4 明写"随批次做，**不单独排期**"——这意味着它们既不在任何已完成批次里，也不在日程上，只在状态表里有记号。**这是"记录在案但实际失管"的典型形态**，和上面 S6 的丢失是同一种病：一个从没进过账本，一个进了账本但账本本身没有日程。

## 2.3 批次 3（`d0c6c9b`）—— 引入一个严重回归

大部分没问题：M4 的 BboxCache 加锁、M8 改成定向 `unhook`、M10 的条件构建、M12 的重命名分支重建、M13 的 suppress 包裹、M16 的 `destroyed` 兜底、M18 的 try/finally、M19 的 splitter 延时保存、M20 的引用计数进退出路径（`release()` 在 `:131-132` 夹到 0，**不会负计数**；`_stop()` 幂等）、M23 的 `TAB_CLEANUP_STEPS` 收敛——这些都是踏实的。

**但有一处必须立刻修：**

### 【严重回归】M17 的补偿把标定测距的电闸整条抹掉了

```python
# gui/main_window.py:697-706
tab.set_function_active(wheel.is_suspended)

def _on_distance_toggle(checked, w=tab, wh=wheel):
    if checked:
        w.set_function_active(wh.is_suspended)

# 先无条件断开旧连接再连（幂等收口，HANDOVER §十二）
try:
    tab.enable_check.toggled.disconnect()          # ← 问题在这一行
except TypeError:
    pass
tab.enable_check.toggled.connect(_on_distance_toggle)
```

问题在 `disconnect()` 的**无参形式**：PyQt 里它不是"断开某一个槽"，而是**清空该信号的全部连接**。而同一个信号上还挂着模块自己的电闸：

```python
# gui/tabs/distance_meter_tab.py:102
self.enable_check.toggled.connect(self._on_enable_toggle)
# → _on_module_toggle：写配置 / _init_engine() 或 _shutdown_engine() / 注册注销热键 / 禁用设置容器
```

我实测确认（offscreen 下两个槽连同一信号，执行一次无参 `disconnect()` 后再 emit，**两个槽都不再被调用**）。

**触发序列恰恰就是 M17 想修的那个场景：**

```
config 里启用了标定测距
  → _create_first_tab() 预创建 TAB_DISTANCE_METER（"四个进阶模块统一在此预创建"）
  → tab.__init__ 里连上 _on_enable_toggle
  → 约 100ms 后后台任务调 main.py:366 window.on_ammo_wheel_ready()
  → get_tab() 拿得到 tab（预创建已进 _tab_cache）
  → tab.enable_check.toggled.disconnect()   ⇒  _on_enable_toggle 被一并清除
```

后果：**启用勾选框变成死的**。用户点它既不写配置、也不起停引擎、也不注册热键。旧行为只是"暂离状态不同步"（轻微显示问题），新行为是"电闸整个失效"——为了补一个显示同步，赔进去一个开关。而 `tests/test_wave_c2_signals.py:45-64` 只断言"新连接生效"，从未断言"原连接还在"，所以 **91 passed 完全测不出这个回归**（我独立实跑也是 91 passed）。

改法是明摆着的：保留槽的引用做**定向** `disconnect(slot)`，或改用 `Qt.UniqueConnection`。顺带提醒：HANDOVER §十二的"先无条件断开再 connect"约定在**跨所有者信号**上不能直接套——那是给自己拥有的连接用的，这里的 `enable_check` 属于 tab，不属于 main_window。

### 另外三处中风险

- **M5 射表缓存**：key 是 profile name，失效判据是 `entry[0] is table` 的**对象同一性**，而 `set_firing_table` 自己完全不碰缓存。今天不出事是因为 UI 写回路径恰好每次新建顶层 dict——但同一函数的 `:689` 已经在就地改写 `branches[0]["samples"]`，属于**碰巧对，不是契约对**。哪天有人改成原地更新，表现是"用户改了射表数据但读数不更新且无任何报错"。建议改成显式版本号，或在 `set_firing_table` 里清缓存。附带：热路径只修了一半——`:1230-1231` 的 `is_firing_extrapolation` 没走缓存，鼠标级每帧仍在重建 profile
- **M23 只收敛了 3.5/4**：`tools/export_gui_facts.py:230` 只调了 `collect_tab_cleanup_steps(win)`，**漏了 `collect_window_cleanup_steps`** ⇒ `overlay.shutdown()` 不执行。而相关测试全用 stub window，没有一条锁住"四个调用方必须引用同一份 SSOT"，所以漏改在 CI 里不可见——这正是 M23 原本要防的病，在同一个地方又犯了一次
- **M2 的副作用**：Scanner 从"排空自退"改成"只由 request_stop 退出"，于是**任何创建却不配对 request_stop 的路径都会永久挂一根等条件变量的线程**。常规路径覆盖了，上面 export 的漏改恰好把这个口子留在开着的状态
- 附带一条小的：M14 只做了防抖，**计划里承诺的增量过滤没做**（仍是全量重建）。这不构成 bug，但计划的缩水应该在账本上写清楚

## 2.4 一处没进账本却悄悄修好了的

`tools/export_gui_facts.py` 的 `ROOT` 现在是 `Path(__file__).resolve().parent.parent`（即 M24）——**这条没在任何批次的记录里被提及，但确实被修了**。好消息是做事的人动手时把看到的问题顺手收拾了；坏消息是它也没进账本，将来回溯时会以为没人管过这件事。

---

# 三、结论

**step5 的诊断能力：强。** 24 项中级里 23 项按行号逐条命中，机制描述到位——尤其是识别出"Qt 信号持有引用导致旧对象不释放"这条主线（S5 / S7 / M16 / M20 其实是同一个病在不同位置的表现）。真正浮夸的只有 P1 的七包数、P10 的载具数（77 vs 79），以及轻级里 4 条应该撤回的假发现。

**step5 的计划纪律：有明显裂缝。** 三种形态反复出现：

1. **诊断 → 计划 的转写丢项**：S6 最典型，自评"严重"却在两个环节同时消失，且没有"为何不修"的记录
2. **计划 → 交付 的半交付**：M14 只做防抖不做增量；P5 只救 config 不救 resources
3. **记账了但没排期**：P8 / P9 / P11–P13 / P15–P17 标"留批次 4"，而批次 4 明写"不单独排期"

**落地代码的工程质量：批次 1 ≥ 批次 2 > 批次 3。** 批次 3 在 15 项里交出 1 个严重回归，而测试套件 91 passed 毫发无损地掩盖了它——这本身值得反省：当前这批测试大多在锁"新连接生效 / 新方法存在"，很少锁"原有的东西还在"。

## 建议的处置顺序

| 优先级 | 事项 | 理由 |
|---|---|---|
| **P0** | 把 `main_window.py:701` 的无参 `disconnect()` 改成定向 `disconnect(slot)` 或 `Qt.UniqueConnection` | 功能性回归，配置启用标定测距的用户每次启动都中 |
| **P0** | 补一条测试：断言连接 `_on_distance_toggle` 之后 `_on_enable_toggle` 仍然存在 | 没有它，同类回归还会再发生 |
| **P1** | S6 重新入账：要么修（推迟到入栈后，如 `QTimer.singleShot(0, self._create_mascot)`），要么在 FIX_PLAN / HANDOVER 写明"决定不修 + 理由" | 诊断不能无缘无故消失 |
| **P1** | 补 `export_gui_facts.py:230` 的 `collect_window_cleanup_steps` | M23 的收敛留了缺口，且该缺口正好是 M2 改动的泄漏面 |
| **P1** | P5 的 resources 侧：让 `resources_dir` 跟随数据目录决策，或至少在只读时明确提示 | 否则 Program Files 下导入 .gsv 是静默失败 |
| **P2** | M5 缓存改显式版本号 / `set_firing_table` 里清缓存；`is_firing_extrapolation` 也走缓存 | 现在是"靠调用方恰好生成新 dict 才有效" |
| **P2** | `mss>=10.0` 补 `<11` | 同一个坑不要踩两次 |
| **P2** | 把"P8 / P9 / P11–P13 / P15–P17 + 已顺手修但没入账的 M24"建成一个真实存在的批次 4，或明确标 won't-fix | 消除"记账了但失管"的状态 |
| **P3** | 轻级那 4 条假发现在 CODE_REVIEW 里划掉并注明 | 避免后人按图索骥去删活代码（`VehicleFilterWidget` 尤其危险，它正在被用） |

---

*本次复核未修改任何业务代码；`docs/reviews/` 下的三份原始报告与 FIX_PLAN 未被改动，仅新增本文件。*
