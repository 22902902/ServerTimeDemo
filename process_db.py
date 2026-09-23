# -*- coding: utf-8 -*-
"""
================================================================================
流程中心 - 数据层（Data Layer）
================================================================================
把「流程 / 步骤」的存取从 ``main.py`` 里拆出来，与 ``todo_db`` / ``tools_db``
的分层约定对齐。节点类型：

    process_flows        流程（标题/分类/平台/入口链接/变量/备注）
    process_steps        步骤（类型/前置检查/说明/命令/预期结果/截图/备注）
    process_runs         一次「照着做」的执行记录（含变量快照）
    process_run_steps    执行时每个步骤的勾选状态

设计取舍
--------------------------------------------------------------------------------
* **加列迁移，不动存量** —— 新字段一律 ``ALTER TABLE ... ADD COLUMN ... DEFAULT``，
  与 ``tools_db.init_all_tool_tables`` 同一套路。老库缺列时只是「没有这个信息」，
  不会崩；已有 18 个步骤的数据零风险。
* **``screenshot_path`` 沿用 JSON 存法** —— ``parse_account_image_items`` 已同时
  兼容「单路径字符串」与「JSON 数组」，历史数据两种形态都出现过（实测 7/18 是多图），
  不动它。
* **变量是「流程级」的** —— ``{{域名}}`` 这类占位符的值由流程统一持有，一条流程
  因此能服务多个域名 / 多台机器 / 多个环境，这是「避免重复劳动」的关键。
* **危险命令识别放在数据层** —— 它是领域判断（哪些命令会造成不可逆后果），
  不是渲染细节；界面层只负责把结果画成红色徽章。
* **不删 ``required_text`` / ``optional_text``** —— 它们是备案场景的存量字段，
  实测填充率仅 11% / 5%，界面上降级到「更多字段」，但数据保留。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

# ---------------------------------------------------------------------------
# 步骤类型
# ---------------------------------------------------------------------------
STEP_KIND_OP = "op"          # 操作型：点哪里、填什么（默认）
STEP_KIND_CMD = "cmd"        # 命令型：可复制执行的命令
STEP_KIND_CHECK = "check"    # 校验型：判断上一步结果对不对
STEP_KIND_NOTE = "note"      # 备注型：纯说明，不需要动作

STEP_KIND_LABELS = {
    STEP_KIND_OP: "操作型",
    STEP_KIND_CMD: "命令型",
    STEP_KIND_CHECK: "校验型",
    STEP_KIND_NOTE: "备注型",
}
STEP_KIND_ORDER = [STEP_KIND_OP, STEP_KIND_CMD, STEP_KIND_CHECK, STEP_KIND_NOTE]
STEP_KIND_CHOICES = [STEP_KIND_LABELS[k] for k in STEP_KIND_ORDER]

COMMAND_LANGS = ["shell", "powershell", "bat", "sql", "yaml", "ini", "conf", "text"]

RUN_STATUS_RUNNING = "running"
RUN_STATUS_DONE = "done"
RUN_STATUS_ABORTED = "aborted"


def label_to_step_kind(label: str) -> str:
    """把界面上的中文类型名翻译回内部 kind（认不出就当操作型）。"""
    text = (label or "").strip()
    for key, value in STEP_KIND_LABELS.items():
        if value == text:
            return key
    return text if text in STEP_KIND_LABELS else STEP_KIND_OP


def step_kind_label(kind: str) -> str:
    return STEP_KIND_LABELS.get((kind or "").strip(), STEP_KIND_LABELS[STEP_KIND_OP])


# ---------------------------------------------------------------------------
# 危险命令识别
# ---------------------------------------------------------------------------
# 判据是「可能造成不可逆后果」，不是「看着吓人」。命中后界面标红并二次确认，
# 但**不阻断** —— 运维本来就要用这些命令，提示的目的是让人停半秒。
DANGER_PATTERNS = (
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r", "递归强制删除"),
    (r"\bmkfs(\.\w+)?\b", "格式化文件系统"),
    (r"\bdd\s+[^\n]*\bof=/dev/", "裸写设备"),
    (r">\s*/dev/sd[a-z]", "覆盖磁盘设备"),
    (r"\bgit\s+reset\s+--hard\b", "丢弃工作区改动"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*[fd]", "删除未跟踪文件"),
    (r"\bgit\s+push\b[^\n]*(\s--force\b|\s-f\b)", "强制推送远端"),
    (r"\bdrop\s+(table|database|schema)\b", "删除数据库对象"),
    (r"\btruncate\s+table\b", "清空数据表"),
    (r"\bdelete\s+from\b(?![\s\S]*\bwhere\b)", "无条件的 DELETE"),
    (r"\bchmod\s+(-R\s+)?777\b", "放开全部权限"),
    (r"\b(shutdown|reboot|halt|poweroff)\b|\binit\s+0\b", "关机 / 重启"),
    (r"\bkill\s+-9\b", "强制杀进程"),
    (r"\bsystemctl\s+(stop|disable|mask)\b", "停止系统服务"),
    (r":\(\)\s*\{[^}]*\}\s*;\s*:", "fork 炸弹"),
    (r"\bDROP\s+(TABLE|DATABASE)\b", "删除数据库对象"),
)
_DANGER_COMPILED = tuple(
    (re.compile(pattern, re.IGNORECASE), reason) for pattern, reason in DANGER_PATTERNS
)


def danger_reasons(*texts) -> list[str]:
    """返回命中的危险原因（去重、保序）。空列表 = 没命中。"""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for regex, reason in _DANGER_COMPILED:
            if reason not in found and regex.search(str(text)):
                found.append(reason)
    return found


def is_dangerous_command(*texts) -> bool:
    return bool(danger_reasons(*texts))


# ---------------------------------------------------------------------------
# 变量（{{键}} 占位符）
# ---------------------------------------------------------------------------
VAR_PATTERN = re.compile(r"\{\{\s*([^{}\n]+?)\s*\}\}")


def parse_variables(raw) -> list[dict]:
    """把存库的 JSON（或已是 list）解析成变量定义列表。

    单项结构： ``{"key": "域名", "label": "域名", "default": "example.com", "hint": "..."}``
    解析不了就返回空列表 —— 坏数据不该把整个流程页拦下来。
    """
    if isinstance(raw, list):
        items = raw
    else:
        text = (raw or "").strip()
        if not text:
            return []
        try:
            items = json.loads(text)
        except (ValueError, TypeError):
            return []
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "") or "").strip()
        if not key:
            continue
        out.append(
            {
                "key": key,
                "label": str(item.get("label", "") or "").strip() or key,
                "default": str(item.get("default", "") or ""),
                "hint": str(item.get("hint", "") or "").strip(),
            }
        )
    return out


def serialize_variables(items) -> str:
    """变量定义列表 → JSON 字符串（存库用）。"""
    clean: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "") or "").strip()
        if not key:
            continue
        clean.append(
            {
                "key": key,
                "label": str(item.get("label", "") or "").strip() or key,
                "default": str(item.get("default", "") or ""),
                "hint": str(item.get("hint", "") or "").strip(),
            }
        )
    return json.dumps(clean, ensure_ascii=False) if clean else ""


def default_variable_values(items) -> dict[str, str]:
    return {item["key"]: item.get("default", "") for item in parse_variables(items)}


def extract_variable_keys(*texts) -> list[str]:
    """从若干段文本里抽出用到的变量名（去重、按首次出现排序）。

    用途：改了命令块之后，提示「这条命令引用了尚未定义的变量」。
    """
    seen: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in VAR_PATTERN.finditer(str(text)):
            key = match.group(1).strip()
            if key and key not in seen:
                seen.append(key)
    return seen


def render_template(text, values) -> str:
    """把 ``{{键}}`` 换成值。

    **未定义或值为空的占位符保持原样**（不替换成空串）—— 让人一眼看见
    「这里还没填」，比悄悄留个空洞安全得多。
    """
    if not text:
        return ""
    table = values or {}

    def _sub(match: re.Match) -> str:
        key = match.group(1).strip()
        if key in table and str(table[key]).strip():
            return str(table[key])
        return match.group(0)

    return VAR_PATTERN.sub(_sub, str(text))


def build_run_script(flow_title: str, steps, values, *, env: str = "") -> str:
    """把流程里所有命令块按序号拼成一段可直接粘贴的 shell 脚本。

    ``steps`` 可以是 sqlite3.Row 或 dict（取 ``step_no`` / ``title`` /
    ``command_text`` / ``precheck_text``）。没有命令的步骤自动跳过 ——
    输出的是「照敲」用的脚本，不是流程全文。
    """
    def _get(item, key, default=""):
        try:
            return item[key]
        except (KeyError, IndexError, TypeError):
            return default

    lines = ["#!/usr/bin/env bash", f"# {flow_title}" + (f"  [环境: {env}]" if env else "")]
    if values:
        pairs = "  ".join(f"{k}={v}" for k, v in values.items() if str(v).strip())
        if pairs:
            lines.append(f"# 变量：{pairs}")
    lines.append("# 由「流程中心」生成，执行前请逐条确认")
    lines.append("set -e")
    lines.append("")

    emitted = 0
    for step in steps or []:
        command = str(_get(step, "command_text", "") or "").strip()
        if not command:
            continue
        emitted += 1
        no = _get(step, "step_no", "")
        title = str(_get(step, "title", "") or "").strip()
        precheck = str(_get(step, "precheck_text", "") or "").strip()
        lines.append(f"# ── [{no}] {title}")
        if precheck:
            lines.append(f"# 前置检查：{render_template(precheck, values)}")
        for row in render_template(command, values).splitlines():
            lines.append(row)
        lines.append("")
    if not emitted:
        return ""
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 建表与加列迁移
# ---------------------------------------------------------------------------
PROCESS_FLOWS_TABLE = """
    CREATE TABLE IF NOT EXISTS process_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT,
        platform TEXT,
        link_url TEXT,
        note TEXT,
        variables TEXT DEFAULT '',
        envs TEXT DEFAULT '',
        favorite INTEGER DEFAULT 0,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

PROCESS_STEPS_TABLE = """
    CREATE TABLE IF NOT EXISTS process_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flow_id INTEGER NOT NULL,
        step_no INTEGER NOT NULL,
        title TEXT NOT NULL,
        link_url TEXT,
        screenshot_path TEXT,
        description_text TEXT,
        required_text TEXT,
        optional_text TEXT,
        note TEXT,
        kind TEXT DEFAULT 'op',
        command_text TEXT DEFAULT '',
        command_lang TEXT DEFAULT 'shell',
        precheck_text TEXT DEFAULT '',
        expected_text TEXT DEFAULT '',
        danger INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (flow_id) REFERENCES process_flows(id) ON DELETE CASCADE
    )
"""

PROCESS_RUNS_TABLE = """
    CREATE TABLE IF NOT EXISTS process_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flow_id INTEGER NOT NULL,
        title TEXT DEFAULT '',
        env TEXT DEFAULT '',
        variables_json TEXT DEFAULT '',
        started_at TEXT NOT NULL,
        finished_at TEXT DEFAULT '',
        status TEXT DEFAULT 'running',
        FOREIGN KEY (flow_id) REFERENCES process_flows(id) ON DELETE CASCADE
    )
"""

PROCESS_RUN_STEPS_TABLE = """
    CREATE TABLE IF NOT EXISTS process_run_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        step_id INTEGER NOT NULL,
        step_no INTEGER NOT NULL,
        done INTEGER DEFAULT 0,
        done_at TEXT DEFAULT '',
        FOREIGN KEY (run_id) REFERENCES process_runs(id) ON DELETE CASCADE
    )
"""

# (列名, DDL) —— 全部带 DEFAULT，老库补列后行为与「没填过」一致
STEP_COLUMN_MIGRATIONS = (
    ("kind", "TEXT DEFAULT 'op'"),
    ("command_text", "TEXT DEFAULT ''"),
    ("command_lang", "TEXT DEFAULT 'shell'"),
    ("precheck_text", "TEXT DEFAULT ''"),
    ("expected_text", "TEXT DEFAULT ''"),
    ("danger", "INTEGER DEFAULT 0"),
)

FLOW_COLUMN_MIGRATIONS = (
    ("variables", "TEXT DEFAULT ''"),
    ("envs", "TEXT DEFAULT ''"),
    ("favorite", "INTEGER DEFAULT 0"),
    ("sort_order", "INTEGER DEFAULT 0"),
)


def _add_missing_columns(conn: sqlite3.Connection, table: str, migrations) -> list[str]:
    """按 PRAGMA table_info 比对后逐列 ALTER TABLE；返回实际补上的列名。

    异常全吞：老库可能因为各种历史原因缺列，补不上也不该拦住程序启动
    （与 ``tools_db`` 的处理一致）。
    """
    try:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.DatabaseError:
        return []
    added: list[str] = []
    for column, ddl in migrations:
        if column in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()
            added.append(column)
        except sqlite3.DatabaseError:
            pass
    return added


def init_process_tables(conn: sqlite3.Connection) -> list[str]:
    """建流程中心的四张表 + 给老库补齐新列。返回补上的列名（便于自检）。

    建表顺序有讲究：``process_steps`` 有指向 ``process_flows`` 的外键，
    父表必须在前 —— 反过来的话 SQLite 建表当时不报错，但级联删除会失效。
    """
    conn.execute(PROCESS_FLOWS_TABLE)
    conn.execute(PROCESS_STEPS_TABLE)
    conn.execute(PROCESS_RUNS_TABLE)
    conn.execute(PROCESS_RUN_STEPS_TABLE)
    conn.commit()
    added = _add_missing_columns(conn, "process_steps", STEP_COLUMN_MIGRATIONS)
    added += _add_missing_columns(conn, "process_flows", FLOW_COLUMN_MIGRATIONS)
    return added


# ---------------------------------------------------------------------------
# 数据访问（混入 Database）
# ---------------------------------------------------------------------------
def _norm(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ProcessDBMixin:
    """流程中心的数据访问层，混入 ``main.Database``。

    只依赖宿主提供的 ``self.conn``。所有写操作后立即 commit（与全局约定一致）。
    """

    # ── 流程 ────────────────────────────────────────────────────────────
    def fetch_process_flows(self, keyword: str = "") -> list[sqlite3.Row]:
        """取流程列表；有关键词时**同时命中流程字段与步骤内容**。

        步骤侧用 EXISTS 子查询而不是 JOIN：一个流程可能多个步骤命中，
        JOIN 会把同一流程返回多行，界面就得去重。EXISTS 天然只回一行。
        """
        if keyword:
            like = f"%{_norm(keyword)}%"
            return self.conn.execute(
                """
                SELECT *
                FROM process_flows
                WHERE title LIKE ?
                   OR category LIKE ?
                   OR platform LIKE ?
                   OR link_url LIKE ?
                   OR note LIKE ?
                   OR EXISTS (
                        SELECT 1 FROM process_steps s
                        WHERE s.flow_id = process_flows.id
                          AND (s.title LIKE ? OR s.description_text LIKE ?
                               OR s.command_text LIKE ? OR s.precheck_text LIKE ?
                               OR s.expected_text LIKE ? OR s.note LIKE ?
                               OR s.required_text LIKE ? OR s.optional_text LIKE ?)
                   )
                ORDER BY favorite DESC, updated_at DESC, id DESC
                """,
                (like,) * 13,
            ).fetchall()
        return self.conn.execute(
            """
            SELECT *
            FROM process_flows
            ORDER BY favorite DESC, updated_at DESC, id DESC
            """
        ).fetchall()

    def fetch_matching_step_ids(self, keyword: str) -> set[int]:
        """搜索关键词命中的步骤 id 集合（用于列表里标出「是这一步命中」）。"""
        text = _norm(keyword)
        if not text:
            return set()
        like = f"%{text}%"
        rows = self.conn.execute(
            """
            SELECT id FROM process_steps
            WHERE title LIKE ? OR description_text LIKE ? OR command_text LIKE ?
               OR precheck_text LIKE ? OR expected_text LIKE ? OR note LIKE ?
               OR required_text LIKE ? OR optional_text LIKE ?
            """,
            (like,) * 8,
        ).fetchall()
        return {int(row["id"]) for row in rows}

    def get_process_flow(self, flow_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM process_flows WHERE id = ?", (flow_id,)).fetchone()

    def add_process_flow(self, payload: dict) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """
            INSERT INTO process_flows (
                title, category, platform, link_url, note,
                variables, envs, favorite, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("title", ""),
                payload.get("category", ""),
                payload.get("platform", ""),
                payload.get("link_url", ""),
                payload.get("note", ""),
                serialize_variables(payload.get("variables")),
                payload.get("envs", ""),
                _as_int(payload.get("favorite"), 0),
                _as_int(payload.get("sort_order"), 0),
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_process_flow(self, flow_id: int, payload: dict, *, partial: bool = False):
        """更新流程。

        ``partial=True`` 时只写 payload 里出现的键 —— 勾选收藏、改变量这类
        单点操作不必回填整行（否则界面没传的字段会被清空）。
        """
        now = datetime.now().isoformat(timespec="seconds")
        sets: list[str] = []
        params: list = []
        # 基础列同样受 partial 约束：只写 payload 里出现过的键，
        # 否则「只改备注」会把标题一起清空。
        for col in ("title", "category", "platform", "link_url", "note"):
            if col in payload or not partial:
                sets.append(f"{col} = ?")
                params.append(payload.get(col, ""))

        if "variables" in payload or not partial:
            sets.append("variables = ?")
            params.append(serialize_variables(payload.get("variables")))
        for col in ("envs",):
            if col in payload or not partial:
                sets.append(f"{col} = ?")
                params.append(payload.get(col, ""))
        for col in ("favorite", "sort_order"):
            if col in payload or not partial:
                sets.append(f"{col} = ?")
                params.append(_as_int(payload.get(col), 0))

        sets.append("updated_at = ?")
        params.append(now)
        params.append(flow_id)
        self.conn.execute(
            f"UPDATE process_flows SET {', '.join(sets)} WHERE id = ?", tuple(params)
        )
        self.conn.commit()

    def set_process_flow_favorite(self, flow_id: int, favorite: bool):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE process_flows SET favorite = ?, updated_at = ? WHERE id = ?",
            (1 if favorite else 0, now, flow_id),
        )
        self.conn.commit()

    def set_process_flow_variables(self, flow_id: int, items) -> str:
        """只改变量定义，返回落库后的 JSON。"""
        raw = serialize_variables(items)
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE process_flows SET variables = ?, updated_at = ? WHERE id = ?",
            (raw, now, flow_id),
        )
        self.conn.commit()
        return raw

    def delete_process_flow(self, flow_id: int):
        self.conn.execute("DELETE FROM process_flows WHERE id = ?", (flow_id,))
        self.conn.commit()

    def fetch_process_flows_by_title(self, title: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM process_flows WHERE title = ?", (_norm(title),)
        ).fetchall()

    # ── 步骤 ────────────────────────────────────────────────────────────
    def fetch_process_steps(self, flow_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM process_steps
            WHERE flow_id = ?
            ORDER BY step_no ASC, id ASC
            """,
            (flow_id,),
        ).fetchall()

    def fetch_all_process_steps(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM process_steps
            ORDER BY flow_id ASC, step_no ASC, id ASC
            """
        ).fetchall()

    def get_process_step(self, step_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM process_steps WHERE id = ?", (step_id,)).fetchone()

    def get_next_process_step_no(self, flow_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(step_no), 0) AS max_no FROM process_steps WHERE flow_id = ?",
            (flow_id,),
        ).fetchone()
        return int(row["max_no"] or 0) + 1

    def add_process_step(self, flow_id: int, payload: dict) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        danger = _as_int(payload.get("danger"), 0)
        if not danger and is_dangerous_command(payload.get("command_text")):
            danger = 1
        cursor = self.conn.execute(
            """
            INSERT INTO process_steps (
                flow_id, step_no, title, link_url, screenshot_path, description_text,
                required_text, optional_text, note, kind, command_text, command_lang,
                precheck_text, expected_text, danger, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                flow_id,
                _as_int(payload.get("step_no"), 1) or 1,
                payload.get("title", ""),
                payload.get("link_url", ""),
                payload.get("screenshot_path", ""),
                payload.get("description_text", ""),
                payload.get("required_text", ""),
                payload.get("optional_text", ""),
                payload.get("note", ""),
                payload.get("kind", STEP_KIND_OP) or STEP_KIND_OP,
                payload.get("command_text", ""),
                payload.get("command_lang", "shell") or "shell",
                payload.get("precheck_text", ""),
                payload.get("expected_text", ""),
                danger,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_process_step(self, step_id: int, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        danger = _as_int(payload.get("danger"), 0)
        if not danger and is_dangerous_command(payload.get("command_text")):
            danger = 1
        self.conn.execute(
            """
            UPDATE process_steps
            SET step_no = ?, title = ?, link_url = ?, screenshot_path = ?, description_text = ?,
                required_text = ?, optional_text = ?, note = ?, kind = ?, command_text = ?,
                command_lang = ?, precheck_text = ?, expected_text = ?, danger = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                _as_int(payload.get("step_no"), 1) or 1,
                payload.get("title", ""),
                payload.get("link_url", ""),
                payload.get("screenshot_path", ""),
                payload.get("description_text", ""),
                payload.get("required_text", ""),
                payload.get("optional_text", ""),
                payload.get("note", ""),
                payload.get("kind", STEP_KIND_OP) or STEP_KIND_OP,
                payload.get("command_text", ""),
                payload.get("command_lang", "shell") or "shell",
                payload.get("precheck_text", ""),
                payload.get("expected_text", ""),
                danger,
                now,
                step_id,
            ),
        )
        self.conn.commit()

    def update_process_step_screenshot(self, step_id: int, screenshot_path: str):
        """只改截图列（贴图 / 移除单图时用，避免整行回填）。"""
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE process_steps SET screenshot_path = ?, updated_at = ? WHERE id = ?",
            (screenshot_path, now, step_id),
        )
        self.conn.commit()

    def update_process_step_title(self, step_id: int, title: str):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE process_steps SET title = ?, updated_at = ? WHERE id = ?",
            (_norm(title), now, step_id),
        )
        self.conn.commit()

    def delete_process_step(self, step_id: int):
        self.conn.execute("DELETE FROM process_steps WHERE id = ?", (step_id,))
        self.conn.commit()

    def move_process_step(self, step_id: int, direction: int) -> bool:
        """和相邻步骤交换 step_no（``direction`` = -1 上移 / +1 下移）。

        返回是否真的动了。首尾处返回 False，界面据此不刷新。
        """
        row = self.get_process_step(step_id)
        if not row:
            return False
        steps = self.fetch_process_steps(int(row["flow_id"]))
        ids = [int(item["id"]) for item in steps]
        try:
            index = ids.index(int(step_id))
        except ValueError:
            return False
        target = index + (1 if direction > 0 else -1)
        if target < 0 or target >= len(steps):
            return False
        other = steps[target]
        now = datetime.now().isoformat(timespec="seconds")
        # 先挪到临时号，避免 step_no 撞车（没有唯一约束，但要保证顺序稳定）
        self.conn.execute(
            "UPDATE process_steps SET step_no = ?, updated_at = ? WHERE id = ?",
            (-1, now, int(step_id)),
        )
        self.conn.execute(
            "UPDATE process_steps SET step_no = ?, updated_at = ? WHERE id = ?",
            (_as_int(row["step_no"], index + 1), now, int(other["id"])),
        )
        self.conn.execute(
            "UPDATE process_steps SET step_no = ?, updated_at = ? WHERE id = ?",
            (_as_int(other["step_no"], target + 1), now, int(step_id)),
        )
        self.conn.commit()
        return True

    def renumber_process_steps(self, flow_id: int):
        """把某流程的 step_no 重排成 1..N（删除步骤后消除空号）。"""
        steps = self.fetch_process_steps(flow_id)
        now = datetime.now().isoformat(timespec="seconds")
        changed = False
        for index, row in enumerate(steps, start=1):
            if _as_int(row["step_no"], index) != index:
                self.conn.execute(
                    "UPDATE process_steps SET step_no = ?, updated_at = ? WHERE id = ?",
                    (index, now, int(row["id"])),
                )
                changed = True
        if changed:
            self.conn.commit()

    # ── 执行留痕 ────────────────────────────────────────────────────────
    def start_process_run(self, flow_id: int, *, title: str = "", env: str = "",
                          variables: dict | None = None,
                          step_ids: list[int] | None = None) -> int:
        """开一次执行：落一条 run + 为每个步骤建一行（未勾选）。"""
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """
            INSERT INTO process_runs (flow_id, title, env, variables_json, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                flow_id,
                title,
                env,
                json.dumps(variables or {}, ensure_ascii=False),
                now,
                RUN_STATUS_RUNNING,
            ),
        )
        run_id = int(cursor.lastrowid)
        if step_ids is None:
            rows = self.fetch_process_steps(flow_id)
            step_ids = [int(row["id"]) for row in rows]
            step_nos = [int(row["step_no"]) for row in rows]
        else:
            step_nos = list(range(1, len(step_ids) + 1))
        for step_id, step_no in zip(step_ids, step_nos):
            self.conn.execute(
                """
                INSERT INTO process_run_steps (run_id, step_id, step_no, done, done_at)
                VALUES (?, ?, ?, 0, '')
                """,
                (run_id, step_id, step_no),
            )
        self.conn.commit()
        return run_id

    def get_process_run(self, run_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM process_runs WHERE id = ?", (run_id,)
        ).fetchone()

    def get_active_process_run(self, flow_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT * FROM process_runs
            WHERE flow_id = ? AND status = ?
            ORDER BY id DESC LIMIT 1
            """,
            (flow_id, RUN_STATUS_RUNNING),
        ).fetchone()

    def fetch_process_run_steps(self, run_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM process_run_steps
            WHERE run_id = ?
            ORDER BY step_no ASC, id ASC
            """,
            (run_id,),
        ).fetchall()

    def set_process_run_step_done(self, run_id: int, step_id: int, done: bool):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            UPDATE process_run_steps
            SET done = ?, done_at = ?
            WHERE run_id = ? AND step_id = ?
            """,
            (1 if done else 0, now if done else "", run_id, step_id),
        )
        self.conn.commit()

    def finish_process_run(self, run_id: int, status: str = RUN_STATUS_DONE):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE process_runs SET status = ?, finished_at = ? WHERE id = ?",
            (status, now, run_id),
        )
        self.conn.commit()

    def fetch_recent_process_runs(self, flow_id: int, limit: int = 10) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM process_runs
            WHERE flow_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (flow_id, int(limit)),
        ).fetchall()

    def count_process_run_done(self, run_id: int) -> tuple[int, int]:
        """返回 ``(已完成数, 总步骤数)``。"""
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done
            FROM process_run_steps WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        return int(row["done"] or 0), int(row["total"] or 0)

    def delete_process_run(self, run_id: int):
        self.conn.execute("DELETE FROM process_runs WHERE id = ?", (run_id,))
        self.conn.commit()
