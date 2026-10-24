"""角度仪页：配置列表+关联载具、校准、使用、角度overlay。常闭零消耗。"""

import time

from PyQt5.QtCore import QObject, Qt, QTimer
from PyQt5.QtGui import QColor, QFont

# 统一字体常量（等宽字体用于数字显示）
FONT_CONSOLAS_8 = QFont("Consolas", 8)
FONT_CONSOLAS_10 = QFont("Consolas", 10)
FONT_CONSOLAS_36_BOLD = QFont("Consolas", 36, QFont.Bold)

from core.colors import (ANGLE_ACTIVE, ANGLE_CALIBRATING,
                         OVERLAY_BOX_BG_ALPHA, OVERLAY_BOX_RGB, OVERLAY_TEXT)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QSpinBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.angle_meter import AngleCalibration, AngleTracker, Calibrator, RawInputReader
from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager, _parse_hotkey_name
from core.overlay_base import ClickThroughOverlay
from core.win32_utils import KEY_NAME_VK, send_mouse_input, user32
from core.cleanup import safe_call
from gui.hotkey_widgets import HotkeyPairWidget
from gui.widgets import (FilterListPanel, make_group_box, make_scroll_area,
                         make_settings_container, VehicleFilterWidget, FitTable)


def _simulate_mouse_move(dy):
    """模拟鼠标相对移动。dy: 上移负值，下移正值（和 Raw Input 一致）。
    SendInput 插入的鼠标事件会被 Raw Input 捕获，使游戏和角度仪同步。"""
    send_mouse_input(dy)


# 鼠标键名 -> 虚拟键码

# 键盘特殊键名 -> 虚拟键码

# 滚轮键集合（无按住/释放状态，每次滚动只触发一次，不启动连续注入定时器）
_WHEEL_KEYS = {"mouse_wheel_up", "mouse_wheel_down"}


def _key_to_vk(key_name):
    """将热键名称转换为虚拟键码，失败返回 None。"""
    if not key_name:
        return None
    name = key_name.lower().strip()
    if name in KEY_NAME_VK:
        return KEY_NAME_VK[name]
    if len(name) == 1:
        result = user32.VkKeyScanW(ord(name))
        if result != -1:
            return result & 0xFF
    return None


class AngleOverlay(ClickThroughOverlay):
    """独立悬浮窗：显示角度数字和校准提示。常闭时不创建。继承ClickThroughOverlay自动获得穿透。"""
    def __init__(self):
        super().__init__()
        self.setFixedSize(160, 110)
        self._angle = 0.0
        self._distance = None
        self._hint = ""
        self._state = "idle"
        self._height_diff = 0.0
        self._is_extrapolated = False

    def set_angle(self, angle):
        self._angle = angle
        self.update()

    def set_hint(self, text):
        self._hint = text
        self.update()

    def set_state(self, state):
        self._state = state
        self.update()

    def set_distance(self, distance):
        self._distance = distance
        self.update()

    def set_height_diff(self, v):
        self._height_diff = v
        self.update()

    def set_extrapolated(self, v):
        self._is_extrapolated = v
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtCore import QRect
        from PyQt5.QtGui import QBrush, QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 底框与滚轮/标定测距同源：深黑统一 alpha，不跟主题走
        p.setBrush(QBrush(QColor(*OVERLAY_BOX_RGB, OVERLAY_BOX_BG_ALPHA)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)
        # 高度差（始终显示，为0时灰色）
        if abs(self._height_diff) > 0.01:
            p.setPen(QColor(ANGLE_CALIBRATING))
        else:
            p.setPen(QColor(128, 128, 128))
        fh = QFont("Norwester", 11)
        p.setFont(fh)
        sign = "+" if self._height_diff >= 0 else ""
        p.drawText(QRect(0, 8, self.width(), 18), Qt.AlignCenter, f"Δh{sign}{self._height_diff:.0f}m")
        # 角度数字：与主 tab SSOT——正常白字，暂离/标定中用状态色
        if self._state in ("paused", "calibrating"):
            p.setPen(QColor(ANGLE_CALIBRATING))
        else:
            p.setPen(QColor(OVERLAY_TEXT))
        f = QFont("Norwester", 28, QFont.Bold)
        p.setFont(f)
        p.drawText(QRect(0, 28, self.width(), 40), Qt.AlignCenter, f"{self._angle:+.2f}°")
        # 距离文字（角度下方）
        p.setPen(QColor(ANGLE_ACTIVE))
        f2 = QFont("Norwester", 14)
        p.setFont(f2)
        if self._distance is not None:
            prefix = "~" if self._is_extrapolated else ""
            p.drawText(QRect(0, 70, self.width(), 24), Qt.AlignCenter, f"{prefix}{self._distance:.0f}m")
        else:
            p.drawText(QRect(0, 70, self.width(), 24), Qt.AlignCenter, "无法拟算")
        # 提示文字（左下角）
        if self._hint:
            p.setPen(QColor(ANGLE_CALIBRATING))
            f3 = QFont("Norwester", 9)
            p.setFont(f3)
            p.drawText(8, self.height() - 6, self._hint[:30])
        p.end()


class _FineTuner(QObject):
    """方向微调（上移/下移共用）：短按走一格，长按 400ms 后连发 50ms/格。
    校准时保持原逻辑（立刻走一格，1s 后连发）。
    direction: -1 上移(负增量)，+1 下移(正增量)。释放判据优先用键 released 信号，
    兜底用 GetAsyncKeyState 内核级查询；VK 从 key1/key2 任一槽位解析。"""

    def __init__(self, tab, direction, action, parent=None):
        super().__init__(parent)
        self.tab = tab
        self.direction = direction
        self.action = action  # "up" / "down"
        self._pressed = False
        self._accel = False
        self._pressed_time = 0.0
        self._vk = None
        self._short_press_fired = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._on_delay_timeout)

    STEP_DEG = 0.1
    _SHORT_PRESS_DELAY_MS = 400  # 短按阈值：超过则进入连发
    _REPEAT_MS = 50              # 连发间隔

    def _is_calibrating(self):
        cal = self.tab.calibrator
        return cal is not None and cal.is_calibrating

    def _inject_step_deg(self):
        """使用模式：按当前曲线反查，把炮塔精确移动 STEP_DEG。
        方向: 上(-1)抬角, 下(+1)降角。注入与 RawInput 为 1:1，故严格准。"""
        tr = self.tab.tracker
        cal = tr.active_calibration if tr else None
        if tr is None or cal is None:
            _simulate_mouse_move(self.direction)
            return
        cur_abs = tr._base_delta + tr._cumulative_delta
        target_angle = round(tr.current_angle, 1) + (-self.direction) * self.STEP_DEG
        target_abs = cal.angle_to_delta(target_angle)
        dy = int(round(cur_abs - target_abs))
        if dy != 0:
            _simulate_mouse_move(dy)

    def on_pressed(self):
        tab = self.tab
        if not tab.raw or tab.tracker is None:
            return
        hks = tab.config.get_angle_meter_hotkeys()
        key1 = hks.get(self.action, {}).get("key1", "")
        key2 = hks.get(self.action, {}).get("key2", "")
        _, pure_key1 = _parse_hotkey_name(key1)
        _, pure_key2 = _parse_hotkey_name(key2)
        wheel = bool(pure_key1 in _WHEEL_KEYS or pure_key2 in _WHEEL_KEYS)
        if wheel and not self._is_calibrating():
            # 滚轮：离散事件，直接走一格即结束，不起定时器
            self._vk = None
            self._inject_step_deg()
            return
        self._vk = _key_to_vk(key1) or _key_to_vk(key2)
        self._pressed = True
        self._pressed_time = time.time()
        self._accel = False
        if self._is_calibrating():
            # 校准：立刻走一格，1s 后连发（_tick 里控制）
            _simulate_mouse_move(self.direction)
            self._timer.setInterval(50)
            self._timer.start()
        else:
            # 使用：短按延迟——400ms 内松开走一格，超过则连发
            self._short_press_fired = False
            self._delay_timer.start(self._SHORT_PRESS_DELAY_MS)

    def _on_delay_timeout(self):
        """长按阈值到了：走第一格 + 启动连发"""
        if not self._pressed:
            return
        self._short_press_fired = True
        self._inject_step_deg()
        self._timer.setInterval(self._REPEAT_MS)
        self._timer.start()

    def _tick(self):
        tab = self.tab
        if not tab.raw or not self._pressed or tab.tracker is None:
            return
        if self._vk is not None and not (user32.GetAsyncKeyState(self._vk) & 0x8000):
            self.on_released()
            return
        # ---- 校准：原始单位 + 长按加速 ----
        if self._is_calibrating():
            held = time.time() - self._pressed_time
            if held < 1.0:
                return
            if held < 1.5:
                if self._accel:
                    self._accel = False
                    self._timer.setInterval(50)
                _simulate_mouse_move(self.direction)
            else:
                if not self._accel:
                    self._accel = True
                    self._timer.setInterval(30)
                _simulate_mouse_move(self.direction * 2)
            return
        # ---- 使用：按住则每拍精确走一格 ----
        self._inject_step_deg()

    def on_released(self):
        # 短按：400ms 内松开，delay_timer 还没触发，补走一格
        if self._pressed and not self._short_press_fired and not self._is_calibrating():
            self._inject_step_deg()
        self._delay_timer.stop()
        self._pressed = False
        self._accel = False
        self._vk = None
        self._short_press_fired = False
        self._timer.stop()

    def stop(self):
        self._delay_timer.stop()
        self._timer.stop()
        self._pressed = False
        self._short_press_fired = False


class _HeightTuner(QObject):
    """高度差长按加速：点按±1m，长按1s后50ms/次，长按1.5s后30ms/次±2m。"""
    STEP = 1.0

    def __init__(self, tab, direction, action, parent=None):
        super().__init__(parent)
        self.tab = tab
        self.direction = direction  # +1 增加, -1 减少
        self.action = action
        self._pressed = False
        self._accel = False
        self._pressed_time = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)

    def on_pressed(self):
        name = self.tab.config.get_current_angle_meter_profile()
        if not name:
            return
        hks = self.tab.config.get_angle_meter_hotkeys()
        key1 = hks.get(self.action, {}).get("key1", "")
        key2 = hks.get(self.action, {}).get("key2", "")
        _, pure_key1 = _parse_hotkey_name(key1)
        _, pure_key2 = _parse_hotkey_name(key2)
        if pure_key1 in _WHEEL_KEYS or pure_key2 in _WHEEL_KEYS:
            # 滚轮：离散事件，直接走一格
            self._apply(self.STEP)
            return
        self._pressed = True
        self._pressed_time = time.time()
        self._accel = False
        self._apply(self.STEP)
        self._timer.setInterval(60)
        self._timer.start()

    def _tick(self):
        if not self._pressed:
            return
        held = time.time() - self._pressed_time
        if held < 0.5:
            return  # 前0.5秒不重复（点按已走一格）
        if held < 1.0:
            if self._accel:
                self._accel = False
                self._timer.setInterval(50)
            self._apply(self.STEP)
        else:
            if not self._accel:
                self._accel = True
                self._timer.setInterval(30)
            self._apply(self.STEP * 2)

    def _apply(self, amount):
        name = self.tab.config.get_current_angle_meter_profile()
        if not name:
            return
        hd = self.tab.config.get_height_diff(name) + self.direction * amount
        self.tab.config.set_height_diff(name, hd)
        if self.tab.overlay:
            self.tab.overlay.set_height_diff(hd)
        # 高度差变化后重新计算落点距离
        if self.tab.tracker is not None:
            self.tab._on_angle(self.tab.tracker.current_angle)

    def on_released(self):
        self._pressed = False
        self._timer.stop()


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
        # 热键微调长按（up/down 共用 _FineTuner，_init_engine 时创建）
        self._up_tuner = None
        self._down_tuner = None
        self._height_up_tuner = _HeightTuner(self, +1, "height_up")
        self._height_down_tuner = _HeightTuner(self, -1, "height_down")

        self._data_loaded = False
        self._build_ui()
        self._connect_ui_signals()
        self.refresh()  # config→UI 加载（热键+配置列表+禁用状态）
        # 根源修复：启动时如果已启用就初始化引擎，不再等showEvent懒加载
        # （main_window会主动创建启用的进阶模块tab，确保__init__被调用）
        if self.config.is_angle_meter_enabled():
            self._init_engine()
        self._data_loaded = True

    def _connect_ui_signals(self):
        self.enable_check.toggled.connect(self._on_enable_toggle)
        self.hk_toggle.hotkey_changed.connect(lambda d: self._on_hotkey_captured("toggle", d))
        self.hk_calibrate.hotkey_changed.connect(lambda d: self._on_hotkey_captured("calibrate", d))
        self.hk_up.hotkey_changed.connect(lambda d: self._on_hotkey_captured("up", d))
        self.hk_down.hotkey_changed.connect(lambda d: self._on_hotkey_captured("down", d))
        self.hk_height_up.hotkey_changed.connect(lambda d: self._on_hotkey_captured("height_up", d))
        self.hk_height_down.hotkey_changed.connect(lambda d: self._on_hotkey_captured("height_down", d))
        self.hk_reset.hotkey_changed.connect(lambda d: self._on_hotkey_captured("reset", d))
        # 校准方案下拉框
        self.cal_scheme_combo.currentIndexChanged.connect(self._on_cal_scheme_combo_changed)
        self.min_spin.valueChanged.connect(self._on_profile_param_changed)
        self.max_spin.valueChanged.connect(self._on_profile_param_changed)
        self.auto_reset_check.toggled.connect(self._on_auto_reset_toggled)
        self.overlay_x_spin.valueChanged.connect(self._on_overlay_pos_changed)
        self.overlay_y_spin.valueChanged.connect(self._on_overlay_pos_changed)
        self.profile_search.textChanged.connect(self._refresh_profile_list)
        self.profile_tag_filter.currentIndexChanged.connect(self._refresh_profile_list)
        self.profile_list.currentItemChanged.connect(self._on_profile_select)
        self.profile_list.customContextMenuRequested.connect(self._on_profile_context_menu)
        self.link_vf.filter_changed.connect(self._refresh_linked_vehicles)
        self.link_vf.vehicle_toggled.connect(self._on_linked_vehicle_changed)
        self.profile_panel.add_requested.connect(self._on_add_profile)
        self.profile_panel.rename_requested.connect(self._on_rename_profile)
        self.profile_panel.delete_requested.connect(self._on_delete_profile)
        self.cal_toggle_btn.clicked.connect(self._on_cal_toggle)
        self.toggle_use_btn.clicked.connect(self._on_toggle_use)
        self.sens_spin.valueChanged.connect(lambda v: self.config.set_angle_meter_sens(v))

    def refresh(self):
        """config→UI 统一加载入口：热键 + 配置列表 + 禁用状态"""
        self._load_hotkeys()
        self._refresh_profile_list()
        self.settings_container.setEnabled(self.config.is_angle_meter_enabled())
        ox, oy = self.config.get_angle_meter_overlay_pos()
        if ox is not None:
            self.overlay_x_spin.setValue(ox)
        if oy is not None:
            self.overlay_y_spin.setValue(oy)
        # 游戏灵敏度（用于已校准曲线的自动换算）
        sens = self.config.get_angle_meter_sens()
        if sens:
            self.sens_spin.setValue(sens)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, content, layout = make_scroll_area(spacing=8, horizontal_scroll_off=True)

        self.enable_check = QCheckBox("启用角度仪模块")
        self.enable_check.setChecked(self.config.is_angle_meter_enabled())
        layout.addWidget(self.enable_check)

        self.settings_container, sc_layout = make_settings_container()
        sc_layout.addWidget(self._build_status_section())
        sc_layout.addWidget(self._build_calibration_section())
        sc_layout.addWidget(self._build_config_section())
        sc_layout.addWidget(self._build_firing_table_section())

        layout.addWidget(self.settings_container)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_status_section(self):
        """使用设置区：角度显示、开始/暂停、热键"""
        use_group, use_v = make_group_box("使用设置", flat=True)

        use_v.setSpacing(6)
        self.use_hint_label = QLabel("\u26a0 使用前请将炮塔调到最低角，然后按开始")
        self.use_hint_label.setFont(FONT_CONSOLAS_10)
        self.use_hint_label.setObjectName("hint_text")
        use_v.addWidget(self.use_hint_label)
        self.angle_display = QLabel("+0.0\u00b0")
        self.angle_display.setFont(FONT_CONSOLAS_36_BOLD)
        self.angle_display.setAlignment(Qt.AlignCenter)
        self.angle_display.setObjectName("angle_display")
        self.angle_display.setProperty("state", "idle")
        self.angle_display.setMinimumHeight(60)
        use_v.addWidget(self.angle_display)
        use_btn_row = QHBoxLayout()
        self.toggle_use_btn = QPushButton("开始使用")
        use_btn_row.addWidget(self.toggle_use_btn)
        use_v.addLayout(use_btn_row)
        hk_grid = QGridLayout()
        hk_grid.setSpacing(6)
        hk_grid.addWidget(QLabel("开始/停止:"), 0, 0)
        self.hk_toggle = HotkeyPairWidget()
        hk_grid.addWidget(self.hk_toggle, 0, 1)
        hk_grid.addWidget(QLabel("校准确认:"), 1, 0)
        self.hk_calibrate = HotkeyPairWidget()
        hk_grid.addWidget(self.hk_calibrate, 1, 1)
        fine_tune_sep = QLabel("\u2500\u2500 \u5fae\u8c03\u70ed\u952e \u2500\u2500")
        fine_tune_sep.setObjectName("hint_text")
        fine_tune_sep.setAlignment(Qt.AlignCenter)
        hk_grid.addWidget(fine_tune_sep, 2, 0, 1, 2)
        hk_grid.addWidget(QLabel("上移微调:"), 3, 0)
        self.hk_up = HotkeyPairWidget()
        hk_grid.addWidget(self.hk_up, 3, 1)
        hk_grid.addWidget(QLabel("下移微调:"), 4, 0)
        self.hk_down = HotkeyPairWidget()
        hk_grid.addWidget(self.hk_down, 4, 1)
        hd_sep = QLabel("── 高度差热键 ──")
        hd_sep.setObjectName("hint_text")
        hd_sep.setAlignment(Qt.AlignCenter)
        hk_grid.addWidget(hd_sep, 5, 0, 1, 2)
        hk_grid.addWidget(QLabel("高度差+:"), 6, 0)
        self.hk_height_up = HotkeyPairWidget()
        hk_grid.addWidget(self.hk_height_up, 6, 1)
        hk_grid.addWidget(QLabel("高度差-:"), 7, 0)
        self.hk_height_down = HotkeyPairWidget()
        hk_grid.addWidget(self.hk_height_down, 7, 1)
        # 悬浮窗位置
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("窗口X:"))
        self.overlay_x_spin = QSpinBox()
        self.overlay_x_spin.setRange(-2000, 2000)
        pos_row.addWidget(self.overlay_x_spin)
        pos_row.addWidget(QLabel("Y:"))
        self.overlay_y_spin = QSpinBox()
        self.overlay_y_spin.setRange(-2000, 2000)
        pos_row.addWidget(self.overlay_y_spin)
        pos_row.addStretch()
        hk_grid.addLayout(pos_row, 8, 0, 1, 2)
        hk_grid.setColumnStretch(1, 1)
        use_v.addLayout(hk_grid)
        return use_group

    def _build_calibration_section(self):
        """校准设置区：精度方案、状态、校准按钮"""
        cal_group, cal_v = make_group_box("校准设置")
        cal_v.setSpacing(6)
        # 第一行：精度方案 | 校准状态 | 游戏灵敏度
        scheme_row = QHBoxLayout()
        scheme_row.addWidget(QLabel("精度方案:"))
        self.cal_scheme_combo = QComboBox()
        for cnt in Calibrator.VALID_POINT_COUNTS:
            self.cal_scheme_combo.addItem("%d 点" % cnt, cnt)
        self.cal_scheme_combo.setFixedWidth(100)
        scheme_row.addWidget(self.cal_scheme_combo)
        self.cal_status_label = QLabel("")
        self.cal_status_label.setFont(FONT_CONSOLAS_10)
        scheme_row.addWidget(self.cal_status_label, 1)
        scheme_row.addWidget(QLabel("灵敏度:"))
        self.sens_spin = QDoubleSpinBox()
        self.sens_spin.setRange(0.01, 100.0)
        self.sens_spin.setSingleStep(0.05)
        self.sens_spin.setValue(1.0)
        self.sens_spin.setToolTip("改灵敏度后更新此值，已校准曲线会自动换算")
        self.sens_spin.setFixedWidth(80)
        scheme_row.addWidget(self.sens_spin)
        cal_v.addLayout(scheme_row)
        self.cal_hint_label = QLabel("")
        self.cal_hint_label.setFont(FONT_CONSOLAS_10)
        self.cal_hint_label.setObjectName("cal_hint")
        self.cal_hint_label.setVisible(False)
        cal_v.addWidget(self.cal_hint_label)
        # 第二行：开始校准（全宽）
        self.cal_toggle_btn = QPushButton("开始校准")
        cal_v.addWidget(self.cal_toggle_btn)
        return cal_group

    def _build_config_section(self):
        """角度仪配置区：角度范围、定角装填、配置列表、关联载具"""
        cfg_group, cfg_v = make_group_box("角度仪配置", flat=True)

        cfg_v.setSpacing(8)
        # 第一行：最低角 | 最高角 | 启用定角装填 | 提示文字
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("最低角:"))
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-180, 180); self.min_spin.setSuffix("\u00b0")
        range_row.addWidget(self.min_spin)
        range_row.addWidget(QLabel("最高角:"))
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-180, 180); self.max_spin.setSuffix("\u00b0")
        range_row.addWidget(self.max_spin)
        self.auto_reset_check = QCheckBox("启用定角装填")
        range_row.addWidget(self.auto_reset_check)
        reset_hint = QLabel("适用于开火后角度归于水平的武器")
        reset_hint.setFont(FONT_CONSOLAS_8)
        reset_hint.setObjectName("hint_text")
        range_row.addWidget(reset_hint)
        range_row.addStretch()
        cfg_v.addLayout(range_row)
        # 第二行：定角装填热键
        reset_key_row = QHBoxLayout()
        reset_key_row.addWidget(QLabel("定角装填热键:"))
        self.hk_reset = HotkeyPairWidget()
        reset_key_row.addWidget(self.hk_reset, 1)
        cfg_v.addLayout(reset_key_row)
        sep_param = QFrame(); sep_param.setFrameShape(QFrame.HLine); sep_param.setObjectName("angle_meter_sep")
        cfg_v.addWidget(sep_param)
        cfg_v.addWidget(QLabel("角度仪列表与关联载具"))
        self.link_vf = VehicleFilterWidget(mode="check")
        if hasattr(self.link_vf, 'list'):
            self.link_vf.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.profile_panel = FilterListPanel(placeholder="搜索配置...",
                                             right_widget=self.link_vf,
                                             min_list_height=216)
        self.profile_list = self.profile_panel.list
        self.profile_search = self.profile_panel.search
        self.profile_tag_filter = self.profile_panel.tag_filter
        cfg_v.addWidget(self.profile_panel)
        return cfg_group

    def _build_firing_table_section(self):
        """射表拟合区：自适应高度表格，加行/删行，外层滚动区负责滚动。"""
        ft_group, ft_v = make_group_box("射表拟合")
        ft_v.setSpacing(6)

        self.firing_table = FitTable()
        self.firing_table.setColumnCount(2)
        self.firing_table.setHorizontalHeaderLabels(["角度 (°)", "距离 (m)"])
        self.firing_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.firing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.firing_table.horizontalHeader().setMinimumSectionSize(60)
        self.firing_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.firing_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.firing_table.setRowCount(0)
        ft_v.addWidget(self.firing_table)

        ft_btn_row = QHBoxLayout()
        self.ft_add_btn = QPushButton("加行")
        self.ft_add_btn.clicked.connect(self._on_ft_add_row)
        ft_btn_row.addWidget(self.ft_add_btn)
        self.ft_del_btn = QPushButton("删行")
        self.ft_del_btn.clicked.connect(self._on_ft_del_row)
        ft_btn_row.addWidget(self.ft_del_btn)
        ft_btn_row.addStretch()
        ft_v.addLayout(ft_btn_row)

        self.firing_table.itemChanged.connect(self._on_ft_item_changed)
        self.firing_table.fit_height()

        return ft_group

    def _on_ft_add_row(self):
        row = self.firing_table.rowCount()
        self.firing_table.insertRow(row)
        for col in range(2):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            self.firing_table.setItem(row, col, item)
        self.firing_table.fit_height()
        self._save_firing_table()

    def _on_ft_del_row(self):
        row = self.firing_table.currentRow()
        if row >= 0:
            self.firing_table.removeRow(row)
            self.firing_table.fit_height()
        self._save_firing_table()

    def _load_firing_table(self, profile_name: str):
        self.firing_table.blockSignals(True)
        self.firing_table.setRowCount(0)
        table = self.config.get_firing_table(profile_name)
        # 新格式 {"branches": [...]} → 取第一个分支的 samples
        if isinstance(table, dict) and "branches" in table:
            branches = table.get("branches", [])
            entries = branches[0].get("samples", []) if branches else []
        else:
            entries = table or []
        for entry in entries:
            if isinstance(entry, (list, tuple)):
                angle_val, dist_val = entry[0], entry[1]
            else:
                angle_val = entry.get("angle", "")
                dist_val = entry.get("distance", "")
            row = self.firing_table.rowCount()
            self.firing_table.insertRow(row)
            for col, val in enumerate([angle_val, dist_val]):
                item = QTableWidgetItem(str(val) if val != "" else "")
                item.setTextAlignment(Qt.AlignCenter)
                self.firing_table.setItem(row, col, item)
        self.firing_table.fit_height()
        self.firing_table.blockSignals(False)

    def _on_ft_item_changed(self, item):
        self._save_firing_table()

    def _save_firing_table(self):
        if self._loading:
            return
        profile_name = self.config.get_current_angle_meter_profile()
        if not profile_name:
            return
        samples = []
        for row in range(self.firing_table.rowCount()):
            angle_item = self.firing_table.item(row, 0)
            dist_item = self.firing_table.item(row, 1)
            angle_text = angle_item.text() if angle_item else ""
            dist_text = dist_item.text() if dist_item else ""
            if angle_text and dist_text:
                try:
                    samples.append({"angle": float(angle_text), "distance": float(dist_text)})
                except ValueError:
                    pass
        samples.sort(key=lambda s: s["angle"])
        # 保存为新格式，保留已有其他分支和元数据
        existing = self.config.get_firing_table(profile_name)
        if isinstance(existing, dict) and "branches" in existing:
            branches = existing.get("branches", [])
            if branches:
                branches[0]["samples"] = samples
            else:
                branches.append({"name": "低抛", "samples": samples})
            table = {
                "pitch_range": existing.get("pitch_range"),
                "branches": branches,
                "physics": existing.get("physics", {}),
            }
        else:
            table = {"pitch_range": None, "branches": [{"name": "低抛", "samples": samples}], "physics": {}}
        self.config.set_firing_table(profile_name, table)


    # === 启用/禁用 ===

    def _on_enable_toggle(self, enabled):
        self.config.set_angle_meter_enabled(enabled)
        if enabled:
            self._init_engine()
            self.settings_container.setEnabled(True)
        else:
            self._shutdown_engine()
            self.settings_container.setEnabled(False)
        self.hotkey.reload_hotkeys()

    def _init_engine(self):
        if self.tracker is not None:
            return
        # 无条件断开旧连接，避免重建时重复挂槽（幂等收口）
        for sig, slot in [
            (self.hotkey.angle_meter_toggle_triggered, self._on_hotkey_toggle),
            (self.hotkey.angle_meter_calibrate_triggered, self._on_hotkey_calibrate),
            (self.hotkey.angle_meter_reset_triggered, self._on_hotkey_reset),
            (self.hotkey.angle_meter_height_up_pressed, getattr(self._height_up_tuner, 'on_pressed', None)),
            (self.hotkey.angle_meter_height_up_released, getattr(self._height_up_tuner, 'on_released', None)),
            (self.hotkey.angle_meter_height_down_pressed, getattr(self._height_down_tuner, 'on_pressed', None)),
            (self.hotkey.angle_meter_height_down_released, getattr(self._height_down_tuner, 'on_released', None)),
        ]:
            if slot is None:
                continue
            try:
                sig.disconnect(slot)
            except TypeError:
                pass  # 未连接
        self.raw = RawInputReader()
        self.raw.register()
        self.tracker = AngleTracker(self.raw)
        # 注入校准数据提供者（tracker 不持缓存，每次 start/reset_to_zero 时调 provider）
        self.tracker.set_calibration_provider(self._get_current_calibration)
        # 注入 min/max 数据提供者
        self.tracker.set_min_max_provider(self._get_current_min_max)
        # Calibrator不再需要global_cal
        self.calibrator = Calibrator(self.raw)
        self.overlay = AngleOverlay()
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps，避免0ms占满事件循环导致 Raw Input 消息无法处理
        self._timer.timeout.connect(self.tracker.update)
        # 信号
        self.tracker.started.connect(self._timer.start)
        self.tracker.stopped.connect(self._timer.stop)
        self.tracker.started.connect(self._on_tracker_started)
        self.tracker.state_changed.connect(self._on_state)
        self.tracker.angle_changed.connect(self._on_angle)
        self.calibrator.progress.connect(self._on_cal_progress)
        self.calibrator.hint.connect(self._on_cal_hint)
        self.calibrator.done.connect(self._on_cal_done)
        self.calibrator.cancelled.connect(self._on_cal_cancelled)
        # 热键信号
        self.hotkey.angle_meter_toggle_triggered.connect(self._on_hotkey_toggle)
        self.hotkey.angle_meter_calibrate_triggered.connect(self._on_hotkey_calibrate)
        self.hotkey.angle_meter_reset_triggered.connect(self._on_hotkey_reset)
        self._up_tuner = _FineTuner(self, -1, "up", self)
        self._down_tuner = _FineTuner(self, 1, "down", self)
        self.hotkey.angle_meter_up_pressed.connect(self._up_tuner.on_pressed)
        self.hotkey.angle_meter_up_released.connect(self._up_tuner.on_released)
        self.hotkey.angle_meter_down_pressed.connect(self._down_tuner.on_pressed)
        self.hotkey.angle_meter_down_released.connect(self._down_tuner.on_released)
        self.hotkey.angle_meter_height_up_pressed.connect(self._height_up_tuner.on_pressed)
        self.hotkey.angle_meter_height_up_released.connect(self._height_up_tuner.on_released)
        self.hotkey.angle_meter_height_down_pressed.connect(self._height_down_tuner.on_pressed)
        self.hotkey.angle_meter_height_down_released.connect(self._height_down_tuner.on_released)
        # 刷新
        self._refresh_profile_list()
        self._apply_current_profile_to_tracker()

    def _shutdown_engine(self):
        # 先断开微调 tuner 的热键信号再停用：up/down tuner 每次启用都会重建，
        # 旧 tuner 置 None 前若不断信号，Qt 信号持引用导致旧 tuner 永不释放，
        # 且重建后新旧两套同时响应热键（注入翻倍）。height tuner 常驻不重建，
        # 由 _init_engine 的"先断再连"循环负责。
        for tuner, sigs in [
            (self._up_tuner, (self.hotkey.angle_meter_up_pressed,
                              self.hotkey.angle_meter_up_released)),
            (self._down_tuner, (self.hotkey.angle_meter_down_pressed,
                                self.hotkey.angle_meter_down_released)),
        ]:
            if tuner is None:
                continue
            for sig, slot in ((sigs[0], tuner.on_pressed), (sigs[1], tuner.on_released)):
                try:
                    sig.disconnect(slot)
                except TypeError:
                    pass  # 未连接
        # 先释放最贵的资源：mss 抓屏句柄（OS 级，泄漏代价最高）
        if self.raw:
            safe_call("raw.close", self.raw.close)
            self.raw = None
        # 其余按原顺序逐项隔离，任何一个失败不影响后续
        if self._up_tuner:
            safe_call("up_tuner.stop", self._up_tuner.stop)
            self._up_tuner = None
        if self._down_tuner:
            safe_call("down_tuner.stop", self._down_tuner.stop)
            self._down_tuner = None
        if self._timer:
            safe_call("timer.stop", self._timer.stop)
            self._timer = None
        if self.tracker:
            safe_call("tracker.stop", self.tracker.stop)
            self.tracker = None
        if self.calibrator:
            self.calibrator = None
        if self.overlay:
            safe_call("overlay.hide", self.overlay.hide)
            self.overlay = None
        self.angle_display.setText("+0.0°")
        self.cal_hint_label.setText("")

    # === 配置列表 ===
    def _refresh_profile_list(self):
        # 填充标签筛选下拉框（保持当前选中；选项无变化时不重建）
        self.profile_panel.set_tag_options(self.config.get_all_tags())
        search, tag = self.profile_panel.filter_values()
        profiles = self.config.get_angle_meter_profiles()
        current = self.config.get_current_angle_meter_profile()
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        selected_row = -1
        for name in sorted(profiles.keys()):
            if search and search not in name.lower():
                continue
            vehicles = self.config.get_angle_meter_profile_linked_vehicles(name)
            tags_eff = self.config.get_angle_meter_profile_effective_tags(name)
            # 标签筛选
            if tag and tag not in tags_eff:
                continue
            parts = []
            # 校准状态
            if vehicles:
                parts.append(f"载具:{','.join(vehicles)}")
            if tags_eff:
                parts.append(f"标签:{','.join(tags_eff)}")
            sub = '; '.join(parts) if parts else ''
            self.profile_list.add_item( name, sub, user_data=name)
            if name == current:
                # 恢复选中必须用"实际插入的行号"——用源列表下标会在搜索/筛选时选错行
                selected_row = self.profile_list.count() - 1
        self.profile_list.blockSignals(False)
        if selected_row >= 0:
            self.profile_list.setCurrentRow(selected_row)
        # 当前配置不在筛选结果里时不会有选中信号，主动把参数区载入（等价于用户点选）
        _cur = self.config.get_current_angle_meter_profile()
        if _cur:
            self._load_profile_params(_cur)

    def _on_profile_select(self, current, previous):
        if current is None:
            return
        name = current.data(Qt.UserRole)
        if name == self.config.get_current_angle_meter_profile():
            return
        # ACTIVE 状态下切 profile → 强制 stop tracker + 悬浮窗提示
        if self.tracker and self.tracker.state in (self.tracker.STATE_ACTIVE, self.tracker.STATE_PAUSED):
            self.tracker.stop()
            if self.overlay:
                self.overlay.set_hint("请重试/重启")
        self.config.set_current_angle_meter_profile(name)
        self._load_profile_params(name)
        self._refresh_linked_vehicles()
        self._apply_current_profile_to_tracker()

    def _load_profile_params(self, name):
        profile = self.config.get_angle_meter_profile(name)
        self._loading = True
        self.min_spin.setValue(profile.get("pitch_min", -80.0))
        self.max_spin.setValue(profile.get("pitch_max", 80.0))
        # 精度方案下拉框选中项
        active = profile.get("active_calibration_point_count", 5)
        self.cal_scheme_combo.blockSignals(True)
        idx = self.cal_scheme_combo.findData(active)
        if idx >= 0:
            self.cal_scheme_combo.setCurrentIndex(idx)
        self.cal_scheme_combo.blockSignals(False)
        # 当前方案校准状态
        cal_pts = self.config.get_angle_meter_calibration_points(name)
        if cal_pts and "points" in cal_pts:
            self.cal_status_label.setText("当前方案已校准(%d点)" % len(cal_pts["points"]))
        else:
            self.cal_status_label.setText("当前方案未校准")
        self._load_firing_table(name)
        # 定角装填：恢复当前 profile 的启用状态
        ar = profile.get("auto_reset", False)
        self.auto_reset_check.blockSignals(True)
        self.auto_reset_check.setChecked(ar)
        self.auto_reset_check.blockSignals(False)
        self.hk_reset.setEnabled(ar)
        self._loading = False

    def _on_profile_param_changed(self):
        if self._loading:
            return
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        profile = self.config.get_angle_meter_profile(name)
        new_min = self.min_spin.value()
        new_max = self.max_spin.value()
        # 补充: 范围改变时清空所有精度方案（校准与范围绑定）
        if (abs(new_min - profile.get("pitch_min", -80.0)) > 0.01 or
                abs(new_max - profile.get("pitch_max", 80.0)) > 0.01):
            self.config.clear_all_calibrations(name)
            profile = self.config.get_angle_meter_profile(name)
            self.cal_status_label.setText("范围已变更，所有方案归为未校准")
        profile["pitch_min"] = new_min
        profile["pitch_max"] = new_max
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

    def _on_profile_context_menu(self, pos):
        item = self.profile_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        action_rename = menu.addAction("重命名")
        action_delete = menu.addAction("删除")
        chosen = menu.exec_(self.profile_list.viewport().mapToGlobal(pos))
        if chosen == action_rename:
            self._on_rename_profile()
        elif chosen == action_delete:
            self._on_delete_profile()

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
        # 如果 tracker 在 ACTIVE 状态，先停止（用户主动删了正在用的 profile）
        if self.tracker and self.tracker.state in (self.tracker.STATE_ACTIVE, self.tracker.STATE_PAUSED):
            self.tracker.stop()
            if self.overlay:
                self.overlay.set_hint("请重试/重启")
        self.config.delete_angle_meter_profile(name)
        self._refresh_profile_list()
        # 删除后无配置时清空参数显示
        if not self.config.get_current_angle_meter_profile():
            self.cal_status_label.setText("当前方案未校准")
            self.angle_display.setText("--.-")
        else:
            # 切到新 profile 后，更新 tracker 的 min/max
            self._apply_current_profile_to_tracker()

    # === 关联载具 ===
    def on_vehicle_data_changed(self):
        """载具页数据变更（标签/载具）时刷新关联载具列表和配置列表"""
        if self.config.get_current_angle_meter_profile():
            self._refresh_linked_vehicles()
            self._refresh_profile_list()

    def refresh_tag_filter(self):
        """标签增删改后，重填 tag_filter 下拉"""
        self.profile_panel.set_tag_options(self.config.get_all_tags())
        tags = self.config.get_all_tags()
        self.link_vf.set_tags(tags)

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
        # 延迟到事件循环下一轮刷新：此刻仍处于 link_vf 的 itemChanged 回调内，
        # 同步重建配置列表/再 populate 关联列表会在事件处理中途清空同一列表，导致 Qt 闪退。
        QTimer.singleShot(0, self._refresh_profile_list)

    def _get_current_calibration(self):
        """tracker 校准数据提供者：每次调用都从 config 读最新值"""
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return None
        cal_data = self.config.get_effective_angle_meter_calibration(name)
        return AngleCalibration.from_list(cal_data) if cal_data else None

    def _get_current_min_max(self):
        """tracker min/max 数据提供者：每次调用都从 config 读最新值"""
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return None, None
        profile = self.config.get_angle_meter_profile(name)
        return (profile.get("pitch_min", -80.0),
                profile.get("pitch_max", 80.0))

    def _apply_current_profile_to_tracker(self):
        if not self.tracker:
            return
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        self.tracker.refresh_min_max()
        self.angle_display.setText("%+.1f°" % self.config.get_angle_meter_profile(name).get("pitch_min", -80.0))

    # === 校准（补充: 各精度方案独立保存可切换）===
    def _on_cal_scheme_combo_changed(self, index):
        if self._loading:
            return
        count = self.cal_scheme_combo.itemData(index)
        if count is None:
            return
        self._on_cal_scheme_changed(count)

    def _on_cal_scheme_changed(self, count):
        """切换当前使用的精度方案"""
        if self._loading:
            return
        name = self.config.get_current_angle_meter_profile()
        if not name:
            return
        self.config.set_active_calibration_point_count(name, count)
        self._load_profile_params(name)
        self._apply_current_profile_to_tracker()

    def _on_cal_toggle(self):
        """开始或取消载具校准"""
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
        # 校准前必须停止 tracker，否则定时器会抢先 consume_delta_y()，
        # 导致 Calibrator.next_point() 读到的增量永远为 0
        if self.tracker and self.tracker.state in ("ACTIVE", "PAUSED"):
            self.tracker.stop()
            if self.overlay:
                self.overlay.hide()
        num_points = self.config.get_active_calibration_point_count(name)
        if not self.calibrator.start(num_points, p.get("pitch_min", -80), p.get("pitch_max", 80)):
            self.cal_status_label.setText(f"校准点数 {num_points} 无效（可选2/5/11），请切换精度方案后重试")
            return
        self._show_overlay()
        self.cal_toggle_btn.setText("取消校准")
        # 校准开始后自动最小化主窗口
        if self.window():
            self.window().showMinimized()

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
        # 校准完成后恢复主窗口
        if self.window():
            self.window().showNormal()
        if self.overlay:
            self.overlay.set_hint("")
            if not self.tracker or self.tracker.state != "ACTIVE":
                self.overlay.hide()
        # 补充: 保存到当前active方案，不覆盖其他方案
        name = self.config.get_current_angle_meter_profile()
        if name:
            num_points = self.config.get_active_calibration_point_count(name)
            self.config.set_angle_meter_calibration_points(name, cal.to_list(), num_points)
            self._load_profile_params(name)
            self._refresh_profile_list()

    def _on_cal_cancelled(self):
        self.cal_hint_label.setText("")
        self.cal_toggle_btn.setText("开始校准")
        # 校准取消后恢复主窗口
        if self.window():
            self.window().showNormal()
        if self.overlay:
            self.overlay.set_hint("")
            if not self.tracker or self.tracker.state != "ACTIVE":
                self.overlay.hide()
        self.cal_status_label.setText("校准已取消")

    # === 使用 ===
    def _show_overlay(self):
        if self.overlay:
            self.overlay.show()
            ox, oy = self.config.get_angle_meter_overlay_pos()
            center = QApplication.primaryScreen().geometry().center()
            if ox is not None and oy is not None:
                self.overlay.move(center.x() + ox, center.y() + oy)
            else:
                self.overlay.move(center.x(), center.y())

    def _on_overlay_pos_changed(self):
        x = self.overlay_x_spin.value()
        y = self.overlay_y_spin.value()
        self.config.set_angle_meter_overlay_pos(x, y)
        if self.overlay and self.overlay.isVisible():
            center = QApplication.primaryScreen().geometry().center()
            self.overlay.move(center.x() + x, center.y() + y)

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
            # 检查载具自己的校准曲线
            cal_data = self.config.get_effective_angle_meter_calibration(name)
            if not cal_data:
                self.use_hint_label.setText("⚠ 当前载具未校准，请先做载具校准")
                return
            self.tracker.start()
            self._show_overlay()

    def set_suspended(self, suspended: bool):
        """全局暂离：停止/恢复读取鼠标增量"""
        if not self.tracker:
            return
        # tracker 状态机用 self.state（ACTIVE/PAUSED/IDLE），没有 _paused 字段
        is_paused = (self.tracker.state == self.tracker.STATE_PAUSED)
        if suspended and not is_paused:
            self.tracker.pause_toggle()
        elif not suspended and is_paused:
            self.tracker.pause_toggle()

    def _on_state(self, state):
        self.angle_display.setProperty("state", state.lower())
        self.angle_display.style().unpolish(self.angle_display)
        self.angle_display.style().polish(self.angle_display)
        if self.overlay:
            self.overlay.set_state(state.lower())
        if state == "ACTIVE":
            self.toggle_use_btn.setText("■ 使用中")
            self.toggle_use_btn.setObjectName("primary_btn")
            self.use_hint_label.setText("✓ 使用中，角度从最低角开始累积")
        elif state == "PAUSED":
            self.toggle_use_btn.setText("⏸ 已暂停")
            self.toggle_use_btn.setObjectName("toggle_primary_btn")
            self.use_hint_label.setText("⏸ 已暂离")
        else:
            self.toggle_use_btn.setText("▶ 开始使用")
            self.toggle_use_btn.setObjectName("")
            self.use_hint_label.setText("⚠ 使用前请将炮塔调到最低角，然后按开始")
        self.toggle_use_btn.style().unpolish(self.toggle_use_btn)
        self.toggle_use_btn.style().polish(self.toggle_use_btn)

    def _on_tracker_started(self):
        """tracker 开始时清"请重试/重启"提示"""
        if self.overlay:
            self.overlay.set_hint("")

    def _on_angle(self, angle):
        self.angle_display.setText(f"{angle:+.2f}°")
        profile_name = self.config.get_current_angle_meter_profile()
        dist = None
        is_extrap = False
        if profile_name:
            dist = self.config.query_firing_distance(profile_name, angle)
            is_extrap = self.config.is_firing_extrapolation(profile_name, angle) if dist is not None else False
            # 高度差修正：ΔR = Δh / tan(θ)
            if dist is not None:
                hd = self.config.get_height_diff(profile_name)
                if abs(hd) > 0.01:
                    import math
                    tan_v = math.tan(math.radians(angle))
                    if abs(tan_v) > 0.01:
                        dist = dist + hd / tan_v
        if self.overlay:
            self.overlay.set_angle(angle)
            self.overlay.set_distance(dist)
            self.overlay.set_extrapolated(is_extrap)
            if profile_name:
                self.overlay.set_height_diff(self.config.get_height_diff(profile_name))

    # === 热键 ===
    def _load_hotkeys(self):
        hks = self.config.get_angle_meter_hotkeys()
        for action, widget in [("toggle", self.hk_toggle),
                               ("calibrate", self.hk_calibrate), ("reset", self.hk_reset),
                               ("up", self.hk_up), ("down", self.hk_down),
                               ("height_up", self.hk_height_up), ("height_down", self.hk_height_down)]:
            widget.set_hotkey(hks.get(action, {}))

    def _on_hotkey_captured(self, action, hk_dict):
        self.config.set_angle_meter_hotkey(action, hk_dict.get("key1", ""), hk_dict.get("trigger1", "keydown"), slot=1)
        self.config.set_angle_meter_hotkey(action, hk_dict.get("key2", ""), hk_dict.get("trigger2", "keydown"), slot=2)
        self.hotkey.reload_hotkeys()

    def _on_hotkey_toggle(self):
        if self.tracker:
            if self.tracker.state in ("ACTIVE", "PAUSED"):
                self.tracker.stop()
                if self.overlay:
                    self.overlay.hide()
                self.toggle_use_btn.setText("开始使用")
            else:
                # 每次开始使用时重置高度差
                pn = self.config.get_current_angle_meter_profile()
                if pn:
                    self.config.set_height_diff(pn, 0.0)
                    if self.overlay:
                        self.overlay.set_height_diff(0.0)
                self.tracker.start()
                self._show_overlay()
                self.toggle_use_btn.setText("停止")

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
        """首次显示时加载数据"""
        super().showEvent(event)
        if not self._data_loaded:
            self._refresh_profile_list()
            if self.config.is_angle_meter_enabled():
                self._init_engine()
                self.settings_container.setEnabled(True)
            else:
                self.settings_container.setEnabled(False)
            self._data_loaded = True
        elif self.config.is_angle_meter_enabled() and self.tracker is None:
            self._init_engine()
        # 每次显示都刷新关联载具（载具页标签可能已变更）
        if self.config.get_current_angle_meter_profile():
            self._refresh_linked_vehicles()

    def shutdown(self):
        self._shutdown_engine()

