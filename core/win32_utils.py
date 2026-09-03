"""
Win32 窗口工具函数
"""
import ctypes

_user32 = ctypes.windll.user32
user32 = _user32  # T3: 公共导出，所有模块统一从此处导入，禁止各自 ctypes.windll.user32 / WinDLL

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
