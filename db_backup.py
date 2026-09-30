# -*- coding: utf-8 -*-
"""
================================================================================
数据库「上一条」快照（db_backup）
================================================================================
给主库（``expiry_manager.db``）加一层「写之前先留一份」的保护：每次**真正要写**
之前，把当前库整份拷进同级的 ``_backup/``，出事就退回去。

为什么不是「定期备份」
--------------------------------------------------------------------------------
诉求是「永远可以回滚上一条」—— 那就不该等定时器，而应该卡在**写的边界**上：
没有写就没有新版本，也就不需要新快照。所以判据是「这条 SQL 是不是写语句」，
而不是「距上次多久」。

为什么用 ``set_trace_callback`` 而不是重写 ``commit()``
--------------------------------------------------------------------------------
``commit()`` 里拍不到「写之前」的状态：

* rollback journal 模式下，未提交的脏页**可能已经落到主文件**，此时拷文件会
  拷到半改状态（拷出来的库打不开或数据错乱）；
* 更现实的场景：本程序对同一个库开着**多个连接**（``Database`` /
  ``StudyNotesDB`` / ``QAWorkLogDBExt`` / ``TodoDB`` / ``ExcelDB``）。
  A 在写、B 的回调在旁边拷文件，拷到的可能是「A 提交到一半」的混合态 ——
  概率低，但一旦发生，回滚过去的库就是坏的，而这正是本模块要防的事。

挂在 trace 回调上就避开了「太晚」这一层 —— 回调在**语句执行之前**触发，
那一刻库里只有上一个已提交的状态。

**取快照用在线备份 API，失败才退回拷文件。** ``Connection.backup()`` 是
事务一致的（``build/probe_backup_in_trace.py`` 实测过：**在 trace 回调这个
位置可以用**，不会被隐式 ``BEGIN`` 锁住 —— 这一条曾经被想当然地写反）。
真被别的连接锁住就退回 ``shutil.copy2``：宁可要一份可能不够干净的快照，
也不要**没有**快照。

同一波操作只拍一张
--------------------------------------------------------------------------------
一次点击常常连着 2~3 个 commit。若每个 commit 前都拍，最后留下的会是「操作到
一半」的中间态，回滚过去等于丢半截。所以设一个静默窗口
（``SNAPSHOT_MIN_INTERVAL`` 秒）：窗口内的写算作同一波，快照停在**这一波开始之前**。

落盘「先写临时文件、再原子改名」
--------------------------------------------------------------------------------
中途失败（磁盘满 / 被占用）不会留下半截的备份文件 —— 那比没有备份更坏，因为
它看起来是有的。原子替换保证「要么是完整的上一版，要么还是原来那份」。

失败不冒泡
--------------------------------------------------------------------------------
快照只是保险，不该让主流程崩。异常一律吞掉并记日志；``_last_at`` 无论成败都推进，
免得一直重试把界面拖慢。
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
BACKUP_DIR_NAME = "_backup"
BACKUP_SUFFIX = ".prev.db"

# 同一波写操作里只拍一张：一次点击通常连着 2~3 个 commit
SNAPSHOT_MIN_INTERVAL = 1.5

# 回滚时给「当前状态」留的后路，命名里带时间戳
ROLLBACK_KEEP_PREFIX = "before_rollback_"

# 写语句识别：只看开头，输入截断到 400 字符够用（关键字必在开头）
_WRITE_HEAD_RE = re.compile(
    r"^(?:[\s;]|--[^\n]*\n|/\*.*?\*/)*"
    r"(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|VACUUM|REINDEX|TRUNCATE)\b",
    re.IGNORECASE | re.DOTALL,
)

_last_at: dict[str, float] = {}
_last_result: dict[str, dict] = {}
_state_lock = threading.Lock()
_tls = threading.local()


def _logger():
    """复用主程序的 logger；拿不到就用模块自己的（测试与脚本场景）。"""
    import logging

    return logging.getLogger("db_backup")


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
def backup_dir(db_path) -> Path:
    """快照目录：与库文件同级，跟着库走（换电脑 / 插 U 盘都还在）。"""
    return Path(db_path).resolve().parent / BACKUP_DIR_NAME


def backup_path(db_path) -> Path:
    """「上一条」快照的完整路径。"""
    db = Path(db_path)
    return backup_dir(db) / (db.stem + BACKUP_SUFFIX)


def is_write_sql(sql) -> bool:
    """这条 SQL 会不会改数据？认不出开头就当读（宁可漏拍也不误拍）。"""
    if not sql:
        return False
    return bool(_WRITE_HEAD_RE.match(str(sql)[:400]))


# ---------------------------------------------------------------------------
# 快照
# ---------------------------------------------------------------------------
def snapshot(db_path, *, conn=None) -> Path | None:
    """把当前库拷成「上一条」快照。成功返回快照路径，失败返回 None（不抛）。

    ``conn`` 给了就用 SQLite 在线备份 API（一致性最好）；没给就走文件拷贝 ——
    那条路要求**没有别的进程在写**，只适合「首次建立」和「回滚」这类离线场景。
    """
    db = Path(db_path)
    if not db.exists():
        return None
    target = backup_path(db)
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if conn is not None:
            try:
                dst = sqlite3.connect(str(tmp))
                try:
                    conn.backup(dst)
                finally:
                    dst.close()
            except Exception:
                # 被别的连接锁住 → 退回拷文件。拷出来的可能不够干净，
                # 但「不够干净的快照」仍然好过「没有快照」。
                shutil.copy2(db, tmp)
        else:
            shutil.copy2(db, tmp)
        os.replace(tmp, target)
        return target
    except Exception as exc:  # 备份失败不该让写操作失败
        _logger().warning("数据库快照失败：%s（%s）", target, exc)
        try:
            tmp.unlink()
        except OSError:
            pass
        return None


def _maybe_snapshot(db_path: Path, conn=None) -> None:
    """写语句执行**之前**调用：够窗口了就拍一张。失败不冒泡。

    ``conn`` 是触发这次快照的连接：给了就走在线备份 API（事务一致），
    没给才退回拷文件（离线场景：首次建立 / 回滚）。
    """
    if getattr(_tls, "inside", False):
        return  # 防递归（理论上 backup 不走 trace，兜一道）
    key = str(db_path)
    now = time.monotonic()
    with _state_lock:
        if now - _last_at.get(key, 0.0) < SNAPSHOT_MIN_INTERVAL:
            return
        _last_at[key] = now
    _tls.inside = True
    try:
        result = snapshot(db_path, conn=conn)
        with _state_lock:
            _last_result[key] = {
                "at": datetime.now().isoformat(timespec="seconds"),
                "ok": result is not None,
                "path": str(result) if result else "",
            }
    finally:
        _tls.inside = False


def info(db_path) -> dict:
    """备份现状，供回滚脚本 / 诊断展示。"""
    db = Path(db_path)
    target = backup_path(db)
    out = {
        "db_path": str(db),
        "db_exists": db.exists(),
        "db_size": db.stat().st_size if db.exists() else 0,
        "db_mtime": (
            datetime.fromtimestamp(db.stat().st_mtime).isoformat(timespec="seconds")
            if db.exists()
            else ""
        ),
        "backup_path": str(target),
        "backup_exists": target.exists(),
        "backup_size": target.stat().st_size if target.exists() else 0,
        "backup_mtime": (
            datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds")
            if target.exists()
            else ""
        ),
        "last_snapshot": _last_result.get(str(db), {}),
    }
    return out


def verify(db_path) -> dict:
    """能不能用？打开跑一次 integrity_check，再数一遍表与行。

    只读，不会碰库里的数据。文件损坏时 SQLite 会在**第一次真读**时报错，
    所以这里必须真的读一遍（只看 ``exists()`` 会漏掉「文件在但内容坏了」）。
    """
    db = Path(db_path)
    result = {"path": str(db), "exists": db.exists(), "ok": False,
              "tables": 0, "rows": 0, "error": ""}
    if not db.exists():
        result["error"] = "文件不存在"
        return result
    try:
        conn = sqlite3.connect(str(db))
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()
            if not check or str(check[0]).lower() != "ok":
                result["error"] = f"integrity_check: {check[0] if check else '无返回'}"
                return result
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            rows = 0
            for name in tables:
                rows += conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            result.update({"ok": True, "tables": len(tables), "rows": int(rows)})
        finally:
            conn.close()
    except Exception as exc:
        result["error"] = str(exc)
    return result


def restore(db_path, *, source=None, keep_current: bool = True) -> dict:
    """用快照覆盖回使用库。**要求程序没在运行**（否则连接还指着旧文件）。

    覆盖之前先把「当前状态」另存一份（``before_rollback_<时间>.db``）——
    回滚本身也可能点错，别把仅有的后路也烧掉。

    ★ **先把源读进临时文件再动库文件**：``--from`` 常指向「上一次的后路」，
    而两次回滚可能落进同一秒 → 后路文件名撞名 → 写后路时会把源冲掉，
    于是「回滚了个寂寞」且不报错（回归套件 M/N 两节钉的就是这个）。
    """
    db = Path(db_path)
    src = Path(source) if source else backup_path(db)
    out = {"ok": False, "db": str(db), "source": str(src), "kept": "", "error": ""}
    if not src.exists():
        out["error"] = "没有可用的快照文件"
        return out
    check = verify(src)
    if not check["ok"]:
        out["error"] = f"快照本身不可用：{check['error']}"
        return out
    try:
        kept = ""
        # ★ 先把「要读的源」复制成临时文件，再去动库文件。
        #   否则下面写「后路」时可能**把源覆盖掉**：`--from` 指的就是上一次
        #   回滚留下的后路，而两次回滚常常在同一秒内（人点两下的间隔 < 1s），
        #   时间戳一旦撞名，`shutil.copy2(db, kept_path)` 会先把源冲掉，
        #   再拿被冲掉的源覆盖库 —— 结果是「回滚了个寂寞」，而且不报错。
        #   （回归套件 M/N 两节复现率 6/8，就是这么抓出来的。）
        tmp_src = src.with_name(src.name + ".restoring.tmp")
        shutil.copy2(src, tmp_src)
        try:
            if keep_current and db.exists():
                # 微秒 + 撞名就加序号：一秒内连退两次也留得下两份后路
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                kept_path = backup_dir(db) / f"{ROLLBACK_KEEP_PREFIX}{stamp}.db"
                n = 0
                while kept_path.exists():
                    n += 1
                    kept_path = kept_path.with_name(
                        "%s_%d.db" % (kept_path.stem, n))
                shutil.copy2(db, kept_path)
                kept = str(kept_path)
            shutil.copy2(tmp_src, db)
        finally:
            try:
                tmp_src.unlink()
            except OSError:
                pass
        for extra in (".journal", "-journal", ".wal", "-wal", ".shm", "-shm"):
            side = Path(str(db) + extra)
            if side.exists():
                side.unlink()
        out.update({"ok": True, "kept": kept, "rows": check["rows"],
                    "tables": check["tables"]})
    except Exception as exc:
        out["error"] = str(exc)
    return out


# ---------------------------------------------------------------------------
# 连接工厂：唯一入口
# ---------------------------------------------------------------------------
def _tracer_for(db_path: Path, conn):
    """返回一个 trace 回调：写语句临执行前触发快照。

    **不能用 ``conn.in_transaction`` 当判据** —— CPython 的 sqlite3 在执行 DML
    之前会隐式 ``BEGIN``，回调触发时事务已经开了，``in_transaction`` 恒为真，
    快照就永远拍不成（这个坑踩过一次：现象是「快照一直停在建表之前那张」）。

    正确的判据是「当前有没有**未提交的改动**」：把 ``total_changes`` 与
    「上次 commit 时的值」比 ——

    * 相等 → 这波还没写过，此刻文件仍是上一个已提交状态，可以拍；
    * 不等 → 已经写了一半，拍下来就是中间态（回滚过去等于丢半截），跳过。
    """

    def _tracer(sql):
        try:
            if not is_write_sql(sql):
                return
            if conn.total_changes != getattr(conn, "_committed_changes", None):
                return  # 当前事务里已有未提交改动，文件可能不干净
            _maybe_snapshot(db_path, conn)
        except Exception:
            pass  # trace 里抛异常会污染 execute，一律吞掉

    return _tracer


_conn_classes: dict[str, type] = {}


def _connection_class(db_path: Path) -> type:
    key = str(db_path)
    cls = _conn_classes.get(key)
    if cls is not None:
        return cls

    class SnapshotConnection(sqlite3.Connection):
        """带「写前快照」的连接。用法与 ``sqlite3.connect`` 完全一致。"""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # 基线：上次提交时的 total_changes。trace 靠它判断当前事务脏不脏
            self._committed_changes = self.total_changes
            try:
                self.set_trace_callback(_tracer_for(db_path, self))
            except Exception:
                pass

        def commit(self):
            """提交后刷新基线 —— 这是 trace 判据的锚点，别漏掉这一句。"""
            try:
                return super().commit()
            finally:
                self._committed_changes = self.total_changes

    SnapshotConnection.__name__ = "SnapshotConnection"
    SnapshotConnection.__qualname__ = "SnapshotConnection"
    _conn_classes[key] = SnapshotConnection
    return SnapshotConnection


def connect(db_path, **kwargs) -> sqlite3.Connection:
    """打开数据库，并在连接上挂好「写前快照」。

    项目里**所有指向主库的连接都该走这里** —— 少挂一个，从那条路上做的改动就
    不会出现在快照里。
    """
    path = Path(db_path)
    kwargs.setdefault("factory", _connection_class(path))
    return sqlite3.connect(str(path), **kwargs)
