# -*- coding: utf-8 -*-
"""Excel 宝典 → 学习笔记 联动回归（纯数据层 + 纯函数，不碰 Tk）。

为什么单独成篇
------------------------------------------------------------------------------
这条链路上算错的地方，**界面上全都看不出来**：

* **「我的补充」被覆盖掉**：这是本模块存在的前提 —— 用户二创的内容必须
  永远活着。生成区与自写区只靠一对 HTML 注释标记分隔，`merge_generated`
  一旦写成「整篇换掉」，用户下次点「生成学习笔记」就会**静默**丢掉自己写
  的心得，而且没有任何提示。这类丢失只有测试守得住。
* **预览与实际不一致**：确认框说「新建 3 篇」、真跑却更新了 3 篇。判定必须
  收口在 `_classify` 一条路径上（预览与写库共用），两边各写一套迟早漂移
  （CSV 导入那次 dry_run 返工就是这个原因）。
* **只读接口顺手建分类**：`pointer_text()` 是给待办备注用的，调一次就在用
  户库里建出一个空分类是副作用。`existing_category_code` 与 `ensure_category`
  必须分开，「看」不许写成「建」。
* **锁定分类被改名/删除**：它是别的模块的笔记落点，改了名下次生成就找不到，
  删了笔记全成孤儿。数据层必须硬拦（`update_category` 返回 False、
  `delete_category` 返回 `(0, 0)`），**同时在界面之外生效** —— 表上能改的
  地方不止一个。
* **`get_next_category_code` 被字母码噎住**：`_free_top_code` 在极端情况下会
  退回 `L09` 这种字母码。老实现 `int(last_code[:2])` 直接 `ValueError`，
  于是「建一个新分类」这个最普通的操作会炸 —— 而它只在极罕见的数据状态下
  才复现。
* **懒创建的进度行把新学的滤掉**：`excel_progress` 只有标过掌握度才有一行。
  `recent_quiz_answers` 少写一个 LEFT JOIN，刚学完还没标掌握度的函数就全被
  滤掉，而它们**恰恰最该记笔记**（今日复习那次踩过同一个坑）。

覆盖
------------------------------------------------------------------------------
A. 标记与合并    split_generated 成对/缺标记/不成对 / compose_note 铺引导文案 /
                 merge_generated 只换生成区、标记不成对时一个字都不丢
B. 模板字段      title / tags（错题）/ 六个小节 / 场景切分 / 示例字段别名
                 （reveal_* 与 example_*）/ 缺字段整段不出现 / 关联待办那一行
C. 分类锁定      ensure_locked_category 幂等 / 按 source_key 找回 /
                 改名被拒 / 删除被拒 / **不影响用户自己的分类增删改** /
                 字母码不噎住 get_next_category_code
D. 桥接只读      existing_category_code 与 count_notes 不建分类 /
                 pointer_text 空库返回空串
E. 找回同一篇    按标签找回 / 改过标题仍找得到 / 用户同名标签但无标记的笔记不被误认
F. 预览=写库     plan_notes 与 sync_notes 口径一致 / first_run / 二次生成是「更新」
G. 二创不丢      二次生成后：自改标题、追加标签、自写的「我的补充」全都还在，
                 生成区换成新的
H. 切轮纯函数    group_quiz_round 45 分钟分界 / 同函数留最新 / 错题优先 /
                 时间戳坏掉不切 / 空输入
I. 懒创建防线    recent_quiz_answers 带上没标过掌握度的函数、函数删了流水还在
J. 待办反向      待办备注带上笔记指纹；没生成过笔记时那一行不出现

用法：
    python scripts/test_excel_note.py
"""

import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from excel_db import (  # noqa: E402
    QUIZ_CHOICE,
    QUIZ_ROUND_GAP_MINUTES,
    ExcelDB,
    group_quiz_round,
)
from excel_note_bridge import (  # noqa: E402
    LOCKED_CATEGORY_NAME,
    NOTE_AREA_LABEL,
    NOTE_SOURCE_KEY,
    NOTE_TAG,
    SOURCE_LABEL,
    USER_SECTION_HINT,
    USER_SECTION_TITLE,
    WRONG_TAG,
    ExcelNoteBridge,
    build_note_template,
    compose_note,
    default_user_section,
    generated_body,
    merge_generated,
    note_tags,
    note_title,
    split_generated,
)
from excel_todo_bridge import review_todo_payload  # noqa: E402
from study_notes_db import GEN_END, GEN_START, StudyNotesDB  # noqa: E402


PASSED = 0
FAILED = 0
_TMP: list[Path] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}")


def _tmpdir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="excel_note_test_"))
    _TMP.append(d)
    return d


def fresh_notes(name: str = "notes.db") -> StudyNotesDB:
    """每个小节一个独立空库：这些用例大量依赖「初始状态」，共用会互相污染。"""
    return StudyNotesDB(_tmpdir() / name)


def fresh_excel(name: str = "excel.db", seed: bool = True) -> ExcelDB:
    return ExcelDB(_tmpdir() / name, seed=seed)


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# 夹具
# ══════════════════════════════════════════════════════════════════════════
# 一条「本轮自测答错的题」：字段名刻意用题目字典那一套（reveal_formula），
# 因为 B 节要顺带证明别名取值是通的。
WRONG_ITEM = {
    "function_id": 7,
    "code": "SUM",
    "name_cn": "求和",
    "category": "数学统计",
    "syntax": "=SUM(number1, [number2], ...)",
    "reveal_formula": "=SUM(A1:A10)",
    "reveal_result": "55",
    "description": "把一批数字加起来。",
    "use_cases": "统计月度销售额；算总分",
    "pitfalls": "整列求和时别把标题行的文字一起选进去",
    "book_page": "P12",
    "mastery": 0,
    "next_review_at": "2026-09-25T09:00:00",
    "prompt": "把 A1:A10 加起来，应该用哪个函数？",
    "answer": "SUM",
    "user_answer": "AVERAGE",
    "is_correct": 0,
}

OK_ITEM = {
    "function_id": 8,
    "code": "AVERAGE",
    "name_cn": "平均值",
    "category": "数学统计",
    "syntax": "=AVERAGE(number1, [number2], ...)",
    "example_formula": "=AVERAGE(B1:B10)",
    "example_result": "12.5",
    "description": "求一批数字的平均值。",
    "use_cases": "算平均分",
    "is_correct": 1,
    "user_answer": "AVERAGE",
}


# ══════════════════════════════════════════════════════════════════════════
# A. 标记与合并
# ══════════════════════════════════════════════════════════════════════════
def test_markers() -> None:
    section("[A] 标记与合并（二创保命的那一层）")

    body = generated_body(WRONG_ITEM, generated_at="2026-09-24 10:29")
    note = compose_note(body)
    gen, tail, paired = split_generated(note)
    check("compose_note 出来的笔记标记成对", paired)
    check("切回来的生成区与原文一致", gen == body.strip("\n"),
          f"{gen[:40]!r} vs {body[:40]!r}")
    check("切回来的尾段就是「我的补充」",
          tail.startswith(f"## {USER_SECTION_TITLE}"), tail[:40])

    check("没有标记的正文一律当用户自己写的",
          split_generated("我随手写的一篇")[2] is False)
    check("只有开始标记 → 不成对",
          split_generated(f"{GEN_START}\n半截")[2] is False)
    check("只有结束标记 → 不成对",
          split_generated(f"半截\n{GEN_END}")[2] is False)
    check("空串不炸", split_generated("") == ("", "", False))

    check("compose_note 不给 tail 时铺引导文案",
          USER_SECTION_TITLE in compose_note(body)
          and compose_note(body).rstrip().endswith("）"))
    check("default_user_section 带标题",
          default_user_section().startswith(f"## {USER_SECTION_TITLE}"))

    # ── 核心不变量：只换生成区 ──
    old = compose_note("## 旧内容\n\n过时的东西", "## 我的补充\n\n这是我自己写的，别动。")
    merged = merge_generated(old, "## 新内容\n\n新的东西")
    check("merge 后生成区换成新的", "## 新内容" in merged and "## 旧内容" not in merged)
    check("merge 后自写内容一个字没丢", "这是我自己写的，别动。" in merged)
    check("merge 后「我的补充」标题只出现一次",
          merged.count(f"## {USER_SECTION_TITLE}") == 1,
          merged.count(f"## {USER_SECTION_TITLE}"))
    check("merge 后仍然成对", split_generated(merged)[2])

    # ── 不成对时宁可少覆盖，不丢内容 ──
    broken = f"{GEN_START}\n老生成区\n我自己写的一段话，没有结束标记"
    rescued = merge_generated(broken, "## 新生成区")
    check("标记不成对时用户那段话还在", "我自己写的一段话" in rescued, rescued)
    check("标记不成对时生成区仍被补上", "## 新生成区" in rescued)
    # 再合并一次也要稳定（别把补进去的东西反复搬家）
    again = merge_generated(rescued, "## 第三版")
    check("不成对的内容再合并一次仍然不丢", "我自己写的一段话" in again)
    check("不成对的内容再合并一次仍成对", split_generated(again)[2])


# ══════════════════════════════════════════════════════════════════════════
# B. 模板字段
# ══════════════════════════════════════════════════════════════════════════
def test_template_fields() -> None:
    section("[B] 模板字段（缺字段就整段不出现）")

    check("标题带函数码与中文名", note_title(WRONG_ITEM) == "Excel 函数 SUM｜求和",
          note_title(WRONG_ITEM))
    check("没有中文名时只用函数码",
          note_title({"code": "SUM"}) == "Excel 函数 SUM")
    check("没有函数码就没有标题", note_title({}) == "")

    check("答错的标签多一个「错题」",
          note_tags(WRONG_ITEM) == [NOTE_TAG, "SUM", WRONG_TAG], note_tags(WRONG_ITEM))
    check("答对的标签不带「错题」",
          note_tags(OK_ITEM) == [NOTE_TAG, "AVERAGE"], note_tags(OK_ITEM))
    check("没作答过就不加「错题」标签",
          note_tags({"code": "IF"}) == [NOTE_TAG, "IF"])

    payload = build_note_template(WRONG_ITEM, generated_at="2026-09-24 10:29")
    check("模板四件套齐全",
          set(payload) == {"title", "tags", "gen_body", "content"}, set(payload))
    body = payload["gen_body"]
    for head in ("## SUM｜求和", "**语法**", "**示例**", "**一句话**",
                 "**适用场景**", "**易错点**", "**本轮自测**"):
        check(f"生成区含 {head}", head in body)
    check("生成区标明来源", SOURCE_LABEL in body)
    check("生成区第一行就是标记，不含标记本身", GEN_START not in body)
    check("整篇 content 才带标记", GEN_START in payload["content"])

    check("示例走 reveal_* 别名（题干那套字段名）",
          "=SUM(A1:A10)" in body and "55" in body)
    check("示例也认 example_* 字段名",
          "=AVERAGE(B1:B10)" in generated_body(OK_ITEM))
    check("场景按分号切成两条项目符号",
          body.count("\n- ") == 2, [ln for ln in body.splitlines() if ln.startswith("- ")])
    check("题干转成引用块",
          "> 把 A1:A10 加起来" in body)
    check("答错写了你的作答与正确答案",
          "你填的是「AVERAGE」" in body and "正确答案是「SUM」" in body)
    check("答对也留一句", "答对了。" in generated_body(OK_ITEM))
    check("答对时不写「答错了」", "答错了" not in generated_body(OK_ITEM))

    # 元信息
    check("元信息带分类/掌握度/下次复习/书页",
          all(part in body for part in ("分类：数学统计", "掌握度：",
                                        "下次复习：2026-09-25", "书页：P12")), body[:400])
    check("下次复习只到天（不出现时分秒）",
          "2026-09-25T" not in body)
    with_todo = generated_body(WRONG_ITEM, todo_title="复习 Excel（3 个）",
                               todo_done=False)
    check("关联待办那一行写得出来", "关联待办：复习 Excel（3 个）（未完成）" in with_todo)
    with_done = generated_body(WRONG_ITEM, todo_title="复习 Excel（3 个）",
                               todo_done=True)
    check("待办已完成时状态跟着变", "（已完成）" in with_done)

    # 极简条目：只剩函数码，所有小节都该消失
    bare = generated_body({"code": "IF", "name_cn": ""})
    check("没有中文名时标题只用函数码", "## IF" in bare and "｜" not in bare, bare)
    for head in ("**语法**", "**示例**", "**一句话**", "**适用场景**",
                 "**易错点**", "**本轮自测**"):
        check(f"缺字段时 {head} 整段不出现", head not in bare)
    check("缺字段时也不留元信息空行", "分类：" not in bare)


# ══════════════════════════════════════════════════════════════════════════
# C. 分类锁定
# ══════════════════════════════════════════════════════════════════════════
def test_locked_category() -> None:
    section("[C] 锁定分类（改不了名、删不掉，但不挡用户自己的分类）")
    db = fresh_notes()

    before = len(db.conn.execute("SELECT id FROM study_categories").fetchall())
    code = db.ensure_locked_category(source_key=NOTE_SOURCE_KEY,
                                     name=LOCKED_CATEGORY_NAME)
    after = len(db.conn.execute("SELECT id FROM study_categories").fetchall())
    check("首次调用建出锁定分类", bool(code) and after == before + 1,
          f"{before} → {after}，code={code!r}")

    again = db.ensure_locked_category(source_key=NOTE_SOURCE_KEY,
                                      name=LOCKED_CATEGORY_NAME)
    after2 = len(db.conn.execute("SELECT id FROM study_categories").fetchall())
    check("再次调用是幂等的（编码不变）", again == code, f"{code!r} vs {again!r}")
    check("再次调用不多建一个", after2 == after, f"{after} → {after2}")

    found = db.find_category_by_source_key(NOTE_SOURCE_KEY)
    check("按 source_key 能找回", found is not None and found.code == code)
    check("找回来的就是锁定分类", found.locked == 1, getattr(found, "locked", None))
    check("锁定分类挂在顶级", bool(found) and not found.parent_code,
          getattr(found, "parent_code", None))
    check("找不到的 source_key 返回 None",
          db.find_category_by_source_key("没这个东西") is None)

    # ── 改名 / 删除必须被拦下 ──
    check("改名被拒（返回 False）",
          db.update_category(found.id, "改个名字") is False)
    check("改名被拒后名字没动",
          db.get_category(found.id).name == LOCKED_CATEGORY_NAME,
          db.get_category(found.id).name)
    check("删除被拒（返回 (0, 0)）",
          db.delete_category(found.id) == (0, 0), db.delete_category(found.id))
    check("删除被拒后分类还在", db.get_category(found.id) is not None)

    # ── 只约束它自己：用户自己的分类照常增删改 ──
    # 注意 `add_category` 只负责插、不返回编码（要编码自己先取），
    # 所以这里先算编码再回查 id。
    mine_code = db.get_next_category_code("")
    db.add_category(code=mine_code, name="我自己的分类")
    row = db.conn.execute(
        "SELECT id FROM study_categories WHERE code = ?", (mine_code,)
    ).fetchone()
    check("用户能新建自己的分类（不被锁定机制挡住）", row is not None, mine_code)
    mine_id = row["id"] if row else 0
    check("用户能改自己分类的名字",
          db.update_category(mine_id, "我改名了") is True)
    check("改名确实生效",
          db.get_category(mine_id).name == "我改名了",
          db.get_category(mine_id).name)
    deleted, _notes = db.delete_category(mine_id)
    check("用户能删自己的分类", db.get_category(mine_id) is None, deleted)
    check("删掉用户分类不影响锁定分类", db.get_category(found.id) is not None)

    # ── 字母回退码不许噎住「新建分类」──
    db.add_category(code="L99", name="怪编码分类")
    try:
        nxt = db.get_next_category_code("")
        ok = bool(nxt)
        err = ""
    except Exception as exc:            # noqa: BLE001 —— 就是要抓住它
        ok, err, nxt = False, f"{type(exc).__name__}: {exc}", ""
    check("存在字母码时 get_next_category_code 仍然能给出编码", ok,
          f"{err} → {nxt!r}")
    check("给出的编码是纯数字（不会是字母码）", nxt.isdigit(), nxt)

    try:
        db.ensure_locked_category(source_key="   ", name="空的")
        raised = False
    except ValueError:
        raised = True
    check("source_key 为空时明确报错（不然没法幂等）", raised)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# D. 桥接只读
# ══════════════════════════════════════════════════════════════════════════
def test_bridge_readonly() -> None:
    section("[D] 只读接口不许建分类")
    db = fresh_notes()
    bridge = ExcelNoteBridge(db)
    before = len(db.conn.execute("SELECT id FROM study_categories").fetchall())

    check("空库里 existing_category_code 是空串",
          bridge.existing_category_code() == "")
    check("空库里 count_notes 是 0", bridge.count_notes() == 0)
    check("一篇都没生成时 pointer_text 是空串（不写「0 篇」占位）",
          bridge.pointer_text() == "", repr(bridge.pointer_text()))
    after = len(db.conn.execute("SELECT id FROM study_categories").fetchall())
    check("★ 三次只读调用没在用户库里建出任何分类", after == before,
          f"{before} → {after}")

    plan = bridge.plan_notes([WRONG_ITEM], generated_at="2026-09-24 10:29")
    after2 = len(db.conn.execute("SELECT id FROM study_categories").fetchall())
    check("干跑也不建分类", after2 == before, f"{before} → {after2}")
    check("干跑标出 first_run", plan["first_run"] is True)
    check("干跑说清会新建几篇", plan["created"] == 1 and plan["updated"] == 0,
          plan)

    result = bridge.sync_notes([WRONG_ITEM], generated_at="2026-09-24 10:29")
    check("真跑才建分类", bridge.existing_category_code() == result["category_code"])
    check("真跑新建 1 篇", result["created"] == 1 and result["updated"] == 0, result)
    check("真跑返回落点给人看", result["area"] == NOTE_AREA_LABEL, result["area"])
    check("计数跟上", bridge.count_notes() == 1, bridge.count_notes())
    check("pointer_text 报出篇数",
          bridge.pointer_text() == f"笔记：{NOTE_AREA_LABEL}（已生成 1 篇）",
          bridge.pointer_text())

    plan2 = bridge.plan_notes([WRONG_ITEM], generated_at="2026-09-24 11:00")
    check("★ 干跑与真跑口径一致：第二遍说「更新 1 篇」",
          plan2["created"] == 0 and plan2["updated"] == 1, plan2)
    check("第二遍不再是 first_run", plan2["first_run"] is False)
    result2 = bridge.sync_notes([WRONG_ITEM], generated_at="2026-09-24 11:00")
    check("真跑第二遍确实是更新", result2["created"] == 0
          and result2["updated"] == 1, result2)
    check("两遍之后还是 1 篇（不会越攒越多）", bridge.count_notes() == 1,
          bridge.count_notes())

    check("没函数码的孤儿流水被跳过",
          len(bridge._classify([{"code": ""}, {"code": "SUM"}],
                               category_code=result["category_code"],
                               generated_at="", todo_title="",
                               todo_done=False)) == 1)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# E. 找回同一篇
# ══════════════════════════════════════════════════════════════════════════
def test_find_note() -> None:
    section("[E] 按函数码找回同一篇（不是按标题）")
    db = fresh_notes()
    bridge = ExcelNoteBridge(db)
    code = bridge.ensure_category()

    check("空分类里找不到", bridge.find_note(category_code=code, code="SUM") is None)
    check("函数码为空直接 None",
          bridge.find_note(category_code=code, code="") is None)
    check("分类码为空直接 None",
          bridge.find_note(category_code="", code="SUM") is None)

    bridge.sync_notes([WRONG_ITEM], generated_at="2026-09-24 10:29")
    found = bridge.find_note(category_code=code, code="SUM")
    check("按标签找得到", found is not None)
    check("大小写不敏感",
          bridge.find_note(category_code=code, code="sum") is not None)

    # 用户改了标题 —— 身份靠标签，照样找得到
    db.update_note(found.id, {
        "category_code": found.category_code,
        "category_name": found.category_name,
        "title": "我自己起的标题：SUM 的坑",
        "content": found.content,
        "tags": found.tags,
        "source_id": found.source_id,
    })
    found2 = bridge.find_note(category_code=code, code="SUM")
    check("★ 改过标题仍找得到同一篇",
          found2 is not None and found2.id == found.id,
          f"{found.id} vs {getattr(found2, 'id', None)}")

    # 用户自己写的一篇，标签里也带 SUM，但正文没有生成标记 → 不许被误认
    mine_id = db.add_note({
        "category_code": code,
        "category_name": LOCKED_CATEGORY_NAME,
        "title": "我手写的 SUM 笔记",
        "content": "## 我的理解\n\nSUM 就是个加法，没有标记。",
        "tags": [NOTE_TAG, "SUM"],
        "source_id": 0,
    })
    hit = bridge.find_note(category_code=code, code="SUM")
    check("★ 用户自己带同名标签但没标记的笔记不被当成生成的那篇",
          hit is not None and hit.id != mine_id, f"hit={getattr(hit, 'id', None)}")
    check("误认保护下仍会命中真正生成的那篇", hit.id == found.id)

    plan = bridge.plan_notes([WRONG_ITEM], generated_at="2026-09-25 09:00")
    check("再生成时算成「更新」而不是新建", plan["updated"] == 1
          and plan["created"] == 0, plan)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# F. 二创不丢
# ══════════════════════════════════════════════════════════════════════════
def test_second_edit_survives() -> None:
    section("[F] 二创内容在二次生成后必须一个字不丢")
    db = fresh_notes()
    bridge = ExcelNoteBridge(db)
    code = bridge.ensure_category()
    bridge.sync_notes([WRONG_ITEM], generated_at="2026-09-24 10:29")
    note = bridge.find_note(category_code=code, code="SUM")

    my_text = "这里是我踩过的坑，绝对不能丢。"
    check("前置：新建的笔记里铺着引导文案", USER_SECTION_HINT in note.content)

    # 模拟用户二创三件事：改标题、追加标签、把引导文案换成自己写的正文；
    # 顺手**往生成区里也塞一句**（这句按约定应该被覆盖掉）。
    tampered = note.content.replace(USER_SECTION_HINT, my_text).replace(
        GEN_END, f"\n> 我往生成区里也塞了一句。\n{GEN_END}", 1)
    db.update_note(note.id, {
        "category_code": note.category_code,
        "category_name": note.category_name,
        "title": "SUM 心得（我改过标题）",
        "content": tampered,
        "tags": [*(note.tags or []), "重点"],
        "source_id": note.source_id,
    })
    edited = db.get_note(note.id)
    check("前置：自写内容确实落库了", my_text in edited.content,
          edited.content[-160:])
    check("前置：标题确实改了", edited.title == "SUM 心得（我改过标题）",
          edited.title)

    # 二次生成（新的时间戳 → 生成区该换）
    result = bridge.sync_notes([WRONG_ITEM], generated_at="2026-09-26 08:00",
                               todo_title="复习 Excel（1 个）")
    check("二次生成算成更新", result["updated"] == 1 and result["created"] == 0,
          result)
    after = db.get_note(note.id)
    check("★ 自写的「我的补充」正文还在", my_text in after.content,
          after.content[-200:])
    check("★ 用户改过的标题保住了", after.title == "SUM 心得（我改过标题）",
          after.title)
    check("★ 用户追加的标签保住了", "重点" in (after.tags or []), after.tags)
    check("生成的标签也在（去重合并）",
          "Excel" in (after.tags or []) and "SUM" in (after.tags or []),
          after.tags)
    check("标签没有重复项", len(after.tags) == len(set(after.tags)), after.tags)
    check("★ 生成区换成新的时间戳", "2026-09-26 08:00" in after.content)
    check("生成区的旧时间戳被换掉了", "2026-09-24 10:29" not in after.content)
    check("生成区里带上了关联待办", "关联待办：复习 Excel（1 个）" in after.content)
    # 这条是**有意**的取舍，钉住免得以后被当 bug「修」掉：
    # 生成区就是生成区，用户往里写的东西会被覆盖 —— 要留的写「我的补充」。
    check("★ 用户塞进生成区的那句被覆盖了（有意：要留的写「我的补充」）",
          "我往生成区里也塞了一句" not in after.content)
    check("笔记篇数不变", bridge.count_notes() == 1, bridge.count_notes())
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# G. 切轮纯函数
# ══════════════════════════════════════════════════════════════════════════
def _row(minutes_ago: int, *, fid: int, correct: int, base=None) -> dict:
    base = base or datetime(2026, 9, 24, 12, 0, 0)
    return {
        "function_id": fid,
        "code": f"F{fid}",
        "is_correct": correct,
        "created_at": (base - timedelta(minutes=minutes_ago)).isoformat(
            timespec="seconds"),
    }


def test_group_round() -> None:
    section("[G] group_quiz_round：切轮 / 去重 / 错题优先")
    check("空输入返回空", group_quiz_round([]) == [])
    check("第一轮分界是 45 分钟", QUIZ_ROUND_GAP_MINUTES == 45,
          QUIZ_ROUND_GAP_MINUTES)

    # 倒序传入（与库里 ORDER BY id DESC 一致）：0、10、20 分钟前是一轮；
    # 80 分钟前那条第隔了 60 分钟 → 停。
    rows = [_row(0, fid=1, correct=1), _row(10, fid=2, correct=0),
            _row(20, fid=3, correct=1), _row(80, fid=4, correct=1)]
    picked = group_quiz_round(rows)
    check("★ 只取最近一轮（3 条），不把上一轮带进来",
          len(picked) == 3 and all(r["function_id"] != 4 for r in picked),
          [r["function_id"] for r in picked])

    rows = [_row(0, fid=1, correct=1), _row(50, fid=2, correct=0)]
    check("超过 45 分钟就断",
          len(group_quiz_round(rows)) == 1,
          [r["function_id"] for r in group_quiz_round(rows)])
    rows = [_row(0, fid=1, correct=1), _row(44, fid=2, correct=0)]
    check("正好 44 分钟不断（边界内侧）",
          len(group_quiz_round(rows)) == 2)
    rows = [_row(0, fid=1, correct=1), _row(46, fid=2, correct=0)]
    check("46 分钟断了（边界外侧）",
          len(group_quiz_round(rows)) == 1)

    # 去重：同一个函数连问两次，留最近那条（倒序里先见到的）
    rows = [_row(0, fid=1, correct=1), _row(5, fid=1, correct=0),
            _row(10, fid=2, correct=1)]
    picked = group_quiz_round(rows)
    check("★ 同一个函数只留一条", len(picked) == 2,
          [r["function_id"] for r in picked])
    hit = [r for r in picked if r["function_id"] == 1][0]
    check("留的是最近那条（第一次的作答）", int(hit["is_correct"]) == 1, hit)

    # 错题优先
    rows = [_row(0, fid=1, correct=1), _row(5, fid=2, correct=0),
            _row(10, fid=3, correct=1), _row(15, fid=4, correct=0)]
    picked = group_quiz_round(rows)
    flags = [int(r["is_correct"]) for r in picked]
    check("★ 答错的排在前面", flags == [0, 0, 1, 1], flags)
    check("错题组内部保持时间序（倒序）",
          [r["function_id"] for r in picked] == [2, 4, 1, 3],
          [r["function_id"] for r in picked])

    # 时间戳坏掉 → 不切（宁可多带，不可少带）
    rows = [{"function_id": 1, "is_correct": 1, "created_at": "坏掉的时间"},
            _row(600, fid=2, correct=0)]
    check("时间戳解析不出来时不切轮",
          len(group_quiz_round(rows)) == 2,
          len(group_quiz_round(rows)))
    rows = [_row(0, fid=1, correct=1), {"function_id": 2, "is_correct": 0,
                                        "created_at": ""}]
    check("时间戳为空也不切轮", len(group_quiz_round(rows)) == 2)


# ══════════════════════════════════════════════════════════════════════════
# H. 懒创建防线（recent_quiz_answers 的 LEFT JOIN）
# ══════════════════════════════════════════════════════════════════════════
def test_recent_answers_join() -> None:
    section("[H] recent_quiz_answers：新学的函数不许被滤掉")
    db = fresh_excel()

    funcs = db.list_functions()[:2]
    fresh_id = int(funcs[0]["id"])
    other_id = int(funcs[1]["id"])

    # fresh_id：只作答、**不标掌握度**（进度行懒创建，此时一行都没有）
    db.record_quiz_result(function_id=fresh_id, quiz_type=QUIZ_CHOICE,
                          prompt="?", answer="A", user_answer="B",
                          is_correct=False, category="", feed_progress=False)
    progress_rows = db.conn.execute(
        "SELECT COUNT(*) AS n FROM excel_progress").fetchone()["n"]
    check("前置：这条函数确实没有进度行", progress_rows == 0, progress_rows)

    rows = db.recent_quiz_answers()
    ids = [int(r["function_id"]) for r in rows]
    check("★ 没标过掌握度的函数照样被捞出来", fresh_id in ids, ids)
    hit = [r for r in rows if int(r["function_id"]) == fresh_id][0]
    check("捞出来的行带着函数码", bool(hit.get("code")), hit)
    check("捞出来的行带着函数正文（名 / 语法 / 说明）",
          bool(hit.get("name_cn")) and bool(hit.get("syntax")),
          {k: hit.get(k) for k in ("code", "name_cn", "syntax")})
    check("掌握度为空也不报错", hit.get("mastery") in (None, ""), hit.get("mastery"))

    # 函数被删过：流水还在，code 为空（页面的 _classify 会跳过它）
    db.record_quiz_result(function_id=other_id, quiz_type=QUIZ_CHOICE,
                          prompt="?", answer="A", user_answer="A",
                          is_correct=True, category="", feed_progress=False)
    rows2 = db.recent_quiz_answers()
    check("两条流水都在", len(rows2) == 2, len(rows2))
    check("流水是倒序（最新那条在最前）",
          int(rows2[0]["function_id"]) == other_id, rows2[0]["function_id"])

    # 直接把函数行删掉（模拟「删过见过这个函数的库」）
    db.conn.execute("DELETE FROM excel_functions WHERE id = ?", (fresh_id,))
    db.conn.commit()
    rows3 = db.recent_quiz_answers()
    orphan = [r for r in rows3 if int(r["function_id"]) == fresh_id]
    check("★ 函数删了流水还在（LEFT JOIN 而不是 INNER JOIN）", bool(orphan),
          [r["function_id"] for r in rows3])
    check("孤儿流水的 code 为空（页面据此跳过）",
          orphan and not str(orphan[0].get("code") or "").strip(),
          orphan[0].get("code") if orphan else None)

    # 端到端：孤儿被跳过，活着的那个整理成笔记
    bridge = ExcelNoteBridge(fresh_notes("n2.db"))
    items = group_quiz_round(rows3)
    check("切轮后孤儿也在（切轮不管孤儿）", len(items) == 2, len(items))
    result = bridge.sync_notes(items, generated_at="2026-09-24 10:29")
    check("★ 只有活着的那个生成笔记", result["created"] == 1, result)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# I. 待办 ⇄ 笔记 的反向那一半
# ══════════════════════════════════════════════════════════════════════════
def test_todo_hint() -> None:
    section("[I] 待办备注里的笔记指纹（反向关联）")
    base = review_todo_payload(due_count=3, today="2026-09-24", extra_wrong=2)
    check("不传 note_hint 时备注里没有「笔记：」",
          "笔记：" not in base["notes"], base["notes"])
    check("基础备注仍然会说去哪打开",
          "Excel 宝典" in base["notes"], base["notes"])

    hint = f"笔记：{NOTE_AREA_LABEL}（已生成 5 篇）"
    with_hint = review_todo_payload(due_count=3, today="2026-09-24",
                                    extra_wrong=2, note_hint=hint)
    check("★ 传了就写进备注", hint in with_hint["notes"], with_hint["notes"])
    check("笔记那行排在「打开」之前（先看见落点）",
          with_hint["notes"].index(hint) < with_hint["notes"].index("打开："),
          with_hint["notes"])
    check("传空串等于没传",
          "笔记：" not in review_todo_payload(due_count=1, today="2026-09-24",
                                             note_hint="")["notes"])
    check("只传空白也等于没传",
          "笔记：" not in review_todo_payload(due_count=1, today="2026-09-24",
                                             note_hint="   ")["notes"])
    check("标题不受影响（due_count 该出现就出现）",
          "3" in with_hint["title"], with_hint["title"])


# ══════════════════════════════════════════════════════════════════════════
def main_test() -> None:
    test_markers()
    test_template_fields()
    test_locked_category()
    test_bridge_readonly()
    test_find_note()
    test_second_edit_survives()
    test_group_round()
    test_recent_answers_join()
    test_todo_hint()


if __name__ == "__main__":
    try:
        main_test()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILED += 1
    finally:
        cleanup()

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
