# -*- coding: utf-8 -*-
"""思维导图 · 数据层。

边界（与 ``memory_db.py`` / ``excel_db.py`` / ``todo_db.py`` 同一套约定）
------------------------------------------------------------------------------
* **不 import tkinter** —— 可以脱离窗口单测。
* 表全部 ``CREATE TABLE IF NOT EXISTS``，**不动任何既有表**（老库直接可用）。
* 树的形状、大纲解析、导出格式**都不在这里**，在 ``mindmap_layout``；
  这里只负责「树 <-> 扁平行」的存取与进度/打卡。

四张业务表 + 一张进度表
------------------------------------------------------------------------------
    mindmap            导图（中心主题 + 分类 + 标签）
    mindmap_nodes      节点（parent_id=0 即中心主题；seq 决定同级顺序）
    mindmap_progress   每张导图的 SRS 状态 —— **懒创建**（key = map_id）
    mindmap_reviews    复习流水（只增不改）
    mindmap_checkins   打卡（一天一行）

三条纪律
------------------------------------------------------------------------------
1. **``mindmap_progress`` 是懒创建的** —— 一切「今日该盲画哪张」的查询
   **必须 LEFT JOIN**。内连接会让「今日训练」在新库里一片空白。
2. **折叠状态属于节点，不属于文本** —— 大纲编辑器提交纯文本时，
   要先 :func:`mindmap_layout.carry_collapsed` 把折叠搬过去，别整树重存丢状态。
3. **``save_outline`` 保住已有 id** —— 靠节点 id 对得上就 UPDATE，
   对不上才 INSERT，树里消失的才 DELETE。全删全插会把 id 洗掉，
   以后任何挂在节点上的数据都会跟着丢。
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, timedelta

import mindmap_layout as ml
import mindmap_seed
import training_core as tc

logger = logging.getLogger(__name__)

# train_settings 里存「用哪套间隔重复算法」的键
SETTING_ALGORITHM = "srs_algorithm"

DEFAULT_MAP_TITLE = "未命名导图"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp(day) -> str:
    """给「指定日」打时间戳：日期部分用 ``day``，时分秒取当下。

    ``_now()`` 一律写墙钟，于是「按 9-28 记一次」在库里落的却是今天的日期，
    ``new_today(today='9-28')`` 数出来是 0。调用方给了「今天」，写库就得认
    这个口径 —— 不传时 ``day`` 就是今天，与 ``_now()`` 完全等价。
    """
    return "{} {}".format(day.isoformat(),
                          datetime.now().strftime("%H:%M:%S"))


def _like_kw(keyword) -> str:
    return f"%{str(keyword or '').strip()}%"


class MindmapDB:
    """思维导图的数据库操作类。"""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._init_tables()
        self.seed_templates()

    # ==================================================================
    # 连接与建表
    # ==================================================================
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mindmap (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT NOT NULL,
                    root_note  TEXT NOT NULL DEFAULT '',
                    category   TEXT NOT NULL DEFAULT '',
                    tags       TEXT NOT NULL DEFAULT '',
                    source_key TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            # 部分唯一索引：source_key 为空的（用户自建）不参与唯一性
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_mindmap_source "
                         "ON mindmap(source_key) WHERE source_key <> ''")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS mindmap_nodes (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_id     INTEGER NOT NULL,
                    parent_id  INTEGER NOT NULL DEFAULT 0,
                    seq        INTEGER NOT NULL DEFAULT 0,
                    depth      INTEGER NOT NULL DEFAULT 0,
                    text       TEXT NOT NULL DEFAULT '',
                    note       TEXT NOT NULL DEFAULT '',
                    collapsed  INTEGER NOT NULL DEFAULT 0,
                    pos_x      REAL,
                    pos_y      REAL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mindmap_nodes_map "
                         "ON mindmap_nodes(map_id, parent_id, seq)")

            # 进度：**懒创建**（盲画过一次才建行）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mindmap_progress (
                    map_id         INTEGER PRIMARY KEY,
                    mastery        INTEGER NOT NULL DEFAULT 0,
                    correct_streak INTEGER NOT NULL DEFAULT 0,
                    interval_days  INTEGER NOT NULL DEFAULT 0,
                    next_review_at TEXT NOT NULL DEFAULT '',
                    review_count   INTEGER NOT NULL DEFAULT 0,
                    marked_at      TEXT NOT NULL DEFAULT '',
                    updated_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    last_review_at TEXT NOT NULL DEFAULT '',
                    ease_factor    REAL NOT NULL DEFAULT 2.5,
                    reps           INTEGER NOT NULL DEFAULT 0,
                    stability      REAL NOT NULL DEFAULT 0,
                    difficulty     REAL NOT NULL DEFAULT 5
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mindmap_progress_due "
                         "ON mindmap_progress(next_review_at)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS mindmap_reviews (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_id        INTEGER NOT NULL,
                    review_date   TEXT NOT NULL,
                    feedback      TEXT NOT NULL,
                    mastery_after INTEGER NOT NULL DEFAULT 0,
                    branch_hit    INTEGER NOT NULL DEFAULT 0,
                    branch_total  INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mindmap_reviews_date "
                         "ON mindmap_reviews(review_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mindmap_reviews_map "
                         "ON mindmap_reviews(map_id)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS mindmap_checkins (
                    check_date    TEXT PRIMARY KEY,
                    minutes       INTEGER NOT NULL DEFAULT 0,
                    maps_new      INTEGER NOT NULL DEFAULT 0,
                    maps_reviewed INTEGER NOT NULL DEFAULT 0,
                    accuracy      REAL NOT NULL DEFAULT 0,
                    note          TEXT NOT NULL DEFAULT '',
                    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)

            # 训练参数（key/value）：目前只有「用哪套间隔重复算法」
            conn.execute("""
                CREATE TABLE IF NOT EXISTS train_settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                )
            """)

            # 老库没有的列在这里补上（新库建表时已经有了，这里是空操作）
            self._ensure_train_columns(conn)
            self._ensure_node_columns(conn)

    def _ensure_train_columns(self, conn) -> None:
        """缺列就 ``ALTER TABLE ADD COLUMN``；**不动存量数据、不重建表**。

        mindmap 的表从 v1.16.0 起就没改过 schema，所以这里原本**没有**迁移机制 ——
        加「多算法 SRS」才需要它。``CREATE TABLE IF NOT EXISTS`` 只对新库生效，
        用户 exe 里那份 db 早就建好了，不补这一步新列会**静默缺失**。
        """
        ddls = {
            "last_review_at": "TEXT NOT NULL DEFAULT ''",
            "ease_factor": "REAL NOT NULL DEFAULT 2.5",
            "reps": "INTEGER NOT NULL DEFAULT 0",
            "stability": "REAL NOT NULL DEFAULT 0",
            "difficulty": "REAL NOT NULL DEFAULT 5",
        }
        have = {str(row["name"])
                for row in conn.execute("PRAGMA table_info(mindmap_progress)")}
        for column, ddl in ddls.items():
            if column in have:
                continue
            conn.execute("ALTER TABLE mindmap_progress ADD COLUMN {} {}".format(
                column, ddl))


    def _ensure_node_columns(self, conn) -> None:
        """``mindmap_nodes`` 缺的列在这里补上（``pos_x`` / ``pos_y``）。

        ``CREATE TABLE IF NOT EXISTS`` 只帮新库 —— 用户 exe 里那份 db 早就建好了，
        不补这一步，自由画布在老库上会**静默失效**（存不进坐标，界面上拖得动、
        重开就没了）。
        """
        ddls = {"pos_x": "REAL", "pos_y": "REAL"}
        have = {str(row["name"])
                for row in conn.execute("PRAGMA table_info(mindmap_nodes)")}
        for column, ddl in ddls.items():
            if column in have:
                continue
            conn.execute("ALTER TABLE mindmap_nodes ADD COLUMN {} {}".format(
                column, ddl))

    # ==================================================================
    # 模板（内置，安装时灌一遍；幂等）
    # ==================================================================
    def seed_templates(self) -> int:
        """把 ``mindmap_seed.TEMPLATES`` 灌成导图。**重跑不会重复建。**

        灌进来的模板是**可编辑的普通导图**（用户可以随便改）——
        它只是一份起始骨架，不是只读资产。
        """
        created = 0
        for item in mindmap_seed.TEMPLATES:
            source_key = f"tpl:{item['code']}"
            if self.get_map_by_source(source_key):
                continue
            map_id = self.add_map(
                item["name"], root_note=item["description"],
                category=item["category"], source_key=source_key)
            tree = ml.parse_outline(item["outline"])
            self.save_outline(map_id, tree)
            created += 1
        return created

    def list_templates(self) -> list[dict]:
        return [dict(t) for t in mindmap_seed.TEMPLATES]

    def get_template(self, code) -> dict | None:
        for item in mindmap_seed.TEMPLATES:
            if item["code"] == str(code):
                return dict(item)
        return None

    def template_categories(self) -> list[str]:
        return mindmap_seed.template_categories()

    def create_from_template(self, code, *, title=None) -> int:
        """按模板新建一张**可编辑**的导图（不是复用模板本身）。"""
        item = self.get_template(code)
        if item is None:
            raise KeyError(f"没有这个模板：{code}")
        map_id = self.add_map(
            title or item["name"], root_note=item["description"],
            category=item["category"])
        self.save_outline(map_id, ml.parse_outline(item["outline"]))
        return map_id

    # ==================================================================
    # 导图 CRUD
    # ==================================================================
    def add_map(self, title, *, root_note="", category="", tags="",
                source_key="") -> int:
        name = str(title or "").strip() or DEFAULT_MAP_TITLE
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO mindmap (title, root_note, category, tags, source_key, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, str(root_note or ""), str(category or ""), str(tags or ""),
                 str(source_key or ""), _now(), _now()))
            map_id = int(cur.lastrowid)
            # 中心主题节点建行的同一次连接里就写掉：否则 load_tree 会拿
            # DEFAULT_MAP_TITLE 兜底，与 get_map()["title"] 对不上 ——
            # 用户在新建对话框填的名字，会在第一次编辑大纲时被那个兜底串覆盖。
            conn.execute(
                "INSERT INTO mindmap_nodes (map_id, parent_id, seq, depth, text, "
                "note, collapsed) VALUES (?, 0, 0, 0, ?, '', 0)", (map_id, name))
            return map_id

    _MAP_FIELDS = ("title", "root_note", "category", "tags", "source_key")

    def update_map(self, map_id, **fields) -> bool:
        sets: list[str] = []
        params: list = []
        for key in self._MAP_FIELDS:
            if key in fields and fields[key] is not None:
                sets.append(f"{key} = ?")
                params.append(str(fields[key]))
        if not sets:
            return False
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(int(map_id))
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE mindmap SET {', '.join(sets)} WHERE id = ?", params)
            return cur.rowcount > 0

    def get_map(self, map_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM mindmap WHERE id = ?",
                               (int(map_id),)).fetchone()
        return dict(row) if row else None

    def get_map_by_source(self, source_key) -> dict | None:
        if not str(source_key or "").strip():
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM mindmap WHERE source_key = ?",
                               (str(source_key),)).fetchone()
        return dict(row) if row else None

    def list_maps(self, *, keyword=None, category=None, limit=None,
                  today=None) -> list[dict]:
        """导图列表。**每一行都带 ``node_count`` / ``mastery`` / ``due``。**

        为什么用 LEFT JOIN 而不是内连接：进度行是懒创建的，刚建好的导图没有
        进度行 —— 内连接会让「缩略图墙」在刚开始用的时候是空的。

        ``today`` 必须能显式传进来：``bucket`` / ``due`` 是拿它当锚点算的。
        这里曾经写死 ``tc.today_str()``，于是 ``due_count(today=明天)`` 会
        拿到「用今天算出来的 bucket」—— 与 ``due_maps(today=明天)`` 的条数
        自相矛盾，而界面在真实今天跑，看不出任何异常。
        """
        sql = """
            SELECT m.*,
                   COALESCE(p.mastery, 0)         AS mastery,
                   COALESCE(p.correct_streak, 0)  AS correct_streak,
                   COALESCE(p.interval_days, 0)   AS interval_days,
                   COALESCE(p.next_review_at, '') AS next_review_at,
                   COALESCE(p.review_count, 0)    AS review_count,
                   (SELECT COUNT(*) FROM mindmap_nodes n WHERE n.map_id = m.id)
                       AS node_count,
                   (SELECT COUNT(*) FROM mindmap_nodes n
                     WHERE n.map_id = m.id AND n.depth = 1)
                       AS branch_count
              FROM mindmap m
              LEFT JOIN mindmap_progress p ON p.map_id = m.id
             WHERE 1 = 1
        """
        params: list = []
        if str(category or "").strip():
            sql += " AND m.category = ?"
            params.append(str(category))
        if str(keyword or "").strip():
            sql += (" AND (m.title LIKE ? OR m.root_note LIKE ? OR m.tags LIKE ?"
                    " OR m.id IN (SELECT map_id FROM mindmap_nodes WHERE text LIKE ?))")
            params += [_like_kw(keyword)] * 4
        sql += " ORDER BY m.updated_at DESC, m.id DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result = [dict(r) for r in rows]
        anchor = tc.parse_date(today) or date.today()
        for item in result:
            item["bucket"] = tc.due_bucket(item["next_review_at"], anchor)
            item["due"] = item["bucket"] == "due"
        if limit is not None:
            result = result[: int(limit)]
        return result

    def count_maps(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM mindmap").fetchone()
        return int(row["n"] if row else 0)

    def categories(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM mindmap "
                "WHERE TRIM(COALESCE(category, '')) <> '' ORDER BY category").fetchall()
        return [str(r["category"]) for r in rows]

    def delete_map(self, map_id) -> bool:
        mid = int(map_id)
        with self._connect() as conn:
            conn.execute("DELETE FROM mindmap_nodes WHERE map_id = ?", (mid,))
            conn.execute("DELETE FROM mindmap_progress WHERE map_id = ?", (mid,))
            conn.execute("DELETE FROM mindmap_reviews WHERE map_id = ?", (mid,))
            cur = conn.execute("DELETE FROM mindmap WHERE id = ?", (mid,))
            return cur.rowcount > 0

    def rename_map(self, map_id, title) -> bool:
        """改标题同时把**中心主题节点**的文字一起改掉（两者本就是一回事）。"""
        mid = int(map_id)
        name = str(title or "").strip()
        if not name:
            return False
        root = self.root_node(mid)
        with self._connect() as conn:
            conn.execute("UPDATE mindmap SET title = ?, updated_at = ? WHERE id = ?",
                         (name, _now(), mid))
            if root:
                conn.execute("UPDATE mindmap_nodes SET text = ? WHERE id = ?",
                             (name, int(root["id"])))
        return True

    # ==================================================================
    # 节点 / 树
    # ==================================================================
    def list_nodes(self, map_id) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mindmap_nodes WHERE map_id = ? "
                "ORDER BY depth, parent_id, seq, id", (int(map_id),)).fetchall()
        return [dict(r) for r in rows]

    def root_node(self, map_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mindmap_nodes WHERE map_id = ? AND parent_id = 0 "
                "ORDER BY seq, id LIMIT 1", (int(map_id),)).fetchone()
        return dict(row) if row else None

    def load_tree(self, map_id) -> dict:
        """整张导图读成树（含 id 与 collapsed），直接可以喂给 ``ml.layout``。"""
        rows = self.list_nodes(map_id)
        if not rows:
            return ml.empty_tree(DEFAULT_MAP_TITLE)
        return ml.build_tree(rows)

    def load_outline(self, map_id) -> str:
        return ml.outline_text(self.load_tree(map_id))

    def node_count(self, map_id) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM mindmap_nodes WHERE map_id = ?",
                               (int(map_id),)).fetchone()
        return int(row["n"] if row else 0)

    def save_outline(self, map_id, tree) -> dict:
        """把整棵树写回库。**尽力认出旧行**，认不出才 INSERT，树里消失的才 DELETE。

        为什么不能「先清空再插」：id 一洗，任何挂在节点上的数据都会跟着丢
        （折叠状态、备注，将来的图标 / 图片），而且外键关系全断。

        认领顺序（``_claim_row`` 那三步）：**先 id，再（父节点新 id + 文字），
        最后才是新建**。所以有以下两个好处：

        * 大纲文本（没有 id）重存时，只要文字没改、父节点还在，节点 id 就保住 ——
          每次保存不再是无脑重建整个子图；
        * 真的新增的分支拿到全新 id，不会和张冠李戴地复用别人的行。

        写入顺序是 DFS，父节点一定先落库，所以新建子树的 ``parent_id``
        一定指向刚拿到的那个新 id。
        """
        mid = int(map_id)
        tree = ml.normalize(tree)
        stats = {"inserted": 0, "updated": 0, "removed": 0, "reused": 0}

        with self._connect() as conn:
            existing = [dict(r) for r in conn.execute(
                "SELECT * FROM mindmap_nodes WHERE map_id = ?", (mid,)).fetchall()]
            by_id = {int(r["id"]): r for r in existing}
            # (parent_id, text) -> 候选行，按原 seq 排序；给「没有 id」的节点找回原行
            pool: dict = {}
            for row in sorted(existing, key=lambda r: (int(r["parent_id"]),
                                                       int(r["seq"]), int(r["id"]))):
                key = (int(row["parent_id"]), str(row["text"]))
                pool.setdefault(key, []).append(row)

            used: set[int] = set()
            kept: set[int] = set()

            def claim(node_id, parent_id, text):
                """按 id -> 按(父, 文字) 的顺序认领一条旧行；都没有就返回 None。"""
                if node_id is not None:
                    row = by_id.get(int(node_id))
                    if row is not None and int(row["id"]) not in used:
                        return row
                for row in pool.get((int(parent_id), str(text)), ()):
                    if int(row["id"]) not in used:
                        return row
                return None

            def walk(node, parent_id, seq, depth):
                text = str(node.get("text") or "")
                row = claim(node.get("id"), parent_id, text)
                payload = (int(parent_id), int(seq), int(depth), text,
                           str(node.get("note") or ""),
                           1 if node.get("collapsed") else 0)
                if row is not None:
                    conn.execute(
                        "UPDATE mindmap_nodes SET parent_id = ?, seq = ?, depth = ?, "
                        "text = ?, note = ?, collapsed = ? WHERE id = ? AND map_id = ?",
                        payload + (int(row["id"]), mid))
                    new_id = int(row["id"])
                    stats["updated"] += 1
                    if node.get("id") is None:
                        stats["reused"] += 1
                else:
                    cur = conn.execute(
                        "INSERT INTO mindmap_nodes (map_id, parent_id, seq, depth, "
                        "text, note, collapsed) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (mid,) + payload)
                    new_id = int(cur.lastrowid)
                    stats["inserted"] += 1
                used.add(new_id)
                kept.add(new_id)
                node["id"] = new_id
                for index, child in enumerate(node.get("children") or ()):
                    walk(child, new_id, index, depth + 1)

            # 根节点的 parent_id 固定 0
            walk(tree, 0, 0, 0)

            stale = [int(r["id"]) for r in existing if int(r["id"]) not in kept]
            if stale:
                # 全是 int，占位符拼接不引入注入面
                conn.execute(
                    "DELETE FROM mindmap_nodes WHERE id IN (%s)" % ", ".join("?" * len(stale)),
                    stale)
                stats["removed"] = len(stale)

            # 中心主题与标题本就是一回事，一次写掉，避免两处不一致
            title = str(tree.get("text") or "").strip() or DEFAULT_MAP_TITLE
            conn.execute("UPDATE mindmap SET title = ?, updated_at = ? WHERE id = ?",
                         (title, _now(), mid))
        return stats

    def save_outline_text(self, map_id, text, *, keep_collapsed=True) -> dict:
        """从**大纲文本**整树重存（界面左栏提交的路径）。

        ``keep_collapsed`` 打开时先把旧树的 ``collapsed`` / ``note`` 搬到新树 ——
        这两个字段都不在大纲文本里，不搬就是「双击折叠了半天，改一行字回来
        全展开了」。
        """
        mid = int(map_id)
        old_tree = self.load_tree(mid) if keep_collapsed else None
        new_tree = ml.parse_outline(text)
        if old_tree is not None:
            # 搬的不止 collapsed：note 也不在大纲文本里，一样会被整树重存洗掉
            new_tree = ml.carry_state(old_tree, new_tree, ("collapsed", "note"))
        return self.save_outline(mid, new_tree)

    def collapsed_flags(self, map_id) -> list[int]:
        """折叠状态的 DFS 快照（整树重存前先存一份）。"""
        tree = self.load_tree(map_id)
        return [1 if node.get("collapsed") else 0
                for node, _parent, _depth in ml.iter_nodes(tree)]

    def restore_collapsed(self, map_id, flags) -> None:
        """按 DFS 顺序把折叠快照贴回去。"""
        mid = int(map_id)
        tree = self.load_tree(mid)
        tree = ml.apply_collapsed(tree, flags)
        self.save_outline(mid, tree)

    def set_collapsed(self, node_id, value) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE mindmap_nodes SET collapsed = ? WHERE id = ?",
                               (1 if value else 0, int(node_id)))
            return cur.rowcount > 0

    def toggle_collapsed(self, node_id) -> dict | None:
        """翻转折叠态，返回 ``{"id", "collapsed"}``（找不到返回 ``None``）。"""
        nid = int(node_id)
        with self._connect() as conn:
            row = conn.execute("SELECT collapsed FROM mindmap_nodes WHERE id = ?",
                               (nid,)).fetchone()
            if row is None:
                return None
            value = 0 if int(row["collapsed"]) else 1
            conn.execute("UPDATE mindmap_nodes SET collapsed = ? WHERE id = ?",
                         (value, nid))
        return {"id": nid, "collapsed": bool(value)}

    def add_node(self, map_id, parent_id, text, *, seq=None, note="") -> int:
        mid = int(map_id)
        pid = int(parent_id or 0)
        if seq is None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), -1) + 1 AS nxt FROM mindmap_nodes "
                    "WHERE map_id = ? AND parent_id = ?", (mid, pid)).fetchone()
            seq = int(row["nxt"] if row else 0)
        if pid:
            depth_row = self._node_row(pid)
            depth = int(depth_row["depth"]) + 1 if depth_row else 1
        else:
            depth = 0
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO mindmap_nodes (map_id, parent_id, seq, depth, text, note, "
                "collapsed) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (mid, pid, int(seq), depth, str(text or ""), str(note or "")))
            conn.execute("UPDATE mindmap SET updated_at = ? WHERE id = ?", (_now(), mid))
            return int(cur.lastrowid)

    def _node_row(self, node_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM mindmap_nodes WHERE id = ?",
                               (int(node_id),)).fetchone()
        return dict(row) if row else None


    # ==================================================================
    # 自由画布（手工拖出来的节点坐标）
    # ==================================================================
    def node_positions(self, map_id) -> dict:
        """**被手工拖过**的节点坐标 ``{node_id: (x, y)}``。

        没拖过的节点**不出现在结果里**（库里是 NULL）—— 调用方拿到的是「要覆盖
        哪些」而不是「全部节点在哪」，于是新加的节点照旧走自动布局。
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, pos_x, pos_y FROM mindmap_nodes WHERE map_id = ? "
                "AND pos_x IS NOT NULL AND pos_y IS NOT NULL",
                (int(map_id),)).fetchall()
        return {int(r["id"]): (float(r["pos_x"]), float(r["pos_y"]))
                for r in rows}

    def set_node_pos(self, node_id, x, y) -> bool:
        """记住这个节点被拖到了哪。**只写这一行**，别的坐标一个字节都不动。"""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE mindmap_nodes SET pos_x = ?, pos_y = ? WHERE id = ?",
                (float(x), float(y), int(node_id)))
        return cur.rowcount > 0

    def clear_node_positions(self, map_id) -> int:
        """回到自动布局：清掉这张图的手工坐标，返回**真的清掉了几处**。

        只清 ``pos_x`` / ``pos_y`` 不为空的行 —— SQLite 的 ``rowcount``
        数的是**匹配到的行**，不加这个条件会把「本来就没坐标的节点」也算
        进来，于是一张 3 节点的图永远返回 3，界面上「已清掉 3 处」是虚报。
        """
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE mindmap_nodes SET pos_x = NULL, pos_y = NULL "
                "WHERE map_id = ? AND "
                "(pos_x IS NOT NULL OR pos_y IS NOT NULL)",
                (int(map_id),))
        return int(cur.rowcount or 0)

    def update_node(self, node_id, **fields) -> bool:
        allowed = ("text", "note", "collapsed", "seq", "depth", "parent_id")
        sets: list[str] = []
        params: list = []
        for key in allowed:
            if key in fields and fields[key] is not None:
                value = fields[key]
                if key == "collapsed":
                    value = 1 if value else 0
                sets.append(f"{key} = ?")
                params.append(value)
        if not sets:
            return False
        params.append(int(node_id))
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE mindmap_nodes SET {', '.join(sets)} WHERE id = ?", params)
            return cur.rowcount > 0

    def _subtree_ids(self, node_id) -> list[int]:
        """节点及其全部子孙的 id（递归 CTE，一次查完）。

        为什么不用「删一层再删一层」：孙子的 ``parent_id`` 会悬空，
        而 ``build_tree`` 的容错是「挂回根节点」—— 表现就是
        「删掉的枝又冒回根上」，比报错还难查。
        """
        with self._connect() as conn:
            rows = conn.execute(
                "WITH RECURSIVE sub(id) AS ("
                "  SELECT ? UNION ALL"
                "  SELECT n.id FROM mindmap_nodes n JOIN sub ON n.parent_id = sub.id"
                ") SELECT id FROM sub", (int(node_id),)).fetchall()
        return [int(r["id"]) for r in rows]

    def delete_node(self, node_id, *, keep_children=False) -> bool:
        """删节点。默认连子孙一起删；``keep_children=True`` 时把孩子提一级。"""
        nid = int(node_id)
        row = self._node_row(nid)
        if row is None:
            return False
        mid = int(row["map_id"])
        if keep_children:
            with self._connect() as conn:
                conn.execute("UPDATE mindmap_nodes SET parent_id = ? WHERE parent_id = ?",
                             (int(row["parent_id"]), nid))
        ids = self._subtree_ids(nid)
        if keep_children:
            ids = [nid]                     # 只删它自己，孩子已经提到上一级了
        if not ids:
            return False
        # ids 全是 int，占位符拼接不引入注入面
        placeholders = ", ".join("?" * len(ids))
        with self._connect() as conn:
            conn.execute(f"DELETE FROM mindmap_nodes WHERE id IN ({placeholders})", ids)
            conn.execute("UPDATE mindmap SET updated_at = ? WHERE id = ?", (_now(), mid))
        self._resync(mid)
        return True

    def _resync(self, map_id) -> None:
        """删/移之后重算 depth 与 seq，保证库里和树的表现一致。"""
        tree = self.load_tree(map_id)
        self.save_outline(map_id, tree)

    def move_node(self, node_id, delta) -> bool:
        """在同级里上下移动（``delta`` 为 -1 / +1）。"""
        nid = int(node_id)
        row = self._node_row(nid)
        if row is None:
            return False
        mid = int(row["map_id"])
        pid = int(row["parent_id"])
        with self._connect() as conn:
            siblings = [dict(r) for r in conn.execute(
                "SELECT id, seq FROM mindmap_nodes WHERE map_id = ? AND parent_id = ? "
                "ORDER BY seq, id", (mid, pid)).fetchall()]
        order = [int(s["id"]) for s in siblings]
        if nid not in order:
            return False
        index = order.index(nid)
        target = index + int(delta)
        if target < 0 or target >= len(order):
            return False
        order.insert(target, order.pop(index))
        with self._connect() as conn:
            for seq, node in enumerate(order):
                conn.execute("UPDATE mindmap_nodes SET seq = ? WHERE id = ?", (seq, node))
            conn.execute("UPDATE mindmap SET updated_at = ? WHERE id = ?", (_now(), mid))
        return True

    def indent_node(self, node_id, *, out=False) -> bool:
        """调层级：``out=False`` 降级（成为上一个兄弟的孩子），``True`` 升级。"""
        nid = int(node_id)
        row = self._node_row(nid)
        if row is None:
            return False
        mid = int(row["map_id"])
        pid = int(row["parent_id"])
        with self._connect() as conn:
            siblings = [dict(r) for r in conn.execute(
                "SELECT id, seq, text, note, collapsed FROM mindmap_nodes "
                "WHERE map_id = ? AND parent_id = ? ORDER BY seq, id",
                (mid, pid)).fetchall()]
        order = [int(s["id"]) for s in siblings]
        if nid not in order:
            return False
        index = order.index(nid)
        if out:
            # 升级：挂到爷爷下，插在父节点后面
            parent = self._node_row(pid) if pid else None
            if parent is None:
                return False
            new_parent = int(parent["parent_id"])
            if new_parent == 0:
                # 父节点已经是中心主题：再往外提就会凭空多出一个根。
                # 界面层用 depth <= 1 拦了同一条线，这里必须一起拦住 ——
                # 否则会「返回 True、实际什么都没变」，还白动一次 seq。
                return False
            with self._connect() as conn:
                conn.execute("UPDATE mindmap_nodes SET parent_id = ? WHERE id = ?",
                             (new_parent, nid))
            self._place_after(nid, int(parent["id"]))
        else:
            # 降级：成为上一个兄弟的最后一个孩子
            if index == 0:
                return False
            prev = int(order[index - 1])
            with self._connect() as conn:
                conn.execute("UPDATE mindmap_nodes SET parent_id = ? WHERE id = ?",
                             (prev, nid))
            with self._connect() as conn:
                row2 = conn.execute(
                    "SELECT COALESCE(MAX(seq), -1) + 1 AS nxt FROM mindmap_nodes "
                    "WHERE map_id = ? AND parent_id = ?", (mid, prev)).fetchone()
                conn.execute("UPDATE mindmap_nodes SET seq = ? WHERE id = ?",
                             (int(row2["nxt"] if row2 else 0), nid))
        self._resync(mid)
        return True

    def _place_after(self, node_id, sibling_id) -> None:
        """把 ``node_id`` 的 seq 插到 ``sibling_id`` 后面（同父时才有效）。"""
        nid = int(node_id)
        row = self._node_row(nid)
        sib = self._node_row(sibling_id)
        if row is None or sib is None:
            return
        if int(row["parent_id"]) != int(sib["parent_id"]):
            return
        with self._connect() as conn:
            siblings = [int(r["id"]) for r in conn.execute(
                "SELECT id FROM mindmap_nodes WHERE map_id = ? AND parent_id = ? "
                "ORDER BY seq, id", (int(row["map_id"]), int(row["parent_id"]))).fetchall()]
        if nid not in siblings or int(sibling_id) not in siblings:
            return
        siblings.remove(nid)
        siblings.insert(siblings.index(int(sibling_id)) + 1, nid)
        with self._connect() as conn:
            for seq, node in enumerate(siblings):
                conn.execute("UPDATE mindmap_nodes SET seq = ? WHERE id = ?", (seq, node))

    # ==================================================================
    # 训练参数（key/value）
    # ==================================================================
    def get_setting(self, key, default="") -> str:
        """读一个训练参数。**没有就返回 default**，不建行。"""
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM train_settings WHERE key = ?",
                               (str(key),)).fetchone()
        return str(row["value"]) if row else str(default)

    def set_setting(self, key, value) -> None:
        """写一个训练参数（**幂等 upsert**）。"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO train_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(key), str(value)))

    def get_algorithm(self) -> str:
        """当前用哪套间隔重复算法（``stairs`` / ``sm2`` / ``fsrs``）。"""
        return tc.normalize_algorithm(self.get_setting(SETTING_ALGORITHM))

    def set_algorithm(self, value) -> str:
        algorithm = tc.normalize_algorithm(value)
        self.set_setting(SETTING_ALGORITHM, algorithm)
        return algorithm

    # ==================================================================
    # 进度 + 复习（key = map_id，因为盲画的对象是整张图）
    # ==================================================================
    def get_progress(self, map_id) -> dict:
        """取进度。**不存在时返回默认值**，不建行（读操作不该有副作用）。"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM mindmap_progress WHERE map_id = ?",
                               (int(map_id),)).fetchone()
        if row:
            return dict(row)
        return {
            "map_id": int(map_id), "mastery": tc.MASTERY_NEW, "correct_streak": 0,
            "interval_days": 0, "next_review_at": "", "review_count": 0,
            "marked_at": "", "updated_at": "", "last_review_at": "",
            "ease_factor": tc.SM2_DEFAULT_EASE, "reps": 0,
            "stability": 0.0, "difficulty": tc.FSRS_DIFFICULTY_DEFAULT,
        }

    def ensure_progress(self, map_id) -> dict:
        """确保有进度行（**幂等**）。盲画过 / 手动标记时才建，这就是「懒创建」。

        **只建一行，不写假流水**：「标记已学过」不是一次盲画。往
        ``mindmap_reviews`` 里塞一条凑数会把正确率变成噪声。
        """
        mid = int(map_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM mindmap_progress WHERE map_id = ?",
                               (mid,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO mindmap_progress (map_id, mastery, correct_streak, "
                    "interval_days, next_review_at, review_count, marked_at, updated_at) "
                    "VALUES (?, ?, 0, 0, '', 0, ?, ?)",
                    (mid, tc.MASTERY_NEW, _now(), _now()))
        return self.get_progress(mid)

    def set_mastery(self, map_id, mastery, *, today=None) -> dict:
        """手动标掌握度。标成「生疏」及以上时把首次盲画**排到今天**（同 excel_db 口径）。"""
        mid = int(map_id)
        value = max(tc.MASTERY_NEW, min(tc.MASTERY_GOOD, int(mastery)))
        anchor = tc.parse_date(today) or date.today()
        current = self.get_progress(mid)
        interval = int(current.get("interval_days") or 0)
        next_at = str(current.get("next_review_at") or "")
        if value >= tc.MASTERY_WEAK and not next_at:
            interval = interval or 1
            next_at = anchor.isoformat()
        elif value <= tc.MASTERY_NEW:
            interval = 0
            next_at = ""
        with self._connect() as conn:
            if value <= tc.MASTERY_NEW:
                # 「取消已学」= 这张图要重新养：算法参数一并归零，免得下次拿旧稳定度算间隔
                conn.execute(
                    "UPDATE mindmap_progress SET ease_factor = ?, reps = 0, "
                    "stability = 0, difficulty = ?, last_review_at = '' "
                    "WHERE map_id = ?",
                    (tc.SM2_DEFAULT_EASE, tc.FSRS_DIFFICULTY_DEFAULT, mid))
            conn.execute(
                """
                INSERT INTO mindmap_progress (map_id, mastery, correct_streak,
                    interval_days, next_review_at, review_count, marked_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(map_id) DO UPDATE SET
                    mastery = excluded.mastery,
                    interval_days = excluded.interval_days,
                    next_review_at = excluded.next_review_at,
                    updated_at = excluded.updated_at
                """,
                (mid, value, int(current.get("correct_streak") or 0), interval,
                 next_at, _now(), _now()))
        return self.get_progress(mid)

    def record_review(self, map_id, feedback, *, today=None,
                      branch_hit=0, branch_total=0) -> dict:
        """记一次盲画：写流水 + 推进 SRS。**一次调用只写一行流水。**"""
        mid = int(map_id)
        anchor = tc.parse_date(today) or date.today()
        current = self.get_progress(mid)
        # FSRS 要看「距上次复习过了几天」—— 进度行的 updated_at 就是上次动它的时刻
        last_seen = (tc.parse_date(current.get("last_review_at"))
                     or tc.parse_date(current.get("updated_at")))
        state = tc.advance_review(
            feedback,
            algorithm=self.get_algorithm(),
            mastery=current.get("mastery", tc.MASTERY_NEW),
            streak=current.get("correct_streak", 0),
            interval_days=current.get("interval_days", 0),
            ease=current.get("ease_factor", tc.SM2_DEFAULT_EASE),
            reps=current.get("reps", 0),
            stability=current.get("stability", 0.0),
            difficulty=current.get("difficulty", 0.0),
            elapsed_days=(anchor - last_seen).days if last_seen else 0)
        next_at = (anchor + timedelta(days=int(state["interval_days"]))).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mindmap_progress (map_id, mastery, correct_streak,
                    interval_days, next_review_at, review_count, marked_at, updated_at,
                    last_review_at, ease_factor, reps, stability, difficulty)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(map_id) DO UPDATE SET
                    mastery = excluded.mastery,
                    correct_streak = excluded.correct_streak,
                    interval_days = excluded.interval_days,
                    next_review_at = excluded.next_review_at,
                    review_count = mindmap_progress.review_count + 1,
                    updated_at = excluded.updated_at,
                    last_review_at = excluded.last_review_at,
                    ease_factor = excluded.ease_factor,
                    reps = excluded.reps,
                    stability = excluded.stability,
                    difficulty = excluded.difficulty
                """,
                (mid, int(state["mastery"]), int(state["correct_streak"]),
                 int(state["interval_days"]), next_at, _stamp(anchor), _stamp(anchor),
                 anchor.isoformat(),
                 float(state["ease_factor"]), int(state["reps"]),
                 float(state["stability"]), float(state["difficulty"])))
            conn.execute(
                "INSERT INTO mindmap_reviews (map_id, review_date, feedback, "
                "mastery_after, branch_hit, branch_total, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mid, anchor.isoformat(), str(feedback), int(state["mastery"]),
                 int(branch_hit or 0), int(branch_total or 0), _now()))
        return {
            "map_id": mid, "feedback": str(feedback),
            "algorithm": str(state.get("algorithm", tc.DEFAULT_ALGORITHM)),
            "mastery": int(state["mastery"]),
            "correct_streak": int(state["correct_streak"]),
            "interval_days": int(state["interval_days"]),
            "next_review_at": next_at,
            "ease_factor": float(state["ease_factor"]),
            "reps": int(state["reps"]),
            "stability": float(state["stability"]),
            "difficulty": float(state["difficulty"]),
        }

    def list_reviews(self, *, map_id=None, since=None, until=None,
                     limit=None) -> list[dict]:
        sql = "SELECT * FROM mindmap_reviews WHERE 1 = 1"
        params: list = []
        if map_id is not None:
            sql += " AND map_id = ?"
            params.append(int(map_id))
        if since:
            sql += " AND review_date >= ?"
            params.append(str(since))
        if until:
            sql += " AND review_date <= ?"
            params.append(str(until))
        sql += " ORDER BY review_date DESC, id DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result = [dict(r) for r in rows]
        return result[: int(limit)] if limit is not None else result

    def review_accuracy(self, *, days=30, today=None) -> dict:
        anchor = tc.parse_date(today) or date.today()
        since = (anchor - timedelta(days=max(1, int(days)) - 1)).isoformat()
        rows = self.list_reviews(since=since)
        reviewed = len(rows)
        correct = sum(1 for r in rows if r["feedback"] == tc.FEEDBACK_KNOWN)
        return {"reviewed": reviewed, "correct": correct,
                "accuracy": tc.accuracy(reviewed, correct)}

    def mastery_distribution(self) -> dict:
        """掌握度分布。**以「全部导图」为分母** —— 没盲画过的也要算进「未学」那档。"""
        dist = {tc.MASTERY_NEW: 0, tc.MASTERY_WEAK: 0, tc.MASTERY_FAIR: 0,
                tc.MASTERY_GOOD: 0}
        for item in self.list_maps():
            level = int(item["mastery"] or 0)
            dist[level] = dist.get(level, 0) + 1
        return dist

    def due_maps(self, *, limit=None, today=None) -> list[dict]:
        """今天该盲画的导图。

        **必须 LEFT JOIN**：进度行懒创建，刚装好模板库时 ``mindmap_progress``
        里一行都没有。若只查进度表，「今日训练」首次打开会是空的 ——
        而那时候才是最该推新的。所以「没有进度行」一律算「待学」。
        """
        anchor = tc.parse_date(today) or date.today()
        maps = self.list_maps(today=anchor)
        due = [m for m in maps
               if not str(m["next_review_at"] or "").strip()
               or str(m["next_review_at"]) <= anchor.isoformat()]
        # 没排过期的（新图）排后面，到期日早的排前面
        due.sort(key=lambda m: (1 if not str(m["next_review_at"] or "").strip() else 0,
                                str(m["next_review_at"] or ""), -int(m["id"])))
        return due[: int(limit)] if limit is not None else due

    def due_count(self, *, today=None) -> int:
        return sum(1 for m in self.due_maps(today=today) if m["due"])

    def new_candidates(self, *, limit=None) -> list[dict]:
        """还没盲画过的图（进度行缺失或 mastery == 0）。"""
        fresh = [m for m in self.list_maps()
                 if int(m["mastery"]) <= tc.MASTERY_NEW
                 and not str(m["next_review_at"] or "").strip()]
        return fresh[: int(limit)] if limit is not None else fresh

    # ==================================================================
    # 打卡
    # ==================================================================
    def checkin(self, check_date=None, *, minutes=None, maps_new=None,
                maps_reviewed=None, accuracy=None, note=None) -> dict:
        """打卡。**同一天重复调用是更新**，不是新增一行。

        传 ``None`` 的字段 = 不改动（用户补一句备注，不该把分钟数清零）。
        """
        day = (tc.parse_date(check_date) or date.today()).isoformat()
        current = self.get_checkin(day) or {
            "check_date": day, "minutes": 0, "maps_new": 0,
            "maps_reviewed": 0, "accuracy": 0.0, "note": "",
        }
        merged = dict(current)
        if minutes is not None:
            merged["minutes"] = int(minutes or 0)
        if maps_new is not None:
            merged["maps_new"] = int(maps_new or 0)
        if maps_reviewed is not None:
            merged["maps_reviewed"] = int(maps_reviewed or 0)
        if accuracy is not None:
            merged["accuracy"] = float(accuracy or 0.0)
        if note is not None:
            merged["note"] = str(note or "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mindmap_checkins (check_date, minutes, maps_new,
                    maps_reviewed, accuracy, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(check_date) DO UPDATE SET
                    minutes = excluded.minutes,
                    maps_new = excluded.maps_new,
                    maps_reviewed = excluded.maps_reviewed,
                    accuracy = excluded.accuracy,
                    note = excluded.note
                """,
                (day, merged["minutes"], merged["maps_new"], merged["maps_reviewed"],
                 merged["accuracy"], merged["note"], _now()))
        return self.get_checkin(day)

    def get_checkin(self, check_date=None) -> dict | None:
        day = (tc.parse_date(check_date) or date.today()).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM mindmap_checkins WHERE check_date = ?",
                               (day,)).fetchone()
        return dict(row) if row else None

    def list_checkins(self, *, start=None, end=None) -> list[dict]:
        sql = "SELECT * FROM mindmap_checkins WHERE 1 = 1"
        params: list = []
        if start:
            sql += " AND check_date >= ?"
            params.append(str(start))
        if end:
            sql += " AND check_date <= ?"
            params.append(str(end))
        sql += " ORDER BY check_date"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def checkin_dates(self) -> list[str]:
        return [str(r["check_date"]) for r in self.list_checkins()]

    # ==================================================================
    # 教学卡
    # ==================================================================
    def list_cards(self) -> list[dict]:
        return [dict(card) for card in mindmap_seed.TEACHING_CARDS]

    def get_card(self, code) -> dict | None:
        for card in mindmap_seed.TEACHING_CARDS:
            if card["code"] == str(code):
                return dict(card)
        return None

    def card_categories(self) -> list[str]:
        return mindmap_seed.card_categories()

    # ==================================================================
    # 统计汇总
    # ==================================================================
    def stats(self, *, days=30, today=None) -> dict:
        anchor = tc.parse_date(today) or date.today()
        start = (anchor - timedelta(days=max(1, int(days)) - 1)).isoformat()
        rows = self.list_checkins(start=start)
        summary = tc.summarize(rows)
        dates = self.checkin_dates()
        accuracy = self.review_accuracy(days=days, today=anchor)
        maps = self.list_maps()
        return {
            "days": summary["days"],
            "minutes": summary["minutes"],
            "maps_new": summary.get("items_new", 0),
            "maps_reviewed": summary.get("items_reviewed", 0),
            "avg_minutes": summary["avg_minutes"],
            "streak": tc.streak_from_dates(dates, anchor),
            "best_streak": tc.best_streak_from_dates(dates),
            "accuracy": accuracy["accuracy"],
            "reviewed": accuracy["reviewed"],
            "correct": accuracy["correct"],
            "mastery": self.mastery_distribution(),
            "maps": len(maps),
            "nodes": sum(int(m["node_count"] or 0) for m in maps),
            "due": self.due_count(today=anchor),
        }

    def new_today(self, *, today=None) -> int:
        """今天**新标记**了几张（看 ``marked_at`` 的前 10 个字符就是日期）。"""
        day = (tc.parse_date(today) or date.today()).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM mindmap_progress "
                "WHERE substr(marked_at, 1, 10) = ?", (day,)).fetchone()
        return int(row["n"] if row else 0)

    def autofill_today(self, *, today=None) -> dict:
        """按今天的实际流水把打卡数字补全（``minutes`` 留给用户填）。"""
        anchor = (tc.parse_date(today) or date.today()).isoformat()
        rows = self.list_reviews(since=anchor, until=anchor)
        reviewed = len(rows)
        correct = sum(1 for r in rows if r["feedback"] == tc.FEEDBACK_KNOWN)
        return self.checkin(
            anchor, maps_reviewed=reviewed, maps_new=self.new_today(today=anchor),
            accuracy=tc.accuracy(reviewed, correct))


# ======================================================================
# 小工具（界面用；放这里是因为它只依赖本模块的数据形状）
# ======================================================================
def suggest_new_count(*, due_total, target_new=None) -> int:
    """今天建议新画几张：由「待盲画量」反向决定 —— 复习多就少画新的。"""
    return ml.suggest_new_count(due_total=due_total, target_new=target_new)


_TAG_SPLIT = re.compile(r"[|,、;；\s]+")


def split_tags(text) -> list[str]:
    """标签串 → 列表（``|`` ``,`` ``、`` ``;`` 与空白都算分隔）。"""
    return [t for t in _TAG_SPLIT.split(str(text or "")) if t]


def format_map_line(item: dict) -> str:
    """导图的一行摘要（列表与结算卡共用，避免两处各写一份）。"""
    title = str(item.get("title", "") or "").strip()
    nodes = int(item.get("node_count") or 0)
    return f"{title}（{nodes} 个节点）" if nodes else title
