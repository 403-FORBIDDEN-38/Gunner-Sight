"""
状态机模块 (State Machine)

负责当前载具、当前弹种、当前倍率等运行状态管理。
采用状态机模式实现，状态变化时发出信号通知其他模块。
所有业务方法（增删改载具/弹种/倍率）的 state 包装都在这里。
"""


from PyQt5.QtCore import QObject, pyqtSignal


class StateMachine(QObject):
    """状态机 - 管理软件运行状态"""

    # 状态变化信号（细粒度：仅发射实际变化的信号，避免冗余全量刷新）
    vehicle_changed = pyqtSignal(str)  # 载具变化 (新载具名)
    ammo_type_changed = pyqtSignal(str)  # 弹种变化 (新弹种名)
    magnification_changed = pyqtSignal(int)  # 倍率变化 (新倍率索引)
    overlay_settings_changed = pyqtSignal()  # Overlay缩放偏移配置变化（不改变状态，仅触发刷新）
    overlay_toggled = pyqtSignal(bool)  # Overlay显示状态变化

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        # 首次启动默认开启准星；已有配置则保持用户上次的设置
        if "overlay_visible" not in self.config._config.get("global_settings", {}):
            self.config._set_overlay_visible(True)
        # 统一刷新：任何配置变更自动触发overlay刷新，不需要每个调用点手动调
        self.config.add_on_change_callback(self.refresh_overlay)

    @property
    def current_vehicle(self) -> str | None:
        """当前载具名称"""
        return self.config.get_current_state()["vehicle"]

    @property
    def current_ammo_type(self) -> str | None:
        """当前弹种名称"""
        return self.config.get_current_state()["ammo_type"]

    @property
    def current_magnification_index(self) -> int:
        """当前倍率索引"""
        return self.config.get_current_state()["magnification_index"]

    @property
    def overlay_visible(self) -> bool:
        """Overlay是否可见（从 config 现场读，不缓存）"""
        return self.config.get_overlay_visible()

    def set_vehicle(self, vehicle_name: str | None):
        """切换载具"""
        old_vehicle = self.current_vehicle
        if old_vehicle == vehicle_name:
            return

        self.config._set_current_vehicle(vehicle_name)
        self.vehicle_changed.emit(self.current_vehicle or "")
        self.ammo_type_changed.emit(self.current_ammo_type or "")
        self.magnification_changed.emit(self.current_magnification_index)

    def set_ammo_type(self, ammo_name: str | None):
        """切换弹种（继承倍率索引，带越界保护）"""
        old_ammo = self.current_ammo_type
        if old_ammo == ammo_name:
            return

        old_mag_index = self.current_magnification_index
        self.config._set_current_ammo_type(ammo_name)
        new_mag_index = self.current_magnification_index
        self.ammo_type_changed.emit(ammo_name or "")
        if new_mag_index != old_mag_index:
            self.magnification_changed.emit(new_mag_index)

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
        self.config._set_current_magnification_index(0)
        new_index = self.current_magnification_index

        if new_index != old_index:
            self.magnification_changed.emit(new_index)

    def set_magnification(self, index: int):
        """设置指定倍率索引"""
        old_index = self.current_magnification_index
        self.config._set_current_magnification_index(index)
        new_index = self.current_magnification_index

        if new_index != old_index:
            self.magnification_changed.emit(new_index)

    def refresh_overlay(self):
        """强制刷新 Overlay（缩放偏移配置变化时调用，不改变状态）"""
        self.overlay_settings_changed.emit()

    def toggle_overlay(self):
        """切换Overlay显示/隐藏"""
        new_visible = not self.overlay_visible
        self.config._set_overlay_visible(new_visible)
        self.overlay_toggled.emit(new_visible)

    def set_overlay_visible(self, visible: bool):
        """设置Overlay显示状态"""
        if self.overlay_visible == visible:
            return
        self.config._set_overlay_visible(visible)
        self.overlay_toggled.emit(visible)

    def get_current_crosshair_path(self) -> str | None:
        """获取当前准星图片路径"""
        return self.config.get_current_crosshair()

    def get_current_magnification_label(self) -> str:
        """获取当前倍率标签"""
        vehicle = self.current_vehicle
        ammo = self.current_ammo_type
        idx = self.current_magnification_index

        if not vehicle or not ammo:
            return ""

        magnifications = self.config.get_magnifications(vehicle)
        if 0 <= idx < len(magnifications):
            return magnifications[idx].get("label", f"倍率{idx + 1}")
        return ""

    def get_state_summary(self) -> str:
        """获取当前状态摘要字符串"""
        vehicle = self.current_vehicle or "未选择"
        ammo = self.current_ammo_type or "未选中"
        mag_label = self.get_current_magnification_label() or "未选中"
        return f"载具: {vehicle} | 弹种: {ammo} | 倍率: {mag_label}"

    # ==================== 业务方法包装（载具/弹种/倍率增删改） ====================
    # 这些方法先调 config 层的业务方法，再根据 was_current 决定要不要发信号。
    # config 层不再碰 current_state，全部由这里负责。

    def add_vehicle(self, name: str) -> bool:
        """新增载具。成功后自动切换到新载具。"""
        if not self.config.add_vehicle(name):
            return False
        self.set_vehicle(name)
        return True

    def remove_vehicle(self, name: str):
        """删除载具。如果删的是当前载具，自动切到 None。"""
        was_current = (self.current_vehicle == name)
        self.config.remove_vehicle(name)
        if was_current:
            self.set_vehicle(None)

    def rename_vehicle(self, old_name: str, new_name: str):
        """重命名载具。如果重命名的是当前载具，自动切到新名。"""
        was_current = (self.current_vehicle == old_name)
        self.config.rename_vehicle(old_name, new_name)
        if was_current:
            self.set_vehicle(new_name)

    def copy_vehicle(self, src_name: str, dst_name: str) -> bool:
        """复制载具。成功后自动切换到新载具。"""
        if not self.config.copy_vehicle(src_name, dst_name):
            return False
        self.set_vehicle(dst_name)
        return True

    def import_vehicle(self, resources_dir, gsv_path):
        """导入载具包。成功后自动切换到新载具。
        返回 (ok, msg, new_name)。"""
        from core.vehicle_io import import_vehicle as _import
        ok, msg, new_name = _import(self.config, resources_dir, gsv_path)
        if ok and new_name:
            self.set_vehicle(new_name)
        return ok, msg, new_name

    def remove_ammo_type(self, vehicle_name: str, ammo_name: str):
        """删除弹种。如果删的是当前弹种，自动切到 None。"""
        was_current = (
            self.current_vehicle == vehicle_name
            and self.current_ammo_type == ammo_name
        )
        self.config.remove_ammo_type(vehicle_name, ammo_name)
        if was_current:
            self.set_ammo_type(None)

    def rename_ammo_type(self, vehicle_name: str, old_name: str, new_name: str):
        """重命名弹种。如果重命名的是当前弹种，自动切到新名。"""
        was_current = (
            self.current_vehicle == vehicle_name
            and self.current_ammo_type == old_name
        )
        self.config.rename_ammo_type(vehicle_name, old_name, new_name)
        if was_current:
            self.set_ammo_type(new_name)

    def remove_magnification(self, vehicle_name: str, index: int):
        """删除倍率。如果删的是当前载具的倍率且越界，自动截断到合法范围。"""
        was_current = (self.current_vehicle == vehicle_name)
        self.config.remove_magnification(vehicle_name, index)
        if not was_current:
            return
        old_index = self.current_magnification_index
        new_count = self.config.get_magnification_count(vehicle_name)
        if old_index >= new_count:
            self.set_magnification(max(0, new_count - 1))
