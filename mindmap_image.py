"""思维导图 · 图片导出（纯函数，不 import tkinter）。

为什么不用「抓画布」：Tk 的 ``canvas.postscript()`` 出的是 EPS，要再转 PNG 就得
有 Ghostscript —— 本机（以及用户的机器）不保证有。所以这里**按布局坐标重新画一遍**，
好处还顺带两个：导出的是**整张导图**（不受当前滚动位置与缩放影响），
而且可以按 ``scale`` 出 2x 高清图。

Pillow 是**可选依赖**：没有它时 :func:`available` 返回 ``False``，
界面就禁用「导出 PNG」，别的导出格式照常。**模块导入时不 import PIL。**
"""
from __future__ import annotations

import io
import os

import mindmap_layout as ml

# 中文字体候选。``tkfont.families()`` 在中文 Windows 上只报本地化族名
# （只有「微软雅黑」没有「Microsoft YaHei」），所以这里直接探**字体文件**。
FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",     # 黑体
    r"C:\Windows\Fonts\simsun.ttc",     # 宋体
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)

BASE_FONT_SIZE = 13        # 与 mindmap_layout 的 CHAR_W=7.6 大致对齐
RADIUS = 9
EDGE_WIDTH = 2
CAPTION_GAP = 22


def pick_font() -> str | None:
    """挑一个存在的中文字体文件；一个都没有就返回 ``None``。"""
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def available() -> bool:
    """Pillow 在不在、字体找不找得到。两个都满足才能导 PNG。"""
    try:
        import PIL
    except Exception:  # noqa: BLE001 - 缺依赖是正常情况，不是错误
        return False
    if not str(getattr(PIL, "__version__", "")).strip():
        return False
    return pick_font() is not None


def _tint(color: str, ratio: float) -> tuple:
    """把颜色朝白色混 ``ratio``（0=原色，1=纯白）。用于节点浅底。"""
    text = str(color).lstrip("#")
    red, green, blue = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda channel: int(channel + (255 - channel) * ratio)  # noqa: E731
    return (mix(red), mix(green), mix(blue))


def _solid(color: str) -> tuple:
    text = str(color).lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def _clip(text: str, font, draw, limit: float) -> str:
    """节点文字超宽就截断加省略号（正常不会发生，布局是按同一口径估宽的）。"""
    if not text:
        return ""
    if draw.textlength(text, font=font) <= limit:
        return text
    for cut in range(len(text) - 1, 0, -1):
        candidate = text[:cut] + "…"
        if draw.textlength(candidate, font=font) <= limit:
            return candidate
    return "…"


def render_png(tree, *, scale=2.0, bg="#ffffff", padding=28,
               font_path=None, layout_kwargs=None) -> bytes:
    """把整张导图渲染成 PNG 字节串。

    ``scale`` 是像素倍率（``2.0`` = 高清，``canvas`` 的坐标是 1x 的）。
    """
    from PIL import Image, ImageDraw, ImageFont

    ratio = max(0.5, float(scale or 1.0))
    layout = ml.layout(ml.normalize(tree), **(layout_kwargs or {}))
    width, height = layout["size"]
    pad = float(padding)
    img_w = int(round((width + pad * 2) * ratio))
    img_h = int(round((height + pad * 2) * ratio))
    image = Image.new("RGB", (max(1, img_w), max(1, img_h)), _solid(bg))
    draw = ImageDraw.Draw(image)

    path = font_path or pick_font()
    if path:
        font = ImageFont.truetype(path, int(BASE_FONT_SIZE * ratio))
        badge_font = ImageFont.truetype(path, int((BASE_FONT_SIZE - 3) * ratio))
    else:  # 没字体也要出图（中文会变方块，界面会提前拦一道）
        font = ImageFont.load_default()
        badge_font = font

    def px(value):
        return (float(value) + pad) * ratio

    # 先画连线，再画节点 —— 反过来连线会压在节点上
    by_iid = layout["by_iid"]
    for parent_iid, child_iid in layout["edges"]:
        parent = by_iid.get(parent_iid)
        child = by_iid.get(child_iid)
        if parent is None or child is None:
            continue
        x1, y1, x2, y2 = ml.edge_points(parent, child)
        points = ml.curve_points(x1, y1, x2, y2)
        flat = []
        for index in range(0, len(points) - 1, 2):
            flat.append((px(points[index]), px(points[index + 1])))
        if len(flat) >= 2:
            draw.line(flat, fill=_tint(ml.depth_color(child["depth"]), 0.55),
                      width=max(1, int(EDGE_WIDTH * ratio)), joint="curve")

    for node in layout["nodes"]:
        depth = int(node["depth"])
        color = ml.depth_color(depth)
        left = px(node["x"])
        top = px(node["y"])
        right = px(node["x"] + node["w"])
        bottom = px(node["y"] + node["h"])
        is_root = depth == 0
        draw.rounded_rectangle(
            (left, top, right, bottom), radius=RADIUS * ratio,
            fill=_solid(color) if is_root else _tint(color, 0.90),
            outline=_solid(color), width=max(1, int(1.6 * ratio)))
        text = _clip(str(node.get("text") or ""), font, draw,
                     (right - left) - 18 * ratio)
        text_w = draw.textlength(text, font=font)
        text_h = font.size if hasattr(font, "size") else BASE_FONT_SIZE
        draw.text(((left + right) / 2 - text_w / 2, (top + bottom) / 2 - text_h * 0.62),
                  text, font=font, fill=(255, 255, 255) if is_root else _solid(color))
        if node.get("hidden_children"):
            badge = f"+{node['hidden_children']}"
            draw.text((right - 12 * ratio, top + 4 * ratio), badge,
                      font=badge_font, fill=_solid(color))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
