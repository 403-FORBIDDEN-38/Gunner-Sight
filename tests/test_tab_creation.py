"""回归：tab 创建机制的**契约**。

这个机制曾经出过一次静默掩盖的事故：`_ensure_tab` 把 tab 工厂的异常吞掉、
缓存一个 QLabel 替身。于是 `main.py` 的热键回调拿到 QLabel 去调 `.toggle()`，
抛出的是与根因无关的 `AttributeError`，真实异常被掩盖两次，替身还被永久缓存，
模块再也恢复不了。本项目**没有可用的版本控制**，这类静默失败只能靠测试守住。

契约五条：
1. `get_tab` 是纯查询，绝不触发懒加载创建；
2. `_ensure_tab` 失败即抛原异常，`_tab_cache` 只装真实 tab，绝不装替身；
3. 需要"坏了也要能用"的路径（导航）降级到 `_tab_error_pages`，且不重复重试；
4. 电闸开启的进阶模块必须在启动时预创建成真 tab（否则热键无对象可派发）；
5. 电闸关闭的必须零开销、不创建。
"""
import pytest
from PyQt5.QtWidgets import QLabel

ADVANCED = ("set_magnifier_enabled", "set_angle_meter_enabled",
            "set_distance_meter_enabled", "set_squad_macro_enabled")


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


def test_enabled_modules_are_precreated_as_real_tabs(config, window):
    """契约 4：电闸开启的进阶模块必须预创建成真 tab，热键才可能响应。"""
    _switch_all(config, True)
    window._create_ui_frame()
    window._create_first_tab()

    for idx in (window.TAB_ANGLE_METER, window.TAB_DISTANCE_METER,
                window.TAB_MAGNIFIER, window.TAB_SQUAD_MACRO):
        widget = window.get_tab(idx)
        assert widget is not None, f"tab {idx} 未预创建"
        assert not isinstance(widget, QLabel), f"tab {idx} 被降级成替身"


def test_disabled_modules_stay_uncreated(config, window):
    """契约 5：电闸关闭的模块零开销——不创建对象。"""
    _switch_all(config, False)
    window._create_ui_frame()
    window._create_first_tab()

    for idx in (window.TAB_ANGLE_METER, window.TAB_DISTANCE_METER,
                window.TAB_MAGNIFIER, window.TAB_SQUAD_MACRO):
        assert window.get_tab(idx) is None, f"关闭的模块 tab {idx} 不应被创建"


def test_all_ten_tabs_construct(config, window):
    """契约 6：全部 10 个 tab 都必须能创建成功（离屏，不显示）。

    这条测试来自一次真实事故：删掉 MainWindow 的 10 个懒加载属性后，
    VehicleConfigTab 创建时会走 `self.overview_tab`（属性访问器）→ AttributeError。
    当时 20 个测试**全是绿的**——因为没有一条会创建 TAB_VEHICLE。
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
