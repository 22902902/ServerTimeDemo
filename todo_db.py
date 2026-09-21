# -*- coding: utf-8 -*-
"""
================================================================================
待办事项模块 - 数据层（Data Layer）
================================================================================
本模块封装「待办 / 提醒事项」所需的全部持久化逻辑与**工作日日历**推算。
复用主程序的 SQLite 数据库文件（db_path 由调用方注入），与其余模块共享连接，
因此备份、迁移都只需处理一个文件。

┌─────────────────────────────────────────────────────────────────────────────┐
│  数据表设计                                                                  │
├────────────────┬────────────────────────────────────────────────────────────┤
│ todo_lists     │ 清单：名称、颜色（苹果 12 色之一）、图标、排序               │
│ todo_items     │ 待办条目：标题、备注、日期、时间、重复、优先级、旗标、标签   │
│ todo_subtasks  │ 子任务：挂在条目下的轻量清单项                             │
│ todo_holidays  │ 节假日日历：放假 / 调休上班两天都记在这一张表               │
│ todo_state     │ 模块内键值状态：上次工作日弹窗日期等                        │
└────────────────┴────────────────────────────────────────────────────────────┘

工作日语义（这层是「周末 / 节假日自动跳过」的全部依据）
--------------------------------------------------------------------------------
本模块把「工作日」定义为：**同时不是法定放假日、也不是周六周日**的那一天；
唯一的例外是**调休上班日** —— 它虽然落在周末，但因为被国务院安排上班，
所以算工作日。

因此日历表里 kind 有两种取值：
    holiday —— 法定放假（含调休连休里的周末），今天不上班
    workday —— 调休上班（通常是某个周六/周日），今天要上班

重复与顺延（对应「未完成自动进入明天」）
--------------------------------------------------------------------------------
* rollover() 在每天首次进入程序时跑一次：
    - 非重复项且已过期 → 顺延到今天（若今天是休假日则顺延到下一个工作日）
    - 重复项且已过期   → 直接推进到今天及以后的第一个周期日（同样跳过休假）
* 勾选**重复项**完成时不做「完成」标记，而是勾出一份 completed 快照留档，
  并把原条目推进到下一周期 —— 这样「每天 / 每周」的条目明天还在，
  同时「已完成」区里能看到每一次的完成记录（与苹果提醒事项行为一致）。

作者：代可行
日期：2026-09-21
================================================================================
"""

from __future__ import annotations

import calendar
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# =============================================================================
# 常量
# =============================================================================

# 苹果提醒事项的 12 色列表色（取自 iOS 18 自建列表取色盘）
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

DEFAULT_LIST_COLOR = "#007AFF"

# 清单可选图标（图标画法见 todo_icons.TILE_GLYPHS，两边的键必须一一对应）
LIST_ICONS: list[str] = [
    "list", "check", "star", "flag", "book", "bag", "key", "gift",
    "cake", "cap", "heart", "leaf", "pill", "dumbbell", "cart", "house",
    "music", "person", "phone", "sun",
]
DEFAULT_LIST_ICON = "list"

# 重复规则 → (步长, 单位)。custom 走 repeat_interval / repeat_unit 两列。
REPEAT_RULES: list[tuple[str, str]] = [
    ("none", "永不"),
    ("daily", "每天"),
    ("weekly", "每周"),
    ("biweekly", "每两周"),
    ("monthly", "每月"),
    ("yearly", "每年"),
    ("custom", "自定"),
]
REPEAT_LABELS = dict(REPEAT_RULES)
REPEAT_STEP = {
    "daily": (1, "day"),
    "weekly": (1, "week"),
    "biweekly": (2, "week"),
    "monthly": (1, "month"),
    "yearly": (1, "year"),
}

REPEAT_UNITS: list[tuple[str, str]] = [
    ("day", "天"), ("week", "周"), ("month", "个月"), ("year", "年"),
]

# 优先级：0 无 / 1 低 / 2 中 / 3 高，与苹果的 ! / !! / !!! 对应
PRIORITY_LABELS = {0: "无", 1: "低", 2: "中", 3: "高"}
PRIORITY_MARKS = {0: "", 1: "!", 2: "!!", 3: "!!!"}

# 智能分组（列表最上方那几张固定卡片）
SMART_LISTS: list[tuple[str, str]] = [
    ("today", "今天"),
    ("scheduled", "计划"),
    ("all", "全部"),
    ("flagged", "旗标"),
    ("completed", "已完成"),
]
SMART_LABELS = dict(SMART_LISTS)


# =============================================================================
# 内置节假日日历
# =============================================================================
# 数据来自《国务院办公厅关于 2026 年部分节假日安排的通知》
# （2025-11-04 发布，国办发明电）。只内置**已正式公布**的年份 ——
# 未公布的年份不猜，next_workday 对无数据的年份只跳周末，
# 用户可在界面上自行补充（次年安排通常在当年 11 月公布）。
#
# 格式：年份 → (放假区间列表, 调休上班日列表)
#   区间用 (起始日, 结束日, 节日名)，闭区间。
HOLIDAY_SEED: dict[int, tuple[list, list]] = {
    2026: (
        [
            ("2026-01-01", "2026-01-03", "元旦"),
            ("2026-02-15", "2026-02-23", "春节"),
            ("2026-04-04", "2026-04-06", "清明节"),
            ("2026-05-01", "2026-05-05", "劳动节"),
            ("2026-06-19", "2026-06-21", "端午节"),
            ("2026-09-25", "2026-09-27", "中秋节"),
            ("2026-10-01", "2026-10-07", "国庆节"),
        ],
        [
            "2026-01-04",
            "2026-02-14",
            "2026-02-28",
            "2026-05-09",
            "2026-09-20",
            "2026-10-10",
        ],
    ),
}

# 生成日历时最多向前向后搜索多少天（防御性上限，避免意外死循环）
_MAX_SCAN_DAYS = 400


# =============================================================================
# 辅助函数
# =============================================================================

def _norm(value) -> str:
    """把任意值规范化为去空白字符串；None 视作空串。"""
    if value is None:
        return ""
    return str(value).strip()


def _now() -> str:
    """当前时间的 ISO 字符串（精确到秒）。"""
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def parse_day(value) -> Optional[date]:
    """把 ``YYYY-MM-DD`` 解析为 date；空值或格式非法时返回 None。"""
    text = _norm(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def day_str(value: date) -> str:
    """date → ``YYYY-MM-DD``。"""
    return value.isoformat()


def add_months(base: date, months: int) -> date:
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


def _iter_range(start: str, end: str):
    """闭区间日期迭代器。"""
    cur, last = date.fromisoformat(start), date.fromisoformat(end)
    while cur <= last:
        yield cur
        cur += timedelta(days=1)


# =============================================================================
# 数据模型（Data Classes）
# =============================================================================

@dataclass
class TodoList:
    """清单（对应苹果的「列表」）。

    字段说明:
        id         - 主键
        name       - 清单名称
        color      - 列表色（十六进制，取值见 LIST_COLORS）
        icon       - 图标名（取值见 LIST_ICONS）
        sort_order - 排序号，越小越靠前
        created_at / updated_at - 创建与修改时间
    """
    id: int = 0
    name: str = ""
    color: str = DEFAULT_LIST_COLOR
    icon: str = DEFAULT_LIST_ICON
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TodoList":
        return cls(
            id=int(row["id"]),
            name=_norm(row["name"]),
            color=_norm(row["color"]) or DEFAULT_LIST_COLOR,
            icon=_norm(row["icon"]) or DEFAULT_LIST_ICON,
            sort_order=int(row["sort_order"] or 0),
            created_at=_norm(row["created_at"]),
            updated_at=_norm(row["updated_at"]),
        )


@dataclass
class TodoItem:
    """待办条目（对应苹果的「提醒事项」）。

    字段说明:
        id               - 主键
        list_id          - 所属清单
        title            - 标题（必填）
        notes            - 备注，支持多行（「点开有一个小型备忘录」就是这个字段）
        due_date         - 截止日期 ``YYYY-MM-DD``；空串表示未设置日期
        due_time         - 截止时间 ``HH:MM``；空串表示未设置时间
        repeat_rule      - 重复规则，见 REPEAT_RULES
        repeat_interval  - 自定重复的步长（repeat_rule='custom' 时生效）
        repeat_unit      - 自定重复的单位 day/week/month/year
        repeat_until     - 重复结束日期；空串表示永不结束
        skip_holidays    - 是否跳过周末与法定节假日（1/0）
        priority         - 优先级 0 无 / 1 低 / 2 中 / 3 高
        flagged          - 旗标 0/1
        tags             - 标签列表
        completed        - 是否已完成 0/1
        completed_at     - 完成时间
        is_repeat_copy   - 是否为「重复项完成时留下的快照」，快照不再参与顺延
        rollover_count   - 被顺延过多少次
        original_due_date- 首次顺延前的原始日期（用于展示「已顺延 N 次」）
        sort_order       - 手动排序号
        created_at / updated_at
    """
    id: int = 0
    list_id: int = 0
    title: str = ""
    notes: str = ""
    due_date: str = ""
    due_time: str = ""
    repeat_rule: str = "none"
    repeat_interval: int = 1
    repeat_unit: str = "week"
    repeat_until: str = ""
    skip_holidays: int = 1
    priority: int = 0
    flagged: int = 0
    tags: list[str] = field(default_factory=list)
    completed: int = 0
    completed_at: str = ""
    is_repeat_copy: int = 0
    rollover_count: int = 0
    original_due_date: str = ""
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""

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

    def tags_str(self) -> str:
        return " ".join(self.tags)

    @classmethod
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

        return cls(
            id=int(row["id"]),
            list_id=int(row["list_id"] or 0),
            title=_norm(row["title"]),
            notes=_norm(row["notes"]),
            due_date=_norm(row["due_date"]),
            due_time=_norm(row["due_time"]),
            repeat_rule=_norm(row["repeat_rule"]) or "none",
            repeat_interval=int(row["repeat_interval"] or 1),
            repeat_unit=_norm(row["repeat_unit"]) or "week",
            repeat_until=_norm(row["repeat_until"]),
            skip_holidays=int(row["skip_holidays"] or 0),
            priority=int(row["priority"] or 0),
            flagged=int(row["flagged"] or 0),
            tags=tags,
            completed=int(row["completed"] or 0),
            completed_at=_norm(row["completed_at"]),
            is_repeat_copy=int(row["is_repeat_copy"] or 0),
            rollover_count=int(row["rollover_count"] or 0),
            original_due_date=_norm(row["original_due_date"]),
            sort_order=int(row["sort_order"] or 0),
            created_at=_norm(row["created_at"]),
            updated_at=_norm(row["updated_at"]),
        )


@dataclass
class TodoSubtask:
    """子任务。"""
    id: int = 0
    item_id: int = 0
    title: str = ""
    completed: int = 0
    sort_order: int = 0
    created_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TodoSubtask":
        return cls(
            id=int(row["id"]),
            item_id=int(row["item_id"] or 0),
            title=_norm(row["title"]),
            completed=int(row["completed"] or 0),
            sort_order=int(row["sort_order"] or 0),
            created_at=_norm(row["created_at"]),
        )


@dataclass
class Holiday:
    """节假日日历中的一天。

    kind:
        holiday —— 法定放假（今天不上班）
        workday —— 调休上班（今天要上班）
    """
    day: str = ""
    name: str = ""
    kind: str = "holiday"

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Holiday":
        return cls(
            day=_norm(row["day"]),
            name=_norm(row["name"]),
            kind=_norm(row["kind"]) or "holiday",
        )


# =============================================================================
# 数据库操作类
# =============================================================================

class TodoDB:
    """待办模块的数据库操作类（含工作日日历推算）。

    使用示例::

        db = TodoDB(DB_PATH)
        db.rollover()                       # 每天首次进入时跑一次
        lists = db.fetch_lists()
        items = db.fetch_items(scope="today")
        db.set_completed(items[0].id, True)
        db.close()
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

    # --------------------------------------------------------------------------
    # 表结构
    # --------------------------------------------------------------------------

    def create_tables(self):
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

            /* 待办条目 */
            CREATE TABLE IF NOT EXISTS todo_items (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id           INTEGER NOT NULL,
                title             TEXT    NOT NULL DEFAULT '',
                notes             TEXT    NOT NULL DEFAULT '',
                due_date          TEXT    NOT NULL DEFAULT '',
                due_time          TEXT    NOT NULL DEFAULT '',
                repeat_rule       TEXT    NOT NULL DEFAULT 'none',
                repeat_interval   INTEGER NOT NULL DEFAULT 1,
                repeat_unit       TEXT    NOT NULL DEFAULT 'week',
                repeat_until      TEXT    NOT NULL DEFAULT '',
                skip_holidays     INTEGER NOT NULL DEFAULT 1,
                priority          INTEGER NOT NULL DEFAULT 0,
                flagged           INTEGER NOT NULL DEFAULT 0,
                tags              TEXT    NOT NULL DEFAULT '[]',
                completed         INTEGER NOT NULL DEFAULT 0,
                completed_at      TEXT    NOT NULL DEFAULT '',
                is_repeat_copy    INTEGER NOT NULL DEFAULT 0,
                rollover_count    INTEGER NOT NULL DEFAULT 0,
                original_due_date TEXT    NOT NULL DEFAULT '',
                sort_order        INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT    NOT NULL,
                updated_at        TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_todo_items_list
                ON todo_items (list_id, completed, due_date);

            /* 子任务 */
            CREATE TABLE IF NOT EXISTS todo_subtasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id     INTEGER NOT NULL,
                title       TEXT    NOT NULL DEFAULT '',
                completed   INTEGER NOT NULL DEFAULT 0,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_todo_subtasks_item
                ON todo_subtasks (item_id, sort_order);

            /* 节假日日历：放假与调休上班共用一表，靠 kind 区分 */
            CREATE TABLE IF NOT EXISTS todo_holidays (
                day   TEXT PRIMARY KEY,
                name  TEXT NOT NULL DEFAULT '',
                kind  TEXT NOT NULL DEFAULT 'holiday'
            );

            /* 模块内键值状态 */
            CREATE TABLE IF NOT EXISTS todo_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
        """)
        self.conn.commit()

    # --------------------------------------------------------------------------
    # 种子数据
    # --------------------------------------------------------------------------

    def seed_default_lists(self):
        """首次运行时给三个演示清单；已有清单则跳过。"""
        count = self.conn.execute("SELECT COUNT(1) FROM todo_lists").fetchone()[0]
        if count:
            return
        for name, color, icon in (
            ("提醒事项", "#AF52DE", "list"),
            ("工作", "#007AFF", "bag"),
            ("生活", "#34C759", "leaf"),
        ):
            self.add_list(name, color, icon)

    def seed_holidays(self):
        """把内置的官方节假日写入日历表（已存在同一天的记录不覆盖）。"""
        now_rows = self.conn.execute("SELECT COUNT(1) FROM todo_holidays").fetchone()[0]
        if now_rows:
            return
        records: list[tuple[str, str, str]] = []
        for _year, (spans, workdays) in HOLIDAY_SEED.items():
            for start, end, name in spans:
                for day in _iter_range(start, end):
                    records.append((day_str(day), name, "holiday"))
            for day in workdays:
                # 名称留空：界面上类型列已经写了「调休上班」，
                # 名称列再写一遍是重复
                records.append((day, "", "workday"))
        if not records:
            return
        self.conn.executemany(
            "INSERT OR IGNORE INTO todo_holidays (day, name, kind) VALUES (?, ?, ?)",
            records,
        )
        self.conn.commit()
        self._holidays_cache = None

    # --------------------------------------------------------------------------
    # 模块内状态
    # --------------------------------------------------------------------------

    def get_state(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM todo_state WHERE key = ?", (key,)
        ).fetchone()
        return _norm(row["value"]) if row else default

    def set_state(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO todo_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    # --------------------------------------------------------------------------
    # 节假日日历
    # --------------------------------------------------------------------------

    def fetch_holidays(self, year: Optional[int] = None) -> list[Holiday]:
        """取日历记录；year 为空时返回全部，按日期排序。"""
        if year is None:
            rows = self.conn.execute(
                "SELECT * FROM todo_holidays ORDER BY day ASC"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM todo_holidays WHERE day LIKE ? ORDER BY day ASC",
                (f"{year:04d}-%",),
            ).fetchall()
        return [Holiday.from_row(r) for r in rows]

    def holiday_map(self) -> dict[str, Holiday]:
        """日历缓存：day → Holiday。写操作会使其失效。"""
        if self._holidays_cache is None:
            self._holidays_cache = {h.day: h for h in self.fetch_holidays()}
        return self._holidays_cache

    def set_holiday(self, day: str, name: str, kind: str):
        """新增或覆盖某一天的日历记录。kind 只接受 holiday / workday。"""
        if kind not in ("holiday", "workday"):
            raise ValueError("kind 只能是 holiday 或 workday")
        self.conn.execute(
            "INSERT INTO todo_holidays (day, name, kind) VALUES (?, ?, ?) "
            "ON CONFLICT(day) DO UPDATE SET name = excluded.name, kind = excluded.kind",
            (day, name, kind),
        )
        self.conn.commit()
        self._holidays_cache = None

    def delete_holiday(self, day: str):
        self.conn.execute("DELETE FROM todo_holidays WHERE day = ?", (day,))
        self.conn.commit()
        self._holidays_cache = None

    def holiday_name(self, day) -> str:
        """取某天的节日名；普通周末返回「周末」，工作日返回空串。"""
        info = self.holiday_map().get(_norm(day))
        if info:
            return info.name
        d = parse_day(day)
        if d and d.weekday() >= 5:
            return "周末"
        return ""

    def is_workday(self, day) -> bool:
        """是否为工作日（调休上班日算工作日；法定放假与周六周日不算）。"""
        key = _norm(day)
        info = self.holiday_map().get(key)
        if info:
            return info.kind == "workday"
        d = parse_day(key)
        if d is None:
            return False
        return d.weekday() < 5

    def is_rest(self, day) -> bool:
        """是否为休息日（is_workday 的取反，供界面直接调用）。"""
        return not self.is_workday(day)

    def shift_to_workday(self, day) -> str:
        """若 day 本身是休息日，向后找到第一个工作日；否则原样返回。

        这是「周末或节假日，自动跳过」的实现：一条待办的日期落在周六，
        它会落到下周一（若周一放假则继续向后）。
        """
        base = parse_day(day)
        if base is None:
            return _norm(day)
        if self.is_workday(base):
            return day_str(base)
        return day_str(self.next_workday(base, include_self=False))

    def next_workday(self, day, *, include_self: bool = True) -> date:
        """向后取最近的工作日（默认含当天）。"""
        cur = parse_day(day)
        if cur is None:
            cur = date.today()
        if not include_self:
            cur += timedelta(days=1)
        for _ in range(_MAX_SCAN_DAYS):
            if self.is_workday(cur):
                return cur
            cur += timedelta(days=1)
        return cur

    def prev_workday(self, day, *, include_self: bool = True) -> date:
        """向前取最近的工作日（默认含当天）。用于判断「假期后第一个工作日」。"""
        cur = parse_day(day)
        if cur is None:
            cur = date.today()
        if not include_self:
            cur -= timedelta(days=1)
        for _ in range(_MAX_SCAN_DAYS):
            if self.is_workday(cur):
                return cur
            cur -= timedelta(days=1)
        return cur

    # --------------------------------------------------------------------------
    # 重复规则
    # --------------------------------------------------------------------------

    def next_occurrence(self, day, item: Optional[TodoItem] = None, *,
                        rule: str = "", interval: int = 1, unit: str = "week",
                        skip_holidays: bool = True) -> str:
        """返回 day 之后的**下一个**周期日（严格晚于 day）。

        参数既可以从 item 上取，也可以直接给（供测试与界面预览使用）。
        ``skip_holidays`` 为真且算出来的日子是休息日时，会继续向后落到工作日。
        """
        rule = rule or (item.repeat_rule if item else "none")
        if item is not None:
            interval = item.repeat_interval
            unit = item.repeat_unit
            skip_holidays = bool(item.skip_holidays)
        if rule == "none":
            return _norm(day)

        base = parse_day(day)
        if base is None:
            return _norm(day)

        step, step_unit = REPEAT_STEP.get(rule, (interval, unit))
        if rule == "custom":
            step, step_unit = max(1, int(interval or 1)), unit or "week"

        if step_unit == "day":
            nxt = base + timedelta(days=step)
        elif step_unit == "week":
            nxt = base + timedelta(weeks=step)
        elif step_unit == "month":
            nxt = add_months(base, step)
        elif step_unit == "year":
            nxt = add_years(base, step)
        else:
            nxt = base + timedelta(days=1)

        if skip_holidays:
            return self.shift_to_workday(nxt)
        return day_str(nxt)

    def advance_past(self, day, item: TodoItem, target: str) -> str:
        """把 day 按重复规则推进到 **>= target** 的第一个周期日。

        比逐日循环快得多，也避免「一条每天的待办逾期三年」这类情况
        需要上千次迭代。
        """
        rule = item.repeat_rule
        if rule == "none":
            return _norm(day)

        step, step_unit = REPEAT_STEP.get(rule, (item.repeat_interval, item.repeat_unit))
        if rule == "custom":
            step, step_unit = max(1, int(item.repeat_interval or 1)), item.repeat_unit or "week"

        base = parse_day(day)
        end = parse_day(target)
        if base is None or end is None:
            return _norm(day)

        # 先用除法一步跳到目标附近，再做少量逐周期修正
        if step_unit == "day":
            gap = (end - base).days
            if gap > 0:
                base = base + timedelta(days=(gap // step) * step)
        elif step_unit == "week":
            gap = (end - base).days
            if gap > 0:
                base = base + timedelta(weeks=(gap // (7 * step)) * step)
        elif step_unit == "month":
            months = (end.year - base.year) * 12 + (end.month - base.month)
            if months > 0:
                base = add_months(base, (months // step) * step)
        elif step_unit == "year":
            years = end.year - base.year
            if years > 0:
                base = add_years(base, (years // step) * step)

        guard = 0
        while base < end and guard < 64:
            nxt = self.next_occurrence(base, rule=rule, interval=step,
                                       unit=step_unit, skip_holidays=False)
            moved = parse_day(nxt)
            if moved is None or moved <= base:
                break
            base = moved
            guard += 1

        if item.skip_holidays:
            return self.shift_to_workday(base)
        return day_str(base)

    # --------------------------------------------------------------------------
    # 每日顺延
    # --------------------------------------------------------------------------

    def rollover(self, today: Optional[str] = None) -> dict:
        """把逾期未完成的待办顺延到「今天」。每天首次进入程序时调用一次。

        规则:
            * 非重复项 → 日期改为今天；今天若在放假则改为下一个工作日。
              顺延次数 +1，并首次记下原始日期。
            * 重复项   → 日期推进到今天及以后的第一个周期日（不再报逾期）。
              与苹果一致：重复项不会「欠账」，只会跳到下一次。

        返回 ``{"today": ..., "moved": 非重复顺延数, "advanced": 重复推进数}``。
        """
        today = _norm(today) or day_str(date.today())
        target = self.shift_to_workday(today)

        rows = self.conn.execute(
            "SELECT * FROM todo_items "
            "WHERE completed = 0 AND is_repeat_copy = 0 "
            "  AND due_date <> '' AND due_date < ?",
            (today,),
        ).fetchall()

        moved_items: list[TodoItem] = []
        advanced_items: list[TodoItem] = []
        now = _now()

        for row in rows:
            item = TodoItem.from_row(row)
            if item.repeat_rule != "none":
                new_day = self.advance_past(item.due_date, item, today)
                if new_day and new_day != item.due_date:
                    advanced_items.append(item)
                    self.conn.execute(
                        "UPDATE todo_items SET due_date = ?, updated_at = ? WHERE id = ?",
                        (new_day, now, item.id),
                    )
                continue

            if target == item.due_date:
                continue
            moved_items.append(item)
            self.conn.execute(
                "UPDATE todo_items "
                "SET due_date = ?, rollover_count = rollover_count + 1, "
                "    original_due_date = CASE WHEN original_due_date = '' "
                "                             THEN ? ELSE original_due_date END, "
                "    updated_at = ? "
                "WHERE id = ?",
                (target, item.due_date, now, item.id),
            )

        if moved_items or advanced_items:
            self.conn.commit()

        result = {
            "today": today,
            "target": target,
            "moved": len(moved_items),
            "advanced": len(advanced_items),
            "carried": [it.title for it in moved_items],
        }
        if moved_items or advanced_items:
            self.set_state("last_rollover_day", today)
        return result

    def workday_notice(self, today: Optional[str] = None) -> Optional[dict]:
        """判断今天是否需要弹「假期后第一个工作日」的汇总窗口。

        判定：今天是工作日，且**上一个工作日**距今天超过 1 个自然日
        （说明中间有周末或长假），并且今天还没弹过。

        返回 None 表示不需要弹；否则返回汇总信息，形如::

            {"today": "2026-10-08", "rest_days": 7, "gap_from": "2026-09-30",
             "today_count": 3, "carried_count": 2, "carried": [...]}
        """
        today = _norm(today) or day_str(date.today())
        base = parse_day(today)
        if base is None or not self.is_workday(base):
            return None
        if self.get_state("workday_notice_day") == today:
            return None

        prev = self.prev_workday(base, include_self=False)
        gap = (base - prev).days
        if gap <= 1:
            return None  # 昨天就是工作日，不是「假期后第一天」

        # 找出刚刚结束的那个假期名：扫描 prev 与 today 之间的休息日，
        # 取最后一个有名字的放假日（假期里的周末没有名字，会被自动跳过）。
        holiday_name = ""
        calendar_map = self.holiday_map()
        cursor = prev + timedelta(days=1)
        while cursor < base:
            info = calendar_map.get(day_str(cursor))
            if info and info.kind == "holiday" and info.name:
                holiday_name = info.name
            cursor += timedelta(days=1)

        carried = [it.title for it in self.fetch_items(scope="today", today=today)]
        return {
            "today": today,
            "rest_days": gap - 1,
            "gap_from": day_str(prev),
            "holiday_name": holiday_name or "假期",
            "today_count": len(carried),
            "carried": carried,
        }

    def ack_workday_notice(self, today: Optional[str] = None):
        """标记今天的汇总窗口已弹过。"""
        self.set_state("workday_notice_day", _norm(today) or day_str(date.today()))

    # --------------------------------------------------------------------------
    # 清单 CRUD
    # --------------------------------------------------------------------------

    def fetch_lists(self) -> list[TodoList]:
        rows = self.conn.execute(
            "SELECT * FROM todo_lists ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        return [TodoList.from_row(r) for r in rows]

    def get_list(self, list_id: int) -> Optional[TodoList]:
        row = self.conn.execute(
            "SELECT * FROM todo_lists WHERE id = ?", (list_id,)
        ).fetchone()
        return TodoList.from_row(row) if row else None

    def add_list(self, name: str, color: str = DEFAULT_LIST_COLOR,
                 icon: str = DEFAULT_LIST_ICON) -> int:
        now = _now()
        nxt = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM todo_lists"
        ).fetchone()[0]
        cursor = self.conn.execute(
            "INSERT INTO todo_lists (name, color, icon, sort_order, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_norm(name) or "新列表", color, icon, nxt, now, now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_list(self, list_id: int, *, name: Optional[str] = None,
                    color: Optional[str] = None, icon: Optional[str] = None,
                    sort_order: Optional[int] = None):
        """按需更新清单字段（只改传入的部分）。"""
        sets, params = [], []
        if name is not None:
            sets.append("name = ?")
            params.append(_norm(name) or "新列表")
        if color is not None:
            sets.append("color = ?")
            params.append(color)
        if icon is not None:
            sets.append("icon = ?")
            params.append(icon)
        if sort_order is not None:
            sets.append("sort_order = ?")
            params.append(int(sort_order))
        if not sets:
            return
        sets.append("updated_at = ?")
        params.extend([_now(), list_id])
        self.conn.execute(
            f"UPDATE todo_lists SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()

    def delete_list(self, list_id: int) -> tuple[int, int]:
        """删除清单，连同其下的待办与子任务。

        返回 ``(删除的待办数, 删除的子任务数)``。至少保留一个清单
        （只剩一个时拒绝删除，返回 ``(0, 0)``）。
        """
        if self.conn.execute("SELECT COUNT(1) FROM todo_lists").fetchone()[0] <= 1:
            return 0, 0
        subtasks = self.conn.execute(
            "SELECT COUNT(1) FROM todo_subtasks WHERE item_id IN "
            "(SELECT id FROM todo_items WHERE list_id = ?)", (list_id,)
        ).fetchone()[0]
        items = self.conn.execute(
            "SELECT COUNT(1) FROM todo_items WHERE list_id = ?", (list_id,)
        ).fetchone()[0]
        self.conn.execute(
            "DELETE FROM todo_subtasks WHERE item_id IN "
            "(SELECT id FROM todo_items WHERE list_id = ?)", (list_id,)
        )
        self.conn.execute("DELETE FROM todo_items WHERE list_id = ?", (list_id,))
        self.conn.execute("DELETE FROM todo_lists WHERE id = ?", (list_id,))
        self.conn.commit()
        return int(items), int(subtasks)

    def open_count_by_list(self) -> dict[int, int]:
        """每个清单下未完成的待办数量（侧栏计数）。

        重复项完成时留下的是快照（is_repeat_copy=1），原条目仍未完成，
        因此这里天然只统计「还欠着的活」。
        """
        rows = self.conn.execute(
            "SELECT list_id, COUNT(1) AS n FROM todo_items "
            "WHERE completed = 0 GROUP BY list_id"
        ).fetchall()
        return {int(r["list_id"]): int(r["n"]) for r in rows}

    # --------------------------------------------------------------------------
    # 待办 CRUD
    # --------------------------------------------------------------------------

    def _items_order_by(self, scope: str) -> str:
        """不同视图的排序：今天视图按时间点，其余按日期，已完成一律沉底。"""
        head = (
            # 已完成先分档沉底：开了「显示已完成」后它们是一整段，不会夹在
            # 未完成项中间。同一档内再按日期 / 时间点排。
            "CASE WHEN completed = 1 THEN 1 ELSE 0 END ASC, "
            "CASE WHEN due_date = '' THEN 1 ELSE 0 END ASC, due_date ASC, "
            "CASE WHEN due_time = '' THEN 1 ELSE 0 END ASC, due_time ASC, "
        )
        tail = (
            "priority DESC, sort_order ASC, updated_at DESC, id DESC"
        )
        return head + tail

    def fetch_items(self, *, scope: str = "all", list_id: Optional[int] = None,
                    keyword: str = "", today: Optional[str] = None,
                    include_completed: Optional[bool] = None) -> list[TodoItem]:
        """按视图取待办列表。

        scope:
            today     —— 今天（含逾期）：日期 <= 今天且未完成
            scheduled —— 计划：凡是设了日期的未完成项
            all       —— 全部：所有未完成项
            flagged   —— 旗标：打了旗标的未完成项
            completed —— 已完成
            list      —— 指定清单（由 list_id 决定）
        include_completed=True 时，除「已完成」视图外都连带显示已完成项
        （界面上的「显示已完成」开关传的就是它）；缺省只看未完成。
        """
        today = today or day_str(date.today())
        sql = "SELECT * FROM todo_items WHERE 1=1"
        params: list = []

        if list_id:
            sql += " AND list_id = ?"
            params.append(int(list_id))

        if scope == "today":
            sql += " AND due_date <> '' AND due_date <= ?"
            params.append(today)
        elif scope == "scheduled":
            sql += " AND due_date <> ''"
        elif scope == "flagged":
            sql += " AND flagged = 1"
        elif scope == "completed":
            sql += " AND completed = 1"
        # else: all / list —— 这里不加条件，要不要连带由下面统一决定

        # 「已完成」视图本身就是只看已完成；其余视图一律由 include_completed
        # 决定连带与否。原先把 completed = 0 写死在各分支里，于是「今天 /
        # 计划 / 旗标」这几个智能分组根本没法显示已完成项。
        if scope != "completed" and not include_completed:
            sql += " AND completed = 0"

        if keyword:
            like = f"%{keyword}%"
            sql += " AND (title LIKE ? OR notes LIKE ? OR tags LIKE ?)"
            params.extend([like, like, like])

        sql += " ORDER BY " + self._items_order_by(scope)
        rows = self.conn.execute(sql, params).fetchall()
        return [TodoItem.from_row(r) for r in rows]

    def get_item(self, item_id: int) -> Optional[TodoItem]:
        row = self.conn.execute(
            "SELECT * FROM todo_items WHERE id = ?", (item_id,)
        ).fetchone()
        return TodoItem.from_row(row) if row else None

    def add_item(self, payload: dict) -> int:
        """新增待办。

        必需字段：title；其余字段可选（list_id 缺省落到第一个清单）。
        日期会自动跳过周末与节假日（skip_holidays=1 时）。
        """
        now = _now()
        list_id = int(payload.get("list_id") or 0)
        if not list_id:
            row = self.conn.execute(
                "SELECT id FROM todo_lists ORDER BY sort_order ASC, id ASC LIMIT 1"
            ).fetchone()
            list_id = int(row["id"]) if row else 0

        due_date = _norm(payload.get("due_date"))
        skip_holidays = 1 if payload.get("skip_holidays", 1) else 0
        repeat_rule = _norm(payload.get("repeat_rule")) or "none"
        # 只有「单次待办」才做日期跳过；重复项的跳过交给下一次推进时处理
        if due_date and skip_holidays and repeat_rule == "none":
            due_date = self.shift_to_workday(due_date)

        nxt = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM todo_items WHERE list_id = ?",
            (list_id,),
        ).fetchone()[0]

        cursor = self.conn.execute(
            """INSERT INTO todo_items
               (list_id, title, notes, due_date, due_time, repeat_rule,
                repeat_interval, repeat_unit, repeat_until, skip_holidays,
                priority, flagged, tags, completed, completed_at, is_repeat_copy,
                rollover_count, original_due_date, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', 0, 0, '', ?, ?, ?)""",
            (
                list_id,
                _norm(payload.get("title")),
                _norm(payload.get("notes")),
                due_date,
                _norm(payload.get("due_time")),
                repeat_rule,
                int(payload.get("repeat_interval") or 1),
                _norm(payload.get("repeat_unit")) or "week",
                _norm(payload.get("repeat_until")),
                skip_holidays,
                int(payload.get("priority") or 0),
                1 if payload.get("flagged") else 0,
                json.dumps(payload.get("tags", []), ensure_ascii=False),
                nxt, now, now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_item(self, item_id: int, payload: dict):
        """按需更新待办字段（只改 payload 里出现的键）。"""
        allowed = {
            "list_id", "title", "notes", "due_date", "due_time", "repeat_rule",
            "repeat_interval", "repeat_unit", "repeat_until", "skip_holidays",
            "priority", "flagged", "tags", "sort_order",
        }
        sets, params = [], []
        for key in allowed:
            if key not in payload:
                continue
            value = payload[key]
            if key == "tags":
                value = json.dumps(value or [], ensure_ascii=False)
            elif key == "flagged":
                value = 1 if value else 0
            elif key == "skip_holidays":
                value = 1 if value else 0
            elif key in ("list_id", "repeat_interval", "priority", "sort_order"):
                value = int(value or 0)
            else:
                value = _norm(value)
            sets.append(f"{key} = ?")
            params.append(value)

        if not sets:
            return
        sets.append("updated_at = ?")
        params.extend([_now(), item_id])
        self.conn.execute(
            f"UPDATE todo_items SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()

    def delete_item(self, item_id: int):
        """删除待办及其子任务。"""
        self.conn.execute("DELETE FROM todo_subtasks WHERE item_id = ?", (item_id,))
        self.conn.execute("DELETE FROM todo_items WHERE id = ?", (item_id,))
        self.conn.commit()

    # -- 勾选 ---------------------------------------------------------------

    def set_completed(self, item_id: int, completed: bool,
                      today: Optional[str] = None) -> dict:
        """勾选 / 取消勾选。

        * 非重复项：直接标记 completed；取消勾选会清掉完成时间。
        * 重复项勾选完成时：**不改原条目**，而是插一条 completed 快照留档，
          再把原条目推进到下一周期 —— 于是「每天」的条目明天还在，
          而「已完成」区里能看到这一次的完成记录（苹果的行为）。
          取消勾选对重复项不适用（它从未被标记为完成），返回 noop。

        返回 ``{"action": "done"|"undone"|"spawn", "next_due": "..."}``。
        """
        item = self.get_item(item_id)
        if item is None:
            return {"action": "noop"}

        now = _now()
        today = _norm(today) or day_str(date.today())

        if not completed:
            self.conn.execute(
                "UPDATE todo_items SET completed = 0, completed_at = '', updated_at = ? "
                "WHERE id = ?",
                (now, item_id),
            )
            self.conn.commit()
            return {"action": "undone"}

        is_repeating = (
            item.repeat_rule != "none"
            and not item.is_repeat_copy
            and bool(_norm(item.due_date))
        )
        if not is_repeating:
            self.conn.execute(
                "UPDATE todo_items SET completed = 1, completed_at = ?, updated_at = ? "
                "WHERE id = ?",
                (now, now, item_id),
            )
            self.conn.commit()
            return {"action": "done"}

        # 重复项：留快照 + 推进原条目
        next_due = self.next_occurrence(item.due_date, item)
        until = _norm(item.repeat_until)
        ended = bool(until) and bool(next_due) and next_due > until

        cursor = self.conn.execute(
            """INSERT INTO todo_items
               (list_id, title, notes, due_date, due_time, repeat_rule,
                repeat_interval, repeat_unit, repeat_until, skip_holidays,
                priority, flagged, tags, completed, completed_at, is_repeat_copy,
                rollover_count, original_due_date, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?, ?, ?, ?)""",
            (
                item.list_id, item.title, item.notes, item.due_date, item.due_time,
                item.repeat_rule, item.repeat_interval, item.repeat_unit,
                item.repeat_until, item.skip_holidays, item.priority, item.flagged,
                json.dumps(item.tags, ensure_ascii=False), now,
                item.rollover_count, item.original_due_date, item.sort_order,
                now, now,
            ),
        )
        copy_id = int(cursor.lastrowid)
        for sub in self.fetch_subtasks(item_id):
            self.conn.execute(
                "INSERT INTO todo_subtasks (item_id, title, completed, sort_order, created_at) "
                "VALUES (?, ?, 1, ?, ?)",
                (copy_id, sub.title, sub.sort_order, now),
            )
            self.conn.execute(
                "UPDATE todo_subtasks SET completed = 1 WHERE id = ?", (sub.id,)
            )

        if ended:
            # 重复已到最后一天：原条目转为「已完成」，不留一个空壳
            self.conn.execute(
                "UPDATE todo_items SET completed = 1, completed_at = ?, updated_at = ? "
                "WHERE id = ?",
                (now, now, item_id),
            )
            next_due = ""
        else:
            self.conn.execute(
                "UPDATE todo_items SET due_date = ?, updated_at = ? WHERE id = ?",
                (next_due, now, item_id),
            )
        self.conn.commit()
        return {"action": "spawn", "next_due": next_due, "copy_id": copy_id}

    def toggle_flag(self, item_id: int) -> int:
        """切换旗标，返回切换后的值。"""
        item = self.get_item(item_id)
        if item is None:
            return 0
        value = 0 if item.flagged else 1
        self.conn.execute(
            "UPDATE todo_items SET flagged = ?, updated_at = ? WHERE id = ?",
            (value, _now(), item_id),
        )
        self.conn.commit()
        return value

    # --------------------------------------------------------------------------
    # 子任务 CRUD
    # --------------------------------------------------------------------------

    def fetch_subtasks(self, item_id: int) -> list[TodoSubtask]:
        rows = self.conn.execute(
            "SELECT * FROM todo_subtasks WHERE item_id = ? "
            "ORDER BY sort_order ASC, id ASC",
            (item_id,),
        ).fetchall()
        return [TodoSubtask.from_row(r) for r in rows]

    def subtask_summary(self, item_ids: list[int]) -> dict[int, tuple[int, int]]:
        """批量取子任务进度 ``{item_id: (已完成, 总数)}``，供列表行显示。"""
        if not item_ids:
            return {}
        marks = ",".join("?" * len(item_ids))
        rows = self.conn.execute(
            f"SELECT item_id, COUNT(1) AS total, "
            f"       SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS done "
            f"FROM todo_subtasks WHERE item_id IN ({marks}) GROUP BY item_id",
            item_ids,
        ).fetchall()
        return {
            int(r["item_id"]): (int(r["done"] or 0), int(r["total"] or 0))
            for r in rows
        }

    def add_subtask(self, item_id: int, title: str) -> int:
        now = _now()
        nxt = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM todo_subtasks WHERE item_id = ?",
            (item_id,),
        ).fetchone()[0]
        cursor = self.conn.execute(
            "INSERT INTO todo_subtasks (item_id, title, completed, sort_order, created_at) "
            "VALUES (?, ?, 0, ?, ?)",
            (item_id, _norm(title), nxt, now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def set_subtask_completed(self, subtask_id: int, completed: bool):
        self.conn.execute(
            "UPDATE todo_subtasks SET completed = ? WHERE id = ?",
            (1 if completed else 0, subtask_id),
        )
        self.conn.commit()

    def delete_subtask(self, subtask_id: int):
        self.conn.execute("DELETE FROM todo_subtasks WHERE id = ?", (subtask_id,))
        self.conn.commit()

    # --------------------------------------------------------------------------
    # 统计
    # --------------------------------------------------------------------------

    def count_by_scope(self, today: Optional[str] = None) -> dict[str, int]:
        """智能分组卡片上的计数。"""
        today = today or day_str(date.today())
        row = self.conn.execute(
            "SELECT "
            " SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) AS all_open, "
            " SUM(CASE WHEN completed = 0 AND due_date <> '' AND due_date <= ? "
            "          THEN 1 ELSE 0 END) AS today_open, "
            " SUM(CASE WHEN completed = 0 AND due_date <> '' THEN 1 ELSE 0 END) AS scheduled, "
            " SUM(CASE WHEN completed = 0 AND flagged = 1 THEN 1 ELSE 0 END) AS flagged, "
            " SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS completed "
            "FROM todo_items WHERE is_repeat_copy = 0 OR completed = 1",
            (today,),
        ).fetchone()
        return {
            "today": int(row["today_open"] or 0),
            "scheduled": int(row["scheduled"] or 0),
            "all": int(row["all_open"] or 0),
            "flagged": int(row["flagged"] or 0),
            "completed": int(row["completed"] or 0),
        }

    def all_tags(self) -> list[str]:
        """全库出现过的标签（去重后按字母序）。"""
        rows = self.conn.execute(
            "SELECT tags FROM todo_items WHERE tags <> '[]'"
        ).fetchall()
        seen: set[str] = set()
        for r in rows:
            try:
                for tag in json.loads(r["tags"]):
                    text = _norm(tag)
                    if text:
                        seen.add(text)
            except Exception:
                continue
        return sorted(seen)

    def close(self):
        """关闭数据库连接（由 main.py 的 exit_app 统一调用）。"""
        try:
            self.conn.close()
        except Exception:
            pass
