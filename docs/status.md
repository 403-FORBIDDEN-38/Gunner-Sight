# GunnerSight 项目状态

## 版本
V0.0140300058（微调热键重新设计+全局硬编码清理完成）

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
- 角度仪热键微调+校准体系重构: 完成
- 角度仪功能修复与UI优化(B1-B3/F1/U1-U4): 完成
- 角度仪第二轮修复+空房子原则实施(P1-P3/B4/U5): 完成
- 微调热键重新设计+全局硬编码清理: 完成

## 已完成功能详情

### 角度仪热键微调功能
- RawInputReader 增加 _injected_delta_y + inject_delta_y()，consume_delta_y() 合并硬件+注入
- HotkeyManager 新增 up/down pressed/released 信号，同时注册 keydown+keyup
- angle_meter_tab 增加上移/下移热键绑定UI，长按定时器（50ms初始，0.5秒后加速到20ms，每次注入5）
- 方向：上移注入负值，下移注入正值
- AngleTracker 和 Calibrator 完全不动

### 校准体系重构
- config_manager 新增 angle_meter_global_calibration 配置；profile 校准字段重构
- Calibrator._generate_from_endpoints 改用 angle_to_delta 反查全局曲线增量相对位置
- angle_meter_tab UI重构——新增全局校准区域，载具校准改为方案选择+状态显示
- 重校全局后自动重新生成所有载具快校
- 兼容性迁移——旧 calibration 标记为 full

### 角度仪功能修复与UI优化（已完成）
- B1: reset_to_zero() 修复 angle_to_delta(0.0) 和 emit(0.0) 未调用导致的崩溃
- B2: _ensure_angle_meter_defaults 去掉空 profiles 自动恢复；delete_angle_meter_profile 允许删除最后一个；get_current_angle_meter_profile 默认值改为空字符串
- B3: 微调热键加状态检查（只在 ACTIVE/PAUSED 状态注入），避免 IDLE 状态累积无效增量
- F1: 校准开始自动最小化主窗口，完成/取消后恢复
- U1: 开始/停止合并为 toggle_use_btn，文字根据状态切换
- U2: 开始/取消校准合并为 cal_toggle_btn，文字根据校准状态切换
- U3: 热键绑定区域改为两列网格布局（左列：开始/停止、暂离、校准确认；右列：上移、下移）
- U4: 去掉"清除当前方案"按钮及 _on_cal_clear 方法

### 角度仪第二轮修复+空房子理念落地（已完成）
- 核心理念：GS 本体是空房子，删掉外部 cfg 后代码里不应有任何硬编码用户数据
- P1: 删除 AngleCalibration.FACTORY 出厂校准曲线，保留 GLOBAL_TARGETS；AngleCalibration 要求必须传入 points；未做全局校准时提示"请先做全局校准"，快速校准不可用
- P2: _default_angle_meter_segment profiles 为空字典；_ensure 不自动创建默认配置；get_angle_meter_profile_for_vehicle 找不到返回空字符串；UI 允许删除所有配置
- P3: 默认热键全部为空字符串（用户自行绑定）
- B4: 鼠标硬件增量修复 — RawInputReader 加 WA_NativeWindow 确保原生窗口接收 WM_INPUT；定时器从 0ms 改为 16ms（0ms 占满事件循环导致 nativeEvent 无法处理）
- U5: 下拉框第一项改为"点击选择校准方案"；状态标签改为"当前方案已校准/未校准"；范围变更/校准取消后统一显示"当前方案未校准"
- B4（发布必修）：鼠标硬件增量失效排查与修复
- U5（UI优化）：校准方案下拉框文字改为"点击选择校准方案"，右侧状态标签改为"当前方案已校准/未校准"

### 微调热键重新设计+全局硬编码清理（已完成）
- 任务一：微调热键从"注入 GS 内部累加器"改为"SendInput 模拟真实鼠标移动"（MOUSEEVENTF_MOVE），使游戏炮管和角度仪示数同步微调。删除注入通道（inject_delta_y/_injected_delta_y），consume_delta_y 改回只返回硬件增量。长按逻辑不变（50ms初始，0.5秒后加速20ms/5单位）。上移 dy=-1，下移 dy=+1。
- 任务二：删除 toggle_overlay 默认热键 F1，改为空字符串。全局扫描确认无其他硬编码用户数据（vehicles/tags/profiles 均为空，所有热键 key1 为空，angle_meter_global_calibration 为未校准）。
- 空房子验证：删除 cfg 后启动，所有配置列表为空，热键全空，无硬编码校准曲线。

## 审查修复记录
### 第一轮（已完成）
- F1（崩溃）: overlay.py get_state() 调用已修复，改用 StateMachine property
- U1（UI）: 缩放偏移模式从 QRadioButton 改为 QPushButton 点击切换
- U2（UI）: 去掉"重置为默认"按钮
- O1（代码质量）: 删除 _update_overlay_preview 冗余变量
- O2（代码质量）: state_machine 新增 overlay_settings_changed 专用信号

### 第二轮（已完成）
- R1（发布必修）: 切换缩放模式从载具切回全局时不生效 → 删除错误的提前 return 判断
- R2（UI）: 缩放模式切换控件从按钮改为 QCheckBox 勾选框
- R3（流程）: 执行Agent汇报精简（不超过5行），详细内容写进 docs/status.md

### 第三轮（已完成）
- U3（UI）: 缩放调整增加 QSpinBox 数值输入框，滑块与输入框双向联动
- U4（UI）: 倍率详情区域从 QFormLayout 改为 QVBoxLayout 左对齐

### 第四轮（已完成）
- U5（发布必修）: 切走再切回载具配置页时载具选中状态丢失 → 恢复选中
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
- 打包 Python: C:\Users\suncheng\AppData\Local\Programs\Python\Python313\python.exe
