"""载具级缩放偏移功能测试"""
import pytest
from core.config_manager import ConfigManager


@pytest.fixture
def config(tmp_path):
    return ConfigManager(config_dir=str(tmp_path / "config"))


class TestVehicleOverlay:
    """载具缩放偏移读写测试"""

    def test_get_vehicle_overlay_returns_default_for_new_vehicle(self, config):
        """新载具（无 overlay 字段）返回默认值"""
        config.add_vehicle("测试载具")
        overlay = config.get_vehicle_overlay("测试载具")
        assert overlay["scale"] == 100.0
        assert overlay["offset_x"] == 0
        assert overlay["offset_y"] == 0

    def test_get_vehicle_overlay_returns_default_for_nonexistent_vehicle(self, config):
        """不存在的载具返回默认值，不崩溃"""
        overlay = config.get_vehicle_overlay("不存在的载具")
        assert overlay["scale"] == 100.0
        assert overlay["offset_x"] == 0
        assert overlay["offset_y"] == 0

    def test_set_vehicle_overlay_persists(self, config):
        """设置载具缩放偏移后能读取"""
        config.add_vehicle("测试载具")
        config.set_vehicle_overlay("测试载具", 150.0, 10, -20)
        overlay = config.get_vehicle_overlay("测试载具")
        assert overlay["scale"] == 150.0
        assert overlay["offset_x"] == 10
        assert overlay["offset_y"] == -20

    def test_set_vehicle_overlay_clamps_scale(self, config):
        """缩放比例被限制在 1-1000 范围内"""
        config.add_vehicle("测试载具")
        config.set_vehicle_overlay("测试载具", 5000.0, 0, 0)
        assert config.get_vehicle_overlay("测试载具")["scale"] == 1000.0
        config.set_vehicle_overlay("测试载具", 0.5, 0, 0)
        assert config.get_vehicle_overlay("测试载具")["scale"] == 1.0

    def test_reset_vehicle_overlay(self, config):
        """重置载具缩放偏移为默认值"""
        config.add_vehicle("测试载具")
        config.set_vehicle_overlay("测试载具", 200.0, 50, 50)
        config.reset_vehicle_overlay("测试载具")
        overlay = config.get_vehicle_overlay("测试载具")
        assert overlay["scale"] == 100.0
        assert overlay["offset_x"] == 0
        assert overlay["offset_y"] == 0

    def test_vehicle_overlay_independent_per_vehicle(self, config):
        """不同载具的缩放偏移互相独立"""
        config.add_vehicle("载具A")
        config.add_vehicle("载具B")
        config.set_vehicle_overlay("载具A", 120.0, 5, 5)
        config.set_vehicle_overlay("载具B", 80.0, -5, -5)
        assert config.get_vehicle_overlay("载具A")["scale"] == 120.0
        assert config.get_vehicle_overlay("载具B")["scale"] == 80.0


class TestMagnificationOverlayMode:
    """倍率缩放偏移开关测试"""

    def _setup_vehicle_ammo_mag(self, config):
        config.add_vehicle("测试载具")
        config.add_ammo_type("测试载具", "测试弹种")
        config.add_magnification("测试载具", "测试弹种", "1X", "")

    def test_default_mode_is_global(self, config):
        """新倍率默认使用全局缩放偏移"""
        self._setup_vehicle_ammo_mag(config)
        assert config.get_magnification_overlay_mode("测试载具", "测试弹种", 0) is False

    def test_set_mode_to_vehicle(self, config):
        """设置倍率使用载具缩放偏移"""
        self._setup_vehicle_ammo_mag(config)
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, True)
        assert config.get_magnification_overlay_mode("测试载具", "测试弹种", 0) is True

    def test_set_mode_to_global(self, config):
        """设置倍率使用全局缩放偏移"""
        self._setup_vehicle_ammo_mag(config)
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, True)
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, False)
        assert config.get_magnification_overlay_mode("测试载具", "测试弹种", 0) is False

    def test_mode_index_out_of_bounds_returns_global(self, config):
        """倍率索引越界时返回全局（false），不崩溃"""
        config.add_vehicle("测试载具")
        config.add_ammo_type("测试载具", "测试弹种")
        assert config.get_magnification_overlay_mode("测试载具", "测试弹种", 999) is False

    def test_mode_independent_per_magnification(self, config):
        """不同倍率的开关互相独立"""
        config.add_vehicle("测试载具")
        config.add_ammo_type("测试载具", "测试弹种")
        config.add_magnification("测试载具", "测试弹种", "1X", "")
        config.add_magnification("测试载具", "测试弹种", "5X", "")
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, True)
        assert config.get_magnification_overlay_mode("测试载具", "测试弹种", 0) is True
        assert config.get_magnification_overlay_mode("测试载具", "测试弹种", 1) is False


class TestEffectiveOverlay:
    """effective_overlay 二选一逻辑测试（核心）"""

    def _setup(self, config):
        config.add_vehicle("测试载具")
        config.add_ammo_type("测试载具", "测试弹种")
        config.add_magnification("测试载具", "测试弹种", "1X", "")
        config.set_vehicle_overlay("测试载具", 150.0, 10, 20)
        config.set_global_scale(80.0)
        config.set_global_offset(5, -5)

    def test_global_mode_returns_global_settings(self, config):
        """全局模式下返回全局缩放偏移"""
        self._setup(config)
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, False)
        effective = config.get_effective_overlay("测试载具", "测试弹种", 0)
        assert effective["scale"] == 80.0
        assert effective["offset_x"] == 5
        assert effective["offset_y"] == -5

    def test_vehicle_mode_returns_vehicle_settings(self, config):
        """载具模式下返回载具缩放偏移"""
        self._setup(config)
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, True)
        effective = config.get_effective_overlay("测试载具", "测试弹种", 0)
        assert effective["scale"] == 150.0
        assert effective["offset_x"] == 10
        assert effective["offset_y"] == 20

    def test_switching_mode_changes_effective(self, config):
        """切换模式时 effective_overlay 返回值相应变化（二选一，不叠加）"""
        self._setup(config)
        # 全局模式
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, False)
        assert config.get_effective_overlay("测试载具", "测试弹种", 0)["scale"] == 80.0
        # 切换到载具模式
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, True)
        assert config.get_effective_overlay("测试载具", "测试弹种", 0)["scale"] == 150.0
        # 切回全局模式
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, False)
        assert config.get_effective_overlay("测试载具", "测试弹种", 0)["scale"] == 80.0

    def test_effective_overlay_no_side_effects(self, config):
        """get_effective_overlay 不修改配置（只读）"""
        self._setup(config)
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, True)
        _ = config.get_effective_overlay("测试载具", "测试弹种", 0)
        # 确认配置未被修改
        assert config.get_vehicle_overlay("测试载具")["scale"] == 150.0
        assert config.get_global_scale() == 80.0


class TestPersistence:
    """持久化测试"""

    def test_vehicle_overlay_persists_after_save_and_reload(self, tmp_path):
        """载具缩放偏移保存后重新加载一致"""
        config_dir = str(tmp_path / "config")
        cfg1 = ConfigManager(config_dir=config_dir)
        cfg1.add_vehicle("持久载具")
        cfg1.set_vehicle_overlay("持久载具", 130.0, 15, 25)
        cfg1.set_magnification_overlay_mode("持久载具", "弹种", 0, True) if cfg1.add_ammo_type("持久载具", "弹种") and cfg1.add_magnification("持久载具", "弹种", "1X", "") else None
        cfg1.save_config()

        cfg2 = ConfigManager(config_dir=config_dir)
        overlay = cfg2.get_vehicle_overlay("持久载具")
        assert overlay["scale"] == 130.0
        assert overlay["offset_x"] == 15
        assert overlay["offset_y"] == 25

    def test_old_config_without_overlay_fields_uses_default(self, tmp_path):
        """旧配置（无 overlay 字段）升级后使用默认值，不崩溃"""
        import json
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        # 模拟旧格式配置（无 overlay 字段）
        old_config = {
            "version": "1.0",
            "global_settings": {"scale": 100.0, "offset_x": 0, "offset_y": 0, "overlay_visible": True},
            "hotkeys": {"toggle_overlay": {"key1": "f1", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                        "cycle_magnification": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                        "ammo_types": {}},
            "vehicles": {"旧载具": {"name": "旧载具", "tags": [], "ammo_types": {
                "旧弹种": {"magnifications": [{"label": "1X", "crosshair": ""}]}
            }}},
            "tags": [],
            "rangefinder": {"enabled": False, "toggle_ui_enabled": True, "current_profile": "", "profiles": {},
                            "hotkeys": {"measure": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"}}},
            "squad_macro": {"enabled": False, "hotkey": {"key1": "", "trigger1": "keydown"}, "squad_name": "", "locked": True, "interval_ms": 100},
            "angle_meter": {"enabled": False, "current_profile": "", "profiles": {},
                            "hotkeys": {"calibrate": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                                        "use": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"},
                                        "pause": {"key1": "", "trigger1": "keydown", "key2": "", "trigger2": "keydown"}}},
            "current_state": {"vehicle": None, "ammo_type": None, "magnification_index": 0}
        }
        (config_dir / "config.json").write_text(json.dumps(old_config, ensure_ascii=False), encoding="utf-8")

        cfg = ConfigManager(config_dir=str(config_dir))
        # 旧载具无 overlay 字段，应返回默认值
        overlay = cfg.get_vehicle_overlay("旧载具")
        assert overlay["scale"] == 100.0
        assert overlay["offset_x"] == 0
        assert overlay["offset_y"] == 0
        # 旧倍率无 use_vehicle_overlay 字段，应默认全局（false）
        assert cfg.get_magnification_overlay_mode("旧载具", "旧弹种", 0) is False



class TestOverlayOpacity:
    """FEATURE-4: 叠加层透明度设置测试"""

    def test_default_vehicle_opacity_is_one(self, config):
        """新载具默认opacity为1.0"""
        config.add_vehicle("测试载具")
        overlay = config.get_vehicle_overlay("测试载具")
        assert overlay["opacity"] == 1.0

    def test_set_vehicle_opacity(self, config):
        """设置载具opacity后能读取"""
        config.add_vehicle("测试载具")
        config.set_vehicle_overlay("测试载具", 100.0, 0, 0, opacity=0.5)
        overlay = config.get_vehicle_overlay("测试载具")
        assert abs(overlay["opacity"] - 0.5) < 0.01

    def test_set_vehicle_opacity_none_preserves_current(self, config):
        """opacity=None时保留当前值，不重置为1.0"""
        config.add_vehicle("测试载具")
        config.set_vehicle_overlay("测试载具", 100.0, 0, 0, opacity=0.3)
        # 不传opacity，只改scale，opacity应保留
        config.set_vehicle_overlay("测试载具", 150.0, 10, 10)
        overlay = config.get_vehicle_overlay("测试载具")
        assert overlay["scale"] == 150.0
        assert abs(overlay["opacity"] - 0.3) < 0.01

    def test_opacity_clamped_to_range(self, config):
        """opacity被限制在0.1-1.0范围内"""
        config.add_vehicle("测试载具")
        config.set_vehicle_overlay("测试载具", 100.0, 0, 0, opacity=0.0)
        assert config.get_vehicle_overlay("测试载具")["opacity"] == 0.1
        config.set_vehicle_overlay("测试载具", 100.0, 0, 0, opacity=2.0)
        assert config.get_vehicle_overlay("测试载具")["opacity"] == 1.0

    def test_global_opacity_default(self, config):
        """全局opacity默认为1.0"""
        assert config.get_overlay_opacity() == 1.0

    def test_global_opacity_set_get(self, config):
        """设置全局opacity后能读取"""
        config.set_overlay_opacity(0.7)
        assert abs(config.get_overlay_opacity() - 0.7) < 0.01

    def test_global_opacity_clamped(self, config):
        """全局opacity被限制在0.1-1.0"""
        config.set_overlay_opacity(0.0)
        assert config.get_overlay_opacity() == 0.1
        config.set_overlay_opacity(1.5)
        assert config.get_overlay_opacity() == 1.0

    def test_effective_overlay_contains_opacity_global(self, config):
        """get_effective_overlay全局模式返回含opacity的字典"""
        config.add_vehicle("测试载具")
        config.add_ammo_type("测试载具", "测试弹种")
        config.set_overlay_opacity(0.6)
        effective = config.get_effective_overlay("测试载具", "测试弹种", 0)
        assert "opacity" in effective
        assert abs(effective["opacity"] - 0.6) < 0.01

    def test_effective_overlay_contains_opacity_vehicle(self, config):
        """get_effective_overlay载具模式返回载具opacity"""
        config.add_vehicle("测试载具")
        config.add_ammo_type("测试载具", "测试弹种")
        config.add_magnification("测试载具", "测试弹种", "1x")
        config.set_vehicle_overlay("测试载具", 100.0, 0, 0, opacity=0.4)
        config.set_magnification_overlay_mode("测试载具", "测试弹种", 0, True)
        effective = config.get_effective_overlay("测试载具", "测试弹种", 0)
        assert "opacity" in effective
        assert abs(effective["opacity"] - 0.4) < 0.01

    def test_old_config_no_opacity_defaults_to_one(self, config, tmp_path):
        """旧配置无opacity字段默认1.0"""
        import json
        config_dir = tmp_path / "old_config"
        config_dir.mkdir()
        old_config = {
            "config_version": 5,
            "vehicles": {"旧载具": {"name": "旧载具", "tags": [], "ammo_types": {},
                        "overlay": {"scale": 100.0, "offset_x": 0, "offset_y": 0}}},
            "global_settings": {"scale": 100.0, "offset_x": 0, "offset_y": 0, "overlay_visible": True},
            "hotkeys": {}, "current_state": {}, "rangefinder": {}, "squad_macro": {},
            "angle_meter": {}, "distance_meter": {}
        }
        (config_dir / "config.json").write_text(json.dumps(old_config, ensure_ascii=False), encoding="utf-8")
        cfg = ConfigManager(config_dir=str(config_dir))
        overlay = cfg.get_vehicle_overlay("旧载具")
        assert overlay.get("opacity", 1.0) == 1.0
        assert cfg.get_overlay_opacity() == 1.0
