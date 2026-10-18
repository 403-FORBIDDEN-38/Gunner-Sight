"""准星面板：载具选择、弹种切换、准星预览与缩放控制"""
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.overlay import OverlayRenderer
from core.resource_manager import ResourceManager
from core.state_machine import StateMachine
from gui.widgets import LinkedSpinSlider, make_group_box, make_scroll_area, VehicleFilterWidget


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
        self._suppress_ammo_combo_writeback = False
        self.ammo_wheel = None  # 由 showEvent 从 window 懒注入（滚轮在后台任务才创建）
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, content, layout = make_scroll_area(spacing=10)

        # 载具选择（优化4: VehicleFilterWidget延迟创建，先占位）
        quick_group, quick_layout = make_group_box("载具选择", flat=True)

        self._vf_container = QWidget()
        self._vf_container.setMinimumHeight(300)
        vf_container_layout = QVBoxLayout(self._vf_container)
        vf_container_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.addWidget(self._vf_container, 1)
        quick_ammo_row = QHBoxLayout()
        quick_ammo_row.addWidget(QLabel("弹种:"))
        self.quick_ammo_combo = QComboBox()
        quick_ammo_row.addWidget(self.quick_ammo_combo, 1)
        self.quick_mag_btn = QPushButton("切换倍率")
        quick_ammo_row.addWidget(self.quick_mag_btn)
        quick_layout.addLayout(quick_ammo_row)
        layout.addWidget(quick_group, 1)

        # 准星参数（全局默认，无载例覆盖时生效）——从适配tab移回，用户主要在此调节
        rg, rl = make_group_box("准星参数", layout_cls=QFormLayout)
        self.size_ctl = LinkedSpinSlider((1.0, 1000.0), slider_range=(1, 1000),
                                         decimals=1, suffix=" %")
        self.offset_x_ctl = LinkedSpinSlider((-2000, 2000), suffix=" px")
        self.offset_y_ctl = LinkedSpinSlider((-2000, 2000), suffix=" px")
        self.opacity_ctl = LinkedSpinSlider((10, 100), suffix=" %")
        rl.addRow("大小缩放:", self.size_ctl)
        rl.addRow("横向偏移:", self.offset_x_ctl)
        rl.addRow("竖向偏移:", self.offset_y_ctl)
        rl.addRow("不透明度:", self.opacity_ctl)
        layout.addWidget(rg)

        # 滚轮窗口：调整滚轮三个悬浮窗（弹种栏/预选列表/倍率挂件）的整体偏移（以屏幕中心为基准）
        wg, wl = make_group_box("滚轮窗口", flat=True, layout_cls=QFormLayout)
        self.wheel_x_ctl = QSpinBox()
        self.wheel_x_ctl.setRange(-2000, 2000)
        self.wheel_x_ctl.setSuffix(" px")
        self.wheel_y_ctl = QSpinBox()
        self.wheel_y_ctl.setRange(-2000, 2000)
        self.wheel_y_ctl.setSuffix(" px")
        wl.addRow("横向偏移:", self.wheel_x_ctl)
        wl.addRow("纵向偏移:", self.wheel_y_ctl)
        layout.addWidget(wg)

        self._connect_crosshair_params()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _ensure_vehicle_filter(self):
        """优化4: 首次调用时创建VehicleFilterWidget并连接延迟信号"""
        if self._vf_created:
            return
        self.quick_vf = VehicleFilterWidget(mode="select")
        self.quick_vf.setMinimumHeight(300)
        self._vf_container.layout().addWidget(self.quick_vf, 1)
        self._vf_created = True
        if self._pending_vf_signals:
            on_vehicle_changed = self._pending_vf_signals[0]
            self.quick_vf.vehicle_selected.connect(on_vehicle_changed)
            self.quick_vf.filter_changed.connect(self.refresh_vehicle_list)
            self._pending_vf_signals = None

    def _connect_ui_signals(self, on_vehicle_changed):
        """连接跨 tab 信号（由 main_window 调用）"""
        # 优化4: VehicleFilterWidget可能未创建，先保存回调
        self._pending_vf_signals = (on_vehicle_changed,)
        if self._vf_created:
            self.quick_vf.vehicle_selected.connect(on_vehicle_changed)
            self.quick_vf.filter_changed.connect(self.refresh_vehicle_list)
        self.quick_ammo_combo.currentTextChanged.connect(
            self._on_ammo_combo_user_selected)
        self.quick_mag_btn.clicked.connect(self.state.cycle_magnification)

    def refresh_vehicle_list(self):
        self._ensure_vehicle_filter()
        self.quick_vf.set_tags(self.config.get_all_tags())
        search, tag = self.quick_vf.get_filter()
        names = self.config.get_vehicle_names_filtered(search, tag)
        self.quick_vf.populate(
            [(n, self.config.get_vehicle_tags(n)) for n in names],
            select_name=self.state.current_vehicle)

    def sync_vehicle_selection(self):
        """只同步选中项，不重新 populate（状态机载具变化时用）"""
        if not getattr(self, 'quick_vf', None):
            return
        self.quick_vf.set_selected(self.state.current_vehicle)

    def refresh_tag_filter(self):
        """标签增删改后，重填 tag_filter 下拉"""
        if not getattr(self, 'quick_vf', None):
            return
        self.quick_vf.set_tags(self.config.get_all_tags())

    def _on_ammo_combo_user_selected(self, text):
        """用户选择触发：只写 state，不做任何刷新"""
        if self._suppress_ammo_combo_writeback:
            return
        if text == self.state.current_ammo_type:
            return
        self.state.set_ammo_type(text)

    def refresh_ammo(self):
        """state 信号触发：同步弹种下拉框"""
        vehicle = self.state.current_vehicle
        ammo = self.state.current_ammo_type
        # rebuild 用 blockSignals（clear + addItems 过程中每 addItem 一次就触发一次 currentTextChanged）
        self.quick_ammo_combo.blockSignals(True)
        try:
            self.quick_ammo_combo.clear()
            if vehicle:
                self.quick_ammo_combo.addItems(
                    self.config.get_ammo_types(vehicle))
        finally:
            self.quick_ammo_combo.blockSignals(False)
        # 恢复选中用 flag（不用 blockSignals）：
        # setCurrentText 会触发 currentTextChanged，
        # 用 _suppress_ammo_combo_writeback 拦截回写 state。
        # 不这样做会和 on_external_ammo_changed 形成循环。
        self._suppress_ammo_combo_writeback = True
        try:
            if ammo and self.quick_ammo_combo.currentText() != ammo:
                self.quick_ammo_combo.setCurrentText(ammo)
        finally:
            self._suppress_ammo_combo_writeback = False

    def _connect_crosshair_params(self):
        """连接准星参数控件信号（内部使用，不需main_window中介）"""
        self.size_ctl.value_changed.connect(self._on_size_changed)
        self.offset_x_ctl.value_changed.connect(self._on_offset_x_changed)
        self.offset_y_ctl.value_changed.connect(self._on_offset_y_changed)
        self.opacity_ctl.value_changed.connect(self._on_opacity_changed)
        self.wheel_x_ctl.valueChanged.connect(self._on_wheel_offset_changed)
        self.wheel_y_ctl.valueChanged.connect(self._on_wheel_offset_changed)

    def _on_size_changed(self, v):
        self.config.set_global_scale(float(v))
        if self.overlay: self.overlay.update_scale(float(v))

    def _on_offset_x_changed(self, v):
        self.config.set_global_offset_x(int(v))
        if self.overlay: self.overlay.update_offset(int(v), self.offset_y_ctl.value())

    def _on_offset_y_changed(self, v):
        self.config.set_global_offset_y(int(v))
        if self.overlay: self.overlay.update_offset(self.offset_x_ctl.value(), int(v))

    def _on_opacity_changed(self, v):
        self.config.set_overlay_opacity(v / 100.0)
        if self.overlay: self.overlay._update_effective_overlay()

    def _on_wheel_offset_changed(self, v):
        self.config.set_wheel_offset(self.wheel_x_ctl.value(), self.wheel_y_ctl.value())
        if self.ammo_wheel is None:
            self.ammo_wheel = getattr(self.window(), "ammo_wheel", None)
        if self.ammo_wheel:
            self.ammo_wheel.reposition()

    def _refresh_crosshair_params(self):
        """从config加载准星参数当前值到控件（静默，不触发信号）"""
        self.size_ctl.set_value_silent(self.config.get_global_scale())
        self.offset_x_ctl.set_value_silent(self.config.get_global_offset_x())
        self.offset_y_ctl.set_value_silent(self.config.get_global_offset_y())
        self.opacity_ctl.set_value_silent(int(self.config.get_overlay_opacity() * 100))
        ox, oy = self.config.get_wheel_offset()
        self.wheel_x_ctl.setValue(ox)
        self.wheel_y_ctl.setValue(oy)

    def refresh(self):
        """全量刷新"""
        self.refresh_vehicle_list()
        self.refresh_ammo()
        self._refresh_crosshair_params()
    def showEvent(self, event):
        super().showEvent(event)
        # VehicleFilterWidget延迟创建
        self._ensure_vehicle_filter()
        # 滚轮模块在后台任务才创建，首次可见时补注入引用
        if self.ammo_wheel is None:
            self.ammo_wheel = getattr(self.window(), "ammo_wheel", None)
