# 当前轮审查意见：载具缩放偏移第三轮 UI 优化

## 背景

载具级缩放偏移功能及前两轮审查修复已完成（F1/U1/U2/O1/O2 + R1/R2/R3），32个测试通过，R1切回全局不生效已修复。用户实际使用中发现2个UI优化问题。

## 审查发现

### U3（应做）：缩放调整增加数值输入框，支持精确微调

**位置**：`gui/tabs/vehicle_config_tab.py` 第128-137行（载具缩放偏移区域的缩放行）

**当前实现**：
```python
scale_layout = QHBoxLayout()
scale_layout.addWidget(QLabel("缩放:"))
self.vo_scale_slider = QSlider(Qt.Horizontal)  # 滑块
self.vo_scale_value = QLabel("100%")            # 纯显示，不能输入
```

**问题**：只有滑块，只能粗调，精确到 87% 这种数值很难拖准。X/Y 偏移已用 QSpinBox，缩放反而没有，不一致。

**修复要求**：
- 把 `vo_scale_value`（QLabel）改成 `vo_scale_spin`（QSpinBox）
- QSpinBox 设置：范围 1-1000，后缀 "%"，初始值 100
- 滑块和输入框双向联动：
  - 滑块 `valueChanged` → 更新 QSpinBox 数值（需 blockSignals 防止循环）
  - QSpinBox `valueChanged` → 更新滑块位置（需 blockSignals 防止循环）
  - 两者都触发配置保存（`set_vehicle_overlay`）和预览刷新（`_update_overlay_preview`）
- `_update_vehicle_overlay_ui` 中刷新数值时，滑块和 QSpinBox 都要 blockSignals 后设置
- 去掉原来的 QLabel，布局变为：`缩放: [滑块] [100%]`

### U4（应做）：倍率详情区域控件对齐优化

**位置**：`gui/tabs/vehicle_config_tab.py` 第113-121行（倍率详情区域 mag_detail_layout）

**当前实现**：用 QFormLayout（表单布局，标签列+控件列）
```python
mag_detail_layout = QFormLayout()
mag_detail_layout.addRow("准星图片:", self.mag_crosshair_label)  # 有标签
mag_detail_layout.addRow("", self.mag_bind_btn)                    # 空标签
mag_detail_layout.addRow("", self.overlay_mode_check)              # 空标签
```

**问题**：QFormLayout 标签列有固定宽度，第一行有标签"准星图片:"占据左列，后两行标签为空，导致按钮和勾选框从控件列开始，与上面的准星图片名不在同一视觉起点，看起来参差不美观。

**修复要求**：
- 把 `mag_detail_layout` 从 QFormLayout 改成 QVBoxLayout（垂直布局，全部左对齐）
- 第一行（准星图片）：用 QHBoxLayout 放两个 QLabel：`QLabel("准星图片:")` + `self.mag_crosshair_label`
- 第二行（选择按钮）：`self.mag_bind_btn` 直接 addWidget，左对齐
- 第三行（勾选框）：`self.overlay_mode_check` 直接 addWidget，左对齐
- 三行从同一位置开始，视觉整齐
- 注意：`mag_detail_layout` 的类型变了，相关代码中如果有 `addRow` 调用都要改成 `addWidget` 或 `addLayout`

## 验收标准

修复完成后按以下清单验收：

### U3 验收
- [ ] 缩放行有滑块和数值输入框（QSpinBox），布局为 `缩放: [滑块] [100%]`
- [ ] 拖动滑块，数值输入框同步更新
- [ ] 修改数值输入框，滑块位置同步更新
- [ ] 拖动滑块或修改数值，overlay 预览实时更新（当前倍率选载具时）
- [ ] 切换载具时，滑块和数值输入框都正确刷新为该载具的配置
- [ ] 数值输入框范围 1-1000，有 % 后缀

### U4 验收
- [ ] 倍率详情区域三行（准星图片、选择按钮、勾选框）左对齐，视觉整齐
- [ ] 准星图片行显示 `准星图片: lav25`（或未绑定）
- [ ] 选择准星图片按钮左对齐
- [ ] "该倍率使用载具缩放配置"勾选框左对齐
- [ ] 切换倍率时，准星图片名和勾选框状态正确刷新

### 通用验收
- [ ] 现有32个测试全部通过
- [ ] R1（切回全局不生效）仍然正常（连续切换全局→载具→全局→载具都正确响应）
- [ ] docs/status.md 已更新
- [ ] 执行Agent对话汇报不超过5行

## 交付格式

修复完成后按以下格式汇报（不超过5行）：

```
【载具缩放偏移第三轮 UI优化】PASS/FAIL
- commit: xxxxxxx
- 测试: 32 passed
- 详见 docs/status.md
```

详细内容（修复了什么、验收清单逐项）写进 docs/status.md。
