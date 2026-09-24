# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 笔记联动桥（学完一轮 → 一套可二创的笔记模板）
================================================================================
把「刚做完的那轮自测」整理成学习笔记模块里的一篇篇笔记模板，省得从零写。

一篇笔记长成什么样
--------------------------------------------------------------------------------
    <!-- gen:start -->
    > **自动生成** · 2026-09-24 10:29 · 来自「Excel 宝典 › 自测出题」
    > 这一段重新生成时会整段覆盖；想留的东西写在下面「我的补充」。

    ## SUM｜求和

    分类：数学统计 · 掌握度：生疏 · 下次复习：2026-09-25

    **一句话**

    把一批数字加起来。

    **语法**

    `=SUM(number1, [number2], ...)`

    **本轮自测**

    答错了（你填的是「AVERAGE」，正确答案是「SUM」）
    <!-- gen:end -->

    ## 我的补充

    （这一段是你自己的地方 —— 写理解、写踩过的坑都行。重新生成只会覆盖
    上面那段，这里一个字都不会动。）

标记**里面**是「生成的」，标记**外面**是「你自己的」。渲染器给两段配不同
样式（见 ``markdown_view``：生成的用冷色底 + 宋体 + 缩进，自己的保持正文），
重新生成也只覆盖标记内 —— 于是「二创」永远不会被冲掉。

为什么单独一个模块，而不是塞进 ``excel_page``
--------------------------------------------------------------------------------
与 ``excel_todo_bridge`` 同一个分工：**页面只管画界面，写库留在数据层**。
页面拿到的是 ``main`` 注入的这个对象，所以 ``excel_page`` 既不认识
``study_notes_db`` 也不认识 ``main``，不会形成循环依赖。

三条约定（由 ``scripts/test_excel_note.py`` 守着）
--------------------------------------------------------------------------------
1. **只在用户点按钮时生成**，不做后台自动整理 —— 与待办联动同一个原则，
   学习工具不该变成催命符。
2. **一个函数一篇笔记**，函数码写进标签当身份。再次生成时按标签找回**同一篇
   更新**，不会越攒越多；用户改过的标题、追加的标签都留着。
3. **标记外面一个字都不动**：标记不成对（被手删了一个）时整篇按「用户自己
   写的」处理，只把生成区补在最前面。宁可少覆盖一次，也不冒把人写的东西
   冲掉的风险。
"""

from __future__ import annotations

import logging
import re

from excel_db import mastery_label
from study_notes_db import GEN_END, GEN_START

logger = logging.getLogger(__name__)

# ── 落点 ───────────────────────────────────────────────────────────────────
# 锁定分类的归属标识与显示名。编码是运行时分配的（见 study_notes_db 的
# ensure_locked_category），所以这里不能硬编码编码 —— 认得是 source_key。
NOTE_SOURCE_KEY = "excel"
LOCKED_CATEGORY_NAME = "Excel 宝典"
# 「落点」给人看的说法。状态栏、确认框、待办备注共用同一句，免得三处措辞对不上。
NOTE_AREA_LABEL = f"学习笔记 › {LOCKED_CATEGORY_NAME}"

# ── 生成区身体 ─────────────────────────────────────────────────────────────
SOURCE_LABEL = "Excel 宝典 › 自测出题"
USER_SECTION_TITLE = "我的补充"
USER_SECTION_HINT = (
    "（这一段是你自己的地方 —— 写理解、写踩过的坑、写你实际用过什么场景都行。"
    "重新生成只会覆盖上面那段，这里一个字都不会动。）"
)

# 笔记标签：第一个是所有生成笔记的公共标记，第二个是函数码（用来找回同一篇）
NOTE_TAG = "Excel"
WRONG_TAG = "错题"

# 场景串的分隔符（与 excel_db.SCENARIO_SPLIT_RE 同一套：中英文分号都要认）
_SCENARIO_RE = re.compile(r"[；;]")

# 元信息里「下次复习」只到天：ISO 串带时分秒，截断掉更好读
_DATE_LEN = 10


# =============================================================================
# 取值小工具
# =============================================================================

def _text(value) -> str:
    """任意值 → 去空白的字符串。None / 数字都不会炸。"""
    return str(value).strip() if value is not None else ""


def _pick(item: dict, *names, default: str = "") -> str:
    """按顺序挑第一个非空字段。

    ★ 为什么要有别名：同一个「示例公式」在两条数据来源里叫不同的名字 ——
    本轮自测的题目字典（``excel_db._question_payload``）把答案字段叫
    ``reveal_formula``，而数据库查出来的行就叫 ``example_formula``。
    与其在业务代码里各写一套取值逻辑（迟早有一边漏掉一个别名），
    不如在这里一次收口。
    """
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return default


def _scenario_bullets(value) -> str:
    """「场景一；场景二」→ 项目符号列表。切不出东西时返回空串。"""
    parts = [part.strip() for part in _SCENARIO_RE.split(_text(value)) if part.strip()]
    return "\n".join(f"- {part}" for part in parts)


def _quote_block(value) -> str:
    """多行文本 → 引用块。

    题干常常是多行的（一段说明 + 两三条场景），直接塞进段落会被渲染器当
    软换行拼成一整行，糊成一团。引用块每行都带 ``>``，读起来才有层次。
    """
    lines = [line.strip() for line in _text(value).split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    return "\n".join("> " + line for line in lines)


def _section(title: str, body: str) -> str:
    """「小标题 + 正文」。正文为空时整段不出现 —— 不留空标题。"""
    body = _text(body)
    if not body:
        return ""
    return f"**{title}**\n\n{body}"


# =============================================================================
# 纯函数：模板 / 拆分 / 合并
# =============================================================================

def split_generated(content: str) -> tuple[str, str, bool]:
    """把正文切成 ``(生成区, 我的补充, 标记是否成对)``。

    标记缺失或不成对（用户手删了一个）时返回 ``("", 全文, False)``：调用方
    据此**整篇当用户自己写的东西**，只把生成区补在最前面，绝不丢内容。
    宁可少覆盖一次，也不能把人写的东西当生成内容冲掉。
    """
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    start = text.find(GEN_START)
    end = text.find(GEN_END)
    if start < 0 or end < 0 or end < start:
        return "", text.strip("\n"), False
    body = text[start + len(GEN_START):end].strip("\n")
    tail = text[end + len(GEN_END):].strip("\n")
    return body, tail, True


def default_user_section() -> str:
    """新建笔记时给「我的补充」铺的那段引导文案。"""
    return f"## {USER_SECTION_TITLE}\n\n{USER_SECTION_HINT}"


def compose_note(generated_body: str, user_body: str = "") -> str:
    """拼一整篇：生成区 + 我的补充。``user_body`` 为空时补引导文案。"""
    user = (user_body or "").strip()
    if not user:
        user = default_user_section()
    return f"{GEN_START}\n{_text(generated_body)}\n{GEN_END}\n\n{user}\n"


def merge_generated(content: str, generated_body: str) -> str:
    """**只换生成区**，标记之外原样保留 —— 这个函数就是「二创不会被覆盖」。"""
    _, user_body, _ = split_generated(content)
    return compose_note(generated_body, user_body)


def _meta_line(item: dict, *, todo_title: str, todo_done: bool) -> str:
    """一行元信息。全为空时返回空串（不留一条光秃秃的横线）。"""
    parts: list[str] = []
    category = _text(item.get("category"))
    if category:
        parts.append(f"分类：{category}")
    mastery = item.get("mastery")
    if mastery not in (None, ""):
        parts.append(f"掌握度：{mastery_label(mastery)}")
    next_review = _text(item.get("next_review_at"))
    if next_review:
        parts.append(f"下次复习：{next_review[:_DATE_LEN]}")
    book_page = _text(item.get("book_page"))
    if book_page:
        parts.append(f"书页：{book_page}")
    line = " · ".join(parts)
    todo = _text(todo_title)
    if todo:
        state = "已完成" if todo_done else "未完成"
        tail = f"关联待办：{todo}（{state}）"
        line = f"{line}\n{tail}" if line else tail
    return line


def _quiz_section(item: dict) -> str:
    """「本轮自测」那一段。没有作答记录（is_correct 缺失）时整段不出现。"""
    if item.get("is_correct") is None:
        return ""
    answer = _pick(item, "answer")
    user_answer = _pick(item, "user_answer")
    if int(item.get("is_correct") or 0):
        head = "答对了。"
        if user_answer:
            head += f"你的作答：{user_answer}"
    else:
        head = "答错了。"
        detail = []
        if user_answer:
            detail.append(f"你填的是「{user_answer}」")
        if answer:
            detail.append(f"正确答案是「{answer}」")
        if detail:
            head += f"（{'，'.join(detail)}）"
    parts = [head]
    prompt = _quote_block(_pick(item, "prompt"))
    if prompt:
        parts += ["", "题目：", "", prompt]
    return _section("本轮自测", "\n".join(parts))


def generated_body(item: dict, *, generated_at: str = "",
                   todo_title: str = "", todo_done: bool = False) -> str:
    """生成区正文（**不含**标记本身）。

    所有字段缺了就整段不出现，所以同一个函数无论来自「本轮自测的题目字典」
    还是「数据库里查出来的行」都能用。
    """
    code = _text(item.get("code"))
    name_cn = _text(item.get("name_cn"))
    heading = f"{code}｜{name_cn}" if name_cn else code

    stamp = " · ".join(
        part for part in ("**自动生成**", _text(generated_at),
                          f"来自「{SOURCE_LABEL}」") if part
    )
    blocks: list[str] = [
        f"> {stamp}",
        "> 这一段重新生成时会整段覆盖；想留的东西写在下面「我的补充」。",
        "",
        f"## {heading}",
    ]
    meta = _meta_line(item, todo_title=todo_title, todo_done=todo_done)
    if meta:
        blocks += ["", meta]

    syntax = _pick(item, "syntax")
    if syntax:
        blocks.append(_section("语法", f"`{syntax}`"))

    formula = _pick(item, "example_formula", "reveal_formula")
    result = _pick(item, "example_result", "reveal_result")
    if formula:
        example = f"`{formula}`"
        if result:
            example += f" → {result}"
        blocks.append(_section("示例", example))

    description = _pick(item, "description")
    if description:
        blocks.append(_section("一句话", description))

    bullets = _scenario_bullets(_pick(item, "use_cases"))
    if bullets:
        blocks.append(_section("适用场景", bullets))

    pitfalls = _pick(item, "pitfalls", "reveal_pitfalls")
    if pitfalls:
        blocks.append(_section("易错点", pitfalls))

    quiz = _quiz_section(item)
    if quiz:
        blocks.append(quiz)

    return "\n".join(part for part in blocks if part).strip() + "\n"


def note_title(item: dict) -> str:
    """笔记标题。带函数码，列表里一眼能看出是哪一页。"""
    code = _text(item.get("code"))
    if not code:
        return ""
    name_cn = _text(item.get("name_cn"))
    return f"Excel 函数 {code}｜{name_cn}" if name_cn else f"Excel 函数 {code}"


def note_tags(item: dict) -> list[str]:
    """笔记标签：``[Excel, 函数码, 错题?]``。

    函数码进标签是为了**稳定身份** —— 标题用户会改，标签不会。
    """
    tags = [NOTE_TAG]
    code = _text(item.get("code"))
    if code:
        tags.append(code)
    if item.get("is_correct") is not None and not int(item.get("is_correct") or 0):
        tags.append(WRONG_TAG)
    return tags


def build_note_template(item: dict, *, generated_at: str = "",
                        todo_title: str = "", todo_done: bool = False) -> dict:
    """一个函数 → 一篇笔记模板。

    返回 ``{"title", "tags", "gen_body", "content"}``：
    ``gen_body`` 给「更新已有笔记」用（只替换标记内那段），
    ``content`` 是新建时用的整篇（生成区 + 空白的「我的补充」）。
    """
    body = generated_body(item, generated_at=generated_at,
                          todo_title=todo_title, todo_done=todo_done)
    return {
        "title": note_title(item),
        "tags": note_tags(item),
        "gen_body": body,
        "content": compose_note(body),
    }


# =============================================================================
# 写库胶水
# =============================================================================

class ExcelNoteBridge:
    """「Excel 宝典 → 学习笔记」的写库胶水。构造时给自己一个 ``StudyNotesDB``。"""

    def __init__(self, study_db, *, category_name: str = LOCKED_CATEGORY_NAME,
                 source_key: str = NOTE_SOURCE_KEY):
        self.study_db = study_db
        self.category_name = category_name
        self.source_key = source_key

    # -- 落点（锁定分类）-------------------------------------------------

    def existing_category_code(self) -> str:
        """**只看不建**：锁定分类已经存在时返回它的编码，否则空串。

        为什么把「看」和「建」分开：待办备注、按钮可用状态这些地方只是想知道
        「有没有生成过笔记」，顺手在用户库里建一个空分类是副作用。
        真正要写笔记时才走 ``ensure_category``。
        """
        cat = self.study_db.find_category_by_source_key(self.source_key)
        return cat.code if cat else ""

    def ensure_category(self) -> str:
        """拿到（必要时创建）锁定分类，返回编码。幂等，见数据层同名方法。"""
        return self.study_db.ensure_locked_category(
            source_key=self.source_key, name=self.category_name)

    def count_notes(self) -> int:
        code = self.existing_category_code()
        if not code:
            return 0
        return int(self.study_db.count_notes_by_category(code) or 0)

    def pointer_text(self) -> str:
        """给待办备注用的一句话；还没生成过笔记时返回空串（不占位、不提这事）。"""
        count = self.count_notes()
        if not count:
            return ""
        return f"笔记：{NOTE_AREA_LABEL}（已生成 {count} 篇）"

    # -- 找回同一篇 ------------------------------------------------------

    def find_note(self, *, category_code: str, code: str):
        """在锁定分类里按**标签里的函数码**找回上次生成的同一篇；没有则 None。

        为什么按标签而不是标题：生成的标题用户完全可能改掉（「二创」本来就
        包括改标题），按标题找会变成「改一次标题就多一篇」。函数码唯一，而且
        是我们写进标签的 —— 它就是这篇笔记的稳定身份。

        另加一道「正文里有生成标记」的判断：用户自己在同一分类下写了一篇
        标签里也带 SUM 的笔记，不该被当成生成的那篇覆盖掉。
        """
        wanted = _text(code).lower()
        if not wanted or not category_code:
            return None
        for note in self.study_db.fetch_notes(category_code=category_code):
            tags = {_text(tag).lower() for tag in (note.tags or [])}
            if wanted in tags and GEN_START in (note.content or ""):
                return note
        return None

    # -- 分类 → 预览 / 落库（同一条路径）----------------------------------

    def _classify(self, items, *, category_code: str, generated_at: str,
                  todo_title: str, todo_done: bool) -> list[tuple]:
        """把 items 分成「要新建」和「要更新」。

        ★ **预览与实际写库共用这一条路径**。两边各写一套是危险的：预览说
        「新建 3 篇」、真跑却更新了 3 篇，用户看到的就是「确认框在骗人」。
        所以判定只算一次（这条教训来自 CSV 导入那次 dry_run 返工）。
        """
        planned: list[tuple] = []
        for item in items or []:
            code = _text(item.get("code"))
            if not code:
                continue      # 函数被删过的孤儿流水（LEFT JOIN 出来 code 为空）
            payload = build_note_template(item, generated_at=generated_at,
                                          todo_title=todo_title,
                                          todo_done=todo_done)
            note = self.find_note(category_code=category_code, code=code)
            planned.append((item, payload, note))
        return planned

    def plan_notes(self, items, *, generated_at: str = "",
                   todo_title: str = "", todo_done: bool = False) -> dict:
        """只算不写：确认框用它说清楚「会新建几篇、更新几篇」。"""
        category_code = self.existing_category_code()      # 只看不建
        planned = self._classify(items, category_code=category_code,
                                 generated_at=generated_at,
                                 todo_title=todo_title, todo_done=todo_done)
        created = [p for p in planned if p[2] is None]
        updated = [p for p in planned if p[2] is not None]
        return {
            "total": len(planned),
            "created": len(created),
            "updated": len(updated),
            "created_titles": [p[1]["title"] for p in created],
            "updated_titles": [p[1]["title"] for p in updated],
            "area": NOTE_AREA_LABEL,
            "first_run": not category_code,
        }

    def sync_notes(self, items, *, generated_at: str = "",
                   todo_title: str = "", todo_done: bool = False) -> dict:
        """把一批函数整理成笔记：没有的**建**，已有的只换生成区。

        返回值 ``{"created", "updated", "total", "area", "titles",
        "category_code"}`` —— 界面直接拿去拼状态栏那句话，不用自己数。
        """
        category_code = self.ensure_category()
        planned = self._classify(items, category_code=category_code,
                                 generated_at=generated_at,
                                 todo_title=todo_title, todo_done=todo_done)
        created = updated = 0
        titles: list[str] = []
        for _item, payload, note in planned:
            titles.append(payload["title"])
            if note is None:
                self.study_db.add_note({
                    "category_code": category_code,
                    "category_name": self.category_name,
                    "title": payload["title"],
                    "content": payload["content"],
                    "tags": payload["tags"],
                    "source_id": 0,
                })
                created += 1
                continue
            # 更新：**标题与标签以用户改过的为准**，只有正文的生成区换新的。
            # 合并用 dict.fromkeys 去重保序：用户自己加的标签不会被挤掉。
            tags = list(dict.fromkeys([*(note.tags or []), *payload["tags"]]))
            self.study_db.update_note(note.id, {
                "category_code": category_code,
                "category_name": self.category_name,
                "title": _text(note.title) or payload["title"],
                "content": merge_generated(note.content, payload["gen_body"]),
                "tags": tags,
                "source_id": note.source_id,
            })
            updated += 1
        logger.info("Excel 笔记同步：新建 %s 篇、更新 %s 篇", created, updated)
        return {
            "created": created,
            "updated": updated,
            "total": created + updated,
            "area": NOTE_AREA_LABEL,
            "titles": titles,
            "category_code": category_code,
        }
