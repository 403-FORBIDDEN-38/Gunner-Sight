"""自动拆分 config_manager.py 为 core/config/ 包（mixin模式）- 修正版"""
import os, re

base = r'C:\Users\suncheng\Doubao\chats\2026-07-30\new-chat\GunnerSight'
src = os.path.join(base, 'core/config_manager.py')
out_dir = os.path.join(base, 'core/config')

# 先读取原文件（还没被覆盖）
with open(src, 'r', encoding='utf-8') as f:
    content = f.read()
lines = content.split('\n')

# 提取import部分（从开头到 class ConfigManager: 之前）
class_start = None
for i, line in enumerate(lines):
    if line.startswith('class ConfigManager:'):
        class_start = i
        break

import_lines = lines[:class_start]
# 去掉空行和模块docstring，只保留import
import_block = '\n'.join(import_lines).strip()
print(f'Import block: {len(import_lines)} lines')

class_lines = lines[class_start:]

# 方法分组（同上）
groups = {
    'base': ['__init__', '_get_minimal_skeleton', '_migrate_crosshair_paths', '_migrate_ammo_hotkeys', '_migrate_xcj_to_rangefinder', '_migrate_angle_meter_hotkeys', '_migrate_angle_meter_calibration', 'load_config', '_merge_config', '_migrate_legacy_hotkey_fields', '_prepare_config_for_save', 'save_config', 'request_save', '_do_deferred_save', 'get_global_scale', 'set_global_scale', 'get_global_offset_x', 'set_global_offset_x', 'get_global_offset_y', 'set_global_offset_y', 'set_global_offset', 'get_overlay_opacity', 'set_overlay_opacity', 'get_overlay_visible', 'set_overlay_visible', 'get_hotkey', 'set_hotkey', 'get_all_hotkeys', 'get_current_state', 'set_current_vehicle', 'set_current_ammo_type', 'set_current_magnification_index', 'cycle_magnification', 'get_current_crosshair', 'get_theme', 'set_theme', 'unbind_crosshair'],
    'vehicle': ['get_vehicles', 'get_vehicle_names', 'get_vehicle', 'get_vehicle_overlay', 'set_vehicle_overlay', 'reset_vehicle_overlay', 'get_magnification_overlay_mode', 'set_magnification_overlay_mode', 'get_effective_overlay', '_default_vehicle_overlay', 'add_vehicle', 'remove_vehicle', 'rename_vehicle', 'copy_vehicle', 'get_all_tags', 'add_tag', 'remove_tag', 'rename_tag', 'get_vehicle_tags', 'set_vehicle_tags', 'get_vehicle_names_filtered', 'get_ammo_types', 'get_ammo_type_names', 'add_ammo_type', 'remove_ammo_type', 'rename_ammo_type', 'get_magnifications', 'add_magnification', 'remove_magnification', 'update_magnification', 'get_magnification_count', 'get_ammo_hotkey', 'set_ammo_hotkey', '_migrate_ammo_hotkeys_vehicle_scope'],
    'rangefinder': ['is_rangefinder_enabled', 'set_rangefinder_enabled', 'is_toggle_ui_enabled', 'set_toggle_ui_enabled', 'get_toggle_ui_step_interval', 'set_toggle_ui_step_interval', 'get_rangefinder_profiles', 'get_rangefinder_profile_names', 'get_rangefinder_profile', 'get_current_rangefinder_profile', 'set_current_rangefinder_profile', 'add_rangefinder_profile', 'update_rangefinder_profile', 'delete_rangefinder_profile', 'rename_rangefinder_profile', 'get_rangefinder_profile_linked_vehicles', 'set_rangefinder_profile_linked_vehicles', 'get_rangefinder_profile_effective_tags', 'get_rangefinder_profiles_filtered', 'get_rangefinder_profile_for_vehicle', 'get_rangefinder_hotkeys', 'set_rangefinder_hotkey'],
    'angle_meter': ['_ensure_angle_meter_defaults', 'is_angle_meter_enabled', 'set_angle_meter_enabled', 'get_angle_meter_profiles', 'get_angle_meter_profile', 'set_angle_meter_profile', 'add_angle_meter_profile', 'rename_angle_meter_profile', 'delete_angle_meter_profile', 'get_current_angle_meter_profile', 'set_current_angle_meter_profile', 'get_angle_meter_profile_for_vehicle', 'get_angle_meter_profile_linked_vehicles', 'get_angle_meter_profile_effective_tags', 'get_angle_meter_calibration_points', 'set_angle_meter_calibration_points', 'get_active_calibration_point_count', 'set_active_calibration_point_count', 'get_all_calibration_status', 'clear_all_calibrations', 'get_effective_angle_meter_calibration', 'get_angle_meter_hotkeys', 'set_angle_meter_hotkey'],
    'distance': ['is_distance_meter_enabled', 'set_distance_meter_enabled', 'get_distance_meter_scale', 'set_distance_meter_scale', 'get_distance_meter_calibration', 'set_distance_meter_calibration', 'clear_distance_meter_calibration', 'get_distance_meter_overlay_offset', 'set_distance_meter_overlay_offset', 'get_distance_meter_hotkeys', 'set_distance_meter_hotkey', 'get_distance_meter_modifiers'],
    'squad_macro': ['is_squad_macro_enabled', 'set_squad_macro_enabled', 'get_squad_macro_hotkey', 'set_squad_macro_hotkey', 'get_squad_macro_name', 'set_squad_macro_name', 'is_squad_macro_locked', 'set_squad_macro_locked', 'get_squad_macro_interval', 'set_squad_macro_interval'],
    'mascot': ['is_mascot_enabled', 'set_mascot_enabled', 'get_mascot_volume', 'set_mascot_volume', 'is_mascot_persistent', 'set_mascot_persistent'],
}

def find_methods(class_lines):
    methods = {}
    i = 0
    while i < len(class_lines):
        m = re.match(r'^    def (\w+)\(', class_lines[i])
        if m:
            name = m.group(1)
            start = i
            j = i + 1
            while j < len(class_lines):
                if re.match(r'^    def \w+\(', class_lines[j]):
                    break
                j += 1
            methods[name] = (start, j)
            i = j
        else:
            i += 1
    return methods

methods = find_methods(class_lines)
print(f'Found {len(methods)} methods')

# 检查未分组
all_grouped = set()
for g in groups.values():
    all_grouped.update(g)
ungrouped = set(methods.keys()) - all_grouped
if ungrouped:
    print(f'WARNING: ungrouped: {ungrouped}')

os.makedirs(out_dir, exist_ok=True)

# 生成每个mixin文件（带import）
for group_name, method_names in groups.items():
    mixin_class = f'Config{group_name.title().replace("_", "")}Mixin'
    body = [import_block, '', f'class {mixin_class}:', f'    """{group_name} 配置管理 mixin"""', '']
    for mname in method_names:
        if mname in methods:
            start, end = methods[mname]
            for line in class_lines[start:end]:
                body.append(line)
            body.append('')
    out_path = os.path.join(out_dir, f'{group_name}.py')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(body))
    print(f'  {group_name}.py: {len(body)} lines')

# __init__.py
init = '''"""ConfigManager 统一入口（多继承聚合各模块 mixin，外部 API 不变）"""
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
'''
with open(os.path.join(out_dir, '__init__.py'), 'w', encoding='utf-8') as f:
    f.write(init)

# 兼容入口
compat = '''"""兼容入口：从 core.config 包导入 ConfigManager（外部引用无需修改）"""
from core.config import ConfigManager

__all__ = ['ConfigManager']
'''
with open(src, 'w', encoding='utf-8') as f:
    f.write(compat)

print('\nSPLIT DONE')
