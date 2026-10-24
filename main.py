from core.logger import logger

"""
Gunner Sight - 屏幕准星辅助软件
主入口文件
"""

import os
import sys
import tempfile
import time
import traceback


# 诊断：测量进程启动到 main.py 执行的时间（PyInstaller bootloader 开销）
if getattr(sys, 'frozen', False):
    import ctypes
    from ctypes import wintypes
    _kernel32 = ctypes.windll.kernel32
    _creation_time = wintypes.FILETIME()
    _kernel32.GetProcessTimes(_kernel32.GetCurrentProcess(), ctypes.byref(_creation_time), None, None, None)
    _boot_start = (_creation_time.dwHighDateTime << 32) | _creation_time.dwLowDateTime
    _boot_now = time.time()
    _boot_start_sec = _boot_start / 10_000_000 - 11644473600
    _boot_elapsed = _boot_now - _boot_start_sec
    logger.info(f"[诊断] 进程启动到 main.py 执行: {_boot_elapsed*1000:.0f}ms (PyInstaller bootloader + Python 初始化)")


class _LibpngFilter:
    """过滤 stderr 中的 libpng bKGD/iCCP 警告（libpng 直接写 stderr 不走 Qt 日志）"""
    def __init__(self, stream):
        self._stream = stream
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if not any(k in line for k in ("libpng", "bKGD", "iCCP")):
                self._stream.write(line + "\n")

    def flush(self):
        if self._buf and not any(k in self._buf for k in ("libpng", "bKGD", "iCCP")):
            self._stream.write(self._buf)
        self._buf = ""
        self._stream.flush()


sys.stderr = _LibpngFilter(sys.stderr)


# 将项目根目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QFontDatabase, QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen

from core.config_manager import get_app_base_dir


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

    Norwester（英文标题）+ Noto Sans SC Light（中文细体，静态字体）。
    """
    resources_dir = get_app_base_dir() / "resources"
    fonts_dir = resources_dir / 'assets/fonts'

    font_norwester = None
    font_noto = None

    # 加载 Norwester（英文）
    norwester_path = os.path.join(fonts_dir, 'NORWESTER.ttf')
    if os.path.exists(norwester_path):
        font_id = QFontDatabase.addApplicationFont(norwester_path)
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                font_norwester = families[0]
        else:
            logger.info(f"[Main] Norwester 字体加载失败: {norwester_path}")
    else:
        logger.info(f"[Main] Norwester 字体文件不存在: {norwester_path}")

    # 加载 Noto Sans SC（中文，可变字体）
    noto_path = os.path.join(fonts_dir, 'NotoSansSC-Light.ttf')
    if os.path.exists(noto_path):
        font_id = QFontDatabase.addApplicationFont(noto_path)
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                font_noto = families[0]
        else:
            logger.info(f"[Main] Noto Sans SC 字体加载失败: {noto_path}")
    else:
        logger.info(f"[Main] Noto Sans SC 字体文件不存在: {noto_path}")

    if font_norwester or font_noto:
        # 根源修复：弃用 setFamilies() 回退链（Qt5 对自定义字体+可变字体回退不可靠）。
        # 改用 insertSubstitution：为 Norwester 注册中文替代字体，
        # 英文/数字强制走 Norwester，只有中文字符才回退 NotoSansSC。
        font = QFont()
        if font_norwester:
            # 主字体用 Norwester
            font.setFamily(font_norwester)
            font.setPointSize(10)
            # 为 Norwester 注册中文替代字体（中文字符自动回退）
            if font_noto:
                QFont.insertSubstitution(font_norwester, font_noto)
            logger.info(f"[Main] 字体设置: 主字体={font_norwester}, 中文替代={font_noto}")
        else:
            # Norwester 加载失败时才用 Noto 作为主字体
            font.setFamily(font_noto)
            font.setPointSize(10)
            logger.info(f"[Main] 字体设置: Norwester 不可用，使用 {font_noto}")
        app.setFont(font)
        return True
    else:
        logger.info("[Main] 未加载任何自定义字体，使用系统默认字体")
        return False


def main():
    # 控制台输出同时写入文件，窗口闪太快也能在文件里看
    _log_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    # P4：只读位置（Program Files 标准用户等）startup_log 写不进去也不能让程序退——
    # 降级 %TEMP%，再失败就放弃文件（_Tee 过滤 None），仅保留控制台输出。
    try:
        _log_file = open(os.path.join(_log_dir, "startup_log.txt"), "w", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[Main] startup_log 写入失败（{_log_dir}）: {e}，降级到 %TEMP%")
        try:
            _log_file = open(os.path.join(tempfile.gettempdir(), "GunnerSight_startup_log.txt"), "w", encoding="utf-8")
        except Exception as e2:
            logger.warning(f"[Main] %TEMP% 下 startup_log 也不可写: {e2}，放弃启动日志文件")
            _log_file = None
    class _Tee:
        """行缓冲Tee：只在写入包含换行符时flush，减少磁盘IO。
        性能优化：原实现每次write都flush，控制台输出频繁时（如热键调试日志）
        会导致大量磁盘IO，影响性能。改为行缓冲后，只有换行时才flush，
        既保证日志行级完整性，又大幅减少flush次数。"""
        def __init__(self, *files): self.files = [f for f in files if f is not None]
        def write(self, obj):
            for f in self.files:
                try:
                    f.write(obj)
                    f.flush()  # segfault高发期：每次write都flush，保证崩溃前日志落盘
                except Exception:
                    # 这里是刻意吞掉：写日志失败绝不能反过来把程序搞崩。
                    # （吞的是"日志写不出去"，不是"程序出错了"——不掩盖任何 bug）
                    pass
        def flush(self):
            for f in self.files:
                try:
                    f.flush()
                except Exception:
                    pass  # 同上：日志通道失败不应影响主流程
    sys.stdout = _Tee(sys.stdout, _log_file)
    sys.stderr = _Tee(sys.stderr, _log_file)
    # 捕获异步回调（QTimer/signal）中的未处理异常，写入 crash_log.txt
    _ex_log_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    def _excepthook(exc_type, exc_value, exc_tb):
        # P4：崩溃日志同样只读降级 %TEMP%；异常路径绝不能因为写不了日志而二次崩溃
        for _path in (os.path.join(_ex_log_dir, "crash_log.txt"),
                      os.path.join(tempfile.gettempdir(), "GunnerSight_crash_log.txt")):
            try:
                with open(_path, "w", encoding="utf-8") as _f:
                    traceback.print_exception(exc_type, exc_value, exc_tb, file=_f)
                break
            except Exception:
                continue
        traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.excepthook = _excepthook
    try:
        _main()
    except Exception:
        # 崩溃日志必须落到可写目录。
        # frozen 时直接取 exe 同级（不依赖 config 目录是否已建，首次启动崩溃也能落盘）；
        # 开发环境取脚本同级。只读位置降级 %TEMP%（P4）。
        if getattr(sys, 'frozen', False):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.dirname(os.path.abspath(__file__))
        for _path in (os.path.join(log_dir, "crash_log.txt"),
                      os.path.join(tempfile.gettempdir(), "GunnerSight_crash_log.txt")):
            try:
                with open(_path, "w", encoding="utf-8") as f:
                    traceback.print_exc(file=f)
                break
            except Exception:
                continue
        # 发布版无控制台（--windows-console-mode=disable）：不弹窗用户看到的就是
        # "双击什么都没发生"。QApplication 之前的致命错误用 MessageBoxW 保证可见（P4）。
        if getattr(sys, 'frozen', False):
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0, f"GUNNER SIGHT 启动失败，错误已写入 crash_log.txt：\n\n{traceback.format_exc()[-1500:]}",
                    "GUNNER SIGHT", 0x10)
            except Exception:
                pass
        raise


def _main():
    # 抑制 libpng bKGD/iCCP 等警告输出（必须在 QApplication 创建前）
    os.environ["QT_LOGGING_RULES"] = "*.warning=false"

    # 高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    _t0 = time.perf_counter()
    app = QApplication(sys.argv)
    app.setApplicationName("GUNNER SIGHT")

    # 启动横幅
    splash = None
    _splash_assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "assets", "splash")
    _SCAN_MS = 300.0
    _full_img = os.path.join(_splash_assets, "full.png")
    if os.path.exists(_full_img):
        # 只加载整图，立即显示
        splash = QSplashScreen(QPixmap(_full_img), Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        splash.show()
        app.processEvents()

    # 横幅显示后再导入重型模块，每个import之间processEvents让横幅动画继续
    from gui.tabs.info_tab import APP_VERSION as _APP_VERSION
    app.processEvents()
    from core.config_manager import ConfigManager
    app.processEvents()
    from core.hotkey_manager import HotkeyManager
    app.processEvents()
    from core.ammo_wheel_selector import AmmoWheelSelector
    app.processEvents()
    from core.cleanup import (
        collect_tab_cleanup_steps,
        collect_window_cleanup_steps,
        run_cleanup_steps,
    )
    app.processEvents()
    from core.overlay import OverlayRenderer
    app.processEvents()
    from core.resource_manager import ResourceManager
    app.processEvents()
    from core.state_machine import StateMachine
    app.processEvents()
    from gui.main_window import MainWindow
    app.processEvents()

    # 根源修复：Fusion style 完全由 Qt 绘制，不调用 Windows 原生 API。
    # 默认 QWindowsVistaStyle 用 DrawThemeBackground 绘制原生下拉按钮/箭头，
    # 原生绘制层在 QSS 之上，导致 QComboBox/SpinBox 三角箭头显示为矩形且 QSS 无法覆盖。
    app.setStyle("Fusion")
    from gui.wheel_filter import install_no_wheel_filter
    # 必须用 install_no_wheel_filter 而不是 app.installEventFilter(NoWheelFilter())：
    # PyQt5 不持有过滤器引用，临时对象会被立即回收，过滤器静默失效
    install_no_wheel_filter(app)
    # 根源修复：字体必须在所有控件创建之前加载，否则已创建的控件不会自动继承自定义字体
    _t_font = time.perf_counter()
    load_custom_fonts(app)
    logger.info(f"[性能] 字体加载 耗时={(time.perf_counter()-_t_font)*1000:.0f}ms")
    app.setApplicationVersion(_APP_VERSION.lstrip("V"))  # 版本号唯一权威来源，与信息页一致
    app.setQuitOnLastWindowClosed(False)
    logger.info(f"[性能] QApplication创建 耗时={(time.perf_counter()-_t0)*1000:.0f}ms")

    # 设置应用程序图标（窗口左上角、任务栏等）
    _t_icon = time.perf_counter()
    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    else:
        logger.info("[Main] 未找到应用程序图标文件")
    logger.info(f"[性能] 图标加载 耗时={(time.perf_counter()-_t_icon)*1000:.0f}ms")

    # 初始化各模块
    _t1 = time.perf_counter()
    config = ConfigManager()
    logger.info(f"[性能] ConfigManager初始化 耗时={(time.perf_counter()-_t1)*1000:.0f}ms")

    _t2 = time.perf_counter()
    state = StateMachine(config)
    logger.info(f"[性能] StateMachine初始化 耗时={(time.perf_counter()-_t2)*1000:.0f}ms")

    _t3 = time.perf_counter()
    resources = ResourceManager()
    logger.info(f"[性能] ResourceManager初始化 耗时={(time.perf_counter()-_t3)*1000:.0f}ms")

    _t4 = time.perf_counter()
    overlay = OverlayRenderer(config, state)
    logger.info(f"[性能] OverlayRenderer初始化 耗时={(time.perf_counter()-_t4)*1000:.0f}ms")

    _t5 = time.perf_counter()
    hotkey = HotkeyManager(config, state)
    logger.info(f"[性能] HotkeyManager初始化 耗时={(time.perf_counter()-_t5)*1000:.0f}ms")

    # 如果有默认载具，设置当前状态
    vehicles = config.get_vehicle_names()
    if vehicles and not state.current_vehicle:
        state.set_vehicle(vehicles[0])

    # 创建主窗口
    _t6 = time.perf_counter()
    window = MainWindow(config, state, overlay, hotkey, resources)
    logger.info(f"[性能] MainWindow创建(UI创建) 耗时={(time.perf_counter()-_t6)*1000:.0f}ms")

    _t7 = time.perf_counter()
    window.show()
    logger.info(f"[性能] 主窗口显示 耗时={(time.perf_counter()-_t7)*1000:.0f}ms")
    logger.info(f"[性能] 启动总耗时(不含字体)={(time.perf_counter()-_t0)*1000:.0f}ms")

    # P6：配置损坏回退提示（若有）——窗口显示后延迟弹一次，确保用户知道配置被重置过
    _notices = getattr(config, "recovery_notices", None)
    if _notices:
        QTimer.singleShot(800, lambda: QMessageBox.warning(window, "配置提示", "\n".join(_notices)))

    # P1: 分阶段异步创建
    # 阶段2a: UI框架（顶栏+导航+tab_stack+信号连接）
    QTimer.singleShot(0, window._create_ui_frame)
    # 阶段2b: 第一个tab（OverviewTab+数据刷新）
    QTimer.singleShot(0, window._create_first_tab)
    # 阶段2c: 后台任务（延迟100ms，用户无感知）
    def _background_tasks():
        _bt = time.perf_counter()
        # 字体已在 QApplication 创建后立即加载（见上方），此处不再重复
        hotkey.initialize()
        logger.info(f"[性能] 热键注册 耗时={(time.perf_counter()-_bt)*1000:.0f}ms")
        # 滚轮切换弹种模块（保存到 window 避免被 GC）
        window.ammo_wheel = AmmoWheelSelector(state, config)
        # M17：补偿先于 wheel 实例化的标定测距 tab（初始同步 + toggled 连接）
        window.on_ammo_wheel_ready()
        hotkey.pause1_triggered.connect(window.ammo_wheel.on_suspend_key1)
        hotkey.pause2_triggered.connect(window.ammo_wheel.on_suspend_key2)
        # 弹种热键命令 → 结束预选列表。必须额外接这一路：选中的就是当前弹种时
        # state.ammo_type_changed 不发信号，只看状态变化会漏掉这次选择命令
        hotkey.ammo_switch_triggered.connect(window.ammo_wheel.on_ammo_hotkey)
        window.ammo_wheel.start()
        # 暂离 → 准星不透明度降一半
        def _on_suspend_changed(suspended):
            try:
                overlay.set_suspended(suspended)
            except Exception as e:
                logger.info(f"[Main] set_suspended failed: {e}")
        window.ammo_wheel.suspend_changed.connect(_on_suspend_changed)
        # 标定测距：暂离中激活，游戏中暂停
        def _on_suspend_for_distance(suspended):
            hotkey.set_distance_meter_active(suspended)
            try:
                tab = window.get_tab(window.TAB_DISTANCE_METER)
                if tab is not None:
                    tab.set_function_active(suspended)
            except Exception as e:
                logger.info(f"[Main] distance meter suspend sync failed: {e}")
        window.ammo_wheel.suspend_changed.connect(_on_suspend_for_distance)
        # 隐藏准星 → 连带隐藏滚轮模块
        def _on_overlay_visible_changed(visible):
            try:
                if hasattr(window, 'ammo_wheel') and window.ammo_wheel:
                    if visible:
                        window.ammo_wheel.show_all()
                    else:
                        window.ammo_wheel.hide_all()
            except Exception as e:
                logger.info(f"[Main] ammo_wheel visibility sync failed: {e}")
        state.overlay_toggled.connect(_on_overlay_visible_changed)
        # 放大镜热键（tab 由 MainWindow._create_first_tab 在电闸开启时预创建）

        def _mag(action):
            """放大镜热键分发：只操作**已创建**的tab，不触发懒加载。

            电闸关闭时 tab 不存在，热键直接不响应（空房子：模块未加载即无行为）。
            """
            tab = window.get_tab(window.TAB_MAGNIFIER)
            if tab is None:
                return
            getattr(tab, action)()

        hotkey.magnifier_toggle_triggered.connect(lambda: _mag("toggle"))
        hotkey.magnifier_zoom_in_triggered.connect(lambda: _mag("zoom_in"))
        hotkey.magnifier_zoom_out_triggered.connect(lambda: _mag("zoom_out"))
        hotkey.magnifier_breath_hold_triggered.connect(lambda: _mag("breath_hold"))
        # 暂离：只控制放大镜可视性
        def _on_suspend_magnifier(suspended):
            try:
                tab = window.get_tab(window.TAB_MAGNIFIER)
                if tab:
                    tab.set_suspended(suspended)
            except Exception:
                pass
        window.ammo_wheel.suspend_changed.connect(_on_suspend_magnifier)
        # 暂离：角度仪停止读取鼠标增量
        def _on_suspend_angle(suspended):
            try:
                tab = window.get_tab(window.TAB_ANGLE_METER)
                if tab:
                    tab.set_suspended(suspended)
            except Exception:
                pass
        window.ammo_wheel.suspend_changed.connect(_on_suspend_angle)
        # Overlay创建（带诊断日志，便于定位Nuitka下问题）
        logger.info("[Overlay] 开始创建透明叠加窗口...")
        try:
            overlay._ensure_overlay()
            logger.info("[Overlay] 透明叠加窗口创建成功")
        except Exception as e:
            logger.info(f"[Overlay] 创建失败(已捕获): {e}")
            import traceback; traceback.print_exc()
        # 所有初始化完成：从右向左扫描消失（延迟100ms再开始）
        if splash:
            frames = sorted(f for f in os.listdir(_splash_assets) if f.endswith(".png") and f != "full.png")
            if frames:
                _scan_idx = [0]
                def _scan_step():
                    if _scan_idx[0] >= len(frames):
                        _scan_timer.stop()
                        splash.close()
                        return
                    splash.setPixmap(QPixmap(os.path.join(_splash_assets, frames[_scan_idx[0]])))
                    splash.update()
                    _scan_idx[0] += 1
                _scan_timer = QTimer(splash)
                _scan_timer.timeout.connect(_scan_step)
                QTimer.singleShot(100, lambda: _scan_timer.start(int(_SCAN_MS / len(frames))))
            else:
                splash.close()
    QTimer.singleShot(100, _background_tasks)

    # 退出兜底清理放大镜线程。
    # 正常关闭走 MainWindow.closeEvent（同样只清理已创建的tab）；
    # 这里是 closeEvent 未执行时的兜底，因此必须用无副作用的 get_tab()：
    # 原实现访问 window.magnifier_tab（懒加载属性），会在退出时现场新建整个
    # 放大镜tab（此时 tab_stack 已 deleteLater），是纯粹的浪费与隐患。
    def _cleanup():
        # M18/M19：兜底路径此前只停 overlay+放大镜，漏停的线程/钩子
        # 不报错、只是活着。现在跑完整清理契约（与 closeEvent 同一份清单；
        # 正常退出时本函数是第二道，各清理动作均幂等）。
        try:
            _steps = (collect_tab_cleanup_steps(window)
                      + collect_window_cleanup_steps(window))
            run_cleanup_steps(_steps)
        except Exception as e:
            logger.warning(f"[Main] 退出清理失败: {e}")
    app.aboutToQuit.connect(_cleanup)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
