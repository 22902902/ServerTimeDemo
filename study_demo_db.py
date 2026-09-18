"""
Python 学习模块数据库层
study_demo_db.py
"""
import sqlite3, os
from datetime import datetime
from pathlib import Path
from typing import Optional

DEMO_DB_PATH = os.path.join(os.path.dirname(__file__), "study_demo.db")

# ---------------------------------------------------------------------------
# 表结构
# ---------------------------------------------------------------------------
TABLE_COURSES = """
CREATE TABLE IF NOT EXISTS courses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    category   TEXT    DEFAULT '编程语言',
    sort_order INTEGER DEFAULT 0,
    created_at TEXT    DEFAULT (datetime('now', 'localtime'))
)
"""

TABLE_CHAPTERS = """
CREATE TABLE IF NOT EXISTS chapters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id   INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    sort_order  INTEGER DEFAULT 0,
    note_ref    TEXT    DEFAULT '',   -- 关联学习笔记模块的笔记路径
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (course_id) REFERENCES courses(id)
)
"""

TABLE_SNIPPETS = """
CREATE TABLE IF NOT EXISTS snippets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id  INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    code        TEXT    DEFAULT '',
    language    TEXT    DEFAULT 'python',
    tags        TEXT    DEFAULT '',   -- 逗号分隔标签
    is_favorite INTEGER DEFAULT 0,
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
)
"""

TABLE_DEMO_FILES = """
CREATE TABLE IF NOT EXISTS demo_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id  INTEGER NOT NULL,
    filename    TEXT    NOT NULL,
    rel_path    TEXT    NOT NULL,
    language    TEXT    DEFAULT 'python',
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
)
"""

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DEMO_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn

def init_db(conn: sqlite3.Connection):
    conn.execute(TABLE_COURSES)
    conn.execute(TABLE_CHAPTERS)
    conn.execute(TABLE_SNIPPETS)
    conn.execute(TABLE_DEMO_FILES)
    conn.commit()
    _seed_defaults(conn)

def _seed_defaults(conn: sqlite3.Connection):
    """首次建库时插入示例数据"""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM courses").fetchone()
    if row[0] > 0:
        return

    courses = [
        ("Python 基础", "编程语言", 1),
        ("AI 与大模型", "AI·LLM", 2),
        ("计算机视觉", "AI·LLM", 3),
        ("深度学习框架", "AI·LLM", 4),
        ("数字图像处理", "AI·LLM", 5),
        ("机器学习", "AI·LLM", 6),
        ("Pandas 项目", "数据科学", 7),
        ("Python 高级", "编程语言", 8),
        ("爬虫", "网络", 9),
    ]
    for name, cat, order in courses:
        conn.execute(
            "INSERT INTO courses (name, category, sort_order) VALUES (?, ?, ?)",
            (name, cat, order)
        )

    chapters_examples = [
        (1, "变量与数据类型", 1),
        (1, "控制流程", 2),
        (1, "函数定义", 3),
        (1, "列表与字典", 4),
        (1, "面向对象", 5),
        (2, "LLM 基础概念", 1),
        (2, "Prompt Engineering", 2),
        (2, "RAG 实战", 3),
    ]
    for course_id, title, order in chapters_examples:
        conn.execute(
            "INSERT INTO chapters (course_id, title, sort_order) VALUES (?, ?, ?)",
            (course_id, title, order)
        )

    conn.commit()


# ---------------------------------------------------------------------------
# 课程
# ---------------------------------------------------------------------------
def list_courses(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM courses ORDER BY sort_order, id"
    ).fetchall()
    return [dict(r) for r in rows]

def add_course(conn, name: str, category: str = "编程语言"):
    row = conn.execute(
        "SELECT MAX(sort_order) AS mx FROM courses"
    ).fetchone()
    order = (row[0] or 0) + 1
    cur = conn.execute(
        "INSERT INTO courses (name, category, sort_order) VALUES (?, ?, ?)",
        (name, category, order)
    )
    conn.commit()
    return cur.lastrowid

def update_course(conn, course_id: int, name: str = None, category: str = None):
    if name is not None:
        conn.execute("UPDATE courses SET name=? WHERE id=?", (name, course_id))
    if category is not None:
        conn.execute("UPDATE courses SET category=? WHERE id=?", (category, course_id))
    conn.commit()

def delete_course(conn, course_id: int):
    conn.execute("DELETE FROM chapters WHERE course_id=?", (course_id,))
    conn.execute("DELETE FROM courses WHERE id=?", (course_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# 章节
# ---------------------------------------------------------------------------
def list_chapters(conn, course_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM chapters WHERE course_id=? ORDER BY sort_order, id",
        (course_id,)
    ).fetchall()
    return [dict(r) for r in rows]

def get_chapter(conn, chapter_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
    return dict(row) if row else None

def add_chapter(conn, course_id: int, title: str):
    row = conn.execute(
        "SELECT MAX(sort_order) AS mx FROM chapters WHERE course_id=?",
        (course_id,)
    ).fetchone()
    order = (row[0] or 0) + 1
    cur = conn.execute(
        "INSERT INTO chapters (course_id, title, sort_order) VALUES (?, ?, ?)",
        (course_id, title, order)
    )
    conn.commit()
    return cur.lastrowid

def update_chapter(conn, chapter_id: int, title: str = None, note_ref: str = None):
    if title is not None:
        conn.execute("UPDATE chapters SET title=? WHERE id=?", (title, chapter_id))
    if note_ref is not None:
        conn.execute("UPDATE chapters SET note_ref=? WHERE id=?", (note_ref, chapter_id))
    conn.commit()

def delete_chapter(conn, chapter_id: int):
    conn.execute("DELETE FROM snippets WHERE chapter_id=?", (chapter_id,))
    conn.execute("DELETE FROM demo_files WHERE chapter_id=?", (chapter_id,))
    conn.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# 代码片段
# ---------------------------------------------------------------------------
def list_snippets(conn, chapter_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM snippets WHERE chapter_id=? ORDER BY sort_order, id",
        (chapter_id,)
    ).fetchall()
    return [dict(r) for r in rows]

def get_snippet(conn, snippet_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM snippets WHERE id=?", (snippet_id,)
    ).fetchone()
    return dict(row) if row else None

def add_snippet(conn, chapter_id: int, title: str, code: str = "",
                language: str = "python", tags: str = "") -> int:
    row = conn.execute(
        "SELECT MAX(sort_order) AS mx FROM snippets WHERE chapter_id=?",
        (chapter_id,)
    ).fetchone()
    order = (row[0] or 0) + 1
    cur = conn.execute(
        "INSERT INTO snippets (chapter_id, title, code, language, tags, sort_order)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (chapter_id, title, code, language, tags, order)
    )
    conn.commit()
    return cur.lastrowid

def update_snippet(conn, snippet_id: int, **kwargs):
    allowed = {"title", "code", "language", "tags", "is_favorite", "sort_order"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    if "is_favorite" in fields:
        fields["is_favorite"] = int(bool(fields["is_favorite"]))
    set_clause = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [snippet_id]
    conn.execute(f"UPDATE snippets SET {set_clause} WHERE id=?", vals)
    conn.commit()

def delete_snippet(conn, snippet_id: int):
    conn.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Demo 文件（study_demo/ 目录下的 .py 文件）
# ---------------------------------------------------------------------------
def list_demo_files(conn, chapter_id: int) -> list[dict]:
    """从 DB 和物理目录两个维度取文件"""
    db_rows = conn.execute(
        "SELECT * FROM demo_files WHERE chapter_id=? ORDER BY filename",
        (chapter_id,)
    ).fetchall()
    return [dict(r) for r in db_rows]

def register_demo_file(conn, chapter_id: int, filename: str, rel_path: str,
                       language: str = "python") -> int:
    """注册一个 demo 文件到 DB"""
    cur = conn.execute(
        "INSERT OR IGNORE INTO demo_files (chapter_id, filename, rel_path, language)"
        " VALUES (?, ?, ?, ?)",
        (chapter_id, filename, rel_path, language)
    )
    conn.commit()
    return cur.lastrowid or \
           conn.execute("SELECT id FROM demo_files WHERE rel_path=? AND chapter_id=?",
                        (rel_path, chapter_id)).fetchone()[0]

def delete_demo_file(conn, demo_id: int):
    conn.execute("DELETE FROM demo_files WHERE id=?", (demo_id,))
    conn.commit()
