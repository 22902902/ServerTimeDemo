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
import tools_page as tp  # noqa: E402
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


def test_tool_tags():
    print("\n[A5] 标签：分隔符解析 / 逐标签打分 / 统计")

    check("竖线 / 逗号 / 顿号 / 分号 / 空格都是分隔符",
          launcher.split_tags("FTP、网络 ftp|ssh, 工具；dev")
          == ["FTP", "网络", "ssh", "工具", "dev"],
          str(launcher.split_tags("FTP、网络 ftp|ssh, 工具；dev")))
    check("全角逗号 / 全角竖线 / 全角分号也认",
          launcher.split_tags("a，b｜c；d") == ["a", "b", "c", "d"])
    check("大小写不敏感去重、保留首次写法",
          launcher.split_tags("FTP、ftp、Ftp") == ["FTP"])
    check("空段与首尾空白被吃掉", launcher.split_tags("  , , ftp  ,, ") == ["ftp"])
    check("空值 / None 安全",
          launcher.split_tags(None) == [] and launcher.split_tags("") == [])

    # 这几个字符不能当分隔符 —— 它们本身就常出现在标签里
    check("不把 / + # 当分隔符（C/C++、C# 是完整标签）",
          launcher.split_tags("C/C++，C#") == ["C/C++", "C#"],
          str(launcher.split_tags("C/C++，C#")))
    check("标签数有上限（防止一行黏进上百个词）",
          len(launcher.split_tags(" ".join(f"t{i}" for i in range(80))))
          == launcher.TAG_MAX)

    check("normalize_tags 存成 | 连接",
          launcher.normalize_tags(" FTP 、网络 ftp ") == "FTP|网络")
    check("tool_tags 兼容老库（缺 tags 列）", launcher.tool_tags({"name": "x"}) == [])

    tagged = {"name": "putty", "tags": "ftp|网络", "path": "a/putty.exe"}
    check("标签完全相等拿满分",
          launcher.best_tag_score("ftp", tagged) == launcher.SCORE_EXACT,
          str(launcher.best_tag_score("ftp", tagged)))
    check("标签前缀命中", launcher.best_tag_score("ft", tagged) is not None)
    check("不跨标签误命中（'tp网' 不算命中）",
          launcher.best_tag_score("tp网", tagged) is None,
          str(launcher.best_tag_score("tp网", tagged)))
    check("没有标签时返回 None", launcher.best_tag_score("ftp", {"name": "x"}) is None)

    # 关键语义：按标签搜时，标签命中要压过「名字里恰好含这几个字母」
    bytag = {"name": "小工具", "tags": "ftp", "path": "a/x.exe"}
    byname = {"name": "8uftp", "tags": "", "path": "a/8uftp.exe"}
    check("标签完全命中 排在 名字子串命中 之前",
          launcher.score_tool("ftp", bytag) > launcher.score_tool("ftp", byname),
          f"{launcher.score_tool('ftp', bytag)} vs {launcher.score_tool('ftp', byname)}")
    ranked = launcher.rank_tools([byname, bytag], "ftp")
    check("rank_tools 把标签命中的排到最前",
          launcher.field_text(ranked[0], "name") == "小工具")

    counts = launcher.popular_tags(
        [{"tags": "ftp|网络"}, {"tags": "ftp|ssh"}, {"tags": "网络"}, {"tags": ""}])
    # ftp 与 网络 各 2 次（网络 来自第 1、3 条），同分按名字升序 → ssh 垫底
    check("标签统计：个数降序、同分按名字升序",
          counts == [("ftp", 2), ("网络", 2), ("ssh", 1)], str(counts))
    check("标签统计支持 limit",
          len(launcher.popular_tags([{"tags": "a|b|c"}], limit=2)) == 2)
    check("标签统计大小写不敏感合并",
          launcher.popular_tags([{"tags": "FTP"}, {"tags": "ftp"}]) == [("FTP", 2)])


def test_tags_db():
    print("\n[A6] 数据层：tags 列迁移 / 扫描不覆盖手工分类")

    tmp = Path(tempfile.gettempdir()) / f"wb_tags_db_{os.getpid()}.db"
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    conn.row_factory = sqlite3.Row
    try:
        # 造一个「老库」：tool_items 里没有 tags 列
        conn.execute("""CREATE TABLE tool_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, alias TEXT, path TEXT,
            icon_path TEXT, category TEXT, args TEXT, run_as_admin INTEGER,
            description TEXT, is_favorite INTEGER, sort_order INTEGER,
            is_builtin INTEGER, is_deleted INTEGER DEFAULT 0, last_run_at TEXT,
            run_count INTEGER, created_at TEXT, updated_at TEXT)""")
        conn.execute("INSERT INTO tool_items (name, path, category, is_deleted) "
                     "VALUES ('8uftp', 'FTP/8uftp.exe', 'FTP', 0)")
        conn.commit()

        tools_db.init_all_tool_tables(conn)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tool_items)").fetchall()]
        check("老库启动时自动补上 tags 列", "tags" in cols)

        tools_db.update_tool(conn, 1, tags="FTP、 工具 ftp")
        check("update_tool 规范化后落库",
              tools_db.get_tool(conn, 1)["tags"] == "FTP|工具",
              str(tools_db.get_tool(conn, 1)["tags"]))

        # 手工改分类（拖拽 / 右键改的就是这条），之后重扫不能把它冲回目录名
        tools_db.update_tool(conn, 1, category="我的网络")
        tools_db.upsert_tool_by_path(conn, "FTP/8uftp.exe", "8uftp", "FTP")
        check("重扫不覆盖用户手工分类",
              tools_db.get_tool(conn, 1)["category"] == "我的网络",
              str(tools_db.get_tool(conn, 1)["category"]))

        # 反过来：还是「未分类」的，才该由目录名兜底
        conn.execute("INSERT INTO tool_items (name, path, category, is_deleted) "
                     "VALUES ('x', 'dev/x.exe', '未分类', 0)")
        conn.commit()
        tools_db.upsert_tool_by_path(conn, "dev/x.exe", "x", "开发工具")
        got = conn.execute(
            "SELECT category FROM tool_items WHERE path='dev/x.exe'").fetchone()
        check("未分类仍由目录名兜底", got["category"] == "开发工具", got["category"])

        putty_id = tools_db.add_tool(conn, name="putty", path="net/putty.exe",
                                     category="我的网络", tags="ssh,telnet 网络")
        check("add_tool 也规范化标签",
              tools_db.get_tool(conn, putty_id)["tags"] == "ssh|telnet|网络",
              str(tools_db.get_tool(conn, putty_id)["tags"]))
        check("list_tag_counts 统计全库标签",
              dict(tools_db.list_tag_counts(conn)) ==
              {"FTP": 1, "工具": 1, "ssh": 1, "telnet": 1, "网络": 1},
              str(tools_db.list_tag_counts(conn)))
        check("list_tag_counts 支持 limit",
              len(tools_db.list_tag_counts(conn, limit=2)) == 2)
        check("SQL 关键词也能命中标签",
              [r["name"] for r in tools_db.list_tools(conn, keyword="telnet")]
              == ["putty"])
        check("按分类过滤仍正常",
              [r["name"] for r in tools_db.list_tools(conn, category="我的网络")]
              == ["8uftp", "putty"],
              str([r["name"] for r in tools_db.list_tools(conn, category="我的网络")]))
        # 软删要走专用入口：update_tool 的字段白名单故意不含 is_deleted
        # （否则「改个描述」的代码路径能顺手把工具删掉）
        tools_db.delete_tool(conn, putty_id)
        check("软删除的工具不进标签统计",
              dict(tools_db.list_tag_counts(conn)) == {"FTP": 1, "工具": 1},
              str(tools_db.list_tag_counts(conn)))
        check("update_tool 拒绝偷改 is_deleted（只能用 delete_tool）",
              tools_db.update_tool(conn, putty_id, is_deleted=0) is False,
              "update_tool 竟然接受了 is_deleted")
    finally:
        conn.close()
        try:
            tmp.unlink()
        except OSError:
            pass


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

    # ★ 夹具是开发库，而「排列 / 图标大小」是用户随手改、会被存进库的设置：
    #   不钉住它，下面的卡片几何 / 星标文案断言就跟着库漂移 —— 库里存着 folder
    #   时文件夹格子只有 84px（断言比的是 CARD_MIN_WIDTH=104），星标在 folder
    #   下也默认不带 ★/☆ 文案，一次假红三条。构造页面前先钉成默认值。
    seed = sqlite3.connect(str(tmp_db))
    seed.row_factory = sqlite3.Row      # init_all_tool_tables 内部按列名取值
    try:
        tools_db.init_all_tool_tables(seed)
        tools_db.set_setting(seed, "view_mode", tp.DEFAULT_VIEW_MODE)
        tools_db.set_setting(seed, "icon_size", "48")
    finally:
        seed.close()

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
        _assert_view_modes(page, root)
        _assert_tags_and_drag(page, conn, root)
        _assert_first_layout(root, tmp_db)
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

    # 常态胶囊底色必须与内容区底色可区分。曾经用 surface_alt(#f7f7f7)：
    # 与白底只差 3%，自绘的圆角在那种对比度下完全看不出来 —— 等于白做。
    def _lum(hexv):
        return int(hexv.lstrip("#")[:2], 16)

    delta = _lum(tp.COLOR_BG) - _lum(tp.COLOR_CHIP_BG)
    check("常态胶囊底色与白底可区分（圆角才看得见）", delta >= 8,
          f"{tp.COLOR_CHIP_BG} vs {tp.COLOR_BG}，亮度差仅 {delta}")
    hover_delta = _lum(tp.COLOR_CHIP_BG) - _lum(tp.COLOR_CHIP_BG_HOVER)
    check("胶囊悬停态比常态明显深一档", hover_delta >= 8,
          f"{tp.COLOR_CHIP_BG_HOVER} vs {tp.COLOR_CHIP_BG}，差 {hover_delta}")
    # 注意要挑一颗「非选中」的：选中那颗的 fill 是近黑 accent，与底色无关
    idle = next((c for c in page._category_chips.values() if not c.is_active),
                None)
    check("常态胶囊底色确实传给了控件",
          idle is not None and idle.fill_color == tp.COLOR_CHIP_BG,
          f"实际 {getattr(idle, 'fill_color', None)!r}")
    check("选中胶囊底色是近黑 accent",
          chip.fill_color == tp.COLOR_ACCENT, f"实际 {chip.fill_color!r}")

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


def _assert_view_modes(page, root):
    """四种排列：图标 / 文件夹 / 卡片 / 列表。

    共用的东西（数据、排序、键盘光标、右键菜单、收藏）必须四种都一样，
    各排列之间只能差「一格画成什么」。这里就是在锁这条边界。
    """
    from ui_components import HoverTooltip

    check("切换器给出四种排列",
          [k for k, _ in tp.VIEW_MODES] == ["icon", "folder", "card", "list"],
          str(list(page._view_chips)))
    check("切换器 4 颗胶囊都在",
          all(c.winfo_exists() for c in page._view_chips.values()))

    page._set_view_mode("card")
    root.update()
    total = len(page.icon_widgets)
    check("有工具可渲染", total > 0, f"{total} 个")

    # ---- 每种排列都要渲染出全部工具，且保持 icon_subwidgets[0]=图标 label 的约定 ----
    shapes = {}
    for mode in ("icon", "folder", "card", "list"):
        page._set_view_mode(mode)
        root.update()
        check(f"「{mode}」渲染出全部格子", len(page.icon_widgets) == total,
              f"{len(page.icon_widgets)}/{total}")
        tid = next(iter(page.icon_widgets), None)
        cell = page.icon_widgets.get(tid)
        sub = page.icon_subwidgets.get(tid, ())
        check(f"「{mode}」subwidgets[0] 是图标 label",
              bool(sub) and sub[0] is not None and sub[0].winfo_class() == "Label",
              str([type(s).__name__ if s is not None else None for s in sub]))
        if cell is not None:
            shapes[mode] = (cell.cget("width"), cell.cget("height"))

    # ---- 图标排列：透明底 + 方格子 + 无描边 ----
    page._set_view_mode("icon")
    root.update()
    tid = next(iter(page.icon_widgets), None)
    cell = page.icon_widgets[tid]
    check("图标排列：格子是正方形",
          abs(int(cell.cget("width")) - int(cell.cget("height"))) <= 1,
          str(shapes.get("icon")))
    check("图标排列：格子不带任何描边",
          str(cell.cget("highlightthickness")) == "0",
          str(cell.cget("highlightthickness")))
    # 常态（既非光标也非选中）必须是纯页面底色 —— 就是「底色透明」
    idle = next((i for i in page.icon_widgets
                 if i not in (page.selected_tool_id, page._cursor_tool_id,
                              page._hover_tool_id)), tid)
    spec = page._cell_paint_spec(idle)
    check("图标排列：常态底色=页面底色且无描边宽度",
          spec[0] == tp.COLOR_BG and spec[2] == 0, str(spec))
    check("图标排列：悬停/光标用浅底色而不是描边",
          page._cell_paint_spec(page.selected_tool_id)[2] == 0
          and page._cell_paint_spec(page._cursor_tool_id)[2] == 0
          if page._cursor_tool_id is not None else True)

    # ---- 悬停浮层：图标排列给「名字+分类」，文件夹排列只给「分类」 ----
    check("图标排列：每格都挂了悬停浮层", len(page._tooltips) == total,
          f"{len(page._tooltips)}/{total}")
    check("图标排列：浮层控件是 HoverTooltip",
          all(isinstance(t, HoverTooltip) for t in page._tooltips))
    sample = page._visible_tools[0]
    text = page._tooltip_text(sample)
    check("图标排列：浮层给「名字 + 分类」两行",
          isinstance(text, tuple) and len(text) == 2 and bool(text[0])
          and bool(text[1]), str(text))

    page._set_view_mode("folder")
    root.update()
    tid = next(iter(page.icon_widgets), None)
    sub = page.icon_subwidgets[tid]
    check("文件夹排列：名字常显", sub[1] is not None and sub[1].winfo_exists())
    check("文件夹排列：名字 label 有文字",
          bool(str(sub[1].cget("text")).strip()), f"{sub[1].cget('text')!r}")
    folder_text = page._tooltip_text(page._visible_tools[0])
    check("文件夹排列：浮层只给分类（名字已常显）",
          isinstance(folder_text, tuple) and bool(folder_text[0])
          and folder_text[1] == "", str(folder_text))

    # ---- 卡片排列：保留描边（原来那套视觉不能变） ----
    page._set_view_mode("card")
    root.update()
    tid = next(iter(page.icon_widgets), None)
    check("卡片排列：保留描边",
          str(page.icon_widgets[tid].cget("highlightthickness")) in ("1", "2"),
          str(page.icon_widgets[tid].cget("highlightthickness")))

    # ---- 列表排列：单列 + 固定行高 + 星标可点 ----
    page._set_view_mode("list")
    root.update()
    tid = next(iter(page.icon_widgets), None)
    cell = page.icon_widgets[tid]
    check("列表排列：单列", page._grid_cols_now == 1, str(page._grid_cols_now))
    check("列表排列：行高固定", int(cell.cget("height")) == tp.LIST_ROW_H,
          str(cell.cget("height")))
    check("列表排列：有分类列", page.icon_subwidgets[tid][2] is not None)
    check("列表排列：星标可点（cursor=hand2）",
          str(page._star_labels[tid].cget("cursor")) == "hand2",
          str(page._star_labels[tid].cget("cursor")))

    # ---- 列数：卡片用固定设置，图标/文件夹随宽度自动算 ----
    check("列表排列恒为一列（宽度无关）", page._grid_columns() == 1)
    page._set_view_mode("icon")
    root.update()
    original_width = page._available_grid_width
    try:
        page._available_grid_width = lambda: 600
        narrow = page._grid_columns()
        page._available_grid_width = lambda: 1400
        wide = page._grid_columns()
    finally:
        page._available_grid_width = original_width
    check("图标排列列数随可用宽度增长", wide > narrow, f"{narrow} → {wide}")
    check("图标排列在窄窗口下也至少留一列",
          narrow >= 1, str(narrow))
    page._set_view_mode("card")
    root.update()
    check("卡片排列仍用设置里的固定列数",
          page._grid_columns() == max(int(page.grid_cols), 1),
          f"{page._grid_columns()} vs grid_cols={page.grid_cols}")

    # ---- 浮层不许泄漏：网格重建时 Toplevel 要跟着销毁 ----
    page._set_view_mode("icon")
    root.update()
    before = len(page._tooltips)
    for _ in range(3):
        page._refresh_grid()
        root.update()
    check("反复重建网格后浮层不累积", len(page._tooltips) == before,
          f"{before} → {len(page._tooltips)}")

    # ---- 收藏角标：图标/文件夹排列是「收藏后才出现的角标」，卡片是「常显可点」 ----
    tid = next(iter(page.icon_widgets), None)
    was_fav = any(launcher.as_flag(t.get("is_favorite"))
                  for t in page._all_tools if launcher.tool_id(t) == tid)
    try:
        if was_fav:
            page._toggle_favorite_by_id(tid)
            root.update()
        page._toggle_favorite_by_id(tid)
        root.update()
        star = page._star_labels[tid]
        check("图标排列：收藏后右上角出现 ★",
              str(star.cget("text")) == "★", repr(star.cget("text")))
        check("图标排列：角标不是可点的（收藏走右键）",
              str(star.cget("cursor")) == "arrow", str(star.cget("cursor")))
        page._toggle_favorite_by_id(tid)
        root.update()
        check("图标排列：取消收藏后角标清空",
              str(star.cget("text")) == "", repr(star.cget("text")))
    finally:
        if was_fav:                        # 还原成进来时的样子
            page._toggle_favorite_by_id(tid)
            root.update()

    page._set_view_mode("card")
    root.update()
    tid = next(iter(page.icon_widgets), None)
    check("卡片排列：星标常显可点",
          str(page._star_labels[tid].cget("cursor")) == "hand2")

    # ---- 右键菜单必须能收藏/取消收藏 ----
    def menu_labels(favorited):
        captured = {}
        original_popup = tk.Menu.tk_popup

        def fake_popup(menu_self, *_a, **_k):
            captured["menu"] = menu_self

        tk.Menu.tk_popup = fake_popup
        try:
            if favorited != any(launcher.as_flag(t.get("is_favorite"))
                                for t in page._all_tools
                                if launcher.tool_id(t) == tid):
                page._toggle_favorite_by_id(tid)
                root.update()
            page._show_tool_menu(types.SimpleNamespace(x_root=5, y_root=5), tid)
        finally:
            tk.Menu.tk_popup = original_popup
        menu = captured.get("menu")
        if menu is None:
            return None
        labels = []
        for index in range(menu.index("end") + 1):
            # 分隔符没有 -label 选项，直接 entrycget 会抛 TclError
            if menu.type(index) == "separator":
                continue
            try:
                labels.append(menu.entrycget(index, "label") or "")
            except tk.TclError:
                pass
        menu.destroy()
        return labels

    labels = menu_labels(favorited=False)
    check("右键菜单含「收藏」", labels is not None and "收藏" in labels,
          str(labels))
    check("右键菜单保留「运行」", labels is not None and "运行" in labels,
          str(labels))
    labels_fav = menu_labels(favorited=True)
    check("已收藏时菜单变成「取消收藏」",
          labels_fav is not None and "取消收藏" in labels_fav, str(labels_fav))
    page._toggle_favorite_by_id(tid)
    root.update()

    # ---- 排列模式要记住 ----
    page._set_view_mode("list")
    root.update()
    saved = tools_db.get_setting(page.db, "view_mode", "")
    check("切换排列会写进设置（下次打开还是它）", saved == "list", f"{saved!r}")
    page._set_view_mode("card")
    root.update()
    check("能切回卡片并同步设置",
          tools_db.get_setting(page.db, "view_mode", "") == "card")


def _all_chips(widget):
    """递归收集 RoundedChip（标签 / 分类 / 收藏横条都是它画的）。

    胶囊的文案是 Canvas 图元，没有 -text 选项，得走 .text 属性，
    不能用 tk.Label 那套 cget。
    """
    found = []
    for child in widget.winfo_children():
        if isinstance(child, RoundedChip):
            found.append(child)
        found.extend(_all_chips(child))
    return found


def _chip_by_text(widget, text):
    for chip in _all_chips(widget):
        if chip.text == text:
            return chip
    return None


def _assert_tags_and_drag(page, conn, root):
    """标签横条 / 全局搜索 / 拖拽改分类 / 描述占位。"""
    print("\n[B7] 标签横条 / 全局搜索 / 拖拽改分类 / 描述占位")

    # 右侧编辑面板是懒建的：不展开的话 edit_desc_text 这些属性还不存在
    if not page._right_visible:
        page._toggle_right_panel()
        root.update()

    # ---- 描述占位：提示语是壳子，不能当成内容存进库 ----
    page._set_desc_value("")
    check("描述为空时取值为空（占位文案不算内容）",
          page._get_desc_value() == "", repr(page._get_desc_value()))
    page._set_desc_value("一段描述")
    check("描述有内容时能原样取回", page._get_desc_value() == "一段描述")

    # ---- 给一个工具打标签；另建两个空分类当投放目标 ----
    first = page._visible_tools[0]
    tid = launcher.tool_id(first)
    tools_db.update_tool(page.db, tid, tags="探针标签,other")
    tools_db.add_category(conn, "拖拽目标分类")
    tools_db.add_category(conn, "诱饵空分类")   # 全程不往里放东西，用来验「松手后收起」
    page._refresh_all()
    root.update()

    # ---- 标签横条 ----
    tag_chip = _chip_by_text(page._strips_frame, "#探针标签")
    check("标签横条出现该标签胶囊", tag_chip is not None,
          str([c.text for c in _all_chips(page._strips_frame)]))
    check("标签胶囊挂在横条区（不是分类栏）",
          _chip_by_text(page._category_bar, "#探针标签") is None)

    # 点标签 = 填进搜索框 = 全局搜索（跨分类、跨包）
    if tag_chip is not None:
        page.current_category = "拖拽目标分类"      # 故意停在「没有这个工具」的分类
        page._refresh_categories()
        root.update()
        tag_chip._invoke()
        root.update()
        names = [t["name"] for t in page._visible_tools]
        check("点标签即全局搜（当前分类里没有也搜得到）",
              first["name"] in names,
              f"当前分类={page.current_category} 命中={names[:5]}")
        check("全局搜时状态条注明「全局」",
              "全局" in page.status_var.get(), page.status_var.get())
        page._search_placeholder_on = False
        page.search_var.set("")
        root.update()

    # ---- 拖拽改分类 ----
    page.current_category = "全部"
    page._search_placeholder_on = False
    page.search_var.set("")
    page._refresh_all()
    root.update()

    card = page.icon_widgets.get(tid)
    check("目标工具在当前视图里", card is not None)
    check("空分类平时不进分类栏",
          "拖拽目标分类" not in page._category_chips
          and "诱饵空分类" not in page._category_chips,
          str(list(page._category_chips)))

    if card is not None:
        before_path = tools_db.get_tool(page.db, tid)["path"]
        before_category = tools_db.get_tool(page.db, tid)["category"]

        ev = type("E", (), {})
        e = ev(); e.widget = card
        e.x_root = card.winfo_rootx() + 4
        e.y_root = card.winfo_rooty() + 4
        page._on_card_press(e, tid)
        root.update()
        check("按下先选中（拖拽前就选中了）", page.selected_tool_id == tid)

        e2 = ev(); e2.widget = card
        e2.x_root = e.x_root + 40          # 超过 DRAG_THRESHOLD
        e2.y_root = e.y_root + 40
        page._on_drag_motion(e2)
        root.update()
        check("越过阈值后出现影子窗口（否则用户不知道拖起来了）",
              page._drag_ghost is not None)
        check("拖拽期间空分类被摆出来（否则放不进去）",
              "拖拽目标分类" in page._category_chips
              and "诱饵空分类" in page._category_chips,
              str(list(page._category_chips)))

        tchip = page._category_chips.get("拖拽目标分类")
        px, py = tchip.winfo_rootx() + 5, tchip.winfo_rooty() + 5
        check("落点判定命中目标分类",
              page._drop_category_at(px, py) == "拖拽目标分类",
              f"point=({px},{py}) 命中={page._drop_category_at(px, py)!r}")

        # 再动一下、动到胶囊上：这次该出现「松手就落这儿」的高亮
        e2b = ev(); e2b.widget = card; e2b.x_root = px; e2b.y_root = py
        page._on_drag_motion(e2b)
        root.update()
        check("拖到分类上时该分类进入投放高亮",
              page._drop_active_name == "拖拽目标分类",
              str(page._drop_active_name))

        e3 = ev(); e3.widget = card; e3.x_root = px; e3.y_root = py
        page._on_drag_release(e3)
        root.update()

        after = tools_db.get_tool(page.db, tid)
        check("松手后分类已落库",
              after["category"] == "拖拽目标分类",
              f"{before_category!r} -> {after['category']!r}")
        check("物理路径一字未动（分类只是逻辑归属）",
              after["path"] == before_path, after["path"])
        check("松手后影子窗口消失", page._drag_ghost is None)
        check("松手后高亮清空", page._drop_active_name is None,
              str(page._drop_active_name))
        check("松手后没收到东西的空分类又收起来",
              "诱饵空分类" not in page._category_chips,
              str(list(page._category_chips)))
        check("拖拽不新建物理目录（分类只是 DB 里的一行）",
              not (ROOT / "Tools" / "拖拽目标分类").exists())

        # ---- 原地松手 = 单击，不该改分类 ----
        fresh = tools_db.get_tool(page.db, tid)
        page._on_card_press(e, tid)
        e4 = ev(); e4.widget = card; e4.x_root = e.x_root + 1; e4.y_root = e.y_root + 1
        page._on_drag_motion(e4)
        page._on_drag_release(e4)
        root.update()
        check("原地松手（没越过阈值）不改分类",
              tools_db.get_tool(page.db, tid)["category"] == fresh["category"])

    # ---- 新建分类入口摆在分类栏里 ----
    new_chip = _chip_by_text(page._category_bar, "+ 新建分类")
    check("分类栏末尾有「+ 新建分类」入口（不埋在设置里）", new_chip is not None,
          str([c.text for c in _all_chips(page._category_bar)]))


def _assert_first_layout(root, tmp_db):
    """首帧排版：不允许「先进去竖排、0.x 秒后才跳正常」，滚动区也不许滞后。

    真实症状（用户截图）：进系统工具箱那一下先排出 2 列竖排（内容比一屏还高、
    还能滚），约 0.1~0.15 秒后才跳成 11 列；期间滚动条还能滚进一大片空白。
    成因是页面未映射时 Tk 把尺寸报成 1x1，按它算列数必然错；再加上重排要走
    140ms 防抖、scrollregion 又只靠 <Configure> 被动更新（慢一帧）。

    这里复刻真实主窗口的构建顺序：页面建好时容器还没 pack（未映射），
    切过去之后必须一次成型。
    """
    print("\n[B8] 首帧排版：不先竖排再跳 / 滚动区不滞后 / 分类横滚条")

    conn2 = sqlite3.connect(str(tmp_db))
    conn2.row_factory = sqlite3.Row
    tools_db.init_all_tool_tables(conn2)
    # 用户那台是「文件夹」排列 —— 列数跟窗口宽度走的正是它
    tools_db.set_setting(conn2, "view_mode", "folder")

    # 单独开一个窗口：和主页面共用一个 root 会平分高度，量出来的画布尺寸是假的
    win = tk.Toplevel(root)
    win.geometry("1180x820+120+120")
    holder = tk.Frame(win)                        # 故意不 pack：模拟「还没切过去」
    second = ToolsPage(holder, conn2, project_root=str(ROOT))
    second.pack(fill="both", expand=True)
    root.update()

    check("「文件夹」排列生效", second.view_mode == "folder", second.view_mode)
    check("未映射时先一个格子都不排（不按兜底列数画一遍）",
          len(second.grid_frame.winfo_children()) == 0,
          f"{len(second.grid_frame.winfo_children())} 个")
    check("标记了「等首帧」而不是硬排", second._pending_layout is True)

    # 记录每一轮排版最终定下的列数，用来确认中间没有竖排态
    seen = []
    original = second._refresh_grid

    def spy():
        original()
        seen.append(second._grid_cols_now)

    second._refresh_grid = spy

    holder.pack(fill="both", expand=True)         # 用户点了「系统工具箱」
    for _ in range(60):
        root.update()
        if second._grid_cols_now and not second._pending_layout:
            break
        time.sleep(0.01)
    # 再跑一会儿让整页几何收敛（画布高度也是一点点长起来的）
    for _ in range(30):
        root.update()
        time.sleep(0.01)

    check("切过去后首帧就排满全部工具",
          len(second.icon_widgets) == len(second._all_tools) > 0,
          f"{len(second.icon_widgets)} / {len(second._all_tools)}")
    cols = second._grid_cols_now
    check("列数跟窗口宽度走（不是兜底值 6）", cols > 6, f"列数 {cols}")
    check("中间没出现过竖排态（列数没掉到 ≤6）",
          all(c > 6 for c in seen), f"各轮列数 {seen}")
    rows = {int(c.grid_info()["row"]) for c in second.grid_frame.winfo_children()
            if c.grid_info()}
    check("排成了两行而不是一长条", rows and max(rows) <= 2, f"行 {sorted(rows)}")

    # ---- 滚动区必须和内容一样高 ----
    region = [int(v) for v in second.canvas.cget("scrollregion").split()]
    content_h = second.grid_frame.winfo_height()
    view_h = second.canvas.winfo_height()
    check("scrollregion 高 == 内容高（不滞后一帧）",
          len(region) == 4 and region[3] - region[1] == content_h,
          f"region {region} / 内容 {content_h}")
    check("前提成立：内容确实没铺满视口", content_h < view_h,
          f"内容 {content_h} / 视口 {view_h}")
    second.canvas.yview_scroll(20, "units")
    root.update()
    check("内容没铺满时滚不动（不会滚进空白）",
          tuple(second.canvas.yview()) == (0.0, 1.0), str(tuple(second.canvas.yview())))

    # ---- ★ 滚轮：装得下时不许把网格顶下去 ----
    # 上面那条 yview 断言在这条 bug 上是**假绿**：scrollregion 比视口矮时，Tk 照样改
    # 内部的 yOrigin 却不给夹回来，yview 一直报 (0,1)。要比的是**几何偏移**
    # （首格相对画布的 y）—— 原 bug 下偏移会 12 -> 150 -> 374 一路窜下去，
    # 用户看到的就是「滚轮往上转，内容整体往下窜」。
    def _first_cell_offset():
        kids = [w for w in second.grid_frame.winfo_children() if w.winfo_manager()]
        return None if not kids else kids[0].winfo_rooty() - second.canvas.winfo_rooty()

    check("前提成立：内容装得进画布", second._grid_fits_canvas())
    second.canvas.yview_moveto(0)
    root.update()
    base_off = _first_cell_offset()
    for _ in range(13):
        second._on_mousewheel(types.SimpleNamespace(delta=120))
        root.update()
    after_off = _first_cell_offset()
    check("装得下时滚轮上滚不把网格顶下去（偏移不变）",
          base_off is not None and after_off == base_off,
          f"偏移 {base_off} -> {after_off}")

    # ---- ★ 重排（等价于切分类那一下）后不许继承漏出去的偏移 ----
    second.canvas.yview_scroll(-10, "units")
    root.update()
    leaked = _first_cell_offset()
    check("前提成立：裸 yview_scroll 确实会顶走网格（原 bug 复现）",
          leaked != base_off, f"偏移 {base_off} -> {leaked}")
    second._refresh_grid()            # 切分类走的就是这条路
    root.update()
    back = _first_cell_offset()
    check("重排后视口自动归顶（不继承漏出的偏移）",
          back == base_off, f"归顶 {back}（基准 {base_off}）")

    # ---- 分类横滚条只在真放不下时出现 ----
    check("分类装得下时不挂横滚条",
          not second._cat_scroll.winfo_ismapped(),
          f"胶囊宽 {second._cat_canvas.bbox('all')[2]} / "
          f"画布宽 {second._cat_canvas.winfo_width()}")

    # ---- 窗口变窄仍要重排（防抖那条路不能被首帧逻辑吃掉） ----
    before = second._grid_cols_now
    win.geometry("640x780")
    for _ in range(80):
        root.update()
        if second._grid_cols_now != before:
            break
        time.sleep(0.01)
    for _ in range(20):
        root.update()
        time.sleep(0.01)
    check("窗口变窄后重新分列", second._grid_cols_now < before,
          f"{before} -> {second._grid_cols_now}")
    region = [int(v) for v in second.canvas.cget("scrollregion").split()]
    check("重排后滚动区仍然收敛",
          region[3] - region[1] == second.grid_frame.winfo_height(),
          f"region {region} / 内容 {second.grid_frame.winfo_height()}")

    win.destroy()
    conn2.close()


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
    test_tool_tags()
    test_tags_db()
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
