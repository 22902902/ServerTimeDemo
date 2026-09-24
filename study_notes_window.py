# -*- coding: utf-8 -*-
"""
================================================================================
学习笔记主窗口
================================================================================
视频课程资料库的核心窗口，整合以下三大功能区域：

┌──────────────────┬────────────────────────────────────────────────────────┐
│   左侧分类树      │   右侧主区域                                             │
│  （280px 固定宽度）│                                                        │
│                  ├────────────────────────────────────────────────────────┤
│  📂 笔记分类      │  工具栏：[新增笔记] [编辑] [删除]  🔍搜索  标签过滤       │
│                  ├────────────────────────────────────────────────────────┤
│  ├─ 01 技术      │  笔记列表（表格）                                        │
│  │  ├─ 0101     │  ID │  标题  │  分类  │  标签  │  来源  │  更新时间      │
│  │  └─ 0102     │  1  │ Python│ 01技术│ Python │ [1] XX │ 2026-07-14     │
│  ├─ 02 烹饪     │  2  │ ...   │ ...   │ ...    │ ...   │ ...            │
│  └─ 03 健身     ├────────────────────────────────────────────────────────┤
│                  │  笔记预览区（Markdown 渲染文本 + 来源信息）               │
│  [+ 新分类]      │  # 标题                                                 │
│  [新增] [编辑]   │  分类：01 技术 / 0101 编程语言                           │
│  [删除]          │  标签：Python 进阶                                      │
│                  │  ──────────────────────                                 │
│  [网盘]          │  📦 来源：[1] Python 进阶完整版                         │
│                  │  🔗 链接：https://pan.baidu.com/...                     │
│                  │  正文内容...                                             │
└──────────────────┴────────────────────────────────────────────────────────┘

编辑器（NoteEditorDialog）特性：
  ✓ Markdown 原生编辑（等宽字体），并且把 Markdown 标记淡化显示 ——
    源码还在，但一眼能看出哪是标题、哪是列表，正文不再被 `#` `**` 淹没
  ✓ 格式工具栏：样式下拉 + 行内格式 + 块元素，选中文字点按钮即包裹，
    不打选中就作用于光标所在行（对齐 Word 的使用习惯）
  ✓ Ctrl+V 粘贴截图 → 自动保存为 PNG → 插入 Markdown 图片语法
  ✓ 渲染预览（Typora 风格）、浏览器预览（Markdown → HTML）
  ✓ 语法速查：按钮悬停看写法，或点「语法速查」看整张对照表
  ✓ 笔记可关联百度网盘资料来源

排版说明
------------------------------------------------------------------------------
两处预览（编辑器右侧的「渲染预览」、笔记页底部的「笔记预览」）统一走
markdown_view.py，共用同一份渲染实现 —— 旧版是各写一套，于是同一篇笔记
在编辑器里有排版、在页面里却是源码。

作者：代可行
日期：2026-07-14
================================================================================
"""

import io
import re
import tempfile
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

import markdown_view
from markdown_view import FONT_FAMILY, MONO_FAMILY
from study_notes_db import StudyNotesDB, StudyCategory
from baidu_disk_window import BaiduDiskWindow
from dialog_form_style import apply_dialog_form_style
from page_components import create_menu_button
from ui_components import HoverTooltip
from ui_theme import MAIN_PALETTE as PALETTE

# ── 编辑区「源码淡化」用的模式 ──────────────────────────────────────────────
# 只淡化**结构性前缀**（行首的 # / > / - / 1. / ``` ）与成对的行内标记，
# 不动文字本身。行首锚定是关键：`- ` 出现在句中（如 a - b）不该被淡化。
_LINE_MARK_PATTERNS = (
    re.compile(r"^\s{0,3}#{1,6}(?=\s)"),                 # 标题
    re.compile(r"^\s{0,3}>\s?"),                          # 引用
    re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s?"),              # 任务列表
    re.compile(r"^\s*[-*+]\s+"),                          # 无序列表
    re.compile(r"^\s*\d+[.)]\s+"),                        # 有序列表
    re.compile(r"^\s*(?:`{3,}|~{3,})[\w+#.\-]*\s*$"),     # 围栏
    re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$"),        # 分隔线
)
# 行内标记：不区分开闭，把符号本身染浅即可 —— 目的是让文字跳出来，
# 不是把配对关系画给你看。`*` 用否定环视避免吃掉 `**` 的两个字符。
_INLINE_MARK_RE = re.compile(r"\*\*|~~|(?<!\*)\*(?!\*)|`+")

# 单篇笔记超过这个长度就不做源码淡化：每敲一个字都要全文重扫一遍，
# 几万字的文档会开始卡。淡化是锦上添花，不值得拿输入流畅度换。
_DIM_MAX_CHARS = 60000


# =============================================================================
# 语法速查表
# =============================================================================

# 左边怎么写、右边什么效果。语法速查窗口直接渲染这张表 —— 文案和工具栏按钮的
# 悬停提示分开维护：提示只讲一句，表里可以讲清边界（比如代码块怎么收尾）。
_SYNTAX_HELP = (
    ("标题", (
        ("# 一级标题", "H1。工具栏「样式」里能一键切，不用手敲 #"),
        ("## 二级标题", "H2。H1/H2 在预览里带下划线，和 Typora 一致"),
        ("### 三级标题", "H3 及以下没有下划线"),
        ("#### 四级标题", "H4"),
        ("##### 五级标题", "H5，字色降一级"),
        ("###### 六级标题", "H6，最弱一级"),
    )),
    ("行内格式", (
        ("**文字**", "加粗"),
        ("*文字*", "斜体"),
        ("~~文字~~", "删除线"),
        ("`代码`", "行内代码，浅灰底 + 等宽字体"),
    )),
    ("列表与块", (
        ("- 文字", "无序列表。要嵌套就多缩进两个空格"),
        ("1. 文字", "有序列表，序号自动排"),
        ("- [ ] 文字", "待办事项（未完成）"),
        ("- [x] 文字", "待办事项（已完成）"),
        ("> 文字", "引用块，左侧显示竖线"),
        ("---", "分隔线，必须独占一行"),
        ("```python", "代码块开始；内容写完再顶格敲一次三个反引号收尾"),
    )),
    ("插入", (
        ("[文字](https://…)", "链接"),
        ("![说明](图片路径)", "图片。Ctrl+V 粘贴截图会自动生成这一行"),
    )),
)


# =============================================================================
# 工具函数
# =============================================================================

def _center_over_parent(window, parent) -> None:
    """
    把弹窗摆到父窗口中央。

    Tk 默认把 Toplevel 放在父窗口左上角附近，尺寸一大就看着像没对齐；
    这里统一收口，免得每个弹窗各写一遍。
    """
    try:
        window.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - window.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - window.winfo_height()) // 3)
        window.geometry(f"+{x}+{y}")
    except Exception:
        pass

def _norm(text) -> str:
    """
    将任意值规范化为非空字符串（统一去空格、None 防护）。
    """
    if text is None:
        return ""
    return str(text).strip()


def _now() -> str:
    """
    返回当前时间 ISO 字符串（精确到秒），用于记录时间戳。
    """
    return datetime.now().isoformat(timespec="seconds")


# =============================================================================
# 分类管理对话框
# =============================================================================

class CategoryEditDialog(tk.Toplevel):
    """
    新增 / 编辑分类的通用对话框（改用 Toplevel 避免 simpledialog 兼容问题）。

    表单字段：
        分类名称（必填）
        排序号（整数，越小越靠前，默认为 0）

    使用方式：
        dlg = CategoryEditDialog(parent, "新增分类", parent_code="01", level=2, initial={"name": "编程语言", "sort_order": 1})
        parent.wait_window(dlg)
        if dlg.result:
            db.add_category(code="0106", name=dlg.result["name"], ...)
    """

    def __init__(self, parent, title: str, parent_code: str = "", level: int = 1,
                 initial: dict | None = None):
        """
        参数:
            parent      - 父窗口
            title       - 对话框标题
            parent_code - 父级分类编码（用于提示当前在哪个分类下新增）
            level       - 当前层级（1/2/3/4，由调用方控制，最多四级）
            initial     - 预填数据（编辑模式时传入）
        """
        super().__init__(parent)
        self.title(title)
        self.parent_code = parent_code
        self.level = level
        self.initial = initial or {}
        self.result = None
        
        # 模态对话框设置
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        self._build_ui()
        self._center_on_parent()
        
        # 绑定回车键确认
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        """构建表单：分类名称 + 排序号 + 按钮。"""
        # 主容器
        main = ttk.Frame(self, padding="16")
        main.grid(row=0, column=0, sticky="nsew")
        
        # 父分类提示
        if self.parent_code:
            hint = f"在 {self.parent_code} 下新增子分类（第{self.level}级）"
        else:
            hint = f"新增顶级分类（第{self.level}级）"
        ttk.Label(main, text=hint, foreground="gray").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        
        # 分类名称
        ttk.Label(main, text="分类名称:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        self.name_entry = ttk.Entry(main, width=36)
        self.name_entry.grid(row=1, column=1, sticky="ew", pady=6)
        self.name_entry.insert(0, self.initial.get("name", ""))
        
        # 排序号
        ttk.Label(main, text="排序号:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        self.sort_entry = ttk.Entry(main, width=36)
        self.sort_entry.grid(row=2, column=1, sticky="ew", pady=6)
        self.sort_entry.insert(0, str(self.initial.get("sort_order", 0)))
        
        # 按钮区
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(16, 0))
        
        ttk.Button(btn_frame, text="确定", command=self._on_ok).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=4)
        
        # 聚焦
        self.name_entry.focus()
        self.name_entry.select_range(0, "end")

    def _center_on_parent(self):
        """居中显示在父窗口上。"""
        _center_over_parent(self, self.master)

    def _on_ok(self):
        """点击确定：校验并保存结果。"""
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("分类管理", "分类名称不能为空。", parent=self)
            return
        
        try:
            sort_order = int(self.sort_entry.get().strip() or "0")
        except ValueError:
            sort_order = 0
        
        self.result = {
            "name": name,
            "sort_order": sort_order,
        }
        self.destroy()


# =============================================================================
# 笔记编辑器对话框
# =============================================================================

class NoteEditorDialog(tk.Toplevel):
    """
    笔记编辑对话框，支持完整 Markdown 书写体验。

    主要功能：
      1. 元信息编辑：标题 / 分类 / 标签 / 来源（网盘资料）
      2. Markdown 正文编辑（Consolas 等宽字体，适合代码）
      3. Ctrl+V 粘贴截图（自动保存 + Markdown img 语法插入）
      4. 快捷插入：图片路径、分隔线、代码块
      5. 浏览器预览（内置 HTML 渲染）

    数据流：
        打开 → 从 db 加载现有笔记（或空白） → 用户编辑 →
        保存 → 写入 db → 通知父窗口刷新列表

    截图存储位置：
        {数据库所在目录}/study_notes_images/{note_id}/*.png
        note_id 为 0 时（新建笔记）临时存到 new/ 子目录，保存后重新整理。
    """

    def __init__(self, parent, db: StudyNotesDB, note_id: int = 0,
                 default_category_code: str = ""):
        """
        参数:
            parent                - 父窗口（StudyNotesWindow）
            db                    - StudyNotesDB 数据库实例
            note_id               - 0=新增模式，>0=编辑已有笔记
            default_category_code - 新增笔记时默认选中的分类编码
        """
        super().__init__(parent)
        self.parent_window = parent
        self.db = db
        self.note_id = note_id
        self.default_category_code = default_category_code
        self.changed = False               # 标记内容是否被修改（用于关闭时提示）
        self._current_note_id = note_id   # 保存后更新（新建笔记保存后获得真实 ID）

        # 建立截图存储目录（{db目录}/study_notes_images/{note_id}/）
        self.note_dir = Path(db.db_path).parent / "study_notes_images"
        self.note_dir.mkdir(exist_ok=True)

        # 加载已有笔记数据
        self._load_existing()

        self.title("笔记编辑" if note_id else "新增笔记")
        self.geometry("1180x760")
        self.minsize(900, 560)
        self.transient(parent)   # 模态窗口
        self.grab_set()          # 焦点捕获
        # 统一底色 / 输入框 / 窗口图标。不套的话弹窗是系统灰底 + Tk 默认羽毛图标，
        # 跟主窗口的品牌标记对不上。
        apply_dialog_form_style(self, PALETTE, style_prefix="NoteEditor")
        self._dim_after = None   # 源码淡化的防抖句柄

        self.build_ui()
        self._populate()
        self._save_original_values()  # 保存原始值，用于关闭时判断是否真的修改了
        self._dim_marks()             # 打开就把已加载内容的 Markdown 标记淡化

        # 窗口关闭时询问是否放弃未保存内容
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 数据加载 ───────────────────────────────────────────────────────────────

    def _load_existing(self):
        """
        如果 note_id > 0，从数据库加载已有笔记数据。
        新增模式下 self._note = None。
        """
        if self.note_id:
            note = self.db.get_note(self.note_id)
            if note:
                self._note = note
                return
        self._note = None

    # ── UI 构建 ───────────────────────────────────────────────────────────────

    def build_ui(self):
        """
        构建编辑器 UI，从上到下分五块：

          1. 元信息行   标题 / 分类 / 标签 / 来源
          2. 格式工具栏 「样式」下拉 + 行内格式 + 块元素 —— 像 Word 那样点按钮
          3. 编辑区     等宽字体的 Markdown 源码，标记符号淡化显示
          4. 渲染预览   点「显示效果」后出现在右侧（Typora 风格）
          5. 底部按钮栏 显示效果 / 浏览器预览 / 语法速查 / 取消 / 保存
        """

        # ── 1. 元信息行 ───────────────────────────────────────────────────────
        meta_frame = ttk.Frame(self, padding=(12, 10, 12, 4), style="NoteEditor.TFrame")
        meta_frame.pack(fill="x")

        # 标题输入框
        ttk.Label(meta_frame, text="标题:", style="NoteEditor.TLabel").pack(side="left", padx=(0, 4))
        self.title_var = tk.StringVar()
        ttk.Entry(meta_frame, textvariable=self.title_var, width=34,
                  style="NoteEditor.TEntry").pack(side="left", padx=(0, 12))

        # 分类下拉框（readonly，不可手动输入，保证编码一致性）
        ttk.Label(meta_frame, text="分类:", style="NoteEditor.TLabel").pack(side="left", padx=(0, 4))
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(
            meta_frame, textvariable=self.category_var, state="readonly",
            width=26, style="NoteEditor.TCombobox",
        )
        self.category_combo.pack(side="left", padx=(0, 12))
        self._fill_category_combo()  # 填充分类选项

        # 标签输入框（空格分隔）
        ttk.Label(meta_frame, text="标签:", style="NoteEditor.TLabel").pack(side="left", padx=(0, 4))
        self.tags_var = tk.StringVar()
        ttk.Entry(meta_frame, textvariable=self.tags_var, width=22,
                  style="NoteEditor.TEntry").pack(side="left", padx=(0, 12))

        # 来源下拉框（关联百度网盘资料）
        ttk.Label(meta_frame, text="来源:", style="NoteEditor.TLabel").pack(side="left", padx=(0, 4))
        self.source_var = tk.StringVar(value="")
        self.source_combo = ttk.Combobox(meta_frame, textvariable=self.source_var,
                                        width=22, style="NoteEditor.TCombobox")
        self.source_combo.pack(side="left", padx=(0, 12))
        self._fill_source_combo()  # 填充网盘资料选项

        # ── 2. 格式工具栏 ─────────────────────────────────────────────────────
        self._build_format_toolbar()

        # ── 3./4. 编辑区与渲染预览 ────────────────────────────────────────────
        editor_frame = ttk.Frame(self, padding=(12, 2, 12, 4), style="NoteEditor.TFrame")
        editor_frame.pack(fill="both", expand=True, side="top")

        # 操作提示
        tip = ttk.Label(
            editor_frame,
            text="Markdown 编辑区  |  "
                 "Ctrl+V 粘贴截图自动插入  |  "
                 "支持本地图片路径或 Base64  |  "
                 "标记符号已淡化，正文更清楚",
            style="NoteEditorMuted.TLabel",
            font=(FONT_FAMILY, 9),
        )
        tip.pack(anchor="w", pady=(0, 4))

        # 横向 PanedWindow：左侧编辑区，右侧预览区（默认隐藏）
        self.paned = ttk.PanedWindow(editor_frame, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        # ── 左：Markdown 文本编辑区 ────────────────────────────────────────
        text_frame = ttk.Frame(self.paned, style="NoteEditor.TFrame")

        self.text_area = tk.Text(
            text_frame,
            wrap="word",              # 自动换行（按单词边界）
            font=(MONO_FAMILY, 11),   # 等宽字体，适合 Markdown 书写
            width=68,                 # 声明宽度：PanedWindow 按两边 requested 分配，
                                      # 比事后 sashpos 稳（sashpos 会被 Tk 重排覆盖）
            relief="flat",            # 不用立体边框：改 1px 发丝线（见 highlight*）
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE.input_border,
            highlightcolor=PALETTE.input_focus,
            insertbackground=PALETTE.text_primary,
            padx=10,
            pady=10,
            undo=True,                # 开启撤销/重做（最多50步）
            maxundo=50,
        )
        vbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_area.yview)
        self.text_area.configure(yscrollcommand=vbar.set)
        self.text_area.pack(side="left", fill="both", expand=True)
        vbar.pack(fill="y", side="right")

        self.paned.add(text_frame, weight=2)

        # ── 右：渲染预览区（默认不加入 PanedWindow，点按钮后显示）───────────
        self.preview_visible = False
        self.preview_frame = ttk.Frame(self.paned, style="NoteEditor.TFrame")

        preview_header = ttk.Frame(self.preview_frame, style="NoteEditor.TFrame")
        preview_header.pack(fill="x", padx=8, pady=(4, 0))
        ttk.Label(
            preview_header, text="渲染预览（Typora 风格）",
            style="NoteEditor.TLabel",
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(side="left")

        preview_text_frame = ttk.Frame(self.preview_frame, style="NoteEditor.TFrame")
        preview_text_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.preview_area = tk.Text(
            preview_text_frame,
            wrap="word",
            font=(FONT_FAMILY, 10),
            width=56,                # 与编辑区的 68 一起决定左右比例（约 55 : 45）
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE.border,
            padx=22,
            pady=18,
            background=PALETTE.surface,  # 预览区当纸看，纯白最接近 Typora 的观感
            state="disabled",        # 只读
        )
        preview_vbar = ttk.Scrollbar(
            preview_text_frame, orient="vertical", command=self.preview_area.yview
        )
        self.preview_area.configure(yscrollcommand=preview_vbar.set)
        self.preview_area.pack(side="left", fill="both", expand=True)
        preview_vbar.pack(side="right", fill="y")

        # Markdown 渲染 tag（两处预览共用 markdown_view 的一套配置）
        markdown_view.setup_tags(self.preview_area)

        # 编辑区的「源码淡化」tag：只改前景色，不动字号 —— 改字号会让光标
        # 与文字错位，看起来像 bug。
        self.text_area.tag_configure("md_mark", foreground=PALETTE.text_muted)

        # 拦截 Ctrl+V：优先检测剪贴板图片；键盘输入正常透传
        self.text_area.bind("<Control-v>", self._on_ctrl_v)
        # 内容变化时：标记修改 + 实时刷新预览（仅可见时）+ 重排淡化标记
        self.text_area.bind("<KeyRelease>", self._on_text_change)
        # 鼠标粘贴 / 剪切 / 拖选不改走 KeyRelease，单独接一下
        self.text_area.bind("<<Paste>>", lambda _: self._schedule_dim())
        self.text_area.bind("<<Cut>>", lambda _: self._schedule_dim())
        self.text_area.bind("<ButtonRelease-1>", lambda _: self._schedule_dim())
        self.title_var.trace_add("write", lambda *_: self._mark_changed())

        # ── 5. 底部按钮栏 ─────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(12, 6, 12, 10), style="NoteEditor.TFrame")
        btn_frame.pack(fill="x")

        self.toggle_preview_btn = ttk.Button(
            btn_frame, text="显示效果", style="Quiet.TButton", width=0,
            command=self._toggle_preview,
        )
        self.toggle_preview_btn.pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="浏览器预览", style="Quiet.TButton", width=0,
                   command=self._preview_markdown).pack(side="left", padx=(0, 6))
        help_btn = ttk.Button(btn_frame, text="语法速查", style="Quiet.TButton", width=0,
                              command=self._open_syntax_help)
        help_btn.pack(side="left", padx=(0, 6))
        HoverTooltip(help_btn, lambda: ("Markdown 语法速查",
                                        "每种写法对照着看，忘了随时点"))

        # 右侧：保存 / 取消（保存是主操作，用近黑实底）
        ttk.Button(btn_frame, text="保存", style="Primary.TButton", width=0,
                   command=self._save).pack(side="right")
        ttk.Button(btn_frame, text="取消", style="Quiet.TButton", width=0,
                   command=self._on_close).pack(side="right", padx=(0, 6))

        # 状态栏（显示笔记 ID 或新建提示）
        status_text = (
            f"  [笔记ID: {self.note_id}]  " if self.note_id
            else "  [新建笔记]  "
        )
        self.status_var = tk.StringVar(value=status_text)
        ttk.Label(btn_frame, textvariable=self.status_var,
                  style="NoteEditorMuted.TLabel").pack(side="left", padx=10)

    # ── 格式工具栏 ────────────────────────────────────────────────────────────

    def _build_format_toolbar(self):
        """
        编辑区上方的格式工具栏。

        分四组，用竖直分隔线隔开（对齐 Word 的功能区逻辑）：

            样式▾  │  加粗 斜体 删除线 代码  │  代码块 引用 列表 编号 分隔线  │  链接 图片

        「样式」是段落级的（作用整行，可来回切换）；中间两组选中文字就包裹，
        没选中时针对光标所在行下手；「链接」「图片」需要先选中文字才有意义。
        每个按钮都有悬停提示告诉你对应的 Markdown 怎么写。
        """
        bar = ttk.Frame(self, padding=(12, 2, 12, 6), style="NoteEditor.TFrame")
        bar.pack(fill="x")

        # 组 1：样式（段落级）
        create_menu_button(
            bar, "样式",
            [
                ("正文",     lambda: self._apply_heading(0)),
                "---",
                ("标题 1",   lambda: self._apply_heading(1)),
                ("标题 2",   lambda: self._apply_heading(2)),
                ("标题 3",   lambda: self._apply_heading(3)),
                ("标题 4",   lambda: self._apply_heading(4)),
                ("标题 5",   lambda: self._apply_heading(5)),
                ("标题 6",   lambda: self._apply_heading(6)),
            ],
            padx=(0, 2),
        )
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=7)

        # 组 2：行内格式（选中即包裹）
        self._fmt_button(bar, "加粗", "加粗", "选中文字后点，或直接敲 **文字**",
                         lambda: self._wrap_inline("**", "**", "加粗文字"))
        self._fmt_button(bar, "斜体", "斜体", "选中文字后点，或直接敲 *文字*",
                         lambda: self._wrap_inline("*", "*", "斜体文字"))
        self._fmt_button(bar, "删除线", "删除线", "选中文字后点，或直接敲 ~~文字~~",
                         lambda: self._wrap_inline("~~", "~~", "删除线文字"))
        self._fmt_button(bar, "代码", "行内代码", "选中文字后点，或直接敲 `代码`",
                         lambda: self._wrap_inline("`", "`", "code"))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=7)

        # 组 3：块元素（作用整行）
        self._fmt_button(bar, "代码块", "代码块",
                         "选中多行则包进围栏；否则插入空代码块",
                         self._insert_code_block)
        self._fmt_button(bar, "引用", "引用块", "在行首加 > ，左侧会显示竖线",
                         lambda: self._apply_block("> "))
        self._fmt_button(bar, "列表", "无序列表", "在行首加 - ，变成圆点列表",
                         lambda: self._apply_block("- "))
        self._fmt_button(bar, "编号", "有序列表", "在行首加 1. ，变成数字列表",
                         lambda: self._apply_block("1. "))
        self._fmt_button(bar, "分隔线", "分隔线", "插入独占一行的 ---",
                         self._insert_hr)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=7)

        # 组 4：插入
        self._fmt_button(bar, "链接", "链接", "选中文字后点，再填网址；不选则插入占位",
                         self._insert_link)
        self._fmt_button(bar, "图片", "图片", "从本地选一张图，插入 ![](路径)",
                         self._insert_image_path)

    def _fmt_button(self, parent, text, title, subtitle, command, *, width=0):
        """工具栏按钮 + 悬停语法提示（Tk 没有原生 tooltip，用项目自绘的那套）。"""
        btn = ttk.Button(parent, text=text, width=width, style="Quiet.TButton",
                         command=command)
        btn.pack(side="left", padx=2)
        HoverTooltip(btn, lambda: (title, subtitle))
        return btn


    # ── 下拉框数据填充 ────────────────────────────────────────────────────────

    def _fill_category_combo(self):
        """
        填充分类下拉选项（树状结构，按 code 排序）。

        选项格式："  0101 编程语言"（带缩进表示层级，前缀为分类编码）
        通过 self._cat_map 字典实现标签文本 → StudyCategory 对象的反向映射，
        用于在保存时根据用户选择的标签找到对应分类对象。
        """
        cats = self.db.fetch_all_categories()
        self._cat_map = {}   # label文本 → StudyCategory（或 None）
        items = []

        # ★ 按 code 排序，确保树状结构正确（01, 0101, 010101, 0102...）
        cats_sorted = sorted(cats, key=lambda c: c.code)

        for c in cats_sorted:
            # 根据层级添加前导空格（视觉缩进效果）
            indent = "　" * (c.level - 1)   # 全角空格，避免字体不等宽导致错位
            label = f"{indent}{c.code} {c.name}"
            items.append(label)
            self._cat_map[label] = c

        # 固定第一个选项为"未分类"（对应空字符串编码）
        self._cat_map["未分类"] = None
        items.insert(0, "未分类")

        self.category_combo["values"] = items
        self.category_combo.current(0)

    def _fill_source_combo(self):
        """
        填充网盘来源下拉选项。

        选项格式："[1] Python 进阶完整版"（前缀为网盘资料 ID）
        self._source_map 实现标签文本 → BaiduDiskSource 对象的反向映射。
        """
        sources = self.db.fetch_baidu_sources()
        self._source_map = {}  # label → BaiduDiskSource
        items = []

        for s in sources:
            label = f"[{s.id}] {s.title}"
            items.append(label)
            self._source_map[label] = s

        self.source_combo["values"] = ["无"] + items
        self.source_combo.current(0)

    # ── 表单预填 ──────────────────────────────────────────────────────────────

    def _populate(self):
        """
        表单预填：在对话框打开时填入已有数据（编辑模式）或设置默认值（新增模式）。
        """
        if not self._note:
            # 新增模式：设置默认分类（从父窗口当前选中分类继承）
            for label, cat in self._cat_map.items():
                if cat and cat.code == self.default_category_code:
                    self.category_combo.set(label)
                    break
            return

        # ── 编辑模式：填入已有数据 ────────────────────────────────────────────
        self.title_var.set(self._note.title)
        self.tags_var.set(" ".join(self._note.tags))
        self.text_area.insert("1.0", self._note.content)

        # 选中笔记所属分类
        for label, cat in self._cat_map.items():
            if cat and cat.code == self._note.category_code:
                self.category_combo.set(label)
                break

        # 选中笔记关联的网盘资料
        if self._note.source_id:
            for label, src in self._source_map.items():
                if src and src.id == self._note.source_id:
                    self.source_combo.set(label)
                    break

    # ── 辅助方法 ──────────────────────────────────────────────────────────────

    def _save_original_values(self):
        """
        保存表单初始值，用于关闭时判断用户是否真的修改了内容。
        """
        self._original = {
            "title": self.title_var.get(),
            "category": self.category_var.get(),
            "tags": self.tags_var.get(),
            "source": self.source_var.get(),
            "content": self.text_area.get("1.0", "end-1c"),  # 去掉末尾换行
        }

    def _is_modified(self) -> bool:
        """
        比较当前值和原始值，判断表单是否被修改。
        """
        if not hasattr(self, "_original"):
            return self.changed  # 兼容：如果没有原始值，用旧逻辑

        current = {
            "title": self.title_var.get(),
            "category": self.category_var.get(),
            "tags": self.tags_var.get(),
            "source": self.source_var.get(),
            "content": self.text_area.get("1.0", "end-1c"),
        }
        return current != self._original

    def _mark_changed(self, *_):
        """
        标记内容已变更（用于兼容旧逻辑，实际判断用 _is_modified）。
        """
        self.changed = True

    def _get_current_category(self) -> tuple[str, str]:
        """
        根据用户在下拉框的选择，返回 (category_code, category_name)。

        返回:
            ("", "")              → 用户选择"未分类"
            ("0101", "编程语言")  → 用户选择了某个分类
        """
        label = self.category_var.get()
        if label == "未分类":
            return "", ""
        cat = self._cat_map.get(label)
        return (cat.code, cat.name) if cat else ("", "")

    def _get_current_source_id(self) -> int:
        """
        获取用户选择的网盘资料 ID。
        用户选择"无"时返回 0。
        """
        label = self.source_var.get()
        if label == "无":
            return 0
        src = self._source_map.get(label)
        return src.id if src else 0

    # ── Ctrl+V 截图粘贴 ───────────────────────────────────────────────────────

    def _on_ctrl_v(self, event):
        """
        拦截 Ctrl+V 键盘事件，优先检测剪贴板是否为图片。

        处理流程：
          1. 尝试从剪贴板读取 image/png 数据
          2. 若失败（TclError）→ 返回 None，让系统执行默认粘贴行为（文本）
          3. 若成功 → 保存 PNG 到笔记专属目录 → 插入 Markdown img 语法 → 返回 "break" 阻止默认行为

        截图文件命名规则：{时间戳}_{序号}.png
        存储位置：{db目录}/study_notes_images/{note_id}/

        注意：图片以相对路径形式插入 Markdown（相对于数据库目录），
              便于打包后路径一致性。
        """
        try:
            clipboard = self.clipboard_get(type="image/png")
        except tk.TclError:
            # 不是图片类型 → 放行，让 Tkinter 执行默认文本粘贴
            return None

        # ── 保存截图 ────────────────────────────────────────────────────────
        img_data = clipboard
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # note_id 为 0 时（新建）临时存到 new/ 目录
        safe_id = str(self._current_note_id) if self._current_note_id else "new"
        img_dir = self.note_dir / safe_id
        img_dir.mkdir(parents=True, exist_ok=True)

        # 计算下一个序号（避免时间戳重复时覆盖）
        existing = sorted(img_dir.glob("*.png"))
        seq = len(existing) + 1
        filename = f"{timestamp}_{seq:03d}.png"
        img_path = img_dir / filename

        try:
            # 将剪贴板二进制数据（BytesIO）转为 PIL Image 再保存为 PNG
            Image.open(io.BytesIO(img_data)).save(img_path)
        except Exception as exc:
            messagebox.showerror("截图粘贴失败", f"保存截图出错：\n{exc}", parent=self)
            return "break"

        # ── 插入 Markdown 图片语法 ───────────────────────────────────────────
        # 计算相对路径（相对于数据库文件所在目录）
        db_dir = Path(self.db.db_path).parent
        try:
            rel = img_path.relative_to(db_dir)
        except Exception:
            rel = img_path  # 跨盘时用绝对路径

        # 在光标位置插入 Markdown 图片语法
        self.text_area.insert(
            self.text_area.index("insert"),
            f"\n![]({rel})\n",
        )
        self.text_area.see("insert")
        self.changed = True
        return "break"   # 阻止默认文本粘贴行为

    # ── 快捷插入 ──────────────────────────────────────────────────────────────

    def _insert_image_path(self):
        """
        通过系统文件对话框选择本地图片，插入 Markdown 图片语法。
        支持格式：PNG / JPG / WEBP / BMP / GIF。
        """
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            # 使用正斜杠路径（跨平台兼容性）
            self.text_area.insert(
                self.text_area.index("insert"),
                f"\n![]({Path(path).as_posix()})\n"
            )
            self.text_area.see("insert")

    def _insert_hr(self):
        """
        在光标位置插入 Markdown 分隔线：---（前后各空一行）。
        """
        self.text_area.insert(self.text_area.index("insert"), "\n---\n")

    def _insert_code_block(self):
        """
        插入 Markdown 代码块。

        有选中内容就整段包进围栏 —— 这是更常用的顺序（先把代码贴进来、再点按钮）；
        没选中则插入一对空围栏，光标落在中间那行。
        """
        ta = self.text_area
        try:
            start = ta.index("sel.first")
            end = ta.index("sel.last")
        except tk.TclError:
            ta.insert(ta.index("insert"), "\n```\n\n```\n")
            ta.edit_separator()  # 记录撤销分隔点
            # 将光标上移一行（移到空代码内容行）
            cur = ta.index("insert")
            parts = cur.split(".")
            parts[1] = str(int(parts[1]) - 2)
            ta.mark_set("insert", ".".join(parts))
            ta.see("insert")
            self._on_text_change()
            return

        selected = ta.get(start, end)
        ta.delete(start, end)
        ta.insert(start, f"```\n{selected}\n```")
        ta.tag_remove("sel", "1.0", "end")
        ta.edit_separator()
        self._on_text_change()

    # ── Markdown 预览 ────────────────────────────────────────────────────────

    def _toggle_preview(self):
        """
        切换预览面板的显示/隐藏。
        """
        if self.preview_visible:
            try:
                self.paned.forget(self.preview_frame)
            except Exception:
                pass
            self.preview_visible = False
            self.toggle_preview_btn.config(text="显示效果")
        else:
            self.paned.add(self.preview_frame, weight=1)
            self.preview_visible = True
            self.toggle_preview_btn.config(text="隐藏效果")
            self._render_preview()
            # 刚 add 进去时控件宽度还是 1px，标题下划线会退化成兜底长度。
            # 等布局落定后按真实宽度重画一遍。
            self.after(60, self._render_preview)

    def _refresh_preview_if_shown(self):
        """
        仅在预览可见时刷新预览内容（避免不必要的渲染开销）。
        """
        if self.preview_visible:
            self._render_preview()

    def _render_preview(self):
        """
        把编辑区内容渲染到右侧预览。

        渲染实现统一在 markdown_view —— 和笔记页的「笔记预览」是同一套，
        所以同一篇笔记在编辑器里和列表下方看到的样子完全一致。
        """
        markdown_view.render(
            self.preview_area,
            self.text_area.get("1.0", "end-1c"),
            empty_hint="（笔记内容为空）",
        )

    # ── 编辑区：源码淡化 ──────────────────────────────────────────────────────

    def _on_text_change(self, _event=None):
        """编辑区每次变化都走这里：标记改动、刷新预览、重排淡化标记。"""
        self._mark_changed()
        self._refresh_preview_if_shown()
        self._schedule_dim()

    def _schedule_dim(self):
        """防抖：连续敲字时不必每个键都全文重扫一遍。"""
        if self._dim_after is not None:
            try:
                self.after_cancel(self._dim_after)
            except Exception:
                pass
        self._dim_after = self.after(160, self._dim_marks)

    def _dim_marks(self):
        """
        把 Markdown 标记符号染成浅灰，让正文跳出来。

        做的是「源码淡化」而不是所见即所得：标记还在、位置也没变，只是不再和
        文字抢注意力 —— 想改语法随时能改，也不会打乱 Tk 自带的光标定位和撤销。

        索引一律用「行号.列号」而不是「1.0+Nc」：后者每次都让 Tcl 从头解析一遍
        偏移量，几百行下来明显变慢。
        """
        self._dim_after = None
        ta = self.text_area
        try:
            content = ta.get("1.0", "end-1c")
        except Exception:
            return
        ta.tag_remove("md_mark", "1.0", "end")
        if len(content) > _DIM_MAX_CHARS:
            return
        for row, line in enumerate(content.split("\n"), start=1):
            if not line:
                continue
            for pat in _LINE_MARK_PATTERNS:
                m = pat.match(line)
                if m:
                    ta.tag_add("md_mark", f"{row}.{m.start()}", f"{row}.{m.end()}")
                    break
            for m in _INLINE_MARK_RE.finditer(line):
                ta.tag_add("md_mark", f"{row}.{m.start()}", f"{row}.{m.end()}")

    # ── 格式工具栏的动作 ──────────────────────────────────────────────────────

    def _wrap_inline(self, prefix: str, suffix: str, placeholder: str):
        """
        行内格式：有选中就包裹选区，没选中就插入一对标记并把光标放进中间。

        选中内容本身已带同样的标记时**去掉它** —— 再点一次加粗应该是「取消加粗」，
        而不是套成 ****粗****。
        """
        ta = self.text_area
        try:
            start = ta.index("sel.first")
            end = ta.index("sel.last")
        except tk.TclError:
            insert = ta.index("insert")
            ta.insert(insert, f"{prefix}{placeholder}{suffix}")
            ta.mark_set("insert", f"{insert}+{len(prefix)}c")
            ta.edit_separator()
            self._on_text_change()
            return

        selected = ta.get(start, end)
        ta.delete(start, end)
        if (selected.startswith(prefix) and selected.endswith(suffix)
                and len(selected) >= len(prefix) + len(suffix)):
            ta.insert(start, selected[len(prefix):len(selected) - len(suffix)])
        else:
            ta.insert(start, f"{prefix}{selected}{suffix}")
        ta.tag_remove("sel", "1.0", "end")
        ta.edit_separator()
        self._on_text_change()

    def _apply_block(self, prefix: str):
        """
        块元素：给光标所在的**每一行**加行首标记（选中多行就整段处理）。

        再点一次同样的标记即取消 —— 列表和引用都按这个语义。
        """
        ta = self.text_area
        try:
            first = min(int(ta.index("insert").split(".")[0]),
                        int(ta.index("sel.first").split(".")[0]))
            last = int(ta.index("sel.last").split(".")[0])
        except tk.TclError:
            first = last = int(ta.index("insert").split(".")[0])
        # 选区刚好停在行首时不该把下一行也带上
        if last > first and ta.index("sel.last").split(".")[1] == "0":
            last -= 1

        ta.edit_separator()
        for row in range(first, last + 1):
            line = ta.get(f"{row}.0", f"{row}.end")
            indent = line[:len(line) - len(line.lstrip())]
            col = len(indent)
            if line.lstrip().startswith(prefix):
                ta.delete(f"{row}.{col}", f"{row}.{col + len(prefix)}")
            else:
                ta.insert(f"{row}.{col}", prefix)
        self._on_text_change()

    def _apply_heading(self, level: int):
        """
        设置光标所在行的标题级别；level=0 表示还原成正文。

        标题是互斥的（一行只能有一个 #），所以先清掉行首已有的 # 再按需写入 ——
        这样「H1 切成 H3」得到的是一行 H3，而不是叠成 ##### H1。
        """
        ta = self.text_area
        row = int(ta.index("insert").split(".")[0])
        line = ta.get(f"{row}.0", f"{row}.end")
        body = re.sub(r"^\s{0,3}#{1,6}\s+", "", line, count=1)
        if level > 0:
            body = "#" * level + " " + body.lstrip()
        ta.edit_separator()
        ta.delete(f"{row}.0", f"{row}.end")
        ta.insert(f"{row}.0", body)
        ta.mark_set("insert", f"{row}.{len(body)}")
        self._on_text_change()

    def _insert_link(self):
        """插入链接：选中文字当标题；没选中就给占位，光标停在网址处。"""
        ta = self.text_area
        try:
            start = ta.index("sel.first")
            end = ta.index("sel.last")
            label = ta.get(start, end)
            ta.delete(start, end)
        except tk.TclError:
            label = "链接文字"
            start = ta.index("insert")

        url = "https://"
        ta.insert(start, f"[{label}]({url})")
        row, col = start.split(".")
        ta.mark_set("insert", f"{row}.{int(col) + len(f'[{label}]({url}')}")
        ta.edit_separator()
        self._on_text_change()

    # ── 语法速查 ─────────────────────────────────────────────────────────────

    def _open_syntax_help(self):
        """语法速查窗口：左边怎么写、右边什么效果。"""
        win = tk.Toplevel(self)
        win.title("Markdown 语法速查")
        win.geometry("760x600")
        win.minsize(560, 380)
        win.transient(self)
        apply_dialog_form_style(win, PALETTE, style_prefix="NoteEditor")

        head = ttk.Frame(win, padding=(18, 14, 18, 6), style="NoteEditor.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Markdown 语法速查",
                  style="NoteEditor.TLabel",
                  font=(FONT_FAMILY, 13, "bold")).pack(anchor="w")
        ttk.Label(head, text="写法照着敲就行；工具栏每个按钮也都有悬停提示。",
                  style="NoteEditorMuted.TLabel",
                  font=(FONT_FAMILY, 9)).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(win, padding=(18, 0, 18, 8), style="NoteEditor.TFrame")
        body.pack(fill="both", expand=True)

        tree = ttk.Treeview(body, columns=("syntax", "effect"),
                            show="headings", selectmode="browse")
        # 不用 #0 树列：ttk 会给它留出图标/展开器的位置，width=0 也压不掉，
        # 结果是分组标题挤在左边一列、表头却对不上。改成就两列数据列，
        # 分组行靠 tag 加粗区分。
        tree.heading("syntax", text="写法", anchor="w")
        tree.heading("effect", text="效果", anchor="w")
        tree.column("syntax", width=230, anchor="w", stretch=False)
        tree.column("effect", width=460, anchor="w")
        tree.tag_configure("group", font=(FONT_FAMILY, 10, "bold"),
                           foreground=PALETTE.text_primary)
        tree.tag_configure("item", foreground=PALETTE.text_secondary)
        for group, items in _SYNTAX_HELP:
            tree.insert("", "end", values=(group, ""), tags=("group",))
            for syntax, effect in items:
                tree.insert("", "end", values=("    " + syntax, effect), tags=("item",))
        vbar = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vbar.set)
        tree.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        foot = ttk.Frame(win, padding=(18, 0, 18, 14), style="NoteEditor.TFrame")
        foot.pack(fill="x")
        ttk.Button(foot, text="知道了", style="Primary.TButton", width=0,
                   command=win.destroy).pack(side="right")
        win.bind("<Escape>", lambda _: win.destroy())
        _center_over_parent(win, self)

    def _preview_markdown(self):
        """
        将 Markdown 内容转换为 HTML 并在系统浏览器中打开预览。

        转换范围（当前为简化实现）：
          - 代码块（``` ```）
          - 行内代码（`code`）
          - 6 级标题（# ~ ######）
          - 加粗（**bold**）、斜体（*italic*）
          - 图片（本地路径自动转绝对路径）
          - 链接、换行、水平线
        """
        content = self.text_area.get("1.0", "end")
        if not content.strip():
            messagebox.showinfo("预览", "笔记内容为空。", parent=self)
            return
        self._save_html_preview(content)

    def _build_html_preview(self, content: str) -> str:
        """
        把 Markdown 转成带样式的完整 HTML（浏览器预览用）。

        tk.Text 画不出 border / 圆角 / 行高，所以浏览器这条路径才是完整版 ——
        这里的 CSS 才能真正 1:1 还原 Typora 的排版。
        """
        return markdown_view.build_html(
            content,
            base_dir=Path(self.db.db_path).parent,
            title=self.title_var.get().strip() or "笔记预览",
        )

    def _save_html_preview(self, content: str):
        """
        将 HTML 内容写入临时文件并调用系统浏览器打开。
        临时文件用完不删除（让浏览器持续访问），由操作系统自动清理。
        """
        html = self._build_html_preview(content)
        try:
            # tempfile.NamedTemporaryFile 创建后文件处于打开状态，
            # delete=False 防止关闭后文件被删除（浏览器后续仍可读）
            with tempfile.NamedTemporaryFile(
                "w", suffix=".html", delete=False, encoding="utf-8"
            ) as f:
                f.write(html)
                path = f.name
            # Windows 文件路径 file:/// 需要四斜杠（file:// + / + / + C:）
            webbrowser.open(f"file:///{path}")
        except Exception as exc:
            messagebox.showerror(
                "预览失败",
                f"无法打开浏览器预览：\n{exc}",
                parent=self,
            )

    # ── 保存 ─────────────────────────────────────────────────────────────────

    def _save(self):
        """
        验证并保存笔记数据到数据库。

        保存流程：
          1. 校验标题必填
          2. 解析标签（空格/逗号分隔 → 列表）
          3. 获取当前选中的分类和来源
          4. 构造 payload 字典
          5. 调用 db.add_note / db.update_note
          6. 更新内部状态，通知父窗口刷新

        注意：新建笔记保存后才能获得真实 ID（自增主键）；
              保存后 _current_note_id 被更新，Ctrl+V 粘贴的截图会保存到正确目录。
        """
        # ── 校验 ─────────────────────────────────────────────────────────────
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("笔记编辑", "标题不能为空。", parent=self)
            return

        # ── 解析标签 ─────────────────────────────────────────────────────────
        tags_text = self.tags_var.get().strip()
        tags = [
            t.strip() for t in re.split(r"[\s,，；;]+", tags_text)
            if t.strip()
        ]

        # ── 获取分类和来源 ───────────────────────────────────────────────────
        category_code, category_name = self._get_current_category()
        source_id = self._get_current_source_id()
        content = self.text_area.get("1.0", "end")

        payload = {
            "title":         title,
            "category_code":  category_code,
            "category_name": category_name,
            "content":        content,
            "tags":           tags,
            "source_id":      source_id,
        }

        # ── 写入数据库 ───────────────────────────────────────────────────────
        if self.note_id:
            self.db.update_note(self.note_id, payload)
            note_id = self.note_id
        else:
            note_id = self.db.add_note(payload)

        # ── 更新状态 ─────────────────────────────────────────────────────────
        self._current_note_id = note_id
        self.note_id = note_id        # 后续保存走 update 路径
        self.changed = False
        self.status_var.set(f"  已保存 [ID: {note_id}]  ")

        # 通知父窗口刷新笔记列表
        self.parent_window.refresh_notes()

        messagebox.showinfo(
            "笔记编辑",
            "笔记已保存。\n\n"
            "提示：保存后 Ctrl+V 粘贴的截图会存到对应笔记目录下。",
            parent=self,
        )

    # ── 关闭 ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        """
        窗口关闭事件处理。

        逻辑：
          - 内容有变更 → 弹出确认对话框，用户确认后才关闭
          - 内容无变更 → 直接关闭
        """
        if self._is_modified():
            if not messagebox.askyesno(
                "笔记编辑",
                "笔记尚未保存，确定要关闭吗？",
                parent=self,
            ):
                return
        self.destroy()


# =============================================================================
# 学习笔记主窗口
# =============================================================================

class StudyNotesPage(ttk.Frame):
    """
    学习笔记资料库页面（嵌入主窗口，非独立窗口）。
    整合分类树、笔记列表、笔记预览三大区域。

    生命周期（由 main.py 管理）：
        __init__ 中创建 self.study_notes_page = StudyNotesPage(parent_frame, self.study_notes_db)
        switch_module("study_notes") → pack(fill="both", expand=True) 显示
        切换其他模块 → pack_forget() 隐藏
    """

    def __init__(self, parent: ttk.Frame, db: StudyNotesDB):
        """
        参数:
            parent - 父容器 ttk.Frame（self.page_container 下的帧）
            db     - StudyNotesDB 数据库实例
        """
        super().__init__(parent)
        # parent.winfo_toplevel() 可还原为 ExpiryManagerApp 实例（供 BaiduDiskWindow 等子窗口使用）
        self.parent = parent
        self.db = db

        # 搜索/筛选状态
        self._last_keyword = ""           # 搜索关键词
        self._selected_category_code = ""  # 当前选中的分类编码（空=全部分类）
        self._selected_note_id: int | None = None

        self.build_ui()
        self.refresh_tree()    # 加载分类树
        self.refresh_notes()   # 加载笔记列表

    # ==========================================================================
    # UI 布局
    # ==========================================================================

    def build_ui(self):
        """
        主窗口采用左右分栏布局（ttk.PanedWindow）：

            ┌──────────────┬─────────────────────────────────────┐
            │  左侧分类树   │          右侧笔记区                   │
            │  (280px 固定) │  ┌─────────────────────────────┐   │
            │              │  │ 工具栏：新增/编辑/删除/搜索     │   │
            │  📂 01 技术  │  ├─────────────────────────────┤   │
            │    ├0101    │  │ 笔记列表表格                   │   │
            │    └0102    │  ├─────────────────────────────┤   │
            │  📂 02 烹饪  │  │ 笔记预览区（Markdown 渲染）    │   │
            │  📂 03 健身  │  └─────────────────────────────┘   │
            │  [+新分类]   │                                      │
            │  [网盘]      │                                      │
            └──────────────┴─────────────────────────────────────┘
        """
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # ── 左侧：分类树面板 ───────────────────────────────────────────────
        left_frame = ttk.Frame(paned, width=280)
        self.build_left_panel(left_frame)
        paned.add(left_frame, weight=0)  # weight=0：固定宽度，不随窗体拉伸

        # ── 右侧：笔记列表 + 预览 ──────────────────────────────────────────
        right_frame = ttk.Frame(paned)
        self.build_right_panel(right_frame)
        paned.add(right_frame, weight=1)  # weight=1：占据剩余全部空间

        paned.pack(fill="both", expand=True)
        self.paned = paned

    def build_left_panel(self, frame: ttk.Frame):
        """
        左侧分类树面板：
          - 顶部：标题栏 + 网盘按钮 + 新分类按钮
          - 中部：ttk.Treeview 分类树（可折叠，支持右键菜单）
          - 底部：新增/编辑/删除快捷按钮
        """

        # ── 标题栏 ──────────────────────────────────────────────────────────
        header = ttk.Frame(frame, padding=(8, 8, 8, 4))
        header.pack(fill="x")
        ttk.Label(header, text="笔记分类", font=(FONT_FAMILY, 10, "bold")).pack(side="left")
        ttk.Button(header, text="网盘", command=self.open_baidu_disk, width=6).pack(side="right", padx=2)
        ttk.Button(header, text="+ 新分类", command=self.add_category).pack(side="right", padx=2)

        # ── 分类树 ──────────────────────────────────────────────────────────
        tree_frame = ttk.Frame(frame, padding=(4, 0, 4, 4))
        tree_frame.pack(fill="both", expand=True)

        self.cat_tree = ttk.Treeview(
            tree_frame,
            show="tree",       # 只显示树形图标列（不含数据列）
            selectmode="browse",  # 单选
            height=999,        # 填满可用高度
        )
        # 系统锁定分类（如「Excel 宝典」）用灰字标出来。它不能改名 / 删除，
        # 得让用户一眼看出「这个不是我能动的」，否则会以为是程序坏了。
        self.cat_tree.tag_configure("locked", foreground=PALETTE.text_secondary)
        cat_vbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.cat_tree.yview)
        self.cat_tree.configure(yscrollcommand=cat_vbar.set)
        self.cat_tree.pack(side="left", fill="both", expand=True)
        cat_vbar.pack(fill="y", side="right")

        # 事件绑定：选中分类 → 刷新笔记列表（按分类过滤）
        self.cat_tree.bind("<<TreeviewSelect>>", self._on_cat_select)
        # 右键菜单：新增子分类 / 编辑 / 删除
        self.cat_tree.bind("<Button-3>", self._on_cat_right_click)

        # ── 底部操作按钮 ────────────────────────────────────────────────────
        btn_row = ttk.Frame(frame, padding=(4, 4, 8, 8))
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="新增", command=self.add_category, width=5).pack(side="left", padx=2)
        ttk.Button(btn_row, text="编辑", command=self.edit_category, width=5).pack(side="left", padx=2)
        ttk.Button(btn_row, text="删除", command=self.delete_category, width=5).pack(side="left", padx=2)

    def build_right_panel(self, frame: ttk.Frame):
        """
        右侧笔记区：
          - 顶部工具栏：新增/编辑/删除 + 搜索框 + 标签过滤 + 关闭按钮
          - 中部笔记列表：ttk.Treeview 表格
          - 底部预览区：只读 Text 展示 Markdown 内容 + 来源信息
        """

        # ── 工具栏 ──────────────────────────────────────────────────────────
        toolbar = ttk.Frame(frame, padding=(10, 8, 10, 4))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="+ 新增笔记", command=self.add_note).pack(side="left", padx=3)
        ttk.Button(toolbar, text="编辑",       command=self.edit_note).pack(side="left", padx=3)
        ttk.Button(toolbar, text="删除",        command=self.delete_note).pack(side="left", padx=3)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        # 原处有个 🔍 emoji：紧跟着就是「搜索」按钮，图标是冗余的，且是彩色的
        self.search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.search_var, width=28).pack(side="left", padx=4)
        ttk.Button(toolbar, text="搜索", command=self.do_search).pack(side="left", padx=3)
        ttk.Button(toolbar, text="清空", command=self.clear_search).pack(side="left", padx=3)

        ttk.Label(toolbar, text="标签过滤:").pack(side="left", padx=(12, 4))
        self.tag_filter_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.tag_filter_var, width=16).pack(side="left", padx=4)
        ttk.Button(toolbar, text="按标签筛选", command=self.do_search).pack(side="left", padx=3)

        ttk.Button(toolbar, text="关闭", command=self.destroy).pack(side="right", padx=3)

        # ── 笔记列表 ────────────────────────────────────────────────────────
        list_frame = ttk.Frame(frame, padding=(10, 4, 10, 4))
        list_frame.pack(fill="both", expand=True)

        columns = ("id", "title", "category", "tags", "source", "updated_at")
        col_meta = {
            "id":          ("ID",      50),
            "title":       ("标题",   340),
            "category":    ("分类",   200),
            "tags":        ("标签",   200),
            "source":      ("来源",   180),
            "updated_at":  ("更新时间", 130),
        }

        self.notes_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=8,
            selectmode="browse",
        )
        for col in columns:
            text, width = col_meta[col]
            self.notes_tree.heading(col, text=text)
            # 定长编号列居中，文本列左对齐（与全站表格规则一致）
            anchor = "center" if col == "id" else "w"
            self.notes_tree.column(col, width=width, anchor=anchor)

        vbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.notes_tree.yview)
        self.notes_tree.configure(yscrollcommand=vbar.set)
        self.notes_tree.pack(side="left", fill="both", expand=True)
        vbar.pack(fill="y", side="right")

        self.notes_tree.bind("<Double-1>", lambda _: self.edit_note())
        self.notes_tree.bind("<Return>",     lambda _: self.edit_note())
        self.notes_tree.bind("<<TreeviewSelect>>", self._on_note_select)

        # ── 笔记预览 ───────────────────────────────────────────────────────
        preview_frame = ttk.LabelFrame(frame, text="笔记预览", padding=(12, 4, 12, 10))
        # expand=True：与上方列表平分窗口多出来的高度。若固定 expand=False，
        # 窗口拉高只会让列表变长，预览区永远是那十几行。
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        preview_inner = ttk.Frame(preview_frame)
        preview_inner.pack(fill="both", expand=True)
        self.preview_text = tk.Text(
            preview_inner,
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE.border_soft,
            state="disabled",   # 只读模式
            font=(FONT_FAMILY, 10),
            bg=PALETTE.surface_alt,
            padx=14,
            pady=10,
            height=15,
        )
        self._setup_page_preview_tags()
        pvbar = ttk.Scrollbar(preview_inner, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=pvbar.set)
        self.preview_text.pack(side="left", fill="both", expand=True)
        pvbar.pack(fill="y", side="right")

    # ==========================================================================
    # 分类树操作
    # ==========================================================================

    def refresh_tree(self):
        """
        重新渲染左侧分类树。

        算法：
          1. 获取所有分类（已按 level / sort_order / code 排序）
          2. 构建 parent_code → [children] 的映射表
          3. 递归插入树节点（父节点ID → "" 表示根层）
          4. 节点标签格式："编码 名称  (笔记数)"（有笔记时显示数量）
          5. 默认展开第一层（方便用户一眼看到所有大类）
        """
        for item in self.cat_tree.get_children():
            self.cat_tree.delete(item)

        cats = self.db.fetch_all_categories()

        # 构建父子映射
        children_map: dict[str, list[StudyCategory]] = {}
        roots: list[StudyCategory] = []
        for c in cats:
            if not c.parent_code:
                roots.append(c)
            else:
                children_map.setdefault(c.parent_code, []).append(c)

        def insert_node(parent_iid: str, cat: StudyCategory):
            """递归插入单个分类节点及其所有子节点。"""
            note_count = self.db.count_notes_by_category(cat.code)
            label = f"{cat.code} {cat.name}"
            # 「（系统）」后缀 + 灰字：锁定分类要一眼看得出为什么改不动。
            # 不用 🔒 这类彩色 emoji —— 它在 Tk 里是彩色的，而且字体缺字时
            # 会变成一个方块（本项目为此撤过图标，见 UI_NOTES）。
            if cat.locked:
                label += "（系统）"
            if note_count > 0:
                label = f"{label}  ({note_count})"
            iid = str(cat.id)
            # values 存 code 和 level（隐藏列，供后续逻辑读取）
            self.cat_tree.insert(parent_iid, "end", iid=iid, text=label,
                                 values=(cat.code, cat.level),
                                 tags=("locked",) if cat.locked else ())
            # 递归插入子节点
            for child in children_map.get(cat.code, []):
                insert_node(iid, child)

        for root in roots:
            insert_node("", root)

        # 默认展开所有大类节点
        for root_iid in self.cat_tree.get_children(""):
            self.cat_tree.item(root_iid, open=True)

    def _on_cat_select(self, event=None):
        """
        用户点击分类树节点时触发：更新过滤条件，刷新右侧笔记列表。

        values[0] = code（分类编码），由 insert_node 时存入
        """
        sel = self.cat_tree.selection()
        if not sel:
            return
        code = self.cat_tree.item(sel[0], "values")[0]
        self._selected_category_code = code
        self.refresh_notes()

    def _on_cat_right_click(self, event):
        """
        分类树右键菜单：弹出操作菜单。

        锁定分类（locked=1）里「编辑 / 删除」两项直接禁用，并补一句说明 ——
        比让用户点了再弹一个「不能改」的提示友好：菜单本身就把事情说清楚了。
        """
        item = self.cat_tree.identify_row(event.y)
        if not item:
            return
        self.cat_tree.selection_set(item)
        code = self.cat_tree.item(item, "values")[0]
        cat = self.db.get_category_by_code(code)
        locked = bool(cat and cat.locked)

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="新增子分类", command=self.add_category)
        if locked:
            menu.add_separator()
            menu.add_command(
                label=f"「{cat.name}」由系统占用，不能改名 / 删除",
                state="disabled")
        else:
            menu.add_command(label="编辑分类", command=self.edit_category)
            menu.add_separator()
            menu.add_command(label="删除分类", command=self.delete_category)
        menu.tk_popup(event.x_root, event.y_root)

    def add_category(self):
        """
        新增分类。

        逻辑：
          - 若当前有选中分类 → 在其下新增子分类（level+1，最多三级）
          - 若无选中 → 新增顶级分类（level=1）
          - 自动生成下一个可用编码（get_next_category_code）
        """
        sel = self.cat_tree.selection()
        parent_code = ""
        parent_cat: StudyCategory | None = None
        level = 1

        if sel:
            pid = self.cat_tree.item(sel[0], "values")[0]
            pcat = self.db.get_category_by_code(pid)
            if pcat:
                parent_cat = pcat
                parent_code = pcat.code
                level = min(pcat.level + 1, 4)

        if level > 4:
            messagebox.showinfo("分类管理", "最多支持四级分类。", parent=self)
            return

        suggested_code = self.db.get_next_category_code(parent_code)

        dlg = CategoryEditDialog(
            self, "新增分类",
            parent_code=parent_code, level=level,
            initial={"sort_order": 0}
        )
        self.wait_window(dlg)
        if not dlg.result:
            return

        self.db.add_category(
            code=suggested_code,
            name=dlg.result["name"],
            parent_code=parent_code,
            level=level,
            sort_order=dlg.result["sort_order"],
        )
        self.refresh_tree()

    def edit_category(self):
        """编辑选中分类的名称和排序号。锁定分类会被挡下（附原因）。"""
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo("分类管理", "请先选择要编辑的分类。", parent=self)
            return
        cat_id = int(sel[0])
        cat = self.db.get_category(cat_id)
        if not cat:
            return
        if cat.locked:
            messagebox.showinfo(
                "分类管理",
                f"「{cat.name}」是系统分类（别的模块的笔记会写到这里），"
                "不能改名。\n\n"
                "你可以在它下面新增子分类，也可以照常在自己的分类里增删改。",
                parent=self)
            return

        dlg = CategoryEditDialog(
            self, "编辑分类",
            initial={"name": cat.name, "sort_order": cat.sort_order},
        )
        self.wait_window(dlg)
        if dlg.result:
            self.db.update_category(cat_id, dlg.result["name"], dlg.result["sort_order"])
            self.refresh_tree()

    def delete_category(self):
        """
        删除选中分类。

        影响范围：
          - 笔记：移至"未分类"（不删除）
          - 子分类：一并删除

        锁定分类不删（数据层也拦了一道）：删了另一头就找不到落点了。
        """
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo("分类管理", "请先选择要删除的分类。", parent=self)
            return
        cat_id = int(sel[0])
        cat = self.db.get_category(cat_id)
        if not cat:
            return
        if cat.locked:
            messagebox.showinfo(
                "分类管理",
                f"「{cat.name}」是系统分类（别的模块的笔记会写到这里），"
                "不能删除。\n\n"
                "里面已有的笔记可以照常打开、编辑、删除。",
                parent=self)
            return

        note_count = self.db.count_notes_by_category(cat.code)
        child_count = len(self.db.get_children_categories(cat.code))

        msg = f"确定删除分类「{cat.name}」吗？\n"
        if note_count > 0:
            msg += f"\n该分类下有 {note_count} 篇笔记，将被移至「未分类」。"
        if child_count > 0:
            msg += f"\n\n同时将删除 {child_count} 个子分类。"
        msg += "\n\n此操作不可恢复。"

        if not messagebox.askyesno("删除分类", msg, parent=self):
            return

        self.db.delete_category(cat_id)
        self._selected_category_code = ""  # 清空选中，防止显示已删除分类的笔记
        self.refresh_tree()
        self.refresh_notes()

    # ==========================================================================
    # 笔记列表操作
    # ==========================================================================

    def refresh_notes(self):
        """
        刷新右侧笔记列表表格。

        过滤逻辑（可叠加）：
          - _last_keyword（非空）→ 标题/正文/标签模糊匹配
          - _selected_category_code（非空）→ 该分类及其子分类
          - tag_filter_var（非空）→ 标签列表任一命中
        """
        for item in self.notes_tree.get_children():
            self.notes_tree.delete(item)

        # 解析标签过滤
        tag_text = self.tag_filter_var.get().strip()
        tags = (
            [t.strip() for t in tag_text.split() if t.strip()]
            if tag_text else None
        )

        notes = self.db.fetch_notes(
            keyword=self._last_keyword,
            category_code=self._selected_category_code,
            tags=tags,
        )

        for note in notes:
            # 解析来源标签
            src_label = ""
            if note.source_id:
                src = self.db.get_baidu_source(note.source_id)
                if src:
                    src_label = f"[{src.id}] {src.title}"

            self.notes_tree.insert(
                "", "end",
                iid=str(note.id),
                values=(
                    note.id,
                    note.title,
                    f"{note.category_code} {note.category_name}".strip() or "未分类",
                    note.tags_str(),
                    src_label,
                    note.updated_at[:16] if note.updated_at else "",
                ),
            )

    def _on_note_select(self, event=None):
        """
        用户选中笔记行时触发：在底部预览区显示笔记内容。
        """
        sel = self.notes_tree.selection()
        if not sel:
            return
        note_id = int(sel[0])
        self._selected_note_id = note_id
        self._show_preview(note_id)

    def _setup_page_preview_tags(self):
        """
        底部预览面板的 tag。

        两套并存：`pv_*` 是这块面板自己的「标题 / 元信息 / 发丝线 / 空态」，
        `markdown_view.setup_tags` 那套（h1~h6 / p / li / code… ）负责正文 ——
        与编辑器右侧预览**同一份配置**，所以同一篇笔记在哪看都一个样。
        """
        p = self.preview_text
        p.tag_configure("pv_title", font=(FONT_FAMILY, 13, "bold"),
                        foreground=PALETTE.text_primary, spacing1=2, spacing3=4)
        p.tag_configure("pv_meta", font=(FONT_FAMILY, 9),
                        foreground=PALETTE.text_muted, spacing3=2)
        p.tag_configure("pv_rule", font=(FONT_FAMILY, 9),
                        foreground="#e2e2e2", spacing1=8, spacing3=8)
        p.tag_configure("pv_body", font=(FONT_FAMILY, 10),
                        foreground=PALETTE.text_primary, spacing1=4)
        markdown_view.setup_tags(p)

    def _show_preview(self, note_id: int):
        """
        在底部面板渲染笔记。

        版式：

            笔记标题
            分类：0101 基础语法
            标签：python 入门
            ────────────────────────
            正文 —— 真实渲染的 Markdown

        旧版这里把 `note.content` 原文整段倒进 Text，于是同一篇笔记在编辑器里
        有排版、在列表下面却是源码（`#` 和 ``` 都露着）。现在先让 markdown_view
        渲染正文，再把元信息头**倒序插入到 1.0** —— 正序插会把后插的排到前面。
        """
        note = self.db.get_note(note_id)
        P = self.preview_text
        if not note:
            markdown_view.render(P, "", empty_hint="")
            return

        markdown_view.render(P, note.content, empty_hint="（这篇笔记还没有正文）")

        rule = markdown_view.rule_length(P)
        head = [(f"{note.title}\n", "pv_title")]
        head.append(((f"分类：{note.category_code} {note.category_name}").strip() or "未分类",
                     "pv_meta"))
        head.append(("\n", None))
        head.append((f"标签：{' '.join(note.tags) if note.tags else '无'}\n", "pv_meta"))
        head.append(("\n", None))
        head.append(("─" * rule + "\n", "pv_rule"))

        # 附加来源信息（如果有关联的网盘资料）
        if note.source_id:
            src = self.db.get_baidu_source(note.source_id)
            if src:
                head.append((f"来源：[{src.id}] {src.title}\n", "pv_meta"))
                head.append((f"链接：{src.link_url}\n", "pv_meta"))
                head.append((f"提取码：{src.access_code}\n", "pv_meta"))
                head.append(("\n", None))
                head.append(("─" * rule + "\n", "pv_rule"))
        head.append(("\n", None))

        P.configure(state="normal")
        for chunk, tag in reversed(head):
            if tag:
                P.insert("1.0", chunk, tag)
            else:
                P.insert("1.0", chunk)
        P.configure(state="disabled")
        P.configure(state="disabled")

    def do_search(self):
        """
        执行搜索 + 标签过滤。

        搜索时清空分类树选中状态（显示全部分类下的搜索结果）。
        """
        self._last_keyword = self.search_var.get().strip()
        self._selected_category_code = ""
        for sel in self.cat_tree.selection():
            self.cat_tree.selection_remove(sel)
        self.refresh_notes()

    def clear_search(self):
        """清空搜索框和标签过滤，恢复默认状态。"""
        self.search_var.set("")
        self.tag_filter_var.set("")
        self._last_keyword = ""
        self.refresh_notes()

    # ==========================================================================
    # 笔记 CRUD（新增 / 编辑 / 删除）
    # ==========================================================================

    def add_note(self):
        """
        打开新增笔记对话框。

        传入 default_category_code：新增时默认选中当前分类树中选中的分类，
        方便用户在同一分类下快速新增多篇笔记。
        """
        dlg = NoteEditorDialog(
            self, self.db,
            note_id=0,
            default_category_code=self._selected_category_code,
        )
        # NoteEditorDialog 销毁后，父窗口刷新列表（由 dlg 内部调用 refresh_notes）
        self.refresh_notes()

    def edit_note(self):
        """打开编辑对话框（预填现有数据）。"""
        sel = self.notes_tree.selection()
        if not sel:
            messagebox.showinfo("学习笔记", "请先选择要编辑的笔记。", parent=self)
            return
        note_id = int(sel[0])
        dlg = NoteEditorDialog(self, self.db, note_id=note_id)
        self.refresh_notes()

    def delete_note(self):
        """删除选中笔记（含确认提示）。"""
        sel = self.notes_tree.selection()
        if not sel:
            messagebox.showinfo("学习笔记", "请先选择要删除的笔记。", parent=self)
            return
        note_id = int(sel[0])
        note = self.db.get_note(note_id)
        if not messagebox.askyesno(
            "删除笔记",
            f"确定删除笔记「{note.title}」吗？\n\n此操作不可恢复。",
            parent=self,
        ):
            return
        self.db.delete_note(note_id)
        self._selected_note_id = None
        self.refresh_notes()

    # ==========================================================================
    # 外部入口
    # ==========================================================================

    def reload(self):
        """
        重新拉一遍分类树和笔记列表。

        给别的模块用：「Excel 宝典」把一轮自测整理成笔记，是**直接写库**的，
        本页要是已经建好在那儿放着，切回来时分类树和列表都还是旧的 ——
        新笔记得等下一次操作才冒出来，看着像没生成成功。
        所以在 main.py 里把本方法注册成 study_notes 页的 on_show，每次切到
        这一页都重画一遍（两个 refresh 都很轻，是几条本地 SQL）。
        """
        self.refresh_tree()
        self.refresh_notes()

    def open_baidu_disk(self):
        """
        打开百度网盘资料库管理窗口。
        由左侧分类树面板的"网盘"按钮触发。
        """
        BaiduDiskWindow(self, self.db)
