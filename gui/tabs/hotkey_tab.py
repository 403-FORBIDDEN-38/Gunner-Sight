"""热键设置页：全局热键 + 弹种热键（动态）"""
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.state_machine import StateMachine
from gui.hotkey_widgets import HotkeyPairWidget, PauseHotkeyWidget
from gui.widgets import make_group_box, make_scroll_area


class HotkeyTab(QWidget):
    GLOBAL_HOTKEYS = [
        ("toggle_overlay", "显示/隐藏准星"),
        ("cycle_magnification", "切换倍率"),
        ("invert_colors", "一键反色"),
        ("reset_magnification", "重置倍率"),
    ]

    def __init__(self, config: ConfigManager, state: StateMachine,
                 hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.state = state
        self.hotkey = hotkey
        self._ammo_pairs = []
        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, content, layout = make_scroll_area(spacing=10)

        # 全局热键
        global_group, gl = make_group_box("全局热键")
        gl.setSpacing(2)
        self.global_pairs = {}
        for key, title in self.GLOBAL_HOTKEYS:
            pair = HotkeyPairWidget(title)
            gl.addWidget(pair)
            self.global_pairs[key] = pair
        # 暂离：k1/k2 两个独立单键
        self.pause_widget = PauseHotkeyWidget()
        gl.addWidget(self.pause_widget)
        layout.addWidget(global_group)

        # 弹种热键
        ammo_group, self.ammo_hk_layout = make_group_box("弹种切换热键（当前载具）", flat=True)
        self.ammo_hk_layout.setSpacing(0)
        self.ammo_hk_container = QWidget()
        self.ammo_hk_container_layout = QVBoxLayout(self.ammo_hk_container)
        self.ammo_hk_container_layout.setContentsMargins(0, 0, 0, 0)
        self.ammo_hk_container_layout.setSpacing(0)
        self.ammo_hk_layout.addWidget(self.ammo_hk_container)
        layout.addWidget(ammo_group)

        hint = QLabel("提示：点击热键输入框后按下想要设置的按键即可绑定。按 Esc 取消设置。")
        hint.setObjectName("hint_text")
        layout.addWidget(hint)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _connect_ui_signals(self, on_global_hotkey_changed):
        for key, pair in self.global_pairs.items():
            pair.hotkey_changed.connect(
                lambda hk, k=key: on_global_hotkey_changed(k, hk))
        self.pause_widget.hotkey_changed.connect(
            lambda key_name, hk: on_global_hotkey_changed(key_name, hk))

    def refresh(self):
        """全量刷新：全局热键 + 当前载具弹种热键"""
        self.load_global_hotkeys()
        self.refresh_ammo_hotkeys()

    def load_global_hotkeys(self):
        for key, pair in self.global_pairs.items():
            pair.set_hotkey(self.hotkey.config.get_hotkey(key))
        self.pause_widget.set_hotkey("pause1", self.hotkey.config.get_hotkey("pause1"))
        self.pause_widget.set_hotkey("pause2", self.hotkey.config.get_hotkey("pause2"))

    def refresh_ammo_hotkeys(self):
        """根据当前载具的弹种动态生成热键绑定框（统一双键格式）"""
        for pair in self._ammo_pairs:
            pair.setParent(None)
            pair.deleteLater()
        self._ammo_pairs.clear()

        vehicle = self.state.current_vehicle
        if not vehicle:
            return
        ammos = self.config.get_ammo_type_names(vehicle)
        for ammo in ammos:
            pair = HotkeyPairWidget(ammo)
            pair.set_hotkey(self.config.get_ammo_hotkey(vehicle, ammo))
            pair.hotkey_changed.connect(
                lambda hk, a=ammo: self._on_ammo_hotkey_changed(a, hk))
            self.ammo_hk_container_layout.addWidget(pair)
            self._ammo_pairs.append(pair)

    def _on_ammo_hotkey_changed(self, ammo, hk):
        vehicle = self.state.current_vehicle
        if not vehicle:
            return
        self.config.set_ammo_hotkey(vehicle, ammo, hk.get("key1", ""), hk.get("trigger1", "keydown"), slot=1)
        self.config.set_ammo_hotkey(vehicle, ammo, hk.get("key2", ""), hk.get("trigger2", "keydown"), slot=2)
        # 只重建弹种热键，不 unhook/重建全局键盘钩子（与载具切换同路径），
        # 避免全量 reload 在运行时让新绑热键不即时生效
        self.hotkey.reload_ammo_hotkeys()

