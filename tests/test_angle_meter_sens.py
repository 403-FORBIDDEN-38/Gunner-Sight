"""回归：角度仪按灵敏度换算格轴（"格" = Raw Input 原始计数 lLastY）。

物理关系（整个换算的唯一依据）：
    "每格转多少度" ∝ 游戏内灵敏度，**与鼠标 DPI 无关**
    （DPI 只决定手移动 1cm 产生多少格；游戏收到的是格数，看不到 DPI）

历史 bug：`ratio = (校准DPI/当前DPI) * (当前灵敏度/校准灵敏度)` 乘在格轴上，两处错：
① 不该有 DPI 项（换 DPI 曲线不该动）；② 灵敏度项**方向反了**。
症状：调高游戏灵敏度后角度仪读数严重偏小、越调越偏。修复前的具体读数是
"灵敏度 1→2 后读 500 格显示 -60°、读 1000 格显示 -40°"（正确是 0° 和 +80°）。
"""
import pytest

from core.angle_meter import AngleCalibration

# 校准样本：灵敏度 1.0 时，0 格 = -80°，2000 格 = +80°（每格 0.08°）
RAW_POINTS = [[0, -80.0], [2000, 80.0]]


def _setup(config, sens_at_cal):
    """建一条"校准在 sens_at_cal 灵敏度下做的"曲线，返回配置名。"""
    config.set_angle_meter_sens(sens_at_cal)
    config.set_angle_meter_profile("P", {})
    config.set_current_angle_meter_profile("P")
    config.set_angle_meter_calibration_points("P", RAW_POINTS, 2)
    return "P"


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

