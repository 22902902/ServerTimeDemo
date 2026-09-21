# -*- coding: utf-8 -*-
"""待办页面 UI 回归测试：真实窗口 + 样例数据 + 逐项断言。

为什么单独成篇（且必须有 tkinter，用系统 Python312 跑）
------------------------------------------------------------------------------
todo_page.py 里的坑几乎全是「代码写了、界面上却没有」，光看源码看不出来：
控件被 expand 的内容区饿死到 0 像素、Toplevel 的 master 不是 root、
占位提示被当成用户输入写进库、菜单对象被 GC 掉导致「点了没反应」。
这些只有把真窗口建出来、量过 winfo_ismapped / winfo_width 才能发现。

本文件固化的口径（都是已经踩过的坑）
------------------------------------------------------------------------------
* 窗口必须真实可见：主窗口一旦 withdraw()，连 pack 好的控件也会全部
  变成「未映射」，断言会集体假红。所以这里不 withdraw。
* 弹窗的 master 是页面而不是 root，找 Toplevel 必须递归整棵树。
* 输入框的占位提示会被写进 textvariable，必须专门断言它没被当成用户输入。
* 菜单不能真的 tk_popup —— 本机没有真实桌面，弹出会挂住主循环。
  做法是把 _show_menu 换成记录器，只验证「调用路径通 + 菜单项结构对」。
* 期望值尽量从数据层现算（db.count_by_scope / fetch_items），而不是写死
  数字：样例数据的日期是跟着「今天」走的，写死就会换个日子假红。

覆盖：
A. 骨架       三栏宽度与可见性
B. 侧栏       智能分组 / 清单行 / 计数 / 选中态
C. 中栏       条目行、自绘勾选框、行高、滚动区同步
D. 详情       备注 / 属性行 / 子任务
E. 搜索       占位提示与关键词过滤
F. 弹窗       新建列表 / 日历（今天高亮）/ 节假日日历（中文类型）
G. 写入       选日期必须跳过节假日；重复项不受影响
H. 快速新建   占位提示不得入库
I. 勾选       单次 vs 重复（留快照 + 推进）
J. 视图切换   智能分组 ↔ 真实清单
K. 菜单       8 个入口全部可走通，结构合法
L. 资产       图标字典一一对应、图标盘按当前颜色渲染

用法：
    python scripts/test_todo_ui.py
"""

import sys
import tempfile
import traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import tkinter as tk                              # noqa: E402
from tkinter import ttk                           # noqa: E402

import todo_icons                                 # noqa: E402
import todo_page                                  # noqa: E402
from todo_db import LIST_ICONS, TodoDB, day_str    # noqa: E402
from todo_page import (                           # noqa: E402
    MIDDLE_WIDTH,
    SIDEBAR_WIDTH,
    ScrollArea,
    TodoPage,
)
from ui_theme import MAIN_PALETTE, THEME          # noqa: E402

PASSED = 0
FAILED = 0

# 详情 / 子任务 / 智能分组实际用到的线性图标名（改名前先改这里）
REQUIRED_GLYPHS = {
    "sun", "calendar", "clock", "repeat", "priority", "flag", "list",
    "tag", "subtask", "plus", "bell", "search", "trash", "chevron_right", "note",
}


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


# ===========================================================================
# 窗口无关的小工具
# ===========================================================================
def text_of(widget) -> str:
    """把控件树里所有 text 拼起来，用来判断「界面上到底有没有这行字」。"""
    out: list[str] = []

    def walk(w):
        for child in w.winfo_children():
            try:
                t = child.cget("text")
                if t:
                    out.append(str(t))
            except tk.TclError:
                pass
            walk(child)

    walk(widget)
    return " | ".join(out)


def toplevels(widget) -> list:
    """递归找弹窗：Toplevel 的 master 是页面，不一定是 root。"""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Toplevel):
            found.append(child)
        found.extend(toplevels(child))
    return found


def descend(widget, cls) -> list:
    out = []
    for child in widget.winfo_children():
        if isinstance(child, cls):
            out.append(child)
        out.extend(descend(child, cls))
    return out


# ===========================================================================
# 样例数据
# ===========================================================================
def build_data(db: TodoDB) -> dict:
    """造一份覆盖各视图的样例数据。

    除两处刻意留默认的项目外，日期都显式 skip_holidays=0 —— 否则
    「今天」若正好落在休息日，日期会被自动挪到下一个工作日，
    「今天」视图的条数就跟预期对不上了。
    """
    lists = {l.name: l for l in db.fetch_lists()}
    work, life, remind = lists["工作"], lists["生活"], lists["提醒事项"]
    today = date.today()

    overdue = db.add_item({"title": "把上周的周报补齐", "list_id": work.id,
                           "due_date": day_str(today - timedelta(days=4)),
                           "skip_holidays": 0})
    long_item = db.add_item({
        "title": "提交季度预算表", "list_id": work.id, "due_date": day_str(today),
        "due_time": "18:00", "priority": 3,
        "notes": "记得附上去年的对比表，以及本季度的差异说明。",
    })
    daily = db.add_item({"title": "每天背 30 个单词", "list_id": life.id,
                         "due_date": day_str(today), "repeat_rule": "daily",
                         "priority": 1, "skip_holidays": 0})
    db.add_item({"title": "每周复盘", "list_id": work.id, "due_date": day_str(today),
                 "repeat_rule": "weekly", "skip_holidays": 0})
    db.add_item({"title": "体检预约", "list_id": life.id,
                 "due_date": day_str(today + timedelta(days=9)), "skip_holidays": 0})
    db.add_item({"title": "给车做保养", "list_id": life.id,
                 "due_date": day_str(today + timedelta(days=25)), "flagged": 1,
                 "tags": ["车", "家庭"], "skip_holidays": 0})
    with_sub = db.add_item({"title": "读《系统之美》第 3 章", "list_id": remind.id,
                            "due_date": day_str(today), "skip_holidays": 0})
    for text in ("整理第一章笔记", "做课后习题"):
        db.add_subtask(with_sub, text)
    db.set_subtask_completed(db.fetch_subtasks(with_sub)[0].id, True)

    return {"work": work, "life": life, "remind": remind, "today": today,
            "overdue": overdue, "long": long_item, "daily": daily,
            "with_sub": with_sub}


# ===========================================================================
# A. 骨架
# ===========================================================================
def test_skeleton(page: TodoPage) -> None:
    section("[A] 骨架：三栏")
    check("页面已映射", page.winfo_ismapped() == 1,
          f"{page.winfo_width()}x{page.winfo_height()}")
    check(f"左侧栏宽 {SIDEBAR_WIDTH}", page.sidebar.winfo_width() == SIDEBAR_WIDTH,
          f"实际 {page.sidebar.winfo_width()}")
    check(f"中栏宽 {MIDDLE_WIDTH}", page.middle.winfo_width() == MIDDLE_WIDTH,
          f"实际 {page.middle.winfo_width()}")
    check("详情栏分到剩余宽度", page.detail.winfo_width() > 300,
          f"w={page.detail.winfo_width()}")
    check("三个面板都可见",
          all(p.winfo_ismapped() == 1 for p in (page.sidebar, page.middle, page.detail)),
          f"{[ (p.winfo_class(), p.winfo_ismapped()) for p in (page.sidebar, page.middle, page.detail)]}")


# ===========================================================================
# B. 侧栏
# ===========================================================================
def test_sidebar(page: TodoPage, db: TodoDB) -> None:
    section("[B] 侧栏：智能分组与清单")
    check("智能分组 5 项", len(page._smart_rows) == 5, f"n={len(page._smart_rows)}")
    check("清单行 3 条", len(page._list_rows) == 3, f"n={len(page._list_rows)}")
    check("智能分组行都有图标",
          all(r["icon"].cget("image") for r in page._smart_rows.values()))
    check("清单行都有彩色图标",
          all(r["icon"].cget("image") for r in page._list_rows.values()))

    row = page._smart_rows["today"]
    expect = str(db.count_by_scope()["today"])
    check("「今天」行的计数与数据层一致",
          row["count"].cget("text") == expect,
          f"界面 {row['count'].cget('text')} / 数据层 {expect}")
    check("「今天」行处于选中态（左侧强调条为强调色）",
          row["accent"].cget("bg") == MAIN_PALETTE.accent, row["accent"].cget("bg"))
    check("未选中的分组没有强调条",
          page._smart_rows["flagged"]["accent"].cget("bg") != MAIN_PALETTE.accent,
          page._smart_rows["flagged"]["accent"].cget("bg"))


# ===========================================================================
# C. 中栏列表
# ===========================================================================
def test_list(page: TodoPage, db: TodoDB) -> None:
    section("[C] 中栏：条目行与滚动区")
    rows = page._row_widgets
    expect = len(db.fetch_items(scope="today"))
    check("今天视图的行数与数据层一致", len(rows) == expect,
          f"界面 {len(rows)} / 数据层 {expect}")
    check("所有条目行均已映射", all(r.winfo_ismapped() == 1 for r in rows.values()))
    check("每行都有自绘勾选框图",
          all(page._find_check(r) is not None and bool(page._find_check(r).cget("image"))
              for r in rows.values()))

    heights = sorted(r.winfo_height() for r in rows.values())
    check("行高在合理区间（28~80px）",
          bool(heights) and 28 <= heights[0] and heights[-1] <= 80,
          f"min={heights[0] if heights else '-'} max={heights[-1] if heights else '-'}")

    region = page.list_area.canvas.bbox("all")
    inner_h = page.list_area.inner.winfo_height()
    check("滚动区高度与内容同步（不滞后一帧）",
          bool(region) and abs((region[3] - region[1]) - inner_h) <= 6,
          f"region_h={region[3] - region[1] if region else '-'} inner_h={inner_h}")
    check("内容未溢出时滚动条推不动",
          page.list_area.canvas.yview() == (0.0, 1.0),
          str(page.list_area.canvas.yview()))


# ===========================================================================
# D. 详情
# ===========================================================================
def test_detail(page: TodoPage, db: TodoDB, data: dict) -> None:
    section("[D] 详情面板")

    page.select_item(data["with_sub"])
    settle(page)
    check("详情区已映射",
          page._detail_area is not None and page._detail_area.winfo_ismapped() == 1)
    check("空态已让位", page._empty_state.winfo_ismapped() == 0)
    check("标题写回输入框", page.title_var.get() == "读《系统之美》第 3 章",
          page.title_var.get())
    check("子任务区 2 行", len(page._subtask_holder.winfo_children()) == 2,
          f"n={len(page._subtask_holder.winfo_children())}")
    check("子任务计数显示 1/2", "1/2" in page._subtask_counter.cget("text"),
          page._subtask_counter.cget("text"))

    csv = text_of(page._detail_area.inner)
    for key in ("备注", "日期", "时间", "重复", "优先级", "旗标", "列表", "标签", "跳过节假日"):
        check(f"详情含「{key}」行", key in csv)
    check("日期显示为中文（今天）", "今天" in csv)

    # 重复项 + 优先级 + 清单归属
    page.select_item(data["daily"])
    settle(page)
    csv = text_of(page._detail_area.inner)
    check("重复显示为「每天」", "每天" in csv)
    check("优先级显示为「低  !」", "低  !" in csv)
    check("清单归属显示为「生活」", "生活" in csv)
    check("没有子任务时计数只剩标题",
          page._subtask_counter.cget("text") == "子任务",
          page._subtask_counter.cget("text"))

    # 长备注回填 + 时间
    page.select_item(data["long"])
    settle(page)
    csv = text_of(page._detail_area.inner)
    check("长备注已回填", "对比表" in page._notes_value())
    check("时间显示 18:00", "18:00" in csv)

    # 属性行高度是否被拉伸
    meta_parent = None
    for child in page._detail_area.inner.winfo_children():
        for gc in child.winfo_children():
            if gc.winfo_class() == "Frame" and len(gc.winfo_children()) >= 8:
                meta_parent = gc
    meta_heights = ([c.winfo_height() for c in meta_parent.winfo_children()]
                    if meta_parent else [])
    check("属性行高在合理区间（22~44px）",
          bool(meta_heights) and 22 <= min(meta_heights) and max(meta_heights) <= 44,
          f"{meta_heights}")


# ===========================================================================
# E. 搜索
# ===========================================================================
def test_search(page: TodoPage, db: TodoDB) -> None:
    section("[E] 搜索框：占位提示与过滤")
    check("占位提示文案为「搜索」", getattr(page, "_search_placeholder", None) == "搜索",
          repr(getattr(page, "_search_placeholder", None)))
    check("占位提示已写进输入框", page.search_var.get() == "搜索",
          repr(page.search_var.get()))

    page._select_side("smart", "all")
    settle(page)
    total = len(db.fetch_items(scope="all"))
    page._on_search_change()
    check("占位提示不会被当成关键词", page.keyword == "", repr(page.keyword))
    check("占位状态下仍显示全部条目", len(page._row_widgets) == total,
          f"界面 {len(page._row_widgets)} / 数据层 {total}")

    page.search_var.set("周报")
    page._on_search_change()
    settle(page)
    hits = len(db.fetch_items(scope="all", keyword="周报"))
    check("输入关键词后生效", page.keyword == "周报", repr(page.keyword))
    check("中栏跟着关键词收敛（与数据层一致）",
          hits >= 1 and len(page._row_widgets) == hits,
          f"界面 {len(page._row_widgets)} / 数据层 {hits}")

    page.search_var.set("")
    page._on_search_change()
    settle(page)
    check("清空后恢复全部", page.keyword == "" and len(page._row_widgets) == total,
          f"keyword={page.keyword!r} rows={len(page._row_widgets)}")


# ===========================================================================
# F. 弹窗
# ===========================================================================
def test_new_list_dialog(page: TodoPage, root) -> None:
    section("[F-1] 弹窗：新建列表")
    before = set(toplevels(root))
    page.new_list_dialog()
    settle(page)
    new = [w for w in toplevels(root) if w not in before]
    check("新建列表弹窗可构造", len(new) == 1, f"n={len(new)}")
    if not new:
        return
    dlg = new[0]
    csv = text_of(dlg)
    check("含「列表名称」", "列表名称" in csv)
    check("含「颜色」", "颜色" in csv)
    check("含「图标」", "图标" in csv)
    check("弹窗高度贴合内容（不满屏留白）", dlg.winfo_height() < 620,
          f"h={dlg.winfo_height()}")

    # 图标盘：20 个图标都要有图，且同一颜色下彼此不同（不是 20 个一样的灰块）
    icon_labels = [w for w in descend(dlg, tk.Label) if str(w.cget("image"))]
    check("图标盘 + 预览至少 21 个位图", len(icon_labels) >= 21, f"n={len(icon_labels)}")
    images = {str(w.cget("image")) for w in icon_labels}
    check("这些位图彼此不同（图标确实按名字区分）", len(images) >= 20,
          f"去重后 {len(images)}")

    for w in new:
        w.destroy()
    settle(page)


def test_calendar_dialog(page: TodoPage, root, data: dict) -> None:
    section("[F-2] 弹窗：日期选择（今天要高亮）")
    before = set(toplevels(root))
    page._pick_date_dialog(data["long"])
    settle(page)
    new = [w for w in toplevels(root) if w not in before]
    check("日历弹窗可构造", len(new) == 1, f"n={len(new)}")
    if not new:
        return
    dlg = new[0]
    csv = text_of(dlg)
    check("含月份标题", "年" in csv and "月" in csv)
    check("含「上个/下个月」导航", "上个月" in csv and "下个月" in csv)
    check("提示「选它会自动落到工作日」", "工作日" in csv)

    today = date.today()
    day_cells = [w for w in descend(dlg, tk.Label)
                 if str(w.cget("text")) == str(today.day)]
    check("日历里能找到今天的日号", len(day_cells) >= 1, f"n={len(day_cells)}")
    painted = [w for w in day_cells
               if str(w.cget("bg")) == MAIN_PALETTE.sidebar_active]
    check("今天那格有底色高亮（不只是字色）", len(painted) == 1,
          f"底色={[str(w.cget('bg')) for w in day_cells]}")

    for w in new:
        w.destroy()
    settle(page)


def test_holiday_dialog(page: TodoPage, root, db: TodoDB) -> None:
    section("[F-3] 弹窗：节假日日历")
    before = set(toplevels(root))
    page.manage_holidays_dialog()
    settle(page)
    new = [w for w in toplevels(root) if w not in before]
    check("节假日弹窗可构造", len(new) == 1, f"n={len(new)}")
    if not new:
        return
    dlg = new[0]

    combos = descend(dlg, ttk.Combobox)
    check("有类型下拉", len(combos) == 1, f"n={len(combos)}")
    if combos:
        values = [str(v) for v in combos[0].cget("values")]
        check("类型下拉是中文（不暴露内部值）",
              values == ["放假", "调休上班"], f"实际 {values}")
        check("下拉默认选中「放假」", str(combos[0].get()) == "放假",
              str(combos[0].get()))

    areas = descend(dlg, ScrollArea)
    check("有可滚动的日历区", len(areas) >= 1, f"n={len(areas)}")
    if areas:
        rows = [c for c in areas[0].inner.winfo_children() if isinstance(c, tk.Frame)]
        check("日历列出了记录", len(rows) > 20, f"n={len(rows)}")
        names = [c.winfo_children() for c in rows]
        names = [c for c in names if len(c) >= 3]
        work_rows = [c for c in names if str(c[1].cget("text")) == "调休上班"]
        check("列出 6 条调休上班（2026）", len(work_rows) == 6, f"n={len(work_rows)}")
        check("调休上班行的名称列留空（类型列已说明）",
              all(str(c[2].cget("text")) == "" for c in work_rows),
              f"实际 {[str(c[2].cget('text')) for c in work_rows]}")
        holiday_rows = [c for c in names if str(c[1].cget("text")) == "放假"]
        check("放假行都有节日名",
              all(str(c[2].cget("text")) for c in holiday_rows),
              f"实际 {[str(c[2].cget('text')) for c in holiday_rows]}")

    for w in new:
        w.destroy()
    settle(page)


# ===========================================================================
# G. 日期写入
# ===========================================================================
def test_due_write(page: TodoPage, db: TodoDB, data: dict) -> None:
    section("[G] 选日期必须跳过节假日")
    saturday = date(2026, 9, 26)          # 中秋假期里的周六
    page.select_item(data["long"])
    settle(page)

    page._set_due(db.get_item(data["long"]), saturday)
    check("选到中秋假期会自动落到工作日",
          db.get_item(data["long"]).due_date == "2026-09-28",
          db.get_item(data["long"]).due_date)
    page._set_due(db.get_item(data["long"]), date(2026, 10, 3))   # 国庆里的周六
    check("选到国庆假期会一路跳到 10-08",
          db.get_item(data["long"]).due_date == "2026-10-08",
          db.get_item(data["long"]).due_date)

    page._set_due(db.get_item(data["daily"]), saturday)
    check("重复项不被 _set_due 改日期（推进交给重复规则自己）",
          db.get_item(data["daily"]).due_date == "2026-09-26",
          db.get_item(data["daily"]).due_date)

    page._set_due(db.get_item(data["long"]), None)
    check("清空日期写空串", db.get_item(data["long"]).due_date == "")
    page._set_due(db.get_item(data["long"]), data["today"])
    page._set_due(db.get_item(data["daily"]), data["today"])
    settle(page)


# ===========================================================================
# H. 快速新建
# ===========================================================================
def test_quick_add(page: TodoPage, db: TodoDB) -> None:
    section("[H] 快速新建：占位提示不得入库")
    n0 = len(db.fetch_items(scope="all"))
    page._restore_placeholder(page.quick_entry, page.quick_var,
                              page._quick_placeholder)
    check("占位提示能恢复", page.quick_var.get() == page._quick_placeholder,
          page.quick_var.get())

    page.quick_add()                       # 此刻框里只有占位提示
    settle(page)
    check("占位提示不会被当成待办写入", len(db.fetch_items(scope="all")) == n0,
          f"{n0} -> {len(db.fetch_items(scope='all'))}")
    check("库里不存在名为占位提示的待办",
          page._quick_placeholder not in
          [i.title for i in db.fetch_items(scope="all", include_completed=True)])

    page.quick_var.set("探针写入的一条待办")
    page.quick_add()
    settle(page)
    check("快速新建生效", len(db.fetch_items(scope="all")) == n0 + 1,
          f"{n0} -> {len(db.fetch_items(scope='all'))}")
    check("新建后自动选中新条目", page.title_var.get() == "探针写入的一条待办",
          page.title_var.get())


# ===========================================================================
# I. 勾选
# ===========================================================================
def test_toggle(page: TodoPage, db: TodoDB, data: dict) -> None:
    section("[I] 勾选：单次 vs 重复")
    page.toggle_complete(db.get_item(data["daily"]).id)
    settle(page)
    left = [i for i in db.fetch_items(scope="all") if i.repeat_rule == "daily"]
    check("重复项勾选后仍存在（推进而非完成）", len(left) == 1, f"n={len(left)}")
    check("重复项日期已推进到今天之后",
          bool(left) and left[0].due_date > day_str(data["today"]),
          left[0].due_date if left else "")
    check("已完成区出现一条快照", len(db.fetch_items(scope="completed")) == 1,
          f"n={len(db.fetch_items(scope='completed'))}")

    page.toggle_complete(data["long"])
    settle(page)
    check("单次项勾选后进入已完成", db.get_item(data["long"]).completed == 1)


# ===========================================================================
# J. 视图切换
# ===========================================================================
def test_scope_switch(page: TodoPage, db: TodoDB, data: dict) -> None:
    section("[J] 视图切换")
    work = data["work"]
    page._select_side("list", work.id)
    settle(page)
    check("切到「工作」后中栏标题变清单名",
          page.mid_title.cget("text") == "工作", page.mid_title.cget("text"))
    check("清单视图标题用清单自己的颜色",
          page.mid_title.cget("fg") == work.color, page.mid_title.cget("fg"))
    expect = len(db.fetch_items(scope="list", list_id=work.id))
    check("清单视图不再插分组标题（分组只在智能视图出现）",
          len(page._row_widgets) == expect,
          f"界面 {len(page._row_widgets)} / 数据层 {expect}")
    check("侧栏「工作」行进入选中态",
          page._list_rows[work.id]["accent"].cget("bg") == MAIN_PALETTE.accent)

    page._select_side("smart", "completed")
    settle(page)
    check("切到「已完成」能列出条目", len(page._row_widgets) >= 1,
          f"n={len(page._row_widgets)}")

    page._select_side("smart", "today")
    settle(page)
    check("切回「今天」", page.current_scope == "today")


# ===========================================================================
# K. 菜单
# ===========================================================================
def test_menus(page: TodoPage, db: TodoDB, data: dict) -> None:
    section("[K] 菜单入口（不真弹，只验调用路径与结构）")
    src = __import__("inspect").getsource(todo_page)
    check("_show_menu 已定义",
          callable(getattr(todo_page.TodoPage, "_show_menu", None)))
    check("裸 tk_popup 只留在 _show_menu 一处",
          src.count("create_flat_menu(self, actions)") == 1,
          f"出现 {src.count('create_flat_menu(self, actions)')} 次")
    check("多处入口都收敛到 _show_menu", src.count("self._show_menu(") >= 4,
          f"出现 {src.count('self._show_menu(')} 次")

    page.select_item(data["with_sub"])
    settle(page)
    recorded: list = []
    original = page._show_menu
    page._show_menu = lambda actions: recorded.append(actions)
    try:
        entries = [
            ("⋯ 视图菜单", page._view_menu),
            ("列表右键菜单", lambda: page._list_context_menu(data["work"].id)),
            ("条目右键菜单", lambda: page._item_context_menu(db.get_item(data["with_sub"]))),
            ("日期选择菜单", page._date_menu),
            ("时间选择菜单", page._time_menu),
            ("重复规则菜单", page._repeat_menu),
            ("优先级菜单", page._priority_menu),
            ("列表归属菜单", page._list_menu),
        ]
        for name, fn in entries:
            try:
                fn()
                settle(page, 2)
                check(f"{name}可走通", True)
            except Exception:
                check(f"{name}可走通", False, traceback.format_exc(limit=2))
    finally:
        page._show_menu = original

    check("共触发 8 个菜单", len(recorded) == 8, f"n={len(recorded)}")
    check("菜单项都是非空列表（(标题, 回调) 或分隔线）",
          all(isinstance(a, list) and a for a in recorded),
          f"类型={sorted({type(a).__name__ for a in recorded})}")
    labels = [item[0] for a in recorded for item in a if isinstance(item, tuple)]
    for must in ("今天", "自定…", "清除日期", "每天", "高  !!!", "重复结束于…"):
        check(f"菜单里出现「{must}」", must in labels)


# ===========================================================================
# L. 图标资产
# ===========================================================================
def test_assets() -> None:
    section("[L] 图标资产")
    check("清单可选图标与图标库一一对应",
          set(LIST_ICONS) == set(todo_icons.TILE_GLYPHS),
          f"仅数据层有 {sorted(set(LIST_ICONS) - set(todo_icons.TILE_GLYPHS))} / "
          f"仅图标库有 {sorted(set(todo_icons.TILE_GLYPHS) - set(LIST_ICONS))}")
    check("详情/分组用到的线性图标都在图标库里",
          REQUIRED_GLYPHS <= set(todo_icons.ROW_GLYPHS),
          f"缺 {sorted(REQUIRED_GLYPHS - set(todo_icons.ROW_GLYPHS))}")
    check("智能分组的图标名都在图标库里",
          {n for n, _ in todo_page.SMART_META.values()} <= set(todo_icons.ROW_GLYPHS))

    # 图标盘按当前颜色渲染：换个颜色，同一个图标的像素必须变
    # （之前二十个图标全用灰底，肉眼分不出，等于没有图标盘）
    blue = todo_icons.tile(22, "#007AFF", "list").tobytes()
    green = todo_icons.tile(22, "#34C759", "list").tobytes()
    check("图标盘方块会跟着清单颜色变", blue != green)
    check("勾选框的勾选/未勾选是不同的图",
          todo_icons.checkbox(18, "#007AFF", False).tobytes()
          != todo_icons.checkbox(18, "#007AFF", True).tobytes())


def settle(root, n: int = 12) -> None:
    for _ in range(n):
        root.update_idletasks()
        root.update()


# ===========================================================================
def main_test() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="todo_ui_"))
    db = TodoDB(tmpdir / "ui.db")
    data = build_data(db)

    root = tk.Tk()
    root.title("待办模块 UI 回归")
    root.geometry("1280x780+40+40")
    THEME.apply_main_ttk_theme(root, ttk.Style(root), MAIN_PALETTE)
    container = ttk.Frame(root)
    container.pack(fill="both", expand=True)
    page = TodoPage(container, db)
    page.pack(fill="both", expand=True)
    settle(root)

    try:
        test_skeleton(page)
        test_sidebar(page, db)
        test_list(page, db)
        test_detail(page, db, data)
        test_search(page, db)
        test_new_list_dialog(page, root)
        test_calendar_dialog(page, root, data)
        test_holiday_dialog(page, root, db)
        test_due_write(page, db, data)
        test_quick_add(page, db)
        test_toggle(page, db, data)
        test_scope_switch(page, db, data)
        test_menus(page, db, data)
        test_assets()
    finally:
        try:
            page._flush_editor()
        except Exception:
            pass
        db.close()
        root.destroy()
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 78)
    print("待办模块 UI 回归测试：真实窗口 + 逐项断言")
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
