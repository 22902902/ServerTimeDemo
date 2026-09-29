"""把 Markdown 变成**能打印**的东西 —— 不认识 Tk，也不引第三方库。

为什么单独成篇
------------------------------------------------------------------------------
导出的 Markdown 是给人贴笔记、给人看的；要**打印**就得有排版（分页、字号、
代码块不跨页断开），而 Markdown 本身不带这些。真正去打印走的是 Windows 的
Shell 动词（``os.startfile(path, "print")``），交给系统里关联 HTML 的那个程序
（浏览器）去做 —— 自己实现打印对话框要引 win32print，为一个「顺手打印」的
动作不值当。

**打印失败必须静默**：关联程序没装、远程桌面没默认打印机都会抛异常，这时只要
让用户「自己打开那个文件」就够了，弹一串红字反而把导出成功的消息盖掉。
"""

from __future__ import annotations

import html
import os
import re

__all__ = ["markdown_to_html", "print_document", "PRINT_STYLE"]


# 打印样式：**分页时代码块不许被切成两半**（跨页断开的公式最难读）
PRINT_STYLE = """
  body { font-family: "Microsoft YaHei UI", sans-serif; font-size: 11pt;
         line-height: 1.6; color: #1c1c1c; margin: 18mm 16mm; }
  h1 { font-size: 20pt; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
  h2 { font-size: 15pt; margin-top: 18px; }
  h3 { font-size: 12.5pt; margin-top: 14px; margin-bottom: 2px; }
  code { font-family: Consolas, monospace; background: #f4f4f4;
         padding: 1px 4px; border-radius: 3px; }
  ul { margin: 4px 0 4px 18px; padding: 0; }
  li { margin: 2px 0; }
  table { border-collapse: collapse; margin: 8px 0; }
  th, td { border: 1px solid #ddd; padding: 3px 8px; text-align: left; }
  hr { border: none; border-top: 1px solid #eee; margin: 14px 0; }
  @media print {
    body { margin: 12mm; }
    h2, h3 { page-break-after: avoid; }
    ul, table { page-break-inside: avoid; }
  }
"""

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_TABLE_DIVIDER = re.compile(r"^\|?[\s:|-]+\|[\s:|-]*$")


def _inline(text: str) -> str:
    """行内：先转义再补标记（顺序反了会把 ``<code>`` 里的内容当成标签）。"""
    # `` 包起来的原样保留，不参与后续转义
    parts = re.split(r"(`[^`]+`)", str(text or ""))
    out = []
    for index, part in enumerate(parts):
        if index % 2:                       # 奇数位 = 反引号里的内容
            out.append("<code>" + html.escape(part.strip("`")) + "</code>")
            continue
        chunk = html.escape(part)
        chunk = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", chunk)
        out.append(chunk)
    return "".join(out)


def markdown_to_html(markdown_text: str, title: str = "文档") -> str:
    """把**本项目自己导出的**那份 Markdown 转成 HTML。

    只支持导出里会出现的那几种语法（标题 / 无序列表 / 表格 / 分隔线 / 段落 /
    行内代码 / 加粗）—— 这不是通用 Markdown 解析器，别拿别处的文档来喂它。
    """
    lines = str(markdown_text or "").splitlines()
    body: list[str] = []
    in_list = False
    in_table = False
    index = 0

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    def close_table() -> None:
        nonlocal in_table
        if in_table:
            body.append("</table>")
            in_table = False

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()

        if not stripped:
            close_list()
            close_table()
            index += 1
            continue

        heading = _HEADING.match(stripped)
        if heading:
            close_list()
            close_table()
            level = min(6, len(heading.group(1)))
            body.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            nxt = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if not in_table and nxt.startswith("|") and _TABLE_DIVIDER.match(nxt):
                close_list()
                body.append("<table><thead><tr>"
                            + "".join(f"<th>{_inline(c)}</th>" for c in cells)
                            + "</tr></thead><tbody>")
                in_table = True
                index += 2                  # 表头 + 分隔行一起吃掉
                continue
            if in_table:
                body.append("<tr>"
                            + "".join(f"<td>{_inline(c)}</td>" for c in cells)
                            + "</tr>")
                index += 1
                continue

        if stripped in ("---", "***", "___"):
            close_list()
            close_table()
            body.append("<hr>")
            index += 1
            continue

        bullet = _BULLET.match(stripped)
        if bullet:
            close_table()
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline(bullet.group(1))}</li>")
            index += 1
            continue

        close_list()
        close_table()
        body.append(f"<p>{_inline(stripped)}</p>")
        index += 1

    close_list()
    close_table()
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(str(title))}</title>\n"
        f"<style>{PRINT_STYLE}</style>\n"
        "</head>\n<body>\n" + "\n".join(body) + "\n</body>\n</html>\n"
    )


def print_document(path) -> bool:
    """用系统里关联的程序打印这个文件。**失败一律返回 False，不抛异常。**

    没装浏览器、远程桌面没有默认打印机都会抛 —— 这时候只要让用户自己打开
    那个文件就够了，不该因为「打不了」把「导出成功了」这件事也一起否掉。
    """
    try:
        os.startfile(str(path), "print")
        return True
    except Exception:
        return False
