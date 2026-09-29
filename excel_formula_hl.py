"""Excel 公式分词器 —— **只认识字符串，不认识 Tk**。

为什么单独成篇
------------------------------------------------------------------------------
公式在界面上是等宽纯文本，一行 ``=IFERROR(VLOOKUP(A2, 表1!A:B, 2, 0), "无")``
看下来眼睛没有落点：哪个是函数、哪个是引用、哪段是写死的字面量，全靠自己扫。
着色能帮上忙，但**着色器绝不能吞字符** —— 一旦 token 拼回去不等于原文，
「复制」按钮拷出来的公式就是坏的，用户照着敲会直接报错。所以这里的硬约束是：

    ``''.join(t.text for t in tokenize(s)) == s``   对**任意**输入都成立

（包括空串、只有引号、引号没闭合、以及中英混排的表名。）

分词只做「这件事是什么」，颜色由界面决定（不同底色要配不同的色）。
"""

from __future__ import annotations

import re
from typing import NamedTuple

__all__ = ["Token", "KINDS", "tokenize"]


class Token(NamedTuple):
    """一段公式文本。``kind`` 决定它该是什么颜色。"""

    kind: str
    text: str


# 六种：函数 / 字符串 / 引用 / 数字 / 运算符 / 括号；认不出来的统称 text
KINDS = ("func", "string", "ref", "number", "operator", "paren", "text")

# --------------------------------------------------------------------------
# 模式表（**顺序即优先级**：谁先匹配上算谁）
# --------------------------------------------------------------------------

# 字符串：Excel 里写双引号本身要写两遍（""），所以引号只有紧跟另一个引号时才不算结束
_STRING = r'"(?:[^"]|"")*"'

# 单元格 / 区域引用，四种形态：
#   1) 带表名：  表1!A1:A9         '我的 表'!A1
#   2) 普通：    A1   $A$1   A1:B2
#   3) 整列整行：A:A   3:3
#   4) 结构化：  表1[单价]
_CELL = r"\$?[A-Za-z]{1,3}\$?\d+"
_COL = r"\$?[A-Za-z]{1,3}:\$?[A-Za-z]{1,3}"
_ROW = r"\$?\d+:\$?\d+"
_RANGE = rf"(?:{_CELL}(?::{_CELL})?|{_COL}|{_ROW})"
_SHEET = r"(?:'[^']*'|[\w\u4e00-\u9fff]+)!"
_STRUCT = r"[\w\u4e00-\u9fff]+\[[^\]]*\]"

_REF = rf"(?:{_SHEET}{_RANGE}|{_STRUCT}|{_RANGE})"

# 函数名：**后面必须紧跟左括号**才是函数（否则它更可能是定义名称）
_FUNC = r"[A-Za-z_][\w.]*(?=\s*\()"

# 数字：整数 / 小数 / 百分号
_NUMBER = r"\d+(?:\.\d+)?%?|\.\d+%?"

_OPERATOR = r"[+\-*/^&=<>]|[,;@]"

_PATTERNS = (
    ("string", re.compile(_STRING)),
    ("ref", re.compile(_REF)),
    ("func", re.compile(_FUNC)),
    ("number", re.compile(_NUMBER)),
    ("operator", re.compile(_OPERATOR)),
    ("paren", re.compile(r"[(){}\[\]]")),
)


def tokenize(text: str) -> list[Token]:
    """把一条公式切成带类别的片段。**拼接后必然等于原文。**

    >>> "".join(t.text for t in tokenize('=SUM(A1:A9, "合计")')) == '=SUM(A1:A9, "合计")'
    True
    """
    src = str(text or "")
    if not src:
        return []

    tokens: list[Token] = []
    pos = 0
    while pos < len(src):
        for kind, pattern in _PATTERNS:
            match = pattern.match(src, pos)
            if match and match.end() > match.start():
                tokens.append(Token(kind, match.group()))
                pos = match.end()
                break
        else:
            # 一个都没匹配上：吃掉一个字符当普通文本（绝不丢字符）
            tokens.append(Token("text", src[pos]))
            pos += 1
    return _merge(tokens)


def _merge(tokens: list[Token]) -> list[Token]:
    """把相邻同类的片段并起来 —— 否则 ``A1`` 会被切成 ``A`` + ``1``。

    注意：**只并同类**，``ref`` 后面跟 ``text`` 不许并（那会糊掉边界）。
    """
    merged: list[Token] = []
    for token in tokens:
        if merged and merged[-1].kind == token.kind:
            merged[-1] = Token(token.kind, merged[-1].text + token.text)
        else:
            merged.append(token)
    return merged
