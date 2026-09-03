"""角度仪页：配置列表+关联载具、校准、使用、角度overlay。常闭零消耗。"""

import ctypes
import time
from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout,
    QGroupBox, QLabel, QCheckBox, QDoubleSpinBox, QPushButton,
    QLineEdit, QApplication, QListWidgetItem, QInputDialog, QAbstractItemView,
    QComboBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.angle_meter import RawInputReader, AngleTracker, Calibrator, AngleCalibration
from gui.widgets import VehicleFilterWidget, OptimizedListWidget
from gui.hotkey_widgets import HotkeyLineEdit


from core.win32_utils import send_mouse_input

def _simulate_mouse_move(dy):
    """模拟鼠标相对移动。dy: 上移负值，下移正值（和 Raw Input 一致）。
    SendInput 插入的鼠标事件会被 Raw Input 捕获，使游戏和角度仪同步。"""
    send_mouse_input(dy)


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
        # 热键微调长按状态
        self._up_pressed = False
        self._down_pressed = False
        self._up_timer = None
        self._down_timer = None
        self._up_accel = False  # 0.8秒后加速
        self._down_accel = False
        self._up_pressed_time = 0.0
        self._down_pressed_time = 0.0
        self._global_calibrating = False
        self._data_loaded = False
        self._build_ui()
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
        self.toggle_use_btn = QPushButton("开始使用")
        use_btn_row.addWidget(self.toggle_use_btn)
        self.pause_btn = QPushButton("暂离/恢复")
        use_btn_row.addWidget(self.pause_btn)
        use_v.addLayout(use_btn_row)
        hk_grid = QGridLayout()
        hk_grid.setSpacing(6)
        # 左列
        hk_grid.addWidget(QLabel("开始/停止:"), 0, 0)
        self.hk_toggle = HotkeyLineEdit()
        self.hk_toggle.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("toggle", k))
        hk_grid.addWidget(self.hk_toggle, 0, 1)
        hk_grid.addWidget(QLabel("暂离:"), 1, 0)
        self.hk_pause = HotkeyLineEdit()
        self.hk_pause.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("pause", k))
        hk_grid.addWidget(self.hk_pause, 1, 1)
        hk_grid.addWidget(QLabel("校准确认:"), 2, 0)
        self.hk_calibrate = HotkeyLineEdit()
        self.hk_calibrate.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("calibrate", k))
        hk_grid.addWidget(self.hk_calibrate, 2, 1)
        # 右列
        hk_grid.addWidget(QLabel("上移微调:"), 0, 2)
        self.hk_up = HotkeyLineEdit()
        self.hk_up.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("up", k))
        hk_grid.addWidget(self.hk_up, 0, 3)
        hk_grid.addWidget(QLabel("下移微调:"), 1, 2)
        self.hk_down = HotkeyLineEdit()
        self.hk_down.hotkeyCaptured.connect(lambda k: self._on_hotkey_captured("down", k))
        hk_grid.addWidget(self.hk_down, 1, 3)
        hk_grid.setColumnStretch(1, 1)
        hk_grid.setColumnStretch(3, 1)
        use_v.addLayout(hk_grid)
        sc_layout.addWidget(use_group)

        # === 行2：校准设置 ===
        cal_group = QGroupBox("校准设置")
        cal_v = QVBoxLayout(cal_group)
        cal_v.setSpacing(6)
        # 全局校准区域
        global_cal_row = QHBoxLayout()
        self.global_cal_status = QLabel("全局校准: 未校准，请先做全局校准")
        self.global_cal_status.setFont(QFont("Consolas", 10))
        global_cal_row.addWidget(self.global_cal_status, 1)
        self.global_cal_btn = QPushButton("全局校准(7点)")
        global_cal_row.addWidget(self.global_cal_btn)
        cal_v.addLayout(global_cal_row)
        global_cal_hint = QLabel("适配显示器/dpi/游戏灵敏度，只需做一次，是所有载具校准的基础。重校后快速校准自动更新。")
        global_cal_hint.setFont(QFont("Consolas", 8))
        global_cal_hint.setObjectName("hint_text")
        global_cal_hint.setWordWrap(True)
        cal_v.addWidget(global_cal_hint)
        sep_global = QFrame(); sep_global.setFrameShape(QFrame.HLine); sep_global.setObjectName("angle_meter_sep")
        cal_v.addWidget(sep_global)
        # 载具校准方案选择
        scheme_row = QHBoxLayout()
        scheme_row.addWidget(QLabel("校准方案:"))
        self.cal_scheme_combo = QComboBox()
        self.cal_scheme_combo.addItems(["点击选择校准方案", "快速校准（3点）", "单独校准（7点）"])
        self.cal_scheme_combo.currentIndexChanged.connect(self._on_cal_scheme_changed)
        scheme_row.addWidget(self.cal_scheme_combo, 1)
        self.cal_status_label = QLabel("")
        self.cal_status_label.setFont(QFont("Consolas", 10))
        scheme_row.addWidget(self.cal_status_label, 1)
        cal_v.addLayout(scheme_row)
        self.cal_hint_label = QLabel("")
        self.cal_hint_label.setFont(QFont("Consolas", 10))
        self.cal_hint_label.setObjectName("cal_hint")
        cal_v.addWidget(self.cal_hint_label)
        cal_btn_row = QHBoxLayout()
        self.cal_toggle_btn = QPushButton("开始校准")
        cal_btn_row.addWidget(self.cal_toggle_btn)
        cal_v.addLayout(cal_btn_row)

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
        self.global_cal_btn.clicked.connect(self._on_global_cal)
        self.cal_toggle_btn.clicked.connect(self._on_cal_toggle)
        self.toggle_use_btn.clicked.connect(self._on_toggle_use)
        self.pause_btn.clicked.connect(self._on_pause)

        # 焦点禁用
        for w in [self.enable_check, self.profile_search, self.min_spin, self.max_spin,
                  self.add_profile_btn, self.rename_profile_btn, self.delete_profile_btn,
                  self.global_cal_btn, self.cal_toggle_btn,
                  self.cal_scheme_combo,
                  self.toggle_use_btn, self.pause_btn,
                  self.hk_toggle, self.hk_pause, self.hk_calibrate, self.hk_reset,
                  self.hk_up, self.hk_down]:
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
        global_points = self.config.get_global_calibration_points()
        global_cal = AngleCalibration(global_points) if global_points else None
        self.calibrator = Calibrator(self.raw, global_cal)
        self.overlay = AngleOverlay()
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps，避免0ms占满事件循环导致 Raw Input 消息无法处理
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
        self.hotkey.angle_meter_up_pressed.connect(self._on_up_pressed)
        self.hotkey.angle_meter_up_released.connect(self._on_up_released)
        self.hotkey.angle_meter_down_pressed.connect(self._on_down_pressed)
        self.hotkey.angle_meter_down_released.connect(self._on_down_released)
        # 长按定时器（50ms初始间隔，0.5秒后加速到20ms，每次注入增量递增）
        self._up_timer = QTimer(self)
        self._up_timer.setInterval(50)
        self._up_timer.timeout.connect(self._on_up_tick)
        self._down_timer = QTimer(self)
        self._down_timer.setInterval(50)
        self._down_timer.timeout.connect(self._on_down_tick)
        # 刷新
        self._refresh_profile_list()
        self._apply_current_profile_to_tracker()

    def _shutdown_engine(self):
        if self._up_timer:
            self._up_timer.stop()
        if self._down_timer:
            self._down_timer.stop()
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
        # 校准方案状态
        ctype = profile.get("calibration_type", "none")
        scheme_map = {"none": 0, "quick": 1, "full": 2}
        self.cal_scheme_combo.blockSignals(True)
        self.cal_scheme_combo.setCurrentIndex(scheme_map.get(ctype, 0))
        self.cal_scheme_combo.blockSignals(False)
        if ctype == "quick" and profile.get("quick_calibration"):
            self.cal_status_label.setText("当前方案已校准")
        elif ctype == "full" and profile.get("full_calibration"):
            self.cal_status_label.setText("当前方案已校准")
        else:
            self.cal_status_label.setText("当前方案未校准")
        # 全局校准状态（空房子原则：无出厂兜底）
        if self.config.is_global_calibrated():
            self.global_cal_status.setText("全局校准: 已校准 ✓")
            self.global_cal_btn.setText("重新校准全局")
            self.cal_scheme_combo.setEnabled(True)
            self.cal_toggle_btn.setEnabled(True)
        else:
            self.global_cal_status.setText("全局校准: 未校准，请先做全局校准")
            self.global_cal_btn.setText("全局校准(7点)")
            # 未做全局校准时，快速校准不可用（快速校准依赖全局曲线）
            self.cal_scheme_combo.setEnabled(True)
            self.cal_toggle_btn.setEnabled(True)
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
            profile["calibration_type"] = "none"
            profile["quick_calibration"] = None
            profile["full_calibration"] = None
            profile["quick_min_delta"] = 0.0
            profile["quick_max_delta"] = 0.0
            self.cal_status_label.setText("当前方案未校准")
            self.cal_scheme_combo.blockSignals(True)
            self.cal_scheme_combo.setCurrentIndex(0)
            self.cal_scheme_combo.blockSignals(False)
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
        self.config.delete_angle_meter_profile(name)
        self._refresh_profile_list()
        # 删除后无配置时清空参数显示
        if not self.config.get_current_angle_meter_profile():
            self.cal_status_label.setText("当前方案未校准")
            self.angle_display.setText("--.-")

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
        cal_data = self.config.get_effective_angle_meter_calibration(name)
        cal = AngleCalibration.from_list(cal_data) if cal_data else None
        self.tracker.set_vehicle_config(
            profile.get("min_angle", -80.0),
            profile.get("max_angle", 80.0),
            cal)
        self.angle_display.setText(f"{profile.get('min_angle', -80.0):+.1f}°")

    # === 校准 ===
    def _on_global_cal(self):
        """全局校准：7点，范围固定-80~80，完成后保存到全局并触发快校重新生成"""
        if not self.calibrator:
            return
        if self.calibrator.is_calibrating:
            self.calibrator.cancel()
            return
        self._global_calibrating = True
        self.calibrator.start("full", -80.0, 80.0)
        self._show_overlay()
        self.cal_toggle_btn.setText("取消校准")
        # F1: 全局校准开始后自动最小化主窗口
        if self.window():
            self.window().showMinimized()

    def _on_cal_toggle(self):
        """开始或取消载具校准（根据当前校准状态）"""
        if not self.calibrator:
            return
        if self.calibrator.is_calibrating:
            self.calibrator.cancel()
            return
        name = self.config.get_current_angle_meter_profile()
        if not name:
            self.cal_status_label.setText("请先创建角度仪配置")
            return
        p = self.config.get_angle_meter_profile(name)
        scheme = self.cal_scheme_combo.currentIndex()
        self._global_calibrating = False
        if scheme == 0:
            self.cal_status_label.setText("请先选择校准方案")
            return
        if scheme == 1 and not self.config.is_global_calibrated():
            self.cal_status_label.setText("快速校准依赖全局校准，请先做全局校准")
            return
        if scheme == 1:
            self.calibrator.start("quick", p.get("min_angle", -80), p.get("max_angle", 80))
        elif scheme == 2:
            self.calibrator.start("full", p.get("min_angle", -80), p.get("max_angle", 80))
        else:
            return
        self._show_overlay()
        self.cal_toggle_btn.setText("取消校准")
        # F1: 校准开始后自动最小化主窗口
        if self.window():
            self.window().showMinimized()

    def _on_cal_scheme_changed(self, index):
        """切换校准方案：立即更新AngleTracker"""
        if self._loading:
            return
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        type_map = {0: "none", 1: "quick", 2: "full"}
        ctype = type_map.get(index, "none")
        self.config.set_angle_meter_calibration_type(name, ctype)
        self._apply_current_profile_to_tracker()
        self._load_profile_params(name)

    def _on_cal_progress(self, step, total):
        self.cal_status_label.setText(f"校准中: {step}/{total}")
        self.cal_toggle_btn.setText("取消校准")

    def _on_cal_hint(self, step, total, target):
        hint = f"→ 请将炮塔调到 {target:.1f}°，按校准确认热键 ({step+1}/{total})"
        self.cal_hint_label.setText(hint)
        if self.overlay:
            self.overlay.set_hint(hint)

    def _on_cal_done(self, cal):
        self.cal_hint_label.setText("")
        self.cal_toggle_btn.setText("开始校准")
        # F1: 校准完成后恢复主窗口
        if self.window():
            self.window().showNormal()
        if self.overlay:
            self.overlay.set_hint("")
            if not self.tracker or self.tracker.state != "ACTIVE":
                self.overlay.hide()
        if getattr(self, '_global_calibrating', False):
            # 全局校准完成：保存到全局，触发所有载具快校重新生成
            self.config.set_global_calibration(cal.to_list())
            self.global_cal_status.setText("全局校准: 已校准 ✓")
            self.global_cal_btn.setText("重新校准全局")
            # 更新Calibrator的全局曲线
            if self.calibrator:
                self.calibrator.global_cal = cal
            self.cal_status_label.setText("全局校准完成，载具快速校准已自动更新")
            self._global_calibrating = False
        else:
            # 载具校准完成：根据当前方案保存
            name = self.config.get_current_angle_meter_profile()
            if name:
                scheme = self.cal_scheme_combo.currentIndex()
                if scheme == 1:  # 快速校准(3点)
                    # 保存min/mid/max_delta用于重校全局后重新生成
                    min_d = cal.min_delta
                    mid_d = cal.points[3][0]  # 7点曲线中间点
                    max_d = cal.max_delta
                    self.config.set_angle_meter_quick_calibration(name, cal.to_list(), min_d, mid_d, max_d)
                elif scheme == 2:  # 单独校准
                    self.config.set_angle_meter_full_calibration(name, cal.to_list())
                if self.tracker:
                    self.tracker.set_calibration(cal)
                self._load_profile_params(name)

    def _on_cal_cancelled(self):
        self.cal_hint_label.setText("")
        self.cal_toggle_btn.setText("开始校准")
        # F1: 校准取消后恢复主窗口
        if self.window():
            self.window().showNormal()
        if self.overlay:
            self.overlay.set_hint("")
            if not self.tracker or self.tracker.state != "ACTIVE":
                self.overlay.hide()
        self._global_calibrating = False
        self.cal_status_label.setText("当前方案未校准")

    # === 使用 ===
    def _show_overlay(self):
        if self.overlay:
            self.overlay.show()
            self.overlay.move(100, 100)

    def _on_toggle_use(self):
        if not self.tracker:
            return
        if self.tracker.state in ("ACTIVE", "PAUSED"):
            self.tracker.stop()
            if self.overlay:
                self.overlay.hide()
        else:
            name = self.config.get_current_angle_meter_profile()
            if not name:
                self.use_hint_label.setText("⚠ 请先创建角度仪配置")
                return
            # 检查是否有可用校准（全局或载具）
            cal_data = self.config.get_effective_angle_meter_calibration(name)
            if not cal_data and not self.config.is_global_calibrated():
                self.use_hint_label.setText("⚠ 请先做全局校准或载具校准")
                return
            self.tracker.start()
            self._show_overlay()

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
            self.toggle_use_btn.setText("停止")
            self.use_hint_label.setText("✓ 使用中，角度从最低角开始累积")
        elif state == "PAUSED":
            self.toggle_use_btn.setText("停止")
            self.use_hint_label.setText("⏸ 已暂离，按暂离/恢复继续")
        else:
            self.toggle_use_btn.setText("开始使用")
            self.use_hint_label.setText("⚠ 使用前请将炮塔调到最低角，然后按开始")

    def _on_angle(self, angle):
        self.angle_display.setText(f"{angle:+.1f}°")
        if self.overlay:
            self.overlay.set_angle(angle)

    # === 热键 ===
    def _load_hotkeys(self):
        hks = self.config.get_angle_meter_hotkeys()
        for action, widget in [("toggle", self.hk_toggle), ("pause", self.hk_pause),
                               ("calibrate", self.hk_calibrate), ("reset", self.hk_reset),
                               ("up", self.hk_up), ("down", self.hk_down)]:
            # 统一双键结构，角度仪 UI 只用 key1（单键绑定）
            key = hks.get(action, {}).get("key1", "")
            widget._key = key
            widget.setText(HotkeyManager.get_key_name(key) if key else "")

    def _on_hotkey_captured(self, action, key):
        # 统一双键结构，角度仪只用 slot=1（单键绑定）
        self.config.set_angle_meter_hotkey(action, key, "keydown", slot=1)
        self.hotkey.reload_hotkeys()

    def _on_hotkey_toggle(self):
        if self.tracker:
            if self.tracker.state in ("ACTIVE", "PAUSED"):
                self.tracker.stop()
                if self.overlay:
                    self.overlay.hide()
                self.toggle_use_btn.setText("开始使用")
            else:
                self.tracker.start()
                self._show_overlay()
                self.toggle_use_btn.setText("停止")

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

    # === 热键微调（长按连续注入）===
    def _on_up_pressed(self):
        """上移微调按下：SendInput 模拟鼠标上移。
        三档：点按(单次) / 短长按(1.0-1.5s,步长1,50ms) / 长长按(>1.5s,步长2,30ms)。
        任何状态下都触发（使用中/校准中），SendInput 使游戏炮管和角度仪示数同步。"""
        if not self.raw or self.tracker is None:
            return
        self._up_pressed = True
        self._up_pressed_time = time.time()
        self._up_accel = False
        _simulate_mouse_move(-1)  # 点按立即触发一次
        if self._up_timer:
            self._up_timer.setInterval(50)
            self._up_timer.start()

    def _on_up_tick(self):
        if not self.raw or not self._up_pressed or self.tracker is None:
            return
        held = time.time() - self._up_pressed_time
        if held < 1.0:
            return  # 点按阶段：等释放，不连续触发
        if held < 1.5:
            # 短长按：步长1，间隔50ms
            if self._up_accel:
                self._up_accel = False
                self._up_timer.setInterval(50)
            _simulate_mouse_move(-1)
        else:
            # 长长按：步长2，间隔30ms
            if not self._up_accel:
                self._up_accel = True
                self._up_timer.setInterval(30)
            _simulate_mouse_move(-2)

    def _on_up_released(self):
        self._up_pressed = False
        self._up_accel = False
        if self._up_timer:
            self._up_timer.stop()

    def _on_down_pressed(self):
        """下移微调按下：SendInput 模拟鼠标下移。
        三档：点按(单次) / 短长按(1.0-1.5s,步长1,50ms) / 长长按(>1.5s,步长2,30ms)。
        任何状态下都触发（使用中/校准中），SendInput 使游戏炮管和角度仪示数同步。"""
        if not self.raw or self.tracker is None:
            return
        self._down_pressed = True
        self._down_pressed_time = time.time()
        self._down_accel = False
        _simulate_mouse_move(1)  # 点按立即触发一次
        if self._down_timer:
            self._down_timer.setInterval(50)
            self._down_timer.start()

    def _on_down_tick(self):
        if not self.raw or not self._down_pressed or self.tracker is None:
            return
        held = time.time() - self._down_pressed_time
        if held < 1.0:
            return  # 点按阶段：等释放，不连续触发
        if held < 1.5:
            # 短长按：步长1，间隔50ms
            if self._down_accel:
                self._down_accel = False
                self._down_timer.setInterval(50)
            _simulate_mouse_move(1)
        else:
            # 长长按：步长2，间隔30ms
            if not self._down_accel:
                self._down_accel = True
                self._down_timer.setInterval(30)
            _simulate_mouse_move(2)

    def _on_down_released(self):
        self._down_pressed = False
        self._down_accel = False
        if self._down_timer:
            self._down_timer.stop()

    # === 生命周期 ===
    def showEvent(self, event):
        """P1-1: 首次显示时加载数据"""
        super().showEvent(event)
        if not self._data_loaded:
            self._refresh_profile_list()
            if self.config.is_angle_meter_enabled():
                self._init_engine()
                self._set_controls_enabled(True)
            else:
                self._set_controls_enabled(False)
            self._data_loaded = True
        elif self.config.is_angle_meter_enabled() and self.tracker is None:
            self._init_engine()

    def shutdown(self):
        self._shutdown_engine()
