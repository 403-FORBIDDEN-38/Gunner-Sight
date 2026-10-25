from core.logger import logger

"""
吉祥物控件：单图Q弹缩放 + 拖动 + 点击信号。
只用M38.png一张图，QPropertyAnimation动画char_label.geometry实现Q弹。
SCALE_X=1.12 / SCALE_Y=0.80，底边中心固定，220ms cubic-bezier(.34,1.56,.64,1)。
事件由widget自身处理，char_label设WA_TransparentForMouseEvents穿透。
"""
import os
from gui.mascot.paths import get_mascot_dir
import time

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QWidget

# 资源文件名常量
CHAR_IMAGE = "M38.png"


def cubic_bezier_easing(x1: float, y1: float, x2: float, y2: float):
    """返回CSS cubic-bezier缓动函数，用于QEasingCurve.setCustomType。"""
    def bezier_x(t):
        return 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3

    def bezier_y(t):
        return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3

    def easing(progress):
        t = progress
        for _ in range(8):
            x = bezier_x(t)
            dx = 3 * (1 - t) ** 2 * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t ** 2 * (1 - x2)
            if abs(dx) < 1e-6:
                break
            t -= (x - progress) / dx
            t = max(0.0, min(1.0, t))
        return bezier_y(t)

    return easing


class MascotWidget(QWidget):
    """M38吉祥物 - 单图Q弹缩放 + 可拖动 + 点击信号"""

    clicked = pyqtSignal()
    pressed = pyqtSignal()
    released = pyqtSignal()

    # Q弹参数
    SCALE_X_PRESS = 1.12
    SCALE_Y_PRESS = 0.80
    ANIM_DURATION = 220  # ms
    CHAR_SIZE = 150

    def __init__(self, resources_dir: str, parent=None):
        super().__init__(parent)
        self.mascot_dir = get_mascot_dir(resources_dir)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.CHAR_SIZE + 20, self.CHAR_SIZE)
        self.setCursor(Qt.OpenHandCursor)

        # char_label原始geometry（常量，底边中心固定参考）
        self.LABEL_ORIGIN = QRect(10, 0, self.CHAR_SIZE, self.CHAR_SIZE)

        # 角色标签（穿透鼠标事件，由widget处理）
        self.char_label = QLabel(self)
        self.char_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.char_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.char_label.setGeometry(self.LABEL_ORIGIN)
        self.char_label.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        self.char_label.setScaledContents(True)
        self.char_label.setPixmap(self._load_png(os.path.join(self.mascot_dir, CHAR_IMAGE)))

        # 拖动状态
        self._dragging = False
        self._drag_offset = QPoint()
        self._drag_moved = False

        # Q弹几何动画
        self._anim = QPropertyAnimation(self.char_label, b"geometry")
        self._anim.setDuration(self.ANIM_DURATION)
        curve = QEasingCurve()
        curve.setCustomType(cubic_bezier_easing(0.34, 1.56, 0.64, 1.0))
        self._anim.setEasingCurve(curve)

    def _load_png(self, filepath):
        """加载PNG，PIL裁剪透明边，底部对齐到CHAR_SIZE画布。"""
        try:
            from PIL import Image as PILImage
            img = PILImage.open(filepath).convert('RGBA')
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            img.thumbnail((self.CHAR_SIZE, self.CHAR_SIZE), PILImage.LANCZOS)
            canvas = PILImage.new('RGBA', (self.CHAR_SIZE, self.CHAR_SIZE), (0, 0, 0, 0))
            canvas.paste(img, ((self.CHAR_SIZE - img.width) // 2, self.CHAR_SIZE - img.height), img)
            data = canvas.tobytes('raw', 'RGBA')
            qimg = QImage(data, self.CHAR_SIZE, self.CHAR_SIZE, self.CHAR_SIZE * 4, QImage.Format_RGBA8888)
            return QPixmap.fromImage(qimg)
        except Exception as e:
            logger.info(f"[mascot] 加载图片失败 {filepath}: {e}")
            return QPixmap()

    def _squished_label_geometry(self, scale_x: float, scale_y: float) -> QRect:
        """计算char_label缩放后的geometry，底边中心固定。"""
        base = self.LABEL_ORIGIN
        cx = base.x() + base.width() / 2
        bottom = base.y() + base.height()
        new_w = int(base.width() * scale_x)
        new_h = int(base.height() * scale_y)
        new_x = int(cx - new_w / 2)
        new_y = int(bottom - new_h)
        return QRect(new_x, new_y, new_w, new_h)

    def _animate_to(self, scale_x: float, scale_y: float):
        """动画char_label缩放到指定比例，底边中心固定。"""
        target = self._squished_label_geometry(scale_x, scale_y)
        self._anim.stop()
        self._anim.setStartValue(self.char_label.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_moved = False
            self._drag_offset = event.pos()
            self.grabMouse()
            self.setCursor(Qt.ClosedHandCursor)
            # 根源优化：高频点击时动画不频繁重启。如果距离上次按压 < 100ms，保持当前动画状态。
            now = time.monotonic() * 1000
            if not hasattr(self, '_last_press_time') or now - self._last_press_time >= 100:
                self._animate_to(self.SCALE_X_PRESS, self.SCALE_Y_PRESS)
            self._last_press_time = now
            self.pressed.emit()

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            delta = event.pos() - self._drag_offset
            if abs(delta.x()) > 3 or abs(delta.y()) > 3:
                self._drag_moved = True
            new_pos = self.pos() + delta
            parent = self.parent()
            if parent:
                new_pos.setX(max(0, min(new_pos.x(), parent.width() - self.width())))
                new_pos.setY(max(0, min(new_pos.y(), parent.height() - self.height())))
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.releaseMouse()
            self.setCursor(Qt.OpenHandCursor)
            self._animate_to(1.0, 1.0)
            self.released.emit()
            if not self._drag_moved:
                self.clicked.emit()

    def shutdown(self):
        """显式停止动画（退出/清理路径调用，幂等）。"""
        self._stop_animation()

    def _stop_animation(self):
        try:
            self._anim.stop()
        except RuntimeError:
            # C++ 对象已删除：窗口销毁级联中 hideEvent 可能晚于子对象销毁
            pass

    def hideEvent(self, event):
        self._stop_animation()
        super().hideEvent(event)
