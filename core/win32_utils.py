"""
Win32 窗口工具函数
"""
import ctypes

_user32 = ctypes.windll.user32
user32 = _user32  # 公共导出，所有模块统一从此处导入，禁止各自 ctypes.windll.user32 / WinDLL

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


def apply_click_through(hwnd):
    """为窗口设置鼠标穿透 + 工具窗口 + 不激活样式（不在任务栏显示）"""
    if not hwnd:
        return
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)


def set_click_through(hwnd, enabled):
    """启用/禁用鼠标穿透（保留工具窗口样式）"""
    if not hwnd:
        return
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex_style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
    if enabled:
        ex_style |= WS_EX_TRANSPARENT
    else:
        ex_style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)


# 统一DLL导出（所有模块禁止各自 ctypes.windll.xxx）
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32


# SendInput 结构（模拟真实鼠标相对移动）
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT_UNION)]

_MOUSEEVENTF_MOVE = 0x0001
_INPUT_MOUSE = 0


def send_mouse_input(dy):
    """模拟鼠标相对移动。dy: 上移负值，下移正值。
    SendInput插入的鼠标事件会被Raw Input捕获，使游戏和角度仪同步。
    返回True成功，False失败（打印日志）。"""
    try:
        inp = _INPUT()
        inp.type = _INPUT_MOUSE
        inp.mi.dx = 0
        inp.mi.dy = dy
        inp.mi.dwFlags = _MOUSEEVENTF_MOVE
        ret = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        if ret == 0:
            print(f"[win32_utils] SendInput失败, dy={dy}, GetLastError={kernel32.GetLastError()}")
            return False
        return True
    except Exception as e:
        print(f"[win32_utils] SendInput异常: {e}")
        return False
