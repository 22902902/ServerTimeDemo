# -*- coding: utf-8 -*-
"""笔记编辑器回归测试：格式工具栏动作 + 源码淡化 + 语法速查 + 两处预览渲染。

为什么需要它
------------------------------------------------------------------------------
这四块都是「点了没反应也不会报错」的功能：

  - 工具栏按钮作用错行（该改光标行却改了别处）
  - 源码淡化把正文文字也染浅了
  - 语法速查表少了几条，没人会注意到
  - 笔记页预览退回显示 Markdown 源码（这正是用户反馈过的问题）

所以这里逐条断言生成出来的文本，而不是只看「有没有崩」。

断言覆盖：
  1. 行内格式：无选中插标记对、有选中包裹、对已加粗的再点 = 取消
  2. 块元素：行首加前缀、再点取消、多行逐行加、保留原有缩进
  3. 标题：级别互斥（H1 切 H3 不叠成 ####）、可还原正文
  4. 链接：无选中给占位、光标停在网址处
  5. 源码淡化：只标标记符号、不动正文、行首锚定（句中的 - 不算）
  6. 编辑器预览：Typora tag 齐全、源码符号不进预览
  7. 语法速查：分组数、条目数、用的是两列数据列（不是 #0 树列）
  8. 笔记页预览：元信息在最前、正文被渲染成结构 tag、围栏不再露出

用法：
    python scripts/test_notes_editor.py
"""

import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
from study_notes_window import NoteEditorDialog, StudyNotesPage  # noqa: E402

PASSED = 0
FAILED = 0

NOTE_MD = """# 一级标题
## 二级标题

正文段落，含 `inline_code` 与 [链接](https://example.com)、**加粗**、*斜体*、~~删除~~。

- 列表项一
- 列表项二

1. 有序一
2. 有序二

> 引用一行

```python
print('Hello World!!!')
```

---
"""


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


def walk(widget, out=None):
    if out is None:
        out = []
    for child in widget.winfo_children():
        out.append(child)
        walk(child, out)
    return out


class FakeDB:
    """只覆盖 get_note，其余委托真库 —— 注入内容但不写用户数据。"""

    def __init__(self, real, note):
        self._real = real
        self._note = note

    def get_note(self, note_id):
        return self._note

    def __getattr__(self, key):
        return getattr(self._real, key)


def main_test():
    main.ExpiryManagerApp.prompt_login = lambda self: None
    main.ExpiryManagerApp.poll_external_commands = lambda self: None

    app = main.ExpiryManagerApp()
    app.geometry("1500x900+0+0")
    app.update()

    dlg = NoteEditorDialog(app, app.study_notes_db, note_id=0)
    dlg.geometry("1180x770+20+20")
    dlg.deiconify()
    dlg.update()
    ta = dlg.text_area

    def reset(text=""):
        ta.delete("1.0", "end")
        if text:
            ta.insert("1.0", text)
        ta.mark_set("insert", "1.0")
        ta.tag_remove("sel", "1.0", "end")
        dlg.update()

    def content():
        return ta.get("1.0", "end-1c")

    # ---------------------------------------------------------------- 1
    print("\n[1] 行内格式：无选中 / 有选中 / 再点取消")
    reset()
    dlg._wrap_inline("**", "**", "加粗文字")
    check("无选中时插入标记对", content() == "**加粗文字**", repr(content()))
    check("光标落在标记中间", ta.index("insert") == "1.2", ta.index("insert"))

    reset("要点")
    ta.tag_add("sel", "1.0", "1.2")
    dlg._wrap_inline("**", "**", "x")
    check("有选中时包裹选区", content() == "**要点**", repr(content()))

    reset("**要点**")
    ta.tag_add("sel", "1.0", "1.6")
    dlg._wrap_inline("**", "**", "x")
    check("对已加粗的选区再点 = 取消加粗", content() == "要点", repr(content()))

    # ---------------------------------------------------------------- 2
    print("\n[2] 块元素：加前缀 / 再点取消 / 多行 / 缩进")
    reset("第一项")
    dlg._apply_block("- ")
    check("行首加 - ", content() == "- 第一项", repr(content()))
    dlg._apply_block("- ")
    check("再点一次取消", content() == "第一项", repr(content()))

    reset("甲\n乙\n丙")
    ta.tag_add("sel", "1.0", "3.1")
    dlg._apply_block("- ")
    check("选中多行则每行都加", content() == "- 甲\n- 乙\n- 丙", repr(content()))

    reset("  缩进过的")
    dlg._apply_block("> ")
    check("标记插在缩进之后", content() == "  > 缩进过的", repr(content()))

    # ---------------------------------------------------------------- 3
    print("\n[3] 标题：级别互斥、可还原正文")
    reset("我的标题")
    dlg._apply_heading(1)
    check("H1", content() == "# 我的标题", repr(content()))
    ta.mark_set("insert", "1.0")
    dlg._apply_heading(3)
    check("H1 → H3 不叠成 ####", content() == "### 我的标题", repr(content()))
    ta.mark_set("insert", "1.0")
    dlg._apply_heading(0)
    check("切回正文", content() == "我的标题", repr(content()))

    # ---------------------------------------------------------------- 4
    print("\n[4] 链接插入")
    reset()
    dlg._insert_link()
    check("无选中时给占位", content() == "[链接文字](https://)", repr(content()))
    check("光标停在网址处", ta.index("insert") == "1.15", ta.index("insert"))

    # ---------------------------------------------------------------- 5
    print("\n[5] 源码淡化：只标标记、不动正文")
    reset("# 标题\n正文 **加粗** 和 `代码`\n- 列表项\n> 引用\n")
    dlg._dim_marks()
    rng = ta.tag_ranges("md_mark")
    check("md_mark tag 已生效", bool(rng))
    marked = "".join(ta.get(rng[i], rng[i + 1]) for i in range(0, len(rng), 2))
    for sym, name in (("#", "行首 #"), ("-", "行首 -"), (">", "行首 >"),
                      ("**", "行内 **"), ("`", "行内反引号")):
        check(f"{name} 被标记", sym in marked, repr(marked))
    check("正文文字没有被标记", "标题" not in marked and "加粗" not in marked, repr(marked))
    check("只改前景色、不动字号",
          str(ta.tag_cget("md_mark", "font")) in ("", "None"),
          repr(ta.tag_cget("md_mark", "font")))
    check("md_mark 颜色 = text_muted",
          str(ta.tag_cget("md_mark", "foreground")).lower() == "#9a9a9a",
          repr(ta.tag_cget("md_mark", "foreground")))

    reset("这是 a - b 的对比")
    dlg._dim_marks()
    check("句中的 - 不算列表标记（行首锚定）", not ta.tag_ranges("md_mark"),
          str(ta.tag_ranges("md_mark")))

    # ---------------------------------------------------------------- 6
    print("\n[6] 编辑器预览：Typora tag 齐全")
    reset("# 一\n## 二\n正文\n\n- 项\n\n> 引\n\n```\ncode\n```\n")
    dlg._toggle_preview()
    dlg.update()
    time.sleep(0.25)
    dlg.update()
    p = dlg.preview_area
    check("预览可见", dlg.preview_visible and p.winfo_ismapped() == 1)
    for tag in ("h1", "h2", "hrule", "p", "li", "quote", "codeblock"):
        check(f"标签「{tag}」生效", bool(p.tag_ranges(tag)))
    body = p.get("1.0", "end")
    check("源码标记没进预览", "#" not in body and "```" not in body, repr(body[:60]))
    check("预览区宽度正常（没被 PanedWindow 压成 0）", p.winfo_width() > 200,
          f"实际 {p.winfo_width()}")
    check("编辑区宽度正常", ta.winfo_width() > 200, f"实际 {ta.winfo_width()}")

    # ---------------------------------------------------------------- 7
    print("\n[7] 语法速查")
    dlg._open_syntax_help()
    dlg.update()
    wins = [w for w in dlg.winfo_children()
            if w.winfo_class() == "Toplevel" and w.title() == "Markdown 语法速查"]
    check("速查窗口已打开", bool(wins))
    if wins:
        win = wins[0]
        tv = [w for w in walk(win) if w.winfo_class() == "Treeview"]
        check("速查表用了 Treeview", bool(tv))
        if tv:
            cols = tv[0]["columns"]
            check("是两列数据列（不用 #0 树列）",
                  list(cols) == ["syntax", "effect"], str(cols))
            show = str(tv[0].cget("show"))
            check("show = headings（#0 树列会挤掉对齐）", "headings" in show, show)
            rows = [tv[0].item(i, "values") for i in tv[0].get_children("")]
            groups = [r[0] for r in rows if r[1] == ""]
            items = [r for r in rows if r[1] != ""]
            check(f"分组数 ≥ 3（实际 {len(groups)}）", len(groups) >= 3, str(groups))
            check(f"语法条目 ≥ 15（实际 {len(items)}）", len(items) >= 15)
            check("分组行带 group tag", bool(tv[0].tag_has("group")))
            # 注意：ttk.Treeview 没有 tag_cget（那是 tk.Text 的 API），
            # 只能 tag_configure(name) 取整份配置
            gfont = str((tv[0].tag_configure("group") or {}).get("font", ""))
            check("分组行加粗显示", "bold" in gfont, gfont)
        win.destroy()

    dlg.destroy()

    # ---------------------------------------------------------------- 8
    print("\n[8] 笔记页预览：正文真的被渲染")
    page = next(w for w in walk(app) if isinstance(w, StudyNotesPage))
    real_db = app.study_notes_db
    notes = real_db.fetch_notes()
    check("库里存在笔记", bool(notes), f"共 {len(notes)} 篇")
    if notes:
        note = real_db.get_note(notes[0].id)
        note.content = NOTE_MD
        note.tags = ["python", "入门"]
        page.db = FakeDB(real_db, note)

        page._show_preview(note.id)
        app.update()
        pv = page.preview_text
        body = pv.get("1.0", "end")

        check("元信息标题在最前（pv_title 起于 1.0）",
              bool(pv.tag_ranges("pv_title"))
              and str(pv.tag_ranges("pv_title")[0]) == "1.0",
              str(pv.tag_ranges("pv_title")))
        for tag in ("h1", "h2", "p", "li", "quote", "codeblock", "hr"):
            check(f"正文结构 tag「{tag}」生效", bool(pv.tag_ranges(tag)))
        check("行内 tag 生效（code / link / bold）",
              all(pv.tag_ranges(t) for t in ("code", "link", "bold")))
        check("围栏符号没有原样露出", "```" not in body,
              repr([ln for ln in body.split("\n") if "```" in ln][:3]))
        check("注释号没有原样露出", not any(
            ln.lstrip().startswith("# ") for ln in body.split("\n")),
            repr([ln for ln in body.split("\n") if ln.lstrip().startswith("# ")][:3]))
        # 正文区与元信息区分属两套 tag，别互相覆盖
        check("元信息与正文用不同 tag", bool(pv.tag_ranges("pv_meta")))

    app.destroy()


if __name__ == "__main__":
    print("=" * 78)
    print("笔记编辑器回归测试")
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
