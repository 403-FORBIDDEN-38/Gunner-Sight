"""批次 3 浪 B 契约测试（vehicle_config_tab 列表语义三项 + resource_tab 对应处）。

- M10：重命名载具时取消 / 空名 / 未改名一律静默 return，不误报「已存在」
  （对齐 _on_rename_tag / _on_rename_ammo 的语义）。
- M11：倍率列表选中恢复必须包 _suppress_mag_writeback，恢复选中不得
  触发 _on_mag_user_selected 回写 state（对齐 vehicle/ammo 语义）。
- M17：splitter 尺寸只在拖动结束（handle 的 MouseButtonRelease）时落盘，
  拖动中的 splitterMoved 不写 config（vehicle_config / resource_tab 两处）。
"""


def _make_vehicle_tab(config, qapp):
    from core.resource_manager import ResourceManager
    from core.state_machine import StateMachine
    from gui.tabs.vehicle_config_tab import VehicleConfigTab

    state = StateMachine(config)
    resources = ResourceManager()
    return VehicleConfigTab(config, state, resources)


def _make_resource_tab(config, qapp):
    from core.resource_manager import ResourceManager
    from gui.tabs.resource_tab import ResourceTab

    resources = ResourceManager()
    return ResourceTab(config, resources)


def _patch_mag_config(tab, monkeypatch):
    """让 _refresh_mag_list 走通：两条倍率，无绑定。"""
    monkeypatch.setattr(tab, "_get_selected_vehicle", lambda: "V1")
    monkeypatch.setattr(tab, "_get_selected_ammo", lambda: "AP")
    monkeypatch.setattr(tab.config, "get_magnifications", lambda v: [{"label": "1x"}, {"label": "2x"}])
    monkeypatch.setattr(tab.config, "get_crosshair_path", lambda *a: "")
    monkeypatch.setattr(tab.config, "get_magnification_overlay_mode", lambda *a: False)
    monkeypatch.setattr(tab.config, "get_overlay_vehicle_ui", lambda *a: False)
    monkeypatch.setattr(tab.config, "get_overlay_ammo_ui", lambda *a: False)


# ---------------------------------------------------------------- M10

def test_rename_cancel_silent(config, qapp, monkeypatch):
    """M10：对话框取消 → 静默 return，不弹警告、不动 state。"""
    from PyQt5.QtWidgets import QInputDialog, QMessageBox

    tab = _make_vehicle_tab(config, qapp)
    monkeypatch.setattr(tab, "_get_selected_vehicle", lambda: "V1")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("随便", False))
    warns, renamed = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))
    monkeypatch.setattr(tab.state, "rename_vehicle", lambda o, n: renamed.append((o, n)))

    tab._on_rename_vehicle()
    assert warns == []
    assert renamed == []


def test_rename_empty_and_same_name_silent(config, qapp, monkeypatch):
    """M10：空名 / 未改名 → 同样静默（原实现两者都误报「已存在」）。"""
    from PyQt5.QtWidgets import QInputDialog, QMessageBox

    tab = _make_vehicle_tab(config, qapp)
    monkeypatch.setattr(tab, "_get_selected_vehicle", lambda: "V1")
    warns = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))
    monkeypatch.setattr(tab.state, "rename_vehicle", lambda o, n: warns.append(("renamed", o, n)))

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("   ", True))  # 空名
    tab._on_rename_vehicle()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("V1", True))  # 同名
    tab._on_rename_vehicle()

    assert warns == []


def test_rename_actual_change_still_executes(config, qapp, monkeypatch):
    """M10 反面：真正改名仍执行（修复没把路堵死）。"""
    from PyQt5.QtWidgets import QInputDialog

    tab = _make_vehicle_tab(config, qapp)
    monkeypatch.setattr(tab, "_get_selected_vehicle", lambda: "V1")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("V2", True))
    calls = []
    monkeypatch.setattr(tab.state, "rename_vehicle", lambda o, n: calls.append(("rename", o, n)))
    monkeypatch.setattr(tab, "_refresh_vehicle_list", lambda: calls.append("refresh"))
    monkeypatch.setattr(tab, "_select_row_by_data", lambda w, n: calls.append(("select", n)))

    tab._on_rename_vehicle()
    assert calls[0] == ("rename", "V1", "V2")
    assert "refresh" in calls


# ---------------------------------------------------------------- M11

def test_mag_restore_suppresses_writeback(config, qapp, monkeypatch):
    """M11：倍率列表选中恢复不得回写 state。

    观测点是 state.set_magnification（_on_mag_user_selected 真身的终点）——
    不能替换实例属性：Qt 信号在构造时已绑定原方法，替换是假绿。
    同时把 state 停在 0（≠ 恢复目标 1）：旧实现的「idx 相等」兜底不生效，
    裸 setCurrentRow(1) 会经真身写 state。
    """
    tab = _make_vehicle_tab(config, qapp)
    _patch_mag_config(tab, monkeypatch)

    # 预置三行旧条目并选中 idx=1
    tab.mag_list.add_item("old1", "", user_data=0)
    tab.mag_list.add_item("old2", "", user_data=1)
    tab.mag_list.add_item("old3", "", user_data=2)
    tab.mag_list.setCurrentRow(1)

    tab.state.set_magnification(0)
    writes = []
    monkeypatch.setattr(tab.state, "set_magnification", lambda i: writes.append(i))

    tab._refresh_mag_list()  # keep_selection=True → 恢复到 idx=1（新 item 对象）
    assert writes == [], "选中恢复回写了 state——_suppress_mag_writeback 未包裹"


def test_mag_writeback_chain_is_live(config, qapp, monkeypatch):
    """M11 有牙证明：信号链是活的——无抑制时换行会经真身写 state。

    与上一个测试互为表里：这个证明「裸 setCurrentRow 确实会写」（旧 bug 的
    机制），上一个证明 refresh 的恢复路径挡住了它。
    """
    tab = _make_vehicle_tab(config, qapp)
    _patch_mag_config(tab, monkeypatch)

    tab.mag_list.add_item("old1", "", user_data=0)
    tab.mag_list.add_item("old2", "", user_data=1)
    tab.mag_list.setCurrentRow(0)
    tab.state.set_magnification(0)

    writes = []
    monkeypatch.setattr(tab.state, "set_magnification", lambda i: writes.append(i))
    tab.mag_list.setCurrentRow(1)  # 用户点击等价路径
    assert writes == [1], "信号链没通——suppress 测试是假绿"


def test_mag_restore_suppress_flag_reset_after_refresh(config, qapp, monkeypatch):
    """M11 副作用防护：refresh 后抑制旗必须复位（否则后续真实点击被静默丢弃）。"""
    tab = _make_vehicle_tab(config, qapp)
    _patch_mag_config(tab, monkeypatch)
    tab.mag_list.add_item("old1", "", user_data=0)
    tab.mag_list.setCurrentRow(0)
    tab._refresh_mag_list()
    assert tab._suppress_mag_writeback is False


# ---------------------------------------------------------------- M17

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
