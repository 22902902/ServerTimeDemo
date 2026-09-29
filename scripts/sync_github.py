#!/usr/bin/env python3
"""把本地改动同步到 GitHub（提交 + 推送），并做公开仓库的安全体检。

用法：
    python scripts/sync_github.py                     # 看状态：哪些没提交、哪些没推送
    python scripts/sync_github.py --audit             # 全量体检：扫所有已跟踪文件
    python scripts/sync_github.py -m "提交说明"        # 提交全部改动并推送
    python scripts/sync_github.py -m "..." --dry-run
    python scripts/sync_github.py -m "..." --force     # 越过安全闸（慎用）

为什么要有个脚本，而不是随手 git push：

1. 这个仓库旁边躺着数据库、登录凭据、excel 和业务图片。.gitignore 排除了
   它们，但忽略规则是"能被改坏"的东西 —— 哪天不小心删了一行，一次
   git add -A 就会把真实数据推上公网。所以这里加第二道闸：提交前逐个检查
   待提交文件，命中敏感特征直接拒绝。

2. 光查文件名不够。真实 IP、客户域名、业务串会藏在**测试样本和注释**里
   （本仓库就发生过：从库里抄了 IP 与域名当测试用例）。所以还要扫内容。

3. 只推 main。本地在别的分支上说明你在做实验，不该顺手推上去。

4. 推送后复核远端 HEAD 与本地一致，避免"以为推上去了其实没有"。

注意：内容扫描用的是 Python re（Unicode 感知）。别用 `git grep '\\b...'`
去扫多字节相邻的串 —— git grep 的 \\b 不认多字节字符，而中文全角冒号
`IP：203.0.113.45` 前面正好是全角冒号，会被判成"没有边界"而整条漏掉。
本文件上一版就因此漏报了真实 IP。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"

# ---------------------------------------------------------------- 文件名红线
FORMIDDEN_NAME = (
    (r"\.(db|db3|sqlite3?)$", "数据库"),
    (r"\.(xlsx?|xlsm|xls|csv|tsv)$", "表格"),
    (r"\.(png|jpe?g|gif|bmp|webp)$", "图片"),
    (r"^login_memory\.json$", "登录凭据"),
    (r"^remember_me\.json$", "登录凭据"),
    (r"interfaces\.local\.json$", "真实接口地址"),
    (r"^\.workbuddy/", "AI 工作记忆"),
    (r"^dist/", "打包产物"),
    (r"^build/", "构建中间件"),
    (r"^Tools/|^excel/", "工具软件与业务表格"),
    (r"^account_images/|^process_flows/", "业务图片"),
    (r"^adb_history/|^study_notes_images/|^study_notes_attachments/", "运行时数据"),
)

# ---------------------------------------------------------------- 内容红线
# 1) 显式的业务串（脱敏一旦被破坏就会命中）
CONTENT_NEEDLES = ("needle-1", "needle-2", "needle-3", "needle-4", "needle-5")

# 2) 公网 IP：私有段 / 回环 / 链路本地 / 文档保留段放行，其余当真实资产拦下
IP_RE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
IP_ALLOW_RE = re.compile(
    r"^(?:"
    r"0\.|127\.|10\.|192\.168\.|169\.254\.|255\.|"
    r"172\.(?:1[6-9]|2[0-9]|3[01])\.|"
    r"203\.0\.113\.|198\.51\.100\.|192\.0\.2\."   # RFC 5737 文档保留段
    r")"
)

# 3) 域名：只放行示例域与公共基础设施，别的都算"真实业务域名"
DOMAIN_RE = re.compile(
    r"(?<![A-Za-z0-9.-])"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:com|cn|net|org|io|com\.cn)"
    r"(?![A-Za-z0-9.-])"
)
DOMAIN_ALLOW_SUFFIX = (
    "example.com", "example.org", "example.net",
    "localhost",
    # 示例/种子数据里用的假域名（Excel 教程的邮箱例子、模板变量测试值）
    "abc.com", "a.com", "x.com",
    # 本仓库统一使用的脱敏占位域名（见 build/patch_sanitize_real_data.py）
    "samplehost001.com", "demo001.com",
    # 公共基础设施
    "github.com", "githubusercontent.com",
    "python.org", "pypi.org", "pythonhosted.org", "readthedocs.io",
    "baidu.com", "qq.com", "weixin.qq.com",
    "w3.org", "gnu.org", "microsoft.com",
)

TEXT_EXT = (".py", ".md", ".json", ".spec", ".txt", ".bat", ".ps1",
            ".cfg", ".toml", ".lock", ".yml", ".yaml", ".ini")
MAX_SCAN_BYTES = 2_000_000


def git(*args: str) -> tuple[int, str]:
    """跑一条 git 命令，返回 (退出码, 去掉尾部空白的 stdout+stderr)。"""
    p = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def changed_files() -> list[str]:
    """待提交的文件（含未跟踪），已删的不算。"""
    code, out = git("status", "--porcelain", "-z")
    if code != 0:
        return []
    names: list[str] = []
    for item in out.split("\0"):
        if len(item) < 4:
            continue
        status, path = item[:2], item[3:]
        if status.strip() == "D":
            continue
        names.append(path.replace("\\", "/"))
    return names


def tracked_files() -> list[str]:
    code, out = git("ls-files")
    return [x.replace("\\", "/") for x in out.splitlines() if x.strip()] if code == 0 else []


def _audit_text(rel: str) -> list[str]:
    """扫一个文本文件的内容，返回问题描述列表。"""
    p = ROOT / rel
    if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
        return []
    try:
        if p.stat().st_size > MAX_SCAN_BYTES:
            return []
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    hits: list[str] = []
    for needle in CONTENT_NEEDLES:
        if needle in text:
            hits.append(f"{rel}  <- 含业务串 {needle!r}")
    for ip in {m.group(0) for m in IP_RE.finditer(text)}:
        if not IP_ALLOW_RE.match(ip):
            hits.append(f"{rel}  <- 含公网 IP {ip}")
    for dom in {m.group(0) for m in DOMAIN_RE.finditer(text)}:
        d = dom.lower()
        if not any(d == s or d.endswith("." + s) for s in DOMAIN_ALLOW_SUFFIX):
            hits.append(f"{rel}  <- 含域名 {dom}")
    return hits


def name_guard(files: list[str]) -> list[str]:
    bad: list[str] = []
    for f in files:
        for pattern, why in FORMIDDEN_NAME:
            if re.search(pattern, f, re.IGNORECASE):
                bad.append(f"{f}  <- {why}")
                break
    return bad


def content_guard(files: list[str]) -> list[str]:
    out: list[str] = []
    for f in files:
        out.extend(_audit_text(f))
    return out


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def run_audit(files: list[str], label: str) -> int:
    """跑安全体检。返回 0 通过 / 2 有问题。"""
    print_section("安全体检")
    print(f"  范围：{label}（{len(files)} 个文件）")
    bad = name_guard(files)
    content = content_guard(files)
    if bad or content:
        print("  × 拒绝。下列文件不该进公开仓库：")
        for line in bad + content:
            print(f"      {line}")
        print("\n  确认无误就加 --force；更该做的是修 .gitignore 或脱敏。")
        return 2
    print("  ✓ 通过：无敏感文件名、无业务串、无公网 IP、无未放行域名")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="提交并推送改动到 GitHub")
    ap.add_argument("-m", "--message", help="提交说明；给了就先提交再推送")
    ap.add_argument("--audit", action="store_true", help="全量体检所有已跟踪文件")
    ap.add_argument("--dry-run", action="store_true", help="只演示，不真的提交/推送")
    ap.add_argument("--force", action="store_true", help="跳过安全体检（危险）")
    args = ap.parse_args()

    code, branch = git("branch", "--show-current")
    if code != 0 or branch != BRANCH:
        print(f"× 当前分支是 {branch or '(取不到)'}，本脚本只推 {BRANCH}。")
        print("  确实要推这个分支，就手动 git push -u origin <分支>。")
        return 1

    if args.audit:
        return run_audit(tracked_files(), "全部已跟踪文件")

    files = changed_files()

    print_section("待提交的改动")
    if files:
        for f in files:
            print(f"  M {f}")
    else:
        print("  (无 —— 工作区干净)")

    if files and not args.force:
        rc = run_audit(files, "本次待提交")
        if rc != 0:
            return rc
    elif files:
        print_section("安全体检")
        print("  ⚠ --force：已跳过（风险自负）")

    if args.message:
        if not files:
            print("\n没有要提交的改动，跳过提交。")
        elif args.dry_run:
            print(f"\n[dry-run] 会执行：git add -A && git commit -m {args.message!r}")
        else:
            code, out = git("add", "-A")
            if code != 0:
                print(f"× git add 失败：{out}")
                return 1
            code, out = git("commit", "-m", args.message)
            print(f"\n{out}")
            if code != 0:
                print("× 提交失败。")
                return 1
    elif files:
        print('\n（改了东西但没给 -m，所以只报告、不提交。要提交就加 -m "说明"）')

    code, ahead = git("rev-list", "--count", f"origin/{BRANCH}..HEAD")
    ahead_n = int(ahead) if code == 0 and ahead.isdigit() else -1

    print_section("推送")
    if args.dry_run:
        print(f"  [dry-run] 待推送 {ahead_n} 个提交")
        return 0
    if ahead_n == 0:
        print("  ✓ 远端已是最新，无需推送")
    else:
        code, out = git("push", "-u", "origin", BRANCH)
        print(f"  {out}" if out else "  (无输出)")
        if code != 0:
            print("× 推送失败。先确认 SSH 可用：ssh -T git@github.com")
            return 1

    print_section("复核")
    _, local_head = git("rev-parse", "HEAD")
    _, remote = git("ls-remote", "origin", f"refs/heads/{BRANCH}")
    remote_head = remote.split()[0] if remote else "(取不到)"
    ok = bool(local_head) and local_head == remote_head
    print(f"  本地 {local_head[:12]}   远端 {remote_head[:12]}   {'✓ 一致' if ok else '× 不一致'}")
    if ok:
        print("  https://github.com/22902902/ServerTimeDemo")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
