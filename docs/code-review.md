# 当前轮审查意见：载具配置页状态一致性修复（补充）

## 背景

U5（载具选中状态恢复）已修复，但修复不完整：切回载具页时载具选中了，但弹种和倍率均未选中。根因是 `_on_vehicle_selected` 触发弹种/倍率列表重建，而这两个列表重建时没有恢复之前的选中状态。

## 审查发现

### U5.1（发布必修）：_refresh_ammo_list 重建后不恢复之前选中的弹种

**位置**：`gui/tabs/vehicle_config_tab.py` `_refresh_ammo_list` 方法

**当前实现**：
```python
def _refresh_ammo_list(self):
    vehicle = self._get_selected_vehicle()
    self.ammo_list.blockSignals(True)
    self.ammo_list.clear()
    if vehicle:
        for ammo in self.config.get_ammo_types(vehicle):
            item = QListWidgetItem(ammo)
            item.setData(Qt.UserRole, ammo)
            self.ammo_list.addItem(item)
    self.ammo_list.blockSignals(False)
```

**问题**：清空列表后重新填充，但不恢复之前选中的弹种。载具选中恢复后，`_on_vehicle_selected` 调用此方法，弹种选中状态丢失。

**修复要求**：
- 重建列表**前**，记录当前选中的弹种名：
  ```python
  previously_selected = self._get_selected_ammo()
  ```
- 重建列表（现有逻辑不变）
- 重建后，如果 `previously_selected` 不为空且在新列表中存在，重新选中：
  ```python
  if previously_selected:
      for i in range(self.ammo_list.count()):
          if self.ammo_list.item(i).data(Qt.UserRole) == previously_selected:
              self.ammo_list.setCurrentRow(i)
              break
  ```
- 恢复选中必须在 `blockSignals(False)` 之后执行，否则 `currentItemChanged` 信号不触发，倍率列表不会刷新
- 如果之前选中的弹种不在新列表中（比如载具变了，弹种列表完全不同），则不恢复，保持未选中——合理行为

### U5.2（发布必修）：_refresh_mag_list 重建后不恢复之前选中的倍率

**位置**：`gui/tabs/vehicle_config_tab.py` `_refresh_mag_list` 方法

**当前实现**：有 `select_idx` 参数，但 `_on_vehicle_selected` 调用时没传，所以没生效。方法内部也没有自动恢复之前选中的逻辑。

**修复要求**：
- 重建列表**前**，记录当前选中的倍率索引：
  ```python
  previously_selected_idx = None
  item = self.mag_list.currentItem()
  if item:
      previously_selected_idx = item.data(Qt.UserRole)
  ```
- 重建列表（现有逻辑不变）
- 重建后，如果 `previously_selected_idx` 不为空且在新列表范围内，重新选中：
  ```python
  if previously_selected_idx is not None and 0 <= previously_selected_idx < self.mag_list.count():
      self.mag_list.setCurrentRow(previously_selected_idx)
  ```
- 恢复选中必须在 `blockSignals(False)` 之后执行
- 注意：`_refresh_mag_list` 已有 `select_idx` 参数，优先使用传入的 `select_idx`（如果调用方显式指定了），没有传入时才用自动恢复的 `previously_selected_idx`。逻辑：
  ```python
  target_idx = select_idx if select_idx is not None else previously_selected_idx
  if target_idx is not None and 0 <= target_idx < self.mag_list.count():
      self.mag_list.setCurrentRow(target_idx)
  ```
- 如果之前选中的倍率索引超出新列表范围（比如弹种变了，倍率数量变少），则不恢复，保持未选中——合理行为

## 验收标准

修复完成后按以下清单验收：

### 功能验收
- [ ] 选中载具甲→弹种a→倍率1 → 切走 → 切回 → 载具甲、弹种a、倍率1三者都仍选中，可继续编辑
- [ ] 选中载具甲→弹种a→倍率2 → 切走 → 切回 → 三者都仍选中，倍率是2不是1
- [ ] 切换载具（甲→乙）时，弹种列表正确刷新为乙的弹种，如果乙有弹种则默认选中第一个（或保持之前选中的如果存在），倍率列表对应刷新
- [ ] 切换弹种（a→b）时，倍率列表正确刷新为b的倍率，如果b有倍率则默认选中第一个
- [ ] 载具没有弹种时，弹种列表为空，倍率列表为空，不崩溃
- [ ] 弹种没有倍率时，倍率列表为空，不崩溃
- [ ] 第一次打开载具配置页（无之前选中）时，列表正常显示，不崩溃

### 测试验收
- [ ] 现有32个测试全部通过
- [ ] U3（缩放数值输入框）、U4（倍率详情对齐）仍然正常

### 流程验收
- [ ] docs/status.md 已更新
- [ ] 执行Agent对话汇报不超过5行

## 交付格式

修复完成后按以下格式汇报（不超过5行）：

```
【载具配置页状态一致性补充修复】PASS/FAIL
- commit: xxxxxxx
- 测试: 32 passed
- 详见 docs/status.md
```

详细内容（修复了什么、验收清单逐项）写进 docs/status.md。
