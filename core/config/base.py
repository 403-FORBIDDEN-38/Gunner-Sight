"""
配置管理模块 (Configuration Manager)

负责载具、弹种、倍率及软件设置的保存与读取。
采用数据驱动架构，所有配置均通过JSON文件管理。
"""

import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

# 配置版本号：迁移函数只在版本变化时执行，避免每次启动重复遍历
CURRENT_CONFIG_VERSION = 5


def get_app_base_dir() -> Path:
    """获取应用基础目录（兼容开发环境和打包环境）
    14.1 onedir 对齐：frozen 时始终返回 exe 同级目录，用户数据(config/resources)外置在此，
    绝不回退 _internal（_internal 仅存程序依赖，用户不动）。
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def _default_angle_meter_profile() -> Dict:
    """角度仪默认配置。各精度方案独立保存，可切换。"""
    return {
        "pitch_min": -80.0, "pitch_max": 80.0,
        "calibrations": {},
        "active_calibration_point_count": 7,
        "linked_vehicles": [], "auto_reset": False
    }


def _default_angle_meter_segment() -> Dict:
    """angle_meter 配置段默认值单一工厂（空房子原则：profiles 为空，用户自行创建）"""
    return {
        "enabled": False, "current_profile": "",
        "profiles": {},
        "hotkeys": {
            "toggle": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "pause": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "calibrate": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "reset": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "up": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "down": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
        }
    }


def _default_distance_meter_segment() -> Dict:
    """distance_meter 配置段默认值（空房子原则：默认禁用，无默认热键，无标定数据）"""
    return {
        "enabled": False,
        "scale_meters": 300,
        "calibrated_pixels": 0,
        "pixels_per_meter": 0,
        "calibration_direction": "",
        "overlay_offset_x": 100,
        "overlay_offset_y": 100,
        "hotkeys": {
            "toggle": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "record": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "measure": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "modifier": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
        }
    }


class ConfigBaseMixin:
    """base 配置管理 mixin"""

    def __init__(self, config_dir: str = None):
        # 设置配置目录
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = get_app_base_dir() / "config"

        self.config_file = self.config_dir / "config.json"
        self.resources_dir = get_app_base_dir() / "resources"

        # 确保目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.resources_dir.mkdir(parents=True, exist_ok=True)

        # 配置数据（初始为最小骨架，load_config 时从 config.json 加载）
        self._config = self._get_minimal_skeleton()

        # 防抖保存
        self._save_timer = None
        self._save_lock = threading.Lock()

        # 加载配置
        self.load_config()

        # 迁移
        self._migrate_crosshair_paths()

        cfg_ver = self._config.get("config_version", 0)
        if cfg_ver < CURRENT_CONFIG_VERSION:
            self._migrate_ammo_hotkeys()
            self._migrate_xcj_to_rangefinder()
            self._migrate_angle_meter_hotkeys()
            self._migrate_angle_meter_calibration()
            self._config["config_version"] = CURRENT_CONFIG_VERSION
            self.save_config()

    def _get_minimal_skeleton(self) -> Dict:
        """最小安全骨架：程序启动必需的顶层键，缺失时不崩溃"""
        return {
            "version": "1.0",
            "config_version": CURRENT_CONFIG_VERSION,
            "global_settings": {
                "scale": 100.0, "offset_x": 0, "offset_y": 0,
                "overlay_opacity": 1.0, "overlay_visible": True,
            },
            "hotkeys": {
                "toggle_overlay": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "cycle_magnification": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "invert_colors": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "reset_magnification": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "toggle_ui": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            },
            "vehicles": {},
            "current_state": {
                "vehicle": "", "ammo_type": "", "magnification_index": 0,
            },
            "tags": [],
            "theme": "dark",
            "rangefinder": {"profiles": {}, "current_profile": ""},
            "angle_meter": _default_angle_meter_segment(),
            "distance_meter": _default_distance_meter_segment(),
            "squad_macro": {"enabled": False, "name": "", "locked": False, "interval": 100},
            "mascot": {"enabled": False, "volume": 0.225, "persistent": False},
        }

    def _migrate_crosshair_paths(self):
        """迁移旧版准星路径格式"""
        vehicles = self._config.get("vehicles", {})
        for v_name, v_data in vehicles.items():
            for a_name, a_data in v_data.get("ammo_types", {}).items():
                for mag in a_data.get("magnifications", []):
                    ch = mag.get("crosshair", "")
                    if ch and "/" not in ch and "\\" not in ch:
                        mag["crosshair"] = f"任意/{ch}" if ch else ""

    def _migrate_ammo_hotkeys(self):
        """迁移旧版弹种热键 key/trigger -> key1/trigger1/key2/trigger2"""
        hotkeys = self._config.get("hotkeys", {})
        ammo = hotkeys.get("ammo_types", {})
        for v_name, v_hotkeys in ammo.items():
            if isinstance(v_hotkeys, dict) and "key" in v_hotkeys:
                if not v_hotkeys.get("key1"):
                    v_hotkeys["key1"] = v_hotkeys["key"]
                    v_hotkeys["trigger1"] = v_hotkeys.get("trigger", "keydown")
                v_hotkeys.pop("key", None)
                v_hotkeys.pop("trigger", None)

    def _migrate_xcj_to_rangefinder(self):
        """迁移旧版 xcj 段到 rangefinder"""
        if "xcj" in self._config:
            old_seg = self._config["xcj"]
            new_seg = self._config.setdefault("rangefinder", {"profiles": {}, "current_profile": ""})
            for k, v in old_seg.items():
                if k not in new_seg or not new_seg.get(k):
                    new_seg[k] = v
            print("[ConfigManager] xcj -> rangefinder 迁移完成")
            del self._config["xcj"]
            self.request_save()

    def _migrate_angle_meter_hotkeys(self):
        """迁移角度仪旧版热键格式"""
        am = self._config.get("angle_meter", {})
        hotkeys = am.get("hotkeys", {})
        for action, hk in hotkeys.items():
            if isinstance(hk, dict) and "key" in hk:
                if not hk.get("key1"):
                    hk["key1"] = hk["key"]
                    hk["trigger1"] = hk.get("trigger", "keydown")
                hk.pop("key", None)
                hk.pop("trigger", None)

    def _migrate_angle_meter_calibration(self):
        """迁移角度仪旧版校准数据格式"""
        am = self._config.get("angle_meter", {})
        for name, profile in am.get("profiles", {}).items():
            if "calibration" in profile and "calibrations" not in profile:
                profile["calibrations"] = {"7": profile.pop("calibration")}
                profile["active_calibration_point_count"] = 7

    def load_config(self) -> bool:
        """从文件加载配置。优先级：config.json > 最小骨架"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                self._merge_config(self._config, loaded)
                self._migrate_legacy_hotkey_fields()
                return True
            except Exception as e:
                print(f"[ConfigManager] config.json 加载失败: {e}，备份并回退最小骨架")
                try:
                    backup = self.config_file.with_suffix('.json.corrupt')
                    self.config_file.rename(backup)
                except Exception:
                    pass

        # 安全回退：最小骨架
        self._config = self._get_minimal_skeleton()
        self.save_config()
        return False

    def _merge_config(self, default: Dict, loaded: Dict):
        """递归合并配置，保留loaded中的值，补充default中的新字段"""
        for key, value in default.items():
            if key not in loaded or loaded[key] is None:
                loaded[key] = value
            elif isinstance(value, dict) and isinstance(loaded[key], dict):
                self._merge_config(value, loaded[key])
        self._config = loaded

    def _migrate_legacy_hotkey_fields(self):
        """加载时迁移旧格式热键 key/trigger -> key1/trigger1（内存中）"""
        hotkeys = self._config.get("hotkeys", {})
        for hk_name, hk_val in hotkeys.items():
            if isinstance(hk_val, dict) and "key" in hk_val:
                if not hk_val.get("key1") and hk_val.get("key"):
                    hk_val["key1"] = hk_val["key"]
                    hk_val["trigger1"] = hk_val.get("trigger", "keydown")

    def _prepare_config_for_save(self):
        """保存前清理冗余字段 + 统一分区顺序"""
        cfg = self._config
        # 清理热键旧格式
        hotkeys = cfg.get("hotkeys", {})
        for hk_name, hk_val in hotkeys.items():
            if isinstance(hk_val, dict) and "key" in hk_val:
                if not hk_val.get("key1") and hk_val.get("key"):
                    hk_val["key1"] = hk_val["key"]
                    hk_val["trigger1"] = hk_val.get("trigger", "keydown")
                del hk_val["key"]
                if "trigger" in hk_val:
                    del hk_val["trigger"]
        # 统一顶层键顺序
        ordered = {}
        key_order = [
            "version", "global_settings", "hotkeys", "vehicles",
            "angle_meter", "distance_meter", "squad_macro", "mascot",
        ]
        for k in key_order:
            if k in cfg:
                ordered[k] = cfg[k]
        for k in cfg:
            if k not in ordered:
                ordered[k] = cfg[k]
        self._config = ordered
        return ordered

    def save_config(self) -> bool:
        """立即保存配置到文件"""
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
            try:
                self._prepare_config_for_save()
                data = json.dumps(self._config, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"序列化配置失败: {e}")
                return False
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(data)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def request_save(self):
        """请求保存配置（防抖：500ms）"""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(0.5, self._do_deferred_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _do_deferred_save(self):
        with self._save_lock:
            self._save_timer = None
            try:
                self._prepare_config_for_save()
                data = json.dumps(self._config, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"序列化配置失败: {e}")
                return
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(data)
        except Exception as e:
            print(f"保存配置失败: {e}")

    # ==================== 全局设置 ====================

    def get_global_scale(self) -> float:
        return self._config["global_settings"]["scale"]

    def set_global_scale(self, scale: float):
        self._config["global_settings"]["scale"] = max(1.0, min(1000.0, scale))
        self.request_save()

    def get_global_offset_x(self) -> int:
        return self._config["global_settings"]["offset_x"]

    def set_global_offset_x(self, offset: int):
        self._config["global_settings"]["offset_x"] = offset
        self.request_save()

    def get_global_offset_y(self) -> int:
        return self._config["global_settings"]["offset_y"]

    def set_global_offset_y(self, offset: int):
        self._config["global_settings"]["offset_y"] = offset
        self.request_save()

    def set_global_offset(self, offset_x: int, offset_y: int):
        self._config["global_settings"]["offset_x"] = offset_x
        self._config["global_settings"]["offset_y"] = offset_y
        self.request_save()

    def get_overlay_opacity(self) -> float:
        return self._config["global_settings"].get("overlay_opacity", 1.0)

    def set_overlay_opacity(self, opacity: float):
        self._config["global_settings"]["overlay_opacity"] = max(0.1, min(1.0, opacity))
        self.request_save()

    def get_overlay_visible(self) -> bool:
        return self._config["global_settings"].get("overlay_visible", True)

    def set_overlay_visible(self, visible: bool):
        self._config["global_settings"]["overlay_visible"] = visible
        self.request_save()

    # ==================== 热键 ====================

    def get_hotkey(self, action: str) -> Dict:
        return self._config.get("hotkeys", {}).get(action, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })

    def set_hotkey(self, action: str, key: str, trigger: str = "keydown", slot: int = 1):
        hk = self._config.setdefault("hotkeys", {}).setdefault(action, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()

    def get_all_hotkeys(self) -> Dict:
        return self._config.get("hotkeys", {})

    # ==================== 当前状态 ====================

    def get_current_state(self) -> Dict:
        return self._config.get("current_state", {})

    def set_current_vehicle(self, vehicle_name: str):
        self._config.setdefault("current_state", {})["vehicle"] = vehicle_name
        # 级联：切换载具后选第一个弹种
        vehicles = self._config.get("vehicles", {})
        if vehicle_name in vehicles:
            ammo_types = vehicles[vehicle_name].get("ammo_types", {})
            if ammo_types:
                first_ammo = list(ammo_types.keys())[0]
                self._config["current_state"]["ammo_type"] = first_ammo
                mags = ammo_types[first_ammo].get("magnifications", [])
                if mags:
                    self._config["current_state"]["magnification_index"] = 0
        self.request_save()

    def set_current_ammo_type(self, ammo_name: str):
        self._config.setdefault("current_state", {})["ammo_type"] = ammo_name
        self._config["current_state"]["magnification_index"] = 0
        self.request_save()

    def set_current_magnification_index(self, index: int):
        self._config.setdefault("current_state", {})["magnification_index"] = index
        self.request_save()

    def cycle_magnification(self):
        state = self._config.get("current_state", {})
        vehicle = state.get("vehicle", "")
        ammo = state.get("ammo_type", "")
        vehicles = self._config.get("vehicles", {})
        if vehicle in vehicles and ammo in vehicles[vehicle].get("ammo_types", {}):
            mags = vehicles[vehicle]["ammo_types"][ammo].get("magnifications", [])
            if mags:
                cur = state.get("magnification_index", 0)
                new_idx = (cur + 1) % len(mags)
                state["magnification_index"] = new_idx
                self.request_save()
                return new_idx
        return 0

    def get_current_crosshair(self) -> Optional[str]:
        state = self._config.get("current_state", {})
        vehicle = state.get("vehicle", "")
        ammo = state.get("ammo_type", "")
        idx = state.get("magnification_index", 0)
        vehicles = self._config.get("vehicles", {})
        if vehicle in vehicles and ammo in vehicles[vehicle].get("ammo_types", {}):
            mags = vehicles[vehicle]["ammo_types"][ammo].get("magnifications", [])
            if 0 <= idx < len(mags):
                return mags[idx].get("crosshair", "")
        return None

    # ==================== 主题 ====================

    def get_theme(self) -> str:
        return self._config.get("theme", "dark")

    def set_theme(self, theme: str):
        self._config["theme"] = theme
        self.request_save()

    # ==================== 工具 ====================

    def unbind_crosshair(self, crosshair_name: str) -> int:
        """解除所有载具/弹种/倍率对指定准星的绑定，返回解除数量"""
        count = 0
        vehicles = self._config.get("vehicles", {})
        for v_data in vehicles.values():
            for a_data in v_data.get("ammo_types", {}).values():
                for mag in a_data.get("magnifications", []):
                    if mag.get("crosshair") == crosshair_name:
                        mag["crosshair"] = ""
                        count += 1
        if count > 0:
            self.request_save()
        return count
