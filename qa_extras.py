# -*- coding: utf-8 -*-
"""
================================================================================
Q&A + 工作纪要 + 练习记录 扩展功能
================================================================================
在 qa_work_log_page.py 基础上增加：
  - 顶部全局模糊搜索栏（跨 4 表：练习/笔记/心得/Q&A）
  - 工作笔记标签页（结构化：标题/正文/TAG/关联练习）
  - 练习记录页图片上传（多张，存储到 practice_images/ 子目录）
  - 复习心得标签页（独立记录，可关联到练习）
================================================================================
"""

import os
import re
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from datetime import datetime
from typing import List, Optional

from qa_work_log_db import (
    QAWorkLogDBExt, WorkNote, PracticeReview, GlobalSearchResult, _today
)


# 图片存储根目录（与主程序同级的 media 子目录）
PRACTICE_IMAGES_DIR = "practice_images"


def _ensure_images_dir(root: str = ".") -> str:
    """确保图片目录存在，返回绝对路径"""
    abs_dir = os.path.join(os.path.abspath(root), PRACTICE_IMAGES_DIR)
    os.makedirs(abs_dir, exist_ok=True)
    return abs_dir


def _save_image(src_path: str, root: str = ".") -> Optional[str]:
    """
    复制图片到 practice_images/，返回相对路径（用于数据库存储）。
    文件名格式：practice_<时间戳>_<原文件名>
    """
    if not src_path or not os.path.isfile(src_path):
        return None
    abs_dir = _ensure_images_dir(root)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18]
    base = os.path.basename(src_path)
    safe = re.sub(r"[^\w\.\-]", "_", base)
    dst_name = f"practice_{ts}_{safe}"
    dst_abs = os.path.join(abs_dir, dst_name)
    try:
        shutil.copy2(src_path, dst_abs)
    except Exception as e:
        messagebox.showerror("图片保存失败", str(e))
        return None
    # 返回相对路径（相对 root），便于打包后兼容
    return os.path.join(PRACTICE_IMAGES_DIR, dst_name)


# =============================================================================
# 工具：TAG 输入解析
# =============================================================================

def parse_tags(text: str) -> List[str]:
    """解析 TAG 字符串为列表（支持中英文逗号、空格分隔）"""
    if not text:
        return []
    parts = re.split(r"[,,;\s]+", text)
    return [p.strip() for p in parts if p.strip()]


def join_tags(tags: List[str]) -> str:
    """列表 → 'tag1, tag2' 字符串"""
    return ", ".join([t for t in tags if t])


# =============================================================================
# 全局搜索栏 Mixin
# =============================================================================

class GlobalSearchBarMixin:
    """提供顶部全局模糊搜索栏"""

    def build_global_search_bar(self, parent: ttk.Frame):
        """在父容器顶部构建全局搜索栏"""
        bar = ttk.Frame(parent, padding=(8, 6, 8, 4))
        bar.pack(fill="x")

        ttk.Label(bar, text="🔍 全局搜索:").pack(side="left", padx=(0, 4))
        self.global_search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.global_search_var, width=32)
        entry.pack(side="left", padx=(0, 4))
        entry.bind("<Return>", lambda e: self.do_global_search())

        ttk.Button(bar, text="搜索", command=self.do_global_search).pack(side="left", padx=2)
        ttk.Button(bar, text="清空", command=self.clear_global_search).pack(side="left", padx=2)

        ttk.Label(
            bar,
            text="提示：搜索标题/正文/TAG/日期（YYYY-MM-DD），跨 4 个模块",
            foreground="#888"
        ).pack(side="left", padx=(12, 0))

        # 搜索结果区（默认隐藏）
        self.search_result_frame = ttk.LabelFrame(parent, text="搜索结果", padding=8)
        self.search_result_tree = ttk.Treeview(
            self.search_result_frame,
            columns=("type", "title", "tags", "date"),
            show="headings",
            height=8
        )
        self.search_result_tree.heading("type", text="类型")
        self.search_result_tree.heading("title", text="标题")
        self.search_result_tree.heading("tags", text="TAG")
        self.search_result_tree.heading("date", text="日期")
        self.search_result_tree.column("type", width=80, anchor="center")
        self.search_result_tree.column("title", width=400, anchor="w")
        self.search_result_tree.column("tags", width=200, anchor="w")
        self.search_result_tree.column("date", width=120, anchor="center")
        ysb = ttk.Scrollbar(self.search_result_frame, orient="vertical",
                            command=self.search_result_tree.yview)
        self.search_result_tree.configure(yscrollcommand=ysb.set)
        self.search_result_tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")
        self.search_result_tree.bind("<Double-1>", self.on_search_result_dblclick)

    def do_global_search(self):
        kw = self.global_search_var.get().strip()
        if not kw:
            messagebox.showinfo("提示", "请输入搜索关键词")
            return
        results = self.db.global_search(kw)
        for item in self.search_result_tree.get_children():
            self.search_result_tree.delete(item)
        type_map = {
            "practice": "🎯 练习",
            "work_note": "📝 笔记",
            "review": "💡 心得",
            "qa": "❓ Q&A",
        }
        for r in results:
            self.search_result_tree.insert(
                "", "end", iid=f"{r.table}:{r.record_id}",
                values=(type_map.get(r.table, r.table), r.title, r.tags, r.date_str)
            )
        # 显示结果区
        self.search_result_frame.pack(fill="both", expand=False, padx=8, pady=(0, 4))
        if not results:
            messagebox.showinfo("搜索结果", f'未找到包含 "{kw}" 的记录')

    def clear_global_search(self):
        self.global_search_var.set("")
        for item in self.search_result_tree.get_children():
            self.search_result_tree.delete(item)
        self.search_result_frame.pack_forget()

    def on_search_result_dblclick(self, event):
        """双击搜索结果：定位到对应标签页并加载"""
        sel = self.search_result_tree.selection()
        if not sel:
            return
        iid = sel[0]
        table, rid = iid.split(":")
        rid = int(rid)
        # 切换到对应标签页
        tab_map = {
            "practice": ("练习记录", lambda: self.open_practice_detail(rid)),
            "work_note": ("工作笔记", lambda: self.open_work_note_detail(rid)),
            "review": ("复习心得", lambda: self.open_review_detail(rid)),
            "qa": ("Q&A 问答", lambda: self.open_qa_detail(rid)),
        }
        if table in tab_map:
            tab_name, callback = tab_map[table]
            # 切换 notebook 到对应 tab
            for idx in range(self.notebook.index("end")):
                if self.notebook.tab(idx, "text") == tab_name:
                    self.notebook.select(idx)
                    break
            self.after(50, callback)


# =============================================================================
# 工作笔记页
# =============================================================================

class WorkNotePanel(ttk.Frame):
    """工作笔记标签页"""

    def __init__(self, parent: ttk.Frame, db: QAWorkLogDBExt,
                 on_record_change: Optional[callable] = None):
        super().__init__(parent)
        self.db = db
        self.on_record_change = on_record_change
        self._build_ui()
        self.pack(fill="both", expand=True)
        self.refresh()

    def _build_ui(self):
        # 工具栏
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="新增笔记", command=self.add_note).pack(side="left", padx=2)
        ttk.Button(toolbar, text="编辑", command=self.edit_note).pack(side="left", padx=2)
        ttk.Button(toolbar, text="删除", command=self.delete_note).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(toolbar, text="搜索:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.search_var, width=24).pack(side="left", padx=2)
        ttk.Button(toolbar, text="刷新", command=self.refresh).pack(side="left", padx=2)
        ttk.Label(toolbar, text="（按标题/正文/TAG 过滤）", foreground="#888").pack(side="left", padx=8)

        # PanedWindow: 左列表 + 右编辑
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 左：列表
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)
        self.tree = ttk.Treeview(
            list_frame,
            columns=("id", "title", "tags", "linked", "updated"),
            show="headings", height=20
        )
        for col, txt, w in [
            ("id", "ID", 50), ("title", "标题", 240), ("tags", "TAG", 160),
            ("linked", "关联练习", 80), ("updated", "更新时间", 140)
        ]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="w" if col != "id" and col != "linked" else "center")
        ysb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # 右：编辑区
        edit_frame = ttk.LabelFrame(paned, text="笔记内容", padding=8)
        paned.add(edit_frame, weight=2)
        ttk.Label(edit_frame, text="标题:").grid(row=0, column=0, sticky="w", pady=2)
        self.title_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.title_var, width=50).grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=2, padx=(4, 0)
        )
        ttk.Label(edit_frame, text="TAG:").grid(row=1, column=0, sticky="w", pady=2)
        self.tags_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.tags_var, width=50).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=2, padx=(4, 0)
        )
        ttk.Label(edit_frame, text="关联练习 ID:").grid(row=2, column=0, sticky="w", pady=2)
        self.linked_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.linked_var, width=12).grid(
            row=2, column=1, sticky="w", pady=2, padx=(4, 0)
        )
        ttk.Label(edit_frame, text="（可留空；填写后可 TAG 互通）", foreground="#888").grid(
            row=2, column=2, sticky="w", padx=4
        )
        ttk.Label(edit_frame, text="正文:").grid(row=3, column=0, sticky="nw", pady=2)
        self.content_text = scrolledtext.ScrolledText(edit_frame, wrap="word", height=18,
                                                     font=("Microsoft YaHei UI", 10))
        self.content_text.grid(row=3, column=1, columnspan=2, sticky="nsew", pady=2, padx=(4, 0))
        edit_frame.rowconfigure(3, weight=1)
        edit_frame.columnconfigure(1, weight=1)

        btn_bar = ttk.Frame(edit_frame)
        btn_bar.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(btn_bar, text="保存", command=self.save_note).pack(side="right", padx=2)
        ttk.Button(btn_bar, text="清空", command=self.clear_form).pack(side="right", padx=2)

        self._current_id = 0

    def refresh(self):
        kw = self.search_var.get().strip()
        notes = self.db.list_work_notes(keyword=kw if kw else None)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for n in notes:
            linked = f"#{n.linked_practice_id}" if n.linked_practice_id else "-"
            self.tree.insert(
                "", "end", iid=str(n.id),
                values=(n.id, n.title, n.tags, linked, n.updated_at)
            )
        self.clear_form()

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        note_id = int(sel[0])
        n = self.db.get_work_note(note_id)
        if not n:
            return
        self._current_id = n.id
        self.title_var.set(n.title)
        self.tags_var.set(n.tags)
        self.linked_var.set(str(n.linked_practice_id) if n.linked_practice_id else "")
        self.content_text.delete("1.0", "end")
        self.content_text.insert("1.0", n.content)

    def add_note(self):
        self.clear_form()
        self._current_id = 0
        self.title_var.set("新笔记")

    def edit_note(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一条笔记")
            return
        self.on_select(None)

    def delete_note(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一条笔记")
            return
        if not messagebox.askyesno("确认", "删除选中的笔记？"):
            return
        note_id = int(sel[0])
        if self.db.delete_work_note(note_id):
            self.refresh()
            if self.on_record_change:
                self.on_record_change()

    def save_note(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("提示", "标题不能为空")
            return
        content = self.content_text.get("1.0", "end").strip()
        tags = self.tags_var.get().strip()
        try:
            linked = int(self.linked_var.get().strip() or "0")
        except ValueError:
            messagebox.showwarning("提示", "关联练习 ID 必须是数字")
            return
        note = WorkNote(
            id=self._current_id, title=title, content=content,
            tags=tags, linked_practice_id=linked
        )
        if self._current_id == 0:
            self.db.add_work_note(note)
        else:
            self.db.update_work_note(note)
        self.refresh()
        if self.on_record_change:
            self.on_record_change()
        messagebox.showinfo("已保存", f"笔记「{title}」已保存")

    def clear_form(self):
        self._current_id = 0
        self.title_var.set("")
        self.tags_var.set("")
        self.linked_var.set("")
        self.content_text.delete("1.0", "end")
        for item in self.tree.selection():
            self.tree.selection_remove(item)


# =============================================================================
# 复习心得页
# =============================================================================

class ReviewPanel(ttk.Frame):
    """复习心得标签页"""

    def __init__(self, parent: ttk.Frame, db: QAWorkLogDBExt,
                 on_record_change: Optional[callable] = None):
        super().__init__(parent)
        self.db = db
        self.on_record_change = on_record_change
        self._build_ui()
        self.pack(fill="both", expand=True)
        self.refresh()

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="新增心得", command=self.add_review).pack(side="left", padx=2)
        ttk.Button(toolbar, text="编辑", command=self.edit_review).pack(side="left", padx=2)
        ttk.Button(toolbar, text="删除", command=self.delete_review).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(toolbar, text="按 TAG 过滤:").pack(side="left", padx=(0, 4))
        self.tag_filter_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.tag_filter_var, width=20).pack(side="left", padx=2)
        ttk.Button(toolbar, text="刷新", command=self.refresh).pack(side="left", padx=2)
        ttk.Button(toolbar, text="按练习 ID 筛选", command=self.refresh_by_practice).pack(side="left", padx=2)

        # 左列表 + 右编辑
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)
        self.tree = ttk.Treeview(
            list_frame,
            columns=("id", "title", "tags", "practice_id", "date"),
            show="headings", height=20
        )
        for col, txt, w in [
            ("id", "ID", 50), ("title", "心得标题", 240), ("tags", "TAG", 160),
            ("practice_id", "关联练习", 80), ("date", "复习日期", 120)
        ]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="w" if col == "title" or col == "tags" else "center")
        ysb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        edit_frame = ttk.LabelFrame(paned, text="心得内容", padding=8)
        paned.add(edit_frame, weight=2)
        ttk.Label(edit_frame, text="标题:").grid(row=0, column=0, sticky="w", pady=2)
        self.title_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.title_var, width=50).grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=2, padx=(4, 0)
        )
        ttk.Label(edit_frame, text="关联练习 ID:").grid(row=1, column=0, sticky="w", pady=2)
        self.practice_id_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.practice_id_var, width=12).grid(
            row=1, column=1, sticky="w", pady=2, padx=(4, 0)
        )
        ttk.Label(edit_frame, text="复习日期:").grid(row=1, column=2, sticky="e", padx=(8, 0))
        self.date_var = tk.StringVar(value=_today())
        ttk.Entry(edit_frame, textvariable=self.date_var, width=14).grid(
            row=1, column=3, sticky="w", pady=2, padx=(4, 0)
        )
        ttk.Label(edit_frame, text="TAG:").grid(row=2, column=0, sticky="w", pady=2)
        self.tags_var = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.tags_var, width=50).grid(
            row=2, column=1, columnspan=3, sticky="ew", pady=2, padx=(4, 0)
        )
        ttk.Label(edit_frame, text="正文:").grid(row=3, column=0, sticky="nw", pady=2)
        self.content_text = scrolledtext.ScrolledText(edit_frame, wrap="word", height=18,
                                                     font=("Microsoft YaHei UI", 10))
        self.content_text.grid(row=3, column=1, columnspan=3, sticky="nsew", pady=2, padx=(4, 0))
        edit_frame.rowconfigure(3, weight=1)
        edit_frame.columnconfigure(1, weight=1)

        btn_bar = ttk.Frame(edit_frame)
        btn_bar.grid(row=4, column=1, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Button(btn_bar, text="保存", command=self.save_review).pack(side="right", padx=2)
        ttk.Button(btn_bar, text="清空", command=self.clear_form).pack(side="right", padx=2)
        ttk.Button(btn_bar, text="查看原练习", command=self.view_practice).pack(side="left", padx=2)

        self._current_id = 0

    def refresh(self):
        tag = self.tag_filter_var.get().strip()
        if tag:
            reviews = self.db.list_reviews_by_tag(tag)
        else:
            # 全部：直接 list
            with self.db._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM practice_reviews ORDER BY review_date DESC LIMIT 500"
                ).fetchall()
            reviews = [PracticeReview.from_row(r) for r in rows]
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in reviews:
            self.tree.insert(
                "", "end", iid=str(r.id),
                values=(r.id, r.title, r.tags,
                        f"#{r.practice_id}" if r.practice_id else "-", r.review_date)
            )
        self.clear_form()

    def refresh_by_practice(self):
        """弹窗输入练习 ID，筛选"""
        from tkinter import simpledialog
        pid = simpledialog.askinteger("按练习 ID 筛选", "请输入练习记录 ID：", parent=self)
        if not pid:
            return
        reviews = self.db.list_reviews_by_practice(pid)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in reviews:
            self.tree.insert(
                "", "end", iid=str(r.id),
                values=(r.id, r.title, r.tags,
                        f"#{r.practice_id}" if r.practice_id else "-", r.review_date)
            )
        self.clear_form()

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        rid = int(sel[0])
        with self.db._connect() as conn:
            row = conn.execute("SELECT * FROM practice_reviews WHERE id=?", (rid,)).fetchone()
        if not row:
            return
        r = PracticeReview.from_row(row)
        self._current_id = r.id
        self.title_var.set(r.title)
        self.practice_id_var.set(str(r.practice_id) if r.practice_id else "")
        self.date_var.set(r.review_date)
        self.tags_var.set(r.tags)
        self.content_text.delete("1.0", "end")
        self.content_text.insert("1.0", r.content)

    def add_review(self):
        self.clear_form()
        self._current_id = 0
        self.title_var.set("新心得")
        self.date_var.set(_today())

    def edit_review(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一条心得")
            return
        self.on_select(None)

    def delete_review(self):
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("确认", "删除选中的心得？"):
            return
        if self.db.delete_review(int(sel[0])):
            self.refresh()
            if self.on_record_change:
                self.on_record_change()

    def save_review(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("提示", "标题不能为空")
            return
        try:
            pid = int(self.practice_id_var.get().strip() or "0")
        except ValueError:
            messagebox.showwarning("提示", "关联练习 ID 必须是数字")
            return
        r = PracticeReview(
            id=self._current_id, practice_id=pid,
            review_date=self.date_var.get().strip() or _today(),
            title=title, content=self.content_text.get("1.0", "end").strip(),
            tags=self.tags_var.get().strip()
        )
        if self._current_id == 0:
            self.db.add_review(r)
        else:
            self.db.update_review(r)
        self.refresh()
        if self.on_record_change:
            self.on_record_change()
        messagebox.showinfo("已保存", f"心得「{title}」已保存")

    def view_practice(self):
        pid = self.practice_id_var.get().strip()
        if not pid:
            messagebox.showinfo("提示", "未关联练习 ID")
            return
        p = self.db.get_practice(int(pid))
        if not p:
            messagebox.showwarning("未找到", f"练习 #{pid} 不存在")
            return
        # 弹窗显示
        from tkinter import Toplevel
        win = Toplevel(self)
        win.title(f"练习 #{p.id} - {p.title}")
        win.geometry("700x500")
        txt = scrolledtext.ScrolledText(win, wrap="word", font=("Microsoft YaHei UI", 10))
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("1.0", f"日期: {p.practice_date}\n分类: {p.category}\nTAG: {p.tags}\n\n{p.content}")
        if p.images:
            txt.insert("end", f"\n\n[图片] {p.images}")
        txt.config(state="disabled")

    def clear_form(self):
        self._current_id = 0
        self.title_var.set("")
        self.practice_id_var.set("")
        self.date_var.set(_today())
        self.tags_var.set("")
        self.content_text.delete("1.0", "end")
        for item in self.tree.selection():
            self.tree.selection_remove(item)


# =============================================================================
# 练习记录图片增强 Mixin
# =============================================================================

class PracticeImageMixin:
    """练习记录页：图片管理 + TAG 关联展示"""

    def build_practice_image_panel(self, parent: ttk.Frame, get_practice_id: callable):
        """
        构建图片管理面板（嵌入到练习记录标签页的编辑区下方）。
        get_practice_id: 返回当前选中的练习 ID（int）
        """
        self._img_get_practice_id = get_practice_id
        frame = ttk.LabelFrame(parent, text="服务器截图 / 图片附件", padding=8)
        # 由调用方负责 pack/grid

        ttk.Button(frame, text="➕ 添加图片", command=self.add_practice_images).pack(side="left", padx=2)
        ttk.Button(frame, text="🗑 移除选中", command=self.remove_practice_image).pack(side="left", padx=2)
        ttk.Button(frame, text="📂 打开目录", command=self.open_practice_images_dir).pack(side="left", padx=2)
        ttk.Label(frame, text="（支持多张；按 Ctrl 多选后删除）", foreground="#888").pack(side="left", padx=8)

        self.practice_img_list = tk.Listbox(frame, height=4, selectmode="extended")
        self.practice_img_list.pack(fill="x", pady=(6, 0))
        return frame

    def add_practice_images(self):
        pid = self._img_get_practice_id()
        if not pid:
            messagebox.showinfo("提示", "请先选中一条练习记录")
            return
        files = filedialog.askopenfilenames(
            title="选择图片（git/linux 服务器截图）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("全部", "*.*")]
        )
        if not files:
            return
        # 读取当前 images
        p = self.db.get_practice(pid)
        if not p:
            return
        existing = [x for x in (p.images or "").split("|") if x]
        added = 0
        for fp in files:
            rel = _save_image(fp)
            if rel:
                existing.append(rel)
                added += 1
        p.images = "|".join(existing)
        self.db.update_practice(p)
        self.refresh_practice_image_list(existing)
        messagebox.showinfo("已添加", f"已添加 {added} 张图片")

    def remove_practice_image(self):
        sel = self.practice_img_list.curselection()
        if not sel:
            return
        pid = self._img_get_practice_id()
        if not pid:
            return
        p = self.db.get_practice(pid)
        if not p:
            return
        images = [x for x in (p.images or "").split("|") if x]
        # 从后往前删
        for idx in reversed(sel):
            if idx < len(images):
                images.pop(idx)
        p.images = "|".join(images)
        self.db.update_practice(p)
        self.refresh_practice_image_list(images)

    def open_practice_images_dir(self):
        path = _ensure_images_dir()
        try:
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def refresh_practice_image_list(self, images: List[str]):
        self.practice_img_list.delete(0, "end")
        for img in images:
            # 只显示文件名
            self.practice_img_list.insert("end", os.path.basename(img))
