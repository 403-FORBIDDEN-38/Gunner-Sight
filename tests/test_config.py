"""ConfigManager 基础测试 15 例"""
import json
from core.config_manager import ConfigManager


class TestConfigInitialization:
    def test_initial_config_has_required_keys(self, config):
        """初始配置有 vehicles、hotkeys、current_state、global_settings、rangefinder、squad_macro、angle_meter 等键"""
        cfg = config._config
        for key in ["vehicles", "hotkeys", "current_state", "global_settings",
                     "rangefinder", "squad_macro", "angle_meter"]:
            assert key in cfg, f"缺少配置键: {key}"


class TestVehicleOperations:
    def test_add_vehicle_appears_in_list(self, config):
        """add_vehicle 后 get_vehicle_names 包含新载具"""
        assert config.add_vehicle("测试载具") is True
        assert "测试载具" in config.get_vehicle_names()

    def test_add_duplicate_vehicle_returns_false(self, config):
        """重复添加载具返回 False"""
        config.add_vehicle("重复载具")
        assert config.add_vehicle("重复载具") is False

    def test_remove_vehicle_disappears_from_list(self, config):
        """remove_vehicle 后载具列表不包含该载具"""
        config.add_vehicle("待删除载具")
        assert config.remove_vehicle("待删除载具") is True
        assert "待删除载具" not in config.get_vehicle_names()

    def test_rename_vehicle_updates_name(self, config):
        """rename_vehicle 后名称更新，旧名称不存在"""
        config.add_vehicle("旧名称")
        assert config.rename_vehicle("旧名称", "新名称") is True
        assert "新名称" in config.get_vehicle_names()
        assert "旧名称" not in config.get_vehicle_names()


class TestAmmoTypeOperations:
    def test_add_ammo_type_appears_in_list(self, config):
        """add_ammo_type 后 get_ammo_type_names 包含新弹种"""
        config.add_vehicle("载具A")
        assert config.add_ammo_type("载具A", "穿甲弹") is True
        assert "穿甲弹" in config.get_ammo_type_names("载具A")

    def test_remove_ammo_type_disappears(self, config):
        """remove_ammo_type 后弹种列表不包含"""
        config.add_vehicle("载具B")
        config.add_ammo_type("载具B", "高爆弹")
        assert config.remove_ammo_type("载具B", "高爆弹") is True
        assert "高爆弹" not in config.get_ammo_type_names("载具B")


class TestMagnificationOperations:
    def test_add_magnification_increases_count(self, config):
        """add_magnification 后 get_magnification_count 增加"""
        config.add_vehicle("载具C")
        config.add_ammo_type("载具C", "弹种C")
        before = config.get_magnification_count("载具C", "弹种C")
        assert config.add_magnification("载具C", "弹种C", "1X", "") is True
        assert config.get_magnification_count("载具C", "弹种C") == before + 1

    def test_remove_magnification_decreases_count(self, config):
        """remove_magnification 后数量减少"""
        config.add_vehicle("载具D")
        config.add_ammo_type("载具D", "弹种D")
        config.add_magnification("载具D", "弹种D", "1X", "")
        config.add_magnification("载具D", "弹种D", "5X", "")
        before = config.get_magnification_count("载具D", "弹种D")
        assert config.remove_magnification("载具D", "弹种D", 0) is True
        assert config.get_magnification_count("载具D", "弹种D") == before - 1


class TestCurrentState:
    def test_set_current_vehicle_updates_state(self, config):
        """set_current_vehicle 后 get_current_state()['vehicle'] 更新"""
        config.add_vehicle("状态载具")
        config.set_current_vehicle("状态载具")
        assert config.get_current_state()["vehicle"] == "状态载具"

    def test_set_current_ammo_type_updates_state(self, config):
        """set_current_ammo_type 后状态更新"""
        config.add_vehicle("状态载具2")
        config.add_ammo_type("状态载具2", "状态弹种")
        config.set_current_vehicle("状态载具2")
        config.set_current_ammo_type("状态弹种")
        assert config.get_current_state()["ammo_type"] == "状态弹种"

    def test_cycle_magnification_wraps_around(self, config):
        """在最后一个倍率时 cycle_magnification 回到第一个（索引0）"""
        config.add_vehicle("循环载具")
        config.add_ammo_type("循环载具", "循环弹种")
        config.add_magnification("循环载具", "循环弹种", "1X", "")
        config.add_magnification("循环载具", "循环弹种", "5X", "")
        config.set_current_vehicle("循环载具")
        config.set_current_ammo_type("循环弹种")
        config.set_current_magnification_index(1)
        config.cycle_magnification()
        assert config.get_current_state()["magnification_index"] == 0


class TestPersistence:
    def test_config_persists_after_save_and_reload(self, tmp_path):
        """save_config 后新建 ConfigManager 加载，数据一致"""
        config_dir = str(tmp_path / "config")
        cfg1 = ConfigManager(config_dir=config_dir)
        cfg1.add_vehicle("持久载具")
        cfg1.save_config()
        cfg2 = ConfigManager(config_dir=config_dir)
        assert "持久载具" in cfg2.get_vehicle_names()

    def test_corrupt_config_recovers_to_default(self, tmp_path):
        """写一个损坏的 config.json（非法JSON）→ 新建 ConfigManager 加载 → 不崩溃且有默认结构"""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text("{invalid json!!!", encoding="utf-8")
        cfg = ConfigManager(config_dir=str(config_dir))
        assert "vehicles" in cfg._config
        assert "hotkeys" in cfg._config

    def test_empty_config_file_initializes_default(self, tmp_path):
        """config.json 存在但内容为空 → 正常初始化为默认结构"""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text("", encoding="utf-8")
        cfg = ConfigManager(config_dir=str(config_dir))
        assert "vehicles" in cfg._config
        assert "global_settings" in cfg._config
