"""
Python 学习辅助模块
study_demo_window.py

新版设计（2026-08-17）：
  1. 课程 → 章节 → 代码片段 三级
  2. 工作流：选语言 → 写代码 → 运行 → 看结果 → 保存到当前章节作为 demo
  3. 样式：编辑器浅色（白底黑字 IDE 风），输出区白底，关键操作按钮置顶
  4. 占位提示：未选章节/未选片段时给出明确提示
"""
import os, sys, subprocess, threading, time, traceback, json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 高亮（可选，有 Pygments 时使用）
# ---------------------------------------------------------------------------
try:
    from pygments import lex
    from pygments.lexers import Python3Lexer, JavaScriptLexer, SqlLexer, BashLexer
    from pygments.token import Token
    HAS_PYGMENTS = True
    LEXER_MAP = {
        "python": Python3Lexer,
        "javascript": JavaScriptLexer,
        "sql": SqlLexer,
        "bash": BashLexer,
    }
except ImportError:
    HAS_PYGMENTS = False
    LEXER_MAP = {}

# ---------------------------------------------------------------------------
# 颜色常量（黑白极简 + 浅色 IDE 风格）
# ---------------------------------------------------------------------------
COLOR_BG       = "#ffffff"
COLOR_CARD     = "#ffffff"
COLOR_CARD_H   = "#f8fafc"
COLOR_BORDER   = "#e5e7eb"
COLOR_PRIMARY  = "#2563eb"
COLOR_ACCENT   = "#0ea5e9"
COLOR_TEXT     = "#111827"
COLOR_MUTED    = "#6b7280"
COLOR_RUN_BTN  = "#16a34a"
COLOR_SAVE_BTN = "#f59e0b"   # 保存 demo 用醒目橙色
COLOR_CODE_BG  = "#fafafa"   # 浅色 IDE
COLOR_CODE_FG  = "#1f2328"
COLOR_OUTPUT_BG= "#ffffff"
COLOR_OUTPUT_FG= "#1f2328"
COLOR_ERROR    = "#dc2626"
COLOR_OK       = "#16a34a"
COLOR_PLACEHOLDER = "#9ca3af"

# 支持的语言
LANGUAGE_OPTIONS = ["python", "javascript", "sql", "bash", "text"]

# 占位提示
CODE_PLACEHOLDER = (
    "💡 工作流程提示：\n"
    "  1. 在左侧选中课程和章节\n"
    "  2. 顶部选择编程语言\n"
    "  3. 在本编辑器中编写代码\n"
    "  4. 点击 ▶ 运行（F5），查看下方输出\n"
    "  5. 运行成功后，点击「💾 保存为 Demo」保存到当前章节"
)


# ---------------------------------------------------------------------------
# 主页面
# ---------------------------------------------------------------------------
class StudyDemoPage(ttk.Frame):
    """Python 学习辅助模块主页面"""

    def __init__(self, parent, db_conn, project_root: str = ""):
        super().__init__(parent)
        self.db = db_conn
        if hasattr(self.db, "conn"):
            self.db = self.db.conn
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        self.demo_root = os.path.join(self.project_root, "study_demo")
        os.makedirs(self.demo_root, exist_ok=True)

        self.current_course_id: Optional[int] = None
        self.current_chapter_id: Optional[int] = None
        self.current_snippet_id: Optional[int] = None
        self._running = False
        self._placeholder_shown = True

        self._build_ui()
        self._load_courses()
        self._show_placeholder()

    # ------------------------------------------------------------------
    # UI 布局
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 顶部说明栏
        self._build_header()

        # 主分割
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ── 左：课程树 ────────────────────────────────────────────────
        left = ttk.Frame(paned, width=240)
        paned.add(left, weight=0)
        self._build_left_panel(left)

        # ── 中：章节+片段列表 ───────────────────────────────────────
        middle = ttk.Frame(paned, width=260)
        paned.add(middle, weight=1)
        self._build_middle_panel(middle)

        # ── 右：代码编辑器+运行+输出 ───────────────────────────────
        right = ttk.Frame(paned)
        paned.add(right, weight=3)
        self._build_right_panel(right)

    def _build_header(self):
        """顶部说明 + 状态"""
        header = ttk.Frame(self)
        header.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(header, text="🐍 Python 学习工作台",
                  font=("", 13, "bold")).pack(side="left")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(header, textvariable=self.status_var,
                  foreground=COLOR_MUTED).pack(side="right")

    def _build_left_panel(self, parent):
        ttk.Label(parent, text="📚 课程", font=("", 11, "bold")).pack(anchor="w", pady=(0, 6))
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="+", width=3, command=self._add_course).pack(side="left")
        ttk.Button(bar, text="✎", width=3, command=self._edit_course).pack(side="left")
        ttk.Button(bar, text="🗑", width=3, command=self._delete_course).pack(side="left")

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame)
        sb.pack(side="right", fill="y")
        self.course_listbox = tk.Listbox(list_frame, font=("", 10),
                                          yscrollcommand=sb.set,
                                          bg=COLOR_CARD, fg=COLOR_TEXT,
                                          highlightthickness=1,
                                          highlightbackground=COLOR_BORDER,
                                          selectbackground=COLOR_PRIMARY,
                                          selectforeground="#fff",
                                          activestyle="none",
                                          borderwidth=0)
        self.course_listbox.pack(side="left", fill="both", expand=True)
        sb.configure(command=self.course_listbox.yview)
        self.course_listbox.bind("<<ListboxSelect>>", self._on_course_select)
        self.course_listbox.bind("<Double-Button-1>", lambda e: self._edit_course())

    def _build_middle_panel(self, parent):
        # 章节
        ttk.Label(parent, text="📖 章节", font=("", 11, "bold")).pack(anchor="w", pady=(0, 6))
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="+ 章节", command=self._add_chapter).pack(side="left")
        ttk.Button(bar, text="✎", width=3, command=self._edit_chapter).pack(side="left")
        ttk.Button(bar, text="🗑", width=3, command=self._delete_chapter).pack(side="left")

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="x", expand=False, pady=(0, 4))
        sb = ttk.Scrollbar(list_frame)
        sb.pack(side="right", fill="y")
        self.chapter_listbox = tk.Listbox(list_frame, font=("", 10), height=6,
                                          yscrollcommand=sb.set,
                                          bg=COLOR_CARD, fg=COLOR_TEXT,
                                          highlightthickness=1,
                                          highlightbackground=COLOR_BORDER,
                                          selectbackground=COLOR_ACCENT,
                                          selectforeground="#fff",
                                          activestyle="none",
                                          borderwidth=0)
        self.chapter_listbox.pack(side="left", fill="both", expand=True)
        sb.configure(command=self.chapter_listbox.yview)
        self.chapter_listbox.bind("<<ListboxSelect>>", self._on_chapter_select)
        self.chapter_listbox.bind("<Double-Button-1>", lambda e: self._edit_chapter())

        # 代码片段
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=(8, 4))
        ttk.Label(parent, text="💻 代码片段（demo）", font=("", 10, "bold")).pack(anchor="w", pady=(0, 4))
        snip_bar = ttk.Frame(parent)
        snip_bar.pack(fill="x", pady=(0, 4))
        ttk.Button(snip_bar, text="+ 片段", command=self._add_snippet).pack(side="left")
        ttk.Button(snip_bar, text="✎", width=3, command=self._edit_snippet).pack(side="left")
        ttk.Button(snip_bar, text="🗑", width=3, command=self._delete_snippet).pack(side="left")
        ttk.Button(snip_bar, text="📂", width=3, command=self._open_demo_folder).pack(side="left")

        list_frame2 = ttk.Frame(parent)
        list_frame2.pack(fill="both", expand=True, pady=(0, 4))
        sb2 = ttk.Scrollbar(list_frame2)
        sb2.pack(side="right", fill="y")
        self.snippet_listbox = tk.Listbox(list_frame2, font=("", 10),
                                          yscrollcommand=sb2.set,
                                          bg=COLOR_CARD, fg=COLOR_TEXT,
                                          highlightthickness=1,
                                          highlightbackground=COLOR_BORDER,
                                          selectbackground=COLOR_PRIMARY,
                                          selectforeground="#fff",
                                          activestyle="none",
                                          borderwidth=0)
        self.snippet_listbox.pack(side="left", fill="both", expand=True)
        sb2.configure(command=self.snippet_listbox.yview)
        self.snippet_listbox.bind("<<ListboxSelect>>", self._on_snippet_select)
        self.snippet_listbox.bind("<Double-Button-1>", lambda e: self._edit_snippet())

    def _build_right_panel(self, parent):
        """右侧：语言选择 + 代码编辑 + 运行 + 输出"""
        # ── 顶部操作栏 ─────────────────────────────────────────────
        top_bar = ttk.Frame(parent)
        top_bar.pack(fill="x", pady=(0, 6))

        self.snippet_title_var = tk.StringVar(value="（新片段）")
        ttk.Label(top_bar, textvariable=self.snippet_title_var,
                  font=("", 10, "bold")).pack(side="left")

        ttk.Label(top_bar, text="语言:").pack(side="left", padx=(16, 2))
        self.lang_combo = ttk.Combobox(top_bar, values=LANGUAGE_OPTIONS,
                                        state="readonly", width=10)
        self.lang_combo.pack(side="left")
        self.lang_combo.set("python")
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        ttk.Button(top_bar, text="📎 关联笔记",
                   command=self._link_note).pack(side="left", padx=(8, 0))

        # ── 代码编辑区（浅色 IDE 风格）──────────────────────────────
        editor_frame = tk.Frame(parent, bg=COLOR_BORDER, bd=1, relief="solid")
        editor_frame.pack(fill="both", expand=True, pady=(0, 4))

        self.code_text = tk.Text(editor_frame,
                                  font=("Cascadia Code", 11),
                                  bg=COLOR_CODE_BG, fg=COLOR_CODE_FG,
                                  insertbackground=COLOR_TEXT,
                                  selectbackground="#bfdbfe",
                                  wrap="none",
                                  undo=True,
                                  relief="flat",
                                  bd=0,
                                  padx=10, pady=10)
        self.code_text.pack(fill="both", expand=True, side="left")

        v_scroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self.code_text.yview)
        v_scroll.pack(side="right", fill="y")
        self.code_text.configure(yscrollcommand=v_scroll.set)

        h_scroll = ttk.Scrollbar(parent, orient="horizontal", command=self.code_text.xview)
        h_scroll.pack(fill="x")
        self.code_text.configure(xscrollcommand=h_scroll.set)

        self.code_text.bind("<F5>", lambda e: self._run_code())
        self.code_text.bind("<Control-Return>", lambda e: self._run_code())
        self.code_text.bind("<FocusIn>", self._on_editor_focus_in)

        # ── 标签页：输出 / 日志 ──────────────────────────────────────
        # ── 运行按钮栏（醒目）─────────────────────────────────────────
        run_bar = tk.Frame(parent, bg=COLOR_BG)
        run_bar.pack(fill="x", pady=(4, 4))

        run_btn = tk.Button(run_bar, text="  ▶  运行 (F5)  ",
                             bg=COLOR_RUN_BTN, fg="white",
                             font=("", 10, "bold"), relief="flat",
                             cursor="hand2", padx=12, pady=4,
                             activebackground="#15803d",
                             command=self._run_code)
        run_btn.pack(side="left", padx=(0, 6))
        self.run_btn = run_btn

        tk.Button(run_bar, text="⏹ 停止",
                  bg="#dc2626", fg="white",
                  font=("", 10), relief="flat",
                  cursor="hand2", padx=10, pady=4,
                  activebackground="#b91c1c",
                  command=self._stop_run).pack(side="left")
        self.stop_btn = run_btn  # alias

        tk.Button(run_bar, text="💾 保存为 Demo",
                  bg=COLOR_SAVE_BTN, fg="white",
                  font=("", 10, "bold"), relief="flat",
                  cursor="hand2", padx=10, pady=4,
                  activebackground="#d97706",
                  command=self._save_snippet).pack(side="left", padx=6)

        tk.Button(run_bar, text="📋 复制代码",
                  relief="flat", padx=8, pady=4,
                  command=self._copy_code).pack(side="left")
        tk.Button(run_bar, text="🗑 清空",
                  relief="flat", padx=8, pady=4,
                  command=self._clear_editor).pack(side="right")

        # ── 输出区（白底，与代码区视觉区分）────────────────────────
        out_frame = tk.Frame(parent, bg=COLOR_BORDER, bd=1, relief="solid")
        out_frame.pack(fill="both", expand=True, pady=(0, 0))

        out_header = tk.Frame(out_frame, bg=COLOR_CARD_H)
        out_header.pack(fill="x")
        ttk.Label(out_header, text="📤 输出",
                  font=("", 10, "bold"),
                  background=COLOR_CARD_H).pack(side="left", padx=8, pady=4)
        self.output_status = tk.Label(out_header, text="（无输出）",
                                       bg=COLOR_CARD_H, fg=COLOR_MUTED,
                                       font=("", 9))
        self.output_status.pack(side="right", padx=8)

        self.output_text = tk.Text(out_frame, font=("Cascadia Code", 10),
                                    bg=COLOR_OUTPUT_BG, fg=COLOR_OUTPUT_FG,
                                    wrap="word", relief="flat", bd=0,
                                    padx=10, pady=8, state="disabled")
        self.output_text.pack(fill="both", expand=True, side="left")

        v_scroll2 = ttk.Scrollbar(out_frame, orient="vertical", command=self.output_text.yview)
        v_scroll2.pack(side="right", fill="y")
        self.output_text.configure(yscrollcommand=v_scroll2.set)
        self.output_text.tag_configure("error", foreground=COLOR_ERROR)
        self.output_text.tag_configure("ok", foreground=COLOR_OK)
        self.output_text.tag_configure("info", foreground="#0ea5e9")
        self.output_text.tag_configure("stdout", foreground=COLOR_OUTPUT_FG)
        self.output_text.tag_configure("stderr", foreground=COLOR_ERROR)
        self.output_text.tag_configure("sys", foreground="#a855f7")

        # 语法高亮标签
        self._apply_code_tags()

        # 占位提示（首次）
        self._show_placeholder()

    # ------------------------------------------------------------------
    # 占位提示
    # ------------------------------------------------------------------
    def _show_placeholder(self):
        """首次进入时显示工作流提示"""
        if not self.code_text.get("1.0", "end-1c").strip():
            self.code_text.insert("1.0", CODE_PLACEHOLDER)
            self.code_text.configure(fg=COLOR_PLACEHOLDER)
            self._placeholder_shown = True

    def _on_editor_focus_in(self, event=None):
        """点击编辑器时清除占位"""
        if self._placeholder_shown:
            self.code_text.delete("1.0", "end")
            self.code_text.configure(fg=COLOR_CODE_FG)
            self._placeholder_shown = False

    def _clear_editor(self):
        self.code_text.delete("1.0", "end")
        self._placeholder_shown = False
        self.code_text.configure(fg=COLOR_CODE_FG)

    # ------------------------------------------------------------------
    # 语法高亮
    # ------------------------------------------------------------------
    def _apply_code_tags(self):
        if not HAS_PYGMENTS:
            return
        tags = {
            "k":  "#cf222e",   # keyword 红
            "s":  "#0a3069",   # string 深蓝
            "n":  "#0550ae",   # number 蓝
            "c":  "#6e7781",   # comment 灰
            "p":  "#1f2328",   # plain
            "b":  "#8250df",   # builtin 紫
            "o":  "#cf222e",   # operator 红
        }
        for tag, color in tags.items():
            self.code_text.tag_configure(tag, foreground=color)

    def _highlight_code(self):
        if not HAS_PYGMENTS:
            return
        lang = self.lang_combo.get()
        lexer_cls = LEXER_MAP.get(lang)
        if not lexer_cls:
            return
        try:
            code = self.code_text.get("1.0", "end-1c")
            self.code_text.tag_remove("k", "1.0", "end")
            self.code_text.tag_remove("s", "1.0", "end")
            self.code_text.tag_remove("n", "1.0", "end")
            self.code_text.tag_remove("c", "1.0", "end")
            self.code_text.tag_remove("b", "1.0", "end")
            self.code_text.tag_remove("o", "1.0", "end")
            for tok, val in lex(code, lexer_cls()):
                tag = None
                if tok in Token.Keyword: tag = "k"
                elif tok in Token.String: tag = "s"
                elif tok in Token.Number: tag = "n"
                elif tok in Token.Comment: tag = "c"
                elif tok in Token.Name.Builtin: tag = "b"
                elif tok in Token.Operator: tag = "o"
                if tag:
                    start = "1.0"
                    # 简化：用 search 找 val
                    idx = "1.0"
                    while True:
                        pos = self.code_text.search(val, idx, stopindex="end", nocase=False)
                        if not pos:
                            break
                        end_pos = f"{pos}+{len(val)}c"
                        self.code_text.tag_add(tag, pos, end_pos)
                        idx = end_pos
        except Exception:
            pass

    def _on_lang_change(self, event=None):
        self._highlight_code()

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _load_courses(self):
        import study_demo_db as db
        self.courses = db.list_courses(self.db)
        self.course_listbox.delete(0, "end")
        for c in self.courses:
            self.course_listbox.insert("end", c["name"])
        # 清空章节和片段
        self._clear_chapter_and_snippet()

    def _clear_chapter_and_snippet(self):
        self.chapter_listbox.delete(0, "end")
        self.snippet_listbox.delete(0, "end")
        self.chapters = []
        self.snippets = []
        self.current_course_id = None
        self.current_chapter_id = None
        self.current_snippet_id = None
        self.snippet_title_var.set("（新片段）")
        self._clear_editor()
        self._show_placeholder()

    def _on_course_select(self, event=None):
        idx = self.course_listbox.curselection()
        if not idx:
            return
        self.current_course_id = self.courses[idx[0]]["id"]
        self._load_chapters()
        self._load_snippets()
        # 选新课程 → 清空当前编辑
        self._clear_editor()
        self._show_placeholder()
        self._set_status(f"已选课程: {self.courses[idx[0]]['name']}")

    def _load_chapters(self):
        import study_demo_db as db
        self.chapters = db.list_chapters(self.db, self.current_course_id) if self.current_course_id else []
        self.chapter_listbox.delete(0, "end")
        for c in self.chapters:
            label = c["title"]
            if c.get("note_ref"):
                label += " 📎"
            self.chapter_listbox.insert("end", label)

    def _on_chapter_select(self, event=None):
        idx = self.chapter_listbox.curselection()
        if not idx:
            return
        self.current_chapter_id = self.chapters[idx[0]]["id"]
        self._load_snippets()
        self._clear_editor()
        self._show_placeholder()
        self._load_note_link()
        self._set_status(f"已选章节: {self.chapters[idx[0]]['title']}")

    def _load_snippets(self):
        import study_demo_db as db
        self.snippets = db.list_snippets(self.db, self.current_chapter_id) if self.current_chapter_id else []
        self.snippet_listbox.delete(0, "end")
        for s in self.snippets:
            lang_tag = f"[{s['language']}]" if s.get("language") else ""
            self.snippet_listbox.insert("end", f"{lang_tag} {s['title']}")

    def _on_snippet_select(self, event=None):
        idx = self.snippet_listbox.curselection()
        if not idx:
            return
        self.current_snippet_id = self.snippets[idx[0]]["id"]
        self._load_snippet_to_editor()

    def _load_snippet_to_editor(self):
        import study_demo_db as db
        snippet = db.get_snippet(self.db, self.current_snippet_id)
        if not snippet:
            return
        self._clear_editor()
        self.code_text.insert("1.0", snippet.get("code", ""))
        self.code_text.configure(fg=COLOR_CODE_FG)
        self._placeholder_shown = False
        self.snippet_title_var.set(f"📝 {snippet.get('title', '')}")
        lang = snippet.get("language", "python")
        if lang in LANGUAGE_OPTIONS:
            self.lang_combo.set(lang)
        else:
            self.lang_combo.set("text")
        self._highlight_code()
        self._set_status(f"已加载片段: {snippet.get('title', '')}")

    def _load_note_link(self):
        import study_demo_db as db
        if not self.current_chapter_id:
            return
        ch = db.get_chapter(self.db, self.current_chapter_id)
        if ch and ch.get("note_ref"):
            note_name = Path(ch["note_ref"]).name
            self.snippet_title_var.set(f"📖 {ch.get('title','')}  📎 {note_name}")

    def _set_status(self, msg):
        self.status_var.set(msg)

    # ------------------------------------------------------------------
    # 增删改
    # ------------------------------------------------------------------
    def _simple_input(self, title, prompt, default=""):
        dlg = _InputDialog(self, title, prompt, default)
        return dlg.result

    def _get_selected_course(self):
        idx = self.course_listbox.curselection()
        if not idx: return None
        return self.courses[idx[0]]

    def _get_selected_chapter(self):
        idx = self.chapter_listbox.curselection()
        if not idx: return None
        return self.chapters[idx[0]]

    def _get_selected_snippet(self):
        idx = self.snippet_listbox.curselection()
        if not idx: return None
        return self.snippets[idx[0]]

    def _add_course(self):
        name = self._simple_input("新增课程", "课程名称:")
        if not name: return
        import study_demo_db as db
        db.add_course(self.db, name)
        self._load_courses()

    def _edit_course(self):
        c = self._get_selected_course()
        if not c: return
        new_name = self._simple_input("编辑课程", "课程名称:", default=c["name"])
        if not new_name: return
        import study_demo_db as db
        db.update_course(self.db, c["id"], new_name)
        self._load_courses()

    def _delete_course(self):
        c = self._get_selected_course()
        if not c: return
        if not messagebox.askyesno("确认删除", f"删除课程「{c['name']}」及其所有章节/片段？", parent=self):
            return
        import study_demo_db as db
        db.delete_course(self.db, c["id"])
        self._load_courses()

    def _add_chapter(self):
        if not self.current_course_id:
            messagebox.showinfo("提示", "请先选择课程", parent=self)
            return
        title = self._simple_input("新增章节", "章节标题:")
        if not title: return
        import study_demo_db as db
        db.add_chapter(self.db, self.current_course_id, title)
        self._load_chapters()

    def _edit_chapter(self):
        c = self._get_selected_chapter()
        if not c: return
        new_title = self._simple_input("编辑章节", "章节标题:", default=c["title"])
        if not new_title: return
        import study_demo_db as db
        db.update_chapter(self.db, c["id"], new_title)
        self._load_chapters()

    def _delete_chapter(self):
        c = self._get_selected_chapter()
        if not c: return
        if not messagebox.askyesno("确认删除", f"删除章节「{c['title']}」及其所有片段？", parent=self):
            return
        import study_demo_db as db
        db.delete_chapter(self.db, c["id"])
        self._load_chapters()
        self._load_snippets()

    def _add_snippet(self):
        """手动新增片段（不依赖编辑器）"""
        if not self.current_chapter_id:
            messagebox.showinfo("提示", "请先选择章节\n\n工作流：选课程 → 选章节 → 写代码 → 运行 → 保存",
                                parent=self)
            return
        title = self._simple_input("新增片段", "片段标题（demo 名称）:")
        if not title: return
        code = self.code_text.get("1.0", "end-1c")
        if self._placeholder_shown or not code.strip():
            code = ""
        lang = self.lang_combo.get()
        import study_demo_db as db
        sid = db.add_snippet(self.db, self.current_chapter_id, title, code, lang)
        self._load_snippets()
        self.current_snippet_id = sid
        self._set_status(f"已新增片段: {title}")

    def _edit_snippet(self):
        s = self._get_selected_snippet()
        if not s: return
        new_title = self._simple_input("编辑片段", "片段标题:", default=s["title"])
        if not new_title: return
        import study_demo_db as db
        db.update_snippet(self.db, s["id"], new_title)
        self._load_snippets()

    def _delete_snippet(self):
        s = self._get_selected_snippet()
        if not s: return
        if not messagebox.askyesno("确认删除", f"删除片段「{s['title']}」？", parent=self):
            return
        import study_demo_db as db
        db.delete_snippet(self.db, s["id"])
        self._load_snippets()

    def _open_demo_folder(self):
        """打开 study_demo/ 文件夹"""
        folder = self.demo_root
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as ex:
            messagebox.showerror("错误", f"无法打开文件夹: {ex}", parent=self)

    # ------------------------------------------------------------------
    # 保存 demo（核心工作流）
    # ------------------------------------------------------------------
    def _save_snippet(self):
        """保存当前编辑器内容为 demo 到当前章节"""
        # 检查占位
        if self._placeholder_shown:
            messagebox.showinfo("提示", "编辑器为空，请先写代码", parent=self)
            return
        code = self.code_text.get("1.0", "end-1c")
        if not code.strip():
            messagebox.showinfo("提示", "编辑器为空，请先写代码", parent=self)
            return

        # 必须有章节
        if not self.current_chapter_id:
            messagebox.showwarning("无法保存",
                "请先选择章节！\n\n工作流：选课程 → 选章节 → 写代码 → 运行 → 保存为 Demo",
                parent=self)
            return

        lang = self.lang_combo.get()

        # 如果当前选中了一个片段，更新它；否则新建
        s = self._get_selected_snippet()
        import study_demo_db as db
        if s:
            if not messagebox.askyesno("更新片段", f"更新现有片段「{s['title']}」？", parent=self):
                return
            db.update_snippet_code(self.db, s["id"], code, lang)
            self.snippet_title_var.set(f"📝 {s['title']}")
            self._set_status(f"已更新片段: {s['title']}")
        else:
            # 新建
            default_title = f"Demo_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            title = self._simple_input("保存为 Demo", "为这个 demo 起个名字:", default=default_title)
            if not title: return
            sid = db.add_snippet(self.db, self.current_chapter_id, title, code, lang)
            self.current_snippet_id = sid
            self.snippet_title_var.set(f"📝 {title}")
            self._set_status(f"已保存 demo: {title}")

        self._load_snippets()
        self._highlight_code()
        self._append_output("\n[已保存]\n", "ok")

    # ------------------------------------------------------------------
    # 运行代码
    # ------------------------------------------------------------------
    def _run_code(self, event=None):
        if self._running:
            messagebox.showinfo("提示", "代码正在运行中，请先停止", parent=self)
            return
        if self._placeholder_shown:
            messagebox.showinfo("提示", "编辑器为空，请先写代码", parent=self)
            return
        code = self.code_text.get("1.0", "end-1c")
        if not code.strip():
            messagebox.showinfo("提示", "编辑器为空", parent=self)
            return

        lang = self.lang_combo.get()
        if lang == "text":
            messagebox.showinfo("提示", "纯文本不支持运行，请选择编程语言", parent=self)
            return

        self._clear_output()
        self._set_status("运行中...")
        self._running = True
        self.run_btn.configure(state="disabled")

        thread = threading.Thread(target=self._run_subprocess, args=(code, lang), daemon=True)
        thread.start()

    def _run_subprocess(self, code, lang):
        try:
            if lang == "python":
                self._run_python(code)
            elif lang == "javascript":
                self._run_javascript(code)
            elif lang == "sql":
                self._run_sql(code)
            elif lang == "bash":
                self._run_bash(code)
        except Exception as ex:
            self._append_output(f"\n[错误] {ex}\n", "error")
            self._append_output(traceback.format_exc(), "error")
        finally:
            self._running = False
            self.after(0, lambda: self.run_btn.configure(state="normal"))
            self.after(0, lambda: self._set_status("就绪"))

    def _run_python(self, code):
        """用 sys.executable 子进程跑，超时 30 秒"""
        self._append_output(f"[sys] Python {sys.version.split()[0]}\n", "sys")
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace"
        )
        self._wait_proc(proc, timeout=30)

    def _run_javascript(self, code):
        self._append_output("[sys] JavaScript (Node.js)\n", "sys")
        node = "node.exe" if sys.platform == "win32" else "node"
        try:
            proc = subprocess.Popen(
                [node, "-e", code],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                shell=False
            )
            self._wait_proc(proc, timeout=30)
        except FileNotFoundError:
            self._append_output("[error] 未找到 node，请先安装 Node.js\n", "error")

    def _run_sql(self, code):
        self._append_output("[sys] SQL 执行（sqlite3）\n", "sys")
        import sqlite3, tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name
        try:
            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            for stmt in code.split(";"):
                stmt = stmt.strip()
                if not stmt: continue
                try:
                    cur.execute(stmt)
                    if cur.description:
                        cols = [d[0] for d in cur.description]
                        self._append_output(" | ".join(cols) + "\n", "info")
                        for row in cur.fetchall():
                            self._append_output(" | ".join(str(c) for c in row) + "\n", "stdout")
                    conn.commit()
                except Exception as ex:
                    self._append_output(f"[error] {ex}\n", "error")
            conn.close()
        finally:
            try: os.unlink(tmp_db)
            except: pass

    def _run_bash(self, code):
        self._append_output("[sys] Bash\n", "sys")
        if sys.platform == "win32":
            # 用 Git Bash 或 WSL
            for bash in ["C:\\Program Files\\Git\\bin\\bash.exe", "C:\\Program Files (x86)\\Git\\bin\\bash.exe", "bash"]:
                if os.path.exists(bash) or bash == "bash":
                    try:
                        proc = subprocess.Popen(
                            [bash, "-c", code],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace",
                            shell=False
                        )
                        self._wait_proc(proc, timeout=30)
                        return
                    except FileNotFoundError:
                        continue
            self._append_output("[error] 未找到 bash（请安装 Git for Windows）\n", "error")
        else:
            proc = subprocess.Popen(
                ["/bin/bash", "-c", code],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace"
            )
            self._wait_proc(proc, timeout=30)

    def _wait_proc(self, proc, timeout=30):
        """使用 communicate() 捕获输出，更可靠"""
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            if stdout:
                self._append_output(stdout, "stdout")
            if stderr:
                self._append_output(stderr, "stderr")
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            if stdout:
                self._append_output(stdout, "stdout")
            if stderr:
                self._append_output(stderr, "stderr")
            self._append_output(f"\n[超时] 已终止（>{timeout}秒）\n", "error")
            return

        rc = proc.returncode
        if rc == 0:
            self._append_output(f"\n[完成] 退出码 0\n", "ok")
        else:
            self._append_output(f"\n[失败] 退出码 {rc}\n", "error")


    def _stop_run(self):
        # 子进程没有保存句柄，只能等超时。建议用户先等待
        messagebox.showinfo("提示", "代码运行有 30 秒超时保护，请等待自动结束", parent=self)

    def _copy_code(self):
        code = self.code_text.get("1.0", "end-1c")
        if self._placeholder_shown or not code.strip():
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self._set_status("已复制到剪贴板")

    # ------------------------------------------------------------------
    # 输出区
    # ------------------------------------------------------------------
    def _clear_output(self):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")
        self.output_status.configure(text="（无输出）")

    def _append_output(self, text, tag="stdout"):
        def _do():
            self.output_text.configure(state="normal")
            self.output_text.insert("end", text, tag)
            self.output_text.see("end")
            self.output_text.configure(state="disabled")
            self.output_status.configure(text=f"最后输出: {len(text)} 字符")
        self.after(0, _do)

    # ------------------------------------------------------------------
    # 关联笔记
    # ------------------------------------------------------------------
    def _link_note(self):
        c = self._get_selected_chapter()
        if not c:
            messagebox.showinfo("提示", "请先选择章节", parent=self)
            return
        path = filedialog.askopenfilename(
            title="选择笔记文件",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All", "*.*")],
            parent=self,
        )
        if not path: return
        import study_demo_db as db
        db.update_chapter_note(self.db, c["id"], path)
        self._load_chapters()
        self._load_note_link()
        self._set_status(f"已关联笔记: {Path(path).name}")


# ---------------------------------------------------------------------------
# 输入对话框
# ---------------------------------------------------------------------------
class _InputDialog(tk.Toplevel):
    def __init__(self, parent, title, prompt, default=""):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.resizable(False, False)

        ttk.Label(self, text=prompt, font=("", 10)).pack(padx=16, pady=(16, 6), anchor="w")
        self.entry = ttk.Entry(self, width=40, font=("", 10))
        self.entry.insert(0, default)
        self.entry.pack(padx=16, pady=(0, 12), fill="x")
        self.entry.focus_set()
        self.entry.select_range(0, "end")

        btns = ttk.Frame(self)
        btns.pack(pady=(0, 16))
        ttk.Button(btns, text="确定", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self._cancel).pack(side="left", padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())

        # 居中
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _ok(self):
        self.result = self.entry.get().strip()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# 兼容旧引用
_dt = __import__("datetime")