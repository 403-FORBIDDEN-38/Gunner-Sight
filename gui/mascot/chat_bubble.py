from core.logger import logger

"""
聊天气泡：三明治层级 + 气泡尾巴 + 内容随机抓取。
层级（从底到顶）：尾巴 → 气泡底 → 内容（alpha剪切蒙版） → 气泡框。
内容从 resources/assets/mascot/content/ 随机抓取（gif/txt/图片/音频），文件名支持-数字概率权重。
shake用相对偏移pyqtProperty叠加在跟随位置上，不与QTimer跟随冲突。
"""
import os
from gui.mascot.paths import get_mascot_dir
import random

from PyQt5.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    QUrl,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import QBitmap, QFont, QFontDatabase, QImage, QMovie, QPixmap
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

# 资源文件名常量
TAIL_IMAGE = "气泡尾巴.png"
BOTTOM_IMAGE = "气泡底.png"
FRAME_IMAGE = "气泡框.png"
FONT_FILE = "乐米小熊日记体.ttf"

# 定稿布局参数（不暴露DIY）
BUBBLE_LAYOUT = {
    "bubble_w": 200,
    "bubble_h": 130,
    "tail_w": 70,
    "tail_h": 60,
    "tail_offset_x": -24,
    "tail_overlap": 12,
    "bubble_offset_x": -52,
    "bubble_offset_y": 99,
    "content_w": 190,
    "content_h": 120,
}


class ChatBubble(QWidget):
    visibility_changed = pyqtSignal(bool)  # 气泡显示/隐藏时发射，用于控制外部QTimer

    def __init__(self, resources_dir: str, parent=None):
        super().__init__(parent)
        self.mascot_dir = get_mascot_dir(resources_dir)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.layout = dict(BUBBLE_LAYOUT)
        self._recompute_geometry()

        self._tail_label = QLabel(self)
        self._tail_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self._tail_label.setAlignment(Qt.AlignCenter)

        self._bottom_label = QLabel(self)
        self._bottom_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self._bottom_label.setAlignment(Qt.AlignCenter)

        self._content_label = QLabel(self)
        self._content_label.setObjectName("mascot_content")
        self._content_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self._content_label.setAlignment(Qt.AlignCenter)
        self._movie = None

        self._frame_label = QLabel(self)
        self._frame_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self._frame_label.setAlignment(Qt.AlignCenter)

        self._apply_layout_to_labels()

        # 子widget的windowOpacity无效，用QGraphicsOpacityEffect实现淡入淡出
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._fade_out)
        self._persistent = False
        self._last_anchor = None
        self._last_content_file = None  # 记录上次内容文件，避免连续重复
        self._content_dir = os.path.join(self.mascot_dir, "content")

        # shake相对偏移
        self._shake_anim = None
        self._shake_offset_val = 0.0

        # 字体加载（根源修复：确保mascot目录中的字体生效，并在样式表中也指定）
        self._font_family = "Microsoft YaHei"
        font_path = os.path.join(self.mascot_dir, FONT_FILE)
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    self._font_family = families[0]
                    logger.info(f"[mascot] 对话字体加载成功: {self._font_family}")
                else:
                    logger.info("[mascot] 字体加载失败: families为空")
            else:
                logger.info(f"[mascot] 字体加载失败: font_id={font_id}")
        else:
            logger.info(f"[mascot] 字体文件不存在: {font_path}")

        # 音频播放器（content中的音频文件）
        self._audio_player = QMediaPlayer()
        self._audio_player.setVolume(10)
        self.hide()

    # shake相对偏移属性
    def _get_shake_offset(self):
        return self._shake_offset_val

    def _set_shake_offset(self, val):
        self._shake_offset_val = val
        if self._last_anchor and self.isVisible():
            self._position_to(*self._last_anchor)

    shake_offset = pyqtProperty(float, _get_shake_offset, _set_shake_offset)

    def _recompute_geometry(self):
        L = self.layout
        self._bubble_w = L["bubble_w"]
        self._bubble_h = L["bubble_h"]
        self._tail_w = L["tail_w"]
        self._tail_h = L["tail_h"]
        self._total_h = self._bubble_h + self._tail_h - L["tail_overlap"]
        self._total_w = max(self._bubble_w, self._tail_w + abs(L["tail_offset_x"]))
        self.setFixedSize(self._total_w, self._total_h)
        self._bubble_x = (self._total_w - self._bubble_w) // 2
        self._tail_x = (self._total_w - self._tail_w) // 2 + L["tail_offset_x"]
        self._tail_y = self._bubble_h - L["tail_overlap"]
        self._content_size = QSize(L["content_w"], L["content_h"])

    def _content_geometry(self):
        cx = self._bubble_x + (self._bubble_w - self._content_size.width()) // 2
        cy = (self._bubble_h - self._content_size.height()) // 2
        return cx, cy, self._content_size.width(), self._content_size.height()

    def _apply_layout_to_labels(self):
        self._tail_label.setGeometry(self._tail_x, self._tail_y, self._tail_w, self._tail_h)
        self._tail_label.setPixmap(self._load_scaled(TAIL_IMAGE, self._tail_w, self._tail_h))
        for label in (self._bottom_label, self._frame_label):
            label.setGeometry(self._bubble_x, 0, self._bubble_w, self._bubble_h)
        self._bottom_label.setPixmap(self._load_scaled(BOTTOM_IMAGE, self._bubble_w, self._bubble_h))
        self._frame_label.setPixmap(self._load_scaled(FRAME_IMAGE, self._bubble_w, self._bubble_h))
        cx, cy, cw, ch = self._content_geometry()
        self._content_label.setGeometry(cx, cy, cw, ch)
        if self._movie:
            self._movie.setScaledSize(self._content_size)
        self._apply_clip_mask()

    def _load_scaled(self, filename, w, h):
        path = os.path.join(self.mascot_dir, filename)
        if not os.path.exists(path):
            return QPixmap()
        return QPixmap(path).scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def _apply_clip_mask(self):
        """mask截取气泡底中内容区域的alpha。"""
        path = os.path.join(self.mascot_dir, BOTTOM_IMAGE)
        if not os.path.exists(path):
            return
        img = QImage(path).scaled(self._bubble_w, self._bubble_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        cx, cy, cw, ch = self._content_geometry()
        rel_x = cx - self._bubble_x
        rel_y = cy
        sub = img.copy(rel_x, rel_y, min(cw, img.width() - rel_x), min(ch, img.height() - rel_y))
        self._content_label.setMask(QBitmap.fromImage(sub.createAlphaMask()))

    def set_persistent(self, enabled):
        self._persistent = enabled
        if enabled:
            self._auto_hide_timer.stop()
        elif self.isVisible():
            self._auto_hide_timer.start(random.randint(3000, 5000))

    def _fade_out(self):
        """淡出动画：透明度1→0，结束后hide并重置透明度。"""
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(600)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self._fade_anim.start()

    def _on_fade_finished(self):
        self.hide()
        self._opacity_effect.setOpacity(1.0)

    def set_volume(self, volume):
        self._audio_player.setVolume(int(max(0.0, min(1.0, volume)) * 100))

    def _pick_text_line(self, filepath):
        """从txt读取所有非空行，随机选一行。文件级有概率，行内平等。"""
        try:
            with open(filepath, encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            if lines:
                return random.choice(lines)
        except Exception as e:
            logger.info(f"[mascot] 读取txt失败 {filepath}: {e}")
        return "..."

    def _pick_from_folder(self):
        """从content文件夹随机选文件。文件名-数字=概率，无标注平分剩余。"""
        if not os.path.isdir(self._content_dir):
            return None, None
        files = []
        unweighted = []
        weighted_sum = 0
        for f in os.listdir(self._content_dir):
            ext = os.path.splitext(f)[1].lower()
            full = os.path.join(self._content_dir, f)
            if ext == '.gif':
                ftype = 'gif'
            elif ext == '.txt':
                ftype = 'text'
            elif ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp'):
                ftype = 'image'
            elif ext in ('.mp3', '.wav', '.ogg', '.m4a'):
                ftype = 'audio'
            else:
                continue
            name_no_ext = os.path.splitext(f)[0]
            weight = None
            if '-' in name_no_ext:
                parts = name_no_ext.rsplit('-', 1)
                if parts[-1].isdigit():
                    weight = int(parts[-1])
            if weight is not None:
                files.append((ftype, full, weight))
                weighted_sum += weight
            else:
                unweighted.append((ftype, full))
        remain = max(0, 100 - weighted_sum)
        if unweighted:
            share = remain / len(unweighted)
            for ftype, full in unweighted:
                files.append((ftype, full, share))
        if not files:
            return None, None
        total = sum(w for _, _, w in files)
        if total <= 0:
            return files[0][0], files[0][1]
        r = random.uniform(0, total)
        acc = 0
        for ftype, fpath, w in files:
            acc += w
            if r <= acc:
                return ftype, fpath
        return files[-1][0], files[-1][1]

    def _load_content(self):
        if self._movie:
            self._movie.stop()
            self._movie = None
        self._content_label.clear()
        self._content_label.setWordWrap(False)
        self._content_label.setFont(QFont())

        ftype, fpath = self._pick_from_folder()
        # 不重复上次文件（最多重试3次，单文件时不死循环）
        _retry = 0
        while fpath and fpath == self._last_content_file and _retry < 3:
            ftype, fpath = self._pick_from_folder()
            _retry += 1
        self._last_content_file = fpath
        if ftype == "gif" and fpath:
            self._movie = QMovie(fpath)
            self._movie.setScaledSize(self._content_size)
            self._content_label.setMovie(self._movie)
            self._movie.start()
        elif ftype == "text" and fpath:
            text = self._pick_text_line(fpath)
            # 富文本包裹：line-height 0.75 激进压缩行间距，颜色由全局QSS mascot_content控制
            self._content_label.setText(
                f'<div style="line-height: 0.75; margin: 0;">{text}</div>')
            self._content_label.setWordWrap(True)
            # QSS明确指定字体族+大小，避免被全局QSS覆盖；18pt在190x120气泡内合适
            self._content_label.setStyleSheet(
                f"QLabel {{ font-family: '{self._font_family}'; font-size: 18pt; "
                f"font-weight: bold; padding: 0px; }}")
        elif ftype == "image" and fpath:
            pix = QPixmap(fpath).scaled(
                self._content_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._content_label.setPixmap(pix)
        elif ftype == "audio" and fpath:
            # 根源优化：如果正在播放同一文件，不重启（高频点击时音频不被切碎）
            current_media = self._audio_player.media()
            current_url = current_media.canonicalUrl().toLocalFile() if current_media else ""
            if current_url != fpath or self._audio_player.state() != QMediaPlayer.PlayingState:
                self._audio_player.stop()
                self._audio_player.setMedia(QMediaContent(QUrl.fromLocalFile(fpath)))
                self._audio_player.setVolume(10)  # setMedia会重置音量，必须重设
                self._audio_player.play()
            self._content_label.setText("♪")
            self._content_label.setStyleSheet(
                f"QLabel {{ font-family: '{self._font_family}'; font-size: 48pt; font-weight: bold; }}")

    def _position_to(self, anchor_x, anchor_y):
        L = self.layout
        x = anchor_x - self._total_w // 2 + L["bubble_offset_x"]
        y = anchor_y - self._total_h + L["bubble_offset_y"] + int(self._shake_offset_val)
        parent = self.parent()
        if parent:
            x = max(0, min(x, parent.width() - self._total_w))
            y = max(0, min(y, parent.height() - self._total_h))
        self.move(x, y)

    def show_bubble(self, anchor_x, anchor_y):
        """根源优化：高频点击时不频繁重载内容。
        如果气泡已可见且距离上次加载内容 < 300ms，只刷新位置和自动隐藏计时器，不重载内容。"""
        import time as _time
        self._last_anchor = (anchor_x, anchor_y)
        now = _time.monotonic() * 1000
        need_reload = True
        if hasattr(self, '_last_load_time') and self.isVisible():
            if now - self._last_load_time < 300:
                need_reload = False
        if need_reload:
            self._load_content()
            self._last_load_time = now
        self._position_to(anchor_x, anchor_y)
        self.setWindowOpacity(1.0)
        self.show()
        self.visibility_changed.emit(True)
        if not self._persistent:
            self._auto_hide_timer.start(random.randint(3000, 5000))

    def update_position(self, anchor_x, anchor_y):
        """只更新位置，不重载内容（QTimer跟随用）。"""
        self._last_anchor = (anchor_x, anchor_y)
        self._position_to(anchor_x, anchor_y)

    def shake(self):
        """点击吉祥物时气泡上下晃动，相对偏移叠加。"""
        if not self.isVisible():
            return
        if self._shake_anim and self._shake_anim.state() == QPropertyAnimation.Running:
            return
        self._shake_anim = QPropertyAnimation(self, b"shake_offset")
        self._shake_anim.setDuration(400)
        self._shake_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._shake_anim.setKeyValueAt(0, 0.0)
        self._shake_anim.setKeyValueAt(0.25, -8.0)
        self._shake_anim.setKeyValueAt(0.5, 4.0)
        self._shake_anim.setKeyValueAt(0.75, -3.0)
        self._shake_anim.setKeyValueAt(1.0, 0.0)
        self._shake_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._load_content()
            if not self._persistent:
                self._auto_hide_timer.start(random.randint(3000, 5000))
            event.accept()
        else:
            super().mousePressEvent(event)

    def shutdown(self):
        """显式停止定时器/GIF/音频（退出/清理路径调用，幂等）。"""
        self._stop_playback()

    def _stop_playback(self):
        for obj in (self._auto_hide_timer, self._movie, self._audio_player):
            if obj is None:
                continue
            try:
                obj.stop()
            except RuntimeError:
                # C++ 对象已删除：窗口销毁级联中 hideEvent 可能晚于子对象销毁
                pass

    def hideEvent(self, event):
        self._stop_playback()
        self._last_content_file = None  # 隐藏后重置，下次可重复
        self.visibility_changed.emit(False)
        super().hideEvent(event)
