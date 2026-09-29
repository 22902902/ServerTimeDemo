# -*- coding: utf-8 -*-
"""维护 / 分发「随身包」—— 运行所需的一切都在一个文件夹里。

包的位置
--------
默认 ``F:\\ServerTimeDemo_随身包``，可用环境变量 ``SERVERDEMO_PORTABLE_DIR`` 覆盖。

它**放在仓库外面**是有意的：``dist/`` 是 PyInstaller 的默认产物目录，历史上还有
``build.bat`` 首句 ``rmdir /s /q dist`` 的写法 —— 包放在里面随时可能被连根清掉，
而它装的是**全部数据**（也是唯一的一份活库）。

更新程序
--------
打包时把产物直接写进包里，不要再用默认的 ``dist/``::

    pyinstaller ExpiryManager_fixed.spec --clean --noconfirm \\
        --distpath "F:/ServerTimeDemo_随身包"
    python scripts/make_portable.py            # 维护护栏文件（幂等，随时可跑）

**数据不用同步** —— 平时双击包里的 exe 用，数据就写在包里了。

拷到 U 盘
---------
::

    python scripts/make_portable.py --target X:\\

整份增量同步（大小与修改时间都一致就跳过），第二次跑很快。
目标上较新的同名文件不会被覆盖，防手滑。

两个必须知道的点
----------------
1. 包里 ``ExpiryManager_Data/.migrated`` 是个 0 字节隐藏文件，**不能删**。
   ``main.py`` 的 ``_migrate_data_dir()`` 只看它在不在：不存在就把 ``BASE_DIR``
   根下的 db / 图片 / Tools 用 ``shutil.copytree`` **复制一份**进
   ``ExpiryManager_Data/``。是复制不是搬，**数据不会丢**，但 Tools 有 599 MB，
   白白多占一块空间。
2. 包里还有个隐藏的 ``ExpiryManager_Data/logs/`` —— 程序把日志写在那里，
   顺带证明「包目录就是它的 BASE_DIR」。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE_NAME = "ExpiryManager_fixed.exe"

# 包的位置：优先环境变量，便于换机/换盘时覆盖
DEFAULT_PACKAGE = Path(
    os.environ.get("SERVERDEMO_PORTABLE_DIR", r"F:\ServerTimeDemo_随身包")
)

# 包里必须存在、但不是从源码拷来的东西
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

也可以让脚本代劳（增量同步，第二次很快）：
    python scripts/make_portable.py --target X:\\          （X 换成 U 盘盘符）

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
   整理好了」，删掉会让下次启动白复制一份 Tools 进来，占地方。
2. interfaces.local.json 里是内部接口地址，敏感，不要分享出去。
3. 更新程序：打包时把产物直接写进本文件夹（pyinstaller 加
   --distpath），数据不受影响；不要先在别处打包再手动拷 exe。

生成时间：{ts}
"""


class Stats:
    def __init__(self) -> None:
        self.copy = 0
        self.skip = 0
        self.newer = 0
        self.bytes = 0

    def line(self) -> str:
        return (
            f"复制 {self.copy} 个 / {self.bytes / 1048576:.1f} MB，"
            f"跳过 {self.skip} 个（已是最新），"
            f"保护 {self.newer} 个（目标更新，未覆盖）"
        )


def _sync_file(src: Path, dst: Path, st: Stats, *, protect_newer: bool) -> None:
    """把单个文件同步过去。大小与修改时间都一致就跳过。"""
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


def ensure_guards(pkg: Path) -> None:
    """把包里那些「不是从源码拷来的」东西补齐：防迁移标记、日志目录、使用说明。"""
    pkg.mkdir(parents=True, exist_ok=True)
    for rel in GUARD_FILES:
        p = pkg / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(b"")
            print(f"  [{rel}] 已创建（防迁移标记）")
    for rel in GUARD_DIRS:
        (pkg / rel).mkdir(parents=True, exist_ok=True)

    readme = pkg / README_NAME
    text = README_TEMPLATE.format(
        exe=EXE_NAME, ts=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    if not readme.exists() or readme.read_text(encoding="utf-8") != text:
        readme.write_text(text, encoding="utf-8", newline="\r\n")
        print(f"  [{README_NAME}] 已更新")


def sync_tree(src: Path, dst: Path, st: Stats, *, protect_newer: bool) -> None:
    """整份增量同步（src 一般是包本身，dst 是 U 盘）。"""
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
        else:
            _sync_file(path, dst / rel, st, protect_newer=protect_newer)


def show_list(pkg: Path) -> None:
    print(f"随身包：{pkg}")
    if not pkg.exists():
        print("  ★ 不存在 —— 是不是还没打包？见本脚本文件头的说明。")
        return
    fs = [f for f in pkg.rglob("*") if f.is_file()]
    print(f"  {len(fs)} 个文件 / {sum(f.stat().st_size for f in fs) / 1048576:.1f} MB")
    print()
    print("顶层内容：")
    for it in sorted(pkg.iterdir(), key=lambda x: (x.is_file(), x.name)):
        if it.is_dir():
            sub = [f for f in it.rglob("*") if f.is_file()]
            size = sum(f.stat().st_size for f in sub)
            print(f"  [目录] {it.name:28} {len(sub):4} 个文件 {size / 1048576:9.1f} MB")
        else:
            print(f"  [文件] {it.name:28} {'':4}          {it.stat().st_size / 1024:9.1f} KB")
    print()
    print("护栏检查：")
    for rel in GUARD_FILES:
        ok = (pkg / rel).exists()
        print(f"  {'✓' if ok else '★ 缺失'} {rel}")
    for rel in GUARD_DIRS:
        ok = (pkg / rel).is_dir()
        print(f"  {'✓' if ok else '★ 缺失'} {rel}/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="维护 / 分发 ServerTimeDemo 随身包（改代码后维护护栏；拷 U 盘用 --target）"
    )
    ap.add_argument("--package", default=str(DEFAULT_PACKAGE),
                    help=f"包的位置，默认 {DEFAULT_PACKAGE}")
    ap.add_argument("--target", default=None,
                    help="把整个包增量同步到这里（如 U 盘根目录），会在其下建同名文件夹")
    ap.add_argument("--no-protect", action="store_true",
                    help="允许用较旧的源覆盖较新的目标（慎用）")
    ap.add_argument("--list", action="store_true", help="只列出包里有什么，不动文件")
    args = ap.parse_args(argv)

    pkg = Path(args.package)

    if args.list:
        show_list(pkg)
        return 0

    print(f"随身包：{pkg}")
    print()
    print("维护护栏文件：")
    ensure_guards(pkg)
    print("✓ 就绪")

    if args.target:
        dst = Path(args.target) / pkg.name
        print()
        print(f"同步到：{dst}")
        st = Stats()
        sync_tree(pkg, dst, st, protect_newer=not args.no_protect)
        print(st.line())
        print()
        print(f"完成。U 盘上的文件夹：{dst}")
    else:
        print()
        print("（未指定 --target，只维护了包本身。）")
        print(f"整个文件夹拷走即可：{pkg}")
        print("或让脚本同步：python scripts/make_portable.py --target X:\\")
    return 0


if __name__ == "__main__":
    sys.exit(main())
