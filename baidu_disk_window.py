# -*- coding: utf-8 -*-
"""
================================================================================
百度网盘资料库管理窗口
================================================================================
独立子窗口，用于管理视频课程的百度网盘分享链接。

功能列表：
  ✓ 新增 / 编辑 / 删除网盘资料
  ✓ 关键词搜索（标题 / 标签 / 备注）
  ✓ 一键复制链接 / 提取码到剪贴板
  ✓ 在浏览器中直接打开链接
  ✓ 双击行或回车快速编辑

窗口通过 BaiduDiskWindow(parent, db) 实例化，
由 StudyNotesWindow 中的"网盘"按钮触发。

作者：代可行
日期：2026-07-14
================================================================================
"""

import re       # 用于标签输入的空格/逗号分隔解析
import webbrowser  # 系统默认浏览器打开链接
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from study_notes_db import StudyNotesDB


class BaiduDiskWindow(tk.Toplevel):
    """
    百度网盘资料库管理主窗口。

    布局结构：
        ┌─────────────────────────────────────────────────────────────┐
        │  [新增] [编辑] [删除] | [复制链接] [复制提取码] [打开链接]   │
        │              搜索: [__________] [搜索] [清空]  [关闭]       │
        ├─────────────────────────────────────────────────────────────┤
        │  ID │  标题  │  链接  │ 提取码 │  标签  │ 备注 │ 更新时间  │
        │  1  │ Python │ http:/ │  abcd  │ Python│ 进阶 │ 2026-07-14 │
        │  2  │ ...    │ ...    │ ...    │ ...   │ ...  │ ...        │
        └─────────────────────────────────────────────────────────────┘

    参数:
        parent - 父窗口（StudyNotesWindow）
        db     - StudyNotesDB 数据库实例
    """

    APP_TITLE = "百度网盘资料库"  # 对话框标题统一用这个常量

    def __init__(self, parent, db: StudyNotesDB):
        """
        初始化网盘管理窗口。

        参数:
            parent - 调用本窗口的父级 Tk/Toplevel 实例
            db     - StudyNotesDB 数据库实例（与主学习笔记窗口共用同一个实例）
        """
        super().__init__(parent)
        self.parent = parent
        self.db = db

        # 窗口基础设置
        self.title(self.APP_TITLE)
        self.geometry("1000x560")       # 初始尺寸，可由用户拖拽调整
        self.transient(parent)          # 模态窗口：显示在父窗口上方
        self.grab_set()                # 模态捕获：焦点锁定本窗口

        self._last_keyword = ""        # 上次搜索关键词（刷新时保留）

        # 构建 UI 并首次加载数据
        self.build_ui()
        self.refresh()

    # ==========================================================================
    # UI 构建
    # ==========================================================================

    def build_ui(self):
        """
        构建窗口 UI，分三个区域：工具栏、搜索栏、表格。
        采用 pack 布局管理器，按从上到下顺序排列。
        """
        # ── 顶部工具栏 ────────────────────────────────────────────────────────
        toolbar = ttk.Frame(self, padding=(10, 8, 10, 4))
        toolbar.pack(fill="x")

        # 数据操作按钮组
        ttk.Button(toolbar, text="新增",   command=self.add_source).pack(side="left", padx=3)
        ttk.Button(toolbar, text="编辑",   command=self.edit_source).pack(side="left", padx=3)
        ttk.Button(toolbar, text="删除",   command=self.delete_source).pack(side="left", padx=3)

        # 分隔符（视觉区分按钮组）
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        # 快捷操作按钮组
        ttk.Button(toolbar, text="复制链接",    command=self.copy_link).pack(side="left", padx=3)
        ttk.Button(toolbar, text="复制提取码", command=self.copy_code).pack(side="left", padx=3)
        ttk.Button(toolbar, text="打开链接",   command=self.open_link).pack(side="left", padx=3)

        # 分隔符 + 搜索区域
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(toolbar, text="搜索:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()  # 绑定搜索框变量
        ttk.Entry(toolbar, textvariable=self.search_var, width=28).pack(side="left", padx=4)
        ttk.Button(toolbar, text="搜索", command=self.do_search).pack(side="left", padx=3)
        ttk.Button(toolbar, text="清空", command=self.clear_search).pack(side="left", padx=3)

        # 关闭按钮靠右
        ttk.Button(toolbar, text="关闭", command=self.destroy).pack(side="right", padx=3)

        # ── 数据表格区域 ──────────────────────────────────────────────────────
        content = ttk.Frame(self, padding=(10, 0, 10, 10))
        content.pack(fill="both", expand=True)

        # 定义列：列ID → (列标题, 列宽)
        columns = ("id", "title", "link_url", "access_code", "tags", "note", "updated_at")
        col_meta = {
            "id":           ("ID",      50),
            "title":        ("标题",   240),
            "link_url":     ("链接",   280),
            "access_code":  ("提取码",  80),
            "tags":         ("标签",   160),
            "note":         ("备注",   160),
            "updated_at":   ("更新时间", 130),
        }

        # Treeview 表格
        self.tree = ttk.Treeview(
            content,
            columns=columns,
            show="headings",   # 只显示表头，不显示第一列树形图标
            height=18,         # 可见行数
            selectmode="browse"  # 单选模式（与数据库行一一对应）
        )
        self.tree.pack(side="left", fill="both", expand=True)

        # 配置每列的标题文本、宽度、对齐方式
        for col in columns:
            text, width = col_meta[col]
            self.tree.heading(col, text=text)
            # ID / 提取码 / 更新时间居中，其余左对齐
            anchor = "center" if col in ("id", "access_code", "updated_at") else "w"
            self.tree.column(col, width=width, anchor=anchor)

        # 垂直滚动条（绑定 Treeview 的 yview）
        vbar = ttk.Scrollbar(content, orient="vertical", command=self.tree.yview)
        vbar.pack(fill="y", side="right")
        self.tree.configure(yscrollcommand=vbar.set)

        # 双击行或按回车 → 打开编辑对话框
        self.tree.bind("<Double-1>",       lambda _: self.edit_source())
        self.tree.bind("<Return>",         lambda _: self.edit_source())

    # ==========================================================================
    # 数据刷新
    # ==========================================================================

    def refresh(self):
        """
        清空表格后重新加载数据显示。
        在搜索、新增、编辑、删除操作后调用，确保界面与数据库同步。
        """
        # 清除所有现有行
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 从数据库获取数据（带搜索关键词过滤）
        sources = self.db.fetch_baidu_sources(self._last_keyword)

        # 逐行插入 Treeview
        for src in sources:
            self.tree.insert(
                "",
                "end",                      # 插入到末尾
                iid=str(src.id),            # 行 ID 用记录 ID，方便后续操作
                values=(
                    src.id,
                    src.title,
                    src.link_url,
                    src.access_code,
                    src.tags_str(),          # 标签列表转空格分隔字符串
                    src.note,
                    # 更新时间只显示到分钟（去掉秒）
                    src.updated_at[:16] if src.updated_at else "",
                ),
            )

    # ==========================================================================
    # 搜索
    # ==========================================================================

    def do_search(self):
        """读取搜索框内容并刷新列表（模糊匹配标题/标签/备注）。"""
        self._last_keyword = self.search_var.get().strip()
        self.refresh()

    def clear_search(self):
        """清空搜索框并显示全部记录。"""
        self.search_var.set("")
        self._last_keyword = ""
        self.refresh()

    # ==========================================================================
    # 行选择辅助
    # ==========================================================================

    def get_selected_id(self) -> int | None:
        """
        获取当前选中行的记录 ID。

        若无选中行，弹出提示并返回 None。
        所有操作方法（edit / delete / copy_* / open_link）开头调用此方法做守卫检查。
        """
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(self.APP_TITLE, "请先选择一条记录。", parent=self)
            return None
        return int(sel[0])

    # ==========================================================================
    # 数据操作（新增 / 编辑 / 删除）
    # ==========================================================================

    def add_source(self):
        """
        打开新增对话框，用户填写完成后将数据写入数据库并刷新列表。
        新增成功后自动定位并选中该行（方便用户继续编辑）。
        """
        dlg = BaiduSourceDialog(self, "新增网盘资料")
        if dlg.result:
            src_id = self.db.add_baidu_source(dlg.result)
            self.refresh()
            self._select_row(src_id)  # 新增后自动选中该行

    def edit_source(self):
        """
        编辑选中行：弹出预填对话框，保存后更新数据库并刷新列表。
        """
        src_id = self.get_selected_id()
        if src_id is None:
            return

        src = self.db.get_baidu_source(src_id)
        if not src:
            return

        # 构造预填数据
        payload = dict(
            title=src.title,
            link_url=src.link_url,
            access_code=src.access_code,
            tags=list(src.tags),  # 列表复制一份，避免意外修改原对象
            note=src.note,
        )
        dlg = BaiduSourceDialog(self, "编辑网盘资料", initial=payload)
        if dlg.result:
            self.db.update_baidu_source(src_id, dlg.result)
            self.refresh()

    def delete_source(self):
        """
        删除选中行。

        删除前确认提示，说明影响范围：
          - 该网盘资料记录被永久删除
          - 引用此资料的笔记不会被删除，仅解除关联（source_id 置为 0）
        """
        src_id = self.get_selected_id()
        if src_id is None:
            return

        confirmed = messagebox.askyesno(
            self.APP_TITLE,
            "确认删除这条网盘资料？\n\n"
            "注：引用此资料的笔记不会被删除，仅解除关联。",
            parent=self,
        )
        if not confirmed:
            return

        self.db.delete_baidu_source(src_id)
        self.refresh()

    # ==========================================================================
    # 剪贴板 / 浏览器操作
    # ==========================================================================

    def _copy_text(self, value: str, label: str):
        """
        将指定字符串复制到系统剪贴板，并显示成功提示。

        参数:
            value - 要复制的内容
            label - 提示中使用的名称（如"链接"、"提取码"）
        """
        if not value:
            messagebox.showinfo(self.APP_TITLE, f"当前没有{label}。", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update()  # 确保剪贴板内容生效（Tkinter 需要显式 update）
        messagebox.showinfo(self.APP_TITLE, f"{label}已复制到剪贴板。", parent=self)

    def copy_link(self):
        """复制选中行的网盘链接到剪贴板。"""
        src_id = self.get_selected_id()
        if src_id is None:
            return
        src = self.db.get_baidu_source(src_id)
        if src:
            self._copy_text(src.link_url, "链接")

    def copy_code(self):
        """复制选中行的提取码到剪贴板。"""
        src_id = self.get_selected_id()
        if src_id is None:
            return
        src = self.db.get_baidu_source(src_id)
        if src:
            self._copy_text(src.access_code, "提取码")

    def open_link(self):
        """
        在系统默认浏览器中打开选中行的网盘链接。

        自动处理：
          - 链接为空时提示用户
          - 链接未带协议头时自动补 https://
        """
        src_id = self.get_selected_id()
        if src_id is None:
            return

        src = self.db.get_baidu_source(src_id)
        if not src or not src.link_url:
            messagebox.showinfo(self.APP_TITLE, "当前没有链接。", parent=self)
            return

        url = src.link_url
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)

    # ==========================================================================
    # 行选中定位
    # ==========================================================================

    def _select_row(self, src_id: int):
        """
        根据记录 ID 定位并选中 Treeview 中对应的行。

        参数:
            src_id - 数据库记录的主键 ID
        """
        self.tree.selection_set(str(src_id))
        self.tree.focus(str(src_id))


# =============================================================================
# 新增 / 编辑对话框
# =============================================================================

class BaiduSourceDialog(simpledialog.Dialog):
    """
    百度网盘资料的新增/编辑对话框。

    复用同一个对话框类，通过 initial 参数区分：
      - initial=None / {} → 新增模式
      - initial=dict(...)  → 编辑模式（预填现有数据）

    表单字段：
        标题（必填）| 链接 | 提取码 | 标签 | 备注

    标签输入支持多种分隔符：空格、逗号（,）、中文逗号（，）、
    分号（;），自动统一处理。
    """

    def __init__(self, parent, title: str, initial: dict | None = None):
        """
        初始化对话框。

        参数:
            parent   - 父窗口
            title    - 对话框标题文本
            initial  - 预填数据字典；None 或空字典表示新增模式
        """
        self.initial = initial or {}
        self.result = None  # 保存后填充，供调用方读取
        super().__init__(parent, title)

    def body(self, master):
        """
        构建对话框主体内容（由 simpledialog.Dialog 自动调用）。

        返回值:
            焦点默认聚焦的控件（本方法返回的 Widget）
        """
        self.entries = {}

        # 定义表单字段：(字段键名, 标签文本, 输入框宽度)
        fields = [
            ("title",       "标题（必填）",                                56),
            ("link_url",    "百度网盘链接",                                 56),
            ("access_code", "提取码",                                       20),
            ("tags",        "标签（空格 / 逗号分隔，如: JAVA 教程 入门）",    56),
            ("note",        "备注",                                         56),
        ]

        for row_idx, (field_key, label_text, width) in enumerate(fields):
            ttk.Label(master, text=label_text).grid(
                row=row_idx, column=0, sticky="nw", padx=8, pady=5
            )
            entry = ttk.Entry(master, width=width)
            entry.grid(row=row_idx, column=1, sticky="ew", padx=8, pady=5)
            # 预填已有数据（编辑模式）
            entry.insert(0, self.initial.get(field_key, ""))
            self.entries[field_key] = entry

        # 让第二列（输入框列）自动撑满宽度
        master.columnconfigure(1, weight=1)

        # 默认聚焦标题输入框
        return self.entries["title"]

    def validate(self):
        """
        点击"确定"按钮时自动调用，用于校验表单数据。

        返回:
            True  → 继续调用 apply()，关闭对话框
            False → 停留对话框，不关闭
        """
        if not self.entries["title"].get().strip():
            messagebox.showwarning(
                "百度网盘资料库",
                "标题不能为空。",
                parent=self,
            )
            return False
        return True

    def apply(self):
        """
        校验通过后自动调用，将表单数据构造成 payload 字典保存到 self.result。
        调用方（BaiduDiskWindow）通过 dlg.result 读取用户提交的数据。
        """
        tags_text = self.entries["tags"].get().strip()
        # 支持多种分隔符：空格、逗号、中文逗号、分号
        tags = [
            t.strip() for t in re.split(r"[\s,，；;]+", tags_text)
            if t.strip()
        ]

        self.result = {
            "title":       self.entries["title"].get().strip(),
            "link_url":    self.entries["link_url"].get().strip(),
            "access_code": self.entries["access_code"].get().strip(),
            "tags":        tags,
            "note":        self.entries["note"].get().strip(),
        }
