"""统一日志模块：loguru 配置。

- 控制台默认 WARNING，GS_DEBUG=1 升 DEBUG（避免刷屏）
- 文件永远 DEBUG（排错时不需要先设环境变量）
- 日志输出到 exe 同目录/logs（绿色便携，不写系统目录）；
  只读安装位置 mkdir 失败时降级 %TEMP%/GunnerSight/logs（P4）
- 格式不含模块名/函数名/行号，减少架构信息泄露
"""
import sys
import os
import tempfile
from pathlib import Path

from loguru import logger


def _get_log_dir() -> Path:
    """确定日志目录（绿色便携：exe 同目录/logs，开发模式项目根目录/logs）。
    只读位置（Program Files 标准用户等）mkdir 失败时降级 %TEMP%/GunnerSight/logs。"""
    if getattr(sys, "frozen", False):
        log_dir = Path(sys.executable).resolve().parent / "logs"
    else:
        log_dir = Path(__file__).resolve().parent.parent / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "GunnerSight" / "logs"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass  # 连 TEMP 都不可写：下面 logger.add 的 try 兜底（仅控制台输出，不阻断启动）
        return fallback
    return log_dir


def _is_debug() -> bool:
    """GS_DEBUG=1 开启完整日志。"""
    return os.environ.get("GS_DEBUG", "").strip() in ("1", "true", "yes")


# 移除默认 handler
logger.remove()

_debug = _is_debug()
# 控制台只报问题（WARNING+），避免刷屏；文件永远最详细（DEBUG+）——
# 正常运行时 85 条 logger.info（含全部 [性能] 计时、[MouseHook]/[Overlay] 诊断）
# 正是排错时最需要的东西，文件里必须留全。
_console_level = "DEBUG" if _debug else "WARNING"
_file_level = "DEBUG"   # 文件永远最详细，不受 GS_DEBUG 影响

# 控制台输出：简化格式，不含模块名/函数名
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level=_console_level,
    colorize=True,
    backtrace=False,
    diagnose=False,
    enqueue=True,
)

# 文件输出：简化格式，不含模块名/函数名/行号
_log_dir = _get_log_dir()
try:
    logger.add(
        _log_dir / "app_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
        level=_file_level,
        rotation="00:00",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        enqueue=True,
    )
except Exception:
    pass  # 极端只读环境：仅保留控制台输出，日志文件不可用不阻断启动

# 记录降级决策（只读位置启动时，这是"日志去哪了"的唯一线索）
_preferred_log_dir = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                      else Path(__file__).resolve().parent.parent) / "logs"
if _log_dir != _preferred_log_dir:
    logger.info(f"[Logger] 首选日志目录不可写（{_preferred_log_dir}），已降级到 {_log_dir}")


def _excepthook(exc_type, exc_value, exc_traceback):
    """全局未处理异常钩子。"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).error(
        f"未处理异常: {exc_type.__name__}"
    )


sys.excepthook = _excepthook

__all__ = ["logger"]
