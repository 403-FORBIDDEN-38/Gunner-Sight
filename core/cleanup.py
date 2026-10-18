"""清理路径的逐项隔离工具。

AGENTS §2.1「中断即泄漏」：清理方法里任何一行抛异常，后面的清理都不执行。
safe_call 把每个清理动作隔离：失败写 warning 日志，不中断后续动作。
"""
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
