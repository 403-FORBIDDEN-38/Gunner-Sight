# GunnerSight 全面代码审查报告

- 审查日期：2026-10-24
- 范围：`main.py`、`core/`（含 `core/config/`）、`gui/`（含 10 个 tab 与 mascot）、`tests/`、`tools/`（含 `tools/build.bat`），约 450KB 源码
- 方法：三轮并行通读（引擎层 / GUI 层 / 启动·测试·工具链）+ 对严重级问题逐条实证复核（下载 mss 9.0.2 wheel 核对包结构、按行号回读源码）
- 性质：**只读审查，未改动任何代码**

严重程度定义：

| 级别 | 含义 |
| --- | --- |
| 严重 | 已确认会致功能失效、数据损坏、任意文件写入或资源泄漏 |
| 中 | 特定条件下出错，或明显坏味道（有具体触发路径） |
| 轻 | 可读性 / 一致性 / 死代码，不影响正确性 |
| 建议 | 可选优化，改不改取决于后续规划 |

---

## 一、严重（7 项，均已实证）

### S1. ~~放大镜抓屏线程启动即死，功能完全静默失效~~ 【2026-10-24 复审后修正：见文末附录 B】

**修正后定性**：`core/magnifier.py:49` 的 `import mss.windows.gdi` 只在 **mss ≥ 10.0** 时可用；而 `pyproject.toml` 声明 `mss>=9.0,<10.0`、`uv.lock` 锁 9.0.2——**代码实际依赖与依赖声明直接矛盾**。

- 在本机实际运行环境（系统 Python313 site-packages，mss **10.2.0**）与 dist 成品 exe（含 mss 10.x 独有符号 `MSSImplGdi`）中，import 成功、patch 生效，**放大镜功能可用**。
- 在任何按 `uv.lock` / `pyproject.toml` 声明全新同步的环境（mss 9.0.2，单文件 `mss/windows.py`，无 gdi 子模块）中，import 必抛 `ModuleNotFoundError`，功能失效。
- 版本无关写法也不存在“简单改法”：9.0.2 的 `CAPTUREBLT` 在 `mss/windows.py`（模块级），10.x 的在 `mss/windows/gdi.py`（`mss.windows` 包 `__init__` 不暴露它），需 try/except 或 getattr 兼容。
- 修复方向（二选一，均未实施）：① `pyproject.toml` 改 `mss>=10.0` 并重锁（代码已实质依赖 10.x 的模块结构）；② 写版本无关导入。
- 附带问题依旧成立：`run()` 无异常保护（M9），mss 9.x 环境下 grab 线程异常即死且 `_cam` 不 close。

---

### S2. 配置保存：原子写在锁外执行，两条保存路径可并发损坏 config.json

`core/config/base.py:233-256`、`276-287`

```python
def save_config(self) -> bool:
    with self._save_lock:
        ...
        data = self._dump_config()
    try:
        self._atomic_write(data)   # ← 锁已释放；tmp 文件名固定 config.json.tmp
```

`save_config()`（主线程立即保存，如 `vehicle_io.py:329` 导入载具后）与 `_do_deferred_save`（Timer 线程，500ms 防抖）都只把序列化放进了 `_save_lock`，`_atomic_write` 的「写固定 tmp → os.replace」在锁外。两者撞车时两个线程交替写同一 tmp 文件，最终 `os.replace` 上去的是交错内容——**config.json 损坏**（虽有骨架回退和损坏备份兜底，但用户本次的全部配置改动丢失）。

**建议**：把 `_atomic_write` 纳入锁内；或每线程生成唯一 tmp 名（`config.json.<pid>.<thread>.tmp`）。

---

### S3. .gsv 导入失败路径引用未绑定变量，且导入无路径穿越校验

`core/vehicle_io.py:305-317`

```python
try:
    path_mapping, copied = _process_image_dirs(...)
except Exception as e:
    # 图片复制失败 → 清理已复制的，中止
    for dst in copied:      # ← copied 从未赋值 → NameError
```

两个问题叠在一处：

1. **NameError**：`_process_image_dirs` 抛异常时元组解包未完成，`copied` 未绑定，except 块第一行就抛 NameError——原始异常被吞、半途复制的文件全部跳过成为孤儿、调用方收到无意义的 NameError。修复：`copied = []` 在 try 之前初始化。
2. **任意文件写**：`vehicle_io.py:188-243` 中 `manifest["images"]` 的相对路径（如 `../../evil.png`）经 `resources_dir / new_dir_rel` 后直接 `mkdir(parents=True)` + `copy2`，全程无 `..` / 绝对路径检查。`sanitize_filename` 只用于导出的 .gsv 文件名，没用于导入路径。恶意/损坏的分享包可在 resources 外任意位置落盘。

**建议**：先初始化 `copied = []`；对每个条目 resolve 后断言仍在 `resources_dir` 之内。

---

### S4. 资源库页「复制路径」菜单必崩：NameError

`gui/tabs/resource_tab.py:690-694`

```python
elif item and chosen == action_copy:
    node_data = item.data(0, Qt.UserRole)
    rel_path = node_data[1]
    from PyQt5.QtWidgets import QApplication
    QApplication.clipboard().setText(str(full_path))   # ← full_path 未定义
```

`full_path` 只在 `action_open`（687 行）和 `action_delete`（698 行）分支里赋值。用户每次点「复制路径」必抛 `NameError`（Qt 打印堆栈、菜单无响应）。`rel_path` 取了不用，说明该分支是从相邻分支复制漏改。

**建议**：补 `full_path = Path(self.resources.resources_dir) / rel_path`，删掉未用的 `rel_path`。

---

### S5. 角度仪微调热键：禁用→启用后旧 _FineTuner 连接不断开，按键注入翻倍

`gui/tabs/angle_meter_tab.py:713-731`（断开循环）、`773-795`（shutdown）、`759-768`（重连）

```python
# _shutdown_engine：先置 None
if self._up_tuner:
    safe_call("up_tuner.stop", self._up_tuner.stop)
    self._up_tuner = None
...
# _init_engine 的"无条件断开旧连接"：
(self.hotkey.angle_meter_up_pressed, getattr(self._up_tuner, 'on_pressed', None)),  # ← None → continue
```

`_shutdown_engine` 把 `_up_tuner/_down_tuner` 置 None 后，`_init_engine` 的断开循环对它们永远是空操作。旧 tuner 以 tab 为父对象不会被销毁，对 `angle_meter_up_pressed/released` 的连接永久存活；再次启用时新 tuner 又连一遍——**两套 tuner 同时响应每次按键，鼠标注入翻倍**，且每轮开关泄漏一个带 2 个 QTimer 的 QObject。高度差 tuner 因 shutdown 不置 None 反而正确——同一份代码里三种处理方式，恰好反的那两个是坏的。

这正是 HANDOVER §十二「重建引擎后热键触发两次」警告的模式，只是发生在自己这一侧。

**建议**：断开循环引用**旧 tuner 对象的实际槽**（在置 None 之前先断开），或让 tuner 自己在 `stop()` 里断开自己的连接。

---

### S6. 配置启用吉祥物时，mascot 被 parent 到页面内部，常驻设计被破坏

`gui/tabs/info_tab.py:27-30`、`98-112`

```python
# __init__ 内同步触发：
self.mascot_enable_check.setChecked(self.config.is_mascot_enabled())
# → _create_mascot：
parent = self.window()   # ← tab 还没 insertWidget，window() 返回 tab 自身
self._mascot = MascotWidget(res_dir, parent=parent)
```

`_ensure_tab` 先无父构造 tab 再 `insertWidget`。若配置里 mascot 已启用，`setChecked(True)` 在 `__init__` 内同步触发创建，此时 `self.window()` 是 **InfoTab 自身**（无父即顶层窗口）。后果：mascot 成为页面子控件——切 tab 时随页面隐藏（桌宠「常驻」设计失效）、被页面边界裁剪、拖动钳制在页面内；且创建后 `_mascot is not None`，`showEvent` 不会纠正。用户手动勾选路径（window() 已有效）反而正常，所以 bug 只潜伏在「开配置启动」路径。

**建议**：把 `_create_mascot` 推迟到 tab 入栈后（如 `showEvent` 首次或 `QTimer.singleShot(0, ...)`），创建前断言 `self.window() is not self`。

---

### S7. OverlayRenderer 初始化即连 5 个 StateMachine 信号，无断开路径

`core/overlay.py:502-513`（构造时 connect 5 个信号，全类无一处 disconnect）

重复构造（测试、未来多窗口）时信号叠加，回调触发多次。当前生产路径只构造一次故未爆发，属结构性隐患。

**建议**：加 `shutdown()` 集中断开；或在 connect 前先无条件 disconnect（幂等收口，与项目「先断再连」约定一致）。

---

## 二、中（21 项）

### core 引擎层

| # | 位置 | 问题 |
| --- | --- | --- |
| M1 | `angle_meter.py:237-243` | `refresh_min_max` 文档说「仅 IDLE 时更新」，实际无条件覆写 `current_angle`；切换精度方案时调用方未先 stop tracker，ACTIVE 态会把显示角度强行拉回最低角，而累积 delta 未重置，下次 update 又跳回去——内外状态不一致 |
| M2 | `bbox_crop.py:263-282` | Scanner 退出/提交竞态：任务入队落在「队列已判空、线程未结束」窗口即成孤儿；`overlay.py:207-209` 的 `_pending_scans` 守卫使该路径**本次会话再也加载不出图**（切弹种准星不更新） |
| M3 | `win32_utils.py:270-291`、`overlay_base.py:48-62` | `GetWindowLongW/SetWindowLongW` 未设 argtypes/restype，64 位句柄按 32 位传参有截断/OverflowError 风险。同仓 `mouse_hook.py:24-51` 给全部 API 设了严格签名，唯独最核心的窗口样式 API 漏设（`angle_meter.py:61-88` RawInput 两处同类） |
| M4 | `bbox_crop.py:145-241` | `BboxCache` 无锁跨线程访问：主线程 `get()/has()`、扫描线程 `get()/set()/save()` 并发，`json.dump` 迭代期 dict 增删可抛 RuntimeError（目前被 scanner 的 except 吞掉） |
| M5 | `firing_table.py:164-171`、`config/angle_meter.py:117-130` | 射表查询挂在 `angle_changed` 上（鼠标每次移动触发），每次角度更新重建 2 次完整 `BallisticProfile`（解析+排序+PCHIP 求导），且 `angle_meter.py:126` 在函数体内 `import`。应按「profile 名+版本」缓存 |
| M6 | `ammo_wheel_selector.py:247-251` | `stop()` 语义错误：只 release 钩子引用（HotkeyManager 也持一份，不会真停）、隐藏窗口，`_enabled` 仍为 True、信号仍连着——stop 后滚轮照样唤出 FullOverlay。当前无调用方，接关闭流程即踩 |
| M7 | `config/base.py:276-287` | `_do_deferred_save` 无条件 `self._save_timer = None`：Timer A 阻塞在锁上时主线程取消 A（无效）并创建 B，A 获锁后把 B 的引用抹掉——B 无法取消、到期重复保存，与 S2 叠加提高损坏概率。修法：`_do_deferred_save(self, timer)`，仅当 `self._save_timer is timer` 时清空 |
| M8 | `hotkey_manager.py:232-239` | `reload_hotkeys()` 每次全量重注册都 `keyboard.unhook_all()`——局部逻辑挥舞全局公共服务。当前 GUI 不用 keyboard 库暂无损害，未来任何模块用都会被静默杀。应 `keyboard.unhook(self._keyboard_global_hook)` |
| M9 | `magnifier.py:47-79` | `_GrabWorker.run()` 无异常保护：`mss.MSS()` 失败、`grab()` 抛 `ScreenShotError`、QImage 构造失败都会直接终止线程且 `self._cam` 永不 close（GDI DC/位图泄漏，CHANGE_LOG 自称「泄漏代价最高」的正是它） |
| M10 | `overlay.py:212-241` | UI 层全屏整图（2K 载具/弹种图）的扫描结果也被 `QPixmap.fromImage` 塞进 crosshair 缓存（上限 50），白白 GPU 上传、挤占准星缓存。应仅对 `path == self._crosshair_path` 构建 pixmap |
| M11 | `mouse_hook.py:143-161` | `_stop()` 在 `_thread_id` 赋值前被调用时：`_running=False` 唤醒不了阻塞的 `GetMessageW`、WM_QUIT 也没发出，钩子线程悬挂到进程退出，`join(0.5)` 超时且无警告日志 |

### GUI 层

| # | 位置 | 问题 |
| --- | --- | --- |
| M12 | `vehicle_config_tab.py:542-554` | 「重命名载具」按取消 / 输入空名 / 输入同名，全部落入 else 弹「已存在」。同页 `_on_rename_tag`、`_on_rename_ammo` 都是静默 return，本处是唯一误报分支 |
| M13 | `vehicle_config_tab.py:723-727` | 倍率列表选中恢复用裸 `setCurrentRow`，未包 `_suppress_mag_writeback`（vehicle/ammo 两列表都包了）。目前仅靠「idx 相等」短路兜底，相等判断一旦失效就形成 `state → 刷新 → state` 回写环路。HANDOVER §8.4 自己写明「三个列表语义不同」，但「阻断回写」这一点上应该一致 |
| M14 | `overview_tab.py:114`、`vehicle_config_tab.py:503`、`resource_tab.py:397` 等 5 处 | 搜索框 `textChanged → 全量 clear()+重建`：每个按键重建全部 item 控件；资源页每次按键还叠加引用索引重建 + 磁盘列举 + 递归聚合。载具/预设上百条时输入明显卡顿。建议 150-200ms 防抖 + 增量过滤（只 setHidden 不重建） |
| M15 | `adapt_tab.py:270-273` | tab 反向读 `window._current_theme`、调 `window._apply_theme()` 私有 API，违反「跨页走信号」约定。应在 MainWindow 上开公共信号 |
| M16 | `hotkey_tab.py:85-102` + `hotkey_widgets.py:115-124` | 热键页 refresh 时 `deleteLater` 掉正在捕获的 `HotkeyLineEdit`——Qt 自动断信号，但 `release()` 永不调用，全局低级鼠标钩子引用计数泄漏、钩子常驻。HotkeyLineEdit 没有 closeEvent/destroyed 兜底释放路径 |
| M17 | `main_window.py:654-663` | `ammo_wheel` 由后台任务创建；测距 tab 若先实例化，`wheel is None` 时初始同步和 `toggled` 连接都不建立，之后无补偿路径——暂离中测距不激活，直到用户手动切一次启用框 |
| M18 | `angle_meter_tab.py:852-877` | `_loading = True` 无 try/finally：`_load_firing_table` 中途任何异常 → `_loading` 永久 True → 此后所有参数修改被静默丢弃。正是 `widgets.py:416 set_silent` 文档注释警示的「控件永久静默」模式 |
| M19 | `vehicle_config_tab.py:309`、`resource_tab.py:170` | `splitterMoved` 逐像素触发 config 写入（虽有 500ms 防抖也是高频入队）。应连 `splitterHandle` 的 release 事件或用 500ms 定时器只在拖动结束保存 |

### 启动 / 测试 / 工具链

| # | 位置 | 问题 |
| --- | --- | --- |
| M20 | `main.py:326/414-429` | `ammo_wheel.start()` 的 `MouseHook.acquire()` 引用计数退出时永不释放：closeEvent 只 `hotkey.shutdown()`，`_cleanup` 只清放大镜 tab——钩子线程靠 `daemon=True` 兜底跑到进程死亡。全项目只有测试 fixture 调过 `ammo_wheel.stop()` |
| M21 | `main.py:156-159` | 启动日志 `open()` 裸调无保护，且早于 `sys.excepthook` 生效。装到只读目录首次启动即 OSError 裸崩，crash_log 也来不及落盘 |
| M22 | `main.py:28-48` | `_LibpngFilter` 在设计上不可能生效：libpng 是 C 层 `fprintf(fd 2)`，替换 Python 的 `sys.stderr` 拦不住它。一个自述功能失效的机制会误导后人以为噪音已治理 |
| M23 | 跨 4 处 | 「逐项隔离清理」契约有四份实现且方法名清单互不一致：`main.py:422`（只放大镜）、`main_window.py` closeEvent、`conftest.py:55-63`、`export_gui_facts.py:225-236`（5 个方法名还含私有名）。清单漂移 = 静默资源泄漏，且无测试锁定四者一致。应收敛成一份共享清单（如 `TABS_WITH_SHUTDOWN = {...}`） |
| M24 | `export_gui_facts.py:14-16` | `ROOT = Path(".")` 依赖 CWD，同仓库另外四个工具都用 `Path(__file__).parent.parent`。从别的目录运行会导入错项目、GUI_INVENTORY 写错位置 |

---

## 三、轻（可读性 / 一致性 / 死代码，选摘）

**死代码（均无调用方）**

- `gui/widgets.py`：`RegionSelector`、`PointPicker`、`CrosshairPreviewWidget`、`make_int_spin`、`VehicleFilterWidget` 四个未用方法
- `gui/tabs/vehicle_config_tab.py:788-815` `_update_mag_item_text`
- `gui/mascot/`：`chat_bubble.set_persistent/set_volume`、`sound_player.set_volume`
- `gui/tabs/squad_macro_tab.py:135-141`：`showEvent` 整段死分支（`_data_loaded` 已在 `__init__` 置 True）
- `core/hotkey_manager.py:158/637`：角度仪 pause 热键/信号未注册、无控件、无调用方
- `core/distance_meter.py:262-284`：`is_modifier_pressed` 及其读取的 `global_combo` 配置全库无人写入
- `tools/export_gui_facts.py:25`：`SKIP_TYPES` 定义后从未使用（且 tools/ 不在 audit_docs 的 ruff 门禁范围内，现有机制发现不了）

**命名 / 一致性**

- `distance_meter_tab.py:86-94`：`offset_x/offset_y` 无 `_spin` 后缀（其他页一律 `*_spin`）；启用槽三种命名 `_on_enable` / `_on_enable_toggle` / `_on_enable_changed`
- `angle_meter_tab.py:1063/1139/1232`：用字符串 `"ACTIVE"/"PAUSED"` 比较，别处用 `STATE_ACTIVE` 常量
- `main.py:158/184/196`：`frozen ? exe 目录 : 脚本目录` 判断重复三次，三个变量名（`_log_dir`/`_ex_log_dir`/`log_dir`），而 `get_app_base_dir()` 已导入未复用
- `core/squad_macro.py:14`：`_user32 = user32` 冗余别名
- `core/overlay.py:77-82`：应用基目录逻辑第三次重复实现（另两处：`_resources_dir()` 静态方法、`config/base.py get_app_base_dir()`）

**魔法数字 / 硬编码散落**

- `chat_bubble.py:114/303` 音量 `10`，与 `SoundPlayer(volume=0.1125)`、`set_volume` 三套音量源互不一致
- `adapt_tab.py:174` 档位阈值 `1200/1700`、`resource_tab.py:454` `max_dim=4096`、`423` 缓存上限 `20`、`angle_meter_tab.py:248-259` 的 `1.0/1.5` 秒阈值均内联
- `"收藏"` 常量两份定义、`"全部标签"/"__all__"` 三处重复
- `hotkey_widgets.py`：`HotkeyPairWidget` 与 `PauseHotkeyWidget` 是同一套「标签+两键框+两触发下拉」的两份拷贝，连 trigger 映射字典都重复两遍

**性能细节**

- `angle_meter_tab.py:110-151`：`AngleOverlay.paintEvent` 每次重绘 import + 新建 4 个 QFont（60fps 路径），而文件顶部已有 `FONT_CONSOLAS_*` 常量范式可循
- `bbox_crop.py:25-60`：`find_opaque_bbox` 纯 Python 逐像素扫描，2K 整图每张约 370 万次判断；可用 numpy 或行级 bytes 技巧优化
- `ammo_wheel_selector.py:366-375`：每次滚轮事件全量重建 FullOverlay 标签列表，已有增量接口 `update_highlight` 未用

**其他**

- `adapt_tab.py:254-257`：内联 `setStyleSheet` 硬编码 `#555`，不随主题/`core/colors.py` 走
- `hotkey_widgets.py:210/216/275-284`：跨类写 `HotkeyLineEdit._key` 私有属性，应加公开 `set_key()`
- `resource_tab.py:517/541/570/660/710`：直接访问 `ResourceManager.resources_dir` 和 `_invalidate_resources_cache()` 私有成员；`_current_pixmap/_scaled_cache` 未在 `__init__` 初始化，靠 `hasattr` 防御
- `main.py:160-180`：`_Tee` docstring 声称「只有换行时才 flush」，实现每次 write 都 flush（文档与实现相反）
- `main.py:211-212`：`AA_EnableHighDpiScaling` 等在 Qt5.14+ 已默认开启，可删或注释原因
- `tools/audit_manual.py:58-61`：`--verbose` 是无操作标志（无条件打印全部），docstring 声称它控制输出
- `tools/audit_docs.py:83`：注释「< 20 个 test function」与检查本体 ≤30、AGENTS.md 已调 30 不一致；63 行用中文注释串作存在性判据，注释一改（行为没变）对账即失败
- `ui_access_test.py:122/134` 两处裸 `except:` 吞 KeyboardInterrupt/SystemExit；`check_mpo_support.py:57` `CreateDXGIFactory1` 未设 argtypes
- `docs/HANDOVER.md:86` 称出厂值取自「发布包的 config.json」，实现实际读 `git HEAD:config/config.json`——文档口径漂移
- `tests/` 私有 API 断言普遍（`win._tab_cache`、`_tab_factories` 等），按 AGENTS §4 自己的标准已越界；`test_cleanup_isolation.py:79-100` 断言 `raw.close` 必须是第一个——纯调用顺序断言，重排即误报
- `conftest.py:55-63`：teardown 的 `except Exception: pass` 静默吞掉清理失败，跨用例泄漏被永久隐藏

---

## 四、建议（结构级，按收益排序）

1. **收口清理契约**：把「哪些 tab 有 shutdown/cleanup、调用哪些方法」收敛成一处共享清单，closeEvent / main.py `_cleanup` / conftest / export_gui_facts 全部引用它。这是当前唯一「清单漂移 = 静默泄漏」的多实现点。
2. **main.py 补契约测试**：启动编排是全项目最脆弱却零覆盖的文件。至少补一条「closeEvent 未执行时 aboutToQuit 兜底仍生效（含 ammo_wheel.stop()）」的测试，风格仿 `test_cleanup_isolation.py`。
3. **保存路径统一加锁**：S2 + M7 一起修——`_atomic_write` 入锁、tmp 名带线程标识、`_do_deferred_save(timer)` 比对后清引用。
4. **信号连接注册表化**：`main_window._connect_tab_signals` 的 60 行 if-elif 树改为 `{tab_index: connect_fn}`，「tags_changed 补连」收敛成一个广播 helper——每加 tab 改一棵树的模式迟早漏连。
5. **搜索防抖 + 增量过滤**：五个页面的搜索框统一走 150-200ms 防抖；过滤只 `setHidden()` 不重建控件（资源页的磁盘列举移出过滤路径）。
6. **ctypes 签名统一门禁**：把「所有 Win32 API 必须设 argtypes/restype」写成 audit_docs 的一条检查（已有 mouse_hook 的规范写法作基准）。
7. **线程内 API 调用统一入口**：`magnifier.py:174/192` 的 `ctypes.windll.user32` 直调改走 `win32_utils.py`，与其 docstring 声称的「统一入口」对齐。
8. **tools 五个脚本加 `main()` 守卫**：当前 import 即执行 + `sys.exit`，无法被复用或单测；若要进 CI 这是前置条件。

---

## 五、总体评价

这个项目的契约意识、防御性注释和文档纪律罕见地强（懒加载/电闸/SSOT/清理隔离都有明确约定且大体被执行）。本轮 52 项发现里，真正危险的是**「坏在静默里」的几处**：放大镜 import 错误导致功能完全失效而无人报错（S1）、配置保存并发损坏（S2）、热键/钩子引用计数在退出与重建路径上泄漏（S5/M6/M16/M20）。建议修复顺序（2026-10-24 复审后更新，S1 已修正为「依赖声明矛盾」而非功能失效）：S4 → S5 → S2/M7 → S3 → 依赖约束（原 S1）→ 其余按 M 级推进。

---

## 附录 B：S1 结论的复审与修正（2026-10-24 晚）

用户对初版报告 S1「放大镜功能完全静默失效」提出异议，主张其环境可用。逐项实证后**用户的质疑成立**，S1 定性错误，已在第一节修订。证据链：

| 待证事实 | 核实方法与结果 |
| --- | --- |
| mss 10.2.0 是否有 `mss/windows/gdi.py` | 下载 10.2.0 wheel：**有**，含模块级 `CAPTUREBLT = 0x40000000` |
| 10.2.0 上 `_gdi.CAPTUREBLT = 0` 是否生效 | `mss/windows/__init__.py` 以 `from mss.windows.gdi import MSSImplGdi` 选后端，gdi.py 内 BitBlt 引用**本模块** CAPTUREBLT 全局 → 运行时 patch 生效 |
| 本机实际运行环境装的 mss 版本 | 系统 Python313（`py` 启动器默认指向）site-packages：**10.2.0** |
| 用户是否走 uv.lock 工作流 | **否**：uv 不在 PATH、项目无 .venv，uv.lock 从未真正同步过 |
| dist 成品 exe 打包的 mss 版本 | exe 内含 mss 10.x 独有符号 `MSSImplGdi` 与 `mss.windows.gdi` → **10.x**；tools/build.bat 用 `py -m nuitka`，用的就是系统 3.13 |
| 9.0.2 的结构 | 单文件 `mss/windows.py`（无 gdi 子模块），`CAPTUREBLT` 是其模块级常量 |

**初版报告的三处缺陷**：

1. **证据缺口**：只核对了 uv.lock（解析 9.0.2）就认定运行时是 9.0.2，没有检查实际为 main.py 提供依赖的解释器装了什么。「lock 锁了什么」≠「环境装了什么」。
2. **逻辑跳跃**：从「pyproject 声明 <10.0」直接推出「用户环境必为 9.0.2 故失效」，中间缺失「用户用什么解释器、装了什么版本」这一环。
3. **定性错误**：把「代码与依赖声明矛盾」直接判定为「功能失效」。实际是**环境依赖型脆弱**：当前环境与打包产物都带 10.x，功能可用；按 lock 全新同步的环境才会中招。

**修正后结论**：放大镜功能在当前用户环境**可用**，S1 降级为「中」：`import mss.windows.gdi` 实际要求 mss≥10.0，与 `pyproject` 的 `mss>=9.0,<10.0` 及 uv.lock 的 9.0.2 矛盾。修复方向二选一（均未实施）：把依赖约束改为 `mss>=10.0` 并重锁；或写 try/except 版本无关导入（注意两个版本的 CAPTUREBLT 分居 `mss/windows.py` 与 `mss/windows/gdi.py`，`import mss.windows as _gdi` 并不能两版本通吃）。另建议核查运行环境与 lock 的一致性——当前「跑 10.2.0、锁 9.0.2」的脱节状态本身就是风险。M9（run() 无异常保护）与 mss 版本无关，依然成立。
