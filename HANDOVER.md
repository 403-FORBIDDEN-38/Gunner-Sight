# GunnerSight 交接文档

> **读者**：第一次拿到这个项目的人 /agent。目标：读完之后能独立改代码。
> **规则**（怎么做才是对的）在
> `AGENTS.md`
> ；这份文件只讲**这个项目长什么样、为什么这么设计**。
> 只写 "是什么" 和 "为什么"，**不写故事**。踩过的坑压缩成第十二节的一行速查。
> 最后更新：2026-10-18（手册重构） · 版本 `V0.0140300174`
> 变更历史见 `CHANGE_LOG.md`（按时间线）；本文件只写当前状态。

---

## 一、一分钟认识它

给游戏 **Squad** 用的屏幕准星辅助工具（PyQt5）。**不读游戏内存、不改游戏文件**——它的全部手段是：透明置顶窗口 + 图片叠加 + 全局热键 + Raw Input 读鼠标增量。

* 跑起来：`py main.py`（不需要管理员权限）

* 打包：`build.bat` → `dist/main.dist/GUNNER SIGHT.exe`（见第十节）

* 源码 / 桌面版是**两份独立目录**（见第十节），改完源码不重打包的话桌面版不会变

---

## 一・五、四份文档各管什么

| 文件 | 读者 | 内容 |
| --- | --- | --- |
| `README.md` | 路人 / 下载页 | 是什么、怎么装、有什么限制。GitHub 门面，用常规 Markdown 排版 |
| `USER_GUIDE.md` | 使用者 | 完整操作手册。按**任务**组织，5 章 + 附录 |
| `HANDOVER.md` | 接手的 agent | 现状与"为什么这么设计"。本文件 |
| `CHANGE_LOG.md` | 接手的 agent | 时间线，**含回退过的方向**（避免重走死路） |

**`USER_GUIDE.md` 的写法有硬规矩**（2026-10-18 重写时定的）：

* **零 markdown 强调符号**——不用 `**加粗**`、不用表格、不用 `>` 引用块、不用行内代码
* 结构只靠四样东西：编号（1. / 一、）、缩进、全角空格对齐、行首标签词
* 行首标签词固定这四个：`判据：` / `注意：` / `失败排除` / `状态收尾`
* 每个操作都要能回答"做完看到什么"和"没看到怎么办"

这不是洁癖。过量的视觉符号会让使用者失去"仅靠文字看懂"的利落感，
而手册是在游戏间隙翻的——符号越多，扫读越慢。参照物是 KAC 枪械手册的中译版。

**`GUI_INVENTORY.md` 是手册的事实底稿**，由 `tools/export_gui_facts.py`
遍历 QWidget 树生成（10 页控件名、类型、range、当前值）。

* 手册里的控件名、参数范围、出厂值，**一律以它为准，不要凭印象写**
* 出厂值取自**发布包**的 `config.json`，不是工作区——工作区是使用者当前状态，随时会变
  （这个坑踩过两次：只看代码骨架→以为滚轮居中；只看工作区→以为准星出厂关闭，都错了）
* 控件遍历有个坑：`QSplitter` / `QScrollArea` / `QStackedWidget` 的内容**不在 `layout()` 里**，
  必须问它们自己要，否则整页会被导出成空

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

**退出**：`closeEvent` 只对**已创建**的 tab 调 `shutdown()/cleanup()`，然后`hotkey.shutdown()` + `config.save_config()`，最后 `quit()`。

`main.py` 另外挂了 `aboutToQuit` 兜底清理放大镜（`closeEvent` 没走时的保险）。

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

  （自动生成的缓存，接不上就删掉重启）

* **写入是防抖的**：`set_xxx` 通常只改内存 + `request_save()`（500ms 防抖落盘）。

  改配置的代码**不要**自己去写文件

* **不存在配置迁移 / 向后兼容，也不要加回来**。软件从未发布，市面上不存在任何旧 cfg。

  历史迁移函数已全部删除。**判断标准**：新加的 "兼容某某旧格式" 代码，先问"谁会产出那个格式"—— 答案不是 "已发布版本的用户"，那就是墓碑

* 配置项大多有默认值兜底（`self._config.get("x", 默认)`），所以加字段不需要迁移

* `ConfigManager` 保存时会顺手清掉 `REMOVED_CONFIG_SECTIONS` 里列的、已删模块的段

  （历史残留不会一直躺在用户 cfg 里）。**删模块时记得往这个集合里加一条**

---

## 四・五、各模块引擎速查

改某个功能前，先看它 "跑在哪个线程、数据怎么流"：

| 模块    | 引擎                              | Tab                       | 关键机制                                                                                                                                                                                                         |
| ----- | ------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 准星面板  | `core/overlay.py`               | `overview_tab.py`        | 透明置顶窗口，画分划图；缩放 / 偏移 / 不透明度三参数，载具可覆盖全局                                                                                                                                                                        |
| 滚轮切弹种 | `core/ammo_wheel_selector.py` | 无独立 tab                   | 滚轮打开预选列表，2s 超时或左键确定收尾；**弹种热键命令也要收尾**（热键选中的就是当前弹种时状态机不发信号）；位置偏移存 `global_settings.wheel_offset_x/y`（`config.get_wheel_offset()` / `set_wheel_offset(x, y)`），准星面板可调                                                                                                                                                    |
| 角度仪   | `core/angle_meter.py`          | `angle_meter_tab.py`    | Raw Input 读鼠标增量 → 查校准曲线 → 角度；灵敏度换算见十一・5                                                                                                                                                                      |
| 标定测距  | `core/distance_meter.py`       | `distance_meter_tab.py` | 屏幕标定 + 地图测距                                                                                                                                                                                                  |
| 适配设置  | `core/overlay.py`（`_adapt_factors`） | `adapt_tab.py`           | 换算系数 = **挡位 / 基准**（基准 2560×1440 → 2K 挡位=1.0、1K=0.75、4K=1.5）；另有 `_sx/_sy_override` 可覆盖 |
| 放大镜   | `core/magnifier.py`             | `magnifier_tab.py`       | **副线程抓屏**：`_GrabWorker`(QThread) 用 `mss.grab(region)` 抓原生区域 → QImage 缩放 → signal 回主线程 paint。paintEvent 尺寸匹配时 1:1 blit，否则拉伸。1x 倍率自动停抓 + 隐藏。屏息：按下半径 +step 且倍率 +zoom_step，松开半径恢复、倍率 `max(1.0, 当前-zoom_step)`。当前 preset 存 `magnifier.current_preset`（S3 修复，重启保持选中） |
| 建队宏   | `core/squad_macro.py`          | `squad_macro_tab.py`    | 按键序列注入（序列本身硬编码，见十一・2）                                                                                                                                                                                        |
| 资源库   | `core/resource_manager.py`     | `resource_tab.py`        | 图片等资源 + 引用计数；`assets/` 下的内部资源不进资源库                                                                                                                                                                           |

**放大镜的 UI 约定**：顶部 48px 大示数是当前倍率；基本参数用 `QGridLayout` 6 列 3 行（外框半径 / 截屏帧率 / X 偏移；屏息半径步长 / 屏息倍率步长 / Y 偏移）；

枪械列表左侧 `DualLabelListWidget` + 右侧标签 `QListWidget`，两者 stretch=1 等高。

---

## 五、热键系统

* `core/hotkey_manager.py` 管全部热键。每个热键槽：`key1/key2` + `trigger1/trigger2`

* trigger 类型：`按下触发` / `松开触发` / `按住模式`（自动绑 down + up）

* **键名 → 虚拟键码只有一个来源**：`core/win32_utils.py::KEY_NAME_VK`（41 项）。
  按键注入（`squad_macro`）和按住检测（`angle_meter_tab`）都查它。
  2026-10-13 合并——此前这两个模块各维护一份表（31 + 5 + 23 项、重叠 18 项），
  属于 AGENTS §1.1 点名的"同一功能多种实现"，**新增键名只改 KEY_NAME_VK**
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
main.py                     启动/退出编排、跨模块接线（信号 connect 都在这）
core/
  colors.py                 颜色唯一来源（主题 + 状态色 + 叠加层色）
  cleanup.py                清理路径逐项隔离助手（safe_call）
  config_manager.py         ConfigManager 汇总入口（唯一 LF 换行的文件）
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
  mascot/                   "惊天一条区"吉祥物（独立小窗口）
resources/                  图片/图标/字体/启动横幅
config/                     运行时配置（打包含此目录）
tests/                      回归套件（策略见 AGENTS §4）
docs/archive/               过期文档
GUI_INVENTORY.md            控件与出厂值底稿（tools/export_gui_facts.py 生成，可重跑）
MANUAL_OUTLINE.md           手册目录与新旧映射（规划产物，已执行完，留作记录）
```

---

## 八、改代码时的硬约定

### 8.1 GUI 一律走工厂，别手搓

```
box, layout = make_group_box("标题")                           # 有边框组
box, layout = make_group_box("标题", flat=True)                # 无边框组
box, layout = make_group_box("标题", layout_cls=QFormLayout)   # 换布局类型
```

* **缩进的唯一权威是全局 QSS**（`main_window.py` 的 `QGroupBox` 规则）。工厂把布局

  `contentsMargins` 固定为 0，从根本上杜绝 "QSS padding + layout margins" 两处叠加

* 有边框组 = QSS 默认规则 `padding: 8px 8px 4px 8px`（实测内容缩进 9/21/9/5）

* 无边框组 = `QGroupBox[flat="true"]`，`padding: 3px 5px 3px 5px`（实测 5/19/5/3）

* 当前 29 个分组框：**有边框 12**（`padding: 8px 8px 4px 8px`）、**无边框 16**

  （`[flat="true"]`，`padding: 3px 5px 3px 5px`），另有 1 个（"文件夹信息"）默认隐藏

### 8.2 颜色：主色板在 `core/colors.py`，强调色在 cfg

* 主题调色板：`THEME_DARK` / `THEME_LIGHT`（键：bg/ctrl/border/hover/text/subtext/dis_text）

* **强调色来自 cfg，不是常量**（2026-10-08 改）：出厂默认在 `core/config/base.py`
  的默认模板 `global_settings.accent_dark` / `accent_light`（中性值：深 `#EBEBEC` / 浅 `#1D1D1F`），
  运行时用 `config.get_accent_dark()` / `get_accent_light()`。
  **`ACCENT` / `ACCENT_HOVER` 常量已删除，不要再 import**
* 强调色底上的文字走主题字典的 `on_accent_text`（深 `#1D1D1F` / 浅 `#EBEBEC`）
* 主题字典的键：`bg / ctrl / btn / base / border / hover / text / subtext / dis_text / on_accent_text`
  （`btn` 给按钮、`base` 给输入框，2026-10-08 新增；**QSS 里按钮必须显式写
  `background-color`**，否则 Qt 会让它透明、不走 QPalette）

* 状态色：角度仪 `ANGLE_*`、标定测距 `DISTANCE_*`（**`ANGLE_IDLE/ACTIVE/PAUSED/CALIBRATING` 现在只是 `DISTANCE_*` 的别名**，改状态色只改 DISTANCE 一处）

* 叠加层 `OVERLAY_*`：**刻意不随主题变化**—— 它们压在游戏画面上，浅色主题也要深底白字。

  QPainter 用 `OVERLAY_BOX_RGB` / `OVERLAY_BOX_BORDER_RGBA` 元组形式（QColor 不认 CSS 的 `rgba()` 字符串）

* 悬浮窗文字统一 `OVERLAY_TEXT`；底框 `OVERLAY_BOX_RGB` + `OVERLAY_BOX_BG_ALPHA`（20%）。**窗口级 `setWindowOpacity` 已全部取消**，透明度改由底框 alpha 表达

* **大示数（48px）** 走 objectName：`QLabel#info_title, QLabel#zoom_display`；

  变暗态用属性选择器 `[dim="true"]`——**改完属性必须** `unpolish/polish`，否则 QSS 不重算

* `gui/` 里的内联 `setStyleSheet` 已清零；叠加层必要的样式串集中在各模块顶部常量

### 8.3 两种 "成对 / 成骨架" 的控件只有一个实现

* `LinkedSpinSlider`——"输入框 + 滑块" 双向联动，自带防回路：

```
ctl = LinkedSpinSlider((1.0, 1000.0), slider_range=(1, 1000), decimals=1,
                       suffix=" %", initial=100)                # 输入框在左（默认）
ctl = LinkedSpinSlider((1, 1000), suffix="%", fixed_width=80, spin_first=False,
                       leading=minus_btn, trailing=plus_btn)    # 滑块在左，两端挂按钮
ctl.value_changed.connect(...)    # 只有用户改动才发；内部镜像同步绝不外发
ctl.set_value_silent(v)           # 载入配置：两控件同步且零信号
ctl.step_value(±5)                # +/- 按钮：走正常信号链，越界由 spin 范围收敛
```

使用方**不需要写 **`blockSignals`。`set_silent()` 用 `try/finally` 保证信号一定恢复 ——历史那种 `blockSignals(True); setValue(); blockSignals(False)` 一行流一旦中途抛异常，控件会**永久静默且不留痕迹**。

* `FilterListPanel`——"搜索 + 标签筛选 + 双标签列表 + 新建 / 重命名 / 删除" 骨架：

```
panel = FilterListPanel(placeholder="搜索配置...", right_widget=self.link_vf,
                        min_list_height=180, list_stretch=1, right_stretch=1)
panel.set_tag_options(tags)      # 同步下拉并保持选中；选项无变化时不重建
panel.filter_values()            # -> (搜索词小写, 当前标签或 None)
panel.add_requested / rename_requested / delete_requested
```

**列表重建与选中恢复的语义不归它管**，各页自己写 —— 那里的语义本来就不同。

### 8.4 列表 "重建后恢复选中" 的两种相反语义（最容易搞错）

* **必须静默**（阻断信号）：防止回写状态机形成回路。

  例：`vehicle_config_tab._select_row_by_data / _select_row_by_index`

* **必须不静默，且必须在 unblock 之后恢复**：要靠 `currentItemChanged` 级联刷新

  下级列表。例：`vehicle_config_tab._refresh_vehicle_list / _refresh_ammo_list`

**所以不要试图把 `vehicle_config_tab` 里那 5 个 `_refresh_*_list` 统一**：

它们分别是 "静默同步"" 级联重建 ""按索引恢复 + 外部覆盖"" 自建 QCheckable 项 " 四种语义，硬合并就是把两种相反的信号语义搅在一起 —— 那是制造 bug，不是清理。

**恢复选中必须用 "实际插入的行号"**（`self.list.count() - 1`），不能用源数据的`enumerate` 下标：搜索 / 标签筛选会让行号与源下标错位，越界时 `setCurrentRow()`

会**清空**选中（表现为 "列表有内容但没选中 / 参数区不刷新"）。

### 8.5 主窗口尺寸：宽度 = 启动横幅的宽度

* `gui/main_window.py` 的 `WINDOW_SIZE = (800, 700)`，`resize` 和 `setMinimumSize`

  都用它：**启动尺寸 = 最小尺寸**，启动后没有 "能再缩小" 的余量

* 用户口径：横幅是**腰封**。横幅图 `resources/assets/splash/full.png` 是 800×151，

  另有 20 张扫描帧（00.png–19.png，尺寸同样是 800×151），窗口就必须 800 宽；两者都居中，所以边缘正好对齐（实测客户区都是 x=560..1360）

* **改宽度前先看 `resources/assets/splash/` 里的图** —— 图宽是唯一权威，不要反过来

* 不要再用 "按屏幕 clamp" 的逻辑决定窗口尺寸（那是为了绕开一个误判，见十二节）

---

## 八・五、日志：出问题先看这里

| sink | 级别 | 用途 |
| --- | --- | --- |
| `logs/app_<日期>.log` | **DEBUG（永远）** | 排错用，留全。文件永远最详细，不需要先设环境变量。7 天轮转 + zip 压缩 |
| 控制台（stderr） | WARNING | 给用户看，不刷屏 |
| `GS_DEBUG=1` 环境变量 | 控制台升 DEBUG | 只升控制台，文件已经是 DEBUG |

**2026-10-16 修**：文件 sink 从 INFO 升到 DEBUG（永远），排错时不需要先设 `GS_DEBUG=1`。
此前文件 sink 是 INFO（2026-10-13 从 WARNING 升到 INFO），DEBUG 级别的 `[性能]` 计时和
`[MouseHook]`/`[Overlay]` 诊断只在设了环境变量时才落盘——现在永远落盘。

**启动性能实测（2026-10-13，源码版）**：

| 阶段 | 耗时 |
| --- | --- |
| **`QApplication()` 构造** | **295 ms** |
| 热键注册（在后台任务里，不阻塞界面） | 61 ms |
| 字体加载 | 13 ms |
| 主窗口显示 | 11 ms |
| ConfigManager / 图标 / UI框架 / MainWindow | 8 / 5 / 3 / 1 ms |
| **合计** | **322 ms** |

**结论：启动路径没有可优化空间** —— 92% 是 Qt 自身初始化（平台插件 + 字体库 + 样式），
换任何 Qt 程序都一样。**不要再去"优化启动"**。
（`crash_log.txt` / `startup_log.txt` 是异常与 stdout 的副本，正常时为空是对的。）

**高频路径审查（2026-10-13，正面结论）**

把 `magnification_changed` / `ammo_type_changed` / `vehicle_changed` / `overlay_toggled` /
`*_triggered` 的**全部接收槽**逐个读过：都是**增量更新**（改文字、换图、设可见性），
没有 `clear()+重建`、没有读盘、没有全量 `populate()`。
`overlay._on_state_changed` 还额外做了"载具切换期间跳过重复信号"的抑制。

**这条铁律项目遵守得不错，新增槽函数时请保持：高频槽里只准做"改已有的"，不准做"重建"。**
（要判断某个槽算不算高频：它挂在哪个信号上——倍率/弹种/overlay 显隐/热键 = 高频。）

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
build.bat
```

**单箭头模型**：源码版是唯一真相来源。桌面版就是源码版打包后的运行副本，没有独立状态。

```
源码版 → 自动备份 → 验证 → build.bat → dist/main.dist/ 整目录覆盖桌面版（含 config/）
```

* 产物：`dist/main.dist/`，用 `robocopy /MIR` 整目录覆盖桌面版，**包含 config/**。桌面版里额外的文件会被删除——想保留的改动必须放源码版里。

* **唯一打包脚本就是它**。历史上还有个 `release.bat`，是 build.bat 的复制粘贴残留（产物名还不一致：`GunnerSight.exe` vs `GUNNER SIGHT.exe`），已删除。开发版与发布版现在没有区别（config 明文，加密已取消）

* `build.bat` 只删 `dist\main.dist`，**保留 **`dist\main.build`（Nuitka 的 C 编译缓存）：删掉它会从 60 秒退化成每次全量重编

* `.bat` **必须 CRLF**（见 AGENTS §3）

* `--include-data-dir=config=config` 会把当前 `config.json` 打进包，所以 config 目录的变化也会进发布包

### 备份

| 类型 | 触发 | 目录 | 增殖 |
| --- | --- | --- | --- |
| 自动备份 | 每次打包前 | `backups/auto_before_build/` | 不增殖，新的覆盖旧的 |
| 用户备份 | 用户说"备份"时 | `backups/GunnerSight_src_<时间戳>/` | 可增殖 |

自动备份排除 `dist/`、`.git/`、`backups/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`。

| 路径 | 是什么 |
| --- | --- |
| `<项目根目录>` | 源码（改这里） |
| `<桌面发布版目录>` | 桌面版（打包产物，用户直接双击的） |
| `GunnerSight\backups\auto_before_build/` | 自动备份（每次打包前覆盖） |
| `GunnerSight\backups\GunnerSight_src_<时间戳>\` | 用户备份（可增殖） |

### 开源仓库（2026-10-18）

| 项 | 值 |
| --- | --- |
| 远端 | `github.com/403-FORBIDDEN-38/Gunner-Sight` |
| HEAD | 以 `git log -1 --oneline` 为准（写文档时是 `d514ae7`） |
| 不进仓库 | `AGENTS.md`（本地说明书）、`dist/`、`backups/`、`logs/`、`__pycache__/` |

**`my_beloved: "Xiaocheng"`** 出现在 `config/config.json` 与 `core/config/base.py` 的默认模板里。
它是用户**特意保留的署名式字段**：不要删、不要改、不要当成"无用字段"清理。
开源前做过凭据扫描（api_key / secret / token / password / bearer / sk- 等，0 匹配）。

---

## 十一、当前偏差与待办（2026-10-18 复核）

### 1. 版本控制已可用（2026-10-18 更新）

* **git 2.56.0 已装**，本地仓库有完整历史，远端已配
  `origin = github.com/403-FORBIDDEN-38/Gunner-Sight`（项目已开源）

* **文件损坏优先用 git 回滚**：`git checkout -- <file>` / `git restore <file>`。
  AGENTS §3 那条「一行能修就修，修不了就回滚」现在**真的可用**，不要再退回手工重写

* **提交纪律**：本地 `git commit` 可以；**push 之前先问用户**（他明确要求过"不必急着 push"）

* **`AGENTS.md` 故意不进仓库**（`.gitignore` 排除，本地保留）：它是给 AI 看的说明书，不公开。
  所以 `git status` 里看不到它的改动，别以为丢了

* 兜底仍然是 `backups/`（见 §十）：git 只能回滚**已提交**的东西，
  未提交的改动一旦写坏就只能靠备份

### 2. 空房子已知偏差（用户决定：先不动，只登记）

* `core/squad_macro.py`：整条建队流程（Ctrl+V / Alt+Tab / Enter / Up / CapsLock 的

  按键序列与时序）硬编码在代码里，cfg 只有 enabled + 热键

* `core/ammo_wheel_selector.py`：确认键硬编码为 `mouse_left`

* 两处都属 "具体功能行为写在代码里"。改造涉及 cfg 结构 + UI + 交互，风险不小，暂缓

### 3. 准星 "大小缩放" 的滑块范围（已统一，2026-10-13）

输入框和滑块已统一为 1.0–1000.0（`overview_tab` 的 `size_ctl`）。

此前滑块是 25–400，输入框填 800 后碰滑块会掉回 ≤400。已修复，"故意保留原行为"的判断作废。

### 4. 死代码已清零（2026-10-13）

`ruff --select F401,F841,F811` 现在为空（0 处）。清掉的是：早期登记的 3 处死局部变量
（滚轮模块 `old`、配置基类 `ammo`、载具配置 `old_label`），
以及配置基类里**重复写了两遍**的 `get_on_accent_text`（后一份静默覆盖前一份，典型的墓碑）。
**新增代码请保持这个状态**：`py -m ruff check --select F401,F841,F811 core gui main.py` 应为空。

### 5. 清理路径逐项隔离（已完成 2026-10-16）

`AngleMeterTab._shutdown_engine()`、`MagnifierTab._destroy_engine()`、
`SquadMacroTab._shutdown_macro()` 三处改用 `core/cleanup.py::safe_call` 逐项隔离；
`_GrabWorker.stop()` 加 wait 超时 warning；`_FineTuner.stop()` 不改（单动作，隔离无意义）。

**关键决策**：
- `raw.close`（mss 句柄，OS 级）提到 `_shutdown_engine` 最前——越贵的资源越先释放，不依赖异常发生就产生收益
- 6 个动作全部纳入隔离——Qt 对象在 C++ 侧被删后 Python 侧调方法抛 RuntimeError，关闭路径最容易出现
- `safe_call` 是 5 行纯函数（try/except + logger.warning），不是类/上下文管理器
- `_GrabWorker.stop` 的 wait 超时 warning **只是报告状态，不是恢复**——线程真没退出时 mss 句柄依然泄漏，只是日志里有一行。不加重试/强制终止（QThread 无安全 terminate）
- 测试边界：mock 测的是"前一步失败后一步仍执行"（代码路径），不是"OS 资源真的释放了"（靠代码审查）

### 6. 需要人工确认手感的两处（自动化测不了）

* **滚轮转发**：统一过滤器后，"无焦点的下拉框 / 数字框不吞滚轮" 才真正生效，

  且按设计**把滚轮转发给最近的滚动区**（页面滚动）。光标停在下拉框上滚动时，现在是 "页面滚动" 而不是 "什么都不动"。这属于恢复设计意图，但建议实际用一遍

* **角度仪换算**：换算发生在**读取时**，存的是原始测量点，所以已有校准数据会自动

  被纠正、不需要重校。但校准会**快照当时的灵敏度**—— 灵敏度必须在**校准之前**填好，否则那条曲线此后永远不自动换算（刻意的保守行为：宁可不动也不按 0 缩放）

---

## 十一・五、审查任务书（2026-10-13 三轮审查产出）

> 给执行方用：每条都有【处方】。**先看第二张表——那是不该动的**，别把精力花在那儿。

### A 类：低风险，可以直接做

| # | 位置 | 现象 | 处方 | 验证 |
| --- | --- | --- | --- | --- |
| A1 ✅ | `core/overlay_base.py` + `core/ammo_wheel_selector.py` | **滚轮三兄弟**（`MagOverlay`/`CompactOverlay`/`FullOverlay`）的 `__init__` 开头各有**逐字相同**的 4 行窗口属性（Tool+无边框+置顶+半透明+不抢焦点+鼠标穿透），共 12 行重复 | 在 `overlay_base.py` 加一个**工厂函数** `make_overlay_window(w)` 收这 4 行，三处调用它。**⚠️ 不要改成继承 `ClickThroughOverlay`**——那套是"可编辑+点击穿透"机制（带 `_edit_mode`/超时/`_verify_click_through`），与滚轮窗口用途不同，继承会把无关机关带进来。另外 `MagnifierOverlay` 只设 3 条（**不带** `WA_TransparentForMouseEvents`），**别一起统一** | 起程序按滚轮 → 弹窗仍正常显示、仍能收到滚轮事件 |
| A2 ✅ | 9 个函数签名 | `RUF013` 隐式 Optional（`def f(x: int = None)`） | 补 `Optional[int]` 并从 `typing` 导入。纯标注，零运行时影响 | `ruff --select RUF013` 清零 |
| A3 ✅ | `tests/conftest.py`、`core/firing_table.py` | 2 处无用 `# noqa` + 1 处文件末尾无换行 | 删 noqa；补末尾换行 | `ruff --select RUF100,W292` 清零 |

### B 类：要动脑，**先补测试再改**

| # | 位置 | 现象 | 处方 | 风险 |
| --- | --- | --- | --- | --- |
| B1 ✅ | `AngleMeterTab._shutdown_engine`、`MagnifierTab._destroy_engine`、`SquadMacroTab._shutdown_macro`、`_GrabWorker.stop` | **裸调清理动作**：按 AGENTS §2.1「中断即泄漏」，第 1 个 `.stop()` 抛异常 → 后面的 `self.raw.close()`（mss 抓屏句柄）永不执行 | 三处改用 `core/cleanup.py::safe_call` 逐项隔离；`_shutdown_engine` 重排顺序（raw.close 提前）；`_GrabWorker.stop` 加 wait 超时 warning；`_FineTuner.stop` 不改（单动作） | 已补 8 个测试（`tests/test_cleanup_isolation.py`），覆盖"前一步失败后一步仍执行"。OS 资源释放靠代码审查 |
| B2（半做） | `core/mouse_hook.py`（`SetWindowsHookEx` 失败重试处） | 钩子设置失败会 **无限每秒重试 + 每秒写一行日志**（`time.sleep(1.0)` 后退避重试） | **仅改了日志级别**（第 1 次 warning / 后续 debug / 恢复成功 warning）。**重试逻辑保留原样**：无上限、固定 1 秒间隔——历史 17 个日志文件 0 次失败，加上限收益为零 | 涉及钩子可靠性策略，用户决定不加上限 |

### C 类：需求/策略，需要用户拍板

* 空房子两处硬编码（见本节的 §2）——改造涉及 cfg 结构 + UI，风险不小

### 不该动的（别把额度花在这里）

| 项 | 数量 | 为什么别动 |
| --- | --- | --- |
| `RUF001/002/003` 歧义 Unicode | **2400+** | 是中文注释里的全角标点（`：`、`（）`）。这是中文项目的必然产物，**改了反而错** |
| `E402` 模块导入不在顶部 | 87 | **刻意为之**的懒加载（`main.py` 里 import 之间插 `processEvents()` 让横幅动画不卡）。改成顶部导入会让启动多卡几百毫秒 |
| `E501` 行长 / `E701` `E702` 一行多语句 | 196 / 25 | 纯风格，零收益；改了一堆 diff 噪音 |
| `RET505` `SIM102` `SIM105` `PERF102` `PERF203` | ~45 | 纯风格建议。改动要过 AST 重构，收益为零、风险非零 |
| 超长函数（`_main` 225 行、`_setup_full_style` 172 行、各 `_build_ui`） | 9 个 | **本质如此**：一个是启动编排、一个是 QSS 字符串、其余是 UI 搭建。硬拆只会增加跳转层级 |
| "启动慢" | — | **已实测**：322 ms 里 295 ms 是 `QApplication()` 自身（平台插件+字体库+样式）。换任何 Qt 程序都一样，**没有优化空间** |
| "高频路径有全量刷新" | — | **已核实**：倍率/弹种/载具/overlay/热键的全部接收槽都是增量更新，没有 `clear()+重建`、没有读盘 |

---

## 十一・六、用户手册打磨（进行中，2026-10-18 讨论定方向，未执行）

> 给接手的 agent：用户要去找大 agent 做这件事。以下是讨论结论和全部上下文，读完直接能动手。

### 当前状态

- `USER_GUIDE.md`：真铁版，LF 换行。已推 GitHub（master）。2026-10-20 第二轮修正 7 处错误（暂离移交退出权、弹种/载具图片叠加层、倍率无名称输入、比例尺热键循环、删全局组合键前缀）。
- airsoft 版（390 行简洁命令式）已删除，不保留。
- 参考素材：`KAC_SR25_真铁手册_中文译制版.docx`（同目录还有英文原件 PDF SR25-UM-0011-REV-3、airsoft 版译件、配图目录）。

### 差距分析（当前手册 vs KAC 真铁手册）

| 维度 | KAC 真铁手册 | 当前 GunnerSight 手册 |
| --- | --- | --- |
| 安全语气 | "警告""绝不要""始终""必须"，后果明确 | "请""建议""可能"，偏软 |
| 工作原理 | 专门一节，几句话讲清内部流转 | 没有，用户不知道软件怎么工作、边界在哪 |
| 操作步骤 | 编号 SOP（步骤1/2/3），每步有可验证结果 | 叙述性散文（"点击...然后..."） |
| 功能检查 | 每项操作后 a/b/c/d 验证，明确"应/不应" | 只有随意的"验证"小节 |
| 排错 | 三列表格（故障/原因/排除），一一对应 | "若...请按以下顺序排查"的散文 |
| 讨好语言 | 没有，只说"做什么"和"不做什么" | "适用于...场景""推荐大多数用户使用" |

### 打磨方向（用户已确认）

1. **安全章硬化**："请"→"必须"，"可能"→"将"，每条警告说清后果（不是"可能影响体验"，而是"将导致叠加层无法渲染"）
2. **加"工作原理"节**：放在操作说明开头。内容：不读游戏内存、截屏+鼠标增量计算、透明置顶窗口、全局底层钩子、状态机统一管理模块。同时列已知边界（全屏独占模式叠加层被截断、桌面焦点下滚轮失效、校准需游戏显示俯仰角）
3. **核心操作改编号 SOP**：首次运行、载具配置、校准、定角装填这些关键流程改成步骤1/2/3，每步带验证结果（"确认屏幕中心出现分划图片"）
4. **排错改表格矩阵**：故障/原因/排除三列，一一对应
5. **删讨好语言**：只留操作和结果
6. **PMCS 表格化**：比赛前检查清单改成三列表（项目/检查内容/处理方法）

### 用户偏好（硬约束）

- **通读一遍过**：不回看不重看，概念解释紧跟操作步骤，无附录割裂
- **去人化、去误差的纪律性**：不提供情绪价值，只提供确定性
- **基于用户操作视角（GUI）**：从用户在界面上看到什么、点什么出发，不是从代码模块出发
- **配图**：用户有 3 张截图（载具配置页浅色、准星面板、适配设置页）。如需更多截图问用户要。

### 注意事项

- 手册里的术语必须与 UI 一致（"定角装填"不是"归零"，config 键名 `auto_reset` 不改但 UI 文本用"定角装填"）
- 版本号写 `V0.0140300174`（从 info_tab.py APP_VERSION 同步，禁止第二处硬编码）
- 改完手册不需要升版本号（AGENTS §6：文档/测试不算源码更新）
- 改完 HANDOVER 必跑 `py tools/audit_docs.py`


## 十二、坑速查（一行一条，都是实测过的）

**改写 / 编码类**

| 症状                                | 根因 / 解法                                                          |
| --------------------------------- | ---------------------------------------------------------------- |
| `.bat` 里含中文的 `echo` 报 "不是内部或外部命令" | 文件是 LF。cmd.exe 按 CR 分行，跟中文 / 代码页无关，`chcp 65001` 无效。改成 CRLF       |
| 用 Python 脚本按内容替换 "0 命中"           | 文件是 CRLF，而匹配串用了 `\n`。按文件实际换行符构造                                 |
| `json.load` / `ast.parse` 报非法字符   | 文件被 PowerShell `Set-Content` / `>` 写了 BOM。改用 Write 工具或 Python 脚本 |
| 文件莫名带 BOM（`ast.parse` 报 U+FEFF） | PowerShell `Set-Content` 留下的。去 BOM 用字节级操作；读文件用 `encoding="utf-8-sig"` 更稳。2026-10-13 清掉 9 个（含 `HANDOVER.md` 和 2 份 mascot 文案，后者首字符是脏的） |
| 备份体积莫名 200MB | 把 `dist/`（**135MB**）或 `.git` 一起备份了。整目录快照排除 `dist .git backups __pycache__ .pytest_cache .ruff_cache` → 约 **40MB** |
| 脚本批量替换后文件半坏                       | 没做 "预期命中 N 处" 断言。**先断言再落盘**                                      |

**界面类**

| 症状                | 根因 / 解法                                       |
| ----------------- | --------------------------------------------- |
| 列表不撑高             | 整条 stretch 链要通：最外层 `addWidget(x, 1)`，内部每一级也要  |
| 无边框分组框标题和内容叠在一起   | 必须 `margin-top: 16px`，不能 0                    |
| tab 里什么都不显示       | `QScrollArea` 忘了 `setWidget(content)`         |
| 改了控件属性但 QSS 没变    | 属性选择器要 `unpolish/polish` 才重新求值                |
| 下拉框 / 数字框的箭头显示成方块 | 用了系统原生 style。必须 `app.setStyle("Fusion")`      |
| 自定义字体没生效          | `load_custom_fonts()` 必须在**任何控件创建之前**调用     |
| 缩进五花八门            | 别自己 `QGroupBox` + 内联样式，走 `make_group_box()` |

**行为类**

| 症状                    | 根因 / 解法                                                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 热键没反应                 | ① `_register_all_hotkeys()` 漏注册；② 对应 tab 没被预创建（见第六节）；③ 改完绑定没 `reload_hotkeys()`                                          |
| 关了再开，功能是坏的            | "电闸关闭" 时没真正销毁，或 `__init__` 只在启用分支里初始化。见第三节                                                                               |
| 程序退出时崩溃（退出码非 0，但测试全过） | 悬空的事件过滤器：`installEventFilter` **不持有所有权**，临时对象会被立刻回收，QApplication 上只剩悬空指针。必须用 `wheel_filter.install_no_wheel_filter(app)` |
| 某个功能 "没保存"            | `set_xxx` 里漏了 `request_save()`（写入是防抖的，不调就不落盘）                                                                              |
| 日志文件里什么也没有 | 文件 sink 曾是 WARNING 级，INFO 全被丢弃（2026-10-13 已修为 INFO）。见八・五 |
| bbox 缓存对不上            | 删 `config/bbox_cache.json` 重启                                                                                               |
| 重建引擎后热键触发两次 / 回调重复执行 | 信号重复连接。`_init_engine` 之类必须**先无条件 disconnect 再 connect**（幂等收口），否则每次重建都多挂一个槽 |
| 标签增删后某些页的下拉里没有新标签 | 漏接 `tags_changed`，见五・五 |

**术语类**

| 名词           | 指什么                                               |
| ------------ | ------------------------------------------------- |
| 电闸 / 开关 / 暂离 | 见第三节                                              |
| 空房子 / 水泥凳子   | 配置驱动：具体功能行为必须在 cfg 里，不在代码里（AGENTS §1.2）           |
| 腰封           | 启动横幅。窗口宽度必须等于它（800px），见 8.5                       |
| 数显模块         | **已删除**。历史文档里出现的 "数显"= 现在的标定测距（`distance_meter`） |

---

## 十三、已知问题（暂不修）

| 问题 | 表现 | 原因 |
| --- | --- | --- |
| 筛选结果为空时列表空 | 筛选后当前载具不在结果集里（如 PMC 空标签），列表 currentRow=-1，但详情区仍显示 state 的载具。**这是设计取舍，不是 bug**（2026-10-14 确认）。详见 §三・五 "S1 修法的边界"。 | 设计取舍 |
| 无弹种的载具 | 倍率列表仍会 populate，各项显示空 crosshair 路径（"未绑定图片"）。 | 老问题，暂不修。 |
| 焦点在桌面时滚轮切弹种失效 | 前台为桌面（Progman/WorkerW）时滚动滚轮，弹种预选不弹出；切回任意其他窗口立即恢复。2026-10-18 日志确认：底层钩子 WH_MOUSE_LL 在桌面前台时收不到 WM_MOUSEWHEEL 事件（`[MouseHook] WHEEL` 零行），非代码 Bug。 | 无解，Windows 底层行为。使用时确保前台窗口不是桌面。 |
