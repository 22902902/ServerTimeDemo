# -*- coding: utf-8 -*-
"""统一 UI 组件层。

提供黑白扁平化风格下常用的：
1. 顶部动作按钮
2. 扁平卡片/分组区块
3. 状态文本与指标卡片
"""

import tkinter as tk
from tkinter import ttk

from ui_theme import MAIN_PALETTE, TYPOGRAPHY


def create_flat_action_button(parent, text: str, command, *, side: str | None = None, padx: int = 4):
    """★ 统一风格：与账号中心/后台接口测试的工具栏按钮保持一致（ttk.Button）。"""
    button = ttk.Button(parent, text=text, command=command)
    if side:
        button.pack(side=side, padx=padx)
    return button


def create_section_frame(parent, title: str):
    frame = tk.LabelFrame(
        parent,
        text=title,
        bg=MAIN_PALETTE.bg,
        fg=MAIN_PALETTE.text_primary,
        padx=14,
        pady=12,
        bd=1,
        relief="solid",
    )
    return frame


def create_info_label(
    parent,
    *,
    textvariable=None,
    text: str | None = None,
    tone: str = "muted",
    wraplength: int = 920,
    bg: str | None = None,
):
    color_map = {
        "primary": MAIN_PALETTE.text_primary,
        "muted": MAIN_PALETTE.text_muted,
        "secondary": MAIN_PALETTE.text_secondary,
        "link": MAIN_PALETTE.link,
        "success": MAIN_PALETTE.success,
        "warn": MAIN_PALETTE.warn,
        "danger": MAIN_PALETTE.danger,
    }
    label = tk.Label(
        parent,
        text=text or "",
        textvariable=textvariable,
        bg=bg or MAIN_PALETTE.bg,
        fg=color_map.get(tone, MAIN_PALETTE.text_muted),
        wraplength=wraplength,
        justify="left",
    )
    return label


def create_metric_card(parent, title: str, value_var, desc: str):
    card = create_section_frame(parent, title)
    tk.Label(
        card,
        textvariable=value_var,
        bg=MAIN_PALETTE.bg,
        fg=MAIN_PALETTE.text_primary,
        font=TYPOGRAPHY.metric,
    ).pack(anchor="w")
    create_info_label(card, text=desc, tone="muted", wraplength=210).pack(anchor="w", pady=6)
    return card


def create_ttk_card(parent, title: str | None = None, *, padding=(12, 10)):
    if title:
        return ttk.LabelFrame(parent, text=title, padding=padding, style="Card.TLabelframe")
    return ttk.Frame(parent, padding=padding, style="Card.TFrame")


def create_ttk_section_header(parent, text: str):
    return ttk.Label(parent, text=text, style="SectionTitle.TLabel")
