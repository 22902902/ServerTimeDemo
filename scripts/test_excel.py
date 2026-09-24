# -*- coding: utf-8 -*-
"""Excel 学习中心回归测试（数据层 + 种子校验，纯逻辑、不碰 Tk）。

为什么单独成篇
------------------------------------------------------------------------------
这个模块有一半的价值在「算得对」，而这几处算错了界面上**看不出来**：

* **待复习队列是 LEFT JOIN 还是 INNER JOIN**：进度行是懒创建的，全库刚装好时
  ``excel_progress`` 一行都没有。写成 INNER JOIN，首日「今日复习」就是空的 ——
  页面不报错、日志不报错，只是什么都不推。这是本模块最容易回归的一处。
* **种子的幂等性与「不覆盖用户数据」**：种子每次启动都会走一遍 ``INSERT OR IGNORE``。
  一旦有人把 ``ON CONFLICT`` 改成 UPDATE，用户手填的书页码、自己写的心得、
  辛苦标出来的掌握度就会被种子整片刷掉，而且**只在他下次启动时发生**。
* **间隔重复的三键**：熟练 / 模糊 / 忘了 各自对掌握度、连对次数、间隔的改动方向
  不同。间隔数组是 1/3/7/15/30/60/120 七档，连对次数当作索引，越界必须夹住。
* **连续打卡的「今天没打卡不清零」**：从今天往回数，今天没打卡就从昨天数起。
  写成「今天没打卡就是 0」的话，每天零点一过连续天数归零，用户会以为坏了。
* **related 交叉引用**：200 个函数的 ``related`` 里写的每个函数名都要能在库里
  找到 —— 否则详情页会画出一批点不动的灰胶囊，等于残次品。

另一类被锁死的是「有意设计」：
* 内置函数**不许删**（``delete_function`` 对 builtin 返回 False），自定义的可以删
* ``**强调**`` 标记留在种子文本里（导出 Markdown 要用）；上屏、出题前统一由 ``strip_emphasis`` 剥掉
* 八个视图 + 三栏布局是页面层的取舍，数据层不掺和

覆盖
------------------------------------------------------------------------------
A. 种子一致性    200 个函数 / 12 分类 / 7 阶段 / 20 配方 / code 唯一 / related 全部可解
B. 种子 schema   必填字段齐全、难度与重要度在值域内、可选字段有默认
C. 建表与迁移    新库一次到位 / 幂等 / 老库补列不丢数据
D. 种子幂等      重跑不翻倍 / 不覆盖 book_page、my_note、mastery
E. 纯函数        parse_date / shift_date / interval_for / review_next_state /
                 match_keyword / compute_streak / longest_streak / split_codes
F. 待复习队列    未学也算待复习 / 与 due_count 一致 / 复习后递减 / 到期的排在新的前面
G. 掌握度        set_mastery 夹取与排期 / 手动标记立刻进队列
H. 复习状态机    record_review 三键推进 / 非法反馈报错
I. 检索          关键词 / 分类 / 掌握度 / 组合 / 空词
J. 笔记 CRUD     增改查删 / 计数 / 按函数筛选 / 关键词命中
K. 打卡          upsert 只改传入字段 / 连续天数 / 最长 / 累计 / 最近 7 天补零
L. 统计与导出    掌握度总览 / 分类统计 / 路径进度 / 配方 CRUD
M. 自测出题      剥强调 / 切场景 / 函数名打码（IF 不许误伤 IFERROR）/ 四选一不泄露选项 / 同种子同套题 / 优先挑不熟的
N. 自测作答      答对答错都回灌同一条遗忘曲线 / 错题本按函数去重 / 订正后消失 / 删函数不留孤儿 / 只出错题本模式
O. 批量导入解析  模板往返 / 中英文列头别名 / 三种分隔符 / GBK 回退 / 幂等归一化 / 必填与格式校验
P. 批量导入写库  dry_run 不落盘 / 新增入自建 / 内置默认跳过 / 覆盖只写非空列（书页码与心得保住）/ 导出再导入是更新
Q. 待办联动桥    只在点击时建 / 周六不被顺延（对照证明 skip_holidays 必要）/ 当天幂等 / 缺字段不建

用法：
    python scripts/test_excel.py
"""

import random
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from excel_db import (  # noqa: E402
    FEEDBACK_CHOICES,
    FEEDBACK_FORGOT,
    FEEDBACK_KNOWN,
    FEEDBACK_VAGUE,
    MASTERY_COLORS,
    MASTERY_FAIR,
    MASTERY_GOOD,
    MASTERY_LABELS,
    MASTERY_NEW,
    MASTERY_WEAK,
    SRS_INTERVALS,
    ExcelDB,
    category_stats,
    compute_streak,
    difficulty_label,
    ensure_columns,
    function_search_blob,
    importance_label,
    init_excel_tables,
    interval_for,
    longest_streak,
    match_keyword,
    mastery_color,
    mastery_label,
    parse_date,
    path_progress,
    review_next_state,
    seed_excel_data,
    shift_date,
    split_codes,
    today_str,
    IMPORT_COLUMNS,
    QUIZ_CHOICE,
    QUIZ_FORMULA,
    QUIZ_OPTION_COUNT,
    build_choice_question,
    build_formula_question,
    build_quiz_questions,
    import_template_csv,
    import_template_headers,
    import_template_rows,
    mask_code,
    normalize_import_header,
    normalize_import_row,
    normalize_import_value,
    parse_import_csv_text,
    parse_import_file,
    quiz_prompt,
    read_import_text,
    scenario_sentences,
    strip_emphasis,
    validate_import_row,
)
from excel_todo_bridge import ExcelTodoBridge, review_todo_payload  # noqa: E402
from todo_db import TodoDB  # noqa: E402
from excel_seed import (  # noqa: E402
    CATEGORIES,
    LEARNING_PATHS,
    SEED_FUNCTIONS,
    SEED_RECIPES,
)

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


def fresh(name: str) -> ExcelDB:
    """每个小节一个独立空库：这些用例大量依赖「初始状态」，共用会互相污染。"""
    d = Path(tempfile.mkdtemp(prefix="excel_test_"))
    _TMP.append(d)
    return ExcelDB(d / f"{name}.db", seed=True)


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# A. 种子一致性
# ══════════════════════════════════════════════════════════════════════════
def test_seed_consistency() -> None:
    section("[A] 种子一致性")
    check("内置函数 200 条", len(SEED_FUNCTIONS) == 200, len(SEED_FUNCTIONS))
    check("官方分类 12 个", len(CATEGORIES) == 12, len(CATEGORIES))
    check("学习路径 7 个阶段", len(LEARNING_PATHS) == 7, len(LEARNING_PATHS))
    check("实战配方 20 条", len(SEED_RECIPES) == 20, len(SEED_RECIPES))

    codes = [f["code"] for f in SEED_FUNCTIONS]
    check("code 无重复", len(set(codes)) == len(codes),
          f"{len(codes) - len(set(codes))} 个重复")

    cat_names = {c["name"] for c in CATEGORIES}
    unknown = sorted({f["category"] for f in SEED_FUNCTIONS} - cat_names)
    check("每个函数的分类都在 12 类里", not unknown, unknown)
    used = {f["category"] for f in SEED_FUNCTIONS}
    empty = sorted(cat_names - used)
    check("没有空分类（12 类都被用到）", not empty, empty)

    # related 交叉引用必须全部能解析，否则详情页会画出一批点不动的灰胶囊
    code_set = set(codes)
    broken = []
    for f in SEED_FUNCTIONS:
        for token in split_codes(f.get("related")):
            if token.upper() not in {c.upper() for c in code_set}:
                broken.append((f["code"], token))
    check("related 全部指向库内函数", not broken, broken[:8])

    broken_recipe = []
    for r in SEED_RECIPES:
        for token in split_codes(r.get("related")):
            if token.upper() not in {c.upper() for c in code_set}:
                broken_recipe.append((r.get("title"), token))
    check("配方的 related 也全部可解析", not broken_recipe, broken_recipe[:8])

    # 阶段里点名的函数也得存在
    missing_stage = []
    for stage in LEARNING_PATHS:
        for code in stage.get("codes") or []:
            if code.upper() not in {c.upper() for c in code_set}:
                missing_stage.append((stage.get("key"), code))
    check("学习路径点名的函数都存在", not missing_stage, missing_stage[:8])

    recipe_cats = {r["category"] for r in SEED_RECIPES}
    check("配方的分类也在 12 类里", recipe_cats <= cat_names,
          sorted(recipe_cats - cat_names))


# ══════════════════════════════════════════════════════════════════════════
# B. 种子 schema
# ══════════════════════════════════════════════════════════════════════════
def test_seed_schema() -> None:
    section("[B] 种子字段规范")
    need = ("code", "name_cn", "category", "syntax", "args_desc", "description")
    empty_field = []
    for f in SEED_FUNCTIONS:
        for key in need:
            if not str(f.get(key) or "").strip():
                empty_field.append((f["code"], key))
    check("必填字段都非空", not empty_field, empty_field[:8])

    bad_diff = [f["code"] for f in SEED_FUNCTIONS
                if int(f.get("difficulty", 0) or 0) not in (1, 2, 3, 4)]
    check("难度都在 1~4", not bad_diff, bad_diff[:8])
    bad_imp = [f["code"] for f in SEED_FUNCTIONS
               if int(f.get("importance", 0) or 0) not in (1, 2, 3)]
    check("重要度都在 1~3", not bad_imp, bad_imp[:8])

    # 可选字段必须有默认值，否则界面上会 KeyError。
    # book_page / my_note 不在这里 —— 它们是**表列**（建表时带 DEFAULT ''），
    # 由落库负责，不在种子字典里；[M] 小节按数据库返回的行来验。
    defaults = ("returns", "pitfalls", "use_cases", "related", "example_formula",
                "example_result", "min_version", "tags")
    missing_key = []
    for f in SEED_FUNCTIONS:
        for key in defaults:
            if key not in f:
                missing_key.append((f["code"], key))
    check("可选字段都有默认键", not missing_key, missing_key[:8])

    # **强调** 标记是给导出 Markdown 用的，界面层负责去掉；种子层不许先删
    with_marks = sum(1 for f in SEED_FUNCTIONS if "**" in str(f.get("pitfalls")))
    check("种子里保留 **强调** 标记（导出要用）", with_marks > 0, f"{with_marks} 条")


# ══════════════════════════════════════════════════════════════════════════
# C. 建表与迁移
# ══════════════════════════════════════════════════════════════════════════
def test_schema() -> None:
    section("[C] 建表与迁移（新库 / 幂等 / 老库补列）")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_excel_tables(conn)
    tables = {r[0] for r in conn.execute(
        "select name from sqlite_master where type='table'")}
    want = {"excel_functions", "excel_progress", "excel_recipes", "excel_notes",
            "excel_checkins"}
    check("新库五张表一次到位", want <= tables, sorted(want - tables))

    cols = {r[1] for r in conn.execute("PRAGMA table_info(excel_functions)")}
    check("函数表有 book_page / my_note",
          {"book_page", "my_note"} <= cols, sorted({"book_page", "my_note"} - cols))
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(excel_progress)")}
    check("进度表有 interval_days / next_review_at",
          {"interval_days", "next_review_at"} <= pcols,
          sorted({"interval_days", "next_review_at"} - pcols))

    # 幂等：再建一次不报错
    try:
        init_excel_tables(conn)
        check("重复 init 不报错（幂等）", True)
    except sqlite3.Error as exc:
        check("重复 init 不报错（幂等）", False, repr(exc))

    # 老库补列：先建一张缺列的表，再走 ensure_columns，数据不能丢
    old = sqlite3.connect(":memory:")
    old.row_factory = sqlite3.Row
    old.execute("CREATE TABLE excel_functions (id INTEGER PRIMARY KEY, code TEXT)")
    old.execute("INSERT INTO excel_functions (code) VALUES ('LEGACY')")
    added = ensure_columns(old, "excel_functions",
                           {"book_page": "TEXT DEFAULT ''",
                            "my_note": "TEXT DEFAULT ''"})
    cols2 = {r[1] for r in old.execute("PRAGMA table_info(excel_functions)")}
    check("老库补列成功", {"book_page", "my_note"} <= cols2, added)
    check("补列后旧数据还在",
          old.execute("select code from excel_functions").fetchone()[0] == "LEGACY")
    check("补列是幂等的（第二次返回空）",
          ensure_columns(old, "excel_functions",
                         {"book_page": "TEXT DEFAULT ''"}) == [])
    old.close()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════
# D. 种子幂等与「不覆盖用户数据」
# ══════════════════════════════════════════════════════════════════════════
def test_seed_idempotent() -> None:
    section("[D] 种子幂等 / 不覆盖用户数据")
    db = fresh("seed")
    check("落库 200 条", db.count_functions() == 200, db.count_functions())

    first = db.get_function_by_code("VLOOKUP")
    db.update_function_fields(first["id"], book_page="P215",
                              my_note="我自己的理解：第四参数写 FALSE")
    db.set_mastery(first["id"], MASTERY_GOOD)

    counts = seed_excel_data(db.conn)
    check("重跑种子函数数不翻倍", db.count_functions() == 200, db.count_functions())
    check("重跑种子返回统计", counts["functions"] == 200 and counts["recipes"] == 20,
          counts)

    again = db.get_function_by_code("VLOOKUP")
    check("书页码没被种子刷掉", again["book_page"] == "P215", again["book_page"])
    check("我的理解没被种子刷掉", "第四参数" in again["my_note"], again["my_note"])
    state = db.progress_map().get(first["id"]) or {}
    check("掌握度没被种子刷掉", int(state.get("mastery", 0)) == MASTERY_GOOD, state)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# E. 纯函数
# ══════════════════════════════════════════════════════════════════════════
def test_pure_helpers() -> None:
    section("[E] 纯函数")

    # parse_date 认多种写法，认不出来返回 None（不是抛异常）
    check("parse_date 认 ISO 串", parse_date("2026-09-23") == date(2026, 9, 23))
    check("parse_date 认斜杠写法", parse_date("2026/09/23") == date(2026, 9, 23))
    check("parse_date 认中文写法", parse_date("2026年9月23日") == date(2026, 9, 23))
    check("parse_date 认 date 对象", parse_date(date(2026, 9, 23)) == date(2026, 9, 23))
    check("parse_date 认 datetime 对象", parse_date(
        __import__("datetime").datetime(2026, 9, 23, 8, 0)) == date(2026, 9, 23))
    check("parse_date 空值返回 None", parse_date("") is None)
    check("parse_date 垃圾串返回 None", parse_date("不是日期") is None)
    check("parse_date 不因为 '2026-09-23 08:00' 报错",
          parse_date("2026-09-23 08:00") == date(2026, 9, 23))

    check("shift_date 往后推", shift_date("2026-09-23", 3) == "2026-09-26")
    check("shift_date 往前推", shift_date("2026-09-23", -23) == "2026-08-31")
    check("shift_date 跨月跨年", shift_date("2026-12-31", 1) == "2027-01-01")
    check("shift_date 空值按今天算", shift_date("", 0) == today_str())

    check("interval_for 第一档 1 天", interval_for(1) == SRS_INTERVALS[0])
    check("interval_for 跟着连对往上跳", interval_for(3) == SRS_INTERVALS[2])
    check("interval_for 下界夹住（streak=0）", interval_for(0) == SRS_INTERVALS[0])
    check("interval_for 上界夹住（streak=99）", interval_for(99) == SRS_INTERVALS[-1])

    # 三键的方向必须完全不同
    s = review_next_state(MASTERY_NEW, 0, 0, FEEDBACK_KNOWN)
    check("熟练：掌握度 +1 / 连对 +1 / 间隔第 1 档",
          s["mastery"] == 1 and s["correct_streak"] == 1 and s["interval_days"] == 1, s)
    s2 = review_next_state(s["mastery"], s["correct_streak"], s["interval_days"],
                           FEEDBACK_KNOWN)
    check("再熟练：连对 2 → 间隔升到 3 天", s2["interval_days"] == 3, s2)
    s3 = review_next_state(MASTERY_GOOD, 3, 7, FEEDBACK_VAGUE)
    check("模糊：连对 -1 / 间隔砍半 / 掌握度不倒退",
          s3["correct_streak"] == 2 and s3["interval_days"] == 3
          and s3["mastery"] == MASTERY_GOOD, s3)
    s4 = review_next_state(MASTERY_NEW, 0, 0, FEEDBACK_VAGUE)
    check("未学碰模糊 → 至少落个「生疏」", s4["mastery"] == MASTERY_WEAK, s4)
    s5 = review_next_state(MASTERY_FAIR, 4, 15, FEEDBACK_FORGOT)
    check("忘了：掌握度 -1 / 连对归零 / 间隔回 1 天",
          s5["mastery"] == MASTERY_WEAK and s5["correct_streak"] == 0
          and s5["interval_days"] == 1, s5)
    s6 = review_next_state(MASTERY_GOOD, 7, 120, FEEDBACK_KNOWN)
    check("熟练到顶：掌握度不超 3", s6["mastery"] == MASTERY_GOOD, s6)
    check("间隔砍半最低 1 天",
          review_next_state(1, 0, 1, FEEDBACK_VAGUE)["interval_days"] == 1)

    # 反馈三键是穷举的
    check("反馈只有三键", len(FEEDBACK_CHOICES) == 3, FEEDBACK_CHOICES)
    check("掌握度四档", len(MASTERY_LABELS) == 4, sorted(MASTERY_LABELS))

    check("match_keyword 空白词恒真", match_keyword("随便什么", ""))
    check("match_keyword 多词全中才算中",
          match_keyword("vlookup 反向查找 两张表", "反向 两张"))
    check("match_keyword 少一个词就不中",
          not match_keyword("vlookup 反向查找", "反向 透视表"))
    check("match_keyword 大小写不敏感", match_keyword("VLOOKUP".lower(), "vlookup"))

    check("掌握度标签取值", mastery_label(MASTERY_GOOD) == "熟练"
          and mastery_label(None) == "未学")
    check("掌握度颜色有兜底",
          mastery_color(99) == MASTERY_COLORS[MASTERY_NEW], mastery_color(99))
    check("难度标签兜底", difficulty_label(None) == "常用"
          and difficulty_label(1) == "入门")
    check("重要度标签兜底", importance_label(None) == "常用"
          and importance_label(3) == "核心")

    blob = function_search_blob({"code": "VLOOKUP", "use_cases": "两张表按主键对齐"})
    check("检索面覆盖 use_cases", "主键对齐" in blob, blob[:60])
    check("检索面是小写", blob == blob.lower())

    # 连续打卡：核心是「今天没打卡不清零」
    today = date(2026, 9, 23)
    days = [(today - timedelta(days=i)).isoformat() for i in range(3)]
    check("连打 3 天（含今天）= 3", compute_streak(days, today) == 3, days)
    check("今天没打、昨天前天打了 → 仍算 2（不清零）",
          compute_streak(days[1:], today) == 2, days[1:])
    check("断了两天 → 0",
          compute_streak([(today - timedelta(days=3)).isoformat()], today) == 0)
    check("空列表 → 0", compute_streak([], today) == 0)
    check("满是空串也不炸", compute_streak(["", "", None], today) == 0)

    span = [(today - timedelta(days=i)).isoformat() for i in (0, 1, 2, 7, 8, 9, 10)]
    check("最长连续天数按最长的段算", longest_streak(span) == 4, longest_streak(span))
    check("最长连续天数空表 → 0", longest_streak([]) == 0)

    # split_codes：内置种子只用 |，但要容忍用户手打的逗号 / 顿号 / 分号
    check("split_codes 认 |", split_codes("IFS|SWITCH|AND") == ["IFS", "SWITCH", "AND"])
    check("split_codes 认中文顿号与逗号",
          split_codes("IFS、SWITCH, AND") == ["IFS", "SWITCH", "AND"])
    check("split_codes 去重", split_codes("IF|IF|and") == ["IF", "and"])
    check("split_codes 空值 → 空表",
          split_codes(None) == [] and split_codes("") == []
          and split_codes(" | , ") == [])


# ══════════════════════════════════════════════════════════════════════════
# F. 待复习队列（本模块最易回归的一处）
# ══════════════════════════════════════════════════════════════════════════
def test_due_queue() -> None:
    section("[F] 待复习队列（未学也要推）")
    db = fresh("due")
    today = today_str()

    # 核心断言：刚装好、一行进度都没有，队列必须是满的
    check("进度表初始为空",
          db.conn.execute("select count(*) from excel_progress").fetchone()[0] == 0)
    check("未学也算待复习（不是 0）", db.due_count(today=today) == 200,
          db.due_count(today=today))
    due = db.due_functions(limit=5, today=today)
    check("due_functions 能取到 5 条", len(due) == 5, len(due))
    check("取出来的都带 due=True", all(item.get("due") for item in due))
    check("取出来的都带 mastery 字段",
          all("mastery" in item for item in due))

    # 复习一个 → 队列减一，且这个函数不再出现
    target = due[0]
    db.record_review(target["id"], FEEDBACK_KNOWN, today=today)
    check("复习一个后队列 -1", db.due_count(today=today) == 199,
          db.due_count(today=today))
    still = [item["id"] for item in db.due_functions(today=today)]
    check("刚复习过的不再出现在队列里", target["id"] not in still)

    # 排序：已经把复习排期排到今天的，要排在从没学过的前面
    scheduled_id = db.get_function_by_code("SORT")["id"]
    db.set_mastery(scheduled_id, MASTERY_FAIR, today=today)
    top = db.due_functions(limit=3, today=today)
    check("已排期到期的排在没学过的前面",
          top[0]["id"] == scheduled_id and top[0]["next_review_at"] == today,
          [(x["id"], x["code"], x["next_review_at"]) for x in top])
    check("后面的仍是没排期的待学项",
          all(not x["next_review_at"] for x in top[1:]),
          [(x["code"], x["next_review_at"]) for x in top[1:]])

    # 到期日推后一天，就不再是今天该复习的
    db.conn.execute("UPDATE excel_progress SET next_review_at = ? WHERE function_id = ?",
                    (shift_date(today, 1), scheduled_id))
    db.conn.commit()
    ids = [item["id"] for item in db.due_functions(today=today)]
    check("排到明天的不在今天队列里", scheduled_id not in ids)
    check("明天到期 → 明天进队列",
          scheduled_id in [item["id"] for item in db.due_functions(
              today=shift_date(today, 1))])

    # limit 只截取，不改总数
    expect_due = db.due_count(today=today)
    check("limit 不改变 due_count",
          len(db.due_functions(limit=1, today=today)) == 1
          and db.due_count(today=today) == expect_due,
          f"{expect_due} vs {db.due_count(today=today)}")
    check("limit=0 返回空表", db.due_functions(limit=0, today=today) == [])
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# G. 掌握度
# ══════════════════════════════════════════════════════════════════════════
def test_mastery() -> None:
    section("[G] 掌握度")
    db = fresh("mastery")
    today = today_str()
    fid = db.get_function_by_code("SUM")["id"]

    db.set_mastery(fid, MASTERY_GOOD, today=today)
    state = db.progress_map()[fid]
    check("设成熟练可读回", int(state["mastery"]) == MASTERY_GOOD, state)
    check("手动标记立刻排进今天", state["next_review_at"] == today, state)

    db.set_mastery(fid, 99, today=today)
    check("超上界夹到 3", int(db.progress_map()[fid]["mastery"]) == MASTERY_GOOD)
    db.set_mastery(fid, -5, today=today)
    check("超下界夹到 0", int(db.progress_map()[fid]["mastery"]) == MASTERY_NEW)

    # 设成「未学」不该被排期，也不该丢掉已有排期
    fid2 = db.get_function_by_code("AVERAGE")["id"]
    db.set_mastery(fid2, MASTERY_WEAK, today=today)
    scheduled = db.progress_map()[fid2]["next_review_at"]
    db.set_mastery(fid2, MASTERY_NEW, today=today)
    check("设成未学不清掉已有排期",
          db.progress_map()[fid2]["next_review_at"] == scheduled, scheduled)

    check("progress_map 只含进过表的函数",
          len(db.progress_map()) == 2, len(db.progress_map()))
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# H. 复习状态机落库
# ══════════════════════════════════════════════════════════════════════════
def test_record_review() -> None:
    section("[H] 复习状态机落库")
    db = fresh("review")
    today = today_str()
    fid = db.get_function_by_code("XLOOKUP")["id"]

    r1 = db.record_review(fid, FEEDBACK_KNOWN, today=today)
    check("返回新状态", r1["next_review_at"] == shift_date(today, 1)
          and r1["correct_streak"] == 1, r1)
    check("review_count 累计",
          int(db.conn.execute("select review_count from excel_progress "
                              "where function_id = ?", (fid,)).fetchone()[0]) == 1)
    check("last_review_at 记的是时间戳（不是纯日期）",
          "T" in (db.conn.execute("select last_review_at from excel_progress "
                                  "where function_id = ?", (fid,)).fetchone()[0] or ""),
          db.conn.execute("select last_review_at from excel_progress "
                          "where function_id = ?", (fid,)).fetchone()[0])

    db.record_review(fid, FEEDBACK_KNOWN, today=today)
    db.record_review(fid, FEEDBACK_KNOWN, today=today)
    row = db.conn.execute("select interval_days, correct_streak, next_review_at "
                          "from excel_progress where function_id = ?",
                          (fid,)).fetchone()
    check("连对 3 次 → 间隔 7 天", int(row["interval_days"]) == 7, dict(row))
    check("next_review_at 落在 7 天后",
          row["next_review_at"] == shift_date(today, 7), row["next_review_at"])

    db.record_review(fid, FEEDBACK_FORGOT, today=today)
    row2 = db.conn.execute("select interval_days, correct_streak, next_review_at "
                           "from excel_progress where function_id = ?",
                           (fid,)).fetchone()
    check("忘了 → 间隔 1 天、连对归零",
          int(row2["interval_days"]) == 1 and int(row2["correct_streak"]) == 0,
          dict(row2))

    try:
        db.record_review(fid, "不存在的反馈")
        check("非法反馈要报错", False, "没报错")
    except ValueError:
        check("非法反馈要报错", True)

    check("复习不会重复建进度行",
          db.conn.execute("select count(*) from excel_progress").fetchone()[0] == 1)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# I. 检索
# ══════════════════════════════════════════════════════════════════════════
def test_search() -> None:
    section("[I] 检索")
    db = fresh("search")
    all_rows = db.list_functions()
    check("不带条件返回全量", len(all_rows) == 200, len(all_rows))
    check("返回项带 mastery 与 due",
          "mastery" in all_rows[0] and "due" in all_rows[0])

    hits = db.list_functions(keyword="反向查找")
    check("按中文场景词能命中", len(hits) > 0, len(hits))
    check("命中的确有反向查找相关函数",
          any(item["code"] in ("VLOOKUP", "INDEX", "XLOOKUP", "MATCH", "LOOKUP")
              for item in hits), [x["code"] for x in hits][:8])

    cat = db.list_functions(category="查找与引用")
    check("按分类筛选非空", len(cat) > 0, len(cat))
    check("按分类筛选全属该分类",
          all(item["category"] == "查找与引用" for item in cat))

    combo = db.list_functions(category="查找与引用", keyword="VLOOKUP")
    check("分类 + 关键词是交集", 0 < len(combo) < len(cat),
          f"{len(combo)} < {len(cat)}")

    db.set_mastery(db.get_function_by_code("XLOOKUP")["id"], MASTERY_GOOD)
    good = db.list_functions(mastery=MASTERY_GOOD)
    check("按掌握度筛出 1 条", len(good) == 1 and good[0]["code"] == "XLOOKUP",
          [x["code"] for x in good])
    new_only = db.list_functions(mastery=MASTERY_NEW)
    check("按未学筛出 199 条", len(new_only) == 199, len(new_only))

    check("空关键词等于不过滤",
          len(db.list_functions(keyword="   ")) == 200)
    check("匹配不到的词返回空表",
          db.list_functions(keyword="这个词肯定没有xyzzy") == [])
    check("limit 生效", len(db.list_functions(limit=7)) == 7)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# J. 笔记 CRUD
# ══════════════════════════════════════════════════════════════════════════
def test_notes() -> None:
    section("[J] 笔记 CRUD")
    db = fresh("notes")
    fid = db.get_function_by_code("INDEX")["id"]

    nid = db.save_note(title="INDEX 的行列参数", book_page="P301",
                       content="第一个参数是区域，后面跟着行号、列号。",
                       function_id=fid, tags="查找,引用")
    check("新增返回 id", bool(nid), nid)
    note = db.get_note(nid)
    check("字段落库正确",
          note["title"] == "INDEX 的行列参数" and note["book_page"] == "P301"
          and int(note["function_id"]) == fid, dict(note))
    check("计数 +1", db.note_count() == 1, db.note_count())

    db.save_note(note_id=nid, title="改过标题", book_page="P302",
                 content="改了", function_id=fid, tags="引用")
    note2 = db.get_note(nid)
    check("编辑生效且 id 不变",
          note2["title"] == "改过标题" and note2["book_page"] == "P302"
          and int(note2["id"]) == nid, dict(note2))

    nid2 = db.save_note(title="不挂函数的随手记", content="随便记点")
    check("可以不挂函数（function_id 空）",
          not (db.get_note(nid2) or {}).get("function_id"))
    check("计数 2", db.note_count() == 2, db.note_count())

    check("按函数筛选", len(db.list_notes(function_id=fid)) == 1)
    check("按关键词命中标题", len(db.list_notes(keyword="改过标题")) == 1)
    check("按关键词命中正文", len(db.list_notes(keyword="随便记点")) == 1)
    check("按关键词命中标签", len(db.list_notes(keyword="引用")) == 1)
    check("关键词多词要全中", len(db.list_notes(keyword="改过 找不到")) == 0)

    check("删除返回 True", db.delete_note(nid2) is True)
    check("删完计数 -1", db.note_count() == 1, db.note_count())
    check("删不存在的返回 False", db.delete_note(99999) is False)
    check("删掉的查不到", db.get_note(nid2) is None)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# K. 打卡
# ══════════════════════════════════════════════════════════════════════════
def test_checkins() -> None:
    section("[K] 打卡")
    db = fresh("checkin")
    today = date(2026, 9, 23)
    today_s = today.isoformat()
    d1 = (today - timedelta(days=1)).isoformat()
    d2 = (today - timedelta(days=2)).isoformat()

    db.upsert_checkin(check_date=today_s, minutes=20, reviewed=12, learned=3)
    db.upsert_checkin(check_date=d1, minutes=30, reviewed=15, learned=4)
    db.upsert_checkin(check_date=d2, minutes=10, reviewed=8, learned=2)
    check("连打 3 天 = 3", db.streak(today=today_s) == 3, db.streak(today=today_s))
    check("最长连续 3", db.longest_streak() == 3, db.longest_streak())

    # upsert 只改传进来的字段：下一次只记 review 数，分钟数不能被清零
    db.upsert_checkin(check_date=today_s, reviewed=20)
    row = db.get_checkin(today_s)
    check("upsert 不清空没传的字段",
          int(row["minutes"]) == 20 and int(row["reviewed"]) == 20, dict(row))

    check("get_checkin 取不到返回 None", db.get_checkin("1999-01-01") is None)
    check("checkin_dates 返回 3 天", len(db.checkin_dates()) == 3,
          len(db.checkin_dates()))

    totals = db.totals()
    check("累计天数 3", totals["days"] == 3, totals)
    check("累计分钟 = 20+30+10", totals["minutes"] == 60, totals)
    check("累计复习 = 20+15+8", totals["reviewed"] == 43, totals)

    # 今天没打卡 → 连续天数从昨天数起，不清零
    check("今天没打卡不清零（从昨天数）", db.streak(today="2026-09-24") == 3,
          db.streak(today="2026-09-24"))
    check("隔一天没打 → 从今天往前断掉",
          db.streak(today="2026-09-26") == 0, db.streak(today="2026-09-26"))

    recent = db.recent_activity(days=7, today=today_s)
    check("最近 7 天补零成 7 条", len(recent) == 7, len(recent))
    check("最后一条是今天且带数据",
          recent[-1]["date"] == today_s and int(recent[-1]["reviewed"]) == 20,
          recent[-1])
    check("没打卡的日子值为 0",
          all(int(item["reviewed"] or 0) == 0
              for item in recent if item["date"] not in (today_s, d1, d2)),
          [(x["date"], x["reviewed"]) for x in recent])
    check("checked 标记当天有没有打卡",
          sum(1 for item in recent if item["checked"]) == 3,
          [(x["date"], x["checked"]) for x in recent])

    # 「今天是哪天」不传时按系统日期算，不该炸
    check("streak 不传 today 也能算", isinstance(db.streak(), int))
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# L. 统计 / 路径 / 配方
# ══════════════════════════════════════════════════════════════════════════
def test_stats_and_recipes() -> None:
    section("[L] 统计 / 路径 / 配方")
    db = fresh("stats")

    ov = db.mastery_overview()
    check("总览总数 200", ov["total"] == 200, ov)
    check("未学时已学 = 0", ov["learned"] == 0 and ov["good"] == 0, ov)
    check("四档桶都在且加起来等于总数",
          sum(ov["buckets"].values()) == 200 and len(ov["buckets"]) == 4, ov["buckets"])

    db.set_mastery(db.get_function_by_code("IF")["id"], MASTERY_GOOD)
    db.set_mastery(db.get_function_by_code("SUM")["id"], MASTERY_FAIR)
    ov2 = db.mastery_overview()
    check("标记后已学 = 2", ov2["learned"] == 2, ov2)
    check("熟练 = 1", ov2["good"] == 1, ov2)
    check("未学 = 198", ov2["buckets"][MASTERY_NEW] == 198, ov2["buckets"])
    check("百分比算得对", ov2["percent"] == 1, ov2["percent"])

    cats = db.category_stats()
    check("分类统计 12 条", len(cats) == 12, len(cats))
    logic = [c for c in cats if c["name"] == "逻辑"][0]
    check("逻辑类已学 1", logic["good"] == 1, logic)
    check("各分类 total 加起来 = 200",
          sum(c["total"] for c in cats) == 200, sum(c["total"] for c in cats))

    paths = db.learning_progress()
    check("路径进度 7 条", len(paths) == 7, len(paths))
    check("每条都带 key/title/goal/tip",
          all({"key", "title", "goal", "tip"} <= set(p) for p in paths))
    check("每条都有 is_recipe_stage 标记",
          all("is_recipe_stage" in p for p in paths))
    stage1 = paths[0]
    check("第一阶段的熟练数为 1", stage1["good"] == 1, stage1)
    check("阶段 percent 是 0~100 的整数",
          all(isinstance(p["percent"], int) and 0 <= p["percent"] <= 100
              for p in paths), [p["percent"] for p in paths])
    recipe_stages = [p for p in paths if p["is_recipe_stage"]]
    check("恰好一个阶段是配方阶段", len(recipe_stages) == 1,
          [p["key"] for p in recipe_stages])

    # 配方 CRUD
    recipes = db.all_recipes()
    check("配方 20 条", len(recipes) == 20, len(recipes))
    check("配方带 book_page / my_note 字段",
          "book_page" in recipes[0] and "my_note" in recipes[0])
    rid = recipes[0]["id"]
    db.update_recipe_fields(rid, book_page="P88", my_note="这一步我常忘")
    got = db.get_recipe(rid)
    check("配方可编辑可读回",
          got["book_page"] == "P88" and got["my_note"] == "这一步我常忘", dict(got))
    db.update_recipe_fields(rid, book_page="", my_note="")
    check("白名单外的键被忽略（不报错）",
          db.update_recipe_fields(rid, title="不该改") is None
          and db.get_recipe(rid)["title"] == recipes[0]["title"])
    check("按关键词筛配方", len(db.list_recipes(keyword="查找")) > 0)
    check("配方分类列表非空", len(db.recipe_categories()) > 0,
          db.recipe_categories())

    # 自定义函数：可以加、可以删；内置的不许删
    db.set_mastery(db.get_function_by_code("SUM")["id"], MASTERY_GOOD)
    new_id = db.add_custom_function({
        "code": "MYFUNC", "name_cn": "我的函数", "category": "数学与三角函数",
        "syntax": "=MYFUNC(x)", "args_desc": "x：任意数", "description": "自己写的",
    })
    check("自定义函数加得进去", bool(new_id), new_id)
    check("总数变 201", db.count_functions() == 201, db.count_functions())
    check("自建函数标记 is_builtin=0",
          int(db.get_function(new_id)["is_builtin"]) == 0,
          db.get_function(new_id)["is_builtin"])
    check("自建函数 code 自动大写",
          db.get_function(new_id)["code"] == "MYFUNC",
          db.get_function(new_id)["code"])
    try:
        db.add_custom_function({"code": "MYFUNC"})
        check("重复 code 要报错", False, "没报错")
    except ValueError:
        check("重复 code 要报错", True)
    try:
        db.add_custom_function({"code": "   "})
        check("空 code 要报错", False, "没报错")
    except ValueError:
        check("空 code 要报错", True)
    check("自定义函数可删", db.delete_function(new_id) is True)
    check("删完回到 200", db.count_functions() == 200, db.count_functions())
    builtin_id = db.get_function_by_code("SUM")["id"]
    # 内置函数是「大声报错」而不是「静默返回 False」—— 页面在调它之前会先拦一道
    # 给出友好提示，直接调用方（脚本 / 测试）则应该立刻知道这是不允许的操作。
    try:
        db.delete_function(builtin_id)
        check("内置函数不许删（要抛 ValueError）", False, "没报错")
    except ValueError:
        check("内置函数不许删（要抛 ValueError）", True)
    check("内置函数还在", db.get_function(builtin_id) is not None)
    check("删不存在的返回 False", db.delete_function(999999) is False)
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# M. 自测出题：题干与凑题
# ══════════════════════════════════════════════════════════════════════════
def test_quiz_questions() -> None:
    section("[M] 自测出题（题干与凑题）")
    db = fresh("quiz")

    # -- 正文清理与切句 ---------------------------------------------------
    check("strip_emphasis 剥掉 ** 标记",
          strip_emphasis("**IF** 是判断用的") == "IF 是判断用的",
          strip_emphasis("**IF** 是判断用的"))
    check("scenario_sentences 中英文分号都拆、空句丢掉",
          scenario_sentences("甲；乙; 丙；；丁") == ["甲", "乙", "丙", "丁"],
          scenario_sentences("甲；乙; 丙；；丁"))
    check("scenario_sentences 尊重 limit",
          scenario_sentences("甲；乙；丙", limit=2) == ["甲", "乙"],
          scenario_sentences("甲；乙；丙", limit=2))

    # -- mask_code：这里有个真会踩的坑 ------------------------------------
    check("mask_code 把函数名换成「这个函数」",
          mask_code("用 IF 做判断", "IF") == "用 这个函数 做判断",
          mask_code("用 IF 做判断", "IF"))
    check("mask_code 不误伤 IFERROR（既没 \\b 也没前缀导致的关键回归点）",
          mask_code("用 IFERROR 包住 IF", "IF") == "用 IFERROR 包住 这个函数",
          mask_code("用 IFERROR 包住 IF", "IF"))
    check("mask_code 对空函数名原样返回",
          mask_code("原样", "") == "原样")

    # -- 题干：选择题必须打码，写公式题不打 -------------------------------
    target = db.get_function_by_code("VLOOKUP")
    check("库里能拿到 VLOOKUP（后面几条都靠它）", target is not None)
    prompt_c = quiz_prompt(target, quiz_type=QUIZ_CHOICE)
    check("选择题题干不含函数名",
          "VLOOKUP" not in prompt_c.upper(), prompt_c)
    check("题干里不留 ** 强调标记", "**" not in prompt_c, prompt_c)
    check("选择题不给语法原型（那是答案的一部分）",
          "语法原型" not in prompt_c, prompt_c)
    prompt_f = quiz_prompt(target, quiz_type=QUIZ_FORMULA)
    check("写公式题题干保留函数名",
          "VLOOKUP" in prompt_f.upper(), prompt_f)
    check("写公式题给出语法原型", "语法原型" in prompt_f, prompt_f)

    # -- 选择题：四选一、正解在选项里、题面不泄露选项 ---------------------
    pool = db.all_functions()
    question = build_choice_question(target, pool, rng=random.Random(1))
    check("选择题能出出来", question is not None)
    if question:
        check("恰好 4 个选项",
              len(question["options"]) == QUIZ_OPTION_COUNT, question["options"])
        check("选项不重复",
              len(set(question["options"])) == len(question["options"]),
              question["options"])
        check("正解在选项里",
              question["answer"] == "VLOOKUP"
              and "VLOOKUP" in question["options"], question["options"])
        check("题面里一个选项名都没出现（否则是在暗示答案）",
              all(opt not in question["prompt"] for opt in question["options"]),
              question["prompt"])
        check("「答完才揭晓」的字段都齐备",
              {"reveal_formula", "reveal_result", "reveal_pitfalls", "syntax"}
              <= set(question), sorted(question))
        check("题目带上函数 id 与分类（错题本要靠它）",
              int(question["function_id"]) == int(target["id"])
              and question["category"] == target["category"], question)
    check("候选池太小（凑不满 4 个）时返回 None，让调用方跳过这题",
          build_choice_question(target, [target], rng=random.Random(1)) is None)

    # -- 写公式题：答案是示例公式，自己写自己评 ---------------------------
    fq = build_formula_question(target, rng=random.Random(2))
    check("写公式题能出出来", fq is not None)
    if fq:
        check("写公式题的答案就是示例公式",
              fq["answer"] == strip_emphasis(target["example_formula"]).strip(),
              fq["answer"])
        check("写公式题没有选项（自评，不是机判）", fq["options"] == [], fq["options"])
    no_example = dict(target)
    no_example["example_formula"] = ""
    check("没有示例公式的函数出不了写公式题",
          build_formula_question(no_example, rng=random.Random(3)) is None)

    # -- 凑一轮：同种子同套题 / 题型模式 / 优先不熟的 ---------------------
    round_a = db.quiz_questions(count=8, seed=42)
    round_b = db.quiz_questions(count=8, seed=42)
    check("同一个种子凑出同一套题（测试与「重做错题」都靠它）",
          [q["code"] for q in round_a] == [q["code"] for q in round_b],
          [q["code"] for q in round_a])
    check("凑题数量不超过上限", 0 < len(round_a) <= 8, len(round_a))
    check("每题都带题干与类型",
          all(q["prompt"] and q["quiz_type"] in (QUIZ_CHOICE, QUIZ_FORMULA)
              for q in round_a), round_a[:1])

    kinds = {q["quiz_type"] for q in db.quiz_questions(count=10, seed=5)}
    check("混合模式两种题型都有",
          kinds == {QUIZ_CHOICE, QUIZ_FORMULA}, kinds)
    only_choice = build_quiz_questions(db.all_functions(), count=6,
                                      mode=QUIZ_CHOICE, rng=random.Random(9))
    check("只出选择题模式确实只有选择题",
          only_choice and all(q["quiz_type"] == QUIZ_CHOICE for q in only_choice),
          len(only_choice))
    only_formula = build_quiz_questions(db.all_functions(), count=6,
                                        mode=QUIZ_FORMULA, rng=random.Random(9))
    check("只出写公式模式确实只有写公式题",
          only_formula and all(q["quiz_type"] == QUIZ_FORMULA for q in only_formula),
          len(only_formula))

    # 把一批标成熟练，再凑一轮：应当基本不抽它们
    strong_codes = set()
    for item in db.all_functions()[:40]:
        db.set_mastery(item["id"], MASTERY_GOOD, today="2026-09-23")
        strong_codes.add(item["code"])
    picked = db.quiz_questions(count=5, seed=11)
    check("抽题优先挑不熟的（quiz_questions 走 list_functions 才带 mastery）",
          picked and all(q["code"] not in strong_codes for q in picked),
          [q["code"] for q in picked])

    check("空库凑题返回空列表而不是报错",
          build_quiz_questions([], count=5, rng=random.Random(1)) == [])
    check("分类过滤只出该分类的题",
          {q["category"] for q in db.quiz_questions(count=6, seed=3,
                                                    category="文本")}
          == {"文本"},
          {q["category"] for q in db.quiz_questions(count=6, seed=3,
                                                    category="文本")})
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# N. 自测作答：回灌遗忘曲线 + 错题本
# ══════════════════════════════════════════════════════════════════════════
def test_quiz_answers() -> None:
    section("[N] 自测作答（回灌 + 错题本）")
    db = fresh("quiz_answer")

    # -- 答对：按「熟练」回灌，间隔往后跳 --------------------------------
    right = db.get_function_by_code("SUM")
    db.set_mastery(right["id"], MASTERY_WEAK, today="2026-09-23")
    first = db.record_quiz_result(function_id=right["id"], quiz_type=QUIZ_CHOICE,
                                  prompt="题干", answer="SUM", user_answer="SUM",
                                  is_correct=True, category=right["category"],
                                  today="2026-09-23")
    check("作答落进流水（有主键）", first["id"] > 0, first)
    state = db.progress_map()[right["id"]]
    check("答对掌握度 +1", state["mastery"] == MASTERY_WEAK + 1, state["mastery"])
    check("答对连对次数 +1", state["correct_streak"] == 1, state["correct_streak"])
    check("答对排到明天（连对 1 次 → 1 天）",
          state["next_review_at"] == "2026-09-24", state["next_review_at"])

    db.record_quiz_result(function_id=right["id"], quiz_type=QUIZ_CHOICE,
                          is_correct=True, today="2026-09-24")
    state = db.progress_map()[right["id"]]
    check("连对两次后间隔跳到 3 天（同一条遗忘曲线）",
          state["next_review_at"] == "2026-09-27", state["next_review_at"])

    # -- 答错：掌握度 −1、明天再来、进错题本 ------------------------------
    wrong = db.get_function_by_code("COUNT")
    state0 = db.progress_map().get(wrong["id"]) or {}
    db.record_quiz_result(function_id=wrong["id"], quiz_type=QUIZ_CHOICE,
                          prompt="题干", answer="COUNT", user_answer="SUM",
                          is_correct=False, category=wrong["category"],
                          today="2026-09-23")
    after = db.progress_map()[wrong["id"]]
    check("答错掌握度落在「生疏」（未学的答错也至少是生疏）",
          after["mastery"] == MASTERY_WEAK,
          (state0.get("mastery"), after["mastery"]))
    check("答错明天再来", after["next_review_at"] == "2026-09-24",
          after["next_review_at"])
    check("答错连对归零", after["correct_streak"] == 0, after["correct_streak"])

    # 同一个函数连错三次，错题本里仍只有一行
    for _ in range(2):
        db.record_quiz_result(function_id=wrong["id"], quiz_type=QUIZ_CHOICE,
                              is_correct=False, category=wrong["category"],
                              today="2026-09-23")
    book = db.quiz_wrong_items()
    ids = [int(item["function_id"]) for item in book]
    check("错题本按函数去重（连错三次只占一行）",
          ids.count(int(wrong["id"])) == 1, ids)
    check("错题本带上函数名与分类（界面直接显示）",
          all(item["code"] and item["category"] for item in book),
          [(item["code"], item["category"]) for item in book])
    check("错题本带出示例公式与示例结果（写公式题要看）",
          "example_formula" in book[0] and "example_result" in book[0],
          sorted(book[0]))

    # -- 订正：从错题本消失，并按「熟练」回灌 ----------------------------
    log_id = int(book[0]["id"])
    before_mastery = db.progress_map()[wrong["id"]]["mastery"]
    check("标订正返回 True", db.mark_quiz_retried(log_id, correct=True,
                                                 today="2026-09-23") is True)
    check("订正后不再出现在错题本（同一个函数错过的每一行都要销账，"
          "否则下次刷新它又被捞回来）",
          int(wrong["id"]) not in [int(i["function_id"])
                                   for i in db.quiz_wrong_items()],
          [i["code"] for i in db.quiz_wrong_items()])
    check("订正把该函数名下所有未订正的错题一起销账",
          db.conn.execute(
              "SELECT COUNT(*) FROM excel_quiz_log "
              "WHERE function_id = ? AND is_correct = 0 AND retried = 0",
              (int(wrong["id"]),)).fetchone()[0] == 0)
    check("订正也按「熟练」回灌（掌握度 +1）",
          db.progress_map()[wrong["id"]]["mastery"] == before_mastery + 1,
          db.progress_map()[wrong["id"]]["mastery"])
    check("订正不存在的记录返回 False", db.mark_quiz_retried(999999) is False)

    # -- 汇总口径 --------------------------------------------------------
    stats = db.quiz_stats()
    check("自测汇总：作答 5 次、对 2 次、错 3 次",
          stats["attempts"] == 5 and stats["correct"] == 2 and stats["wrong"] == 3,
          stats)
    check("正确率四舍五入成整数（2/5）", stats["accuracy"] == 40, stats)
    check("错题本已清空（pending 归零）", stats["pending"] == 0, stats)

    # -- 只出错题本里的题 -------------------------------------------------
    db.record_quiz_result(function_id=wrong["id"], quiz_type=QUIZ_CHOICE,
                          is_correct=False, category=wrong["category"],
                          today="2026-09-23")
    only = db.quiz_questions(count=5, only_wrong=True, seed=2)
    check("只出错题本模式：抽到的都在错题本里（错题本只剩 1 条时也必须出得来题，"
          "干扰项要从全库取）",
          only and {q["function_id"] for q in only} == {int(wrong["id"])},
          [(q["code"], q["function_id"]) for q in only])
    if only and only[0]["options"]:
        check("只练错题时干扰项仍从全库来（选项不止错题本里那一个）",
              len(only[0]["options"]) == QUIZ_OPTION_COUNT,
              only[0]["options"])

    # -- 删函数要把它的流水一并清掉 ---------------------------------------
    victim_id = db.add_custom_function({
        "code": "MYTEMP", "name_cn": "临时函数", "category": "逻辑",
        "syntax": "MYTEMP()", "description": "只为验删除的孤儿清理"})
    db.record_quiz_result(function_id=victim_id, quiz_type=QUIZ_CHOICE,
                          is_correct=False, category="逻辑", today="2026-09-23")
    check("自建函数能删", db.delete_function(victim_id) is True)
    orphan = [item["code"] for item in db.quiz_wrong_items()]
    check("删掉函数后错题本不留孤儿（否则会出现没有名字的一行）",
          "MYTEMP" not in orphan, orphan)

    # -- 清理：只清错 / 全清 ---------------------------------------------
    removed = db.clear_quiz_log(wrong_only=True)
    check("清错题本确实删掉了错题流水", removed >= 1, removed)
    check("清完错题本为空", db.quiz_wrong_items() == [])
    check("清错题本不动答对的流水",
          db.quiz_stats()["correct"] == 2, db.quiz_stats())
    check("作答总数也不变（清错题本 ≠ 统计清零，答对的 2 条还在）",
          db.quiz_stats()["attempts"] == 2, db.quiz_stats())
    db.clear_quiz_log(wrong_only=False)
    check("全清后统计归零",
          db.quiz_stats()["attempts"] == 0 and db.quiz_stats()["accuracy"] == 0,
          db.quiz_stats())
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# O. 批量导入：解析与校验
# ══════════════════════════════════════════════════════════════════════════
def test_import_parsing() -> None:
    section("[O] 批量导入（解析与校验）")

    # -- 模板 ------------------------------------------------------------
    headers = import_template_headers()
    check("模板列数 = IMPORT_COLUMNS 列数",
          len(headers) == len(IMPORT_COLUMNS), len(headers))
    check("必填列的列头带 * 前缀",
          headers[0] == "*code" and headers[1] == "*name_cn"
          and headers[2] == "*category", headers[:5])
    check("可选列的列头不带 *",
          not any(h.startswith("*") for h in headers[5:]), headers[5:])

    rows = parse_import_csv_text(import_template_csv())
    check("模板 CSV 能被自己的解析器读回来（照模板填就能导）",
          len(rows) == len(import_template_rows()), len(rows))
    first = normalize_import_row(rows[0])
    check("模板行认得出函数名", first["code"] == "MYFUNC1", first["code"])
    check("模板行认得出中文名与分类",
          first["name_cn"] == "我的函数一" and first["category"] == "查找与引用",
          (first["name_cn"], first["category"]))
    check("模板行的难度中文认成数字（常用 → 2）",
          first["difficulty"] == 2, first["difficulty"])
    check("模板行的重要度中文认成数字（核心 → 3）",
          first["importance"] == 3, first["importance"])
    check("模板行本身没有校验问题（否则模板就是错的）",
          validate_import_row(first) == [], validate_import_row(first))

    # -- 列头别名与归一化 -------------------------------------------------
    check("中文列头能认成字段名",
          normalize_import_header("函数名") == "code"
          and normalize_import_header("中文名称") == "name_cn"
          and normalize_import_header(" 我的理解 ") == "my_note",
          (normalize_import_header("函数名"), normalize_import_header("我的理解")))
    check("模板里的 * 前缀不影响识别",
          normalize_import_header("*难度") == "difficulty")
    check("认不出来的列头返回 None（那一列直接忽略）",
          normalize_import_header("随便写点什么") is None
          and normalize_import_header("") is None)

    check("None 归一化成空串", normalize_import_value(None) == "")
    check("整数值的浮点去掉 .0（Excel 读出来是 412.0）",
          normalize_import_value(412.0) == "412", normalize_import_value(412.0))
    check("日期转 ISO",
          normalize_import_value(date(2026, 9, 23)) == "2026-09-23",
          normalize_import_value(date(2026, 9, 23)))
    check("布尔转 1/0", normalize_import_value(True) == "1")

    check("normalize_import_row 幂等（预览与写库共用同一条路径）",
          normalize_import_row(first) == first,
          {k: (first[k], normalize_import_row(first)[k])
           for k in first if first[k] != normalize_import_row(first)[k]})
    check("函数名统一大写并去掉内部空格",
          normalize_import_row({"函数": " my func 1 "})["code"] == "MYFUNC1",
          normalize_import_row({"函数": " my func 1 "})["code"])
    check("分类留空时兜到「逻辑」",
          normalize_import_row({"函数": "AAA"})["category"] == "逻辑")

    # -- 校验 ------------------------------------------------------------
    blank = normalize_import_row({})
    check("必填全空时报出 4 个问题（分类会兜到「逻辑」，所以不算缺）",
          len(validate_import_row(blank)) == 4, validate_import_row(blank))
    check("分类留空时兜底不算错", blank["category"] == "逻辑", blank["category"])
    base = {"code": "AAA", "name_cn": "甲", "category": "逻辑",
            "syntax": "AAA()", "description": "说明"}
    check("完整的一行没有校验问题", validate_import_row(base) == [],
          validate_import_row(base))
    check("函数名带空格会被拦下",
          any("空格" in p for p in validate_import_row({**base, "code": "MY FUNC"})),
          validate_import_row({**base, "code": "MY FUNC"}))
    check("函数名超 32 字符会被拦下",
          any("32" in p for p in validate_import_row({**base, "code": "X" * 33})),
          validate_import_row({**base, "code": "X" * 33}))
    check("难度填成 9 会被拦下",
          any("difficulty" in p
              for p in validate_import_row({**base, "difficulty": "9"})),
          validate_import_row({**base, "difficulty": "9"}))
    check("难度留空不算问题（有默认值）",
          validate_import_row({**base, "difficulty": "", "importance": ""}) == [])

    # -- 分隔符嗅探：逗号 / 分号 / 制表符 --------------------------------
    body = ("甲,列号,替换\n乙,列号,替换\n丙,列号,替换\n")
    cases = {
        "逗号": "函数名,中文名,分类,语法,用途\n" + body,
        "分号": "函数名;中文名;分类;语法;用途\n" + body.replace(",", ";"),
        "制表符": "函数名\t中文名\t分类\t语法\t用途\n" + body.replace(",", "\t"),
    }
    for label, text in cases.items():
        parsed = parse_import_csv_text(text)
        ok = len(parsed) == 3 and normalize_import_row(parsed[0])["code"] == "甲"
        check(f"{label}分隔的文件能解析（不靠 csv.Sniffer 猜，靠表头认不认得出来）",
              ok,
              (len(parsed), normalize_import_row(parsed[0]) if parsed else None))
    check("中间夹的空行会被丢掉",
          len(parse_import_csv_text("函数名,分类\n甲,逻辑\n,\n乙,逻辑\n")) == 2)

    # -- 编码回退与文件派发 ----------------------------------------------
    folder = Path(tempfile.mkdtemp(prefix="excel_import_"))
    _TMP.append(folder)
    gbk_path = folder / "gbk.csv"
    gbk_path.write_bytes(cases["逗号"].encode("gbk"))
    check("GBK 的 CSV 也能读（Excel 在中文 Windows 上就是这么存的）",
          "甲" in read_import_text(gbk_path), read_import_text(gbk_path)[:12])
    utf8_path = folder / "utf8.csv"
    utf8_path.write_bytes(("\ufeff" + cases["逗号"]).encode("utf-8"))
    check("带 BOM 的 UTF-8 也认",
          normalize_import_row(parse_import_file(utf8_path)[0])["code"] == "甲")
    try:
        parse_import_file(folder / "nope.csv")
        check("文件不存在时抛 ValueError", False, "没报错")
    except ValueError:
        check("文件不存在时抛 ValueError", True)

    # 导出的 CSV（列头是英文字段名）也要能被导入端认出来
    check("导出的列头能被导入端认回字段名",
          normalize_import_header("example_formula") == "example_formula"
          and normalize_import_header("book_page") == "book_page")


# ══════════════════════════════════════════════════════════════════════════
# P. 批量导入：写库三分支
# ══════════════════════════════════════════════════════════════════════════
def test_import_writing() -> None:
    section("[P] 批量导入（新增 / 更新 / 跳过）")
    db = fresh("import")
    before = db.count_functions()

    new_row = {"函数名": "MYTEXT", "中文名": "我的文本函数", "分类": "文本",
               "语法": "MYTEXT(文本)", "用途": "照书补录的冷门函数", "难度": "入门"}

    # -- dry_run：先报规模、一个字都不写 ---------------------------------
    preview = db.import_functions([new_row], dry_run=True)
    check("dry_run 报出 1 条新增", preview["added"] == ["MYTEXT"], preview)
    check("dry_run 入库数不变", db.count_functions() == before)
    check("dry_run 不会把函数真的建出来",
          db.get_function_by_code("MYTEXT") is None)

    # -- 新增：入成自建，所以可删 ----------------------------------------
    result = db.import_functions([new_row])
    check("导入后新增 1 条", result["added"] == ["MYTEXT"], result)
    check("库里总数 +1", db.count_functions() == before + 1)
    created = db.get_function_by_code("MYTEXT")
    check("导入进来的算自建（is_builtin=0）",
          created is not None and not int(created["is_builtin"]),
          created and created["is_builtin"])
    check("自建函数允许删除", db.delete_function(created["id"]) is True)

    # -- 同名内置：默认跳过，勾了覆盖才改写 -------------------------------
    builtin_rows = [{"函数名": "vlookup", "中文名": "改过的中文名",
                     "分类": "查找与引用", "语法": "VLOOKUP(值,区域,列)",
                     "用途": "试图覆盖内置"}]
    skipped = db.import_functions(builtin_rows)
    check("同名内置默认跳过", skipped["skipped"] and not skipped["updated"], skipped)
    check("跳过时内置内容一个字都没动",
          db.get_function_by_code("VLOOKUP")["name_cn"] != "改过的中文名")

    forced = db.import_functions(builtin_rows, overwrite_builtin=True)
    check("勾了「覆盖内置」才更新", forced["updated"] == ["VLOOKUP"], forced)
    after = db.get_function_by_code("VLOOKUP")
    check("覆盖后内容确实改了", after["name_cn"] == "改过的中文名",
          after["name_cn"])
    check("覆盖不改 is_builtin（它还是内置，仍然不许删）",
          int(after["is_builtin"]) == 1)

    # -- 覆盖只写非空列：书页码与心得不能被一次导入抹掉 -------------------
    db.update_function_fields(after["id"], book_page="88", my_note="我自己的心得")
    db.import_functions([{"函数名": "VLOOKUP", "中文名": "第三次改名",
                          "分类": "查找与引用", "语法": "VLOOKUP()",
                          "用途": "只改名字，书页与心得留空"}],
                        overwrite_builtin=True)
    kept = db.get_function_by_code("VLOOKUP")
    check("覆盖只写非空列（书页码与心得都保住了）",
          kept["book_page"] == "88" and kept["my_note"] == "我自己的心得",
          (kept["book_page"], kept["my_note"]))
    check("同一行的非空列照常改掉", kept["name_cn"] == "第三次改名",
          kept["name_cn"])

    # -- 错误分支：必填空、同文件重名 ------------------------------------
    messy = [
        {"函数名": "", "中文名": "没函数名", "分类": "逻辑", "语法": "x", "用途": "y"},
        {"函数名": "DUP", "中文名": "甲", "分类": "逻辑", "语法": "x", "用途": "y"},
        {"函数名": "dup", "中文名": "乙", "分类": "逻辑", "语法": "x", "用途": "y"},
    ]
    report = db.import_functions(messy)
    check("第一行（第 2 行）缺函数名 → errors 里点名行号",
          any(e["row"] == 2 for e in report["errors"]), report["errors"])
    check("同一个文件里大小写不同的重名也算重名",
          any("两次" in e["message"] for e in report["errors"]), report["errors"])
    check("重名的那一组只入了一条",
          report["added"] == ["DUP"], (report["added"], report["errors"]))
    check("大小写归一后能查到", db.get_function_by_code("dup") is not None)

    # -- 非官方分类：提示一句，但照样入库 ---------------------------------
    odd = db.import_functions([{"函数名": "MYODD", "中文名": "怪分类",
                                "分类": "我瞎编的分类", "语法": "MYODD()",
                                "用途": "试试自定义分类"}])
    check("非官方分类会给出提示", bool(odd["warnings"]), odd["warnings"])
    check("但照样入库（只是挂自定义分类）",
          db.get_function_by_code("MYODD") is not None)
    check("返回值里有 total（新增 + 更新）", odd["total"] == 1, odd)

    # -- 导出与模板落盘：导出的东西能被导入端读回来 -----------------------
    folder = Path(tempfile.mkdtemp(prefix="excel_export_"))
    _TMP.append(folder)
    csv_path = folder / "out.csv"
    exported = db.export_functions_csv(csv_path)
    check("导出条数与库内一致", exported == db.count_functions(), exported)
    check("导出文件带 BOM（Excel 双击不乱码）",
          csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
    back = parse_import_csv_text(read_import_text(csv_path))
    check("导出能被自己解析回来（导出 → 改 → 再导）",
          len(back) == exported, (len(back), exported))
    check("导出再导入是「原地更新」而不是新增",
          db.import_functions(back)["added"] == [],
          db.import_functions(back)["added"])

    tpl_path = folder / "template.csv"
    db.write_import_template(tpl_path)
    check("模板能落盘且带 BOM",
          tpl_path.exists() and tpl_path.read_bytes().startswith(b"\xef\xbb\xbf"))
    db.close()


# ══════════════════════════════════════════════════════════════════════════
# Q. 待办联动桥
# ══════════════════════════════════════════════════════════════════════════
def test_todo_bridge() -> None:
    section("[Q] 待办联动桥（Excel 宝典 → 待办）")
    folder = Path(tempfile.mkdtemp(prefix="excel_todo_"))
    _TMP.append(folder)
    todo = TodoDB(folder / "todo.db")
    bridge = ExcelTodoBridge(todo)

    # 2026-09-26 是周六：「今天要做的事」不该被顺延到下周一
    saturday = "2026-09-26"
    payload = review_todo_payload(due_count=7, today=saturday, extra_wrong=3)
    check("标题里带数量", payload["title"] == "复习 Excel 函数 7 个",
          payload["title"])
    check("到期日就是今天", payload["due_date"] == saturday, payload["due_date"])
    check("备注里顺手提一句错题本还有几条", "3" in payload["notes"],
          payload["notes"])
    check("中优先级（不该盖过真正的工作项）", payload["priority"] == 2,
          payload["priority"])
    node = review_todo_payload(due_count=0, today=saturday)
    check("队列为空时标题不带「0 个」", node["title"] == "复习 Excel 函数",
          node["title"])
    check("队列为空时备注给出下一步（标几个或做一轮自测）",
          "函数宝典" in node["notes"] or "自测" in node["notes"], node["notes"])

    # -- 写入 ------------------------------------------------------------
    out = bridge.create_review_todo(payload)
    check("点一下就能建出待办",
          out["created"] is True and out["item_id"], out)
    items = todo.fetch_items(scope="all", include_completed=True)
    mine = [item for item in items if str(item.title) == payload["title"]]
    check("待办真的建出来了", len(mine) == 1, [str(i.title) for i in items])
    check("落在周六当天，没被顺延到下周一",
          mine and str(mine[0].due_date) == saturday,
          mine and str(mine[0].due_date))
    check("打了 Excel 标签（方便按标签滤出学习类）",
          mine and "Excel" in list(mine[0].tags), mine and mine[0].tags)

    # 对照组：不传 skip_holidays 的默认行为就会顺延 —— 说明桥这个参数是必要的
    plain_id = todo.add_item({"title": "对照：默认会被顺延", "due_date": saturday})
    plain = [i for i in todo.fetch_items(scope="all", include_completed=True)
             if int(i.id) == int(plain_id)]
    check("对照：默认 skip_holidays 会把周六顺延到下周一",
          plain and str(plain[0].due_date) == "2026-09-28",
          plain and str(plain[0].due_date))

    # -- 当天幂等 --------------------------------------------------------
    again = bridge.create_review_todo(payload)
    check("同一天再点不重复建",
          again["created"] is False and int(again["item_id"]) == int(out["item_id"]),
          again)
    check("「同标题同日期」的待办仍然只有一条",
          len([i for i in todo.fetch_items(scope="all", include_completed=True)
               if str(i.title) == payload["title"]]) == 1)

    # 已完成的那条不再算重复：明天（或今天重开）该能再建
    todo.set_completed(int(out["item_id"]), True)
    third = bridge.create_review_todo(payload)
    check("已完成的同名待办不再算重复，会再建一条", third["created"] is True, third)

    # 换一天不算重复
    other_day = dict(payload, due_date="2026-09-27")
    check("换一天可以再建",
          bridge.create_review_todo(other_day)["created"] is True)

    # -- 缺字段不建（界面上不该出现半条待办） -----------------------------
    miss_title = bridge.create_review_todo({"title": "", "due_date": saturday})
    check("缺标题不建，并给出一句话",
          miss_title["created"] is False and miss_title["item_id"] is None
          and miss_title["message"], miss_title)
    miss_date = bridge.create_review_todo({"title": "复习 Excel 函数 1 个",
                                          "due_date": ""})
    check("缺日期不建", miss_date["created"] is False, miss_date)
    check("空 payload 不建", bridge.create_review_todo({})["created"] is False)

    todo.close()


# ══════════════════════════════════════════════════════════════════════════
# R. 页面会用到的聚合口径
# ══════════════════════════════════════════════════════════════════════════
def test_page_contracts() -> None:
    section("[R] 页面契约（页面用到的每个数据入口）")
    db = fresh("contract")

    # excel_page 里调过的每一个 ExcelDB 方法都要真的存在（防改名漏改）
    used = (
        "count_functions all_functions list_functions get_function "
        "get_function_by_code update_function_fields add_custom_function "
        "delete_function functions_by_code set_mastery record_review "
        "due_functions due_count mastery_overview category_stats "
        "learning_progress progress_map all_recipes list_recipes get_recipe "
        "update_recipe_fields recipe_categories list_notes save_note get_note "
        "delete_note note_count upsert_checkin checkin_dates get_checkin "
        "streak longest_streak totals recent_activity "
        "quiz_questions record_quiz_result quiz_wrong_items mark_quiz_retried "
        "quiz_stats clear_quiz_log import_functions update_function_content "
        "export_functions_csv write_import_template"
    ).split()
    missing = [name for name in used if not callable(getattr(db, name, None))]
    check("页面用到的数据入口都存在", not missing, missing)

    # 页面会读的键，都要在返回结构里
    item = db.all_functions()[0]
    need_keys = {"id", "code", "name_cn", "category", "syntax", "args_desc",
                 "returns", "description", "use_cases", "pitfalls", "related",
                 "example_formula", "example_result", "difficulty",
                 "importance", "min_version", "tags", "sort_order",
                 "book_page", "my_note"}
    check("函数行字段齐全", need_keys <= set(item), sorted(need_keys - set(item)))
    recipe = db.all_recipes()[0]
    rec_keys = {"id", "title", "category", "difficulty", "scene", "formula",
                "breakdown", "pitfalls", "related", "book_page", "my_note"}
    check("配方行字段齐全", rec_keys <= set(recipe), sorted(rec_keys - set(recipe)))

    # category_stats / path_progress 的键（页面直接取下标，KeyError 会当场炸）
    c = db.category_stats()[0]
    check("分类统计字段齐全",
          {"name", "total", "good", "learned", "percent"} <= set(c), sorted(c))
    p = db.learning_progress()[0]
    check("路径进度字段齐全",
          {"key", "title", "goal", "tip", "codes", "total", "good", "learned",
           "percent", "is_recipe_stage"} <= set(p), sorted(p))

    # 空库也要能画出统计（不能除零）
    empty = path_progress({"key": "X", "title": "空阶段", "goal": "", "tip": "",
                           "codes": []}, {}, {})
    check("空阶段不除零", empty["percent"] == 0, empty)
    check("空分类统计不炸", category_stats([], {}) == [] or True)

    # 自测汇总的键（导航徽标与错题本视图直接取下标）
    empty_quiz = db.quiz_stats()
    check("自测汇总字段齐全（空库也不除零）",
          {"attempts", "correct", "wrong", "pending", "accuracy"}
          <= set(empty_quiz) and empty_quiz["accuracy"] == 0, empty_quiz)
    db.close()


def main_test() -> None:
    test_seed_consistency()
    test_seed_schema()
    test_schema()
    test_seed_idempotent()
    test_pure_helpers()
    test_due_queue()
    test_mastery()
    test_record_review()
    test_search()
    test_notes()
    test_checkins()
    test_stats_and_recipes()
    test_quiz_questions()
    test_quiz_answers()
    test_import_parsing()
    test_import_writing()
    test_todo_bridge()
    test_page_contracts()


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
