# -*- coding: utf-8 -*-
"""Python 语法手册 · 正文（第二部分：第八章 ~ 附录）。

块类型说明见 manual_engine 的模块 docstring。
其中 ``("module_table",)`` 与 ``("test_table",)`` 是**占位块**：
真内容由 make_python_manual.py 在生成时现算（扫源码目录、读测试结果），
于是这两张表永远不会过时。
"""

from __future__ import annotations

BLOCKS = [
    # =========================================================================
    # 第八章
    # =========================================================================
    ("h1", "第八章 异常处理"),
    ("p", "异常不是错误，是**控制流的一种**。Python 的哲学是「先让它抛出来，"
          "在知道怎么处理的地方处理掉」，而不是层层返回错误码。"
          "但「在哪里处理」和「处理成什么样」是本项目花了不少笔墨的地方。"),

    ("h2", "8.1 try 语句的四个部分"),
    ("table", [
        ["部分", "执行时机", "用途"],
        ["`try:`", "总是", "放可能抛异常的代码"],
        ["`except E:`", "try 里抛出 E 时", "处理；可写多个，**从上往下匹配**"],
        ["`else:`", "try 里没抛异常时", "放「只在成功后才做」的事，别塞进 try"],
        ["`finally:`", "无论如何", "清理：关文件、恢复状态、续期定时器"],
    ]),
    ("code", "python", '''    def todo_alert_check(self):
        """巡检一次「有没有提醒该响了」。"""
        if getattr(self, "_exiting", False):
            return
        try:
            self._run_todo_alerts()
        except Exception:
            logger.exception("待办到点提醒巡检失败")
        finally:
            self.after(TODO_TICK_MS, self.todo_alert_check)
'''),
    ("caption", "▲ main.py · 一个把四个部分用到极致的例子（这里只用了三个）"),
    ("ok", "为什么续期放在 finally 而不是 try 的末尾",
     "这是本项目的定时器纪律：**「续期」必须无条件执行**。\n"
     "如果写成 `try: 干活(); self.after(...)` —— 一旦「干活」抛异常，"
     "`after` 永远不会被调用，**这个定时器就彻底死了**，"
     "之后再也不会有任何提醒。这类 bug 用户不会看到报错，只会觉得"
     "「提醒时好时坏」。测试里专门塞了一个会抛异常的替身来钉住这条。"),
    ("note", "`except Exception` 而不是裸 `except:`",
     "裸 `except:` 会连 `KeyboardInterrupt`（Ctrl+C）和 `SystemExit` 一起吞掉，"
     "让程序无法正常中断。项目里所有兜底都是 `except Exception`，"
     "只有极少数「清理路径」才用裸 except 且立刻继续抛。"),

    ("h2", "8.2 常见内置异常与层级"),
    ("out", """BaseException
├── SystemExit                  sys.exit() 抛的
├── KeyboardInterrupt           Ctrl+C
└── Exception                   ← 业务代码该捕获的都在这下面
    ├── ArithmeticError ── ZeroDivisionError
    ├── LookupError ────── IndexError / KeyError
    ├── OSError ────────── FileNotFoundError / PermissionError
    ├── ValueError               值对、类型不对
    ├── TypeError                类型不对
    ├── AttributeError           没有这个属性
    ├── RuntimeError ───── RecursionError
    ├── ImportError ────── ModuleNotFoundError
    └── StopIteration            迭代器耗尽"""),
    ("caption", "▲ 只需要记住三件事：业务兜底捕 Exception、LookupError 管下标和键、其余按需"),
    ("table", [
        ["异常", "典型触发", "本项目里的位置"],
        ["`ValueError`", "`int(\"abc\")`、`strptime` 格式不符", "`parse_moment()` 拆时间"],
        ["`KeyError`", "`d[\"不存在的键\"]`", "优先用 `d.get(k, 默认)` 规避"],
        ["`TypeError`", "`1 + \"a\"`、参数个数不对", "编码 bug，不该捕获"],
        ["`AttributeError`", "`None.foo`、访问不存在的方法", "`import pygments` 之后取属性"],
        ["`OSError` / `FileNotFoundError`", "文件不存在、权限不足", "日志目录建不出来时降级"],
        ["`sqlite3.Error`", "SQL 错误、表不存在", "数据层"],
        ["`tk.TclError`", "控件已销毁、字体无效", "界面层点击态与字体缓存"],
        ["`ImportError`", "可选依赖没装", "`openpyxl` 的延迟导入"],
    ]),

    ("h2", "8.3 raise 与异常链 from"),
    ("code", "python", '''def load_excel_assets(file_path: Path) -> list[dict]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("缺少 openpyxl，请先执行 pip install -r requirements.txt") from exc
'''),
    ("caption", "▲ main.py · 把「依赖没装」翻译成「用户看得懂的一句话」"),
    ("p", "`raise ... from exc` 保留了**原始异常**，Python 会把两条都打印出来："),
    ("out", """Traceback (most recent call last):
  File \"main.py\", line 2323, in load_excel_assets
    from openpyxl import load_workbook
ModuleNotFoundError: No module named 'openpyxl'

The above exception was the direct cause of the following exception:

RuntimeError: 缺少 openpyxl，请先执行 pip install -r requirements.txt"""),
    ("caption", "▲ from 会把「直接原因」写在上面，排查时两层都能看到"),
    ("table", [
        ["写法", "效果"],
        ["`raise`", "在 except 里原样重抛，保持原异常"],
        ["`raise NewError(...)`", "抛新的，原异常挂成 `__context__`（隐式链）"],
        ["`raise NewError(...) from exc`", "**显式链**，明确「是它导致的」"],
        ["`raise NewError(...) from None`", "**掐断链**，只显示新异常（当原异常是噪音时）"],
    ]),
    ("note", "什么时候该 `from None`",
     "当原始异常对使用者毫无意义、只会吓人时 —— 比如「配置文件里某个字段格式不对」，"
     "底层抛的是 `KeyError: 'port'`，对用户没用。这时候 `from None` 只留自己那句。"
     "但**调试期不要掐** —— 排障时你正需要那层原始信息。"),

    ("h2", "8.4 两种处理风格，以及怎么选"),
    ("p", "本项目里两种风格都在用，而且分得很清楚：**记日志** vs **静默降级**。"),
    ("h3", "风格一：记日志（出问题了我要知道）"),
    ("code", "python", '''    def _after_todo_alert(self):
        """提醒窗里点过「完成」/「稍后提醒」之后刷新待办页。"""
        try:
            self.todo_view.refresh()
        except Exception:
            logger.exception("提醒处理后刷新待办页失败")
'''),
    ("caption", "▲ main.py · `logger.exception` 会自动带上完整堆栈"),
    ("p", "`logger.exception` 等价于 `logger.error(..., exc_info=True)`，"
          "**只能在 except 块里用**（它靠 `sys.exc_info()` 取当前异常）。"
          "它的输出会落到 `ExpiryManager_Data/logs/app.log`。"),
    ("h3", "风格二：静默降级（失败也无关紧要）"),
    ("code", "python", '''import pygments


def _get_highlighter():
    try:
        from pygments.lexers import PythonLexer
        from pygments.formatters import HtmlFormatter
    except ImportError:
        return None          # 没装 pygments 就没有语法高亮，功能照常
    return PythonLexer(), HtmlFormatter()
'''),
    ("caption", "▲ 可选的第三方依赖：装不装都能跑"),
    ("table", [
        ["场景", "选择", "理由"],
        ["核心流程失败（存库、读配置）", "记日志 + 上报用户", "静默失败会让数据悄悄丢失"],
        ["可选依赖缺失", "静默降级", "功能变弱，但程序可用"],
        ["清理路径（关连接、恢复界面）", "静默忽略", "此刻再抛异常只会盖住真正的错"],
        ["定时器 / 事件回调", "记日志 + **保证继续运行**", "断掉之后不会自己恢复"],
        ["用户输入格式错", "不抛异常，返回 None / 默认值", "属于正常业务分支"],
    ]),
    ("warn", "静默降级最大的风险是「假装没事」",
     "`except: pass` 会让一个功能**长期不工作而没人发现**。"
     "本项目因此定了一条：**静默降级必须写明「降级之后是什么状态」**。"
     "上面那段 pygments 的例子，`return None` 的语义是「没有高亮器」，"
     "调用方拿到 None 会走纯文本渲染 —— 这就是一句能读懂的空兜底，"
     "而不是「不知道发生了什么，反正没崩」。"),

    ("h2", "8.5 assert：只用来钉「不可能发生」"),
    ("warn", "assert 会在 -O 优化模式下被整体删掉",
     "`python -O script.py` 时所有 `assert` 语句消失。所以：\n"
     "**绝不能用 assert 做输入校验或安全检查**（`assert user.is_admin` 这种写法在 "
     "`-O` 下直接失效）。\n"
     "**该用的是「内部不变量」** —— 描述「如果这行不成立，说明代码本身写错了」。"),
    ("code", "python", '''# 内部不变量：锚点必须命中一次，否则说明源码已经被改动过
assert raw.count(old) == 1, f"锚点命中 {raw.count(old)} 次，本应恰好 1 次"
'''),
    ("caption", "▲ 本项目所有字节级补丁脚本的第一道闸"),
    ("p", "项目里 `assert` 出现最多的地方是两个：**补丁脚本**（保证替换唯一）与"
          "**回归测试**（断言行为）。业务代码里几乎见不到 —— 业务条件一律用 `if` 加"
          "正常控制流处理。"),

    ("h2", "8.6 自定义异常"),
    ("code", "python", '''class CaptureFailed(RuntimeError):
    """抓图失败（窗口句柄不对、窗口已销毁、或抓到的是纯色空图）。"""
'''),
    ("caption", "▲ scripts/window_shot.py · 一个自定义异常的完整定义只要三行"),
    ("p", "继承哪个基类是有讲究的：这里选 `RuntimeError` 而不是 `Exception`，"
          "含义是「**运行环境的问题**，不是调用方传错了参数」——"
          "后者该继承 `ValueError`，参数类型问题该继承 `TypeError`。"
          "选对了，调用方就能写出有意义的 `except`。"),
    ("code", "python", '''    colors = image.getcolors(maxcolors=1 << 20) or []
    if len(colors) < min_colors:
        raise CaptureFailed(
            f"只抓到 {len(colors)} 种颜色（{colors[:1]}）—— PrintWindow 没生效")
'''),
    ("caption", "▲ 抛的时候带上现场数据，收到的人不用再复现一次"),
    ("ok", "自定义异常的规矩",
     "① **定义要短**，docstring 说清「什么情况下会抛」；\n"
     "② **基类选对**（ValueError / TypeError / RuntimeError / OSError），"
     "让调用方能按语义捕获；\n"
     "③ **消息里带上下文**（期望值、实际值、关键变量），不要只写「失败了」；\n"
     "④ 不要为了「显得专业」而给每个函数配一个异常类 —— "
     "本项目的 83 个文件里只定义了一个。"),
    ("pagebreak",),

    # =========================================================================
    # 第九章
    # =========================================================================
    ("h1", "第九章 模块、包与导入"),
    ("p", "一个 `.py` 文件就是一个模块，一个含 `__init__.py` 的目录就是一个包。"
          "本项目的导入语句里藏着几条实用经验，这一章一起讲。"),

    ("h2", "9.1 导入的四种写法"),
    ("table", [
        ["写法", "含义", "项目里的例子"],
        ["`import sqlite3`", "导入模块，用时 `sqlite3.Row`", "标准库一律这么导"],
        ["`from pathlib import Path`", "导入名字", "文件路径操作"],
        ["`from datetime import date, datetime, timedelta`", "导入多个名字", "时间计算"],
        ["`import numpy as np`", "起别名", "本项目没用到，但 `import tkinter as tk` 同理"],
    ]),
    ("code", "python", '''from __future__ import annotations

import calendar
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
'''),
    ("caption", "▲ todo_db.py 的导入区 —— 顺序是「标准库 → 第三方 → 本项目」"),
    ("note", "导入顺序不是形式主义",
     "PEP 8 建议分三段（标准库 / 第三方 / 本项目），段间空一行。"
     "好处很实际：**一眼看出这个模块依赖了几个外部包**。"
     "本项目的第三方依赖只有 `openpyxl` 与可选的 `pygments`，"
     "所以「第三方段」经常是空的 —— 这本身就是一条信息："
     "**这个程序装起来几乎没有外部依赖。**\n"
     "`from __future__ import annotations` 必须放最前，它是编译器指令，"
     "位置错了会直接 SyntaxError。"),
    ("h3", "别用 `from module import *`"),
    ("code", "python", '''# 不推荐：不知道导进来了什么，还可能覆盖同名变量
from todo_db import *


# 推荐：明确列出
from todo_db import TodoDB, TodoItem, ALERT_GRACE_MINUTES
'''),
    ("caption", "▲ 对比（项目没有使用星号导入）"),

    ("h2", "9.2 if __name__ == \"__main__\""),
    ("p", "`__name__` 是模块的「名字」：**被导入时是模块名，被直接运行时是字符串 `\"__main__\"`**。"
          "所以这个守卫的含义是「只有当我被当作脚本运行时才执行」。"),
    ("code", "python", '''if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import tkinter as tk

    root = tk.Tk()
    root.title("截图自检")
    root.geometry("320x140+80+80")
    tk.Label(root, text="PrintWindow 自检", font=("Microsoft YaHei UI", 14)).pack(pady=30)
    root.update()
    try:
        image = shot_widget(root, out)
        print(f"OK  抓到 {image.size[0]}x{image.size[1]} → {out}")
    finally:
        root.destroy()
'''),
    ("caption", "▲ scripts/window_shot.py 末尾：既是库，也是可自检的命令行工具"),
    ("p", "本项目的 `scripts/` 下几乎每个文件都有这一段，好处是"
          "**同一个文件既能被测试导入，也能单独跑一次做自检** —— "
          "`python scripts/window_shot.py` 会立刻告诉你截图功能在这台机器上可不可用。"),
    ("warn", "守卫里做的事要「无副作用」或明说副作用",
     "`main.py` 是**唯一**一个没有 `if __name__ == \"__main__\"` 守卫的主模块吗？"
     "并不是 —— 它也有，而且里面只做一件事：建单实例互斥、配日志、起 `mainloop()`。"
     "**千万不要在模块顶层写有副作用的代码**（建文件、连数据库、弹窗），"
     "否则别人只是 `import` 一下就触发了。"),

    ("h2", "9.3 包、相对导入与 __init__.py"),
    ("out", """embedded_admin_tools/
├── __init__.py
├── api_demo_window.py          界面
├── crypto_window.py
├── returnCode.json             数据
└── services/                   业务与数据
    ├── api_client.py
    ├── crypto_service.py
    ├── error_code_service.py
    ├── icon_service.py
    └── interface_service.py"""),
    ("caption", "▲ 内置工具包的分层"),
    ("code", "python", '''import json
import tkinter as tk

from .services.api_client import ApiClient
from .services.crypto_service import DESCryptoService
from .services.error_code_service import ErrorCodeService
from .services.icon_service import save_temp_icon
'''),
    ("caption", "▲ embedded_admin_tools/market_quote_window.py · 用相对导入引同包内的模块"),
    ("table", [
        ["写法", "含义"],
        ["`from . import x`", "同包内"],
        ["`from .sibling import x`", "同包的子模块"],
        ["`from .. import x`", "上一级包"],
        ["`from .services.x import Y`", "同包的子包"],
    ]),
    ("note", "`__init__.py` 现在可以省略，但本项目仍然放着",
     "Python 3.3+ 支持「命名空间包」，没有 `__init__.py` 也能导入。"
     "但显式放着它有两个好处：**① 让工具（打包器、IDE）明确知道这是包**；"
     "**② 它是「包级初始化」的落点**。本项目选择保持显式。"),
    ("p", "另一个值得记的细节：`embedded_admin_tools/` 根目录下有若干同名文件"
          "（如 `error_code_service.py`），它们是**带 docstring 的 6 行兼容包装**，"
          "内部转发到 `services/` 里的真实现 —— 为的是老的 `import` 路径不断。"
          "**看起来像重复代码，其实是有意的兼容层**，不要删。"),

    ("h2", "9.4 延迟导入：把 800 毫秒挪出启动路径"),
    ("code", "python", '''def load_excel_assets(file_path: Path) -> list[dict]:
    try:
        from openpyxl import load_workbook      # 放在函数里，不放在文件顶部
    except ImportError as exc:
        raise RuntimeError("缺少 openpyxl，请先执行 pip install -r requirements.txt") from exc
'''),
    ("caption", "▲ main.py · openpyxl 按需导入"),
    ("note", "为什么不用模块级 import",
     "`openpyxl` 的导入要花大约 **800 毫秒** —— 对一个双击就期待看到界面的桌面程序来说，"
     "这是能感觉到的延迟。而「导入 Excel」是低频操作，很可能一次都用不上。\n"
     "**判断标准：贵 + 少用 = 延迟导入；便宜 + 常用 = 放文件顶部。**"
     "延迟导入的代价是「每次调用都要查一次 `sys.modules`」（微秒级，可忽略），"
     "以及错误发现得晚（所以要配一个清楚的 `ImportError` 提示）。"),
    ("warn", "延迟导入不能用在「热路径」里",
     "如果一个函数每秒被调用几百次（比如渲染循环、事件处理），"
     "在里面写 `from x import y` 虽然 Python 有缓存不会重新加载，"
     "但每次仍要走一遍查找与加锁逻辑。**贵的东西放函数里，热的路径别放。**"),

    ("h2", "9.5 冻结（打包）后的路径"),
    ("code", "python", '''def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "ExpiryManager_Data"
'''),
    ("caption", "▲ main.py · 一个函数解决「源码运行」与「打包运行」的路径差异"),
    ("table", [
        ["", "源码运行", "PyInstaller 打包后"],
        ["`__file__`", "`.py` 文件的路径", "指向临时解包目录（且每次运行都不同）"],
        ["`sys.executable`", "python.exe 的路径", "**exe 自身的路径**"],
        ["`sys.frozen`", "不存在", "`True`"],
        ["`sys._MEIPASS`", "不存在", "临时解包目录（放只读资源）"],
    ]),
    ("warn", "这是打包程序最容易踩的坑",
     "把数据目录建在 `__file__` 旁边，在打包版里会建到临时解包目录 —— "
     "**程序关掉数据就没了**，而且每次运行都从空白开始。"
     "正确做法就是上面这三行：**判断 `sys.frozen`，用 `sys.executable` 定位 exe，"
     "把数据放在 exe 同级目录**。\n"
     "顺带一个排查技巧：`sys._MEIPASS` 存在就说明正在打包环境里跑，"
     "打印它可以确认资源被解包到哪了。"),

    ("h2", "9.6 sys.path 与脚本运行"),
    ("code", "python", '''if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import tkinter as tk
'''),
    ("caption", "▲ scripts/window_shot.py：把项目根目录加进搜索路径，才能 import 项目模块"),
    ("p", "运行的脚本所在目录会自动进 `sys.path`，但**脚本的父目录不会**。所以"
          "`scripts/` 下的工具要导入根目录的 `todo_db`，就得自己插一条路径"
          "（`parent.parent` 就是根目录）。"),
    ("note", "`sys.path.insert(0, ...)` 里的 0",
     "0 表示插到**最前面**，优先级最高。用 `append` 是插到最后，"
     "可能被同名的已安装包抢先。这里要的是「优先用项目里的这一份」，所以是 0。"),
    ("pagebreak",),

    # =========================================================================
    # 第十章
    # =========================================================================
    ("h1", "第十章 类型注解"),
    ("p", "类型注解是给「读代码的人」和「静态检查工具」看的。**运行时它默认不生效** ——"
          "写成 `def f(x: int)` 之后传字符串照样能跑。理解这一点，就不会"
          "把它当成语言层面的类型约束了。"),

    ("h2", "10.1 注解写在三个地方"),
    ("code", "python", '''count: int = 0                      # 1. 变量
cache: dict = {}                    #     有注解就一定会成为 dataclass 字段
                                    #     （所以类体里给变量加注解要谨慎）

def snooze(self, item_id: int,      # 2. 参数
           minutes: int = SNOOZE_MINUTES,
           now: Optional[datetime] = None) -> str:   # 3. 返回值
    ...
'''),
    ("caption", "▲ 三种位置的注解（todo_db.py · snooze 的签名）"),
    ("note", "类体里的注解有额外含义",
     "在 `@dataclass` 装饰的类里，**每一条带注解的类属性都会变成一个字段**。"
     "所以下面这两种写法语义完全不同：\n"
     "`x: int = 0` → dataclass 认它是字段，进 `__init__` 参数表。\n"
     "`x = 0` → 只是普通类属性，**不进 `__init__`**。\n"
     "想加一个「不属于构造参数」的类级常量，就不要写注解，或者用 "
     "`field(init=False)`。"),

    ("h2", "10.2 Optional 与联合类型"),
    ("table", [
        ["写法", "含义", "备注"],
        ["`Optional[datetime]`", "`datetime` 或 `None`", "等价于 `Union[datetime, None]`"],
        ["`Union[int, str]`", "两者之一", "3.10 起可写 `int | str`"],
        ["`int | None`", "同上（3.10+）", "**旧版本解释器会直接 SyntaxError**"],
        ["`Any`", "任意类型", "等于放弃检查，少用"],
        ["`Literal[\"a\", \"b\"]`", "限定几个字面量值", "很适合表示「状态字符串」"],
        ["`Final`", "常量标记", "`Final[int] = 10`"],
    ]),
    ("code", "python", '''from typing import Optional

def alert_moment(item: "TodoItem") -> Optional[datetime]:
    """一条待办「下一次该响」的时刻；没设日期或时间时返回 None。"""
    if not _norm(item.due_date) or not _norm(item.due_time):
        return None
    ...
'''),
    ("caption", "▲ todo_db.py · `Optional[...]` 是项目里最常用的类型包装"),
    ("warn", "本项目写 `Optional[X]` 而不是 `X | None`",
     "两种写法在 3.10+ 等价，而且加了 `from __future__ import annotations` 之后"
     "连 3.7 都能用 `|` 写法（因为注解不再被求值）。本项目仍统一用 "
     "`Optional[X]`，原因是**它也是给不熟悉新语法的读者看的**，"
     "而且项目里有一部分模块没有加 future 导入。**在同一个代码库里保持一致，"
     "比「用上最新语法」更重要。**"),

    ("h2", "10.3 容器泛型"),
    ("code", "python", '''REPEAT_RULES: list[tuple[str, str]] = [("none", "永不"), ...]
LIST_ICONS: list[str] = ["list", "check", ...]
moments: dict[int, str] = {}
counts: dict[str, int] = {}
self._holidays_cache: Optional[dict[str, Holiday]] = None
'''),
    ("caption", "▲ todo_db.py · 泛型容器的几种常见嵌套"),
    ("table", [
        ["写法", "含义"],
        ["`list[str]`", "字符串列表"],
        ["`tuple[str, str]`", "固定两个元素的元组"],
        ["`dict[str, int]`", "键是 str、值是 int"],
        ["`list[tuple[str, str]]`", "二元组构成的列表（本项目的表数据都是这个）"],
        ["`set[int]`", "整数集合"],
        ["`Sequence[str]`", "只读序列（比 `list` 更宽松，参数建议用它）"],
        ["`Iterable[str]`", "可迭代对象"],
        ["`Iterator[str]`", "迭代器"],
    ]),
    ("note", "注解里的泛型不参与运行",
     "`list[str]` 在运行期并不检查元素类型，它是「给人看的契约」。"
     "真要在运行期校验得自己写断言，或者用 `pydantic` 之类的库。"
     "本项目选择**不校验** —— 数据来源是自己写的 SQL 与自己的界面，"
     "注解的作用是「读代码时不用猜」。"),

    ("h2", "10.4 Callable：把函数当参数传时怎么标注"),
    ("code", "python", '''from typing import Callable, Optional


class ConsolePage(ttk.Frame):
    def __init__(self, master, log_path: Path,
                 on_status: Optional[Callable[[str], None]] = None):
        ...
'''),
    ("caption", "▲ console_page.py · 回调参数的标注方式"),
    ("table", [
        ["写法", "含义"],
        ["`Callable[[str], None]`", "收一个 str、返回 None 的函数"],
        ["`Callable[..., None]`", "参数随便、返回 None"],
        ["`Callable[[], None]`", "无参数、无返回值（`command=` 最常见）"],
        ["`Optional[Callable[[int], None]]`", "**可为 None 的回调** —— 传不传都行"],
    ]),
    ("note", "`Optional[Callable[...]]` 是界面代码里的标准形状",
     "组件的回调参数几乎总是「可选」的 —— 谁用谁传。"
     "项目里所有窗口类的构造参数都遵循这个形状："
     "`on_changed=` / `on_open=` / `on_close=`，默认 `None`，"
     "用时先判 `if self.on_open:` 再调用。"),
    ("code", "python", '''        self._on_open = on_open
        ...
    def _open(self, item):
        if self._on_open is None:
            return
        self._on_open(item.id)
'''),
    ("caption", "▲ 回调的调用点必须判空（本项目所有组件都遵守）"),

    ("h2", "10.5 from __future__ import annotations"),
    ("code", "python", '''from __future__ import annotations        # 必须放在文件第一条语句之后

class TreeNode:
    def attach(self, parent: TreeNode) -> TreeNode:    # 不用写引号了
        ...
'''),
    ("caption", "▲ 加了它之后，注解不必是「运行时可求值」的"),
    ("table", [
        ["", "不加 future", "加了 future"],
        ["注解求值时机", "定义时**立即求值**", "全部变成字符串，永不求值"],
        ["前向引用", "必须写 `-> \"TodoList\"`", "直接写 `-> TodoList`"],
        ["用新语法（`int | str`）", "要 3.10+", "3.7+ 都行"],
        ["性能", "每个函数定义都要求值注解", "零开销"],
        ["用 `get_type_hints()`", "直接可用", "仍可用（会主动求值字符串）"],
    ]),
    ("code", "python", '''@dataclass
class TodoList:
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TodoList":     # 没有 future 导入时的写法
        return cls(...)
'''),
    ("caption", "▲ todo_db.py 用了引号包住类名 —— 因为它有 future 导入之前的历史写法"),
    ("warn", "引号包类型名是「没有 future 导入」时的必需动作",
     "`-> TodoList` 写在 `class TodoList` 内部时，类本身还没定义完，"
     "立即求值会抛 `NameError`。加引号让它延迟成字符串即可。"
     "**加了 `from __future__ import annotations` 之后就不需要引号了** ——"
     "本项目两种写法并存（老模块带引号、新模块带 future），"
     "新写代码建议统一带 future。"),

    ("h2", "10.6 注解不参与运行 —— 一条必须记住的边界"),
    ("out", """>>> def f(x: int) -> str:
...     return x          # 返回的是 int，不是 str
>>> f("我甚至传了个字符串")
'我甚至传了个字符串'      # 一切正常，没有任何报错"""),
    ("caption", "▲ 注解完全不影响运行"),
    ("p", "想要运行期检查，有三条路：**手动 `isinstance`**、"
          "**用 `pydantic` / `attrs` 这类校验库**、或者**靠测试**。"
          "本项目走第三条 —— 1053 个断言构成的回归测试就是它的「类型检查器」，"
          "而且是**检查行为而不是检查声明**的那种。"),
    ("ok", "类型注解在本项目的实际定位",
     "它不是约束，而是**文档**。价值体现在三处：① IDE 的自动补全与跳转；"
     "② 读代码时不用翻实现就能知道参数形状；③ `@dataclass` 靠它生成 `__init__`"
     "（这是唯一「有实际作用」的用法）。\n"
     "所以项目里**没注解的地方也不必补** —— 补了不影响运行，漏了不出错。"
     "但 `@dataclass` 的字段必须有注解，那是硬要求。"),
    ("pagebreak",),

    # =========================================================================
    # 第十一章
    # =========================================================================
    ("h1", "第十一章 标准库实战"),
    ("p", "Python 的「自带电池」在这项目里用得很实际：**没有引入任何 Web 框架、"
          "ORM、配置库**，全部靠标准库完成。这一章按模块讲，每个都配项目里的真实用法。"),

    ("h2", "11.1 pathlib：路径就用 / 拼"),
    ("code", "python", '''from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "ExpiryManager_Data"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "expiry_manager.db"

LOG_DIR.mkdir(parents=True, exist_ok=True)      # 不存在就建，存在也不报错
'''),
    ("caption", "▲ main.py · 路径拼接与目录创建"),
    ("table", [
        ["操作", "写法"],
        ["拼接", "`p / \"sub\" / \"file.txt\"`（`/` 被重载成拼接）"],
        ["取父目录", "`p.parent`、`p.parents[1]`"],
        ["取文件名 / 后缀 / 主干", "`p.name`、`p.suffix`、`p.stem`"],
        ["绝对化", "`p.resolve()`"],
        ["存在性", "`p.exists()`、`p.is_file()`、`p.is_dir()`"],
        ["建目录", "`p.mkdir(parents=True, exist_ok=True)`"],
        ["遍历", "`p.iterdir()`、`p.glob(\"*.py\")`、`p.rglob(\"*.py\")`"],
        ["读 / 写文本", "`p.read_text(encoding=\"utf-8\")` / `p.write_text(...)`"],
        ["读 / 写字节", "`p.read_bytes()` / `p.write_bytes(...)`"],
    ]),
    ("warn", "`write_text` 会把行尾换成 CRLF（Windows）",
     "`Path.write_text()` 走的是文本模式，Windows 下**默认把 `\\n` 翻译成 `\\r\\n`**。"
     "本项目因此踩过一次：一个纯 LF 的测试脚本被 `write_text` 写回后"
     "变成 946 个 CRLF，`git diff` 从「改几行」炸成「改 946 行」。"
     "**要精确保住行尾，只能用 `write_bytes()`。** 详见 13.1、13.2。"),

    ("h2", "11.2 datetime 与 calendar：日期计算的三个必备套路"),
    ("h3", "套路一：按自然月推进，天数不足时收敛到月末"),
    ("code", "python", '''def add_months(base: date, months: int) -> date:
    """按自然月推进，遇到目标月天数不足时收敛到该月最后一天。

    例：1 月 31 日 + 1 个月 → 2 月 28/29 日（而不是抛异常或滚到 3 月）。
    """
    total = (base.year * 12 + base.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_years(base: date, years: int) -> date:
    """按自然年推进，2 月 29 日在平年收敛到 2 月 28 日。"""
    year = base.year + years
    day = min(base.day, calendar.monthrange(year, base.month)[1])
    return date(year, base.month, day)
'''),
    ("caption", "▲ todo_db.py · 重复规则里「每月 / 每年」的推进逻辑"),
    ("note", "这里的三个知识点",
     "① **`divmod(总月数, 12)`** 一次同时拿到年和月 —— "
     "把「年 + 月」压成一个线性坐标再除，比手工处理进位干净得多。\n"
     "② **`calendar.monthrange(y, m)[1]`** 拿到该月天数，免去自己写闰年判断。\n"
     "③ **`min(base.day, 月末)`** 是「收敛」而非「报错」："
     "1 月 31 日加一个月落到 2 月 28/29 日，而不是抛 ValueError。"
     "**日期推进的默认策略应该是收敛** —— 用户设了「每月 31 日」，"
     "到 2 月时他期待的是「2 月最后一天」，不是一个报错。"),
    ("h3", "套路二：格式化与解析要配对"),
    ("code", "python", '''def moment_str(value: datetime) -> str:
    """datetime → ``YYYY-MM-DD HH:MM``（提醒精确到分钟，秒没有意义）。"""
    return value.strftime("%Y-%m-%d %H:%M")


def _now() -> str:
    """当前时间的 ISO 字符串（精确到秒）。"""
    return datetime.now().isoformat(timespec="seconds")
'''),
    ("caption", "▲ todo_db.py · 项目里时间入库只走这两个函数"),
    ("table", [
        ["格式码", "含义", "易错点"],
        ["`%Y-%m-%d`", "2026-09-21", "大写的 `%Y` 是四位年"],
        ["`%H:%M`", "14:05", "24 小时制用大写 `%H`；`%I` 是 12 小时制"],
        ["`%S`", "秒", ""],
        ["`%f`", "微秒", "6 位"],
        ["`%j`", "一年中的第几天", ""],
        ["`%a` / `%A`", "星期缩写 / 全称", "**受系统语言影响**，别用来判断星期"],
    ]),
    ("warn", "中文 Windows 上 `%a` 出来是中文星期",
     "`strftime(\"%a\")` 依赖系统 locale，在中文系统上可能是「周一」。"
     "要判断星期几一律用 **`date.weekday()`（0 = 周一）** 或 **`isoweekday()`（1 = 周一）**，"
     "不要解析格式化的字符串。本项目判断「是不是周末」用的就是数值。"),
    ("h3", "套路三：比较与差值"),
    ("code", "python", '''    now = now or datetime.now()
    base = alert_moment(item) or now
    nxt = max(base, now) + timedelta(minutes=max(1, minutes))
'''),
    ("caption", "▲ todo_db.py · snooze()：`max(datetime, datetime)` 也是一行"),
    ("p", "`datetime` 支持比较、支持加减 `timedelta`，所以「两个时间取较晚的那个」"
          "直接用内建 `max` 就行，不需要写 if。"),
    ("warn", "`datetime.now()` 是「本机时间」，没有时区信息",
     "它返回的是 naive datetime（`tzinfo` 为 None），含义是「这台机器认为的本地时间」。"
     "本项目是**单机自用工具**，所有时间都取自本机、也只在本机比较，"
     "所以 naive 时间没有问题。\n"
     "但只要出现「跨机器同步」「服务器时间」「夏令时」任何一项，"
     "就必须换成 **`datetime.now(timezone.utc)`** 存 UTC、"
     "展示时再 `astimezone()` 到本地 —— 否则一定会在某个时刻错一小时。"),

    ("h2", "11.3 json：结构化数据的通用交换格式"),
    ("code", "python", '''@classmethod
def from_row(cls, row: sqlite3.Row) -> "TodoItem":
    raw = row["tags"]
    if isinstance(raw, str):
        try:
            tags = json.loads(raw)
        except Exception:
            tags = [t.strip() for t in raw.split(",") if t.strip()]
    elif isinstance(raw, list):
        tags = raw
    else:
        tags = []
'''),
    ("caption", "▲ todo_db.py · 从数据库读 JSON 列，带三级降级"),
    ("p", "这段是本项目里「**宽容解析**」的范本：先按 JSON 解；解不出来就退化成"
          "逗号分隔的纯文本；连类型都不对（既不是字符串也不是列表）就当空。"
          "**老旧数据、手工改过的数据都能读进来**，不会因为一行脏数据让整个列表加载失败。"),
    ("table", [
        ["函数", "用途"],
        ["`json.dumps(obj, ensure_ascii=False, indent=2)`", "转字符串；**中文要 `ensure_ascii=False`**"],
        ["`json.loads(text)`", "解析字符串"],
        ["`json.dump(obj, f)` / `json.load(f)`", "直接读写文件对象"],
        ["`json.dumps(obj, sort_keys=True)`", "键排序，便于人工对比文件"],
    ]),
    ("warn", "`ensure_ascii=True` 是默认值，中文会变成 \\uXXXX",
     "写配置文件时如果忘了 `ensure_ascii=False`，文件里会是一串 `\\u5f85\\u529e`。"
     "程序读起来没问题，但**人打开来看不懂** —— 而配置文件恰恰是给人改的。"),
    ("p", "读 JSON 文件时有个固定套路：**先判文件存在、再包 try**，缺文件不该是错误："),
    ("code", "python", '''def load_app_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("状态文件读取失败（%s），按空白处理", exc)
        return {}
'''),
    ("caption", "▲ 由本手册编写；项目里 login_memory.json 的读取就是同一形状"),

    ("h2", "11.4 sqlite3：本项目唯一的持久化方案"),
    ("p", "选择 SQLite 的理由很直接：**单文件、零配置、免安装**。"
          "对一个要给别人拷过去就能跑的桌面程序来说，这是唯一合理的选项。"),
    ("h3", "连接与三个必设项"),
    ("code", "python", '''    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
'''),
    ("caption", "▲ todo_db.py · 这三行是全项目数据层的统一开头"),
    ("table", [
        ["设置", "为什么必须写"],
        ["`row_factory = sqlite3.Row`", "不设的话查询结果是普通元组，只能按**下标**取值。"
                                        "设了之后可以 `row[\"name\"]` —— **加一列不会让所有取值错位**"],
        ["`PRAGMA foreign_keys = ON`", "SQLite **默认不检查外键**（这是历史包袱），必须每个连接显式打开"],
        ["`check_same_thread=False`", "允许连接跨线程使用。本项目定时器与子线程都会读库"],
    ]),
    ("h3", "查询：参数化、避免 SQL 注入"),
    ("code", "python", '''        rows = self.conn.execute(
            "SELECT * FROM todo_holidays WHERE day LIKE ? ORDER BY day ASC",
            (f"{year:04d}-%",),
        ).fetchall()
        return [Holiday.from_row(r) for r in rows]
'''),
    ("caption", "▲ todo_db.py · 问号占位符 + 参数元组"),
    ("ok", "永远不要用 f-string 拼 SQL",
     "`conn.execute(f\"... WHERE name = '{name}'\")` 是**注入漏洞**，"
     "而且遇到名字里带单引号（比如「O'Brien」）会直接语法错误。\n"
     "正确做法就是问号占位符：**SQL 语句是固定的，数据单独作为第二个参数传**。"
     "SQLite 驱动会自己做转义。命名占位符两种写法都支持："
     "`?` 配元组、`:name` 配字典。"),
    ("h3", "批量操作：executemany"),
    ("code", "python", '''    def mark_alerted(self, moments: dict[int, str]):
        """把「这一轮已经响过」记回条目（键为条目 id，值为提醒时刻原文）。"""
        if not moments:
            return
        now = _now()
        self.conn.executemany(
            "UPDATE todo_items SET alerted_for = ?, updated_at = ? WHERE id = ?",
            [(text, now, item_id) for item_id, text in moments.items()],
        )
        self.conn.commit()
'''),
    ("caption", "▲ todo_db.py · executemany + 列表推导构造参数"),
    ("p", "`executemany` 接受「一个 SQL + 一批参数」，比循环调用 `execute` 快得多"
          "（少了每轮的语句准备开销）。注意这里**只 commit 一次**，"
          "而不是每条 commit —— 后者会让 SQLite 做 N 次磁盘刷写。"),
    ("h3", "建表：IF NOT EXISTS + executescript"),
    ("code", "python", '''    def create_tables(self):
        """建表（IF NOT EXISTS，重复调用安全）。"""
        self.conn.executescript("""
            /* 清单：颜色 + 图标，是「用不同颜色区分」的载体 */
            CREATE TABLE IF NOT EXISTS todo_lists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                color       TEXT    NOT NULL DEFAULT '#007AFF',
                icon        TEXT    NOT NULL DEFAULT 'list',
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_todo_items_list
                ON todo_items (list_id, completed, due_date);
        """)
        self.conn.commit()
'''),
    ("caption", "▲ todo_db.py · 略作节选"),
    ("note", "`IF NOT EXISTS` 让建表变成幂等操作",
     "`__init__` 里直接调 `create_tables()`，不需要先判断「数据库是新的还是老的」。"
     "这同样是**幂等**思想：把「首次运行」和「再次运行」写成同一条路径，"
     "就不会出现「第二次启动报错」这类只在特定顺序下出现的问题。"),
    ("h3", "数据库迁移：SQLite 没有 ADD COLUMN IF NOT EXISTS"),
    ("code", "python", '''    existing = {
        row["name"]
        for row in self.conn.execute("PRAGMA table_info(todo_items)").fetchall()
    }
    for column, ddl in (
        ("alerted_for", "ALTER TABLE todo_items ADD COLUMN "
                        "alerted_for TEXT NOT NULL DEFAULT ''"),
        ("snooze_until", "ALTER TABLE todo_items ADD COLUMN "
                         "snooze_until TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in existing:
            self.conn.execute(ddl)
    self.conn.commit()
'''),
    ("caption", "▲ todo_db.py · 加字段的标准姿势：先查后补"),
    ("ok", "迁移的两条纪律",
     "① **新字段必须有默认值**（`NOT NULL DEFAULT ''`）—— 否则老数据那些行就没有合法值。\n"
     "② **加列永远只做加法**：不改名、不删列、不改类型。SQLite 的 `ALTER TABLE` "
     "能力很弱（只支持 ADD COLUMN 和 RENAME），要改结构就得「建新表 + 拷数据 + 换名」，"
     "那是另一个量级的风险。**所以设计表时多留一个空列的成本，远低于事后改结构。**"),
    ("h3", "排序：多级 ORDER BY"),
    ("code", "python", '''            "SELECT * FROM todo_lists ORDER BY sort_order ASC, id ASC"
'''),
    ("caption", "▲ todo_db.py · fetch_lists()"),
    ("p", "第二级 `id ASC` 是**稳定排序**的保证：`sort_order` 相同的两条按 id 排，"
          "结果不会随数据库内部顺序变化。没有它，用户会看到「顺序偶尔自己变」。"
          "这与 4.6 节里 Python 侧「用下标做第二排序键」是同一个道理。"),
    ("h3", "事务与 commit"),
    ("table", [
        ["对象", "作用"],
        ["`conn.commit()`", "提交当前事务，落盘"],
        ["`conn.rollback()`", "回滚未提交的改动"],
        ["`with conn:`", "进入时开事务，正常退出自动 commit、异常自动 rollback"],
        ["`conn.execute` 直接改数据", "SQLite 驱动会**隐式开启**事务，等你 commit"],
        ["`conn.close()`", "关闭连接；未提交的改动会丢"],
    ]),
    ("warn", "本项目手工 commit 而不依赖 `with conn:`",
     "因为待办模块的连接是跨页面共享的长连接，用 `with conn:` 会频繁开关事务，"
     "而界面操作往往是「读一下、改一下、再读一下」的连续动作，"
     "中间开事务反而容易撞上锁。\n"
     "项目的做法是：**每个写方法自己以 `self.conn.commit()` 收尾**，"
     "读方法完全不碰事务。这样「一次界面操作 = 一次 commit」，语义清楚。"),
    ("h3", "取行数据的几种方式"),
    ("table", [
        ["写法", "结果", "取不到时"],
        ["`fetchall()`", "全部行组成的列表", "空列表"],
        ["`fetchone()`", "第一行", "**None**"],
        ["`fetchmany(n)`", "最多 n 行", "可能是短列表"],
        ["`row[\"列名\"]`", "按列名取值（需设 row_factory）", "KeyError"],
        ["`row.keys()`", "列名列表", "—"],
        ["`conn.total_changes`", "本连接累计改动行数", "—"],
        ["`cursor.lastrowid`", "刚插入行的 id", "—"],
    ]),
    ("code", "python", '''        cur = self.conn.execute(
            "INSERT INTO todo_items (list_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (list_id, title, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)
'''),
    ("caption", "▲ 插入之后拿回新 id 的写法"),

    ("h2", "11.5 logging：一份日志基建的最小正确实现"),
    ("code", "python", '''def setup_logging(log_dir=None, level=None, *, console=None,
                  filename=LOG_FILENAME):
    """配置 root logger，重复调用幂等。返回 root logger。"""
    global _configured
    root = logging.getLogger()
    if _configured:
        return root

    resolved = _resolve_level(level)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    handlers = []

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
                sys.stderr.write(f"[log_setup] 日志文件不可用（{exc}），仅输出到控制台\\n")
            except Exception:
                pass
'''),
    ("caption", "▲ log_setup.py · 节选"),
    ("table", [
        ["要点", "做法"],
        ["**配 root logger**", "入口调一次，之后任意模块 `getLogger(__name__)` 自动生效"],
        ["**幂等**", "`_configured` 标志，重复调用直接返回，不会重复挂 handler"],
        ["**必须挂文件 handler**", "打包版 `console=False`，`sys.stderr` 是 None，只挂控制台等于日志全丢"],
        ["**轮转**", "`RotatingFileHandler(maxBytes=1MB, backupCount=3)`，不会把磁盘写满"],
        ["**编码**", "`encoding=\"utf-8\"`，中文日志在 Windows 上才不会乱码"],
        ["**失败只降级**", "日志基建不该成为程序起不来的原因"],
    ]),
    ("warn", "控制台 handler 要「先探测再挂」",
     "打包成窗口程序后 `sys.stderr` 是 **None**。此时若照旧挂 "
     "`StreamHandler(sys.stderr)`，Python 的 logging 每次 `emit` 都会抛 "
     "`AttributeError: 'NoneType' object has no attribute 'write'` ——"
     "然后**被 logging 自己吞掉**。表面平静，实际一条日志都没落。\n"
     "项目的做法是写一个 `_console_stream()`：探测 `sys.stderr is None` 就返回 None，"
     "顺便试写一次确认可用，再去挂 handler。"),
    ("code", "python", '''logger = logging.getLogger(__name__)      # 每个模块顶部一行，不需要任何配置

# 记录异常：自动带上堆栈
try:
    risky()
except Exception:
    logger.exception("待办到点提醒巡检失败")

# 记录普通信息：用 %s 占位符，不要提前拼字符串
logger.debug("日志已初始化：级别=%s，处理器=%d 个", level, len(handlers))
'''),
    ("caption", "▲ 模块内的用法"),
    ("note", "`logger.info(\"...\" + str(x))` 与 `logger.info(\"...%s\", x)` 的区别",
     "后者**只有真的要输出时才会做字符串格式化**。日志级别是 INFO 时，"
     "一条 DEBUG 级别的格式化完全不会执行 —— 在高频路径上这是实打实的性能差别。\n"
     "项目里因此全用 `%s` 占位符形式，没有一处提前拼字符串。"),
    ("note", "`logger.exception` 只能用在自己没被处理过的异常分支里",
     "它内部调 `sys.exc_info()`，**必须处在 except 块中**才有堆栈可打。"
     "在 except 块外调用它，只是记一条 ERROR 而没有堆栈 —— "
     "看起来一样，但排查时才发现少了最关键的信息。"),

    ("h2", "11.6 re：正则的四个实用要点"),
    ("code", "python", '''_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\\*\\*([^*]+)\\*\\*")

for m in PATTERN.finditer(text):
    spans.append((m.start(), m.end(), m.group(1)))
'''),
    ("caption", "▲ 本手册生成器里的用法；项目里 markdown_view.py 同形"),
    ("table", [
        ["要点", "说明"],
        ["**先编译**", "`re.compile()` 一次，循环里复用；`re` 内部虽有缓存，显式更明确"],
        ["**用 `finditer` 而不是 `findall`**", "`finditer` 给的是 Match 对象，能拿到 `start()` / `end()` / 分组"],
        ["**用 `re.escape()` 转义字面量**", "搜用户输入或文件名时必做，否则 `(` `*` 会被当语法"],
        ["**原始字符串**", "正则一律写 `r\"...\"`，否则反斜杠要先过 Python 一层"],
    ]),
    ("warn", "多分组正则 + `findall` 会得到元组列表",
     "`re.findall(r\"(\\r\\n|\\n)\", text)` 返回的是**元组列表**而不是字符串列表，"
     "于是 `hits[0]` 拿到的是 `('\\n',)`。本项目在写字节补丁脚本时踩过一次。\n"
     "**要精确控制就一律用 `finditer`**：`for m in re.finditer(pat, text)`，"
     "然后 `m.group(0)` 取整体、`m.group(1)` 取第一个分组，"
     "还能用 `m.start()` / `m.end()` 定位。"),
    ("p", "另一个与字节打交道时的常见错误：**在字节串上做正则时，模式也要是字节串**。"
          "项目里查文件里有没有三引号的脚本就是把模式和 `re.escape()` 都编码成 bytes："),
    ("code", "python", '''for m in re.finditer(re.escape(b'\\"\\"\\"'), raw):
    ...
'''),
    ("caption", "▲ 在 `bytes` 上做正则，模式和输入都必须是 `bytes`"),

    ("h2", "11.7 其它常用模块"),
    ("table", [
        ["模块", "用途", "项目里的例子"],
        ["`os`", "环境变量、路径", "`os.environ.get(ENV_LEVEL, \"\")` 覆盖日志级别"],
        ["`sys`", "解释器相关", "`sys.frozen` 判打包、`sys.path` 加搜索路径"],
        ["`subprocess`", "启动外部程序", "工具包启动 exe、`explorer` 打开目录"],
        ["`shutil`", "文件复制删除", "导入图片时复制到数据目录"],
        ["`webbrowser`", "打开浏览器", "点链接打开文档"],
        ["`zipfile`", "压缩包", "读 Excel（xlsx 本质是 zip）"],
        ["`hashlib`", "摘要", "密码哈希 `hashlib.sha256(...).hexdigest()`"],
        ["`calendar`", "日历计算", "`calendar.monthrange()` 取月末"],
        ["`time`", "计时", "`time.perf_counter()` 测耗时"],
        ["`ctypes`", "调 Windows API", "单实例互斥、`PrintWindow` 截图"],
    ]),
    ("code", "python", '''def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()
'''),
    ("caption", "▲ main.py · 密码哈希（自用工具的强度取舍，见下方说明）"),
    ("warn", "SHA-256 直接哈希密码，在生产环境是不够的",
     "没有加盐、没有慢哈希，**字典攻击很容易**。本项目是单机自用工具、"
     "只防「别人翻开数据库文件能看到明文」，这个强度按需求是够的。\n"
     "真要正经存密码，用 **`hashlib.scrypt`** 或 **`bcrypt`**，"
     "它们把每一条密码的哈希成本抬到几十毫秒，暴力破解就不可行了。"
     "**这一段的价值不在代码，而在「知道自己选的是什么强度」。**"),
    ("code", "python", '''result = subprocess.run(
    [str(exe_path), "--version"],
    capture_output=True, text=True, timeout=15,
    creationflags=subprocess.CREATE_NO_WINDOW,     # 不弹黑框
)
if result.returncode == 0:
    version = result.stdout.strip()
'''),
    ("caption", "▲ 运行外部命令并取输出（参数用列表形式，不要拼成一个字符串）"),
    ("ok", "`subprocess` 的三条纪律",
     "① **参数用列表**：`[\"powershell.exe\", \"-Command\", cmd]`。"
     "用 `shell=True` 加拼字符串等于把命令行注入的口子开着。\n"
     "② **一定要 `timeout`**：外部程序卡住会连带界面卡死。\n"
     "③ **Windows 上给 `CREATE_NO_WINDOW`**：否则每跑一次都会闪一个黑框，"
     "对一个 GUI 程序来说非常难看。"),
    ("pagebreak",),

    # =========================================================================
    # 第十二章
    # =========================================================================
    ("h1", "第十二章 GUI 相关的 Python 语法"),
    ("p", "这一章不讲界面设计（那是另一个话题），只讲**用 Python 写 Tkinter 时会用到的"
          "语言特性**：回调、闭包、定时器、事件、变量类，以及控件生命周期带来的"
          "那几个专属异常。"),

    ("h2", "12.1 界面为什么用类组织"),
    ("code", "python", '''class TodoPage(ttk.Frame):
    def __init__(self, master, db=None, *, on_status=None):
        super().__init__(master)
        self.db = db
        self.current_list_id = 0
        self._list_rows = {}

        self._build()
        self.refresh_all()
'''),
    ("caption", "▲ todo_page.py · 页面类的构造骨架"),
    ("p", "用类的理由有两条，都很实际："),
    ("ol", [
        "**状态要有地方放**。`self.current_list_id`（当前选中的清单）、"
        "`self._list_rows`（行控件索引）必须活到下一次交互 —— "
        "装在函数局部变量里，函数一返回就没了。",
        "**回调要能找回来**。按钮的 `command=self.on_click` 是一个绑定方法，"
        "它自带 `self`，所以点下去时能拿到这套状态。用纯函数就得靠全局变量。",
    ]),
    ("note", "为什么页面继承 `ttk.Frame` 而不是 `object`",
     "`ttk.Frame` 本身就是一个容器控件。继承它之后，`TodoPage` 实例**可以直接 "
     "`pack()` / `grid()` 到父容器里**，就和一个普通 Frame 一样用："
     "`self.todo_view = TodoPage(container, db); self.todo_view.pack(fill=\"both\")`。\n"
     "如果继承 `object`，就得自己再持有一个 Frame 并把它暴露出去，多一层转发。"),
    ("p", "注意构造签名里的 `db=None`：**数据层是「注入」进来的，不是页面自己 new 的**。"
          "这是 7.8 节「组合」的直接收益 —— 测试时塞一个替身进去就行，"
          "不需要真数据库。"),

    ("h2", "12.2 回调：传函数对象，不传调用结果"),
    ("code", "python", '''        dialog = TodoAlertDialog(
            self, items, db=self.todo_db,
            on_changed=self._after_todo_alert,     # 传函数对象，不加括号
            on_open=self._open_todo_item,
        )
'''),
    ("caption", "▲ main.py · 三个回调全是具名方法名"),
    ("table", [
        ["正确", "错误", "错误的结果"],
        ["`command=self.save`", "`command=self.save()`", "**绑定时就执行一次**，回调变成 `None`"],
        ["`bind(\"<Enter>\", self._on_enter)`", "`bind(\"<Enter>\", self._on_enter())`", "同上"],
        ["`command=lambda: self.save(1)`", "`command=lambda x: self.save(1)`", "参数对不上，点击时报错"],
        ["`bind(\"<Enter>\", lambda e: f(e))`", "`bind(\"<Enter>\", lambda: f(e))`", "Tkinter 会传事件参数，参数个数不符"],
    ]),
    ("note", "`bind` 的回调**一定会收到一个事件对象**",
     "`widget.bind(\"<Enter>\", handler)` 里的 `handler` 会被 Tkinter 调用成 "
     "`handler(event)`。所以回调签名必须能收下一个参数 —— "
     "这就是为什么项目里到处是 `lambda e: self.set_hover(True)` 里的那个 `e`。\n"
     "如果用的是具名方法（`self._invoke`），它的签名就得是 `def _invoke(self, event=None)`。"
     "**写成 `def _invoke(self)` 也能跑 `command=`，但接 `bind` 就会 TypeError** —— "
     "所以项目里统一给事件处理方法加 `event=None`。"),
    ("code", "python", '''        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))
        if command is not None:
            self.bind("<Button-1>", self._invoke)
'''),
    ("caption", "▲ ui_components.py · 两种回调用法并存"),

    ("h2", "12.3 after：Tkinter 的定时器"),
    ("code", "python", '''TODO_TICK_MS = 30 * 1000          # 30 秒

    def todo_alert_check(self):
        """巡检一次「有没有提醒该响了」。

        自己续期，所以只要程序在跑就一直有效 —— 窗口缩到托盘也一样
        （mainloop 还活着），人不在电脑前也不会漏掉。
        """
        if getattr(self, "_exiting", False):
            return
        try:
            self._run_todo_alerts()
        except Exception:
            logger.exception("待办到点提醒巡检失败")
        finally:
            self.after(TODO_TICK_MS, self.todo_alert_check)
'''),
    ("caption", "▲ main.py · 自续期定时器"),
    ("image", "build/release/todo_alert_window.png", 0.62),
    ("caption", "▲ 就是上面那个 30 秒定时器弹出来的东西：屏幕右下角的到点提醒窗。"
                "`-topmost` 压过别的窗口，但**不 `grab_set`**，"
                "所以不会把正在打字的人从输入框里拽出来。"),
    ("table", [
        ["方法", "作用"],
        ["`widget.after(ms, func)`", "延迟 ms 毫秒调用一次"],
        ["`widget.after(ms, func, *args)`", "带参数调用"],
        ["`widget.after_idle(func)`", "界面空闲时调用"],
        ["`handle = widget.after(...)`", "返回句柄，可以取消"],
        ["`widget.after_cancel(handle)`", "取消（**退出前必须做**，否则回调会打到已销毁的控件上）"],
        ["`widget.after_cancel(\"all\")`", "取消该控件上全部定时任务"],
        ["`widget.update()` / `update_idletasks()`", "强制立刻处理一次事件队列（截图、测试时用）"],
    ]),
    ("ok", "自续期定时器的三条纪律",
     "① **续期必须放 `finally`** —— 否则一次异常就让定时器永久死掉（见 8.1）。\n"
     "② **退出前要停** —— 项目里用 `self._exiting` 标志：退出流程一开始就置位，"
     "下一轮巡检看到标志直接 return，不会再去碰正在销毁的控件。\n"
     "③ **回调出错要有人接住** —— Tkinter 的事件循环里抛出的异常**不会让程序退出**，"
     "只会打到 stderr（打包版等于吞掉）。所以回调里必须自己 `try/except` + 记日志。"),
    ("warn", "为什么不用 `threading.Timer` 或独立线程",
     "**Tkinter 不是线程安全的**：只有创建控件的那一个线程能碰控件。"
     "从子线程里调 `widget.config(...)` 可能看起来正常、也可能在几分钟后随机崩掉 ——"
     "这类 bug 极难复现。\n"
     "`after()` 跑在主线程的事件循环里，天然没有这个问题。"
     "**要在界面程序里做定时任务，就用 `after`。**"),

    ("h2", "12.4 事件绑定与事件对象"),
    ("table", [
        ["事件", "触发"],
        ["`<Button-1>` / `<ButtonRelease-1>`", "鼠标左键按下 / 松开"],
        ["`<B1-Motion>`", "按住左键拖动"],
        ["`<Double-Button-1>`", "双击"],
        ["`<Enter>` / `<Leave>`", "鼠标进入 / 离开控件"],
        ["`<KeyRelease>`", "按下一个键"],
        ["`<Return>`", "回车"],
        ["`<FocusOut>`", "失去焦点（表单自动保存常绑它）"],
        ["`<Configure>`", "控件尺寸变化"],
        ["`<<ComboboxSelected>>`", "虚拟事件（ttk 特有），注意是**双尖括号**"],
    ]),
    ("code", "python", '''class _DragEvent:
    """拖动回调用得到的字段就这两个；自己造一个替身，测试时就不需要真鼠标。"""

    def __init__(self, y_root: int):
        self.y_root = y_root


page._list_drag_press(ids[0], _DragEvent(base + mid(0)))
page._list_drag_motion(ids[0], _DragEvent(base + mid(2)))
page._list_drag_release(ids[0], _DragEvent(base + mid(2)))
'''),
    ("caption", "▲ scripts/test_todo_ui.py · 用替身对象模拟事件"),
    ("p", "这段是**测试写法**上的一个要点：拖动处理只用到事件对象上的 `y_root` 一个字段，"
          "那么测试就不必真的造鼠标事件，**传一个只有该字段的小对象即可**。"
          "这叫「鸭子类型」的实用面 —— **不要求参数是某个类，只要求它有那个属性**。"
          "结果是拖动的回归测试完全不需要真实鼠标操作，跑起来稳定又快。"),
    ("note", "事件对象上常用的字段",
     "`event.x` / `event.y` 是**相对控件左上角**的坐标；`event.x_root` / `event.y_root` "
     "是**相对屏幕**的坐标；`event.widget` 是触发事件的控件；"
     "`event.keysym` 是按键名（如 `\"Return\"`）；`event.width` / `event.height` "
     "在 `<Configure>` 里给出新尺寸。\n"
     "**拖动计算要用 `y_root`**（屏幕坐标），因为它不受「被拖动的行自己在移动」影响；"
     "用 `event.y` 会在行移动之后跟着漂。"),

    ("h2", "12.5 变量类：StringVar / IntVar / BooleanVar"),
    ("code", "python", '''        self.keyword_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.keyword_var)
        entry.bind("<KeyRelease>", lambda e: self._on_search())
        ...
    def _on_search(self):
        keyword = self.keyword_var.get().strip()
'''),
    ("caption", "▲ todo_page.py · 搜索框的两种用法并存"),
    ("table", [
        ["写法", "取值", "适用"],
        ["`textvariable=var`", "`var.get()` / `var.set(x)`", "需要程序主动改控件内容时"],
        ["直接 `entry.get()`", "从控件读", "只读用户输入时更简单"],
        ["字符串", "`tk.StringVar()`", "文本"],
        ["整数", "`tk.IntVar()`", "复选框、计数器"],
        ["布尔", "`tk.BooleanVar()`", "`Checkbutton`"],
        ["双击", "`tk.DoubleVar()`", "滑块数值"],
    ]),
    ("note", "变量类是「双向绑定」的实现方式",
     "`textvariable=` 之后，**改 `var` 会立刻改控件，改控件也会立刻改 `var`**。"
     "本项目只在「需要程序回写控件」的地方用它（比如搜索框要能被清空）。"
     "纯读取输入的场景直接 `entry.get()` 更省事 —— 少一个需要维护的对象。\n"
     "一个易错点：`IntVar` 在输入框为空或非数字时 `get()` 会**抛 TclError**，"
     "因为 Tk 存的是字符串、转 int 失败。所以读数字一律要包一层兜底。"),

    ("h2", "12.6 控件生命周期与 TclError"),
    ("code", "python", '''    key = tuple(base)
    cached = _STRIKE_FONTS.get(key)
    if cached is not None:
        try:
            cached.actual()             # 探一次活：解释器换过之后旧对象就是废的
            return cached
        except tk.TclError:
            _STRIKE_FONTS.pop(key, None)
'''),
    ("caption", "▲ todo_page.py · strike_font() 的缓存探活"),
    ("warn", "控件被销毁之后，任何 `cget` / `config` 都会抛 TclError",
     "报错长得像 `TclError: invalid command name \".!todopage.!frame.!label3\"`。"
     "触发场景很多：**定时器回调打在已关闭的窗口上**、"
     "**在 Tk 解释器销毁后复用缓存的 `Font` 对象**、"
     "**跨测试用例复用了上一个 `Tk()` 根窗口的控件**。\n"
     "应对方式有两种，项目里都用了：\n"
     "① **先判存在**：`if widget.winfo_exists(): widget.destroy()`；\n"
     "② **探活后再用**：像上面这样先调一个无害方法，抛 `TclError` 就说明对象已废，"
     "清掉缓存重建。\n"
     "**永远不要缓存 Tk 对象而不做存活检查** —— 本项目的字体缓存就是这么修的。"),
    ("code", "python", '''    def _close_todo_alert(self):
        """关掉还挂着的提醒窗（开会错过的那一批不应一直压在最上层）。"""
        dialog = getattr(self, "_todo_alert_win", None)
        self._todo_alert_win = None            # 先置空：让本方法可重复调用
        if dialog is None:
            return
        try:
            if dialog.winfo_exists():
                dialog.destroy()
        except Exception:
            pass
'''),
    ("caption", "▲ main.py · 关闭窗口的标准姿势：先置空引用、再判存在、最后包 try"),
    ("h3", "winfo 系列：询问控件的实际状态"),
    ("table", [
        ["方法", "返回"],
        ["`winfo_exists()`", "控件是否还活着"],
        ["`winfo_width()` / `winfo_height()`", "当前实际尺寸（**布局算完之后才是真实值**）"],
        ["`winfo_reqwidth()` / `winfo_reqheight()`", "控件自己请求的尺寸"],
        ["`winfo_x()` / `winfo_y()`", "**相对父容器**的左上角坐标"],
        ["`winfo_rootx()` / `winfo_rooty()`", "相对屏幕的坐标"],
        ["`winfo_children()`", "子控件列表"],
        ["`winfo_screenwidth()` / `winfo_screenheight()`", "屏幕尺寸"],
        ["`winfo_ismapped()`", "是否真的被显示出来了"],
    ]),
    ("warn", "`winfo_width()` 在布局计算前返回的是 1（不是错，是还没算）",
     "刚 `pack()` 完立刻问尺寸，拿到的往往是 `1`。必须等 Tk 处理过一次事件队列，"
     "也就是调用 `update_idletasks()` 或 `update()` 之后才有真实值。\n"
     "**测试里所有「量尺寸」的断言前面都必须先 `update()`**，"
     "否则断言的是「还没布局」而不是「布局结果」。\n"
     "另外 `winfo_ismapped()` 有个特别之处：**主窗口 `withdraw()` 时，所有控件都返回 0**。"
     "所以拿它判断「控件有没有被饿死」之前，必须先 `deiconify()`。"),

    ("h2", "12.7 一个跨语言的坑：Tk 会「饿死」控件"),
    ("code", "python", '''        self.vsb = ttk.Scrollbar(self, orient="vertical")
        self.vsb.pack(side="right", fill="y")           # 先 pack 滚动条

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0,
                                yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)   # 后 pack 画布
'''),
    ("caption", "▲ todo_page.py · ScrollArea 里 pack 的顺序"),
    ("warn", "这个坑不属于 Python 语法，但每次都让人以为是语法问题",
     "`pack` 是**按调用顺序分配剩余空间**的。如果先 pack 一个 "
     "`fill=\"both\", expand=True` 的控件，它会把空间全部吃掉，"
     "后面 pack 的固定尺寸控件只分到 **0 像素**，"
     "于是 Tk **根本不映射它** —— 代码明明写了，界面上就是不存在。\n"
     "这不是「被裁掉一点」，而是**完全不存在**。判定口径是："
     "`winfo_manager()` 非空 **且** `winfo_ismapped() == 0`。\n"
     "**规矩：先 pack 固定尺寸的控件，最后 pack 那个 `expand=True` 的内容区；"
     "滚动条要先于它管理的滚动区域。**"),
    ("ok", "本章小结：GUI 里最该记住的四条",
     "① 回调传**函数对象**（`self.save`），不传调用结果（`self.save()`）；\n"
     "② 定时任务用 **`after`** + `finally` 续期 + 退出标志，不要用线程；\n"
     "③ 任何缓存的 Tk 对象在用之前都要**探活**，控件销毁后一律 `TclError`；\n"
     "④ 别在**模块顶层**建窗口或控件 —— 那会让 `import` 有副作用，测试也没法隔离。"),
    ("pagebreak",),

    # =========================================================================
    # 第十三章
    # =========================================================================
    ("h1", "第十三章 工程约定与陷阱"),
    ("p", "这一章是那些**不属于任何单一语法点、但每个真实项目都会撞上**的东西。"
          "它们大多与「Python 在 Windows 上 + 中文 + 打包发布」这个组合有关。"),

    ("h2", "13.1 行尾：CRLF 与 LF"),
    ("table", [
        ["场景", "行尾", "说明"],
        ["Windows 上的多数编辑器", "CRLF（`\\r\\n`）", "本项目应用源码就是这种"],
        ["Git Bash / 跨平台工具", "LF（`\\n`）", "本项目 `scripts/*.py` 与 `*.md` 是这种"],
        ["Python 文本模式读取", "**统一翻译成 `\\n`**", "`universal newlines`，看不见 CRLF"],
        ["Python 文本模式写入", "`\\n` 被翻译成**平台默认**", "Windows 上就是 CRLF —— 这是 `write_text` 的陷阱"],
        ["Python 二进制模式", "**原样进出**", "字节级补丁必须走这条"],
    ]),
    ("p", "关键点是第二行与第四行：**Python 的文本模式会让行尾「看起来统一」**，"
          "所以你在代码里从没感觉到 CRLF 的存在；但**写回磁盘时它又会按平台转换**，"
          "于是「读出来再写回去」这个动作本身就会改文件。"),
    ("warn", "`Path.write_text` 在 Windows 上会把整个文件变成 CRLF",
     "本项目实际踩过：一个纯 LF 的测试脚本用 `write_text` 写回之后，"
     "946 行全部变成 CRLF，`git diff` 显示「946 增 / 778 删」，"
     "真实的逻辑改动被淹没在里面。\n"
     "**要保住原行尾只有一条路：`read_bytes()` + `write_bytes()`**，"
     "中间需要处理文本时用 `decode(\"utf-8\")`，处理完再 `encode(\"utf-8\")`，"
     "全程不让行尾经过文本模式的翻译。"),
    ("code", "python", '''raw = p.read_bytes()                       # 字节读：CRLF 保持原样
assert raw.count(b"\\r\\n") == 0, "这个文件应该是纯 LF"      # 先确认现状
before = raw.count(b"\\n")
text = raw.decode("utf-8")                 # 现在是字符串，里面的换行是 "\\n"
text = text.replace(old, new, 1)           # 只改目标片段
out = text.encode("utf-8")                 # 字节写回：不产生任何 CRLF
assert out.count(b"\\n") == before + added  # 行数变化符合预期
p.write_bytes(out)
'''),
    ("caption", "▲ 纯 LF 文件的补丁骨架"),
    ("ok", "完整规则（本项目所有改写源码的操作都遵守）",
     "1. **先查明行尾现状**：`raw.count(b\"\\r\\n\")` 与 `raw.count(b\"\\n\")` 相等 → 纯 CRLF；"
     "后者减前者得到的就是「单独 LF」的数量。\n"
     "2. **纯 CRLF 文件**：`text.replace(\"\\n\", \"\\r\\n\")` 写回，并断言 "
     "`out.count(b\"\\r\\n\") == out.count(b\"\\n\")`。\n"
     "3. **纯 LF 文件**：**绝对不要**经过 `write_text`，只走 `write_bytes`。\n"
     "4. **混排文件（如 `main.py`）**：先记下「单独 LF」的数量（167 个），"
     "补丁锚点**带上 `\\r\\n`**，写完复核这个数量没变。\n"
     "5. 收尾一律用 `git diff --numstat` 复核变更行数 —— 数字不对说明行尾被动过。"),

    ("h2", "13.2 文本 vs 字节：什么时候必须用字节"),
    ("table", [
        ["任务", "该用的 API", "理由"],
        ["读写配置 / 日志", "`read_text` / `write_text`", "人看的文本，行尾无所谓"],
        ["改写源码文件", "**`read_bytes` / `write_bytes`**", "必须保住原行尾"],
        ["解析二进制格式", "`read_bytes`", "图片、Excel、zip"],
        ["网络 / 子进程 IO", "`bytes`", "协议是字节流"],
        ["哈希、加解密", "`bytes`", "算法定义在字节上"],
        ["写 CSV / 文本导出", "`open(..., newline=\"\")`", "**让 csv 模块自己管行尾**"],
    ]),
    ("warn", "`csv` 模块必须配 `newline=\"\"`",
     "`csv.writer` 自己会写 `\\r\\n`，而文本模式又会把 `\\n` 再翻一遍，"
     "结果是每行多一个空行。正确写法是 "
     "`open(path, \"w\", encoding=\"utf-8-sig\", newline=\"\")`。"
     "**这是 Python 官方文档特别标注的一条**。"),
    ("note", "`encoding=\"utf-8-sig\"` 是什么时候该用",
     "`utf-8-sig` 会在文件开头写 BOM（`EF BB BF`）。**Excel 打开 CSV 时**«BR»"
     "靠这个 BOM 判断编码，没有它中文会乱码。所以：**给用户用 Excel 打开的 CSV 用 "
     "`utf-8-sig`；程序自己读写的 JSON / 日志 / 源码统统用普通 `utf-8`**（加 BOM 反而会让"
     "严格的解析器报错）。\n"
     "本项目 `tools_page.py` 里的 CSV 导出就是这么分的。"),

    ("h2", "13.3 编码：统一 UTF-8，一处都不要例外"),
    ("code", "python", '''# 源码文件
# -*- coding: utf-8 -*-

# 读写文件
path.read_text(encoding="utf-8")
path.write_bytes(text.encode("utf-8"))

# 日志
RotatingFileHandler(..., encoding="utf-8")

# 子进程
subprocess.run(..., encoding="utf-8", errors="replace")

# 控制台（打包版 stderr 可能没有）
stream.reconfigure(errors="replace")
'''),
    ("caption", "▲ 项目里的编码设置集中在这几处"),
    ("table", [
        ["坑", "表现", "应对"],
        ["Windows 默认编码是 cp936", "读写文件不指定 `encoding` 时中文可能乱码或报错", "**每个 `open` 都写 `encoding=\"utf-8\"`**"],
        ["控制台打印中文", "`UnicodeEncodeError` 或显示问号", "`errors=\"replace\"` 放宽"],
        ["BOM", "JSON 解析失败、字符串开头多一个不可见字符", "程序内部一律普通 utf-8"],
        ["源码里有非法字节", "`SyntaxError: Non-UTF-8 code`", "确保编辑器保存为 UTF-8 无 BOM"],
    ]),

    ("h2", "13.4 时间：本项目明确选了「本机时间」"),
    ("table", [
        ["做法", "含义", "适用"],
        ["`datetime.now()`", "**本机**当前时间，naive", "单机自用工具（本项目）"],
        ["`datetime.utcnow()`", "UTC 时间，naive", "**已不推荐**，用下面那个"],
        ["`datetime.now(timezone.utc)`", "带时区的 UTC", "需要跨机器一致时"],
        ["`datetime.now().timestamp()`", "Unix 时间戳（秒）", "存库、跨系统比较"],
        ["`date.today()`", "本机日期", "只关心「哪一天」时"],
    ]),
    ("warn", "naive 时间的边界在哪",
     "naive datetime 的含义是「这台机器认为的本地时间」。它有三种情况会出问题：\n"
     "① **换机器**：同一份数据在另一个时区的电脑上打开，时间含义就变了；\n"
     "② **夏令时**：本地时间在切换日会出现重复或缺失的一小时；\n"
     "③ **与外部系统对时间**：服务器给的是 UTC，直接比较会差几小时。\n"
     "本项目的场景是「单机、自用、只在本地比较」，所以 naive 时间成立。"
     "**但这个结论要写下来**（就像这条注释一样），"
     "否则将来接了云同步功能，没人知道当初是「有意选的」还是「没想到」。"),

    ("h2", "13.5 数值：先把误差摆到台面上"),
    ("code", "python", """print(0.1 + 0.2)            # 0.30000000000000004
print(0.1 + 0.2 == 0.3)     # False
print(round(2.675, 2))      # 2.67  —— 不是四舍五入的错，是 2.675 本身就存不准
print(1 / 3)                # 0.3333333333333333
"""),
    ("caption", "▲ 这些结果都是「正确」的，浮点数就是这样"),
    ("table", [
        ["需求", "做法"],
        ["显示两位小数", "`f\"{v:.2f}\"`"],
        ["比较两个浮点是否相等", "`abs(a - b) < 1e-9`"],
        ["金额计算", "**用 `int` 存分**，或 `decimal.Decimal(\"0.1\")`"],
        ["只要整数结果", "`//`（向下取整）、`int()`（向零取整）、`round()`（银行家舍入）"],
        ["统计求和顺序敏感", "`math.fsum()` 精度更好"],
    ]),
    ("note", "`round()` 是「银行家舍入」，不是四舍五入",
     "`round(0.5)` 得 0、`round(1.5)` 得 2 —— 它舍入到**最近的偶数**。"
     "这是 IEEE-754 的默认策略，用来避免大量数据相加时的系统性偏差。"
     "要真正的四舍五入，用 `decimal.Decimal(...).quantize(Decimal(\"0.01\"), "
     "rounding=ROUND_HALF_UP)`。"),

    ("h2", "13.6 静态检查：pyflakes 与它的口径"),
    ("table", [
        ["工具", "查什么", "本项目"],
        ["`pyflakes`", "未使用的导入 / 变量、未定义的名字、f-string 问题", "**在用**，作为回归基线"],
        ["`ruff`", "pyflakes + pycodestyle + 很多规则，极快", "待办清单上"],
        ["`mypy` / `pyright`", "类型检查", "待办清单上"],
        ["`black`", "格式化", "未用（现有风格已统一）"],
    ]),
    ("warn", "pyflakes 的口径要限定在「有效范围」",
     "项目根目录有一批 `_` 开头的临时脚本，噪声很大，"
     "把它们算进来会让告警数虚高。本项目的有效基线只统计"
     "「**非 `_` 开头 + `embedded_admin_tools/`**」，当前是 **7 条旧账**，"
     "全是「赋值未使用」这类无关痛痒的。\n"
     "**关键不是「零告警」，而是「告警数不再增加」** —— "
     "回归时对比数字，新增一条就要查。"),
    ("note", "本项目补的两个专用检查脚本",
     "`pyflakes` 有两个盲区，项目为此写了单独的脚本：\n"
     "`check_name_scope.py` —— 查 **except 块里的名字在块外被引用**"
     "（Python 3 会在 except 结束时**删除** `except E as e` 里的 `e`）"
     "以及闭包作用域问题；\n"
     "`project_audit.py` —— 用 AST 统计函数长度、嵌套深度、重复代码。\n"
     "**pyflakes 不是全覆盖**，知道它漏什么，比用到它更重要。"),

    ("h2", "13.7 打包：Python 特有的三个认知"),
    ("out", """ExpiryManager_fixed.spec
    ├── Analysis(['main.py'])      分析依赖图，收集所有 import
    ├── PYZ                        把 .pyc 压进一个归档
    ├── EXE                        bootloader + PYZ + 数据文件
    └── （onefile 模式没有 COLLECT 目录，全部塞进单个 exe）"""),
    ("caption", "▲ PyInstaller onefile 的产物结构"),
    ("table", [
        ["认知", "后果"],
        ["**漏了模块不报错**", "只在运行版炸。所以要「反向核对」：打开 exe 归档验证符号在不在"],
        ["**`hiddenimports` 要手工补**", "动态导入（`importlib`、字符串名字）分析不到，必须列出"],
        ["**路径会变**", "`__file__` 指向临时解包目录，数据目录要用 `sys.executable` 定位"],
        ["**没有控制台**", "`console=False` 时 `sys.stderr` 是 None，日志必须落文件"],
        ["**首次启动慢**", "onefile 要先解包到临时目录，体积越大越慢"],
    ]),
    ("note", "「反向核对」怎么做",
     "打开 exe 的归档，把源码编译后的字节码取出来，检查关键函数名在不在：\n"
     "`CArchiveReader(exe)` → `open_embedded_archive(\"PYZ.pyz\")` → `extract(\"todo_db\")`，"
     "然后**递归遍历 code object 的 `co_names` / `co_consts`**（`repr(code)` 看不到函数名）。"
     "入口脚本 `main` 不在 PYZ 里，得从 CArchive 的 `main` 条目取。\n"
     "本项目把它固化成 `scripts/check_exe.py`，每次打包后跑一遍。"),
    ("warn", "打包脚本最大的危险是「删掉真实数据」",
     "很多打包脚本第一步是 `rmdir /s /q dist`，之后只把少数几个文件拷回去 ——"
     "于是**用户积累的运行期数据永久丢失**（数据库、上传的图片、登录记忆）。"
     "本项目因此不用那个脚本，改用「只备份数据库与工具目录到临时位置、"
     "**只删 exe**」的安全版本。\n"
     "**任何「清理后重建」的脚本，都要先问一句：重建得回来吗？**"),
    ("pagebreak",),

    # =========================================================================
    # 附录 A 速查卡（不占章号：小节编号本来就是 A.x）
    # =========================================================================
    ("h1", "附录 A · 语法速查卡"),
    ("p", "这份附录是一页纸级别的浓缩。适合打印出来放在手边，"
          "或者在你「明明记得有这么一个语法但想不起来怎么写」的时候翻。"),

    ("h2", "A.1 数据类型与字面量"),
    ("table", [
        ["", "字面量", "可变", "可哈希", "常用取值"],
        ["`int`", "`42`、`0x1F`、`0b1010`、`1_000_000`", "否", "是", "整数"],
        ["`float`", "`3.14`、`1e-9`", "否", "是", "小数"],
        ["`bool`", "`True` / `False`", "否", "是", "`int` 的子类"],
        ["`str`", "`'a'`、`\"a\"`、`f\"{x}\"`、`r\"\\\\d\"`", "否", "是", "文本"],
        ["`bytes`", "`b\"abc\"`", "否", "是", "字节日志、二进制"],
        ["`list`", "`[1, 2]`", "**是**", "否", "有序收集"],
        ["`tuple`", "`(1, 2)`、`1, 2`", "否", "是", "固定组合、字典键"],
        ["`dict`", "`{'a': 1}`", "**是**", "否", "键值映射（保插入序）"],
        ["`set`", "`{1, 2}`、`set()`", "**是**", "否", "去重、存在性"],
        ["`None`", "`None`", "否", "是", "「没有值」"],
        ["`frozenset`", "`frozenset({1})`", "否", "是", "不可变集合"],
    ]),
    ("h2", "A.2 字符串与容器操作"),
    ("table", [
        ["类别", "操作"],
        ["字符串", "`s.strip()` `s.split(sep)` `s.replace(a,b)` `s.startswith(p)` `s.endswith(p)` "
                  "`s.casefold()` `s.zfill(2)` `s.join(seq)` `s in t` `s[1:5]` `s[::-1]`"],
        ["列表", "`append` `extend` `insert` `remove` `pop` `clear` `index` `count` `sort` `reverse` `copy`"],
        ["字典", "`d.get(k, dflt)` `d.setdefault(k, v)` `d.update(o)` `d.pop(k, dflt)` "
                "`d.keys()` `d.values()` `d.items()` `d1 | d2`"],
        ["集合", "`add` `discard` `remove` `union` `intersection` `difference` `issubset`"],
        ["通用", "`len(x)` `x in c` `max/min(c)` `sum(c)` `sorted(c)` `reversed(c)` `enumerate(c)` "
                "`zip(a, b)` `any(c)` `all(c)` `list(c)` `tuple(c)` `set(c)` `dict(pairs)`"],
    ]),
    ("h2", "A.3 控制流与函数"),
    ("table", [
        ["", "写法"],
        ["条件", "`if / elif / else`；三目 `a if c else b`"],
        ["循环", "`for x in c:` / `while c:`；`break` / `continue` / `pass`；`for ... else:`"],
        ["异常", "`try / except E / else / finally`；`raise E(...)` / `raise ... from e`"],
        ["函数定义", "`def f(a, b=1, *args, c, **kw) -> T:`"],
        ["仅关键字", "`def f(a, *, b):` —— `b` 只能用 `b=` 传"],
        ["返回多值", "`return a, b`（实为元组）"],
        ["lambda", "`lambda x: x + 1` —— 只能是一个表达式"],
        ["装饰器", "`@deco` 写在 `def` 上方；`functools.wraps` 保住元信息"],
        ["闭包", "内层函数读外层变量；写要 `nonlocal` / `global`；绑定用 `lambda i=i:`"],
    ]),
    ("h2", "A.4 类"),
    ("table", [
        ["", "写法"],
        ["定义", "`class C(Base):`"],
        ["构造", "`def __init__(self, ...):` 第一句是 `super().__init__(...)`"],
        ["实例 / 类属性", "`self.x = 1` / 类体里 `x = 1`"],
        ["计算属性", "`@property def x(self):` 用 `obj.x` 读"],
        ["备用构造", "`@classmethod def from_row(cls, row):`"],
        ["无状态工具", "`@staticmethod def helper():`"],
        ["数据类", "`@dataclass`；可变默认值用 `field(default_factory=list)`"],
        ["魔术方法", "`__init__` `__repr__` `__eq__` `__len__` `__iter__` `__enter__` `__exit__`"],
        ["继承检查", "`isinstance(x, C)` / `issubclass(D, C)` / `C.__mro__`"],
    ]),
    ("h2", "A.5 模块与导入"),
    ("table", [
        ["", "写法"],
        ["导入模块", "`import m` → `m.f()`"],
        ["导入名字", "`from m import f, g` → `f()`"],
        ["别名", "`import tkinter as tk` / `from x import y as z`"],
        ["相对导入", "`from . import x` / `from .sub import y`"],
        ["脚本守卫", "`if __name__ == \"__main__\":`"],
        ["延迟导入", "把 `import` 放进函数体（省启动时间）"],
        ["加搜索路径", "`sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`"],
        ["打包路径", "`Path(sys.executable).parent if getattr(sys, \"frozen\", False) else Path(__file__).parent`"],
    ]),
    ("h2", "A.6 常用标准库"),
    ("table", [
        ["需求", "写法"],
        ["路径", "`Path(a) / \"b\"`、`.parent` `.name` `.stem` `.suffix` `.resolve()` `.exists()`"],
        ["建目录", "`p.mkdir(parents=True, exist_ok=True)`"],
        ["读文本", "`p.read_text(encoding=\"utf-8\")`"],
        ["**保行尾写回**", "`p.write_bytes(text.encode(\"utf-8\"))`"],
        ["当前时间", "`datetime.now()` / `date.today()`"],
        ["时间格式化", "`dt.strftime(\"%Y-%m-%d %H:%M\")` → `\"2026-09-21 14:05\"`"],
        ["日期运算", "`d + timedelta(days=1)`；月末天数 `calendar.monthrange(y, m)[1]`"],
        ["JSON", "`json.dumps(o, ensure_ascii=False)` / `json.loads(s)`"],
        ["SQLite", "`sqlite3.connect(p)` + `conn.row_factory = sqlite3.Row`"],
        ["日志", "`logging.getLogger(__name__)` → `logger.exception(\"…\")`"],
        ["子进程", "`subprocess.run([...], capture_output=True, text=True, timeout=15)`"],
        ["环境变量", "`os.environ.get(\"NAME\", \"\")`"],
        ["正则", "`re.compile(r\"...\")` → `.finditer(text)` / `.search` / `.sub`"],
        ["哈希", "`hashlib.sha256(b).hexdigest()`"],
    ]),
    ("h2", "A.7 高频惯用法"),
    ("table", [
        ["目的", "写法"],
        ["计频", "`d[k] = d.get(k, 0) + 1`"],
        ["设默认不覆盖", "`d.setdefault(k, v)`"],
        ["兜底默认（小心吞掉 0）", "`x = value or DEFAULT`"],
        ["提取一列", "`[row[\"name\"] for row in rows]`"],
        ["过滤", "`[x for x in xs if 条件]`"],
        ["建索引", "`{x.id: x for x in xs}`"],
        ["去重保序", "`list(dict.fromkeys(xs))`"],
        ["多条件排序", "`sorted(xs, key=lambda x: (-x.score, x.name))`"],
        ["稳定二级排序", "`sorted(xs, key=lambda x: (x.a, x.id))`"],
        ["并列遍历", "`for a, b in zip(xs, ys):`"],
        ["带下标遍历", "`for i, x in enumerate(xs, 1):`"],
        ["交换", "`a, b = b, a`"],
        ["安全取值", "`d.get(k, \"\")` 而不是 `d[k]`"],
        ["幂等追加", "追加前先 `find` 标记，命中就跳过"],
        ["判 None", "`if x is None:`（不要用 `== None`）"],
        ["空值判真", "`if not x:` 会连 `0` / `\"\"` / `[]` 一起匹配"],
    ]),
    ("pagebreak",),

    # =========================================================================
    # 附录 B 模块清单
    # =========================================================================
    ("h1", "附录 B · 模块清单"),
    ("p", "下表是生成这份手册时对源码目录**现算**的结果，"
          "顺序按文件行数从大到小。职责取自各模块自己的 docstring 首句。"),
    ("module_table",),
    ("h2", "B.1 数据目录结构"),
    ("out", """ExpiryManager_Data/                 ← 全部运行期数据都在这一个目录里
├── expiry_manager.db               主数据库（24 张表）
├── login_memory.json               登录记忆（含密码密文）
├── logs/app.log                    轮转日志（1 MB × 3 份）
├── account_images/                 账号中心上传的图片
├── study_notes_images/             笔记图片
├── study_notes_attachments/        笔记附件
├── process_flow_images/            流程图图片
└── ...                             导出文件、历史记录等"""),
    ("caption", "▲ 目录名与迁移映射见 main.py 的 _MIGRATION_MAP"),
    ("note", "所有数据放一个目录，是给「备份」用的",
     "一个程序的数据散落在十几个地方时，「备份」就变成了需要文档的操作。"
     "收进一个目录之后，用户只需要「拷走这个文件夹」。\n"
     "配套的设计是 **`_MIGRATION_MAP` + `.migrated` 标记文件**："
     "首次启动时把散落在程序目录里的老文件搬进 `ExpiryManager_Data/` 并留下标记，"
     "之后不再执行。**迁移只做一次、且可重复检测**，"
     "这也是幂等思想的一个应用。"),
    ("h2", "B.2 测试套件与基线"),
    ("p", "项目共 11 个回归套件，下表是本次生成时的实测结果（**跑一遍现统计**）："),
    ("test_table",),
    ("pagebreak",),

    # =========================================================================
    # 附录 C 坑对照表
    # =========================================================================
    ("h1", "附录 C · 坑对照表"),
    ("p", "这份附录把前面各处散落的「不要这么写」集中成一张表，"
          "方便当检查清单用。左边是**错误写法**，中间是**症状**，右边是**正确写法**。"),

    ("h2", "C.1 语法与语义类"),
    ("table", [
        ["错误写法", "症状", "正确写法"],
        ["`def f(x, items=[])`", "所有调用共享同一个列表，越追加越长", "`items=None` + 函数内 `if items is None: items = []`"],
        ["`@dataclass` 里 `tags: list = []`", "同上，且更难发现", "`field(default_factory=list)`"],
        ["`for x in items: items.remove(x)`", "元素被跳过，删不干净", "遍历 `list(items)` 副本，或重建列表"],
        ["`for k in d: del d[k]`", "`RuntimeError: dictionary changed size`", "先 `for k in list(d):`"],
        ["循环里 `lambda: f(i)`", "所有回调都用最后的 `i`", "`lambda i=i: f(i)`，或用工厂方法"],
        ["`x == None`", "自定义 `__eq__` 时结果可能不符预期", "`x is None`"],
        ["`if not x:` 判数字", "`0` 被当成「没有值」", "`if x is None:`"],
        ["`except:`", "连 Ctrl+C 都吞掉，程序无法中断", "`except Exception:`"],
        ["`assert` 做输入校验", "`python -O` 时校验整段消失", "`if not ok: raise ValueError(...)`"],
        ["`except Exception: pass`", "功能长期不工作而无人知晓", "至少记一条日志；或注明降级后的状态"],
        ["`d[\"k\"]` 读可能没有的键", "`KeyError`", "`d.get(\"k\", 默认值)`"],
        ["`int(\"\")`", "`ValueError`", "`int(x or 0)`，或包 `try`"],
        ["`0.1 + 0.2 == 0.3`", "False", "`abs(a - b) < 1e-9`；金额用 int 或 Decimal"],
        ["`round(2.675, 2)`", "得 2.67", "`Decimal.quantize(..., ROUND_HALF_UP)`"],
        ["`strptime` 解析 `9:05`", "部分实现解析不出非零填充小时", "手工 `int()` 拆（见 `parse_moment`）"],
        ["`strftime(\"%a\")` 判星期", "中文系统上输出中文", "`date.weekday()` 数值判断"],
    ]),

    ("h2", "C.2 文件与编码类"),
    ("table", [
        ["错误写法", "症状", "正确写法"],
        ["`Path.write_text(...)` 改源码", "**整个文件的行尾被翻成 CRLF**，diff 爆炸", "`read_bytes` + `write_bytes`"],
        ["`open(p, \"w\")` 不写编码", "中文在 Windows 上乱码或报错", "`encoding=\"utf-8\"`"],
        ["CSV 导出用 `open(p, \"w\")`", "每行多一个空行", "`newline=\"\"`（+ `utf-8-sig` 给 Excel）"],
        ["程序内部读写用 `utf-8-sig`", "JSON 解析失败（BOM）", "内部一律 `utf-8`"],
        ["`__file__` 定位数据目录", "打包后数据写进临时目录，关掉就丢", "`sys.frozen` + `sys.executable`"],
        ["一次替换多个锚点不校验", "锚点写错时静默改错地方", "每处锚点**断言恰好命中一次**，否则整体拒写"],
        ["补丁脚本用 `findall` 取多分组", "拿到的是元组列表，`hits[0]` 不是字符串", "用 `finditer` 并按 `group(n)` 取"],
        ["脚本里写转义引号", "反斜杠被链路吃掉，外层字符串提前闭合", "内容一律用单引号 / 三单引号"],
        ["全量替换不做行数复核", "行尾被改动而看不出来", "`git diff --numstat` 核对变更行数"],
    ]),

    ("h2", "C.3 GUI 类"),
    ("table", [
        ["错误写法", "症状", "正确写法"],
        ["`command=self.save()`", "绑定时就执行一次，回调变成 `None`", "`command=self.save`"],
        ["`def handler(self):` 配 `bind`", "`TypeError`：少一个位置参数", "`def handler(self, event=None):`"],
        ["先 pack `expand=True` 的控件", "后面 pack 的控件被饿死，**完全不显示**", "先 pack 固定尺寸控件，最后 pack 内容区"],
        ["滚动条后于滚动区 pack", "滚动条被挤出可视区", "滚动条先 pack"],
        ["子类 `__init__` 里先干别的", "`TclError`：`self` 还不是控件", "第一句 `super().__init__(...)`"],
        ["主窗口 `withdraw()` 后查 `ismapped()`", "所有控件都返回 0，误判成「被饿死」", "先 `deiconify()` 再判定"],
        ["布局前查 `winfo_width()`", "得到 1（还没算）", "先 `update_idletasks()` / `update()`"],
        ["缓存 Tk 对象不探活", "解释器换过后 `TclError: invalid command name`", "用前调一个无害方法探活，失败就清缓存"],
        ["销毁后继续用控件", "同上", "`if w.winfo_exists(): w.destroy()`"],
        ["回调里不 try", "异常被 Tk 事件循环吞掉，界面静默失灵", "回调内部 `try/except` + 记日志"],
        ["用线程更新界面", "随机崩溃，极难复现", "用 `after()` 回到主线程"],
        ["定时器只在成功路径续期", "**一次异常后定时器永久死掉**", "`finally:` 里续期"],
        ["退出时不取消定时器", "回调打到正在销毁的控件上", "置退出标志，回调先检查它"],
    ]),

    ("h2", "C.4 数据与打包类"),
    ("table", [
        ["错误写法", "症状", "正确写法"],
        ["f-string 拼 SQL", "SQL 注入；名字带单引号直接语法错误", "`?` 占位符 + 参数元组"],
        ["循环里逐条 commit", "慢（每条一次磁盘刷写）", "`executemany` + 只 commit 一次"],
        ["不设 `row_factory`", "只能按下标取值，加一列就让取值全错位", "`conn.row_factory = sqlite3.Row`"],
        ["不设 `PRAGMA foreign_keys`", "外键形同虚设", "每个连接显式 `PRAGMA foreign_keys = ON`"],
        ["`ALTER TABLE` 前不查列", "重复启动报「duplicate column」", "先 `PRAGMA table_info` 再按需补"],
        ["新列不给默认值", "老数据行没有合法值", "`ADD COLUMN ... NOT NULL DEFAULT ''`"],
        ["只按键排序", "顺序随内部存储变化，看起来会「自己变」", "加第二级 `id ASC`"],
        ["改结构时删列", "老用户数据丢失", "加列永远只做加法"],
        ["打包脚本先清空 dist", "**用户运行期数据永久丢失**", "只删制品，数据另存另拷"],
        ["只信打包日志", "漏模块只在运行版炸", "打开归档**反向核对**符号"],
        ["`pip freeze` 覆盖依赖锁", "把间接依赖锁成当前版本，难以复现", "只锁直接依赖"],
    ]),
    ("pagebreak",),

    # =========================================================================
    # 附录 D 工具脚本
    # =========================================================================
    ("h1", "附录 D · 工具脚本与开发流程"),
    ("p", "项目跑到后来长出了一套自己的开发工具。它们既是「本项目怎么维护」的说明，"
          "也是写 Python 工具脚本的现成参考。"),
    ("table", [
        ["脚本", "作用", "值得学的地方"],
        ["`scripts/run_all_tests.py`", "一条命令跑完全部套件并汇总成表",
         "开场先探 `tkinter` 是否可用，解释器不对时**直接说该换哪个**，不闷头跑出一片假红"],
        ["`scripts/window_shot.py`", "把窗口抓成 PNG",
         "`PrintWindow` + `PW_RENDERFULLCONTENT`；抓完校验颜色数，**只抓到一种就抛错**"],
        ["`scripts/check_exe.py`", "打包后反向核对归档里的符号",
         "递归遍历 code object 的 `co_names` / `co_consts`"],
        ["`scripts/test_*.py`（11 个）", "回归测试",
         "每个都用 `check(名称, 条件, 现场值)` 的写法，失败时打印真实值"],
        ["`scripts/gen_changelog.py`", "从 `app_version.py` 生成 CHANGELOG",
         "**单一数据源**：版本号只有一处，日志自动重建"],
        ["`project_audit.py`", "AST 静态审计", "函数长度、嵌套深度、重复代码"],
        ["`check_name_scope.py`", "补 pyflakes 盲区", "except 名字作用域、闭包作用域"],
        ["`prune_unused_imports.py`", "批量删未使用导入", "字节级改写 + 语法安全校验"],
        ["`dep_inventory.py`", "依赖清单", "统计模块级 import 的第三方包"],
    ]),
    ("h2", "D.1 本项目自己的「补丁纪律」"),
    ("p", "前面 13.1 与 13.2 讲的是行尾，这里把它拼成一套完整的操作流程 —— "
          "这是本项目这几轮迭代里最核心的一条工程经验。"),
    ("ol", [
        "**写一个补丁脚本，而不是手工改文件**。脚本里每处替换都带断言："
        "锚点必须**恰好命中一次**，否则整体拒写。这一步拦住的是「替换到了别的地方」"
        "和「文件已经被改过」。",
        "**顺序化执行，不要在同一个文件上并行编辑**。同一文件的两处修改若并行提交，"
        "后一次的写入会基于旧内容，**静默丢掉前一次的改动**。",
        "**字节读、字节写**（`read_bytes` / `write_bytes`），中途 `decode` 处理文本、"
        "`encode` 写回，全程不碰文本模式的行尾翻译。",
        "**先记下当前的行尾指纹**：纯 CRLF 的文件，断言 `count(b\"\\r\\n\") == count(b\"\\n\")`；"
        "纯 LF 的文件，断言 `count(b\"\\r\\n\") == 0`；"
        "混排的文件（`main.py` 有 167 个单独 LF），断言这个数量没变。",
        "**写完立刻 `py_compile.compile(path, doraise=True)`**，语法错误当场暴露。",
        "**收尾用 `git diff --numstat` 核对**：变更行数与预期不符，说明动到了不该动的地方，"
        "`git checkout -- .` 回退重来。",
    ]),
    ("warn", "这套流程里最容易被跳过、也最危险的一条",
     "**「删除」最危险，仅次于它的就是「全量替换」**。\n"
     "本项目有一条硬规则：**不用 `git rm <目录>/<文件>`**。在某个 Git 版本下，"
     "只要路径里带 `/`，`git rm` 会删掉**整个顶层目录树** ——"
     "曾经因此一次性误删 25 个文件。正确做法是 `rm <file>` 再用 `git add -A` 让 Git 记录，"
     "而且**删除之前先提交**，这样任何误删都能 `git checkout -- .` 完整恢复。"),
    ("h2", "D.2 这套流程的通用形状"),
    ("p", "把上面六步抽象出来，它与具体的项目、语言都无关："),
    ("ok", "任何「程序化改写文件」都适用的四条",
     "① **先验证前提**（锚点唯一、现状符合预期），再动手；\n"
     "② **宁可整体失败，不要部分成功**（一处不对劲就什么都不写）；\n"
     "③ **写完立刻做一次独立校验**（编译、行数、差异）；\n"
     "④ **保证可回退**（先提交，再改）。\n"
     "这四条合起来就是一个最小可用的「安全批量改写」协议。"),
    ("h2", "D.3 待办（项目的下一步）"),
    ("p", "以下几条写在项目自己的记忆文件里，属于已经排定但还没做的："),
    ("ul", [
        "**拆 `main.py`**（当前 5,400 余行）—— 入口、主窗口、通用工具函数三者分离。",
        "**`todo_db.py` 的迁移逻辑表驱动化** + SQL 标识符白名单。",
        "**`Database` 的 Mixin 拆分** —— 现在 24 张表的操作都在一个类里。",
        "**引入 ruff 与 mypy**，把静态检查从「只看告警数」推进到「有规范标准」。",
        "**其余页面的空状态** —— 待办模块的空状态已经做完，其它页面还没有。",
    ]),
    ("spacer", 18),
    ("h2", "结语"),
    ("p", "这本手册从头到尾只做了一件事：**把语法点钉在真实代码上**。"
          "如果你读完之后记住的不是「Python 有推导式和装饰器」，"
          "而是「定时器续期要放 `finally`」「改源码要走字节」「"
          "`field(default_factory=list)` 是为什么」——那它就起作用了。"),
    ("p", "附录里的模块清单、体量统计、测试基线都是**生成时现算的**，"
          "所以只要重新跑一次生成脚本，它们永远与仓库同步；"
          "而正文里的代码是手抄的，改动后需要人工同步。"
          "这一点也提醒了一件更普适的事：**能自动化的东西就让机器算，"
          "手工抄写的内容一定要标注它的保质期。**"),
]
