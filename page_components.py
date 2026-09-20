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

from ui_components import create_flat_menu, create_ttk_card


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

    注意：一行塞太多按钮会互相挤。pack 放不下的控件会被 Tk **直接不映射**
    ——界面上完全不存在，不是「被裁掉一点」。动作超过 6~7 个时，用
    create_menu_button 把次要动作收进下拉，别指望它自己排得下。
    """
    buttons = []
    for item in items:
        text, command = item[0], item[1]
        item_style = item[2] if len(item) > 2 else style
        # width=0 让按钮按文字自适应：ttk 默认宽度非 0，会把所有按钮撑成同宽，
        # 在窄栏里挤掉末尾按钮
        button = ttk.Button(toolbar, text=text, command=command, style=item_style, width=0)
        button.pack(side=side, padx=padx)
        buttons.append(button)
    return buttons


def create_menu_button(toolbar, text, actions, *, side="left", padx=4, style="Quiet.TButton"):
    """把一组动作收进下拉菜单的按钮，用于动作多于一行放不下的工具栏。

    actions 每项为 (标题, 回调)，分隔线写 "---"。
    菜单对象挂在返回值的 .menu 上：必须留引用，否则被 GC 回收后点不开。
    """
    button = ttk.Button(toolbar, text=f"{text} ▾", style=style, width=0)
    button.pack(side=side, padx=padx)
    menu = create_flat_menu(button, actions)

    def popup():
        try:
            menu.tk_popup(button.winfo_rootx(),
                          button.winfo_rooty() + button.winfo_height() + 2)
        finally:
            menu.grab_release()

    button.configure(command=popup)
    button.menu = menu
    return button


def create_summary_card(parent, title: str, textvariable, *, wraplength: int = 920, padding=(14, 10)):
    card = create_ttk_card(parent, title, padding=padding)
    card.pack(fill="x", padx=GUTTER, pady=(0, 12))
    label = ttk.Label(card, textvariable=textvariable, style="Muted.TLabel", justify="left", wraplength=wraplength)
    label.pack(anchor="w")
    return card, label


def create_content_frame(parent, *, padding=(GUTTER, 0, GUTTER, 16)):
    """可伸缩内容区。

    这里必须 pack_propagate(False)，把「自己声明的尺寸」与子控件解耦。
    否则子控件（尤其 Treeview 这类请求尺寸巨大的）会吃掉整条 pack 链的
    全部剩余空间，夹在它后面 pack 的固定高度控件（状态栏、页脚滚动条）
    只分到 0 像素、被 Tk 直接不映射 —— 代码写了，界面上根本不存在。
    """
    frame = ttk.Frame(parent, padding=padding)
    frame.configure(width=1, height=1)
    frame.pack(fill="both", expand=True)
    frame.pack_propagate(False)
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
    """右侧预览栏（固定宽度）。

    顺序有讲究：同一容器里左侧那个 fill=both/expand=True 的表格卡片会把
    右侧挤成 0 宽、整个不显示。要建「表格 + 预览」，用
    create_table_preview_split 一次建好两边，别先 pack 左侧再调这个函数。
    """
    frame = create_ttk_card(parent, title, padding=padding)
    frame.pack(side="right", fill="y", padx=(GUTTER, 0))
    frame.configure(width=width)
    frame.pack_propagate(False)
    return frame


def create_table_preview_split(parent, *, table_title, preview_title,
                               preview_width: int = 300,
                               table_padding=(10, 10), preview_padding=(16, 12),
                               padding=(GUTTER, 0, GUTTER, 16)):
    """左侧表格卡片 + 右侧预览栏，一次建好，返回 (table_card, preview_card)。

    先 pack 右侧（固定宽度）再 pack 左侧（fill/expand）。反过来的话，
    左侧 Treeview 卡片的请求宽度是各列之和（本项目账号中心实测 1674px），
    会把右侧整个挤成 0 宽。
    """
    content = ttk.Frame(parent, padding=padding)
    content.configure(width=1, height=1)
    content.pack(fill="both", expand=True)
    content.pack_propagate(False)

    preview_card = create_ttk_card(content, preview_title, padding=preview_padding)
    preview_card.configure(width=preview_width)
    preview_card.pack(side="right", fill="y", padx=(GUTTER, 0))
    preview_card.pack_propagate(False)

    table_card = create_ttk_card(content, table_title, padding=table_padding)
    table_card.pack(side="left", fill="both", expand=True)
    return table_card, preview_card


def pack_tree_with_scrollbars(card, tree, *, horizontal: bool = True, pady=0):
    """把 Treeview 与滚动条装进卡片，返回 (v_scroll, h_scroll)。

    顺序必须是「先滚动条、后表格」：Treeview 的请求宽度 = 各列宽度之和，
    先 pack 它会把两个滚动条双双挤出可视区（实测两个都 w=1）。
    """
    v_scroll = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
    v_scroll.pack(side="right", fill="y")
    h_scroll = None
    if horizontal:
        h_scroll = ttk.Scrollbar(card, orient="horizontal", command=tree.xview)
        h_scroll.pack(side="bottom", fill="x")
    tree.configure(yscrollcommand=v_scroll.set,
                   xscrollcommand=h_scroll.set if h_scroll else "")
    tree.pack(side="left", fill="both", expand=True, pady=pady)
    return v_scroll, h_scroll


def create_status_bar(parent, textvariable, *, padding=(GUTTER, 12)):
    """底部状态栏。

    用 side="bottom"：这样它在 build() 里最后调用（读起来最自然）也能贴在底部。
    """
    bar = ttk.Frame(parent, padding=padding)
    bar.pack(side="bottom", fill="x")
    ttk.Label(bar, textvariable=textvariable, anchor="w",
              style="Muted.TLabel").pack(fill="x")
    return bar
