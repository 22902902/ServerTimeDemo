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


# 统一内容内边距：24px 为外壳与页面共用的左右 gutter
GUTTER = 24


def create_page_toolbar(parent, *, padding=(GUTTER, 20, GUTTER, 10)):
    toolbar = ttk.Frame(parent, padding=padding)
    toolbar.pack(fill="x")
    return toolbar


def add_toolbar_buttons(toolbar, items, *, side="left", padx=4, style="Quiet.TButton"):
    """批量生成工具栏按钮。

    默认使用 Quiet.TButton（浅底、无边框），与整体克制风格一致；
    需要强调的主操作可传 style="Primary.TButton"。
    items 支持 (text, command) 或 (text, command, style) 两种写法。
    """
    buttons = []
    for item in items:
        text, command = item[0], item[1]
        item_style = item[2] if len(item) > 2 else style
        button = ttk.Button(toolbar, text=text, command=command, style=item_style)
        button.pack(side=side, padx=padx)
        buttons.append(button)
    return buttons


def create_summary_card(parent, title: str, textvariable, *, wraplength: int = 920, padding=(14, 10)):
    card = create_ttk_card(parent, title, padding=padding)
    card.pack(fill="x", padx=GUTTER, pady=(0, 12))
    label = ttk.Label(card, textvariable=textvariable, style="Muted.TLabel", justify="left", wraplength=wraplength)
    label.pack(anchor="w")
    return card, label


def create_content_frame(parent, *, padding=(GUTTER, 0, GUTTER, 16)):
    frame = ttk.Frame(parent, padding=padding)
    frame.pack(fill="both", expand=True)
    return frame


def create_two_pane_layout(parent, *, left_width: int, right_pad=(GUTTER, 0), padding=(GUTTER, 0, GUTTER, 16)):
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
    frame.pack(side="right", fill="y", padx=(GUTTER, 0))
    frame.configure(width=width)
    frame.pack_propagate(False)
    return frame


def create_status_bar(parent, textvariable, *, padding=(GUTTER, 12)):
    bar = ttk.Frame(parent, padding=padding)
    bar.pack(fill="x")
    ttk.Label(bar, textvariable=textvariable, anchor="w").pack(fill="x")
    return bar
