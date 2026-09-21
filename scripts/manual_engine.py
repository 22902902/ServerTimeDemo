# -*- coding: utf-8 -*-
"""Python 语法手册的排版引擎 —— 把「块列表」渲染成一份带目录、页码、书签的 PDF。

设计要点
================================================================================
1. **内容与排版分离。** 手册正文写在 ``manual_content.py`` 里，是一串「块」元组
   （见下面的 BLOCK 说明）；本模块只负责把块变成 reportlab 的 flowable。
   改文案不用碰排版代码，加新块类型也只改一个 dispatch 表。

2. **代码块用 ``XPreformatted``，不用 ``Preformatted``。**
   ``Preformatted`` 保留缩进与换行，但不认内联标签，于是没法给关键字上色；
   ``XPreformatted`` 两者都要，是这份手册里唯一能满足「缩进 + 着色」的 flowable。

3. **AST 无关的极简着色器。** 手册里贴的片段常常是「不完整的代码」（只有几行、
   没有上下文），交给 ``ast`` / ``tokenize`` 会直接抛错。这里的着色器是纯正则
   逐个 token 扫过去的，**不解析语法、不要求片段可编译**，对残缺片段同样安全。

4. **中文字体走系统字体。** 正文微软雅黑（与项目界面同族），代码宋体 ——
   宋体的 ASCII 是半角等宽、汉字是全角，正好是中文代码注释想要的排版。
   字体缺失时给出明确指引，而不是默默退化成方框。

块（BLOCK）说明
================================================================================
    ("h1", "第一章 标题")                 章：另起一页，进目录（一级）
    ("h2", "1.1 小节")                    节：进目录（二级）
    ("h3", "小标题")                      子节：不进目录
    ("p", "正文，支持 `代码` 与 **加粗**")
    ("ul", ["条目", "条目"])              无序列表
    ("ol", ["条目", "条目"])              有序列表
    ("code", "python", "源码")            代码块（带行号 + 着色）
    ("out", "文本")                       控制台输出块（不着色）
    ("table", [表头, 行, ...])            表格（首行为表头）
    ("note", "标题", "正文")              提示框
    ("warn", "标题", "正文")              警告框
    ("ok", "标题", "正文")                结论 / 正确做法框
    ("quote", "正文")                     引自项目源码的原文摘录
    ("spacer", 12)                        竖向留白
    ("pagebreak",)                        强制换页
"""

from __future__ import annotations

import re
import xml.sax.saxutils as saxutils
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle, XPreformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents

# =============================================================================
# 字体
# =============================================================================

FONT_DIR = Path("C:/Windows/Fonts")

# 逻辑名 -> (文件名, .ttc 子字体序号)。ttc 里通常打包了多个字族，序号 0 是常规体。
FONT_FILES = {
    "BODY":     ("msyh.ttc", 0),      # 微软雅黑 —— 与项目界面同族
    "BODY_B":   ("msyhbd.ttc", 0),    # 微软雅黑 Bold
    "MONO":     ("simsun.ttc", 0),    # 宋体 —— 半角等宽 + 全角汉字
}

FALLBACK_HINT = (
    "找不到中文字体文件。本引擎依赖 Windows 自带字体：\n"
    "  微软雅黑 C:/Windows/Fonts/msyh.ttc、宋体 C:/Windows/Fonts/simsun.ttc\n"
    "若在别的机器上生成，请修改 manual_engine.FONT_FILES 指向本机存在的字体。"
)


def register_fonts():
    """注册中文字体，返回实际可用的字体名映射。缺失时抛错并给出指引。"""
    missing = [f for f, _ in FONT_FILES.values() if not (FONT_DIR / f).exists()]
    if missing:
        raise RuntimeError(FALLBACK_HINT + "\n缺失：" + "、".join(missing))

    for name, (filename, index) in FONT_FILES.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename),
                                       subfontIndex=index))
    # 让 <b> 标签在正文字族上自动切到 Bold 而不是「假粗」
    pdfmetrics.registerFontFamily("BODY", normal="BODY", bold="BODY_B",
                                  italic="BODY", boldItalic="BODY_B")
    return {name: name for name in FONT_FILES}


# =============================================================================
# 配色（沿用项目的克制灰阶，只为代码加了必要的语义色）
# =============================================================================

class Ink:
    headline = "#141414"
    text = "#2B2B2B"
    secondary = "#6B6B6B"
    muted = "#9A9A9A"
    rule = "#DCDCDC"
    rule_soft = "#ECECEC"
    code_bg = "#F6F7F8"
    code_gutter = "#EDEFF1"
    table_head = "#F0F1F2"
    accent = "#1C1C1C"
    note_bg = "#F6F7F8"
    note_edge = "#BFBFBF"
    warn_bg = "#FDF6EE"
    warn_edge = "#D9A15B"
    ok_bg = "#F2F8F3"
    ok_edge = "#7FA97F"

    # 代码语义色
    c_keyword = "#1A4F9C"
    c_const = "#8A2E2E"
    c_builtin = "#6C3FA0"
    c_string = "#1F7A45"
    c_comment = "#8C8C8C"
    c_number = "#B0561A"
    c_decorator = "#8A6D00"
    c_defname = "#8A2E2E"
    c_plain = "#23282D"
    c_inline = "#8A2E2E"


# =============================================================================
# 版心
# =============================================================================

PAGE_W, PAGE_H = A4
MARGIN_L = 52
MARGIN_R = 52
MARGIN_T = 68
MARGIN_B = 58
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R      # ≈ 491pt

GUTTER_W = 26                                 # 代码行号栏宽
CODE_BG_PAD_L = 7
CODE_BG_PAD_R = 6
CODE_AVAIL = CONTENT_W - GUTTER_W - CODE_BG_PAD_L - CODE_BG_PAD_R   # ≈ 452pt

CODE_FONT_SIZE = 8.5
CODE_LEADING = 12.6
# 宋体半角字符宽 ≈ 字号的一半，据此估算一行能放下多少「半角字符」
CODE_MAX_COLS = int(CODE_AVAIL / (CODE_FONT_SIZE / 2))
CODE_MAX_LINES = 44          # 超过就必须在内容里拆块，否则一页放不下

# 段落的右侧留白。两个原因都会让版面比版心宽：
#   1. ``wordWrap="CJK"`` 按字断行，收尾的「）」会跟着前一个字留在行尾；
#   2. ``<b>`` 切到雅黑 Bold，而 CJK 断行仍按 Regular 的字宽预算 —— Bold 更宽。
# 全量扫描逐页抓过越界行（最多 5.1pt），留出余量后就齐了。
BODY_RIGHT_SLACK = 13
CELL_RIGHT_SLACK = 5


# =============================================================================
# 段落样式
# =============================================================================

def build_styles():
    s = {}
    s["h1"] = ParagraphStyle(
        "h1", fontName="BODY_B", fontSize=19, leading=27,
        textColor=Ink.headline, spaceBefore=0, spaceAfter=14,
        wordWrap="CJK", keepWithNext=1,
    )
    # 与 h1 长得一样，但**不进目录**：专给「目录」这个标题自己用。
    # 否则目录会把「目录」也收成第一条，看着像自己指向自己。
    s["h1_plain"] = ParagraphStyle("h1_plain", parent=s["h1"])
    s["h2"] = ParagraphStyle(
        "h2", fontName="BODY_B", fontSize=13, leading=20,
        textColor=Ink.headline, spaceBefore=17, spaceAfter=8,
        wordWrap="CJK", keepWithNext=1,
    )
    s["h3"] = ParagraphStyle(
        "h3", fontName="BODY_B", fontSize=10.5, leading=17,
        textColor=Ink.text, spaceBefore=12, spaceAfter=5,
        wordWrap="CJK", keepWithNext=1,
    )
    s["body"] = ParagraphStyle(
        "body", fontName="BODY", fontSize=9.6, leading=16.4,
        textColor=Ink.text, spaceBefore=0, spaceAfter=7.5,
        wordWrap="CJK", alignment=TA_LEFT, rightIndent=BODY_RIGHT_SLACK,
    )
    s["bullet"] = ParagraphStyle(
        "bullet", parent=s["body"], leftIndent=15, bulletIndent=3,
        spaceAfter=3.4, leading=15.8,
    )
    s["ordered"] = ParagraphStyle(
        "ordered", parent=s["bullet"], leftIndent=19, bulletIndent=3,
    )
    s["code"] = ParagraphStyle(
        "code", fontName="MONO", fontSize=CODE_FONT_SIZE,
        leading=CODE_LEADING, textColor=Ink.c_plain,
    )
    s["gutter"] = ParagraphStyle(
        "gutter", fontName="MONO", fontSize=7.2, leading=CODE_LEADING,
        textColor=Ink.muted, alignment=TA_RIGHT,
    )
    s["caption"] = ParagraphStyle(
        "caption", fontName="BODY", fontSize=8.4, leading=13,
        textColor=Ink.secondary, spaceBefore=1, spaceAfter=10, wordWrap="CJK",
    )
    s["th"] = ParagraphStyle(
        "th", fontName="BODY_B", fontSize=8.8, leading=14,
        textColor=Ink.headline, wordWrap="CJK", rightIndent=CELL_RIGHT_SLACK,
    )
    s["td"] = ParagraphStyle(
        "td", fontName="BODY", fontSize=8.8, leading=14,
        textColor=Ink.text, wordWrap="CJK", rightIndent=CELL_RIGHT_SLACK,
    )
    s["box_title"] = ParagraphStyle(
        "box_title", fontName="BODY_B", fontSize=9.2, leading=14.5,
        textColor=Ink.headline, spaceAfter=3, wordWrap="CJK",
    )
    s["box_body"] = ParagraphStyle(
        "box_body", fontName="BODY", fontSize=9.1, leading=15.4,
        textColor=Ink.text, wordWrap="CJK", spaceAfter=0,
        rightIndent=BODY_RIGHT_SLACK,
    )
    s["quote"] = ParagraphStyle(
        "quote", fontName="MONO", fontSize=8.4, leading=14,
        textColor="#4A4A4A", leftIndent=10, wordWrap="CJK",
        rightIndent=BODY_RIGHT_SLACK,
    )
    s["toc0"] = ParagraphStyle(
        "toc0", fontName="BODY_B", fontSize=10, leading=19,
        textColor=Ink.headline,
    )
    s["toc1"] = ParagraphStyle(
        "toc1", fontName="BODY", fontSize=9.2, leading=15.6,
        textColor=Ink.secondary, leftIndent=16,
    )
    s["cover_title"] = ParagraphStyle(
        "cover_title", fontName="BODY_B", fontSize=30, leading=44,
        textColor=Ink.headline, alignment=TA_CENTER, wordWrap="CJK",
    )
    s["cover_sub"] = ParagraphStyle(
        "cover_sub", fontName="BODY", fontSize=12.5, leading=22,
        textColor=Ink.secondary, alignment=TA_CENTER, wordWrap="CJK",
    )
    s["cover_meta"] = ParagraphStyle(
        "cover_meta", fontName="BODY", fontSize=9.2, leading=17,
        textColor=Ink.muted, alignment=TA_CENTER, wordWrap="CJK",
    )
    s["volume_note"] = ParagraphStyle(
        "volume_note", fontName="BODY", fontSize=9.4, leading=16,
        textColor=Ink.secondary, wordWrap="CJK", spaceAfter=0,
    )
    return s


STYLES = None       # 由 build() 填充


# =============================================================================
# 内联标记
# =============================================================================

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")

# 换行哨兵。内容文件里能用 ``«BR»`` 表示换行 —— 它不含反斜杠，
# 因此不会在「写入工具 -> 内容文件 -> 引擎」这条链路上被吃掉。
# 生成器踩过一次：`\n` 恰好落在一行末尾时被吞掉，字符串少了收尾引号，
# 直接 SyntaxError。凡是想显式控制换行的地方，用哨兵最稳。
BR = "«BR»"


def md(text: str) -> str:
    """把 ``**加粗**``、`` `行内代码` `` 与换行转成 reportlab 内联标记。

    先整体转义，再替换 —— 顺序反了的话，替换进去的 ``<font>`` 会被当成
    用户输入里的尖括号一起转义掉，页面上就直接显示标签原文。

    **换行必须显式转成 ``<br/>``**：``Paragraph`` 会把文本里的换行连同连续空格
    一起折叠掉（它是「段落」，不是「预排版文本」），不转的话多行提示框
    会挤成一整行。两种写法都接受：真实的换行符，以及哨兵 ``«BR»``。
    """
    out = saxutils.escape(text)
    out = _INLINE_CODE.sub(
        lambda m: f'<font face="MONO" color="{Ink.c_inline}">{m.group(1)}</font>',
        out)
    out = _BOLD.sub(r"<b>\1</b>", out)
    return out.replace(BR, "<br/>").replace("\n", "<br/>")


# =============================================================================
# 极简 Python 着色器
# =============================================================================

KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally",
    "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
    "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
    "match", "case",
}
CONSTANTS = {"True", "False", "None"}
BUILTINS = {
    "abs", "all", "any", "bool", "bytes", "callable", "chr", "classmethod",
    "dataclass", "dict", "dir", "divmod", "enumerate", "eval", "filter",
    "float", "format", "frozenset", "getattr", "hasattr", "hash", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max", "min",
    "next", "object", "open", "ord", "print", "property", "range", "repr",
    "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod",
    "str", "sum", "super", "tuple", "type", "vars", "zip",
    "Exception", "ValueError", "TypeError", "KeyError", "RuntimeError",
    "OSError", "AttributeError", "IndexError", "StopIteration", "TclError",
    "NotImplementedError", "FileNotFoundError", "ImportError",
}

# 顺序即优先级：注释 > 字符串 > 装饰器 > 数字 > 标识符 > 运算符
_TOKEN_RE = re.compile(
    r"""(?P<comment>\#[^\n]*)"""
    r"""|(?P<string>(?:[rbfuRBFU]{0,2})?(?:'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\""""
    r"""|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"))"""
    r"""|(?P<decorator>@[A-Za-z_][\w.]*)"""
    r"""|(?P<number>\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b)"""
    r"""|(?P<name>[A-Za-z_]\w*)"""
    r"""|(?P<space>[^\S\n]+)"""
    r"""|(?P<other>.)""",
    re.DOTALL,
)

_DEF_HEAD = re.compile(r"\b(def|class)\s+$")


def _colorize_spans(src: str):
    """产出 ``(文本, 颜色或 None)`` 序列。不解析语法，所以片段残缺也不会报错。"""
    spans = []
    prev_end = 0
    pending_defname = False
    for m in _TOKEN_RE.finditer(src):
        # 两个 token 之间若有空隙（比如换行），原样保留
        if m.start() > prev_end:
            spans.append((src[prev_end:m.start()], None))
        prev_end = m.end()

        kind = m.lastgroup
        text = m.group()
        if kind == "name":
            if pending_defname:
                spans.append((text, Ink.c_defname))
                pending_defname = False
                continue
            if text in CONSTANTS:
                spans.append((text, Ink.c_const))
            elif text in KEYWORDS:
                spans.append((text, Ink.c_keyword))
                pending_defname = True
            elif text in BUILTINS:
                spans.append((text, Ink.c_builtin))
            else:
                spans.append((text, None))
            continue
        if kind in ("space", "other"):
            spans.append((text, None))
            continue
        pending_defname = False
        spans.append((text, {
            "comment": Ink.c_comment,
            "string": Ink.c_string,
            "decorator": Ink.c_decorator,
            "number": Ink.c_number,
        }[kind]))
    if prev_end < len(src):
        spans.append((src[prev_end:], None))
    return spans


def highlight_python(src: str) -> str:
    """Python 源码 -> XPreformatted 可用的内联标记字符串。

    每个 token 单独转义后再包 ``<font>``：整体转义会把我们自己的标签一起吃掉。
    """
    out = []
    for text, color in _colorize_spans(src):
        escaped = saxutils.escape(text)
        if color is None:
            out.append(escaped)
        else:
            out.append(f'<font color="{color}">{escaped}</font>')
    return "".join(out)


def plain_pre(src: str) -> str:
    """非 Python 文本（控制台输出 / 目录树）：整体转义，不着色。"""
    return saxutils.escape(src)


# =============================================================================
# Flowable 构造
# =============================================================================

def _code_flowable(src: str, lang: str = "python"):
    """代码块：左侧行号栏 + 带底色的代码栏。

    行号与代码分两列是为了让行号右对齐（塞进同一段文本里做不到），
    两列的行距必须一致，否则行号会跟代码逐行错开。
    """
    lines = src.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()

    if len(lines) > CODE_MAX_LINES:
        raise ValueError(
            f"代码块 {len(lines)} 行，超过一页能容纳的 {CODE_MAX_LINES} 行 —— "
            "请在内容里拆成两块")
    for i, line in enumerate(lines, 1):
        width = sum(2 if ord(ch) > 0x2000 else 1 for ch in line)
        if width > CODE_MAX_COLS:
            raise ValueError(
                f"代码块第 {i} 行约 {width} 显示列，超出版心 {CODE_MAX_COLS} 列：\n"
                f"    {line[:60]}…")

    body = highlight_python(src) if lang == "python" else plain_pre(src)
    gutter_text = "\n".join(str(i) for i in range(1, len(lines) + 1))

    gutter = XPreformatted(gutter_text, STYLES["gutter"])
    code = XPreformatted(body, STYLES["code"])

    table = Table(
        [[gutter, code]],
        colWidths=[GUTTER_W, CONTENT_W - GUTTER_W],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), Ink.code_gutter),
            ("BACKGROUND", (1, 0), (1, 0), Ink.code_bg),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 4),
            ("RIGHTPADDING", (0, 0), (0, 0), 4),
            ("LEFTPADDING", (1, 0), (1, 0), CODE_BG_PAD_L),
            ("RIGHTPADDING", (1, 0), (1, 0), CODE_BG_PAD_R),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]),
    )
    return table


def _box_flowable(title: str, body: str, bg: str, edge: str):
    inner = []
    if title:
        inner.append(Paragraph(md(title), STYLES["box_title"]))
    inner.append(Paragraph(md(body), STYLES["box_body"]))
    table = Table([[inner]], colWidths=[CONTENT_W],
                  style=TableStyle([
                      ("BACKGROUND", (0, 0), (-1, -1), bg),
                      ("LINEBEFORE", (0, 0), (0, -1), 2.4, edge),
                      ("LEFTPADDING", (0, 0), (-1, -1), 10),
                      ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                      ("TOPPADDING", (0, 0), (-1, -1), 7.5),
                      ("BOTTOMPADDING", (0, 0), (-1, -1), 7.5),
                  ]))
    return [Spacer(1, 1), table, Spacer(1, 9)]


def _table_flowable(rows):
    header, *body = rows
    data = [[Paragraph(md(str(c)), STYLES["th"]) for c in header]]
    for row in body:
        data.append([Paragraph(md(str(c)), STYLES["td"]) for c in row])

    ncols = len(header)
    widths = _column_widths(rows, ncols)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), Ink.table_head),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, Ink.rule),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, Ink.rule_soft),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]
    return Table(data, colWidths=widths, repeatRows=1, style=TableStyle(style))


# 一个「不可折断的片段」：连续的半角可打印字符。中文按字断行，
# 断点天然存在，所以不计入保底；文件名 / 函数名 / 命令行这种半角串
# 一旦被折断就成了两行，必须给足宽度。
_UNBREAKABLE = re.compile(r"[!-~]+")

# 但不是所有片段都值得为它撑宽一列：连着三十几个半角字符的长路径
# （``embedded_admin_tools/login_memory_service.py``）需要 220pt 才放得下，
# 那是半张版心 —— 给它就等于把整张表挤干。超过这个长度的片段一律
# 不参与保底，让它自己折行去。短期标识符（``todo_db.py`` 这种）才是
# 真正需要保护的，它们远在这个长度以内。
_MAX_FLOOR_PIECE = 32


def _column_widths(rows, ncols):
    """按列内最长内容分配栏宽，并保证短内容不被折断。

    只「按最长内容等比例摊」会出事：附录 B 的模块清单里，「行数 / 类 / 函数」
    三列的内容只有几个字符，一旦跟模块路径（几十字符）、职责（整句话）
    一起按比例摊，就只剩十几个磅 —— 净可用宽度比一个数字还窄，
    于是 ``5404`` 被逐位竖排成一个数字一行。

    所以分两步：先给每列算一个保底宽度，再把富余列的空间挪给不足列
    （守恒，总宽不变）。

    **保底按「最长的不可折断片段」算，不按整格内容算。** 这是后来修的：
    按整格最长内容算时，「职责」这种整句话的中文列会拿到一个虚高的保底，
    平白挤掉旁边那列的空间；而它本来就是要折行的。改成只看半角串之后，
    中文长句不再虚占，``prune_unused_imports.py`` 这类长标识符才有位置。
    权重另有一道封顶：长句子不该按全句长度争宽。
    """
    FSIZE = 8.8
    PAD = 12.0 + CELL_RIGHT_SLACK   # 左右内边距 + 单元格右侧余量
    MIN_COL = 20.0      # 任何列的绝对下限
    # 保底最多吃半张版心：再长就该让它折行，不能一列把整张表挤干。
    # 附录 B 的最长模块名（46 字符 ≈ 210pt）正好卡在这条线以内，能整行放下。
    FLOOR_CAP = CONTENT_W * 0.5
    WT_CAP = 200.0      # 权重上限：长句子本来就要折行，不该按全句长度争宽

    weights, floors = [], []
    for c in range(ncols):
        longest = 0.0
        widest = 0.0                 # 该列最长的「不可折断片段」
        for row in rows:
            if c < len(row):
                # 去掉行内标记再量：`` ` `` / ``*`` 不占版面
                clean = re.sub(r"[`*]", "", str(row[c]))
                longest = max(longest,
                              pdfmetrics.stringWidth(clean, "BODY", FSIZE))
                for piece in _UNBREAKABLE.findall(clean):
                    if len(piece) > _MAX_FLOOR_PIECE:
                        continue
                    widest = max(widest,
                                 pdfmetrics.stringWidth(piece, "BODY", FSIZE))
        # 表头整串也参与保底：表头通常是两三个字，不会虚占宽度，
        # 但它若掉到下限，「函数」就会被折成「函」「数」两行。
        head = re.sub(r"[`*]", "", str(rows[0][c])) if c < len(rows[0]) else ""
        widest = max(widest, pdfmetrics.stringWidth(head, "BODY_B", FSIZE))
        weights.append(min(max(18.0, longest), WT_CAP))
        floors.append(min(max(MIN_COL, widest + PAD), FLOOR_CAP))

    # 分配：**先发保底，富余再按权重摊**。
    #
    # 早先写的是反过来的「先按权重摊，再把不足的补到保底」，那个写法有个死角：
    # 一旦某列的保底本身就超过它的权重份额，它自己也在「等待补偿」的行列里，
    # 「仍有富余可供让出」的列集合就被算空，整个补偿被跳过 —— 数字列于是
    # 被压成竖排（5444 印成 5/4/4/4）。先发保底不存在这个死角。
    used = sum(floors)
    if used > CONTENT_W:
        # 保底总和就超了版心（列多 + 有超长串），只能等比压缩，
        # 让长列去折行 —— 没有更好的办法了。
        k = CONTENT_W / used
        return [f * k for f in floors]

    rest = CONTENT_W - used
    wsum = sum(weights) or 1.0
    return [f + rest * w / wsum for f, w in zip(floors, weights)]


class ChapterRule(Flowable):
    """章节标题下面那条细线 —— 用 Flowable 画比用 Table 干净。"""

    def __init__(self, width):
        super().__init__()
        self.width = width
        self.height = 6

    def wrap(self, aw, ah):
        return (self.width, self.height)

    def draw(self):
        self.canv.setStrokeColor(colors.HexColor(Ink.accent))
        self.canv.setLineWidth(1.6)
        self.canv.line(0, 3, 34, 3)


# 相对路径以**项目根目录**为基准解析 —— 生成脚本自己在 scripts/ 下，
# 因此往上退一层。这样内容文件里写 "build/probe/x.png" 就有确定含义。
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _image_flowable(path, frac: float = 0.86):
    """按版心宽度等比缩放一张图，并套一圈极淡的边框。

    白底截图直接放在纸面上会「糊」成一片，浅边框至少给它一个边界。

    **宽高必须在构造时就传给 ``Image``**。先建对象再赋 ``drawWidth`` 是个坑：
    实测（``get_image_info`` / 内容流里的 ``cm``）宽会被当成**像素数**直接当磅值用 ——
    960px 的原图画成 1280pt 宽（2.9 倍横向拉伸），而且往左捅出纸面。
    构造参数走的是另一条赋值路径，产出的 ``cm`` 才是 ``442.152 0 0 269.436 ...``。
    """
    from reportlab.platypus import Image as RLImage

    src = Path(path)
    if not src.is_absolute():
        src = PROJECT_ROOT / src
    if not src.exists():
        raise FileNotFoundError(f"插图不存在：{src}")

    # reportlab 报的 imageWidth/Height 与磁盘像素数未必相同（同一份 960×585
    # 的 PNG，它报 1280×780），但**纵横比一致**，所以只拿比例算高度。
    probe = RLImage(str(src))
    width = CONTENT_W * frac
    height = width * probe.imageHeight / probe.imageWidth

    # 一页放不下就整体缩小，宁可小一点也不让它被切掉
    max_h = PAGE_H - MARGIN_T - MARGIN_B - 96
    if height > max_h:
        width *= max_h / height
        height = max_h

    img = RLImage(str(src), width=width, height=height, hAlign="CENTER")

    table = Table([[img]], colWidths=[CONTENT_W],
                  style=TableStyle([
                      ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                      ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                      ("BOX", (0, 0), (-1, -1), 0.5, Ink.rule_soft),
                      ("LEFTPADDING", (0, 0), (-1, -1), 6),
                      ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                      ("TOPPADDING", (0, 0), (-1, -1), 6),
                      ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                  ]))
    return table


# =============================================================================
# 文档模板（目录 + 书签 + 页眉页脚）
# =============================================================================

class ManualDoc(BaseDocTemplate):
    """带目录、PDF 书签与页眉页脚的文档模板。

    页脚左端要显示「当前章」，而章标题是流到哪算哪 —— 靠 ``afterFlowable``
    在读到一个 h1 时把章节名记下来；因为每章都以分页开始，页脚取到的
    一定是这一页真正的章名。
    """

    def __init__(self, filename, meta, **kw):
        super().__init__(filename, pagesize=A4,
                         leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                         topMargin=MARGIN_T, bottomMargin=MARGIN_B,
                         title=meta["title"], author=meta["author"],
                         subject=meta["subject"], creator=meta["creator"],
                         **kw)
        self.meta = meta
        self.current_chapter = ""
        self._toc_counter = 0
        frame = Frame(MARGIN_L, MARGIN_B, CONTENT_W,
                      PAGE_H - MARGIN_T - MARGIN_B, id="body",
                      leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        cover = Frame(0, 0, PAGE_W, PAGE_H, id="cover",
                      leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover], onPage=self._draw_cover),
            PageTemplate(id="body", frames=[frame],
                         onPage=self._header, onPageEnd=self._footer),
        ])

    # -- 目录 / 书签 -----------------------------------------------------
    def handle_documentBegin(self):
        """每遍重排开始时把书签序号归零。

        ``multiBuild`` 会反复调用 ``build()``，而 ``build()`` 又会调本方法。
        书签 key 里若带着一个跨遍累加的序号（ch1、ch2、ch3…），第二遍生成的
        key 就全变了 —— 目录的 ``_entries`` 每遍都不一样，``_allSatisfied()``
        永远不成立，最后抛 ``Index entries not resolved after 10 passes``。
        序号每次归零，key 才是稳定的（ch1 永远指第一章）。

        ``current_chapter`` 也要一起清 —— 目录页排在所有章节**之前**，页脚是
        在画页时实时取当前章名的；不清就会用到上一遍遗留的末章名，于是目录页
        的页脚挂着「第十七章」这种牛头不对马嘴的残留。
        """
        self._toc_counter = 0
        self.current_chapter = ""
        super().handle_documentBegin()

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        text = flowable.getPlainText()
        if name == "h1":
            self.current_chapter = text
            self._toc_counter += 1
            key = f"ch{self._toc_counter}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=False)
            self.notify("TOCEntry", (0, text, self.page, key))
        elif name == "h2":
            self._toc_counter += 1
            key = f"ch{self._toc_counter}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=1, closed=False)
            self.notify("TOCEntry", (1, text, self.page, key))

    # -- 封面 -------------------------------------------------------------
    def _draw_cover(self, canvas, doc):
        c = canvas
        c.saveState()
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        c.setFillColor(colors.HexColor(Ink.accent))
        c.rect(0, PAGE_H - 190, PAGE_W, 2.6, stroke=0, fill=1)

        c.setFillColor(colors.HexColor(Ink.headline))
        c.setFont("BODY_B", 31)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 296, "Python 语法手册")
        c.setFont("BODY", 14)
        c.setFillColor(colors.HexColor(Ink.secondary))
        c.drawCentredString(PAGE_W / 2, PAGE_H - 330, "—— 配 ServerTimeDemo 项目实例")

        # 分册时多出「册名 + 收录范围」两行，其下的分隔线与说明顺势下移；
        # 合订本（meta 里没有 volume）保持原来的一整套位置不动。
        volume = self.meta.get("volume")
        rule_y = PAGE_H - 372
        if volume:
            c.setFont("BODY_B", 21)
            c.setFillColor(colors.HexColor(Ink.accent))
            c.drawCentredString(PAGE_W / 2, PAGE_H - 368, volume)
            c.setFont("BODY", 10.5)
            c.setFillColor(colors.HexColor(Ink.secondary))
            c.drawCentredString(PAGE_W / 2, PAGE_H - 390,
                                self.meta.get("volume_sub", ""))
            rule_y = PAGE_H - 414

        c.setStrokeColor(colors.HexColor(Ink.rule))
        c.setLineWidth(0.7)
        c.line(PAGE_W / 2 - 90, rule_y, PAGE_W / 2 + 90, rule_y)

        c.setFillColor(colors.HexColor(Ink.text))
        c.setFont("BODY", 10.5)
        lines = [
            "从词法到工程约定，逐条对照真实代码",
            f"{self.meta['stat_files']} 个 Python 文件 · {self.meta['stat_lines']} 行 · "
            f"{self.meta['stat_tables']} 张数据表",
        ]
        y = rule_y - 30
        for line in lines:
            c.drawCentredString(PAGE_W / 2, y, line)
            y -= 22

        c.setFont("BODY", 9)
        c.setFillColor(colors.HexColor(Ink.muted))
        y = 196
        for line in [f"项目版本 {self.meta['app_version']}",
                     f"手册版本 {self.meta['manual_version']}",
                     f"生成日期 {self.meta['date']}"]:
            c.drawCentredString(PAGE_W / 2, y, line)
            y -= 18
        c.setFont("BODY", 8.4)
        # 「全三册 · 本册为上册」这类归属说明，只有分册时才画
        if self.meta.get("volume_set"):
            c.drawCentredString(PAGE_W / 2, 138, self.meta["volume_set"])
        c.drawCentredString(PAGE_W / 2, 118,
                            "本手册的每一段示例代码都摘自本项目源码，未作伪写")
        c.restoreState()

    # -- 页眉 / 页脚 -------------------------------------------------------
    def _header(self, canvas, doc):
        c = canvas
        c.saveState()
        c.setFont("BODY", 8)
        c.setFillColor(colors.HexColor(Ink.muted))
        c.drawString(MARGIN_L, PAGE_H - MARGIN_T + 20, self.meta["title"])
        c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 20,
                          self.meta["header_right"])
        c.setStrokeColor(colors.HexColor(Ink.rule_soft))
        c.setLineWidth(0.5)
        c.line(MARGIN_L, PAGE_H - MARGIN_T + 14, PAGE_W - MARGIN_R,
               PAGE_H - MARGIN_T + 14)
        c.restoreState()

    def _footer(self, canvas, doc):
        c = canvas
        c.saveState()
        c.setStrokeColor(colors.HexColor(Ink.rule_soft))
        c.setLineWidth(0.5)
        c.line(MARGIN_L, MARGIN_B - 16, PAGE_W - MARGIN_R, MARGIN_B - 16)
        c.setFont("BODY", 8)
        c.setFillColor(colors.HexColor(Ink.muted))
        if self.current_chapter:
            c.drawString(MARGIN_L, MARGIN_B - 29, self.current_chapter)
        c.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 29, str(doc.page))
        c.restoreState()


# =============================================================================
# 构建
# =============================================================================

def build(blocks, out_path: Path, meta: dict):
    """把块列表渲染成 PDF，返回 ``(输出路径, 页数)``。

    ``meta`` 里带上 ``volume`` / ``volume_sub`` / ``volume_set`` / ``volume_note``
    就是分册封面（多两行册名），不带就是合订本封面 —— 两者用同一套模板。
    """
    global STYLES
    register_fonts()
    STYLES = build_styles()

    story = []
    toc = TableOfContents()
    toc.levelStyles = [STYLES["toc0"], STYLES["toc1"]]
    toc.dotsMinLevel = 0
    toc._rightIndent = 2
    story.append(NextPageTemplate("cover"))
    story.append(Spacer(1, 1))
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())
    story.append(Paragraph("目录", STYLES["h1_plain"]))
    story.append(ChapterRule(CONTENT_W))
    if meta.get("volume_note"):
        story.append(Spacer(1, 8))
        story.append(Paragraph(md(meta["volume_note"]), STYLES["volume_note"]))
    story.append(Spacer(1, 8))
    story.append(toc)
    story.append(PageBreak())

    for block in blocks:
        story.extend(_render(block))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = ManualDoc(str(out_path), meta)
    doc.multiBuild(story)
    return out_path, doc.page


def _render(block):
    kind = block[0]

    if kind == "h1":
        return [Paragraph(md(block[1]), STYLES["h1"]),
                ChapterRule(CONTENT_W), Spacer(1, 12)]
    if kind == "h2":
        return [Paragraph(md(block[1]), STYLES["h2"])]
    if kind == "h3":
        return [Paragraph(md(block[1]), STYLES["h3"])]
    if kind == "p":
        return [Paragraph(md(block[1]), STYLES["body"])]
    if kind == "ul":
        return [Paragraph(md(t), STYLES["bullet"], bulletText="·")
                for t in block[1]] + [Spacer(1, 5)]
    if kind == "ol":
        out = []
        for i, t in enumerate(block[1], 1):
            out.append(Paragraph(md(t), STYLES["ordered"], bulletText=f"{i}."))
        return out + [Spacer(1, 5)]
    if kind == "code":
        return [Spacer(1, 2), _code_flowable(block[2], block[1]),
                Spacer(1, 9)]
    if kind == "out":
        return [Spacer(1, 2),
                _code_flowable(block[1], lang="text"), Spacer(1, 9)]
    if kind == "table":
        return [Spacer(1, 2), _table_flowable(block[1]), Spacer(1, 10)]
    if kind == "note":
        return _box_flowable(block[1], block[2], Ink.note_bg, Ink.note_edge)
    if kind == "warn":
        return _box_flowable(block[1], block[2], Ink.warn_bg, Ink.warn_edge)
    if kind == "ok":
        return _box_flowable(block[1], block[2], Ink.ok_bg, Ink.ok_edge)
    if kind == "quote":
        return [Spacer(1, 1), _quote_flowable(block[1]), Spacer(1, 9)]
    if kind == "image":
        return [Spacer(1, 3), _image_flowable(block[1], block[2] if len(block) > 2 else 0.86),
                Spacer(1, 9)]
    if kind == "caption":
        return [Paragraph(md(block[1]), STYLES["caption"])]
    if kind == "spacer":
        return [Spacer(1, block[1])]
    if kind == "pagebreak":
        return [PageBreak()]
    raise ValueError(f"未知的块类型：{kind}")


def _quote_flowable(text):
    return Table([[XPreformatted(plain_pre(text), STYLES["quote"])]],
                 colWidths=[CONTENT_W],
                 style=TableStyle([
                     ("LINEBEFORE", (0, 0), (0, -1), 2.0, Ink.rule),
                     ("LEFTPADDING", (0, 0), (-1, -1), 10),
                     ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                     ("TOPPADDING", (0, 0), (-1, -1), 3),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                 ]))
