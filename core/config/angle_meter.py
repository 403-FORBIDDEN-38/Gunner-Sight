
from core.config.base import _default_angle_meter_profile, _default_angle_meter_segment
from core.firing_table import BallisticProfile
from core.firing_table import is_extrapolation as _ft_is_extrap


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

    def get_angle_meter_overlay_pos(self) -> tuple:
        d = self._config.get("angle_meter", {})
        return d.get("overlay_x", None), d.get("overlay_y", None)

    def set_angle_meter_overlay_pos(self, x: int, y: int):
        d = self._config.setdefault("angle_meter", {})
        d["overlay_x"] = x
        d["overlay_y"] = y
        self.request_save()

    # --- 配置列表（武器站级，一个配置可关联多个载具）---


    def get_angle_meter_profiles(self) -> dict[str, dict]:
        # 纯读取，无写副作用。默认值由最小骨架 + _ensure_angle_meter_defaults() 在初始化时确保（内存中，不写盘）。
        return self._config.get("angle_meter", {}).get("profiles", {})


    def get_angle_meter_profile(self, name: str) -> dict:
        return self.get_angle_meter_profiles().get(name, _default_angle_meter_profile())


    def set_angle_meter_profile(self, name: str, profile: dict):
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

    def get_firing_table(self, name: str) -> list[dict]:
        """获取射表数据：[{"angle": float, "distance": float}, ...]"""
        profile = self.get_angle_meter_profile(name)
        return profile.get("firing_table", []) if profile else []

    def set_firing_table(self, name: str, table: list[dict]):
        """保存射表数据"""
        profiles = self.get_angle_meter_profiles()
        if name in profiles:
            profiles[name]["firing_table"] = table
            self.request_save()

    def query_firing_distance(self, name: str, angle: float) -> float | None:
        """根据角度查射表，PCHIP 插值+外推。超出外推范围返回 None。

        M3：profile 按 name 缓存（table 引用 is 判有效）。本函数挂在
        angle_changed 上（鼠标每次移动触发），不缓存则每次角度更新都要
        重建 2 次完整 profile（解析+排序+PCHIP 求导）。
        """
        table = self.get_firing_table(name)
        if not table:
            return None
        entry = self._firing_profile_cache.get(name)
        if entry is None or entry[0] is not table:
            profile = BallisticProfile.from_config(table)
            self._firing_profile_cache[name] = (table, profile)
        else:
            profile = entry[1]
        return profile.query(angle)

    def is_firing_extrapolation(self, name: str, angle: float) -> bool:
        """判断角度是否超出标定范围（即当前结果为外推）。"""
        table = self.get_firing_table(name)
        if not table:
            return False
        return _ft_is_extrap(table, angle)

    def get_height_diff(self, name: str) -> float:
        """获取高度差（发射点-目标点，单位m）。"""
        profile = self.get_angle_meter_profile(name)
        return float(profile.get("height_diff", 0.0)) if profile else 0.0

    def set_height_diff(self, name: str, value: float):
        """设置高度差。"""
        profiles = self.get_angle_meter_profiles()
        if name in profiles:
            profiles[name]["height_diff"] = float(value)
            self.request_save()


    def get_angle_meter_profile_effective_tags(self, name: str) -> list:
        """从关联载具派生标签（所有关联载具标签的并集）"""
        tags = []
        for v in self.get_angle_meter_profile_linked_vehicles(name):
            for t in self.get_vehicle_tags(v):
                if t not in tags:
                    tags.append(t)
        return tags

    # --- 热键（单键：toggle=开始/停止, pause=暂离, calibrate=校准确认, reset=定角装填）---

    # === 全局校准 ===

    def get_angle_meter_calibration_points(self, name: str, point_count: int | None = None):
        """补充: 获取指定点数的校准曲线，None=未校准。
        point_count为None时用active_calibration_point_count。"""
        profile = self.get_angle_meter_profile(name)
        if point_count is None:
            point_count = profile.get("active_calibration_point_count", 5)
        return profile.get("calibrations", {}).get(str(point_count))


    def set_angle_meter_calibration_points(self, name: str, points, point_count: int = 5):
        """保存指定点数的校准曲线，附带校准时刻的灵敏度。

        只快照灵敏度：原始计数"每格转多少度"只取决于游戏内灵敏度，
        与鼠标 DPI 无关（DPI 只影响手移动 1cm 产生多少格，游戏看不到 DPI）。
        """
        profile = self.get_angle_meter_profile(name)
        profile.setdefault("calibrations", {})[str(point_count)] = {
            "points": points,
            "_cal_sens": self.get_angle_meter_sens(),
        }
        profile["active_calibration_point_count"] = point_count
        self.set_angle_meter_profile(name, profile)


    def get_active_calibration_point_count(self, name: str) -> int:
        return self.get_angle_meter_profile(name).get("active_calibration_point_count", 5)


    def set_active_calibration_point_count(self, name: str, count: int):
        profile = self.get_angle_meter_profile(name)
        profile["active_calibration_point_count"] = count
        self.set_angle_meter_profile(name, profile)


    def get_all_calibration_status(self, name: str) -> dict:
        """返回各点数方案的校准状态: {5: bool, 11: bool}"""
        cals = self.get_angle_meter_profile(name).get("calibrations", {})
        return {c: bool(cals.get(str(c))) for c in (2, 5, 11)}


    def clear_all_calibrations(self, name: str):
        """补充: 清空该载具所有精度方案的校准数据（范围变更时调用）"""
        profile = self.get_angle_meter_profile(name)
        profile["calibrations"] = {}
        self.set_angle_meter_profile(name, profile)


    def get_effective_angle_meter_calibration(self, name: str):
        """返回active方案的校准曲线（points列表），按灵敏度变化换算格轴。

        换算原理（"格" = Raw Input 原始计数 lLastY）：
          游戏里"每格转多少度" ∝ 游戏内灵敏度，**与鼠标 DPI 无关**
          （DPI 只决定手移动 1cm 产生多少格；游戏收到的是格数，看不到 DPI）。
        所以把灵敏度从 S_cal 改成 S_cur 后，同一角度所需的格数变为
          C_new = C_cal * (S_cal / S_cur)
        即格轴乘以 校准时灵敏度 / 当前灵敏度。方向：灵敏度调高 → 每格转角变大
        → 同一角度用更少的格 → 曲线左压。
        """
        profile = self.get_angle_meter_profile(name)
        count = profile.get("active_calibration_point_count", 5)
        cal = profile.get("calibrations", {}).get(str(count))
        if not cal:
            return None
        points = cal.get("points", [])
        cal_sens = cal.get("_cal_sens")
        cur_sens = self.get_angle_meter_sens()
        # 任一侧灵敏度缺失（0/未填）就不换算：宁可保持原始校准，也不按 0 缩放
        if cal_sens and cur_sens and cal_sens > 0 and cur_sens > 0:
            ratio = cal_sens / cur_sens
            if abs(ratio - 1.0) > 0.001:
                points = [[int(d * ratio), a] for d, a in points]
        return points

    def get_angle_meter_sens(self) -> float:
        return self._config.get("angle_meter", {}).get("sens", 0)

    def set_angle_meter_sens(self, sens: float):
        self._config.setdefault("angle_meter", {})["sens"] = sens
        self.request_save()


    def get_angle_meter_hotkeys(self) -> dict:
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
