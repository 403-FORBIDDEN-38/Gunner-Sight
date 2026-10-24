"""契约：refresh_min_max 只在 IDLE 状态更新 current_angle（M1）。

历史 bug：赋值语句在 IDLE 判断之外——测量中（ACTIVE）调用会把 current_angle
拽回最小值，正在进行的角度测量直接作废（文档写的"IDLE 状态时"才是契约）。
"""

from core.angle_meter import AngleTracker, RawInputReader


def test_refresh_min_max_updates_only_in_idle(qapp):
    raw = RawInputReader()
    tracker = AngleTracker(raw)
    tracker.set_min_max_provider(lambda: (-80.0, 80.0))

    # IDLE：刷新到 min
    assert tracker.state == tracker.STATE_IDLE
    tracker.refresh_min_max()
    assert tracker.current_angle == -80.0

    # ACTIVE（测量中）：不得改写 current_angle
    tracker._set_state(tracker.STATE_ACTIVE)
    tracker.current_angle = 42.0
    tracker.refresh_min_max()
    assert tracker.current_angle == 42.0
