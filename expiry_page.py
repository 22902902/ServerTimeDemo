# -*- coding: utf-8 -*-
"""到期管理页面类。"""

import re
import tkinter.font as tkfont
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


# ----------------------------------------------------------------------
# 单元格文本收敛：表格负责「扫视」，详情弹窗负责「细读」
#
# 「资源详情」在库里常是多行（一行一个 IP / 域名 / 域名列表），
# 直接塞进 Treeview 会把行撑高、文字溢出到相邻列，整张表看起来是散的。
# 这里统一收敛成一行、不超出列宽：换行折成分隔符，放不下就丢整段并加省略号。
#
# 为什么强调「丢整段」而不是直接按字符切：像
#   IP：203.0.113.45 / 配置：4 核（vCPU）16 GiB10 Mbps
# 按字符切会得到「…（vCPU）1…」这种从数值中间断开的残句，读起来是坏的；
# 整段丢弃则得到「IP：203.0.113.45…」，至少每一段都是完整的。
# Treeview 自己超宽只会硬裁（看不出「后面还有」），所以省略号必须自己加。
# ----------------------------------------------------------------------
CELL_SUMMARY_SEP = " · "
CELL_TEXT_PADDING = 14   # 单元格左右留白，避免文字顶到列边线上


def split_cell_chunks(value) -> list[str]:
    """按换行把单元格值切成若干段（去掉空段与首尾空白）。"""
    if value is None:
        return []
    return [chunk.strip() for chunk in re.split(r"[\r\n]+", str(value)) if chunk.strip()]


def compact_cell_text(value, *, sep: str = CELL_SUMMARY_SEP) -> str:
    """把可能多行的单元格值压成单行（换行折成分隔符）。"""
    return sep.join(split_cell_chunks(value))


def ellipsize_px(text: str, max_px: int, *, font) -> str:
    """按像素宽度截断并追加省略号（宽度用二分查找量，不逐字符循环）。

    这是最后手段：只在「连第一段都放不下」时才用，避免把数值从中间切开。
    """
    if not text or max_px <= 0:
        return text or ""
    if font.measure(text) <= max_px:
        return text
    ellipsis = "…"
    budget = max_px - font.measure(ellipsis)
    if budget <= 0:
        return ellipsis
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if font.measure(text[:mid]) <= budget:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + ellipsis


def treeview_font(tree):
    """取 Treeview 实际使用的字体，供按像素量算截断宽度。"""
    try:
        spec = ttk.Style(tree).lookup("Treeview", "font")
    except Exception:
        spec = None
    if spec:
        try:
            return tkfont.Font(root=tree, font=spec)
        except Exception:
            pass
    return tkfont.nametofont("TkDefaultFont")


def summarize_cell_text(value, column: str, *, column_meta, font=None,
                        sep: str = CELL_SUMMARY_SEP) -> str:
    """把单元格值收敛成「一行、且不超出该列宽度」的摘要。

    放得下 → 原样；放不下 → 逐段保留、末尾加省略号；连第一段都放不下
    → 才退化为按像素截断。完整内容一律由「详情」弹窗承载。
    """
    chunks = split_cell_chunks(value)
    if not chunks:
        return ""
    width = column_meta.get(column, {}).get("width", 0)
    if not width:
        return sep.join(chunks)

    font = font or tkfont.nametofont("TkDefaultFont")
    limit = width - CELL_TEXT_PADDING
    full = sep.join(chunks)
    if font.measure(full) <= limit:
        return full

    kept = ""
    for index, chunk in enumerate(chunks):
        candidate = chunk if not kept else kept + sep + chunk
        # 还有后续段时先预留省略号的位置，否则最后一段会被省略号顶出列外
        tail = "…" if index < len(chunks) - 1 else ""
        if font.measure(candidate + tail) <= limit:
            kept = candidate
        else:
            break
    if kept:
        return kept + "…"
    return ellipsize_px(chunks[0], limit, font=font)


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
