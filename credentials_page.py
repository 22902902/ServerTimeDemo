# -*- coding: utf-8 -*-
"""账号中心页面类。

布局要点（踩过的坑，别改回去）：
1. 工具栏原来 17 个按钮平铺一行，需求 1872px / 可用 1148px，末尾 5 个按钮和
   整个搜索框被 Tk **直接不映射** —— 代码写了，界面上根本不存在。
   现在主操作留一行，复制类与打开/导入类各收进一个下拉菜单。
2. 搜索框先 pack（side="right"）：万一将来动作又多起来，被挤掉的也是按钮，
   而不是搜索框。
3. 表格与右侧预览栏用 create_table_preview_split 一次建好 —— 它保证先 pack
   右侧固定宽度的预览栏，否则会被左侧 Treeview 卡片（请求宽度 1674px）挤成 0 宽。
4. Treeview 的滚动条必须比表格先 pack，理由同上。
"""

import tkinter as tk
from tkinter import ttk

from page_components import (
    GUTTER,
    add_toolbar_buttons,
    create_menu_button,
    create_page_toolbar,
    create_status_bar,
    create_summary_card,
    create_table_preview_split,
    pack_tree_with_scrollbars,
)


class CredentialsPage:
    def __init__(self, app, container, image_preview_cls):
        self.app = app
        self.container = container
        self.image_preview_cls = image_preview_cls

    def build(self):
        app = self.app
        app.credentials_page = ttk.Frame(self.container)

        self._build_toolbar(app)
        self._build_filter_bar(app)

        app.credentials_summary_var = tk.StringVar(value="")
        create_summary_card(
            app.credentials_page, "账号中心概览", app.credentials_summary_var, wraplength=920
        )

        # 状态栏用 side="bottom"，放在内容区之前调用也更贴合「固定条先占位」的直觉
        app.credentials_status_var = tk.StringVar(value="账号中心已就绪。")
        create_status_bar(app.credentials_page, app.credentials_status_var)

        table_card, preview_card = create_table_preview_split(
            app.credentials_page,
            table_title="账号列表",
            preview_title="注册信息预览",
            # 320 而非 300：要给「选中账号后…」这类 19 字提示留出整行，
            # 300 时文本宽约 253px、可用仅 266px，第 20 个字必被折到下一行
            preview_width=320,
        )
        self._build_tree(app, table_card)
        self._build_preview(app, preview_card)

    # ------------------------------------------------------------------
    # 工具栏
    # ------------------------------------------------------------------
    def _build_toolbar(self, app):
        toolbar = create_page_toolbar(app.credentials_page)
        add_toolbar_buttons(
            toolbar,
            [
                ("新增账号", app.add_credential_item, "Primary.TButton"),
                ("编辑选中", app.edit_credential_item),
                ("删除选中", app.delete_credential_item),
            ],
        )
        create_menu_button(
            toolbar,
            "复制",
            [
                ("复制整行", app.copy_credential_row),
                ("复制模板", app.copy_credential_template),
                ("复制账号", lambda: app.copy_credential_field("username", "账号")),
                ("复制密码", lambda: app.copy_credential_field("password", "密码")),
                ("复制邮箱", lambda: app.copy_credential_field("email", "邮箱")),
                ("复制手机号", lambda: app.copy_credential_field("phone", "手机号")),
            ],
        )
        create_menu_button(
            toolbar,
            "更多",
            [
                ("导出选中", app.export_selected_credentials_excel),
                ("导入 Excel", app.import_credentials_excel),
                ("导出 Excel", app.export_credentials_excel),
                "---",
                ("打开共享管理", app.open_selected_shared_manager),
                "---",
                ("查看截图", app.open_selected_credential_image),
                ("打开截图文件夹", app.open_selected_credential_image_folder),
                ("打开链接", app.open_credential_link),
            ],
        )

        # 先放右侧的搜索：它比次级按钮重要，宁可挤按钮也不挤它
        ttk.Button(toolbar, text="搜索", command=app.refresh_credentials_table).pack(
            side="right", padx=(6, 0)
        )
        ttk.Entry(toolbar, textvariable=app.credential_search_var, width=26).pack(
            side="right", padx=4
        )

    # ------------------------------------------------------------------
    # 筛选栏
    # ------------------------------------------------------------------
    def _build_filter_bar(self, app):
        filter_bar = ttk.Frame(app.credentials_page, padding=(GUTTER, 0, GUTTER, 12))
        filter_bar.pack(fill="x")

        ttk.Label(filter_bar, text="来源").pack(side="left")
        ttk.Combobox(
            filter_bar,
            textvariable=app.credential_source_var,
            values=["全部来源", "账号密码库", "共享账户台账"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=4)
        ttk.Label(filter_bar, text="分组").pack(side="left", padx=(12, 0))
        ttk.Combobox(
            filter_bar,
            textvariable=app.credential_group_var,
            values=["不分组", "按平台分组", "按用途分组", "按来源分组"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=4)
        ttk.Button(filter_bar, text="应用筛选", style="Primary.TButton",
                   command=app.refresh_credentials_table).pack(side="left", padx=(12, 0))
        # 刷新原来在工具栏里，是被挤没的那批之一；挪到筛选栏右侧，位置更合理
        ttk.Button(filter_bar, text="刷新列表",
                   command=app.refresh_credentials_table).pack(side="right")

    # ------------------------------------------------------------------
    # 表格
    # ------------------------------------------------------------------
    def _build_tree(self, app, table_card):
        columns = (
            "source_label", "group_label", "title", "category", "platform",
            "link_url", "username", "password", "email", "phone", "note",
        )
        meta = {
            "source_label": ("来源", 96),
            "group_label": ("分组", 110),
            "title": ("标题", 170),
            "category": ("分类/用途", 110),
            "platform": ("平台", 92),
            "link_url": ("链接", 200),
            "username": ("账号", 130),
            "password": ("密码", 120),
            "email": ("邮箱", 150),
            "phone": ("手机号", 110),
            "note": ("备注", 180),
        }
        center_cols = {"source_label", "group_label"}
        app.credentials_tree = ttk.Treeview(
            table_card, columns=columns, show="headings", height=20, selectmode="extended"
        )
        for column in columns:
            app.credentials_tree.heading(column, text=meta[column][0], anchor="w")
            app.credentials_tree.column(
                column,
                width=meta[column][1],
                minwidth=56,
                anchor="center" if column in center_cols else "w",
            )
        pack_tree_with_scrollbars(table_card, app.credentials_tree)
        app.credentials_tree.bind("<Double-1>", lambda event: app.edit_credential_item())
        app.credentials_tree.bind(
            "<<TreeviewSelect>>", lambda event: app.refresh_credential_preview()
        )
        app.credential_row_meta = {}

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    def _build_preview(self, app, preview_card):
        app.credential_preview = self.image_preview_cls(
            app,
            preview_size=(260, 170),
            empty_text="选中账号后，这里显示注册/密保截图小图。",
        )
        # 卡片已自带「截图预览」标题，这里不再传 title，否则标题会出现两遍
        app.credential_preview.build(preview_card).pack(fill="x")
        ttk.Button(
            preview_card, text="查看大图", command=app.open_selected_credential_image
        ).pack(fill="x", pady=(8, 0))
