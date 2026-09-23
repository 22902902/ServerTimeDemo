# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 界面层
================================================================================
``ExcelLearningPage(ttk.Frame)``：由 ``main`` 建一次，之后靠 pack / pack_forget 切换，
与 ``TodoPage`` / ``ProcessPage`` 同一套约定。数据全部来自注入的 ``ExcelDB``。
**本模块不 import main** —— 图片路径解析这类依赖 ``BASE_DIR`` 的能力，
通过 ``ExcelImageTools`` 适配器注入（与流程中心的做法一致，避免循环依赖）。

六个视图
--------------------------------------------------------------------------------
今日复习 / 函数宝典 / 学习路径 / 实战配方 / 学习笔记 / 打卡统计

两处对设计文档的调整，写在这里免得后面看着奇怪
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
"""

from __future__ import annotations

import re
import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, simpledialog, ttk

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
    difficulty_label,
    importance_label,
    mastery_label,
    parse_date,
    split_codes,
    today_str,
)
from excel_seed import CATEGORIES
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
VIEW_PATH = "path"
VIEW_RECIPE = "recipe"
VIEW_NOTE = "note"
VIEW_STATS = "stats"
VIEW_CHOICES = (
    (VIEW_DUE, "今日复习"),
    (VIEW_LIBRARY, "函数宝典"),
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
_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)


def _plain(text) -> str:
    """把种子正文里的 ``**强调**`` 去掉标记再上屏。

    为什么不做成真加粗：Tk 的 Label 不支持富文本，只是「一段折行文字」，
    要真加粗就得换成只读 Text 并自己算高度 —— 而这段文字是**按宽度折行**的，
    高度依赖当时的控件宽度，会掉进「首帧控件宽度报 1、按它算必然错」那个
    老坑（本项目为此返工过多次）。权衡：去掉标记让正文干净，比为了一处加粗
    引入一个会抖的控件划算。种子里留着 ``**`` 是因为导出 Markdown 时要它。

    ``_field`` / 卡片正文都过这一道，所以只有**置中**的强调会被去掉；
    落到小标题（例如「易错点（最值钱的一栏）」）上的加粗本来就靠颜色区分。
    """
    return _INLINE_BOLD_RE.sub(r"\1", str(text or ""))


def _badge(parent, text: str, *, fg: str, bg: str = "", palette=MAIN_PALETTE,
           font=None):
    """小徽标：色块 + 文字。用于掌握度、难度、分类。"""
    return tk.Label(
        parent, text=f" {text} ", fg=fg, bg=bg or palette.surface_alt,
        font=font or TYPOGRAPHY.badge, padx=3, pady=1,
    )


def _mono_block(parent, text: str, *, palette=MAIN_PALETTE, on_copy=None,
                height_lines=None, copy_text=None):
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
    body.configure(state="disabled")
    if on_copy:
        body.bind("<Control-c>", lambda e: on_copy(
            copy_text if copy_text is not None else text) or "break")
    body.pack(fill="x", padx=8, pady=(2, 6))
    return holder


def _field(parent, title: str, text: str, *, palette=MAIN_PALETTE,
           fg=None, font=None, mono=False):
    """「小标题 + 正文」的成对展示块。空文本直接不渲染（返回 None）。"""
    text = _plain(text).strip()
    if not text:
        return None
    block = tk.Frame(parent, bg=palette.surface)
    tk.Label(block, text=title, bg=palette.surface, fg=palette.text_muted,
             font=TYPOGRAPHY.caption, anchor="w").pack(anchor="w")
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
                 palette=MAIN_PALETTE, typography=TYPOGRAPHY):
        super().__init__(master)
        self.db = db
        self.app_title = app_title
        self.image_preview_cls = image_preview_cls
        self.images = images
        self.on_status = on_status
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
                "---",
                ("手动打卡", self.checkin_today),
                ("重建函数库种子（不清进度）", self.reseed_functions),
                "---",
                ("打开截图目录", self.open_note_image_folder),
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

        # 搜索 / 筛选行：只在需要它的视图里出现
        self.filter_row = ttk.Frame(parent)
        ttk.Label(self.filter_row, text="搜索").pack(side="left")
        entry = ttk.Entry(self.filter_row, textvariable=self.search_var, width=22)
        entry.pack(side="left", padx=(6, 4))
        entry.bind("<Return>", lambda e: self.render_current_view())
        ttk.Button(self.filter_row, text="查", width=3,
                   command=self.render_current_view).pack(side="left")
        self.category_box = ttk.Combobox(
            self.filter_row, textvariable=self.category_var, state="readonly", width=14,
            values=["全部分类"] + [item["name"] for item in CATEGORIES],
        )
        self.category_box.pack(side="left", padx=(10, 0))
        self.category_box.bind("<<ComboboxSelected>>", lambda e: self.render_current_view())
        self.mastery_box = ttk.Combobox(
            self.filter_row, textvariable=self.mastery_var, state="readonly", width=12,
            values=[label for label, _ in MASTERY_FILTER_CHOICES],
        )
        self.mastery_box.pack(side="left", padx=(6, 0))
        self.mastery_box.bind("<<ComboboxSelected>>", lambda e: self.render_current_view())

        # 一行提示：告诉用户当前视图的筛选是「按什么筛」，省得靠猜
        self.filter_hint_var = tk.StringVar()
        tk.Label(self.filter_row, textvariable=self.filter_hint_var,
                 bg=self.palette.bg, fg=self.palette.text_muted,
                 font=TYPOGRAPHY.caption).pack(side="left", padx=(12, 0))

        self.body_host = ttk.Frame(parent)
        self.body_host.pack(fill="both", expand=True, pady=(10, 0))

        # 六个视图帧建一次，切换时只 pack / pack_forget（保住滚动位置与选中状态）
        self.view_frames: dict[str, ttk.Frame] = {}
        for key, _label in VIEW_CHOICES:
            self.view_frames[key] = ttk.Frame(self.body_host)
        self._build_due_view()
        self._build_library_view()
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

    # -- 视图 3：学习路径 ------------------------------------------------
    def _build_path_view(self):
        frame = self.view_frames[VIEW_PATH]
        self.path_area = ScrollArea(frame, bg=self.palette.bg, inner_bg=self.palette.bg,
                                    autohide_scrollbar=True)
        self.path_area.pack(fill="both", expand=True)

    # -- 视图 4：实战配方 ------------------------------------------------
    def _build_recipe_view(self):
        frame = self.view_frames[VIEW_RECIPE]
        self.recipe_area = ScrollArea(frame, bg=self.palette.bg,
                                      inner_bg=self.palette.bg,
                                      autohide_scrollbar=True)
        self.recipe_area.pack(fill="both", expand=True)

    # -- 视图 5：学习笔记 ------------------------------------------------
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

    # -- 视图 6：打卡统计 ------------------------------------------------
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
        """重建左栏（视图 6 项 + 分类 12 项）。数很重，整表重建比增量省心。

        收尾**必须**落到一个明确的选区状态 —— 见下面那段注释，这是踩过的坑。
        """
        tree = self.nav_tree
        selection = tree.selection()
        for iid in tree.get_children(""):
            tree.delete(iid)
        tree.insert("", "end", iid="g::views", text="学习视图", open=True,
                    values=("",))
        counts = {
            VIEW_DUE: str(self.db.due_count()) or "0",
            VIEW_LIBRARY: str(self.db.count_functions()),
            VIEW_PATH: str(len(self.db.learning_progress())),
            VIEW_RECIPE: str(len(self.db.all_recipes())),
            VIEW_NOTE: str(self.db.note_count()),
            VIEW_STATS: str(self.db.streak()),
        }
        for key, label in VIEW_CHOICES:
            suffix = " 天" if key == VIEW_STATS else ""
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

        踩过的坑：这条筛选行原先对三个视图是**同一套**控件，于是配方视图里
        那个分类下拉「摆了但选什么都不筛」—— 控件在那儿却不生效，
        比没有更让人困惑。笔记视图则是「掌握度」根本无从谈起。
        """
        if key not in (VIEW_LIBRARY, VIEW_RECIPE, VIEW_NOTE):
            self.filter_row.pack_forget()
            return

        show_category = key in (VIEW_LIBRARY, VIEW_RECIPE)
        if key == VIEW_LIBRARY:
            values = ["全部分类"] + [item["name"] for item in CATEGORIES]
        elif key == VIEW_RECIPE:
            values = ["全部分类"] + self.db.recipe_categories()
        else:
            values = ["全部分类"]
        if show_category:
            self.category_box.configure(values=values)
            # 换视图后旧选中值可能不在新候选里（例如从配方的「统计」切到笔记）
            if self.category_var.get() not in values:
                self.category_var.set("全部分类")
        else:
            self.category_var.set("全部分类")

        if show_category:
            self.category_box.pack(side="left", padx=(10, 0))
        else:
            self.category_box.pack_forget()
        if key == VIEW_LIBRARY:
            self.mastery_box.pack(side="left", padx=(6, 0))
        else:
            self.mastery_box.pack_forget()

        hint = {"library": "按分类 / 掌握度筛，或直接搜场景词",
                "recipe": "按主题筛，或搜场景词（工期 / 月供 / 去重）",
                "note": "搜标题 / 正文 / 标签 / 书页码"}.get(key, "")
        self.filter_hint_var.set(hint)
        self.filter_row.pack(fill="x", pady=(10, 0), before=self.body_host)

    def render_current_view(self):
        for child in self.head_actions.winfo_children():
            child.destroy()
        renderer = {
            VIEW_DUE: self.render_due,
            VIEW_LIBRARY: self.render_library,
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
                            on_copy=self.copy_to_clipboard, height_lines=2)
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
                                  on_copy=self.copy_to_clipboard, height_lines=3)
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
    # 视图 3：学习路径
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
    # 视图 4：实战配方
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
    # 视图 5：学习笔记
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
    # 视图 6：打卡统计
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

        # 分类掌握
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

    # ==================================================================
    # 导出 / 维护
    # ==================================================================
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
