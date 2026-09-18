# -*- coding: utf-8 -*-
"""
================================================================================
Q&A 问答 + 每周工作纪要 + 练习记录 页面
================================================================================
整合三个功能在一个页面内，使用 Notebook 标签页切换
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime, timedelta
from typing import Optional

from qa_work_log_db import QAWorkLogDB, QAWorkLogDBExt, QAItem, WeeklyLog, PracticeLog
from qa_extras import (
    GlobalSearchBarMixin, WorkNotePanel, ReviewPanel,
    PracticeImageMixin, _save_image, _ensure_images_dir, parse_tags
)


class QAWorkLogPage(ttk.Frame, GlobalSearchBarMixin, PracticeImageMixin):
    """Q&A + 工作纪要 + 练习记录 + 工作笔记 + 复习心得 主页面"""

    def __init__(self, parent: ttk.Frame, db: QAWorkLogDBExt):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self._current_practice_id = 0
        self.build_ui()
        self.refresh_all()

    def build_ui(self):
        """构建界面"""
        # 顶部全局模糊搜索栏
        self.build_global_search_bar(self)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # === Q&A 标签页 ===
        self.qa_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.qa_frame, text="Q&A 问答")
        self.build_qa_tab()

        # === 工作纪要标签页 ===
        self.weekly_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.weekly_frame, text="每周纪要")
        self.build_weekly_tab()

        # === 练习记录标签页 ===
        self.practice_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.practice_frame, text="练习记录")
        self.build_practice_tab()

        # === 工作笔记标签页 ===
        self.work_note_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.work_note_frame, text="工作笔记")
        self.work_note_panel = WorkNotePanel(self.work_note_frame, self.db,
                                              on_record_change=self.refresh_all)

        # === 复习心得标签页 ===
        self.review_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.review_frame, text="复习心得")
        self.review_panel = ReviewPanel(self.review_frame, self.db,
                                         on_record_change=self.refresh_all)

    # ==========================================================================
    # Q&A 标签页
    # ==========================================================================

    def build_qa_tab(self):
        """构建 Q&A 界面"""
        # 工具栏
        toolbar = ttk.Frame(self.qa_frame, padding=(8, 8, 8, 6))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="新增问答", command=self.add_qa).pack(side="left", padx=2)
        ttk.Button(toolbar, text="编辑", command=self.edit_qa).pack(side="left", padx=2)
        ttk.Button(toolbar, text="删除", command=self.delete_qa).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        # 筛选
        ttk.Label(toolbar, text="范围:").pack(side="left")
        self.qa_scope_var = tk.StringVar(value="全部")
        ttk.Combobox(toolbar, textvariable=self.qa_scope_var, values=["全部", "工作", "生活"], width=8, state="readonly").pack(side="left", padx=2)

        ttk.Label(toolbar, text="类型:").pack(side="left", padx=(8, 0))
        self.qa_cat_var = tk.StringVar(value="全部")
        ttk.Combobox(toolbar, textvariable=self.qa_cat_var, values=["全部", "项目", "事件", "流程"], width=8, state="readonly").pack(side="left", padx=2)

        ttk.Label(toolbar, text="搜索:").pack(side="left", padx=(8, 0))
        self.qa_search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.qa_search_var, width=20).pack(side="left", padx=2)
        ttk.Button(toolbar, text="刷新", command=self.refresh_qa).pack(side="left", padx=2)

        # 列表
        list_frame = ttk.Frame(self.qa_frame)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        cols = ("scope", "category", "ref_name", "question", "created_at")
        self.qa_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=12)
        self.qa_tree.heading("scope", text="范围")
        self.qa_tree.heading("category", text="类型")
        self.qa_tree.heading("ref_name", text="关联")
        self.qa_tree.heading("question", text="问题")
        self.qa_tree.heading("created_at", text="创建时间")
        self.qa_tree.column("scope", width=60)
        self.qa_tree.column("category", width=60)
        self.qa_tree.column("ref_name", width=120)
        self.qa_tree.column("question", width=400)
        self.qa_tree.column("created_at", width=120)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.qa_tree.yview)
        self.qa_tree.configure(yscrollcommand=vsb.set)
        self.qa_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 详情预览
        detail_frame = ttk.LabelFrame(self.qa_frame, text="答案详情", padding=8)
        detail_frame.pack(fill="x", padx=8, pady=(0, 8))
        self.qa_detail_text = scrolledtext.ScrolledText(detail_frame, wrap="word", height=6, state="disabled")
        self.qa_detail_text.pack(fill="both", expand=True)

        self.qa_tree.bind("<<TreeviewSelect>>", self.on_qa_select)
        self.qa_tree.bind("<Double-1>", lambda e: self.edit_qa())

    def refresh_qa(self):
        """刷新 Q&A 列表"""
        scope = self.qa_scope_var.get()
        cat = self.qa_cat_var.get()
        keyword = self.qa_search_var.get().strip()

        scope = None if scope == "全部" else scope
        cat = None if cat == "全部" else cat
        keyword = keyword if keyword else None

        items = self.db.list_qa(scope=scope, category=cat, keyword=keyword)

        self.qa_tree.delete(*self.qa_tree.get_children())
        for item in items:
            self.qa_tree.insert("", "end", iid=str(item.id), values=(
                item.scope, item.category, item.ref_name,
                item.question[:50] + "..." if len(item.question) > 50 else item.question,
                item.created_at[:16] if item.created_at else ""
            ))

    def on_qa_select(self, event=None):
        """选中 Q&A 显示详情"""
        sel = self.qa_tree.selection()
        if not sel:
            return
        item = self.db.get_qa(int(sel[0]))
        if item:
            self.qa_detail_text.config(state="normal")
            self.qa_detail_text.delete("1.0", "end")
            self.qa_detail_text.insert("1.0", f"【问题】\n{item.question}\n\n【答案】\n{item.answer}")
            self.qa_detail_text.config(state="disabled")

    def add_qa(self):
        """新增问答"""
        dialog = QADialog(self, self.db)
        self.wait_window(dialog)
        if dialog.result:
            self.refresh_qa()

    def edit_qa(self):
        """编辑问答"""
        sel = self.qa_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一条记录")
            return
        item = self.db.get_qa(int(sel[0]))
        if item:
            dialog = QADialog(self, self.db, item)
            self.wait_window(dialog)
            if dialog.result:
                self.refresh_qa()

    def delete_qa(self):
        """删除问答"""
        sel = self.qa_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一条记录")
            return
        if messagebox.askyesno("确认", "确定删除这条问答？"):
            self.db.delete_qa(int(sel[0]))
            self.refresh_qa()

    # ==========================================================================
    # 工作纪要标签页
    # ==========================================================================

    def build_weekly_tab(self):
        """构建工作纪要界面"""
        toolbar = ttk.Frame(self.weekly_frame, padding=(8, 8, 8, 6))
        toolbar.pack(fill="x")

        self.week_label = ttk.Label(toolbar, text="", font=("Microsoft YaHei UI", 10, "bold"))
        self.week_label.pack(side="left")

        ttk.Button(toolbar, text="查看历史", command=self.show_archived_weeks).pack(side="right", padx=2)

        # 周一到周五输入区
        days_frame = ttk.Frame(self.weekly_frame)
        days_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.weekly_texts = {}
        day_names = ["周一", "周二", "周三", "周四", "周五"]

        for i, name in enumerate(day_names, 1):
            frame = ttk.LabelFrame(days_frame, text=name, padding=4)
            frame.pack(fill="both", expand=True, pady=2)
            text = scrolledtext.ScrolledText(frame, wrap="word", height=4)
            text.pack(fill="both", expand=True)
            self.weekly_texts[i] = text

        # 保存按钮
        btn_frame = ttk.Frame(self.weekly_frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="保存本周纪要", command=self.save_weekly).pack(side="right")

    def refresh_weekly(self):
        """刷新工作纪要"""
        monday = self._get_monday()
        sunday = (datetime.strptime(monday, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
        self.week_label.config(text=f"本周：{monday} 至 {sunday}")

        logs = self.db.get_current_week_logs()
        log_map = {log.day: log for log in logs}

        for day, text in self.weekly_texts.items():
            text.delete("1.0", "end")
            if day in log_map:
                text.insert("1.0", log_map[day].content)

    def save_weekly(self):
        """保存工作纪要"""
        for day, text in self.weekly_texts.items():
            log = self.db.get_or_create_weekly_log(day)
            content = text.get("1.0", "end-1c")
            self.db.update_weekly_log(log.id, content)
        messagebox.showinfo("完成", "本周纪要已保存")

    def show_archived_weeks(self):
        """显示历史归档"""
        dialog = ArchivedWeeksDialog(self, self.db)
        self.wait_window(dialog)

    def _get_monday(self) -> str:
        """获取本周一日期"""
        d = datetime.now()
        monday = d - timedelta(days=d.weekday())
        return monday.strftime("%Y-%m-%d")

    # ==========================================================================
    # 练习记录标签页
    # ==========================================================================

    def build_practice_tab(self):
        """构建练习记录界面"""
        toolbar = ttk.Frame(self.practice_frame, padding=(8, 8, 8, 6))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="新增记录", command=self.add_practice).pack(side="left", padx=2)
        ttk.Button(toolbar, text="编辑", command=self.edit_practice).pack(side="left", padx=2)
        ttk.Button(toolbar, text="删除", command=self.delete_practice).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(toolbar, text="分类:").pack(side="left")
        self.practice_cat_var = tk.StringVar(value="全部")
        cats = ["全部", "记忆宫殿", "Git", "Linux", "自定义"]
        ttk.Combobox(toolbar, textvariable=self.practice_cat_var, values=cats, width=10, state="readonly").pack(side="left", padx=2)

        ttk.Button(toolbar, text="今日", command=self.show_today_practice).pack(side="left", padx=2)
        ttk.Button(toolbar, text="刷新", command=self.refresh_practice).pack(side="left", padx=2)

        # 列表
        list_frame = ttk.Frame(self.practice_frame)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        cols = ("date", "category", "title", "tags")
        self.practice_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=10)
        self.practice_tree.heading("date", text="日期")
        self.practice_tree.heading("category", text="分类")
        self.practice_tree.heading("title", text="标题")
        self.practice_tree.heading("tags", text="标签")
        self.practice_tree.column("date", width=100)
        self.practice_tree.column("category", width=80)
        self.practice_tree.column("title", width=300)
        self.practice_tree.column("tags", width=150)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.practice_tree.yview)
        self.practice_tree.configure(yscrollcommand=vsb.set)
        self.practice_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 详情
        detail_frame = ttk.LabelFrame(self.practice_frame, text="练习详情", padding=8)
        detail_frame.pack(fill="x", padx=8, pady=(0, 8))
        self.practice_detail_text = scrolledtext.ScrolledText(detail_frame, wrap="word", height=8, state="disabled")
        self.practice_detail_text.pack(fill="both", expand=True)

        # 服务器截图 / 图片附件（来自 qa_extras.PracticeImageMixin）
        self.practice_image_panel = self.build_practice_image_panel(
            self.practice_frame,
            get_practice_id=lambda: self._current_practice_id
        )
        self.practice_image_panel.pack(fill="x", padx=8, pady=(0, 8))

        self.practice_tree.bind("<<TreeviewSelect>>", self.on_practice_select)
        self.practice_tree.bind("<Double-1>", lambda e: self.edit_practice())

        # 快速模板按钮
        template_frame = ttk.LabelFrame(self.practice_frame, text="快速模板", padding=8)
        template_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(template_frame, text="记忆宫殿", command=lambda: self.quick_practice("记忆宫殿")).pack(side="left", padx=2)
        ttk.Button(template_frame, text="Git", command=lambda: self.quick_practice("Git")).pack(side="left", padx=2)
        ttk.Button(template_frame, text="Linux", command=lambda: self.quick_practice("Linux")).pack(side="left", padx=2)

    def refresh_practice(self):
        """刷新练习记录"""
        cat = self.practice_cat_var.get()
        cat = None if cat == "全部" else cat
        items = self.db.list_practices(category=cat)

        self.practice_tree.delete(*self.practice_tree.get_children())
        for item in items:
            self.practice_tree.insert("", "end", iid=str(item.id), values=(
                item.practice_date, item.category, item.title, item.tags
            ))

    def on_practice_select(self, event=None):
        """选中练习显示详情"""
        sel = self.practice_tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        self._current_practice_id = pid
        item = self.db.get_practice(pid)
        if item:
            self.practice_detail_text.config(state="normal")
            self.practice_detail_text.delete("1.0", "end")
            content = item.content
            if item.images:
                content += f"\n\n[图片附件] {item.images.replace('|', chr(10))}"
            self.practice_detail_text.insert("1.0", content)
            self.practice_detail_text.config(state="disabled")
            # 刷新图片列表
            images = [x for x in (item.images or "").split("|") if x]
            self.refresh_practice_image_list(images)

    def add_practice(self):
        """新增练习记录"""
        dialog = PracticeDialog(self, self.db)
        self.wait_window(dialog)
        if dialog.result:
            self.refresh_practice()

    def edit_practice(self):
        """编辑练习记录"""
        sel = self.practice_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一条记录")
            return
        item = self.db.get_practice(int(sel[0]))
        if item:
            dialog = PracticeDialog(self, self.db, item)
            self.wait_window(dialog)
            if dialog.result:
                self.refresh_practice()

    def delete_practice(self):
        """删除练习记录"""
        sel = self.practice_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一条记录")
            return
        if messagebox.askyesno("确认", "确定删除这条记录？"):
            self.db.delete_practice(int(sel[0]))
            self.refresh_practice()

    def show_today_practice(self):
        """显示今日练习"""
        self.practice_cat_var.set("全部")
        items = self.db.get_today_practices()
        self.practice_tree.delete(*self.practice_tree.get_children())
        for item in items:
            self.practice_tree.insert("", "end", iid=str(item.id), values=(
                item.practice_date, item.category, item.title, item.tags
            ))

    def quick_practice(self, category: str):
        """快速创建练习记录（带模板）"""
        templates = {
            "记忆宫殿": {
                "title": f"记忆宫殿 - {datetime.now().strftime('%m%d')}",
                "content": """今天练：身体桩——从头到脚10个部位
额头→眼睛→鼻子→嘴→脖子→肩膀→手→肚子→膝盖→脚

每个部位绑定信息：
1. 额头: 
2. 眼睛: 
3. 鼻子: 
4. 嘴: 
5. 脖子: 
6. 肩膀: 
7. 手: 
8. 肚子: 
9. 膝盖: 
10. 脚: 
""",
                "tags": "记忆宫殿,身体桩"
            },
            "Git": {
                "title": f"Git练习 - {datetime.now().strftime('%m%d')}",
                "content": """今天练：

git rebase -i HEAD~3 整理最近3次提交

技巧：
- pick 保持原样
- squash 合并
- reword 改消息

实操记录：
""",
                "tags": "Git,rebase"
            },
            "Linux": {
                "title": f"Linux练习 - {datetime.now().strftime('%m%d')}",
                "content": """今天练：

grep -E "pattern1|pattern2" file | sort | uniq -c | sort -rn

技巧：先排序再uniq，效率更高

实操记录：
""",
                "tags": "Linux,grep"
            }
        }
        tmpl = templates.get(category, {"title": "", "content": "", "tags": ""})
        log = PracticeLog(
            practice_date=datetime.now().strftime("%Y-%m-%d"),
            category=category,
            title=tmpl["title"],
            content=tmpl["content"],
            tags=tmpl["tags"]
        )
        dialog = PracticeDialog(self, self.db, log, is_template=True)
        self.wait_window(dialog)
        if dialog.result:
            self.refresh_practice()

    def refresh_all(self):
        """刷新所有标签页"""
        self.refresh_qa()
        self.refresh_weekly()
        self.refresh_practice()


# =============================================================================
# 对话框类
# =============================================================================

class QADialog(tk.Toplevel):
    """Q&A 编辑对话框"""

    def __init__(self, parent, db: QAWorkLogDB, item: QAItem = None):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.item = item
        self.result = False

        self.title("编辑问答" if item else "新增问答")
        self.geometry("600x450")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.build_ui()
        if item:
            self.load_data()

        self.center_on_parent()

    def center_on_parent(self):
        self.update_idletasks()
        px, py = self.parent.winfo_x(), self.parent.winfo_y()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        sw, sh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - sw) // 2}+{py + (ph - sh) // 2}")

    def build_ui(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        # 范围
        ttk.Label(frame, text="范围:").grid(row=0, column=0, sticky="w", pady=4)
        self.scope_var = tk.StringVar(value="工作")
        ttk.Combobox(frame, textvariable=self.scope_var, values=["工作", "生活"], width=12, state="readonly").grid(row=0, column=1, sticky="w", pady=4)

        # 类型
        ttk.Label(frame, text="类型:").grid(row=1, column=0, sticky="w", pady=4)
        self.cat_var = tk.StringVar(value="项目")
        ttk.Combobox(frame, textvariable=self.cat_var, values=["项目", "事件", "流程"], width=12, state="readonly").grid(row=1, column=1, sticky="w", pady=4)

        # 关联名称
        ttk.Label(frame, text="关联:").grid(row=2, column=0, sticky="w", pady=4)
        self.ref_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.ref_var, width=40).grid(row=2, column=1, sticky="ew", pady=4)

        # 问题
        ttk.Label(frame, text="问题:").grid(row=3, column=0, sticky="nw", pady=4)
        self.question_text = scrolledtext.ScrolledText(frame, wrap="word", height=4)
        self.question_text.grid(row=3, column=1, sticky="ew", pady=4)

        # 答案
        ttk.Label(frame, text="答案:").grid(row=4, column=0, sticky="nw", pady=4)
        self.answer_text = scrolledtext.ScrolledText(frame, wrap="word", height=6)
        self.answer_text.grid(row=4, column=1, sticky="ew", pady=4)

        # 标签
        ttk.Label(frame, text="标签:").grid(row=5, column=0, sticky="w", pady=4)
        self.tags_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.tags_var, width=40).grid(row=5, column=1, sticky="ew", pady=4)

        frame.columnconfigure(1, weight=1)

        # 按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=12)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="保存", command=self.save).pack(side="left", padx=4)

    def load_data(self):
        self.scope_var.set(self.item.scope)
        self.cat_var.set(self.item.category)
        self.ref_var.set(self.item.ref_name)
        self.question_text.insert("1.0", self.item.question)
        self.answer_text.insert("1.0", self.item.answer)
        self.tags_var.set(self.item.tags)

    def save(self):
        item = QAItem(
            id=self.item.id if self.item else 0,
            scope=self.scope_var.get(),
            category=self.cat_var.get(),
            ref_name=self.ref_var.get().strip(),
            question=self.question_text.get("1.0", "end-1c").strip(),
            answer=self.answer_text.get("1.0", "end-1c").strip(),
            tags=self.tags_var.get().strip()
        )
        if not item.question:
            messagebox.showwarning("提示", "问题不能为空", parent=self)
            return
        if item.id:
            self.db.update_qa(item)
        else:
            self.db.add_qa(item)
        self.result = True
        self.destroy()


class PracticeDialog(tk.Toplevel):
    """练习记录编辑对话框"""

    def __init__(self, parent, db: QAWorkLogDB, item: PracticeLog = None, is_template: bool = False):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.item = item
        self.is_template = is_template
        self.result = False

        self.title("编辑练习记录" if (item and not is_template) else "新增练习记录")
        self.geometry("550x450")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.build_ui()
        if item:
            self.load_data()

        self.center_on_parent()

    def center_on_parent(self):
        self.update_idletasks()
        px, py = self.parent.winfo_x(), self.parent.winfo_y()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        sw, sh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - sw) // 2}+{py + (ph - sh) // 2}")

    def build_ui(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        # 日期
        ttk.Label(frame, text="日期:").grid(row=0, column=0, sticky="w", pady=4)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(frame, textvariable=self.date_var, width=15).grid(row=0, column=1, sticky="w", pady=4)

        # 分类
        ttk.Label(frame, text="分类:").grid(row=1, column=0, sticky="w", pady=4)
        self.cat_var = tk.StringVar(value="记忆宫殿")
        ttk.Combobox(frame, textvariable=self.cat_var, values=["记忆宫殿", "Git", "Linux", "自定义"], width=12, state="readonly").grid(row=1, column=1, sticky="w", pady=4)

        # 标题
        ttk.Label(frame, text="标题:").grid(row=2, column=0, sticky="w", pady=4)
        self.title_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.title_var, width=50).grid(row=2, column=1, sticky="ew", pady=4)

        # 内容
        ttk.Label(frame, text="内容:").grid(row=3, column=0, sticky="nw", pady=4)
        self.content_text = scrolledtext.ScrolledText(frame, wrap="word", height=10)
        self.content_text.grid(row=3, column=1, sticky="ew", pady=4)

        # 标签
        ttk.Label(frame, text="标签:").grid(row=4, column=0, sticky="w", pady=4)
        self.tags_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.tags_var, width=50).grid(row=4, column=1, sticky="ew", pady=4)

        frame.columnconfigure(1, weight=1)

        # 按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=12)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="保存", command=self.save).pack(side="left", padx=4)

    def load_data(self):
        self.date_var.set(self.item.practice_date)
        self.cat_var.set(self.item.category)
        self.title_var.set(self.item.title)
        self.content_text.insert("1.0", self.item.content)
        self.tags_var.set(self.item.tags)

    def save(self):
        log = PracticeLog(
            id=self.item.id if self.item else 0,
            practice_date=self.date_var.get().strip(),
            category=self.cat_var.get(),
            title=self.title_var.get().strip(),
            content=self.content_text.get("1.0", "end-1c").strip(),
            tags=self.tags_var.get().strip()
        )
        if not log.title:
            messagebox.showwarning("提示", "标题不能为空", parent=self)
            return
        if log.id and not self.is_template:
            self.db.update_practice(log)
        else:
            self.db.add_practice(log)
        self.result = True
        self.destroy()


class ArchivedWeeksDialog(tk.Toplevel):
    """历史归档周列表对话框"""

    def __init__(self, parent, db: QAWorkLogDB):
        super().__init__(parent)
        self.parent = parent
        self.db = db

        self.title("历史工作纪要")
        self.geometry("500x400")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.build_ui()
        self.load_data()
        self.center_on_parent()

    def center_on_parent(self):
        self.update_idletasks()
        px, py = self.parent.winfo_x(), self.parent.winfo_y()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        sw, sh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - sw) // 2}+{py + (ph - sh) // 2}")

    def build_ui(self):
        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="选择要查看的周:").pack(anchor="w", pady=(0, 4))

        self.listbox = tk.Listbox(frame, height=10)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-1>", lambda e: self.view_week())

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=8)
        ttk.Button(btn_frame, text="查看", command=self.view_week).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="关闭", command=self.destroy).pack(side="right", padx=2)

    def load_data(self):
        weeks = self.db.list_archived_weeks()
        for w in weeks:
            monday = datetime.strptime(w, "%Y-%m-%d")
            sunday = monday + timedelta(days=6)
            self.listbox.insert("end", f"{w} 至 {sunday.strftime('%Y-%m-%d')}")
        if not weeks:
            self.listbox.insert("end", "暂无归档记录")

    def view_week(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        text = self.listbox.get(sel[0])
        if "暂无" in text:
            return
        week_start = text.split(" ")[0]
        dialog = ViewWeekDialog(self, self.db, week_start)
        self.wait_window(dialog)


class ViewWeekDialog(tk.Toplevel):
    """查看某周纪要详情"""

    def __init__(self, parent, db: QAWorkLogDB, week_start: str):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.week_start = week_start

        self.title(f"工作纪要 - {week_start}")
        self.geometry("600x500")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.build_ui()
        self.load_data()
        self.center_on_parent()

    def center_on_parent(self):
        self.update_idletasks()
        px, py = self.parent.winfo_x(), self.parent.winfo_y()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        sw, sh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - sw) // 2}+{py + (ph - sh) // 2}")

    def build_ui(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        day_names = ["周一", "周二", "周三", "周四", "周五"]
        self.texts = []

        for i, name in enumerate(day_names, 1):
            lf = ttk.LabelFrame(frame, text=name, padding=4)
            lf.pack(fill="x", pady=4)
            text = scrolledtext.ScrolledText(lf, wrap="word", height=4, state="disabled")
            text.pack(fill="x")
            self.texts.append(text)

        ttk.Button(frame, text="关闭", command=self.destroy).pack(anchor="e", pady=8)

    def load_data(self):
        logs = self.db.get_week_logs(self.week_start)
        log_map = {log.day: log for log in logs}
        for i, text in enumerate(self.texts, 1):
            text.config(state="normal")
            text.delete("1.0", "end")
            if i in log_map:
                text.insert("1.0", log_map[i].content)
            text.config(state="disabled")
