from core.logger import logger

"""
配置管理模块 (Configuration Manager)

负责载具、弹种、倍率及软件设置的保存与读取。
采用数据驱动架构，所有配置均通过JSON文件管理。
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

from core.colors import THEME_DARK, THEME_LIGHT

# 受保护配置键：永远保留，禁止任何清理/迁移/墓碑逻辑删除。
# 即使未来从 _get_minimal_skeleton 移除，用户 cfg 里的值也不会丢失。
# 新增受保护字段时在此登记（键 -> 默认值）。
_PROTECTED_CONFIG_KEYS = {
    "my_beloved": "Xiaocheng",
}

def get_app_base_dir() -> Path:
    """获取应用基础目录（兼容开发环境和打包环境）
    14.1 onedir 对齐：frozen 时始终返回 exe 同级目录，用户数据(config/resources)外置在此，
    绝不回退 _internal（_internal 仅存程序依赖，用户不动）。
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def get_config_file() -> Path:
    """配置文件路径：config/config.json（开发版和发布版统一）。"""
    return get_app_base_dir() / "config" / "config.json"


def _is_writable(dir_path: Path) -> bool:
    """目录可写探测：实际创建并删除一个探针文件。

    比 os.access 可靠——只读介质、OneDrive"文件按需"占位、目录只读属性
    都可能让 os.access 返回 True 而真实写入失败（P4/P5 的根因）。
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        probe = dir_path / f".gs_write_probe_{os.getpid()}"
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        probe.unlink()
        return True
    except Exception:
        return False


def get_fallback_data_dir() -> Path:
    r"""只读安装位置的降级数据目录：%APPDATA%\GunnerSight"""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "GunnerSight"


def _seed_config_from(src: Path, dst: Path) -> None:
    """首次降级启动：把随包出厂的 config.json 复制到降级目录做种子
    （不存在才复制，绝不覆盖用户已有数据；出厂 77 载具库因此不丢）。"""
    try:
        if src.is_file() and not dst.exists():
            shutil.copyfile(src, dst)
            logger.info(f"[ConfigManager] 出厂配置已复制到 {dst}")
    except Exception as e:
        logger.info(f"[ConfigManager] 复制出厂配置失败: {e}")


def _resolve_portable_config_dir() -> Path:
    r"""数据目录决策（P5，启动时一次）：

    1. exe 同级/config 可写 → 维持绿色便携（绝大多数用户，含开发版）；
    2. 不可写（Program Files 标准用户 / 公司锁定目录 / 只读介质）→
       %APPDATA%\GunnerSight\config，并把出厂 config.json 复制过去做种子；
    3. %APPDATA% 也不可写 → %TEMP%\GunnerSight\config（保命：能启动，设置不持久）。
    """
    portable = get_config_file().parent
    if _is_writable(portable):
        return portable

    logger.info(f"[ConfigManager] 便携配置目录不可写: {portable}，降级数据目录")
    fallback = get_fallback_data_dir() / "config"
    if _is_writable(fallback):
        _seed_config_from(portable / "config.json", fallback / "config.json")
        return fallback

    temp_fallback = Path(tempfile.gettempdir()) / "GunnerSight" / "config"
    logger.info(f"[ConfigManager] %APPDATA% 不可写，最终降级到 {temp_fallback}")
    _seed_config_from(portable / "config.json", temp_fallback / "config.json")
    return temp_fallback


def _default_angle_meter_profile() -> dict:
    """角度仪默认配置。各精度方案独立保存，可切换。"""
    return {
        "pitch_min": -80.0, "pitch_max": 80.0,
        "calibrations": {},
        "active_calibration_point_count": 5,
        "linked_vehicles": [], "auto_reset": False,
        "firing_table": []
    }


def _default_angle_meter_segment() -> dict:
    """angle_meter 配置段默认值单一工厂（空房子原则：profiles 为空，用户自行创建）"""
    return {
        "enabled": False, "current_profile": "",
        "profiles": {},
        "hotkeys": {
            "toggle": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "pause": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "calibrate": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "reset": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "up": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "down": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
        }
    }


def _default_distance_meter_segment() -> dict:
    """distance_meter 配置段默认值（空房子原则：默认禁用，无默认热键，无标定数据）"""
    return {
        "enabled": False,
        "scale_meters": 300,
        "calibrated_pixels": 0,
        "pixels_per_meter": 0,
        "calibration_direction": "",
        "overlay_offset_x": 100,
        "overlay_offset_y": 100,
        "hotkeys": {
            "toggle": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "record": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "measure": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            "modifier": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
        }
    }


class ConfigBaseMixin:
    """base 配置管理 mixin"""

    def __init__(self, config_dir: str | None = None):
        # 设置配置目录（P5：便携优先；只读安装降级 %APPDATA%，再不行 %TEMP%）
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = _resolve_portable_config_dir()
        self.config_file = self.config_dir / "config.json"
        self.resources_dir = get_app_base_dir() / "resources"

        # 确保目录存在（P4：只读环境下创建失败绝不阻断启动，仅记录）
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.info(f"[ConfigManager] 创建配置目录失败: {self.config_dir} ({e})")
        try:
            self.resources_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.info(f"[ConfigManager] 创建资源目录失败: {self.resources_dir} ({e})")

        # 配置数据（初始为最小骨架，load_config 时从 config.json 加载）
        self._config = self._get_minimal_skeleton()

        # 防抖保存
        self._save_timer = None
        self._save_token = None  # 当前 Timer 的身份令牌：过期回调不得清掉新 Timer 的引用
        self._save_lock = threading.Lock()

        # 配置变更回调（统一通知所有监听者，替代到处手动调 refresh）
        self._on_change_callbacks = []

        # 启动期需要告知用户的恢复提示（P6：配置损坏回退；main 启动后弹一次）
        self.recovery_notices: list[str] = []

        # M3：射表 profile 缓存 {name: (table 引用, BallisticProfile)}。
        # 射表查询挂在 angle_changed（鼠标移动级），每次重建 profile 要做
        # 解析+排序+PCHIP 求导。用 table 引用（is）判有效：set_firing_table
        # 换 list 对象即自动失效，无需版本号。
        self._firing_profile_cache: dict = {}

        # 加载配置
        self.load_config()

    def _get_minimal_skeleton(self) -> dict:
        """最小安全骨架：程序启动必需的顶层键，缺失时不崩溃"""
        return {
            "my_beloved": "Xiaocheng",
            "version": "1.0",
            "global_settings": {
                "scale": 100.0, "offset_x": 0, "offset_y": 0,
                "overlay_opacity": 1.0, "overlay_visible": True,
                "wheel_offset_x": 0, "wheel_offset_y": 0,
                # 出厂兜底（对最终用户）：中性无倾向值——深主题用浅色、浅主题用深色。
                # 用户在适配设置改过后存进自己的 CFG，运行时走用户值。
                "accent_dark": "#EBEBEC", "accent_light": "#1D1D1F",
            },
            "hotkeys": {
                "toggle_overlay": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
                "cycle_magnification": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
                "invert_colors": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
                "reset_magnification": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
                "toggle_ui": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
            },
            "vehicles": {},
            "current_state": {
                "vehicle": "", "ammo_type": "", "magnification_index": 0,
            },
            "tags": [],
            "theme": "dark",
            "angle_meter": _default_angle_meter_segment(),
            "distance_meter": _default_distance_meter_segment(),
            "magnifier": {
                "enabled": False,
                "zoom": 2.0,
                "radius": 200,
                "hotkeys": {
                    "toggle": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
                    "zoom_in": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
                    "zoom_out": {"key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"},
                },
            },
            "squad_macro": {"enabled": False, "name": "", "locked": False, "interval": 100},
            "mascot": {"enabled": False, "volume": 0.225, "persistent": False},
            "ui_state": {"splitter_sizes": {}},
        }

    def load_config(self) -> bool:
        """从文件加载配置（明文JSON）。"""
        if self.config_file.exists():
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    loaded = json.load(f)
                self._merge_config(self._config, loaded)
                # 受保护字段兜底（只在顶层执行，不进递归）：强制存在，用户值优先。
                for key, default_val in _PROTECTED_CONFIG_KEYS.items():
                    self._config.setdefault(key, default_val)
                return True
            except Exception as e:
                logger.info(f"[ConfigManager] config.json 加载失败: {e}，备份并回退最小骨架")
                # P6：原文件必须先"留痕"（备份/改名/恢复副本至少一样成功）才允许写骨架覆盖；
                # 全部失败则原文件原地保留，本次以默认配置运行，绝不静默覆盖用户数据。
                if self._recover_from_corrupt_config():
                    self._config = self._get_minimal_skeleton()
                    self.save_config()
                else:
                    self._config = self._get_minimal_skeleton()
                return False

        # 安全回退：最小骨架
        self._config = self._get_minimal_skeleton()
        self.save_config()
        return False

    def _recover_from_corrupt_config(self) -> bool:
        """P6：config.json 损坏时的安全回退。

        返回 True = 原内容已安全留痕，调用方可写骨架覆盖；False = 原文件原地未动。
        每一步失败都写日志，成功路径登记 recovery_notices（启动后弹一次提示）。
        """
        import datetime

        original_bytes = None
        try:
            original_bytes = self.config_file.read_bytes()
        except Exception as e:
            logger.info(f"[ConfigManager] 读取损坏的 config.json 内容失败: {e}")
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1) 优先：rename 到 backups/（历史行为）
        try:
            import os
            backup_dir = self.config_file.parent.parent / "backups"
            os.makedirs(backup_dir, exist_ok=True)
            backup = backup_dir / f"config.corrupt_{ts}"
            self.config_file.rename(backup)
            logger.info(f"[ConfigManager] 原 config.json 已备份到 {backup}")
            self.recovery_notices.append(f"配置文件损坏，已备份到 {backup} 并恢复默认配置。")
            return True
        except Exception as e:
            logger.info(f"[ConfigManager] 备份 config.json 到 backups/ 失败: {e}")

        # 2) 次选：同目录改名（backups 不可用但配置目录可写时）
        try:
            same_dir = self.config_file.with_name(f"config.corrupt_{ts}")
            self.config_file.rename(same_dir)
            logger.info(f"[ConfigManager] 原 config.json 已改名为 {same_dir}")
            self.recovery_notices.append(f"配置文件损坏，已保留为 {same_dir.name} 并恢复默认配置。")
            return True
        except Exception as e:
            logger.info(f"[ConfigManager] 同目录改名保留 config.json 失败: {e}")

        # 3) 保底：原内容写成恢复副本（配置目录优先，%TEMP% 兜底）
        if original_bytes is not None:
            for base in (self.config_file.parent, Path(tempfile.gettempdir())):
                try:
                    copy = base / f"gunnersight_config.corrupt_{ts}"
                    copy.write_bytes(original_bytes)
                    logger.info(f"[ConfigManager] 损坏配置的恢复副本已写入 {copy}")
                    self.recovery_notices.append(f"配置文件损坏，恢复副本在 {copy}，已加载默认配置。")
                    return True
                except Exception as e:
                    logger.info(f"[ConfigManager] 写恢复副本到 {base} 失败: {e}")

        # 4) 全部失败：原文件原地保留，绝不覆盖
        logger.warning("[ConfigManager] 损坏的 config.json 无法留痕，保留原文件不覆盖，本次以默认配置运行")
        self.recovery_notices.append("配置文件损坏且无法备份，已保留原文件、本次以默认配置运行。请手动迁移 config.json。")
        return False

    def _merge_config(self, default: dict, loaded: dict):
        """递归合并配置，保留loaded中的值，补充default中的新字段"""
        for key, value in default.items():
            if key not in loaded or loaded[key] is None:
                loaded[key] = value
            elif isinstance(value, dict) and isinstance(loaded[key], dict):
                self._merge_config(value, loaded[key])
        self._config = loaded
        # 墓碑清理：删掉历史遗留字段（代码里没人读，防止幽灵引用传播）
        if "angle_meter" in self._config:
            self._config["angle_meter"].pop("current_vehicle", None)
            self._config["angle_meter"].pop("vehicles", None)

    def _prepare_config_for_save(self):
        """保存前统一分区顺序"""
        cfg = self._config
        # 统一顶层键顺序
        ordered = {}
        key_order = [
            "my_beloved", "version", "global_settings", "hotkeys", "vehicles",
            "angle_meter", "distance_meter", "squad_macro", "mascot",
        ]
        for k in key_order:
            if k in cfg:
                ordered[k] = cfg[k]
        for k in cfg:
            if k not in ordered:
                ordered[k] = cfg[k]
        self._config = ordered
        return ordered

    def _dump_config(self) -> str:
        """在锁内做保存前整理+序列化。
        与 GUI 写线程并发时 json.dumps 可能撞到 dict 被增删而抛
        RuntimeError: dictionary changed size during iteration；
        此处重试若干次（每次间隔 50ms），避免丢一次自动保存。"""
        self._prepare_config_for_save()
        last_err = None
        for _ in range(3):
            try:
                return json.dumps(self._config, indent=4, ensure_ascii=False)
            except RuntimeError as e:
                last_err = e
                time.sleep(0.05)
        raise last_err

    def save_config(self) -> bool:
        """立即保存配置到文件（序列化+落盘全程在锁内，杜绝与防抖保存并发写坏文件）"""
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
                self._save_token = None
            try:
                data = self._dump_config()
            except Exception as e:
                logger.info(f"序列化配置失败: {e}")
                return False
            try:
                self._atomic_write(data)
                return True
            except Exception as e:
                logger.info(f"保存配置失败: {e}")
                return False

    def _atomic_write(self, data: str):
        """原子写：先写临时文件再 os.replace。
        tmp 名带线程标识（锁外双保险）；finally 保证失败路径不残留 .tmp。"""
        tmp = self.config_file.parent / f"{self.config_file.name}.{threading.get_ident()}.tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(data)
            os.replace(tmp, self.config_file)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def add_on_change_callback(self, cb):
        """注册配置变更回调（任何 set_* 触发 request_save 时自动调用）"""
        self._on_change_callbacks.append(cb)

    def request_save(self):
        """请求保存配置（防抖：500ms）"""
        # 立即通知所有监听者（同步刷新UI，不等磁盘写入）
        for cb in self._on_change_callbacks:
            try:
                cb()
            except Exception:
                pass
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
            token = object()
            timer = threading.Timer(0.5, self._do_deferred_save, args=(token,))
            timer.daemon = True
            self._save_timer = timer
            self._save_token = token
            timer.start()

    def _do_deferred_save(self, token):
        """防抖到点后的落盘（Timer 线程）。
        token 不匹配说明自己已被更新的 request_save 取代——不清引用（那是新
        Timer 的），但照常落盘当前状态。"""
        with self._save_lock:
            if self._save_token is token:
                self._save_timer = None
                self._save_token = None
            try:
                data = self._dump_config()
            except Exception as e:
                logger.info(f"序列化配置失败: {e}")
                return
            try:
                self._atomic_write(data)
            except Exception as e:
                logger.info(f"保存配置失败: {e}")

    # ==================== 全局设置 ====================

    def get_global_scale(self) -> float:
        return self._config["global_settings"]["scale"]

    def set_global_scale(self, scale: float):
        self._config["global_settings"]["scale"] = max(1.0, min(1000.0, scale))
        self.request_save()

    def get_global_offset_x(self) -> int:
        return self._config["global_settings"]["offset_x"]

    def set_global_offset_x(self, offset: int):
        self._config["global_settings"]["offset_x"] = offset
        self.request_save()

    def get_global_offset_y(self) -> int:
        return self._config["global_settings"]["offset_y"]

    def set_global_offset_y(self, offset: int):
        self._config["global_settings"]["offset_y"] = offset
        self.request_save()

    def set_global_offset(self, offset_x: int, offset_y: int):
        self._config["global_settings"]["offset_x"] = offset_x
        self._config["global_settings"]["offset_y"] = offset_y
        self.request_save()

    def get_display_resolution(self):
        """用户标注的当前屏幕分辨率 (w,h)。[0,0] 表示自动检测真实屏幕。"""
        rs = self._config["global_settings"].get("display_resolution")
        if not rs or len(rs) != 2:
            return (0, 0)
        return (int(rs[0]), int(rs[1]))

    def set_display_resolution(self, width: int, height: int):
        self._config["global_settings"]["display_resolution"] = [int(width), int(height)]
        self.request_save()

    def get_adapt_mode(self) -> str:
        """preset=按分辨率档预设；custom=手动 sx/sy"""
        return self._config["global_settings"].get("adapt_mode", "preset")

    def set_adapt_mode(self, mode: str):
        self._config["global_settings"]["adapt_mode"] = mode if mode in ("preset", "custom") else "preset"
        self.request_save()

    def get_sx_override(self) -> float:
        return float(self._config["global_settings"].get("sx_override", 0.0))

    def set_sx_override(self, v: float):
        self._config["global_settings"]["sx_override"] = float(v)
        self.request_save()

    def get_sy_override(self) -> float:
        return float(self._config["global_settings"].get("sy_override", 0.0))

    def set_sy_override(self, v: float):
        self._config["global_settings"]["sy_override"] = float(v)

    def get_sx_adapt_mode(self) -> str:
        """横向适配逻辑：expand=增加/拓宽视野(等比)；stretch=拉伸/图像拉伸(非等比)"""
        return self._config["global_settings"].get("sx_adapt_mode", "expand")

    def set_sx_adapt_mode(self, mode: str):
        self._config["global_settings"]["sx_adapt_mode"] = mode if mode in ("expand", "stretch") else "expand"
        self.request_save()

    def get_sy_adapt_mode(self) -> str:
        """竖向适配逻辑：expand=增加/拓宽视野(等比)；stretch=拉伸/图像拉伸(非等比)"""
        return self._config["global_settings"].get("sy_adapt_mode", "expand")

    def set_sy_adapt_mode(self, mode: str):
        self._config["global_settings"]["sy_adapt_mode"] = mode if mode in ("expand", "stretch") else "expand"
        self.request_save()

    def get_selected_screen(self) -> str:
        return self._config["global_settings"].get("selected_screen", "")

    def set_selected_screen(self, name: str):
        self._config["global_settings"]["selected_screen"] = str(name)
        self.request_save()

    def get_overlay_opacity(self) -> float:
        return self._config["global_settings"].get("overlay_opacity", 1.0)

    def set_overlay_opacity(self, opacity: float):
        self._config["global_settings"]["overlay_opacity"] = max(0.1, min(1.0, opacity))
        self.request_save()

    def get_overlay_visible(self) -> bool:
        return self._config["global_settings"].get("overlay_visible", True)

    def _set_overlay_visible(self, visible: bool):
        self._config["global_settings"]["overlay_visible"] = visible
        self.request_save()

    # ==================== 热键 ====================

    def get_hotkey(self, action: str) -> dict:
        return self._config.get("hotkeys", {}).get(action, {
            "key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"
        })

    def set_hotkey(self, action: str, key: str, trigger: str = "keydown", slot: int = 1):
        hk = self._config.setdefault("hotkeys", {}).setdefault(action, {
            "key1": "", "trigger1": "toggle", "key2": "", "trigger2": "toggle"
        })
        hk[f"key{slot}"] = key
        hk[f"trigger{slot}"] = trigger
        self.request_save()

    def get_all_hotkeys(self) -> dict:
        return self._config.get("hotkeys", {})

    # ==================== 当前状态 ====================

    def get_current_state(self) -> dict:
        return self._config.get("current_state", {})

    def _set_current_vehicle(self, vehicle_name: str | None):
        state = self._config.setdefault("current_state", {})
        state["vehicle"] = vehicle_name
        # 级联：切换载具后，弹种/倍率必须无条件重置为新载具的有效值
        # （新载具无弹种时置 None/0，严禁残留旧载具数据）
        vehicles = self._config.get("vehicles", {})
        ammo_types = vehicles.get(vehicle_name, {}).get("ammo_types", {}) if vehicle_name in vehicles else {}
        if ammo_types:
            first_ammo = next(iter(ammo_types))
            state["ammo_type"] = first_ammo
            state["magnification_index"] = 0
        else:
            state["ammo_type"] = None
            state["magnification_index"] = 0
        self.request_save()

    def _set_current_ammo_type(self, ammo_name: str | None):
        self._config.setdefault("current_state", {})["ammo_type"] = ammo_name
        # 不重置倍率索引，继承当前倍率（越界由 state_machine 处理）
        self.request_save()

    def _set_current_magnification_index(self, index: int):
        self._config.setdefault("current_state", {})["magnification_index"] = index
        self.request_save()

    def cycle_magnification(self):
        state = self._config.get("current_state", {})
        vehicle = state.get("vehicle", "")
        vehicles = self._config.get("vehicles", {})
        if vehicle in vehicles:
            mags = vehicles[vehicle].get("magnifications", [])
            if mags:
                cur = state.get("magnification_index", 0)
                new_idx = (cur + 1) % len(mags)
                state["magnification_index"] = new_idx
                self.request_save()
                return new_idx
        return 0

    def get_current_crosshair(self) -> str | None:
        """返回当前准星的绝对路径（拼接 resources 目录，统一正斜杠）
        读 crosshairs dict：ammo_types[ammo].crosshairs[label].path
        """
        state = self._config.get("current_state", {})
        vehicle = state.get("vehicle", "")
        ammo = state.get("ammo_type", "")
        idx = state.get("magnification_index", 0)
        vehicles = self._config.get("vehicles", {})
        if vehicle not in vehicles:
            return None
        v = vehicles[vehicle]
        mags = v.get("magnifications", [])
        if not (0 <= idx < len(mags)):
            return None
        label = mags[idx].get("label", "")
        ammo_data = v.get("ammo_types", {}).get(ammo, {})
        crosshairs = ammo_data.get("crosshairs", {})
        entry = crosshairs.get(label, {})
        rel = entry.get("path", "")
        if not rel:
            return ""
        rel = rel.replace("\\", "/")
        return str(self.resources_dir / rel).replace("\\", "/")

    # ==================== 主题 ====================

    def get_theme(self) -> str:
        return self._config.get("theme", "dark")

    def get_accent_dark(self) -> str:
        """深色主题强调色（出厂默认见 global_settings 模板）"""
        return self._config["global_settings"]["accent_dark"]

    def set_accent_dark(self, hexc: str):
        self._config["global_settings"]["accent_dark"] = hexc
        self.request_save()

    def get_accent_light(self) -> str:
        """浅色主题强调色（出厂默认见 global_settings 模板）"""
        return self._config["global_settings"]["accent_light"]

    def set_accent_light(self, hexc: str):
        self._config["global_settings"]["accent_light"] = hexc
        self.request_save()

    def get_accent(self, theme: str | None = None) -> str:
        """当前（或指定）主题生效的强调色"""
        if theme is None:
            theme = self.get_theme()
        return self.get_accent_light() if theme == "light" else self.get_accent_dark()

    def get_on_accent_text(self) -> str:
        """当前主题强调色底上的文字色（与主界面 on_accent_text 一致）"""
        return self._theme_palette()["on_accent_text"]

    def _theme_palette(self) -> dict:
        """当前主题的界面调色板"""
        return THEME_LIGHT if self.get_theme() == "light" else THEME_DARK

    # ---------- 滚轮悬浮窗位置偏移 ----------
    # 滚轮三个 overlay 整体偏移 (x, y) px；默认贴屏幕右边垂直居中
    def get_wheel_offset(self):
        g = self._config["global_settings"]
        return g.get("wheel_offset_x", 0), g.get("wheel_offset_y", 0)

    def set_wheel_offset(self, x: int, y: int):
        self._config["global_settings"]["wheel_offset_x"] = int(x)
        self._config["global_settings"]["wheel_offset_y"] = int(y)
        self.request_save()

    def get_splitter_sizes(self, name: str, default=None):
        """获取QSplitter保存的尺寸，不存在返回default"""
        return self._config.get("ui_state", {}).get("splitter_sizes", {}).get(name, default)

    def set_splitter_sizes(self, name: str, sizes: list):
        """保存QSplitter尺寸"""
        if "ui_state" not in self._config:
            self._config["ui_state"] = {}
        if "splitter_sizes" not in self._config["ui_state"]:
            self._config["ui_state"]["splitter_sizes"] = {}
        self._config["ui_state"]["splitter_sizes"][name] = list(sizes)
        self.request_save()

    def set_theme(self, theme: str):
        self._config["theme"] = theme
        self.request_save()

    # ==================== 工具 ====================

    def unbind_crosshair(self, crosshair_name: str) -> int:
        """解除所有载具/弹种/倍率对指定图片的绑定，返回解除数量
        覆盖：准星图片(crosshairs.path) + 载具图片(base_ui) + 弹种图片(ammo_ui)"""
        count = 0
        vehicles = self._config.get("vehicles", {})
        for v_data in vehicles.values():
            # 载具图片 base_ui
            if v_data.get("base_ui") == crosshair_name:
                v_data["base_ui"] = ""
                count += 1
            for a_data in v_data.get("ammo_types", {}).values():
                # 弹种图片 ammo_ui
                if a_data.get("ammo_ui") == crosshair_name:
                    a_data["ammo_ui"] = ""
                    count += 1
                # 准星图片
                crosshairs = a_data.get("crosshairs", {})
                for entry in crosshairs.values():
                    if entry.get("path") == crosshair_name:
                        entry["path"] = ""
                        count += 1
        if count > 0:
            self.request_save()
        return count

    def get_crosshair_reference_index(self) -> dict[str, list[str]]:
        """构建资源引用倒排索引：{图片相对路径: [载具名, ...]}（载具名不去重）
        统计范围：准星图片(crosshairs.path) + 载具图片(base_ui) + 弹种图片(ammo_ui)"""
        index: dict[str, list[str]] = {}
        vehicles = self._config.get("vehicles", {})
        for vname, v_data in vehicles.items():
            # 载具图片 base_ui
            base_ui = v_data.get("base_ui", "").replace("\\", "/")
            if base_ui:
                index.setdefault(base_ui, []).append(vname)
            for a_data in v_data.get("ammo_types", {}).values():
                # 弹种图片 ammo_ui
                ammo_ui = a_data.get("ammo_ui", "").replace("\\", "/")
                if ammo_ui:
                    index.setdefault(ammo_ui, []).append(vname)
                # 准星图片
                crosshairs = a_data.get("crosshairs", {})
                for entry in crosshairs.values():
                    ch = entry.get("path", "").replace("\\", "/")
                    if ch:
                        index.setdefault(ch, []).append(vname)
        return index

    def rename_crosshair_path(self, old_path: str, new_path: str) -> int:
        """批量更新config中所有引用old_path的位置为new_path，返回更新数量
        覆盖：准星图片(crosshairs.path) + 载具图片(base_ui) + 弹种图片(ammo_ui)"""
        count = 0
        vehicles = self._config.get("vehicles", {})
        for v_data in vehicles.values():
            # 载具图片 base_ui
            if v_data.get("base_ui") == old_path:
                v_data["base_ui"] = new_path
                count += 1
            for a_data in v_data.get("ammo_types", {}).values():
                # 弹种图片 ammo_ui
                if a_data.get("ammo_ui") == old_path:
                    a_data["ammo_ui"] = new_path
                    count += 1
                # 准星图片
                crosshairs = a_data.get("crosshairs", {})
                for entry in crosshairs.values():
                    if entry.get("path") == old_path:
                        entry["path"] = new_path
                        count += 1
        if count > 0:
            self.request_save()
        return count
