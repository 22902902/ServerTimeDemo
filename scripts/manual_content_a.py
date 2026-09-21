# -*- coding: utf-8 -*-
"""Python 语法手册 · 正文（第一部分：第一章 ~ 第七章）。

内容与排版分离：本文件只描述「写什么」，至于标题多大、代码块什么底色，
全部交给 manual_engine.py。块的类型说明见 manual_engine 的模块 docstring。

写作约定
--------------------------------------------------------------------------------
* **每一段示例代码都摘自本项目源码**，不是为讲语法现编的。因此手册读起来的
  顺序是「语法点 -> 项目里的真实用法 -> 当初为什么这么写」。
* 代码里出现的 ``todo_db`` / ``todo_page`` / ``main`` 等名字，都能在项目里
  直接检索到。
* 正文里的 `` `x` `` 会渲染成等宽字，``**x**`` 会渲染成粗体。
"""

from __future__ import annotations

MAIN_VERSION = "v1.9.0"

BLOCKS = [
    # =========================================================================
    # 第一章
    # =========================================================================
    ("h1", "第一章 手册说明与项目全景"),
    ("p", "这是一本**可以对着代码看的** Python 语法手册。它不讲「Python 是什么」，"
          "而是把语言特性一条条摆开，每条都配一段本项目（ServerTimeDemo / "
          "ExpiryManager）里正在运行的真实代码 —— 你在项目里搜得到它、在手册里"
          "看得到它的语法依据，以及当初为什么写成那样。"),
    ("p", "这样编排的理由很实际：语法书上的例子总是干净的，而**真实的坑都长在"
          "「语法都对、组合起来就是不对」的地方**。本项目攒下的一批坑（行尾被"
          "改写、删除线画不出来、定时器断掉、目录页码不收敛）恰好都是这种，"
          "放在对应语法点旁边才记得住。"),

    ("h2", "1.1 怎么用这本手册"),
    ("ul", [
        "**当参考书查**：附录 A 是一页纸的语法速查表，附录 C 是「错误写法 → 正确写法」的对照表，"
        "两处都适合直接跳过去看。",
        "**当教材读**：第一到第十章按语言本身的顺序推进（词法 → 类型 → 控制流 → 函数 → 类 → 异常 → 模块 → 注解），"
        "每一节末尾都落到项目里的一段代码。",
        "**当项目导览读**：第十一章往后是「本项目真正用到的标准库」与「GUI 语法」、"
        "「工程约定与陷阱」，附录 B 是全模块清单。",
    ]),
    ("note", "版本对应关系",
     "手册里引用的代码对应项目 {ver}。若代码后续改动，以仓库里的实际源码为准 —— "
     "附录 B 的模块清单与体量统计是**每次生成时现算的**，不会过时；"
     "正文里的代码是手抄的，改动后需要同步。".replace("{ver}", MAIN_VERSION)),

    ("h2", "1.2 这个项目是什么"),
    ("p", "一句话：**一个单窗口的 Tkinter 桌面工作台**，把「服务器到期管理」「账号中心」"
          "「工具包」「学习笔记」「待办提醒」等一堆自用小功能收在一个程序里，"
          "用自绘的左侧导航切换，数据统一落在一个 SQLite 文件上。"),
    ("p", "它对学 Python 来说是个不错的样本，原因是三件事都齐了："),
    ("ol", [
        "**语言面够宽** —— 数据类、装饰器、闭包、上下文管理、类型注解、推导式、"
        "生成器全都在用，不是玩具代码。",
        "**有真实的持久化层** —— 24 张表的 SQLite，带迁移逻辑、事务、行工厂。",
        "**有真实的界面层** —— Tkinter 的坑几乎踩全了，注释里留着原因。",
    ]),
    ("image", "build/todo_shots/01_主界面三栏.png", 0.9),
    ("caption", "▲ 程序里的待办模块：左栏是清单（可拖动排序），中栏是条目列表，右栏是详情。"
                "手册里引用的界面代码大都能在这张图上找到对应形态。"),

    ("h2", "1.3 代码规模"),
    ("p", "生成这份手册时统计的体量（**每次生成现算**，见 `scripts/make_python_manual.py`）："),
    ("table", [
        ["位置", "文件数", "说明"],
        ["根目录", "{n_root}", "业务模块：界面、数据层、主题、组件"],
        ["embedded_admin_tools/", "{n_emb}", "内置管理工具（按 services/ 分层）"],
        ["scripts/", "{n_scr}", "开发期工具：测试、打包核对、手册生成本身"],
    ]),
    ("p", "**合计 {n_all} 个 Python 文件、{n_lines} 行**。根目录里 `main.py` 一个文件就有 "
          "5,400 余行 —— 它同时是「程序的入口」「主窗口的类定义」「一批通用工具函数」"
          "三个角色，这也是项目待办清单上「拆 main.py」那条的由来。"),

    ("h2", "1.4 分层与数据流"),
    ("p", "模块之间的依赖是单向的，画成下来是这样："),
    ("out", """       main.py（入口 + 主窗口 ExpiryManagerApp）
          │   组装一切、持有 DB、管定时器与托盘
          ├──────────────┬──────────────┬───────────────┐
          ▼              ▼              ▼               ▼
     nav_sidebar    *_page.py       *_window.py     log_setup
     （自绘导航）   （页面：拼控件） （独立窗口）    （日志，入口调一次）
          │              │              │
          │              ▼              ▼
          │          ui_components   *_db.py（数据层）
          │          page_components      │
          │          ui_theme（token）    ▼
          └────────────►  sqlite3  ──►  ExpiryManager_Data/expiry_manager.db"""),
    ("caption", "▲ 分层约定：页面不直接写 SQL，数据层不认识 tkinter。"),
    ("p", "这条约定带来两个好处，也是项目里反复强调的：**数据层的模块可以在没有 tkinter "
          "的解释器里跑测试**（本项目 11 个测试套件里有一批就是这么跑的），"
          "以及**换界面不用动数据逻辑**。"),

    ("h2", "1.5 全模块地图"),
    ("p", "下面这张表覆盖根目录与 `embedded_admin_tools/` 的全部模块，职责取各文件自己的"
          "模块 docstring 首句 —— 想了解某个功能从哪个文件入手，查这里最快。"),
    ("module_table",),

    ("h2", "1.6 阅读约定"),
    ("table", [
        ["记号", "含义"],
        ["`等宽字`", "代码、文件名、函数名、命令行"],
        ["**粗体**", "关键结论"],
        ["▲ 出处", "紧跟代码块下方，标明这段代码来自哪个文件的哪个函数"],
        ["灰底方框", "引自项目源码 docstring 的原文，是我自己当初写的注释"],
        ["蓝灰色提示框", "背景知识或设计取舍"],
        ["橙边框警告框", "踩过的坑，以及为什么不能那么写"],
        ["绿边框结论框", "拍板下来的正确做法"],
    ]),
    ("p", "代码块左侧是对齐的行号，方便你在源码里定位；行号栏与代码栏底色不同，"
          "复制代码时不容易把行号一起带走。"),
    ("pagebreak",),

    # =========================================================================
    # 第二章
    # =========================================================================
    ("h1", "第二章 词法与基础语法"),
    ("p", "这一章讲最小的单位：一个源文件长什么样、注释怎么写、名字怎么起、"
          "行怎么折。这些都是「一眼就能看懂、但写错了要很久才发现」的东西。"),

    ("h2", "2.1 文件头：编码声明与模块 docstring"),
    ("p", "Python 3 的源文件默认就是 UTF-8，所以 `# -*- coding: utf-8 -*-` 严格来说不是必需的。"
          "项目里每个文件仍然带着它 —— 这是延续下来的习惯，好处是文件被拿去看、"
          "被别的编辑器打开时意图明确。"),
    ("p", "真正重要的是**紧跟其后的模块 docstring**：它是文件的第一个语句，"
          "会被 `help()` 和文档工具读到。本项目把它当「文件级说明书」用，"
          "把这张表有哪些表、有哪些容易误解的语义都写在里面："),
    ("code", "python", '''# -*- coding: utf-8 -*-
"""
================================================================================
待办事项模块 - 数据层（Data Layer）
================================================================================
本模块封装「待办 / 提醒事项」所需的全部持久化逻辑与**工作日日历**推算。
复用主程序的 SQLite 数据库文件（db_path 由调用方注入），与其余模块共享连接，
因此备份、迁移都只需处理一个文件。

本模块涉及的表（建表语句见 create_tables）：
    todo_lists     清单：名称、颜色（苹果 12 色之一）、图标、排序
    todo_items     待办条目：标题、备注、日期、时间、重复、优先级、旗标、标签
    todo_subtasks  子任务：挂在条目下的轻量清单项
    todo_holidays  节假日日历：放假 / 调休上班两天都记在这一张表
    todo_state     模块内键值状态：上次工作日弹窗日期等

工作日语义（这层是「周末 / 节假日自动跳过」的全部依据）
--------------------------------------------------------------------------------
本模块把「工作日」定义为：**同时不是法定放假日、也不是周六周日**的那一天；
唯一的例外是**调休上班日** —— 它虽然落在周末，但因为被国务院安排上班，
所以算工作日。
"""
'''),
    ("caption", "▲ todo_db.py 开头 · 节选（原文用表格画表结构，此处为放进版心改排成列表）"),
    ("note", "docstring 的三种写法",
     "**单行**：`\"\"\"一句话说明。\"\"\"` 收在同行；**多行**：首行一句话概要、空一行、"
     "再写细节，结尾的 `\"\"\"` 单独一行（PEP 257）；**原始串**：内容里有反斜杠时用 "
     "`r\"\"\"...\"\"\"`，避免转义被解释。本项目的模块 docstring 统一是多行写法，"
     "因为要塞进表结构和语义约定。"),

    ("h2", "2.2 注释：为什么这么写"),
    ("p", "本项目的注释有个明确取向：**不解释「这行在做什么」，只解释「为什么不是别的写法」**。"
          "代码本身已经说明前一半，后一半才是三个月后还会绊人的部分。"),
    ("code", "python", '''def _migrate_alert_columns(self):
    """给老库补上「到点提醒」的两列。

    新装的程序建表时就带上它们，但**已经装过老版本**的库里
    ``todo_items`` 没有这两列 —— SQLite 又没有
    ``ADD COLUMN IF NOT EXISTS``，只能先查 ``PRAGMA table_info``
    再按需补，否则用户得删库重来。
    """
    existing = {
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
    ("caption", "▲ todo_db.py · TodoDB._migrate_alert_columns()"),
    ("p", "注意这里没有一行注释在说「查询表结构」「循环补列」。它说的是"
          "**为什么不能写 `ADD COLUMN IF NOT EXISTS`**、以及**漏了会有什么后果**"
          "（用户得删库重来）。"),

    ("h2", "2.3 命名规范"),
    ("p", "Python 社区只有一份约定（PEP 8），没有强制。本项目的实际用法如下，"
          "照着写就不会有突兀感："),
    ("table", [
        ["对象", "写法", "项目里的例子"],
        ["模块", "全小写 + 下划线", "`todo_db`、`nav_sidebar`、`page_components`"],
        ["包", "全小写，不用下划线", "`embedded_admin_tools`"],
        ["类", "大驼峰 CapWords", "`TodoDB`、`TodoPage`、`ScrollArea`、`ManualDoc`"],
        ["函数 / 方法", "全小写 + 下划线", "`pending_alerts`、`_migrate_alert_columns`"],
        ["变量", "全小写 + 下划线", "`due_date`、`submit_text`、`moment`"],
        ["常量", "全大写 + 下划线", "`ALERT_GRACE_MINUTES`、`TODO_TICK_MS`"],
        ["私有成员", "前导单下划线", "`self._conn`、`_norm`、`_STRIKE_FONTS`"],
        ["类型变量", "同变量", "`list[str]`、`dict[int, str]`"],
        ["「别碰」的成员", "双下划线前后", "`__init__`、`__eq__`、`__enter__`"],
    ]),
    ("warn", "单下划线与双下划线的区别",
     "**前导单下划线**（`_norm`）只是「约定别在外部用」，`from m import *` 会跳过它，"
     "但直接写 `m._norm()` 照样能调 —— 它是给人的信号，不是给解释器的锁。"
     "**前导双下划线**（`self.__x`）会触发名称改写（mangling），"
     "在类 `Foo` 里变成 `_Foo__x`，用于避免与子类同名属性打架。"
     "本项目只用单下划线，因为**界面层的测试需要直接点私有方法**"
     "（例如探针里调 `page._list_drag_press(...)` 模拟拖动），"
     "双下划线反而会让测试写不下去。"),

    ("h2", "2.4 缩进与续行"),
    ("p", "缩进用 **4 个空格**，项目里没有一处用 Tab。行太长时有三种合法折法，"
          "本项目三种都在用："),
    ("ol", [
        "**括号里直接换行**（隐式续行，最常用）：`(` `[` `{` 之内不需要任何续行符，"
        "这是首选写法，因为它不依赖行尾有没有空格。",
        "**行尾反斜杠**：只有在括号外、又必须折行时才用。项目里几乎不用 ——"
        "反斜杠后粘一个空格就是语法错误，而肉眼看不出来。",
        "**把长表达式提成变量或辅助函数**：比前两种都好，本项目后来倾向这种。",
    ]),
    ("code", "python", '''    for column, ddl in (
        ("alerted_for", "ALTER TABLE todo_items ADD COLUMN "
                        "alerted_for TEXT NOT NULL DEFAULT ''"),
        ("snooze_until", "ALTER TABLE todo_items ADD COLUMN "
                         "snooze_until TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in existing:
            self.conn.execute(ddl)
'''),
    ("caption", "▲ 括号内的隐式续行 · todo_db.py"),
    ("p", "上面这段还有一处值得留意的细节：两个字符串字面量**直接相邻**"
          "（`\"ALTER TABLE ... \" ` 和 `\"alerted_for ...\"`），"
          "Python 会在编译期把它们拼成一个，不会产生运行期开销 —— "
          "这是拆长字符串的惯用手段。"),

    ("h2", "2.5 运算符速查"),
    ("table", [
        ["类别", "运算符", "说明 / 项目里的用法"],
        ["算术", "`+ - * /`", "`/` 永远得到 float，即使能整除"],
        ["整除 / 取余", "`// %`", "`divmod(总数, 12)` 一次拿到商和余（`add_months()`）"],
        ["幂", "`**`", "`2 ** 10`"],
        ["比较", "`== != < <= > >=`", "可以链式写：`0 <= hour <= 23`"],
        ["身份", "`is` / `is not`", "只与 `None` / `True` / `False` 比较时用"],
        ["成员", "`in` / `not in`", "`if column not in existing`"],
        ["逻辑", "`and or not`", "短路求值；`not` 优先级最低，别省括号"],
        ["位运算", "`& | ^ ~ << >>`", "本项目用在权限位与颜色通道上"],
        ["赋值", "`= += -= *= /= //= %= **=`", "还有 `&=` `|=` 等位运算版本"],
        ["三目", "`A if 条件 else B`", "表达式，不是语句"],
        ["海象", "`:=`", "在表达式里赋值，见 5.6"],
        ["解包", "`*` / `**`", "`f(*args, **kwargs)`、`a, *rest = seq`"],
    ]),
    ("note", "`0 <= hour <= 23` 为什么在 Python 里能写",
     "这是**链式比较**，Python 把它编译成 `0 <= hour and hour <= 23`，"
     "且中间的 `hour` 只求值一次。项目里解析时间就是这么校验的："
     "`if not (0 <= hour <= 23 and 0 <= minute <= 59): return None`。"),

    ("h2", "2.6 为什么这里必须用字节而不是字符"),
    ("p", "本项目有一条贯穿始终的纪律：**改源码文件必须走字节层**。"
          "先看现状 —— 项目里不同文件的行尾是不一样的："),
    ("table", [
        ["文件", "行尾现状", "成因"],
        ["应用源码（`main.py`、`todo_db.py` …）", "CRLF", "在 Windows 上生成、被编辑器改过"],
        ["`main.py`", "**混排**：CRLF + 少量单独 LF", "历史上被不同工具改过"],
        ["`scripts/*.py`", "LF", "在 Git Bash 环境里生成"],
        ["`*.md`", "LF", "同上"],
    ]),
    ("p", "行尾混排本身不影响运行，但会**把 diff 炸掉**：如果把 `main.py` 用普通文本方式"
          "写回去，Python 的默认行为会把整个文件的行尾统一成一种，于是「改 5 行」在 "
          "`git diff` 里显示为「改了 5,000 行」。所以本项目改源码的姿势是先读进来、"
          "只替换目标片段、再原样写回："),
    ("code", "python", '''from pathlib import Path

p = Path("todo_db.py")
raw = p.read_bytes()                      # 字节读，不经过文本层
assert raw.count(b"\\r\\n") == raw.count(b"\\n")   # 确认是纯 CRLF
before = raw.count(b"\\n")
text = raw.decode("utf-8").replace("\\r\\n", "\\n")     # 统一成 LF 再操作

# ……在这里对 text 做替换，并断言每处锚点恰好命中一次……

out = text.replace("\\n", "\\r\\n").encode("utf-8")
assert out.count(b"\\n") == before + added          # 行数变化符合预期
assert out.count(b"\\r\\n") == out.count(b"\\n")     # 没有意外的单独 LF
p.write_bytes(out)                                  # 字节写，不经文本层
'''),
    ("caption", "▲ 项目里改源码通用的「字节级补丁」骨架"),
    ("ok", "这条纪律的三条硬要求",
     "① 每处锚点**断言恰好命中一次**，否则整体拒写（避免半截替换）；"
     "② 断言**行尾变化量**与预期一致；③ 写完用 `py_compile` 与 "
     "`git diff --numstat` 复核变更行数。三条齐了，才敢按下执行。"),
    ("pagebreak",),

    # =========================================================================
    # 第三章
    # =========================================================================
    ("h1", "第三章 变量与内置类型"),
    ("p", "Python 的变量不是「装东西的盒子」，而是**贴在对象上的名字**。"
          "理解这一点，后面很多现象（可变默认参数、闭包捕获、`is` 与 `==` 的区别）"
          "就都有了解释。"),

    ("h2", "3.1 赋值与解包的各种形态"),
    ("table", [
        ["写法", "效果"],
        ["`a = b = 0`", "两个名字指向同一个对象"],
        ["`a, b = 1, 2`", "元组解包，右边先构造成元组"],
        ["`a, b = b, a`", "交换（右边先整体求值）"],
        ["`first, *rest = seq`", "带星号解包，`rest` 是列表"],
        ["`a, (b, c) = 1, (2, 3)`", "嵌套解包"],
        ["`x += 1`", "对不可变对象等于 `x = x + 1`；对列表是原地修改"],
    ]),
    ("p", "项目里最常见的解包是**遍历字典 / 元组列表时当场拆开**："),
    ("code", "python", '''REPEAT_RULES: list[tuple[str, str]] = [
    ("none", "永不"),
    ("daily", "每天"),
    ("weekly", "每周"),
    ("biweekly", "每两周"),
    ("monthly", "每月"),
    ("yearly", "每年"),
    ("custom", "自定"),
]
REPEAT_LABELS = dict(REPEAT_RULES)          # 元组列表 -> 字典，一行搞定
'''),
    ("caption", "▲ todo_db.py · 规则表与其反查字典同源"),
    ("p", "`dict()` 接一个「二元组序列」就能构造字典，所以**下拉框要的顺序**"
          "（列表）和**按值查标签**（字典）可以共用一份数据，永远不会不同步。"),

    ("h2", "3.2 数字：int / float / bool"),
    ("p", "`int` 是任意精度的（不会溢出），`float` 是 IEEE-754 双精度（**会有误差**），"
          "`bool` 是 `int` 的子类（`True == 1`）。"),
    ("code", "python", '''def excel_serial_to_date(value: float) -> date:
    """Excel 的日期序列号转 date：以 1899-12-30 为原点。"""
    base = datetime(1899, 12, 30)
    return (base + timedelta(days=float(value))).date()
'''),
    ("caption", "▲ main.py · 导入 Excel 时的日期换算"),
    ("warn", "金额和精度的规矩",
     "`0.1 + 0.2 == 0.3` 是 **False**（结果是 0.30000000000000004）。"
     "所以：① 金额一律用 `int` 存「分」，或 `decimal.Decimal`；"
     "② 比较浮点用 `abs(a - b) < 1e-9`，别用 `==`；"
     "③ 展示时用 `f\"{v:.2f}\"` 格式化，不要指望它精确。"
     "本项目目前的金额场景都还在 Excel 导入导出环节，因此是「转成 float 再格式化」，"
     "没有做分单位存储 —— 涉及记账时要改。"),

    ("h2", "3.3 字符串"),
    ("p", "字符串是**不可变**的：任何「修改」都是造了一个新串。这决定了"
          "「循环里拼字符串」是 O(n²) 的坏习惯，应该先收进列表再 `join`。"),
    ("h3", "三种字符串字面量"),
    ("code", "python", '''plain = "ALTER TABLE todo_items ADD COLUMN alerted_for TEXT NOT NULL DEFAULT ''"
fstring = f"有 {len(missed)} 条提醒已过时间：{names}{tail}"
raw_text = r"C:\\Users\\shaoy\\AppData"       # r 前缀：反斜杠不转义
multiline = """第一行
第二行"""
'''),
    ("caption", "▲ 三种字面量；注意 f-string 里的单引号是 SQL 里的空串，不是 Python 的"),
    ("h3", "f-string 的常用写法"),
    ("table", [
        ["写法", "结果"],
        ["`f\"{name}\"`", "直接插入"],
        ["`f\"{value:.2f}\"`", "保留两位小数"],
        ["`f\"{n:>3}\"`", "右对齐、宽度 3（拼菜单与行号时常用）"],
        ["`f\"{raw!r}\"`", "用 `repr()` 的结果插入，调试时看得到引号与转义"],
        ["`f\"{when:%Y-%m-%d}\"`", "直接套日期格式"],
        ["`f\"{items=}\"`", "3.8+ 的调试写法，展开成 `items=[1, 2]`"],
    ]),
    ("code", "python", '''        names = "、".join(it.title for it in missed[:3])
        tail = f" 等 {len(missed)} 条" if len(missed) > 3 else ""
        self.tray.notify(APP_TITLE, f"有 {len(missed)} 条提醒已过时间：{names}{tail}")
'''),
    ("caption", "▲ main.py · 托盘汇总文案；`join` 接的是生成器表达式，不需要先造列表"),
    ("h3", "常用方法与切片"),
    ("table", [
        ["写法", "作用"],
        ["`s.strip()`", "去掉两端空白（还有 `lstrip` / `rstrip`）"],
        ["`s.split(\" \")`", "按分隔符切成列表；不传参数则按任意空白切并去掉空串"],
        ["`s.replace(a, b)`", "全部替换"],
        ["`s.startswith(p)` / `s.endswith(p)`", "前后缀判断"],
        ["`s.casefold()`", "大小写无关比较用的规范化（比 `lower()` 更彻底）"],
        ["`s.zfill(2)`", "补零到两位，如 `\"9\".zfill(2) == \"09\"`"],
        ["`s[:2]`", "取前两个字符（切片不会越界报错）"],
        ["`\"-\".join(seq)`", "拼接，元素必须都是字符串"],
        ["`s in other`", "子串判断"],
    ]),
    ("code", "python", '''def _norm(value) -> str:
    """把任意值规范化为去空白字符串；None 视作空串。"""
    if value is None:
        return ""
    return str(value).strip()
'''),
    ("caption", "▲ todo_db.py · _norm()，全模块 30 多处在用"),
    ("note", "`_norm` 为什么值得单独存在",
     "SQLite 取出来的列可能是 `None`、可能是 `\"\"`、也可能是带空格的文本。"
     "如果每个字段各自 `strip()`，迟早有人漏掉一处，于是出现「明明填了日期却说没填」。"
     "**收成一个函数之后，「空」在整个模块里只有一个含义**：空字符串。"
     "这个函数还顺带承担了类型宽容 —— 传进来数字也能变成字符串。"),

    ("h2", "3.4 真值判定与 None"),
    ("p", "任何对象都有「真假」。下面这些**都是假**：`None`、`False`、`0`、`0.0`、"
          "`\"\"`、`[]`、`()`、`{}`、`set()`。其余为真。"),
    ("code", "python", '''if not _norm(item.due_date) or not _norm(item.due_time):
    return None                      # 没设日期或时间 -> 这条根本不参与提醒
'''),
    ("caption", "▲ todo_db.py · alert_moment() 的第一道闸"),
    ("p", "因为空串是假值，上面这两句既可以理解为「没设置」，也可以理解为「设置了但是空的」——"
          "两者在业务上是同一件事，正好不需要区分。"),
    ("h3", "`or` 兜底的惯用法"),
    ("code", "python", '''color=_norm(row["color"]) or DEFAULT_LIST_COLOR,
repeat_rule=_norm(row["repeat_rule"]) or "none",
sort_order=int(row["sort_order"] or 0),
'''),
    ("caption", "▲ todo_db.py · from_row() 里成排的兜底"),
    ("p", "`a or b` 的含义是「`a` 若为假就取 `b`」，正好用来填默认值："
          "库里的空值 → 变成有意义的默认值。**但要注意它同时会吞掉合法的 `0` 与空串** ——"
          "所以这里的 `int(row[\"sort_order\"] or 0)` 是安全的（0 本来就是想要的默认值），"
          "而如果某个字段的合法值包含 `0`，就不能这么写。"),

    ("h3", "与 None 比较：用 is"),
    ("table", [
        ["写法", "结论"],
        ["`if x is None:`", "**推荐**。`None` 是单例，`is` 是身份比较，没有重载歧义"],
        ["`if x == None:`", "能用但不推荐；`x` 的自定义 `__eq__` 可能改变结果"],
        ["`if not x:`", "判「假值」。当心它会连 `0`、空串、空列表一起匹配"],
        ["`if x:`", "判「有值」"],
    ]),
    ("code", "python", '''    dialog = getattr(self, "_todo_alert_win", None)
    self._todo_alert_win = None
    if dialog is None:
        return
'''),
    ("caption", "▲ main.py · _close_todo_alert()：先取出、先置空、再判断"),
    ("p", "这里刻意分了三步。如果写成 `if self._todo_alert_win: self._todo_alert_win.destroy()` "
          "再置空，第二层调用（把引用清空后）也不会出错，但**中间任何一步抛异常都会留下"
          "一个指向已销毁控件的引用**，而 `destroy()` 之后的控件再访问会抛 "
          "`TclError: invalid command name`。先把引用置 `None`，等于让「关闭」这个操作"
          "**幂等** —— 重复调用安全。"),

    ("h2", "3.5 类型转换"),
    ("table", [
        ["写法", "结果 / 注意"],
        ["`int(\"42\")`", "42；`int(\"4.2\")` 会 **抛 ValueError**"],
        ["`int(4.9)`", "4，**向零取整**，不是四舍五入"],
        ["`float(\"4.2\")`", "4.2"],
        ["`str(42)`", "'42'；对对象是 `repr` 还是 `str` 取决于是否定义了 `__str__`"],
        ["`bool([])`", "False"],
        ["`list(\"abc\")`", "`['a', 'b', 'c']`"],
        ["`list({\"a\": 1})`", "`['a']` —— 字典转列表拿到的是**键**"],
        ["`dict([(\"a\", 1)])`", "`{'a': 1}`"],
        ["`round(2.675, 2)`", "**2.67**，浮点误差所致，别指望它四舍五入"],
    ]),
    ("warn", "`int()` 的三种失败方式",
     "`int(\"\")`、`int(\"abc\")`、`int(None)` 全都抛 **ValueError 或 TypeError**。"
     "所以从界面或文件读来的数字一律要防：本项目用的姿势是"
     "`int(x)` 外面套 `try / except ValueError`，或者用 `or` 先兜成默认值 —— "
     "`int(row[\"sort_order\"] or 0)` 里的 `or 0` 就是为了让 `None` 不进 `int()`。"),
    ("pagebreak",),

    # =========================================================================
    # 第四章
    # =========================================================================
    ("h1", "第四章 容器类型"),
    ("p", "四种内建容器划分得很清楚：**list 有序可变、tuple 有序不可变、"
          "dict 按键取值、set 只关心「有没有」**。选错的典型症状是"
          "「明明只想判断存在性，却写了一个每次都要遍历的列表」。"),
    ("table", [
        ["类型", "字面量", "可变", "有序", "适用"],
        ["list", "`[1, 2]`", "是", "是", "有顺序的一批东西；界面的行、排序结果"],
        ["tuple", "`(1, 2)`", "否", "是", "固定的组合；能当 dict 的键"],
        ["dict", "`{\"a\": 1}`", "是", "是（3.7+ 保证插入序）", "按名字取东西；配置、行数据"],
        ["set", "`{1, 2}`", "是", "否", "去重、存在性判断、集合运算"],
    ]),
    ("p", "注意 `{}` 是**空字典**，空集合要写 `set()`。"),

    ("h2", "4.1 list：本项目的界面行就是它"),
    ("table", [
        ["操作", "写法"],
        ["追加 / 扩展", "`items.append(x)` / `items.extend(seq)`"],
        ["插入 / 删除", "`items.insert(i, x)` / `del items[i]` / `items.pop()`"],
        ["查找", "`items.index(x)`（找不到抛 ValueError）、`x in items`"],
        ["排序", "`items.sort()`（原地）vs `sorted(items)`（新列表）"],
        ["倒序 / 反转", "`items.reverse()`（原地）、`list(reversed(items))`"],
        ["浅复制", "`items.copy()` 或 `items[:]`"],
        ["统计", "`items.count(x)`、`len(items)`、`sum(nums)`、`max` / `min`"],
    ]),
    ("code", "python", '''    due: list[TodoItem] = []
    missed: list[TodoItem] = []
    moments: dict[int, str] = {}
    for row in rows:
        item = TodoItem.from_row(row)
        moment = alert_moment(item)
        if moment is None or moment > now:
            continue
        text = moment_str(moment)
        (missed if now - moment > grace else due).append(item)
        moments[item.id] = text
'''),
    ("caption", "▲ todo_db.py · pending_alerts() 内部（此处略作合并以缩短篇幅）"),
    ("p", "`(a if 条件 else b).append(x)` 这种写法能省掉一个 if 分支，"
          "但**只在两个候选都很短时才值得**。更长的情况宁可写两行 —— "
          "本项目在 `_run_todo_alerts` 里就是老老实实分成 `if missed:` 与 `if due:` 两段。"),

    ("h2", "4.2 tuple：固定结构与「可哈希」"),
    ("p", "元组常被当成「不可变的列表」，其实它更适合**表示一条结构固定的记录** ——"
          "比如「颜色名 + 色值」、「标签 + 个数」。它还有一个列表没有的能力："
          "**可以当字典的键、可以放进 set**，因为它不可变、可哈希。"),
    ("code", "python", '''# 苹果提醒事项的 12 色列表色（取自 iOS 18 自建列表取色盘）
LIST_COLORS: list[tuple[str, str]] = [
    ("红色", "#FF3B30"),
    ("橙色", "#FF9500"),
    ("黄色", "#FFCC00"),
    ("绿色", "#34C759"),
    ("薄荷", "#00C7BE"),
    ("蓝色", "#007AFF"),
    ("靛蓝", "#5856D6"),
    ("紫色", "#AF52DE"),
    ("玫红", "#FF2D55"),
    ("棕色", "#A2845E"),
    ("深灰", "#8E8E93"),
    ("浅褐", "#D4B89F"),
]
'''),
    ("caption", "▲ todo_db.py · LIST_COLORS"),
    ("note", "这里为什么不用两个平铺的列表",
     "写成 `NAMES = [...]` 加 `VALUES = [...]` 也能跑，但那样「第 3 个颜色叫什么」"
     "要靠下标对齐，插一个就会错位。**两个互相有对应关系的东西，就装进同一个元组**，"
     "让它们物理上无法分离。"),

    ("h2", "4.3 dict：本项目的配置与行数据主力"),
    ("table", [
        ["操作", "写法", "注意"],
        ["取值（带默认）", "`d.get(k, default)`", "**键不存在也不报错**；`d[k]` 会抛 KeyError"],
        ["存在性", "`k in d`", "判断的是**键**，不是值"],
        ["设默认值", "`d.setdefault(k, v)`", "键在就不动，不在才写入"],
        ["更新多个", "`d.update(other)`", "或 3.9+ 的 `d1 | d2`（合并出新字典）"],
        ["删除", "`del d[k]` / `d.pop(k, None)`", "`pop` 给默认值可以不报错"],
        ["遍历", "`d.items()` / `d.keys()` / `d.values()`", "遍历时**不能改大小**"],
        ["构造", "`dict(zip(keys, vals))`", "两个列表配成字典"],
    ]),
    ("code", "python", '''def popular_tags(tools, limit: int = 0) -> list[tuple[str, int]]:
    """统计一批工具的标签使用次数：[(标签, 个数)]，个数降序、标签升序。"""
    counts: dict[str, int] = {}
    label: dict[str, str] = {}
    for tool in tools:
        for tag in tool_tags(tool):
            key = tag.casefold()
            counts[key] = counts.get(key, 0) + 1
            label.setdefault(key, tag)
    items = [(label[key], count) for key, count in counts.items()]
    items.sort(key=lambda item: (-item[1], item[0].casefold()))
    return items[:limit] if limit > 0 else items
'''),
    ("caption", "▲ tools_launcher.py · popular_tags()"),
    ("p", "这一小段里有四个可以直接拿去用的字典惯用法："),
    ("ol", [
        "**计数**：`counts[k] = counts.get(k, 0) + 1`。不用先判断键在不在。",
        "**保留首次出现的写法**：`label.setdefault(k, tag)` —— 大小写不同的标签"
        "（`Python` / `python`）只算一个，展示时用第一次遇到的写法。",
        "**两张表同源**：计数用规范化后的键，展示用原始写法，各司其职。",
        "**`items()` 遍历**：拿到的是 `(键, 值)` 二元组，直接就地解包。",
    ]),
    ("warn", "不要在遍历字典时增删键",
     "`for k in d: del d[k]` 会抛 `RuntimeError: dictionary changed size during iteration`。"
     "正确做法是先取快照：`for k in list(d): ...`，或者收集成列表再统一删。"
     "本项目在 `log_setup._reset_for_tests` 里就是先 `list(root.handlers)` 再逐个移除。"),

    ("h2", "4.4 set：判断「有没有」比 list 快得多"),
    ("p", "`x in list` 要逐个比对（O(n)），`x in set` 走哈希（平均 O(1)）。"
          "**只要一段代码反复问「这个在里面吗」，就该换成 set** —— "
          "本项目在数据库迁移里就是这么用的："),
    ("code", "python", '''    existing = {
        row["name"]
        for row in self.conn.execute("PRAGMA table_info(todo_items)").fetchall()
    }
    for column, ddl in (...):
        if column not in existing:
            self.conn.execute(ddl)
'''),
    ("caption", "▲ todo_db.py · 先把列名收成 set，再逐列判断"),
    ("p", "这里其实只判断了 2 次，换不换 set 无所谓；但同一个模式在 "
          "`main.py` 里判断 `tool_items` / `shared_accounts` / `credential_items` / `users` "
          "四张表几十个列时，就是在真省时间。**统一的写法让「哪种都行」的地方也不用挑**。"),
    ("h3", "集合运算"),
    ("table", [
        ["写法", "含义"],
        ["`a | b`", "并集"],
        ["`a & b`", "交集"],
        ["`a - b`", "差集（在 a 不在 b）"],
        ["`a ^ b`", "对称差（只在一侧）"],
        ["`a <= b`", "a 是否为 b 的子集"],
        ["`a.isdisjoint(b)`", "两者是否完全不相交"],
    ]),

    ("h2", "4.5 推导式：一行构造容器"),
    ("p", "推导式（comprehension）是 Python 最有辨识度的语法之一。四种形态："),
    ("code", "python", '''names = [row["name"] for row in rows]                    # 列表推导
names = [n for n in names if n]                          # 带过滤
sizes = {name: len(name) for name in names}              # 字典推导
unique = {name.casefold() for name in names}             # 集合推导
total = sum(len(name) for name in names)                 # 生成器表达式（不是推导）'''),
    ("caption", "▲ 四种形态"),
    ("p", "**生成器表达式**与列表推导只差一对方括号，但它不一次性造出列表，"
          "而是按需产出。传给 `sum` / `join` / `any` / `all` 这类函数时应该用生成器版本，"
          "省一次内存分配："),
    ("code", "python", '''names = "、".join(it.title for it in missed[:3])
'''),
    ("caption", "▲ main.py · join 直接吃生成器，不需要先造列表"),
    ("p", "项目里也大量用推导式做「提取一列」的活："),
    ("code", "python", '''headers = [normalize_text(value) for value in header_row]
header_map = {header: index for index, header in enumerate(headers) if header}
cols = [p.name for p in sorted(rows, reverse=True)[:20]]
labels = [item["label"] for item in parse_account_image_items(image_value)
          if item.get("label")]
'''),
    ("caption", "▲ 分别出自 main.py 与手册生成本身"),
    ("warn", "推导式别写太长",
     "推导式一旦超过一行、或者带两三个 `if`，可读性会迅速差过普通 for 循环。"
     "本项目的规矩是：**推导式里不写函数调用以外的逻辑**；"
     "需要分支就用普通循环 + `append`。判断标准很朴素 —— "
     "「这行字能不能一口气念完」。"),

    ("h2", "4.6 排序与 key"),
    ("p", "`sort()` 与 `sorted()` 都接受 `key=` 参数：**key 是一个函数，"
          "负责把元素映射成「拿来比较的东西」**。按多个条件排序，就让 key 返回元组。"),
    ("code", "python", '''    scored.sort(key=lambda item: (-item[0], item[1]))
'''),
    ("caption", "▲ tools_launcher.py · 先按分数降序、分数相同再按原顺序升序"),
    ("p", "`-item[0]` 是「降序」的常用写法（元组比较是逐项比较，负号翻转了大小关系）。"
          "第二项 `item[1]` 是原始下标，用它保证**同分时顺序稳定**，"
          "否则每次搜索结果都会自己换位置。"),
    ("p", "key 也可以是一个具名函数，条件复杂时比 lambda 清楚得多："),
    ("code", "python", '''    def sort_key(pair):
        raw_value = pair[0]
        number_value = self.parse_number(raw_value)
        if number_value is not None:
            return (0, number_value)
        return (1, str(raw_value).lower())

    items.sort(key=sort_key, reverse=reverse)
'''),
    ("caption", "▲ embedded_admin_tools/market_quote_window.py · 表格点表头排序"),
    ("p", "这个 key 返回 `(0, 数字)` 或 `(1, 文本)`：**第一项是「能不能当数字看」的标志位**，"
          "于是所有数字行排在所有文本行前面，各自内部再比大小 —— "
          "表格排序里非常实用的一个小技巧。"),
    ("note", "多条件排序为什么不用连写多个 sort",
     "Python 的 sort **稳定**，所以「先按 A 排、再按 B 排」也能得到正确结果，"
     "但那是写两次、遍历两遍。**用元组 key 一次搞定**，意图也更直白。"),
    ("image", "build/release/todo_list_drag.png", 0.9),
    ("caption", "▲ 清单拖动重排进行中：被拖的那一行整体压暗，两行之间有一条 2px 插入指示线。"
                "松手之后算出的新顺序，最后就是写回 `todo_lists.sort_order` 的那一串值。"),

    ("h2", "4.7 可变与不可变：一个必须记住的陷阱"),
    ("p", "这是 Python 最经典的坑之一，本项目在数据类那里正面撞上过："),
    ("code", "python", '''# 错误写法：所有实例共用同一个列表！
@dataclass
class Bad:
    tags: list[str] = []


# 正确写法：默认值由工厂函数「每次现造一个」
@dataclass
class TodoItem:
    tags: list[str] = field(default_factory=list)
'''),
    ("caption", "▲ todo_db.py · TodoItem 里的 field(default_factory=list)"),
    ("warn", "根因不在 dataclass，在「默认值只求值一次」",
     "函数（和方法）的默认值**在定义时求值一次**，之后所有调用共用同一个对象。"
     "所以 `def f(items=[])` 里的那一个空列表会被所有调用共享 —— "
     "往里 append 一次，下次调用还在。`@dataclass` 只是把这个行为原样继承了下来。\n"
     "判断规则很简单：**默认值是可变对象（list / dict / set）就必须用工厂**。"
     "`field(default_factory=list)` 的含义是「每次构造实例时调一次 `list()`」，"
     "于是每个实例都有自己的空列表。"),
    ("p", "不可变对象没有这个问题，所以 `TodoItem` 里几十个 `str` / `int` 字段"
          "都直接写默认值，只有 `tags` 需要 `default_factory`。"),
    ("pagebreak",),

    # =========================================================================
    # 第五章
    # =========================================================================
    ("h1", "第五章 控制流"),
    ("p", "Python 的控制流语法极少，但有两种写法上的倾向值得学："
          "**早退式（守卫子句）**与**扁平化嵌套**。项目里几乎所有稍长的函数都这么写。"),

    ("h2", "5.1 if / elif / else 与条件表达式"),
    ("code", "python", '''    if getattr(self, "_exiting", False):
        return
    try:
        self._run_todo_alerts()
    except Exception:
        logger.exception("待办到点提醒巡检失败")
    finally:
        self.after(TODO_TICK_MS, self.todo_alert_check)
'''),
    ("caption", "▲ main.py · todo_alert_check()：先守卫、再干活、最后必续期"),
    ("p", "条件表达式（三目）是**表达式**不是语句，所以能塞进参数里："),
    ("code", "python", '''        mid_count = len(items) if self.current_scope == "completed" else len(open_items)
        return items[:limit] if limit > 0 else items
        "BODY" if heavy else "BODY_LIGHT"
'''),
    ("caption", "▲ 三处真实用例（todo_page.py / tools_launcher.py / ui_theme.py）"),
    ("note", "为什么 Python 没有 `switch`（以及后来为什么又有了）",
     "老版本里用「`if / elif` 链」或「字典派发」代替。本项目 `main.py` 里"
     "按模块 key 切换到不同页面，用的就是字典 + 显式分支，而不是上百行 `elif`。"
     "3.10 起有了 `match` 语句，但它**不是 C 的 switch**：它是**结构匹配**，"
     "能匹配序列、映射、类实例，也支持 `case _:` 兜底。见 5.6。"),

    ("h2", "5.2 守卫子句：把嵌套压平"),
    ("p", "所谓守卫子句，就是**先把所有「不满足就早点退出」的情况写在函数开头**，"
          "让真正的主逻辑留在最外层。对比一下："),
    ("code", "python", '''# 不推荐：条件一层套一层
def export(items, path):
    if items:
        if path:
            if len(items) > 0:
                # 真正的逻辑被推到第 3 层
                return write(items, path)


# 推荐：先排除掉不成立的情况
def export(items, path):
    if not items:
        return None
    if not path:
        return None
    return write(items, path)
'''),
    ("p", "本项目的 `pending_alerts` 与 `parse_moment` 都是后者："),
    ("code", "python", '''def parse_moment(value) -> Optional[datetime]:
    """把 ``YYYY-MM-DD HH:MM`` 解析为 datetime；非法或空值返回 None。"""
    parts = _norm(value).replace("T", " ").split(" ")
    if len(parts) < 2:
        return None
    day = parse_day(parts[0])
    clock = parts[1].split(":")
    if day is None or len(clock) < 2:
        return None
    try:
        hour, minute = int(clock[0]), int(clock[1][:2])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return datetime(day.year, day.month, day.day, hour, minute)
'''),
    ("caption", "▲ todo_db.py · parse_moment()：五道闸，一道比一道严"),
    ("note", "手工解析而不用 strptime 的原因",
     "`datetime.strptime(\"2026-09-18 9:05\", \"%Y-%m-%d %H:%M\")` 里 `%H` 期望两位小时，"
     "对 `9:05` 这种**非零填充**的写法在部分实现上解析不出来。"
     "手工 `int()` 拆没有这个不确定性，而且能顺手把「小时 25」这种荒谬值一并挡掉。"
     "**当输入是「用户手填 / 别的系统塞进来的」时，宁可自己拆。**"),

    ("h2", "5.3 for 循环与它的好搭档"),
    ("table", [
        ["写法", "用途"],
        ["`for x in seq:`", "直接遍历元素"],
        ["`for i, x in enumerate(seq):`", "同时要下标（可加 `start=1`）"],
        ["`for a, b in zip(xs, ys):`", "并行遍历两个序列（长度不齐时以短的为准）"],
        ["`for k, v in d.items():`", "遍历字典"],
        ["`for line in file:`", "逐行读文件（不要 readlines）"],
        ["`for i in range(n):`", "按次数循环；`range(2, 10, 3)` 支持步长"],
        ["`for x in reversed(seq):`", "倒着来（不复制）"],
    ]),
    ("code", "python", '''    for column, ddl in (
        ("alerted_for", "..."),
        ("snooze_until", "..."),
    ):
        if column not in existing:
            self.conn.execute(ddl)
'''),
    ("caption", "▲ 遍历「二元组序列」时当场解包，是项目里最常用的循环形态"),
    ("warn", "别在遍历列表时删除元素",
     "`for x in items: items.remove(x)` 会**跳过元素**：删除会让后面的元素前移，"
     "而下标继续前进。正确做法是「遍历副本、删原表」"
     "（`for x in list(items): items.remove(x)`），"
     "或者直接重建（`items = [x for x in items if not 要删(x)]`）—— 后者更清楚。"),

    ("h2", "5.4 while 与 break / continue"),
    ("p", "`while` 用于「不知道要循环几次」的场景。本项目里一个典型是"
          "日历推算 —— 从今天起一天天往前找，直到找到那个既不是周末、也不是法定假期的一天："),
    ("code", "python", '''        yield cur
        cur += timedelta(days=1)
'''),
    ("caption", "▲ todo_db.py · 工作日推算器（生成器，用 yield 逐个给出）"),
    ("p", "`break` 立即跳出循环，`continue` 跳到下一次迭代。两者的使用规矩是："
          "**`continue` 尽量放在循环体开头做守卫**，让下半段保持平坦："),
    ("code", "python", '''    for row in rows:
        item = TodoItem.from_row(row)
        moment = alert_moment(item)
        if moment is None or moment > now:
            continue
        text = moment_str(moment)
        # ……下面才是真正要做的事
'''),
    ("caption", "▲ todo_db.py · pending_alerts()：不合格的直接 continue 掉"),
    ("h3", "for 的 else 分支"),
    ("p", "`for` 和 `while` 都可以带 `else`：**循环自然结束时执行，被 `break` 打断时跳过**。"
          "它解决的是「找了一圈没找到」这种情况，省掉一个标志位变量："),
    ("code", "python", '''for item in items:
    if item.id == target:
        print("找到了")
        break
else:
    print("一圈下来没有")      # 只有没 break 过才走到这里
'''),
    ("caption", "▲ 语法示例（本项目暂未使用；知道有这个写法就够）"),

    ("h2", "5.5 海象运算符 :=（3.8+）"),
    ("p", "它允许**在表达式里赋值**，主要价值是省掉一次重复计算。判断标准很明确："
          "**同一个函数调用要写两遍时才有必要用**，否则只会让人多读两眼。"),
    ("code", "python", '''# 不用海象：匹配到要调用两次
m = pattern.search(text)
if m:
    print(m.group(1))

# 用海象：调用一次
if (m := pattern.search(text)):
    print(m.group(1))
'''),
    ("caption", "▲ 典型用法；注意海象赋值处必须加括号"),
    ("note", "本项目基本没用到海象",
     "因为项目的风格是「守卫子句 + 具名中间变量」—— 拆出来的名字本身就有可读性价值，"
     "而海象把赋值藏进条件里，反而更难扫读。**知道它、但不滥用**，是这一节的结论。"),

    ("h2", "5.6 match / case（3.10+）"),
    ("p", "3.10 引入的 `match` 是**结构模式匹配**，比 `switch` 强得多：它可以按位置、"
          "按键、按类型去「拆」一个值，还支持带条件的 `case ... if ...`。"),
    ("code", "python", '''def describe(node):
    match node:
        case {"kind": "module", "key": key}:
            return f"模块 {key}"
        case {"kind": "group", "items": [first, *_]}:
            return f"分组，第一个是 {first}"
        case [x, y]:
            return "二元组"
        case _:
            return "其他"
'''),
    ("caption", "▲ 用项目里 nav_sidebar.NAV_MODEL 那种嵌套字典当输入会很自然（示例由本手册编写）"),
    ("warn", "用不用它，先看运行环境",
     "`match` 需要 **Python 3.10 以上**。本项目当前用 3.12 打包，语法上可用，"
     "但**没有引入** —— 因为 `match` 对这类「字典键判断」的场景并不比显式 "
     "`if node[\"kind\"] == \"module\"` 更清楚，而且要照顾到「读代码的人可能不熟这个新语法」。"
     "**能读懂新语法，和该不该在团队代码里用它，是两件事。**"),
    ("pagebreak",),

    # =========================================================================
    # 第六章
    # =========================================================================
    ("h1", "第六章 函数"),
    ("p", "函数是 Python 里唯一的抽象单位：**它同时是「一段逻辑」和「一个对象」**。"
          "GUI 编程之所以处处是函数，就是因为按钮、绑定、定时器全都要求「传一个可调用对象进来」。"),

    ("h2", "6.1 定义、返回值、多返回值"),
    ("p", "没有 `return` 的函数返回 `None`。要返回多个值时，**返回的是元组**，"
          "调用方解包即可 —— 不需要任何特殊语法："),
    ("code", "python", '''def _resolve_level(level):
    """确定日志级别：显式参数 > 环境变量 > 默认 INFO。"""
    if level is not None:
        return level
    raw = os.environ.get(ENV_LEVEL, "").strip().upper()
    if raw:
        value = getattr(logging, raw, None)
        if isinstance(value, int):
            return value
    return DEFAULT_LEVEL
'''),
    ("caption", "▲ log_setup.py · 三级优先级的兜底写法"),
    ("p", "注意这个函数的返回值**可能是调用方传进来的同一个对象**（`return level`）。"
          "这是有意的：不加工就直接原样传回去，把「判断」和「构造」分开。"),

    ("h2", "6.2 参数的四种形态"),
    ("table", [
        ["形态", "写法", "说明"],
        ["位置参数", "`def f(a, b):`", "按顺序传"],
        ["默认参数", "`def f(a, b=0):`", "**必须在位置参数之后**"],
        ["可变位置", "`def f(*args):`", "`args` 是元组"],
        ["可变关键字", "`def f(**kwargs):`", "`kwargs` 是字典"],
        ["仅关键字", "`def f(a, *, b):`", "`*` 之后的只能用 `b=` 传"],
        ["仅位置", "`def f(a, /, b):`", "`/` 之前的不能按关键字传（3.8+）"],
    ]),
    ("p", "**仅关键字参数**在本项目里用得很刻意。看这个界面组件的构造函数："),
    ("code", "python", '''    def __init__(self, master, *, bg: str, inner_bg: Optional[str] = None):
        super().__init__(master, bg=bg)
        self._bg = bg
'''),
    ("caption", "▲ todo_page.py · ScrollArea.__init__ 的 `*`"),
    ("note", "`*` 是在防止什么",
     "`bg` 与 `inner_bg` 都是颜色字符串，**位置传参时写反了是一个安静的 bug** —— "
     "界面底色和内容底色对调，程序照样跑，只是看起来怪。加上 `*` 之后，"
     "调用处必须写 `ScrollArea(parent, bg=\"#fff\", inner_bg=\"#fafafa\")`，"
     "两个颜色各自带着名字，**顺序就再也不会搞错**。\n"
     "同理 `PendingAlerts` 那种「一次调三个开关」的函数更适合全部改成仅关键字。"),

    ("h2", "6.3 可变默认参数的陷阱（第 4.7 节的正脸）"),
    ("code", "python", '''def add(item, bucket=[]):          # 危险：默认值只在定义时求值一次
    bucket.append(item)
    return bucket


add(1)          # [1]
add(2)          # [1, 2]   <- 上一次的 1 还在
'''),
    ("caption", "▲ 反例（由本手册编写）"),
    ("warn", "根因是「默认值只在定义时求值一次」",
     "函数（和方法）的默认值**在定义时求值一次**，之后所有调用共用同一个对象。\n"
     "所以上面那个空列表会被所有调用共享 —— 往里 append 一次，下次调用它还在。"
     "3.7 节讲的 `field(default_factory=list)` 是同一个坑的 dataclass 版本。\n"
     "**规矩：默认值一律用不可变对象；可变的一律用 `None` 哨兵或工厂函数。**"),
    ("code", "python", '''def build_tree(nodes, seen=None):
    seen = seen if seen is not None else set()      # 每次调用现造一个
    ...
'''),
    ("caption", "▲ 用 None 当哨兵的标准写法"),

    ("h2", "6.4 作用域：LEGB 与闭包"),
    ("p", "Python 找名字的顺序是 **L**ocal → **E**nclosing（外层函数）→ **G**lobal（模块）"
          "→ **B**uiltin（内建）。函数内部**只能读**外层的变量；要写，必须声明 "
          "`global`（写模块级）或 `nonlocal`（写外层函数级）。"),
    ("code", "python", '''_STRIKE_FONTS: dict = {}


def strike_font(base, widget):
    """把元组字体转成带删除线的 ``tkinter.font.Font``。"""
    key = tuple(base)
    cached = _STRIKE_FONTS.get(key)        # 读全局字典：允许
    if cached is not None:
        try:
            cached.actual()
            return cached
        except tk.TclError:
            _STRIKE_FONTS.pop(key, None)   # 改全局字典的内容：也允许
    font = tkfont.Font(root=widget, family=base[0], size=base[1],
                       weight=("bold" if "bold" in styles else "normal"),
                       overstrike=1)
    _STRIKE_FONTS[key] = font              # 仍然是改内容，不是重新赋值
    return font
'''),
    ("caption", "▲ todo_page.py · 模块级缓存 + 函数读写的标准姿势"),
    ("image", "build/todo_shots/05_已完成划线.png", 0.9),
    ("caption", "▲ 完成态的两种标记同时生效：左侧勾选 + 标题文字中间一道删除线。"
                "这道横线只有 `overstrike=1` 的 `Font` 对象画得出来 —— "
                "上面那个字体缓存就是为它服务的。"),
    ("note", "「改字典内容」为什么不需要 nonlocal / global",
     "规则是：**给名字重新赋值**才需要声明；`d[k] = v`、`d.pop(k)`、`lst.append(x)` "
     "都不是重新赋值，它们只是在调用对象自己的方法。所以上面这段完全合法。"
     "如果写成 `_STRIKE_FONTS = {}`（重新绑定这个名字），函数里就必须先声明 `global`，"
     "否则 Python 会在函数内新建一个同名局部变量，外面那个纹丝不动 —— "
     "**这是最安静的一类 bug**。"),

    ("h3", "闭包：函数记住了它出生时的环境"),
    ("code", "python", '''def make_strike_fontter(base):
    """返回一个「把 base 变成带删除线字体」的函数。"""
    cache = {}

    def get(widget):
        font = cache.get(widget)
        if font is None:
            font = tkfont.Font(root=widget, family=base[0], size=base[1],
                               overstrike=1)
            cache[widget] = font
        return font

    return get          # get 记住了 base 和 cache
'''),
    ("caption", "▲ 闭包演示（由本手册编写，用于说明内层函数如何捕获外层变量）"),
    ("code", "python", '''for i in range(3):
    buttons.append(lambda: print(i))      # 三个都会打印 2，不是 0 1 2
'''),
    ("caption", "▲ 反例（由本手册编写）"),
    ("warn", "闭包捕获的是「变量」而不是「当时的值」",
     "三个 lambda 捕获的是**同一个变量 `i`**，循环结束时 `i` 已经是 2，"
     "所以点哪个按钮都打印 2。\n"
     "两种修法：① 用默认参数把当前值**绑死在定义时**，写 `lambda i=i: print(i)`；"
     "② 抽出一个工厂函数，让 `i` 成为那次调用的局部变量。\n"
     "**这个坑在 GUI 里是高频雷区**，因为「循环创建一排按钮」正是最常见的写法。"),
    ("code", "python", '''        for node in nodes:
            self._make_row(node, level=level, kind=kind)

    def _make_row(self, node, *, level, kind):
        """每行都由这个方法独立创建，node 是本次调用的局部变量。"""
        row = tk.Frame(self)
        row.bind("<Button-1>", lambda _e, n=node: self._on_click(n))
'''),
    ("caption", "▲ nav_sidebar.py 的做法：用工厂方法（而非在循环里直接写 lambda）"),
    ("p", "上例中 `lambda _e, n=node: ...` 用了「默认参数绑定」这一招："
          "`n=node` 在**定义时**就把当前的 `node` 存进了函数的默认值里，"
          "之后再怎么循环都与它无关。"),

    ("h2", "6.5 lambda：只配做「一次性小函数」"),
    ("p", "`lambda` 的语法是 `lambda 参数: 表达式`，**函数体必须是一个表达式**，"
          "不能有语句、不能有 return、不能多行。它存在的意义只有一个："
          "**给 `key=`、`command=`、`bind()` 这类要「一个小函数」的地方当场塞一个。**"),
    ("code", "python", '''        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))
        if command is not None:
            self.bind("<Button-1>", self._invoke)
'''),
    ("caption", "▲ ui_components.py · 悬停进出用 lambda，真正的点击回调用具名方法"),
    ("p", "注意这段的分界很讲究：**纯转发一行调用的用 lambda，有实际逻辑的用方法。**"
          "`lambda e: self.set_hover(True)` 一眼就看完，而 `_invoke` 里要做状态判断、"
          "要触发回调、要返回值，所以它有名字。"),
    ("table", [
        ["场景", "选择"],
        ["`key=lambda x: x[0]`", "lambda"],
        ["`command=lambda: self.do(1)`", "lambda"],
        ["需要 try / 多行 / 分支", "写具名函数，再传函数名"],
        ["会被反复调用、需要单元测试", "写具名函数"],
        ["需要 `__name__` 出现在日志里", "写具名函数（lambda 的名字是 `<lambda>`）"],
    ]),

    ("h2", "6.6 函数是对象：回调与高阶函数"),
    ("p", "这是理解 Tkinter 的关键：**`command=on_click` 传的是函数对象本身，"
          "`command=on_click()` 传的是它的返回值** —— 后者会在绑定时立刻调用一次，"
          "然后把返回值（通常是 `None`）当作回调。"),
    ("code", "python", '''        dialog = TodoAlertDialog(
            self, items, db=self.todo_db,
            on_changed=self._after_todo_alert,     # 传函数对象，不加括号
            on_open=self._open_todo_item,
        )
'''),
    ("caption", "▲ main.py · show_todo_alert() · 三个回调全是具名方法"),
    ("p", "常见的更高阶用法还有 `functools.partial` 与把函数放进容器里派发："),
    ("code", "python", '''from functools import partial

# partial：把部分参数先固定住，得到一个新的可调用对象
on_pick = partial(self.set_color, picker, hex_value)
on_pick()          # 等价于 self.set_color(picker, hex_value)

# 派发字典：按 key 找处理函数，比长串 if / elif 清楚
HANDLERS = {
    "module_ops_expiry": self._build_expiry_page,
    "module_life_todo": self._build_todo_page,
}
HANDLERS[key]()'''),
    ("caption", "▲ 由本手册编写；项目中等价的写法见 main.py 的页面切换"),
    ("note", "`__name__` 与 `functools.wraps`",
     "函数对象自带 `__name__`、`__doc__`、`__module__`。写装饰器时如果不把这几个属性"
     "搬过去，被装饰的函数在日志里就会显示成包装函数的名字 —— 本项目的 "
     "`logger.exception` 会带上模块名，所以装饰器一定要用 `functools.wraps`。见 6.7。"),

    ("h2", "6.7 装饰器"),
    ("p", "装饰器就是「**接收一个函数、返回一个新函数**」的函数。`@deco` 写在 `def` 上方，"
          "等价于在这句 `def` 之后执行 `func = deco(func)`。"),
    ("h3", "项目里在用的四种内建装饰器"),
    ("table", [
        ["装饰器", "作用", "项目里的位置"],
        ["`@property`", "把方法伪装成属性，读的时候不加括号", "`TodoItem.due_day`、`ReminderSummary.has_items`"],
        ["`@classmethod`", "第一个参数是类本身（`cls`），常当「备用构造函数」", "`TodoItem.from_row()`、`ToolboxDatabaseAdapter.from_source()`"],
        ["`@staticmethod`", "不接收 `self` / `cls`，只是挂在类名下的普通函数", "`todo_page.py` 里的三个纯函数"],
        ["`@dataclass`", "按注解自动生成 `__init__` / `__repr__` / `__eq__`", "`TodoItem`、`TodoList`、`Typography`、`Palette`"],
    ]),
    ("code", "python", '''@dataclass(frozen=True)
class Typography:
    """字体 token（字号单位为 pt，10pt 约等于 13px）。

    注意：Tk 只支持 normal / bold 两档字重（没有 500），
    因此「只用两种字重」在这一层映射为 normal 与 bold。
    """

    hero: tuple = ("Microsoft YaHei UI", 18)
    page_title: tuple = ("Microsoft YaHei UI", 16)
    title: tuple = ("Microsoft YaHei UI", 11, "bold")
    body: tuple = ("Microsoft YaHei UI", 10)
    caption: tuple = ("Microsoft YaHei UI", 9)
'''),
    ("caption", "▲ ui_theme.py · 用 frozen dataclass 当「常量表」"),
    ("note", "`frozen=True` 换来了什么",
     "冻结之后实例属性不可再赋值，`Typography()` 本身又不可哈希（字段是 tuple 可以），"
     "关键是**它向读代码的人宣告了「这是常量」**。"
     "如果哪天有人写了 `TYPOGRAPHY.body = 12`，会立刻抛 "
     "`FrozenInstanceError`，而不是悄悄改坏全局样式。"),
    ("h3", "自己写一个装饰器"),
    ("code", "python", '''import functools
import time


def timed(logger):
    """记录被装饰函数的耗时。"""

    def deco(func):
        @functools.wraps(func)          # 保住 __name__ / __doc__
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                cost = (time.perf_counter() - start) * 1000
                logger.debug("%s 用了 %.1f ms", func.__name__, cost)

        return wrapper

    return deco


@timed(logger)
def load_workbook(path):
    ...
'''),
    ("caption", "▲ 带参数的装饰器：外三层、里一层"),
    ("warn", "`functools.wraps` 不能省",
     "少了它，被装饰的函数 `__name__` 会变成 `wrapper`、`__doc__` 会变成 `None`。"
     "后果是：日志里看到的全是 `wrapper`，`help()` 查不到文档，"
     "测试里按名字找函数也找不到。**所有手写装饰器都必须带 `functools.wraps`。**"),
    ("code", "python", '''@a
@b
def f(): ...

# 完全等价于
f = a(b(f))
'''),
    ("caption", "▲ 多层装饰器"),
    ("note", "装饰器的执行顺序（从下往上）",
     "离 `def` 最近的那个**先包上**，所以执行顺序是 `b` 先、`a` 后。"
     "记忆口诀是「**从上往下读，从下往上执行**」。"),
    ("pagebreak",),

    # =========================================================================
    # 第七章
    # =========================================================================
    ("h1", "第七章 类与对象"),
    ("p", "本项目的界面全是类：每个页面一个 `class XxxPage(ttk.Frame)`，"
          "每个数据层一个 `class XxxDB`，每个独立窗口一个 `class XxxWindow`。"
          "这一章把类相关的语法一次讲清，并说明项目为什么这么组织。"),

    ("h2", "7.1 class 与 self"),
    ("code", "python", '''class TodoDB:
    """待办模块的数据层。

    用法::

        db = TodoDB(DATA_DIR / "expiry_manager.db")
        lists = db.fetch_lists()
        db.close()

    多个页面共享同一个连接，所以**不要**在这里 commit 之后就 close。
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._holidays_cache: Optional[dict[str, Holiday]] = None

        self.create_tables()
        self.seed_holidays()
        self.seed_default_lists()
'''),
    ("caption", "▲ todo_db.py · 节选（省略了 docstring 中的示例细节）"),
    ("p", "`self` 就是「这个实例本身」，必须显式写在参数表第一位。"
          "**它不是关键字，只是一个约定俗成的名字** —— 但请永远叫它 `self`，"
          "改成别的只会让人皱眉。"),
    ("p", "构造函数里这几行的顺序是有讲究的：**先建连接、先设 `row_factory`、"
          "再建表**。因为 `create_tables()` 内部要用 `self.conn`；"
          "而 `row_factory` 决定了后续所有查询返回的是 `sqlite3.Row` 还是元组 ——"
          "项目里所有 `row[\"name\"]` 这种按列名取值，全靠它。"),
    ("table", [
        ["参数", "含义", "项目里的选择"],
        ["`check_same_thread=False`", "允许连接跨线程使用", "定时器与子线程都要读库"],
        ["`row_factory = sqlite3.Row`", "查询结果可按列名取值", "全项目通用写法"],
        ["`PRAGMA foreign_keys = ON`", "开启外键约束", "SQLite 默认是关的，**必须显式开**"],
    ]),

    ("h2", "7.2 实例属性 vs 类属性"),
    ("table", [
        ["写法", "位置", "存在哪", "改动影响"],
        ["`self.x = 1`", "通常在 `__init__` 里", "每个实例各一份", "只影响该实例"],
        ["`x = 1`", "类体里（方法外）", "所有实例共用一份", "改类属性会影响所有实例"],
    ]),
    ("code", "python", '''class TodoItem:
    # 类属性：这是「字段的默认值」，dataclass 会据此生成 __init__
    id: int = 0
    title: str = ""
    tags: list[str] = field(default_factory=list)
'''),
    ("caption", "▲ todo_db.py · 带注解的类属性被 @dataclass 收编成实例属性"),
    ("warn", "类属性如果是可变对象，就是第 4.7 节的坑",
     "`tags: list = []` 看着像「每个实例一个空列表」，实际是**所有实例共用一个**。"
     "这也是为什么 `field(default_factory=list)` 必须写 —— "
     "dataclass 本身不会帮你把类属性拷贝成实例属性，它只是照抄默认值。"),

    ("h2", "7.3 继承与 super()"),
    ("p", "本项目的继承几乎全部只有一层，而且**全是继承 GUI 框架的基类**："),
    ("code", "python", '''class ScrollArea(tk.Frame):
    def __init__(self, master, *, bg: str, inner_bg: Optional[str] = None):
        super().__init__(master, bg=bg)     # 先让父类把控件建好
        self._bg = bg

        self.vsb = ttk.Scrollbar(self, orient="vertical")
        self.vsb.pack(side="right", fill="y")

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0,
                                yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.configure(command=self.canvas.yview)
'''),
    ("caption", "▲ todo_page.py · ScrollArea"),
    ("ok", "`super().__init__()` 必须在最前面",
     "父类 `tk.Frame.__init__` 负责创建真正的控件对象。在它执行之前，"
     "`self` 还不是一个可用的控件 —— 此时调用 `self.pack()` 或传 `self` 当父容器"
     "都会报 `TclError`。**规矩：子类 `__init__` 第一句永远是 `super().__init__(...)`。**"),
    ("p", "多层继承时 `super()` 会按 MRO（方法解析顺序）找下一个类。"
          "查看顺序用 `ClassName.__mro__`。本项目没用到菱形继承，"
          "所以 `super()` 的效果就是「父类」——但**仍然要用 `super()` 而不是 "
          "`tk.Frame.__init__(self, ...)`**，因为将来插入中间类时前者自动适配。"),

    ("h2", "7.4 property：把方法当属性读"),
    ("code", "python", '''@dataclass
class TodoItem:
    # -- 展示辅助 ------------------------------------------------------
    @property
    def due_day(self) -> Optional[date]:
        """截止日期的 date 形式；未设置时返回 None。"""
        return parse_day(self.due_date)

    @property
    def priority_mark(self) -> str:
        return PRIORITY_MARKS.get(self.priority, "")

    @property
    def repeat_label(self) -> str:
        return REPEAT_LABELS.get(self.repeat_rule, "永不")
'''),
    ("caption", "▲ todo_db.py · TodoItem 的三个计算属性"),
    ("p", "调用处因此变得很干净：`item.repeat_label` 而不是 `item.repeat_label()`。"
          "**判断该不该用 property 的标准是「它像不像一个属性」** —— "
          "「这条待办重复吗」是属性，「把这条待办推进到下一周期」是动作，"
          "后者必须是方法（项目里叫 `advance_repeat` 之类）。"),
    ("h3", "只读 property 与可写 property"),
    ("code", "python", '''class Node:
    def __init__(self):
        self._active = False

    @property
    def is_active(self) -> bool:          # 读
        return self._active

    @is_active.setter
    def is_active(self, value: bool):     # 写（名字必须是 <属性名>.setter）
        self._active = bool(value)
        self._paint()
'''),
    ("caption", "▲ 由本手册编写；ui_components.py 里是把读写拆成 is_active 属性 + set_active() 方法"),
    ("note", "项目里为什么不给每个属性都配 setter",
     "`ui_components.py` 里只定义了 `@property is_active`（只读），"
     "写用的是具名方法 `set_active(value)`。原因：**setter 会让「赋值」看起来是免费的，"
     "而这里赋值要触发重绘**。改成方法后，调用方一眼看得出「这一步有副作用」。"
     "凡是「写」会引发别的事情（重绘、落库、发通知）的地方，都不该用 setter。"),

    ("h2", "7.5 classmethod 与 staticmethod"),
    ("code", "python", '''@dataclass
class TodoList:
    id: int = 0
    name: str = ""
    color: str = DEFAULT_LIST_COLOR

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TodoList":
        return cls(
            id=int(row["id"]),
            name=_norm(row["name"]),
            color=_norm(row["color"]) or DEFAULT_LIST_COLOR,
            sort_order=int(row["sort_order"] or 0),
        )
'''),
    ("caption", "▲ todo_db.py · from_row() 是典型的「备用构造函数」"),
    ("table", [
        ["", "第一个参数", "调用方式", "典型用途"],
        ["普通方法", "`self`", "`obj.m()`", "需要访问实例状态"],
        ["`@classmethod`", "`cls`", "`Cls.m()` 或 `obj.m()`", "备用构造函数；工厂"],
        ["`@staticmethod`", "无", "`Cls.m()`", "逻辑上属于这个类、但不需要实例"],
    ]),
    ("note", "`from_row` 用 `cls` 而不是 `TodoList` 的原因",
     "`cls(...)` 会在子类调用时自动构造子类实例。如果写死 `TodoList(...)`，"
     "将来继承出一个 `TodoItemExt` 再调 `TodoItemExt.from_row(row)`，"
     "拿到的却是一个 `TodoList` —— 这类 bug 非常难找。**工厂方法一律用 `cls`。**"),
    ("code", "python", '''class ToolboxDatabaseAdapter:
    """系统工具箱数据库适配器，统一收口原始 sqlite 连接的传递方式。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @classmethod
    def from_source(cls, db_source):
        if isinstance(db_source, cls):
            return db_source                 # 已经是适配器，原样返回
        if hasattr(db_source, "conn"):
            return cls(db_source.conn)       # 传进来的是上层 DB 对象
        return cls(db_source)                # 传进来的是裸连接

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn
'''),
    ("caption", "▲ tools_db.py · 兼容三种入参的适配器工厂"),
    ("p", "`isinstance(db_source, cls)` 这一句是**幂等**的关键："
          "同一个适配器被传进去两次，第二次原样返回，不会套娃。"),

    ("h2", "7.6 魔术方法：让自定义对象融入语言"),
    ("p", "魔术方法（dunder methods）是「用自定义类去接语言的操作符」的钩子。"
          "本项目实际用到的不多，但都用在了点子上："),
    ("table", [
        ["魔术方法", "什么时候被调用", "项目里的位置"],
        ["`__init__`", "构造实例", "随处可见"],
        ["`__repr__`", "`repr(obj)`、调试器窗口、打印列表", "dataclass 自动生成"],
        ["`__eq__`", "`==` 比较", "dataclass 自动生成（按字段逐一比）"],
        ["`__enter__` / `__exit__`", "`with` 语句进入 / 退出", "数据库连接的上下文管理"],
        ["`__iter__`", "`for x in obj`", "工作日推算器"],
        ["`__len__`", "`len(obj)`", "容器类组件"],
        ["`__getitem__`", "`obj[key]`", "行数据包装"],
    ]),
    ("code", "python", '''import sqlite3
from contextlib import contextmanager


@contextmanager
def connect(db_path):
    """with 写法：无论正常结束还是抛异常，连接都会被关掉。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


with connect(DATA_DIR / "expiry_manager.db") as conn:
    rows = conn.execute("SELECT * FROM accounts").fetchall()
'''),
    ("caption", "▲ 由本手册编写；项目里 todos 用的是「长连接 + 显式 close」，见下方说明"),
    ("note", "项目为什么没用 with 管连接",
     "因为待办模块的连接是**跨页面、跨定时器共享的长期连接**"
     "（`todo_alert_check` 每 30 秒要用一次，提醒窗里点「完成」也要用）。"
     "每次操作都开关一次连接，在 SQLite 上意味着反复做文件级加锁，"
     "既慢又容易撞上 `database is locked`。\n"
     "**`with` 适合「用完即弃」的资源（临时文件、一次性查询），"
     "不适合长生命周期对象。** 判断标准是：这个资源的生命周期跟「一次操作」对齐，"
     "还是跟「整个程序」对齐。"),
    ("h3", "`__repr__` 为什么值钱"),
    ("p", "`@dataclass` 会自动生成 `__repr__`，于是打印一条待办长这样："
          "`TodoItem(id=7, title='交房租', due_date='2026-09-25', ...)`。"
          "**调试时能直接看到字段名，比看 `(7, 3, '交房租', '')` 强太多** —— "
          "这是项目大量使用 dataclass 的直接收益之一。"),

    ("h2", "7.7 dataclass：数据类的标准做法"),
    ("code", "python", '''@dataclass
class ReminderSummary:
    """到期提醒摘要数据类。

    属性:
      overdue:  已过期资产列表
      due_15:   15 天内到期资产列表（同结构）
      due_30:   30 天内到期资产列表（同结构）

    方法:
      has_items -> bool  返回是否还有需要提醒的资产
    """
    overdue: list
    due_15: list
    due_30: list

    @property
    def has_items(self) -> bool:
        return bool(self.overdue or self.due_15 or self.due_30)
'''),
    ("caption", "▲ main.py · ReminderSummary"),
    ("table", [
        ["参数", "作用"],
        ["`@dataclass`", "按注解生成 `__init__` / `__repr__` / `__eq__`"],
        ["`frozen=True`", "不可变；赋值抛 `FrozenInstanceError`"],
        ["`eq=False`", "不生成 `__eq__`（想用「同一性」比较时）"],
        ["`order=True`", "生成 `<` `>` 等比较方法（按字段顺序比）"],
        ["`slots=True`", "生成 `__slots__`，省内存、防手滑加属性（3.10+）"],
        ["`field(default=...)`", "给字段加额外设置"],
        ["`field(default_factory=list)`", "**可变默认值必须用它**"],
        ["`field(compare=False)`", "参与比较时忽略该字段"],
        ["`field(repr=False)`", "打印时不显示（密码之类）"],
    ]),
    ("warn", "给 dataclass 加字段一定要带默认值",
     "项目的 `TodoItem` 有 24 个字段，每个都有默认值。原因是"
     "**只要有一个字段没默认值，所有 `TodoItem(...)` 的调用点都必须补上它** ——"
     "而调用点在数据层与界面层一共有几十处。带默认值之后，新增字段"
     "（`alerted_for`、`snooze_until` 就是这么加的）只需要动 dataclass 定义本身，"
     "其它代码一行都不用改。\n"
     "**代价是字段顺序变得重要**：位置传参会按声明顺序对号入座。所以项目里所有 "
     "`TodoItem(...)` 都用关键字传参。"),
    ("note", "dataclass 与 NamedTuple、普通的类怎么选",
     "**数据为主、没有行为** → `@dataclass`。**不可变、还要能当字典键** → "
     "`NamedTuple` 或 `frozen=True` 的 dataclass。"
     "**有明显的状态与行为** → 普通类（比如 `TodoDB`、`ScrollArea`）。"
     "本项目的 `TodoDB` 虽然是「数据层」，但它是**行为的集合**，"
     "所以是普通类而不是 dataclass。"),

    ("h2", "7.8 组合优于继承：本项目的分层就靠它"),
    ("p", "本项目只有「页面继承框架基类」这一种继承，其余关系全部是**组合** —— "
          "对象把别的对象当零件用："),
    ("out", """ExpiryManagerApp（主窗口）
   ├── self.todo_db     = TodoDB(...)          # 数据
   ├── self.todo_view   = TodoPage(...)        # 界面
   ├── self.tray        = TrayController(...)  # 托盘
   └── self.todo_view 也持有 self.todo_db（注入）"""),
    ("caption", "▲ 组合关系（真实字段名以 main.py 为准）"),
    ("p", "组合的好处在这里很具体：**`TodoPage` 只认「一个长得像 TodoDB 的东西」**，"
          "所以测试时塞一个替身进去就能跑界面测试，完全不需要真数据库。"
          "如果用继承（`class TodoPage(TodoDB)`），页面和数据就焊死了。"),
    ("ok", "拿不准时的判断标准",
     "问一句「**A 是不是一种 B**」。`TodoPage` 是一种 `tk.Frame` 吗？是 —— 用继承。"
     "`TodoPage` 是一种 `TodoDB` 吗？不是，它是**用一个** `TodoDB` —— 用组合。"
     "这条「is-a / has-a」的判断在 90% 的情况下够用。"),
    ("pagebreak",),
]
