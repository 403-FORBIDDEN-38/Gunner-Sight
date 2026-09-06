import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

class ConfigVehicleMixin:
    """vehicle 配置管理 mixin"""

    def get_vehicles(self) -> Dict[str, Dict]:
        """获取所有载具配置"""
        return self._config["vehicles"]


    def get_vehicle_names(self) -> List[str]:
        """获取所有载具名称列表"""
        return list(self._config["vehicles"].keys())


    def get_vehicle(self, name: str) -> Optional[Dict]:
        """获取指定载具配置"""
        return self._config["vehicles"].get(name)

    # === 载具缩放偏移 ===


    def get_vehicle_overlay(self, vehicle_name: str) -> Dict:
        """获取载具缩放偏移配置，不存在时返回默认值"""
        vehicle = self._config["vehicles"].get(vehicle_name)
        if vehicle and "overlay" in vehicle:
            return vehicle["overlay"]
        return self._default_vehicle_overlay()


    def set_vehicle_overlay(self, vehicle_name: str, scale: float, offset_x: int, offset_y: int, opacity=None):
        """设置载具缩放偏移配置，防抖保存。opacity=None保留当前值（避免现有调用点重置透明度）"""
        vehicle = self._config["vehicles"].get(vehicle_name)
        if not vehicle:
            return
        current_opacity = vehicle.get("overlay", {}).get("opacity", 1.0)
        if opacity is not None:
            current_opacity = max(0.1, min(1.0, float(opacity)))
        vehicle["overlay"] = {
            "scale": max(1.0, min(1000.0, float(scale))),
            "offset_x": int(offset_x),
            "offset_y": int(offset_y),
            "opacity": current_opacity
        }
        self.request_save()


    def reset_vehicle_overlay(self, vehicle_name: str):
        """重置载具缩放偏移为默认值"""
        vehicle = self._config["vehicles"].get(vehicle_name)
        if not vehicle:
            return
        vehicle["overlay"] = self._default_vehicle_overlay()
        self.request_save()

    # === 倍率缩放偏移开关 ===


    def get_magnification_overlay_mode(self, vehicle_name: str, ammo_name: str, index: int) -> bool:
        """获取倍率缩放偏移模式（true=载具，false=全局）"""
        mags = self.get_magnifications(vehicle_name, ammo_name)
        if 0 <= index < len(mags):
            return mags[index].get("use_vehicle_overlay", False)
        return False


    def set_magnification_overlay_mode(self, vehicle_name: str, ammo_name: str, index: int, use_vehicle: bool):
        """设置倍率缩放偏移模式，防抖保存"""
        mags = self.get_magnifications(vehicle_name, ammo_name)
        if 0 <= index < len(mags):
            mags[index]["use_vehicle_overlay"] = bool(use_vehicle)
            self.request_save()

    # === 核心：有效缩放偏移（二选一判断唯一入口） ===


    def get_effective_overlay(self, vehicle_name: str, ammo_name: str, index: int) -> Dict:
        """获取当前倍率的有效缩放偏移配置。
        二选一判断逻辑只在此方法中做一次，overlay 渲染和 UI 预览都调用此方法。"""
        use_vehicle = self.get_magnification_overlay_mode(vehicle_name, ammo_name, index)
        if use_vehicle:
            return self.get_vehicle_overlay(vehicle_name)
        return {
            "scale": self.get_global_scale(),
            "offset_x": self.get_global_offset_x(),
            "offset_y": self.get_global_offset_y(),
            "opacity": self.get_overlay_opacity()
        }

    @staticmethod

    def _default_vehicle_overlay() -> Dict:
        """载具缩放偏移默认值（单一工厂方法，不散落多处）"""
        return {"scale": 100.0, "offset_x": 0, "offset_y": 0, "opacity": 1.0}


    def add_vehicle(self, name: str) -> bool:
        """添加新载具"""
        if name in self._config["vehicles"]:
            return False
        self._config["vehicles"][name] = {
            "name": name,
            "tags": [],
            "ammo_types": {},
            "overlay": self._default_vehicle_overlay()
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
        """删除倍率，删除后自动重新编号（倍率1、倍率2...无断层）"""
        magnifications = self.get_magnifications(vehicle_name, ammo_name)
        if index < 0 or index >= len(magnifications):
            return False

        magnifications.pop(index)

        # 自动重新编号，消除断层
        for i, mag in enumerate(magnifications):
            mag["label"] = f"倍率{i+1}"

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

