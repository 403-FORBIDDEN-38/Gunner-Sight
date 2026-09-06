"""ConfigManager 统一入口（多继承聚合各模块 mixin，外部 API 不变）"""
from core.config.base import ConfigBaseMixin
from core.config.vehicle import ConfigVehicleMixin
from core.config.rangefinder import ConfigRangefinderMixin
from core.config.angle_meter import ConfigAngleMeterMixin
from core.config.distance import ConfigDistanceMixin
from core.config.squad_macro import ConfigSquadMacroMixin
from core.config.mascot import ConfigMascotMixin


class ConfigManager(
    ConfigBaseMixin,
    ConfigVehicleMixin,
    ConfigRangefinderMixin,
    ConfigAngleMeterMixin,
    ConfigDistanceMixin,
    ConfigSquadMacroMixin,
    ConfigMascotMixin,
):
    """统一配置管理器（聚合所有模块 mixin，外部 API 完全不变）"""
    pass
