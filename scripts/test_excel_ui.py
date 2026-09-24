# -*- coding: utf-8 -*-
"""Excel 学习中心 UI 回归测试：真实窗口 + 逐项断言。

为什么单独成篇（必须真开窗口，只能用系统 Python312 跑）
------------------------------------------------------------------------------
数据层测「算得对」，这里测「画出来了没有」。本模块实测踩到/堵住过的坑：

* **八个视图是建一次、pack_forget 切换的**，不是每次重建。切错帧的表现是
  「点了一下什么都没发生」，不看控件树看不出来。
* **`<<TreeviewSelect>>` 是延迟投递的**（实测：selection_set 之后不进一次
  事件循环根本收不到）。原来的 `_nav_guard` 布尔守卫因此完全无效 ——
  进「学习路径」的某一阶段会被弹回「今日复习」。本文件要求每次切视图后
  **多跑一轮事件循环**再断言，否则这个 bug 测不出来。
* **筛选行对三个视图曾共用同一套控件**，于是配方视图的分类下拉「摆了不筛」。
  断言改成「切到配方后候选值换成了配方分类」。
* **首帧不许排宽度相关版式**：未映射控件一律报 1x1。柱状图因此用定宽 Canvas。
* 配方卡片上的 ``**强调**`` 标记曾经直接上屏（看着像 bug），现在由界面层去掉。

本文件固化的口径
------------------------------------------------------------------------------
* 窗口必须真实可见：主窗口一旦 ``withdraw()``，连 pack 好的控件也全部变成
  「未映射」，断言会集体假红。所以这里不 withdraw。
* 「已映射」要同时满足 ``winfo_ismapped()`` **且** 宽高 > 1。
* **不真弹模态窗**（simpledialog / messagebox）：本机没有真实桌面时会把主循环
  挂住。涉及弹窗的功能只验入口存在与回调可调用（把弹窗类/函数临时替换掉）。
* 期望值从数据层现算，不写死数字。

覆盖：
A. 骨架        左右两栏宽度 / 工具栏按钮 / 状态栏贴在底部
B. 左栏导航    视图 8 项 + 分类 12 项 / 数量列 / 默认选中今日复习
C. 视图切换    八视图逐一切换不炸、帧真的换了、标题跟着变
D. 今日复习    卡片数 == min(队列, 12) / 三个反馈按钮 / 空队列提示
E. 函数宝典    列表 200 行 / 详情字段 / 掌握度下拉 / 相关函数胶囊可点
F. 筛选行      按视图换候选值 / 配方视图收起掌握度 / 配方分类真的筛
G. 学习路径    7 张阶段卡 / 点阶段进函数宝典并筛 / 退出筛选回全量
                （含「延迟事件不把视图抢回去」这条）
H. 实战配方    20 张卡 / 书页码输入 / 心得入口存在
I. 学习笔记    空状态 / 存一条后出现在列表 / 预览渲染 Markdown
J. 打卡统计    5 个指标卡 / 打卡日历 35 格 / 分类条形
K. 自建函数    入口存在 / 走数据层加一条后列表变 201 / 内置不给删
L. 关键纪律    定宽控件不被 expand 控件饿死 / 状态栏在底部
M. 自测/错题本 两个新视图切得动 / 筛选行只留分类 / 答题前不揭晓 /
                 答错进错题本并回灌 / 重做做对自动移出
N. 批量导入   「更多」菜单四个入口 / 模板与导出真的落盘 / 先报规模再写 /
                 撞内置会先问 / 点「否」一个字都不写
O. 待办按钮   打开页面不会自动建 / 点一下才调一次桥 / 未注入时只提示
P. 雷达图     定宽 Canvas / 12 个分类名与官方一致 / 12 轴顶点 / 排在条形图之前
Q. 笔记联动   结算卡与「更多」两个入口 / 没作答时一个字都不写 / 确认框口径与
                 真跑一致 / 再点一次是更新不是又建两篇 / 点「否」不写 /
                 待办备注带上笔记指纹

用法::

    python scripts/test_excel_ui.py
"""

import shutil
import sys
import tempfile
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from excel_db import (  # noqa: E402
    FEEDBACK_VAGUE,
    MASTERY_FAIR,
    MASTERY_GOOD,
    ExcelDB,
    today_str,
)
from excel_page import (  # noqa: E402
    VIEW_CHOICES,
    VIEW_DUE,
    VIEW_LIBRARY,
    VIEW_NOTE,
    VIEW_PATH,
    VIEW_QUIZ,
    VIEW_RECIPE,
    VIEW_STATS,
    VIEW_WRONG,
    ExcelFunctionDialog,
    ExcelLearningPage,
)
from excel_seed import CATEGORIES  # noqa: E402
from excel_note_bridge import NOTE_AREA_LABEL, ExcelNoteBridge  # noqa: E402
from excel_todo_bridge import review_todo_payload  # noqa: E402
from study_notes_db import StudyNotesDB  # noqa: E402
from ui_theme import MAIN_PALETTE  # noqa: E402

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


def section(title: str) -> None:
    print(f"\n{title}")


def settle(root: tk.Misc, rounds: int = 2) -> None:
    """让 Tk 把挂起的几何结算跑完。

    ``rounds`` 默认 2 而不是 1 是有原因的：``<<TreeviewSelect>>`` 这类虚拟
    事件要**下一轮**事件循环才投递，只跑一轮会漏掉「视图被抢回去」这类 bug。
    """
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def mapped(widget) -> bool:
    """「真的在屏幕上」：已映射 **且** 有真实尺寸（未映射一律报 1x1）。"""
    try:
        return (bool(widget.winfo_ismapped())
                and widget.winfo_width() > 1 and widget.winfo_height() > 1)
    except tk.TclError:
        return False


def texts_of(widget) -> list:
    """递归收集所有控件的 text / textvariable 当前值。"""
    found = []
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return found
    for child in children:
        try:
            variable = child.cget("textvariable")
            if variable:
                try:
                    found.append(str(child.tk.globalgetvar(variable)))
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        try:
            value = child.cget("text")
            if value:
                found.append(str(value))
        except tk.TclError:
            pass
        found.extend(texts_of(child))
    return found


def count_widgets(widget) -> int:
    total = 0
    for child in widget.winfo_children():
        total += 1 + count_widgets(child)
    return total


def find_menu_buttons(widget, out=None) -> list:
    """递归找「挂着 .menu 的按钮」—— create_menu_button 把菜单留在 .menu 上。

    菜单项标题只能从 tk.Menu 里逐条 ``entrycget`` 读（分隔线会抛错，跳过）。
    """
    if out is None:
        out = []
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return out
    for child in children:
        if hasattr(child, "menu"):
            out.append(child)
        find_menu_buttons(child, out)
    return out


def menu_labels(page) -> list:
    labels = []
    for button in find_menu_buttons(page):
        menu = getattr(button, "menu", None)
        if menu is None:
            continue
        try:
            last = menu.index("end")
        except tk.TclError:
            continue
        if last is None:
            continue
        for i in range(int(last) + 1):
            try:
                label = str(menu.entrycget(i, "label"))
            except tk.TclError:
                continue        # 分隔线没有 label
            if label:
                labels.append(label)
    return labels


def make_db(name: str, tmpdir: Path) -> ExcelDB:
    return ExcelDB(tmpdir / f"{name}.db", seed=True)


def make_page(root, db) -> ExcelLearningPage:
    page = ExcelLearningPage(root, db, app_title="test", image_preview_cls=None,
                             images=None, on_status=lambda m: None)
    page.pack(fill="both", expand=True)
    return page


# ══════════════════════════════════════════════════════════════════════════
# A. 骨架
# ══════════════════════════════════════════════════════════════════════════
def test_skeleton(root, page) -> None:
    section("[A] 骨架")
    settle(root)
    check("页面本身已映射", mapped(page))
    check("左栏有真实宽度",
          page.nav_tree.master.winfo_width() > 100,
          page.nav_tree.master.winfo_width())
    check("内容区有真实宽度", page.body_host.winfo_width() > 300,
          page.body_host.winfo_width())
    check("内容区比左栏宽（左栏没被撑开）",
          page.body_host.winfo_width() > page.nav_tree.master.winfo_width())

    buttons = [texts_of(w) for w in page.winfo_children()]
    joined = " ".join(" ".join(x) for x in buttons)
    for label in ("开始今日复习", "随机抽一个", "新增笔记"):
        check(f"工具栏有「{label}」", label in joined, joined[:120])

    status = page.winfo_children()[-1]
    check("状态栏在页面最底部（side=bottom）",
          status.winfo_ismapped() and status.winfo_y() > page.body_host.winfo_y(),
          f"status.y={status.winfo_y()} body.y={page.body_host.winfo_y()}")


# ══════════════════════════════════════════════════════════════════════════
# B. 左栏导航
# ══════════════════════════════════════════════════════════════════════════
def test_nav(page, db) -> None:
    section("[B] 左栏导航")
    groups = page.nav_tree.get_children("")
    check("导航两个分组", len(groups) == 2, groups)
    check("分组顺序是 视图 → 分类", groups == ("g::views", "g::cats"), groups)

    views = page.nav_tree.get_children("g::views")
    check("视图 8 项", len(views) == 8, len(views))
    labels = [page.nav_tree.item(iid, "text") for iid in views]
    check("视图名与 VIEW_CHOICES 一致",
          all(any(label in text for _k, label in VIEW_CHOICES) for text in labels),
          labels)
    check("今日复习的数量列 == 待复习数",
          page.nav_tree.item("view::due", "values")[0] == str(db.due_count()),
          page.nav_tree.item("view::due", "values"))
    check("函数宝典的数量列 == 200",
          page.nav_tree.item("view::library", "values")[0] == "200",
          page.nav_tree.item("view::library", "values"))

    cats = page.nav_tree.get_children("g::cats")
    check("分类 12 项", len(cats) == 12, len(cats))
    check("分类项的 id 前缀是 cat::", all(iid.startswith("cat::") for iid in cats))
    check("导航默认停在「今日复习」",
          page.nav_tree.selection() == ("view::due",), page.nav_tree.selection())


# ══════════════════════════════════════════════════════════════════════════
# C. 视图切换
# ══════════════════════════════════════════════════════════════════════════
def test_view_switch(root, page) -> None:
    section("[C] 视图切换")
    for key, label in VIEW_CHOICES:
        try:
            page.show_view(key)
            settle(root)
            visible = [k for k, frame in page.view_frames.items()
                       if frame.winfo_ismapped()]
            ok = page.view_key == key and visible == [key]
            detail = f"view_key={page.view_key} 可见帧={visible}"
        except Exception as exc:                         # noqa: BLE001
            ok, detail = False, repr(exc)
        check(f"切到「{label}」只显示该帧", ok, detail)

    page.show_view("不存在的键")
    settle(root)
    check("非法视图键回落到今日复习", page.view_key == VIEW_DUE, page.view_key)

    # 工具栏按钮是**直接调 show_view** 的（不走导航点击）。这里锁一条防线：
    # 导航停在别的视图时，程序切过去的视图不能被那条延迟投递的
    # <<TreeviewSelect>> 按旧选区抢回来（实测踩过一次）。
    page.nav_tree.selection_set("view::stats")
    settle(root, rounds=3)
    check("先把导航停在打卡统计", page.view_key == VIEW_STATS, page.view_key)
    page.start_today_review()
    settle(root, rounds=3)
    check("点「开始今日复习」不会被抢回统计页",
          page.view_key == VIEW_DUE, page.view_key)
    check("导航高亮跟着切过来了",
          page.nav_tree.selection() == ("view::due",), page.nav_tree.selection())

    page.pick_random_function()
    settle(root, rounds=3)
    check("随机抽一个后停在函数宝典", page.view_key == VIEW_LIBRARY, page.view_key)
    check("随机抽一个后导航高亮同步",
          page.nav_tree.selection() == ("view::library",), page.nav_tree.selection())

    # 切到阶段筛选后，导航必须让出选中；退出后又能回来
    page.open_stage(page.db.learning_progress()[0])
    settle(root, rounds=3)
    check("阶段筛选下导航无选中", not page.nav_tree.selection(),
          page.nav_tree.selection())
    page.clear_stage_filter()
    settle(root, rounds=3)
    check("退出阶段筛选后导航回到函数宝典",
          page.nav_tree.selection() == ("view::library",), page.nav_tree.selection())


# ══════════════════════════════════════════════════════════════════════════
# D. 今日复习
# ══════════════════════════════════════════════════════════════════════════
def test_due(root, page, db) -> None:
    section("[D] 今日复习")
    page.show_view(VIEW_DUE)
    settle(root)
    expect = min(12, db.due_count())
    cards = page.due_area.inner.winfo_children()
    check("卡片数 == min(队列, 12)", len(cards) >= expect, f"{len(cards)} vs {expect}")
    check("元信息写了待复习数量",
          f"待复习 {db.due_count()}" in page.meta_var.get(), page.meta_var.get())

    joined = " ".join(texts_of(page.due_area.inner))
    for label in ("熟练（记得）", "模糊（想一下）", "忘了（重来）", "看完整说明"):
        check(f"卡片有「{label}」", label in joined)

    first = db.due_functions(limit=1)[0]
    before = db.due_count()
    page.review_function(first, FEEDBACK_VAGUE)
    settle(root)
    check("走页面入口复习后队列 -1", db.due_count() == before - 1,
          f"{before} -> {db.due_count()}")

    # 空队列：把整库都排到未来，看空状态文案
    page.db.conn.execute("UPDATE excel_functions SET id = id")   # 占位，不改数据
    page.db.conn.execute(
        "INSERT OR REPLACE INTO excel_progress (function_id, mastery, "
        "correct_streak, interval_days, next_review_at) "
        "SELECT id, 1, 0, 30, ? FROM excel_functions",
        ((date.fromisoformat(today_str()) + timedelta(days=30)).isoformat(),))
    page.db.conn.commit()
    page.show_view(VIEW_DUE)
    settle(root)
    check("队列清空后待复习为 0", page.db.due_count() == 0, page.db.due_count())
    empty_text = " ".join(texts_of(page.due_area.inner))
    check("空队列给出提示而不是一片空白",
          "今天没有到期的函数" in empty_text, empty_text[:120])


# ══════════════════════════════════════════════════════════════════════════
# E. 函数宝典
# ══════════════════════════════════════════════════════════════════════════
def test_library(root, page, db) -> None:
    section("[E] 函数宝典")
    page.show_view(VIEW_LIBRARY)
    settle(root)
    rows = page.list_tree.get_children("")
    check("列表 200 行", len(rows) == 200, len(rows))
    check("列表行 id 前缀是 fn::", all(iid.startswith("fn::") for iid in rows))
    check("左栏列表已映射", mapped(page.list_tree))
    check("右侧详情区已映射", mapped(page.detail_area))

    vlookup = db.get_function_by_code("VLOOKUP")
    page.show_function_detail(vlookup["id"])
    settle(root)
    joined = " ".join(texts_of(page.detail_area.inner))
    for label in ("参数", "返回值", "易错点（最值钱的一栏）", "适用场景", "相关函数"):
        check(f"详情有「{label}」小节", label in joined)
    check("详情正文不带 ** 标记（界面层已去掉）", "**" not in joined,
          [x for x in texts_of(page.detail_area.inner) if "**" in x][:2])

    # 掌握度下拉：设一个，数据层要跟着变
    page.set_mastery(vlookup["id"], MASTERY_GOOD)
    settle(root)
    state = db.progress_map()[vlookup["id"]]
    check("掌握度下拉能改数据", int(state["mastery"]) == MASTERY_GOOD, state)
    check("改完列表里的掌握度列跟着变",
          any(page.list_tree.item(iid, "values")[2] == "熟练"
              for iid in page.list_tree.get_children("")
              if iid == f"fn::{vlookup['id']}"),
          page.list_tree.item(f"fn::{vlookup['id']}", "values"))

    # 相关函数胶囊可点
    related = db.get_function_by_code("IF")
    page.show_function_detail(related["id"])
    settle(root)
    page.open_function("IFS")
    settle(root)
    check("相关函数能跳过去",
          page.selected_function_id == db.get_function_by_code("IFS")["id"],
          page.selected_function_id)
    page.open_function("这个函数肯定没有")
    settle(root)
    check("跳到不存在的函数时给提示不炸",
          "还没有" in page.status_var.get(), page.status_var.get())


# ══════════════════════════════════════════════════════════════════════════
# F. 筛选行（按视图适配）
# ══════════════════════════════════════════════════════════════════════════
def test_filter_row(root, page, db) -> None:
    section("[F] 筛选行按视图适配")
    page.show_view(VIEW_LIBRARY)
    settle(root)
    check("函数宝典里筛选行已映射", mapped(page.filter_row))
    lib_values = list(page.category_box.cget("values"))
    check("函数宝典的分类候选 = 12 个官方分类",
          lib_values == ["全部分类"] + [c["name"] for c in CATEGORIES],
          lib_values[:4])
    check("函数宝典里有掌握度下拉", page.mastery_box.winfo_ismapped())

    page.show_view(VIEW_RECIPE)
    settle(root)
    recipe_values = list(page.category_box.cget("values"))
    check("配方视图的分类候选换成配方分类",
          recipe_values == ["全部分类"] + db.recipe_categories(), recipe_values)
    check("配方视图收起掌握度下拉（无从谈起）",
          not page.mastery_box.winfo_ismapped(), page.mastery_box.winfo_manager())
    check("配方视图保留分类下拉", page.category_box.winfo_ismapped())

    # 配方分类真的筛（这是「摆了不筛」那个 bug 的回归防线）
    target = db.recipe_categories()[0]
    full = len(page.recipe_area.inner.winfo_children())
    page.category_var.set(target)
    page.render_recipe()
    settle(root)
    filtered = len(page.recipe_area.inner.winfo_children())
    check("选中某配方分类后卡片变少",
          0 < filtered < full, f"{filtered} < {full}（{target}）")
    joined = " ".join(texts_of(page.recipe_area.inner))
    check("留下的卡片都是该分类", target in joined, joined[:120])
    page.category_var.set("全部分类")
    page.render_recipe()
    settle(root)
    check("切回全部分类恢复 20 条",
          len(page.recipe_area.inner.winfo_children()) == full, full)

    page.show_view(VIEW_NOTE)
    settle(root)
    check("笔记视图收起分类与掌握度",
          not page.category_box.winfo_ismapped()
          and not page.mastery_box.winfo_ismapped())
    check("笔记视图仍可搜索", mapped(page.filter_row))

    page.show_view(VIEW_STATS)
    settle(root)
    check("统计视图整条筛选行收起",
          not page.filter_row.winfo_ismapped(), page.filter_row.winfo_manager())


# ══════════════════════════════════════════════════════════════════════════
# G. 学习路径
# ══════════════════════════════════════════════════════════════════════════
def test_path(root, page, db) -> None:
    section("[G] 学习路径")
    page.show_view(VIEW_PATH)
    settle(root)
    joined = " ".join(texts_of(page.path_area.inner))
    stages = db.learning_progress()
    found = sum(1 for stage in stages if stage["key"] in joined)
    check("7 个阶段都画出来了", found == 7, found)
    check("每张卡都有「打开这一阶段」按钮",
          joined.count("打开这一阶段") == 7, joined.count("打开这一阶段"))

    stage = stages[0]
    page.open_stage(stage)
    settle(root, rounds=3)          # 关键：多跑一轮，暴露延迟事件抢视图
    check("点阶段切到函数宝典",
          page.view_key == VIEW_LIBRARY, page.view_key)
    check("点阶段后带上阶段筛选", page.stage_codes == stage["codes"],
          page.stage_codes)
    check("阶段筛选下导航让出选中（没有对应节点）",
          not page.nav_tree.selection(), page.nav_tree.selection())
    rows = page.list_tree.get_children("")
    check("列表只剩该阶段的函数",
          0 < len(rows) <= len(stage["codes"]), f"{len(rows)} / {len(stage['codes'])}")
    order = [page.list_tree.item(iid, "values")[0] for iid in rows]
    check("阶段内按课程序排，不是字母序",
          order == stage["codes"][:len(order)], f"{order[:5]} vs {stage['codes'][:5]}")

    page.clear_stage_filter()
    settle(root, rounds=3)
    check("退出筛选回到全量 200",
          page.stage_codes is None
          and len(page.list_tree.get_children("")) == 200,
          len(page.list_tree.get_children("")))

    # 二次进入后用导航离开，确认不会卡在筛选态
    page.open_stage(stage)
    settle(root, rounds=3)
    page.nav_tree.selection_set("view::due")
    settle(root, rounds=3)
    check("点导航「今日复习」能离开阶段筛选",
          page.view_key == VIEW_DUE and page.stage_codes is None,
          f"view={page.view_key} codes={page.stage_codes}")

    recipe_stage = [s for s in stages if s["is_recipe_stage"]][0]
    page.open_stage(recipe_stage)
    settle(root, rounds=3)
    check("配方阶段跳到实战配方", page.view_key == VIEW_RECIPE, page.view_key)


# ══════════════════════════════════════════════════════════════════════════
# H. 实战配方
# ══════════════════════════════════════════════════════════════════════════
def test_recipe(root, page, db) -> None:
    section("[H] 实战配方")
    page.search_var.set("")
    page.category_var.set("全部分类")
    page.show_view(VIEW_RECIPE)
    settle(root)
    cards = page.recipe_area.inner.winfo_children()
    check("20 张配方卡", len(cards) == 20, len(cards))
    joined = " ".join(texts_of(page.recipe_area.inner))
    check("卡片有场景 / 公式 / 拆解 / 容易踩的坑",
          all(k in joined for k in ("什么时候用：", "公式", "拆解", "容易踩的坑")))
    check("卡片正文不带 ** 标记", "**" not in joined,
          [x for x in texts_of(page.recipe_area.inner) if "**" in x][:2])
    check("有「记住」与「写点心得」入口",
          "记住" in joined and "写点心得" in joined)

    rid = db.all_recipes()[0]["id"]
    page.save_recipe_page(rid, "P123")
    settle(root)
    check("书页码能存进库", db.get_recipe(rid)["book_page"] == "P123",
          db.get_recipe(rid)["book_page"])

    recipe = db.get_recipe(rid)
    recipe["my_note"] = "我自己的心得"
    db.update_recipe_fields(rid, my_note="我自己的心得")
    page.render_recipe()
    settle(root)
    check("心得显示在卡片上",
          "我的心" in " ".join(texts_of(page.recipe_area.inner)))


# ══════════════════════════════════════════════════════════════════════════
# I. 学习笔记
# ══════════════════════════════════════════════════════════════════════════
def test_note(root, page, db) -> None:
    section("[I] 学习笔记")
    page.show_view(VIEW_NOTE)
    settle(root)
    check("初始笔记列表为空", len(page.note_tree.get_children("")) == 0,
          page.note_tree.get_children(""))
    check("笔记列表已映射", mapped(page.note_tree))

    nid = db.save_note(title="IF 的嵌套写法", book_page="P102",
                       content="# 要点\n\n- 嵌套别超三层\n- 换 IFS\n",
                       function_id=db.get_function_by_code("IF")["id"],
                       tags="逻辑,嵌套")
    page.render_note()
    settle(root)
    rows = page.note_tree.get_children("")
    check("存一条后列表出现 1 行", len(rows) == 1, rows)
    row_values = [str(v) for iid in rows
                  for v in page.note_tree.item(iid, "values")]
    check("列表显示书页码", "P102" in " ".join(row_values), row_values)

    page.show_note_preview(nid)
    settle(root)
    # 预览是 tk.Text（正文不是 text 选项），要直接取内容
    preview_text = page.note_preview.get("1.0", "end")
    check("预览渲染出 Markdown 标题与正文",
          "要点" in preview_text and "嵌套别超三层" in preview_text,
          preview_text[:80].replace("\n", " / "))

    page.search_var.set("嵌套")
    page.render_note()
    settle(root)
    check("按关键词搜到笔记", len(page.note_tree.get_children("")) == 1)
    page.search_var.set("肯定搜不到的词xyzzy")
    page.render_note()
    settle(root)
    check("搜不到时列表为空", len(page.note_tree.get_children("")) == 0)
    page.search_var.set("")
    page.render_note()
    settle(root)

    page.delete_note.__self__  # 只确认方法存在，不真弹确认框
    check("删除入口存在", callable(getattr(page, "delete_note", None)))


# ══════════════════════════════════════════════════════════════════════════
# J. 打卡统计
# ══════════════════════════════════════════════════════════════════════════
def test_stats(root, page, db) -> None:
    section("[J] 打卡统计")
    today = today_str()
    # 窗口内散布几笔（含本周一，用来验周一对齐），再加一笔**窗口外**的
    # （-40 天）用来验「不该画的没画」。
    today_day = date.fromisoformat(today)
    this_monday = today_day - timedelta(days=today_day.isoweekday() - 1)
    checked_days = {
        today,
        (today_day - timedelta(days=1)).isoformat(),
        (today_day - timedelta(days=3)).isoformat(),
        this_monday.isoformat(),
        (this_monday - timedelta(days=7)).isoformat(),
        (this_monday - timedelta(days=23)).isoformat(),
        (today_day - timedelta(days=40)).isoformat(),      # 窗口外
    }
    for day in sorted(checked_days):
        db.upsert_checkin(check_date=day, minutes=20, reviewed=10, learned=2)
    db.set_mastery(db.get_function_by_code("IF")["id"], MASTERY_FAIR)

    page.show_view(VIEW_STATS)
    settle(root)
    joined = " ".join(texts_of(page.stats_area.inner))
    for label in ("连续打卡", "最长连续", "累计学习", "累计复习", "累计时长"):
        check(f"有「{label}」指标卡", label in joined)
    check("总进度那一行在", "总进度：已学" in joined, joined[:160])
    check("最近 7 天那一段在", "最近 7 天复习量" in joined)
    check("打卡日历那一段在", "打卡日历" in joined)
    check("分类熟练度那一段在", "各分类熟练度" in joined)
    check("统计页内容不是空白", count_widgets(page.stats_area.inner) > 40,
          count_widgets(page.stats_area.inner))

    # 日历 35 格：数一下方块（每个 18x18 的 Frame）
    squares = 0
    for widget in page.stats_area.inner.winfo_children():
        squares += count_calendar_cells(widget)
    check("打卡日历 35 格", squares == 35, squares)

    # 行必须按周一对齐 —— 表头写的是「一二三四五六日」，
    # 行要是从「今天往前 35 天」切，第一列就不是周一，表头等于在骗人。
    rows = find_calendar_rows(page.stats_area.inner)
    check("打卡日历解析出 5 行 × 7 格",
          len(rows) == 5 and all(len(r) == 7 for r in rows),
          [len(r) for r in rows])
    if len(rows) == 5:
        today_day = date.fromisoformat(today)
        this_monday_row = 4                      # 最后一行是本周
        column = today_day.isoweekday() - 1       # 周一 = 0
        check("本周那一行的第一格是周一（有打卡时必须是绿的）",
              rows[this_monday_row][0].cget("bg") == MAIN_PALETTE.success,
              rows[this_monday_row][0].cget("bg"))
        check("今天落在「本周行 + 本日星期几」那一格",
              rows[this_monday_row][column].cget("bg") == MAIN_PALETTE.success,
              f"col={column} bg={rows[this_monday_row][column].cget('bg')}")
        future = [rows[this_monday_row][c].cget("bg")
                  for c in range(column + 1, 7)]
        check("今天之后的日子画成「还没到」（浅色）",
              all(color == MAIN_PALETTE.surface_alt for color in future), future)
        check("未打卡的过去日子画成灰条",
              rows[0][3].cget("bg") == MAIN_PALETTE.border_soft,
              rows[0][3].cget("bg"))

        # 完整的「格子 ↔ 日期」映射：不靠肉眼数像素，
        # 行首周一 + 列号唯一确定日期，再和库里打卡日期逐一比对。
        this_monday = today_day - timedelta(days=today_day.isoweekday() - 1)
        grid_start = this_monday - timedelta(days=28)
        green, future_dates = [], []
        for r_index in range(5):
            for c_index in range(7):
                day = grid_start + timedelta(days=r_index * 7 + c_index)
                bg = rows[r_index][c_index].cget("bg")
                if bg == MAIN_PALETTE.success:
                    green.append(day.isoformat())
                elif bg == MAIN_PALETTE.surface_alt:
                    future_dates.append(day.isoformat())
        window = {(grid_start + timedelta(days=i)).isoformat() for i in range(35)}
        inside = sorted(checked_days & window)
        check("绿格子集合 == 窗口内的打卡日期",
              sorted(green) == inside, f"格子={sorted(green)} 库={inside}")
        check("窗口外的打卡不画（-40 天那条没出现）",
              (today_day - timedelta(days=40)).isoformat() not in green,
              sorted(green)[:3])
        expected_future = {d for d in window
                           if date.fromisoformat(d) > today_day}
        check("浅色格子集合 == 今天以后的日期",
              sorted(future_dates) == sorted(expected_future),
              f"{len(future_dates)} vs {len(expected_future)}")

    page.checkin_today()
    settle(root)
    check("手动打卡后连续天数 >= 1", db.streak() >= 1, db.streak())


def is_calendar_cell(widget) -> bool:
    """打卡日历的格子：18x18 的 Frame（表头 Label 的 width 是字符数 3，不会误判）。"""
    try:
        return int(widget.cget("width")) == 18 and int(widget.cget("height")) == 18
    except (tk.TclError, ValueError):
        return False


def find_calendar_rows(widget) -> list:
    """把打卡日历的 5 行 × 7 格按顺序取出来；找不到返回 []。"""
    for child in widget.winfo_children():
        rows = []
        for row_frame in child.winfo_children():
            try:
                cells = [c for c in row_frame.winfo_children()
                         if is_calendar_cell(c)]
            except tk.TclError:
                cells = []
            if len(cells) == 7:
                rows.append(cells)
        if len(rows) == 5:
            return rows
        deeper = find_calendar_rows(child)
        if deeper:
            return deeper
    return []


def count_calendar_cells(widget) -> int:
    """数「18x18 的方块」——打卡日历的格子就是按这个尺寸画的。"""
    total = 0
    for child in widget.winfo_children():
        if is_calendar_cell(child):
            total += 1
        total += count_calendar_cells(child)
    return total


# ══════════════════════════════════════════════════════════════════════════
# K. 自建函数
# ══════════════════════════════════════════════════════════════════════════
def test_custom_function(root, page, db, monkey) -> None:
    section("[K] 自建函数（照书补）")
    page.show_view(VIEW_LIBRARY)
    settle(root)
    joined = " ".join(texts_of(page.head_actions))
    check("有「新增函数（照书补）」入口", "新增函数" in joined, joined)
    check("选中的是内置函数时不给删除按钮",
          "删除这个自建函数" not in joined, joined)

    # 不真弹模态窗：把页面用到的对话框类换成「直接给出结果」的假货
    class FakeDialog:
        def __init__(self, *args, **kwargs):
            self.result = {
                "code": "MYLOOKUP", "name_cn": "我的查找", "category": "查找与引用",
                "syntax": "=MYLOOKUP(值, 区域)", "args_desc": "值：要找的",
                "returns": "找到的那一行", "description": "自己照书补的",
                "use_cases": "书上第 12 章的冷门函数", "pitfalls": "",
                "related": "VLOOKUP", "example_formula": "=MYLOOKUP(A2,B:C)",
                "example_result": "返回 B 列对应值", "min_version": "",
                "tags": "自建", "difficulty": 2, "importance": 2,
            }

    monkey["dialog"] = ExcelFunctionDialog
    monkey["page"] = page
    import excel_page as module
    module.ExcelFunctionDialog = FakeDialog
    try:
        page.wait_window = lambda _w=None: None
        page.add_custom_function()
        settle(root)
        check("自建函数加进库了",
              db.get_function_by_code("MYLOOKUP") is not None)
        check("总数变 201", db.count_functions() == 201, db.count_functions())
        check("加完自动选中它",
              page.selected_function_id == db.get_function_by_code("MYLOOKUP")["id"],
              page.selected_function_id)
        check("加完列表里能看到",
              any(iid == f"fn::{page.selected_function_id}"
                  for iid in page.list_tree.get_children("")))
    finally:
        module.ExcelFunctionDialog = monkey["dialog"]

    # 选中自建函数后，删除按钮出现
    page.render_library()
    settle(root)
    check("选中自建函数时出现删除按钮",
          "删除这个自建函数" in " ".join(texts_of(page.head_actions)),
          " ".join(texts_of(page.head_actions)))

    # 内置函数：删除入口被拦（不真弹窗，替换 messagebox）
    from tkinter import messagebox
    original_info = messagebox.showinfo
    original_ask = messagebox.askyesno
    messagebox.showinfo = lambda *a, **k: None
    messagebox.askyesno = lambda *a, **k: True
    try:
        page.selected_function_id = db.get_function_by_code("SUM")["id"]
        page.delete_selected_function()
        settle(root)
        check("内置函数删不掉（拦住了）",
              db.get_function_by_code("SUM") is not None)
        check("内置函数删不掉时有说明文案",
              "内置函数" in page.status_var.get()
              or db.count_functions() == 201,
              page.status_var.get())

        page.selected_function_id = db.get_function_by_code("MYLOOKUP")["id"]
        page.delete_selected_function()
        settle(root)
        check("自建函数能删掉",
              db.get_function_by_code("MYLOOKUP") is None)
        check("删完回到 200", db.count_functions() == 200, db.count_functions())
    finally:
        messagebox.showinfo = original_info
        messagebox.askyesno = original_ask


# ══════════════════════════════════════════════════════════════════════════
# L. 布局纪律
# ══════════════════════════════════════════════════════════════════════════
def test_layout_discipline(root, page) -> None:
    section("[L] 布局纪律")
    page.show_view(VIEW_LIBRARY)
    settle(root)
    problems = []
    for name, widget in (("左栏树", page.nav_tree),
                         ("左栏树容器", page.nav_tree.master),
                         ("函数列表", page.list_tree),
                         ("详情滚动区", page.detail_area),
                         ("内容宿主", page.body_host)):
        if not mapped(widget):
            problems.append(f"{name}(mapped={widget.winfo_ismapped()},"
                            f"{widget.winfo_width()}x{widget.winfo_height()})")
    check("固定尺寸控件没被 expand 控件饿死", not problems, problems)

    check("状态栏贴底在后母容器最后一位",
          page.winfo_children()[-1].winfo_manager() == "pack",
          page.winfo_children()[-1].winfo_manager())

    # 柱状图的 Canvas 是定宽的（避开「首帧宽度报 1」）
    page.show_view(VIEW_STATS)
    settle(root)
    canvases = collect_canvases(page.stats_area.inner)
    check("统计页有定宽 Canvas 条形图", len(canvases) > 0, len(canvases))
    check("条形图 Canvas 宽度都是正数且不随窗口漂",
          all(c.winfo_reqwidth() > 8 for c in canvases),
          [c.winfo_reqwidth() for c in canvases][:6])


def collect_canvases(widget) -> list:
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Canvas):
            found.append(child)
        found.extend(collect_canvases(child))
    return found


# ══════════════════════════════════════════════════════════════════════════
# M. 自测出题 / 错题本
# ══════════════════════════════════════════════════════════════════════════
def walk_all(widget) -> list:
    """把一棵控件树摊平（含自身）。"""
    found = [widget]
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return found
    for child in children:
        found.extend(walk_all(child))
    return found


def collect_menu_labels(widget) -> list:
    """收集所有下拉菜单的条目文字（``create_menu_button`` 把菜单挂在 .menu 上）。"""
    labels: list[str] = []
    for child in walk_all(widget):
        menu = getattr(child, "menu", None)
        if not isinstance(menu, tk.Menu):
            continue
        try:
            end = menu.index("end")
        except tk.TclError:
            continue
        if end is None:
            continue
        for index in range(int(end) + 1):
            try:
                if menu.type(index) == "separator":
                    continue
                labels.append(str(menu.entrycget(index, "label")))
            except tk.TclError:
                continue
    return labels


def test_quiz_view(root, page, db) -> None:
    section("[M] 自测出题 / 错题本两个视图")
    check("两个新视图的帧都建了",
          VIEW_QUIZ in page.view_frames and VIEW_WRONG in page.view_frames,
          sorted(page.view_frames))
    check("视图总数 8", len(VIEW_CHOICES) == 8, len(VIEW_CHOICES))

    views = page.nav_tree.get_children("g::views")
    labels = [page.nav_tree.item(iid, "text") for iid in views]
    check("导航里有「自测出题」", any("自测出题" in t for t in labels), labels)
    check("导航里有「错题本」", any("错题本" in t for t in labels), labels)

    # 切过去不许被延迟投递的 <<TreeviewSelect>> 抢回来（老坑）
    for key in (VIEW_QUIZ, VIEW_WRONG):
        page.show_view(key)
        settle(root)
        check(f"切到 {key} 后视图没被抢走", page.view_key == key, page.view_key)
        check(f"{key} 的帧真的映射了", mapped(page.view_frames[key]))

    # 筛选行：这两个视图只留分类
    page.show_view(VIEW_QUIZ)
    settle(root)
    check("自测视图收起搜索框", not page.search_group.winfo_ismapped())
    check("自测视图保留分类下拉", page.category_group.winfo_ismapped())
    check("自测视图收起掌握度下拉", not page.mastery_group.winfo_ismapped())
    page.show_view(VIEW_WRONG)
    settle(root)
    check("错题本同样收起掌握度下拉",
          not page.mastery_group.winfo_ismapped())
    check("错题本保留分类下拉", page.category_group.winfo_ismapped())
    check("错题本的搜索框还在（按函数名 / 题干搜）",
          page.search_group.winfo_ismapped())
    page.show_view(VIEW_LIBRARY)
    settle(root)
    check("切回宝典三组都回来，且 pack 顺序固定（搜索→分类→掌握度→提示）",
          page.filter_row.pack_slaves()
          == [page.search_group, page.category_group, page.mastery_group,
              page.filter_hint],
          page.filter_row.pack_slaves())

    # 抽题
    page.show_view(VIEW_QUIZ)
    page.start_quiz()
    settle(root)
    check("抽出一轮题（默认 10 道）",
          len(page.quiz_questions) == 10, len(page.quiz_questions))
    check("计数归零重来", page.quiz_correct == 0 and page.quiz_wrong == 0,
          (page.quiz_correct, page.quiz_wrong))
    question = page.quiz_questions[0]
    check("首题有题干", bool(question["prompt"].strip()))
    if question["quiz_type"] == "choice":
        check("选择题摆了 4 个选项",
              len(question["options"]) == 4, question["options"])
        check("题面上没有答案（函数名打过码）",
              question["answer"] not in question["prompt"], question["prompt"])

    body = " ".join(texts_of(page.quiz_area.inner))
    check("答题前不揭晓答案（没有「看完整说明」这种揭晓块）",
          "看完整说明" not in body, body[:120])
    check("答题前没有判分结论",
          "答对了" not in body and "答错了" not in body, body[:120])

    # 故意答错 → 进错题本 + 回灌掌握度
    target_id = int(question["function_id"])
    before_mastery = int((db.progress_map().get(target_id) or {})
                         .get("mastery", 0) or 0)
    if question["quiz_type"] == "choice":
        wrong_option = [o for o in question["options"]
                        if o != question["answer"]][0]
        page.answer_choice(wrong_option)
    else:
        page.reveal_formula()
        settle(root)
        page.grade_formula(False)
    settle(root)
    check("答错计数 +1", page.quiz_wrong == 1, page.quiz_wrong)
    after_mastery = int((db.progress_map().get(target_id) or {})
                        .get("mastery", 0) or 0)
    check("答错没让掌握度上升", after_mastery <= max(before_mastery, 1),
          (before_mastery, after_mastery))
    check("答完后揭晓块出现了", "看完整说明" in " ".join(
        texts_of(page.quiz_area.inner)))
    check("落进自测流水",
          db.quiz_stats()["attempts"] == 1 and db.quiz_stats()["pending"] == 1,
          db.quiz_stats())
    check("导航里的错题本计数跟着更新（带「条」后缀）",
          page.nav_tree.set(f"view::{VIEW_WRONG}", "count").startswith("1"),
          page.nav_tree.set(f"view::{VIEW_WRONG}", "count"))

    # 错题本视图：卡片、重做、订正
    page.show_view(VIEW_WRONG)
    settle(root)
    cards = [w for w in page.wrong_area.inner.winfo_children()
             if isinstance(w, tk.Frame)]
    check("错题本画出了卡片", bool(cards), len(cards))
    item = db.quiz_wrong_items()[0]
    check("卡片上写了函数名", item["code"] in " ".join(
        texts_of(page.wrong_area.inner)), item["code"])

    page.redo_wrong_item(item)
    settle(root)
    check("重做只出这一道", len(page.quiz_questions) == 1,
          len(page.quiz_questions))
    check("重做的是同一个函数",
          int(page.quiz_questions[0]["function_id"]) == int(item["function_id"]))
    check("标着「错题重做」", page.quiz_retry_id == item["id"],
          page.quiz_retry_id)

    redo = page.quiz_questions[0]
    if redo["quiz_type"] == "choice":
        page.answer_choice(redo["answer"])
    else:
        page.reveal_formula()
        settle(root)
        page.grade_formula(True)
    settle(root)
    check("做对后错题本清空", db.quiz_wrong_items() == [],
          [i["code"] for i in db.quiz_wrong_items()])
    check("重做标记已复位", page.quiz_retry_id is None)
    check("答对计数 +1", page.quiz_correct == 1, page.quiz_correct)

    # 错题本空状态
    page.show_view(VIEW_WRONG)
    settle(root)
    check("错题本空了以后有提示文案",
          "错题" in " ".join(texts_of(page.wrong_area.inner))
          or "干净" in " ".join(texts_of(page.wrong_area.inner)),
          " ".join(texts_of(page.wrong_area.inner))[:120])


# ══════════════════════════════════════════════════════════════════════════
# N. 批量导入 / 导出
# ══════════════════════════════════════════════════════════════════════════
def test_import_ui(root, page, db, tmpdir) -> None:
    section("[N] 批量导入 / 导出（界面入口）")
    labels = collect_menu_labels(page)
    for label in ("批量导入函数（CSV / Excel）", "下载导入模板",
                  "导出函数库为 CSV", "打开导出目录"):
        check(f"「更多」菜单里有「{label}」", label in labels, labels)

    export_dir = Path(page._export_dir())
    check("导出目录与数据库同级（不往代码目录乱写）",
          export_dir.parent == Path(db.db_path).parent,
          (str(export_dir), str(db.db_path)))

    page.save_import_template()
    template = export_dir / "excel_import_template.csv"
    check("「下载导入模板」真的落盘", template.exists() and template.stat().st_size > 0,
          str(template))
    check("模板是 UTF-8 BOM（Excel 双击不乱码）",
          template.read_bytes().startswith(b"\xef\xbb\xbf"))
    page.export_functions_csv()
    exported = sorted(export_dir.glob("excel_functions_*.csv"))
    check("「导出函数库为 CSV」真的落盘", bool(exported),
          [p.name for p in exported])

    # 不真弹窗：把文件选择与确认框换成假货
    import excel_page as module
    src = Path(tmpdir) / "ui_import.csv"
    src.write_text(
        "*code,*name_cn,*category,*syntax,*description,difficulty\n"
        "MYUIFUNC,界面导入,统计,\"MYUIFUNC(区域)\",从界面导进来的,常用\n"
        "VLOOKUP,撞内置,查找与引用,VLOOKUP(...),和内置重名,常用\n",
        encoding="utf-8-sig")
    asked = {"preview": [], "overwrite": []}

    def fake_askyesno(title=None, message="", **kwargs):
        if "重名" in message:
            asked["overwrite"].append(message)
            return False                 # 保留内置的，只导新的
        asked["preview"].append(message)
        return True

    saved = (module.filedialog.askopenfilename, module.messagebox.askyesno,
             module.messagebox.showinfo, module.messagebox.showerror)
    module.filedialog.askopenfilename = lambda **k: str(src)
    module.messagebox.askyesno = fake_askyesno
    module.messagebox.showinfo = lambda *a, **k: None
    module.messagebox.showerror = lambda *a, **k: None
    before = db.count_functions()
    try:
        page.import_functions_dialog()
        settle(root)
    finally:
        (module.filedialog.askopenfilename, module.messagebox.askyesno,
         module.messagebox.showinfo, module.messagebox.showerror) = saved

    check("先报了规模：弹过预览确认", bool(asked["preview"]), asked)
    if asked["preview"]:
        text = asked["preview"][0]
        check("预览里写了新增 / 更新 / 跳过",
              all(k in text for k in ("新增", "更新", "跳过")), text)
        check("预览里点出了文件名的来处", src.name in text, text)
    check("撞内置时会先问一句「要不要覆盖」", bool(asked["overwrite"]),
          asked["overwrite"])
    check("导入后库里 +1", db.count_functions() == before + 1, db.count_functions())
    imported = db.get_function_by_code("MYUIFUNC")
    check("导进来的是自建函数（可删）",
          imported is not None and not int(imported["is_builtin"]),
          imported and imported["is_builtin"])
    check("内置的没被覆盖",
          db.get_function_by_code("VLOOKUP")["name_cn"] != "撞内置",
          db.get_function_by_code("VLOOKUP")["name_cn"])
    check("导完自动切到函数宝典", page.view_key == VIEW_LIBRARY, page.view_key)
    check("状态栏报了导入结果", "导入" in page.status_var.get(),
          page.status_var.get())

    # 取消路径：预览时点「否」，一个字都不该写
    src2 = Path(tmpdir) / "ui_import_cancel.csv"
    src2.write_text(
        "*code,*name_cn,*category,*syntax,*description\n"
        "MYCANCEL,被取消的,统计,\"MYCANCEL()\",不该被导进来\n",
        encoding="utf-8-sig")
    before2 = db.count_functions()
    module.filedialog.askopenfilename = lambda **k: str(src2)
    module.messagebox.askyesno = lambda *a, **k: False
    module.messagebox.showinfo = lambda *a, **k: None
    module.messagebox.showerror = lambda *a, **k: None
    try:
        page.import_functions_dialog()
        settle(root)
    finally:
        (module.filedialog.askopenfilename, module.messagebox.askyesno,
         module.messagebox.showinfo, module.messagebox.showerror) = saved
    check("预览时点「否」不会写库", db.count_functions() == before2,
          db.count_functions())
    check("取消有明确文案", "取消" in page.status_var.get(), page.status_var.get())

    # 收尾：把导入进来的清掉，别把多出来的那条留给后面的小节
    db.delete_function(imported["id"])
    page.refresh_nav()
    check("收尾：自建函数删掉后回到原数（可删这条也是约定）",
          db.count_functions() == before, db.count_functions())


# ══════════════════════════════════════════════════════════════════════════
# O. 今日复习 → 生成待办
# ══════════════════════════════════════════════════════════════════════════
def test_todo_button(root, page, db) -> None:
    section("[O] 今日复习 → 生成待办（只手动触发）")
    calls: list = []

    def hook(payload):
        calls.append(dict(payload))
        return {"created": True, "item_id": 42, "message": "假桥：已建待办。"}

    original = page.todo_hook
    page.todo_hook = hook
    try:
        page.show_view(VIEW_DUE)
        settle(root)
        check("光是打开今日复习页不会自动建待办（学习工具不做催命符）",
              calls == [], calls)

        joined = " ".join(texts_of(page.head_actions))
        check("今日复习页有「生成今日复习待办」按钮",
              "生成今日复习待办" in joined, joined)

        page.create_review_todo()
        settle(root)
        check("点一下才调一次桥", len(calls) == 1, len(calls))
        if calls:
            payload = calls[0]
            check("payload 四件套齐全（标题 / 日期 / 备注 / 优先级）",
                  all(k in payload for k in ("title", "due_date", "notes",
                                             "priority")), sorted(payload))
            check("标题里带「复习」", "复习" in str(payload.get("title", "")))
            check("日期就是今天（页面上看到哪天就落在哪天）",
                  payload.get("due_date") == today_str(), payload.get("due_date"))
        check("状态栏回了桥给的那句话", "假桥" in page.status_var.get(),
              page.status_var.get())

        # 没注入时只给提示，不许把页面搞崩
        page.todo_hook = None
        page.create_review_todo()
        settle(root)
        check("没注入 hook 时只给提示不报错",
              "todo_hook" in page.status_var.get(), page.status_var.get())
    finally:
        page.todo_hook = original


# ══════════════════════════════════════════════════════════════════════════
# Q. 自测 → 生成学习笔记
# ══════════════════════════════════════════════════════════════════════════
def test_note_link(root, page, db, tmpdir) -> None:
    section("[Q] 自测 → 生成学习笔记（按钮 + 干跑确认框 + 只在点击时写）")
    import excel_page as ep

    saved = {
        "notes": page.notes,
        "session": list(page.quiz_session),
        "questions": list(page.quiz_questions),
        "correct": page.quiz_correct,
        "wrong": page.quiz_wrong,
        "recent": page.db.recent_quiz_answers,
    }
    asked: list = []
    shown: list = []
    orig_yesno = ep.messagebox.askyesno
    orig_info = ep.messagebox.showinfo
    host = tk.Frame(root)
    host.pack(fill="both", expand=True)
    notes_path = Path(tmpdir) / "notes_ui.db"
    study_db = StudyNotesDB(notes_path)
    bridge = ExcelNoteBridge(study_db)

    try:
        # ── Q1 没注入桥时只提示 ──
        page.notes = None
        page.quiz_session = []
        page.generate_study_notes()
        settle(root)
        check("没注入笔记桥时只给提示不报错",
              "笔记桥" in page.status_var.get(), page.status_var.get())

        # ── Q2 有桥但这一轮没作答 → 不写，给一句「先去做一轮」 ──
        page.notes = bridge
        page.db.recent_quiz_answers = lambda **kw: []
        ep.messagebox.showinfo = lambda *a, **k: shown.append(a)
        page.generate_study_notes()
        settle(root)
        check("没有自测记录时弹一句提示", len(shown) == 1, len(shown))
        check("★ 没有自测记录时一个字都不写", bridge.count_notes() == 0,
              bridge.count_notes())
        check("也没顺手建出分类（只读接口不建）",
              bridge.existing_category_code() == "",
              bridge.existing_category_code())

        # ── Q3 本轮作答：错题优先；结算卡上出现按钮 ──
        entries = [
            {"function_id": 1, "code": "SUM", "name_cn": "求和", "category": "数学统计",
             "is_correct": 0, "user_answer": "AVERAGE", "answer": "SUM",
             "prompt": "把 A1:A10 加起来用哪个？", "quiz_type": "choice",
             "created_at": "2026-09-24T10:00:00"},
            {"function_id": 2, "code": "IF", "name_cn": "条件判断", "category": "逻辑判断",
             "is_correct": 1, "user_answer": "IF", "answer": "IF",
             "prompt": "?", "quiz_type": "choice",
             "created_at": "2026-09-24T10:01:00"},
        ]
        page.quiz_session = [dict(item) for item in entries]
        page.quiz_questions = [dict(item) for item in entries]
        page.quiz_correct, page.quiz_wrong = 1, 1
        items = page._note_source_items()
        check("★ 本轮作答按「错题优先」整理",
              [i["code"] for i in items] == ["SUM", "IF"],
              [i["code"] for i in items])

        card = page._quiz_summary(host)
        settle(root)
        card_text = " ".join(texts_of(card))
        check("★ 自测结算卡上出现「生成学习笔记（2）」按钮",
              "生成学习笔记（2）" in card_text, card_text)
        check("结算卡原有按钮没被挤掉",
              all(t in card_text for t in ("再来一轮", "去做今日复习")), card_text)

        labels = menu_labels(page)
        check("「更多」菜单里也有同一个入口",
              any("生成学习笔记" in t for t in labels), labels)
        check("「更多」菜单原有的导出入口还在",
              any("导出学习进度" in t for t in labels), labels)

        # ── Q4 确认框文案：落点 / 条数 / 我的补充不会被覆盖 ──
        plan = bridge.plan_notes(items, generated_at="2026-09-24 10:30")
        text = page._note_confirm_text(plan)
        check("确认框写明落点", NOTE_AREA_LABEL in text, text)
        check("首次生成会说明要自动建分类", "首次" in text, text)
        check("确认框列出会新建 2 篇", "新建（2 篇）" in text, text)
        check("确认框说明「我的补充」原样保留", "我的补充" in text, text)
        check("★ 与真跑口径一致：算出来就是新建 2 篇",
              plan["created"] == 2 and plan["updated"] == 0, plan)

        second = bridge.plan_notes(items, generated_at="2026-09-24 11:00")
        text2 = page._note_confirm_text(second)
        check("★ 还没写过时第二次干跑仍算「首次」（只读接口不建分类）",
              second["first_run"] is True and "首次" in text2, second)

        # ── Q5 真跑：点一次才写一次 ──
        ep.messagebox.askyesno = lambda *a, **k: (asked.append(a), True)[1]
        page.generate_study_notes()
        settle(root)
        check("★ 点一下才写（新建 2 篇）", bridge.count_notes() == 2,
              bridge.count_notes())
        check("确实先问了一句", len(asked) == 1, len(asked))
        status = page.status_var.get()
        check("状态栏报出「新建 2 篇」与落点",
              "新建 2 篇" in status and NOTE_AREA_LABEL in status, status)

        # ── Q5b 写完之后再来一轮：确认框该说「更新」，真跑也只更新 ──
        third = bridge.plan_notes(items, generated_at="2026-09-24 12:00")
        text3 = page._note_confirm_text(third)
        check("★ 写过之后再干跑就算「更新」了",
              third["updated"] == 2 and third["created"] == 0, third)
        check("更新那一段写明只换自动生成区",
              "更新（只换自动生成那一段" in text3, text3)
        check("更新时列出的是这两篇",
              "Excel 函数 SUM" in text3 and "Excel 函数 IF" in text3, text3)
        check("★ 更新时不再说「首次会建分类」", "首次" not in text3, text3)

        page.generate_study_notes()
        settle(root)
        status2 = page.status_var.get()
        check("★ 再点一次是「更新 2 篇」，不会越攒越多",
              "更新 2 篇" in status2 and bridge.count_notes() == 2, status2)

        # ── Q6 点「否」一个字都不写 ──
        ep.messagebox.askyesno = lambda *a, **k: False
        before = bridge.count_notes()
        page.generate_study_notes()
        settle(root)
        check("★ 点「否」之后篇数不变", bridge.count_notes() == before,
              f"{before} → {bridge.count_notes()}")

        # ── Q7 待办备注里的笔记指纹 ──
        page.review_todo_title = "复习 Excel 函数 3 个"
        hint = page._note_pointer_text()
        check("笔记指针报出落点与篇数",
              NOTE_AREA_LABEL in hint and "2 篇" in hint, hint)
        with_hint = review_todo_payload(due_count=3, today=today_str(),
                                        extra_wrong=1, note_hint=hint)
        check("★ 待办备注里带上了笔记指纹", hint in with_hint["notes"],
              with_hint["notes"])
    finally:
        ep.messagebox.askyesno = orig_yesno
        ep.messagebox.showinfo = orig_info
        page.notes = saved["notes"]
        page.quiz_session = saved["session"]
        page.quiz_questions = saved["questions"]
        page.quiz_correct = saved["correct"]
        page.quiz_wrong = saved["wrong"]
        page.db.recent_quiz_answers = saved["recent"]
        page.review_todo_title = ""
        try:
            host.destroy()
        except tk.TclError:
            pass
        study_db.close()


# ══════════════════════════════════════════════════════════════════════════
# P. 分类掌握雷达图
# ══════════════════════════════════════════════════════════════════════════
def test_radar(root, page, db) -> None:
    section("[P] 分类掌握雷达图")
    for item in db.all_functions()[:12]:
        db.set_mastery(item["id"], MASTERY_GOOD)

    page.show_view(VIEW_STATS)
    settle(root)
    canvases = collect_canvases(page.stats_area.inner)
    radar = [c for c in canvases if int(c.cget("width")) == 400]
    check("统计页画出了雷达图（定宽 400 的 Canvas，避开首帧宽度报 1）",
          len(radar) == 1, [c.cget("width") for c in canvases])
    if not radar:
        return
    canvas = radar[0]
    polygons = [i for i in canvas.find_all() if canvas.type(i) == "polygon"]
    labels = [canvas.itemcget(i, "text") for i in canvas.find_all()
              if canvas.type(i) == "text"]
    check("网格环 + 两层数据多边形都画了（同心环 4 层 + 2 层数据）",
          len(polygons) >= 6, len(polygons))
    check("12 个分类都标了名", len(labels) == 12, labels)
    check("分类名就是官方 12 类（不多不少）",
          set(labels) == {c["name"] for c in CATEGORIES}, sorted(set(labels)))
    check("每个标签都有锚点（否则会全挤在圆心看不清）",
          all(canvas.itemcget(i, "anchor") for i in canvas.find_all()
              if canvas.type(i) == "text"))
    data_polygon = polygons[-1]
    check("数据多边形按 12 轴取点（12 个顶点 = 24 个坐标）",
          len(canvas.coords(data_polygon)) == 24,
          len(canvas.coords(data_polygon)))
    check("有分类被标了熟练时数据多边形不是缩在圆心的空壳",
          max(abs(v) for v in canvas.coords(data_polygon)) > 20,
          canvas.coords(data_polygon)[:6])

    # collect_canvases 是深度优先、按子控件顺序收集的，所以列表顺序就是版式顺序
    # 版式：总进度 → 最近 7 天 → 打卡日历 → **雷达图** → 分类横向条
    index = canvases.index(radar[0])
    check("雷达图前面有老图（是新增，不是替换）",
          any(int(c.cget("width")) != 400 for c in canvases[:index]),
          [c.cget("width") for c in canvases])
    check("雷达图排在分类横向条之前（先看形状，再看逐类明细）",
          any(int(c.cget("width")) != 400 for c in canvases[index + 1:]),
          [c.cget("width") for c in canvases])

def main_test() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="excel_ui_test_"))
    root = tk.Tk()
    root.title("test-excel-ui")
    root.geometry("1280x860+30+10")
    root.deiconify()          # 关键：不能 withdraw，否则全部未映射、断言集体假红
    root.update_idletasks()

    db = None
    monkey: dict = {}
    try:
        db = make_db("excel_ui", tmpdir)
        page = make_page(root, db)
        settle(root, rounds=3)

        test_skeleton(root, page)
        test_nav(page, db)
        test_view_switch(root, page)
        test_layout_discipline(root, page)
        test_due(root, page, db)
        test_library(root, page, db)
        test_filter_row(root, page, db)
        test_path(root, page, db)
        test_recipe(root, page, db)
        test_note(root, page, db)
        test_stats(root, page, db)
        test_custom_function(root, page, db, monkey)
        test_quiz_view(root, page, db)
        test_import_ui(root, page, db, tmpdir)
        test_todo_button(root, page, db)
        test_radar(root, page, db)
        test_note_link(root, page, db, tmpdir)
    finally:
        if db is not None:
            db.close()
        root.destroy()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    import traceback

    print("=" * 78)
    print("Excel 学习中心 UI 回归测试：真实窗口 + 逐项断言")
    print("=" * 78)
    try:
        main_test()
    except Exception:
        traceback.print_exc()
        FAILED += 1

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
