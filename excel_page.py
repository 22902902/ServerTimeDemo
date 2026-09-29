# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 界面层
================================================================================
``ExcelLearningPage(ttk.Frame)``：由 ``main`` 建一次，之后靠 pack / pack_forget 切换，
与 ``TodoPage`` / ``ProcessPage`` 同一套约定。数据全部来自注入的 ``ExcelDB``。
**本模块不 import main** —— 图片路径解析这类依赖 ``BASE_DIR`` 的能力，
通过 ``ExcelImageTools`` 适配器注入（与流程中心的做法一致，避免循环依赖）。

八个视图
--------------------------------------------------------------------------------
今日复习 / 函数宝典 / 自测出题 / 错题本 / 学习路径 / 实战配方 / 学习笔记 / 打卡统计
「自测出题」「错题本」是 P1 加的两个视图；「分类掌握雷达图」画在打卡统计页里，
「生成今日复习待办」按钮在今日复习页顶上（只在点它时建，不做后台自动生成）。

三处对设计文档的调整，写在这里免得后面看着奇怪
--------------------------------------------------------------------------------
**1. 「函数宝典」中栏用 Treeview 而不是卡片列表。**
   设计文档里画的是卡片。实际写的时候改了：中栏要一次列出 200 个函数，
   卡片在这个量级下又慢又难扫（每个卡片 4~5 个控件 = 近千个控件）。
   Treeview 一屏能看 20 多行、支持键盘上下键连续翻。
   **卡片留在「今日复习」** —— 那里的每张卡都带三个反馈按钮，是要「操作」的，
   而这里是要「扫」。形态跟着用途走，不跟着图走。

**2. 「学习路径」点阶段不换视图，而是切到「函数宝典」并加一层阶段筛选。**
   这样阶段清单直接复用了整套列表 + 详情界面（含掌握度、书页、笔记），
   不用再写一份「阶段内的函数列表」。顶部会出现「退出阶段筛选」的返回按钮。

**3. 「自测出题」不建题库表，题干按出题当时的样子快照进流水。**
   题干是从函数本身推出来的（场景 + 语法 + 示例），存一份题库等于给同一份
   数据留第二个副本。所谓「揭晓字段」（语法 / 示例 / 易错点）只是**答题前
   不渲染**，不是不存在 —— 所以一道题不需要任何额外录入就能出。
"""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from dialog_form_style import (
    apply_dialog_form_style,
    create_form_entry,
    create_form_label,
)
from excel_db import (
    DIFFICULTY_LABELS,
    FEEDBACK_CHOICES,
    FEEDBACK_FORGOT,
    FEEDBACK_KNOWN,
    FEEDBACK_VAGUE,
    IMPORTANCE_LABELS,
    MASTERY_CHOICES,
    MASTERY_COLORS,
    MASTERY_GOOD,
    MASTERY_NEW,
    MASTERY_WEAK,
    QUIZ_BATCH,
    QUIZ_CHOICE,
    QUIZ_FORMULA,
    QUIZ_MODE_CHOICES,
    QUIZ_MODE_MIXED,
    QUIZ_TYPE_LABELS,
    QUIZ_WRONG_LIMIT,
    build_choice_question,
    build_formula_question,
    difficulty_label,
    group_quiz_round,
    importance_label,
    mastery_label,
    parse_date,
    parse_import_file,
    split_codes,
    strip_emphasis,
    today_str,
)
from excel_export import markdown_to_html, print_document
from excel_formula_hl import tokenize as tokenize_formula
from excel_seed import CATEGORIES
from excel_todo_bridge import review_todo_payload
from page_components import (
    GUTTER,
    add_toolbar_buttons,
    create_menu_button,
    create_page_toolbar,
    create_status_bar,
    create_two_pane_layout,
)
from ui_components import ScrollArea, create_ttk_section_header
from ui_theme import MAIN_PALETTE, TYPOGRAPHY

try:
    import markdown_view
    HAS_MARKDOWN = True
except ImportError:            # 预览降级为纯文本，不影响使用
    HAS_MARKDOWN = False

try:
    import image_clipboard
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False


# ======================================================================
# 视图
# ======================================================================
VIEW_DUE = "due"
VIEW_LIBRARY = "library"
VIEW_QUIZ = "quiz"
VIEW_WRONG = "wrong"
VIEW_PATH = "path"
VIEW_RECIPE = "recipe"
VIEW_NOTE = "note"
VIEW_STATS = "stats"
VIEW_CHOICES = (
    (VIEW_DUE, "今日复习"),
    (VIEW_LIBRARY, "函数宝典"),
    (VIEW_QUIZ, "自测出题"),
    (VIEW_WRONG, "错题本"),
    (VIEW_PATH, "学习路径"),
    (VIEW_RECIPE, "实战配方"),
    (VIEW_NOTE, "学习笔记"),
    (VIEW_STATS, "打卡统计"),
)

# 左栏宽度 = 树列宽合计 + Treeview 自带滚动条约 17px（照流程中心的口径）
LEFT_WIDTH = 248
NAV_TREE_WIDTH = 160
NAV_COUNT_WIDTH = 44

# 函数宝典中栏宽度（列表）
LIST_WIDTH = 320

# 今日复习一次推几张：少一点才点得完，点得完才会坚持
REVIEW_BATCH = 12

# 笔记截图落在 account_images 下的子目录（复用账号中心那套存储协议）
NOTE_IMAGE_SUBDIR = "excel_notes"

BAR_WIDTH = 168
BAR_HEIGHT = 8

# 雷达图：**固定尺寸 Canvas**，不参与自适应 —— 与条形图同一个理由，
# 避开「首帧控件宽度报 1、按它算坐标必然错」那个老坑。
RADAR_WIDTH = 400
RADAR_HEIGHT = 320
RADAR_RADIUS = 96
# 轴标签落在半径 + 这个偏移处：留够「查找与引用」这种 5 个汉字的位置
RADAR_LABEL_GAP = 26
RADAR_RINGS = 4

# 复习热力图：与雷达图同一个道理，**固定尺寸**，不参与自适应
HEATMAP_WEEKS = 18
HEATMAP_CELL = 11
HEATMAP_GAP = 3
HEATMAP_LEFT = 4        # 左边留给月份标签
HEATMAP_TOP = 16
# 由浅到深五档：0 档是「没练」的底色，必须和最浅那档拉得开
HEATMAP_COLORS = ("#ececec", "#cfe3d4", "#a8cbb2", "#7bb38d", "#4f9166")

MASTERY_FILTER_CHOICES = (
    ("全部掌握度", None),
    ("未学", MASTERY_NEW),
    ("生疏", MASTERY_WEAK),
    ("一般", 2),
    ("熟练", MASTERY_GOOD),
)


class ExcelImageTools:
    """图片能力的注入包。

    ``excel_page`` 不能 import main（会形成循环依赖），
    但笔记截图又必须复用账号中心那套「相对路径 + 统一目录」的存储协议。
    所以把用得到的几个函数打成一个小对象传进来 —— 与 ``ProcessImageTools`` 同构。
    """

    def __init__(self, *, base_dir, resolve_paths, storage_value, make_dir,
                 parse_items, serialize_items):
        self.base_dir = base_dir
        self.resolve_paths = resolve_paths
        self.storage_value = storage_value
        self.make_dir = make_dir
        self.parse_items = parse_items
        self.serialize_items = serialize_items


# ======================================================================
# 小组件
# ======================================================================
# 渲染小工具
# ======================================================================
def _plain(text) -> str:
    """把种子正文里的 ``**强调**`` 去掉标记再上屏。

    真正的剥标记在数据层（``excel_db.strip_emphasis``）—— 出题也会把
    同一段正文抄进题干，两处各写一套正则迟早有一边忘掉；这里只留一个
    好读的别名。

    为什么不做成真加粗：Tk 的 Label 不支持富文本，只是「一段折行文字」，
    要真加粗就得换成只读 Text 并自己算高度 —— 而这段文字是**按宽度折行**的，
    高度依赖当时的控件宽度，会掉进「首帧控件宽度报 1、按它算必然错」那个
    老坑（本项目为此返工过多次）。权衡：去掉标记让正文干净，比为了一处加粗
    引入一个会抖的控件划算。种子里留着 ``**`` 是因为导出 Markdown 时要它。

    ``_field`` / 卡片正文都过这一道，所以只有**置中**的强调会被去掉；
    落到小标题（例如「易错点（最值钱的一栏）」）上的加粗本来就靠颜色区分。
    """
    return strip_emphasis(text)


def _badge(parent, text: str, *, fg: str, bg: str = "", palette=MAIN_PALETTE,
           font=None):
    """小徽标：色块 + 文字。用于掌握度、难度、分类。"""
    return tk.Label(
        parent, text=f" {text} ", fg=fg, bg=bg or palette.surface_alt,
        font=font or TYPOGRAPHY.badge, padx=3, pady=1,
    )


# --------------------------------------------------------------------------
# 公式着色（颜色在界面侧；分词器只管分类）
# --------------------------------------------------------------------------
FORMULA_COLORS = {
    "func": "#1a4f8a",      # 函数名：蓝
    "string": "#2e6b46",    # 写死的字面量：绿
    "ref": "#8a6a2f",       # 单元格 / 区域 / 表名：棕
    "number": "#7a3f9d",    # 数字：紫
    "operator": "#6b6b6b",  # 运算符与分隔符：灰
    "paren": "#6b6b6b",     # 括号：灰
}


def _paint_formula(body, text) -> None:
    """给只读 Text 里的公式上色。**只加 tag，一个字符都不改。**

    ``tokenize`` 保证拼接后等于原文，所以这里可以放心按字符偏移算区间；
    复制出去的仍然是原始字符串 —— 高亮要是改了文本，用户照着敲就会报错。
    """
    offset = 0
    for token in tokenize_formula(text):
        color = FORMULA_COLORS.get(token.kind)
        if color:
            tag = "hl_" + token.kind
            body.tag_configure(tag, foreground=color)
            body.tag_add(tag, f"1.0+{offset}c",
                         f"1.0+{offset + len(token.text)}c")
        offset += len(token.text)


def _mono_block(parent, text: str, *, palette=MAIN_PALETTE, on_copy=None,
                height_lines=None, copy_text=None, highlight=None):
    """等宽代码块 + 一键复制。只读 Text 仍可选中，所以「看」和「拷」都满足。"""
    holder = tk.Frame(parent, bg=palette.surface_alt, highlightthickness=1,
                      highlightbackground=palette.border_soft)
    head = tk.Frame(holder, bg=palette.surface_alt)
    head.pack(fill="x", padx=8, pady=(4, 0))
    if on_copy:
        ttk.Button(head, text="复制", width=6,
                   command=lambda: on_copy(copy_text if copy_text is not None else text)
                   ).pack(side="right")
    lines = text.count("\n") + 1
    body = tk.Text(
        holder, height=max(1, min(height_lines or lines, 14)), wrap="char",
        font=TYPOGRAPHY.mono, bg=palette.surface_alt, fg=palette.text_primary,
        relief="flat", highlightthickness=0, bd=0, padx=3, pady=3, cursor="xterm",
    )
    body.insert("1.0", text)
    if highlight is not None:
        _paint_formula(body, text)
    body.configure(state="disabled")
    if on_copy:
        body.bind("<Control-c>", lambda e: on_copy(
            copy_text if copy_text is not None else text) or "break")
    body.pack(fill="x", padx=8, pady=(2, 6))
    return holder


def _field(parent, title: str, text: str, *, palette=MAIN_PALETTE,
           fg=None, font=None, mono=False, highlight=None):
    """「小标题 + 正文」的成对展示块。空文本直接不渲染（返回 None）。"""
    text = _plain(text).strip()
    if not text:
        return None
    block = tk.Frame(parent, bg=palette.surface)
    tk.Label(block, text=title, bg=palette.surface, fg=palette.text_muted,
             font=TYPOGRAPHY.caption, anchor="w").pack(anchor="w")
    if mono and highlight is not None:
        body = tk.Text(block, height=1, wrap="char", font=TYPOGRAPHY.mono,
                       bg=palette.surface, fg=fg or palette.text_primary,
                       relief="flat", highlightthickness=0, bd=0,
                       padx=0, pady=0)
        body.insert("1.0", text)
        _paint_formula(body, text)
        body.configure(state="disabled")
        body.pack(anchor="w", fill="x", pady=(2, 0))
        return block
    tk.Label(block, text=text, bg=palette.surface,
             fg=fg or palette.text_primary, font=font or TYPOGRAPHY.body,
             justify="left", anchor="w", wraplength=760).pack(anchor="w", pady=(2, 0))
    return block


def _bar_row(parent, label: str, value_text: str, ratio: float, *, color: str,
             palette=MAIN_PALETTE, label_width=11, bar_width=BAR_WIDTH):
    """一行条形统计。

    条形用**固定宽度的 Canvas** 画，不参与自适应 —— 这样就不会碰到
    「首帧控件还没映射、宽度报 1，按它算比例必然错」那个老坑（本项目踩过多次）。
    """
    row = tk.Frame(parent, bg=palette.surface)
    tk.Label(row, text=label, width=label_width, anchor="w", bg=palette.surface,
             fg=palette.text_primary, font=TYPOGRAPHY.caption).pack(side="left")
    canvas = tk.Canvas(row, width=bar_width, height=BAR_HEIGHT,
                       bg=palette.border_soft, highlightthickness=0, bd=0)
    filled = max(0, min(bar_width, int(round(bar_width * float(ratio or 0)))))
    if filled > 0:
        canvas.create_rectangle(0, 0, filled, BAR_HEIGHT, fill=color, outline="")
    canvas.pack(side="left", padx=(0, 8))
    tk.Label(row, text=value_text, bg=palette.surface, fg=palette.text_muted,
             font=TYPOGRAPHY.caption).pack(side="left")
    return row


def _mastery_badge(parent, mastery: int, *, palette=MAIN_PALETTE):
    return _badge(parent, mastery_label(mastery),
                  fg="#ffffff" if mastery else palette.text_muted,
                  bg=MASTERY_COLORS.get(int(mastery or 0), palette.surface_alt),
                  palette=palette)


def _empty_hint(parent, text: str, *, palette=MAIN_PALETTE):
    """空状态：灰色两行，中间留白，避免「一片空白像是坏了」。"""
    holder = tk.Frame(parent, bg=palette.surface)
    tk.Label(holder, text="（这里还是空的）", bg=palette.surface,
             fg=palette.text_secondary, font=TYPOGRAPHY.body).pack(anchor="w")
    tk.Label(holder, text=text, bg=palette.surface, fg=palette.text_muted,
             font=TYPOGRAPHY.caption, justify="left", wraplength=640,
             ).pack(anchor="w", pady=(4, 0))
    return holder


# ======================================================================
# 笔记编辑对话框
# ======================================================================
class ExcelNoteDialog(tk.Toplevel):
    """新增 / 编辑一条 Excel 学习笔记。``result`` 为 None 表示取消。"""

    def __init__(self, master, *, app_title, note=None, function_name="",
                 image_preview_cls=None, images: ExcelImageTools | None = None):
        super().__init__(master)
        self.title("编辑学习笔记" if note else "新增学习笔记")
        self.app_title = app_title
        self.note = note or {}
        self.images = images
        self.image_preview_cls = image_preview_cls
        self.result: dict | None = None

        self.title_var = tk.StringVar(value=str(self.note.get("title", "")))
        self.page_var = tk.StringVar(value=str(self.note.get("book_page", "")))
        self.tags_var = tk.StringVar(value=str(self.note.get("tags", "")))
        self.link_var = tk.StringVar(value=function_name or "（不关联函数）")
        self.hint_var = tk.StringVar(value="")

        body = ttk.Frame(self, padding=(16, 14))
        body.pack(fill="both", expand=True)

        form = ttk.Frame(body)
        form.pack(fill="x")
        self._row(form, "标题", self.title_var)
        self._row(form, "书页码", self.page_var)
        self._row(form, "标签", self.tags_var)
        ttk.Label(form, text="关联函数", width=8, anchor="w").grid(
            row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Label(form, textvariable=self.link_var,
                  foreground=MAIN_PALETTE.text_muted).grid(
            row=3, column=1, sticky="w", pady=(6, 0))

        ttk.Label(body, text="正文（支持 Markdown：# 标题、- 列表、`代码`）",
                  foreground=MAIN_PALETTE.text_muted).pack(anchor="w", pady=(12, 4))
        self.content_text = tk.Text(body, height=12, wrap="word", undo=True,
                                    bg=MAIN_PALETTE.surface_alt,
                                    fg=MAIN_PALETTE.text_primary,
                                    relief="flat", highlightthickness=1,
                                    highlightbackground=MAIN_PALETTE.border_soft)
        self.content_text.pack(fill="both", expand=True)
        self.content_text.insert("1.0", str(self.note.get("content", "")))

        self.preview_holder = ttk.Frame(body)
        self.preview_holder.pack(fill="x", pady=(10, 0))
        if self.image_preview_cls is not None and self.images is not None:
            self.image_preview = self.image_preview_cls(
                self.preview_holder,
                str(self.note.get("images", "")),
                preview_size=(200, 128),
                empty_text="未贴截图（在正文里按 Ctrl+V 可直接贴图）",
                image_subdir=NOTE_IMAGE_SUBDIR,
            )
            self.image_preview.build(self.preview_holder).pack(fill="x")
        else:
            self.image_preview = None

        tk.Label(body, textvariable=self.hint_var, fg="#8a6a2f",
                 wraplength=520, justify="left").pack(anchor="w", pady=(8, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="保存", style="Primary.TButton",
                   command=self._save).pack(side="right", padx=4)
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="right")

        # 贴图：剪贴板里是图片就落盘并挂到预览上，否则放行默认粘贴
        self.content_text.bind("<Control-v>", self._on_paste)
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.content_text.focus_set()

    def _row(self, parent, label, variable, row=None):
        index = len(parent.grid_slaves()) // 2 if row is None else row
        ttk.Label(parent, text=label, width=8, anchor="w").grid(
            row=index, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(parent, textvariable=variable, width=46).grid(
            row=index, column=1, sticky="ew", pady=(6, 0))
        parent.columnconfigure(1, weight=1)

    def _on_paste(self, _event=None):
        if not (HAS_CLIPBOARD and self.images is not None and self.image_preview is not None):
            return None
        try:
            target_dir = self.images.make_dir(NOTE_IMAGE_SUBDIR)
            saved = image_clipboard.save_clipboard_image(self.content_text, target_dir)
        except Exception:
            self.hint_var.set("粘贴截图失败：读剪贴板出错，文字粘贴不受影响。")
            return None
        if saved is None:
            return None                      # 剪贴板里不是图 → 走默认文本粘贴
        stored = self.images.storage_value(saved)
        current = self.image_preview.get_value()
        items = self.images.parse_items(current) if current else []
        items.append({"path": stored, "label": ""})
        self.image_preview.set_value(self.images.serialize_items(items))
        self.hint_var.set(f"已贴上一张截图：{saved.name}")
        return "break"                       # 拦下这次 Ctrl+V，避免又插一段文字

    def _save(self):
        title = self.title_var.get().strip()
        content = self.content_text.get("1.0", "end").strip()
        if not title and not content:
            self.hint_var.set("标题和正文至少写一项。")
            return
        if not title:
            title = content.splitlines()[0][:24]
        self.result = {
            "title": title,
            "book_page": self.page_var.get().strip(),
            "tags": self.tags_var.get().strip(),
            "content": content,
            "images": self.image_preview.get_value() if self.image_preview else "",
            "function_id": self.note.get("function_id"),
        }
        self.destroy()


# ======================================================================
# 自建函数对话框
# ======================================================================
FUNCTION_DIALOG_FIELDS = (
    ("code", "函数名", 22),
    ("name_cn", "中文名", 22),
    ("syntax", "语法", 60),
    ("args_desc", "参数说明", 60),
    ("returns", "返回值", 60),
    ("description", "一句话说明", 60),
    ("use_cases", "适用场景", 60),
    ("pitfalls", "易错点", 60),
    ("related", "相关函数（| 分隔）", 60),
    ("example_formula", "示例公式", 60),
    ("example_result", "示例结果", 60),
    ("min_version", "最低版本", 22),
    ("tags", "标签（| 分隔）", 22),
)


class ExcelFunctionDialog(simpledialog.Dialog):
    """自建一个书上的冷门函数（``is_builtin=0``，因此可以删）。

    设计文档里写明了「冷门函数留给自建入口，你照书补」—— 速查宝典里有些函数
    内置库里没有，靠这个入口按书补录；补录进来的走 ``add_custom_function``，
    和内置的区分开（内置的不允许删，只能改书页码和掌握度）。
    """

    def __init__(self, parent, title: str, *, app_title: str, initial: dict | None = None,
                 categories=None):
        self.initial = dict(initial or {})
        self.app_title = app_title
        self.categories = list(categories or [])
        self.result: dict | None = None
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="ExcelDialog")
        self.entries: dict[str, tk.Widget] = {}
        row_index = 0

        create_form_label(master, "分类", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="w", padx=6, pady=4)
        self.category_var = tk.StringVar(
            value=self.initial.get("category") or (self.categories[0]
                                                   if self.categories else "逻辑"))
        category_box = ttk.Combobox(master, textvariable=self.category_var,
                                    values=self.categories, state="readonly", width=20)
        category_box.grid(row=row_index, column=1, sticky="w", padx=6, pady=4)
        row_index += 1

        create_form_label(master, "难度", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="w", padx=6, pady=4)
        self.difficulty_var = tk.StringVar(
            value=difficulty_label(self.initial.get("difficulty") or 2))
        ttk.Combobox(master, textvariable=self.difficulty_var,
                     values=[label for _v, label in sorted(DIFFICULTY_LABELS.items())],
                     state="readonly", width=20).grid(
            row=row_index, column=1, sticky="w", padx=6, pady=4)
        row_index += 1

        create_form_label(master, "重要度", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="w", padx=6, pady=4)
        self.importance_var = tk.StringVar(
            value=importance_label(self.initial.get("importance") or 2))
        ttk.Combobox(master, textvariable=self.importance_var,
                     values=[label for _v, label in sorted(IMPORTANCE_LABELS.items())],
                     state="readonly", width=20).grid(
            row=row_index, column=1, sticky="w", padx=6, pady=4)
        row_index += 1

        for field, label, width in FUNCTION_DIALOG_FIELDS:
            create_form_label(master, label, palette=MAIN_PALETTE).grid(
                row=row_index, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=width)
            entry.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, str(self.initial.get(field, "") or ""))
            self.entries[field] = entry
            row_index += 1

        master.columnconfigure(1, weight=1)
        return self.entries["code"]

    def validate(self):
        if not self.entries["code"].get().strip():
            messagebox.showwarning(self.app_title, "函数名不能为空，比如 MYLOOKUP。",
                                   parent=self)
            return False
        return True

    def apply(self):
        payload = {field: widget.get().strip()
                   for field, widget in self.entries.items()}
        payload["category"] = self.category_var.get().strip()
        payload["difficulty"] = self._reverse(DIFFICULTY_LABELS,
                                             self.difficulty_var.get(), 2)
        payload["importance"] = self._reverse(IMPORTANCE_LABELS,
                                             self.importance_var.get(), 2)
        self.result = payload

    @staticmethod
    def _reverse(mapping, label, fallback):
        for value, text in mapping.items():
            if text == label:
                return value
        return fallback


# ======================================================================
# 页面
# ======================================================================
class ExcelLearningPage(ttk.Frame):
    """Excel 学习中心页面。"""

    def __init__(self, master, db, *, app_title: str, image_preview_cls=None,
                 images: ExcelImageTools | None = None, on_status=None,
                 todo_hook=None, notes=None, palette=MAIN_PALETTE,
                 typography=TYPOGRAPHY):
        super().__init__(master)
        self.db = db
        self.app_title = app_title
        self.image_preview_cls = image_preview_cls
        self.images = images
        self.on_status = on_status
        # 「生成今日复习待办」的落库动作，由 main 注入 ExcelTodoBridge 的方法。
        # 本模块不 import todo_db / main —— 与图片能力同一个手法（避免循环依赖）。
        self.todo_hook = todo_hook
        # 「生成学习笔记」的落库动作，由 main 注入 ExcelNoteBridge 对象。
        # 与 todo_hook / images 同一个手法：本模块既不认识 study_notes_db
        # 也不认识 main，所以不会形成循环依赖。
        self.notes = notes
        self.palette = palette
        self.typography = typography

        # ── 视图状态 ──
        self.view_key = VIEW_DUE
        self.selected_function_id: int | None = None
        self.selected_recipe_id: int | None = None
        self.selected_note_id: int | None = None
        self.stage_codes: list[str] | None = None      # 学习路径的阶段筛选
        self.stage_title = ""
        self._thumb_refs: list = []                    # 挡住缩略图被 GC

        # ── 自测状态 ──
        self.quiz_questions: list[dict] = []           # 本轮题目；点「开始」才填
        self.quiz_index = 0
        self.quiz_correct = 0
        self.quiz_wrong = 0
        self.quiz_answered = False
        self.quiz_picked = ""                          # 选择题刚点的那个选项
        self.quiz_formula_state = ""                   # 写公式题的自评结果
        self.quiz_retry_id: int | None = None          # 从错题本进来时记着它
        # **本轮**（本次运行）的自测作答，顺序 = 作答先后。
        # 「生成学习笔记」优先用它；应用重启后它是空的，那时从库里捞最近一轮
        # （见 _note_source_items）。
        self.quiz_session: list[dict] = []
        # 本会话里建过的复习待办标题。只在「生成今日复习待办」成功之后才有值，
        # 笔记的生成区拿它写「关联待办」那一行 —— 没建过就干脆不提。
        self.review_todo_title = ""
        self.quiz_formula_var = tk.StringVar()
        self.quiz_mode_var = tk.StringVar(value=QUIZ_MODE_CHOICES[0][1])

        self.search_var = tk.StringVar()
        self.category_var = tk.StringVar(value="全部分类")
        self.mastery_var = tk.StringVar(value=MASTERY_FILTER_CHOICES[0][0])
        self.title_var = tk.StringVar(value="今日复习")
        self.meta_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Excel 学习中心已就绪。")
        self.checkin_note_var = tk.StringVar()
        self.checkin_minutes_var = tk.StringVar(value="20")

        self._build()
        self.refresh()

    # ==================================================================
    # 构建
    # ==================================================================
    def _build(self):
        self._build_toolbar()
        _, left, right = create_two_pane_layout(
            self,
            left_width=LEFT_WIDTH,
            right_pad=(16, 0),
            padding=(GUTTER, 0, GUTTER, 16),
        )
        self._build_nav(left)
        self._build_right(right)
        create_status_bar(self, self.status_var, padding=(GUTTER, 0, GUTTER, 16))

    def _build_toolbar(self):
        toolbar = create_page_toolbar(self)
        add_toolbar_buttons(
            toolbar,
            [
                ("开始今日复习", self.start_today_review, "Primary.TButton"),
                ("随机抽一个", self.pick_random_function),
                ("新增笔记", self.add_note),
            ],
        )
        create_menu_button(
            toolbar,
            "更多",
            [
                ("导出学习进度（Markdown）", self.export_progress),
                ("生成学习笔记（整理到「学习笔记」）", self.generate_study_notes),
                "---",
                ("批量导入函数（CSV / Excel）", self.import_functions_dialog),
                ("下载导入模板", self.save_import_template),
                ("导出函数库为 CSV", self.export_functions_csv),
                ("导出函数库为 Markdown（可打印）",
                 self.export_functions_markdown),
                "---",
                ("手动打卡", self.checkin_today),
                ("重建函数库种子（不清进度）", self.reseed_functions),
                "---",
                ("打开截图目录", self.open_note_image_folder),
                ("打开导出目录", self.open_export_folder),
            ],
        )

    # -- 左栏：视图 + 分类 ------------------------------------------------
    def _build_nav(self, parent):
        create_ttk_section_header(parent, "学习中心").pack(anchor="w", pady=(0, 6))
        self.nav_tree = ttk.Treeview(
            parent, columns=("count",), show="tree headings", height=26,
            selectmode="browse",
        )
        self.nav_tree.heading("#0", text="视图 / 分类", anchor="w")
        self.nav_tree.heading("count", text="数", anchor="e")
        self.nav_tree.column("#0", width=NAV_TREE_WIDTH, minwidth=120, stretch=True,
                             anchor="w")
        self.nav_tree.column("count", width=NAV_COUNT_WIDTH, minwidth=36,
                             stretch=False, anchor="e")
        # 滚动条先于 Treeview pack，否则会被表格请求宽度挤成 0 宽
        scroll = ttk.Scrollbar(parent, orient="vertical", command=self.nav_tree.yview)
        self.nav_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.nav_tree.pack(side="left", fill="both", expand=True)
        self.nav_tree.bind("<<TreeviewSelect>>", self._on_nav_select)

    def _build_right(self, parent):
        head = ttk.Frame(parent)
        head.pack(fill="x")
        ttk.Label(head, textvariable=self.title_var,
                  style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(head, textvariable=self.meta_var,
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))
        self.head_actions = ttk.Frame(head)
        self.head_actions.pack(side="right")

        # 搜索 / 筛选行：只在需要它的视图里出现。
        #
        # 三组控件各自包在一个组帧里 —— 不是为了好看，是为了能**整体收起**：
        # 自测视图里「搜索」无从谈起（题干是现生成的），留着它就变成
        # 「控件在那儿却不生效」，比没有更让人困惑。
        # 收起 / 放回的**顺序固定**（搜索 → 分类 → 掌握度 → 提示），因为 pack 是
        # 「追加」语义：顺序不固定的话，每切一次视图控件就会重新排一次队。
        self.filter_row = ttk.Frame(parent)
        self.search_group = ttk.Frame(self.filter_row)
        ttk.Label(self.search_group, text="搜索").pack(side="left")
        self.search_entry = ttk.Entry(self.search_group, textvariable=self.search_var,
                                      width=22)
        self.search_entry.pack(side="left", padx=(6, 4))
        self.search_entry.bind("<Return>", lambda e: self.render_current_view())
        ttk.Button(self.search_group, text="查", width=3,
                   command=self.render_current_view).pack(side="left")

        self.category_group = ttk.Frame(self.filter_row)
        self.category_box = ttk.Combobox(
            self.category_group, textvariable=self.category_var, state="readonly",
            width=14, values=["全部分类"] + [item["name"] for item in CATEGORIES],
        )
        self.category_box.pack(side="left")
        self.category_box.bind("<<ComboboxSelected>>",
                               lambda e: self.render_current_view())

        self.mastery_group = ttk.Frame(self.filter_row)
        self.mastery_box = ttk.Combobox(
            self.mastery_group, textvariable=self.mastery_var, state="readonly",
            width=12, values=[label for label, _ in MASTERY_FILTER_CHOICES],
        )
        self.mastery_box.pack(side="left")
        self.mastery_box.bind("<<ComboboxSelected>>",
                              lambda e: self.render_current_view())

        # 一行提示：告诉用户当前视图的筛选是「按什么筛」，省得靠猜
        self.filter_hint_var = tk.StringVar()
        self.filter_hint = tk.Label(self.filter_row, textvariable=self.filter_hint_var,
                                    bg=self.palette.bg, fg=self.palette.text_muted,
                                    font=TYPOGRAPHY.caption)

        self.body_host = ttk.Frame(parent)
        self.body_host.pack(fill="both", expand=True, pady=(10, 0))

        # 八个视图帧建一次，切换时只 pack / pack_forget（保住滚动位置与选中状态）
        self.view_frames: dict[str, ttk.Frame] = {}
        for key, _label in VIEW_CHOICES:
            self.view_frames[key] = ttk.Frame(self.body_host)
        self._build_due_view()
        self._build_library_view()
        self._build_quiz_view()
        self._build_wrong_view()
        self._build_path_view()
        self._build_recipe_view()
        self._build_note_view()
        self._build_stats_view()

    # -- 视图 1：今日复习 ------------------------------------------------
    def _build_due_view(self):
        frame = self.view_frames[VIEW_DUE]
        self.due_area = ScrollArea(frame, bg=self.palette.bg, inner_bg=self.palette.bg,
                                   autohide_scrollbar=True)
        self.due_area.pack(fill="both", expand=True)

    # -- 视图 2：函数宝典 ------------------------------------------------
    def _build_library_view(self):
        frame = self.view_frames[VIEW_LIBRARY]
        _, left, right = create_two_pane_layout(
            frame, left_width=LIST_WIDTH, right_pad=(14, 0), padding=(0, 0, 0, 0)
        )
        self.list_tree = ttk.Treeview(
            left, columns=("code", "name_cn", "mastery"), show="tree headings",
            height=24, selectmode="browse",
        )
        self.list_tree.heading("#0", text="", anchor="w")
        self.list_tree.column("#0", width=0, minwidth=0, stretch=False)
        for column, (title, width, anchor) in {
            "code": ("函数", 118, "w"),
            "name_cn": ("中文名", 88, "w"),
            "mastery": ("掌握", 52, "center"),
        }.items():
            self.list_tree.heading(column, text=title, anchor=anchor)
            self.list_tree.column(column, width=width, minwidth=40, stretch=False,
                                  anchor=anchor)
        list_scroll = ttk.Scrollbar(left, orient="vertical",
                                    command=self.list_tree.yview)
        self.list_tree.configure(yscrollcommand=list_scroll.set)
        list_scroll.pack(side="right", fill="y")
        self.list_tree.pack(side="left", fill="both", expand=True)
        self.list_tree.bind("<<TreeviewSelect>>", self._on_list_select)

        self.detail_area = ScrollArea(right, bg=self.palette.bg,
                                      inner_bg=self.palette.bg,
                                      autohide_scrollbar=True)
        self.detail_area.pack(fill="both", expand=True)

    # -- 视图 3：自测出题 ------------------------------------------------
    def _build_quiz_view(self):
        frame = self.view_frames[VIEW_QUIZ]
        self.quiz_area = ScrollArea(frame, bg=self.palette.bg,
                                    inner_bg=self.palette.bg,
                                    autohide_scrollbar=True)
        self.quiz_area.pack(fill="both", expand=True)

    # -- 视图 4：错题本 --------------------------------------------------
    def _build_wrong_view(self):
        frame = self.view_frames[VIEW_WRONG]
        self.wrong_area = ScrollArea(frame, bg=self.palette.bg,
                                     inner_bg=self.palette.bg,
                                     autohide_scrollbar=True)
        self.wrong_area.pack(fill="both", expand=True)

    # -- 视图 5：学习路径 ------------------------------------------------
    def _build_path_view(self):
        frame = self.view_frames[VIEW_PATH]
        self.path_area = ScrollArea(frame, bg=self.palette.bg, inner_bg=self.palette.bg,
                                    autohide_scrollbar=True)
        self.path_area.pack(fill="both", expand=True)

    # -- 视图 6：实战配方 ------------------------------------------------
    def _build_recipe_view(self):
        frame = self.view_frames[VIEW_RECIPE]
        self.recipe_area = ScrollArea(frame, bg=self.palette.bg,
                                      inner_bg=self.palette.bg,
                                      autohide_scrollbar=True)
        self.recipe_area.pack(fill="both", expand=True)

    # -- 视图 7：学习笔记 ------------------------------------------------
    def _build_note_view(self):
        frame = self.view_frames[VIEW_NOTE]
        split = ttk.Frame(frame)
        split.pack(fill="both", expand=True)
        top = ttk.Frame(split)
        top.pack(fill="x")
        self.note_tree = ttk.Treeview(
            top, columns=("title", "book_page", "updated"), show="tree headings",
            height=9, selectmode="browse",
        )
        self.note_tree.heading("#0", text="", anchor="w")
        self.note_tree.column("#0", width=0, minwidth=0, stretch=False)
        for column, (title, width, anchor) in {
            "title": ("标题", 300, "w"),
            "book_page": ("书页", 70, "center"),
            "updated": ("更新时间", 140, "center"),
        }.items():
            self.note_tree.heading(column, text=title, anchor=anchor)
            self.note_tree.column(column, width=width, minwidth=50, stretch=False,
                                  anchor=anchor)
        note_scroll = ttk.Scrollbar(top, orient="vertical",
                                    command=self.note_tree.yview)
        self.note_tree.configure(yscrollcommand=note_scroll.set)
        note_scroll.pack(side="right", fill="y")
        self.note_tree.pack(side="left", fill="x", expand=True)
        self.note_tree.bind("<<TreeviewSelect>>", self._on_note_select)
        self.note_tree.bind("<Double-1>", lambda e: self.edit_note())

        self.note_preview_holder = ttk.Frame(split)
        self.note_preview_holder.pack(fill="both", expand=True, pady=(10, 0))
        self.note_preview = tk.Text(
            self.note_preview_holder, wrap="word", height=14,
            bg=self.palette.surface, fg=self.palette.text_primary,
            relief="flat", highlightthickness=1,
            highlightbackground=self.palette.border_soft,
        )
        preview_scroll = ttk.Scrollbar(self.note_preview_holder, orient="vertical",
                                       command=self.note_preview.yview)
        self.note_preview.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.pack(side="right", fill="y")
        self.note_preview.pack(side="left", fill="both", expand=True)
        if HAS_MARKDOWN:
            try:
                markdown_view.setup_tags(self.note_preview)
            except Exception:
                pass

    # -- 视图 8：打卡统计 ------------------------------------------------
    def _build_stats_view(self):
        frame = self.view_frames[VIEW_STATS]
        self.stats_area = ScrollArea(frame, bg=self.palette.bg,
                                     inner_bg=self.palette.bg,
                                     autohide_scrollbar=True)
        self.stats_area.pack(fill="both", expand=True)

    # ==================================================================
    # 导航
    # ==================================================================
    def refresh(self):
        """对外入口：重新拉数据并重绘当前视图（``main`` 的 ``on_show`` 调它）。"""
        self.refresh_nav()
        self.render_current_view()

    def refresh_nav(self):
        """重建左栏（视图 8 项 + 分类 12 项）。数很重，整表重建比增量省心。

        收尾**必须**落到一个明确的选区状态 —— 见下面那段注释，这是踩过的坑。
        """
        tree = self.nav_tree
        selection = tree.selection()
        for iid in tree.get_children(""):
            tree.delete(iid)
        tree.insert("", "end", iid="g::views", text="学习视图", open=True,
                    values=("",))
        quiz = self.db.quiz_stats()          # 一次算完，两个视图共用
        counts = {
            VIEW_DUE: str(self.db.due_count()) or "0",
            VIEW_LIBRARY: str(self.db.count_functions()),
            VIEW_QUIZ: str(quiz["attempts"]),
            VIEW_WRONG: str(quiz["pending"]),
            VIEW_PATH: str(len(self.db.learning_progress())),
            VIEW_RECIPE: str(len(self.db.all_recipes())),
            VIEW_NOTE: str(self.db.note_count()),
            VIEW_STATS: str(self.db.streak()),
        }
        for key, label in VIEW_CHOICES:
            suffix = {VIEW_STATS: " 天", VIEW_WRONG: " 条"}.get(key, "")
            text = label
            if key == VIEW_STATS and counts[key] != "0":
                text = f"{label}（连续 {counts[key]} 天）"
            tree.insert("g::views", "end", iid=f"view::{key}", text=text,
                        values=(counts[key] + suffix,))
        tree.insert("", "end", iid="g::cats", text="按分类查", open=False,
                    values=("",))
        for item in self.db.category_stats():
            label = item["name"]
            if item["total"]:
                label = f"{item['name']}（{item['good']}/{item['total']} 熟练）"
            tree.insert("g::cats", "end", iid=f"cat::{item['name']}", text=label,
                        values=(str(item["total"]) or "",))

        # 坑：ttk 的 <<TreeviewSelect>> 是**延迟投递**的（要等下一次事件循环），
        # 所以围着 selection_set 设一个布尔守卫**根本拦不住** —— 事件到达时守卫
        # 早已复位，_on_nav_select 会读「那时候」的选区，反手把视图抢成别的。
        # 实测：进「学习路径」的某一阶段后会被弹回「今日复习」，就是这么来的。
        # 唯一可靠的做法是让刷新结束时的选区**就是想让用户停的那一项**。
        if self.stage_codes:
            # 阶段筛选显示的是「阶段子集」，导航里没有对应节点。
            # 必须清空选区；否则会退回上一次的旧选中项，一帧之后视图被抢走。
            # 空选区到达 _on_nav_select 会被开头那句 ``if not selection`` 挡掉。
            if tree.selection():
                tree.selection_remove(*tree.selection())
            return
        target = f"view::{self.view_key}"
        if tree.exists(target):
            tree.selection_set(target)
        elif selection and tree.exists(selection[0]):
            tree.selection_set(selection[0])
        elif tree.selection():
            tree.selection_remove(*tree.selection())

    def _on_nav_select(self, _event=None):
        selection = self.nav_tree.selection()
        if not selection:
            return
        iid = selection[0]
        if iid.startswith("view::"):
            # 主动点了某个视图，说明要离开阶段筛选
            if self.stage_codes:
                self.stage_codes = None
                self.stage_title = ""
            self.show_view(iid.split("::", 1)[1])
        elif iid.startswith("cat::"):
            self.stage_codes = None
            self.stage_title = ""
            self.category_var.set(iid.split("::", 1)[1])
            self.mastery_var.set(MASTERY_FILTER_CHOICES[0][0])
            self.show_view(VIEW_LIBRARY)

    # ==================================================================
    # 视图切换
    # ==================================================================
    def show_view(self, key: str):
        if key not in self.view_frames:
            key = VIEW_DUE
        self.view_key = key
        for frame_key, frame in self.view_frames.items():
            if frame_key == key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        self._sync_filter_row(key)
        self._sync_nav_selection(key)
        self.render_current_view()

    def _sync_nav_selection(self, key: str):
        """让左栏高亮跟着当前视图走 —— 不变量：**导航选中项恒等于 view_key**。

        为什么必须做这一步（踩过的坑）：``<<TreeviewSelect>>`` 是延迟投递的，
        ``_on_nav_select`` 在事件到达时才去读「当时」的选区。于是只要有一条
        **还没被处理**的旧事件挂在那儿，用户点工具栏（开始今日复习 / 新增笔记 /
        随机抽一个，这些都直接调 ``show_view``）切走的视图，会在一帧之后
        被那条旧事件按旧选区**抢回去**。实测：统计页滚一下再点「开始今日复习」，
        界面会弹回统计页。

        所以每次切视图都要把选区改成对应的视图节点，让任何挂起事件都只是
        「再断言一次同一个视图」。**只在选中项确实不同时才设** —— 实测同一个
        iid 重复 ``selection_set`` 仍会再投递一次事件，不判断就会互相触发成死循环。
        """
        if self.stage_codes:
            return                       # 阶段筛选没有对应节点，选区保持空
        target = f"view::{key}"
        if not self.nav_tree.exists(target):
            return
        if self.nav_tree.selection() != (target,):
            self.nav_tree.selection_set(target)

    def _sync_filter_row(self, key: str):
        """筛选行按视图适配：换候选值、收起用不上的控件。

        踩过的坑一：这条筛选行原先对几个视图是**同一套**控件，于是配方视图里
        那个分类下拉「摆了但选什么都不筛」—— 控件在那儿却不生效，
        比没有更让人困惑。笔记视图则是「掌握度」根本无从谈起。

        踩过的坑二：加了「自测出题」「错题本」之后，分类下拉在四个视图里
        指的是四件事（宝典按函数的分类筛、配方按配方主题筛、自测限定出题范围、
        错题本按错题的分类筛），候选值必须跟着视图换，不能共用一份。

        踩过的坑三：收起控件不能只 ``pack_forget`` 想要的，得**先把四组全部忘掉、
        再按固定顺序放回**。pack 是追加语义，只忘中间一组的话，剩下的会自动
        往上挤，下次放回就跑到末尾去了 —— 界面看着像「控件自己乱跑」。
        """
        self.search_group.pack_forget()
        self.category_group.pack_forget()
        self.mastery_group.pack_forget()
        self.filter_hint.pack_forget()

        if key not in (VIEW_LIBRARY, VIEW_RECIPE, VIEW_NOTE, VIEW_QUIZ, VIEW_WRONG):
            self.filter_row.pack_forget()
            return

        # -- 搜索框：笔记 / 宝典 / 配方 / 错题本都用得上，自测用不上
        if key in (VIEW_LIBRARY, VIEW_RECIPE, VIEW_NOTE, VIEW_WRONG):
            self.search_group.pack(side="left")

        # -- 分类下拉：宝典 / 配方 / 自测 / 错题本有，笔记没有
        show_category = key in (VIEW_LIBRARY, VIEW_RECIPE, VIEW_QUIZ, VIEW_WRONG)
        if show_category:
            if key == VIEW_RECIPE:
                values = ["全部分类"] + self.db.recipe_categories()
            else:
                values = ["全部分类"] + [item["name"] for item in CATEGORIES]
            self.category_box.configure(values=values)
            # 换视图后旧选中值可能不在新候选里（例如从配方的「统计」切到笔记）
            if self.category_var.get() not in values:
                self.category_var.set("全部分类")
            self.category_group.pack(side="left", padx=(10, 0))
        else:
            self.category_var.set("全部分类")

        # -- 掌握度：只有宝典有这一维
        if key == VIEW_LIBRARY:
            self.mastery_group.pack(side="left", padx=(6, 0))

        hint = {
            VIEW_LIBRARY: "按分类 / 掌握度筛，或直接搜场景词",
            VIEW_RECIPE: "按主题筛，或搜场景词（工期 / 月供 / 去重）",
            VIEW_NOTE: "搜标题 / 正文 / 标签 / 书页码",
            VIEW_QUIZ: "按分类限定出题范围（搜索框在自测里不参与筛选）",
            VIEW_WRONG: "按分类筛错题，或搜函数名 / 题干",
        }.get(key, "")
        self.filter_hint_var.set(hint)
        self.filter_hint.pack(side="left", padx=(12, 0))
        self.filter_row.pack(fill="x", pady=(10, 0), before=self.body_host)

    def render_current_view(self):
        for child in self.head_actions.winfo_children():
            child.destroy()
        renderer = {
            VIEW_DUE: self.render_due,
            VIEW_LIBRARY: self.render_library,
            VIEW_QUIZ: self.render_quiz,
            VIEW_WRONG: self.render_wrong,
            VIEW_PATH: self.render_path,
            VIEW_RECIPE: self.render_recipe,
            VIEW_NOTE: self.render_note,
            VIEW_STATS: self.render_stats,
        }.get(self.view_key, self.render_due)
        renderer()

    # ==================================================================
    # 视图 1：今日复习
    # ==================================================================
    def start_today_review(self):
        self.show_view(VIEW_DUE)

    def render_due(self):
        area = self.due_area
        area.clear()
        today = today_str()
        due_total = self.db.due_count(today=today)
        checkin = self.db.get_checkin(today) or {}
        reviewed_today = int(checkin.get("reviewed", 0) or 0)
        streak = self.db.streak(today=today)
        self.title_var.set("今日复习")
        self.meta_var.set(
            f"待复习 {due_total} 个 · 今天已复习 {reviewed_today} 个 · 连续打卡 {streak} 天"
            f"（一次推 {REVIEW_BATCH} 个）"
        )
        ttk.Button(self.head_actions, text="生成今日复习待办",
                   command=self.create_review_todo).pack(side="right")

        items = self.db.due_functions(limit=REVIEW_BATCH, today=today)
        if not items:
            holder = _empty_hint(
                area.inner,
                "今天没有到期的函数。\n"
                "去「函数宝典」把已经会的标成「生疏」或「一般」，"
                "它们会立刻进入复习队列；\n"
                "或者点上面的「随机抽一个」，随手翻一张卡片。",
                palette=self.palette,
            )
            holder.pack(anchor="w", pady=(8, 0))
            if reviewed_today:
                self._today_done_block(area.inner, reviewed_today).pack(
                    anchor="w", pady=(16, 0))
            else:
                self._checkin_block(area.inner).pack(anchor="w", pady=(16, 0))
            return

        for index, item in enumerate(items, start=1):
            self._due_card(area.inner, item, index).pack(
                fill="x", pady=(0, 10), anchor="w")

        tail = tk.Frame(area.inner, bg=self.palette.bg)
        tk.Label(tail, text=f"本批 {len(items)} 个，队列里还有 "
                            f"{max(0, due_total - len(items))} 个。",
                 bg=self.palette.bg, fg=self.palette.text_muted,
                 font=self.palette and TYPOGRAPHY.caption).pack(side="left")
        ttk.Button(tail, text="继续", command=self._next_review_batch).pack(
            side="left", padx=8)
        if not reviewed_today:
            self._checkin_block(area.inner).pack(anchor="w", pady=(16, 0))
        tail.pack(anchor="w", pady=(6, 0))

    def _due_card(self, parent, item, index):
        card = tk.Frame(parent, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        head = tk.Frame(card, bg=self.palette.surface)
        head.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(head, text=f"{index}.", bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        tk.Label(head, text=item["code"], bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.title).pack(side="left", padx=(6, 0))
        tk.Label(head, text=item.get("name_cn", ""), bg=self.palette.surface,
                 fg=self.palette.text_secondary,
                 font=TYPOGRAPHY.body).pack(side="left", padx=(8, 0))
        _badge(head, item.get("category", ""), fg=self.palette.text_muted,
               palette=self.palette).pack(side="left", padx=(8, 0))
        _mastery_badge(head, item.get("mastery", 0), palette=self.palette).pack(
            side="left", padx=(4, 0))
        last = item.get("next_review_at", "")
        if last:
            tk.Label(head, text=f"上次排到 {last}", bg=self.palette.surface,
                     fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(side="right")

        tk.Label(card, text=_plain(item.get("description", "")),
                 bg=self.palette.surface,
                 fg=self.palette.text_primary, font=TYPOGRAPHY.body,
                 justify="left", anchor="w", wraplength=700).pack(
            anchor="w", padx=12, pady=(6, 0))
        if item.get("syntax"):
            tk.Label(card, text=item["syntax"], bg=self.palette.surface,
                     fg=self.palette.text_secondary, font=TYPOGRAPHY.mono,
                     justify="left", anchor="w", wraplength=700).pack(
                anchor="w", padx=12, pady=(4, 0))
        if item.get("use_cases"):
            tk.Label(card, text="用在：" + _plain(item["use_cases"].split("；")[0]),
                     bg=self.palette.surface, fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption, justify="left", anchor="w",
                     wraplength=700).pack(anchor="w", padx=12, pady=(4, 0))

        actions = tk.Frame(card, bg=self.palette.surface)
        actions.pack(fill="x", padx=12, pady=(8, 10))
        for feedback, label, style in (
            (FEEDBACK_KNOWN, "熟练（记得）", "Primary.TButton"),
            (FEEDBACK_VAGUE, "模糊（想一下）", "Quiet.TButton"),
            (FEEDBACK_FORGOT, "忘了（重来）", "Quiet.TButton"),
        ):
            ttk.Button(actions, text=label, style=style,
                       command=lambda f=feedback, i=item: self.review_function(i, f)
                       ).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="看完整说明",
                   command=lambda i=item: self.open_function(i["code"])
                   ).pack(side="right")
        return card

    def review_function(self, item, feedback):
        """今日复习的三键反馈：改状态 + 记一次打卡。"""
        state = self.db.record_review(item["id"], feedback)
        checkin = self.db.get_checkin(today_str()) or {}
        self.db.upsert_checkin(
            reviewed=int(checkin.get("reviewed", 0) or 0) + 1,
        )
        label = dict(FEEDBACK_CHOICES).get(feedback, feedback)
        interval = state["interval_days"]
        self._set_status(
            f"{item['code']} 已记「{label}」：掌握度 {mastery_label(state['mastery'])}，"
            f"{interval} 天后再复习（{state['next_review_at']}）。"
        )
        self.refresh_nav()
        self.render_due()

    def _next_review_batch(self):
        due_total = self.db.due_count()
        if due_total <= REVIEW_BATCH:
            self._set_status("队列已经见底，去「函数宝典」多标几个吧。")
        self.render_due()

    def _today_done_block(self, parent, reviewed):
        holder = tk.Frame(parent, bg=self.palette.bg)
        tk.Label(holder, text=f"今天已经复习 {reviewed} 个，收工。",
                 bg=self.palette.bg, fg=self.palette.success,
                 font=TYPOGRAPHY.body).pack(anchor="w")
        ttk.Button(holder, text="写两句今天的心得",
                   command=self.checkin_today).pack(anchor="w", pady=(6, 0))
        return holder

    def _checkin_block(self, parent):
        holder = tk.Frame(parent, bg=self.palette.bg)
        tk.Label(holder, text="收工打卡", bg=self.palette.bg,
                 fg=self.palette.text_primary, font=TYPOGRAPHY.section).pack(anchor="w")
        row = tk.Frame(holder, bg=self.palette.bg)
        row.pack(anchor="w", pady=(6, 0))
        tk.Label(row, text="今天学了", bg=self.palette.bg,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        ttk.Entry(row, textvariable=self.checkin_minutes_var, width=5).pack(
            side="left", padx=4)
        tk.Label(row, text="分钟，一句话心得", bg=self.palette.bg,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        ttk.Entry(row, textvariable=self.checkin_note_var, width=42).pack(
            side="left", padx=4)
        ttk.Button(row, text="打卡", command=self.checkin_today).pack(side="left", padx=4)
        return holder

    def checkin_today(self):
        try:
            minutes = max(0, int(float(self.checkin_minutes_var.get() or 0)))
        except ValueError:
            minutes = 0
        self.db.upsert_checkin(minutes=minutes, note=self.checkin_note_var.get().strip())
        self.checkin_note_var.set("")
        self._set_status(f"已打卡：今天学习 {minutes} 分钟，"
                         f"连续 {self.db.streak()} 天。")
        self.refresh_nav()
        self.render_current_view()

    def create_review_todo(self):
        """把「今天要复习 N 个」丢进待办列表。

        **只在点这个按钮时建**，不做后台自动生成 —— 学习工具不该变成催命符
        （设计文档第七节也是这么定的）。写库的动作全在注入进来的 ``todo_hook``
        （``ExcelTodoBridge``）里，所以本模块既不认识 ``todo_db`` 也不认识 ``main``。
        """
        if self.todo_hook is None:
            self._set_status("这一版没注入 todo_hook，待办联动还没接上。")
            return
        payload = review_todo_payload(
            due_count=self.db.due_count(),
            today=today_str(),
            extra_wrong=self.db.quiz_stats()["pending"],
            note_hint=self._note_pointer_text())
        result = self.todo_hook(payload) or {}
        self._set_status(result.get("message", "已处理。"))

    # ==================================================================
    # 自测 → 学习笔记模板
    # ==================================================================
    # 不是视图，是一个动作：把「本轮自测碰过的函数」整理成笔记模块里的一套
    # 模板（落点见 excel_note_bridge，是一个锁定分类）。
    #
    # 为什么做成按钮而不是「做完自动生成」：与待办联动同一个原则 —— 学习工具
    # 不该在用户没同意的时候往别的模块里塞东西。按钮就摆在自测结算卡上，
    # 答完一轮顺手一点；不点也不影响任何既有功能。

    def _note_source_items(self):
        """这一轮自测碰过的函数：答错的排前面，每个函数只留一条。

        两条来源、一个口径：

          1. **本轮**（``self.quiz_session``）：应用没重启时最准，「我刚做的
             那十道题」就是它；
          2. **最近一轮**（``recent_quiz_answers`` + ``group_quiz_round``）：
             重启之后内存没了，但作答流水还在库里。隔 45 分钟以上算换了一轮，
             所以捞回来的是「上一次那一轮」，不是今天所有作答。

        两条都过一遍 ``group_quiz_round``，去重与排序口径完全一致 ——
        来源不同不该导致整理出来的东西不一样。
        """
        if self.quiz_session:
            # 内存里的顺序是「先做的在前」，而 group_quiz_round 要的是倒序
            # （它从最新一条往回吃），所以先翻一下。
            return group_quiz_round(list(reversed(self.quiz_session)))
        return group_quiz_round(self.db.recent_quiz_answers())

    def _note_pointer_text(self) -> str:
        """「笔记区在哪、已经有几篇」—— 写进待办备注用。

        一篇都没生成过时返回空串：那就不提这件事，别在待办备注里塞一句
        「笔记：0 篇」，看着像错误。**只读**，不会顺手把分类建出来。
        """
        if self.notes is None:
            return ""
        return self.notes.pointer_text()

    def _note_confirm_text(self, plan: dict) -> str:
        """确认框里那段话：落点、条数、已有的会被怎么处理，一次说清。

        单独抽出来是为了能测 —— 弹窗里的文案本来最容易写歪（说「新建 3 篇」
        实际却更新了 3 篇），而它又是用户唯一的事前依据。
        """
        lines = [f"把这一轮自测的 {plan['total']} 个函数整理成学习笔记模板。", ""]
        area = f"落点：{plan['area']}"
        if plan.get("first_run"):
            area += "（首次生成时会自动建好这个分类）"
        lines.append(area)

        def block(title: str, titles: list, limit: int = 5) -> None:
            if not titles:
                return
            lines.append("")
            lines.append(f"{title}（{len(titles)} 篇）：")
            lines.extend(f"    · {name}" for name in titles[:limit])
            if len(titles) > limit:
                lines.append(f"    …… 另外 {len(titles) - limit} 篇")

        block("新建", plan.get("created_titles") or [])
        block("更新（只换自动生成那一段，你写的「我的补充」原样保留）",
              plan.get("updated_titles") or [])
        lines += [
            "",
            "笔记里上面那段是自动生成的（颜色 / 字体 / 排版都跟你自己写的不同，"
            "一眼能分开），下面「我的补充」是你自己的地方；重新生成只覆盖上面那段。",
        ]
        return "\n".join(lines)

    def generate_study_notes(self):
        """把这一轮自测整理成学习笔记模板。

        **只在点这个按钮时才写**（与待办联动同一个原则）：不做后台自动整理。
        真正的写库全在注入进来的 ``notes``（``ExcelNoteBridge``）里。
        """
        if self.notes is None:
            self._set_status("这一版没注入笔记桥，笔记联动还没接上。")
            return
        items = self._note_source_items()
        if not items:
            messagebox.showinfo(
                "生成学习笔记",
                "还没有可整理的自测记录。\n\n"
                "先去「自测出题」做一轮（答错的那几道最值得记），"
                "回来这里就能一键整理成一套笔记模板。",
                parent=self)
            return

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        todo_title = self.review_todo_title
        # 先干跑一遍：确认框要说的「新建几篇 / 更新几篇」与实际写库走的是
        # 同一条判定路径（bridge 里 _classify 收口），不然确认框会骗人。
        plan = self.notes.plan_notes(items, generated_at=generated_at,
                                     todo_title=todo_title, todo_done=False)
        if not plan["total"]:
            self._set_status("这一轮里没有可整理的函数。")
            return
        if not messagebox.askyesno("生成学习笔记", self._note_confirm_text(plan),
                                   parent=self):
            return

        result = self.notes.sync_notes(items, generated_at=generated_at,
                                       todo_title=todo_title, todo_done=False)
        parts = []
        if result["created"]:
            parts.append(f"新建 {result['created']} 篇")
        if result["updated"]:
            parts.append(f"更新 {result['updated']} 篇")
        self._set_status(
            f"已{'、'.join(parts)}学习笔记 → {result['area']}。"
            "切到「学习笔记」模块就能接着写。")
        self.refresh_nav()

    # ==================================================================
    # 视图 2：函数宝典
    # ==================================================================
    def _selected_mastery_filter(self):
        label = self.mastery_var.get()
        for text, value in MASTERY_FILTER_CHOICES:
            if text == label:
                return value
        return None

    def _library_items(self):
        category = self.category_var.get()
        if category in ("", "全部分类"):
            category = None
        items = self.db.list_functions(
            category=category,
            mastery=self._selected_mastery_filter(),
            keyword=self.search_var.get(),
        )
        if self.stage_codes:
            order = {code: index for index, code in enumerate(self.stage_codes)}
            items = [item for item in items if item["code"] in order]
            items.sort(key=lambda item: order.get(item["code"], 0))
        return items

    def render_library(self):
        if self.stage_codes:
            self.title_var.set(f"学习路径 · {self.stage_title}")
            self.meta_var.set(f"本阶段 {len(self.stage_codes)} 个函数"
                              "（按建议顺序排列，点行看详情）")
            ttk.Button(self.head_actions, text="退出阶段筛选",
                       command=self.clear_stage_filter).pack(side="right")
        else:
            self.title_var.set("函数宝典")
            items_hint = self.db.count_functions()
            self.meta_var.set(f"共 {items_hint} 个函数 · 按分类筛选，点行看语法 / 示例 / 易错点")

        # 自建入口：设计文档写明「冷门函数留给自建，你照书补」。
        # 删除按钮只在选中自建函数时可用（内置的不许删）。
        selected = (self.db.get_function(self.selected_function_id)
                    if self.selected_function_id else None)
        if selected is not None and not int(selected.get("is_builtin", 1)):
            ttk.Button(self.head_actions, text="删除这个自建函数",
                       command=self.delete_selected_function).pack(
                side="right", padx=(0, 6))
        ttk.Button(self.head_actions, text="新增函数（照书补）",
                   command=self.add_custom_function).pack(side="right", padx=(0, 6))

        for child in self.list_tree.get_children(""):
            self.list_tree.delete(child)
        items = self._library_items()
        for item in items:
            self.list_tree.insert(
                "", "end", iid=f"fn::{item['id']}",
                text="",
                values=(item["code"], item.get("name_cn", ""),
                        mastery_label(item.get("mastery", 0))),
            )
        if not items:
            self.title_var.set(self.title_var.get() + "（无匹配结果）")

        target = None
        if self.selected_function_id and self.list_tree.exists(
                f"fn::{self.selected_function_id}"):
            target = f"fn::{self.selected_function_id}"
        elif items:
            target = f"fn::{items[0]['id']}"
        if target:
            self.list_tree.selection_set(target)
            self.list_tree.see(target)
            self.show_function_detail(int(target.split("::", 1)[1]))
        else:
            self.detail_area.clear()
            _empty_hint(self.detail_area.inner,
                        "没有匹配的函数。把搜索词缩短一点，"
                        "或把分类 / 掌握度切回「全部」。",
                        palette=self.palette).pack(anchor="w", pady=8)

    def clear_stage_filter(self):
        self.stage_codes = None
        self.stage_title = ""
        self.refresh_nav()
        self.render_library()

    def _on_list_select(self, _event=None):
        selection = self.list_tree.selection()
        if not selection:
            return
        self.show_function_detail(int(selection[0].split("::", 1)[1]))

    def show_function_detail(self, function_id: int):
        """渲染右侧详情。所有字段都是「有才画」，空字段不占位。"""
        item = self.db.get_function(function_id)
        if not item:
            return
        state = self.db.progress_map().get(int(function_id)) or {}
        item["mastery"] = int(state.get("mastery", 0) or 0)
        # get_function 只返回函数表本身，复习排期在 progress 表里，必须合并进来，
        # 否则下面「下次复习」那行永远是空的（字段拿不到，压根不画）。
        item["next_review_at"] = state.get("next_review_at", "") or ""
        item["review_count"] = int(state.get("review_count", 0) or 0)
        self.selected_function_id = int(function_id)

        area = self.detail_area
        area.clear()
        host = area.inner

        head = tk.Frame(host, bg=self.palette.surface)
        head.pack(fill="x", anchor="w")
        tk.Label(head, text=item["code"], bg=self.palette.surface,
                 fg=self.palette.text_primary, font=TYPOGRAPHY.hero).pack(side="left")
        tk.Label(head, text=item.get("name_cn", ""), bg=self.palette.surface,
                 fg=self.palette.text_secondary,
                 font=TYPOGRAPHY.subtitle).pack(side="left", padx=(10, 0))
        _badge(head, item.get("category", ""), fg=self.palette.text_muted,
               palette=self.palette).pack(side="left", padx=(10, 0))
        _badge(head, difficulty_label(item.get("difficulty")),
               fg=self.palette.text_secondary, palette=self.palette).pack(
            side="left", padx=(4, 0))
        _badge(head, "重要度 " + importance_label(item.get("importance")),
               fg=self.palette.text_secondary, palette=self.palette).pack(
            side="left", padx=(4, 0))
        if item.get("min_version"):
            _badge(head, item["min_version"], fg=self.palette.text_muted,
                   palette=self.palette).pack(side="left", padx=(4, 0))

        tk.Label(host, text=_plain(item.get("description", "")),
                 bg=self.palette.surface,
                 fg=self.palette.text_primary, font=TYPOGRAPHY.body, justify="left",
                 anchor="w", wraplength=760).pack(anchor="w", pady=(8, 0))

        mastery_row = tk.Frame(host, bg=self.palette.surface)
        mastery_row.pack(anchor="w", pady=(10, 0))
        tk.Label(mastery_row, text="我的掌握度", bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        mastery_box = ttk.Combobox(
            mastery_row, state="readonly", width=8,
            values=[label for _, label in MASTERY_CHOICES],
        )
        mastery_box.set(mastery_label(item.get("mastery", 0)))
        mastery_box.pack(side="left", padx=6)
        reverse = {label: value for value, label in MASTERY_CHOICES}
        mastery_box.bind(
            "<<ComboboxSelected>>",
            lambda e, box=mastery_box, fid=item["id"]:
            self.set_mastery(fid, reverse.get(box.get(), 0)),
        )
        if item.get("next_review_at"):
            tk.Label(mastery_row, text=f"下次复习 {item['next_review_at']}",
                     bg=self.palette.surface, fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(side="left", padx=(10, 0))

        block = _mono_block(host, item.get("syntax", ""), palette=self.palette,
                            on_copy=self.copy_to_clipboard, height_lines=2,
                            highlight=tokenize_formula)
        block.pack(fill="x", anchor="w", pady=(10, 0))

        for title, key, kwargs in (
            ("参数", "args_desc", {}),
            ("返回值", "returns", {}),
            ("易错点（最值钱的一栏）", "pitfalls", {"fg": self.palette.danger}),
            ("适用场景", "use_cases", {}),
            ("相关函数", "related", {"fg": self.palette.text_secondary}),
        ):
            widget = _field(host, title, item.get(key, ""), palette=self.palette,
                            **kwargs)
            if widget is not None:
                widget.pack(fill="x", anchor="w", pady=(10, 0))

        if item.get("related"):
            self._related_chips(host, item["related"]).pack(anchor="w", pady=(6, 0))

        if item.get("example_formula"):
            tk.Label(host, text="示例", bg=self.palette.surface,
                     fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(anchor="w", pady=(12, 2))
            example = _mono_block(host, item["example_formula"], palette=self.palette,
                                  on_copy=self.copy_to_clipboard, height_lines=3,
                                  highlight=tokenize_formula)
            example.pack(fill="x", anchor="w")
            if item.get("example_result"):
                tk.Label(host, text=item["example_result"], bg=self.palette.surface,
                         fg=self.palette.text_secondary, font=TYPOGRAPHY.caption,
                         justify="left", anchor="w", wraplength=740).pack(
                    anchor="w", pady=(4, 0))

        # 我的书页 + 我的理解：就地编辑，改完点保存
        mine = tk.Frame(host, bg=self.palette.surface)
        mine.pack(fill="x", anchor="w", pady=(14, 0))
        tk.Label(mine, text="对照实体书", bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(anchor="w")
        page_row = tk.Frame(mine, bg=self.palette.surface)
        page_row.pack(anchor="w", pady=(4, 0))
        tk.Label(page_row, text="书页码", bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        page_var = tk.StringVar(value=item.get("book_page", ""))
        ttk.Entry(page_row, textvariable=page_var, width=14).pack(side="left", padx=6)
        ttk.Button(page_row, text="记住这一页", command=lambda:
                   self.save_book_page(item["id"], page_var.get())).pack(side="left")

        tk.Label(mine, text="我的理解（想到什么写什么，下次复习会一起看到）",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(anchor="w", pady=(10, 4))
        note_text = tk.Text(mine, height=4, wrap="word",
                            bg=self.palette.surface_alt,
                            fg=self.palette.text_primary, relief="flat",
                            highlightthickness=1,
                            highlightbackground=self.palette.border_soft)
        note_text.insert("1.0", item.get("my_note", ""))
        note_text.pack(fill="x")
        tk.Button(mine, text="保存我的理解", relief="flat", bd=0,
                  bg=self.palette.chip_bg, fg=self.palette.text_primary,
                  activebackground=self.palette.chip_bg_hover,
                  font=TYPOGRAPHY.caption, padx=10, pady=3, cursor="hand2",
                  command=lambda fid=item["id"], widget=note_text:
                  self.save_my_note(fid, widget),
                  ).pack(anchor="w", pady=(6, 0))

        buttons = tk.Frame(host, bg=self.palette.surface)
        buttons.pack(anchor="w", pady=(14, 4))
        ttk.Button(buttons, text="复制这一条说明（Markdown）",
                   command=lambda i=item: self.copy_function_markdown(i)).pack(side="left")
        ttk.Button(buttons, text="为它写一篇笔记",
                   command=lambda i=item: self.add_note(function_id=i["id"],
                                                        function_name=i["code"])
                   ).pack(side="left", padx=6)
        self._highlight_related(host)

    def _related_chips(self, parent, related: str):
        holder = tk.Frame(parent, bg=self.palette.surface)
        # 分隔符收口在数据层（``|`` ``,`` ``、`` ``;`` 与空白都认），
        # 内置种子只用 ``|``，但自定义函数很可能打逗号。
        for code in split_codes(related):
            exists = self.db.get_function_by_code(code) is not None
            text = f" {code} "
            label = tk.Label(
                holder, text=text,
                bg=self.palette.chip_bg if exists else self.palette.surface_alt,
                fg=self.palette.text_primary if exists else self.palette.text_muted,
                font=TYPOGRAPHY.badge, padx=4, pady=2,
                cursor="hand2" if exists else "",
            )
            label.pack(side="left", padx=(0, 5))
            if exists:
                label.bind("<Button-1>", lambda e, c=code: self.open_function(c))
        return holder

    def _highlight_related(self, _host):
        """占位：相关函数已经用可点胶囊表达，这里不再额外画一条。"""
        return None

    def set_mastery(self, function_id: int, mastery: int):
        self.db.set_mastery(function_id, mastery)
        self._set_status(f"掌握度已设为「{mastery_label(mastery)}」，"
                         "它已经排进今天的复习队列。")
        self.refresh_nav()
        self.render_library()

    def save_book_page(self, function_id: int, page: str):
        self.db.update_function_fields(function_id, book_page=str(page).strip())
        self._set_status(f"已记住书页码：{page or '（清空）'}")

    def save_my_note(self, function_id: int, widget):
        text = widget.get("1.0", "end").strip()
        self.db.update_function_fields(function_id, my_note=text)
        self._set_status("我的理解已保存。")

    # -- 自建函数 --------------------------------------------------------
    def add_custom_function(self):
        """照书补录一个内置库里没有的函数。"""
        dialog = ExcelFunctionDialog(
            self, "新增函数（照书补）", app_title=self.app_title,
            categories=[item["name"] for item in CATEGORIES],
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            new_id = self.db.add_custom_function(dialog.result)
        except ValueError as exc:
            messagebox.showwarning(self.app_title, str(exc), parent=self)
            return
        self.selected_function_id = int(new_id)
        self.stage_codes = None
        self.stage_title = ""
        self.search_var.set("")
        self.category_var.set("全部分类")
        self.mastery_var.set(MASTERY_FILTER_CHOICES[0][0])
        self.show_view(VIEW_LIBRARY)
        self.refresh_nav()
        self._set_status(f"已加入自建函数 {dialog.result.get('code', '')}"
                         "（它和内置函数一样能复习、能记书页码）。")

    def delete_selected_function(self):
        item = (self.db.get_function(self.selected_function_id)
                if self.selected_function_id else None)
        if item is None:
            self._set_status("先在上面选一个函数。")
            return
        if int(item.get("is_builtin", 1)):
            # 内置的不给删：200 条是课程骨架，删一条会让学习路径出现空洞，
            # 而种子里每次启动都会 INSERT OR IGNORE 回来，删了也会复活 ——
            # 与其让人困惑，不如直接说清楚。
            messagebox.showinfo(
                self.app_title,
                f"{item['code']} 是内置函数，不能删除。\n"
                "内置的 200 条是学习路径的骨架（下次启动会自动补回），\n"
                "你只能改它的书页码和掌握度。自建函数才可以删。",
                parent=self)
            return
        if not messagebox.askyesno(self.app_title,
                                   f"确定删除自建函数 {item['code']}？\n"
                                   "挂在它上面的笔记会保留，但会失去与函数的关联。",
                                   parent=self):
            return
        if self.db.delete_function(item["id"]):
            self.selected_function_id = None
            self.show_view(VIEW_LIBRARY)
            self.refresh_nav()
            self._set_status(f"自建函数 {item['code']} 已删除。")

    def open_function(self, code: str):
        item = self.db.get_function_by_code(code)
        if not item:
            self._set_status(f"库里还没有 {code} 的详解。")
            return
        self.selected_function_id = int(item["id"])
        self.stage_codes = None
        self.stage_title = ""
        self.search_var.set("")
        self.category_var.set("全部分类")
        self.mastery_var.set(MASTERY_FILTER_CHOICES[0][0])
        self.show_view(VIEW_LIBRARY)

    def pick_random_function(self):
        import random
        codes = [item["code"] for item in self.db.all_functions()]
        if not codes:
            return
        self.open_function(random.choice(codes))
        self._set_status("随机抽到一个，翻一眼就当复习。")

    # ==================================================================
    # 视图 3：自测出题
    # ==================================================================
    def _quiz_mode(self) -> str:
        label = self.quiz_mode_var.get()
        for value, text in QUIZ_MODE_CHOICES:
            if text == label:
                return value
        return QUIZ_MODE_MIXED

    def _quiz_category(self):
        """当前分类筛选，``None`` 表示不限。

        分类下拉是「宝典 / 配方 / 自测 / 错题本」四个视图共用的一个控件
        （见 ``_sync_filter_row``），这里只做一次翻译，三个视图口径一致。
        """
        category = self.category_var.get()
        return None if category in ("", "全部分类") else category

    def start_quiz(self, *, only_wrong: bool = False, reset: bool = True):
        """开始一轮自测。

        ``reset=False`` 只切到自测视图、不重新抽题。
        """
        if reset:
            questions = self.db.quiz_questions(
                count=QUIZ_BATCH, category=self._quiz_category(),
                mode=self._quiz_mode(), only_wrong=only_wrong)
            self._reset_quiz_round(questions)
            if not questions:
                self._set_status("抽不出题：先确认「函数宝典」里有函数，"
                                 "或把分类切回「全部」。")
            else:
                self._set_status(f"这轮 {len(questions)} 题。答错的会进错题本，"
                                 "并按「忘了」回灌到复习间隔里。")
        self.show_view(VIEW_QUIZ)

    def start_wrong_quiz(self):
        """错题专场：只从错题本里抽题。做对的那几道会被标成「已订正」。"""
        self.start_quiz(only_wrong=True)

    def _reset_quiz_round(self, questions):
        self.quiz_questions = list(questions or [])
        self.quiz_index = 0
        self.quiz_correct = 0
        self.quiz_wrong = 0
        self.quiz_answered = False
        self.quiz_picked = ""
        self.quiz_formula_state = ""
        self.quiz_retry_id = None
        self.quiz_formula_var.set("")

    def _current_quiz(self):
        if 0 <= self.quiz_index < len(self.quiz_questions):
            return self.quiz_questions[self.quiz_index]
        return None

    def render_quiz(self):
        self.title_var.set("自测出题")
        stats = self.db.quiz_stats()
        self.meta_var.set(f"累计答 {stats['attempts']} 题 · 正确率 {stats['accuracy']}% · "
                          f"错题本挂着 {stats['pending']} 条")

        # head_actions 每次渲染前会被清空，所以这里的控件要重建一遍。
        # 题型下拉**不绑定切换**：改题型只改那个变量的值，点右边按钮才开新一轮 ——
        # 免得「手一滑换了个题型，做到一半的这一轮就没了」。
        ttk.Label(self.head_actions, text="题型").pack(side="left", padx=(0, 4))
        ttk.Combobox(self.head_actions, textvariable=self.quiz_mode_var,
                     state="readonly", width=10,
                     values=[text for _value, text in QUIZ_MODE_CHOICES]).pack(
            side="left", padx=(0, 8))
        ttk.Button(self.head_actions,
                   text="重新抽题" if self.quiz_questions else "开始一轮",
                   style="Primary.TButton", command=self.start_quiz).pack(side="left")
        if stats["pending"]:
            ttk.Button(self.head_actions, text=f"错题专场（{stats['pending']}）",
                       command=self.start_wrong_quiz).pack(side="left", padx=(6, 0))

        area = self.quiz_area
        area.clear()
        if not self.quiz_questions:
            _empty_hint(
                area.inner,
                "点右上角「开始一轮」抽 10 题；改了「题型」再点它就换题型。\n"
                "选择题机器判分；写公式题你自己写、自己对 —— 写不出来时看一眼示例，"
                "那一下才叫学到了。\n"
                "两种题的错题都会进错题本，并按「忘了」回灌到「今日复习」的间隔里，"
                "所以自测和复习是同一条遗忘曲线上的两种练习。",
                palette=self.palette).pack(anchor="w", pady=(8, 0))
            return

        question = self._current_quiz()
        if question is None:
            self._quiz_summary(area.inner).pack(fill="x", anchor="w")
            return
        self._quiz_card(area.inner, question).pack(fill="x", anchor="w")

    def _quiz_card(self, parent, question):
        card = tk.Frame(parent, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        head = tk.Frame(card, bg=self.palette.surface)
        head.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(head, text=f"第 {self.quiz_index + 1} / {len(self.quiz_questions)} 题",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(side="left")
        _badge(head, QUIZ_TYPE_LABELS.get(question["quiz_type"], ""),
               fg=self.palette.accent_text, bg=self.palette.accent,
               palette=self.palette).pack(side="left", padx=(8, 0))
        if question.get("category"):
            _badge(head, question["category"], fg=self.palette.text_muted,
                   palette=self.palette).pack(side="left", padx=(4, 0))
        if self.quiz_retry_id:
            _badge(head, "错题重做", fg="#ffffff", bg=self.palette.warn,
                   palette=self.palette).pack(side="left", padx=(4, 0))
        tk.Label(head, text=f"已对 {self.quiz_correct} · 已错 {self.quiz_wrong}",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(side="right")

        tk.Label(card, text=question["prompt"], bg=self.palette.surface,
                 fg=self.palette.text_primary, font=TYPOGRAPHY.body,
                 justify="left", anchor="w", wraplength=720).pack(
            anchor="w", padx=12, pady=(8, 0))

        if question["quiz_type"] == QUIZ_CHOICE:
            self._quiz_choice_body(card, question)
        else:
            self._quiz_formula_body(card, question)
        return card

    def _quiz_choice_body(self, card, question):
        """选择题：没答之前是四个按钮，答完换成四个带标记的色块。

        为什么答题前用按钮、答题后用色块：按钮是**能点的**，色块是**只能看的** ——
        形态跟着「可操作性」走，省得答完了还去点一个已经没有意义的按钮。
        """
        grid = tk.Frame(card, bg=self.palette.surface)
        grid.pack(fill="x", padx=8, pady=(8, 4))
        letters = "ABCD"
        for index, option in enumerate(question.get("options") or []):
            row, column = divmod(index, 2)
            picked = option == self.quiz_picked
            if not self.quiz_answered:
                ttk.Button(grid, text=f"{letters[index]}. {option}", width=26,
                           command=lambda opt=option: self.answer_choice(opt)).grid(
                    row=row, column=column, sticky="w", padx=4, pady=3)
                continue
            if option == question["answer"]:
                fg, bg, mark = "#ffffff", self.palette.success, "√"
            elif picked:
                fg, bg, mark = "#ffffff", self.palette.danger, "×"
            else:
                fg, bg, mark = self.palette.text_muted, self.palette.surface_alt, " "
            _badge(grid, f"{letters[index]}. {option} {mark}", fg=fg, bg=bg,
                   palette=self.palette, font=TYPOGRAPHY.body).grid(
                row=row, column=column, sticky="w", padx=4, pady=3)
        if self.quiz_answered:
            self._quiz_feedback(card, question, self.quiz_picked == question["answer"])

    def _quiz_formula_body(self, card, question):
        """写公式题：**先写、再看、最后自己判**，三个阶段各画一屏。"""
        body = tk.Frame(card, bg=self.palette.surface)
        body.pack(fill="x", padx=12, pady=(8, 0))

        if not self.quiz_answered:                     # 阶段一：写
            tk.Label(body, text="在下面写出来（写不出来没关系，写完看示例）",
                     bg=self.palette.surface, fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(anchor="w")
            row = tk.Frame(body, bg=self.palette.surface)
            row.pack(anchor="w", pady=(4, 0))
            entry = ttk.Entry(row, textvariable=self.quiz_formula_var, width=66,
                              font=TYPOGRAPHY.mono)
            entry.pack(side="left")
            ttk.Button(row, text="对答案", style="Primary.TButton",
                       command=self.reveal_formula).pack(side="left", padx=(6, 0))
            entry.focus_set()
            return

        if self.quiz_formula_var.get().strip():
            tk.Label(body, text="我写的是：" + self.quiz_formula_var.get().strip(),
                     bg=self.palette.surface, fg=self.palette.text_secondary,
                     font=TYPOGRAPHY.mono, justify="left", anchor="w",
                     wraplength=700).pack(anchor="w")

        if not self.quiz_formula_state:                 # 阶段二：对答案 + 自评
            self._quiz_reveal(card, question)
            grade = tk.Frame(card, bg=self.palette.surface)
            grade.pack(fill="x", padx=12, pady=(8, 10))
            tk.Label(grade, text="对着示例看：你写对了吗？",
                     bg=self.palette.surface, fg=self.palette.text_primary,
                     font=TYPOGRAPHY.body).pack(side="left")
            ttk.Button(grade, text="写对了", style="Primary.TButton",
                       command=lambda: self.grade_formula(True)).pack(
                side="left", padx=(8, 6))
            ttk.Button(grade, text="没写对",
                       command=lambda: self.grade_formula(False)).pack(side="left")
            return

        self._quiz_feedback(card, question, self.quiz_formula_state == "right")

    def _quiz_reveal(self, card, question):
        """揭晓块：答案 + 语法 + 示例 + 易错点。**答题前绝不渲染。**"""
        holder = tk.Frame(card, bg=self.palette.surface)
        holder.pack(fill="x", padx=12, pady=(6, 0))
        if question["quiz_type"] == QUIZ_CHOICE:
            answer = f"{question['answer']}（{question.get('name_cn', '')}）"
        else:
            answer = question["answer"]
        for title, text in (("答案", answer),
                            ("语法", question.get("syntax", "")),
                            ("示例", question.get("reveal_formula", "")),
                            ("示例结果", question.get("reveal_result", "")),
                            ("易错点", question.get("reveal_pitfalls", ""))):
            block = _field(holder, title, text, palette=self.palette,
                           mono=title in ("语法", "示例"),
                           highlight=tokenize_formula
                           if title in ("语法", "示例") else None)
            if block is not None:
                block.pack(anchor="w", pady=(2, 0))
        ttk.Button(holder, text="看完整说明",
                   command=lambda code=question["code"]: self.open_function(code)
                   ).pack(anchor="w", pady=(6, 0))
        return holder

    def _quiz_feedback(self, card, question, correct):
        """自评 / 判分都结束之后的收尾：一句结论 + 「下一题」+ 揭晓。

        揭晓字段（语法 / 示例 / 易错点）**只在这里取用** —— 这就是题目不用
        另建一张表的原因：答案本来就在函数里，只是答题前不看它。
        """
        head = tk.Frame(card, bg=self.palette.surface)
        head.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(head, text="答对了" if correct else "答错了（已进错题本）",
                 bg=self.palette.surface,
                 fg=self.palette.success if correct else self.palette.danger,
                 font=TYPOGRAPHY.section).pack(side="left")
        ttk.Button(head, text="下一题", style="Primary.TButton",
                   command=self.next_question).pack(side="right")
        self._quiz_reveal(card, question)
        tk.Frame(card, bg=self.palette.surface, height=10).pack()

    def answer_choice(self, option):
        """点了一个选项 —— 选择题的唯一入口。"""
        question = self._current_quiz()
        if question is None or self.quiz_answered:
            return
        self.quiz_picked = option
        self.quiz_answered = True
        self._record_quiz(question, user_answer=option,
                          is_correct=option == question["answer"])
        self.render_quiz()

    def reveal_formula(self):
        """写公式题：从「写」进入「对答案 + 自评」。"""
        question = self._current_quiz()
        if question is None or self.quiz_answered:
            return
        self.quiz_answered = True
        self.quiz_formula_state = ""
        self.render_quiz()

    def grade_formula(self, correct: bool):
        """写公式题的自评开关。

        **自评不是偷懒**：公式的等价写法太多（``INDEX+MATCH`` 换个写法照样对），
        机器判错的代价比不判大得多；而「把答案写一遍」本身就已经是一次提取练习。
        """
        question = self._current_quiz()
        if question is None or not self.quiz_answered or self.quiz_formula_state:
            return
        self.quiz_formula_state = "right" if correct else "wrong"
        self._record_quiz(question, user_answer=self.quiz_formula_var.get().strip(),
                          is_correct=bool(correct))
        self.render_quiz()

    def _record_quiz(self, question, *, user_answer, is_correct):
        """落一次作答，并刷新底栏那句反馈。"""
        if is_correct:
            self.quiz_correct += 1
        else:
            self.quiz_wrong += 1
        state = self.db.record_quiz_result(
            function_id=question["function_id"], quiz_type=question["quiz_type"],
            prompt=question["prompt"], answer=question["answer"],
            user_answer=user_answer, is_correct=is_correct,
            category=question.get("category", ""))
        # 记一笔「本轮」作答。字段名刻意跟 recent_quiz_answers 查出来的行对齐
        # （created_at / user_answer / is_correct），这样「本轮」和「重启后从
        # 库里捞回来的最近一轮」能走同一个 group_quiz_round —— 两条来源的去重
        # 与排序口径必须完全一致，否则同一件事在两种情况下整理出的结果不同。
        entry = {
            **question,
            "user_answer": user_answer,
            "is_correct": bool(is_correct),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        # 掌握度 / 下次复习时间从回灌结果里带回来：笔记模板的元信息要用，
        # 而且这两个值只有刚做完自测时才最新鲜。
        if state.get("mastery") is not None:
            entry["mastery"] = state["mastery"]
            entry["next_review_at"] = state.get("next_review_at", "")
        self.quiz_session.append(entry)
        # 从「重做这一道」进来的：做对了就顺手把它移出错题本
        if self.quiz_retry_id and is_correct:
            self.db.mark_quiz_retried(self.quiz_retry_id, correct=False)
            self.quiz_retry_id = None
        tail = ""
        if state.get("mastery") is not None:
            tail = (f"；已按「{'熟练' if is_correct else '忘了'}」回灌：掌握度"
                    f"{mastery_label(state['mastery'])}、"
                    f"{state.get('interval_days', 1)} 天后再复习")
        self._set_status(("答对了" if is_correct else "答错了，已进错题本") + tail + "。")
        self.refresh_nav()

    def next_question(self):
        self.quiz_answered = False
        self.quiz_picked = ""
        self.quiz_formula_state = ""
        self.quiz_retry_id = None
        self.quiz_formula_var.set("")
        self.quiz_index += 1
        if self.quiz_index >= len(self.quiz_questions):
            self._set_status(f"这轮做完了：对 {self.quiz_correct}、"
                             f"错 {self.quiz_wrong}。")
        self.render_quiz()

    def _quiz_summary(self, parent):
        total = len(self.quiz_questions)
        accuracy = round(self.quiz_correct * 100 / total) if total else 0
        card = tk.Frame(parent, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        tk.Label(card, text="这一轮做完了", bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(card, text=f"{total} 题，对 {self.quiz_correct}、错 {self.quiz_wrong}，"
                            f"正确率 {accuracy}%。",
                 bg=self.palette.surface, fg=self.palette.text_primary,
                 font=TYPOGRAPHY.body).pack(anchor="w", padx=12)
        tk.Label(card, text="错的那几道已经进「错题本」，同时把「今日复习」的间隔"
                            "拉回了一天 —— 明天它们会自己冒出来。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption, justify="left", anchor="w",
                 wraplength=700).pack(anchor="w", padx=12, pady=(4, 0))
        row = tk.Frame(card, bg=self.palette.surface)
        row.pack(fill="x", padx=12, pady=(8, 10))
        ttk.Button(row, text="再来一轮", style="Primary.TButton",
                   command=self.start_quiz).pack(side="left")
        if self.quiz_wrong:
            ttk.Button(row, text=f"去错题本（{self.quiz_wrong}）",
                       command=lambda: self.show_view(VIEW_WRONG)).pack(
                side="left", padx=6)
        ttk.Button(row, text="去做今日复习",
                   command=self.start_today_review).pack(side="left")
        # 答完一轮就是「学完了」的那一刻 —— 把整理笔记的入口放在这儿最顺手。
        # 数量直接写在按钮上：不用点开才知道要做多少事。
        note_count = len(self._note_source_items())
        if note_count:
            ttk.Button(row, text=f"生成学习笔记（{note_count}）",
                       command=self.generate_study_notes).pack(
                side="left", padx=(6, 0))
        return card

    # ==================================================================
    # 视图 4：错题本
    # ==================================================================
    def _wrong_items(self, *, limit=None):
        items = self.db.quiz_wrong_items(category=self._quiz_category(), limit=limit)
        keyword = self.search_var.get().strip().lower()
        if keyword:
            items = [
                item for item in items
                if keyword in f"{item.get('code', '')} {item.get('name_cn', '')}".lower()
                or keyword in str(item.get("prompt", "")).lower()
            ]
        return items

    def render_wrong(self):
        self.title_var.set("错题本")
        stats = self.db.quiz_stats()
        items = self._wrong_items(limit=QUIZ_WRONG_LIMIT)
        self.meta_var.set(f"挂着 {stats['pending']} 条没订正 · "
                          f"累计答错 {stats['wrong']} 题 · 正确率 {stats['accuracy']}%")

        ttk.Button(self.head_actions, text="错题专场",
                   command=self.start_wrong_quiz).pack(side="right")
        if stats["pending"]:
            ttk.Button(self.head_actions, text="清空错题本",
                       command=self.clear_wrong_book).pack(side="right", padx=(0, 6))
        ttk.Button(self.head_actions, text="开始一轮自测",
                   command=self.start_quiz).pack(side="right", padx=(0, 6))

        area = self.wrong_area
        area.clear()
        if not items:
            _empty_hint(
                area.inner,
                "错题本是空的。\n"
                "「自测出题」里答错的函数会自动进来；重做一遍做对了，"
                "或者点「已订正」，它就会从这里消失。",
                palette=self.palette).pack(anchor="w", pady=(8, 0))
            return
        for item in items:
            self._wrong_card(area.inner, item).pack(fill="x", anchor="w", pady=(0, 10))
        if stats["pending"] > len(items):
            tk.Label(area.inner,
                     text=f"（只列出最近 {len(items)} 条，还有 "
                          f"{stats['pending'] - len(items)} 条更早的；"
                          "用上面的分类 / 搜索缩小范围。）",
                     bg=self.palette.bg, fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(anchor="w", pady=(0, 8))

    def _wrong_card(self, parent, item):
        card = tk.Frame(parent, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        head = tk.Frame(card, bg=self.palette.surface)
        head.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(head, text=item.get("code") or "（函数已不在库里）",
                 bg=self.palette.surface, fg=self.palette.text_primary,
                 font=TYPOGRAPHY.title).pack(side="left")
        if item.get("name_cn"):
            tk.Label(head, text=item["name_cn"], bg=self.palette.surface,
                     fg=self.palette.text_secondary,
                     font=TYPOGRAPHY.body).pack(side="left", padx=(8, 0))
        if item.get("category"):
            _badge(head, item["category"], fg=self.palette.text_muted,
                   palette=self.palette).pack(side="left", padx=(8, 0))
        _badge(head, QUIZ_TYPE_LABELS.get(item.get("quiz_type", ""), ""),
               fg=self.palette.text_muted,
               palette=self.palette).pack(side="left", padx=(4, 0))
        tk.Label(head, text=f"错于 {str(item.get('created_at', ''))[:16]}",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(side="right")

        body = tk.Frame(card, bg=self.palette.surface)
        body.pack(fill="x", padx=12, pady=(6, 0))
        fields = [("当时问的是", item.get("prompt", "")),
                  ("正确答案", item.get("answer", "")),
                  ("我答的", item.get("user_answer", ""))]
        # 写公式题的「正确答案」就是示例公式，再列一遍是重复；
        # 这时候更有信息量的是**它算出来是什么**。
        if item.get("quiz_type") == QUIZ_FORMULA:
            fields.append(("示例结果", item.get("example_result", "")))
        else:
            fields.append(("示例", item.get("example_formula", "")))
        for title, text in fields:
            block = _field(body, title, text, palette=self.palette,
                           fg=self.palette.danger if title == "我答的" else None,
                           mono=title in ("正确答案", "示例"))
            if block is not None:
                block.pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(card, bg=self.palette.surface)
        actions.pack(fill="x", padx=12, pady=(8, 10))
        ttk.Button(actions, text="重做这一道", style="Primary.TButton",
                   command=lambda row=item: self.redo_wrong_item(row)).pack(side="left")
        ttk.Button(actions, text="已订正（回灌熟练）",
                   command=lambda row=item: self.dismiss_wrong_item(row, correct=True)
                   ).pack(side="left", padx=6)
        ttk.Button(actions, text="只是想移出",
                   command=lambda row=item: self.dismiss_wrong_item(row, correct=False)
                   ).pack(side="left")
        if item.get("code"):
            ttk.Button(actions, text="看完整说明",
                       command=lambda code=item["code"]: self.open_function(code)
                       ).pack(side="right")
        return card

    def redo_wrong_item(self, item):
        """只重做这一道。

        ``seed`` 取这道错题的 id：出题要选干扰项、本该是随机的，但同一条错题
        每次重做都该是同一套选项 —— 否则「重做」就变成了「换一题」。
        """
        function = (self.db.get_function(item.get("function_id"))
                    if item.get("function_id") else None)
        if function is None:
            self._set_status("这个函数已经不在库里了，点「只是想移出」清掉它吧。")
            return
        import random
        rng = random.Random(int(item.get("id") or 0))
        pool = self.db.list_functions()
        want_formula = item.get("quiz_type") == QUIZ_FORMULA
        question = (build_formula_question(function, rng=rng) if want_formula
                    else build_choice_question(function, pool, rng=rng))
        if question is None:                  # 缺示例公式 / 选项凑不齐 → 换题型
            question = (build_choice_question(function, pool, rng=rng)
                        if want_formula
                        else build_formula_question(function, rng=rng))
        if question is None:
            self._set_status("这个函数的信息还不够出一道题（补一下语法 / 示例再试）。")
            return
        self._reset_quiz_round([question])
        self.quiz_retry_id = int(item.get("id") or 0)
        self.show_view(VIEW_QUIZ)
        self._set_status(f"重做 {function['code']}：做对了就自动移出错题本。")

    def dismiss_wrong_item(self, item, *, correct: bool):
        """把一条错题移出。``correct=True`` 时会按「熟练」回灌一次掌握度。"""
        quiz_id = int(item.get("id") or 0)
        if not quiz_id or not self.db.mark_quiz_retried(quiz_id, correct=correct):
            self._set_status("这条错题已经不在了，刷新一下就好。")
        else:
            self._set_status(
                f"{item.get('code', '')} 已移出错题本"
                + ("，并按「熟练」回灌了一次。" if correct else "（掌握度没动）。"))
        self.refresh_nav()
        self.render_wrong()

    def clear_wrong_book(self):
        if not messagebox.askyesno(
                self.app_title,
                "清空错题本？\n\n只清「没做对」的记录；"
                "掌握度和复习排期不受影响（那是「今日复习」管的事）。",
                parent=self):
            return
        count = self.db.clear_quiz_log(wrong_only=True)
        self.refresh_nav()
        self.render_wrong()
        self._set_status(f"已清掉 {count} 条错题记录。")

    # ==================================================================
    # 视图 5：学习路径
    # ==================================================================
    def render_path(self):
        self.title_var.set("学习路径")
        self.meta_var.set("七阶段能力阶梯，推荐顺序：L1 → L5 → L2/L4 → L3 → L6 → L7")
        area = self.path_area
        area.clear()
        host = area.inner

        overview = self.db.mastery_overview()
        card = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        card.pack(fill="x", anchor="w", pady=(0, 12))
        tk.Label(card, text=f"总进度：已学 {overview['learned']} / {overview['total']}，"
                            f"熟练 {overview['good']}",
                 bg=self.palette.surface, fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 4))
        _bar_row(card, "已学比例", f"{overview['percent']}%",
                 overview["percent"] / 100, color=self.palette.accent,
                 palette=self.palette, label_width=8).pack(anchor="w", padx=12)
        tk.Label(card, text="「已学」= 掌握度到「生疏」及以上；"
                            "「熟练」= 连续答对到最高档。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(4, 10))

        for stage in self.db.learning_progress():
            self._stage_card(host, stage).pack(fill="x", anchor="w", pady=(0, 10))

    def _stage_card(self, parent, stage):
        card = tk.Frame(parent, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        head = tk.Frame(card, bg=self.palette.surface)
        head.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(head, text=stage["key"], bg=self.palette.surface,
                 fg=self.palette.text_muted,
                 font=TYPOGRAPHY.badge).pack(side="left")
        tk.Label(head, text=stage["title"], bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.title).pack(side="left", padx=(8, 0))
        ttk.Button(head, text="打开这一阶段",
                   command=lambda s=stage: self.open_stage(s)).pack(side="right")

        tk.Label(card, text=stage["goal"], bg=self.palette.surface,
                 fg=self.palette.text_secondary, font=TYPOGRAPHY.body,
                 justify="left", anchor="w", wraplength=740).pack(
            anchor="w", padx=12, pady=(6, 0))
        tk.Label(card, text=stage["tip"], bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption,
                 justify="left", anchor="w", wraplength=740).pack(
            anchor="w", padx=12, pady=(4, 0))

        if stage["is_recipe_stage"]:
            tk.Label(card, text="这一阶段是 20 条实战配方，点「打开」去看。",
                     bg=self.palette.surface, fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(8, 10))
            return card

        row = tk.Frame(card, bg=self.palette.surface)
        row.pack(fill="x", padx=12, pady=(8, 10))
        _bar_row(row, "熟练进度", f"{stage['good']} / {stage['total']}"
                 f"（已学 {stage['learned']}）", stage["percent"] / 100,
                 color=self.palette.success, palette=self.palette,
                 label_width=8).pack(side="left")
        return card

    def open_stage(self, stage):
        if stage["is_recipe_stage"]:
            if not (self.search_var.get() or "").strip():
                self.search_var.set("")
            self.show_view(VIEW_RECIPE)
            self._set_status("实战配方：20 条组合套路，照着在自己的表里敲一遍。")
            return
        self.stage_codes = list(stage["codes"])
        self.stage_title = f"{stage['key']} {stage['title']}"
        self.search_var.set("")
        self.category_var.set("全部分类")
        self.mastery_var.set(MASTERY_FILTER_CHOICES[0][0])
        self.show_view(VIEW_LIBRARY)
        self.refresh_nav()

    # ==================================================================
    # 视图 6：实战配方
    # ==================================================================
    def render_recipe(self):
        self.title_var.set("实战配方")
        category = self.category_var.get()
        if category in ("", "全部分类"):
            category = None
        recipes = self.db.list_recipes(keyword=self.search_var.get(),
                                       category=category)
        scope = f"（{category}）" if category else ""
        self.meta_var.set(f"共 {len(recipes)} 条组合套路{scope} · "
                          "场景 → 成品公式 → 逐段拆解")
        area = self.recipe_area
        area.clear()
        host = area.inner
        if not recipes:
            _empty_hint(host, "没有匹配的配方。把搜索词换成场景里的词试试，"
                              "比如「查找」「工期」「月供」。",
                        palette=self.palette).pack(anchor="w", pady=8)
            return
        for recipe in recipes:
            self._recipe_card(host, recipe).pack(fill="x", anchor="w", pady=(0, 12))

    def _recipe_card(self, parent, recipe):
        card = tk.Frame(parent, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        head = tk.Frame(card, bg=self.palette.surface)
        head.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(head, text=recipe["title"], bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.title).pack(side="left")
        _badge(head, recipe.get("category", ""), fg=self.palette.text_muted,
               palette=self.palette).pack(side="left", padx=(8, 0))
        _badge(head, difficulty_label(recipe.get("difficulty")),
               fg=self.palette.text_secondary, palette=self.palette).pack(
            side="left", padx=(4, 0))
        if recipe.get("book_page"):
            _badge(head, "书页 " + recipe["book_page"], fg=self.palette.text_muted,
                   palette=self.palette).pack(side="left", padx=(4, 0))

        if recipe.get("scene"):
            tk.Label(card, text="什么时候用：" + _plain(recipe["scene"]),
                     bg=self.palette.surface,
                     fg=self.palette.text_secondary, font=TYPOGRAPHY.body,
                     justify="left", anchor="w", wraplength=740).pack(
                anchor="w", padx=12, pady=(6, 0))
        if recipe.get("formula"):
            tk.Label(card, text="公式", bg=self.palette.surface,
                     fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(8, 2))
            _mono_block(card, recipe["formula"], palette=self.palette,
                        on_copy=self.copy_to_clipboard, height_lines=3).pack(
                fill="x", padx=12)
        for title, key, fg in (("拆解", "breakdown", None),
                               ("容易踩的坑", "pitfalls", self.palette.danger)):
            widget = _field(card, title, recipe.get(key, ""), palette=self.palette,
                            fg=fg, font=TYPOGRAPHY.caption if fg else TYPOGRAPHY.body)
            if widget is not None:
                widget.pack(fill="x", anchor="w", padx=12, pady=(8, 0))
        if recipe.get("related"):
            self._related_chips(card, recipe["related"]).pack(
                anchor="w", padx=12, pady=(8, 0))
        if recipe.get("my_note"):
            _field(card, "我的心得", recipe["my_note"], palette=self.palette).pack(
                fill="x", anchor="w", padx=12, pady=(8, 0))

        row = tk.Frame(card, bg=self.palette.surface)
        row.pack(fill="x", padx=12, pady=(8, 10))
        page_var = tk.StringVar(value=recipe.get("book_page", ""))
        tk.Label(row, text="书页码", bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        ttk.Entry(row, textvariable=page_var, width=8).pack(side="left", padx=4)
        ttk.Button(row, text="记住", command=lambda rid=recipe["id"], var=page_var:
                   self.save_recipe_page(rid, var.get())).pack(side="left")
        ttk.Button(row, text="写点心得", command=lambda r=recipe:
                   self.edit_recipe_note(r)).pack(side="left", padx=6)
        return card

    def save_recipe_page(self, recipe_id: int, page: str):
        self.db.update_recipe_fields(recipe_id, book_page=str(page).strip())
        self._set_status(f"配方书页码已记住：{page or '（清空）'}")
        self.render_recipe()

    def edit_recipe_note(self, recipe):
        # 从库里重读一次再编辑：列表里的那条可能是几轮之前渲染的，
        # 用它回填会把别人/上一轮改过的内容盖回去。
        latest = self.db.get_recipe(recipe["id"]) or recipe
        dialog = _TextPrompt(self, title=f"「{latest['title']}」我的心得",
                             initial=latest.get("my_note", ""),
                             app_title=self.app_title)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.db.update_recipe_fields(recipe["id"], my_note=dialog.result)
        self._set_status("心得已保存。")
        self.render_recipe()

    # ==================================================================
    # 视图 7：学习笔记
    # ==================================================================
    def render_note(self):
        self.title_var.set("学习笔记")
        notes = self.db.list_notes(keyword=self.search_var.get())
        self.meta_var.set(f"共 {len(notes)} 篇 · 把书上的页码、自己的理解、"
                          "截下来的图放在一起")
        ttk.Button(self.head_actions, text="编辑选中",
                   command=self.edit_note).pack(side="right", padx=(6, 0))
        ttk.Button(self.head_actions, text="删除选中",
                   command=self.delete_note).pack(side="right", padx=(6, 0))

        for child in self.note_tree.get_children(""):
            self.note_tree.delete(child)
        for note in notes:
            self.note_tree.insert(
                "", "end", iid=f"nt::{note['id']}", text="",
                values=(note.get("title", ""), note.get("book_page", ""),
                        str(note.get("updated_at", ""))[:16].replace("T", " ")),
            )
        if notes:
            target = f"nt::{self.selected_note_id}" if self.selected_note_id and \
                self.note_tree.exists(f"nt::{self.selected_note_id}") else \
                f"nt::{notes[0]['id']}"
            self.note_tree.selection_set(target)
            self.show_note_preview(int(target.split("::", 1)[1]))
        else:
            self.note_preview.configure(state="normal")
            self.note_preview.delete("1.0", "end")
            self.note_preview.insert(
                "1.0",
                "还没有笔记。点上面的「新增笔记」，把书上的页码和自己的理解记下来；\n"
                "在正文里按 Ctrl+V 可以直接把截图贴进来。",
            )
            self.note_preview.configure(state="disabled")

    def _on_note_select(self, _event=None):
        selection = self.note_tree.selection()
        if not selection:
            return
        self.show_note_preview(int(selection[0].split("::", 1)[1]))

    def show_note_preview(self, note_id: int):
        note = self.db.get_note(note_id)
        if not note:
            return
        self.selected_note_id = int(note_id)
        self.note_preview.configure(state="normal")
        self.note_preview.delete("1.0", "end")
        header_parts = []
        if note.get("book_page"):
            header_parts.append(f"书页 {note['book_page']}")
        if note.get("tags"):
            header_parts.append(f"标签 {note['tags']}")
        if note.get("function_id"):
            linked = self.db.get_function(note["function_id"])
            if linked:
                header_parts.append(f"关联函数 {linked['code']}")
        if header_parts:
            self.note_preview.insert("end", " · ".join(header_parts) + "\n\n")
        content = note.get("content", "")
        if HAS_MARKDOWN:
            try:
                markdown_view.render(self.note_preview, content,
                                     empty_hint="（这篇笔记没有正文）")
            except Exception:
                self.note_preview.insert("end", content or "（这篇笔记没有正文）")
        else:
            self.note_preview.insert("end", content or "（这篇笔记没有正文）")
        images = note.get("images", "")
        if images and self.images is not None:
            try:
                paths = self.images.resolve_paths(images)
            except Exception:
                paths = []
            names = [p.name for p in (paths or []) if p]
            if names:
                self.note_preview.insert("end", "\n\n截图：" + "、".join(names))
        self.note_preview.configure(state="disabled")

    def add_note(self, function_id=None, function_name=""):
        if self.image_preview_cls is None and function_id is None:
            # 没有图片能力也能记笔记，只是不能贴图；这里不做拦截，仅提示
            pass
        linked_name = function_name
        if function_id and not linked_name:
            item = self.db.get_function(function_id)
            linked_name = item["code"] if item else ""
        dialog = ExcelNoteDialog(
            self, app_title=self.app_title, function_name=linked_name,
            image_preview_cls=self.image_preview_cls, images=self.images,
        )
        if function_id:
            dialog.note = dict(dialog.note or {})
            dialog.note["function_id"] = int(function_id)
        self.wait_window(dialog)
        if not dialog.result:
            return
        note_id = self.db.save_note(**dialog.result)
        self.selected_note_id = note_id
        self._set_status(f"笔记已保存（#{note_id}）。")
        self.show_view(VIEW_NOTE)
        self.refresh_nav()

    def edit_note(self):
        if not self.selected_note_id:
            self._set_status("先在列表里选一篇笔记。")
            return
        note = self.db.get_note(self.selected_note_id)
        if not note:
            return
        linked_name = ""
        if note.get("function_id"):
            item = self.db.get_function(note["function_id"])
            linked_name = item["code"] if item else ""
        dialog = ExcelNoteDialog(
            self, app_title=self.app_title, note=note, function_name=linked_name,
            image_preview_cls=self.image_preview_cls, images=self.images,
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        payload = dict(dialog.result)
        function_id = payload.pop("function_id", None)
        self.db.save_note(note_id=self.selected_note_id,
                          function_id=function_id, **payload)
        self._set_status("笔记已更新。")

    def delete_note(self):
        if not self.selected_note_id:
            self._set_status("先在列表里选一篇笔记。")
            return
        if not messagebox.askyesno(self.app_title, "确定删除这篇笔记？",
                                   parent=self):
            return
        if self.db.delete_note(self.selected_note_id):
            self._set_status("笔记已删除。")
            self.selected_note_id = None
            self.refresh_nav()

    def open_note_image_folder(self):
        if self.images is None:
            return
        try:
            folder = self.images.make_dir(NOTE_IMAGE_SUBDIR)
        except Exception:
            self._set_status("截图目录还创建不出来。")
            return
        import os
        try:
            os.startfile(str(folder))
            self._set_status(f"已打开截图目录：{folder}")
        except OSError:
            self._set_status(f"截图目录：{folder}")

    # ==================================================================
    # 视图 8：打卡统计
    # ==================================================================
    def render_stats(self):
        today = today_str()
        streak = self.db.streak(today=today)
        longest = self.db.longest_streak()
        totals = self.db.totals()
        overview = self.db.mastery_overview()
        self.title_var.set("打卡统计")
        self.meta_var.set(f"连续 {streak} 天 · 最长 {longest} 天 · "
                          f"累计学习 {totals['days']} 天")

        area = self.stats_area
        area.clear()
        host = area.inner

        metrics = tk.Frame(host, bg=self.palette.bg)
        metrics.pack(fill="x", anchor="w")
        for label, value in (
            ("连续打卡", f"{streak} 天"),
            ("最长连续", f"{longest} 天"),
            ("累计学习", f"{totals['days']} 天"),
            ("累计复习", f"{totals['reviewed']} 次"),
            ("累计时长", f"{totals['minutes']} 分钟"),
        ):
            cell = tk.Frame(metrics, bg=self.palette.surface, highlightthickness=1,
                            highlightbackground=self.palette.border_soft)
            cell.pack(side="left", padx=(0, 8))
            tk.Label(cell, text=value, bg=self.palette.surface,
                     fg=self.palette.text_primary,
                     font=TYPOGRAPHY.metric).pack(anchor="w", padx=12, pady=(8, 0))
            tk.Label(cell, text=label, bg=self.palette.surface,
                     fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(0, 8))

        # 总进度 + 掌握度分布
        card = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        card.pack(fill="x", anchor="w", pady=(12, 0))
        tk.Label(card, text=f"总进度：已学 {overview['learned']} / {overview['total']}"
                            f"（{overview['percent']}%），熟练 {overview['good']}",
                 bg=self.palette.surface, fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 6))
        _bar_row(card, "已学", f"{overview['learned']} 个",
                 overview["percent"] / 100, color=self.palette.accent,
                 palette=self.palette, label_width=8).pack(anchor="w", padx=12)
        for value, label in MASTERY_CHOICES:
            count = overview["buckets"].get(value, 0)
            ratio = count / overview["total"] if overview["total"] else 0
            _bar_row(card, label, f"{count} 个", ratio,
                     color=MASTERY_COLORS.get(value, self.palette.text_muted),
                     palette=self.palette, label_width=8).pack(
                anchor="w", padx=12, pady=(4, 0))
        tk.Label(card, text="掌握度只看「你自己标的」和「复习反馈」，不看时间也不看次数 —— "
                            "它衡量的是自信程度，不是努力程度。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(8, 10))

        # 最近 7 天
        week = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        week.pack(fill="x", anchor="w", pady=(12, 0))
        tk.Label(week, text="最近 7 天复习量", bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 6))
        activity = self.db.recent_activity(days=7, today=today)
        peak = max([row["reviewed"] for row in activity] + [1])
        for row in activity:
            text = f"{row['reviewed']} 个" if row["checked"] else "—"
            if row["minutes"]:
                text += f" / {row['minutes']} 分钟"
            _bar_row(week, row["label"], text, row["reviewed"] / peak,
                     color=self.palette.accent if row["checked"]
                     else self.palette.border_soft,
                     palette=self.palette, label_width=6).pack(
                anchor="w", padx=12, pady=(3, 0))
        tk.Label(week, text="最长的条形代表这 7 天里复习最多的那天。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(8, 10))

        # 打卡日历（最近 5 周，一行一周）
        # 只在「最近 7 天」里看连续天数太短，看不出坚持的形状；这里铺 35 格，
        # 「哪几天断了」一眼就看见。格数固定，不依赖控件宽度（避开首帧宽度坑）。
        # **行必须按周一对齐**：表头写的是「一二三四五六日」，行要是从
        # 「今天往前 35 天」切、那第一列就不是周一，表头等于在骗人。
        cal = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                       highlightbackground=self.palette.border_soft)
        cal.pack(fill="x", anchor="w", pady=(12, 0))
        tk.Label(cal, text="打卡日历（最近 5 周）", bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 6))
        marked = set(self.db.checkin_dates())
        anchor_day = parse_date(today) or date.today()
        this_monday = anchor_day - timedelta(days=anchor_day.isoweekday() - 1)
        grid_start = this_monday - timedelta(days=28)          # 含本周共 5 行
        head_row = tk.Frame(cal, bg=self.palette.surface)
        head_row.pack(anchor="w", padx=12)
        tk.Label(head_row, text="", width=6, bg=self.palette.surface).pack(side="left")
        for name in ("一", "二", "三", "四", "五", "六", "日"):
            tk.Label(head_row, text=name, width=3, bg=self.palette.surface,
                     fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(side="left", padx=1)
        for week_index in range(5):
            week_monday = grid_start + timedelta(days=week_index * 7)
            row = tk.Frame(cal, bg=self.palette.surface)
            row.pack(anchor="w", padx=12, pady=(2, 0))
            tk.Label(row, text=week_monday.strftime("%m/%d"), width=6,
                     bg=self.palette.surface, fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption, anchor="w").pack(side="left")
            for column in range(7):
                day = week_monday + timedelta(days=column)
                if day > anchor_day:
                    fill = self.palette.surface_alt          # 还没到的一天
                elif day.isoformat() in marked:
                    fill = self.palette.success
                else:
                    fill = self.palette.border_soft
                cell = tk.Frame(row, width=18, height=18, bg=fill,
                                highlightthickness=1,
                                highlightbackground=self.palette.border_soft)
                cell.pack(side="left", padx=1)
                cell.pack_propagate(False)
        tk.Label(cal, text="绿色 = 当天打了卡，最右边一列是周日；灰白格是还没到的日子。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(8, 10))

        # 分类掌握：雷达图 + 横向条，两张图同一份数据、问的是两个问题 ——
        # 条形回答「哪一类是多少」，雷达回答「整体形状缺哪一角」。
        # 12 个分类铺在圆周上，瘪进去的那一片一眼就看得出来，
        # 而横向条要逐行比长度才看得出来。
        heat_card = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                             highlightbackground=self.palette.border_soft)
        heat_card.pack(fill="x", anchor="w", pady=(12, 0))
        tk.Label(heat_card, text="复习热力图（最近 18 周）",
                 bg=self.palette.surface, fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 2))
        heat_data = self.db.heatmap()
        self._heatmap_chart(heat_card, heat_data).pack(
            anchor="w", padx=12, pady=(4, 0))
        heat_legend = tk.Frame(heat_card, bg=self.palette.surface)
        heat_legend.pack(anchor="w", padx=12, pady=(6, 0))
        tk.Label(heat_legend, text="少", bg=self.palette.surface,
                 fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(side="left", padx=(0, 4))
        for color in HEATMAP_COLORS:
            swatch = tk.Frame(heat_legend, width=11, height=11, bg=color)
            swatch.pack(side="left", padx=1)
            swatch.pack_propagate(False)
        tk.Label(heat_legend, text="多", bg=self.palette.surface,
                 fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(side="left", padx=(4, 0))
        tk.Label(heat_card,
                 text="一格一天，颜色越深当天复习得越多；灰白是还没到的日子。"
                      "看的是哪一阵子在练、哪一阵子荒了 —— 与上面的打卡日历"
                      "（只问「打了没」）是两个问题。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption, justify="left", anchor="w",
                 wraplength=700).pack(anchor="w", padx=12, pady=(6, 10))

        radar_card = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                              highlightbackground=self.palette.border_soft)
        radar_card.pack(fill="x", anchor="w", pady=(12, 0))
        tk.Label(radar_card, text="分类掌握雷达图（一眼看出短板）",
                 bg=self.palette.surface, fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 2))
        self._radar_chart(radar_card, self.db.category_stats()).pack(
            anchor="w", padx=12, pady=(4, 0))
        legend = tk.Frame(radar_card, bg=self.palette.surface)
        legend.pack(anchor="w", padx=12, pady=(4, 0))
        for color, text in ((self.palette.accent, "已学（掌握度 ≥ 生疏）"),
                            (self.palette.success, "熟练")):
            swatch = tk.Frame(legend, width=12, height=12, bg=color)
            swatch.pack(side="left", padx=(0, 4))
            swatch.pack_propagate(False)
            tk.Label(legend, text=text, bg=self.palette.surface,
                     fg=self.palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(side="left", padx=(0, 14))
        tk.Label(radar_card,
                 text="半径 = 该分类的比例；12 条轴等分圆周，从正上方开始顺时针。"
                      "某一类长期贴在圆心附近，就是那一片该补了。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption, justify="left", anchor="w",
                 wraplength=700).pack(anchor="w", padx=12, pady=(6, 10))

        # 分类掌握（准确数值；整体形状看上面的雷达图）
        cats = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                        highlightbackground=self.palette.border_soft)
        cats.pack(fill="x", anchor="w", pady=(12, 0))
        tk.Label(cats, text="各分类熟练度（一眼看出短板）", bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.section).pack(anchor="w", padx=12, pady=(10, 6))
        for item in self.db.category_stats():
            if not item["total"]:
                continue
            _bar_row(cats, item["name"], f"{item['good']} / {item['total']}",
                     item["good"] / item["total"], color=self.palette.success,
                     palette=self.palette, label_width=14).pack(
                anchor="w", padx=12, pady=(3, 0))
        tk.Label(cats, text="条形是「熟练 / 总数」。某一类条形长期很短，"
                            "说明那一片该补了。",
                 bg=self.palette.surface, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(anchor="w", padx=12, pady=(8, 10))

        # 手动打卡
        checkin_card = tk.Frame(host, bg=self.palette.surface, highlightthickness=1,
                                highlightbackground=self.palette.border_soft)
        checkin_card.pack(fill="x", anchor="w", pady=(12, 10))
        today_checkin = self.db.get_checkin(today) or {}
        state_text = "今天还没打卡。" if not today_checkin else (
            f"今天已打卡：复习 {today_checkin.get('reviewed', 0)} 个，"
            f"{today_checkin.get('minutes', 0)} 分钟。"
        )
        tk.Label(checkin_card, text=state_text, bg=self.palette.surface,
                 fg=self.palette.text_primary,
                 font=TYPOGRAPHY.body).pack(anchor="w", padx=12, pady=(10, 4))
        if today_checkin.get("note"):
            tk.Label(checkin_card, text="心得：" + today_checkin["note"],
                     bg=self.palette.surface, fg=self.palette.text_secondary,
                     font=TYPOGRAPHY.caption, justify="left", anchor="w",
                     wraplength=700).pack(anchor="w", padx=12)
        row = tk.Frame(checkin_card, bg=self.palette.surface)
        row.pack(fill="x", padx=12, pady=(6, 10))
        tk.Label(row, text="学习", bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        ttk.Entry(row, textvariable=self.checkin_minutes_var, width=5).pack(
            side="left", padx=4)
        tk.Label(row, text="分钟，心得", bg=self.palette.surface,
                 fg=self.palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        ttk.Entry(row, textvariable=self.checkin_note_var, width=40).pack(
            side="left", padx=4)
        ttk.Button(row, text="打卡 / 更新", command=self.checkin_today).pack(
            side="left", padx=4)

    def _heatmap_chart(self, parent, data):
        """复习热力图：**格子是量，不是有无** —— 看趋势用的。

        跨 18 周、列按周一对齐（行是周一..周日）。未来的日子画成空档，否则
        右下角一片深色会让人以为「最近没练」，其实那几天还没到。
        """
        step = HEATMAP_CELL + HEATMAP_GAP
        columns = data.get("columns") or []
        width = HEATMAP_LEFT + max(1, len(columns)) * step
        height = HEATMAP_TOP + 7 * step
        canvas = tk.Canvas(parent, width=width, height=height,
                           bg=self.palette.surface, highlightthickness=0, bd=0)
        for column_index, column in enumerate(columns):
            x = HEATMAP_LEFT + column_index * step
            for row_index, day in enumerate(column):
                y = HEATMAP_TOP + row_index * step
                if day.get("future"):
                    fill = self.palette.surface_alt
                    outline = self.palette.surface_alt
                else:
                    level = int(day.get("level", 0) or 0)
                    fill = HEATMAP_COLORS[min(level, len(HEATMAP_COLORS) - 1)]
                    outline = self.palette.border_soft
                canvas.create_rectangle(x, y, x + HEATMAP_CELL, y + HEATMAP_CELL,
                                        fill=fill, outline=outline)
        for column_index, label in data.get("months") or []:
            canvas.create_text(HEATMAP_LEFT + column_index * step, 2, text=label,
                               anchor="nw", fill=self.palette.text_muted,
                               font=TYPOGRAPHY.caption)
        return canvas

    def _radar_chart(self, parent, stats, *, radius=RADAR_RADIUS):
        """12 轴分类掌握雷达图。

        **固定尺寸 Canvas**，不参与自适应 —— 与条形图同一个理由：比例要按
        「画的时候」的控件宽度算，而首帧那个宽度是假的（1px），照它算必然画歪。
        把尺寸定死，整件事就绕开了。

        画**两层**多边形：外层是「已学率」，内层是「熟练率」。两个都看才有信息 ——
        只画熟练率的话，一整片「学过但没练熟」会干净得像没学。
        """
        import math
        canvas = tk.Canvas(parent, width=RADAR_WIDTH, height=RADAR_HEIGHT,
                           bg=self.palette.surface, highlightthickness=0, bd=0)
        items = [item for item in stats if item.get("total")]
        if len(items) < 3:
            canvas.create_text(RADAR_WIDTH / 2, RADAR_HEIGHT / 2,
                               text="分类太少，画不出雷达图（至少要 3 类）",
                               fill=self.palette.text_muted,
                               font=TYPOGRAPHY.caption)
            return canvas

        center_x, center_y = RADAR_WIDTH / 2, RADAR_HEIGHT / 2
        count = len(items)
        step = 2 * math.pi / count
        start = -math.pi / 2                       # 12 点钟方向起，顺时针铺

        def point(index, ratio):
            angle = start + step * index
            length = radius * max(0.0, min(1.0, float(ratio or 0)))
            return (center_x + length * math.cos(angle),
                    center_y + length * math.sin(angle))

        # 同心网格 + 轴线
        for ring in range(1, RADAR_RINGS + 1):
            points: list[float] = []
            for index in range(count):
                points.extend(point(index, ring / RADAR_RINGS))
            canvas.create_polygon(*points, outline=self.palette.border_soft,
                                  fill="", width=1)
        for index in range(count):
            x, y = point(index, 1.0)
            canvas.create_line(center_x, center_y, x, y,
                               fill=self.palette.border_soft)

        # 两层数据多边形。``stipple`` 让填充变成网点，两层叠着也看得见下面那层。
        for key, color in (("learned", self.palette.accent),
                           ("good", self.palette.success)):
            points = []
            for index, item in enumerate(items):
                points.extend(point(index, (item.get(key, 0) or 0)
                                    / (item.get("total") or 1)))
            canvas.create_polygon(*points, outline=color, fill=color,
                                  stipple="gray25", width=2)

        # 轴标签：跟着角度往圆外挪，靠右的贴左对齐、靠左的贴右对齐，
        # 免得「查找与引用」这种长名字压在别的标签上
        for index, item in enumerate(items):
            angle = start + step * index
            dx, dy = math.cos(angle), math.sin(angle)
            anchor = "w" if dx > 0.3 else ("e" if dx < -0.3 else "center")
            canvas.create_text(center_x + (radius + RADAR_LABEL_GAP) * dx,
                               center_y + (radius + RADAR_LABEL_GAP) * dy,
                               text=item["name"], anchor=anchor,
                               fill=self.palette.text_secondary,
                               font=TYPOGRAPHY.caption)
        return canvas

    # ==================================================================
    # 导出 / 维护
    # ==================================================================
    # ==================================================================
    # 批量导入 / 导出函数库
    # ==================================================================
    def _export_dir(self) -> str:
        """导出目录：与数据库同级（``exports/``），和学习进度导出落在一处。"""
        target = Path(str(self.db.db_path)).parent / "exports"
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    def open_export_folder(self):
        folder = self._export_dir()
        import os
        try:
            os.startfile(folder)
            self._set_status(f"已打开导出目录：{folder}")
        except OSError:
            self._set_status(f"导出目录：{folder}")

    def save_import_template(self):
        """把导入模板写到导出目录（Excel 双击就能打开）。"""
        target = Path(self._export_dir()) / "excel_import_template.csv"
        try:
            saved = self.db.write_import_template(target)
        except OSError as exc:
            self._set_status(f"写模板失败：{exc}")
            return
        self._set_status(f"模板已写到 {saved}（把那两行示例改掉再导入）。")

    def export_functions_markdown(self):
        """把整库导成 Markdown，顺带一份 HTML —— 打印要排版，md 没有。

        导完问一句「现在打印吗」：走系统里关联 HTML 的程序（浏览器）。
        打印失败不打扰 —— 文件已经落盘了，让用户自己打开就行。
        """
        import os
        today = today_str()
        target_dir = os.path.join(
            os.path.dirname(os.path.abspath(self.db.db_path)), "exports")
        os.makedirs(target_dir, exist_ok=True)
        md_path = os.path.join(target_dir, f"excel_functions_{today}.md")
        try:
            count = self.db.export_functions_markdown(md_path)
        except OSError as exc:
            self._set_status(f"导出失败：{exc}")
            return
        html_path = md_path[:-3] + ".html"
        try:
            with open(md_path, encoding="utf-8") as handle:
                content = handle.read()
            with open(html_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(markdown_to_html(
                    content, title=f"Excel 函数库（{today}）"))
        except OSError:
            html_path = ""
        self._set_status(f"已导出 {count} 个函数到 {md_path}。")
        if html_path and messagebox.askyesno(
                "导出完成",
                f"已导出 {count} 个函数。\n\n现在打印吗？\n"
                f"（不想打印就打开 {os.path.basename(md_path)} 自己看）"):
            if not print_document(html_path):
                self._set_status("没能调起打印，文件已经导出好了，可自行打开。")

    def export_functions_csv(self):
        """把整库导成 CSV：等于一份「我的函数库」备份，也能改完再导回来。"""
        target = Path(self._export_dir()) / f"excel_functions_{today_str()}.csv"
        try:
            count = self.db.export_functions_csv(target)
        except OSError as exc:
            self._set_status(f"导出失败：{exc}")
            return
        self._set_status(f"已导出 {count} 个函数到 {target}。")

    def import_functions_dialog(self):
        """挑一个 CSV / Excel 文件批量导入。

        先 ``dry_run`` 跑一遍，把「会新增几条 / 更新几条 / 跳过几条 / 几行有问题」
        报给你确认了才真写 —— 批量写库之前必须让人先看到规模。
        """
        path = filedialog.askopenfilename(
            parent=self,
            title="选一个 CSV 或 Excel 文件",
            filetypes=[("CSV / Excel", "*.csv *.tsv *.txt *.xlsx *.xlsm"),
                       ("所有文件", "*.*")])
        if not path:
            return
        try:
            rows = parse_import_file(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror(self.app_title, f"读不了这个文件：{exc}", parent=self)
            return
        if not rows:
            messagebox.showinfo(self.app_title,
                                "文件里没读到数据行（第一行要当表头）。", parent=self)
            return

        overwrite = False
        preview = self.db.import_functions(rows, dry_run=True)
        if preview["skipped"]:
            overwrite = messagebox.askyesno(
                self.app_title,
                f"其中有 {len(preview['skipped'])} 条和库里的内置函数重名。\n\n"
                "「是」＝连内置的一起改写（只写文件里非空的字段，"
                "你的书页码 / 心得不会丢）；\n"
                "「否」＝保留内置的，只导入新函数。",
                parent=self)
            preview = self.db.import_functions(rows, overwrite_builtin=overwrite,
                                               dry_run=True)
        if not messagebox.askyesno(self.app_title,
                                   self._import_preview_text(preview, path),
                                   parent=self):
            self._set_status("已取消导入，什么都没动。")
            return

        result = self.db.import_functions(rows, overwrite_builtin=overwrite)
        self.selected_function_id = None
        self.show_view(VIEW_LIBRARY)
        self.refresh_nav()
        self._report_import(result, path)

    @staticmethod
    def _import_preview_text(result, path) -> str:
        lines = [f"文件：{Path(path).name}", "",
                 f"新增 {len(result['added'])} 条",
                 f"更新 {len(result['updated'])} 条",
                 f"跳过 {len(result['skipped'])} 条"]
        if result["warnings"]:
            lines.append(f"提示 {len(result['warnings'])} 条")
        if result["errors"]:
            lines.append(f"有问题 {len(result['errors'])} 行（这些不会导进去）")
        lines += ["", "新增的都是「自建函数」（可以删）。继续吗？"]
        return "\n".join(lines)

    def _report_import(self, result, path):
        lines = [f"已从「{Path(path).name}」导入："
                 f"新增 {len(result['added'])}、更新 {len(result['updated'])}、"
                 f"跳过 {len(result['skipped'])}。"]
        if result["added"]:
            names = "、".join(result["added"][:12])
            lines += ["", "新增：" + names + ("…" if len(result["added"]) > 12 else "")]
        if result["warnings"]:
            lines.append("")
            lines += [f"提示：{item['message']}（{item['code']}）"
                      for item in result["warnings"][:5]]
        if result["errors"]:
            lines.append("")
            lines.append("这几行没导进去：")
            lines += [f"第 {item['row']} 行 {item['code']}：{item['message']}"
                      for item in result["errors"][:8]]
            if len(result["errors"]) > 8:
                lines.append(f"（还有 {len(result['errors']) - 8} 行，"
                             "先修前几条再导一次。）")
        show = messagebox.showwarning if result["errors"] else messagebox.showinfo
        show(self.app_title, "\n".join(lines), parent=self)
        self._set_status(f"导入完成：新增 {len(result['added'])}、"
                         f"更新 {len(result['updated'])}、"
                         f"跳过 {len(result['skipped'])}、"
                         f"错误 {len(result['errors'])}。")

    def export_progress(self):
        """把学习进度导成 Markdown，可直接贴进笔记或打印。"""
        import os
        today = today_str()
        lines = [f"# Excel 学习进度（{today}）", ""]
        overview = self.db.mastery_overview()
        totals = self.db.totals()
        lines.append(f"- 函数库：{overview['total']} 个，已学 {overview['learned']} 个，"
                     f"熟练 {overview['good']} 个")
        lines.append(f"- 连续打卡：{self.db.streak()} 天（最长 {self.db.longest_streak()} 天）")
        lines.append(f"- 累计：学习 {totals['days']} 天 / 复习 {totals['reviewed']} 次 / "
                     f"{totals['minutes']} 分钟")
        lines.append("")
        lines.append("## 各阶段进度")
        lines.append("")
        lines.append("| 阶段 | 熟练 | 已学 | 总数 |")
        lines.append("| --- | --- | --- | --- |")
        for stage in self.db.learning_progress():
            if stage["is_recipe_stage"]:
                lines.append(f"| {stage['key']} {stage['title']} | — | — | 20 条配方 |")
            else:
                lines.append(f"| {stage['key']} {stage['title']} | {stage['good']} | "
                             f"{stage['learned']} | {stage['total']} |")
        lines.append("")
        lines.append("## 还没掌握的（掌握度 ≤ 生疏）")
        lines.append("")
        progress = self.db.progress_map()
        pending = [
            item for item in self.db.all_functions()
            if int((progress.get(item["id"]) or {}).get("mastery", 0) or 0) <= MASTERY_WEAK
        ]
        for item in pending[:200]:
            page = f"（书页 {item['book_page']}）" if item.get("book_page") else ""
            lines.append(f"- **{item['code']}** {item.get('name_cn', '')}"
                         f"{page} —— {item.get('description', '')}")
        lines.append("")
        content = "\n".join(lines)
        try:
            target_dir = os.path.join(os.path.dirname(os.path.abspath(self.db.db_path)),
                                      "exports")
            os.makedirs(target_dir, exist_ok=True)
            path = os.path.join(target_dir, f"excel_progress_{today}.md")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        except OSError:
            self.copy_to_clipboard(content)
            self._set_status("写文件失败，已经把进度复制到剪贴板。")
            return
        self.copy_to_clipboard(content)
        self._set_status(f"进度已导出到 {path}（同时复制到剪贴板）。")

    def reseed_functions(self):
        """补种：把新版本新增的函数补进来，**不动你的书页码 / 笔记 / 掌握度**。"""
        from excel_db import seed_excel_data
        try:
            counts = seed_excel_data(self.db.conn)
        except Exception as exc:
            messagebox.showerror(self.app_title, f"重建种子失败：{exc}", parent=self)
            return
        self._set_status(f"函数库已对齐到内置版本：内置 {counts['functions']} 个函数、"
                         f"{counts['recipes']} 条配方（你的书页码与进度都没动）。")
        self.refresh()

    # ==================================================================
    # 通用
    # ==================================================================
    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(str(text or ""))
            self._set_status("已复制到剪贴板。")
        except tk.TclError:
            self._set_status("复制失败：剪贴板被别的程序占用了。")

    def copy_function_markdown(self, item: dict):
        lines = [f"# {item['code']} {item.get('name_cn', '')}", ""]
        if item.get("category"):
            lines.append(f"- 分类：{item['category']}")
        if item.get("min_version"):
            lines.append(f"- 最低版本：{item['min_version']}")
        if item.get("book_page"):
            lines.append(f"- 书页：{item['book_page']}")
        lines.append("")
        for title, key in (("一句话", "description"), ("语法", "syntax"),
                           ("参数", "args_desc"), ("返回值", "returns"),
                           ("示例", "example_formula"), ("示例结果", "example_result"),
                           ("易错点", "pitfalls"), ("适用场景", "use_cases"),
                           ("相关函数", "related"), ("我的理解", "my_note")):
            value = str(item.get(key, "") or "").strip()
            if value:
                lines += [f"## {title}", "", value, ""]
        self.copy_to_clipboard("\n".join(lines))

    def _set_status(self, message: str):
        self.status_var.set(message)
        if self.on_status:
            try:
                self.on_status(message)
            except Exception:
                pass


class _TextPrompt(tk.Toplevel):
    """一个极简的多行文本输入框（给「写点心得」用）。``result`` 为 None 表示取消。"""

    def __init__(self, master, *, title: str, initial: str = "", app_title: str = ""):
        super().__init__(master)
        self.title(title)
        self.app_title = app_title
        self.result: str | None = None
        body = ttk.Frame(self, padding=(16, 14))
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, width=64, height=10, wrap="word",
                            bg=MAIN_PALETTE.surface_alt,
                            fg=MAIN_PALETTE.text_primary, relief="flat",
                            highlightthickness=1,
                            highlightbackground=MAIN_PALETTE.border_soft)
        self.text.insert("1.0", initial or "")
        self.text.pack(fill="both", expand=True)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="保存", style="Primary.TButton",
                   command=self._save).pack(side="right", padx=4)
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.text.focus_set()

    def _save(self):
        self.result = self.text.get("1.0", "end").strip()
        self.destroy()
