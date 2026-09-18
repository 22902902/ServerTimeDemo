# -*- coding: utf-8 -*-
"""左侧分组导航侧栏（自绘）。

为什么不用原生 ttk.Treeview
------------------------------------------------------------------------------
Treeview 的缩进连线、三角展开器、整行反白选中都是随主题原生绘制的，
用 style 无法消除，圆角更做不到。对一个「黑白 + 浅灰」的克制风格来说，
这些原生痕迹正是界面显得「硬」的主要来源。

本模块用 tk.Frame / tk.Label 自绘导航行：

1. 浅灰侧栏与白色内容区靠**色差**分隔，不画竖线
2. 悬停 / 选中用极浅灰填充表达；选中额外加 2px 左侧近黑细条
3. 层级用「缩进 + 5px 圆点」表达，不使用图标（旧版的黄色文件夹图标已移除）

对外接口
------------------------------------------------------------------------------
    nav = SidebarNav(parent, on_select=handler)
    nav.pack(side="left", fill="y")
    nav.select("module_ops_expiry", notify=False)
"""

from __future__ import annotations

import tkinter as tk

from ui_theme import MAIN_PALETTE, TYPOGRAPHY


# 导航结构（唯一数据源）
#   section —— 分组标题，不可点击
#   group   —— 可折叠分组，点击展开/收起
#   module  —— 功能模块，点击切换页面；key 必须能在 module_items 中查到
NAV_MODEL = [
    {
        "kind": "section",
        "key": "sec_work",
        "label": "工作",
        "items": [
            {"kind": "module", "key": "module_ops_expiry", "label": "到期管理"},
            {"kind": "module", "key": "module_work_credentials", "label": "账号中心"},
            {"kind": "module", "key": "module_work_processes", "label": "流程中心"},
            {
                "kind": "group",
                "key": "grp_api",
                "label": "接口测试",
                "items": [
                    {
                        "kind": "group",
                        "key": "grp_wenpai",
                        "label": "文拍",
                        "items": [
                            {"kind": "module", "key": "module_admin_backend", "label": "后台接口测试"},
                        ],
                    },
                ],
            },
            {"kind": "module", "key": "module_qa_work", "label": "Q&A 与工作纪要"},
            {"kind": "module", "key": "module_system_toolbox", "label": "系统工具箱"},
        ],
    },
    {
        "kind": "section",
        "key": "sec_life",
        "label": "生活",
        "items": [
            {"kind": "module", "key": "module_study_notes", "label": "笔记"},
            {"kind": "module", "key": "module_study_demo", "label": "Python 学习"},
        ],
    },
]

# 尺寸 token（保持 4 的倍数节奏）
SECTION_GAP_TOP = 16
ROW_PAD_Y = 7
DOT_SIZE = 5
INDENT_STEP = 14
ACCENT_WIDTH = 2
DOT_LEFT_GAP = 6
DOT_TEXT_GAP = 9


class SidebarNav(tk.Frame):
    """自绘的分组导航侧栏。"""

    def __init__(
        self,
        master,
        *,
        on_select=None,
        palette=MAIN_PALETTE,
        typography=TYPOGRAPHY,
        width: int = 212,
    ):
        super().__init__(master, bg=palette.sidebar_bg, width=width)
        self.pack_propagate(False)

        self.palette = palette
        self.typography = typography
        self.on_select = on_select

        self._inner = tk.Frame(self, bg=palette.sidebar_bg)
        self._inner.pack(fill="both", expand=True, padx=10, pady=6)

        self._rows: dict[str, dict] = {}
        self._nodes: dict[str, dict] = {}
        self._collapsed: set[str] = set()
        self._selected: str | None = None
        self._hovered: str | None = None
        self._section_count = 0

        self._index_nodes(NAV_MODEL)
        self.rebuild()

    # ------------------------------------------------------------------
    # 模型索引
    # ------------------------------------------------------------------
    def _index_nodes(self, nodes) -> None:
        for node in nodes:
            self._nodes[node["key"]] = node
            if node.get("items"):
                self._index_nodes(node["items"])

    def module_keys(self) -> list[str]:
        """返回所有 module 节点的 key（顺序与渲染一致）。"""
        return [key for key, node in self._nodes.items() if node["kind"] == "module"]

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def rebuild(self) -> None:
        """整表重建。导航仅十余行，重建比增量增删更简单可靠。"""
        for child in self._inner.winfo_children():
            child.destroy()
        self._rows.clear()
        self._section_count = 0
        self._render(NAV_MODEL, level=0, hidden=False)
        self._refresh_states()

    def _render(self, nodes, *, level: int, hidden: bool) -> None:
        for node in nodes:
            kind = node["kind"]
            key = node["key"]
            if kind == "section":
                self._make_section(node)
                self._render(node.get("items", []), level=level + 1, hidden=False)
                continue
            if hidden:
                continue
            if kind == "group":
                self._make_row(node, level=level, kind=kind)
                self._render(
                    node.get("items", []),
                    level=level + 1,
                    hidden=key in self._collapsed,
                )
            else:
                self._make_row(node, level=level, kind=kind)

    def _make_section(self, node) -> None:
        palette = self.palette
        top = 4 if self._section_count == 0 else SECTION_GAP_TOP
        self._section_count += 1

        wrapper = tk.Frame(self._inner, bg=palette.sidebar_bg)
        wrapper.pack(fill="x", pady=(top, 4))
        tk.Label(
            wrapper,
            text=node["label"],
            bg=palette.sidebar_bg,
            fg=palette.text_muted,
            font=self.typography.nav_group,
            anchor="w",
        ).pack(fill="x", padx=12)

    def _make_row(self, node, *, level: int, kind: str) -> None:
        palette = self.palette
        key = node["key"]
        indent = DOT_LEFT_GAP + max(0, level - 1) * INDENT_STEP

        row = tk.Frame(self._inner, bg=palette.sidebar_bg, cursor="hand2")
        row.pack(fill="x")

        # 左侧 2px 强调条：始终存在（避免选中时布局位移），只改颜色
        accent = tk.Frame(row, width=ACCENT_WIDTH, bg=palette.sidebar_bg)
        accent.pack(side="left", fill="y")

        dot = tk.Frame(row, width=DOT_SIZE, height=DOT_SIZE, bg=palette.nav_dot)
        dot.pack(side="left", padx=(indent, DOT_TEXT_GAP))

        label = tk.Label(
            row,
            text=node["label"],
            bg=palette.sidebar_bg,
            fg=palette.nav_text,
            font=self.typography.nav_item,
            anchor="w",
            cursor="hand2",
        )
        label.pack(side="left", fill="x", expand=True, pady=ROW_PAD_Y)

        chevron = None
        if kind == "group":
            chevron = tk.Label(
                row,
                text=self._chevron_text(key),
                bg=palette.sidebar_bg,
                fg=palette.text_muted,
                font=self.typography.nav_group,
                cursor="hand2",
            )
            chevron.pack(side="right", padx=(6, 10))

        widgets = [row, accent, dot, label]
        if chevron is not None:
            widgets.append(chevron)
        for widget in widgets:
            widget.bind("<Enter>", lambda _e, k=key: self._on_enter(k))
            widget.bind("<Leave>", lambda _e, k=key: self._on_leave(k))
            widget.bind("<Button-1>", lambda _e, k=key: self._on_click(k))

        self._rows[key] = {
            "row": row,
            "accent": accent,
            "dot": dot,
            "label": label,
            "chevron": chevron,
            "kind": kind,
        }

    def _chevron_text(self, key: str) -> str:
        return "▾" if key not in self._collapsed else "▸"

    # ------------------------------------------------------------------
    # 状态刷新
    # ------------------------------------------------------------------
    def _refresh_states(self) -> None:
        palette = self.palette
        for key, widgets in self._rows.items():
            if key == self._selected:
                bg, fg = palette.sidebar_active, palette.text_primary
                font = self.typography.nav_item_active
                dot_bg, accent_bg = palette.accent, palette.accent
            elif key == self._hovered:
                bg, fg = palette.sidebar_hover, palette.nav_text
                font = self.typography.nav_item
                dot_bg, accent_bg = palette.nav_dot_hover, palette.sidebar_hover
            else:
                bg, fg = palette.sidebar_bg, palette.nav_text
                font = self.typography.nav_item
                dot_bg, accent_bg = palette.nav_dot, palette.sidebar_bg

            widgets["row"].configure(bg=bg)
            widgets["accent"].configure(bg=accent_bg)
            widgets["dot"].configure(bg=dot_bg)
            widgets["label"].configure(bg=bg, fg=fg, font=font)
            if widgets["chevron"] is not None:
                widgets["chevron"].configure(bg=bg)

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _on_enter(self, key: str) -> None:
        if self._hovered == key:
            return
        self._hovered = key
        self._refresh_states()

    def _on_leave(self, key: str) -> None:
        # 指针从行移到子控件（圆点/文字）时父行也会收到 Leave，
        # 因此延迟到空闲时用指针实际坐标复核，避免悬停态闪烁。
        self.after_idle(lambda k=key: self._confirm_leave(k))

    def _confirm_leave(self, key: str) -> None:
        if self._hovered != key:
            return
        widgets = self._rows.get(key)
        if not widgets:
            return
        row = widgets["row"]
        try:
            pointer_x, pointer_y = row.winfo_pointerxy()
            root_x, root_y = row.winfo_rootx(), row.winfo_rooty()
            inside = (
                root_x <= pointer_x < root_x + row.winfo_width()
                and root_y <= pointer_y < root_y + row.winfo_height()
            )
        except Exception:
            inside = False
        if not inside:
            self._hovered = None
            self._refresh_states()

    def _on_click(self, key: str) -> None:
        node = self._nodes.get(key)
        if not node:
            return
        if node["kind"] == "group":
            if key in self._collapsed:
                self._collapsed.discard(key)
            else:
                self._collapsed.add(key)
            self.rebuild()
            return
        self.select(key)

    # ------------------------------------------------------------------
    # 对外选择接口
    # ------------------------------------------------------------------
    def select(self, key: str, *, notify: bool = True) -> bool:
        """高亮某个模块。notify=False 用于由代码（而非点击）发起的高亮同步。"""
        if key not in self._rows:
            return False
        changed = key != self._selected
        self._selected = key
        self._refresh_states()
        if notify and changed and self.on_select:
            self.on_select(key)
        return True

    def current(self) -> str | None:
        return self._selected
