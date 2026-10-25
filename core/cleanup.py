"""清理路径的逐项隔离工具 + 清理契约 SSOT。

AGENTS §2.1「中断即泄漏」：清理方法里任何一行抛异常，后面的清理都不执行。
safe_call 把每个清理动作隔离：失败写 warning 日志，不中断后续动作。

M19 清理契约：「哪些对象要清理、调什么方法」曾经有四份各自为政的实现——
MainWindow.closeEvent / main.py 的 aboutToQuit 兜底 / tests/conftest 的
fixture teardown / tools/export_gui_facts 的离屏构造收尾。四份清单互有
出入（closeEvent 只停 3 个 tab，main.py 只停 overlay+放大镜，export 还在
试五个历史方法名），清单漂移 = 静默泄漏：漏停的线程/钩子不报错，只是活着。

现在统一走本模块的 collect_* 函数；四份调用方只负责「什么时候跑」。
"""
import time

from loguru import logger


def safe_call(name: str, fn):
    """执行一个清理动作，失败时写 warning 但不抛出。

    Args:
        name: 动作名（用于日志）
        fn: 无参可调用对象
    """
    try:
        fn()
    except Exception as e:
        logger.warning(f"[cleanup] {name} failed: {type(e).__name__}: {e}")


# ---------------- 清理契约 SSOT（M19） ----------------

# (tab 属性名, 清理方法名, 日志显示名)。
# 放大镜用 cleanup()（停 worker + 释放 mss GDI 资源），其余三个用 shutdown()。
# 各 tab 的 shutdown()/cleanup() 内部再调 _shutdown_engine/_destroy_engine/
# _shutdown_macro——对外只有这两个统一入口。
TAB_CLEANUP_STEPS = (
    ("TAB_ANGLE_METER", "shutdown", "角度仪"),
    ("TAB_DISTANCE_METER", "shutdown", "标定测距"),
    ("TAB_SQUAD_MACRO", "shutdown", "建队宏"),
    ("TAB_MAGNIFIER", "cleanup", "放大镜"),
)


def collect_tab_cleanup_steps(window):
    """按契约表收集「已创建 tab」的清理动作。

    只用 get_tab() 纯查询，不触发懒加载创建（HANDOVER §十一：退出路径
    访问懒加载属性会现场新建 tab，纯浪费与隐患）。
    """
    steps = []
    for attr, method, label in TAB_CLEANUP_STEPS:
        idx = getattr(window, attr, None)
        if idx is None:
            continue
        w = window.get_tab(idx)
        if w is None:
            continue
        fn = getattr(w, method, None)
        if callable(fn):
            steps.append((label, fn))
    return steps


def collect_window_cleanup_steps(window):
    """收集 window 级清理动作（桌宠/overlay/hotkey/弹种滚轮/配置保存）。

    M18：ammo_wheel.stop() 进退出路径——滚轮模块常驻鼠标钩子与定时器，
    此前没有任何一处退出路径停它。

    桌宠（MascotWidget/ChatBubble/SoundPlayer）parent 是主窗口而非信息页，
    由信息页创建但生命周期属窗口级；退出时必须显式停动画/定时器/音频，
    否则窗口销毁级联里 hideEvent 会踩到已删除的 C++ 子对象。
    """
    steps = []
    info_idx = getattr(window, "TAB_INFO", None)
    if info_idx is not None:
        info_tab = window.get_tab(info_idx)
        shutdown_mascot = (getattr(info_tab, "shutdown_mascot", None)
                           if info_tab is not None else None)
        if callable(shutdown_mascot):
            steps.append(("桌宠", shutdown_mascot))
    overlay = getattr(window, "overlay", None)
    if overlay is not None:
        steps.append(("Overlay信号", overlay.shutdown))
    hotkey = getattr(window, "hotkey", None)
    if hotkey is not None:
        steps.append(("热键", hotkey.shutdown))
    wheel = getattr(window, "ammo_wheel", None)
    if wheel is not None:
        stop = getattr(wheel, "stop", None)
        if callable(stop):
            steps.append(("弹种滚轮", stop))
    config = getattr(window, "config", None)
    if config is not None:
        steps.append(("配置保存", config.save_config))
    return steps


def run_cleanup_steps(steps, on_step=None):
    """逐项执行清理（safe_call 隔离，一项失败不影响其余）。

    Args:
        steps: [(label, fn), ...] collect_* 的产出
        on_step: 可选回调 (label, elapsed_ms)，供调用方打耗时日志
    """
    for label, fn in steps:
        t0 = time.perf_counter()
        safe_call(label, fn)
        if on_step is not None:
            on_step(label, (time.perf_counter() - t0) * 1000)
