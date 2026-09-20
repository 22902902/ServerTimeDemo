# -*- coding: utf-8 -*-
"""全局 UI 主题定义。

风格已敲定，规则如下（改样式时逐条对照）：

1. 靠背景色差分栏，不画竖线：侧栏 #f4f4f4 / 内容 #ffffff
2. 不用 relief 硬描边：卡片与输入框只用 0.5px~1px 的极浅描边（#ececec）
3. 字色不用纯黑：最深 #1c1c1c，次级 #6b6b6b，弱化 #9a9a9a
4. 圆角：小控件 6px，卡片 8px（Tk 原生无圆角，自绘组件负责）
5. 间距走 4 的倍数：8 / 12 / 16 / 24 / 32
6. 字级：20 页面标题 / 14 区块 / 13 正文 / 12 辅助 / 11 组标签（单位 pt）
7. 字重只有两档：normal 与 bold（Tk 无 500，bold 即 500 的角色）
8. 强调色只有一个：近黑 #1c1c1c；红/琥珀/绿仅用于状态且降饱和
9. 导航选中态：#e3e3e3 填充 + 2px 左侧近黑细条，不做整行反白
10. 导航图标用 5px 圆点，不用图标字体
11. 顶栏动作按钮做成纯文字，悬停才浮现浅底
"""

from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True)
class Typography:
    """字体 token（字号单位为 pt，10pt 约等于 13px）。

    注意：Tk 只支持 normal / bold 两档字重（没有 500），
    因此「只用两种字重」在这一层映射为 normal 与 bold。
    """

    hero: tuple = ("Microsoft YaHei UI", 18)
    page_title: tuple = ("Microsoft YaHei UI", 16)
    title: tuple = ("Microsoft YaHei UI", 11, "bold")
    subtitle: tuple = ("Microsoft YaHei UI", 13, "bold")
    section: tuple = ("Microsoft YaHei UI", 11, "bold")
    body: tuple = ("Microsoft YaHei UI", 10)
    caption: tuple = ("Microsoft YaHei UI", 9)
    metric: tuple = ("Microsoft YaHei UI", 20)
    badge: tuple = ("Microsoft YaHei UI", 9, "bold")
    nav_item: tuple = ("Microsoft YaHei UI", 10)
    nav_item_active: tuple = ("Microsoft YaHei UI", 10, "bold")
    nav_group: tuple = ("Microsoft YaHei UI", 9, "bold")


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface_alt: str
    text_primary: str
    text_secondary: str
    text_muted: str
    border: str
    border_soft: str
    button_bg: str
    button_hover: str
    button_pressed: str
    accent: str
    accent_hover: str
    accent_text: str
    input_bg: str
    input_border: str
    input_focus: str
    badge_bg: str
    link: str
    success: str
    warn: str
    danger: str
    status: str
    notebook_tab: str
    notebook_hover: str
    # 侧栏 / 导航（仅自绘侧栏使用；其余窗口不渲染侧栏，取默认值即可）
    sidebar_bg: str = "#f4f4f4"
    sidebar_hover: str = "#eaeaea"
    sidebar_active: str = "#e3e3e3"
    nav_text: str = "#3d3d3d"
    # 线性图标的描边色：比正文浅一档，让文字主导；选中时才压到近黑
    nav_icon: str = "#8f8f8f"
    nav_icon_hover: str = "#525252"
    nav_icon_active: str = "#1c1c1c"


MAIN_PALETTE = Palette(
    bg="#ffffff",
    surface="#ffffff",
    surface_alt="#f7f7f7",
    text_primary="#1c1c1c",
    text_secondary="#6b6b6b",
    text_muted="#9a9a9a",
    border="#ececec",
    border_soft="#f0f0f0",
    button_bg="#ffffff",
    button_hover="#f2f2f2",
    button_pressed="#e8e8e8",
    accent="#1c1c1c",
    accent_hover="#333333",
    accent_text="#ffffff",
    input_bg="#fafafa",
    input_border="#e6e6e6",
    input_focus="#c4c4c4",
    badge_bg="#eeeeee",
    link="#4f6b85",
    success="#2e6b46",
    warn="#8a6a2f",
    danger="#a3372f",
    status="#1c1c1c",
    notebook_tab="#f2f2f2",
    notebook_hover="#ececec",
    sidebar_bg="#f4f4f4",
    sidebar_hover="#eaeaea",
    sidebar_active="#e3e3e3",
    nav_text="#3d3d3d",
    nav_icon="#8f8f8f",
    nav_icon_hover="#525252",
    nav_icon_active="#1c1c1c",
)

TOOLBOX_PALETTE = Palette(
    bg="#ffffff",
    surface="#ffffff",
    surface_alt="#f7f7f7",
    text_primary="#1c1c1c",
    text_secondary="#6b6b6b",
    text_muted="#9a9a9a",
    border="#e6e6e6",
    border_soft="#f0f0f0",
    button_bg="#ffffff",
    button_hover="#f2f2f2",
    button_pressed="#e8e8e8",
    accent="#1c1c1c",
    accent_hover="#333333",
    accent_text="#ffffff",
    input_bg="#fafafa",
    input_border="#e6e6e6",
    input_focus="#c4c4c4",
    badge_bg="#f0f0f0",
    link="#4f6b85",
    success="#2e6b46",
    warn="#8a6a2f",
    danger="#a3372f",
    status="#1c1c1c",
    notebook_tab="#f2f2f2",
    notebook_hover="#ececec",
)

ADMIN_TOOL_PALETTE = Palette(
    bg="#ffffff",
    surface="#ffffff",
    surface_alt="#f7f7f7",
    text_primary="#1c1c1c",
    text_secondary="#6b6b6b",
    text_muted="#9a9a9a",
    border="#e6e6e6",
    border_soft="#f0f0f0",
    button_bg="#ffffff",
    button_hover="#f2f2f2",
    button_pressed="#e8e8e8",
    accent="#1c1c1c",
    accent_hover="#333333",
    accent_text="#ffffff",
    input_bg="#fafafa",
    input_border="#e6e6e6",
    input_focus="#c4c4c4",
    badge_bg="#f0f0f0",
    link="#4f6b85",
    success="#2e6b46",
    warn="#8a6a2f",
    danger="#a3372f",
    status="#1c1c1c",
    notebook_tab="#f2f2f2",
    notebook_hover="#ececec",
)

PACKAGE_ACCENT_COLORS = [
    "#5b7c99",
    "#5f8a94",
    "#6b8f74",
    "#a8865c",
    "#a06a62",
    "#7d739a",
    "#9c7089",
    "#5e8a84",
    "#7c7c7c",
]


class ThemeManager:
    def __init__(self, typography: Typography):
        self.typography = typography

    def apply_main_ttk_theme(self, root, style: ttk.Style | None = None, palette: Palette = MAIN_PALETTE):
        style = style or ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=palette.bg, foreground=palette.text_primary, bordercolor=palette.border)
        style.configure("TFrame", background=palette.bg)
        style.configure("App.TFrame", background=palette.bg)
        style.configure("Surface.TFrame", background=palette.surface)
        style.configure(
            "Card.TFrame",
            background=palette.surface,
            borderwidth=1,
            relief="flat",
            bordercolor=palette.border_soft,
            lightcolor=palette.border_soft,
            darkcolor=palette.border_soft,
        )
        style.configure("TLabel", background=palette.bg, foreground=palette.text_primary, font=self.typography.body)
        style.configure("Muted.TLabel", background=palette.bg, foreground=palette.text_muted, font=self.typography.body)
        style.configure("Title.TLabel", background=palette.bg, foreground=palette.text_primary, font=self.typography.title)
        style.configure("SectionTitle.TLabel", background=palette.bg, foreground=palette.text_primary, font=self.typography.section)
        style.configure(
            "TLabelframe",
            background=palette.bg,
            foreground=palette.text_primary,
            borderwidth=1,
            relief="flat",
            bordercolor=palette.border_soft,
            lightcolor=palette.border_soft,
            darkcolor=palette.border_soft,
        )
        style.configure("TLabelframe.Label", background=palette.bg, foreground=palette.text_primary, font=self.typography.section)
        # 标签页：去掉 clam 默认的立体边框；选中靠「白底 + 深字」与灰底 tab 栏区分
        style.configure(
            "TNotebook",
            background=palette.surface_alt,
            borderwidth=0,
            tabmargins=(12, 6, 12, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=palette.surface_alt,
            foreground=palette.text_secondary,
            padding=(14, 8),
            font=self.typography.body,
            borderwidth=0,
            bordercolor=palette.surface_alt,
            lightcolor=palette.surface_alt,
            darkcolor=palette.surface_alt,
            focuscolor=palette.surface_alt,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", palette.bg), ("active", palette.notebook_hover)],
            foreground=[("selected", palette.text_primary), ("active", palette.text_primary)],
            bordercolor=[("selected", palette.bg)],
            lightcolor=[("selected", palette.bg)],
            darkcolor=[("selected", palette.bg)],
        )
        style.configure(
            "Card.TLabelframe",
            background=palette.surface,
            borderwidth=1,
            relief="flat",
            bordercolor=palette.border_soft,
            lightcolor=palette.border_soft,
            darkcolor=palette.border_soft,
        )
        style.configure("Card.TLabelframe.Label", background=palette.surface, foreground=palette.text_primary, font=self.typography.section)
        style.configure(
            "TButton",
            background=palette.surface_alt,
            foreground=palette.text_primary,
            font=self.typography.body,
            borderwidth=0,
            relief="flat",
            focusthickness=0,
            focuscolor=palette.surface_alt,
            padding=(12, 6),
        )
        style.map(
            "TButton",
            background=[("active", palette.button_hover), ("pressed", palette.button_pressed)],
            foreground=[("disabled", palette.text_muted)],
        )
        style.configure(
            "TEntry",
            fieldbackground=palette.input_bg,
            foreground=palette.text_primary,
            bordercolor=palette.input_border,
            lightcolor=palette.input_border,
            darkcolor=palette.input_border,
            insertcolor=palette.text_primary,
            borderwidth=1,
            padding=(10, 6),
        )
        style.configure(
            "TCombobox",
            fieldbackground=palette.input_bg,
            background=palette.input_bg,
            foreground=palette.text_primary,
            bordercolor=palette.input_border,
            lightcolor=palette.input_border,
            darkcolor=palette.input_border,
            borderwidth=1,
            padding=(8, 5),
            arrowsize=14,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette.input_bg)],
            background=[("readonly", palette.input_bg)],
            foreground=[("readonly", palette.text_primary)],
            selectbackground=[("readonly", palette.input_bg)],
            selectforeground=[("readonly", palette.text_primary)],
            arrowcolor=[("readonly", palette.text_primary)],
        )
        style.configure(
            "Treeview",
            background=palette.surface,
            fieldbackground=palette.surface,
            foreground=palette.text_primary,
            font=self.typography.body,
            rowheight=28,
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "Treeview.Heading",
            background=palette.surface_alt,
            foreground=palette.text_muted,
            font=self.typography.badge,
            borderwidth=0,
            relief="flat",
            padding=(8, 9),
        )
        style.map(
            "Treeview",
            background=[("selected", palette.sidebar_active)],
            foreground=[("selected", palette.text_primary)],
        )
        style.map("Treeview.Heading", background=[("active", palette.surface)])
        # 工具栏按钮：浅底、无边框，悬停才加深（对齐克制的按钮观感）
        style.configure(
            "Quiet.TButton",
            background=palette.surface_alt,
            foreground=palette.text_secondary,
            borderwidth=0,
            relief="flat",
            focusthickness=0,
            focuscolor=palette.surface_alt,
            padding=(12, 6),
            font=self.typography.body,
        )
        style.map(
            "Quiet.TButton",
            background=[("active", palette.button_hover), ("pressed", palette.button_pressed)],
            foreground=[("active", palette.text_primary)],
        )
        style.configure(
            "Primary.TButton",
            background=palette.accent,
            foreground=palette.accent_text,
            borderwidth=0,
            relief="flat",
            focusthickness=0,
            focuscolor=palette.accent,
            padding=(12, 6),
            font=self.typography.body,
        )
        style.map(
            "Primary.TButton",
            background=[("active", palette.accent_hover), ("pressed", "#000000")],
            foreground=[("active", palette.accent_text), ("pressed", palette.accent_text)],
        )
        return style

    def apply_admin_ttk_theme(
        self,
        style: ttk.Style,
        *,
        palette: Palette = ADMIN_TOOL_PALETTE,
        title_size: int = 22,
        section_size: int = 12,
        topbar_bg: str | None = None,
        include_notebook: bool = True,
        include_status: bool = True,
        include_app_label: bool = True,
        include_app_muted: bool = True,
        include_card_labelframe: bool = True,
        include_card_frame: bool = True,
        include_card_inset: bool = False,
    ):
        topbar_bg = topbar_bg or palette.surface
        style.configure(".", background=palette.surface, foreground=palette.text_primary, bordercolor=palette.border)
        style.configure("TFrame", background=palette.surface)
        style.configure("App.TFrame", background=palette.bg)
        style.configure("Surface.TFrame", background=palette.surface)
        style.configure("Topbar.TFrame", background=topbar_bg)
        style.configure("TLabel", background=palette.surface, foreground=palette.text_primary, font=self.typography.body)
        if include_app_label:
            style.configure("App.TLabel", background=palette.bg, foreground=palette.text_primary, font=self.typography.body)
        style.configure("Muted.TLabel", background=palette.surface, foreground=palette.text_secondary, font=self.typography.body)
        if include_app_muted:
            style.configure("AppMuted.TLabel", background=palette.bg, foreground=palette.text_secondary, font=self.typography.body)
        style.configure("Title.TLabel", background=palette.surface, foreground=palette.text_primary, font=("Microsoft YaHei UI", title_size, "bold"))
        style.configure("SectionTitle.TLabel", background=palette.surface, foreground=palette.text_primary, font=("Microsoft YaHei UI", section_size, "bold"))
        style.configure("Topbar.TLabel", background=topbar_bg, foreground=palette.accent_text if topbar_bg == palette.accent else palette.text_primary, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TopbarMuted.TLabel", background=topbar_bg, foreground=palette.text_secondary, font=self.typography.body)
        if include_status:
            style.configure("Status.TLabel", background=palette.surface, foreground=palette.status, font=("Microsoft YaHei UI", 10, "bold"))

        if include_card_labelframe:
            style.configure(
                "Card.TLabelframe",
                background=palette.surface,
                borderwidth=1,
                relief="flat",
                bordercolor=palette.border_soft,
                lightcolor=palette.border_soft,
                darkcolor=palette.border_soft,
            )
            style.configure("Card.TLabelframe.Label", background=palette.surface, foreground=palette.text_primary, font=self.typography.section)

        if include_card_frame:
            style.configure(
                "Card.TFrame",
                background=palette.surface,
                borderwidth=1,
                relief="flat",
                bordercolor=palette.border_soft,
                lightcolor=palette.border_soft,
                darkcolor=palette.border_soft,
            )

        if include_card_inset:
            style.configure(
                "CardInset.TFrame",
                background=palette.surface,
                borderwidth=1,
                relief="flat",
                bordercolor=palette.border_soft,
                lightcolor=palette.border_soft,
                darkcolor=palette.border_soft,
            )

        style.configure(
            "TButton",
            background=palette.button_bg,
            foreground=palette.text_primary,
            borderwidth=1,
            relief="solid",
            focusthickness=0,
            focuscolor=palette.button_bg,
            padding=(16, 9),
            font=self.typography.body,
        )
        style.map(
            "TButton",
            background=[("active", palette.button_hover), ("pressed", palette.button_pressed)],
            foreground=[("disabled", palette.text_muted)],
        )
        style.configure(
            "Primary.TButton",
            background=palette.accent,
            foreground=palette.accent_text,
            borderwidth=0,
            padding=(18, 10),
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", palette.accent_hover), ("pressed", "#111111")],
            foreground=[("active", palette.accent_text), ("pressed", palette.accent_text)],
        )
        style.configure(
            "TEntry",
            fieldbackground=palette.input_bg,
            foreground=palette.text_primary,
            bordercolor=palette.input_border,
            lightcolor=palette.input_border,
            darkcolor=palette.input_border,
            insertcolor=palette.text_primary,
            padding=(10, 7),
        )
        style.configure(
            "TCombobox",
            fieldbackground=palette.input_bg,
            background=palette.input_bg,
            foreground=palette.text_primary,
            bordercolor=palette.input_border,
            lightcolor=palette.input_border,
            darkcolor=palette.input_border,
            padding=(8, 6),
            arrowsize=14,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette.input_bg)],
            background=[("readonly", palette.input_bg)],
            foreground=[("readonly", palette.text_primary)],
            selectbackground=[("readonly", palette.input_bg)],
            selectforeground=[("readonly", palette.text_primary)],
            arrowcolor=[("readonly", palette.text_primary)],
        )
        style.configure("TRadiobutton", background=palette.surface, foreground=palette.text_primary, font=self.typography.body)
        style.configure(
            "Treeview",
            background=palette.surface,
            fieldbackground=palette.surface,
            foreground=palette.text_primary,
            font=self.typography.body,
            rowheight=28,
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "Treeview.Heading",
            background=palette.surface_alt,
            foreground=palette.text_muted,
            font=self.typography.badge,
            borderwidth=0,
            relief="flat",
            padding=(8, 9),
        )
        style.map(
            "Treeview",
            background=[("selected", palette.sidebar_active)],
            foreground=[("selected", palette.text_primary)],
        )

        if include_notebook:
            style.configure("TNotebook", background=palette.bg, borderwidth=0, tabmargins=(0, 0, 0, 0))
            style.configure(
                "TNotebook.Tab",
                background=palette.notebook_tab,
                foreground=palette.text_secondary,
                padding=(14, 8),
                font=("Microsoft YaHei UI", 10, "bold"),
                borderwidth=0,
            )
            style.map(
                "TNotebook.Tab",
                background=[("selected", palette.surface), ("active", palette.notebook_hover)],
                foreground=[("selected", palette.text_primary), ("active", palette.text_primary)],
            )

        return style

    def configure_toolbox_button_style(self, style: ttk.Style, palette: Palette = TOOLBOX_PALETTE):
        style.configure("Accent.TButton", background=palette.surface_alt, foreground=palette.accent)
        style.map("Accent.TButton", background=[("active", palette.button_hover), ("!disabled", palette.surface_alt)])

        # 工具栏动作：默认「看不见按钮、只看得到文字」，悬停才浮出一层浅底。
        # 一排实心灰底按钮压在白色页面上又重又硬，还抢搜索框的视觉焦点；
        # 这与顶栏动作的处理保持一致。clam 会画 1px 描边，所以把
        # bordercolor / lightcolor / darkcolor 一起设成页面底色才能真正抹平。
        style.configure(
            "Toolbar.TButton",
            background=palette.bg,
            foreground=palette.text_secondary,
            borderwidth=0,
            relief="flat",
            focusthickness=0,
            focuscolor=palette.bg,
            bordercolor=palette.bg,
            lightcolor=palette.bg,
            darkcolor=palette.bg,
            padding=(12, 6),
            font=self.typography.body,
        )
        style.map(
            "Toolbar.TButton",
            background=[("active", palette.surface_alt),
                        ("pressed", palette.button_pressed)],
            foreground=[("active", palette.text_primary),
                        ("pressed", palette.text_primary)],
        )


TYPOGRAPHY = Typography()
THEME = ThemeManager(TYPOGRAPHY)
