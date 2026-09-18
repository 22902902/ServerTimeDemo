# -*- coding: utf-8 -*-
"""账号中心页面类。"""

import tkinter as tk
from tkinter import ttk

from page_components import (
    add_toolbar_buttons,
    create_content_frame,
    create_page_toolbar,
    create_preview_sidebar,
    create_status_bar,
    create_summary_card,
)
from ui_components import create_ttk_card


class CredentialsPage:
    def __init__(self, app, container, image_preview_cls):
        self.app = app
        self.container = container
        self.image_preview_cls = image_preview_cls

    def build(self):
        self.app.credentials_page = ttk.Frame(self.container)
        credentials_top = create_page_toolbar(self.app.credentials_page)
        add_toolbar_buttons(
            credentials_top,
            [
                ("新增账号", self.app.add_credential_item),
                ("编辑选中", self.app.edit_credential_item),
                ("删除选中", self.app.delete_credential_item),
                ("复制整行", self.app.copy_credential_row),
                ("复制模板", self.app.copy_credential_template),
                ("导出选中", self.app.export_selected_credentials_excel),
                ("打开共享管理", self.app.open_selected_shared_manager),
                ("导入 Excel", self.app.import_credentials_excel),
                ("导出 Excel", self.app.export_credentials_excel),
                ("复制账号", lambda: self.app.copy_credential_field("username", "账号")),
                ("复制密码", lambda: self.app.copy_credential_field("password", "密码")),
                ("复制邮箱", lambda: self.app.copy_credential_field("email", "邮箱")),
                ("复制手机号", lambda: self.app.copy_credential_field("phone", "手机号")),
                ("查看截图", self.app.open_selected_credential_image),
                ("打开截图文件夹", self.app.open_selected_credential_image_folder),
                ("打开链接", self.app.open_credential_link),
                ("刷新列表", self.app.refresh_credentials_table),
            ],
        )

        filter_bar = ttk.Frame(self.app.credentials_page, padding=(10, 0, 10, 8))
        filter_bar.pack(fill="x")
        ttk.Label(filter_bar, text="来源").pack(side="left")
        ttk.Combobox(
            filter_bar,
            textvariable=self.app.credential_source_var,
            values=["全部来源", "账号密码库", "共享账户台账"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=4)
        ttk.Label(filter_bar, text="分组").pack(side="left", padx=(12, 0))
        ttk.Combobox(
            filter_bar,
            textvariable=self.app.credential_group_var,
            values=["不分组", "按平台分组", "按用途分组", "按来源分组"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=4)
        ttk.Entry(credentials_top, textvariable=self.app.credential_search_var, width=32).pack(side="right", padx=4)
        ttk.Button(credentials_top, text="搜索", command=self.app.refresh_credentials_table).pack(side="right", padx=4)
        ttk.Label(credentials_top, text="关键词").pack(side="right")
        ttk.Button(filter_bar, text="应用筛选", command=self.app.refresh_credentials_table).pack(side="left", padx=(8, 0))

        self.app.credentials_summary_var = tk.StringVar(value="")
        create_summary_card(self.app.credentials_page, "账号中心概览", self.app.credentials_summary_var, wraplength=920)

        credentials_frame = create_content_frame(self.app.credentials_page, padding=(10, 0, 10, 0))
        credentials_table_frame = create_ttk_card(credentials_frame, "账号列表", padding=(10, 10))
        credentials_table_frame.pack(side="left", fill="both", expand=True)
        credentials_preview_frame = create_preview_sidebar(credentials_frame, "注册信息预览", width=300, padding=(10, 10))

        credential_columns = (
            "source_label",
            "group_label",
            "title",
            "category",
            "platform",
            "link_url",
            "username",
            "password",
            "email",
            "phone",
            "note",
        )
        self.app.credentials_tree = ttk.Treeview(
            credentials_table_frame, columns=credential_columns, show="headings", height=20, selectmode="extended"
        )
        credential_meta = {
            "source_label": ("来源", 110),
            "group_label": ("分组", 140),
            "title": ("标题", 180),
            "category": ("分类/用途", 120),
            "platform": ("平台", 100),
            "link_url": ("链接", 220),
            "username": ("账号", 140),
            "password": ("密码", 140),
            "email": ("邮箱", 180),
            "phone": ("手机号", 120),
            "note": ("备注", 220),
        }
        for column in credential_columns:
            self.app.credentials_tree.heading(column, text=credential_meta[column][0])
            self.app.credentials_tree.column(column, width=credential_meta[column][1], anchor="center")
        self.app.credentials_tree.pack(side="left", fill="both", expand=True)
        self.app.credentials_tree.bind("<Double-1>", lambda event: self.app.edit_credential_item())
        self.app.credentials_tree.bind("<<TreeviewSelect>>", lambda event: self.app.refresh_credential_preview())
        self.app.credential_row_meta = {}
        credentials_y_scroll = ttk.Scrollbar(credentials_table_frame, orient="vertical", command=self.app.credentials_tree.yview)
        credentials_x_scroll = ttk.Scrollbar(self.app.credentials_page, orient="horizontal", command=self.app.credentials_tree.xview)
        self.app.credentials_tree.configure(yscrollcommand=credentials_y_scroll.set, xscrollcommand=credentials_x_scroll.set)
        credentials_y_scroll.pack(side="right", fill="y")
        credentials_x_scroll.pack(fill="x", padx=10)

        self.app.credential_preview = self.image_preview_cls(
            self.app,
            preview_size=(260, 170),
            empty_text="选中账号后，这里显示注册/密保截图小图。",
        )
        self.app.credential_preview.build(credentials_preview_frame, title="截图预览").pack(fill="x", pady=(0, 6))
        ttk.Button(credentials_preview_frame, text="查看大图", command=self.app.open_selected_credential_image).pack(fill="x")

        self.app.credentials_status_var = tk.StringVar(value="账号中心已就绪。")
        create_status_bar(self.app.credentials_page, self.app.credentials_status_var)
