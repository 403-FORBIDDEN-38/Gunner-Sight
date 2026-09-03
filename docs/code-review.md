# 当前轮审查意见：载具级缩放偏移功能修复

## 功能完成状态

载具级缩放偏移功能三步已全部完成（配置层+逻辑层、UI层、测试），32个测试全部通过。但存在1个崩溃级bug和若干UI/流程问题，需修复后才能验收。

## 审查发现

### F1（发布必修）：overlay.py 调用不存在的方法，切换倍率崩溃

**位置**：`core/overlay.py` 第280行

**问题**：`_update_effective_overlay` 方法中调用 `self.state.get_state()`，但 StateMachine 没有 `get_state()` 方法。StateMachine 提供的是三个 property：`current_vehicle`、`current_ammo_type`、`current_magnification_index`。

**崩溃信息**：
```
AttributeError: 'StateMachine' object has no attribute 'get_state'
```

**触发条件**：任何触发 `_on_state_changed` 的操作（切换倍率、切换弹种、切换载具、refresh_overlay）都会崩溃。

**修复要求**：
- 删除 `state = self.state.get_state()` 及后续的 `state.get(...)` 调用
- 改用 `self.state.current_vehicle`、`self.state.current_ammo_type`、`self.state.current_magnification_index`
- 修复后验证：切换倍率不崩溃，缩放偏移正确切换

### U1（应做）：缩放偏移模式开关从单选按钮改为点击切换

**位置**：`gui/tabs/vehicle_config_tab.py` 第118-129行

**问题**：当前用 QRadioButton + QButtonGroup 实现全局/载具切换。用户明确不需要第三种配置，单选按钮组语义过重（暗示有多个选项），且占用空间。

**修复要求**：
- 去掉 `mode_global_radio`、`mode_vehicle_radio`、`mode_group`
- 改用一个 QPushButton，文字动态显示当前模式：
  - 当前全局时显示："缩放偏移：全局（点击切换为载具）"
  - 当前载具时显示："缩放偏移：载具（点击切换为全局）"
- 点击按钮在全局/载具间切换，切换后更新配置、列表项文本、实时预览
- 按钮可设置不同样式区分两种模式（如全局时灰色，载具时蓝色），但非强制

### U2（应做）：去掉"重置为默认"按钮

**位置**：`gui/tabs/vehicle_config_tab.py` 第159行、第203行、第577-583行

**问题**：用户认为载具偏移缩放是低频改动，重置为默认无必要，去掉可简化UI。

**修复要求**：
- 去掉 `vo_reset_btn` 控件及其布局
- 去掉 `_on_reset_vehicle_overlay` 方法
- 去掉 `vo_reset_btn.clicked.connect` 信号连接
- config_manager 的 `reset_vehicle_overlay` 方法保留（API完整性，测试仍覆盖），只是UI不再调用

### O1（小问题）：_update_overlay_preview 有冗余变量

**位置**：`gui/tabs/vehicle_config_tab.py` 第597行

**问题**：`effective = self.config.get_effective_overlay(vehicle, ammo, idx)` 计算了但从未使用。下一行直接调用 `self.state.refresh_overlay()`，refresh_overlay 会触发 `_on_state_changed`，在那里重新计算 effective_overlay。

**修复要求**：删除第597行的冗余变量计算。

### O2（建议，可选）：refresh_overlay 信号语义不清

**位置**：`core/state_machine.py` 第105-107行

**问题**：`refresh_overlay()` 通过发射 `magnification_changed` 信号来触发 overlay 刷新，但倍率实际上没有变化。语义上不够清晰。

**修复要求（可选）**：
- 新增一个专用信号 `overlay_settings_changed = pyqtSignal()`
- `refresh_overlay()` 改为发射 `overlay_settings_changed`
- overlay.py 中连接 `overlay_settings_changed` 到 `_on_state_changed`（或单独的处理方法）
- 此为代码质量优化，不影响功能，可做可不做。如果做，确保 `magnification_changed` 的原有连接不受影响

## 流程要求

### P1：执行结果必须写入 docs/status.md

每次完成功能或修复后，执行 Agent 必须更新 `docs/status.md`，记录：
- 当前版本
- 功能完成状态
- 测试结果
- 待修复问题

不允许只在对话里汇报而不更新项目文档。

## 验收标准

修复完成后，按以下清单验收：

### 功能验收
- [ ] 切换倍率不崩溃（F1修复验证）
- [ ] 切换弹种不崩溃
- [ ] 切换载具不崩溃
- [ ] 倍率选"全局"时，overlay 使用全局缩放偏移
- [ ] 倍率选"载具"时，overlay 使用当前载具的缩放偏移
- [ ] 二选一，不叠加
- [ ] 载具缩放偏移修改时实时预览（当前倍率选载具时）
- [ ] 缩放偏移模式按钮点击切换全局/载具，文字动态更新
- [ ] "重置为默认"按钮已移除

### 测试验收
- [ ] 现有32个测试全部通过（15原有 + 17新增）
- [ ] 如新增了 overlay_settings_changed 信号，确保相关测试通过

### 代码质量验收
- [ ] overlay.py 不再调用 get_state()
- [ ] _update_overlay_preview 无冗余变量
- [ ] 无审查编号写入代码注释
- [ ] docs/status.md 已更新

## 交付格式

修复完成后按以下格式汇报：

```
【载具缩放偏移修复】完成状态
- 修复了哪些问题：（F1/U1/U2/O1/O2逐项说明）
- 验收结果：PASS / FAIL
- 证据：（git commit hash / pytest输出 / 崩溃验证截图）
- docs/status.md 是否已更新：是/否
- 遇到的问题：（无则写"无"）
```

全部完成后输出最终汇总：
- git log --oneline 修复相关提交
- pytest tests/ -v 最后5行
- 验收清单逐项勾选结果
