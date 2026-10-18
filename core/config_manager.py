"""兼容入口：从 core.config 包导入 ConfigManager 及模块级函数（外部引用无需修改）"""
from core.config import ConfigManager
from core.config.base import (
    _default_angle_meter_profile,
    _default_angle_meter_segment,
    _default_distance_meter_segment,
    get_app_base_dir,
)

__all__ = [
    'ConfigManager', 'get_app_base_dir',
    '_default_angle_meter_profile', '_default_angle_meter_segment',
    '_default_distance_meter_segment',
]
