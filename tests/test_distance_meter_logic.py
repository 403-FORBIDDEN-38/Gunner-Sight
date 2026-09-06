"""距离测算逻辑单元测试（适配ConfigManager）"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.distance_meter import DistanceMeter, DistanceState, pixel_distance
from core.config_manager import ConfigManager

# mock get_cursor_pos
_mock_pos = [0, 0]
def _mock_get_cursor_pos():
    return tuple(_mock_pos)

import core.distance_meter as dm
dm.get_cursor_pos = _mock_get_cursor_pos


def _make_meter(td, flow_active=True):
    """创建测试用DistanceMeter（ConfigManager用临时目录）。flow_active=True默认启用流程。"""
    config = ConfigManager(config_dir=os.path.join(td, "config"))
    meter = DistanceMeter(config)
    if flow_active:
        meter.set_flow_active(True)
    return meter


def test_pixel_distance():
    assert pixel_distance((0, 0), (3, 4)) == 5.0
    assert pixel_distance((10, 10), (10, 10)) == 0.0
    print("PASS: pixel_distance")


def test_state_machine():
    """两层状态：模块开启（config.enabled）与流程启用（_flow_active）分离"""
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td, flow_active=False)
        assert meter.state == DistanceState.DISABLED
        assert not meter.is_flow_active()
        assert not meter.calibrated
        print("PASS: 初始待机状态DISABLED")
        # 启用流程
        meter.set_flow_active(True)
        assert meter.is_flow_active()
        assert meter.state == DistanceState.ENABLED_UNCALIBRATED
        print("PASS: 流程启用后ENABLED_UNCALIBRATED")
        # 待机
        meter.set_flow_active(False)
        assert not meter.is_flow_active()
        assert meter.state == DistanceState.DISABLED
        print("PASS: 待机后DISABLED")
        # toggle()切换
        meter.toggle()
        assert meter.is_flow_active()
        assert meter.state == DistanceState.ENABLED_UNCALIBRATED
        print("PASS: toggle()启用流程")


def test_calibration():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        assert meter.state == DistanceState.CALIBRATING_WAIT_B
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        assert meter.state == DistanceState.CALIBRATED
        assert meter.calibrated
        print("PASS: 标定完成")


def test_measurement():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.measure_point()
        assert meter.state == DistanceState.MEASURING_WAIT_D
        _mock_pos[0], _mock_pos[1] = 150, 0
        meter.measure_point()
        assert meter.state == DistanceState.CALIBRATED
        assert abs(meter.last_result - 150.0) < 0.1
        print("PASS: 测距完成")


def test_disabled_no_response():
    """待机（_flow_active=False）时记录/测算不响应"""
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td, flow_active=False)
        assert meter.record_point() is None
        assert meter.measure_point() is None
        print("PASS: 待机时无响应")


def test_uncalibrated_no_measure():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        result = meter.measure_point()
        assert result == "uncalibrated"
        print("PASS: 未标定不能测距")


def test_multiple_measurements():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        # 第一次测距
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.measure_point()
        _mock_pos[0], _mock_pos[1] = 100, 0
        meter.measure_point()
        assert abs(meter.last_result - 100.0) < 0.1
        # 第二次测距（自动重启）
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.measure_point()
        _mock_pos[0], _mock_pos[1] = 200, 0
        meter.measure_point()
        assert abs(meter.last_result - 200.0) < 0.1
        print("PASS: 多次测距")


def test_recalibration():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        assert meter.calibrated
        # 重新标定
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        assert meter.state == DistanceState.CALIBRATING_WAIT_B
        assert not meter.calibrated
        print("PASS: 重新标定清除旧数据")


def test_scale_change_resets():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        assert meter.calibrated
        meter.set_scale_meters(500)
        assert not meter.calibrated
        assert meter.state == DistanceState.ENABLED_UNCALIBRATED
        print("PASS: 比例尺变化重置标定")


def test_config_persistence():
    with tempfile.TemporaryDirectory() as td:
        config = ConfigManager(config_dir=os.path.join(td, "config"))
        meter = DistanceMeter(config)
        meter.set_scale_meters(500)
        config.set_distance_meter_hotkey("toggle", "F1")
        config.set_distance_meter_overlay_offset(200, 300)
        config.save_config()  # 强制写入（request_save有500ms防抖）
        # 重新加载
        config2 = ConfigManager(config_dir=os.path.join(td, "config"))
        assert config2.get_distance_meter_scale() == 500
        assert config2.get_distance_meter_hotkeys()["toggle"]["key1"] == "F1"
        assert config2.get_distance_meter_overlay_offset() == (200, 300)
        print("PASS: 配置持久化")


def test_default_overlay_position():
    with tempfile.TemporaryDirectory() as td:
        config = ConfigManager(config_dir=os.path.join(td, "config"))
        assert config.get_distance_meter_overlay_offset() == (100, 100)
        print("PASS: 默认悬浮位置(100,100)")


def test_get_status_text():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td, flow_active=False)
        assert "待机" in meter.get_status_text()
        meter.set_flow_active(True)
        assert "未标定" in meter.get_status_text()
        print("PASS: 状态文本")


def test_calibration_slope_correction():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        # 横向标定：点A(0,0)，点B(300,10)——手抖y偏移10px
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 10
        meter.record_point()
        assert meter.calibrated
        assert meter.calibration_direction == "横向"
        cal = meter._cfg.get_distance_meter_calibration()
        assert abs(cal["calibrated_pixels"] - 300) < 0.01
        print("PASS: 横向标定取dx忽略y偏移")
        # 竖向标定
        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 10, 400
        meter.record_point()
        assert meter.calibration_direction == "竖向"
        cal = meter._cfg.get_distance_meter_calibration()
        assert abs(cal["calibrated_pixels"] - 400) < 0.01
        print("PASS: 竖向标定取dy忽略x偏移")


def test_calibration_measurement_independent():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        # 标定
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        # 测距途中按记录键不打断
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.measure_point()
        result = meter.record_point()
        assert result == "interrupted"
        assert meter.state == DistanceState.MEASURING_WAIT_D
        print("PASS: 标定测距独立")


def test_multiple_calibration_measurement():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        # 多次标定
        for i in range(3):
            _mock_pos[0], _mock_pos[1] = 0, 0
            meter.record_point()
            _mock_pos[0], _mock_pos[1] = 300, 0
            meter.record_point()
            assert meter.calibrated
        print("PASS: 多次标定测距")


def test_interrupt_hints():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        # 标定途中按测算键
        result = meter.measure_point()
        assert result == "interrupted"
        print("PASS: 防打断提示")


def test_calibrating_scale_change():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        assert meter.state == DistanceState.CALIBRATING_WAIT_B
        meter.set_scale_meters(500)
        assert meter.state == DistanceState.ENABLED_UNCALIBRATED
        assert not meter.calibrated
        print("PASS: 标定途中改比例尺")


def test_cycle_scale():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        meter.cycle_scale(1)
        assert meter.scale_meters == 100
        meter.cycle_scale(1)
        assert meter.scale_meters == 33
        print("PASS: 循环切换比例尺")


def test_status_colors():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td, flow_active=False)
        assert meter.get_status_color() == "#888888"  # 待机
        meter.set_flow_active(True)
        assert meter.get_status_color() == "#ff4444"  # 未标定
        print("PASS: 状态颜色")


def test_quick_measure():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        # 正常测距
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.measure_point()
        _mock_pos[0], _mock_pos[1] = 100, 0
        meter.measure_point()
        # quick_measure沿用上一次点1
        _mock_pos[0], _mock_pos[1] = 200, 0
        result = meter.quick_measure()
        assert result == "quick_measured"
        assert abs(meter.last_result - 200.0) < 0.1
        print("PASS: shift+测距沿用上一次点1")


def test_quick_measure_no_history():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        result = meter.quick_measure()
        assert result == "no_history"
        print("PASS: 无测距历史时quick_measure提示")


def test_quick_measure_interrupts_while_measuring():
    """BUG-11: quick_measure在MEASURING_WAIT_D状态下应提示不覆盖"""
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)
        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        # 进入测距中状态（只按一次measure_point，等待点2）
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.measure_point()
        assert meter.state == DistanceState.MEASURING_WAIT_D
        # quick_measure应被拦截
        result = meter.quick_measure()
        assert result == "interrupted"
        assert meter.state == DistanceState.MEASURING_WAIT_D
        print("PASS: 测距中quick_measure被拦截不覆盖")


def test_clear_calibration_resets_state():
    """BUG-10: clear_distance_meter_calibration清理标定数据"""
    with tempfile.TemporaryDirectory() as td:
        config = ConfigManager(config_dir=os.path.join(td, "config"))
        meter = DistanceMeter(config)
        meter.set_flow_active(True)
        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        assert meter.calibrated
        cal = config.get_distance_meter_calibration()
        assert cal["pixels_per_meter"] > 0
        # 清理标定数据
        config.clear_distance_meter_calibration()
        cal = config.get_distance_meter_calibration()
        assert cal["pixels_per_meter"] == 0
        assert cal["calibrated_pixels"] == 0
        print("PASS: 清理标定数据后恢复默认空值")


def test_scale_change_clears_history():
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)

        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.measure_point()
        _mock_pos[0], _mock_pos[1] = 100, 0
        meter.measure_point()
        assert meter.last_measure_point_1 is not None
        meter.set_scale_meters(500)
        assert meter.last_measure_point_1 is None
        print("PASS: 切换比例尺清空历史点1")


def test_standby_preserves_calibration():
    """待机（_flow_active=False）不清理标定数据，重新启用流程后标定仍在"""
    with tempfile.TemporaryDirectory() as td:
        meter = _make_meter(td)
        meter.set_scale_meters(300)
        _mock_pos[0], _mock_pos[1] = 0, 0
        meter.record_point()
        _mock_pos[0], _mock_pos[1] = 300, 0
        meter.record_point()
        assert meter.calibrated
        # 待机
        meter.set_flow_active(False)
        assert not meter.is_flow_active()
        # 标定数据保留
        cal = meter._cfg.get_distance_meter_calibration()
        assert cal["calibrated_pixels"] > 0
        assert cal["pixels_per_meter"] > 0
        # 重新启用流程，state应为CALIBRATED
        meter.set_flow_active(True)
        assert meter.state == DistanceState.CALIBRATED
        print("PASS: 待机保留标定数据，重新启用后CALIBRATED")


if __name__ == "__main__":
    tests = [
        test_pixel_distance, test_state_machine, test_calibration,
        test_measurement, test_disabled_no_response, test_uncalibrated_no_measure,
        test_multiple_measurements, test_recalibration, test_scale_change_resets,
        test_config_persistence, test_default_overlay_position, test_get_status_text,
        test_calibration_slope_correction, test_calibration_measurement_independent,
        test_multiple_calibration_measurement, test_interrupt_hints,
        test_calibrating_scale_change, test_cycle_scale, test_status_colors,
        test_quick_measure, test_quick_measure_no_history,
        test_quick_measure_interrupts_while_measuring, test_clear_calibration_resets_state,
        test_scale_change_clears_history, test_standby_preserves_calibration,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
    print(f"\n=== {passed}/{len(tests)} 项测试通过 ===")
