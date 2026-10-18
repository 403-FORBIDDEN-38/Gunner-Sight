# VDR-Spiral：信息数显模块从零重构

> 启动时间：2026-09-07
> 触发原因：多轮补丁后截图流程仍导致鼠标无反应，补丁网络无法根治
> 范围：core/rangefinder.py 完全重写（overlay/config/UI 保持接口兼容）

---

## ② 观态（行为事实）

### 功能行为（FACT）
- F1：用户按截图热键 → MeasureThread → measure() → 返回 {roi1, roi2}
- F2：measure() 流程：BlockInput(True) → toggle_ui(显示UI) → 截图ROI1 → 截图ROI2(可选) → toggle_ui(隐藏UI) → BlockInput(False)
- F3：toggle_ui() 执行步骤列表：wait→press_key(esc)→wait→click→wait→press_key(esc)→wait
- F4：独立无UI热键 → quick_toggle_ui() → 同样步骤但不截图
- F5：截图结果显示在 RangefinderOverlay（透明置顶穿透窗口）
- F6：支持双区域截图（roi2.enabled）
- F7：配置项：roi/roi2/ui_button/display_pos/display_size/display_opacity/toggle_steps/关联载具

### 问题行为（FACT）
- P1：截图后鼠标点击桌面/窗口/任务栏无反应（反复出现≥5次）
- P2：保存配置后触发截图，bug必现
- P3：SetCursorPos 与鼠标内核驱动冲突（已改为 click_at 绝对坐标）
- P4：窗口重建后 Qt 层 WA_TransparentForMouseEvents 丢失（已修复）
- P5：BlockInput 可能因异常未释放（已加看门狗）

### 架构问题（FACT）
- A1：三条执行路径并行：quick_toggle_ui→_execute_steps；engine._run_steps→_execute_steps；engine.measure→toggle_ui→_run_steps→_execute_steps
- A2：模块级全局状态 _toggle_ui_running 与实例状态混合
- A3：BlockInput 在 quick_toggle_ui 和 measure() 中分别管理，无统一入口
- A4：RangefinderEngine._click/_press_key 是死代码（_run_steps 调用 _execute_steps）
- A5：quick_toggle_ui 不使用引擎实例，与引擎 measure() 可能并发冲突

---

## ③ 反推（本质需求）

### 本质需求
- N1：用户需要在游戏中快速截取指定区域并显示结果（来源：F1,F5）
- N2：截图前后需切换游戏UI状态（ESC+点击）（来源：F2,F3）
- N3：截图过程中需防止用户输入干扰（来源：F2 BlockInput）
- N4：输入锁定必须可靠释放，任何异常路径下不得永久锁定（来源：P1,P5）——不可变约束
- N5：悬浮窗必须穿透鼠标（来源：P2,P4）——不可变约束
- N6：配置可保存/切换/关联载具（来源：F7）
- N7：独立无UI切换与截图共享同一套步骤执行逻辑（来源：F3,F4）

### 不变量
- INV-1：measure() 退出时 BlockInput 必须为 False（无论正常/异常/中止）
- INV-2：所有模拟输入操作（按键/点击）必须在 BlockInput 锁定期间执行
- INV-3：overlay 可见且非编辑模式时，Qt+Win32 双层穿透必须同时生效
- INV-4：截图流程与独立切换流程共享步骤执行器，不得有两套实现

---

## ④ 塑骨（新架构）

### 核心设计原则
1. 单一权威：RangefinderEngine 是唯一执行入口，消除模块级全局状态
2. 资源生命周期：InputLock 上下文管理器管理 BlockInput，__exit__ 保证释放
3. 步骤执行器内聚：_execute_step 是引擎方法，不再暴露模块级函数
4. 兼容层：quick_toggle_ui 保留为模块级函数，内部委托给引擎单例

### 模块结构
```
core/rangefinder.py
├── InputLock (上下文管理器)
│   ├── __enter__ → BlockInput(True) + 5秒看门狗
│   └── __exit__ → BlockInput(False) + 取消看门狗 (永远执行)
├── RangefinderEngine
│   ├── set_config(config)
│   ├── measure() → {roi1, roi2}
│   │   └── with InputLock(): toggle_ui(); capture; toggle_ui()
│   ├── toggle_ui() → 执行步骤列表
│   ├── _execute_step(step) → wait/press_key/click
│   ├── _capture(roi) → PIL.Image
│   ├── abort() / close()
│   └── _running (实例级重入保护，替代模块级全局)
├── quick_toggle_ui(x, y, step_interval) — 兼容层，委托引擎单例
└── MeasureThread(QThread) — 保持不变
```

### 与旧实现关键差异
| 方面 | 旧实现 | 新实现 |
|------|--------|--------|
| 执行入口 | 3条路径（quick/_run_steps/_execute_steps） | 1条（engine._execute_step） |
| BlockInput | 两处分别管理 | InputLock上下文管理器统一 |
| 全局状态 | _toggle_ui_running模块级 | _running实例级 |
| 死代码 | _click/_press_key | 删除 |
| 重入保护 | 模块级全局 | 实例级+线程锁 |

---

## ⑤ 重铸实现

见 core/rangefinder.py 完全重写。

---

## ⑥ 跃进（验证清单）
- 截图流程正常：截图→显示结果→鼠标可点击
- 独立无UI切换正常
- 保存配置后截图正常
- 连续截图10次无异常
- 截图中按中止热键正常退出
- BlockInput异常时5秒看门狗恢复
- pytest无回归
