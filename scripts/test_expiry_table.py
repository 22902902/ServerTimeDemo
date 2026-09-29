# -*- coding: utf-8 -*-
"""到期表格「单元格收敛」回归测试。

背景：库里的「资源详情」可能是多行的（一行一个 IP、一行一个配置），
直接塞进 ttk.Treeview 会把行撑高、文字溢出到相邻列，整张表看着是散的。
现在的策略是：表格里只给「一行摘要」，完整内容交给「详情」弹窗。

本测试锁定两件事：

A. 纯函数层
   - 换行折成分隔符；空值/纯空白安全
   - 放得下就原样返回，放不下就「逐段保留 + 省略号」
   - 关键性质：**不从一段数值中间截断**（否则会出现「（vCPU）1…」这种残句）
   - 返回结果绝不含换行，且实测像素宽不超过该列宽度

B. 真实表格层（构造真实主窗口）
   - 无条件跳过可选库：逐行逐格断言「不含换行」
   - 库里确实存在多行记录的列，其摘要必须以 … 结尾，且首段完整保留
   - 用 Treeview 实际字体量宽，确认没有单元格超出列宽

用法：
    python scripts/test_expiry_table.py
"""

import sqlite3
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import expiry_page  # noqa: E402
from expiry_page import (  # noqa: E402
    compact_cell_text,
    ellipsize_px,
    split_cell_chunks,
    summarize_cell_text,
    treeview_font,
)


PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


# 取自库内 assets.resource_detail 的样本（IP / 域名已脱敏为占位值）
REAL_MULTILINE = "IP：203.0.113.45\n配置：4 核（vCPU）16 GiB10 Mbps"
REAL_DOMAINS = "samplehost001.com \nwww.samplehost001.com"
REAL_ONE_LINE = "www.demo001.com、demo001.com"

FAKE_META = {
    "resource_detail": {"title": "资源详情", "width": 280},
    "narrow": {"title": "窄列", "width": 40},
    "note": {"title": "备注", "width": 220},
}


def test_pure_functions(root):
    print("\n[A] 纯函数层")

    check("split: 单行 → 一段", split_cell_chunks(REAL_ONE_LINE) == [REAL_ONE_LINE])
    check("split: 两行 → 两段", split_cell_chunks(REAL_MULTILINE) ==
          ["IP：203.0.113.45", "配置：4 核（vCPU）16 GiB10 Mbps"])
    check("split: CRLF 与多余空白被吃掉",
          split_cell_chunks("a\r\n\r\n  b  \r\n") == ["a", "b"])
    check("split: None → 空列表", split_cell_chunks(None) == [])
    check("split: 纯空白 → 空列表", split_cell_chunks("  \n \n ") == [])

    check("compact: 换行折成分隔符",
          compact_cell_text(REAL_MULTILINE) ==
          "IP：203.0.113.45 · 配置：4 核（vCPU）16 GiB10 Mbps")
    check("compact: 空值 → 空串", compact_cell_text(None) == "")

    font = tk.font.nametofont("TkDefaultFont")

    # 放得下 → 原样
    short = summarize_cell_text(REAL_ONE_LINE, "resource_detail",
                               column_meta=FAKE_META, font=font)
    check("summary: 放得下时原样返回", short == REAL_ONE_LINE, f"实际 {short!r}")

    # 放不下 → 丢整段 + 省略号，首段完整
    got = summarize_cell_text(REAL_MULTILINE, "resource_detail",
                              column_meta=FAKE_META, font=font)
    check("summary: 放不下时首段完整保留", got.startswith("IP：203.0.113.45"),
          f"实际 {got!r}")
    check("summary: 放不下时以省略号收尾", got.endswith("…"), f"实际 {got!r}")
    check("summary: 没有把第二段从中间截断",
          "（vCPU）1…" not in got and "配置：4 核" not in got, f"实际 {got!r}")

    got_dom = summarize_cell_text(REAL_DOMAINS, "resource_detail",
                                  column_meta=FAKE_META, font=font)
    check("summary: 域名用例保留第一段",
          got_dom.startswith("samplehost001.com"), f"实际 {got_dom!r}")

    # 连第一段都放不下 → 退化为按像素截断（此时允许切开）
    got_tiny = summarize_cell_text(REAL_MULTILINE, "narrow",
                                   column_meta=FAKE_META, font=font)
    check("summary: 极窄列退化为字符截断并加省略号",
          got_tiny.endswith("…") and font.measure(got_tiny) <= 40 - 14,
          f"实际 {got_tiny!r} 宽 {font.measure(got_tiny)}")

    # 列宽未知 → 至少保证是单行
    got_unknown = summarize_cell_text(REAL_MULTILINE, "没有这一列",
                                      column_meta=FAKE_META, font=font)
    check("summary: 未知列名只做单行化、不截断",
          "\n" not in got_unknown and got_unknown == compact_cell_text(REAL_MULTILINE),
          f"实际 {got_unknown!r}")

    check("summary: 空值 → 空串",
          summarize_cell_text("", "resource_detail", column_meta=FAKE_META, font=font) == "")

    # 宽度不越界（对所有真实取值）
    over = []
    for value in (REAL_MULTILINE, REAL_DOMAINS, REAL_ONE_LINE):
        for column in ("resource_detail", "note"):
            text = summarize_cell_text(value, column, column_meta=FAKE_META, font=font)
            limit = FAKE_META[column]["width"] - expiry_page.CELL_TEXT_PADDING
            if font.measure(text) > limit:
                over.append((column, text, font.measure(text), limit))
    check("summary: 所有用例宽度都不越界", not over, f"越界 {over}")

    # ellipsize 自身
    check("ellipsize: 放得下不动", ellipsize_px("abc", 999, font=font) == "abc")
    check("ellipsize: 极窄时只留省略号", ellipsize_px("abcdef", 3, font=font) == "…")


def test_real_table():
    print("\n[B] 真实表格层")

    if not (ROOT / "expiry_manager.db").exists():
        check("数据库存在（缺失则跳过表格层）", True, "已跳过")
        return

    import main

    main.ExpiryManagerApp.prompt_login = lambda self: None
    main.ExpiryManagerApp.poll_external_commands = lambda self: None
    main.ExpiryManagerApp.startup_sequence = lambda self: None

    app = main.ExpiryManagerApp()
    app.withdraw()
    app.nav.select("module_ops_expiry", notify=True)
    app.update_idletasks()
    app.refresh_table()
    app.update_idletasks()

    tree = app.tree
    rows = list(tree.get_children())
    check("表格已填充记录", len(rows) > 0, f"rows={len(rows)}")
    if not rows:
        app.destroy()
        return

    font = treeview_font(tree)
    columns = list(tree["columns"])

    # 1) 任何单元格都不含换行 —— 这是「每行等高」的前提
    offenders = []
    for iid in rows:
        values = tree.item(iid, "values")
        for index, value in enumerate(values):
            if "\n" in str(value) or "\r" in str(value):
                offenders.append((columns[index], str(value)[:40]))
    check("所有单元格都是单行（无换行符）", not offenders, f"越界单元格 {offenders[:3]}")

    # 2) 宽度不越界
    over = []
    for iid in rows:
        values = tree.item(iid, "values")
        for index, value in enumerate(values):
            column = columns[index]
            width = main.COLUMN_META.get(column, {}).get("width", 0)
            if not width or not str(value):
                continue
            measured = font.measure(str(value))
            if measured > width:
                over.append((column, measured, width, str(value)[:30]))
    check("没有单元格超出其列宽", not over, f"超宽 {over[:3]}")

    # 3) 逐行核对摘要：首段必须完整保留，被截断就必须有可见省略号
    #    注意 record_no 不唯一（多条记录共用 No-000-001），必须用主键 id 对应
    conn = sqlite3.connect(str(ROOT / "expiry_manager.db"))
    conn.row_factory = sqlite3.Row
    try:
        raw_by_id = {
            r["id"]: (r["resource_detail"] or "")
            for r in conn.execute("SELECT id, resource_detail FROM assets")
        }
    finally:
        conn.close()

    id_index = columns.index("id")
    detail_index = columns.index("resource_detail")

    multi_count = sum(1 for v in raw_by_id.values() if "\n" in v or "\r" in v)
    check("库内确实存在多行资源详情（否则本项断言没有意义）",
          multi_count > 0, f"多行记录数 {multi_count}")

    misses = []
    checked = 0
    for iid in rows:
        values = tree.item(iid, "values")
        try:
            row_id = int(values[id_index])
        except (TypeError, ValueError):
            misses.append((values[id_index], "表格中的 id 不是整数"))
            continue
        raw_value = raw_by_id.get(row_id)
        if raw_value is None:
            misses.append((row_id, "表格里的 id 在库里查不到"))
            continue
        checked += 1
        summary = str(values[detail_index])
        chunks = expiry_page.split_cell_chunks(raw_value)
        if not chunks:
            if summary:
                misses.append((row_id, summary, "库内为空、表里却有值"))
            continue
        if not summary.startswith(chunks[0]):
            misses.append((row_id, summary, f"首段应为 {chunks[0]!r}"))
        elif summary != expiry_page.compact_cell_text(raw_value) and not summary.endswith("…"):
            misses.append((row_id, summary, "已截断但缺少省略号"))

    check(f"逐行核对 {checked} 条记录的摘要（首段完整 + 截断可见）",
          checked == len(rows) and not misses, f"问题 {misses[:3]}")

    app.destroy()


def main_test():
    print("=" * 78)
    print("到期表格单元格收敛：纯函数 + 真实表格")
    print("=" * 78)

    root = tk.Tk()
    root.withdraw()
    try:
        test_pure_functions(root)
    finally:
        # 必须先销毁：同进程内存在两个 Tk 根会让 TkinterDnD 主窗口的
        # PhotoImage 报 "image pyimage1 doesn't exist"
        root.destroy()

    test_real_table()


if __name__ == "__main__":
    try:
        main_test()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILED += 1

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
