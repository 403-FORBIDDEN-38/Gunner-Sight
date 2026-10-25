"""批次 4 浪 4：P3 账本纪律契约测试。

P3-1：版本号同步守卫。APP_VERSION 是唯一权威，pyproject 从它同步——此前
靠人工 + 注释约定，tests/ 下 grep APP_VERSION 零命中，无机械校验。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_app_version_pyproject_sync():
    """pyproject version 必须等于 APP_VERSION 去掉前缀 V。"""
    from gui.tabs.info_tab import APP_VERSION

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "pyproject.toml 缺 [project] version 行"
    assert m.group(1) == APP_VERSION.lstrip("V"), (
        f"版本号不同源：pyproject={m.group(1)} APP_VERSION={APP_VERSION}")
