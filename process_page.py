# -*- coding: utf-8 -*-
"""流程中心页面类。"""

from tkinter import scrolledtext, ttk

from page_components import (
    add_toolbar_buttons,
    create_content_frame,
    create_page_toolbar,
    create_preview_sidebar,
    create_status_bar,
    create_summary_card,
    create_two_pane_layout,
)
from ui_components import create_ttk_section_header
from ui_theme import TYPOGRAPHY


class ProcessPage:
    def __init__(self, app, container, *, process_flow_templates, image_preview_cls):
        self.app = app
        self.container = container
        self.process_flow_templates = process_flow_templates
        self.image_preview_cls = image_preview_cls

    def build(self):
        self.app.process_page = ttk.Frame(self.container)
        process_top = create_page_toolbar(self.app.process_page)
        add_toolbar_buttons(
            process_top,
            [
                ("新增流程", self.app.add_process_flow),
                ("创建模板", self.app.create_process_template),
                ("编辑流程", self.app.edit_process_flow),
                ("删除流程", self.app.delete_process_flow),
                ("复制流程", self.app.copy_process_flow),
                ("打开流程链接", self.app.open_process_flow_link),
                ("刷新列表", self.app.refresh_process_flows),
            ],
        )
        ttk.Combobox(
            process_top,
            textvariable=self.app.process_template_var,
            values=[item["label"] for item in self.process_flow_templates],
            state="readonly",
            width=18,
        ).pack(side="left", padx=4)
        ttk.Entry(process_top, textvariable=self.app.process_search_var, width=32).pack(side="right", padx=4)
        ttk.Button(process_top, text="搜索", command=self.app.refresh_process_flows).pack(side="right", padx=4)
        ttk.Label(process_top, text="关键词").pack(side="right")

        _, process_left, process_right = create_two_pane_layout(
            self.app.process_page,
            left_width=360,
            right_pad=(10, 0),
            padding=(10, 0, 10, 10),
        )
        create_ttk_section_header(process_left, "流程列表").pack(anchor="w", pady=(0, 6))
        self.app.process_flow_tree = ttk.Treeview(
            process_left,
            columns=("title", "category", "platform", "updated_at"),
            show="headings",
            height=24,
            selectmode="browse",
        )
        process_flow_meta = {
            "title": ("流程名称", 150),
            "category": ("分类", 90),
            "platform": ("平台", 90),
            "updated_at": ("更新时间", 130),
        }
        for column, meta in process_flow_meta.items():
            self.app.process_flow_tree.heading(column, text=meta[0])
            self.app.process_flow_tree.column(column, width=meta[1], anchor="center")
        self.app.process_flow_tree.pack(side="left", fill="both", expand=True)
        self.app.process_flow_tree.bind("<<TreeviewSelect>>", lambda event: self.app.refresh_process_steps())
        self.app.process_flow_tree.bind("<Double-1>", lambda event: self.app.edit_process_flow())
        process_flow_scroll = ttk.Scrollbar(process_left, orient="vertical", command=self.app.process_flow_tree.yview)
        self.app.process_flow_tree.configure(yscrollcommand=process_flow_scroll.set)
        process_flow_scroll.pack(side="right", fill="y")
        self.app.process_flow_row_meta = {}

        create_summary_card(process_right, "流程概览", self.app.process_flow_summary_var, wraplength=860, padding=(10, 10))

        step_toolbar = ttk.Frame(process_right, padding=(0, 10, 0, 6))
        step_toolbar.pack(fill="x")
        add_toolbar_buttons(
            step_toolbar,
            [
                ("新增步骤", self.app.add_process_step),
                ("编辑步骤", self.app.edit_process_step),
                ("删除步骤", self.app.delete_process_step),
                ("打开步骤链接", self.app.open_process_step_link),
                ("查看截图", self.app.open_process_step_image),
                ("打开截图文件夹", self.app.open_process_step_image_folder),
            ],
        )

        self.app.process_step_tree = ttk.Treeview(
            process_right,
            columns=("step_no", "title", "link_url"),
            show="headings",
            height=10,
            selectmode="browse",
        )
        process_step_meta = {
            "step_no": ("步骤", 70),
            "title": ("步骤标题", 260),
            "link_url": ("步骤链接", 360),
        }
        for column, meta in process_step_meta.items():
            self.app.process_step_tree.heading(column, text=meta[0])
            self.app.process_step_tree.column(column, width=meta[1], anchor="center")
        self.app.process_step_tree.pack(fill="x")
        self.app.process_step_tree.bind("<<TreeviewSelect>>", lambda event: self.app.refresh_process_step_detail())
        self.app.process_step_tree.bind("<Double-1>", lambda event: self.app.edit_process_step())
        self.app.process_step_row_meta = {}

        process_detail_frame = create_content_frame(process_right, padding=(0, 10, 0, 0))
        process_text_frame = ttk.Frame(process_detail_frame)
        process_text_frame.pack(side="left", fill="both", expand=True)
        process_preview_frame = create_preview_sidebar(process_detail_frame, "步骤截图", width=300, padding=(10, 10))

        ttk.Label(process_text_frame, textvariable=self.app.process_step_title_var, style="SectionTitle.TLabel").pack(anchor="w")
        self.app.process_step_detail_text = scrolledtext.ScrolledText(
            process_text_frame,
            wrap="word",
            height=16,
            font=TYPOGRAPHY.body,
        )
        self.app.process_step_detail_text.pack(fill="both", expand=True, pady=(6, 0))
        self.app.process_step_detail_text.configure(state="disabled")
        self.app.process_step_preview = self.image_preview_cls(
            self.app,
            preview_size=(260, 170),
            empty_text="选中步骤后，这里显示该步骤的截图小图。",
        )
        self.app.process_step_preview.build(process_preview_frame, title="步骤截图").pack(fill="x", pady=(0, 6))
        ttk.Button(process_preview_frame, text="查看大图", command=self.app.open_process_step_image).pack(fill="x")

        create_status_bar(self.app.process_page, self.app.process_status_var, padding=(10, 0, 10, 10))
