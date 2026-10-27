
class ConfigDistanceMixin:
    """distance 配置管理 mixin"""

    def is_distance_meter_enabled(self) -> bool:
        return self._config.get("distance_meter", {}).get("enabled", False)


    def set_distance_meter_enabled(self, enabled: bool):
        self._config.setdefault("distance_meter", {})["enabled"] = enabled
        self.request_save()


    def get_distance_meter_scale(self) -> float:
        return self._config.get("distance_meter", {}).get("scale_meters", 300)


    def set_distance_meter_scale(self, scale: float):
        self._config.setdefault("distance_meter", {})["scale_meters"] = float(scale)
        self.request_save()


    def get_distance_meter_calibration(self) -> dict:
        dm = self._config.get("distance_meter", {})
        return {
            "calibrated_pixels": dm.get("calibrated_pixels", 0),
            "pixels_per_meter": dm.get("pixels_per_meter", 0),
            "calibration_direction": dm.get("calibration_direction", ""),
        }


    def set_distance_meter_calibration(self, calibrated_pixels: float, pixels_per_meter: float, direction: str):
        dm = self._config.setdefault("distance_meter", {})
        dm["calibrated_pixels"] = calibrated_pixels
        dm["pixels_per_meter"] = pixels_per_meter
        dm["calibration_direction"] = direction
        self.request_save()


    def clear_distance_meter_calibration(self):
        """禁用时清理标定数据"""
        dm = self._config.setdefault("distance_meter", {})
        dm["calibrated_pixels"] = 0
        dm["pixels_per_meter"] = 0
        dm["calibration_direction"] = ""
        self.request_save()


    def get_distance_meter_overlay_offset(self) -> tuple:
        dm = self._config.get("distance_meter", {})
        return dm.get("overlay_offset_x", 100), dm.get("overlay_offset_y", 100)


    def set_distance_meter_overlay_offset(self, x: int, y: int):
        dm = self._config.setdefault("distance_meter", {})
        dm["overlay_offset_x"] = int(x)
        dm["overlay_offset_y"] = int(y)
        self.request_save()


    def get_distance_meter_hotkeys(self) -> dict:
        return self._config.get("distance_meter", {}).get("hotkeys", {
            "toggle": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "record": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "measure": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
            "modifier": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
        })


    def set_distance_meter_hotkey(self, action: str, key: str, trigger: str = "keydown", slot: int = 1):
        hk = self._config.setdefault("distance_meter", {}).setdefault("hotkeys", {}).setdefault(action, {
            "key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()


    def get_distance_meter_modifiers(self) -> list:
        """返回组合键列表[key1, key2]（过滤空值），任一按下即触发组合键效果"""
        hk = self.get_distance_meter_hotkeys().get("modifier", {})
        return [k for k in [hk.get("key1", ""), hk.get("key2", "")] if k]

    # ==================== 建队宏 ====================

