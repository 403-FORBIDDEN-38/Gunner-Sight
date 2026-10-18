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

    def __init__(self, resources_dir: str | None = None):
        if resources_dir:
            self.resources_dir = Path(resources_dir)
        else:
            self.resources_dir = get_app_base_dir() / "resources"
        self.resources_dir.mkdir(parents=True, exist_ok=True)
        self._resources_cache = None  # 资源列表缓存，None表示需要重新扫描

    def get_resources_dir(self) -> Path:
        return self.resources_dir

    def list_resources(self) -> list[str]:
        """列出所有资源文件名（递归扫描子文件夹，返回相对路径）。
        性能优化：带缓存，资源目录变化时（import/remove/rename）才重新扫描。"""
        if self._resources_cache is not None:
            return self._resources_cache
        if not self.resources_dir.exists():
            self._resources_cache = []
            return []
        extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
        result = []
        for f in self.resources_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in extensions:
                rel = f.relative_to(self.resources_dir)
                # 排除 assets/ 目录（mascot/fonts 等内部资源，不进资源库）
                if rel.parts and rel.parts[0] == "assets":
                    continue
                result.append(str(rel).replace("\\", "/"))
        self._resources_cache = sorted(result)
        return self._resources_cache

    def _invalidate_resources_cache(self):
        """清除资源列表缓存（资源目录变化时调用）"""
        self._resources_cache = None

    def get_resource_path(self, filename: str) -> str | None:
        """获取资源文件的完整路径"""
        path = self.resources_dir / filename
        if path.exists():
            return str(path)
        return None

    def import_resource(self, source_path: str, new_name: str | None = None) -> str | None:
        """
        导入资源文件到资源目录。
        - 若源文件已在资源目录内，直接返回其相对路径（尊重用户选择的具体文件）
        - 若从外部导入，复制到资源根目录，同名直接覆盖
        """
        try:
            source = Path(source_path).resolve()
            if not source.exists() or not source.is_file():
                return None
            if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}:
                return None

            # 已在资源目录内 → 直接返回相对路径
            # 注意：self.resources_dir 也要 resolve，否则 Windows 上路径格式不一致会导致 relative_to 失败
            resources_dir = self.resources_dir.resolve()
            try:
                return source.relative_to(resources_dir).as_posix()
            except ValueError:
                logger.info(f"[import_resource] source不在资源目录内: source={source}, resources_dir={resources_dir}")
                pass  # 不在资源目录内，继续外部导入

            # 外部导入 → 复制到资源根目录，同名覆盖
            dest_name = new_name if new_name else source.name
            if not Path(dest_name).suffix:
                dest_name += source.suffix
            dest = self.resources_dir / dest_name
            shutil.copy2(source, dest)
            self._invalidate_resources_cache()
            return dest.relative_to(self.resources_dir).as_posix()

        except Exception as e:
            logger.info(f"导入资源失败: {e}")
            return None

    def remove_resource(self, filename: str) -> bool:
        """删除资源文件"""
        try:
            path = self.resources_dir / filename
            if path.exists():
                path.unlink()
                self._invalidate_resources_cache()
                return True
            return False
        except Exception as e:
            logger.info(f"删除资源失败: {e}")
            return False

    def rename_resource(self, old_name: str, new_name: str) -> bool:
        """重命名资源文件"""
        try:
            old_path = self.resources_dir / old_name
            if not old_path.exists():
                return False
            if not Path(new_name).suffix:
                new_name += old_path.suffix
            new_path = self.resources_dir / new_name
            if new_path.exists():
                return False
            old_path.rename(new_path)
            self._invalidate_resources_cache()
            return True
        except Exception as e:
            logger.info(f"重命名资源失败: {e}")
            return False
