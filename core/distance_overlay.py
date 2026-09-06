"""距离测算悬浮窗口 - 透明置顶鼠标穿透（一行文本版）
显示当前状态和测距结果。位置由调用方通过move()控制。
"""
from PyQt5.QtWidgets import QLabel, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QPen

from core.overlay_base import ClickThroughOverlay


class DistanceOverlay(ClickThroughOverlay):
    """距离测算悬浮窗口（一行文本）

    特性:
    - 透明背景，置顶，始终鼠标穿透
    - 一行显示：比例尺 + 状态/测距结果
    - 位置由调用方通过move()控制（无拖动编辑模式）
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setMinimumWidth(120)

        self._status_text = "未启用"
        self._result_text = ""

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        self._scale_label = QLabel(self._status_text)
        self._scale_label.setStyleSheet("color: #cccccc; font-size: 12px; font-weight: bold;")
        self._scale_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._scale_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._scale_label)

        self._sep_label = QLabel("|")
        self._sep_label.setStyleSheet("color: #555; font-size: 12px;")
        self._sep_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._sep_label)

        self._result_label = QLabel(self._result_text)
        self._result_label.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        self._result_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._result_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._result_label)

        layout.addStretch()

    def set_scale(self, text: str):
        """设置比例尺栏（白色固定）"""
        if text == self._status_text:
            return
        self._status_text = text
        self._scale_label.setText(text)
        self._adjust_width()

    def set_state_hint(self, state_word: str, state_color: str, hint: str = ""):
        """设置状态栏：状态词上色，提示文字白色"""
        if hint:
            html = f'<span style="color:{state_color}">{state_word}</span> <span style="color:#ffffff">{hint}</span>'
        else:
            html = f'<span style="color:{state_color}">{state_word}</span>'
        if html == self._result_text:
            return
        self._result_text = html
        self._result_label.setText(html)
        self._sep_label.setVisible(True)
        self._adjust_width()

    def set_result(self, text: str, color: str = "#00ff88"):
        """设置结果栏（测距结果绿色）"""
        html = f'<span style="color:{color}">{text}</span>'
        if html == self._result_text:
            return
        self._result_text = html
        self._result_label.setText(html)
        self._sep_label.setVisible(True)
        self._adjust_width()

    def _adjust_width(self):
        """根据内容自动调整宽度"""
        import re
        w = 16
        fm = self._scale_label.fontMetrics()
        w += fm.horizontalAdvance(self._status_text) + 8
        if self._result_text:
            w += fm.horizontalAdvance("|") + 8
            plain = re.sub(r'<[^>]+>', '', self._result_text)
            w += self._result_label.fontMetrics().horizontalAdvance(plain) + 8
        self.setFixedWidth(max(120, min(w, 400)))

    def set_edit_mode(self, enabled: bool):
        """禁用编辑模式：距离测算overlay始终穿透，不允许进入编辑模式"""
        pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(20, 20, 20, 160))
        p.setPen(QPen(QColor(0, 255, 136), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()
