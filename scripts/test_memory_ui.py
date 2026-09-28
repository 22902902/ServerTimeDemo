# -*- coding: utf-8 -*-
"""记忆宫殿 UI 回归测试：真实窗口 + 逐项断言。

为什么单独成篇（必须真开窗口，只能用系统 Python312 跑）
------------------------------------------------------------------------------
数据层测「算得对」，这里测「画出来了没有」。本模块实测踩到/堵住过的坑：

* **走一遍的顺序不可颠倒**：先出「第 N 站 + 桩名 + 桩的提示」，
  按「显示答案」才给出记忆项内容。答案没展开之前自评按钮必须**禁用**。
  这一条一旦写反，界面上照样能用 —— 只是训练变成了「照着抄」。
* **同一站只写一次**：双击 / 空格 / 点按钮三条路径都能触发自评，
  没有 ``graded`` 守卫就会一站写两行流水，正确率曲线直接失真。
* **六视图是建一次、``pack_forget`` 切换的**，不是每次重建。切错帧的表现是
  「点了一下什么都没发生」，不看控件树看不出来。
* **``<<TreeviewSelect>>`` 是延迟投递的**（下一轮事件循环才到）。左栏重建会
  清掉选中、重设选中又无条件投递事件 → 自激成死循环（实测卡死过）。
  所以每次切视图后都要**多跑一轮事件循环**再断言，否则这类 bug 测不出来。
* **首帧不许排宽度相关版式**：未映射控件一律报 1x1。
* **不真弹模态窗**（simpledialog / messagebox）：本机没有真实桌面时会把主循环
  挂住。涉及弹窗的功能只验入口存在、回调可调用（把弹窗函数临时替换掉）。

本文件固化的口径
------------------------------------------------------------------------------
* 窗口必须真实可见：主窗口一旦 ``withdraw()``，连 pack 好的控件也全部变成
  「未映射」，断言会集体假红。所以这里不 withdraw。
* 「已映射」要同时满足 ``winfo_ismapped()`` **且** 宽高 > 1。
* **本文件不碰开发库**：页面与数据层都接在临时库上，跑完即删 ——
  UI 套件的夹具就是开发库那套约定在这里不适用（那是给 test_shell_ui 的）。
* 期望值从数据层现算，不写死数字。

覆盖：
A. 骨架        左右两栏 / 工具栏按钮 / 状态栏
B. 左栏导航    6 个视图 + 宫殿节点带条目数 / 点一下切视图
C. 视图切换    六视图逐一切换不炸、帧真的换了、标题与 meta 跟着变
D. 走一遍      顺序 = walk_order / 先提示后答案 / 自评只写一次 / 结算
E. WalkSession 用假记录器单测四条不变量（不碰库）
F. 今日训练    队列来源 = due_items / 队列为空时只提示不弹窗
G. 待办联动    没注入时只提示 / 注入后点一下才调一次
H. 关键纪律    状态栏在底部 / 左栏不被右侧 expand 区饿死

用法::

    python scripts/test_memory_ui.py
"""

import shutil
import sys
import tempfile
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from tkinter import messagebox  # noqa: E402

import markdown_view  # noqa: E402
import training_core as tc  # noqa: E402
from memory_db import MemoryPalaceDB  # noqa: E402
from memory_page import (  # noqa: E402
    TREE_PALACE,
    TREE_VIEW,
    VIEW_CHOICES,
    VIEW_LIBRARY,
    VIEW_STATS,
    VIEW_TODAY,
    MemoryPalacePage,
    WalkSession,
)

PASSED = 0
FAILED = 0
_TMP: list[Path] = []


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


def count_buttons(widget) -> int:
    total = 0
    for child in widget.winfo_children():
        if child.winfo_class() in ("Button", "TButton"):
            total += 1
        total += count_buttons(child)
    return total


def find_status_bar(page, var):
    """状态栏那一行的容器 —— 用 textvariable 认人。

    别用「找一个没有子控件的 Frame」来猜：``create_status_bar`` 返回的
    Frame 里还装着一个 ``ttk.Label``，那个条件永远为假。
    """
    todo = list(page.winfo_children())
    while todo:
        widget = todo.pop(0)
        try:
            todo.extend(widget.winfo_children())
        except tk.TclError:
            continue
        if widget.winfo_class() not in ("Label", "TLabel"):
            continue
        try:
            if str(widget.cget("textvariable")) == str(var):
                return widget.master
        except tk.TclError:
            pass
    return None


class QuietModals:
    """把模态窗替换掉：既不挂主循环，又能记录「到底弹了没有」。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def __enter__(self):
        self._saved = (messagebox.showinfo, messagebox.showwarning,
                       messagebox.showerror)
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(messagebox, name, self._make(name))
        return self

    def _make(self, name):
        def fake(title=None, message=None, **kw):
            self.calls.append((name, str(title), str(message)))
            return "ok"
        return fake

    def __exit__(self, *exc):
        (messagebox.showinfo, messagebox.showwarning,
         messagebox.showerror) = self._saved
        return False

    def kinds(self) -> list:
        return [c[0] for c in self.calls]


def cluster(name: str) -> MemoryPalaceDB:
    """一个有 2 座宫殿、16 + 12 桩、36 条记忆项的临时库（不碰开发库）。"""
    d = Path(tempfile.mkdtemp(prefix="mem_ui_"))
    _TMP.append(d)
    db = MemoryPalaceDB(d / f"{name}.db")
    ids = db.import_all_templates()
    db.import_bank("BANK_36JI", ids[0])
    return db


def empty_db(name: str) -> MemoryPalaceDB:
    d = Path(tempfile.mkdtemp(prefix="mem_ui_"))
    _TMP.append(d)
    return MemoryPalaceDB(d / f"{name}.db")


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


def build_page(db, *, todo_hook=None) -> tuple:
    root = tk.Tk()
    root.geometry("1400x900+40+40")
    page = MemoryPalacePage(root, db, app_title="记忆宫殿测试",
                            on_status=lambda _t: None, todo_hook=todo_hook,
                            markdown=markdown_view)
    page.pack(fill="both", expand=True)
    settle(root, 3)
    return root, page


# ══════════════════════════════════════════════════════════════════════════
# A. 骨架
# ══════════════════════════════════════════════════════════════════════════
def test_skeleton() -> None:
    section("[A] 骨架")
    db = cluster("skeleton")
    root, page = build_page(db)
    try:
        check("窗口真的可见（不 withdraw）", mapped(root))
        check("左栏导航树已映射且有尺寸", mapped(page.nav_tree))
        check("右栏有内容区", mapped(page.views[VIEW_TODAY]))
        check("工具栏有按钮", count_buttons(page) >= 5, count_buttons(page))
        check("状态栏有文字", any("就绪" in t for t in texts_of(page)),
              [t for t in texts_of(page) if "就绪" in t])
        check("左栏宽度是定值（不被右侧 expand 区挤没）",
              int(page.nav_tree.winfo_width()) > 100,
              page.nav_tree.winfo_width())
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# B. 左栏导航
# ══════════════════════════════════════════════════════════════════════════
def test_nav() -> None:
    section("[B] 左栏导航")
    db = cluster("nav")
    root, page = build_page(db)
    try:
        settle(root)
        items = page.nav_tree.get_children()
        view_items = [i for i in items if i.startswith(f"{TREE_VIEW}:")]
        palace_items = [i for i in items if i.startswith(f"{TREE_PALACE}:")]
        check("6 个视图节点都在", len(view_items) == len(VIEW_CHOICES),
              [page.nav_tree.item(i, "text") for i in view_items])
        check("宫殿节点都在（2 座）", len(palace_items) == len(db.list_palaces()),
              [page.nav_tree.item(i, "text") for i in palace_items])
        check("宫殿节点带条目数（36 条挂在第一座）",
              any(str(page.nav_tree.item(i, "values")[0]) == "36"
                  for i in palace_items),
              [(page.nav_tree.item(i, "text"),
                page.nav_tree.item(i, "values")) for i in palace_items])

        # 点「记忆项库」应该切过去，而且**不能被延迟事件抢回来**
        page.nav_tree.selection_set(f"{TREE_VIEW}:{VIEW_LIBRARY}")
        settle(root, 3)
        check("点导航切到对应视图", page.view_key == VIEW_LIBRARY, page.view_key)
        check("切完一轮事件循环后视图没被抢回去",
              page.view_key == VIEW_LIBRARY, page.view_key)
        check("标题跟着变", page.title_var.get() == dict(VIEW_CHOICES)[VIEW_LIBRARY],
              page.title_var.get())
        check("只有当前视图的帧在映射",
              mapped(page.views[VIEW_LIBRARY])
              and not mapped(page.views[VIEW_TODAY]))
        check("宫殿节点也可以选中",
              (page.nav_tree.selection_set(f"{TREE_PALACE}:"
                                           f"{db.list_palaces()[0]['id']}"),
               settle(root, 3),
               int(page.current_palace_id) == int(db.list_palaces()[0]["id"]))[-1])
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# C. 视图切换
# ══════════════════════════════════════════════════════════════════════════
def test_views() -> None:
    section("[C] 视图切换")
    db = cluster("views")
    root, page = build_page(db)
    try:
        ok, bad = True, []
        for key, label in VIEW_CHOICES:
            try:
                page.show_view(key)
                settle(root, 2)
                if not mapped(page.views[key]) or page.view_key != key:
                    bad.append((key, page.view_key, mapped(page.views[key])))
            except Exception as exc:                  # noqa: BLE001
                ok = False
                bad.append((key, f"{type(exc).__name__}: {exc}"))
        check("六个视图逐一切换都不炸且真的换帧", ok and not bad, bad)
        check("切一圈回到今日训练仍然正常",
              (page.show_view(VIEW_TODAY), settle(root, 2),
               page.view_key == VIEW_TODAY)[-1])
        page.refresh()
        settle(root, 2)
        check("meta 反映库里的规模",
              f"{len(db.list_palaces())} 座宫殿" in page.meta_var.get()
              and f"{db.count_items()} 条记忆项" in page.meta_var.get(),
              page.meta_var.get())
        check("换视图不会丢「当前宫殿」",
              (page.nav_tree.selection_set(f"{TREE_PALACE}:"
                                           f"{db.list_palaces()[0]['id']}"),
               settle(root, 2),
               page.show_view(VIEW_STATS), settle(root, 2),
               page.current_palace_id is not None)[-1])
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# D. 走一遍
# ══════════════════════════════════════════════════════════════════════════
def test_walk() -> None:
    section("[D] 走一遍（先提示、后答案）")
    db = cluster("walk")
    root, page = build_page(db)
    try:
        palace = [p for p in db.list_palaces() if db.count_items(palace_id=p["id"])]
        pid = int(palace[0]["id"])
        page.current_palace_id = pid
        order = db.walk_order(pid)
        check("这座宫殿确实有记忆项", len(order) >= 16, len(order))
        check("顺序 = 地点桩 seq（station 单调不减）",
              [int(r["station"]) for r in order]
              == sorted(int(r["station"]) for r in order),
              [int(r["station"]) for r in order][:12])

        page.walk_current_palace()
        settle(root, 3)
        session = page.walk_window
        check("走一遍窗口真的开起来了",
              session is not None and session.winfo_exists()
              and mapped(session), bool(session))
        check("站数与 walk_order 一致",
              len(session.items) == len(order), (len(session.items), len(order)))
        check("站序与 walk_order 的 id 序列一致",
              [it["id"] for it in session.items] == [r["id"] for r in order],
              [it["id"] for it in session.items][:6])

        check("**不变量A：先提示后答案**（答案区未映射）",
              session.revealed is False and not mapped(session.answer_frame),
              (session.revealed, mapped(session.answer_frame)))
        check("**不变量B：未展开时自评被吞掉**",
              all(str(b.cget("state")) == "disabled"
                  for b in session.grade_buttons.values())
              and (session.grade(tc.FEEDBACK_KNOWN) or True)
              and session.results == [],
              [(k, str(b.cget("state")))
               for k, b in session.grade_buttons.items()])
        check("提示里带桩名与第几站",
              "第 1" in session.station_var.get(), session.station_var.get())
        first = session.items[0]
        # 桩名与「第几站」一起放在大标题（station_var）里；
        # hint_var 放的是这条桩自己的提示语。原先读错了变量。
        check("大标题里出现桩名",
              str(first["locus_name"]) in session.station_var.get(),
              (first["locus_name"], session.station_var.get()))
        check("hint_var 就是这条桩的提示语",
              session.hint_var.get() == str(first.get("locus_hint") or ""),
              (first.get("locus_hint"), session.hint_var.get()))

        session.show_answer()
        settle(root, 2)
        check("展开后答案区真的映射出来",
              session.revealed is True and mapped(session.answer_frame),
              (session.revealed, mapped(session.answer_frame)))
        check("展开后自评按钮解禁",
              all(str(b.cget("state")) == "normal"
                  for b in session.grade_buttons.values()))
        check("答案区显示的是这一条的正面",
              str(first["front"]) in session.front_var.get(),
              (first["front"], session.front_var.get()))

        session.grade(tc.FEEDBACK_KNOWN)
        settle(root, 2)
        check("**不变量C：同一站只写一次**（第二击被吞）",
              len(db.list_reviews(item_id=first["id"])) == 1
              and (session.grade(tc.FEEDBACK_KNOWN) or True)
              and len(db.list_reviews(item_id=first["id"])) == 1,
              len(db.list_reviews(item_id=first["id"])))
        check("自评后跳到下一站且自评重新锁上",
              session.index == 1 and session.graded is False
              and session.revealed is False,
              (session.index, session.graded, session.revealed))
        progress = db.get_progress(first["id"])
        check("进度真的写回了 SRS",
              int(progress["mastery"]) == tc.MASTERY_WEAK
              and int(progress["correct_streak"]) == 1,
              progress)

        # 全部走完 → 结算
        for _ in range(len(order)):
            session.show_answer()
            session.grade(tc.FEEDBACK_KNOWN)
        settle(root, 2)
        check("走完进入结算",
              session.finished is True and int(session.summary()["reviewed"])
              == len(order), session.summary())
        check("结算后每一站恰好一行流水",
              len(db.list_reviews()) == len(order), len(db.list_reviews()))
        check("结算后收起了结构区", not mapped(session.answer_frame))

        session.close()
        settle(root, 3)
        check("关掉后页面把 walk_window 置空",
              page.walk_window is None, page.walk_window)
        check("关掉后按流水补了打卡",
              len(db.list_checkins()) == 1, db.list_checkins())
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# E. WalkSession 单测（假记录器，不碰库）
# ══════════════════════════════════════════════════════════════════════════
def test_walk_session_unit() -> None:
    section("[E] WalkSession 四条不变量（假记录器）")
    root = tk.Tk()
    root.geometry("900x700+40+40")
    try:
        written: list = []

        class Recorder:
            def __call__(self, item, feedback):
                written.append((item["id"], feedback))

        items = [{"id": 11, "front": "甲", "back": "A", "locus_name": "玄关",
                  "locus_hint": "进门左手", "station": 1},
                 {"id": 12, "front": "乙", "back": "B", "locus_name": "客厅",
                  "locus_hint": "沙发后", "station": 2},
                 {"id": 13, "front": "丙", "back": "C", "locus_name": "厨房",
                  "locus_hint": "冰箱顶", "station": 3}]
        session = WalkSession(root, items, on_grade=Recorder())
        settle(root, 3)

        check("初始：第 1 站、未展开、答案区未映射",
              session.index == 0 and session.revealed is False
              and not mapped(session.answer_frame))
        check("空格键在未展开时 = 显示答案",
              (session._on_space() or True) and session.revealed is True)
        check("展开后再按空格 = 自评「记得」",
              (session._on_space() or True)
              and written == [(11, tc.FEEDBACK_KNOWN)], written)
        # 第二击落到的**已经不是同一站**了：第一击写完就把 index 推到 1、
        # 并把答案重新收起。所以这一击的语义回到「显示答案」—— 不该再多出
        # 一行流水。原断言以为第二击会再写一条，是把它当成了同一站。
        check("重复按空格不会重复写（第二击变成「显示答案」）",
              (session._on_space() or True) and len(written) == 1
              and session.index == 1 and session.revealed is True, written)
        check("数字键 1/2/3 = 忘了/模糊/记得（此刻答案已展开）",
              (session.grade(tc.FEEDBACK_FORGOT) or True)
              and written[-1] == (12, tc.FEEDBACK_FORGOT), written)
        # 「同一站只写一次」的正面证据：展开后连按两次同一个自评键，只写一行。
        session.show_answer()
        session.grade(tc.FEEDBACK_VAGUE)
        session.grade(tc.FEEDBACK_VAGUE)
        check("同一站连按两次自评只写一行（守卫真的生效）",
              [w[0] for w in written] == [11, 12, 13], written)
        settle(root, 2)
        check("走完三站后进入结算",
              session.finished is True
              and int(session.summary()["reviewed"]) == 3
              and int(session.summary()["correct"]) == 1, session.summary())
        check("结算后三条自评按钮全部禁用",
              all(str(b.cget("state")) == "disabled"
                  for b in session.grade_buttons.values()))
        check("结算后再评也不会写",
              (session.grade(tc.FEEDBACK_KNOWN) or True) and len(written) == 3,
              written)
        check("结算文案给出正确率",
              "正确率" in session.hint_var.get(), session.hint_var.get())
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# F. 今日训练
# ══════════════════════════════════════════════════════════════════════════
def test_today_training() -> None:
    section("[F] 今日训练")
    db = cluster("today")
    root, page = build_page(db)
    try:
        due = db.due_items(limit=None)
        check("空库里也有可练的（内置题库导进来的都算待学）",
              len(due) >= 16, len(due))
        page.start_today_training()
        settle(root, 3)
        session = page.walk_window
        check("今日训练的队列 = due_items", session is not None
              and len(session.items) == len(due),
              (len(session.items) if session else None, len(due)))
        check("今日训练的队列不带 station 也照样能走",
              session is not None
              and (session.show_answer() or True)
              and session.revealed is True)
        session.close()
        settle(root, 2)
    finally:
        root.destroy()

    # 空库：只提示，不弹模态（这里允许弹，但必须把窗口挂住的风险挡掉）
    db2 = empty_db("today_empty")
    root2, page2 = build_page(db2)
    try:
        with QuietModals() as modals:
            page2.start_today_training()
            settle(root2, 2)
        check("空库点「开始今日训练」只提示、不开走一遍窗",
              page2.walk_window is None and "showinfo" in modals.kinds(),
              (page2.walk_window, modals.kinds()))
        check("状态栏说清楚了去哪找内容",
              "题库" in page2.status_var.get(), page2.status_var.get())
    finally:
        root2.destroy()


# ══════════════════════════════════════════════════════════════════════════
# G. 待办联动
# ══════════════════════════════════════════════════════════════════════════
def test_todo_hook() -> None:
    section("[G] 生成今日训练待办")
    calls: list = []

    def hook(*, due, suggested=0):
        calls.append((int(due), int(suggested)))
        return "复习记忆宫殿 N 条", "已生成今日训练待办"

    db = cluster("todo")
    root, page = build_page(db, todo_hook=hook)
    try:
        check("**打开页面不会自动建待办**", calls == [], calls)
        page.make_today_todo()
        settle(root, 2)
        check("点一下才调一次桥", len(calls) == 1, calls)
        check("due 与库里的 due_count 一致",
              calls[0][0] == db.due_count(), (calls, db.due_count()))
        check("suggested 由桥自己算（> 0）", calls[0][1] > 0, calls[0])
        check("状态栏回显了桥给的话",
              "已生成" in page.status_var.get(), page.status_var.get())
    finally:
        root.destroy()

    # 没注入桥：只提示
    db2 = cluster("todo_none")
    root2, page2 = build_page(db2, todo_hook=None)
    try:
        with QuietModals() as modals:
            page2.make_today_todo()
            settle(root2, 2)
        check("没注入桥时只提示、不报错",
              "showinfo" in modals.kinds(), modals.kinds())
    finally:
        root2.destroy()


# ══════════════════════════════════════════════════════════════════════════
# H. 关键纪律
# ══════════════════════════════════════════════════════════════════════════
def test_discipline() -> None:
    section("[H] 关键纪律")
    db = cluster("discipline")
    root, page = build_page(db)
    try:
        settle(root, 3)
        # 状态栏贴在底部：它的 rooty 必须比内容区大。
        # 「找一个没有子控件的 Frame」认不出状态栏（那个 Frame 里还有一个
        # 标签），所以改成用 textvariable 认人。
        status = find_status_bar(page, page.status_var)
        content = page.views[VIEW_TODAY]
        check("状态栏比内容区更靠下（side=bottom 真的生效）",
              status is not None
              and status.winfo_rooty() > content.winfo_rooty(),
              (status.winfo_rooty() if status else None,
               content.winfo_rooty()))
        check("左栏与右栏宽度都为正（没被 expand 区饿死）",
              int(page.nav_tree.winfo_width()) > 100
              and int(content.winfo_width()) > 200,
              (page.nav_tree.winfo_width(), content.winfo_width()))
        check("六个视图帧都建好了（不是懒建）",
              len(page.views) == len(VIEW_CHOICES), sorted(page.views))
    finally:
        root.destroy()


def main_test() -> None:
    test_skeleton()
    test_nav()
    test_views()
    test_walk()
    test_walk_session_unit()
    test_today_training()
    test_todo_hook()
    test_discipline()


if __name__ == "__main__":
    try:
        main_test()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILED += 1
    finally:
        cleanup()

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
