"""标定测距模块设置页（FEATURE-3并入GS主程序）

可关闭模式：默认禁用，禁用时零消耗（不创建DistanceMeter/Overlay，不注册热键）。
复用项目已有模块：ConfigManager配置、HotkeyManager热键、HotkeyPairWidget双键绑定。
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel,
                             QDoubleSpinBox, QGroupBox)
from PyQt5.QtCore import Qt

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.distance_meter import DistanceMeter
from core.distance_overlay import DistanceOverlay
from gui.hotkey_widgets import HotkeyPairWidget


class DistanceMeterTab(QWidget):
    """标定测距设置页"""

    def __init__(self, config: ConfigManager, hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.hotkey = hotkey
        self.meter = None  # DistanceMeter逻辑对象（启用时创建）
        self.overlay = None  # 悬浮窗口（启用时创建）

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 启用开关（单独不受禁用影响）
        self.enable_check = QCheckBox("启用标定测距模块")
        self.enable_check.setChecked(self.config.is_distance_meter_enabled())
        self.enable_check.toggled.connect(self._on_enable_toggle)
        layout.addWidget(self.enable_check)

        # 设置容器（禁用时整体不可用）
        self.settings_container = QWidget()
        sc = QVBoxLayout(self.settings_container)
        sc.setContentsMargins(0, 0, 0, 0)
        sc.setSpacing(8)

        # 操作提示
        hint = QLabel("操作流程：1.启用模块 2.按记录热键标定比例尺两端 3.按测算热键测距目标两端\n"
                      "组合键+记录=切换比例尺(33/100/300/900循环)  组合键+测算=沿用上一次点1快速测距")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        sc.addWidget(hint)

        # 状态显示
        status_group = QGroupBox("当前状态")
        sg = QVBoxLayout(status_group)
        self.scale_label = QLabel("比例尺：300m")
        self.calib_label = QLabel("标定状态：未标定")
        sg.addWidget(self.scale_label)
        sg.addWidget(self.calib_label)
        sc.addWidget(status_group)

        # 热键设置（4个HotkeyPairWidget）
        hk_group = QGroupBox("热键设置")
        hg = QVBoxLayout(hk_group)
        self.hk_toggle = HotkeyPairWidget("启用/禁用")
        self.hk_record = HotkeyPairWidget("记录")
        self.hk_measure = HotkeyPairWidget("测算")
        self.hk_modifier = HotkeyPairWidget("组合键")
        for w in [self.hk_toggle, self.hk_record, self.hk_measure, self.hk_modifier]:
            hg.addWidget(w)
        self.hk_toggle.hotkey_changed.connect(lambda d: self._on_hotkey_changed("toggle", d))
        self.hk_record.hotkey_changed.connect(lambda d: self._on_hotkey_changed("record", d))
        self.hk_measure.hotkey_changed.connect(lambda d: self._on_hotkey_changed("measure", d))
        self.hk_modifier.hotkey_changed.connect(lambda d: self._on_hotkey_changed("modifier", d))
        sc.addWidget(hk_group)

        # 悬浮窗口设置（右下偏移）
        ov_group = QGroupBox("悬浮窗口设置（右下偏移）")
        og = QHBoxLayout(ov_group)
        og.addWidget(QLabel("X偏移："))
        self.offset_x = QDoubleSpinBox()
        self.offset_x.setRange(0, 2000)
        self.offset_x.setDecimals(0)
        og.addWidget(self.offset_x)
        og.addWidget(QLabel("Y偏移："))
        self.offset_y = QDoubleSpinBox()
        self.offset_y.setRange(0, 2000)
        self.offset_y.setDecimals(0)
        og.addWidget(self.offset_y)
        og.addStretch()
        self.offset_x.valueChanged.connect(self._on_offset_changed)
        self.offset_y.valueChanged.connect(self._on_offset_changed)
        sc.addWidget(ov_group)

        sc.addStretch()
        layout.addWidget(self.settings_container)

        # 加载热键配置
        self._load_hotkeys()
        # 加载偏移
        ox, oy = self.config.get_distance_meter_overlay_offset()
        self.offset_x.setValue(ox)
        self.offset_y.setValue(oy)

        # 如果已启用，初始化引擎
        if self.config.is_distance_meter_enabled():
            self._init_engine()
        self.settings_container.setEnabled(self.config.is_distance_meter_enabled())

    def _load_hotkeys(self):
        hks = self.config.get_distance_meter_hotkeys()
        self.hk_toggle.set_hotkey(hks.get("toggle", {}))
        self.hk_record.set_hotkey(hks.get("record", {}))
        self.hk_measure.set_hotkey(hks.get("measure", {}))
        self.hk_modifier.set_hotkey(hks.get("modifier", {}))

    def _on_hotkey_changed(self, action: str, hk: dict):
        self.config.set_distance_meter_hotkey(action, hk["key1"], hk["trigger1"], 1)
        self.config.set_distance_meter_hotkey(action, hk["key2"], hk["trigger2"], 2)
        if self.meter is not None:
            self.hotkey.reload_hotkeys()

    def _on_offset_changed(self):
        self.config.set_distance_meter_overlay_offset(
            int(self.offset_x.value()), int(self.offset_y.value()))
        if self.overlay is not None:
            self._position_overlay()

    def _on_module_toggle(self, enabled: bool):
        """第一层：UI开关控制模块开启/关闭（创建/销毁meter+overlay，注册/unregister热键）"""
        self.config.set_distance_meter_enabled(enabled)
        if enabled:
            self._init_engine()
        else:
            self._shutdown_engine()
        self.settings_container.setEnabled(enabled)
        self.hotkey.reload_hotkeys()

    def _on_enable_toggle(self, enabled: bool):
        self._on_module_toggle(enabled)

    def _init_engine(self):
        if self.meter is not None:
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
        # 刷新状态
        self._update_status_display()

    def _shutdown_engine(self):
        if self.meter is not None:
            # 断开热键信号
            try:
                self.hotkey.distance_meter_toggle_triggered.disconnect(self._on_toggle_hotkey)
                self.hotkey.distance_meter_record_triggered.disconnect(self._on_record_hotkey)
                self.hotkey.distance_meter_measure_triggered.disconnect(self._on_measure_hotkey)
            except (TypeError, RuntimeError):
                pass
            # BUG-10: 禁用模块时清理标定数据（不清理热键配置和悬浮位置）
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
                self.overlay.set_result(parts['result'], parts.get('result_color', '#00ff88'))
            # 无result时不调用set_result，保留set_state_hint的状态提示

    # === 热键回调 ===
    def _on_toggle_hotkey(self):
        """第二层：热键只切换流程启用状态（_flow_active），不销毁meter不隐藏overlay"""
        if self.meter is None:
            return  # 模块未开启时热键不响应
        self.meter.toggle()  # 切换_flow_active
        self._update_status_display()

    def _on_record_hotkey(self):
        if self.meter is None:
            return
        # 组合键+记录=切换比例尺
        if self.meter.is_modifier_pressed():
            self.meter.cycle_scale(-1)  # 循环切换
        else:
            self.meter.record_point()
        self._update_status_display()

    def _on_measure_hotkey(self):
        if self.meter is None:
            return
        # 组合键+测算=沿用上一次点1
        if self.meter.is_modifier_pressed():
            self.meter.quick_measure()
        else:
            self.meter.measure_point()
        self._update_status_display()

    def shutdown(self):
        """程序关闭时调用"""
        self._shutdown_engine()
