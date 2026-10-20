# GunnerSight 变更日志

> 按时间线记所有动作（含回退）。HANDOVER.md 只写当前状态，需要更新时从软件状态 + 本日志里挑有价值的事总结。
"有价值的 CHANGE_LOG"：
什么算有价值——只保留两类——(a) 已回退的方案及其失败原因；(b) 影响架构/接口/数据格式的改动。 其余（改个字符串、调个颜色、重写一个函数）不总结。

---

## 2026-10-20 文档：cfg 兼容性条款更新

- HANDOVER §配置：从"不存在配置迁移/向后兼容，软件从未发布"改为"配置必须向后兼容，软件已发布"
- 原因：2026-10-18 软件已开源发布，用户手上有旧 cfg
- 规则：加字段不需要迁移（默认值兜底），删字段或改语义需标 breaking change 并说明影响

---

## 2026-10-20 适配设置页：适配逻辑下拉框独立于模式

### 改动

- `adapt_tab.py`：把 sx/sy 的"增加/拉伸"下拉框从 custom_widget 移到独立行，预设和自定义模式下均可用
- 之前：预设模式下拉框被禁用，想换拉伸必须切自定义手填 sx/sy
- 现在：预设模式下直接切适配逻辑，数值仍由档位+宽高比自动计算
- cfg 无变化，`sx_adapt_mode`/`sy_adapt_mode` 本就是独立字段

---

## 2026-10-20 用户手册第二轮错误修正 + git 历史清理

### USER_GUIDE.md 错误修正（7 处）

1. 删"全局组合键前缀 Ctrl"（1-5 和附录 C 两处）——代码里无此概念，大 agent 写手册时编造
2. 暂离描述从"两套独立状态"改为"移交退出权"——按另一个暂离键会转移退出权，再按新键退出
3. 弹种图片从"替换分划"改为"叠加层之一，与倍率图多层叠加"
4. 倍率添加从"输入名称 1x/4x/8x"改为"直接添加，自动命名第 N 档"——GUI 无输入名称对话框
5. 载具图片从"仅用于列表识别"改为"可作为叠加层显示，与弹种/倍率图多层叠加"
6. 比例尺从"页面上填写数值"改为"热键循环切换四档：33/100/300/900m"

### 代码有但 GUI 未开放的功能

- 倍率重命名：`update_magnification(label=)` 接口存在，cfg 手动改 label 仍生效，GUI 无入口。保留不砍。

### git 历史重写

- 删除 AGENTS.md、docs/ 全部、_tmp 临时脚本、version_info.txt、GunnerSight.spec
- 替换全部历史中的本地用户路径
- force push 覆盖远程

---

## 2026-10-18 数值范围统一 + 角度仪 overlay 语义变更 + 手册错误修正

### 准星面板载具列表拉伸修复

根因：`overview_tab._build_ui` 末尾 `layout.addStretch()` 吃掉所有剩余空间，载具组 stretch 链全没传 1。修复 5 处联动（含通用组件 `widgets.py::VehicleFilterWidget`），载具配置页中栏列表同样受益。

### 数值范围统一：准星/独立偏移 ±500 → ±2000

- `overview_tab.py`：全局偏移 LinkedSpinSlider (-500,500) → (-2000,2000)
- `vehicle_config_tab.py`：独立偏移 QSpinBox (-500,500) → (-2000,2000)
- 原因：4K 屏 ±500 不够用

### 角度仪 overlay 语义变更（breaking change）

- 从屏幕绝对坐标（0~9999，左上角原点）改为相对屏幕中心偏移（±2000）
- `_show_overlay` / `_on_overlay_pos_changed` 改为 `move(center.x()+ox, center.y()+oy)`
- 默认位置从 (100,100) 改为屏幕中心 (0,0 偏移)
- 影响：已有用户 config 里存的绝对坐标值会被解释为偏移量，位置会变。无自动迁移。

### 用户手册错误修正（USER_GUIDE.md）

1. 反色：从"切换式"改为"按住式"（config 里 trigger='hold'，按下松开各触发一次 toggle）
2. 出厂预设：从"LAV-6 / SMK"改为"AAA 示例载具 / AP"（与 current_state 一致）
3. 放大镜预设：从"不会跨重启保存"改为"会跨重启保存"（config 里 current_preset 非空）
4. 分辨率挡位：从"出厂预配 1K"改为"点识别当前屏后自动匹配"
5. 配置迁移：从"不做配置迁移"改为"只补全新字段默认值，不做版本间格式转换"

### 版本

V0.0140300174 → V0.0140300175

### DEDICATION 纪念（三层）

- 源码：`info_tab.py` 加 `DEDICATION = "Dedicated to Xiaocheng"`，信息页版本号下面一行灰色小字
- exe 属性：`build.bat` 加 `--copyright="Copyright © 2026 [403 FORBIDDEN]. Dedicated to Xiaocheng."`，Windows 文件属性→详细信息可见
- cfg：已有 `my_beloved: "Xiaocheng"` 受保护字段（base.py `_PROTECTED_CONFIG_KEYS`）

### 素材版权声明（无敌大甲）

- 新增 `CREDITS.md`：通用 blanket statement，覆盖所有素材（版权归原作者、非商业用途、48小时下架、免责担保）
- `README.md` 加"素材版权声明"节
- `info_tab.py` 加一行短声明

### build.bat 改进

- 转 UTF-8 with BOM + CRLF（cmd.exe 才能正确解析 © 字符）
- 动态读取版本号：`for /f` 从 `info_tab.APP_VERSION` 转换为 Windows 4段格式（V0.0140300177 → 0.14.3.177）
- 加 `--product-version`（Nuitka 要求提供 copyright 时必须同时提供版本号）
- 加 `--include-data-files=CREDITS.md=CREDITS.md`（打进发布包）
- 踩坑：`--windows-legal-copyright` 不是有效参数，正确的是 `--copyright`

### 版本

V0.0140300175 → V0.0140300177

### 打包 V0.0140300177

备份 → py_compile + pytest 29 passed → build.bat（Nuitka 4.2.1，zig 后端）→ robocopy /MIR 覆盖桌面版。exe 版权属性验证通过，CREDITS.md 已进包。

---

## 2026-10-18 滚轮边界 bug + GitHub 开源 + my_beloved 保护 + 手册文风讨论

### 滚轮切弹种桌面焦点边界 bug（已闭环，非代码 bug）

**现象**：鼠标焦点在 Windows 桌面时滚轮无法触发弹种预选，其他窗口正常。

**排查**：加临时日志确认——`fg=Notepad` / `fg=Qt5152QWindowIcon`（软件自身）时 `[MouseHook] WHEEL` 正常 emit 且 `_on_wheel` 正常响应；桌面前台时段底层钩子零条日志。

**结论**：WH_MOUSE_LL 低级钩子在前台为桌面（Progman/WorkerW）时收不到 WM_MOUSEWHEEL，Windows 系统层行为，代码层无解。已记入 HANDOVER §十三。

**教训**：项目用 `from core.logger import logger`（loguru），不是标准库 `logging`。第一次加日志误用 logging 导致 NameError。

### 打包 V0.0140300174

清理临时日志改了 .py，按 AGENTS §6 升版本。单箭头流程：备份 → py_compile + pytest 29 passed + audit_docs 30/30 → build.bat（Nuitka）→ robocopy /MIR 覆盖桌面版。

### 项目安全检查（开源前）

- 凭据扫描：全项目 grep api_key/secret/token/password/bearer/sk- 等，0 匹配
- 依赖：pyproject.toml 仅 5 个（PyQt5、Pillow、keyboard、loguru、mss），全本地库
- 网络请求：0 匹配 requests/urllib/socket/websocket/QNetworkAccessManager。两处 URL（squadcalc.app、squad-armor.com）通过 QDesktopServices.openUrl() 调系统浏览器，用户主动点击
- 打包产物 464 文件，无 .pdb/.env/.key/.pem
- 结果：PASS 7 / UNKNOWN 2（Git 历史扫描当时无 git CLI；干净环境启动未实测）/ FAIL 0

### Git 安装与 GitHub 开源

- winget 安装 Git.Git 2.55.0.windows.5
- 项目已有 .git（从 V0.0140300054 起完整历史，最新提交 9860d90），V0.0140300086 后大规模重构未提交
- 配置 git 身份：user.name=403-FORBIDDEN-38, user.email=3117023693@qq.com, core.autocrlf=false
- 创建/更新 .gitignore（排除 dist/、backups/、logs/、构建日志、__pycache__、AGENTS.md 等；config/config.json 不排除——是项目核心数据应公开）
- 基线提交 c856842：566 files changed, +25474 / -7213
- 推送到 https://github.com/403-FORBIDDEN-38/Gunner-Sight.git（master 分支）
- 随后清理仓库：git rm --cached AGENTS.md（本地保留，加 .gitignore）、删 airsoft 版 USER_GUIDE.md、git mv USER_GUIDE_formal.md → USER_GUIDE.md，force push 覆盖

### my_beloved 受保护配置字段

用户在 cfg 骨架 `_get_minimal_skeleton()` 加了 `"my_beloved": "Xiaocheng"`，要求加保护防止被误删。

**第一次实现的 bug**：把兜底逻辑写进递归的 `_merge_config()`，导致递归到 vehicles 子字典时也执行 `loaded.setdefault("my_beloved", ...)`，给 vehicles 字典加了 my_beloved 键（值是字符串）。`get_vehicle_names_filtered` 遍历到这个键 → `get_vehicle_tags` 调 `.get()` 抛 `AttributeError: 'str' object has no attribute 'get'` → VehicleConfigTab 创建失败。

**修法**：受保护兜底从 `_merge_config` 移到 `load_config` 顶层（合并完成后执行一次）。模块级常量 `_PROTECTED_CONFIG_KEYS = {"my_beloved": "Xiaocheng"}`（base.py）。config.json 磁盘未被污染（污染只在内存），29 passed。

### 用户手册文风讨论（进行中，未动手）

- 参考 KAC 真铁手册中文译制版（KAC_SR25_真铁手册_中文译制版.docx）
- 当前 USER_GUIDE.md 是真铁版（722 行，LF），有真铁的壳但缺魂
- 差距分析（6 维）：安全语气偏软、缺工作原理章节、操作步骤是叙述性散文而非编号 SOP、缺功能检查环节、排错是散文而非表格矩阵、有讨好语言
- 打磨方向（用户已确认方向，待执行）：①安全章硬化 ②加工作原理节（含已知边界）③核心操作改编号 SOP ④排错改表格矩阵 ⑤删讨好语言 ⑥PMCS 表格化
- 用户偏好：通读一遍过、不回看不重看、去人化去误差的纪律性
- 详见 HANDOVER §十一・六

---

## 2026-10-17 角度仪第三轮 + 准星常闭修复 + 定角装填修复

### OverlayRenderer.hide()/show() 不再改 state

**根因**：`OverlayRenderer.hide()` 不只是隐藏窗口，还调 `state.set_overlay_visible(False)`。关闭软件时 `closeEvent` 里调 `overlay.hide()` → state 被改成 False → `save_config()` 保存 False → 下次启动准星常闭。

**修法**：`hide()`/`show()` 只控制窗口显隐（`set_visible`），不改 state。state 由用户操作（按钮/热键）通过 `state.set_overlay_visible()` 改变，再通过 `overlay_toggled` 信号控制窗口。

**影响**：所有调 `overlay.hide()` 的地方（关闭、tab shutdown、角度仪停止使用等）不再改变用户的准星偏好。

### 角度仪微调：短按延迟 + 长按连发

**根因**：使用模式下 `on_pressed` 立刻走一格 + 60ms 后连发，想精确点一次 0.1° 很难（手指停留超过 60ms 就变成连发）。

**修法**：
- 短按（<400ms 松开）：松开时走一格
- 长按（≥400ms）：400ms 时走第一格，之后每 50ms 连发
- 校准时保持原逻辑（立刻走一格，1s 后连发）
- 滚轮直接走一格，不起定时器

### 术语"归零"→"定角装填"

UI 文本和注释全部更名（复选框"启用定角装填"、热键"定角装填热键"、日志"[角度仪] 定角装填"）。config 键名 `auto_reset`、代码变量/函数/信号名全部保留（牵连 12 处，不值得改）。

### 定角装填启用状态不随 profile 切换

**根因**：`_load_profile_params` 切换 profile 时漏了恢复 `auto_reset_check` 的勾选状态和 `hk_reset` 的启用状态。

**修法**：加 4 行恢复代码（blockSignals 防递归）。

### 排版

- 校准设置：灵敏度挪到第一行（精度方案 | 校准状态 | 灵敏度），开始校准按钮单独一行全宽
- 角度仪配置：2 行（最低角 | 最高角 | 启用定角装填 | 提示 | 热键单独一行）

---

## 2026-10-16 B1 清理路径逐项隔离 + 日志门控 + 测试红线

### B1：清理路径逐项隔离

**根因**：AGENTS §2.1「中断即泄漏」——清理方法里任何一行抛异常，后面的清理都不执行。3 处 tab 的关闭路径（角度仪 / 放大镜 / 建队宏）是裸调，第 1 个 `.stop()` 抛异常 → 后面的 `raw.close()`（mss 句柄）永不执行。

**修法**：
- 抽 `core/cleanup.py::safe_call(name, fn)`（5 行纯函数：try/except + logger.warning）
- 3 处 tab 关闭路径改用 safe_call 逐项隔离
- 角度仪 `_shutdown_engine` 顺序重排：`raw.close`（OS 级 mss 句柄）提到最前——越贵的资源越先释放，不依赖异常发生就产生收益
- `_GrabWorker.stop` 的 wait 超时加 warning（**只报告不恢复**：线程真没退出时 mss 句柄依然泄漏，QThread 无安全 terminate）
- `_FineTuner.stop` 不改（单动作，隔离无意义）

**测试边界**：mock 测的是"前一步失败后一步仍执行"（代码路径），不是"OS 资源真的释放了"（靠代码审查）。

### 日志门控

文件 sink 级别从 `INFO（GS_DEBUG 升 DEBUG）` 改成**永远 DEBUG**；控制台 sink 保持 `WARNING（GS_DEBUG 升 DEBUG）`。排错时不需要先设环境变量。

### 测试红线

AGENTS §4 测试红线 20 → 30。原值是直觉值，B1 后契约测试达 29 且都非实现细节测试，据实调整。

---

## 2026-10-14 SSOT 残留 S1/S2/S3 全部修复

### S1：载具页 getter 回落 state

**根因**：`vehicle_config_tab._get_selected_vehicle/_ammo` 从 `list.currentItem()` 取 UserRole，列表空时返回 None。筛选无结果（如 PMC 空标签）时列表空，但 state 保持原值——详情区空白。

**修法**：两个 getter 列表无选中时回落到 `state.current_vehicle` / `state.current_ammo_type`。语义从"读列表"变成"读 state，列表空时回落"。45 处调用点未动。

**设计取舍**：筛选只过滤列表，不改变"当前载具"。筛选无结果时详情区显示 state 的载具（虽然列表里看不到它）。

### S2：hotkey_manager 绕过 state

**根因**：`hotkey_manager.py` 两处 `self.config.get_current_state().get("vehicle")` 绕过 StateMachine 直读 config。

**修法**：改成 `self.state.current_vehicle`。hotkey_manager 已持有 self.state，两行改动。

### S3：放大镜当前 preset 无持有者

**根因**：`config.magnifier` 只有 get/set_magnifier_presets（dict 操作），没有 current_preset 持有者。"当前是哪个 preset"完全靠 UI 列表选中，重启后选中态丢失。

**修法**：
- `config.magnifier` 加 `current_preset` 键 + `get/set_current_magnifier_preset`（默认 `""`）
- `magnifier_tab._on_preset_select` 加幂等短路（值没变不写 config，避免高频搜索触发 request_save）
- `_refresh_preset_list` 改选中恢复逻辑：从 config 读 current，在结果里恢复；不在且非空选第 0 行；空不选
- 删除 / 重命名 preset 时同步处理 current_preset（参照角度仪 `current_profile`）
- 删掉 `refresh()` 里手动调的 `_on_preset_select`（双调冗余）

---

## 2026-10-11 屏幕适配公式修正 + 倍率详情切弹种不更新

### 屏幕适配公式修正

**根因**：`_adapt_factors()` 里用的是 `self._resource_w` / `self._resource_h`（硬编码 2560/1440），而不是 `self._display_w` / `self._display_h`（用户设置的分辨率挡位）。`set_display_resolution()` 设的是 `_display_w` / `_display_h`，但 `_adapt_factors()` 读的是 `_resource_w` / `_resource_h`。所以切换分辨率挡位时，sx/sy 不跟着变。

**第一次修反了方向**：改成 `屏幕宽 / 挡位宽`，用户纠正后改成 `挡位 / 基准`。

**最终公式**：
```python
sx = (self._display_w or self._resource_w) / self._resource_w
sy = (self._display_h or self._resource_h) / self._resource_h
```
- 2K 挡位 = 1.0（不缩放）
- 1K 挡位 = 0.75
- 4K 挡位 = 1.5
- 删掉了 `cur_w` / `cur_h`（屏幕物理宽），纯按「挡位 / 基准」算

### 倍率详情切弹种不更新

**根因**：`on_external_ammo_changed` 里只调了 `_refresh_mag_list()`，没调 `_update_mag_detail()`。倍率继承时索引不变，`_on_mag_user_selected` 里 `idx == state.current_magnification_index` 直接 return，不发信号，所以倍率详情的三个勾选框（独立偏移/叠加载具图片/叠加弹种图片）停留在旧弹种的值。

**修法**：在 `on_external_ammo_changed` 末尾加 `self._update_mag_detail()`。

**双调分析**：倍率索引回退时会双调，但 `_update_mag_detail()` 幂等（读 config + 设 checkbox），无害。

---

## 2026-10-08 SSOT 改造

### 起因

发现两个 bug：
- **bug A**：新增载具时，只有"载具列表"选中了新载具，但弹种列表、倍率列表、状态机、其他 UI 都还停留在旧载具的数据
- **bug B**：删除当前载具时，载具列表删除了，但 state.current_vehicle 还指向被删的载具，所有 UI 也还显示被删载具的信息

排查这两个 bug 时，发现项目里"当前 X"的语义在多处独立存储、靠信号拼凑同步。
归纳出 12 条伪 SSOT。

### 改动

（逐条列，带位置）

* **config 层**：业务方法不再碰 current_state，副作用上移到 state_machine
* **state_machine**：8 个业务方法包装 + 三个 setter 私有化
* **4 列表（vehicle/ammo/mag/quick_ammo_combo）**：选中态由 state 驱动
* **删载具**：清 angle_meter.profiles[*].linked_vehicles
* **删标签**：加 tags_changed 信号，各 tab 的 tag_filter 响应
* **删 profile**：tracker 改 provider 化（_calibration / _min_max 不持缓存）
* **墓碑清理**：angle_meter.current_vehicle / vehicles 加载时 pop
* **角度仪热键重建**：_init_engine 开头无条件 disconnect
* **标定测距暂离同步**：main_window 里同步 ammo_wheel.is_suspended

### 回退与翻车（重要）

* **4 列表改造中，"标签列表空"**：_refresh_tag_list 在新 init 路径里丢了
* **"页面加载失败"**：_pending_vf_signals 从二元组改一元组后没 grep 解包点
* **"标定测距 tab 崩"**：wheel.is_suspended 是 @property，误加括号调用
→ 定位困难，因为 Qt 吞信号槽异常，靠 try/except 包住才拿到 traceback

### 已知问题（不修）

**只留指针**：这两条已登记在 HANDOVER 十三节（同一信息只该有一处）。




---

## 2026-10-08（V155 → V165）

### 配色体系重构

* **删 `ACCENT` 常量**：`colors.py` 不再有 `ACCENT = "#8B6F47"`。强调色出厂默认挪到 config 默认模板 `global_settings.accent_dark/light`（中性值：深主题 `#EBEBEC`、浅主题 `#1D1D1F`）。运行时走 `config.get_accent(theme)`
* **状态色收敛**：`ANGLE_IDLE/ACTIVE/PAUSED/CALIBRATING` 全部改为 `DISTANCE_*` 的别名（灰/绿/橙/橙）；`CAL_HINT` = `DISTANCE_CALIBRATING`
* **主题调色板加 `btn`/`base`**：按钮走 `btn`、输入框走 `base`，以 bg 为基准 ±3 明度（DARK: btn `#202022`/base `#1A1A1C`；LIGHT: btn `#EEEEEF`/base `#E8E8E9`）
* **悬浮窗配色自成体系**：底框 `OVERLAY_BOX_RGB=(20,20,20)` + `OVERLAY_BOX_BG_ALPHA=51`（20%）；文字 `OVERLAY_TEXT="#EBEBEC"` 白字；窗口级 `setWindowOpacity` 全取消
* **滚轮强调项文字跟主题**：横幅/高亮项文字走 `on_accent_text`（与主界面一致），不再固定白

### 悬浮窗三个模块

* **滚轮**：倍率挂件只显示当前倍率（"下一倍率"砍掉）；`FullOverlay(accent)` 构造收 accent；文字全白
* **标定测距**：比例尺、提示文字白字；`set_active()` 退化为兼容空壳
* **角度仪**：悬浮窗底框从"跟主题"改为统一 `OVERLAY_BOX_RGB`；角度示数与主 tab SSOT——正常白、暂离/标定中橙

### 滚轮位置 XY

* `config.get_wheel_offset()` / `set_wheel_offset(x,y)`：`global_settings.wheel_offset_x/y`
* 准星面板加"滚轮位置"组（±2000px）；`AmmoWheelSelector.reposition()`

### 导航调整

* "相关"组顺序：**适配设置 → 资源库 → 信息**（原"资源"改名"相关"，"屏幕适配"改名"适配设置"）

### 修过的 bug

* **角度仪暂离对不上**：`set_suspended()` 用 `getattr(self.tracker, '_paused', False)` 判断暂停态，但 tracker 没有 `_paused` 字段（状态机用 `self.state`）。改成 `tracker.state == STATE_PAUSED`
* **准星面板 tab 创建失败**：`_connect_crosshair_params()` 在滚轮控件创建之前调用。控件创建顺序挪正
* **按钮没变化**：QSS `QPushButton` 没写 `background-color`，Qt 应用 QSS 后背景透明不走 `QPalette.Button`。已补 `background-color: {btn}`

### 回退过的方向

* 悬浮窗文字色曾要求"随当前主题"（上一轮），本轮又要求"固定白字"——以本轮为准
* `get_overlay_text()` / `get_overlay_text_dim()` / `get_overlay_text_suspend()` 加了又删

