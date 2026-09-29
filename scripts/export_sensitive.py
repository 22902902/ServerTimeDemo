# -*- coding: utf-8 -*-
r"""把「不能进版本库的敏感数据」导出到一个文件夹，供随身 U 盘携带。

用法::

    python scripts/export_sensitive.py                 # 导出到默认目录
    python scripts/export_sensitive.py H:\随身备份      # 指定 U 盘目录
    python scripts/export_sensitive.py --skip-tools    # 不带 Tools 工具软件
    python scripts/export_sensitive.py --list          # 只列出会导出什么

为什么要单独导出：这些东西**永远不该进 Git**（数据库含业务数据、凭据含手机号
与密码密文、excel 与各业务图片目录含内部资料），但换机器时又必须带着走。
仓库里的 .gitignore 只是"不提交"，不解决"随身带走"。

设计要点：

* **只读源项目**：导出是复制，源文件一个字节都不动。
* **增量**：目标文件与源文件的大小和修改时间都一致就跳过，第二次跑很快
  （Tools 有 600 MB，全量重拷没必要）。
* **镜像项目结构**：备份目录里就是项目根的局部镜像，恢复时整目录覆盖回去即可。
* **Tools 是可选大头**：收集的工具软件约 600 MB，可重新下载，
  所以给了 ``--skip-tools``。
* 结束时写 ``备份清单.txt``（含关键文件 SHA256）与 ``恢复说明.txt``。
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = Path(r"F:\ServerTimeDemo_随身备份")

# 敏感 / 不可重建的数据。相对项目根，目录与文件混排；支持 * 通配。
DATA_PATTERNS = [
    # 运行版（exe 在 dist/ 下，BASE_DIR 就是 dist/）
    "dist/expiry_manager.db*",
    "dist/login_memory.json",
    "dist/remember_me.json",
    "dist/account_images",
    # 源码运行时的数据（仓库根）
    "expiry_manager.db",
    "expiry_manager.db.*",
    "login_memory.json",
    "remember_me.json",
    "study_demo.db",
    "study_notes.db",
    "account_images",
    "process_flow_images",
    "study_notes_images",
    "study_notes_attachments",
    "study_demo",
    "adb_history",
    # 用户在意的表格
    "excel",
    # 真实接口配置（仓库里那份是 example.com 占位符）
    "embedded_admin_tools/config/interfaces.local.json",
    # AI 开发记忆（含项目内部描述，不进公开仓库）
    ".workbuddy",
]

# 体积大但可重新获取：收集的工具软件
TOOLS_PATTERNS = ["Tools"]

# 需要留指纹的关键文件（数据库 / 凭据 / 表格），备份完算一次 SHA256
FINGERPRINT = [
    "dist/expiry_manager.db",
    "expiry_manager.db",
    "dist/login_memory.json",
    "login_memory.json",
    "excel/服务器与云服务到期情况.xlsx",
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


def expand(patterns: list[str]) -> list[Path]:
    """把通配展开成实际存在的路径（相对项目根）。"""
    found: list[Path] = []
    for pat in patterns:
        if any(ch in pat for ch in "*?["):
            found.extend(sorted(ROOT.glob(pat)))
        else:
            p = ROOT / pat
            if p.exists():
                found.append(p)
    # 去重 + 去掉被别的条目包含的子路径（先列目录时容易重复）
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


def export(items: list[Path], dest: Path, stats: Stats) -> list[tuple[str, int, int]]:
    """镜像复制；返回 [(相对路径, 文件数, 字节数)]。"""
    report = []
    for src in items:
        rel = src.relative_to(ROOT)
        target = dest / rel
        n_before, b_before = stats.copied, stats.bytes
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    stats.sync(f, target / f.relative_to(src))
            # 目录自身的文件数单独数一遍，便于写清单
            files = [f for f in src.rglob("*") if f.is_file()]
            report.append((str(rel) + "/", len(files), sum(f.stat().st_size for f in files)))
        else:
            stats.sync(src, target)
            report.append((str(rel), 1, src.stat().st_size))
        _ = (n_before, b_before)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="导出不能进 Git 的敏感数据")
    ap.add_argument("dest", nargs="?", default=str(DEFAULT_DEST), help="目标目录（默认 %(default)s）")
    ap.add_argument("--skip-tools", action="store_true", help="不导出 Tools 工具软件（约 600 MB）")
    ap.add_argument("--list", action="store_true", help="只列出会导出什么，不复制")
    args = ap.parse_args()

    dest = Path(args.dest)
    patterns = list(DATA_PATTERNS) + ([] if args.skip_tools else TOOLS_PATTERNS)
    items = expand(patterns)

    if not items:
        print("没有找到任何可导出的数据 —— 确认脚本是在项目根下的 scripts/ 里运行。")
        return 1

    print(f"项目根 : {ROOT}")
    print(f"目标目录: {dest}")
    print("-" * 70)
    total_files, total_bytes = 0, 0
    listing = []
    for p in items:
        if p.is_dir():
            fs = [f for f in p.rglob("*") if f.is_file()]
            n, b = len(fs), sum(f.stat().st_size for f in fs)
        else:
            n, b = 1, p.stat().st_size
        total_files += n
        total_bytes += b
        listing.append((str(p.relative_to(ROOT)), n, b))
        print(f"  {str(p.relative_to(ROOT)):<52} {n:>5} 个文件  {human(b):>10}")
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
        f"来源项目: {ROOT}",
        f"备份目录: {dest}",
        "",
        "这些内容**故意不进 Git**（数据库含业务数据、凭据含手机号与密码密文、",
        "excel 与业务图片目录含内部资料）。换机器时把它们放回项目对应位置即可。",
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
    for rel in FINGERPRINT:
        f = ROOT / rel
        if f.exists():
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
        "1. 先拿到代码（GitHub 公开仓库）：",
        "       git clone https://github.com/22902902/ServerTimeDemo.git",
        "",
        "2. 把本备份目录里的内容，按原来的相对位置复制回项目根目录：",
        "       dist\\expiry_manager.db*        -> 项目根\\dist\\",
        "       dist\\login_memory.json         -> 项目根\\dist\\",
        "       dist\\account_images\\           -> 项目根\\dist\\",
        "       expiry_manager.db 等根级数据库  -> 项目根\\",
        "       excel\\                         -> 项目根\\",
        "       Tools\\                         -> 项目根\\  （exe 还要用的话再复制一份到 dist\\Tools\\）",
        "       embedded_admin_tools\\config\\interfaces.local.json -> 对应位置",
        "   （本备份就是项目根的局部镜像，直接整目录覆盖合并过去即可。）",
        "",
        "3. 装上 Python 3.12（Tkinter 要真实窗口，便携版没带），然后：",
        "       pip install -r requirements.txt",
        "       python main.py",
        "   或者直接用 dist\\ExpiryManager_fixed.exe。",
        "",
        "4. 用「备份清单.txt」里的 SHA256 核对关键文件是否拷全。",
        "",
        "注意：",
        "* 没纳入备份的 ExpiryManager_Data\\ 是早期数据目录的残留，",
        "  程序和它没关系（现在认的是项目根 / dist\\），需要的话手工复制。",
        "* Tools\\ 是可重新下载的工具软件，体积大；不带它也能正常用程序。",
    ]
    (dest / "恢复说明.txt").write_text("\n".join(restore), encoding="utf-8")

    print(f"清单已写入: {dest / '备份清单.txt'}")
    print(f"说明已写入: {dest / '恢复说明.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
