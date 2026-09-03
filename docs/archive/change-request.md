# 变更说明

## 第 2 轮变更请求（已处理）

### 问题 1：task-spec.md 中列出的模块与源码实际不符
- log_overlay、xcj、xcj_overlay 在源码中不存在
- 主 Agent 已确认并从 task-spec.md 移除

### 问题 2：信息数显与测距仪重复列出
- 两者是同一模块（rangefinder.py + rangefinder_overlay.py）
- 主 Agent 已确认并合并

---

## 第 3 轮补充发现（执行 Agent 主动报告）

### 发现 1：主 Agent review 存在盲区
review.md 指出了4个问题，但**未发现**初稿遗漏了 mouse_hook / win32_utils 的独立功能点。这两个模块在初稿中仅出现在架构图、模块划分表、外部接口表和附录目录结构中，第3章功能需求没有独立章节和功能点。

修订后的 task-spec.md 已补上 3.10 基础模块，执行 Agent 已按新规格补充 FR-048（共享低级鼠标钩子）和 FR-049（Win32 窗口样式工具）。

**建议主 Agent 复审时关注**：是否还有其他 core 模块在第3章中没有独立功能点。当前 11 个 core 模块对应关系：
- overlay.py → 3.1 ✅
- config_manager.py → 3.2 ✅
- hotkey_manager.py → 3.3 ✅
- state_machine.py → 3.4 ✅
- 载具/弹种/倍率（分布在 config_manager + state_machine）→ 3.5 ✅
- rangefinder.py + rangefinder_overlay.py → 3.6 ✅
- angle_meter.py → 3.7 ✅
- squad_macro.py → 3.8 ✅
- resource_manager.py → 3.9 ✅
- mouse_hook.py + win32_utils.py → 3.10 ✅（本轮补充）
- GUI → 3.11 ✅

### 发现 2：特殊适配行为全覆盖
经检查，项目中的特殊适配行为（BlockInput、Raw Input、数据迁移、防抖保存、图片缓存、MD5去重、细粒度信号、常闭零消耗、settings_container禁用模式）在各自模块的功能点中均有明确描述，无遗漏。
