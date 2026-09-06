"""
热键绑定 UI 组件（业务相关，非通用组件）
- HotkeyLineEdit: 按键捕获输入框（键盘+鼠标），ESC 清除
- HotkeyPairWidget: 功能标签 + 两个热键绑定框（统一双键格式）

从 gui/widgets.py 迁移，解决 widgets 反向依赖 core 的架构问题。
依赖 core.hotkey_manager 和 core.mouse_hook（业务逻辑），
因此不属于通用 UI 组件，独立成模块。
"""
from PyQt5.QtWidgets import QLineEdit, QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QKeySequence

from core.hotkey_manager import HotkeyManager
from core.mouse_hook import MouseHook
from gui.widgets import NoWheelComboBox

# Qt特殊键 → keyboard库键名映射（QKeySequence.toString()对这些键返回空或格式不符）
_SPECIAL_KEY_MAP = {
    Qt.Key_CapsLock: "caps lock",
    Qt.Key_NumLock: "num lock",
    Qt.Key_ScrollLock: "scroll lock",
    Qt.Key_Print: "print screen",
    Qt.Key_Pause: "pause",
    Qt.Key_Insert: "insert",
    Qt.Key_Delete: "delete",
    Qt.Key_Home: "home",
    Qt.Key_End: "end",
    Qt.Key_PageUp: "page up",
    Qt.Key_PageDown: "page down",
}


class HotkeyLineEdit(QLineEdit):
    """热键捕获输入框：点击后捕获下一个按键（键盘或鼠标），ESC 清除"""
    hotkeyCaptured = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击设置...")
        self._capturing = False
        self._mouse_hook = None
        self._key = ""
        self._pending_modifier = None  # 待决修饰键
        self._has_non_modifier = False  # 本次捕获是否已按过非修饰键

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._capturing:
                self._start_capture()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self._capturing:
            key = event.key()
            if key == Qt.Key_Escape:
                self._finish_capture(None)
                return
            # 修饰键记录为待决，keyReleaseEvent 判断是否单独绑定
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                self._pending_modifier = key
                return
            self._has_non_modifier = True
            mod = ""
            if event.modifiers() & Qt.ControlModifier:
                mod += "ctrl+"
            if event.modifiers() & Qt.AltModifier:
                mod += "alt+"
            if event.modifiers() & Qt.ShiftModifier:
                mod += "shift+"
            # 特殊键用映射，普通键用QKeySequence
            key_name = _SPECIAL_KEY_MAP.get(key, QKeySequence(key).toString().lower())
            self._finish_capture(mod + key_name)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # 若释放的是待决修饰键且期间未捕获其他键，则绑定该修饰键本身
        if self._capturing and self._pending_modifier is not None:
            if event.key() == self._pending_modifier and not self._has_non_modifier:
                name = {Qt.Key_Control: "ctrl", Qt.Key_Shift: "shift",
                        Qt.Key_Alt: "alt", Qt.Key_Meta: "meta"}.get(event.key(), "")
                if name:
                    self._finish_capture(name)
                    return
            self._pending_modifier = None
        super().keyReleaseEvent(event)

    def event(self, event):
        # Tab 被 QLineEdit 当焦点切换，拦截捕获态下的 Tab 按键
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Tab and self._capturing:
            self._finish_capture("tab")
            return True
        return super().event(event)

    def _start_capture(self):
        self._capturing = True
        self._pending_modifier = None
        self._has_non_modifier = False
        self.setText("按下按键... (esc清除)")
        self.setFocus()
        self._mouse_hook = MouseHook.instance()
        self._mouse_hook.acquire()
        self._mouse_hook.mouse_down.connect(self._on_global_mouse)

    def _on_global_mouse(self, key):
        if self._capturing:
            self._finish_capture(key)

    def _finish_capture(self, key):
        self._capturing = False
        if self._mouse_hook:
            try:
                self._mouse_hook.mouse_down.disconnect(self._on_global_mouse)
            except TypeError:
                pass
            self._mouse_hook.release()
            self._mouse_hook = None
        self._key = key or ""
        if key:
            self.setText(HotkeyManager.get_key_name(key))
        else:
            self.clear()
        self.hotkeyCaptured.emit(self._key)


class HotkeyPairWidget(QWidget):
    """功能标签 + 两个热键绑定框（键1较宽，键2较窄）"""
    hotkey_changed = pyqtSignal(dict)

    def __init__(self, label_text: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.title_label = QLabel(label_text)
        self.title_label.setMinimumWidth(100)
        layout.addWidget(self.title_label)

        self.key1 = HotkeyLineEdit()
        self.key1.setMinimumWidth(120)
        self.key1.hotkeyCaptured.connect(self._emit_changed)
        layout.addWidget(self.key1, 3)

        self.trigger1 = NoWheelComboBox()
        self.trigger1.addItems(["按下触发", "松开触发"])
        self.trigger1.setFixedWidth(80)
        self.trigger1.currentIndexChanged.connect(self._emit_changed)
        layout.addWidget(self.trigger1)

        self.key2 = HotkeyLineEdit()
        self.key2.setMinimumWidth(80)
        self.key2.hotkeyCaptured.connect(self._emit_changed)
        layout.addWidget(self.key2, 1)

        self.trigger2 = NoWheelComboBox()
        self.trigger2.addItems(["按下触发", "松开触发"])
        self.trigger2.setFixedWidth(80)
        self.trigger2.currentIndexChanged.connect(self._emit_changed)
        layout.addWidget(self.trigger2)

    def set_hotkey(self, hk: dict):
        """从 dict 加载 {key1, trigger1, key2, trigger2}"""
        self.trigger1.blockSignals(True)
        self.trigger2.blockSignals(True)

        k1 = hk.get("key1", "")
        self.key1._key = k1
        self.key1.setText(HotkeyManager.get_key_name(k1) if k1 else "")
        self.trigger1.setCurrentIndex(0 if hk.get("trigger1", "keydown") == "keydown" else 1)

        k2 = hk.get("key2", "")
        self.key2._key = k2
        self.key2.setText(HotkeyManager.get_key_name(k2) if k2 else "")
        self.trigger2.setCurrentIndex(0 if hk.get("trigger2", "keydown") == "keydown" else 1)

        self.trigger1.blockSignals(False)
        self.trigger2.blockSignals(False)

    def _emit_changed(self, *_):
        self.hotkey_changed.emit({
            "key1": self.key1._key,
            "trigger1": "keydown" if self.trigger1.currentIndex() == 0 else "keyup",
            "key2": self.key2._key,
            "trigger2": "keydown" if self.trigger2.currentIndex() == 0 else "keyup",
        })
