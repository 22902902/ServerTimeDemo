# -*- coding: utf-8 -*-
"""思维导图 UI 回归测试：真实窗口 + 逐项断言。

为什么单独成篇（必须真开窗口，只能用系统 Python312 跑）
------------------------------------------------------------------------------
数据层测「算得对」，这里测「画出来了没有」。本模块实测踩到 / 堵住过的坑：

* **首屏右栏是空的**（本套件的第一条回归锁）。``MindMapPage._build()`` 只把
  五个视图帧**建好**，真正 pack 它们的地方只有 ``show_view()`` 一处；而
  ``_reload_nav()`` 里「重设选中」带了 ``if selected is not None`` 前置条件 ——
  首屏 ``current_map_id`` 就是 ``None``，导航树里一个选中项都没有，那条延迟
  投递的 ``<<TreeviewSelect>>`` 永远不来，``show_view()`` 从头到尾没被调用过。
  表现就是：进「思维导图」右栏只有标题行，数据都读好了（``_reload_today``
  把行填进了 ``today_tree``）只是那块帧没装上 —— 界面上看就是**一片空白**。
* **盲画的顺序不可颠倒**：第一屏只报「中心主题 + 一级分支几个 / 共几个节点 /
  最深几层」，**一个分支文字都不许出现**，那要靠自己回忆出来。这一条写反了
  界面上照样能用，只是训练变成了「照着念」。
* **全部层级展开之前，自评按钮必须禁用**；自评三档**只写一次**。
* **折叠是把子树从排布里摘出去，不是删节点** —— 库里一个节点都不能少。
  写成「删子树」的版本，界面上看着一模一样。
* **``Text`` 的 ``<<Modified>>`` 是延迟投递的**，且程序性改写（``_set_outline_text``）
  必须置 ``_applying`` 才能不触发「自动落库 -> 回写 -> 再触发」的循环。
* **不真弹模态窗**（``simpledialog`` / ``messagebox`` / ``filedialog``）：
  本机没有真实桌面时会把主循环挂住。本文件把三者的入口全部换掉。

本文件固化的口径
------------------------------------------------------------------------------
* 窗口必须真实可见：主窗口一旦 ``withdraw()``，连 pack 好的控件也全部变成
  「未映射」，断言会集体假红。所以这里不 withdraw。
* 「已映射」要同时满足 ``winfo_ismapped()`` **且** 宽高 > 1。
* **本文件不碰开发库**：页面与数据层都接在临时库上，跑完即删。
* 期望值从数据层现算，不写死数字。

覆盖：
A. 骨架        左右两栏 / 工具栏按钮 / 状态栏 / **首屏右栏不是空的**
B. 左栏导航    5 个视图 + 两个分组 + 导图节点 / 点一下切视图 / 分组标题不改视图
C. 视图切换    五视图逐一切换不炸、帧真的换了、标题与 meta 跟着变
D. 编辑工作台  大纲 == 树 / 缩进 / 加同级 / 加子节点 / 删行 / 打字自动落库
E. 画布        折叠不丢节点 / 缩放到极值不炸 / 重排节点数不变
F. BlindSession 用假记录器单测三条不变量（不碰库）
G. 盲画        真库走一遍：写回 SRS 一行流水 / 关掉补打卡
H. 待办联动    没注入时只提示 / 注入后点一下才调一次
I. 关键纪律    状态栏在底部 / 左栏不被右侧 expand 区饿死

用法::

    python scripts/test_mindmap_ui.py
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

from tkinter import filedialog, messagebox, simpledialog  # noqa: E402

import markdown_view  # noqa: E402
import mindmap_layout as ml  # noqa: E402
import training_core as tc  # noqa: E402
from mindmap_db import MindmapDB  # noqa: E402
from mindmap_page import (  # noqa: E402
    GROUP_MINE,
    GROUP_TPL,
    NEW_NODE_TEXT,
    NODE_TAG,
    TREE_GROUP,
    TREE_MAP,
    TREE_TPL_MAP,
    TREE_VIEW,
    VIEW_CHOICES,
    VIEW_EDITOR,
    VIEW_STATS,
    VIEW_TODAY,
    VIEW_WALL,
    BlindSession,
    MindMapPage,
)

PASSED = 0
FAILED = 0
_TMP: list[Path] = []

#: 一棵结构足够深、又不会太啰嗦的样图（9 个节点 / 最深 3 层 / 3 个一级分支）
SAMPLE_OUTLINE = "\n".join([
    "周末计划",
    "  采购",
    "    超市",
    "    菜市场",
    "  运动",
    "    跑步",
    "      公园",
    "    游泳",
    "  阅读",
])


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
    """让 Tk 把挂起的几何结算与延迟事件跑完。

    ``rounds`` 默认 2 而不是 1 是有原因的：``<<TreeviewSelect>>`` 与
    ``Text`` 的 ``<<Modified>>`` 都是**下一轮**事件循环才投递，只跑一轮会漏掉
    「视图被抢回去」「打字没落库」这类 bug。
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

    别用「找一个没有子控件的 Frame」来猜：``create_status_bar`` 返回的 Frame
    里还装着一个 ``ttk.Label``，那个条件永远为假。
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


def drawn_nodes(page) -> set:
    """画布上**真的画出来了**的节点（按 ``node-<id>`` 标签去重）。

    一个节点会 create 出矩形 + 文字（折叠时还有「+n」），都挂同一个 tag，
    所以必须按 tag 去重，不能数 canvas item。
    """
    tags = set()
    for item in page.canvas.find_all():
        for tag in page.canvas.gettags(item):
            if tag.startswith(NODE_TAG):
                tags.add(tag)
    return tags


def outline_of(page) -> str:
    return page.outline.get("1.0", "end").rstrip("\n")


class QuietDialogs:
    """把模态窗全部替换掉：既不挂主循环，又能记录「到底弹了没有」。"""

    def __init__(self, *, yes: bool = True, answer=None, path: str = ""):
        self.calls: list[str] = []
        self.texts: list[str] = []
        self._fields = [(messagebox, "showinfo", None),
                        (messagebox, "showwarning", None),
                        (messagebox, "showerror", None),
                        (messagebox, "askyesno", yes),
                        (simpledialog, "askstring", answer),
                        (simpledialog, "askinteger", answer),
                        (filedialog, "asksaveasfilename", path)]

    def __enter__(self):
        self._saved = [(module, name, getattr(module, name))
                       for module, name, _reply in self._fields]
        for module, name, reply in self._fields:
            setattr(module, name, self._make(name, reply))
        return self

    def _make(self, name, reply):
        def fake(*args, **kwargs):
            self.calls.append(name)
            self.texts.extend(str(a) for a in args)
            self.texts.extend(f"{k}={v}" for k, v in kwargs.items())
            return reply
        return fake

    def __exit__(self, *exc):
        for module, name, original in self._saved:
            setattr(module, name, original)
        return False

    def kinds(self) -> list:
        return list(self.calls)


# ══════════════════════════════════════════════════════════════════════════
# 夹具（临时库，跑完即删）
# ══════════════════════════════════════════════════════════════════════════
def cluster(name: str) -> tuple:
    """一个带 10 张模板导图 + 1 张自建样图的临时库。返回 ``(db, map_id)``。"""
    d = Path(tempfile.mkdtemp(prefix="mm_ui_"))
    _TMP.append(d)
    db = MindmapDB(d / f"{name}.db")          # 构造即灌 10 张模板导图
    return db, sample_map(db, "我的导图")


def sample_map(db, title: str = "样图") -> int:
    """在库里新建一张结构固定的自建导图（不是模板来源）。"""
    map_id = db.add_map(title)
    db.save_outline(map_id, ml.parse_outline(SAMPLE_OUTLINE))
    return map_id


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


def build_page(db, *, todo_hook=None) -> tuple:
    root = tk.Tk()
    root.geometry("1400x900+40+40")
    page = MindMapPage(root, db, app_title="思维导图测试",
                       on_status=lambda _t: None, todo_hook=todo_hook,
                       markdown=markdown_view)
    page.pack(fill="both", expand=True)
    settle(root, 3)
    return root, page


def node_row(db, map_id, text):
    for row in db.list_nodes(map_id):
        if str(row["text"]) == str(text):
            return row
    return None


# ══════════════════════════════════════════════════════════════════════════
# A. 骨架
# ══════════════════════════════════════════════════════════════════════════
def test_skeleton() -> None:
    section("[A] 骨架")
    db, _map_id = cluster("skeleton")
    root, page = build_page(db)
    try:
        check("窗口真的可见（不 withdraw）", mapped(root))
        check("左栏导航树已映射且有尺寸", mapped(page.nav_tree))
        today = page.views[VIEW_TODAY]
        check("**首屏右栏不是空的**（视图帧真的 pack 上了）",
              mapped(today),
              (today.winfo_ismapped(), today.winfo_width(), today.winfo_height()))
        check("首屏左栏选中项 == 当前视图（就是它把视图 pack 出来的）",
              tuple(page.nav_tree.selection()) == (f"{TREE_VIEW}:{VIEW_TODAY}",),
              page.nav_tree.selection())
        check("今日训练表格里真的有行（数据画进了**可见**的帧）",
              len(page.today_tree.get_children()) > 0,
              len(page.today_tree.get_children()))
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
    db, map_id = cluster("nav")
    root, page = build_page(db)
    try:
        settle(root)
        items = page.nav_tree.get_children()
        view_items = [i for i in items if i.startswith(f"{TREE_VIEW}:")]
        group_items = [i for i in items if i.startswith(f"{TREE_GROUP}:")]
        check("5 个视图节点都在", len(view_items) == len(VIEW_CHOICES),
              [page.nav_tree.item(i, "text") for i in view_items])
        check("两个分组节点在（我的导图 / 从模板创建）", len(group_items) == 2,
              [page.nav_tree.item(i, "text") for i in group_items])
        mine = page.nav_tree.get_children(f"{TREE_GROUP}:{GROUP_MINE}")
        tpl = page.nav_tree.get_children(f"{TREE_GROUP}:{GROUP_TPL}")
        check("自建的图落在「我的导图」组里",
              f"{TREE_MAP}:{map_id}" in mine,
              (mine, map_id))
        check("模板灌出来的图落在「从模板创建」组里",
              len(tpl) == len(db.list_maps()) - len(mine), (len(tpl), len(mine)))
        check("模板来源的图用 tplmap: 前缀（自建的是 map:）",
              bool(tpl) and all(i.startswith(f"{TREE_TPL_MAP}:") for i in tpl),
              tpl[:3])

        # 点「缩略图墙」应该切过去，而且**不能被延迟事件抢回来**
        page.nav_tree.selection_set(f"{TREE_VIEW}:{VIEW_WALL}")
        settle(root, 3)
        check("点导航切到对应视图", page.view_key == VIEW_WALL, page.view_key)
        check("切完一轮事件循环后视图没被抢回去",
              page.view_key == VIEW_WALL, page.view_key)
        check("标题跟着变", page.title_var.get() == dict(VIEW_CHOICES)[VIEW_WALL],
              page.title_var.get())
        check("只有当前视图的帧在映射",
              mapped(page.views[VIEW_WALL])
              and not mapped(page.views[VIEW_TODAY]))

        # 分组标题只是标尺，点了不改视图
        page.nav_tree.selection_set(f"{TREE_GROUP}:{GROUP_MINE}")
        settle(root, 3)
        check("点分组标题不改视图", page.view_key == VIEW_WALL, page.view_key)

        # 点导图节点 -> 进编辑工作台
        page.nav_tree.selection_set(f"{TREE_MAP}:{map_id}")
        settle(root, 3)
        check("点导图节点进编辑工作台",
              page.view_key == VIEW_EDITOR
              and int(page.current_map_id or 0) == map_id,
              (page.view_key, page.current_map_id))
        check("进去后大纲就是这张图的文本",
              outline_of(page) == ml.outline_text(db.load_tree(map_id)),
              outline_of(page)[:40])
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# C. 视图切换
# ══════════════════════════════════════════════════════════════════════════
def test_views() -> None:
    section("[C] 视图切换")
    db, _map_id = cluster("views")
    root, page = build_page(db)
    try:
        ok, bad = True, []
        for key, _label in VIEW_CHOICES:
            try:
                page.show_view(key)
                settle(root, 2)
                if not mapped(page.views[key]) or page.view_key != key:
                    bad.append((key, page.view_key, mapped(page.views[key])))
            except Exception as exc:                  # noqa: BLE001
                ok = False
                bad.append((key, f"{type(exc).__name__}: {exc}"))
        check("五个视图逐一切换都不炸且真的换帧", ok and not bad, bad)
        check("切一圈回到今日训练仍然正常",
              (page.show_view(VIEW_TODAY), settle(root, 2),
               page.view_key == VIEW_TODAY)[-1])
        check("切到打卡统计后 meta 描述了导图总量",
              (page.show_view(VIEW_STATS), settle(root, 2),
               "张导图" in page.meta_var.get())[-1], page.meta_var.get())

        # **不变量**：左栏高亮恒等于当前视图。这条锁住的正是「延迟投递的
        # <<TreeviewSelect>> 把视图抢回去」—— 实测切到缩略图墙，一帧之后
        # view_key 变回 editor。只要「选中项」和「当前视图」不是一回事，
        # 它就会发生。
        bad = []
        for key, _label in VIEW_CHOICES:
            page.show_view(key)
            settle(root, 3)
            if tuple(page.nav_tree.selection()) != (f"{TREE_VIEW}:{key}",):
                bad.append((key, page.nav_tree.selection(), page.view_key))
        check("**不变量**：切完视图左栏高亮恒等于当前视图", not bad, bad)

        # 工作台是唯一的例外：那里「当前那件事」是某一张导图，就选中那张
        mid = sample_map(db, "高亮用例")
        page._open_map(mid)
        settle(root, 3)
        check("进工作台后左栏高亮的是当前那张导图",
              tuple(page.nav_tree.selection()) == (f"{TREE_MAP}:{mid}",),
              page.nav_tree.selection())
        page.show_view(VIEW_STATS)
        settle(root, 3)
        check("从工作台切走：高亮回到视图节点，且视图不被抢回来",
              tuple(page.nav_tree.selection()) == (f"{TREE_VIEW}:{VIEW_STATS}",)
              and page.view_key == VIEW_STATS,
              (page.nav_tree.selection(), page.view_key))
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# D. 编辑工作台（大纲 <-> 画布）
# ══════════════════════════════════════════════════════════════════════════
def test_editor() -> None:
    section("[D] 编辑工作台（大纲 <-> 画布）")
    db, _seed_id = cluster("editor")
    root, page = build_page(db)
    try:
        # ---- 进入工作台：文本与树一致 ---------------------------------
        mid = sample_map(db, "进台用例")
        page._open_map(mid)
        settle(root, 4)
        check("大纲文本 == 树的文本（互为逆运算）",
              outline_of(page) == ml.outline_text(db.load_tree(mid)),
              outline_of(page)[:60])
        check("大纲第一行就是中心主题（DFS 序）",
              page.outline.get("1.0", "1.end") == "周末计划",
              page.outline.get("1.0", "1.end"))
        check("进去就是「已同步」", page.sync_var.get() == "已同步", page.sync_var.get())
        check("画布把库里每个节点都画上了",
              len(drawn_nodes(page)) == db.node_count(mid),
              (len(drawn_nodes(page)), db.node_count(mid)))

        # ---- 缩进：成为上一个兄弟的孩子 -------------------------------
        mid = sample_map(db, "缩进用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        # 大纲是 **DFS 序**：1 周末计划 / 2 采购 / 3 超市 / 4 菜市场 / 5 运动 /
        # 6 跑步 / 7 公园 / 8 游泳 / 9 阅读。要缩进的节点必须是「不是第一个」
        # 的兄弟，否则会被数据层正当拦下。
        page._focus_row(5)                     # 第 5 行 = 第二个一级分支「运动」
        page.outline_indent_in()
        settle(root, 3)
        moved = node_row(db, mid, "运动")
        parent = node_row(db, mid, "采购")
        check("缩进：节点真的降了一层（挂到上一个兄弟下）",
              int(moved["depth"]) == 2
              and int(moved["parent_id"]) == int(parent["id"]),
              (moved["depth"], moved["parent_id"], parent["id"]))
        check("缩进不增不减节点", db.node_count(mid) == count,
              (db.node_count(mid), count))
        check("子树跟着一起下移（跑步第 3 层、公园第 4 层）",
              int(node_row(db, mid, "跑步")["depth"]) == 3
              and int(node_row(db, mid, "公园")["depth"]) == 4,
              [(r["text"], r["depth"]) for r in db.list_nodes(mid)
               if r["text"] in ("跑步", "公园")])
        check("结构变了之后大纲被规范化重写（缩进仍是 2 空格递增）",
              outline_of(page) == ml.outline_text(db.load_tree(mid))
              and "\t" not in outline_of(page),
              outline_of(page)[:80])
        check("状态栏说的是「已缩进一层」（精确匹配，不能用子串）",
              page.status_var.get() == "已缩进一层。", page.status_var.get())

        # ---- 同级的第一个孩子没法再缩进（数据层的正当口径）-------------
        mid = sample_map(db, "首子缩进用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        page._focus_row(3)                     # 「超市」= 采购的第一个孩子
        page.outline_indent_in()
        settle(root, 2)
        check("上一级的第一个孩子没法缩进（有明确提示）",
              "第一个孩子" in page.status_var.get(), page.status_var.get())
        check("被拦下时不动数据", db.node_count(mid) == count)
        check("被拦下时大纲也不改写",
              outline_of(page) == ml.outline_text(db.load_tree(mid)))

        # ---- 第一层反缩进必须被拦下 -----------------------------------
        mid = sample_map(db, "反缩进用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        page._focus_row(2)                     # 第 2 行 = 第一个一级分支
        page.outline_indent_out()
        settle(root, 2)
        check("第一层反缩进被拦下（提示而非静默失败）",
              "第一层" in page.status_var.get(), page.status_var.get())
        check("被拦下时库里一个节点都没动", db.node_count(mid) == count)
        check("被拦下时大纲也没被改写",
              outline_of(page) == ml.outline_text(db.load_tree(mid)))

        # ---- 加同级 / 加子节点 ----------------------------------------
        mid = sample_map(db, "加节点用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        page._focus_row(2)                     # 「采购」
        page.outline_add_sibling()
        settle(root, 3)
        check("加同级：节点数 +1", db.node_count(mid) == count + 1,
              (db.node_count(mid), count))
        check("新节点用的是占位文本", node_row(db, mid, NEW_NODE_TEXT) is not None,
              [r["text"] for r in db.list_nodes(mid)])
        fresh = node_row(db, mid, NEW_NODE_TEXT)
        check("新同级挂在同一个父下（仍是第一层）",
              int(fresh["parent_id"]) == int(node_row(db, mid, "采购")["parent_id"]),
              (fresh["parent_id"], node_row(db, mid, "采购")["parent_id"]))
        # 第一层节点的 ``parent_id`` 是**中心主题的 id**（只有根自己是 0），
        # 所以只能按 depth 过滤，再按 seq 还原同级顺序。
        level1 = sorted((r for r in db.list_nodes(mid) if int(r["depth"]) == 1),
                        key=lambda r: (int(r["seq"]), int(r["id"])))
        check("新节点插在「采购」后面（不是甩到最后）",
              [r["text"] for r in level1][:2] == ["采购", NEW_NODE_TEXT],
              [r["text"] for r in level1])
        # 光标要停在刚动过的那一行。这是「延迟事件不许重载编辑框」的现场证据：
        # 一旦 ``_on_nav_select`` 走了 refresh()，编辑框会被整体重写、光标被顶走。
        lines = page._outline_text_lines()
        row = page._outline_row()
        check("结构操作后光标停在动过的那一行（不被延迟事件冲掉）",
              lines[row - 1].strip() == NEW_NODE_TEXT, (row, lines[row - 1]))

        page._focus_row(2)
        count = db.node_count(mid)
        page.outline_add_child()
        settle(root, 3)
        child = [r for r in db.list_nodes(mid) if str(r["text"]) == NEW_NODE_TEXT
                 and int(r["parent_id"]) == int(node_row(db, mid, "采购")["id"])]
        check("加子节点：挂在光标那一行下面",
              len(child) == 1 and db.node_count(mid) == count + 1,
              (len(child), db.node_count(mid), count))

        # ---- 删行（要过 askyesno）------------------------------------
        mid = sample_map(db, "删行用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        page._focus_row(2)                     # 「采购」—— 它带着两个子节点
        with QuietDialogs(yes=True) as quiet:
            page.outline_delete_line()
        settle(root, 3)
        check("删行：连子树一起删掉（9 -> 6）",
              db.node_count(mid) == count - 3, (db.node_count(mid), count))
        check("删行前问了确认", quiet.kinds() == ["askyesno"], quiet.kinds())
        check("删完大纲同步了",
              outline_of(page) == ml.outline_text(db.load_tree(mid)),
              outline_of(page)[:60])

        mid = sample_map(db, "删根用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        page._focus_row(1)                     # 中心主题
        page.outline_delete_line()
        settle(root, 2)
        check("中心主题删不了（只提示，不弹确认）",
              "中心主题删不了" in page.status_var.get(), page.status_var.get())
        check("中心主题没被删掉", db.node_count(mid) == count)

        mid = sample_map(db, "取消删用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        page._focus_row(2)
        with QuietDialogs(yes=False) as quiet:
            page.outline_delete_line()
        settle(root, 2)
        check("确认框点「否」就一个节点都不删", db.node_count(mid) == count,
              (db.node_count(mid), count))

        # ---- 打字 -> 自动落库（防抖 + <<Modified>>）-------------------
        mid = sample_map(db, "打字用例")
        page._open_map(mid)
        settle(root, 3)
        count = db.node_count(mid)
        page.outline.insert("end", "\n  临时分支")
        settle(root, 2)
        check("打字后标记为「未同步」", page.sync_var.get() == "未同步",
              page.sync_var.get())
        page._flush_outline()                  # 立刻落库，不等 350ms
        settle(root, 2)
        check("落库后库里真的多了这个节点",
              node_row(db, mid, "临时分支") is not None
              and db.node_count(mid) == count + 1,
              (db.node_count(mid), count))
        check("落库后回到「已同步」", page.sync_var.get() == "已同步",
              page.sync_var.get())
        check("落库后画布跟着重画了",
              len(drawn_nodes(page)) == db.node_count(mid),
              (len(drawn_nodes(page)), db.node_count(mid)))
        # 程序性改写不该触发落库（``_applying`` 那道闸）
        page._set_outline_text(ml.outline_text(db.load_tree(mid)))
        settle(root, 2)
        check("程序性改写大纲不会触发自动落库",
              page._apply_job is None and page.sync_var.get() == "已同步",
              (page._apply_job, page.sync_var.get()))
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# E. 画布三不变量
# ══════════════════════════════════════════════════════════════════════════
def test_canvas() -> None:
    section("[E] 画布三不变量（折叠 / 缩放 / 重排）")
    db, _seed_id = cluster("canvas")
    mid = sample_map(db, "画布用例")
    root, page = build_page(db)
    try:
        page._open_map(mid)
        settle(root, 4)
        ids_before = {int(r["id"]) for r in db.list_nodes(mid)}
        drawn_before = drawn_nodes(page)
        check("画布上的节点数 == 库里的节点数",
              len(drawn_before) == len(ids_before) == db.node_count(mid),
              (len(drawn_before), len(ids_before), db.node_count(mid)))

        # ---- 折叠：只是不画，不是删 ----------------------------------
        page._focus_row(1)                     # 中心主题
        page.toggle_current_node()
        settle(root, 3)
        drawn_folded = drawn_nodes(page)
        check("**折叠不丢节点**：库里一个都不少",
              {int(r["id"]) for r in db.list_nodes(mid)} == ids_before,
              (len(db.list_nodes(mid)), len(ids_before)))
        check("折叠真的把子树从画布上摘下去了",
              len(drawn_folded) < len(drawn_before),
              (len(drawn_folded), len(drawn_before)))
        check("折叠中心主题后画布上只剩它一个",
              len(drawn_folded) == 1, len(drawn_folded))
        check("状态栏说了折叠", "折叠" in page.status_var.get(), page.status_var.get())

        page._focus_row(1)
        page.toggle_current_node()
        settle(root, 3)
        check("再折一次就展开，节点全回来",
              drawn_nodes(page) == drawn_before,
              (len(drawn_nodes(page)), len(drawn_before)))
        check("展开后库里还是那些节点",
              {int(r["id"]) for r in db.list_nodes(mid)} == ids_before)

        # ---- 缩放：极值不炸、节点数不变 ------------------------------
        bad = []
        for value in (0.5, 0.75, 1.0, 1.5, 2.0, 0.05, 9.9, -3.0):
            try:
                page.set_zoom(value)
                settle(root, 1)
                if drawn_nodes(page) != drawn_before:
                    bad.append((value, len(drawn_nodes(page))))
            except Exception as exc:              # noqa: BLE001
                bad.append((value, f"{type(exc).__name__}: {exc}"))
        check("缩放到极值都不炸，且画出来的节点数不变", not bad, bad)
        page.set_zoom(0.05)
        check("缩放被夹在下界", int(round(page.zoom * 100)) == 40, page.zoom)
        page.set_zoom(9.9)
        check("缩放被夹在上界", int(round(page.zoom * 100)) == 250, page.zoom)
        page.zoom_step(99)
        check("按到头取到最大档", int(round(page.zoom * 100)) == 200, page.zoom)
        page.zoom_step(-99)
        check("缩到头取到最小档", int(round(page.zoom * 100)) == 50, page.zoom)
        check("缩放后标签跟着变", page.zoom_var.get() == "50%", page.zoom_var.get())

        # ---- 重排：不碰数据 ------------------------------------------
        page.relayout()
        settle(root, 3)
        check("重排不炸、画出来的节点数不变",
              drawn_nodes(page) == drawn_before,
              (len(drawn_nodes(page)), len(drawn_before)))
        check("重排不碰数据（库里节点数与 id 集合都没变）",
              {int(r["id"]) for r in db.list_nodes(mid)} == ids_before)
        check("重排后视口回到左上",
              float(page.canvas.xview()[0]) == 0.0
              and float(page.canvas.yview()[0]) == 0.0,
              (page.canvas.xview(), page.canvas.yview()))
        check("有真实视口时不再挂「待排」标记",
              page._pending_layout is False
              and page._canvas_viewport() is not None,
              (page._pending_layout, page._canvas_viewport()))
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# F. BlindSession 三条不变量（假记录器，不碰库）
# ══════════════════════════════════════════════════════════════════════════
def test_blind_session_unit() -> None:
    section("[F] BlindSession 三条不变量（假记录器）")
    root = tk.Tk()
    root.geometry("900x700+40+40")
    try:
        written: list = []

        class Recorder:
            def __call__(self, map_id, feedback, brief):
                written.append((map_id, feedback, brief["branches"]))

        tree = ml.parse_outline(SAMPLE_OUTLINE)
        brief = ml.blind_brief(tree)
        levels = ml.reveal_levels(tree)
        session = BlindSession(root, 7, tree, on_grade=Recorder())
        settle(root, 3)

        check("只是把规模报出来（一级分支 / 总节点 / 最深）",
              session.brief["branches"] == brief["branches"] == 3
              and session.brief["total"] == brief["total"] == 9
              and session.brief["depth"] == brief["depth"] == 3,
              (session.brief, brief))
        check("**不变量A：结构区整块没映射**",
              session.revealed_count == 0
              and not mapped(session.answer_frame),
              (session.revealed_count, mapped(session.answer_frame)))
        check("第一屏只报中心主题", session.root_var.get() == "周末计划",
              session.root_var.get())
        screen = " ".join([session.head_var.get(), session.root_var.get(),
                           session.hint_var.get()])
        check("**不变量A2：一个一级分支文字都没提前泄露**",
              all(name not in screen for name in ("采购", "运动", "阅读")), screen)
        check("提示里说了先自己画再核对",
              "先拿纸笔" in session.hint_var.get(), session.hint_var.get())
        check("**不变量B：没展开完自评被吞掉**",
              all(str(b.cget("state")) == "disabled"
                  for b in session.grade_buttons.values())
              and session.results == []
              and len(session.levels) == 3,
              [(k, str(b.cget("state"))) for k, b in session.grade_buttons.items()])

        session.show_answer()
        settle(root, 2)
        check("展开一级后结构区真的映射出来",
              mapped(session.answer_frame) and session.revealed_count == 1,
              (mapped(session.answer_frame), session.revealed_count))
        check("第一级只给本层文字",
              "采购" in session.level_vars[0].get()
              and "超市" not in session.level_vars[0].get(),
              session.level_vars[0].get())
        check("还没展开完，自评仍禁用",
              not session._all_revealed()
              and all(str(b.cget("state")) == "disabled"
                      for b in session.grade_buttons.values()))

        for _ in range(len(levels) - 1):
            session.show_answer()
        settle(root, 2)
        check("逐级展开到全部",
              session._all_revealed()
              and session.revealed_count == len(levels),
              (session.revealed_count, len(levels)))
        check("最深一层是叶子层的文字",
              "公园" in session.level_vars[2].get(), session.level_vars[2].get())
        check("展开完自评解禁",
              all(str(b.cget("state")) == "normal"
                  for b in session.grade_buttons.values()))
        check("展开按钮变成「已全部展开」",
              "已全部展开" in str(session.reveal_button.cget("text")),
              session.reveal_button.cget("text"))

        check("空格在「已全展开」时 = 自评「记得」",
              (session._on_space() or True)
              and written == [(7, tc.FEEDBACK_KNOWN, 3)], written)
        check("**不变量C：同一张只写一次**",
              (session.grade(tc.FEEDBACK_KNOWN) or True)
              and len(written) == 1, written)
        settle(root, 2)
        check("结算后收起结构区", not mapped(session.answer_frame))
        check("结算后自评按钮全部禁用",
              all(str(b.cget("state")) == "disabled"
                  for b in session.grade_buttons.values()))
        check("结算文案给出正确率",
              "正确率" in session.hint_var.get(), session.hint_var.get())
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# G. 盲画走一遍（真库）
# ══════════════════════════════════════════════════════════════════════════
def test_blind_flow() -> None:
    section("[G] 盲画走一遍（真库）")
    db, _seed_id = cluster("blind")
    mid = sample_map(db, "盲画用例")
    root, page = build_page(db)
    try:
        page._open_map(mid)
        settle(root, 3)
        page.blind_current_map()
        settle(root, 3)
        session = page.blind_window
        check("盲画窗口真的开起来了",
              session is not None and session.winfo_exists() and mapped(session),
              bool(session))
        check("盲画的就是当前这张图", int(session.map_id) == mid,
              (session.map_id, mid))
        check("**不变量A：先给规模、后给结构**",
              session.revealed_count == 0 and not mapped(session.answer_frame),
              (session.revealed_count, mapped(session.answer_frame)))

        branches = len(db.load_tree(mid)["children"])
        for _ in range(len(session.levels)):
            session.show_answer()
        settle(root, 2)
        session.grade(tc.FEEDBACK_KNOWN)
        settle(root, 3)

        rows = db.list_reviews(map_id=mid)
        check("盲画写回 SRS：恰好一行流水", len(rows) == 1, rows)
        check("流水里留了这次的分支总数",
              int(rows[0]["branch_total"]) == branches,
              (rows[0]["branch_total"], branches))
        progress = db.get_progress(mid)
        check("进度真的推进了（记得 -> 掌握度上升、连续数 +1）",
              int(progress["mastery"]) == tc.MASTERY_WEAK
              and int(progress["correct_streak"]) == 1,
              progress)
        check("全库也只有这一行流水", len(db.list_reviews()) == 1,
              len(db.list_reviews()))

        session.close()
        settle(root, 3)
        check("关掉后页面把 blind_window 置空",
              page.blind_window is None, page.blind_window)
        check("关掉后按流水补了打卡",
              len(db.list_checkins()) == 1, db.list_checkins())
        check("关掉后状态栏报了本轮成绩",
              "正确率" in page.status_var.get(), page.status_var.get())
    finally:
        root.destroy()


# ══════════════════════════════════════════════════════════════════════════
# H. 生成今日训练待办
# ══════════════════════════════════════════════════════════════════════════
def test_todo_hook() -> None:
    section("[H] 生成今日训练待办")
    db, _map_id = cluster("todo")
    calls: list = []

    def hook(*, due, suggested):
        calls.append((due, suggested))
        return "今天盲画 3 张", "已生成今日训练待办：今天盲画 3 张"

    root, page = build_page(db, todo_hook=hook)
    try:
        check("**打开页面不会自动建待办**", calls == [], calls)
        page.make_today_todo()
        settle(root, 2)
        check("点一下才调一次桥", len(calls) == 1, calls)
        check("due 与库里的 due_count 一致",
              calls[0][0] == db.due_count(), (calls[0], db.due_count()))
        check("suggested 由页面按到期量现算（> 0）", calls[0][1] > 0, calls[0])
        check("状态栏回显了桥给的话",
              "今日训练待办" in page.status_var.get(), page.status_var.get())
        page.make_today_todo()
        check("再点一次又调一次（不缓存）", len(calls) == 2, calls)
    finally:
        root.destroy()

    root2, page2 = build_page(db)
    try:
        with QuietDialogs() as quiet:
            page2.make_today_todo()
        check("没注入桥时只提示、不报错",
              quiet.kinds() == ["showinfo"], (quiet.kinds(), quiet.texts))
    finally:
        root2.destroy()


# ══════════════════════════════════════════════════════════════════════════
# I. 关键纪律
# ══════════════════════════════════════════════════════════════════════════
def test_discipline() -> None:
    section("[I] 关键纪律")
    db, _map_id = cluster("discipline")
    root, page = build_page(db)
    try:
        settle(root, 3)
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
        check("五个视图帧都建好了（不是懒建）",
              len(page.views) == len(VIEW_CHOICES), sorted(page.views))
        check("工具栏标题用的是页面标题变量（不是写死的）",
              page.title_var.get() == dict(VIEW_CHOICES)[VIEW_TODAY],
              page.title_var.get())
    finally:
        root.destroy()


# ════════════════════════════════════════════════════════════════════════════
# J. 间隔重复算法（界面上够得着才算做完）
# ════════════════════════════════════════════════════════════════════════════
def test_algorithm_selector() -> None:
    section("[J] 间隔重复算法（下拉框要够得着、切了要落库）")
    db, _map_id = cluster("algo")
    root, page = build_page(db)
    try:
        page.show_view(VIEW_STATS)
        settle(root, 3)
        box = getattr(page, "algorithm_box", None)
        check("统计页有算法下拉框", box is not None)
        if box is None:
            return
        # 「控件不见了」多半是被 expand 区饿死：建了不等于看得见
        check("下拉框真的被映射出来（不是只 new 了不 pack）",
              bool(box.winfo_ismapped()) and int(box.winfo_width()) > 40,
              (box.winfo_ismapped(), box.winfo_width(), box.winfo_height()))
        check("三套算法都在下拉框里",
              tuple(box.cget("values"))
              == tuple(label for _key, label in tc.ALGORITHM_CHOICES),
              box.cget("values"))
        check("默认显示阶梯，旁边有一句说明",
              page.algorithm_var.get() == tc.algorithm_label(tc.DEFAULT_ALGORITHM)
              and str(page.algorithm_hint.cget("text")).strip() != "",
              (page.algorithm_var.get(), page.algorithm_hint.cget("text")))

        page.algorithm_var.set(tc.algorithm_label(tc.ALGORITHM_FSRS))
        page._on_algorithm_change()
        settle(root, 2)
        check("选了 FSRS 就写进库（界面够得着才叫做完）",
              db.get_algorithm() == tc.ALGORITHM_FSRS, db.get_algorithm())
        check("说明文案跟着换",
              "还记得的概率" in str(page.algorithm_hint.cget("text")),
              page.algorithm_hint.cget("text"))

        page.refresh()
        settle(root, 2)
        check("刷新后还是 FSRS（不是每次都弹回默认）",
              page.algorithm_var.get() == tc.algorithm_label(tc.ALGORITHM_FSRS)
              and db.get_algorithm() == tc.ALGORITHM_FSRS,
              page.algorithm_var.get())

        # 下拉框里出现认不出来的值：按「没选」处理，不许把空串写进库
        page.algorithm_var.set("不存在的算法")
        page._on_algorithm_change()
        settle(root, 2)
        check("认不出来的值不会把库写坏（回落显示当前值）",
              db.get_algorithm() == tc.ALGORITHM_FSRS
              and page.algorithm_var.get() == tc.algorithm_label(
                  tc.ALGORITHM_FSRS),
              (db.get_algorithm(), page.algorithm_var.get()))
    finally:
        root.destroy()


class _Ev:
    """假的事件对象。Tk 的事件对象也就是几个属性，够用就行。"""

    def __init__(self, x, y):
        self.x = x
        self.y = y


def test_free_canvas() -> None:
    section("[K] 自由画布（真的拖一次，坐标要进库）")
    db, map_id = cluster("freecv")
    root, page = build_page(db)
    try:
        page.show_view(VIEW_EDITOR)
        settle(root, 3)
        page.current_map_id = map_id
        page.tree = db.load_tree(map_id)
        settle(root, 3)

        check("编辑视图有「自由布局」按钮", hasattr(page, "free_button"))
        check("按钮真的被映射出来（不是只 new 了不 pack）",
              bool(page.free_button.winfo_ismapped())
              and int(page.free_button.winfo_width()) > 40,
              (page.free_button.winfo_ismapped(),
               page.free_button.winfo_width()))
        check("默认关着（不摆位置的时候就是自动布局）",
              page.free_layout is False
              and "关" in str(page.free_button.cget("text")),
              page.free_button.cget("text"))

        records = page.canvas_layout.get("nodes") or []
        node = next((r for r in records if r.get("key") is not None
                     and int(r["depth"]) == 1), None)
        check("布局里有可拖的一级分支", node is not None, len(records))
        if node is None:
            return

        def screen_of(record):
            """布局坐标 -> 画布像素。拖动手感全靠这一换算。"""
            ox, oy = page._canvas_offset
            return (record["x"] * page.zoom + ox + record["w"] * page.zoom / 2.0,
                    record["y"] * page.zoom + oy + record["h"] * page.zoom / 2.0)

        # 关着的时候按下去：不该抓任何节点（否则点一下就把节点挪了）
        cx, cy = screen_of(node)
        page._on_canvas_press(_Ev(cx, cy))
        check("关着的时候按下去不抓节点", page._drag is None)
        page._on_canvas_drag(_Ev(cx + 80, cy + 40))
        check("关着的时候拖动也不写坐标", db.node_positions(map_id) == {},
              db.node_positions(map_id))

        # 打开自由布局，真的拖一次
        page.toggle_free_layout()
        settle(root, 2)
        check("开了之后按钮文案跟着变",
              page.free_layout is True and "开" in str(page.free_button.cget("text")),
              page.free_button.cget("text"))

        cx, cy = screen_of(node)
        check("命中测试找得到这个节点（by_iid 与 tag 不是一个东西，拿错就拖不动）",
              page._node_at(_Ev(cx, cy)) == int(node["key"]),
              page._node_at(_Ev(cx, cy)))
        page._on_canvas_press(_Ev(cx, cy))
        check("按下之后抓住了节点", page._drag is not None)
        page._on_canvas_drag(_Ev(cx + 120, cy + 60))
        settle(root, 2)
        during = page._free_pos.get(int(node["key"]))
        check("拖动过程中画面就跟着走了（不是松手才动）", during is not None, during)
        page._on_canvas_release(_Ev(cx + 120, cy + 60))
        settle(root, 2)

        saved = db.node_positions(map_id)
        check("**松手之后坐标进了库**（下次打开还在）",
              int(node["key"]) in saved, saved)
        if int(node["key"]) in saved:
            auto_x = float(node["x"])
            check("坐标确实挪动了（不是原地打转）",
                  abs(saved[int(node["key"])][0] - auto_x) > 1.0,
                  (auto_x, saved[int(node["key"])]))
            check("坐标被夹在 >= 0（负坐标会跑到画布外，看着像节点丢了）",
                  saved[int(node["key"])][0] >= 0.0
                  and saved[int(node["key"])][1] >= 0.0, saved[int(node["key"])])

        # 关掉 -> 回到自动布局；再开 -> 手工位置回来
        page.toggle_free_layout()
        settle(root, 2)
        auto_now = page._node_record(int(node["key"]))
        check("关掉自由布局：节点回到自动排布的位置",
              abs(float(auto_now["x"]) - float(node["x"])) < 0.01,
              (auto_now["x"], node["x"]))
        page.toggle_free_layout()
        settle(root, 2)
        free_now = page._node_record(int(node["key"]))
        check("再打开：手工摆的位置还在（坐标是记在库里的）",
              abs(float(free_now["x"]) - saved[int(node["key"])][0]) < 0.01,
              (free_now["x"], saved.get(int(node["key"]))))

        # 点一下但没拖：不该写坐标（否则点一下节点就"被摆过"了）
        before = dict(db.node_positions(map_id))
        other = next((r for r in page.canvas_layout["nodes"]
                      if r.get("key") is not None
                      and int(r["key"]) != int(node["key"])
                      and int(r["depth"]) == 1), None)
        if other is not None:
            ox, oy = screen_of(other)
            page._on_canvas_press(_Ev(ox, oy))
            page._on_canvas_release(_Ev(ox, oy))
            check("点一下不拖：不写坐标", db.node_positions(map_id) == before,
                  db.node_positions(map_id))
    finally:
        root.destroy()


def main_test() -> None:
    test_skeleton()
    test_nav()
    test_views()
    test_editor()
    test_canvas()
    test_blind_session_unit()
    test_blind_flow()
    test_todo_hook()
    test_discipline()
    test_algorithm_selector()
    test_free_canvas()


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
