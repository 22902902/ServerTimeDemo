# -*- coding: utf-8 -*-
"""流程中心（视图层 + 交互逻辑）。

分层
--------------------------------------------------------------------------------
::

    process_db.py      数据层（建表 / 加列迁移 / CRUD / 变量插值 / 危险命令识别）
    process_page.py    本文件：界面 + 交互
    main.py            只留一个外层容器 Frame 与一个 refresh 垫片

与 ``todo_page.py`` 同一范式（``class XxxPage(ttk.Frame)``），业务逻辑随视图
一起住在页面里 —— 流程中心原先 360 行处理器堆在 ``main.py`` 里，是唯一没跟
上分层约定的旧模块。

界面
--------------------------------------------------------------------------------
    ┌──────────┬──────────────────────────────────────────────────────┐
    │ 流程列表  │ 流程头：标题 / 分类 / 平台        进度 3/7 ▓▓▓░░░      │
    │ 230px    │        [开始执行][编辑][导出][复制为脚本]              │
    │          ├──────────────────────────────────────────────────────┤
    │ ★ 收藏    │ 变量栏：域名=[example.com] 环境=[prod]          [改值]  │
    │ 备案 (2)  ├──────────────────────────────────────────────────────┤
    │ 运维 (3)  │ 步骤卡片流（ScrollArea，图文混排，一卡一步）          │
    │          │   ☐ 6 替换证书文件          [命令型][危险]            │
    │          │      前置检查 … / 命令块 … / 预期结果 … / 缩略图×3    │
    │          ├──────────────────────────────────────────────────────┤
    │          │ 快速录入：[输入框] [贴图] [添加]  ← 边做边记           │
    └──────────┴──────────────────────────────────────────────────────┘

为什么步骤不用 Treeview
--------------------------------------------------------------------------------
实测真实数据里的 18 个步骤：截图填充率 **100%**、多图占 **39%**，而原先把截图
塞在 320px 卡片里的 260×170 小窗、多图靠「上一张 / 下一张」翻 —— 最该被看见
的东西被摆在了角落。表格行也装不下「前置检查 / 命令 / 预期结果」三块文本。
于是步骤改成卡片流：一卡一步、截图横排、命令等宽可一键复制。

布局纪律（改这里之前先读 UI_NOTES.md §10）
--------------------------------------------------------------------------------
1. **先 pack 定尺寸控件、后 pack expand 控件** —— 否则后 pack 的固定高度控件
   只分到 0 像素、被 Tk **直接不映射**（代码写了、界面上根本不存在）。
   下面的顺序是：流程头 → 变量栏 → 快速录入条(side=bottom) → 步骤流(expand)。
2. 左侧固定宽度栏由 ``create_two_pane_layout`` 建（它保证先 pack 左栏）。
3. Treeview 的滚动条必须**比表格先 pack**。
4. 步骤流用 ``ui_components.ScrollArea``（``autohide_scrollbar=True``）：它内部
   已处理 scrollregion 即时更新、滚动条按需显隐、装得下就收掉。**不要自己
   再手搓 Canvas** —— 工具箱那边手搓出来的滚轮 rubber-band 坑修过一轮。
5. 每次重建卡片流后必须 ``scroll_top()``：内容变矮时旧的 yOrigin 不会自己
   夹回来，会把内容顶出视野（``yview`` 还照报 (0,1)，看不出来）。
"""

from __future__ import annotations

import json
import os
import re
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from credential_process_dialogs import ProcessStepDialog, ProcessVariablesDialog
from page_components import (
    GUTTER,
    add_toolbar_buttons,
    create_menu_button,
    create_page_toolbar,
    create_status_bar,
    create_two_pane_layout,
)
from process_db import (
    RUN_STATUS_DONE,
    STEP_KIND_CMD,
    STEP_KIND_CHECK,
    STEP_KIND_NOTE,
    STEP_KIND_OP,
    build_run_script,
    danger_reasons,
    parse_variables,
    render_template,
    step_kind_label,
)
from ui_components import ScrollArea, create_flat_menu, create_ttk_section_header
from ui_theme import MAIN_PALETTE, TYPOGRAPHY

try:
    from PIL import Image, ImageTk, UnidentifiedImageError
    HAS_PIL = True
except ImportError:                     # 没有 Pillow 时截图区降级为文字提示
    HAS_PIL = False

THUMB_SIZE = (104, 72)

# 左栏宽度 = 4 个树列之和（24+118+52+30）再留出 Treeview 滚动条的位置。
# 只写 230 会把最右边的「步」列挤出可视区 —— 列在、但看不见。
FLOW_LIST_WIDTH = 248

# 步骤类型 → 徽章配色（只用 palette 里已有的语义色，不另引调色板）
KIND_BADGE_STYLE = {
    STEP_KIND_OP:    ("surface_alt", "text_secondary"),
    STEP_KIND_CMD:   ("badge_bg", "accent"),
    STEP_KIND_CHECK: ("badge_bg", "success"),
    STEP_KIND_NOTE:  ("surface_alt", "text_muted"),
}

VAR_LINE_PATTERN = re.compile(r"^\s*([^=]+?)\s*=\s*(.*)$")


class ProcessImageTools:
    """页面要用到的图片能力。

    由 ``main`` 注入而不是反向 ``import main``（会循环导入）：这几个函数都住在
    ``main.py`` 里，且依赖它模块级的 ``BASE_DIR`` —— 打包后是 ``dist/``，路径
    解析规则不能在这里重写一遍。
    """

    def __init__(self, *, base_dir, resolve_paths, storage_value, make_dir,
                 parse_items, serialize_items):
        self.base_dir = Path(base_dir)              # 打包后是 dist/，路径以它为根
        self.resolve_paths = resolve_paths          # (value) -> list[Path]
        self.storage_value = storage_value          # (Path) -> str（相对 BASE_DIR）
        self.make_dir = make_dir                    # (subdir) -> Path
        self.parse_items = parse_items              # (value) -> list[dict]
        self.serialize_items = serialize_items      # (list[dict]) -> str


class ProcessPage(ttk.Frame):
    """流程中心页面。由 ``main`` 建一次，之后靠 pack / pack_forget 切换。"""

    def __init__(self, master, db, *, app_title: str, flow_templates,
                 image_preview_cls, images: ProcessImageTools, format_datetime,
                 on_status=None, palette=MAIN_PALETTE, typography=TYPOGRAPHY):
        super().__init__(master)
        self.db = db
        self.app_title = app_title
        self.flow_templates = flow_templates or []
        self.image_preview_cls = image_preview_cls
        self.images = images
        self.format_datetime = format_datetime
        self.on_status = on_status
        self.palette = palette
        self.typography = typography

        # ── 视图状态 ──
        self.search_var = tk.StringVar()
        self.template_var = tk.StringVar(
            value=self.flow_templates[0]["label"] if self.flow_templates else ""
        )
        self.status_var = tk.StringVar(value="流程中心已就绪。")
        self.flow_title_var = tk.StringVar(value="请选择左侧流程")
        self.flow_meta_var = tk.StringVar(value="还没有选中流程。")
        self.progress_var = tk.StringVar(value="")
        self.quick_var = tk.StringVar()

        self._flow_rows: dict[str, object] = {}
        self._variable_overrides: dict[str, str] = {}
        self._thumb_refs: list = []          # 挡住缩略图被 GC
        self._flow_menu = None               # 必须保引用，否则 tk_popup 一闪就没
        self._matched_step_ids: set[int] = set()

        self._build()
        self.refresh_flows()

    # ==================================================================
    # 构建
    # ==================================================================
    def _build(self):
        self._build_toolbar()
        _, left, right = create_two_pane_layout(
            self,
            # 248 是算出来的：树列宽合计 224，再加 Treeview 自己的滚动条约 17px
            left_width=FLOW_LIST_WIDTH,
            right_pad=(16, 0),
            padding=(GUTTER, 0, GUTTER, 16),
        )
        self._build_flow_list(left)
        self._build_right_pane(right)
        create_status_bar(self, self.status_var, padding=(24, 0, 24, 16))

    # -- 工具栏 ----------------------------------------------------------
    def _build_toolbar(self):
        toolbar = create_page_toolbar(self)
        add_toolbar_buttons(
            toolbar,
            [
                ("新增流程", self.add_flow, "Primary.TButton"),
                ("编辑流程", self.edit_flow),
                ("删除流程", self.delete_flow),
                ("新增步骤", self.add_step),
            ],
        )
        create_menu_button(
            toolbar,
            "更多",
            [
                ("从模板创建流程", self.create_from_template),
                ("从本流程另存为模板", self.save_as_template),
                "---",
                ("复制流程文本", self.copy_flow_text),
                ("复制为脚本", self.copy_script),
                ("导出 Markdown", self.export_markdown),
                "---",
                ("编辑流程变量", self.edit_variables),
                ("查看执行记录", self.show_run_history),
                "---",
                ("打开流程链接", self.open_flow_link),
                ("打开截图目录", self.open_step_image_folder),
            ],
        )
        # 搜索框先 pack 到右侧：以后动作再多起来，被挤掉的应该是按钮
        ttk.Button(toolbar, text="搜索", command=self.refresh_flows).pack(
            side="right", padx=(6, 0)
        )
        ttk.Entry(toolbar, textvariable=self.search_var, width=24).pack(
            side="right", padx=4
        )
        ttk.Combobox(
            toolbar,
            textvariable=self.template_var,
            values=[item["label"] for item in self.flow_templates],
            state="readonly",
            width=16,
        ).pack(side="right", padx=4)

    # -- 左栏：流程列表 --------------------------------------------------
    def _build_flow_list(self, parent):
        create_ttk_section_header(parent, "流程列表").pack(anchor="w", pady=(0, 6))
        self.flow_tree = ttk.Treeview(
            parent,
            columns=("title", "category", "step_count"),
            show="tree headings",
            height=24,
            selectmode="browse",
        )
        self.flow_tree.heading("#0", text="★", anchor="center")
        self.flow_tree.column("#0", width=24, minwidth=24, stretch=False, anchor="center")
        meta = {
            "title": ("流程名称", 118),
            "category": ("分类", 52),
            "step_count": ("步", 30),
        }
        for column, (title, width) in meta.items():
            self.flow_tree.heading(column, text=title, anchor="w")
            self.flow_tree.column(
                column, width=width, minwidth=30,
                anchor="center" if column == "step_count" else "w",
            )
        # 滚动条先于 Treeview pack，否则会被表格请求宽度挤成 0 宽
        scroll = ttk.Scrollbar(parent, orient="vertical", command=self.flow_tree.yview)
        self.flow_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.flow_tree.pack(side="left", fill="both", expand=True)
        self.flow_tree.bind("<<TreeviewSelect>>", lambda e: self.refresh_steps())
        self.flow_tree.bind("<Double-1>", lambda e: self.edit_flow())
        self.flow_tree.bind("<Button-3>", self.popup_flow_menu)

    # -- 右栏 ------------------------------------------------------------
    def _build_right_pane(self, parent):
        # ① 流程头（固定高度，先 pack）
        head = ttk.Frame(parent)
        head.pack(fill="x")
        title_row = ttk.Frame(head)
        title_row.pack(fill="x")
        ttk.Label(title_row, textvariable=self.flow_title_var,
                  style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(title_row, textvariable=self.flow_meta_var,
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(title_row, textvariable=self.progress_var,
                  style="Muted.TLabel").pack(side="right")

        self.progress_canvas = tk.Canvas(head, height=4, highlightthickness=0, bd=0,
                                        bg=self.palette.bg)
        self.progress_canvas.pack(fill="x", pady=(6, 8))
        self.progress_canvas.bind("<Configure>", lambda e: self._paint_progress())

        actions = ttk.Frame(head)
        actions.pack(fill="x", pady=(0, 4))
        # 「开始执行」的文案会随执行状态变，所以单独建并留引用；不能再经
        # add_toolbar_buttons 加一遍，否则界面上会出现两个同名按钮
        self.run_button = ttk.Button(actions, text="开始执行",
                                     style="Primary.TButton", command=self.toggle_run)
        self.run_button.pack(side="left", padx=(4, 0))
        add_toolbar_buttons(
            actions,
            [
                ("编辑流程", self.edit_flow),
                ("导出 Markdown", self.export_markdown),
                ("复制为脚本", self.copy_script),
            ],
        )

        # ② 变量栏（固定高度，先 pack）
        self.var_bar = ttk.Frame(head)
        self.var_bar.pack(fill="x", pady=(4, 10))

        # ③ 快速录入条：pack 到**底部**，必须在 expand 控件之前 pack，
        #    否则只分到 0 像素、被 Tk 直接不映射
        entry_bar = ttk.Frame(parent, padding=(0, 8, 0, 0))
        entry_bar.pack(side="bottom", fill="x")
        ttk.Label(entry_bar, text="快速录入", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        self.quick_entry = ttk.Entry(entry_bar, textvariable=self.quick_var)
        self.quick_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.quick_entry.bind("<Return>", lambda e: (self.quick_add_step(), "break")[1])
        ttk.Button(entry_bar, text="贴图", command=self.paste_step_image).pack(side="left")
        ttk.Button(entry_bar, text="添加步骤", style="Primary.TButton",
                   command=self.quick_add_step).pack(side="left", padx=4)
        ttk.Label(
            entry_bar,
            text="回车建步骤；行首「$ 」建命令型、「! 」建校验型；截图后直接点「贴图」",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))

        # ④ 步骤卡片流（最后一个 pack，吃掉剩余空间）
        self.step_area = ScrollArea(parent, bg=self.palette.bg,
                                    inner_bg=self.palette.bg,
                                    autohide_scrollbar=True)
        self.step_area.pack(fill="both", expand=True)
        self.step_holder = self.step_area.inner

        # ⑤ 大图查看器（沿用账号中心的预览组件，不 pack，只在「看大图」时用）
        self.image_viewer = self.image_preview_cls(
            self, preview_size=(260, 170), empty_text="选中步骤后查看截图。"
        )

    # ==================================================================
    # 刷新
    # ==================================================================
    def refresh_flows(self, select_flow_id=None):
        """重建流程列表，随后联动刷新步骤。"""
        target = select_flow_id if select_flow_id is not None else self._selected_flow_id(silent=True)
        keyword = self.search_var.get().strip()
        self._matched_step_ids = self.db.fetch_matching_step_ids(keyword) if keyword else set()

        counts: dict[int, int] = {}
        for step in self.db.fetch_all_process_steps():
            flow_id = int(step["flow_id"])
            counts[flow_id] = counts.get(flow_id, 0) + 1

        for item in self.flow_tree.get_children():
            self.flow_tree.delete(item)
        self._flow_rows = {}
        rows = self.db.fetch_process_flows(keyword)
        for row in rows:
            iid = f"flow_{row['id']}"
            self._flow_rows[iid] = row
            self.flow_tree.insert(
                "", "end", iid=iid,
                text="★" if int(row["favorite"] or 0) else "",
                values=(row["title"], row["category"] or "", counts.get(int(row["id"]), 0)),
            )

        if not rows:
            self._set_status("没有匹配的流程。" if keyword else "还没有流程，点「新增流程」开始。")
            self.refresh_steps()
            return

        picked = None
        for iid, row in self._flow_rows.items():
            if int(row["id"]) == int(target or rows[0]["id"]):
                picked = iid
                break
        picked = picked or next(iter(self._flow_rows))
        self.flow_tree.selection_set(picked)
        self.flow_tree.focus(picked)
        self.flow_tree.see(picked)
        self.refresh_steps()
        hit = f"（搜索命中 {len(rows)} 个流程）" if keyword else ""
        self._set_status(f"共 {len(rows)} 个流程{hit}。")

    def refresh_steps(self, select_step_id=None):
        """重建右侧：流程头 / 变量栏 / 进度 / 步骤卡片流。"""
        flow = self._selected_flow(silent=True)
        if flow is None:
            self.flow_title_var.set("请选择左侧流程")
            self.flow_meta_var.set("还没有选中流程。")
            self.progress_var.set("")
            self._paint_variable_bar(None)
            self._paint_progress()
            self.step_area.clear()
            self._empty_hint("左侧还没有选中流程。")
            self._set_status("请选择左侧流程。")
            return

        steps = self.db.fetch_process_steps(int(flow["id"]))
        self.flow_title_var.set(flow["title"])
        meta = " · ".join(x for x in (flow["category"] or "", flow["platform"] or "") if x)
        self.flow_meta_var.set(meta or "未填分类/平台")
        self._paint_variable_bar(flow)

        run, done_ids = self._run_state(int(flow["id"]))
        self._paint_progress(run=run, done=len(done_ids), total=len(steps))
        self._paint_run_button(run)
        # 进度条只画色块，数字得自己写 —— 否则「跑到第几步」要用户去数卡片
        self.progress_var.set(
            f"执行中 {len(done_ids)} / {len(steps)}" if run
            else f"共 {len(steps)} 步 · 未开始"
        )

        self.render_steps(flow, steps, done_ids=done_ids)
        self._set_status(f"「{flow['title']}」共 {len(steps)} 个步骤。")

    def render_steps(self, flow, steps, *, done_ids=None):
        for child in self.step_holder.winfo_children():
            child.destroy()
        self._thumb_refs = []
        self.step_area.scroll_top()      # 内容变矮时旧 yOrigin 不会自己夹回来

        values = self.variable_values()
        done_ids = done_ids or set()
        for index, step in enumerate(steps, start=1):
            card = build_step_card(
                self.step_holder, step, index=index, variables=values,
                done=int(step["id"]) in done_ids,
                matched=int(step["id"]) in self._matched_step_ids,
                page=self, thumb_refs=self._thumb_refs,
            )
            card.pack(fill="x", pady=(0, 8))

    def _empty_hint(self, text):
        tk.Label(self.step_holder, text=text, bg=self.palette.bg,
                 fg=self.palette.text_muted, font=self.typography.body,
                 justify="left", anchor="w").pack(fill="x", pady=(24, 0))

    # ==================================================================
    # 选中项
    # ==================================================================
    def _selected_flow_id(self, silent: bool = False) -> int | None:
        selection = self.flow_tree.selection()
        if not selection:
            if not silent:
                messagebox.showinfo(self.app_title, "请先选择一个流程。", parent=self)
            return None
        row = self._flow_rows.get(selection[0])
        if not row:
            if not silent:
                messagebox.showwarning(self.app_title, "当前流程不存在。", parent=self)
            return None
        return int(row["id"])

    def _selected_flow(self, silent: bool = False):
        flow_id = self._selected_flow_id(silent=silent)
        if flow_id is None:
            return None
        return self.db.get_process_flow(flow_id)

    def _current_steps(self):
        flow = self._selected_flow(silent=True)
        if flow is None:
            return []
        return self.db.fetch_process_steps(int(flow["id"]))

    # ==================================================================
    # 变量
    # ==================================================================
    def variable_definitions(self):
        flow = self._selected_flow(silent=True)
        return parse_variables(flow["variables"]) if flow else []

    def variable_values(self) -> dict[str, str]:
        values = {}
        for item in self.variable_definitions():
            values[item["key"]] = self._variable_overrides.get(item["key"], item.get("default", ""))
        return values

    def render_text(self, text, values=None) -> str:
        return render_template(text, self.variable_values() if values is None else values)

    def _paint_variable_bar(self, flow):
        for child in self.var_bar.winfo_children():
            child.destroy()
        if flow is None:
            return
        definitions = parse_variables(flow["variables"])
        if not definitions:
            ttk.Label(self.var_bar,
                      text="未定义变量。用「更多 → 编辑流程变量」可把域名/环境/路径"
                           "抽成 {{变量}}，一套流程就能服务多个对象。",
                      style="Muted.TLabel").pack(side="left")
            return
        row = ttk.Frame(self.var_bar)
        row.pack(fill="x")
        ttk.Label(row, text="变量", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        values = self.variable_values()
        for item in definitions:
            key = item["key"]
            value = values.get(key, "")
            mark = "" if str(value).strip() else "（空）"
            ttk.Label(row, text=f"{item['label']} = {value}{mark}",
                      style="Muted.TLabel").pack(side="left", padx=(0, 12))
        ttk.Button(row, text="改值", command=self.edit_variables).pack(side="right")

    def edit_variables(self):
        flow = self._selected_flow()
        if flow is None:
            return
        dialog = ProcessVariablesDialog(
            self, "编辑流程变量",
            initial={"variables": flow["variables"] or ""},
            app_title=self.app_title,
        )
        if dialog.result is None:
            return
        self.db.set_process_flow_variables(int(flow["id"]), dialog.result)
        self._variable_overrides = {}
        self.refresh_steps()
        self._set_status("流程变量已保存。")

    # ==================================================================
    # 进度与执行模式
    # ==================================================================
    def _run_state(self, flow_id: int):
        run = self.db.get_active_process_run(flow_id)
        if run is None:
            return None, set()
        done_ids = {int(row["step_id"]) for row in self.db.fetch_process_run_steps(int(run["id"]))
                    if int(row["done"] or 0)}
        return run, done_ids

    def _paint_progress(self, run=None, done=None, total=None):
        canvas = self.progress_canvas
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        canvas.delete("all")
        if width <= 1 or height <= 1:      # 未映射时报 1x1，别按它排宽度相关版式
            return
        canvas.create_rectangle(0, 0, width, height, fill=self.palette.border_soft, outline="")
        if total:
            ratio = max(0.0, min(1.0, (done or 0) / float(total)))
            if ratio:
                canvas.create_rectangle(0, 0, max(2, int(width * ratio)), height,
                                       fill=self.palette.success, outline="")

    def _paint_run_button(self, run):
        self.run_button.configure(text="结束执行" if run else "开始执行")

    def toggle_run(self):
        flow = self._selected_flow()
        if flow is None:
            return
        run, _ = self._run_state(int(flow["id"]))
        if run is None:
            steps = self.db.fetch_process_steps(int(flow["id"]))
            if not steps:
                messagebox.showinfo(self.app_title, "这个流程还没有步骤，先录步骤再执行。",
                                    parent=self)
                return
            self.db.start_process_run(
                int(flow["id"]), title=flow["title"] or "",
                env=self.variable_values().get("环境", ""),
                variables=self.variable_values(),
            )
            self._set_status("已开始执行：勾选步骤记录进度，变量快照已存。")
        else:
            self.db.finish_process_run(int(run["id"]), RUN_STATUS_DONE)
            self._set_status("本次执行已结束。")
        self.refresh_steps()

    def set_step_done(self, step_id: int, done: bool):
        flow = self._selected_flow(silent=True)
        if flow is None:
            return
        run, _ = self._run_state(int(flow["id"]))
        if run is None:
            # 直接勾选也允许：自动开一次执行，省得先点「开始执行」
            run_id = self.db.start_process_run(
                int(flow["id"]), title=flow["title"] or "",
                env=self.variable_values().get("环境", ""),
                variables=self.variable_values(),
            )
        else:
            run_id = int(run["id"])
        self.db.set_process_run_step_done(run_id, step_id, done)
        self.refresh_steps()

    def show_run_history(self):
        flow = self._selected_flow()
        if flow is None:
            return
        runs = self.db.fetch_recent_process_runs(int(flow["id"]), limit=10)
        if not runs:
            messagebox.showinfo(self.app_title, "这个流程还没有执行记录。", parent=self)
            return
        lines = []
        for run in runs:
            done, total = self.db.count_process_run_done(int(run["id"]))
            head = f"#{run['id']}  {self.format_datetime(run['started_at'] or '')}  进度 {done}/{total}"
            if run["status"] != "running":
                head += f"  [{run['status']}]"
            lines.append(head)
            if run["env"]:
                lines.append(f"      环境：{run['env']}")
            snapshot = run["variables_json"] or ""
            if snapshot and snapshot != "{}":
                try:
                    table = json.loads(snapshot)
                except ValueError:
                    table = {}
                if table:
                    lines.append("      变量：" + "  ".join(f"{k}={v}" for k, v in table.items()))
        messagebox.showinfo(self.app_title,
                           "最近执行记录：\n\n" + "\n".join(lines), parent=self)

    # ==================================================================
    # 流程 CRUD
    # ==================================================================
    def add_flow(self):
        from credential_process_dialogs import ProcessFlowDialog
        dialog = ProcessFlowDialog(self, "新增流程", app_title=self.app_title)
        if dialog.result:
            flow_id = self.db.add_process_flow(dialog.result)
            self.refresh_flows(select_flow_id=flow_id)
            self._set_status("已新增流程。")

    def edit_flow(self):
        flow = self._selected_flow()
        if flow is None:
            return
        from credential_process_dialogs import ProcessFlowDialog
        dialog = ProcessFlowDialog(self, "编辑流程", initial=dict(flow), app_title=self.app_title)
        if dialog.result:
            self.db.update_process_flow(int(flow["id"]), dialog.result)
            self.refresh_flows(select_flow_id=int(flow["id"]))
            self._set_status("已更新流程。")

    def delete_flow(self):
        flow = self._selected_flow()
        if flow is None:
            return
        step_count = len(self.db.fetch_process_steps(int(flow["id"])))
        reclaim = self.db.collect_flow_orphan_screenshots(int(flow["id"]))
        if not messagebox.askyesno(
            self.app_title,
            f"确认删除流程「{flow['title']}」吗？\n\n"
            f"将同时删除该流程下的 {step_count} 个步骤记录与执行记录。\n"
            + (f"并回收 {len(reclaim)} 张不再被引用的截图。"
               if reclaim else "（没有需要回收的截图）"),
            parent=self,
        ):
            return
        self.db.delete_process_flow(int(flow["id"]))
        removed = self._reclaim_screenshots(reclaim)
        self.refresh_flows()
        self._set_status("已删除流程。"
                         + (f"回收了 {removed} 张截图。" if removed else ""))

    def toggle_favorite(self):
        flow = self._selected_flow()
        if flow is None:
            return
        new_value = not int(flow["favorite"] or 0)
        self.db.set_process_flow_favorite(int(flow["id"]), new_value)
        self.refresh_flows(select_flow_id=int(flow["id"]))
        self._set_status("已" + ("加入收藏。" if new_value else "取消收藏。"))

    def copy_flow_text(self):
        flow = self._selected_flow()
        if flow is None:
            return
        steps = self._current_steps()
        values = self.variable_values()
        lines = [
            f"流程名称：{flow['title']}",
            f"分类：{flow['category'] or ''}",
            f"平台：{flow['platform'] or ''}",
            f"入口链接：{flow['link_url'] or ''}",
        ]
        if values:
            lines.append("变量：" + "  ".join(f"{k}={v}" for k, v in values.items()))
        lines.append(f"备注：{flow['note'] or ''}")
        lines.append("")
        lines.append("步骤明细：")
        if not steps:
            lines.append("（无步骤）")
        for step in steps:
            lines.append(f"【{step['step_no']}】{step['title']}  [{step_kind_label(step['kind'])}]")
            if step["link_url"]:
                lines.append(f"  链接：{step['link_url']}")
            if step["precheck_text"]:
                lines.append(f"  前置检查：{self.render_text(step['precheck_text'], values)}")
            if step["description_text"]:
                lines.append(f"  说明：{self.render_text(step['description_text'], values)}")
            if step["command_text"]:
                lines.append(f"  命令（{step['command_lang']}）：")
                for row in self.render_text(step["command_text"], values).splitlines():
                    lines.append(f"      {row}")
            if step["expected_text"]:
                lines.append(f"  预期结果：{self.render_text(step['expected_text'], values)}")
            filenames = [Path(p).name for p in self.images.resolve_paths(step["screenshot_path"] or "")]
            if filenames:
                lines.append(f"  截图（{len(filenames)}）：" + "、".join(filenames))
            if step["note"]:
                lines.append(f"  备注：{step['note']}")
            lines.append("")
        self.copy_to_clipboard("\n".join(lines).rstrip())
        self._set_status("流程内容已复制到剪贴板。")

    def copy_script(self):
        """把整条流程的命令块拼成可粘贴的 shell 脚本。"""
        flow = self._selected_flow()
        if flow is None:
            return
        steps = self._current_steps()
        if not any((step["command_text"] or "").strip() for step in steps):
            messagebox.showinfo(
                self.app_title,
                "这个流程里还没有命令块。\n\n"
                "把步骤类型改成「命令型」并填上命令，就能一键拼成脚本。",
                parent=self,
            )
            return
        script = build_run_script(flow["title"] or "", steps, self.variable_values(),
                                  env=self.variable_values().get("环境", ""))
        self.copy_to_clipboard(script)
        self._set_status("已把流程内所有命令拼成脚本并复制（变量已渲染）。")

    def export_markdown(self):
        flow = self._selected_flow()
        if flow is None:
            return
        steps = self._current_steps()
        values = self.variable_values()
        default_name = re.sub(r'[\\/:*?"<>|]', "_", flow["title"] or "流程") + ".md"
        path = filedialog.asksaveasfilename(
            title="导出流程为 Markdown",
            defaultextension=".md",
            initialfile=default_name,
            filetypes=[("Markdown", "*.md"), ("所有文件", "*.*")],
            parent=self,
        )
        if not path:
            return
        lines = [f"# {flow['title']}", ""]
        for label, value in (("分类", flow["category"]), ("平台", flow["platform"]),
                             ("入口链接", flow["link_url"])):
            if value:
                lines.append(f"- **{label}**：{value}")
        if values:
            lines.append("- **变量**：" + "；".join(f"`{k}` = `{v}`" for k, v in values.items()))
        if flow["note"]:
            lines.append(f"- **备注**：{flow['note']}")
        lines += ["", "---", ""]
        for step in steps:
            lines.append(f"## {step['step_no']}. {step['title']}　`{step_kind_label(step['kind'])}`")
            lines.append("")
            if step["link_url"]:
                lines.append(f"入口：[{step['link_url']}]({step['link_url']})")
                lines.append("")
            if step["precheck_text"]:
                lines.append(
                    f"> **前置检查**：{self.render_text(step['precheck_text'], values)}"
                )
                lines.append("")
            if step["description_text"]:
                lines.append(self.render_text(step["description_text"], values))
                lines.append("")
            if step["command_text"]:
                lines.append(f"```{step['command_lang'] or 'shell'}")
                lines.append(self.render_text(step["command_text"], values))
                lines.append("```")
                lines.append("")
            if step["expected_text"]:
                lines.append(f"**预期结果**：{self.render_text(step['expected_text'], values)}")
                lines.append("")
            for image_path in self.images.resolve_paths(step["screenshot_path"] or ""):
                try:
                    relative = Path(image_path).relative_to(self.images.base_dir)
                    link = str(relative).replace("\\", "/")
                except (ValueError, OSError):
                    link = str(image_path).replace("\\", "/")
                lines.append(f"![{Path(image_path).stem}]({link})")
                lines.append("")
            if step["note"]:
                lines.append(f"*备注：{step['note']}*")
                lines.append("")
        try:
            Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(self.app_title, f"导出失败：\n{exc}", parent=self)
            return
        self._set_status(f"已导出：{path}")

    def open_flow_link(self):
        flow = self._selected_flow()
        if flow is None:
            return
        link = (flow["link_url"] or "").strip()
        if not link:
            messagebox.showinfo(self.app_title, "当前流程没有入口链接。", parent=self)
            return
        self.open_url(link)

    def create_from_template(self):
        template = self._pick_template()
        if not template:
            messagebox.showinfo(self.app_title, "当前没有可用的流程模板。", parent=self)
            return
        title = (template["flow"].get("title") or "").strip()
        if title and self.db.fetch_process_flows_by_title(title):
            if not messagebox.askyesno(
                self.app_title,
                f"已存在同名流程「{title}」。\n\n是否仍然再创建一份副本？",
                parent=self,
            ):
                return
        flow_id = self.db.add_process_flow(template["flow"])
        created = 0
        for step in template.get("steps", []):
            self.db.add_process_step(flow_id, step)
            created += 1
        self.refresh_flows(select_flow_id=flow_id)
        self._set_status(f"已从模板创建流程，含 {created} 个步骤。")
        messagebox.showinfo(
            self.app_title,
            f"模板创建成功：{title or '未命名'}\n共 {created} 个步骤，可按实际业务继续修改。",
            parent=self,
        )

    def save_as_template(self):
        """把当前流程另存为模板 —— 真正有价值的模板是用户自己攒出来的那些。"""
        flow = self._selected_flow()
        if flow is None:
            return
        steps = self._current_steps()
        item = {
            "key": f"local_{flow['id']}",
            "label": f"{flow['title']}（自建）",
            "flow": {
                "title": flow["title"], "category": flow["category"] or "",
                "platform": flow["platform"] or "", "link_url": flow["link_url"] or "",
                "note": flow["note"] or "", "variables": flow["variables"] or "",
            },
            "steps": [
                {key: step[key] for key in (
                    "step_no", "title", "link_url", "description_text", "required_text",
                    "optional_text", "note", "kind", "command_text", "command_lang",
                    "precheck_text", "expected_text")}
                for step in steps
            ],
        }
        if not any(t.get("key") == item["key"] for t in self.flow_templates):
            self.flow_templates.append(item)
        self.template_var.set(item["label"])
        self._sync_template_combobox()
        self._set_status(f"已把「{flow['title']}」存为模板，可在左侧下拉里选用。")

    def _pick_template(self):
        label = (self.template_var.get() or "").strip()
        for item in self.flow_templates:
            if (item.get("label") or "").strip() == label:
                return item
        return self.flow_templates[0] if self.flow_templates else None

    def _sync_template_combobox(self):
        for child in self.winfo_children():
            self._walk_sync_combobox(child)

    def _walk_sync_combobox(self, widget):
        if isinstance(widget, ttk.Combobox):
            widget.configure(values=[item["label"] for item in self.flow_templates])
        for child in widget.winfo_children():
            self._walk_sync_combobox(child)

    def popup_flow_menu(self, event):
        """流程列表右键菜单。菜单必须保引用，否则一闪就没。"""
        iid = self.flow_tree.identify_row(event.y)
        if iid:
            self.flow_tree.selection_set(iid)
            self.refresh_steps()
        actions = [
            ("新增流程", self.add_flow),
            ("编辑流程", self.edit_flow),
            ("收藏 / 取消收藏", self.toggle_favorite),
            "---",
            ("新增步骤", self.add_step),
            ("编辑变量", self.edit_variables),
            "---",
            ("复制为脚本", self.copy_script),
            ("导出 Markdown", self.export_markdown),
            "---",
            ("删除流程", self.delete_flow),
        ]
        self._flow_menu = create_flat_menu(self, actions, palette=self.palette)
        try:
            self._flow_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._flow_menu.grab_release()

    # ==================================================================
    # 步骤 CRUD
    # ==================================================================
    def add_step(self):
        flow = self._selected_flow()
        if flow is None:
            return
        dialog = ProcessStepDialog(
            self, "新增步骤",
            initial={"step_no": self.db.get_next_process_step_no(int(flow["id"])),
                     "kind": STEP_KIND_OP},
            app_title=self.app_title, image_preview_cls=self.image_preview_cls,
            image_subdir=self._image_subdir(flow),
        )
        if dialog.result:
            self.db.add_process_step(int(flow["id"]), dialog.result)
            self.refresh_flows(select_flow_id=int(flow["id"]))
            self._set_status("已新增步骤。")

    def edit_step(self, step_id=None):
        step = self._resolve_step(step_id)
        if step is None:
            return
        flow = self.db.get_process_flow(int(step["flow_id"]))
        dialog = ProcessStepDialog(
            self, "编辑步骤", initial=dict(step), app_title=self.app_title,
            image_preview_cls=self.image_preview_cls,
            image_subdir=self._image_subdir(flow),
        )
        if dialog.result:
            self.db.update_process_step(int(step["id"]), dialog.result)
            self.refresh_steps()
            self._set_status("已更新步骤。")

    def delete_step(self, step_id=None):
        step = self._resolve_step(step_id)
        if step is None:
            return
        reclaim = self.db.collect_orphan_screenshots([int(step["id"])])
        if not messagebox.askyesno(
            self.app_title,
            f"确认删除步骤【{step['step_no']}】{step['title']}吗？\n"
            + (f"并回收 {len(reclaim)} 张不再被引用的截图。"
               if reclaim else "（没有需要回收的截图）"),
            parent=self,
        ):
            return
        flow_id = int(step["flow_id"])
        self.db.delete_process_step(int(step["id"]))
        self.db.renumber_process_steps(flow_id)
        removed = self._reclaim_screenshots(reclaim)
        self.refresh_flows(select_flow_id=flow_id)
        self._set_status("已删除步骤，后续步骤序号已重排。"
                         + (f"回收了 {removed} 张截图。" if removed else ""))

    def _reclaim_screenshots(self, values) -> int:
        """把「已经没有任何步骤引用」的截图从磁盘删掉，返回删掉的张数。

        只在**用户确认过删除**之后调用，且值来自 ``collect_orphan_screenshots``
        —— 数据层已经把「还有别人引用」的扣掉了，所以这里的删除面收窄到
        「删了也没有人会找不到图」。

        文件不在了不算错（用户可能自己清过），所以吞掉 ``OSError`` 而不是中断
        整个删除流程：删文件失败不该让「删步骤」这件事失败。张数会回报到状态栏，
        真出问题能对得上账。
        """
        removed = 0
        for value in values or []:
            for path in self.images.resolve_paths(value) or []:
                try:
                    if path.is_file():
                        path.unlink()
                        removed += 1
                except OSError:
                    continue
        return removed

    def move_step(self, step_id: int, direction: int):
        if self.db.move_process_step(step_id, direction):
            self.refresh_steps()

    def _resolve_step(self, step_id=None):
        """``step_id`` 为空时退化成「当前选中的步骤」——卡片流没有选中态，
        所以多数调用都会显式传 id。"""
        if step_id is None:
            messagebox.showinfo(self.app_title, "请点步骤卡片上的按钮操作。", parent=self)
            return None
        step = self.db.get_process_step(int(step_id))
        if step is None:
            messagebox.showwarning(self.app_title, "当前步骤不存在。", parent=self)
        return step

    def quick_add_step(self):
        """快速录入：回车建步骤。

        行首「$ 」→ 命令型；「! 」→ 校验型；其余按标题建操作型。
        """
        flow = self._selected_flow()
        if flow is None:
            return
        text = (self.quick_var.get() or "").strip()
        if not text:
            messagebox.showinfo(self.app_title, "先在输入框里写一句话，或点「贴图」。",
                                parent=self)
            return
        payload = {
            "step_no": self.db.get_next_process_step_no(int(flow["id"])),
            "title": text,
            "kind": STEP_KIND_OP,
        }
        if text.startswith("$ "):
            payload["kind"] = STEP_KIND_CMD
            payload["title"] = f"命令 {payload['step_no']}"
            payload["command_text"] = text[2:].strip()
        elif text.startswith("! "):
            payload["kind"] = STEP_KIND_CHECK
            payload["title"] = f"校验 {payload['step_no']}"
            payload["expected_text"] = text[2:].strip()
        self.db.add_process_step(int(flow["id"]), payload)
        self.quick_var.set("")
        self.refresh_flows(select_flow_id=int(flow["id"]))
        self.quick_entry.focus_set()
        self._set_status(f"已添加步骤 {payload['step_no']}。")

    def paste_step_image(self, step_id=None):
        """把剪贴板里的截图贴进步骤；没指定步骤就新建一个带图步骤。"""
        import image_clipboard

        flow = self._selected_flow()
        if flow is None:
            return
        target_dir = self.images.make_dir(self._image_subdir(flow))
        try:
            saved = image_clipboard.save_clipboard_image(self, target_dir)
        except Exception as exc:
            messagebox.showerror(self.app_title, f"保存截图失败：\n{exc}", parent=self)
            return
        if saved is None:
            messagebox.showinfo(
                self.app_title,
                "剪贴板里没有图片。\n\n先用截图工具截一张（或复制图片），再点「贴图」。",
                parent=self,
            )
            return
        stored = self.images.storage_value(saved)

        if step_id is None:
            payload = {
                "step_no": self.db.get_next_process_step_no(int(flow["id"])),
                "title": (self.quick_var.get() or "").strip() or
                         f"步骤 {self.db.get_next_process_step_no(int(flow['id']))}",
                "kind": STEP_KIND_OP,
                "screenshot_path": stored,
            }
            self.db.add_process_step(int(flow["id"]), payload)
            self.quick_var.set("")
        else:
            step = self.db.get_process_step(int(step_id))
            if step is None:
                return
            items = self.images.parse_items(step["screenshot_path"] or "")
            items.append({"path": stored, "label": ""})
            self.db.update_process_step_screenshot(int(step_id), self.images.serialize_items(items))

        self.refresh_flows(select_flow_id=int(flow["id"]))
        self._set_status(f"已贴入截图：{Path(stored).name}")

    def view_step_image(self, step_id=None, index: int = 0):
        step = self._resolve_step(step_id)
        if step is None:
            return
        value = step["screenshot_path"] or ""
        paths = self.images.resolve_paths(value) if value else []
        if not paths:
            messagebox.showinfo(self.app_title, "当前步骤没有截图。", parent=self)
            return
        self.image_viewer.set_value(value)
        self.image_viewer.current_index = max(0, min(int(index), len(paths) - 1))
        self.image_viewer.refresh()
        self.image_viewer.open_large_viewer(parent=self, title="查看步骤截图")

    def open_step_image_folder(self):
        """打开当前流程的截图目录（不存在就现建一个，省得用户自己找）。"""
        flow = self._selected_flow(silent=True)
        if flow is None:
            return
        try:
            target = self.images.make_dir(self._image_subdir(flow))
            os.startfile(str(target))
            self._set_status(f"已打开截图目录：{target}")
        except (OSError, FileNotFoundError) as exc:
            messagebox.showerror(self.app_title, f"打开截图目录失败：\n{exc}", parent=self)

    def open_step_link(self, step_id=None):
        step = self._resolve_step(step_id)
        if step is None:
            return
        link = (step["link_url"] or "").strip()
        if not link:
            messagebox.showinfo(self.app_title, "当前步骤没有链接。", parent=self)
            return
        self.open_url(link)

    def _image_subdir(self, flow):
        return f"process_flows/{int(flow['id'])}" if flow is not None else "process_flows"

    # ==================================================================
    # 工具
    # ==================================================================
    def copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except tk.TclError as exc:
            messagebox.showerror(self.app_title, f"复制失败：\n{exc}", parent=self)

    def open_url(self, url: str):
        target = url if re.match(r"^https?://", url, re.I) else f"https://{url}"
        try:
            webbrowser.open(target)
            self._set_status("已在浏览器中打开。")
        except Exception as exc:
            messagebox.showerror(self.app_title, f"打开链接失败：\n{exc}", parent=self)

    def _set_status(self, message: str):
        self.status_var.set(message)
        if self.on_status:
            try:
                self.on_status(message)
            except Exception:
                pass


# =============================================================================
# 步骤卡片 / 命令块 / 截图画廊（纯视图，回调走 page）
# =============================================================================

def _badge(parent, text: str, bg_attr: str, fg_attr: str, palette=MAIN_PALETTE):
    return tk.Label(parent, text=f" {text} ", bg=getattr(palette, bg_attr),
                    fg=getattr(palette, fg_attr), font=TYPOGRAPHY.badge, padx=2)


class CommandBlock(tk.Frame):
    """命令块：等宽字体 + 一键复制 + 危险原因提示。

    只读 ``Text`` 仍然允许选中与 Ctrl+C，所以既能看也能抠字；「复制」按钮给的
    是**变量已渲染**的内容，与屏幕上看到的一致。
    """

    def __init__(self, master, display_text: str, *, lang: str = "shell", danger=(),
                 palette=MAIN_PALETTE, on_copy=None):
        super().__init__(master, bg=palette.surface_alt,
                         highlightthickness=1, highlightbackground=palette.border_soft)
        self.display_text = display_text
        self.on_copy = on_copy

        head = tk.Frame(self, bg=palette.surface_alt)
        head.pack(fill="x", padx=8, pady=(5, 2))
        tk.Label(head, text=lang or "shell", bg=palette.surface_alt,
                 fg=palette.text_muted, font=TYPOGRAPHY.caption).pack(side="left")
        if danger:
            tk.Label(head, text="危险操作 · " + "、".join(danger), bg=palette.surface_alt,
                     fg=palette.danger, font=TYPOGRAPHY.caption).pack(side="left", padx=(8, 0))
        ttk.Button(head, text="复制", width=6, command=self._copy).pack(side="right")

        lines = display_text.count("\n") + 1
        body = tk.Text(
            self, height=max(1, min(lines, 12)), wrap="char",
            font=TYPOGRAPHY.mono, bg=palette.surface_alt, fg=palette.text_primary,
            relief="flat", highlightthickness=0, bd=0, padx=2, pady=2, cursor="xterm",
        )
        body.insert("1.0", display_text)
        body.configure(state="disabled")
        body.bind("<Control-c>", lambda e: self._copy() or "break")
        body.pack(fill="x", padx=8, pady=(0, 6))
        self.body = body

    def _copy(self):
        if self.on_copy:
            self.on_copy(self.display_text)


class ScreenshotStrip(tk.Frame):
    """截图横排缩略图；点任一张打开大图。"""

    def __init__(self, master, image_value: str, *, page, on_open=None,
                 thumb_refs=None, palette=MAIN_PALETTE):
        super().__init__(master, bg=palette.surface)
        paths = []
        try:
            paths = [p for p in (page.images.resolve_paths(image_value) or []) if p and p.exists()]
        except Exception:
            paths = []

        if not paths:
            tk.Label(self, text="（无截图）", bg=palette.surface, fg=palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(side="left")
            return
        if not HAS_PIL:
            tk.Label(self, text=f"（{len(paths)} 张截图，未安装 Pillow 无法预览）",
                     bg=palette.surface, fg=palette.text_muted,
                     font=TYPOGRAPHY.caption).pack(side="left")
            return

        for index, path in enumerate(paths):
            photo = _load_thumb(path, THUMB_SIZE)
            if photo is None:
                tk.Label(self, text="(图片损坏)", bg=palette.surface, fg=palette.text_muted,
                         font=TYPOGRAPHY.caption).pack(side="left", padx=3)
                continue
            if thumb_refs is not None:
                thumb_refs.append(photo)     # 必须保引用，否则 PhotoImage 被 GC 掉
            holder = tk.Label(self, image=photo, bg=palette.surface,
                              highlightthickness=1,
                              highlightbackground=palette.border_soft, cursor="hand2")
            holder.image = photo
            holder.pack(side="left", padx=(0, 6))
            holder.bind("<Button-1>", lambda e, i=index: on_open(i) if on_open else None)


def _load_thumb(path, size):
    try:
        with Image.open(path) as image:
            preview = image.convert("RGB")
            preview.thumbnail(size)
            return ImageTk.PhotoImage(preview)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    except Exception:
        return None


def _section(parent, title: str, text: str, palette, *, fg=None):
    row = tk.Frame(parent, bg=palette.surface)
    row.pack(fill="x", padx=10, pady=(2, 2))
    tk.Label(row, text=title, bg=palette.surface, fg=palette.text_secondary,
             font=TYPOGRAPHY.caption, width=6, anchor="w").pack(side="left", anchor="n")
    tk.Label(row, text=text, bg=palette.surface, fg=fg or palette.text_primary,
             font=TYPOGRAPHY.body, justify="left", anchor="w",
             wraplength=540).pack(side="left", fill="x", expand=True)
    return row


def build_step_card(parent, step, *, index, variables, done, matched, page,
                    thumb_refs=None, palette=MAIN_PALETTE):
    """渲染一个步骤卡（``step`` 是 sqlite3.Row 或 dict）。"""
    def field(key, default=""):
        try:
            value = step[key]
        except (KeyError, IndexError, TypeError):
            return default
        return default if value is None else value

    def rendered(key):
        return page.render_text(field(key, ""), variables)

    step_id = int(field("id", 0))
    kind = (field("kind", "op") or "op").strip()
    command_text = field("command_text", "")

    card = tk.Frame(parent, bg=palette.surface,
                    highlightthickness=2 if matched else 1,
                    highlightbackground=palette.accent if matched else palette.border_soft)

    # ── 头部 ──
    head = tk.Frame(card, bg=palette.surface)
    head.pack(fill="x", padx=10, pady=(8, 2))
    done_var = tk.BooleanVar(value=done)
    tk.Checkbutton(head, variable=done_var, bg=palette.surface, activebackground=palette.surface,
                   highlightthickness=0, bd=0,
                   command=lambda: page.set_step_done(step_id, done_var.get())).pack(side="left")
    tk.Label(head, text=str(field("step_no", index)), bg=palette.surface,
             fg=palette.text_muted, font=TYPOGRAPHY.badge, width=3,
             anchor="e").pack(side="left")
    tk.Label(head, text=str(field("title", "(无标题)") or "(无标题)"), bg=palette.surface,
             fg=palette.text_primary, font=TYPOGRAPHY.title).pack(side="left", padx=(4, 8))
    bg_attr, fg_attr = KIND_BADGE_STYLE.get(kind, KIND_BADGE_STYLE[STEP_KIND_OP])
    _badge(head, step_kind_label(kind), bg_attr, fg_attr, palette).pack(side="left")

    dangers = danger_reasons(command_text)
    if dangers:
        _badge(head, "危险", "danger", "surface", palette).pack(side="left", padx=4)
        tk.Label(head, text="、".join(dangers), bg=palette.surface, fg=palette.danger,
                 font=TYPOGRAPHY.caption).pack(side="left")

    ttk.Button(head, text="删除", width=5,
               command=lambda: page.delete_step(step_id)).pack(side="right")
    ttk.Button(head, text="编辑", width=5,
               command=lambda: page.edit_step(step_id)).pack(side="right", padx=4)
    ttk.Button(head, text="贴图", width=5,
               command=lambda: page.paste_step_image(step_id)).pack(side="right")

    # ── 链接 ──
    link = field("link_url", "")
    if str(link).strip():
        label = tk.Label(card, text=str(link), bg=palette.surface, fg=palette.link,
                         font=TYPOGRAPHY.caption, cursor="hand2", anchor="w")
        label.pack(fill="x", padx=10, pady=(0, 2))
        label.bind("<Button-1>", lambda e, sid=step_id: page.open_step_link(sid))

    # ── 四块文本 ──
    precheck = rendered("precheck_text")
    if precheck.strip():
        _section(card, "前置检查", precheck, palette, fg=palette.warn)
    description = rendered("description_text")
    if description.strip():
        _section(card, "说明", description, palette)
    if str(command_text).strip():
        CommandBlock(card, rendered("command_text"), lang=field("command_lang", "shell"),
                     danger=dangers, palette=palette,
                     on_copy=page.copy_to_clipboard).pack(fill="x", padx=10, pady=(4, 2))
    expected = rendered("expected_text")
    if expected.strip():
        _section(card, "预期结果", expected, palette, fg=palette.success)

    # 备注区：顺带显示存量的「必填项 / 选填项」（实测填充率 11% / 5%，
    # 不单独占位，但数据不丢）
    extras = []
    for key, name in (("note", "备注"), ("required_text", "必填项"), ("optional_text", "选填项")):
        value = str(field(key, "") or "").strip()
        if value:
            extras.append(f"{name}：{value}")
    if extras:
        _section(card, "备注", "\n".join(extras), palette, fg=palette.text_muted)

    # ── 截图 ──
    shot_row = tk.Frame(card, bg=palette.surface)
    shot_row.pack(fill="x", padx=10, pady=(4, 10))
    tk.Label(shot_row, text="截图", bg=palette.surface, fg=palette.text_secondary,
             font=TYPOGRAPHY.caption, width=6, anchor="w").pack(side="left", anchor="n")
    ScreenshotStrip(shot_row, field("screenshot_path", ""), page=page,
                    on_open=lambda i, sid=step_id: page.view_step_image(sid, i),
                    thumb_refs=thumb_refs, palette=palette).pack(side="left", anchor="n")

    # 上下移（放在卡片右下角，不挤头部）
    move_row = tk.Frame(card, bg=palette.surface)
    move_row.pack(fill="x", padx=10, pady=(0, 8))
    ttk.Button(move_row, text="上移", width=5,
               command=lambda: page.move_step(step_id, -1)).pack(side="right")
    ttk.Button(move_row, text="下移", width=5,
               command=lambda: page.move_step(step_id, 1)).pack(side="right", padx=4)

    return card
