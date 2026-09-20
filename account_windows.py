# -*- coding: utf-8 -*-
"""共享账户管理相关窗口。"""

import re
import sqlite3
import webbrowser
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from dialog_form_style import apply_dialog_form_style
from page_components import (
    GUTTER,
    add_toolbar_buttons,
    create_menu_button,
    create_table_preview_split,
    pack_tree_with_scrollbars,
)
from ui_theme import MAIN_PALETTE, TYPOGRAPHY


def center_dialog_over_parent(dialog, parent) -> None:
    """把弹窗摆到父窗口中间偏上，而不是永远贴在屏幕/父窗口左上角。"""
    try:
        parent.update_idletasks()
        size = dialog.geometry().split("+")[0]
        width, height = (int(value) for value in size.split("x"))
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 3)
        dialog.geometry(f"+{x}+{y}")
    except Exception:
        pass


class AccountManagerDialog(tk.Toplevel):
    """共享账户管理窗口。"""

    def __init__(
        self,
        parent,
        group_key: str,
        *,
        context: dict | None = None,
        app_title: str,
        normalize_text,
        format_account_identity,
        get_account_image_display_text,
        account_edit_dialog_cls,
        account_image_preview_cls,
    ):
        super().__init__(parent)
        self.parent = parent
        self.db = parent.db
        self.normalize_text = normalize_text
        self.format_account_identity = format_account_identity
        self.get_account_image_display_text = get_account_image_display_text
        self.account_edit_dialog_cls = account_edit_dialog_cls
        self.account_image_preview_cls = account_image_preview_cls
        self.app_title = app_title
        self.group_key = normalize_text(group_key)
        self.context = context or {}
        self.title("账户管理")
        self.geometry("1220x580")
        self.minsize(940, 460)
        self.transient(parent)
        self.grab_set()
        self.build_ui()
        self.refresh_accounts()
        center_dialog_over_parent(self, parent)

    def build_ui(self):
        apply_dialog_form_style(self, MAIN_PALETTE, style_prefix="AccountDialog")
        self.bind("<Escape>", lambda event: self.destroy())

        header = ttk.Frame(self, padding=(GUTTER, 18, GUTTER, 8))
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"账号编号：{self.group_key or '未设置'}",
            font=TYPOGRAPHY.subtitle,
            style="AccountDialog.TLabel",
        ).pack(anchor="w")
        used_count = self.db.count_assets_by_account_no(self.group_key)
        ttk.Label(
            header,
            text=f"当前有 {used_count} 条资源共用这个账户编号，修改后会同步反映到这些记录。",
            style="AccountDialogMuted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # 13 个按钮平铺一行时需求 1563px、可用 960px，末尾 5 个按钮被 Tk 直接
        # 不映射。这里把复制类与打开类各收进一个下拉。
        toolbar = ttk.Frame(self, padding=(GUTTER, 0, GUTTER, 10))
        toolbar.pack(fill="x")
        add_toolbar_buttons(
            toolbar,
            [
                ("新增账户", self.add_account, "Primary.TButton"),
                ("编辑账户", self.edit_account),
                ("删除选中", self.delete_account),
            ],
        )
        create_menu_button(
            toolbar,
            "复制",
            [
                ("复制整行", self.copy_account_row),
                ("复制模板", self.copy_account_template),
                ("复制账号", self.copy_account_name),
                ("复制密码", self.copy_password),
                ("复制邮箱", self.copy_email),
                ("复制手机号", self.copy_phone),
            ],
        )
        create_menu_button(
            toolbar,
            "更多",
            [
                ("打开链接", self.open_link),
                "---",
                ("查看截图", self.open_selected_account_screenshot),
                ("打开截图文件夹", self.open_selected_account_image_folder),
            ],
        )
        ttk.Button(toolbar, text="关闭", command=self.destroy).pack(side="right", padx=(6, 0))

        table_card, preview_card = create_table_preview_split(
            self,
            table_title="账户列表",
            preview_title="截图预览",
            preview_width=300,
            padding=(GUTTER, 0, GUTTER, GUTTER),
        )

        columns = ("id", "subject_name", "account_identity", "password",
                   "email", "phone", "platform", "note")
        meta = {
            "id": ("ID", 44),
            "subject_name": ("主体名称", 126),
            "account_identity": ("账号信息", 148),
            "password": ("密码(明文)", 92),
            "email": ("邮箱", 126),
            "phone": ("手机号", 92),
            "platform": ("平台", 74),
            "note": ("备注", 108),
        }
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings",
                                 height=14, selectmode="extended")
        for column in columns:
            self.tree.heading(column, text=meta[column][0], anchor="w")
            self.tree.column(
                column,
                width=meta[column][1],
                minwidth=44,
                anchor="center" if column == "id" else "w",
            )
        pack_tree_with_scrollbars(table_card, self.tree)
        self.tree.bind("<Double-1>", lambda event: self.edit_account())
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.refresh_account_preview())

        self.account_preview = self.account_image_preview_cls(
            self,
            preview_size=(240, 160),
            empty_text="选中账户后，这里显示注册/密保截图小图。",
        )
        self.account_preview.build(preview_card, title="截图预览").pack(fill="x")
        ttk.Button(preview_card, text="查看大图",
                   command=self.open_selected_account_screenshot).pack(fill="x", pady=(8, 0))

    def refresh_accounts(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self.db.fetch_shared_accounts(self.group_key):
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["subject_name"] or "",
                    self.format_account_identity(
                        row["account_no"] or "", row["account_name"] or ""
                    ),
                    row["password"] or "",
                    row["email"] or "",
                    row["phone"] or "",
                    row["platform"] or "",
                    row["note"] or "",
                ),
            )
        self.refresh_account_preview()

    def get_selected_account_id(self, silent: bool = False) -> int | None:
        selection = self.tree.selection()
        if not selection:
            if not silent:
                messagebox.showinfo(self.app_title, "请先选择一个账户。", parent=self)
            return None
        return int(self.tree.item(selection[0], "values")[0])

    def get_selected_account_ids(self, silent: bool = False) -> list[int]:
        selection = self.tree.selection()
        if not selection:
            if not silent:
                messagebox.showinfo(self.app_title, "请先选择一个账户。", parent=self)
            return []
        return [int(self.tree.item(item_id, "values")[0]) for item_id in selection]

    def get_selected_account_row(self, silent: bool = False) -> sqlite3.Row | None:
        account_id = self.get_selected_account_id(silent=silent)
        if account_id is None:
            return None
        return next((item for item in self.db.fetch_shared_accounts(self.group_key) if item["id"] == account_id), None)

    def get_selected_account_rows(self, silent: bool = False) -> list[sqlite3.Row]:
        account_ids = self.get_selected_account_ids(silent=silent)
        if not account_ids:
            return []
        account_id_set = set(account_ids)
        return [item for item in self.db.fetch_shared_accounts(self.group_key) if item["id"] in account_id_set]

    def refresh_account_preview(self):
        row = self.get_selected_account_row(silent=True)
        self.account_preview.set_value(row["screenshot_path"] if row else "")

    def open_selected_account_screenshot(self):
        row = self.get_selected_account_row()
        if not row:
            return
        if not self.normalize_text(row["screenshot_path"]):
            messagebox.showinfo(self.app_title, "当前账户没有截图。", parent=self)
            return
        self.account_preview.set_value(row["screenshot_path"])
        self.account_preview.open_large_viewer(parent=self, title="查看共享账户截图")

    def open_selected_account_image_folder(self):
        row = self.get_selected_account_row()
        if not row:
            return
        image_value = self.normalize_text(row["screenshot_path"])
        if not image_value:
            messagebox.showinfo(self.app_title, "当前账户没有截图。", parent=self)
            return
        try:
            self.account_preview.set_value(image_value)
            self.account_preview.open_current_image_folder(parent=self)
            self.parent.log_status("已打开共享账户截图目录。")
        except (OSError, Exception) as exc:
            messagebox.showerror(self.app_title, f"打开截图目录失败：\n{exc}", parent=self)

    def build_account_row_text(self, row: sqlite3.Row) -> str:
        lines = [
            f"账号组：{row['group_key'] or self.group_key}",
            f"主体编号：{row['subject_code'] or ''}",
            f"主体名称：{row['subject_name'] or ''}",
            f"账号信息：{self.format_account_identity(row['account_no'] or '', row['account_name'] or '')}",
            f"密码：{row['password'] or ''}",
            f"平台：{row['platform'] or ''}",
            f"链接：{row['link_url'] or ''}",
            f"邮箱：{row['email'] or ''}",
            f"手机号：{row['phone'] or ''}",
            f"截图：{self.get_account_image_display_text(row['screenshot_path'] or '')}",
            f"备注：{row['note'] or ''}",
        ]
        return "\n".join(lines)

    def copy_account_row(self):
        rows = self.get_selected_account_rows()
        if not rows:
            return
        text = "\n\n--------------------\n\n".join(self.build_account_row_text(row) for row in rows)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.parent.log_status(f"已复制 {len(rows)} 条共享账户完整信息。")
        messagebox.showinfo(self.app_title, f"已复制 {len(rows)} 条共享账户完整信息。", parent=self)

    def build_account_template_text(self, row: sqlite3.Row) -> str:
        lines = [
            f"账号组：{row['group_key'] or self.group_key}",
            f"主体名称：{row['subject_name'] or ''}",
            f"平台：{row['platform'] or ''}",
            f"链接：{row['link_url'] or ''}",
            f"账号：{row['account_name'] or ''}",
            f"账号编号：{row['account_no'] or ''}",
            f"密码：{row['password'] or ''}",
            f"邮箱：{row['email'] or ''}",
            f"手机号：{row['phone'] or ''}",
            f"截图：{self.get_account_image_display_text(row['screenshot_path'] or '')}",
            f"备注：{row['note'] or ''}",
        ]
        return "\n".join(lines)

    def copy_account_template(self):
        rows = self.get_selected_account_rows()
        if not rows:
            return
        text = "\n\n====================\n\n".join(self.build_account_template_text(row) for row in rows)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.parent.log_status(f"已复制 {len(rows)} 条共享账户模板文本。")
        messagebox.showinfo(self.app_title, f"已复制 {len(rows)} 条共享账户模板文本。", parent=self)

    def copy_text(self, value: str, label: str):
        if not value:
            messagebox.showinfo(self.app_title, f"当前账户没有{label}。", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update()
        self.parent.log_status(f"已复制{label}。")
        messagebox.showinfo(self.app_title, f"{label}已复制到剪贴板。", parent=self)

    def copy_account_name(self):
        row = self.get_selected_account_row()
        if not row:
            messagebox.showwarning(self.app_title, "账户不存在。", parent=self)
            return
        self.copy_text(row["account_name"] or "", "账号")

    def copy_password(self):
        row = self.get_selected_account_row()
        if not row:
            messagebox.showwarning(self.app_title, "账户不存在。", parent=self)
            return
        self.copy_text(row["password"] or "", "密码")

    def copy_email(self):
        row = self.get_selected_account_row()
        if not row:
            messagebox.showwarning(self.app_title, "账户不存在。", parent=self)
            return
        self.copy_text(row["email"] or "", "邮箱")

    def copy_phone(self):
        row = self.get_selected_account_row()
        if not row:
            messagebox.showwarning(self.app_title, "账户不存在。", parent=self)
            return
        self.copy_text(row["phone"] or "", "手机号")

    def open_link(self):
        row = self.get_selected_account_row()
        if not row:
            messagebox.showwarning(self.app_title, "账户不存在。", parent=self)
            return
        link_url = self.normalize_text(row["link_url"])
        if not link_url:
            messagebox.showinfo(self.app_title, "当前账户没有链接。", parent=self)
            return
        target_url = link_url if re.match(r"^https?://", link_url, re.I) else f"https://{link_url}"
        try:
            webbrowser.open(target_url)
            self.parent.log_status("已打开共享账户链接。")
        except (webbrowser.Error, OSError, Exception) as exc:
            messagebox.showerror(self.app_title, f"打开链接失败：\n{exc}", parent=self)

    def add_account(self):
        initial = {
            "subject_code": self.context.get("subject_code", ""),
            "subject_name": self.context.get("subject_name", ""),
            "account_no": self.context.get("account_no", "") or self.group_key,
            "platform": self.context.get("platform", ""),
            "link_url": self.context.get("link_url", ""),
            "email": self.context.get("email", ""),
            "phone": self.context.get("phone", ""),
            "note": self.context.get("note", ""),
        }
        dialog = self.account_edit_dialog_cls(self, "新增账户", initial=initial)
        if dialog.result:
            self.db.add_shared_account(self.group_key, dialog.result)
            self.refresh_accounts()
            self.parent.refresh_table()

    def edit_account(self):
        row = self.get_selected_account_row()
        if not row:
            messagebox.showwarning(self.app_title, "账户不存在。", parent=self)
            return
        dialog = self.account_edit_dialog_cls(self, "编辑账户", initial=dict(row))
        if dialog.result:
            self.db.update_shared_account(row["id"], self.group_key, dialog.result)
            self.refresh_accounts()
            self.parent.refresh_table()

    def delete_account(self):
        account_ids = self.get_selected_account_ids()
        if not account_ids:
            return
        if len(account_ids) == 1:
            confirm_text = "确认删除这个账户吗？"
        else:
            confirm_text = f"确认删除选中的 {len(account_ids)} 个账户吗？"
        if not messagebox.askyesno(self.app_title, confirm_text, parent=self):
            return
        image_paths, shared_count, _ = self.parent.get_deletable_account_image_paths(shared_ids=account_ids)
        delete_images = False
        if image_paths:
            choice = messagebox.askyesnocancel(
                self.app_title,
                f"检测到 {shared_count} 条共享账户关联 {len(image_paths)} 张本地截图。\n\n是否同时删除这些已不再被其他记录引用的截图文件？\n\n是：删除记录并删除本地截图\n否：只删除记录\n取消：不执行删除",
                parent=self,
            )
            if choice is None:
                return
            delete_images = choice
        for account_id in account_ids:
            self.db.delete_shared_account(account_id)
        removed_count, failed_files = self.parent.delete_local_account_image_files(image_paths) if delete_images else (0, [])
        self.refresh_accounts()
        self.parent.refresh_table()
        self.parent.refresh_credentials_table()
        if failed_files:
            messagebox.showwarning(
                self.app_title,
                "记录已删除，但以下截图文件删除失败：\n\n" + "\n".join(failed_files[:8]),
                parent=self,
            )
        self.parent.log_status(
            f"已删除 {len(account_ids)} 条共享账户记录。"
            + (f" 同时删除截图 {removed_count} 张。" if delete_images else "")
        )


class AccountLedgerDialog(tk.Toplevel):
    """共享账号台账窗口。"""

    def __init__(
        self,
        parent,
        *,
        app_title: str,
        normalize_text,
        account_manager_dialog_cls,
    ):
        super().__init__(parent)
        self.parent = parent
        self.db = parent.db
        self.app_title = app_title
        self.normalize_text = normalize_text
        self.account_manager_dialog_cls = account_manager_dialog_cls
        self.title("全局账户台账")
        self.geometry("1040x580")
        self.minsize(880, 460)
        self.transient(parent)
        self.grab_set()
        self.search_var = tk.StringVar()
        self.build_ui()
        self.refresh_groups()
        center_dialog_over_parent(self, parent)

    def build_ui(self):
        apply_dialog_form_style(self, MAIN_PALETTE, style_prefix="AccountDialog")
        self.bind("<Escape>", lambda event: self.destroy())

        header = ttk.Frame(self, padding=(GUTTER, 18, GUTTER, 8))
        header.pack(fill="x")
        ttk.Label(header, text="全局账户台账", font=TYPOGRAPHY.subtitle,
                  style="AccountDialog.TLabel").pack(anchor="w")
        ttk.Label(header, text="按账号编号汇总共享账户与关联资源。双击一行可直接打开该组的账户管理。",
                  style="AccountDialogMuted.TLabel").pack(anchor="w", pady=(4, 0))

        top = ttk.Frame(self, padding=(GUTTER, 0, GUTTER, 10))
        top.pack(fill="x")
        ttk.Button(top, text="关闭", command=self.destroy).pack(side="right", padx=(6, 0))
        # 搜索组整体靠右：pack 顺序与视觉顺序相反，先 pack 的贴最右
        search_box = ttk.Frame(top)
        search_box.pack(side="right")
        ttk.Button(search_box, text="搜索", command=self.refresh_groups).pack(side="right", padx=(6, 0))
        ttk.Entry(search_box, textvariable=self.search_var, width=26).pack(side="right", padx=4)
        ttk.Label(search_box, text="账号组").pack(side="right")
        add_toolbar_buttons(
            top,
            [
                ("新增账号组", self.add_group, "Primary.TButton"),
                ("打开管理", self.open_group_manager),
                ("刷新", self.refresh_groups),
            ],
        )

        table_card = ttk.Frame(self, padding=(GUTTER, 0, GUTTER, GUTTER))
        table_card.pack(fill="both", expand=True)
        columns = ("group_key", "account_summary", "account_count",
                   "asset_count", "platform", "subject_name", "note")
        meta = {
            "group_key": ("账号编号", 110),
            "account_summary": ("主账号信息", 200),
            "account_count": ("账户数", 72),
            "asset_count": ("关联资源", 80),
            "platform": ("平台", 100),
            "subject_name": ("主体名称", 200),
            "note": ("备注", 460),
        }
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", height=20)
        for column in columns:
            self.tree.heading(column, text=meta[column][0], anchor="w")
            numeric = column in ("account_count", "asset_count")
            self.tree.column(column, width=meta[column][1], minwidth=56,
                             anchor="e" if numeric else "w")
        pack_tree_with_scrollbars(table_card, self.tree)
        self.tree.bind("<Double-1>", lambda event: self.open_group_manager())

    def refresh_groups(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for group in self.db.fetch_account_group_summaries(self.search_var.get()):
            self.tree.insert(
                "",
                "end",
                values=(
                    group["group_key"],
                    group["account_summary"],
                    group["account_count"],
                    group["asset_count"],
                    group["platform"],
                    group["subject_name"],
                    group["note"],
                ),
            )

    def get_selected_group_key(self) -> str:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(self.app_title, "请先选择一个账号组。", parent=self)
            return ""
        return self.normalize_text(self.tree.item(selection[0], "values")[0])

    def add_group(self):
        group_key = simpledialog.askstring(self.app_title, "请输入新的账号编号，例如 ZH-0008", parent=self)
        group_key = self.normalize_text(group_key)
        if not group_key:
            return
        self.open_group_manager(group_key=group_key)

    def open_group_manager(self, group_key: str = ""):
        group_key = self.normalize_text(group_key) or self.get_selected_group_key()
        if not group_key:
            return
        context = self.db.get_account_group_context(group_key)
        manager = self.account_manager_dialog_cls(self.parent, group_key, context=context)
        self.wait_window(manager)
        self.refresh_groups()
