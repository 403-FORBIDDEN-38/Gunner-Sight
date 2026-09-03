"""
通用可复用控件：
- OptimizedListWidget: setUniformItemSizes 修复滚动后点击错位
- NoWheelSlider/NoWheelComboBox: 无焦点时屏蔽滚轮误触
- HotkeyLineEdit: 按键捕获输入框（键盘+鼠标）
- HotkeyPairWidget: 功能标签 + 两个热键绑定框（统一双键格式）
- RegionSelector/PointPicker: 全屏区域/坐标选择器
- VehicleFilterWidget: 载具筛选+列表组合控件（select/click/check 三种模式）
- CrosshairPreviewWidget: 准星预览控件
"""
from PyQt5.QtWidgets import (
    QComboBox, QSlider, QLineEdit, QListWidget, QWidget, QRubberBand,
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QApplication,
    QListWidgetItem, QDialog
)
from PyQt5.QtCore import QEvent, Qt, pyqtSignal, QPoint, QSize, QRect
from PyQt5.QtGui import QKeySequence, QPixmap, QPainter, QColor, QFont

from core.hotkey_manager import HotkeyManager
from core.mouse_hook import MouseHook


class OptimizedListWidget(QListWidget):
    """启用 uniformItemSizes，修复滚动后点击项错位"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUniformItemSizes(True)
        self.setResizeMode(QListWidget.Adjust)


class NoWheelSlider(QSlider):
    """无焦点时屏蔽滚轮，避免翻页误触"""
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoWheelComboBox(QComboBox):
    """无焦点时屏蔽滚轮，避免翻页误触"""
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


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
        self._pending_modifier = None  # 17.2: 待决修饰键
        self._has_non_modifier = False  # 17.2: 本次捕获是否已按过非修饰键

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
            # 17.2: 修饰键记录为待决，keyReleaseEvent 判断是否单独绑定
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
            self._finish_capture(mod + QKeySequence(key).toString().lower())
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # 17.2: 若释放的是待决修饰键且期间未捕获其他键，则绑定该修饰键本身
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
        # 17.2: Tab 被 QLineEdit 当焦点切换，拦截捕获态下的 Tab 按键
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


class RegionSelector(QDialog):
    """全屏半透明区域选择器（模态对话框，阻塞其他窗口输入）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setModal(True)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self._origin = QPoint()
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)
        self.result_rect = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 80))
        p.setPen(QColor(255, 255, 255, 200))
        p.setFont(QFont("Arial", 10))
        p.drawText(self.rect(), Qt.AlignTop | Qt.AlignHCenter, "拖动鼠标选择区域，ESC 取消")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._origin = e.pos()
            self._rubber.setGeometry(QRect(self._origin, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, e):
        if self._rubber.isVisible():
            self._rubber.setGeometry(QRect(self._origin, e.pos()).normalized())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            rect = QRect(self._origin, e.pos()).normalized()
            if rect.width() > 5 and rect.height() > 5:
                self.result_rect = rect
                self.accept()
            else:
                self.reject()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()


class PointPicker(QDialog):
    """全屏点击坐标选择器，可带提示文字（模态对话框）"""
    def __init__(self, hint: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setModal(True)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self._hint = hint
        self.result_pos = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self._hint:
            p.setPen(QColor(255, 255, 0))
            p.setFont(QFont("Arial", 10))
            p.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignHCenter | Qt.AlignTop, self._hint)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.result_pos = (e.globalX(), e.globalY())
            self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()


class VehicleFilterWidget(QWidget):
    """载具筛选+列表组合控件
    mode="select": 单选，发射 vehicle_selected
    mode="click": 点击发射 vehicle_clicked
    mode="check": 勾选框，发射 vehicle_toggled(name, checked)
    """
    filter_changed = pyqtSignal()
    vehicle_selected = pyqtSignal(str)
    vehicle_clicked = pyqtSignal(str)
    vehicle_toggled = pyqtSignal(str, bool)

    def __init__(self, mode="select", parent=None):
        super().__init__(parent)
        self._mode = mode
        self._vehicles = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索载具...")
        self.search.textChanged.connect(self.filter_changed)
        filter_row.addWidget(self.search, 2)
        self.tag_combo = NoWheelComboBox()
        self.tag_combo.currentIndexChanged.connect(self.filter_changed)
        filter_row.addWidget(self.tag_combo, 1)
        layout.addLayout(filter_row)

        self.list = OptimizedListWidget()
        if self._mode == "select":
            self.list.currentItemChanged.connect(self._on_current_changed)
        elif self._mode == "click":
            self.list.itemClicked.connect(self._on_item_clicked)
        # check 模式在 populate 中连接 itemChanged
        layout.addWidget(self.list)

    def set_tags(self, tags):
        current = self.tag_combo.currentData()
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("全部标签", None)
        for t in tags:
            self.tag_combo.addItem(t, t)
        idx = self.tag_combo.findData(current)
        if idx >= 0:
            self.tag_combo.setCurrentIndex(idx)
        self.tag_combo.blockSignals(False)

    def get_filter(self):
        return self.search.text().strip(), self.tag_combo.currentData()

    def populate(self, vehicles, select_name=None, checked_set=None):
        self._vehicles = vehicles
        search, tag = self.get_filter()
        self.list.blockSignals(True)
        self.list.clear()
        for name, vtags in vehicles:
            if search and search.lower() not in name.lower():
                continue
            if tag and tag not in vtags:
                continue
            if self._mode == "check":
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if (checked_set and name in checked_set) else Qt.Unchecked)
                self.list.addItem(item)
            else:
                self.list.addItem(name)
        self.list.blockSignals(False)

        if self._mode == "select" and select_name:
            for i in range(self.list.count()):
                if self.list.item(i).text() == select_name:
                    self.list.setCurrentRow(i)
                    break

        if self._mode == "check":
            try:
                self.list.itemChanged.disconnect(self._on_item_changed)
            except TypeError:
                pass
            self.list.itemChanged.connect(self._on_item_changed)

    def selected_vehicle(self):
        item = self.list.currentItem()
        return item.text() if item else None

    # === T11: 公共方法，替代外部直接操作 self.list 私有成员 ===
    def set_no_selection(self):
        """设置列表为无选择模式（check 模式下禁用高亮选中）"""
        from PyQt5.QtWidgets import QAbstractItemView
        self.list.setSelectionMode(QAbstractItemView.NoSelection)

    def add_disabled_item(self, text):
        """添加一个不可交互的提示项（如"暂无载具"）"""
        from PyQt5.QtWidgets import QListWidgetItem
        item = QListWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
        self.list.addItem(item)

    def get_checked_items(self):
        """返回所有勾选项的 UserRole 数据列表（check 模式专用）"""
        result = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                result.append(it.data(Qt.UserRole))
        return result

    def _on_current_changed(self, current, _previous):
        if current:
            self.vehicle_selected.emit(current.text())

    def _on_item_clicked(self, item):
        if item:
            self.vehicle_clicked.emit(item.text())

    def _on_item_changed(self, item):
        self.vehicle_toggled.emit(item.data(Qt.UserRole), item.checkState() == Qt.Checked)


class CrosshairPreviewWidget(QWidget):
    """准星预览控件：居中显示 QPixmap，支持缩放"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._scale = 100
        self.setMinimumSize(200, 200)
        self.setObjectName("preview_box")

    def set_crosshair(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def set_scale(self, value):
        self._scale = value
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap or self._pixmap.isNull():
            return
        p = QPainter(self)
        scaled = self._pixmap.scaled(
            int(self._pixmap.width() * self._scale / 100),
            int(self._pixmap.height() * self._scale / 100),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)
