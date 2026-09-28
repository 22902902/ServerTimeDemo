# -*- coding: utf-8 -*-
"""开机自启动（Windows 登录时自动拉起本程序）。

设计要点
--------------------------------------------------------------------
* 只写 **HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run**，不碰 HKLM：
  当前用户级自启不需要管理员权限，勾一下即时生效、取消即时报废，也不会影响
  这台机器上的其他用户。（改 HKLM 得提权，而且卸载时容易留垃圾。）
* **注册表才是唯一事实来源**。``app_state`` 里只额外记一对「意图 + 当时写入的
  命令」，用途只有一个：程序被搬到别的目录 / 改名之后，识别出「条目还在、
  但指向老位置」并把它修回当前位置 —— 见 ``StartupManager.repair_drift``。
  为什么不拿 app_state 当「开着没开着」的判据：用户完全可以在任务管理器里
  把这条自启关掉，那时 app_state 说开着、系统实际不启动，界面必须显示真实状态。
* 命令尾巴带 ``--autostart``：程序据此走「静默到托盘」—— 不弹登录框、不抢焦点，
  只用「记住密码」自动登录后常驻托盘，到期提醒照常工作。
* 读写注册表的 **后端可注入**（``WinRegBackend`` / ``DictBackend``）：测试全程用
  内存字典，一个字节都不碰真实注册表；只有一条端到端用例会在**临时键路径**上
  真读写一次，跑完即删。
* 本模块 **不 import tkinter，也不 import main** —— 纯数据层，可以脱离界面单测。
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

try:  # 非 Windows 上导入本模块不该炸；真正用的时候才报错
    import winreg
except ImportError:  # pragma: no cover - 只有非 Windows 会走到
    winreg = None


# ---------------------------------------------------------------------------
# 常量：界面文案、测试、打包都引用这里，别在别处硬编码这些字符串
# ---------------------------------------------------------------------------
AUTOSTART_FLAG = "--autostart"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ServerTimeDemoPersonalSystem"
# app_state 里的两个键：用户意图（"1"/"0"）与启用时写入的命令（供漂移自愈比对）
STATE_INTENT_KEY = "autostart"
STATE_COMMAND_KEY = "autostart_command"
# 「记住密码」的文件名。历史上它既落在程序根目录，也被数据目录迁移过一份，
# 两个位置都可能存在且内容不一定同步 —— 所以解析入口收成候选路径列表。
REMEMBER_FILE_NAME = "remember_me.json"


# ---------------------------------------------------------------------------
# 纯函数：命令行拼装 / 比较 / 凭据解析
# ---------------------------------------------------------------------------

def is_autostart_launch(argv=None) -> bool:
    """本次进程是不是由「开机自启动」拉起来的。

    Windows 拉起 Run 条目时不会再塞别的东西，所以命令行里出现过
    ``--autostart`` 就算。**大小写不敏感** —— 用户手抄这条命令时很可能
    写成 ``--AutoStart``。
    """
    args = sys.argv[1:] if argv is None else list(argv)
    return any(str(item).strip().lower() == AUTOSTART_FLAG for item in args)


def _quote(part) -> str:
    """按 Windows 命令行规则给一段内容加引号。

    Run 条目的值是**一整行命令行**，路径里有空格（``C:\\Program Files\\...``）
    而不加引号，系统会把它拆成「程序 C:\\Program」+ 一串参数。一律加引号最省事，
    也让 expected/actual 的比较稳定。
    """
    text = str(part).strip()
    if not text:
        return ""
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text
    return f'"{text}"'


def executable_for_autostart(*, frozen=None, executable=None, script=None,
                             pythonw=None) -> tuple:
    """算出该拉起哪个可执行文件，返回 ``(可执行文件, 脚本路径或空串)``。

    * 打包版（frozen）：直接拉 exe 自己，不需要脚本。
    * 源码版：优先用同目录的 **pythonw.exe** —— 用 python.exe 会在开机时弹一个
      黑色控制台窗口，很吓人；找不到 pythonw 才退回 python.exe。
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    exe = str(executable or sys.executable)
    if frozen:
        return exe, ""
    script_path = str(script or "")
    if not script_path:
        # 源码版不知道 main.py 在哪就没什么可拉起的，如实返回空脚本
        return exe, ""
    if pythonw is None:
        candidate = Path(exe).with_name("pythonw.exe")
        pythonw = str(candidate) if candidate.exists() else exe
    return str(pythonw), script_path


def build_command(*, frozen=None, executable=None, script=None,
                  flag=AUTOSTART_FLAG) -> str:
    """拼出要写进 Run 的那一整行命令。"""
    exe, script_path = executable_for_autostart(
        frozen=frozen, executable=executable, script=script)
    parts = [_quote(exe)]
    if script_path:
        parts.append(_quote(script_path))
    if flag:
        parts.append(flag)
    return " ".join(part for part in parts if part)


def normalize_command(text) -> str:
    """把一条 Run 命令行归一化，用来判断「是不是同一条」。

    要比掉三件事：引号、大小写、多余空格。还要展开 ``%VAR%`` —— 有些安装器
    写的是 ``%LOCALAPPDATA%\\...``，字面量跟实际路径不同，不展开就会把同一个
    位置误判成「指向别处」。
    """
    expanded = os.path.expandvars(str(text or "")).strip()
    if not expanded:
        return ""
    # 顺带把斜杠统一：Windows 上 C:/x/a.exe 与 C:\\x\\a.exe 是同一个
    # 文件，不统一就会把同一条命令误判成「指向别处」，白报一次陈旧。
    return " ".join(expanded.replace('"', " ").replace("\\", "/").split()).lower()


def _decode_b64(value) -> str:
    """把「记住密码」文件里的 base64 字段解回明文；解不出就返回空串。"""
    if not value:
        return ""
    try:
        return base64.b64decode(str(value)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def load_remember_file(path) -> dict:
    """读一个 ``remember_me.json``，返回**已解码**的字典；不可用时返回空字典。

    返回 ``{}`` 的三种情况：文件不存在、不是合法 JSON、没勾「记住密码」。
    勾了记住时返回 ``{"username": ..., "password": ..., "remember": True}``，
    其中两个字段**可能是空串**（勾了记住但框里是空的）—— 这是刻意的：登录框
    要照搬这两个值去预填输入框，不该由这里替它决定「空的就换成默认值」。
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not data.get("remember"):
        return {}
    return {
        "username": _decode_b64(data.get("username")),
        "password": _decode_b64(data.get("password")),
        "remember": True,
    }


def read_remembered_credentials(candidates) -> tuple | None:
    """取出「记住密码」里的 ``(用户名, 密码)``；拿不到就返回 ``None``。

    这是 ``remember_me.json`` 的**唯一解析入口**（主窗口的登录框也走这里），
    免得「静默登录」和「手动登录」各解一套，哪天格式变了只改了一边。

    参数可以是一个路径，也可以是一串候选路径（按顺序取第一个能用的）。
    为什么要候选：这个文件既在程序根目录、也被数据目录迁移过一份，两处都可能
    存在且内容不一定同步。
    """
    if isinstance(candidates, (str, Path)):
        candidates = [candidates]
    for raw_path in candidates or ():
        data = load_remember_file(raw_path)
        if not data:
            continue
        if data["username"] and data["password"]:
            return data["username"], data["password"]
    return None


# ---------------------------------------------------------------------------
# 后端：注册表读写（真实 / 内存）
# ---------------------------------------------------------------------------

class DictBackend:
    """内存后端：测试用，一个字节都不碰真实注册表。"""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def read(self, name):
        return self.values.get(name)

    def write(self, name, value):
        self.values[name] = value

    def delete(self, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class WinRegBackend:
    """真实注册表后端：认准 HKCU 下的一条子键（默认就是 Run）。"""

    def __init__(self, key_path=RUN_KEY_PATH, root=None):
        if winreg is None:  # pragma: no cover - 非 Windows
            raise RuntimeError("当前环境没有 winreg，无法读写注册表。")
        self.key_path = key_path
        self.root = winreg.HKEY_CURRENT_USER if root is None else root

    def _open(self, *, create: bool):
        access = winreg.KEY_READ | winreg.KEY_SET_VALUE
        if create:
            # CreateKeyEx 会顺带建出缺失的中间层，所以临时键路径也能直接用
            return winreg.CreateKeyEx(self.root, self.key_path, 0, access)
        return winreg.OpenKey(self.root, self.key_path, 0, access)

    def read(self, name):
        try:
            key = self._open(create=False)
        except FileNotFoundError:
            return None
        try:
            value, _kind = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)
        return "" if value is None else str(value)

    def write(self, name, value):
        key = self._open(create=True)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))
        finally:
            winreg.CloseKey(key)

    def delete(self, name):
        try:
            key = self._open(create=False)
        except FileNotFoundError:
            raise FileNotFoundError(name)
        try:
            winreg.DeleteValue(key, name)
        finally:
            winreg.CloseKey(key)


# ---------------------------------------------------------------------------
# 管理器
# ---------------------------------------------------------------------------

class StartupManager:
    """「开机自启动」的读写与自愈。

    所有外部依赖都可注入（后端、可执行文件、脚本、frozen 标志），所以测试既能用
    内存后端跑纯逻辑，也能用 ``WinRegBackend`` + **临时键路径**跑一次真注册表。
    """

    def __init__(self, *, backend=None, value_name=VALUE_NAME, key_path=RUN_KEY_PATH,
                 frozen=None, executable=None, script=None, flag=AUTOSTART_FLAG):
        if backend is None:
            backend = WinRegBackend(key_path) if winreg is not None else DictBackend()
        self.backend = backend
        self.value_name = value_name
        self.key_path = key_path
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
        self.executable = str(executable or sys.executable)
        self.script = str(script) if script else ""
        self.flag = flag

    # -- 命令 ---------------------------------------------------------------
    def expected_command(self) -> str:
        """本程序「此刻」应该写进注册表的那条命令。"""
        return build_command(frozen=self.frozen, executable=self.executable,
                             script=self.script, flag=self.flag)

    def read_command(self) -> str:
        """注册表里现存的那条命令；没有（或读不动）返回空串。"""
        try:
            return str(self.backend.read(self.value_name) or "")
        except OSError:
            return ""

    # -- 状态 ---------------------------------------------------------------
    def is_enabled(self) -> bool:
        """条目存在、且**正好指向本程序此刻的位置**。"""
        current = self.read_command()
        if not current:
            return False
        return normalize_command(current) == normalize_command(self.expected_command())

    def is_stale(self) -> bool:
        """条目存在、但指向的不是此刻的位置（程序被搬走 / 别的东西写的）。"""
        return bool(self.read_command()) and not self.is_enabled()

    def state(self) -> dict:
        """给界面看的一份快照 —— 全是**真实**状态，不是用户意图。"""
        current = self.read_command()
        expected = self.expected_command()
        return {
            "enabled": bool(current) and normalize_command(current) == normalize_command(expected),
            "stale": bool(current) and normalize_command(current) != normalize_command(expected),
            "command": current,
            "expected": expected,
            "value_name": self.value_name,
            "key_path": self.key_path,
        }

    # -- 开关 ---------------------------------------------------------------
    def enable(self) -> tuple:
        """写入自启动条目，并**回读校验**，返回 ``(是否成功, 命令或错误说明)``。

        回读这一步不能省：注册表写入在权限不足 / 被安全软件拦下时可能不抛异常
        却也没生效，只报「成功」等于骗用户。
        """
        command = self.expected_command()
        try:
            self.backend.write(self.value_name, command)
        except OSError as exc:
            return False, f"写入注册表失败：{exc}"
        if normalize_command(self.read_command()) != normalize_command(command):
            return False, "写入注册表后回读不一致，可能被安全软件拦截了。"
        return True, command

    def disable(self) -> tuple:
        """删掉自启动条目，并回读确认，返回 ``(是否成功, 错误说明)``。

        条目本来就不存在算成功 —— 用户要的结果是「关掉」，本来就没开就是关着。
        """
        try:
            self.backend.delete(self.value_name)
        except FileNotFoundError:
            return True, ""
        except OSError as exc:
            return False, f"删除注册表项失败：{exc}"
        if self.read_command():
            return False, "删除后回读该条目仍在，可能被安全策略拦住了。"
        return True, ""

    # -- 自愈 ---------------------------------------------------------------
    def repair_drift(self, remembered_command: str) -> dict:
        """程序被搬目录 / 改名后，把条目改回指向现在的位置。

        只在「条目还在、而且内容和当初我们写进去的那条一模一样」时动手。
        另外两种情况**一律不碰**，因为它们表达的是别人的选择：

        * 条目被删了（用户在任务管理器里关掉）→ 偷偷加回来是在跟用户对着干；
        * 条目内容被改成了别的 → 那不是我们的东西，改了是破坏。

        返回 ``{"repaired": bool, "message": str}``。
        """
        current = self.read_command()
        if not current:
            return {"repaired": False, "message": ""}
        expected = self.expected_command()
        if normalize_command(current) == normalize_command(expected):
            return {"repaired": False, "message": ""}
        if normalize_command(current) != normalize_command(remembered_command or ""):
            return {"repaired": False,
                    "message": "自启动条目指向的位置不是本程序记录的那一处，未改动。"}
        ok, detail = self.enable()
        if not ok:
            return {"repaired": False, "message": f"自启动条目修复失败：{detail}"}
        return {"repaired": True,
                "message": f"程序位置已变化，开机自启动条目已更新为：{detail}"}
