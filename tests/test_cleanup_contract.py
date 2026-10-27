"""core/cleanup.py：清理契约 SSOT 与关闭路径。

**为什么不许各写一份清单**（M19 / P1-3）
清理原本有四份独立实现：closeEvent / aboutToQuit / conftest teardown /
export_gui_facts。四份各漏各的，谁也不知道另外三份有什么。现在只有一份
契约表（core/cleanup.py），四个调用方只负责「什么时候跑」。

漏项的实证：export_gui_facts 只接了 tab 侧 collector，window 侧
（overlay/hotkey/滚轮/桌宠/配置保存）全漏；而 ammo_wheel 常驻鼠标钩子与
超时定时器，四份清单没有一处停它——关窗后钩子还挂着，滚轮事件继续注入。
test_collect_window_steps_includes_ammo_wheel 与
test_close_event_stops_ammo_wheel 在旧代码上必红，这是修复的有牙证明。

**中断即泄漏**（docs/RULES.md §2.1）
run_cleanup_steps 逐项 safe_call 隔离，一项崩不影响其余。现实里的典型失败是
Qt 对象在 C++ 侧已删除、Python 侧调方法抛 RuntimeError（"wrapped C/C++
object of type X has been deleted"）——关闭路径最容易撞上。

**边界说明（重要）**
这些用例用 mock 替换真实资源（mss 句柄、线程等），测的是**代码路径**，不是
"OS 资源真的释放了"。OS 层的资源泄漏靠代码审查保证，pytest 覆盖不到。

**只连不断**
OverlayRenderer 曾经只连不断：重复构造时新旧实例的回调叠加（Qt 信号持引用，
旧实例连同 overlay 窗口一起不释放），关窗后旧回调仍在响应状态变化。禁用模块
时 up/down tuner 同理——不断则旧 tuner 泄漏、重建后新旧双调（注入翻倍），
而 parent 是 tab，只丢 Python 引用还会每轮累积一个带 2 个 QTimer 的 QObject。
"""
import pytest
from unittest.mock import Mock, patch

from core.cleanup import (
    collect_tab_cleanup_steps,
    collect_window_cleanup_steps,
    run_cleanup_steps,
    safe_call,
)

ADVANCED = ("set_magnifier_enabled", "set_angle_meter_enabled",
            "set_distance_meter_enabled", "set_squad_macro_enabled")


def _enable_all(config):
    for setter in ADVANCED:
        getattr(config, setter)(True)


def _make_tab(cls, config, qapp):
    """构造 tab，hotkey 用 mock（不装真实钩子）。"""
    hotkey = Mock()
    return cls(config, hotkey, parent=None)


# ---------------------------------------------------------------- 替身

class _FakeTab:
    def __init__(self):
        self.calls = []

    def shutdown(self):
        self.calls.append("shutdown")

    def cleanup(self):
        self.calls.append("cleanup")


class _FakeWheel:
    def __init__(self):
        self.stop_called = False

    def stop(self):
        self.stop_called = True


class _FakeOverlay:
    def __init__(self):
        self.shutdown_called = False

    def shutdown(self):
        self.shutdown_called = True


class _FakeHotkey:
    def __init__(self):
        self.shutdown_called = False

    def shutdown(self):
        self.shutdown_called = True


class _FakeConfig:
    def __init__(self):
        self.saved = 0

    def save_config(self):
        self.saved += 1


class _FakeMascotTab:
    def __init__(self):
        self.shutdown_calls = 0

    def shutdown_mascot(self):
        self.shutdown_calls += 1


def _make_stub_window(tabs=None):
    """最小 window stub：只提供契约用到的属性（TAB_* 索引值任意，只看属性名）。"""

    class _StubWindow:
        pass

    w = _StubWindow()
    w._tabs = tabs if tabs is not None else {}
    w.TAB_ANGLE_METER = 5
    w.TAB_DISTANCE_METER = 4
    w.TAB_SQUAD_MACRO = 7
    w.TAB_MAGNIFIER = 6
    w.overlay = _FakeOverlay()
    w.hotkey = _FakeHotkey()
    w.config = _FakeConfig()
    w.ammo_wheel = _FakeWheel()
    w.get_tab = lambda idx: w._tabs.get(idx)
    return w


# ---------------------------------------------------------------- safe_call 本身

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


# ---------------------------------------------------------------- tab 清单

def test_collect_tab_steps_covers_four_tabs():
    """契约表覆盖全部四个需要清理的 tab；放大镜用 cleanup，其余用 shutdown。"""
    tabs = {5: _FakeTab(), 4: _FakeTab(), 7: _FakeTab(), 6: _FakeTab()}
    w = _make_stub_window(tabs)
    steps = collect_tab_cleanup_steps(w)
    assert [(label, fn.__name__) for label, fn in steps] == [
        ("角度仪", "shutdown"), ("标定测距", "shutdown"),
        ("建队宏", "shutdown"), ("放大镜", "cleanup"),
    ]
    idx_of = {"角度仪": 5, "标定测距": 4, "建队宏": 7, "放大镜": 6}
    for label, fn in steps:
        assert fn.__self__ is tabs[idx_of[label]]
    # 跑一遍：四个 tab 各调各的方法
    run_cleanup_steps(steps)
    for tab in tabs.values():
        assert tab.calls == ["shutdown"] or tab.calls == ["cleanup"]


def test_collect_tab_steps_skips_uncreated_and_missing_method():
    """未创建的 tab（get_tab 返回 None）与缺清理方法的 tab 都静默跳过。"""

    class _NoShutdown:
        pass

    tabs = {5: _NoShutdown(), 6: _FakeTab()}  # 角度仪缺 shutdown，放大镜在
    w = _make_stub_window(tabs)
    steps = collect_tab_cleanup_steps(w)
    assert [label for label, _ in steps] == ["放大镜"]


def test_collect_tab_steps_no_lazy_creation(window):
    """M19：退出路径的 collect 不触发懒加载（新建 tab 再马上清理，纯浪费与隐患）。"""
    for attr in ("TAB_ANGLE_METER", "TAB_DISTANCE_METER",
                 "TAB_SQUAD_MACRO", "TAB_MAGNIFIER"):
        assert window._tab_cache.get(getattr(window, attr)) is None
    assert collect_tab_cleanup_steps(window) == []
    # collect 之后四个契约 tab 依然没被创建
    for attr in ("TAB_ANGLE_METER", "TAB_DISTANCE_METER",
                 "TAB_SQUAD_MACRO", "TAB_MAGNIFIER"):
        assert window._tab_cache.get(getattr(window, attr)) is None


# ---------------------------------------------------------------- window 清单

def test_collect_window_steps_includes_ammo_wheel():
    """M18 有牙：契约必须包含弹种滚轮 stop——旧四份清理清单一项都没有。"""
    w = _make_stub_window()
    steps = collect_window_cleanup_steps(w)
    assert [label for label, _ in steps] == [
        "Overlay信号", "热键", "弹种滚轮", "配置保存",
    ]
    run_cleanup_steps(steps)
    assert w.ammo_wheel.stop_called
    assert w.overlay.shutdown_called
    assert w.hotkey.shutdown_called
    assert w.config.saved == 1


def test_collect_window_steps_skips_missing_attrs():
    """overlay/ammo_wheel 缺失（如测试 fixture、导出脚本）时对应项跳过，不抛异常。"""
    w = _make_stub_window()
    w.ammo_wheel = None
    w.overlay = None
    steps = collect_window_cleanup_steps(w)
    assert [label for label, _ in steps] == ["热键", "配置保存"]


def test_collect_window_steps_includes_mascot():
    """桌宠是窗口级资源：信息页已创建时契约含其清理入口（P0-2 顺带加固）。"""
    tab = _FakeMascotTab()
    w = _make_stub_window({8: tab})
    w.TAB_INFO = 8
    steps = collect_window_cleanup_steps(w)
    assert [label for label, _ in steps] == [
        "桌宠", "Overlay信号", "热键", "弹种滚轮", "配置保存",
    ]
    run_cleanup_steps(steps)
    assert tab.shutdown_calls == 1


# ---------------------------------------------------------------- 逐项隔离

def test_angle_meter_shutdown_isolates_failures(config, qapp):
    """_up_tuner.stop 抛异常 → raw.close 仍然被调用（最关键的 mss 句柄）。"""
    from gui.tabs.angle_meter_tab import AngleMeterTab

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
    from gui.tabs.angle_meter_tab import AngleMeterTab

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


def test_magnifier_destroy_isolates_failures(config, qapp):
    """overlay.set_active 抛异常 → overlay.close 仍然被调用。"""
    from gui.tabs.magnifier_tab import MagnifierTab

    tab = _make_tab(MagnifierTab, config, qapp)
    overlay = Mock()
    overlay.set_active.side_effect = RuntimeError("wrapped C/C++ object deleted")
    tab.overlay = overlay

    tab._destroy_engine()

    overlay.close.assert_called_once()
    assert tab.overlay is None


def test_squad_macro_shutdown_isolates_failures(config, qapp):
    """squad_macro.stop 抛异常 → squad_macro = None 仍然执行。"""
    from gui.tabs.squad_macro_tab import SquadMacroTab

    tab = _make_tab(SquadMacroTab, config, qapp)
    tab.squad_macro = Mock()
    tab.squad_macro.running = True
    tab.squad_macro.stop.side_effect = RuntimeError("thread join failed")

    tab._shutdown_macro()

    assert tab.squad_macro is None


def test_squad_macro_shutdown_not_running(config, qapp):
    """squad_macro 不在运行 → 不调 stop，直接置 None。"""
    from gui.tabs.squad_macro_tab import SquadMacroTab

    tab = _make_tab(SquadMacroTab, config, qapp)
    macro = Mock()
    macro.running = False
    tab.squad_macro = macro

    tab._shutdown_macro()

    macro.stop.assert_not_called()
    assert tab.squad_macro is None


def test_run_cleanup_steps_isolates_failures():
    """中断即泄漏：一项抛异常不阻断后续项。"""
    order = []

    def boom():
        raise RuntimeError("模拟清理崩溃")

    run_cleanup_steps([("甲", boom), ("乙", lambda: order.append("乙")), ("丙", boom)])
    assert order == ["乙"]


def test_run_cleanup_steps_on_step_callback():
    """on_step 回调逐项收到 (label, 耗时ms)——closeEvent 的耗时日志靠它。"""
    seen = []
    run_cleanup_steps([("甲", lambda: None), ("乙", lambda: None)],
                      on_step=lambda label, ms: seen.append((label, ms >= 0)))
    assert seen == [("甲", True), ("乙", True)]


# ---------------------------------------------------------------- 只连不断

def test_shutdown_disconnects_state_signals(config, qapp):
    """OverlayRenderer.shutdown() 必须真正断开 StateMachine 信号（S7）。"""
    from core.overlay import OverlayRenderer
    from core.state_machine import StateMachine

    state = StateMachine(config)
    renderer = OverlayRenderer(config, state)

    # 连接有效：vehicle_changed 会置位抑制旗（_on_vehicle_changed 的第一个动作）
    state.vehicle_changed.emit("V")
    assert renderer._vehicle_change_in_progress is True

    renderer.shutdown()

    # 断开后：再 emit 不应触发任何回调
    renderer._vehicle_change_in_progress = False
    state.vehicle_changed.emit("V2")
    assert renderer._vehicle_change_in_progress is False


def test_ammo_wheel_stop_disconnects_state_signals(config, qapp, monkeypatch):
    """P2-2：stop() 断开自己建立的连接；重复 stop 不抛（幂等）。"""
    from PyQt5.QtCore import QObject, pyqtSignal

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


def test_shutdown_engine_deletes_tuner_cpp_objects(config, qapp):
    """P2-1：_shutdown_engine 必须把 tuner 的 C++ 对象真正删掉。

    只丢 Python 引用不够——parent 是 tab，每轮禁用/启用就累积一个带 2 个
    QTimer 的 QObject。
    """
    from PyQt5 import sip
    from PyQt5.QtCore import QEvent, QObject
    from PyQt5.QtWidgets import QApplication

    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine
    from gui.tabs.angle_meter_tab import AngleMeterTab

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

    tab = AngleMeterTab(config, HotkeyManager(config, StateMachine(config)))
    up, down = _FakeTuner(tab), _FakeTuner(tab)
    tab._up_tuner, tab._down_tuner = up, down

    tab._shutdown_engine()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    assert up.stopped and down.stopped
    assert sip.isdeleted(up), "up_tuner 未 deleteLater（C++ 对象泄漏在 tab 下）"
    assert sip.isdeleted(down), "down_tuner 未 deleteLater（C++ 对象泄漏在 tab 下）"


# ---------------------------------------------------------------- 关闭路径端到端

def test_close_event_runs_full_shutdown(window, config, monkeypatch):
    """closeEvent 全套清理零异常（含 Overlay 信号断开这项新接线）。

    closeEvent 的每一项清理都只记日志、不中断后续，所以「没崩」不等于「干净」。
    本测试要求**连日志级异常都没有**——守的正是「新增清理项接错线」这类静默回归。
    """
    from PyQt5.QtGui import QCloseEvent

    from core import logger as logger_mod

    messages = []
    monkeypatch.setattr(logger_mod.logger, "info",
                        lambda msg, *a, **k: messages.append(str(msg)))

    _enable_all(config)
    window._create_ui_frame()
    window._create_first_tab()

    window.closeEvent(QCloseEvent())

    bad = [m for m in messages if "关闭异常" in m]
    assert not bad, f"closeEvent 清理异常: {bad}"


def test_close_event_stops_ammo_wheel(window):
    """M18+M19 端到端：closeEvent 跑完整契约——四 tab + overlay/hotkey/滚轮/配置保存。

    旧 closeEvent 的硬编码清单没有弹种滚轮，本测试在旧代码上必红。
    tab 方法用实例属性替换（契约 collect 时现场 getattr，能拿到替身；
    区别于 PyQt 信号连接——那个必须连时就绑定）。finally 里还原，
    保证 fixture teardown 跑真清理。
    """
    from PyQt5.QtGui import QCloseEvent

    contract_idxs = (window.TAB_ANGLE_METER, window.TAB_DISTANCE_METER,
                     window.TAB_SQUAD_MACRO, window.TAB_MAGNIFIER)
    window._create_ui_frame()
    window._create_first_tab()
    for idx in contract_idxs:
        window._ensure_tab(idx)
    tabs = {idx: window.get_tab(idx) for idx in contract_idxs}
    calls = []
    originals = {}
    try:
        for idx, tab in tabs.items():
            method = "cleanup" if idx == window.TAB_MAGNIFIER else "shutdown"
            originals[idx] = getattr(tab, method)
            setattr(tab, method, lambda idx=idx: calls.append(idx))
        wheel = _FakeWheel()
        window.ammo_wheel = wheel

        window.closeEvent(QCloseEvent())

        assert sorted(calls) == sorted(contract_idxs)
        assert wheel.stop_called  # M18 有牙点
    finally:
        for idx, fn in originals.items():
            method = "cleanup" if idx == window.TAB_MAGNIFIER else "shutdown"
            setattr(tabs[idx], method, fn)


def test_angle_meter_disable_disconnects_old_tuners(window, config):
    """S5：禁用后旧 tuner 的信号必须已断开（不断则泄漏 + 重建后双调）。"""
    _enable_all(config)
    window._create_ui_frame()
    window._create_first_tab()
    tab = window.get_tab(window.TAB_ANGLE_METER)
    assert tab is not None

    tab._init_engine()
    old_up, old_down = tab._up_tuner, tab._down_tuner
    assert old_up is not None and old_down is not None

    tab._shutdown_engine()

    # 断开探针：旧 tuner 的槽此时应处于"未连接"状态（disconnect 抛 TypeError）
    with pytest.raises(TypeError):
        tab.hotkey.angle_meter_up_pressed.disconnect(old_up.on_pressed)
    with pytest.raises(TypeError):
        tab.hotkey.angle_meter_down_released.disconnect(old_down.on_released)


def test_angle_meter_enable_disable_cycles_are_clean(window, config):
    """10 轮启用/禁用循环：无异常，且每轮旧 tuner 都断开（不累积连接）。"""
    _enable_all(config)
    window._create_ui_frame()
    window._create_first_tab()
    tab = window.get_tab(window.TAB_ANGLE_METER)
    assert tab is not None

    for _ in range(10):
        tab._init_engine()
        old_up = tab._up_tuner
        tab._shutdown_engine()
        with pytest.raises(TypeError):
            tab.hotkey.angle_meter_up_pressed.disconnect(old_up.on_pressed)


# ---------------------------------------------------------------- 静态接线

def test_all_cleanup_call_sites_use_both_collectors():
    """P1-3：四个清理调用方必须同时接 tab 与 window 两个 collector。

    §2.3 漏项根因：export_gui_facts 只接 tab 侧，window 侧（overlay/hotkey/
    滚轮/桌宠/配置保存）全漏。静态锁住接线，防再次漂移。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for rel in ("gui/main_window.py", "main.py", "tests/conftest.py",
                "tools/export_gui_facts.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "collect_tab_cleanup_steps" in src, f"{rel} 缺 tab 侧 collector"
        assert "collect_window_cleanup_steps" in src, f"{rel} 缺 window 侧 collector"
