"""契约：关闭路径与启用/禁用循环（S5 / S7 接线回归）。

- closeEvent 是清理契约的收口：任何一项清理抛异常都只记日志、不中断后续，
  所以"没崩"不等于"干净"——本测试要求**连日志级异常都没有**，
  守的正是"新增清理项接错线"这类静默回归（S7 的 Overlay 信号断开就在此列）。
- 角度仪启用/禁用循环：up/down 微调 tuner 每次启用都会重建，shutdown 必须
  真正断开旧 tuner 的信号——不断则旧 tuner 泄漏、重建后新旧双调（注入翻倍）。
  用"断开探针"锁定：旧 tuner 的槽在 shutdown 后必须处于未连接状态。
"""
import pytest
from PyQt5.QtGui import QCloseEvent

ADVANCED = ("set_magnifier_enabled", "set_angle_meter_enabled",
            "set_distance_meter_enabled", "set_squad_macro_enabled")


def _enable_all(config):
    for setter in ADVANCED:
        getattr(config, setter)(True)


def test_close_event_runs_full_shutdown(window, config, monkeypatch):
    """closeEvent 全套清理零异常（含 Overlay 信号断开这项新接线）。"""
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
