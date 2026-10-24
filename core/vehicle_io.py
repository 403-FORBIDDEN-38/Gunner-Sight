"""
载具导入导出模块。

.gsv 文件本质是 zip，内部结构：
  manifest.json  — 载具数据 + 热键 + 图片清单
  images/        — 准星图片（保持 resources/ 下的相对路径）
  README.txt     — 导出元信息（可选）

导入时图片按目录级处理：每个目录作为整体，要么全复用要么全改名。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from core.logger import logger

FORMAT_VERSION = 1
_WINDOWS_RESERVED = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str) -> str:
    """载具名中的 Windows 保留字符替换为下划线。"""
    return _WINDOWS_RESERVED.sub("_", name)


def _collect_crosshair_paths(vehicle_data: dict) -> list[str]:
    """收集载具所有倍率的 crosshair 路径，去重，跳过空字符串。"""
    paths: set[str] = set()
    for ammo in vehicle_data.get("ammo_types", {}).values():
        crosshairs = ammo.get("crosshairs", {})
        for entry in crosshairs.values():
            ch = entry.get("path", "")
            if ch:
                paths.add(ch)
    return sorted(paths)


# ============================================================
# 导出
# ============================================================
def export_vehicle(
    config: Any,
    resources_dir: Path,
    vehicle_name: str,
    output_path: Path,
) -> tuple[bool, str]:
    """
    导出单个载具为 .gsv 文件。

    返回 (成功, 消息)。
    """
    vehicles = config._config.get("vehicles", {})
    if vehicle_name not in vehicles:
        return False, f"载具 '{vehicle_name}' 不存在"

    vehicle_data = json.loads(json.dumps(vehicles[vehicle_name]))  # deep copy
    crosshairs = _collect_crosshair_paths(vehicle_data)

    # 弹种热键
    ammo_hotkeys = config._config.get("hotkeys", {}).get("ammo_types", {}).get(vehicle_name, {})

    # 检查图片缺失
    missing: list[str] = []
    existing: list[str] = []
    for rel in crosshairs:
        if (resources_dir / rel).exists():
            existing.append(rel)
        else:
            missing.append(rel)

    manifest = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "vehicle": vehicle_data,
        "ammo_hotkeys": ammo_hotkeys,
        "images": existing,
        "missing": missing,
    }

    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr(
                "README.txt",
                f"GunnerSight Vehicle Package\n"
                f"Exported: {manifest['exported_at']}\n"
                f"Vehicle: {vehicle_name}\n"
                f"Images: {len(existing)} (missing: {len(missing)})\n",
            )
            for rel in existing:
                src = resources_dir / rel
                zf.write(src, f"images/{rel}")
    except Exception as e:
        logger.exception(f"导出载具失败: {e}")
        return False, f"导出失败: {e}"

    msg = f"已导出 '{vehicle_name}'（{len(existing)} 张图片）"
    if missing:
        msg += f"，{len(missing)} 张图片缺失已跳过"
    return True, msg


# ============================================================
# 导入 — 目录级处理
# ============================================================
def _resolve_vehicle_name(config: Any, base_name: str) -> str:
    """载具名冲突处理：原名 → 原名_导入 → 原名_导入2 ..."""
    vehicles = config._config.get("vehicles", {})
    if base_name not in vehicles:
        return base_name
    candidate = f"{base_name}_导入"
    counter = 2
    while candidate in vehicles:
        candidate = f"{base_name}_导入{counter}"
        counter += 1
    return candidate


def _resolve_dir_name(resources_dir: Path, dir_rel: str) -> str:
    """
    目录名冲突处理：D → D_导入 → D_导入2 ...
    只改最后一级目录名，保留父目录路径。
    """
    target = resources_dir / dir_rel
    if not target.exists():
        return dir_rel

    p = Path(dir_rel)
    parent = p.parent
    name = p.name

    candidate = str(parent / f"{name}_导入").replace("\\", "/")
    counter = 2
    while (resources_dir / candidate).exists():
        candidate = str(parent / f"{name}_导入{counter}").replace("\\", "/")
        counter += 1
    return candidate


def _md5_file(path: Path) -> str:
    """计算文件 MD5。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_identical(local_dir: Path, pkg_dir: Path, files: list[str]) -> bool:
    """
    对比包内目录和本地目录：包内所有文件本地都有且 MD5 全部一致 → True。
    本地额外文件不影响判断。
    """
    for fname in files:
        local_file = local_dir / fname
        pkg_file = pkg_dir / fname
        if not local_file.exists() or not pkg_file.exists():
            return False
        if _md5_file(local_file) != _md5_file(pkg_file):
            return False
    return True


def _group_by_dir(image_list: list[str]) -> dict[str, list[str]]:
    """
    将图片路径按父目录分组。
    返回 {父目录相对路径: [文件名, ...]}。
    根目录下的文件父目录为空字符串 ""。
    """
    dirs: dict[str, list[str]] = {}
    for rel in image_list:
        p = Path(rel)
        parent = str(p.parent).replace("\\", "/")
        if parent == ".":
            parent = ""
        dirs.setdefault(parent, []).append(p.name)
    return dirs


def _process_image_dirs(
    images_tmp: Path,
    resources_dir: Path,
    image_list: list[str],
) -> tuple[dict[str, str], list[Path]]:
    """
    目录级处理图片导入。

    规则：
    - 本地没有同名目录 → 整目录直接复制
    - 本地有同名目录且所有文件MD5一致 → 跳过，复用本地
    - 本地有同名目录但有文件缺失或MD5不一致 → 整目录改名导入（D_导入）

    返回 (路径映射表 {原相对路径: 新相对路径}, 已复制的文件列表)。
    """
    dir_files = _group_by_dir(image_list)
    path_mapping: dict[str, str] = {}
    copied: list[Path] = []

    resources_root = resources_dir.resolve()
    for dir_rel, files in sorted(dir_files.items()):
        # 路径穿越防护：manifest 是不可信输入，目录条目与文件名都不得越出
        # resources_dir（否则恶意 .gsv 可借导入把文件写到用户磁盘任意位置）
        if dir_rel:
            if not (resources_dir / dir_rel).resolve().is_relative_to(resources_root):
                raise ValueError(f"非法的资源目录条目（越出 resources）: {dir_rel}")
        for fname in files:
            if Path(fname).name != fname:
                raise ValueError(f"非法的资源文件名: {fname}")
        pkg_dir = images_tmp / dir_rel if dir_rel else images_tmp
        local_dir = resources_dir / dir_rel if dir_rel else resources_dir

        # 过滤包内实际存在的文件
        existing_files = [f for f in files if (pkg_dir / f).exists()]
        if not existing_files:
            continue

        if not local_dir.exists():
            # 情况1：本地没有同名目录 → 直接复制，路径不变
            new_dir_rel = dir_rel
        else:
            # 情况2：本地有同名目录 → MD5对比
            if _dir_identical(local_dir, pkg_dir, existing_files):
                # 2a：全部一致 → 跳过，复用本地，路径不变
                for fname in existing_files:
                    rel = f"{dir_rel}/{fname}" if dir_rel else fname
                    path_mapping[rel] = rel
                continue
            else:
                # 2b：有不一致 → 整目录改名导入
                new_dir_rel = _resolve_dir_name(resources_dir, dir_rel)

        # 执行复制（任一步失败 → 回滚本次导入已复制的全部文件：导入是原子操作，
        # 中途失败不留孤儿。异常路径上调用方拿不到本函数的局部复制进度，
        # 所以回滚必须在这里做）
        dst_dir = resources_dir / new_dir_rel if new_dir_rel else resources_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        for fname in existing_files:
            src = pkg_dir / fname
            dst = dst_dir / fname
            try:
                shutil.copy2(src, dst)
            except Exception:
                for done in copied:
                    try:
                        done.unlink()
                    except OSError:
                        pass
                raise
            copied.append(dst)
            rel = f"{dir_rel}/{fname}" if dir_rel else fname
            new_rel = f"{new_dir_rel}/{fname}" if new_dir_rel else fname
            path_mapping[rel] = new_rel

    return path_mapping, copied


def _remap_crosshairs(vehicle_data: dict, mapping: dict[str, str]) -> None:
    """用映射表更新载具内所有 crosshair 路径（原地修改）。"""
    for ammo in vehicle_data.get("ammo_types", {}).values():
        crosshairs = ammo.get("crosshairs", {})
        for entry in crosshairs.values():
            ch = entry.get("path", "")
            if ch and ch in mapping:
                entry["path"] = mapping[ch]


def import_vehicle(
    config: Any,
    resources_dir: Path,
    gsv_path: Path,
) -> tuple[bool, str, str | None]:
    """
    导入 .gsv 文件。

    返回 (成功, 消息, 新载具名)。
    顺序：先图片、后 config。图片失败 config 不动。
    图片按目录级处理：每个目录作为整体，要么全复用要么全改名。
    """
    if not gsv_path.exists():
        return False, f"文件不存在: {gsv_path}", None

    with tempfile.TemporaryDirectory(prefix="gsv_import_") as tmpdir:
        tmp = Path(tmpdir)

        # 1. 解压
        try:
            with zipfile.ZipFile(gsv_path, "r") as zf:
                zf.extractall(tmp)
        except Exception as e:
            return False, f"解压失败: {e}", None

        # 2. 读 manifest（明文 JSON）
        manifest_json_path = tmp / "manifest.json"
        if manifest_json_path.exists():
            try:
                manifest = json.loads(manifest_json_path.read_text(encoding="utf-8"))
            except Exception as e:
                return False, f"manifest.json 解析失败: {e}", None
        else:
            return False, "缺少 manifest.json", None

        if manifest.get("format_version") != FORMAT_VERSION:
            return False, f"不支持的格式版本: {manifest.get('format_version')}", None

        vehicle_data = manifest.get("vehicle", {})
        base_name = vehicle_data.get("name", "")
        if not base_name:
            return False, "manifest 中缺少载具名", None

        # 3. 载具名冲突
        new_name = _resolve_vehicle_name(config, base_name)

        # 4. 目录级图片处理 + 映射表
        image_list = manifest.get("images", [])
        images_tmp = tmp / "images"
        copied: list[Path] = []
        try:
            path_mapping, copied = _process_image_dirs(
                images_tmp, resources_dir, image_list
            )
        except Exception as e:
            # 图片复制失败 → 清理已复制的，中止
            for dst in copied:
                try:
                    dst.unlink()
                except OSError:
                    pass
            logger.exception(f"导入图片失败: {e}")
            return False, f"图片复制失败: {e}", None

        # 5. 用映射表更新 crosshair 路径
        _remap_crosshairs(vehicle_data, path_mapping)
        vehicle_data["name"] = new_name

        # 6. 写入 config（原子写由 save_config 保证）
        try:
            config._config["vehicles"][new_name] = vehicle_data
            ammo_hotkeys = manifest.get("ammo_hotkeys", {})
            if ammo_hotkeys:
                config._config.setdefault("hotkeys", {}).setdefault("ammo_types", {})[new_name] = ammo_hotkeys
            config.save_config()
        except Exception as e:
            # config 写入失败 → 图片成为孤儿但不影响现有数据，不回滚图片
            logger.exception(f"写入 config 失败: {e}")
            return False, f"写入配置失败: {e}", None

    return True, f"已导入 '{new_name}'", new_name
