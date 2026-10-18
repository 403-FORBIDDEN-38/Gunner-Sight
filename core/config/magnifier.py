class ConfigMagnifierMixin:
    """magnifier 配置管理 mixin"""

    def is_magnifier_enabled(self) -> bool:
        return self._config.get("magnifier", {}).get("enabled", False)

    def set_magnifier_enabled(self, enabled: bool):
        self._config.setdefault("magnifier", {})["enabled"] = enabled
        self.request_save()

    def get_magnifier_zoom(self) -> float:
        return self._config.get("magnifier", {}).get("zoom", 2.0)

    def set_magnifier_zoom(self, zoom: float):
        self._config.setdefault("magnifier", {})["zoom"] = float(zoom)
        self.request_save()

    def get_magnifier_radius(self) -> int:
        return self._config.get("magnifier", {}).get("radius", 200)

    def set_magnifier_radius(self, radius: int):
        self._config.setdefault("magnifier", {})["radius"] = int(radius)
        self.request_save()

    def get_magnifier_fps(self) -> int:
        return self._config.get("magnifier", {}).get("fps", 60)

    def set_magnifier_fps(self, fps: int):
        self._config.setdefault("magnifier", {})["fps"] = int(fps)
        self.request_save()

    def get_magnifier_breath_step(self) -> int:
        return self._config.get("magnifier", {}).get("breath_step", 20)

    def set_magnifier_breath_step(self, step: int):
        self._config.setdefault("magnifier", {})["breath_step"] = int(step)
        self.request_save()

    def get_magnifier_breath_zoom(self) -> float:
        return self._config.get("magnifier", {}).get("breath_zoom", 0.0)

    def set_magnifier_breath_zoom(self, zoom: float):
        self._config.setdefault("magnifier", {})["breath_zoom"] = float(zoom)
        self.request_save()

    def get_magnifier_hotkeys(self) -> dict:
        return self._config.get("magnifier", {}).get("hotkeys", {
            "toggle": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "zoom_in": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "zoom_out": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "breath_hold": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
        })

    def set_magnifier_hotkey(self, action: str, key: str, trigger: str = "toggle", slot: int = 1):
        hk = self._config.setdefault("magnifier", {}).setdefault("hotkeys", {}).setdefault(action, {
            "key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()

    # ===== 预设（枪种配置）=====
    def get_magnifier_presets(self) -> dict:
        return self._config.get("magnifier", {}).get("presets", {})

    def get_magnifier_preset(self, name: str) -> dict:
        return self.get_magnifier_presets().get(name, {"radius": 200, "step": 20, "ox": 0, "oy": 0})

    def set_magnifier_preset(self, name: str, data: dict):
        self._config.setdefault("magnifier", {}).setdefault("presets", {})[name] = data
        self.request_save()

    def get_current_magnifier_preset(self) -> str:
        return self._config.get("magnifier", {}).get("current_preset", "")

    def set_current_magnifier_preset(self, name: str):
        self._config.setdefault("magnifier", {})["current_preset"] = name
        self.request_save()

    def add_magnifier_preset(self, name: str):
        presets = self.get_magnifier_presets()
        if name not in presets:
            presets[name] = {"radius": 200, "step": 20}
            self._config.setdefault("magnifier", {})["presets"] = presets
            self.request_save()

    def rename_magnifier_preset(self, old: str, new: str):
        presets = self.get_magnifier_presets()
        if old in presets and new not in presets:
            presets[new] = presets.pop(old)
            if self.get_current_magnifier_preset() == old:
                self.set_current_magnifier_preset(new)
            self._config.setdefault("magnifier", {})["presets"] = presets
            self.request_save()

    def delete_magnifier_preset(self, name: str):
        presets = self.get_magnifier_presets()
        if name in presets:
            del presets[name]
            if self.get_current_magnifier_preset() == name:
                remaining = list(presets.keys())
                if remaining:
                    self.set_current_magnifier_preset(remaining[0])
                else:
                    self._config.setdefault("magnifier", {})["current_preset"] = ""
            self._config.setdefault("magnifier", {})["presets"] = presets
            self.request_save()
