
class ConfigVehicleMixin:
    """vehicle 配置管理 mixin

    数据结构（v2 倍率公共化 + 弹种UI条件叠加）：
    载具级:
      magnifications: [{"label": "1x"}, ...]  公共倍率列表
    弹种级:
      ui: "路径"  弹种级 UI 叠加层（2K全屏整图，可选，缺失=未绑定）
      crosshairs: {"label": {"path": "xxx.png", "use_vehicle_overlay": False, "overlay_ammo_ui": False}}
    """

    # ==================== 载具基础 ====================

    def get_vehicles(self) -> dict[str, dict]:
        return self._config["vehicles"]

    def get_vehicle_names(self) -> list[str]:
        return list(self._config["vehicles"].keys())

    def get_vehicle(self, name: str) -> dict | None:
        return self._config["vehicles"].get(name)

    # ==================== 载具缩放偏移 ====================

    def get_vehicle_overlay(self, vehicle_name: str) -> dict:
        vehicle = self._config["vehicles"].get(vehicle_name)
        if vehicle and "overlay" in vehicle:
            return vehicle["overlay"]
        return self._default_vehicle_overlay()

    def set_vehicle_overlay(self, vehicle_name: str, scale: float, offset_x: int, offset_y: int, opacity=None):
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
        vehicle = self._config["vehicles"].get(vehicle_name)
        if not vehicle:
            return
        vehicle["overlay"] = self._default_vehicle_overlay()
        self.request_save()

    # ==================== 倍率 overlay 模式（读 crosshairs dict） ====================

    def get_magnification_overlay_mode(self, vehicle_name: str, ammo_name: str, index: int) -> bool:
        """获取倍率缩放偏移模式（true=载具，false=全局）。读 crosshairs dict。"""
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return False
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.get(label, {})
        return entry.get("use_vehicle_overlay", False)

    def set_magnification_overlay_mode(self, vehicle_name: str, ammo_name: str, index: int, use_vehicle: bool):
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.setdefault(label, {"path": "", "use_vehicle_overlay": False, "overlay_ammo_ui": False})
        entry["use_vehicle_overlay"] = bool(use_vehicle)
        self.request_save()

    # ==================== 有效缩放偏移（二选一唯一入口） ====================

    def get_effective_overlay(self, vehicle_name: str, ammo_name: str, index: int) -> dict:
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
    def _default_vehicle_overlay() -> dict:
        return {"scale": 100.0, "offset_x": 0, "offset_y": 0, "opacity": 1.0}

    # ==================== 载具增删改 ====================

    def add_vehicle(self, name: str) -> bool:
        if name in self._config["vehicles"]:
            return False
        self._config["vehicles"][name] = {
            "name": name,
            "tags": [],
            "ammo_types": {},
            "magnifications": [],
            "overlay": self._default_vehicle_overlay()
        }
        self.request_save()
        return True

    def remove_vehicle(self, name: str) -> bool:
        if name not in self._config["vehicles"]:
            return False
        del self._config["vehicles"][name]
        self._config.get("hotkeys", {}).get("ammo_types", {}).pop(name, None)
        # 清理角度仪配置里对本载具的引用
        profiles = self._config.get("angle_meter", {}).get("profiles", {})
        for profile in profiles.values():
            linked = profile.get("linked_vehicles", [])
            if name in linked:
                linked.remove(name)
        # current_state 的更新由 state_machine 负责，本方法只做业务
        self.request_save()
        return True

    def rename_vehicle(self, old_name: str, new_name: str) -> bool:
        if old_name not in self._config["vehicles"] or new_name in self._config["vehicles"]:
            return False
        vehicle = self._config["vehicles"].pop(old_name)
        vehicle["name"] = new_name
        self._config["vehicles"][new_name] = vehicle
        ammo_hks = self._config.get("hotkeys", {}).get("ammo_types", {})
        if old_name in ammo_hks:
            ammo_hks[new_name] = ammo_hks.pop(old_name)
        # current_state 的更新由 state_machine 负责，本方法只做业务
        self.request_save()
        return True

    def copy_vehicle(self, src_name: str, dst_name: str) -> bool:
        import copy as _copy
        if src_name not in self._config["vehicles"] or dst_name in self._config["vehicles"]:
            return False
        src = self._config["vehicles"][src_name]
        new_vehicle = _copy.deepcopy(src)
        new_vehicle["name"] = dst_name
        self._config["vehicles"][dst_name] = new_vehicle
        src_hks = self._config.get("hotkeys", {}).get("ammo_types", {}).get(src_name)
        if src_hks is not None:
            self._config.setdefault("hotkeys", {}).setdefault("ammo_types", {})[dst_name] = _copy.deepcopy(src_hks)
        self.request_save()
        return True

    # ==================== 标签管理 ====================

    def get_all_tags(self) -> list[str]:
        return list(self._config.get("tags", []))

    def add_tag(self, tag_name: str) -> bool:
        tag_name = tag_name.strip()
        if not tag_name or tag_name in self._config.get("tags", []):
            return False
        self._config.setdefault("tags", []).append(tag_name)
        self.request_save()
        return True

    def remove_tag(self, tag_name: str) -> bool:
        if tag_name not in self._config.get("tags", []):
            return False
        self._config["tags"].remove(tag_name)
        for vehicle in self._config["vehicles"].values():
            if tag_name in vehicle.get("tags", []):
                vehicle["tags"].remove(tag_name)
        self.request_save()
        return True

    def reorder_tags(self, new_order: list[str]) -> bool:
        current = self._config.get("tags", [])
        if sorted(new_order) != sorted(current):
            return False
        self._config["tags"] = list(new_order)
        self.request_save()
        return True

    def rename_tag(self, old_name: str, new_name: str) -> bool:
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

    def get_vehicle_tags(self, vehicle_name: str) -> list[str]:
        vehicle = self.get_vehicle(vehicle_name)
        if vehicle:
            return vehicle.get("tags", [])
        return []

    def set_vehicle_tags(self, vehicle_name: str, tags: list[str]):
        vehicle = self.get_vehicle(vehicle_name)
        if vehicle:
            valid_tags = [t for t in tags if t in self._config.get("tags", [])]
            vehicle["tags"] = list(dict.fromkeys(valid_tags))
            self.request_save()

    def get_vehicle_names_filtered(self, text: str = "", tag: str = "") -> list[str]:
        text_lower = text.lower()
        result = []
        for name, vehicle in self._config["vehicles"].items():
            if text_lower and text_lower not in name.lower():
                continue
            if tag and tag not in vehicle.get("tags", []):
                continue
            result.append(name)
        return sorted(result)

    # ==================== 弹种管理 ====================

    def get_ammo_types(self, vehicle_name: str) -> dict[str, dict]:
        vehicle = self.get_vehicle(vehicle_name)
        if vehicle:
            return vehicle["ammo_types"]
        return {}

    def get_ammo_type_names(self, vehicle_name: str) -> list[str]:
        return list(self.get_ammo_types(vehicle_name).keys())

    def add_ammo_type(self, vehicle_name: str, ammo_name: str) -> bool:
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle or ammo_name in vehicle["ammo_types"]:
            return False
        # 新弹种的 crosshairs 初始化为空 dict（倍率列表是载具级公共的）
        vehicle["ammo_types"][ammo_name] = {
            "name": ammo_name,
            "crosshairs": {}
        }
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
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle or ammo_name not in vehicle["ammo_types"]:
            return False
        del vehicle["ammo_types"][ammo_name]
        v_hks = self._config.get("hotkeys", {}).get("ammo_types", {}).get(vehicle_name, {})
        if ammo_name in v_hks:
            del v_hks[ammo_name]
        # current_state 的更新由 state_machine 负责，本方法只做业务
        self.request_save()
        return True

    def rename_ammo_type(self, vehicle_name: str, old_name: str, new_name: str) -> bool:
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle or old_name not in vehicle["ammo_types"] or new_name in vehicle["ammo_types"]:
            return False
        ammo = vehicle["ammo_types"].pop(old_name)
        ammo["name"] = new_name
        vehicle["ammo_types"][new_name] = ammo
        v_hks = self._config.get("hotkeys", {}).get("ammo_types", {}).get(vehicle_name, {})
        if old_name in v_hks:
            v_hks[new_name] = v_hks.pop(old_name)
        # current_state 的更新由 state_machine 负责，本方法只做业务
        self.request_save()
        return True

    # ==================== 倍率管理（载具级公共） ====================

    def get_magnifications(self, vehicle_name: str) -> list[dict]:
        """获取载具级公共倍率列表 [{"label": "1x"}, ...]"""
        vehicle = self.get_vehicle(vehicle_name)
        if vehicle:
            return vehicle.get("magnifications", [])
        return []

    def get_magnification_count(self, vehicle_name: str) -> int:
        return len(self.get_magnifications(vehicle_name))

    def add_magnification(self, vehicle_name: str, label: str = "") -> bool:
        """添加倍率（载具级公共，所有弹种共享）。"""
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle:
            return False
        mags = vehicle.setdefault("magnifications", [])
        if not label:
            label = f"倍率{len(mags) + 1}"
        mags.append({"label": label})
        # 给所有弹种的 crosshairs 加一个空条目
        for ammo in vehicle.get("ammo_types", {}).values():
            crosshairs = ammo.setdefault("crosshairs", {})
            if label not in crosshairs:
                crosshairs[label] = {"path": "", "use_vehicle_overlay": False, "overlay_ammo_ui": False}
        self.request_save()
        return True

    def remove_magnification(self, vehicle_name: str, index: int) -> bool:
        """删除倍率（载具级公共，从所有弹种的 crosshairs 中移除）。"""
        vehicle = self.get_vehicle(vehicle_name)
        if not vehicle:
            return False
        mags = vehicle.get("magnifications", [])
        if index < 0 or index >= len(mags):
            return False
        removed = mags.pop(index)
        removed_label = removed.get("label", "")
        # 从所有弹种的 crosshairs 中移除
        for ammo in vehicle.get("ammo_types", {}).values():
            crosshairs = ammo.get("crosshairs", {})
            crosshairs.pop(removed_label, None)
        # 重新编号 label（倍率1、倍率2...）
        for i, mag in enumerate(mags):
            mag["label"] = f"倍率{i + 1}"
        # 同步更新所有弹种 crosshairs 的 key
        for ammo in vehicle.get("ammo_types", {}).values():
            crosshairs = ammo.get("crosshairs", {})
            new_crosshairs = {}
            for i, mag in enumerate(mags):
                # 找到对应的旧 key
                matched = None
                for k in crosshairs:
                    if k == mag["label"] or (i < index and k == mag["label"]) or (i >= index and k == f"倍率{i+2}"):
                        matched = k
                        break
                if matched is not None:
                    new_crosshairs[mag["label"]] = crosshairs[matched]
                else:
                    new_crosshairs[mag["label"]] = {"path": "", "use_vehicle_overlay": False, "overlay_ammo_ui": False}
            ammo["crosshairs"] = new_crosshairs
        # current_state 的更新由 state_machine 负责，本方法只做业务
        self.request_save()
        return True

    def update_magnification(self, vehicle_name: str, index: int, label: str | None = None) -> bool:
        """更新倍率配置（载具级公共）。"""
        mags = self.get_magnifications(vehicle_name)
        if index < 0 or index >= len(mags):
            return False
        old_label = mags[index].get("label", "")
        if label is not None and label != old_label:
            mags[index]["label"] = label
            # 同步更新所有弹种 crosshairs 的 key
            vehicle = self.get_vehicle(vehicle_name)
            for ammo in vehicle.get("ammo_types", {}).values():
                crosshairs = ammo.get("crosshairs", {})
                if old_label in crosshairs:
                    crosshairs[label] = crosshairs.pop(old_label)
        self.request_save()
        return True

    # ==================== crosshair 绑定（弹种级，读 crosshairs dict） ====================

    def get_crosshair_path(self, vehicle_name: str, ammo_name: str, index: int) -> str:
        """获取指定倍率的 crosshair 路径。"""
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return ""
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.get(label, {})
        return entry.get("path", "")

    def set_crosshair_path(self, vehicle_name: str, ammo_name: str, index: int, path: str) -> bool:
        """设置指定倍率的 crosshair 路径。"""
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return False
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.setdefault(label, {"path": "", "use_vehicle_overlay": False, "overlay_ammo_ui": False})
        entry["path"] = path
        self.request_save()
        return True

    # ==================== 弹种 UI 绑定 ====================

    def get_ammo_ui(self, vehicle_name: str, ammo_name: str) -> str:
        ammo = self.get_ammo_types(vehicle_name).get(ammo_name, {})
        return ammo.get("ui", "")

    def set_ammo_ui(self, vehicle_name: str, ammo_name: str, path: str):
        ammo = self.get_ammo_types(vehicle_name).get(ammo_name)
        if ammo:
            ammo["ui"] = path
            self.request_save()

    # ==================== 载具 UI 绑定 ====================

    def get_vehicle_ui(self, vehicle_name: str) -> str:
        vehicle = self._config["vehicles"].get(vehicle_name, {})
        return vehicle.get("base_ui", "")

    def set_vehicle_ui(self, vehicle_name: str, path: str):
        vehicle = self._config["vehicles"].get(vehicle_name)
        if vehicle:
            vehicle["base_ui"] = path
            self.request_save()

    # ==================== overlay_ammo_ui（倍率级开关） ====================

    def get_overlay_ammo_ui(self, vehicle_name: str, ammo_name: str, index: int) -> bool:
        """获取该倍率是否叠加弹种 UI。"""
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return False
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.get(label, {})
        return entry.get("overlay_ammo_ui", False)

    def set_overlay_ammo_ui(self, vehicle_name: str, ammo_name: str, index: int, enabled: bool):
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.setdefault(label, {"path": "", "use_vehicle_overlay": False, "overlay_ammo_ui": False, "overlay_vehicle_ui": False})
        entry["overlay_ammo_ui"] = bool(enabled)
        self.request_save()

    # ==================== overlay_vehicle_ui（倍率级开关） ====================

    def get_overlay_vehicle_ui(self, vehicle_name: str, ammo_name: str, index: int) -> bool:
        """获取该倍率是否叠加载具 UI。"""
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return False
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.get(label, {})
        return entry.get("overlay_vehicle_ui", False)

    def set_overlay_vehicle_ui(self, vehicle_name: str, ammo_name: str, index: int, enabled: bool):
        label = self._mag_label_at(vehicle_name, index)
        if label is None:
            return
        crosshairs = self._get_crosshairs_dict(vehicle_name, ammo_name)
        entry = crosshairs.setdefault(label, {"path": "", "use_vehicle_overlay": False, "overlay_ammo_ui": False, "overlay_vehicle_ui": False})
        entry["overlay_vehicle_ui"] = bool(enabled)
        self.request_save()

    # ==================== 内部辅助 ====================

    def _mag_label_at(self, vehicle_name: str, index: int) -> str | None:
        mags = self.get_magnifications(vehicle_name)
        if 0 <= index < len(mags):
            return mags[index].get("label")
        return None

    def _get_crosshairs_dict(self, vehicle_name: str, ammo_name: str) -> dict:
        ammo = self.get_ammo_types(vehicle_name).get(ammo_name)
        if ammo is None:
            return {}
        return ammo.setdefault("crosshairs", {})

    # ==================== 弹种热键 ====================

    def get_ammo_hotkey(self, vehicle_name: str, ammo_name: str) -> dict:
        return self._config["hotkeys"]["ammo_types"].get(vehicle_name, {}).get(ammo_name, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })

    def set_ammo_hotkey(self, vehicle_name: str, ammo_name: str, key: str, trigger: str = "keydown", slot: int = 1):
        v_hks = self._config["hotkeys"]["ammo_types"].setdefault(vehicle_name, {})
        hk = v_hks.setdefault(ammo_name, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()
