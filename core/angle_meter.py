"""
角度仪核心模块 — 纯逻辑，无 UI 依赖。

FEATURE-1: 取消全局校准，每载具单曲线（用户自选X点）。
每个载具有且只有一条校准曲线，用户自选校准点数（3/5/7/9/11）。

GS 接入方式:
    from core.angle_meter import RawInputReader, AngleTracker, Calibrator, AngleCalibration

    raw = RawInputReader()
    raw.register()
    tracker = AngleTracker(raw)
    calibrator = Calibrator(raw)

    # 设置当前载具配置（由 GS ConfigManager 提供）
    tracker.set_vehicle_config(min_angle=-20, max_angle=30, calibration=cal)

    # 使用
    tracker.start()      # 开始（用户已调到最低角）
    tracker.update()     # 每帧调用（GS 定时器）
    tracker.stop()       # 停止

    # 校准（用户自选点数）
    calibrator.start(num_points=7, min_angle=-20, max_angle=30)
    calibrator.next_point()  # 确认键
    calibrator.done.connect(lambda cal: tracker.set_calibration(cal))
"""
import ctypes
from core.win32_utils import user32  # 统一 Win32 入口
import ctypes.wintypes
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QObject


# ============================================================
# Raw Input ctypes 结构（模块级别）
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
# 1. RawInputReader — 唯一鼠标增量输入源
# ============================================================
class RawInputReader(QWidget):
    """Windows Raw Input 硬件级鼠标增量读取。无业务逻辑。"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DontShowOnScreen)
        self.setAttribute(Qt.WA_NativeWindow)  # 确保原生窗口创建，接收 WM_INPUT
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
            if raw.header.dwType == 0:  # RIM_TYPEMOUSE
                if not (raw.mouse.usFlags & 0x01) and raw.mouse.lLastY != 0:
                    self._delta_y += raw.mouse.lLastY

    def consume_delta_y(self):
        """读取并清空垂直增量。上移返回负值，下移返回正值。"""
        v = self._delta_y
        self._delta_y = 0
        return v


# ============================================================
# 2. AngleCalibration — 不可变校准曲线
# ============================================================
class AngleCalibration:
    """不可变校准曲线：增量→角度的分段线性映射。
    FEATURE-1: 点数不固定，由用户自选（3/5/7/9/11）。"""

    def __init__(self, points):
        if points is None or len(points) < 2:
            raise ValueError("校准曲线必须提供至少2点（空房子原则：无出厂兜底）")
        self._points = tuple((float(d), float(a)) for d, a in points)

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
        """增量→角度（分段线性，超范围钳定）"""
        if delta <= self._points[0][0]:
            return self._points[0][1]
        if delta >= self._points[-1][0]:
            return self._points[-1][1]
        for i in range(len(self._points) - 1):
            d0, a0 = self._points[i]
            d1, a1 = self._points[i + 1]
            if d0 <= delta <= d1:
                if d1 == d0:
                    return a0
                return a0 + (a1 - a0) * (delta - d0) / (d1 - d0)
        return self._points[-1][1]

    def angle_to_delta(self, angle):
        """角度→增量（反查）"""
        if angle <= self._points[0][1]:
            return self._points[0][0]
        if angle >= self._points[-1][1]:
            return self._points[-1][0]
        for i in range(len(self._points) - 1):
            d0, a0 = self._points[i]
            d1, a1 = self._points[i + 1]
            if a0 <= angle <= a1:
                if a1 == a0:
                    return d0
                return d0 + (d1 - d0) * (angle - a0) / (a1 - a0)
        return self._points[-1][0]

    def to_list(self):
        return [[d, a] for d, a in self._points]

    @classmethod
    def from_list(cls, lst):
        if not lst or len(lst) < 2:
            return None
        return cls([(float(p[0]), float(p[1])) for p in lst])


# ============================================================
# 3. AngleTracker — 使用状态机
# ============================================================
class AngleTracker(QObject):
    """角度追踪器。只管使用状态，不管校准流程和载具列表。
    FEATURE-1: calibration必须是载具自己的曲线，无全局校准兜底。"""
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
        self._min_angle = -80.0
        self._max_angle = 80.0
        self._calibration = None  # FEATURE-1: 必须是载具自己的曲线，None=未校准
        self._cumulative_delta = 0.0
        self._base_delta = 0.0
        self._min_abs = 0.0
        self._max_abs = 0.0
        self.current_angle = -80.0

    def set_vehicle_config(self, min_angle, max_angle, calibration=None):
        """注入当前载具配置。可在 IDLE 时随时调用。"""
        self._min_angle = float(min_angle)
        self._max_angle = float(max_angle)
        self._calibration = calibration
        self.current_angle = self._min_angle
        if self.state == self.STATE_IDLE:
            self.angle_changed.emit(self.current_angle)

    def set_calibration(self, cal):
        """设置载具校准曲线（None=未校准）"""
        self._calibration = cal

    @property
    def active_calibration(self):
        return self._calibration

    def start(self):
        if self.state != self.STATE_IDLE:
            return
        cal = self._calibration
        if cal is None:
            self.log.emit("[角度仪] 错误：当前载具未校准，请先做载具校准")
            return
        # FEATURE-1: 载具曲线本身就是载具范围，直接用端点
        self._base_delta = cal.min_delta
        self._min_abs = cal.min_delta
        self._max_abs = cal.max_delta
        self._cumulative_delta = 0.0
        self.raw.consume_delta_y()
        self.current_angle = self._min_angle
        self._set_state(self.STATE_ACTIVE)
        self.angle_changed.emit(self.current_angle)
        self.started.emit()
        self.log.emit(f"[角度仪] 开始，范围 {self._min_angle}°~{self._max_angle}°")

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
        """归零：将当前位置设为0度基准"""
        if self.state != self.STATE_ACTIVE:
            return
        cal = self._calibration
        if cal is None:
            return
        zero_delta = cal.angle_to_delta(0.0)
        current_abs = self._base_delta + self._cumulative_delta
        self._cumulative_delta += (zero_delta - current_abs)
        self.current_angle = 0.0
        self.angle_changed.emit(0.0)
        self.log.emit("[角度仪] 归零")

    def update(self):
        """每帧调用。IDLE/PAUSED 时直接返回。"""
        if self.state != self.STATE_ACTIVE:
            return
        delta = -self.raw.consume_delta_y()  # 上移为正
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
        cal = self._calibration
        if cal is None:
            return
        angle = cal.delta_to_angle(abs_delta)
        if abs(angle - self.current_angle) > 0.01:
            self.current_angle = angle
            self.angle_changed.emit(angle)

    def _set_state(self, s):
        self.state = s
        self.state_changed.emit(s)


# ============================================================
# 4. Calibrator — 校准流程控制器（FEATURE-1: 单模式，用户自选点数）
# ============================================================
class Calibrator(QObject):
    """校准流程控制器。FEATURE-1: 单模式，用户自选点数（3/5/7/9/11），直接采集N点。"""
    progress = pyqtSignal(int, int)
    hint = pyqtSignal(int, int, float)
    done = pyqtSignal(object)
    cancelled = pyqtSignal()
    log = pyqtSignal(str)

    VALID_POINT_COUNTS = (3, 5, 7, 9, 11)

    def __init__(self, raw_reader):
        super().__init__()
        self.raw = raw_reader
        self._num_points = 7
        self._step = 0
        self._min_angle = -80.0
        self._max_angle = 80.0
        self._points = []
        self._calibrating = False

    @property
    def is_calibrating(self):
        return self._calibrating

    def start(self, num_points=7, min_angle=-80.0, max_angle=80.0):
        """开始校准。num_points必须在VALID_POINT_COUNTS中。"""
        if self._calibrating:
            return
        if num_points not in self.VALID_POINT_COUNTS:
            self.log.emit(f"[校准] 错误：点数{num_points}无效，可选{self.VALID_POINT_COUNTS}")
            return
        self._calibrating = True
        self._num_points = num_points
        self._step = 0
        self._points = []
        self._min_angle = float(min_angle)
        self._max_angle = float(max_angle)
        self.raw.consume_delta_y()
        self.log.emit(f"[校准] 开始，{num_points}点，范围 {min_angle}°~{max_angle}°")
        self.progress.emit(0, num_points)
        target = self._target_for_step(0)
        self._emit_hint(0, num_points, target, "最低角")

    def next_point(self):
        if not self._calibrating:
            return
        delta_step = -self.raw.consume_delta_y()
        if self._step == 0:
            abs_delta = 0.0
        else:
            abs_delta = self._points[-1][0] + delta_step
        target = self._target_for_step(self._step)
        self._points.append((abs_delta, target))
        self.log.emit(f"[校准] 点{self._step+1}/{self._num_points}: 总增量={abs_delta:.0f}, 角度={target:.1f}°")
        self._step += 1
        self.progress.emit(self._step, self._num_points)
        if self._step >= self._num_points:
            cal = AngleCalibration(self._points)
            self._finish(cal)
        else:
            target = self._target_for_step(self._step)
            self._emit_hint(self._step, self._num_points, target)

    def cancel(self):
        if self._calibrating:
            self._calibrating = False
            self.cancelled.emit()
            self.log.emit("[校准] 已取消")

    def _target_for_step(self, step):
        """均匀分布在min_angle~max_angle之间"""
        return self._min_angle + step * (self._max_angle - self._min_angle) / (self._num_points - 1)

    def _finish(self, cal):
        self.log.emit(f"[校准] 完成！{cal.point_count}点分段线性")
        for i, (d, a) in enumerate(cal.points):
            self.log.emit(f"  点{i+1}: 增量={d:.0f}, 角度={a:.1f}°")
        self._calibrating = False
        self.done.emit(cal)

    def _emit_hint(self, step, total, target, label=""):
        self.hint.emit(step, total, target)
        suffix = f"（{label}）" if label else ""
        self.log.emit(f"[校准] 请将炮塔调到 {target:.1f}°{suffix}，按确认键记录 ({step+1}/{total})")
