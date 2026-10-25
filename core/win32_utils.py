from core.logger import logger

"""
Win32 窗口工具函数
"""
import ctypes
import time
from ctypes import wintypes

_user32 = ctypes.windll.user32
user32 = _user32  # 公共导出，所有模块统一从此处导入，禁止各自 ctypes.windll.user32 / WinDLL
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

# SetWindowDisplayAffinity 的 dwAffinity 取值：把窗口从截屏/录屏里排除（放大镜不拍自己）
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

# === mouse_event 常量（简单可靠，try/finally确保UP必发） ===
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002

# === SendInput 结构定义（原子输入序列，64位对齐） ===
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _INPUT_UNION),
    ]

INPUT_MOUSE = 0
user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint


# EnumThreadWindows 用于枚举前台窗口线程的所有窗口
user32.EnumThreadWindows.argtypes = [wintypes.DWORD, ctypes.c_void_p, wintypes.LPARAM]
user32.EnumThreadWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
# 窗口样式长属性（64 位安全：句柄按指针宽度传，样式值按 LONG）
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

# 截屏屏蔽与屏幕度量。
# SetWindowDisplayAffinity 的 HWND 必须显式声明 argtypes：不声明时 ctypes 按 C int
# 传参，64 位下高位句柄会被截断（现在能用是因为 HWND 实际值几乎都 < 2^32，纯属碰巧）。
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int


def release_mouse_capture():
    """强制释放任何窗口的鼠标捕获（SetCapture泄漏）。
    向当前前台窗口线程的所有窗口、光标下窗口及其父窗口链发送WM_CANCELMODE。
    WM_CANCELMODE会让窗口取消模态操作并调用ReleaseCapture。"""
    # 1. 释放当前线程的捕获
    try:
        user32.ReleaseCapture()
    except Exception as e:
        logger.info(f"[win32_utils] ReleaseCapture failed: {e}")
    # 2. 向前台窗口线程的所有窗口发WM_CANCELMODE（最彻底）
    try:
        fg = user32.GetForegroundWindow()
        if fg:
            tid = user32.GetWindowThreadProcessId(fg, None)
            if tid:
                def _enum_cb(hwnd, _lp):
                    _send_cancel_mode(hwnd)
                    return True
                cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_enum_cb)
                user32.EnumThreadWindows(tid, cb, 0)
    except Exception as e:
        logger.info(f"[win32_utils] EnumThreadWindows failed: {e}")
    # 3. 向光标下窗口及其父窗口链发WM_CANCELMODE
    try:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        hwnd = user32.WindowFromPoint(pt)
        while hwnd:
            _send_cancel_mode(hwnd)
            hwnd = user32.GetParent(hwnd)
    except Exception as e:
        logger.info(f"[win32_utils] WindowFromPoint walk failed: {e}")

# EnumWindows 用于枚举所有顶层窗口（跨进程释放捕获）
user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL


def release_all_mouse_capture():
    """最彻底的鼠标捕获释放：枚举系统所有顶层窗口，逐个发送 WM_CANCELMODE。
    覆盖 release_mouse_capture() 遗漏的进程（如桌面 explorer.exe、后台应用）。
    SetCapture 泄漏时，只有捕获者所在线程的窗口能收到鼠标消息，
    必须向该窗口发 WM_CANCELMODE 才能强制 ReleaseCapture。"""
    # 1. 释放当前线程
    try:
        user32.ReleaseCapture()
    except Exception as e:
        logger.info(f"[win32_utils] ReleaseCapture(all) failed: {e}")
    # 2. 枚举所有顶层窗口发 WM_CANCELMODE
    try:
        def _enum_all_cb(hwnd, _lp):
            _send_cancel_mode(hwnd)
            return True
        cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_enum_all_cb)
        user32.EnumWindows(cb, 0)
    except Exception as e:
        logger.info(f"[win32_utils] EnumWindows failed: {e}")
    logger.info("[win32_utils] release_all_mouse_capture done")

WM_CANCELMODE = 0x001F
SMTO_ABORTIFHUNG = 0x0002
_CANCELMODE_TIMEOUT_MS = 200  # SendMessageTimeout 超时：遇到挂起窗口自动跳过，不永久阻塞


def _send_cancel_mode(hwnd):
    """向窗口发送 WM_CANCELMODE（带超时，不永久阻塞）。
    SendMessageW 是同步的，目标窗口无响应时会永久阻塞；
    SendMessageTimeoutW 遇到挂起窗口在超时后返回，保证枚举不卡死。"""
    try:
        result = ctypes.c_ulonglong(0)
        user32.SendMessageTimeoutW(
            hwnd, WM_CANCELMODE, 0, 0,
            SMTO_ABORTIFHUNG, _CANCELMODE_TIMEOUT_MS, ctypes.byref(result)
        )
    except Exception:
        pass


def clear_input_state():
    """强制释放所有可能卡住的鼠标键、键盘修饰键和鼠标捕获。
    使用SendInput（与click_at同一输入栈），确保能释放SendInput按下的键。
    调用release_mouse_capture()处理SetCapture泄漏。"""
    def _send_mouse(flags):
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dwFlags = flags
        inp.union.mi.dx = 0
        inp.union.mi.dy = 0
        inp.union.mi.mouseData = 0
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = None
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    # 0. 先释放鼠标捕获（否则后续消息可能被捕获窗口吃掉）
    release_mouse_capture()
    # 1. 只对实际卡住的鼠标键发 UP（GetAsyncKeyState & 0x8000）。
    # 不能无条件发 RIGHTUP：右键没按时注入 RIGHTUP 会被系统当成真实右键释放，弹出右键菜单。
    _MOUSE_UP = [(0x01, MOUSEEVENTF_LEFTUP), (0x02, MOUSEEVENTF_RIGHTUP)]
    for vk, flags in _MOUSE_UP:
        try:
            if user32.GetAsyncKeyState(vk) & 0x8000:
                _send_mouse(flags)
        except Exception:
            pass
    # 2. 键盘修饰键抬起
    for vk in (0x11, 0x12, 0x10, 0x5B):  # CTRL, ALT, SHIFT, LWIN
        try:
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass
    # 3. 再释放一次捕获（防止UP消息又触发了新的捕获）
    release_mouse_capture()



def get_cursor_pos():
    """获取当前光标位置（屏幕坐标）。"""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


# 虚拟屏幕尺寸缓存（运行时不变，避免每次click_at都调用4次GetSystemMetrics）
_virtual_screen_cache = None

def _get_virtual_screen():
    """获取虚拟屏幕尺寸（带缓存）。返回 (vx, vy, vw, vh)。"""
    global _virtual_screen_cache
    if _virtual_screen_cache is None:
        _virtual_screen_cache = (
            user32.GetSystemMetrics(76),  # SM_XVIRTUALSCREEN
            user32.GetSystemMetrics(77),  # SM_YVIRTUALSCREEN
            user32.GetSystemMetrics(78),  # SM_CXVIRTUALSCREEN
            user32.GetSystemMetrics(79),  # SM_CYVIRTUALSCREEN
        )
    return _virtual_screen_cache


def click_at(x, y):
    """稳定点击：分两步——先MOVE到目标坐标，等待5ms让位置稳定，再LEFTDOWN+LEFTUP。
    根源修复：原实现SendInput数组内MOVE和LEFTDOWN连续，鼠标移动后无时间稳定，
    导致偶尔点歪。拆成两步后，MOVE和CLICK之间有5ms间隔，确保位置稳定后再点击。
    性能优化：虚拟屏幕尺寸缓存，避免每次4次GetSystemMetrics。"""
    x, y = int(x), int(y)
    # 绝对坐标映射到虚拟屏幕(0-65535)，使用缓存避免重复GetSystemMetrics
    vx, vy, vw, vh = _get_virtual_screen()
    nx = int((x - vx) * 65535 / max(1, vw - 1))
    ny = int((y - vy) * 65535 / max(1, vh - 1))

    # 第一步：MOVE到目标坐标
    move_input = (INPUT * 1)()
    move_input[0].type = INPUT_MOUSE
    move_input[0].union.mi.dx = nx
    move_input[0].union.mi.dy = ny
    move_input[0].union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    move_input[0].union.mi.mouseData = 0
    move_input[0].union.mi.time = 0
    move_input[0].union.mi.dwExtraInfo = None
    user32.SendInput(1, move_input, ctypes.sizeof(INPUT))

    # 等待5ms让鼠标位置稳定
    time.sleep(0.005)

    # 第二步：LEFTDOWN → 等待10ms → LEFTUP
    down = (INPUT * 1)()
    down[0].type = INPUT_MOUSE
    down[0].union.mi.dx = 0
    down[0].union.mi.dy = 0
    down[0].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    down[0].union.mi.mouseData = 0
    down[0].union.mi.time = 0
    down[0].union.mi.dwExtraInfo = None
    user32.SendInput(1, down, ctypes.sizeof(INPUT))

    time.sleep(0.010)  # 按住10ms

    up = (INPUT * 1)()
    up[0].type = INPUT_MOUSE
    up[0].union.mi.dx = 0
    up[0].union.mi.dy = 0
    up[0].union.mi.dwFlags = MOUSEEVENTF_LEFTUP
    up[0].union.mi.mouseData = 0
    up[0].union.mi.time = 0
    up[0].union.mi.dwExtraInfo = None
    user32.SendInput(1, up, ctypes.sizeof(INPUT))


def move_mouse_to(x, y):
    """只移动鼠标到目标位置（不点击）。用于esc后游戏把鼠标拉回中心时，先移到目标位置。"""
    x, y = int(x), int(y)
    vx, vy, vw, vh = _get_virtual_screen()
    nx = int((x - vx) * 65535 / max(1, vw - 1))
    ny = int((y - vy) * 65535 / max(1, vh - 1))
    inp = (INPUT * 1)()
    inp[0].type = INPUT_MOUSE
    inp[0].union.mi.dx = nx
    inp[0].union.mi.dy = ny
    inp[0].union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    inp[0].union.mi.mouseData = 0
    inp[0].union.mi.time = 0
    inp[0].union.mi.dwExtraInfo = None
    user32.SendInput(1, inp, ctypes.sizeof(INPUT))


def set_click_through(hwnd, enabled):
    """启用/禁用鼠标穿透（保留工具窗口样式）。
    返回 True 成功，False 失败（打印错误信息）。"""
    if not hwnd:
        logger.info(f"[win32_utils] set_click_through: hwnd invalid (enabled={enabled})")
        return False
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex_style == 0:
        err = kernel32.GetLastError()
        logger.info(f"[win32_utils] GetWindowLongW returned 0, hwnd={hwnd}, GetLastError={err}")
        return False
    ex_style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
    if enabled:
        ex_style |= WS_EX_TRANSPARENT
    else:
        ex_style &= ~WS_EX_TRANSPARENT
    ret = user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
    if ret == 0:
        err = kernel32.GetLastError()
        logger.info(f"[win32_utils] SetWindowLongW failed, hwnd={hwnd}, enabled={enabled}, GetLastError={err}")
        return False
    return True




def send_mouse_input(dy):
    """模拟鼠标相对移动。dy: 上移负值，下移正值。
    SendInput插入的鼠标事件会被Raw Input捕获，使游戏和角度仪同步。
    返回True成功，False失败（打印日志）。"""
    try:
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = 0
        inp.union.mi.dy = dy
        inp.union.mi.dwFlags = MOUSEEVENTF_MOVE
        inp.union.mi.mouseData = 0
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = None
        ret = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if ret == 0:
            logger.info(f"[win32_utils] SendInput failed, dy={dy}, GetLastError={kernel32.GetLastError()}")
            return False
        return True
    except Exception as e:
        logger.info(f"[win32_utils] SendInput exception: {e}")
        return False


# SendMessageTimeoutW：带超时的窗口消息发送，遇到挂起窗口不永久阻塞
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_ulonglong)
]
user32.SendMessageTimeoutW.restype = ctypes.c_ulonglong

# 键名 → 虚拟键码（VK）：全局按键状态查询与按键注入的唯一来源。
#
# 为什么集中在这里：squad_macro（按键注入查码）和 angle_meter_tab（按住检测查码）
# 曾经各维护一份（31 + 5 + 23 项，重叠 18 项）。同一功能两种实现 = 改一处漏一处，
# 历史上「热键键名格式变更后使用方没同步」就是这么出的 bug。新增键名只改这里。
KEY_NAME_VK = {
    # 鼠标键
    "mouse_left": 0x01, "mouse_right": 0x02, "mouse_middle": 0x04,
    "mouse_xbutton1": 0x05, "mouse_xbutton2": 0x06,
    # 修饰键
    "shift": 0x10, "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12,
    # 编辑 / 导航
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D,
    "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "home": 0x24, "end": 0x23,
    "insert": 0x2D, "delete": 0x2E, "left": 0x25,
    "up": 0x26, "right": 0x27, "down": 0x28,
    "page up": 0x21, "page down": 0x22,
    # 锁定键
    "num lock": 0x90, "caps lock": 0x14,
    # 功能键
    "f1": 0x70, "f2": 0x71, "f3": 0x72,
    "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78,
    "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
