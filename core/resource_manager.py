from core.logger import logger

"""
资源管理模块 (Resource Manager)

负责准星图片的导入、删除、重命名及资源目录管理。
仅保留实际被调用的方法，避免墓碑代码。
"""

import shutil
from pathlib import Path

from core.config_manager import get_app_base_dir


class ResourceManager:
    """资源管理器 - 管理所有准星图片资源"""

    def __init__(self, resources_dir: str | None = None, write_dir: str | None = None):
        if resources_dir:
            self.resources_dir = Path(resources_dir)
        else:
            self.resources_dir = get_app_base_dir() / "resources"
        # P1-2：读主路径与写路径分离。便携/可写安装时两者相同；只读安装时
        # write_dir 指向 config 侧 resources（导入/导出不再静默失败）。
        self.write_dir = Path(write_dir) if write_dir else self.resources_dir
        try:
            self.resources_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.info(f"[ResourceManager] 创建资源目录失败: {self.resources_dir} ({e})")
        if self.write_dir != self.resources_dir:
            try:
                self.write_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.info(f"[ResourceManager] 创建资源写入目录失败: {self.write_dir} ({e})")
        self._resources_cache = None  # 资源列表缓存，None表示需要重新扫描

    def get_write_dir(self) -> Path:
        """写路径（导入/导出目标）：只读安装时降级到可写目录。"""
        return self.write_dir

    def get_resources_dir(self) -> Path:
        return self.resources_dir

    def list_resources(self) -> list[str]:
        """列出所有资源文件名（递归扫描子文件夹，返回相对路径）。
        性能优化：带缓存，资源目录变化时（import/remove/rename）才重新扫描。
        P1-2：读主路径 + 写路径取并集（只读安装下用户资源在写路径）。"""
        if self._resources_cache is not None:
            return self._resources_cache
        extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
        dirs = [self.resources_dir]
        if self.write_dir != self.resources_dir:
            dirs.append(self.write_dir)
        result = set()
        for d in dirs:
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() in extensions:
                    rel = f.relative_to(d)
                    # 排除 assets/ 目录（mascot/fonts 等内部资源，不进资源库）
                    if rel.parts and rel.parts[0] == "assets":
                        continue
                    result.add(str(rel).replace("\\", "/"))
        self._resources_cache = sorted(result)
        return self._resources_cache

    def _invalidate_resources_cache(self):
        """清除资源列表缓存（资源目录变化时调用）"""
        self._resources_cache = None

    def get_resource_path(self, filename: str) -> str | None:
        """获取资源文件的完整路径（读主路径优先，写路径兜底）。"""
        for d in (self.resources_dir, self.write_dir):
            path = d / filename
            if path.exists():
                return str(path)
        return None

    def _locate(self, filename: str) -> Path | None:
        """定位资源文件：写路径优先（用户新导入的都在此），读主路径兜底。"""
        for d in (self.write_dir, self.resources_dir):
            path = d / filename
            if path.exists():
                return path
        return None

    def import_resource(self, source_path: str, new_name: str | None = None) -> str | None:
        """
        导入资源文件到资源目录。
        - 若源文件已在资源目录内，直接返回其相对路径（尊重用户选择的具体文件）
        - 若从外部导入，复制到写路径根目录，同名直接覆盖（P1-2：写路径优先可写）
        """
        try:
            source = Path(source_path).resolve()
            if not source.exists() or not source.is_file():
                return None
            if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}:
                return None

            # 已在资源目录内（读主路径或写路径）→ 直接返回相对路径
            for d in (self.resources_dir, self.write_dir):
                try:
                    return source.relative_to(d.resolve()).as_posix()
                except ValueError:
                    continue

            # 外部导入 → 复制到写路径根目录，同名覆盖
            dest_name = new_name if new_name else source.name
            if not Path(dest_name).suffix:
                dest_name += source.suffix
            dest = self.write_dir / dest_name
            shutil.copy2(source, dest)
            self._invalidate_resources_cache()
            return dest.relative_to(self.write_dir).as_posix()

        except Exception as e:
            logger.info(f"导入资源失败: {e}")
            return None

    def remove_resource(self, filename: str) -> bool:
        """删除资源文件（跨读/写路径定位）"""
        try:
            path = self._locate(filename)
            if path is not None:
                path.unlink()
                self._invalidate_resources_cache()
                return True
            return False
        except Exception as e:
            logger.info(f"删除资源失败: {e}")
            return False

    def rename_resource(self, old_name: str, new_name: str) -> bool:
        """重命名资源文件（保持在原所在目录内）"""
        try:
            old_path = self._locate(old_name)
            if old_path is None:
                return False
            if not Path(new_name).suffix:
                new_name += old_path.suffix
            new_path = old_path.parent / new_name
            if new_path.exists():
                return False
            old_path.rename(new_path)
            self._invalidate_resources_cache()
            return True
        except Exception as e:
            logger.info(f"重命名资源失败: {e}")
            return False
