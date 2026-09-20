# -*- coding: utf-8 -*-
"""弹窗表单统一样式。

让表单型弹窗的标签、输入框、勾选框、单选框尽量接近登录/改密窗口的视觉风格，
避免系统默认 ttk 在不同弹窗里出现白底块、灰底块混杂的问题。
"""

import os
import sys
import tkinter as tk
from tkinter import ttk

from ui_theme import MAIN_PALETTE, Palette


_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def apply_window_icon(window) -> None:
    """给 Toplevel 设上应用图标。

    不设的话弹窗标题栏是 Tk 默认的羽毛图标，跟主窗口的品牌标记对不上。
    图标优先取代码里内嵌的那份 base64（打包成 exe 后也在），
    失败再退回外部 app.ico；两者都失败就静默放过 —— 图标缺失不该拦住弹窗。
    """
    for loader in (
        lambda: __import__(
            "embedded_admin_tools.services.app_icon_service",
            fromlist=["save_temp_app_icon"],
        ).save_temp_app_icon(),
        lambda: os.path.join(getattr(sys, "_MEIPASS", _APP_DIR), "app.ico"),
    ):
        try:
            icon_path = loader()
            if icon_path:
                window.iconbitmap(str(icon_path))
                return
        except Exception:
            continue


def apply_dialog_form_style(master, palette: Palette = MAIN_PALETTE, *, style_prefix: str = "DialogForm") -> str:
    """给弹窗容器应用统一底色，并注册 Combobox / ttk 容器样式。"""
    try:
        master.configure(bg=palette.bg)
    except Exception:
        pass

    if isinstance(master, (tk.Tk, tk.Toplevel)):
        apply_window_icon(master)

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
    # 单行输入框与下拉框同款，否则同一行里一个浅灰、一个白，看着像两套控件
    style.configure(
        f"{style_prefix}.TEntry",
        fieldbackground=palette.input_bg,
        background=palette.input_bg,
        foreground=palette.text_primary,
        bordercolor=palette.input_border,
        lightcolor=palette.input_border,
        darkcolor=palette.input_border,
        insertcolor=palette.text_primary,
        padding=(8, 6),
    )
    style.map(
        f"{style_prefix}.TEntry",
        fieldbackground=[("focus", palette.surface)],
        bordercolor=[("focus", palette.input_focus)],
        lightcolor=[("focus", palette.input_focus)],
        darkcolor=[("focus", palette.input_focus)],
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

