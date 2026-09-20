# -*- coding: utf-8 -*-
"""系统工具箱「启动器」回归测试。

背景：工具箱是用户最常用的功能，工具一多就有三个具体痛点 ——
  1. 进页面不知道该干嘛：老版占两行工具栏，但没有任何输入焦点
  2. 名字撞车分不清：库里有 3 个 putty、2 个 simplewall、2 个 DiskGenius
  3. 收藏形同虚设：功能存在，但按钮藏在右侧面板里，用户库里 0 个收藏

本测试锁定：

A. 纯函数层（tools_launcher，不依赖窗口）
   - 模糊匹配的分档顺序：完全相等 > 前缀 > 词首 > 子串 > 子序列
   - 排序稳定、空查询保持原序、不命中即为空
   - 副标题消歧：**同一重名组内的副标题必须两两不同**（否则等于没提示）
   - 收藏 / 最近使用 / 时长条标签

B. 真实窗口层（构造真实 ToolsPage，跑在库的副本上）
   - 卡片铺满、分类 chip 不出现空分类
   - 卡片内容不溢出卡片（标题最多两行）
   - 即输即搜：搜 "dkgn" 能搜到 DiskGenius；回车启动第一条命中
   - ↑↓ 移动光标；星标收藏落库并进「收藏」横条
   - 启动后进「最近使用」横条
   - 命令条按钮不含 emoji、且走「悬停才浮底」的 Toolbar.TButton
   - 分类 / 快捷条用的是自绘圆角胶囊，不带原生 1px 边框
   - 圆角底图的半径是真的（Pillow 超采样），不是 smooth 多边形那种「只切 1px」
   - 回归修复：「带参数 + 不提权」不再 NameError

C. 图标抽取（真实 exe）
   - 老图标 alpha 全 0 时能从 AND 蒙版推出透明度（PuTTY 0.6x / 屏幕吸色器踩过）
   - 全透明的空 PNG 会被判定为不可用，坏缓存删掉重抽
   - 确实没有图标的文件返回 False、不留垃圾，并进负缓存避免反复重试

用法：
    python scripts/test_tools_launcher.py
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import time
import types
import tkinter as tk
from tkinter import ttk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import tools_db  # noqa: E402
import tools_launcher as launcher  # noqa: E402
import app_icons  # noqa: E402
from tools_page import ToolsPage  # noqa: E402
from ui_components import RoundedChip, rounded_rect_image  # noqa: E402
from ui_theme import THEME, TOOLBOX_PALETTE  # noqa: E402


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


def make_tool(tool_id, name, path, **kwargs):
    """构造一条工具记录（字段与 tool_items 表对齐）。"""
    row = {
        "id": tool_id, "name": name, "alias": "", "path": path,
        "category": "未分类", "icon_path": "", "args": "",
        "run_as_admin": 0, "is_favorite": 0, "is_deleted": 0,
        "last_run_at": "", "run_count": 0,
    }
    row.update(kwargs)
    return row


# 与库内真实情况一致的重名样例（3 个 putty、2 个 simplewall 等）
SAMPLE = [
    make_tool(5, "8uftp", "FTP/8uftp/8uftp.exe", category="FTP"),
    make_tool(11, "simplewall", "网络/simplewall防火墙X32/simplewall.exe",
              alias="simplewall防火墙", category="网络"),
    make_tool(14, "simplewall", "网络/simplewall防火墙X64/simplewall.exe",
              alias="simplewall防火墙", category="网络"),
    make_tool(26, "DiskGenius", "工具包/DiskGenius.exe", category="工具包"),
    make_tool(39, "DiskGenius", "硬盘分区/DiskGenius/DiskGenius.exe",
              category="硬盘分区"),
    make_tool(27, "mstsc", "C:/Windows/System32/mstsc.exe",
              category="系统工具", run_as_admin=1),
    make_tool(29, "cmd", "C:/Windows/System32/cmd.exe", category="系统工具"),
    make_tool(30, "屏幕吸色器", "未分类/屏幕吸色器.exe", category="未分类"),
    make_tool(35, "屏幕吸色器", "工具包/屏幕吸色器.exe", category="工具包"),
    make_tool(32, "putty", "工具包/putty.exe", category="工具包", is_favorite=1),
    make_tool(33, "PuTTY_0.67.0.0", "工具包/PuTTY_0.67.0.0.exe",
              category="工具包", last_run_at="2026-09-19 10:00:00"),
    make_tool(34, "putty_V0.63.LinuxProbe.Com", "工具包/putty_V0.63.LinuxProbe.Com.exe",
              category="工具包", last_run_at="2026-09-20 11:00:00"),
]


# ---------------------------------------------------------------------------
# A. 纯函数层
# ---------------------------------------------------------------------------

def test_fuzzy_scoring():
    print("\n[A1] 模糊匹配分档与排序")

    exact = launcher.fuzzy_score("diskgenius", "DiskGenius")
    prefix = launcher.fuzzy_score("disk", "DiskGenius")
    word = launcher.fuzzy_score("genius", "Disk Genius")
    substring = launcher.fuzzy_score("geni", "DiskGenius")
    subsequence = launcher.fuzzy_score("dkgn", "DiskGenius")

    check("五个分档都命中", None not in
          (exact, prefix, word, substring, subsequence))
    check("分档顺序 相等 > 前缀 > 词首 > 子串 > 子序列",
          exact > prefix > word > substring > subsequence > 0,
          f"exact={exact} prefix={prefix} word={word} "
          f"substr={substring} subseq={subsequence}")

    check("大小写不敏感", launcher.fuzzy_score("CMD", "cmd") == launcher.SCORE_EXACT)
    check("完全不命中返回 None", launcher.fuzzy_score("zzz", "cmd") is None)
    check("字符顺序不对也不算命中（不是集合匹配）",
          launcher.fuzzy_score("dc", "cmd") is None)
    check("空查询返回 0", launcher.fuzzy_score("", "cmd") == 0)


def test_ranking():
    print("\n[A2] rank_tools 排序行为")

    check("空查询保持原顺序",
          [t["id"] for t in launcher.rank_tools(SAMPLE, "")] ==
          [t["id"] for t in SAMPLE])

    check("空格查询也视为空查询",
          [t["id"] for t in launcher.rank_tools(SAMPLE, "   ")] ==
          [t["id"] for t in SAMPLE])

    hits = launcher.rank_tools(SAMPLE, "putty")
    check("搜 putty 命中 3 个变体", len(hits) == 3, f"命中 {[t['name'] for t in hits]}")
    check("完全同名的排第一", hits and hits[0]["name"] == "putty",
          f"实际第一：{hits[0]['name'] if hits else None}")

    hits = launcher.rank_tools(SAMPLE, "dkgn")
    check("子序列 dkgn 能搜到 DiskGenius",
          len(hits) == 2 and all(t["name"] == "DiskGenius" for t in hits),
          f"命中 {[t['name'] for t in hits]}")

    check("搜不存在的关键词返回空表", launcher.rank_tools(SAMPLE, "qqqqqq") == [])

    hits = launcher.rank_tools(SAMPLE, "simplewall防火墙")
    check("按别名能搜到（别名也是检索字段）", len(hits) == 2,
          f"命中 {[t['name'] for t in hits]}")

    hits = launcher.rank_tools(SAMPLE, "防火墙")
    check("按分类能搜到", len(hits) >= 2, f"命中 {[t['name'] for t in hits]}")

    # 同分时保持原顺序，否则每次刷新顺序都在跳
    ties = [make_tool(i, "same", f"x/{i}.exe") for i in range(5)]
    check("同分保持原顺序（稳定排序）",
          [t["id"] for t in launcher.rank_tools(ties, "same")] == [0, 1, 2, 3, 4])


def test_hints():
    print("\n[A3] 副标题消歧")

    check("有别名时优先用别名",
          launcher.tool_hint(SAMPLE[0]) == "FTP")

    bare = make_tool(99, "X", "a/X.exe", category="未分类")
    check("「未分类」不显示（满屏未分类等于没提示）",
          launcher.tool_hint(bare) == "")

    hints = launcher.compute_hints(SAMPLE)
    check("每张卡片都算出了副标题", len(hints) == len(SAMPLE))

    # 核心不变式：重名组内的副标题必须两两不同
    bad = []
    for group in launcher.duplicate_groups(SAMPLE).values():
        group_hints = [hints[t["id"]] for t in group]
        if len(set(group_hints)) != len(group_hints):
            bad.append((group[0]["name"], group_hints))
    check("每个重名组的副标题都能区分开", not bad, f"区分不开：{bad}")

    sw = {t["id"]: hints[t["id"]] for t in SAMPLE if t["name"] == "simplewall"}
    check("simplewall 别名相同 → 退到上级目录 X32/X64",
          set(sw.values()) == {"simplewall防火墙X32", "simplewall防火墙X64"},
          f"实际 {sw}")

    names = dict(launcher.duplicate_names(SAMPLE))
    check("重名统计正确（3 组）",
          names == {"DiskGenius": 2, "simplewall": 2, "屏幕吸色器": 2},
          f"实际 {names}")
    check("重名集合覆盖全部 6 个重名工具",
          launcher.duplicate_id_set(SAMPLE) == {11, 14, 26, 39, 30, 35},
          f"实际 {sorted(launcher.duplicate_id_set(SAMPLE))}")


def test_strips():
    print("\n[A4] 收藏 / 最近使用 / 时长条标签")

    check("as_flag 认 1", launcher.as_flag(1) is True)
    check("as_flag 认 '0'", launcher.as_flag("0") is False)
    check("as_flag 认 'True'", launcher.as_flag("True") is True)
    check("as_flag 认 None", launcher.as_flag(None) is False)

    favs = launcher.favorite_tools(SAMPLE)
    check("收藏只挑出 is_favorite=1 的", [t["name"] for t in favs] == ["putty"],
          f"实际 {[t['name'] for t in favs]}")

    recents = launcher.recent_tools(SAMPLE)
    check("最近使用按时间倒序",
          [t["name"] for t in recents] ==
          ["putty_V0.63.LinuxProbe.Com", "PuTTY_0.67.0.0"],
          f"实际 {[t['name'] for t in recents]}")

    check("最近使用 limit 生效", len(launcher.recent_tools(SAMPLE, limit=1)) == 1)
    check("最近使用可排除指定 id（避免和收藏条重复）",
          all(t["id"] != 32 for t in
              launcher.recent_tools(SAMPLE, exclude_ids={32})))

    check("时长条标签优先取别名",
          launcher.strip_label(make_tool(1, "全名很长", "a.exe", alias="短")) == "短")
    long_name = launcher.strip_label(make_tool(1, "A" * 40, "a.exe"), max_len=10)
    check("超长标签截断且带省略号",
          len(long_name) == 10 and long_name.endswith("…"), f"实际 {long_name!r}")


# ---------------------------------------------------------------------------
# B. 真实窗口层
# ---------------------------------------------------------------------------

def build_page(root, db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    tools_db.init_all_tool_tables(conn)
    page = ToolsPage(root, conn, project_root=str(ROOT))
    page.pack(fill="both", expand=True)
    root.update_idletasks()
    return page, conn


def test_real_page():
    print("\n[B] 真实工具箱页面")

    tmp_db = Path(tempfile.gettempdir()) / f"wb_tools_launcher_{os.getpid()}.db"
    shutil.copy2(ROOT / "expiry_manager.db", tmp_db)

    root = tk.Tk()
    root.geometry("1180x820")
    # 不 withdraw：几何断言要跑在真实映射的窗口上，否则 winfo_width() 全是 1，
    # 「不溢出」这类断言会永远通过 —— 等于没测
    page, conn = build_page(root, tmp_db)
    # 占位文案必须在跑事件循环之前查：页面 after(80) 会自动聚焦搜索框，
    # 一跑循环就清掉占位（那是正确行为）
    _assert_placeholder_initial(page)
    root.update()
    try:
        _assert_cards(page, conn)
        _assert_categories(page, conn)
        # 上面切过分类 → 网格被重建 → 必须再跑一轮事件循环，新卡片才会被映射
        root.update()
        _assert_geometry(page)
        _assert_spaced_category_chip(page)
        _assert_search(page)
        _assert_cursor_and_run(page)
        _assert_favorite(page, conn)
        _assert_recent(page, conn)
        _assert_command_bar(page)
        _assert_launch_with_args(page, conn)
        _assert_status_bar(page)
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
        conn.close()
        try:
            tmp_db.unlink()
        except OSError:
            pass


def _assert_placeholder_initial(page):
    """占位文案必须在「跑事件循环之前」检查。

    页面构造后会 after(80) 自动聚焦搜索框，一跑事件循环就会触发 FocusIn
    把占位文案清掉 —— 那是正确行为，只是测试不能再指望它还在。
    """
    check("初始显示占位文案", page.search_var.get() == page.SEARCH_PLACEHOLDER,
          f"实际 {page.search_var.get()!r}")
    check("占位文案不算关键词", page._current_keyword() == "")
    check("占位文案是浅色的（看得出是提示不是输入）",
          page.search_entry.cget("foreground") != "#1c1c1c",
          f"实际 {page.search_entry.cget('foreground')!r}")
    page._hide_placeholder()
    check("聚焦后占位文案被清掉", page.search_var.get() == "")


def _assert_cards(page, conn):
    total = conn.execute(
        "SELECT COUNT(*) FROM tool_items WHERE COALESCE(is_deleted,0)=0").fetchone()[0]
    check("网格铺出全部工具卡片", len(page.icon_widgets) == total,
          f"卡片 {len(page.icon_widgets)} / 库内 {total}")
    check("可见列表与卡片数一致", len(page._visible_tools) == len(page.icon_widgets))

    stars = list(page._star_labels.values())
    check("每张卡片都有收藏星标", len(stars) == len(page.icon_widgets))
    check("星标只有 ★ / ☆ 两态",
          all(s.cget("text") in ("★", "☆") for s in stars))

    countdown = page._status_label_text() if hasattr(page, "_status_label_text") else \
        page.status_var.get()
    check("状态条报出工具总数", "个工具" in countdown, f"实际 {countdown!r}")


def _assert_categories(page, conn):
    conn.row_factory = sqlite3.Row
    counts = {}
    for row in conn.execute(
            "SELECT COALESCE(category,'未分类') c, COUNT(*) n FROM tool_items "
            "WHERE COALESCE(is_deleted,0)=0 GROUP BY c"):
        counts[row["c"]] = row["n"]

    all_cats = [r["name"] for r in tools_db.list_categories(page.db)]
    shown = set(page._category_chips)
    empties = [c for c in all_cats if counts.get(c, 0) == 0]

    check("「全部」chip 一定在", "全部" in shown)
    check("空分类不进分类栏", not (shown & set(empties)),
          f"混进了空分类 {sorted(shown & set(empties))}")
    check("非空分类都在分类栏里",
          all(c in shown for c in counts if c != "全部"),
          f"缺少 {[c for c in counts if c not in shown]}")
    chip = page._category_chips["全部"]
    check("chip 文案带数量", chip.text == f"全部 {sum(counts.values())}",
          f"实际 {chip.text!r}")
    check("分类 chip 是自绘圆角胶囊", isinstance(chip, RoundedChip))
    check("分类 chip 不带原生 1px 边框",
          str(chip.cget("highlightthickness")) == "0")
    check("当前分类恰好只有一颗 chip 亮起",
          sum(1 for c in page._category_chips.values() if c.is_active) == 1
          and page._category_chips[page.current_category].is_active,
          f"亮起 {[n for n, c in page._category_chips.items() if c.is_active]}")

    # 切到某个分类，网格应只剩该分类
    target = next(c for c in ("系统工具", "工具包", "网络") if c in shown)
    page._switch_category(target)
    check(f"切到「{target}」后只剩该分类",
          len(page.icon_widgets) == counts[target],
          f"卡片 {len(page.icon_widgets)} / 库内 {counts[target]}")
    page._switch_category("全部")
    check("切回「全部」恢复全量",
          len(page.icon_widgets) == sum(counts.values()))


def _assert_spaced_category_chip(page):
    """复现回归：分类名含空格时，靠 split(" ") 从文案里取名字会取错。

    库里有「ADB 工具」这种带空格的分类名，取成 "ADB" 就永远判不出选中态，
    悬停一次选中配色就被涂掉了。
    """
    import tools_page as tp

    page.current_category = "ADB 工具"
    chip = page._create_category_chip("ADB 工具", 3, None)
    page.winfo_toplevel().update()
    accent = tp.COLOR_ACCENT
    check("带空格分类名的 chip 初始就是选中配色",
          chip.is_active and chip.fill_color == accent,
          f"is_active={chip.is_active} fill={chip.fill_color!r}")

    chip.event_generate("<Enter>")
    page.winfo_toplevel().update()
    after_enter = chip.fill_color
    chip.event_generate("<Leave>")
    page.winfo_toplevel().update()
    after_leave = chip.fill_color

    check("带空格分类名的选中 chip 悬停后仍是选中配色",
          after_enter == accent and after_leave == accent,
          f"accent={accent} enter={after_enter} leave={after_leave}")

    chip.destroy()
    page._category_chips.pop("ADB 工具", None)
    page.category_buttons = [c for c in page.category_buttons if c is not chip]
    page.current_category = "全部"


def _assert_geometry(page):
    """卡片内容必须留在卡片里 —— 标题最多两行。

    注意 tk.Label 的单行 reqheight = linespace + 6（实测 17 → 23），
    所以两行是 2 * linespace + 6，不是 2 * linespace。
    """
    import tools_page as tp

    page.winfo_toplevel().update()

    line_h = page._name_font.metrics("linespace")
    two_line_h = 2 * line_h + tp.LABEL_VPAD
    overflow, title_overflow, too_narrow = [], [], []

    for tool_id, card in page.icon_widgets.items():
        card_w, card_h = card.winfo_width(), card.winfo_height()
        if card_w <= 1 or card_h <= 1:
            overflow.append((tool_id, "卡片未映射/尺寸异常", (card_w, card_h)))
            continue
        if card_w < tp.CARD_MIN_WIDTH:
            too_narrow.append((tool_id, card_w))
        for child in card.winfo_children():
            right = child.winfo_x() + child.winfo_width()
            bottom = child.winfo_y() + child.winfo_height()
            if right > card_w + 1 or bottom > card_h + 1:
                overflow.append((tool_id, child.winfo_class(),
                                 (right, bottom), (card_w, card_h)))
        _, name_label, _, _ = page.icon_subwidgets[tool_id]
        if name_label.winfo_reqheight() > two_line_h:
            title_overflow.append((tool_id, name_label.cget("text"),
                                   name_label.winfo_reqheight(), two_line_h))

    check("卡片已真正映射（几何断言才有意义）",
          all(c.winfo_width() > 1 for c in page.icon_widgets.values()))
    check("卡片子控件都不溢出卡片", not overflow, f"溢出 {overflow[:3]}")
    check("标题一律不超过两行", not title_overflow, f"超行 {title_overflow[:3]}")
    check("卡片宽度不小于最小宽度", not too_narrow, f"过窄 {too_narrow[:3]}")
    check("卡片高度足够容纳图标 + 两行标题 + 副标题",
          all(c.winfo_height() >= page.icon_size + 40
              for c in page.icon_widgets.values()))


def _assert_search(page):
    page.search_var.set("dkgn")
    page.winfo_toplevel().update_idletasks()
    names = [t["name"] for t in page._visible_tools]
    check("搜 dkgn 即输即搜命中 DiskGenius",
          names and all(n == "DiskGenius" for n in names),
          f"命中 {names}")
    check("搜 dkgn 网格只剩命中的卡片",
          len(page.icon_widgets) == len(names))

    page.search_var.set("qqqqqq")
    names = [t["name"] for t in page._visible_tools]
    check("搜不到时可见列表为空", names == [], f"命中 {names}")
    check("搜不到时状态条给出提示",
          "没有匹配" in page.status_var.get(), f"实际 {page.status_var.get()!r}")

    page._clear_search()
    check("清空后恢复全量", len(page.icon_widgets) == len(page._all_tools),
          f"卡片 {len(page.icon_widgets)} / 全量 {len(page._all_tools)}")


def _assert_cursor_and_run(page):
    page.search_var.set("putty")
    first_id = launcher.tool_id(page._visible_tools[0])
    check("搜索后光标自动落在第一条命中",
          page._cursor_tool_id == first_id,
          f"光标 {page._cursor_tool_id} / 首条 {first_id}")

    cursor_card = page.icon_widgets[page._cursor_tool_id]
    check("光标卡片被涂上强调边框",
          int(cursor_card.cget("highlightthickness")) == 2,
          f"实际 {cursor_card.cget('highlightthickness')}")

    page._move_cursor(1)
    check("↓ 移动光标", page._cursor_tool_id != first_id,
          f"光标仍为 {page._cursor_tool_id}")
    page._move_cursor(-1)
    check("↑ 移回原处", page._cursor_tool_id == first_id)

    # 回车启动第一条命中（拦下真实启动，只记录 id）
    launched = []
    original = page._run_tool_by_id
    page._run_tool_by_id = lambda tid: launched.append(tid)
    try:
        page._on_search_enter()
    finally:
        page._run_tool_by_id = original
    check("回车启动当前光标的那一条", launched == [first_id],
          f"实际启动 {launched}")

    page._clear_search()


def _assert_favorite(page, conn):
    """星标收藏：落库 + 立刻变实心 + 进「收藏」横条。

    开始前先把这颗星强制清成未收藏 —— 测试不该依赖真实库里原本的收藏状态，
    用户随时可能手动收藏过某个工具，否则这条断言会随着库的状态时灵时不灵，
    失败得莫名其妙。跑完再把原值还原回去。
    """
    target = page._visible_tools[0]
    tid = launcher.tool_id(target)

    def flag():
        return conn.execute("SELECT is_favorite FROM tool_items WHERE id=?",
                            (tid,)).fetchone()[0]

    original = flag()
    conn.execute("UPDATE tool_items SET is_favorite=0 WHERE id=?", (tid,))
    conn.commit()
    for bucket in (page._all_tools, page._visible_tools):
        for item in bucket:
            if launcher.tool_id(item) == tid:
                item["is_favorite"] = 0
    page._refresh_star(tid)

    page._toggle_favorite_by_id(tid)
    check("点星标把收藏状态写进库", bool(flag()), f"after={flag()!r}")
    check("星标立刻变成实心 ★",
          page._star_labels[tid].cget("text") == "★",
          f"实际 {page._star_labels[tid].cget('text')!r}")

    strip_texts = [_label_text(w)
                   for row in page._strips_frame.winfo_children()
                   for w in row.winfo_children()]
    check("收藏后出现在「收藏」横条",
          "收藏" in strip_texts and
          launcher.strip_label(target) in strip_texts,
          f"横条 {strip_texts}")

    page._toggle_favorite_by_id(tid)
    check("再点一次取消收藏", not flag())
    check("星标变回空心 ☆",
          page._star_labels[tid].cget("text") == "☆")

    if original:
        conn.execute("UPDATE tool_items SET is_favorite=1 WHERE id=?", (tid,))
        conn.commit()
        for bucket in (page._all_tools, page._visible_tools):
            for item in bucket:
                if launcher.tool_id(item) == tid:
                    item["is_favorite"] = 1
        page._refresh_star(tid)




def _assert_recent(page, conn):
    """启动过的工具要进「最近使用」横条。

    刻意挑一个「没被收藏」的工具：收藏的那几个会被排除在「最近」之外
    （免得两条横条重复显示同一个），拿收藏过的工具来测必然误报。
    """
    target = next((t for t in page._visible_tools
                   if not launcher.as_flag(t.get("is_favorite"))), None)
    if target is None:
        print("  skip  当前视图里的工具都被收藏了，跳过「最近使用」横条断言")
        return

    tid = launcher.tool_id(target)
    page._after_tool_run(tid)

    row = conn.execute("SELECT last_run_at, run_count FROM tool_items WHERE id=?",
                       (tid,)).fetchone()
    check("启动后记下最近使用时间", bool(row["last_run_at"]),
          f"last_run_at={row['last_run_at']!r}")
    check("启动次数累加", (row["run_count"] or 0) >= 1)

    strip_texts = [_label_text(w)
                   for row in page._strips_frame.winfo_children()
                   for w in row.winfo_children()]
    check("启动后出现在「最近」横条",
          "最近" in strip_texts and launcher.strip_label(target) in strip_texts,
          f"横条 {strip_texts}")




def _assert_command_bar(page):
    """命令条按钮一律纯文字 —— 之前是一排 emoji（✎ 🔍 🧹 📁 ⚙）。"""
    emojis = "✎🔍🧹📁⚙▶💾📌🗑＋"
    texts = []
    for widget in page._command_bar.winfo_children():
        texts.extend(_all_button_texts(widget))
    polluted = [t for t in texts if any(ch in t for ch in emojis)]
    check("命令条按钮不含 emoji", not polluted, f"含 emoji 的按钮 {polluted}")
    check("命令条有搜索框", page.search_entry.winfo_exists())
    check("命令条按钮文案齐全",
          {"添加工具", "包管理", "扫描目录", "打开目录", "设置"} <= set(texts),
          f"实际 {texts}")

    styles = {str(b.cget("style")) for w in page._command_bar.winfo_children()
              for b in _all_buttons(w)}
    check("命令条按钮走「悬停才浮底」的 Toolbar.TButton",
          styles <= {"Toolbar.TButton", "Primary.TButton"},
          f"实际 {sorted(styles)}")


def _label_text(widget) -> str:
    """取控件上的文案：tk 控件走 cget，自绘胶囊走 .text。"""
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return getattr(widget, "text", "")


def _all_buttons(widget):
    found = []
    if widget.winfo_class() == "TButton":
        found.append(widget)
    for child in widget.winfo_children():
        found.extend(_all_buttons(child))
    return found


def _all_button_texts(widget):
    texts = []
    if widget.winfo_class() in ("TButton", "Button", "Label"):
        try:
            texts.append(str(widget.cget("text")))
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        texts.extend(_all_button_texts(child))
    return texts


def _assert_launch_with_args(page, conn):
    """回归：「带参数 + 不提权」曾经因为 _sub 只在提权分支绑定而 NameError。"""
    import tools_page

    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
    if not exe.exists():
        print("  skip  本机没有 cmd.exe，跳过带参数启动回归")
        return

    conn.execute(
        "INSERT INTO tool_items (name, path, category, args, run_as_admin) "
        "VALUES (?, ?, ?, ?, 0)", ("__test_args__", str(exe), "工具包", "--version"))
    conn.commit()
    tid = conn.execute("SELECT id FROM tool_items WHERE name='__test_args__'"
                        ).fetchone()[0]

    calls = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls.append((list(args), kwargs))

    original_popen = tools_page.subprocess.Popen
    tools_page.subprocess.Popen = FakePopen
    try:
        page._run_tool_by_id(tid)
    except Exception as exc:  # 旧代码这里是 UnboundLocalError
        check("带参数 + 不提权的工具能正常启动（不再 NameError）", False,
              f"抛出 {type(exc).__name__}: {exc}")
    else:
        check("带参数 + 不提权的工具能正常启动（不再 NameError）",
              bool(calls) and calls[0][0][0] == str(exe) and
              calls[0][0][1:] == ["--version"],
              f"实际调用 {calls}")
    finally:
        tools_page.subprocess.Popen = original_popen
        conn.execute("DELETE FROM tool_items WHERE name='__test_args__'")
        conn.commit()


def _assert_status_bar(page):
    page.search_var.set("")
    page._refresh_grid()
    text = page.status_var.get()
    check("状态条含总数", "共" in text and "个工具" in text, f"实际 {text!r}")
    check("状态条点名重名工具", "重名" in text, f"实际 {text!r}")
    check("状态条是 ttk 标签挂着的（真的会显示）",
          page._status_bar.winfo_exists())


# ---------------------------------------------------------------------------
# [C] 图标抽取 / 无图标底牌 / 圆角胶囊
# ---------------------------------------------------------------------------

def test_icon_extraction():
    """真实 exe 的图标抽取。

    本机真实踩过的坑：PuTTY 0.6x、Delphi 编的屏幕吸色器，图标是「32 位色但
    alpha 通道全 0」，透明度只存在于 AND 蒙版里。老代码照 BGRA 直读，写出来的是
    一张 88 字节的全透明空图 —— 文件在、大小也正常，显示出来什么都没有，
    用户看到的就是「这个工具抽不到图标」。
    """
    try:
        from PIL import Image
    except ImportError:
        print("  skip  没有 Pillow，跳过图标抽取测试")
        return

    import tools_page as tp

    tools_dir = ROOT / "Tools"
    samples = [p for p in (
        tools_dir / "工具包" / "putty.exe",
        tools_dir / "工具包" / "屏幕吸色器.exe",
        tools_dir / "工具包" / "8uftp.exe",
    ) if p.exists()]
    if not samples:
        print("  skip  本机 Tools 目录里没有可用样本")
        return

    tmp = Path(tempfile.mkdtemp(prefix="wb_icon_"))
    try:
        cache = tmp / "cache"
        for exe in samples:
            out = tmp / (exe.stem + ".png")
            ok = tp.extract_exe_icon(str(exe), str(out), 48, cache)
            check(f"{exe.name} 能抽出图标", ok)
            if not ok:
                continue
            alpha = Image.open(out).convert("RGBA").getchannel("A").getextrema()
            check(f"{exe.name} 抽出的图不是全透明", alpha[1] > 0,
                  f"alpha={alpha}")

        # ---- 坏缓存自愈：伪造一张全透明空图放进缓存目录 ----
        exe = samples[0]
        cache2 = tmp / "cache2"
        cp = tp._get_icon_cache_path(str(exe), 48, cache2)
        cp.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (48, 48), (0, 0, 0, 0)).save(cp)
        check("全透明的空 PNG 被判为不可用", not tp.png_icon_is_usable(cp))
        out2 = tmp / "heal.png"
        healed = tp.extract_exe_icon(str(exe), str(out2), 48, cache2)
        check("坏缓存被删掉并重新抽出好图", healed and tp.png_icon_is_usable(cp))

        # ---- 抽不到时：返回 False、不留垃圾、并进负缓存 ----
        # 两条抽取路径都打成失败，测的才是「抽不到」这条分支本身。
        # 用真 exe 测不出来：PowerShell 的 ExtractAssociatedIcon 哪怕文件根本没有
        # 图标资源，也会还你一枚系统默认图标 —— 那是可用结果，不是失败。
        junk = tmp / "noicon.exe"
        junk.write_bytes(b"MZ" + b"\0" * 4096)
        out3 = tmp / "junk.png"
        cache3 = tmp / "cache3"
        originals = (tp._extract_icon_image, tp.subprocess.run)
        tp._extract_icon_image = lambda *a, **k: None
        tp.subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=1)
        try:
            check("两条路径都抽不到时返回 False",
                  not tp.extract_exe_icon(str(junk), str(out3), 48, cache3))
            check("失败时不留垃圾 PNG", not out3.exists())
            start = time.time()
            tp.extract_exe_icon(str(junk), str(out3), 48, cache3)
            elapsed = time.time() - start
            check("抽不到的结果进负缓存（二次调用 <20ms）", elapsed < 0.02,
                  f"耗时 {elapsed * 1000:.0f}ms")
        finally:
            tp._extract_icon_image, tp.subprocess.run = originals
        # 负缓存只按「路径 + mtime + 大小」记，文件一被替换就得能重新尝试。
        # 这里显式改 mtime：同一纳秒内重写有可能拿到同样的 mtime_ns，
        # 那这个断言就成了掷骰子。
        junk.write_bytes(b"MZ" + b"\1" * 4096)
        os.utime(junk, (time.time() + 5, time.time() + 5))
        check("exe 变了之后会重新尝试（负缓存不会误锁）",
              tp._file_stamp(junk) not in tp._icon_miss_cache)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_letter_tile():
    """无图标工具的占位底牌：圆角 + 首字，且不同首字必须长得不一样。"""
    tile = app_icons.letter_tile("putty", 48)
    check("底牌尺寸 / 模式正确",
          tile.size == (48, 48) and tile.mode == "RGBA",
          f"{tile.size} {tile.mode}")
    check("底牌本身不透明（画得出来）", tile.getchannel("A").getextrema()[1] > 0)
    check("中文首字也能画", app_icons.letter_tile("屏幕吸色器", 48)
          .getchannel("A").getextrema()[1] > 0)
    check("不同首字画出不同的图（有区分度）",
          tile.tobytes() != app_icons.letter_tile("disk", 48).tobytes())
    check("按尺寸独立渲染", app_icons.letter_tile("putty", 64).size == (64, 64))
    check("空名字不崩", app_icons.letter_tile("", 32).size == (32, 32))


def test_rounded_chip():
    """自绘圆角胶囊：真圆角位图、无原生边框、三种状态各自换底图。"""
    root = tk.Tk()
    root.geometry("320x200")
    root.update()
    try:
        chip = RoundedChip(root, "系统工具 6", bg="#f7f7f7", fg="#1c1c1c",
                           canvas_bg="#ffffff", hover_bg="#f0f0f0",
                           active_bg="#1c1c1c", active_fg="#ffffff")
        chip.pack(padx=10, pady=10)
        root.update()

        def bg_image():
            """当前底图的位图名。换了状态就该换图，不换说明状态没接上。"""
            return str(chip.itemcget(chip.find_all()[0], "image"))

        kinds = [chip.type(i) for i in chip.find_all()]
        check("胶囊 = 圆角底图 + 文字", kinds == ["image", "text"],
              f"图元 {kinds}")
        check("没有原生 1px 高亮边框（「硬」的主要来源）",
              str(chip.cget("highlightthickness")) == "0")
        check("没有默认边框宽度", str(chip.cget("bd")) == "0")
        check("宽度按文字实测撑开", chip.winfo_reqwidth() > 40,
              f"reqwidth={chip.winfo_reqwidth()}")

        check("常态底色正确", chip.fill_color == "#f7f7f7",
              f"实际 {chip.fill_color!r}")
        normal = bg_image()
        check("常态底图已就位", bool(normal))

        chip.set_hover(True)
        check("悬停换底色", chip.fill_color == "#f0f0f0",
              f"实际 {chip.fill_color!r}")
        check("悬停换了一张底图", bg_image() != normal)
        hover = bg_image()

        chip.set_active(True)
        check("选中优先于悬停", chip.fill_color == "#1c1c1c",
              f"实际 {chip.fill_color!r}")
        check("选中又换了一张底图", bg_image() not in (normal, hover))

        chip.set_active(False)
        chip.set_hover(True)
        check("切回悬停复用已缓存的底图（不重复渲染）", bg_image() == hover)

        chip.set_drop_highlight(True)
        check("拖放高亮走选中配色", chip.fill_color == "#1c1c1c")
        chip.set_drop_highlight(False)

        chip.set_text("网络 3")
        check("改文案即时生效", chip.text == "网络 3")
        chip.destroy()
    finally:
        root.destroy()




def test_toolbar_button_style():
    """命令条按钮样式：常态等于页面底色（看不见按钮），悬停才浮出浅底。

    ★ 这里必须自己建一个 root 再销毁。``ttk.Style()`` 在没有 root 时会**自己造一个
    并占住 _default_root**，之后 tk.Tk() 就不再是默认 root，ImageTk 造出来的图会落进
    上一个解释器，跑到真实页面时报 image "pyimage1" doesn't exist —— 这个坑是实测
    踩出来的，不是理论担心。
    """
    root = tk.Tk()
    root.withdraw()
    try:
        style = ttk.Style(master=root)
        THEME.configure_toolbox_button_style(style, TOOLBOX_PALETTE)
        normal = str(style.lookup("Toolbar.TButton", "background"))
        check("Toolbar.TButton 常态底色 = 页面底色",
              normal == TOOLBOX_PALETTE.bg, f"实际 {normal!r}")
        check("Toolbar.TButton 无边框",
              str(style.lookup("Toolbar.TButton", "borderwidth")) == "0")
        active = str(style.lookup("Toolbar.TButton", "background", ["active"]))
        check("悬停才浮出浅底", active == TOOLBOX_PALETTE.surface_alt,
              f"实际 {active!r}")
        check("常态字色是次级色（不抢搜索框）",
              str(style.lookup("Toolbar.TButton", "foreground"))
              == TOOLBOX_PALETTE.text_secondary)
    finally:
        root.destroy()




def test_rounded_rect_image():
    """圆角底图的半径必须是真的。

    这条是「按钮很硬」的正面回归：早先用 ``create_polygon(smooth=True)``，
    把屏幕像素打成 ASCII 一看，设定半径 6 实际只把角切掉 1~2 像素，
    看着基本还是直角。现在改成 Pillow 4 倍超采样渲染，实测能切出 4px 连续透明。
    """
    im = rounded_rect_image(64, 25, 6, "#1c1c1c")
    check("底图尺寸 / 模式正确",
          im.size == (64, 25) and im.mode == "RGBA", f"{im.size} {im.mode}")
    check("中心实心且颜色正确", im.getpixel((32, 12)) == (28, 28, 28, 255),
          f"实际 {im.getpixel((32, 12))}")
    check("四角是透明的（方角不可能透明）",
          all(im.getpixel(p)[3] < 8 for p in ((0, 0), (63, 0), (0, 24), (63, 24))),
          f"实际 {[im.getpixel(p)[3] for p in ((0, 0), (63, 0), (0, 24), (63, 24))]}")

    depth = 0
    while depth < 20 and im.getpixel((depth, 0))[3] < 128:
        depth += 1
    check("圆角深度接近设定半径（不再是只切 1px）", 3 <= depth <= 8,
          f"顶边左侧透明 {depth}px（半径 6）")

    mid = 0
    while mid < 20 and im.getpixel((32, mid))[3] < 128:
        mid += 1
    check("顶边中段没有透明（否则就是把上面整条削掉了）", mid == 0,
          f"实际 {mid}px")

    check("半径会被夹到不超过半高",
          rounded_rect_image(40, 10, 99, "#000000").getpixel((20, 5))[3] == 255)
    check("颜色支持 #rgb 简写",
          rounded_rect_image(20, 20, 4, "#fff").getpixel((10, 10)) == (255, 255, 255, 255))


def main():
    print("=" * 78)
    print("系统工具箱启动器：纯函数 + 真实页面")
    print("=" * 78)

    test_fuzzy_scoring()
    test_ranking()
    test_hints()
    test_strips()
    test_icon_extraction()
    test_letter_tile()
    test_rounded_chip()
    test_rounded_rect_image()
    test_toolbar_button_style()
    test_real_page()

    print("\n" + "=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
