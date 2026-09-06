"""AngleCalibration 校准曲线算法测试"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.angle_meter import AngleCalibration


@pytest.fixture
def linear_cal():
    """线性校准曲线：0增量=-80度，914增量=80度"""
    points = [(0, -80.0), (153, -53.3), (305, -26.7), (457, 0.0),
              (609, 26.7), (762, 53.3), (914, 80.0)]
    return AngleCalibration(points)


class TestAngleCalibrationBasic:
    def test_point_count(self, linear_cal):
        assert linear_cal.point_count == 7

    def test_min_max_delta(self, linear_cal):
        assert linear_cal.min_delta == 0
        assert linear_cal.max_delta == 914

    def test_min_max_angle(self, linear_cal):
        assert linear_cal.min_angle == -80.0
        assert linear_cal.max_angle == 80.0

    def test_endpoints_delta_to_angle(self, linear_cal):
        assert linear_cal.delta_to_angle(0) == -80.0
        assert linear_cal.delta_to_angle(914) == 80.0

    def test_midpoint_delta_to_angle(self, linear_cal):
        assert abs(linear_cal.delta_to_angle(457) - 0.0) < 0.01

    def test_endpoints_angle_to_delta(self, linear_cal):
        assert linear_cal.angle_to_delta(-80.0) == 0
        assert abs(linear_cal.angle_to_delta(80.0) - 914) < 1

    def test_midpoint_angle_to_delta(self, linear_cal):
        assert abs(linear_cal.angle_to_delta(0.0) - 457) < 1


class TestAngleCalibrationInterpolation:
    def test_linear_segment_interpolation(self):
        """两点之间线性插值"""
        cal = AngleCalibration([(0, 0.0), (100, 10.0)])
        assert abs(cal.delta_to_angle(50) - 5.0) < 0.01

    def test_angle_to_delta_reverse_interpolation(self):
        cal = AngleCalibration([(0, 0.0), (100, 10.0)])
        assert abs(cal.angle_to_delta(5.0) - 50) < 0.01

    def test_clamp_below_min(self, linear_cal):
        """低于最小增量时钳制到最小角度"""
        assert linear_cal.delta_to_angle(-100) == -80.0

    def test_clamp_above_max(self, linear_cal):
        """高于最大增量时钳制到最大角度"""
        assert linear_cal.delta_to_angle(1000) == 80.0


class TestAngleCalibrationSerialization:
    def test_to_list_roundtrip(self, linear_cal):
        lst = linear_cal.to_list()
        assert len(lst) == 7
        restored = AngleCalibration.from_list(lst)
        assert restored.point_count == 7
        assert restored.min_delta == linear_cal.min_delta
        assert restored.max_delta == linear_cal.max_delta

    def test_from_list_empty_returns_none(self):
        assert AngleCalibration.from_list([]) is None

    def test_from_list_none_returns_none(self):
        assert AngleCalibration.from_list(None) is None


class TestAngleCalibrationEdgeCases:
    def test_single_point_raises(self):
        with pytest.raises(ValueError):
            AngleCalibration([(100, 50.0)])

    def test_none_points_raises(self):
        with pytest.raises(ValueError):
            AngleCalibration(None)

    def test_two_points(self):
        cal = AngleCalibration([(0, -20.0), (500, 30.0)])
        assert cal.point_count == 2
        assert abs(cal.delta_to_angle(250) - 5.0) < 0.01
