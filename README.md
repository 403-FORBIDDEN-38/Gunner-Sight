# GunnerSight

Squad 载具炮手辅助工具。透明叠加层显示自定义炮镜分划，不读游戏内存，不注入进程。

## 功能

- **准星叠加** — 载具/弹种/倍率三级自动切换，全局或载具级缩放/偏移/透明度
- **信息数显** — 无UI模式下自动截图测距仪数值并贴回屏幕
- **标定测距** — 基于地图比例尺标定像素-米换算，任意两点距离实时测算
- **炮塔角度仪** — RawInput 鼠标增量推算俯仰角，每武器站独立校准曲线
- **建队宏** — 自动化控制台建队流程
- **吉祥物** — 桌面挂件，点击 Q 弹动画 + 音效 + 气泡反馈

## 快速开始

### 运行

```bash
pip install PyQt5 mss keyboard pillow pytest
py main.py
```

> Windows 上 `python` 可能指向 Store 占位符（静默零输出），用 `py` 启动器。

需以管理员身份运行（信息数显的 BlockInput 需要管理员权限）。游戏设为窗口化或无边框窗口。

### 配置

- `config/config.json` — 全部用户配置（载具、热键、各模块参数）
- `resources/` — 炮镜图片、字体、吉祥物素材
- 删除 `config.json` 后重启即重置（程序本体无默认用户数据）

## 架构

```
main.py
├── core/                        # 业务逻辑层（无 UI 依赖，可独立测试）
│   ├── config_manager.py        # 配置持久化
│   ├── state_machine.py         # 载具/弹种/倍率三级状态机
│   ├── overlay_base.py          # ClickThroughOverlay 穿透基类
│   ├── overlay.py               # 准星叠加层
│   ├── distance_overlay.py      # 测距悬浮窗口
│   ├── rangefinder_overlay.py   # 数显叠加层
│   ├── angle_meter.py           # RawInput + 校准曲线 + 角度追踪
│   ├── distance_meter.py        # 像素-米比率 + 标定/测距状态机
│   ├── rangefinder.py           # 截图 + BlockInput + 无UI切换
│   ├── squad_macro.py           # 热键序列 + 后台线程
│   ├── hotkey_manager.py        # 全局热键 + 双键 + 主线程转发
│   ├── resource_manager.py      # 图片缓存 + 懒加载
│   └── win32_utils.py           # Win32 API 封装（穿透/SendInput）
├── gui/
│   ├── main_window.py           # 主窗口（懒加载 9 个 tab）
│   ├── widgets.py               # 通用组件
│   ├── hotkey_widgets.py        # HotkeyPairWidget 双键组件
│   ├── mascot/                  # 吉祥物模块
│   └── tabs/                    # 9 个页签
├── tests/                       # pytest 单元测试（104 用例）
└── tools/                       # 静态扫描等开发工具
```

### 数据流

```
用户按热键
  → hotkey_manager 捕获（keyboard 钩子，子线程）
  → QTimer.singleShot(0, callback) 转主线程
  → 更新 state_machine 状态
  → 发射 changed 信号
  → overlay / 各模块监听信号更新显示
```

状态唯一存储于 state_machine，其他模块不维护副本。

## 核心实现

### 叠加层穿透

`ClickThroughOverlay` 基类同时设置 Qt 层面 `WA_TransparentForMouseEvents` 和 Win32 层面 `WS_EX_TRANSPARENT | WS_EX_LAYERED`。重写 `setWindowOpacity` 和 `setWindowFlags`，操作后自动调用 `ensure_click_through()` 恢复穿透——Windows 上设置透明度可能清除 `WS_EX_TRANSPARENT`。`showEvent` 中无条件恢复穿透。

编辑模式通过 `set_edit_mode(True)` 临时关闭穿透允许拖动，ESC 退出，30 秒超时兜底，`hideEvent` 重置状态。

三个叠加层（准星/测距/数显）全部继承此基类。

### 角度仪

使用 Windows Raw Input API（`RegisterRawInputDevices` + `WM_INPUT`）读取鼠标硬件原始增量，不受系统鼠标加速影响。`RawInputReader` 继承 QWidget，通过 `nativeEvent` 捕获消息。

`AngleCalibration` 为不可变对象，存储校准点（增量累计值→角度，3-11 点），使用时分段线性插值。`AngleTracker`（使用状态）与 `Calibrator`（校准流程）分离。

微调通过 `SendInput` 模拟真实鼠标移动，使校准和使用的增量来源一致。点按步长 1°，长按连续，长长按加速。

一个角度仪配置可关联多辆载具（同一武器站多车共用）。

### 标定测距

用户在地图比例尺两端标定，软件记录像素距离，结合指定比例尺算出每像素对应的米数。任意两点像素距离 × 比率 = 实际距离。

标定比例尺时判断主轴方向（横向/竖向），只取主轴距离，忽略手抖导致的另一轴偏移。

模块启用（UI 复选框，控制对象创建/定时器）与流程激活（热键，控制是否响应标定/测距热键）为两层状态。标定与测距为独立状态机，互不打断。

组合键 + 测距热键可沿用上一次测距点 1，直接指定本次点为点 2。

### 热键系统

使用 `keyboard` 库 `on_press`/`on_release` 全局监听，支持鼠标键和 CAPS LOCK 等特殊键。按下/松开触发独立配置。

`HotkeyPairWidget` 统一双键绑定 UI，所有页面复用。配置格式 `{key1, trigger1, key2, trigger2}`。

keyboard 钩子回调在子线程执行，Qt UI 操作必须在主线程。触发时用 `QTimer.singleShot(0, callback)` 转到主线程事件队列执行。

### 配置管理

保存时构造有序 dict，按 `version → global_settings → hotkeys → vehicles → angle_meter → distance_meter → squad_macro → mascot` 输出。

保存热键时自动过滤旧格式字段 `key`/`trigger`，只输出 `key1`/`key2`。读取时兼容旧格式，内存中迁移到 `key1`，下次保存自动干净。

配置变更后 500ms 防抖写入磁盘，`save_config()` 可强制立即保存。

程序本体不含默认用户数据——删除 config 后重启，所有列表为空。

### 吉祥物

Q 弹动画用 `QPropertyAnimation` 动画 `char_label.geometry`，按压 `scaleY(0.80) scaleX(1.12)`，底边中心固定（缩放时 cx/bottom 不变）。`setScaledContents(True)` 使 pixmap 跟随 label 拉伸。cubic-bezier 缓动用 `QEasingCurve.setCustomType` + 牛顿迭代求解 `(.34,1.56,.64,1)`。

气泡为三明治层级（尾巴→底→内容→框），内容区域用气泡底 alpha 通道做 `setMask` 剪切蒙版。shake 用 `pyqtProperty` 相对偏移叠加，不与位置跟随冲突。

音效：短按 release 与 press 末尾重叠 100ms（按 press 剩余时长计算），长按松手时播 release。

气泡隐藏时通过 `visibility_changed` 信号停止 16ms 跟随定时器，显示时启动。模块禁用时完整清理（deleteLater + 停止定时器）。

### 资源管理

三级缓存：文件列表缓存 + 缩略图缓存（上限 300）+ 原图缓存。缩略图异步分批加载，每次加载 2 个后交还事件循环，避免大量图片同时解码阻塞 UI。

`list_resources()` 递归扫描时跳过 `assets/` 目录（mascot/fonts 等内部资源不进用户资源库）。

导入图片时按文件大小 + MD5 检查是否已有相同内容，有则复用不创建副本。

## 开发

### 测试

```bash
py -m pytest tests/ -v
```

104 个测试用例，覆盖 config_manager、vehicle_overlay、distance_meter_logic、angle_meter、hotkey_manager。

### 静态扫描

```bash
py tools/static_scan.py
```

检查：主线程裸 time.sleep、重复方法定义、except:pass 危险吞没、未使用 import。

### 打包

```bash
pyinstaller --onedir --name GunnerSight main.py
```

`config/` 与 `resources/` 外置在 exe 同级，用户数据不随打包丢失。

### 版本号

唯一来源：`gui/tabs/info_tab.py` 的 `APP_VERSION`。

## 扩展

### 添加新模块

1. `core/` 下创建逻辑层（无 UI 依赖，可独立测试）
2. `gui/tabs/` 下创建页签（`__init__(config, resources, parent)`）
3. `gui/main_window.py` 的 `_tab_factories` 中注册
4. `config_manager.py` 中添加配置段（无默认用户数据）
5. 需要热键时在 `hotkey_manager.py` 注册信号，回调走 `QTimer.singleShot(0)` 转主线程
6. 写 pytest 测试

### 添加热键

1. `hotkey_manager.py` 添加信号和注册逻辑
2. 对应 tab 用 `HotkeyPairWidget` 绑定
3. `config_manager.py` 添加配置读写方法

## 技术栈

Python 3 · PyQt5 · mss · keyboard · RawInput · ctypes/Win32 API · pytest

## 免责声明

本软件免费，不读取游戏内存，不注入进程，不修改游戏文件。使用者需自行承担使用后果，请遵守游戏用户协议。若遇他人以「代下、安装、指导、内部版」等名义收费，谨防信息差。

联系方式 QQ：3117023693
