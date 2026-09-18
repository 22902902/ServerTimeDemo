# -*- coding: utf-8 -*-
"""全局日志配置 —— 在程序入口调用一次，全项目模块自动生效。

为什么需要它（2026-09-18 P1 第 4 步）
    此前 main.py 在模块顶部给一个具名 logger 单独装了 StreamHandler，有两个问题：

    1. **发布版完全丢失日志。**
       `ExpiryManager_fixed.spec` 里 `console=False`，打包出来是无控制台的窗口
       程序，`sys.stderr` 没有可写目标。全项目 9 处 `logger.exception`
       （main.py 8 处 + tools_page.py 1 处）在正式 exe 里一条记录都留不下来 ——
       而它们的用途恰恰是事后排查。
    2. **其余模块的日志无处可去。**
       `logging.getLogger(__name__)` 是标准做法，但没有配置 root，消息只会落到
       `logging.lastResort`（WARNING 级、无格式化、仅 stderr），同样在发布版丢失。

    所以本模块配置的是 **root logger**：入口调用一次 `setup_logging()`，之后任意
    模块（包括将来新增的）用 `logging.getLogger(__name__)` 就直接可用，不需要
    每个模块各自装 handler。这是「全项目接入」最省事也最不容易做错的方式。

用法
    # 入口：main.py 的 main()
    import log_setup
    log_setup.setup_logging(DATA_DIR / "logs")

    # 任意模块，无需任何配置
    import logging
    logger = logging.getLogger(__name__)
    logger.exception("出错了")        # 自动带上时间/级别/模块名，落盘到 app.log
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

# 日志文件名与轮转策略：单文件 1 MB，保留 3 份历史
LOG_FILENAME = "app.log"
MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 3

# 默认级别 INFO。
# 原来 main.py 设的是 DEBUG，但它只调用 logger.exception（ERROR 级），
# DEBUG 等于没有任何实际效果，反而会让第三方库的调试输出淹没有效信息。
DEFAULT_LEVEL = logging.INFO

# 环境变量覆盖级别，便于临时抓详细日志而不用改代码：
#   set EXPIRY_LOG_LEVEL=DEBUG && python main.py
ENV_LEVEL = "EXPIRY_LOG_LEVEL"

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _resolve_level(level):
    """确定日志级别：显式参数 > 环境变量 > 默认 INFO。"""
    if level is not None:
        return level
    raw = os.environ.get(ENV_LEVEL, "").strip().upper()
    if raw:
        value = getattr(logging, raw, None)
        if isinstance(value, int):
            return value
    return DEFAULT_LEVEL


def _console_stream():
    """返回可用的控制台流；不可用时返回 None。

    打包成窗口程序（`console=False`）后 `sys.stderr` 是 None，此时如果照旧装
    StreamHandler，每次写日志都会在 emit 里抛 AttributeError，然后被 logging
    自己吞掉 —— 表面平静，实际什么都没输出。所以这里先探测再决定。

    顺带把编码错误策略放宽为 replace：中文提示写到 cp936 控制台时不会因为
    个别字符编码不了就整条日志丢失。
    """
    stream = sys.stderr
    if stream is None:
        return None
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
    try:
        stream.write("")
        stream.flush()
    except Exception:
        return None
    return stream


def setup_logging(log_dir=None, level=None, *, console=None,
                  filename=LOG_FILENAME):
    """配置 root logger，重复调用幂等。返回 root logger。

    参数:
        log_dir  日志目录（通常传 DATA_DIR / "logs"）。传 None 则不落盘。
                 目录不存在会自动创建；创建失败只降级不抛异常 ——
                 日志基建不该成为程序起不来的原因。
        level    日志级别，默认 INFO（见 DEFAULT_LEVEL）。
        console  是否额外输出到控制台。None = 自动探测（打包版为无，源码运行有为）。
        filename 日志文件名。
    """
    global _configured
    root = logging.getLogger()
    if _configured:
        return root

    resolved = _resolve_level(level)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    handlers = []

    # 1) 文件：发布版唯一可靠的落地点，也是本模块存在的主要理由
    if log_dir is not None:
        try:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / filename,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(resolved)
            handlers.append(file_handler)
        except OSError as exc:
            # 只读介质 / 权限不足等：继续走控制台，不中断启动
            try:
                sys.stderr.write(f"[log_setup] 日志文件不可用（{exc}），仅输出到控制台\n")
            except Exception:
                pass

    # 2) 控制台：源码运行时方便即时查看
    if console is None:
        console = _console_stream() is not None
    if console:
        stream = _console_stream()
        if stream is not None:
            console_handler = logging.StreamHandler(stream)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(resolved)
            handlers.append(console_handler)

    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(resolved)

    _configured = True

    if handlers:
        root.debug("日志已初始化：级别=%s，处理器=%d 个",
                   logging.getLevelName(resolved), len(handlers))
    return root


def is_configured():
    """是否已初始化。测试与诊断用。"""
    return _configured


def _reset_for_tests():
    """移除本模块添加的 handler 并复位标志。仅供测试使用。"""
    global _configured
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    _configured = False
