# -*- coding: utf-8 -*-
"""页面级组件层。

用于抽离 main.py 中重复出现的页面骨架：
1. 顶部工具栏
2. 摘要卡片
3. 左右分栏布局
4. 预览侧栏
"""

from __future__ import annotations

from tkinter import ttk

from ui_components import create_ttk_card


def create_page_toolbar(parent, *, padding=(10, 10, 10, 8)):
    toolbar = ttk.Frame(parent, padding=padding)
    toolbar.pack(fill="x")
    return toolbar


def add_toolbar_buttons(toolbar, items, *, side="left", padx=4):
    buttons = []
    for text, command in items:
        button = ttk.Button(toolbar, text=text, command=command)
        button.pack(side=side, padx=padx)
        buttons.append(button)
    return buttons


def create_summary_card(parent, title: str, textvariable, *, wraplength: int = 920, padding=(14, 10)):
    card = create_ttk_card(parent, title, padding=padding)
    card.pack(fill="x", padx=10, pady=(0, 8))
    label = ttk.Label(card, textvariable=textvariable, style="Muted.TLabel", justify="left", wraplength=wraplength)
    label.pack(anchor="w")
    return card, label


def create_content_frame(parent, *, padding=(10, 0, 10, 10)):
    frame = ttk.Frame(parent, padding=padding)
    frame.pack(fill="both", expand=True)
    return frame


def create_two_pane_layout(parent, *, left_width: int, right_pad=(10, 0), padding=(10, 0, 10, 10)):
    content = ttk.Frame(parent, padding=padding)
    content.pack(fill="both", expand=True)

    left = ttk.Frame(content, width=left_width)
    left.pack(side="left", fill="y")
    left.pack_propagate(False)

    right = ttk.Frame(content)
    right.pack(side="left", fill="both", expand=True, padx=right_pad)
    return content, left, right


def create_preview_sidebar(parent, title: str, *, width: int = 300, padding=(10, 10)):
    frame = create_ttk_card(parent, title, padding=padding)
    frame.pack(side="right", fill="y", padx=(10, 0))
    frame.configure(width=width)
    frame.pack_propagate(False)
    return frame


def create_status_bar(parent, textvariable, *, padding=10):
    bar = ttk.Frame(parent, padding=padding)
    bar.pack(fill="x")
    ttk.Label(bar, textvariable=textvariable, anchor="w").pack(fill="x")
    return bar
