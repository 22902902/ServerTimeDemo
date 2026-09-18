# -*- coding: utf-8 -*-
"""到期管理页面类。"""

from tkinter import ttk

from page_components import add_toolbar_buttons, create_content_frame, create_page_toolbar, create_status_bar
from ui_theme import MAIN_PALETTE


COLOR_BADGE_BG = MAIN_PALETTE.badge_bg

# 列对齐：文本左对齐，定长的编号/日期/操作居中，纯数字右对齐。
# 整表居中会让长文本（资源详情、链接）参差不齐，是表格可读性的大忌。
COLUMN_ALIGN = {
    "id": "center",
    "record_no": "center",
    "expiry_date": "center",
    "days_left": "e",
    "detail_action": "center",
    "accounts_action": "center",
}


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
                ("新增记录", self.app.add_asset, "Primary.TButton"),
                ("编辑记录", self.app.edit_asset),
                ("删除记录", self.app.delete_asset),
                ("账户管理", self.app.open_selected_account_manager),
                ("账号中心", self.app.open_account_ledger),
                ("设置", self.app.open_settings),
                ("到期概览", self.app.show_reminder_popup),
                ("刷新列表", self.app.refresh_table),
            ],
        )

        # 工具栏按钮已占满一行，再放「关键词」标签只会被压成 0 宽（实测不可见），
        # 而「搜索」按钮本身已表明输入框用途，故省略标签。
        # 注意 pack(side="right") 为逆序堆积：先写的靠最右，所以先写按钮、再写输入框。
        ttk.Button(top, text="搜索", command=self.app.refresh_table).pack(side="right", padx=4)
        ttk.Entry(top, textvariable=self.app.search_var, width=28).pack(side="right", padx=4)

        table_frame = create_content_frame(self.app.expiry_page, padding=(24, 0, 24, 0))

        self.app.tree = ttk.Treeview(table_frame, columns=self.tree_columns, show="headings", height=22)
        for column in self.tree_columns:
            self.app.tree.heading(column, text=self.column_meta[column]["title"], anchor="w")
            self.app.tree.column(
                column,
                width=self.column_meta[column]["width"],
                anchor=COLUMN_ALIGN.get(column, "w"),
            )
        self.app.tree.bind("<ButtonRelease-1>", self.app.on_tree_click)

        # 状态底色一律降饱和：保留「一眼看出紧急」的功能，去掉刺眼的粉/黄块
        self.app.tree.tag_configure("overdue", background="#fbeeec")
        self.app.tree.tag_configure("due_15", background="#fdf6e3")
        self.app.tree.tag_configure("due_30", background="#f6f6f6")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.app.tree.yview)
        x_scroll = ttk.Scrollbar(self.app.expiry_page, orient="horizontal", command=self.app.tree.xview)
        self.app.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.app.tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(fill="x", padx=24)
        self.app.apply_visible_columns()

        create_status_bar(self.app.expiry_page, self.app.status_var, padding=(24, 12))
