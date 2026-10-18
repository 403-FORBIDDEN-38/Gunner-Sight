"""
角度仪核心模块 — 纯逻辑，无 UI 依赖。

校准模型：点列分段线性。每个校准点 (delta, angle)，
相邻点之间线性插值，端点外钳定。
"""
import ctypes
import ctypes.wintypes

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget

from core.win32_utils import user32


# ============================================================
# Raw Input ctypes 结构
# ============================================================
class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", ctypes.wintypes.USHORT),
        ("usUsage", ctypes.wintypes.USHORT),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("hwndTarget", ctypes.wintypes.HWND),
    ]

class _RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", ctypes.wintypes.DWORD), ("dwSize", ctypes.wintypes.DWORD),
                ("hDevice", ctypes.c_void_p), ("wParam", ctypes.wintypes.WPARAM)]

class _RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", ctypes.wintypes.USHORT), ("ulButtons", ctypes.wintypes.ULONG),
                ("ulRawButtons", ctypes.wintypes.ULONG), ("lLastX", ctypes.c_long),
                ("lLastY", ctypes.c_long), ("ulExtraInformation", ctypes.wintypes.ULONG)]

class _RAWINPUT(ctypes.Structure):
    _fields_ = [("header", _RAWINPUTHEADER), ("mouse", _RAWMOUSE)]


# ============================================================
# 1. RawInputReader
# ============================================================
class RawInputReader(QWidget):
    """Windows Raw Input 硬件级鼠标增量读取。"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DontShowOnScreen)
        self.setAttribute(Qt.WA_NativeWindow)
        self._delta_y = 0
        self._registered = False

    def register(self):
        hwnd = int(self.winId())
        dev = _RAWINPUTDEVICE()
        dev.usUsagePage = 1
        dev.usUsage = 2
        dev.dwFlags = 0x00000100  # RIDEV_INPUTSINK
        dev.hwndTarget = hwnd
        ok = user32.RegisterRawInputDevices(
            ctypes.byref(dev), 1, ctypes.sizeof(dev))
        self._registered = bool(ok)
        return ok

    def nativeEvent(self, eventType, message):
        if eventType in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x00FF:
                self._handle(msg.lParam)
                return True, 0
        return False, 0

    def _handle(self, hRaw):
        sz = ctypes.wintypes.UINT(0)
        user32.GetRawInputData(
            ctypes.c_void_p(hRaw), 0x10000003, None, ctypes.byref(sz), ctypes.sizeof(_RAWINPUTHEADER))
        if sz.value == 0 or sz.value > 4096:
            return
        buf = ctypes.create_string_buffer(sz.value)
        cpy = user32.GetRawInputData(
            ctypes.c_void_p(hRaw), 0x10000003, buf, ctypes.byref(sz), ctypes.sizeof(_RAWINPUTHEADER))
        if cpy == sz.value:
            raw = _RAWINPUT.from_buffer(buf)
            if raw.header.dwType == 0:
                if not (raw.mouse.usFlags & 0x01) and raw.mouse.lLastY != 0:
                    self._delta_y += raw.mouse.lLastY

    def consume_delta_y(self):
        v = self._delta_y
        self._delta_y = 0
        return v

    def close(self):
        if self._registered:
            dev = _RAWINPUTDEVICE()
            dev.usUsagePage = 1
            dev.usUsage = 2
            dev.dwFlags = 0x00000001
            dev.hwndTarget = None
            user32.RegisterRawInputDevices(
                ctypes.byref(dev), 1, ctypes.sizeof(dev))
            self._registered = False


# ============================================================
# 2. AngleCalibration — 点列分段线性
# ============================================================
class AngleCalibration:
    """点列分段线性：points = [[delta, angle], ...]，按 delta 排序。

    delta 落在两点之间 → 线性插值；端点外 → 钳定。
    """

    def __init__(self, points):
        if not points:
            raise ValueError("校准曲线至少需要 2 个点")
        self._points = sorted((float(d), float(a)) for d, a in points)
        if len(self._points) < 2:
            raise ValueError("校准曲线至少需要 2 个点")

    @property
    def points(self):
        return self._points

    @property
    def point_count(self):
        return len(self._points)

    @property
    def min_delta(self):
        return self._points[0][0]

    @property
    def max_delta(self):
        return self._points[-1][0]

    @property
    def min_angle(self):
        return self._points[0][1]

    @property
    def max_angle(self):
        return self._points[-1][1]

    def delta_to_angle(self, delta):
        if delta <= self._points[0][0]:
            return self._points[0][1]
        if delta >= self._points[-1][0]:
            return self._points[-1][1]
        for i in range(len(self._points) - 1):
            d0, a0 = self._points[i]
            d1, a1 = self._points[i + 1]
            if d0 <= delta <= d1:
                if d1 == d0:
                    return a1
                return a0 + (a1 - a0) * (delta - d0) / (d1 - d0)
        return self._points[-1][1]

    def angle_to_delta(self, angle):
        if angle <= self._points[0][1]:
            return self._points[0][0]
        if angle >= self._points[-1][1]:
            return self._points[-1][0]
        for i in range(len(self._points) - 1):
            d0, a0 = self._points[i]
            d1, a1 = self._points[i + 1]
            if a0 <= angle <= a1:
                if a1 == a0:
                    return d1
                return d0 + (d1 - d0) * (angle - a0) / (a1 - a0)
        return self._points[-1][0]

    def to_list(self):
        return [[int(d), a] for d, a in self._points]

    @classmethod
    def from_list(cls, lst):
        if not lst:
            return None
        return cls(lst)


# ============================================================
# 3. AngleTracker
# ============================================================
class AngleTracker(QObject):
    STATE_IDLE = "IDLE"
    STATE_CALIBRATING = "CALIBRATING"
    STATE_ACTIVE = "ACTIVE"
    STATE_PAUSED = "PAUSED"

    state_changed = pyqtSignal(str)
    angle_changed = pyqtSignal(float)
    started = pyqtSignal()
    stopped = pyqtSignal()
    log = pyqtSignal(str)

    def __init__(self, raw_reader):
        super().__init__()
        self.raw = raw_reader
        self.state = self.STATE_IDLE
        self._calibration_provider = None  # callable: 返回 AngleCalibration 或 None
        self._min_max_provider = None  # callable: 返回 (min, max) 元组
        self._cumulative_delta = 0.0
        self._base_delta = 0.0
        self._min_abs = 0.0
        self._max_abs = 0.0
        self.current_angle = -80.0

    def set_calibration_provider(self, provider):
        """注入校准数据提供者（callable: 返回 AngleCalibration 或 None）"""
        self._calibration_provider = provider

    def set_min_max_provider(self, provider):
        """注入 min/max 数据提供者（callable: 返回 (min, max) 元组）"""
        self._min_max_provider = provider

    @property
    def active_calibration(self):
        if self._calibration_provider is None:
            return None
        return self._calibration_provider()

    @property
    def active_min_angle(self):
        if self._min_max_provider is None:
            return None
        return self._min_max_provider()[0]

    @property
    def active_max_angle(self):
        if self._min_max_provider is None:
            return None
        return self._min_max_provider()[1]

    def refresh_min_max(self):
        """从 provider 重读 min/max，更新 current_angle（IDLE 状态时）"""
        min_angle = self.active_min_angle
        if min_angle is not None:
            self.current_angle = min_angle
            if self.state == self.STATE_IDLE:
                self.angle_changed.emit(self.current_angle)

    def start(self):
        if self.state != self.STATE_IDLE:
            return
        cal = self.active_calibration
        if cal is None:
            self.log.emit("[角度仪] 错误：当前载具未校准，请先做载具校准")
            return
        self._base_delta = cal.min_delta
        self._min_abs = cal.min_delta
        self._max_abs = cal.max_delta
        self._cumulative_delta = 0.0
        self.raw.consume_delta_y()
        self.current_angle = self.active_min_angle
        self._set_state(self.STATE_ACTIVE)
        self.angle_changed.emit(self.current_angle)
        self.started.emit()
        self.log.emit(f"[角度仪] 开始，范围 {self.active_min_angle}°~{self.active_max_angle}°")

    def stop(self):
        if self.state in (self.STATE_ACTIVE, self.STATE_PAUSED):
            self._set_state(self.STATE_IDLE)
            self.stopped.emit()
            self.log.emit("[角度仪] 已停止")

    def pause_toggle(self):
        if self.state == self.STATE_ACTIVE:
            self._set_state(self.STATE_PAUSED)
            self.log.emit("[角度仪] 已暂离")
        elif self.state == self.STATE_PAUSED:
            self.raw.consume_delta_y()
            self._set_state(self.STATE_ACTIVE)
            self.log.emit("[角度仪] 已恢复")

    def reset_to_zero(self):
        if self.state != self.STATE_ACTIVE:
            return
        cal = self.active_calibration
        if cal is None:
            return
        zero_delta = cal.angle_to_delta(0.0)
        current_abs = self._base_delta + self._cumulative_delta
        self._cumulative_delta += (zero_delta - current_abs)
        self.current_angle = 0.0
        self.angle_changed.emit(0.0)
        self.log.emit("[角度仪] 定角装填")

    def update(self):
        if self.state != self.STATE_ACTIVE:
            return
        delta = -self.raw.consume_delta_y()
        if delta == 0:
            return
        self._cumulative_delta += delta
        abs_delta = self._base_delta + self._cumulative_delta
        if abs_delta <= self._min_abs:
            self._cumulative_delta = self._min_abs - self._base_delta
            abs_delta = self._min_abs
        elif abs_delta >= self._max_abs:
            self._cumulative_delta = self._max_abs - self._base_delta
            abs_delta = self._max_abs
        cal = self.active_calibration
        if cal is None:
            return
        angle = cal.delta_to_angle(abs_delta)
        if abs(angle - self.current_angle) > 0.001:
            self.current_angle = angle
            # 对外读数按 0.1° 对齐 Squad Link 射表网格（内部保留全精度跟踪）
            self.angle_changed.emit(round(angle, 1))

    def _set_state(self, s):
        self.state = s
        self.state_changed.emit(s)


# ============================================================
# 4. Calibrator — 单点点对点校准
# ============================================================
class Calibrator(QObject):
    """单点点对点校准：每个角度按一次确认，记录一个 delta。

    流程：
      start(num_points, min_angle, max_angle)
        → 自动选 num_points 个建议角度（含端点和 0°）
      next_point()   # 当前角度已对准，按确认记录并进入下一个
      done          # 全部采完，发出 AngleCalibration
    """

    progress = pyqtSignal(int, int)
    hint = pyqtSignal(int, int, float)
    done = pyqtSignal(object)
    cancelled = pyqtSignal()
    log = pyqtSignal(str)

    VALID_POINT_COUNTS = (2, 5, 11)

    def __init__(self, raw_reader):
        super().__init__()
        self.raw = raw_reader
        self._num_points = 5
        self._step = 0
        self._min_angle = -80.0
        self._max_angle = 80.0
        self._target_angles = []
        self._collected = []
        self._abs_base = 0.0
        self._calibrating = False

    @property
    def is_calibrating(self):
        return self._calibrating

    def start(self, num_points=5, min_angle=-80.0, max_angle=80.0):
        if self._calibrating:
            return False
        if num_points not in self.VALID_POINT_COUNTS:
            self.log.emit(f"[校准] 错误：点数{num_points}无效，可选{self.VALID_POINT_COUNTS}")
            return False
        self._calibrating = True
        self._num_points = num_points
        self._step = 0
        self._min_angle = float(min_angle)
        self._max_angle = float(max_angle)
        self._target_angles = self._pick_angles(min_angle, max_angle, num_points)
        self._collected = []
        self._abs_base = 0.0
        self.raw.consume_delta_y()
        self.log.emit(f"[校准] 开始，{num_points}点，范围 {min_angle}°~{max_angle}°")
        self.progress.emit(0, num_points)
        target = self._target_angles[0]
        self._emit_hint(0, num_points, target)
        return True

    def _pick_angles(self, lo, hi, n):
        """均匀取 n 个建议角度，必含 lo, hi 两端点。
        n=2（两点/Squad Link 式）：只取两端点。"""
        lo, hi = float(lo), float(hi)
        if n == 2:
            return [lo, hi]
        step = (hi - lo) / (n - 1)
        return [round(lo + i * step, 4) for i in range(n)]

    def next_point(self):
        """当前角度已对准，记录 delta 并进入下一个。"""
        if not self._calibrating:
            return
        step = -self.raw.consume_delta_y()
        self._abs_base += step
        target = self._target_angles[self._step]
        self._collected.append((self._abs_base, target))
        self.log.emit(f"[校准] 角度 {target:.1f}°：记录 delta={self._abs_base:.0f}")
        self._step += 1
        if self._step >= len(self._target_angles):
            self._finish()
            return
        self.progress.emit(self._step, len(self._target_angles))
        self._emit_hint(self._step, len(self._target_angles),
                        self._target_angles[self._step])

    def cancel(self):
        if self._calibrating:
            self._calibrating = False
            self.cancelled.emit()
            self.log.emit("[校准] 已取消")

    def _finish(self):
        if len(self._collected) < 1:
            self.log.emit("[校准] 错误：未采集到任何数据")
            self._calibrating = False
            return
        cal = AngleCalibration(self._collected)
        self._calibrating = False
        self.done.emit(cal)
        self.log.emit(f"[校准] 完成！{cal.point_count} 个点")
        for d, a in cal.points:
            self.log.emit(f"  {a:.1f}°: delta={d:.0f}")

    def _emit_hint(self, step, total, target):
        self.hint.emit(step, total, target)
        self.log.emit(f"[校准] 请将炮塔调到 {target:.1f}°，按校准确认热键 ({step+1}/{total})")
