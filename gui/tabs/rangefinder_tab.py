"""测距仪页：UI切换、测距仪模块、ROI、结果显示、配置管理、关联载具"""
from core.win32_utils import user32  # 统一 Win32 入口
from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFrame,
    QGroupBox, QLabel, QCheckBox, QSpinBox, QPushButton, QComboBox,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QInputDialog,
    QAbstractItemView, QApplication, QDialog
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from gui.widgets import VehicleFilterWidget, RegionSelector, PointPicker, OptimizedListWidget
from gui.hotkey_widgets import HotkeyPairWidget

# 时间常量（魔法数字命名化，注释取值依据）
MEASURE_DELAY_MS = 150        # 测距启动延迟：热键触发后等待 UI 切换/BlockInput 状态稳定再截图
SHUTDOWN_WAIT_MS = 200        # 关闭等待超时：测距线程 abort 后应在 200ms 内返回，超时则强制继续关闭


class RangefinderTab(QWidget):
    def __init__(self, config: ConfigManager, hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.hotkey = hotkey
        self.rangefinder_engine = None
        self.rangefinder_overlay = None
        self.rangefinder_overlay2 = None
        self._measure_thread = None
        self._measuring = False
        self._selector = None
        self._picker = None
        self._saved_opacity = 1.0
        self._loading = False
        self._data_loaded = False
        self._build_ui()
        self._connect_config_signals()
        self._load_hotkeys()  # 热键注册必须在__init__（启动时可用）

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # === 第一行：UI切换（独立隔板）===
        ui_toggle_group = QGroupBox("UI 切换（独立于信息数显模块）")
        ui_toggle_layout = QHBoxLayout(ui_toggle_group)
        ui_toggle_layout.setSpacing(8)
        # 左：有/无UI快速切换
        toggle_ui_v = QVBoxLayout()
        toggle_ui_v.setSpacing(4)
        tui_row = QHBoxLayout()
        self.toggle_ui_enable_check = QCheckBox("启用 有/无UI快速切换")
        self.toggle_ui_enable_check.setChecked(self.config.is_toggle_ui_enabled())
        self.toggle_ui_enable_check.toggled.connect(self._on_toggle_ui_enable)
        tui_row.addWidget(self.toggle_ui_enable_check)
        tui_row.addStretch()
        toggle_ui_v.addLayout(tui_row)
        self.toggle_ui_pair = HotkeyPairWidget("UI切换")
        self.toggle_ui_pair.hotkey_changed.connect(self._on_toggle_ui_hotkey_changed)
        toggle_ui_v.addWidget(self.toggle_ui_pair)
        ui_toggle_layout.addLayout(toggle_ui_v, 1)
        # 右：无UI按钮坐标
        ui_coord_v = QVBoxLayout()
        ui_coord_v.setSpacing(4)
        ui_coord_v.addWidget(QLabel("无UI按钮坐标"))
        ui_h = QHBoxLayout()
        ui_h.setSpacing(6)
        self.ui_x = QSpinBox(); self.ui_x.setRange(0, 9999); self.ui_x.setMaximumWidth(90)
        self.ui_y = QSpinBox(); self.ui_y.setRange(0, 9999); self.ui_y.setMaximumWidth(90)
        ui_h.addWidget(QLabel("X:")); ui_h.addWidget(self.ui_x)
        ui_h.addSpacing(10); ui_h.addWidget(QLabel("Y:")); ui_h.addWidget(self.ui_y)
        ui_h.addSpacing(10)
        self.pick_ui_btn = QPushButton("点击选定"); self.pick_ui_btn.setMaximumWidth(100)
        ui_h.addWidget(self.pick_ui_btn)
        ui_h.addStretch()
        ui_coord_v.addLayout(ui_h)
        ui_toggle_layout.addLayout(ui_coord_v, 1)
        layout.addWidget(ui_toggle_group)

        # === 启用开关（单独，不受禁用影响）===
        self.enable_check = QCheckBox("启用信息数显模块")
        self.enable_check.setChecked(self.config.is_rangefinder_enabled())
        self.enable_check.toggled.connect(self._on_enable_toggle)
        layout.addWidget(self.enable_check)

        # === 设置容器（除启用开关外的所有控件，禁用时整体禁用）===
        self.settings_container = QWidget()
        sc_layout = QVBoxLayout(self.settings_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(8)

        # === 第二~四行：信息数显设置（同一隔板）===
        settings_group = QGroupBox("信息数显设置")
        settings_v = QVBoxLayout(settings_group)
        settings_v.setSpacing(10)

        # 行2：信息截取热键（左）+ 执行间隙（右）
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        hk_v = QVBoxLayout()
        hk_v.setSpacing(4)
        self.hk_pair = HotkeyPairWidget("信息截取")
        self.hk_pair.hotkey_changed.connect(self._on_hotkey_changed)
        hk_v.addWidget(self.hk_pair)
        row2.addLayout(hk_v, 1)
        # 执行间隙（右对齐）
        interval_v = QVBoxLayout()
        interval_v.setSpacing(4)
        interval_row = QHBoxLayout()
        interval_row.addStretch()
        interval_row.addWidget(QLabel("执行间隙(ms):"))
        self.step_interval_spin = QSpinBox()
        self.step_interval_spin.setRange(10, 1000)
        self.step_interval_spin.setSingleStep(10)
        self.step_interval_spin.setMaximumWidth(80)
        self.step_interval_spin.valueChanged.connect(self._on_step_interval_changed)
        interval_row.addWidget(self.step_interval_spin)
        interval_v.addLayout(interval_row)
        row2.addLayout(interval_v)
        settings_v.addLayout(row2)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine); sep1.setObjectName("rangefinder_sep")
        settings_v.addWidget(sep1)

        # 行3：ROI + 结果显示
        settings_v.addWidget(QLabel("截取区域与结果显示"))
        roi_disp_row = QHBoxLayout()
        roi_disp_row.setSpacing(8)
        # 左：ROI
        roi_v = QVBoxLayout()
        roi_v.setSpacing(4)
        self.roi_x = QSpinBox(); self.roi_x.setRange(0, 9999); self.roi_x.setMaximumWidth(90)
        self.roi_y = QSpinBox(); self.roi_y.setRange(0, 9999); self.roi_y.setMaximumWidth(90)
        self.roi_w = QSpinBox(); self.roi_w.setRange(1, 9999); self.roi_w.setMaximumWidth(90)
        self.roi_h = QSpinBox(); self.roi_h.setRange(1, 9999); self.roi_h.setMaximumWidth(90)
        roi_row1 = QHBoxLayout(); roi_row1.setSpacing(4)
        roi_row1.addWidget(QLabel("X:")); roi_row1.addWidget(self.roi_x)
        roi_row1.addSpacing(8); roi_row1.addWidget(QLabel("Y:")); roi_row1.addWidget(self.roi_y)
        roi_row1.addSpacing(8); roi_row1.addWidget(QLabel("宽:")); roi_row1.addWidget(self.roi_w)
        roi_row1.addSpacing(8); roi_row1.addWidget(QLabel("高:")); roi_row1.addWidget(self.roi_h)
        roi_row1.addStretch()
        roi_v.addLayout(roi_row1)
        self.pick_roi_btn = QPushButton("框选区域"); self.pick_roi_btn.setMaximumWidth(100)
        roi_v.addWidget(self.pick_roi_btn)
        roi_disp_row.addLayout(roi_v, 1)
        # 右：结果显示
        disp_v = QVBoxLayout()
        disp_v.setSpacing(4)
        self.disp_x = QSpinBox(); self.disp_x.setRange(0, 9999); self.disp_x.setMaximumWidth(90)
        self.disp_y = QSpinBox(); self.disp_y.setRange(0, 9999); self.disp_y.setMaximumWidth(90)
        self.disp_w = QSpinBox(); self.disp_w.setRange(20, 9999); self.disp_w.setMaximumWidth(90)
        self.disp_h = QSpinBox(); self.disp_h.setRange(20, 9999); self.disp_h.setMaximumWidth(90)
        disp_row1 = QHBoxLayout(); disp_row1.setSpacing(4)
        disp_row1.addWidget(QLabel("位置X:")); disp_row1.addWidget(self.disp_x)
        disp_row1.addSpacing(8); disp_row1.addWidget(QLabel("位置Y:")); disp_row1.addWidget(self.disp_y)
        disp_row1.addStretch()
        disp_v.addLayout(disp_row1)
        disp_row2 = QHBoxLayout(); disp_row2.setSpacing(4)
        disp_row2.addWidget(QLabel("宽度:")); disp_row2.addWidget(self.disp_w)
        disp_row2.addSpacing(8); disp_row2.addWidget(QLabel("高度:")); disp_row2.addWidget(self.disp_h)
        disp_row2.addStretch()
        disp_v.addLayout(disp_row2)
        disp_row3 = QHBoxLayout(); disp_row3.setSpacing(4)
        self.disp_op = QSpinBox(); self.disp_op.setRange(10, 100); self.disp_op.setValue(100); self.disp_op.setMaximumWidth(90)
        disp_row3.addWidget(QLabel("透明度:")); disp_row3.addWidget(self.disp_op); disp_row3.addStretch()
        disp_v.addLayout(disp_row3)
        self.drag_btn = QPushButton("拖拽定位"); self.drag_btn.setMaximumWidth(100)
        disp_v.addWidget(self.drag_btn)
        roi_disp_row.addLayout(disp_v, 1)
        settings_v.addLayout(roi_disp_row)

        # 第二截取区域（弹药数量等）
        roi2_row = QHBoxLayout()
        roi2_row.setSpacing(8)
        self.roi2_enabled = QCheckBox("启用第二截取区域")
        roi2_row.addWidget(self.roi2_enabled)
        roi2_row.addStretch()
        settings_v.addLayout(roi2_row)
        roi2_disp_row = QHBoxLayout()
        roi2_disp_row.setSpacing(8)
        # 左：ROI2
        roi2_v = QVBoxLayout()
        roi2_v.setSpacing(4)
        self.roi2_x = QSpinBox(); self.roi2_x.setRange(0, 9999); self.roi2_x.setMaximumWidth(90)
        self.roi2_y = QSpinBox(); self.roi2_y.setRange(0, 9999); self.roi2_y.setMaximumWidth(90)
        self.roi2_w = QSpinBox(); self.roi2_w.setRange(1, 9999); self.roi2_w.setMaximumWidth(90)
        self.roi2_h = QSpinBox(); self.roi2_h.setRange(1, 9999); self.roi2_h.setMaximumWidth(90)
        roi2_r1 = QHBoxLayout(); roi2_r1.setSpacing(4)
        roi2_r1.addWidget(QLabel("X:")); roi2_r1.addWidget(self.roi2_x)
        roi2_r1.addSpacing(8); roi2_r1.addWidget(QLabel("Y:")); roi2_r1.addWidget(self.roi2_y)
        roi2_r1.addSpacing(8); roi2_r1.addWidget(QLabel("宽:")); roi2_r1.addWidget(self.roi2_w)
        roi2_r1.addSpacing(8); roi2_r1.addWidget(QLabel("高:")); roi2_r1.addWidget(self.roi2_h)
        roi2_r1.addStretch()
        roi2_v.addLayout(roi2_r1)
        self.pick_roi2_btn = QPushButton("框选区域2"); self.pick_roi2_btn.setMaximumWidth(100)
        roi2_v.addWidget(self.pick_roi2_btn)
        roi2_disp_row.addLayout(roi2_v, 1)
        # 右：结果2显示位置（大小/透明度共用区域1）
        disp2_v = QVBoxLayout()
        disp2_v.setSpacing(4)
        self.disp2_x = QSpinBox(); self.disp2_x.setRange(0, 9999); self.disp2_x.setMaximumWidth(90)
        self.disp2_y = QSpinBox(); self.disp2_y.setRange(0, 9999); self.disp2_y.setMaximumWidth(90)
        disp2_r1 = QHBoxLayout(); disp2_r1.setSpacing(4)
        disp2_r1.addWidget(QLabel("位置X:")); disp2_r1.addWidget(self.disp2_x)
        disp2_r1.addSpacing(8); disp2_r1.addWidget(QLabel("位置Y:")); disp2_r1.addWidget(self.disp2_y)
        disp2_r1.addStretch()
        disp2_v.addLayout(disp2_r1)
        self.drag2_btn = QPushButton("拖拽定位2"); self.drag2_btn.setMaximumWidth(100)
        disp2_v.addWidget(self.drag2_btn)
        disp2_v.addStretch()
        roi2_disp_row.addLayout(disp2_v, 1)
        settings_v.addLayout(roi2_disp_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); sep2.setObjectName("rangefinder_sep")
        settings_v.addWidget(sep2)

        # 行4：配置 + 关联载具
        settings_v.addWidget(QLabel("信息数显列表与关联载具"))
        cfg_link_row = QHBoxLayout()
        cfg_link_row.setSpacing(8)
        # 左：配置列表
        sel_v = QVBoxLayout()
        sel_v.setSpacing(4)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索配置...")
        search_row.addWidget(self.search, 2)
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("全部标签")
        search_row.addWidget(self.tag_filter, 1)
        sel_v.addLayout(search_row)
        self.profile_list = OptimizedListWidget()
        self.profile_list.setMinimumHeight(120)
        sel_v.addWidget(self.profile_list, 1)
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("新建")
        self.rename_btn = QPushButton("重命名")
        self.delete_btn = QPushButton("删除")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.rename_btn)
        btn_row.addWidget(self.delete_btn)
        sel_v.addLayout(btn_row)
        cfg_link_row.addLayout(sel_v, 1)
        # 右：关联载具
        link_v = QVBoxLayout()
        link_v.setSpacing(4)
        self.link_vf = VehicleFilterWidget(mode="check")
        self.link_vf.set_no_selection()
        self.link_vf.setMinimumHeight(120)
        self.link_vf.filter_changed.connect(self._refresh_linked_vehicles)
        self.link_vf.vehicle_toggled.connect(self._on_linked_vehicle_changed)
        link_v.addWidget(self.link_vf)
        cfg_link_row.addLayout(link_v, 1)
        settings_v.addLayout(cfg_link_row)

        sc_layout.addWidget(settings_group)

        # 第五行：保存
        self.save_btn = QPushButton("保存当前配置")
        sc_layout.addWidget(self.save_btn)
        sc_layout.addStretch()
        layout.addWidget(self.settings_container)
        layout.addStretch()

        # 信号
        self.search.textChanged.connect(self._refresh_profile_list)
        self.tag_filter.currentIndexChanged.connect(self._refresh_profile_list)
        self.profile_list.currentItemChanged.connect(self._on_list_select)
        self.add_btn.clicked.connect(self._on_add_profile)
        self.rename_btn.clicked.connect(self._on_rename_profile)
        self.delete_btn.clicked.connect(self._on_delete_profile)
        self.pick_roi_btn.clicked.connect(self._on_pick_roi)
        self.pick_ui_btn.clicked.connect(self._on_pick_ui)
        self.drag_btn.clicked.connect(self._on_drag)
        self.pick_roi2_btn.clicked.connect(self._on_pick_roi2)
        self.drag2_btn.clicked.connect(self._on_drag2)
        self.roi2_enabled.toggled.connect(self._on_roi2_toggled)
        self.disp_op.valueChanged.connect(self._on_opacity)
        self.save_btn.clicked.connect(self._on_save_profile)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _load_hotkeys(self):
        self.toggle_ui_pair.set_hotkey(self.hotkey.config.get_hotkey("toggle_ui"))
        self.hk_pair.set_hotkey(self.config.get_rangefinder_hotkeys().get("measure", {}))
        self.step_interval_spin.setValue(self.config.get_toggle_ui_step_interval())

    def _connect_config_signals(self):
        """连接所有配置控件的 valueChanged 信号，修改后自动保存"""
        widgets = [
            self.roi_x, self.roi_y, self.roi_w, self.roi_h,
            self.roi2_x, self.roi2_y, self.roi2_w, self.roi2_h,
            self.ui_x, self.ui_y,
            self.disp_x, self.disp_y, self.disp_w, self.disp_h, self.disp_op,
            self.disp2_x, self.disp2_y,
        ]
        for w in widgets:
            w.valueChanged.connect(self._on_config_changed)
        self.roi2_enabled.toggled.connect(self._on_config_changed)

    def _on_config_changed(self):
        """配置控件值改变时自动保存（加载配置时不触发）"""
        if not self._loading:
            self._on_save_profile()

    # === 启用/禁用 ===
    def _on_enable_toggle(self, enabled):
        self.config.set_rangefinder_enabled(enabled)
        if enabled:
            self._init_rangefinder()
            self._set_controls_enabled(True)
        else:
            self._shutdown_rangefinder()
            self._set_controls_enabled(False)
        self.hotkey.reload_hotkeys()

    def _set_controls_enabled(self, enabled):
        # 根源方案：禁用整个设置容器，新控件自动纳入，无需手动维护列表
        self.settings_container.setEnabled(enabled)

    # === 测距仪引擎实例 ===
    def _init_rangefinder(self):
        from core.rangefinder import RangefinderEngine
        from core.rangefinder_overlay import RangefinderOverlay
        if self.rangefinder_engine is None:
            self.rangefinder_engine = RangefinderEngine()
        if self.rangefinder_overlay is None:
            self.rangefinder_overlay = RangefinderOverlay()
            QTimer.singleShot(0, self.rangefinder_overlay.show)
        if self.rangefinder_overlay2 is None:
            self.rangefinder_overlay2 = RangefinderOverlay()
            QTimer.singleShot(0, self.rangefinder_overlay2.show)
        self._load_profile_to_ui()
        self._refresh_profile_list()
        # 强制同步 overlay 配置（_load_profile_to_ui 可能因 profile 为空提前 return）
        QTimer.singleShot(0, self._sync_rangefinder_config)

    def _shutdown_rangefinder(self):
        # 先退出编辑模式（释放鼠标钩子）
        if self.rangefinder_overlay:
            try:
                self.rangefinder_overlay.set_edit_mode(False)
            except Exception:
                pass
        if self.rangefinder_overlay2:
            try:
                self.rangefinder_overlay2.set_edit_mode(False)
            except Exception:
                pass
        # 再关闭 overlay 窗口
        if self.rangefinder_overlay:
            self.rangefinder_overlay.close()
            self.rangefinder_overlay = None
        if self.rangefinder_overlay2:
            self.rangefinder_overlay2.close()
            self.rangefinder_overlay2 = None
        # 最后释放测距仪截图资源
        if self.rangefinder_engine:
            self.rangefinder_engine.close()
            self.rangefinder_engine = None

    # === 配置列表 ===
    def _refresh_profile_list(self):
        # 标签下拉框只在标签数量变化时重建
        tags = self.config.get_all_tags()
        existing = [self.tag_filter.itemData(i) for i in range(1, self.tag_filter.count())]
        if existing != tags:
            self.tag_filter.blockSignals(True)
            current_tag = self.tag_filter.currentData()
            self.tag_filter.clear()
            self.tag_filter.addItem("全部标签", None)
            for t in tags:
                self.tag_filter.addItem(t, t)
            idx = self.tag_filter.findData(current_tag)
            self.tag_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.tag_filter.blockSignals(False)

        tag = self.tag_filter.currentData() or ""
        names = self.config.get_rangefinder_profiles_filtered(self.search.text(), tag)

        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        current = self.config.get_current_rangefinder_profile()
        selected_row = -1
        for i, name in enumerate(names):
            vehicles = self.config.get_rangefinder_profile_linked_vehicles(name)
            tags_eff = self.config.get_rangefinder_profile_effective_tags(name)
            parts = []
            if vehicles:
                parts.append(f"载具:{','.join(vehicles)}")
            if tags_eff:
                parts.append(f"标签:{','.join(tags_eff)}")
            display = f"{name}  ({'; '.join(parts)})" if parts else name
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, name)
            self.profile_list.addItem(item)
            if name == current:
                selected_row = i
        self.profile_list.blockSignals(False)
        if selected_row >= 0:
            self.profile_list.setCurrentRow(selected_row)

    def _on_list_select(self, current, _previous):
        if current:
            name = current.data(Qt.UserRole)
            self.config.set_current_rangefinder_profile(name)
            self._load_profile_to_ui()

    def _load_profile_to_ui(self):
        name = self.config.get_current_rangefinder_profile()
        if not name:
            return
        self._loading = True
        p = self.config.get_rangefinder_profile(name)
        self.roi_x.setValue(p.get("roi", {}).get("x", 0))
        self.roi_y.setValue(p.get("roi", {}).get("y", 0))
        self.roi_w.setValue(p.get("roi", {}).get("w", 200))
        self.roi_h.setValue(p.get("roi", {}).get("h", 80))
        self.ui_x.setValue(p.get("ui_button", {}).get("x", 960))
        self.ui_y.setValue(p.get("ui_button", {}).get("y", 540))
        self.disp_x.setValue(p.get("display_pos", {}).get("x", 100))
        self.disp_y.setValue(p.get("display_pos", {}).get("y", 100))
        self.disp_w.setValue(p.get("display_size", {}).get("w", 300))
        self.disp_h.setValue(p.get("display_size", {}).get("h", 80))
        self.disp_op.setValue(int(p.get("display_opacity", 1.0) * 100))
        roi2 = p.get("roi2", {})
        self.roi2_enabled.setChecked(roi2.get("enabled", False))
        self.roi2_x.setValue(roi2.get("x", 0))
        self.roi2_y.setValue(roi2.get("y", 0))
        self.roi2_w.setValue(roi2.get("w", 200))
        self.roi2_h.setValue(roi2.get("h", 80))
        dp2 = p.get("display_pos2", {})
        self.disp2_x.setValue(dp2.get("x", 400))
        self.disp2_y.setValue(dp2.get("y", 100))
        self._refresh_linked_vehicles()
        self.hk_pair.set_hotkey(self.config.get_rangefinder_hotkeys().get("measure", {}))
        self._sync_rangefinder_config()
        self._loading = False

    def _refresh_linked_vehicles(self):
        name = self.config.get_current_rangefinder_profile()
        self.link_vf.set_tags(self.config.get_all_tags())
        search, tag = self.link_vf.get_filter()
        vehicles = self.config.get_vehicle_names_filtered(search, tag)
        if not vehicles:
            self.link_vf.populate([])
            self.link_vf.add_disabled_item("（暂无载具，请先在载具配置页创建）")
        elif name:
            bound = set(self.config.get_rangefinder_profile_linked_vehicles(name))
            self.link_vf.populate(
                [(v, self.config.get_vehicle_tags(v)) for v in vehicles],
                checked_set=bound)

    def _on_linked_vehicle_changed(self, _name, _checked):
        name = self.config.get_current_rangefinder_profile()
        if not name:
            return
        bound = self.link_vf.get_checked_items()
        self.config.set_rangefinder_profile_linked_vehicles(name, bound)
        self._refresh_profile_list()

    def _sync_rangefinder_config(self):
        if not self.rangefinder_engine:
            return
        name = self.config.get_current_rangefinder_profile()
        if name:
            cfg = dict(self.config.get_rangefinder_profile(name))
            cfg["toggle_ui_step_interval"] = self.config.get_toggle_ui_step_interval()
            self.rangefinder_engine.set_config(cfg)
        if self.rangefinder_overlay:
            p = self.config.get_rangefinder_profile(name) if name else {}
            self.rangefinder_overlay.set_position(p.get("display_pos", {}).get("x", 100),
                                          p.get("display_pos", {}).get("y", 100))
            self.rangefinder_overlay.set_display_size(p.get("display_size", {}).get("w", 300),
                                              p.get("display_size", {}).get("h", 80))
            self.rangefinder_overlay.set_opacity(p.get("display_opacity", 1.0))
        if self.rangefinder_overlay2:
            p = self.config.get_rangefinder_profile(name) if name else {}
            self.rangefinder_overlay2.set_position(p.get("display_pos2", {}).get("x", 400),
                                           p.get("display_pos2", {}).get("y", 100))
            self.rangefinder_overlay2.set_display_size(p.get("display_size", {}).get("w", 300),
                                               p.get("display_size", {}).get("h", 80))
            self.rangefinder_overlay2.set_opacity(p.get("display_opacity", 1.0))
            if not p.get("roi2", {}).get("enabled", False):
                self.rangefinder_overlay2.clear()

    # === 配置 CRUD ===
    def _on_save_profile(self):
        name = self.config.get_current_rangefinder_profile()
        if not name:
            return
        profile = {
            "roi": {"x": self.roi_x.value(), "y": self.roi_y.value(),
                    "w": self.roi_w.value(), "h": self.roi_h.value()},
            "roi2": {"x": self.roi2_x.value(), "y": self.roi2_y.value(),
                     "w": self.roi2_w.value(), "h": self.roi2_h.value(),
                     "enabled": self.roi2_enabled.isChecked()},
            "ui_button": {"x": self.ui_x.value(), "y": self.ui_y.value()},
            "display_pos": {"x": self.disp_x.value(), "y": self.disp_y.value()},
            "display_pos2": {"x": self.disp2_x.value(), "y": self.disp2_y.value()},
            "display_size": {"w": self.disp_w.value(), "h": self.disp_h.value()},
            "display_opacity": self.disp_op.value() / 100.0,
            "linked_vehicles": self.config.get_rangefinder_profile_linked_vehicles(name),
            "toggle_steps": self.config.get_rangefinder_profile(name).get("toggle_steps", []),
        }
        self.config.update_rangefinder_profile(name, profile)
        self._sync_rangefinder_config()

    def _on_add_profile(self):
        name, ok = QInputDialog.getText(self, "新建信息数显列表", "配置名称:")
        if ok and name.strip():
            self.config.add_rangefinder_profile(name.strip())
            self.config.set_current_rangefinder_profile(name.strip())
            self._refresh_profile_list()
            self._load_profile_to_ui()

    def _on_rename_profile(self):
        name = self.config.get_current_rangefinder_profile()
        if not name:
            return
        new, ok = QInputDialog.getText(self, "重命名", "新名称:", text=name)
        if ok and new.strip() and new != name:
            self.config.rename_rangefinder_profile(name, new.strip())
            self._refresh_profile_list()

    def _on_delete_profile(self):
        name = self.config.get_current_rangefinder_profile()
        if not name:
            return
        reply = QMessageBox.question(self, "确认", f"删除配置 '{name}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.config.delete_rangefinder_profile(name)
            self._refresh_profile_list()

    # === 屏幕拾取 ===
    def _start_selector(self, callback):
        # 模态对话框：阻塞其他窗口输入，从根源避免 Overlay 拦截
        selector = RegionSelector(self.window())
        if selector.exec_() == QDialog.Accepted and selector.result_rect:
            r = selector.result_rect
            callback(r.x(), r.y(), r.width(), r.height())

    def _on_pick_roi(self):
        self._start_selector(self._on_roi_selected)

    def _on_roi_selected(self, x, y, w, h):
        self.roi_x.setValue(x); self.roi_y.setValue(y)
        self.roi_w.setValue(w); self.roi_h.setValue(h)
        self._on_save_profile()

    def _on_pick_roi2(self):
        self._start_selector(self._on_roi2_selected)

    def _on_roi2_selected(self, x, y, w, h):
        self.roi2_x.setValue(x); self.roi2_y.setValue(y)
        self.roi2_w.setValue(w); self.roi2_h.setValue(h)
        self._on_save_profile()

    def _on_roi2_toggled(self, enabled):
        if self.rangefinder_overlay2 and not enabled:
            self.rangefinder_overlay2.clear()

    def _on_pick_ui(self):
        picker = PointPicker("点击 Squad 菜单中的'无 UI'按钮", self.window())
        if picker.exec_() == QDialog.Accepted and picker.result_pos:
            x, y = picker.result_pos
            self.ui_x.setValue(x)
            self.ui_y.setValue(y)
            self._on_save_profile()

    def _on_drag(self):
        if self.rangefinder_overlay:
            self.rangefinder_overlay.set_edit_mode(True)
            # 信号驱动替代 200ms 轮询，退出编辑模式时自动触发保存
            try:
                self.rangefinder_overlay.edit_mode_changed.disconnect()
            except Exception:
                pass
            self.rangefinder_overlay.edit_mode_changed.connect(self._on_edit_finished)

    def _on_edit_finished(self, enabled):
        """T8: 编辑模式退出信号槽，替代 200ms 轮询"""
        if not enabled and self.rangefinder_overlay:
            self.disp_x.setValue(self.rangefinder_overlay.x())
            self.disp_y.setValue(self.rangefinder_overlay.y())
            self.disp_w.setValue(self.rangefinder_overlay.width())
            self.disp_h.setValue(self.rangefinder_overlay.height())
            self._on_save_profile()

    def _on_drag2(self):
        if self.rangefinder_overlay2:
            self.rangefinder_overlay2.set_edit_mode(True)
            # 信号驱动替代 200ms 轮询
            try:
                self.rangefinder_overlay2.edit_mode_changed.disconnect()
            except Exception:
                pass
            self.rangefinder_overlay2.edit_mode_changed.connect(self._on_edit2_finished)

    def _on_edit2_finished(self, enabled):
        """T8: 编辑模式退出信号槽，替代 200ms 轮询"""
        if not enabled and self.rangefinder_overlay2:
            self.disp2_x.setValue(self.rangefinder_overlay2.x())
            self.disp2_y.setValue(self.rangefinder_overlay2.y())
            self._on_save_profile()

    # === 热键 ===
    @staticmethod
    def _normalize_hotkey_pair(hk):
        """T10: 共享函数——双键相同时清空 key2，避免同一键触发两次"""
        if hk.get("key1") and hk["key1"] == hk.get("key2"):
            hk["key2"] = ""
            hk["trigger2"] = "keydown"
        return hk

    def _on_toggle_ui_enable(self, enabled):
        self.config.set_toggle_ui_enabled(enabled)
        self.hotkey.reload_hotkeys()

    def _on_toggle_ui_hotkey_changed(self, hk):
        hk = self._normalize_hotkey_pair(hk)
        if hk.get("key2") == "":
            self.toggle_ui_pair.set_hotkey(hk)
        self.hotkey.set_hotkey_pair("toggle_ui", hk)

    def _on_hotkey_changed(self, hk):
        hk = self._normalize_hotkey_pair(hk)
        if hk.get("key2") == "":
            self.hk_pair.set_hotkey(hk)
        self.config.set_rangefinder_hotkey("measure", hk["key1"], hk["trigger1"], 1)
        self.config.set_rangefinder_hotkey("measure", hk["key2"], hk["trigger2"], 2)
        self.hotkey.reload_hotkeys()

    def _on_step_interval_changed(self, val):
        self.config.set_toggle_ui_step_interval(val)

    def _on_opacity(self, v):
        if self.rangefinder_overlay:
            self.rangefinder_overlay.set_opacity(v / 100.0)

    # === 测距触发（供 main_window 调用）===
    def on_measure_hotkey(self):
        if self.config.is_rangefinder_enabled():
            self._start_measure()

    def on_toggle_ui_hotkey(self):
        from core.rangefinder import quick_toggle_ui
        import threading
        profile_name = self.config.get_current_rangefinder_profile()
        if profile_name:
            btn = self.config.get_rangefinder_profile(profile_name).get("ui_button", {})
        else:
            btn = {}
        # quick_toggle_ui含time.sleep，必须在后台线程执行避免阻塞UI事件循环
        threading.Thread(
            target=quick_toggle_ui,
            args=(btn.get("x", 960), btn.get("y", 540)),
            kwargs={"step_interval": self.config.get_toggle_ui_step_interval()},
            daemon=True
        ).start()

    def _start_measure(self):
        if not self.rangefinder_engine or not self.config.get_current_rangefinder_profile():
            return
        if self._measuring:
            return
        if self._measure_thread and self._measure_thread.isRunning():
            return
        self._measuring = True
        self._sync_rangefinder_config()
        QTimer.singleShot(MEASURE_DELAY_MS, self._do_measure)

    def _do_measure(self):
        from core.rangefinder import MeasureThread
        self._measure_thread = MeasureThread(self.rangefinder_engine)
        self._measure_thread.finished.connect(self._on_measure_done)
        self._measure_thread.start()

    def _on_measure_done(self, result):
        self._measuring = False
        if not isinstance(result, dict):
            return
        img1 = result.get("roi1")
        img2 = result.get("roi2")
        if img1 and self.rangefinder_overlay:
            data = img1.tobytes("raw", "RGB")
            qimg = QImage(data, img1.width, img1.height, img1.width * 3, QImage.Format_RGB888)
            self.rangefinder_overlay.set_image(QPixmap.fromImage(qimg))
        if img2 and self.rangefinder_overlay2:
            data = img2.tobytes("raw", "RGB")
            qimg = QImage(data, img2.width, img2.height, img2.width * 3, QImage.Format_RGB888)
            self.rangefinder_overlay2.set_image(QPixmap.fromImage(qimg))
        elif not img2 and self.rangefinder_overlay2:
            self.rangefinder_overlay2.clear()
        # BUG-9第四层：测距完成后强制恢复两个overlay的穿透（额外保险）
        for ov in (self.rangefinder_overlay, self.rangefinder_overlay2):
            if ov:
                ov.ensure_click_through()

    def refresh(self):
        """全量刷新（供 main_window 调用）"""
        if self.config.is_rangefinder_enabled() and self.rangefinder_engine is None:
            # 延迟初始化：等主窗口完全显示后再初始化 overlay，避免 __init__ 阶段时序问题
            QTimer.singleShot(0, self._init_rangefinder)
        elif not self.config.is_rangefinder_enabled():
            self._set_controls_enabled(False)
        self._refresh_profile_list()

    def showEvent(self, event):
        """P1-1: 首次显示时加载数据+补检overlay初始化"""
        super().showEvent(event)
        if not self._data_loaded:
            if self.config.is_rangefinder_enabled():
                self._refresh_profile_list()
                self._load_profile_to_ui()
            else:
                self._set_controls_enabled(False)
            self._data_loaded = True
        if self.config.is_rangefinder_enabled() and self.rangefinder_engine is None:
            QTimer.singleShot(0, self._init_rangefinder)
        # BUG-9兜底：切回时如果overlay仍在编辑模式（异常情况），强制退出
        for ov in (self.rangefinder_overlay, self.rangefinder_overlay2):
            if ov and ov._edit_mode:
                ov.set_edit_mode(False)

    def hideEvent(self, event):
        """BUG-9：切tab时如果overlay在编辑模式，自动退出（overlay是独立顶层窗口，切tab不会hide）"""
        super().hideEvent(event)
        for ov in (self.rangefinder_overlay, self.rangefinder_overlay2):
            if ov and ov._edit_mode:
                ov.set_edit_mode(False)

    def switch_profile(self, name):
        """切换到指定配置并刷新UI（供 main_window 跨页调用）"""
        if name and name != self.config.get_current_rangefinder_profile():
            self.config.set_current_rangefinder_profile(name)
            self._load_profile_to_ui()
            self._refresh_profile_list()

    def shutdown(self):
        # 防止新的测距开始
        self._measuring = False
        # 请求中止当前测距（让 measure() 安全提前返回，确保 BlockInput 被恢复）
        if self.rangefinder_engine:
            self.rangefinder_engine.abort()
        # 断开编辑模式信号（轮询定时器已删除）
        for ov in (self.rangefinder_overlay, self.rangefinder_overlay2):
            if ov:
                try:
                    ov.edit_mode_changed.disconnect()
                except Exception:
                    pass
        # 等待测距线程自然结束（measure() 会因 abort 标志快速返回）
        if self._measure_thread and self._measure_thread.isRunning():
            finished = self._measure_thread.wait(SHUTDOWN_WAIT_MS)  # 最多等待1秒
            # 超时分支必须有明确处理，不能静默继续
            if not finished:
                print(f"[Rangefinder] 测距线程关闭等待超时({SHUTDOWN_WAIT_MS}ms)，强制继续关闭")
                # 确认 BlockInput 已恢复（测距线程 abort 路径会在 finally 中恢复）
                try:
                    user32.BlockInput(False)
                except Exception:
                    pass
        self._shutdown_rangefinder()
