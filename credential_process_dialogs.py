# -*- coding: utf-8 -*-
"""账号中心与流程中心相关弹窗。"""

from tkinter import messagebox, scrolledtext, simpledialog, ttk

from dialog_form_style import apply_dialog_form_style, create_form_entry, create_form_frame, create_form_label
from ui_theme import MAIN_PALETTE


class CredentialItemDialog(simpledialog.Dialog):
    """统一凭证编辑对话框。"""

    def __init__(self, parent, title: str, initial: dict | None = None, *, app_title: str, image_preview_cls):
        self.initial = initial or {}
        self.result = None
        self.app_title = app_title
        self.image_preview_cls = image_preview_cls
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        self.entries = {}
        fields = [
            ("title", "标题"),
            ("category", "分类/用途"),
            ("platform", "平台"),
            ("link_url", "链接"),
            ("username", "账号"),
            ("password", "密码"),
            ("email", "邮箱"),
            ("phone", "手机号"),
            ("note", "备注"),
        ]
        for row_index, (field, label) in enumerate(fields):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(row=row_index, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=52)
            entry.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, self.initial.get(field, ""))
            self.entries[field] = entry
        self.screenshot_preview = self.image_preview_cls(
            self,
            image_value=self.initial.get("screenshot_path", ""),
            preview_size=(240, 150),
            empty_text="未上传注册/密保截图",
            image_subdir="credentials",
        )
        screenshot_frame = self.screenshot_preview.build(master, title="注册/密保截图")
        screenshot_frame.grid(row=len(fields), column=0, columnspan=2, sticky="ew", padx=6, pady=(8, 4))
        screenshot_actions = create_form_frame(master, palette=MAIN_PALETTE)
        screenshot_actions.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))
        ttk.Button(
            screenshot_actions,
            text="添加图片",
            command=lambda: self.screenshot_preview.choose_image(parent=self),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            screenshot_actions,
            text="查看大图",
            command=lambda: self.screenshot_preview.open_large_viewer(parent=self),
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="命名当前",
            command=lambda: self.screenshot_preview.rename_current(parent=self),
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="移除当前",
            command=self.screenshot_preview.remove_current,
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="清空全部",
            command=self.screenshot_preview.clear_all,
        ).pack(side="left", padx=6)
        master.columnconfigure(1, weight=1)
        return self.entries["title"]

    def validate(self):
        if not self.entries["title"].get().strip():
            messagebox.showwarning(self.app_title, "标题不能为空。", parent=self)
            return False
        return True

    def apply(self):
        self.result = {field: widget.get().strip() for field, widget in self.entries.items()}
        self.result["screenshot_path"] = self.screenshot_preview.get_value()


class ProcessFlowDialog(simpledialog.Dialog):
    """流程记录编辑对话框。"""

    def __init__(self, parent, title: str, initial: dict | None = None, *, app_title: str):
        self.initial = initial or {}
        self.result = None
        self.app_title = app_title
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        self.entries = {}
        fields = [
            ("title", "流程名称"),
            ("category", "分类"),
            ("platform", "平台"),
            ("link_url", "流程入口链接"),
            ("note", "备注"),
        ]
        for row_index, (field, label) in enumerate(fields):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(row=row_index, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=56)
            entry.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, self.initial.get(field, ""))
            self.entries[field] = entry
        master.columnconfigure(1, weight=1)
        return self.entries["title"]

    def validate(self):
        if not self.entries["title"].get().strip():
            messagebox.showwarning(self.app_title, "流程名称不能为空。", parent=self)
            return False
        return True

    def apply(self):
        self.result = {field: widget.get().strip() for field, widget in self.entries.items()}


class ProcessStepDialog(simpledialog.Dialog):
    """流程步骤编辑对话框。"""

    def __init__(self, parent, title: str, initial: dict | None = None, *, app_title: str, image_preview_cls):
        self.initial = initial or {}
        self.result = None
        self.app_title = app_title
        self.image_preview_cls = image_preview_cls
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        self.entries = {}
        simple_fields = [
            ("step_no", "步骤序号"),
            ("title", "步骤标题"),
            ("link_url", "步骤链接"),
            ("required_text", "必填项说明"),
            ("optional_text", "选填项说明"),
            ("note", "备注"),
        ]
        current_row = 0
        for field, label in simple_fields:
            create_form_label(master, label, palette=MAIN_PALETTE).grid(row=current_row, column=0, sticky="nw", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=64)
            entry.grid(row=current_row, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, str(self.initial.get(field, "")))
            self.entries[field] = entry
            current_row += 1

        create_form_label(master, "步骤描述", palette=MAIN_PALETTE).grid(row=current_row, column=0, sticky="nw", padx=6, pady=4)
        self.description_text = scrolledtext.ScrolledText(master, width=62, height=8, wrap="word")
        self.description_text.grid(row=current_row, column=1, sticky="nsew", padx=6, pady=4)
        self.description_text.configure(
            bg=MAIN_PALETTE.input_bg,
            fg=MAIN_PALETTE.text_primary,
            insertbackground=MAIN_PALETTE.text_primary,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=MAIN_PALETTE.input_border,
            highlightcolor=MAIN_PALETTE.input_focus,
        )
        self.description_text.insert("1.0", self.initial.get("description_text", ""))
        current_row += 1

        self.screenshot_preview = self.image_preview_cls(
            self,
            image_value=self.initial.get("screenshot_path", ""),
            preview_size=(240, 150),
            empty_text="未上传步骤截图",
            image_subdir="process_flows",
        )
        screenshot_frame = self.screenshot_preview.build(master, title="步骤截图")
        screenshot_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", padx=6, pady=(8, 4))
        current_row += 1

        screenshot_actions = create_form_frame(master, palette=MAIN_PALETTE)
        screenshot_actions.grid(row=current_row, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))
        ttk.Button(
            screenshot_actions,
            text="添加图片",
            command=lambda: self.screenshot_preview.choose_image(parent=self),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            screenshot_actions,
            text="命名当前",
            command=lambda: self.screenshot_preview.rename_current(parent=self),
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="查看大图",
            command=lambda: self.screenshot_preview.open_large_viewer(parent=self, title="查看步骤截图"),
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="移除当前",
            command=self.screenshot_preview.remove_current,
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="清空全部",
            command=self.screenshot_preview.clear_all,
        ).pack(side="left", padx=6)

        master.columnconfigure(1, weight=1)
        master.rowconfigure(current_row - 1, weight=1)
        return self.entries["title"]

    def validate(self):
        title = self.entries["title"].get().strip()
        if not title:
            messagebox.showwarning(self.app_title, "步骤标题不能为空。", parent=self)
            return False
        step_no_text = self.entries["step_no"].get().strip() or "1"
        if not step_no_text.isdigit() or int(step_no_text) <= 0:
            messagebox.showwarning(self.app_title, "步骤序号必须为正整数。", parent=self)
            return False
        return True

    def apply(self):
        self.result = {field: widget.get().strip() for field, widget in self.entries.items()}
        self.result["step_no"] = int(self.result.get("step_no", "1") or "1")
        self.result["description_text"] = self.description_text.get("1.0", "end").strip()
        self.result["screenshot_path"] = self.screenshot_preview.get_value()
