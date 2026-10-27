"""core/angle_meter.py + gui/tabs/angle_meter_tab.py：角度换算与状态更新时机。

**灵敏度换算（唯一依据）**
    "每格转多少度" ∝ 游戏内灵敏度，**与鼠标 DPI 无关**
    （DPI 只决定手移动 1cm 产生多少格；游戏收到的是格数，看不到 DPI）

历史 bug：`ratio = (校准DPI/当前DPI) * (当前灵敏度/校准灵敏度)` 乘在格轴上，两处错：
① 不该有 DPI 项（换 DPI 曲线不该动）；② 灵敏度项**方向反了**。症状：调高游戏
灵敏度后角度仪读数严重偏小、越调越偏。修复前的具体读数是"灵敏度 1→2 后读
500 格显示 -60°、读 1000 格显示 -40°"（正确是 0° 和 +80°）。

灵敏度缺失（0 / 未填）时**不换算**，保持原始校准——宁可给一条"没换算的"曲线，
也不给一条被 0 除坏掉的。

**current_angle 只在 IDLE 更新**
赋值语句曾在 IDLE 判断之外——测量中（ACTIVE）调用会把 current_angle 拽回最小值，
正在进行的角度测量直接作废（文档写的"IDLE 状态时"才是契约）。

**射表 profile 按 table 引用缓存**
`query_firing_distance` 挂在 angle_changed（鼠标移动级），每次重建要做解析 + 排序
+ PCHIP 求导——同 table 引用（is）期间必须复用缓存。

**_loading 必须复位**
`_load_profile_params` 中途异常时若不复位，`_loading` 永久 True，此后所有参数修改
被静默丢弃。
"""
import pytest

from core.angle_meter import AngleCalibration, AngleTracker, RawInputReader

# 校准样本：灵敏度 1.0 时，0 格 = -80°，2000 格 = +80°（每格 0.08°）
RAW_POINTS = [[0, -80.0], [2000, 80.0]]


def _setup(config, sens_at_cal):
    """建一条"校准在 sens_at_cal 灵敏度下做的"曲线，返回配置名。"""
    config.set_angle_meter_sens(sens_at_cal)
    config.set_angle_meter_profile("P", {})
    config.set_current_angle_meter_profile("P")
    config.set_angle_meter_calibration_points("P", RAW_POINTS, 2)
    return "P"


def _make_angle_meter_tab(config, qapp):
    from core.hotkey_manager import HotkeyManager
    from core.state_machine import StateMachine
    from gui.tabs.angle_meter_tab import AngleMeterTab

    return AngleMeterTab(config, HotkeyManager(config, StateMachine(config)))


# ---------------------------------------------------------------- 灵敏度换算

@pytest.mark.parametrize("sens_at_cal, sens_now, expected_count", [
    (1.0, 1.0, 2000),   # 没变 → 不缩放
    (1.0, 2.0, 1000),   # 灵敏度 ×2 → 每格转角 ×2 → 同一角度只需一半的格（曲线左压）
    (2.0, 1.0, 4000),   # 灵敏度 ÷2 → 同一角度需要两倍的格（曲线右展）
])
def test_sens_scales_count_axis(config, sens_at_cal, sens_now, expected_count):
    """换算律：格轴 × (校准灵敏度 / 当前灵敏度)，正反两向一起验。"""
    name = _setup(config, sens_at_cal)
    config.set_angle_meter_sens(sens_now)
    assert config.get_effective_angle_meter_calibration(name) == [
        [0, -80.0], [expected_count, 80.0]]


def test_readout_matches_physics(config):
    """端到端：灵敏度 1→2 后，读 500 格应显示 0°、读 1000 格应显示 +80°。

    修复前这两个读数是 -60° 和 -40°（曲线反向缩放所致）——所以这个测试**有牙**：
    把 `ratio = cal_sens / cur_sens` 改成反过来，它会失败。
    """
    name = _setup(config, 1.0)
    config.set_angle_meter_sens(2.0)
    cal = AngleCalibration(config.get_effective_angle_meter_calibration(name))

    assert round(cal.delta_to_angle(500), 6) == 0.0
    assert round(cal.delta_to_angle(1000), 6) == 80.0
    assert round(cal.delta_to_angle(0), 6) == -80.0


def test_missing_sens_keeps_raw_calibration(config):
    """灵敏度缺失（0 / 未填）时**不换算**，保持原始校准——绝不按 0 缩放。

    这是刻意的保守行为：宁可给一条"没换算的"曲线，也不给一条被 0 除坏掉的。
    """
    name = _setup(config, 0)
    config.set_angle_meter_sens(2.0)
    assert config.get_effective_angle_meter_calibration(name) == RAW_POINTS


def test_sens_change_requests_save(config):
    """灵敏度现在是唯一的换算参数，改动必须触发落盘请求。

    历史 bug：`set_angle_meter_sens` 漏了 `request_save()`——不报错，只是重启后
    换算基准丢失、曲线悄悄变样。落盘是防抖的、没法断言文件内容，
    所以这里退一步断言"落盘被请求了"（这是唯一能锁住这个静默失败的办法）。
    """
    from unittest import mock

    with mock.patch.object(config, "request_save") as spy:
        config.set_angle_meter_sens(1.75)

    spy.assert_called_once()
    assert config.get_angle_meter_sens() == 1.75


# ---------------------------------------------------------------- 状态更新时机

def test_refresh_min_max_updates_only_in_idle(qapp):
    """refresh_min_max 只在 IDLE 状态更新 current_angle。"""
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


# ---------------------------------------------------------------- 射表 profile 缓存

def test_firing_profile_cached_by_table_identity(config, monkeypatch):
    """同 name 重复查询只构建一次 profile；table 换对象才重建。"""
    import core.config.angle_meter as am_mod

    calls = []
    real_from_config = am_mod.BallisticProfile.from_config.__func__

    def counting(cls, data):
        calls.append(data)
        return real_from_config(cls, data)

    monkeypatch.setattr(am_mod.BallisticProfile, "from_config", classmethod(counting))

    name = "p1"
    config.add_angle_meter_profile(name)
    config.set_firing_table(name, [{"angle": 0, "distance": 100}, {"angle": 5, "distance": 200}])

    for _ in range(50):
        assert config.query_firing_distance(name, 2.5) is not None
    assert len(calls) == 1, "同 table 引用的 50 次查询只应构建 1 次 profile"

    # set_firing_table 换 list 对象 → 引用失效，重建一次
    config.set_firing_table(name, [{"angle": 0, "distance": 100}, {"angle": 5, "distance": 200}])
    assert config.query_firing_distance(name, 2.5) is not None
    assert len(calls) == 2

    # 之后同对象查询不再重建
    assert config.query_firing_distance(name, 1.0) is not None
    assert len(calls) == 2


# ---------------------------------------------------------------- _loading 复位

def test_loading_flag_resets_on_param_load_failure(config, qapp, monkeypatch):
    """`_load_profile_params` 中途异常，`_loading` 复位，参数通道不永久静默。"""
    tab = _make_angle_meter_tab(config, qapp)

    def _boom(name):
        raise RuntimeError("模拟射表解析失败")

    monkeypatch.setattr(tab, "_load_firing_table", _boom)
    with pytest.raises(RuntimeError):
        tab._load_profile_params("p1")
    assert tab._loading is False, "_loading 永久 True——此后参数修改全被静默丢弃"

    # 复位生效：参数变更不再被 _on_profile_param_changed 提前吞掉
    tab.config.add_angle_meter_profile("p1")
    tab.config.set_current_angle_meter_profile("p1")
    seen = []
    monkeypatch.setattr(tab, "_apply_current_profile_to_tracker", lambda: seen.append(1))
    tab._on_profile_param_changed()
    assert seen == [1]
