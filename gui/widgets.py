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

    # === 公共方法，替代外部直接操作 self.list 私有成员 ===
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
