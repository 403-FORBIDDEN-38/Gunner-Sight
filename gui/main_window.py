"""
主窗口模块 (Main Window)

软件主界面：左侧导航 + 右侧内容区，所有功能页由独立 tab 组件实现。
本文件仅负责：导航、顶栏、主题、跨页信号协调、关闭清理。
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QListWidget, QApplication,
    QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
    QFrame
)
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import Qt, QUrl

from core.config_manager import ConfigManager
from core.state_machine import StateMachine
from core.overlay import OverlayRenderer
from core.hotkey_manager import HotkeyManager
from core.resource_manager import ResourceManager
from gui.widgets import OptimizedListWidget

from gui.tabs.overview_tab import OverviewTab
from gui.tabs.vehicle_config_tab import VehicleConfigTab
from gui.tabs.hotkey_tab import HotkeyTab
from gui.tabs.rangefinder_tab import RangefinderTab
from gui.tabs.squad_macro_tab import SquadMacroTab
from gui.tabs.resource_tab import ResourceTab
from gui.tabs.info_tab import InfoTab
from gui.tabs.angle_meter_tab import AngleMeterTab


class MainWindow(QMainWindow):
    """主窗口：纯导航 + 跨页协调"""

    def __init__(self, config: ConfigManager, state: StateMachine,
                 overlay: OverlayRenderer, hotkey: HotkeyManager,
                 resources: ResourceManager):
        super().__init__()
        self.config = config
        self.state = state
        self.overlay = overlay
        self.hotkey = hotkey
        self.resources = resources

        self.setWindowTitle("GunnerSight Overlay - 屏幕准星辅助软件")
        self.resize(1100, 750)
        self.setMinimumSize(800, 600)

        self._current_theme = self.config.get_theme()
        self._scrolling = False  # 预留：防止信号循环
        self._setup_style(self._current_theme)
        self._create_ui()
        self._connect_signals()
        self._apply_theme(self._current_theme)

        # 启动刷新：概览页 + 数显模块（数显热键需启动时注册，不依赖进入导航页）
        self.overview_tab.refresh()
        self.rangefinder_tab.refresh()

    # ==================== 主题 ====================

    def _setup_style(self, theme="dark"):
        if theme == "light":
            bg = "#F5F5F5"; ctrl = "#FFFFFF"; border = "#D0D0D0"
            hover = "#E8E8E8"; text = "#222222"; subtext = "#666666"; dis_text = "#AAAAAA"
        else:
            bg = "#202020"; ctrl = "#2A2A2A"; border = "#3A3A3A"
            hover = "#333333"; text = "#E0E0E0"; subtext = "#888888"; dis_text = "#666666"

        self.setStyleSheet(f"""
            QWidget {{ background-color: {bg}; color: {text}; font-size: 14px; }}
            QMainWindow {{ background-color: {bg}; }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QAbstractItemView {{
                background-color: {ctrl}; color: {text};
                border: 1px solid {border}; border-radius: 2px; padding: 4px 6px;
            }}
            QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: #0030FF; }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: #0030FF; }}
            QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QAbstractItemView:disabled {{
                color: {dis_text}; border-color: {ctrl};
            }}
            QAbstractItemView::item {{ padding: 5px; background-color: {ctrl}; }}
            QAbstractItemView::item:selected {{ background-color: #0030FF; color: #FFFFFF; }}
            QAbstractItemView::item:hover:!selected {{ background-color: {hover}; }}
            QPushButton {{
                background-color: {ctrl}; color: {text};
                border: 1px solid {border}; border-radius: 2px; padding: 5px 12px;
            }}
            QPushButton:hover {{ background-color: {hover}; border-color: #0030FF; }}
            QPushButton:pressed {{ background-color: #0030FF; color: #FFFFFF; }}
            QPushButton:disabled {{ color: {dis_text}; background-color: {bg}; }}
            QGroupBox {{
                border: 1px solid {border}; border-radius: 2px;
                margin-top: 10px; padding-top: 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {subtext}; font-size: 12px;
            }}
            QCheckBox {{ spacing: 6px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border: 1px solid {border}; border-radius: 2px; background-color: {ctrl};
            }}
            QCheckBox::indicator:checked {{ background-color: #0030FF; border-color: #0030FF; }}
            QCheckBox:disabled {{ color: {dis_text}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {border}; }}
            QSlider::handle:horizontal {{
                width: 12px; height: 12px; margin: -4px 0;
                background: #0030FF; border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{ background: #0030FF; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{ border: 1px solid #0030FF; }}
            QScrollBar:vertical {{ width: 10px; background: {bg}; }}
            QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {hover}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ height: 10px; background: {bg}; }}
            QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 30px; }}
            QScrollBar::handle:horizontal:hover {{ background: {hover}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QLabel {{ background-color: transparent; }}
            QListWidget#nav_list {{ border: none; background-color: {bg}; }}
            QListWidget#nav_list::item {{ padding: 8px 12px; background-color: {bg}; }}
            QListWidget#nav_list::item:selected {{ background-color: #0030FF; color: #FFFFFF; }}
            QListWidget#nav_list::item:hover:!selected {{ background-color: {ctrl}; }}
            QFrame#angle_meter_sep, QFrame#rangefinder_sep {{
                background-color: {border};
                max-height: 1px; min-height: 1px;
                border: none;
            }}

            QLabel#info_title {{ font-size: 24px; font-weight: bold; }}
            QLabel#hint_text {{ font-size: 12px; color: {subtext}; }}
            QLabel#cal_hint {{ font-size: 12px; color: #FFAA00; }}
            QLabel#angle_display {{ font-size: 36px; font-weight: bold; }}
            QLabel#angle_display[state="idle"] {{ color: #888888; }}
            QLabel#angle_display[state="active"] {{ color: #00FF00; }}
            QLabel#angle_display[state="paused"] {{ color: #FF6600; }}
            QLabel#angle_display[state="calibrating"] {{ color: #FFAA00; }}
            QPushButton#link_btn {{
                color: #0030FF; border: none; background: transparent;
                padding: 2px 0px; text-align: left;
            }}
            QPushButton#link_btn:hover {{ color: #3355FF; }}
            QPushButton#primary_btn {{
                background-color: #0030FF; color: #FFFFFF; border-color: #0030FF;
            }}
            QPushButton#primary_btn:hover {{ background-color: #0040FF; }}
            QPushButton#primary_btn:disabled {{ background-color: {border}; border-color: {border}; color: {dis_text}; }}
            QPushButton#toggle_primary_btn:checked {{
                background-color: #0030FF; color: #FFFFFF; border-color: #0030FF;
            }}
            QPushButton#toggle_primary_btn:checked:hover {{ background-color: #0040FF; }}
            QLabel#free_notice {{
                font-size: 12px; color: #8A6D00;
                background-color: rgba(255, 200, 0, 25);
                border: 1px solid rgba(200, 160, 0, 60);
                border-radius: 4px; padding: 10px;
            }}
        """)

    def _apply_theme(self, theme):
        self._current_theme = theme
        self._setup_style(theme)
        self.theme_btn.setText("浅色" if theme == "light" else "深色")

    def _toggle_theme(self):
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self.config.set_theme(new_theme)
        self._apply_theme(new_theme)

    # ==================== UI 构建 ====================

    def _create_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 顶栏
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)
        self.state_label = QLabel("载具: 未选择 | 弹种: 未选择 | 倍率: 无")
        top_layout.addWidget(self.state_label)
        top_layout.addStretch()
        self.overlay_toggle_btn = QPushButton("隐藏准星")
        self.overlay_toggle_btn.setObjectName("toggle_primary_btn")
        self.overlay_toggle_btn.setCheckable(True)
        self.overlay_toggle_btn.setChecked(True)
        top_layout.addWidget(self.overlay_toggle_btn)
        self.theme_btn = QPushButton("浅色")
        self.theme_btn.setFixedHeight(24)
        self.theme_btn.setToolTip("切换浅色/深色模式")
        self.theme_btn.clicked.connect(self._toggle_theme)
        top_layout.addWidget(self.theme_btn)
        main_layout.addWidget(top_bar)

        # 导航 + 内容
        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        nav_col = QWidget()
        nav_col.setFixedWidth(140)
        nav_col_layout = QVBoxLayout(nav_col)
        nav_col_layout.setContentsMargins(0, 0, 0, 0)
        nav_col_layout.setSpacing(0)

        self.nav_list = OptimizedListWidget()
        self.nav_list.setObjectName("nav_list")
        self.nav_list.setFocusPolicy(Qt.NoFocus)
        nav_col_layout.addWidget(self.nav_list, 1)

        mortar_btn = QPushButton("猜点与迫炮")
        mortar_btn.setObjectName("link_btn")
        mortar_btn.setCursor(Qt.PointingHandCursor)
        mortar_btn.setFixedHeight(36)
        mortar_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://squadcalc.app/?map=Jensen")))
        nav_col_layout.addWidget(mortar_btn)

        armor_btn = QPushButton("装甲与图鉴\n需科学上网")
        armor_btn.setObjectName("link_btn")
        armor_btn.setCursor(Qt.PointingHandCursor)
        armor_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://squad-armor.com/vehicles")))
        nav_col_layout.addWidget(armor_btn)

        nav_layout.addWidget(nav_col)

        # 页签式容器 + 右侧翻页按钮
        content_with_nav = QWidget()
        content_layout = QHBoxLayout(content_with_nav)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.tab_stack = QStackedWidget()
        content_layout.addWidget(self.tab_stack, 1)
        # 右侧翻页按钮栏
        page_nav_col = QWidget()
        page_nav_col.setFixedWidth(36)
        pn_layout = QVBoxLayout(page_nav_col)
        pn_layout.setContentsMargins(2, 0, 2, 0)
        pn_layout.setSpacing(4)
        self.prev_page_btn = QPushButton("▲")
        self.prev_page_btn.setFixedSize(32, 32)
        self.prev_page_btn.setToolTip("上一页")
        self.prev_page_btn.clicked.connect(self._go_prev_page)
        pn_layout.addWidget(self.prev_page_btn)
        pn_layout.addStretch()
        self.next_page_btn = QPushButton("▼")
        self.next_page_btn.setFixedSize(32, 32)
        self.next_page_btn.setToolTip("下一页")
        self.next_page_btn.clicked.connect(self._go_next_page)
        pn_layout.addWidget(self.next_page_btn)
        content_layout.addWidget(page_nav_col)
        nav_layout.addWidget(content_with_nav, 1)
        main_layout.addWidget(nav_container)

        self._nav_pages = []
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        # 创建所有 tab
        self.overview_tab = OverviewTab(config=self.config, state=self.state,
                                        hotkey=self.hotkey, resources=self.resources,
                                        overlay=self.overlay)
        self.vehicle_tab = VehicleConfigTab(config=self.config, state=self.state,
                                            resources=self.resources)
        self.hotkey_tab = HotkeyTab(config=self.config, state=self.state, hotkey=self.hotkey)
        self.rangefinder_tab = RangefinderTab(config=self.config, hotkey=self.hotkey)
        self.angle_meter_tab = AngleMeterTab(config=self.config, hotkey=self.hotkey)
        self.squad_macro_tab = SquadMacroTab(config=self.config, hotkey=self.hotkey)
        self.resource_tab = ResourceTab(config=self.config, resources=self.resources)
        self.info_tab = InfoTab(resources=self.resources)

        self._add_page(self.overview_tab, "全局设置")
        self._add_page(self.vehicle_tab, "载具配置")
        self._add_page(self.hotkey_tab, "热键设置")
        self._add_page(self.rangefinder_tab, "信息数显")
        self._add_page(self.angle_meter_tab, "角度仪")
        self._add_page(self.squad_macro_tab, "建队宏")
        self._add_page(self.resource_tab, "资源库")
        self._add_page(self.info_tab, "信息")

        # 初始化：选中第一页（触发 _on_nav_changed 切换 tab_stack + 更新翻页按钮）
        self.nav_list.setCurrentRow(0)

        # 禁用焦点防空格误触
        self._disable_control_focus()
        QApplication.instance().installEventFilter(self)

    def _add_page(self, widget, name):
        self._nav_pages.append(name)
        self.tab_stack.addWidget(widget)
        self.nav_list.addItem(name)

    def _on_nav_changed(self, index):
        self.tab_stack.setCurrentIndex(index)
        self._update_page_nav_buttons(index)


    def _go_prev_page(self):
        """跳转到上一导航页"""
        idx = self.nav_list.currentRow()
        if idx > 0:
            self.nav_list.setCurrentRow(idx - 1)

    def _go_next_page(self):
        """跳转到下一导航页"""
        idx = self.nav_list.currentRow()
        if idx < len(self._nav_pages) - 1:
            self.nav_list.setCurrentRow(idx + 1)

    def _update_page_nav_buttons(self, index):
        """根据当前页面索引显示/隐藏上下翻页按钮"""
        self.prev_page_btn.setVisible(index > 0)
        self.next_page_btn.setVisible(index < len(self._nav_pages) - 1)

    def _disable_control_focus(self, widget=None):
        if widget is None:
            widget = self
        for child in widget.findChildren(QPushButton):
            child.setFocusPolicy(Qt.NoFocus)
        for child in widget.findChildren(QCheckBox):
            child.setFocusPolicy(Qt.NoFocus)
        for child in widget.findChildren(QComboBox):
            child.setFocusPolicy(Qt.NoFocus)
        for child in widget.findChildren(QSlider):
            child.setFocusPolicy(Qt.NoFocus)
        for child in widget.findChildren(QSpinBox):
            child.setFocusPolicy(Qt.ClickFocus)
        for child in widget.findChildren(QDoubleSpinBox):
            child.setFocusPolicy(Qt.ClickFocus)

    # ==================== 信号连接 ====================

    def _connect_signals(self):
        # 状态机（细粒度信号：ammo_type_changed 已覆盖载具切换时的刷新）
        self.state.magnification_changed.connect(self._on_magnification_changed)
        self.state.ammo_type_changed.connect(self._on_ammo_type_changed)
        self.state.overlay_toggled.connect(lambda _: self._refresh_status_bar())

        # 顶栏
        self.overlay_toggle_btn.toggled.connect(self._on_overlay_toggle)

        # 概览页
        self.overview_tab.connect_signals(
            on_vehicle_changed=self._on_quick_vehicle_changed,
            on_ammo_changed=self.state.set_ammo_type,
            on_preview_scale=self._on_preview_scale)

        # 热键页
        self.hotkey_tab.connect_signals(on_global_hotkey_changed=self._on_global_hotkey_changed)

        # 其他 tab
        self.vehicle_tab.connect_signals()
        self.vehicle_tab.data_changed.connect(self.overview_tab.refresh_vehicle_list)
        self.resource_tab.connect_signals()

        # 热键管理器信号
        self.hotkey.toggle_overlay_triggered.connect(self.state.toggle_overlay)
        self.hotkey.cycle_magnification_triggered.connect(self.state.cycle_magnification)
        self.hotkey.invert_colors_triggered.connect(self.overlay.toggle_invert_colors)
        self.hotkey.reset_magnification_triggered.connect(self.state.reset_magnification)
        self.hotkey.ammo_switch_triggered.connect(self.state.set_ammo_type)
        self.hotkey.rangefinder_measure_triggered.connect(self.rangefinder_tab.on_measure_hotkey)
        self.hotkey.toggle_ui_triggered.connect(self.rangefinder_tab.on_toggle_ui_hotkey)
        self.hotkey.squad_macro_triggered.connect(self.squad_macro_tab.on_hotkey)

    # ==================== 跨页回调 ====================

    def _on_magnification_changed(self, _index):
        self._refresh_status_bar()
        # 仅当概览页可见时刷新预览，避免游戏中高频切换时磁盘IO
        if self.overview_tab.isVisible():
            self.overview_tab.refresh_preview()

    def _on_ammo_type_changed(self, _ammo_name):
        self._refresh_status_bar()
        # 概览页不可见时跳过刷新，showEvent 会补刷
        if self.overview_tab.isVisible():
            self.overview_tab.refresh_ammo()
            self.overview_tab.refresh_preview()

    def _on_overlay_toggle(self, checked):
        self.state.set_overlay_visible(checked)

    def _on_quick_vehicle_changed(self, name):
        if name:
            self.state.set_vehicle(name)
            # 切换载具重建弹种热键列表 + 重新注册热键（只注册当前载具的弹种键）
            self.hotkey_tab.refresh_ammo_hotkeys()
            self.hotkey.reload_hotkeys()
            # 自动切换关联的测距仪配置
            if self.config.is_rangefinder_enabled():
                linked = self.config.get_rangefinder_profile_for_vehicle(name)
                self.rangefinder_tab.switch_profile(linked)

    def _on_preview_scale(self, value):
        self.overview_tab.preview_scale_label.setText(f"{value}%")
        self.overview_tab.preview_widget.set_scale(value)

    def _on_global_hotkey_changed(self, key, hk):
        self.hotkey.set_hotkey_pair(key, hk)

    # ==================== 刷新 ====================

    def _refresh_status_bar(self):
        summary = self.state.get_state_summary()
        self.state_label.setText(summary)
        visible = self.state.overlay_visible
        self.overlay_toggle_btn.blockSignals(True)
        self.overlay_toggle_btn.setChecked(visible)
        self.overlay_toggle_btn.blockSignals(False)
        self.overlay_toggle_btn.setText("隐藏准星" if visible else "显示准星")

    # ==================== 事件 ====================

    def eventFilter(self, obj, event):
        if event.type() == event.Wheel:
            if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox)):
                if not obj.hasFocus():
                    return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        _t0 = time.perf_counter()
        # 先立即隐藏所有窗口（用户感知到程序立即关闭）
        self.hide()
        if self.rangefinder_tab.rangefinder_overlay:
            self.rangefinder_tab.rangefinder_overlay.hide()
        if self.rangefinder_tab.rangefinder_overlay2:
            self.rangefinder_tab.rangefinder_overlay2.hide()
        if self.overlay:
            self.overlay.hide()
        print(f"[性能] 关闭-窗口隐藏 耗时={(time.perf_counter()-_t0)*1000:.0f}ms")
        # 后台执行清理（停止线程、钩子、释放资源）
        _t1 = time.perf_counter()
        self.rangefinder_tab.shutdown()
        print(f"[性能] 关闭-数显模块清理 耗时={(time.perf_counter()-_t1)*1000:.0f}ms")
        _t2 = time.perf_counter()
        self.angle_meter_tab.shutdown()
        print(f"[性能] 关闭-角度仪清理(RawInput注销) 耗时={(time.perf_counter()-_t2)*1000:.0f}ms")
        _t3 = time.perf_counter()
        self.squad_macro_tab.shutdown()
        print(f"[性能] 关闭-建队宏清理 耗时={(time.perf_counter()-_t3)*1000:.0f}ms")
        _t4 = time.perf_counter()
        self.hotkey.shutdown()
        print(f"[性能] 关闭-热键注销 耗时={(time.perf_counter()-_t4)*1000:.0f}ms")
        # 保存配置
        _t5 = time.perf_counter()
        self.config.save_config()
        print(f"[性能] 关闭-配置保存 耗时={(time.perf_counter()-_t5)*1000:.0f}ms")
        print(f"[性能] 关闭总耗时={(time.perf_counter()-_t0)*1000:.0f}ms")
        event.accept()
        QApplication.instance().quit()
