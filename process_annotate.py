# -*- coding: utf-8 -*-
"""截图标注：圈注 / 方框 / 箭头 / 文字，PIL 直出，不引第三方依赖。

为什么需要
--------------------------------------------------------------------------------
流程截图是「当时那个界面」的唯一记录，可它经常差一口气就能用：证书文件名在
一大片文字里、要指的那一行在几十行日志中间。以前只能口头说「第三行那个」，
或者另开画图软件画完再手动贴回来。这里把「画一笔」收进流程中心自己。

三条硬约束（由 ``scripts/test_process.py`` 的 [M] 节守着）
--------------------------------------------------------------------------------
1. **不动原图，只增不改**。标注结果另存成 ``原名_标注.png``（重名再退到
   ``_2``、``_3``），原图与它在库里的路径一个字节都不变。截图不可再生，
   覆盖原图等于把「当时那个界面」永久弄丢。
2. **一笔都没有就不落盘**。空 ops 直接返回失败，免得目录里堆一堆与原图
   一模一样的副本 —— 那种文件在缩略图里根本看不出差别。
3. **坐标先夹进图片范围**。画布尺寸与图片尺寸不一定相等（界面按视口缩放），
   越界坐标在 PIL 上**不报错**，只会画到画布外面：看不见、也测不出来，
   但图确实被写坏了。所以夹取必须发生在画之前。

分层
--------------------------------------------------------------------------------
::

    process_annotate.py          本文件：纯逻辑（形状模型 + 画 + 存），不认识 Tk
    process_annotate_dialog.py   画布交互（拖拽出形状），只回调 ops
    process_page.py              「标注」入口：算出目标文件名、写回库

``apply_ops`` 才需要 PIL。形状规整、坐标夹取、目标文件名这些**不依赖 PIL**
的部分单独拎出来，测试在没有 Pillow 的机器上也能跑。
"""

from __future__ import annotations

import math
from pathlib import Path

__all__ = [
    "SHAPE_ARROW",
    "SHAPE_ELLIPSE",
    "SHAPE_LABELS",
    "SHAPE_ORDER",
    "SHAPE_RECT",
    "SHAPE_TEXT",
    "SUFFIX",
    "COLORS",
    "DEFAULT_COLOR",
    "DEFAULT_WIDTH",
    "normalize_op",
    "normalize_ops",
    "clamp_box",
    "clamp_point",
    "arrow_head",
    "candidate_path",
    "apply_ops",
    "annotate_file",
]

SHAPE_ELLIPSE = "ellipse"
SHAPE_RECT = "rect"
SHAPE_ARROW = "arrow"
SHAPE_TEXT = "text"

SHAPE_LABELS = {
    SHAPE_ELLIPSE: "圈注",
    SHAPE_RECT: "方框",
    SHAPE_ARROW: "箭头",
    SHAPE_TEXT: "文字",
}
SHAPE_ORDER = (SHAPE_ELLIPSE, SHAPE_RECT, SHAPE_ARROW, SHAPE_TEXT)

# 标注配色：红在最前（「重点」的默认色），其余三个只在要区分多笔时才用得上
COLORS = ("#e53935", "#fb8c00", "#43a047", "#1e88e5")
DEFAULT_COLOR = COLORS[0]
DEFAULT_WIDTH = 3

# 另存后缀。加在**词干**后面而不是扩展名前面，是为了 ``foo.png`` →
# ``foo_标注.png`` 这种一眼能认出来的名字。
SUFFIX = "_标注"


def normalize_op(op) -> dict | None:
    """把一条操作规整成确定形状；不合法返回 ``None``。

    丢掉一笔远好过整张图存不出来：画布上已经画出来的东西还在，用户补一笔就行。
    """
    if not isinstance(op, dict):
        return None
    kind = str(op.get("kind") or "").strip().lower()
    if kind not in SHAPE_LABELS:
        return None
    color = str(op.get("color") or "").strip() or DEFAULT_COLOR
    try:
        width = int(op.get("width") or DEFAULT_WIDTH)
    except (TypeError, ValueError):
        width = DEFAULT_WIDTH
    entry = {"kind": kind, "color": color, "width": max(1, min(width, 24))}

    if kind == SHAPE_TEXT:
        text = str(op.get("text") or "").strip()
        if not text:
            return None
        entry["text"] = text

    for key in ("x1", "y1", "x2", "y2"):
        try:
            entry[key] = int(round(float(op.get(key) or 0)))
        except (TypeError, ValueError):
            entry[key] = 0
    return entry


def normalize_ops(ops) -> list[dict]:
    """整批规整，顺序保持不动（后画的盖在上面，和画布上看到的一致）。"""
    result = []
    for op in (ops or []):
        one = normalize_op(op)
        if one is not None:
            result.append(one)
    return result


def clamp_box(box, size) -> tuple[int, int, int, int]:
    """把 ``(x1, y1, x2, y2)`` 夹进 ``(宽, 高)``，并归一成左上 / 右下。

    拖拽可以从任意一个角开始，所以先排序再夹取，画出来的框才是「框住那一块」。
    """
    width = int(size[0])
    height = int(size[1])
    values = []
    for value in box:
        try:
            values.append(int(round(float(value))))
        except (TypeError, ValueError):
            values.append(0)
    x1, y1, x2, y2 = values
    low_x, high_x = sorted((x1, x2))
    low_y, high_y = sorted((y1, y2))
    return (max(0, min(low_x, width)), max(0, min(low_y, height)),
            max(0, min(high_x, width)), max(0, min(high_y, height)))


def clamp_point(point, size) -> tuple[int, int]:
    """单个点夹进图片范围（箭头两端都要过这一关，见模块头第 3 条）。"""
    width = int(size[0])
    height = int(size[1])
    values = []
    for value in point:
        try:
            values.append(int(round(float(value))))
        except (TypeError, ValueError):
            values.append(0)
    return (max(0, min(values[0], width)), max(0, min(values[1], height)))


def arrow_head(x1, y1, x2, y2, *, size: int = 14, spread: float = 26.0):
    """算出箭头两条「翼」的端点。

    PIL 的 ``ImageDraw`` 没有箭头，只能自己画两条短线。这里刻意做成**纯函数**
    （返回两组坐标，不碰画布）：箭头的角度算错在图上不明显，但在地图上就是
    「箭头指偏了」，只有能直接断言坐标才抓得住。

    返回 ``[[(xa, ya), (x2, y2)], [(xb, yb), (x2, y2)]]``。
    """
    delta_x = float(x2) - float(x1)
    delta_y = float(y2) - float(y1)
    length = math.hypot(delta_x, delta_y)
    if length == 0:
        return []
    # 箭头方向朝终点：从终点往起点退，再各自偏 ±spread 度
    back = math.atan2(-delta_y, -delta_x)
    half = math.radians(spread) / 2.0
    wings = []
    for sign in (1.0, -1.0):
        angle = back + sign * half
        wings.append([
            (int(round(x2 + size * math.cos(angle))),
             int(round(y2 - size * math.sin(angle)))),
            (int(x2), int(y2)),
        ])
    return wings


def candidate_path(src, *, taken=None) -> Path:
    """标注结果的落点：``a.png`` → ``a_标注.png``，重名依次退到 ``_2`` / ``_3``。

    ``taken`` 是「已经被占用的文件名」集合（小写字）。传进来而不是自己去列目录，
    是为了让调用方能把**同一批要新增的文件**也算进去（一次标注多张时）。
    """
    path = Path(src)
    used = {str(name).lower() for name in (taken or ())}
    stem = path.stem + SUFFIX
    suffix = path.suffix or ".png"

    def free(name: str) -> bool:
        return name.lower() not in used

    if free(stem + suffix):
        return path.with_name(stem + suffix)
    index = 2
    while True:
        name = f"{stem}_{index}{suffix}"
        if free(name):
            return path.with_name(name)
        index += 1


def _load_font(size: int):
    """尽量拿一个能看的字号；拿不到就退回 PIL 的位图默认字体。

    ``ImageFont.load_default(size=...)`` 要 Pillow ≥ 10；老版本只认无参调用，
    那时文字会比预期小一号 —— 能看就行，不值得为它引一个字体文件。
    """
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def apply_ops(image, ops, *, font=None):
    """在 ``image`` 上按顺序画完所有操作，返回同一个对象（原地改）。"""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    size = image.size
    for op in normalize_ops(ops):
        color = op["color"]
        width = op["width"]
        if op["kind"] == SHAPE_ELLIPSE:
            draw.ellipse(clamp_box((op["x1"], op["y1"], op["x2"], op["y2"]), size),
                         outline=color, width=width)
        elif op["kind"] == SHAPE_RECT:
            draw.rectangle(clamp_box((op["x1"], op["y1"], op["x2"], op["y2"]), size),
                           outline=color, width=width)
        elif op["kind"] == SHAPE_ARROW:
            start = clamp_point((op["x1"], op["y1"]), size)
            end = clamp_point((op["x2"], op["y2"]), size)
            if start != end:
                draw.line([start, end], fill=color, width=width)
                for wing in arrow_head(*start, *end, size=8 + width * 2):
                    draw.line(wing, fill=color, width=width)
        elif op["kind"] == SHAPE_TEXT:
            point = clamp_point((op["x1"], op["y1"]), size)
            draw.text(point, op["text"], fill=color, font=font or _load_font(18))
    return image


def annotate_file(src, dest, ops, *, opener=None) -> dict:
    """读原图 → 画 → 存到 ``dest``。**原图一个字节都不动。**

    返回 ``{"ok", "dest", "count", "reason"}``：界面直接把 ``reason`` 显示到
    状态栏，不用自己拼话术。
    """
    from PIL import Image

    valid = normalize_ops(ops)
    if not valid:
        return {"ok": False, "dest": None, "count": 0,
                "reason": "还没有画任何标注，没有生成新图。"}

    source = Path(src)
    open_fn = opener or (lambda path: Image.open(path))
    try:
        with open_fn(source) as handle:
            image = handle.convert("RGB")
    except Exception as exc:                      # noqa: BLE001 - 一句话比堆栈好
        return {"ok": False, "dest": None, "count": 0,
                "reason": f"打不开原图：{exc}"}

    try:
        apply_ops(image, valid)
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False, "dest": None, "count": 0,
                "reason": f"画标注失败：{exc}"}

    target = Path(dest)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, "PNG")
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False, "dest": None, "count": len(valid),
                "reason": f"保存标注图失败：{exc}"}
    return {"ok": True, "dest": target, "count": len(valid),
            "reason": f"标注已保存：{target.name}（画了 {len(valid)} 笔）。"}
