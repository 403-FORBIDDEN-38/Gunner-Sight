"""放大镜设置页
电闸(模块加载) / 开关(功能+窗口) / 暂离(只控可视) 三概念分离
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QGridLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout, QMenu, QWidget,
)
from core.config_manager import ConfigManager
from core.hotkey_manager import HotkeyManager
from core.magnifier import MagnifierOverlay
from core.cleanup import safe_call
from gui.hotkey_widgets import HotkeyPairWidget
from gui.widgets import (make_group_box, FilterListPanel, make_scroll_area,
                         make_settings_container)


class MagnifierTab(QWidget):
    def __init__(self, config: ConfigManager, hotkey: HotkeyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.hotkey = hotkey
        self.overlay = None
        # M12：preset 搜索防抖 timer（180ms）
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._apply_preset_search)

        self._build_ui()
        self._connect_ui()
        self.refresh()

        if self.config.is_magnifier_enabled():
            self._init_engine()

    # ---------- UI ----------

    def _build_ui(self):
        scroll, content, layout = make_scroll_area(spacing=8, horizontal_scroll_off=True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 3, 5, 3)
        outer.setSpacing(6)
        outer.addWidget(scroll)

        self.enable_check = QCheckBox("启用放大镜模块")
        layout.addWidget(self.enable_check)

        self.settings_container, sc_layout = make_settings_container()

        # --- 大示数 ---
        self.zoom_display = QLabel("1.00x")
        self.zoom_display.setAlignment(Qt.AlignCenter)
        self.zoom_display.setObjectName("zoom_display")  # 样式在全局 QSS，随主题
        sc_layout.addWidget(self.zoom_display)

        # --- 基本参数 ---
        param_group, p = make_group_box("基本参数", layout_cls=QGridLayout, flat=True)
        p.setSpacing(8)

        # 行0：外框半径(左) | 截屏帧率(中) | X偏移(右)
        p.addWidget(QLabel("外框半径:"), 0, 0)
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(10, 2000)
        self.radius_spin.setSuffix(" px")
        p.addWidget(self.radius_spin, 0, 1)

        p.addWidget(QLabel("截屏帧率:"), 0, 2)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(15, 144)
        self.fps_spin.setSuffix(" fps")
        p.addWidget(self.fps_spin, 0, 3)

        p.addWidget(QLabel("X偏移:"), 0, 4)
        self.ox_spin = QSpinBox()
        self.ox_spin.setRange(-2000, 2000)
        self.ox_spin.setSuffix(" px")
        p.addWidget(self.ox_spin, 0, 5)

        # 行1：屏息半径步长(左) | 屏息倍率步长(中) | Y偏移(右)
        p.addWidget(QLabel("屏息半径步长:"), 1, 0)
        self.breath_step_spin = QSpinBox()
        self.breath_step_spin.setRange(1, 500)
        self.breath_step_spin.setSuffix(" px")
        p.addWidget(self.breath_step_spin, 1, 1)

        p.addWidget(QLabel("屏息倍率步长:"), 1, 2)
        self.breath_zoom_spin = QDoubleSpinBox()
        self.breath_zoom_spin.setRange(0.0, 10.0)
        self.breath_zoom_spin.setSingleStep(0.5)
        self.breath_zoom_spin.setSuffix("x")
        p.addWidget(self.breath_zoom_spin, 1, 3)

        p.addWidget(QLabel("Y偏移:"), 1, 4)
        self.oy_spin = QSpinBox()
        self.oy_spin.setRange(-2000, 2000)
        self.oy_spin.setSuffix(" px")
        p.addWidget(self.oy_spin, 1, 5)

        sc_layout.addWidget(param_group)

        # --- 热键设置 ---
        hk_group, h = make_group_box("热键设置")
        h.setSpacing(6)
        self.hk_toggle = HotkeyPairWidget("开关")
        self.hk_zoom_in = HotkeyPairWidget("放大")
        self.hk_zoom_out = HotkeyPairWidget("缩小")
        self.hk_breath = HotkeyPairWidget("屏息缩放")
        for w in (self.hk_toggle, self.hk_zoom_in, self.hk_zoom_out, self.hk_breath):
            h.addWidget(w)
        sc_layout.addWidget(hk_group)

        # --- 枪械列表（预设） ---
        preset_group, g = make_group_box("枪械列表", flat=True)
        g.setSpacing(6)

        # 右：标签复选框
        self.tag_list = QListWidget()
        self.tag_list.setSelectionMode(QListWidget.NoSelection)
        self.preset_panel = FilterListPanel(placeholder="搜索配置...",
                                            right_widget=self.tag_list,
                                            list_stretch=4, right_stretch=1)
        self.preset_list = self.preset_panel.list
        self.preset_search = self.preset_panel.search
        self.preset_tag_filter = self.preset_panel.tag_filter
        g.addWidget(self.preset_panel, 1)
        sc_layout.addWidget(preset_group, 1)

        layout.addWidget(self.settings_container, 1)

    # ---------- signals ----------

    def _connect_ui(self):
        self.enable_check.toggled.connect(self._on_enable)
        self.fps_spin.valueChanged.connect(self._on_fps)
        self.radius_spin.valueChanged.connect(self._on_radius)
        self.breath_step_spin.valueChanged.connect(self._on_breath_step)
        self.breath_zoom_spin.valueChanged.connect(lambda v: self.config.set_magnifier_breath_zoom(v))
        self.ox_spin.valueChanged.connect(self._on_ox)
        self.oy_spin.valueChanged.connect(self._on_oy)

        self.hk_toggle.hotkey_changed.connect(lambda d: self._on_hk("toggle", d))
        self.hk_zoom_in.hotkey_changed.connect(lambda d: self._on_hk("zoom_in", d))
        self.hk_zoom_out.hotkey_changed.connect(lambda d: self._on_hk("zoom_out", d))
        self.hk_breath.hotkey_changed.connect(lambda d: self._on_hk("breath_hold", d))

        self.preset_list.currentItemChanged.connect(self._on_preset_select)
        self.preset_list.customContextMenuRequested.connect(self._on_preset_menu)
        self.preset_panel.add_requested.connect(self._on_add_preset)
        self.preset_panel.rename_requested.connect(self._on_rename_preset)
        self.preset_panel.delete_requested.connect(self._on_delete_preset)
        self.preset_search.textChanged.connect(self._on_preset_search)
        self.preset_tag_filter.currentIndexChanged.connect(self._refresh_preset_list)
        self.tag_list.itemChanged.connect(self._on_tag_toggled)

    # ---------- refresh ----------

    def refresh(self):
        self.enable_check.blockSignals(True)
        self.enable_check.setChecked(self.config.is_magnifier_enabled())
        self.enable_check.blockSignals(False)

        self.zoom_display.setText(f"{self.config.get_magnifier_zoom():.2f}x")

        self.radius_spin.blockSignals(True)
        self.radius_spin.setValue(self.config.get_magnifier_radius())
        self.radius_spin.blockSignals(False)
        self.fps_spin.blockSignals(True)
        self.fps_spin.setValue(self.config.get_magnifier_fps())
        self.fps_spin.blockSignals(False)

        self.breath_step_spin.blockSignals(True)
        self.breath_step_spin.setValue(self.config.get_magnifier_breath_step())
        self.breath_step_spin.blockSignals(False)
        self.breath_zoom_spin.blockSignals(True)
        self.breath_zoom_spin.setValue(self.config.get_magnifier_breath_zoom())
        self.breath_zoom_spin.blockSignals(False)

        hks = self.config.get_magnifier_hotkeys()
        self.hk_toggle.set_hotkey(hks.get("toggle", {}))
        self.hk_zoom_in.set_hotkey(hks.get("zoom_in", {}))
        self.hk_zoom_out.set_hotkey(hks.get("zoom_out", {}))
        self.hk_breath.set_hotkey(hks.get("breath_hold", {}))

        self._refresh_tag_list()
        self._refresh_preset_list()
        # _refresh_preset_list 里的 setCurrentRow 会触发 _on_preset_select 刷详情，无需手动再调
        self.settings_container.setEnabled(self.config.is_magnifier_enabled())
        # 之前只在"禁用"时改样式，重新启用后样式不回滚——这里两个方向都设置
        self._set_zoom_dim(not self.config.is_magnifier_enabled())

    # ---------- tag list ----------

    def _refresh_tag_list(self):
        all_tags = self.config.get_all_tags()
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for t in all_tags:
            item = QListWidgetItem(t)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.tag_list.addItem(item)
        self.tag_list.blockSignals(False)

    def _on_tag_toggled(self, item):
        preset_item = self.preset_list.currentItem()
        if not preset_item:
            return
        name = preset_item.data(Qt.UserRole)
        data = self.config.get_magnifier_preset(name)
        tags = set(data.get("tags", []))
        tag = item.text()
        if item.checkState() == Qt.Checked:
            tags.add(tag)
        else:
            tags.discard(tag)
        data["tags"] = sorted(tags)
        self.config.set_magnifier_preset(name, data)
        self._refresh_preset_list()

    # ---------- preset list ----------

    def refresh_tag_filter(self):
        """标签增删改后，重填 tag_filter 下拉"""
        # 标签筛选下拉：数据源是本页预设实际用到的标签
        all_tags = set()
        for data in self.config.get_magnifier_presets().values():
            all_tags.update(data.get("tags", []))
        self.preset_panel.set_tag_options(sorted(all_tags))

    def _on_preset_search(self, _text):
        """M12：只重启防抖 timer，停止输入 180ms 后才真正过滤。"""
        self._search_timer.start()

    def _apply_preset_search(self):
        self._refresh_preset_list()

    def _refresh_preset_list(self):
        current = self.config.get_current_magnifier_preset()

        # 标签筛选下拉：数据源是本页预设实际用到的标签
        all_tags = set()
        for data in self.config.get_magnifier_presets().values():
            all_tags.update(data.get("tags", []))
        self.preset_panel.set_tag_options(sorted(all_tags))

        search, tag_filter = self.preset_panel.filter_values()

        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        current_row = -1
        for name in sorted(self.config.get_magnifier_presets().keys()):
            data = self.config.get_magnifier_preset(name)
            tags = data.get("tags", [])
            if search and search not in name.lower():
                continue
            if tag_filter and tag_filter not in tags:
                continue
            sub = f"半径:{data.get('radius', 200)} 步长:{data.get('step', 20)}"
            if tags:
                sub += f" 标签:{','.join(tags)}"
            self.preset_list.add_item(name, sub, user_data=name)
            if name == current:
                # 恢复选中必须用"实际插入的行号"——用源列表下标会在搜索/筛选时选错行
                current_row = self.preset_list.count() - 1
        self.preset_list.blockSignals(False)
        if self.preset_list.count() > 0:
            # current 在结果里 → 恢复它（_on_preset_select 幂等短路不写 config）
            # current 不在结果里 → 选第 0 行（触发 _on_preset_select 写 current）
            self.preset_list.setCurrentRow(current_row if current_row >= 0 else 0)
        # 列表空 → 不调 setCurrentRow，current_preset 保持不动

    def _on_preset_select(self, current, previous):
        if not current:
            return
        name = current.data(Qt.UserRole)
        data = self.config.get_magnifier_preset(name)
        self.radius_spin.blockSignals(True)
        self.radius_spin.setValue(data.get("radius", 200))
        self.radius_spin.blockSignals(False)
        self.breath_step_spin.blockSignals(True)
        self.breath_step_spin.setValue(data.get("step", 20))
        self.breath_step_spin.blockSignals(False)
        self.ox_spin.blockSignals(True)
        self.ox_spin.setValue(data.get("ox", 0))
        self.ox_spin.blockSignals(False)
        self.oy_spin.blockSignals(True)
        self.oy_spin.setValue(data.get("oy", 0))
        self.oy_spin.blockSignals(False)
        if self.overlay:
            self.overlay.set_offset(data.get("ox", 0), data.get("oy", 0))
            self.overlay.set_radius(data.get("radius", 200))
        # update tag checkboxes
        preset_tags = set(data.get("tags", []))
        self.tag_list.blockSignals(True)
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            item.setCheckState(Qt.Checked if item.text() in preset_tags else Qt.Unchecked)
        self.tag_list.blockSignals(False)
        # 写 current_preset，值没变就不写（幂等短路，避免高频 refresh 触发 request_save）
        if self.config.get_current_magnifier_preset() != name:
            self.config.set_current_magnifier_preset(name)

    def _on_preset_menu(self, pos):
        item = self.preset_list.itemAt(pos)
        if not item:
            return
        self.preset_list.setCurrentItem(item)
        m = QMenu(self)
        a_rename = m.addAction("重命名")
        a_del = m.addAction("删除")
        chosen = m.exec_(self.preset_list.viewport().mapToGlobal(pos))
        if chosen == a_rename:
            self._on_rename_preset()
        elif chosen == a_del:
            self._on_delete_preset()

    def _on_add_preset(self):
        name, ok = QInputDialog.getText(self, "新建", "配置名:")
        if ok and name.strip():
            self.config.add_magnifier_preset(name.strip())
            self._refresh_preset_list()

    def _on_rename_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return
        old = item.data(Qt.UserRole)
        new, ok = QInputDialog.getText(self, "重命名", "新名:", text=old)
        if ok and new.strip() and new.strip() != old:
            self.config.rename_magnifier_preset(old, new.strip())
            self._refresh_preset_list()

    def _on_delete_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        self.config.delete_magnifier_preset(name)
        self._refresh_preset_list()

    # ---------- enable / engine ----------

    def _on_enable(self, checked: bool):
        self.config.set_magnifier_enabled(checked)
        if checked:
            self._init_engine()
            self._set_zoom_dim(False)
        else:
            self._destroy_engine()
            self._set_zoom_dim(True)
        self.settings_container.setEnabled(checked)
        self.hotkey.reload_hotkeys()

    def _set_zoom_dim(self, dim: bool):
        """大示数的"禁用变暗"态：改属性后必须 repolish，QSS 才会重新求值。"""
        self.zoom_display.setProperty("dim", dim)
        self.zoom_display.style().unpolish(self.zoom_display)
        self.zoom_display.style().polish(self.zoom_display)

    def _init_engine(self):
        if self.overlay:
            return
        self.overlay = MagnifierOverlay()
        self.overlay.set_zoom(self.config.get_magnifier_zoom())
        self.overlay.set_radius(self.config.get_magnifier_radius())
        self.overlay.set_fps(self.config.get_magnifier_fps())
        item = self.preset_list.currentItem()
        if item:
            name = item.data(Qt.UserRole)
            data = self.config.get_magnifier_preset(name)
            self.overlay.set_offset(data.get("ox", 0), data.get("oy", 0))
        self.overlay.set_active(True)

    def _destroy_engine(self):
        if self.overlay:
            safe_call("overlay.set_active", lambda: self.overlay.set_active(False))
            safe_call("overlay.hide", self.overlay.hide)
            # 同步销毁worker（不用deleteLater，退出时事件循环可能已停）
            safe_call("overlay.close", self.overlay.close)
            self.overlay = None

    # ---------- param callbacks ----------

    def _on_zoom(self, val):
        self.config.set_magnifier_zoom(val)
        self.zoom_display.setText(f"{val:.2f}x")
        if self.overlay:
            self.overlay.set_zoom(val)

    def _on_radius(self, val):
        self.config.set_magnifier_radius(int(val))
        if self.overlay:
            self.overlay.set_radius(int(val))
        # save to current preset
        item = self.preset_list.currentItem()
        if item:
            name = item.data(Qt.UserRole)
            data = self.config.get_magnifier_preset(name)
            data["radius"] = int(val)
            self.config.set_magnifier_preset(name, data)
            self._refresh_preset_list()

    def _on_fps(self, val):
        self.config.set_magnifier_fps(val)
        if self.overlay:
            self.overlay.set_fps(val)

    def _on_breath_step(self, val):
        self.config.set_magnifier_breath_step(int(val))
        item = self.preset_list.currentItem()
        if item:
            name = item.data(Qt.UserRole)
            data = self.config.get_magnifier_preset(name)
            data["step"] = int(val)
            self.config.set_magnifier_preset(name, data)
            self._refresh_preset_list()

    def _on_ox(self, val):
        item = self.preset_list.currentItem()
        if item:
            name = item.data(Qt.UserRole)
            data = self.config.get_magnifier_preset(name)
            data["ox"] = int(val)
            self.config.set_magnifier_preset(name, data)
            if self.overlay:
                self.overlay.set_offset(int(val), data.get("oy", 0))

    def _on_oy(self, val):
        item = self.preset_list.currentItem()
        if item:
            name = item.data(Qt.UserRole)
            data = self.config.get_magnifier_preset(name)
            data["oy"] = int(val)
            self.config.set_magnifier_preset(name, data)
            if self.overlay:
                self.overlay.set_offset(data.get("ox", 0), int(val))

    def _on_hk(self, action, hk):
        self.config.set_magnifier_hotkey(action, hk["key1"], hk.get("trigger1", "toggle"), 1)
        self.config.set_magnifier_hotkey(action, hk["key2"], hk.get("trigger2", "toggle"), 2)
        self.hotkey.reload_hotkeys()

    # ---------- hotkey actions ----------

    def toggle(self):
        if self.overlay:
            self.overlay.set_active(not self.overlay.is_active())

    def zoom_in(self):
        if self.overlay:
            z = self.config.get_magnifier_zoom() + 0.5
            self.config.set_magnifier_zoom(z)
            self.zoom_display.setText(f"{z:.2f}x")
            self.overlay.set_zoom(z)

    def zoom_out(self):
        if self.overlay:
            z = max(1.0, self.config.get_magnifier_zoom() - 0.5)
            self.config.set_magnifier_zoom(z)
            self.zoom_display.setText(f"{z:.2f}x")
            self.overlay.set_zoom(z)

    def breath_hold(self):
        if self.overlay:
            self.overlay.toggle_breath_hold(
                self.config.get_magnifier_breath_step(),
                self.config.get_magnifier_breath_zoom())
            self.zoom_display.setText(f"{self.overlay.zoom():.2f}x")

    # ---------- suspend / cleanup ----------

    def set_suspended(self, suspended: bool):
        if self.overlay:
            self.overlay.set_suspended(suspended)

    def cleanup(self):
        self._destroy_engine()
