# VDR-Spiral：叠加层穿透系统系统性重生

> 启动时间：2026-09-07
> 范围：GS 项目所有叠加层（overlay）的穿透机制
> 触发原因：穿透问题反复出现（至少3次），补丁网络无法根治，AngleOverlay 独立实现从未设置穿透

---

## 阶段②：观态（行为观测）

### 已验证行为事实（FACT）

#### A. 穿透丢失行为
- FACT-1：用户使用信息数显功能后，鼠标点击无法穿透 overlay，只能点击 GS 窗口
- FACT-2：该问题反复出现（至少3次），每次修复后又复现
- FACT-3：关闭 GS 进程后问题消失（overlay 窗口拦截了鼠标）
- FACT-4：用户描述为"鼠标点不到桌面图标/任务栏"，不是鼠标完全不能动（排除 BlockInput）

#### B. 四个 overlay 子类的实现状态
- FACT-5：`OverlayWindow`（准星叠加）继承 `ClickThroughOverlay`，无独立重写 ✅
- FACT-6：`RangefinderOverlay`（信息数显）继承 `ClickThroughOverlay`，有独立 `set_opacity` 和编辑模式/MouseHook 逻辑 ⚠️
- FACT-7：`DistanceOverlay`（标定测距）继承 `ClickThroughOverlay` ✅
- FACT-8：`AngleOverlay`（角度仪）**直接继承 QWidget，不继承 ClickThroughOverlay** ❌
  - 没有设置 `WA_TransparentForMouseEvents`
  - 没有调用 `set_click_through` 设置 Win32 `WS_EX_TRANSPARENT`
  - **结论：AngleOverlay 从未有穿透，不是"穿透丢失"，是"从未设置穿透"**

#### C. 穿透机制行为
- FACT-9：穿透由两层组成：Qt `WA_TransparentForMouseEvents` + Win32 `WS_EX_TRANSPARENT`
- FACT-10：`setWindowOpacity` 在 Windows 上会触发生层窗口重建，`winId()` 变化
- FACT-11：`setWindowFlags` 也会触发窗口重建
- FACT-12：窗口重建后，旧的 `WS_EX_TRANSPARENT` 扩展样式丢失
- FACT-13：基类 `ClickThroughOverlay` 重写了 `setWindowOpacity`/`setWindowFlags`/`showEvent` 来恢复穿透
- FACT-14：但在窗口刚重建、新 `winId` 尚未生效时，`_apply_click_through()` 中 `set_click_through(int(self.winId()), ...)` 可能拿到无效 hwnd，`set_click_through` 中 `if not hwnd: return` **静默跳过**
- FACT-15：`_apply_click_through()` 失败时只 print，无重试机制
- FACT-16：`win32_utils.set_click_through` 不检查 `GetWindowLongW`/`SetWindowLongW` 返回值，失败静默

#### D. 补丁网络行为
- FACT-17：`rangefinder_tab.py:719` 有 BUG-9 的第三层补丁：测距完成后强制 `ov.ensure_click_through()`
- FACT-18：这个补丁只覆盖测距完成场景，不覆盖其他场景（修改透明度、切换tab、窗口重建、编辑模式退出）
- FACT-19：补丁注释是中文乱码（之前 PowerShell 编码损坏残留）

#### E. 编辑模式行为
- FACT-20：进入编辑模式时关闭穿透（`WA_TransparentForMouseEvents=False` + 清除 `WS_EX_TRANSPARENT`）
- FACT-21：退出编辑模式时恢复穿透
- FACT-22：`RangefinderOverlay` 重写了 `set_edit_mode`，添加了 MouseHook 全局鼠标监听（点击外部自动退出）
- FACT-23：`AngleOverlay` 没有编辑模式

#### F. 时序问题
- FACT-24：`_init_rangefinder` 中创建 overlay 后，`QTimer.singleShot(0, _sync_rangefinder_config)` 中调用 `set_opacity()`
- FACT-25：`set_opacity()` → `setWindowOpacity()` → 窗口重建 → 穿透丢失 → `ensure_click_through()` 可能因时序静默失败
- FACT-26：`ClickThroughOverlay.__init__` 中 `setWindowFlags()` 也会触发窗口重建，此时窗口尚未创建，`ensure_click_through()` 静默失败，依赖后续 `QTimer.singleShot(0, self._apply_click_through)` 和 `showEvent` 恢复

### UNKNOWN（尚未验证）
- UNKNOWN-1：除信息数显外，其他 overlay（准星、标定测距）是否也发生过穿透丢失？
- UNKNOWN-2：`setWindowOpacity` 触发窗口重建的具体时序（重建后多久新 winId 生效？）
- UNKNOWN-3：AngleOverlay 从未设置穿透，用户是否遇到过角度仪 overlay 拦截鼠标的问题？

---

## 阶段③：反推（本质反推）

### 本质需求（每个需求标注来源行为和置信度）

#### 本质需求1：叠加层显示时（非编辑模式），鼠标必须穿透到下层窗口
- 来源：FACT-1, FACT-2, FACT-3, FACT-4
- 置信度：Confirmed（已被多次独立行为验证）
- 不可变约束：overlay 可见且非编辑模式时，鼠标事件必须穿透
- 换栈检验：✅ 换技术栈仍然成立（任何平台的悬浮窗都需要穿透）

#### 本质需求2：穿透状态必须是单一权威来源，不能分散在多个路径
- 来源：FACT-17, FACT-18（补丁只覆盖部分场景）
- 置信度：Confirmed
- 不可变约束：穿透状态只能由一个模块管理，所有修改窗口样式的操作必须经过这个模块自动恢复
- 换栈检验：✅ 仍然成立（状态一致性是跨平台需求）

#### 本质需求3：任何导致窗口重建的操作后，穿透必须被可靠恢复
- 来源：FACT-10, FACT-11, FACT-12, FACT-14, FACT-15, FACT-16
- 置信度：Confirmed
- 不可变约束：窗口重建后穿透恢复必须有验证（检查 Win32 API 返回值）和重试（失败时延迟重试），不能静默失败
- 换栈检验：✅ 仍然成立（任何平台都有窗口重建/样式重置的问题）

#### 本质需求4：所有叠加层必须走同一套穿透机制，禁止独立实现
- 来源：FACT-8（AngleOverlay 独立实现，从未设置穿透）
- 置信度：Confirmed
- 不可变约束：所有 overlay 窗口必须继承统一的穿透基类，禁止直接继承 QWidget 并自行设置窗口样式
- 换栈检验：✅ 仍然成立（统一管理是跨平台需求）

#### 本质需求5：编辑模式是唯一允许关闭穿透的场景，且必须有明确的进入/退出边界
- 来源：FACT-20, FACT-21, FACT-22
- 置信度：Probable（有较强行为证据支持）
- 不可变约束：除编辑模式外，任何时候都不应该关闭穿透；编辑模式的进入/退出必须是显式的、可追踪的
- 换栈检验：✅ 仍然成立

### 不变量（系统必须始终满足的约束）
- INV-1：overlay 可见 + 非编辑模式 → `WA_TransparentForMouseEvents=True` AND `WS_EX_TRANSPARENT` 已设置
- INV-2：overlay 可见 + 编辑模式 → `WA_TransparentForMouseEvents=False` AND `WS_EX_TRANSPARENT` 已清除
- INV-3：任何窗口重建操作后，穿透状态必须恢复到重建前的状态（不是默认穿透，而是当前状态）
- INV-4：穿透恢复操作必须验证成功，失败时必须重试，不能静默跳过

### 可替换实现选择
- 穿透机制：Qt `WA_TransparentForMouseEvents` + Win32 `WS_EX_TRANSPARENT`（当前实现，可替换为其他平台机制）
- 穿透管理：基类统一管理（当前）/ 独立穿透管理器 / 状态机（可替换）
- 编辑模式：基类 `set_edit_mode`（当前）/ 状态机 / 上下文管理器（可替换）

---

## 阶段④：塑骨（理论建模）

### 架构设计：统一穿透管理层

#### 核心原则
- 穿透状态是基类的唯一权威来源
- 所有修改窗口样式的方法被基类拦截，操作后自动恢复穿透
- 穿透恢复带验证和重试，禁止静默失败
- 所有 overlay 必须继承基类，禁止独立实现

#### 模块结构

```
ClickThroughOverlay (基类，增强)
├── 穿透状态机
│   ├── 状态：TRANSPARENT / NON_TRANSPARENT（编辑模式）
│   └── 转换：进入编辑→NON_TRANSPARENT，退出编辑→TRANSPARENT
├── 窗口样式拦截（所有方法重写）
│   ├── setWindowOpacity → super() → 恢复穿透（立即+延迟确认）
│   ├── setWindowFlags → super() → 恢复穿透（立即+延迟确认）
│   ├── setAttribute → 检查是否影响穿透 → super() → 恢复穿透
│   └── showEvent → super() → 恢复穿透（立即+延迟确认）
├── 穿透恢复机制
│   ├── _apply_click_through() → 设置 Win32 穿透 + 验证返回值
│   ├── _verify_click_through() → 检查 GetWindowLongW 是否包含 WS_EX_TRANSPARENT
│   └── 重试：验证失败时 QTimer.singleShot(10ms) 重试，最多3次
├── 编辑模式（统一实现）
│   ├── set_edit_mode(enabled) → 切换穿透状态 + 更新光标 + 超时定时器
│   └── 子类可扩展（如 RangefinderOverlay 的 MouseHook）
└── AngleOverlay 迁移为继承 ClickThroughOverlay
```

#### 穿透恢复时序（关键设计）

```
操作触发（setWindowOpacity / setWindowFlags / showEvent）
    ↓
super().xxx()  // 执行实际操作，可能触发窗口重建
    ↓
_apply_click_through()  // 立即恢复穿透
    ↓
_verify_click_through()  // 验证 Win32 样式是否正确
    ↓
验证成功？──是──→ 完成
    │
    否
    ↓
QTimer.singleShot(10ms, _apply_and_verify)  // 延迟重试
    ↓
最多重试3次
    ↓
3次都失败 → print 错误（不再静默）
```

#### 关键设计决策

1. **为什么用延迟确认而不是只立即恢复？**
   - 窗口重建后新 winId 可能尚未完全生效，立即恢复可能拿到无效 hwnd
   - 延迟 10ms 确认能覆盖时序问题
   - 来源：FACT-14, FACT-24, FACT-25, FACT-26

2. **为什么需要验证和重试？**
   - 当前 `_apply_click_through` 失败时只 print，无验证无重试
   - Win32 API 可能因各种原因失败（hwnd 无效、窗口正在重建等）
   - 验证确保穿透真的设置成功，重试覆盖瞬时失败
   - 来源：FACT-15, FACT-16

3. **为什么 AngleOverlay 必须迁移？**
   - AngleOverlay 从未设置穿透，是独立实现的维护成本和风险
   - 迁移后自动获得基类的所有穿透保护
   - 来源：FACT-8

4. **为什么删除 rangefinder_tab.py:719 的补丁？**
   - 补丁只覆盖部分场景，是补丁网络的一部分
   - 基类统一恢复后，补丁不再需要
   - 来源：FACT-17, FACT-18

#### 与现有实现的关键差异

| 方面 | 现有实现 | 新设计 |
|------|---------|--------|
| 穿透恢复 | 立即恢复，无验证 | 立即恢复 + 延迟确认 + 验证 + 重试 |
| 失败处理 | 静默 print | 验证失败重试，3次失败显式报错 |
| AngleOverlay | 独立实现，无穿透 | 继承基类，自动获得穿透 |
| 补丁 | rangefinder_tab.py:719 额外补丁 | 删除，基类统一覆盖 |
| setAttribute | 未重写 | 重写，检查是否影响穿透 |
| 穿透状态 | 隐式（_edit_mode 变量） | 显式状态机，可查询可验证 |

#### 性能影响
- 延迟确认（10ms QTimer）：每次窗口样式变更后增加一次定时器事件，开销可忽略
- 验证（GetWindowLongW）：一次 Win32 API 调用，开销可忽略
- 重试（最多3次）：只在验证失败时触发，正常路径无额外开销
- **结论：性能影响可忽略，可靠性大幅提升**

---

## 阶段⑤：重铸实现（交给执行 Agent）

### 任务清单

1. **增强 `ClickThroughOverlay` 基类**（`core/overlay_base.py`）
   - 添加 `_verify_click_through()` 方法：检查 `GetWindowLongW` 返回值是否包含 `WS_EX_TRANSPARENT`
   - 增强 `_apply_click_through()`：设置后调用 `_verify_click_through()`，失败时延迟重试（最多3次，间隔10ms）
   - 重写 `setAttribute()`：检查是否修改了 `WA_TransparentForMouseEvents`，如果是则在 super() 后恢复穿透
   - 所有窗口样式方法（setWindowOpacity/setWindowFlags/showEvent）添加延迟确认（QTimer.singleShot(10ms)）
   - `win32_utils.set_click_through` 添加返回值和错误检查

2. **迁移 `AngleOverlay`**（`gui/tabs/angle_meter_tab.py`）
   - 改为继承 `ClickThroughOverlay`
   - 删除独立的 `setWindowFlags` 和 `setAttribute` 调用（基类已设置）
   - 确认角度仪 overlay 显示后鼠标能穿透

3. **删除补丁**（`gui/tabs/rangefinder_tab.py`）
   - 删除 `rangefinder_tab.py:719` 附近的 BUG-9 第三层补丁（测距完成后强制 ensure_click_through）
   - 清理中文乱码注释

4. **验证**
   - 启动 GS，所有 overlay 显示后鼠标能穿透点击桌面
   - 信息数显：连续测距10次，每次后穿透正常
   - 信息数显：修改透明度设置，修改后穿透正常
   - 信息数显：进入/退出编辑模式，退出后穿透正常
   - 角度仪：overlay 显示后鼠标能穿透 160x80 区域
   - 准星叠加：overlay 显示后穿透正常
   - 标定测距：overlay 显示后穿透正常
   - 切换 tab 再切回，穿透正常
   - 控制台无"应用穿透失败"或"穿透验证失败"错误

---

## 阶段⑥：跃进（用户验证后决定）

待用户验证后，根据新发现的行为问题决定是否需要下一轮螺旋。
