# -*- coding: utf-8 -*-
r"""把「不能进 Git 的敏感数据」导出到一个文件夹，供随身 U 盘携带。

用法::

    python scripts/export_sensitive.py                 # 导出到默认目录
    python scripts/export_sensitive.py H:\随身备份      # 指定 U 盘目录
    python scripts/export_sensitive.py --skip-tools    # 不带 Tools（约 5 MB，秒级）
    python scripts/export_sensitive.py --list          # 只列出会导出什么

为什么要单独导出：这些东西**永远不该进 Git**（数据库含业务数据、凭据含手机号
与密码密文、excel 与各业务图片目录含内部资料），但换机器时又必须带着走。
仓库里的 .gitignore 只是"不提交"，不解决"随身带走"。

数据在哪（2026-09-29 之后）
--------------------------
程序的**运行目录是「随身包」**（默认 ``F:\ServerTimeDemo_随身包``，
可用环境变量 ``SERVERDEMO_PORTABLE_DIR`` 覆盖）。exe 同级目录就是 ``BASE_DIR``，
所以数据库、图片、Tools、excel、真实接口配置全在包里，**不在仓库里**。
本脚本因此以包为源；只有 ``.workbuddy``（AI 工作记忆）和源码运行时用的那份
``interfaces.local.json`` 还留在仓库根。

和 ``make_portable.py --target`` 的分工
---------------------------------------
* ``make_portable.py --target X:\``  —— 把**整份运行目录**（含 Tools，约 600 MB）
  同步到 U 盘。它就是"下班直接拷那个文件夹"的脚本版。
* 本脚本 —— 只导**数据**（``--skip-tools`` 时约 5 MB，秒级），
  另写 ``备份清单.txt``（含关键文件 SHA256）与 ``恢复说明.txt``。
  适合"只想带走数据、Tools 到新机器再下"的场景。

设计要点：

* **只读源**：导出是复制，源文件一个字节都不动。
* **增量**：目标文件与源文件的大小和修改时间都一致就跳过，第二次跑很快。
* **镜像结构**：备份目录里就是包（及仓库里的少数几项）的局部镜像，
  恢复时整目录覆盖回包里即可。
* ``--skip-tools``：Tools 约 600 MB，是能重新下载的工具软件。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = Path(r"F:\ServerTimeDemo_随身备份")
DEFAULT_PACK = Path(
    os.environ.get("SERVERDEMO_PORTABLE_DIR", r"F:\ServerTimeDemo_随身包")
)

# 随身包里要带走的数据（相对包根）。支持 * 通配。
PACK_PATTERNS = [
    # 主数据库与登录凭据
    "expiry_manager.db",
    "expiry_manager.db.*",
    "login_memory.json",
    "remember_me.json",
    "study_demo.db",
    # 「上一条」快照与回滚前的后路 —— 包整个丢了要恢复时，
    # 少了它就没有可回退的版本（它很小，别省）
    "_backup",
    # 业务图片
    "account_images",
    "process_flow_images",
    "study_notes_images",
    "study_notes_attachments",
    # 用户在意的表格
    "excel",
    # 真实接口配置（仓库里那份是 example.com 占位符）
    "interfaces.local.json",
    # 运行数据目录：pg 不备份也问题不大，但 .migrated 必须带上 ——
    # 缺了它，恢复后首次启动会把包根的数据再复制一份进 ExpiryManager_Data。
    "ExpiryManager_Data/.migrated",
    # 其余小目录
    "adb_history",
    "study_demo",
]

PACK_TOOLS = ["Tools"]

# 仓库里、包里没有的
REPO_PATTERNS = [
    # AI 开发记忆（含项目内部描述，不进公开仓库）
    ".workbuddy",
    # 源码运行时用的真实接口配置
    "embedded_admin_tools/config/interfaces.local.json",
]

# 关键文件指纹（算一次 SHA256，用于核对 U 盘是否拷全）。
# 元素是 (来源, 相对路径)，来源为 "pack" 或 "repo"。
FINGERPRINT = [
    ("pack", "expiry_manager.db"),
    ("pack", "login_memory.json"),
    ("pack", "excel/服务器与云服务到期情况.xlsx"),
    ("pack", "ExpiryManager_Data/.migrated"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB"):
        if n < step:
            return f"{n:.1f} {unit}"
        n /= step
    return f"{n:.1f} TB"


def expand(base: Path, patterns: list[str]) -> list[Path]:
    """把通配展开成实际存在的路径（相对 base）。"""
    found: list[Path] = []
    for pat in patterns:
        if any(ch in pat for ch in "*?["):
            found.extend(sorted(base.glob(pat)))
        else:
            p = base / pat
            if p.exists():
                found.append(p)
    # 去重 + 去掉被别的条目包含的子路径
    uniq: list[Path] = []
    seen: set[Path] = set()
    for p in found:
        rp = p.resolve()
        if rp in seen:
            continue
        if any(rp != o and rp.is_relative_to(o) for o in seen):
            continue
        seen.add(rp)
        uniq.append(p)
    return uniq


class Stats:
    def __init__(self) -> None:
        self.copied = 0
        self.skipped = 0
        self.bytes = 0

    def sync(self, src: Path, dst: Path) -> None:
        if dst.exists():
            try:
                s, d = src.stat(), dst.stat()
                if s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime):
                    self.skipped += 1
                    return
            except OSError:
                pass
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        self.copied += 1
        self.bytes += src.stat().st_size


def measure(p: Path) -> tuple[int, int]:
    if p.is_dir():
        fs = [f for f in p.rglob("*") if f.is_file()]
        return len(fs), sum(f.stat().st_size for f in fs)
    return 1, p.stat().st_size


def export(items: list[tuple[Path, Path, str]], dest: Path, stats: Stats) -> None:
    """items 是 (源绝对路径, 基准目录, 在备份里的落点)。"""
    for src, base, rel in items:
        target = dest / rel
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    stats.sync(f, target / f.relative_to(src))
        else:
            stats.sync(src, target)


def main() -> int:
    ap = argparse.ArgumentParser(description="导出不能进 Git 的敏感数据")
    ap.add_argument("dest", nargs="?", default=str(DEFAULT_DEST),
                    help="目标目录（默认 %(default)s）")
    ap.add_argument("--from", dest="source", default=None,
                    help=f"随身包位置，默认 {DEFAULT_PACK}（也可用环境变量 "
                         f"SERVERDEMO_PORTABLE_DIR）")
    ap.add_argument("--skip-tools", action="store_true",
                    help="不导出 Tools 工具软件（约 600 MB -> 约 5 MB）")
    ap.add_argument("--list", action="store_true", help="只列出会导出什么，不复制")
    args = ap.parse_args()

    dest = Path(args.dest)
    pack = Path(args.source) if args.source else DEFAULT_PACK
    fallback = False
    if not pack.is_dir():
        print(f"★ 随身包不存在：{pack}")
        print("  回退到按仓库根取数据（源码运行时的老布局）。")
        print("  包在别处就加 --from <路径>，或设 SERVERDEMO_PORTABLE_DIR。")
        print()
        pack, fallback = ROOT, True

    items: list[tuple[Path, Path, str]] = []
    for p in expand(pack, PACK_PATTERNS + ([] if args.skip_tools else PACK_TOOLS)):
        items.append((p, pack, p.relative_to(pack)))
    for p in expand(ROOT, REPO_PATTERNS):
        items.append((p, ROOT, p.relative_to(ROOT)))

    if not items:
        print("没有找到任何可导出的数据 —— 确认随身包路径对不对。")
        return 1

    print(f"随身包 : {pack}{'  （回退到仓库根）' if fallback else ''}")
    print(f"目标   : {dest}")
    print("-" * 70)
    total_files, total_bytes = 0, 0
    listing = []
    for src, _base, rel in items:
        n, b = measure(src)
        total_files += n
        total_bytes += b
        listing.append((str(rel), n, b))
        print(f"  {str(rel):<52} {n:>5} 个文件  {human(b):>10}")
    print("-" * 70)
    print(f"合计 {total_files} 个文件，{human(total_bytes)}")

    if args.list:
        print("\n（--list 模式，未复制任何文件）")
        return 0

    print("\n开始复制（增量：大小与修改时间都一致就跳过）…")
    started = time.time()
    stats = Stats()
    export(items, dest, stats)
    print(f"完成：复制 {stats.copied} 个文件（{human(stats.bytes)}），"
          f"跳过 {stats.skipped} 个未变动，用时 {time.time() - started:.1f} 秒")

    # ---------------------------------------------------------------- 清单
    lines = [
        "ServerTimeDemo 随身备份清单",
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"数据来源: {pack}",
        f"备份目录: {dest}",
        "",
        "这些内容**故意不进 Git**（数据库含业务数据、凭据含手机号与密码密文、",
        "excel 与业务图片目录含内部资料）。恢复时按下面的说明放回去即可。",
        "",
        "=" * 70,
        f"{'项':<52}{'文件数':>8}{'体积':>12}",
        "=" * 70,
    ]
    for rel, n, b in listing:
        lines.append(f"{rel:<52}{n:>8}{human(b):>12}")
    lines.append("=" * 70)
    lines.append(f"{'合计':<52}{total_files:>8}{human(total_bytes):>12}")
    lines.append("")

    fp_lines = []
    for origin, rel in FINGERPRINT:
        base = pack if origin == "pack" else ROOT
        f = base / rel
        if f.is_file():
            fp_lines.append(f"  {sha256(f)}  {rel}  ({f.stat().st_size} 字节)")
    if fp_lines:
        lines.append("关键文件指纹（SHA256，可用于核对 U 盘是否拷贝完整）：")
        lines.extend(fp_lines)
        lines.append("")

    (dest / "备份清单.txt").write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------ 恢复说明
    restore = [
        "恢复说明 —— 把这份备份用回一台新机器",
        "",
        "前提：程序现在的**运行目录就是「随身包」**（exe 与数据在同一层，",
        "exe 同级目录就是程序认的 BASE_DIR）。",
        "",
        "1. 先拿到代码（公开仓库）：",
        "       git clone https://github.com/22902902/ServerTimeDemo.git",
        "",
        f"2. 准备随身包目录：{pack}",
        "   （环境变量 SERVERDEMO_PORTABLE_DIR 可以改位置。）",
        "   包里的 exe 与 Tools\\ 可以从别处拷，或重新打包：",
        "       pyinstaller ExpiryManager_fixed.spec --clean --noconfirm --distpath \"<包目录>\"",
        "",
        "3. 把本备份目录里的内容**整目录覆盖合并**进包里：",
        "       expiry_manager.db 等       -> <包目录>\\",
        "       login_memory.json         -> <包目录>\\",
        "       account_images\\            -> <包目录>\\account_images\\",
        "       excel\\                     -> <包目录>\\excel\\",
        "       interfaces.local.json     -> <包目录>\\",
        "       _backup\\                   -> <包目录>\\_backup\\   （「上一条」快照）",
        "       ExpiryManager_Data\\.migrated -> <包目录>\\ExpiryManager_Data\\  ★别漏",
        "",
        "4. ★ ExpiryManager_Data\\.migrated 是 0 字节隐藏文件，**必须存在**。",
        "   缺了它，程序下次启动会把包根的数据再复制一份进 ExpiryManager_Data",
        "   （是复制不是搬，数据不丢，但会白占一块空间）。",
        "",
        "5. 用「备份清单.txt」里的 SHA256 核对关键文件是否拷全。",
        "",
        "注意：",
        "* Tools\\ 是可重新下载的工具软件，体积大；--skip-tools 的备份里没有它。",
        "* 只要整份拷包（含 Tools）时，用 make_portable.py --target X:\\ 更省事：",
        "       python scripts/make_portable.py --target X:\\",
        "* 日常别再从源码跑 main.py 写数据 —— 源码跑的 BASE_DIR 是仓库根，"
        "只适合临时调试；跑全量测试会在仓库根派生一份夹具库（可随时删）。",
    ]
    (dest / "恢复说明.txt").write_text("\n".join(restore), encoding="utf-8")

    print(f"清单已写入: {dest / '备份清单.txt'}")
    print(f"说明已写入: {dest / '恢复说明.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
