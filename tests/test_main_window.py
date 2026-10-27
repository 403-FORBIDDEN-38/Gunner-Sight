"""gui/main_window.py：tab 创建机制、跨页信号、补偿接线、桌宠归属。

**tab 创建：静默掩盖过一次事故**
`_ensure_tab` 曾把 tab 工厂的异常吞掉、缓存一个 QLabel 替身。于是 `main.py`
的热键回调拿到 QLabel 去调 `.toggle()`，抛出的是与根因无关的 `AttributeError`，
真实异常被掩盖两次，替身还被永久缓存，模块再也恢复不了。契约五条：
1. `get_tab` 是纯查询，绝不触发懒加载创建；
2. `_ensure_tab` 失败即抛原异常，`_tab_cache` 只装真实 tab，绝不装替身；
3. 需要"坏了也要能用"的路径（导航）降级到 `_tab_error_pages`，且不重复重试；
4. 电闸开启的进阶模块必须在启动时预创建成真 tab（否则热键无对象可派发）；
5. 电闸关闭的必须零开销、不创建。
第六条（全部 10 个 tab 都要能建）来自另一次真实事故：删掉 MainWindow 的 10 个
懒加载属性后，VehicleConfigTab 创建时会走 `self.overview_tab` → AttributeError，
而当时 20 个测试**全是绿的**——因为没有一条会创建 TAB_VEHICLE。

**跨页信号（M15）**：adapt_tab 改主题色只发公共信号 `theme_reapply_requested`，
不反向读 `window._current_theme`、不调 `window._apply_theme()` 私有 API；
MainWindow 只在「改的是当前主题」时重应用。

**补偿接线（M17 / P0-1）**：ammo_wheel 后台创建后，`on_ammo_wheel_ready` 补偿
先于它实例化的标定测距 tab（初始同步 + toggled 连接），暂离状态不再失联。
这里曾用无参 `disconnect()`，把 tab 自己的电闸 `_on_enable_toggle` 一并清空——
启用勾选框就此失效（不写配置、不起停引擎、不注册热键），而 91 passed 全绿，
因为旧测试只断言「新连接生效」。

**桌宠归属（P0-2）**：info_tab `__init__` 的 setChecked 同步触发创建路径，桌宠
被 parent 到 tab 自身（tab 工厂不传 parent，`__init__` 期 `window()` 返回自身），
切 tab 即消失；showEvent 兜底因 `_mascot` 已被错误置位从未生效。
`config.is_mascot_enabled()` 现硬编码 False（「不持久化，每次启动默认关闭」），
故该触发链在生产不可达——这是**已知的潜在陷阱**：一旦恢复持久化，bug 立刻复活。
下列测试用 monkeypatch 把 getter 钉成 True 锁定契约，与持久化策略解耦。

**断言方向**：不只锁「我加的东西在工作」，锁「我碰过的东西还活着」。观测点选
终态副作用（配置写入 / 暂离同步 / parent 与可见性），不数连接数。
"""
import types

import pytest
from PyQt5.QtWidgets import QLabel

ADVANCED = ("set_magnifier_enabled", "set_angle_meter_enabled",
            "set_distance_meter_enabled", "set_squad_macro_enabled")
CONTRACT_IDXS = ("TAB_ANGLE_METER", "TAB_DISTANCE_METER",
                 "TAB_MAGNIFIER", "TAB_SQUAD_MACRO")


def _switch_all(config, on):
    for setter in ADVANCED:
        getattr(config, setter)(on)


def _boom_factory():
    """返回必定失败的 tab 工厂 + 调用计数器。"""
    calls = []

    def factory():
        calls.append(1)
        raise RuntimeError("模拟 tab 构造失败")

    return factory, calls


# ---------------------------------------------------------------- 契约 1-3：get/ensure/降级

def test_get_tab_is_query_only(window):
    """契约 1：未创建时返回 None，反复调用零副作用。"""
    assert window.get_tab(window.TAB_MAGNIFIER) is None
    before = len(window._tab_cache)
    for _ in range(5):
        assert window.get_tab(window.TAB_MAGNIFIER) is None
    assert len(window._tab_cache) == before


def test_ensure_tab_raises_and_never_caches_placeholder(window):
    """契约 2：抛的是原异常，且不污染 _tab_cache、不装替身。"""
    window._create_ui_frame()
    window._create_first_tab()
    assert not any(isinstance(w, QLabel) for w in window._tab_cache.values())

    factory, _ = _boom_factory()
    window._tab_factories[window.TAB_MAGNIFIER] = factory
    with pytest.raises(RuntimeError, match="模拟 tab 构造失败"):
        window._ensure_tab(window.TAB_MAGNIFIER)
    assert window.TAB_MAGNIFIER not in window._tab_cache


def test_nav_degrades_without_polluting_cache_or_retrying(window):
    """契约 3：导航到坏页面 → 降级页、不崩、不进缓存、不重复重试。"""
    window._create_ui_frame()
    window._create_first_tab()

    factory, calls = _boom_factory()
    window._tab_factories[window.TAB_MAGNIFIER] = factory
    row = window._tab_to_row[window.TAB_MAGNIFIER]

    window._on_nav_changed(row)  # 不应抛出
    assert window.TAB_MAGNIFIER in window._tab_error_pages
    assert window.TAB_MAGNIFIER not in window._tab_cache

    n = len(calls)
    window._on_nav_changed(row)
    assert len(calls) == n, "已降级的页面不应重复重试构造"


# ---------------------------------------------------------------- 契约 4-6：预创建与全量可建

def test_enabled_modules_are_precreated_as_real_tabs(config, window):
    """契约 4：电闸开启的进阶模块必须预创建成真 tab，热键才可能响应。"""
    _switch_all(config, True)
    window._create_ui_frame()
    window._create_first_tab()

    for attr in CONTRACT_IDXS:
        idx = getattr(window, attr)
        widget = window.get_tab(idx)
        assert widget is not None, f"tab {idx} 未预创建"
        assert not isinstance(widget, QLabel), f"tab {idx} 被降级成替身"


def test_disabled_modules_stay_uncreated(config, window):
    """契约 5：电闸关闭的模块零开销——不创建对象。"""
    _switch_all(config, False)
    window._create_ui_frame()
    window._create_first_tab()

    for attr in CONTRACT_IDXS:
        idx = getattr(window, attr)
        assert window.get_tab(idx) is None, f"关闭的模块 tab {idx} 不应被创建"


def test_all_ten_tabs_construct(config, window):
    """契约 6：全部 10 个 tab 都必须能创建成功（离屏，不显示）。

    它同时守住了 tab 工厂里任何一处跨 tab 接线写错。
    """
    window._create_ui_frame()
    window._create_first_tab()

    failed = []
    for idx in range(10):
        try:
            window._ensure_tab(idx)
            if window.get_tab(idx) is None:
                failed.append((idx, "返回 None"))
        except Exception as e:
            failed.append((idx, f"{type(e).__name__}: {e}"))
    assert not failed, f"tab 创建失败: {failed}"


# ---------------------------------------------------------------- 跨页信号（M15）

def test_adapt_tab_emits_public_signal(config, qapp, monkeypatch):
    """M15：_pick_accent 只 emit 公共信号（不再走 window 私有 API）。"""
    from unittest.mock import MagicMock

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


# ---------------------------------------------------------------- ammo_wheel 补偿（M17 / P0-1）

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


def test_ammo_wheel_ready_keeps_tab_own_slot_alive(window, monkeypatch):
    """P0-1 有牙：补偿连接之后，tab 自己的电闸必须仍然生效（双槽存活）。"""
    window._create_ui_frame()
    tab = window._ensure_tab(window.TAB_DISTANCE_METER)
    assert tab is not None

    # wheel 后创建（暂离中）→ 触发补偿路径
    window.ammo_wheel = types.SimpleNamespace(is_suspended=True)
    window.on_ammo_wheel_ready()

    # 引擎起停不在本契约内，stub 掉（离屏建真 overlay 无意义；
    # 默认配置热键全空，reload_hotkeys 是安全 no-op）
    monkeypatch.setattr(tab, "_init_engine", lambda: None)
    monkeypatch.setattr(tab, "_shutdown_engine", lambda: None)
    synced = []
    monkeypatch.setattr(tab, "set_function_active", lambda v: synced.append(v))

    # 归一到「关」再开到「开」——无论夹具默认值如何都走一遍真 toggle
    tab.enable_check.setChecked(False)
    tab.enable_check.setChecked(True)

    # 槽 1（tab 自己的电闸 _on_enable_toggle）：配置被写入
    assert window.config.is_distance_meter_enabled() is True
    # 槽 2（window 的补偿 _on_distance_toggle）：暂离状态已同步
    assert synced == [True], "补偿槽失效：电闸开启未同步暂离状态"


def test_ammo_wheel_ready_compensation_is_idempotent(window, monkeypatch):
    """补偿入口重复调用不叠加连接（定向断开只摘自己的那条）。"""
    window._create_ui_frame()
    tab = window._ensure_tab(window.TAB_DISTANCE_METER)
    window.ammo_wheel = types.SimpleNamespace(is_suspended=True)

    window.on_ammo_wheel_ready()
    window.on_ammo_wheel_ready()  # 再调一次：旧连接被定向摘掉后重连

    monkeypatch.setattr(tab, "_init_engine", lambda: None)
    monkeypatch.setattr(tab, "_shutdown_engine", lambda: None)
    synced = []
    monkeypatch.setattr(tab, "set_function_active", lambda v: synced.append(v))

    tab.enable_check.setChecked(True)
    # 只触发一次同步（若叠加成两个槽，这里会是 [True, True]）
    assert synced == [True]


# ---------------------------------------------------------------- 桌宠（P0-2）

def test_mascot_not_created_during_init(config, qapp, monkeypatch):
    """P0-2：config 称启用时，__init__ 期不得创建桌宠。

    那时 tab 尚未 insertWidget，self.window() 返回 tab 自身——
    此期创建的桌宠必被 parent 成页面子控件。blockSignals 后创建只能
    发生在 showEvent / MainWindow 创建回调（window() 已就绪）。
    getter 现硬编码 False，此处 monkeypatch 成 True 锁定契约。
    """
    from core.resource_manager import ResourceManager
    from gui.tabs.info_tab import InfoTab

    monkeypatch.setattr(config, "is_mascot_enabled", lambda: True)
    tab = InfoTab(config=config, resources=ResourceManager())
    assert tab.mascot_enable_check.isChecked() is True, "勾选状态应已加载"
    assert tab._mascot is None, "__init__ 期不得创建桌宠（parent 会是 tab 自身）"


def test_mascot_parented_to_window_not_tab(window, monkeypatch):
    """P0-2：config 称启用时，桌宠 parent 必须是主窗口（不是 tab 自身）。"""
    monkeypatch.setattr(window.config, "is_mascot_enabled", lambda: True)
    window._create_ui_frame()
    tab = window._ensure_tab(window.TAB_INFO)

    mascot = tab._mascot
    assert mascot is not None, "config 称启用时桌宠应被创建（创建回调）"
    assert mascot.parent() is window, "桌宠必须 parent 到主窗口"
    assert mascot.parent() is not tab


def test_mascot_survives_tab_switch(window, monkeypatch):
    """P0-2：桌宠是窗口子控件，切走信息页不消失（可见性依赖祖先链）。"""
    monkeypatch.setattr(window.config, "is_mascot_enabled", lambda: True)
    window._create_ui_frame()
    tab = window._ensure_tab(window.TAB_INFO)
    other = window._ensure_tab(window.TAB_OVERVIEW)

    window.show()
    window.tab_stack.setCurrentWidget(other)  # 切到概览页

    assert tab._mascot is not None
    assert tab._mascot.isVisible(), "切走信息页，桌宠不该随页面隐藏"


def test_mascot_shutdown_in_cleanup_contract(window, monkeypatch):
    """M19 契约覆盖桌宠：窗口清理后句柄清空，动画/定时器/音频已显式停。

    前置修复：桌宠 hideEvent 曾无保护地 stop 动画，窗口销毁级联里会踩
    已删除的 QPropertyAnimation（间歇性 RuntimeError）。现在退出路径先
    shutdown（控件已隐藏则销毁时不再触发 hideEvent），hideEvent 另有护栏。
    """
    from core.cleanup import collect_window_cleanup_steps, run_cleanup_steps

    monkeypatch.setattr(window.config, "is_mascot_enabled", lambda: True)
    window._create_ui_frame()
    tab = window._ensure_tab(window.TAB_INFO)
    assert tab._mascot is not None

    steps = [s for s in collect_window_cleanup_steps(window) if s[0] == "桌宠"]
    assert steps, "清理契约缺桌宠项（collect_window_cleanup_steps）"
    run_cleanup_steps(steps)
    assert tab._mascot is None and tab._bubble is None
