"""文档对账：把 HANDOVER / AGENTS 里的**事实性断言**拿去和代码核对。

为什么需要它：这个项目的文档就是"现状的唯一权威"，而它**已经烂过一次**——
2026-10-08 删掉 `ACCENT` 常量、搬走强调色、做完 SSOT 改造之后，HANDOVER 三个月
没人碰，下一任 agent 会照着过时的文档写出错代码。文档漂移是本项目最贵的失败模式，
比代码 bug 贵：bug 会报错，过时文档不会。

用法：py tools/audit_docs.py        （不一致时退出码 1）
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HAND = (ROOT / "HANDOVER.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

results = []


def check(label, ok, detail=""):
    results.append((label, ok, detail))


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# 1. 版本号三处一致，且文档写的是当前版本
ver = re.search(r'APP_VERSION = "([^"]+)"', read("gui/tabs/info_tab.py")).group(1)
pyproject = re.search(r'version = "([^"]+)"', read("pyproject.toml")).group(1)
check("版本号 info_tab == pyproject.toml", ver.lstrip("V") == pyproject, f"{ver} vs {pyproject}")
check("HANDOVER 标注的版本 = 代码版本", ver in HAND, f"代码 {ver}")

# 2. 窗口宽度 == 启动横幅宽度（这是用户的硬要求）
from PIL import Image  # noqa: E402
banner_w = Image.open(ROOT / "resources/assets/splash/full.png").size[0]
win_w = int(re.search(r"WINDOW_SIZE = \((\d+),", read("gui/main_window.py")).group(1))
check(f"窗口宽度 {win_w} == 横幅宽度 {banner_w}", win_w == banner_w)

# 3. 文档提到"已删除/已搬走"的常量时，代码里确实没有
colors = read("core/colors.py")
for name, should_exist in [("THEME_DARK", True), ("THEME_LIGHT", True),
                           ("OVERLAY_BOX_RGB", True), ("ACCENT", False),
                           ("ACCENT_HOVER", False)]:
    defined = bool(re.search(rf"^{name}\b", colors, re.M))
    if should_exist:
        check(f"colors.py 定义了 {name}", defined, "文档拿它当唯一来源")
    else:
        check(f"colors.py 里 {name} 已删除（文档若提它必须是在提醒'别再用'）",
              not defined or "已删除" in HAND, f"{name} 又回来了？")

# 4. 文档承诺的 SSOT 组件都在
for path, sym in [("gui/widgets.py", "class LinkedSpinSlider"),
                  ("gui/widgets.py", "class FilterListPanel"),
                  ("gui/widgets.py", "def set_silent"),
                  ("gui/wheel_filter.py", "def install_no_wheel_filter"),
                  ("core/state_machine.py", "def add_vehicle"),
                  ("core/overlay.py", "def _adapt_factors"),
                  ("core/config/base.py", "def get_wheel_offset"),
                  ("gui/tabs/vehicle_config_tab.py", "tags_changed = pyqtSignal"),
                  ("gui/tabs/angle_meter_tab.py", "无条件断开旧连接")]:
    check(f"{path}::{sym.split()[-1]} 存在", sym in read(path))

# 4b. §四・五 表格里写死的数字/常量必须和代码一致
check("适配基准 2560×1440 与代码一致", "_resource_w = 2560" in read("core/overlay.py"),
      "overlay.py 里的基准不是 2560")
for name in ("OVERLAY_TEXT", "OVERLAY_BOX_BG_ALPHA", "OVERLAY_BOX_RGB"):
    check(f"文档提到的 {name} 在 colors.py 里", re.search(rf"^{name}\b", colors, re.M) is not None)
for name in ("适配设置", "相关"):
    check(f"导航名 '{name}' 与 main_window 一致", name in read("gui/main_window.py"))

# 5. 文档里的项目内路径都存在
missing = [m.group(1) for m in re.finditer(r"`((?:core|gui|tests|resources|config|docs|backups)/[\w/\.]+)`", HAND)
           if not (ROOT / m.group(1)).exists() and not m.group(1).endswith("/")]
check("HANDOVER 引用的项目内路径都存在", not missing, f"缺失 {sorted(set(missing))[:5]}")

# 6. 备份约定：文档写的快照目录真的存在
snaps = list((ROOT / "backups").glob("GunnerSight_src_*")) if (ROOT / "backups").is_dir() else []
check("文档描述的 backups/GunnerSight_src_* 快照存在", bool(snaps), f"backups/ 下有 {len(snaps)} 个")

# 7. 测试规模红线（AGENTS §4：< 20 个 test function）
nfunc = sum(len(re.findall(r"^def (test_\w+)", (ROOT / p).read_text(encoding="utf-8"), re.M))
            for p in [str(x.relative_to(ROOT)) for x in (ROOT / "tests").glob("test_*.py")])
check(f"测试函数数 {nfunc} ≤ 30（AGENTS §4 红线）", nfunc <= 30)

# 8. 死表达式：HANDOVER 说"应为空"，那就必须是 0（不再去文档里解析数字——那种解析一改措辞就失效）
r = subprocess.run([sys.executable, "-m", "ruff", "check", "--select", "F401,F841,F811",
                    "--output-format", "concise", "core", "gui", "main.py", "tests"],
                   capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
ndead = len([ln for ln in r.stdout.splitlines() if re.search(r"\b(F401|F841|F811)\b", ln)])
check(f"死代码 0 处（ruff F401/F841/F811，实际 {ndead} 处）", ndead == 0,
      "; ".join(r.stdout.splitlines()[:3]))

# 9. 文档没被 markdown 转义污染（下划线/星号被反斜杠转义）
#    反引号内的反斜杠是合法的（可能在演示一条 Windows 路径），所以先剥掉 code span 再查
def _strip_code_spans(text):
    return re.sub(r"`[^`]*`", "", text)


bad = [p for p in ["AGENTS.md", "HANDOVER.md", "CHANGE_LOG.md"]
       if re.search(r"\\[_*]", _strip_code_spans((ROOT / p).read_text(encoding="utf-8")))]
check("文档没有被 markdown 转义污染（`\\_` 之类）", not bad, f"脏文件: {bad}")

# 10. 文档换行风格没被改坏（AGENTS/HANDOVER 是 CRLF）
for name in ["AGENTS.md", "HANDOVER.md"]:
    d = (ROOT / name).read_bytes()
    check(f"{name} 保持 CRLF", d.count(b"\r\n") == d.count(b"\n") > 0)

# ---------------- 输出 ----------------
width = max(len(r[0]) for r in results)
for label, ok, detail in results:
    print(f"{'✓' if ok else '✗'} {label.ljust(width)}" + (f"   [{detail}]" if detail and not ok else ""))
bad = [r for r in results if not r[1]]
print("-" * (width + 8))
print(f"{len(results)} 项，通过 {len(results)-len(bad)}，不一致 {len(bad)}")
sys.exit(1 if bad else 0)
