from core.logger import logger

"""距离测算模块 - 逻辑层
基于地图比例尺标定，测量任意两点间游戏内距离。
状态机: DISABLED -> ENABLED_UNCALIBRATED -> CALIBRATING_WAIT_B -> CALIBRATED -> MEASURING_WAIT_D
并入GS主程序，配置通过ConfigManager管理。
"""
import ctypes
from ctypes import wintypes
from enum import Enum

from core.win32_utils import user32


class DistanceState(Enum):
    DISABLED = "disabled"
    ENABLED_UNCALIBRATED = "enabled_uncalibrated"
    CALIBRATING_WAIT_B = "calibrating_wait_b"
    CALIBRATED = "calibrated"
    MEASURING_WAIT_D = "measuring_wait_d"


# 比例尺预设列表（组合键+记录键循环切换，小到大：33→100→300→900→33）
SCALE_PRESETS = [33, 100, 300, 900]

from core.colors import (DISTANCE_DISABLED, DISTANCE_UNCALIBRATED, DISTANCE_CALIBRATING,
                         DISTANCE_CALIBRATED, DISTANCE_MEASURING, OVERLAY_TEXT)

# 状态颜色映射（悬浮窗口文本颜色）
STATUS_COLORS = {
    DistanceState.DISABLED: DISTANCE_DISABLED,
    DistanceState.ENABLED_UNCALIBRATED: DISTANCE_UNCALIBRATED,
    DistanceState.CALIBRATING_WAIT_B: DISTANCE_CALIBRATING,
    DistanceState.CALIBRATED: DISTANCE_CALIBRATED,
    DistanceState.MEASURING_WAIT_D: DISTANCE_MEASURING,
}


def get_cursor_pos() -> tuple[int, int]:
    """获取鼠标当前屏幕坐标。必须用 wintypes.POINT，与 win32_utils 里 GetCursorPos 的 argtypes 一致，
    否则 Nuitka 下类型不匹配会原生崩溃。"""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def pixel_distance(p1: tuple[int, int], p2: tuple[int, int]) -> float:
    """两点间像素距离（欧几里得）"""
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


class DistanceMeter:
    """距离测算逻辑层

    配置通过ConfigManager管理（distance_meter段）。
    空房子原则：默认禁用，无默认热键，无标定数据。
    """

    def __init__(self, config):
        """config: ConfigManager实例"""
        self._cfg = config
        self._state = DistanceState.DISABLED
        self._calib_point_a: tuple[int, int] | None = None
        self._measure_point_c: tuple[int, int] | None = None
        self._last_measure_point_1: tuple[int, int] | None = None
        self._last_result: float | None = None
        self._status_callback = None
        self._flow_active = False  # 暂离中才激活

    # === 状态查询 ===
    @property
    def state(self) -> DistanceState:
        return self._state

    @property
    def enabled(self) -> bool:
        return self._cfg.is_distance_meter_enabled()

    @property
    def calibrated(self) -> bool:
        return self._cfg.get_distance_meter_calibration()["pixels_per_meter"] > 0

    @property
    def calibration_direction(self) -> str:
        return self._cfg.get_distance_meter_calibration()["calibration_direction"]

    # === 第二层状态：流程启用（热键控制，运行时状态，不存config）===
    def is_flow_active(self) -> bool:
        return self._flow_active

    def set_flow_active(self, active: bool):
        self._flow_active = active
        if active:
            # 进入暂离：清除上次测距数据，按标定状态设置
            self._measure_point_c = None
            self._calib_point_a = None
            if self.calibrated:
                self._state = DistanceState.CALIBRATED
            else:
                self._state = DistanceState.ENABLED_UNCALIBRATED
            self._notify("流程已启用")
        else:
            # 回到游戏：显示暂离，保留测距数据
            self._state = DistanceState.DISABLED
            self._notify("已待机")

    def get_status_text(self) -> str:
        """获取当前状态文本（供悬浮窗口显示，精简版：比例尺|流程|提示/距离）"""
        scale = self._cfg.get_distance_meter_scale()
        scale_str = f"{scale:.0f}m" if scale > 0 else "?"
        if self._state == DistanceState.DISABLED:
            return "待机 | 按启用热键开始"
        elif self._state == DistanceState.ENABLED_UNCALIBRATED:
            return f"{scale_str} | 未标定 | 请按标定热键标定第1点"
        elif self._state == DistanceState.CALIBRATING_WAIT_B:
            return f"{scale_str} | 标定中 | 请按标定热键标定第2点"
        elif self._state == DistanceState.CALIBRATED:
            if self._last_result is not None:
                return f"{scale_str} | 已标定 | 距离：{self._last_result:.1f}m"
            return f"{scale_str} | 已标定 | 请按测距热键测距第1点"
        elif self._state == DistanceState.MEASURING_WAIT_D:
            return f"{scale_str} | 测距中 | 请按测距热键测距第2点"
        return f"{scale_str} | 未知状态"

    def get_status_parts(self) -> dict:
        """获取结构化状态数据（供悬浮窗口分别设置颜色）。
        返回: {scale, state_word, state_color, hint, result, result_color}
        """
        scale = self._cfg.get_distance_meter_scale()
        # 待机状态（流程未启用）：记录/测算不响应
        if not self._flow_active:
            scale_str = f"{scale:.0f}m" if scale > 0 else "?"
            return {"scale": scale_str, "state_word": "待机", "state_color": DISTANCE_DISABLED,
                    "hint": "按启用热键开始", "result": None, "result_color": OVERLAY_TEXT}
        scale_str = f"{scale:.0f}m" if scale > 0 else "?"
        color = self.get_status_color()
        if self._state == DistanceState.DISABLED:
            return {"scale": scale_str, "state_word": "未启用", "state_color": color,
                    "hint": "请按启用热键", "result": None, "result_color": OVERLAY_TEXT}
        elif self._state == DistanceState.ENABLED_UNCALIBRATED:
            return {"scale": scale_str, "state_word": "未标定", "state_color": color,
                    "hint": "请按标定热键标定第1点", "result": None, "result_color": OVERLAY_TEXT}
        elif self._state == DistanceState.CALIBRATING_WAIT_B:
            return {"scale": scale_str, "state_word": "标定中", "state_color": color,
                    "hint": "请按标定热键标定第2点", "result": None, "result_color": OVERLAY_TEXT}
        elif self._state == DistanceState.CALIBRATED:
            if self._last_result is not None:
                return {"scale": scale_str, "state_word": "已标定", "state_color": color,
                        "hint": None, "result": f"距离：{self._last_result:.1f}m", "result_color": DISTANCE_CALIBRATED}
            return {"scale": scale_str, "state_word": "已标定", "state_color": color,
                    "hint": "请按测距热键测距第1点", "result": None, "result_color": OVERLAY_TEXT}
        elif self._state == DistanceState.MEASURING_WAIT_D:
            return {"scale": scale_str, "state_word": "测距中", "state_color": color,
                    "hint": "请按测距热键测距第2点", "result": None, "result_color": OVERLAY_TEXT}
        return {"scale": scale_str, "state_word": "未知", "state_color": color,
                "hint": "", "result": None, "result_color": OVERLAY_TEXT}

    @property
    def scale_meters(self) -> float:
        return self._cfg.get_distance_meter_scale()

    @property
    def pixels_per_meter(self) -> float:
        return self._cfg.get_distance_meter_calibration()["pixels_per_meter"]

    @property
    def last_result(self) -> float | None:
        return self._last_result

    @property
    def overlay_position(self) -> tuple[int, int]:
        return self._cfg.get_distance_meter_overlay_offset()

    def get_config(self) -> dict:
        return self._cfg.get_distance_meter_hotkeys()

    def set_status_callback(self, callback):
        """设置状态变化回调: fn(state: DistanceState, message: str)"""
        self._status_callback = callback

    def _notify(self, message: str):
        if self._status_callback:
            try:
                self._status_callback(self._state, message)
            except Exception as e:
                logger.info(f"[DistanceMeter] 状态回调异常: {e}")

    # === 配置设置 ===
    def set_scale_meters(self, meters: float):
        """设置比例尺数值（米）。比例尺变化后标定失效，重置状态机。"""
        if meters <= 0:
            return
        self._cfg.set_distance_meter_scale(float(meters))
        self._cfg.clear_distance_meter_calibration()
        self._calib_point_a = None
        self._measure_point_c = None
        self._last_measure_point_1 = None
        self._last_result = None
        if self._flow_active:
            self._state = DistanceState.ENABLED_UNCALIBRATED
        else:
            self._state = DistanceState.DISABLED
        self._notify("比例尺已更改，请重新标定")

    def cycle_scale(self, direction: int):
        """循环切换比例尺预设。
        direction: -1=下一个(小到大: 33→100→300→900→33), +1=上一个(大到小: 33→900→300→100→33)
        """
        current = self._cfg.get_distance_meter_scale()
        # 找到当前比例尺在预设列表中的索引
        try:
            idx = SCALE_PRESETS.index(current)
        except ValueError:
            idx = 0  # 不匹配默认第一个
        # direction=-1=小到大=index+1, direction=+1=大到小=index-1
        if direction == -1:
            idx = (idx + 1) % len(SCALE_PRESETS)
        else:
            idx = (idx - 1) % len(SCALE_PRESETS)
        new_scale = SCALE_PRESETS[idx]
        self.set_scale_meters(new_scale)

    def get_status_color(self) -> str:
        """获取当前状态对应的悬浮窗口文本颜色"""
        return STATUS_COLORS.get(self._state, OVERLAY_TEXT)

    def set_hotkey(self, name: str, key: str):
        """设置热键: toggle/record/measure/modifier"""
        self._cfg.set_distance_meter_hotkey(name, key)

    # 键名 -> 虚拟键码（用于全局组合键检测）
    _COMBO_VK_MAP = {
        "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
        "mouse_left": 0x01, "mouse_right": 0x02, "mouse_middle": 0x04,
        "mouse_xbutton1": 0x05, "mouse_xbutton2": 0x06,
    }


    def set_overlay_position(self, x: int, y: int):
        self._cfg.set_distance_meter_overlay_offset(int(x), int(y))

    # === 核心操作 ===
    def toggle(self) -> bool:
        """兼容接口：暂离控制在set_flow_active中处理"""
        return self._flow_active

    def record_point(self) -> str | None:
        """标定热键：第1次记比例尺点A，第2次记点B并完成标定。
        返回状态消息，待机或非标定状态返回None。
        """
        if not self._flow_active:
            self._notify("待机中，请先按启用热键")
            return None
        if self._state == DistanceState.DISABLED:
            return None

        pos = get_cursor_pos()

        if self._state in (DistanceState.ENABLED_UNCALIBRATED, DistanceState.CALIBRATED):
            # 第1次：记录点A，进入标定中
            # 多次标定：清除旧标定数据
            if self._state == DistanceState.CALIBRATED:
                self._cfg.clear_distance_meter_calibration()
                self._last_result = None
            self._calib_point_a = pos
            self._state = DistanceState.CALIBRATING_WAIT_B
            self._notify(f"标定中：点A已记录({pos[0]},{pos[1]})，请移到比例尺另一端按标定热键")
            return "calibrating"

        elif self._state == DistanceState.CALIBRATING_WAIT_B:
            # 第2次：记录点B，完成标定
            if self._calib_point_a is None:
                self._state = DistanceState.ENABLED_UNCALIBRATED
                self._notify("标定失败：点A丢失")
                return "failed"
            # 比例尺斜线修正：取主轴距离（横/竖中较大者），忽略手抖偏移
            dx = abs(pos[0] - self._calib_point_a[0])
            dy = abs(pos[1] - self._calib_point_a[1])
            if dx >= dy:
                px = dx
                direction = "横向"
            else:
                px = dy
                direction = "竖向"
            scale = self._cfg.get_distance_meter_scale()
            if px <= 0 or scale <= 0:
                self._state = DistanceState.ENABLED_UNCALIBRATED
                self._notify("标定失败：像素距离或比例尺无效")
                return "failed"
            ppm = px / scale
            self._cfg.set_distance_meter_calibration(px, ppm, direction)
            self._state = DistanceState.CALIBRATED
            self._calib_point_a = None
            self._notify(f"已标定（{direction}）：{px:.1f}像素 = {scale:.0f}m ({ppm:.2f}像素/m)")
            return "calibrated"

        # MEASURING_WAIT_D状态下按记录键：不打断测距，提示用户
        if self._state == DistanceState.MEASURING_WAIT_D:
            self._notify("测距中，请先完成测距")
            return "interrupted"

        return None

    def measure_point(self) -> str | None:
        """测距热键：第1次记目标点C，第2次记点D并显示测距结果。
        返回状态消息，待机或未标定返回None。
        """
        if not self._flow_active:
            self._notify("待机中，请先按启用热键")
            return None
        if self._state == DistanceState.DISABLED:
            return None
        # 标定途中按测算键：不打断标定，提示用户
        if self._state == DistanceState.CALIBRATING_WAIT_B:
            self._notify("标定中，请先完成标定")
            return "interrupted"
        if not self.calibrated:
            self._notify("未标定，请先完成比例尺标定")
            return "uncalibrated"

        pos = get_cursor_pos()

        if self._state in (DistanceState.CALIBRATED, DistanceState.ENABLED_UNCALIBRATED):
            # 第1次：记录点C
            self._measure_point_c = pos
            self._state = DistanceState.MEASURING_WAIT_D
            self._notify(f"测距中：点C已记录({pos[0]},{pos[1]})，请移到目标另一端按测距热键")
            return "measuring"

        elif self._state == DistanceState.MEASURING_WAIT_D:
            # 第2次：记录点D，计算距离
            if self._measure_point_c is None:
                self._state = DistanceState.CALIBRATED
                self._notify("测距失败：点C丢失")
                return "failed"
            px = pixel_distance(self._measure_point_c, pos)
            ppm = self._cfg.get_distance_meter_calibration()["pixels_per_meter"]
            if ppm <= 0:
                self._state = DistanceState.CALIBRATED
                self._notify("测距失败：标定数据无效")
                return "failed"
            distance = px / ppm
            self._last_result = distance
            self._last_measure_point_1 = self._measure_point_c  # 记录上一次测距点1
            self._measure_point_c = None
            self._state = DistanceState.CALIBRATED
            self._notify(f"距离：{distance:.1f}m (像素距离{px:.1f})")
            return "measured"

        return None

    def quick_measure(self) -> str | None:
        """组合键+测距键：沿用上一次测距点1，当前鼠标位置为点2，直接计算距离。
        不更新last_measure_point_1（支持连续环测）。
        返回状态消息，待机/未标定/无历史点1返回None或提示。
        """
        if not self._flow_active:
            self._notify("待机中，请先按启用热键")
            return None
        if self._state == DistanceState.DISABLED:
            return None
        # 标定途中不打断
        if self._state == DistanceState.CALIBRATING_WAIT_B:
            self._notify("标定中，请先完成标定")
            return "interrupted"
        # 测距途中不打断（与record_point保持一致）
        if self._state == DistanceState.MEASURING_WAIT_D:
            self._notify("测距中，请先完成测距")
            return "interrupted"
        if not self.calibrated:
            self._notify("未标定，请先完成比例尺标定")
            return "uncalibrated"
        if self._last_measure_point_1 is None:
            self._notify("请先完成一次正常测距")
            return "no_history"

        pos = get_cursor_pos()
        px = pixel_distance(self._last_measure_point_1, pos)
        ppm = self._cfg.get_distance_meter_calibration()["pixels_per_meter"]
        if ppm <= 0:
            self._notify("测距失败：标定数据无效")
            return "failed"
        distance = px / ppm
        self._last_result = distance
        # 不更新last_measure_point_1，保持环测
        self._state = DistanceState.CALIBRATED
        self._notify(f"距离：{distance:.1f}m (沿用上一次点1)")
        return "quick_measured"

    @property
    def last_measure_point_1(self) -> tuple[int, int] | None:
        return self._last_measure_point_1
