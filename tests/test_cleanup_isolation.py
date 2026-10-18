"""B1 回归：清理路径的逐项隔离。

边界说明（重要）：
- 这些测试覆盖的是"前一步失败后，后一步仍然被调用"（B1 想修的契约）。
- 它们用 mock 替换真实资源（mss 句柄、线程等），测的是**代码路径**，
  不是"OS 资源真的释放了"。OS 层的资源泄漏靠代码审查保证，pytest 覆盖不到。
- 真实失败场景：Qt 对象在 C++ 侧被删后，Python 侧调方法抛 RuntimeError
  （"wrapped C/C++ object of type X has been deleted"）。关闭路径最容易出现。
"""
import pytest
from unittest.mock import Mock, patch

from core.cleanup import safe_call
from gui.tabs.angle_meter_tab import AngleMeterTab
from gui.tabs.magnifier_tab import MagnifierTab
from gui.tabs.squad_macro_tab import SquadMacroTab


def _make_tab(cls, config, qapp):
    """构造 tab，hotkey 用 mock（不装真实钩子）。"""
    hotkey = Mock()
    return cls(config, hotkey, parent=None)


# ---------- safe_call 本身 ----------

def test_safe_call_calls_fn():
    calls = []
    safe_call("test", lambda: calls.append(1))
    assert calls == [1]


def test_safe_call_swallows_exception_and_logs():
    import core.cleanup as cleanup_mod
    with patch.object(cleanup_mod.logger, "warning") as mock_warn:
        def boom():
            raise RuntimeError("boom")
        # 不应抛出
        safe_call("boom_fn", boom)
        # 应该有 warning 日志
        mock_warn.assert_called_once()
        assert "boom_fn" in mock_warn.call_args[0][0]


def test_safe_call_returns_none_on_success():
    assert safe_call("ok", lambda: 42) is None


# ---------- AngleMeterTab._shutdown_engine ----------

def test_angle_meter_shutdown_isolates_failures(config, qapp):
    """_up_tuner.stop 抛异常 → raw.close 仍然被调用（最关键的 mss 句柄）。"""
    tab = _make_tab(AngleMeterTab, config, qapp)
    up_tuner = Mock()
    up_tuner.stop.side_effect = RuntimeError("wrapped C/C++ object deleted")
    tab._up_tuner = up_tuner
    down_tuner = Mock()
    tab._down_tuner = down_tuner
    tab._timer = Mock()
    tracker = Mock()
    tab.tracker = tracker
    tab.calibrator = Mock()
    tab.overlay = Mock()
    raw = Mock()
    tab.raw = raw
    tab.angle_display = Mock()
    tab.cal_hint_label = Mock()

    tab._shutdown_engine()

    # 关键断言：即使第一步抛异常，raw.close 仍然被调用
    raw.close.assert_called_once()
    assert tab.raw is None
    # 其余也应该被调用（逐项隔离）
    down_tuner.stop.assert_called_once()
    tracker.stop.assert_called_once()


def test_angle_meter_shutdown_raw_first(config, qapp):
    """raw.close 应该在最前面执行（最贵的资源先释放）。"""
    tab = _make_tab(AngleMeterTab, config, qapp)
    tab._up_tuner = Mock()
    tab._down_tuner = Mock()
    tab._timer = Mock()
    tab.tracker = Mock()
    tab.calibrator = Mock()
    tab.overlay = Mock()
    tab.raw = Mock()
    tab.angle_display = Mock()
    tab.cal_hint_label = Mock()

    call_order = []
    tab.raw.close.side_effect = lambda: call_order.append("raw.close")
    tab._up_tuner.stop.side_effect = lambda: call_order.append("up_tuner.stop")
    tab.tracker.stop.side_effect = lambda: call_order.append("tracker.stop")

    tab._shutdown_engine()

    # raw.close 必须是第一个
    assert call_order[0] == "raw.close"


# ---------- MagnifierTab._destroy_engine ----------

def test_magnifier_destroy_isolates_failures(config, qapp):
    """overlay.set_active 抛异常 → overlay.close 仍然被调用。"""
    tab = _make_tab(MagnifierTab, config, qapp)
    overlay = Mock()
    overlay.set_active.side_effect = RuntimeError("wrapped C/C++ object deleted")
    tab.overlay = overlay

    tab._destroy_engine()

    overlay.close.assert_called_once()
    assert tab.overlay is None


# ---------- SquadMacroTab._shutdown_macro ----------

def test_squad_macro_shutdown_isolates_failures(config, qapp):
    """squad_macro.stop 抛异常 → squad_macro = None 仍然执行。"""
    tab = _make_tab(SquadMacroTab, config, qapp)
    tab.squad_macro = Mock()
    tab.squad_macro.running = True
    tab.squad_macro.stop.side_effect = RuntimeError("thread join failed")

    tab._shutdown_macro()

    assert tab.squad_macro is None


def test_squad_macro_shutdown_not_running(config, qapp):
    """squad_macro 不在运行 → 不调 stop，直接置 None。"""
    tab = _make_tab(SquadMacroTab, config, qapp)
    macro = Mock()
    macro.running = False
    tab.squad_macro = macro

    tab._shutdown_macro()

    macro.stop.assert_not_called()
    assert tab.squad_macro is None
