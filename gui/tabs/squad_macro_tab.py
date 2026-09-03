"""建队宏页：循环开关、热键、名称、锁队、载具选择"""
from PyQt5.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFrame,
    QGroupBox, QLabel, QCheckBox, QLineEdit, QSpinBox, QPushButton
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from gui.widgets import HotkeyLineEdit, VehicleFilterWidget


class SquadMacroTab(QWidget):
    def __init__(self, config: ConfigManager, hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.hotkey = hotkey
        self.squad_macro = None
        self._data_loaded = False
        self._build_ui()

    def showEvent(self, event):
        """P1-1: 首次显示时加载数据，避免__init__阻塞"""
        super().showEvent(event)
        if not self._data_loaded:
            self._update_controls_enabled()
            self._refresh_vehicle_list()
            self._data_loaded = True

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

        # === 建队循环 ===
        loop_group = QGroupBox("建队循环")
        loop_vlayout = QVBoxLayout(loop_group)
        loop_row = QHBoxLayout()
        self.enable_cb = QCheckBox("启用建队循环")
        self.enable_cb.stateChanged.connect(self._on_enable_changed)
        self.enable_cb.setChecked(self.config.is_squad_macro_enabled())
        loop_row.addWidget(self.enable_cb)
        loop_row.addStretch()
        loop_row.addWidget(QLabel("建队热键:"))
        self.hotkey_edit = HotkeyLineEdit()
        sm_hk = self.config.get_squad_macro_hotkey()
        if sm_hk.get("key1"):
            self.hotkey_edit.setText(HotkeyManager.get_key_name(sm_hk["key1"]))
        self.hotkey_edit.hotkeyCaptured.connect(self._on_hotkey_captured)
        loop_row.addWidget(self.hotkey_edit)
        self.start_btn = QPushButton("开始循环")
        self.start_btn.setObjectName("primary_btn")
        self.start_btn.setToolTip("开始建队循环并最小化窗口，自动切换到游戏")
        self.start_btn.clicked.connect(self._on_start_clicked)
        loop_row.addWidget(self.start_btn)
        loop_vlayout.addLayout(loop_row)
        hint1 = QLabel("无日志读取功能请自行判断循环时机")
        hint1.setObjectName("hint_text")
        loop_vlayout.addWidget(hint1)
        hint_interval_row = QHBoxLayout()
        hint2 = QLabel("触发热键开始循环，再次触发热键会停止循环并停用建队循环，再次使用请到建队宏页面手动开启")
        hint2.setObjectName("hint_text")
        hint2.setWordWrap(True)
        hint_interval_row.addWidget(hint2, stretch=1)
        hint_interval_row.addWidget(QLabel("循环间隔(ms):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(50, 5000)
        self.interval_spin.setSingleStep(50)
        self.interval_spin.setValue(self.config.get_squad_macro_interval())
        self.interval_spin.setFixedWidth(90)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        hint_interval_row.addWidget(self.interval_spin)
        loop_vlayout.addLayout(hint_interval_row)
        layout.addWidget(loop_group)

        # === 建队设置 ===
        setting_group = QGroupBox("建队设置")
        setting_layout = QHBoxLayout(setting_group)
        setting_layout.addWidget(QLabel("小队名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入小队名称变量")
        self.name_edit.setText(self.config.get_squad_macro_name())
        self.name_edit.editingFinished.connect(self._on_name_changed)
        setting_layout.addWidget(self.name_edit, 2)
        setting_layout.addStretch()
        self.locked_cb = QCheckBox("锁队建立")
        self.locked_cb.setChecked(self.config.is_squad_macro_locked())
        self.locked_cb.stateChanged.connect(self._on_locked_changed)
        setting_layout.addWidget(self.locked_cb)
        layout.addWidget(setting_group)

        # === 载具选择 ===
        vehicle_group = QGroupBox("载具选择（点击填充小队名称）")
        vehicle_layout = QVBoxLayout(vehicle_group)
        self.vf = VehicleFilterWidget(mode="click")
        self.vf.setMinimumHeight(180)
        self.vf.filter_changed.connect(self._refresh_vehicle_list)
        self.vf.vehicle_clicked.connect(self._on_vehicle_clicked)
        vehicle_layout.addWidget(self.vf)
        layout.addWidget(vehicle_group)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _update_controls_enabled(self):
        enabled = self.enable_cb.isChecked()
        self.name_edit.setEnabled(enabled)
        self.locked_cb.setEnabled(enabled)
        self.vf.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.interval_spin.setEnabled(enabled)
        self.hotkey_edit.setEnabled(enabled)

    def _on_interval_changed(self, value):
        self.config.set_squad_macro_interval(value)

    def _init_macro(self):
        if self.squad_macro is None:
            from core.squad_macro import SquadMacro
            self.squad_macro = SquadMacro()
            self.squad_macro.on_stopped = self._on_macro_stopped

    def _shutdown_macro(self):
        if self.squad_macro:
            if self.squad_macro.running:
                self.squad_macro.stop()
            self.squad_macro = None

    def _on_enable_changed(self, state):
        enabled = state == Qt.Checked
        self.config.set_squad_macro_enabled(enabled)
        self._update_controls_enabled()
        if enabled:
            self._init_macro()
        else:
            self._shutdown_macro()
        self.hotkey.reload_hotkeys()

    def _on_hotkey_captured(self, key):
        self.config.set_squad_macro_hotkey(key if key else "", "keydown")
        self.hotkey.reload_hotkeys()

    def _on_name_changed(self):
        self.config.set_squad_macro_name(self.name_edit.text())

    def _on_locked_changed(self, state):
        self.config.set_squad_macro_locked(state == Qt.Checked)

    def _refresh_vehicle_list(self):
        self.vf.set_tags(self.config.get_all_tags())
        search, tag = self.vf.get_filter()
        names = self.config.get_vehicle_names_filtered(search, tag)
        self.vf.populate([(n, self.config.get_vehicle_tags(n)) for n in names])

    def _on_vehicle_clicked(self, name):
        if name:
            self.name_edit.setText(name)
            self.config.set_squad_macro_name(name)

    def _start_loop(self):
        if not self.config.is_squad_macro_enabled() or self.squad_macro is None:
            return False
        name = self.config.get_squad_macro_name()
        if not name.strip():
            return False
        if self.squad_macro.running:
            self.squad_macro.stop()
            return False
        locked = self.config.is_squad_macro_locked()
        interval = self.config.get_squad_macro_interval()
        cmd = f'CreateSquad "{name.strip()}" {"1" if locked else "0"}'
        QApplication.clipboard().setText(cmd)
        self.squad_macro.start(name, locked, interval)
        return True

    def _on_start_clicked(self):
        if self._start_loop():
            self.window().showMinimized()
            QTimer.singleShot(200, self._switch_to_game)

    def _switch_to_game(self):
        from core.squad_macro import find_game_window, activate_window, alt_tab
        hwnd = find_game_window("squad")
        if hwnd:
            activate_window(hwnd)
        else:
            alt_tab()

    def on_hotkey(self):
        """建队宏热键触发：供 main_window 调用"""
        if self.squad_macro is None:
            return
        if self.squad_macro.running:
            self.squad_macro.stop()
        elif self._start_loop():
            pass

    def _on_macro_stopped(self):
        QTimer.singleShot(0, self._do_macro_stopped)

    def _do_macro_stopped(self):
        if self.enable_cb.isChecked():
            self.enable_cb.setChecked(False)

    def shutdown(self):
        self._shutdown_macro()
