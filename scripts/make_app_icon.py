# -*- coding: utf-8 -*-
"""生成应用图标（app.ico），并同步更新内嵌 base64 副本。

为什么要这个脚本
------------------------------------------------------------------------------
应用图标此前是一枚「亮蓝圆角方块 + 白色箭头」，与项目定稿的黑白 + 浅灰体系
直接冲突（全项目唯一的高饱和度色块）。而且它有**两份**：根目录 ``app.ico``
与 ``embedded_admin_tools/services/app_icon_service.py`` 里内嵌的 base64。
打包版走内嵌那份，开发态走外部那份 —— 手工改一处必然产生不一致。

本脚本把「画图标」这件事变成可复现的代码：
  * 图标是**画出来的**，不是美术资源，随时可重新生成
  * 一份设计同时产出两份载体（app.ico + 内嵌 base64），杜绝不一致
  * 每个尺寸单独按 8 倍超采样渲染再降采样，保证 16px 不糊

用法
------------------------------------------------------------------------------
    python scripts/make_app_icon.py --preview            # 只出候选对比图，不写文件
    python scripts/make_app_icon.py --design ring --write # 生成并写入两份载体

设计语言：**近黑圆角方块 + 白色几何标记**，单色、无渐变、无阴影。
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app_icons  # noqa: E402  （需要先补 sys.path）

TILE_DARK = (28, 28, 28, 255)      # #1c1c1c —— 与 ui_theme 的 accent 同值
TILE_LIGHT = (255, 255, 255, 255)
LIGHT_EDGE = (222, 222, 222, 255)  # #dedede —— 浅底牌在白背景上的细边
GLYPH_LIGHT = (255, 255, 255, 255)
GLYPH_DARK = (28, 28, 28, 255)

# 圆角比例：0.235 是 iOS / Windows 11 图标的常见量级，既圆又不至于变成胶囊
TILE_RADIUS_RATIO = 0.235
SS = 8  # 每个尺寸的超采样倍数


# ----------------------------------------------------------------------
# 几何标记（全部按 size 的归一化比例作画，因此任意尺寸都同构）
# ----------------------------------------------------------------------
def _g_bars(d: ImageDraw.ImageDraw, s: int, fg) -> None:
    """三条横线，末行渐短 ——「清单 / 管理」语义。"""
    h = max(1, int(s * 0.098))
    r = h // 2
    x0 = int(s * 0.245)
    span = s - 2 * x0
    for frac_y, frac_w in ((0.285, 1.0), (0.451, 0.70), (0.617, 0.44)):
        y = int(s * frac_y)
        d.rounded_rectangle(
            [x0, y, x0 + int(span * frac_w), y + h], radius=r, fill=fg
        )


def _g_arrow(d: ImageDraw.ImageDraw, s: int, fg) -> None:
    """上箭头（精修版）—— 延续旧图标的「续期」语义，但细、正、几何。"""
    w = max(1, int(s * 0.092))
    r = w / 2
    cx = s / 2
    y_bot, y_top, y_wing = s * 0.700, s * 0.285, s * 0.455
    x_l, x_r = s * 0.275, s * 0.725
    d.line([(cx, y_bot), (cx, y_top)], fill=fg, width=w)
    d.line([(x_l, y_wing), (cx, y_top)], fill=fg, width=w)
    d.line([(x_r, y_wing), (cx, y_top)], fill=fg, width=w)
    for px, py in ((cx, y_bot), (x_l, y_wing), (x_r, y_wing)):
        d.ellipse([px - r, py - r, px + r, py + r], fill=fg)


def _g_layers(d: ImageDraw.ImageDraw, s: int, fg) -> None:
    """两张错位卡片 ——「模块 / 系统」语义。"""
    w = max(1, int(s * 0.056))
    side = s * 0.40
    r = int(s * 0.07)
    bx, by = s * 0.35, s * 0.245          # 后层（右上，描边）
    d.rounded_rectangle(
        [bx, by, bx + side, by + side], radius=r, outline=fg, width=w
    )
    fx, fy = s * 0.25, s * 0.345          # 前层（左下，实心）
    d.rounded_rectangle([fx, fy, fx + side, fy + side], radius=r, fill=fg)


def _g_grid(d: ImageDraw.ImageDraw, s: int, fg) -> None:
    """2×2 点阵 ——「工具箱」语义。"""
    side = s * 0.245
    r = int(s * 0.072)
    gap = s * 0.105
    x0 = (s - (side * 2 + gap)) / 2
    y0 = x0
    for ix in (0, 1):
        for iy in (0, 1):
            x = x0 + ix * (side + gap)
            y = y0 + iy * (side + gap)
            d.rounded_rectangle([x, y, x + side, y + side], radius=r, fill=fg)


GLYPHS = {
    "bars": _g_bars,
    "arrow": _g_arrow,
    "layers": _g_layers,
    "grid": _g_grid,
}

# 候选清单：名字 -> (底牌, 标记)。标记为 None 表示用 app_icons 的圆环标记。
DESIGNS: dict[str, tuple[str, str]] = {
    "ring": ("dark", "brand"),
    "bars": ("dark", "bars"),
    "arrow": ("dark", "arrow"),
    "layers": ("dark", "layers"),
    "grid": ("dark", "grid"),
    "light_ring": ("light", "brand"),
    "light_bars": ("light", "bars"),
}


# ----------------------------------------------------------------------
# 渲染
# ----------------------------------------------------------------------
def render(design: str, size: int) -> Image.Image:
    """把指定设计渲染到指定边长。每个尺寸独立超采样，保证小尺寸清晰。"""
    tile, glyph_name = DESIGNS[design]

    # 圆环标记与界面内的品牌标记同源（app_icons.draw_brand_tile）
    if glyph_name == "brand":
        if tile == "light":
            return app_icons.draw_brand_tile(
                size, tile=TILE_LIGHT, glyph=GLYPH_DARK, edge=LIGHT_EDGE
            )
        return app_icons.draw_brand_tile(size)

    s = size * SS
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    pad = max(0, int(s * 0.015))
    box = [pad, pad, s - 1 - pad, s - 1 - pad]
    radius = int(s * TILE_RADIUS_RATIO)

    if tile == "dark":
        d.rounded_rectangle(box, radius=radius, fill=TILE_DARK)
        fg = GLYPH_LIGHT
    else:
        d.rounded_rectangle(
            box,
            radius=radius,
            fill=TILE_LIGHT,
            outline=LIGHT_EDGE,
            width=max(1, int(s * 0.014)),
        )
        fg = GLYPH_DARK

    GLYPHS[glyph_name](d, s, fg)
    return im.resize((size, size), Image.LANCZOS)


ICO_SIZES = [256, 128, 64, 48, 32, 16]


def build_ico(design: str) -> bytes:
    buf = io.BytesIO()
    render(design, ICO_SIZES[0]).save(
        buf, format="ICO", sizes=[(n, n) for n in ICO_SIZES]
    )
    return buf.getvalue()


# ----------------------------------------------------------------------
# 预览图
# ----------------------------------------------------------------------
def _load_font(size: int):
    """预览图的标注用中文字体，否则默认位图字体会把汉字画成方框。"""
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
        p = Path("C:/Windows/Fonts") / name
        if p.exists():
            try:
                from PIL import ImageFont
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return None


def build_preview(out_path: Path) -> None:
    big = 160
    names = list(DESIGNS)
    cols = len(names)
    cell_w, cell_h = big + 28, big + 96
    W = cols * cell_w + 24
    H = cell_h + 150
    sheet = Image.new("RGB", (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(sheet)
    f_name = _load_font(14)
    f_note = _load_font(15)

    smalls = [48, 32, 24, 16]
    x = 12
    for name in names:
        # 大图
        sheet.paste(render(name, big), (x + 14, 16), render(name, big))
        d.text((x + 14, 16 + big + 6), name, fill=(60, 60, 60), font=f_name)

        # 白底小尺寸
        sx = x + 14
        sy = 16 + big + 26
        for n in smalls:
            tile = render(name, n)
            sheet.paste(tile, (sx, sy + (48 - n)), tile)
            sx += n + 8

        # 深底（模拟深色任务栏）
        dy = sy + 56
        d.rectangle([x + 6, dy - 4, x + cell_w - 10, dy + 46], fill=(32, 32, 32))
        dx = x + 14
        for n in (48, 32, 16):
            tile = render(name, n)
            sheet.paste(tile, (dx, dy + (40 - n)), tile)
            dx += n + 8
        x += cell_w

    d.text((14, H - 30), "上排：白底 48/32/24/16    下排：深色任务栏模拟 48/32/16",
           fill=(130, 130, 130), font=f_note)
    sheet.save(out_path)
    print(f"预览已生成 -> {out_path}")


# ----------------------------------------------------------------------
# 写入两份载体
# ----------------------------------------------------------------------
def write_icon(design: str) -> None:
    ico = build_ico(design)

    ico_path = ROOT / "app.ico"
    ico_path.write_bytes(ico)
    print(f"已写入 {ico_path.relative_to(ROOT)}  ({len(ico)} 字节)")

    service = ROOT / "embedded_admin_tools" / "services" / "app_icon_service.py"
    raw = service.read_bytes()
    marker = b'_APP_ICON_B64 = """'
    i = raw.index(marker)
    j = raw.index(b'"""', i + len(marker))
    b64 = base64.b64encode(ico).decode("ascii")
    lines = [b64[k:k + 76].encode("ascii") for k in range(0, len(b64), 76)]
    blob = b"\r\n".join(lines)

    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    new_block = marker + nl + blob + nl + b'"""'
    raw = raw[:i] + new_block + raw[j + 3:]
    service.write_bytes(raw)
    print(f"已写入 {service.relative_to(ROOT)}  (base64 {len(b64)} 字符)")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成应用图标")
    ap.add_argument("--design", default="ring", choices=sorted(DESIGNS),
                    help="图标设计名（默认 ring）")
    ap.add_argument("--preview", metavar="PATH",
                    help="只输出候选对比图，不修改任何文件")
    ap.add_argument("--write", action="store_true",
                    help="写入 app.ico 与内嵌 base64")
    args = ap.parse_args()

    if args.preview:
        build_preview(Path(args.preview))
        return 0
    if args.write:
        write_icon(args.design)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
