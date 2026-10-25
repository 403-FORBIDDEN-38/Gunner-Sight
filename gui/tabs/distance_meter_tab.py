"""标定测距模块设置页（并入GS主程序）

可关闭模式：默认禁用，禁用时零消耗（不创建DistanceMeter/Overlay，不注册热键）。
复用项目已有模块：ConfigManager配置、HotkeyManager热键、HotkeyPairWidget双键绑定。
"""
from core.colors import DISTANCE_CALIBRATED
from gui.widgets import make_group_box, make_settings_container
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import ConfigManager
from core.distance_meter import DistanceMeter
from core.distance_overlay import DistanceOverlay
from core.hotkey_manager import HotkeyManager
from gui.hotkey_widgets import HotkeyPairWidget


class DistanceMeterTab(QWidget):
    """标定测距设置页"""

    def __init__(self, config: ConfigManager, hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.hotkey = hotkey
        self.meter = None  # DistanceMeter逻辑对象（启用时创建）
        self.overlay = None  # 悬浮窗口（启用时创建）

        self._build_ui()
        self._connect_ui_signals()

        self.refresh()  # config→UI 加载（热键+偏移+禁用状态）
        # 电闸：用户开关控制模块是否加载
        if self.config.is_distance_meter_enabled():
            self._init_engine()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 电闸：启用开关（单独不受禁用影响）
        self.enable_check = QCheckBox("启用标定测距模块")
        self.enable_check.setChecked(self.config.is_distance_meter_enabled())
        layout.addWidget(self.enable_check)

        # 设置容器（禁用时整体不可用）
        self.settings_container, sc = make_settings_container()

        # 操作提示
        hint = QLabel("操作流程：1.启用模块 2.按标定热键标定比例尺两端 3.按测距热键测距目标两端")
        hint.setWordWrap(True)
        hint.setObjectName("hint_text")
        sc.addWidget(hint)

        # 状态显示
        status_group, sg = make_group_box("当前状态", flat=True)

        self.scale_label = QLabel("比例尺：300m")
        self.calib_label = QLabel("标定状态：未标定")
        sg.addWidget(self.scale_label)
        sg.addWidget(self.calib_label)
        sc.addWidget(status_group)

        # 热键设置（全部独立热键，支持修饰键组合）
        hk_group, hg = make_group_box("热键设置")
        self.hk_record = HotkeyPairWidget("标定")
        hg.addWidget(self.hk_record)
        self.hk_measure = HotkeyPairWidget("测距")
        hg.addWidget(self.hk_measure)
        self.hk_cycle_scale = HotkeyPairWidget("切换比例尺")
        hg.addWidget(self.hk_cycle_scale)
        self.hk_quick_measure = HotkeyPairWidget("快速测距")
        hg.addWidget(self.hk_quick_measure)
        sc.addWidget(hk_group)

        # 悬浮窗口设置（右下偏移）
        ov_group, og = make_group_box("悬浮窗口设置（右下偏移）", layout_cls=QHBoxLayout, flat=True)

        og.addWidget(QLabel("横向偏移："))
        self.offset_x_spin = QDoubleSpinBox()
        self.offset_x_spin.setRange(0, 2000)
        self.offset_x_spin.setDecimals(0)
        og.addWidget(self.offset_x_spin)
        og.addWidget(QLabel("竖向偏移："))
        self.offset_y_spin = QDoubleSpinBox()
        self.offset_y_spin.setRange(0, 2000)
        self.offset_y_spin.setDecimals(0)
        og.addWidget(self.offset_y_spin)
        og.addStretch()
        sc.addWidget(ov_group)

        sc.addStretch()
        layout.addWidget(self.settings_container)

    def _connect_ui_signals(self):
        self.enable_check.toggled.connect(self._on_enable_toggle)
        self.hk_record.hotkey_changed.connect(lambda d: self._on_hotkey_changed("record", d))
        self.hk_measure.hotkey_changed.connect(lambda d: self._on_hotkey_changed("measure", d))
        self.hk_cycle_scale.hotkey_changed.connect(lambda d: self._on_hotkey_changed("cycle_scale", d))
        self.hk_quick_measure.hotkey_changed.connect(lambda d: self._on_hotkey_changed("quick_measure", d))
        self.offset_x_spin.valueChanged.connect(self._on_offset_changed)
        self.offset_y_spin.valueChanged.connect(self._on_offset_changed)

    def refresh(self):
        """config→UI 统一加载入口：热键 + 偏移 + 禁用状态"""
        self._load_hotkeys()
        ox, oy = self.config.get_distance_meter_overlay_offset()
        self.offset_x_spin.setValue(ox)
        self.offset_y_spin.setValue(oy)
        self.settings_container.setEnabled(self.config.is_distance_meter_enabled())

    def _load_hotkeys(self):
        hks = self.config.get_distance_meter_hotkeys()
        self.hk_record.set_hotkey(hks.get("record", {}))
        self.hk_measure.set_hotkey(hks.get("measure", {}))
        self.hk_cycle_scale.set_hotkey(hks.get("cycle_scale", {}))
        self.hk_quick_measure.set_hotkey(hks.get("quick_measure", {}))

    def _on_hotkey_changed(self, action: str, hk: dict):
        self.config.set_distance_meter_hotkey(action, hk["key1"], hk["trigger1"], 1)
        self.config.set_distance_meter_hotkey(action, hk["key2"], hk["trigger2"], 2)
        if self.meter is not None:
            self.hotkey.reload_hotkeys()

    def _on_offset_changed(self):
        self.config.set_distance_meter_overlay_offset(
            int(self.offset_x_spin.value()), int(self.offset_y_spin.value()))
        if self.overlay is not None:
            self._position_overlay()

    def _on_enable_toggle(self, enabled: bool):
        self._on_module_toggle(enabled)

    def _on_module_toggle(self, enabled: bool):
        """电闸：用户开关控制模块加载/卸载（创建/销毁meter+overlay，注册/unregister热键）"""
        self.config.set_distance_meter_enabled(enabled)
        if enabled:
            self._init_engine()
        else:
            self._shutdown_engine()
        self.settings_container.setEnabled(enabled)
        self.hotkey.reload_hotkeys()

    def set_function_active(self, active: bool):
        """暂离控制：暂离中激活，游戏中暂停。
        注意：外部 suspend 与内部 active 语义相反——
        滚轮暂离时用户不看滚轮，正好让标定测距工作。"""
        if self.meter is not None:
            self.meter.set_flow_active(active)
            self._update_status_display()
        if self.overlay is not None:
            self.overlay.set_active(active)

    def _init_engine(self):
        if self.meter is not None:
            if self.overlay is None:
                self.overlay = DistanceOverlay()
                self.overlay.show()
                self._position_overlay()
            return
        self.meter = DistanceMeter(self.config)
        self.meter.set_status_callback(self._on_meter_status)
        self.overlay = DistanceOverlay()
        self.overlay.show()
        self._position_overlay()
        # 热键信号
        self.hotkey.distance_meter_toggle_triggered.connect(self._on_toggle_hotkey)
        self.hotkey.distance_meter_record_triggered.connect(self._on_record_hotkey)
        self.hotkey.distance_meter_measure_triggered.connect(self._on_measure_hotkey)
        self.hotkey.distance_meter_cycle_scale_triggered.connect(self._on_cycle_scale_hotkey)
        self.hotkey.distance_meter_quick_measure_triggered.connect(self._on_quick_measure_hotkey)
        # 刷新状态
        self._update_status_display()

    def _shutdown_engine(self):
        if self.meter is not None:
            # 断开所有热键信号
            for signal, cb in [
                (self.hotkey.distance_meter_toggle_triggered, self._on_toggle_hotkey),
                (self.hotkey.distance_meter_record_triggered, self._on_record_hotkey),
                (self.hotkey.distance_meter_measure_triggered, self._on_measure_hotkey),
                (self.hotkey.distance_meter_cycle_scale_triggered, self._on_cycle_scale_hotkey),
                (self.hotkey.distance_meter_quick_measure_triggered, self._on_quick_measure_hotkey),
            ]:
                try:
                    signal.disconnect(cb)
                except (TypeError, RuntimeError):
                    pass
            # 禁用模块时清理标定数据（不清理热键配置和悬浮位置）
            self.config.clear_distance_meter_calibration()
            self.meter = None
        if self.overlay is not None:
            self.overlay.hide()
            self.overlay = None
        self.scale_label.setText("比例尺：300m")
        self.calib_label.setText("标定状态：未标定")

    def _position_overlay(self):
        """右下偏移定位：x=屏宽-offset_x-窗口宽, y=屏高-offset_y-窗口高"""
        if self.overlay is None:
            return
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        w = self.overlay.width()
        h = self.overlay.height()
        ox, oy = self.config.get_distance_meter_overlay_offset()
        x = screen.width() - ox - w
        y = screen.height() - oy - h
        self.overlay.move(max(0, x), max(0, y))

    def _on_meter_status(self, state, message):
        self._update_status_display()

    def _update_status_display(self):
        if self.meter is None:
            return
        parts = self.meter.get_status_parts()
        self.scale_label.setText(f"比例尺：{parts['scale']}")
        state_text = parts['state_word']
        if parts['result']:
            self.calib_label.setText(f"标定状态：{state_text} | {parts['result']}")
        else:
            self.calib_label.setText(f"标定状态：{state_text}")
        if self.overlay is not None:
            self.overlay.set_scale(parts['scale'])
            self.overlay.set_state_hint(parts['state_word'], parts['state_color'], parts.get('hint', ''))
            if parts.get('result'):
                self.overlay.set_result(parts['result'], parts.get('result_color', DISTANCE_CALIBRATED))
            # 无result时不调用set_result，保留set_state_hint的状态提示

    # === 热键回调 ===
    def _on_toggle_hotkey(self):
        if self.meter is None:
            return
        self.meter.toggle()
        self._update_status_display()

    def _on_record_hotkey(self):
        if self.meter is None:
            return
        self.meter.record_point()
        self._update_status_display()

    def _on_measure_hotkey(self):
        if self.meter is None:
            return
        self.meter.measure_point()
        self._update_status_display()

    def _on_cycle_scale_hotkey(self):
        """切换比例尺热键触发（独立热键，支持修饰键组合）"""
        if self.meter is None:
            return
        self.meter.cycle_scale(-1)
        self._update_status_display()

    def _on_quick_measure_hotkey(self):
        """快速测距热键触发（沿用上一次点1，独立热键，支持修饰键组合）"""
        if self.meter is None:
            return
        self.meter.quick_measure()
        self._update_status_display()

    def shutdown(self):
        """程序关闭时调用"""
        self._shutdown_engine()


