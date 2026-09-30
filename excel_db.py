# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 数据层
================================================================================
分层约定与 ``todo_db`` / ``process_db`` 一致：**本模块只管数据与规则，不碰界面**。
好处是测试能脱离 tkinter 跑（``scripts/test_excel.py`` 是纯数据层套件，
在便携版 Python 上也能过），而界面层 ``excel_page`` 只消费这里的方法。

六张表
--------------------------------------------------------------------------------
``excel_functions``  函数库。内置 200 条 + 你自己加的；``code`` 唯一，种子靠它幂等。
``excel_progress``   掌握度与复习状态，1:1 挂在函数上（**懒创建**，没学过的函数不占行）。
``excel_recipes``    20 条实战配方（组合套路），也能写自己的心得。
``excel_notes``      我的笔记：可挂书页、可挂函数、可带截图。
``excel_checkins``   打卡：一天一行，``check_date`` 唯一。
``excel_quiz_log``   自测流水：每答一题一行，错题本与正确率都从它算（P1 新增）。

三条设计取舍，值得写下来
--------------------------------------------------------------------------------
**1. 掌握度独立成表，而不是加在 ``excel_functions`` 上。**
   种子每次启动都会 ``INSERT OR IGNORE`` 走一遍，函数表是「种子说了算」的；
   而进度是「你说了算」的。两者分开，升级版本重建种子时进度不会丢，
   也不会因为种子里多一条少一条而把进度错位。

**2. 复习间隔用「连对次数查表」，不实现完整 SM-2。**
   完整 SM-2 要维护难度因子 EF，参数一多就没人愿意点。
   这里用 ``1 / 3 / 7 / 15 / 30 / 60 / 120`` 天七档：
   连续答对就往后跳一档，模糊就砍半，忘了就回到 1 天。
   规则简单到能背，才可能真的天天用。

**3. 自测只存「流水」，不存「题库」。**
   题干是从函数本身推出来的（场景 + 语法 + 示例），存一遍等于给同一份数据
   留第二个副本。库里只留你答了什么（``excel_quiz_log``），题干按出题当时的
   样子快照进去 —— 以后改了函数，老记录也不会跟着变。
"""

from __future__ import annotations

import csv
import io
import logging
import random
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import db_backup
from excel_seed import CATEGORIES, LEARNING_PATHS, SEED_FUNCTIONS, SEED_RECIPES

logger = logging.getLogger(__name__)

# ======================================================================
# 常量
# ======================================================================
MASTERY_NEW = 0        # 未学
MASTERY_WEAK = 1       # 生疏
MASTERY_FAIR = 2       # 一般
MASTERY_GOOD = 3       # 熟练
MASTERY_CHOICES = (
    (MASTERY_NEW, "未学"),
    (MASTERY_WEAK, "生疏"),
    (MASTERY_FAIR, "一般"),
    (MASTERY_GOOD, "熟练"),
)
MASTERY_LABELS = dict(MASTERY_CHOICES)

# 颜色取 MAIN_PALETTE 的同一套语气：灰 / 红 / 琥珀 / 绿
MASTERY_COLORS = {
    MASTERY_NEW: "#c9c9c9",
    MASTERY_WEAK: "#a3372f",
    MASTERY_FAIR: "#8a6a2f",
    MASTERY_GOOD: "#2e6b46",
}

DIFFICULTY_LABELS = {1: "入门", 2: "常用", 3: "进阶", 4: "高级"}
IMPORTANCE_LABELS = {1: "了解", 2: "常用", 3: "核心"}

# 复习反馈
FEEDBACK_KNOWN = "known"    # 熟练
FEEDBACK_VAGUE = "vague"    # 模糊
FEEDBACK_FORGOT = "forgot"  # 忘了
FEEDBACK_CHOICES = (
    (FEEDBACK_KNOWN, "熟练"),
    (FEEDBACK_VAGUE, "模糊"),
    (FEEDBACK_FORGOT, "忘了"),
)

# 连续答对 1..7 次对应的复习间隔（天）。第 8 次起维持最后一档。
SRS_INTERVALS = (1, 3, 7, 15, 30, 60, 120)

# 详情页里「我的理解」是就地编辑的，可改的字段白名单就在这里
EDITABLE_FUNCTION_FIELDS = ("book_page", "my_note")
EDITABLE_RECIPE_FIELDS = ("book_page", "my_note")


# ----------------------------------------------------------------------
# 自测出题（P1）
# ----------------------------------------------------------------------
# 为什么题目不额外建表存：题干是从函数本身推出来的（场景 + 语法 + 示例），
# 存一遍就等于给同一份数据留了第二个副本，改一处忘一处。
# 库里只留「你答了什么」的流水（``excel_quiz_log``），题干按当时的样子快照进去。
QUIZ_CHOICE = "choice"      # 看场景选函数：机器判分
QUIZ_FORMULA = "formula"    # 给场景写公式：写完自评
QUIZ_TYPE_LABELS = {QUIZ_CHOICE: "选函数", QUIZ_FORMULA: "写公式"}

QUIZ_MODE_MIXED = "mixed"
QUIZ_MODE_CHOICES = (
    (QUIZ_MODE_MIXED, "混合出题"),
    (QUIZ_CHOICE, "只出选择题"),
    (QUIZ_FORMULA, "只出写公式"),
)

# 一轮几题：10 题大约三五分钟，是「顺手做一下」还愿意做的上限。
QUIZ_BATCH = 10
# 选择题选项数 = 1 个答案 + (QUIZ_OPTION_COUNT - 1) 个干扰项
QUIZ_OPTION_COUNT = 4
# 错题本一次最多列多少条，再多就该靠分类筛了
QUIZ_WRONG_LIMIT = 50

# 「最近一轮」的分界：相邻两次作答隔了这么久就算换了一轮。
# 45 分钟是按真实节奏估的 —— 一轮 10 题顺手做完几分钟，中途去开会、
# 吃个饭回来就不该算同一轮了。宽松一点没关系，宁可多带上一两道。
QUIZ_ROUND_GAP_MINUTES = 45
# 从流水里捞「最近一轮」时最多往回读多少行（防呆上限，不是业务阈值）
QUIZ_LOOKBACK = 80

# ----------------------------------------------------------------------
# CSV / Excel 批量导入（P1）
# ----------------------------------------------------------------------
# 模板列顺序 = 这里的顺序；``True`` 表示必填（模板列头会加 ``*`` 前缀）。
IMPORT_COLUMNS = (
    ("code", True),
    ("name_cn", True),
    ("category", True),
    ("syntax", True),
    ("description", True),
    ("args_desc", False),
    ("returns", False),
    ("example_formula", False),
    ("example_result", False),
    ("pitfalls", False),
    ("use_cases", False),
    ("related", False),
    ("tags", False),
    ("min_version", False),
    ("difficulty", False),
    ("importance", False),
    ("book_page", False),
    ("my_note", False),
)

# 列头别名：中文表头也认，省得为了导入把自己表里的列名改一遍。
# 比对前会去掉首尾空白、去掉模板里常见的前导 ``*``、去掉内部空白，再转小写。
IMPORT_HEADER_ALIASES = {
    "code": ("code", "函数", "函数名", "函数名code"),
    "name_cn": ("name_cn", "中文名", "中文名称", "别名"),
    "category": ("category", "分类", "类别", "官方分类"),
    "syntax": ("syntax", "语法", "语法原型"),
    "description": ("description", "用途", "一句话", "一句话用途", "说明"),
    "args_desc": ("args_desc", "参数", "参数说明"),
    "returns": ("returns", "返回值", "返回"),
    "example_formula": ("example_formula", "示例", "示例公式", "例子"),
    "example_result": ("example_result", "示例结果", "期望结果", "结果"),
    "pitfalls": ("pitfalls", "易错点", "注意", "坑"),
    "use_cases": ("use_cases", "适用场景", "场景", "用途场景"),
    "related": ("related", "相关函数", "相关"),
    "tags": ("tags", "标签"),
    "min_version": ("min_version", "最低版本", "版本"),
    "difficulty": ("difficulty", "难度"),
    "importance": ("importance", "重要度", "重要性"),
    "book_page": ("book_page", "书页", "书页码", "页码"),
    "my_note": ("my_note", "我的理解", "笔记", "心得"),
}

# 导入能改的字段白名单。``is_builtin`` / ``sort_order`` 一律不给碰 ——
# 前者决定「这条能不能删」，后者是课程顺序，都不是导入该管的事。
IMPORT_WRITABLE_FIELDS = (
    "name_cn", "category", "tags", "syntax", "args_desc", "returns",
    "description", "example_formula", "example_result", "pitfalls",
    "use_cases", "related", "min_version", "difficulty", "importance",
    "book_page", "my_note",
)

# 走 openpyxl 的后缀；其余（.csv / .tsv / .txt）按 CSV 解析
IMPORT_EXCEL_SUFFIXES = (".xlsx", ".xlsm")

# 官方 12 类之外的自定义分类会被提示一句，但仍允许入库
CATEGORY_NAMES = tuple(item["name"] for item in CATEGORIES)
# ``**强调**``：种子正文里的 Markdown 标记，上屏 / 出题前统一剥掉
EMPHASIS_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
# ``use_cases`` 是「；分隔的场景串」，中英文分号都要认
SCENARIO_SPLIT_RE = re.compile(r"[；;]")

# ======================================================================
# DDL
# ======================================================================
TABLE_FUNCTIONS = """
CREATE TABLE IF NOT EXISTS excel_functions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT    NOT NULL UNIQUE,
    name_cn        TEXT    NOT NULL DEFAULT '',
    category       TEXT    NOT NULL DEFAULT '',
    tags           TEXT    NOT NULL DEFAULT '',
    syntax         TEXT    NOT NULL DEFAULT '',
    args_desc      TEXT    NOT NULL DEFAULT '',
    returns        TEXT    NOT NULL DEFAULT '',
    description    TEXT    NOT NULL DEFAULT '',
    example_formula TEXT   NOT NULL DEFAULT '',
    example_result TEXT    NOT NULL DEFAULT '',
    pitfalls       TEXT    NOT NULL DEFAULT '',
    use_cases      TEXT    NOT NULL DEFAULT '',
    related        TEXT    NOT NULL DEFAULT '',
    min_version    TEXT    NOT NULL DEFAULT '',
    difficulty     INTEGER NOT NULL DEFAULT 2,
    importance     INTEGER NOT NULL DEFAULT 2,
    book_page      TEXT    NOT NULL DEFAULT '',
    my_note        TEXT    NOT NULL DEFAULT '',
    is_builtin     INTEGER NOT NULL DEFAULT 0,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL DEFAULT '',
    updated_at     TEXT    NOT NULL DEFAULT ''
)
"""

TABLE_PROGRESS = """
CREATE TABLE IF NOT EXISTS excel_progress (
    function_id     INTEGER PRIMARY KEY,
    mastery         INTEGER NOT NULL DEFAULT 0,
    review_count    INTEGER NOT NULL DEFAULT 0,
    correct_streak  INTEGER NOT NULL DEFAULT 0,
    interval_days   INTEGER NOT NULL DEFAULT 0,
    last_review_at  TEXT    NOT NULL DEFAULT '',
    next_review_at  TEXT    NOT NULL DEFAULT '',
    marked_at       TEXT    NOT NULL DEFAULT ''
)
"""

TABLE_RECIPES = """
CREATE TABLE IF NOT EXISTS excel_recipes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL UNIQUE,
    scene       TEXT    NOT NULL DEFAULT '',
    category    TEXT    NOT NULL DEFAULT '',
    formula     TEXT    NOT NULL DEFAULT '',
    breakdown   TEXT    NOT NULL DEFAULT '',
    pitfalls    TEXT    NOT NULL DEFAULT '',
    related     TEXT    NOT NULL DEFAULT '',
    difficulty  INTEGER NOT NULL DEFAULT 2,
    book_page   TEXT    NOT NULL DEFAULT '',
    my_note     TEXT    NOT NULL DEFAULT '',
    is_builtin  INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT    NOT NULL DEFAULT ''
)
"""

TABLE_NOTES = """
CREATE TABLE IF NOT EXISTS excel_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL DEFAULT '',
    book_page   TEXT    NOT NULL DEFAULT '',
    function_id INTEGER,
    content     TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '',
    images      TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT    NOT NULL DEFAULT ''
)
"""

TABLE_CHECKINS = """
CREATE TABLE IF NOT EXISTS excel_checkins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    check_date  TEXT    NOT NULL UNIQUE,
    minutes     INTEGER NOT NULL DEFAULT 0,
    reviewed    INTEGER NOT NULL DEFAULT 0,
    learned     INTEGER NOT NULL DEFAULT 0,
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT ''
)
"""

TABLE_QUIZ_LOG = """
CREATE TABLE IF NOT EXISTS excel_quiz_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    function_id INTEGER NOT NULL DEFAULT 0,
    quiz_type   TEXT    NOT NULL DEFAULT 'choice',
    prompt      TEXT    NOT NULL DEFAULT '',
    answer      TEXT    NOT NULL DEFAULT '',
    user_answer TEXT    NOT NULL DEFAULT '',
    is_correct  INTEGER NOT NULL DEFAULT 0,
    category    TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT '',
    retried     INTEGER NOT NULL DEFAULT 0,
    retried_at  TEXT    NOT NULL DEFAULT ''
)
"""

# 错题本按「没错对 + 没订正」筛，量大时全表扫会钝，给它一条索引
TABLE_QUIZ_WRONG_INDEX = """
CREATE INDEX IF NOT EXISTS idx_excel_quiz_log_wrong
    ON excel_quiz_log (is_correct, retried, id)
"""

TABLES = (
    TABLE_FUNCTIONS,
    TABLE_PROGRESS,
    TABLE_RECIPES,
    TABLE_NOTES,
    TABLE_CHECKINS,
    TABLE_QUIZ_LOG,
    TABLE_QUIZ_WRONG_INDEX,
)
# 建表之后可能新增的列（存量库升级用）。列名 → 列定义。
FUNCTION_EXTRA_COLUMNS = {
    "book_page": "TEXT NOT NULL DEFAULT ''",
    "my_note": "TEXT NOT NULL DEFAULT ''",
}
RECIPE_EXTRA_COLUMNS = {
    "book_page": "TEXT NOT NULL DEFAULT ''",
    "my_note": "TEXT NOT NULL DEFAULT ''",
}
NOTE_EXTRA_COLUMNS = {
    "images": "TEXT NOT NULL DEFAULT ''",
    "tags": "TEXT NOT NULL DEFAULT ''",
}


# ======================================================================
# 小工具（纯函数，测试直接打这里）
# ======================================================================
def today_str() -> str:
    """今天的 ISO 日期串。全模块统一用它取「今天」，测试才好固定时间。"""
    return date.today().isoformat()


def parse_date(value) -> date | None:
    """把 ``YYYY-MM-DD`` 之类的串解析成 date；解析不了返回 None。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def shift_date(value, days: int) -> str:
    """把日期串往后推 ``days`` 天（负数往前），返回 ISO 串。"""
    base = parse_date(value) or date.today()
    return (base + timedelta(days=int(days))).isoformat()


def interval_for(streak: int) -> int:
    """连续答对 ``streak`` 次之后，下次该隔多少天再来。"""
    index = max(0, min(int(streak) - 1, len(SRS_INTERVALS) - 1))
    return SRS_INTERVALS[index]


def review_next_state(mastery: int, streak: int, interval: int, feedback: str) -> dict:
    """按反馈算出新的「掌握度 / 连对次数 / 间隔」。**纯函数，不落库。**

    三键的规则（写在设计文档里，这里保持一致）：
      熟练 → 掌握度 +1（最高 3），连对 +1，间隔按连对档位往后跳
      模糊 → 掌握度不变（**但至少落个「生疏」**，否则「没学过」会一直是没学过），
             连对 -1，间隔砍半（最低 1 天）
      忘了 → 掌握度 -1（最低 1），连对归零，间隔回到 1 天
    """
    mastery = max(MASTERY_NEW, min(MASTERY_GOOD, int(mastery)))
    streak = max(0, int(streak))
    interval = max(0, int(interval))

    if feedback == FEEDBACK_KNOWN:
        mastery = min(MASTERY_GOOD, mastery + 1)
        streak += 1
        interval = interval_for(streak)
    elif feedback == FEEDBACK_VAGUE:
        # 「模糊」也是学过了：万一之前是未学，至少落个生疏，否则会显示成「没学过」
        mastery = max(MASTERY_WEAK, mastery)
        streak = max(0, streak - 1)
        interval = max(1, interval // 2) if interval else 1
    else:  # FEEDBACK_FORGOT
        mastery = max(MASTERY_WEAK, mastery - 1)
        streak = 0
        interval = 1

    return {"mastery": mastery, "correct_streak": streak, "interval_days": interval}


def mastery_label(value) -> str:
    return MASTERY_LABELS.get(int(value or 0), "未学")


def mastery_color(value) -> str:
    return MASTERY_COLORS.get(int(value or 0), MASTERY_COLORS[MASTERY_NEW])


def difficulty_label(value) -> str:
    return DIFFICULTY_LABELS.get(int(value or 2), "常用")


def importance_label(value) -> str:
    return IMPORTANCE_LABELS.get(int(value or 2), "常用")


def function_search_blob(item: dict) -> str:
    """把一条函数摊成一段用于检索的小写文本。

    检索面覆盖「你脑子里可能出现的词」：函数名、中文名、用途描述、适用场景、
    示例公式、易错点、相关函数。这样「把两张表对起来」也能命中 VLOOKUP ——
    因为它的 ``use_cases`` 里写着「两张表按主键对齐」。
    """
    keys = ("code", "name_cn", "category", "tags", "syntax", "args_desc",
            "description", "use_cases", "example_formula", "example_result",
            "pitfalls", "related", "min_version")
    return "\n".join(str(item.get(key, "")) for key in keys).lower()


def match_keyword(blob: str, keyword: str) -> bool:
    """关键词全部命中才算匹配（按空白切词，所以「查找 反向」能一起缩小范围）。"""
    tokens = str(keyword or "").lower().split()
    if not tokens:
        return True
    return all(token in blob for token in tokens)


# 相关函数 / 配方关联的书写分隔符。与工具箱的标签约定保持一致
# （``tools_launcher.TAG_SEPARATOR_RE``）：内置种子只用 ``|``，
# 但用户手写的自定义函数很可能打逗号或顿号，这里一并收。
CODE_SEPARATOR_RE = re.compile(r"[|｜,，、;；\s]+")


def split_codes(text) -> list[str]:
    """把 `related` 这类字段拆成函数名列表（去空段、保持原顺序、不重复）。"""
    raw = "" if text is None else str(text)
    codes: list[str] = []
    seen: set[str] = set()
    for part in CODE_SEPARATOR_RE.split(raw):
        code = part.strip()
        if not code:
            continue
        key = code.upper()
        if key in seen:
            continue
        seen.add(key)
        codes.append(code)
    return codes


def compute_streak(day_list, today=None) -> int:
    """连续打卡天数。

    规则：从「今天」往回数。**今天还没打卡不清零** —— 从昨天开始数，
    否则每天零点一过，所有人的连续天数都会变成 0，看着很像 bug。
    """
    days = {d for d in (str(x).strip() for x in day_list) if d}
    if not days:
        return 0
    anchor = parse_date(today) or date.today()
    if anchor.isoformat() not in days:
        anchor = anchor - timedelta(days=1)
    count = 0
    cursor = anchor
    while cursor.isoformat() in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def longest_streak(day_list) -> int:
    """历史最长连续打卡天数。"""
    days = sorted({parse_date(d) for d in day_list if parse_date(d)})
    if not days:
        return 0
    best = 1
    run = 1
    for previous, current in zip(days, days[1:]):
        if (current - previous).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def category_stats(functions, progress) -> list[dict]:
    """按分类统计「总数 / 已学 / 熟练」，顺序跟随 ``CATEGORIES``。"""
    buckets: dict[str, dict] = {}
    for item in functions:
        bucket = buckets.setdefault(
            item["category"], {"name": item["category"], "total": 0, "learned": 0, "good": 0}
        )
        bucket["total"] += 1
        mastery = int((progress.get(item["id"]) or {}).get("mastery", 0) or 0)
        if mastery >= MASTERY_WEAK:
            bucket["learned"] += 1
        if mastery >= MASTERY_GOOD:
            bucket["good"] += 1
    ordered: list[dict] = []
    seen: set[str] = set()
    for meta in CATEGORIES:
        name = meta["name"]
        seen.add(name)
        bucket = buckets.pop(name, None)
        if bucket is None:
            bucket = {"name": name, "total": 0, "learned": 0, "good": 0}
        bucket["desc"] = meta.get("desc", "")
        bucket["percent"] = round(bucket["learned"] * 100 / bucket["total"]) if bucket["total"] else 0
        ordered.append(bucket)
    for name in sorted(buckets):
        bucket = buckets[name]
        bucket["desc"] = ""
        bucket["percent"] = round(bucket["learned"] * 100 / bucket["total"]) if bucket["total"] else 0
        ordered.append(bucket)
    return ordered


def path_progress(path: dict, functions_by_code: dict, progress: dict) -> dict:
    """算一个学习阶段的进度。``codes`` 缺省时表示这一阶段是「配方阶段」。"""
    codes = [c for c in (path.get("codes") or []) if c in functions_by_code]
    total = len(codes)
    learned = 0
    good = 0
    for code in codes:
        function_id = functions_by_code[code]["id"]
        mastery = int((progress.get(function_id) or {}).get("mastery", 0) or 0)
        if mastery >= MASTERY_WEAK:
            learned += 1
        if mastery >= MASTERY_GOOD:
            good += 1
    percent = round(good * 100 / total) if total else 0
    return {
        "key": path.get("key", ""),
        "title": path.get("title", ""),
        "goal": path.get("goal", ""),
        "tip": path.get("tip", ""),
        "codes": codes,
        "is_recipe_stage": bool(path.get("recipes")) or not codes,
        "total": total,
        "learned": learned,
        "good": good,
        "percent": percent,
    }


# ======================================================================
# 自测出题（纯函数，测试直接打这里）
# ======================================================================
def strip_emphasis(text) -> str:
    """剥掉种子正文里的 ``**强调**`` 标记。

    种子里的 ``**`` 是留给 Markdown 导出用的；而 Tk 的 ``Label`` 不支持富文本，
    直接贴上去会显示出字面的两个星号。**出题会把正文抄进题干，所以这一步
    必须在数据层做** —— 挂在界面层的话，同一段文字就有了两条清理路径，
    迟早会有一边忘掉。
    """
    return EMPHASIS_RE.sub(r"\1", str(text or ""))


def scenario_sentences(text, *, limit=None) -> list[str]:
    """把 ``use_cases`` 这种「；分隔的场景串」拆成一句一句。"""
    parts = [strip_emphasis(part).strip()
             for part in SCENARIO_SPLIT_RE.split(str(text or ""))]
    parts = [part for part in parts if part]
    if limit is not None:
        parts = parts[: max(0, int(limit))]
    return parts


def mask_code(text, code) -> str:
    """把题干里出现的函数名换成「这个函数」。

    不做这一步的话，有些函数的 ``description`` 里就写着它自己的名字，
    等于把答案印在题面上。用前后 lookaround 而不是 ``\\b``：``IF``
    不该在 ``IFERROR`` 里被替换掉。
    """
    token = str(code or "").strip()
    if not token:
        return str(text or "")
    pattern = rf"(?i)(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
    return re.sub(pattern, "这个函数", str(text or ""))


def quiz_prompt(target: dict, *, quiz_type: str) -> str:
    """把一条函数摊成题干。**只出题，不给答案。**

    ``quiz_type`` 决定要不要给函数名打码：选择题必须打（不然答案就印在题面上），
    写公式题本来就告诉了你用哪个函数，打了反而变出「这个函数 的通用写法」
    这种别扭话。
    """
    code = target.get("code", "")
    hide = quiz_type == QUIZ_CHOICE
    blocks: list[str] = []
    headline = strip_emphasis(target.get("description", "")).strip()
    if hide:
        headline = mask_code(headline, code)
    if headline:
        blocks.append(headline)
    for sentence in scenario_sentences(target.get("use_cases", ""), limit=2):
        masked = mask_code(sentence, code) if hide else sentence
        if masked:
            blocks.append("· " + masked)
    if quiz_type == QUIZ_FORMULA and str(target.get("syntax", "")).strip():
        blocks.append("语法原型：" + str(target["syntax"]).strip())
    return "\n".join(blocks).strip()


def _question_payload(target: dict, quiz_type: str, prompt: str,
                      options=None, answer: str = "") -> dict:
    """题干 + 「答完之后才揭晓」的那些字段。

    揭晓字段在**答题前界面不许用** —— 界面只在判完分后渲染它们。
    这样就不用为答案另建一张表：答案本来就在函数里。
    """
    return {
        "function_id": int(target.get("id") or 0),
        "code": str(target.get("code", "")).strip(),
        "name_cn": target.get("name_cn", ""),
        "category": target.get("category", ""),
        "quiz_type": quiz_type,
        "prompt": prompt,
        "options": list(options or []),
        "answer": answer,
        "syntax": str(target.get("syntax", "")).strip(),
        "reveal_formula": strip_emphasis(target.get("example_formula", "")).strip(),
        "reveal_result": strip_emphasis(target.get("example_result", "")).strip(),
        "reveal_pitfalls": strip_emphasis(target.get("pitfalls", "")).strip(),
    }


def build_choice_question(target: dict, pool, *, rng=None) -> dict | None:
    """出一道选择题：给场景，四选一认函数。

    干扰项**优先取同分类**（「VLOOKUP 还是 XLOOKUP」才考得出东西），
    同分类不够再从全库补。题干里出现过的函数名一律不当干扰项，
    否则题面在暗示答案。凑不满选项数时返回 None，调用方跳过这题。
    """
    rng = rng or random.Random()
    code = str(target.get("code", "")).strip()
    if not code:
        return None
    prompt = quiz_prompt(target, quiz_type=QUIZ_CHOICE)
    if not prompt:
        return None

    candidates = []
    for item in pool or []:
        other = str(item.get("code", "")).strip()
        if not other or other == code or other in prompt:
            continue
        candidates.append(item)
    same = [item for item in candidates if item.get("category") == target.get("category")]
    rest = [item for item in candidates if item.get("category") != target.get("category")]
    rng.shuffle(same)
    rng.shuffle(rest)

    distractors: list[str] = []
    for item in same + rest:
        other = str(item["code"]).strip()
        if other not in distractors:
            distractors.append(other)
        if len(distractors) >= QUIZ_OPTION_COUNT - 1:
            break
    if len(distractors) < QUIZ_OPTION_COUNT - 1:
        return None
    options = [code, *distractors]
    rng.shuffle(options)
    return _question_payload(target, QUIZ_CHOICE, prompt, options=options, answer=code)


def build_formula_question(target: dict, *, rng=None) -> dict | None:
    """出一道「写公式」题：给场景，你自己写，写完自评。

    为什么是自评而不是机器判：Excel 里等价写法太多（``INDEX+MATCH`` 换个写法
    照样对），判错的代价比不判大得多。这道题的价值在**把答案写一遍** ——
    写不出来时看一眼示例，那一下才叫学到了。没有示例公式的函数出不了这题。
    """
    code = str(target.get("code", "")).strip()
    formula = strip_emphasis(target.get("example_formula", "")).strip()
    if not code or not formula:
        return None
    body = quiz_prompt(target, quiz_type=QUIZ_FORMULA)
    if not body:
        return None
    name_cn = str(target.get("name_cn", "")).strip()
    who = f"{code}（{name_cn}）" if name_cn else code
    prompt = f"用 {who} 写一条公式，解决这件事：\n{body}"
    return _question_payload(target, QUIZ_FORMULA, prompt, answer=formula)


def build_quiz_questions(functions, *, count=QUIZ_BATCH, mode=QUIZ_MODE_MIXED,
                         rng=None, pool=None) -> list[dict]:
    """凑一轮题。

    **优先出还不熟的**（掌握度 ≤ 一般）：练已经会的是浪费时间，
    「生疏」那一堆才是真正该反复过的。不熟的不够数才拿熟练的补。
    抽题走传入的 ``rng``，所以同一个种子必然凑出同一套题（测试靠这个）。

    ``functions`` 是**抽题范围**，``pool`` 是**干扰项来源**（缺省同前者）。
    分开是为了「只练错题」：那时抽题范围可能只剩一两个函数，但四选一
    照样得凑出三个不相干的选项 —— 干扰项跟目标不必同出一源。
    """
    rng = rng or random.Random()
    candidates = [dict(item) for item in (functions or [])]
    if not candidates:
        return []
    distractor_pool = [dict(item) for item in (pool if pool is not None
                                               else functions or [])]
    weak = [item for item in candidates
            if int(item.get("mastery", 0) or 0) <= MASTERY_FAIR]
    strong = [item for item in candidates
              if int(item.get("mastery", 0) or 0) > MASTERY_FAIR]
    rng.shuffle(weak)
    rng.shuffle(strong)
    targets = (weak + strong)[: max(1, int(count))]

    questions: list[dict] = []
    for index, target in enumerate(targets):
        if mode == QUIZ_CHOICE:
            wanted = QUIZ_CHOICE
        elif mode == QUIZ_FORMULA:
            wanted = QUIZ_FORMULA
        else:
            wanted = QUIZ_CHOICE if index % 2 == 0 else QUIZ_FORMULA
        attempt = [wanted]
        if mode == QUIZ_MODE_MIXED and wanted == QUIZ_FORMULA:
            attempt.append(QUIZ_CHOICE)     # 缺示例公式的题降级成选择题
        for quiz_type in attempt:
            question = (build_choice_question(target, distractor_pool, rng=rng)
                        if quiz_type == QUIZ_CHOICE
                        else build_formula_question(target, rng=rng))
            if question:
                questions.append(question)
                break
    return questions


def group_quiz_round(rows, *, gap_minutes: int = QUIZ_ROUND_GAP_MINUTES) -> list[dict]:
    """把按时间**倒序**的作答流水切成「最近一轮」，并顺手做两件事：

    ① **每个函数只留最近那条**。同一轮里同一个函数可能被连问两次
       （错题本重做、连着抽到），整理笔记时不该出现两页；
    ② **答错的排前面**。「学完生成笔记」是为了记住不会的，
       会的不着急看。

    时间分界：从最新一条往回走，遇到「与上一条相隔超过 ``gap_minutes``」
    就停。时间戳解析不出来时**不切**（宁可多带几条，也不要少带）。

    返回的每一条都被补上 ``quiz_id``，界面拿它做「重做这一道」的入口。
    """
    if not rows:
        return []

    def stamp(value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    anchor = stamp(rows[0].get("created_at"))
    picked: list[dict] = []
    previous = anchor
    for row in rows:
        current = stamp(row.get("created_at"))
        if (anchor is not None and current is not None and previous is not None
                and (previous - current).total_seconds() > int(gap_minutes) * 60):
            break
        picked.append(dict(row))
        if current is not None:
            previous = current

    # ① 按函数去重：流水是倒序的，先见到的那条就是最新的
    seen: set[int] = set()
    unique: list[dict] = []
    for item in picked:
        key = int(item.get("function_id") or 0)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(item)

    # ② 答错的排前面（稳定排序，同一组里保持原来的时间序）
    unique.sort(key=lambda item: 1 if int(item.get("is_correct") or 0) else 0)
    return unique


# ======================================================================
# CSV / Excel 批量导入（纯函数，测试直接打这里）
# ======================================================================
def import_template_headers() -> list[str]:
    """模板列头：必填列前面加 ``*``（Excel 里一眼能看出哪几列不能空）。"""
    return [f"*{name}" if required else name for name, required in IMPORT_COLUMNS]


def import_template_rows() -> list[list[str]]:
    """模板里的两行示例。

    函数名故意起成 ``MYFUNC1`` / ``MYFUNC2``：**导入前你会改成自己的**。
    万一没改就导进去了，库里也只是多两条一眼看得出的自建函数，删掉即可 ——
    比让你对着一片空白猜格式友好。
    """
    return [
        ["MYFUNC1", "我的函数一", "查找与引用",
         "MYFUNC1(查找值, 区域)",
         "照书上抄下来的冷门函数，一句话说明它干什么",
         "查找值：要去找的东西\n区域：去哪里找", "返回找到的那一行",
         "=MYFUNC1(A2,$D$2:$F$99)", "示例里 A2 能取到「张三」", "参数顺序容易记反",
         "书上有、内置库里没有的那类需求", "VLOOKUP|INDEX", "照书补录", "Excel 2019",
         "常用", "核心", "412", "我自己的理解"],
        ["MYFUNC2", "我的函数二", "数学与三角函数",
         "MYFUNC2(数值, [位数])", "第二条示例，导入前删掉这一行也可以",
         "数值：要处理的数\n位数：可选", "返回处理后的数值",
         "=MYFUNC2(3.14159,2)", "返回 3.14", "", "算数取整", "", "", "",
         "入门", "了解", "", ""],
    ]


def import_template_csv() -> str:
    """模板 CSV 全文（落盘时用 ``utf-8-sig``，Excel 双击打开不乱码）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(import_template_headers())
    for row in import_template_rows():
        writer.writerow(row)
    return buffer.getvalue()


def normalize_import_header(name) -> str | None:
    """把表头认成内部字段名；认不出来返回 None（那一列会被忽略）。"""
    text = str("" if name is None else name).strip().lstrip("*").strip().lower()
    text = re.sub(r"\s+", "", text)
    if not text:
        return None
    for field, aliases in IMPORT_HEADER_ALIASES.items():
        if text in aliases:
            return field
    return None


def normalize_import_value(value) -> str:
    """单元格值归一化成字符串：``None`` 空串、整数去掉 ``.0``、日期转 ISO。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_level(value, mapping, fallback: int) -> int:
    """解析「难度 / 重要度」列：认数字，也认中文（入门 / 核心）。"""
    text = normalize_import_value(value)
    if not text:
        return fallback
    if text.isdigit():
        number = int(text)
        return number if number in mapping else fallback
    for number, label in mapping.items():
        if label == text:
            return number
    return fallback


def normalize_import_row(raw: dict) -> dict:
    """一行「表头 → 单元格」整理成入库字段字典。

    **幂等**：已经归一化过的行再跑一遍结果不变（界面拿它做预览、
    ``import_functions`` 里再跑一遍，两处都不会走样）。
    """
    row = {field: "" for field, _required in IMPORT_COLUMNS}
    for header, value in (raw or {}).items():
        field = normalize_import_header(header)
        if field is None:
            continue
        row[field] = normalize_import_value(value)
    row["code"] = re.sub(r"\s+", "", row["code"]).upper()
    row["category"] = row["category"] or "逻辑"
    row["difficulty"] = parse_level(row["difficulty"], DIFFICULTY_LABELS, 2)
    row["importance"] = parse_level(row["importance"], IMPORTANCE_LABELS, 2)
    return row


def validate_import_row(row: dict) -> list[str]:
    """必填与格式校验。返回问题列表，空列表 = 这一行能入库。"""
    problems: list[str] = []
    for field, required in IMPORT_COLUMNS:
        if required and not str(row.get(field, "") or "").strip():
            problems.append(f"{field} 不能为空")
    code = str(row.get("code", "") or "").strip()
    if len(code) > 32:
        problems.append("函数名最长 32 个字符")
    if re.search(r"\s", code):
        problems.append("函数名里不能有空格")
    for field, mapping in (("difficulty", DIFFICULTY_LABELS),
                           ("importance", IMPORTANCE_LABELS)):
        value = row.get(field)
        if value in ("", None):
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = None
        if number not in mapping:
            problems.append(f"{field} 只能填 {min(mapping)}-{max(mapping)} 或对应的中文")
    return problems


def read_import_text(path) -> str:
    """按 UTF-8(含 BOM) → GBK 的顺序试解码。

    Excel「另存为 CSV」在中文 Windows 上默认是 GBK，而自己用编辑器存的
    多半是 UTF-8。两个都认，省得让你先去猜该存哪种编码。
    """
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def import_rows_from_table(rows) -> list[dict]:
    """「列表的列表」→ 「表头 → 单元格」行字典（第一行是表头，空行丢掉）。"""
    table = [list(row) for row in (rows or []) if row is not None]
    table = [row for row in table
             if any(str("" if cell is None else cell).strip() for cell in row)]
    if not table:
        return []
    headers = [normalize_import_header(cell) or str(cell or "").strip()
               for cell in table[0]]
    result: list[dict] = []
    for row in table[1:]:
        result.append({headers[index]: (row[index] if index < len(row) else "")
                       for index in range(len(headers))})
    return result


def parse_import_csv_text(text) -> list[dict]:
    """CSV / TSV 文本 → 行字典列表。**纯函数，测试直接打这里。**

    分隔符不靠 ``csv.Sniffer`` 一锤定音：它在小样本上会挑错（实测把分号、
    制表符的文件都判成逗号），代价是整行变成一个单元格、表头全认不出来、
    每一行都进 errors —— 用户看到的是「照模板填的，一导全错」还不报异常。
    所以改成**试一遍再比**：按候选分隔符各解析一次，谁认出来的字段名多谁赢。
    判据从「猜字符频率」换成「表头认不认得出来」，与后面的导入逻辑同一个口径。
    """
    body = str(text or "")
    order: list[str] = []
    sample = body[:8192]
    if sample:
        try:
            order.append(csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter)
        except csv.Error:
            pass
    for delimiter in (",", ";", "\t"):
        if delimiter not in order:
            order.append(delimiter)

    best: list[dict] = []
    best_hits = -1
    for delimiter in order:
        rows = import_rows_from_table(
            [row for row in csv.reader(io.StringIO(body), delimiter=delimiter)]
        )
        if not rows:
            continue
        hits = sum(1 for key in rows[0] if normalize_import_header(key))
        if hits > best_hits:
            best, best_hits = rows, hits
        if best_hits >= 5:              # 认出 5 个字段已经不可能再是别的分隔符
            break
    return best


def parse_import_xlsx(path) -> list[dict]:
    """读 xlsx 的第一个工作表。

    ``openpyxl`` **按需导入**：纯数据层测试与日常启动都不该为它买单
    （与项目里其他按需导入的地方同一个口径）。
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:                # pragma: no cover - 取决于环境
        raise ValueError("读取 Excel 文件需要 openpyxl，先 pip install openpyxl") from exc
    book = load_workbook(filename=str(path), read_only=True, data_only=True)
    try:
        rows = [list(row) for row in book.worksheets[0].iter_rows(values_only=True)]
    finally:
        book.close()
    return import_rows_from_table(rows)


def parse_import_file(path) -> list[dict]:
    """按后缀解析导入文件，统一成「行字典列表」。"""
    target = Path(path)
    if not target.exists():
        raise ValueError(f"找不到文件：{target}")
    if target.suffix.lower() in IMPORT_EXCEL_SUFFIXES:
        return parse_import_xlsx(target)
    return parse_import_csv_text(read_import_text(target))


# ======================================================================
# 建表 / 迁移 / 种子
# ======================================================================
def ensure_columns(conn: sqlite3.Connection, table: str, spec: dict) -> list[str]:
    """缺列就 ``ALTER TABLE ADD COLUMN``；返回本次实际补的列名。

    存量库升级用：新字段一律带 ``DEFAULT``，所以对已有数据零风险。
    """
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    added: list[str] = []
    for column, definition in spec.items():
        if column in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        added.append(column)
    return added


def init_excel_tables(conn: sqlite3.Connection) -> None:
    """建齐五张表（幂等）。"""
    for statement in TABLES:
        conn.execute(statement)
    ensure_columns(conn, "excel_functions", FUNCTION_EXTRA_COLUMNS)
    ensure_columns(conn, "excel_recipes", RECIPE_EXTRA_COLUMNS)
    ensure_columns(conn, "excel_notes", NOTE_EXTRA_COLUMNS)
    conn.commit()


def seed_excel_data(conn: sqlite3.Connection, force: bool = False) -> dict:
    """写入内置函数库与配方。

    ``INSERT OR IGNORE`` + ``code`` / ``title`` 唯一约束 = 幂等：
    升级版本时新增的函数会被补进来，而你自己填的 **书页码、我的理解、掌握度
    一律不动**（那三个字段不在 INSERT 的列里，已存在行直接跳过）。

    ``force=True`` 时改成 ``INSERT OR REPLACE`` 覆盖可变字段 —— 只给
    「重建种子」这类显式操作使用，会清掉书页码与笔记，界面上不要随便调。
    """
    now = datetime.now().isoformat(timespec="seconds")
    verb = "INSERT OR REPLACE" if force else "INSERT OR IGNORE"
    function_sql = f"""
        {verb} INTO excel_functions (
            code, name_cn, category, tags, syntax, args_desc, returns, description,
            example_formula, example_result, pitfalls, use_cases, related,
            min_version, difficulty, importance, is_builtin, sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
    """
    for order, item in enumerate(SEED_FUNCTIONS):
        conn.execute(function_sql, (
            item["code"], item["name_cn"], item["category"], item["tags"],
            item["syntax"], item["args_desc"], item["returns"], item["description"],
            item["example_formula"], item["example_result"], item["pitfalls"],
            item["use_cases"], item["related"], item["min_version"],
            int(item["difficulty"]), int(item["importance"]), order, now, now,
        ))

    recipe_sql = f"""
        {verb} INTO excel_recipes (
            title, scene, category, formula, breakdown, pitfalls, related,
            difficulty, is_builtin, sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
    """
    for order, item in enumerate(SEED_RECIPES):
        conn.execute(recipe_sql, (
            item["title"], item["scene"], item["category"], item["formula"],
            item["breakdown"], item["pitfalls"], item["related"],
            int(item["difficulty"]), order, now, now,
        ))
    conn.commit()
    return {"functions": len(SEED_FUNCTIONS), "recipes": len(SEED_RECIPES)}


def _function_markdown_lines(item: dict, progress: dict | None = None) -> list[str]:
    """单个函数的 Markdown 片段。**没有值的字段整段不写**（空栏很占地方）。"""
    lines = []
    code = str(item.get("code") or "")
    name = str(item.get("name_cn") or "")
    lines.append(f"### {code} {name}".rstrip())
    lines.append("")
    if str(item.get("description") or "").strip():
        lines.append(str(item["description"]).strip())
        lines.append("")
    for title, key, mono in (
        ("语法", "syntax", True),
        ("参数", "args_desc", False),
        ("返回值", "returns", False),
        ("示例", "example_formula", True),
        ("适用", "use_cases", False),
        ("易错点", "pitfalls", False),
        ("相关", "related", False),
    ):
        value = str(item.get(key) or "").strip()
        if not value:
            continue
        shown = f"`{value}`" if mono else value
        lines.append(f"- **{title}**：{shown}")
    if str(item.get("example_result") or "").strip():
        lines.append(f"- **示例结果**：{item['example_result']}")
    extra = []
    if str(item.get("book_page") or "").strip():
        extra.append(f"书页 {item['book_page']}")
    if progress is not None:
        extra.append("掌握度 " + mastery_label(
            int(progress.get("mastery", 0) or 0)))
    if extra:
        lines.append("- " + " / ".join(extra))
    note = str(item.get("my_note") or "").strip()
    if note:
        lines.append("")
        lines.append(f"> 我的笔记：{note}")
    lines.append("")
    return lines


def functions_markdown(items, *, title="Excel 函数库",
                       progress: dict | None = None) -> str:
    """整库 Markdown：按分类分章 + 目录。**纯函数**，不碰数据库。"""
    rows = [dict(item) for item in (items or [])]
    lines = [f"# {title}", ""]

    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in rows:
        category = str(item.get("category") or "未分类")
        if category not in grouped:
            grouped[category] = []
            order.append(category)
        grouped[category].append(item)

    lines.append(f"共 {len(rows)} 个函数，{len(order)} 个分类。")
    lines.append("")
    lines.append("## 目录")
    lines.append("")
    for category in order:
        lines.append(f"- {category}（{len(grouped[category])}）")
    lines.append("")

    for category in order:
        lines.append(f"## {category}")
        lines.append("")
        for item in grouped[category]:
            row_progress = None
            if progress is not None:
                # 进度行是懒创建的：没复习过的函数**没有那一行**，
                # 这时它该显示「未学」，而不是整段不写
                row_progress = (progress.get(item.get("id"))
                                or {"mastery": 0})
            lines.extend(_function_markdown_lines(item, row_progress))
        lines.append("---")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ======================================================================
# 数据访问
# ======================================================================
class ExcelDB:
    """Excel 学习中心的数据入口。由 ``main`` 建一次并注入页面。"""

    def __init__(self, db_path, *, seed: bool = True):
        self.db_path = db_path
        self.conn = db_backup.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        init_excel_tables(self.conn)
        if seed:
            seed_excel_data(self.conn)

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            logger.exception("关闭 Excel 学习中心数据库失败")

    # -- 内部 ----------------------------------------------------------
    @staticmethod
    def _rows_to_dicts(rows) -> list[dict]:
        return [dict(row) for row in rows]

    def _progress_by_id(self) -> dict[int, dict]:
        rows = self.conn.execute("SELECT * FROM excel_progress").fetchall()
        return {int(row["function_id"]): dict(row) for row in rows}

    # -- 函数 ----------------------------------------------------------
    def count_functions(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM excel_functions").fetchone()
        return int(row["n"]) if row else 0

    def all_functions(self) -> list[dict]:
        return self._rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM excel_functions ORDER BY sort_order, code"
            ).fetchall()
        )

    def functions_by_code(self) -> dict[str, dict]:
        return {item["code"]: item for item in self.all_functions()}

    def get_function(self, function_id) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM excel_functions WHERE id = ?", (int(function_id),)
        ).fetchone()
        return dict(row) if row else None

    def get_function_by_code(self, code: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM excel_functions WHERE code = ?", (str(code).upper(),)
        ).fetchone()
        return dict(row) if row else None

    def list_functions(self, *, category=None, mastery=None, keyword="",
                       limit=None, due_only=False, today=None) -> list[dict]:
        """按分类 / 掌握度 / 关键词筛选函数列表（带 ``mastery`` 与 ``due`` 字段）。

        ``mastery`` 传 None 表示不限；传数字表示只要这一档。筛选在 Python 里做 ——
        200 条量级下，可读性比省那几毫秒重要，**关键词要匹配到 use_cases 与
        example_formula，SQL 里写这些条件会很别扭**。
        """
        rows = self.all_functions()
        progress = self._progress_by_id()
        anchor = parse_date(today) or date.today()
        result: list[dict] = []
        for item in rows:
            state = progress.get(item["id"]) or {}
            item_mastery = int(state.get("mastery", MASTERY_NEW) or MASTERY_NEW)
            item["mastery"] = item_mastery
            next_review = parse_date(state.get("next_review_at"))
            item["next_review_at"] = state.get("next_review_at", "")
            item["due"] = bool(next_review and next_review <= anchor)
            if category and item["category"] != category:
                continue
            if mastery is not None and item_mastery != int(mastery):
                continue
            if due_only and not item["due"]:
                continue
            if keyword and not match_keyword(function_search_blob(item), keyword):
                continue
            result.append(item)
        if limit is not None:
            result = result[: int(limit)]
        return result

    def update_function_fields(self, function_id, **fields) -> None:
        """更新「书页码 / 我的理解」这类可编辑字段（白名单之外的键直接忽略）。"""
        payload = {k: v for k, v in fields.items() if k in EDITABLE_FUNCTION_FIELDS}
        if not payload:
            return
        payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
        assignments = ", ".join(f"{key} = ?" for key in payload)
        self.conn.execute(
            f"UPDATE excel_functions SET {assignments} WHERE id = ?",
            (*payload.values(), int(function_id)),
        )
        self.conn.commit()

    def add_custom_function(self, payload: dict) -> int:
        """新增一条自建函数（``is_builtin = 0``，因此允许删除）。"""
        code = str(payload.get("code", "")).strip().upper()
        if not code:
            raise ValueError("函数名不能为空")
        if self.get_function_by_code(code):
            raise ValueError(f"函数 {code} 已存在")
        now = datetime.now().isoformat(timespec="seconds")
        order_row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS n FROM excel_functions"
        ).fetchone()
        cursor = self.conn.execute(
            """
            INSERT INTO excel_functions (
                code, name_cn, category, tags, syntax, args_desc, returns, description,
                example_formula, example_result, pitfalls, use_cases, related,
                min_version, difficulty, importance, book_page, my_note,
                is_builtin, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                code,
                str(payload.get("name_cn", "")).strip(),
                str(payload.get("category", "")).strip() or "逻辑",
                str(payload.get("tags", "")).strip(),
                str(payload.get("syntax", "")).strip(),
                str(payload.get("args_desc", "")).strip(),
                str(payload.get("returns", "")).strip(),
                str(payload.get("description", "")).strip(),
                str(payload.get("example_formula", "")).strip(),
                str(payload.get("example_result", "")).strip(),
                str(payload.get("pitfalls", "")).strip(),
                str(payload.get("use_cases", "")).strip(),
                str(payload.get("related", "")).strip(),
                str(payload.get("min_version", "")).strip(),
                int(payload.get("difficulty", 2) or 2),
                int(payload.get("importance", 2) or 2),
                str(payload.get("book_page", "")).strip(),
                str(payload.get("my_note", "")).strip(),
                int(order_row["n"]) + 1,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def delete_function(self, function_id) -> bool:
        """删除**自建**函数。内置函数不允许删（只能改书页码与掌握度）。"""
        item = self.get_function(function_id)
        if not item:
            return False
        if item["is_builtin"]:
            raise ValueError("内置函数不能删除，只能标记掌握度或写笔记。")
        self.conn.execute("DELETE FROM excel_progress WHERE function_id = ?", (int(function_id),))
        # 答题流水也要清：``quiz_wrong_items`` 是 LEFT JOIN 出来的，
        # 留着孤儿行会在错题本里显示成一条没有函数名的空条目。
        self.conn.execute("DELETE FROM excel_quiz_log WHERE function_id = ?", (int(function_id),))
        self.conn.execute("DELETE FROM excel_functions WHERE id = ?", (int(function_id),))
        self.conn.commit()
        return True

    # -- 批量导入 ------------------------------------------------------
    def import_functions(self, rows, *, overwrite_builtin: bool = False,
                         dry_run: bool = False) -> dict:
        """把「行字典列表」批量写进函数库。

        三条去向（都体现在返回值里，界面照着报数）：
          新增 —— 库里没有这个函数名，入成**自建**（``is_builtin=0``，所以可删）
          更新 —— 库里已有且是自建的；或你显式勾了「覆盖内置」
          跳过 —— 库里已有且是**内置**的，而你没勾覆盖

        覆盖时**只写文件里非空的字段**：空单元格的意思是「这列我没填」，
        不是「把它清空」，所以你的书页码与心得不会被一次导入抹掉。

        ``dry_run=True`` 时只走分类、**一个字都不写**，界面拿它做「导之前先报
        规模」—— 这样预览和真写是同一段判定逻辑，不会出现「预览说 3 条、
        实际写了 5 条」。
        """
        added: list[str] = []
        updated: list[str] = []
        skipped: list[dict] = []
        errors: list[dict] = []
        warnings: list[dict] = []
        seen: set[str] = set()

        for offset, raw in enumerate(list(rows or []), start=2):   # 表头算第 1 行
            row = normalize_import_row(raw)
            code = str(row.get("code", "") or "").strip()
            problems = validate_import_row(row)
            if problems:
                errors.append({"row": offset, "code": code,
                               "message": "；".join(problems)})
                continue
            if code in seen:
                errors.append({"row": offset, "code": code,
                               "message": "同一个文件里这个函数名出现了两次"})
                continue
            seen.add(code)
            if row["category"] not in CATEGORY_NAMES:
                warnings.append({"row": offset, "code": code,
                                 "message": f"分类「{row['category']}」不在官方 12 类里，"
                                            "会以自定义分类入库"})
            existing = self.get_function_by_code(code)
            try:
                if existing is None:
                    if not dry_run:
                        self.add_custom_function(row)
                    added.append(code)
                elif not int(existing.get("is_builtin", 0) or 0) or overwrite_builtin:
                    if not dry_run:
                        self.update_function_content(existing["id"], row)
                    updated.append(code)
                else:
                    skipped.append({"row": offset, "code": code,
                                    "message": "库里已有同名内置函数"
                                               "（勾上「覆盖内置」可以强制改写）"})
            except (ValueError, sqlite3.Error) as exc:
                errors.append({"row": offset, "code": code, "message": str(exc)})
        return {
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "warnings": warnings,
            "total": len(added) + len(updated),
        }

    def update_function_content(self, function_id, row: dict) -> None:
        """按导入行改写函数内容。

        **只写非空字段**，也不碰 ``is_builtin``（决定这条能不能删）与
        ``sort_order``（课程顺序）—— 列名全部来自白名单常量，不存在拼接注入。
        """
        payload: dict = {}
        for field in IMPORT_WRITABLE_FIELDS:
            if field not in row:
                continue
            value = row[field]
            if isinstance(value, str) and not value.strip():
                continue
            payload[field] = value
        if not payload:
            return
        payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
        assignments = ", ".join(f"{key} = ?" for key in payload)
        self.conn.execute(
            f"UPDATE excel_functions SET {assignments} WHERE id = ?",
            (*payload.values(), int(function_id)),
        )
        self.conn.commit()

    def export_functions_markdown(self, path) -> int:
        """把整库导成 Markdown（书页码与自己写的笔记一并带走）。"""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = self.all_functions()
        target.write_text(
            functions_markdown(rows, progress=self.progress_map()),
            encoding="utf-8", newline="\n")
        return len(rows)

    def export_functions_csv(self, path) -> int:
        """把整库导成 CSV（列头与导入模板一致，可以「导出 → 改 → 再导回来」）。"""
        headers = [name for name, _required in IMPORT_COLUMNS]
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(headers)
        count = 0
        for item in self.all_functions():
            writer.writerow([item.get(name, "") for name in headers])
            count += 1
        Path(path).write_bytes(buffer.getvalue().encode("utf-8-sig"))
        return count

    def write_import_template(self, path) -> str:
        """把导入模板写到 ``path``（UTF-8 带 BOM，Excel 双击打开不乱码）。"""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(import_template_csv().encode("utf-8-sig"))
        return str(target)

    # -- 掌握度与复习 ---------------------------------------------------
    def progress_map(self) -> dict[int, dict]:
        return self._progress_by_id()

    def _ensure_progress(self, function_id) -> dict:
        row = self.conn.execute(
            "SELECT * FROM excel_progress WHERE function_id = ?", (int(function_id),)
        ).fetchone()
        if row:
            return dict(row)
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO excel_progress (function_id, mastery, marked_at) VALUES (?, ?, ?)",
            (int(function_id), MASTERY_NEW, now),
        )
        self.conn.commit()
        return {"function_id": int(function_id), "mastery": MASTERY_NEW,
                "review_count": 0, "correct_streak": 0, "interval_days": 0,
                "last_review_at": "", "next_review_at": "", "marked_at": now}

    def set_mastery(self, function_id, mastery, *, today=None) -> dict:
        """手动设掌握度（详情页那个下拉）。

        设成 1 及以上时顺手把「首次复习」排到今天，这样手动标过的函数
        会立刻出现在今日复习里 —— 符合直觉：我标了「生疏」，就该尽快再过一遍。
        """
        state = self._ensure_progress(function_id)
        anchor = parse_date(today) or date.today()
        mastery = max(MASTERY_NEW, min(MASTERY_GOOD, int(mastery)))
        interval = int(state.get("interval_days") or 0)
        next_review = state.get("next_review_at") or ""
        if mastery >= MASTERY_WEAK and not next_review:
            interval = interval or 1
            next_review = anchor.isoformat()
        self.conn.execute(
            "UPDATE excel_progress SET mastery = ?, interval_days = ?, next_review_at = ? "
            "WHERE function_id = ?",
            (mastery, interval, next_review, int(function_id)),
        )
        self.conn.commit()
        return {"mastery": mastery, "interval_days": interval, "next_review_at": next_review}

    def record_review(self, function_id, feedback, *, today=None) -> dict:
        """记一次复习反馈，返回新状态（含 ``next_review_at``）。"""
        if feedback not in dict(FEEDBACK_CHOICES):
            raise ValueError(f"未知的复习反馈：{feedback}")
        state = self._ensure_progress(function_id)
        anchor = parse_date(today) or date.today()
        new_state = review_next_state(
            state.get("mastery", 0), state.get("correct_streak", 0),
            state.get("interval_days", 0), feedback,
        )
        interval = max(1, int(new_state["interval_days"]))
        next_review = anchor + timedelta(days=interval)
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            UPDATE excel_progress
               SET mastery = ?, review_count = review_count + 1,
                   correct_streak = ?, interval_days = ?,
                   last_review_at = ?, next_review_at = ?
             WHERE function_id = ?
            """,
            (
                int(new_state["mastery"]), int(new_state["correct_streak"]),
                interval, now, next_review.isoformat(), int(function_id),
            ),
        )
        self.conn.commit()
        return {
            "mastery": int(new_state["mastery"]),
            "correct_streak": int(new_state["correct_streak"]),
            "interval_days": interval,
            "next_review_at": next_review.isoformat(),
        }

    def due_functions(self, *, limit=None, today=None) -> list[dict]:
        """今天该复习的函数。

        **必须 LEFT JOIN**：进度行是懒创建的，没学过 / 刚装好种子库时
        ``excel_progress`` 里一行都没有。若按内连接只查 progress，首次打开
        「今日复习」会是空的 —— 而这时候才是最该推新的。所以「没有进度行」
        一律算作「没排过期的待学项」。

        排序：先已经排过期、今天到点的（复习优先），再没学过的（按课程序）。
        """
        anchor = parse_date(today) or date.today()
        rows = self.conn.execute(
            """
            SELECT f.*, p.mastery AS mastery, p.next_review_at AS next_review_at,
                   p.review_count AS review_count
              FROM excel_functions f
              LEFT JOIN excel_progress p ON p.function_id = f.id
             WHERE COALESCE(p.next_review_at, '') = '' OR p.next_review_at <= ?
             ORDER BY CASE WHEN COALESCE(p.next_review_at, '') = '' THEN 1 ELSE 0 END,
                      p.next_review_at, f.sort_order
            """,
            (anchor.isoformat(),),
        ).fetchall()
        result = self._rows_to_dicts(rows)
        for item in result:
            item["due"] = True
        if limit is not None:
            result = result[: int(limit)]
        return result

    def due_count(self, *, today=None) -> int:
        anchor = parse_date(today) or date.today()
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM excel_functions f "
            "LEFT JOIN excel_progress p ON p.function_id = f.id "
            "WHERE COALESCE(p.next_review_at, '') = '' OR p.next_review_at <= ?",
            (anchor.isoformat(),),
        ).fetchone()
        return int(row["n"]) if row else 0

    def mastery_overview(self) -> dict:
        """总跨度统计：总数 / 已学 / 熟练 / 各掌握度档位数量。"""
        total = self.count_functions()
        buckets = {value: 0 for value, _ in MASTERY_CHOICES}
        tracked = 0
        for state in self._progress_by_id().values():
            mastery = max(MASTERY_NEW, min(MASTERY_GOOD, int(state.get("mastery", 0) or 0)))
            buckets[mastery] += 1
            tracked += 1
        # 没进过 progress 表的函数按「未学」算（进度是懒创建的）
        buckets[MASTERY_NEW] += max(0, total - tracked)
        learned = sum(count for value, count in buckets.items() if value >= MASTERY_WEAK)
        return {
            "total": total,
            "learned": learned,
            "good": buckets.get(MASTERY_GOOD, 0),
            "buckets": buckets,
            "percent": round(learned * 100 / total) if total else 0,
        }

    def category_stats(self) -> list[dict]:
        return category_stats(self.all_functions(), self._progress_by_id())

    def learning_progress(self) -> list[dict]:
        """七个阶段的进度。"""
        by_code = self.functions_by_code()
        progress = self._progress_by_id()
        return [path_progress(path, by_code, progress) for path in LEARNING_PATHS]

    # -- 配方 ----------------------------------------------------------
    def all_recipes(self) -> list[dict]:
        return self._rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM excel_recipes ORDER BY sort_order, title"
            ).fetchall()
        )

    def get_recipe(self, recipe_id) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM excel_recipes WHERE id = ?", (int(recipe_id),)
        ).fetchone()
        return dict(row) if row else None

    def list_recipes(self, *, keyword="", category=None) -> list[dict]:
        result: list[dict] = []
        for item in self.all_recipes():
            if category and item["category"] != category:
                continue
            if keyword:
                blob = "\n".join(str(item.get(k, "")) for k in
                                 ("title", "scene", "category", "formula",
                                  "breakdown", "pitfalls", "related")).lower()
                if not match_keyword(blob, keyword):
                    continue
            result.append(item)
        return result

    def update_recipe_fields(self, recipe_id, **fields) -> None:
        payload = {k: v for k, v in fields.items() if k in EDITABLE_RECIPE_FIELDS}
        if not payload:
            return
        payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
        assignments = ", ".join(f"{key} = ?" for key in payload)
        self.conn.execute(
            f"UPDATE excel_recipes SET {assignments} WHERE id = ?",
            (*payload.values(), int(recipe_id)),
        )
        self.conn.commit()

    def recipe_categories(self) -> list[str]:
        seen: list[str] = []
        for item in self.all_recipes():
            if item["category"] and item["category"] not in seen:
                seen.append(item["category"])
        return seen

    # -- 笔记 ----------------------------------------------------------
    def list_notes(self, *, keyword="", function_id=None) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM excel_notes ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        result: list[dict] = []
        for item in self._rows_to_dicts(rows):
            if function_id is not None and int(item["function_id"] or 0) != int(function_id):
                continue
            if keyword:
                blob = "\n".join(str(item.get(k, "")) for k in
                                 ("title", "book_page", "content", "tags")).lower()
                if not match_keyword(blob, keyword):
                    continue
            result.append(item)
        return result

    def get_note(self, note_id) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM excel_notes WHERE id = ?", (int(note_id),)
        ).fetchone()
        return dict(row) if row else None

    def save_note(self, *, note_id=None, title="", book_page="", function_id=None,
                  content="", tags="", images="") -> int:
        now = datetime.now().isoformat(timespec="seconds")
        if note_id:
            self.conn.execute(
                """
                UPDATE excel_notes
                   SET title = ?, book_page = ?, function_id = ?, content = ?,
                       tags = ?, images = ?, updated_at = ?
                 WHERE id = ?
                """,
                (title, book_page, function_id, content, tags, images, now, int(note_id)),
            )
            self.conn.commit()
            return int(note_id)
        cursor = self.conn.execute(
            """
            INSERT INTO excel_notes (title, book_page, function_id, content, tags,
                                     images, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, book_page, function_id, content, tags, images, now, now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def delete_note(self, note_id) -> bool:
        cursor = self.conn.execute("DELETE FROM excel_notes WHERE id = ?", (int(note_id),))
        self.conn.commit()
        return cursor.rowcount > 0

    def note_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM excel_notes").fetchone()
        return int(row["n"]) if row else 0

    # -- 自测出题 ------------------------------------------------------
    def recent_quiz_answers(self, *, limit=QUIZ_LOOKBACK) -> list[dict]:
        """最近的自测流水（**倒序**），每条带上函数正文 —— 「生成学习笔记」的原料。

        ★ 三个 LEFT JOIN 都是必须的：
        * ``excel_functions`` —— 函数被删过后流水还在（错题本遇到过这个坑），
          内连接会让「删过一个自测过的函数」直接把这一轮少几条；
        * ``excel_progress`` —— 进度行是**懒创建**的，没标过掌握度的函数
          一行都没有（今日复习那次已经踩过：INNER JOIN 让新用户看到空页面）。
          这里要的正是「掌握度」这一栏，用内连接就会把新学的全滤掉 ——
          而新学的恰恰最该记笔记。

        ``f.category`` 显式取别名：``q.category`` 是**作答当时**的分类，
        函数改过分类后两者会不一样，笔记里要的是函数现在的归属。
        """
        rows = self.conn.execute(
            "SELECT q.id AS quiz_id, q.function_id, q.quiz_type, q.prompt, "
            "       q.answer, q.user_answer, q.is_correct, q.created_at, "
            "       f.code AS code, f.name_cn AS name_cn, "
            "       f.category AS category, f.syntax AS syntax, "
            "       f.example_formula AS example_formula, "
            "       f.example_result AS example_result, f.pitfalls AS pitfalls, "
            "       f.description AS description, f.use_cases AS use_cases, "
            "       f.book_page AS book_page, "
            "       p.mastery AS mastery, p.next_review_at AS next_review_at "
            "FROM excel_quiz_log AS q "
            "LEFT JOIN excel_functions AS f ON f.id = q.function_id "
            "LEFT JOIN excel_progress AS p ON p.function_id = q.function_id "
            "ORDER BY q.id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return self._rows_to_dicts(rows)

    def quiz_questions(self, *, count=QUIZ_BATCH, category=None,
                       mode=QUIZ_MODE_MIXED, only_wrong=False,
                       seed=None) -> list[dict]:
        """凑一轮题。``category=None`` 全库抽；``only_wrong=True`` 只出错题本里的。"""
        pool = self.list_functions(category=category)
        if not pool:
            return []
        if only_wrong:
            wrong_ids = {int(row["function_id"] or 0)
                         for row in self.quiz_wrong_items(category=category, limit=None)}
            narrowed = [item for item in pool if int(item["id"]) in wrong_ids]
            if narrowed:
                # 抽题范围缩到错题本，但干扰项仍从全库出 —— 否则错题本只剩
                # 一两条时，四选一凑不出选项，页面会是一片空白。
                return build_quiz_questions(narrowed, count=count, mode=mode,
                                            rng=random.Random(seed), pool=pool)
        return build_quiz_questions(pool, count=count, mode=mode,
                                    rng=random.Random(seed))

    def record_quiz_result(self, *, function_id, quiz_type, prompt="", answer="",
                           user_answer="", is_correct, category="",
                           feed_progress=True, today=None) -> dict:
        """记一次作答，并把结果**回灌到同一条遗忘曲线**上。

        对 → 按「熟练」回灌（掌握度 +1、间隔往后跳一档）；
        错 → 按「忘了」回灌（掌握度 −1、明天再来），同时进错题本。
        这样自测就不是一次孤立的测验，而是复习的一种形式 —— 曲线认得它，
        不会出现「今天复习了 20 个，自测又做对 10 个，进度却纹丝不动」。
        """
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            "INSERT INTO excel_quiz_log (function_id, quiz_type, prompt, answer, "
            "user_answer, is_correct, category, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (int(function_id or 0), str(quiz_type or QUIZ_CHOICE), str(prompt or ""),
             str(answer or ""), str(user_answer or ""), 1 if is_correct else 0,
             str(category or ""), now),
        )
        self.conn.commit()
        state: dict = {}
        if feed_progress and function_id:
            feedback = FEEDBACK_KNOWN if is_correct else FEEDBACK_FORGOT
            state = self.record_review(int(function_id), feedback, today=today)
        return {"id": int(cursor.lastrowid), "is_correct": bool(is_correct), **state}

    def quiz_wrong_items(self, *, category=None, limit=QUIZ_WRONG_LIMIT) -> list[dict]:
        """错题本：**每个函数只留最近一次做错的那条**，订正过的不再出现。

        为什么按函数去重而不是列出每一次错：同一道题连错三次不该在清单里占三行 ——
        那是流水，不是待办。定的是「哪些还没弄明白」，不是「错了几次」。
        """
        rows = self.conn.execute(
            "SELECT q.*, f.code AS code, f.name_cn AS name_cn, "
            "       f.category AS fn_category, f.syntax AS syntax, "
            "       f.example_formula AS example_formula, "
            "       f.example_result AS example_result "
            "FROM excel_quiz_log AS q "
            "LEFT JOIN excel_functions AS f ON f.id = q.function_id "
            "WHERE q.is_correct = 0 AND q.retried = 0 "
            "ORDER BY q.id DESC"
        ).fetchall()
        result: list[dict] = []
        seen: set[int] = set()
        for row in rows:
            item = dict(row)
            key = int(item.get("function_id") or 0)
            if key in seen:
                continue
            seen.add(key)
            item["category"] = item.get("fn_category") or item.get("category") or ""
            item["code"] = item.get("code") or ""
            item["name_cn"] = item.get("name_cn") or ""
            if category and item["category"] != category:
                continue
            result.append(item)
            if limit is not None and len(result) >= int(limit):
                break
        return result

    def mark_quiz_retried(self, quiz_id, *, correct=True, today=None) -> bool:
        """把一道错题标成「订正过」；``correct=True`` 时顺手按「熟练」回灌一次。

        **按函数销账，不是按这一行销账。** 同一个函数可能错了好几次，
        错题本只显示最新那条（那是故意的）；要是只把这一行标成已订正，
        下次刷新就会从旧流水里把同一个函数捞回来 —— 用户看到的是
        「点了订正它还在」，跟按钮坏了没区别。错题本问的是「哪些还没弄明白」，
        那么「订正」自然就该等于「这个函数弄明白了」。
        """
        row = self.conn.execute(
            "SELECT * FROM excel_quiz_log WHERE id = ?", (int(quiz_id),)
        ).fetchone()
        if not row:
            return False
        record = dict(row)
        self.conn.execute(
            "UPDATE excel_quiz_log SET retried = 1, retried_at = ? "
            "WHERE id = ? OR (function_id = ? AND function_id > 0 "
            "                 AND is_correct = 0 AND retried = 0)",
            (datetime.now().isoformat(timespec="seconds"), int(quiz_id),
             int(record.get("function_id") or 0)),
        )
        self.conn.commit()
        if correct and record.get("function_id"):
            self.record_review(int(record["function_id"]), FEEDBACK_KNOWN, today=today)
        return True

    def quiz_stats(self) -> dict:
        """自测汇总：答了多少次、对了几次、错题本还挂着几条。"""
        row = self.conn.execute(
            "SELECT COUNT(*) AS attempts, COALESCE(SUM(is_correct), 0) AS correct "
            "FROM excel_quiz_log"
        ).fetchone()
        attempts = int(row["attempts"] or 0)
        correct = int(row["correct"] or 0)
        return {
            "attempts": attempts,
            "correct": correct,
            "wrong": attempts - correct,
            "pending": len(self.quiz_wrong_items(limit=None)),
            "accuracy": round(correct * 100 / attempts) if attempts else 0,
        }

    def clear_quiz_log(self, *, wrong_only=True) -> int:
        """清空错题本；``wrong_only=False`` 时连答对的流水一起清（统计随之归零）。"""
        if wrong_only:
            cursor = self.conn.execute(
                "DELETE FROM excel_quiz_log WHERE is_correct = 0")
        else:
            cursor = self.conn.execute("DELETE FROM excel_quiz_log")
        self.conn.commit()
        return int(cursor.rowcount or 0)

    # -- 打卡 ----------------------------------------------------------
    def upsert_checkin(self, *, check_date=None, minutes=None, reviewed=None,
                       learned=None, note=None) -> dict:
        """记一天打卡。只更新传进来的字段（``None`` 表示这一项不动）。"""
        target = str(check_date or today_str())
        existing = self.conn.execute(
            "SELECT * FROM excel_checkins WHERE check_date = ?", (target,)
        ).fetchone()
        now = datetime.now().isoformat(timespec="seconds")
        if existing is None:
            self.conn.execute(
                "INSERT INTO excel_checkins (check_date, minutes, reviewed, learned, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (target, int(minutes or 0), int(reviewed or 0), int(learned or 0),
                 str(note or ""), now),
            )
        else:
            current = dict(existing)
            self.conn.execute(
                "UPDATE excel_checkins SET minutes = ?, reviewed = ?, learned = ?, note = ? "
                "WHERE check_date = ?",
                (
                    int(current["minutes"] if minutes is None else minutes),
                    int(current["reviewed"] if reviewed is None else reviewed),
                    int(current["learned"] if learned is None else learned),
                    str(current["note"] if note is None else note),
                    target,
                ),
            )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM excel_checkins WHERE check_date = ?", (target,)
        ).fetchone()
        return dict(row) if row else {}

    def checkin_dates(self) -> list[str]:
        return [row["check_date"] for row in self.conn.execute(
            "SELECT check_date FROM excel_checkins ORDER BY check_date"
        ).fetchall()]

    def get_checkin(self, check_date=None) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM excel_checkins WHERE check_date = ?",
            (str(check_date or today_str()),),
        ).fetchone()
        return dict(row) if row else None

    def streak(self, *, today=None) -> int:
        return compute_streak(self.checkin_dates(), today)

    def longest_streak(self) -> int:
        return longest_streak(self.checkin_dates())

    def totals(self) -> dict:
        """累计口径：学习天数 / 复习次数 / 累计分钟。"""
        row = self.conn.execute(
            "SELECT COUNT(*) AS days, COALESCE(SUM(minutes), 0) AS minutes, "
            "COALESCE(SUM(reviewed), 0) AS reviewed, COALESCE(SUM(learned), 0) AS learned "
            "FROM excel_checkins"
        ).fetchone()
        return {
            "days": int(row["days"] or 0),
            "minutes": int(row["minutes"] or 0),
            "reviewed": int(row["reviewed"] or 0),
            "learned": int(row["learned"] or 0),
        }

    def heatmap(self, *, weeks=18, today=None) -> dict:
        """复习热力图的数据：**列 = 周（周一起），行 = 周一..周日**。

        ``level`` 是给界面上色用的分档（0 = 没练，1..4 由浅到深）。分级按
        ``max`` 等分 —— 全程只练 3 个的人不该看到一片浅色，得按他自己的峰值算。
        """
        span = max(1, int(weeks))
        anchor = parse_date(today) or date.today()
        # 末尾这一列必须是**包含今天**的那一周，且从周一开头
        end_monday = anchor - timedelta(days=anchor.weekday())
        start_monday = end_monday - timedelta(weeks=span - 1)

        rows = {row["check_date"]: dict(row) for row in self.conn.execute(
            "SELECT * FROM excel_checkins").fetchall()}

        columns: list[list[dict]] = []
        months: list[tuple] = []
        last_month = None
        peak = 0
        total = 0
        for column_index in range(span):
            monday = start_monday + timedelta(weeks=column_index)
            if last_month != monday.month:
                months.append((column_index, f"{monday.month}月"))
                last_month = monday.month
            column: list[dict] = []
            for row_index in range(7):
                day = monday + timedelta(days=row_index)
                key = day.isoformat()
                record = rows.get(key) or {}
                value = int(record.get("reviewed", 0) or 0)
                future = day > anchor
                if not future:
                    total += value
                    peak = max(peak, value)
                column.append({
                    "date": key,
                    "value": value,
                    "level": 0,
                    "minutes": int(record.get("minutes", 0) or 0),
                    "checked": key in rows,
                    "future": future,
                })
            columns.append(column)

        for column in columns:
            for day in column:
                if day["future"] or not day["value"] or not peak:
                    continue
                ratio = day["value"] / float(peak)
                day["level"] = 1 if ratio <= 0.25 else (
                    2 if ratio <= 0.5 else (3 if ratio <= 0.75 else 4))
        return {
            "weeks": span,
            "columns": columns,
            "months": months,
            "max": peak,
            "total": total,
            "start": start_monday.isoformat(),
            "end": anchor.isoformat(),
        }

    def recent_activity(self, *, days=7, today=None) -> list[dict]:
        """最近 N 天的复习量（含没打卡的日子，值为 0），画柱状用。"""
        anchor = parse_date(today) or date.today()
        rows = {row["check_date"]: dict(row) for row in self.conn.execute(
            "SELECT * FROM excel_checkins"
        ).fetchall()}
        result: list[dict] = []
        for offset in range(int(days) - 1, -1, -1):
            day = anchor - timedelta(days=offset)
            key = day.isoformat()
            record = rows.get(key) or {}
            result.append({
                "date": key,
                "label": f"{day.month}/{day.day}",
                "weekday": day.isoweekday(),
                "reviewed": int(record.get("reviewed", 0) or 0),
                "minutes": int(record.get("minutes", 0) or 0),
                "checked": key in rows,
            })
        return result
