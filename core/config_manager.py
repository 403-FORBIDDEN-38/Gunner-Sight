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


def get_app_base_dir() -> Path:
    """获取应用基础目录（兼容开发环境和打包环境）
    14.1 onedir 对齐：frozen 时始终返回 exe 同级目录，用户数据(config/resources)外置在此，
    绝不回退 _internal（_internal 仅存程序依赖，用户不动）。
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _default_angle_meter_profile() -> Dict:
    """R1: 角度仪默认配置单一工厂（最小骨架与 _ensure 共用，禁止两份字面量）"""
    return {"min_angle": -80.0, "max_angle": 80.0, "calibration": None, "linked_vehicles": [], "auto_reset": False}


def _default_angle_meter_segment() -> Dict:
    """R1: angle_meter 配置段默认值单一工厂"""
    return {
        "enabled": False, "current_profile": "",
        "profiles": {"默认配置": _default_angle_meter_profile()},
        "hotkeys": {
            "toggle": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "pause": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "calibrate": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "reset": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
        }
    }


class ConfigManager:
    """配置管理器 - 负责所有配置数据的持久化与访问"""

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

        # 防抖保存：set_* 调用 request_save()，500ms 无新修改才写盘
        self._save_timer = None
        self._save_lock = threading.Lock()

        # 加载配置
        self.load_config()

        # 数据迁移：旧版倍率准星存绝对路径，统一为文件名
        self._migrate_crosshair_paths()
        # 数据迁移：旧版弹种热键用 key/trigger 单键格式，统一为 key1/trigger1/key2/trigger2
        self._migrate_ammo_hotkeys()
        # 数据迁移：旧版 "xcj" 配置段 → 新版 "rangefinder" 段（批次2 全局改名）
        self._migrate_xcj_to_rangefinder()
        # 数据迁移：角度仪热键旧单键格式 → 新双键格式
        self._migrate_angle_meter_hotkeys()
        # 数据迁移：弹种热键从全局改为按载具维度
        self._migrate_ammo_hotkeys_vehicle_scope()
        # 确保 angle_meter 段存在（旧 config.json 可能没有此段），内存中补全，不写盘
        self._ensure_angle_meter_defaults()

    def _get_minimal_skeleton(self) -> Dict:
        """最小骨架配置（仅用于 config.json 丢失/损坏时的最后安全回退）"""
        return {
            "version": "1.0",
            "global_settings": {"scale": 100.0, "offset_x": 0, "offset_y": 0, "overlay_visible": True},
            "hotkeys": {
                "toggle_overlay": {"key1": "f1", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "cycle_magnification": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "invert_colors": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "reset_magnification": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "toggle_ui": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                "ammo_types": {}
            },
            "vehicles": {},
            "tags": [],
            "rangefinder": {
                "enabled": False, "toggle_ui_enabled": True, "current_profile": "",
                "profiles": {},
                "hotkeys": {"measure": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"}}
            },
            "squad_macro": {"enabled": False, "hotkey": {"key1": "", "trigger1": "keydown"}, "squad_name": "", "locked": True, "interval_ms": 100},
            "angle_meter": _default_angle_meter_segment(),
            "current_state": {"vehicle": None, "ammo_type": None, "magnification_index": 0}
        }

    def _migrate_crosshair_paths(self):
        """旧版倍率准星存绝对路径，统一为相对文件名；引用不存在文件的清空"""
        changed = False
        for v_name, v_data in self._config.get("vehicles", {}).items():
            for a_name, a_data in v_data.get("ammo_types", {}).items():
                for mag in a_data.get("magnifications", []):
                    ch = mag.get("crosshair", "")
                    if not ch:
                        continue
                    # 绝对路径 → 取文件名
                    if os.path.isabs(ch):
                        ch = os.path.basename(ch)
                        mag["crosshair"] = ch
                        changed = True
                    # 文件不存在 → 清空（避免持续报"准星图片不存在"）
                    if ch and not (self.resources_dir / ch).exists():
                        mag["crosshair"] = ""
                        changed = True
        if changed:
            self.request_save()

    def _migrate_ammo_hotkeys(self):
        """16.1: 旧版弹种热键 key/trigger → key1/trigger1/key2/trigger2。
        按值判定：旧key有值且新key1为空才搬（兼容骨架合并后新旧键并存的情况）。"""
        changed = False
        for hk in self._config.get("hotkeys", {}).get("ammo_types", {}).values():
            if hk.get("key") and not hk.get("key1"):
                hk["key1"] = hk.pop("key")
                hk["trigger1"] = hk.pop("trigger", "keydown")
                hk.setdefault("key2", "")
                hk.setdefault("trigger2", "keydown")
                changed = True
            elif "key" in hk and not hk.get("key"):
                hk.pop("key", None)
                hk.pop("trigger", None)
        if changed:
            self.request_save()

    def _migrate_xcj_to_rangefinder(self):
        """批次2: 旧版 "xcj" 配置段 → 新版 "rangefinder" 段（全局改名）。
        老 config.json 升级不丢配置：若存在旧 xcj 段且无 rangefinder 段，整体迁移。"""
        old_seg = self._config.get("xcj")
        new_seg = self._config.get("rangefinder")
        if old_seg is not None and new_seg is None:
            self._config["rangefinder"] = old_seg
            del self._config["xcj"]
            self.request_save()
            print("[ConfigManager] 配置迁移: xcj → rangefinder 段已迁移")
        elif old_seg is not None and new_seg is not None:
            # 新段 profiles 为空且旧段有数据 → 搬入旧段数据（禁止无脑删旧）
            if not new_seg.get("profiles") and old_seg.get("profiles"):
                new_seg["profiles"] = old_seg["profiles"]
                for k in ("enabled", "toggle_ui_enabled", "current_profile", "hotkeys"):
                    if k in old_seg and (k not in new_seg or not new_seg.get(k)):
                        new_seg[k] = old_seg[k]
                print("[ConfigManager] 配置迁移: xcj 数据已搬入空 rangefinder 段")
            del self._config["xcj"]
            self.request_save()

    def _migrate_angle_meter_hotkeys(self):
        """16.1: 角度仪热键旧单键 {key,trigger} → 新双键 {key1,trigger1,key2,trigger2}。
        按值判定：旧key有值且新key1为空才搬（兼容骨架合并后新旧键并存）。"""
        am = self._config.get("angle_meter", {})
        hks = am.get("hotkeys", {})
        changed = False
        for action, hk in hks.items():
            if hk.get("key") and not hk.get("key1"):
                hk["key1"] = hk.pop("key")
                hk["trigger1"] = hk.pop("trigger", "keydown")
                hk.setdefault("key2", "")
                hk.setdefault("trigger2", "keydown")
                changed = True
            elif "key" in hk and not hk.get("key"):
                hk.pop("key", None)
                hk.pop("trigger", None)
        if changed:
            self.request_save()
            print("[ConfigManager] 配置迁移: 角度仪热键 单键→双键 已迁移")

    def load_config(self) -> bool:
        """从文件加载配置。
        优先级：config.json（用户配置，含出厂预设） > 最小骨架（安全回退）
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                self._merge_config(self._config, loaded)
                return True
            except Exception as e:
                print(f"[ConfigManager] config.json 加载失败: {e}，备份并回退最小骨架")
                try:
                    backup = self.config_file.with_suffix('.json.corrupt')
                    self.config_file.rename(backup)
                except Exception:
                    pass


        # 最后安全回退：最小骨架
        self._config = self._get_minimal_skeleton()
        self.save_config()
        return False

    def _merge_config(self, default: Dict, loaded: Dict):
        """递归合并配置，保留loaded中的值，补充default中的新字段
        loaded中为None的字段会被default覆盖（兼容旧配置残留）"""
        for key, value in default.items():
            if key not in loaded or loaded[key] is None:
                loaded[key] = value
            elif isinstance(value, dict) and isinstance(loaded[key], dict):
                self._merge_config(value, loaded[key])
        self._config = loaded

    def save_config(self) -> bool:
        """立即保存配置到文件（closeEvent 等需要同步写盘的场景）"""
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=4, ensure_ascii=False)
                return True
            except Exception as e:
                print(f"保存配置失败: {e}")
                return False

    def request_save(self):
        """请求保存配置（防抖：500ms 内无新修改才写盘，避免滑块拖动等高频操作反复IO）"""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(0.5, self._do_deferred_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _do_deferred_save(self):
        with self._save_lock:
            self._save_timer = None
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"保存配置失败: {e}")

    # ==================== 全局设置 ====================

    def get_global_scale(self) -> float:
        """获取全局缩放比例(%)"""
        return self._config["global_settings"]["scale"]

    def set_global_scale(self, scale: float):
        """设置全局缩放比例(%)"""
        self._config["global_settings"]["scale"] = max(1.0, min(1000.0, scale))
        self.request_save()

    def get_global_offset_x(self) -> int:
        """获取全局X偏移(像素)"""
        return self._config["global_settings"]["offset_x"]

    def set_global_offset_x(self, offset: int):
        """设置全局X偏移(像素)"""
        self._config["global_settings"]["offset_x"] = int(offset)
        self.request_save()

    def get_global_offset_y(self) -> int:
        """获取全局Y偏移(像素)"""
        return self._config["global_settings"]["offset_y"]

    def set_global_offset_y(self, offset: int):
        """设置全局Y偏移(像素)"""
        self._config["global_settings"]["offset_y"] = int(offset)
        self.request_save()

    def set_global_offset(self, offset_x: int, offset_y: int):
        """设置全局偏移（合并写盘，避免两次IO）"""
        self._config["global_settings"]["offset_x"] = int(offset_x)
        self._config["global_settings"]["offset_y"] = int(offset_y)
        self.request_save()

    def get_overlay_visible(self) -> bool:
        """获取Overlay显示状态"""
        return self._config["global_settings"]["overlay_visible"]

    def set_overlay_visible(self, visible: bool):
        """设置Overlay显示状态（运行时状态，不立即写盘）"""
        self._config["global_settings"]["overlay_visible"] = visible

    # ==================== 载具管理 ====================

    def get_vehicles(self) -> Dict[str, Dict]:
        """获取所有载具配置"""
        return self._config["vehicles"]

    def get_vehicle_names(self) -> List[str]:
        """获取所有载具名称列表"""
        return list(self._config["vehicles"].keys())

    def get_vehicle(self, name: str) -> Optional[Dict]:
        """获取指定载具配置"""
        return self._config["vehicles"].get(name)

    def add_vehicle(self, name: str) -> bool:
        """添加新载具"""
        if name in self._config["vehicles"]:
            return False
        self._config["vehicles"][name] = {
            "name": name,
            "tags": [],
            "ammo_types": {}
        }
        self.request_save()
        return True

    def remove_vehicle(self, name: str) -> bool:
        """删除载具"""
        if name not in self._config["vehicles"]:
            return False
        del self._config["vehicles"][name]

        # 如果当前载具被删除，重置当前状态
        if self._config["current_state"]["vehicle"] == name:
            self._config["current_state"]["vehicle"] = None
            self._config["current_state"]["ammo_type"] = None
            self._config["current_state"]["magnification_index"] = 0

        self.request_save()
        return True

    def rename_vehicle(self, old_name: str, new_name: str) -> bool:
        """重命名载具"""
        if old_name not in self._config["vehicles"] or new_name in self._config["vehicles"]:
            return False

        vehicle = self._config["vehicles"].pop(old_name)
        vehicle["name"] = new_name
        self._config["vehicles"][new_name] = vehicle

        # 更新当前状态
        if self._config["current_state"]["vehicle"] == old_name:
            self._config["current_state"]["vehicle"] = new_name

        self.request_save()
        return True

    def copy_vehicle(self, src_name: str, dst_name: str) -> bool:
        """复制载具配置（弹种、倍率、准星绑定、标签完整复制）"""
        import copy as _copy
        if src_name not in self._config["vehicles"] or dst_name in self._config["vehicles"]:
            return False
        src = self._config["vehicles"][src_name]
        new_vehicle = _copy.deepcopy(src)
        new_vehicle["name"] = dst_name
        self._config["vehicles"][dst_name] = new_vehicle
        self.request_save()
        return True

    # ==================== 标签管理 ====================

    def get_all_tags(self) -> List[str]:
        """获取全局标签库"""
        return list(self._config.get("tags", []))

    def add_tag(self, tag_name: str) -> bool:
        """创建新标签"""
        tag_name = tag_name.strip()
        if not tag_name or tag_name in self._config.get("tags", []):
            return False
        self._config.setdefault("tags", []).append(tag_name)
        self.request_save()
        return True

    def remove_tag(self, tag_name: str) -> bool:
        """删除标签（解绑所有载具的该标签，不删除载具）"""
        if tag_name not in self._config.get("tags", []):
            return False
        self._config["tags"].remove(tag_name)
        # 解绑所有载具的该标签
        for vehicle in self._config["vehicles"].values():
            if tag_name in vehicle.get("tags", []):
                vehicle["tags"].remove(tag_name)
        self.request_save()
        return True

    def rename_tag(self, old_name: str, new_name: str) -> bool:
        """重命名标签（同步更新所有载具的绑定）"""
        new_name = new_name.strip()
        if old_name not in self._config.get("tags", []) or not new_name:
            return False
        if new_name in self._config["tags"]:
            return False
        idx = self._config["tags"].index(old_name)
        self._config["tags"][idx] = new_name
        for vehicle in self._config["vehicles"].values():
            if old_name in vehicle.get("tags", []):
                vehicle["tags"] = [new_name if t == old_name else t for t in vehicle["tags"]]
        self.request_save()
        return True

    def get_vehicle_tags(self, vehicle_name: str) -> List[str]:
        """获取载具绑定的标签"""
        vehicle = self.get_vehicle(vehicle_name)
        if vehicle:
            return vehicle.get("tags", [])
        return []

    def set_vehicle_tags(self, vehicle_name: str, tags: List[str]):
        """设置载具标签（只能绑定全局标签库中存在的标签）"""
        vehicle = self.get_vehicle(vehicle_name)
        if vehicle:
            valid_tags = [t for t in tags if t in self._config.get("tags", [])]
            vehicle["tags"] = list(dict.fromkeys(valid_tags))  # 去重保序
            self.request_save()

    def get_vehicle_names_filtered(self, text: str = "", tag: str = "") -> List[str]:
        """按名称文本和标签筛选载具（AND 关系）"""
        text_lower = text.lower()
        result = []
        for name, vehicle in self._config["vehicles"].items():
            if text_lower and text_lower not in name.lower():
                continue
            if tag and tag not in vehicle.get("tags", []):
                continue
            result.append(name)
        return sorted(result)

    # ==================== 测距仪管理 ====================

    def is_rangefinder_enabled(self) -> bool:
        return self._config.get("rangefinder", {}).get("enabled", False)

    def set_rangefinder_enabled(self, enabled: bool):
        self._config.setdefault("rangefinder", {})["enabled"] = enabled
        self.request_save()

    def is_toggle_ui_enabled(self) -> bool:
        return self._config.get("rangefinder", {}).get("toggle_ui_enabled", True)

    def set_toggle_ui_enabled(self, enabled: bool):
        self._config.setdefault("rangefinder", {})["toggle_ui_enabled"] = enabled
        self.request_save()

    def get_toggle_ui_step_interval(self) -> int:
        """返回有/无UI切换流程各步骤间等待间隙(ms)，默认50"""
        return self._config.get("rangefinder", {}).get("toggle_ui_step_interval", 50)

    def set_toggle_ui_step_interval(self, ms: int):
        self._config.setdefault("rangefinder", {})["toggle_ui_step_interval"] = max(10, min(1000, int(ms)))
        self.request_save()

    def get_rangefinder_profiles(self) -> Dict[str, Dict]:
        return self._config.get("rangefinder", {}).get("profiles", {})

    def get_rangefinder_profile_names(self) -> List[str]:
        return list(self.get_rangefinder_profiles().keys())

    def get_rangefinder_profile(self, name: str) -> Dict:
        return self.get_rangefinder_profiles().get(name, {})

    def get_current_rangefinder_profile(self) -> str:
        return self._config.get("rangefinder", {}).get("current_profile", "")

    def set_current_rangefinder_profile(self, name: str):
        self._config.setdefault("rangefinder", {})["current_profile"] = name
        self.request_save()

    def add_rangefinder_profile(self, name: str, profile: Dict = None):
        if profile is None:
            profile = {
                "roi": {"x": 0, "y": 0, "w": 200, "h": 80},
                "roi2": {"x": 0, "y": 0, "w": 200, "h": 80, "enabled": False},
                "ui_button": {"x": 960, "y": 540},
                "display_pos": {"x": 100, "y": 100},
                "display_pos2": {"x": 400, "y": 100},
                "display_size": {"w": 300, "h": 80},
                "display_opacity": 1.0,
                "linked_vehicles": [],
                "toggle_steps": [
                    {"action": "wait", "ms": 50},
                    {"action": "press_key", "key": "esc"},
                    {"action": "wait", "ms": 30},
                    {"action": "click"},
                    {"action": "wait", "ms": 20},
                    {"action": "press_key", "key": "esc"},
                    {"action": "wait", "ms": 200},
                ],
            }
        self._config.setdefault("rangefinder", {}).setdefault("profiles", {})[name] = profile
        self.request_save()

    def update_rangefinder_profile(self, name: str, profile: Dict):
        profiles = self._config.setdefault("rangefinder", {}).setdefault("profiles", {})
        if name in profiles:
            profiles[name].update(profile)
            self.request_save()

    def delete_rangefinder_profile(self, name: str):
        profiles = self._config.get("rangefinder", {}).get("profiles", {})
        if name in profiles:
            del profiles[name]
            if self.get_current_rangefinder_profile() == name:
                self._config["rangefinder"]["current_profile"] = ""
            self.request_save()

    def rename_rangefinder_profile(self, old: str, new: str):
        profiles = self._config.get("rangefinder", {}).get("profiles", {})
        if old in profiles and new not in profiles:
            profiles[new] = profiles.pop(old)
            if self.get_current_rangefinder_profile() == old:
                self._config["rangefinder"]["current_profile"] = new
            self.request_save()

    def get_rangefinder_profile_linked_vehicles(self, name: str) -> List[str]:
        return self.get_rangefinder_profile(name).get("linked_vehicles", [])

    def set_rangefinder_profile_linked_vehicles(self, name: str, vehicles: List[str]):
        profile = self.get_rangefinder_profile(name)
        if profile:
            profile["linked_vehicles"] = list(dict.fromkeys(vehicles))
            self.request_save()

    def get_rangefinder_profile_effective_tags(self, name: str) -> List[str]:
        """从关联载具派生标签（所有关联载具标签的并集）"""
        tags = []
        for v in self.get_rangefinder_profile_linked_vehicles(name):
            for t in self.get_vehicle_tags(v):
                if t not in tags:
                    tags.append(t)
        return tags

    def get_rangefinder_profiles_filtered(self, text: str = "", tag: str = "") -> List[str]:
        text_lower = text.lower()
        result = []
        for name, profile in self.get_rangefinder_profiles().items():
            if text_lower and text_lower not in name.lower():
                # 也搜索关联载具名称
                linked = profile.get("linked_vehicles", [])
                if not any(text_lower in v.lower() for v in linked):
                    continue
            if tag:
                eff_tags = self.get_rangefinder_profile_effective_tags(name)
                if tag not in eff_tags:
                    continue
            result.append(name)
        return sorted(result)

    def get_rangefinder_profile_for_vehicle(self, vehicle_name: str) -> str:
        """查找关联到指定载具的测距仪配置名"""
        for name, profile in self.get_rangefinder_profiles().items():
            if vehicle_name in profile.get("linked_vehicles", []):
                return name
        return ""

    def get_rangefinder_hotkeys(self) -> Dict:
        return self._config.get("rangefinder", {}).get("hotkeys", {})

    def set_rangefinder_hotkey(self, action: str, key: str, trigger: str, slot: int = 1):
        hk = self._config.setdefault("rangefinder", {}).setdefault("hotkeys", {}).setdefault(action, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()

    # ==================== 建队宏 ====================

    def is_squad_macro_enabled(self) -> bool:
        return self._config.get("squad_macro", {}).get("enabled", False)

    def set_squad_macro_enabled(self, enabled: bool):
        self._config.setdefault("squad_macro", {})["enabled"] = enabled
        self.request_save()

    def get_squad_macro_hotkey(self) -> Dict:
        return self._config.get("squad_macro", {}).get("hotkey", {"key1": "", "trigger1": "keydown"})

    def set_squad_macro_hotkey(self, key: str, trigger: str = "keydown"):
        hk = self._config.setdefault("squad_macro", {}).setdefault("hotkey", {})
        hk["key1"] = key
        hk["trigger1"] = trigger
        self.request_save()

    def get_squad_macro_name(self) -> str:
        return self._config.get("squad_macro", {}).get("squad_name", "")

    def set_squad_macro_name(self, name: str):
        self._config.setdefault("squad_macro", {})["squad_name"] = name
        self.request_save()

    def is_squad_macro_locked(self) -> bool:
        return self._config.get("squad_macro", {}).get("locked", True)

    def set_squad_macro_locked(self, locked: bool):
        self._config.setdefault("squad_macro", {})["locked"] = locked
        self.request_save()

    def get_squad_macro_interval(self) -> int:
        sm = self._config.get("squad_macro") or {}
        return int(sm.get("interval_ms", 100))

    def set_squad_macro_interval(self, interval_ms: int):
        sm = self._config.setdefault("squad_macro", {})
        sm["interval_ms"] = max(50, int(interval_ms))
        self.request_save()

    # ==================== 弹种管理 ====================

    def get_ammo_types(self, vehicle_name: str) -> Dict[str, Dict]:
        """获取指定载具的所有弹种"""
        vehicle = self.get_vehicle(vehicle_name)
        if vehicle:
            return vehicle["ammo_types"]
        return {}

    def get_ammo_type_names(self, vehicle_name: str) -> List[str]:
        """获取指定载具的弹种名称列表"""
        return list(self.get_ammo_types(vehicle_name).keys())

    def add_ammo_type(self, vehicle_name: str, ammo_name: str) -> bool:
        """19.3: 添加弹种，按该载具内弹种序号预填数字键(1-9)，不覆盖已绑定。"""
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle or ammo_name in vehicle["ammo_types"]:
            return False

        vehicle["ammo_types"][ammo_name] = {
            "name": ammo_name,
            "magnifications": []
        }

        # 按当前载具内弹种序号预填（第N个弹种→数字N），超过9留空
        v_hks = self._config.setdefault("hotkeys", {}).setdefault("ammo_types", {}).setdefault(vehicle_name, {})
        existing_count = len([k for k in v_hks if k != ammo_name])
        digit = str(existing_count + 1) if existing_count < 9 else ""
        v_hks[ammo_name] = {
            "key1": digit, "trigger1": "keydown",
            "key2": "", "trigger2": "keydown"
        }

        self.request_save()
        return True

    def remove_ammo_type(self, vehicle_name: str, ammo_name: str) -> bool:
        """19.3: 删除弹种，同步删除对应载具下的热键"""
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle or ammo_name not in vehicle["ammo_types"]:
            return False

        del vehicle["ammo_types"][ammo_name]
        # 同步删除该载具下的弹种热键
        v_hks = self._config.get("hotkeys", {}).get("ammo_types", {}).get(vehicle_name, {})
        if ammo_name in v_hks:
            del v_hks[ammo_name]

        # 删除对应热键
        if ammo_name in self._config["hotkeys"]["ammo_types"]:
            del self._config["hotkeys"]["ammo_types"][ammo_name]

        # 如果当前弹种被删除，重置
        if (self._config["current_state"]["vehicle"] == vehicle_name and
                self._config["current_state"]["ammo_type"] == ammo_name):
            self._config["current_state"]["ammo_type"] = None
            self._config["current_state"]["magnification_index"] = 0

        self.request_save()
        return True

    def rename_ammo_type(self, vehicle_name: str, old_name: str, new_name: str) -> bool:
        """重命名弹种"""
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle or old_name not in vehicle["ammo_types"] or new_name in vehicle["ammo_types"]:
            return False

        ammo = vehicle["ammo_types"].pop(old_name)
        ammo["name"] = new_name
        vehicle["ammo_types"][new_name] = ammo

        # 同步重命名该载具下的热键
        v_hks = self._config.get("hotkeys", {}).get("ammo_types", {}).get(vehicle_name, {})
        if old_name in v_hks:
            v_hks[new_name] = v_hks.pop(old_name)

        # 更新当前状态
        if (self._config["current_state"]["vehicle"] == vehicle_name and
                self._config["current_state"]["ammo_type"] == old_name):
            self._config["current_state"]["ammo_type"] = new_name

        self.request_save()
        return True

    # ==================== 倍率管理 ====================

    def get_magnifications(self, vehicle_name: str, ammo_name: str) -> List[Dict]:
        """获取指定弹种的所有倍率"""
        ammo_types = self.get_ammo_types(vehicle_name)
        if ammo_name in ammo_types:
            return ammo_types[ammo_name]["magnifications"]
        return []

    def add_magnification(self, vehicle_name: str, ammo_name: str, label: str = "", crosshair_path: str = "") -> bool:
        """添加倍率"""
        ammo_types = self.get_ammo_types(vehicle_name)
        if ammo_name not in ammo_types:
            return False

        if not label:
            index = len(ammo_types[ammo_name]["magnifications"]) + 1
            label = f"倍率{index}"

        ammo_types[ammo_name]["magnifications"].append({
            "label": label,
            "crosshair": crosshair_path
        })

        self.request_save()
        return True

    def remove_magnification(self, vehicle_name: str, ammo_name: str, index: int) -> bool:
        """删除倍率"""
        magnifications = self.get_magnifications(vehicle_name, ammo_name)
        if index < 0 or index >= len(magnifications):
            return False

        magnifications.pop(index)

        # 如果当前倍率索引越界，调整
        if self._config["current_state"]["magnification_index"] >= len(magnifications):
            self._config["current_state"]["magnification_index"] = max(0, len(magnifications) - 1)

        self.request_save()
        return True

    def update_magnification(self, vehicle_name: str, ammo_name: str, index: int,
                             label: str = None, crosshair_path: str = None) -> bool:
        """更新倍率配置"""
        magnifications = self.get_magnifications(vehicle_name, ammo_name)
        if index < 0 or index >= len(magnifications):
            return False

        if label is not None:
            magnifications[index]["label"] = label
        if crosshair_path is not None:
            magnifications[index]["crosshair"] = crosshair_path

        self.request_save()
        return True

    def get_magnification_count(self, vehicle_name: str, ammo_name: str) -> int:
        """获取倍率数量"""
        return len(self.get_magnifications(vehicle_name, ammo_name))

    def unbind_crosshair(self, crosshair_name: str) -> int:
        """遍历所有载具/弹种/倍率，解绑指定准星图片，返回解绑数量"""
        count = 0
        for vehicle in self._config.get("vehicles", {}).values():
            for ammo in vehicle.get("ammo_types", {}).values():
                for mag in ammo.get("magnifications", []):
                    if mag.get("crosshair") == crosshair_name:
                        mag["crosshair"] = ""
                        count += 1
        if count > 0:
            self.request_save()
        return count

    # ==================== 热键管理 ====================

    def get_hotkey(self, action: str) -> Dict:
        """获取指定功能的热键配置（统一双键格式）"""
        return self._config["hotkeys"].get(action, {})

    def set_hotkey(self, action: str, key: str, trigger: str = "keydown", slot: int = 1):
        """设置热键（slot=1或2）"""
        if action not in self._config["hotkeys"]:
            self._config["hotkeys"][action] = {
                "key1": "", "trigger1": "keydown",
                "key2": "", "trigger2": "keydown"
            }
        slot_key = f"key{slot}"
        slot_trigger = f"trigger{slot}"
        self._config["hotkeys"][action][slot_key] = key
        self._config["hotkeys"][action][slot_trigger] = trigger
        self.request_save()

    def get_ammo_hotkey(self, vehicle_name: str, ammo_name: str) -> Dict:
        """19.3: 获取指定载具的弹种切换热键（按载具维度存储）"""
        return self._config["hotkeys"]["ammo_types"].get(vehicle_name, {}).get(ammo_name, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })

    def set_ammo_hotkey(self, vehicle_name: str, ammo_name: str, key: str, trigger: str = "keydown", slot: int = 1):
        """19.3: 设置指定载具的弹种切换热键（按载具维度存储）"""
        v_hks = self._config["hotkeys"]["ammo_types"].setdefault(vehicle_name, {})
        hk = v_hks.setdefault(ammo_name, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()

    def get_all_hotkeys(self) -> Dict:
        """获取所有热键配置"""
        return self._config["hotkeys"]

    # ==================== 当前状态 ====================

    def get_current_state(self) -> Dict:
        """获取当前运行状态"""
        return self._config["current_state"]

    def set_current_vehicle(self, vehicle_name: str):
        """设置当前载具"""
        if vehicle_name in self._config["vehicles"]:
            self._config["current_state"]["vehicle"] = vehicle_name

            # 自动选择第一个弹种
            ammo_names = self.get_ammo_type_names(vehicle_name)
            if ammo_names:
                self._config["current_state"]["ammo_type"] = ammo_names[0]
                self._config["current_state"]["magnification_index"] = 0
            else:
                self._config["current_state"]["ammo_type"] = None
                self._config["current_state"]["magnification_index"] = 0

            # 运行时状态，不立即写盘

    def set_current_ammo_type(self, ammo_name: str):
        """设置当前弹种（继承倍率索引，带越界保护）"""
        vehicle_name = self._config["current_state"]["vehicle"]
        if not vehicle_name:
            return

        ammo_types = self.get_ammo_types(vehicle_name)
        if ammo_name not in ammo_types:
            return

        self._config["current_state"]["ammo_type"] = ammo_name

        # 越界保护：如果当前倍率索引大于目标弹种的最大索引，使用最后一级
        mag_count = self.get_magnification_count(vehicle_name, ammo_name)
        if mag_count > 0:
            current_idx = self._config["current_state"]["magnification_index"]
            if current_idx >= mag_count:
                self._config["current_state"]["magnification_index"] = mag_count - 1
        else:
            self._config["current_state"]["magnification_index"] = 0

        # 运行时状态，不立即写盘

    def set_current_magnification_index(self, index: int):
        """设置当前倍率索引"""
        vehicle_name = self._config["current_state"]["vehicle"]
        ammo_name = self._config["current_state"]["ammo_type"]

        if not vehicle_name or not ammo_name:
            return

        mag_count = self.get_magnification_count(vehicle_name, ammo_name)
        if mag_count > 0:
            self._config["current_state"]["magnification_index"] = index % mag_count
            # 运行时状态，不立即写盘

    def cycle_magnification(self):
        """循环切换倍率"""
        vehicle_name = self._config["current_state"]["vehicle"]
        ammo_name = self._config["current_state"]["ammo_type"]

        if not vehicle_name or not ammo_name:
            return

        mag_count = self.get_magnification_count(vehicle_name, ammo_name)
        if mag_count > 0:
            current = self._config["current_state"]["magnification_index"]
            self._config["current_state"]["magnification_index"] = (current + 1) % mag_count
            # 运行时状态，不立即写盘

    def get_current_crosshair(self) -> Optional[str]:
        """获取当前准星图片路径"""
        state = self._config["current_state"]
        vehicle_name = state["vehicle"]
        ammo_name = state["ammo_type"]
        mag_index = state["magnification_index"]

        if not vehicle_name or not ammo_name:
            return None

        magnifications = self.get_magnifications(vehicle_name, ammo_name)
        if 0 <= mag_index < len(magnifications):
            crosshair = magnifications[mag_index].get("crosshair", "")
            if crosshair:
                return str(self.resources_dir / crosshair)
        return None

    # ==================== 主题 ====================

    def get_theme(self) -> str:
        return self._config.get("theme", "dark")

    def set_theme(self, theme: str):
        self._config["theme"] = theme
        self.request_save()

    # ==================== 角度仪 ====================

    def _migrate_ammo_hotkeys_vehicle_scope(self):
        """19.3: 弹种热键从全局 {弹种名: hk} 迁移为按载具 {载具名: {弹种名: hk}}。
        旧格式遍历所有载具，把全局弹种热键复制到各载具下；迁移后删除旧全局键。
        同时批量重绑：每辆载具的弹种按序号从1开始预填数字键。"""
        ammo_hks = self._config.get("hotkeys", {}).get("ammo_types", {})
        if not ammo_hks:
            return
        # 判断是否已是新格式（值是dict且key是载具名）
        sample = next(iter(ammo_hks.values()), None)
        if isinstance(sample, dict) and "key1" not in sample:
            return  # 已是载具维度
        # 旧格式：{弹种名: {key1,...}} → 新格式 {载具名: {弹种名: {key1,...}}}
        new_ammo_hks = {}
        vehicles = self._config.get("vehicles", {})
        for v_name in vehicles:
            new_ammo_hks[v_name] = {}
            v_ammos = vehicles[v_name].get("ammo_types", {})
            for idx, a_name in enumerate(v_ammos.keys()):
                # 优先用旧全局绑定，否则按序号预填
                old_hk = ammo_hks.get(a_name, {})
                if old_hk.get("key1"):
                    new_ammo_hks[v_name][a_name] = dict(old_hk)
                else:
                    digit = str(idx + 1) if idx < 9 else ""
                    new_ammo_hks[v_name][a_name] = {
                        "key1": digit, "trigger1": "keydown",
                        "key2": "", "trigger2": "keydown"
                    }
        self._config["hotkeys"]["ammo_types"] = new_ammo_hks
        self.request_save()
        print("[ConfigManager] 配置迁移: 弹种热键已改为按载具维度存储")

    def _ensure_angle_meter_defaults(self):
        """D4: 确保 angle_meter 配置段存在（旧 config.json 可能没有）。
        仅在内存中补全默认值，不触发写盘；用户首次修改时才会持久化。
        R1: 默认值统一走 _default_angle_meter_segment / _default_angle_meter_profile 工厂。"""
        am = self._config.get("angle_meter")
        if am is None:
            self._config["angle_meter"] = _default_angle_meter_segment()
        elif not am.get("profiles"):
            am["profiles"] = {"默认配置": _default_angle_meter_profile()}

    def is_angle_meter_enabled(self) -> bool:
        return self._config.get("angle_meter", {}).get("enabled", False)

    def set_angle_meter_enabled(self, enabled: bool):
        self._config.setdefault("angle_meter", {})["enabled"] = enabled
        self.request_save()

    # --- 配置列表（武器站级，一个配置可关联多个载具）---

    def get_angle_meter_profiles(self) -> Dict[str, Dict]:
        # 纯读取，无写副作用。默认值由最小骨架 + _ensure_angle_meter_defaults() 在初始化时确保（内存中，不写盘）。
        return self._config.get("angle_meter", {}).get("profiles", {})

    def get_angle_meter_profile(self, name: str) -> Dict:
        return self.get_angle_meter_profiles().get(name, _default_angle_meter_profile())

    def set_angle_meter_profile(self, name: str, profile: Dict):
        self._config.setdefault("angle_meter", {}).setdefault("profiles", {})[name] = profile
        self.request_save()

    def add_angle_meter_profile(self, name: str):
        profiles = self.get_angle_meter_profiles()
        if name not in profiles:
            profiles[name] = _default_angle_meter_profile()
            self.request_save()

    def rename_angle_meter_profile(self, old_name: str, new_name: str):
        profiles = self.get_angle_meter_profiles()
        if old_name in profiles and new_name not in profiles:
            profiles[new_name] = profiles.pop(old_name)
            if self.get_current_angle_meter_profile() == old_name:
                self.set_current_angle_meter_profile(new_name)
            self.request_save()

    def delete_angle_meter_profile(self, name: str):
        profiles = self.get_angle_meter_profiles()
        if name in profiles and len(profiles) > 1:
            del profiles[name]
            if self.get_current_angle_meter_profile() == name:
                self.set_current_angle_meter_profile(next(iter(profiles)))
            self.request_save()

    def get_current_angle_meter_profile(self) -> str:
        return self._config.get("angle_meter", {}).get("current_profile", "默认配置")

    def set_current_angle_meter_profile(self, name: str):
        self._config.setdefault("angle_meter", {})["current_profile"] = name
        self.request_save()

    def get_angle_meter_profile_for_vehicle(self, vehicle: str) -> str:
        """根据载具名找到关联的配置名，找不到返回默认配置"""
        for pname, pdata in self.get_angle_meter_profiles().items():
            if vehicle in pdata.get("linked_vehicles", []):
                return pname
        return "默认配置"

    def get_angle_meter_profile_linked_vehicles(self, name: str) -> list:
        """返回角度仪配置关联的载具列表"""
        profile = self.get_angle_meter_profile(name)
        return profile.get("linked_vehicles", []) if profile else []

    def get_angle_meter_profile_effective_tags(self, name: str) -> list:
        """从关联载具派生标签（所有关联载具标签的并集）"""
        tags = []
        for v in self.get_angle_meter_profile_linked_vehicles(name):
            for t in self.get_vehicle_tags(v):
                if t not in tags:
                    tags.append(t)
        return tags

    # --- 热键（单键：toggle=开始/停止, pause=暂离, calibrate=校准确认, reset=归零）---

    def get_angle_meter_hotkeys(self) -> Dict:
        # 统一为双键结构（key1/trigger1/key2/trigger2），与全局热键一致；角度仪 UI 只用 key1
        return self._config.get("angle_meter", {}).get("hotkeys", {
            "toggle": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "pause": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "calibrate": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "reset": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
        })

    def set_angle_meter_hotkey(self, action: str, key: str, trigger: str = "keydown", slot: int = 1):
        # 统一为双键结构，slot=1 或 2；角度仪 UI 只用 slot=1
        hk = self._config.setdefault("angle_meter", {}).setdefault("hotkeys", {}).setdefault(action, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()
