"""
状态机模块 (State Machine)

负责当前载具、当前弹种、当前倍率等运行状态管理。
采用状态机模式实现，状态变化时发出信号通知其他模块。
"""

from PyQt5.QtCore import QObject, pyqtSignal
from typing import Optional


class StateMachine(QObject):
    """状态机 - 管理软件运行状态"""

    # 状态变化信号（细粒度：仅发射实际变化的信号，避免冗余全量刷新）
    ammo_type_changed = pyqtSignal(str)  # 弹种变化 (新弹种名)
    magnification_changed = pyqtSignal(int)  # 倍率变化 (新倍率索引)
    overlay_settings_changed = pyqtSignal()  # Overlay缩放偏移配置变化（不改变状态，仅触发刷新）
    overlay_toggled = pyqtSignal(bool)  # Overlay显示状态变化

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        # 每次启动默认开启准星，不继承上次退出时的状态
        self._overlay_visible = True
        self.config.set_overlay_visible(True)

    @property
    def current_vehicle(self) -> Optional[str]:
        """当前载具名称"""
        return self.config.get_current_state()["vehicle"]

    @property
    def current_ammo_type(self) -> Optional[str]:
        """当前弹种名称"""
        return self.config.get_current_state()["ammo_type"]

    @property
    def current_magnification_index(self) -> int:
        """当前倍率索引"""
        return self.config.get_current_state()["magnification_index"]

    @property
    def overlay_visible(self) -> bool:
        """Overlay是否可见"""
        return self._overlay_visible

    def set_vehicle(self, vehicle_name: str):
        """切换载具"""
        old_vehicle = self.current_vehicle
        if old_vehicle == vehicle_name:
            return

        self.config.set_current_vehicle(vehicle_name)

        if self.current_vehicle != old_vehicle:
            self.ammo_type_changed.emit(self.current_ammo_type or "")
            self.magnification_changed.emit(self.current_magnification_index)

    def set_ammo_type(self, ammo_name: str):
        """切换弹种（继承倍率索引，带越界保护）"""
        old_ammo = self.current_ammo_type
        if old_ammo == ammo_name:
            return

        old_mag_index = self.current_magnification_index
        self.config.set_current_ammo_type(ammo_name)
        new_mag_index = self.current_magnification_index

        if self.current_ammo_type != old_ammo:
            self.ammo_type_changed.emit(ammo_name)
            if new_mag_index != old_mag_index:
                self.magnification_changed.emit(new_mag_index)
            # 不发射 state_changed，弹种切换由 ammo_type_changed 细粒度处理

    def cycle_magnification(self):
        """循环切换倍率"""
        old_index = self.current_magnification_index
        self.config.cycle_magnification()
        new_index = self.current_magnification_index

        if new_index != old_index:
            self.magnification_changed.emit(new_index)
            # 不发射 state_changed，倍率切换由 magnification_changed 细粒度处理

    def reset_magnification(self):
        """重置倍率为最低倍（索引0）"""
        old_index = self.current_magnification_index
        if old_index == 0:
            return
        self.config.set_current_magnification_index(0)
        new_index = self.current_magnification_index

        if new_index != old_index:
            self.magnification_changed.emit(new_index)

    def set_magnification(self, index: int):
        """设置指定倍率索引"""
        old_index = self.current_magnification_index
        self.config.set_current_magnification_index(index)
        new_index = self.current_magnification_index

        if new_index != old_index:
            self.magnification_changed.emit(new_index)

    def refresh_overlay(self):
        """强制刷新 Overlay（缩放偏移配置变化时调用，不改变状态）"""
        self.overlay_settings_changed.emit()

    def toggle_overlay(self):
        """切换Overlay显示/隐藏"""
        self._overlay_visible = not self._overlay_visible
        self.config.set_overlay_visible(self._overlay_visible)
        self.overlay_toggled.emit(self._overlay_visible)
        # 不发射 state_changed，Overlay 切换由 overlay_toggled 处理

    def set_overlay_visible(self, visible: bool):
        """设置Overlay显示状态"""
        if self._overlay_visible == visible:
            return
        self._overlay_visible = visible
        self.config.set_overlay_visible(visible)
        self.overlay_toggled.emit(visible)

    def get_current_crosshair_path(self) -> Optional[str]:
        """获取当前准星图片路径"""
        return self.config.get_current_crosshair()

    def get_current_magnification_label(self) -> str:
        """获取当前倍率标签"""
        vehicle = self.current_vehicle
        ammo = self.current_ammo_type
        idx = self.current_magnification_index

        if not vehicle or not ammo:
            return ""

        magnifications = self.config.get_magnifications(vehicle, ammo)
        if 0 <= idx < len(magnifications):
            return magnifications[idx].get("label", f"倍率{idx + 1}")
        return ""

    def get_state_summary(self) -> str:
        """获取当前状态摘要字符串"""
        vehicle = self.current_vehicle or "未选择"
        ammo = self.current_ammo_type or "未选择"
        mag_label = self.get_current_magnification_label() or "无"
        return f"载具: {vehicle} | 弹种: {ammo} | 倍率: {mag_label}"
