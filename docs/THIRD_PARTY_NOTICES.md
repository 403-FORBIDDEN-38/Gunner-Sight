# 第三方组件版权与许可声明

本软件（GunnerSight）以 **GPL-3.0-only** 分发。分发包内含下列第三方组件，
其版权归各自作者所有，按各自的许可条款随本软件一同分发。

| 组件 | 版本 | 许可 | 版权持有者 |
|---|---|---|---|
| Python | 3.13.5 | PSF License Agreement 2.0 | Python Software Foundation |
| PyQt5 | 5.15.11 | GNU GPL v3 | Riverbank Computing Limited |
| Qt | 5.15.2 | GNU LGPL v3 | The Qt Company Ltd. |
| PyQt5-sip | 12.19.0 | BSD-2-Clause | Riverbank Computing Limited |
| Pillow | 12.3.0 | MIT-CMU (HPND) | Secret Labs AB、Fredrik Lundh 等 |
| mss | 10.2.0 | MIT | BoboTiG 及贡献者 |
| loguru | 0.7.3 | MIT | Delgan |
| keyboard | 0.13.5 | MIT | BoppreH |
| Nuitka（仅运行时部分） | 4.2.1 | Apache-2.0 | Kay Hayen |

## 许可全文的取得方式

- **GPL-3.0 全文**：本目录下的 `LICENSE` 文件
- **其余各组件的许可全文与源码**：

| 组件 | 地址 |
|---|---|
| Python | https://www.python.org/ |
| PyQt5 / PyQt5-sip | https://riverbankcomputing.com/software/pyqt/ |
| Qt | https://www.qt.io/ |
| Pillow | https://python-pillow.org/ |
| mss | https://github.com/BoboTiG/python-mss |
| loguru | https://github.com/Delgan/loguru |
| keyboard | https://github.com/boppreh/keyboard |
| Nuitka | https://nuitka.net/ |

## 关于 Qt 的 LGPL v3

Qt 以**动态链接**方式使用：分发包内的 `qt5core.dll`、`qt5gui.dll`、
`qt5widgets.dll` 等均为独立文件，不是静态编入主程序。
这满足 LGPL v3 第 4 条关于「允许使用者替换该库」的要求——你可以用自己
编译的同版本 Qt5 DLL 直接替换这些文件，无需修改主程序。

## 本软件的对应源码

GPL-3.0 要求分发目标代码时一并提供对应源码。本软件的源码可从：

https://github.com/403-FORBIDDEN-38/Gunner-Sight

取得，版本与分发包的标签（如 `v183`）对应。
本软件未修改 PyQt5、Qt、Python 及上表其他组件的源码，因此其"对应源码"
即为各自官方发布的原版，地址见上。
