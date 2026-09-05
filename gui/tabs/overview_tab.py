"""全局设置页：载具选择、准星预览、全局准星参数"""
from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFrame,
    QGroupBox, QLabel, QComboBox, QPushButton,
    QDoubleSpinBox, QSpinBox, QFormLayout
)
from PyQt5.QtCore import Qt

from core.config_manager import ConfigManager
from core.state_machine import StateMachine
from core.hotkey_manager import HotkeyManager
from core.resource_manager import ResourceManager
from core.overlay import OverlayRenderer
from gui.widgets import VehicleFilterWidget, CrosshairPreviewWidget, NoWheelSlider


class OverviewTab(QWidget):
    def __init__(self, config: ConfigManager, state: StateMachine,
                 hotkey: HotkeyManager, resources: ResourceManager,
                 overlay: OverlayRenderer = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.state = state
        self.hotkey = hotkey
        self.resources = resources
        self.overlay = overlay
        self._vf_created = False
        self._pending_vf_signals = None  # 优化4: 延迟连接的信号回调
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 载具选择（优化4: VehicleFilterWidget延迟创建，先占位）
        quick_group = QGroupBox("载具选择")
        quick_layout = QVBoxLayout(quick_group)
        self._vf_container = QWidget()
        self._vf_container.setMinimumHeight(300)
        vf_container_layout = QVBoxLayout(self._vf_container)
        vf_container_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.addWidget(self._vf_container)
        quick_ammo_row = QHBoxLayout()
        quick_ammo_row.addWidget(QLabel("弹种:"))
        self.quick_ammo_combo = QComboBox()
        quick_ammo_row.addWidget(self.quick_ammo_combo, 1)
        self.quick_mag_btn = QPushButton("切换倍率")
        quick_ammo_row.addWidget(self.quick_mag_btn)
        quick_layout.addLayout(quick_ammo_row)
        layout.addWidget(quick_group)

        # 准星预览
        preview_group = QGroupBox("准星预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_widget = CrosshairPreviewWidget()
        preview_layout.addWidget(self.preview_widget)
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("预览缩放:"))
        self.preview_scale_slider = NoWheelSlider(Qt.Horizontal)
        self.preview_scale_slider.setRange(10, 400)
        self.preview_scale_slider.setValue(100)
        self.preview_scale_label = QLabel("100%")
        self.preview_scale_label.setFixedWidth(50)
        scale_layout.addWidget(self.preview_scale_slider)
        scale_layout.addWidget(self.preview_scale_label)
        preview_layout.addLayout(scale_layout)
        layout.addWidget(preview_group)

        # 全局准星参数
        crosshair_group = QGroupBox("全局准星参数")
        crosshair_layout = QFormLayout(crosshair_group)
        scale_row = QHBoxLayout()
        self.scale_slider = NoWheelSlider(Qt.Horizontal)
        self.scale_slider.setRange(25, 400)
        self.scale_slider.setValue(100)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(1.0, 1000.0)
        self.scale_spin.setValue
        self.scale_spin.setSuffix(" %")
        self.scale_spin.setDecimals(1)
        self.scale_minus_btn = QPushButton("-"); self.scale_minus_btn.setFixedWidth(30)
        self.scale_plus_btn = QPushButton("+"); self.scale_plus_btn.setFixedWidth(30)
        scale_row.addWidget(self.scale_minus_btn)
        scale_row.addWidget(self.scale_spin)
        scale_row.addWidget(self.scale_slider)
        scale_row.addWidget(self.scale_plus_btn)
        crosshair_layout.addRow("全局缩放:", scale_row)

        offset_x_row = QHBoxLayout()
        self.offset_x_spin = QSpinBox(); self.offset_x_spin.setRange(-500, 500); self.offset_x_spin.setSuffix(" px")
        self.offset_x_minus_btn = QPushButton("-"); self.offset_x_minus_btn.setFixedWidth(30)
        self.offset_x_plus_btn = QPushButton("+"); self.offset_x_plus_btn.setFixedWidth(30)
        offset_x_row.addWidget(self.offset_x_minus_btn); offset_x_row.addWidget(self.offset_x_spin)
        offset_x_row.addWidget(self.offset_x_plus_btn); offset_x_row.addStretch()
        crosshair_layout.addRow("X轴偏移:", offset_x_row)

        offset_y_row = QHBoxLayout()
        self.offset_y_spin = QSpinBox(); self.offset_y_spin.setRange(-500, 500); self.offset_y_spin.setSuffix(" px")
        self.offset_y_minus_btn = QPushButton("-"); self.offset_y_minus_btn.setFixedWidth(30)
        self.offset_y_plus_btn = QPushButton("+"); self.offset_y_plus_btn.setFixedWidth(30)
        offset_y_row.addWidget(self.offset_y_minus_btn); offset_y_row.addWidget(self.offset_y_spin)
        offset_y_row.addWidget(self.offset_y_plus_btn); offset_y_row.addStretch()
        crosshair_layout.addRow("Y轴偏移:", offset_y_row)

        opacity_row = QHBoxLayout()
        self.opacity_slider = NoWheelSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(100)
        self.opacity_spin = QSpinBox(); self.opacity_spin.setRange(10, 100); self.opacity_spin.setSuffix(" %")
        self.opacity_minus_btn = QPushButton("-"); self.opacity_minus_btn.setFixedWidth(30)
        self.opacity_plus_btn = QPushButton("+"); self.opacity_plus_btn.setFixedWidth(30)
        opacity_row.addWidget(self.opacity_minus_btn); opacity_row.addWidget(self.opacity_spin)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_plus_btn); opacity_row.addStretch()
        crosshair_layout.addRow("叠加层透明度:", opacity_row)
        layout.addWidget(crosshair_group)
        layout.addStretch()


        # 内部信号
        self.scale_slider.valueChanged.connect(self._on_scale_slider)
        self.scale_spin.valueChanged.connect(self._on_scale_spin)
        self.scale_minus_btn.clicked.connect(lambda: self.scale_spin.setValue(self.scale_spin.value() - 1))
        self.scale_plus_btn.clicked.connect(lambda: self.scale_spin.setValue(self.scale_spin.value() + 1))
        self.offset_x_spin.valueChanged.connect(self._on_offset_x)
        self.offset_y_spin.valueChanged.connect(self._on_offset_y)
        self.offset_x_minus_btn.clicked.connect(lambda: self.offset_x_spin.setValue(self.offset_x_spin.value() - 1))
        self.offset_x_plus_btn.clicked.connect(lambda: self.offset_x_spin.setValue(self.offset_x_spin.value() + 1))
        self.offset_y_minus_btn.clicked.connect(lambda: self.offset_y_spin.setValue(self.offset_y_spin.value() - 1))
        self.offset_y_plus_btn.clicked.connect(lambda: self.offset_y_spin.setValue(self.offset_y_spin.value() + 1))
        self.opacity_slider.valueChanged.connect(self._on_opacity_slider)
        self.opacity_spin.valueChanged.connect(self._on_opacity_spin)
        self.opacity_minus_btn.clicked.connect(lambda: self.opacity_spin.setValue(self.opacity_spin.value() - 5))
        self.opacity_plus_btn.clicked.connect(lambda: self.opacity_spin.setValue(self.opacity_spin.value() + 5))
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _on_scale_slider(self, value):
        self.scale_spin.blockSignals(True)
        self.scale_spin.setValue(value)
        self.scale_spin.blockSignals(False)
        if self.overlay:
            self.overlay.update_scale(float(value))
        else:
            self.config.set_global_scale(float(value))

    def _on_scale_spin(self, value):
        self.scale_slider.blockSignals(True)
        self.scale_slider.setValue(int(value))
        self.scale_slider.blockSignals(False)
        if self.overlay:
            self.overlay.update_scale(value)
        else:
            self.config.set_global_scale(value)

    def _on_offset_x(self, value):
        if self.overlay:
            self.overlay.update_offset(value, self.offset_y_spin.value())
        else:
            self.config.set_global_offset_x(value)

    def _on_offset_y(self, value):
        if self.overlay:
            self.overlay.update_offset(self.offset_x_spin.value(), value)
        else:
            self.config.set_global_offset_y(value)

    def _on_opacity_slider(self, value):
        self.opacity_spin.blockSignals(True)
        self.opacity_spin.setValue(value)
        self.opacity_spin.blockSignals(False)
        self._apply_global_opacity(value)

    def _on_opacity_spin(self, value):
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(value)
        self.opacity_slider.blockSignals(False)
        self._apply_global_opacity(value)

    def _apply_global_opacity(self, percent):
        self.config.set_overlay_opacity(percent / 100.0)
        if self.overlay:
            self.overlay.refresh()

    def _ensure_vehicle_filter(self):
        """优化4: 首次调用时创建VehicleFilterWidget并连接延迟信号"""
        if self._vf_created:
            return
        self.quick_vf = VehicleFilterWidget(mode="select")
        self.quick_vf.setMinimumHeight(300)
        self._vf_container.layout().addWidget(self.quick_vf)
        self._vf_created = True
        if self._pending_vf_signals:
            on_vehicle_changed, on_ammo_changed, on_preview_scale = self._pending_vf_signals
            self.quick_vf.vehicle_selected.connect(on_vehicle_changed)
            self.quick_vf.filter_changed.connect(self.refresh_vehicle_list)
            self._pending_vf_signals = None

    def connect_signals(self, on_vehicle_changed, on_ammo_changed, on_preview_scale):
        """连接跨 tab 信号（由 main_window 调用）"""
        # 优化4: VehicleFilterWidget可能未创建，先保存回调
        self._pending_vf_signals = (on_vehicle_changed, on_ammo_changed, on_preview_scale)
        if self._vf_created:
            self.quick_vf.vehicle_selected.connect(on_vehicle_changed)
            self.quick_vf.filter_changed.connect(self.refresh_vehicle_list)
        self.quick_ammo_combo.currentTextChanged.connect(on_ammo_changed)
        self.quick_mag_btn.clicked.connect(self.state.cycle_magnification)
        self.preview_scale_slider.valueChanged.connect(on_preview_scale)

    def refresh_vehicle_list(self):
        self._ensure_vehicle_filter()
        self.quick_vf.set_tags(self.config.get_all_tags())
        search, tag = self.quick_vf.get_filter()
        names = self.config.get_vehicle_names_filtered(search, tag)
        self.quick_vf.populate(
            [(n, self.config.get_vehicle_tags(n)) for n in names],
            select_name=self.state.current_vehicle)

    def refresh_ammo(self):
        """仅更新弹种下接框（弹种变化时调用，避免全量刷新载具列表）"""
        vehicle = self.state.current_vehicle
        ammo = self.state.current_ammo_type
        self.quick_ammo_combo.blockSignals(True)
        self.quick_ammo_combo.clear()
        if vehicle:
            ammos = self.config.get_ammo_types(vehicle)
            self.quick_ammo_combo.addItems(ammos)
            if ammo in ammos:
                self.quick_ammo_combo.setCurrentText(ammo)
        self.quick_ammo_combo.blockSignals(False)

    def refresh(self):
        """全量刷新"""
        self.refresh_vehicle_list()
        self.refresh_ammo()
        # 全局参数
        self.scale_slider.blockSignals(True)
        self.scale_spin.blockSignals(True)
        s = self.config.get_global_scale()
        self.scale_slider.setValue(int(s))
        self.scale_spin.setValue(s)
        self.scale_slider.blockSignals(False)
        self.scale_spin.blockSignals(False)
        ox = self.config.get_global_offset_x()
        oy = self.config.get_global_offset_y()
        self.offset_x_spin.blockSignals(True)
        self.offset_x_spin.setValue(ox)
        self.offset_x_spin.blockSignals(False)
        self.offset_y_spin.blockSignals(True)
        self.offset_y_spin.setValue(oy)
        self.offset_y_spin.blockSignals(False)
        op = int(self.config.get_overlay_opacity() * 100)
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(op)
        self.opacity_slider.blockSignals(False)
        self.opacity_spin.blockSignals(True)
        self.opacity_spin.setValue(op)
        self.opacity_spin.blockSignals(False)

    def refresh_preview(self):
        """刷新准星预览（多条目 QPixmap 缓存，循环切换不重复加载）"""
        from pathlib import Path
        from PyQt5.QtGui import QPixmap
        if not hasattr(self, '_preview_cache'):
            self._preview_cache = {}
        path = self.state.get_current_crosshair_path()
        if not path or not Path(path).exists():
            self.preview_widget.set_crosshair(None)
            return
        if path not in self._preview_cache:
            # 缓存上限保护：超过 30 项清空（准星图片通常很少）
            if len(self._preview_cache) >= 30:
                self._preview_cache.clear()
            self._preview_cache[path] = QPixmap(path)
        self.preview_widget.set_crosshair(self._preview_cache[path])

    def showEvent(self, event):
        super().showEvent(event)
        # 优化3: 准星预览异步加载，不阻塞窗口首次绘制
        if not hasattr(self, '_preview_loaded') or not self._preview_loaded:
            self._preview_loaded = True
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self.refresh_preview)
        # 优化4: VehicleFilterWidget延迟创建
        self._ensure_vehicle_filter()
