"""吉祥物资源路径统一入口"""
import os


def get_mascot_dir(resources_dir: str) -> str:
    """返回吉祥物资源目录（assets/mascot）"""
    return os.path.join(resources_dir, "assets/mascot")
