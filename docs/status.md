# GunnerSight 项目状态

## 版本
V0.0140300055（角度仪热键微调+校准体系重构完成，待冒烟测试）

## 测试
- tests/test_config.py: 15 passed
- tests/test_vehicle_overlay.py: 17 passed
- 总计: 32 passed, 0 failed

## 功能完成状态
- 载具级缩放偏移功能: 完成
- 第一轮审查修复 F1/U1/U2/O1/O2: 完成
- 第二轮审查修复 R1/R2/R3: 完成
- 第三轮 UI 优化 U3/U4: 完成
- 第四轮状态一致性修复 U5/U5.1/U5.2: 完成
- 角度仪热键微调+校准体系重构: 完成（代码修改完成，待冒烟测试）

## 当前轮任务完成详情

### 角度仪热键微调功能（阶段1-3）
- 阶段1: RawInputReader 增加 _injected_delta_y + inject_delta_y()，consume_delta_y() 合并硬件+注入
- 阶段2: HotkeyManager 新增 up/down pressed/released 信号，同时注册 keydown+keyup
- 阶段3: angle_meter_tab 增加上移/下移热键绑定UI，长按定时器（50ms初始，0.5秒后加速到20ms，每次注入5）
- 方向：上移注入负值（AngleTracker中 -consume = 正角度），下移注入正值
- AngleTracker 和 Calibrator 完全不动

### 校准体系重构（阶段4-7）
- 阶段4: config_manager 新增 angle_meter_global_calibration 配置；profile 校准字段重构（calibration_type/quick_calibration/quick_min_delta/quick_max_delta/full_calibration）；12个新方法
- 阶段5: Calibrator._generate_from_endpoints 改用 angle_to_delta 反查全局曲线增量相对位置，复刻非线性形状
- 阶段6: angle_meter_tab UI重构——新增全局校准区域（状态+按钮+说明），载具校准改为方案选择（下拉框：未校准/快速/单独）+状态显示+开始/清除按钮；_on_cal_done区分全局/载具校准；重校全局后自动重新生成所有载具快校
- 阶段7: 兼容性迁移——旧 calibration 字段无 calibration_type → 标记为 full，数据移入 full_calibration；_merge_config 递归补全新字段

## 关键设计决策
- 热键微调在输入源层注入（RawInputReader），校准和使用自动都生效，防错逻辑自动覆盖
- 快速校准算法：用全局曲线 angle_to_delta(global_angle) 反查真实增量，计算相对位置后映射到载具范围，复刻全局曲线非线性形状
- 重校全局后：有 quick_min_delta/quick_max_delta 的载具快校自动重新生成；无 min_delta 的旧快校保留；独校不受影响
- 两种方案数据独立保存，切换不丢失

## 待修复问题
（无，当前为新功能开发完成，待冒烟测试）

## 审查修复记录
### 第一轮（已完成）
- F1（崩溃）: overlay.py get_state() 调用已修复，改用 StateMachine property
- U1（UI）: 缩放偏移模式从 QRadioButton 改为 QPushButton 点击切换
- U2（UI）: 去掉"重置为默认"按钮
- O1（代码质量）: 删除 _update_overlay_preview 冗余变量
- O2（代码质量）: state_machine 新增 overlay_settings_changed 专用信号

### 第二轮（已完成）
- R1（发布必修）: 切换缩放模式从载具切回全局时不生效 → 删除 _update_overlay_preview 中错误的提前 return 判断
- R2（UI）: 缩放模式切换控件从按钮改为 QCheckBox 勾选框"该倍率使用载具缩放配置"
- R3（流程）: 执行Agent汇报精简（不超过5行），详细内容写进 docs/status.md

### 第三轮（已完成）
- U3（UI）: 缩放调整增加 QSpinBox 数值输入框，滑块与输入框双向联动
- U4（UI）: 倍率详情区域从 QFormLayout 改为 QVBoxLayout 左对齐

### 第四轮（已完成）
- U5（发布必修）: 切走再切回载具配置页时载具选中状态丢失 → _refresh_vehicle_list 恢复载具选中
- U5.1: _refresh_ammo_list 恢复弹种选中
- U5.2: _refresh_mag_list 恢复倍率选中

## 流程整改进度
- [x] P0-1 git 初始化
- [x] P0-2 文件归位归档
- [x] P0-3 清理审查编号
- [x] P0-4 测试骨架
- [x] P1-5 简化双Agent流程
- [x] P1-6 验收checklist

## 环境备注
- 系统未安装 git，使用 dulwich（纯 Python git 实现）替代
- python 命令指向 Windows Store 占位符，使用 py 启动器（py -m pytest）
