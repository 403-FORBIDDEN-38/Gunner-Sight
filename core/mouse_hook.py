from core.logger import logger

"""
共享低级鼠标钩子 (WH_MOUSE_LL)

HotkeyManager（全局热键）和 HotkeyLineEdit（热键绑定捕获）共用同一个钩子，
避免各自创建独立钩子导致系统钩子链过长。

使用引用计数：acquire() / release()，最后一个持有者释放时停止钩子。
"""
import ctypes
import ctypes.wintypes
import threading
import time

from PyQt5.QtCore import QObject, pyqtSignal

from core.win32_utils import kernel32

# 独立的 user32 DLL 实例，避免全局 windll 的线程安全问题
from core.win32_utils import user32 as _user32  # 统一 Win32 入口

# 严格设置函数参数类型和返回类型（64位安全）
_user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
]
_user32.SetWindowsHookExW.restype = ctypes.c_void_p  # HHOOK

_user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
_user32.UnhookWindowsHookEx.restype = ctypes.c_int

_user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint64, ctypes.c_int64,
]
_user32.CallNextHookEx.restype = ctypes.c_int64  # LRESULT

_user32.GetMessageW.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
]
_user32.GetMessageW.restype = ctypes.c_int

_user32.TranslateMessage.argtypes = [ctypes.c_void_p]
_user32.TranslateMessage.restype = ctypes.c_int

_user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
_user32.DispatchMessageW.restype = ctypes.c_int64

_user32.PostThreadMessageW.argtypes = [
    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_int64,
]
_user32.PostThreadMessageW.restype = ctypes.c_int


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", ctypes.wintypes.POINT),
        ("mouseData", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


WH_MOUSE_LL = 14
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
WM_MOUSEWHEEL = 0x020A
XBUTTON1, XBUTTON2 = 0x0001, 0x0002
HC_ACTION = 0
WM_QUIT = 0x0012
LLMHF_INJECTED = 0x01  # MSLLHOOKSTRUCT.flags 低位：事件是注入的(SendInput/mouse_event)

# HOOKPROC 类型：返回 LRESULT (c_int64)
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int64,  # LRESULT
    ctypes.c_int,    # nCode
    ctypes.c_uint64, # wParam (WPARAM)
    ctypes.c_int64,  # lParam (LPARAM)
)

_DOWN_EVENTS = {WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN}
_UP_EVENTS = {WM_LBUTTONUP, WM_RBUTTONUP, WM_MBUTTONUP, WM_XBUTTONUP}

_SIMPLE_KEY_MAP = {
    WM_LBUTTONDOWN: "mouse_left", WM_LBUTTONUP: "mouse_left",
    WM_RBUTTONDOWN: "mouse_right", WM_RBUTTONUP: "mouse_right",
    WM_MBUTTONDOWN: "mouse_middle", WM_MBUTTONUP: "mouse_middle",
}


class MouseHook(QObject):
    """全局共享鼠标钩子单例"""

    mouse_down = pyqtSignal(str)
    mouse_up = pyqtSignal(str)
    mouse_wheel = pyqtSignal(int)  # delta: 正数=向上滚动, 负数=向下滚动

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        super().__init__()
        self._hook = None
        self._thread = None
        self._running = False
        self._proc_ref = None
        self._thread_id = None
        self._ref_count = 0
        self._ref_lock = threading.Lock()
        self._retry_count = 0  # 钩子设置失败/线程意外退出的连续重试次数

    # --- 引用计数 ---
    def acquire(self):
        with self._ref_lock:
            self._ref_count += 1
            if self._ref_count == 1:
                self._start()

    def release(self):
        with self._ref_lock:
            self._ref_count -= 1
            if self._ref_count <= 0:
                self._ref_count = 0
                self._stop()

    # --- 内部 ---
    def _start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _stop(self):
        self._running = False
        if self._hook:
            try:
                _user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None
        if self._thread_id:
            try:
                _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        # 等待钩子线程结束（最多500ms）
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
            if self._thread.is_alive():
                # M11：超时说明线程卡在事件队列里，无法强杀——留痕，别静默
                logger.warning("[MouseHook] 钩子线程 500ms 内未退出（事件队列阻塞？）")
        self._proc_ref = None
        self._thread_id = None
        self._thread = None

    def _loop(self):
        while self._running:
            try:
                self._thread_id = threading.get_native_id()

                def hook_proc(nCode, wParam, lParam):
                    try:
                        if nCode == HC_ACTION:
                            msll = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                            if msll.flags & LLMHF_INJECTED:
                                return _user32.CallNextHookEx(None, nCode, wParam, lParam)
                            key = _SIMPLE_KEY_MAP.get(wParam)
                            if key is None and wParam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                                try:
                                    data = ctypes.cast(
                                        lParam, ctypes.POINTER(MSLLHOOKSTRUCT)
                                    ).contents
                                    xb = data.mouseData >> 16
                                    if xb == XBUTTON1:
                                        key = "mouse_xbutton1"
                                    elif xb == XBUTTON2:
                                        key = "mouse_xbutton2"
                                except Exception as e:
                                    logger.info(f"[MouseHook] XBUTTON 解析异常: {e}")
                            if wParam == WM_MOUSEWHEEL:
                                try:
                                    data = ctypes.cast(
                                        lParam, ctypes.POINTER(MSLLHOOKSTRUCT)
                                    ).contents
                                    delta = ctypes.c_short(data.mouseData >> 16).value
                                    if delta != 0:
                                        self.mouse_wheel.emit(delta)
                                except Exception as e:
                                    logger.info(f"[MouseHook] WHEEL 解析异常: {e}")
                            elif key:
                                if wParam in _DOWN_EVENTS:
                                    self.mouse_down.emit(key)
                                elif wParam in _UP_EVENTS:
                                    self.mouse_up.emit(key)
                    except Exception as e:
                        logger.info(f"[MouseHook] 钩子回调异常: {e}")
                    return _user32.CallNextHookEx(None, nCode, wParam, lParam)

                self._proc_ref = HOOKPROC(hook_proc)
                self._hook = _user32.SetWindowsHookExW(
                    WH_MOUSE_LL,
                    ctypes.cast(self._proc_ref, ctypes.c_void_p).value,
                    None, 0
                )
                if not self._hook:
                    error_code = kernel32.GetLastError()
                    if self._retry_count == 0:
                        logger.warning(f"[MouseHook] 钩子设置失败，错误码: {error_code}，开始重试")
                    else:
                        logger.debug(f"[MouseHook] 钩子设置失败（重试中，第 {self._retry_count + 1} 次），错误码: {error_code}")
                    self._retry_count += 1
                    # 刻意退避后重试：钩子可能被安全软件临时拦截，等一会儿能成。
                    # 这是"失败重试的退避"，不是"用等待掩盖时序问题"（AGENTS 2.1 禁的是后者）
                    time.sleep(1.0)
                    continue
                # 恢复成功：此前有过重试
                if self._retry_count > 0:
                    logger.warning(f"[MouseHook] 钩子已恢复（此前重试了 {self._retry_count} 次）")
                    self._retry_count = 0

                msg = ctypes.wintypes.MSG()
                while self._running:
                    bRet = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                    if bRet == 0 or bRet == -1:
                        break
                    _user32.TranslateMessage(ctypes.byref(msg))
                    _user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as e:
                logger.info(f"[MouseHook] 钩子线程错误: {e}")
            finally:
                if self._hook:
                    try:
                        _user32.UnhookWindowsHookEx(self._hook)
                    except Exception:
                        pass
                    self._hook = None
                self._proc_ref = None
            # 意外退出后自动重启（除非stop()被调用）
            if self._running:
                if self._retry_count == 0:
                    logger.warning("[MouseHook] 钩子线程意外退出，开始自动重启")
                else:
                    logger.debug(f"[MouseHook] 钩子线程意外退出（重启中，第 {self._retry_count + 1} 次）")
                self._retry_count += 1
                time.sleep(1.0)  # 同上：重试退避
        self._running = False
