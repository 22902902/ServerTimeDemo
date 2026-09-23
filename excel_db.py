# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 数据层
================================================================================
分层约定与 ``todo_db`` / ``process_db`` 一致：**本模块只管数据与规则，不碰界面**。
好处是测试能脱离 tkinter 跑（``scripts/test_excel.py`` 是纯数据层套件，
在便携版 Python 上也能过），而界面层 ``excel_page`` 只消费这里的方法。

五张表
--------------------------------------------------------------------------------
``excel_functions``  函数库。内置 200 条 + 你自己加的；``code`` 唯一，种子靠它幂等。
``excel_progress``   掌握度与复习状态，1:1 挂在函数上（**懒创建**，没学过的函数不占行）。
``excel_recipes``    20 条实战配方（组合套路），也能写自己的心得。
``excel_notes``      我的笔记：可挂书页、可挂函数、可带截图。
``excel_checkins``   打卡：一天一行，``check_date`` 唯一。

两条设计取舍，值得写下来
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
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, timedelta

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

TABLES = (
    TABLE_FUNCTIONS,
    TABLE_PROGRESS,
    TABLE_RECIPES,
    TABLE_NOTES,
    TABLE_CHECKINS,
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


# ======================================================================
# 数据访问
# ======================================================================
class ExcelDB:
    """Excel 学习中心的数据入口。由 ``main`` 建一次并注入页面。"""

    def __init__(self, db_path, *, seed: bool = True):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
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
        self.conn.execute("DELETE FROM excel_functions WHERE id = ?", (int(function_id),))
        self.conn.commit()
        return True

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
