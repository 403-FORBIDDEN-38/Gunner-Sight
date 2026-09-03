"""
角度仪核心模块 — 纯逻辑，无 UI 依赖。

GS 接入方式:
    from core.angle_meter import RawInputReader, AngleTracker, Calibrator, AngleCalibration

    raw = RawInputReader()
    raw.register()
    tracker = AngleTracker(raw)
    calibrator = Calibrator(raw, global_cal)  # global_cal 由用户全局校准提供

    # 设置当前载具配置（由 GS ConfigManager 提供）
    tracker.set_vehicle_config(min_angle=-20, max_angle=30, calibration=None)

    # 使用
    tracker.start()      # 开始（用户已调到最低角）
    tracker.update()     # 每帧调用（GS 定时器）
    tracker.stop()       # 停止

    # 校准
    calibrator.start("quick", -20, 30)
    calibrator.next_point()  # F6 确认
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
        self._injected_delta_y = 0
        self._registered = False

    def inject_delta_y(self, value):
        """热键注入垂直增量（上移负值，下移正值，和硬件增量一致）"""
        self._injected_delta_y += value

    def register(self):
        # 确保原生窗口已创建（winId() 会强制创建）
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
                bf = raw.mouse.ulButtons & 0xFFFF
                if not (raw.mouse.usFlags & 0x01) and raw.mouse.lLastY != 0:
                    self._delta_y += raw.mouse.lLastY

    def consume_delta_y(self):
        """读取并清空垂直增量（硬件+热键注入合并）。上移返回负值，下移返回正值。"""
        v = self._delta_y + self._injected_delta_y
        self._delta_y = 0
        self._injected_delta_y = 0
        return v


# ============================================================
# 2. AngleCalibration — 不可变校准曲线
# ============================================================
class AngleCalibration:
    """不可变校准曲线：增量→角度的分段线性映射。"""
    NUM_POINTS = 7
    # 全局校准目标角度（功能参数，非用户数据）
    GLOBAL_TARGETS = [-80.0, -53.2, -26.6, 0.0, 26.6, 53.2, 80.0]

    def __init__(self, points):
        if points is None or len(points) < 2:
            raise ValueError("校准曲线必须提供至少2点（空房子原则：无出厂兜底）")
        self._points = tuple((float(d), float(a)) for d, a in points)

    @property
    def points(self):
        return self._points

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
        """角度→增量（反查，用于确定载具范围在全局曲线中的位置）"""
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
# 3. AngleTracker — 使用状态机（无载具管理，由外部注入配置）
# ============================================================
class AngleTracker(QObject):
    """角度追踪器。只管使用状态，不管校准流程和载具列表。"""
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
        # 当前载具配置（由外部注入）
        self._min_angle = -80.0
        self._max_angle = 80.0
        self._calibration = None  # None = 使用全局出厂校准
        # 使用状态
        self._cumulative_delta = 0.0
        self._base_delta = 0.0  # 载具最低角在全局曲线中的增量位置
        self._min_abs = 0.0     # 缓存：载具范围下限的绝对增量
        self._max_abs = 0.0     # 缓存：载具范围上限的绝对增量
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
        """设置载具单独校准曲线（None = 全局出厂）"""
        self._calibration = cal

    @property
    def active_calibration(self):
        return self._calibration  # 可能为 None（空房子原则：无出厂兜底）

    def start(self):
        if self.state != self.STATE_IDLE:
            return
        cal = self.active_calibration
        if cal is None:
            self.log.emit("[角度仪] 错误：无校准曲线，请先做全局校准或载具校准")
            return
        # 确定基准增量：载具最低角对应的绝对增量
        if self._calibration is None:
            # 使用全局校准：载具范围是全局的子区间
            self._base_delta = cal.angle_to_delta(self._min_angle)
            self._min_abs = self._base_delta
            self._max_abs = cal.angle_to_delta(self._max_angle)
        else:
            # 使用载具单独校准：曲线本身就是载具范围
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
            self.raw.consume_delta_y()  # 暂离期间的鼠标移动不计入
            self._set_state(self.STATE_ACTIVE)
            self.log.emit("[角度仪] 已恢复")

    def reset_to_zero(self):
        """归零：将当前位置设为0度基准"""
        if self.state != self.STATE_ACTIVE:
            return
        cal = self.active_calibration
        if cal is None:
            return
        zero_delta = cal.angle_to_delta(0.0)
        # 调整 cumulative 使当前角度=0
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
        # 钳定到载具范围（用绝对增量比较，避免角度浮点边界问题）
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
        if abs(angle - self.current_angle) > 0.01:
            self.current_angle = angle
            self.angle_changed.emit(angle)

    def _set_state(self, s):
        self.state = s
        self.state_changed.emit(s)


# ============================================================
# 4. Calibrator — 校准流程控制器
# ============================================================
class Calibrator(QObject):
    """校准流程控制器。独立于 AngleTracker。"""
    progress = pyqtSignal(int, int)
    hint = pyqtSignal(int, int, float)
    done = pyqtSignal(object)
    cancelled = pyqtSignal()
    log = pyqtSignal(str)

    MODE_QUICK = "quick"
    MODE_FULL = "full"

    def __init__(self, raw_reader, global_cal=None):
        super().__init__()
        self.raw = raw_reader
        self.global_cal = global_cal  # 可能为 None（用户未做全局校准时）
        self._mode = None
        self._step = 0
        self._min_angle = -80.0
        self._max_angle = 80.0
        self._points = []
        self._quick_min_delta = 0.0

    @property
    def is_calibrating(self):
        return self._mode is not None

    def start(self, mode, min_angle, max_angle):
        if self.is_calibrating:
            return
        self._mode = mode
        self._step = 0
        self._points = []
        self._min_angle = float(min_angle)
        self._max_angle = float(max_angle)
        self.raw.consume_delta_y()

        if mode == self.MODE_QUICK:
            self.log.emit(f"[快速校准] 开始，范围 {min_angle}°~{max_angle}°（2点）")
            self.progress.emit(0, 2)
            self._emit_hint(0, 2, min_angle, "最低角")
        else:
            self.log.emit(f"[7点校准] 开始，范围 {min_angle}°~{max_angle}°")
            self.progress.emit(0, 7)
            target = self._target_for_step(0)
            self._emit_hint(0, 7, target, "最低角")

    def next_point(self):
        if not self.is_calibrating:
            return
        delta_step = -self.raw.consume_delta_y()
        if self._mode == self.MODE_QUICK:
            self._next_quick(delta_step)
        else:
            self._next_full(delta_step)

    def cancel(self):
        if self.is_calibrating:
            self._mode = None
            self.cancelled.emit()
            self.log.emit("[校准] 已取消")

    def _next_quick(self, delta_step):
        if self._step == 0:
            self._quick_min_delta = 0.0
            self._step = 1
            self.progress.emit(1, 2)
            self.log.emit("[快速校准] 第1点已记录（最低角）")
            self._emit_hint(1, 2, self._max_angle, "最高角")
        else:
            max_delta = self._quick_min_delta + delta_step
            self.log.emit(f"[快速校准] 第2点已记录（最高角），总增量={max_delta:.0f}")
            if max_delta <= 0:
                self.log.emit("[快速校准] 失败：总增量为0，请确保从最低角移动到最高角")
                self._mode = None
                self.cancelled.emit()
                return
            cal = self._generate_from_endpoints(self._quick_min_delta, max_delta)
            self._finish(cal)

    def _generate_from_endpoints(self, min_delta, max_delta):
        """用全局校准曲线反查增量相对位置，复刻非线性形状到载具范围。
        无全局校准时退化为线性插值。"""
        vehicle_total = max_delta - min_delta
        if self.global_cal is None:
            # 无全局校准：线性插值兜底
            generated = []
            for i in range(AngleCalibration.NUM_POINTS):
                rel = i / (AngleCalibration.NUM_POINTS - 1)
                veh_angle = self._min_angle + rel * (self._max_angle - self._min_angle)
                veh_delta = min_delta + rel * vehicle_total
                generated.append((round(veh_delta, 1), round(veh_angle, 1)))
            return AngleCalibration(generated)
        global_min_delta = self.global_cal.min_delta
        global_max_delta = self.global_cal.max_delta
        global_delta_range = global_max_delta - global_min_delta
        if global_delta_range == 0:
            # 兜底：线性插值
            generated = []
            for i in range(AngleCalibration.NUM_POINTS):
                rel = i / (AngleCalibration.NUM_POINTS - 1)
                veh_angle = self._min_angle + rel * (self._max_angle - self._min_angle)
                veh_delta = min_delta + rel * vehicle_total
                generated.append((round(veh_delta, 1), round(veh_angle, 1)))
            return AngleCalibration(generated)
        generated = []
        global_min_angle = self.global_cal.min_angle
        global_max_angle = self.global_cal.max_angle
        for i in range(AngleCalibration.NUM_POINTS):
            global_angle = self.global_cal.points[i][1]
            # 关键：用全局曲线反查该角度对应的真实增量（捕捉非线性）
            global_delta_at_angle = self.global_cal.angle_to_delta(global_angle)
            # 该增量在全局增量范围内的相对位置
            rel = (global_delta_at_angle - global_min_delta) / global_delta_range
            # 映射到载具增量范围
            veh_delta = min_delta + rel * vehicle_total
            # 角度映射到载具范围（用角度比例）
            veh_angle = self._min_angle + (global_angle - global_min_angle) / (global_max_angle - global_min_angle) * (self._max_angle - self._min_angle)
            generated.append((round(veh_delta, 1), round(veh_angle, 1)))
        return AngleCalibration(generated)

    def _next_full(self, delta_step):
        if self._step == 0:
            abs_delta = 0.0
        else:
            abs_delta = self._points[-1][0] + delta_step
        target = self._target_for_step(self._step)
        self._points.append((abs_delta, target))
        self.log.emit(f"[7点校准] 点{self._step+1}/7: 总增量={abs_delta:.0f}, 角度={target:.1f}°")
        self._step += 1
        self.progress.emit(self._step, 7)
        if self._step >= 7:
            cal = AngleCalibration(self._points)
            self._finish(cal)
        else:
            target = self._target_for_step(self._step)
            self._emit_hint(self._step, 7, target)

    def _target_for_step(self, step):
        if abs(self._min_angle - (-80.0)) < 0.01 and abs(self._max_angle - 80.0) < 0.01:
            return AngleCalibration.GLOBAL_TARGETS[step]
        return self._min_angle + step * (self._max_angle - self._min_angle) / 6

    def _finish(self, cal):
        mode_name = "快速校准" if self._mode == self.MODE_QUICK else "7点校准"
        self.log.emit(f"[{mode_name}] 完成！")
        for i, (d, a) in enumerate(cal.points):
            self.log.emit(f"  点{i+1}: 增量={d:.0f}, 角度={a:.1f}°")
        self._mode = None
        self.done.emit(cal)

    def _emit_hint(self, step, total, target, label=""):
        self.hint.emit(step, total, target)
        suffix = f"（{label}）" if label else ""
        self.log.emit(f"[校准] 请将炮塔调到 {target:.1f}°{suffix}，按确认键记录 ({step+1}/{total})")
