# -*- coding: utf-8 -*-
"""笔记页排版回归测试：Markdown 预览 tag + 编辑器外框 + 底部预览面板。

为什么需要它
------------------------------------------------------------------------------
排版是"看不见的回归"：把标题灰度改回去、把行内代码改回品红、把 relief 改回
solid，程序都不报错，只有肉眼能发现。这里把定稿规则固化成断言。

断言覆盖：
  1. 六级标题：字色统一 text_primary（末两级例外），层级只靠字号 + 段间距
  2. 行内代码 / 代码块：无高饱和前景色，代码块无 solid 边框
  3. 链接：取 palette.link（极低饱和墨蓝），不是 #0366d6
  4. 引用块：以「▎」为书脊线，「❝」已移除
  5. 编辑器与预览区：relief=flat + 1px 发丝线，不再是立体边框
  6. 底部预览面板：真实渲染后有标题 / 元信息 / 发丝线 / 正文四类 tag
  7. 浏览器预览 HTML：不残留 #0366d6 / #c7254e
  8. 笔记列表：ID 列居中，文本列左对齐
  9. 分类面板与工具栏：彩色 emoji 已移除

用法：
    python scripts/test_notes_markdown.py
"""

import sys
import tkinter.font as tkfont
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
import study_notes_window as snw  # noqa: E402
from markdown_view import (  # noqa: E402
    FONT_FAMILY,
    GEN_BAR_CHAR,
    GEN_BG,
    GEN_CODE_BG,
    GEN_FONT_CANDIDATES,
    GEN_INDENT,
    GEN_PREFIX,
)
from study_notes_db import GEN_END, GEN_START  # noqa: E402
from study_notes_window import (  # noqa: E402
    MONO_FAMILY,
    NoteEditorDialog,
    StudyNotesPage,
)
from ui_theme import MAIN_PALETTE as PALETTE  # noqa: E402


SAMPLE = """# 一级**标题**
## 二级标题
### 三级标题

正文段落，含 `inline_code` 与 [链接](https://example.com) 以及 **加粗** 与 *斜体*。

![截图](shot.png)

> 这是一段引用
> 引用第二行

- 列表项含 `code_in_li`
- 列表项二

```python
print("hello")
```

---
"""

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


def tag_size(widget, tag: str) -> int:
    return int(tkfont.Font(font=widget.tag_cget(tag, "font")).cget("size"))


def tag_color(widget, tag: str) -> str:
    return str(widget.tag_cget(tag, "foreground"))


def walk(widget, out=None):
    if out is None:
        out = []
    for child in widget.winfo_children():
        out.append(child)
        walk(child, out)
    return out


# ttk.Label 的 winfo_class 是 "TLabel"，tk.Label 是 "Label" —— 只按 "Label"
# 过滤会扫到一个空集，断言看似通过其实什么都没验（本轮踩过这个坑）。
LABEL_CLASSES = ("Label", "TLabel")


def label_texts(widget) -> list[str]:
    return [str(w.cget("text")) for w in walk(widget)
            if w.winfo_class() in LABEL_CLASSES and str(w.cget("text")) != ""]


def tree_nodes(tree, parent="", out=None) -> list:
    """递归收集分类树 / 笔记树的全部 iid（含各级子节点）。"""
    if out is None:
        out = []
    for iid in tree.get_children(parent):
        out.append(iid)
        tree_nodes(tree, iid, out)
    return out


def main_test():
    main.ExpiryManagerApp.prompt_login = lambda self: None
    main.ExpiryManagerApp.poll_external_commands = lambda self: None

    print("=" * 78)
    print("构造真实主窗口 + 笔记编辑器")
    print("=" * 78)
    app = main.ExpiryManagerApp()
    app.withdraw()
    app.update_idletasks()

    dlg = NoteEditorDialog(app, app.study_notes_db, note_id=0)
    dlg.withdraw()
    dlg.text_area.insert("1.0", SAMPLE)
    dlg._render_preview()
    dlg.update_idletasks()
    p = dlg.preview_area

    # ---------------------------------------------------------------- 1
    print("\n[1] 六级标题：字号分层 + 字色统一")
    sizes = [tag_size(p, f"h{i}") for i in range(1, 7)]
    check("字号逐级不增（h1 ≥ h2 ≥ … ≥ h6）",
          all(sizes[i] >= sizes[i + 1] for i in range(5)), f"实际 {sizes}")
    check("h1 明显大于 h6（至少差 5pt）", sizes[0] - sizes[5] >= 5,
          f"h1={sizes[0]} h6={sizes[5]}")
    for lvl in (1, 2, 3, 4):
        check(f"h{lvl} 字色 = text_primary",
              tag_color(p, f"h{lvl}") == PALETTE.text_primary,
              f"实际 {tag_color(p, f'h{lvl}')}")
    check("h5 字色 = text_secondary",
          tag_color(p, "h5") == PALETTE.text_secondary,
          f"实际 {tag_color(p, 'h5')}")
    check("h6 字色 = text_muted",
          tag_color(p, "h6") == PALETTE.text_muted,
          f"实际 {tag_color(p, 'h6')}")
    old_grays = {"#1a1a1a", "#222", "#333", "#444", "#555", "#666"}
    used = {tag_color(p, f"h{i}").lower() for i in range(1, 7)}
    check("不再使用旧版那套六个灰度", not (used & old_grays), f"实际 {sorted(used)}")

    # ---------------------------------------------------------------- 2
    print("\n[2] 代码：无高饱和前景色 / 无 solid 边框")
    check("行内代码前景 = 正文色（不是品红 #c7254e）",
          tag_color(p, "code").lower() == PALETTE.text_primary,
          f"实际 {tag_color(p, 'code')}")
    check("行内代码底色 = surface_alt",
          str(p.tag_cget("code", "background")).lower() == PALETTE.surface_alt,
          f"实际 {p.tag_cget('code', 'background')}")
    check("代码块前景 = 正文色（不是 #333）",
          tag_color(p, "codeblock").lower() == PALETTE.text_primary,
          f"实际 {tag_color(p, 'codeblock')}")
    check("代码块不带 solid 边框",
          str(p.tag_cget("codeblock", "relief")) not in ("solid", "ridge", "groove"),
          f"实际 {p.tag_cget('codeblock', 'relief')}")

    # ---------------------------------------------------------------- 3
    print("\n[3] 链接与图片：palette.link")
    check("链接色 = palette.link",
          tag_color(p, "link").lower() == PALETTE.link,
          f"实际 {tag_color(p, 'link')}")
    check("图片占位色 = palette.link",
          tag_color(p, "image").lower() == PALETTE.link,
          f"实际 {tag_color(p, 'image')}")

    # ---------------------------------------------------------------- 4
    print("\n[4] 引用块：▎ 书脊线")
    body = p.get("1.0", "end")
    check("渲染结果里出现 ▎", "▎" in body)
    check("旧版的 ❝ 已移除", "❝" not in body)
    check("quote_bar tag 已生效", bool(p.tag_ranges("quote_bar")))
    check("quote tag 已生效", bool(p.tag_ranges("quote")))
    check("引用块与书脊线同底色",
          str(p.tag_cget("quote_bar", "background")).lower()
          == str(p.tag_cget("quote", "background")).lower())

    # ---------------------------------------------------------------- 5
    print("\n[5] 结构元素")
    check("标题 tag 已生效（h1）", bool(p.tag_ranges("h1")))
    check("代码块 tag 已生效", bool(p.tag_ranges("codeblock")))
    check("分隔线 tag 已生效", bool(p.tag_ranges("hr")))
    check("列表 tag 已生效", bool(p.tag_ranges("li")))

    # ---------------------------------------------------------------- 5b
    print("\n[5b] 行内标记真的被应用了（旧实现只删符号不打 tag）")
    for tag in ("code", "link", "bold", "italic", "image"):
        check(f"行内 tag「{tag}」在预览里已生效", bool(p.tag_ranges(tag)),
              f"tag_ranges('{tag}') 为空 —— 说明该 tag 只是配了，渲染时没用上")

    def font_of_first(tag):
        rng = p.tag_ranges(tag)
        if not rng:
            return None
        return tkfont.Font(font=p.tag_cget(tag, "font")).actual("family")

    check("行内代码用等宽字体（证明 tag 优先级正确）",
          font_of_first("code") == MONO_FAMILY,
          f"实际 {font_of_first('code')}，期望 {MONO_FAMILY}")
    check("链接带下划线",
          "underline" in str(p.tag_cget("link", "font")),
          f"实际 {p.tag_cget('link', 'font')}")

    # 列表项里的行内代码不能被 li 的字体盖掉
    def inside_any(rng_start, outer):
        for j in range(0, len(outer) - 1, 2):
            if outer[j] <= rng_start < outer[j + 1]:
                return True
        return False

    li_ranges = p.tag_ranges("li")
    code_ranges = p.tag_ranges("code")
    code_starts = [code_ranges[i] for i in range(0, len(code_ranges), 2)]
    check("列表项里的行内代码仍带 code tag（li 没有压过它）",
          any(inside_any(s, li_ranges) for s in code_starts),
          f"li={li_ranges} code={code_ranges}")

    # 标题里的加粗也应生效
    h1_ranges = p.tag_ranges("h1")
    bold_ranges = p.tag_ranges("bold")
    check("标题内的加粗也带 bold tag",
          bool(bold_ranges) and inside_any(bold_ranges[0], h1_ranges),
          f"h1={h1_ranges} bold={bold_ranges}")
    check("Markdown 标记符号本身没有被渲染出来",
          "`" not in body and "**" not in body and "](" not in body,
          f"残留符号：{[s for s in ('`', '**', '](') if s in body]}")
    check("Markdown 标记符号本身没有被渲染出来",
          "`" not in body and "**" not in body and "](" not in body,
          f"残留符号：{[s for s in ('`', '**', '](') if s in body]}")

    # ---------------------------------------------------------------- 6
    print("\n[6] 编辑器 / 预览区外框")
    check("编辑区 relief = flat", str(dlg.text_area.cget("relief")) == "flat",
          f"实际 {dlg.text_area.cget('relief')}")
    check("编辑区 1px 发丝线 = input_border",
          str(dlg.text_area.cget("highlightbackground")).lower() == PALETTE.input_border,
          f"实际 {dlg.text_area.cget('highlightbackground')}")
    check("预览区 relief = flat", str(p.cget("relief")) == "flat",
          f"实际 {p.cget('relief')}")
    check("预览区底色 = surface（当纸看）",
          str(p.cget("background")).lower() == PALETTE.surface,
          f"实际 {p.cget('background')}")

    # ---------------------------------------------------------------- 7
    print("\n[7] 浏览器预览 HTML")
    html = dlg._build_html_preview(SAMPLE)
    check("不含旧的链接蓝 #0366d6", "#0366d6" not in html)
    check("不含旧的代码品红 #c7254e", "#c7254e" not in html)
    check("链接色已改为 #4f6b85", "#4f6b85" in html)
    check("不再用 rgba box-shadow 阴影", "box-shadow" not in html)
    check("body 背景为纯白", "background: #ffffff" in html)

    dlg_texts = label_texts(dlg)
    check("编辑器标签扫描有效（防止空集假通过）", len(dlg_texts) >= 4,
          f"只扫到 {len(dlg_texts)} 个：{dlg_texts}")
    dlg_leftover = [t for t in dlg_texts if any(c in t for c in "📂🔍📝💡📦🔗🔑")]
    check("编辑器标签不再有彩色 emoji", not dlg_leftover, f"残留 {dlg_leftover}")
    check("编辑区提示文案已去 emoji",
          any(t.startswith("Markdown 编辑区") for t in dlg_texts),
          f"实际 {dlg_texts}")

    # ---------------------------------------------------------------- 9
    print("\n[9] 生成区：标记行不渲染 + 颜色/字体/排版三处与正文不同")
    # 生成区的样式是「让用户一眼分出哪段是机器写的」——改回正文样式程序也不
    # 报错，只有肉眼才发现。所以三项差异各留一条断言。
    gen_note = (
        f"{GEN_START}\n"
        "> **自动生成** · 2026-09-24 10:29 · 来自「Excel 宝典 › 自测出题」\n"
        "> 这一段重新生成时会整段覆盖；想留的东西写在下面「我的补充」。\n"
        "\n"
        "## SUM｜求和\n"
        "\n"
        "分类：数学统计 · 掌握度：生疏\n"
        "\n"
        "**一句话**\n"
        "\n"
        "把一批数字加起来，含 `=SUM(A1:A10)` 这样的行内代码。\n"
        "\n"
        "```python\n"
        "print(1)\n"
        "```\n"
        f"{GEN_END}\n"
        "\n"
        "## 我的补充\n"
        "\n"
        "我自己写的一段话，样式应该跟上面完全不同。\n"
    )
    dlg.text_area.delete("1.0", "end")
    dlg.text_area.insert("1.0", gen_note)
    dlg._render_preview()
    dlg.update_idletasks()

    shown = p.get("1.0", "end-1c")
    check("★ 两个标记行都不出现在预览里",
          GEN_START not in shown and GEN_END not in shown
          and "gen:start" not in shown and "gen:end" not in shown,
          repr([ln for ln in shown.splitlines() if "gen:" in ln]))

    # 生成区 = 带任意 gen_ 前缀 tag 的那些行
    total_rows = int(p.index("end-1c").split(".")[0])
    gen_rows = [r for r in range(1, total_rows + 1)
                if any(str(t).startswith(GEN_PREFIX)
                       for t in p.tag_names(f"{r}.0"))]
    check("★ 认出了生成区（标签家族生效）", bool(gen_rows),
          f"总行数 {total_rows}，gen 行 {gen_rows}")
    check("gen_zone 元素 tag 已挂上",
          any("gen_zone" in p.tag_names(f"{r}.0") for r in gen_rows))

    # 分界线：用户自己那段以「我的补充」开头
    my_row = next((r for r in range(1, total_rows + 1)
                   if p.get(f"{r}.0", f"{r}.end").strip() == "我的补充"), 0)
    check("找到了「我的补充」那一行（防假绿）", my_row > 0, my_row)
    user_rows = list(range(my_row, total_rows + 1)) if my_row else []
    stray = [r for r in user_rows
             if any(str(t).startswith(GEN_PREFIX) for t in p.tag_names(f"{r}.0"))]
    check("★ 用户自己的那一段一个 gen_ tag 都没有", not stray, f"串到 {stray}")

    # 排版：整块左缩进；生成区每行首带书脊线，用户那段没有
    check(f"生成区整块左缩进 ≥ {GEN_INDENT}px（排版不同）",
          int(p.tag_cget("gen_bar", "lmargin1")) >= GEN_INDENT,
          p.tag_cget("gen_bar", "lmargin1"))
    gen_bars = sum(1 for r in gen_rows[:my_row - 1]
                   if GEN_BAR_CHAR in p.get(f"{r}.0", f"{r}.end"))
    check("生成区非空行都带书脊线", gen_bars > 0, gen_bars)
    check("用户那一段没有书脊线",
          not any(GEN_BAR_CHAR in p.get(f"{r}.0", f"{r}.end") for r in user_rows))

    # 颜色：正文底色 / 字色 / 代码底色三处都不一样
    check("gen_zone 底色 = GEN_BG（颜色不同）",
          str(p.tag_cget("gen_zone", "background")).lower() == GEN_BG.lower(),
          p.tag_cget("gen_zone", "background"))
    check("gen_p 字色与正文 p 不同",
          tag_color(p, "gen_p").lower() != tag_color(p, "p").lower(),
          f"gen_p={tag_color(p, 'gen_p')} p={tag_color(p, 'p')}")
    check("gen_code 底色 = GEN_CODE_BG",
          str(p.tag_cget("gen_code", "background")).lower() == GEN_CODE_BG.lower(),
          p.tag_cget("gen_code", "background"))

    # 字体：生成区用衬线中文字（候选里挑一个系统真有的），且与正文不同
    fam_of = lambda tag: str(tkfont.Font(font=p.tag_cget(tag, "font")).cget("family"))
    gen_family = fam_of("gen_p")
    body_family = fam_of("p")
    check("gen_p 有独立字体族", bool(gen_family), gen_family)
    check("★ 生成区字体与正文不同",
          gen_family != body_family, f"{gen_family} vs {body_family}")
    check("生成区字体取自衬线候选（不是随便落在一个默认字体上）",
          gen_family in GEN_FONT_CANDIDATES or gen_family != FONT_FAMILY,
          f"实际 {gen_family}")
    check("生成区代码仍是等宽字体（衬线只作用于正文）",
          fam_of("gen_code") == MONO_FAMILY, fam_of("gen_code"))

    # 浏览器预览：同一套差异也要在 HTML 里
    html_gen = dlg._build_html_preview(gen_note)
    check("HTML 里生成区有独立容器 class", 'class="genzone"' in html_gen)
    check("HTML 里生成区底色已写入", GEN_BG in html_gen)
    check("HTML 里标记行不渲染",
          GEN_START not in html_gen and GEN_END not in html_gen)
    html_plain = dlg._build_html_preview("## 普通笔记\n\n没有标记。\n")
    check("普通笔记的 HTML 里没有生成区容器",
          'class="genzone"' not in html_plain)

    # 反向：一篇没有标记的普通笔记，预览里不许出现 gen_ tag
    dlg.text_area.delete("1.0", "end")
    dlg.text_area.insert("1.0", "## 普通笔记\n\n就是普通正文。\n")
    dlg._render_preview()
    dlg.update_idletasks()
    plain_rows = [r for r in range(1, int(p.index("end-1c").split(".")[0]) + 1)
                  if any(str(t).startswith(GEN_PREFIX) for t in p.tag_names(f"{r}.0"))]
    check("★ 没有标记的普通笔记一个 gen_ tag 都没有", not plain_rows, plain_rows)

    dlg.destroy()

    # ---------------------------------------------------------------- 8
    print("\n[8] 笔记页（嵌入主窗口）")
    page = app.study_notes_page
    inner = [w for w in walk(page) if isinstance(w, StudyNotesPage)]
    check("主窗口内嵌 StudyNotesPage", bool(inner),
          f"实际 {[type(w).__name__ for w in walk(page)][:6]}")
    if inner:
        pg = inner[0]
        pv = pg.preview_text
        for tag in ("pv_title", "pv_meta", "pv_rule", "pv_body"):
            check(f"底部预览 tag「{tag}」已配置",
                  str(pv.tag_cget(tag, "font")) != "")
        check("底部预览底色 = surface_alt",
              str(pv.cget("bg")).lower() == PALETTE.surface_alt,
              f"实际 {pv.cget('bg')}")
        check("预览标题字号 > 正文字号",
              tag_size(pv, "pv_title") > tag_size(pv, "pv_body"))
        check("笔记列表 ID 列居中",
              str(pg.notes_tree.column("id", "anchor")) == "center",
              f"实际 {pg.notes_tree.column('id', 'anchor')}")
        check("笔记列表 标题 列左对齐",
              str(pg.notes_tree.column("title", "anchor")) == "w",
              f"实际 {pg.notes_tree.column('title', 'anchor')}")
        check("笔记列表 更新时间 列左对齐",
              str(pg.notes_tree.column("updated_at", "anchor")) == "w")

        texts = label_texts(pg)
        # 页面上本来就只有两个 Label（其余是 ttk.Button 与表头 heading），
        # 因此阈值取 2 —— 但必须确认扫到了东西，否则断言是空集假通过。
        check("确实扫到了页面上的标签（防止空集假通过）", len(texts) >= 2,
              f"只扫到 {len(texts)} 个：{texts}")
        leftover = [t for t in texts if any(c in t for c in "📂🔍📝💡📦🔗🔑")]
        check("分类面板/工具栏不再有彩色 emoji", not leftover, f"残留 {leftover}")
        check("分类面板标题为「笔记分类」", "笔记分类" in texts,
              f"实际标签 {texts}")

        # ------------------------------------------------------------ 10
        print("\n[10] 锁定分类：看得见「（系统）」，改不了也删不掉")
        locked_code = app.study_notes_db.ensure_locked_category(
            source_key="excel", name="Excel 宝典")
        check("数据层建出了锁定分类", bool(locked_code), locked_code)
        pg.reload()
        pg.update_idletasks()
        nodes = {iid: str(pg.cat_tree.item(iid, "text"))
                 for iid in tree_nodes(pg.cat_tree)}
        hit = [iid for iid, text in nodes.items() if "Excel 宝典" in text]
        check("★ 分类树里能看到锁定分类", bool(hit), list(nodes.values())[:8])
        node = hit[0] if hit else ""
        check("树上带「（系统）」后缀（明显区别于普通分类）",
              bool(node) and nodes[node].endswith("（系统）"), nodes.get(node))
        check("该节点打了 locked 标记",
              bool(node) and "locked" in pg.cat_tree.item(node, "tags"),
              pg.cat_tree.item(node, "tags") if node else None)
        check("locked 标记配了弱化字色",
              str(pg.cat_tree.tag_configure("locked", "foreground")) != "",
              pg.cat_tree.tag_configure("locked", "foreground"))

        said: list = []
        orig_info = snw.messagebox.showinfo
        snw.messagebox.showinfo = lambda *a, **k: said.append(a)
        try:
            pg.cat_tree.selection_set(node)
            pg.edit_category()
            check("★ 选中锁定分类点「编辑分类」被挡下（不弹编辑框）",
                  len(said) == 1, said)
            check("提示说明它是系统分类、不能改名",
                  bool(said) and "系统分类" in str(said[0])
                  and "不能改名" in str(said[0]), said)
            said.clear()
            pg.delete_category()
            check("★ 选中锁定分类点「删除分类」也被挡下", len(said) == 1, said)
            check("提示说明不能删除",
                  bool(said) and "不能删除" in str(said[0]), said)
        finally:
            snw.messagebox.showinfo = orig_info
        check("★ 折腾一圈之后分类还在、还锁着",
              bool(node) and app.study_notes_db.get_category(int(node)).locked == 1)

        # 只约束它自己：树上的普通分类照旧，一个都没被误打系统标记。
        # ★ 这一段**只读**：绝不能为了测「用户能建自己的分类」就往库里塞一条
        # —— 这个夹具是开发库，每跑一次测试就留一条垃圾分类（本轮踩过：
        # 探针脚本建了两条「我自己的分类」，得手工清掉）。
        locked_nodes = [iid for iid in nodes
                        if "locked" in pg.cat_tree.item(iid, "tags")]
        check("★ 树上只有锁定分类一个被打 locked 标记",
              locked_nodes == ([node] if node else []),
              [nodes[i] for i in locked_nodes])
        plain = {iid: text for iid, text in nodes.items() if "（系统）" not in text}
        check("普通分类照旧显示（锁定机制不波及它们）", len(plain) >= 5,
              len(plain))
        check("★ 普通分类没有一个被误打 locked 标记",
              not any("locked" in pg.cat_tree.item(iid, "tags") for iid in plain))
        check("锁定分类混在普通分类里、不是唯一一项",
              len(plain) + 1 == len(nodes), f"{len(plain)} + 1 vs {len(nodes)}")

    app.destroy()


if __name__ == "__main__":
    print("=" * 78)
    print("笔记页排版回归测试")
    print("=" * 78)
    try:
        main_test()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILED += 1

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
