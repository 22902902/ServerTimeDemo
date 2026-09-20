# -*- coding: utf-8 -*-
"""到期管理相关弹窗。"""

from datetime import datetime
import sqlite3
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from dialog_form_style import apply_dialog_form_style, create_form_checkbutton, create_form_entry, create_form_frame, create_form_label, create_form_radiobutton
from ui_theme import MAIN_PALETTE, TYPOGRAPHY


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


# ----------------------------------------------------------------------
# 详情弹窗
#
# 表格里每列只给一行摘要（截断处带 …），完整内容在这里呈现 —— 所以这个弹窗
# 的目标不是「能看」，而是「一眼扫完、顺手复制走」：
#   · 顶部一行回答最常被问的两件事：这是哪一条、还有多久到期
#   · 正文按「资源信息 / 账号信息 / 时间」分组，标签列对齐、值可自动换行
#   · 底部「复制全部」复制的是扁平文本，方便贴到别处
# 正文用 tk.Text 而不是一堆 Label：值可选中、可 Ctrl+C，多行的资源详情也能自然换行。
# ----------------------------------------------------------------------
DETAIL_GROUPS = (
    ("资源信息", ("resource_type", "resource_detail",
                  "resource_subject_code", "resource_subject_name")),
    ("账号信息", ("account_no", "account_subject_code", "account_subject_name")),
    ("到期", ("expiry_date", "expiry_raw")),
    ("其他", ("note",)),
)
DETAIL_OTHER_GROUP = "其他"       # 未登记字段也并进这一组，避免出现两个同名分组
# 顶部表头已经展示过的字段，正文里不再重复一遍
DETAIL_HEADER_FIELDS = ("record_no", "platform")
DETAIL_LABEL_TAB_PX = 100         # 标签列宽（像素），正文靠 tab stop 对齐
DETAIL_EMPTY = "—"                # 空值占位，保持版面可读

# 到期状态徽标底色与主表格的行 tag 保持一致，避免同一个状态两种颜色
DETAIL_STATE_STYLE = {
    "overdue":  ("#fbeeec", "#a3372f"),
    "soon":     ("#fdf6e3", "#8a6a2f"),
    "upcoming": ("#f6f6f6", "#6b6b6b"),
    "normal":   ("#eeeeee", "#6b6b6b"),
    "unknown":  ("#eeeeee", "#9a9a9a"),
}


def describe_expiry(remain_days) -> tuple[str, str]:
    """把剩余天数翻译成（状态键, 给用户看的一句话）。"""
    if remain_days is None:
        return "unknown", "未设置到期"
    if remain_days < 0:
        return "overdue", f"已过期 {abs(remain_days)} 天"
    if remain_days == 0:
        return "soon", "今天到期"
    if remain_days <= 15:
        return "soon", f"{remain_days} 天后到期"
    if remain_days <= 30:
        return "upcoming", f"{remain_days} 天后到期"
    return "normal", f"{remain_days} 天后到期"


def _row_value(row, field: str) -> str:
    """安全取一行里的字段（sqlite3.Row 缺列会抛 IndexError，不能直接下标）。"""
    try:
        value = row[field]
    except (IndexError, KeyError, TypeError):
        return ""
    return "" if value is None else str(value)


class DetailDialog(tk.Toplevel):
    """资产/服务记录详情弹窗（只读）。

    刻意保留了原来 simpledialog.Dialog 版本的调用签名，只把外壳换成自绘 Toplevel：
    原版是一个 Text 倾倒「键：值」行再加英文 OK/Cancel，既没有层级也不好复制。
    这里不做 wait_window —— 主窗口用 grab_set 保持模态即可，调用方不必等待。
    """

    def __init__(
        self,
        parent,
        asset_row: sqlite3.Row,
        accounts: list[sqlite3.Row],
        *,
        detail_fields,
        format_account_identity,
        remain_days=None,
    ):
        super().__init__(parent)
        self.asset_row = asset_row
        self.accounts = list(accounts or [])
        self.detail_fields = list(detail_fields)
        self.format_account_identity = format_account_identity
        self.remain_days = remain_days

        self.title("资源详情")
        self.configure(bg=MAIN_PALETTE.bg)
        self.minsize(580, 460)
        self.resizable(True, True)
        self.transient(parent)

        self._build()
        self._center_on(parent)
        self.bind("<Escape>", lambda _event: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()
        self.focus_set()

    # -- 组装 ---------------------------------------------------------------
    def _build(self) -> None:
        self._build_header()
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        self._build_body()
        self._build_footer()

    def _build_header(self) -> None:
        palette = MAIN_PALETTE
        head = tk.Frame(self, bg=palette.bg)
        head.pack(fill="x", padx=24, pady=(20, 16))

        left = tk.Frame(head, bg=palette.bg)
        left.pack(side="left", fill="x", expand=True)

        record_no = _row_value(self.asset_row, "record_no").strip()
        tk.Label(
            left,
            text=record_no or "（无编号）",
            bg=palette.bg,
            fg=palette.text_primary,
            font=TYPOGRAPHY.subtitle,
            anchor="w",
        ).pack(anchor="w")

        subtitle = " · ".join(
            part for part in (
                _row_value(self.asset_row, "platform").strip(),
                _row_value(self.asset_row, "resource_type").strip(),
            ) if part
        )
        tk.Label(
            left,
            text=subtitle or DETAIL_EMPTY,
            bg=palette.bg,
            fg=palette.text_secondary,
            font=TYPOGRAPHY.body,
            anchor="w",
        ).pack(anchor="w", pady=(6, 0))

        right = tk.Frame(head, bg=palette.bg)
        right.pack(side="right", anchor="n")

        state_key, state_text = describe_expiry(self.remain_days)
        bg, fg = DETAIL_STATE_STYLE.get(state_key, DETAIL_STATE_STYLE["unknown"])
        tk.Label(
            right,
            text=state_text,
            bg=bg,
            fg=fg,
            font=TYPOGRAPHY.badge,
            padx=10,
            pady=4,
        ).pack(anchor="e")

        expiry_date = _row_value(self.asset_row, "expiry_date").strip()
        if expiry_date:
            tk.Label(
                right,
                text=f"到期日 {expiry_date}",
                bg=palette.bg,
                fg=palette.text_muted,
                font=TYPOGRAPHY.caption,
            ).pack(anchor="e", pady=(8, 0))

    def _build_body(self) -> None:
        palette = MAIN_PALETTE
        wrap = tk.Frame(self, bg=palette.bg)
        wrap.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        self.body = tk.Text(
            wrap,
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            bg=palette.bg,
            fg=palette.text_primary,
            selectbackground=palette.sidebar_active,
            selectforeground=palette.text_primary,
            insertbackground=palette.text_primary,
            cursor="arrow",
            padx=0,
            pady=0,
            spacing2=2,
        )
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.body.yview)
        self.body.configure(yscrollcommand=scroll.set)
        self.body.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._configure_body_tags()
        self._fill_body()
        # 只读：仍可选中与 Ctrl+C，但不能编辑
        self.body.configure(state="disabled")

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="复制选中", command=self._copy_selection)
        self.body.bind("<Button-3>", self._popup_menu)

    def _configure_body_tags(self) -> None:
        palette = MAIN_PALETTE
        # Tk 的 tag 优先级 = 创建顺序，后建的覆盖同名字段。
        # 先建「版式」tag，再建「字体/颜色」tag —— 后者不声明 lmargin，
        # 所以字段的悬挂缩进不会被字体 tag 冲掉。
        self.body.tag_configure("field", lmargin1=0, lmargin2=DETAIL_LABEL_TAB_PX, spacing3=7)
        self.body.tag_configure("sec", spacing1=20, spacing3=9)
        self.body.tag_configure("sub", spacing1=12, spacing3=2,
                                lmargin1=0, lmargin2=DETAIL_LABEL_TAB_PX)
        self.body.tag_configure("section", font=TYPOGRAPHY.section, foreground=palette.text_primary)
        self.body.tag_configure("k", font=TYPOGRAPHY.caption, foreground=palette.text_muted)
        # 值里可能自带换行（如「资源详情」在库里就是两行）。Tk 把内嵌换行当作
        # 新段落，用的是 lmargin1 —— 所以 v / empty 必须自己再声明一次缩进，
        # 否则第二行会顶回最左边，和标签列错开。
        self.body.tag_configure("v", font=TYPOGRAPHY.body, foreground=palette.text_primary,
                                lmargin1=DETAIL_LABEL_TAB_PX, lmargin2=DETAIL_LABEL_TAB_PX)
        self.body.tag_configure("empty", font=TYPOGRAPHY.body, foreground=palette.text_muted,
                                lmargin1=DETAIL_LABEL_TAB_PX, lmargin2=DETAIL_LABEL_TAB_PX)
        self.body.tag_configure("sub_label", font=TYPOGRAPHY.title,
                                foreground=palette.text_primary)
        self.body.tag_configure("sub_value", font=TYPOGRAPHY.title,
                                foreground=palette.text_primary)
        # 标签列对齐靠 tab stop，而不是自己补空格 —— 换字体、换缩放都不会错位
        self.body.configure(tabs=(DETAIL_LABEL_TAB_PX, "left"))

    def _fill_body(self) -> None:
        labels = {field: label for field, label in self.detail_fields}
        grouped = set()
        sections = []

        for title, fields in DETAIL_GROUPS:
            pairs = [(field, labels[field]) for field in fields if field in labels]
            grouped.update(field for field, _unused in pairs)
            if pairs:
                sections.append((title, pairs))

        # 以后给 DETAIL_FIELDS 加字段但忘了登记分组时，不会丢显示
        leftover = [(field, label) for field, label in self.detail_fields
                    if field not in grouped and field not in DETAIL_HEADER_FIELDS]
        if leftover:
            if sections and sections[-1][0] == DETAIL_OTHER_GROUP:
                sections[-1] = (DETAIL_OTHER_GROUP, sections[-1][1] + leftover)
            else:
                sections.append((DETAIL_OTHER_GROUP, leftover))

        for title, pairs in sections:
            self._insert_section(title)
            for field, label in pairs:
                self._insert_field(label, _row_value(self.asset_row, field))

        self._insert_section("账户信息")
        if not self.accounts:
            self._insert_field("", "无")
            return
        for index, account in enumerate(self.accounts, start=1):
            identity = self.format_account_identity(
                _row_value(account, "account_no"), _row_value(account, "account_name")
            )
            self.body.insert("end", f"{index}\t", ("sub", "sub_label"))
            self.body.insert("end", f"{identity or '（未命名）'}\n", ("sub", "sub_value"))
            for label, field in (
                ("主体编号", "subject_code"),
                ("主体名称", "subject_name"),
                ("密码", "password"),
                ("平台", "platform"),
                ("备注", "note"),
            ):
                self._insert_field(label, _row_value(account, field))

    def _insert_section(self, title: str) -> None:
        self.body.insert("end", f"{title}\n", ("sec", "section"))

    def _insert_field(self, label: str, value: str) -> None:
        text = (value or "").strip()
        self.body.insert("end", f"{label}\t", ("field", "k"))
        if text:
            self.body.insert("end", f"{text}\n", ("field", "v"))
        else:
            self.body.insert("end", f"{DETAIL_EMPTY}\n", ("field", "empty"))

    def _build_footer(self) -> None:
        palette = MAIN_PALETTE
        foot = tk.Frame(self, bg=palette.bg)
        foot.pack(fill="x", padx=24, pady=(14, 20))

        ttk.Button(foot, text="关闭", style="Primary.TButton", width=0,
                   command=self._close).pack(side="right")
        self._btn_copy = ttk.Button(foot, text="复制全部", style="Quiet.TButton", width=0,
                                    command=self._copy_all)
        self._btn_copy.pack(side="right", padx=(0, 8))

    # -- 行为 ---------------------------------------------------------------
    def _center_on(self, parent) -> None:
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 3)
        except Exception:
            return
        self.geometry(f"+{x}+{y}")

    def _popup_menu(self, event) -> None:
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _copy_selection(self) -> None:
        try:
            selected = self.body.get("sel.first", "sel.last")
        except Exception:
            return
        if selected:
            self._to_clipboard(selected)

    def _copy_all(self) -> None:
        if not self._to_clipboard(self._plain_text()):
            return
        try:
            self._btn_copy.configure(text="已复制到剪贴板")
        except Exception:
            return
        self.after(1400, self._reset_copy_label)

    def _reset_copy_label(self) -> None:
        if not self.winfo_exists():
            return
        try:
            self._btn_copy.configure(text="复制全部")
        except Exception:
            pass

    def _to_clipboard(self, text: str) -> bool:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            return False
        return True

    def _plain_text(self) -> str:
        """复制出去的仍是扁平「标签：值」文本 —— 便于贴进聊天或工单。"""
        lines = [f"{label}：{_row_value(self.asset_row, field)}"
                 for field, label in self.detail_fields]
        lines.append("")
        lines.append("账户信息：")
        if not self.accounts:
            lines.append("无")
        else:
            for index, account in enumerate(self.accounts, start=1):
                lines.append(f"{index}.")
                lines.append(f"  主体编号：{_row_value(account, 'subject_code')}")
                lines.append(f"  主体名称：{_row_value(account, 'subject_name')}")
                lines.append("  账号信息：" + self.format_account_identity(
                    _row_value(account, "account_no"), _row_value(account, "account_name")))
                lines.append(f"  密码：{_row_value(account, 'password')}")
                lines.append(f"  平台：{_row_value(account, 'platform')}")
                lines.append(f"  备注：{_row_value(account, 'note')}")
        return "\n".join(lines)

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
