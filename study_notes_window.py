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
  ✓ Markdown 原生编辑（代码高亮友好字体 Consolas）
  ✓ Ctrl+V 粘贴截图 → 自动保存为 PNG → 插入 Markdown 图片语法
  ✓ 插入本地图片路径、分隔线、代码块
  ✓ 浏览器预览（Markdown → HTML 转换）
  ✓ 笔记可关联百度网盘资料来源

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

from study_notes_db import StudyNotesDB, StudyCategory
from baidu_disk_window import BaiduDiskWindow
from ui_theme import MAIN_PALETTE as PALETTE

# 排版常量：字体族沿用全站 token，避免同一页出现两个「雅黑」
FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"

# 行内 Markdown 语法（预览区混排用）。**分支顺序即优先级**：先认行内代码，
# 再认图片 / 链接，最后才是加粗与斜体 —— 顺序反了 `code` 里带星号、
# 或 `**粗体**` 里嵌反引号这类写法就会切错。
_INLINE_PATTERN = re.compile(
    r"(`[^`]+`)"
    r"|(!\[[^\]]*\]\([^)]*\))"
    r"|(\[[^\]]+\]\([^)]*\))"
    r"|(\*\*[^*]+\*\*)"
    r"|(\*[^*]+\*)"
)


# =============================================================================
# 工具函数
# =============================================================================

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
        self.update_idletasks()
        parent = self.master
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

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
        self.geometry("1100x720")
        self.transient(parent)   # 模态窗口
        self.grab_set()          # 焦点捕获

        self.build_ui()
        self._populate()
        self._save_original_values()  # 保存原始值，用于关闭时判断是否真的修改了

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
        构建编辑器 UI，从上到下分三块：
          1. 元信息行（标题 / 分类 / 标签 / 来源下拉框）
          2. Markdown 编辑区（Text + 滚动条）
          3. 底部按钮栏 + 状态栏
        """

        # ── 元信息行 ──────────────────────────────────────────────────────────
        meta_frame = ttk.Frame(self, padding=(10, 8, 10, 4))
        meta_frame.pack(fill="x")

        # 标题输入框
        ttk.Label(meta_frame, text="标题:").pack(side="left", padx=(0, 4))
        self.title_var = tk.StringVar()
        ttk.Entry(meta_frame, textvariable=self.title_var, width=40).pack(side="left", padx=(0, 12))

        # 分类下拉框（readonly，不可手动输入，保证编码一致性）
        ttk.Label(meta_frame, text="分类:").pack(side="left", padx=(0, 4))
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(
            meta_frame, textvariable=self.category_var,
            state="readonly", width=30
        )
        self.category_combo.pack(side="left", padx=(0, 12))
        self._fill_category_combo()  # 填充分类选项

        # 标签输入框（空格分隔）
        ttk.Label(meta_frame, text="标签:").pack(side="left", padx=(0, 4))
        self.tags_var = tk.StringVar()
        ttk.Entry(meta_frame, textvariable=self.tags_var, width=30).pack(side="left", padx=(0, 12))

        # 来源下拉框（关联百度网盘资料）
        ttk.Label(meta_frame, text="来源:").pack(side="left", padx=(0, 4))
        self.source_var = tk.StringVar(value="")
        self.source_combo = ttk.Combobox(meta_frame, textvariable=self.source_var, width=28)
        self.source_combo.pack(side="left", padx=(0, 12))
        self._fill_source_combo()  # 填充网盘资料选项

        # ── Markdown 编辑区 ──────────────────────────────────────────────────
        editor_frame = ttk.Frame(self, padding=(10, 4, 10, 4))
        editor_frame.pack(fill="both", expand=True, side="top")

        # 操作提示
        tip = ttk.Label(
            editor_frame,
            text="Markdown 编辑区  |  "
                 "Ctrl+V 粘贴截图自动插入  |  "
                 "支持本地图片路径或 Base64",
            foreground=PALETTE.text_muted,
            font=(FONT_FAMILY, 9),
        )
        tip.pack(anchor="w", pady=(0, 4))

        # 横向 PanedWindow：左侧编辑区，右侧预览区（默认隐藏）
        self.paned = ttk.PanedWindow(editor_frame, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        # ── 左：Markdown 文本编辑区 ────────────────────────────────────────
        text_frame = ttk.Frame(self.paned)

        self.text_area = tk.Text(
            text_frame,
            wrap="word",              # 自动换行（按单词边界）
            font=(MONO_FAMILY, 11),   # 等宽字体，适合 Markdown 书写
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
        self.preview_frame = ttk.Frame(self.paned)

        preview_header = ttk.Frame(self.preview_frame)
        preview_header.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(
            preview_header, text="渲染预览（Markdown 效果）",
            foreground=PALETTE.text_secondary,
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(side="left")

        preview_text_frame = ttk.Frame(self.preview_frame)
        preview_text_frame.pack(fill="both", expand=True, padx=6, pady=4)

        self.preview_area = tk.Text(
            preview_text_frame,
            wrap="word",
            font=(FONT_FAMILY, 10),
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE.border,
            padx=18,
            pady=16,
            background=PALETTE.surface,  # 预览区当纸看，纯白最接近 Typora 的观感
            state="disabled",        # 只读
        )
        preview_vbar = ttk.Scrollbar(
            preview_text_frame, orient="vertical", command=self.preview_area.yview
        )
        self.preview_area.configure(yscrollcommand=preview_vbar.set)
        self.preview_area.pack(side="left", fill="both", expand=True)
        preview_vbar.pack(side="right", fill="y")

        # 配置 Markdown 渲染 tag
        self._setup_preview_tags()

        # 拦截 Ctrl+V：优先检测剪贴板图片；键盘输入正常透传
        self.text_area.bind("<Control-v>", self._on_ctrl_v)
        # 内容变化时：标记修改 + 实时刷新预览（仅预览可见时）
        self.text_area.bind(
            "<KeyRelease>",
            lambda _: (self._mark_changed(), self._refresh_preview_if_shown())
        )
        self.title_var.trace_add("write", lambda *_: self._mark_changed())

        # ── 底部按钮栏 ───────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(10, 8, 10, 10))
        btn_frame.pack(fill="x")

        # 左侧：快捷编辑工具
        ttk.Button(btn_frame, text="插入图片路径",  command=self._insert_image_path).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="插入分隔线",    command=self._insert_hr).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="插入代码块",    command=self._insert_code_block).pack(side="left", padx=4)
        self.toggle_preview_btn = ttk.Button(
            btn_frame, text="显示效果", command=self._toggle_preview
        )
        self.toggle_preview_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="浏览器预览",    command=self._preview_markdown).pack(side="left", padx=4)

        # 右侧：保存 / 取消
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="取消", command=self._on_close).pack(side="right", padx=4)

        # 状态栏（显示笔记 ID 或新建提示）
        status_text = (
            f"  [笔记ID: {self.note_id}]  " if self.note_id
            else "  [新建笔记]  "
        )
        self.status_var = tk.StringVar(value=status_text)
        ttk.Label(btn_frame, textvariable=self.status_var,
                  foreground=PALETTE.text_muted).pack(side="left", padx=8)

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
        插入 Markdown 代码块，并将光标移到代码内容区域（中间那行）。
        效果：
            ```
            {光标在这里}
            ```
        """
        self.text_area.insert(self.text_area.index("insert"), "\n```\n\n```\n")
        self.text_area.edit_separator()  # 记录撤销分隔点
        # 将光标上移一行（移到空代码内容行）
        cur = self.text_area.index("insert")
        parts = cur.split(".")
        parts[1] = str(int(parts[1]) - 2)
        self.text_area.mark_set("insert", ".".join(parts))
        self.text_area.see("insert")

    # ── Markdown 预览 ────────────────────────────────────────────────────────

    def _setup_preview_tags(self):
        """
        为预览 Text 控件配置 Markdown 渲染所需的 tag 样式。
        """
        p = self.preview_area
        # ★ tag 优先级 = 创建顺序（后建的覆盖先建的）。因此**容器 tag 必须
        #   先建、行内 tag 必须后建**：否则列表项里的 `code` 会被 li 的字体
        #   盖掉，反引号里的字就不会变等宽。
        # ── 容器 ──────────────────────────────────────────────────────────
        p.tag_configure("text", font=(FONT_FAMILY, 10))
        # 段间距交给 spacing3，不靠空行，读起来才有 Typora 那种松弛感
        p.tag_configure("p", font=(FONT_FAMILY, 10), spacing1=2, spacing3=10,
                        lmargin1=2, lmargin2=2)
        p.tag_configure("li", font=(FONT_FAMILY, 10), lmargin1=18, lmargin2=30, spacing3=5)
        # tk.Text 不能给 tag 画左边框，引用块的书脊线由渲染时插入的「▎」承担
        p.tag_configure("quote", font=(FONT_FAMILY, 10), foreground=PALETTE.text_secondary,
                        lmargin1=14, lmargin2=14, background="#f7f7f7",
                        spacing1=6, spacing3=6)
        p.tag_configure("quote_bar", font=(FONT_FAMILY, 10), foreground="#cfcfcf",
                        lmargin1=14, lmargin2=14, background="#f7f7f7",
                        spacing1=6, spacing3=6)
        # 去掉 relief="solid"：Tk 的 tag 边框色不可控，一律渲染成深色硬边
        p.tag_configure("codeblock", font=(MONO_FAMILY, 10), background=PALETTE.surface_alt,
                        foreground=PALETTE.text_primary,
                        lmargin1=12, lmargin2=12, spacing1=8, spacing3=8)
        p.tag_configure("hr", font=(FONT_FAMILY, 9), foreground="#dcdcdc",
                        justify="center", spacing1=12, spacing3=12)
        # ── 标题 H1~H6 ────────────────────────────────────────────────────
        # 旧版给六级标题配了六个不同灰度，层级全靠"变灰"表达 —— 那既不好看，
        # 也让正文一多就分不出主次。改为：字色统一 text_primary，层级只用
        # 「字号 + 段间距」，只把最末两级降为次级 / 弱化色。
        p.tag_configure("h1", font=(FONT_FAMILY, 16, "bold"), spacing1=18, spacing3=8,
                        foreground=PALETTE.text_primary)
        p.tag_configure("h2", font=(FONT_FAMILY, 14, "bold"), spacing1=16, spacing3=6,
                        foreground=PALETTE.text_primary)
        p.tag_configure("h3", font=(FONT_FAMILY, 12, "bold"), spacing1=14, spacing3=5,
                        foreground=PALETTE.text_primary)
        p.tag_configure("h4", font=(FONT_FAMILY, 11, "bold"), spacing1=12, spacing3=4,
                        foreground=PALETTE.text_primary)
        p.tag_configure("h5", font=(FONT_FAMILY, 10, "bold"), spacing1=10, spacing3=3,
                        foreground=PALETTE.text_secondary)
        p.tag_configure("h6", font=(FONT_FAMILY, 10, "bold"), spacing1=10, spacing3=3,
                        foreground=PALETTE.text_muted)
        # ── 行内（优先级最高，必须最后建）──────────────────────────────────
        p.tag_configure("bold", font=(FONT_FAMILY, 10, "bold"))
        p.tag_configure("italic", font=(FONT_FAMILY, 10, "italic"))
        p.tag_configure("strike", font=(FONT_FAMILY, 10, "overstrike"),
                        foreground=PALETTE.text_muted)
        # 旧版是 #c7254e 品红前景 + 灰底，全站仅有的彩色之一；改为一律正文色，
        # 靠浅灰底表达"这是代码"就够了。
        p.tag_configure("code", font=(MONO_FAMILY, 10), background=PALETTE.surface_alt,
                        foreground=PALETTE.text_primary)
        # 链接色取 palette.link（极低饱和墨蓝）——纯灰链接在正文里只剩"可点"
        # 没有"可辨"，高饱和蓝又和纯灰阶冲突，这个值是两个极端之间的落点。
        p.tag_configure("image", font=(FONT_FAMILY, 10, "italic"), foreground=PALETTE.link)
        p.tag_configure("link", font=(FONT_FAMILY, 10, "underline"), foreground=PALETTE.link)

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

    def _refresh_preview_if_shown(self):
        """
        仅在预览可见时刷新预览内容（避免不必要的渲染开销）。
        """
        if self.preview_visible:
            self._render_preview()

    def _render_preview(self):
        """
        将 Markdown 文本渲染到预览区域（不调外部浏览器）。
        使用 tk.Text + tag 模拟 Markdown 效果。
        """
        content = self.text_area.get("1.0", "end-1c")
        p = self.preview_area
        p.configure(state="normal")
        p.delete("1.0", "end")

        if not content.strip():
            p.insert("1.0", "（笔记内容为空）", "text")
            p.configure(state="disabled")
            return

        import re as _re
        # 按代码块分段处理
        parts = _re.split(r"(```[\w]*\n.*?```)", content, flags=_re.DOTALL)
        for part in parts:
            if not part:
                continue
            code_match = _re.match(r"```([\w]*)\n(.*?)```", part, flags=_re.DOTALL)
            if code_match:
                lang = code_match.group(1) or ""
                code = code_match.group(2).rstrip("\n")
                if lang:
                    p.insert("end", f"⟨{lang}⟩\n", ("codeblock",))
                else:
                    p.insert("end", "\n", ("codeblock",))
                p.insert("end", code + "\n\n", "codeblock")
                continue
            self._render_markdown_block(p, part)

        p.configure(state="disabled")

    def _render_markdown_block(self, text_widget, block: str):
        """
        渲染一个不含代码块的 Markdown 片段（按行处理）。
        """
        import re as _re
        lines = block.split("\n")
        list_buffer = []

        def flush_list():
            if not list_buffer:
                return
            for item in list_buffer:
                text_widget.insert("end", "• ", "li")
                self._insert_inline(text_widget, item, "li")
                text_widget.insert("end", "\n", "li")
            list_buffer.clear()

        for line in lines:
            stripped = line.strip()
            if _re.match(r"^-{3,}$", stripped):
                flush_list()
                text_widget.insert("end", "─" * 40 + "\n", "hr")
                continue
            m = _re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if m:
                flush_list()
                level = len(m.group(1))
                text = m.group(2).strip()
                tag = f"h{level}"
                self._insert_inline(text_widget, text, tag)
                text_widget.insert("end", "\n\n", tag)
                continue
            if stripped.startswith(">"):
                flush_list()
                quote_text = _re.sub(r"^>\s?", "", stripped)
                # tk.Text 无法给 tag 画左边框，用「▎」当书脊线；两段共用同一组
                # lmargin/背景/间距，拼在同一行里看不出接缝。
                text_widget.insert("end", "▎ ", ("quote", "quote_bar"))
                self._insert_inline(text_widget, quote_text, "quote")
                text_widget.insert("end", "\n", "quote")
                continue
            m = _re.match(r"^[-*+]\s+(.+)$", stripped)
            if m:
                list_buffer.append(m.group(1))
                continue
            m = _re.match(r"^\d+\.\s+(.+)$", stripped)
            if m:
                list_buffer.append(m.group(1))
                continue
            if stripped == "":
                flush_list()
                text_widget.insert("end", "\n", "p")
                continue
            flush_list()
            self._insert_inline(text_widget, stripped, "p")
            text_widget.insert("end", "\n", "p")

        flush_list()

    def _insert_inline(self, text_widget, text: str, base_tag: str) -> None:
        """
        把一行文本按行内 Markdown 语法**分段插入**，让加粗 / 斜体 / 行内代码 /
        链接 / 图片占位真正带上各自的 tag。

        旧实现 `_inline_md()` 只是把标记符号删掉后返回纯字符串，也就是那些
        行内 tag 配了却从来没被使用过 —— 预览里加粗和正文长得一模一样。
        改成逐段插入后，混排才有可能。
        """
        pos = 0
        for m in _INLINE_PATTERN.finditer(text):
            if m.start() > pos:
                text_widget.insert("end", text[pos:m.start()], base_tag)
            seg = m.group(0)
            if seg.startswith("`"):
                text_widget.insert("end", seg[1:-1], ("code", base_tag))
            elif seg.startswith("!["):
                label = re.match(r"!\[([^\]]*)\]", seg).group(1)
                text_widget.insert("end", f"[图片: {label}]", ("image", base_tag))
            elif seg.startswith("["):
                label = re.match(r"\[([^\]]+)\]", seg).group(1)
                text_widget.insert("end", label, ("link", base_tag))
            elif seg.startswith("**"):
                text_widget.insert("end", seg[2:-2], ("bold", base_tag))
            else:
                text_widget.insert("end", seg[1:-1], ("italic", base_tag))
            pos = m.end()
        if pos < len(text):
            text_widget.insert("end", text[pos:], base_tag)

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
        将 Markdown 文本转换为带样式的 HTML 字符串。

        实现说明：
          - 使用 re.sub 逐条正则替换；
          - 标题替换从高到低（6→1）进行，避免 # 一级被 ###### 六级错误匹配；
          - 本地图片路径自动转为绝对路径（file:/// 协议）。

        参数:
            content - Markdown 原始文本
        返回:
            完整 HTML 字符串（含 DOCTYPE、head、body、embedded CSS）
        """
        import html as html_mod
        h = html_mod.escape(content)

        # 代码块（```lang\ncode\n```），需先于行内代码处理
        h = re.sub(
            r"```(\w*)\n(.*?)```",
            lambda m: f'<pre><code class="lang-{m.group(1)}">'
                     f'{html_mod.escape(m.group(2))}</code></pre>',
            h, flags=re.DOTALL
        )
        # 行内代码
        h = re.sub(r"`([^`]+)`", r"<code>\1</code>", h)
        # 标题（H6 → H1，逆序防止嵌套错误匹配）
        for lvl in range(6, 0, -1):
            h = re.sub(
                r"^" + r"#" * lvl + r"\s+(.+)$",
                lambda m: f"<h{lvl}>{m.group(1)}</h{lvl}>",
                h, flags=re.MULTILINE
            )
        # 加粗
        h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
        # 斜体
        h = re.sub(r"\*(.+?)\*", r"<em>\1</em>", h)
        # 图片（本地路径转绝对路径再渲染）
        def img_sub(m):
            src = m.group(1)
            if not (src.startswith("http://") or src.startswith("https://")):
                db_dir = Path(self.db.db_path).parent
                img_path = db_dir / src
                if img_path.exists():
                    src = str(img_path).replace("\\", "/")
            return f'<img src="{src}" style="max-width:100%;border-radius:6px;" />'
        h = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", img_sub, h)
        # 链接
        h = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', h)
        # 段落（两个换行之间视为段落边界）
        h = h.replace("\n\n", "</p><p>")
        h = f"<p>{h}</p>"
        h = re.sub(r"<p>\s*</p>", "", h)
        # 水平线
        h = re.sub(r"^-{3,}$", "<hr>", h, flags=re.MULTILINE)

        html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    max-width: 760px;
    margin: 48px auto;
    padding: 0 24px;
    background: #ffffff;
    color: #1c1c1c;
    line-height: 1.75;
    font-size: 15px;
  }}
  h1,h2,h3,h4,h5,h6 {{ font-weight: 600; color: #1c1c1c; margin: 1.6em 0 .6em }}
  h1 {{ font-size: 1.7em; padding-bottom: .35em; border-bottom: 1px solid #ececec }}
  h2 {{ font-size: 1.4em; padding-bottom: .3em; border-bottom: 1px solid #f0f0f0 }}
  h3 {{ font-size: 1.2em }}
  h4,h5,h6 {{ font-size: 1em }}
  h5 {{ color: #6b6b6b }}
  h6 {{ color: #9a9a9a }}
  p {{ margin: .8em 0 }}
  pre {{ background: #f7f7f7; border: 1px solid #efefef; border-radius: 8px;
        padding: 16px; overflow-x: auto }}
  code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 4px; font-size: .9em;
         font-family: Consolas, "Courier New", monospace }}
  pre code {{ background: none; padding: 0 }}
  img {{ max-width: 100%; border-radius: 8px }}
  a {{ color: #4f6b85 }}
  hr {{ border: none; border-top: 1px solid #ececec; margin: 28px 0 }}
  blockquote {{ border-left: 3px solid #e2e2e2; margin: 1em 0;
               padding: .2em 18px; color: #6b6b6b }}
</style>
</head>
<body>
{h}
</body>
</html>"""
        return html

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
            height=10,
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
        preview_frame = ttk.LabelFrame(frame, text="笔记预览", padding=(10, 4, 10, 8))
        preview_frame.pack(fill="both", expand=False, padx=10, pady=(0, 8))

        preview_inner = ttk.Frame(preview_frame)
        preview_inner.pack(fill="both", expand=True)
        self.preview_text = tk.Text(
            preview_inner,
            wrap="word",
            relief="flat",
            state="disabled",   # 只读模式
            font=(FONT_FAMILY, 10),
            bg=PALETTE.surface_alt,
            height=12,
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
            if note_count > 0:
                label = f"{label}  ({note_count})"
            iid = str(cat.id)
            # values 存 code 和 level（隐藏列，供后续逻辑读取）
            self.cat_tree.insert(parent_iid, "end", iid=iid, text=label, values=(cat.code, cat.level))
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
        """
        item = self.cat_tree.identify_row(event.y)
        if not item:
            return
        self.cat_tree.selection_set(item)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="新增子分类", command=self.add_category)
        menu.add_command(label="编辑分类",   command=self.edit_category)
        menu.add_separator()
        menu.add_command(label="删除分类",   command=self.delete_category)
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
        """编辑选中分类的名称和排序号。"""
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo("分类管理", "请先选择要编辑的分类。", parent=self)
            return
        cat_id = int(sel[0])
        cat = self.db.get_category(cat_id)
        if not cat:
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
        """
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo("分类管理", "请先选择要删除的分类。", parent=self)
            return
        cat_id = int(sel[0])
        cat = self.db.get_category(cat_id)
        if not cat:
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
        """底部预览面板的 tag：标题 / 元信息 / 发丝线 / 正文，纯灰阶。"""
        p = self.preview_text
        p.tag_configure("pv_title", font=(FONT_FAMILY, 12, "bold"),
                        foreground=PALETTE.text_primary, spacing3=6)
        p.tag_configure("pv_meta", font=(FONT_FAMILY, 9),
                        foreground=PALETTE.text_muted, spacing3=2)
        p.tag_configure("pv_rule", font=(FONT_FAMILY, 9),
                        foreground="#e2e2e2", spacing1=6, spacing3=6)
        p.tag_configure("pv_body", font=(FONT_FAMILY, 10),
                        foreground=PALETTE.text_primary, spacing1=4)

    def _show_preview(self, note_id: int):
        """
        在底部只读 Text 中渲染笔记内容。

        渲染格式：
            # 标题
            分类：编码 名称
            标签：空格分隔的标签

            ─────────────────────────
            来源：[ID] 标题
            链接：https://...
            提取码：xxxx

            ─────────────────────────
            正文内容（Markdown）
        """
        note = self.db.get_note(note_id)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        if not note:
            self.preview_text.configure(state="disabled")
            return

        # 旧版是把 Markdown 原文（含 "# 标题"）整段倒出来，没有排版。
        # 改为逐段带 tag 插入，让这块面板也读起来像一篇文档。
        P = self.preview_text
        P.insert("end", f"{note.title}\n", "pv_title")
        meta_cat = f"分类：{note.category_code} {note.category_name}".strip() or "未分类"
        P.insert("end", meta_cat, "pv_meta")
        P.insert("end", "\n")
        tags = " ".join(note.tags) if note.tags else "无"
        P.insert("end", f"标签：{tags}\n", "pv_meta")
        P.insert("end", "\n")
        P.insert("end", "─" * 60 + "\n", "pv_rule")

        # 附加来源信息（如果有关联的网盘资料）
        if note.source_id:
            src = self.db.get_baidu_source(note.source_id)
            if src:
                P.insert("end", f"来源：[{src.id}] {src.title}\n", "pv_meta")
                P.insert("end", f"链接：{src.link_url}\n", "pv_meta")
                P.insert("end", f"提取码：{src.access_code}\n", "pv_meta")
                P.insert("end", "\n")
                P.insert("end", "─" * 60 + "\n", "pv_rule")

        P.insert("end", "\n")
        P.insert("end", note.content, "pv_body")
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

    def open_baidu_disk(self):
        """
        打开百度网盘资料库管理窗口。
        由左侧分类树面板的"网盘"按钮触发。
        """
        BaiduDiskWindow(self, self.db)
