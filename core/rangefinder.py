"""
Rangefinder - 集成进 GunnerSight 的独立模块
单轮 toggle 步骤，measure 调用两次 toggle（显示UI→截图→隐藏UI）
BlockInput 防止鼠标干扰，keybd_event 模拟按键
"""
import time
import ctypes
from core.win32_utils import user32  # T3: 统一 Win32 入口
from ctypes import wintypes
import threading
from PIL import Image
import mss
from PyQt5.QtCore import QThread, pyqtSignal

_user32 = user32
KEYEVENTF_KEYUP = 0x0002
VK_ESC = 0x1B


def quick_toggle_ui(x, y, step_interval=None):
    """快速有/无UI切换，共享 _execute_steps；重入保护。
    行为变更：执行后鼠标归位到屏幕中心。
    安全：_blocked 标志确保只在成功 BlockInput(True) 后释放，防止任何异常路径导致输入锁定。"""
    global _toggle_ui_running
    if _toggle_ui_running:
        return
    _toggle_ui_running = True
    _blocked = False
    try:
        try:
            _user32.BlockInput(True)
            _blocked = True
        except Exception:
            pass
        steps = apply_step_interval(DEFAULT_TOGGLE_STEPS, step_interval)
        _execute_steps(steps, x, y)
    finally:
        if _blocked:
            try:
                _user32.BlockInput(False)
            except Exception:
                pass
        try:
            sw = _user32.GetSystemMetrics(0)
            sh = _user32.GetSystemMetrics(1)
            _user32.SetCursorPos(sw // 2, sh // 2)
        except Exception:
            pass
        _toggle_ui_running = False

_VK_MAP = {
    "esc": 0x1B, "escape": 0x1B, "enter": 0x0D, "return": 0x0D,
    "space": 0x20, " ": 0x20, "tab": 0x09,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

DEFAULT_TOGGLE_STEPS = [
    {"action": "wait", "ms": 60},
    {"action": "press_key", "key": "esc"},
    {"action": "wait", "ms": 50},
    {"action": "click"},
    {"action": "wait", "ms": 40},
    {"action": "press_key", "key": "esc"},
    {"action": "wait", "ms": 200},
]

# 17.3B: quick_toggle_ui 重入保护（鼠标键作热键时，模拟 mouse_event 会被钩子再次捕获触发回调）
_toggle_ui_running = False


def _execute_steps(steps, bx, by):
    """17.3A: 模块级步骤执行器，quick_toggle_ui 与 RangefinderEngine._run_steps 共享。
    支持 action: wait(ms) / press_key(key) / click(使用 bx,by)。"""
    for step in steps:
        action = step.get("action")
        if action == "wait":
            time.sleep(step.get("ms", 10) / 1000.0)
        elif action == "press_key":
            vk = _VK_MAP.get(step.get("key", "").lower())
            if vk is not None:
                _user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.015)
                _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        elif action == "click":
            _user32.SetCursorPos(int(bx), int(by))
            time.sleep(0.01)
            _user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.015)
            _user32.mouse_event(0x0004, 0, 0, 0, 0)


def apply_step_interval(steps, interval):
    """把步骤列表中 action=="wait" 的步骤替换为 ms=interval，但保留最后一个 wait（UI恢复等待）。
    interval 为 None 时直接返回原 steps。"""
    if interval is None:
        return steps
    wait_indices = [i for i, s in enumerate(steps) if s.get("action") == "wait"]
    if not wait_indices:
        return steps
    last_wait = wait_indices[-1]
    return [dict(s, ms=interval) if s.get("action") == "wait" and i != last_wait else s
            for i, s in enumerate(steps)]


class RangefinderEngine:
    def __init__(self):
        self._sct = mss.mss()
        self._lock = threading.Lock()
        self.config = {}
        self.last_image = None
        self._abort = False  # 中止标志：关闭时设置，让 measure() 安全提前返回

    def set_config(self, config: dict):
        self.config = config

    def abort(self):
        """请求中止当前测距操作（线程安全）"""
        self._abort = True

    def close(self):
        """释放 mss 截图资源"""
        self._abort = True
        try:
            self._sct.close()
        except Exception:
            pass

    def capture_roi(self, roi=None):
        if roi is None:
            roi = self.config.get("roi", {})
        x, y, w, h = roi.get("x", 0), roi.get("y", 0), roi.get("w", 100), roi.get("h", 50)
        if w <= 0 or h <= 0:
            return None
        raw = self._sct.grab({"top": y, "left": x, "width": w, "height": h})
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def _click(self, x, y):
        _user32.SetCursorPos(int(x), int(y))
        time.sleep(0.015)
        _user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.015)
        _user32.mouse_event(0x0004, 0, 0, 0, 0)

    def _press_key(self, key_name):
        vk = _VK_MAP.get(key_name.lower())
        if vk is None:
            return
        _user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.015)
        _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    def _run_steps(self, steps):
        """T7: 复用模块级 _execute_steps，与 quick_toggle_ui 共享同一套执行逻辑
        保留 _abort 中止检查（measure 流程中可能被热键中止）"""
        btn = self.config.get("ui_button", {})
        bx, by = btn.get("x", 0), btn.get("y", 0)
        for step in steps:
            if self._abort:
                return
            _execute_steps([step], bx, by)

    def toggle_ui(self):
        steps = self.config.get("toggle_steps", DEFAULT_TOGGLE_STEPS)
        interval = self.config.get("toggle_ui_step_interval", None)
        steps = apply_step_interval(steps, interval)
        self._run_steps(steps)

    def measure(self):
        """显示UI → 截图（双区域）→ 隐藏UI，返回 {"roi1": img, "roi2": img_or_None}"""
        self._abort = False  # 重置中止标志
        with self._lock:
            # 记录鼠标位置
            pt = wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(pt))

            # BlockInput 防止用户干扰（需管理员权限）
            try:
                _user32.BlockInput(True)
                blocked = True
            except Exception:
                blocked = False

            captured1 = None
            captured2 = None
            try:
                if not self._abort:
                    self.toggle_ui()  # 显示UI
                if not self._abort:
                    time.sleep(0.01)  # 动作间容错
                if not self._abort:
                    captured1 = self.capture_roi()
                # 第二区域（如果启用）
                if not self._abort:
                    roi2 = self.config.get("roi2", {})
                    if roi2.get("enabled", False):
                        captured2 = self.capture_roi(roi2)
                if not self._abort:
                    time.sleep(0.01)  # 动作间容错
                if not self._abort:
                    self.toggle_ui()  # 隐藏UI
            finally:
                # 无论是否中止，都必须恢复 BlockInput 和鼠标位置
                if blocked:
                    try:
                        _user32.BlockInput(False)
                    except Exception:
                        pass
                try:
                    _user32.SetCursorPos(pt.x, pt.y)
                except Exception:
                    pass

            self.last_image = captured1
            return {"roi1": captured1, "roi2": captured2}


class MeasureThread(QThread):
    finished = pyqtSignal(object)

    def __init__(self, rf):
        super().__init__()
        self.rf = rf

    def run(self):
        img = self.rf.measure()
        self.finished.emit(img)
