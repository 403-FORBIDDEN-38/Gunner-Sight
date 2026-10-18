from core.logger import logger

"""Overlay统一基类 - 封装点击穿透逻辑，消除各overlay不一致实现。


1. 穿透恢复带验证（GetWindowLongW检查WS_EX_TRANSPARENT）+ 重试（最多3次，间隔10ms）
2. setAttribute重写：修改WA_TransparentForMouseEvents后恢复穿透
3. 所有窗口样式方法添加延迟确认（QTimer.singleShot 10ms）
4. 失败显式报错，不再静默
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget

from core.win32_utils import GWL_EXSTYLE, WS_EX_TRANSPARENT, set_click_through, user32


class ClickThroughOverlay(QWidget):
    """所有overlay窗口的统一基类。"""

    EDIT_TIMEOUT_MS = 30000  # 编辑模式30秒无操作自动退出
    MAX_RETRY = 3  # 穿透恢复最大重试次数
    RETRY_DELAY_MS = 10  # 重试间隔

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self._retry_count = 0
        self._applying_click_through = False  # 防止setAttribute递归

        # 编辑模式超时定时器（兜底）
        self._edit_timeout_timer = QTimer(self)
        self._edit_timeout_timer.setSingleShot(True)
        self._edit_timeout_timer.timeout.connect(self._on_edit_timeout)

        # 窗口基础设置（必须在__init__中设置，否则WA_TranslucentBackground不生效导致全黑窗口）
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

    def _verify_click_through(self) -> bool:
        """验证Win32穿透是否已设置（检查WS_EX_TRANSPARENT标志）"""
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return False
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if self._edit_mode:
                # 编辑模式：不应有WS_EX_TRANSPARENT
                return not (ex_style & WS_EX_TRANSPARENT)
            else:
                # 非编辑模式：应有WS_EX_TRANSPARENT
                return bool(ex_style & WS_EX_TRANSPARENT)
        except Exception:
            return False

    def _apply_click_through(self):
        """应用Win32鼠标穿透 + Qt层穿透 + 验证 + 重试（编辑模式时禁用穿透）"""
        # winId有效性检查：窗口未完全创建时winId可能为0，直接调用Win32 API会segfault（Nuitka高发）
        try:
            hwnd = int(self.winId())
        except Exception:
            hwnd = 0
        if not hwnd:
            self._retry_count += 1
            if self._retry_count <= self.MAX_RETRY:
                QTimer.singleShot(self.RETRY_DELAY_MS, self._apply_click_through)
            else:
                logger.info(f"[OverlayBase] winId无效，放弃穿透（重试{self.MAX_RETRY}次）")
                self._retry_count = 0
            return
        # 同步Qt层WA_TransparentForMouseEvents（窗口重建后会丢失）
        # 用标志位防止setAttribute重写触发递归
        self._applying_click_through = True
        try:
            super().setAttribute(Qt.WA_TransparentForMouseEvents, not self._edit_mode)
        finally:
            self._applying_click_through = False
        try:
            success = set_click_through(hwnd, not self._edit_mode)
        except Exception as e:
            logger.info(f"[OverlayBase] apply click-through exception: {e}")
            success = False

        if success and self._verify_click_through():
            self._retry_count = 0
            return

        # 验证失败，延迟重试
        self._retry_count += 1
        if self._retry_count <= self.MAX_RETRY:
            QTimer.singleShot(self.RETRY_DELAY_MS, self._apply_click_through)
        else:
            logger.info(f"[OverlayBase] click-through verify FAILED after {self.MAX_RETRY} retries, edit_mode={self._edit_mode}")
            self._retry_count = 0

    def ensure_click_through(self):
        """公共方法：强制重新应用穿透（窗口样式变更后调用）"""
        self._retry_count = 0
        self._apply_click_through()

    def setWindowOpacity(self, opacity):
        """重写：设置透明度后自动重新应用穿透（Windows上改透明度可能清除WS_EX_TRANSPARENT）"""
        super().setWindowOpacity(opacity)
        self.ensure_click_through()
        # 延迟确认：窗口重建后winId可能变化
        QTimer.singleShot(self.RETRY_DELAY_MS, self._apply_click_through)

    def setWindowFlags(self, flags):
        """重写：设置窗口标志后自动重新应用穿透"""
        super().setWindowFlags(flags)
        self.ensure_click_through()
        QTimer.singleShot(self.RETRY_DELAY_MS, self._apply_click_through)

    def setAttribute(self, attribute, on=True):
        """重写：修改WA_TransparentForMouseEvents后恢复Win32穿透"""
        super().setAttribute(attribute, on)
        if attribute == Qt.WA_TransparentForMouseEvents and not self._applying_click_through:
            # Qt层穿透状态变化（非_apply_click_through内部调用），同步Win32层
            self.ensure_click_through()

    def showEvent(self, event):
        """showEvent无条件恢复穿透（根治：不检查edit_mode）"""
        super().showEvent(event)
        self.ensure_click_through()
        QTimer.singleShot(self.RETRY_DELAY_MS, self._apply_click_through)

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


def make_wheel_overlay_window(w):
    """给滚轮三个 overlay（MagOverlay/CompactOverlay/FullOverlay）统一设置窗口属性。

    这三个类的 __init__ 开头原本各有逐字相同的 4 行，抽成工厂避免重复。
    注意：不要改成继承 ClickThroughOverlay——那套是"可编辑+点击穿透"机制，
    与滚轮窗口用途不同，继承会把无关机关带进来。
    """
    w.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    w.setAttribute(Qt.WA_TranslucentBackground)
    w.setAttribute(Qt.WA_ShowWithoutActivating)
    w.setAttribute(Qt.WA_TransparentForMouseEvents)
