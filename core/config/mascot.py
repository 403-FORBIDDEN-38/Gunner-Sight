
class ConfigMascotMixin:
    """mascot 配置管理 mixin"""

    def is_mascot_enabled(self) -> bool:
        # 不持久化：每次启动默认关闭，不读取cfg中的enabled
        return False


    def set_mascot_enabled(self, enabled: bool):
        # 不持久化：仅运行时内存记录，不写cfg
        self._mascot_enabled_runtime = enabled


    def get_mascot_volume(self) -> float:
        return self._config.get("mascot", {}).get("volume", 0.1125)


    def set_mascot_volume(self, volume: float):
        self._config.setdefault("mascot", {})["volume"] = max(0.0, min(1.0, float(volume)))
        self.request_save()


    def is_mascot_persistent(self) -> bool:
        return self._config.get("mascot", {}).get("persistent", True)


    def set_mascot_persistent(self, persistent: bool):
        self._config.setdefault("mascot", {})["persistent"] = persistent
        self.request_save()

