"""批次 4 浪 3：P2 四项契约测试。

P2-1（S5）：禁用模块时 _up_tuner/_down_tuner 必须 deleteLater——parent 是
tab，只丢 Python 引用则每轮禁用/启用累积一个带 2 个 QTimer 的 QObject。
P2-2（M6）：AmmoWheelSelector.stop() 反向断开自己建立的四条连接，且幂等
（closeEvent + aboutToQuit 双跑）。
P2-3 是 FIX_PLAN 文案点名（无代码）；P2-4 mss 上界属 pyproject，由
uv lock --check 命令级验证。
"""
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QApplication


class _FakeTuner(QObject):
    """最小 tuner 替身：_shutdown_engine 会调 on_pressed/on_released/stop。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stopped = False

    def on_pressed(self):
        pass

    def on_released(self):
        pass

    def stop(self):
        self.stopped = True


def test_shutdown_engine_deletes_tuner_cpp_objects(config, qapp):
    """P2-1：_shutdown_engine 必须把 tuner 的 C++ 对象真正删掉。"""
    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine
    from gui.tabs.angle_meter_tab import AngleMeterTab

    tab = AngleMeterTab(config, HotkeyManager(config, StateMachine(config)))
    up, down = _FakeTuner(tab), _FakeTuner(tab)
    tab._up_tuner, tab._down_tuner = up, down

    tab._shutdown_engine()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    assert up.stopped and down.stopped
    assert sip.isdeleted(up), "up_tuner 未 deleteLater（C++ 对象泄漏在 tab 下）"
    assert sip.isdeleted(down), "down_tuner 未 deleteLater（C++ 对象泄漏在 tab 下）"


def test_ammo_wheel_stop_disconnects_state_signals(config, qapp, monkeypatch):
    """P2-2：stop() 断开自己建立的连接；重复 stop 不抛（幂等）。"""
    from PyQt5.QtCore import pyqtSignal

    from core import ammo_wheel_selector as mod

    class _FakeHook(QObject):
        mouse_wheel = pyqtSignal(int)
        mouse_down = pyqtSignal(str)

        def __init__(self):
            super().__init__()
            self.acquired = 0
            self.released = 0

        def acquire(self):
            self.acquired += 1

        def release(self):
            self.released += 1

    class _FakeState(QObject):
        ammo_type_changed = pyqtSignal(str)
        magnification_changed = pyqtSignal(int)
        current_vehicle = "T-72"

    hook = _FakeHook()
    state = _FakeState()
    monkeypatch.setattr(mod.MouseHook, "instance", classmethod(lambda cls: hook))
    monkeypatch.setattr(config, "get_ammo_type_names", lambda v: ["AP", "HE"])

    wheel = mod.AmmoWheelSelector(state, config)
    wheel._active = False
    wheel._preview_index = -1

    wheel.stop()
    wheel.stop()  # 幂等：第二次不抛异常
    assert hook.released == 2

    # 已断开：state 信号不再驱动滚轮（未断开时 _preview_index 会变成 0）
    state.ammo_type_changed.emit("AP")
    assert wheel._preview_index == -1
