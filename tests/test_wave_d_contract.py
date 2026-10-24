"""浪 D：退出收口与清理契约（M18/M19）。

M18：ammo_wheel.stop() 进退出路径。滚轮模块常驻鼠标钩子（MouseHook）与
超时定时器，此前四份清理实现（closeEvent / aboutToQuit / conftest /
export_gui_facts）没有一处停它——关窗后钩子还挂着，滚轮事件继续注入。
有牙证明：test_collect_window_steps_includes_ammo_wheel 与
test_close_event_stops_ammo_wheel 在旧代码上必红（旧清单无「弹种滚轮」项）。

M19：清理契约 SSOT（core/cleanup.py）。四份调用方只负责「什么时候跑」，
「清理什么、调什么方法」只有一份。AGENTS §2.1「中断即泄漏」：
run_cleanup_steps 逐项 safe_call 隔离，一项崩不影响其余。
"""
from core.cleanup import (
    collect_tab_cleanup_steps,
    collect_window_cleanup_steps,
    run_cleanup_steps,
)


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


# ---------------- tab 清单 ----------------

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


# ---------------- window 清单（M18 主战场） ----------------

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


# ---------------- 逐项隔离（AGENTS §2.1） ----------------

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
