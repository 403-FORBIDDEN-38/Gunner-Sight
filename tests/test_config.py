r"""core/config/base.py：数据目录降级、配置损坏回退、保存并发安全。

这个模块守的是**用户数据**——坏了不崩，只是设置全丢或者配置静默被覆盖。
四类契约：

**P5 数据目录降级**
config 原先钉死 exe 同级，只读安装（Program Files 标准用户）下设置全部丢失。
现在：exe 同级可写 → 维持便携（默认路径不变）；不可写 → 降级
%APPDATA%\GunnerSight\config，并把出厂 config.json 复制过去做种子（77 载具库
不丢）；%APPDATA% 也不可写 → 降级 %TEMP%\GunnerSight\config 保命。

**P6 配置损坏回退**
原先"损坏 + 备份失败"时骨架会静默覆盖原文件，用户数据永久丢失。现在：原文件
必须先留痕（backups 改名 / 同目录改名 / 恢复副本至少一样成功）才允许写骨架；
全部失败则原文件原地保留，绝不静默覆盖。

**P4 日志目录降级**
日志/startup_log 写盘无保护，只读位置双击"什么都没发生"——mkdir 失败要降级到
%TEMP%/GunnerSight/logs，否则用户连排查入口都没有。

**S2/M7 保存并发安全**
① `_atomic_write` 曾在 `_save_lock` 之外——主线程立即保存与 Timer 防抖保存并发
时，两条路径交错写同一个 `config.json.tmp` 再 os.replace，可把半截 JSON 换成
正式配置（下次启动加载失败回退骨架 = 用户设置全丢）。
② 旧 Timer 的回调把新 Timer 的引用清成 None，防抖失效、退出前悬挂 Timer。
"""
import json
import sys
import threading
import time
from pathlib import Path


from core.config import base as cfg_base
from core.config_manager import ConfigManager


# ---------------------------------------------------------------- 保存并发安全

def test_atomic_write_runs_inside_save_lock(config, monkeypatch):
    """S2 契约：_atomic_write 必须在 _save_lock 内执行（修复前在锁外）。"""
    observed = []
    real_atomic = config._atomic_write

    def spy(data):
        observed.append(config._save_lock.locked())
        return real_atomic(data)

    monkeypatch.setattr(config, "_atomic_write", spy)

    config.save_config()
    config._do_deferred_save(object())  # 直接驱动一次防抖落盘

    assert observed == [True, True]


def test_concurrent_saves_never_corrupt_config(config, tmp_path):
    """立即保存与防抖保存并发撞车：config.json 必须始终可解析、无 .tmp 残留。"""
    stop = threading.Event()

    def immediate_saver():
        while not stop.is_set():
            config.save_config()

    def deferred_saver():
        while not stop.is_set():
            config.request_save()
            time.sleep(0.6)  # >500ms 防抖窗，让 Timer 真的到点（更短会被反复取消）

    threads = [threading.Thread(target=immediate_saver) for _ in range(2)]
    threads.append(threading.Thread(target=deferred_saver))
    for t in threads:
        t.start()
    time.sleep(1.2)
    stop.set()
    for t in threads:
        t.join(timeout=5)

    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data["my_beloved"] == "Xiaocheng"
    assert list(tmp_path.glob("*.tmp")) == []


def test_stale_deferred_callback_keeps_newer_timer_reference(config):
    """M7 契约：过期 Timer 的回调不得清掉新 Timer 的引用。"""
    config.request_save()
    first_timer, first_token = config._save_timer, config._save_token
    config.request_save()  # 取消旧的、换新的
    second_timer, second_token = config._save_timer, config._save_token
    assert second_timer is not first_timer
    assert second_token is not first_token

    try:
        # 过期的回调后跑完：不动新 Timer 的引用
        config._do_deferred_save(first_token)
        assert config._save_timer is second_timer
        assert config._save_token is second_token

        # 新 Timer 的回调：正常清引用
        config._do_deferred_save(second_token)
        assert config._save_timer is None
        assert config._save_token is None
    finally:
        for t in (first_timer, second_timer):
            t.cancel()


# ---------------------------------------------------------------- P5：数据目录降级

def test_is_writable_true_for_tmp_dir(tmp_path):
    assert cfg_base._is_writable(tmp_path) is True
    # 探针文件不残留
    assert not any(p.name.startswith(".gs_write_probe_") for p in tmp_path.iterdir())


def test_is_writable_false_under_file(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    assert cfg_base._is_writable(blocker / "sub") is False


def test_portable_dir_kept_when_writable(tmp_path, monkeypatch):
    r"""契约 1：exe 同级可写 → 维持便携，行为与修复前一致。"""
    exe_dir = tmp_path / "exe"
    (exe_dir / "config").mkdir(parents=True)
    monkeypatch.setattr(cfg_base, "get_app_base_dir", lambda: exe_dir)

    cm = ConfigManager()
    assert cm.config_dir == exe_dir / "config"
    assert cm.config_file == exe_dir / "config" / "config.json"


def test_degrade_to_appdata_with_factory_seed(tmp_path, monkeypatch):
    r"""契约 2：只读安装 → %APPDATA%\GunnerSight\config，出厂配置做种子（77 载具库不丢）。"""
    exe_dir = tmp_path / "exe"
    (exe_dir / "config").mkdir(parents=True)
    factory = {"my_beloved": "Xiaocheng", "vehicles": {"T-90": {"ammo_types": {}}}}
    (exe_dir / "config" / "config.json").write_text(json.dumps(factory), encoding="utf-8")
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(cfg_base, "get_app_base_dir", lambda: exe_dir)

    # 便携目录不可写（模拟 Program Files 标准用户），APPDATA 可写
    real_is_writable = cfg_base._is_writable
    def fake_writable(p):
        return False if p == exe_dir / "config" else real_is_writable(p)
    monkeypatch.setattr(cfg_base, "_is_writable", fake_writable)

    cm = ConfigManager()
    assert cm.config_dir == appdata / "GunnerSight" / "config"
    # 出厂配置被复制为种子：用户的 77 载具库在只读安装下依然可见
    assert "T-90" in cm.get_vehicle_names()
    seeded = json.loads((appdata / "GunnerSight" / "config" / "config.json").read_text(encoding="utf-8"))
    assert seeded["vehicles"].keys() == {"T-90"}


def test_degrade_does_not_overwrite_existing_appdata_config(tmp_path, monkeypatch):
    """降级不覆盖用户已有数据：APPDATA 里已有 config.json 时绝不重新播种。"""
    exe_dir = tmp_path / "exe"
    (exe_dir / "config").mkdir(parents=True)
    (exe_dir / "config" / "config.json").write_text('{"vehicles": {"出厂车": {}}}', encoding="utf-8")
    appdata = tmp_path / "appdata"
    target = appdata / "GunnerSight" / "config"
    target.mkdir(parents=True)
    (target / "config.json").write_text('{"vehicles": {"用户自己的车": {}}}', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(cfg_base, "get_app_base_dir", lambda: exe_dir)
    real_is_writable = cfg_base._is_writable
    monkeypatch.setattr(cfg_base, "_is_writable",
                        lambda p: False if p == exe_dir / "config" else real_is_writable(p))

    cm = ConfigManager()
    assert "用户自己的车" in cm.get_vehicle_names()
    assert "出厂车" not in cm.get_vehicle_names()


def test_degrade_to_temp_when_appdata_also_unwritable(tmp_path, monkeypatch):
    r"""契约 3：%APPDATA% 也不可写 → %TEMP%\GunnerSight\config 保命。"""
    exe_dir = tmp_path / "exe"
    (exe_dir / "config").mkdir(parents=True)
    monkeypatch.setattr(cfg_base, "get_app_base_dir", lambda: exe_dir)
    # 便携目录不可写
    real_is_writable = cfg_base._is_writable
    monkeypatch.setattr(cfg_base, "_is_writable",
                        lambda p: False if p == exe_dir / "config" else real_is_writable(p))
    # %APPDATA% 指向"文件下的路径"从而同样不可写
    blocker = tmp_path / "appdata_blocker"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setattr(cfg_base, "get_fallback_data_dir", lambda: blocker / "GunnerSight")
    # %TEMP% 重定向到 tmp_path，避免污染真实临时目录
    monkeypatch.setattr(cfg_base.tempfile, "gettempdir", lambda: str(tmp_path))

    cm = ConfigManager()
    assert cm.config_dir == tmp_path / "GunnerSight" / "config"
    assert cm.config_file.is_file()  # 骨架已落盘（能启动）


# ---------------------------------------------------------------- P6：配置损坏回退

def _write_corrupt(config_dir: Path):
    config_dir.mkdir(parents=True, exist_ok=True)
    config_dir.joinpath("config.json").write_text("{ this is not json", encoding="utf-8")


def test_corrupt_config_backs_up_then_writes_skeleton(tmp_path):
    r"""契约 4a：backups 可用 → rename 备份 + 写骨架 + 登记提示。"""
    work = tmp_path / "work"
    config_dir = work / "config"
    _write_corrupt(config_dir)
    original = config_dir.joinpath("config.json").read_bytes()

    cm = ConfigManager(config_dir=str(config_dir))
    # 原文件已备份（内容原样保留）
    backups = list((work / "backups").glob("config.corrupt_*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    # 骨架已写入且可解析
    assert json.loads(config_dir.joinpath("config.json").read_text(encoding="utf-8"))["my_beloved"] == "Xiaocheng"
    # 提示已登记（main 启动后弹一次）
    assert cm.recovery_notices and "备份" in cm.recovery_notices[0]


def test_corrupt_config_renames_in_place_when_backups_blocked(tmp_path):
    r"""契约 4b：backups 不可建（被文件占用）→ 同目录改名保留，仍写骨架。"""
    work = tmp_path / "work"
    config_dir = work / "config"
    _write_corrupt(config_dir)
    original = config_dir.joinpath("config.json").read_bytes()
    (work / "backups").write_text("blocked by a file", encoding="utf-8")

    cm = ConfigManager(config_dir=str(config_dir))
    renamed = list(config_dir.glob("config.corrupt_*"))
    assert len(renamed) == 1
    assert renamed[0].read_bytes() == original
    assert json.loads(config_dir.joinpath("config.json").read_text(encoding="utf-8"))["my_beloved"] == "Xiaocheng"
    assert cm.recovery_notices and "保留为" in cm.recovery_notices[0]


def test_corrupt_config_keeps_original_when_all_recovery_fails(tmp_path, monkeypatch):
    r"""契约 4c：改名与恢复副本全部失败 → 原文件原地保留，绝不静默覆盖。"""
    work = tmp_path / "work"
    config_dir = work / "config"
    _write_corrupt(config_dir)
    original = config_dir.joinpath("config.json").read_bytes()

    def boom(*a, **k):
        raise OSError("simulated read-only")
    monkeypatch.setattr(Path, "rename", boom)
    monkeypatch.setattr(Path, "write_bytes", boom)

    cm = ConfigManager(config_dir=str(config_dir))
    # 原文件一字未动
    assert config_dir.joinpath("config.json").read_bytes() == original
    assert not list(config_dir.glob("config.corrupt_*"))
    assert not list(config_dir.glob("gunnersight_config.corrupt_*"))
    # 内存中用骨架跑，提示告知用户
    assert cm.get_vehicle_names() == []
    assert cm.recovery_notices and "无法备份" in cm.recovery_notices[0]


# ---------------------------------------------------------------- P4：日志目录降级

def test_log_dir_falls_back_to_temp_when_unwritable(tmp_path, monkeypatch):
    r"""契约 5：frozen 且 exe 同级 logs 不可建 → 降级 %TEMP%/GunnerSight/logs。"""
    from core import logger as logger_mod

    blocker = tmp_path / "exe_blocker"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(blocker / "GUNNER SIGHT.exe"))
    monkeypatch.setattr(logger_mod.tempfile, "gettempdir", lambda: str(tmp_path))

    log_dir = logger_mod._get_log_dir()
    assert log_dir == tmp_path / "GunnerSight" / "logs"
    assert log_dir.is_dir()


def test_log_dir_normal_path_unchanged(monkeypatch):
    """开发环境（非 frozen）：日志目录仍是项目根/logs。"""
    from core import logger as logger_mod

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    log_dir = logger_mod._get_log_dir()
    assert log_dir.name == "logs"


# ---------------------------------------------------------------- P5：信息页可见性

def test_info_tab_shows_data_dir(qapp, config):
    """P5：信息页显示当前数据目录（只读降级后用户需要知道配置去向）。"""
    from PyQt5.QtWidgets import QLabel

    from core.resource_manager import ResourceManager
    from gui.tabs.info_tab import InfoTab

    tab = InfoTab(config, ResourceManager())
    texts = [lbl.text() for lbl in tab.findChildren(QLabel)]
    assert any(t.startswith("数据目录:") and str(config.config_dir) in t for t in texts)
