"""批次 3 浪 C2 契约测试（跨页信号与补偿两项）。

- M15：adapt_tab 改主题色只发公共信号 theme_reapply_requested，不反向读
  window._current_theme、不调 window._apply_theme() 私有 API；MainWindow
  只在「改的是当前主题」时重应用。
- M17：ammo_wheel 后台创建后，on_ammo_wheel_ready 补偿先于它实例化的
  标定测距 tab（初始同步 + toggled 连接），暂离状态不再失联。
"""
import types
from unittest.mock import MagicMock


def test_adapt_tab_emits_public_signal(config, qapp, monkeypatch):
    """M15：_pick_accent 只 emit 公共信号（不再走 window 私有 API）。"""
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import QColorDialog

    from gui.tabs.adapt_tab import AdaptTab

    overlay_stub = MagicMock()
    overlay_stub.get_adapt_factors.return_value = (1.0, 1.0)
    tab = AdaptTab(config=config, overlay=overlay_stub)
    fired = []
    tab.theme_reapply_requested.connect(fired.append)
    monkeypatch.setattr(QColorDialog, "getColor", lambda *a, **k: QColor("#ff0000"))

    tab._pick_accent("dark")
    assert fired == ["dark"]


def test_theme_reapply_only_for_current_theme(window, monkeypatch):
    """M15：MainWindow 侧——改的不是当前主题不重应用；是当前主题才重应用。"""
    window._create_ui_frame()
    applied = []
    monkeypatch.setattr(window, "_apply_theme", lambda t: applied.append(t))

    window._current_theme = "dark"
    window._on_theme_reapply_requested("light")
    assert applied == []

    window._on_theme_reapply_requested("dark")
    assert applied == ["dark"]


def test_on_ammo_wheel_ready_compensates_existing_tab(window, monkeypatch):
    """M17：tab 先于 wheel 存在时，wheel 就绪后补齐同步 + 连接。"""
    window._create_ui_frame()
    tab = window._ensure_tab(window.TAB_DISTANCE_METER)
    assert tab is not None

    # wheel 后创建（暂离中）
    window.ammo_wheel = types.SimpleNamespace(is_suspended=True)
    synced = []
    monkeypatch.setattr(tab, "set_function_active", lambda v: synced.append(v))

    window.on_ammo_wheel_ready()
    assert synced == [True], "暂离状态未同步到已存在的测距 tab"

    # toggled 连接已建立：勾选启用时同步暂离状态
    monkeypatch.undo()
    synced2 = []
    monkeypatch.setattr(tab, "set_function_active", lambda v: synced2.append(v))
    tab.enable_check.setChecked(True)
    assert synced2 == [True]


def test_on_ammo_wheel_ready_no_tab_is_noop(window):
    """M17：测距 tab 未创建时补偿是安全 no-op（不炸、不懒加载 tab）。"""
    window._create_ui_frame()
    assert window.get_tab(window.TAB_DISTANCE_METER) is None
    window.ammo_wheel = types.SimpleNamespace(is_suspended=False)
    window.on_ammo_wheel_ready()  # 不抛异常即通过
    assert window.get_tab(window.TAB_DISTANCE_METER) is None
