"""gui/tabs/*：各设置页共用的两种交互模式（搜索防抖、splitter 落盘时机）。

这两个契约都是「同一模式在多页各写一遍」的收敛。模式本身错了不会崩，只是
手感变差或者写盘过频，用户也不会报——所以必须锁住。

**搜索防抖（M12）**
textChanged 每按键全量重建列表（资源页还叠加引用索引重建 + 磁盘列举 + 递归
聚合）→ 改为停止输入 180ms 后才过滤一次。覆盖五处：vehicle_config_tab /
resource_tab / angle_meter_tab / magnifier_tab / VehicleFilterWidget
（overview quick_vf、squad_macro、angle_meter link 三处共用）。
切标签下拉同样走防抖——离散操作，延迟 180ms 无感，模式统一。

**splitter 只在拖动结束落盘（M17）**
拖动中的 splitterMoved 不写 config，handle 的 MouseButtonRelease 才写一次。
vehicle_config / resource_tab 两处独立修改，都要锁住。
"""
from PyQt5.QtTest import QTest

WAIT_MS = 400  # > 180ms 防抖窗口，确保 timeout 已触发


# ---------------------------------------------------------------- 页面构造

def _make_vehicle_tab(config, qapp):
    from core.resource_manager import ResourceManager
    from core.state_machine import StateMachine
    from gui.tabs.vehicle_config_tab import VehicleConfigTab

    return VehicleConfigTab(config, StateMachine(config), ResourceManager())


def _make_resource_tab(config, qapp):
    from core.resource_manager import ResourceManager
    from gui.tabs.resource_tab import ResourceTab

    return ResourceTab(config, ResourceManager())


def _make_angle_meter_tab(config, qapp):
    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine
    from gui.tabs.angle_meter_tab import AngleMeterTab

    return AngleMeterTab(config, HotkeyManager(config, StateMachine(config)))


def _make_magnifier_tab(config, qapp):
    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine
    from gui.tabs.magnifier_tab import MagnifierTab

    return MagnifierTab(config, HotkeyManager(config, StateMachine(config)))


# ---------------------------------------------------------------- 搜索防抖

def test_vehicle_config_search_debounced(config, qapp, monkeypatch):
    """输入过程中不过滤；停止输入后只过滤一次（最后一次输入生效）。"""
    tab = _make_vehicle_tab(config, qapp)
    calls = []
    monkeypatch.setattr(tab, "_refresh_vehicle_list", lambda **k: calls.append(1))

    tab.vehicle_search.setText("a")
    tab.vehicle_search.setText("ab")
    tab.vehicle_search.setText("abc")
    assert calls == [], "输入中不应触发过滤"

    QTest.qWait(WAIT_MS)
    assert len(calls) == 1, "停止输入后应只过滤一次"


def test_resource_search_debounced(config, qapp, monkeypatch):
    """资源页（最重路径：磁盘列举+索引重建）同样防抖。"""
    tab = _make_resource_tab(config, qapp)
    calls = []
    monkeypatch.setattr(tab, "_refresh_tree", lambda: calls.append(1))

    tab.resource_search.setText("x")
    tab.resource_search.setText("xy")
    assert calls == []

    QTest.qWait(WAIT_MS)
    assert len(calls) == 1


def test_angle_meter_profile_search_debounced(config, qapp, monkeypatch):
    tab = _make_angle_meter_tab(config, qapp)
    calls = []
    monkeypatch.setattr(tab, "_refresh_profile_list", lambda: calls.append(1))

    tab.profile_search.setText("p")
    tab.profile_search.setText("pp")
    assert calls == []

    QTest.qWait(WAIT_MS)
    assert len(calls) == 1


def test_magnifier_preset_search_debounced(config, qapp, monkeypatch):
    tab = _make_magnifier_tab(config, qapp)
    calls = []
    monkeypatch.setattr(tab, "_refresh_preset_list", lambda: calls.append(1))

    tab.preset_search.setText("m")
    tab.preset_search.setText("mm")
    assert calls == []

    QTest.qWait(WAIT_MS)
    assert len(calls) == 1


def test_vehicle_filter_widget_search_debounced(qapp):
    """VehicleFilterWidget（overview/squad_macro/angle_meter link 共用）内部防抖。"""
    from gui.widgets import VehicleFilterWidget

    w = VehicleFilterWidget(mode="select")
    fired = []
    w.filter_changed.connect(lambda: fired.append(1))

    w.search.setText("a")
    w.search.setText("ab")
    assert fired == []

    QTest.qWait(WAIT_MS)
    assert len(fired) == 1


def test_vehicle_filter_widget_tag_change_debounced(qapp):
    """切标签下拉同样走防抖（离散操作，延迟 180ms 无感，模式统一）。"""
    from gui.widgets import VehicleFilterWidget

    w = VehicleFilterWidget(mode="select")
    w.set_tags(["装甲", "轻甲"])
    fired = []
    w.filter_changed.connect(lambda: fired.append(1))

    w.tag_combo.setCurrentIndex(1)
    assert fired == []

    QTest.qWait(WAIT_MS)
    assert len(fired) == 1


# ---------------------------------------------------------------- splitter 落盘时机

def _release_event():
    from PyQt5.QtCore import QEvent, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent

    return QMouseEvent(QEvent.MouseButtonRelease, QPointF(1, 1),
                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)


def test_vehicle_config_splitter_saves_only_on_release(config, qapp, monkeypatch):
    """M17：拖动中 splitterMoved 不写 config；handle release 才写一次。"""
    tab = _make_vehicle_tab(config, qapp)
    saved = []
    monkeypatch.setattr(tab.config, "set_splitter_sizes", lambda n, s: saved.append((n, s)))

    tab._on_splitter_moved(10, 1)
    tab._on_splitter_moved(20, 1)
    assert saved == [], "拖动中不应落盘"

    tab.eventFilter(tab.splitter.handle(1), _release_event())
    assert len(saved) == 1 and saved[0][0] == "vehicle_config"

    # release 后再无脏标记，重复 release 不重复写
    tab.eventFilter(tab.splitter.handle(1), _release_event())
    assert len(saved) == 1


def test_resource_tab_splitter_saves_only_on_release(config, qapp, monkeypatch):
    """M17：resource_tab 同契约（两处独立修改，都要锁住）。"""
    tab = _make_resource_tab(config, qapp)
    saved = []
    monkeypatch.setattr(tab.config, "set_splitter_sizes", lambda n, s: saved.append((n, s)))

    tab._on_splitter_moved(5, 1)
    assert saved == []

    tab.eventFilter(tab.splitter.handle(1), _release_event())
    assert len(saved) == 1 and saved[0][0] == "resource_tab"
