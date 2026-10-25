"""载具配置页：标签列表、载具列表、弹种列表、倍率列表"""
from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QSplitter,
    QSplitterHandle,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QFileDialog,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import ConfigManager
from core.resource_manager import ResourceManager
from core.state_machine import StateMachine
from core.vehicle_io import export_vehicle, sanitize_filename
from gui.widgets import (LinkedSpinSlider, make_group_box, DualLabelListWidget,
                         make_button_row, format_binding_text, OptimizedListWidget,
                         set_silent)


class VehicleConfigTab(QWidget):
    data_changed = pyqtSignal()
    tags_changed = pyqtSignal()

    def __init__(self, config: ConfigManager, state: StateMachine,
                 resources: ResourceManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.state = state
        self.resources = resources
        self._tag_check_just_changed = False
        # 抑制回写 flag：覆盖 rebuild 恢复选中 + 外部 state 同步两种场景
        self._suppress_vehicle_writeback = False
        self._suppress_ammo_writeback = False
        self._suppress_mag_writeback = False
        # M17：splitter 拖动结束（handle release）才落盘的脏标记
        self._splitter_dirty = False
        # M12：搜索防抖 timer（180ms）——textChanged 每按键全量重建列表，
        # 停止输入后才过滤一次
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._apply_vehicle_search)

        self._build_ui()
        self._connect_ui_signals()
        # 首次创建时 populate 所有 UI 元素
        self._refresh_tag_list()
        self.on_external_vehicle_changed(self.state.current_vehicle)

    def showEvent(self, event):
        super().showEvent(event)
        # 无需操作：初始状态在 __init__ 里同步；后续变化由信号驱动

    _UNSET = object()  # 区分"没传参"和"传了 None"

    def on_external_vehicle_changed(self, name):
        """外部 state 变化：同步 vehicle_list 选中 + 刷下游"""
        # 判断：当前选中是否已经是 name
        current = self.vehicle_list.currentItem()
        current_data = current.data(Qt.UserRole) if current else None
        if name:
            # 有载具：同步选中 + 刷下游
            if current_data != name:
                self._refresh_vehicle_list(force_select=name)
            self._refresh_ammo_list(force_select=self.state.current_ammo_type)
            self._refresh_mag_list(select_idx=self.state.current_magnification_index)
        else:
            # 无载具（删除当前载具 / 首次启动无 current_vehicle）：
            # 无条件 rebuild vehicle_list（force_select=None 明确不选中）
            self._refresh_vehicle_list(force_select=None)
            self._refresh_ammo_list(force_select=None)
            self._refresh_mag_list(select_idx=None)
        self._update_tag_checkboxes()
        self._update_vehicle_overlay_ui()
        # 切载具时可能被双调一次（vehicle_changed + magnification_changed），幂等
        self._update_mag_detail()

    def on_external_ammo_changed(self, name):
        """外部 state 变化：同步弹种选中 + 刷下游"""
        # 同步选中
        self._suppress_ammo_writeback = True
        try:
            if name:
                idx = self._find_row_by_data(self.ammo_list, name)
                if idx >= 0 and self.ammo_list.currentRow() != idx:
                    self.ammo_list.setCurrentRow(idx)
            else:
                # 无弹种：清空选中
                if self.ammo_list.currentRow() >= 0:
                    self.ammo_list.setCurrentRow(-1)
        finally:
            self._suppress_ammo_writeback = False
        # 刷下游
        self._refresh_mag_list(select_idx=self.state.current_magnification_index)
        # 倍率继承时索引不变，_on_mag_user_selected 直接 return 不发信号，
        # 所以这里必须主动刷一次倍率详情（独立偏移/载具图片/弹种图片勾选框）
        self._update_mag_detail()

    def on_external_mag_changed(self, idx):
        """外部 state 变化：同步倍率选中 + 刷下游"""
        # 同步选中
        self._suppress_mag_writeback = True
        try:
            if 0 <= idx < self.mag_list.count() and self.mag_list.currentRow() != idx:
                self.mag_list.setCurrentRow(idx)
        finally:
            self._suppress_mag_writeback = False
        # 刷下游
        self._update_mag_detail()

    @staticmethod
    def _find_row_by_data(list_widget, data) -> int:
        """按 UserRole 数据查找行索引，找不到返回 -1"""
        for i in range(list_widget.count()):
            if list_widget.item(i).data(Qt.UserRole) == data:
                return i
        return -1

    @staticmethod
    def _select_row_by_data(list_widget, data):
        """按 UserRole 数据选中对应行（不阻断信号，由 flag 抑制回写）"""
        for i in range(list_widget.count()):
            if list_widget.item(i).data(Qt.UserRole) == data:
                list_widget.setCurrentRow(i)
                return True
        return False

    @staticmethod
    def _select_row_by_index(list_widget, index):
        """按索引静默选中对应行（阻断信号，避免回写状态机形成回路）。"""
        if index is not None and 0 <= index < list_widget.count():
            list_widget.blockSignals(True)
            list_widget.setCurrentRow(index)
            list_widget.blockSignals(False)
            return True
        return False

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 标签列
        tag_panel, tag_layout = make_group_box("标签列表")
        tag_layout.setSpacing(5)
        self.tag_list = OptimizedListWidget()
        self.tag_list.setObjectName("tag_list")
        self.tag_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        self.tag_list.itemChanged.connect(self._on_tag_check_changed)
        self.tag_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tag_list.customContextMenuRequested.connect(self._on_tag_list_context_menu)
        tag_layout.addWidget(self.tag_list, 1)
        tag_input_layout = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("点击创建标签")
        tag_input_layout.addWidget(self.tag_input, 1)
        self.add_tag_btn = QPushButton("+")
        self.add_tag_btn.setFixedWidth(32)
        tag_input_layout.addWidget(self.add_tag_btn)
        tag_layout.addLayout(tag_input_layout)
        tag_btn_layout, tag_btns = make_button_row([("rename", "重命名"), ("remove", "删除")])
        self.rename_tag_btn = tag_btns["rename"]
        self.remove_tag_btn = tag_btns["remove"]
        tag_layout.addLayout(tag_btn_layout)

        # 载具列
        vehicle_panel, vehicle_layout = make_group_box("载具列表", flat=True)
        vehicle_layout.setSpacing(5)
        self.vehicle_search = QLineEdit()
        self.vehicle_search.setPlaceholderText("搜索载具...")
        vehicle_layout.addWidget(self.vehicle_search)
        self.vehicle_list = DualLabelListWidget()
        self.vehicle_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vehicle_list.customContextMenuRequested.connect(self._on_vehicle_list_context_menu)
        vehicle_layout.addWidget(self.vehicle_list, 1)
        # 两行三列：第一行添加/复制/重命名，第二行删除/导出/导入
        row1_layout, row1_btns = make_button_row([
            ("add", "添加"), ("copy", "复制"), ("rename", "重命名")])
        row2_layout, row2_btns = make_button_row([
            ("remove", "删除"), ("export", "导出"), ("import", "导入")])
        vehicle_btn_layout = QVBoxLayout()
        vehicle_btn_layout.setSpacing(4)
        vehicle_btn_layout.addLayout(row1_layout)
        vehicle_btn_layout.addLayout(row2_layout)
        v_btns = {**row1_btns, **row2_btns}
        self.add_vehicle_btn = v_btns["add"]
        self.copy_vehicle_btn = v_btns["copy"]
        self.rename_vehicle_btn = v_btns["rename"]
        self.remove_vehicle_btn = v_btns["remove"]
        self.export_vehicle_btn = v_btns["export"]
        self.import_vehicle_btn = v_btns["import"]
        vehicle_layout.addLayout(vehicle_btn_layout)

        # 弹种+倍率列
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # 载具图片列表（与弹种/倍率列表一致：GroupBox 包裹，双击绑定，右键菜单操作）
        vehicle_ui_group, vui_layout = make_group_box("载具图片", flat=True)
        self.vehicle_ui_list = DualLabelListWidget()
        self.vehicle_ui_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vehicle_ui_list.customContextMenuRequested.connect(self._on_vehicle_ui_list_context_menu)
        self.vehicle_ui_list.itemDoubleClicked.connect(lambda _item: self._on_bind_vehicle_ui())
        self.vehicle_ui_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.vehicle_ui_list.setMaximumHeight(32)
        vui_layout.addWidget(self.vehicle_ui_list)
        right_layout.addWidget(vehicle_ui_group, 0)

        ammo_group, ammo_layout = make_group_box("弹种列表")
        self.ammo_list = DualLabelListWidget()
        self.ammo_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ammo_list.customContextMenuRequested.connect(self._on_ammo_list_context_menu)
        ammo_layout.addWidget(self.ammo_list, 1)
        ammo_btn_layout, a_btns = make_button_row([("add", "添加"), ("rename", "重命名"), ("remove", "删除")])
        self.add_ammo_btn = a_btns["add"]
        self.rename_ammo_btn = a_btns["rename"]
        self.remove_ammo_btn = a_btns["remove"]
        ammo_layout.addLayout(ammo_btn_layout)

        mag_group, mag_layout = make_group_box("倍率列表", flat=True)
        self.mag_list = DualLabelListWidget()
        self.mag_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mag_list.customContextMenuRequested.connect(self._on_mag_list_context_menu)
        mag_layout.addWidget(self.mag_list, 1)
        mag_btn_layout, m_btns = make_button_row([("add", "添加"), ("remove", "删除")])
        self.add_mag_btn = m_btns["add"]
        self.remove_mag_btn = m_btns["remove"]
        mag_layout.addLayout(mag_btn_layout)
        mag_detail_layout = QVBoxLayout()
        # 缩放偏移模式 + 叠加弹种图片 勾选框
        check_row = QHBoxLayout()
        self.overlay_mode_check = QCheckBox("独立偏移")
        check_row.addWidget(self.overlay_mode_check)
        self.overlay_vehicle_ui_check = QCheckBox("叠加载具图片")
        check_row.addWidget(self.overlay_vehicle_ui_check)
        self.overlay_ammo_ui_check = QCheckBox("叠加弹种图片")
        check_row.addWidget(self.overlay_ammo_ui_check)
        check_row.addStretch()
        mag_detail_layout.addLayout(check_row)
        mag_layout.addLayout(mag_detail_layout)

        # 弹种/倍率高度可调节：弹种通常较多，默认给更大比例
        ammo_mag_splitter = QSplitter(Qt.Vertical)
        ammo_mag_splitter.setChildrenCollapsible(False)
        ammo_mag_splitter.addWidget(ammo_group)
        ammo_mag_splitter.addWidget(mag_group)
        ammo_mag_splitter.setStretchFactor(0, 2)
        ammo_mag_splitter.setStretchFactor(1, 1)
        right_layout.addWidget(ammo_mag_splitter, 1)

        # 载具缩放偏移区域
        self.vehicle_overlay_group = QGroupBox("独立偏移")
        vo_layout = QVBoxLayout(self.vehicle_overlay_group)
        vo_layout.setContentsMargins(0, 0, 0, 0)
        # 缩放（滑块在左、输入框在右）
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("大小缩放:"))
        self.vo_scale_ctl = LinkedSpinSlider((1, 1000), suffix="%", fixed_width=80,
                                             spin_first=False, initial=100)
        scale_layout.addWidget(self.vo_scale_ctl)
        vo_layout.addLayout(scale_layout)
        # X/Y 偏移
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(QLabel("横向偏移:"))
        self.vo_offset_x = QSpinBox()
        self.vo_offset_x.setRange(-2000, 2000)
        offset_layout.addWidget(self.vo_offset_x)
        offset_layout.addWidget(QLabel("竖向偏移:"))
        self.vo_offset_y = QSpinBox()
        self.vo_offset_y.setRange(-2000, 2000)
        offset_layout.addWidget(self.vo_offset_y)
        vo_layout.addLayout(offset_layout)
        # 透明度（- / 输入框 / 滑块 / +）
        self.vo_opacity_minus_btn = QPushButton("-"); self.vo_opacity_minus_btn.setFixedWidth(30)
        self.vo_opacity_plus_btn = QPushButton("+"); self.vo_opacity_plus_btn.setFixedWidth(30)
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("不透明度:"))
        self.vo_opacity_ctl = LinkedSpinSlider((10, 100), suffix="%", fixed_width=80,
                                               initial=100, leading=self.vo_opacity_minus_btn,
                                               trailing=self.vo_opacity_plus_btn)
        opacity_layout.addWidget(self.vo_opacity_ctl)
        vo_layout.addLayout(opacity_layout)
        # 说明文字
        vo_hint = QLabel('倍率选"独立"时使用此配置')
        vo_hint.setObjectName("hint_text")
        vo_layout.addWidget(vo_hint)
        right_layout.addWidget(self.vehicle_overlay_group, 0)



        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(tag_panel)
        self.splitter.addWidget(vehicle_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 3)
        # 恢复保存的尺寸，没有则用默认
        saved = self.config.get_splitter_sizes("vehicle_config", [150, 250, 400])
        self.splitter.setSizes(saved)
        # M17：拖动中只标记脏，handle release（拖动结束）时才写 config。
        # splitterMoved 逐像素触发，直接写是高频入队（500ms 防抖被反复重启）。
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        for _hi in range(1, self.splitter.count()):
            self.splitter.handle(_hi).installEventFilter(self)
        tag_panel.setMinimumWidth(120)
        vehicle_panel.setMinimumWidth(180)
        right_panel.setMinimumWidth(280)
        layout.addWidget(self.splitter)

    def _on_splitter_moved(self, _pos, _index):
        """M17：splitter 拖动中只标记脏，release 时才落盘（见 eventFilter）。"""
        self._splitter_dirty = True

    def eventFilter(self, obj, event):
        # M17：splitter handle 的鼠标 release = 拖动结束，此时才保存尺寸。
        if event.type() == QEvent.MouseButtonRelease and self._splitter_dirty:
            if isinstance(obj, QSplitterHandle):
                self._splitter_dirty = False
                self.config.set_splitter_sizes("vehicle_config", self.splitter.sizes())
        return super().eventFilter(obj, event)

    def _connect_ui_signals(self):
        # 载具
        self.add_vehicle_btn.clicked.connect(self._on_add_vehicle)
        self.copy_vehicle_btn.clicked.connect(self._on_copy_vehicle)
        self.rename_vehicle_btn.clicked.connect(self._on_rename_vehicle)
        self.remove_vehicle_btn.clicked.connect(self._on_remove_vehicle)
        self.export_vehicle_btn.clicked.connect(self._on_export_vehicle)
        self.import_vehicle_btn.clicked.connect(self._on_import_vehicle)
        self.vehicle_list.currentItemChanged.connect(self._on_vehicle_user_selected)
        self.vehicle_search.textChanged.connect(self._on_vehicle_search)
        # 标签

        self.add_tag_btn.clicked.connect(self._on_add_tag)
        self.tag_input.returnPressed.connect(self._on_add_tag)
        self.rename_tag_btn.clicked.connect(self._on_rename_tag)
        self.remove_tag_btn.clicked.connect(self._on_remove_tag)
        # 弹种
        self.add_ammo_btn.clicked.connect(self._on_add_ammo)
        self.rename_ammo_btn.clicked.connect(self._on_rename_ammo)
        self.remove_ammo_btn.clicked.connect(self._on_remove_ammo)
        self.ammo_list.currentItemChanged.connect(self._on_ammo_user_selected)
        self.ammo_list.itemDoubleClicked.connect(lambda _item: self._on_bind_ammo_ui())
        # 倍率
        self.add_mag_btn.clicked.connect(self._on_add_mag)
        self.remove_mag_btn.clicked.connect(self._on_remove_mag)
        self.mag_list.currentItemChanged.connect(self._on_mag_user_selected)
        self.mag_list.itemDoubleClicked.connect(lambda _item: self._on_bind_crosshair())
        self.overlay_mode_check.stateChanged.connect(self._on_overlay_mode_changed)
        self.overlay_vehicle_ui_check.stateChanged.connect(self._on_overlay_vehicle_ui_changed)
        self.overlay_ammo_ui_check.stateChanged.connect(self._on_overlay_ammo_ui_changed)
        # 载具缩放偏移
        self.vo_scale_ctl.value_changed.connect(self._on_vehicle_scale_changed)
        self.vo_offset_x.valueChanged.connect(self._on_vehicle_offset_changed)
        self.vo_offset_y.valueChanged.connect(self._on_vehicle_offset_changed)
        self.vo_opacity_ctl.value_changed.connect(self._on_vehicle_opacity_changed)
        self.vo_opacity_minus_btn.clicked.connect(lambda: self.vo_opacity_ctl.step_value(-5))
        self.vo_opacity_plus_btn.clicked.connect(lambda: self.vo_opacity_ctl.step_value(5))

    # === 标签 ===
    FAVORITE_TAG = "收藏"

    def _refresh_tag_list(self):
        # 确保"收藏"标签存在
        if self.FAVORITE_TAG not in self.config.get_all_tags():
            self.config.add_tag(self.FAVORITE_TAG)
        all_tags = self.config.get_all_tags()
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        # 全部标签
        all_item = QListWidgetItem("全部标签")
        all_item.setData(Qt.UserRole, "__all__")
        self.tag_list.addItem(all_item)
        # 收藏（固定第二位）
        fav_item = QListWidgetItem(self.FAVORITE_TAG)
        fav_item.setData(Qt.UserRole, self.FAVORITE_TAG)
        fav_item.setFlags(fav_item.flags() | Qt.ItemIsUserCheckable)
        fav_item.setCheckState(Qt.Unchecked)
        self.tag_list.addItem(fav_item)
        # 其他标签（排除收藏）
        for tag in all_tags:
            if tag == self.FAVORITE_TAG:
                continue
            item = QListWidgetItem(tag)
            item.setData(Qt.UserRole, tag)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.tag_list.addItem(item)
        self.tag_list.blockSignals(False)
        self._update_tag_checkboxes()

    def _on_tag_clicked(self, item):
        if self._tag_check_just_changed:
            self._tag_check_just_changed = False
            return
        tag = item.data(Qt.UserRole)
        if tag == "__all__":
            self._refresh_vehicle_list()
        else:
            self._refresh_vehicle_list(tag_filter=tag)
        # 筛选有结果 → 自动切第一辆。这是用户确认的行为，别动。
        if self.vehicle_list.count() > 0:
            self.vehicle_list.setCurrentRow(0)

    def _on_tag_check_changed(self, item):
        self._tag_check_just_changed = True
        tag = item.data(Qt.UserRole)
        if tag == "__all__":
            return
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        tags = self.config.get_vehicle_tags(vehicle)
        if item.checkState() == Qt.Checked:
            if tag not in tags:
                tags.append(tag)
        else:
            if tag in tags:
                tags.remove(tag)
        self.config.set_vehicle_tags(vehicle, tags)
        self._refresh_vehicle_list()
        self.data_changed.emit()

    def _update_tag_checkboxes(self):
        """切换载具时，按新载具的 tags 刷新所有 checkbox"""
        vehicle = self._get_selected_vehicle()
        tags = set(self.config.get_vehicle_tags(vehicle)) if vehicle else set()
        self.tag_list.blockSignals(True)
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            if item.data(Qt.UserRole) != "__all__":
                item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in tags else Qt.Unchecked)
        self.tag_list.blockSignals(False)


    def _on_add_tag(self):
        name = self.tag_input.text().strip()
        if name and self.config.add_tag(name):
            self.tag_input.clear()
            self._refresh_tag_list()
            self.tags_changed.emit()


    def _on_rename_tag(self):
        item = self.tag_list.currentItem()
        if not item or item.data(Qt.UserRole) == "__all__":
            return
        old = item.data(Qt.UserRole)
        new, ok = QInputDialog.getText(self, "重命名标签", "新名称:", text=old)
        if ok and new.strip() and new != old:
            self.config.rename_tag(old, new.strip())
            self._refresh_tag_list()
            self._refresh_vehicle_list()
            self.data_changed.emit()
            self.tags_changed.emit()

    def _on_remove_tag(self):
        item = self.tag_list.currentItem()
        if not item or item.data(Qt.UserRole) == "__all__":
            return
        tag = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "确认", f"删除标签 '{tag}'?（载具将解绑此标签）",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.config.remove_tag(tag)
            self._refresh_tag_list()
            self._refresh_vehicle_list()
            self.tags_changed.emit()

    # === 载具 ===
    def _get_selected_vehicle(self):
        item = self.vehicle_list.currentItem()
        if item:
            return item.data(Qt.UserRole)
        # 列表无选中 → 回落到 state。
        # 场景：筛选结果为空时（如 PMC 空标签），列表空但 state 保持原值。
        # 语义：本方法返回"当前载具"，无论它是否在当前筛选视图里。
        return self.state.current_vehicle

    def _refresh_vehicle_list(self, tag_filter=None, force_select=_UNSET):
        search = self.vehicle_search.text()
        if tag_filter is None:
            tag_item = self.tag_list.currentItem()
            if tag_item and tag_item.data(Qt.UserRole) != "__all__":
                tag_filter = tag_item.data(Qt.UserRole)
        names = self.config.get_vehicle_names_filtered(search, tag_filter or "")
        # 决定要选中的载具：force_select 优先，其次当前选中
        if force_select is not self._UNSET:
            target_select = force_select
        else:
            target_select = self._get_selected_vehicle()
        self.vehicle_list.blockSignals(True)
        self.vehicle_list.clear()
        for name in names:
            tags = self.config.get_vehicle_tags(name)
            sub = ','.join(tags) if tags else ''
            self.vehicle_list.add_item( name, sub, user_data=name)
        self.vehicle_list.blockSignals(False)
        # 恢复选中（用 flag 包裹，不触发回写）
        self._suppress_vehicle_writeback = True
        try:
            if target_select:
                idx = self._find_row_by_data(self.vehicle_list, target_select)
                if idx >= 0 and self.vehicle_list.currentRow() != idx:
                    self.vehicle_list.setCurrentRow(idx)
        finally:
            self._suppress_vehicle_writeback = False

    def _on_vehicle_search(self, _text):
        """M12：只重启防抖 timer，停止输入 180ms 后才真正过滤。"""
        self._search_timer.start()

    def _apply_vehicle_search(self):
        self._refresh_vehicle_list()

    def _on_vehicle_user_selected(self, current, _previous):
        """用户点击触发：只写 state，不做任何刷新（由 state 信号触发 on_external_vehicle_changed）"""
        if self._suppress_vehicle_writeback:
            return  # 来自 state 同步，不回写
        name = current.data(Qt.UserRole) if current else None
        if name == self.state.current_vehicle:
            return  # 没变化，不重复写
        self.state.set_vehicle(name)

    def _on_add_vehicle(self):
        name, ok = QInputDialog.getText(self, "添加载具", "载具名称:")
        if ok and name.strip():
            name = name.strip()
            if self.state.add_vehicle(name):
                self._refresh_vehicle_list()
                self._select_row_by_data(self.vehicle_list, name)
                self.data_changed.emit()
            else:
                QMessageBox.warning(self, "提示", f"载具 '{name}' 已存在！")

    def _on_copy_vehicle(self):
        current = self._get_selected_vehicle()
        if not current:
            QMessageBox.information(self, "提示", "请先选择要复制的载具")
            return
        default_name = f"{current}_副本"
        name, ok = QInputDialog.getText(self, "复制载具", "新载具名称:", text=default_name)
        if ok and name.strip():
            name = name.strip()
            if self.state.copy_vehicle(current, name):
                self._refresh_vehicle_list()
                self._select_row_by_data(self.vehicle_list, name)
                self.data_changed.emit()  # 复制带入了弹种热键，需立即重建弹种热键
            else:
                QMessageBox.warning(self, "提示", f"载具 '{name}' 已存在！")

    def _on_rename_vehicle(self):
        current = self._get_selected_vehicle()
        if not current:
            return
        name, ok = QInputDialog.getText(self, "重命名载具", "新名称:", text=current)
        # M10：取消 / 空名 / 未改名都是用户主动放弃，静默 return（对齐
        # _on_rename_tag / _on_rename_ammo 的语义）。原实现三种情况全落
        # else 弹「已存在」——纯误报，本页唯一的多余分支。
        if not ok or not name.strip() or name.strip() == current:
            return
        new_name = name.strip()
        self.state.rename_vehicle(current, new_name)
        self._refresh_vehicle_list()
        self._select_row_by_data(self.vehicle_list, new_name)
        self.data_changed.emit()

    def _on_remove_vehicle(self):
        current = self._get_selected_vehicle()
        if not current:
            return
        reply = QMessageBox.question(self, "确认", f"删除载具 '{current}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.state.remove_vehicle(current)
            # state.remove_vehicle 内部触发 vehicle_changed("")，
            # on_external_vehicle_changed 空 name 分支已同步三列表
            self.data_changed.emit()

    def _on_export_vehicle(self):
        current = self._get_selected_vehicle()
        if not current:
            QMessageBox.information(self, "提示", "请先选择要导出的载具")
            return
        output = self.resources.get_write_dir() / (sanitize_filename(current) + ".gsv")
        ok, msg = export_vehicle(
            self.config,
            self.resources.get_resources_dir(),
            current,
            output,
        )
        if ok:
            QMessageBox.information(self, "导出成功", msg + f"\n已保存到: {output}")
        else:
            QMessageBox.warning(self, "导出失败", msg)

    def _on_import_vehicle(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入载具", "", "GunnerSight 载具包 (*.gsv)")
        if not path:
            return
        from pathlib import Path
        ok, msg, new_name = self.state.import_vehicle(
            self.resources.get_write_dir(),
            Path(path),
        )
        if not ok:
            QMessageBox.warning(self, "导入失败", msg)
            return
        self._refresh_vehicle_list()
        if new_name:
            self._select_row_by_data(self.vehicle_list, new_name)
            self._refresh_ammo_list(keep_selection=False)
            if self.ammo_list.count() > 0:
                self.ammo_list.setCurrentRow(0)
            self._refresh_mag_list()
            self._update_vehicle_overlay_ui()
        self.data_changed.emit()
        from core.logger import logger
        logger.info(msg)

    # === 弹种 ===
    def _refresh_ammo_list(self, keep_selection=True, force_select=_UNSET):
        vehicle = self._get_selected_vehicle()
        # 决定要选中的弹种
        if force_select is not self._UNSET:
            target = force_select  # 可能为 None，明确表达"无选中"
        elif keep_selection:
            target = self._get_selected_ammo()
        else:
            target = None
        self.ammo_list.blockSignals(True)
        self.ammo_list.clear()
        if vehicle:
            for ammo in self.config.get_ammo_types(vehicle):
                ammo_ui = self.config.get_ammo_ui(vehicle, ammo)
                sub = format_binding_text(ammo_ui)
                self.ammo_list.add_item(ammo, sub, user_data=ammo)
        self.ammo_list.blockSignals(False)
        # 恢复选中（用 flag 包裹）
        self._suppress_ammo_writeback = True
        try:
            if target:
                idx = self._find_row_by_data(self.ammo_list, target)
                if idx >= 0 and self.ammo_list.currentRow() != idx:
                    self.ammo_list.setCurrentRow(idx)
        finally:
            self._suppress_ammo_writeback = False

    def _on_ammo_user_selected(self, current, _previous):
        """用户点击触发：只写 state，不做任何刷新（由 state 信号触发 on_external_ammo_changed）"""
        if self._suppress_ammo_writeback:
            return
        name = current.data(Qt.UserRole) if current else None
        if name == self.state.current_ammo_type:
            return
        self.state.set_ammo_type(name)

    def _on_add_ammo(self):
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        name, ok = QInputDialog.getText(self, "添加弹种", "弹种名称:")
        if ok and name.strip():
            self.config.add_ammo_type(vehicle, name.strip())
            self._refresh_ammo_list()
            self.data_changed.emit()  # 新增弹种自动绑定了热键，需立即重建弹种热键
            # 自动选中新弹种
            for i in range(self.ammo_list.count()):
                if self.ammo_list.item(i).data(Qt.UserRole) == name.strip():
                    self.ammo_list.setCurrentRow(i)
                    break

    def _on_rename_ammo(self):
        vehicle = self._get_selected_vehicle()
        item = self.ammo_list.currentItem()
        if not vehicle or not item:
            return
        old = item.data(Qt.UserRole)
        new, ok = QInputDialog.getText(self, "重命名弹种", "新名称:", text=old)
        if ok and new.strip() and new != old:
            self.state.rename_ammo_type(vehicle, old, new.strip())
            self._refresh_ammo_list()
            self.data_changed.emit()  # 弹种重命名同步热键键名

    def _on_remove_ammo(self):
        vehicle = self._get_selected_vehicle()
        item = self.ammo_list.currentItem()
        if not vehicle or not item:
            return
        ammo = item.data(Qt.UserRole)
        self.state.remove_ammo_type(vehicle, ammo)
        self._refresh_ammo_list()
        self.data_changed.emit()  # 删除弹种需卸载其热键
        # 立即重建倍率列表，避免残留被删弹种的倍率：还有弹种则选第一个，否则清空
        if self.ammo_list.currentRow() < 0 and self.ammo_list.count() > 0:
            self.ammo_list.setCurrentRow(0)  # 触发 _on_ammo_selected 重建倍率
        else:
            self._refresh_mag_list(keep_selection=False)

    # === 倍率 ===
    def _get_selected_ammo(self):
        item = self.ammo_list.currentItem()
        if item:
            return item.data(Qt.UserRole)
        # 同上：列表无选中时回落到 state
        return self.state.current_ammo_type

    def _refresh_mag_list(self, select_idx=None, keep_selection=True):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        # 记录当前选中的倍率索引，重建后恢复（优先使用传入的 select_idx）
        previously_selected_idx = None
        if keep_selection:
            item = self.mag_list.currentItem()
            if item:
                previously_selected_idx = item.data(Qt.UserRole)
        self.mag_list.blockSignals(True)
        self.mag_list.clear()
        if vehicle:
            for i, mag in enumerate(self.config.get_magnifications(vehicle)):
                label = mag.get("label", f"倍率{i+1}")
                ch = self.config.get_crosshair_path(vehicle, ammo, i) if ammo else ""
                mode = "独立" if self.config.get_magnification_overlay_mode(vehicle, ammo, i) else ""
                overlay_vehicle = self.config.get_overlay_vehicle_ui(vehicle, ammo, i) if ammo else False
                overlay_ammo = self.config.get_overlay_ammo_ui(vehicle, ammo, i) if ammo else False
                tags = f"[{mode}]" if mode else ""
                if overlay_vehicle:
                    tags += "[载具]"
                if overlay_ammo:
                    tags += "[弹种]"
                ch_part = format_binding_text(ch)
                sub = f"{tags} {ch_part}" if tags else ch_part
                self.mag_list.add_item(label, sub, user_data=i)
        # 优先使用传入的 select_idx，没有则用自动恢复的 previously_selected_idx
        target_idx = select_idx if select_idx is not None else previously_selected_idx
        self.mag_list.blockSignals(False)
        # M11：选中恢复必须包 _suppress_mag_writeback（对齐 vehicle/ammo 语义）。
        # 裸 setCurrentRow 会触发 _on_mag_user_selected 回写 state；原先只靠
        # 「idx 相等」短路兜底，相等判断一旦失效就形成 state→刷新→state 回写环路。
        # try/finally：异常也不把抑制旗永久留在 True（widgets.py set_silent 注释
        # 警示的「控件永久静默」模式）。
        self._suppress_mag_writeback = True
        try:
            if target_idx is not None and 0 <= target_idx < self.mag_list.count():
                self.mag_list.setCurrentRow(target_idx)
        finally:
            self._suppress_mag_writeback = False

    def _update_mag_detail(self):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            self.overlay_mode_check.blockSignals(True)
            self.overlay_mode_check.setChecked(False)
            self.overlay_mode_check.blockSignals(False)
            self.overlay_vehicle_ui_check.blockSignals(True)
            self.overlay_vehicle_ui_check.setChecked(False)
            self.overlay_vehicle_ui_check.blockSignals(False)
            self.overlay_ammo_ui_check.blockSignals(True)
            self.overlay_ammo_ui_check.setChecked(False)
            self.overlay_ammo_ui_check.blockSignals(False)
            return
        idx = item.data(Qt.UserRole)
        use_vehicle = self.config.get_magnification_overlay_mode(vehicle, ammo, idx)
        self.overlay_mode_check.blockSignals(True)
        self.overlay_mode_check.setChecked(use_vehicle)
        self.overlay_mode_check.blockSignals(False)
        overlay_vehicle = self.config.get_overlay_vehicle_ui(vehicle, ammo, idx)
        self.overlay_vehicle_ui_check.blockSignals(True)
        self.overlay_vehicle_ui_check.setChecked(overlay_vehicle)
        self.overlay_vehicle_ui_check.blockSignals(False)
        overlay_ammo = self.config.get_overlay_ammo_ui(vehicle, ammo, idx)
        self.overlay_ammo_ui_check.blockSignals(True)
        self.overlay_ammo_ui_check.setChecked(overlay_ammo)
        self.overlay_ammo_ui_check.blockSignals(False)

    def _on_mag_user_selected(self, current, _previous):
        """用户点击触发：只写 state，不做任何刷新（由 state 信号触发 on_external_mag_changed）"""
        if self._suppress_mag_writeback:
            return
        idx = self.mag_list.currentRow()
        if idx == self.state.current_magnification_index:
            return
        self.state.set_magnification(idx)

    def _on_add_mag(self):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        if not vehicle or not ammo:
            return
        self.config.add_magnification(vehicle)
        self._refresh_mag_list()
        # 自动选中新倍率（最后一个）
        if self.mag_list.count() > 0:
            self.mag_list.setCurrentRow(self.mag_list.count() - 1)

    def _on_remove_mag(self):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        idx = item.data(Qt.UserRole)
        self.state.remove_magnification(vehicle, idx)
        self._refresh_mag_list()


    def _on_overlay_mode_changed(self, _state):
        """缩放偏移模式切换：勾选框状态变化"""
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        idx = item.data(Qt.UserRole)
        use_vehicle = self.overlay_mode_check.isChecked()
        self.config.set_magnification_overlay_mode(vehicle, ammo, idx, use_vehicle)
        self._refresh_mag_list(keep_selection=True)
        self._update_overlay_preview()

    def _update_vehicle_overlay_ui(self):
        """切换载具时更新载具缩放偏移区域的标题和数值"""
        vehicle = self._get_selected_vehicle()
        if vehicle:
            self.vehicle_overlay_group.setTitle(f"独立偏移 — {vehicle}")
            overlay = self.config.get_vehicle_overlay(vehicle)
            self.vo_scale_ctl.set_value_silent(int(overlay["scale"]))
            set_silent(self.vo_offset_x, overlay["offset_x"])
            set_silent(self.vo_offset_y, overlay["offset_y"])
            self.vo_opacity_ctl.set_value_silent(int(overlay.get("opacity", 1.0) * 100))
        else:
            self.vehicle_overlay_group.setTitle("独立偏移")
        # 载具图片列表刷新
        self._refresh_vehicle_ui_list()

    def _on_vehicle_scale_changed(self, value):
        """缩放变化（滑块或输入框）：保存配置 + 预览"""
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        overlay = self.config.get_vehicle_overlay(vehicle)
        self.config.set_vehicle_overlay(vehicle, int(value), overlay["offset_x"], overlay["offset_y"])
        self._update_overlay_preview()

    def _on_vehicle_offset_changed(self, _value):
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        overlay = self.config.get_vehicle_overlay(vehicle)
        self.config.set_vehicle_overlay(vehicle, overlay["scale"],
                                         self.vo_offset_x.value(), self.vo_offset_y.value())
        self._update_overlay_preview()

    def _on_vehicle_opacity_changed(self, value):
        self._apply_vehicle_opacity(int(value))

    def _apply_vehicle_opacity(self, percent):
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        overlay = self.config.get_vehicle_overlay(vehicle)
        self.config.set_vehicle_overlay(vehicle, overlay["scale"],
                                         overlay["offset_x"], overlay["offset_y"],
                                         opacity=percent / 100.0)
        self._update_overlay_preview()

    def _update_overlay_preview(self):
        """实时更新 overlay 预览（get_effective_overlay 已封装二选一逻辑，总是刷新）"""
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        # 通过 state_machine 强制刷新 overlay（不改变状态）
        self.state.refresh_overlay()

    def _on_tag_list_context_menu(self, pos):
        item = self.tag_list.itemAt(pos)
        if not item:
            self.tag_list.clearSelection()
            return
        tag = item.text()
        if tag == "全部标签" or tag == self.FAVORITE_TAG:
            self.tag_list.clearSelection()
            return
        menu = QMenu(self)
        action_up = menu.addAction("上移")
        action_down = menu.addAction("下移")
        menu.addSeparator()
        action_rename = menu.addAction("重命名")
        menu.addSeparator()
        action_delete = menu.addAction("删除标签")
        chosen = menu.exec_(self.tag_list.viewport().mapToGlobal(pos))
        if chosen in (action_up, action_down):
            # 用不含收藏的列表操作，收藏固定在第一位
            all_tags = self.config.get_all_tags()
            other_tags = [t for t in all_tags if t != self.FAVORITE_TAG]
            if tag in other_tags:
                idx = other_tags.index(tag)
                if chosen == action_up and idx > 0:
                    other_tags[idx], other_tags[idx - 1] = other_tags[idx - 1], other_tags[idx]
                elif chosen == action_down and idx < len(other_tags) - 1:
                    other_tags[idx], other_tags[idx + 1] = other_tags[idx + 1], other_tags[idx]
                else:
                    self.tag_list.clearSelection()
                    return
                new_order = [self.FAVORITE_TAG] + other_tags
                self.config.reorder_tags(new_order)
                self._refresh_tag_list()
        elif chosen == action_rename:
            new_name, ok = QInputDialog.getText(self, "重命名标签", "新名称:", text=tag)
            if ok and new_name.strip() and new_name.strip() != tag:
                self.config.rename_tag(tag, new_name.strip())
                self._refresh_tag_list()
                self._refresh_vehicle_list()
        elif chosen == action_delete:
            self._on_remove_tag()
        # 右键后清除选中高亮（右键不应触发筛选）
        self.tag_list.clearSelection()

    def _on_vehicle_list_context_menu(self, pos):
        item = self.vehicle_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        action_copy = menu.addAction("复制载具")
        action_rename = menu.addAction("重命名")
        menu.addSeparator()
        action_export = menu.addAction("导出载具")
        menu.addSeparator()
        action_delete = menu.addAction("删除载具")
        chosen = menu.exec_(self.vehicle_list.viewport().mapToGlobal(pos))
        if chosen == action_copy:
            self._on_copy_vehicle()
        elif chosen == action_rename:
            self._on_rename_vehicle()
        elif chosen == action_export:
            self._on_export_vehicle()
        elif chosen == action_delete:
            self._on_remove_vehicle()

    def _on_ammo_list_context_menu(self, pos):
        item = self.ammo_list.itemAt(pos)
        if not item:
            return
        # 先选中右键点击的项，确保 _on_remove_ammo 能拿到 currentItem
        self.ammo_list.setCurrentItem(item)
        ammo = item.data(Qt.UserRole)
        vehicle = self._get_selected_vehicle()
        if not vehicle or not ammo:
            return
        menu = QMenu(self)
        action_clear = menu.addAction("清除弹种UI绑定")
        action_clear.setEnabled(bool(self.config.get_ammo_ui(vehicle, ammo)))
        menu.addSeparator()
        action_delete = menu.addAction("删除弹种")
        chosen = menu.exec_(self.ammo_list.viewport().mapToGlobal(pos))
        if chosen == action_clear:
            self.config.set_ammo_ui(vehicle, ammo, "")
            self._refresh_ammo_list(keep_selection=True)
            self.state.refresh_overlay()
        elif chosen == action_delete:
            self._on_remove_ammo()

    def _on_mag_list_context_menu(self, pos):
        item = self.mag_list.itemAt(pos)
        if not item:
            return
        idx = item.data(Qt.UserRole)
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        if not vehicle or not ammo or idx is None:
            return
        menu = QMenu(self)
        action_clear = menu.addAction("清除准星绑定")
        action_clear.setEnabled(bool(self.config.get_crosshair_path(vehicle, ammo, idx)))
        menu.addSeparator()
        action_delete = menu.addAction("删除倍率")
        chosen = menu.exec_(self.mag_list.viewport().mapToGlobal(pos))
        if chosen == action_clear:
            self.config.set_crosshair_path(vehicle, ammo, idx, "")
            self._refresh_mag_list(keep_selection=True)
            self._update_mag_detail()
            self.state.refresh_overlay()
        elif chosen == action_delete:
            self._on_remove_mag()

    def _on_bind_ammo_ui(self):
        from PyQt5.QtWidgets import QFileDialog
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        if not vehicle or not ammo:
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择弹种 UI 图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            dest_name = self.resources.import_resource(path)
            if dest_name:
                self.config.set_ammo_ui(vehicle, ammo, dest_name)
                self._refresh_ammo_list(keep_selection=True)
                self.state.refresh_overlay()

    def _on_overlay_ammo_ui_changed(self, _state):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        idx = item.data(Qt.UserRole)
        self.config.set_overlay_ammo_ui(vehicle, ammo, idx, self.overlay_ammo_ui_check.isChecked())
        self._refresh_mag_list(keep_selection=True)

    def _on_overlay_vehicle_ui_changed(self, _state):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        idx = item.data(Qt.UserRole)
        self.config.set_overlay_vehicle_ui(vehicle, ammo, idx, self.overlay_vehicle_ui_check.isChecked())
        self._refresh_mag_list(keep_selection=True)

    def _on_bind_vehicle_ui(self):
        from PyQt5.QtWidgets import QFileDialog
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择载具 UI 图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            dest_name = self.resources.import_resource(path)
            if dest_name:
                self.config.set_vehicle_ui(vehicle, dest_name)
                self._refresh_vehicle_ui_list()
                self.state.refresh_overlay()

    def _on_clear_vehicle_ui(self):
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        self.config.set_vehicle_ui(vehicle, "")
        self._refresh_vehicle_ui_list()
        self.state.refresh_overlay()

    def _refresh_vehicle_ui_list(self):
        """载具图片列表刷新：SSOT，载具名从选中载具动态获取"""
        vehicle = self._get_selected_vehicle()
        self.vehicle_ui_list.clear()
        if vehicle:
            vehicle_ui = self.config.get_vehicle_ui(vehicle)
            sub = vehicle_ui if vehicle_ui else "双击绑定图片"
            self.vehicle_ui_list.add_item(vehicle, sub)
            self.vehicle_ui_list.setCurrentRow(0)

    def _on_vehicle_ui_list_context_menu(self, pos):
        """载具图片列表右键菜单：清除绑定 + 载具操作（复制/重命名/导出/删除）"""
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        menu = QMenu(self)
        action_clear = menu.addAction("清除载具图片绑定")
        action_clear.setEnabled(bool(self.config.get_vehicle_ui(vehicle)))
        menu.addSeparator()
        action_copy = menu.addAction("复制载具")
        action_rename = menu.addAction("重命名")
        menu.addSeparator()
        action_export = menu.addAction("导出载具")
        menu.addSeparator()
        action_delete = menu.addAction("删除载具")
        chosen = menu.exec_(self.vehicle_ui_list.viewport().mapToGlobal(pos))
        if chosen == action_clear:
            self.config.set_vehicle_ui(vehicle, "")
            self._refresh_vehicle_ui_list()
            self.state.refresh_overlay()
        elif chosen == action_copy:
            self._on_copy_vehicle()
        elif chosen == action_rename:
            self._on_rename_vehicle()
        elif chosen == action_export:
            self._on_export_vehicle()
        elif chosen == action_delete:
            self._on_remove_vehicle()

    def _on_bind_crosshair(self):
        from PyQt5.QtWidgets import QFileDialog
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        idx = item.data(Qt.UserRole)
        path, _ = QFileDialog.getOpenFileName(self, "选择准星图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            dest_name = self.resources.import_resource(path)
            if dest_name:
                self.config.set_crosshair_path(vehicle, ammo, idx, dest_name)
                self._refresh_mag_list(keep_selection=True)
                self._update_mag_detail()
                self.data_changed.emit()
                self.state.refresh_overlay()

    def refresh(self):
        self._refresh_tag_list()
        self._refresh_vehicle_list()
        self.data_changed.emit()
