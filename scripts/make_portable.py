# -*- coding: utf-8 -*-
"""构建「随身包」—— 把运行所需的一切收进一个自包含文件夹。

为什么需要它
------------
程序的数据本来散落两处，换电脑或拷 U 盘时要一个个找：

* ``BASE_DIR``（exe 同级目录）下的 ``expiry_manager.db``、``account_images``、
  ``Tools``…… —— 运行时产生的数据；
* 仓库根下的 ``excel/`` —— 「服务器与云服务到期情况.xlsx」是程序的默认导入文件；
* ``interfaces.local.json`` —— 真实接口地址（不入库，只在本机）。

少带一样，新电脑上就少一块功能；多带一份，就多出几百 MB 废拷贝。

「随身包」把这些一次收齐：里面的 ``ExpiryManager_fixed.exe`` 双击即可运行，
而 exe 同级目录就是 ``BASE_DIR`` —— 数据天然就在它旁边。拷走整个文件夹，
换台电脑接着用，不需要安装。

用法::

    python scripts/make_portable.py --full           # 首次建包（同步全部）
    python scripts/make_portable.py                  # 日常只刷 exe（几秒）
    python scripts/make_portable.py --target E:\\     # 直接同步到 U 盘
    python scripts/make_portable.py --list           # 只列出会同步什么

两个必须知道的点
----------------
1. 包里保留了 ``ExpiryManager_Data/.migrated`` 这个隐藏空文件。程序首次启动时
   若发现它不存在，会执行「数据目录迁移」，把根目录的数据库、图片、Tools
   反向搬进 ``ExpiryManager_Data/`` —— 那会让数据换个位置。所以它不能少。
2. 默认只刷 exe，是为了防止「用仓库根的旧 excel / 旧 study_demo.db 覆盖便携包里
   已经更新的那份」。同步数据请显式加 ``--full``，且它默认保护较新的目标文件。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "dist" / "随身包"
EXE_NAME = "ExpiryManager_fixed.exe"

# 源（相对仓库根）-> 随身包内的相对路径。
# 顺序有意义：先放本体，再放数据，最后放配置。
ITEMS: list[tuple[str, str]] = [
    (f"dist/{EXE_NAME}", EXE_NAME),
    ("dist/expiry_manager.db", "expiry_manager.db"),
    ("dist/login_memory.json", "login_memory.json"),
    ("dist/remember_me.json", "remember_me.json"),
    ("dist/account_images", "account_images"),
    ("dist/study_notes_images", "study_notes_images"),
    ("dist/adb_history", "adb_history"),
    ("dist/study_demo", "study_demo"),
    ("excel", "excel"),
    ("study_demo.db", "study_demo.db"),
    ("embedded_admin_tools/config/interfaces.local.json", "interfaces.local.json"),
    ("dist/Tools", "Tools"),
]

# 包里必须存在、但不是从源文件拷来的东西
GUARD_FILES = ("ExpiryManager_Data/.migrated",)
GUARD_DIRS = (
    "ExpiryManager_Data/logs",
    "study_notes_attachments",
    "process_flow_images",
)

README_NAME = "使用说明.txt"
README_TEMPLATE = """\
ServerTimeDemo 随身包
=====================

怎么用
------
双击「{exe}」即可运行。数据就在本文件夹里，换一台电脑照样能用 ——
把整个文件夹拷过去就行，不需要安装任何东西。

拷 U 盘
-------
直接拷这个文件夹（带着里面全部内容）。不要只拷 exe：数据库、图片、
工具箱都在同级的子文件夹里，漏了就少一块功能。

文件夹里都是什么
----------------
  {exe}   程序本体
  expiry_manager.db        主数据库（账号、待办、流程、笔记……）
  account_images\\           账号截图、流程步骤截图
  Tools\\                    工具箱里的软件
  excel\\                    服务器与云服务到期情况.xlsx（导入用）
  interfaces.local.json    接口地址配置（内部信息，请勿外传）
  ExpiryManager_Data\\       程序运行日志
  login_memory.json        登录信息
  remember_me.json         「记住我」状态

三条注意
--------
1. 这些文件是一个整体，别单独删或改名。特别是 ExpiryManager_Data\\
   里那个隐藏的空文件 .migrated 不能删 —— 程序靠它判断「数据已经
   整理好了」，删掉会导致下次启动把数据搬到别的位置。
2. interfaces.local.json 里是内部接口地址，敏感，不要分享出去。
3. 更新程序：重新构建后执行 `python scripts/make_portable.py`
   （不加 --full），它会把最新的 exe 同步进来，数据不受影响。

生成时间：{ts}
"""


class Stats:
    def __init__(self) -> None:
        self.copy = 0
        self.skip = 0
        self.newer = 0
        self.bytes = 0
        self.missing: list[str] = []

    def line(self) -> str:
        return (
            f"复制 {self.copy} 个 / {self.bytes / 1048576:.1f} MB，"
            f"跳过 {self.skip} 个（已是最新），"
            f"保护 {self.newer} 个（目标更新，未覆盖）"
        )


def _sync_file(src: Path, dst: Path, st: Stats, *, protect_newer: bool) -> None:
    """把单个文件同步到包内。大小与修改时间都一致就跳过。"""
    if dst.exists() and dst.is_file():
        s, d = src.stat(), dst.stat()
        if protect_newer and d.st_mtime > s.st_mtime + 1:
            st.newer += 1
            return
        if s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime):
            st.skip += 1
            return
    # 只读文件要先去掉只读位才能覆盖（Tools 里有这类文件）
    if dst.exists():
        try:
            dst.chmod(0o666)
        except OSError:
            pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    st.copy += 1
    st.bytes += src.stat().st_size


def _sync_tree(src: Path, dst: Path, st: Stats, *, protect_newer: bool) -> None:
    # 先建根，否则「源是个空目录」时目标不会被创建
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
        else:
            _sync_file(path, dst / rel, st, protect_newer=protect_newer)


def build(target: Path, *, full: bool, protect_newer: bool = True) -> Stats:
    st = Stats()
    target.mkdir(parents=True, exist_ok=True)

    for src_rel, dst_rel in ITEMS:
        src = ROOT / src_rel
        if not src.exists():
            st.missing.append(src_rel)
            continue
        # 默认只刷 exe；其余等 --full
        if not full and dst_rel != EXE_NAME:
            continue
        dst = target / dst_rel
        if src.is_dir():
            _sync_tree(src, dst, st, protect_newer=protect_newer)
        else:
            _sync_file(src, dst, st, protect_newer=protect_newer)
        print(f"  [{dst_rel}] 已同步", flush=True)

    # 护栏：防迁移标记 + 日志目录
    for rel in GUARD_FILES:
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(b"")
            print(f"  [{rel}] 已创建（防迁移标记）", flush=True)
    for rel in GUARD_DIRS:
        (target / rel).mkdir(parents=True, exist_ok=True)

    # 使用说明：内容有变化才重写
    readme = target / README_NAME
    text = README_TEMPLATE.format(exe=EXE_NAME, ts=datetime.now().strftime("%Y-%m-%d %H:%M"))
    if not readme.exists() or readme.read_text(encoding="utf-8") != text:
        readme.write_text(text, encoding="utf-8", newline="\r\n")

    return st


def show_list() -> None:
    print(f"随身包目标：{DEFAULT_TARGET}")
    print(f"（仓库根 {ROOT}）")
    print()
    print("会同步这些：")
    total = 0
    for src_rel, dst_rel in ITEMS:
        src = ROOT / src_rel
        if not src.exists():
            print(f"  [缺] {src_rel:52} -> {dst_rel}")
            continue
        if src.is_dir():
            n = sum(1 for p in src.rglob("*") if p.is_file())
            size = sum(p.stat().st_size for p in src.rglob("*") if p.is_file())
            print(f"  [{n:4} 个文件 {size / 1048576:8.1f} MB] {src_rel:44} -> {dst_rel}")
        else:
            size = src.stat().st_size
            print(f"  [ {size / 1048576:8.1f} MB         ] {src_rel:44} -> {dst_rel}")
        total += size
    print()
    print(f"合计约 {total / 1048576:.1f} MB")
    print("另外会创建：ExpiryManager_Data/.migrated（防迁移标记）、ExpiryManager_Data/logs/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="构建 ServerTimeDemo 随身包（自包含、可运行、可拷走）")
    ap.add_argument("--target", default=str(DEFAULT_TARGET), help="目标文件夹，默认 dist/随身包；可直接给 U 盘盘符")
    ap.add_argument("--full", action="store_true", help="同步全部内容（首次建包用）；默认只刷 exe")
    ap.add_argument("--no-protect", action="store_true", help="--full 时允许用较旧的源覆盖较新的目标（慎用）")
    ap.add_argument("--list", action="store_true", help="只列出会同步什么，不动文件")
    args = ap.parse_args(argv)

    if args.list:
        show_list()
        return 0

    target = Path(args.target)
    mode = "全部内容" if args.full else f"仅 {EXE_NAME}"
    print(f"随身包 -> {target}")
    print(f"模式：{mode}")
    print()

    st = build(target, full=args.full, protect_newer=not args.no_protect)

    print()
    print(st.line())
    if st.missing:
        print()
        print("以下源不存在（已跳过，检查一下是不是路径变了）：")
        for m in st.missing:
            print(f"  - {m}")
    print()
    print(f"完成。整个文件夹拷走即可：{target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
