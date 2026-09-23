# -*- coding: utf-8 -*-
"""账号中心与流程中心相关弹窗。"""

from tkinter import messagebox, scrolledtext, simpledialog, ttk

from dialog_form_style import apply_dialog_form_style, create_form_entry, create_form_frame, create_form_label
from process_db import (
    COMMAND_LANGS,
    STEP_KIND_CHOICES,
    STEP_KIND_OP,
    label_to_step_kind,
    parse_variables,
    step_kind_label,
)
from ui_theme import MAIN_PALETTE, TYPOGRAPHY


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
    """流程步骤编辑对话框。

    字段按「常用 / 备案遗留」分两组：常用的是类型、标题、链接、前置检查、说明、
    命令、预期结果、截图；备案遗留的是必填项 / 选填项说明（实测填充率只有
    11% / 5%，但数据要留着，所以放在下面、不删）。

    步骤类型决定哪个框是主角：命令型时命令框是重点，操作型只要说明。这里**不做
    动态显隐** —— Tk 里藏起来的控件会让人以为功能没了，全部一次摊开更省事。
    """

    def __init__(self, parent, title: str, initial: dict | None = None, *,
                 app_title: str, image_preview_cls, image_subdir: str = "process_flows"):
        self.initial = initial or {}
        self.result = None
        self.app_title = app_title
        self.image_preview_cls = image_preview_cls
        self.image_subdir = image_subdir
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        self.entries = {}
        current_row = [0]

        def add_entry(key: str, label: str, *, width: int = 64):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(
                row=current_row[0], column=0, sticky="nw", padx=6, pady=4
            )
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=width)
            entry.grid(row=current_row[0], column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, str(self.initial.get(key, "") or ""))
            self.entries[key] = entry
            current_row[0] += 1
            return entry

        def add_combo(key: str, label: str, values: list, initial_value: str, *, width: int = 20):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(
                row=current_row[0], column=0, sticky="nw", padx=6, pady=4
            )
            box = ttk.Combobox(master, values=list(values), state="readonly", width=width)
            box.grid(row=current_row[0], column=1, sticky="w", padx=6, pady=4)
            box.set(initial_value)
            self.entries[key] = box
            current_row[0] += 1
            return box

        def add_text(key: str, label: str, *, height: int = 5, mono: bool = False):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(
                row=current_row[0], column=0, sticky="nw", padx=6, pady=4
            )
            widget = scrolledtext.ScrolledText(
                master, width=62, height=height, wrap="none" if mono else "word",
                font=TYPOGRAPHY.mono if mono else TYPOGRAPHY.body,
            )
            widget.grid(row=current_row[0], column=1, sticky="nsew", padx=6, pady=4)
            widget.configure(
                bg=MAIN_PALETTE.input_bg,
                fg=MAIN_PALETTE.text_primary,
                insertbackground=MAIN_PALETTE.text_primary,
                relief="solid",
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=MAIN_PALETTE.input_border,
                highlightcolor=MAIN_PALETTE.input_focus,
            )
            widget.insert("1.0", str(self.initial.get(key, "") or ""))
            self.entries[key] = widget
            row_now = current_row[0]
            current_row[0] += 1
            return widget, row_now

        add_entry("step_no", "步骤序号", width=12)
        add_combo("kind_label", "步骤类型", STEP_KIND_CHOICES,
                  step_kind_label(self.initial.get("kind", STEP_KIND_OP)))
        add_entry("title", "步骤标题")
        add_entry("link_url", "步骤链接")
        add_entry("precheck_text", "前置检查")
        _, row_description = add_text("description_text", "步骤说明", height=4)
        add_combo("command_lang", "命令语言", COMMAND_LANGS,
                  str(self.initial.get("command_lang", "shell") or "shell"))
        add_text("command_text", "命令（可复制执行）", height=5, mono=True)
        add_entry("expected_text", "预期结果")
        add_entry("required_text", "必填项说明（留档）")
        add_entry("optional_text", "选填项说明（留档）")
        add_entry("note", "备注")

        self.screenshot_preview = self.image_preview_cls(
            self,
            image_value=self.initial.get("screenshot_path", ""),
            preview_size=(240, 150),
            empty_text="未上传步骤截图（也可在页面里直接「贴图」）",
            image_subdir=self.image_subdir,
        )
        create_form_label(master, "步骤截图", palette=MAIN_PALETTE).grid(
            row=current_row[0], column=0, sticky="nw", padx=6, pady=4
        )
        screenshot_frame = self.screenshot_preview.build(master)
        screenshot_frame.grid(row=current_row[0], column=1, sticky="nsew", padx=6, pady=4)
        current_row[0] += 1

        screenshot_actions = create_form_frame(master, palette=MAIN_PALETTE)
        screenshot_actions.grid(row=current_row[0], column=1, sticky="w", padx=6, pady=(0, 6))
        ttk.Button(screenshot_actions, text="添加图片",
                   command=lambda: self.screenshot_preview.choose_image(parent=self)).pack(
            side="left", padx=(0, 6))
        ttk.Button(screenshot_actions, text="命名当前",
                   command=lambda: self.screenshot_preview.rename_current(parent=self)).pack(
            side="left", padx=6)
        ttk.Button(screenshot_actions, text="查看大图",
                   command=lambda: self.screenshot_preview.open_large_viewer(
                       parent=self, title="查看步骤截图")).pack(side="left", padx=6)
        ttk.Button(screenshot_actions, text="移除当前",
                   command=self.screenshot_preview.remove_current).pack(side="left", padx=6)
        ttk.Button(screenshot_actions, text="清空全部",
                   command=self.screenshot_preview.clear_all).pack(side="left", padx=6)

        master.columnconfigure(1, weight=1)
        master.rowconfigure(row_description, weight=1)
        return self.entries["title"]

    def validate(self):
        if not self.entries["title"].get().strip():
            messagebox.showwarning(self.app_title, "步骤标题不能为空。", parent=self)
            return False
        step_no_text = self.entries["step_no"].get().strip() or "1"
        if not step_no_text.isdigit() or int(step_no_text) <= 0:
            messagebox.showwarning(self.app_title, "步骤序号必须为正整数。", parent=self)
            return False
        # 新建时选了「命令型」却一个命令都没写，等于建了个空壳，先问一句
        if not str(self.initial.get("id", "") or "").strip():
            if label_to_step_kind(self.entries["kind_label"].get()) == "cmd":
                if not self.entries["command_text"].get("1.0", "end").strip():
                    if not messagebox.askyesno(
                        self.app_title,
                        "步骤类型选了「命令型」但命令是空的。\n\n仍然保存吗？",
                        parent=self,
                    ):
                        return False
        return True

    def apply(self):
        def text_of(key):
            widget = self.entries[key]
            if isinstance(widget, scrolledtext.ScrolledText):
                return widget.get("1.0", "end").strip()
            return widget.get().strip()

        self.result = {
            "step_no": int(self.entries["step_no"].get().strip() or "1"),
            "title": self.entries["title"].get().strip(),
            "kind": label_to_step_kind(self.entries["kind_label"].get()),
            "link_url": self.entries["link_url"].get().strip(),
            "precheck_text": text_of("precheck_text"),
            "description_text": text_of("description_text"),
            "command_lang": self.entries["command_lang"].get().strip() or "shell",
            "command_text": text_of("command_text"),
            "expected_text": text_of("expected_text"),
            "required_text": self.entries["required_text"].get().strip(),
            "optional_text": self.entries["optional_text"].get().strip(),
            "note": self.entries["note"].get().strip(),
            "screenshot_path": self.screenshot_preview.get_value(),
        }


class ProcessVariablesDialog(simpledialog.Dialog):
    """流程变量编辑：**每行一个变量**。

    用「一行一条」的纯文本而不是表格编辑器：这类变量通常只有三五条，敲起来比点
    「新增行」快得多，也方便整段粘贴进来。两种写法::

        域名=example.com
        环境|部署环境=prod
        # 井号开头的行会被忽略

    第二行那种写法里，竖线后面是**显示名**（不写就与键名相同）。返回值
    （``result``）是变量定义列表，交数据层序列化落库。
    """

    def __init__(self, parent, title: str, initial: dict | None = None, *, app_title: str):
        self.initial = initial or {}
        self.result = None
        self.app_title = app_title
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        create_form_label(master, "变量定义", palette=MAIN_PALETTE).grid(
            row=0, column=0, sticky="nw", padx=6, pady=4
        )
        self.text = scrolledtext.ScrolledText(master, width=54, height=11, wrap="none",
                                              font=TYPOGRAPHY.mono)
        self.text.grid(row=0, column=1, sticky="nsew", padx=6, pady=4)
        self.text.configure(
            bg=MAIN_PALETTE.input_bg,
            fg=MAIN_PALETTE.text_primary,
            insertbackground=MAIN_PALETTE.text_primary,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=MAIN_PALETTE.input_border,
            highlightcolor=MAIN_PALETTE.input_focus,
        )
        existing = self._lines_from_initial()
        if existing:
            self.text.insert("1.0", "\n".join(existing))
        create_form_label(
            master,
            "每行一个：键=默认值\n"
            "也可写 键|显示名=默认值（竖线后是显示名）\n"
            "# 开头的行会被忽略\n\n"
            "命令或说明里写 {{键}} 就会替换成这里填的值；\n"
            "留空的值不替换，原样显示 {{键}} 表示「还没填」。",
            palette=MAIN_PALETTE,
        ).grid(row=1, column=1, sticky="w", padx=6, pady=(0, 6))
        master.columnconfigure(1, weight=1)
        master.rowconfigure(0, weight=1)
        return self.text

    def _lines_from_initial(self) -> list:
        items = parse_variables(self.initial.get("variables", ""))
        lines = []
        for item in items:
            head = (item["key"] if item["label"] == item["key"]
                    else item["key"] + "|" + item["label"])
            lines.append(head + "=" + str(item.get("default", "")))
        return lines

    def validate(self):
        for index, line in enumerate(self.text.get("1.0", "end").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            head = stripped.split("=", 1)[0]
            if not head.split("|", 1)[0].strip():
                messagebox.showwarning(
                    self.app_title,
                    "第 " + str(index) + " 行没有变量名：\n" + stripped,
                    parent=self,
                )
                return False
        return True

    def apply(self):
        items = []
        seen = set()
        for line in self.text.get("1.0", "end").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                head, default = stripped.split("=", 1)
            else:
                head, default = stripped, ""
            head = head.strip()
            if "|" in head:
                key, label = head.split("|", 1)
            else:
                key, label = head, head
            key = key.strip()
            label = label.strip() or key
            if not key or key in seen:
                continue
            seen.add(key)
            items.append({"key": key, "label": label,
                          "default": default.strip(), "hint": ""})
        self.result = items
