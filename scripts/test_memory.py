# -*- coding: utf-8 -*-
"""记忆宫殿回归测试（数据层 + 种子 + 训练内核，纯逻辑、不碰 Tk）。

为什么单独成篇
------------------------------------------------------------------------------
这个模块有几处算错了界面上**看不出来**：

* **「今日复习」是 LEFT JOIN 还是 INNER JOIN**：进度行是懒创建的，
  刚装好内置题库时 ``memory_progress`` 一行都没有。写成内连接，首日
  「今日训练」就是空的 —— 页面不报错、日志不报错，只是什么都不推。
* **``walk_order`` 的顺序**：必须严格按地点桩的 ``seq``。顺序错了，
  记忆宫殿就从「沿路线走」退化成「随机抽背」—— 而这条路线本身才是记忆的载体。
* **间隔重复的三键**：记得 / 模糊 / 忘了 对掌握度、连对次数、间隔的改动方向
  完全不同。间隔数组是 1/3/7/15/30/60/120 七档，连对次数当索引，越界必须夹住。
* **连续打卡的「今天没打卡不清零」**：从今天往回数，今天没打卡就从昨天数起。
  写成「今天没打卡就是 0」的话，每天零点一过连续天数归零，用户会以为坏了。
* **``ensure_progress`` 不许写假流水**：「标记已学」不是一次复习。塞一条凑数，
  正确率曲线会凭空多出一次作答，这个指标就成噪声了。
* **``marked_at`` 只记「第一次标记」**：它被后续的复习覆盖掉，
  「今天新学了几条」就变成「今天动过几条」。
* **题库导入的幂等**：靠 ``source_key``。改成无脑 INSERT，重导一次就翻倍。

另一类被锁死的是「有意设计」：
* 删地点桩**不删桩上的记忆项**（它们退回「未分配」），删宫殿才有两种口径
* 六个视图 + 三栏布局是页面层的取舍，数据层不掺和
* 种子装载自检不通过就**当场抛错**，不许静默少一半

覆盖
------------------------------------------------------------------------------
A. 训练内核      与 excel_db 的口径钉在一起 / 阶梯 / 三键 / 打卡连续
B. 种子一致性    10 卡 / 3 宫殿 / 38 桩 / 100 数字桩 / 5 题库 130 题 / 装载自检
C. 建表与幂等    新库一次到位 / 重开不重复灌 / 老库（只有老表）不被动
D. 宫殿 CRUD      增改查删 / 模板导入幂等 / 删宫殿两种口径
E. 地点桩        seq 紧凑 / 删中间重排 / reorder / move / 删桩不删项
F. 记忆项        LEFT JOIN 防线 / 筛选 / 未分配 / 关键词
G. walk_order    顺序 = seq / station 标注 / 未分配的排最后
H. 间隔重复      懒创建 / 三键推进 / 到 120 封顶 / 一行流水 / 掌握度分布
I. 打卡          同日更新 / 跨月连续 / 周一对齐 / autofill / 正确率
J. 题库入库      导入幂等 / 自动挂桩 / 桩不够时收尾 / 二次导入不重复
K. 小工具        教学卡 / suggest_new_count / split_tags / format_item_line
L. 页面契约      页面用到的每个数据入口都存在、字段齐全
M. 待办桥        只在点击时建 / 当天幂等 / 不被顺延 / 两个模块共用一套规则

用法：
    python scripts/test_memory.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import excel_db  # noqa: E402
import memory_db  # noqa: E402
import memory_seed  # noqa: E402
import todo_db  # noqa: E402
import training_core as tc  # noqa: E402
import training_todo_bridge as ttb  # noqa: E402
from memory_db import MemoryPalaceDB  # noqa: E402

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


def fresh(name: str) -> MemoryPalaceDB:
    """每个小节一个独立空库：这些用例大量依赖「初始状态」，共用会互相污染。"""
    d = Path(tempfile.mkdtemp(prefix="mem_test_"))
    _TMP.append(d)
    return MemoryPalaceDB(d / f"{name}.db")


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


def _row_ids(rows) -> list:
    return [int(r["id"]) for r in rows]


# ══════════════════════════════════════════════════════════════════════════
# A. 训练内核
# ══════════════════════════════════════════════════════════════════════════
def test_core_matches_excel() -> None:
    section("[A] 训练内核（与 excel_db 的口径钉在一起）")
    check("间隔阶梯 = 1/3/7/15/30/60/120",
          tuple(tc.SRS_INTERVALS) == (1, 3, 7, 15, 30, 60, 120),
          tc.SRS_INTERVALS)
    check("掌握度四档 0/1/2/3",
          (tc.MASTERY_NEW, tc.MASTERY_WEAK, tc.MASTERY_FAIR,
           tc.MASTERY_GOOD) == (0, 1, 2, 3))
    check("三种反馈取值稳定",
          (tc.FEEDBACK_KNOWN, tc.FEEDBACK_VAGUE, tc.FEEDBACK_FORGOT)
          == ("known", "vague", "forgot"))

    # 把两份实现钉在一起：同一组输入必须给同一结果，将来合并时这条就是安全网
    mismatches = []
    for mastery in (0, 1, 2, 3):
        for streak in (0, 1, 2, 3, 5, 7, 20):
            for interval in (0, 1, 3, 7, 30, 120, 999):
                for feedback in ("known", "vague", "forgot"):
                    ours = tc.review_next_state(mastery, streak, interval, feedback)
                    theirs = excel_db.review_next_state(
                        mastery, streak, interval, feedback)
                    if (int(ours["mastery"]), int(ours["correct_streak"]),
                            int(ours["interval_days"])) != (
                            int(theirs["mastery"]), int(theirs["correct_streak"]),
                            int(theirs["interval_days"])):
                        mismatches.append((mastery, streak, interval, feedback,
                                           ours, theirs))
    check("与 excel_db.review_next_state 逐格一致（4×7×7×3 = 588 组）",
          not mismatches, mismatches[:2])

    # excel_db 没有独立的 accuracy 函数（只在 quiz_stats() 里就地算过一次百分比），
    # 所以这里比对的是「同一口径」：tc.accuracy 的百分比四舍五入 == 那边的算式。
    acc_pairs = [(0, 0), (1, 1), (3, 2), (7, 0), (10, 10)]
    check("accuracy 与 excel_db 的百分比口径一致",
          all(round(tc.accuracy(r, c) * 100)
              == (round(c * 100 / r) if r else 0)
              for r, c in acc_pairs))
    check("interval_for 与 excel_db 一致",
          all(int(tc.interval_for(i)) == int(excel_db.interval_for(i))
              for i in range(0, 12)))
    check("streak_from_dates 与 excel_db 一致（今天没打卡不算断）",
          all(tc.streak_from_dates(dates, anchor)
              == excel_db.compute_streak(dates, anchor)
              for dates, anchor in (
                  (["2026-09-28"], "2026-09-28"),
                  (["2026-09-27"], "2026-09-28"),
                  (["2026-09-26"], "2026-09-28"),
                  (["2026-09-25", "2026-09-26", "2026-09-27"], "2026-09-28"),
                  ([], "2026-09-28"),
              )))


# ══════════════════════════════════════════════════════════════════════════
# B. 种子一致性
# ══════════════════════════════════════════════════════════════════════════
def test_seed_consistency() -> None:
    section("[B] 种子一致性")
    counts = memory_seed.counts()
    check("教学卡 ≥ 10 张", counts["cards"] >= 10, counts["cards"])
    check("宫殿模板 ≥ 3 套", counts["templates"] >= 3, counts["templates"])
    check("地点桩 ≥ 38 个", counts["loci"] >= 38, counts["loci"])
    check("数字桩恰好 100 个", counts["pegs"] == 100, counts["pegs"])
    check("题库 ≥ 5 个", counts["banks"] >= 5, counts["banks"])
    check("题量 ≥ 130 条", counts["bank_items"] >= 130, counts["bank_items"])

    check("教学卡码唯一",
          len({c["code"] for c in memory_seed.TEACHING_CARDS})
          == len(memory_seed.TEACHING_CARDS))
    check("宫殿模板码唯一",
          len({t["code"] for t in memory_seed.PALACE_TEMPLATES})
          == len(memory_seed.PALACE_TEMPLATES))
    check("题库码唯一",
          len({b["code"] for b in memory_seed.BANKS}) == len(memory_seed.BANKS))
    # NUMBER_PEGS 是 (code, image, hint) 三元组；编码唯一、图像也必须唯一，
    # 否则两个数字指向同一张图，编码就失去意义了。
    check("数字桩编码是 00~99 且有序",
          [p[0] for p in memory_seed.NUMBER_PEGS]
          == [f"{i:02d}" for i in range(100)])
    check("数字桩图像不重复（重复就失去编码意义）",
          len({p[1] for p in memory_seed.NUMBER_PEGS}) == len(
              memory_seed.NUMBER_PEGS))
    check("每个数字桩都有图像与提示",
          all(str(p[1]).strip() and str(p[2]).strip()
              for p in memory_seed.NUMBER_PEGS))
    check("每个题库都够 20 条以上",
          all(len(b["items"]) >= 20 for b in memory_seed.BANKS),
          [f"{b['code']}:{len(b['items'])}" for b in memory_seed.BANKS])

    # 装载自检：不通过就当场抛错，不许静默少一半
    try:
        memory_seed.validate()
        ok, detail = True, ""
    except Exception as exc:                     # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    check("模块级 validate() 通过", ok, detail)
    check("教学卡可选字段齐全",
          all({"code", "title", "category", "body", "practice", "tip"}
              <= set(c) for c in memory_seed.TEACHING_CARDS))


# ══════════════════════════════════════════════════════════════════════════
# C. 建表与幂等
# ══════════════════════════════════════════════════════════════════════════
def test_schema() -> None:
    section("[C] 建表与幂等")
    db = fresh("schema")
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    need = {"memory_palaces", "memory_loci", "memory_items", "memory_progress",
            "memory_reviews", "memory_checkins", "memory_banks", "memory_bank_items"}
    check("八张表齐备", need <= names, sorted(need - names))
    check("题库随建库灌好", len(db.list_banks()) >= 5, len(db.list_banks()))
    before = len(db.list_bank_items(db.list_banks()[0]["id"]))
    db2 = MemoryPalaceDB(db.db_path)             # 重开一次
    check("重开不重复灌题库",
          len(db2.list_banks()) >= 5
          and len(db2.list_bank_items(db2.list_banks()[0]["id"])) == before)
    check("重开不会重复建宫殿（模板要显式导入）",
          db2.list_palaces() == [], len(db2.list_palaces()))

    # 老库（只有别的模块的表）不受影响：新表 CREATE TABLE IF NOT EXISTS，不动老表
    d = Path(tempfile.mkdtemp(prefix="mem_old_"))
    _TMP.append(d)
    legacy = d / "legacy.db"
    with sqlite3.connect(legacy) as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('老数据')")
    MemoryPalaceDB(legacy)
    with sqlite3.connect(legacy) as conn:
        row = conn.execute("SELECT name FROM users").fetchone()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    check("老库里的老表原封不动", row and row[0] == "老数据", row)
    check("老库加上了新表", "memory_items" in tables and "users" in tables)


# ══════════════════════════════════════════════════════════════════════════
# D. 宫殿 CRUD
# ══════════════════════════════════════════════════════════════════════════
def test_palace_crud() -> None:
    section("[D] 宫殿 CRUD")
    db = fresh("palace")
    pid = db.add_palace("我的住宅", kind="住宅", route_note="进门顺时针",
                        description="练熟的第一条路线", tags="住宅|日常")
    row = db.get_palace(pid)
    check("新建宫殿字段齐全",
          row and row["name"] == "我的住宅" and row["kind"] == "住宅"
          and row["route_note"] == "进门顺时针", row)
    check("update_palace 生效并返回 True",
          db.update_palace(pid, name="我的住宅 v2", route_note="改成逆时针") is True)
    check("update_palace 改完读回来是新值",
          db.get_palace(pid)["name"] == "我的住宅 v2")
    check("update_palace 传空返回 False", db.update_palace(pid) is False)
    check("get_palace 找不到返回 None", db.get_palace(99999) is None)

    # 模板导入幂等：命中 source_key 时返回**既有** id，所以第二次不是空列表，
    # 而是与第一次一模一样的 id 列表；宫殿总数也不会再涨。
    before_n = len(db.list_palaces())
    ids = db.import_all_templates()
    again = db.import_all_templates()
    check("导入全部模板返回 3 个 id", len(ids) == 3, ids)
    check("重复导入不会再建（幂等）",
          again == ids and len(db.list_palaces()) == before_n + 3,
          (again, before_n, len(db.list_palaces())))
    check("模板宫殿带 source_key 可追溯（前缀 template:）",
          db.get_palace_by_source("template:TPL_HOME") is not None,
          [p["source_key"] for p in db.list_palaces()])
    check("模板宫殿真的带了桩",
          all(len(db.list_loci(p["id"])) > 0 for p in db.list_palaces()
              if str(p["source_key"]).startswith("template:")),
          [(p["name"], len(db.list_loci(p["id"]))) for p in db.list_palaces()])

    # 删宫殿两种口径
    work = db.add_palace("临时的")
    db.add_locus(work, "门口")
    db.add_item(front="要记的", palace_id=work)
    check("delete_palace(默认) 连项一起删",
          db.delete_palace(work) is True and db.count_items(palace_id=work) == 0)

    work2 = db.add_palace("临时的2")
    item_id = db.add_item(front="留下的", palace_id=work2)
    db.delete_palace(work2, keep_items=True)
    kept = db.get_item(item_id)
    check("delete_palace(keep_items=True) 项保留",
          kept is not None and int(kept["palace_id"]) == 0,
          kept and kept["palace_id"])
    check("保留的项变成「未归档」",
          item_id in _row_ids(db.list_items(unassigned=True)))


# ══════════════════════════════════════════════════════════════════════════
# E. 地点桩
# ══════════════════════════════════════════════════════════════════════════
def test_loci() -> None:
    section("[E] 地点桩（走一遍的路线）")
    db = fresh("loci")
    pid = db.add_palace("测试路线")
    ids = [db.add_locus(pid, f"第 {i} 站", hint=f"提示 {i}") for i in range(1, 6)]
    loci = db.list_loci(pid)
    check("桩按 seq 排好且 seq = 0..4",
          [int(x["seq"]) for x in loci] == list(range(5)),
          [int(x["seq"]) for x in loci])
    check("桩名与提示都存住了",
          loci[0]["name"] == "第 1 站" and loci[0]["hint"] == "提示 1")

    db.delete_locus(ids[2])                       # 删中间那个
    loci = db.list_loci(pid)
    check("删中间一个后 seq 紧凑无洞",
          [int(x["seq"]) for x in loci] == [0, 1, 2, 3],
          [int(x["seq"]) for x in loci])
    check("被删的桩不在列表里", ids[2] not in _row_ids(loci))

    db.reorder_loci(pid, [ids[4], ids[0], ids[1], ids[3]])
    loci = db.list_loci(pid)
    check("reorder_loci 按给定顺序重排",
          _row_ids(loci) == [ids[4], ids[0], ids[1], ids[3]], _row_ids(loci))

    # reorder 传入残缺 / 带重复的名单，不许丢桩。
    # 注意 ids[2] 在上面已经被删了，存活的只有 ids[0]/[1]/[3]/[4]。
    alive = [ids[0], ids[1], ids[3], ids[4]]
    db.reorder_loci(pid, [ids[0], ids[0], ids[1]])
    loci = db.list_loci(pid)
    check("reorder_loci 传重复 id 不丢桩（去重保序 + 没提到的接后面）",
          sorted(_row_ids(loci)) == sorted(alive), _row_ids(loci))
    check("reorder_loci 前两个就是名单顺序",
          _row_ids(loci)[:2] == [ids[0], ids[1]], _row_ids(loci))

    db.reorder_loci(pid, [ids[0], ids[1], ids[3], ids[4]])
    moved = db.move_locus(ids[3], -1)
    loci = db.list_loci(pid)
    check("move_locus(-1) 与邻居换位",
          moved is True and _row_ids(loci) == [ids[0], ids[3], ids[1], ids[4]],
          _row_ids(loci))
    check("move_locus 到顶返回 False", db.move_locus(ids[0], -1) is False)
    check("move_locus 到底返回 False", db.move_locus(ids[4], 1) is False)

    # 删桩不删项
    db.add_item(front="挂在桩上的", palace_id=pid, locus_id=ids[0])
    db.delete_locus(ids[0])
    rows = db.list_items(palace_id=pid)
    check("删桩不删桩上的记忆项（退回未分配）",
          len(rows) == 1 and int(rows[0]["locus_id"]) == 0, rows)
    check("item_counts_by_locus 统计正确",
          db.item_counts_by_locus(pid).get(0, 0) == 1,
          db.item_counts_by_locus(pid))


# ══════════════════════════════════════════════════════════════════════════
# F. 记忆项
# ══════════════════════════════════════════════════════════════════════════
def test_items() -> None:
    section("[F] 记忆项")
    db = fresh("items")
    pid = db.add_palace("路线")
    lid = db.add_locus(pid, "鞋柜")
    a = db.add_item(front="苹果", back="apple", imagery="一个巨大的苹果挡住鞋柜",
                    story="进门先踩到苹果", palace_id=pid, locus_id=lid,
                    category="英语", tags="食物")
    b = db.add_item(front="香蕉", back="banana", palace_id=pid, locus_id=lid,
                    category="英语")
    c = db.add_item(front="未挂的", back="free")

    rows = db.list_items(palace_id=pid)
    check("list_items 行字段带 mastery / due / locus_name",
          {"mastery", "next_review_at", "due", "bucket", "locus_name", "locus_seq",
           "palace_name"} <= set(rows[0]), sorted(rows[0]))
    # 「due」= 已到期该复习（bucket == "due"）；全新项是 bucket == "new"、due 为假。
    # 这条防线要验的是**全新项根本没被内连接滤掉**（在列表里、mastery=0）。
    check("**LEFT JOIN 防线**：全新项 mastery=0、bucket=new（没被滤掉）",
          all(int(r["mastery"]) == 0 and r["bucket"] == "new"
              and r["due"] is False for r in rows),
          [(r["front"], r["mastery"], r["bucket"]) for r in rows])
    check("按宫殿筛选只拿到本宫殿的", _row_ids(rows) == [a, b], _row_ids(rows))
    check("按桩筛选", _row_ids(db.list_items(palace_id=pid, locus_id=lid))
          == [a, b])
    check("未归档筛选只拿到没宫殿的",
          _row_ids(db.list_items(unassigned=True)) == [c],
          _row_ids(db.list_items(unassigned=True)))
    check("按分类筛选",
          _row_ids(db.list_items(category="英语")) == [a, b])
    check("关键词命中 front / back / imagery / story / tags",
          _row_ids(db.list_items(keyword="香蕉")) == [b]
          and _row_ids(db.list_items(keyword="apple")) == [a]
          and _row_ids(db.list_items(keyword="巨大的")) == [a]
          and _row_ids(db.list_items(keyword="踩到")) == [a]
          and _row_ids(db.list_items(keyword="食物")) == [a])
    check("categories 去重排序", db.categories() == ["英语"], db.categories())
    check("count_items 与 list_items 一致",
          db.count_items(palace_id=pid) == len(rows))

    db.update_item(a, front="大苹果", back="big apple")
    check("update_item 生效", db.get_item(a)["front"] == "大苹果")
    check("update_item 空参数返回 False", db.update_item(a) is False)
    check("delete_item 生效", db.delete_item(b) is True and db.get_item(b) is None)


# ══════════════════════════════════════════════════════════════════════════
# G. walk_order
# ══════════════════════════════════════════════════════════════════════════
def test_walk_order() -> None:
    section("[G] walk_order（走一遍的顺序）")
    db = fresh("walk")
    pid = db.add_palace("路线")
    l1 = db.add_locus(pid, "玄关", hint="进门左手边")
    l2 = db.add_locus(pid, "客厅", hint="沙发后面")
    l3 = db.add_locus(pid, "厨房", hint="冰箱顶上")
    # 故意按「乱序」插入，并让一个桩挂两条
    i_x = db.add_item(front="客厅A", palace_id=pid, locus_id=l2)
    i_y = db.add_item(front="玄关A", palace_id=pid, locus_id=l1)
    i_z = db.add_item(front="厨房A", palace_id=pid, locus_id=l3)
    i_w = db.add_item(front="玄关B", palace_id=pid, locus_id=l1)
    i_free = db.add_item(front="没挂桩", palace_id=pid)

    order = db.walk_order(pid)
    check("顺序 = 桩 seq（不是插入顺序）",
          [r["front"] for r in order] == ["玄关A", "玄关B", "客厅A", "厨房A",
                                          "没挂桩"],
          [r["front"] for r in order])
    check("station = seq + 1",
          [int(r["station"]) for r in order[:4]] == [1, 1, 2, 3],
          [r["station"] for r in order])
    check("桩名与提示都带出来",
          order[0]["locus_name"] == "玄关" and order[0]["locus_hint"] == "进门左手边",
          (order[0]["locus_name"], order[0]["locus_hint"]))
    check("未分配的排在最后且 station=0",
          int(order[-1]["station"]) == 0
          and order[-1]["locus_name"] == "（未分配桩）", order[-1])

    db.reorder_loci(pid, [l3, l1, l2])
    order2 = db.walk_order(pid)
    check("重排桩后走一遍顺序跟着变",
          [r["front"] for r in order2][:4] == ["厨房A", "玄关A", "玄关B", "客厅A"],
          [r["front"] for r in order2])
    check("走一遍覆盖全部项（含未分配）",
          len(order2) == 5 and {int(x["id"]) for x in order2}
          == {i_x, i_y, i_z, i_w, i_free})
    check("桩上没有项不会出现在队列里（空桩跳过）",
          all(r["locus_name"] != "空桩" for r in order2))


# ══════════════════════════════════════════════════════════════════════════
# H. 间隔重复
# ══════════════════════════════════════════════════════════════════════════
def test_srs() -> None:
    section("[H] 间隔重复")
    db = fresh("srs")
    pid = db.add_palace("路线")
    lid = db.add_locus(pid, "桩")
    iid = db.add_item(front="要记的", palace_id=pid, locus_id=lid)

    check("get_progress 不建行（读操作无副作用）",
          db.get_progress(iid)["mastery"] == 0
          and db.get_progress(iid)["next_review_at"] == "")
    with __import__("sqlite3").connect(db.db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM memory_progress").fetchone()[0]
    check("只读不落库", n == 0, n)

    db.ensure_progress(iid)
    db.ensure_progress(iid)
    prog = db.get_progress(iid)
    check("ensure_progress 幂等且不写假流水",
          len(db.list_reviews(item_id=iid)) == 0,
          db.list_reviews(item_id=iid))
    check("ensure_progress 记下 marked_at", str(prog["marked_at"]).strip() != "")

    marked = prog["marked_at"]

    # 三键推进
    db.record_review(iid, tc.FEEDBACK_KNOWN, today="2026-09-01")
    p = db.get_progress(iid)
    check("记得：掌握度升到 1、连对 1、间隔 1 天、到期 09-02",
          (int(p["mastery"]), int(p["correct_streak"]), int(p["interval_days"]),
           p["next_review_at"]) == (1, 1, 1, "2026-09-02"), p)
    check("判过之后 marked_at 不被覆盖（它记的是「第一次标记」）",
          p["marked_at"] == marked, (marked, p["marked_at"]))

    db.record_review(iid, tc.FEEDBACK_KNOWN, today="2026-09-02")
    p = db.get_progress(iid)
    check("连对两次：间隔走到 3 天、到期 09-05",
          (int(p["correct_streak"]), int(p["interval_days"]),
           p["next_review_at"]) == (2, 3, "2026-09-05"), p)

    db.record_review(iid, tc.FEEDBACK_VAGUE, today="2026-09-05")
    p = db.get_progress(iid)
    check("模糊：连对 -1、间隔减半、掌握度不低于生疏",
          int(p["correct_streak"]) == 1 and int(p["interval_days"]) == 1
          and int(p["mastery"]) >= tc.MASTERY_WEAK, p)

    db.record_review(iid, tc.FEEDBACK_FORGOT, today="2026-09-06")
    p = db.get_progress(iid)
    check("忘了：连对归零、间隔回到 1 天、掌握度 -1",
          (int(p["correct_streak"]), int(p["interval_days"]),
           int(p["mastery"])) == (0, 1, 1), p)
    check("忘了之后明天还会再来",
          p["next_review_at"] == "2026-09-07", p["next_review_at"])

    # 一路记得，间隔必须一路加长并最终封顶在 120
    iid2 = db.add_item(front="长跑", palace_id=pid, locus_id=lid)
    reached = []
    for day in range(1, 16):
        db.record_review(iid2, tc.FEEDBACK_KNOWN, today=f"2026-10-{day:02d}")
        reached.append(int(db.get_progress(iid2)["interval_days"]))
    check("一路记得：间隔单调不减并封顶 120",
          reached == sorted(reached) and reached[-1] == 120
          and max(reached) == 120, reached)
    check("流水条数 = 复习次数（一次一行）",
          len(db.list_reviews(item_id=iid2)) == 15,
          len(db.list_reviews(item_id=iid2)))

    total_reviews = len(db.list_reviews())
    dist = db.mastery_distribution()
    check("掌握度分布覆盖全库记忆项", sum(dist.values()) == db.count_items(),
          (sum(dist.values()), db.count_items()))
    acc = db.review_accuracy(days=400, today="2026-10-20")
    check("正确率 = 记得 / 总复习",
          acc["reviewed"] == total_reviews
          and abs(acc["accuracy"] - acc["correct"] / max(1, total_reviews)) < 1e-9,
          acc)

    # set_mastery 手动标记
    iid3 = db.add_item(front="手标", palace_id=pid, locus_id=lid)
    db.set_mastery(iid3, tc.MASTERY_WEAK, today="2026-09-28")
    p3 = db.get_progress(iid3)
    check("手动标生疏：排到今天（立刻进复习队列）",
          p3["next_review_at"] == "2026-09-28", p3)
    check("手动标记不算一次复习（不写流水）",
          len(db.list_reviews(item_id=iid3)) == 0)
    db.set_mastery(iid3, 99)
    check("掌握度越界被夹到 3", int(db.get_progress(iid3)["mastery"]) == 3)
    db.set_mastery(iid3, -5)
    check("掌握度负数被夹到 0 且清空排期",
          int(db.get_progress(iid3)["mastery"]) == 0
          and db.get_progress(iid3)["next_review_at"] == "")

    # due 队列两把尺子，别混：
    #   due_items() = 今日训练队列 = 全新（bucket=new）+ 已到期（bucket=due）
    #   due_count() = 只数「已到期」那部分；全新项走 new_candidates() 数
    db2 = fresh("due")
    p2 = db2.add_palace("路线")
    l2 = db2.add_locus(p2, "桩")
    for i in range(3):
        db2.add_item(front=f"项{i}", palace_id=p2, locus_id=l2)
    today_items = db2.due_items(today="2026-09-28")
    check("**懒创建防线**：全新项全都进今日训练队列（没被内连接滤掉）",
          len(today_items) == 3
          and all(x["bucket"] == "new" for x in today_items),
          [x["bucket"] for x in today_items])
    check("due_count 只数已到期：全新项不算 due（另有 new_candidates）",
          db2.due_count(today="2026-09-28") == 0
          and len(db2.new_candidates()) == 3,
          (db2.due_count(today="2026-09-28"), len(db2.new_candidates())))
    check("stats['due'] 就是 due_count",
          db2.stats(today="2026-09-28")["due"]
          == db2.due_count(today="2026-09-28"))

    first = today_items[0]["id"]
    db2.record_review(first, tc.FEEDBACK_KNOWN, today="2026-09-28")
    check("排到明天的那条，当天就退出训练队列",
          len(db2.due_items(today="2026-09-28")) == 2
          and first not in [int(x["id"])
                            for x in db2.due_items(today="2026-09-28")],
          [x["front"] for x in db2.due_items(today="2026-09-28")])
    check("第二天它变成「到期」，due_count 才 +1",
          db2.due_count(today="2026-09-29") == 1
          and len(db2.due_items(today="2026-09-29")) == 3,
          (db2.due_count(today="2026-09-29"),
           len(db2.due_items(today="2026-09-29"))))
    check("new_candidates 只给从没排过期的",
          len(db2.new_candidates()) == 2, len(db2.new_candidates()))


# ══════════════════════════════════════════════════════════════════════════
# I. 打卡
# ══════════════════════════════════════════════════════════════════════════
def test_checkins() -> None:
    section("[I] 打卡统计")
    db = fresh("checkin")
    db.checkin("2026-09-28", minutes=30, items_new=5, items_reviewed=10,
               accuracy=0.8)
    row = db.get_checkin("2026-09-28")
    check("打卡字段齐全",
          {"check_date", "minutes", "items_new", "items_reviewed", "accuracy",
           "note"} <= set(row), sorted(row))

    db.checkin("2026-09-28", note="补一句")
    row = db.get_checkin("2026-09-28")
    check("同日重复打卡是**更新**不是新增",
          len(db.list_checkins()) == 1, len(db.list_checkins()))
    check("只传 note 时其余字段不被清零",
          int(row["minutes"]) == 30 and int(row["items_reviewed"]) == 10,
          row)
    check("note 写进去了", row["note"] == "补一句")

    for day in (26, 27):
        db.checkin(f"2026-09-{day:02d}", minutes=10)
    check("连续天数：26/27/28 三天",
          tc.streak_from_dates(db.checkin_dates(), "2026-09-28") == 3,
          db.checkin_dates())
    check("跨月连续：8/31 + 9/1 算 2 天",
          tc.streak_from_dates(["2026-08-31", "2026-09-01"], "2026-09-01") == 2)
    check("今天没打卡不算断（从昨天数起）",
          tc.streak_from_dates(["2026-09-26", "2026-09-27"], "2026-09-28") == 2)
    check("隔了一天就断",
          tc.streak_from_dates(["2026-09-25", "2026-09-27"], "2026-09-28") == 1)

    grid = tc.checkin_grid(db.checkin_dates(), today="2026-09-28", weeks=5)
    check("打卡日历 5 周 × 7 天", len(grid) == 5
          and all(len(r["cells"]) == 7 for r in grid), len(grid))
    check("**按周一对齐**：每行第一格是周一",
          all(r["cells"][0]["date"].weekday() == 0 for r in grid))
    check("打过卡的日子被标出来",
          any(c["checked"] for r in grid for c in r["cells"]))
    check("未来的日子被标成 future（不画数字）",
          any(c["is_future"] for r in grid for c in r["cells"]))
    check("今天被标出来", any(c["is_today"] for r in grid for c in r["cells"]))
    check("周标题是 一..日", tc.weekday_headers() == ("一", "二", "三", "四",
                                                    "五", "六", "日"))

    # autofill 按当天真实流水补全
    db2 = fresh("autofill")
    pid = db2.add_palace("路线")
    lid = db2.add_locus(pid, "桩")
    i1 = db2.add_item(front="A", palace_id=pid, locus_id=lid)
    i2 = db2.add_item(front="B", palace_id=pid, locus_id=lid)
    db2.record_review(i1, tc.FEEDBACK_KNOWN, today="2026-09-28")
    db2.record_review(i2, tc.FEEDBACK_FORGOT, today="2026-09-28")
    rec = db2.autofill_today(today="2026-09-28")
    check("autofill：复习 2 条、正确率 0.5",
          int(rec["items_reviewed"]) == 2
          and abs(float(rec["accuracy"]) - 0.5) < 1e-9, rec)
    check("autofill 不动 minutes（那是用户自己填的）",
          int(rec["minutes"]) == 0, rec["minutes"])
    rec2 = db2.autofill_today(today="2026-09-28")
    check("autofill 幂等（还是 1 行打卡、数字不变）",
          len(db2.list_checkins()) == 1
          and int(rec2["items_reviewed"]) == 2, rec2)

    stats = db2.stats(today="2026-09-28")
    check("stats 键齐全",
          {"days", "minutes", "items_new", "items_reviewed", "avg_minutes",
           "streak", "best_streak", "accuracy", "reviewed", "correct",
           "mastery", "items", "palaces", "due"} <= set(stats), sorted(stats))
    check("stats 的 items 与库一致", int(stats["items"]) == 2, stats["items"])


# ══════════════════════════════════════════════════════════════════════════
# J. 题库入库
# ══════════════════════════════════════════════════════════════════════════
def test_bank_import() -> None:
    section("[J] 题库 → 记忆项")
    db = fresh("bank")
    pid = db.import_number_pegs()
    check("数字桩宫殿有 100 个桩", len(db.list_loci(pid)) == 100,
          len(db.list_loci(pid)))
    check("数字桩宫殿可重复导入（幂等）",
          db.import_number_pegs() == pid and len(db.list_loci(pid)) == 100)

    # 模板码是 TPL_* 系列（见 memory_seed.PALACE_TEMPLATES）
    home_code = memory_seed.PALACE_TEMPLATES[0]["code"]
    tpl = db.import_template(home_code)
    loci = db.list_loci(tpl)
    check("按码导入模板", len(loci) >= 16, len(loci))
    check("同一模板重复导入返回同一个宫殿",
          db.import_template(home_code) == tpl)
    try:
        db.import_template("NOT_A_TPL")
        bad = False
    except KeyError:
        bad = True
    check("导入不存在的模板抛 KeyError", bad)

    bank_code = memory_seed.BANKS[0]["code"]
    bank = db.get_bank_by_code(bank_code)
    total = len(db.list_bank_items(bank["id"]))
    first = db.import_bank(bank_code, tpl)
    check("导入题库：新增条数 = 题量", first["created"] == total, first)
    check("导入的项挂在桩上（从 1 号桩开始）",
          all(int(x["locus_id"]) != 0
              for x in db.list_items(palace_id=tpl)),
          [(x["front"], x["locus_id"]) for x in db.list_items(palace_id=tpl)][:3])

    second = db.import_bank(bank_code, tpl)
    check("**重复导入幂等**：新增 0、跳过全部",
          second["created"] == 0 and second["skipped"] == total, second)
    check("重复导入后总数没变",
          db.count_items(palace_id=tpl) == total, db.count_items(palace_id=tpl))

    # 桩不够：多出来的挂到最后一个桩。
    # 注意 source_key 是 ``bank:<码>:<题号>`` —— **全库唯一、不带宫殿**，
    # 所以同一个题库在一座图书馆里只能入库一次；这里换个题库来验。
    bank2_code = memory_seed.BANKS[1]["code"]
    bank2 = db.get_bank_by_code(bank2_code)
    total2 = len(db.list_bank_items(bank2["id"]))
    small = db.add_palace("只有两个桩")
    s1 = db.add_locus(small, "一")
    s2 = db.add_locus(small, "二")
    db.import_bank(bank2_code, small)
    counts = db.item_counts_by_locus(small)
    check("桩不够时收尾挂到最后一个桩",
          counts.get(s1, 0) == 1 and counts.get(s2, 0) == total2 - 1,
          counts)
    dup = db.import_bank(bank2_code, tpl)
    check("同一题库换个宫殿再导：一条不新增（source_key 全库唯一）",
          dup["created"] == 0 and dup["skipped"] == total2, dup)

    # 不挂桩：只入库（再换一个题库，避开 source_key 冲突）
    bank3_code = memory_seed.BANKS[2]["code"]
    bank3 = db.get_bank_by_code(bank3_code)
    total3 = len(db.list_bank_items(bank3["id"]))
    loose = db.import_bank(bank3_code, 0)
    check("palace_id=0 时只入库不挂桩",
          loose["created"] == total3
          and all(int(x["locus_id"]) == 0
                  for x in db.list_items(unassigned=True)
                  if x["category"] == bank3["name"]),
          [x["locus_id"] for x in db.list_items(unassigned=True)][:3])
    check("导入的项带分类（题库名）",
          bank["name"] in db.categories(), db.categories())

    try:
        db.import_bank("不存在的题库")
        bad = False
    except KeyError:
        bad = True
    check("导入不存在的题库抛 KeyError", bad)


# ══════════════════════════════════════════════════════════════════════════
# K. 小工具
# ══════════════════════════════════════════════════════════════════════════
def test_helpers() -> None:
    section("[K] 小工具")
    db = fresh("helpers")
    cards = db.list_cards()
    check("教学卡可读且字段齐全",
          len(cards) >= 10
          and all({"code", "title", "category", "body", "practice", "tip"}
                  <= set(c) for c in cards), len(cards))
    check("get_card 按码可取", db.get_card(cards[0]["code"])["title"]
          == cards[0]["title"])
    check("get_card 找不到返回 None", db.get_card("nope") is None)
    check("card_categories 非空", len(db.card_categories()) > 0)

    # 基准量住在 training_core，不在 memory_seed
    check("suggest_new_count：队列干净就按基准量",
          memory_db.suggest_new_count(due_total=0) == tc.SUGGEST_NEW_PER_DAY,
          memory_db.suggest_new_count(due_total=0))
    check("suggest_new_count：到期越多加新越少（有下限、不归零）",
          [memory_db.suggest_new_count(due_total=x) for x in (0, 8, 24, 48)]
          == [tc.SUGGEST_NEW_PER_DAY, tc.SUGGEST_NEW_PER_DAY,
              tc.SUGGEST_NEW_PER_DAY // 2, tc.SUGGEST_NEW_PER_DAY // 4],
          [memory_db.suggest_new_count(due_total=x) for x in (0, 8, 24, 48)])
    # target_new 是「基准量」而不是硬钉值：待复习爆表时照样被压小
    check("suggest_new_count 的 target_new 是基准、不是硬钉值",
          memory_db.suggest_new_count(due_total=0, target_new=5) == 5
          and memory_db.suggest_new_count(due_total=999, target_new=5) == 1,
          (memory_db.suggest_new_count(due_total=0, target_new=5),
           memory_db.suggest_new_count(due_total=999, target_new=5)))

    check("split_tags 认 | , 、 ; 与空白",
          memory_db.split_tags("英语|食物, 水果、苹果 ; 名词") ==
          ["英语", "食物", "水果", "苹果", "名词"], memory_db.split_tags(
              "英语|食物, 水果、苹果 ; 名词"))
    check("split_tags 空串给空列表", memory_db.split_tags("") == [])
    check("split_tags 不把 / 当分隔符（那是路径）",
          memory_db.split_tags("a/b") == ["a/b"])

    row = {"front": "苹果", "back": "apple"}
    check("format_item_line 带答案", "苹果" in memory_db.format_item_line(row))
    check("format_item_line 缺字段不炸",
          memory_db.format_item_line({}) == "")


# ══════════════════════════════════════════════════════════════════════════
# L. 页面契约
# ══════════════════════════════════════════════════════════════════════════
def test_page_contracts() -> None:
    section("[L] 页面契约（memory_page 用到的每个数据入口）")
    db = fresh("contract")
    used = (
        "list_palaces get_palace add_palace update_palace delete_palace "
        "add_locus update_locus get_locus list_loci delete_locus move_locus "
        "reorder_loci import_all_templates import_number_pegs "
        "item_counts_by_locus add_item update_item get_item delete_item "
        "list_items count_items categories due_items due_count due_count "
        "walk_order record_review list_reviews mastery_distribution "
        "checkin checkin_dates autofill_today new_today stats "
        "list_banks get_bank list_bank_items get_bank_by_code import_bank "
        "list_cards get_card"
    ).split()
    missing = [name for name in used if not callable(getattr(db, name, None))]
    check("页面用到的数据入口都存在", not missing, missing)

    pid = db.import_template(memory_seed.PALACE_TEMPLATES[0]["code"])
    item = db.list_items(palace_id=pid)[0] if db.count_items(palace_id=pid) else None
    if item is None:
        # 挂到第一个桩上（模板宫殿有桩），这样下面的 station 检查不是空转
        first_locus = db.list_loci(pid)
        db.add_item(front="补一条", palace_id=pid,
                    locus_id=int(first_locus[0]["id"]) if first_locus else 0)
        item = db.list_items(palace_id=pid)[0]
    need = {"id", "palace_id", "locus_id", "front", "back", "imagery", "story",
            "category", "tags", "locus_name", "locus_seq", "palace_name",
            "mastery", "next_review_at", "due", "bucket"}
    check("记忆项行字段齐全", need <= set(item), sorted(need - set(item)))

    walk = db.walk_order(pid)
    check("walk_order 行带 station / locus_name / locus_hint",
          walk and {"station", "locus_name", "locus_hint"} <= set(walk[0]),
          sorted(walk[0]) if walk else "空")
    # 契约：挂了桩的 station = seq + 1（≥ 1）；没挂桩的才是 0。
    assigned = [r for r in walk if int(r["locus_id"] or 0)]
    loose = [r for r in walk if not int(r["locus_id"] or 0)]
    check("station：挂桩的 ≥ 1、未分配的 = 0",
          assigned and all(int(r["station"]) >= 1 for r in assigned)
          and all(int(r["station"]) == 0 for r in loose),
          ([(r["station"], r["locus_id"]) for r in walk][:5],
           len(assigned), len(loose)))

    palace = db.list_palaces()[0]
    check("宫殿行带 item_count", "item_count" in palace, sorted(palace))
    locus = db.list_loci(pid)[0]
    check("地点桩行带 seq / hint / name",
          {"id", "palace_id", "seq", "name", "hint"} <= set(locus),
          sorted(locus))
    card = db.list_cards()[0]
    check("教学卡行字段齐全",
          {"code", "title", "category", "body", "practice", "tip"} <= set(card),
          sorted(card))
    bank = db.list_banks()[0]
    check("题库行带 item_count", "item_count" in bank, sorted(bank))
    entry = db.list_bank_items(bank["id"])[0]
    check("题条目字段齐全",
          {"seq", "question", "answer", "hint"} <= set(entry), sorted(entry))


# ══════════════════════════════════════════════════════════════════════════
# M. 待办桥
# ══════════════════════════════════════════════════════════════════════════
def test_todo_bridge() -> None:
    section("[M] 训练 → 待办（记忆宫殿 / 思维导图共用一套规则）")
    d = Path(tempfile.mkdtemp(prefix="mem_todo_"))
    _TMP.append(d)
    todo = todo_db.TodoDB(d / "todo.db")
    bridge = ttb.TrainingTodoBridge(todo)

    payload = ttb.review_payload(kind=ttb.KIND_MEMORY, due=7, suggested=3,
                                today="2026-09-28")
    check("标题带上数量与单位", payload["title"] == "复习记忆宫殿 7 条",
          payload["title"])
    check("截止日期 = 今天", payload["due_date"] == "2026-09-28")
    check("备注里带建议新学量与入口路径",
          "建议 3 条" in payload["notes"] and "记忆宫殿" in payload["notes"],
          payload["notes"])

    empty = ttb.review_payload(kind=ttb.KIND_MEMORY, due=0, today="2026-09-28")
    check("队列为空时标题不带 0", empty["title"] == "复习记忆宫殿",
          empty["title"])
    check("队列为空时给出去哪找内容", "题库训练" in empty["notes"])

    mm = ttb.review_payload(kind=ttb.KIND_MINDMAP, due=3, today="2026-09-28")
    check("导图档走「盲画」措辞（不是「复习」）",
          mm["title"] == "盲画思维导图 3 张" and "待盲画 3 张" in mm["notes"],
          (mm["title"], mm["notes"]))

    hook = bridge.make_hook("memory")
    title, message = hook(due=7, suggested=3)
    check("hook 返回 (标题, 一句话)",
          title == "复习记忆宫殿 7 条" and "已" in message, (title, message))
    items = todo.fetch_items(scope="all")
    check("真的写进了待办", len(items) == 1, len(items))
    check("标签是记忆宫殿", list(items[0].tags) == ["记忆宫殿"], items[0].tags)
    check("**skip_holidays=0**：今天的事不许被顺延到工作日",
          int(getattr(items[0], "skip_holidays", 0)) == 0,
          getattr(items[0], "skip_holidays", None))

    title2, message2 = hook(due=7, suggested=3)
    check("**当天幂等**：连点两次不堆两条",
          len(todo.fetch_items(scope="all")) == 1 and "已经有一条" in message2,
          message2)

    hook_mm = bridge.make_hook("mindmap")
    hook_mm(due=3)
    mm_items = todo.fetch_items(scope="all")
    check("两个模块的待办各自独立（标题不同、标签不同）",
          len(mm_items) == 2
          and {str(i.title) for i in mm_items}
          == {"复习记忆宫殿 7 条", "盲画思维导图 3 张"}, len(mm_items))
    check("导图待办标签是思维导图",
          any(list(i.tags) == ["思维导图"] for i in mm_items),
          [list(i.tags) for i in mm_items])

    # 缺字段不建
    check("缺标题不建待办",
          bridge.create({"due_date": "2026-09-28"})["created"] is False)
    check("缺日期不建待办",
          bridge.create({"title": "x"})["created"] is False)
    check("缺字段时待办总数没变", len(todo.fetch_items(scope="all")) == 2)

    # 「做不到就多建一条，而不是把按钮废掉」
    class BrokenTodo:
        def fetch_items(self, **kw):
            raise RuntimeError("模拟读失败")

        def add_item(self, payload):
            return 4242

    broken = ttb.TrainingTodoBridge(BrokenTodo())
    result = broken.create(ttb.review_payload(kind=ttb.KIND_MEMORY, due=1))
    check("读待办失败时按「没有重复项」处理，照样建",
          result["created"] is True and result["item_id"] == 4242, result)


def main_test() -> None:
    test_core_matches_excel()
    test_seed_consistency()
    test_schema()
    test_palace_crud()
    test_loci()
    test_items()
    test_walk_order()
    test_srs()
    test_checkins()
    test_bank_import()
    test_helpers()
    test_page_contracts()
    test_todo_bridge()


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
