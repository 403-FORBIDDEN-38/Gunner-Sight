"""
GunnerSight Overlay - 屏幕准星辅助软件
主入口文件
"""

import sys
import atexit
import os
import ctypes
import traceback

# 版本号唯一权威来源（info_tab.py），QApplication 与信息页共享同一值
from gui.tabs.info_tab import APP_VERSION as _APP_VERSION

# 请求管理员权限（BlockInput / UI 自动化需要）
def _request_admin():
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except Exception:
        pass
    try:
        # 打包后：直接重新运行当前 exe
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv[1:]) if len(sys.argv) > 1 else ""
            work_dir = os.path.dirname(exe_path)
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe_path, params, work_dir, 1)
        else:
            # 开发环境：用 python 运行 main.py
            script_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(script_dir, "main.py")
            params = f'"{script_path}"'
            if len(sys.argv) > 1:
                params += " " + " ".join(f'"{a}"' for a in sys.argv[1:])
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, script_dir, 1)
        # D7: ShellExecuteW 返回值 <=32 表示失败（含用户拒绝 UAC），给明确提示
        if ret <= 32:
            print("[Main] 需要管理员权限才能运行（BlockInput / UI 自动化），用户拒绝或提权失败，程序退出")
    except Exception as e:
        print(f"[Main] 提权请求异常: {e}，程序退出")
    sys.exit(0)

_request_admin()

# 将项目根目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QFont, QFontDatabase
from PyQt5.QtCore import Qt

from core.config_manager import ConfigManager, get_app_base_dir
from core.state_machine import StateMachine
from core.overlay import OverlayRenderer
from core.hotkey_manager import HotkeyManager
from core.resource_manager import ResourceManager
from gui.main_window import MainWindow


def get_app_icon_path():
    """获取应用程序图标的路径（兼容开发环境和打包后）"""
    # 打包后：PyInstaller 临时目录
    if hasattr(sys, '_MEIPASS'):
        meipass_icon = os.path.join(sys._MEIPASS, 'app_icon.ico')
        if os.path.exists(meipass_icon):
            return meipass_icon

    # 开发环境：脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dev_icon = os.path.join(script_dir, 'app_icon.ico')
    if os.path.exists(dev_icon):
        return dev_icon

    # 可执行文件同目录（打包后也可能在这里）
    exe_dir = os.path.dirname(sys.executable)
    exe_icon = os.path.join(exe_dir, 'app_icon.ico')
    if os.path.exists(exe_icon):
        return exe_icon

    # 外置 resources 目录（onedir 发布版 resources 外置）
    res_icon = os.path.join(exe_dir, 'resources', 'app_icon.ico')
    if os.path.exists(res_icon):
        return res_icon

    # 源码 resources 目录
    dev_res_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'app_icon.ico')
    if os.path.exists(dev_res_icon):
        return dev_res_icon

    return None


def load_custom_fonts(app):
    """加载自定义字体并设置应用程序默认字体

    英文使用 Norwester，中文自动回退到 Source Han Sans SC（思源黑体 Bold）。
    Qt 的字体回退机制会自动为每个字符选择第一个包含该字形的字体。
    """
    resources_dir = get_app_base_dir() / "resources"
    fonts_dir = resources_dir / 'fonts'

    font_norwester = None
    font_sourcehan = None

    # 加载 Norwester（英文）
    norwester_path = os.path.join(fonts_dir, 'NORWESTER.ttf')
    if os.path.exists(norwester_path):
        font_id = QFontDatabase.addApplicationFont(norwester_path)
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                font_norwester = families[0]
        else:
            print(f"[Main] Norwester 字体加载失败: {norwester_path}")
    else:
        print(f"[Main] Norwester 字体文件不存在: {norwester_path}")

    # 加载 Source Han Sans SC（中文）
    sourcehan_path = os.path.join(fonts_dir, 'SYHT_BOLD.otf')
    if os.path.exists(sourcehan_path):
        font_id = QFontDatabase.addApplicationFont(sourcehan_path)
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                font_sourcehan = families[0]
        else:
            print(f"[Main] Source Han Sans 字体加载失败: {sourcehan_path}")
    else:
        print(f"[Main] Source Han Sans 字体文件不存在: {sourcehan_path}")

    # 设置应用程序默认字体
    # 字体族按优先级排列：英文用 Norwester，中文自动回退到 Source Han Sans
    families = []
    if font_norwester:
        families.append(font_norwester)
    if font_sourcehan:
        families.append(font_sourcehan)

    if families:
        # 构建字体：优先 Norwester，回退 Source Han Sans，最后回退系统默认
        font = QFont()
        font.setFamilies(families)
        font.setPointSize(10)  # 默认字号
        font.setStyleStrategy(QFont.PreferDefault)
        app.setFont(font)

        # 也设置为应用程序的默认字体（确保所有控件继承）
        app.setFont(font, "QWidget")
        app.setFont(font, "QMainWindow")
        app.setFont(font, "QDialog")

        return True
    else:
        print("[Main] 未加载任何自定义字体，使用系统默认字体")
        return False


def main():
    try:
        _main()
    except Exception:
        # D2 加固：崩溃日志必须落到可写目录。
        # frozen 时直接取 exe 同级（不依赖 config 目录是否已建，首次启动崩溃也能落盘）；
        # 开发环境取脚本同级。
        if getattr(sys, 'frozen', False):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(log_dir, "crash_log.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise


def _main():
    # 启动时释放任何残留的 BlockInput（上次异常退出可能导致输入锁定）
    try:
        from core.win32_utils import user32 as _u
        _u.BlockInput(False)
        atexit.register(lambda: _u.BlockInput(False))
    except Exception:
        pass

    # 高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("GunnerSight Overlay")
    app.setApplicationVersion(_APP_VERSION.lstrip("V"))  # 版本号唯一权威来源，与信息页一致
    app.setQuitOnLastWindowClosed(False)

    # 设置应用程序图标（窗口左上角、任务栏等）
    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    else:
        print("[Main] 未找到应用程序图标文件")

    # 加载自定义字体（英文 Norwester + 中文 Source Han Sans）
    load_custom_fonts(app)

    # 初始化各模块
    config = ConfigManager()
    state = StateMachine(config)
    resources = ResourceManager()
    overlay = OverlayRenderer(config, state)
    hotkey = HotkeyManager(config, state)

    # 如果有默认载具，设置当前状态
    vehicles = config.get_vehicle_names()
    if vehicles and not state.current_vehicle:
        state.set_vehicle(vehicles[0])

    # 创建主窗口
    window = MainWindow(config, state, overlay, hotkey, resources)
    window.show()

    # 窗口显示后再初始化热键（keyboard 库导入+注册约 500ms，不阻塞窗口出现）
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(0, hotkey.initialize)

    # 运行
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

