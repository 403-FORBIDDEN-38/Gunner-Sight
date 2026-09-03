"""载具配置页：标签列表、载具列表、弹种列表、倍率列表"""
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QLabel, QFormLayout,
    QMessageBox, QInputDialog, QAbstractItemView,
    QSlider, QSpinBox, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal

from core.config_manager import ConfigManager
from core.resource_manager import ResourceManager
from core.state_machine import StateMachine
from gui.widgets import OptimizedListWidget


class VehicleConfigTab(QWidget):
    data_changed = pyqtSignal()

    def __init__(self, config: ConfigManager, state: StateMachine,
                 resources: ResourceManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.state = state
        self.resources = resources
        self._tag_check_just_changed = False
        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 标签列
        tag_panel = QGroupBox("标签列表")
        tag_layout = QVBoxLayout(tag_panel)
        tag_layout.setContentsMargins(8, 12, 8, 8)
        tag_layout.setSpacing(5)
        self.tag_list = OptimizedListWidget()
        self.tag_list.setSelectionMode(QAbstractItemView.SingleSelection)
        tag_layout.addWidget(self.tag_list, 1)
        tag_input_layout = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("点击创建标签")
        tag_input_layout.addWidget(self.tag_input, 1)
        self.add_tag_btn = QPushButton("+")
        self.add_tag_btn.setFixedWidth(32)
        tag_input_layout.addWidget(self.add_tag_btn)
        tag_layout.addLayout(tag_input_layout)
        tag_btn_layout = QHBoxLayout()
        self.rename_tag_btn = QPushButton("重命名")
        self.remove_tag_btn = QPushButton("删除")
        tag_btn_layout.addWidget(self.rename_tag_btn, 1)
        tag_btn_layout.addWidget(self.remove_tag_btn, 1)
        tag_layout.addLayout(tag_btn_layout)

        # 载具列
        vehicle_panel = QGroupBox("载具列表")
        vehicle_layout = QVBoxLayout(vehicle_panel)
        vehicle_layout.setContentsMargins(8, 12, 8, 8)
        vehicle_layout.setSpacing(5)
        self.vehicle_search = QLineEdit()
        self.vehicle_search.setPlaceholderText("搜索载具...")
        vehicle_layout.addWidget(self.vehicle_search)
        self.vehicle_list = OptimizedListWidget()
        vehicle_layout.addWidget(self.vehicle_list, 1)
        vehicle_btn_layout = QHBoxLayout()
        self.add_vehicle_btn = QPushButton("添加")
        self.copy_vehicle_btn = QPushButton("复制")
        self.rename_vehicle_btn = QPushButton("重命名")
        self.remove_vehicle_btn = QPushButton("删除")
        vehicle_btn_layout.addWidget(self.add_vehicle_btn)
        vehicle_btn_layout.addWidget(self.copy_vehicle_btn)
        vehicle_btn_layout.addWidget(self.rename_vehicle_btn)
        vehicle_btn_layout.addWidget(self.remove_vehicle_btn)
        vehicle_layout.addLayout(vehicle_btn_layout)

        # 弹种+倍率列
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        ammo_group = QGroupBox("弹种列表")
        ammo_layout = QVBoxLayout(ammo_group)
        self.ammo_list = OptimizedListWidget()
        ammo_layout.addWidget(self.ammo_list, 1)
        ammo_btn_layout = QHBoxLayout()
        self.add_ammo_btn = QPushButton("添加")
        self.rename_ammo_btn = QPushButton("重命名")
        self.remove_ammo_btn = QPushButton("删除")
        ammo_btn_layout.addWidget(self.add_ammo_btn)
        ammo_btn_layout.addWidget(self.rename_ammo_btn)
        ammo_btn_layout.addWidget(self.remove_ammo_btn)
        ammo_layout.addLayout(ammo_btn_layout)
        right_layout.addWidget(ammo_group, 1)

        mag_group = QGroupBox("倍率列表")
        mag_layout = QVBoxLayout(mag_group)
        self.mag_list = OptimizedListWidget()
        mag_layout.addWidget(self.mag_list, 1)
        mag_btn_layout = QHBoxLayout()
        self.add_mag_btn = QPushButton("添加")
        self.rename_mag_btn = QPushButton("重命名")
        self.remove_mag_btn = QPushButton("删除")
        mag_btn_layout.addWidget(self.add_mag_btn)
        mag_btn_layout.addWidget(self.rename_mag_btn)
        mag_btn_layout.addWidget(self.remove_mag_btn)
        mag_layout.addLayout(mag_btn_layout)
        mag_detail_layout = QVBoxLayout()
        # 准星图片行
        crosshair_row = QHBoxLayout()
        crosshair_row.addWidget(QLabel("准星图片:"))
        self.mag_crosshair_label = QLabel("未绑定")
        self.mag_crosshair_label.setWordWrap(True)
        crosshair_row.addWidget(self.mag_crosshair_label)
        crosshair_row.addStretch()
        mag_detail_layout.addLayout(crosshair_row)
        # 选择按钮
        self.mag_bind_btn = QPushButton("选择准星图片")
        mag_detail_layout.addWidget(self.mag_bind_btn)
        # 缩放偏移模式勾选框
        self.overlay_mode_check = QCheckBox("该倍率使用载具缩放配置")
        mag_detail_layout.addWidget(self.overlay_mode_check)
        mag_layout.addLayout(mag_detail_layout)
        right_layout.addWidget(mag_group, 2)

        # 载具缩放偏移区域
        self.vehicle_overlay_group = QGroupBox("载具缩放偏移")
        vo_layout = QVBoxLayout(self.vehicle_overlay_group)
        # 缩放滑块
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("缩放:"))
        self.vo_scale_slider = QSlider(Qt.Horizontal)
        self.vo_scale_slider.setRange(1, 1000)
        self.vo_scale_slider.setValue(100)
        self.vo_scale_spin = QSpinBox()
        self.vo_scale_spin.setRange(1, 1000)
        self.vo_scale_spin.setSuffix("%")
        self.vo_scale_spin.setValue(100)
        self.vo_scale_spin.setFixedWidth(80)
        scale_layout.addWidget(self.vo_scale_slider, 1)
        scale_layout.addWidget(self.vo_scale_spin)
        vo_layout.addLayout(scale_layout)
        # X/Y 偏移
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(QLabel("X偏移:"))
        self.vo_offset_x = QSpinBox()
        self.vo_offset_x.setRange(-500, 500)
        offset_layout.addWidget(self.vo_offset_x)
        offset_layout.addWidget(QLabel("Y偏移:"))
        self.vo_offset_y = QSpinBox()
        self.vo_offset_y.setRange(-500, 500)
        offset_layout.addWidget(self.vo_offset_y)
        vo_layout.addLayout(offset_layout)
        # 说明文字
        vo_hint = QLabel('倍率选"载具"时使用此配置')
        vo_hint.setStyleSheet("color: gray; font-size: 11px;")
        vo_layout.addWidget(vo_hint)
        right_layout.addWidget(self.vehicle_overlay_group, 1)

        layout.addWidget(tag_panel, 1)
        layout.addWidget(vehicle_panel, 2)
        layout.addWidget(right_panel, 3)

    def connect_signals(self):
        # 载具
        self.add_vehicle_btn.clicked.connect(self._on_add_vehicle)
        self.copy_vehicle_btn.clicked.connect(self._on_copy_vehicle)
        self.rename_vehicle_btn.clicked.connect(self._on_rename_vehicle)
        self.remove_vehicle_btn.clicked.connect(self._on_remove_vehicle)
        self.vehicle_list.currentItemChanged.connect(self._on_vehicle_selected)
        self.vehicle_search.textChanged.connect(self._on_vehicle_search)
        # 标签
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        self.tag_list.itemChanged.connect(self._on_tag_check_changed)
        self.add_tag_btn.clicked.connect(self._on_add_tag)
        self.tag_input.returnPressed.connect(self._on_add_tag)
        self.rename_tag_btn.clicked.connect(self._on_rename_tag)
        self.remove_tag_btn.clicked.connect(self._on_remove_tag)
        # 弹种
        self.add_ammo_btn.clicked.connect(self._on_add_ammo)
        self.rename_ammo_btn.clicked.connect(self._on_rename_ammo)
        self.remove_ammo_btn.clicked.connect(self._on_remove_ammo)
        self.ammo_list.currentItemChanged.connect(self._on_ammo_selected)
        # 倍率
        self.add_mag_btn.clicked.connect(self._on_add_mag)
        self.rename_mag_btn.clicked.connect(self._on_rename_mag)
        self.remove_mag_btn.clicked.connect(self._on_remove_mag)
        self.mag_list.currentItemChanged.connect(self._on_mag_selected)
        self.mag_list.itemDoubleClicked.connect(lambda _item: self._on_bind_crosshair())
        self.mag_bind_btn.clicked.connect(self._on_bind_crosshair)
        self.overlay_mode_check.stateChanged.connect(self._on_overlay_mode_changed)
        # 载具缩放偏移
        self.vo_scale_slider.valueChanged.connect(self._on_vehicle_scale_slider_changed)
        self.vo_scale_spin.valueChanged.connect(self._on_vehicle_scale_spin_changed)
        self.vo_offset_x.valueChanged.connect(self._on_vehicle_offset_changed)
        self.vo_offset_y.valueChanged.connect(self._on_vehicle_offset_changed)

    # === 标签 ===
    def _refresh_tag_list(self):
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        all_item = QListWidgetItem("全部标签")
        all_item.setData(Qt.UserRole, "__all__")
        self.tag_list.addItem(all_item)
        for tag in self.config.get_all_tags():
            item = QListWidgetItem(tag)
            item.setData(Qt.UserRole, tag)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.tag_list.addItem(item)
        self.tag_list.blockSignals(False)

    def _on_tag_clicked(self, item):
        if self._tag_check_just_changed:
            self._tag_check_just_changed = False
            return
        tag = item.data(Qt.UserRole)
        if tag == "__all__":
            self.vehicle_list.clearSelection()
            self._refresh_vehicle_list()
        else:
            self._refresh_vehicle_list(tag_filter=tag)

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

    def _on_add_tag(self):
        name = self.tag_input.text().strip()
        if name and self.config.add_tag(name):
            self.tag_input.clear()
            self._refresh_tag_list()

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

    # === 载具 ===
    def _get_selected_vehicle(self):
        item = self.vehicle_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _refresh_vehicle_list(self, tag_filter=None):
        search = self.vehicle_search.text()
        if tag_filter is None:
            tag_item = self.tag_list.currentItem()
            if tag_item and tag_item.data(Qt.UserRole) != "__all__":
                tag_filter = tag_item.data(Qt.UserRole)
        names = self.config.get_vehicle_names_filtered(search, tag_filter or "")
        # 记录当前选中的载具，重建后恢复（切走再切回时保持状态一致）
        previously_selected = self._get_selected_vehicle()
        self.vehicle_list.blockSignals(True)
        self.vehicle_list.clear()
        for name in names:
            tags = self.config.get_vehicle_tags(name)
            display = f"{name}  ({','.join(tags)})" if tags else name
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, name)
            self.vehicle_list.addItem(item)
        self.vehicle_list.blockSignals(False)
        # 恢复之前选中的载具（在 blockSignals(False) 之后，确保触发 currentItemChanged 刷新弹种/倍率）
        if previously_selected:
            for i in range(self.vehicle_list.count()):
                if self.vehicle_list.item(i).data(Qt.UserRole) == previously_selected:
                    self.vehicle_list.setCurrentRow(i)
                    break
        self._update_tag_checkboxes()

    def _update_tag_checkboxes(self):
        vehicle = self._get_selected_vehicle()
        tags = set(self.config.get_vehicle_tags(vehicle)) if vehicle else set()
        self.tag_list.blockSignals(True)
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            if item.data(Qt.UserRole) != "__all__":
                item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in tags else Qt.Unchecked)
        self.tag_list.blockSignals(False)

    def _on_vehicle_search(self, _text):
        self._refresh_vehicle_list()

    def _on_vehicle_selected(self, current, _previous):
        if current:
            self._update_tag_checkboxes()
        self._refresh_ammo_list()
        self._refresh_mag_list()
        self._update_vehicle_overlay_ui()

    def _on_add_vehicle(self):
        name, ok = QInputDialog.getText(self, "添加载具", "载具名称:")
        if ok and name.strip():
            name = name.strip()
            if self.config.add_vehicle(name):
                self._refresh_vehicle_list()
                # 选中新载具
                for i in range(self.vehicle_list.count()):
                    if self.vehicle_list.item(i).text() == name:
                        self.vehicle_list.setCurrentRow(i)
                        break
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
            if self.config.copy_vehicle(current, name):
                self._refresh_vehicle_list()
                # 选中新复制的载具
                for i in range(self.vehicle_list.count()):
                    if self.vehicle_list.item(i).text() == name:
                        self.vehicle_list.setCurrentRow(i)
                        break
            else:
                QMessageBox.warning(self, "提示", f"载具 '{name}' 已存在！")

    def _on_rename_vehicle(self):
        current = self._get_selected_vehicle()
        if not current:
            return
        name, ok = QInputDialog.getText(self, "重命名载具", "新名称:", text=current)
        if ok and name.strip() and name != current:
            if self.config.rename_vehicle(current, name.strip()):
                self._refresh_vehicle_list()
            else:
                QMessageBox.warning(self, "提示", f"载具 '{name.strip()}' 已存在！")

    def _on_remove_vehicle(self):
        current = self._get_selected_vehicle()
        if not current:
            return
        reply = QMessageBox.question(self, "确认", f"删除载具 '{current}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.config.remove_vehicle(current)
            self._refresh_vehicle_list()
            self._refresh_ammo_list()
            self._refresh_mag_list()

    # === 弹种 ===
    def _refresh_ammo_list(self):
        vehicle = self._get_selected_vehicle()
        self.ammo_list.blockSignals(True)
        self.ammo_list.clear()
        if vehicle:
            for ammo in self.config.get_ammo_types(vehicle):
                item = QListWidgetItem(ammo)
                item.setData(Qt.UserRole, ammo)
                self.ammo_list.addItem(item)
        self.ammo_list.blockSignals(False)

    def _on_ammo_selected(self, current, _previous):
        self._refresh_mag_list()

    def _on_add_ammo(self):
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        name, ok = QInputDialog.getText(self, "添加弹种", "弹种名称:")
        if ok and name.strip():
            self.config.add_ammo_type(vehicle, name.strip())
            self._refresh_ammo_list()

    def _on_rename_ammo(self):
        vehicle = self._get_selected_vehicle()
        item = self.ammo_list.currentItem()
        if not vehicle or not item:
            return
        old = item.data(Qt.UserRole)
        new, ok = QInputDialog.getText(self, "重命名弹种", "新名称:", text=old)
        if ok and new.strip() and new != old:
            self.config.rename_ammo_type(vehicle, old, new.strip())
            self._refresh_ammo_list()

    def _on_remove_ammo(self):
        vehicle = self._get_selected_vehicle()
        item = self.ammo_list.currentItem()
        if not vehicle or not item:
            return
        ammo = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "确认", f"删除弹种 '{ammo}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.config.remove_ammo_type(vehicle, ammo)
            self._refresh_ammo_list()

    # === 倍率 ===
    def _get_selected_ammo(self):
        item = self.ammo_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _refresh_mag_list(self, select_idx=None):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        self.mag_list.blockSignals(True)
        self.mag_list.clear()
        if vehicle and ammo:
            for i, mag in enumerate(self.config.get_magnifications(vehicle, ammo)):
                label = mag.get("label", f"倍率{i+1}")
                ch = mag.get("crosshair", "")
                mode = "载具" if mag.get("use_vehicle_overlay", False) else "全局"
                ch_part = ch if ch else "未绑定"
                display = f"{label}  —  {ch_part}  —  [{mode}]"
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, i)
                self.mag_list.addItem(item)
        if select_idx is not None and 0 <= select_idx < self.mag_list.count():
            self.mag_list.setCurrentRow(select_idx)
        self.mag_list.blockSignals(False)
        self._update_mag_detail()

    def _update_mag_detail(self):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            self.mag_crosshair_label.setText("未绑定")
            self.overlay_mode_check.blockSignals(True)
            self.overlay_mode_check.setChecked(False)
            self.overlay_mode_check.blockSignals(False)
            return
        idx = item.data(Qt.UserRole)
        mags = self.config.get_magnifications(vehicle, ammo)
        if idx < len(mags):
            mag = mags[idx]
            crosshair = mag.get("crosshair", "")
            self.mag_crosshair_label.setText(crosshair if crosshair else "未绑定")
            # 更新缩放偏移模式勾选框
            use_vehicle = mag.get("use_vehicle_overlay", False)
            self.overlay_mode_check.blockSignals(True)
            self.overlay_mode_check.setChecked(use_vehicle)
            self.overlay_mode_check.blockSignals(False)

    def _on_mag_selected(self, _current, _previous):
        self._update_mag_detail()

    def _on_add_mag(self):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        if not vehicle or not ammo:
            return
        self.config.add_magnification(vehicle, ammo)
        self._refresh_mag_list()

    def _on_remove_mag(self):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        idx = item.data(Qt.UserRole)
        self.config.remove_magnification(vehicle, ammo, idx)
        self._refresh_mag_list()

    def _update_mag_item_text(self, idx):
        """仅更新指定倍率项的显示文本，不全量重建列表"""
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        if not vehicle or not ammo:
            return
        mags = self.config.get_magnifications(vehicle, ammo)
        if idx >= len(mags):
            return
        item = self.mag_list.item(idx)
        if not item:
            return
        mag = mags[idx]
        label = mag.get("label", f"倍率{idx+1}")
        ch = mag.get("crosshair", "")
        mode = "载具" if mag.get("use_vehicle_overlay", False) else "全局"
        ch_part = ch if ch else "未绑定"
        item.setText(f"{label}  —  {ch_part}  —  [{mode}]")

    def _on_rename_mag(self):
        vehicle = self._get_selected_vehicle()
        ammo = self._get_selected_ammo()
        item = self.mag_list.currentItem()
        if not vehicle or not ammo or not item:
            return
        idx = item.data(Qt.UserRole)
        mags = self.config.get_magnifications(vehicle, ammo)
        if idx >= len(mags):
            return
        old_label = mags[idx].get("label", f"倍率{idx+1}")
        new_label, ok = QInputDialog.getText(self, "重命名倍率", "新名称:", text=old_label)
        if ok and new_label.strip() and new_label.strip() != old_label:
            self.config.update_magnification(vehicle, ammo, idx, label=new_label.strip())
            self._update_mag_item_text(idx)

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
        self._update_mag_item_text(idx)
        self._update_overlay_preview()

    def _update_vehicle_overlay_ui(self):
        """切换载具时更新载具缩放偏移区域的标题和数值"""
        vehicle = self._get_selected_vehicle()
        if vehicle:
            self.vehicle_overlay_group.setTitle(f"载具缩放偏移 — {vehicle}")
            overlay = self.config.get_vehicle_overlay(vehicle)
            self.vo_scale_slider.blockSignals(True)
            self.vo_scale_spin.blockSignals(True)
            self.vo_offset_x.blockSignals(True)
            self.vo_offset_y.blockSignals(True)
            self.vo_scale_slider.setValue(int(overlay["scale"]))
            self.vo_scale_spin.setValue(int(overlay["scale"]))
            self.vo_offset_x.setValue(overlay["offset_x"])
            self.vo_offset_y.setValue(overlay["offset_y"])
            self.vo_scale_slider.blockSignals(False)
            self.vo_scale_spin.blockSignals(False)
            self.vo_offset_x.blockSignals(False)
            self.vo_offset_y.blockSignals(False)
        else:
            self.vehicle_overlay_group.setTitle("载具缩放偏移")

    def _on_vehicle_scale_slider_changed(self, value):
        """滑块变化：同步 spin + 保存配置 + 预览"""
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        self.vo_scale_spin.blockSignals(True)
        self.vo_scale_spin.setValue(value)
        self.vo_scale_spin.blockSignals(False)
        overlay = self.config.get_vehicle_overlay(vehicle)
        self.config.set_vehicle_overlay(vehicle, value, overlay["offset_x"], overlay["offset_y"])
        self._update_overlay_preview()

    def _on_vehicle_scale_spin_changed(self, value):
        """数值输入框变化：同步滑块 + 保存配置 + 预览"""
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        self.vo_scale_slider.blockSignals(True)
        self.vo_scale_slider.setValue(value)
        self.vo_scale_slider.blockSignals(False)
        overlay = self.config.get_vehicle_overlay(vehicle)
        self.config.set_vehicle_overlay(vehicle, value, overlay["offset_x"], overlay["offset_y"])
        self._update_overlay_preview()

    def _on_vehicle_offset_changed(self, _value):
        vehicle = self._get_selected_vehicle()
        if not vehicle:
            return
        overlay = self.config.get_vehicle_overlay(vehicle)
        self.config.set_vehicle_overlay(vehicle, overlay["scale"],
                                         self.vo_offset_x.value(), self.vo_offset_y.value())
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
                self.config.update_magnification(vehicle, ammo, idx, crosshair_path=dest_name)
                self._update_mag_item_text(idx)

    def refresh(self):
        self._refresh_tag_list()
        self._refresh_vehicle_list()
        self.data_changed.emit()
