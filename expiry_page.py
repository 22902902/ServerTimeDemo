# -*- coding: utf-8 -*-
"""到期管理页面类。"""

from tkinter import ttk

from page_components import add_toolbar_buttons, create_content_frame, create_page_toolbar, create_status_bar
from ui_theme import MAIN_PALETTE


COLOR_BADGE_BG = MAIN_PALETTE.badge_bg


class ExpiryPage:
    def __init__(self, app, container, *, tree_columns, column_meta):
        self.app = app
        self.container = container
        self.tree_columns = tree_columns
        self.column_meta = column_meta

    def build(self):
        self.app.expiry_page = ttk.Frame(self.container)

        top = create_page_toolbar(self.app.expiry_page)
        add_toolbar_buttons(
            top,
            [
                ("导入 Excel", self.app.import_excel),
                ("新增记录", self.app.add_asset),
                ("编辑记录", self.app.edit_asset),
                ("删除记录", self.app.delete_asset),
                ("账户管理", self.app.open_selected_account_manager),
                ("账号中心", self.app.open_account_ledger),
                ("设置", self.app.open_settings),
                ("到期概览", self.app.show_reminder_popup),
                ("刷新列表", self.app.refresh_table),
            ],
        )

        ttk.Entry(top, textvariable=self.app.search_var, width=32).pack(side="right", padx=4)
        ttk.Button(top, text="搜索", command=self.app.refresh_table).pack(side="right", padx=4)
        ttk.Label(top, text="关键词").pack(side="right")

        table_frame = create_content_frame(self.app.expiry_page, padding=(10, 0, 10, 0))

        self.app.tree = ttk.Treeview(table_frame, columns=self.tree_columns, show="headings", height=22)
        for column in self.tree_columns:
            self.app.tree.heading(column, text=self.column_meta[column]["title"])
            self.app.tree.column(column, width=self.column_meta[column]["width"], anchor="center")
        self.app.tree.bind("<ButtonRelease-1>", self.app.on_tree_click)

        self.app.tree.tag_configure("overdue", background="#ffe6e6")
        self.app.tree.tag_configure("due_15", background="#fff2cc")
        self.app.tree.tag_configure("due_30", background=COLOR_BADGE_BG)

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.app.tree.yview)
        x_scroll = ttk.Scrollbar(self.app.expiry_page, orient="horizontal", command=self.app.tree.xview)
        self.app.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.app.tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(fill="x", padx=10)
        self.app.apply_visible_columns()

        create_status_bar(self.app.expiry_page, self.app.status_var, padding=10)
