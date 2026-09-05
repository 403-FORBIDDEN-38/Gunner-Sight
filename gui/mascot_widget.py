"""
M38 摆件 - 帧动画(按下/按住/松开) + 可拖动
纯净版：无对话框、无语音、无事件触发
动效实现与 mascot_debug.py 一致
"""
import os
from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QPixmap, QImage


class MascotWidget(QWidget):
    """M38 摆件 - 点击动画 + 可拖动"""

    def __init__(self, resources_dir, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.mascot_dir = os.path.join(resources_dir, "mascot")

        self.char_size = 150
        self.setFixedSize(self.char_size + 20, self.char_size)

        # 加载素材
        self.idle_pix = self._load_static(os.path.join(self.mascot_dir, "M38.png"))
        self.hold_pix = self._load_static(os.path.join(self.mascot_dir, "hold.png"))
        self.press_frames = self._load_gif(os.path.join(self.mascot_dir, "press.gif"))
        self.release_frames = self._load_gif(os.path.join(self.mascot_dir, "release.gif"))

        # 角色标签
        self.char_label = QLabel(self)
        self.char_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.char_label.setFixedSize(self.char_size, self.char_size)
        self.char_label.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        self.char_label.setPixmap(self.idle_pix)
        self.char_label.move(10, 0)
        self.char_label.setCursor(Qt.OpenHandCursor)
        self.char_label.mousePressEvent = self._on_press
        self.char_label.mouseMoveEvent = self._on_move
        self.char_label.mouseReleaseEvent = self._on_release

        # 拖动
        self._dragging = False
        self._drag_offset = QPoint()
        self._drag_moved = False

        # 动画
        self._state = "idle"
        self._frame_idx = 0
        self._cur_frames = []
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._next_frame)

    # --- 图像处理（与 mascot_debug.py 一致） ---
    def _load_static(self, filepath):
        from PIL import Image as PILImage
        try:
            img = PILImage.open(filepath).convert('RGBA')
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            img.thumbnail((self.char_size, self.char_size), PILImage.LANCZOS)
            canvas = PILImage.new('RGBA', (self.char_size, self.char_size), (0, 0, 0, 0))
            canvas.paste(img, ((self.char_size - img.width) // 2, self.char_size - img.height), img)
            data = canvas.tobytes('raw', 'RGBA')
            qimg = QImage(data, self.char_size, self.char_size, self.char_size * 4, QImage.Format_RGBA8888)
            return QPixmap.fromImage(qimg)
        except Exception:
            return QPixmap()

    def _load_gif(self, filepath, interp=3):
        from PIL import Image as PILImage
        def clean(img):
            r, g, b, a = img.split()
            zero = PILImage.new('L', img.size, 0)
            r = PILImage.composite(r, zero, a)
            g = PILImage.composite(g, zero, a)
            b = PILImage.composite(b, zero, a)
            return PILImage.merge('RGBA', (r, g, b, a))
        try:
            img = PILImage.open(filepath)
        except Exception:
            return []
        raw = []
        for i in range(getattr(img, 'n_frames', 1)):
            img.seek(i)
            frame = clean(img.convert('RGBA'))
            bbox = frame.getbbox()
            if bbox:
                frame = frame.crop(bbox)
            raw.append(frame)
        if not raw:
            return []
        max_w = max(f.width for f in raw)
        max_h = max(f.height for f in raw)
        normalized = []
        for f in raw:
            canvas = PILImage.new('RGBA', (max_w, max_h), (0, 0, 0, 0))
            canvas.paste(f, ((max_w - f.width) // 2, max_h - f.height), f)
            normalized.append(canvas)
        frames = []
        for i in range(len(normalized)):
            frames.append(normalized[i])
            if i < len(normalized) - 1:
                for j in range(1, interp + 1):
                    blended = PILImage.blend(normalized[i], normalized[i + 1], j / (interp + 1))
                    frames.append(clean(blended))
        result = []
        for f in frames:
            f.thumbnail((self.char_size, self.char_size), PILImage.LANCZOS)
            canvas = PILImage.new('RGBA', (self.char_size, self.char_size), (0, 0, 0, 0))
            canvas.paste(f, ((self.char_size - f.width) // 2, self.char_size - f.height), f)
            data = canvas.tobytes('raw', 'RGBA')
            qimg = QImage(data, self.char_size, self.char_size, self.char_size * 4, QImage.Format_RGBA8888)
            result.append(QPixmap.fromImage(qimg))
        return result

    # --- 动画控制 ---
    def _on_press(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_moved = False
            self._drag_offset = event.pos()
            self.char_label.grabMouse()
            self.char_label.setCursor(Qt.ClosedHandCursor)
            self._state = "pressing"
            self._cur_frames = self.press_frames
            self._frame_idx = 0
            if self._cur_frames:
                self.char_label.setPixmap(self._cur_frames[0])
                self._timer.start(8)

    def _on_move(self, event):
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

    def _on_release(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.char_label.releaseMouse()
            self.char_label.setCursor(Qt.OpenHandCursor)
            if self._state in ("pressing", "holding"):
                self._state = "releasing"
                self._timer.stop()
                self._cur_frames = self.release_frames
                self._frame_idx = 0
                if self._cur_frames:
                    self.char_label.setPixmap(self._cur_frames[0])
                    self._timer.start(8)

    def hideEvent(self, event):
        """隐藏时停止动画定时器，避免后台空转"""
        self._timer.stop()
        super().hideEvent(event)

    def _next_frame(self):
        self._frame_idx += 1
        if self._frame_idx >= len(self._cur_frames):
            self._timer.stop()
            if self._state == "pressing":
                self._state = "holding"
                self.char_label.setPixmap(self.hold_pix)
            elif self._state == "releasing":
                self._state = "idle"
                self.char_label.setPixmap(self.idle_pix)
            return
        self.char_label.setPixmap(self._cur_frames[self._frame_idx])
