"""
通用可复用控件：
- OptimizedListWidget: setUniformItemSizes 修复滚动后点击错位
- HotkeyLineEdit: 按键捕获输入框（键盘+鼠标）
- HotkeyPairWidget: 功能标签 + 两个热键绑定框（统一双键格式）
- RegionSelector/PointPicker: 全屏区域/坐标选择器
- VehicleFilterWidget: 载具筛选+列表组合控件（select/click/check 三种模式）
- CrosshairPreviewWidget: 准星预览控件
- LinkedSpinSlider: 输入框+滑块双向联动（自带防回路）
- FilterListPanel: 搜索+标签筛选+双标签列表+新建/重命名/删除 骨架
- set_silent: 设值不触发信号的唯一实现（try/finally 保证信号恢复）
"""
from PyQt5.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRubberBand,
    QSizePolicy,
    QTableWidget,
    QHeaderView,
    QAbstractItemView,
    QAbstractScrollArea,
    QVBoxLayout,
    QWidget,
)


class OptimizedListWidget(QListWidget):
    """启用 uniformItemSizes，修复滚动后点击项错位"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUniformItemSizes(True)
        self.setResizeMode(QListWidget.Adjust)


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
        # M12：搜索防抖（180ms）。textChanged 每按键全量重建列表，载具上百条
        # 时输入明显卡顿；停止输入后才过滤一次。
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self.filter_changed)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索载具...")
        self.search.textChanged.connect(self._on_filter_input)
        filter_row.addWidget(self.search, 2)
        self.tag_combo = QComboBox()
        self.tag_combo.currentIndexChanged.connect(self._on_filter_input)
        filter_row.addWidget(self.tag_combo, 1)
        layout.addLayout(filter_row)

        # select/click 用 DualLabelListWidget（显示载具名+标签），check 保持纯文本（需要勾选框）
        if self._mode == "check":
            self.list = OptimizedListWidget()
        else:
            self.list = DualLabelListWidget()
        if self._mode == "select":
            self.list.currentItemChanged.connect(self._on_current_changed)
        elif self._mode == "click":
            self.list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list, 1)

    FAVORITE_TAG = "收藏"

    def _on_filter_input(self):
        """M12：输入/切标签只重启防抖 timer，停止 180ms 后才 emit filter_changed。"""
        self._filter_timer.start()

    def set_tags(self, tags):
        current = self.tag_combo.currentData()
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("全部标签", None)
        if self.FAVORITE_TAG in tags:
            self.tag_combo.addItem(self.FAVORITE_TAG, self.FAVORITE_TAG)
        for t in tags:
            if t == self.FAVORITE_TAG:
                continue
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
                sub = ','.join(vtags) if vtags else ''
                self.list.add_item(name, sub, user_data=name)
        self.list.blockSignals(False)

        if self._mode == "select":
            # 初始化选中仅做视觉同步，不触发 vehicle_selected 信号。
            # populate 的调用场景（启动/搜索过滤/数据变更后刷新）中载具并未切换，
            # 触发信号会导致 _on_quick_vehicle_changed 执行不必要的热键重载和 tab 提前创建。
            self.list.blockSignals(True)
            if select_name:
                for i in range(self.list.count()):
                    if self.list.item(i).data(Qt.UserRole) == select_name:
                        self.list.setCurrentRow(i)
                        break
            elif self.list.count() > 0:
                self.list.setCurrentRow(0)
            self.list.blockSignals(False)

        if self._mode == "check":
            try:
                self.list.itemChanged.disconnect(self._on_item_changed)
            except TypeError:
                pass
            self.list.itemChanged.connect(self._on_item_changed)

    def selected_vehicle(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def set_selected(self, name):
        """只同步选中项，不重新 populate（数据未变时用）"""
        if not name:
            return
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == name:
                self.list.setCurrentRow(i)
                break
        self.list.blockSignals(False)

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
            self.vehicle_selected.emit(current.data(Qt.UserRole))

    def _on_item_clicked(self, item):
        if item:
            self.vehicle_clicked.emit(item.data(Qt.UserRole))

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


class DualLabelItem(QWidget):
    """列表项：本体左对齐 + 绑定信息靠右（区域内左对齐，超长省略）"""

    def __init__(self, main_text="", sub_text="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        self.main_label = QLabel(main_text)
        self.main_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.sub_label = QLabel()
        self.sub_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.sub_label.setObjectName("list_sub_label")
        # main 按内容宽(stretch=0)，spacer 吃剩余空间(stretch=1)，sub 靠右按内容宽
        layout.addWidget(self.main_label, 0)
        layout.addStretch(1)
        layout.addWidget(self.sub_label, 0)
        self._sub_text = sub_text
        self._update_elided()

    def set_main(self, text):
        self.main_label.setText(text)

    def set_sub(self, text):
        self._sub_text = text
        self._update_elided()

    def _update_elided(self):
        if not self._sub_text:
            self.sub_label.setText("")
            return
        # maxWidth 由 resizeEvent 动态计算，直接用它做 elide 上限
        max_w = max(20, self.sub_label.maximumWidth() - 4)
        fm = self.sub_label.fontMetrics()
        self.sub_label.setText(fm.elidedText(self._sub_text, Qt.ElideRight, max_w))

    def sizeHint(self):
        # 固定值：不依赖 fontMetrics()，避免 QSS 应用时序不同导致高度不一致
        # 字体固定 14px，上下边距各 7px，行高 28px
        return QSize(0, 28)

    def set_highlighted(self, on):
        """选中高亮：main_label/sub_label 文字变白，配合 item:selected 背景"""
        if getattr(self, '_highlighted', None) == on:
            return
        self._highlighted = on
        for label in (self.main_label, self.sub_label):
            label.setProperty("dual_hl", "true" if on else "false")
            label.style().unpolish(label)
            label.style().polish(label)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # sub 可用宽度 = 总宽 - 左右边距 - main 内容宽 - spacing
        main_w = self.main_label.sizeHint().width()
        available = self.width() - 8 - 8 - main_w - 8
        self.sub_label.setMaximumWidth(max(40, available))
        self._update_elided()


class DualLabelListWidget(OptimizedListWidget):
    """双标签列表：内聚objectName、局部QSS零padding、add_item入口
    所有约定集中在此类，使用方零配置。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dual_label_list")
        # 用 objectName 选择器提高优先级，抵消全局 QAbstractItemView::item { padding: 5px }
        self.setStyleSheet(
            "QListWidget#dual_label_list::item { padding: 0; }"
        )
        self.currentItemChanged.connect(self._on_current_changed)

    def setCurrentRow(self, row):
        """重写：任何途径设置选中行都自动同步高亮（含blockSignals期间调用）"""
        super().setCurrentRow(row)
        self._sync_highlight(row)

    def setCurrentItem(self, item):
        """重写：任何途径设置选中项都自动同步高亮"""
        super().setCurrentItem(item)
        self._sync_highlight(self.row(item) if item else -1)

    def _sync_highlight(self, row):
        """唯一高亮同步入口：遍历全项，第row项高亮，其余取消"""
        for i in range(self.count()):
            w = self.itemWidget(self.item(i))
            if w and hasattr(w, 'set_highlighted'):
                w.set_highlighted(i == row)

    def _on_current_changed(self, current, _previous):
        """信号触发时统一走_sync_highlight"""
        self._sync_highlight(self.row(current) if current else -1)

    def add_item(self, main_text, sub_text="", user_data=None):
        return _add_dual_label_item(self, main_text, sub_text, user_data)


def _add_dual_label_item(list_widget, main_text, sub_text="", user_data=None):
    """向列表添加双标签项，返回QListWidgetItem"""
    item = QListWidgetItem()
    widget = DualLabelItem(main_text, sub_text)
    list_widget.addItem(item)
    list_widget.setItemWidget(item, widget)
    sh = widget.sizeHint()
    item.setSizeHint(QSize(0, sh.height()))
    if user_data is not None:
        item.setData(Qt.UserRole, user_data)
    return item


def set_silent(widget, value):
    """设置控件值但不触发信号（唯一实现，替代散落的一行流 blockSignals）。

    用 try/finally 保证信号开关一定恢复——历史上这类一行流一旦中途抛异常，
    控件会永久静默（表现为"改了没反应"），且不会留下任何报错。
    """
    widget.blockSignals(True)
    try:
        widget.setValue(value)
    finally:
        widget.blockSignals(False)


class LinkedSpinSlider(QWidget):
    """输入框 + 滑块 双向联动（自带防回路，使用方零配置）。

    约定集中在此类：内部镜像同步绝不触发 value_changed，只有用户改动才发出，
    使用方无需写任何 blockSignals。value_changed 参数为 spin 的值（float）。
    - spin_range     输入框范围（含小数即用 QDoubleSpinBox）
    - slider_range   滑块范围，缺省与 spin_range 相同（滑块精度可粗于输入框）
    - spin_first     输入框在左（默认）还是滑块在左
    - leading/trailing  行首/行尾附加控件（如 +/- 按钮）
    """
    value_changed = pyqtSignal(float)

    def __init__(self, spin_range, slider_range=None, decimals=0, suffix="",
                 step=None, fixed_width=None, spin_first=True, initial=None,
                 leading=None, trailing=None, parent=None):
        super().__init__(parent)
        lo, hi = spin_range
        from PyQt5.QtWidgets import QDoubleSpinBox, QSlider, QSpinBox
        self.spin = QDoubleSpinBox() if decimals else QSpinBox()
        self.spin.setRange(lo, hi)
        if decimals:
            self.spin.setDecimals(decimals)
        if suffix:
            self.spin.setSuffix(suffix)
        if step:
            self.spin.setSingleStep(step)
        if fixed_width:
            self.spin.setFixedWidth(fixed_width)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(*(slider_range or (int(lo), int(hi))))
        if initial is not None:
            self.set_value_silent(initial)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        if leading is not None:
            layout.addWidget(leading)
        if spin_first:
            layout.addWidget(self.spin)
            layout.addWidget(self.slider, 1)
        else:
            layout.addWidget(self.slider, 1)
            layout.addWidget(self.spin)
        if trailing is not None:
            layout.addWidget(trailing)

        self.spin.valueChanged.connect(self._on_spin)
        self.slider.valueChanged.connect(self._on_slider)

    def value(self):
        return self.spin.value()

    def set_value_silent(self, value):
        """载入配置用：两个控件同步且不发信号"""
        set_silent(self.slider, int(value))
        set_silent(self.spin, value)

    def step_value(self, delta):
        """按增量调整（走正常信号链，越界由 spin 范围自动收敛），供 +/- 按钮用"""
        self.spin.setValue(self.spin.value() + delta)

    def _on_spin(self, value):
        set_silent(self.slider, int(value))
        self.value_changed.emit(value)

    def _on_slider(self, value):
        set_silent(self.spin, value)
        self.value_changed.emit(self.spin.value())


class FilterListPanel(QWidget):
    """搜索框 + 标签筛选下拉 + 双标签列表 + 新建/重命名/删除 按钮行（统一骨架）。

    "搜索+筛选+列表+CRUD"的布局与标签下拉同步逻辑集中在此类，使用方零配置；
    列表重建与选中恢复的语义（静默/级联）因页面而异，仍由使用方自己实现。
    """
    add_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, placeholder="搜索配置...", right_widget=None,
                 min_list_height=0, list_stretch=1, right_stretch=1,
                 button_texts=("新建", "重命名", "删除"), parent=None):
        super().__init__(parent)
        from PyQt5.QtWidgets import QPushButton
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        column = QVBoxLayout()
        column.setSpacing(4)
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        search_row.addWidget(self.search, 2)
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("全部标签", None)
        search_row.addWidget(self.tag_filter, 1)
        column.addLayout(search_row)

        self.list = DualLabelListWidget()
        if min_list_height:
            self.list.setMinimumHeight(min_list_height)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        column.addWidget(self.list, 1)

        btn_row = QHBoxLayout()
        self.buttons = {}
        for key, text in zip(("add", "rename", "delete"), button_texts):
            btn = QPushButton(text)
            self.buttons[key] = btn
            btn_row.addWidget(btn)
        self.buttons["add"].clicked.connect(self.add_requested)
        self.buttons["rename"].clicked.connect(self.rename_requested)
        self.buttons["delete"].clicked.connect(self.delete_requested)
        column.addLayout(btn_row)
        row.addLayout(column, list_stretch)

        self.right_widget = right_widget
        if right_widget is not None:
            right = QVBoxLayout()
            right.setSpacing(4)
            right.addWidget(right_widget)
            row.addLayout(right, right_stretch)

    def set_tag_options(self, tags):
        """同步标签下拉选项（保持当前选中）。

        选项集合与顺序都一致时不动它——避免无谓重建触发 currentIndexChanged 递归刷新。
        """
        tags = list(tags)
        existing = [self.tag_filter.itemData(i) for i in range(1, self.tag_filter.count())]
        if existing == tags:
            return
        current = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("全部标签", None)
        for t in tags:
            self.tag_filter.addItem(t, t)
        idx = self.tag_filter.findData(current)
        self.tag_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.tag_filter.blockSignals(False)

    def filter_values(self):
        """返回 (搜索词小写, 当前标签或 None)"""
        return self.search.text().lower(), self.tag_filter.currentData()


def make_group_box(title: str, flat: bool = False, layout_cls=None):
    """创建分组框，返回 (group_box, layout)。

    缩进的唯一权威是全局 QSS（gui/main_window.py 的 QGroupBox 规则）：
    布局 contentsMargins 恒为 0，这里统一保证，避免"QSS padding + layout margins"
    两处叠加出多种缩进（历史上出现过 7 种）。
    flat=True → 无边框组，走 QSS 的 QGroupBox[flat="true"] 规则。
    """
    from PyQt5.QtWidgets import QGroupBox, QVBoxLayout
    box = QGroupBox(title)
    if flat:
        box.setProperty("flat", True)
    layout = (layout_cls or QVBoxLayout)(box)
    layout.setContentsMargins(0, 0, 0, 0)
    return box, layout


def make_settings_container(spacing: int = 8):
    """创建设置容器（禁用时整体不可用），返回 (container, layout) 元组"""
    from PyQt5.QtWidgets import QWidget, QVBoxLayout
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    return container, layout


def make_int_spin(min_val: int, max_val: int, width: int = 90, value: int | None = None,
                  suffix: str | None = None, single_step: int | None = None):
    """创建整数输入框（统一 range + 宽度，可选 value/suffix/single_step）"""
    from PyQt5.QtWidgets import QSpinBox
    spin = QSpinBox()
    spin.setRange(min_val, max_val)
    spin.setMaximumWidth(width)
    if value is not None:
        spin.setValue(value)
    if suffix:
        spin.setSuffix(suffix)
    if single_step:
        spin.setSingleStep(single_step)
    return spin


def make_button_row(button_specs):
    """创建按钮行，button_specs = [(attr_name, text), ...]
    返回 (QHBoxLayout, {attr_name: QPushButton})"""
    from PyQt5.QtWidgets import QPushButton, QHBoxLayout
    layout = QHBoxLayout()
    buttons = {}
    for attr_name, text in button_specs:
        btn = QPushButton(text)
        buttons[attr_name] = btn
        layout.addWidget(btn)
    return layout, buttons


def format_binding_text(path: str) -> str:
    """列表项绑定文字：未绑定统一显示为占位"""
    return path if path else "双击绑定图片"


def make_scroll_area(spacing: int = 10, margins=(10, 10, 10, 10), horizontal_scroll_off: bool = False):
    """创建滚动区域（统一模板），返回 (QScrollArea, content_widget, content_layout)"""
    from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QFrame
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    if horizontal_scroll_off:
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return scroll, content, layout


class FitTable(QTableWidget):
    """自适应高度表格：无自身滚动条，高度=表头+所有行，外层滚动区负责滚动。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fit_table")
        # 关闭自身滚动条
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 内容不被压缩
        self.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # 高度固定，宽度自适应
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # verticalHeader 保持可见但宽度 0（hide 会让行高计算失效）
        self.verticalHeader().setFixedWidth(0)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        # 表头随内容滚动（不浮顶）
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

    def sizeHint(self):
        h = self.horizontalHeader().sizeHint().height()
        h += self.verticalHeader().length()
        h += self.frameWidth() * 2
        return QSize(self.width() if self.width() > 0 else 400, h)

    def fit_height(self):
        """加行/删行/编辑后调用：重新计算行高并通知布局更新。"""
        self.resizeRowsToContents()
        self.updateGeometry()

    def mousePressEvent(self, event):
        """单击直接进入编辑（Qt 没有现成的单击编辑 trigger）。"""
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid() and index.column() in (0, 1):
                item = self.itemFromIndex(index)
                if item:
                    self.editItem(item)

