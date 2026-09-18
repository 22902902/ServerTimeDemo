# -*- coding: utf-8 -*-
"""到期管理相关弹窗。"""

from datetime import datetime
import sqlite3
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from dialog_form_style import apply_dialog_form_style, create_form_checkbutton, create_form_entry, create_form_frame, create_form_label, create_form_radiobutton
from ui_theme import MAIN_PALETTE


class AssetDialog(simpledialog.Dialog):
    """资产/服务记录编辑对话框（新增或编辑）。"""

    def __init__(self, parent, title: str, initial: dict | None = None, *, app_title: str):
        self.initial = initial or {}
        self.result = None
        self.app_title = app_title
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        self.entries = {}
        fields = [
            ("record_no", "编号"),
            ("platform", "平台"),
            ("account_no", "账号编号"),
            ("account_subject_code", "账号主体编号"),
            ("account_subject_name", "账号主体名称"),
            ("resource_type", "资源类型"),
            ("resource_detail", "资源详情"),
            ("resource_subject_code", "资源主体编号"),
            ("resource_subject_name", "资源主体名称"),
            ("expiry_date", "到期日期(YYYY-MM-DD)"),
            ("note", "备注"),
        ]

        for row_index, (field, label) in enumerate(fields):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(row=row_index, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=45)
            entry.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, self.initial.get(field, ""))
            self.entries[field] = entry

        master.columnconfigure(1, weight=1)
        return self.entries["platform"]

    def validate(self):
        resource_type = self.entries["resource_type"].get().strip()
        if not resource_type:
            messagebox.showwarning(self.app_title, "资源类型不能为空。", parent=self)
            return False

        expiry_text = self.entries["expiry_date"].get().strip()
        if expiry_text:
            try:
                datetime.strptime(expiry_text, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning(self.app_title, "到期日期格式必须为 YYYY-MM-DD。", parent=self)
                return False
        return True

    def apply(self):
        payload = {field: widget.get().strip() for field, widget in self.entries.items()}
        payload["expiry_raw"] = payload["expiry_date"]
        self.result = payload


class SettingsDialog(simpledialog.Dialog):
    """应用设置对话框。"""

    def __init__(
        self,
        parent,
        visible_columns: list[str],
        close_behavior: str,
        *,
        app_title: str,
        displayable_columns,
        column_meta,
    ):
        self.visible_columns = visible_columns
        self.close_behavior = close_behavior
        self.result = None
        self.app_title = app_title
        self.displayable_columns = list(displayable_columns)
        self.column_meta = column_meta
        super().__init__(parent, "面板设置")

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        create_form_label(master, "勾选后显示在主面板，不勾选则只在详情中显示。", palette=MAIN_PALETTE).pack(anchor="w", padx=8, pady=(8, 4))
        self.vars = {}
        box = create_form_frame(master, palette=MAIN_PALETTE)
        box.pack(fill="both", expand=True)
        for index, column in enumerate(self.displayable_columns):
            var = tk.BooleanVar(value=column in self.visible_columns)
            self.vars[column] = var
            chk = create_form_checkbutton(box, text=self.column_meta[column]["title"], variable=var, palette=MAIN_PALETTE)
            chk.grid(row=index // 2, column=index % 2, sticky="w", padx=6, pady=4)

        close_box = ttk.LabelFrame(master, text="关闭行为", padding=8, style="MainDialog.TLabelframe")
        close_box.pack(fill="x", padx=8, pady=(0, 8))
        self.close_behavior_var = tk.StringVar(value=self.close_behavior)
        options = [
            ("ask", "每次询问"),
            ("minimize", "总是最小化到托盘"),
            ("exit", "总是退出程序"),
        ]
        for index, (value, label) in enumerate(options):
            create_form_radiobutton(close_box, text=label, value=value, variable=self.close_behavior_var, palette=MAIN_PALETTE).grid(
                row=0, column=index, sticky="w", padx=8, pady=4
            )
        return box

    def validate(self):
        selected = [column for column in self.displayable_columns if self.vars[column].get()]
        if not selected:
            messagebox.showwarning(self.app_title, "主面板至少保留一个字段。", parent=self)
            return False
        return True

    def apply(self):
        self.result = {
            "visible_columns": [column for column in self.displayable_columns if self.vars[column].get()],
            "close_behavior": self.close_behavior_var.get(),
        }


class DetailDialog(simpledialog.Dialog):
    """资产/服务记录详情弹窗（只读查看模式）。"""

    def __init__(
        self,
        parent,
        asset_row: sqlite3.Row,
        accounts: list[sqlite3.Row],
        *,
        detail_fields,
        format_account_identity,
    ):
        self.asset_row = asset_row
        self.accounts = accounts
        self.detail_fields = detail_fields
        self.format_account_identity = format_account_identity
        super().__init__(parent, "详情")

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        text = scrolledtext.ScrolledText(master, width=90, height=28, wrap="word")
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.configure(
            bg=MAIN_PALETTE.input_bg,
            fg=MAIN_PALETTE.text_primary,
            insertbackground=MAIN_PALETTE.text_primary,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=MAIN_PALETTE.input_border,
            highlightcolor=MAIN_PALETTE.input_focus,
        )
        lines = []
        for field, label in self.detail_fields:
            lines.append(f"{label}：{self.asset_row[field] or ''}")

        lines.append("")
        lines.append("账户信息：")
        if not self.accounts:
            lines.append("无")
        else:
            for index, account in enumerate(self.accounts, start=1):
                lines.append(f"{index}. 主体编号：{account['subject_code'] or ''}")
                lines.append(f"   主体名称：{account['subject_name'] or ''}")
                lines.append(
                    f"   账号信息：{self.format_account_identity(account['account_no'] or '', account['account_name'] or '')}"
                )
                lines.append(f"   密码：{account['password'] or ''}")
                lines.append(f"   平台：{account['platform'] or ''}")
                lines.append(f"   备注：{account['note'] or ''}")

        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        return text
