"""弹种重命名的契约（倍率绑定不得在画面上消失 + 右键菜单可达）。

背景：数据层从来没丢过绑定（crosshairs 是弹种字典内部的一份，改 key 不动
它），但 UI 会在重命名瞬间按「旧名」去查一次路径：

    state.rename_ammo_type → config 改 key → set_ammo_type(new)
      → ammo_type_changed → on_external_ammo_changed
        → _refresh_mag_list 里 _get_selected_ammo() 读到的仍是列表上的旧名
          → get_crosshair_path(vehicle, 旧名, i) 全空 → 三行全部显示
            「双击绑定图片」

随后 `_refresh_ammo_list()` 再拿旧名当恢复目标，列表找不到 → currentRow=-1。
用户看到的就是「我把弹种改了个名，倍率绑定全没了」。
"""

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QInputDialog, QMenu, QMessageBox

PLACEHOLDER = "双击绑定图片"


@pytest.fixture
def vconfig(config):
    """V1 / MG + SMK / 三条倍率，两个弹种各自绑好三张图。"""
    config.add_vehicle("V1")
    config.add_ammo_type("V1", "MG")
    config.add_ammo_type("V1", "SMK")
    for _ in range(3):
        config.add_magnification("V1", "")
    for i in range(3):
        config.set_crosshair_path("V1", "MG", i, f"mg{i}.png")
        config.set_crosshair_path("V1", "SMK", i, f"smk{i}.png")
    return config


def _make_tab(config, qapp):
    """载具页 + 复刻 main_window._connect_tab_signals(TAB_VEHICLE) 的三条连线。"""
    from core.resource_manager import ResourceManager
    from core.state_machine import StateMachine
    from gui.tabs.vehicle_config_tab import VehicleConfigTab

    state = StateMachine(config)
    state.set_vehicle("V1")
    state.set_ammo_type("MG")
    state.set_magnification(1)
    tab = VehicleConfigTab(config, state, ResourceManager())
    state.vehicle_changed.connect(tab.on_external_vehicle_changed)
    state.ammo_type_changed.connect(tab.on_external_ammo_changed)
    state.magnification_changed.connect(tab.on_external_mag_changed)
    tab._refresh_ammo_list(force_select="MG")
    tab._refresh_mag_list(select_idx=1)
    return state, tab


def _mag_subs(tab):
    """倍率列表「画面上」显示的绑定文字（占位语说明该行显示为空）。"""
    return [
        tab.mag_list.itemWidget(tab.mag_list.item(i))._sub_text
        for i in range(tab.mag_list.count())
    ]


def _current_ammo(tab):
    item = tab.ammo_list.currentItem()
    return item.data(Qt.UserRole) if item else None


# ---------------------------------------------------------------- 数据层

def test_config_rename_ammo_preserves_crosshairs_and_hotkey(vconfig):
    """数据层本就完好：改 key 不动 crosshairs，热键键名跟着搬。"""
    hk_before = dict(vconfig.get_ammo_hotkey("V1", "MG"))
    assert vconfig.rename_ammo_type("V1", "MG", "MG2") is True
    assert [vconfig.get_crosshair_path("V1", "MG2", i) for i in range(3)] == [
        "mg0.png", "mg1.png", "mg2.png",
    ]
    assert vconfig.get_ammo_hotkey("V1", "MG2") == hk_before
    assert "MG" not in vconfig.get_ammo_types("V1")


def test_state_rename_ammo_reports_result_and_keeps_ammo_on_collision(vconfig, qapp):
    """撞名返回 False，且**不许**把当前弹种静默切到那个已存在的同名弹种。"""
    from core.state_machine import StateMachine

    state = StateMachine(vconfig)
    state.set_vehicle("V1")
    state.set_ammo_type("MG")
    assert state.rename_ammo_type("V1", "MG", "SMK") is False
    assert state.current_ammo_type == "MG"
    assert state.rename_ammo_type("V1", "MG", "MG2") is True
    assert state.current_ammo_type == "MG2"


# ---------------------------------------------------------------- 界面层

def test_rename_current_ammo_keeps_bindings_visible(vconfig, qapp, monkeypatch):
    """核心回归：重命名当前弹种后，倍率行不得退化成占位语，列表不得空选中。"""
    state, tab = _make_tab(vconfig, qapp)
    assert _mag_subs(tab) == ["mg0.png", "mg1.png", "mg2.png"]

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("MG2", True))
    tab._on_rename_ammo()

    assert _mag_subs(tab) == ["mg0.png", "mg1.png", "mg2.png"], "重命名后画面上的绑定丢了"
    assert _current_ammo(tab) == "MG2", "重命名后弹种列表空选中"
    assert state.current_ammo_type == "MG2"
    assert tab.mag_list.currentRow() == 1


def test_rename_ammo_collision_warns_without_touching_anything(
    vconfig, qapp, monkeypatch
):
    """撞名：弹一条提示，数据与画面都不动（旧实现既无提示又切走弹种）。"""
    state, tab = _make_tab(vconfig, qapp)
    warns = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("SMK", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))

    tab._on_rename_ammo()

    assert len(warns) == 1
    assert set(vconfig.get_ammo_types("V1")) == {"MG", "SMK"}
    assert state.current_ammo_type == "MG"
    assert _current_ammo(tab) == "MG"
    assert _mag_subs(tab) == ["mg0.png", "mg1.png", "mg2.png"]


def test_rename_ammo_cancel_is_silent(vconfig, qapp, monkeypatch):
    """取消 / 空名 / 未改名：静默 return，不弹提示、不动数据（M10 语义）。"""
    state, tab = _make_tab(vconfig, qapp)
    warns = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))

    for answer in (("", False), ("   ", True), ("MG", True)):
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, _r=answer, **k: _r)
        tab._on_rename_ammo()

    assert warns == []
    assert set(vconfig.get_ammo_types("V1")) == {"MG", "SMK"}


# ---------------------------------------------------------------- 右键菜单

def _open_ammo_menu(tab, monkeypatch, exec_impl):
    monkeypatch.setattr(QMenu, "exec_", exec_impl)
    monkeypatch.setattr(tab.ammo_list, "itemAt", lambda pos: tab.ammo_list.item(0))
    tab._on_ammo_list_context_menu(QPoint(1, 1))


def test_ammo_context_menu_offers_rename(vconfig, qapp, monkeypatch):
    """弹种右键菜单必须给到重命名（此前只有「清除弹种UI绑定」「删除弹种」）。"""
    _state, tab = _make_tab(vconfig, qapp)
    seen = {}

    def fake_exec(menu_self, *a, **k):
        seen["labels"] = [act.text() for act in menu_self.actions() if act.text()]
        return None

    _open_ammo_menu(tab, monkeypatch, fake_exec)

    assert "重命名" in seen["labels"]
    assert "删除弹种" in seen["labels"]
    assert "清除弹种UI绑定" in seen["labels"]


def test_ammo_context_menu_rename_actually_renames(vconfig, qapp, monkeypatch):
    """点菜单里的「重命名」要真走重命名（并保住绑定）。"""
    _state, tab = _make_tab(vconfig, qapp)

    def choose_rename(menu_self, *a, **k):
        for act in menu_self.actions():
            if act.text() == "重命名":
                return act
        return None

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("MG2", True))
    _open_ammo_menu(tab, monkeypatch, choose_rename)

    assert "MG2" in vconfig.get_ammo_types("V1")
    assert _mag_subs(tab) == ["mg0.png", "mg1.png", "mg2.png"]
