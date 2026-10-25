"""批次 4 浪 2：P1 五项契约测试。

P1-2（本文件主体）：资源目录读写分离。
- config.resources_write_dir：exe 同级不可写时降级到 config 侧 resources；
- config.resolve_resource_path：读多路径（出厂目录优先，写目录兜底）；
- ResourceManager：list 取并集、get 两处都找、导入/删除落写路径。

P1-1 / P1-4 的验证属命令级（uv lock --check 无环境变量通过；_LibpngFilter
删除后无引用），不做同义反复测试。P1-3 的接线契约在 test_wave_d_contract.py。
"""
from pathlib import Path


def _patch_read_only_resources(monkeypatch):
    """把「exe 同级 resources 可写性」钉成 False，其余路径仍走真实探针。"""
    from core.config import base as base_mod

    real = base_mod._is_writable
    factory_res = base_mod.get_app_base_dir() / "resources"

    def fake(path):
        if Path(path) == factory_res:
            return False
        return real(path)

    monkeypatch.setattr(base_mod, "_is_writable", fake)
    return factory_res


def test_resources_write_dir_falls_back_when_read_only(tmp_path, monkeypatch):
    """P1-2：只读安装下写路径降级到 config 侧，读主路径不变。"""
    from core.config_manager import ConfigManager

    factory_res = _patch_read_only_resources(monkeypatch)
    cfg = ConfigManager(config_dir=str(tmp_path))

    assert cfg.resources_dir == factory_res          # 读主路径仍是出厂目录
    assert cfg.resources_write_dir == tmp_path / "resources"
    assert cfg.resources_write_dir != cfg.resources_dir
    assert (tmp_path / "resources").exists()         # 写目录已创建


def test_resources_write_dir_same_when_writable(tmp_path):
    """便携/可写安装：读=写，保持原行为。"""
    from core.config_manager import ConfigManager

    cfg = ConfigManager(config_dir=str(tmp_path))
    assert cfg.resources_write_dir == cfg.resources_dir


def test_resolve_resource_path_multipath(tmp_path):
    """读多路径：出厂目录优先，写目录兜底，两处都无时回主路径（交下游判空）。"""
    from core.config_manager import ConfigManager

    cfg = ConfigManager(config_dir=str(tmp_path))
    read_dir, write_dir = tmp_path / "read", tmp_path / "write"
    read_dir.mkdir()
    write_dir.mkdir()
    (read_dir / "factory.png").write_bytes(b"r")
    (write_dir / "user.png").write_bytes(b"w")
    (read_dir / "both.png").write_bytes(b"r")
    (write_dir / "both.png").write_bytes(b"w")
    cfg.resources_dir = read_dir
    cfg.resources_write_dir = write_dir

    assert cfg.resolve_resource_path("factory.png") == read_dir / "factory.png"
    assert cfg.resolve_resource_path("user.png") == write_dir / "user.png"
    assert cfg.resolve_resource_path("both.png") == read_dir / "both.png"
    assert cfg.resolve_resource_path("missing.png") == read_dir / "missing.png"


def test_resource_manager_multipath(tmp_path):
    """写路径分离时：list 并集、get 两处找、导入/删除落写路径。"""
    from core.resource_manager import ResourceManager

    read_dir, write_dir = tmp_path / "read", tmp_path / "write"
    read_dir.mkdir()
    write_dir.mkdir()
    (read_dir / "factory.png").write_bytes(b"f")
    (write_dir / "user.png").write_bytes(b"u")
    (read_dir / "assets").mkdir()
    (read_dir / "assets" / "inner.png").write_bytes(b"a")

    rm = ResourceManager(resources_dir=str(read_dir), write_dir=str(write_dir))
    assert set(rm.list_resources()) == {"factory.png", "user.png"}  # assets 仍排除
    assert rm.get_resource_path("factory.png") == str(read_dir / "factory.png")
    assert rm.get_resource_path("user.png") == str(write_dir / "user.png")

    external = tmp_path / "external.png"
    external.write_bytes(b"x")
    assert rm.import_resource(str(external)) == "external.png"
    assert (write_dir / "external.png").exists()
    assert not (read_dir / "external.png").exists()

    assert rm.remove_resource("user.png") is True
    assert not (write_dir / "user.png").exists()
    assert rm.remove_resource("factory.png") is True  # 读路径里的也能删（便携同目录语义）


def test_resource_manager_default_write_dir_equals_read(tmp_path):
    """未传 write_dir 时读写同目录（既有调用方零改动）。"""
    from core.resource_manager import ResourceManager

    rm = ResourceManager(resources_dir=str(tmp_path))
    assert rm.get_write_dir() == rm.get_resources_dir() == tmp_path
