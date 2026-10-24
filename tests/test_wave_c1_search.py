"""批次 3 浪 C1 契约测试（搜索防抖，5 页统一模式）。

M12：textChanged 每按键全量重建列表（资源页还叠加引用索引重建 + 磁盘列举
+ 递归聚合）→ 停止输入 180ms 后才过滤一次。

覆盖：vehicle_config_tab / resource_tab / angle_meter_tab / magnifier_tab /
VehicleFilterWidget（overview quick_vf、squad_macro、angle_meter link 三处共用）。
"""
from PyQt5.QtTest import QTest

WAIT_MS = 400  # > 180ms 防抖窗口，确保 timeout 已触发


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
