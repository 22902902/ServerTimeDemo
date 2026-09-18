# -*- coding: utf-8 -*-
"""全局 UI 主题定义。

目标：
1. 为主程序、系统工具箱、后台工具提供统一的字体与颜色 token
2. 通过 ThemeManager 集中应用 ttk 样式，降低样式分散维护成本
3. 以黑白为基底，保留少量功能色用于状态提示
"""

from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True)
class Typography:
    title: tuple = ("Microsoft YaHei UI", 14, "bold")
    subtitle: tuple = ("Microsoft YaHei UI", 12, "bold")
    section: tuple = ("Microsoft YaHei UI", 10, "bold")
    body: tuple = ("Microsoft YaHei UI", 10)
    metric: tuple = ("Microsoft YaHei UI", 16, "bold")
    badge: tuple = ("Microsoft YaHei UI", 9, "bold")
    hero: tuple = ("Microsoft YaHei UI", 22, "bold")


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


MAIN_PALETTE = Palette(
    bg="#ffffff",
    surface="#ffffff",
    surface_alt="#f6f6f6",
    text_primary="#111111",
    text_secondary="#444444",
    text_muted="#6b6b6b",
    border="#d9d9d9",
    border_soft="#cfcfcf",
    button_bg="#f4f4f4",
    button_hover="#ebebeb",
    button_pressed="#dfdfdf",
    accent="#111111",
    accent_hover="#2a2a2a",
    accent_text="#ffffff",
    input_bg="#fafafa",
    input_border="#d0d0d0",
    input_focus="#9b9b9b",
    badge_bg="#eeeeee",
    link="#1f4d8b",
    success="#2f6b2f",
    warn="#8a5a00",
    danger="#8b1e1e",
    status="#2457a6",
    notebook_tab="#ececec",
    notebook_hover="#f2f2f2",
)

TOOLBOX_PALETTE = Palette(
    bg="#ffffff",
    surface="#ffffff",
    surface_alt="#f5f5f5",
    text_primary="#111111",
    text_secondary="#666666",
    text_muted="#7a7a7a",
    border="#111111",
    border_soft="#9f9f9f",
    button_bg="#ffffff",
    button_hover="#f0f0f0",
    button_pressed="#e6e6e6",
    accent="#111111",
    accent_hover="#2b2b2b",
    accent_text="#ffffff",
    input_bg="#ffffff",
    input_border="#9f9f9f",
    input_focus="#111111",
    badge_bg="#f0f0f0",
    link="#111111",
    success="#1f5f3b",
    warn="#7a5a00",
    danger="#7a1f1f",
    status="#111111",
    notebook_tab="#ececec",
    notebook_hover="#f2f2f2",
)

ADMIN_TOOL_PALETTE = Palette(
    bg="#ffffff",
    surface="#ffffff",
    surface_alt="#f7f7f7",
    text_primary="#111111",
    text_secondary="#666666",
    text_muted="#8a8a8a",
    border="#dfdfdf",
    border_soft="#e7e7e7",
    button_bg="#f4f4f4",
    button_hover="#eaeaea",
    button_pressed="#dddddd",
    accent="#1d1d1d",
    accent_hover="#333333",
    accent_text="#ffffff",
    input_bg="#f7f7f7",
    input_border="#dfdfdf",
    input_focus="#b5b5b5",
    badge_bg="#f0f0f0",
    link="#2457a6",
    success="#2f6b2f",
    warn="#8a5a00",
    danger="#8b1e1e",
    status="#2457a6",
    notebook_tab="#e8e8e8",
    notebook_hover="#f0f0f0",
)

PACKAGE_ACCENT_COLORS = [
    "#2563eb",
    "#0ea5e9",
    "#10b981",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#ec4899",
    "#14b8a6",
    "#6b7280",
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
            relief="solid",
            bordercolor=palette.border,
            lightcolor=palette.border,
            darkcolor=palette.border,
        )
        style.configure("TLabel", background=palette.bg, foreground=palette.text_primary, font=self.typography.body)
        style.configure("Muted.TLabel", background=palette.bg, foreground=palette.text_muted, font=self.typography.body)
        style.configure("Title.TLabel", background=palette.bg, foreground=palette.text_primary, font=self.typography.title)
        style.configure("SectionTitle.TLabel", background=palette.bg, foreground=palette.text_primary, font=self.typography.section)
        style.configure("TLabelframe", background=palette.bg, foreground=palette.text_primary)
        style.configure("TLabelframe.Label", background=palette.bg, foreground=palette.text_primary, font=self.typography.section)
        style.configure(
            "Card.TLabelframe",
            background=palette.surface,
            borderwidth=1,
            relief="solid",
            bordercolor=palette.border,
            lightcolor=palette.border,
            darkcolor=palette.border,
        )
        style.configure("Card.TLabelframe.Label", background=palette.surface, foreground=palette.text_primary, font=self.typography.section)
        style.configure(
            "TButton",
            background=palette.button_bg,
            foreground=palette.text_primary,
            font=self.typography.body,
            borderwidth=1,
            relief="solid",
            padding=(10, 5),
        )
        style.map(
            "TButton",
            background=[("active", palette.button_hover), ("pressed", palette.button_pressed)],
            relief=[("pressed", "sunken")],
        )
        style.configure("TEntry", fieldbackground=palette.surface, foreground=palette.text_primary, padding=4)
        style.configure("TCombobox", fieldbackground=palette.surface, foreground=palette.text_primary, padding=4)
        style.configure("Treeview", background=palette.surface, fieldbackground=palette.surface, foreground=palette.text_primary, font=self.typography.body)
        style.configure("Treeview.Heading", background=palette.surface_alt, foreground=palette.text_primary, font=self.typography.section)
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
                relief="solid",
                bordercolor=palette.border,
                lightcolor=palette.border,
                darkcolor=palette.border,
            )
            style.configure("Card.TLabelframe.Label", background=palette.surface, foreground=palette.text_primary, font=self.typography.section)

        if include_card_frame:
            style.configure(
                "Card.TFrame",
                background=palette.surface,
                borderwidth=1,
                relief="solid",
                bordercolor=palette.border,
                lightcolor=palette.border,
                darkcolor=palette.border,
            )

        if include_card_inset:
            style.configure(
                "CardInset.TFrame",
                background=palette.surface,
                borderwidth=1,
                relief="solid",
                bordercolor=palette.border,
                lightcolor=palette.border,
                darkcolor=palette.border,
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
        style.configure("Treeview", background=palette.surface, fieldbackground=palette.surface, foreground=palette.text_primary, font=self.typography.body)
        style.configure("Treeview.Heading", background=palette.surface_alt, foreground=palette.text_primary, font=self.typography.section)

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


TYPOGRAPHY = Typography()
THEME = ThemeManager(TYPOGRAPHY)
