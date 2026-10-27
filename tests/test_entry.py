"""入口与账本：Win32 调用签名（RULES §9）+ 版本号同源（P3-1）。

这个文件里的东西没有任何运行时症状——错了也照常工作，直到某台机器上恰好
踩中。所以只能靠可执行检查兜住，靠人眼 review 兜不住。

**Win32 签名是门禁盲区**
ruff 不查 ctypes，运行时不报错，类型也不报——**未声明 argtypes 的 Win32 调用
在 64 位上会静默截断句柄，而程序照常工作**，直到某个用户的窗口句柄恰好落在
高地址。这是"现在能用纯属碰巧"那一类缺陷。两条契约：
1. `core/win32_utils.py` 是唯一入口，其余模块只准
   `from core.win32_utils import user32`；
2. 凡是被业务代码调用的 API，必须在 win32_utils 里显式声明 argtypes/restype。

**版本号只有一个权威**
APP_VERSION 是唯一真源，pyproject 从它同步。此前靠人工 + 注释约定，
tests/ 下 grep APP_VERSION 零命中，无机械校验——改一处忘另一处不会有任何症状。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 允许直接出现 ctypes.windll.user32 的文件，每个都要有理由：
# - core/win32_utils.py：唯一定义处，别处一律从这里导入
# - tools/ui_access_test.py：独立的界面探针工具，不 import core（故意与主程序解耦）
# - main.py：启动失败路径的 MessageBox，跑在"core 可能已经坏了"的时候，
#   多依赖一个项目模块就多一种连报错都弹不出来的可能
# - 本文件用正则描述违规形态，留一条以免将来改动后自匹配
ALLOWED_DIRECT = {
    "core/win32_utils.py",
    "tools/ui_access_test.py",
    "main.py",
    "tests/test_entry.py",
}

# 业务代码实际调用到的、必须已声明签名的 API
REQUIRED_SIGNATURES = [
    "SetWindowDisplayAffinity",  # 放大镜把自己从截屏里排除
    "GetSystemMetrics",          # 屏幕/虚拟屏幕尺寸
    "SendInput",                 # 按键与鼠标注入（原子序列）
    "EnumWindows",
    "EnumThreadWindows",
    "SendMessageTimeoutW",
    "GetWindowLongW",
    "SetWindowLongW",
    "GetCursorPos",
    "WindowFromPoint",
    "GetParent",
    "GetWindowThreadProcessId",
]


def _scan_py_files():
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(("backups/", "dist/", ".venv/", "build/")):
            continue
        yield rel, p


# ---------------------------------------------------------------- Win32

def test_no_direct_windll_user32_outside_entry_point():
    """除白名单外，不允许各自 ctypes.windll.user32 / WinDLL('user32')。"""
    pat = re.compile(r"ctypes\.windll\.user32|WinDLL\(\s*[\"']user32")
    offenders = []
    for rel, p in _scan_py_files():
        if rel in ALLOWED_DIRECT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            # 注释里提到写法是允许的（说明为什么禁止时要引原文）
            if pat.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{rel}:{i}")
    assert not offenders, (
        "发现绕过 core.win32_utils 的 Win32 直调（签名无处声明，64 位会截断句柄）：\n"
        + "\n".join(offenders)
    )


def test_used_win32_apis_declare_signatures():
    """业务代码调到的 API 必须已声明 argtypes——没声明就是 64 位定时炸弹。"""
    from core import win32_utils

    missing = [
        name for name in REQUIRED_SIGNATURES
        if getattr(win32_utils.user32, name).argtypes is None
    ]
    assert not missing, (
        f"这些 Win32 API 未声明 argtypes/restype，64 位下句柄会被截断成 C int：{missing}"
    )


def test_return_types_are_explicit():
    """返回 BOOL/DWORD 的 API，restype 必须明确，别吃 ctypes 默认的 c_int。"""
    import ctypes
    from ctypes import wintypes

    from core import win32_utils

    assert win32_utils.user32.SetWindowDisplayAffinity.restype is wintypes.BOOL
    assert win32_utils.user32.GetSystemMetrics.restype is ctypes.c_int


# ---------------------------------------------------------------- 版本号账本

def test_app_version_pyproject_sync():
    """pyproject version 必须等于 APP_VERSION 去掉前缀 V。"""
    from gui.tabs.info_tab import APP_VERSION

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "pyproject.toml 缺 [project] version 行"
    assert m.group(1) == APP_VERSION.lstrip("V"), (
        f"版本号不同源：pyproject={m.group(1)} APP_VERSION={APP_VERSION}")
