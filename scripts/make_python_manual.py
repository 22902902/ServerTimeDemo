# -*- coding: utf-8 -*-
"""生成《Python 语法手册（配 ServerTimeDemo 项目实例）》PDF。

用法::

    # 1) 先把测试基线跑出来（手册附录 B 要引用它）
    python scripts/run_all_tests.py --json build/manual/test_baseline.json

    # 2) 生成 PDF
    python scripts/make_python_manual.py

为什么手册没写在 app 里
------------------------------------------------------------------------------
手册是本项目的**说明文档**，不进 exe（spec 的 datas 只带 app.ico），
所以它不占用发布包体积。生成它需要 reportlab，而 reportlab 只在开发环境装：
`ExpiryManager_fixed.spec` 里没有任何 reportlab 或手册相关模块。

三个文件是怎么分工的
------------------------------------------------------------------------------
* `scripts/manual_content_a.py`  正文第一 ~ 七章
* `scripts/manual_content_b.py`  正文第八章 ~ 附录
* `scripts/manual_engine.py`     排版引擎（字体、样式、目录、代码高亮）
* 本文件                        把上面三者接起来 + 现算统计数字

统计数字（文件数、行数、模块清单、测试基线）**一律现算**，
不写死在正文里 —— 那样改一次代码就得手工同步一遍，迟早对不上。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import manual_content_a          # noqa: E402
import manual_content_b          # noqa: E402
import manual_engine             # noqa: E402

DEFAULT_OUT = ROOT / "docs" / "Python语法手册.pdf"
BASELINE_JSON = ROOT / "build" / "manual" / "test_baseline.json"

# 统计范围：根目录业务模块、内置工具包、开发脚本
SCOPE = [
    ("根目录", ROOT, "*.py"),
    ("embedded_admin_tools", ROOT / "embedded_admin_tools", "**/*.py"),
    ("scripts", ROOT / "scripts", "*.py"),
]


# 统计时不纳入的文件：手册自己的正文数据（是文字不是代码，算进「项目行数」
# 会把统计口径搞糊），以及 `_` 开头的临时脚本。
SKIP_NAMES = ("manual_content_a.py", "manual_content_b.py")


def _py_files(base: Path, pattern: str):
    """列出参与统计的 .py 文件：跳过临时脚本、本手册正文数据与生成物目录。"""
    skip_dirs = {"build", "dist", "__pycache__", ".git", ".workbuddy"}
    out = []
    for p in sorted(base.glob(pattern)):
        if p.name.startswith("_") or p.name in SKIP_NAMES:
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        out.append(p)
    return out


def collect_stats():
    """现算各区域的文件数与行数。"""
    rows = []
    for label, base, pattern in SCOPE:
        files = _py_files(base, pattern)
        lines = sum(len(p.read_bytes().split(b"\n")) for p in files)
        rows.append((label, files, lines))
    return rows


def build_module_table():
    """扫源码生成「模块 → 职责」表。

    职责取各模块 docstring 里第一行既非空、也不是分隔线的文字；
    取不到就写「（无模块 docstring）」。行数 / 类数 / 函数数也用 AST 现数。
    """
    entries = []
    for label, base, pattern in SCOPE:
        for path in _py_files(base, pattern):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            doc = ast.get_docstring(tree) or ""
            summary = ""
            for line in doc.splitlines():
                line = line.strip()
                if line and not set(line) <= set("=-—─"):
                    summary = line
                    break
            lines = len(path.read_bytes().split(b"\n"))
            nclass = sum(isinstance(n, ast.ClassDef) for n in tree.body)
            nfunc = sum(isinstance(n, ast.FunctionDef) for n in tree.body)
            where = "" if label == "根目录" else label + "/"
            entries.append({
                "file": where + path.name,
                "summary": summary or "（无模块 docstring）",
                "lines": lines,
                "nclass": nclass,
                "nfunc": nfunc,
            })

    entries.sort(key=lambda e: -e["lines"])
    rows = [["模块", "行数", "类", "函数", "职责"]]
    for e in entries:
        rows.append([f"`{e['file']}`", str(e["lines"]), str(e["nclass"]),
                     str(e["nfunc"]), e["summary"]])
    return rows


def build_test_table():
    """读测试基线 JSON 生成表；没有就返回一张「怎么生成它」的说明表。"""
    if not BASELINE_JSON.exists():
        return [
            ["套件", "通过", "失败"],
            ["（还没有测试基线）", "—", "先跑一次：",
             ],
        ], None

    data = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    rows = [["套件", "通过", "失败"]]
    for item in data["suites"]:
        rows.append([f"`{item['name']}`", str(item["passed"]), str(item["failed"])])
    rows.append(["**合计**", f"**{data['total_passed']}**",
                 f"**{data['total_failed']}**"])
    return rows, data


def _sub_tokens(obj, tokens):
    """递归做 token 替换。

    必须递归：``table`` 块的单元格是「列表里套列表」，只扫顶层元组的字符串
    就会漏掉它们 —— 表现是页面上直接印出 ``{n_root}`` 这样的占位符原文。
    只替换明确列出的 token，不用 ``str.format``（正文里有大量 f-string 花括号）。
    """
    if isinstance(obj, str):
        for token, value in tokens.items():
            if token in obj:
                obj = obj.replace(token, value)
        return obj
    if isinstance(obj, list):
        return [_sub_tokens(x, tokens) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_sub_tokens(x, tokens) for x in obj)
    return obj


def _assert_no_placeholders(blocks, tokens):
    """展开完还留着的**已知占位符**一律当成错误，别让它印到纸上。

    踩过一次：``table`` 的单元格是「列表套列表」，早期实现只扫顶层元组里的
    字符串，于是页面上真的印出了 ``{n_root}``。与其靠人工翻页发现，
    不如在这里硬失败。

    只认 ``tokens`` 里列出的名字 —— 代码样例里的 ``{name}`` / ``{key}`` 是
    合法的 f-string，不能一起误伤。
    """
    leftover = []

    def walk(obj, where):
        if isinstance(obj, str):
            for token in tokens:
                if token in obj:
                    leftover.append((where, token))
        elif isinstance(obj, (list, tuple)):
            for x in obj:
                walk(x, where)

    for i, block in enumerate(blocks):
        walk(block, f"块 #{i}（{block[0]}）")
    if leftover:
        detail = "、".join(f"{w} 里的 {t}" for w, t in leftover[:10])
        raise SystemExit(f"有占位符没被替换：{detail}")


def _token_map(stats):
    """现算出来的数字 -> 正文里的 ``{token}``。"""
    by_label = {label: (len(files), lines) for label, files, lines in stats}
    n_root, l_root = by_label["根目录"]
    n_emb, l_emb = by_label["embedded_admin_tools"]
    n_scr, l_scr = by_label["scripts"]
    return {
        "{n_root}": f"{n_root} 个",
        "{n_emb}": f"{n_emb} 个",
        "{n_scr}": f"{n_scr} 个",
        "{n_all}": str(n_root + n_emb + n_scr),
        "{n_lines}": f"{l_root + l_emb + l_scr:,}",
    }


def expand(blocks, stats, base_data):
    """把占位块与 `{token}` 换成现算的内容。"""
    tokens = _token_map(stats)

    out = []
    for block in blocks:
        kind = block[0]
        if kind == "module_table":
            out.append(("table", build_module_table()))
            continue
        if kind == "test_table":
            out.append(("table", build_test_table()[0]))
            continue
        out.append(_sub_tokens(block, tokens))
    return out


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="生成 Python 语法手册 PDF")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"输出 PDF 路径（默认 {DEFAULT_OUT}）")
    parser.add_argument("--app-version", default=None,
                        help="封面显示的应用程序版本号（默认读 app_version.py）")
    parser.add_argument("--manual-version", default="1.0", help="手册自身版本号")
    args = parser.parse_args(argv)

    app_version = args.app_version
    if app_version is None:
        text = (ROOT / "app_version.py").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("APP_VERSION"):
                app_version = line.split("=", 1)[1].strip().strip("\"'")
                break
        app_version = app_version or "未知"

    stats = collect_stats()
    total_files = sum(len(f) for _, f, _ in stats)
    total_lines = sum(l for _, _, l in stats)
    _, base_data = build_test_table()

    # 数据库表数：直接数一次（数据库不存在时写「—」）
    n_tables = "—"
    db = ROOT / "ExpiryManager_Data" / "expiry_manager.db"
    if db.exists():
        import sqlite3
        conn = sqlite3.connect(str(db))
        try:
            n_tables = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'").fetchone()[0]
        finally:
            conn.close()

    today = datetime.now().strftime("%Y 年 %m 月 %d 日")
    meta = {
        "title": "Python 语法手册",
        "author": "代可行",
        "subject": "Python 语法参考，配 ServerTimeDemo 项目实例",
        "creator": "scripts/make_python_manual.py",
        "header_right": f"项目 {app_version} · 手册 {args.manual_version}",
        "app_version": app_version,
        "manual_version": args.manual_version,
        "date": today,
        "stat_files": total_files,
        "stat_lines": f"{total_lines:,}",
        "stat_tables": n_tables,
    }

    blocks = expand(
        list(manual_content_a.BLOCKS) + list(manual_content_b.BLOCKS),
        stats, base_data)
    _assert_no_placeholders(blocks, _token_map(stats))

    out_path = manual_engine.build(blocks, Path(args.out), meta)

    print("手册已生成")
    print(f"  输出      {out_path}")
    print(f"  体量      {out_path.stat().st_size / 1024:.0f} KB")
    print(f"  统计      {total_files} 个文件 / {total_lines:,} 行 / {n_tables} 张表")
    print(f"  代码块    {sum(1 for b in blocks if b[0] == 'code')} 个")
    print(f"  表格      {sum(1 for b in blocks if b[0] == 'table')} 张")
    print(f"  插图      {sum(1 for b in blocks if b[0] == 'image')} 张")
    if not BASELINE_JSON.exists():
        print("  注意      没有测试基线，附录 B 是空的。先跑：")
        print("            python scripts/run_all_tests.py "
              "--json build/manual/test_baseline.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
