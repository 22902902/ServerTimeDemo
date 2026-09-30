#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
回滚数据库：把「上一条」备份盖回使用库
================================================================================
平时不用管它 —— 主程序每次写库之前会自动把当前状态存成
``_backup/expiry_manager.prev.db``，这里只负责「真出事了把它盖回去」。

用法（在项目目录下）::

    python scripts\\rollback_db.py                 # 只看现状，不动任何文件
    python scripts\\rollback_db.py --list          # 再列出所有可回滚点
    python scripts\\rollback_db.py --yes           # 直接回滚到「上一条」
    python scripts\\rollback_db.py --from <文件> --yes   # 回滚到指定的一份

几条硬约束
--------------------------------------------------------------------------------
* **程序必须没在运行**。库还开着的时候覆盖文件，改动会互相打架；脚本会先检测，
  检测到就直接拒绝（用 ``--force`` 才能绕过，不建议）。
* **回滚前先把当前状态留一份**（``_backup/before_rollback_<时间>.db``）。
  回滚本身也可能点错 —— 别把仅有的后路也烧掉。
* **先验再盖**：备份文件会先跑 ``PRAGMA integrity_check`` 并数一遍表/行，
  确认它自己是好的才拿去覆盖。半截的备份比没有备份更坏。
* 覆盖完成后顺手清掉 ``-journal`` / ``-wal`` / ``-shm`` 残留，否则 SQLite 会拿
  旧日志去「修复」新库，把刚恢复的数据又搅乱。

默认目标是随身包里的库（``SERVERDEMO_PORTABLE_DIR`` 下的 ``expiry_manager.db``，
默认 ``F:\\ServerTimeDemo_随身包``），换机器 / 换目录用环境变量或 ``--db`` 指定。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import db_backup  # noqa: E402

# 运行目录（随身包）——与 make_portable / export_sensitive / check_exe
# 同一个约定：环境变量优先，默认仍是本机这个位置。
PORTABLE_DIR = Path(os.environ.get("SERVERDEMO_PORTABLE_DIR",
                                   r"F:\ServerTimeDemo_随身包"))
DEFAULT_DB = PORTABLE_DIR / "expiry_manager.db"
APP_EXE = "ExpiryManager_fixed.exe"


def app_running() -> bool:
    """主程序还在跑吗？检测不出来时返回 False（不阻断，但会提示）。

    ★ 不要给 `subprocess.run` 加 `text=True` —— 中文 Windows 的 tasklist 输出是
    GBK，Python 会按 UTF-8 去解，直接抛 UnicodeDecodeError（踩过）。
    直接拿 bytes 比就行，编码是什么都无所谓。
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_EXE}"],
            capture_output=True, timeout=10,
        ).stdout
        return APP_EXE.lower().encode() in (out or b"").lower()
    except Exception:
        return False


def human_size(n: int) -> str:
    return f"{n:,} 字节" if n < 1024 * 1024 else f"{n / 1024 / 1024:.2f} MB"


def show(db: Path) -> None:
    info = db_backup.info(db)
    print("=" * 68)
    print("当前状态")
    print("=" * 68)
    print(f"  使用库   {info['db_path']}")
    if info["db_exists"]:
        print(f"           {human_size(info['db_size'])} · 改动于 {info['db_mtime']}")
    else:
        print("           ⚠ 文件不存在")
    print(f"  备份 db  {info['backup_path']}")
    if info["backup_exists"]:
        print(f"           {human_size(info['backup_size'])} · 备份于 {info['backup_mtime']}")
        gap = info["db_size"] - info["backup_size"]
        print(f"           与使用库相差 {human_size(abs(gap))}（{'使用库更大' if gap > 0 else '使用库更小/相同'}）")
    else:
        print("           ⚠ 还没有备份 —— 回滚无从谈起")
    last = info.get("last_snapshot") or {}
    if last:
        print(f"  本次运行内最近一次快照：{last.get('at', '?')} {'成功' if last.get('ok') else '失败'}")
    print()


def list_points(db: Path) -> list[Path]:
    """所有可回滚点：『上一条』+ 历次回滚留下的 before_rollback 存档。"""
    folder = db_backup.backup_dir(db)
    if not folder.exists():
        return []
    points = [p for p in folder.glob("*.db") if p.is_file()]
    return sorted(points, key=lambda p: p.stat().st_mtime, reverse=True)


def show_points(db: Path) -> None:
    points = list_points(db)
    if not points:
        print("（还没有任何可回滚点）\n")
        return
    print("可回滚点（新的在前）")
    print("=" * 68)
    for p in points:
        mark = "←「上一条」" if p == db_backup.backup_path(db) else ""
        when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {when}  {human_size(p.stat().st_size):>12}  {p.name} {mark}")
    print()


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes", "是")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把「上一条」备份盖回使用库（回滚一步）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="使用库路径")
    parser.add_argument("--from", dest="source", default="", help="指定用来回滚的备份文件")
    parser.add_argument("--list", action="store_true", help="列出所有可回滚点")
    parser.add_argument("--yes", action="store_true", help="跳过确认（脚本化时用）")
    parser.add_argument("--force", action="store_true", help="程序在运行时也强行回滚（危险）")
    args = parser.parse_args()

    db = Path(args.db)
    source = Path(args.source) if args.source else None

    show(db)
    if args.list:
        show_points(db)
        print("（--list 只做查看，什么都没改；要去掉 --list 才会真的回滚）")
        return 0

    target = source or db_backup.backup_path(db)
    if not target.exists():
        print("[中止] 找不到可用的备份，没什么可回滚的。")
        return 1

    check = db_backup.verify(target)
    print(f"待回滚的备份：{target.name}")
    if check["ok"]:
        print(f"  ✓ 完整性 OK · {check['tables']} 表 / {check['rows']} 行\n")
    else:
        print(f"  ✗ 这份备份不可用：{check['error']}\n[中止] 换个回滚点试试（--list 看全部）")
        return 1

    if app_running() and not args.force:
        print(f"[中止] {APP_EXE} 正在运行 —— 先关掉程序再回滚。")
        print("       （程序开着时覆盖库文件，改动会互相打架，越弄越乱）")
        return 1
    if app_running():
        print("⚠ 程序还在运行，但指定了 --force，继续。")

    if not args.yes:
        print("这会用上面那份备份**覆盖**当前使用库，当前数据将退回那个时间点。")
        print("（覆盖前会把当前状态另存一份 before_rollback_<时间>.db，还能再退回来）")
        if not confirm("确定继续？输入 y 回车："):
            print("[取消] 什么都没做。")
            return 1

    result = db_backup.restore(db, source=target)
    print()
    if not result["ok"]:
        print(f"[失败] {result['error']}")
        return 1

    print("=" * 68)
    print("[完成] 已回滚")
    print("=" * 68)
    print(f"  使用库已退回：{target.name}")
    print(f"  表 / 行      ：{result['tables']} / {result['rows']}")
    if result.get("kept"):
        print(f"  回滚前状态另存：{result['kept']}")
        print("                 （按错了就用 --from 指向它，再回滚一次）")
    print("\n  现在可以打开程序检查数据了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
