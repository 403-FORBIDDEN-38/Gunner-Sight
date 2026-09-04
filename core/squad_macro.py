"""
建队宏模块 - Squad 游戏一键建队循环
流程：~ ~ 粘贴 CreateSquad "名称" 1/0 回车 → 循环 ↑ 回车 → 用户停止
"""
import time
import ctypes
from core.win32_utils import user32  # 统一 Win32 入口
import threading

_user32 = user32

VK_OEM3 = 0xC0      # ~ 键
VK_RETURN = 0x0D     # 回车
VK_UP = 0x26         # ↑
VK_CONTROL = 0x11    # Ctrl
VK_V = 0x56          # V
KEYEVENTF_KEYUP = 0x0002


def _key_down(vk):
    _user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk):
    _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _press(vk, delay=0.015):
    _key_down(vk)
    time.sleep(delay)
    _key_up(vk)


def _paste():
    """Ctrl+V 粘贴"""
    _key_down(VK_CONTROL)
    time.sleep(0.01)
    _press(VK_V, 0.01)
    time.sleep(0.01)
    _key_up(VK_CONTROL)


# 模块级 WNDENUMPROC 回调类型，避免每次 find_game_window 调用时重复创建
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def find_game_window(keyword="squad"):
    """查找标题包含关键字的顶层窗口（不区分大小写），返回 hwnd 或 None"""
    results = []

    def _enum_cb(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd):
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buf, length + 1)
                if keyword.lower() in buf.value.lower():
                    results.append(hwnd)
        return True

    _user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    return results[0] if results else None


def activate_window(hwnd):
    """激活并前置指定窗口"""
    if not hwnd:
        return False
    try:
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.05)
        _user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def alt_tab():
    """模拟 Alt+Tab 切换到下一个窗口"""
    _key_down(0x12)  # VK_MENU (Alt)
    time.sleep(0.02)
    _press(0x09, 0.02)  # Tab
    time.sleep(0.02)
    _key_up(0x12)


class SquadMacro:
    """建队宏：一键建队循环"""

    def __init__(self):
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        self.on_stopped = None  # 停止回调（用于UI关闭开关）

    @property
    def running(self):
        return self._running

    def start(self, squad_name: str, locked: bool = True, interval_ms: int = 100):
        """开始建队循环（剪贴板由调用者在主线程设置）"""
        if self._running:
            return
        if not squad_name.strip():
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            args=(squad_name.strip(), locked, max(50, interval_ms)),
            daemon=True
        )
        self._thread.start()

    def stop(self, wait: bool = True, timeout: float = 1.0):
        """停止建队循环"""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    def _loop(self, squad_name: str, locked: bool, interval_ms: int):
        try:
            interval = interval_ms / 1000.0
            # 初始化步骤：每步前检查 stop_event，确保关闭时能快速响应
            # 1. ~ 唤出控制台
            if self._stop_event.is_set(): return
            _press(VK_OEM3, 0.02)
            if self._stop_event.wait: return
            # 2. ~ 展开控制台
            if self._stop_event.is_set(): return
            _press(VK_OEM3, 0.02)
            if self._stop_event.wait: return
            # 3. 粘贴命令（剪贴板已由调用者在主线程设置）
            if self._stop_event.wait: return
            _paste()
            if self._stop_event.wait: return
            # 4. 第一次回车提交
            if self._stop_event.is_set(): return
            _press(VK_RETURN, 0.015)
            if self._stop_event.wait(interval): return

            # 5. 循环 ↑ 回车（等待地图加载后建队成功）
            while not self._stop_event.is_set():
                _press(VK_UP, 0.015)
                if self._stop_event.wait: break
                _press(VK_RETURN, 0.015)
                if self._stop_event.wait(interval): break
        except Exception as e:
            print(f"[SquadMacro] 循环异常: {e}")
        finally:
            self._running = False
            if self.on_stopped:
                try:
                    self.on_stopped()
                except Exception:
                    pass
