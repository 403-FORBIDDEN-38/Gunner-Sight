"""批次 3 浪 C3 契约测试（异常路径兜底两项）。

- M14：HotkeyLineEdit 在捕获态被销毁/关闭（hotkey_tab refresh 的
  deleteLater 路径）时，全局低级鼠标钩子必须释放——否则引用计数泄漏、
  钩子常驻到进程退出。
- M16：angle_meter_tab._load_profile_params 中途异常时 _loading 必须
  复位——否则永久 True，此后所有参数修改被静默丢弃。
"""
import pytest
from unittest.mock import MagicMock


def _make_angle_meter_tab(config, qapp):
    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine
    from gui.tabs.angle_meter_tab import AngleMeterTab

    return AngleMeterTab(config, HotkeyManager(config, StateMachine(config)))


def _fake_mouse_hook(monkeypatch):
    from gui import hotkey_widgets

    hook = MagicMock()
    monkeypatch.setattr(hotkey_widgets.MouseHook, "instance", staticmethod(lambda: hook))
    return hook


# ---------------------------------------------------------------- M14

def test_capturing_edit_destroyed_releases_hook(qapp, monkeypatch):
    """M14：deleteLater 销毁路径（无 closeEvent）也必须释放钩子。"""
    from PyQt5.QtCore import QEvent

    from gui.hotkey_widgets import HotkeyLineEdit

    hook = _fake_mouse_hook(monkeypatch)
    edit = HotkeyLineEdit()
    edit._start_capture()
    assert hook.acquire.call_count == 1

    edit.deleteLater()
    # processEvents() 默认不派发 DeferredDelete，必须显式 sendPostedEvents
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    assert hook.release.call_count == 1, "捕获态被销毁后钩子未释放——引用计数泄漏"


def test_capturing_edit_close_releases_hook(qapp, monkeypatch):
    """M14：closeEvent 路径同样释放。"""
    from gui.hotkey_widgets import HotkeyLineEdit

    hook = _fake_mouse_hook(monkeypatch)
    edit = HotkeyLineEdit()
    edit._start_capture()

    edit.close()
    assert hook.release.call_count == 1


def test_finish_capture_still_releases_once(qapp, monkeypatch):
    """M14 回归：正常捕获结束释放一次；随后再销毁不二次 release（幂等）。"""
    from PyQt5.QtCore import QEvent

    from gui.hotkey_widgets import HotkeyLineEdit

    hook = _fake_mouse_hook(monkeypatch)
    edit = HotkeyLineEdit()
    edit._start_capture()

    edit._finish_capture("a")
    assert hook.release.call_count == 1

    edit.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    assert hook.release.call_count == 1, "销毁路径重复 release——引用计数会被多减"


# ---------------------------------------------------------------- M16

def test_loading_flag_resets_on_param_load_failure(config, qapp, monkeypatch):
    """M16：_load_profile_params 中途异常，_loading 复位，参数通道不永久静默。"""
    tab = _make_angle_meter_tab(config, qapp)

    def _boom(name):
        raise RuntimeError("模拟射表解析失败")

    monkeypatch.setattr(tab, "_load_firing_table", _boom)
    with pytest.raises(RuntimeError):
        tab._load_profile_params("p1")
    assert tab._loading is False, "_loading 永久 True——此后参数修改全被静默丢弃"

    # 复位生效：参数变更不再被 _on_profile_param_changed 提前吞掉
    tab.config.add_angle_meter_profile("p1")
    tab.config.set_current_angle_meter_profile("p1")
    seen = []
    monkeypatch.setattr(tab, "_apply_current_profile_to_tracker", lambda: seen.append(1))
    tab._on_profile_param_changed()
    assert seen == [1]
