# 当前项目状态

## 版本
V0.0140300054（载具配置页状态一致性补充修复完成）

## 测试
- 总计: 32 passed, 0 failed

## 第五轮修复记录（U5.1/U5.2）

### U5.1（发布必修）：_refresh_ammo_list 重建后不恢复之前选中的弹种
- 根因：U5 修复了载具选中恢复，但 _on_vehicle_selected 触发弹种列表重建，弹种选中状态丢失
- 修复：_refresh_ammo_list 重建前记录 previously_selected，重建后在 blockSignals(False) 之后恢复选中
- 边界：之前选中的弹种不在新列表中（载具变了）则不恢复，保持未选中

### U5.2（发布必修）：_refresh_mag_list 重建后不恢复之前选中的倍率
- 根因：_refresh_mag_list 有 select_idx 参数但 _on_vehicle_selected 调用时没传，且无自动恢复逻辑
- 修复：重建前记录 previously_selected_idx，重建后优先使用传入的 select_idx，没有则用自动恢复的
- 边界：之前选中的倍率索引超出新列表范围（弹种变了，倍率数量变少）则不恢复

## 功能完成状态
- 载具级缩放偏移功能: 完成
- 第一轮审查修复 F1/U1/U2/O1/O2: 完成
- 第二轮审查修复 R1/R2/R3: 完成
- 第三轮 UI 优化 U3/U4: 完成
- 第四轮状态一致性修复 U5: 完成
- 第五轮状态一致性补充修复 U5.1/U5.2: 完成

## 待修复问题
（无）
