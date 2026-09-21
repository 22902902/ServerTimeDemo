# -*- coding: utf-8 -*-
"""
===============================================================================
工具库数据库
===============================================================================
表：
  - tool_items        工具条目
  - tool_categories   工具分类
  - tool_toolbar      工具栏（收藏）
  - adb_history       ADB 操作历史
===============================================================================
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

# 标签的拆词 / 统计规则放在 tools_launcher（纯逻辑层，可脱离窗口单测），
# 这里只负责取数，避免分隔符规则在两处各写一遍。
import tools_launcher


# =============================================================================
# 表结构
# =============================================================================

TOOL_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS tool_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    alias TEXT DEFAULT '',
    path TEXT NOT NULL,
    icon_path TEXT DEFAULT '',
    category TEXT DEFAULT '未分类',
    args TEXT DEFAULT '',
    run_as_admin INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    is_favorite INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    is_builtin INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    last_run_at TEXT DEFAULT '',
    run_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

TOOL_CATEGORIES_TABLE = """
CREATE TABLE IF NOT EXISTS tool_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    icon TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    package_id INTEGER DEFAULT NULL
)
"""

TOOL_TOOLBAR_TABLE = """
CREATE TABLE IF NOT EXISTS tool_toolbar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id INTEGER NOT NULL UNIQUE,
    slot INTEGER NOT NULL,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

ADB_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS adb_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial TEXT DEFAULT '',
    command TEXT NOT NULL,
    category TEXT DEFAULT '通用',
    success INTEGER DEFAULT 1,
    note TEXT DEFAULT '',
    executed_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

TOOL_PACKAGES_TABLE = """
CREATE TABLE IF NOT EXISTS tool_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    icon_path TEXT DEFAULT '',
    accent_color TEXT DEFAULT ''
)
"""

TOOL_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS tool_settings (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
)
"""


def init_all_tool_tables(conn: sqlite3.Connection):
    conn.execute(TOOL_ITEMS_TABLE)
    conn.execute(TOOL_CATEGORIES_TABLE)
    conn.execute(TOOL_TOOLBAR_TABLE)
    conn.execute(ADB_HISTORY_TABLE)
    conn.execute(TOOL_PACKAGES_TABLE)
    conn.execute(TOOL_SETTINGS_TABLE)
    conn.commit()
    # ★ 迁移：旧库表加 is_deleted 列
    cols = [r[1] for r in conn.execute("PRAGMA table_info(tool_items)").fetchall()]
    if "is_deleted" not in cols:
        try:
            conn.execute("ALTER TABLE tool_items ADD COLUMN is_deleted INTEGER DEFAULT 0")
            conn.commit()
        except Exception:
            pass
    # ★ 迁移：旧库表加 alias 列
    if "alias" not in cols:
        try:
            conn.execute("ALTER TABLE tool_items ADD COLUMN alias TEXT DEFAULT ''")
            conn.commit()
        except Exception:
            pass
    # ★ 迁移：旧库表加 tags 列（标签 —— 启动器按标签跨分类全局搜索）
    #    缺列时 field_text() 会退成空串，老库只是「没有标签」，不会崩。
    if "tags" not in cols:
        try:
            conn.execute("ALTER TABLE tool_items ADD COLUMN tags TEXT DEFAULT ''")
            conn.commit()
        except Exception:
            pass
    # ★ 迁移：旧库表加 last_run_at / run_count
    #    启动器的「最近使用」横条依赖这两列；缺列时 field_text() 会退成空串，
    #    所以对老库只是“没有最近使用”，不会崩。
    for col, ddl in (("last_run_at", "TEXT DEFAULT ''"),
                     ("run_count", "INTEGER DEFAULT 0")):
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE tool_items ADD COLUMN {col} {ddl}")
                conn.commit()
            except Exception:
                pass
    # ★ 迁移：旧库 tool_categories 表加 package_id 列
    cat_cols = [r[1] for r in conn.execute("PRAGMA table_info(tool_categories)").fetchall()]
    if "package_id" not in cat_cols:
        try:
            conn.execute("ALTER TABLE tool_categories ADD COLUMN package_id INTEGER DEFAULT NULL")
            conn.commit()
        except Exception:
            pass
    # ★ 迁移：旧库 tool_packages 表加 icon_path + accent_color
    pkg_cols = [r[1] for r in conn.execute("PRAGMA table_info(tool_packages)").fetchall()]
    for col, default in [("icon_path", ""), ("accent_color", "")]:
        if col not in pkg_cols:
            try:
                conn.execute(f"ALTER TABLE tool_packages ADD COLUMN {col} TEXT DEFAULT '{default}'")
                conn.commit()
            except Exception:
                pass
    _seed_default_categories(conn)
    _seed_default_packages(conn)
    _seed_default_settings(conn)
    # ★ 一次性迁移：把 package_id IS NULL 的现存分类全部归属到 "个人系统" 包
    #    避免切到新包后看不到历史分类的尴尬
    try:
        null_count = conn.execute("SELECT COUNT(*) FROM tool_categories WHERE package_id IS NULL").fetchone()[0]
        if null_count > 0:
            default_pkg = conn.execute(
                "SELECT id FROM tool_packages WHERE name='个人系统' LIMIT 1"
            ).fetchone()
            if default_pkg:
                conn.execute(
                    "UPDATE tool_categories SET package_id=? WHERE package_id IS NULL",
                    (default_pkg["id"],)
                )
                conn.commit()
    except Exception:
        pass


class ToolboxDatabaseAdapter:
    """系统工具箱数据库适配器，统一收口原始 sqlite 连接的传递方式。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @classmethod
    def from_source(cls, db_source):
        if isinstance(db_source, cls):
            return db_source
        if hasattr(db_source, "conn"):
            return cls(db_source.conn)
        return cls(db_source)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def ensure_ready(self):
        init_all_tool_tables(self._conn)


def _seed_default_categories(conn: sqlite3.Connection):
    """初始化默认分类（★ 全部归属到 "个人系统" 包）"""
    defaults = [
        ("系统工具", 10),
        ("网络工具", 20),
        ("开发工具", 30),
        ("办公软件", 40),
        ("ADB 工具", 50),
        ("批处理脚本", 60),
        ("未分类", 99),
    ]
    # 取 "个人系统" 包 id
    default_pkg = conn.execute("SELECT id FROM tool_packages WHERE name='个人系统' LIMIT 1").fetchone()
    pkg_id = default_pkg["id"] if default_pkg else None
    for name, order in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO tool_categories (name, sort_order, package_id) VALUES (?, ?, ?)",
            (name, order, pkg_id)
        )
    conn.commit()


def _seed_default_packages(conn: sqlite3.Connection):
    """初始化默认下拉包"""
    defaults = [
        ("个人系统", 10),
        ("常用工具", 20),
        ("开发工具", 30),
        ("办公软件", 40),
    ]
    for name, order in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO tool_packages (name, sort_order, is_active) VALUES (?, ?, 1)",
            (name, order)
        )
    conn.commit()


def _seed_default_settings(conn: sqlite3.Connection):
    """初始化默认设置"""
    defaults = {
        "tools_dir": "",          # 留空时使用 <project_root>/Tools
        "use_relative_path": "1", # 1=数据库存相对路径
        "default_run_mode": "normal",  # normal / admin
        "icon_size": "48",
        "grid_cols": "6",
    }
    for k, v in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO tool_settings (key, value) VALUES (?, ?)",
            (k, v)
        )
    conn.commit()


# =============================================================================
# 工具条目 CRUD
# =============================================================================

def upsert_tool_by_path(conn, path: str, name: str, category: str = "未分类",
                        icon_path: str = "") -> int:
    """根据路径插入或更新工具条目，返回 id。
    重要：如果该 path 已被软删除（用户手动删过），**跳过** — 不复活。
    否则会造成“删除后重启又出现”的 bug。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # ★ 检查是否软删除
    deleted = conn.execute(
        "SELECT id FROM tool_items WHERE path=? AND is_deleted=1", (path,)
    ).fetchone()
    if deleted:
        return deleted["id"]  # 不复活，保留黑名单
    row = conn.execute(
        "SELECT id FROM tool_items WHERE path=? AND is_deleted=0", (path,)
    ).fetchone()
    if row:
        # ★ 分类不再被扫描结果覆盖：分类现在是「用户手工维护的归属」
        #   （拖拽 / 右键改分类），扫描只负责发现新文件。旧实现每次重扫都
        #   把手工分类冲回目录名 —— 用户刚拖好的分类一扫就没了。
        #   仅当原分类为空或「未分类」时才用目录名兜底。
        conn.execute(
            "UPDATE tool_items SET name=?, "
            "category=CASE WHEN COALESCE(category, '') IN ('', '未分类') "
            "THEN ? ELSE category END, "
            "icon_path=?, updated_at=? WHERE id=?",
            (name, category, icon_path, now, row["id"])
        )
        conn.commit()
        return row["id"]
    else:
        cursor = conn.execute(
            "INSERT INTO tool_items (name, path, icon_path, category, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, path, icon_path, category, now, now)
        )
        conn.commit()
        return cursor.lastrowid


def add_tool(conn, name: str, path: str, category: str = "未分类",
             args: str = "", run_as_admin: bool = False,
             description: str = "", icon_path: str = "", tags: str = "") -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.execute(
        "INSERT INTO tool_items (name, path, category, args, run_as_admin, description, tags, icon_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, path, category, args, int(run_as_admin), description,
         tools_launcher.normalize_tags(tags), icon_path, now, now)
    )
    conn.commit()
    return cursor.lastrowid


def update_tool(conn, tool_id: int, **kwargs) -> bool:
    allowed = {"name", "alias", "path", "icon_path", "category", "args",
               "run_as_admin", "description", "tags", "is_favorite", "sort_order"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    if "run_as_admin" in fields:
        fields["run_as_admin"] = int(bool(fields["run_as_admin"]))
    if "is_favorite" in fields:
        fields["is_favorite"] = int(bool(fields["is_favorite"]))
    if "tags" in fields:
        # 存储形态统一在数据层收口：调用方随便传 "a、b" / "a|b" / "a,b" 都一样
        fields["tags"] = tools_launcher.normalize_tags(fields["tags"])
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tool_id]
    conn.execute(f"UPDATE tool_items SET {set_clause}, updated_at=? WHERE id=?", values)
    conn.commit()
    return True


def delete_tool(conn, tool_id: int) -> bool:
    """软删除：标记 is_deleted=1，从工具栏移除。
    物理文件保留。重启扫描时如文件仍存在则不复活（黑名单）。"""
    conn.execute("DELETE FROM tool_toolbar WHERE tool_id=?", (tool_id,))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE tool_items SET is_deleted=1, updated_at=? WHERE id=?", (now, tool_id))
    conn.commit()
    return True


def restore_tool(conn, tool_id: int) -> bool:
    """恢复软删除的工具"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE tool_items SET is_deleted=0, updated_at=? WHERE id=?", (now, tool_id))
    conn.commit()
    return True


def purge_tool(conn, tool_id: int) -> bool:
    """彻底删除：删除 DB 记录"""
    conn.execute("DELETE FROM tool_toolbar WHERE tool_id=?", (tool_id,))
    conn.execute("DELETE FROM tool_items WHERE id=?", (tool_id,))
    conn.commit()
    return True


def get_tool(conn, tool_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM tool_items WHERE id=?", (tool_id,)).fetchone()
    return dict(row) if row else None


def touch_tool_run(conn, tool_id: int):
    """记一次启动：刷新最近使用时间 + 累加次数。

    刷新/统计失败不应影响工具本身能不能启动，
    所以这里把异常全吞（也避免老库缺列时把启动流程打断）。
    """
    try:
        conn.execute(
            "UPDATE tool_items SET last_run_at=?, run_count=COALESCE(run_count,0)+1 "
            "WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tool_id))
        conn.commit()
    except Exception:
        pass


def list_tools(conn, category: str = "", keyword: str = "",
               favorites_only: bool = False,
               include_deleted: bool = False,
               sort_key: str = "",
               package: str = "") -> list[dict]:
    sql = "SELECT * FROM tool_items WHERE 1=1"
    params = []
    if not include_deleted:
        sql += " AND is_deleted=0"
    if category and category != "全部":
        sql += " AND category=?"
        params.append(category)
    if package:
        # ★ "常用工具" 包=伪包，显示所有工具（不按包过滤）
        if package != "常用工具":
            sql += (" AND category IN (SELECT tc.name FROM tool_categories tc "
                     "LEFT JOIN tool_packages tp ON tc.package_id = tp.id "
                     "WHERE tp.name = ?)")
            params.append(package)
    if keyword:
        # ★ 补上 alias / category / tags：用户往往记得别名（如 "FF"）、
        #    分类或标签，却记不住全名；过去只搜 name/description/args 会搜不到。
        #    （启动器的 UI 搜索走 rank_tools 的模糊排序，这里是给其它入口的 SQL 兜底）
        sql += (" AND (name LIKE ? OR description LIKE ? OR args LIKE ? "
                "OR COALESCE(alias,'') LIKE ? OR COALESCE(category,'') LIKE ? "
                "OR COALESCE(tags,'') LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw, kw, kw, kw])
    if favorites_only:
        sql += " AND is_favorite=1"
    # ★ 排序：sort_key 指定则按该字段排，否则默认按 分类+s序
    if sort_key == "name":
        sql += " ORDER BY category, name COLLATE NOCASE"
    elif sort_key == "id":
        sql += " ORDER BY category, id DESC"
    elif sort_key == "category":
        sql += " ORDER BY category, name COLLATE NOCASE"
    else:
        sql += " ORDER BY category, sort_order, name"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def list_tag_counts(conn, package: str = "", limit: int = 0) -> list[tuple[str, int]]:
    """统计标签使用次数：[(标签, 个数)]，个数降序、标签升序。

    标签是「跨分类、跨包」的检索入口，所以默认不做包过滤 —— 在这儿按包缩一遍，
    等于把「全局搜标签」又关回抽屉里。确实要按包看时才传 package。
    """
    sql = "SELECT COALESCE(tags, '') AS tags FROM tool_items WHERE is_deleted=0"
    params: list = []
    if package and package != "常用工具":
        sql += (" AND category IN (SELECT tc.name FROM tool_categories tc "
                "LEFT JOIN tool_packages tp ON tc.package_id = tp.id "
                "WHERE tp.name = ?)")
        params.append(package)
    return tools_launcher.popular_tags(conn.execute(sql, params).fetchall(), limit)


def list_deleted_paths(conn) -> set[str]:
    """返回所有软删除工具的 path 集合（供 scan 跳过/恢复用）"""
    return {r["path"] for r in conn.execute(
        "SELECT path FROM tool_items WHERE is_deleted=1"
    ).fetchall()}


def restore_deleted_by_path(conn, path: str) -> Optional[int]:
    """如果 path 在软删除表中，恢复它并返回 id"""
    row = conn.execute(
        "SELECT id FROM tool_items WHERE path=? AND is_deleted=1", (path,)
    ).fetchone()
    if not row:
        return None
    conn.execute("UPDATE tool_items SET is_deleted=0, updated_at=? WHERE id=?",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), row["id"]))
    conn.commit()
    return row["id"]


def list_categories(conn, package: str = '') -> list[dict]:
    """列出分类。常用工具=伪包(显示全部)；其他按包过滤。"""
    if package == '常用工具':
        rows = conn.execute(
            'SELECT * FROM tool_categories ORDER BY sort_order, name'
        ).fetchall()
    elif package:
        rows = conn.execute(
            'SELECT tc.* FROM tool_categories tc '
            'LEFT JOIN tool_packages tp ON tc.package_id = tp.id '
            'WHERE tp.name = ? '
            'ORDER BY tc.sort_order, tc.name',
            (package,)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM tool_categories ORDER BY sort_order, name'
        ).fetchall()
    return [dict(r) for r in rows]

def add_category(conn, name: str, sort_order: int = 0, package_id: int = None) -> int:
    if package_id is None:
        # 默认归属到 "个人系统" 包（避免遗留 NULL）
        default_pkg = conn.execute("SELECT id FROM tool_packages WHERE name='个人系统' LIMIT 1").fetchone()
        package_id = default_pkg["id"] if default_pkg else None
    cursor = conn.execute(
        "INSERT OR IGNORE INTO tool_categories (name, sort_order, package_id) VALUES (?, ?, ?)",
        (name, sort_order, package_id)
    )
    conn.commit()
    if cursor.lastrowid:
        return cursor.lastrowid
    row = conn.execute("SELECT id FROM tool_categories WHERE name=?", (name,)).fetchone()
    if row and package_id is not None:
        # 旧 NULL 的已存在分类→补上 package_id
        if row["package_id"] is None:
            conn.execute("UPDATE tool_categories SET package_id=? WHERE id=?", (package_id, row["id"]))
            conn.commit()
    return row["id"] if row else 0


def update_category(conn, category_id: int, new_name: str = None, package_id: int = None) -> bool:
    """重命名/迁移分类。
    - new_name=None ：不改名（保持原名）
    - new_name=""   ：非法输入，拒绝（返回 False）
    - new_name="xxx"：改为 xxx
    - package_id=None：不换包；数值：迁移到指定包
    """
    if new_name is not None and new_name == "":
        return False  # 空字符串是无效输入，不静默忽略
    row = conn.execute("SELECT * FROM tool_categories WHERE id=?", (category_id,)).fetchone()
    if not row:
        return False
    old_name = row["name"]
    fields = []
    values = []
    if new_name is not None and new_name != old_name:
        fields.append("name=?"); values.append(new_name)
    if package_id is not None:
        fields.append("package_id=?"); values.append(package_id)
    if fields:
        set_clause = ", ".join(fields)
        conn.execute(f"UPDATE tool_categories SET {set_clause} WHERE id=?", values + [category_id])
        if new_name is not None and new_name != old_name:
            conn.execute("UPDATE tool_items SET category=? WHERE category=?", (new_name, old_name))
        conn.commit()
    return True


def delete_category(conn, category_id: int) -> tuple[bool, str]:
    """删除分类（若分类下有工具则拒绝）。
    返回: (success, message)"""
    row = conn.execute("SELECT name FROM tool_categories WHERE id=?", (category_id,)).fetchone()
    if not row:
        return False, "分类不存在"
    name = row["name"]
    used = conn.execute(
        "SELECT COUNT(*) AS c FROM tool_items WHERE category=?", (name,)
    ).fetchone()
    if used["c"] > 0:
        return False, f"该分类下有 {used['c']} 个工具，请清空工具后删除。"
    conn.execute("DELETE FROM tool_categories WHERE id=?", (category_id,))
    conn.commit()
    return True, "ok"


def count_tools_in_category(conn, category_name: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM tool_items WHERE category=?", (category_name,)
    ).fetchone()
    return row["c"] if row else 0


# =============================================================================
# 包（下拉菜单）CRUD
# =============================================================================

def list_packages(conn, include_inactive: bool = False) -> list[dict]:
    sql = "SELECT * FROM tool_packages"
    if not include_inactive:
        sql += " WHERE is_active=1"
    sql += " ORDER BY sort_order, name"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def add_package(conn, name: str, sort_order: int = 0) -> int:
    cursor = conn.execute(
        "INSERT OR IGNORE INTO tool_packages (name, sort_order, is_active) VALUES (?, ?, 1)",
        (name, sort_order)
    )
    conn.commit()
    if cursor.lastrowid:
        return cursor.lastrowid
    row = conn.execute("SELECT id FROM tool_packages WHERE name=?", (name,)).fetchone()
    return row["id"] if row else 0


def update_package(conn, package_id: int, new_name: str,
                   icon_path: str = None, accent_color: str = None) -> bool:
    """更新包名/logo/标识色。任一字段为 None 则不改。"""
    fields, values = [], []
    if new_name is not None:
        fields.append("name=?"); values.append(new_name)
    if icon_path is not None:
        fields.append("icon_path=?"); values.append(icon_path)
    if accent_color is not None:
        fields.append("accent_color=?"); values.append(accent_color)
    if not fields:
        return False
    values.append(package_id)
    conn.execute(f"UPDATE tool_packages SET {', '.join(fields)} WHERE id=?", values)
    conn.commit()
    return True


def get_package_by_name(conn, name: str) -> Optional[dict]:
    """按名取包（含 logo/颜色）。"""
    row = conn.execute("SELECT * FROM tool_packages WHERE name=?", (name,)).fetchone()
    if not row:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    cols = [c[0] for c in conn.execute(
        "SELECT * FROM tool_packages WHERE name=?", (name,)
    ).description]
    return dict(zip(cols, row))


def delete_package(conn, package_id: int) -> tuple[bool, str]:
    """软删除：标记 is_active=0，避免误删导致下拉找不到匹配。"""
    row = conn.execute("SELECT name FROM tool_packages WHERE id=?", (package_id,)).fetchone()
    if not row:
        return False, "包不存在"
    name = row["name"]
    used = conn.execute("SELECT COUNT(*) AS c FROM tool_items WHERE category=?", (name,)).fetchone()
    if used["c"] > 0:
        return False, f"该包下有 {used['c']} 个工具正在使用此分类，请先将工具迁移到其他包后再删除。"
    conn.execute("UPDATE tool_packages SET is_active=0 WHERE id=?", (package_id,))
    conn.commit()
    return True, "ok"


def activate_package(conn, package_id: int) -> bool:
    conn.execute("UPDATE tool_packages SET is_active=1 WHERE id=?", (package_id,))
    conn.commit()
    return True


# =============================================================================
# 设置（key-value）
# =============================================================================

def get_setting(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM tool_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key: str, value: str) -> bool:
    conn.execute(
        "INSERT INTO tool_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    conn.commit()
    return True


def get_all_settings(conn) -> dict:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM tool_settings").fetchall()}


# =============================================================================
# 工具栏（收藏/快速启动）
# =============================================================================

def add_to_toolbar(conn, tool_id: int) -> bool:
    row = conn.execute("SELECT id FROM tool_toolbar WHERE tool_id=?", (tool_id,)).fetchone()
    if row:
        return False
    max_slot_row = conn.execute("SELECT COALESCE(MAX(slot), -1) AS ms FROM tool_toolbar").fetchone()
    slot = (max_slot_row["ms"] or -1) + 1
    conn.execute("INSERT INTO tool_toolbar (tool_id, slot) VALUES (?, ?)", (tool_id, slot))
    conn.commit()
    return True


def remove_from_toolbar(conn, tool_id: int) -> bool:
    conn.execute("DELETE FROM tool_toolbar WHERE tool_id=?", (tool_id,))
    conn.commit()
    return True


def list_toolbar(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT t.*, tb.slot, tb.added_at AS pinned_at
        FROM tool_toolbar tb
        JOIN tool_items t ON t.id = tb.tool_id
        ORDER BY tb.slot
    """).fetchall()
    return [dict(r) for r in rows]


def reorder_toolbar(conn, slot_map: dict[int, int]) -> bool:
    """slot_map: {tool_id: new_slot}"""
    for tool_id, new_slot in slot_map.items():
        conn.execute("UPDATE tool_toolbar SET slot=? WHERE tool_id=?", (new_slot, tool_id))
    conn.commit()
    return True


# =============================================================================
# ADB 历史
# =============================================================================

def add_adb_history(conn, command: str, device_serial: str = "",
                    category: str = "通用", success: bool = True,
                    note: str = "") -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.execute(
        "INSERT INTO adb_history (device_serial, command, category, success, note, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (device_serial, command, category, int(success), note, now)
    )
    conn.commit()
    return cursor.lastrowid


def list_adb_history(conn, limit: int = 200, device_serial: str = "",
                     category: str = "") -> list[dict]:
    sql = "SELECT * FROM adb_history WHERE 1=1"
    params = []
    if device_serial:
        sql += " AND device_serial=?"
        params.append(device_serial)
    if category and category != "全部":
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY executed_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def clear_adb_history(conn) -> bool:
    conn.execute("DELETE FROM adb_history")
    conn.commit()
    return True


# =============================================================================
# 扫描工具
# =============================================================================

# 支持的工具扩展名
TOOL_EXTENSIONS = {".exe", ".bat", ".cmd", ".lnk", ".py", ".ps1", ".vbs", ".jar"}

# 排除的目录名
EXCLUDED_DIRS = {"__pycache__", ".git", "node_modules", ".vscode", "build", "dist"}


def scan_tools_folder(root: str | Path) -> list[dict]:
    """
    扫描 Tools 文件夹，返回工具条目列表。
    每个条目: {name, path, category(子目录名), rel_path}
    """
    root = Path(root)
    if not root.exists():
        return []
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            category = "未分类"
        else:
            category = rel_dir.split(os.sep)[0]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TOOL_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, fn)
            results.append({
                "name": os.path.splitext(fn)[0],
                "path": full_path,
                "category": category,
                "rel_path": os.path.relpath(full_path, root),
            })
    return results
