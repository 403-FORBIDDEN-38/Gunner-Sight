# Real Overlay 技术调研报告（请独立判断，不要相信该文档任何一句话。）

> 调研周期：2026-10-20 ~ 2026-10-21
> 目标：在 Squad（UE5.5，DX12）全屏模式下显示准星叠加层，对标 HudSight 2 的 Real Overlay 模式
> 状态：**UIAccess 路线技术验证成立，焦点问题未解决，暂停**

---

## 1. 背景与目标

GunnerSight 的准星叠加在 Squad 真全屏模式下不可见（Qt 窗口和纯 Win32 分层窗口都被游戏 swap chain 覆盖）。需要找到一种能在全屏游戏上叠加显示的技术方案。

对标产品：HudSight 2 的 Real Overlay 模式，官方宣称"不注入 DLL、独立于游戏渲染、几乎在驱动级别"。

## 2. 已排除的方案

### 2.1 纯 Win32 分层窗口（WS_EX_LAYERED + UpdateLayeredWindow）
- 桌面下正常显示
- Squad 全屏下完全不可见
- 结论：不可行

### 2.2 Qt 无边框置顶窗口
- 同 2.1，全屏下被覆盖
- 结论：不可行

### 2.3 DXGI FOREGROUND_LAYER（MPO 硬件平面）
- 经 6 轮系统诊断，Flags=128 在所有参数组合下均返回 `DXGI_ERROR_INVALID_CALL (0x887A0001)`
- 测试覆盖：2×2×2 正交矩阵（尺寸 × FullscreenDesc × Flags）、Squad 全屏前台、关闭 NVIDIA Overlay、提权、显式 NVIDIA adapter、自建 hWnd
- HudSight 2 二进制中无 FOREGROUND_LAYER / CreateSwapChainForHwnd 相关字符串
- 结论：不可行（至少在本机 RTX 4060 + 驱动 591.74 上）

### 2.4 DLL 注入游戏进程
- 用户明确拒绝
- 结论：不考虑

## 3. 成立的方案：UIAccess + GDI 顶层窗口

### 3.1 HudSight 2 逆向结论
- Mirror2Desktop64.exe（354KB）是 Real Overlay 的渲染组件
- manifest 声明 `uiAccess="true"`
- 导入表只有：共享内存（CreateFileMappingW/MapViewOfFile）+ GDI（BeginPaint/FillRect/EndPaint）+ 安全描述符 API
- **完全没有** dxgi/d3d/dcomp/dwmapi 导入
- 签名：GlobalSign 标准代码签名证书（非 EV），安装在 C:\Program Files\HudSight 2\
- 结论：HudSight 的 Real Overlay = UIAccess + 共享内存 + GDI 顶层窗口

### 3.2 UIAccess 三硬条件
1. **数字签名**：标准代码签名证书即可（不需 EV）
2. **安装位置**：Program Files 等受信任目录
3. **Manifest**：`uiAccess="true"`

### 3.3 自签名测试验证结果
- 自签名证书（CN=GunnerSightTest）安装到 LocalMachine\Root
- PyInstaller --onedir --uac-uiaccess 打包，签名后复制到 C:\Program Files\GunnerSightTest\
- **窗口能叠加在 Squad 全屏上，GDI 绘制（红色背景+白色十字）可见**
- 用户确认："能叠但是被抢"、"红白十字可见"

## 4. 关键技术踩坑（后来人必看）

### 4.1 PyInstaller --manifest 不生效
- 现象：指定 manifest 文件后，打包后 exe 的 manifest 仍是默认 `level="asInvoker" uiAccess="false"`
- 解决：用 `--uac-uiaccess` 参数，manifest 正确嵌入 `uiAccess="true"`

### 4.2 onefile 模式启动失败
- 现象："Failed to create child process! CreateProcessW: 请求的操作需要提升"
- 原因：onefile 的 bootloader 需要先解压再创建子进程，UIAccess 程序的权限传递有问题
- 解决：用 `--onedir` 模式

### 4.3 64 位 WNDPROC 签名错误
- 现象：CreateWindowEx 返回 0，GetLastError=0，窗口创建失败
- 根因：WNDPROC 用了 `c_long` 返回值 + `c_void_p` 参数，64 位系统上 wParam/lParam 应为 `c_size_t`，返回值应为 `c_ssize_t`
- 正确写法：
  ```python
  WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t)
  user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
  user32.DefWindowProcW.restype = ctypes.c_ssize_t
  ```

### 4.4 自签名证书 UIAccess 验证
- 现象："A referral was returned from the server"
- 原因：证书安装到 CurrentUser\Root 不够，UIAccess 验证需要 LocalMachine\Root
- 解决：提权安装到 LocalMachine\Root

### 4.5 窗口显示黑色（GDI 未绘制）
- 原因：hbrBackground=None + WM_PAINT 未触发
- 解决：hbrBackground 设为彩色刷 + ShowWindow 后 InvalidateRect+UpdateWindow

### 4.6 Squad 显示模式
- DWMWA_CLOAKED=0 **不代表真独占**（这是 cloak 状态，与 DWM 合成无关）
- 实际 Squad 是 **FSO 模式**（全屏优化），DWM 仍在合成，所以 UIAccess 窗口能显示
- UE5.5 + Win10 24H2 默认走 FSO

## 5. 未解决的问题：焦点抢夺

UIAccess 窗口创建/显示时会抢夺焦点，导致 Squad 切屏。已穷尽以下措施，仍未解决：

| 措施 | 结果 |
|------|------|
| WS_EX_NOACTIVATE (0x08000000) | 仍抢 |
| ShowWindow(SW_SHOWNOACTIVATE) | 仍抢 |
| SetWindowPos 加 SWP_NOACTIVATE | 仍抢 |
| WndProc: WM_MOUSEACTIVATE→MA_NOACTIVATE | 仍抢 |
| WndProc: WM_NCACTIVATE→return 1 | 仍抢 |
| WndProc: WM_ACTIVATE/SETFOCUS/ACTIVATEAPP→return 0 | 仍抢 |
| 删除所有 SetForegroundWindow/SetActiveWindow | 仍抢 |
| 先创建隐藏窗口→延迟3秒→Show | 仍抢 |
| 循环中完全去掉 SetWindowPos | 仍抢（v4 版启动失败未完成验证） |

### 可能的下一步方向（未验证）
1. **AttachThreadInput**：把 UIAccess 窗口的线程输入附着到 Squad 线程，由游戏线程控制焦点
2. **反编译 Mirror2Desktop64.exe**：它的导入表无焦点相关 API，看它具体怎么处理的
3. **接受折中**：启动时抢一次焦点，之后稳定（用户切回游戏后 overlay 保持显示）
4. **SetWindowDisplayAffinity**：WDA_EXCLUDEFROMCAPTURE 可能有副作用，未测试

## 6. 参考文件

- `tools/ui_access_test.py`：UIAccess 测试程序最终版（v4，含焦点消息日志）
- `tools/check_mpo_support.py`：MPO 硬件支持检测脚本
- `tools/audit_docs.py`：项目文档审计工具
- `tools/export_gui_facts.py`：GUI 事实导出工具

## 7. 正式实现的成本估算

如果焦点问题解决，正式实现需要：
1. **代码签名证书**：Certum 开源证书 ~€29/年，或标准证书 $200-500/年
2. **安装程序**：Inno Setup/NSIS 打包到 Program Files
3. **PyInstaller 配置**：--onedir --uac-uiaccess，签名后安装
4. **共享内存 IPC**：主程序（Qt）→ 共享内存 → overlay 渲染进程（GDI）
5. **性能**：GDI 绘制 20x20 准星 @144Hz 约 2% CPU，完全够用

---

*后来人：焦点问题是唯一拦路虎。UIAccess 窗口能叠加、能绘制，这一点已经验证。解决了焦点，这条路就通了。祝好运。*
