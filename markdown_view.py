# -*- coding: utf-8 -*-
"""
================================================================================
Markdown 渲染（Typora 风格）
================================================================================
把一段 Markdown 渲染进 tk.Text。服务于两处预览：

  - 笔记编辑器（NoteEditorDialog）右侧的「渲染预览」
  - 笔记页（StudyNotesPage）底部的「笔记预览」

为什么单独一个模块
------------------------------------------------------------------------------
这两处原本各写一套：编辑器里那套比较完整（`NoteEditorDialog._render_*`），
笔记页那边只配了四个 tag、正文直接 `insert(note.content)` —— 于是同一篇笔记
在编辑器里是有排版的，在页面里却是源码。渲染逻辑收到这里之后，两处共用一份
实现，不会再各走各的。

为什么是 Typora
------------------------------------------------------------------------------
按 Typora 默认主题（GitHub 风味）的比例还原：

    正文 16px / 行高 1.6   标题 2.25 / 1.75 / 1.5 / 1.25 / 1 / 1 (em)
    h1 h2 带 1px 下边框    代码块 #f8f8f8 浅灰、无边框、padding 1em
    引用 4px 左侧竖线      分隔线比标题下框线更明显

tk.Text 的能力缺口（只能近似，别当成 bug 去"修"）
------------------------------------------------------------------------------
  - **没有行高**：`spacing2` 模拟折行的行距，`spacing1`/`spacing3` 模拟段前段后距
  - **tag 画不出边框**：h1/h2 的下边框用一条极浅的「─」行代替，引用块的左侧
    竖线用「▎」承担
  - **没有圆角**：代码块只有浅灰底，画不出 Typora 那个 3px 圆角

颜色一律取 ui_theme 的 token，不搬 Typora 的蓝色链接 —— 全站的强调色只有近黑
一个，让笔记页成为唯一的彩色区域不划算（取舍理由见 UI_NOTES.md）。

「生成区」是这条单色规矩上唯一开的口子
------------------------------------------------------------------------------
笔记正文里可以用一对 HTML 注释圈出「系统自动生成」的一段（标记常量的唯一定义
在 study_notes_db：GEN_START / GEN_END；「Excel 宝典」把一轮自测整理成笔记模板
就靠它）。圈内的文字换上另一套样式：

    颜色  正文冷灰蓝、底色淡蓝、行首一条浅蓝竖线
    字体  宋体（系统里没有宋体时自动退回全站字体）
    排版  整块缩进，字号小一号

开这个口子的理由：**生成区是机器产物，长得像机器输出本身就是功能** ——
一眼看得出「这段不是我写的」，改起来才有分寸。颜色仍然只从 ui_theme 取
（强调色就是 palette.link），没有引入第二个色相。

作者：代可行
日期：2026-09-20
================================================================================
"""

import html as _html
import re
import tkinter.font as tkfont
from pathlib import Path

from study_notes_db import GEN_END, GEN_START
from ui_theme import MAIN_PALETTE as PALETTE


# 排版常量：字体族沿用全站 token，避免同一页出现两个「雅黑」
FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"

# 正文基准字号（pt）。两处预览都用它，保证同一篇笔记在哪看都一个样。
BASE_SIZE = 10


# =============================================================================
# 生成区主题
# =============================================================================
# 生成区（见模块头）要跟「自己写的」一眼分得开，所以**颜色 / 字体 / 排版**三样
# 都得动，不是加一层底色那么简单：
#
#   颜色  正文 GEN_FG、底色 GEN_BG、行首竖线 GEN_BAR、强调色沿用一个 palette token
#   字体  宋体（Windows 中文环境标配；真没有就退回 FONT_FAMILY，见 _gen_family）
#   排版  整块缩进 GEN_INDENT、字号减 1pt、每行行首一条竖线
#
# 底色挑冷调：#f7f7f7（surface_alt）是代码块在用的**暖灰**，再用一个中性灰
# 就分不出「这是代码」还是「这是生成区」了。
GEN_PREFIX = "gen_"          # 生成区 tag 统一前缀，一套影子 tag 家族
GEN_BG = "#eef3f9"
GEN_CODE_BG = "#e3ebf4"      # 生成区里的代码：比底色再深一档，才分得出「这是代码」
GEN_FG = "#33475b"
GEN_BAR = "#b9c9db"
GEN_ACCENT = PALETTE.link    # 不引入第二个色相：全站唯一的「墨蓝」就是它
# 生成区的字体。★ 必须给一串候选，不能只写 "SimSun"：中文版 Windows 上
# Tk 报出来的族名是**本地化**的（'宋体' / '新宋体' / '楷体'），英文名
# SimSun 常常查不到（实测这台机器 234 个族里只有 '宋体'，没有 'SimSun'）。
# 只写英文名的话 _gen_family 会一路退回雅黑 ——「字体有区别」这条要求
# 就悄悄失效了，而且界面上看不出哪里不对。
GEN_FONT_CANDIDATES = ("宋体", "SimSun", "新宋体", "NSimSun", "楷体", "KaiTi")
GEN_INDENT = 14              # 整块左缩进（像素）
GEN_BAR_CHAR = "▎"
# gen_ 家族覆盖哪些基础 tag。hr / hrule / empty 是「版面装饰」，不参与主题 ——
# 生成区里出现的分隔线仍然是一条普通分隔线（换色反而像坏掉了）。
GEN_TAG_NAMES = (
    "text", "p", "li", "quote", "quote_bar", "codeblock", "codeblock_lang",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "bold", "italic", "strike", "code", "image", "link",
)

# ── 行内语法 ────────────────────────────────────────────────────────────────
# **分支顺序即优先级**：先认行内代码，再认图片 / 链接，然后是删除线、加粗，
# 最后才是斜体。顺序反了，`code` 里带星号、或 `**粗**` 里嵌反引号这类写法
# 就会切错。
INLINE_PATTERN = re.compile(
    r"(`[^`]+`)"
    r"|(!\[[^\]]*\]\([^)]*\))"
    r"|(\[[^\]]+\]\([^)]*\))"
    r"|(~~[^~]+~~)"
    r"|(\*\*[^*]+\*\*)"
    r"|(\*[^*]+\*)"
)

# 围栏代码块：``` 或 ~~~，后面可跟语言名
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+#.-]*)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_UL_RE = re.compile(r"^[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
_TASK_RE = re.compile(r"^[-*+]\s+\[([ xX])\]\s+(.*)$")
_FENCE_ONLY_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")

_LINE_CHAR = "─"          # 横线用字符画：tk.Text 的 tag 画不出 border
_RULE_MIN = 26            # 面板窄到算不出宽度时的兜底长度


# =============================================================================
# tag 配置
# =============================================================================

def setup_tags(text_widget, *, base: int = BASE_SIZE) -> None:
    """
    为预览用的 Text 配置整套 Typora 风格 tag。

    ★ tag 优先级 = 创建顺序（后建的盖先建的）。因此**容器 tag 必须先建、
      行内 tag 必须后建**：否则列表项里的 `code` 会被 li 的字体盖掉，
      反引号里的字就不会变等宽。

    参数:
        text_widget - 目标 tk.Text
        base        - 正文基准字号（pt），各级标题按 Typora 的比例推算
    """
    w = text_widget
    mono = (MONO_FAMILY, base - 1)

    # ── 容器 ────────────────────────────────────────────────────────────────
    w.tag_configure("text", font=(FONT_FAMILY, base))
    # 段间距交给 spacing1/spacing3，折行的行距交给 spacing2 —— Tk 没有 line-height，
    # 这三者合起来才是 Typora 那个 1.6 的松弛感。不靠插空行，否则段落间距不可控。
    w.tag_configure("p", font=(FONT_FAMILY, base),
                    spacing1=3, spacing2=5, spacing3=9,
                    lmargin1=2, lmargin2=2)
    w.tag_configure("li", font=(FONT_FAMILY, base),
                    lmargin1=20, lmargin2=34, spacing2=5, spacing3=6)
    # tk.Text 不能给 tag 画左边框，引用块的书脊线由渲染时插入的「▎」承担
    w.tag_configure("quote", font=(FONT_FAMILY, base), foreground=PALETTE.text_secondary,
                    lmargin1=16, lmargin2=16, background="#f7f7f7",
                    spacing1=6, spacing3=6)
    w.tag_configure("quote_bar", font=(FONT_FAMILY, base), foreground="#cfcfcf",
                    lmargin1=16, lmargin2=16, background="#f7f7f7",
                    spacing1=6, spacing3=6)
    # 代码块：Typora 是 #f8f8f8 无边框 + 圆角。这里去掉 relief —— 宁可没有边框，
    # 也不要 Tk 那个色不可控的立体硬边。
    w.tag_configure("codeblock", font=mono, background=PALETTE.surface_alt,
                    foreground=PALETTE.text_primary,
                    lmargin1=14, lmargin2=14, spacing1=9, spacing3=9)
    # 围栏里的语言名（如 python），比代码本身更淡，别抢戏
    w.tag_configure("codeblock_lang", font=(MONO_FAMILY, base - 2),
                    foreground=PALETTE.text_muted, background=PALETTE.surface_alt,
                    lmargin1=14, lmargin2=14, spacing1=9)
    # 真分隔线（---）：Typora 里比标题下框线更实
    w.tag_configure("hr", font=(FONT_FAMILY, 9), foreground="#d8d8d8",
                    justify="center", spacing1=14, spacing3=14)
    # 标题下框线（h1/h2 的 border-bottom）：极浅、紧贴标题
    w.tag_configure("hrule", font=(FONT_FAMILY, 8), foreground="#ececec",
                    spacing1=4, spacing3=8)
    w.tag_configure("empty", font=(FONT_FAMILY, base),
                    foreground=PALETTE.text_muted, spacing1=8)

    # ── 标题 H1~H6 ──────────────────────────────────────────────────────────
    # 层级只靠「字号 + 段间距」表达。旧版给六级标题配了六个不同灰度，正文一多
    # 就分不出主次，那是把层级交给"变灰"了。字号比例照 Typora。
    h_sizes = {1: base + 10, 2: base + 7, 3: base + 4,
               4: base + 2, 5: base + 1, 6: base}
    h_space = {1: (20, 4), 2: (18, 4), 3: (15, 3), 4: (13, 3), 5: (11, 2), 6: (11, 2)}
    h_color = {1: PALETTE.text_primary, 2: PALETTE.text_primary,
               3: PALETTE.text_primary, 4: PALETTE.text_primary,
               5: PALETTE.text_secondary, 6: PALETTE.text_muted}
    for lvl in range(1, 7):
        s1, s3 = h_space[lvl]
        w.tag_configure(f"h{lvl}", font=(FONT_FAMILY, h_sizes[lvl], "bold"),
                        foreground=h_color[lvl], spacing1=s1, spacing3=s3,
                        lmargin1=2, lmargin2=2)

    # ── 行内（优先级最高，必须最后建）──────────────────────────────────────
    w.tag_configure("bold", font=(FONT_FAMILY, base, "bold"))
    w.tag_configure("italic", font=(FONT_FAMILY, base, "italic"))
    w.tag_configure("strike", font=(FONT_FAMILY, base, "overstrike"),
                    foreground=PALETTE.text_muted)
    # 旧版是 #c7254e 品红前景 + 灰底，全站仅有的彩色之一。改为一律正文色，
    # 靠浅灰底表达"这是代码"就够了。
    w.tag_configure("code", font=mono, background=PALETTE.surface_alt,
                    foreground=PALETTE.text_primary)
    # 链接色取 palette.link（极低饱和墨蓝）——纯灰链接在正文里只剩"可点"没有
    # "可辨"，高饱和蓝又和纯灰阶冲突，这个值是两个极端之间的落点。
    w.tag_configure("image", font=(FONT_FAMILY, base, "italic"), foreground=PALETTE.link)
    w.tag_configure("link", font=(FONT_FAMILY, base, "underline"), foreground=PALETTE.link)

    # ── 生成区（gen_ 影子家族）────────────────────────────────────────────
    _setup_gen_tags(w, base=base)


def _setup_gen_tags(text_widget, *, base: int) -> None:
    """配置生成区那一套 tag（见模块头与 GEN_* 常量）。

    ★ 建 tag 的**顺序**就是优先级，动它之前先想清楚：

      1. ``gen_zone`` 只定底色与缩进，但必须建在**基础 tag 之后** ——
         它靠「后建的盖先建的」去压掉 p / li / quote 各自的缩进，
         整块生成区才会缩进一致；
      2. ``gen_zone`` 又要建在 gen_ 家族**之前**：底色由 gen_p / gen_code
         这些自己声明，于是代码块能在生成区里保住自己那份略深的底，
         不会整块糊成一个颜色；
      3. ``gen_`` 行内 tag 必须建在 gen_ 容器之后 —— 否则生成区里的行内
         代码会被 gen_p 的字体盖掉，等宽就没了（基础 tag 那边同一个坑）。

    字体一律换成宋体：这是「字体有区别」这条要求的落点，也是最省事的一种
    区分方式 —— 换字号只是排版，换字体是一眼就能看出来的另一种字。
    """
    w = text_widget
    family = _gen_family(w)
    mono = (MONO_FAMILY, base - 2)

    # 1) 整块：底色 + 缩进
    w.tag_configure("gen_zone", background=GEN_BG,
                    lmargin1=GEN_INDENT, lmargin2=GEN_INDENT + 12)

    # 2) 生成区的容器 tag
    w.tag_configure(GEN_PREFIX + "text", font=(family, base - 1),
                    foreground=GEN_FG, background=GEN_BG)
    w.tag_configure(GEN_PREFIX + "p", font=(family, base - 1),
                    foreground=GEN_FG, background=GEN_BG,
                    spacing1=3, spacing2=5, spacing3=9)
    w.tag_configure(GEN_PREFIX + "li", font=(family, base - 1),
                    foreground=GEN_FG, background=GEN_BG,
                    spacing2=5, spacing3=6)
    w.tag_configure(GEN_PREFIX + "quote", font=(family, base - 1),
                    foreground=GEN_ACCENT, background=GEN_BG,
                    spacing1=6, spacing3=6)
    w.tag_configure(GEN_PREFIX + "quote_bar", font=(family, base - 1),
                    foreground=GEN_BAR, background=GEN_BG,
                    spacing1=6, spacing3=6)
    w.tag_configure(GEN_PREFIX + "codeblock", font=mono, background=GEN_CODE_BG,
                    foreground=GEN_FG, spacing1=9, spacing3=9)
    w.tag_configure(GEN_PREFIX + "codeblock_lang", font=(MONO_FAMILY, base - 3),
                    foreground=GEN_ACCENT, background=GEN_CODE_BG, spacing1=9)
    h_sizes = {1: base + 9, 2: base + 6, 3: base + 3,
               4: base + 1, 5: base, 6: base - 1}
    for lvl in range(1, 7):
        # 段前段后间距**照抄基础标题 tag**（直接读回来，而不是再抄一份数字 ——
        # 不然以后有人调基础标题的行距，生成区的标题就悄悄对不上了）。
        # ★ 这一条以前漏了：生成区的标题会死死贴在上一段上。它只有「真开窗口
        #   量一遍行盒高度」才看得出来，静态检查与肉眼扫一眼都发现不了 ——
        #   机理见 _apply_gen_theme 里「行首字符与 spacing」那段说明。
        w.tag_configure(GEN_PREFIX + f"h{lvl}",
                        font=(family, h_sizes[lvl], "bold"),
                        foreground=GEN_FG if lvl <= 4 else GEN_ACCENT,
                        background=GEN_BG,
                        spacing1=w.tag_cget(f"h{lvl}", "spacing1") or 0,
                        spacing3=w.tag_cget(f"h{lvl}", "spacing3") or 0)

    # 3) 生成区的行内 tag（最后建，压住上面的容器）
    w.tag_configure(GEN_PREFIX + "bold", font=(family, base - 1, "bold"))
    w.tag_configure(GEN_PREFIX + "italic", font=(family, base - 1, "italic"))
    w.tag_configure(GEN_PREFIX + "strike", font=(family, base - 1, "overstrike"),
                    foreground=GEN_ACCENT)
    w.tag_configure(GEN_PREFIX + "code", font=mono, background=GEN_CODE_BG,
                    foreground=GEN_FG)
    w.tag_configure(GEN_PREFIX + "image", font=(family, base - 1, "italic"),
                    foreground=GEN_ACCENT)
    w.tag_configure(GEN_PREFIX + "link", font=(family, base - 1, "underline"),
                    foreground=GEN_ACCENT)

    # 4) 行首竖线。自带底色**和缩进** —— 它可能落在标题 / 列表 / 引用的行首，
    #    那几种的底色都一样，所以竖线不会在色块里露出接缝。
    #
    #    ★ 缩进必须自带：竖线是在 gen_zone 打完之后才插进去的，插进去的字符
    #    会**把 gen_zone 的区间切成一段一段**（Tk 不给插入的文字继承区间起点
    #    上的 tag），于是每个生成行的行首那个字符身上只有 gen_bar。Tk 是按
    #    「行首字符身上优先级最高的那个 lmargin」定这一行的缩进的 —— 只给
    #    gen_zone 设、不给 gen_bar 设，整块生成区就会集体贴到最左边，
    #    底色还在、缩进没了（实测就是这么回事）。
    #
    #    ★★ 同理，**spacing1 / spacing3 也看行首字符**。所以光靠这个 tag 还不够：
    #    插进去的竖线把段前段后的间距一起吃掉了，生成区里所有段落挤成一坨
    #    （实测正文两段相隔 31px，生成区里只剩 12px = 一整行行高）。修法是插入时
    #    **把这一行自己的 gen_ 类型 tag 一起带上**（见 _apply_gen_theme）—— 间距
    #    就落回 gen_p / h2 / li 基础 tag，而 lmargin / 字体 / 底色仍归 gen_bar
    #    （它创建得最晚、优先级最高）。
    w.tag_configure("gen_bar", font=(family, base - 1),
                    foreground=GEN_BAR, background=GEN_BG,
                    lmargin1=GEN_INDENT, lmargin2=GEN_INDENT + 12)


def _gen_family(widget) -> str:
    """挑一个系统里真有的衬线中文字体给生成区用；一个都没有才退回全站字体。

    盲目指定一个不存在的族，Tk 会静默换成某个默认字体 —— 观感不可控，
    而且「字体有区别」这条要求会悄悄失效（界面上还看不出哪里不对）。
    所以先查一次系统字体表，按 ``GEN_FONT_CANDIDATES`` 的顺序挑第一个命中的。
    """
    try:
        available = set(tkfont.families(widget))
    except Exception:
        return FONT_FAMILY
    for name in GEN_FONT_CANDIDATES:
        if name in available:
            return name
    return FONT_FAMILY


# =============================================================================
# 渲染
# =============================================================================

def rule_length(text_widget) -> int:
    """
    算一条「撑满面板」的横线要几个「─」。

    Typora 的标题下边框是 `width: 100%` 的，这里用等宽字符拼，只能按当前像素
    宽度反推字符数。控件还没上屏（宽=1）时给个能看的兜底值。
    """
    try:
        px = int(text_widget.winfo_width())
    except Exception:
        px = 0
    if px <= 1:
        return 40
    try:
        unit = max(1, tkfont.Font(font=(FONT_FAMILY, BASE_SIZE)).measure(_LINE_CHAR))
    except Exception:
        return 40
    return max(_RULE_MIN, px // unit - 2)


def insert_inline(text_widget, text: str, base_tag: str) -> None:
    """
    把一行文本按行内 Markdown 语法**分段插入**，让加粗 / 斜体 / 删除线 /
    行内代码 / 链接 / 图片占位各自带上 tag。

    只删标记不打 tag 是不够的：那样预览里加粗和正文长得一模一样，行内 tag 配了
    也从来没被用上。
    """
    pos = 0
    for m in INLINE_PATTERN.finditer(text):
        if m.start() > pos:
            text_widget.insert("end", text[pos:m.start()], base_tag)
        seg = m.group(0)
        if seg.startswith("`"):
            text_widget.insert("end", seg[1:-1], ("code", base_tag))
        elif seg.startswith("!["):
            label = re.match(r"!\[([^\]]*)\]", seg).group(1)
            text_widget.insert("end", f"[图片: {label}]", ("image", base_tag))
        elif seg.startswith("["):
            label = re.match(r"\[([^\]]+)\]", seg).group(1)
            text_widget.insert("end", label, ("link", base_tag))
        elif seg.startswith("~~"):
            text_widget.insert("end", seg[2:-2], ("strike", base_tag))
        elif seg.startswith("**"):
            text_widget.insert("end", seg[2:-2], ("bold", base_tag))
        else:
            text_widget.insert("end", seg[1:-1], ("italic", base_tag))
        pos = m.end()
    if pos < len(text):
        text_widget.insert("end", text[pos:], base_tag)


def split_by_markers(content: str) -> list:
    """
    按生成区标记把正文切成 ``[(是否生成区, 文本), …]``。

    标记行**本身不参与渲染** —— 它们只是给机器看的边界。只认「整行就是一个
    标记」的写法：正文里恰好在句子中间引用了这几个字（比如一篇讲这个格式的
    笔记）不该把渲染切成两半。
    """
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    segments: list = []
    buf: list = []
    in_gen = False

    def flush():
        if buf:
            segments.append((in_gen, "\n".join(buf)))
            buf.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == GEN_START:
            flush()                 # 标记之前那段归「自己写的」
            in_gen = True
            continue
        if stripped == GEN_END:
            flush()                 # 标记之内那段归「生成的」
            in_gen = False
            continue
        buf.append(line)
    flush()
    return segments


def _apply_gen_theme(text_widget, start: str, end: str) -> None:
    """
    给 ``[start, end)`` 这一段换上生成区的样式（见模块头）。

    做法是**渲染完再换 tag**：先把这一段当普通 Markdown 渲染出来，然后

      ① 每个基础 tag 落在区间内的范围，原样再打一份带 ``gen_`` 前缀的；
      ② 整段打一个 ``gen_zone``（底色 + 缩进）；
      ③ 逐行在最前面插一条竖线。

    为什么不在渲染时直接选 gen_ tag：渲染循环里有四十来处 tag 字面量，挨个改
    是纯粹的体力活 + 大面积出错面。而「生成区 = 普通渲染 + 换 tag」这条规则
    一句话说得清，优先级交给 `_setup_gen_tags` 的创建顺序去保证。
    """
    w = text_widget
    if w.compare(start, "==", end):
        return

    for name in GEN_TAG_NAMES:
        ranges = w.tag_ranges(name)
        for index in range(0, len(ranges), 2):
            lo, hi = str(ranges[index]), str(ranges[index + 1])
            if w.compare(lo, ">=", start) and w.compare(hi, "<=", end):
                w.tag_add(GEN_PREFIX + name, lo, hi)
    w.tag_add("gen_zone", start, end)

    # 竖线**从后往前**插：每插一次后面的下标就整体右移。正着插的话，第一行
    # 插完第二行就不是原来那一行了 —— 这是本文件里最容易被写错的一处。
    first = int(str(start).split(".")[0])
    last = int(str(end).split(".")[0])
    for row in range(last, first - 1, -1):
        if not w.get(f"{row}.0", f"{row}.end"):
            continue                    # 空行不插，否则色块里会飘一条孤线
        names = w.tag_names(f"{row}.0")
        tags = set(names)
        # 标题下那根浅横线本身就是装饰；引用行自带一条 «▎» 书脊线，
        # 再叠一条会变成「▎ ▎」——看着像坏了。
        if "hrule" in tags or "quote_bar" in tags:
            continue
        # ★ 插进去的字符**不会继承这一行原有的 tag**，于是它成了行首字符，而 Tk
        #   的 spacing1 / spacing3 正是取自「行首字符上优先级最高的 tag」。只打
        #   gen_bar 的话，生成区里所有段间距都会被吃掉，段落挤成一坨（实测：正文
        #   两段相隔 31px，生成区里只剩 12px = 一整行行高，肉眼看着就是「糊在一块」）。
        #   所以把这一行原有的 gen_ tag **整套**都带上：间距就落回 gen_p / h2 / li
        #   基础 tag。lmargin、字体、底色仍归 gen_bar（创建最晚、优先级最高），
        #   所以缩进与竖线的一致性不受影响。
        #   注意要带**整套**而不是「最具体的那个」：一行可能同时带 gen_p 与 gen_bold
        #   （整段加粗的那种行），而 gen_bold 自己不设间距 —— 只带它的话间距照样丢。
        kind_tags = [name for name in names
                     if name.startswith(GEN_PREFIX) and name != "gen_zone"]
        w.insert(f"{row}.0", GEN_BAR_CHAR + " ", ("gen_bar", *kind_tags))

    # 空行的底色**不用另外补**：Tk 会把段前段后的 spacing 也一起涂上背景，
    # 而渲染器本来就不为 Markdown 空行产出空行（空行只是「结束上一段」），
    # 所以整块底色天然是连着的（量过像素：整段一直是 GEN_BG，没有白道）。
    # 早先这里给空行的换行符补过一道 tag，结果那个换行符**会跟着后面的插入
    # 一路漂到文末**（tag 粘的是字符不是位置），把「我的补充」后面也染上了 ——
    # 所以这里必须什么都不做，别再加回来。


def render(text_widget, content: str, *, empty_hint: str = "（笔记内容为空）") -> None:
    """
    把一段 Markdown 渲染进 Text（只读控件会被临时解锁后再锁回）。

    支持：围栏代码块（含未闭合的，编辑到一半很常见）、H1~H6、引用、无序 /
    有序 / 任务列表、分隔线、粗体 / 斜体 / 删除线 / 行内代码 / 链接 / 图片，
    以及**生成区**（一对 HTML 注释圈起来的那段，见模块头）—— 生成区会换成
    另一套颜色 / 字体 / 排版，标记行自己不显示。

    参数:
        text_widget - 目标 tk.Text
        content     - Markdown 原文
        empty_hint  - 内容为空时的提示文案；传 "" 则什么都不显示
    """
    w = text_widget
    was_disabled = str(w.cget("state")) == "disabled"
    if was_disabled:
        w.configure(state="normal")
    w.delete("1.0", "end")

    if not (content or "").strip():
        if empty_hint:
            w.insert("end", empty_hint, "empty")
        if was_disabled:
            w.configure(state="disabled")
        return

    # 一段一段渲染：生成区那几段渲染完再换 tag。
    #
    # ★ 段边界必须用 ``index("end-1c")``，**不能用** ``index("end")``。
    #   Tk 的 Text 永远自带一个收尾换行，``end`` 指的是它**后面**那一行；
    #   拿它当段起点，整段就往前错一行 —— 实测的表现是：生成区第一行没拿到
    #   竖线，而多出来的那一行把「我的补充」也染上了底色。
    #   ``end-1c`` 正落在那个收尾换行上，也就是下一次 ``insert("end", …)``
    #   真正落笔的位置。
    for is_gen, chunk in split_by_markers(content):
        if not chunk.strip():
            continue
        start = w.index("end-1c")
        _render_markdown(w, chunk)
        if is_gen:
            _apply_gen_theme(w, start, w.index("end-1c"))

    if was_disabled:
        w.configure(state="disabled")


def _render_markdown(text_widget, text: str) -> None:
    """
    把一段**已经规范化过行尾**的 Markdown 渲染到控件末尾。

    从 render() 里拆出来只为一件事：生成区要「先按普通样式渲染、再整段换
    tag」，那就得能一段一段地渲染。除签名外，这里一个字节的行为都没变。
    """
    w = text_widget
    lines = text.split("\n")

    para_buf: list = []        # 连续普通行攒成一段（Typora 里软换行属同段）
    list_buf: list = []        # [(kind, 文本)]，kind: ul / ol / task
    in_code = False
    fence_lang = ""
    ol_next = 1                # 有序列表的序号游标

    def flush_para():
        if not para_buf:
            return
        insert_inline(w, " ".join(para_buf), "p")
        w.insert("end", "\n", "p")
        para_buf.clear()

    def flush_list():
        nonlocal ol_next
        if not list_buf:
            return
        for kind, item in list_buf:
            if kind == "ul":
                w.insert("end", "•   ", "li")
            elif kind == "ol":
                w.insert("end", f"{ol_next}.   ", "li")
                ol_next += 1
            else:                       # task
                checked, label = item
                w.insert("end", "☑   " if checked else "☐   ", "li")
                insert_inline(w, label, "li")
                w.insert("end", "\n", "li")
                continue
            insert_inline(w, item, "li")
            w.insert("end", "\n", "li")
        list_buf.clear()
        ol_next = 1

    def flush_all():
        flush_para()
        flush_list()

    for line in lines:
        fence = _FENCE_RE.match(line)

        # ── 围栏：开 / 闭都走这里 ──────────────────────────────────────────
        if fence:
            if in_code:
                in_code = False
                fence_lang = ""
                w.insert("end", "\n", "codeblock")   # 代码块下方留白
            else:
                flush_all()
                in_code = True
                fence_lang = fence.group(2) or ""
                if fence_lang:
                    w.insert("end", f"{fence_lang}\n", "codeblock_lang")
                    w.insert("end", "", "codeblock")
            continue

        # ── 代码块内：原样保留，不做任何行内解析 ───────────────────────────
        if in_code:
            w.insert("end", line + "\n", "codeblock")
            continue

        stripped = line.strip()

        # 空行：结束当前块
        if not stripped:
            flush_all()
            continue

        # 分隔线（--- / *** / ___）。必须在列表判断之前：`---` 会被 - 列表吃掉
        if _FENCE_ONLY_RE.match(stripped):
            flush_all()
            w.insert("end", _LINE_CHAR * rule_length(w) + "\n", "hr")
            continue

        m = _HEADING_RE.match(stripped)
        if m:
            flush_all()
            level = len(m.group(1))
            tag = f"h{level}"
            insert_inline(w, m.group(2).strip(), tag)
            w.insert("end", "\n", tag)
            # Typora 的 h1/h2 带 1px 下边框；h3 及以下没有。用一条极浅的
            # 「─」行代替 —— tag 画不出 border。
            if level <= 2:
                w.insert("end", _LINE_CHAR * rule_length(w) + "\n", "hrule")
            continue

        if stripped.startswith(">"):
            flush_all()
            quote_text = _QUOTE_RE.match(stripped).group(1)
            # 书脊线与正文共用同一组 lmargin/背景/间距，拼在一行里看不出接缝
            w.insert("end", "▎  ", ("quote", "quote_bar"))
            insert_inline(w, quote_text, "quote")
            w.insert("end", "\n", "quote")
            continue

        m = _TASK_RE.match(stripped)
        if m:
            flush_para()
            list_buf.append(("task", (m.group(1).lower() == "x", m.group(2))))
            continue

        m = _UL_RE.match(stripped)
        if m:
            flush_para()
            list_buf.append(("ul", m.group(1)))
            continue

        m = _OL_RE.match(stripped)
        if m:
            flush_para()
            list_buf.append(("ol", m.group(2)))
            continue

        # 普通行：攒进段落缓冲（软换行算同一段，与 Typora 一致）
        flush_list()
        para_buf.append(stripped)

    # 收尾：未闭合的代码块就让它保持打开状态（编辑到一半的常态）
    flush_all()


# =============================================================================
# 浏览器预览用的 HTML（这条路径才能真正 100% 还原 Typora）
# =============================================================================

def build_html(content: str, *, base_dir=None, title: str = "笔记预览") -> str:
    """
    把 Markdown 转成自带样式的完整 HTML 字符串。

    为什么还要 HTML 版：tk.Text 画不出 border / 圆角 / 行高，这里的 CSS 反而能
    1:1 还原 Typora 的排版。所以「浏览器预览」不是重复功能，是完整版。

    生成区（见模块头）在这条路径上包一层 ``.genzone``，用 CSS 做冷底 + 左侧
    色条 —— 真正画得出竖线的地方，就不用像 tk.Text 那边拿「▎」硬凑。

    参数:
        content  - Markdown 原文
        base_dir - 相对图片路径的解析基准（通常是数据库所在目录）
        title    - <title> 文案
    """
    parts: list = []
    for is_gen, chunk in split_by_markers(content):
        if not chunk.strip():
            continue
        fragment = _markdown_fragment(chunk, base_dir=base_dir)
        if is_gen:
            fragment = f'<div class="genzone">\n{fragment}\n</div>'
        parts.append(fragment)
    return _HTML_SHELL.format(
        title=_html.escape(title), body="".join(parts),
        # 生成区的几个色值也走 format，别在 CSS 里再硬编码一遍 ——
        # 两处各写一份，改的时候必然漏一处。
        gen_bg=GEN_BG, gen_code_bg=GEN_CODE_BG, gen_fg=GEN_FG,
        gen_bar=GEN_BAR, gen_accent=GEN_ACCENT,
    )


def _markdown_fragment(content: str, *, base_dir=None) -> str:
    """
    单段 Markdown → HTML 片段（不含 <html> 外壳）。

    ★ 所有替换都在 ``_html.escape`` **之后**做，认的是转义后的实体
    （``&gt;`` ``&quot;`` …）。生成区的标记行在这里已经由 `split_by_markers`
    摘掉了，所以不用再操心注释会被转义成 ``&lt;!--``。
    """
    h = _html.escape(content.replace("\r\n", "\n").replace("\r", "\n"))

    # 代码块（```lang\ncode\n```），必须先于行内代码处理
    h = re.sub(
        r"```(\w*)\n(.*?)```",
        lambda m: f'<pre><code class="lang-{m.group(1)}">'
                  f'{_html.escape(m.group(2))}</code></pre>',
        h, flags=re.DOTALL
    )
    # 行内代码
    h = re.sub(r"`([^`]+)`", r"<code>\1</code>", h)
    # 标题（H6 → H1 逆序，防止 # 一级被 ###### 六级错误匹配）
    for lvl in range(6, 0, -1):
        h = re.sub(
            r"^" + r"#" * lvl + r"\s+(.+)$",
            lambda m, _l=lvl: f"<h{_l}>{m.group(1)}</h{_l}>",
            h, flags=re.MULTILINE
        )
    # 引用块（连续 > 行合成一个 blockquote）
    def quote_sub(m):
        body = "<br>".join(x.strip() for x in m.group(0).strip().split("\n"))
        return f"<blockquote><p>{body}</p></blockquote>"

    h = re.sub(r"(?:^&gt;\s?.*$\n?)+", quote_sub, h, flags=re.MULTILINE)
    # ★ 分隔线必须在段落包装之前替换：段落替换会把 `---` 包进 <p> 里，之后就
    #   再也匹配不到行首行尾了（这里踩过一次，<hr> 静默消失）。
    h = re.sub(r"^(?:-{3,}|\*{3,}|_{3,})\s*$", "<hr>", h, flags=re.MULTILINE)

    h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
    h = re.sub(r"\*(.+?)\*", r"<em>\1</em>", h)
    h = re.sub(r"~~(.+?)~~", r"<del>\1</del>", h)

    def img_sub(m):
        src = m.group(1)
        if not (src.startswith("http://") or src.startswith("https://")):
            if base_dir:
                img_path = Path(base_dir) / src
                if img_path.exists():
                    src = str(img_path).replace("\\", "/")
        return f'<img src="{src}" alt="{m.group(2)}">'

    h = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", img_sub, h)
    h = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', h)

    # 段落（两个换行之间视为段落边界）
    h = h.replace("\n\n", "</p><p>")
    h = f"<p>{h}</p>"
    h = re.sub(r"<p>\s*</p>", "", h)

    return h


# Typora 默认主题的排版比例：正文 16px / 行高 1.6 / h1 2.25em 带下边框 /
# 代码块 #f8f8f8 圆角 3px / 引用 4px 左侧竖线。链接色换成本项目的 palette.link。
_HTML_SHELL = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  body {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    max-width: 820px;
    margin: 44px auto;
    padding: 0 28px;
    background: #ffffff;
    color: #1c1c1c;
    line-height: 1.6;
    font-size: 16px;
    word-wrap: break-word;
  }}
  h1, h2, h3, h4, h5, h6 {{
    font-weight: 600; color: #1c1c1c;
    margin: 1.4em 0 .7em; line-height: 1.3;
  }}
  h1 {{ font-size: 2.1em; padding-bottom: .3em; border-bottom: 1px solid #ececec }}
  h2 {{ font-size: 1.65em; padding-bottom: .3em; border-bottom: 1px solid #ececec }}
  h3 {{ font-size: 1.35em }}
  h4 {{ font-size: 1.15em }}
  h5 {{ font-size: 1em }}
  h6 {{ font-size: 1em; color: #9a9a9a }}
  p, ul, ol, blockquote, pre {{ margin: .85em 0 }}
  ul, ol {{ padding-left: 1.6em }}
  li {{ margin: .25em 0 }}
  a {{ color: #4f6b85 }}
  hr {{ border: none; border-top: 2px solid #e7e7e7; margin: 26px 0 }}
  blockquote {{
    border-left: 4px solid #e2e2e2;
    padding: .1em 16px;
    color: #6b6b6b;
    background: #fafafa;
  }}
  blockquote p {{ margin: .5em 0 }}
  code {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 85%;
    background: #f4f4f4;
    padding: .2em .4em;
    border-radius: 3px;
  }}
  pre {{
    background: #f8f8f8;
    border-radius: 4px;
    padding: 14px 16px;
    overflow-x: auto;
  }}
  pre code {{ background: none; padding: 0; font-size: 92% }}
  img {{ max-width: 100%; border-radius: 6px }}
  del {{ color: #9a9a9a }}
  table {{ border-collapse: collapse; margin: 1em 0 }}
  th, td {{ border: 1px solid #e6e6e6; padding: 6px 13px }}
  th {{ background: #f8f8f8; font-weight: 600 }}
  /* 生成区：冷底 + 左侧色条 + 宋体 + 小一号。三个维度都跟正文拉开，
     一眼就能看出「这段不是我写的」（与 tk.Text 那边同一套取舍）。 */
  .genzone {{
    background: {gen_bg};
    border-left: 3px solid {gen_bar};
    border-radius: 3px;
    padding: 2px 18px;
    margin: 1.2em 0;
    font-family: "SimSun", "宋体", "新宋体", "Microsoft YaHei UI", serif;
    font-size: 15px;
    color: {gen_fg};
  }}
  .genzone > p:first-child {{ margin-top: .7em }}
  .genzone > p:last-child {{ margin-bottom: .7em }}
  .genzone h1, .genzone h2, .genzone h3, .genzone h4 {{
    color: {gen_fg}; border-bottom-color: {gen_bar};
  }}
  .genzone h5, .genzone h6 {{ color: {gen_accent} }}
  .genzone a {{ color: {gen_accent} }}
  .genzone blockquote {{
    border-left-color: {gen_bar};
    background: rgba(255, 255, 255, .55);
    color: {gen_accent};
  }}
  .genzone code {{ background: {gen_code_bg}; color: {gen_fg} }}
  .genzone pre {{ background: {gen_code_bg} }}
  .genzone hr {{ border-top-color: {gen_bar} }}
  .genzone del {{ color: {gen_accent} }}
</style>
</head>
<body>
{body}
</body>
</html>"""
