import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

from core.config.base import _default_angle_meter_segment, _default_angle_meter_profile

class ConfigAngleMeterMixin:
    """angle_meter 配置管理 mixin"""

    def _ensure_angle_meter_defaults(self):
        """确保 angle_meter 配置段存在（旧 config.json 可能没有）。
        仅在内存中补全默认值，不触发写盘；用户首次修改时才会持久化。
        只在 angle_meter 段不存在时创建默认 segment，用户删除所有配置是合法行为，不自动恢复。"""
        am = self._config.get("angle_meter")
        if am is None:
            self._config["angle_meter"] = _default_angle_meter_segment()


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
        if name in profiles:
            del profiles[name]
            if self.get_current_angle_meter_profile() == name:
                # 删除后如果还有配置，选第一个；否则清空当前选择
                remaining = list(profiles.keys())
                if remaining:
                    self.set_current_angle_meter_profile(remaining[0])
                else:
                    self._config.setdefault("angle_meter", {})["current_profile"] = ""
            self.request_save()


    def get_current_angle_meter_profile(self) -> str:
        return self._config.get("angle_meter", {}).get("current_profile", "")


    def set_current_angle_meter_profile(self, name: str):
        self._config.setdefault("angle_meter", {})["current_profile"] = name
        self.request_save()


    def get_angle_meter_profile_for_vehicle(self, vehicle: str) -> str:
        """根据载具名找到关联的配置名，找不到返回空字符串（空房子原则）"""
        for pname, pdata in self.get_angle_meter_profiles().items():
            if vehicle in pdata.get("linked_vehicles", []):
                return pname
        return ""


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

    # === 全局校准 ===

    def get_angle_meter_calibration_points(self, name: str, point_count: int = None):
        """FEATURE-1补充: 获取指定点数的校准曲线，None=未校准。
        point_count为None时用active_calibration_point_count。"""
        profile = self.get_angle_meter_profile(name)
        if point_count is None:
            point_count = profile.get("active_calibration_point_count", 7)
        return profile.get("calibrations", {}).get(str(point_count))


    def set_angle_meter_calibration_points(self, name: str, points, point_count: int = 7):
        """FEATURE-1补充: 保存指定点数的校准曲线，不覆盖其他方案"""
        profile = self.get_angle_meter_profile(name)
        profile.setdefault("calibrations", {})[str(point_count)] = points
        profile["active_calibration_point_count"] = point_count
        self.set_angle_meter_profile(name, profile)


    def get_active_calibration_point_count(self, name: str) -> int:
        return self.get_angle_meter_profile(name).get("active_calibration_point_count", 7)


    def set_active_calibration_point_count(self, name: str, count: int):
        profile = self.get_angle_meter_profile(name)
        profile["active_calibration_point_count"] = count
        self.set_angle_meter_profile(name, profile)


    def get_all_calibration_status(self, name: str) -> dict:
        """返回各点数方案的校准状态: {3: bool, 5: bool, 7: bool, 9: bool, 11: bool}"""
        cals = self.get_angle_meter_profile(name).get("calibrations", {})
        return {c: bool(cals.get(str(c))) for c in (3, 5, 7, 9, 11)}


    def clear_all_calibrations(self, name: str):
        """FEATURE-1补充: 清空该载具所有精度方案的校准数据（范围变更时调用）"""
        profile = self.get_angle_meter_profile(name)
        profile["calibrations"] = {}
        self.set_angle_meter_profile(name, profile)


    def get_effective_angle_meter_calibration(self, name: str):
        """FEATURE-1补充: 返回active方案的校准曲线，无全局兜底"""
        profile = self.get_angle_meter_profile(name)
        count = profile.get("active_calibration_point_count", 7)
        return profile.get("calibrations", {}).get(str(count))


    def get_angle_meter_hotkeys(self) -> Dict:
        # 统一为双键结构（key1/trigger1/key2/trigger2），与全局热键一致；角度仪 UI 只用 key1
        return self._config.get("angle_meter", {}).get("hotkeys", {
            "toggle": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "pause": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "calibrate": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "reset": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "up": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "down": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
        })


    def set_angle_meter_hotkey(self, action: str, key: str, trigger: str = "keydown", slot: int = 1):
        # 统一为双键结构，slot=1 或 2；角度仪 UI 只用 slot=1
        hk = self._config.setdefault("angle_meter", {}).setdefault("hotkeys", {}).setdefault(action, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()

    # --- 吉祥物配置 ---
