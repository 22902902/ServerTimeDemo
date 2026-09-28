# -*- coding: utf-8 -*-
"""思维导图 · 界面。

五视图，三栏骨架，与 ``excel_page.py`` / ``memory_page.py`` 同一套做法：
**页面对象只建一次**，之后靠 ``pack`` / ``pack_forget`` 切换视图。

    1 今日训练   到期的导图 + 盲画入口 + 建议练习量
    2 编辑工作台 左：大纲编辑（缩进 = 层级）  右：自动布局画布
    3 缩略图墙   全部导图的小图，一眼看清积累了多少
    4 训练模板   内置范式（SWOT / 5W1H / 费曼四步…），点一个即建一张
    5 打卡统计   日历 + 掌握度分布 + 正确率

「盲画」（``BlindSession``）是本模块的**核心动作**，与记忆宫殿的「走一遍」同构：

* **先给提示、再给结构** —— 只报中心主题与「一级分支几个 / 共几个节点 / 最深几层」，
  **故意不给任何分支文字**，那要靠自己回忆。界面顺序一旦反过来，练习效果直接归零。
* 逐级展开；**全部层级展开之前，自评按钮是禁用的**；自评三档**只写一次**。

大纲与数据库的双向关系（这是本页面的核心设计）
------------------------------------------------------------------------------
* **打字 -> 库**：编辑框改动走 ``save_outline_text``（防抖 350ms 自动落库）。
  这条路径认领节点 id（``save_outline`` 那三步），所以折叠状态与备注不会因为
  敲了几个字就丢。
* **结构操作 -> 库**：Tab / Shift+Tab / Enter / Alt+↑↓ / Alt+Del 与画布双击**不**
  自己拼文本，而是调 ``mindmap_db`` 的 ``indent_node`` / ``move_node`` /
  ``add_node`` / ``delete_node`` / ``toggle_collapsed``，然后**用树重新生成大纲
  文本**。理由：这些方法已经有测试守着，手搓缩进字符串只会重复一遍它们的逻辑，
  还更容易在中间插入一行时把缩进数错。

两个刻意的界面决定（都不是疏漏）
------------------------------------------------------------------------------
1. 编辑框里 ``Delete`` 保持「删一个字符」，删行是 **Alt+Delete**。正文里最常用的
   删除键不能被抢走 —— 抢走之后连改错别字都会删掉整行。
2. 结构操作之后编辑框会被**规范化重写**（缩进统一 2 空格、项目符号被去掉）。
   结构才是唯一事实来源，所以文本以树的表达为准。

能力注入（与 Excel 宝典同一手法，本模块**不 import main、不 import todo_db**）
------------------------------------------------------------------------------
``todo_hook`` 是「生成今日训练待办」的落库动作；``markdown`` 是 ``markdown_view``
模块（渲染模板预览）。两样都由 ``main`` 注入。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import mindmap_db
import mindmap_layout as ml
import training_core as tc
from dialog_form_style import (apply_dialog_form_style, create_form_entry,
                               create_form_label)
from page_components import (add_toolbar_buttons, create_menu_button,
                             create_page_toolbar, create_status_bar,
                             create_two_pane_layout)
from ui_components import (ScrollArea, create_flat_action_button,
                           create_metric_card, create_section_frame,
                           create_ttk_section_header)
from ui_theme import MAIN_PALETTE, TYPOGRAPHY

# ----------------------------------------------------------------------
# 视图
# ----------------------------------------------------------------------
VIEW_TODAY = "today"
VIEW_EDITOR = "editor"
VIEW_WALL = "wall"
VIEW_TEMPLATES = "templates"
VIEW_STATS = "stats"
VIEW_CHOICES = (
    (VIEW_TODAY, "今日训练"),
    (VIEW_EDITOR, "编辑工作台"),
    (VIEW_WALL, "缩略图墙"),
    (VIEW_TEMPLATES, "训练模板"),
    (VIEW_STATS, "打卡统计"),
)
VIEW_LABELS = dict(VIEW_CHOICES)

TREE_VIEW = "view"
TREE_MAP = "map"
TREE_TPL_MAP = "tplmap"
TREE_GROUP = "grp"

GROUP_MINE = "mine"
GROUP_TPL = "tpl"

ZOOM_VALUES = (("50%", 0.5), ("75%", 0.75), ("100%", 1.0),
               ("150%", 1.5), ("200%", 2.0))
ZOOM_MIN = 0.4
ZOOM_MAX = 2.5
ZOOM_DEFAULT = 1.0

CANVAS_PAD = 26
NODE_TAG = "node-"
EDGE_TAG = "edge"
TOAST_TAG = "toast"
WALL_COLUMNS = 3
WALL_MAX = 60
WALL_BOX = (232, 130)

INDENT_STEP = 2
NEW_NODE_TEXT = "新分支"
APPLY_DELAY_MS = 350
DUE_COLOR = "#a3372f"

MASTERY_FILTER_CHOICES = (("all", "全部掌握度"),) + tuple(
    (str(value), label) for value, label in tc.MASTERY_CHOICES)


def _tint(color, ratio) -> str:
    """把颜色朝白色混 ``ratio``（0=原色，1=纯白）。节点浅底用。"""
    text = str(color).lstrip("#")
    red, green, blue = (int(text[i:i + 2], 16) for i in (0, 2, 4))

    def blend(channel):
        return int(channel + (255 - channel) * ratio)

    return f"#{blend(red):02x}{blend(green):02x}{blend(blue):02x}"


# ======================================================================
# 对话框
# ======================================================================
class MapDialog(simpledialog.Dialog):
    """新建 / 编辑一张导图的信息。"""

    def __init__(self, parent, title, *, app_title, initial=None):
        self.initial = dict(initial or {})
        self.app_title = app_title
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MindMapDialog")
        self.entries: dict[str, tk.Widget] = {}
        row_index = 0
        for field, label, width in (("title", "中心主题", 30),
                                    ("category", "分类", 24),
                                    ("tags", "标签", 30)):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(
                row=row_index, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=width)
            entry.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, str(self.initial.get(field, "") or ""))
            self.entries[field] = entry
            row_index += 1

        create_form_label(master, "说明", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="nw", padx=6, pady=4)
        self.note_text = tk.Text(master, width=38, height=4, wrap="word")
        self.note_text.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
        self.note_text.insert("1.0", str(self.initial.get("root_note", "") or ""))

        master.columnconfigure(1, weight=1)
        return self.entries["title"]

    def validate(self):
        if not self.entries["title"].get().strip():
            messagebox.showwarning(self.app_title, "中心主题不能为空。", parent=self)
            return False
        return True

    def apply(self):
        self.result = {
            "title": self.entries["title"].get().strip(),
            "category": self.entries["category"].get().strip(),
            "tags": self.entries["tags"].get().strip(),
            "root_note": self.note_text.get("1.0", "end").strip(),
        }


# ======================================================================
# 盲画（核心动作）
# ======================================================================
class BlindSession(tk.Toplevel):
    """凭记忆复述一张导图的结构。

    **顺序不可颠倒**：第一屏只有中心主题与结构规模统计，**故意不给分支文字**。
    点「显示结构」才逐级放出；全部层级展开之前，三个自评按钮是**禁用**的。

    本类不认识数据库：自评通过 ``on_grade(map_id, feedback, brief)`` 回调交出去，
    这样测试可以注入一个假的记录器，验证「先提示后结构」与「只写一次」。
    """

    def __init__(self, master, map_id, tree, *, app_title="个人系统", title="盲画",
                 palette=MAIN_PALETTE, typography=TYPOGRAPHY,
                 on_grade=None, on_finish=None, on_close=None):
        super().__init__(master)
        self.title(title)
        self.configure(bg=palette.bg)
        self.geometry("720x560")
        self.minsize(600, 460)

        self.map_id = int(map_id)
        self.tree = ml.normalize(tree)
        self.brief = ml.blind_brief(self.tree)
        self.levels = ml.reveal_levels(self.tree)
        self.revealed_count = 0
        self.graded = False
        self.results: list[dict] = []
        self.on_grade = on_grade
        self.on_finish = on_finish
        self.on_close = on_close
        self.palette = palette
        self.typography = typography
        self.app_title = app_title
        self.finished = False

        self._build()
        self._render_current()
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<space>", lambda _e: self._on_space())
        self.bind("<Key-1>", lambda _e: self.grade(tc.FEEDBACK_FORGOT))
        self.bind("<Key-2>", lambda _e: self.grade(tc.FEEDBACK_VAGUE))
        self.bind("<Key-3>", lambda _e: self.grade(tc.FEEDBACK_KNOWN))
        self.protocol("WM_DELETE_WINDOW", self.close)

    # -- 构建 -----------------------------------------------------------
    def _build(self):
        palette = self.palette
        self.head_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.head_var, bg=palette.bg,
                 fg=palette.text_muted, font=self.typography.caption).pack(
            anchor="w", padx=24, pady=(16, 4))

        self.root_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.root_var, bg=palette.bg,
                 fg=palette.text_primary, font=self.typography.title).pack(
            anchor="w", padx=24)

        self.hint_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.hint_var, bg=palette.bg,
                 fg=palette.text_muted, font=self.typography.body,
                 wraplength=650, justify="left").pack(
            anchor="w", padx=24, pady=(4, 10))

        # 结构区：**没展开之前整块不 pack**，不是仅仅藏文字
        self.answer_frame = create_section_frame(self, "结构")
        self.level_vars: list[tk.StringVar] = []
        self.level_labels: list[tk.Widget] = []
        for _level in self.levels:
            var = tk.StringVar(value="")
            self.level_vars.append(var)
            self.level_labels.append(
                tk.Label(self.answer_frame, textvariable=var, bg=palette.bg,
                         fg=palette.text_primary, font=self.typography.body,
                         wraplength=640, justify="left"))

        buttons = tk.Frame(self, bg=palette.bg)
        buttons.pack(side="bottom", fill="x", padx=24, pady=16)
        self.reveal_button = create_flat_action_button(
            buttons, "显示结构（空格）", self.show_answer)
        self.reveal_button.pack(side="left")

        self.grade_buttons: dict[str, tk.Widget] = {}
        for value, label in ((tc.FEEDBACK_KNOWN, "记得（3）"),
                             (tc.FEEDBACK_VAGUE, "模糊（2）"),
                             (tc.FEEDBACK_FORGOT, "忘了（1）")):
            button = create_flat_action_button(
                buttons, label, lambda v=value: self.grade(v))
            button.pack(side="right", padx=4)
            button.configure(state="disabled")
            self.grade_buttons[value] = button

    # -- 渲染 -----------------------------------------------------------
    def _render_current(self):
        brief = self.brief
        self.head_var.set("盲画 · 第 1 / 1 张")
        self.root_var.set(brief["root"] or "（空导图）")
        self.hint_var.set(
            f"一级分支 {brief['branches']} 个 · 共 {brief['total']} 个节点 · "
            f"最深 {brief['depth']} 层。\n"
            "先拿纸笔（或在心里）把结构画出来，再点「显示结构」核对。")
        self.revealed_count = 0
        self.graded = False
        for var in self.level_vars:
            var.set("")
        for label in self.level_labels:
            label.pack_forget()
        self.answer_frame.pack_forget()
        if not self.levels:
            # 只有中心主题：没有可回忆的结构，直接解锁自评
            self.reveal_button.configure(state="disabled", text="无可展开层级")
            for button in self.grade_buttons.values():
                button.configure(state="normal")
        else:
            self.reveal_button.configure(state="normal", text="显示结构（空格）")
            for button in self.grade_buttons.values():
                button.configure(state="disabled")

    def _all_revealed(self) -> bool:
        return not self.levels or self.revealed_count >= len(self.levels)

    def show_answer(self):
        """展开下一级。**这是唯一会显示结构的路径。**"""
        if self.graded or self._all_revealed():
            return
        level = self.levels[self.revealed_count]
        texts = "、".join(level["texts"]) or "（空）"
        self.level_vars[self.revealed_count].set(
            f"第 {level['level']} 层（{len(level['texts'])} 个）：{texts}")
        self.level_labels[self.revealed_count].pack(anchor="w", pady=2)
        if self.revealed_count == 0:
            self.answer_frame.pack(fill="x", padx=24, pady=(6, 10))
        self.revealed_count += 1
        if self._all_revealed():
            self.reveal_button.configure(state="disabled", text="已全部展开")
            for button in self.grade_buttons.values():
                button.configure(state="normal")

    def grade(self, feedback):
        """自评。**结构没全展开不许评**；同一张**只写一次**。"""
        if self.graded or not self._all_revealed():
            return
        self.graded = True
        for button in self.grade_buttons.values():
            button.configure(state="disabled")
        self.results.append({"map_id": self.map_id, "feedback": feedback,
                             "branches": self.brief["branches"]})
        if self.on_grade is not None:
            self.on_grade(self.map_id, feedback, self.brief)
        self._render_summary()

    def _on_space(self):
        if self._all_revealed():
            self.grade(tc.FEEDBACK_KNOWN)
        else:
            self.show_answer()

    # -- 结算 -----------------------------------------------------------
    def summary(self) -> dict:
        reviewed = len(self.results)
        correct = sum(1 for r in self.results if r["feedback"] == tc.FEEDBACK_KNOWN)
        return {"total": 1, "reviewed": reviewed, "correct": correct,
                "accuracy": tc.accuracy(reviewed, correct)}

    def _render_summary(self):
        self.finished = True
        data = self.summary()
        self.head_var.set("本张结束")
        if data["reviewed"]:
            self.root_var.set(f"自评：{tc.feedback_label(self.results[0]['feedback'])}")
            self.hint_var.set(
                "记得的会越隔越久再出现；忘了的明天就会再来。"
                f"　本次正确率 "
                f"{tc.accuracy_percent(data['reviewed'], data['correct'])}。")
        else:
            self.root_var.set("已跳过")
            self.hint_var.set("")
        self.answer_frame.pack_forget()
        self.reveal_button.configure(state="disabled")
        for button in self.grade_buttons.values():
            button.configure(state="disabled")
        if self.on_finish is not None:
            self.on_finish(data)

    def close(self):
        if self.on_close is not None:
            try:
                self.on_close(self.summary())
            except Exception:  # noqa: BLE001 - 关闭时的回调不该把窗口卡住
                pass
        self.destroy()


# ======================================================================
# 页面
# ======================================================================
class MindMapPage(ttk.Frame):
    """思维导图页面。由 ``main`` 建一次，之后靠 pack / pack_forget 切换。"""

    def __init__(self, master, db, *, app_title="个人系统", on_status=None,
                 todo_hook=None, markdown=None, palette=MAIN_PALETTE,
                 typography=TYPOGRAPHY):
        super().__init__(master)
        self.db = db
        self.app_title = app_title
        self.on_status = on_status
        # 「生成今日训练待办」的落库动作，由 main 注入 —— 本模块不认识 todo_db
        self.todo_hook = todo_hook
        # markdown_view 模块，用来渲染模板预览；没注入就退化成纯文本
        self.markdown = markdown
        self.palette = palette
        self.typography = typography

        self.view_key = VIEW_TODAY
        self.current_map_id: int | None = None
        self.selected_template_code: str | None = None
        self.tree: dict = ml.empty_tree()
        self.canvas_layout: dict = {"nodes": [], "edges": [], "by_iid": {},
                                    "size": (1.0, 1.0), "bounds": (0, 0, 0, 0)}
        self.zoom = ZOOM_DEFAULT
        self.blind_window: BlindSession | None = None
        self._canvas_offset = (float(CANVAS_PAD), float(CANVAS_PAD))
        self._pending_layout = False
        self._pending_center = False
        self._applying = False
        self._apply_job = None
        self._nav_signature: list | None = None

        self.search_var = tk.StringVar()
        self.category_var = tk.StringVar(value="全部分类")
        self.title_var = tk.StringVar(value=VIEW_LABELS[VIEW_TODAY])
        self.meta_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="思维导图已就绪。")
        self.sync_var = tk.StringVar(value="")
        self.today_due_var = tk.StringVar(value="0")
        self.today_new_var = tk.StringVar(value="0")
        self.today_streak_var = tk.StringVar(value="0")
        self.stats_minutes_var = tk.StringVar(value="0")
        self.stats_days_var = tk.StringVar(value="0")
        self.stats_accuracy_var = tk.StringVar(value="—")
        self.zoom_var = tk.StringVar(value="100%")

        self._build()
        self.refresh()

    # ==================================================================
    # 构建
    # ==================================================================
    def _build(self):
        self._build_toolbar()
        _, left, right = create_two_pane_layout(
            self, left_width=250, right_pad=(16, 0),
            padding=(24, 0, 24, 16))
        self._build_nav(left)
        self._build_right(right)
        create_status_bar(self, self.status_var, padding=(24, 0, 24, 16))

    def _build_toolbar(self):
        toolbar = create_page_toolbar(self)
        add_toolbar_buttons(toolbar, [
            ("新建导图", self.add_map, "Primary.TButton"),
            ("开始今日盲画", self.start_today_training),
            ("盲画当前", self.blind_current_map),
            ("从模板新建", self.show_templates),
        ])
        create_menu_button(toolbar, "更多", [
            ("编辑导图信息", self.edit_current_map),
            "---",
            ("导出当前导图为 PNG", lambda: self.export_map("png")),
            ("导出当前导图为 Markdown", lambda: self.export_map("markdown")),
            ("导出当前导图为 OPML", lambda: self.export_map("opml")),
            ("导出当前导图为纯文本大纲", lambda: self.export_map("text")),
            "---",
            ("生成今日训练待办", self.make_today_todo),
            ("手动打卡", self.checkin_today),
            "---",
            ("删除当前导图", self.delete_current_map),
        ])

    # -- 左栏 -----------------------------------------------------------
    def _build_nav(self, parent):
        create_ttk_section_header(parent, "视图 / 导图").pack(anchor="w", pady=(0, 6))
        self.nav_tree = ttk.Treeview(parent, columns=("count",),
                                     show="tree headings", height=26,
                                     selectmode="browse")
        self.nav_tree.heading("#0", text="视图 / 导图", anchor="w")
        self.nav_tree.heading("count", text="节", anchor="e")
        self.nav_tree.column("#0", width=186, minwidth=120, stretch=True, anchor="w")
        self.nav_tree.column("count", width=42, minwidth=34, stretch=False,
                             anchor="e")
        self.nav_tree.pack(fill="both", expand=True)
        self.nav_tree.tag_configure("due", foreground=DUE_COLOR)
        self.nav_tree.bind("<<TreeviewSelect>>", self._on_nav_select)

    # -- 右栏 -----------------------------------------------------------
    def _build_right(self, parent):
        head = tk.Frame(parent, bg=self.palette.bg)
        head.pack(fill="x")
        tk.Label(head, textvariable=self.title_var, bg=self.palette.bg,
                 fg=self.palette.text_primary,
                 font=self.typography.subtitle).pack(side="left")
        tk.Label(head, textvariable=self.meta_var, bg=self.palette.bg,
                 fg=self.palette.text_muted,
                 font=self.typography.caption).pack(side="left", padx=12)

        # 五个视图帧**建一次**，切换只 pack / pack_forget
        self.views: dict[str, tk.Frame] = {}
        for key, builder in (
            (VIEW_TODAY, self._build_today_view),
            (VIEW_EDITOR, self._build_editor_view),
            (VIEW_WALL, self._build_wall_view),
            (VIEW_TEMPLATES, self._build_templates_view),
            (VIEW_STATS, self._build_stats_view),
        ):
            frame = tk.Frame(parent, bg=self.palette.bg)
            self.views[key] = frame
            builder(frame)

    # ---- 视图 1：今日训练 ---------------------------------------------
    def _build_today_view(self, parent):
        cards = tk.Frame(parent, bg=self.palette.bg)
        cards.pack(fill="x", pady=(12, 8))
        create_metric_card(cards, "今天到期", self.today_due_var,
                           "到点该盲画的导图。跳过就等于重新学一遍。").pack(
            side="left", padx=(0, 10))
        create_metric_card(cards, "建议新画", self.today_new_var,
                           "导图比记忆项重，建议量故意压小。").pack(side="left", padx=10)
        create_metric_card(cards, "连续打卡", self.today_streak_var,
                           "今天没打卡不算断 —— 夜里过了点不会归零。").pack(
            side="left", padx=10)

        bar = tk.Frame(parent, bg=self.palette.bg)
        bar.pack(fill="x", pady=(4, 6))
        create_flat_action_button(bar, "开始今日盲画",
                                  self.start_today_training).pack(side="left")
        create_flat_action_button(bar, "生成今日训练待办",
                                  self.make_today_todo).pack(side="left", padx=8)
        create_flat_action_button(bar, "手动打卡",
                                  self.checkin_today).pack(side="left")

        self.today_tree = self._make_map_tree(parent)
        self.today_tree.bind("<Double-1>", lambda _e: self.open_selected_in_editor())

    # ---- 视图 2：编辑工作台 -------------------------------------------
    def _build_editor_view(self, parent):
        split = tk.Frame(parent, bg=self.palette.bg)
        split.pack(fill="both", expand=True, pady=(12, 0))

        left = tk.Frame(split, bg=self.palette.bg, width=336)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        head = tk.Frame(left, bg=self.palette.bg)
        head.pack(fill="x")
        create_ttk_section_header(head, "大纲（缩进 = 层级）").pack(side="left")
        tk.Label(head, textvariable=self.sync_var, bg=self.palette.bg,
                 fg=self.palette.text_muted,
                 font=self.typography.caption).pack(side="right")

        # pack 顺序：先把底部的固定高度控件放好，最后才让编辑框 expand 吃掉中间。
        # 反过来（先 expand 再挤固定尺寸）在空间不够时后 pack 的会被 Tk **直接
        # 不映射** —— 代码写了、界面上根本不存在。
        actions = tk.Frame(left, bg=self.palette.bg)
        actions.pack(side="bottom", fill="x", pady=(6, 0))
        create_menu_button(actions, "行操作", [
            ("缩进（Tab）", self.outline_indent_in),
            ("反缩进（Shift+Tab）", self.outline_indent_out),
            "---",
            ("加同级（Enter）", self.outline_add_sibling),
            ("加子节点（Alt+Enter）", self.outline_add_child),
            "---",
            ("上移（Alt+↑）", self.outline_move_up),
            ("下移（Alt+↓）", self.outline_move_down),
            "---",
            ("删行（Alt+Del）", self.outline_delete_line),
        ])
        create_flat_action_button(actions, "折叠 / 展开当前",
                                  self.toggle_current_node).pack(side="left", padx=2)
        create_flat_action_button(actions, "重排 / 居中",
                                  self.relayout).pack(side="left", padx=2)

        self.outline = tk.Text(left, wrap="none", height=18, undo=True,
                               relief="solid", bd=1, padx=6, pady=4,
                               font=self.typography.mono)
        self.outline.pack(fill="both", expand=True, pady=(4, 0))
        self.outline.bind("<<Modified>>", self._on_outline_modified)
        # **直接绑方法，不要套 lambda** —— lambda 会把 return "break" 吞掉，
        # Tab 就退化成「插入一个制表符」，缩进功能静默失效。
        self.outline.bind("<Tab>", self.outline_indent_in)
        self.outline.bind("<Shift-Tab>", self.outline_indent_out)
        self.outline.bind("<ISO_Left_Tab>", self.outline_indent_out)
        self.outline.bind("<Return>", self.outline_add_sibling)
        self.outline.bind("<Alt-Return>", self.outline_add_child)
        self.outline.bind("<Alt-Up>", self.outline_move_up)
        self.outline.bind("<Alt-Down>", self.outline_move_down)
        self.outline.bind("<Alt-Delete>", self.outline_delete_line)

        right = tk.Frame(split, bg=self.palette.bg)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        right_head = tk.Frame(right, bg=self.palette.bg)
        right_head.pack(fill="x")
        create_ttk_section_header(right_head, "画布").pack(side="left")
        create_flat_action_button(right_head, "＋",
                                  lambda: self.zoom_step(1)).pack(side="right", padx=2)
        create_flat_action_button(right_head, "－",
                                  lambda: self.zoom_step(-1)).pack(side="right", padx=2)
        self.zoom_box = ttk.Combobox(
            right_head, textvariable=self.zoom_var, width=6, state="readonly",
            values=[label for label, _value in ZOOM_VALUES])
        self.zoom_box.pack(side="right", padx=4)
        self.zoom_box.bind("<<ComboboxSelected>>", self._on_zoom_selected)
        tk.Label(right_head, text="缩放", bg=self.palette.bg,
                 fg=self.palette.text_muted,
                 font=self.typography.caption).pack(side="right", padx=(8, 0))

        # 画布 + 滚动条。同样的顺序讲究：先 pack 定尺寸的滚动条，
        # 最后 pack 会 expand 的画布。
        holder = tk.Frame(right, bg=self.palette.bg)
        holder.pack(fill="both", expand=True, pady=(4, 0))
        self.canvas = tk.Canvas(holder, bg="#ffffff", highlightthickness=1,
                                highlightbackground=self.palette.border,
                                xscrollincrement=24, yscrollincrement=24)
        self.hbar = ttk.Scrollbar(holder, orient="horizontal",
                                  command=self.canvas.xview)
        self.hbar.pack(side="bottom", fill="x")
        self.vbar = ttk.Scrollbar(holder, orient="vertical",
                                  command=self.canvas.yview)
        self.vbar.pack(side="right", fill="y")
        self.canvas.configure(xscrollcommand=self.hbar.set,
                              yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Double-1>", self._on_canvas_double_click)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_canvas_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_canvas_wheel_x)
        self.canvas.bind("<Control-MouseWheel>", self._on_canvas_zoom_wheel)

    # ---- 视图 3：缩略图墙 ---------------------------------------------
    def _build_wall_view(self, parent):
        bar = tk.Frame(parent, bg=self.palette.bg)
        bar.pack(fill="x", pady=(12, 4))
        ttk.Entry(bar, textvariable=self.search_var, width=20).pack(side="left")
        self.category_box = ttk.Combobox(bar, textvariable=self.category_var,
                                        values=["全部分类"], state="readonly",
                                        width=14)
        self.category_box.pack(side="left", padx=(6, 4))
        self.category_box.bind("<<ComboboxSelected>>",
                               lambda _e: self._reload_wall())
        create_flat_action_button(bar, "搜索", self._reload_wall).pack(
            side="left", padx=4)
        create_flat_action_button(bar, "重置", self.reset_filters).pack(side="left")
        self.wall_hint_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.wall_hint_var, bg=self.palette.bg,
                 fg=self.palette.text_muted,
                 font=self.typography.caption).pack(side="left", padx=10)

        scroll = ScrollArea(parent, bg=self.palette.bg)
        scroll.pack(fill="both", expand=True, pady=(6, 0))
        self.wall_host = tk.Frame(scroll.inner, bg=self.palette.bg)
        self.wall_host.pack(fill="both", expand=True)

    # ---- 视图 4：训练模板 ---------------------------------------------
    def _build_templates_view(self, parent):
        split = tk.Frame(parent, bg=self.palette.bg)
        split.pack(fill="both", expand=True, pady=(12, 0))
        left = tk.Frame(split, bg=self.palette.bg, width=262)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        create_ttk_section_header(left, "内置范式").pack(anchor="w")
        self.template_tree = ttk.Treeview(left, columns=("cat",),
                                          show="tree headings", height=18,
                                          selectmode="browse")
        self.template_tree.heading("#0", text="模板", anchor="w")
        self.template_tree.heading("cat", text="类", anchor="e")
        self.template_tree.column("#0", width=190, anchor="w")
        self.template_tree.column("cat", width=56, anchor="e", stretch=False)
        self.template_tree.pack(fill="both", expand=True, pady=(4, 0))
        self.template_tree.bind("<<TreeviewSelect>>", self._on_template_select)

        right = tk.Frame(split, bg=self.palette.bg)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        head = tk.Frame(right, bg=self.palette.bg)
        head.pack(fill="x")
        self.template_desc_var = tk.StringVar(value="选一个模板看看骨架。")
        tk.Label(head, textvariable=self.template_desc_var, bg=self.palette.bg,
                 fg=self.palette.text_muted, font=self.typography.caption,
                 wraplength=440, justify="left").pack(side="left", anchor="w")
        create_flat_action_button(head, "用这个模板新建",
                                  self.create_from_selected_template).pack(side="right")

        self.template_body = tk.Text(right, wrap="word", height=20, relief="flat",
                                     bd=0, bg=self.palette.bg,
                                     highlightthickness=0, padx=2, pady=2)
        self.template_body.pack(fill="both", expand=True, pady=(6, 0))
        self.template_body.configure(state="disabled")

    # ---- 视图 5：打卡统计 ---------------------------------------------
    def _build_stats_view(self, parent):
        scroll = ScrollArea(parent, bg=self.palette.bg)
        scroll.pack(fill="both", expand=True, pady=(12, 0))
        host = scroll.inner

        cards = tk.Frame(host, bg=self.palette.bg)
        cards.pack(fill="x")
        create_metric_card(cards, "累计分钟", self.stats_minutes_var,
                           "30 天内累计练习时长。").pack(side="left", padx=(0, 10))
        create_metric_card(cards, "打卡天数", self.stats_days_var,
                           "30 天内打过卡的天数。").pack(side="left", padx=10)
        create_metric_card(cards, "正确率", self.stats_accuracy_var,
                           "30 天内盲画「记得」的比例。").pack(side="left", padx=10)

        create_ttk_section_header(host, "打卡日历（按周一对齐）").pack(
            anchor="w", pady=(16, 6))
        self.calendar_host = tk.Frame(host, bg=self.palette.bg)
        self.calendar_host.pack(fill="x")

        create_ttk_section_header(host, "掌握度分布").pack(anchor="w", pady=(16, 6))
        self.mastery_host = tk.Frame(host, bg=self.palette.bg)
        self.mastery_host.pack(fill="x")

        create_ttk_section_header(host, "最近盲画流水").pack(anchor="w", pady=(16, 6))
        self.review_tree = ttk.Treeview(host, columns=("date", "map", "feedback"),
                                        show="headings", height=8, selectmode="browse")
        for key, text, width in (("date", "日期", 100), ("map", "导图", 320),
                                 ("feedback", "自评", 80)):
            self.review_tree.heading(key, text=text, anchor="w")
            self.review_tree.column(key, width=width, anchor="w")
        self.review_tree.pack(fill="x")

    # -- 公共：导图表格 -------------------------------------------------
    def _make_map_tree(self, parent):
        tree = ttk.Treeview(parent,
                            columns=("map", "nodes", "branches", "mastery", "due"),
                            show="headings", height=12, selectmode="browse")
        for key, text, width in (("map", "导图", 240), ("nodes", "节点", 60),
                                 ("branches", "分支", 60), ("mastery", "掌握度", 70),
                                 ("due", "到期", 100)):
            tree.heading(key, text=text, anchor="w")
            tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True, pady=(6, 0))
        tree.tag_configure("due", foreground=DUE_COLOR)
        tree.bind("<<TreeviewSelect>>", self._on_map_row_select)
        return tree

    # ==================================================================
    # 视图切换与刷新
    # ==================================================================
    def show_view(self, key: str):
        if key not in self.views:
            return
        for frame in self.views.values():
            frame.pack_forget()
        self.views[key].pack(fill="both", expand=True, pady=(10, 0))
        self.view_key = key
        self.title_var.set(VIEW_LABELS.get(key, key))
        if key == VIEW_EDITOR:
            self._pending_layout = True
        self.refresh()

    def refresh(self):
        """整页刷新：左栏 + 当前视图。"""
        self._reload_nav()
        self._reload_today_metrics()
        if self.view_key == VIEW_TODAY:
            self._reload_today()
        elif self.view_key == VIEW_EDITOR:
            self._reload_editor()
        elif self.view_key == VIEW_WALL:
            self._reload_wall()
        elif self.view_key == VIEW_TEMPLATES:
            self._reload_templates()
        elif self.view_key == VIEW_STATS:
            self._reload_stats()
        self._refresh_meta()

    def _refresh_meta(self):
        maps = self.db.list_maps()
        nodes = sum(int(m["node_count"] or 0) for m in maps)
        self.meta_var.set(f"{len(maps)} 张导图 · {nodes} 个节点 · "
                          f"今日待盲画 {self.db.due_count()}")

    # -- 左栏 -----------------------------------------------------------
    def _reload_nav(self):
        tree = self.nav_tree
        maps = self.db.list_maps()
        selected = self.current_map_id
        # 第一道闸：内容没变就别重建。``tree.delete()`` 会把选中项一起清掉，
        # 于是每轮刷新都得重设一次选中 —— 而 Tk 的 ``selection_set`` 是**无条件**
        # 投递 ``<<TreeviewSelect>>`` 的，事件回来又触发刷新，能自激成死循环
        # （实测：切到某个视图后整个窗口卡死，栈停在
        # _on_nav_select -> refresh -> _reload_nav 上）。
        signature = [(m["id"], m["title"], m["node_count"], m["mastery"],
                      1 if m["due"] else 0) for m in maps]
        if signature != self._nav_signature:
            self._nav_signature = signature
            tree.delete(*tree.get_children())
            for key, label in VIEW_CHOICES:
                tree.insert("", "end", iid=f"{TREE_VIEW}:{key}", text=f"  {label}",
                            values=("",))
            mine = [m for m in maps
                    if not str(m.get("source_key") or "").startswith("tpl:")]
            from_tpl = [m for m in maps
                        if str(m.get("source_key") or "").startswith("tpl:")]
            tree.insert("", "end", iid=f"{TREE_GROUP}:{GROUP_MINE}",
                        text="▾ 我的导图", values=(len(mine),), open=True)
            for item in mine:
                self._insert_map_node(tree, f"{TREE_MAP}:{item['id']}", item,
                                      f"{TREE_GROUP}:{GROUP_MINE}")
            tree.insert("", "end", iid=f"{TREE_GROUP}:{GROUP_TPL}",
                        text="▾ 从模板创建", values=(len(from_tpl),), open=False)
            for item in from_tpl:
                self._insert_map_node(tree, f"{TREE_TPL_MAP}:{item['id']}", item,
                                      f"{TREE_GROUP}:{GROUP_TPL}")
        # 第二道闸：**左栏选中项恒等于「当前视图」**（与
        # ``excel_page._sync_nav_selection`` 是同一条口径）。编辑工作台里
        # 「当前那件事」是某一张导图，就选中那张；其余视图一律选中自己的
        # 视图节点。两条理由：
        #
        # * 只做「选中当前导图」的话，停在别的视图上时那条**延迟投递**的
        #   ``<<TreeviewSelect>>`` 回来后会一路 refresh 到 ``_reload_editor``，
        #   把视图**抢回**工作台（实测：切到缩略图墙，一帧后 view_key 变回
        #   editor）。
        # * 反过来一个选中都不设的话，``show_view()``（**唯一**会 pack 视图帧
        #   的地方）永远不会被调用 —— 首屏右栏一片空白（数据都读好了，只是
        #   那块帧没装上）。
        #
        # 「已选中同一项则一个字都别写」由 ``_select_only`` 自己保证：
        # ``selection_set`` 是无条件投递事件的，不比较就会自激成死循环。
        target = None
        if self.view_key == VIEW_EDITOR and selected is not None:
            for prefix in (TREE_MAP, TREE_TPL_MAP):
                if tree.exists(f"{prefix}:{selected}"):
                    target = f"{prefix}:{selected}"
                    break
        if target is None:
            target = f"{TREE_VIEW}:{self.view_key}"
        self._select_only(tree, target)

    def _insert_map_node(self, tree, iid, item, parent):
        tree.insert(parent, "end", iid=iid,
                    text=f"  {'●' if item['due'] else '·'} {item['title']}",
                    values=(item["node_count"],),
                    tags=("due",) if item["due"] else ())

    def _on_nav_select(self, _event=None):
        selection = self.nav_tree.selection()
        if not selection:
            return
        kind, _, value = selection[0].partition(":")
        if kind == TREE_GROUP:
            return                      # 分组标题只是个标尺，点了不改视图
        if kind == TREE_VIEW:
            self.current_map_id = None
            self.show_view(value)
            return
        map_id = int(value)
        # 「选中的就是当前这张、而且已经在工作台里」= 无事可做，直接返回。
        # 这道闸是必须的：``_reload_nav`` 每次重设选中都会**无条件**投递一次
        # ``<<TreeviewSelect>>``，事件回来若走 refresh() -> _reload_editor()
        # -> _set_outline_text()，编辑框会被整体重写一遍，光标被顶到最后一行
        # —— 结构操作刚 ``_focus_row`` 到位的位置，一帧之后就被冲掉了。
        if int(self.current_map_id or 0) == map_id and self.view_key == VIEW_EDITOR:
            return
        self.current_map_id = map_id
        if self.view_key != VIEW_EDITOR:
            self.show_view(VIEW_EDITOR)
        else:
            self.refresh()

    # -- 视图 1 ---------------------------------------------------------
    def _reload_today_metrics(self):
        stats = self.db.stats()
        self.today_due_var.set(str(stats["due"]))
        self.today_new_var.set(str(mindmap_db_suggest(stats["due"])))
        self.today_streak_var.set(str(stats["streak"]))

    def _reload_today(self):
        tree = self.today_tree
        tree.delete(*tree.get_children())
        for item in self.db.due_maps():
            tree.insert("", "end", iid=f"map:{item['id']}",
                        values=(item["title"], item["node_count"],
                                item["branch_count"],
                                tc.mastery_label(item["mastery"]),
                                item["next_review_at"] or "未排期"),
                        tags=("due",) if item["due"] else ())

    def _on_map_row_select(self, event=None):
        tree = event.widget if event is not None else None
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            return
        self.current_map_id = int(selection[0].split(":")[1])

    def open_selected_in_editor(self):
        if self.current_map_id is None:
            return
        self.show_view(VIEW_EDITOR)

    # -- 视图 2 ---------------------------------------------------------
    def _reload_editor(self):
        map_id = self.current_map_id
        if map_id is None:
            maps = self.db.list_maps()
            map_id = int(maps[0]["id"]) if maps else None
            self.current_map_id = map_id
        if map_id is None or self.db.get_map(map_id) is None:
            self.tree = ml.empty_tree()
            self._set_outline_text(ml.outline_text(self.tree))
            self.sync_var.set("没有导图")
            self._render_canvas()
            return
        self._load_map(map_id)

    def _load_map(self, map_id):
        self.tree = self.db.load_tree(map_id)
        self._set_outline_text(ml.outline_text(self.tree))
        self.sync_var.set("已同步")
        self._pending_layout = True
        self._render_canvas()

    def _set_outline_text(self, text):
        """程序性改写编辑框。**必须置 ``_applying`` 并复位 modified 标记**，
        否则会触发一轮自动落库 → 回写 → 再触发。"""
        self._applying = True
        try:
            self.outline.delete("1.0", "end")
            self.outline.insert("1.0", text)
            self.outline.edit_modified(False)
        finally:
            self._applying = False

    def _on_outline_modified(self, _event=None):
        if not self.outline.edit_modified():
            return
        self.outline.edit_modified(False)
        if self._applying:
            return
        self.sync_var.set("未同步")
        self._schedule_apply()

    def _schedule_apply(self, delay=APPLY_DELAY_MS):
        if self._apply_job is not None:
            try:
                self.after_cancel(self._apply_job)
            except Exception:  # noqa: BLE001 - 已经跑掉了就无所谓
                pass
        self._apply_job = self.after(delay, self._apply_outline)

    def _flush_outline(self):
        """把待落库的改动立刻写下去（结构操作前必须先做，否则树是旧的）。"""
        if self._apply_job is None:
            return
        try:
            self.after_cancel(self._apply_job)
        except Exception:  # noqa: BLE001
            pass
        self._apply_job = None
        self._apply_outline()

    def _apply_outline(self):
        """把大纲文本落库，并按新结构重排画布。

        **不改写编辑框** —— 那会把光标顶回开头。画布读的是库里的树（带 id），
        所以折叠状态与备注都能被 ``save_outline`` 认回来。
        """
        self._apply_job = None
        map_id = self.current_map_id
        if map_id is None or self._applying:
            return
        text = self.outline.get("1.0", "end").rstrip("\n")
        if not text.strip():
            self.sync_var.set("大纲为空")
            return
        self.db.save_outline_text(map_id, text)
        self._reload_tree_into_view()

    def _reload_tree_into_view(self, keep_text=True):
        """库 -> 树 -> 界面（画布 + 左栏 + 元信息）。"""
        map_id = self.current_map_id
        if map_id is None:
            return
        self.tree = self.db.load_tree(map_id)
        if not keep_text:
            self._set_outline_text(ml.outline_text(self.tree))
        self.sync_var.set("已同步")
        self._nav_signature = None          # 标题 / 节点数可能变了，逼一次重建
        self._render_canvas()
        self._reload_nav()
        self._refresh_meta()
        self._reload_today_metrics()

    # -- 大纲行操作（全部走数据层，再按树重写文本）----------------------
    def _outline_text_lines(self) -> list[str]:
        body = self.outline.get("1.0", "end")
        if body.endswith("\n"):
            body = body[:-1]
        return body.split("\n")

    def _outline_row(self) -> int:
        return int(self.outline.index("insert").split(".")[0])

    def _current_outline_node_id(self):
        """大纲里光标所在行 -> 树里节点的 id。

        ``outline_text`` 是 DFS 序，所以只要数「光标之前有几个非空行」。
        空行**不占位**（``_outline_lines`` 会跳过空行），这一点必须跟解析口径
        一致，否则光标前面留一个空行就会指到别的节点上。
        """
        lines = self._outline_text_lines()
        row = self._outline_row()
        if not (1 <= row <= len(lines)):
            return None
        if not lines[row - 1].strip():
            return None
        position = sum(1 for line in lines[:row] if line.strip())
        nodes = [node for node, _parent, _depth in ml.iter_nodes(self.tree)]
        if 1 <= position <= len(nodes):
            return nodes[position - 1].get("id")
        return None

    def _row_of_node(self, node_id) -> int:
        for index, (node, _parent, _depth) in enumerate(ml.iter_nodes(self.tree),
                                                       start=1):
            if node.get("id") == node_id:
                return index
        return 1

    def _focus_row(self, row):
        lines = self._outline_text_lines()
        target = max(1, min(int(row), max(1, len(lines))))
        self.outline.mark_set("insert", f"{target}.end")
        self.outline.see(f"{target}.0")

    def _node_rows(self) -> dict:
        return {int(r["id"]): r for r in self.db.list_nodes(self.current_map_id)}

    def _require_node(self):
        """光标行 -> 节点行。拿不到就提示并返回 ``None``。"""
        map_id = self.current_map_id
        if map_id is None:
            return None
        self._flush_outline()
        node_id = self._current_outline_node_id()
        if node_id is None:
            self._status("把光标放在某一行上（第一行是中心主题）。")
            return None
        row = self._node_rows().get(int(node_id))
        if row is None:
            self._status("没找到这一行对应的节点，先让大纲同步一下。")
            return None
        return row

    def _after_structure_change(self, node_id, message):
        if self._apply_job is not None:
            try:
                self.after_cancel(self._apply_job)
            except Exception:  # noqa: BLE001
                pass
            self._apply_job = None
        self._reload_tree_into_view(keep_text=False)
        self._focus_row(self._row_of_node(node_id))
        self._status(message)
        return "break"

    def outline_indent_in(self, _event=None):
        row = self._require_node()
        if row is None:
            return "break"
        if int(row["parent_id"]) == 0:
            self._status("中心主题不能再缩进。")
            return "break"
        if self.db.indent_node(int(row["id"]), out=False):
            return self._after_structure_change(int(row["id"]), "已缩进一层。")
        self._status("已经是上一级的第一个孩子，没法再缩进。")
        return "break"

    def outline_indent_out(self, _event=None):
        row = self._require_node()
        if row is None:
            return "break"
        if int(row["depth"]) <= 1:
            self._status("已经是第一层了，再往外就脱离中心主题。")
            return "break"
        if self.db.indent_node(int(row["id"]), out=True):
            return self._after_structure_change(int(row["id"]), "已提升一层。")
        self._status("没法再往外提。")
        return "break"

    def outline_add_sibling(self, _event=None):
        row = self._require_node()
        if row is None:
            return "break"
        map_id = self.current_map_id
        parent_id = int(row["parent_id"])
        siblings = sorted(
            (r for r in self._node_rows().values()
             if int(r["parent_id"]) == parent_id),
            key=lambda r: (int(r["seq"]), int(r["id"])))
        order = [int(r["id"]) for r in siblings]
        try:
            index = order.index(int(row["id"]))
        except ValueError:
            index = len(order) - 1
        new_id = self.db.add_node(map_id, parent_id, NEW_NODE_TEXT)
        # add_node 只会追加到最后，往后挪到目标位置（用公开 API 一步步换）
        for _ in range(len(order) - index - 1):
            if not self.db.move_node(new_id, -1):
                break
        return self._after_structure_change(new_id, "已在下面加了一个同级分支。")

    def outline_add_child(self, _event=None):
        row = self._require_node()
        if row is None:
            return "break"
        new_id = self.db.add_node(self.current_map_id, int(row["id"]),
                                  NEW_NODE_TEXT)
        return self._after_structure_change(new_id, "已加了一个子节点。")

    def outline_move_up(self, _event=None):
        return self._outline_move(-1)

    def outline_move_down(self, _event=None):
        return self._outline_move(1)

    def _outline_move(self, delta):
        row = self._require_node()
        if row is None:
            return "break"
        if int(row["parent_id"]) == 0:
            self._status("中心主题没有兄弟，动不了。")
            return "break"
        node_id = int(row["id"])
        if self.db.move_node(node_id, delta):
            return self._after_structure_change(
                node_id, "已上移。" if delta < 0 else "已下移。")
        self._status("已经在最上（最下）面了。")
        return "break"

    def outline_delete_line(self, _event=None):
        row = self._require_node()
        if row is None:
            return "break"
        node_id = int(row["id"])
        if int(row["parent_id"]) == 0:
            self._status("中心主题删不了 —— 想删整张导图请用「更多 → 删除当前导图」。")
            return "break"
        text = str(row["text"] or "")
        if not messagebox.askyesno(
                self.app_title,
                f"删掉「{text}」及其全部子节点？\n\n（不可撤销）", parent=self):
            return "break"
        self.db.delete_node(node_id)
        if self._apply_job is not None:
            try:
                self.after_cancel(self._apply_job)
            except Exception:  # noqa: BLE001
                pass
            self._apply_job = None
        self._reload_tree_into_view(keep_text=False)
        self._focus_row(min(self._outline_row(), len(self._outline_text_lines())))
        self._status("已删除。")
        return "break"

    # ==================================================================
    # 画布
    # ==================================================================
    def _canvas_viewport(self):
        """真实可视尺寸。**未映射或还是 1x1 时返回 ``None``** —— 首帧的控件一律
        报 1x1，拿它去算「装不装得下」必然算错。"""
        if not self.canvas.winfo_ismapped():
            return None
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 1 or height <= 1:
            return None
        return width, height

    def _render_canvas(self):
        canvas = self.canvas
        canvas.delete("all")
        layout = ml.layout(self.tree)
        self.canvas_layout = layout
        zoom = self.zoom
        width, height = layout["size"]
        viewport = self._canvas_viewport()
        if viewport is None:
            # 量不到就先按左上角画，并挂上待办：等第一次带真实尺寸的 Configure
            offset_x = offset_y = float(CANVAS_PAD)
            self._pending_layout = True
        else:
            self._pending_layout = False
            offset_x = max(float(CANVAS_PAD), (viewport[0] - width * zoom) / 2.0)
            offset_y = max(float(CANVAS_PAD), (viewport[1] - height * zoom) / 2.0)
        self._canvas_offset = (offset_x, offset_y)
        self._draw_map(canvas, layout, zoom, offset_x, offset_y, with_tags=True)
        canvas.configure(scrollregion=(
            0, 0, int(width * zoom + offset_x * 2),
            int(height * zoom + offset_y * 2)))
        self._pending_center = False

    def _draw_map(self, canvas, layout, zoom, offset_x, offset_y, *,
                  with_tags=False, label_font=None):
        """把一份布局画到任意 Canvas 上（主画布与缩略图墙共用同一份代码）。"""
        by_iid = layout["by_iid"]
        edge_width = max(1.0, 1.6 * zoom)

        def px(value, offset):
            return value * zoom + offset

        # 先连线、后节点 —— 反过来连线会压在节点上
        for parent_iid, child_iid in layout["edges"]:
            parent = by_iid.get(parent_iid)
            child = by_iid.get(child_iid)
            if parent is None or child is None:
                continue
            x1, y1, x2, y2 = ml.edge_points(parent, child)
            points = ml.curve_points(x1, y1, x2, y2)
            flat = []
            for index in range(0, len(points) - 1, 2):
                flat.append(px(points[index], offset_x))
                flat.append(px(points[index + 1], offset_y))
            canvas.create_line(*flat, smooth=True, tags=(EDGE_TAG,),
                               fill=_tint(ml.depth_color(child["depth"]), 0.55),
                               width=edge_width)

        for node in layout["nodes"]:
            depth = int(node["depth"])
            color = ml.depth_color(depth)
            key = node.get("key")
            tags = (f"{NODE_TAG}{key}",) if (with_tags and key is not None) else ()
            left = px(node["x"], offset_x)
            top = px(node["y"], offset_y)
            right = px(node["x"] + node["w"], offset_x)
            bottom = px(node["y"] + node["h"], offset_y)
            is_root = depth == 0
            canvas.create_rectangle(
                left, top, right, bottom, tags=tags,
                fill=color if is_root else _tint(color, 0.90),
                outline=color, width=1.4 if zoom >= 0.75 else 1.0)
            canvas.create_text(
                (left + right) / 2.0, (top + bottom) / 2.0, text=node["text"],
                tags=tags, fill="#ffffff" if is_root else color,
                font=label_font or ("", max(7, int(11 * min(zoom, 1.6)))),
                width=max(20.0, right - left - 10.0))
            if node.get("hidden_children"):
                canvas.create_text(
                    right - 4, top + 3, tags=tags, anchor="ne",
                    text=f"+{node['hidden_children']}", fill=color,
                    font=("", max(6, int(9 * min(zoom, 1.6)))))

    def _on_canvas_configure(self, _event=None):
        """第一次拿到真实尺寸时把版式重排一遍 —— 首帧量到的 1x1 不能用。"""
        if not self._pending_layout and not self._pending_center:
            return
        if self._canvas_viewport() is None:
            return
        self._pending_layout = False
        self._pending_center = False
        self._render_canvas()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def _node_at(self, event):
        """命中测试。用几何重叠，不用 ``winfo_containing`` —— 后者是「屏幕命中」，
        指针下压着任何置顶窗口就返回空（拖拽自己的影子窗口也算）。"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        for item in reversed(self.canvas.find_overlapping(x, y, x, y)):
            for tag in self.canvas.gettags(item):
                if tag.startswith(NODE_TAG):
                    try:
                        return int(tag[len(NODE_TAG):])
                    except ValueError:
                        return None
        return None

    def _on_canvas_double_click(self, event):
        """双击节点 = 折叠 / 展开。**先落库再重画**，所以关掉窗口也是这个状态。"""
        node_id = self._node_at(event)
        if node_id is None:
            return
        result = self.db.toggle_collapsed(node_id)
        if result is None:
            return
        self.tree = self.db.load_tree(self.current_map_id)
        self._render_canvas()
        self.canvas.delete(TOAST_TAG)
        self.canvas.create_text(
            12, 12, anchor="nw", tags=(TOAST_TAG,),
            text="已折叠" if result["collapsed"] else "已展开",
            fill=self.palette.text_muted, font=("", 9))
        self.after(900, lambda: self.canvas.delete(TOAST_TAG))

    def _on_canvas_wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_canvas_wheel_x(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_canvas_zoom_wheel(self, event):
        self.zoom_step(1 if event.delta > 0 else -1)
        return "break"

    def _on_zoom_selected(self, _event=None):
        label = self.zoom_var.get()
        for text, value in ZOOM_VALUES:
            if text == label:
                self.zoom = float(value)
                self._render_canvas()
                return

    def zoom_step(self, delta):
        """按预设档位放大 / 缩小。档位之间的非标值也能正确取到最近的一档。"""
        current = min(range(len(ZOOM_VALUES)),
                      key=lambda i: abs(float(ZOOM_VALUES[i][1]) - self.zoom))
        target = ZOOM_VALUES[max(0, min(len(ZOOM_VALUES) - 1,
                                        current + int(delta)))][1]
        self.set_zoom(target)

    def set_zoom(self, value):
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(value)))
        self.zoom_var.set(f"{int(round(self.zoom * 100))}%")
        self._render_canvas()

    def relayout(self):
        """重算坐标并回到左上（装得下就居中）。**不碰数据。**"""
        self._pending_layout = True
        self._render_canvas()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    # -- 折叠 -----------------------------------------------------------
    def toggle_current_node(self):
        map_id = self.current_map_id
        if map_id is None:
            return
        self._flush_outline()
        node_id = self._current_outline_node_id()
        if node_id is None:
            self._status("把光标放在某一行上（第一行是中心主题）。")
            return
        result = self.db.toggle_collapsed(node_id)
        if result is None:
            return
        self.tree = self.db.load_tree(map_id)
        self._render_canvas()
        self._status("已折叠。" if result["collapsed"] else "已展开。")

    # -- 视图 3 ---------------------------------------------------------
    def _reload_wall(self):
        self.category_box.configure(values=["全部分类"] + self.db.categories())
        category = self.category_var.get()
        rows = self.db.list_maps(
            category=None if category in ("", "全部分类") else category,
            keyword=self.search_var.get())
        for child in self.wall_host.winfo_children():
            child.destroy()
        shown = rows[:WALL_MAX]
        self.wall_hint_var.set(
            f"显示 {len(shown)} / {len(rows)} 张" if len(rows) > len(shown)
            else f"共 {len(rows)} 张")
        for index, item in enumerate(shown):
            self._build_wall_card(item, index // WALL_COLUMNS, index % WALL_COLUMNS)
        for column in range(WALL_COLUMNS):
            self.wall_host.columnconfigure(column, weight=1, uniform="wall")

    def _build_wall_card(self, item, row, column):
        palette = self.palette
        card = tk.Frame(self.wall_host, bg=palette.bg, relief="solid", bd=1)
        card.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)
        head = tk.Frame(card, bg=palette.bg)
        head.pack(fill="x", padx=6, pady=(5, 2))
        tk.Label(head, text=item["title"], bg=palette.bg, fg=palette.text_primary,
                 font=self.typography.caption, anchor="w").pack(side="left")
        tk.Label(head, text=tc.mastery_label(item["mastery"]), bg=palette.bg,
                 fg=tc.mastery_color(item["mastery"]),
                 font=self.typography.caption).pack(side="right")

        box_w, box_h = WALL_BOX
        canvas = tk.Canvas(card, width=box_w, height=box_h, bg="#ffffff",
                           highlightthickness=0)
        canvas.pack(padx=6, pady=(0, 4))
        layout = ml.layout(self.db.load_tree(item["id"]))
        width, height = layout["size"]
        zoom = min((box_w - 12) / max(1.0, width),
                   (box_h - 12) / max(1.0, height), 1.0)
        offset_x = max(6.0, (box_w - width * zoom) / 2.0)
        offset_y = max(6.0, (box_h - height * zoom) / 2.0)
        self._draw_map(canvas, layout, zoom, offset_x, offset_y, label_font=("", 6))
        canvas.bind("<Button-1>",
                    lambda _e, mid=int(item["id"]): self._open_map(mid))

        foot = tk.Frame(card, bg=palette.bg)
        foot.pack(fill="x", padx=6, pady=(0, 5))
        tk.Label(foot, text=f"{item['node_count']} 节点 · {item['branch_count']} 分支",
                 bg=palette.bg, fg=palette.text_muted,
                 font=self.typography.caption).pack(side="left")
        if item["due"]:
            tk.Label(foot, text="该盲画了", bg=palette.bg, fg=DUE_COLOR,
                     font=self.typography.caption).pack(side="right")

    def _open_map(self, map_id):
        self.current_map_id = int(map_id)
        self.show_view(VIEW_EDITOR)

    def reset_filters(self):
        self.search_var.set("")
        self.category_var.set("全部分类")
        self._reload_wall()

    # -- 视图 4 ---------------------------------------------------------
    def _reload_templates(self):
        tree = self.template_tree
        tree.delete(*tree.get_children())
        items = self.db.list_templates()
        for item in items:
            tree.insert("", "end", iid=f"tpl:{item['code']}",
                        text=f"  {item['name']}", values=(item["category"],))
        if self.selected_template_code is None:
            self.selected_template_code = items[0]["code"] if items else None
        if self.selected_template_code:
            self._select_only(tree, f"tpl:{self.selected_template_code}")
        self._render_template()

    def _on_template_select(self, _event=None):
        selection = self.template_tree.selection()
        if not selection:
            return
        self.selected_template_code = selection[0].split(":", 1)[1]
        self._render_template()

    def _render_template(self):
        widget = self.template_body
        item = (self.db.get_template(self.selected_template_code)
                if self.selected_template_code else None)
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if not item:
            self.template_desc_var.set("选一个模板看看骨架。")
            widget.insert("1.0", "左边选一个模板。")
        else:
            self.template_desc_var.set(
                f"{item['name']} · {item['category']} —— {item['description']}")
            text = (f"# {item['name']}\n\n{item['description']}\n\n---\n\n"
                    + ml.to_markdown(ml.parse_outline(item["outline"])))
            if self.markdown is not None:
                try:
                    self.markdown.render(widget, text, empty_hint="")
                except Exception:  # noqa: BLE001 - 渲染失败不该让整页打不开
                    widget.configure(state="normal")
                    widget.delete("1.0", "end")
                    widget.insert("1.0", text)
            else:
                widget.insert("1.0", text)
        widget.configure(state="disabled")

    def show_templates(self):
        self.show_view(VIEW_TEMPLATES)

    def create_from_selected_template(self):
        if not self.selected_template_code:
            messagebox.showinfo(self.app_title, "先在左边选一个模板。", parent=self)
            return
        item = self.db.get_template(self.selected_template_code)
        map_id = self.db.create_from_template(self.selected_template_code)
        self.current_map_id = map_id
        self._status(f"已按「{item['name']}」新建一张导图 —— 改写大纲就是你的了。")
        self.show_view(VIEW_EDITOR)

    # -- 视图 5 ---------------------------------------------------------
    def _reload_stats(self):
        stats = self.db.stats()
        self.stats_minutes_var.set(str(stats["minutes"]))
        self.stats_days_var.set(str(stats["days"]))
        self.stats_accuracy_var.set(
            tc.accuracy_percent(stats["reviewed"], stats["correct"]))

        palette = self.palette
        for child in self.calendar_host.winfo_children():
            child.destroy()
        header = tk.Frame(self.calendar_host, bg=palette.bg)
        header.pack(anchor="w")
        tk.Label(header, text="", width=6, bg=palette.bg).pack(side="left")
        for label in tc.weekday_headers():
            tk.Label(header, text=label, width=4, bg=palette.bg,
                     fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")
        for row in tc.checkin_grid(self.db.checkin_dates()):
            line = tk.Frame(self.calendar_host, bg=palette.bg)
            line.pack(anchor="w")
            tk.Label(line, text=row["label"], width=6, bg=palette.bg,
                     fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")
            for cell in row["cells"]:
                fill = tc.CHECKIN_FILL if cell["checked"] else palette.bg
                text = "·" if cell["is_future"] else str(cell["date"].day)
                tk.Label(line, text=text, width=4, bg=fill,
                         fg=palette.text_primary, font=self.typography.caption,
                         relief="solid" if cell["is_today"] else "flat",
                         bd=1 if cell["is_today"] else 0).pack(
                    side="left", padx=1, pady=1)

        for child in self.mastery_host.winfo_children():
            child.destroy()
        distribution = self.db.mastery_distribution()
        total = max(1, sum(distribution.values()))
        for value, text in tc.MASTERY_CHOICES:
            count = int(distribution.get(value, 0))
            line = tk.Frame(self.mastery_host, bg=palette.bg)
            line.pack(fill="x", pady=1)
            tk.Label(line, text=text, width=6, anchor="w", bg=palette.bg,
                     fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")
            tk.Frame(line, bg=tc.mastery_color(value),
                     width=int(240 * count / total), height=12).pack(side="left")
            tk.Label(line, text=f" {count}", bg=palette.bg, fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")

        self.review_tree.delete(*self.review_tree.get_children())
        for row in self.db.list_reviews(limit=50):
            item = self.db.get_map(row["map_id"]) or {}
            self.review_tree.insert(
                "", "end",
                values=(row["review_date"], item.get("title", ""),
                        tc.feedback_label(row["feedback"])))

    # -- 公共填充 -------------------------------------------------------
    def _select_only(self, tree, iid) -> bool:
        """只在「选中项确实不同」时才写 selection，返回是否真的写了。

        踩过的坑：Tk 的 ``tree.selection_set()`` 是**无条件**投递
        ``<<TreeviewSelect>>`` 的，而 ``tree.delete()`` 又会把选中项一并清掉。
        于是「刷新 -> 重设选中 -> 事件 -> 再刷新」能自激成死循环。
        判据必须是**把当前选区读回来比较**；布尔守卫拦不住 —— 事件要等下一轮
        事件循环才投递，那时守卫早已复位。
        """
        # 存在性判定必须用 ``exists`` 而不是 ``get_children()``：后者只给
        # **顶层**节点，而导图节点是挂在「我的导图 / 从模板创建」分组下面的
        # —— 用 ``get_children()`` 判定会让本方法对每一张导图都返回 False
        # （实测：``_open_map(mid)`` 之后 ``nav_tree.selection() == ()``，
        # 左栏高亮永远跟不上当前导图）。
        if iid is None or not tree.exists(iid):
            return False
        if tuple(tree.selection()) == (iid,):
            return False
        tree.selection_set(iid)
        return True

    def _status(self, text: str) -> None:
        self.status_var.set(text)
        if self.on_status is not None:
            try:
                self.on_status(text)
            except Exception:  # noqa: BLE001
                pass

    # ==================================================================
    # 动作
    # ==================================================================
    # -- 导图 -----------------------------------------------------------
    def add_map(self):
        dialog = MapDialog(self, "新建导图", app_title=self.app_title)
        if not dialog.result:
            return
        map_id = self.db.add_map(**dialog.result)
        self.current_map_id = map_id
        self._nav_signature = None
        self._status(f"已新建导图「{dialog.result['title']}」，改大纲就能长出结构。")
        self.show_view(VIEW_EDITOR)

    def edit_current_map(self):
        map_id = self.current_map_id
        if map_id is None:
            messagebox.showinfo(self.app_title, "先在左栏选一张导图。", parent=self)
            return
        item = self.db.get_map(map_id)
        if not item:
            return
        dialog = MapDialog(self, "编辑导图信息", app_title=self.app_title,
                           initial=item)
        if not dialog.result:
            return
        payload = dict(dialog.result)
        new_title = payload.pop("title")
        self.db.update_map(map_id, **payload)
        # 中心主题与标题是一回事（save_outline 也是这么写的），标题改了要一起改根节点，
        # 否则下一次保存大纲就把标题冲回去了
        if new_title and new_title != str(item.get("title") or ""):
            root = self.db.root_node(map_id)
            if root:
                self.db.update_node(int(root["id"]), text=new_title)
        self._nav_signature = None
        self._reload_tree_into_view(keep_text=False)
        self._status("导图信息已更新。")

    def delete_current_map(self):
        map_id = self.current_map_id
        if map_id is None:
            messagebox.showinfo(self.app_title, "先在左栏选一张导图。", parent=self)
            return
        item = self.db.get_map(map_id)
        if not item:
            return
        if not messagebox.askyesno(
                self.app_title,
                f"删除导图「{item['title']}」？\n\n节点与盲画记录一起删掉，不可撤销。",
                parent=self):
            return
        self.db.delete_map(map_id)
        self.current_map_id = None
        self._nav_signature = None
        self._status("已删除。")
        self.refresh()

    # -- 盲画 -----------------------------------------------------------
    def start_today_training(self):
        rows = self.db.due_maps()
        if not rows:
            self._status("今天没有要盲画的导图。去「训练模板」建一张新的。")
            messagebox.showinfo(self.app_title,
                                "今天没有该盲画的，也没有没画过的 —— 干净。\n"
                                "想多练就去「训练模板」建一张。", parent=self)
            return
        self._open_blind(int(rows[0]["id"]))

    def blind_current_map(self):
        map_id = self.current_map_id
        if map_id is None:
            messagebox.showinfo(self.app_title, "先在左栏选一张导图。", parent=self)
            return
        self._open_blind(map_id)

    def _open_blind(self, map_id):
        if self.blind_window is not None and self.blind_window.winfo_exists():
            self.blind_window.lift()
            return
        self.blind_window = BlindSession(
            self, map_id, self.db.load_tree(map_id), app_title=self.app_title,
            title=f"盲画 · {(self.db.get_map(map_id) or {}).get('title', '思维导图')}",
            palette=self.palette, typography=self.typography,
            on_grade=self._grade_map, on_finish=self._finish_blind,
            on_close=lambda _summary: self._after_blind_closed())

    def _grade_map(self, map_id, feedback, brief):
        """写回 SRS。**每张导图每轮恰好一行流水**。

        ``branch_total`` 留档（这次盲画时这张图有几个一级分支）；
        ``branch_hit`` 不猜 —— 用户只给了三档自评，编一个命中数就是假数据。
        """
        self.db.record_review(map_id, feedback,
                              branch_hit=0, branch_total=brief["branches"])

    def _finish_blind(self, summary):
        self._status(
            f"本轮：盲画 {summary['reviewed']} 张，记得 {summary['correct']} 张，"
            f"正确率 {tc.accuracy_percent(summary['reviewed'], summary['correct'])}。")

    def _after_blind_closed(self):
        self.blind_window = None
        self.db.autofill_today()
        self.refresh()

    # -- 打卡与待办 -----------------------------------------------------
    def checkin_today(self):
        record = self.db.autofill_today()
        minutes = simpledialog.askstring(
            "打卡", f"今天练了多少分钟？（已盲画 {record['maps_reviewed']} 张）",
            initialvalue=str(record["minutes"] or 20), parent=self)
        if minutes is not None:
            try:
                record = self.db.checkin(minutes=int(minutes or 0))
            except ValueError:
                messagebox.showwarning(self.app_title, "分钟数要填数字。", parent=self)
                return
        self._status(f"已打卡：盲画 {record['maps_reviewed']} 张、"
                     f"新画 {record['maps_new']} 张。")
        self.refresh()

    def make_today_todo(self):
        if self.todo_hook is None:
            messagebox.showinfo(self.app_title, "待办联动没有接上。", parent=self)
            return
        due = self.db.due_count()
        suggested = mindmap_db_suggest(due)
        title, message = self.todo_hook(due=due, suggested=suggested)
        self._status(message or f"已生成今日训练待办：{title}")

    # -- 导出 -----------------------------------------------------------
    def export_map(self, fmt):
        map_id = self.current_map_id
        if map_id is None:
            messagebox.showinfo(self.app_title, "先在左栏选一张导图。", parent=self)
            return
        stem = str((self.db.get_map(map_id) or {}).get("title") or "").strip() \
            or "思维导图"
        if fmt == "png":
            self._export_png(map_id, stem)
            return
        payload, extension, _mime = ml.export_bytes(
            self.db.load_tree(map_id), fmt, title=stem)
        path = self._ask_save_path("导出导图", stem, extension,
                                   [("所有文件", "*.*")])
        if not path:
            return
        with open(path, "wb") as handle:
            handle.write(payload)
        self._status(f"已导出到 {path}")

    def _ask_save_path(self, title, stem, extension, filetypes):
        return filedialog.asksaveasfilename(
            title=title, defaultextension=extension,
            initialfile=f"{stem}{extension}", filetypes=filetypes)

    def _export_png(self, map_id, stem):
        try:
            import mindmap_image
        except ImportError:
            messagebox.showinfo(self.app_title, "缺少导出 PNG 需要的组件。",
                                parent=self)
            return
        if not mindmap_image.available():
            messagebox.showinfo(
                self.app_title,
                "导出 PNG 需要 Pillow 与一个中文字体，本机没找到。\n"
                "可以先导出 Markdown / OPML。", parent=self)
            return
        path = self._ask_save_path("导出 PNG", stem, ".png",
                                   [("PNG 图片", "*.png"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            payload = mindmap_image.render_png(self.db.load_tree(map_id))
        except Exception as error:  # noqa: BLE001 - 渲染失败不该把窗口带走
            messagebox.showerror(self.app_title, f"导出失败：{error}", parent=self)
            return
        with open(path, "wb") as handle:
            handle.write(payload)
        self._status(f"已导出到 {path}")


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def mindmap_db_suggest(due_total) -> int:
    """今天建议新画几张（由待盲画量反推）。"""
    return mindmap_db.suggest_new_count(due_total=due_total)
