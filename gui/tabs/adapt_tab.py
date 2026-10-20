"""适配 tab：屏幕选择 + 分辨率适配（准星参数已移回准星面板）+ 主题色设置"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from gui.widgets import make_group_box


class AdaptTab(QWidget):
    def __init__(self, config, overlay):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.config = config
        self.overlay = overlay
        self._building = True
        self._build_ui()
        self._connect_ui_signals()
        self.refresh()
        self._building = False

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # 1. 屏幕
        sg, sl = make_group_box("屏幕", layout_cls=QHBoxLayout, flat=True)

        sl.addWidget(QLabel("显示器:"))
        self.screen_combo = QComboBox()
        self.screen_combo.setMinimumWidth(280)
        sl.addWidget(self.screen_combo)
        self.detect_btn = QPushButton("识别当前屏")
        sl.addWidget(self.detect_btn)
        sl.addStretch()
        outer.addWidget(sg)

        # 2. 屏幕缩放
        cg, cl = make_group_box("屏幕缩放（sx/sy 机械系数）")
        mr = QHBoxLayout()
        mr.addWidget(QLabel("模式:"))
        self.mode_preset = QRadioButton("预设")
        self.mode_custom = QRadioButton("自定义")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_preset)
        self.mode_group.addButton(self.mode_custom)
        mr.addWidget(self.mode_preset)
        mr.addWidget(self.mode_custom)
        mr.addStretch()
        cl.addLayout(mr)


        self.preset_widget = QWidget()
        pl = QHBoxLayout(self.preset_widget)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(QLabel("档位:"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(["1K", "2K", "4K"])
        pl.addWidget(self.res_combo)
        pl.addWidget(QLabel("宽高比:"))
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["16:9", "16:10", "4:3"])
        pl.addWidget(self.aspect_combo)
        self.factor_label = QLabel("")
        pl.addWidget(self.factor_label)
        pl.addStretch()
        cl.addWidget(self.preset_widget)

        # 适配逻辑：预设/自定义模式下均可用，独立于数值输入
        self.logic_widget = QWidget()
        ll = QHBoxLayout(self.logic_widget)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("适配逻辑:"))
        self.sx_logic = QComboBox()
        self.sx_logic.addItems(["增加", "拉伸"])
        self.sx_logic.setMinimumWidth(60)
        self.sy_logic = QComboBox()
        self.sy_logic.addItems(["增加", "拉伸"])
        self.sy_logic.setMinimumWidth(60)
        ll.addWidget(QLabel("横向"))
        ll.addWidget(self.sx_logic)
        ll.addSpacing(16)
        ll.addWidget(QLabel("竖向"))
        ll.addWidget(self.sy_logic)
        ll.addStretch()
        cl.addWidget(self.logic_widget)

        self.custom_widget = QWidget()
        cul = QFormLayout(self.custom_widget)
        cul.setContentsMargins(0, 0, 0, 0)
        self.sx_spin = QDoubleSpinBox()
        self.sx_spin.setRange(0.05, 3.0); self.sx_spin.setDecimals(3); self.sx_spin.setSingleStep(0.01)
        self.sy_spin = QDoubleSpinBox()
        self.sy_spin.setRange(0.05, 3.0); self.sy_spin.setDecimals(3); self.sy_spin.setSingleStep(0.01)
        cul.addRow("横向缩放 sx:", self.sx_spin)
        cul.addRow("竖向缩放 sy:", self.sy_spin)
        cl.addWidget(self.custom_widget)
        outer.addWidget(cg)

        # 3. 主题色设置：深/浅主题的 ACCENT 分别可配
        tg, tl = make_group_box("主题色设置", flat=True)
        for which, label_text in (("dark", "深色主题:"), ("light", "浅色主题:")):
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            btn = QPushButton()
            btn.setFixedSize(64, 22)
            btn.setToolTip("点击修改该主题下的强调色")
            btn.clicked.connect(lambda _checked=False, w=which: self._pick_accent(w))
            row.addWidget(btn)
            row.addStretch()
            tl.addLayout(row)
            if which == "dark":
                self.dark_accent_btn = btn
            else:
                self.light_accent_btn = btn
        outer.addWidget(tg)

        outer.addStretch()

        note = QLabel("说明：横向sx/竖向sy可各自独立选择适配逻辑。增加=游戏拓宽视野画面不拉伸，该轴等比缩放(圆不变形)；拉伸=游戏画面拉伸，该轴按比例缩放(圆可变椭圆)。\n等比基准=min(sx,sy)；偏移量总是按各自轴比例换算；预设自动计算，自定义手调。")
        note.setObjectName("hint_text")
        outer.addWidget(note)

    def _connect_ui_signals(self):
        self.screen_combo.currentIndexChanged.connect(self._on_screen_changed)
        self.detect_btn.clicked.connect(self._on_detect_screen)
        self.mode_preset.toggled.connect(self._on_mode_changed)
        self.res_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.aspect_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.sx_spin.valueChanged.connect(self._on_custom_sxsy)
        self.sy_spin.valueChanged.connect(self._on_custom_sxsy)
        self.sx_logic.currentIndexChanged.connect(self._on_sx_logic_changed)
        self.sy_logic.currentIndexChanged.connect(self._on_sy_logic_changed)


    # ===== 屏幕 =====
    def _populate_screens(self):
        self.screen_combo.blockSignals(True)
        self.screen_combo.clear()
        selected = self.config.get_selected_screen()
        idx = 0
        for i, scr in enumerate(QApplication.screens()):
            geo = scr.geometry()
            name = scr.name() or f"显示器{i+1}"
            self.screen_combo.addItem(f"{name} ({geo.width()}×{geo.height()})", name)
            if selected and name == selected:
                idx = i
        self.screen_combo.setCurrentIndex(idx)
        self.screen_combo.blockSignals(False)

    def _find_screen(self, name):
        for scr in QApplication.screens():
            if (scr.name() or "") == name:
                return scr
        return None

    def _auto_tier_for_screen(self, name):
        scr = self._find_screen(name)
        if not scr:
            return
        h = scr.geometry().height()
        tier = "1K" if h <= 1200 else ("2K" if h <= 1700 else "4K")
        self.res_combo.blockSignals(True)
        self.res_combo.setCurrentText(tier)
        self.res_combo.blockSignals(False)
        self._apply_preset()

    def _on_screen_changed(self, _idx):
        if self._building:
            return
        name = self.screen_combo.currentData()
        if not name:
            return
        self.config.set_selected_screen(name)
        self.overlay.set_selected_screen(name)
        self._auto_tier_for_screen(name)

    def _on_detect_screen(self):
        scr = QApplication.primaryScreen()
        if not scr:
            return
        name = scr.name() or "显示器1"
        for i in range(self.screen_combo.count()):
            if self.screen_combo.itemData(i) == name:
                self.screen_combo.setCurrentIndex(i)
                break
        self._auto_tier_for_screen(name)

    # ===== 模式 =====
    def _on_mode_changed(self):
        if self._building:
            return
        custom = self.mode_custom.isChecked()
        self.preset_widget.setEnabled(not custom)
        self.custom_widget.setEnabled(custom)
        self.config.set_adapt_mode("custom" if custom else "preset")
        self.overlay.refresh_adapt()
        self._refresh_factor()

    def _apply_preset(self):
        tier = self.res_combo.currentText()
        h = {"1K": 1080, "2K": 1440, "4K": 2160}[tier]
        asp = self.aspect_combo.currentText()
        ratio = 4/3 if asp.startswith("4:3") else (16/10 if asp.startswith("16:10") else 16/9)
        self.config.set_display_resolution(int(round(h * ratio)), h)
        self.overlay.refresh_adapt()
        self._refresh_factor()

    def _on_preset_changed(self):
        if self._building:
            return
        self._apply_preset()

    def _on_sx_logic_changed(self, _idx):
        if self._building:
            return
        stretch = (self.sx_logic.currentIndex() == 1)
        self.config.set_sx_adapt_mode("stretch" if stretch else "expand")
        self.overlay.refresh_adapt()

    def _on_sy_logic_changed(self, _idx):
        if self._building:
            return
        stretch = (self.sy_logic.currentIndex() == 1)
        self.config.set_sy_adapt_mode("stretch" if stretch else "expand")
        self.overlay.refresh_adapt()

    def _on_custom_sxsy(self):
        if self._building or not self.mode_custom.isChecked():
            return
        self.config.set_sx_override(self.sx_spin.value())
        self.config.set_sy_override(self.sy_spin.value())
        self.overlay.refresh_adapt()
        self._refresh_factor()

    def _refresh_factor(self):
        sx, sy = self.overlay.get_adapt_factors() if self.overlay else (1.0, 1.0)
        self.factor_label.setText("sx=%.3f sy=%.3f" % (sx, sy))

    # ===== 主题色 =====
    def _refresh_accent_buttons(self):
        self.dark_accent_btn.setStyleSheet(
            f"background-color: {self.config.get_accent_dark()}; border: 1px solid #555;")
        self.light_accent_btn.setStyleSheet(
            f"background-color: {self.config.get_accent_light()}; border: 1px solid #555;")

    def _pick_accent(self, which):
        current = self.config.get_accent_dark() if which == "dark" else self.config.get_accent_light()
        color = QColorDialog.getColor(QColor(current), self, "选择主题色")
        if not color.isValid():
            return
        if which == "dark":
            self.config.set_accent_dark(color.name())
        else:
            self.config.set_accent_light(color.name())
        self._refresh_accent_buttons()
        # 改的是当前主题 → 立即重应用整套样式（QSS + 滚轮 overlay 强调色）
        window = self.window()
        cur_theme = getattr(window, "_current_theme", None)
        if cur_theme == ("dark" if which == "dark" else "light"):
            window._apply_theme(cur_theme)

    # ===== 刷新 =====
    def refresh(self):
        self._building = True
        self._populate_screens()
        mode = self.config.get_adapt_mode()
        self.mode_preset.setChecked(mode != "custom")
        self.mode_custom.setChecked(mode == "custom")
        self.preset_widget.setEnabled(mode != "custom")
        self.custom_widget.setEnabled(mode == "custom")
        disp = self.config.get_display_resolution()
        h2t = {1080: "1K", 1440: "2K", 2160: "4K"}
        self.res_combo.setCurrentText(h2t.get(disp[1], "1K"))
        ar = disp[0] / disp[1] if disp[1] else 16 / 9
        self.aspect_combo.setCurrentText("4:3" if abs(ar - 4/3) < 0.02 else ("16:10" if abs(ar - 16/10) < 0.02 else "16:9"))
        sx_stretch = (self.config.get_sx_adapt_mode() == "stretch")
        self.sx_logic.setCurrentIndex(1 if sx_stretch else 0)
        sy_stretch = (self.config.get_sy_adapt_mode() == "stretch")
        self.sy_logic.setCurrentIndex(1 if sy_stretch else 0)
        # 自定义模式下加载配置中的sx/sy覆盖值到输入框
        self.sx_spin.setValue(self.config.get_sx_override())
        self.sy_spin.setValue(self.config.get_sy_override())
        self._refresh_factor()
        self._refresh_accent_buttons()
        self._building = False
