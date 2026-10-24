"""契约：OverlayRenderer.shutdown() 必须真正断开 StateMachine 信号（S7）。

历史 bug：OverlayRenderer 只连不断——没有任何断开路径。重复构造时新旧实例的
回调叠加（Qt 信号持引用，旧实例连同 overlay 窗口一起不释放），关窗/退出后
旧回调仍在响应状态变化。
"""
from core.overlay import OverlayRenderer
from core.state_machine import StateMachine


def test_shutdown_disconnects_state_signals(config, qapp):
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
