# -*- coding: utf-8 -*-
"""记忆宫殿 · 数据层。

边界（与 ``excel_db.py`` / ``todo_db.py`` 同一套约定）
------------------------------------------------------------------------------
* **不 import tkinter** —— 可以脱离窗口单测。
* 表全部 ``CREATE TABLE IF NOT EXISTS``，**不动任何既有表**（老库直接可用）。
* 间隔重复的算法**不在这里**，在 ``training_core``；这里只负责读写与落库。

六张业务表 + 两张题库表
------------------------------------------------------------------------------
    memory_palaces     宫殿（地点桩路线的容器）
    memory_loci        地点桩（seq 决定「走一遍」的顺序）
    memory_items       记忆项（front/back + 联想画面 + 故事链）
    memory_progress    每条记忆项的 SRS 状态 —— **懒创建**
    memory_reviews     复习流水（只增不改，用来画正确率曲线）
    memory_checkins    打卡（一天一行）
    memory_banks       题库
    memory_bank_items  题库条目

两条纪律
------------------------------------------------------------------------------
1. **``memory_progress`` 是懒创建的** —— 所有「今日该练什么」的查询**必须 LEFT JOIN**，
   内连接会把「刚建好、还没学过」的记忆项整片滤掉，而那恰恰是最该推新的。
2. **``checkin`` 同日重复写是 UPDATE 不是 INSERT** —— 用户练完想补一句备注，
   不该多出一行（那会让「打卡天数」虚高）。
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, timedelta

import memory_seed
import training_core as tc

logger = logging.getLogger(__name__)

PALACE_KINDS = ("住宅", "通勤", "虚拟", "自定义")

DEFAULT_PALACE_NAME = "我的记忆宫殿"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _like_kw(keyword) -> str:
    return f"%{str(keyword or '').strip()}%"


class MemoryPalaceDB:
    """记忆宫殿的数据库操作类。"""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._init_tables()
        self.seed_banks()

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
                CREATE TABLE IF NOT EXISTS memory_palaces (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    kind        TEXT NOT NULL DEFAULT '自定义',
                    description TEXT NOT NULL DEFAULT '',
                    route_note  TEXT NOT NULL DEFAULT '',
                    tags        TEXT NOT NULL DEFAULT '',
                    source_key  TEXT NOT NULL DEFAULT '',
                    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            # 部分唯一索引：source_key 为空的（用户自建）不参与唯一性
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_mem_palace_source "
                         "ON memory_palaces(source_key) WHERE source_key <> ''")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_loci (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    palace_id  INTEGER NOT NULL,
                    seq        INTEGER NOT NULL DEFAULT 0,
                    name       TEXT NOT NULL,
                    hint       TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_loci_palace "
                         "ON memory_loci(palace_id, seq)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_items (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    palace_id  INTEGER NOT NULL DEFAULT 0,
                    locus_id   INTEGER NOT NULL DEFAULT 0,
                    front      TEXT NOT NULL,
                    back       TEXT NOT NULL DEFAULT '',
                    imagery    TEXT NOT NULL DEFAULT '',
                    story      TEXT NOT NULL DEFAULT '',
                    detail     TEXT NOT NULL DEFAULT '',
                    images     TEXT NOT NULL DEFAULT '',
                    category   TEXT NOT NULL DEFAULT '',
                    tags       TEXT NOT NULL DEFAULT '',
                    source_key TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_mem_item_source "
                         "ON memory_items(source_key) WHERE source_key <> ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_items_palace "
                         "ON memory_items(palace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_items_locus "
                         "ON memory_items(locus_id)")

            # 进度：**懒创建**（学到才建行）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_progress (
                    item_id        INTEGER PRIMARY KEY,
                    mastery        INTEGER NOT NULL DEFAULT 0,
                    correct_streak INTEGER NOT NULL DEFAULT 0,
                    interval_days  INTEGER NOT NULL DEFAULT 0,
                    next_review_at TEXT NOT NULL DEFAULT '',
                    review_count   INTEGER NOT NULL DEFAULT 0,
                    marked_at      TEXT NOT NULL DEFAULT '',
                    updated_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_progress_due "
                         "ON memory_progress(next_review_at)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_reviews (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id       INTEGER NOT NULL,
                    review_date   TEXT NOT NULL,
                    feedback      TEXT NOT NULL,
                    mastery_after INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_reviews_date "
                         "ON memory_reviews(review_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_reviews_item "
                         "ON memory_reviews(item_id)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_checkins (
                    check_date     TEXT PRIMARY KEY,
                    minutes        INTEGER NOT NULL DEFAULT 0,
                    items_new      INTEGER NOT NULL DEFAULT 0,
                    items_reviewed INTEGER NOT NULL DEFAULT 0,
                    accuracy       REAL NOT NULL DEFAULT 0,
                    note           TEXT NOT NULL DEFAULT '',
                    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_banks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    code        TEXT NOT NULL UNIQUE,
                    name        TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    sort_order  INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_bank_items (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    bank_id  INTEGER NOT NULL,
                    seq      INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer   TEXT NOT NULL DEFAULT '',
                    hint     TEXT NOT NULL DEFAULT '',
                    detail   TEXT NOT NULL DEFAULT '',
                    images   TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_bank_items "
                         "ON memory_bank_items(bank_id, seq)")

            # 老库没有的列在这里补上（新库建表时已经有了，这里是空操作）
            self._ensure_memory_columns(conn)

    def _ensure_memory_columns(self, conn) -> None:
        """缺列就 ``ALTER TABLE ADD COLUMN``；**不动存量数据、不重建表**。

        为什么需要它：``CREATE TABLE IF NOT EXISTS`` 只对新库生效 —— 开发机和
        用户的 exe 里那份 db 早就建好了，新加的 ``detail`` / ``images``
        不加这一步就会永远缺失，而且是**静默**缺失（读出来是 KeyError 或空串）。
        """
        wanted = {
            "memory_items": (
                ("detail", "TEXT NOT NULL DEFAULT ''"),
                ("images", "TEXT NOT NULL DEFAULT ''"),
            ),
            "memory_bank_items": (
                ("detail", "TEXT NOT NULL DEFAULT ''"),
                ("images", "TEXT NOT NULL DEFAULT ''"),
            ),
        }
        for table, columns in wanted.items():
            have = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, ddl in columns:
                if column in have:
                    continue
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # ==================================================================
    # 题库（内置，安装时灌一遍；幂等）
    # ==================================================================
    def seed_banks(self) -> int:
        """把 ``memory_seed.BANKS`` 灌进题库表。**幂等**：重跑不重复插。

        已存在的条目按「谁拥有这一栏」分别处理：题干 / 答案 / 提示以种子为准
        （这样改正错字能推给老库），``detail`` 只在空着时补，``images`` 不动 ——
        后两栏是用户自己写的位置笔记和游戏截图。
        """
        inserted = 0
        with self._connect() as conn:
            for order, bank in enumerate(memory_seed.BANKS):
                row = conn.execute("SELECT id FROM memory_banks WHERE code = ?",
                                   (bank["code"],)).fetchone()
                if row:
                    bank_id = int(row["id"])
                    conn.execute(
                        "UPDATE memory_banks SET name = ?, description = ?, sort_order = ? "
                        "WHERE id = ?",
                        (bank["name"], bank["description"], order, bank_id))
                else:
                    cur = conn.execute(
                        "INSERT INTO memory_banks (code, name, description, sort_order) "
                        "VALUES (?, ?, ?, ?)",
                        (bank["code"], bank["name"], bank["description"], order))
                    bank_id = int(cur.lastrowid)
                    inserted += 1
                exists = {int(r["seq"]): int(r["id"]) for r in conn.execute(
                    "SELECT id, seq FROM memory_bank_items WHERE bank_id = ?", (bank_id,))}
                for item in bank["items"]:
                    seq = int(item["seq"])
                    if seq in exists:
                        # 题干 / 答案 / 提示是内置文案，种子才是权威（纠错、改措辞
                        # 靠重灌推给老库）；**detail 只在还空着的时候补** —— 给老题库
                        # 补「四周细节」靠的就是这一步，而用户自己在弹窗里写的笔记
                        # 不能被冲掉（弹窗明说了「可以自己补充」）。images 同理，
                        # 那是用户自己截的图，任何情况下都不覆盖。
                        conn.execute(
                            "UPDATE memory_bank_items SET question = ?, answer = ?, "
                            "hint = ?, detail = CASE WHEN TRIM(detail) = '' "
                            "THEN ? ELSE detail END WHERE id = ?",
                            (item["question"], item["answer"], item.get("hint", ""),
                             item.get("detail", ""), exists[seq]))
                        continue
                    conn.execute(
                        "INSERT INTO memory_bank_items (bank_id, seq, question, answer, "
                        "hint, detail) VALUES (?, ?, ?, ?, ?, ?)",
                        (bank_id, seq, item["question"], item["answer"],
                         item.get("hint", ""), item.get("detail", "")))
        return inserted

    def list_banks(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT b.*, (SELECT COUNT(*) FROM memory_bank_items i
                              WHERE i.bank_id = b.id) AS item_count
                  FROM memory_banks b ORDER BY b.sort_order, b.id
                """).fetchall()
        return [dict(r) for r in rows]

    def get_bank(self, bank_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_banks WHERE id = ?",
                               (int(bank_id),)).fetchone()
        return dict(row) if row else None

    def get_bank_by_code(self, code) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_banks WHERE code = ?",
                               (str(code),)).fetchone()
        return dict(row) if row else None

    def list_bank_items(self, bank_id) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_bank_items WHERE bank_id = ? ORDER BY seq",
                (int(bank_id),)).fetchall()
        return [dict(r) for r in rows]

    def get_bank_item(self, item_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_bank_items WHERE id = ?",
                               (int(item_id),)).fetchone()
        return dict(row) if row else None

    def update_bank_item(self, item_id, **fields) -> bool:
        """改题库项。**只放行 ``detail`` / ``images`` 两个用户字段** ——
        题干 / 答案 / 提示 / 序号都由内置种子决定，不允许就地改（会被下次
        ``seed_banks`` 覆盖回去，用户会以为「改了没用」）。
        """
        allowed = ("detail", "images")
        sets = [(k, fields[k]) for k in allowed if k in fields]
        if not sets:
            return False
        clause = ", ".join(f"{k} = ?" for k, _ in sets)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE memory_bank_items SET {clause} WHERE id = ?",
                [v for _, v in sets] + [int(item_id)])
            return cur.rowcount > 0

    # ==================================================================
    # 宫殿
    # ==================================================================
    def add_palace(self, name, *, kind="自定义", description="", route_note="",
                   tags="", source_key="") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO memory_palaces (name, kind, description, route_note, tags, "
                "source_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(name).strip() or DEFAULT_PALACE_NAME, str(kind or "自定义"),
                 str(description or ""), str(route_note or ""), str(tags or ""),
                 str(source_key or ""), _now()))
            return int(cur.lastrowid)

    def update_palace(self, palace_id, **fields) -> bool:
        allowed = ("name", "kind", "description", "route_note", "tags")
        sets = [(k, fields[k]) for k in allowed if k in fields]
        if not sets:
            return False
        clause = ", ".join(f"{k} = ?" for k, _ in sets)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE memory_palaces SET {clause} WHERE id = ?",
                               [v for _, v in sets] + [int(palace_id)])
            return cur.rowcount > 0

    def get_palace(self, palace_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_palaces WHERE id = ?",
                               (int(palace_id),)).fetchone()
        return dict(row) if row else None

    def get_palace_by_source(self, source_key) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_palaces WHERE source_key = ?",
                               (str(source_key or ""),)).fetchone()
        return dict(row) if row else None

    def list_palaces(self, keyword=None) -> list[dict]:
        """宫殿列表，带桩数 / 记忆项数 / 待复习数（用于左栏）。"""
        sql = """
            SELECT p.*,
                   (SELECT COUNT(*) FROM memory_loci l WHERE l.palace_id = p.id)  AS locus_count,
                   (SELECT COUNT(*) FROM memory_items i WHERE i.palace_id = p.id) AS item_count
              FROM memory_palaces p
        """
        params: list = []
        if str(keyword or "").strip():
            sql += " WHERE p.name LIKE ? OR p.tags LIKE ?"
            params += [_like_kw(keyword), _like_kw(keyword)]
        sql += " ORDER BY p.id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def delete_palace(self, palace_id, *, keep_items=False) -> bool:
        """删宫殿。默认连它的桩与记忆项一起删（进度与流水也清）。

        ``keep_items=True`` 时把记忆项改成「未归档」（palace_id / locus_id 归零），
        不丢内容 —— 界面上删宫殿前会问一句。
        """
        pid = int(palace_id)
        with self._connect() as conn:
            if keep_items:
                conn.execute("UPDATE memory_items SET palace_id = 0, locus_id = 0 "
                             "WHERE palace_id = ?", (pid,))
            else:
                ids = [int(r["id"]) for r in conn.execute(
                    "SELECT id FROM memory_items WHERE palace_id = ?", (pid,))]
                for item_id in ids:
                    self._purge_item(conn, item_id)
                conn.execute("DELETE FROM memory_items WHERE palace_id = ?", (pid,))
            conn.execute("DELETE FROM memory_loci WHERE palace_id = ?", (pid,))
            cur = conn.execute("DELETE FROM memory_palaces WHERE id = ?", (pid,))
            return cur.rowcount > 0

    def _purge_item(self, conn, item_id) -> None:
        conn.execute("DELETE FROM memory_progress WHERE item_id = ?", (int(item_id),))
        conn.execute("DELETE FROM memory_reviews WHERE item_id = ?", (int(item_id),))

    # -- 模板导入 -------------------------------------------------------
    def import_template(self, template_code, *, name=None) -> int:
        """把内置宫殿模板建成一座真宫殿。**幂等**：同一模板只导一次。

        幂等靠 ``source_key``（部分唯一索引）：已导过就返回既有宫殿 id，
        不会每点一次多出一座「我的住宅」。
        """
        tpl = next((t for t in memory_seed.PALACE_TEMPLATES
                    if t["code"] == template_code), None)
        if tpl is None:
            raise KeyError(f"没有这个宫殿模板：{template_code}")
        source_key = f"template:{template_code}"
        existing = self.get_palace_by_source(source_key)
        if existing:
            return int(existing["id"])

        palace_id = self.add_palace(
            name or tpl["name"], kind=tpl["kind"], description=tpl["description"],
            route_note=tpl["route_note"], source_key=source_key)
        with self._connect() as conn:
            for seq, (locus_name, hint) in enumerate(tpl["loci"]):
                conn.execute(
                    "INSERT INTO memory_loci (palace_id, seq, name, hint, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (palace_id, seq, locus_name, hint, _now()))
        return palace_id

    def import_all_templates(self) -> list[int]:
        return [self.import_template(t["code"]) for t in memory_seed.PALACE_TEMPLATES]

    def import_number_pegs(self, *, name="数字桩（00–99）",
                           palace_name=None) -> int:
        """把 100 个数字桩建成一座宫殿：**每个数字桩就是一个地点桩**。幂等。"""
        source_key = "pegs:00-99"
        existing = self.get_palace_by_source(source_key)
        if existing:
            return int(existing["id"])
        palace_id = self.add_palace(
            palace_name or name, kind="虚拟",
            description="00–99 一百个固定图像。练「数字记忆」的地基："
                        "先把这 100 个图像背熟，之后任何数字串都能两位一组转成画面。",
            route_note="按 00 → 99 顺序走，不要打乱。",
            source_key=source_key)
        with self._connect() as conn:
            for seq, (code, image, note) in enumerate(memory_seed.NUMBER_PEGS):
                conn.execute(
                    "INSERT INTO memory_loci (palace_id, seq, name, hint, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (palace_id, seq, f"{code} {image}", note, _now()))
        return palace_id

    # ==================================================================
    # 地点桩
    # ==================================================================
    def add_locus(self, palace_id, name, *, hint="", seq=None) -> int:
        pid = int(palace_id)
        with self._connect() as conn:
            if seq is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), -1) + 1 AS nxt FROM memory_loci "
                    "WHERE palace_id = ?", (pid,)).fetchone()
                seq = int(row["nxt"])
            cur = conn.execute(
                "INSERT INTO memory_loci (palace_id, seq, name, hint, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pid, int(seq), str(name).strip(), str(hint or ""), _now()))
            return int(cur.lastrowid)

    def update_locus(self, locus_id, **fields) -> bool:
        allowed = ("name", "hint", "seq", "palace_id")
        sets = [(k, fields[k]) for k in allowed if k in fields]
        if not sets:
            return False
        clause = ", ".join(f"{k} = ?" for k, _ in sets)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE memory_loci SET {clause} WHERE id = ?",
                               [v for _, v in sets] + [int(locus_id)])
            return cur.rowcount > 0

    def get_locus(self, locus_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_loci WHERE id = ?",
                               (int(locus_id),)).fetchone()
        return dict(row) if row else None

    def list_loci(self, palace_id) -> list[dict]:
        """宫殿里的桩，按 walk 顺序。带该桩挂了几条记忆项。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT l.*, (SELECT COUNT(*) FROM memory_items i
                              WHERE i.locus_id = l.id) AS item_count
                  FROM memory_loci l WHERE l.palace_id = ?
                 ORDER BY l.seq, l.id
                """, (int(palace_id),)).fetchall()
        return [dict(r) for r in rows]

    def delete_locus(self, locus_id) -> bool:
        """删桩。桩上的记忆项**不删**，改成未归档（内容比位置重要）。

        删完把该宫殿剩下的 seq **压实**（0,1,2,…），否则「走一遍」会出现空档。
        """
        lid = int(locus_id)
        locus = self.get_locus(lid)
        if not locus:
            return False
        with self._connect() as conn:
            conn.execute("UPDATE memory_items SET locus_id = 0 WHERE locus_id = ?", (lid,))
            conn.execute("DELETE FROM memory_loci WHERE id = ?", (lid,))
            self._compact_loci(conn, int(locus["palace_id"]))
        return True

    def _compact_loci(self, conn, palace_id) -> None:
        rows = conn.execute(
            "SELECT id FROM memory_loci WHERE palace_id = ? ORDER BY seq, id",
            (int(palace_id),)).fetchall()
        for index, row in enumerate(rows):
            conn.execute("UPDATE memory_loci SET seq = ? WHERE id = ?",
                         (index, int(row["id"])))

    def reorder_loci(self, palace_id, ordered_ids) -> None:
        """按给定顺序重排桩（拖拽后调用）。只认属于这座宫殿的 id。"""
        pid = int(palace_id)
        with self._connect() as conn:
            current = [int(r["id"]) for r in conn.execute(
                "SELECT id FROM memory_loci WHERE palace_id = ? ORDER BY seq, id", (pid,))]
            valid = set(current)
            wanted = [int(x) for x in ordered_ids if int(x) in valid]
            # 去重但保序：同一个 id 在 ordered_ids 里出现两次，只认第一次
            seen: set[int] = set()
            ordered: list[int] = []
            for locus_id in wanted:
                if locus_id not in seen:
                    seen.add(locus_id)
                    ordered.append(locus_id)
            # 没被提到的桩接在后面，保持它们原来的相对顺序
            ordered.extend(x for x in current if x not in seen)
            for index, locus_id in enumerate(ordered):
                conn.execute("UPDATE memory_loci SET seq = ? WHERE id = ?",
                             (index, locus_id))

    def move_locus(self, locus_id, delta) -> bool:
        """上移 / 下移一格（``delta`` 为 -1 / +1）。"""
        locus = self.get_locus(locus_id)
        if not locus:
            return False
        pid = int(locus["palace_id"])
        loci = self.list_loci(pid)
        ids = [int(l["id"]) for l in loci]
        if locus_id not in ids:
            return False
        index = ids.index(int(locus_id))
        target = max(0, min(len(ids) - 1, index + int(delta)))
        if target == index:
            return False
        ids.insert(target, ids.pop(index))
        self.reorder_loci(pid, ids)
        return True

    # ==================================================================
    # 记忆项
    # ==================================================================
    def add_item(self, *, front, back="", palace_id=0, locus_id=0, imagery="",
                 story="", detail="", images="", category="", tags="",
                 source_key="") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO memory_items (palace_id, locus_id, front, back, imagery, "
                "story, detail, images, category, tags, source_key, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (int(palace_id or 0), int(locus_id or 0), str(front).strip(),
                 str(back or ""), str(imagery or ""), str(story or ""),
                 str(detail or ""), str(images or ""),
                 str(category or ""), str(tags or ""), str(source_key or ""), _now()))
            return int(cur.lastrowid)

    def update_item(self, item_id, **fields) -> bool:
        allowed = ("front", "back", "imagery", "story", "detail", "images",
                   "category", "tags", "palace_id", "locus_id")
        sets = [(k, fields[k]) for k in allowed if k in fields]
        if not sets:
            return False
        clause = ", ".join(f"{k} = ?" for k, _ in sets)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE memory_items SET {clause} WHERE id = ?",
                               [v for _, v in sets] + [int(item_id)])
            return cur.rowcount > 0

    def get_item(self, item_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_items WHERE id = ?",
                               (int(item_id),)).fetchone()
        return dict(row) if row else None

    def delete_item(self, item_id) -> bool:
        iid = int(item_id)
        with self._connect() as conn:
            self._purge_item(conn, iid)
            cur = conn.execute("DELETE FROM memory_items WHERE id = ?", (iid,))
            return cur.rowcount > 0

    def list_items(self, *, palace_id=None, locus_id=None, category=None,
                   mastery=None, keyword=None, unassigned=False,
                   limit=None) -> list[dict]:
        """记忆项列表。**每一行都带 ``mastery`` / ``next_review_at`` / ``due``**。

        为什么用 LEFT JOIN 而不是内连接：进度行是懒创建的，刚建好的项没有进度行 ——
        内连接会让「记忆项库」在刚开始用的时候是空的。
        """
        sql = """
            SELECT i.*,
                   COALESCE(p.mastery, 0)        AS mastery,
                   COALESCE(p.next_review_at, '') AS next_review_at,
                   COALESCE(p.review_count, 0)    AS review_count,
                   COALESCE(p.correct_streak, 0)  AS correct_streak,
                   COALESCE(p.interval_days, 0)   AS interval_days,
                   COALESCE(l.name, '')           AS locus_name,
                   COALESCE(l.seq, -1)            AS locus_seq,
                   COALESCE(pl.name, '')          AS palace_name
              FROM memory_items i
              LEFT JOIN memory_progress p ON p.item_id = i.id
              LEFT JOIN memory_loci     l ON l.id = i.locus_id
              LEFT JOIN memory_palaces  pl ON pl.id = i.palace_id
             WHERE 1 = 1
        """
        params: list = []
        if palace_id is not None:
            sql += " AND i.palace_id = ?"
            params.append(int(palace_id))
        if locus_id is not None:
            sql += " AND i.locus_id = ?"
            params.append(int(locus_id))
        if category:
            sql += " AND i.category = ?"
            params.append(str(category))
        if unassigned:
            sql += " AND (i.palace_id = 0 OR i.locus_id = 0)"
        if str(keyword or "").strip():
            sql += (" AND (i.front LIKE ? OR i.back LIKE ? OR i.imagery LIKE ?"
                    " OR i.story LIKE ? OR i.tags LIKE ?)")
            params += [_like_kw(keyword)] * 5
        sql += " ORDER BY i.palace_id, COALESCE(l.seq, 9999), i.id"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result = [dict(r) for r in rows]
        today = tc.today_str()
        for item in result:
            item["due"] = tc.due_bucket(item["next_review_at"], today) == "due"
            item["bucket"] = tc.due_bucket(item["next_review_at"], today)
        if mastery is not None:
            result = [x for x in result if int(x["mastery"]) == int(mastery)]
        if limit is not None:
            result = result[: int(limit)]
        return result

    def count_items(self, **kwargs) -> int:
        return len(self.list_items(**kwargs))

    def categories(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM memory_items "
                "WHERE TRIM(COALESCE(category, '')) <> '' ORDER BY category").fetchall()
        return [str(r["category"]) for r in rows]

    def due_items(self, *, limit=None, palace_id=None, today=None) -> list[dict]:
        """今天该复习的项。

        **必须 LEFT JOIN**：进度行懒创建，没学过 / 刚装好种子库时
        ``memory_progress`` 里一行都没有。若只查进度表，「今日训练」首次打开会是空的 ——
        而那时候才是最该推新的。所以「没有进度行」一律算「没排过期的待学项」。
        """
        anchor = tc.parse_date(today) or date.today()
        sql = """
            SELECT i.*,
                   COALESCE(p.mastery, 0)         AS mastery,
                   COALESCE(p.next_review_at, '') AS next_review_at,
                   COALESCE(p.review_count, 0)    AS review_count,
                   COALESCE(l.name, '')           AS locus_name,
                   COALESCE(l.seq, -1)            AS locus_seq,
                   COALESCE(pl.name, '')          AS palace_name
              FROM memory_items i
              LEFT JOIN memory_progress p ON p.item_id = i.id
              LEFT JOIN memory_loci     l ON l.id = i.locus_id
              LEFT JOIN memory_palaces  pl ON pl.id = i.palace_id
             WHERE COALESCE(p.next_review_at, '') = '' OR p.next_review_at <= ?
        """
        params: list = [anchor.isoformat()]
        if palace_id is not None:
            sql += " AND i.palace_id = ?"
            params.append(int(palace_id))
        sql += (" ORDER BY CASE WHEN COALESCE(p.next_review_at, '') = '' THEN 1 ELSE 0 END,"
                " p.next_review_at, i.palace_id, COALESCE(l.seq, 9999), i.id")
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result = [dict(r) for r in rows]
        for item in result:
            item["bucket"] = tc.due_bucket(item["next_review_at"], anchor)
            item["due"] = item["bucket"] == "due"
        if limit is not None:
            result = result[: int(limit)]
        return result

    def due_count(self, *, today=None) -> int:
        return sum(1 for x in self.due_items(today=today) if x["due"])

    def new_candidates(self, *, limit=None, palace_id=None) -> list[dict]:
        """还没学过的项（进度行缺失或 mastery == 0），按宫殿与桩序。"""
        items = self.list_items(palace_id=palace_id)
        fresh = [x for x in items if int(x["mastery"]) <= tc.MASTERY_NEW
                 and not str(x["next_review_at"] or "").strip()]
        return fresh[: int(limit)] if limit is not None else fresh

    def walk_order(self, palace_id) -> list[dict]:
        """「走一遍」的顺序：**按桩的 seq**，一个桩上挂的项按 id。

        桩上没有项的跳过；没有宫殿的项排在最后（如果有的话）。
        """
        loci = self.list_loci(palace_id)
        items = self.list_items(palace_id=palace_id)
        by_locus: dict[int, list[dict]] = {}
        for item in items:
            by_locus.setdefault(int(item["locus_id"] or 0), []).append(item)

        ordered: list[dict] = []
        for locus in loci:
            for item in by_locus.get(int(locus["id"]), []):
                row = dict(item)
                row["station"] = int(locus["seq"]) + 1
                row["locus_name"] = locus["name"]
                row["locus_hint"] = locus["hint"]
                ordered.append(row)
        for item in by_locus.get(0, []):
            row = dict(item)
            row["station"] = 0
            row["locus_name"] = "（未分配桩）"
            row["locus_hint"] = ""
            ordered.append(row)
        return ordered

    def item_counts_by_locus(self, palace_id) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT locus_id, COUNT(*) AS n FROM memory_items "
                "WHERE palace_id = ? GROUP BY locus_id", (int(palace_id),)).fetchall()
        return {int(r["locus_id"]): int(r["n"]) for r in rows}

    # ==================================================================
    # 进度 + 复习
    # ==================================================================
    def get_progress(self, item_id) -> dict:
        """取进度。**不存在时返回默认值**，不建行（读操作不该有副作用）。"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_progress WHERE item_id = ?",
                               (int(item_id),)).fetchone()
        if row:
            return dict(row)
        return {
            "item_id": int(item_id), "mastery": tc.MASTERY_NEW, "correct_streak": 0,
            "interval_days": 0, "next_review_at": "", "review_count": 0,
            "marked_at": "", "updated_at": "",
        }

    def ensure_progress(self, item_id) -> dict:
        """确保有进度行（**幂等**）。学到 / 标记时才建，这就是「懒创建」。

        **只建一行，不写假流水**：「标记已学」不是一次复习。往 ``memory_reviews``
        里塞一条凑数，会让正确率曲线凭空多出一次作答，把这个指标变成噪声。
        """
        iid = int(item_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_progress WHERE item_id = ?",
                               (iid,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO memory_progress (item_id, mastery, correct_streak, "
                    "interval_days, next_review_at, review_count, marked_at, updated_at) "
                    "VALUES (?, ?, 0, 0, '', 0, ?, ?)",
                    (iid, tc.MASTERY_NEW, _now(), _now()))
        return self.get_progress(iid)

    def set_mastery(self, item_id, mastery, *, today=None) -> dict:
        """手动标掌握度（列表里的「标记」下拉）。

        标成「生疏」及以上时，把首次复习**排到今天**：标完立刻能在「今日训练」里
        再过一遍，才符合直觉 —— 我标了「生疏」，就该尽快再看一次。
        （与 ``excel_db.set_mastery`` 同一口径。）
        """
        iid = int(item_id)
        value = max(tc.MASTERY_NEW, min(tc.MASTERY_GOOD, int(mastery)))
        anchor = tc.parse_date(today) or date.today()
        current = self.get_progress(iid)
        interval = int(current.get("interval_days") or 0)
        next_at = str(current.get("next_review_at") or "")
        if value >= tc.MASTERY_WEAK and not next_at:
            interval = interval or 1
            next_at = anchor.isoformat()
        elif value <= tc.MASTERY_NEW:
            interval = 0
            next_at = ""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_progress (item_id, mastery, correct_streak,
                    interval_days, next_review_at, review_count, marked_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    mastery = excluded.mastery,
                    interval_days = excluded.interval_days,
                    next_review_at = excluded.next_review_at,
                    updated_at = excluded.updated_at
                """,
                (iid, value, int(current.get("correct_streak") or 0), interval,
                 next_at, _now(), _now()))
        return self.get_progress(iid)

    def record_review(self, item_id, feedback, *, today=None) -> dict:
        """记一次复习：写流水 + 推进 SRS 状态。**一次调用只写一行流水。**"""
        iid = int(item_id)
        anchor = tc.parse_date(today) or date.today()
        current = self.get_progress(iid)
        state = tc.review_next_state(
            current.get("mastery", tc.MASTERY_NEW),
            current.get("correct_streak", 0),
            current.get("interval_days", 0),
            feedback)
        next_at = (anchor + timedelta(days=int(state["interval_days"]))).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_progress (item_id, mastery, correct_streak,
                    interval_days, next_review_at, review_count, marked_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    mastery = excluded.mastery,
                    correct_streak = excluded.correct_streak,
                    interval_days = excluded.interval_days,
                    next_review_at = excluded.next_review_at,
                    review_count = memory_progress.review_count + 1,
                    updated_at = excluded.updated_at
                """,
                (iid, int(state["mastery"]), int(state["correct_streak"]),
                 int(state["interval_days"]), next_at, _now(), _now()))
            conn.execute(
                "INSERT INTO memory_reviews (item_id, review_date, feedback, "
                "mastery_after, created_at) VALUES (?, ?, ?, ?, ?)",
                (iid, anchor.isoformat(), str(feedback), int(state["mastery"]), _now()))
        return {
            "item_id": iid, "feedback": str(feedback),
            "mastery": int(state["mastery"]),
            "correct_streak": int(state["correct_streak"]),
            "interval_days": int(state["interval_days"]),
            "next_review_at": next_at,
        }

    def list_reviews(self, *, item_id=None, since=None, until=None,
                     limit=None) -> list[dict]:
        sql = "SELECT * FROM memory_reviews WHERE 1 = 1"
        params: list = []
        if item_id is not None:
            sql += " AND item_id = ?"
            params.append(int(item_id))
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
        """掌握度分布。**以「全部记忆项」为分母** —— 没学过的也要算进「未学」那一档。"""
        dist = {tc.MASTERY_NEW: 0, tc.MASTERY_WEAK: 0, tc.MASTERY_FAIR: 0,
                tc.MASTERY_GOOD: 0}
        for item in self.list_items():
            level = int(item["mastery"] or 0)
            dist[level] = dist.get(level, 0) + 1
        return dist

    # ==================================================================
    # 打卡
    # ==================================================================
    def checkin(self, check_date=None, *, minutes=None, items_new=None,
                items_reviewed=None, accuracy=None, note=None) -> dict:
        """打卡。**同一天重复调用是更新**，不是新增一行。

        传 ``None`` 的字段 = 不改动（用户补一句备注，不该把分钟数清零）。
        """
        day = (tc.parse_date(check_date) or date.today()).isoformat()
        current = self.get_checkin(day) or {
            "check_date": day, "minutes": 0, "items_new": 0,
            "items_reviewed": 0, "accuracy": 0.0, "note": "",
        }
        merged = dict(current)
        if minutes is not None:
            merged["minutes"] = int(minutes or 0)
        if items_new is not None:
            merged["items_new"] = int(items_new or 0)
        if items_reviewed is not None:
            merged["items_reviewed"] = int(items_reviewed or 0)
        if accuracy is not None:
            merged["accuracy"] = float(accuracy or 0.0)
        if note is not None:
            merged["note"] = str(note or "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_checkins (check_date, minutes, items_new,
                    items_reviewed, accuracy, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(check_date) DO UPDATE SET
                    minutes = excluded.minutes,
                    items_new = excluded.items_new,
                    items_reviewed = excluded.items_reviewed,
                    accuracy = excluded.accuracy,
                    note = excluded.note
                """,
                (day, merged["minutes"], merged["items_new"], merged["items_reviewed"],
                 merged["accuracy"], merged["note"], _now()))
        return self.get_checkin(day)

    def get_checkin(self, check_date=None) -> dict | None:
        day = (tc.parse_date(check_date) or date.today()).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_checkins WHERE check_date = ?",
                               (day,)).fetchone()
        return dict(row) if row else None

    def list_checkins(self, *, start=None, end=None) -> list[dict]:
        sql = "SELECT * FROM memory_checkins WHERE 1 = 1"
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
    # 题库 → 记忆项
    # ==================================================================
    def import_bank(self, bank_code, palace_id=0, *, category=None) -> dict:
        """把一个题库灌成记忆项。**幂等**：同一题只导一次（靠 ``source_key``）。

        宫殿里有桩就**按顺序自动挂上去**（第 1 题挂第 1 桩），这样导完立刻能走一遍。
        桩不够就多出来的挂到最后一个桩上；一个桩都没有就落在「未归档」。
        """
        bank = self.get_bank_by_code(bank_code)
        if bank is None:
            raise KeyError(f"没有这个题库：{bank_code}")
        bank_id = int(bank["id"])
        items = self.list_bank_items(bank_id)
        loci = self.list_loci(palace_id) if palace_id else []
        label = category or str(bank["name"])

        created = 0
        skipped = 0
        for index, entry in enumerate(items):
            source_key = f"bank:{bank_code}:{int(entry['seq'])}"
            with self._connect() as conn:
                exists = conn.execute(
                    "SELECT id FROM memory_items WHERE source_key = ?",
                    (source_key,)).fetchone()
            if exists:
                skipped += 1
                continue
            if loci:
                locus_id = int(loci[min(index, len(loci) - 1)]["id"])
            else:
                locus_id = 0
            self.add_item(
                front=str(entry["question"]), back=str(entry["answer"]),
                palace_id=int(palace_id or 0), locus_id=locus_id,
                imagery=str(entry.get("hint", "")), category=label,
                detail=str(entry.get("detail", "") or ""),
                images=str(entry.get("images", "") or ""),
                source_key=source_key)
            created += 1
        return {"created": created, "skipped": skipped, "total": len(items)}

    # ==================================================================
    # 教学卡
    # ==================================================================
    def list_cards(self) -> list[dict]:
        return [dict(card) for card in memory_seed.TEACHING_CARDS]

    def get_card(self, code) -> dict | None:
        for card in memory_seed.TEACHING_CARDS:
            if card["code"] == str(code):
                return dict(card)
        return None

    def card_categories(self) -> list[str]:
        seen: list[str] = []
        for card in memory_seed.TEACHING_CARDS:
            if card["category"] not in seen:
                seen.append(card["category"])
        return seen

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
        return {
            "days": summary["days"],
            "minutes": summary["minutes"],
            "items_new": summary["items_new"],
            "items_reviewed": summary["items_reviewed"],
            "avg_minutes": summary["avg_minutes"],
            "streak": tc.streak_from_dates(dates, anchor),
            "best_streak": tc.best_streak_from_dates(dates),
            "accuracy": accuracy["accuracy"],
            "reviewed": accuracy["reviewed"],
            "correct": accuracy["correct"],
            "mastery": self.mastery_distribution(),
            "palaces": len(self.list_palaces()),
            "items": self.count_items(),
            "due": self.due_count(today=anchor),
        }

    def new_today(self, *, today=None) -> int:
        """今天**新标记**了几条（看 ``marked_at`` 的前 10 个字符就是日期）。

        为什么不用「掌握度 == 未学」来数：那会把历史上所有没学完的都算进来，
        跟「今天新学」根本不是一回事。
        """
        day = (tc.parse_date(today) or date.today()).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM memory_progress WHERE substr(marked_at, 1, 10) = ?",
                (day,)).fetchone()
        return int(row["n"] if row else 0)

    def autofill_today(self, *, today=None) -> dict:
        """按今天的实际流水，把打卡数字补全（分钟数留给用户填）。

        这样用户点「打卡」时不用自己数「今天复习了几个」——
        程序比他清楚。``minutes`` 保持原值（只有用户知道练了多久）。
        """
        anchor = (tc.parse_date(today) or date.today()).isoformat()
        rows = self.list_reviews(since=anchor, until=anchor)
        reviewed = len(rows)
        correct = sum(1 for r in rows if r["feedback"] == tc.FEEDBACK_KNOWN)
        return self.checkin(
            anchor, items_reviewed=reviewed, items_new=self.new_today(today=anchor),
            accuracy=tc.accuracy(reviewed, correct))


# ======================================================================
# 小工具（界面用；放这里是因为它只依赖本模块的数据形状）
# ======================================================================
def suggest_new_count(*, due_total, target_new=None) -> int:
    """今天建议新学几条：由「待复习量」反向决定 —— 复习多就少学新的。"""
    limit = int(target_new or tc.SUGGEST_NEW_PER_DAY)
    if int(due_total or 0) >= 40:
        return max(1, limit // 4)
    if int(due_total or 0) >= 20:
        return max(2, limit // 2)
    return limit


_TAG_SPLIT = re.compile(r"[|,、;；\s]+")


def split_tags(text) -> list[str]:
    """标签串 → 列表（``|`` ``,`` ``、`` ``;`` 与空白都算分隔）。"""
    return [t for t in _TAG_SPLIT.split(str(text or "")) if t]


def format_item_line(item: dict) -> str:
    """记忆项的一行摘要（列表与结算卡共用，避免两处各写一份）。"""
    front = str(item.get("front", "") or "").strip()
    back = str(item.get("back", "") or "").strip()
    return f"{front} → {back}" if back else front
