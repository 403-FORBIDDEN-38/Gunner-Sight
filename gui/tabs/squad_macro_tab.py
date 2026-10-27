"""建队宏页：循环开关、热键、名称、锁队、载具选择"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.cleanup import safe_call
from gui.hotkey_widgets import HotkeyLineEdit, HotkeyPairWidget
from gui.widgets import make_group_box, make_settings_container, VehicleFilterWidget


class SquadMacroTab(QWidget):
    def __init__(self, config: ConfigManager, hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.hotkey = hotkey
        self.squad_macro = None
        self._build_ui()
        self._connect_ui_signals()
        # 根源修复：启动时如果已启用就初始化宏，不再等showEvent懒加载
        # （main_window会主动创建启用的进阶模块tab，确保__init__被调用）
        if self.config.is_squad_macro_enabled():
            self._init_macro()
        # 根源修复：必须在__init__中实际加载数据，不能只设标志位
        # 否则关闭状态不禁用、载具列表为空（批次 5：原 showEvent 懒加载分支已随之删除）
        self.settings_container.setEnabled(self.enable_check.isChecked())
        self._refresh_vehicle_list()

    def _build_ui(self):
        # 不用滚动区：内容固定，载具选择组 stretch=1 填满页面剩余高度
        # （滚动区里 content 高度=内容高度，stretch 吃不到窗口空余）
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # 启用开关（在 settings_container 外，不被禁用）
        enable_row = QHBoxLayout()
        self.enable_check = QCheckBox("启用建队循环")
        self.enable_check.blockSignals(True)
        self.enable_check.setChecked(self.config.is_squad_macro_enabled())
        self.enable_check.blockSignals(False)
        enable_row.addWidget(self.enable_check)
        enable_row.addStretch()
        outer.addLayout(enable_row)

        # 设置容器（禁用时整体不可用）
        self.settings_container, sc = make_settings_container()

        # === 建队循环 ===
        loop_group, loop_vlayout = make_group_box("建队循环", flat=True)

        # 第一行：建队热键（左）+ 开始循环（右）
        loop_row1 = QHBoxLayout()
        loop_row1.addWidget(QLabel("建队热键:"))
        self.hotkey_edit = HotkeyPairWidget()
        self.hotkey_edit.set_hotkey(self.config.get_squad_macro_hotkey())
        loop_row1.addWidget(self.hotkey_edit, 1)
        loop_row1.addStretch()
        self.start_btn = QPushButton("开始循环")
        self.start_btn.setObjectName("primary_btn")
        loop_row1.addWidget(self.start_btn)
        loop_vlayout.addLayout(loop_row1)
        # 第三行：控制台键 + 循环间隔
        loop_row3 = QHBoxLayout()
        loop_row3.addWidget(QLabel("控制台键:"))
        self.console_key_edit = HotkeyLineEdit()
        console_key = self.config.get_squad_macro_console_key()
        if console_key:
            from core.hotkey_manager import HotkeyManager
            self.console_key_edit.setText(HotkeyManager.get_key_name(console_key))
        loop_row3.addWidget(self.console_key_edit, 1)
        loop_row3.addWidget(QLabel("间隔(ms):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(50, 5000)
        self.interval_spin.setSingleStep(50)
        self.interval_spin.setFixedWidth(80)
        self.interval_spin.blockSignals(True)
        self.interval_spin.setValue(self.config.get_squad_macro_interval())
        self.interval_spin.blockSignals(False)
        loop_row3.addWidget(self.interval_spin)
        loop_vlayout.addLayout(loop_row3)
        hint1 = QLabel("无日志读取功能请自行判断循环时机。触发热键开始循环，再次触发热键会停止循环并停用建队循环，再次使用请到建队宏页面手动开启")
        hint1.setObjectName("hint_text")
        hint1.setWordWrap(True)
        loop_vlayout.addWidget(hint1)
        sc.addWidget(loop_group)

        # === 建队设置 ===
        setting_group, setting_layout = make_group_box("建队设置", layout_cls=QHBoxLayout)
        setting_layout.addWidget(QLabel("小队名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入小队名称变量")
        self.name_edit.setText(self.config.get_squad_macro_name())
        setting_layout.addWidget(self.name_edit, 2)
        setting_layout.addStretch()
        self.locked_cb = QCheckBox("锁队建立")
        self.locked_cb.blockSignals(True)
        self.locked_cb.setChecked(self.config.is_squad_macro_locked())
        self.locked_cb.blockSignals(False)
        setting_layout.addWidget(self.locked_cb)
        sc.addWidget(setting_group)

        # === 载具选择（点击填充小队名称）：stretch=1 填满页面剩余高度 ===
        vehicle_group, vehicle_layout = make_group_box("载具选择（点击填充小队名称）", flat=True)

        self.vf = VehicleFilterWidget(mode="click")
        self.vf.setMinimumHeight(180)
        vehicle_layout.addWidget(self.vf, 1)
        sc.addWidget(vehicle_group, 1)

        outer.addWidget(self.settings_container, 1)

    def _connect_ui_signals(self):
        self.enable_check.stateChanged.connect(self._on_enable_toggle)
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.hotkey_edit.hotkey_changed.connect(self._on_hotkey_captured)
        self.console_key_edit.hotkeyCaptured.connect(self._on_console_key_captured)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        self.name_edit.editingFinished.connect(self._on_name_changed)
        self.locked_cb.stateChanged.connect(self._on_locked_changed)
        self.vf.filter_changed.connect(self._refresh_vehicle_list)
        self.vf.vehicle_clicked.connect(self._on_vehicle_clicked)


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
                safe_call("squad_macro.stop", self.squad_macro.stop)
            self.squad_macro = None

    def _on_enable_toggle(self, state):
        enabled = state == Qt.Checked
        self.config.set_squad_macro_enabled(enabled)
        self.settings_container.setEnabled(self.enable_check.isChecked())
        if enabled:
            self._init_macro()
        else:
            self._shutdown_macro()
        self.hotkey.reload_hotkeys()

    def _on_hotkey_captured(self, hk_dict):
        self.config.set_squad_macro_hotkey(hk_dict.get("key1", ""), hk_dict.get("trigger1", "keydown"), slot=1)
        self.config.set_squad_macro_hotkey(hk_dict.get("key2", ""), hk_dict.get("trigger2", "keydown"), slot=2)
        self.hotkey.reload_hotkeys()

    def _on_console_key_captured(self, key):
        # 控制台键只需要指示当前按键是什么，不需要trigger/双键等概念
        if key:
            self.config.set_squad_macro_console_key(key)

    def _on_name_changed(self):
        self.config.set_squad_macro_name(self.name_edit.text())

    def _on_locked_changed(self, state):
        self.config.set_squad_macro_locked(state == Qt.Checked)

    def _refresh_vehicle_list(self):
        self.vf.set_tags(self.config.get_all_tags())
        search, tag = self.vf.get_filter()
        names = self.config.get_vehicle_names_filtered(search, tag)
        self.vf.populate([(n, self.config.get_vehicle_tags(n)) for n in names])

    def refresh_tag_filter(self):
        """标签增删改后，重填 tag_filter 下拉"""
        self.vf.set_tags(self.config.get_all_tags())

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
        console_key = self.config.get_squad_macro_console_key()
        self.squad_macro.start(name, locked, interval, console_key)
        return True

    def _on_start_clicked(self):
        # 按钮启动：先最小化本窗口并切到游戏，等窗口真正聚焦后再开始输出，
        # 避免宏的按键发到本窗口导致命令输入不全。
        self.window().showMinimized()
        QTimer.singleShot(200, self._switch_to_game_then_start)

    def _switch_to_game_then_start(self):
        self._switch_to_game()
        # 给游戏窗口一点时间完成聚焦，再启动输出
        QTimer.singleShot(150, self._start_loop)

    def _switch_to_game(self):
        from core.squad_macro import activate_window, alt_tab, find_game_window
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
            # 停止后关闭模块：取消启用勾选 -> _on_enable_toggle(False) 会释放宏对象并注销热键，
            # 防止误触再按一下又启动。同步在GUI线程执行，不依赖工作线程里的QTimer。
            if self.enable_check.isChecked():
                self.enable_check.setChecked(False)
        elif self._start_loop():
            # 热键启动：用户按热键时已在游戏窗口内，直接开始输出，不切窗口。
            pass

    def _on_macro_stopped(self):
        QTimer.singleShot(0, self._do_macro_stopped)

    def _do_macro_stopped(self):
        if self.enable_check.isChecked():
            self.enable_check.setChecked(False)

    def shutdown(self):
        self._shutdown_macro()
