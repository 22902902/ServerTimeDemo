# -*- coding: utf-8 -*-
"""回归套件：写前快照（db_backup）与回滚脚本（scripts/rollback_db.py）。

为什么这条防线值得单独一个套件
------------------------------------------------------------------------------
「每次写库前留一份」是整个数据层的保险丝 —— 它一旦静默失效，表现出来的样子
和「功能正常」一模一样（数据照写、界面照跑），只有真出事要回滚时才发现没有
可退的版本。所以这里不测「能不能导入」，而是把**时机**逐条钉死：

* 快照拍的是「写之前」的状态（不是写之后，也不是中间态）
* 同一波连续写只拍一张（否则回滚过去等于丢半截）
* 纯读不拍（否则回滚点会被「看一眼」推后）
* 拍不成时写操作照样成功（备份不能把主流程拖垮）

回滚脚本走**子进程**跑真 CLI，覆盖「--list 不能误回滚」「坏备份要拒绝」
「回滚前留后路」「没有备份时拒绝执行」这些只看函数签名看不出来的行为。

全程用临时库，不碰随身包里的真实数据。
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db_backup  # noqa: E402

SCRIPT = ROOT / "scripts" / "rollback_db.py"
passed = failed = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok    {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


def make_db(path: Path, rows: int = 0) -> None:
    """造一个最小可用的库：一张表 + 若干行。"""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE todo_lists (id INTEGER PRIMARY KEY, name TEXT)")
        for i in range(rows):
            conn.execute("INSERT INTO todo_lists (name) VALUES (?)", (f"第 {i} 行",))
        conn.commit()
    finally:
        conn.close()


def count(path: Path, table: str = "todo_lists") -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def run_cli(*args) -> subprocess.CompletedProcess:
    """stdin 接 DEVNULL —— 否则脚本里的 input() 会把测试挂死。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        cwd=str(ROOT),
        timeout=90,
    )


def body_of(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or b"").decode("utf-8", "replace")


def section_a() -> None:
    print("A. is_write_sql 只认写语句")
    for sql, want in [
        ("SELECT * FROM t", False),
        ("  select 1", False),
        ("INSERT INTO t (a) VALUES (1)", True),
        ("insert into t values (1)", True),
        ("\n\t UPDATE t SET a=1", True),
        ("-- 注释\nDELETE FROM t", True),
        ("/* 块注释 */ REPLACE INTO t VALUES (1)", True),
        ("CREATE TABLE IF NOT EXISTS x (a)", True),
        ("DROP TABLE x", True),
        ("ALTER TABLE x ADD COLUMN b", True),
        ("PRAGMA table_info(t)", False),
        ("BEGIN", False),
        ("COMMIT", False),
        ("", False),
        (None, False),
        ("WITH x AS (SELECT 1) SELECT * FROM x", False),
    ]:
        check(f"{str(sql)[:34]!r} → {want}", db_backup.is_write_sql(sql) is want)


def section_b(root: Path) -> tuple[Path, sqlite3.Connection, Path]:
    print("\nB. connect() 是唯一入口，且真的挂上了快照")
    db = root / "expiry_manager.db"
    conn = db_backup.connect(db)
    check("返回的是 Connection 子类", type(conn) is not sqlite3.Connection)
    check("类名可读", type(conn).__name__ == "SnapshotConnection")
    check("库文件名与备份名对得上", db_backup.backup_path(db).name == "expiry_manager.prev.db")
    check("备份目录叫 _backup", db_backup.backup_dir(db).name == "_backup")
    conn.execute("CREATE TABLE todo_lists (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    return db, conn, db_backup.backup_path(db)


def section_c(db: Path, conn: sqlite3.Connection, snap: Path) -> None:
    print("\nC. 快照拍的是「写之前」")
    db_backup._last_at.clear()
    conn.execute("INSERT INTO todo_lists (name) VALUES ('甲')")
    conn.commit()
    check("快照文件已生成", snap.exists())
    n = count(snap)
    check(f"库里 1 行时，快照停在 0 行（实际 {n}）", n == 0)

    print("\nD. 同一波连续写只拍一张")
    db_backup._last_at.clear()
    conn.execute("INSERT INTO todo_lists (name) VALUES ('乙')")
    conn.execute("INSERT INTO todo_lists (name) VALUES ('丙')")
    conn.commit()
    n = count(snap)
    check(f"窗口内连写两条，快照仍是 1 行（实际 {n}）", n == 1)

    print("\nE. 纯读不产生新快照")
    mtime = snap.stat().st_mtime_ns
    db_backup._last_at.clear()
    for _ in range(50):
        conn.execute("SELECT COUNT(*) FROM todo_lists").fetchone()
    check("反复 SELECT 后快照未被改写", snap.stat().st_mtime_ns == mtime)

    print("\nF. 窗口过后再写，快照推到「这一次写之前」")
    db_backup._last_at.clear()
    conn.execute("INSERT INTO todo_lists (name) VALUES ('丁')")
    conn.commit()
    n = count(snap)
    check(f"库里 4 行时快照推到 3 行（实际 {n}）", n == 3)


def section_g(root: Path, db: Path, conn: sqlite3.Connection) -> None:
    print("\nG. verify() 能识破坏文件")
    check("真库 verify 通过", db_backup.verify(db)["ok"])
    bad = root / "bad.db"
    bad.write_bytes(b"this is not a sqlite file at all" * 40)
    r = db_backup.verify(bad)
    check("坏文件 verify 不通过", not r["ok"], r["error"])
    check("坏文件不会假装 OK", r["rows"] == 0 and r["tables"] == 0)

    print("\nH. info() 给出时间与大小")
    conn.close()
    i = db_backup.info(db)
    check("备份存在且非空", i["backup_exists"] and i["backup_size"] > 0)
    check("库信息也在", i["db_exists"] and i["db_mtime"] != "")

    print("\nI. 快照写不进去时，写操作照样成功")
    blocked = root / "blocked"
    blocked.mkdir(parents=True, exist_ok=True)
    (blocked / "_backup").write_text("占位文件，不是目录", encoding="utf-8")
    c2 = db_backup.connect(blocked / "x.db")
    c2.execute("CREATE TABLE todo_lists (id INTEGER PRIMARY KEY, name TEXT)")
    c2.commit()
    db_backup._last_at.clear()
    c2.execute("INSERT INTO todo_lists (name) VALUES ('还能写')")
    c2.commit()
    check("写操作成功（不被备份拖垮）", count(blocked / "x.db") == 1)
    check("快照没生成但也没抛异常", not db_backup.backup_path(blocked / "x.db").is_file())
    c2.close()


def section_j(root: Path) -> None:
    print("\nJ. 回滚脚本：没有备份时拒绝执行")
    db = root / "cli1" / "expiry_manager.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    make_db(db, 0)
    proc = run_cli("--db", str(db), "--yes")
    check("退出码非 0", proc.returncode != 0, str(proc.returncode))
    check("说了「找不到可用备份」", "找不到可用" in body_of(proc))

    print("\nK. 回滚脚本：--list 只查看，一个字节都不动")
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO todo_lists (name) VALUES ('一')")
    conn.execute("INSERT INTO todo_lists (name) VALUES ('二')")
    conn.commit()
    conn.close()
    db_backup.snapshot(db)
    before = db.read_bytes()
    proc = run_cli("--db", str(db), "--list")
    body = body_of(proc)
    check("退出码 0", proc.returncode == 0, str(proc.returncode))
    check("列出了可回滚点", "expiry_manager.prev.db" in body)
    check("明确说了只做查看", "什么都没改" in body)
    check("没有走到确认环节", "确定继续" not in body)
    check("使用库一个字节没动", db.read_bytes() == before)

    print("\nL. 回滚脚本：改动后按「上一条」回滚，并留后路")
    n0 = count(db)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO todo_lists (name) VALUES ('临时行')")
    conn.commit()
    conn.close()
    n1 = count(db)
    check(f"已插入一行（{n0} → {n1}）", n1 == n0 + 1)

    proc = run_cli("--db", str(db), "--yes")
    body = body_of(proc)
    check("回滚退出码 0", proc.returncode == 0, body[-300:])
    check("输出了「已回滚」", "已回滚" in body)
    check("说了会另存回滚前状态", "回滚前状态另存" in body)
    check(f"数据退回上一条（{n1} → {count(db)}）", count(db) == n0)

    kept = sorted((db.parent / "_backup").glob("before_rollback_*.db"))
    check("生成了 before_rollback_*.db", len(kept) == 1, str(kept))
    if kept:
        check("后路里存的是回滚前的数据", count(kept[0]) == n1)

    print("\nM. 回滚脚本：--from 指回后路可以再退回来")
    if kept:
        proc = run_cli("--db", str(db), "--from", str(kept[0]), "--yes")
        check("二次回滚退出码 0", proc.returncode == 0)
        check(f"又回到「插入后」（{count(db)}）", count(db) == n1)

    print("\nM2. 一秒内连退两次：后路不撞名，源不被自己覆盖")
    rb = sorted((db.parent / "_backup").glob("before_rollback_*.db"))
    check(f"两次回滚留下两份不同的后路（实际 {len(rb)}）", len(rb) == 2,
          str([p.name for p in rb]))
    if len(rb) == 2:
        got = [count(p) for p in rb]
        check(f"两份各是某一次的「回滚前」（行数 {got}，应含 {n0} 与 {n1}）",
              set(got) == {n0, n1}, str(got))

    print("\nN. 回滚脚本：备份损坏时拒绝拿它回滚")
    snap = db_backup.backup_path(db)
    good = snap.with_name("_good_copy.db")
    shutil.copy2(snap, good)
    snap.write_bytes(b"garbage not a database" * 100)
    proc = run_cli("--db", str(db), "--yes")
    body = body_of(proc)
    check("拒绝了坏备份", proc.returncode != 0 and "不可用" in body, body[-300:])
    check("使用库没被动过", count(db) == n1)
    shutil.copy2(good, snap)

    print("\nO. 回滚脚本：不给 --yes 时不会误回滚（非交互环境）")
    before = count(db)
    run_cli("--db", str(db))
    check("数据没变（默认要人工确认）", count(db) == before)

    print("\nP. 回滚脚本：--help 可用")
    check("--help 退出码 0", run_cli("--help").returncode == 0)


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="test_db_backup_"))
    try:
        section_a()
        db, conn, snap = section_b(root)
        section_c(db, conn, snap)
        section_g(root, db, conn)
        section_j(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + "=" * 78)
    print(f"通过 {passed} 项，失败 {failed} 项")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
