# -*- coding: utf-8 -*-
"""
================================================================================
Q&A 问答 + 每周工作纪要 + 练习记录 数据层
================================================================================

数据表设计:
┌─────────────────┬────────────────────────────────────────────────────────────┐
│ qa_items        │ Q&A 问答表：项目/事件/流程维度的问答记录                      │
│                 │ 字段: id, scope(工作/生活), category(项目/事件/流程),        │
│                 │       ref_name(关联名称), question, answer, tags, created_at │
├─────────────────┼────────────────────────────────────────────────────────────┤
│ weekly_logs     │ 每周工作纪要表：周一到周五记录，周六归档                      │
│                 │ 字段: id, week_start(周一日期), day(1-5), content,           │
│                 │       is_archived, created_at, updated_at                    │
├─────────────────┼────────────────────────────────────────────────────────────┤
│ practice_logs   │ 练习记录表：记忆宫殿/Git/Linux 等每日练习打卡                 │
│                 │ 字段: id, practice_date, category(记忆宫殿/Git/Linux/自定义), │
│                 │       title, content, tags, created_at                       │
└─────────────────┴────────────────────────────────────────────────────────────┘
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List


def _now() -> str:
    """返回当前时间的 ISO 格式字符串"""
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    """返回今天日期字符串 YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


def _monday_of_week(date_str: str = None) -> str:
    """获取指定日期所在周的周一日期"""
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        d = datetime.now()
    monday = d - timedelta(days=d.weekday())
    return monday.strftime("%Y-%m-%d")


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class QAItem:
    """Q&A 问答实体"""
    id: int = 0
    scope: str = ""           # 工作 / 生活
    category: str = ""        # 项目 / 事件 / 流程
    ref_name: str = ""        # 关联名称（项目名称/事件名/流程名）
    question: str = ""        # 问题
    answer: str = ""          # 答案
    tags: str = ""            # 标签，逗号分隔
    created_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "QAItem":
        return cls(
            id=row["id"],
            scope=row["scope"],
            category=row["category"],
            ref_name=row["ref_name"],
            question=row["question"],
            answer=row["answer"],
            tags=row["tags"],
            created_at=row["created_at"],
        )


@dataclass
class WeeklyLog:
    """每周工作纪要实体"""
    id: int = 0
    week_start: str = ""      # 本周一日期 YYYY-MM-DD
    day: int = 1              # 1=周一, 2=周二, ..., 5=周五
    content: str = ""         # 纪要内容
    is_archived: bool = False # 是否已归档
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "WeeklyLog":
        return cls(
            id=row["id"],
            week_start=row["week_start"],
            day=row["day"],
            content=row["content"],
            is_archived=bool(row["is_archived"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass
class PracticeLog:
    """练习记录实体"""
    id: int = 0
    practice_date: str = ""   # 练习日期 YYYY-MM-DD
    category: str = ""        # 记忆宫殿 / Git / Linux / 自定义
    title: str = ""           # 标题
    content: str = ""         # 详细内容
    tags: str = ""            # 标签
    images: str = ""          # 图片路径，多张用 | 分隔
    created_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PracticeLog":
        return cls(
            id=row["id"],
            practice_date=row["practice_date"],
            category=row["category"],
            title=row["title"],
            content=row["content"],
            tags=row["tags"],
            images=row["images"] if "images" in row.keys() else "",
            created_at=row["created_at"],
        )


# =============================================================================
# 数据库操作类
# =============================================================================

class QAWorkLogDB:
    """Q&A + 工作纪要 + 练习记录 数据库操作类"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """初始化数据表"""
        with self._connect() as conn:
            # Q&A 问答表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS qa_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL DEFAULT '工作',
                    category TEXT NOT NULL DEFAULT '项目',
                    ref_name TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL DEFAULT '',
                    tags TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_scope ON qa_items(scope)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_category ON qa_items(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_ref ON qa_items(ref_name)")

            # 每周工作纪要表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_start TEXT NOT NULL,
                    day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 5),
                    content TEXT NOT NULL DEFAULT '',
                    is_archived INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(week_start, day)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_weekly_start ON weekly_logs(week_start)")

            # 练习记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS practice_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    practice_date TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    tags TEXT DEFAULT '',
                    images TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 兼容旧库：检测并添加 images 列
            cols = [r[1] for r in conn.execute("PRAGMA table_info(practice_logs)").fetchall()]
            if "images" not in cols:
                conn.execute("ALTER TABLE practice_logs ADD COLUMN images TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_practice_date ON practice_logs(practice_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_practice_cat ON practice_logs(category)")

            # 工作笔记表（结构化：标题/正文/TAG/关联练习）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS work_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    tags TEXT DEFAULT '',
                    linked_practice_id INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_notes_created ON work_notes(created_at)")

            # 复习心得表（通过 tags 或 linked_practice_id 关联原练习）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS practice_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    practice_id INTEGER DEFAULT 0,
                    review_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    tags TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_practice ON practice_reviews(practice_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_date ON practice_reviews(review_date)")

    # ==========================================================================
    # Q&A 问答 CRUD
    # ==========================================================================

    def add_qa(self, item: QAItem) -> int:
        """添加问答"""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO qa_items (scope, category, ref_name, question, answer, tags, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (item.scope, item.category, item.ref_name, item.question, item.answer, item.tags, _now())
            )
            return cursor.lastrowid

    def update_qa(self, item: QAItem) -> bool:
        """更新问答"""
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE qa_items SET scope=?, category=?, ref_name=?, question=?, answer=?, tags=?
                   WHERE id=?""",
                (item.scope, item.category, item.ref_name, item.question, item.answer, item.tags, item.id)
            )
            return cursor.rowcount > 0

    def delete_qa(self, qa_id: int) -> bool:
        """删除问答"""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM qa_items WHERE id=?", (qa_id,))
            return cursor.rowcount > 0

    def get_qa(self, qa_id: int) -> Optional[QAItem]:
        """获取单个问答"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM qa_items WHERE id=?", (qa_id,)).fetchone()
            return QAItem.from_row(row) if row else None

    def list_qa(self, scope: str = None, category: str = None, ref_name: str = None, keyword: str = None) -> List[QAItem]:
        """列表查询，支持筛选"""
        sql = "SELECT * FROM qa_items WHERE 1=1"
        params = []
        if scope:
            sql += " AND scope=?"
            params.append(scope)
        if category:
            sql += " AND category=?"
            params.append(category)
        if ref_name:
            sql += " AND ref_name LIKE ?"
            params.append(f"%{ref_name}%")
        if keyword:
            sql += " AND (question LIKE ? OR answer LIKE ? OR tags LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [QAItem.from_row(r) for r in rows]

    # ==========================================================================
    # 每周工作纪要 CRUD
    # ==========================================================================

    def get_or_create_weekly_log(self, day: int, week_start: str = None) -> WeeklyLog:
        """获取或创建某天的纪要"""
        if week_start is None:
            week_start = _monday_of_week()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM weekly_logs WHERE week_start=? AND day=?",
                (week_start, day)
            ).fetchone()
            if row:
                return WeeklyLog.from_row(row)
            # 创建新的
            conn.execute(
                "INSERT INTO weekly_logs (week_start, day, content, is_archived) VALUES (?, ?, '', 0)",
                (week_start, day)
            )
            return self.get_or_create_weekly_log(day, week_start)

    def update_weekly_log(self, log_id: int, content: str) -> bool:
        """更新纪要内容"""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE weekly_logs SET content=?, updated_at=? WHERE id=?",
                (content, _now(), log_id)
            )
            return cursor.rowcount > 0

    def get_current_week_logs(self) -> List[WeeklyLog]:
        """获取本周所有纪要（周一到周五）"""
        week_start = _monday_of_week()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM weekly_logs WHERE week_start=? ORDER BY day",
                (week_start,)
            ).fetchall()
            return [WeeklyLog.from_row(r) for r in rows]

    def archive_week(self, week_start: str = None) -> bool:
        """归档整周纪要"""
        if week_start is None:
            week_start = _monday_of_week()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE weekly_logs SET is_archived=1 WHERE week_start=?",
                (week_start,)
            )
            return cursor.rowcount > 0

    def list_archived_weeks(self) -> List[str]:
        """获取所有已归档的周"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT week_start FROM weekly_logs WHERE is_archived=1 ORDER BY week_start DESC"
            ).fetchall()
            return [r["week_start"] for r in rows]

    def get_week_logs(self, week_start: str) -> List[WeeklyLog]:
        """获取指定周的所有纪要"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM weekly_logs WHERE week_start=? ORDER BY day",
                (week_start,)
            ).fetchall()
            return [WeeklyLog.from_row(r) for r in rows]

    def auto_archive_if_saturday(self) -> bool:
        """如果是周六，自动归档本周"""
        if datetime.now().weekday() == 5:  # 周六
            return self.archive_week()
        return False

    # ==========================================================================
    # 练习记录 CRUD
    # ==========================================================================

    def add_practice(self, log: PracticeLog) -> int:
        """添加练习记录"""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO practice_logs (practice_date, category, title, content, tags, images, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (log.practice_date or _today(), log.category, log.title, log.content, log.tags, log.images, _now())
            )
            return cursor.lastrowid

    def update_practice(self, log: PracticeLog) -> bool:
        """更新练习记录"""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE practice_logs SET practice_date=?, category=?, title=?, content=?, tags=?, images=? WHERE id=?",
                (log.practice_date, log.category, log.title, log.content, log.tags, log.images, log.id)
            )
            return cursor.rowcount > 0

    def delete_practice(self, log_id: int) -> bool:
        """删除练习记录"""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM practice_logs WHERE id=?", (log_id,))
            return cursor.rowcount > 0

    def get_practice(self, log_id: int) -> Optional[PracticeLog]:
        """获取单条练习记录"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM practice_logs WHERE id=?", (log_id,)).fetchone()
            return PracticeLog.from_row(row) if row else None

    def list_practices(self, category: str = None, date_from: str = None, date_to: str = None, keyword: str = None) -> List[PracticeLog]:
        """列表查询"""
        sql = "SELECT * FROM practice_logs WHERE 1=1"
        params = []
        if category:
            sql += " AND category=?"
            params.append(category)
        if date_from:
            sql += " AND practice_date>=?"
            params.append(date_from)
        if date_to:
            sql += " AND practice_date<=?"
            params.append(date_to)
        if keyword:
            sql += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        sql += " ORDER BY practice_date DESC, created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [PracticeLog.from_row(r) for r in rows]

    def get_today_practices(self) -> List[PracticeLog]:
        """获取今日练习记录"""
        return self.list_practices(date_from=_today(), date_to=_today())

    def get_practice_stats(self, days: int = 30) -> dict:
        """获取最近 N 天练习统计"""
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT category, COUNT(*) as cnt FROM practice_logs
                   WHERE practice_date>=? GROUP BY category""",
                (from_date,)
            ).fetchall()
            return {r["category"]: r["cnt"] for r in rows}

    def close(self):
        """关闭数据库（SQLite 无需显式关闭连接，保留接口统一）"""
        pass


# =============================================================================
# 工作笔记实体
# =============================================================================

@dataclass
class WorkNote:
    """工作笔记实体（结构化：标题/正文/TAG/关联练习）"""
    id: int = 0
    title: str = ""
    content: str = ""
    tags: str = ""
    linked_practice_id: int = 0
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "WorkNote":
        return cls(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            tags=row["tags"],
            linked_practice_id=row["linked_practice_id"] if row["linked_practice_id"] else 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass
class PracticeReview:
    """复习心得实体（通过 linked_practice_id 或 tags 关联原练习）"""
    id: int = 0
    practice_id: int = 0
    review_date: str = ""
    title: str = ""
    content: str = ""
    tags: str = ""
    created_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PracticeReview":
        return cls(
            id=row["id"],
            practice_id=row["practice_id"] if row["practice_id"] else 0,
            review_date=row["review_date"],
            title=row["title"],
            content=row["content"],
            tags=row["tags"],
            created_at=row["created_at"],
        )


@dataclass
class GlobalSearchResult:
    """全局搜索结果"""
    table: str = ""       # practice / work_note / review / qa
    record_id: int = 0
    title: str = ""
    snippet: str = ""     # 高亮片段
    tags: str = ""
    date_str: str = ""    # 用于显示的时间字段


# =============================================================================
# 扩展数据库方法：工作笔记 + 复习心得 + 全局搜索
# =============================================================================

class QAWorkLogDBExt(QAWorkLogDB):
    """QAWorkLogDB 扩展：工作笔记、复习心得、全局搜索"""

    # ---- 工作笔记 CRUD ----

    def add_work_note(self, note: WorkNote) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO work_notes (title, content, tags, linked_practice_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (note.title, note.content, note.tags, note.linked_practice_id, _now(), _now())
            )
            return cur.lastrowid

    def update_work_note(self, note: WorkNote) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE work_notes SET title=?, content=?, tags=?, linked_practice_id=?, updated_at=?
                   WHERE id=?""",
                (note.title, note.content, note.tags, note.linked_practice_id, _now(), note.id)
            )
            return cur.rowcount > 0

    def delete_work_note(self, note_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM work_notes WHERE id=?", (note_id,))
            return cur.rowcount > 0

    def get_work_note(self, note_id: int) -> Optional[WorkNote]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM work_notes WHERE id=?", (note_id,)).fetchone()
            return WorkNote.from_row(row) if row else None

    def list_work_notes(self, keyword: str = None, tag: str = None) -> List[WorkNote]:
        sql = "SELECT * FROM work_notes WHERE 1=1"
        params = []
        if keyword:
            sql += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
            params.extend([f"%{keyword}%"] * 3)
        if tag:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        sql += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [WorkNote.from_row(r) for r in rows]

    # ---- 复习心得 CRUD ----

    def add_review(self, review: PracticeReview) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO practice_reviews (practice_id, review_date, title, content, tags, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (review.practice_id, review.review_date or _today(), review.title, review.content, review.tags, _now())
            )
            return cur.lastrowid

    def update_review(self, review: PracticeReview) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE practice_reviews SET practice_id=?, review_date=?, title=?, content=?, tags=?
                   WHERE id=?""",
                (review.practice_id, review.review_date, review.title, review.content, review.tags, review.id)
            )
            return cur.rowcount > 0

    def delete_review(self, review_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM practice_reviews WHERE id=?", (review_id,))
            return cur.rowcount > 0

    def list_reviews_by_practice(self, practice_id: int) -> List[PracticeReview]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM practice_reviews WHERE practice_id=? ORDER BY review_date DESC",
                (practice_id,)
            ).fetchall()
            return [PracticeReview.from_row(r) for r in rows]

    def list_reviews_by_tag(self, tag: str) -> List[PracticeReview]:
        """通过 tag 反查复习心得（复用 TAG 关联）"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM practice_reviews WHERE tags LIKE ? ORDER BY review_date DESC",
                (f"%{tag}%",)
            ).fetchall()
            return [PracticeReview.from_row(r) for r in rows]

    # ---- 全局模糊搜索 ----

    def global_search(self, keyword: str) -> List[GlobalSearchResult]:
        """
        跨表模糊搜索：练习记录/工作笔记/复习心得/Q&A
        搜索范围：标题、正文、TAG、时间字段（YYYY-MM-DD 形式可命中）
        """
        if not keyword or not keyword.strip():
            return []
        kw = keyword.strip()
        like = f"%{kw}%"
        results: List[GlobalSearchResult] = []

        with self._connect() as conn:
            # 1. 练习记录
            rows = conn.execute(
                """SELECT id, title, content, tags, practice_date as dt FROM practice_logs
                   WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? OR practice_date LIKE ?
                   ORDER BY practice_date DESC LIMIT 100""",
                (like, like, like, like)
            ).fetchall()
            for r in rows:
                results.append(GlobalSearchResult(
                    table="practice", record_id=r["id"],
                    title=r["title"], snippet=_make_snippet(r["content"], kw),
                    tags=r["tags"], date_str=r["dt"]
                ))
            # 2. 工作笔记
            rows = conn.execute(
                """SELECT id, title, content, tags, updated_at as dt FROM work_notes
                   WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
                   ORDER BY updated_at DESC LIMIT 100""",
                (like, like, like)
            ).fetchall()
            for r in rows:
                results.append(GlobalSearchResult(
                    table="work_note", record_id=r["id"],
                    title=r["title"], snippet=_make_snippet(r["content"], kw),
                    tags=r["tags"], date_str=r["dt"]
                ))
            # 3. 复习心得
            rows = conn.execute(
                """SELECT id, title, content, tags, review_date as dt FROM practice_reviews
                   WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? OR review_date LIKE ?
                   ORDER BY review_date DESC LIMIT 100""",
                (like, like, like, like)
            ).fetchall()
            for r in rows:
                results.append(GlobalSearchResult(
                    table="review", record_id=r["id"],
                    title=r["title"], snippet=_make_snippet(r["content"], kw),
                    tags=r["tags"], date_str=r["dt"]
                ))
            # 4. Q&A
            rows = conn.execute(
                """SELECT id, question as title, answer as content, tags, created_at as dt FROM qa_items
                   WHERE question LIKE ? OR answer LIKE ? OR tags LIKE ? OR ref_name LIKE ?
                   ORDER BY created_at DESC LIMIT 100""",
                (like, like, like, like)
            ).fetchall()
            for r in rows:
                results.append(GlobalSearchResult(
                    table="qa", record_id=r["id"],
                    title=r["title"], snippet=_make_snippet(r["content"], kw),
                    tags=r["tags"], date_str=r["dt"]
                ))
        return results

    def get_related_records(self, tags: str) -> dict:
        """通过 TAG 反查所有关联记录（练习/笔记/心得/Q&A）"""
        if not tags:
            return {"practices": [], "notes": [], "reviews": [], "qas": []}
        tag_list = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
        if not tag_list:
            return {"practices": [], "notes": [], "reviews": [], "qas": []}
        like_clauses = " OR ".join(["tags LIKE ?"] * len(tag_list))
        params = [f"%{t}%" for t in tag_list]
        out = {"practices": [], "notes": [], "reviews": [], "qas": []}
        with self._connect() as conn:
            for r in conn.execute(
                f"SELECT * FROM practice_logs WHERE {like_clauses} ORDER BY practice_date DESC", params
            ).fetchall():
                out["practices"].append(PracticeLog.from_row(r))
            for r in conn.execute(
                f"SELECT * FROM work_notes WHERE {like_clauses} ORDER BY updated_at DESC", params
            ).fetchall():
                out["notes"].append(WorkNote.from_row(r))
            for r in conn.execute(
                f"SELECT * FROM practice_reviews WHERE {like_clauses} ORDER BY review_date DESC", params
            ).fetchall():
                out["reviews"].append(PracticeReview.from_row(r))
            for r in conn.execute(
                f"SELECT * FROM qa_items WHERE {like_clauses} ORDER BY created_at DESC", params
            ).fetchall():
                out["qas"].append(QAItem.from_row(r))
        return out


def _make_snippet(text: str, keyword: str, max_len: int = 80) -> str:
    """生成搜索高亮片段：取关键词前后各 30 字符"""
    if not text:
        return ""
    idx = text.lower().find(keyword.lower())
    if idx < 0:
        return text[:max_len] + ("..." if len(text) > max_len else "")
    start = max(0, idx - 30)
    end = min(len(text), idx + len(keyword) + 50)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet
