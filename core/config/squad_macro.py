import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

class ConfigSquadMacroMixin:
    """squad_macro 配置管理 mixin"""

    def is_squad_macro_enabled(self) -> bool:
        return self._config.get("squad_macro", {}).get("enabled", False)


    def set_squad_macro_enabled(self, enabled: bool):
        self._config.setdefault("squad_macro", {})["enabled"] = enabled
        self.request_save()


    def get_squad_macro_hotkey(self) -> Dict:
        return self._config.get("squad_macro", {}).get("hotkey", {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"})


    def set_squad_macro_hotkey(self, key: str, trigger: str = "keydown", slot: int = 1):
        hk = self._config.setdefault("squad_macro", {}).setdefault("hotkey", {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"})
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
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

