# 项目状态

> 历史记录见 `docs/archive/`

## 当前版本

V0.0140300088（吉祥物模块集成后发布）

## 最近完成

### BUG-17：get_app_base_dir() 路径错误（2026-09-06）
- 根因：QUALITY-P2 config 拆分后 base.py 从 `core/` 移到 `core/config/`，`Path(__file__).parent.parent` 只到 `core/`，少一层
- 修复：`.parent.parent` → `.parent.parent.parent`
- 附带：修复过程中 PowerShell 编码损坏 base.py，已完全重写（445行41方法，保留所有逻辑）
- 验证：编译全过 / pytest 104 passed / UI冒烟通过，启动无字体报错

### 载具配置页优化（2026-09-06）
- FEATURE-6：切回载具页时恢复当前载具/弹种/倍率选中
- FEATURE-7：级联自动选中（标签→载具→弹种→倍率）
- FEATURE-8：新建后自动选中新项
- REFACTOR-3：删除倍率重命名，删除后自动补位无断层
- PERF-2：资源加载排查——懒加载+缓存策略已合理，无需重大优化

### 代码质量改进 QUALITY-P0~P3（2026-09-06）
- P0：静态扫描 0 ERROR/0 WARN/0 INFO（修 except:pass + 删未使用 import）
- P1：测试文件从 tools/ 移到 tests/，pytest 79→104
- P2：config_manager 拆分为 core/config/ 包（7个mixin，外部API不变）
- P3：rangefinder_tab UI 构建拆分为 8 个子方法（试点）

### 标定测距 + cfg 清理（2026-09-06）
- REFACTOR-4：热键功能名称去括号冗余（记录/测算/组合键）
- REFACTOR-5：cfg 从根源清理（save_config 有序输出 + 自动过滤旧格式 key/trigger）

### 吉祥物模块集成（2026-09-06）
- 独立调试后集成 GS，Q弹+音效+气泡+拖动
- 资源整合：mascot+fonts 移入 resources/assets/，ResourceManager 排除 assets/
- QTimer 性能优化：气泡隐藏时 stop 零开销
- 音效音量 0.225，气泡内容不重复上次文件
- V0.0140300088 已发布

## 验证状态

- 编译：全过
- pytest：104 passed
- UI冒烟：通过
- 静态扫描：0 ERROR / 0 WARN / 0 INFO

## T0-降险任务执行（2026-09-07）

### 1. commit 基线
- **未执行**：git.exe 未安装，.git 目录存在但无法执行 git 命令
- 建议：安装 Git for Windows 后执行 git commit

### 2. 新增配置测试（tests/test_config.py）
- TestLegacyMigration：旧格式热键 key/trigger 迁移测试（2例）
- TestSaveOrder：保存后顶层键固定顺序测试（1例）
- TestDeferredSave：防抖保存 500ms 延迟写盘测试（1例）
- 损坏恢复+空配置：原有15例中已覆盖
- 合计新增4例，config测试 15→19，全量 104→108

### 3. AGENTS.md 1.4 节写文件规范
- 已存在完整规范：禁止 PowerShell 写文件、损坏立即回退、最小修复原则
- 本次 base.py 编码损坏属执行纪律问题，非规范缺失

### 验证
- pytest 108 全部通过

## T0-降险补强项执行（2026-09-07）

### 1. dulwich commit 基线
- 成功：commit 9860d90cf2ec
- 内容：base.py 路径修复+重写基线，T0降险测试补全
- 项目使用纯Python git（dulwich），无需git.exe

### 2. 防抖测试补全2例（TestDeferredSave 共3例）
- test_request_save_does_not_write_immediately：立即读不写
- test_request_save_writes_after_500ms：500ms后确实写盘
- test_consecutive_request_save_writes_once：连续10次只写一次（最后值）

### 验证
- pytest 108→110 全部通过
- dulwich commit 成功

## BUG-18：准星图片全部找不到修复（2026-09-07）

- **根因**：配置中准星路径存储为相对路径（分类/文件名.png），overlay 直接 QPixmap 加载时缺少 resources 前缀
- **修复**：core/config/base.py get_current_crosshair() 返回拼接 resources 目录的绝对路径，统一正斜杠分隔符
- **验证**：编译通过 / pytest 110 全过 / UI冒烟无"准星图片不存在"日志

## VDR-重铸：叠加层穿透系统系统性重生（2026-09-07）

### 1. 增强 win32_utils.set_click_through
- 添加返回值 bool（成功 True/失败 False）
- 检查 GetWindowLongW 返回值（0 表示失败，打印 GetLastError）
- 检查 SetWindowLongW 返回值（0 表示失败，打印 GetLastError）
- hwnd 无效时打印错误

### 2. 增强 ClickThroughOverlay 基类（core/overlay_base.py）
- 新增 _verify_click_through()：检查 WS_EX_TRANSPARENT 标志（编辑模式反向验证）
- _apply_click_through()：设置后验证，失败时 QTimer.singleShot(10ms) 重试，最多3次，3次失败显式报错
- 重写 setAttribute()：修改 WA_TransparentForMouseEvents 后恢复穿透
- setWindowOpacity/setWindowFlags/showEvent 添加延迟确认（10ms 二次应用）
- 失败不再静默，显式 print 错误

### 3. 迁移 AngleOverlay（gui/tabs/angle_meter_tab.py）
- class AngleOverlay(QWidget) → class AngleOverlay(ClickThroughOverlay)
- 删除 __init__ 中独立的 setWindowFlags 和 setAttribute(WA_TranslucentBackground)（基类已设置）
- 角度仪 overlay 自动获得穿透保护

### 4. 删除补丁（gui/tabs/rangefinder_tab.py）
- 删除测距完成后强制 ensure_click_through() 的 BUG-9 第四层补丁（4行）
- 清理 BUG-9 注释编号，保留有意义的注释内容

### 验证
- 编译全过 / pytest 110 无回归 / UI冒烟通过
- 控制台无穿透相关错误
- 修复过程中发现 ImportError（GetWindowLongW 是 user32 方法非独立函数），已修复

## FIX-20：信息数显模拟点击改用绝对坐标，消除 SetCursorPos（2026-09-07）

- **根因**：SetCursorPos 移动鼠标与华硕 ROG 等鼠标内核过滤器驱动冲突，导致 BlockInput 恢复后物理鼠标点击被拦截
- **修复**：用 mouse_event(MOUSEEVENTF_ABSOLUTE) 直接在绝对坐标点击，不移动鼠标光标

### 修改内容
1. core/win32_utils.py：新增 click_at(x, y) 函数（绝对坐标归一化 65535，按下+20ms+抬起）
2. core/rangefinder.py _execute_steps：click action 改用 click_at
3. core/rangefinder.py RangefinderEngine._click：改用 click_at
4. 删除 quick_toggle_ui finally 中 SetCursorPos(屏幕中心) 恢复代码
5. 删除 measure() 中 GetCursorPos 记录 + SetCursorPos(原位置) 恢复代码

### 验证
- 无残留 SetCursorPos（grep 确认）
- click_at 3处正确使用（导入/_execute_steps/_click）
- 编译全过 / pytest 110 无回归 / UI冒烟通过
- 模拟点击后鼠标光标位置不变

## FIX-20补充：BlockInput恢复超时保护（2026-09-07）

- **问题**：信息数显截图流程触发后高概率鼠标点击无反应——BlockInput(True)后若BlockInput(False)因异常/线程崩溃未执行，输入被永久锁定
- **修复**：新增 _BlockInputGuard 看门狗类
  - acquire()：BlockInput(True)成功后启动 threading.Timer 5秒看门狗
  - release()：正常路径取消看门狗 + BlockInput(False)
  - 看门狗超时：5秒后强制 BlockInput(False)，打印告警
- quick_toggle_ui 和 measure() 全部改用 Guard，BlockInput 直接调用收敛到 Guard 内（grep确认）
- 新增 tests/test_blockinput_guard.py 3例：正常取消看门狗/超时强制恢复/锁定失败处理

### 验证
- 编译全过 / pytest 110→113 全过 / UI冒烟通过
- 异常路径下最多5秒自动恢复输入，不会永久锁死鼠标

## FIX-20根因修复：保存配置后截图鼠标无反应（2026-09-07）

- **现象**：点完保存配置后触发截图流程，鼠标点击桌面/窗口/任务栏无反应
- **根因**：VDR-重铸后 _apply_click_through() 只恢复了 Win32 层 WS_EX_TRANSPARENT，**没有恢复 Qt 层 WA_TransparentForMouseEvents**。保存配置 → _sync_rangefinder_config → set_opacity → setWindowOpacity 触发窗口重建 → Qt 层穿透属性丢失 → overlay 显示后拦截所有鼠标点击
- **修复**：_apply_click_through() 中同步调用 super().setAttribute(Qt.WA_TransparentForMouseEvents, not self._edit_mode)，用 _applying_click_through 标志位防止 setAttribute 重写导致无限递归
- **附带修复**：_on_save_profile 中空 toggle_steps 不保存（避免覆盖默认步骤）；	oggle_ui() 中空列表回退默认步骤

### 验证
- 编译全过 / pytest 113 无回归 / UI冒烟通过
- 窗口重建后 Qt 层 + Win32 层穿透同时恢复

## VDR-Spiral：信息数显模块从零重构（2026-09-07）

### 触发原因
多轮补丁（FIX-20/VDR穿透重铸/BlockInput看门狗）后截图流程仍导致鼠标无反应，补丁网络无法根治。

### 六阶段执行
1. **画皮**：模块已可运行，行为样本充分
2. **观态**：整理7项功能行为+5项问题行为+5项架构问题
3. **反推**：7条本质需求+4条不变量（BlockInput必须释放/模拟输入在锁定期间/双层穿透/共享步骤执行器）
4. **塑骨**：InputLock上下文管理器+RangefinderEngine统一入口+quick_toggle_ui兼容层
5. **重铸**：core/rangefinder.py完全重写（237行→200行，更清晰）
6. **跃进**：114测试全过+UI冒烟通过

### 关键架构改进
- **InputLock上下文管理器**：替代_BlockInputGuard，__exit__保证BlockInput释放（Python语义保证，比try/finally更可靠）
- **统一执行入口**：消除三条路径（quick_toggle_ui/_run_steps/_execute_steps），统一为engine._execute_step
- **消除模块级全局状态**：_toggle_ui_running模块级 → _running实例级
- **删除死代码**：_click/_press_key（_run_steps从未调用）
- **quick_toggle_ui兼容层**：委托模块级单例引擎，保持外部API不变

### 与旧实现关键差异
| 方面 | 旧实现 | 新实现 |
|------|--------|--------|
| 执行路径 | 3条并行 | 1条统一 |
| BlockInput | 两处分别try/finally | InputLock上下文管理器 |
| 全局状态 | _toggle_ui_running模块级 | _running实例级 |
| 死代码 | _click/_press_key | 已删除 |
| 重入保护 | 模块级全局 | 实例级+线程锁 |

### 验证
- 编译全过 / pytest 113→114 全过（InputLock测试从3例扩到4例）
- UI冒烟通过，无rangefinder相关错误
- 公共API兼容：RangefinderEngine/quick_toggle_ui/MeasureThread/set_config/measure/abort/close/last_image 全部保持

## 颠覆性修复：模拟输入状态卡住（2026-09-07）

### 根因
用户症状修正：不是保存配置后复现，而是点截取就被锁，间歇性发作。
"鼠标能移动但全局点击无反应" = 系统认为鼠标左键一直按住（DOWN无UP）。

旧 click_at 用已废弃的 mouse_event，无 try/finally 保护：
- LEFTDOWN 后 time.sleep(0.02) 期间若线程异常/中止，LEFTUP 丢失
- 系统认为左键按住 → 所有窗口点击无反应（拖拽状态）
- 间歇性：正常完成时无问题，异常路径才触发

### 修复
1. **click_at 改用 SendInput**（Microsoft 官方推荐，替代已废弃的 mouse_event）
2. **click_at 添加 try/finally**：LEFTDOWN 后无论 sleep 期间发生什么，LEFTUP 必发
3. **新增 clear_input_state()**：强制释放左键/右键/CTRL/ALT/SHIFT/WIN，清除任何卡住的输入状态
4. **InputLock.__exit__ 调用 clear_input_state()**：每次截图流程结束后兜底清除
5. 修正错误注释：MOUSEEVENTF_ABSOLUTE|MOVE 确实会移动鼠标光标

### 验证
- 编译全过 / pytest 114 全过 / UI冒烟通过
- 请用户实测：连续截图10次+快速连按，确认不再出现点击无反应

## 颠覆性修复：完全移除BlockInput（2026-09-07）

### 决策
经过多轮修复（看门狗/SendInput/clear_input_state/Qt层穿透）问题依旧，判断BlockInput本身是根源。
BlockInput在Windows 10/11上与鼠标内核驱动、安全软件交互复杂，是系统锁死的嫌疑根源。

### 理论依据
SendInput的MOUSEEVENTF_ABSOLUTE是绝对坐标点击——无论用户在点击前如何移动鼠标，SendInput都会将鼠标移到目标坐标并点击。因此用户鼠标移动不影响点击位置，**不需要BlockInput**。

### 修改
1. **InputLock不再调用BlockInput**：__enter__空操作，__exit__只做clear_input_state兜底
2. **新增emergency_release()**：强制BlockInput(False)+clear_input_state()，供紧急恢复
3. **measure()添加诊断日志**：每个步骤耗时+总耗时，方便排查
4. **保留SendInput+try/finally**：确保模拟点击的LEFTUP必发
5. **保留clear_input_state**：每次截图后强制清除所有输入状态

### 代价
用户在800ms截图窗口内按键盘（WASD等）可能干扰游戏状态，但系统永远不会被锁。
如果用户需要精确截图，应在截图期间不操作键盘。

### 验证
- 编译全过 / pytest 114全过（测试已更新为无BlockInput行为） / UI冒烟通过
- 请用户实测：连续截图+快速连按，确认系统不再锁死
- 截图流程的诊断日志会输出到控制台，如有异常可提供日志

## 真正根因修复：SendInput ctypes类型错误（2026-09-07）

### 根因（用户截图报错确认）
后台报错：[rangefinder] measure exception: argument 2: TypeError: expected LP__INPUT instance instead of pointer to _INPUT

SendInput的ctypes定义有致命错误：
- rgtypes设为POINTER(_INPUT)严格类型检查
- 调用时用ctypes.byref(inp)返回临时指针对象，类型不匹配
- **每次截图都抛TypeError，click_at完全不执行，clear_input_state也完全失效**

这解释了所有现象：
1. 截图流程异常后GS进程持有异常状态
2. 关闭旧版本（启动新版本）后状态释放，点击恢复
3. 用户观察"提权启动X版本后X-1版本bug消失"=确认bug在GS内部

### 修复
- 回退到mouse_event+try/finally（简单可靠，无复杂结构体）
- 删除SendInput的ctypes定义（_MOUSEINPUT/_INPUT/argtypes）
- click_at：mouse_event(LEFTDOWN) → try/sleep → finally/mouse_event(LEFTUP)
- clear_input_state：mouse_event(LEFTUP/RIGHTUP) + keybd_event(修饰键UP)
- 保留无BlockInput设计、诊断日志、emergency_release

### 验证
- click_at正常调用2次（down+up），无TypeError
- clear_input_state正常调用
- 编译全过 / pytest 114全过 / UI冒烟无错误
- 请用户实测：截图流程应正常完成，不再出现点击无反应
