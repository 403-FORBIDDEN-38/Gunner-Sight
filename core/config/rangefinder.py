import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

class ConfigRangefinderMixin:
    """rangefinder 配置管理 mixin"""

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

    # === 距离测算模块（FEATURE-3）===

