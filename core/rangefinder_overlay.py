"""Rangefinder 结果 Overlay - 透明置顶鼠标穿透窗口"""
import ctypes
from core.win32_utils import user32  # T3: 统一 Win32 入口
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont

from core.win32_utils import set_click_through
from core.mouse_hook import MouseHook


class POINT(ctypes.Structure):
    """T5: 模块级 POINT 结构体，避免每次调用时重复定义"""
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RangefinderOverlay(QWidget):
    edit_mode_changed = pyqtSignal(bool)  # T8: 编辑模式变更信号，替代 200ms 轮询

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(300, 80)
        self._pixmap = None
        self._edit_mode = False
        self._drag_pos = None
        self._scaled_cache = None
        self._cache_size = None
        self._mouse_hook_connected = False
        set_click_through(int(self.winId()), True)

    def set_edit_mode(self, enabled):
        self._edit_mode = enabled
        if not enabled:
            self.edit_mode_changed.emit(False)  # T8: 退出编辑模式时发射信号
        if enabled:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.setCursor(Qt.SizeAllCursor)
            # 监听全局鼠标点击，点击 overlay 外区域自动退出编辑模式
            if not self._mouse_hook_connected:
                MouseHook.instance().mouse_down.connect(self._on_global_mouse_down)
                MouseHook.instance().acquire()
                self._mouse_hook_connected = True
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setCursor(Qt.ArrowCursor)
            if self._mouse_hook_connected:
                MouseHook.instance().mouse_down.disconnect(self._on_global_mouse_down)
                MouseHook.instance().release()
                self._mouse_hook_connected = False
        set_click_through(int(self.winId()), not enabled)
        self.update()

    def _on_global_mouse_down(self, button):
        """全局鼠标按下事件：点击 overlay 外区域自动退出编辑模式"""
        if not self._edit_mode or button != "mouse_left":
            return
        # 获取鼠标全局位置
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        # 检查是否在 overlay 窗口几何区域内
        geo = self.frameGeometry()
        if not geo.contains(pt.x, pt.y):
            self.set_edit_mode(False)

    def set_position(self, x, y):
        self.move(int(x), int(y))

    def set_display_size(self, w, h):
        self.setFixedSize(max(50, int(w)), max(30, int(h)))
        self._scaled_cache = None
        self._cache_size = None

    def set_opacity(self, opacity):
        self.setWindowOpacity(max(0.1, min(1.0, opacity)))

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self._scaled_cache = None
        self._cache_size = None
        self.update()

    def clear(self):
        self._pixmap = None
        self.update()

    def showEvent(self, event):
        """19.1: Qt 在 show/update 后可能重置扩展样式，showEvent 中重新设置穿透"""
        super().showEvent(event)
        if not self._edit_mode:
            set_click_through(int(self.winId()), True)

    def paintEvent(self, event):
        p = QPainter(self)
        if self._edit_mode:
            p.fillRect(self.rect(), QColor(100, 100, 100, 60))
            p.setPen(QPen(QColor(255, 255, 0), 2, Qt.DashLine))
            p.drawRect(self.rect().adjusted(1, 1, -1, -1))
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont("Arial", 9))
            p.drawText(self.rect(), Qt.AlignCenter, "拖动移动 / 滚轮缩放 / 点击外部退出")
        elif self._pixmap:
            cur_size = (self.width(), self.height())
            if self._scaled_cache is None or self._cache_size != cur_size:
                self._scaled_cache = self._pixmap.scaled(
                    self.width(), self.height(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._cache_size = cur_size
            scaled = self._scaled_cache
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)

    def mousePressEvent(self, e):
        if self._edit_mode and e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._edit_mode and self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def wheelEvent(self, e):
        if self._edit_mode:
            d = e.angleDelta().y() // 120
            self.setFixedSize(max(50, self.width() + d * 20),
                              max(30, self.height() + d * 10))

    def mouseDoubleClickEvent(self, e):
        if self._edit_mode:
            self.set_edit_mode(False)
