# 项目状态

## 当前阶段
已完成 — 需求规格说明书 V1.0 定稿（初稿基线）

## 轮次
第 3 轮（最终轮）

## 状态流转
- [x] 主 Agent 建立协作框架
- [x] 主 Agent 完成任务规格书（task-spec.md）
- [x] 执行 Agent 读取全部 core 模块确认功能
- [x] 执行 Agent 完成需求规格说明书初稿（第2轮，58个功能点）
- [x] 主 Agent 完成审查（review.md，24/25通过，4个问题+1盲区）
- [x] 执行 Agent 按审查意见优化（第3轮，59个功能点，FR-001~059连续）
- [x] 主 Agent 复审通过（有条件通过，定稿为初稿基线）
- [x] 决策：通过

## 最终交付物
| 文件 | 说明 |
|---|---|
| output.md | 需求规格说明书 V1.0（8章+附录，59个功能点 FR-001~FR-059） |
| task-spec.md | 任务规格书（主 Agent 撰写，已修订） |
| review.md | 审查报告+决策单（主 Agent 撰写） |
| status.md | 项目状态（本文件） |
| change-request.md | 变更请求+补盲发现记录 |

## 定稿说明
- **定稿级别**：初稿基线，可用于开发参考和功能清单核对
- **已验证**：结构完整性、修改响应性、FR 字段完整性（主 Agent 独立验证通过）
- **间接验证**：内容真实性、config.json 字段准确性（基于执行 Agent 源码读取自验）
- **后续建议**：若需发布级正式文档，抽 overlay 和 config_manager 两个核心模块做源码级交叉验证

## 关键里程碑
- 第1轮：执行 Agent 发现 task-spec.md 未填写，阻塞等待
- 第2轮：主 Agent 完成规格书，执行 Agent 完成初稿（58功能点），提出2项变更请求
- 第3轮：主 Agent 审查打回4问题，执行 Agent 修复并主动补盲（新增 mouse_hook/win32_utils 基础模块），主 Agent 复审通过定稿

---

## code-review 修复阶段（执行 Agent 工作日志）

### 当前状态
- 批次1打回项(4) + 批次2(3) + 批次3(7) + 批次4(裁定) + onedir发布收尾 全部完成
- 最终版本 V0.0140300036
- 14.5 终审证据清单已交付主 Agent
- 等待主 Agent 独立终审结论，未自行发布

### 过程流水（不进对话）
- onedir spec 修改：EXE不吞binaries/datas，新增COLLECT；datas移除config/resources
- get_app_base_dir 对齐：frozen时始终返回exe_dir，不回退_internal
- 签名排查：KeyUsage参数不生效→TextExtension手动添加→确认DigitalSignature正确；UnknownError经导入受信任根验证变Valid，证明签名正确，UnknownError=NotTrusted等价
- xcj残留修复：angle_meter_tab.py:205 objectName("xcj_sep")遗漏→angle_meter_sep，触发重新打包+版本号递增036
- 26个py_compile全通过，冒烟PID 24792
- 批次5(A4/A5/A7/T2/T4)确认未改动

### 沟通分层执行
- 已读取 AGENTS.md 7.4，后续严格遵守：过程入status.md，对话只交最终交付单

---

## 第十六节修复（037）工作日志

### 修复项
- 16.1: 迁移方法按值判定（ammo/angle_meter），xcj并存分支新段空则搬入旧段数据
- 16.1.3: 抢救当前 config 4个角度仪旧热键（reset=mouse_left, pause=f8, calibrate=f6, toggle=f7）
- 16.2: HotkeyLineEdit 右键非捕获态也清除，提示文字改"(esc清除)"
- 16.3: rangefinder_tab 两个 HotkeyPairWidget 补标签（UI切换/信息截取）
- 16.4: add_ammo_type 按序预填数字键1-9，不覆盖已绑定，冲突顺延
- 16.5: rangefinder profiles 为空，无 .corrupt 备份，如实告知需用户重建
- 15.2 P1: info_tab XCJ 文案改"外置信息数显（测距）"，grep -i 无残留
- 15.2 P2: 打包前清理 __pycache__，发布版 0 个
- 图标: spec datas 添加 app_icon.ico 打进 _internal，get_app_icon_path 增加 resources 检查
- 版本: 036→037，version_info 同步
- 修复 info_tab.py/angle_meter_tab.py BOM 字符

### 验证
- 27个 .py 全部语法通过
- 发布版: exe+_internal+外置config/resources，app_icon.ico 在 _internal，__pycache__=0
- 签名: CN=403 FORBIDDEN, SHA256, DigiCert时间戳, Status=UnknownError(=NotTrusted)
- ProductVersion: V0.0140300037

---

## 第十七节修复（038）工作日志
- 17.1: 右键清除已移除，仅 ESC 清除
- 17.2: HotkeyLineEdit 支持 shift/tab/ctrl 单独绑定（keyReleaseEvent 判断待决修饰键，event() 拦截 Tab），组合键不受影响
- 17.3A: _execute_steps 模块级函数已定义（wait/press_key/click），quick_toggle_ui 与 _run_steps 共享，修复 NameError 崩溃
- 17.3B: quick_toggle_ui 加 _toggle_ui_running 重入保护，finally 重置，防止鼠标键热键自触发振荡
- 17.4: link_vf 无 profile 时不再隐藏，显示空列表
- 版本 037→038，全量编译0失败，发布版 pycache=0，签名 CN=403 FORBIDDEN

---

## 第十九节修复（039，暂不打包）工作日志
- 19.1: rangefinder_overlay + overlay 均添加 showEvent 重新 set_click_through，防止 Qt show/update 后重置扩展样式
- 19.2: quick_toggle_ui 去掉 finally 中 SetCursorPos 归位（行为变更：独立热键执行后鼠标停在无UI按钮坐标）；measure 完整流程保留归位；DEFAULT_TOGGLE_STEPS wait 容错增加(50→60,30→50,20→40)
- 19.3: 弹种热键从全局 {弹种名:hk} 改为按载具 {载具名:{弹种名:hk}}；迁移方法自动转换+批量重绑每载具从1开始；hotkey_manager 只注册当前载具弹种键；切换载具 reload_hotkeys；get/set/add/remove/rename 全部按载具维度
- 版本 038→039，全量编译0失败
- 用户要求：暂不打包，测试确认无误后再打

---

## 第二十节紧急修复（040）工作日志
- 20.1: hotkey_manager.py 顶部添加 import keyboard（此前缺失导致所有键盘热键 NameError 失效）；AST 漏导入排查未发现其他真实漏导入（其余为局部变量误报）
- 20.2: quick_toggle_ui 执行后鼠标归位到屏幕中心（GetSystemMetrics 取屏宽高，BlockInput 释放后 SetCursorPos 到中心）；measure 完整流程仍归原位
- 20.3: 叠加层穿透已确认通过（showEvent 修复），未改动
- README: 修复 XCJ 旧称为信息数显
- 版本 039→040，全量编译0失败，发布版 pycache=0，签名 CN=403 FORBIDDEN
- 注意: 打包需用 C:\Users\suncheng\AppData\Local\Programs\Python\Python313\python.exe（sandbox python 无 PyInstaller）

---

## BlockInput 残留紧急修复（041，未打包）
- 问题: 用户启动数显后出现系统输入锁定（无法点击窗口/任务栏），疑似 BlockInput(True) 异常未释放
- 根因: quick_toggle_ui / measure 中 BlockInput(True) 后，若 Python 解释器级崩溃（ctypes访问违规等），finally 可能不执行，导致输入永久锁定
- 修复1: main.py 启动时调用 BlockInput(False) 释放任何残留，atexit 注册兜底释放
- 修复2: quick_toggle_ui 使用 _blocked 标志，只在成功 BlockInput(True) 后才释放，最外层 finally 确保释放
- 修复3: 归位屏幕中心的 SetCursorPos 也放在 try-except 中，防止异常影响 BlockInput 释放
- 版本 040→041，全量编译0失败
- 待用户确认当前鼠标是否恢复，确认后打包

---

## 041 发布完成
- README: 补角度仪模块说明 + 新手教程（5分钟上手 + 进阶功能）+ 常见问题补充
- BlockInput 残留防护: main.py 启动清理 + atexit 兜底 + quick_toggle_ui _blocked 标志
- 版本 V0.0140300041，全量编译0失败，发布版 pycache=0
- 签名 CN=403 FORBIDDEN, SHA256, DigiCert时间戳, Status=UnknownError(=NotTrusted)
- 发布版结构: exe+_internal+外置config/resources+README，完整可分发

---

## 042 发布完成
- 文档打包: README.md + USER_GUIDE.md 部署到发布版 exe 同级目录（与 config/resources 并列）
- 信息页手册按钮: info_tab.py 泛化 _open_readme → _open_doc(filename) 复用，新增"用户手册"按钮（样式同 link_btn）
- 装甲与图鉴链接: main_window.py 导航栏"猜点与迫炮"下方新增"装甲与图鉴（需科学上网）"按钮，固定高度36，链接 squad-armor.com
- 版本 V0.0140300042，全量编译0失败，发布版 pycache=0
- 签名 CN=403 FORBIDDEN, SHA256, DigiCert时间戳

---

## 043 发布完成
- 信息页按钮统一: "简述说明 (README)" → "简述说明"，与"用户手册"格式一致
- 装甲与图鉴两行显示: 新增 TwoLineLink 通用组件（QWidget+双QLabel+clicked信号），主标题"装甲与图鉴"+副标题"需科学上网"小字左对齐，去掉固定高度36硬编码，高度自适应
- 版本 V0.0140300043，全量编译0失败，发布版 pycache=0
- 签名 CN=403 FORBIDDEN, SHA256, DigiCert时间戳
- 发布版含 README.md + USER_GUIDE.md + config + resources

---

## 044 发布完成（043 崩溃修复）
- 根因: main_window.py:30 import 被脚本截断 rom gui.tabs.angle_meter_tab import Angl → 应为 AngleMeterTab，导致启动 ImportError 崩溃
- 修复: 恢复 AngleMeterTab 完整导入，TwoLineLink 类与导入之间补两个空行
- 全文件截断排查: 扫描所有 .py 文件，未发现其他被截断的类名/变量名/import
- 验证方式升级: 本次实际启动 exe 冒烟测试（PID 2548，主窗口句柄 2885406，进程存活12秒+），确认无 ImportError，8页签均可加载
- 版本 V0.0140300044，全量编译0失败，发布版 pycache=0
- 签名 CN=403 FORBIDDEN, SHA256, DigiCert时间戳
- 注意: 测试进程以管理员权限运行，需手动关闭（PID 2548）

---

## 045 发布完成（044 残留修复）
- 根因: 043 脚本截断 AngleMeterTab 为两部分，044 只修复了前半部分 Angl→AngleMeterTab，第59行残留孤立的 eMeterTab 导致 NameError
- 修复: 删除第59行孤立的 eMeterTab，确认全文件无其他残留
- 启动冒烟通过: PID=6244，主窗口句柄=721740，进程存活12秒+，无 ImportError/NameError
- 版本 V0.0140300045，全量编译0失败，发布版 pycache=0
- 签名 CN=403 FORBIDDEN, SHA256, DigiCert时间戳
- 教训: 脚本编辑后必须用 grep 检查被截断标识符的所有部分，不能只修一处

---

## 046 发布完成（导航栏对齐/颜色修复）
- 根因: TwoLineLink(QWidget) 内 QLabel 设置 objectName=link_btn，但样式表选择器是 QPushButton#link_btn，只匹配 QPushButton，导致颜色不一致
- 修复: 删除 TwoLineLink 类，装甲按钮改用 QPushButton("装甲与图鉴\n需科学上网")，完全复用 link_btn 样式，与猜点与迫炮对齐一致
- 链接更新: https://squad-armor.com → https://squad-armor.com/vehicles
- 清理: 删除不再需要的 pyqtSignal 导入
- 启动冒烟通过: PID=6392，主窗口句柄=1706552，进程存活12秒+
- 版本 V0.0140300046，全量编译0失败，发布版 pycache=0
- 签名 CN=403 FORBIDDEN, SHA256, DigiCert时间戳

## 三轮崩溃修复总结（043-045）
- 043: 脚本插入 TwoLineLink 类时截断了 AngleMeterTab 导入（Angl + eMeterTab 分离），导致启动 ImportError 崩溃
- 044: 只修复了前半部分 Angl→AngleMeterTab，遗漏第59行孤立的 eMeterTab，导致 NameError 崩溃
- 045: 删除第59行残留 eMeterTab，彻底修复
- 根因教训: 脚本批量替换/插入时，标识符可能被截断为多部分，必须 grep 检查所有部分，不能只修一处
- 验证升级: py_compile 通过 ≠ 能运行，必须实际启动 exe 冒烟测试

---

## 047 源码版（单页垂直滚动式 UI，不打包）
- 架构变更: QStackedWidget 页签式 → QScrollArea 单页垂直滚动式
- 容器: QScrollArea + QWidget + QVBoxLayout，setWidgetResizable(True)，横向不滚动只垂直滚动
- 页面堆叠: 8页面按导航顺序依次 addWidget，每页前加 page_section_title 标题 + page_separator 分割线
- 导航联动: verticalScrollBar().valueChanged → 计算可视区域中心落在哪个页面 → nav_list.setCurrentRow 高亮
- 点击跳转: nav_list.currentRowChanged → verticalScrollBar().setValue(page.y()-50)，直接跳转无动画
- 防循环: _scrolling 标志位区分用户点击和滚动触发，滚动触发时不执行跳转
- 默认位置: 启动滚动条在顶部(0)，不保存/恢复滚动位置
- 性能优化: isVisible() → _is_page_visible()（检查页面是否在滚动区域可视范围内），保持概览页不可见时跳过刷新
- 嵌套滚动: Qt 默认行为，鼠标在列表上滚轮滚内层，不在列表上滚外层
- 启动冒烟通过: Python313 启动 PID=22396，主窗口句柄=3016836，进程存活15秒+，无崩溃
- 版本 V0.0140300047，全量编译0失败
- 注意: 首次冒烟用 sandbox python 失败（无 PyQt5），改用 Python313 成功

---

## 048 源码版（嵌套滚动修复 + 滚动刷新机制，不打包）
- 嵌套滚动修复: 移除5个页面(overview/hotkey/rangefinder/angle_meter/squad_macro)内层 QScrollArea，content 布局直接提升为页面主布局
- 双重边距: 页面主布局 margins=(0,0,0,0)，由外层 scroll_layout 统一控制边距
- 点击跳转: _on_nav_changed 改为跳转到页面对应标题 QLabel 的 y()，_add_page 保存标题引用，移除硬编码 50
- 死代码清理: 删除 _is_page_visible 方法，恢复 isVisible() 调用
- 滚动刷新机制: _on_scroll_changed 中页面进入可视区域时调用 refresh()（替代页签式 showEvent），_last_refreshed_page 防重复
- 跨页面刷新: vehicle_tab.data_changed 连接 hotkey_tab.refresh_ammo_hotkeys()，载具配置变更后热键页弹种列表自动刷新
- 编码修复: squad_macro_tab.py 被 PowerShell Set-Content 损坏（BOM+中文乱码），从发布版恢复后重新移除内层滚动
- 启动冒烟通过: PID=24508，主窗口句柄=1903152，进程存活15秒+，无崩溃
- 版本 V0.0140300048，全量编译0失败
- 教训: PowerShell Set-Content -Encoding utf8 会添加 BOM 并可能损坏中文，修改 Python 文件必须用 Python 脚本或 Edit 工具

---

## 049 源码版（回滚页签式 + 右侧翻页按钮，不打包）
- 回滚: 主窗口 QScrollArea 单页滚动式 → QStackedWidget 页签式
- 恢复内层滚动: 5个页面(overview/hotkey/rangefinder/angle_meter/squad_macro)恢复内层 QScrollArea
- 右侧翻页按钮: 内容区域右侧固定宽36px按钮栏，▲(上一页)/▼(下一页)垂直居中排列，32x32
- 边界隐藏: _update_page_nav_buttons(index)，第一页隐藏▲，最后一页隐藏▼
- 翻页逻辑: _go_prev_page/_go_next_page 通过 nav_list.setCurrentRow 切换，与导航点击一致
- 移除滚动代码: 删除 _on_scroll_changed/_page_titles/_last_refreshed_page/_refresh_page_if_needed/滚动样式
- 恢复 showEvent 刷新: 页签式下切换页面触发 showEvent，无需手动滚动刷新
- 启动冒烟通过: PID=288，主窗口句柄=2165212，进程存活15秒+，无崩溃
- 版本 V0.0140300049，全量编译0失败
- 教训: 恢复内层滚动时必须同时恢复 QScrollArea 导入，脚本检查 'QScrollArea' in content 会误匹配 scroll=QScrollArea() 行

---

## 050 源码版（导航初始选中修复，不打包）
- 根因: _create_ui 末尾只调用 _update_page_nav_buttons(0) 但未调用 nav_list.setCurrentRow(0)，初始 currentRow=-1
- 现象: 启动时页面在全局设置页但导航不高亮；第一次按▼只是选中第0页(currentRow -1→0)，第二次按▼才切换到第1页
- 修复: 替换为 self.nav_list.setCurrentRow(0)，触发 currentRowChanged→_on_nav_changed(0)，同时切换 tab_stack 和更新翻页按钮
- 启动冒烟通过: PID=25576，主窗口句柄=1378002，进程存活15秒+
- 版本 V0.0140300050，全量编译0失败

---

## 051 源码版（翻页按钮位置调整，不打包）
- 调整: 右侧翻页按钮从「双stretch夹中间」改为「▲顶部 + stretch撑开 + ▼底部」，一上一下分布
- 启动冒烟通过: PID=21812，主窗口句柄=1051288，进程存活15秒+
- 版本 V0.0140300051，全量编译0失败

---

## 051 发布版（打包+签名+部署）
- 打包: PyInstaller onedir，FileVersion=0.1.4.51，ProductVersion=V0.0140300051
- 签名: CN=403 FORBIDDEN 自签名证书，SHA256+时间戳，状态 UnknownError(=NotTrusted，自签名正常)
- 部署: GunnerSight_Release/ 结构正确 — config/ resources/ _internal/ GunnerSight.exe README.md USER_GUIDE.md
- 发布版冒烟通过: PID=20812，主窗口句柄=3868714，标题=GunnerSight Overlay，进程存活15秒+
- 主 Agent 审查通过，发版意见：可以打包发布

---

## 052 发布版（角度仪列表格式对齐 + 分隔线颜色）
- config_manager: 新增 get_angle_meter_profile_linked_vehicles + get_angle_meter_profile_effective_tags（与数显仪对齐）
- angle_meter_tab: _refresh_profile_list 显示 名称 (载具:XXX; 标签:XXX)，setData(Qt.UserRole, name)，blockSignals 防刷新触发选择
- angle_meter_tab: 三处 .text() 改为 .data(Qt.UserRole)（_on_profile_select/_on_rename_profile/_on_delete_profile）
- 分隔线颜色: 样式表新增 QFrame#angle_meter_sep, QFrame#rangefinder_sep，background-color={border}，替换刺眼白色
- 修复: 样式表 f-string 中普通大括号未转义导致 NameError，改为 {{ }}
- 打包: FileVersion=0.1.4.52, ProductVersion=V0.0140300052
- 签名: UnknownError（自签名正常）
- 发布版冒烟通过: PID=21332, 句柄=4130906

---

## 053 发布版（信息截取执行间隙设置）
- config_manager: 新增 get/set_toggle_ui_step_interval，配置在 rangefinder.toggle_ui_step_interval，默认50ms，范围10-1000
- rangefinder.py: quick_toggle_ui 接受可选 step_interval 参数，wait 步骤使用该值替代硬编码
- rangefinder_tab: row2 布局改为「信息截取热键(左) + 执行间隙输入框(右)」，QSpinBox 范围10-1000，步长10
- rangefinder_tab: _on_step_interval_changed 保存配置，refresh 时初始化 spin 值
- rangefinder_tab: on_toggle_ui_hotkey 传递 step_interval 给 quick_toggle_ui
- 打包: FileVersion=0.1.4.53, ProductVersion=V0.0140300053
- 签名: UnknownError（自签名正常）
- 发布版冒烟通过: PID=10028, 句柄=4589654

---

## 054 发布版（执行间隙修复：保留最后恢复等待 + 测距流程生效）
- rangefinder.py: 新增 apply_step_interval(steps, interval)，替换 wait 步骤但保留最后一个 wait（UI恢复等待），interval=None 返回原 steps
- rangefinder.py: quick_toggle_ui 改用 apply_step_interval，替换原来的列表推导式
- rangefinder.py: RangefinderEngine.toggle_ui() 从 self.config.get("toggle_ui_step_interval") 读间隙，调用 apply_step_interval 后再 _run_steps
- rangefinder_tab.py: _sync_rangefinder_config 把全局间隙合并进 engine config（cfg["toggle_ui_step_interval"]）
- 修复问题1: 调小间隙后最后200ms UI恢复等待不再被替换
- 修复问题2: 测距流程（信息截取热键）时间隙现在生效
- 打包: FileVersion=0.1.4.54, ProductVersion=V0.0140300054
- 签名: UnknownError（自签名正常）
- 发布版冒烟通过: PID=6320, 句柄=7604210
