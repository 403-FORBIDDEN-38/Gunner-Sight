# GunnerSight 交接文档

> **读者**：第一次拿到这个项目的人 / agent。目标：读完之后能独立改代码。
> **规矩**（怎么做才是对的、做错会怎样）在 `docs/RULES.md`；这份文件只讲
> **这个项目长什么样、为什么这么设计**。
> 只写 "是什么" 和 "为什么"：**不写故事、不记战绩、不写"某批次已完成"**。
> 最后复核：2026-10-25 · 版本 `V0.0140300184`
> 变更历史见 `docs/CHANGE_LOG.md`（按时间线）；本文件只写当前状态。

---

## 一、一分钟认识它

给游戏 **Squad** 用的屏幕准星辅助工具（PyQt5）。**不读游戏内存、不改游戏文件**——它的全部手段是：透明置顶窗口 + 图片叠加 + 全局热键 + Raw Input 读鼠标增量。

* 跑起来：`py main.py`（不需要管理员权限）

* 打包：`tools/build.bat` → `dist/main.dist/GUNNER SIGHT.exe`（见第十节）

* 源码 / 桌面版是**两份独立目录**（见第十节），改完源码不重打包的话桌面版不会变

---

## 一・五、五份文档各管什么

| 文件 | 读者 | 内容 |
| --- | --- | --- |
| `README.md` | 路人 / 下载页 | 是什么、怎么装、有什么限制。GitHub 门面，用常规 Markdown 排版 |
| `USER_GUIDE.md` | 使用者 | 完整操作手册。按**任务**组织，5 章 + 附录 |
| `docs/RULES.md` | 改代码的人 / agent | **未来**：规矩。该怎么做、做错会怎样，含坑速查与"别去修的东西"。判据的唯一来源 |
| `docs/HANDOVER.md` | 接手的 agent | **现状**：长什么样、为什么这么设计。本文件 |
| `docs/CHANGE_LOG.md` | 接手的 agent | **过去**：时间线，含回退过的方向（避免重走死路） |

三份 agent 文档按**时间性**分工，一条信息只能有一个家：
**判据进 RULES、事实进 HANDOVER、经过进 LOG。** 判据细则写在 `docs/RULES.md` §10。

其余项目文档已归类到 `docs/`。**审查报告不留在仓库里**：2026-10-24 那一批审查、修复计划、
交叉复核（共 11 份）已经归档删除，判据已提炼进 RULES、现状进本文件、经过进 CHANGE_LOG。
需要看原文用 `git log --diff-filter=D -- docs/reviews/` 找，再从历史里取。

**`USER_GUIDE.md` 的写法硬规矩在 `docs/RULES.md` §11.1**——零 markdown 强调符号，
结构只靠编号 / 缩进 / 全角对齐 / 行首标签词。

**`tools/audit_manual.py` 是手册的机械体检**（2026-10-18 加）：**只报告，不裁决**。

* 判据覆盖：每个操作小节（1-x / 2-x / 3-x / 4-x）必须带 `判据：`/`注意：`/`失败排除`/`状态收尾`
  之一，缺了退出码为 1。0-x（边界）与 5-x（整节就是失败清单）不套这个标准
* 强断言清单：列出所有 `不会 / 一定 / 无法 / 绝不` 句子，**供人核边界，脚本不判对错**
* 数字清单：列出所有带单位的数字，供人和代码 / 出厂配置对账

**为什么后两项只列不判**：写在文档里的标准会和手册一起漂移，写成可执行检查它自己会报错；
但"这句断言有没有依据"必须人判断，所以不让它影响退出码。

**手册的内容口径、断言的证据边界、事实底稿的取用规则在 `docs/RULES.md` §11.2~§11.4**。
（写法硬规矩、术语一致性、"追到调用点"的六处实证都在那里。）

本文件只声明一个事实：手册的**事实底稿**由 `tools/export_gui_facts.py` 生成到
`build/GUI_INVENTORY.md`（`build/` 是 gitignore 的构建产物目录），**是生成物、不入库**。

## 二、启动链路（读懂这条链就看懂了 60%）

`main.py` 的 `main()` → `_main()`，顺序**不能随便动**：

```
main()
 ├─ stdout/stderr 接到 startup_log.txt；sys.excepthook 接到 crash_log.txt
 │    （必须在最外层：_main 里任何异常都要能落盘）
 └─ _main()
     1. QApplication.setAttribute(AA_EnableHighDpiScaling / AA_UseHighDpiPixmaps)
     2. QApplication()  ← 之后才允许建任何 Qt 对象
     3. 启动横幅 QSplashScreen(800×151 full.png) + show()
     4. 逐个 import 重型模块（每步之间 processEvents()，让横幅动画继续）
     5. app.setStyle("Fusion")    ← QWindowsVistaStyle 会用原生绘制盖在 QSS 上，
                                     表现为下拉框/数字框箭头变方块且 QSS 压不住
     6. install_no_wheel_filter(app)   ← 必须用这个函数，不能直接 installEventFilter
     7. load_custom_fonts(app)    ← 必须在任何控件创建之前，否则已建的控件不继承字体
     8. ConfigManager → StateMachine → ResourceManager → OverlayRenderer → HotkeyManager
     9. MainWindow(config, state, overlay, hotkey, resources)
            ├─ __init__：设窗口尺寸 + 应用全局 QSS（_setup_full_style）
            └─ 建 10 个 tab 的"工厂"，但**不建对象**
    10. window.show()
    11. QTimer.singleShot(0,  _create_ui_frame)    ← 顶栏 + 导航 + tab_stack
        QTimer.singleShot(0,  _create_first_tab)   ← 只建准星面板
        QTimer.singleShot(100, _background_tasks)  ← 热键注册、滚轮模块、overlay 窗口、
                                                      横幅从右向左扫描消失
    12. app.exec_()
```

**退出**：`closeEvent` 先隐藏窗口，再跑**一份清理契约**——
`collect_tab_cleanup_steps(self) + collect_window_cleanup_steps(self)` 交给
`run_cleanup_steps()`（逐项 `safe_call` 隔离 + 每步耗时日志），然后 `hotkey.shutdown()` +
`config.save_config()`，最后 `quit()`。清单本体在 `core/cleanup.py`，**不在这里逐项列**。

`main.py` 另外挂了 `aboutToQuit`，跑的是**同一份契约**（不是"只清放大镜"那套旧兜底）。
正常退出时它是第二道，所以各清理动作必须**幂等**——双跑安全。

**为什么要 "分阶段 + 单发定时器"**：窗口先显示出来（用户马上看到界面），重活放到事件循环里做。所以**不要把这些 `singleShot` 改成同步调用**——那会让启动黑屏更久。

---

## 三、三个概念：电闸 / 开关 / 暂离

每个功能模块都有三层，**混在一起是本项目最容易犯的错**：

| 层      | 含义         | 判断方法                                | 关闭时做什么                                              |
| ------ | ---------- | ----------------------------------- | --------------------------------------------------- |
| **电闸** | 模块是否**加载** | `config.is_xxx_enabled()`         | 销毁引擎：timer.stop ()、线程.stop ()、overlay=None、对象置 None |
| **开关** | 功能是否**激活** | 热键 toggle → `overlay.set_active()` | 停 timer / 截屏，窗口 hide                                |
| **暂离** | 窗口是否**可见** | `ammo_wheel.suspend_changed` 信号   | 只 hide/show，**不动开关状态**                              |

> **`overlay.hide()`/`show()` 只控制窗口显隐，不改 `state.overlay_visible`**。state 是用户偏好，只能由用户操作（按钮/热键）改变。关闭时调 `overlay.hide()` 是为了隐藏窗口，不能连带把用户偏好改成 False（2026-10-17 修过这个 bug：closeEvent 里 `overlay.hide()` 改了 state → 保存 False → 下次启动准星常闭）。

| 模块    | 电闸                             | 开关                 | 暂离                         |
| ----- | ------------------------------ | ------------------ | -------------------------- |
| 准星面板  | 常驻                             | `overlay_toggled` | 降透明度 50%                   |
| 滚轮切弹种 | 常驻                             | 无                  | 它是 `suspend_changed` 的信号源 |
| 角度仪   | `is_angle_meter_enabled`    | `pause_toggle`    | 暂停读鼠标增量                    |
| 标定测距  | `is_distance_meter_enabled` | = 暂离取反             | `set_function_active`    |
| 放大镜   | `is_magnifier_enabled`       | `set_active`      | `set_suspended`           |
| 建队宏   | `is_squad_macro_enabled`    | start/stop         | 不需要                        |

**电闸关闭时零开销**是硬要求：不建对象、不注册钩子、不启线程。所以"关掉再打开" 必须真的能恢复，"打开着启动" 和 "启动后打开" 必须走同一条初始化路径。

---

## 三・五、当前 X 的唯一持有者（SSOT）

**2026-10-08 做过一次 SSOT 改造**，把"当前载具 / 弹种 / 倍率"从多处各自存储收敛成一处。
这是硬约束，违反它会直接产出"UI 与状态不一致"的 bug。改造前项目里有 **12 处伪 SSOT**
（同一语义存好几份、靠信号互相拼凑同步）。

* **唯一持有者**：`core/state_machine.py` 的 `StateMachine`。
  读用 `state.current_vehicle` / `current_ammo_type` / `current_magnification_index`
* **config 层不再直接写 `current_state`**。三个 setter 已私有化：
  `_set_current_vehicle` / `_set_current_ammo_type` / `_set_current_magnification_index`
  —— 只有 `StateMachine` 能调
* **业务改动也要走 state，不要直接调 config**。下面这些在 `StateMachine` 上有包装，
  它们改完数据会**顺带把选中态修好**（如删掉当前载具时一并迁移 / 清空 `current_*`）：
  `add_vehicle` / `remove_vehicle` / `rename_vehicle` / `copy_vehicle` / `import_vehicle` /
  `remove_ammo_type` / `rename_ammo_type` / `remove_magnification`。
  绕过包装直接调 `config.xxx()` 会留下指向已删对象的悬空状态
* **UI 的选中态由 state 驱动**：列表不要自己记"我选中的是谁"；收到
  `vehicle_changed` / `ammo_type_changed` / `magnification_changed` 后按 state 重设选中
* **症状速查**：新增载具后只有载具列表变了、弹种 / 倍率列表还停在旧载具；删掉当前载具后
  各处仍显示它 —— 都是又冒出第二份"当前 X"了

---

**一处可接受的缓存（不是伪 SSOT，别去"修"它）**：`MainWindow._current_theme`。
`config.get_theme()` 是权威，它只是缓存，而且**只有一条写路径**（`__init__` 读一次 + `_apply_theme` 写）。
唯一风险是"以后有人在别处 `config.set_theme()` 却不经过 `_apply_theme`"——
真要做的话，在 `set_theme` 旁标一句"改主题的唯一入口是 `MainWindow._toggle_theme`"就够了，**不要**为此重构。

**S1 修法的边界（2026-10-14）**

S1 的修法是"`_get_selected_vehicle()` / `_get_selected_ammo()` 列表无选中时回落到 state"。
它带来一个新行为：**筛选结果为空时，详情区显示 state 的载具——虽然列表里看不到它。**
这是设计取舍，不是 bug：筛选只过滤列表，不改变"当前载具"。

- 正常路径：列表选中 = state → getter 取列表值 → 不变
- 筛选有结果：自动切第一辆（`_on_tag_clicked` 末尾 `setCurrentRow(0)`）→ state 变 → 列表选中变 → 取列表值
- 筛选无结果：列表空 → getter 回落 state → 返回当前载具

## 四、配置系统

* `core/config/` 按模块拆文件，**Mixin 模式**：`core/config/__init__.py` 把各 Mixin 拼成

  一个 `ConfigManager`。新增配置项 → 找到对应 Mixin 文件加 `get_/set_` 方法

* 两个文件：`config/config.json`（明文，加密已取消）、`config/bbox_cache.json`

  （bbox 预计算缓存，每条存 `bbox` / `mtime` / `orig_size` / `sha256`。**有效性判据是内容
  sha256，mtime 只作快路径**：mtime 在 zip 解压（2 秒精度、向下取偶）和 git clone（不保存
  mtime）后必然失真，只认 mtime 会让出厂的预计算在别人机器上 0 命中。`cleanup()` 只删孤儿
  **并顺带自愈 mtime，不得按 mtime 删条目**——那会在第一次启动、第一个 `get()` 之前就把整份
  缓存清空。真接不上才删掉重启）

* **数据目录决策**（2026-10-24 批次 2，P5）：便携优先——exe 同级 `config/` 可写就维持；

  不可写（Program Files 标准用户 / 公司锁定目录 / 只读介质）降级

  `%APPDATA%\GunnerSight\config`，**首次降级把随包出厂的 config.json 复制过去做种子**

  （77 载具库不丢）；`%APPDATA%` 也不可写时退 `%TEMP%\GunnerSight\config`（保命，设置不持久）。

  探测用**真实写探针文件**，不信 `os.access`（只读介质 / OneDrive 占位文件会让它说谎）。

  `bbox_cache.json` 跟随同一决策（`OverlayWindow(config_dir=...)`，overlay 不再自己拼路径）。

  信息页显示当前数据目录。`resources/` 不降级——只读位置读出厂资源没问题，受影响的只有导入新图

* **配置损坏回退**（2026-10-24 批次 2，P6）：加载失败时**先留痕再覆盖**——rename 到

  `backups/` → 同目录改名 → 写恢复副本（配置目录 / %TEMP%）逐级降级；全部失败则原文件

  原地保留，启动路径**绝不静默覆盖**用户数据。回退后启动弹一次提示（`config.recovery_notices`）

* **写入是防抖的**：`set_xxx` 通常只改内存 + `request_save()`（500ms 防抖落盘）。

  改配置的代码**不要**自己去写文件

* **锁内 IO 是有意的，别优化出去**：`_atomic_write` 全程持 `_save_lock`——序列化 + 302KB 落盘 +
  最多 3×50ms 重试，全在锁里。极端情况会让 UI 线程卡 ~150ms，这是**主动接受的代价**。
  把落盘挪出锁看起来能提速，实际正好回到「配置并发保存损坏」那个最贵的 bug（四层防御就是为它建的）。
  这条写在 CHANGE_LOG 里只是"事实"，在这里才是"别再动它"。

* **配置必须向后兼容**。软件已发布（2026-10-18 起），用户手上有旧 cfg。

  改配置格式时必须保证：旧 cfg 加载不崩溃、新字段有默认值兜底、语义变更（如角度仪坐标从绝对改相对）在 CHANGE_LOG 标 breaking change 并说明影响。

  加字段不需要迁移（`get("x", 默认)` 兜底）。删字段或改语义才需要考虑。

* 配置项大多有默认值兜底（`self._config.get("x", 默认)`），所以加字段不需要迁移

* `ConfigManager` 保存时会顺手清掉 `REMOVED_CONFIG_SECTIONS` 里列的、已删模块的段

  （历史残留不会一直躺在用户 cfg 里）。**删模块时记得往这个集合里加一条**

**资源目录读写分离**（两条路径，别混）：

* `config.resources_dir` = **读**主路径（exe 同级的出厂资源）
* `config.resources_write_dir` = **写**路径（主路径不可写时降级到 config 侧）
* `config.resolve_resource_path(rel)`：出厂优先 → 写目录兜底。**读图片一律走它**，
  不要自己拼 `resources_dir / rel`——装到 Program Files 这类只读位置时会读不到
* `ResourceManager(write_dir=...)` / `get_write_dir()`：list 取两目录并集，
  import / export `.gsv` 落到写路径

---

## 四・五、各模块引擎速查

改某个功能前，先看它 "跑在哪个线程、数据怎么流"：

| 模块    | 引擎                              | Tab                       | 关键机制                                                                                                                                                                                                         |
| ----- | ------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 准星面板  | `core/overlay.py`               | `overview_tab.py`        | 透明置顶窗口，画分划图；缩放 / 偏移 / 不透明度三参数，载具可覆盖全局                                                                                                                                                                        |
| 滚轮切弹种 | `core/ammo_wheel_selector.py` | 无独立 tab                   | 滚轮打开预选列表，2s 超时或左键确定收尾；**弹种热键命令也要收尾**（热键选中的就是当前弹种时状态机不发信号）；位置偏移存 `global_settings.wheel_offset_x/y`（`config.get_wheel_offset()` / `set_wheel_offset(x, y)`），准星面板可调                                                                                                                                                    |
| 角度仪   | `core/angle_meter.py`          | `angle_meter_tab.py`    | Raw Input 读鼠标增量 → 查校准曲线 → 角度；**灵敏度换算在读取时做**，见本节下方                                                                                                                                                                      |
| 标定测距  | `core/distance_meter.py`       | `distance_meter_tab.py` | 屏幕标定 + 地图测距                                                                                                                                                                                                  |
| 适配设置  | `core/overlay.py`（`_adapt_factors`） | `adapt_tab.py`           | 换算系数 = **挡位 / 基准**（基准 2560×1440 → 2K 挡位=1.0、1K=0.75、4K=1.5）；另有 `_sx/_sy_override` 可覆盖 |
| 放大镜   | `core/magnifier.py`             | `magnifier_tab.py`       | **副线程抓屏**：`_GrabWorker`(QThread) 用 `mss.grab(region)` 抓原生区域 → QImage 缩放 → signal 回主线程 paint。paintEvent 尺寸匹配时 1:1 blit，否则拉伸。1x 倍率自动停抓 + 隐藏。屏息拆成两笔账：**旋钮**（`_zoom`/`_radius`，持久化，决定松开后落在哪）+ **加成**（`_breath_zoom`/`_breath_radius`，只在按住期间存在），画面取两者之和；松开只撤加成，按住期间调的旋钮留着。旋钮顶到下限时差额转记到加成上（否则热键"按了不动"），见 `adjust_zoom`。当前 preset 存 `magnifier.current_preset`（S3 修复，重启保持选中） |
| 建队宏   | `core/squad_macro.py`          | `squad_macro_tab.py`    | 按键序列注入（序列本身硬编码，见十二节）                                                                                                                                                                                        |
| 资源库   | `core/resource_manager.py`     | `resource_tab.py`        | 图片等资源 + 引用计数；`assets/` 下的内部资源不进资源库                                                                                                                                                                           |

**角度仪的灵敏度换算**：换算发生在**读取时**，存的是原始测量点——所以已有校准数据会自动
被纠正、不需要重校。但校准会**快照当时的灵敏度**：灵敏度必须在**校准之前**填好，
否则那条曲线此后永远不自动换算（刻意的保守行为：宁可不动也不按 0 缩放）。

**射表 profile 缓存靠「对象同一性」**：缓存判据是 `entry[0] is not table`——
只有**换了一个新的 table 对象**才算失效，**原地修改射表内容不会让缓存失效**。
表现是"用户改了射表数据但读数不更新，且不报任何错"（这个项目最怕的失败形态）。
所以写回路径必须**替换引用**，不准原地改 dict。当前 UI 恰好每次新建顶层 dict，
属于**碰巧对**，不是契约对——哪天有人改成原地更新就会静默失效。

**放大镜的 UI 约定**：顶部 48px 大示数是当前倍率；基本参数用 `QGridLayout` 6 列 3 行（外框半径 / 截屏帧率 / X 偏移；屏息半径步长 / 屏息倍率步长 / Y 偏移）；

枪械列表左侧 `DualLabelListWidget` + 右侧标签 `QListWidget`，两者 stretch=1 等高。

---

## 五、热键系统

* `core/hotkey_manager.py` 管全部热键。每个热键槽：`key1/key2` + `trigger1/trigger2`

* trigger 类型：`按下触发` / `松开触发` / `按住模式`（自动绑 down + up）

* **键名 → 虚拟键码只有一个来源**：`core/win32_utils.py::KEY_NAME_VK`（41 项）。
  按键注入（`squad_macro`）和按住检测（`angle_meter_tab`）都查它。
  2026-10-13 合并——此前这两个模块各维护一份表（31 + 5 + 23 项、重叠 18 项），
  属于 `docs/RULES.md` §1.1 点名的"同一功能多种实现"，**新增键名只改 KEY_NAME_VK**
* 键名格式**带修饰键前缀**：`ctrl+mouse_wheel_up`。判断 "这是不是滚轮键" 必须先用

  `_parse_hotkey_name()` 拆掉修饰键再比主键 —— 直接 `in _WHEEL_KEYS` 会漏

* **新增一个热键的三步**：

1. `_register_all_hotkeys()` 里注册

2. `HotkeyManager` 上定义 pyqtSignal

3. `main.py` 里 connect 到具体动作

* 改完绑定关系要调 `hotkey.reload_hotkeys()`

* **全局钩子只在 `hotkey.initialize()` 之后生效**，而这个调用在 `_background_tasks` 里。

  测试里**不要**调它（会真的装系统级钩子）

---

## 五・五、跨模块信号（谁通知谁）

页面之间**不互相持有引用**，一律走信号；`main_window` 是唯一接线处
（它的职责就是"跨页协调"，所以 `connect` 都写在那里）。常用的几路：

| 信号 | 从哪来 | 到哪去 | 为什么 |
| --- | --- | --- | --- |
| `StateMachine.vehicle_changed` / `ammo_type_changed` / `magnification_changed` | 状态机 | 各页按 state 重设选中与详情 | 当前 X 的 SSOT，见三・五 |
| `VehicleConfigTab.tags_changed` | 载具配置页（标签增 / 删 / 改名） | 准星面板 / 角度仪 / 放大镜 / 建队宏的 `refresh_tag_filter` | 标签下拉的数据源变了，各页都必须重建；漏接的页面表现为"下拉里找不到新标签" |
| `AmmoWheelSelector.suspend_changed` | 滚轮模块（暂离的源） | 准星 overlay / 放大镜 / 标定测距 / 角度仪 | 暂离要一次通知所有可视模块，见第三节 |
| `HotkeyManager.*_triggered` | 热键管理器 | `main.py` 的分发函数 | 热键只改状态 / 调**已创建**的 tab，不触发懒加载 |

**新增跨页联动的规矩**：信号定义在**数据的拥有者**那一侧（谁改数据谁 emit），
接线写在 `main_window`，接收方只做"按新状态刷新自己"，**不要反向回写数据**。

---

## 六、tab 创建机制（本项目最核心的约定）

`gui/main_window.py`：

* `_NAV_GROUPS` 定义导航分组和顺序；运行时维护 `_row_to_tab` / `_tab_to_row` 映射

组名与页面名**以 `_NAV_GROUPS` 里的字面量为准**。2026-10-08 改过名："资源" → "相关"、"屏幕适配" → "适配设置"；按旧名 grep 会 0 命中。

* `_tab_factories`：`{tab索引: lambda 构造该tab}`。**只是蓝图，不是对象**

* `_ensure_tab(idx)`：**懒加载**。构建失败时：记录完整 traceback 后

  **原样抛出**，绝不返回替身、绝不写进 `_tab_cache`

* `_tab_error_pages`：需要 "坏了也要能用" 的路径（导航、启动预创建）降级到这里。

  **它和 `_tab_cache` 是两回事**，不能混

* `get_tab(idx)`：**纯查询，零副作用**。热键回调、退出清理、任何 "可能还没创建" 的

  场景都必须用它，不能访问 `window.xxx_tab` 这类懒加载属性（那会现场造一个新 tab）

**启动时创建哪些 tab**：

* `_create_first_tab()` 建准星面板（用户第一眼要看的）

* **电闸开启的进阶模块（角度仪 / 标定测距 / 放大镜 / 建队宏）会被主动预创建**——

  否则全局热键触发时没有 tab 可以派发，表现为 "热键没反应"

* 其余 tab 都是用户点导航时才建

**由此推出的一条硬约定**（改任何进阶模块都必须遵守）：

> `__init__` 被调用时，该 tab **不是当前显示页**，`showEvent` **不会触发**。
> 所以 `__init__` 必须自己完成"加载数据 + 设置控件启用状态"，
> **不能只设一个 `_data_loaded = True` 之类的标志位等 `showEvent` 来加载**。

---

## 七、目录地图

```
LICENSE                     当前许可全文：GPL-3.0-only
LICENSE-HISTORY.md          许可更正声明（历史 MIT 时期的分层说明，见第十节末）
main.py                     启动/退出编排、跨模块接线（信号 connect 都在这）
core/
  colors.py                 颜色唯一来源（主题 + 状态色 + 叠加层色）
  cleanup.py                清理契约 SSOT（TAB_CLEANUP_STEPS / collect_* / run_cleanup_steps）
  config_manager.py         ConfigManager 汇总入口
  config/                   按模块拆的配置 Mixin
  hotkey_manager.py         全局热键（键盘 + 鼠标）
  overlay.py                准星叠加层
  ammo_wheel_selector.py    滚轮预选弹种（无独立 tab）
  {magnifier,angle_meter,distance_meter,squad_macro}.py   各功能引擎
  resource_manager.py       资源库（图片等）
  state_machine.py          当前 X 的唯一持有者（SSOT，见三・五）+ 状态广播
gui/
  main_window.py            窗口壳、导航、tab 工厂、**全局 QSS**、主题
  widgets.py                通用控件工厂（改动前先看这里有没有现成的）
  hotkey_widgets.py         热键绑定控件
  wheel_filter.py           无焦点控件不吞滚轮
  tabs/                     10 个页面
  mascot/                   "惊天一条区"吉祥物（独立小窗口；音量常量 DEFAULT_MASCOT_VOLUME）
resources/                  图片/图标/字体/启动横幅
config/                     运行时配置（打包含此目录）
tests/                      回归套件（策略见 docs/RULES.md §5）
docs/                       项目文档（README、USER_GUIDE、AGENTS 在根目录）
  RULES.md                  开发规范——规矩，判据的唯一来源
  HANDOVER.md               交接文档（本文件）
  CHANGE_LOG.md             变更时间线（含回退过的方向）
  CREDITS.md                第三方素材版权声明（随包发布）
tools/                      开发辅助：audit_docs / audit_manual / export_gui_facts / build.bat
```

---

## 八、改代码时的硬约定

> **这一节的内容已迁至 `docs/RULES.md` §4**（GUI 约定）：工厂、颜色、成对控件、
> 列表恢复选中、窗口尺寸。
> 为什么搬：它们是**判据**（下次该怎么做），不是**现状**（现在长什么样）。
> 标题保留只为不让旧引用失效。**新增的 GUI 规矩写进 RULES，不要写回这里**；
> 只有当某条变成"这个项目的现状描述"（某页面特有的既定行为）时，才记在此处。

---

## 八・五、日志：出问题先看这里

| sink | 级别 | 用途 |
| --- | --- | --- |
| `logs/app_<日期>.log` | **DEBUG（永远）** | 排错用，留全。文件永远最详细，不需要先设环境变量。7 天轮转 + zip 压缩 |
| 控制台（stderr） | WARNING | 给用户看，不刷屏 |
| `GS_DEBUG=1` 环境变量 | 控制台升 DEBUG | 只升控制台，文件已经是 DEBUG |

**文件 sink 永远是 DEBUG**，排错时不需要先设 `GS_DEBUG=1`；该变量只升控制台。

**启动耗时约 320 ms，其中 92% 是 `QApplication()` 自身**（平台插件 + 字体库 + 样式）——
已实测，没有优化空间；高频路径的全部接收槽也逐个审过，都是增量更新。
（分阶段数字与"为什么别再优化"的完整依据在 `docs/RULES.md` §8。）

## 九、怎么验证（测量手册）

**离屏 Qt 没有字体**，所以**不要用像素 / 截图判断文字和尺寸**，要量属性。

| 想验什么              | 怎么量                                                                                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 内边距               | `分组框.layout().geometry()` + `contentsMargins()`（它正好铺满 QSS 收缩后的 contentsRect）。**必须先把该页设为当前页**——Qt 不给 `QStackedWidget` 的隐藏页做布局                                                      |
| 控件布局 / 列宽比 / 左右顺序 | 先 `widget.layout().activate()` + `processEvents()`，再读 `geometry().getRect()`。**不 activate 会读到过期的 0 或全宽**                                                                          |
| 颜色                | 读 `QApplication.styleSheet()`（Qt 持有的已解析样式表）+ 控件的 objectName / 属性                                                                                                                  |
| 真实窗口尺寸 / 位置       | 起真进程，用 `GetClientRect` + `ClientToScreen`。**不要用 **`GetWindowRect`—— 它含 Windows 的隐形拖拽边框（本机每边约 9px），会把 800 量成 818                                                              |
| 真实运行行为            | 在**进程内**构造 `MainWindow` 并 `show()`（windows 平台），比外部探针可靠得多                                                                                                                          |
| 离屏构造全部 tab        | `QT_QPA_PLATFORM=offscreen`，`ConfigManager(config_dir=tmp)`，`_create_ui_frame()` + `_create_first_tab()` + `_ensure_tab(i)`。**不要调 **`hotkey.initialize()`（会装全局钩子） |

**通用纪律**：先量 "改之前"，再量 "改之后"，用数字说话。

如果一个测试 / 探针的结论是 "没问题"，也要能说出 "我凭什么认为它没问题"——这一轮就出现过 "两个样本都已经被我改坏，却拿它们互相当对照" 的错误结论。

---

## 十、打包与路径

```
# 唯一打包脚本（双击或命令行跑）
tools/build.bat
```

**单箭头模型**：源码版是唯一真相来源。桌面版就是源码版打包后的运行副本，没有独立状态。

```
源码版 → 自动备份 → 验证 → tools/build.bat → dist/main.dist/ 整目录覆盖桌面版（含 config/）
```

* 产物：`dist/main.dist/`，用 `robocopy /MIR` 整目录覆盖桌面版，**包含 config/**。桌面版里额外的文件会被删除——想保留的改动必须放源码版里。

* **唯一打包脚本就是它**。历史上还有个 `release.bat`，是它的复制粘贴残留（产物名还不一致：`GunnerSight.exe` vs `GUNNER SIGHT.exe`），已删除。开发版与发布版现在没有区别（config 明文，加密已取消）

* `tools/build.bat` 只删 `dist\main.dist`，**保留 **`dist\main.build`（Nuitka 的 C 编译缓存）：删掉它会从 60 秒退化成每次全量重编

* `.bat` **必须 CRLF 且全文纯 ASCII**（见 `docs/RULES.md` §3 与 §9；中文写进 `.bat` 会被解析器吞字符）

* `tools/build.bat` **解释器自适应**（2026-10-24 批次 2，P2）：有 `uv` 走

  `uv run --with nuitka --with zstandard python`，否则系统 `py` 启动器；缺 nuitka 时

  预检并给人话错误（而不是 `No module named nuitka`）。作者机器没有 uv，行为与以前逐字一致

* `pyproject.toml` **已可打包**（2026-10-24 批次 2，P1）：`[build-system]`（setuptools）+

  `[tool.setuptools.packages.find] include=["core*","gui*"]` + `py-modules=["main"]`，

  `pip wheel .` / `pip install .` 不再报 "Multiple top-level packages discovered"；

  构建依赖放 `[project.optional-dependencies] build`（nuitka + zstandard），不进默认安装

  **但「装得上」不等于「能用」**：wheel 只含 `core*` / `gui*` / `main`，
  **不含 `config/` 和 `resources/`**。`pip install .` 之后启动会自己建配置骨架，
  但没有任何准星图——是个空壳。本项目按**源码仓库**分发，pip 安装只用于验证构建链能过，
  不是支持路径。

* **依赖源显式声明**：`pyproject.toml` 的 `[[tool.uv.index]]` 指向 aliyun（`default = true`），
  不再依赖环境变量或本机 pip 配置。克隆仓库的人 `uv sync` 直接能跑

* `--include-data-dir=config=config` 会把当前 `config.json` 打进包，所以 config 目录的变化也会进发布包

* **资源目录名不止"有中文"这一种危险**：`resources/` 下还有 20+ 个**含空格或逗号**的英文目录
  （如 `USMC, LAV-25`）。拼路径、`robocopy`、zip 打包都容易被它们咬到——路径一律加引号，
  不要用字符串拼接去凑路径。

* **发布包必须在 Windows 侧打包**：`.gsv` 由 Python `zipfile` 写 UTF-8 标志位，
  第三方压缩器不在支持路径内；在 Linux/CI 上打 zip，中文与含空格目录名会乱码，
  表现是对应载具准星不显示，**且不报错**。

### 备份

| 类型 | 触发 | 目录 | 增殖 |
| --- | --- | --- | --- |
| 自动备份 | 每次打包前 | `backups/auto_before_build/` | 不增殖，新的覆盖旧的 |
| 用户备份 | 用户说"备份"时 | `backups/GunnerSight_src_<时间戳>/` | 可增殖 |

自动备份排除 `dist/`、`.git/`、`.venv/`、`backups/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`.workbuddy/`。

**`.venv/` 必须留在这个名单里**：它 156MB，曾占整份备份的 78%。它是 `uv sync` 建出来的虚拟环境（不是源码），
丢了能重建，备份它只是白写盘。

| 路径 | 是什么 |
| --- | --- |
| `<项目根目录>` | 源码（改这里） |
| `<桌面发布版目录>` | 桌面版（打包产物，用户直接双击的） |
| `GunnerSight\backups\auto_before_build/` | 自动备份（每次打包前覆盖） |
| `GunnerSight\backups\GunnerSight_src_<时间戳>\` | 用户备份（可增殖） |
| `GunnerSight\.venv\` | 本地虚拟环境，`uv sync` 建的（156MB，不入库） |
| `GunnerSight\gunnersight.egg-info\` | 上面那个虚拟环境做"可编辑安装"时，setuptools 顺手写在**源码根目录**的包元数据（包名/版本/依赖清单，12KB）。不入库、可删、删了下次 `uv sync` 又长出来。**别去编辑它**，改它不影响已安装的包 |

### 开源仓库

| 项 | 值 |
| --- | --- |
| 远端 | `github.com/403-FORBIDDEN-38/Gunner-Sight` |
| HEAD | 以 `git log -1 --oneline` 为准（**不要在这里写死值**，写的那一刻就开始过期） |
| 不进仓库 | `AGENTS.md`（人格层钩子，仅本地保留）、`dist/`、`backups/`、`logs/`、`__pycache__/` |
| 进仓库 | `docs/RULES.md`——规矩要能被 diff、被 review、改坏能回滚，所以它必须入库 |

**`my_beloved: "Xiaocheng"`** 出现在 `config/config.json` 与 `core/config/base.py` 的默认模板里。
它是用户**特意保留的署名式字段**：不要删、不要改、不要当成"无用字段"清理。
开源前做过凭据扫描（api_key / secret / token / password / bearer / sk- 等，0 匹配）。

### 发布前验收矩阵（来源：2026-10-24 发布兼容性专项审查；原文已归档删除，结论见 CHANGE_LOG）

每项都应在**非作者机器**上过。本机已过 ①②⑤⑥⑦⑧（逐项证据见 CHANGE_LOG 2026-10-24）。
**仍缺 ②③④ 三项，欠账登记在 §十一**——不在这里重复一遍。挂了就是回归，回来查。

| # | 验收项 | 方法 |
| --- | --- | --- |
| 1 | 标准安装路径 | 干净环境 `uv sync` + `pip install .` 均成功。**这项只证明构建链能过**：`pip install .` 装完是空壳（无 `config/`、`resources/`），真正可用的分发形态是源码仓库或 dist |
| 2 | 从零构建 | 干净 Windows 按 README 产出 dist（含联网下载编译器场景） |
| 3 | 只读位置运行 | Program Files + 标准用户双击，正常启动、日志降级 TEMP |
| 4 | 设置持久化 | 上述环境下修改设置，重启后保留 |
| 5 | 可选模块全开 | 放大镜/角度仪/测距/吉祥物电闸全开，跑 10 分钟看 logs 无异常 |
| 6 | 压缩包完整性 | 英文 Windows 解压 zip，中文资源目录名与文件数与发布前一致 |
| 7 | 出厂配置 | 解压成品检查 config.json 与源码版一致（`my_beloved` 是刻意署名，见上文） |
| 8 | 非 Windows 报错 | Linux 下启动给人话错误而非 ctypes 堆栈 |

### 许可：GPL-3.0-only，不可改回 MIT

当前许可是 **GPL-3.0-only**，全文在根目录 `LICENSE`。原因见 `README.md` 许可节：
依赖 PyQt5（GPLv3 / 商业双许可，**无 linking exception**），分发二进制就必须整体 GPLv3。

历史 `136d148` 至 `592feac` 之前误标 MIT，**已更正**。更正声明、以及"从历史版本回滚的人
仍受什么约束"在 `LICENSE-HISTORY.md`——**别把那段 MIT 当成可用的授权依据**：
本项目对 PyQt5 没有版权也没有授权资格，那份声明就 PyQt5 部分自始无效。
发布标签 `v0.0140300177`（指向 MIT 时期）已删除。

---

## 十一、当前待办

> 本节**只为真正的欠账存在**。条目完成就删掉，把结论搬进对应机制章节——
> **不要在这里记"某批次已完成"**，那是 `docs/CHANGE_LOG.md` 的事。
> 长期不修的已知问题在下一节，不在本节。

### 发布前验收：仍缺"非作者机器"三项

`docs/reviews/` 那批审查（原文已归档删除，结论见 CHANGE_LOG）列过 8 项验收，本机已过 ①②⑤⑥⑦⑧
（批次 2 后 P1/P2/P4/P5/P6/P7 已修，见 CHANGE_LOG）。**仍待非作者机器**——本机结构上验不了：

| # | 项 | 为什么本机验不了 |
| --- | --- | --- |
| 2 | 从零构建 | 要干净 Windows 按 README 产出 dist（含联网下载编译器的场景） |
| 3 | 只读位置运行 | 要 Program Files + 标准用户双击，看是否正常启动、日志是否降级 TEMP |
| 4 | 设置持久化 | 要在上述环境改设置，重启后看是否保留 |

矩阵全表与验收方法在 §十。挂了就是回归，回来查。

---

## 十二、已知问题（暂不修）

| 问题 | 表现 | 原因 |
| --- | --- | --- |
| 筛选结果为空时列表空 | 筛选后当前载具不在结果集里（如 PMC 空标签），列表 currentRow=-1，但详情区仍显示 state 的载具。**这是设计取舍，不是 bug**（2026-10-14 确认）。详见 §三・五 "S1 修法的边界"。 | 设计取舍 |
| 无弹种的载具 | 倍率列表仍会 populate，各项显示空 crosshair 路径（"未绑定图片"）。 | 老问题，暂不修。 |
| 焦点在桌面时滚轮切弹种失效 | 前台为桌面（Progman/WorkerW）时滚动滚轮，弹种预选不弹出；切回任意其他窗口立即恢复。2026-10-18 日志确认：底层钩子 WH_MOUSE_LL 在桌面前台时收不到 WM_MOUSEWHEEL 事件（`[MouseHook] WHEEL` 零行），非代码 Bug。 | 无解，Windows 底层行为。使用时确保前台窗口不是桌面。 |
| 空房子：两处硬编码 | 建队按键序列与时序（`core/squad_macro.py`）、弹种滚轮确认键 `mouse_left`（`core/ammo_wheel_selector.py`）仍在代码里，cfg 只有 enabled + 热键。 | **2026-10-24 用户拍板"就这样"**：① 该硬编码即理论最优解；② 无改造意愿。不是"以后再改"，别再提。 |
| 吉祥物启用态不持久化 | `config.is_mascot_enabled()` 硬编码返回 False，每次启动默认关闭；`set_mascot_enabled` 写的 `_mascot_enabled_runtime` 全仓无人读。 | **2026-10-25 用户拍板**：吉祥物是"彩蛋性质"的玩意，每次启动关闭是设计意图而不是缺陷。**别给它加持久化**；那个字段是已知冗余，勿当 bug 修。 |
| `_connect_tab_signals` 是一棵 if-elif 树 | 7 个分支按 `tab_index` 硬编；"载具页已存在就补连 `tags_changed`"这段在角度仪/建队宏/放大镜**重复了三遍** | **结构性债，未排期**。正确形态是 `{tab_index: connect_fn}` 注册表。每加一个 tab 就要改这棵树 → 迟早漏连。新增 tab 时**必须同时接两条**：`data_changed`（数据）与 `tags_changed`（标签过滤下拉） |
| 两份热键控件拷贝 | `PauseHotkeyWidget` 与 `HotkeyPairWidget` 是同一套控件的两份实现，连 trigger 映射字典都是复制的 | 违反 §1.1「同一功能一个实现」的**已知例外**，暂不合并（要同时动热键页与暂停页布局）。改其中一份时，另一份的对应 bug 要一起判断 |
| Real Overlay（游戏内叠加）未实现 | 普通置顶透明窗对 DX12 全屏独占无效，需要 UIAccess / hook 层方案 | 2026-10 做过一轮技术调研，结论是成本高、稳定性不可接受，功能没做。**调研笔记已删**（技术有保鲜期），真要做请重新调研，不要照着旧结论做 |
