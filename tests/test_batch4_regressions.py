"""批次 4 浪 1：P0 回归契约测试（对应 CONSOLIDATED_ACTIONS_FOR_STEP5 §三）。

P0-1：on_ammo_wheel_ready 的补偿连接曾用无参 disconnect()，把标定测距
tab 自己的电闸 _on_enable_toggle 一并清空——启用勾选框就此失效（不写
配置、不起停引擎、不注册热键），而 91 passed 全绿（旧测试只断言新连接
生效）。

P0-2：info_tab __init__ 的 setChecked 同步触发创建路径，桌宠被 parent
到 tab 自身（tab 工厂不传 parent，__init__ 期 window() 返回自身），切
tab 即消失；showEvent 兜底因 _mascot 已被错误置位从未生效。

**P0-2 与单据的一处不符（已按 §〇-3 记账，待用户醒审）**：现
`config.is_mascot_enabled()` 自 2026-09-07（c0973fe）起硬编码返回
False（「不持久化，每次启动默认关闭」），`set_mascot_enabled` 只写一个
全仓无人读的 `_mascot_enabled_runtime`。故单据描述的触发链当前在
生产不可达——这是**潜在陷阱**：一旦将来恢复持久化，bug 立刻复活。
下列测试用 monkeypatch 把 getter 钉成 True 锁定契约，与持久化策略
解耦。是否恢复持久化属产品决策，不在本批次范围。

断言方向（§五 根因）：不只锁「我加的东西在工作」，锁「我碰过的东西
还活着」。观测点选终态副作用（配置写入 / 暂离同步 / parent 与可见性），
不数连接数。
"""
import types


def test_ammo_wheel_ready_keeps_tab_own_slot_alive(window, monkeypatch):
    """补偿连接之后，tab 自己的电闸必须仍然生效（双槽存活）。"""
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
