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
M. 完成态     勾上 + 标题划一道横线（含详情标题）；勾选后的回执不被重画吞掉
N. 显示已完成 开关持久化 / 已完成沉底带划线 / 点圆圈恢复 / 逾期不再标红
O. 到点提醒窗 贴屏幕右下角 / 头部不重复标题 / 「全部完成」「稍后提醒」真写库
P. 主程序接线 到点弹窗 vs 早已过点只走托盘 / 30 秒巡检自续期 / 出错不断循环

用法：
    python scripts/test_todo_ui.py
"""

import sys
import tempfile
import traceback
import types
from datetime import date, datetime, timedelta
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
    ALERT_MARGIN,
    ALERT_WIDTH,
    MIDDLE_WIDTH,
    SIDEBAR_WIDTH,
    ScrollArea,
    TodoAlertDialog,
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


def find_label(widget, text: str):
    """在控件树里找 text 等于给定值的 tk.Label（递归）。找不到回 None。"""
    if widget is None:
        return None
    try:
        if isinstance(widget, tk.Label) and widget.cget("text") == text:
            return widget
    except tk.TclError:                 # 控件已被 destroy（切视图会重建整列行）
        return None
    for child in widget.winfo_children():
        got = find_label(child, text)
        if got is not None:
            return got
    return None


def font_attr(widget, option: str) -> int:
    """读控件**实际生效**的字体属性。

    Tk 里删除线只有 ``font.Font`` 对象带得动，元组字体带不动 —— 所以必须问
    真正生效的那一层：``font actual <spec> -overstrike``（字体名与描述串都吃）。
    """
    return int(widget.tk.call("font", "actual", widget.cget("font"), f"-{option}"))


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
# M. 完成态
# ===========================================================================
def test_completed_style(page: TodoPage, db: TodoDB, data: dict) -> None:
    section("[M] 完成态：勾上 + 标题划一道横线")

    # 已完成项只出现在「已完成」视图（其余视图按苹果的路子过滤掉），
    # 所以「划了线」在「已完成」里验，「没划线」在别的视图里验。
    #
    # 注意：切视图会 _row_widgets.clear() + 重建整列行控件，旧 Label 立刻
    # destroy —— 它的 cget()/winfo_* 全部变成 "invalid command name"。
    # 所以属性一律**当场读成数值**留存，不要留着控件引用跨视图比较。
    done_items = db.fetch_items(scope="completed")
    done_item = next((i for i in done_items if i.repeat_rule == "none"), None) \
        or (done_items[0] if done_items else None)
    check("数据层里存在已完成项", done_item is not None, f"n={len(done_items)}")

    page._select_side("smart", "completed")
    settle(page)
    title_done = find_label(page._row_widgets.get(done_item.id), done_item.title)
    check("「已完成」视图里找得到该条目", title_done is not None,
          f"行={list(page._row_widgets)}")
    over_done = font_attr(title_done, "overstrike") if title_done else None
    size_done = font_attr(title_done, "size") if title_done else None
    fg_done = title_done.cget("fg") if title_done else ""
    check("已完成项标题字体带删除线（overstrike=1）", over_done == 1,
          f"overstrike={over_done}")
    check("已完成项标题是灰字", fg_done == MAIN_PALETTE.text_muted, fg_done)

    page._select_side("smart", "today")
    settle(page)
    open_items = db.fetch_items(scope="today")
    open_item = open_items[0] if open_items else None
    title_open = find_label(page._row_widgets.get(open_item.id), open_item.title) \
        if open_item is not None else None
    over_open = font_attr(title_open, "overstrike") if title_open else None
    size_open = font_attr(title_open, "size") if title_open else None
    check("今天视图里找得到未完成项", title_open is not None)
    check("未完成项标题不带删除线（overstrike=0）", over_open == 0,
          f"overstrike={over_open}")
    # 字号必须一致：完成态只该多一道线，不该变成另一种字体
    check("两个状态字号一致（只是多了道线）",
          size_done is not None and size_done == size_open,
          f"{size_done} vs {size_open}")

    # 详情面板：列表上划了、点进来又是正常字，会让人怀疑刚才勾没勾上
    page.select_item(done_item.id)
    settle(page)
    over_entry_done = font_attr(page.detail_title_entry, "overstrike")
    check("详情标题（已完成）带删除线", over_entry_done == 1,
          f"overstrike={over_entry_done}")
    if open_item is not None:
        page.select_item(open_item.id)
        settle(page)
        check("详情标题（未完成）不带删除线",
              font_attr(page.detail_title_entry, "overstrike") == 0,
              f"overstrike={font_attr(page.detail_title_entry, 'overstrike')}")

    # 勾选后的回执：提示写在 refresh_all() 之前会被重画清空 —— 等于没写
    new_id = db.add_item({"title": "回执用的一条", "list_id": data["work"].id,
                          "due_date": day_str(data["today"]), "skip_holidays": 0})
    page.refresh_all()
    settle(page)
    page.mid_helper.configure(text="")
    page.toggle_complete(new_id)
    settle(page)
    hint = page.mid_helper.cget("text")
    check("单次项勾选后给出回执", "已完成" in hint, repr(hint))
    check("回执没被重画吞掉", hint != "", repr(hint))


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


# ===========================================================================
# N. 显示已完成
# ===========================================================================
def test_show_completed(page: TodoPage, db: TodoDB, data: dict) -> None:
    section("[N] 显示已完成：开关 / 沉底 / 划掉 / 点圆圈恢复")
    check("缺省是关的", page.show_completed is False, f"实际 {page.show_completed}")

    # ⋯ 菜单里挂着这个开关，开着的时候带勾
    recorded: list = []
    original = page._show_menu
    page._show_menu = lambda actions: recorded.append(actions)
    try:
        page._view_menu()
        settle(page, 2)
        page.toggle_show_completed()
        settle(page)
        page._view_menu()
        settle(page, 2)
    finally:
        page._show_menu = original

    def done_entry(actions):
        return next((it for it in actions
                     if isinstance(it, tuple) and it[0].endswith("显示已完成")), None)

    check("⋯ 菜单里有「显示已完成」", done_entry(recorded[0]) is not None,
          f"{recorded[0]}")
    check("关着的时候不带勾", done_entry(recorded[0])[0] == "显示已完成",
          repr(done_entry(recorded[0])[0]))
    check("开着的时候带勾", done_entry(recorded[1])[0].startswith("✓"),
          repr(done_entry(recorded[1])[0]))
    check("开关的回调指向 toggle_show_completed",
          done_entry(recorded[0])[1] == page.toggle_show_completed)
    check("切换后内存状态为开", page.show_completed is True)
    check("切换后写进了 todo_state", db.get_state("show_completed") == "1",
          repr(db.get_state("show_completed")))
    check("切换后有回执（没被重画吞掉）", page.mid_helper.cget("text") != "",
          repr(page.mid_helper.cget("text")))

    # 标题旁的数字要跟左栏一致：开着开关也不该把已完成的算进「今天 4」里
    page._select_side("smart", "today")
    settle(page)
    check("标题旁的计数 = 同一分组未完成数（与左栏一致）",
          page.mid_count.cget("text") == str(len(db.fetch_items(scope="today"))),
          f"中栏 {page.mid_count.cget('text')!r} "
          f"vs 未完成 {len(db.fetch_items(scope='today'))}")
    page._select_side("smart", "completed")
    settle(page)
    check("「已完成」视图的计数数全部",
          page.mid_count.cget("text")
          == str(len(db.fetch_items(scope="completed"))),
          f"{page.mid_count.cget('text')!r}")

    # —— 中栏：已完成要出现、要沉底、要划线 ——
    page._select_side("smart", "today")
    settle(page)
    expected = [it.id for it in db.fetch_items(
        scope="today", include_completed=True)]
    ids = list(page._row_widgets)
    # 注意：智能分组视图是**按清单分组**渲染的，行顺序不等于数据层的平铺顺序，
    # 所以这里只比集合；顺序另用「已完成沉底」与「已完成段内顺序」两条来钉。
    check("中栏展示的条目与数据层一致", set(ids) == set(expected),
          f"{sorted(ids)} != {sorted(expected)}")

    done_ids = {it.id for it in db.fetch_items(scope="completed")}
    shown_done = [i for i in ids if i in done_ids]
    open_rows = [i for i in ids if i not in done_ids]
    check("「今天」里出现了已完成项", bool(shown_done), f"行={ids}")
    if shown_done and open_rows:
        check("已完成的全部排在未完成之后",
              ids.index(shown_done[0]) > ids.index(open_rows[-1]),
              f"行={ids}")
        # 已完成那一段是平铺渲染的，段内顺序应与数据层一致（也按日期升序）
        expect_done = [it.id for it in
                       db.fetch_items(scope="today", include_completed=True)
                       if it.completed]
        check("已完成段内顺序与数据层一致", shown_done == expect_done,
              f"{shown_done} != {expect_done}")

        # 「已完成」小标题要夹在两段之间
        kids = list(page.list_area.inner.winfo_children())
        row_of = {w: iid for iid, w in page._row_widgets.items()}
        head_idx = next((i for i, w in enumerate(kids)
                         if find_label(w, "已完成") is not None), None)
        open_idx = [i for i, w in enumerate(kids)
                    if w in row_of and row_of[w] in open_rows]
        done_idx = [i for i, w in enumerate(kids)
                    if w in row_of and row_of[w] in done_ids]
        check("中栏里有「已完成」小标题", head_idx is not None)
        check("小标题夹在未完成段与已完成段之间",
              head_idx is not None and open_idx and done_idx
              and max(open_idx) < head_idx < min(done_idx),
              f"标题={head_idx} 未完成={open_idx} 已完成={done_idx}")

    first_done = db.get_item(shown_done[0]) if shown_done else None
    check("取到一条已完成项用于断言样式", first_done is not None)
    if first_done is not None:
        lbl = find_label(page._row_widgets.get(first_done.id), first_done.title)
        check("已完成项标题带删除线", lbl is not None
              and font_attr(lbl, "overstrike") == 1,
              f"overstrike={font_attr(lbl, 'overstrike') if lbl else '-'}")
        check("已完成项标题是灰字", lbl is not None
              and lbl.cget("fg") == MAIN_PALETTE.text_muted,
              lbl.cget("fg") if lbl else "-")

    # —— 逾期的活做完了就不该再喊「逾期」 ——
    od = data["overdue"]
    od_row = page._row_widgets.get(od)
    check("逾期未完成项标着「逾期」",
          od_row is not None and "逾期" in text_of(od_row),
          text_of(od_row) if od_row is not None else "没找到行")
    db.set_completed(od, True)
    page.refresh_all()
    settle(page)
    od_row = page._row_widgets.get(od)
    check("做完了还在列表里（开关开着）", od_row is not None)
    if od_row is not None:
        check("做完了就不再喊「逾期」", "逾期" not in text_of(od_row),
              text_of(od_row))

    # —— 点圆圈恢复：已完成项再点一下要能撤回 ——
    check("点之前是已完成", db.get_item(first_done.id).completed == 1)
    page._on_check_click(first_done.id)
    settle(page)
    check("点圆圈后恢复成未完成", db.get_item(first_done.id).completed == 0,
          f"completed={db.get_item(first_done.id).completed}")
    check("恢复后有回执", "恢复" in page.mid_helper.cget("text"),
          repr(page.mid_helper.cget("text")))
    restored = page._row_widgets.get(first_done.id)
    check("恢复后仍留在列表里", restored is not None, f"行={list(page._row_widgets)}")
    if restored is not None:
        lbl = find_label(restored, first_done.title)
        check("恢复后标题不再带删除线", lbl is not None
              and font_attr(lbl, "overstrike") == 0,
              f"overstrike={font_attr(lbl, 'overstrike') if lbl else '-'}")

    # —— 偏好要能被下个页面读回去 ——
    other = TodoPage(page.master, db)
    settle(page)
    content = text_of(other)
    check("新开的页面读回同一个偏好（开关仍是开）", other.show_completed is True,
          f"实际 {other.show_completed}")
    check("新开的页面内容没炸", "已完成" in content)
    other.destroy()

    # —— 关掉：已完成的要从列表里消失 ——
    # done_ids 是在测试开头取的，中间「完成一条逾期项 / 恢复一条」已经改了它，
    # 这里必须重新现算 —— 用陈旧的集合去断言只会得到假红
    done_ids_now = {it.id for it in db.fetch_items(scope="completed")}
    page.toggle_show_completed()
    settle(page)
    check("关掉后开关状态为关", page.show_completed is False)
    check("关掉后写回 todo_state", db.get_state("show_completed") == "0",
          repr(db.get_state("show_completed")))
    check("关掉后有回执", "隐藏" in page.mid_helper.cget("text"),
          repr(page.mid_helper.cget("text")))
    left = list(page._row_widgets)
    check("关掉后已完成的从列表消失",
          all(i not in done_ids_now for i in left), f"行={left}")
    check("关掉后行数 = 未完成数",
          len(left) == len(db.fetch_items(scope="today")),
          f"{len(left)} vs {len(db.fetch_items(scope='today'))}")
    check("关掉后没有「已完成」小标题",
          find_label(page.list_area.inner, "已完成") is None)


def test_alert_dialog(page, db, data) -> None:
    section('[O] 到点提醒窗（贴屏幕右下角 / 文案 / 完成与稍后真写库）')
    today = data['today']
    lists = {l.name: l for l in db.fetch_lists()}

    def add(title, list_name='工作', hhmm='18:00'):
        return db.add_item({'title': title, 'list_id': lists[list_name].id,
                            'due_date': day_str(today), 'due_time': hhmm,
                            'skip_holidays': 0})

    first = add('到点提醒甲')
    second = add('到点提醒乙', '生活')
    fired: list = []

    dlg = TodoAlertDialog(page, [db.get_item(first), db.get_item(second)], db=db,
                          on_changed=lambda: fired.append(1))
    settle(page)

    check('提醒窗立起来了', dlg.winfo_exists() == 1 and dlg.winfo_ismapped() == 1)
    check(f'宽度固定 {ALERT_WIDTH}px', dlg.winfo_width() == ALERT_WIDTH,
          f'实际 {dlg.winfo_width()}')
    check('贴屏幕右边',
          dlg.winfo_x() + dlg.winfo_width() + ALERT_MARGIN == dlg.winfo_screenwidth(),
          f'x={dlg.winfo_x()} w={dlg.winfo_width()} sw={dlg.winfo_screenwidth()}')
    check('整窗落在屏幕内（不越过下边缘）',
          dlg.winfo_y() + dlg.winfo_height() <= dlg.winfo_screenheight(),
          f'y={dlg.winfo_y()} h={dlg.winfo_height()} sh={dlg.winfo_screenheight()}')
    check('浮在最上层', bool(dlg.attributes('-topmost')))
    # 提醒就该去打扰人，但**不能抢键盘焦点** —— 正在打字时被拽走最烦人
    check('不抢占 grab（非模态）', dlg.grab_current() is None)

    content = text_of(dlg)
    check('窗口标题写着「提醒事项」', dlg.title() == '提醒事项', dlg.title())
    check('内容区不再重复一遍同名大标题', content.count('提醒事项') == 1, content)
    check('头部报条数', '2 条到时间了' in content, content)
    check('两条都列出来了',
          '到点提醒甲' in content and '到点提醒乙' in content, content)
    check('带上提醒时刻', '18:00' in content, content)
    check('两条时主按钮是「全部完成」', '全部完成' in content, content)
    check('有「稍后提醒」且写明分钟数', '稍后提醒 10 分钟' in content, content)

    dlg.complete_all()
    settle(page)
    check('「全部完成」真写库（甲）', db.get_item(first).completed == 1)
    check('「全部完成」真写库（乙）', db.get_item(second).completed == 1)
    check('处理完通知外面刷新', fired == [1], f'{fired}')
    check('窗口自己关掉了', not dlg.winfo_exists())

    third = add('只有一条', '提醒事项')
    dlg2 = TodoAlertDialog(page, [db.get_item(third)], db=db)
    settle(page)
    content2 = text_of(dlg2)
    check('单条时主按钮是「完成」而非「全部完成」',
          '完成' in content2 and '全部完成' not in content2, content2)
    check('单条时头部是「到时间了」', '到时间了' in content2, content2)

    dlg2.snooze_all()
    settle(page)
    check('「稍后提醒」真写库', bool(db.get_item(third).snooze_until),
          repr(db.get_item(third).snooze_until))
    check('稍后提醒从原定时点起算（还没到点时不算当刻）',
          db.get_item(third).snooze_until == f'{day_str(today)} 18:10',
          db.get_item(third).snooze_until)
    check('窗口自己关掉了', not dlg2.winfo_exists())

    # 逾期很久才按「稍后提醒」：必须从当刻起算，否则推后 10 分钟仍在过去，
    # 下一轮巡检会判成「错过」，这条就再也弹不出来了
    overdue = add('早就过点的', hhmm='09:00')
    db.snooze(overdue, 10)
    later = db.get_item(overdue).snooze_until
    check('逾期的从当刻起算（推后时刻落在未来）',
          datetime.strptime(later, '%Y-%m-%d %H:%M') > datetime.now(), later)
    check('逾期项打盹到点还能响',
          overdue in [i.id for i in db.pending_alerts(
              datetime.strptime(later, '%Y-%m-%d %H:%M'))['due']], later)


class _FakeTray:
    '''只记账、不真弹气泡：本机没有真实桌面，pystray 的 notify 弹不出来。'''

    def __init__(self):
        self.calls: list = []

    def notify(self, title, message):
        self.calls.append((title, message))


def test_alert_wiring(page, db, data, root) -> None:
    section('[P] 主程序接线（到点弹窗 / 早已过点只走托盘 / 巡检自续期）')
    import main as app_module

    App = app_module.ExpiryManagerApp
    today = data['today']
    lists = {l.name: l for l in db.fetch_lists()}
    at = datetime.now()

    def add(title, hhmm, list_name='工作'):
        return db.add_item({'title': title, 'list_id': lists[list_name].id,
                            'due_date': day_str(today), 'due_time': hhmm,
                            'skip_holidays': 0})

    def make_fake():
        '''把待办那套方法绑到轻量对象上，绕开整棵主界面（它要登录框才起得来）。'''
        fake = types.SimpleNamespace()
        fake.todo_db = db
        fake.tray = _FakeTray()
        fake._exiting = False
        fake.logs = []
        fake.log_status = fake.logs.append
        fake.shown = []
        fake.show_todo_alert = lambda items: fake.shown.append([i.id for i in items])
        fake.run = lambda: App._run_todo_alerts(fake)
        return fake

    # —— 未来的提醒：什么都不该发生 ——
    fake = make_fake()
    future = add('明年的会', '09:00')
    db.update_item(future, {'due_date': '2027-12-31'})
    fake.run()
    check('未来的提醒不弹窗', not fake.shown)
    check('未来的提醒不发托盘', not fake.tray.calls)
    check('未来的提醒不写记账', db.get_item(future).alerted_for == '')

    # —— 到点：交给弹窗，不另外叠加托盘 ——
    due_now = add('刚过点的', at.strftime('%H:%M'))
    fake = make_fake()
    fake.run()
    check('到点的那条交给弹窗', fake.shown == [[due_now]], f'{fake.shown}')
    check('到点不再叠加托盘通知', not fake.tray.calls, f'{fake.tray.calls}')
    check('已经记账（下一轮不会重复弹）', db.get_item(due_now).alerted_for != '')
    fake.shown.clear()
    fake.run()
    check('下一轮真的不再挑出来', not fake.shown)

    # —— 早已过点：只走托盘汇总 ——
    missed = add('早上就过点了',
                 (at - timedelta(hours=3)).strftime('%H:%M'), '生活')
    fake = make_fake()
    fake.run()
    check('过点太久的不会弹窗', not fake.shown, f'{fake.shown}')
    check('改走托盘汇总（一条）', len(fake.tray.calls) == 1, f'{fake.tray.calls}')
    if fake.tray.calls:
        _title, message = fake.tray.calls[0]
        check('托盘文案带条数', '1 条' in message, message)
        check('托盘文案带标题', '早上就过点了' in message, message)
    check('过点的也记账了', db.get_item(missed).alerted_for != '')
    fake.run()
    check('过点的不每 30 秒重复报', len(fake.tray.calls) == 1, f'{fake.tray.calls}')

    # —— 混合：一边弹窗一边汇总，互不串台 ——
    db.update_item(due_now, {'due_time': at.strftime('%H:%M')})
    add('另一条过点的', (at - timedelta(hours=2)).strftime('%H:%M'), '提醒事项')
    fake = make_fake()
    fake.run()
    check('弹窗只拿到到点那条', fake.shown == [[due_now]], f'{fake.shown}')
    check('托盘只拿到过点那条', len(fake.tray.calls) == 1, f'{fake.tray.calls}')
    if fake.tray.calls:
        check('托盘里不含到点那条', '刚过点的' not in fake.tray.calls[0][1],
              fake.tray.calls[0][1])

    # —— 巡检定时器：30 秒一次，自己续期 ——
    ticks: list = []
    ticker = types.SimpleNamespace()
    ticker._exiting = False
    ticker.ran = []
    ticker._run_todo_alerts = lambda: ticker.ran.append(1)
    ticker.after = lambda ms, fn: ticks.append((ms, fn))
    ticker.todo_alert_check = App.todo_alert_check
    App.todo_alert_check(ticker)
    check('巡检真的跑了一轮', ticker.ran == [1])
    check('巡检间隔是 30 秒',
          bool(ticks) and ticks[0][0] == app_module.TODO_TICK_MS, f'{ticks[:1]}')
    check('巡检回调指向自己（自续期）',
          bool(ticks) and getattr(ticks[0][1], '__func__', ticks[0][1])
          is App.todo_alert_check, f'{ticks[:1]}')
    check('常量就是 30 秒', app_module.TODO_TICK_MS == 30 * 1000)
    check('常量是 main 模块级（打包后读得到）',
          hasattr(app_module, 'TODO_TICK_MS'))

    # —— 出错不能把循环掐断：断了就再也没有提醒了 ——
    ticks.clear()
    broken = types.SimpleNamespace()
    broken._exiting = False

    def boom():
        raise RuntimeError('模拟数据库炸了')

    broken._run_todo_alerts = boom
    broken.after = lambda ms, fn: ticks.append((ms, fn))
    broken.todo_alert_check = App.todo_alert_check
    print('        （下面那段 Traceback 是故意触发的：验证巡检出错后仍会续期）')
    App.todo_alert_check(broken)
    check('巡检出错后仍然续期', bool(ticks) and ticks[0][0] == app_module.TODO_TICK_MS,
          f'{ticks}')

    ticks.clear()
    quitting = types.SimpleNamespace()
    quitting._exiting = True
    quitting._run_todo_alerts = lambda: ticks.append('不该跑')
    quitting.after = lambda ms, fn: ticks.append(('after', ms))
    App.todo_alert_check(quitting)
    check('退出中不再巡检、也不再续期', not ticks, f'{ticks}')

    # —— 真弹窗：show_todo_alert 同时只留一个 ——
    root.todo_db = db
    root.log_status = lambda _m: None
    root._todo_alert_win = None
    # tk.Tk 重写了 __getattr__（转发给底层解释器对象），没挂在实例上的方法取不到。
    # 必须用 MethodType 绑定 —— 直接赋未绑定函数的话，实例 __dict__ 里的函数
    # **不会**被描述符协议绑定（那只对类属性生效），调用时会少掉 self
    root._close_todo_alert = types.MethodType(App._close_todo_alert, root)
    root._after_todo_alert = types.MethodType(App._after_todo_alert, root)
    root._open_todo_item = types.MethodType(App._open_todo_item, root)

    shown = add('真窗验证', at.strftime('%H:%M'), '生活')
    App.show_todo_alert(root, [db.get_item(shown)])
    settle(root)
    win = root._todo_alert_win
    check('主程序把提醒窗挂上了', isinstance(win, TodoAlertDialog), f'{type(win)}')
    check('提醒窗确实映射出来了', win is not None and win.winfo_ismapped() == 1)

    App.show_todo_alert(root, [db.get_item(due_now)])
    settle(root)
    second_win = root._todo_alert_win
    check('新一批顶掉旧的（同时只留一个）', second_win is not win)
    check('旧的那个已经销毁', not win.winfo_exists())

    App._close_todo_alert(root)
    check('_close_todo_alert 关掉了它', not second_win.winfo_exists())
    check('关掉后引用被清空', root._todo_alert_win is None)
    App._close_todo_alert(root)
    check('重复关不报错（幂等）', root._todo_alert_win is None)


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
        test_completed_style(page, db, data)
        test_scope_switch(page, db, data)
        test_menus(page, db, data)
        test_assets()
        test_show_completed(page, db, data)
        test_alert_dialog(page, db, data)
        test_alert_wiring(page, db, data, root)
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
