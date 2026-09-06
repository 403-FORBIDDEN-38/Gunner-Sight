"""
资源管理模块 (Resource Manager)

负责准星图片的导入、删除、重命名及资源目录管理。
仅保留实际被调用的方法，避免墓碑代码。
"""

import shutil
from pathlib import Path
from typing import List, Optional

from core.config_manager import get_app_base_dir


class ResourceManager:
    """资源管理器 - 管理所有准星图片资源"""

    def __init__(self, resources_dir: str = None):
        if resources_dir:
            self.resources_dir = Path(resources_dir)
        else:
            self.resources_dir = get_app_base_dir() / "resources"
        self.resources_dir.mkdir(parents=True, exist_ok=True)

    def get_resources_dir(self) -> Path:
        return self.resources_dir

    def list_resources(self) -> List[str]:
        """列出所有资源文件名（递归扫描子文件夹，返回相对路径）"""
        if not self.resources_dir.exists():
            return []
        extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
        result = []
        for f in self.resources_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in extensions:
                rel = f.relative_to(self.resources_dir)
                # 排除 assets/ 目录（mascot/fonts 等内部资源，不进资源库）
                if rel.parts and rel.parts[0] == "assets":
                    continue
                result.append(str(rel))
        return sorted(result)

    def get_resource_path(self, filename: str) -> Optional[str]:
        """获取资源文件的完整路径"""
        path = self.resources_dir / filename
        if path.exists():
            return str(path)
        return None

    def import_resource(self, source_path: str, new_name: str = None) -> Optional[str]:
        """
        导入资源文件到资源目录。
        若资源库中已存在内容完全相同的图片，直接复用，不创建副本。
        """
        try:
            source = Path(source_path)
            if not source.exists() or not source.is_file():
                return None
            if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}:
                return None

            # 先比较文件大小快速排除，大小相同才计算 MD5（避免不必要的全文件读取）
            source_size = source.stat().st_size
            source_hash = self._file_md5(source)
            for existing in self.resources_dir.rglob("*"):
                if not (existing.is_file() and existing.suffix.lower() in
                        {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}):
                    continue
                if existing.stat().st_size != source_size:
                    continue
                if self._file_md5(existing) == source_hash:
                    return existing.name

            # 确定目标文件名
            if new_name:
                dest_name = new_name
                if not Path(dest_name).suffix:
                    dest_name += source.suffix
            else:
                dest_name = source.name

            dest = self.resources_dir / dest_name

            # 处理重名文件（仅文件名重名但内容不同时才加后缀）
            if dest.exists():
                stem = Path(dest_name).stem
                suffix = Path(dest_name).suffix
                counter = 1
                while True:
                    dest = self.resources_dir / f"{stem}_{counter}{suffix}"
                    if not dest.exists():
                        break
                    counter += 1

            shutil.copy2(source, dest)
            return dest.name

        except Exception as e:
            print(f"导入资源失败: {e}")
            return None

    @staticmethod
    def _file_md5(filepath: Path, chunk_size: int = 8192) -> str:
        """计算文件 MD5 哈希"""
        import hashlib
        h = hashlib.md5()
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()

    def remove_resource(self, filename: str) -> bool:
        """删除资源文件"""
        try:
            path = self.resources_dir / filename
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            print(f"删除资源失败: {e}")
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
            return True
        except Exception as e:
            print(f"重命名资源失败: {e}")
            return False
