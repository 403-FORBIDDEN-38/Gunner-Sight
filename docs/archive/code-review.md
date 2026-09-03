# GunnerSight 代码质量审查意见（交执行 Agent）

- 审查方：主 Agent（独立审查，不修改源码）
- 执行方：执行 Agent（负责全部修复与打包）
- 审查对象：`C:\Users\suncheng\Doubao\chats\2026-07-30\new-chat\GunnerSight\` 全部 26 个 Python 文件
- 版本：V0.0140300032
- 审查方法：vdr-code-review（全部文件逐行读完，rangefinder_tab.py 725 行已分段读全，无截断遗留）
- 决策口径：**有条件通过，可以发布**；发布前必修项见第五节，其余记为技术债

---

## 一、最终决策

**有条件通过。** 全部文件中未发现崩溃级缺陷，核心链路（状态机/热键/Overlay/角度仪/测距仪/建队宏）功能正确。发布前须完成第五节"发布必修项"，随后由执行 Agent 重新打包发布版（当前发布版滞后源码约 2 天，缺角度仪集成、settings_container 模式、布局重构等）。

修复与打包全部由执行 Agent 实施；主 Agent 不直接改源码。修复完成后回到主 Agent 复审。

---

## 二、真实缺陷（D，执行 Agent 逐项处理）

### D1〔中·发布必修〕main.py:160 版本号硬编码不一致
- 事实：`app.setApplicationVersion("1.0.0")` 写死为 1.0.0；info_tab.py:12 的 `APP_VERSION = "V0.0140300032"` 才是实际版本。
- 违反：8.2 版本号规范、3.1 单一事实源（同一版本号存在两个不一致来源）。
- 后果：QApplication 层版本（任务栏/文件属性/关于对话框可能读取）与信息页显示不一致。
- 证据等级：FACT。
- 修复约束：全程序版本号只能有一个权威来源，QApplication 与信息页必须读到同一值；修复后两处显示一致。不规定具体写法。

### D2〔低-中〕main.py:147 crash_log.txt 打包后路径可能不可写
- 事实：崩溃日志路径用 `os.path.dirname(os.path.abspath(__file__))`，PyInstaller 打包后该路径落在 `_internal` 目录，安装到 Program Files 等只读位置时写日志失败。
- 违反：错误处理不得因环境只读而二次失败。
- 后果：真正崩溃时反而无法落盘崩溃日志。
- 证据等级：INFERENCE（未在只读目录实测，但路径推导成立）。
- 修复约束：崩溃日志必须写到用户可写目录（项目已有 `get_app_base_dir()`，需核实其打包后指向，统一走同一可写根目录）。

### D3〔低〕xcj 旧命名全局残留（功能正常，纯命名问题）
- 事实：xcj 是 rangefinder 旧称，现仍贯穿——config_manager 最小骨架 `"xcj"` 配置段；hotkey_manager 信号 `xcj_measure_triggered`；rangefinder.py 模块文档串 "XCJ Rangefinder"；rangefinder_tab.py 变量 `self.xcj/self.xcj_overlay/self.xcj_overlay2` 及全部 `is_xcj_enabled/get_xcj_profile/set_current_xcj_profile` 等方法名。
- 关键确认（FACT）：本次已逐行确认 rangefinder_tab + rangefinder **确实在读写 config 的 "xcj" 段**，所以这不是"引用了不存在的模块"，而是**一次未完成的全局改名**。功能完整，不影响运行。
- 违反：3.1 统一性（同一概念两套名字增加认知成本）。
- 修复约束：如要改名，必须 config 段、方法名、信号名、变量名、配置迁移一次性全局一致改，并提供旧 "xcj" 配置段到新段名的迁移（避免老用户 config.json 失效）；若本轮不改名，保留现状但在技术债登记，禁止半改（改一半比不改更糟）。

### D4〔低〕config_manager.py:838 getter 带写盘副作用
- 事实：`get_angle_meter_profiles()` 在 profiles 为空时创建默认配置并 `request_save()`。
- 违反：getter 不应有写副作用（最小惊讶）。
- 后果：仅"读取"动作可能触发磁盘写，调用方难以预期。
- 证据等级：FACT。
- 修复约束：读取与"首次初始化默认值"分离；默认值的初始化在显式流程发生。

### D5〔低〕overlay.py:270 访问 OverlayWindow 私有成员
- 事实：`OverlayRenderer._update_crosshair()` 读 `self.overlay._current_path`。
- 违反：封装边界（不跨对象访问下划线私有成员）。
- 修复约束：被访问方提供只读公共属性，访问方走公共接口。

### D6〔低〕mouse_hook.py:179-180 钩子回调静默吞异常
- 事实：钩子回调内 `except Exception: pass`。
- 违反：5.2 第8条"异常被吞掉"。
- 说明：钩子回调禁止耗时操作，但完全静默会让钩子失效时无线索。
- 修复约束：保留回调轻量的前提下，至少留一条带前缀的轻量日志（如 print），不得阻塞钩子链。

### D7〔低〕main.py:35 用户拒绝 UAC 后静默退出
- 事实：`_request_admin()` 在用户拒绝提权后 `sys.exit(0)`，无任何提示。
- 后果：用户看到程序"没反应"，不知原因。
- 修复约束：退出前给出明确提示（需要管理员权限，已退出）。

### D8〔低-中〕rangefinder_tab.py:586-591 / 602-607 拖拽编辑定时器重复创建未清理
- 事实：`_on_drag`/`_on_drag2` 每次都 `self._edit_timer = QTimer(self)` 覆盖旧引用，未先 stop 旧定时器。
- 后果：编辑过程中再次点"拖拽定位"，旧 200ms 轮询定时器引用丢失、无法停止，可能两个定时器并存并重复触发保存。
- 证据等级：FACT（代码路径成立，重复点击触发）。
- 修复约束：创建新定时器前必须先停止并清理旧的；或复用同一定时器。修复后连续多次点击只存在一个活动定时器。

### D9〔低〕rangefinder_tab.py:723-724 关闭等待超时无兜底
- 事实：shutdown 中 `self._measure_thread.wait(1000)` 最多等 1 秒，超时后无日志、无确认 BlockInput 已恢复，直接继续 `_shutdown_xcj()` 关闭引擎。
- 后果：测距线程若 1 秒未退出，会在引擎 close 后仍访问它；正常有 abort 标志会快速返回，故风险低。
- 证据等级：INFERENCE。
- 修复约束：wait 超时分支必须有明确处理（日志 + 确认输入状态 BlockInput 已恢复），不能静默继续。

---

## 三、架构风险（A，不阻塞发布，评估是否本轮处理）

- A1 state_machine.py:23-25 每次启动强制 overlay_visible=True，config 中该字段启动时被覆盖、实际不被读取。需明确这是"每次启动默认显示"的设计还是缺陷；若用户关闭准星的偏好应被记住，则为缺陷。
- A2 config_manager.py:735-799 当前载具/弹种/倍率 setter 不 request_save，每次启动回到第一个载具。同上，需明确是否为有意设计。
- A3 角度仪热键为单键结构（key/trigger），其余热键为双键结构（key1/trigger1/key2/trigger2），两套模型增加维护成本，且角度仪不支持双键组合。
- A4 config_manager.py 907 行承担 8 类配置（载具/弹种/倍率/热键/xcj/建队宏/角度仪/主题），职责过多，后续可按 vdr-refactor 按职责拆分（模块≠文件）。
- A5 rangefinder_tab.py 725 行，承担 UI 切换+测距引擎+双 ROI+结果显示+配置 CRUD+关联载具+双 Overlay，职责过多（同 A4，后续拆分）。
- A6 overlay.py:44 `_pixmap_cache` 无上限，而 `_scaled_cache` 有 50 项上限，策略不一致；当前仅 36 张图不会溢出。
- A7 angle_meter_tab.py:17 `AngleOverlay` 类定义在 tab 文件内，宜独立到 gui/。

---

## 四、技术债（T，登记，给明确上限/升级路径）

- T1 xcj→rangefinder 全局改名（与 D3 同源，若做须一次性一致改 + 配置迁移）。
- T2 angle_meter.py `RawInputReader` 继承 QWidget 仅为拿 winId()，纯输入源不应是 UI 组件。
- T3 Win32 调用入口不统一：win32_utils/rangefinder/squad_macro 用 `ctypes.windll.user32`，mouse_hook 用独立 `ctypes.WinDLL('user32', use_last_error=True)`，应统一。
- T4 config_manager.py 大量 setdefault 链式调用，可读性差。
- T5 rangefinder_overlay.py:52 POINT 结构体内定义于方法，应提至模块级。
- T6 squad_macro.py:56 WNDENUMPROC 每次 find_game_window 重复创建，应模块级。
- T7 rangefinder.py `quick_toggle_ui` 独立函数与 `RangefinderEngine.toggle_ui` 方法功能重叠，应合一。
- T8 rangefinder_tab.py:593-599/609-614 用 200ms 轮询读 overlay 私有 `_edit_mode`，违反 5.4 事件驱动优先；应由 RangefinderOverlay 提供 edit_mode_changed 信号（同时消除 D5 同类私有访问）。
- T9 rangefinder_tab.py 魔法数字 150ms(664)/200ms(轮询)/1000ms(wait) 无注释，需说明取值依据。
- T10 rangefinder_tab.py:621-635 两处"双键相同清空 key2"逻辑重复，提取共享函数。
- T11 rangefinder_tab.py:460 直接操作 `link_vf.list` 内部控件，绕过公共接口（对比 angle_meter_tab 用 populate()），应走 VehicleFilterWidget 公共方法。

---

## 五、发布必修项（执行 Agent 打包前完成，后主 Agent 复审）

1. D1：统一版本号唯一权威来源，QApplication 与信息页一致。
2. 重新打包发布版，同步源码近 2 天全部改动（角度仪集成、settings_container、布局重构等），并核对发布版 config.json 与源码版结构兼容（走配置迁移）。
3. 建议本轮一并处理 D8（定时器泄漏，成本低、路径明确）；D2/D9 涉及打包与关闭健壮性，建议同批。其余 D4-D7、A、T 可记入后续迭代。

---

## 六、已排除的疑点（避免执行 Agent 误改，FACT）

- rangefinder_tab.py:679-685 `QImage(data,...)` 中 data 为局部 bytes：`QPixmap.fromImage` 在同一同步调用栈内立即深拷贝像素，data 在拷贝完成前始终存活，**无引用悬空，非缺陷**，禁止当作 bug 重写。
- rangefinder_tab.py:668 每次测距 new MeasureThread：测距是低频手动热键，且有 `_measuring` + `isRunning()` 双重防重入，可接受，非缺陷。
- squad_macro.py `alt_tab()`：经核实在 squad_macro_tab.py:184 `_switch_to_game` 中被调用，**不是墓碑代码**，禁止删除。

---

## 七、值得保持的优点（修复时不得破坏）

mouse_hook 引用计数+64位类型安全+回调只转发；hotkey 严格边沿检测；overlay 双缓存且缩放缓存有上限；config 500ms 防抖保存+跨版本迁移；angle_meter 输入/校准数据/状态机/校准流程分层清晰；细粒度信号避免全量刷新；resource MD5 去重；可选模块常闭零消耗 + settings_container 统一禁用；关闭时先 hide 再后台清理实现瞬关。

---

## 八、执行 Agent 回复格式要求

逐项回复：编号 → 处理结果（已修复/不采纳并说明理由/延期并登记技术债）→ 修改文件与行号 → 自验方式与结果（PASS/FAIL/UNKNOWN）。不允许只回"已修复"而不给位置和验证。

---

# 第二轮：第一轮修复独立复审 + 源码版全量修复交办

## 九、第一轮修复独立复审（主 Agent 亲自读源码/查产物，未采信汇报文字）

| 项 | 复审结论 | 独立证据（主 Agent 亲验） |
|---|---|---|
| D1 版本号 | **PASS** | info_tab.py:12 源头 `APP_VERSION="V0.0140300032"` 正确；main.py:12 导入、main.py:165 `setApplicationVersion(_APP_VERSION.lstrip("V"))` 与之同源；信息页带 V、QApplication 去 V 为点分版本，合理 |
| D2 crash_log 路径 | **有条件 PASS（须加固，列入批次1）** | main.py:150-152 确实改用 get_app_base_dir()；但读 config_manager.py:16-31 实现发现：frozen 时仅当 **exe 同级已存在 config 目录**才返回 exe 同级，否则回退 `_internal`，都没有才 return exe_dir。**首次启动、config 目录尚未建立时崩溃（如 QApplication/字体阶段），仍会回退只读目录**。当前 onefile 打包恰好不存在 _internal 目录，靠第29行兜底才成立——结论依赖打包方式这一前提，并非真正健壮 |
| D8 定时器泄漏 | **PASS** | rangefinder_tab.py:591-594、611-614 新建 QTimer 前先 stop()+deleteLater() 旧定时器，逻辑成立 |
| D9 关闭超时兜底 | **PASS** | rangefinder_tab.py:2 已 `import ctypes`；733 捕获 wait 返回值，735-741 超时打印带前缀日志并 BlockInput(False) 恢复输入；恢复调用再包 try/except 防止中断关闭，可接受 |
| 重新打包 | **结构 PASS / 运行时 UNKNOWN** | 主 Agent 用文件系统独立核实 GunnerSight_Release 含 GunnerSight.exe + config/config.json + resources（准星/fonts/mascot/app_icon.ico 共50项）+ README，无 _internal，证实 onefile。**但 exe 能否真正启动属运行时行为，当前审查环境无法独立启动 GUI 验证，执行方自称"PID 验证"对主 Agent 是 UNKNOWN**——需执行方按 7.3 提供启动日志或现场复现 |
| 新发现 N1 | 技术债 | main.py:49 顶层已导入 get_app_base_dir，main.py:151 except 内又局部导入一次，冗余，批次1顺手清理 |

复审小结：D1/D8/D9 独立验证通过；D2 不接受"已修复"表述，降级为有条件 PASS 并要求批次1加固；打包运行时启动为 UNKNOWN，待补证据。**本轮验证证明：只看汇报会漏掉 D2 的首次启动盲区——独立走路径是必要的。**

## 十、第二轮交办：在源码版修复全部剩余已知问题（用户要求"全部修复"）

执行范围：**源码版 `GunnerSight/`**（不是发布版）。按批次顺序做，**每批完成按 AGENTS.md 7.2 格式交付、回主 Agent 复审通过后再进下一批**，禁止一次性全改后统一交付（无法审查）。所有改动遵守：病灶根源、统一性、配置迁移不丢老用户数据、高频路径零全量刷新。

### 批次1｜健壮性与一致性（低风险，先做）
- **D2 加固**：崩溃日志路径在 frozen 时直接取 `Path(sys.executable).parent`（exe 同级，可写），不经过"config 目录是否存在"的判断；或新增不依赖 config 已建的可写目录函数。修复后须能解释：首次启动 config 未建时崩溃，日志落在何处。
- **D4**：`get_angle_meter_profiles()` 读取与"首次创建默认并写盘"分离，getter 无写副作用。
- **D6**：mouse_hook 钩子回调异常不得 `pass` 静默，加带 `[MouseHook]` 前缀轻量日志，保持回调非耗时。
- **D7**：用户拒绝 UAC 后先弹提示/打印"需要管理员权限，程序退出"再 sys.exit。
- **A6**：overlay `_pixmap_cache` 加上限（与 `_scaled_cache` 一致策略）。
- **T9**：150/200/1000ms 提为命名常量并注释取值依据。
- **N1**：删 main.py:151 冗余局部 import。

### 批次2｜命名统一 + 热键模型统一（中风险，均含配置迁移，合并一次做透）
- **D3/T1（xcj→rangefinder 全局改名）**：config 段名、config_manager 方法名（is_xcj_*/get_xcj_* 等）、hotkey 信号 `xcj_measure_triggered`、rangefinder/rangefinder_tab 内 self.xcj* 变量与模块文档串，一次性全部改，**禁止半改**。必须写旧 `"xcj"` 段到新段的自动迁移，老 config.json 升级不丢配置。
- **A3**：角度仪单键热键结构与全局双键结构统一（或抽出统一热键模型），旧单键配置自动迁移到新结构。
- **T3**：统一 Win32 user32 加载入口（mouse_hook 的独立 WinDLL/use_last_error 与其余模块的 ctypes.windll.user32 收敛为一种），先论证 last_error 是否必须保留再定方案。

### 批次3｜封装与事件驱动（中风险）
- **D5+T8**：OverlayWindow/RangefinderOverlay 提供公共 `current_path` 属性与 `edit_mode_changed` 信号；OverlayRenderer、rangefinder_tab 不再访问 `_current_path`/`_edit_mode`；删除两个 200ms 轮询定时器，改信号驱动（符合 AGENTS 3.4 事件驱动优先）。
- **T11**：rangefinder_tab 不再直接操作 `link_vf.list`，给 VehicleFilterWidget 补公共方法（对齐 angle_meter_tab 的 populate）。
- **T7**：`quick_toggle_ui` 与 `RangefinderEngine.toggle_ui` 重复实现合一。
- **T10**：两处"双键相同清空 key2"提取为一个共享函数。
- **T5/T6**：POINT 结构体、WNDENUMPROC 回调提至模块级，不在方法/每次调用时创建。

### 批次4｜用户选择跨启动持久化（中风险；主 Agent 判定，用户可否决）
- **A1**：overlay_visible 启动时按 config 恢复，不再无条件强制 True。
- **A2**：当前载具/弹种/倍率 setter 持久化，启动恢复上次选择。
- 统一本质：配置软件应记忆用户上次会话选择。若产品意图确为"每次启动默认"，由用户明确后回退，执行方不自行决定。

### 批次5｜内部结构重构（高风险，行为严格保持；建议评估后单独排期）
- A4 config_manager 按职责拆分、A5 rangefinder_tab 拆分、A7 AngleOverlay 独立出 tab 文件、T2 RawInputReader 去除 QWidget 继承（改为外部注入句柄/独立持有）、T4 setdefault 链可读性。
- **硬约束**：纯内部结构调整，对外公共接口与一切用户可观察行为保持不变；禁止借重构改行为；完成后全功能回归（8 个导航页 + 热键 + overlay + 角度仪 + 测距 + 建队宏）。
- **主 Agent 专业意见（供用户决策）**：本批只提升架构整洁度、回归面最大，按 Ponytail/YAGNI，稳定工作的代码不为"更漂亮"而大动；建议作为独立重构任务，不阻塞批次1-4 的缺陷与一致性修复。是否纳入本轮由用户拍板，执行方不擅自启动。

## 十一、本轮交付与验证要求
1. 每批交付：逐项编号 → 处理结果 → 文件:行号 → 自验（语法 py_compile + 启动冒烟，功能结论留主 Agent）。
2. 批次2 必须额外交付：用一份旧 config.json（含 xcj 段、单键角度仪热键）实测迁移后的结果，证明无丢字段。
3. 打包运行时启动（上轮 UNKNOWN 项）：在最终批次后提供一次干净环境启动证据（进程存活 + 无 crash_log + 主要页面可打开）。
4. 任何一项做不到或发现新问题，写入 change-request.md，不许静默跳过。

---

# 第三轮：批次1独立复审 + 发布收尾要求

## 十二、批次1独立复审（主 Agent 逐项读改后源码，未采信"7/7 PASS"汇报）

| 项 | 复审结论 | 独立证据 |
|---|---|---|
| D2 加固 | **PASS** | main.py:156-160 frozen 时直接 `dirname(sys.executable)`（exe 同级），不再经过 config 存在性判断，首次启动 config 未建的盲区已消除。残余前提：exe 同级须可写——绿色单文件软件成立；若装 Program Files 只读目录仍受限，此极端场景不覆盖，可接受 |
| D4 | **PASS（附 1 处去重建议）** | config_manager.py:66 __init__ 调 `_ensure_angle_meter_defaults()`、836-847 仅内存补全不写盘、858-860 getter 已纯读取，写副作用消除。**新小瑕疵 R1**：angle_meter 默认结构在 `_get_minimal_skeleton`(89-93) 与 `_ensure_angle_meter_defaults`(841-847) 写了两遍相同字面量，改默认值要改两处，违反统一性，应提取为一个共享默认工厂 |
| D6 | **PASS** | mouse_hook.py:172-173、179-180 两处 except 均改为带 `[MouseHook]` 前缀 print；关键是 181 行 `CallNextHookEx` 在 try/except 之外无条件执行，异常不会中断钩子链，正确 |
| D7 | **PASS** | main.py:27/35 frozen 与 dev 两分支都给 ret 赋值，37-40 `ret<=32` 与异常路径都打印明确提示后再 sys.exit，逻辑闭合 |
| A6 | **FAIL，打回重做** | 见下"打回项①"，上限保护放错分支，属真实逻辑缺陷 |
| T9 | **替换到位，但 1 处日志 bug，打回顺手修** | 601/621 用 EDIT_POLL_INTERVAL_MS、678 用 MEASURE_DELAY_MS、738 用 SHUTDOWN_WAIT_MS，裸数字已消除；但 741 行把常量名写进了字面字符串 |
| N1 | **部分完成，补漏** | get_app_base_dir 局部导入已删；但 main.py:152 `import traceback` 与文件顶部第 9 行重复，漏删 |

### 打回项（修正后只需回读这几点，不必全量复审）

**① A6 缓存上限位置错误（真实缺陷，必修）**
- 现状：上限检查在 overlay.py:94 的**读命中分支**内；而真正写入缓存是在 115 行（cache miss 加载成功后），写入处**没有任何上限检查**。
- 后果链（FACT，代码路径推演）：
  1. 新图走 99→115 写入，从不检查长度 → 缓存仍可无限增长，A6 想防的问题在写入路径上没被拦住；
  2. 一旦数量超过 50，每次"命中"都执行 `_pixmap_cache.clear()` 清空**包括当前项在内的全部缓存**，当前帧靠局部变量勉强显示，其余图下次全部重新读盘——造成缓存抖动（thrashing），与缓存目的相反。
- 当前 36 张图永远到不了 51，所以启动冒烟 PASS 是假象，问题被数据量掩盖。
- 修复约束：把上限判断移到**第 115 行写入之前**（`if len(cache) >= max: cache.clear()`，再写入当前项，保证当前项一定在缓存中）；删除第 94 行命中分支里的 clear（命中路径只读不清）。_scaled_cache 也按同一正确模式核对一遍。

**② 741 行日志常量名当字面量**：`print("...超时(SHUTDOWN_WAIT_MS ms)...")` 会原样打印常量名而非数值，改为 f-string `...超时({SHUTDOWN_WAIT_MS}ms)...`。

**③ main.py:152 删重复 `import traceback`**（顶部第 9 行已有）。

**④ R1 默认结构去重**：提取 angle_meter 默认 profile/段为单一共享工厂，最小骨架与 ensure 都调用它，禁止两份字面量。

**批次1总结论：D2/D4/D6/D7 独立验证通过；A6 打回（位置错误），连同②③④修正后回读即可，通过后批次1关闭、进入批次2。**

## 十三、发布收尾交办（版本号 / 版本资源信息 / 数字签名）

### 13.1 版本号递增（用户点名）
- 唯一权威来源仍是 info_tab.py 的 APP_VERSION；批次1-4 每批改动后按 AGENTS 8.2 规范递增更新次数（当前 V0.0140300032，下一次为 V0.0140300033，以此类推），最终发布版本以收尾时为准；main.py 自动同源，禁止出现第二处写死版本。

### 13.2 exe 版本资源信息（免费、必做，解决"属性页空白/像个人打包"）
- 现状：PyInstaller 默认不写 Windows 版本资源，exe 右键→属性→详细信息为空，这正是别人说"个人打包、无版本信息"的来源之一，**它和数字签名是两回事**。
- 交办：生成 PyInstaller version 资源文件（VSVersionInfo），至少填：文件版本/产品版本（与 APP_VERSION 同源）、产品名 GunnerSight Overlay、公司名/署名 **403 FORBIDDEN**、版权、原始文件名 GunnerSight.exe；在 GunnerSight.spec 的 `version=` 挂载，重新打包后核对属性→详细信息页完整。

### 13.3 数字签名（用户已决策：自签名，署名 403 FORBIDDEN）

**决策**：不购买 CA 证书；用本机自签名代码签名证书给最终 exe 签名，目标是**任何电脑上 exe 属性→"数字签名"页都能看到签名者 403 FORBIDDEN**。

**边界（必须知晓，已向用户确认）**：自签名在他人电脑上证书状态为"不受信任的颁发者"，**不消除 SmartScreen"未知发布者"拦截、不获得系统信任**；本次只追求"签名存在、署名正确显示"，不追求可信。禁止尝试伪造受信任根、把自签证书塞进对方受信任根存储等绕过行为。

**执行步骤（执行 Agent 在用户机器操作，普通权限即可，无需管理员；优先用 PowerShell 内置 cmdlet，免装 Windows SDK）**：

1. 创建代码签名自签证书（有效期取 10 年，避免明年显示过期），存当前用户存储：
```powershell
New-SelfSignedCertificate -Type CodeSigningCert `
  -Subject "CN=403 FORBIDDEN" `
  -KeyUsage DigitalSignature -KeyAlgorithm RSA -KeyLength 2048 `
  -HashAlgorithm SHA256 -FriendlyName "GunnerSight Code Sign" `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -NotAfter (Get-Date).AddYears(10)
```
记录返回的 Thumbprint；证书留在 CurrentUser\My 供以后重签复用，无需导出 pfx、不随 exe 分发。

2. **顺序铁律：先打包出最终 exe（含 13.2 版本资源）→ 再对成品签名**。签名后任何字节改动都会使签名失效，故签名必须是打包完成后的最后一步；若重新打包必须重签。

3. 对最终 exe 签名（优先 Set-AuthenticodeSignature，不依赖 signtool/SDK；带时间戳更规范）：
```powershell
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -match "403 FORBIDDEN" } | Select-Object -First 1
Set-AuthenticodeSignature -FilePath ".\GunnerSight.exe" `
  -Certificate $cert -HashAlgorithm SHA256 `
  -TimestampServer "http://timestamp.digicert.com"
```
（若执行环境无 Set-AuthenticodeSignature，再退而用 Windows SDK 的 signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256，并先定位 signtool.exe 实际路径。）

4. 同步到 GunnerSight_Release 的必须是**已签名的最终 exe**。

### 13.4 主 Agent 复审验收标准（执行 Agent 须提供证据）
- **版本资源(②)**：exe 属性→详细信息页字段齐全——产品名 GunnerSight Overlay、公司/署名 403 FORBIDDEN、文件版本/产品版本与 APP_VERSION 同源、版权、原始文件名 GunnerSight.exe。可用 PowerShell `(Get-Item .\GunnerSight.exe).VersionInfo | fl *` 输出佐证。
- **数字签名(③)**：`Get-AuthenticodeSignature .\GunnerSight.exe` 输出中 `SignerCertificate.Subject` 含 `CN=403 FORBIDDEN`、签名算法 SHA256、TimeStamper 非空；属性页出现"数字签名"标签且签名者显示 403 FORBIDDEN。
- **预期现象不是失败**：自签名的 `Status` 会是 UnknownTrust/NotTrusted（本机未把自签证书加入受信任根时），这是自签的**正常预期**，验收只看"签名存在 + 署名正确 + SHA256 + 有时间戳"，**不要**因为 NotTrusted 就反复重签。
- 可选（仅本机去红字，不影响他人、不要求、不随分发）：若用户希望本机属性页不显示不受信任，可把该证书公钥导入 CurrentUser 的 `Root` 与 `TrustedPublisher`；是否做由用户决定，执行 Agent 不擅自导入。
- **状态辨析（执行 Agent 不得混淆）**：自签名、证书未导入受信任根时，`Get-AuthenticodeSignature` 的正常状态是 **NotTrusted / UnknownTrust**；若报的是 **UnknownError**，这**不是**预期结果，通常意味着时间戳未取到（时间戳服务器连不上）、签名后文件被改动或证书 KeyUsage 异常。出现 UnknownError 必须贴出完整输出（Status / StatusMessage / SignerCertificate.Subject / TimeStamper）排查到 NotTrusted 为止，禁止把 UnknownError 当作"自签正常"一笔带过。

---

# 第四轮：发布执行交办（用户已定 onedir）+ 发布前终审清单

## 十四、发布执行（用户决策：打包模式改 onedir，然后发布）

### 14.1 打包模式切回 onedir（用户拍板，覆盖之前的 onefile）
- spec 改为 onedir 结构：`EXE()` 不再吞 `a.binaries/a.datas`，其后新增 `COLLECT(exe, a.binaries, a.datas, ...)`；产物为 **GunnerSight.exe + `_internal/`**（依赖在 _internal 内）。
- **用户数据外置、不重复打包**：`config/`、`resources/` 是用户可直接修改的数据，放在 **exe 同级**；源码 `core/`、`gui/` 等程序依赖打进 `_internal/`。重新核对 spec 的 `datas`，禁止 config/resources 既打进 _internal 又在 exe 同级放一份（两份会产生"改了不生效/不知读哪份"的优先级问题）；如需要出厂默认，只在内部留一份种子并明确首次复制逻辑。
- **get_app_base_dir() 随 onedir 对齐**：onedir 下 exe 同级确实存在 `_internal/`，必须保证优先读写 **exe 同级外置 config**（用户数据），绝不能把用户配置写进 `_internal/`；D2 的 crash_log 仍固定写 exe 同级、不依赖 config 是否已建。
- 最终发布目录结构：
```
GunnerSight_Release/
├── GunnerSight.exe      （onedir 主程序，签名对象）
├── _internal/          （程序依赖，用户不动）
├── config/config.json  （外置用户配置）
├── resources/          （外置准星/字体/吉祥物等）
└── README.md
```

### 14.2 版本信息（version_info.txt）
- 版本唯一权威来源仍是 info_tab 的 APP_VERSION，version_info 由它派生，**禁止第二处手写版本号**导致下次漂移；FileVersion 受 Windows 约束用四段数字（如 0.1.4.35），ProductVersion 用 APP_VERSION 原文，二者映射关系在交付说明写清。
- Comments 可选（一句中性项目简介）；不得填 LegalTrademarks（无注册商标）、PrivateBuild/SpecialBuild（正式版不用）。

### 14.3 签名（onedir）
- onedir 个人分发**只签主程序 GunnerSight.exe**，_internal 内 dll 不必逐个签。
- 顺序：spec 打包出最终 onedir → 对最终 exe 自签名（CN=403 FORBIDDEN, SHA256, 带时间戳）→ 签名后不得再改 exe，改了必须重签。
- 把 UnknownError 排查到 **NotTrusted**（自签预期状态）为止，交付完整 Get-AuthenticodeSignature 输出。

### 14.4 批次边界纠偏（重要）
- 执行 Agent 汇报"按第十节批次 1-5 执行"有误：**批次 5（A4 config_manager 拆分 / A5 rangefinder_tab 拆分 / A7 / T2 / T4）本轮禁止做，已单独立项**。交付时须明确确认这些大重构**未被改动**；若已误改，回退。
- 本轮范围仅：批次1打回项 + 批次2 + 批次3 + 批次4 + 本节发布收尾。

### 14.5 发布前终审证据清单（最终代码定型后一次性交付，主 Agent 独立终审，通过才允许发布）
1. **批次1打回项**：A6 缓存上限检查已移到"写入前"（贴 overlay.py 行号与代码，证明命中分支不再 clear、写入前超限先清再写当前项，_scaled_cache 同法）；741 日志改 f-string；main.py 重复 import traceback 已删；R1 angle_meter 默认结构单一工厂、无两份字面量。
2. **批次2**：全局 grep 证明无 xcj 残留（config 段/方法/信号/变量/文档串）；**用一份含旧 xcj 段 + 单键角度仪热键的旧 config.json 实测迁移**，贴迁移前后对比，证明字段不丢、程序正常读取；角度仪热键并入统一双键模型且旧配置自动迁移；Win32 user32 加载入口统一。
3. **批次3**：rangefinder_tab 不再访问 `_edit_mode/_current_path` 私有成员、200ms 轮询已改为 edit_mode_changed 信号驱动；link_vf 走公共接口；quick_toggle_ui/toggle_ui 合一；双键清空逻辑去重；POINT/WNDENUMPROC 提模块级。
4. **批次4**：overlay_visible、当前载具/弹种/倍率改为持久化，贴"修改→关闭→重启→恢复"的验证结果。
5. **质量门**：全部 .py 通过 py_compile；启动冒烟；8 个导航页 + 热键 + overlay + 角度仪 + 测距 + 建队宏回归无 REGRESSION。
6. **发布产物**：onedir 目录结构符合 14.1；外置 config/resources 读写正确（不写 _internal）；`VersionInfo | fl *` 字段齐全；`Get-AuthenticodeSignature` 状态 NotTrusted、署名 CN=403 FORBIDDEN、SHA256、时间戳非空。
7. 最终 APP_VERSION 值与本次递增记录。

**主 Agent 终审方式**：独立读取上述关键改后源码、抽查旧配置迁移、核对发布目录实体与版本/签名输出；汇报文字仅作线索，结论以主 Agent 亲验为准。任一项不达标即打回，不得带问题发布。

---

# 第十五节：发布前独立终审结论（主 Agent 亲验，非采信汇报）

## 15.1 已逐项 PASS（主 Agent 直接读改后源码核实）
- **A6**：overlay.py:118-120 上限判断在"写入前"（先 clear 再写当前项），命中分支 96-99 只读不清；_scaled_cache 217-219 同法。上轮打回项真实修复。
- **D2**：main.py:155-159 frozen 崩溃日志固定 exe 同级，不依赖 config 存在；get_app_base_dir config_manager.py:16-23 frozen 始终 exe 同级、不回退 _internal，符合 onedir。
- **D4/R1**：getter 纯读取（898-900）；默认结构统一走 _default_angle_meter_profile/_segment 工厂（26-42、885/887/903/912），无两份字面量。
- **D5/T8**：overlay 提供 current_path 公共属性（61-64），外部不再碰 _current_path；rangefinder_overlay edit_mode_changed 信号（:18）退出编辑时发射（:38）；rangefinder_tab _on_drag/_on_drag2 先 disconnect 防重复再 connect（589-592/608-611），_on_edit_finished 用 overlay.x()/y()/width()/height() 公共方法回写，**全文件已无 _edit_timer/_edit2_timer/EDIT_POLL_INTERVAL、无 _edit_mode 私有访问**，200ms 轮询真实删除；shutdown 728-744 断信号 + wait(SHUTDOWN_WAIT_MS) + f-string 超时日志 + BlockInput(False) 兜底。
- **T3**：user32 统一由 win32_utils 导出；main.py 残留 windll 仅 shell32（IsUserAnAdmin/ShellExecuteW 提权，不在 user32 统一范围，合理）；mouse_hook 走 `from core.win32_utils import user32`。
- **T5**：POINT 提模块级（rangefinder_overlay:12-14）。**T10**：_normalize_hotkey_pair 静态共享（621-627），两处调用。
- **批次2迁移（最高风险项，静态走读通过）**：_migrate_xcj_to_rangefinder（142-155）旧段在/新段无→整体搬迁删旧；新旧并存→删旧保新（不覆盖新配置）；无旧段→不动。_migrate_angle_meter_hotkeys/_migrate_ammo_hotkeys 以 `"key" in hk and "key1" not in hk` 为判据，旧 key→key1、key2 留空，可防重复迁移。迁移在 load_config 后按序执行（73-79），逻辑上不丢字段。
- **A3**：全局/弹种/角度仪热键统一双键 slot 模型（747-758、956-963）。
- **A1**：state_machine:23-25 每次启动强制准星开启、不继承上次，注释记录用户决策，符合裁定。**A2**：current_state 属 config，运行时改内存、main_window.closeEvent:382 统一 save_config 落盘，重启恢复，成立。
- **版本**：info_tab APP_VERSION=V0.0140300036 唯一来源，version_info filevers(0,1,4,36)/ProductVersion 一致，main.py 由其导入，无第二处手写。
- **onedir**：spec 为 EXE+COLLECT、datas 仅 gui/core；发布目录为 exe+_internal+外置 config/resources+README，结构正确。
- **签名**：StatusMessage 原文 "chain…terminated in a root which is not trusted" + 临时导入根变 Valid 的对照，证实签名本身成立、UnknownError 即自签 NotTrusted；署名 CN=403 FORBIDDEN、SHA256、DigiCert 时间戳非空。认可。

## 15.2 打回（不得带问题发布）
- **P1〔必改·用户可见残留〕info_tab.py:35**：信息页描述仍写"外置信息数显(**XCJ**)"——大写 XCJ 漏网（执行方仅 grep 小写 xcj 就断言"无残留"，该结论不成立）。改为"信息数显/外置信息数显（测距）"等不含旧缩写的措辞。**改后必须全局 `grep -i xcj` 复查（忽略大小写），源码中除迁移方法识别旧字段外不得再有任何 xcj/XCJ（含 UI 文案、注释、文档串）。**
- **P2〔本次顺手·发布整洁度〕_internal 混入 __pycache__**：发布包 `_internal/core/__pycache__`、`_internal/gui/__pycache__`、`_internal/gui/tabs/__pycache__` 是 spec datas 整目录拷贝带入的 .pyc 缓存，冗余且不专业。打包前清理源码树 __pycache__（或 spec 排除 .pyc），重新打包后发布目录不得含 __pycache__。
- **P3〔提示·不阻塞〕**：源码目录残留 dist/ 构建中间产物（其中是旧副本，易干扰 grep），可清理；不影响 GunnerSight_Release。

## 15.3 UNKNOWN（主 Agent 本会话无法运行，如实声明）
运行时项（26 文件 py_compile、启动冒烟、8 页/热键/overlay/角度仪/测距/建队宏回归、**拿一份含 xcj 段+单键角度仪热键的旧 config.json 真实迁移一次**）主 Agent 命令通道不可用、未能亲跑，结论基于静态走读：静态层面未发现会导致失败的缺陷。执行 Agent 须补"旧 config 实跑迁移"的结果（迁移前后字段对比 + 程序正常读取）作为最终凭证，不得只贴"代码看起来对"。

## 15.4 放行条件
P1 改文案 + 全局忽略大小写复查无残留、P2 重新打包且发布目录无 __pycache__；因动源码，APP_VERSION 036→**037**（唯一来源），version_info 同步，重新 onedir 打包后**对新 exe 重签名**（签名在最后）。完成后主 Agent 只回读 ①info_tab 文案与 grep -i 结果 ②发布目录无 __pycache__ ③版本037/签名输出，三点过即放行发布，不再全量重审。

---

# 第十六节：用户实测回归 + 新需求（发布前必修，与 P1/P2 合并为 037）

> 性质：以下多为批次2/3 重构引入的**运行时回归**——主 Agent 静态走读未跑程序、用户实测才暴露，印证 15.3 的 UNKNOWN。先修这批再发布。

## 16.1 〔根因级·最高优先〕配置迁移与骨架合并顺序错误，导致旧配置"该迁的没迁、该留的被删"
**根因机制（FACT，已读源码与真实 config.json 坐实）**：`__init__` 顺序是 建最小骨架(含新结构空键) → `load_config._merge_config` 把骨架新键递归合并进用户旧数据 → 才跑各 `_migrate_*`。于是旧数据里"旧键 key"与"骨架补的空新键 key1"**同时存在**：
- `_migrate_angle_meter_hotkeys`/`_migrate_ammo_hotkeys` 判据是 `"key" in hk and "key1" not in hk`——合并后 key1 已存在（空），判据恒 False，**迁移被跳过**。真实 config 861-894 行：angle_meter 的 reset/pause/calibrate/toggle 旧键 `mouse_left/f8/f6/f7` 仍在、key1 全空 → **角度仪热键实际失效**。
- `_migrate_xcj_to_rangefinder` 的"新旧并存删旧"分支：骨架先补了空 rangefinder 段，用户真实数据在旧 xcj 段，合并后并存 → 走 152-155 行**删掉有数据的 xcj、保留空 rangefinder**。真实 config 896-909 rangefinder.profiles={}、已无 xcj 段 → **信息数显配置/列表/关联载具被清空**。

**修复约束（治根，非补丁）**：
1. 统一修三个迁移方法（crosshair_paths/ammo/angle_meter/xcj），迁移判据改为**按值判定**而非"新键是否存在"：旧键有值且新键为空才搬（`if hk.get("key") and not hk.get("key1"): key1=key; trigger1=trigger`），搬完删除遗留旧键 key/trigger；推荐更彻底的顺序——**先对 loaded 原始数据做迁移，再与骨架合并补默认**，避免骨架新键污染旧格式判定。两案择一，但必须对"旧键+空新键并存"和"纯旧格式"两种输入都正确。
2. xcj 并存分支改为：**新 rangefinder.profiles 为空且旧 xcj 带数据时把数据搬入**；仅当新段确有用户数据时才删旧，禁止无脑删旧。
3. 一次性数据抢救：对当前这份真实 config，把 angle_meter hotkeys 残留的 key/trigger 正确迁入 key1/trigger1（恢复 f6/f7/f8/mouse_left 绑定）并清掉旧键。

## 16.2 〔控件根因〕热键绑定框"右键清除"失效，提示与行为不一致
**根因（widgets.py HotkeyLineEdit）**：mousePressEvent:66 右键清除被 `and self._capturing` 门控——只有先左键进入捕获态再右键才清；用户对**已绑定**框直接右键时 _capturing=False，走 super 无反应，只剩 keyPressEvent:75 的 ESC（捕获态）能清，而 :93 文案写"(右键清除)"。**修复：右键在捕获/非捕获态都清除当前绑定（非捕获态右键直接清空已绑定值），保留 ESC 作捕获态取消；改的是共享控件，所有热键框同时生效，不要逐页打补丁。** 文案与行为对齐。

## 16.3 〔UI 回归〕两个热键框功能标签丢失
HotkeyPairWidget 本身支持 label_text（widgets.py:124/130），但 rangefinder_tab 实例化没传：:72 `HotkeyPairWidget()` 补 "UI切换"、:116 补 "信息截取"。**并排查其他页面所有 HotkeyPairWidget() 实例化，漏传功能名的一并补齐。**

## 16.4 〔新需求·vdr-feature〕弹种按创建顺序自动预填数字热键
**本质需求**：弹种切换键天然就是 1/2/3/4…，免去"建弹种→再跑热键页逐个绑"的重复劳动。行为约束：
1. 落点在 `ConfigManager.add_ammo_type`（创建弹种处，当前 616-619 给空热键），由 vehicle_config_tab._on_add_ammo 链路触发。
2. 新建弹种且其**尚无热键**时，按该载具内弹种创建序号预填主键区数字：第1个→"1"…第9个→"9"，写 key1、trigger1="keydown"、key2 空。
3. **只预填默认、绝不覆盖已存在绑定**；目标数字已被其他弹种占用则顺延到下一个空闲数字；超过 9 / 无空闲则留空；用户之后可在热键页自由改；删除弹种不自动重排其余键（避免覆盖用户手改）；重命名跟随。
4. **键名字符串必须与 hotkey_manager 的识别格式完全一致**（先读其按键命名/ get_key_name 规则再填，禁止填了系统识别不了）。
5. 现有已存在但热键为空的弹种不在本次自动回填范围内（只对"新建"生效），除非用户另行要求批量补。

## 16.5 数据丢失须如实告知，不得假装恢复
- 角度仪热键：可从当前 config 残留旧键抢救（见 16.1.3）。
- 信息数显 rangefinder profiles：当前已空、目录下**无 .json.corrupt 备份、发布版 config 同样为空**；若执行 Agent 找不到其他可恢复副本，必须明确告知"这部分需用户重建"，禁止虚构恢复结果。

## 16.6 回归与发布（合并 15.2）
用这份真实 config 实跑并贴证据：①迁移后角度仪 4 个热键正确恢复显示且可用；②信息数显新建配置→保存→**重启仍在**（验证不再被迁移清空）；③右键在非捕获态可清已绑定、ESC 捕获态可取消，提示一致；④"UI切换/信息截取"标签显示；⑤连续新建 ap/he/coax/smk 热键页自动出现 1/2/3/4 且可改、冲突顺延。连同 15.2 的 P1（info_tab XCJ 文案 + grep -i 无残留）、P2（无 __pycache__）一并完成，版本 036→037（唯一来源），重打包 onedir + 最后重签名，按 7.4 只回一份精炼交付，交主 Agent 回读放行。

---

# 第十七节：用户实测第二轮回归（038，发布前必修）

## 17.1 〔用户明确〕回退右键清除
HotkeyLineEdit.mousePressEvent 删除 RightButton 清除分支，恢复 super 默认行为；**仅 ESC 清除**，提示"(esc清除)"已对齐。右键不再有任何清除/取消作用。

## 17.2 〔控件根因〕支持 shift/tab/ctrl 独立绑定
hotkey_manager.get_key_name 已支持 ctrl/shift/alt/tab（429-452），问题全在 HotkeyLineEdit 捕获控件：
- **修饰键**：keyPressEvent:79 目前纯修饰键直接 return（仅为支持组合键），导致无法单独绑。改为：捕获态下记录待决修饰键，在 **keyReleaseEvent** 判断——若释放的是修饰键且本次捕获期间未捕获其他键，则绑定该修饰键本身（键名 `ctrl`/`shift`/`alt`，小写，与 get_key_name 一致）；若期间捕获了其他键，则走原组合键逻辑不变。
- **Tab**：QLineEdit 默认把 Tab 当焦点切换，keyPressEvent 收不到。重写 `event()` 拦截 `QEvent.KeyPress + Key_Tab`，捕获态下绑定 `"tab"` 并消费事件。
- **不破坏**现有组合键（ctrl+X / alt+F1 等）仍可正常绑；绑定后显示走 get_key_name。

## 17.3 〔最高优先〕无UI切换闪烁/点击失败——两个根因
**根因A（FACT，已坐实）：批次3 T7 半成品，测距功能当前崩溃。** rangefinder.py:128 `_run_steps` 调用 `_execute_steps([step], bx, by)`，但该函数**全文未定义**（已读完全文 192 行确认无 def）。`RangefinderEngine.toggle_ui()`/`measure()` 调用即 NameError。修复二选一：①真正定义模块级 `_execute_steps`（执行步骤序列）并让 quick_toggle_ui 与 _run_steps 都调用；②回退 T7，_run_steps 内联执行 steps。**禁止保留对未定义函数的调用。** measure 路径的 BlockInput 与鼠标归位由外层 finally（167-177）统一负责，toggle_ui 内部不需重复。

**根因B（高可信推断，须实测复现验证）：quick_toggle_ui 无重入保护。** 若 toggle_ui 热键绑定为**鼠标键**，函数内模拟的 `mouse_event(down/up)`（:39/:41）会被鼠标低级钩子捕获并再次触发热键回调，导致重入/振荡——表现正是用户描述的"鼠标在无UI按钮坐标与原光标位置间来回闪烁、点击失败率激增"。修复：模块级 `_toggle_ui_running` 标志（或 threading.Lock），quick_toggle_ui 进入时若已为真直接 return，finally 重置；热键回调侧在标志为真时忽略本次触发。**执行方须用"鼠标键作 toggle_ui 热键"实测复现原问题、再验证修复后无闪烁且点击成功。**

## 17.4 〔可选·不阻塞〕关联载具列表
无可用数显仪时左侧关联载具列表不显示。低成本则修：无 profile 时仍显示空列表或"暂无数显仪"提示，不隐藏整个列表控件；复杂则跳过，用户已明确同意可放弃。

## 17.5 〔交付硬约束〕回应"输出冗杂"
精炼交付单**不超过 15 行**，每行格式 `项 | 文件:行 | 结果`；不写过程、不写解释、不贴大段代码、不附质量门长表。过程/试错/日志写入 status.md 或工作日志。本约束同步进执行方 AGENTS.md 7.4。

## 17.6 回归与发布
实测贴证据：①右键不清、ESC 清；②shift/tab/ctrl 可单独绑、ctrl+X 组合键仍可绑；③鼠标键作 toggle_ui 热键时无闪烁、点击成功；④测距 measure 正常执行（不再 NameError）；⑤关联载具列表（若修）。版本 037→**038**（唯一来源），重打包 onedir + 最后重签名，按 17.5 格式回交付单，交主 Agent 回读。

---

# 第十八节：038 回读结论（主 Agent 亲验）

**静态回读 PASS**：
- 17.1 widgets.py:63-69 右键分支已删除，仅 ESC（:74-76）清除，提示"(esc清除)"（:116）。
- 17.2 修饰键：keyPressEvent 记录待决修饰键（:78-80），keyReleaseEvent 判断纯修饰键单独绑定（:93-103，键名 ctrl/shift/alt/meta），非修饰键路径组合键逻辑不变（:81-89）；Tab 由 event() 拦截捕获态 Key_Tab（:105-110）。
- 17.3A _execute_steps 已定义（rangefinder.py:66-84，wait/press_key/click），quick_toggle_ui（:34）与 _run_steps（:142）均调用，NameError 消除，measure 链路（:148-180）完整。
- 17.3B 重入保护：模块级 _toggle_ui_running（:63），quick_toggle_ui 入口检查（:22-24）+ finally 重置（:42），鼠标键自触发时直接 return。
- 版本：info_tab.py:12 APP_VERSION=V0.0140300038；version_info filevers/prodvers=(0,1,4,38)、ProductVersion 同源、CompanyName=403 FORBIDDEN。
- 发布版 Glob 确认 0 个 __pycache__。

**运行时 UNKNOWN（主 Agent 无法亲跑，需用户实测确认）**：
1. shift/tab/ctrl 实际绑定后热键是否生效（静态逻辑正确，未实跑）。
2. 鼠标键作无UI切换热键时是否仍闪烁、点击是否成功（重入保护逻辑正确，需实测复现场景验证）。
3. 测距 measure 实际执行是否正常出图（NameError 已消除，需实跑）。

**放行条件**：用户实测上述 3 项无异常，038 即作为发布版定稿。若实测发现问题，按对应节打回修复。

---

# 第十九节：用户实测第三轮（039，发布前必修）

## 19.1 〔排查修复〕数显叠加层疑似未鼠标穿透
win32_utils.set_click_through（:25-35）实现正确（WS_EX_LAYERED+WS_EX_TRANSPARENT），rangefinder_overlay __init__（:33）与退出编辑模式（:54）均调用 set_click_through(True)，且有 Qt.WA_TransparentForMouseEvents（:24）。静态层面应穿透，用户实测疑似未穿透，需排查：
- 实测确认：点击叠加层覆盖区域，下方窗口/游戏是否收到点击事件。
- 若未穿透，常见根因：Qt 在 show()/update()/setWindowFlags 后重置扩展样式，需在 showEvent 中重新 set_click_through(True)；或 WA_TransparentForMouseEvents 与 WS_EX_TRANSPARENT 冲突时以 Win32 样式为准。
- 同时检查主 overlay（core/overlay.py）是否也有同样问题，一并修复。

## 19.2 〔行为变更〕无UI切换鼠标位置恢复——按用户建议调整
用户反馈"ui切换随时间显著易错"，建议"只在测距流程完成后恢复鼠标位置"。当前 quick_toggle_ui（rangefinder.py:40）每次执行完都 SetCursorPos 恢复原位，measure（:153记位、finally恢复）也恢复。调整：
- **quick_toggle_ui（独立热键路径）去掉 finally 里的 SetCursorPos 恢复**，执行完鼠标停在无UI按钮坐标，不再强制移回（避免游戏视角跳动/连续操作累积偏差）。
- **measure（测距完整流程）保留 finally 统一恢复一次**（测距是完整闭环，结束后归位合理）。
- 同时排查"易错"是否有其他原因：DEFAULT_TOGGLE_STEPS 各 wait 是否过短（esc 菜单未弹出就点击）、BlockInput 释放时机与 SetCursorPos 的时序、重入保护是否在快速连按时仍有缝隙。若发现其他根因一并修。
- 行为变更需在交付中明确说明：独立无UI热键执行后鼠标不再自动归位。

## 19.3 〔模型变更〕弹种热键改为按载具维度，每辆载具独立从 1 开始
**当前模型（不满足需求）**：hotkeys.ammo_types 全局按弹种名存储 `{弹种名: {key1,...}}`，hotkey_manager 注册所有载具的所有弹种热键（:147-153），add_ammo_type 预填时全局找最小空闲数字（config_manager:628-639）——导致载具a绑了1、2后，载具b只能从3开始。
**用户需求**：人不同时开两辆载具，每辆载具的弹种键应独立从1开始，且已绑定的弹种批量重绑。

**模型变更（根因方案）**：
1. **存储结构**：`hotkeys.ammo_types` 从 `{弹种名: hk}` 改为 `{载具名: {弹种名: hk}}`。写迁移方法：旧格式遍历所有载具，把全局弹种热键复制到各载具下（同名弹种在各载具下独立一份），迁移后删除旧全局键。
2. **动态注册**：hotkey_manager 注册弹种热键时，**只注册当前载具**（current_state.vehicle）的弹种热键；切换载具时（state_machine.set_vehicle / ammo_type_changed 链路）触发 hotkey_manager.reload_hotkeys()，卸载旧载具弹种键、注册新载具的。这样不同载具的弹种可以共用同一个键位，运行时不冲突。
3. **预填逻辑**：add_ammo_type 预填改为按**当前载具内**弹种序号（第N个弹种→数字N，1-9），不再全局找空闲；同一载具内不重复，超过9留空。只预填不覆盖用户已手动绑定的。
4. **批量重绑已存在弹种**：新增一次性操作（或在迁移时一并执行），遍历所有载具的所有弹种，按该载具内弹种序号重设 key1=序号（覆盖现有绑定，用户明确要求"已经绑定的也帮我重绑"）。
5. **同步更新**：remove_ammo_type / rename_ammo_type 同步操作对应载具下的热键；get/set 弹种热键的接口按载具名+弹种名访问。
6. **回归**：载具a建ap/he→热键页显示1/2；载具b建smk/coax→显示1/2（不是3/4）；切换载具后按1切换当前载具的第一个弹种；两辆载具同名弹种互不干扰。

## 19.4 版本与发布
版本 038→**039**（info_tab 唯一来源，version_info 同步），重打包 onedir + 重签名，按 17.5 交付单格式（≤15行）回交付，交主 Agent 回读。19.2 行为变更需在交付中明确标注。

---

# 第二十节：用户实测 039——紧急修复（040，发布阻断级）

## 20.1 〔严重·发布阻断〕hotkey_manager 缺 `import keyboard`，所有键盘热键失效
**根因（FACT，已读源码确认）**：hotkey_manager.py 顶部（:13-16）只有 PyQt5/typing/mouse_hook 的 import，**没有 `import keyboard`**；但 :238 `_register_keyboard_hotkey` 中调用 `keyboard.hook(self._on_global_keyboard_event)`，导致每个键盘热键注册都抛 `NameError: name 'keyboard' is not defined`。用户实测启动后台报一串"注册键盘热键 f1/q/capslock/x/y/1/2/3 失败"。
**修复**：hotkey_manager.py 顶部加 `import keyboard`。修复后所有键盘热键（全局功能键+弹种键）恢复正常，启动无该报错。
**排查要求**：检查其他模块是否也有类似的"使用了但未 import"的问题（尤其批次重构中改动过的文件），一并修复。

## 20.2 〔行为调整〕无UI切换后鼠标归位到屏幕中心
用户测试 19.2 后反馈"ui切换结束后鼠标不归位，哪怕归于屏幕中心也行"。当前 quick_toggle_ui（rangefinder.py:20-40）已完全去掉鼠标归位，鼠标停在无UI按钮坐标。调整：
- quick_toggle_ui 执行完（BlockInput 释放后）将鼠标移到**屏幕中心**，而非原位（原位恢复会导致游戏视角跳动/易错），也非不归位（体验差）。
- 实现：`user32.GetSystemMetrics(0)` 取屏宽、`GetSystemMetrics(1)` 取屏高，`SetCursorPos(宽//2, 高//2)`。多显示器场景取主显示器中心即可。
- measure（测距完整流程）仍保留 finally 归位到原位（测距是完整闭环，归位合理），不受影响。

## 20.3 〔已确认通过〕叠加层鼠标穿透
rangefinder_overlay.py:90-94 showEvent 中重新 set_click_through(True)，主 overlay 同步处理，用户实测穿透已恢复。无需再改。

## 20.4 版本与发布
版本 039→**040**（info_tab 唯一来源，version_info 同步），**本次必须打包 onedir + 重签名**（20.1 是发布阻断，修完立即出包供用户测试）。按 ≤15 行格式回交付单，交主 Agent 回读。

---

# 第二十一节：041 回读结论（主 Agent 亲验）

**静态回读 PASS**：
- 20.1 hotkey_manager.py:16 `import keyboard` 已加，键盘热键 NameError 消除。
- 20.2 quick_toggle_ui（rangefinder.py:42-47）执行后 SetCursorPos 到屏幕中心（GetSystemMetrics 取屏宽高），独立 try-except；_blocked 标志确保 BlockInput 只在成功时释放。
- BlockInput 残留防护：main.py:177-183 启动时 BlockInput(False) + atexit 兜底。
- 版本：info_tab.py:12 V0.0140300041；version_info filevers/prodvers=(0,1,4,41)。
- README 含角度仪（校准/归零/暂离）+ 新手教程 + 常见问题。
- 发布版结构完整（exe+_internal+外置config/resources+README），无 __pycache__，已签名（CN=403 FORBIDDEN, SHA256, DigiCert时间戳）。

**运行时 UNKNOWN（需用户实测确认）**：
1. 键盘热键实际生效（启动无 NameError 报错、按热键有响应）。
2. 无UI切换后鼠标归位到屏幕中心、切换稳定性。
3. 叠加层鼠标穿透（用户已反馈疑似修复，建议再确认）。

**结论**：静态层面 041 可作为发布版定稿。用户实测上述 3 项无异常即发布完成；若有问题按对应节打回。
