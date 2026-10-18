"""
热键绑定 UI 组件（业务相关，非通用组件）
- HotkeyLineEdit: 按键捕获输入框（键盘+鼠标），ESC 清除
- HotkeyPairWidget: 功能标签 + 两个热键绑定框（统一双键格式）

从 gui/widgets.py 迁移，解决 widgets 反向依赖 core 的架构问题。
依赖 core.hotkey_manager 和 core.mouse_hook（业务逻辑），
因此不属于通用 UI 组件，独立成模块。
"""
from PyQt5.QtCore import QEvent, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QWidget

from core.hotkey_manager import HotkeyManager
from core.mouse_hook import MouseHook
from core.win32_utils import user32  # 组合键：捕获时查询修饰键状态

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


def _capture_modifier_prefix():
    """捕获当前按下的修饰键，返回前缀字符串（如 "ctrl+alt+"），无修饰键返回空串。
    组合键支持：捕获鼠标键/滚轮时记录同时按下的修饰键。"""
    mods = []
    if user32.GetAsyncKeyState(0x11) & 0x8000:  # VK_CONTROL
        mods.append("ctrl")
    if user32.GetAsyncKeyState(0x12) & 0x8000:  # VK_MENU
        mods.append("alt")
    if user32.GetAsyncKeyState(0x10) & 0x8000:  # VK_SHIFT
        mods.append("shift")
    if user32.GetAsyncKeyState(0x5B) & 0x8000:  # VK_LWIN
        mods.append("win")
    return "+".join(mods) + "+" if mods else ""


class HotkeyLineEdit(QLineEdit):
    """热键捕获输入框：点击后捕获下一个按键（键盘或鼠标），ESC 清除。
    组合键支持：捕获鼠标键/滚轮时自动记录同时按下的修饰键。"""
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
        self._mouse_hook.mouse_wheel.connect(self._on_global_mouse_wheel)

    def _on_global_mouse(self, key):
        """根源修复：组合键支持，捕获鼠标键时记录同时按下的修饰键。"""
        if self._capturing:
            prefix = _capture_modifier_prefix()
            self._finish_capture(prefix + key)

    def _on_global_mouse_wheel(self, delta):
        """根源修复：支持滚轮作为热键绑定。delta>0=向上，delta<0=向下。
        组合键支持：捕获滚轮时记录同时按下的修饰键。"""
        if self._capturing:
            prefix = _capture_modifier_prefix()
            wheel_key = "mouse_wheel_up" if delta > 0 else "mouse_wheel_down"
            self._finish_capture(prefix + wheel_key)

    def _finish_capture(self, key):
        self._capturing = False
        if self._mouse_hook:
            try:
                self._mouse_hook.mouse_down.disconnect(self._on_global_mouse)
            except TypeError:
                pass
            try:
                self._mouse_hook.mouse_wheel.disconnect(self._on_global_mouse_wheel)
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
        if label_text:
            self.title_label.setMinimumWidth(100)
        else:
            # 空标签时隐藏，避免占用 100px 最小宽度导致小窗口水平滚动
            self.title_label.setVisible(False)
            self.title_label.setMinimumWidth(0)
        layout.addWidget(self.title_label)

        self.key1 = HotkeyLineEdit()
        self.key1.setMinimumWidth(90)
        self.key1.hotkeyCaptured.connect(self._emit_changed)
        layout.addWidget(self.key1, 3)

        self.trigger1 = QComboBox()
        self.trigger1.addItems(["按下触发", "松开触发", "按住模式"])
        self.trigger1.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.trigger1.setMinimumWidth(80)
        self.trigger1.currentIndexChanged.connect(self._emit_changed)
        layout.addWidget(self.trigger1)

        self.key2 = HotkeyLineEdit()
        self.key2.setMinimumWidth(60)
        self.key2.hotkeyCaptured.connect(self._emit_changed)
        layout.addWidget(self.key2, 1)

        self.trigger2 = QComboBox()
        self.trigger2.addItems(["按下触发", "松开触发", "按住模式"])
        self.trigger2.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.trigger2.setMinimumWidth(80)
        self.trigger2.currentIndexChanged.connect(self._emit_changed)
        layout.addWidget(self.trigger2)

    def set_hotkey(self, hk: dict):
        """从 dict 加载 {key1, trigger1, key2, trigger2}"""
        self.trigger1.blockSignals(True)
        self.trigger2.blockSignals(True)

        k1 = hk.get("key1", "")
        self.key1._key = k1
        self.key1.setText(HotkeyManager.get_key_name(k1) if k1 else "")
        t1 = hk.get("trigger1", "toggle")
        self.trigger1.setCurrentIndex({"keydown": 0, "keyup": 1, "hold": 2, "toggle": 0}.get(t1, 0))

        k2 = hk.get("key2", "")
        self.key2._key = k2
        self.key2.setText(HotkeyManager.get_key_name(k2) if k2 else "")
        t2 = hk.get("trigger2", "toggle")
        self.trigger2.setCurrentIndex({"keydown": 0, "keyup": 1, "hold": 2, "toggle": 0}.get(t2, 0))

        self.trigger1.blockSignals(False)
        self.trigger2.blockSignals(False)

    def _emit_changed(self, *_):
        self.hotkey_changed.emit({
            "key1": self.key1._key,
            "trigger1": {0:"keydown",1:"keyup",2:"hold"}[self.trigger1.currentIndex()],
            "key2": self.key2._key,
            "trigger2": {0:"keydown",1:"keyup",2:"hold"}[self.trigger2.currentIndex()],
        })


class PauseHotkeyWidget(QWidget):
    """暂离热键：两个独立单键（样式对齐 HotkeyPairWidget，无 k1/k2 标签）"""
    hotkey_changed = pyqtSignal(str, dict)  # key_name, hk_dict

    def __init__(self, label_text="暂离", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.title_label = QLabel(label_text)
        self.title_label.setMinimumWidth(100)
        layout.addWidget(self.title_label)

        # 第一个键（宽，占3份）
        self.key1 = HotkeyLineEdit()
        self.key1.setMinimumWidth(90)
        self.key1.hotkeyCaptured.connect(lambda _: self._emit("pause1"))
        layout.addWidget(self.key1, 3)
        self.trigger1 = QComboBox()
        self.trigger1.addItems(["按下触发", "松开触发", "按住模式"])
        self.trigger1.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.trigger1.setMinimumWidth(80)
        self.trigger1.currentIndexChanged.connect(lambda: self._emit("pause1"))
        layout.addWidget(self.trigger1)

        # 第二个键（窄，占1份）
        self.key2 = HotkeyLineEdit()
        self.key2.setMinimumWidth(60)
        self.key2.hotkeyCaptured.connect(lambda _: self._emit("pause2"))
        layout.addWidget(self.key2, 1)
        self.trigger2 = QComboBox()
        self.trigger2.addItems(["按下触发", "松开触发", "按住模式"])
        self.trigger2.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.trigger2.setMinimumWidth(80)
        self.trigger2.currentIndexChanged.connect(lambda: self._emit("pause2"))
        layout.addWidget(self.trigger2)

    def set_hotkey(self, key_name, hk):
        if key_name == "pause1":
            self.trigger1.blockSignals(True)
            k = hk.get("key1", "")
            self.key1._key = k
            self.key1.setText(HotkeyManager.get_key_name(k) if k else "")
            self.trigger1.setCurrentIndex({"keydown": 0, "keyup": 1, "hold": 2, "toggle": 0}.get(hk.get("trigger1", "keydown"), 0))
            self.trigger1.blockSignals(False)
        elif key_name == "pause2":
            self.trigger2.blockSignals(True)
            k = hk.get("key1", "")
            self.key2._key = k
            self.key2.setText(HotkeyManager.get_key_name(k) if k else "")
            self.trigger2.setCurrentIndex({"keydown": 0, "keyup": 1, "hold": 2, "toggle": 0}.get(hk.get("trigger1", "keydown"), 0))
            self.trigger2.blockSignals(False)

    def _emit(self, key_name):
        if key_name == "pause1":
            hk = {
                "key1": self.key1._key,
                "trigger1": {0:"keydown",1:"keyup",2:"hold"}[self.trigger1.currentIndex()],
                "key2": "", "trigger2": "keydown",
            }
        else:
            hk = {
                "key1": self.key2._key,
                "trigger1": {0:"keydown",1:"keyup",2:"hold"}[self.trigger2.currentIndex()],
                "key2": "", "trigger2": "keydown",
            }
        self.hotkey_changed.emit(key_name, hk)
