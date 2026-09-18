# -*- coding: utf-8 -*-
"""弹窗表单统一样式。

让表单型弹窗的标签、输入框、勾选框、单选框尽量接近登录/改密窗口的视觉风格，
避免系统默认 ttk 在不同弹窗里出现白底块、灰底块混杂的问题。
"""

import tkinter as tk
from tkinter import ttk

from ui_theme import MAIN_PALETTE, Palette


def apply_dialog_form_style(master, palette: Palette = MAIN_PALETTE, *, style_prefix: str = "DialogForm") -> str:
    """给弹窗容器应用统一底色，并注册 Combobox / ttk 容器样式。"""
    try:
        master.configure(bg=palette.bg)
    except Exception:
        pass

    style = ttk.Style(master)
    style.configure(f"{style_prefix}.TFrame", background=palette.bg)
    style.configure(f"{style_prefix}.TLabel", background=palette.bg, foreground=palette.text_primary)
    style.configure(f"{style_prefix}Muted.TLabel", background=palette.bg, foreground=palette.text_muted)
    style.configure(f"{style_prefix}.TLabelframe", background=palette.bg, foreground=palette.text_primary)
    style.configure(f"{style_prefix}.TLabelframe.Label", background=palette.bg, foreground=palette.text_primary)
    style.configure(
        f"{style_prefix}.TCombobox",
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
        f"{style_prefix}.TCombobox",
        fieldbackground=[("readonly", palette.input_bg)],
        background=[("readonly", palette.input_bg)],
        foreground=[("readonly", palette.text_primary)],
        selectbackground=[("readonly", palette.input_bg)],
        selectforeground=[("readonly", palette.text_primary)],
        arrowcolor=[("readonly", palette.text_primary)],
    )
    return style_prefix


def create_form_label(master, text: str, *, palette: Palette = MAIN_PALETTE, muted: bool = False, **kwargs):
    return tk.Label(
        master,
        text=text,
        bg=palette.bg,
        fg=palette.text_muted if muted else palette.text_primary,
        anchor="w",
        justify=kwargs.pop("justify", "left"),
        **kwargs,
    )


def create_form_frame(master, *, palette: Palette = MAIN_PALETTE, **kwargs):
    return tk.Frame(master, bg=palette.bg, **kwargs)


def create_form_entry(master, *, textvariable=None, palette: Palette = MAIN_PALETTE, show: str | None = None, **kwargs):
    return tk.Entry(
        master,
        textvariable=textvariable,
        show=show,
        bg=palette.input_bg,
        fg=palette.text_primary,
        insertbackground=palette.text_primary,
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=palette.input_border,
        highlightcolor=palette.input_focus,
        **kwargs,
    )


def create_form_checkbutton(master, *, text: str, variable, palette: Palette = MAIN_PALETTE, **kwargs):
    return tk.Checkbutton(
        master,
        text=text,
        variable=variable,
        bg=palette.bg,
        fg=palette.text_primary,
        activebackground=palette.bg,
        activeforeground=palette.text_primary,
        selectcolor=palette.bg,
        highlightthickness=0,
        anchor="w",
        justify=kwargs.pop("justify", "left"),
        **kwargs,
    )


def create_form_radiobutton(master, *, text: str, variable, value, palette: Palette = MAIN_PALETTE, **kwargs):
    return tk.Radiobutton(
        master,
        text=text,
        variable=variable,
        value=value,
        bg=palette.bg,
        fg=palette.text_primary,
        activebackground=palette.bg,
        activeforeground=palette.text_primary,
        selectcolor=palette.bg,
        highlightthickness=0,
        anchor="w",
        justify=kwargs.pop("justify", "left"),
        **kwargs,
    )

