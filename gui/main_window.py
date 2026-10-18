from core.logger import logger

"""
主窗口模块 (Main Window)

软件主界面：左侧导航 + 右侧内容区，所有功能页由独立 tab 组件实现。
本文件仅负责：导航、顶栏、主题、跨页信号协调、关闭清理。
"""

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.overlay import OverlayRenderer
from core.resource_manager import ResourceManager
from core.state_machine import StateMachine
from gui.tabs.adapt_tab import AdaptTab
from gui.tabs.angle_meter_tab import AngleMeterTab
from gui.tabs.distance_meter_tab import DistanceMeterTab
from gui.tabs.hotkey_tab import HotkeyTab
from gui.tabs.info_tab import InfoTab
from gui.tabs.magnifier_tab import MagnifierTab
from gui.tabs.overview_tab import OverviewTab
from gui.tabs.resource_tab import ResourceTab
from gui.tabs.squad_macro_tab import SquadMacroTab
from gui.tabs.vehicle_config_tab import VehicleConfigTab
from gui.widgets import OptimizedListWidget


class MainWindow(QMainWindow):
    """主窗口：纯导航 + 跨页协调"""
    # Tab 索引常量（导航顺序与 _nav_pages 严格对应）
    TAB_OVERVIEW = 0
    TAB_VEHICLE = 1
    TAB_HOTKEY = 2
    TAB_ANGLE_METER = 3
    TAB_DISTANCE_METER = 4
    TAB_SQUAD_MACRO = 5
    TAB_RESOURCE = 6
    TAB_ADAPT = 7
    TAB_INFO = 8
    TAB_MAGNIFIER = 9

    # 导航分组定义：(分组名, [(TAB常量, 显示名), ...])
    # 不改 TAB_* 常量值，运行时维护 row↔tab 映射
    _NAV_GROUPS = [
        ("准星", [
            (TAB_OVERVIEW, "准星面板"),
            (TAB_VEHICLE, "载具配置"),
            (TAB_HOTKEY, "热键设置"),
        ]),
        ("工具", [
            (TAB_DISTANCE_METER, "标定测距"),
            (TAB_MAGNIFIER, "放大镜"),
            (TAB_ANGLE_METER, "角度仪"),
            (TAB_SQUAD_MACRO, "建队宏"),
        ]),
        ("相关", [
            (TAB_ADAPT, "适配设置"),
            (TAB_RESOURCE, "资源库"),
            (TAB_INFO, "信息"),
        ]),
    ]

    def __init__(self, config: ConfigManager, state: StateMachine,
                 overlay: OverlayRenderer, hotkey: HotkeyManager,
                 resources: ResourceManager):
        super().__init__()
        self.config = config
        self.state = state
        self.overlay = overlay
        self.hotkey = hotkey
        self.resources = resources
        self._current_theme = self.config.get_theme()
        self._scrolling = False
        self._ui_initialized = False
        self._first_tab_initialized = False
        # 在 __init__ 就建好，保证 get_tab() 在任何阶段（含UI框架创建前）都可安全调用
        self._tab_cache = {}        # index -> 真实 tab widget（get_tab/属性访问器的唯一来源）
        self._tab_error_pages = {}  # index -> 创建失败降级页（绝不写进 _tab_cache）

        # P1: 窗口属性+极简背景色
        self.setWindowTitle("GUNNER SIGHT")
        self.resize(*self.WINDOW_SIZE)
        self.setMinimumSize(*self.WINDOW_SIZE)
        # 同步应用QSS：确保所有后续创建的控件都能拿到正确的字体/样式
        # （原方案用QTimer延迟应用，导致不同tab创建时QSS状态不一致）
        self._setup_full_style(self._current_theme)

    # ==================== 主题 ====================

    # 窗口尺寸：宽度必须等于启动横幅图的宽度（resources/assets/splash/full.png = 800px）。
    # 横幅居中弹出，窗口宽度一致时两者边缘正好对齐——横幅像贴在窗口上的"腰封"。
    # 启动尺寸 = 最小尺寸：启动后没有"手动缩小的余量"，也不会一开始就比横幅宽。
    WINDOW_SIZE = (800, 700)

    def _setup_full_style(self, theme="dark"):
        """完整QSS：应用级样式表。先设QPalette和app-level QSS，再清除per-widget stylesheet，避免中间出现空白背景。"""
        # 颜色全部来自 core/colors.py（唯一颜色来源），本文件不再写死任何颜色
        from core.colors import (ANGLE_CALIBRATING,
                                 ANGLE_IDLE, ANGLE_PAUSED, CAL_HINT, MASCOT_TEXT, NOTICE_BG,
                                 NOTICE_BORDER, NOTICE_TEXT, OVERLAY_TEXT,
                                 THEME_DARK, THEME_LIGHT)
        palette_colors = THEME_LIGHT if theme == "light" else THEME_DARK
        bg, ctrl, border = (palette_colors["bg"], palette_colors["ctrl"],
                            palette_colors["border"])
        btn, base = palette_colors["btn"], palette_colors["base"]
        hover, text, subtext, dis_text = (palette_colors["hover"], palette_colors["text"],
                                         palette_colors["subtext"], palette_colors["dis_text"])
        accent = self.config.get_accent(theme)
        on_accent = palette_colors["on_accent_text"]

        # 箭头图标路径（兼容源码/打包，深浅主题自动切换）
        from core.config.base import get_app_base_dir
        _icons_dir = (get_app_base_dir() / "resources" / "assets" / "icons").as_posix()
        _arrow_suffix = "light" if theme == "light" else "dark"
        arrow_up = f"{_icons_dir}/arrow_up_{_arrow_suffix}.png"
        arrow_down = f"{_icons_dir}/arrow_down_{_arrow_suffix}.png"

        # QPalette 接管基础配色：切换不触发 polish，几乎瞬间完成
        from PyQt5.QtGui import QColor, QPalette
        app = QApplication.instance()
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(bg))
        pal.setColor(QPalette.WindowText, QColor(text))
        pal.setColor(QPalette.Base, QColor(base))
        pal.setColor(QPalette.AlternateBase, QColor(base))
        pal.setColor(QPalette.Text, QColor(text))
        pal.setColor(QPalette.Button, QColor(btn))
        pal.setColor(QPalette.ButtonText, QColor(text))
        pal.setColor(QPalette.Highlight, QColor(accent))
        pal.setColor(QPalette.HighlightedText, QColor(on_accent))
        pal.setColor(QPalette.PlaceholderText, QColor(subtext))
        # Fusion 渐变由 Button/Light/Midlight/Mid/Dark/Shadow 色阶算出，全部拉平到 ctrl 即消除渐变
        for _role in (QPalette.Light, QPalette.Midlight, QPalette.Mid, QPalette.Dark, QPalette.Shadow):
            pal.setColor(_role, QColor(ctrl))
        pal.setColor(QPalette.Disabled, QPalette.Text, QColor(dis_text))
        pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(dis_text))
        app.setPalette(pal)

        # QSS 只保留 QPalette 做不到的：边框、圆角、间距、hover、高亮元素
        app.setStyleSheet(f"""
            QWidget {{ font-family: Norwester; font-size: 14px; }}
            QLineEdit {{
                border: 1px solid {border}; border-radius: 2px; padding: 4px 6px;
                background-color: {base}; color: {text};
            }}
            QComboBox, QSpinBox, QDoubleSpinBox {{
                background-color: {base}; border: 1px solid {border};
                border-radius: 2px; padding: 4px 8px; color: {text};
            }}
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {accent}; }}
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {accent}; }}
            QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
                background-color: {bg}; color: {dis_text}; border-color: {ctrl};
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox::down-arrow {{ image: url({arrow_down}); width: 10px; height: 6px; }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{ border: none; width: 16px; }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{ border: none; width: 16px; }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({arrow_up}); width: 8px; height: 5px; }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({arrow_down}); width: 8px; height: 5px; }}
            QAbstractItemView {{ border: none; background-color: {bg}; }}
            QLineEdit:hover, QLineEdit:focus {{ border-color: {accent}; }}
            QLineEdit:disabled {{ background-color: {bg}; color: {dis_text}; border-color: {ctrl}; }}
            QAbstractItemView::item {{ padding: 5px; }}
            QAbstractItemView::item:selected {{ background-color: {accent}; color: palette(highlighted-text); }}
            QAbstractItemView::item:selected:!active {{ background-color: {accent}; color: palette(highlighted-text); }}
            QAbstractItemView::item:hover:!selected {{ background-color: {hover}; }}
            QLabel[dual_hl="true"] {{ color: {on_accent}; }}
            QLabel#list_sub_label[dual_hl="true"] {{ color: {on_accent}; }}
            QPushButton {{ border: 1px solid {border}; border-radius: 2px; padding: 5px 12px; background-color: {btn}; }}
            QPushButton:hover {{ background-color: {hover}; border-color: {accent}; }}
            QPushButton:pressed {{ background-color: {accent}; color: {on_accent}; }}
            QPushButton:disabled {{ background-color: {bg}; }}
            QGroupBox {{ border: 1px solid {border}; border-radius: 2px; margin-top: 12px; padding: 8px 8px 4px 8px; background-color: {bg}; }}
            QGroupBox[flat="true"] {{ border: none; margin-top: 16px; padding: 3px 5px 3px 5px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {text}; font-size: 13px; font-weight: bold; }}
            QPushButton#cal_scheme_btn:checked {{ background-color: {accent}; color: {on_accent}; border: 1px solid {accent}; font-weight: bold; }}
            QCheckBox {{ spacing: 6px; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {border}; border-radius: 2px; }}
            QCheckBox::indicator:checked {{ background-color: {accent}; border-color: {accent}; }}
            QCheckBox:hover::indicator {{ border-color: {accent}; }}
            QCheckBox:disabled {{ color: {dis_text}; }}
            QCheckBox::indicator:disabled {{ border-color: {ctrl}; background-color: {bg}; }}
            QCheckBox::indicator:checked:disabled {{ background-color: {ctrl}; border-color: {ctrl}; }}
            QRadioButton {{ spacing: 6px; }}
            QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {border}; border-radius: 7px; }}
            QRadioButton::indicator:checked {{ background-color: {accent}; border-color: {accent}; }}
            QRadioButton:hover::indicator {{ border-color: {accent}; }}
            QRadioButton:disabled {{ color: {dis_text}; }}
            QRadioButton::indicator:disabled {{ border-color: {ctrl}; background-color: {bg}; }}
            QRadioButton::indicator:checked:disabled {{ background-color: {ctrl}; border-color: {ctrl}; }}
            QListView::indicator {{ width: 14px; height: 14px; border: 1px solid {border}; border-radius: 2px; }}
            QListView::indicator:checked {{ background-color: {accent}; border-color: {accent}; }}
            QSlider {{ background: transparent; border: none; }}
            QSlider::groove:horizontal {{ border: none; margin: 0; height: 6px; background: {border}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ border: none; width: 14px; height: 14px; margin: -4px 0; background: {accent}; border-radius: 7px; }}
            QSlider::sub-page:horizontal {{ border: none; background: {accent}; border-radius: 3px; }}
            QSlider::add-page:horizontal {{ background: transparent; }}
            QSlider:disabled {{ background: transparent; }}
            QSlider:disabled::groove:horizontal {{ background: {ctrl}; }}
            QSlider:disabled::handle:horizontal {{ background: {border}; }}
            QSlider:disabled::sub-page:horizontal {{ background: {border}; }}
            QSlider:disabled::add-page:horizontal {{ background: transparent; }}
            QScrollBar:vertical, QScrollBar:horizontal {{ background: {bg}; }}
            QScrollBar:vertical {{ width: 10px; }}
            QScrollBar:horizontal {{ height: 10px; }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {border}; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ min-height: 30px; }}
            QScrollBar::handle:horizontal {{ min-width: 30px; }}
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {hover}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
            QLabel {{ background-color: transparent; }}
            QScrollArea {{ background-color: {bg}; }}
            QScrollArea > QWidget > QWidget {{ background-color: {bg}; }}
            QListWidget#nav_list::item {{ padding: 8px 12px; }}
            QListWidget#nav_list::item:selected {{ background-color: {accent}; color: palette(highlighted-text); }}
            QListWidget#nav_list::item:selected:!active {{ background-color: {accent}; color: palette(highlighted-text); }}
            QListWidget#nav_list::item:hover:!selected:enabled {{ background-color: {ctrl}; }}
            QListWidget#nav_list::item:disabled {{ background-color: transparent; }}
            QListWidget#nav_list::item:disabled:hover {{ background-color: transparent; }}
            QListWidget#nav_list::item:disabled {{ color: {subtext}; font-weight: bold; padding: 6px 12px 2px; }}
            QLabel#nav_group_header {{ color: {subtext}; font-size: 11px; font-weight: bold; padding: 8px 12px 2px; }}
            QPushButton#nav_link_item {{ color: {accent}; border: none; background: transparent; padding: 6px 12px; text-align: left; }}
            QPushButton#nav_link_item:hover {{ background-color: {ctrl}; }}
            QFrame#angle_meter_sep {{ background-color: {border}; max-height: 1px; min-height: 1px; border: none; }}
            QLabel#info_title, QLabel#zoom_display {{ font-size: 48px; font-weight: bold; }}
            QLabel#zoom_display {{ padding: 8px; }}
            QLabel#zoom_display[dim="true"] {{ color: {dis_text}; }}
            QLabel#hint_text {{ font-size: 12px; color: {subtext}; }}
            QLabel#list_sub_label {{ color: {subtext}; font-size: 12px; }}
            QLabel#mascot_content {{ color: {MASCOT_TEXT}; }}
            QLabel#cal_hint {{ font-size: 12px; color: {CAL_HINT}; }}
            QLabel#angle_display {{ font-size: 36px; font-weight: bold; }}
            QLabel#angle_display[state="idle"] {{ color: {ANGLE_IDLE}; }}
            QLabel#angle_display[state="active"] {{ color: {OVERLAY_TEXT}; }}
            QLabel#angle_display[state="paused"] {{ color: {ANGLE_PAUSED}; }}
            QLabel#angle_display[state="calibrating"] {{ color: {ANGLE_CALIBRATING}; }}
            QPushButton#link_btn {{ color: {accent}; border: none; background: transparent; padding: 2px 0px; text-align: left; }}
            QPushButton#link_btn:hover {{ color: {accent}; }}
            QPushButton#primary_btn {{ background-color: {accent}; color: {on_accent}; border-color: {accent}; }}
            QPushButton#primary_btn:hover {{ background-color: {accent}; }}
            QPushButton#primary_btn:disabled {{ background-color: {border}; border-color: {border}; }}
            QPushButton#toggle_primary_btn:checked {{ background-color: {accent}; color: {on_accent}; border-color: {accent}; }}
            QPushButton#toggle_primary_btn:checked:hover {{ background-color: {accent}; }}
            QHeaderView::section {{ border: 1px solid {border}; padding: 4px 6px; }}
            QTableWidget {{ gridline-color: {border}; }}
            QTableWidget#fit_table::item {{ padding: 0px; }}
            QTableWidget#fit_table::item:selected {{ background-color: {accent}; color: {on_accent}; }}
            QTableWidget#fit_table::item:selected:!active {{ background-color: {accent}; color: {on_accent}; }}
            QTableWidget#fit_table QLineEdit {{ background-color: {accent}; color: {on_accent}; border: none; padding: 0; margin: 0; selection-background-color: {on_accent}; selection-color: {accent}; }}
            QExpandingLineEdit {{ background-color: {accent}; color: {on_accent}; border: none; padding: 0; margin: 0; selection-background-color: {on_accent}; selection-color: {accent}; }}
            QLabel#free_notice {{ font-size: 12px; color: {NOTICE_TEXT}; background-color: {NOTICE_BG}; border: 1px solid {NOTICE_BORDER}; border-radius: 4px; padding: 10px; }}
            /* #1 QMessageBox 跟随主题色 */
            QMessageBox {{ background-color: {bg}; }}
            QMessageBox QLabel {{ color: {text}; background-color: transparent; font-size: 14px; }}
            QMessageBox QPushButton {{ min-width: 60px; padding: 5px 16px; }}
            /* #7 全局去除 focus 虚线框 */
            QListWidget::item, QListView::item, QTreeWidget::item, QTableWidget::item {{ outline: none; }}
            QWidget:focus {{ outline: none; }}
        """)
        # 清除per-widget QSS（此时app-level样式已生效，不会出现空白背景）
        self.setStyleSheet("")
        # 主题SSOT传播：遍历所有顶级窗口强制repolish，确保弹出窗口/叠加窗口同步更新
        for w in QApplication.topLevelWidgets():
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()
    def _apply_theme(self, theme):
        self._current_theme = theme
        self.setUpdatesEnabled(False)
        self._setup_full_style(theme)
        self.setUpdatesEnabled(True)
        self.update()
        self.theme_btn.setText("浅色" if theme == "light" else "深色")
        # 强调色变化后重刷滚轮横幅/高亮背景（样式构造时固化，repolish 不重建；
        # overlay 文字色已固定白字，不再随主题走）
        wheel = getattr(self, "ammo_wheel", None)
        if wheel is not None:
            wheel.apply_accent()

    def _toggle_theme(self):
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self.config.set_theme(new_theme)
        self._apply_theme(new_theme)

    # ==================== UI 构建 ====================

    def _create_ui_frame(self):
        """P1: show后异步创建UI框架（顶栏+导航+tab_stack+翻页按钮+完整QSS+信号连接）"""
        if self._ui_initialized:
            return
        self._ui_initialized = True
        import time as _t_ui
        _t0 = _t_ui.perf_counter()
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 顶栏
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)
        self.state_label = QLabel("载具: 未选择 | 弹种: 未选中 | 倍率: 未选中")
        top_layout.addWidget(self.state_label)
        top_layout.addStretch()
        self.overlay_toggle_btn = QPushButton("隐藏准星")
        self.overlay_toggle_btn.setObjectName("toggle_primary_btn")
        self.overlay_toggle_btn.setCheckable(True)
        self.overlay_toggle_btn.setChecked(True)
        top_layout.addWidget(self.overlay_toggle_btn)
        self.theme_btn = QPushButton("浅色" if self._current_theme == "light" else "深色")
        self.theme_btn.setFixedHeight(24)
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

        # 链接区（底部，与导航列表视觉整合）
        link_area = QWidget()
        link_layout = QVBoxLayout(link_area)
        link_layout.setContentsMargins(0, 0, 0, 0)
        link_layout.setSpacing(0)
        link_header = QLabel("链接")
        link_header.setObjectName("nav_group_header")
        link_layout.addWidget(link_header)
        mortar_btn = QPushButton("猜点与迫炮")
        mortar_btn.setObjectName("nav_link_item")
        mortar_btn.setCursor(Qt.PointingHandCursor)
        mortar_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://squadcalc.app/?map=Jensen")))
        link_layout.addWidget(mortar_btn)
        armor_btn = QPushButton("装甲与图鉴\n需科学上网")
        armor_btn.setObjectName("nav_link_item")
        armor_btn.setCursor(Qt.PointingHandCursor)
        armor_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://squad-armor.com/vehicles")))
        link_layout.addWidget(armor_btn)
        nav_col_layout.addWidget(link_area)

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
        self.prev_page_btn.clicked.connect(self._go_prev_page)
        pn_layout.addWidget(self.prev_page_btn)
        pn_layout.addStretch()
        self.next_page_btn = QPushButton("▼")
        self.next_page_btn.setFixedSize(32, 32)
        self.next_page_btn.clicked.connect(self._go_next_page)
        pn_layout.addWidget(self.next_page_btn)
        content_layout.addWidget(page_nav_col)
        nav_layout.addWidget(content_with_nav, 1)
        main_layout.addWidget(nav_container)

        # 导航映射：row ↔ TAB常量（分组标题行映射为 None）
        self._row_to_tab = {}
        self._tab_to_row = {}
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        # Tab懒加载 - 工厂映射，首次访问时创建
        self._tab_factories = {
            self.TAB_OVERVIEW: lambda: OverviewTab(config=self.config, state=self.state, hotkey=self.hotkey, resources=self.resources, overlay=self.overlay),
            self.TAB_VEHICLE: lambda: VehicleConfigTab(config=self.config, state=self.state, resources=self.resources),
            self.TAB_HOTKEY: lambda: HotkeyTab(config=self.config, state=self.state, hotkey=self.hotkey),
            self.TAB_ANGLE_METER: lambda: AngleMeterTab(config=self.config, hotkey=self.hotkey),
            self.TAB_DISTANCE_METER: lambda: DistanceMeterTab(config=self.config, hotkey=self.hotkey),
            self.TAB_MAGNIFIER: lambda: MagnifierTab(config=self.config, hotkey=self.hotkey),
            self.TAB_SQUAD_MACRO: lambda: SquadMacroTab(config=self.config, hotkey=self.hotkey),
            self.TAB_RESOURCE: lambda: ResourceTab(config=self.config, resources=self.resources),
            self.TAB_ADAPT: lambda: AdaptTab(config=self.config, overlay=self.overlay),
            self.TAB_INFO: lambda: InfoTab(config=self.config, resources=self.resources),
        }

        # 按分组构建导航：分组标题(不可选) + tab项
        _row = 0
        for _group_name, _tabs in self._NAV_GROUPS:
            _header = QListWidgetItem(_group_name)
            _header.setFlags(Qt.NoItemFlags)  # 不可选不可点
            self.nav_list.addItem(_header)
            self._row_to_tab[_row] = None
            _row += 1
            for _tab_idx, _tab_name in _tabs:
                self.nav_list.addItem(_tab_name)
                self._row_to_tab[_row] = _tab_idx
                self._tab_to_row[_tab_idx] = _row
                _row += 1

        # 第一个tab延迟到window.show()后创建（_init_first_tab），避免阻塞启动
        self._first_tab_initialized = False

        # 滚轮防误触由 gui/wheel_filter.py 的全局 NoWheelFilter 统一负责（main.py 安装）。
        # 这里曾再装一个 self 作 application 级过滤器：既与 NoWheelFilter 重复
        # （同名异实现，且只覆盖三种控件、吞掉滚轮不转发导致页面滚不动），
        # 又因为没有反注册而在窗口销毁后给 QApplication 留下悬空指针。
        self._connect_signals()
        # QSS延迟到第一个tab创建后异步应用，避免阻塞UI框架创建
        logger.info(f"[性能] UI框架创建 耗时={(_t_ui.perf_counter()-_t0)*1000:.0f}ms")

    def _create_first_tab(self):
        """P1: 创建第一个tab并选中（UI框架创建后调用）。
        同时主动创建所有启用的进阶模块tab，避免懒加载导致热键不响应。"""
        if self._first_tab_initialized:
            return
        self._first_tab_initialized = True
        try:
            self._ensure_tab(self.TAB_OVERVIEW)
            self.get_tab(self.TAB_OVERVIEW).refresh()
        except Exception as e:
            # 准星面板是主页面：失败降级为错误页，程序其余部分仍可用
            self._make_error_page(self.TAB_OVERVIEW, e)
        self.nav_list.setCurrentRow(self._tab_to_row[self.TAB_OVERVIEW])
        # 主动创建所有启用的进阶模块tab（根源修复：不再懒加载，启动时即初始化引擎）
        # 只创建启用的模块，关闭的模块仍然懒加载，节省启动时间
        # 四个进阶模块统一在此预创建（热键回调只操作已存在的tab，不触发创建）
        if self.config.is_angle_meter_enabled():
            self._precreate_tab(self.TAB_ANGLE_METER)  # 角度仪
        if self.config.is_distance_meter_enabled():
            self._precreate_tab(self.TAB_DISTANCE_METER)  # 标定测距
        if self.config.is_magnifier_enabled():
            self._precreate_tab(self.TAB_MAGNIFIER)  # 放大镜
        if self.config.is_squad_macro_enabled():
            self._precreate_tab(self.TAB_SQUAD_MACRO)  # 建队宏
        # 根源修复：启动时强制刷新状态栏。
        # 状态栏初始文本是硬编码的"未选择"，但配置中可能已有载具。
        # set_vehicle中old_vehicle==vehicle_name时直接return不发信号，导致状态栏不更新。
        self._refresh_status_bar()
        # QSS已在__init__同步应用，这里只设置焦点策略
        self._disable_control_focus()

    def _ensure_tab(self, index):
        """懒加载创建tab，创建后连接该tab特有的信号。

        失败时记录完整堆栈并**抛出原异常**，绝不返回替身 widget。
        替身（QLabel）会让下游拿到它的调用方抛出与根因无关的第二个异常，
        真实根因被掩盖两次——历史案例见 crash_log.txt：放大镜构造失败被吞掉，
        最终只留下 "'QLabel' object has no attribute 'toggle'"。
        需要"失败也要能用"的调用方，走 _make_error_page 降级。
        """
        if index not in self._tab_cache:
            try:
                widget = self._tab_factories[index]()
            except Exception:
                logger.opt(exception=True).error(f"[MainWindow] tab 创建失败: index={index}")
                raise
            self._tab_cache[index] = widget
            self.tab_stack.insertWidget(index, widget)
            self._disable_control_focus(widget)
            self._connect_tab_signals(index, widget)
        return self._tab_cache[index]

    def get_tab(self, index):
        """查询**已创建**的 tab，无副作用。

        与 self.xxx_tab 属性访问器的区别：不触发懒加载创建，因此可在
        热键回调、关闭清理等"不该新建对象"的路径上安全使用。
        未创建（模块电闸关闭）时返回 None。
        """
        return self._tab_cache.get(index)

    def _make_error_page(self, index, exc):
        """创建失败降级页：缓存在 _tab_error_pages，不进 _tab_cache。

        _tab_cache 只装真实 tab，保证 get_tab() 与属性访问器的语义不被污染，
        也避免降级页被永久缓存后模块再也无法恢复。
        """
        page = self._tab_error_pages.get(index)
        if page is None:
            page = QLabel(f"页面加载失败：{exc}")
            page.setAlignment(Qt.AlignCenter)
            page.setWordWrap(True)
            self._tab_error_pages[index] = page
            self.tab_stack.insertWidget(index, page)
        return page

    def _precreate_tab(self, index):
        """启动时预创建（尽力而为）：单个模块初始化失败不拖垮整个启动。"""
        try:
            self._ensure_tab(index)
        except Exception as e:
            self._make_error_page(index, e)

    def _on_nav_changed(self, row):
        tab_idx = self._row_to_tab.get(row)
        if tab_idx is None:
            return  # 点击分组标题，不切换
        if tab_idx in self._tab_error_pages:
            widget = self._tab_error_pages[tab_idx]  # 已降级，不重复重试
        else:
            try:
                widget = self._ensure_tab(tab_idx)
            except Exception as e:
                widget = self._make_error_page(tab_idx, e)
        self.tab_stack.setCurrentWidget(widget)
        self._update_page_nav_buttons(row)


    def _go_prev_page(self):
        """跳转到上一导航页（跳过分组标题）"""
        row = self.nav_list.currentRow()
        for r in range(row - 1, -1, -1):
            if self._row_to_tab.get(r) is not None:
                self.nav_list.setCurrentRow(r)
                break

    def _go_next_page(self):
        """跳转到下一导航页（跳过分组标题）"""
        row = self.nav_list.currentRow()
        for r in range(row + 1, self.nav_list.count()):
            if self._row_to_tab.get(r) is not None:
                self.nav_list.setCurrentRow(r)
                break

    def _update_page_nav_buttons(self, row):
        """根据当前行显示/隐藏上下翻页按钮（跳过分组标题）"""
        has_prev = any(self._row_to_tab.get(r) is not None for r in range(row))
        has_next = any(self._row_to_tab.get(r) is not None for r in range(row + 1, self.nav_list.count()))
        self.prev_page_btn.setVisible(has_prev)
        self.next_page_btn.setVisible(has_next)

    def _disable_control_focus(self, widget=None):
        """设置控件焦点策略：按钮/复选框/下拉框/滑块不抢焦点，SpinBox可点击输入"""
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

        # 热键管理器全局信号（不依赖tab）
        self.hotkey.toggle_overlay_triggered.connect(self.state.toggle_overlay)
        self.hotkey.cycle_magnification_triggered.connect(self.state.cycle_magnification)
        self.hotkey.invert_colors_triggered.connect(self.overlay.toggle_invert_colors)
        self.hotkey.reset_magnification_triggered.connect(self.state.reset_magnification)
        self.hotkey.ammo_switch_triggered.connect(self.state.set_ammo_type)
        # 载具页选中载具时，刷新主页载具选择
        self.state.vehicle_changed.connect(self._on_state_vehicle_changed)

    def _connect_tab_signals(self, index, widget):
        """tab创建时连接该tab特有的信号"""
        if index == self.TAB_OVERVIEW:  # overview
            widget._connect_ui_signals(
                on_vehicle_changed=self._on_quick_vehicle_changed)
        elif index == self.TAB_VEHICLE:  # vehicle（内部信号在__init__自连接）
            overview_tab = self.get_tab(self.TAB_OVERVIEW)
            if overview_tab is not None:
                widget.data_changed.connect(overview_tab.refresh_vehicle_list)
            # 弹种增删改后自动重建当前载具弹种热键，无需重启
            widget.data_changed.connect(self.hotkey.reload_ammo_hotkeys)
            # 角度仪 tab 已创建时才连接，避免未启用模块被强制实例化
            angle_tab = self.get_tab(self.TAB_ANGLE_METER)
            if angle_tab is not None:
                widget.data_changed.connect(angle_tab.on_vehicle_data_changed)
            # 标签增删改后，各 tab 的 tag_filter 下拉刷新
            if overview_tab is not None:
                widget.tags_changed.connect(overview_tab.refresh_tag_filter)
            if angle_tab is not None:
                widget.tags_changed.connect(angle_tab.refresh_tag_filter)
            magnifier_tab = self.get_tab(self.TAB_MAGNIFIER)
            if magnifier_tab is not None:
                widget.tags_changed.connect(magnifier_tab.refresh_tag_filter)
            squad_macro_tab = self.get_tab(self.TAB_SQUAD_MACRO)
            if squad_macro_tab is not None:
                widget.tags_changed.connect(squad_macro_tab.refresh_tag_filter)
            # 状态机载具/弹种/倍率变化时，同步到载具页列表高亮
            self.state.vehicle_changed.connect(widget.on_external_vehicle_changed)
            self.state.ammo_type_changed.connect(widget.on_external_ammo_changed)
            self.state.magnification_changed.connect(widget.on_external_mag_changed)
        elif index == self.TAB_HOTKEY:  # hotkey
            widget._connect_ui_signals(on_global_hotkey_changed=self._on_global_hotkey_changed)
        elif index == self.TAB_ANGLE_METER:  # 角度仪
            # 补连载具页 data_changed（如果载具页已存在）
            vehicle_tab = self.get_tab(self.TAB_VEHICLE)
            if vehicle_tab is not None:
                vehicle_tab.data_changed.connect(widget.on_vehicle_data_changed)
                vehicle_tab.tags_changed.connect(widget.refresh_tag_filter)
        elif index == self.TAB_SQUAD_MACRO:  # 建队宏
            self.hotkey.squad_macro_triggered.connect(widget.on_hotkey)
            # 补连载具页 tags_changed（如果载具页已存在）
            vehicle_tab = self.get_tab(self.TAB_VEHICLE)
            if vehicle_tab is not None:
                vehicle_tab.tags_changed.connect(widget.refresh_tag_filter)
        elif index == self.TAB_MAGNIFIER:  # 放大镜
            # 补连载具页 tags_changed（如果载具页已存在）
            vehicle_tab = self.get_tab(self.TAB_VEHICLE)
            if vehicle_tab is not None:
                vehicle_tab.tags_changed.connect(widget.refresh_tag_filter)
        elif index == self.TAB_DISTANCE_METER:  # 标定测距
            # 同步当前暂离状态（如果开电闸时已在暂离中）
            wheel = getattr(self, 'ammo_wheel', None)
            if wheel is not None:
                widget.set_function_active(wheel.is_suspended)
                # 电闸开启后同步当前暂离状态
                def _on_distance_toggle(checked, w=widget, wh=wheel):
                    if checked:
                        w.set_function_active(wh.is_suspended)
                widget.enable_check.toggled.connect(_on_distance_toggle)
        elif index == self.TAB_RESOURCE:  # 资源库：切换到时刷新树
            widget.refresh()

    # ==================== 跨页回调 ====================

    def _on_magnification_changed(self, _index):
        self._refresh_status_bar()

    def _on_ammo_type_changed(self, _ammo_name):
        self._refresh_status_bar()
        # 信号回调只刷新已存在的页面，不触发懒加载创建（UI未建好时无需刷新，
        # 页面创建时的 refresh() 会读取当前状态补齐）
        tab = self.get_tab(self.TAB_OVERVIEW)
        # 概览页不可见时跳过刷新，showEvent 会补刷
        if tab is not None and tab.isVisible():
            tab.refresh_ammo()

    def _on_overlay_toggle(self, checked):
        self.state.set_overlay_visible(checked)

    def _on_state_vehicle_changed(self, name):
        """任何来源（主页/载具页/热键）的载具变化统一在此处理副作用。
        vehicle_changed 信号只在载具真正变化时发射，天然免疫初始化误触发。"""
        if not name:
            return
        # 同步 UI（只刷新已存在的页面，不触发懒加载创建）
        tab = self.get_tab(self.TAB_OVERVIEW)
        if tab is not None:
            tab.sync_vehicle_selection()
            tab.refresh_ammo()
        # 重建弹种热键：实际热键绑定总是更新；热键页UI仅在已创建时刷新（不强制实例化）
        hotkey_tab = self.get_tab(self.TAB_HOTKEY)
        if hotkey_tab is not None:
            hotkey_tab.refresh_ammo_hotkeys()
        self.hotkey.reload_ammo_hotkeys()

    def _on_quick_vehicle_changed(self, name):
        """主页载具列表选择载具：只更新状态机，副作用由 vehicle_changed 信号统一处理"""
        if name:
            self.state.set_vehicle(name)

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

    def focusOutEvent(self, event):
        """窗口失去焦点时自动保存配置（防抖500ms，复用config.request_save）。"""
        try:
            if self._ui_initialized:
                self.config.request_save()
        except Exception as e:
            logger.info(f"[MainWindow] focusOut 自动保存配置失败: {e}")
        super().focusOutEvent(event)

    def closeEvent(self, event):
        import time
        import traceback as _tb
        _t0 = time.perf_counter()
        try:
            # P1: UI未初始化时直接关闭
            if not self._ui_initialized:
                event.accept()
                return
            # 先立即隐藏所有窗口
            self.hide()
            try:
                if self.overlay:
                    self.overlay.hide()
            except Exception as e:
                logger.info(f"[关闭异常] 隐藏overlay: {e}")
            logger.info(f"[性能] 关闭-窗口隐藏 耗时={(time.perf_counter()-_t0)*1000:.0f}ms")

            # 只对已创建的tab执行shutdown
            _shutdown_map = {self.TAB_ANGLE_METER: "角度仪", self.TAB_DISTANCE_METER: "标定测距", self.TAB_SQUAD_MACRO: "建队宏"}
            _shutdown_fns = []
            for _idx, _name in _shutdown_map.items():
                _w = self.get_tab(_idx)
                if _w is not None:
                    _shutdown_fns.append((_name, lambda w=_w: w.shutdown()))
            # 放大镜：cleanup()停worker线程+释放mss GDI资源
            _mag = self.get_tab(self.TAB_MAGNIFIER)
            if _mag is not None:
                _shutdown_fns.append(("放大镜", lambda w=_mag: w.cleanup()))
            _shutdown_fns.extend([
                ("热键", lambda: self.hotkey.shutdown()),
                ("配置保存", lambda: self.config.save_config()),
            ])
            for _name, _fn in _shutdown_fns:
                _ts = time.perf_counter()
                try:
                    _fn()
                    logger.info(f"[性能] 关闭-{_name} 耗时={(time.perf_counter()-_ts)*1000:.0f}ms")
                except Exception as e:
                    logger.info(f"[关闭异常] {_name}: {e}")
                    _tb.print_exc()

            logger.info(f"[性能] 关闭总耗时={(time.perf_counter()-_t0)*1000:.0f}ms")
        except Exception as e:
            logger.info(f"[关闭异常] closeEvent顶层: {e}")
            _tb.print_exc()
        finally:
            try:
                self.tab_stack.deleteLater()
            except Exception:
                pass
            event.accept()
            QApplication.instance().quit()
