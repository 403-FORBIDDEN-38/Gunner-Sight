from core.logger import logger

"""
建队宏模块 - Squad 游戏一键建队循环
流程：控制台键 → Win32 剪贴板粘贴 CreateSquad "名称" 1/0 → 回车 → 循环 ↑ 回车
"""
import ctypes
import threading
import time
from ctypes import wintypes

from core.win32_utils import KEY_NAME_VK, kernel32, user32

_user32 = user32

KEYEVENTF_KEYUP = 0x0002
VK_RETURN = 0x0D
VK_UP = 0x26
VK_CONTROL = 0x11
VK_V = 0x56
VK_MENU = 0x12
VK_TAB = 0x09
VK_CAPITAL = 0x14



# ctypes 签名：模块级设置一次，避免每次剪贴板操作重复绑定
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.restype = ctypes.c_void_p
_user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
_user32.SetClipboardData.restype = ctypes.c_void_p


def _resolve_vk(key_name):
    if not key_name:
        return 0xC0
    name = key_name.lower().strip()
    if name in KEY_NAME_VK:
        return KEY_NAME_VK[name]
    try:
        result = _user32.VkKeyScanW(ord(name[0]))
        if result != -1 and (result & 0xFF) != 0xFF:
            return result & 0xFF
    except Exception:
        pass
    return 0xC0


def _key_down(vk):
    _user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk):
    _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _press(vk, delay=0.015):
    _key_down(vk)
    time.sleep(delay)
    _key_up(vk)


def _set_clipboard_text(text):
    """用 Win32 API 直接设置系统剪贴板。失败路径释放全局内存，避免泄漏。"""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    if not _user32.OpenClipboard(None):
        return
    try:
        _user32.EmptyClipboard()
        data = text.encode('utf-16-le') + b'\x00\x00'
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return
        locked = kernel32.GlobalLock(h)
        if not locked:
            kernel32.GlobalFree(h)
            return
        ctypes.memmove(locked, data, len(data))
        kernel32.GlobalUnlock(h)
        # SetClipboardData 成功后内存所有权移交系统，不可再 Free；失败才释放
        if not _user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
    finally:
        _user32.CloseClipboard()


def _paste():
    _key_down(VK_CONTROL)
    time.sleep(0.03)
    _press(VK_V, 0.03)
    time.sleep(0.03)
    _key_up(VK_CONTROL)
    time.sleep(0.05)


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def find_game_window(keyword="squad"):
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
    if not hwnd:
        return False
    try:
        _user32.ShowWindow(hwnd, 9)
        time.sleep(0.05)
        _user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def alt_tab():
    _key_down(VK_MENU)
    time.sleep(0.02)
    _press(VK_TAB, 0.02)
    time.sleep(0.02)
    _key_up(VK_MENU)


class SquadMacro:
    def __init__(self):
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        self.on_stopped = None

    @property
    def running(self):
        return self._running

    def start(self, squad_name: str, locked: bool = True, interval_ms: int = 100, console_key: str = "`"):
        if self._running:
            return
        if not squad_name.strip():
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            args=(squad_name.strip(), locked, max(50, interval_ms), console_key),
            daemon=True
        )
        self._thread.start()

    def stop(self, wait: bool = True, timeout: float = 1.0):
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    def _loop(self, squad_name: str, locked: bool, interval_ms: int, console_key: str = "`"):
        was_caps_on = bool(_user32.GetKeyState(VK_CAPITAL) & 0x0001)
        try:
            interval = interval_ms / 1000.0
            console_name = console_key.split("+")[-1].strip() if console_key else "`"
            console_vk = _resolve_vk(console_name)
            cmd = f'CreateSquad "{squad_name}" {"1" if locked else "0"}'

            _set_clipboard_text(cmd)

            # 开 CapsLock 使 IME 自动切英文，避免中文输入法拦截按键
            if not was_caps_on:
                _press(VK_CAPITAL, 0.03)
                time.sleep(0.05)

            if self._stop_event.is_set(): return
            _press(console_vk, 0.05)
            if self._stop_event.is_set(): return
            _press(console_vk, 0.05)
            if self._stop_event.is_set(): return
            _paste()
            if self._stop_event.is_set(): return
            _press(VK_RETURN, 0.015)
            if self._stop_event.wait(interval): return

            while not self._stop_event.is_set():
                _press(VK_UP, 0.015)
                if self._stop_event.is_set(): break
                _press(VK_RETURN, 0.015)
                if self._stop_event.wait(interval): break
        except Exception as e:
            logger.info(f"[SquadMacro] 循环异常: {e}")
        finally:
            # 恢复 CapsLock 原始状态
            try:
                if not was_caps_on and bool(_user32.GetKeyState(VK_CAPITAL) & 0x0001):
                    _press(VK_CAPITAL, 0.03)
            except Exception:
                pass
            self._running = False
            if self.on_stopped:
                try:
                    self.on_stopped()
                except Exception:
                    pass
