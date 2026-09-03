# 当前项目状态

## 版本
V0.0140300054（载具级缩放偏移功能已修复）

## 测试
- tests/test_config.py: 15 passed
- tests/test_vehicle_overlay.py: 17 passed
- 总计: 32 passed, 0 failed

## 功能完成状态
- 载具级缩放偏移功能: 完成（三步全部完成）
- 审查修复 F1/U1/U2/O1/O2: 完成

## 审查修复记录
- F1（崩溃）: overlay.py get_state() 调用已修复，改用 StateMachine property
- U1（UI）: 缩放偏移模式从 QRadioButton 改为 QPushButton 点击切换
- U2（UI）: 去掉"重置为默认"按钮
- O1（代码质量）: 删除 _update_overlay_preview 冗余变量
- O2（代码质量）: state_machine 新增 overlay_settings_changed 专用信号，refresh_overlay 语义清晰

## 待修复问题
（无）
