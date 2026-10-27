"""放大镜「屏息」与倍率/半径步长的交互契约。

回归 2026-10-27 报出的两个问题：
1. 屏息中按倍率步长，加成被静默覆盖（旋钮 1.0 + 屏息 3.0，按放大 0.5 反而掉回 1.5）
2. 屏息半径步长不能设为 0
3. 旋钮已在下限时按缩小，画面完全不动（热键像失灵）

不变量：屏幕上看到的是「旋钮 + 屏息加成」；松开屏息只撤加成，旋钮保持被调过的值。
"""
import pytest

from core.magnifier import RADIUS_MIN, ZOOM_MIN, MagnifierOverlay


@pytest.fixture
def overlay(qapp):
    o = MagnifierOverlay()
    yield o
    o.close()


# ---------- 倍率 ----------

def test_zoom_step_during_breath_keeps_boost(overlay):
    """屏息中放大：作用在当前画面值上，松开只撤加成。"""
    overlay.set_zoom(1.0)
    overlay.toggle_breath_hold(20, 3.0)
    assert overlay.zoom() == pytest.approx(4.0)

    base = overlay.adjust_zoom(0.5)
    assert overlay.zoom() == pytest.approx(4.5)   # 不是掉回 1.5
    assert base == pytest.approx(1.5)             # 旋钮同步调整

    overlay.toggle_breath_hold(20, 3.0)
    assert overlay.zoom() == pytest.approx(1.5)   # 只减 3.0，调过的 0.5 留着


def test_multiple_steps_during_breath_accumulate_on_knob(overlay):
    overlay.set_zoom(1.0)
    overlay.toggle_breath_hold(0, 3.0)
    overlay.adjust_zoom(0.5)
    overlay.adjust_zoom(0.5)
    assert overlay.zoom() == pytest.approx(5.0)

    overlay.toggle_breath_hold(0, 3.0)
    assert overlay.zoom() == pytest.approx(2.0)


def test_zoom_out_at_knob_floor_eats_breath(overlay):
    """旋钮已在 1.0：差额转记到屏息加成上，画面必须动，旋钮不被推过下限。"""
    overlay.set_zoom(ZOOM_MIN)
    overlay.toggle_breath_hold(0, 3.0)
    assert overlay.zoom() == pytest.approx(4.0)

    overlay.adjust_zoom(-0.5)
    assert overlay.zoom() == pytest.approx(3.5)        # 不是停在 4.0
    assert overlay._zoom == pytest.approx(ZOOM_MIN)    # 旋钮仍是下限

    overlay.toggle_breath_hold(0, 3.0)
    assert overlay.zoom() == pytest.approx(ZOOM_MIN)   # 松开落回旋钮


def test_adjust_without_breath_does_not_create_boost(overlay):
    """没按屏息时，到限的差额没有去处，直接丢弃。"""
    overlay.set_zoom(ZOOM_MIN)
    overlay.adjust_zoom(-0.5)
    assert overlay.zoom() == pytest.approx(ZOOM_MIN)
    assert overlay._breath_zoom == 0.0


def test_set_zoom_during_breath_moves_knob_only(overlay):
    """set_zoom 设的是旋钮，屏息加成照旧叠加。"""
    overlay.set_zoom(1.0)
    overlay.toggle_breath_hold(0, 3.0)
    overlay.set_zoom(2.0)
    assert overlay.zoom() == pytest.approx(5.0)

    overlay.toggle_breath_hold(0, 3.0)
    assert overlay.zoom() == pytest.approx(2.0)


# ---------- 半径 ----------

def test_radius_change_during_breath_is_kept(overlay):
    """屏息中改半径（滑块的语义），松开只撤加成，不退回快照。"""
    overlay.set_radius(200)
    overlay.toggle_breath_hold(20, 0.0)
    assert overlay.radius() == 220

    overlay.set_radius(300)
    assert overlay.radius() == 320

    overlay.toggle_breath_hold(20, 0.0)
    assert overlay.radius() == 300


def test_radius_never_below_floor(overlay):
    overlay.set_radius(RADIUS_MIN - 50)
    assert overlay.radius() == RADIUS_MIN


# ---------- 步长为 0 ----------

def test_breath_step_zero_is_allowed_noop(overlay):
    overlay.set_radius(200)
    overlay.set_zoom(2.0)
    overlay.toggle_breath_hold(0, 0.0)
    assert overlay.radius() == 200
    assert overlay.zoom() == pytest.approx(2.0)
    overlay.toggle_breath_hold(0, 0.0)
    assert overlay.radius() == 200


def test_breath_step_spinbox_accepts_zero(config, qapp):
    """界面控件必须允许 0（旧实现下界写死成 1）。"""
    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine
    from gui.tabs.magnifier_tab import MagnifierTab

    tab = MagnifierTab(config, HotkeyManager(config, StateMachine(config)))
    try:
        assert tab.breath_step_spin.minimum() == 0
        tab.breath_step_spin.setValue(0)
        assert config.get_magnifier_breath_step() == 0
    finally:
        tab.cleanup()
