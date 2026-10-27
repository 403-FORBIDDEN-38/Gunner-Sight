"""core/config/vehicle.py + gui/tabs/vehicle_config_tab.py：载具/弹种配置契约。

**改名不许丢东西，也不许乱动**
弹种改名：数据层从来没丢过绑定（crosshairs 是弹种字典内部的一份，改 key 不动
它），但 UI 会在重命名瞬间按「旧名」去查一次路径：

    state.rename_ammo_type → config 改 key → set_ammo_type(new)
      → ammo_type_changed → on_external_ammo_changed
        → _refresh_mag_list 里 _get_selected_ammo() 读到的仍是列表上的旧名
          → get_crosshair_path(vehicle, 旧名, i) 全空 → 三行全部显示
            「双击绑定图片」

随后 `_refresh_ammo_list()` 再拿旧名当恢复目标，列表找不到 → currentRow=-1。
用户看到的就是「我把弹种改了个名，倍率绑定全没了」。判据因此是：**改数据 →
重建视图 → 按 state 选中 → 再刷下游**，不允许在「视图还显示旧名」时查新名字。

载具改名（M10）：取消 / 空名 / 未改名一律静默 return，不误报「已存在」。

**列表选中恢复不许回写 state**（M11）
倍率列表选中恢复必须包 `_suppress_mag_writeback`，否则 setCurrentRow 会经
真身的 `_on_mag_user_selected` 回写 state——恢复动作被当成用户点击。

**.gsv 导入的失败路径**（S3a/S3b）
① 图片复制失败的 except 块曾引用未绑定的 `copied`——NameError 吞掉原始异常，
已复制的图片成孤儿留在 resources 里。
② manifest 的图片条目没有路径校验——含 `../` 的恶意 .gsv 可借导入把文件写到
resources 目录之外（任意文件写）。
"""
import json
import shutil
import zipfile

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QInputDialog, QMenu, QMessageBox

from core.vehicle_io import FORMAT_VERSION, import_vehicle

PLACEHOLDER = "双击绑定图片"


# ---------------------------------------------------------------- 夹具与工具

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


def _make_tab_wired(config, qapp):
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


def _make_vehicle_tab(config, qapp):
    from core.resource_manager import ResourceManager
    from core.state_machine import StateMachine
    from gui.tabs.vehicle_config_tab import VehicleConfigTab

    return VehicleConfigTab(config, StateMachine(config), ResourceManager())


def _mag_subs(tab):
    """倍率列表「画面上」显示的绑定文字（占位语说明该行显示为空）。"""
    return [
        tab.mag_list.itemWidget(tab.mag_list.item(i))._sub_text
        for i in range(tab.mag_list.count())
    ]


def _current_ammo(tab):
    item = tab.ammo_list.currentItem()
    return item.data(Qt.UserRole) if item else None


def _patch_mag_config(tab, monkeypatch):
    """让 _refresh_mag_list 走通：两条倍率，无绑定。"""
    monkeypatch.setattr(tab, "_get_selected_vehicle", lambda: "V1")
    monkeypatch.setattr(tab, "_get_selected_ammo", lambda: "AP")
    monkeypatch.setattr(tab.config, "get_magnifications", lambda v: [{"label": "1x"}, {"label": "2x"}])
    monkeypatch.setattr(tab.config, "get_crosshair_path", lambda *a: "")
    monkeypatch.setattr(tab.config, "get_magnification_overlay_mode", lambda *a: False)
    monkeypatch.setattr(tab.config, "get_overlay_vehicle_ui", lambda *a: False)
    monkeypatch.setattr(tab.config, "get_overlay_ammo_ui", lambda *a: False)


# ---------------------------------------------------------------- 弹种改名：数据层

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


# ---------------------------------------------------------------- 弹种改名：界面层

def test_rename_current_ammo_keeps_bindings_visible(vconfig, qapp, monkeypatch):
    """核心回归：重命名当前弹种后，倍率行不得退化成占位语，列表不得空选中。"""
    state, tab = _make_tab_wired(vconfig, qapp)
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
    state, tab = _make_tab_wired(vconfig, qapp)
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
    state, tab = _make_tab_wired(vconfig, qapp)
    warns = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))

    for answer in (("", False), ("   ", True), ("MG", True)):
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, _r=answer, **k: _r)
        tab._on_rename_ammo()

    assert warns == []
    assert set(vconfig.get_ammo_types("V1")) == {"MG", "SMK"}


# ---------------------------------------------------------------- 弹种右键菜单

def _open_ammo_menu(tab, monkeypatch, exec_impl):
    monkeypatch.setattr(QMenu, "exec_", exec_impl)
    monkeypatch.setattr(tab.ammo_list, "itemAt", lambda pos: tab.ammo_list.item(0))
    tab._on_ammo_list_context_menu(QPoint(1, 1))


def test_ammo_context_menu_offers_rename(vconfig, qapp, monkeypatch):
    """弹种右键菜单必须给到重命名（此前只有「清除弹种UI绑定」「删除弹种」）。"""
    _state, tab = _make_tab_wired(vconfig, qapp)
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
    _state, tab = _make_tab_wired(vconfig, qapp)

    def choose_rename(menu_self, *a, **k):
        for act in menu_self.actions():
            if act.text() == "重命名":
                return act
        return None

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("MG2", True))
    _open_ammo_menu(tab, monkeypatch, choose_rename)

    assert "MG2" in vconfig.get_ammo_types("V1")
    assert _mag_subs(tab) == ["mg0.png", "mg1.png", "mg2.png"]


# ---------------------------------------------------------------- 载具改名静默语义（M10）

def test_rename_cancel_silent(config, qapp, monkeypatch):
    """M10：对话框取消 → 静默 return，不弹警告、不动 state。"""
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


# ---------------------------------------------------------------- 倍率选中恢复不回写（M11）

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


# ---------------------------------------------------------------- .gsv 导入失败路径

def _make_gsv(path, images, files=None, name="T"):
    """构造一个 .gsv：manifest.json + images/ 下的文件。"""
    files = files or {}
    with zipfile.ZipFile(path, "w") as zf:
        manifest = {
            "format_version": FORMAT_VERSION,
            "vehicle": {"name": name},
            "images": images,
        }
        zf.writestr("manifest.json", json.dumps(manifest))
        for rel, content in files.items():
            zf.writestr(rel, content)


@pytest.mark.parametrize("bad_entry", [
    "../escape/x.png",       # 目录穿越
    "sub/../../x.png",       # 嵌套穿越
    "C:/Windows/evil.png",   # 绝对路径（pathlib 拼接会整体替换 base）
])
def test_import_rejects_path_traversal(config, tmp_path, bad_entry):
    """S3b：manifest 图片条目越出 resources → 拒绝且不在磁盘留痕。"""
    resources = tmp_path / "resources"
    resources.mkdir()
    gsv = tmp_path / "evil.gsv"
    _make_gsv(gsv, images=[bad_entry])

    ok, msg, _new_name = import_vehicle(config, resources, gsv)

    assert ok is False
    assert "非法" in msg
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "x.png").exists()
    assert config._config["vehicles"] == {}


def test_import_image_failure_reports_original_error(config, tmp_path, monkeypatch):
    """S3a：复制中途失败 → 报原始异常并清理已复制文件（不是 NameError）。"""
    import core.vehicle_io as vio

    resources = tmp_path / "resources"
    resources.mkdir()
    gsv = tmp_path / "flaky.gsv"
    _make_gsv(gsv, images=["sub/a.png", "sub/b.png"],
              files={"images/sub/a.png": "A", "images/sub/b.png": "B"})

    real_copy2 = shutil.copy2
    state = {"n": 0}

    def flaky(src, dst):
        state["n"] += 1
        if state["n"] > 1:
            raise OSError("disk full")
        return real_copy2(src, dst)

    monkeypatch.setattr(vio.shutil, "copy2", flaky)

    ok, msg, _new_name = import_vehicle(config, resources, gsv)

    assert ok is False
    assert "disk full" in msg  # 修复前这里抛 NameError: copied
    assert not (resources / "sub" / "a.png").exists()  # 孤儿被清理


def test_import_normal_flow_still_works(config, tmp_path):
    """对照：正常导入不受路径校验影响（防过度收紧）。"""
    resources = tmp_path / "resources"
    resources.mkdir()
    gsv = tmp_path / "ok.gsv"
    _make_gsv(gsv, images=["sub/a.png"], files={"images/sub/a.png": "A"})

    ok, _msg, new_name = import_vehicle(config, resources, gsv)

    assert ok is True
    assert (resources / "sub" / "a.png").exists()
    assert new_name in config._config["vehicles"]
