"""角度仪页：配置列表+关联载具、校准、使用、角度overlay。常闭零消耗。"""

from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFrame,
    QGroupBox, QLabel, QCheckBox, QDoubleSpinBox, QPushButton,
    QLineEdit, QApplication, QListWidgetItem, QInputDialog, QAbstractItemView,
    QComboBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.angle_meter import RawInputReader, AngleTracker, Calibrator, AngleCalibration
from gui.widgets import HotkeyLineEdit, VehicleFilterWidget, OptimizedListWidget


class AngleOverlay(QWidget):
    """独立悬浮窗：显示角度数字和校准提示。常闭时不创建。"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(160, 80)
        self._angle = 0.0
        self._hint = ""
        self._state = "idle"

    def set_angle(self, angle):
        self._angle = angle
        self.update()

    def set_hint(self, text):
        self._hint = text
        self.update()

    def set_state(self, state):
        self._state = state
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QBrush, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 背景
        p.setBrush(QBrush(QColor(20, 20, 20, 200)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)
        # 角度文字
        colors = {"idle": "#888888", "active": "#00FF00", "paused": "#FF6600", "calibrating": "#FFAA00"}
        p.setPen(QColor(colors.get(self._state, "#00FF00")))
        f = QFont("Consolas", 28, QFont.Bold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, f"{self._angle:+.1f}°")
        # 提示文字
        if self._hint:
            p.setPen(QColor("#FFAA00"))
            f2 = QFont("Consolas", 9)
            p.setFont(f2)
            p.drawText(8, self.height() - 8, self._hint[:30])
        p.end()


class AngleMeterTab(QWidget):
    def __init__(self, config: ConfigManager, hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.hotkey = hotkey
        # 常闭：核心对象延迟创建
        self.raw = None
        self.tracker = None
        self.calibrator = None
        self.overlay = None
        self._timer = None
        self._loading = False
        self._build_ui()
        self._load_hotkeys()
        self._refresh_profile_list()
        # 根据配置初始化
        if self.config.is_angle_meter_enabled():
            self._init_engine()
            self._set_controls_enabled(True)
        else:
            self._set_controls_enabled(False)

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

        # === 启用开关（单独，不受禁用影响）===
        self.enable_check = QCheckBox("启用角度仪模块")
        self.enable_check.setChecked(self.config.is_angle_meter_enabled())
        self.enable_check.toggled.connect(self._on_enable_toggle)
        layout.addWidget(self.enable_check)

        # === 设置容器（除启用开关外的所有控件，禁用时整体禁用）===
        self.settings_container = QWidget()
        sc_layout = QVBoxLayout(self.settings_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(8)

        # === 行1：使用设置 ===
        use_group = QGroupBox("使用设置")
        use_v = QVBoxLayout(use_group)
        use_v.setSpacing(6)
        self.use_hint_label = QLabel("⚠ 使用前请将炮塔调到最低角，然后按开始")
        self.use_hint_label.setFont(QFont("Consolas", 10))
        self.use_hint_label.setObjectName("hint_text")
        use_v.addWidget(self.use_hint_label)
        self.angle_display = QLabel("+0.0°")
        self.angle_display.setFont(QFont("Consolas", 36, QFont.Bold))
        self.angle_display.setAlignment(Qt.AlignCenter)
        self.angle_display.setObjectName("angle_display")
        self.angle_display.setProperty("state", "idle")
        self.angle_display.setMinimumHeight(60)
        use_v.addWidget(self.angle_display)
        use_btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始使用")
        use_btn_row.addWidget(self.start_btn)
        self.stop_btn = QPushButton("停止")
        use_btn_row.addWidget(self.stop_btn)
        self.pause_btn = QPushButton("暂离/恢复")
        use_btn_row.addWidget(self.pause_btn)
        use_v.addLayout(use_btn_row)
        hk_use_row1 = QHBoxLayout()
        hk_use_row1.addWidget(QLabel("开始/停止热键:"))
        self.hk_toggle = HotkeyLineEdit()
        self.hk_toggle.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("toggle", k))
        hk_use_row1.addWidget(self.hk_toggle)
        hk_use_row1.addStretch()
        use_v.addLayout(hk_use_row1)
        hk_use_row2 = QHBoxLayout()
        hk_use_row2.addWidget(QLabel("暂离热键:"))
        self.hk_pause = HotkeyLineEdit()
        self.hk_pause.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("pause", k))
        hk_use_row2.addWidget(self.hk_pause)
        hk_use_row2.addStretch()
        use_v.addLayout(hk_use_row2)
        sc_layout.addWidget(use_group)

        # === 行2：校准设置 ===
        cal_group = QGroupBox("校准设置")
        cal_v = QVBoxLayout(cal_group)
        cal_v.setSpacing(6)
        self.cal_status_label = QLabel("状态: 使用全局出厂校准")
        self.cal_status_label.setFont(QFont("Consolas", 10))
        cal_v.addWidget(self.cal_status_label)
        self.cal_hint_label = QLabel("")
        self.cal_hint_label.setFont(QFont("Consolas", 10))
        self.cal_hint_label.setObjectName("cal_hint")
        cal_v.addWidget(self.cal_hint_label)
        cal_btn_row = QHBoxLayout()
        self.cal_quick_btn = QPushButton("快速校准(2点)")
        cal_btn_row.addWidget(self.cal_quick_btn)
        self.cal_full_btn = QPushButton("精确校准(7点)")
        cal_btn_row.addWidget(self.cal_full_btn)
        self.cal_cancel_btn = QPushButton("取消校准")
        cal_btn_row.addWidget(self.cal_cancel_btn)
        cal_v.addLayout(cal_btn_row)
        hk_cal_row = QHBoxLayout()
        hk_cal_row.addWidget(QLabel("校准确认热键:"))
        self.hk_calibrate = HotkeyLineEdit()
        self.hk_calibrate.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("calibrate", k))
        hk_cal_row.addWidget(self.hk_calibrate)
        hk_cal_row.addStretch()
        cal_v.addLayout(hk_cal_row)
        sc_layout.addWidget(cal_group)

        # === 行3+行4：角度仪配置（QGroupBox 包裹，左上角小字标题，组内自适应高度）===
        cfg_group = QGroupBox("角度仪配置")
        cfg_v = QVBoxLayout(cfg_group)
        cfg_v.setSpacing(8)
        # 行3：参数行（角度范围 + 归零设置，左右并排）
        param_row = QHBoxLayout()
        param_row.setSpacing(12)
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("最低角:"))
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-90, 90); self.min_spin.setSuffix("°")
        self.min_spin.valueChanged.connect(self._on_profile_param_changed)
        range_row.addWidget(self.min_spin)
        range_row.addWidget(QLabel("最高角:"))
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-90, 90); self.max_spin.setSuffix("°")
        self.max_spin.valueChanged.connect(self._on_profile_param_changed)
        range_row.addWidget(self.max_spin)
        range_row.addStretch()
        param_row.addLayout(range_row, 1)
        reset_row = QHBoxLayout()
        self.auto_reset_check = QCheckBox("启用归零键")
        self.auto_reset_check.toggled.connect(self._on_auto_reset_toggled)
        reset_row.addWidget(self.auto_reset_check)
        reset_row.addWidget(QLabel("归零热键:"))
        self.hk_reset = HotkeyLineEdit()
        self.hk_reset.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("reset", k))
        reset_row.addWidget(self.hk_reset, 1)
        param_row.addLayout(reset_row, 1)
        cfg_v.addLayout(param_row)
        sep_param = QFrame(); sep_param.setFrameShape(QFrame.HLine); sep_param.setObjectName("angle_meter_sep")
        cfg_v.addWidget(sep_param)
        cfg_v.addWidget(QLabel("角度仪列表与关联载具"))
        # 行4：列表行（配置列表 + 关联载具，左右并排）
        list_row = QHBoxLayout()
        list_row.setSpacing(8)
        list_v = QVBoxLayout()
        list_v.setSpacing(4)
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        self.profile_search = QLineEdit()
        self.profile_search.setPlaceholderText("搜索配置...")
        self.profile_search.textChanged.connect(self._refresh_profile_list)
        search_row.addWidget(self.profile_search, 2)
        self.profile_tag_filter = QComboBox()
        self.profile_tag_filter.addItem("全部标签")
        search_row.addWidget(self.profile_tag_filter, 1)
        list_v.addLayout(search_row)
        self.profile_list = OptimizedListWidget()
        self.profile_list.setMinimumHeight(120)
        self.profile_list.currentItemChanged.connect(self._on_profile_select)
        list_v.addWidget(self.profile_list, 1)
        pbtn_row = QHBoxLayout()
        self.add_profile_btn = QPushButton("新建")
        self.rename_profile_btn = QPushButton("重命名")
        self.delete_profile_btn = QPushButton("删除")
        pbtn_row.addWidget(self.add_profile_btn)
        pbtn_row.addWidget(self.rename_profile_btn)
        pbtn_row.addWidget(self.delete_profile_btn)
        list_v.addLayout(pbtn_row)
        list_row.addLayout(list_v, 1)
        link_v = QVBoxLayout()
        link_v.setSpacing(4)
        self.link_vf = VehicleFilterWidget(mode="check")
        self.link_vf.list.setSelectionMode(QAbstractItemView.NoSelection) if hasattr(self.link_vf, 'list') else None
        self.link_vf.filter_changed.connect(self._refresh_linked_vehicles)
        self.link_vf.vehicle_toggled.connect(self._on_linked_vehicle_changed)
        link_v.addWidget(self.link_vf, 1)
        list_row.addLayout(link_v, 1)
        cfg_v.addLayout(list_row, 1)
        sc_layout.addWidget(cfg_group)

        sc_layout.addStretch()
        layout.addWidget(self.settings_container)
        layout.addStretch()

        # 按钮信号
        self.add_profile_btn.clicked.connect(self._on_add_profile)
        self.rename_profile_btn.clicked.connect(self._on_rename_profile)
        self.delete_profile_btn.clicked.connect(self._on_delete_profile)
        self.cal_quick_btn.clicked.connect(self._on_cal_quick)
        self.cal_full_btn.clicked.connect(self._on_cal_full)
        self.cal_cancel_btn.clicked.connect(self._on_cal_cancel)
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.pause_btn.clicked.connect(self._on_pause)

        # 焦点禁用
        for w in [self.enable_check, self.profile_search, self.min_spin, self.max_spin,
                  self.add_profile_btn, self.rename_profile_btn, self.delete_profile_btn,
                  self.cal_quick_btn, self.cal_full_btn, self.cal_cancel_btn,
                  self.start_btn, self.stop_btn, self.pause_btn,
                  self.hk_toggle, self.hk_pause, self.hk_calibrate, self.hk_reset]:
            w.setFocusPolicy(Qt.NoFocus)

    # === 启用/禁用 ===
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _on_enable_toggle(self, enabled):
        self.config.set_angle_meter_enabled(enabled)
        if enabled:
            self._init_engine()
            self._set_controls_enabled(True)
        else:
            self._shutdown_engine()
            self._set_controls_enabled(False)
        self.hotkey.reload_hotkeys()

    def _init_engine(self):
        if self.tracker is not None:
            return
        self.raw = RawInputReader()
        self.raw.register()
        self.tracker = AngleTracker(self.raw)
        self.calibrator = Calibrator(self.raw, AngleCalibration())
        self.overlay = AngleOverlay()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tracker.update)
        # 信号
        self.tracker.started.connect(self._timer.start)
        self.tracker.stopped.connect(self._timer.stop)
        self.tracker.state_changed.connect(self._on_state)
        self.tracker.angle_changed.connect(self._on_angle)
        self.calibrator.progress.connect(self._on_cal_progress)
        self.calibrator.hint.connect(self._on_cal_hint)
        self.calibrator.done.connect(self._on_cal_done)
        self.calibrator.cancelled.connect(self._on_cal_cancelled)
        # 热键信号
        self.hotkey.angle_meter_toggle_triggered.connect(self._on_hotkey_toggle)
        self.hotkey.angle_meter_pause_triggered.connect(self._on_hotkey_pause)
        self.hotkey.angle_meter_calibrate_triggered.connect(self._on_hotkey_calibrate)
        self.hotkey.angle_meter_reset_triggered.connect(self._on_hotkey_reset)
        # 刷新
        self._refresh_profile_list()
        self._apply_current_profile_to_tracker()

    def _shutdown_engine(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
        if self.tracker:
            self.tracker.stop()
            self.tracker = None
        if self.calibrator:
            self.calibrator = None
        if self.overlay:
            self.overlay.hide()
            self.overlay = None
        if self.raw:
            self.raw.close()
            self.raw = None
        self.angle_display.setText("+0.0°")
        self.cal_hint_label.setText("")

    def _set_controls_enabled(self, enabled):
        # 根源方案：禁用整个设置容器，新控件自动纳入，无需手动维护列表
        self.settings_container.setEnabled(enabled)

    # === 配置列表 ===
    def _refresh_profile_list(self):
        search = self.profile_search.text().lower() if hasattr(self, 'profile_search') else ""
        profiles = self.config.get_angle_meter_profiles()
        current = self.config.get_current_angle_meter_profile()
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        selected_row = -1
        for i, name in enumerate(sorted(profiles.keys())):
            if search and search not in name.lower():
                continue
            vehicles = self.config.get_angle_meter_profile_linked_vehicles(name)
            tags_eff = self.config.get_angle_meter_profile_effective_tags(name)
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

    def _on_profile_select(self, current, previous):
        if current is None:
            return
        name = current.data(Qt.UserRole)
        self.config.set_current_angle_meter_profile(name)
        self._load_profile_params(name)
        self._refresh_linked_vehicles()
        self._apply_current_profile_to_tracker()

    def _load_profile_params(self, name):
        profile = self.config.get_angle_meter_profile(name)
        self._loading = True
        self.min_spin.setValue(profile.get("min_angle", -80.0))
        self.max_spin.setValue(profile.get("max_angle", 80.0))
        self._loading = False
        cal = profile.get("calibration")
        if cal:
            self.cal_status_label.setText(f"状态: 载具单独校准（{len(cal)}点）✓")
        else:
            self.cal_status_label.setText("状态: 使用全局出厂校准（建议做一次快速校准）")
        self.auto_reset_check.blockSignals(True)
        self.auto_reset_check.setChecked(profile.get("auto_reset", False))
        self.auto_reset_check.blockSignals(False)
        self.hk_reset.setEnabled(profile.get("auto_reset", False))

    def _on_profile_param_changed(self):
        if self._loading:
            return
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        profile = self.config.get_angle_meter_profile(name)
        new_min = self.min_spin.value()
        new_max = self.max_spin.value()
        # 范围改变时清除旧校准（校准与范围绑定）
        if (abs(new_min - profile.get("min_angle", -80.0)) > 0.01 or
                abs(new_max - profile.get("max_angle", 80.0)) > 0.01):
            profile["calibration"] = None
            self.cal_status_label.setText("状态: 使用全局出厂校准（范围已变更，旧校准已清除）")
        profile["min_angle"] = new_min
        profile["max_angle"] = new_max
        self.config.set_angle_meter_profile(name, profile)
        self._apply_current_profile_to_tracker()

    def _on_auto_reset_toggled(self, checked):
        if self._loading:
            return
        self.hk_reset.setEnabled(checked)
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        profile = self.config.get_angle_meter_profile(name)
        profile["auto_reset"] = checked
        self.config.set_angle_meter_profile(name, profile)

    def _on_add_profile(self):
        name, ok = QInputDialog.getText(self, "新建配置", "配置名称:")
        if ok and name:
            self.config.add_angle_meter_profile(name)
            self.config.set_current_angle_meter_profile(name)
            self._refresh_profile_list()

    def _on_rename_profile(self):
        item = self.profile_list.currentItem()
        if not item:
            return
        old = item.data(Qt.UserRole)
        name, ok = QInputDialog.getText(self, "重命名配置", "新名称:", text=old)
        if ok and name and name != old:
            self.config.rename_angle_meter_profile(old, name)
            self._refresh_profile_list()

    def _on_delete_profile(self):
        item = self.profile_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        profiles = self.config.get_angle_meter_profiles()
        if len(profiles) <= 1:
            return
        self.config.delete_angle_meter_profile(name)
        self._refresh_profile_list()

    # === 关联载具 ===
    def _refresh_linked_vehicles(self):
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        profile = self.config.get_angle_meter_profile(name)
        linked = set(profile.get("linked_vehicles", []))
        tags = self.config.get_all_tags()
        self.link_vf.set_tags(tags)
        search, tag = self.link_vf.get_filter()
        vehicles = self.config.get_vehicle_names_filtered(search, tag)
        self.link_vf.populate(
            [(v, self.config.get_vehicle_tags(v)) for v in vehicles],
            checked_set=linked)

    def _on_linked_vehicle_changed(self, vehicle_name, checked):
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        profile = self.config.get_angle_meter_profile(name)
        linked = set(profile.get("linked_vehicles", []))
        if checked:
            linked.add(vehicle_name)
        else:
            linked.discard(vehicle_name)
        profile["linked_vehicles"] = sorted(linked)
        self.config.set_angle_meter_profile(name, profile)

    def _apply_current_profile_to_tracker(self):
        if not self.tracker:
            return
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        profile = self.config.get_angle_meter_profile(name)
        cal_data = profile.get("calibration")
        cal = AngleCalibration.from_list(cal_data) if cal_data else None
        self.tracker.set_vehicle_config(
            profile.get("min_angle", -80.0),
            profile.get("max_angle", 80.0),
            cal)
        self.angle_display.setText(f"{profile.get('min_angle', -80.0):+.1f}°")

    # === 校准 ===
    def _on_cal_quick(self):
        if self.calibrator:
            name = self.config.get_current_angle_meter_profile()
            p = self.config.get_angle_meter_profile(name)
            self.calibrator.start("quick", p.get("min_angle", -80), p.get("max_angle", 80))
            self._show_overlay()

    def _on_cal_full(self):
        if self.calibrator:
            name = self.config.get_current_angle_meter_profile()
            p = self.config.get_angle_meter_profile(name)
            self.calibrator.start("full", p.get("min_angle", -80), p.get("max_angle", 80))
            self._show_overlay()

    def _on_cal_cancel(self):
        if self.calibrator:
            self.calibrator.cancel()

    def _on_cal_progress(self, step, total):
        self.cal_status_label.setText(f"校准中: {step}/{total}")

    def _on_cal_hint(self, step, total, target):
        hint = f"→ 请将炮塔调到 {target:.1f}°，按校准确认热键 ({step+1}/{total})"
        self.cal_hint_label.setText(hint)
        if self.overlay:
            self.overlay.set_hint(hint)

    def _on_cal_done(self, cal):
        name = self.config.get_current_angle_meter_profile()
        if name:
            profile = self.config.get_angle_meter_profile(name)
            profile["calibration"] = cal.to_list()
            self.config.set_angle_meter_profile(name, profile)
            if self.tracker:
                self.tracker.set_calibration(cal)
        self.cal_hint_label.setText("")
        if self.overlay:
            self.overlay.set_hint("")
            if not self.tracker or self.tracker.state != "ACTIVE":
                self.overlay.hide()
        self.cal_status_label.setText(f"状态: 载具单独校准（{len(cal.points)}点）✓")

    def _on_cal_cancelled(self):
        self.cal_hint_label.setText("")
        if self.overlay:
            self.overlay.set_hint("")
            if not self.tracker or self.tracker.state != "ACTIVE":
                self.overlay.hide()
        self.cal_status_label.setText("校准已取消")

    # === 使用 ===
    def _show_overlay(self):
        if self.overlay:
            self.overlay.show()
            self.overlay.move(100, 100)

    def _on_start(self):
        if self.tracker:
            self.tracker.start()
            self._show_overlay()

    def _on_stop(self):
        if self.tracker:
            self.tracker.stop()
            if self.overlay:
                self.overlay.hide()

    def _on_pause(self):
        if self.tracker:
            self.tracker.pause_toggle()

    def _on_state(self, state):
        self.angle_display.setProperty("state", state.lower())
        self.angle_display.style().unpolish(self.angle_display)
        self.angle_display.style().polish(self.angle_display)
        if self.overlay:
            self.overlay.set_state(state.lower())
        if state == "ACTIVE":
            self.use_hint_label.setText("✓ 使用中，角度从最低角开始累积")
        elif state == "PAUSED":
            self.use_hint_label.setText("⏸ 已暂离，按暂离/恢复继续")
        else:
            self.use_hint_label.setText("⚠ 使用前请将炮塔调到最低角，然后按开始")

    def _on_angle(self, angle):
        self.angle_display.setText(f"{angle:+.1f}°")
        if self.overlay:
            self.overlay.set_angle(angle)

    # === 热键 ===
    def _load_hotkeys(self):
        hks = self.config.get_angle_meter_hotkeys()
        for action, widget in [("toggle", self.hk_toggle), ("pause", self.hk_pause),
                               ("calibrate", self.hk_calibrate), ("reset", self.hk_reset)]:
            # A3: 统一双键结构，角度仪 UI 只用 key1（单键绑定）
            key = hks.get(action, {}).get("key1", "")
            widget._key = key
            widget.setText(HotkeyManager.get_key_name(key) if key else "")

    def _on_hotkey_captured(self, action, key):
        # A3: 统一双键结构，角度仪只用 slot=1（单键绑定）
        self.config.set_angle_meter_hotkey(action, key, "keydown", slot=1)
        self.hotkey.reload_hotkeys()

    def _on_hotkey_toggle(self):
        if self.tracker:
            if self.tracker.state in ("ACTIVE", "PAUSED"):
                self.tracker.stop()
                if self.overlay:
                    self.overlay.hide()
            else:
                self.tracker.start()
                self._show_overlay()

    def _on_hotkey_pause(self):
        if self.tracker:
            self.tracker.pause_toggle()

    def _on_hotkey_calibrate(self):
        if self.calibrator and self.calibrator.is_calibrating:
            self.calibrator.next_point()

    def _on_hotkey_reset(self):
        if not self.tracker:
            return
        name = self.config.get_current_angle_meter_profile()
        profile = self.config.get_angle_meter_profile(name) if name else {}
        if profile.get("auto_reset", False):
            self.tracker.reset_to_zero()

    # === 生命周期 ===
    def showEvent(self, event):
        super().showEvent(event)
        if self.config.is_angle_meter_enabled() and self.tracker is None:
            self._init_engine()
        elif self.config.is_angle_meter_enabled():
            self._refresh_profile_list()

    def shutdown(self):
        self._shutdown_engine()
