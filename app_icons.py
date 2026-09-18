# -*- coding: utf-8 -*-
"""应用图形资产：应用标记 + 导航线性图标。

为什么用 Pillow 渲染，而不是 tk.Canvas 直接画
------------------------------------------------------------------------------
``tk.Canvas`` **没有抗锯齿**，1.5px 的斜线（钥匙、代码括号、对话气泡）会明显出锯齿，
在这个追求克制的界面里一眼就廉价。本项目已依赖 Pillow，用它在一张 8 倍超采样画布上
作画再降采样，边缘是干净的。

为什么要按 Tk 缩放渲染
------------------------------------------------------------------------------
图标是**位图**。若固定渲染 16px，在 125% / 150% 缩放的高清屏上会被 Tk 拉花。
因此按 ``tk scaling`` 换算出真实需要的像素数再渲染，每个缩放档位各缓存一份。

颜色不进图标资产
------------------------------------------------------------------------------
同一枚图标按需渲染成不同颜色（默认 / 悬停 / 选中）并缓存，状态切换只是换一张
已缓存的图，不必逐项去改图元颜色 —— 这是 tk.Canvas 方案做不到的。

约定
------------------------------------------------------------------------------
所有几何按 **16×16 逻辑单位**书写（``U = 画布边长 / 16``），线宽 1.35 单位、圆头圆角，
与 ``scripts/make_app_icon.py`` 的圆角比例、强调色一致。
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageTk

# ----------------------------------------------------------------------
# 尺寸与线型
# ----------------------------------------------------------------------
UNITS = 16                 # 逻辑坐标空间边长
STROKE = 1.35              # 逻辑线宽（导航图标）
SS = 8                     # 超采样倍数
BASE_SCALING = 96 / 72     # Tk 在 96 DPI 下的 scaling 值，作为「100%」基准

ICON_LOGICAL = 15          # 导航图标逻辑尺寸
BRAND_LOGICAL = 20         # 应用标记逻辑尺寸

TILE_DARK = (28, 28, 28, 255)   # #1c1c1c，与 ui_theme 的 accent 同值
GLYPH_LIGHT = (255, 255, 255, 255)

# 应用标记的几何（与 scripts/make_app_icon.py 的 ring 设计逐值对应）
TILE_RADIUS_RATIO = 0.235
BRAND_RING_RADIUS = 3.92   # 逻辑单位
BRAND_RING_STROKE = 1.408  # 逻辑单位
RING_GAP_START = 340       # 缺口起角（PIL 约定：0° 在 3 点方向，顺时针）
RING_GAP_END = 290


def tk_scaling(widget) -> float:
    """取当前 Tk 缩放（像素 / 点）。取不到时按 100% 处理。"""
    try:
        return float(widget.tk.call("tk", "scaling"))
    except Exception:
        return BASE_SCALING


def scaled_px(widget, logical: int) -> int:
    """把逻辑像素换算成当前缩放下的实际像素。"""
    return max(1, int(round(logical * tk_scaling(widget) / BASE_SCALING)))


# ----------------------------------------------------------------------
# 画笔
# ----------------------------------------------------------------------
def _rgb(color) -> tuple[int, int, int, int]:
    if isinstance(color, tuple):
        return color
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), 255)


class Pen:
    """把 16×16 逻辑坐标映射到超采样画布的画笔（线条一律圆头）。"""

    def __init__(self, px: int, color, stroke: float = STROKE, supersample: int = SS):
        self.px = px
        self.side = px * supersample
        self.u = self.side / UNITS
        self.w = max(1, int(round(stroke * self.u)))
        self.fg = _rgb(color)
        self.im = Image.new("RGBA", (self.side, self.side), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    # -- 坐标换算 ------------------------------------------------------
    def _p(self, x: float, y: float) -> tuple[float, float]:
        return (x * self.u, y * self.u)

    def _cap(self, x: float, y: float) -> None:
        r = self.w / 2
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=self.fg)

    # -- 图元 ----------------------------------------------------------
    def poly(self, pts) -> None:
        """折线，首尾加圆头、转折处自动圆角。"""
        p = [self._p(x, y) for x, y in pts]
        if len(p) > 1:
            self.d.line(p, fill=self.fg, width=self.w, joint="curve")
        self._cap(*p[0])
        self._cap(*p[-1])

    def ring(self, cx: float, cy: float, r: float) -> None:
        rr = r * self.u
        x, y = self._p(cx, cy)
        self.d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=self.fg, width=self.w)

    def arc(self, cx: float, cy: float, r: float, a0: float, a1: float,
            caps: bool = True) -> None:
        """圆弧（角度按 PIL 约定：0° 在 3 点方向，顺时针）。

        ``caps`` 为真时两端补圆头（折线端点那样的收尾）；画带缺口的圆环时
        必须关掉 —— 圆头会向缺口内各探入约一个线宽，把缺口吃掉一半。
        """
        rr = r * self.u
        x, y = self._p(cx, cy)
        self.d.arc([x - rr, y - rr, x + rr, y + rr], a0, a1, fill=self.fg, width=self.w)
        if not caps:
            return
        for a in (a0, a1):
            rad = math.radians(a)
            self._cap(x + rr * math.cos(rad), y + rr * math.sin(rad))

    def box(self, x0: float, y0: float, x1: float, y1: float,
            r: float = 0.0, fill: bool = False) -> None:
        X0, Y0 = self._p(x0, y0)
        X1, Y1 = self._p(x1, y1)
        rr = r * self.u
        if fill:
            self.d.rounded_rectangle([X0, Y0, X1, Y1], radius=rr, fill=self.fg)
        else:
            self.d.rounded_rectangle([X0, Y0, X1, Y1], radius=rr,
                                     outline=self.fg, width=self.w)

    def image(self) -> Image.Image:
        return self.im.resize((self.px, self.px), Image.LANCZOS)


# ----------------------------------------------------------------------
# 导航图标（16×16 逻辑坐标）
# ----------------------------------------------------------------------
def _g_clock(g: Pen) -> None:            # 到期管理
    g.ring(8, 8, 5.7)
    g.poly([(8, 8), (8, 4.5)])
    g.poly([(8, 8), (11.0, 8)])


def _g_key(g: Pen) -> None:              # 账号中心
    g.ring(4.5, 8, 2.3)
    g.poly([(6.8, 8), (13.0, 8)])
    g.poly([(10.8, 8), (10.8, 10.3)])
    g.poly([(13.0, 8), (13.0, 10.3)])


def _g_flow(g: Pen) -> None:             # 流程中心
    g.ring(4.2, 4.2, 1.9)
    g.ring(11.8, 4.2, 1.9)
    g.ring(11.8, 11.8, 1.9)
    g.poly([(6.1, 4.2), (9.9, 4.2)])
    g.poly([(11.8, 6.1), (11.8, 9.9)])


def _g_code(g: Pen) -> None:             # 后台接口测试
    g.poly([(6.4, 4.4), (2.6, 8.0), (6.4, 11.6)])
    g.poly([(9.6, 4.4), (13.4, 8.0), (9.6, 11.6)])


def _g_chat(g: Pen) -> None:             # Q&A 与工作纪要
    g.box(2.4, 2.8, 13.6, 10.4, r=2.4)
    g.poly([(5.6, 10.3), (5.6, 13.4), (9.0, 10.3)])


def _g_grid(g: Pen) -> None:             # 系统工具箱
    side, gap, r = 5.2, 1.2, 1.5
    x0 = (UNITS - (side * 2 + gap)) / 2
    for ix in (0, 1):
        for iy in (0, 1):
            x = x0 + ix * (side + gap)
            y = x0 + iy * (side + gap)
            g.box(x, y, x + side, y + side, r=r, fill=True)


def _g_doc(g: Pen) -> None:              # 笔记
    g.box(3.6, 2.4, 12.4, 13.6, r=1.8)
    g.poly([(6.0, 6.2), (10.0, 6.2)])
    g.poly([(6.0, 8.6), (10.0, 8.6)])
    g.poly([(6.0, 11.0), (8.4, 11.0)])


def _g_book(g: Pen) -> None:             # Python 学习
    g.box(2.4, 3.2, 13.6, 13.0, r=1.6)
    g.poly([(8.0, 3.2), (8.0, 13.0)])


def _g_dot(g: Pen) -> None:              # 兜底（未登记图标的模块）
    g.box(6.8, 6.8, 9.2, 9.2, r=1.2, fill=True)


# 分组行的展开/收起指示（放在左侧图标槽里，与模块图标同一视觉重量）
def _g_chevron_down(g: Pen) -> None:
    g.poly([(5.4, 6.6), (8.0, 9.4), (10.6, 6.6)])


def _g_chevron_right(g: Pen) -> None:
    g.poly([(6.6, 5.4), (9.4, 8.0), (6.6, 10.6)])


CHEVRON_PX = 12          # chevron 逻辑尺寸，比模块图标略小以让位给文字


NAV_GLYPHS = {
    "module_ops_expiry": _g_clock,
    "module_work_credentials": _g_key,
    "module_work_processes": _g_flow,
    "module_admin_backend": _g_code,
    "module_qa_work": _g_chat,
    "module_system_toolbox": _g_grid,
    "module_study_notes": _g_doc,
    "module_study_demo": _g_book,
}


# ----------------------------------------------------------------------
# 应用标记（与 app.ico 的 ring 设计同源）
# ----------------------------------------------------------------------
def draw_brand_tile(size: int, *, tile=TILE_DARK, glyph=GLYPH_LIGHT,
                    edge=None) -> Image.Image:
    """画一枚「圆角方块 + 圆环缺口」的应用标记。

    ``scripts/make_app_icon.py`` 的 ring / light_ring 两个设计都直接调用本函数，
    因此窗口图标与界面内的品牌标记永远同源，不会各自漂移。

    ``tile`` / ``glyph`` 为 (R,G,B,A) 或 ``#rrggbb``；``edge`` 不为空时给底牌描细边
    （浅底牌放在白背景上需要它才立得住）。
    """
    g = Pen(size, glyph, stroke=BRAND_RING_STROKE)
    side = g.side
    pad = max(0, int(side * 0.015))
    box = [pad, pad, side - 1 - pad, side - 1 - pad]
    radius = int(side * TILE_RADIUS_RATIO)
    if edge is None:
        g.d.rounded_rectangle(box, radius=radius, fill=_rgb(tile))
    else:
        g.d.rounded_rectangle(box, radius=radius, fill=_rgb(tile),
                              outline=_rgb(edge),
                              width=max(1, int(side * 0.014)))
    r = BRAND_RING_RADIUS
    g.arc(8, 8, r, RING_GAP_START, 360, caps=False)
    g.arc(8, 8, r, 0, RING_GAP_END, caps=False)
    return g.image()


# ----------------------------------------------------------------------
# 缓存与对外接口
# ----------------------------------------------------------------------
_image_cache: dict = {}


def _photo(key: str, factory) -> "ImageTk.PhotoImage":
    photo = _image_cache.get(key)
    if photo is None:
        photo = ImageTk.PhotoImage(factory())
        _image_cache[key] = photo      # 缓存同时充当引用，防止被 GC 回收
    return photo


def nav_icon(module_key: str, color: str, px: int) -> "ImageTk.PhotoImage":
    """取一枚导航图标（按 模块 key + 颜色 + 像素 缓存）。"""
    known = module_key in NAV_GLYPHS
    glyph = NAV_GLYPHS[module_key] if known else _g_dot
    name = module_key if known else "_dot"

    def build():
        g = Pen(px, color)
        glyph(g)
        return g.image()

    return _photo(f"nav:{name}:{color}:{px}", build)


def chevron(expanded: bool, color: str, px: int) -> "ImageTk.PhotoImage":
    """分组行的展开 / 收起指示。"""
    glyph = _g_chevron_down if expanded else _g_chevron_right
    name = "down" if expanded else "right"

    def build():
        g = Pen(px, color)
        glyph(g)
        return g.image()

    return _photo(f"chevron:{name}:{color}:{px}", build)


def brand_mark(widget, px: int | None = None) -> "ImageTk.PhotoImage":
    """顶栏左上角的应用标记，尺寸随当前 Tk 缩放。"""
    if px is None:
        px = scaled_px(widget, BRAND_LOGICAL)
    return _photo(f"brand:{px}", lambda: draw_brand_tile(px))


def clear_cache() -> None:
    """清空位图缓存（缩放变化或测试隔离时使用）。"""
    _image_cache.clear()
