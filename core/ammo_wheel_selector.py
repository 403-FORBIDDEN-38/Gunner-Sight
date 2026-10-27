"""
滚轮切换弹种模块

三个独立悬浮窗口 + 三态暂离状态机：
- CompactOverlay：常显当前弹种
- FullOverlay：预选弹种列表
- MagOverlay：倍率挂件（当前倍率+下一倍率，位于弹种栏下方）

暂离转换规则：
- 按不是当前退出权的键 → 转交退出权（不退出）
- 按是当前退出权的键 → 退出暂离
- 暂离时：热键切弹种可用，滚轮不可用
"""
from PyQt5.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from core.win32_utils import set_click_through
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.mouse_hook import MouseHook
from core.colors import OVERLAY_BOX_BG, OVERLAY_BOX_BORDER, OVERLAY_TEXT
from core.overlay_base import make_wheel_overlay_window

# 叠加层样式串（原文件里多处重复，集中一处）
_BOX_STYLE = f"QWidget#box {{ background-color: {OVERLAY_BOX_BG}; border: 1px solid {OVERLAY_BOX_BORDER}; }}"
# 文字统一白字 OVERLAY_TEXT；仅横幅/高亮背景用用户配置的强调色 accent（见各 Overlay.apply_accent）


def _label_idle_style() -> str:
    return f"color: {OVERLAY_TEXT}; padding: 4px 24px 4px 12px;"


def _label_active_style(accent: str, on_accent_text: str) -> str:
    return f"color: {on_accent_text}; background-color: {accent}; padding: 4px 24px 4px 12px;"


PREVIEW_TIMEOUT_MS = 2000
MAG_GAP_PX = 4  # 倍率挂件与弹种栏的间距

NORMAL = 0
SUSPENDED_KEY1 = 1
SUSPENDED_KEY2 = 2


def _screen_geom():
    return QApplication.primaryScreen().geometry()


def _position_right(w, ox=0, oy=0):
    """以屏幕中心为基准（ox/oy 为偏移量，0,0 即居中）"""
    screen = _screen_geom()
    w.adjustSize()
    if hasattr(w, '_fixed_h'):
        w.setFixedHeight(w._fixed_h)
    x = screen.center().x() - w.width() // 2 + ox
    y = screen.center().y() - w.height() // 2 + oy
    w.move(x, y)


class MagOverlay(QWidget):
    """倍率挂件：只显示当前倍率（白字），纯文字无框。"""

    def __init__(self):
        super().__init__()
        make_wheel_overlay_window(self)
        self._font = QFont("Norwester", 10)
        self._current_label = QLabel()
        self._current_label.setFont(self._font)
        self._current_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._current_label.setStyleSheet(f"color: {OVERLAY_TEXT}; padding: 2px 24px 2px 12px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._current_label)

    def showEvent(self, e):
        super().showEvent(e)
        set_click_through(int(self.winId()), True)

    def set_magnification(self, current_label):
        self._current_label.setText(current_label)

    def show_at(self, x, y):
        self.adjustSize()
        self.move(x, y)
        self.show()
        self.raise_()


class CompactOverlay(QWidget):
    def __init__(self):
        super().__init__()
        make_wheel_overlay_window(self)
        self._suspended = False
        self._ammo_label = QLabel()
        self._ammo_label.setFont(QFont("Norwester", 11))
        self._ammo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._suspend_label = QLabel("暂离")
        self._suspend_label.setFont(QFont("Norwester", 11))
        self._suspend_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._suspend_label.hide()
        self.setFixedWidth(120)
        self.setFixedHeight(32)  # 固定高度，避免中文字符回退导致高度变化
        self._fixed_h = 32
        # 底层：黑色底框
        box = QWidget()
        box.setObjectName("box")
        box.setStyleSheet(_BOX_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 6, 0, 6)
        # 中间层：主题色横幅（填满宽度）；文字固定白字
        self._banner = QWidget()
        self._banner.setObjectName("banner")
        banner_lay = QHBoxLayout(self._banner)
        banner_lay.setContentsMargins(0, 0, 0, 0)
        banner_lay.addWidget(self._ammo_label, 1)  # 顶层左：弹种名
        banner_lay.addWidget(self._suspend_label)  # 顶层右：暂离
        lay.addWidget(self._banner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        self._ammo_label.setStyleSheet(f"color: {OVERLAY_TEXT}; padding: 4px 8px 4px 12px;")
        self._suspend_label.setStyleSheet(f"color: {OVERLAY_TEXT}; padding: 4px 12px 4px 8px;")

    def apply_accent(self, accent: str, on_accent_text: str):
        """用户改强调色后重刷横幅背景+文字色（与主界面 on_accent_text 一致）"""
        self._banner.setStyleSheet(f"QWidget#banner {{ background-color: {accent}; }}")
        self._ammo_label.setStyleSheet(f"color: {on_accent_text}; padding: 4px 8px 4px 12px;")
        self._suspend_label.setStyleSheet(f"color: {on_accent_text}; padding: 4px 12px 4px 8px;")

    def showEvent(self, e):
        super().showEvent(e)
        set_click_through(int(self.winId()), True)
        self._suspend_label.setVisible(self._suspended)

    def set_ammo(self, name):
        self._ammo_label.setText(name)

    def set_suspended(self, suspended):
        self._suspended = suspended
        # 只有窗口可见时才更新暂离标签，避免hide_all后暂离导致窗口重新弹出
        if self.isVisible():
            self._suspend_label.setVisible(suspended)

    def show_at_right(self, ox=0, oy=0):
        _position_right(self, ox, oy)
        self.show()
        self.raise_()


class FullOverlay(QWidget):
    def __init__(self, accent: str):
        super().__init__()
        make_wheel_overlay_window(self)
        self._labels = []
        self._current_index = -1
        # 高亮背景色由用户配置 accent 运行时决定；文字跟主界面 on_accent_text
        self._accent = accent
        self._on_accent_text = OVERLAY_TEXT  # 占位，apply_accent 立即覆盖
        box = QWidget()
        box.setObjectName("box")
        box.setStyleSheet(_BOX_STYLE)
        self._box_layout = QVBoxLayout(box)
        self._box_layout.setContentsMargins(0, 6, 0, 6)
        self._box_layout.setSpacing(0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        self._font = QFont("Norwester", 11)
        self.setFixedWidth(120)

    def showEvent(self, e):
        super().showEvent(e)
        set_click_through(int(self.winId()), True)

    def set_ammo_list(self, names, highlight):
        for label in self._labels:
            self._box_layout.removeWidget(label)
            label.deleteLater()
        self._labels.clear()
        for i, name in enumerate(names):
            label = QLabel(name)
            label.setFont(self._font)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if i == highlight:
                label.setStyleSheet(_label_active_style(self._accent, self._on_accent_text))
            else:
                label.setStyleSheet(_label_idle_style())
            self._box_layout.addWidget(label)
            self._labels.append(label)
        self._current_index = highlight

    def update_highlight(self, index):
        if index == self._current_index:
            return
        for i, label in enumerate(self._labels):
            if i == index:
                label.setStyleSheet(_label_active_style(self._accent, self._on_accent_text))
            else:
                label.setStyleSheet(_label_idle_style())
        self._current_index = index

    def apply_accent(self, accent: str, on_accent_text: str):
        """用户改强调色后重刷高亮背景+文字色（与主界面 on_accent_text 一致）"""
        self._accent = accent
        self._on_accent_text = on_accent_text
        for i, label in enumerate(self._labels):
            label.setStyleSheet(_label_active_style(accent, on_accent_text) if i == self._current_index
                                else _label_idle_style())

    def show_at_right(self, ox=0, oy=0):
        _position_right(self, ox, oy)
        self.show()
        self.raise_()


class AmmoWheelSelector(QObject):
    suspend_changed = pyqtSignal(bool)  # True=进入暂离, False=退出暂离

    def __init__(self, state_machine, config_manager, parent=None):
        super().__init__(parent)
        self.state = state_machine
        self.config = config_manager
        self._compact = CompactOverlay()
        self._full = FullOverlay(self.config.get_accent())
        self._mag = MagOverlay()
        self._preview_index = -1
        self._active = False
        self._suspend_state = NORMAL
        self._enabled = True  # overlay隐藏时为False，忽略滚轮事件

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        self._hook = MouseHook.instance()
        self._hook.mouse_wheel.connect(self._on_wheel)
        self._hook.mouse_down.connect(self._on_mouse_down)
        self.state.ammo_type_changed.connect(self._on_ammo_changed_external)
        self.state.magnification_changed.connect(self._on_magnification_changed)
        # 按当前配置把各 overlay 的强调色样式一次刷好
        self.apply_accent()

    def start(self):
        self._enabled = True
        self._hook.acquire()
        self._show_compact()

    def stop(self):
        """退出路径（清理契约调用，幂等）。

        P2-2：反向断开本对象建立的四条连接。前两条挂在 MouseHook 单例上，
        不断开则 stop 后滚轮/按键事件仍会进本对象；后两条挂在 state 上，
        同理。targeted disconnect + TypeError 守卫使 closeEvent 与
        aboutToQuit 双跑安全。
        """
        self._enabled = False
        for sig, slot in (
            (self._hook.mouse_wheel, self._on_wheel),
            (self._hook.mouse_down, self._on_mouse_down),
            (self.state.ammo_type_changed, self._on_ammo_changed_external),
            (self.state.magnification_changed, self._on_magnification_changed),
        ):
            try:
                sig.disconnect(slot)
            except TypeError:
                pass  # 未连接（重复 stop）
        self._hook.release()
        self._compact.hide()
        self._full.hide()
        self._mag.hide()

    def hide_all(self):
        self._enabled = False
        self._compact.hide()
        self._full.hide()
        self._mag.hide()

    def show_all(self):
        self._enabled = True
        if self._active:
            ammo_names = self.config.get_ammo_type_names(self.state.current_vehicle) or []
            self._show_full_with_ammo(ammo_names)
        else:
            self._show_compact()

    def reposition(self):
        """用户在准星面板调整了滚轮位置偏移后，把当前可见的 overlay 按新偏移重新摆位。
        若当前无 overlay 可见（未触发滚轮），临时摆出 compact 供实时预览。"""
        ox, oy = self.config.get_wheel_offset()
        if self._full.isVisible():
            self._full.show_at_right(ox, oy)
        elif self._compact.isVisible():
            self._compact.show_at_right(ox, oy)
        else:
            self._compact.show_at_right(ox, oy)
        if self._mag.isVisible():
            self._position_mag_below(self._full if self._active else self._compact)

    def apply_accent(self):
        """强调色/主题变化后重刷横幅+高亮项（文字跟主界面 on_accent_text）"""
        accent = self.config.get_accent()
        on_accent = self.config.get_on_accent_text()
        self._compact.apply_accent(accent, on_accent)
        self._full.apply_accent(accent, on_accent)

    @property
    def is_suspended(self):
        return self._suspend_state != NORMAL

    def on_suspend_key1(self):
        self._handle_suspend_key(1)

    def on_suspend_key2(self):
        self._handle_suspend_key(2)

    def on_ammo_hotkey(self, ammo_name):
        """弹种热键命令：命令优先于预选列表，立即结束预选回到常显。

        必须由"命令"驱动，不能只靠 state.ammo_type_changed：热键选中的就是当前弹种时，
        StateMachine.set_ammo_type 因值未变化直接 return（细粒度信号约定，避免冗余刷新），
        这里收不到任何信号，预选列表会一直挂到超时——表现就是"选择已选中的弹种失败，
        必须选别的弹种/等超时/左键确定才能回到当前列表"。
        与 _on_mouse_down（左键确定）同一语义：目标等于当前弹种时也要结束预选。
        """
        if not self._active:
            return
        self._cancel_preview()
        # 直接用命令里的弹种名，不依赖"state 先更新"的槽位连接顺序
        if ammo_name:
            self._compact.set_ammo(ammo_name)

    def _handle_suspend_key(self, key):
        if self._suspend_state == NORMAL:
            self._suspend_state = SUSPENDED_KEY1 if key == 1 else SUSPENDED_KEY2
            self.suspend_changed.emit(True)
            # 隐藏状态下不show任何滚轮模块窗口，只记录暂离状态
            if self._enabled:
                self._compact.set_suspended(True)
            self._cancel_preview()
        elif self._suspend_state == SUSPENDED_KEY1:
            if key == 1:
                self._suspend_state = NORMAL
                self.suspend_changed.emit(False)
                if self._enabled:
                    self._compact.set_suspended(False)
            else:
                self._suspend_state = SUSPENDED_KEY2
        else:  # SUSPENDED_KEY2
            if key == 2:
                self._suspend_state = NORMAL
                self.suspend_changed.emit(False)
                if self._enabled:
                    self._compact.set_suspended(False)
            else:
                self._suspend_state = SUSPENDED_KEY1

    def _on_wheel(self, delta):
        if not self._enabled:
            return
        if self._suspend_state != NORMAL:
            return
        vehicle = self.state.current_vehicle
        if not vehicle:
            return
        ammo_names = self.config.get_ammo_type_names(vehicle)
        if not ammo_names:
            return
        if self._preview_index < 0:
            try:
                self._preview_index = ammo_names.index(self.state.current_ammo_type)
            except ValueError:
                self._preview_index = 0
        old_index = self._preview_index
        if delta > 0:
            if self._preview_index > 0:
                self._preview_index -= 1
        else:
            if self._preview_index < len(ammo_names) - 1:
                self._preview_index += 1
        if self._preview_index == old_index and self._active:
            return
        self._show_full_with_ammo(ammo_names)
        self._timeout_timer.start(PREVIEW_TIMEOUT_MS)

    def _show_full_with_ammo(self, ammo_names):
        if not self._enabled:
            return
        self._compact.hide()
        self._full.set_ammo_list(ammo_names, self._preview_index)
        ox, oy = self.config.get_wheel_offset()
        self._full.show_at_right(ox, oy)
        self._active = True
        self._update_mag_display()
        self._position_mag_below(self._full)

    def _on_mouse_down(self, button):
        if not self._active or button != "mouse_left":
            return
        vehicle = self.state.current_vehicle
        if not vehicle or self._preview_index < 0:
            self._cancel_preview()
            return
        ammo_names = self.config.get_ammo_type_names(vehicle)
        if 0 <= self._preview_index < len(ammo_names):
            target = ammo_names[self._preview_index]
            if target != self.state.current_ammo_type:
                self.state.set_ammo_type(target)
        self._cancel_preview()

    def _on_ammo_changed_external(self, ammo_name):
        vehicle = self.state.current_vehicle
        if vehicle:
            ammo_names = self.config.get_ammo_type_names(vehicle)
            try:
                self._preview_index = ammo_names.index(ammo_name)
            except ValueError:
                self._preview_index = -1
        if self._active:
            # P1修复：外部弹种不在列表时 _preview_index=-1，保持当前高亮不丢失
            if self._preview_index >= 0:
                self._full.update_highlight(self._preview_index)
            self._timeout_timer.start(PREVIEW_TIMEOUT_MS)
        else:
            self._compact.set_ammo(ammo_name)

    def _on_magnification_changed(self, index):
        self._update_mag_display()

    def _update_mag_display(self):
        vehicle = self.state.current_vehicle
        if not vehicle:
            return
        mags = self.config.get_magnifications(vehicle)
        if not mags:
            return
        cur_idx = self.state.current_magnification_index
        cur_label = mags[cur_idx].get("label", f"倍率{cur_idx + 1}") if 0 <= cur_idx < len(mags) else ""
        self._mag.set_magnification(cur_label)

    def _position_mag_below(self, anchor):
        """把倍率挂件放在 anchor 窗口的正下方，右对齐。"""
        anchor.adjustSize()
        x = anchor.x()
        y = anchor.y() + anchor.height() + MAG_GAP_PX
        self._mag.show_at(x, y)

    def _on_timeout(self):
        self._cancel_preview()

    def _cancel_preview(self):
        self._active = False
        self._preview_index = -1
        self._timeout_timer.stop()
        if self._enabled:
            self._show_compact()

    def _show_compact(self):
        if not self._enabled:
            return
        self._full.hide()
        self._compact.set_ammo(self.state.current_ammo_type or "")
        ox, oy = self.config.get_wheel_offset()
        self._compact.show_at_right(ox, oy)
        self._update_mag_display()
        self._position_mag_below(self._compact)



