"""回归：滚轮预选列表期间，弹种热键命令必须结束预选（回到常显）。

历史问题：热键选中的**就是当前弹种**时，`StateMachine.set_ammo_type` 因值未变化
直接 return（细粒度信号约定，避免冗余刷新），滚轮模块收不到任何信号，预选列表
一直挂到 2s 超时。表现："用热键选择已选中的弹种失败，必须选别的弹种 / 等超时 /
左键确定才能回到当前列表"。修法与左键确定（`_on_mouse_down`）对齐：
目标等于当前弹种时也要结束预选。

这里复刻 `main.py` 的接线顺序（先 `state.set_ammo_type`，后 `selector.on_ammo_hotkey`），
因为"弹种没变就不发信号"正是要靠这个顺序才能暴露出来。
"""
import pytest
from PyQt5.QtCore import QObject, pyqtSignal

VEHICLE = "测试载具"
AMMOS = ["AP", "HE", "SMOKE"]


class _HotkeyStub(QObject):
    """最小复刻 HotkeyManager 的弹种热键信号，用于验证真实接线顺序。"""

    ammo_switch_triggered = pyqtSignal(str)


@pytest.fixture
def scene(config, qapp):
    from core.ammo_wheel_selector import AmmoWheelSelector
    from core.state_machine import StateMachine

    config.add_vehicle(VEHICLE)
    for ammo in AMMOS:
        config.add_ammo_type(VEHICLE, ammo)
    config._set_current_vehicle(VEHICLE)
    config._set_current_ammo_type(AMMOS[0])  # 当前弹种 = AP

    state = StateMachine(config)
    selector = AmmoWheelSelector(state, config)

    hotkey = _HotkeyStub()
    hotkey.ammo_switch_triggered.connect(state.set_ammo_type)
    hotkey.ammo_switch_triggered.connect(selector.on_ammo_hotkey)

    yield state, selector, hotkey
    selector.stop()


def _open_preview(selector):
    """滚轮打开预选列表，并滚到当前弹种以外的位置（高亮 AP → HE）。"""
    selector._on_wheel(-1)
    assert selector._active is True, "滚轮没有打开预选列表"
    assert selector._preview_index == 1, "滚轮没有移动高亮"


@pytest.mark.parametrize("ammo_idx, label", [
    (0, "已选中的弹种（曾是失败的场景）"),
    (2, "其它弹种"),
])
def test_hotkey_resolves_preview(scene, ammo_idx, label):
    """核心回归：预选列表打开时，热键选任何弹种都必须立即结束预选。"""
    state, selector, hotkey = scene
    _open_preview(selector)

    hotkey.ammo_switch_triggered.emit(AMMOS[ammo_idx])

    assert state.current_ammo_type == AMMOS[ammo_idx], label
    assert selector._active is False, "热键选择后，预选列表仍未结束"
    assert selector._preview_index == -1
    assert selector._timeout_timer.isActive() is False


def test_hotkey_without_preview_only_changes_state(scene):
    """没有预选列表时，热键只改状态，不应触发预选收尾逻辑。"""
    state, selector, hotkey = scene
    assert selector._active is False

    hotkey.ammo_switch_triggered.emit(AMMOS[1])

    assert state.current_ammo_type == AMMOS[1]
    assert selector._active is False
