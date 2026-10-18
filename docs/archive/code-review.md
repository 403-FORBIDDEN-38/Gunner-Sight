# 当前待办

> 已完成任务见 `docs/archive/code-review-archive-20260906.md`

---

## FIX-20：信息数显模拟点击改用绝对坐标，消除 SetCursorPos（P1，鼠标驱动冲突根源修复）

**背景**：信息数显的模拟点击流程是 `SetCursorPos(目标位置) → mouse_event(LEFTDOWN) → mouse_event(LEFTUP)`。`SetCursorPos` 移动鼠标会与华硕 ROG 等鼠标内核过滤器驱动（如 `klmouflt`）产生状态冲突，导致 BlockInput 恢复后过滤器状态机混乱，物理鼠标点击被拦截。

**修复方案**：用 `mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTDOWN, 归一化X, 归一化Y, 0, 0)` 直接在绝对坐标点击，不需要先 `SetCursorPos` 移动鼠标。

**修改内容**：

### 1. `core/win32_utils.py`：添加 `click_at(x, y)` 函数
```python
def click_at(x, y):
    """绝对坐标点击：用 MOUSEEVENTF_ABSOLUTE 直接在指定坐标点击，不移动鼠标光标。
    坐标为像素坐标（相对于主显示器左上角）。"""
    sw = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    sh = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    if sw <= 0 or sh <= 0:
        return
    nx = int(x * 65535 / sw)
    ny = int(y * 65535 / sh)
    # 绝对坐标移动+按下
    user32.mouse_event(0x8000 | 0x0001 | 0x0002, nx, ny, 0, 0)  # ABSOLUTE|MOVE|LEFTDOWN
    time.sleep(0.02)
    # 绝对坐标抬起（保持同一位置）
    user32.mouse_event(0x8000 | 0x0001 | 0x0004, nx, ny, 0, 0)  # ABSOLUTE|MOVE|LEFTUP
```

### 2. `core/rangefinder.py`：`_execute_steps` 的 click action 改用 `click_at`
- 第90-94行：删除 `SetCursorPos(int(bx), int(by))` + 两次 `mouse_event`
- 改为调用 `win32_utils.click_at(int(bx), int(by))`
- 保留 20ms 延迟（click_at 内部已有）

### 3. `core/rangefinder.py`：`RangefinderEngine._click` 改用 `click_at`
- 第142-147行：删除 `SetCursorPos(int(x), int(y))` + 两次 `mouse_event`
- 改为调用 `win32_utils.click_at(int(x), int(y))`

### 4. 删除不再需要的鼠标位置恢复代码
- `quick_toggle_ui` 函数 finally 块（第46-51行）：删除 `SetCursorPos(sw // 2, sh // 2)`——因为鼠标没有被移动，不需要恢复
- `_run_steps` 中的鼠标位置恢复代码（第214行附近）：删除 `SetCursorPos(pt.x, pt.y)`——同理

### 5. BlockInput 恢复超时保护（防止线程卡住导致输入永久锁定）
`quick_toggle_ui` 和 `RangefinderEngine.measure()` 都使用 `BlockInput(True/False)`，当前仅靠 try/finally 恢复。如果线程卡住（截图卡住、toggle_ui 卡住、sleep 卡住），finally 不会执行，BlockInput 永远不恢复，用户输入永久锁定。

**修复方案**：用 `threading.Timer` 添加超时保护：
- `BlockInput(True)` 成功后，启动一个 `threading.Timer(5.0, _force_unblock)`，5 秒后自动调用 `BlockInput(False)`
- 在 finally 中正常恢复 BlockInput 后，取消这个定时器（`timer.cancel()`）
- `_force_unblock` 函数中用标志位防止重复调用，调用后 print 警告日志
- 超时时间设为 5 秒（正常 measure 流程在 1 秒内完成，5 秒足够覆盖异常情况）

需要修改的位置：
- `quick_toggle_ui` 函数（第23-52行）：BlockInput 后启动 Timer，finally 中取消
- `RangefinderEngine.measure()` 方法（第159-197行）：BlockInput 后启动 Timer，finally 中取消

### 6. 验证
- 信息数显正常工作（截图、识别、显示）
- 模拟点击后鼠标光标位置不变（不跳转到目标位置）
- 连续使用信息数显 10 次后，物理鼠标点击仍正常
- BlockInput 超时保护：模拟 measure 线程卡住（如在 toggle_ui 中添加 time.sleep(10)），验证 5 秒后 BlockInput 自动恢复，用户输入不被永久锁定
- 原有测试无回归
- 静态扫描无新增警告

**注意**：`MOUSEEVENTF_ABSOLUTE` 坐标映射到主显示器。多显示器环境下，如果目标在副显示器，需要用 `GetSystemMetrics(SM_XVIRTUALSCREEN/SM_CXVIRTUALSCREEN)` 计算虚拟屏幕坐标。当前 GS 主要在单显示器环境使用，先支持主显示器，后续可扩展。

---

## VDR-重铸：叠加层穿透系统系统性重生（P0，VDR-Spiral 阶段⑤）

**VDR 分析已完成**：详见 `docs/vdr-click-through.md`（阶段②观态→③反推→④塑骨）

**核心发现**：
1. 信息数显穿透反复丢失的根因是窗口重建时序导致 `_apply_click_through()` 静默失败，无验证无重试
2. **AngleOverlay（角度仪悬浮窗）从未设置穿透**——直接继承 QWidget，没有 `WA_TransparentForMouseEvents`，没有 `WS_EX_TRANSPARENT`
3. 补丁网络：`rangefinder_tab.py:719` 的 BUG-9 第三层补丁只覆盖测距完成场景
4. `win32_utils.set_click_through` 不检查 API 返回值，失败静默

**重铸任务**（按顺序执行）：

### 1. 增强 ClickThroughOverlay 基类（core/overlay_base.py）
- 添加 `_verify_click_through()`：检查 `GetWindowLongW` 返回值是否包含 `WS_EX_TRANSPARENT`
- 增强 `_apply_click_through()`：设置后验证，失败时 `QTimer.singleShot(10ms)` 延迟重试，最多3次，3次失败显式 print 错误（不再静默）
- 重写 `setAttribute()`：检查是否修改了 `WA_TransparentForMouseEvents`，如果是则 super() 后恢复穿透
- `setWindowOpacity`/`setWindowFlags`/`showEvent` 添加延迟确认（`QTimer.singleShot(10ms, self._apply_click_through)`）

### 2. 增强 win32_utils.set_click_through（core/win32_utils.py）
- 添加返回值 bool：成功返回 True，失败返回 False
- 检查 `GetWindowLongW` 返回值（0 可能表示失败）
- 检查 `SetWindowLongW` 返回值（0 表示失败，调用 `GetLastError`）
- 失败时 print 错误信息

### 3. 迁移 AngleOverlay（gui/tabs/angle_meter_tab.py）
- `class AngleOverlay(QWidget)` → `class AngleOverlay(ClickThroughOverlay)`
- 删除 `__init__` 中独立的 `setWindowFlags` 和 `setAttribute(WA_TranslucentBackground)`（基类已设置）
- 确认角度仪 overlay 显示后鼠标能穿透 160x80 区域

### 4. 删除补丁（gui/tabs/rangefinder_tab.py）
- 删除 `rangefinder_tab.py` 中 BUG-9 第三层补丁（测距完成后强制 `ov.ensure_click_through()`）
- 清理中文乱码注释
- 基类统一恢复后补丁不再需要

### 5. 验证（必须全部通过）
- 启动 GS，所有 overlay 显示后鼠标能穿透点击桌面图标
- 信息数显：连续测距10次，每次后穿透正常
- 信息数显：修改透明度设置，修改后穿透正常
- 信息数显：进入/退出编辑模式，退出后穿透正常
- 角度仪：overlay 显示后鼠标能穿透 160x80 区域
- 准星叠加：overlay 显示后穿透正常
- 标定测距：overlay 显示后穿透正常
- 切换 tab 再切回，穿透正常
- 控制台无"应用穿透失败"或"穿透验证失败"错误
- 原有 110 测试无回归

---

## BUG-18：准星图片全部找不到（P0）

**根因**：配置中准星路径存储为 `分类\文件名.png`（无 `resources\` 前缀的相对路径），overlay 的 `set_crosshair()` 直接 `QPixmap(image_path)` 加载。当前工作目录是项目根目录，路径解析为 `项目根\分类\文件名.png`——**缺少 `resources\` 前缀**，实际文件在 `项目根\resources\分类\文件名.png`。

**附加问题**：配置中路径分隔符不统一——有些用正斜杠 `任意/xxx.png`，有些用反斜杠 `USA M1128 MGS\xxx.png`。

**表现**：启动后日志大量 `[Overlay] 准星图片不存在: USMC&USA M2\M2 1X.png`，overlay 无准星显示。资源库能正常显示图片（资源库自己拼接了 resources 前缀）。

**修复**：在 config 层 `get_current_crosshair()` 中返回拼接了 `resources\` 目录的绝对路径（`str(self.resources_dir / relative_path)`），所有调用方统一得到正确路径。同时统一路径分隔符为正斜杠。

**验证**：启动后无"准星图片不存在"日志，overlay 正常显示准星，切换载具/弹种/倍率准星正确切换，资源库不受影响。

---

## ~~BUG-17：get_app_base_dir() 路径错误~~ ✅ 已修复

**根因**：`core/config/base.py` 的 `get_app_base_dir()` 开发环境返回 `Path(__file__).parent.parent`，但 base.py 在 `core/config/` 下，上溯两层只到 `core/`，少了一层。QUALITY-P2 config 拆分引入的回归。

**修复**：第26行 `.parent.parent` → `.parent.parent.parent`。**最小修复 = 一行，基于根源病灶（路径上溯层数错误），不是补丁。**

**事故**：修复过程中执行Agent用 PowerShell `Set-Content` 写文件导致中文编码损坏，最终完全重写 base.py（445行41方法）。详见下方 T0-降险。

---

## T0-降险：base.py 重写后加强测试 + 流程规范（P0）

**事故根因**：执行Agent修复一行路径错误时，用 PowerShell `Set-Content` 写 Python 文件 → 编码损坏 → 用 20+ 步批量清理乱码 → 越修越坏 → 完全重写 445 行文件。**一行错误变成整个文件重写，是典型的修复手段脱离根源病灶。**

**任务**：

### 1. 加强配置测试覆盖（确认重写版行为与原始一致）
- 旧配置迁移测试：构造旧格式 cfg（key/trigger 热键、xcj 段、旧角度仪校准），验证 load_config 后所有迁移正确
- 损坏配置恢复测试：构造语法错误 config.json，验证自动备份为 .corrupt 并回退最小骨架
- 空配置初始化测试：删除 config.json 后启动，验证最小骨架正确生成、所有列表为空
- 保存有序+过滤冗余字段测试：保存后验证顶层键按固定顺序、热键无 key/trigger 旧字段
- 防抖保存测试：连续 request_save 10 次，验证只执行一次实际写入

### 2. 执行Agent AGENTS.md 加强写文件规范（防止再次发生）
- 写 Python 文件必须用 Write 工具或 Python 脚本，**禁止 PowerShell Set-Content/Add-Content**（Windows PowerShell 5.1 默认写 UTF-8 with BOM，ast.parse 直接失败）
- 文件损坏/编码异常时，**立即从 git 恢复或用备份**，禁止用批量正则清理乱码（可能清掉正常代码）
- **最小修复原则**：一行能修的绝不重写整个文件；修复必须基于根源病灶，不是补丁式掩盖症状
- 重写文件必须有方法级对比验证（方法列表、签名、关键逻辑逐项对比）

### 3. 立即 commit 当前 base.py 作为基线
- 当前重写版功能正常（编译+108测试+UI冒烟通过），先固化防止后续修改丢失
- **用 dulwich commit**（项目一直用纯 Python git，不需要 git.exe），禁止以"git.exe 未安装"为由跳过

### 4. 防抖测试补全（当前只测了"不立即写盘"，需补）
- `test_deferred_save_writes_after_500ms`：request_save 后等待 600ms，验证文件已写入
- `test_consecutive_request_save_writes_once`：连续 request_save 10 次，等待 600ms，验证只执行一次实际写入（可用 mock 统计 _do_deferred_save 调用次数）

**验证**：新增测试全部通过 + 原有 108 测试无回归 + dulwich commit 成功

**补充项（审查发现，必须执行）**：
1. **用 dulwich commit 当前 base.py 作为基线** — 系统未装 git.exe，但项目一直用 `pip install dulwich` 纯 Python git 实现做 commit。禁止以"git.exe未安装"为由放弃。用 dulwich Python API 完成 add + commit。
2. **防抖测试补充 2 例** — 当前只验证了"request_save 后不立即写盘"，需补充：
   - `test_request_save_writes_after_500ms`：request_save 后等待 600ms，验证文件已写入
   - `test_consecutive_request_save_writes_once`：连续 request_save 10 次，等待 600ms，验证只执行一次实际写入（用 mock 或文件 mtime 判断）

---

## FEATURE-6：载具页进入时恢复当前使用的载具/弹种/倍率选中

`vehicle_config_tab.py` 的 `showEvent` 中读取 state_machine 当前状态，依次选中标签→载具→弹种→倍率。注意在列表数据加载完成后执行。

---

## FEATURE-7：级联自动选中（标签→载具→弹种→倍率）

选中标签→载具列表自动选中第一辆→弹种自动选中第一个→倍率自动选中第一倍率。空列表不崩溃，用 blockSignals 防循环。

---

## FEATURE-8：新建载具/弹种/倍率时自动选中新项

新建后 `setCurrentRow` 选中新项（通常最后一行），触发级联。

---

## REFACTOR-3：删除倍率重命名 + 删除倍率时自动补位

- 删除倍率重命名按钮和方法（倍率名是自动序号，无意义）
- 倍率名称不持久化，UI 动态生成"倍率{idx+1}"，从根源消除断层
- 载具/弹种重命名保留

---

## PERF-2：资源加载性能优化

排查点：overlay 是否预加载所有准星图片（应只加载当前使用的）、资源库缓存上限是否合理、图片是否预缩放、切换时旧 QPixmap 是否释放。优先懒加载。

---

## QUALITY-P3：大tab拆分子组件（持续优化）

angle_meter_tab(772行)、rangefinder_tab(708行)、vehicle_config_tab(668行) 拆分为主tab + 子组件，单文件≤400行。

---

## BUG-20：信息数显 BlockInput 与鼠标过滤器驱动冲突导致物理鼠标点击失效（P0）

**根因**：信息数显流程 `BlockInput(True) → SetCursorPos(移动鼠标) → mouse_event(点击) → BlockInput(False)` 中，`SetCursorPos` 软件生成的鼠标移动事件被华硕 ROG 鼠标内核过滤器 `klmouflt.K4W-21-26` 处理，导致过滤器状态机混乱。`BlockInput(False)` 恢复后，过滤器继续吞掉物理鼠标点击但不向上传递。模拟点击（软件注入）不受影响，因为不经过过滤器的物理设备处理逻辑。

**修复方案**：

### 1. 去掉 SetCursorPos，用绝对坐标直接点击（核心改动）
当前流程需要先 `SetCursorPos` 移动鼠标再点击，这是导致过滤器状态混乱的关键步骤。改为用 `MOUSEEVENTF_ABSOLUTE` 直接在绝对坐标点击，不需要先移动鼠标：
```python
# 旧：SetCursorPos(x, y) + mouse_event(LEFTDOWN) + mouse_event(LEFTUP)
# 新：mouse_event(ABSOLUTE|MOVE|LEFTDOWN, x*65535//screenW, y*65535//screenH, 0, 0)
#     mouse_event(ABSOLUTE|LEFTUP, ...)
```
点击完成后，用 `SetCursorPos` 把鼠标移回原始位置（减少用户感知），但这个移动发生在 BlockInput(False) 之后，不影响过滤器状态。

### 2. BlockInput 恢复后验证鼠标状态（兜底）
`BlockInput(False)` 后：
- 调用 `GetAsyncKeyState(VK_LBUTTON)` 检测鼠标状态是否正常
- 发送一个测试性的模拟点击到屏幕角落（0,0），验证系统是否正常响应
- 如果检测到异常（连续3次状态异常），弹窗提示用户"鼠标驱动状态异常，建议重启电脑"，并提供一键修复按钮（重启资源管理器 + 重新枚举鼠标设备）

### 3. 确保 BlockInput 可靠恢复
- 用 `try/finally` 包裹整个信息数显流程，任何异常路径都确保 `BlockInput(False)` 被调用
- 添加超时保护：如果信息数显流程超过5秒未完成，自动调用 `BlockInput(False)` 恢复输入

**验证**：
- 信息数显连续使用10次，每次后物理鼠标点击正常
- 信息数显使用过程中强制中断（按 Esc），BlockInput 能恢复
- 信息数显使用后，华硕 ROG 鼠标（如有）物理点击正常
- 模拟点击功能不受影响
- 原有110测试无回归
