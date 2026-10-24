"""共享测试夹具。

约定（务必遵守，否则会污染用户环境）：
- 全部用例使用 offscreen Qt：不弹窗、不抢焦点。
- 不安装任何全局钩子（不调用 HotkeyManager.initialize()）。
- ConfigManager 一律指向 tmp_path，**绝不读写用户的 config/config.json**。
"""
import os
import sys

WS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WS_ROOT not in sys.path:
    sys.path.insert(0, WS_ROOT)

# 必须在创建 QApplication 之前设置，否则 Qt 会尝试连真实显示
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """整个测试会话共用一个 QApplication（Qt 不允许创建多个）。"""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def config(tmp_path, qapp):
    """最小骨架配置，落在临时目录，不触碰用户真实配置。"""
    from core.config_manager import ConfigManager

    return ConfigManager(config_dir=str(tmp_path))


@pytest.fixture
def window(config, qapp):
    """完整的 MainWindow（离屏，不显示）。"""
    from core.hotkey_manager import HotkeyManager
    from core.overlay import OverlayRenderer
    from core.resource_manager import ResourceManager
    from core.state_machine import StateMachine
    from gui.main_window import MainWindow

    state = StateMachine(config)
    resources = ResourceManager()
    hotkey = HotkeyManager(config, state)
    overlay = OverlayRenderer(config, state)

    win = MainWindow(config, state, overlay, hotkey, resources)
    yield win

    # M19：清理口径与 closeEvent 同一份契约（core.cleanup SSOT）。
    # 含 overlay 常驻 scanner 显式停（request_stop + wait）——否则 prescan
    # 长队列在进程退出时才被 join，每个用例都白等几十秒。
    from core.cleanup import (
        collect_tab_cleanup_steps,
        collect_window_cleanup_steps,
        run_cleanup_steps,
    )
    _steps = (collect_tab_cleanup_steps(win)
              + collect_window_cleanup_steps(win))
    run_cleanup_steps(_steps)
