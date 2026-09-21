# -*- coding: utf-8 -*-
"""待办模块的自绘图形资产。

为什么单独一层，而不是直接塞进 todo_page
------------------------------------------------------------------------------
Tk 的 ``tk.Canvas`` 没有抗锯齿，圆形勾选框、圆角清单图标这类带曲线的图形
直接画会明显起毛边。本模块复用 ``app_icons.Pen`` 在 8 倍超采样画布上作画再
降采样，与左侧导航图标同一套渲染管线、同一套线宽语言。

与 ``app_icons`` 的分工
------------------------------------------------------------------------------
``app_icons`` 只管**全局导航**那几枚图标；本模块管**待办模块内部**的图形。
两边都按 16×16 逻辑单位书写、都按 Tk 缩放渲染并缓存，视觉上是同一族。

三类资产
------------------------------------------------------------------------------
1. ``checkbox``  —— 圆形勾选框：未选是空心圈，选中是实心圆 + 白色对勾
2. ``tile``      —— 清单图标：填色圆角方块 + 白色图形（苹果的列表图标就是这么画的）
3. ``row_glyph`` —— 详情面板每一行的线性小图标（日期 / 时间 / 重复 / 优先级…）

颜色全部由调用方传入，同一张图按 (颜色, 尺寸, 状态) 缓存，切换状态只是换图，
不必重绘 —— 这是 tk.Canvas 方案做不到的。
"""

from __future__ import annotations

import math

from PIL import Image

from app_icons import Pen, _photo

UNITS = 16                 # 逻辑坐标空间边长（与 app_icons 一致）
SS = 8                     # 超采样倍数
WHITE = (255, 255, 255, 255)

CHECK_STROKE = 1.15        # 勾选框圈线（逻辑单位）
CHECK_RADIUS = 6.3
TILE_STROKE = 1.25         # 清单图标里白色图形的线宽
GLYPH_STROKE = 1.3         # 详情行图标线宽


# ----------------------------------------------------------------------
# 填充图元（Pen 只提供描边，填色形状在这里补齐）
# ----------------------------------------------------------------------
def _fill_ellipse(g: Pen, cx: float, cy: float, rx: float, ry: float) -> None:
    g.d.ellipse([(cx - rx) * g.u, (cy - ry) * g.u,
                 (cx + rx) * g.u, (cy + ry) * g.u], fill=g.fg)


def _fill_poly(g: Pen, pts) -> None:
    g.d.polygon([(x * g.u, y * g.u) for x, y in pts], fill=g.fg)


def _ell_arc(g: Pen, cx: float, cy: float, rx: float, ry: float,
             a0: float, a1: float) -> None:
    g.d.arc([(cx - rx) * g.u, (cy - ry) * g.u,
             (cx + rx) * g.u, (cy + ry) * g.u],
            a0, a1, fill=g.fg, width=g.w)


# ======================================================================
# 1. 圆形勾选框
# ======================================================================
def _draw_checkbox(g: Pen, checked: bool) -> None:
    if not checked:
        g.ring(8, 8, CHECK_RADIUS)
        return
    _fill_ellipse(g, 8, 8, 7.6, 7.6)
    g.fg = WHITE
    g.w = max(1, int(round(1.5 * g.u)))
    g.poly([(4.9, 8.3), (7.1, 10.6), (11.2, 5.6)])


def checkbox(px: int, color: str, checked: bool) -> Image.Image:
    """圆形勾选框。

    ``color`` 在未勾选时是圈线色（一般给 text_muted），勾选后是填充色
    （一般给所属清单的颜色 —— 这样一眼能看出这条属于哪个清单）。
    """
    g = Pen(px, color, stroke=CHECK_STROKE)
    _draw_checkbox(g, bool(checked))
    return g.image()


# ======================================================================
# 2. 清单图标（填色圆角方块 + 白色图形）
# ======================================================================
def _t_list(g: Pen) -> None:
    for y in (5.0, 8.0, 11.0):
        g.box(3.9, y - 0.55, 5.0, y + 0.55, r=0.5, fill=True)
        g.poly([(6.6, y), (12.1, y)])


def _t_check(g: Pen) -> None:
    g.poly([(4.2, 8.4), (6.9, 11.1), (11.8, 5.4)])


def _t_star(g: Pen) -> None:
    pts = []
    for i in range(10):
        r = 5.0 if i % 2 == 0 else 2.15
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((8 + r * math.cos(a), 8 + r * math.sin(a)))
    _fill_poly(g, pts)


def _t_flag(g: Pen) -> None:
    g.poly([(4.6, 3.4), (4.6, 12.6)])
    _fill_poly(g, [(5.4, 3.6), (11.9, 3.6), (9.9, 6.2), (11.9, 8.8), (5.4, 8.8)])


def _t_book(g: Pen) -> None:
    g.box(4.0, 3.8, 12.0, 12.2, r=1.3)
    g.poly([(8.0, 3.8), (8.0, 12.2)])


def _t_bag(g: Pen) -> None:
    g.box(3.6, 5.8, 12.4, 12.2, r=1.6)
    g.poly([(6.2, 5.8), (6.2, 4.3), (9.8, 4.3), (9.8, 5.8)])


def _t_key(g: Pen) -> None:
    g.ring(5.4, 6.6, 2.2)
    g.poly([(7.0, 8.2), (12.0, 12.6)])
    g.poly([(9.6, 10.4), (10.9, 9.1)])
    g.poly([(11.0, 11.7), (12.3, 10.4)])


def _t_gift(g: Pen) -> None:
    g.box(4.0, 7.2, 12.0, 12.2, r=1.0)
    g.poly([(8.0, 7.2), (8.0, 12.2)])
    g.poly([(3.2, 7.2), (12.8, 7.2)])
    _fill_poly(g, [(5.6, 4.0), (8.0, 4.0), (8.0, 6.4), (5.6, 6.4)])
    _fill_poly(g, [(8.0, 4.0), (10.4, 4.0), (10.4, 6.4), (8.0, 6.4)])


def _t_cake(g: Pen) -> None:
    g.box(3.8, 8.4, 12.2, 12.4, r=1.2)
    g.poly([(3.8, 8.4), (12.2, 8.4)])
    g.poly([(8.0, 4.2), (8.0, 6.8)])
    g.box(7.2, 3.0, 8.8, 4.4, r=0.6, fill=True)


def _t_cap(g: Pen) -> None:
    _fill_poly(g, [(3.4, 7.0), (8.0, 4.6), (12.6, 7.0), (8.0, 9.4)])
    g.poly([(5.8, 8.2), (5.8, 11.0), (10.2, 11.0), (10.2, 8.2)])


def _t_heart(g: Pen) -> None:
    _fill_ellipse(g, 6.0, 6.6, 2.4, 2.3)
    _fill_ellipse(g, 10.0, 6.6, 2.4, 2.3)
    _fill_poly(g, [(3.9, 7.2), (12.1, 7.2), (8.0, 12.4)])


def _t_leaf(g: Pen) -> None:
    # 叶形：一条长弧 + 一条短弧对扣出尖头，再补中脉
    _ell_arc(g, 8.0, 8.0, 4.8, 5.4, 118, 300)
    _ell_arc(g, 8.9, 7.1, 4.6, 5.2, 298, 118)
    g.poly([(5.6, 11.4), (10.4, 4.6)])


def _t_pill(g: Pen) -> None:
    g.box(2.8, 6.2, 13.2, 9.8, r=1.8)
    g.poly([(8.0, 6.2), (8.0, 9.8)])


def _t_dumbbell(g: Pen) -> None:
    g.poly([(5.2, 8.0), (10.8, 8.0)])
    g.box(3.2, 5.6, 4.6, 10.4, r=0.7, fill=True)
    g.box(11.4, 5.6, 12.8, 10.4, r=0.7, fill=True)


def _t_cart(g: Pen) -> None:
    g.poly([(3.0, 4.2), (4.8, 4.2), (6.4, 10.2), (12.0, 10.2)])
    g.poly([(5.2, 6.2), (12.6, 6.2), (11.7, 9.0)])
    _fill_ellipse(g, 7.0, 12.0, 1.1, 1.1)
    _fill_ellipse(g, 11.0, 12.0, 1.1, 1.1)


def _t_house(g: Pen) -> None:
    g.poly([(3.6, 8.2), (8.0, 4.2), (12.4, 8.2)])
    g.box(5.0, 8.2, 11.0, 12.2, r=0.8)


def _t_music(g: Pen) -> None:
    g.poly([(9.4, 4.2), (9.4, 11.2)])
    g.poly([(9.4, 4.2), (12.4, 5.2), (12.4, 7.8)])
    _fill_ellipse(g, 7.8, 11.2, 1.8, 1.4)


def _t_person(g: Pen) -> None:
    g.ring(8.0, 6.2, 2.4)
    _ell_arc(g, 8.0, 14.0, 4.8, 4.6, 190, 350)


def _t_phone(g: Pen) -> None:
    g.box(5.2, 3.2, 10.8, 12.8, r=1.7)
    g.poly([(7.2, 11.2), (8.8, 11.2)])


def _t_sun(g: Pen) -> None:
    g.ring(8, 8, 3.0)
    for i in range(8):
        a = math.radians(i * 45)
        x0, y0 = 8 + 4.3 * math.cos(a), 8 + 4.3 * math.sin(a)
        x1, y1 = 8 + 6.1 * math.cos(a), 8 + 6.1 * math.sin(a)
        g.poly([(x0, y0), (x1, y1)])


TILE_GLYPHS = {
    "list": _t_list, "check": _t_check, "star": _t_star, "flag": _t_flag,
    "book": _t_book, "bag": _t_bag, "key": _t_key, "gift": _t_gift,
    "cake": _t_cake, "cap": _t_cap, "heart": _t_heart, "leaf": _t_leaf,
    "pill": _t_pill, "dumbbell": _t_dumbbell, "cart": _t_cart,
    "house": _t_house, "music": _t_music, "person": _t_person,
    "phone": _t_phone, "sun": _t_sun,
}


def tile(px: int, color: str, icon: str = "list") -> Image.Image:
    """清单图标：填色圆角方块 + 白色图形（苹果自建列表的图标就是这个形制）。"""
    glyph = TILE_GLYPHS.get(icon) or TILE_GLYPHS["list"]
    g = Pen(px, color, stroke=TILE_STROKE)
    g.box(0.8, 0.8, 15.2, 15.2, r=3.6, fill=True)
    g.fg = WHITE
    g.w = max(1, int(round(TILE_STROKE * g.u)))
    glyph(g)
    return g.image()


def dot(px: int, color: str) -> Image.Image:
    """纯色圆点（智能分组里表示「这是该清单的第一条」这一类场合）。"""
    g = Pen(px, color)
    _fill_ellipse(g, 8, 8, 6.0, 6.0)
    return g.image()


# ======================================================================
# 3. 详情行 / 工具栏的线性图标
# ======================================================================
def _g_calendar(g: Pen) -> None:
    g.box(2.8, 3.6, 13.2, 13.2, r=1.9)
    g.poly([(2.8, 6.8), (13.2, 6.8)])
    g.poly([(6.0, 2.3), (6.0, 5.0)])
    g.poly([(10.0, 2.3), (10.0, 5.0)])


def _g_clock(g: Pen) -> None:
    g.ring(8, 8, 5.6)
    g.poly([(8, 8), (8, 4.6)])
    g.poly([(8, 8), (10.8, 8)])


def _g_repeat(g: Pen) -> None:
    _ell_arc(g, 8, 8, 5.0, 5.0, 205, 335)
    _ell_arc(g, 8, 8, 5.0, 5.0, 25, 155)
    _fill_poly(g, [(10.0, 1.7), (13.4, 5.2), (10.0, 5.6)])
    _fill_poly(g, [(6.0, 14.3), (2.6, 10.8), (6.0, 10.4)])


def _g_priority(g: Pen) -> None:
    g.poly([(8, 3.4), (8, 9.4)])
    g.box(7.1, 10.8, 8.9, 12.6, r=0.7, fill=True)


def _g_flag(g: Pen) -> None:
    g.poly([(4.4, 2.6), (4.4, 13.6)])
    g.poly([(4.4, 3.2), (12.4, 3.2), (10.3, 6.2), (12.4, 9.2), (4.4, 9.2)])


def _g_list(g: Pen) -> None:
    for y in (4.6, 8.0, 11.4):
        g.box(2.9, y - 0.6, 4.1, y + 0.6, r=0.5, fill=True)
        g.poly([(6.0, y), (13.2, y)])


def _g_tag(g: Pen) -> None:
    g.poly([(2.8, 8.4), (8.4, 2.8), (13.4, 2.8), (13.4, 7.8), (7.8, 13.4),
            (2.8, 8.4)])
    g.box(10.4, 4.6, 11.7, 5.9, r=0.6, fill=True)


def _g_subtask(g: Pen) -> None:
    g.box(2.9, 2.9, 13.1, 13.1, r=3.2)
    g.poly([(5.4, 8.3), (7.4, 10.3), (11.0, 6.0)])


def _g_note(g: Pen) -> None:
    g.poly([(3.2, 12.4), (3.2, 3.4), (13.0, 3.4), (13.0, 12.4), (3.2, 12.4)])
    g.poly([(5.6, 6.4), (10.6, 6.4)])
    g.poly([(5.6, 9.0), (9.0, 9.0)])


def _g_bell(g: Pen) -> None:
    g.arc(8, 8, 4.8, 180, 360, caps=False)
    g.poly([(3.2, 8.0), (3.2, 11.0)])
    g.poly([(12.8, 8.0), (12.8, 11.0)])
    g.poly([(2.3, 11.0), (13.7, 11.0)])
    g.poly([(6.8, 12.6), (9.2, 12.6)])


def _g_plus(g: Pen) -> None:
    g.poly([(8, 3.4), (8, 12.6)])
    g.poly([(3.4, 8), (12.6, 8)])


def _g_trash(g: Pen) -> None:
    g.poly([(3.4, 4.6), (12.6, 4.6)])
    g.poly([(5.2, 4.6), (5.2, 13.2), (10.8, 13.2), (10.8, 4.6)])
    g.poly([(6.4, 2.8), (9.6, 2.8)])
    g.poly([(8.0, 6.6), (8.0, 11.2)])


def _g_search(g: Pen) -> None:
    g.ring(7.2, 7.2, 4.4)
    g.poly([(10.4, 10.4), (13.6, 13.6)])


def _g_chevron_right(g: Pen) -> None:
    g.poly([(6.4, 3.6), (11.0, 8.0), (6.4, 12.4)])


def _g_sun_small(g: Pen) -> None:
    g.ring(8, 8, 2.8)
    for i in range(8):
        a = math.radians(i * 45)
        g.poly([(8 + 4.1 * math.cos(a), 8 + 4.1 * math.sin(a)),
                (8 + 5.7 * math.cos(a), 8 + 5.7 * math.sin(a))])


ROW_GLYPHS = {
    "calendar": _g_calendar, "clock": _g_clock, "repeat": _g_repeat,
    "priority": _g_priority, "flag": _g_flag, "list": _g_list,
    "tag": _g_tag, "subtask": _g_subtask, "note": _g_note, "bell": _g_bell,
    "plus": _g_plus, "trash": _g_trash, "search": _g_search,
    "chevron_right": _g_chevron_right, "sun": _g_sun_small,
}


def row_glyph(px: int, name: str, color: str) -> Image.Image:
    """详情面板每一行的线性小图标（16×16 逻辑单位，与导航图标同线宽）。"""
    glyph = ROW_GLYPHS.get(name) or _g_list
    g = Pen(px, color, stroke=GLYPH_STROKE)
    glyph(g)
    return g.image()


# ======================================================================
# 缓存接口（返回 ImageTk.PhotoImage，供 tk.Label 直接使用）
# ======================================================================
def _cb(px: int, color: str, checked: bool):
    return _photo(f"todo:cb:{color}:{px}:{int(bool(checked))}",
                  lambda: checkbox(px, color, checked))


def _tile(px: int, color: str, icon: str):
    return _photo(f"todo:tile:{color}:{px}:{icon}", lambda: tile(px, color, icon))


def _dot(px: int, color: str):
    return _photo(f"todo:dot:{color}:{px}", lambda: dot(px, color))


def _glyph(px: int, name: str, color: str):
    return _photo(f"todo:glyph:{name}:{color}:{px}",
                  lambda: row_glyph(px, name, color))


# 便于调用方 import 后直接使用
checkbox_image = _cb
tile_image = _tile
dot_image = _dot
glyph_image = _glyph
