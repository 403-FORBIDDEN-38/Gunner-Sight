"""Overlay统一基类 - 封装点击穿透逻辑，消除各overlay不一致实现。

保证：
1. __init__同时设置Qt穿透 + Win32穿透（双保险）
2. showEvent无条件恢复穿透（不检查edit_mode）
3. hideEvent重置编辑模式为False
4. 编辑模式统一实现：进入关穿透，退出开穿透
5. 编辑模式ESC键退出 + 30秒超时自动退出（兜底）
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer

from core.win32_utils import set_click_through


class ClickThroughOverlay(QWidget):
    """所有overlay窗口的统一基类。"""

    EDIT_TIMEOUT_MS = 30000  # 编辑模式30秒无操作自动退出

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False

        # 编辑模式超时定时器（兜底）
        self._edit_timeout_timer = QTimer(self)
        self._edit_timeout_timer.setSingleShot(True)
        self._edit_timeout_timer.timeout.connect(self._on_edit_timeout)

        # 窗口基础设置（子类可在__init__后覆盖setWindowFlags）
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # 延迟应用Win32穿透（窗口创建后winId才有效）
        QTimer.singleShot(0, self._apply_click_through)

    def _apply_click_through(self):
        """应用Win32鼠标穿透（编辑模式时禁用穿透）"""
        try:
            set_click_through(int(self.winId()), not self._edit_mode)
        except Exception as e:
            print(f"[OverlayBase] 应用穿透失败: {e}")

    def ensure_click_through(self):
        """公共方法：强制重新应用穿透（窗口样式变更后调用）"""
        self._apply_click_through()

    def setWindowOpacity(self, opacity):
        """重写：设置透明度后自动重新应用穿透（Windows上改透明度可能清除WS_EX_TRANSPARENT）"""
        super().setWindowOpacity(opacity)
        self.ensure_click_through()

    def setWindowFlags(self, flags):
        """重写：设置窗口标志后自动重新应用穿透"""
        super().setWindowFlags(flags)
        self.ensure_click_through()

    def showEvent(self, event):
        """showEvent无条件恢复穿透（根治：不检查edit_mode）"""
        super().showEvent(event)
        self._apply_click_through()

    def hideEvent(self, event):
        """hideEvent重置编辑模式（根治：跨hide/show不残留编辑状态）"""
        super().hideEvent(event)
        self._edit_mode = False
        self._edit_timeout_timer.stop()

    def set_edit_mode(self, enabled: bool):
        """统一编辑模式切换：进入关穿透，退出开穿透"""
        self._edit_mode = enabled
        if enabled:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.setCursor(Qt.SizeAllCursor)
            self._edit_timeout_timer.start(self.EDIT_TIMEOUT_MS)
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setCursor(Qt.ArrowCursor)
            self._edit_timeout_timer.stop()
        self._apply_click_through()
        self.update()

    def _on_edit_timeout(self):
        """编辑模式超时自动退出"""
        if self._edit_mode:
            self.set_edit_mode(False)

    def keyPressEvent(self, event):
        """ESC键退出编辑模式"""
        if event.key() == Qt.Key_Escape and self._edit_mode:
            self.set_edit_mode(False)
        else:
            super().keyPressEvent(event)
