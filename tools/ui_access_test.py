# -*- coding: utf-8 -*-
"""
UIAccess 测试 v4：极简版
- 创建隐藏窗口 → 延迟3秒 → ShowWindowNoActivate
- 一次性 SetWindowPos(TOPMOST)，之后**完全不调** SetWindowPos
- sleep 循环里只 InvalidateRect 重绘
- 日志写到 %TEMP%
"""
import ctypes
import time
import os

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
SWP_NOMOVE = 0x0001
SWP_NOSIZE = 0x0002
SWP_NOACTIVATE = 0x0010

WM_ACTIVATE = 0x0006
WM_MOUSEACTIVATE = 0x0021
WM_SETFOCUS = 0x0007
WM_ACTIVATEAPP = 0x001C
WM_NCACTIVATE = 0x0086
WM_PAINT = 0x000F
MA_NOACTIVATE = 3

LOG_FILE = os.path.join(os.environ.get("TEMP", "."), "uiaccess_msg_log.txt")

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t)

focus_msgs = []

def wnd_proc(hwnd, msg, wparam, lparam):
    if msg in (WM_ACTIVATE, WM_MOUSEACTIVATE, WM_SETFOCUS, WM_ACTIVATEAPP, WM_NCACTIVATE):
        focus_msgs.append(f"0x{msg:04X} wp={wparam} lp={lparam}")

    if msg == WM_PAINT:
        ps = ctypes.c_ulong()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        brush = gdi32.CreateSolidBrush(0x000000FF)
        user32.FillRect(hdc, ctypes.byref(RECT(0, 0, 300, 300)), brush)
        white = gdi32.CreateSolidBrush(0x00FFFFFF)
        user32.FillRect(hdc, ctypes.byref(RECT(140, 50, 160, 250)), white)
        user32.FillRect(hdc, ctypes.byref(RECT(50, 140, 250, 160)), white)
        gdi32.DeleteObject(brush)
        gdi32.DeleteObject(white)
        user32.EndPaint(hwnd, ctypes.byref(ps))
        return 0

    if msg == WM_MOUSEACTIVATE:
        return MA_NOACTIVATE
    if msg == WM_NCACTIVATE:
        return 1
    if msg in (WM_ACTIVATE, WM_SETFOCUS, WM_ACTIVATEAPP):
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

wnd_proc_cb = WNDPROC(wnd_proc)

class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p), ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p), ("lpszClassName", ctypes.c_wchar_p),
    ]

red_brush = gdi32.CreateSolidBrush(0x000000FF)
wc = WNDCLASS(0, ctypes.cast(wnd_proc_cb, ctypes.c_void_p), 0, 0, 0, None, None, red_brush, None, "UIAccessV4")
user32.RegisterClassW(ctypes.byref(wc))

sw = user32.GetSystemMetrics(0)
sh = user32.GetSystemMetrics(1)
x = sw // 2 - 150
y = sh // 2 - 150

# 创建隐藏窗口
hwnd = user32.CreateWindowExW(
    WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
    "UIAccessV4", "test",
    WS_POPUP,
    x, y, 300, 300,
    0, 0, 0, None
)

# 延迟 3 秒
time.sleep(3)

# 显示（不激活）
user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
# 一次性设置 TOPMOST，之后再也不调 SetWindowPos
user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
user32.InvalidateRect(hwnd, None, True)
user32.UpdateWindow(hwnd)

fg_before = user32.GetForegroundWindow()

# 循环 27 秒，只重绘，不调 SetWindowPos
for i in range(27):
    time.sleep(1)
    user32.InvalidateRect(hwnd, None, False)
    user32.UpdateWindow(hwnd)
    if i % 5 == 0:
        fg_now = user32.GetForegroundWindow()
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{i}s] fg={fg_now} focus_msgs={len(focus_msgs)}\n")
        except:
            pass

fg_after = user32.GetForegroundWindow()

# 写日志
try:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\nfg_before={fg_before} fg_after={fg_after}\n")
        f.write(f"焦点消息共 {len(focus_msgs)} 条:\n")
        for m in focus_msgs:
            f.write(f"  {m}\n")
except:
    pass

user32.DestroyWindow(hwnd)
gdi32.DeleteObject(red_brush)
