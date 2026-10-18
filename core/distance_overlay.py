"""距离测算悬浮窗口 - 透明置顶鼠标穿透（一行文本版）
显示当前状态和测距结果。位置由调用方通过move()控制。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QHBoxLayout, QLabel

from core.colors import (DISTANCE_CALIBRATED, OVERLAY_BOX_BG_ALPHA, OVERLAY_BOX_BORDER_RGBA,
                         OVERLAY_BOX_RGB, OVERLAY_SEP, OVERLAY_TEXT)
from core.overlay_base import ClickThroughOverlay


class DistanceOverlay(ClickThroughOverlay):
    """距离测算悬浮窗口（一行文本）

    特性:
    - 透明背景，置顶，始终鼠标穿透
    - 一行显示：比例尺 + 状态/测距结果
    - 位置由调用方通过move()控制（无拖动编辑模式）
    - 配色自成体系：黑底框 + 白字；状态/结果等"关键词"色由调用方传入
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setFixedWidth(220)  # 根源修复：固定宽度，避免任何大小变化导致窗口重建/穿透丢失，进而拖动地图

        self._status_text = ""
        self._result_text = ""

        self._active = False
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        self._scale_label = QLabel(self._status_text)
        self._scale_label.setStyleSheet(f"color: {OVERLAY_TEXT}; font-size: 12px; font-family: Norwester;")
        self._scale_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._scale_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._scale_label)

        self._sep_label = QLabel("|")
        self._sep_label.setStyleSheet(f"color: {OVERLAY_SEP}; font-size: 12px;")
        self._sep_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._sep_label)

        self._result_label = QLabel(self._result_text)
        self._result_label.setStyleSheet(f"color: {OVERLAY_TEXT}; font-size: 13px; font-family: Norwester;")
        self._result_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._result_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._result_label)

        layout.addStretch()

    def set_scale(self, text: str):
        """设置比例尺栏（白色固定）。长文本用省略号截断，不改变窗口大小。"""
        if text == self._status_text:
            return
        self._status_text = text
        elided = self._scale_label.fontMetrics().elidedText(text, Qt.ElideRight, 80)
        self._scale_label.setText(elided)

    def set_state_hint(self, state_word: str, state_color: str, hint: str = ""):
        """设置状态栏：状态词上色，提示文字白色。长文本用省略号截断，不改变窗口大小。"""
        if hint:
            plain = f"{state_word} {hint}"
            elided = self._result_label.fontMetrics().elidedText(plain, Qt.ElideRight, 110)
            # 把截断后的纯文本拆回状态词和提示
            parts = elided.split(" ", 1)
            if len(parts) == 2:
                html = f'<span style="color:{state_color}">{parts[0]}</span> <span style="color:{OVERLAY_TEXT}">{parts[1]}</span>'
            else:
                html = f'<span style="color:{state_color}">{elided}</span>'
        else:
            elided = self._result_label.fontMetrics().elidedText(state_word, Qt.ElideRight, 110)
            html = f'<span style="color:{state_color}">{elided}</span>'
        if html == self._result_text:
            return
        self._result_text = html
        self._result_label.setText(html)
        self._sep_label.setVisible(True)

    def set_result(self, text: str, color: str = DISTANCE_CALIBRATED):
        """设置结果栏（测距结果绿色）。长文本用省略号截断，不改变窗口大小。"""
        elided = self._result_label.fontMetrics().elidedText(text, Qt.ElideRight, 110)
        html = f'<span style="color:{color}">{elided}</span>'
        if html == self._result_text:
            return
        self._result_text = html
        self._result_label.setText(html)
        self._sep_label.setVisible(True)

    def _adjust_width(self):
        """已禁用：宽度固定为220，长文本用省略号截断。任何大小变化都可能导致窗口重建/穿透丢失。"""
        pass

    def set_edit_mode(self, enabled: bool):
        """禁用编辑模式：距离测算overlay始终穿透，不允许进入编辑模式"""
        pass

    def set_active(self, active: bool):
        """暂离/游戏中状态切换。窗口级透明度已取消，此接口仅保留调用兼容。"""
        self._active = active
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(*OVERLAY_BOX_RGB, OVERLAY_BOX_BG_ALPHA))
        p.setPen(QPen(QColor(*OVERLAY_BOX_BORDER_RGBA), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()
