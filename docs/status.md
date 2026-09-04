# GunnerSight 项目状态

## 版本
V0.0140300061（3点快校+微调三档+性能日志完成）

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
- 校准途中微调热键修复: 完成
- 微调参数调整+快校调试日志: 完成
- 3点快校+微调三档+性能日志: 完成

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

### 校准途中微调热键修复（已完成）
- 根因：B3 修复时在 _on_up_pressed/_on_down_pressed/_on_up_tick/_on_down_tick 中加了"只在 ACTIVE/PAUSED 状态才触发"的状态检查，在新设计（SendInput 模拟鼠标移动）下不适用，导致校准途中（CALIBRATING 状态）热键被拦截。
- 修复：删除4处状态检查，热键在任何状态下都触发 _simulate_mouse_move（保留空指针检查）。
- 验证：使用途中热键正常；校准途中按热键→游戏炮管移动→按确认→校准点包含微调增量；校准开始前按热键第一个点不受影响（start 时清零）；校准取消后按热键不影响后续校准。

### 微调参数调整+快校调试日志（已完成）
- 任务一：微调参数调整
  - 长按判定：0.5s → 0.8s（用按下时间戳判定，不再用 QTimer.singleShot）
  - 加速后步长：5 → 2
  - 加速后间隔：20ms → 30ms
  - 点按步长：确认1（SendInput最小单位）
  - 删除 _enable_up_accel/_enable_down_accel 死代码方法
- 任务二：快校不准定位
  - 算法检查4个原因：①全局曲线增量随角度增加而增加（next_point中delta_step=-consume_delta_y()，上移为正），min_delta/max_delta按角度排序正确；②快校端点顺序正确（先最低角后最高角）；③微调热键SendInput上移dy=-1被RawInput捕获后delta_step为正，与物理一致；④angle_to_delta假设角度单调递增，全局曲线满足。未发现明显bug。
  - 添加临时调试日志：全局校准完成时输出全局曲线7个点；快校完成时输出全局曲线、快校端点(min_delta/max_delta)、生成的7个点及delta_to_angle值。用print输出到控制台，待用户提供输出后分析不准原因。

### 校准途中微调热键修复（当前轮，待执行）
- 问题：使用途中微调正常，校准途中热键无效
- 根因：B3 修复时加的状态检查"只在 ACTIVE/PAUSED 状态触发"在新设计（SendInput 模拟鼠标移动）下不适用，校准途中被拦截
- 修复：删除 _on_up_pressed/_on_down_pressed 中的状态检查，热键在任何状态下都触发 SendInput
- 校准途中增量自然累积在 RawInputReader，Calibrator.next_point() 消费时计入

### 微调参数调整+快校不准定位（当前轮，待执行）
- 任务一（应做）：微调参数调整 — 长按判定从0.5s改为0.8s，加速步长从5改为2，加速间隔从20ms改为30ms，确认点按步长为1
- 任务二（发布必修）：快校不准定位 — 添加临时调试日志（全局曲线点、快校端点、生成曲线点），检查4个可能原因：全局曲线增量方向、快校端点顺序、校准途中微调增量方向、angle_to_delta非单调处理。发现明显bug直接修复。

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

### 3点快校+微调三档+性能日志（已完成）
- 任务一：3点快校 - 快校从2点改为3点（最低角/中间角/最高角），分段映射算法，配置保存三个端点，重校全局后重新生成，旧2点配置兼容
- 任务二：微调热键三档 - 点按(步长1单次)/短长按(1.0-1.5s步长1间隔50ms)/长长按(>1.5s步长2间隔30ms)，时间戳判定档位
- 任务三：性能日志 - 启动/关闭关键节点加计时日志，只测量不优化

### P0性能优化（已完成）
- P0-1: 字体加载延迟到窗口显示后，窗口先用系统默认字体显示，字体加载完成后自动切换
- P0-2: ConfigManager加配置版本号(CURRENT_CONFIG_VERSION=3)，迁移函数只在版本变化时执行，已迁移配置跳过所有迁移
- P0-3: 关闭时热键注销简化，直接keyboard.unhook_all()，删除先unhook单个钩子的重复操作
- 版本: V0.0140300062

### 任务四：退出卡顿优化+UI文字修复（已完成）
- P0-4: 退出卡顿优化 - rangefinder SHUTDOWN_WAIT_MS 1000->200ms，closeEvent quit前加tab_stack.deleteLater()主动删除所有tab
- P0-5: 快校文字 快速校准（2点）->快速校准（3点）
- P0-6: 去掉思源黑体加载，只保留Norwester英文字体，中文自动回退系统字体
- 版本: V0.0140300063

### 任务一：启动性能彻底优化（已完成）
- P0-1: Tab懒加载 - _create_ui只创建第一个tab，其余7个在首次点击导航时创建；_ensure_tab(index)懒加载+8个property兼容属性访问；_connect_tab_signals延迟连接tab特有信号；closeEvent只遍历已创建的tab
- P0-2: Overlay延迟创建 - OverlayRenderer.__init__不创建窗口(self.overlay=None)，_ensure_overlay()懒加载创建并同步状态；所有操作overlay的方法前调用_ensure_overlay或检查None；main.py窗口显示后100ms异步预创建
- 预期效果: MainWindow创建从984ms降到约150-200ms，Overlay初始化从271ms降到约10ms，启动总耗时从1473ms降到约400-500ms
- 版本: V0.0140300064

### 启动性能修复（已完成）
- 删除main_window.py启动时主动创建RangefinderTab的代码(self._ensure_tab(3).refresh())
- 改为main.py window.show()后QTimer.singleShot(0, lambda: window._ensure_tab(3).refresh())异步创建
- 任务二检查: _connect_signals无意外创建tab，Overlay预创建(QTimer.singleShot(100))已存在
- 预期: MainWindow创建919ms->200-300ms，启动总耗时1374ms->400-500ms
- 版本: V0.0140300065

### 启动性能系统性修复（已完成）
- P0-1: 修复懒加载index错位 - _on_nav_changed用setCurrentWidget(widget)替代setCurrentIndex(index)
- P0-2: 消除重复QSS - 删除__init__中提前的_setup_style()调用，只保留_apply_theme()
- P0-3: OverviewTab数据延迟加载 - __init__删除refresh()，main.py窗口显示后QTimer.singleShot异步refresh
- P1-1: 所有tab数据加载移到showEvent - squad_macro/angle_meter/rangefinder添加_data_loaded标志，首次显示时加载数据；热键注册保留在__init__（启动时可用）；vehicle_config/hotkey/resource已有showEvent加载
- P1-2: tab创建加异常保护 - _ensure_tab中try-except包裹widget创建，失败时显示错误提示
- 预期: MainWindow创建908ms->150-250ms，启动总耗时1315ms->300-450ms
- 版本: V0.0140300066

### 建队宏页面崩溃修复（已完成）
- 根因: squad_macro_tab._build_ui中setChecked触发_on_enable_changed→hotkey.reload_hotkeys()，__init__阶段热键未初始化导致崩溃
- 修复: enable_cb/interval_spin/locked_cb初始值设置用blockSignals包裹，避免__init__阶段触发信号
- 修复: _ensure_tab异常保护逻辑修正，widget创建失败时不尝试连接信号
- 版本: V0.0140300067

### 启动性能完整优化（7项全部执行）
- 优化1 QSS分阶段: _setup_minimal_style+_setup_full_style，窗口显示后异步应用
- 优化2 消除focus遍历: 删除_disable_control_focus，QSS加focus:none/clickfocus规则
- 优化3 refresh_preview延迟: showEvent中QTimer.singleShot异步加载准星预览
- 优化4 VehicleFilterWidget延迟: OverviewTab中_ensure_vehicle_filter懒加载
- 优化5 提权消除: _request_admin移到main()入口，避免import时触发
- 优化6 容器简化: 审查后无明显冗余容器（已用layout嵌套）
- 优化7 Config迁移跳过: config_version=3已实现，最新版本跳过迁移
- 额外优化: 第一个tab(OverviewTab)延迟创建到window.show后，MainWindow创建790ms->3ms
- 实测: MainWindow创建3ms，第一个tab创建14ms，完整QSS 64ms
- 版本: V0.0140300068

### 修复 Unknown property focus 报错（已完成）
- 根因: Qt QSS不支持focus属性，优化2中错误添加了focus:none/focus:clickfocus
- 修复: 从QSS移除focus属性，恢复_disable_control_focus方法，改为异步执行（window.show后）
- 实测: 焦点策略仅2ms，无Unknown property focus输出
- 版本: V0.0140300069

### 启动性能根本性重构（P0-P3完成）
- P0: show()1060ms根因=__init__创建框架控件导致首次绘制慢
- P1: __init__只设窗口属性+极简背景色，show后分阶段异步创建(_create_ui_frame->_create_first_tab->_background_tasks)
- P2: QSS从90行简化到45行，合并重复选择器
- P3: OverviewTab已轻量化(VehicleFilterWidget延迟创建+preview延迟加载)
- 实测: MainWindow创建2ms, show()293ms, 启动总耗时486ms(优化前1200ms)
- UI框架创建629ms(异步用户无感知), 后台任务延迟100ms执行
- closeEvent加_ui_initialized保护
- 版本: V0.0140300070

### V0.0140300072 - Tee NoneType 崩溃修复
- 根因: console=False打包后sys.stdout为None，_Tee(None, _log_file)写入时None.write()崩溃
- 修复: _Tee.__init__过滤None文件描述符，write/flush加try-except保护
- commit: 9996a47c
- 打包: onedir + 签名，发布版 GunnerSight_Release 已合并更新

### V0.0140300073 - 角度仪BUG修复
- BUG-1: 关联载具后不立即刷新。根因: _on_linked_vehicle_changed修改linked_vehicles后未调用_refresh_profile_list。修复: 末尾添加_refresh_profile_list()调用。
- BUG-2: 配置列表标签筛选下拉框无法展开/无功能。根因: profile_tag_filter是未完成功能(无信号连接、无标签填充、无筛选逻辑)。修复: 参照rangefinder_tab完整实现——addItem带data、currentIndexChanged连接_refresh_profile_list、_refresh_profile_list中动态填充标签+按标签筛选。
- CFG校准数据: 已保留(全局校准7点 + 2个载具配置各7点quick校准)，未覆盖未重置。
- 测试: 32 passed
- commit: 129e101e
- 打包: onedir + 签名，发布版 GunnerSight_Release 已更新

### V0.0140300074 - BUG-3修复
- BUG-3: 角度仪俯仰范围输入框无法输入数字和滚轮调节。根因: min_spin/max_spin被设为Qt.NoFocus，无法获得焦点导致键盘输入和滚轮事件失效。修复: 从NoFocus列表移除，改为Qt.ClickFocus。
- CFG校准数据: 已保留(全局校准7点 + 2个载具配置各7点)，未覆盖。
- 测试: 32 passed
- commit: 02555202
- 打包: onedir + 签名，发布版已更新

### V0.0140300075 - FEATURE-1: 取消全局校准，每载具单曲线
- 配置层: 删除angle_meter_global_calibration，删除calibration_type/quick_calibration/full_calibration，每载具只有calibration_points+calibration_point_count(3/5/7/9/11)
- 逻辑层: AngleCalibration删除NUM_POINTS/GLOBAL_TARGETS；AngleTracker删除全局校准分支，calibration必须是载具曲线；Calibrator重构为单模式start(num_points,min,max)直接采集N点
- UI层: 删除全局校准UI和快校/独校选择，改为校准点数下拉框(3/5/7/9/11)；列表显示已校准N点/未校准
- 迁移: config_version 3->4，旧quick_calibration/full_calibration->calibration_points，全局校准数据丢弃。实测AAA/MK19各7点校准数据保留
- 测试: 32 passed
- commit: 41f18d92
- 打包: onedir + 签名，发布版已更新

### V0.0140300076 - FEATURE-1补充: 各精度方案独立保存可切换
- 配置层: calibrations字典{3/5/7/9/11: points} + active_calibration_point_count + pitch_min/pitch_max(不设硬限制-180~180)
- 逻辑层: 角度查询用active方案曲线; 修改pitch范围清空所有方案; 新增get_all_calibration_status/clear_all_calibrations/set_active_calibration_point_count
- UI层: 校准点数下拉框改为3/5/7/9/11按钮组(可切换, 已校准显示✓); 俯仰角范围-90~90改为-180~180
- 迁移: config_version 4->5, 单方案calibration_points->calibrations[count], min/max_angle->pitch_min/max。实测AAA/MK19校准数据保留
- 测试: 32 passed
- commit: 0e443a5f
- 打包: onedir + 签名，发布版已更新

### V0.0140300077 - BUG-4+BUG-5+UI-1+UI-2+代码质量严查
- BUG-4: _execute_steps中time.sleep被截断为裸引用(无调用), 修复为time.sleep(0.02), UI切换点击恢复正常
- BUG-5: showEvent只在首次加载刷新, 改为每次显示都刷新关联载具列表(载具页标签变更即时同步)
- UI-1: 角度仪列表校准状态改为'已校准(7点)'/'未校准'格式
- UI-2: 归零键下方加注释'适用于开火后角度归于水平的武器'
- 代码质量7项: 异常处理多为合理资源清理; -80/80为profile默认值非限制; 无重复造轮子(rangefinder/angle_meter为独立模块配置); 32 passed
- commit: 5d18d4f0
- 打包: onedir+签名, 发布版已更新

### V0.0140300078 - BUG-5二次修复+UI修正+FEATURE-2
- BUG-5根因: vehicle_config_tab._on_tag_check_changed/_on_rename_tag修改标签后未发射data_changed信号; main_window中data_changed只连了overview_tab未连angle_meter_tab。修复: 标签变更后emit data_changed; main_window连接vehicle_tab.data_changed->angle_meter_tab.on_vehicle_data_changed; angle_meter_tab新增on_vehicle_data_changed刷新关联载具和配置列表
- UI-1: 角度仪配置列表去掉校准状态显示(已校准/未校准), 校准状态只在校准设置区域显示
- UI-2: 归零键注释从整行上方改为归零键正下方(reset_col垂直布局包含reset_row+hint)
- FEATURE-2: 资源库新增'导入文件夹'按钮, 递归遍历子文件夹, 支持png/jpg/jpeg/bmp/gif/webp, 同名跳过, 导入后显示成功/跳过统计
- 测试: 32 passed
- commit: df8aad41
- 打包: onedir+签名, 发布版已更新

### V0.0140300079 - FEATURE-2修正: 资源库自动扫描子文件夹
- 删除上一版'导入文件夹'按钮及_on_import_folder方法(用户需求重新明确: 不是按钮导入, 是自动扫描resources子文件夹)
- resource_manager.list_resources改为rglob递归扫描, 返回相对路径(如subfolder/image.png); import_resource重复检查也改为递归
- resource_tab新增'刷新'按钮, 点击清除缓存重新扫描; 懒加载缓存(_resource_cache), 首次打开页面时扫描, 切换页面不重复扫描
- 导入/删除/重命名后自动清除缓存; 性能: rglob扫描几百张图片约10-50ms
- 测试: 32 passed
- commit: f7e51b0b
- 打包: onedir+签名, 发布版已更新

### V0.0140300080 - BUG-6准星不显示修复(严重回归)
- 根因: 用户把准星图片从resources顶层移动到子文件夹后, 配置中存储的仍是顶层文件名; _migrate_crosshair_paths只在config_version变化时执行, 且顶层文件不存在就直接清空引用, 导致get_current_crosshair返回不存在的路径
- 修复1: _migrate_crosshair_paths中顶层文件不存在时改为rglob递归搜索子文件夹, 找到则更新为相对路径(如'任意/Dot.png'), 找不到才清空
- 修复2: _migrate_crosshair_paths移出版本判断, 每次启动都执行(幂等, 已存在的引用不重复处理)
- 验证: get_current_crosshair返回resources/任意/Dot.png, path exists=True
- ResourceManager底层路径逻辑未被污染: list_resources递归扫描返回相对路径, get_resource_path用resources_dir/filename支持相对路径, 与ConfigManager一致
- 测试: 32 passed
- commit: 321f46dd
- 打包: onedir+签名, 发布版已更新

### V0.0140300081 - BUG-7数显频率+BUG-8穿透丢失根源性彻查
#### BUG-7根因: rangefinder.py和squad_macro.py中共10处time.sleep被截断为裸引用(与BUG-4同类批量编辑损伤)
- rangefinder.py: _click方法2处(SetCursorPos后/mouse_event LEFTDOWN后), _press_key方法1处(keybd_event按下后), measure方法2处(toggle_ui后/截图后动作间容错)
- squad_macro.py: _paste方法2处(Ctrl按下后/V按下后), activate_window方法1处(ShowWindow后), alt_tab方法2处(Alt按下后/Tab按下后)
- 影响: 裸引用不执行等待, UI切换/按键操作可能失败需重试, 整体流程变慢; 测距流程中点击UI按钮无响应导致截取失败
- 修复: 全部恢复为time.sleep(0.01~0.05)实际调用
#### BUG-8根因: overlay.py中两个重复showEvent方法, 后者(延迟50ms版本)覆盖前者(立即应用版本)
- line 66: showEvent立即调用_apply_click_through()
- line 237: showEvent用QTimer.singleShot(50, ...)延迟应用穿透
- Python类中后定义的同名方法覆盖前者, 导致实际生效的是延迟版本, show后50ms内窗口已显示但无穿透
- 修复: 删除重复的延迟版本, 保留立即应用版本
#### 适配: 发布版config同步到开发版
- 发布版有4个角度仪配置(AAA示例/MK19/AGS/QLZ87), 开发版只有2个, 已同步(含校准数据)
- resources无发布版独有文件, 开发版3个临时截图文件不同步
- 测试: 32 passed
- commit: ca74c035
- 打包: onedir+签名, 发布版已更新

### V0.0140300082 - 全量扫描3问题根源性彻查
#### 问题1: time.sleep调用链确认
- 共15处sleep: rangefinder.py 9处, squad_macro.py 6处
- squad_macro.py全部6处在后台线程(threading.Thread daemon), 保留
- rangefinder.py中measure()的2处动作间容错在MeasureThread后台线程, 保留
- rangefinder.py中_execute_steps/_click/_press_key的7处被quick_toggle_ui和_run_steps共享
  - _run_steps路径在MeasureThread后台线程, 保留
  - quick_toggle_ui路径在热键回调(主线程), 原直接调用会阻塞UI事件循环
- 修复: on_toggle_ui_hotkey改用threading.Thread(daemon=True)执行quick_toggle_ui
#### 问题2: 异常吞没审查
- 共23处except:pass(含多行)
- 22处合理清理保护(钩子释放/BlockInput恢复/SetCursorPos恢复/信号disconnect/窗口关闭/回调异常/配置重命名), 保留
- 1处危险操作吞没: rangefinder.py quick_toggle_ui中BlockInput(True)失败仍继续模拟鼠标
- 修复: BlockInput(True)失败改为打印警告+重置重入标志+return中止
- resource_tab.py图标加载失败pass加注释说明
#### 问题3: 自验流程改进
- 新增tools/static_scan.py静态扫描工具
- 检查项: 裸函数引用(如time.sleep无括号)/重复方法定义/except危险吞没/可能未使用import
- 每次提交前必须运行, 结果写入status.md
- 当前扫描结果: 0 ERROR, 0 WARN, 9 INFO(均为可能未使用import的误报)
- 测试: 32 passed
- commit: 433d23ba
- 打包: onedir+签名, 发布版已更新

### FEATURE-3距离测算模块原型（不并入主程序，不打包）
- 文件: core/distance_meter.py(逻辑层), core/distance_overlay.py(悬浮窗口), gui/tabs/distance_meter_tab.py(设置页)
- 测试入口: tools/test_distance_meter.py(独立启动), tools/test_distance_meter_logic.py(9项单元测试全通过)
- 状态机: DISABLED -> ENABLED_UNCALIBRATED -> CALIBRATING_WAIT_B -> CALIBRATED -> MEASURING_WAIT_D
- 3个热键: 启用/记录(比例尺标定两点)/测算(距离测量两点), 记录与测算分开支持一次标定多次测距
- 悬浮窗口: 透明置顶鼠标穿透, 双击进入拖动模式, 位置可配置持久化
- 配置: 独立JSON文件(distance_meter_test.json), 不影响主程序config.json
- 禁硬编码: 比例尺/热键/悬浮位置/颜色全部可配置
- 未修改main.py/main_window.py, 未注册到tab导航, 未加入PyInstaller打包
- 验证: 9项逻辑测试全通过(像素距离/状态机/标定/测距/多次测距/重新标定/禁用无响应/持久化/比例尺重置)
- commit: 85f9fc6e
- 版本号不变(原型不并入主程序)

### FEATURE-3原型修复5项（不并入主程序，不打包）
- 修复1: HotkeyLineEdit支持鼠标按键(左/右/中/侧键1/侧键2)+特殊键(CapsLock/NumLock/ScrollLock/Insert/Delete/Home/End/PageUp/PageDown/方向键等), grabMouse捕获鼠标点击
- 修复2根因: 热键绑定后只保存到配置, 从未注册全局热键! 新增GlobalHotkeyManager类, 键盘用keyboard库add_hotkey注册, 鼠标用MouseHook全局钩子注册, 注册失败打印错误日志
- 修复3: 悬浮窗口从220x70缩小为一行文本(高度28px, 宽度自适应内容120~400px), 显示格式'状态 | 结果', 保持点击穿透
- 修复4: 默认悬浮位置从x=100,y=100改为x=100,y=200, 保留可配置性
- 修复5: 移除'重置标定'按钮, 新增'比例尺标定'按钮, 点击调用start_calibration()自动清除旧标定→进入等待点A状态→悬浮提示'请记录比例尺第1点', 标定中可再次点击重新开始
- DistanceMeter新增start_calibration()方法
- 验证: 11项逻辑测试全通过(新增start_calibration/默认位置2项)
- commit: d5fa5d2b
- 版本号不变(原型不并入主程序)

### FEATURE-3原型二次修复3项（不并入主程序，不打包）
- 修复1(严重崩溃)根因: keyboard库add_hotkey的回调在钩子子线程执行, 回调中操作QWidget(通过status_callback->overlay)导致Qt跨线程崩溃! 修复: 键盘热键callback包装为QTimer.singleShot(0, cb)转到主线程执行; 鼠标热键本身是Qt信号自动主线程无需改
- 修复2: DistanceMeter新增get_status_text()方法返回完整状态文本(未启用/未标定|请按记录热键标定/标定中|请记录第2点/已标定|XXX像素=XXXm/测距中|请记录目标第2点/已标定|距离:XXXm), 悬浮窗口启动时立即调用_update_overlay_state显示状态, 不再空白
- 修复3: 移除设置页'比例尺标定'按钮及_on_start_calibration方法, 标定流程完全通过热键完成(启用->记录热键2次), 设置页只保留比例尺输入+3热键绑定+悬浮位置
- 验证: 12项逻辑测试全通过(新增get_status_text各状态测试)
- commit: 9fa70c1e
- 版本号不变(原型不并入主程序)

### FEATURE-3原型三次修复2项（不并入主程序，不打包）
- 修复1悬浮常显: __init__中默认启用(未启用则toggle)+立即创建显示悬浮窗口; 记录/测算热键回调中未启用时自动启用; 提取_create_overlay方法复用; 启用热键保留(日后并入GS需要)
- 修复2比例尺斜线修正: 标定点B时计算dx=|x2-x1|,dy=|y2-y1|, dx>=dy取dx(横向)否则取dy(竖向), 忽略手抖在次轴的偏移; calibration_direction存入config并在get_status_text显示'已标定(横向/竖向)'; 测距仍取直线距离sqrt(dx^2+dy^2)不做修正
- 验证: 13项逻辑测试全通过(新增斜线修正测试: 横向取dx/竖向取dy/测距直线距离)
- commit: 6920f806
- 版本号不变(原型不并入主程序)

### FEATURE-3原型四次修复2项（不并入主程序，不打包）
- 修复1(需求澄清)启用与悬浮解耦: __init__中移除默认启用toggle, 悬浮窗口仍常显; 启用热键只切换'是否响应标定/测距热键'状态, 不控制悬浮窗口显示/隐藏; 悬浮窗口始终显示当前状态
- 修复2(bug)未启用不响应热键: 移除_on_record_hotkey/_on_measure_hotkey中'未启用时自动启用'逻辑(上一轮错误添加); 未启用时回调检查enabled, 不执行标定/测距, 悬浮窗口提示'未启用 | 请先按启用热键'; 启用热键是唯一启闭入口
- 验证: 13项逻辑测试全通过(DistanceMeter层DISABLED检查已覆盖, tab层新增enabled前置检查)
- commit: 2769bc8d
- 版本号不变(原型不并入主程序)

### FEATURE-3原型五次修复4项（不并入主程序，不打包）
- 修复1: 移除设置页'启动/关闭悬浮窗口'按钮及_toggle_test_overlay方法, 悬浮窗口模块启动时常显, 设置页只保留比例尺输入+3热键绑定+悬浮位置
- 修复2热键组合键容错: 废弃keyboard.add_hotkey(精确匹配单键), 改用keyboard.hook全局事件监听+_pressed_keys集合边沿检测, 多键同时按下时目标键被按下即触发(不要求其他键松开), 按住不重复触发; 键盘回调仍QTimer.singleShot转主线程
- 修复3标定/测距独立: 移除record_point中MEASURING_WAIT_D打断测距的分支, 移除measure_point中CALIBRATING_WAIT_B打断标定的死代码分支; 多次标定: CALIBRATED状态按记录键自动清除旧标定数据(pixels_per_meter/calibrated_pixels/direction/last_result)开始新标定; 多次测距: 完成后按测算键自动开始新测距(保留标定数据)
- 修复4悬浮文字精简: get_status_text重写为'状态 | 下一步提示/结果'格式, 移除比例尺数值重复显示/冗余描述, 示例: 未启用|请按启用热键 / 未标定|请按记录热键标定第1点 / 标定中|请按记录热键标定第2点 / 已标定(横向)|请按测算热键测距第1点 / 测距中|请按测算热键测距第2点 / 已标定|距离:600m
- 验证: 15项逻辑测试全通过(新增标定/测距独立+多次标定测距2项, 修复多次标定未清旧数据bug)
- commit: e97bc599
- 版本号不变(原型不并入主程序)
