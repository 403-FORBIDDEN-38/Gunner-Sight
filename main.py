"""
GunnerSight Overlay - 屏幕准星辅助软件
主入口文件
"""

import sys
import atexit
import os
import time
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
        # ShellExecuteW 返回值 <=32 表示失败（含用户拒绝 UAC），给明确提示
        if ret <= 32:
            print("[Main] 需要管理员权限才能运行（BlockInput / UI 自动化），用户拒绝或提权失败，程序退出")
    except Exception as e:
        print(f"[Main] 提权请求异常: {e}，程序退出")
    sys.exit(0)

# 优化5: _request_admin移到main()中，避免import时触发提权

# 将项目根目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QFont, QFontDatabase
from PyQt5.QtCore import Qt, QTimer

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

    P0-6: 只加载 Norwester（英文），中文字符自动回退系统默认字体。
    去掉思源黑体加载（5-15MB文件解析耗时，系统字体已足够）。
    """
    resources_dir = get_app_base_dir() / "resources"
    fonts_dir = resources_dir / 'fonts'

    font_norwester = None

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

    if font_norwester:
        font = QFont()
        font.setFamilies([font_norwester, "Source Han Sans CN"])
        font.setPointSize(10)
        font.setStyleStrategy(QFont.PreferDefault)
        app.setFont(font)
        app.setFont(font, "QWidget")
        app.setFont(font, "QMainWindow")
        app.setFont(font, "QDialog")
        return True
    else:
        print("[Main] 未加载任何自定义字体，使用系统默认字体")
        return False


def main():
    _request_admin()  # 优化5: 提权移到main入口
    # 控制台输出同时写入文件，窗口闪太快也能在文件里看
    _log_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    _log_file = open(os.path.join(_log_dir, "startup_log.txt"), "w", encoding="utf-8")
    class _Tee:
        def __init__(self, *files): self.files = files
        def write(self, obj):
            for f in self.files: f.write(obj); f.flush()
        def flush(self):
            for f in self.files: f.flush()
    sys.stdout = _Tee(sys.stdout, _log_file)
    sys.stderr = _Tee(sys.stderr, _log_file)
    try:
        _main()
    except Exception:
        # 崩溃日志必须落到可写目录。
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

    _t0 = time.perf_counter()
    app = QApplication(sys.argv)
    app.setApplicationName("GunnerSight Overlay")
    app.setApplicationVersion(_APP_VERSION.lstrip("V"))  # 版本号唯一权威来源，与信息页一致
    app.setQuitOnLastWindowClosed(False)
    print(f"[性能] QApplication创建 耗时={(time.perf_counter()-_t0)*1000:.0f}ms")

    # 设置应用程序图标（窗口左上角、任务栏等）
    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    else:
        print("[Main] 未找到应用程序图标文件")

    # 初始化各模块
    _t1 = time.perf_counter()
    config = ConfigManager()
    print(f"[性能] ConfigManager初始化 耗时={(time.perf_counter()-_t1)*1000:.0f}ms")

    _t2 = time.perf_counter()
    state = StateMachine(config)
    print(f"[性能] StateMachine初始化 耗时={(time.perf_counter()-_t2)*1000:.0f}ms")

    _t3 = time.perf_counter()
    resources = ResourceManager()
    print(f"[性能] ResourceManager初始化 耗时={(time.perf_counter()-_t3)*1000:.0f}ms")

    _t4 = time.perf_counter()
    overlay = OverlayRenderer(config, state)
    print(f"[性能] OverlayRenderer初始化 耗时={(time.perf_counter()-_t4)*1000:.0f}ms")

    _t5 = time.perf_counter()
    hotkey = HotkeyManager(config, state)
    print(f"[性能] HotkeyManager初始化 耗时={(time.perf_counter()-_t5)*1000:.0f}ms")

    # 如果有默认载具，设置当前状态
    vehicles = config.get_vehicle_names()
    if vehicles and not state.current_vehicle:
        state.set_vehicle(vehicles[0])

    # 创建主窗口
    _t6 = time.perf_counter()
    window = MainWindow(config, state, overlay, hotkey, resources)
    print(f"[性能] MainWindow创建(UI创建) 耗时={(time.perf_counter()-_t6)*1000:.0f}ms")

    _t7 = time.perf_counter()
    window.show()
    print(f"[性能] 主窗口显示 耗时={(time.perf_counter()-_t7)*1000:.0f}ms")
    print(f"[性能] 启动总耗时(不含字体)={(time.perf_counter()-_t0)*1000:.0f}ms")

    # 异步初始化：极简QSS(防白屏)->第一个tab->完整QSS->数据刷新
    def _delayed_init():
        _di = time.perf_counter()
        window._setup_minimal_style(window._current_theme)
        print(f'[性能] 极简QSS 耗时={(time.perf_counter()-_di)*1000:.0f}ms')
        _di2 = time.perf_counter()
        window._init_first_tab()
        print(f'[性能] 第一个tab创建 耗时={(time.perf_counter()-_di2)*1000:.0f}ms')
        _di3 = time.perf_counter()
        window._setup_full_style(window._current_theme)
        print(f'[性能] 完整QSS 耗时={(time.perf_counter()-_di3)*1000:.0f}ms')
        _di4 = time.perf_counter()
        window._disable_control_focus()
        print(f'[性能] 焦点策略 耗时={(time.perf_counter()-_di4)*1000:.0f}ms')
        window.overview_tab.refresh()
    QTimer.singleShot(0, _delayed_init)

    # P0-1: 字体延迟加载，窗口先用系统默认字体显示
    def _load_fonts_delayed():
        _tf = time.perf_counter()
        load_custom_fonts(app)
        print(f"[性能] 字体加载(延迟) 耗时={(time.perf_counter()-_tf)*1000:.0f}ms")
    QTimer.singleShot(0, _load_fonts_delayed)

    # P0-2: Overlay窗口延迟预创建（窗口显示后100ms异步创建，不阻塞启动）
    QTimer.singleShot(100, overlay._ensure_overlay)

    # RangefinderTab异步创建（不阻塞启动）
    QTimer.singleShot(0, lambda: window._ensure_tab(3).refresh())

    # 窗口显示后再初始化热键（keyboard 库导入+注册约 500ms，不阻塞窗口出现）
    def _init_hotkey_timed():
        _th = time.perf_counter()
        hotkey.initialize()
        print(f"[性能] 热键注册 耗时={(time.perf_counter()-_th)*1000:.0f}ms")
    QTimer.singleShot(0, _init_hotkey_timed)

    # 运行
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
