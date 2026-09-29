# -*- coding: utf-8 -*-
"""把命令送到系统终端里（本机 Windows 上真正敲命令的地方）。

为什么不「自动执行」
--------------------------------------------------------------------------------
流程里的命令是给服务器（CentOS）用的 **Linux shell** —— ``cd /www/xxx && rm -rf``
在这台 Windows 上根本跑不起来。真要执行，只能靠你已经连好的那个 SSH 会话。
所以「发送到终端」做的是两件事：

1. 命令进**剪贴板**（变量已渲染、与屏幕上看到的一字不差）；
2. **开一个终端窗口**，把光标交回给你 —— 切到 SSH 会话里 Ctrl+V 回车。

顺带的好处：危险命令不会被误触发。这条不是妥协，是这类命令本来就只能在别处执行 ——
真在本机强行跑，轻则报错，重则把本机目录当成服务器目录删掉。

不引依赖、不动注册表：优先 Windows Terminal（``wt.exe``），没有就退回 ``cmd.exe``。
两者都只是**开一个窗口**，不带任何 ``-c`` / ``/c`` 参数，所以不会执行任何东西。

可注入点（``which`` / ``popen`` / ``copy``）是为了套件能在不真开窗口的前提下断言
「选的是哪个终端、shell 拼出来长什么样」。
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

# 优先 Windows Terminal（多标签、好复制粘贴），退回老 cmd
TERMINAL_CANDIDATES = ("wt.exe", "cmd.exe")
# 命令太长时终端窗口标题会难看，但不截断命令本身
TITLE_LIMIT = 60

__all__ = [
    "TERMINAL_CANDIDATES",
    "choose_launcher",
    "launcher_argv",
    "send_to_terminal",
]


def choose_launcher(which=None) -> str | None:
    """挑一个可用的终端可执行文件；一个都没有返回 ``None``。"""
    resolver = which or shutil.which
    for name in TERMINAL_CANDIDATES:
        try:
            found = resolver(name)
        except Exception:                     # noqa: BLE001 - 探测失败当「没有」
            found = None
        if found:
            return str(found)
    return None


def launcher_argv(launcher: str) -> list[str]:
    """把「开一个终端窗口」拼成命令行。

    **刻意不带执行参数**：``cmd.exe /k`` 里没有东西可执行，窗口就是空的；
    Windows Terminal 更是直接开一个空的默认 profile。命令走剪贴板，不走参数 ——
    这样命令里的 ``%`` / ``&`` / ``^`` 之类的元字符不会在路上被 shell 吃掉。
    """
    name = str(launcher or "").strip()
    if not name:
        return []
    base = name.replace("/", "\\").rsplit("\\", 1)[-1].lower()
    if base.startswith("cmd"):
        return [name, "/k"]
    return [name]


def send_to_terminal(text, *, copy=None, which=None, popen=None, cwd=None) -> dict:
    """把 ``text`` 放进剪贴板并开一个终端窗口。

    ``copy``  —— ``copy(text) -> bool``，不开终端也照样先把命令备好。
    ``which`` / ``popen`` —— 见模块头「可注入点」。

    返回 ``{"copied", "opened", "launcher", "reason"}``：``reason`` 是给状态栏
    用的一句话，界面不必自己拼。
    """
    command = str(text or "")
    result = {"copied": False, "opened": False, "launcher": "", "reason": ""}
    if not command.strip():
        result["reason"] = "这条步骤没有命令，没什么可发送的。"
        return result

    if copy is not None:
        try:
            result["copied"] = bool(copy(command))
        except Exception:                      # noqa: BLE001 - 剪贴板失败不该拦住开窗口
            logger.exception("复制命令到剪贴板失败")
            result["copied"] = False

    launcher = choose_launcher(which)
    if not launcher:
        result["reason"] = ("没找到终端程序（Windows Terminal / cmd），"
                            "命令已复制，请手动打开终端粘贴。")
        return result

    argv = launcher_argv(launcher)
    runner = popen or subprocess.Popen
    kwargs = {"cwd": str(cwd)} if cwd else {}
    # 只在 Windows 上带这个 flag；其它平台传了会 TypeError
    if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    try:
        runner(argv, **kwargs)
    except Exception as exc:                   # noqa: BLE001 - 让界面拿到一句话
        logger.exception("打开终端失败")
        result["reason"] = (f"打开终端失败（{exc}），命令已复制，请手动粘贴。"
                            if result["copied"] else f"打开终端失败：{exc}")
        return result

    result["opened"] = True
    result["launcher"] = launcher
    result["reason"] = ("已打开终端，命令在剪贴板里 —— 切到你的 SSH 会话 Ctrl+V 回车。"
                        if result["copied"] else "已打开终端（命令没能进剪贴板，请手动输入）。")
    return result
