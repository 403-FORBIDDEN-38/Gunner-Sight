"""导出「界面控件清单 + 出厂配置关键值」——手册重构的事实底稿。

两个事实源分开取：
- 控件结构：离屏构造 MainWindow（用 tmp config，干净状态），遍历 QWidget 树
- 出厂数值：直接读 config/config.json（**这才是用户拿到手看到的值**，不是代码默认值）

输出：GUI_INVENTORY.md
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import (          # noqa: E402
    QAbstractItemView, QAbstractSpinBox, QCheckBox, QComboBox, QGroupBox,
    QLabel, QLineEdit, QListWidget, QPushButton, QRadioButton, QScrollArea,
    QSlider, QSplitter, QStackedWidget, QTableWidget, QTabWidget, QTreeWidget,
    QWidget, QApplication,
)

SKIP_TYPES = (QWidget,)          # 只跳过"纯 QWidget 容器"（没有文字/参数的）
MAX_LINES_PER_TAB = 120

app = QApplication.instance() or QApplication(sys.argv)

from core.config_manager import ConfigManager          # noqa: E402
from core.hotkey_manager import HotkeyManager          # noqa: E402
from core.overlay import OverlayRenderer               # noqa: E402
from core.resource_manager import ResourceManager      # noqa: E402
from core.state_machine import StateMachine            # noqa: E402
from gui.main_window import MainWindow                 # noqa: E402


def describe(w):
    """提取一个控件的"事实"：文字 / 范围 / 默认值。没有可读信息的返回 None。"""
    t = type(w).__name__
    if isinstance(w, QGroupBox):
        return f"QGroupBox 「{w.title()}」{'  flat' if w.isFlat() else ''}"
    if isinstance(w, (QCheckBox, QRadioButton)):
        return f"{t} 「{w.text()}」  checked={w.isChecked()}"
    if isinstance(w, QPushButton):
        txt = w.text()
        s = f"QPushButton 「{txt}」" if txt else "QPushButton <无文字，纯色块/图标>"
        if w.isCheckable():
            s += f"  checkable checked={w.isChecked()}"
        return s
    if isinstance(w, QLabel):
        txt = w.text().replace("\n", "⏎")
        if not txt:
            return None
        return f"QLabel 「{txt[:60]}」" + (f"  objectName={w.objectName()}" if w.objectName() else "")
    if isinstance(w, QLineEdit):
        return (f"QLineEdit placeholder=「{w.placeholderText()}」"
                + (f"  text=「{w.text()[:24]}」" if w.text() else ""))
    if isinstance(w, QComboBox):
        items = [w.itemText(i) for i in range(min(w.count(), 6))]
        more = f" …+{w.count()-6}" if w.count() > 6 else ""
        return f"QComboBox {w.count()} 项: {items}{more}  当前=「{w.currentText()}」"
    if isinstance(w, QAbstractSpinBox):
        dec = getattr(w, "decimals", lambda: 0)()
        return (f"{t} range=[{w.minimum()}, {w.maximum()}] 当前={w.value()}"
                + (f"  suffix=「{w.suffix()}」" if w.suffix() else "")
                + (f"  decimals={dec}" if dec else ""))
    if isinstance(w, QSlider):
        return f"QSlider range=[{w.minimum()}, {w.maximum()}] 当前={w.value()}"
    if isinstance(w, QListWidget):
        vis = [w.item(i).text() for i in range(min(w.count(), 3))]
        return f"QListWidget {w.count()} 项  {vis}"
    if isinstance(w, QTreeWidget):
        return f"QTreeWidget 顶层 {w.topLevelItemCount()} 项"
    if isinstance(w, QTableWidget):
        heads = []
        for c in range(w.columnCount()):
            it = w.horizontalHeaderItem(c)
            heads.append(it.text() if it else "")
        return f"QTableWidget {w.rowCount()}行×{w.columnCount()}列  表头={heads}"
    if isinstance(w, QTabWidget):
        return f"QTabWidget {w.count()} 页"
    if isinstance(w, QStackedWidget):
        return f"QStackedWidget {w.count()} 页"
    if isinstance(w, QSplitter):
        return f"QSplitter {w.count()} 段 sizes={w.sizes()}"
    return None


def iter_widgets(layout):
    """按布局顺序递归产出控件（含嵌套子布局），跳过分隔条 / spacer。"""
    if layout is None:
        return
    for i in range(layout.count()):
        it = layout.itemAt(i)
        if it is None:
            continue
        cw = it.widget()
        if cw is not None:
            yield cw
        else:
            yield from iter_widgets(it.layout())


def kids_of(w):
    """取子控件。注意：QSplitter / QStackedWidget / QTabWidget 的内容不在 layout() 里，
    必须问它们自己要——否则整页会被导出成空（这是第一版的 bug）。"""
    if isinstance(w, QScrollArea):
        # QScrollArea 的内容同样不在 layout() 里，要问 widget()
        inner = w.widget()
        return [inner] if inner is not None else []
    if isinstance(w, QSplitter):
        return [w.widget(i) for i in range(w.count()) if w.widget(i) is not None]
    if isinstance(w, QTabWidget):
        return [w.widget(i) for i in range(w.count()) if w.widget(i) is not None]
    if isinstance(w, QStackedWidget):
        # 走全部页（手册要覆盖每一页），不只当前页
        return [w.widget(i) for i in range(w.count()) if w.widget(i) is not None]
    return list(iter_widgets(w.layout()))


def walk(w, depth, out, budget):
    """递归导出；返回还能写几行"""
    desc = describe(w)
    if desc:
        out.append("  " * depth + "- " + desc)
        budget -= 1
    if budget <= 0:
        return 0
    for c in kids_of(w):
        if isinstance(c, QWidget):
            budget = walk(c, depth + 1, out, budget)
            if budget <= 0:
                return 0
    return budget


# ---------- 1. 控件清单 ----------
cfg = ConfigManager(config_dir=tempfile.mkdtemp())
for s in ("set_magnifier_enabled", "set_angle_meter_enabled",
          "set_distance_meter_enabled", "set_squad_macro_enabled"):
    getattr(cfg, s)(True)
st = StateMachine(cfg)
win = MainWindow(cfg, st, OverlayRenderer(cfg, st), HotkeyManager(cfg, st), ResourceManager())
win._create_ui_frame()
win._create_first_tab()

NAMES = {
    win.TAB_OVERVIEW: "准星面板", win.TAB_VEHICLE: "载具配置", win.TAB_HOTKEY: "热键设置",
    win.TAB_ADAPT: "适配设置", win.TAB_DISTANCE_METER: "标定测距",
    win.TAB_MAGNIFIER: "放大镜", win.TAB_ANGLE_METER: "角度仪",
    win.TAB_SQUAD_MACRO: "建队宏", win.TAB_RESOURCE: "资源库", win.TAB_INFO: "信息",
}
NAV = [("准星", ["准星面板", "载具配置", "热键设置", "适配设置"]),
       ("工具", ["标定测距", "放大镜", "角度仪", "建队宏"]),
       ("相关", ["资源库", "信息"])]

lines = ["# GUI 控件清单（事实底稿）", "",
         "> 由脚本遍历 QWidget 树导出，**不是手写**。用途：写手册时确认「页面上有什么」。",
         "> 参数（range/当前值）来自**代码骨架默认值**；用户实际看到的值见文末「出厂配置」。", ""]
for group, pages in NAV:
    lines.append(f"## 导航组：{group}")
    lines.append("")
    for pname in pages:
        idx = next(k for k, v in NAMES.items() if v == pname)
        try:
            win._ensure_tab(idx)
        except Exception as e:
            lines += [f"### {pname}", "", f"（创建失败：{e}）", ""]
            continue
        tab = win.get_tab(idx)
        out = []
        walk(tab, 0, out, MAX_LINES_PER_TAB)
        lines += [f"### {pname}  `TAB_{list(NAMES.keys())[list(NAMES.values()).index(pname)]}` = {idx}",
                  "", "```"] + out + ["```", ""]

# ---------- 2. 出厂配置关键值 ----------
import json
import subprocess


def load_factory_config():
    """出厂配置 = **发布包里带的那份**（用户拿到手第一眼看到的）。

    绝不读工作区 config/config.json —— 那是使用者**当前状态**，随时会变。
    实测过：工作区 overlay_visible=false，而出厂（发布包 + git HEAD）都是 true。
    拿不到发布包时退回 git HEAD（提交时状态，与发布包一致）。
    """
    pkg = Path(r"config/config.json")
    if pkg.exists():
        return json.loads(pkg.read_text(encoding="utf-8")), f"发布包 `{pkg}`"
    out = subprocess.run(["git", "show", "HEAD:config/config.json"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return json.loads(out), "git HEAD:config/config.json"


factory, factory_src = load_factory_config()
g = factory.get("global_settings", {})
lines += ["## 出厂配置关键值（**随包发布**的那份 config）", "",
          f"> 来源：{factory_src}",
          "> **用户拿到手看到的就是这些值**。使用者运行后本机 config 会变——",
          "> 工作区 `config/config.json` 是**当前状态**，不是出厂值，别混。", "",
          "| 项 | 出厂值 |", "| --- | --- |",
          f"| 载具数量 | **{len(factory.get('vehicles', {}))}** |",
          f"| 标签数量 | **{len(factory.get('tags', []))}** |",
          f"| 滚轮窗口偏移 | x=**{g.get('wheel_offset_x')}**, y=**{g.get('wheel_offset_y')}** |",
          f"| 全局缩放 / 偏移 | {g.get('scale')}% / ({g.get('offset_x')}, {g.get('offset_y')}) |",
          f"| 叠加层可见 / 不透明度 | {g.get('overlay_visible')} / {g.get('overlay_opacity')} |",
          f"| 主题 | {factory.get('theme')} |", ""]

lines += ["### 出厂热键绑定", "", "| 功能槽 | 绑定 |", "| --- | --- |"]
for k, v in (factory.get("hotkeys") or {}).items():
    if isinstance(v, dict):
        k1, k2 = v.get("key1", ""), v.get("key2", "")
        lines.append(f"| `{k}` | {k1 or '—'} / {k2 or '—'} |")
lines.append("")

lines += ["### 各模块电闸（出厂是否启用）", "", "| 模块 | enabled |", "| --- | --- |"]
for k in ("magnifier", "angle_meter", "distance_meter", "squad_macro", "mascot"):
    sec = factory.get(k) or {}
    lines.append(f"| {k} | {sec.get('enabled')} |")
lines.append("")

Path("GUI_INVENTORY.md").write_text("\n".join(lines), encoding="utf-8", newline="\r\n")
print(f"已生成 GUI_INVENTORY.md：{len(lines)} 行")
print(f"  控件清单覆盖 {len(NAMES)} 页；出厂载具 {len(factory.get('vehicles', {}))} 个")

# 收尾：离屏构造起了放大镜抓屏线程，不清理会报 "QThread: Destroyed while thread is still running"
for idx in range(10):
    _tab = win.get_tab(idx)
    if _tab is None:
        continue
    for _m in ("shutdown", "cleanup", "_shutdown_engine", "_destroy_engine",
               "_shutdown_macro"):
        _fn = getattr(_tab, _m, None)
        if callable(_fn):
            try:
                _fn()
            except Exception:
                pass
