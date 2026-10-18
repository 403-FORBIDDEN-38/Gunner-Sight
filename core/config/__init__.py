"""ConfigManager 统一入口（多继承聚合各模块 mixin，外部 API 不变）"""
from core.config.angle_meter import ConfigAngleMeterMixin
from core.config.base import ConfigBaseMixin
from core.config.distance import ConfigDistanceMixin
from core.config.magnifier import ConfigMagnifierMixin
from core.config.mascot import ConfigMascotMixin
from core.config.squad_macro import ConfigSquadMacroMixin
from core.config.vehicle import ConfigVehicleMixin


class ConfigManager(
    ConfigBaseMixin,
    ConfigVehicleMixin,
    ConfigAngleMeterMixin,
    ConfigDistanceMixin,
    ConfigMagnifierMixin,
    ConfigSquadMacroMixin,
    ConfigMascotMixin,
):
    """统一配置管理器（聚合所有模块 mixin，外部 API 完全不变）"""
    pass
