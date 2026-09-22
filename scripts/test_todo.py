# -*- coding: utf-8 -*-
"""待办 / 提醒事项模块回归测试（数据层 + 节假日引擎，纯逻辑、不碰 Tk）。

为什么单独成篇
------------------------------------------------------------------------------
todo_db.py 里最容易算错、又最不容易被肉眼发现的，是**日历推算**：
「周六顺延到下周一」「落在长假里的日期要跳到假期后第一个工作日」
「每天的重复项勾完要推进而不是消失」「逾期项每天早上自动顺延到今天」。
这些一旦算错，界面照样好看，只是日子全错，而且错得很安静。
所以这里把数据层每条规则逐一钉死，完全不看界面 —— 因此不依赖 tkinter，
用哪个解释器都能跑。

另一类被锁死的是「有意设计」而非「巧合」：
* 调休上班日算工作日（周日也要上班）
* 重复项勾选留快照、原条目推进（苹果的行为）
* 内置的调休上班日**不写名称**（界面上类型列已经写了「调休上班」）

覆盖：
A. 节假日引擎    is_workday / is_rest / shift_to_workday / next·prev_workday / holiday_name
B. 重复规则      next_occurrence（月末收敛、跳过休息日）/ advance_past（跨年一步到位）
C. 每日顺延      rollover（非重复移到今天 / 重复推进 / 幂等 / 已完成不动 / 今天休息）
D. 工作日弹窗    workday_notice（长假后第一个工作日弹、连续工作日不弹、同一天只弹一次）
E. 勾选语义      set_completed（done·undone / 重复留快照并推进 / 子任务快照 / 到期收尾）
F. 智能分组      count_by_scope / fetch_items 各视图 / open_count_by_list
I. 显示已完成    include_completed 在四个视图都生效 / 已完成沉底 / 偏好持久化
J. 到点提醒      alert_moment / pending_alerts（刚过点 vs 早已过点）/ 同一条不重复响 /
                 改时间·顺延·勾选都会让提醒记录作废 / 稍后提醒 / 老库自动补列
L. 提前提醒      alert_instants 两档排程（提前 / 到点）/ 只响最靠后那一档 / 两档各记各的账 /
                 提前档打盹不吃到点 / 关机一天只响到点档 / 跨日提前 / 老库裸时刻按到点认
K. 清单排序      reorder_lists（保序去重 / 缺漏接末尾 / 未知 id 忽略 / sort_order 连续）
G. 增删改查      清单 / 待办 / 子任务 / 标签 / 手工维护日历
H. 辅助函数      parse_day / day_str / add_months / add_years

用法：
    python scripts/test_todo.py
"""

import shutil
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from todo_db import (  # noqa: E402
    ADVANCE_CHOICES,
    ALERT_GRACE_MINUTES,
    ALERT_STAGE_DUE,
    ALERT_STAGE_EARLY,
    HOLIDAY_SEED,
    LIST_COLORS,
    LIST_ICONS,
    MAX_ADVANCE_MINUTES,
    SMART_LISTS,
    SNOOZE_MINUTES,
    TodoDB,
    add_months,
    add_years,
    advance_label,
    alert_instants,
    alert_moment,
    alert_stage_key,
    day_str,
    due_moment,
    moment_str,
    parse_alert_key,
    parse_day,
    parse_moment,
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


def fresh_db(name: str) -> TodoDB:
    """每个小节一个独立库：待办模块的用例大量依赖「初始状态」，共用会互相污染。"""
    d = Path(tempfile.mkdtemp(prefix="todo_test_"))
    _TMP.append(d)
    return TodoDB(d / f"{name}.db")


def lists_by_name(db: TodoDB) -> dict:
    return {l.name: l for l in db.fetch_lists()}


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


# ===========================================================================
# A. 节假日引擎
# ===========================================================================
def test_holidays() -> None:
    section("[A] 节假日引擎")
    db = fresh_db("holiday")

    spans, workdays = HOLIDAY_SEED[2026]
    check("内置 2026 放假 7 段", len(spans) == 7, f"实际 {len(spans)}")
    check("内置 2026 调休上班 6 天", len(workdays) == 6, f"实际 {len(workdays)}")
    check("日历表已写入 2026 记录", len(db.fetch_holidays(2026)) > 30,
          f"实际 {len(db.fetch_holidays(2026))}")

    # 法定放假 / 调休上班 / 普通周末 / 普通工作日，四类都要有
    cases = [
        ("2026-01-01", False, "元旦法定假"),
        ("2026-01-03", False, "元旦最后一天"),
        ("2026-01-04", True, "元旦调休上班（周日）"),
        ("2026-01-05", True, "节后第一个周一"),
        ("2026-01-10", False, "普通周六"),
        ("2026-02-14", True, "春节调休上班（周六）"),
        ("2026-02-15", False, "春节第一天"),
        ("2026-02-28", True, "春节调休上班（周六）"),
        ("2026-05-09", True, "劳动节调休上班（周六）"),
        ("2026-09-18", True, "普通周五"),
        ("2026-09-19", False, "普通周六"),
        ("2026-09-20", True, "中秋调休上班（周日）"),
        ("2026-09-25", False, "中秋第一天"),
        ("2026-09-27", False, "中秋最后一天"),
        ("2026-09-28", True, "节后第一个周一"),
        ("2026-10-01", False, "国庆第一天"),
        ("2026-10-07", False, "国庆最后一天"),
        ("2026-10-08", True, "节后第一个工作日"),
        ("2026-10-10", True, "国庆调休上班（周六）"),
    ]
    for day, expect, why in cases:
        got = db.is_workday(day)
        check(f"is_workday {day} = {expect}（{why}）", got is expect, f"实际 {got}")
    check("is_rest 与 is_workday 处处互斥",
          all(db.is_rest(d) is (not db.is_workday(d)) for d, _, _ in cases))

    # 顺延
    check("普通工作日原样返回", db.shift_to_workday("2026-09-18") == "2026-09-18")
    check("周六 → 次日（次日恰好是调休上班日）",
          db.shift_to_workday("2026-09-19") == "2026-09-20")
    check("中秋假最后一天 → 假期后第一个工作日",
          db.shift_to_workday("2026-09-27") == "2026-09-28")
    check("国庆第一天 → 10-08", db.shift_to_workday("2026-10-01") == "2026-10-08")
    check("调休的周六本身算工作日、不后移",
          db.shift_to_workday("2026-02-28") == "2026-02-28")
    check("空值安全", db.shift_to_workday("") == "")

    # 前后找工作日
    check("next_workday 含当天", db.next_workday("2026-09-19") == date(2026, 9, 20))
    check("next_workday 不含当天", db.next_workday("2026-09-19", include_self=False)
          == date(2026, 9, 20))
    check("prev_workday 含当天", db.prev_workday("2026-09-28") == date(2026, 9, 28))
    check("prev_workday 不含当天会跨过整个中秋假",
          db.prev_workday("2026-09-28", include_self=False) == date(2026, 9, 24))
    check("prev_workday 把调休的周日当工作日",
          db.prev_workday("2026-09-21", include_self=False) == date(2026, 9, 20))

    # 节日名
    check("节日名：春节", db.holiday_name("2026-02-17") == "春节")
    check("节日名：国庆节", db.holiday_name("2026-10-03") == "国庆节")
    check("普通周末 → 「周末」", db.holiday_name("2026-09-19") == "周末")
    check("普通工作日 → 空串", db.holiday_name("2026-09-18") == "")
    check("调休上班日没有节日名", db.holiday_name("2026-09-20") == "")

    db.close()


# ===========================================================================
# B. 重复规则
# ===========================================================================
def test_repeat_rules() -> None:
    section("[B] 重复规则")
    db = fresh_db("repeat")
    L = lists_by_name(db)["工作"].id

    check("rule=none 原样返回",
          db.next_occurrence("2026-09-18", rule="none") == "2026-09-18")

    for rule, src, want in [
        ("daily", "2026-09-18", "2026-09-19"),
        ("weekly", "2026-09-18", "2026-09-25"),
        ("biweekly", "2026-09-18", "2026-10-02"),
        ("monthly", "2026-09-18", "2026-10-18"),
        ("yearly", "2026-09-18", "2027-09-18"),
    ]:
        got = db.next_occurrence(src, rule=rule, skip_holidays=False)
        check(f"{rule}：{src} → {want}", got == want, f"实际 {got}")

    check("自定义 3 天",
          db.next_occurrence("2026-09-18", rule="custom", interval=3, unit="day",
                             skip_holidays=False) == "2026-09-21")
    check("自定义 2 个月",
          db.next_occurrence("2026-09-18", rule="custom", interval=2, unit="month",
                             skip_holidays=False) == "2026-11-18")

    # 月末收敛（不能抛异常，也不能滚到 3 月）
    check("1-31 + 1 个月 → 2-28",
          db.next_occurrence("2026-01-31", rule="monthly",
                             skip_holidays=False) == "2026-02-28")
    check("1-31 + 1 个月（跳过休息日）→ 2-28（当天是调休上班）",
          db.next_occurrence("2026-01-31", rule="monthly",
                             skip_holidays=True) == "2026-02-28")
    check("add_months 直接调用也收敛",
          add_months(date(2026, 1, 31), 1) == date(2026, 2, 28))
    check("add_years 闰日收敛",
          add_years(date(2024, 2, 29), 1) == date(2025, 2, 28))

    # 跳过休息日
    check("每天 + 跳过休息日：9-24 → 跨过中秋假到 9-28",
          db.next_occurrence("2026-09-24", rule="daily",
                             skip_holidays=True) == "2026-09-28")
    check("每周 + 跳过休息日：9-18 → 9-28",
          db.next_occurrence("2026-09-18", rule="weekly",
                             skip_holidays=True) == "2026-09-28")
    check("每周 + 不跳过：9-18 → 9-25",
          db.next_occurrence("2026-09-18", rule="weekly",
                             skip_holidays=False) == "2026-09-25")

    # advance_past：先除法跳再修正，跨一年也只是常数次迭代
    daily = db.get_item(db.add_item(
        {"list_id": L, "title": "每天的活", "due_date": "2026-01-01",
         "repeat_rule": "daily", "skip_holidays": 0}))
    check("advance_past 跨一年落到目标当天",
          db.advance_past("2026-01-01", daily, "2027-01-01") == "2027-01-01")
    check("advance_past 结果不早于目标",
          parse_day(db.advance_past("2026-01-01", daily, "2027-03-15"))
          >= date(2027, 3, 15))

    weekly = db.get_item(db.add_item(
        {"list_id": L, "title": "周报", "due_date": "2026-09-18",
         "repeat_rule": "weekly", "skip_holidays": 0}))
    check("advance_past 每周项落点仍是周五",
          db.advance_past("2026-09-18", weekly, "2026-11-01") == "2026-11-06")

    plain = db.get_item(db.add_item({"list_id": L, "title": "不重复的"}))
    check("advance_past 对 none 规则原样返回",
          db.advance_past("2026-01-01", plain, "2027-01-01") == "2026-01-01")

    db.close()


# ===========================================================================
# C. 每日顺延
# ===========================================================================
def test_rollover() -> None:
    section("[C] 每日顺延 rollover")
    db = fresh_db("rollover")
    L = lists_by_name(db)["工作"].id

    a = db.add_item({"list_id": L, "title": "逾期单次", "due_date": "2026-09-10",
                     "skip_holidays": 0})
    b = db.add_item({"list_id": L, "title": "逾期每天", "due_date": "2026-09-10",
                     "repeat_rule": "daily", "skip_holidays": 0})
    c = db.add_item({"list_id": L, "title": "未来单次", "due_date": "2026-12-01",
                     "skip_holidays": 0})
    d = db.add_item({"list_id": L, "title": "已完成的逾期", "due_date": "2026-09-10",
                     "skip_holidays": 0})
    db.set_completed(d, True)

    res = db.rollover(today="2026-09-18")
    check("非重复项顺延数 = 1", res["moved"] == 1, f"实际 {res}")
    check("重复项推进数 = 1", res["advanced"] == 1, f"实际 {res}")
    check("目标日 = 今天（工作日）", res["target"] == "2026-09-18", f"实际 {res}")
    check("只带走未完成的", res["carried"] == ["逾期单次"], f"实际 {res['carried']}")

    ia = db.get_item(a)
    check("单次逾期项日期改为今天", ia.due_date == "2026-09-18", f"实际 {ia.due_date}")
    check("顺延次数 +1", ia.rollover_count == 1, f"实际 {ia.rollover_count}")
    check("记下原始日期", ia.original_due_date == "2026-09-10",
          f"实际 {ia.original_due_date}")

    ib = db.get_item(b)
    check("重复项推进到今天（不再算逾期）", ib.due_date == "2026-09-18",
          f"实际 {ib.due_date}")
    check("重复项不累加顺延次数", ib.rollover_count == 0, f"实际 {ib.rollover_count}")

    check("未来项不动", db.get_item(c).due_date == "2026-12-01")
    check("已完成项不动", db.get_item(d).due_date == "2026-09-10")

    res2 = db.rollover(today="2026-09-18")
    check("再跑一次无事可做（幂等）",
          res2["moved"] == 0 and res2["advanced"] == 0, f"实际 {res2}")
    check("顺延次数没有被重复累加", db.get_item(a).rollover_count == 1)
    db.close()

    # 今天是休息日 → 顺延目标自动落到下一个工作日
    db2 = fresh_db("rollover_rest")
    L2 = lists_by_name(db2)["工作"].id
    e = db2.add_item({"list_id": L2, "title": "落在周六的顺延",
                      "due_date": "2026-09-15", "skip_holidays": 0})
    res3 = db2.rollover(today="2026-09-19")     # 周六
    check("今天休息时目标落到 9-20", res3["target"] == "2026-09-20", f"实际 {res3}")
    check("条目实际落到 9-20", db2.get_item(e).due_date == "2026-09-20",
          f"实际 {db2.get_item(e).due_date}")
    db2.close()


# ===========================================================================
# D. 假期后第一个工作日的弹窗
# ===========================================================================
def test_workday_notice() -> None:
    section("[D] 假期后第一个工作日的弹窗")
    db = fresh_db("notice")
    L = lists_by_name(db)["工作"].id

    check("普通周五不弹（昨天就是工作日）",
          db.workday_notice(today="2026-09-18") is None)
    check("休息日本身不弹", db.workday_notice(today="2026-09-19") is None)
    check("周日调休上班后紧接周一，不算「假期后第一天」",
          db.workday_notice(today="2026-09-21") is None)

    info = db.workday_notice(today="2026-09-28")
    check("中秋后第一个工作日要弹", info is not None)
    if info:
        check("认出刚结束的假期名", info["holiday_name"] == "中秋节", f"实际 {info}")
        check("休息天数 = 3", info["rest_days"] == 3, f"实际 {info}")
        check("上一个工作日 = 9-24", info["gap_from"] == "2026-09-24", f"实际 {info}")

    # 假期里攒下的活会体现在汇总里
    db.add_item({"list_id": L, "title": "假期攒下的活", "due_date": "2026-09-30",
                 "skip_holidays": 0})
    info2 = db.workday_notice(today="2026-10-08")
    check("国庆后第一个工作日要弹", info2 is not None)
    if info2:
        check("国庆休息天数 = 7", info2["rest_days"] == 7, f"实际 {info2}")
        check("假期名 = 国庆节", info2["holiday_name"] == "国庆节", f"实际 {info2}")
        check("汇总带上今天要办的条数", info2["today_count"] == 1, f"实际 {info2}")
        check("汇总带上条目名", info2["carried"] == ["假期攒下的活"], f"实际 {info2}")

    db.ack_workday_notice(today="2026-10-08")
    check("ack 之后同一天不再弹", db.workday_notice(today="2026-10-08") is None)
    check("换一天仍能弹（周末过后）", db.workday_notice(today="2026-10-12") is not None)
    db.close()


# ===========================================================================
# E. 勾选语义
# ===========================================================================
def test_complete() -> None:
    section("[E] 勾选语义")
    db = fresh_db("complete")
    L = lists_by_name(db)["工作"].id

    one = db.add_item({"list_id": L, "title": "单次待办", "due_date": "2026-09-18",
                       "skip_holidays": 0})
    check("单次项勾选 → done", db.set_completed(one, True)["action"] == "done")
    it = db.get_item(one)
    check("completed 置 1", it.completed == 1)
    check("写了完成时间", bool(it.completed_at))
    check("取消勾选 → undone", db.set_completed(one, False)["action"] == "undone")
    check("取消后 completed 归 0", db.get_item(one).completed == 0)
    check("取消后清掉完成时间", db.get_item(one).completed_at == "")

    # 重复项：留快照 + 推进原条目（苹果的行为）
    rep = db.add_item({"list_id": L, "title": "每天站会", "due_date": "2026-09-18",
                       "repeat_rule": "daily", "skip_holidays": 0})
    db.add_subtask(rep, "看板")
    db.add_subtask(rep, "记录")
    r = db.set_completed(rep, True)
    check("重复项勾选 → spawn", r["action"] == "spawn", f"实际 {r}")
    check("返回下一次日期", r["next_due"] == "2026-09-19", f"实际 {r}")

    orig = db.get_item(rep)
    check("原条目仍然存在", orig is not None)
    check("原条目仍未完成", orig.completed == 0)
    check("原条目日期已推进", orig.due_date == "2026-09-19", f"实际 {orig.due_date}")

    done = db.fetch_items(scope="completed")
    check("已完成区出现一条快照",
          [c.title for c in done].count("每天站会") == 1,
          f"实际 {[c.title for c in done]}")
    snap = [c for c in done if c.title == "每天站会"][0]
    check("快照标记 is_repeat_copy", snap.is_repeat_copy == 1)
    check("快照日期 = 完成当次那天", snap.due_date == "2026-09-18",
          f"实际 {snap.due_date}")
    check("快照带走了子任务",
          len(db.fetch_subtasks(snap.id)) == 2, f"实际 {len(db.fetch_subtasks(snap.id))}")
    check("原条目的子任务被标记完成",
          all(s.completed == 1 for s in db.fetch_subtasks(rep)))

    # 重复到 repeat_until 之后：不允许留一个永远推不动的空壳
    end = db.add_item({"list_id": L, "title": "只剩这一次", "due_date": "2026-09-18",
                       "repeat_rule": "daily", "repeat_until": "2026-09-18",
                       "skip_holidays": 0})
    r4 = db.set_completed(end, True)
    check("到期后勾选仍留一条快照", r4["action"] == "spawn", f"实际 {r4}")
    check("到期后 next_due 为空", r4["next_due"] == "", f"实际 {r4}")
    check("到期后原条目收尾为已完成", db.get_item(end).completed == 1)

    check("对不存在的 id 勾选是 noop",
          db.set_completed(999999, True)["action"] == "noop")
    db.close()


# ===========================================================================
# F. 智能分组与列表过滤
# ===========================================================================
def test_scopes() -> None:
    section("[F] 智能分组与列表过滤")
    db = fresh_db("scopes")
    L = lists_by_name(db)
    W, LI, R = L["工作"].id, L["生活"].id, L["提醒事项"].id
    TODAY = "2026-09-18"

    db.add_item({"list_id": W, "title": "今天要交", "due_date": TODAY,
                 "skip_holidays": 0})
    db.add_item({"list_id": W, "title": "已经逾期", "due_date": "2026-09-10",
                 "skip_holidays": 0})
    i3 = db.add_item({"list_id": LI, "title": "下周的事", "due_date": "2026-09-25",
                      "skip_holidays": 0})
    i4 = db.add_item({"list_id": R, "title": "没日期的草稿"})
    db.add_item({"list_id": LI, "title": "打旗标的", "due_date": "2026-09-30",
                 "skip_holidays": 0, "flagged": True})
    i6 = db.add_item({"list_id": W, "title": "干完了的", "due_date": "2026-09-11",
                      "skip_holidays": 0})
    db.set_completed(i6, True)

    def titles(**kw):
        return [it.title for it in db.fetch_items(today=TODAY, **kw)]

    cnt = db.count_by_scope(today=TODAY)
    check("今天计数 = 2", cnt["today"] == 2, f"实际 {cnt}")
    # 「今天要交」虽然今天到期，但它同样设了日期，所以也算在「计划」里
    check("计划计数 = 4", cnt["scheduled"] == 4, f"实际 {cnt}")
    check("全部未完成 = 5", cnt["all"] == 5, f"实际 {cnt}")
    check("旗标 = 1", cnt["flagged"] == 1, f"实际 {cnt}")
    check("已完成 = 1", cnt["completed"] == 1, f"实际 {cnt}")

    check("今天视图含逾期项",
          set(titles(scope="today")) == {"今天要交", "已经逾期"},
          f"实际 {titles(scope='today')}")
    check("今天视图按日期升序", titles(scope="today")[0] == "已经逾期",
          f"实际 {titles(scope='today')}")
    check("计划视图 = 所有设了日期的未完成",
          set(titles(scope="scheduled")) == {"已经逾期", "今天要交", "下周的事", "打旗标的"},
          f"实际 {titles(scope='scheduled')}")
    check("全部视图 = 5 条未完成", len(titles(scope="all")) == 5,
          f"实际 {titles(scope='all')}")
    check("没日期的排在最后", titles(scope="all")[-1] == "没日期的草稿",
          f"实际 {titles(scope='all')}")
    check("旗标视图", titles(scope="flagged") == ["打旗标的"],
          f"实际 {titles(scope='flagged')}")
    check("已完成视图", titles(scope="completed") == ["干完了的"],
          f"实际 {titles(scope='completed')}")
    check("清单视图只出该清单",
          set(titles(scope="list", list_id=W)) == {"今天要交", "已经逾期"},
          f"实际 {titles(scope='list', list_id=W)}")

    # 搜索命中标题 / 备注 / 标签三处
    check("搜索命中标题", titles(scope="all", keyword="周") == ["下周的事"],
          f"实际 {titles(scope='all', keyword='周')}")
    db.update_item(i4, {"notes": "参考去年的模板"})
    check("搜索命中备注", titles(scope="all", keyword="模板") == ["没日期的草稿"],
          f"实际 {titles(scope='all', keyword='模板')}")
    db.update_item(i3, {"tags": ["季度", "报告"]})
    check("搜索命中标签", titles(scope="all", keyword="季度") == ["下周的事"],
          f"实际 {titles(scope='all', keyword='季度')}")
    check("搜不到就是空", titles(scope="all", keyword="不存在的词") == [])

    per = db.open_count_by_list()
    check("工作清单未完成 = 2", per.get(W) == 2, f"实际 {per}")
    check("生活清单未完成 = 2", per.get(LI) == 2, f"实际 {per}")
    check("提醒事项未完成 = 1", per.get(R) == 1, f"实际 {per}")
    check("各清单之和 = 全部未完成", sum(per.values()) == 5, f"实际 {per}")
    # 逾期数（侧栏角标上色用）：数据里有「已经逾期」这一条
    overdue = db.count_by_scope(today=TODAY)["overdue"]
    check("逾期计数 = 1（只有「已经逾期」那条）", overdue == 1, f"实际 {overdue}")
    check("按清单的逾期数之和 = 总逾期",
          sum(db.overdue_count_by_list(today=TODAY).values()) == overdue,
          f"实际 {db.overdue_count_by_list(today=TODAY)}")
    db.close()


# ===========================================================================
# I. 显示已完成
# ===========================================================================
def test_show_completed() -> None:
    section("[I] 显示已完成（include_completed / 沉底排序 / 偏好持久化）")
    db = fresh_db("showdone")
    L = lists_by_name(db)
    W, LI = L["工作"].id, L["生活"].id
    TODAY = "2026-09-18"

    db.add_item({"list_id": W, "title": "今天要交", "due_date": TODAY,
                 "skip_holidays": 0})
    done_today = db.add_item({"list_id": W, "title": "早上已经交掉的",
                              "due_date": TODAY, "skip_holidays": 0})
    db.add_item({"list_id": W, "title": "下周的", "due_date": "2026-09-25",
                 "skip_holidays": 0})
    db.add_item({"list_id": LI, "title": "打旗标的", "due_date": "2026-09-30",
                 "skip_holidays": 0, "flagged": True})
    # 已完成的也打了旗标：用来验证不靠「未完成」之外的第二个条件去过滤
    done_old = db.add_item({"list_id": LI, "title": "上周就做完了",
                            "due_date": "2026-09-09", "flagged": True,
                            "skip_holidays": 0})
    db.set_completed(done_today, True)
    db.set_completed(done_old, True)

    def titles(**kw):
        return [it.title for it in db.fetch_items(today=TODAY, **kw)]

    # —— 缺省：开关关着，四个视图都不该漏出已完成项 ——
    check("缺省「今天」不含已完成",
          titles(scope="today") == ["今天要交"], f"实际 {titles(scope='today')}")
    check("缺省「计划」不含已完成",
          titles(scope="scheduled") == ["今天要交", "下周的", "打旗标的"],
          f"实际 {titles(scope='scheduled')}")
    check("缺省「全部」不含已完成",
          set(titles(scope="all")) == {"今天要交", "下周的", "打旗标的"},
          f"实际 {titles(scope='all')}")
    check("缺省「清单」不含已完成",
          titles(scope="list", list_id=W) == ["今天要交", "下周的"],
          f"实际 {titles(scope='list', list_id=W)}")

    # —— 打开开关：智能分组也要能带上已完成项 ——
    # （原先把 completed = 0 写死在 today/scheduled/flagged 三个分支里，
    #   于是开关只在「全部 / 清单」两个视图生效，这是修掉的那个 bug。）
    check("「今天」连带已完成",
          titles(scope="today", include_completed=True)
          == ["今天要交", "上周就做完了", "早上已经交掉的"],
          f"实际 {titles(scope='today', include_completed=True)}")
    check("「计划」连带已完成",
          titles(scope="scheduled", include_completed=True)
          == ["今天要交", "下周的", "打旗标的", "上周就做完了", "早上已经交掉的"],
          f"实际 {titles(scope='scheduled', include_completed=True)}")
    check("「旗标」连带已完成",
          [t for t in titles(scope="flagged", include_completed=True)]
          == ["打旗标的", "上周就做完了"],
          f"实际 {titles(scope='flagged', include_completed=True)}")
    check("「清单」连带已完成",
          set(titles(scope="list", list_id=W, include_completed=True))
          == {"今天要交", "早上已经交掉的", "下周的"},
          f"实际 {titles(scope='list', list_id=W, include_completed=True)}")

    # —— 排序：已完成一律沉底，同一档内仍按日期 ——
    check("已完成的沉在最后（未完成在前、已完成垫底）",
          titles(scope="all", include_completed=True)
          == ["今天要交", "下周的", "打旗标的", "上周就做完了", "早上已经交掉的"],
          f"实际 {titles(scope='all', include_completed=True)}")
    check("沉底后未完成之间仍按日期升序",
          titles(scope="all", include_completed=True)[:3]
          == ["今天要交", "下周的", "打旗标的"],
          f"实际 {titles(scope='all', include_completed=True)}")
    check("已完成那一档内部也按日期升序",
          titles(scope="all", include_completed=True)[-2:]
          == ["上周就做完了", "早上已经交掉的"],
          f"实际 {titles(scope='all', include_completed=True)}")

    # —— 「已完成」视图本来就是只看已完成，开关不该影响它 ——
    check("「已完成」视图不受开关影响（开着）",
          set(titles(scope="completed", include_completed=True))
          == {"早上已经交掉的", "上周就做完了"},
          f"实际 {titles(scope='completed', include_completed=True)}")
    check("「已完成」视图不受开关影响（关着）",
          set(titles(scope="completed", include_completed=False))
          == {"早上已经交掉的", "上周就做完了"},
          f"实际 {titles(scope='completed', include_completed=False)}")

    # —— 搜索与完成的组合：关键词要能搜到已完成项 ——
    check("开着开关时关键词能搜到已完成项",
          titles(scope="all", keyword="早上", include_completed=True)
          == ["早上已经交掉的"],
          f"实际 {titles(scope='all', keyword='早上', include_completed=True)}")

    # —— 开关状态本身：存得进、读得出、缺省是关 ——
    check("开关缺省是关", db.get_state("show_completed", "0") == "0",
          repr(db.get_state("show_completed", "0")))
    db.set_state("show_completed", "1")
    check("开关写得进 todo_state", db.get_state("show_completed") == "1",
          repr(db.get_state("show_completed")))
    path = db.db_path
    db.close()

    # 重开一个连接读同一份库：偏好要还在（界面就是靠这个记住的）
    again = TodoDB(path)
    check("重开库后开关仍是开", again.get_state("show_completed") == "1",
          repr(again.get_state("show_completed")))
    again.close()


# ===========================================================================
# G. 增删改查
# ===========================================================================
def test_crud() -> None:
    section("[G] 增删改查（清单 / 待办 / 子任务 / 标签 / 日历）")
    db = fresh_db("crud")

    names = [l.name for l in db.fetch_lists()]
    check("首次运行自动建三个演示清单",
          names == ["提醒事项", "工作", "生活"], f"实际 {names}")
    check("演示清单的配色与图标都在可选集内",
          all(l.color in {v for _, v in LIST_COLORS} and l.icon in LIST_ICONS
              for l in db.fetch_lists()),
          f"实际 {[(l.name, l.color, l.icon) for l in db.fetch_lists()]}")

    lid = db.add_list("读书", "#AF52DE", "book")
    check("清单追加在末尾", db.fetch_lists()[-1].id == lid)
    db.update_list(lid, color="#5856D6", icon="star")
    got = db.get_list(lid)
    check("新建清单可改色改图标",
          got.color == "#5856D6" and got.icon == "star", f"实际 {got}")
    check("清单名留空时给默认名",
          db.get_list(db.add_list("   ")).name == "新列表")

    it = db.add_item({"list_id": lid, "title": "《设计模式》第 3 章",
                      "notes": "记得做笔记", "due_date": "2026-09-18",
                      "due_time": "20:00", "priority": 2, "tags": ["书"],
                      "skip_holidays": 0})
    got = db.get_item(it)
    check("新增待办字段完整落库",
          got.notes == "记得做笔记" and got.due_time == "20:00"
          and got.priority == 2 and got.tags == ["书"], f"实际 {got}")
    check("优先级标记 !!", got.priority_mark == "!!", f"实际 {got.priority_mark}")
    check("重复规则文字 = 永不", got.repeat_label == "永不")

    db.update_item(it, {"title": "改过的标题", "priority": 3})
    got = db.get_item(it)
    check("按需更新只改传入的键",
          got.title == "改过的标题" and got.priority == 3 and got.notes == "记得做笔记",
          f"实际 {got}")
    check("优先级标记 !!!", got.priority_mark == "!!!")
    check("未传的键确实没动（日期还在）", got.due_date == "2026-09-18")

    check("切旗标 0→1", db.toggle_flag(it) == 1)
    check("切旗标 1→0", db.toggle_flag(it) == 0)

    s1 = db.add_subtask(it, "读完 3.1")
    s2 = db.add_subtask(it, "读完 3.2")
    db.set_subtask_completed(s1, True)
    check("子任务数 = 2", len(db.fetch_subtasks(it)) == 2)
    check("子任务进度 = (1, 2)", db.subtask_summary([it])[it] == (1, 2),
          f"实际 {db.subtask_summary([it])}")
    check("空列表不做多余查询", db.subtask_summary([]) == {})
    db.delete_subtask(s2)
    check("删除子任务后 = (1, 1)", db.subtask_summary([it])[it] == (1, 1),
          f"实际 {db.subtask_summary([it])}")

    db.update_item(it, {"tags": ["书", "技术"]})
    check("全库标签去重排序", db.all_tags() == ["书", "技术"], f"实际 {db.all_tags()}")

    deleted = db.delete_list(lid)
    check("删除清单返回 (待办数, 子任务数)", deleted == (1, 1), f"实际 {deleted}")
    check("清单下的待办一并删除", db.get_item(it) is None)
    check("清单本身已删除", db.get_list(lid) is None)
    db.close()

    # 只剩一个清单时拒绝删除
    d2 = fresh_db("crud_one")
    only = d2.fetch_lists()[0]
    d2.delete_list(d2.fetch_lists()[1].id)
    d2.delete_list(d2.fetch_lists()[1].id)
    check("只剩一个清单时拒绝删除", d2.delete_list(only.id) == (0, 0),
          f"实际 {[l.name for l in d2.fetch_lists()]}")
    d2.close()

    # 手工维护日历
    d3 = fresh_db("crud_cal")
    seeded = d3.fetch_holidays(2026)
    wd_rows = [h for h in seeded if h.kind == "workday"]
    check("内置调休上班共 6 天", len(wd_rows) == 6, f"实际 {len(wd_rows)}")
    check("内置调休上班不写名称（类型列已说明）",
          all(h.name == "" for h in wd_rows),
          f"实际 {[(h.day, h.name) for h in wd_rows]}")

    check("2026-07-06 是普通工作日", d3.is_workday("2026-07-06") is True)
    d3.set_holiday("2026-07-06", "公司额外假", "holiday")
    check("手工设为放假后变成休息日", d3.is_workday("2026-07-06") is False)
    check("手工假期能取到名字", d3.holiday_name("2026-07-06") == "公司额外假")
    d3.delete_holiday("2026-07-06")
    check("删掉后回到按星期判断", d3.is_workday("2026-07-06") is True)

    d3.set_holiday("2026-07-11", "", "workday")
    check("周末可手工设为调休上班", d3.is_workday("2026-07-11") is True)
    check("调休上班日名称留空", d3.holiday_name("2026-07-11") == "")

    d3.set_holiday("2026-07-06", "第一次", "holiday")
    d3.set_holiday("2026-07-06", "改过名", "workday")
    check("同一天重复写入是覆盖而非报错",
          d3.holiday_name("2026-07-06") == "改过名"
          and d3.is_workday("2026-07-06") is True)

    try:
        d3.set_holiday("2026-07-12", "x", "nonsense")
        check("非法 kind 必须报错", False, "没有抛 ValueError")
    except ValueError:
        check("非法 kind 必须报错", True)
    d3.close()


# ===========================================================================
# H. 辅助函数
# ===========================================================================
def test_helpers() -> None:
    section("[H] 辅助函数与模块常量")
    check("parse_day 合法日期", parse_day("2026-09-18") == date(2026, 9, 18))
    check("parse_day 带时间戳也认", parse_day("2026-09-18 20:00") == date(2026, 9, 18))
    check("parse_day 空值 → None", parse_day("") is None)
    check("parse_day 非法文本 → None", parse_day("不是日期") is None)
    check("day_str 往返一致", day_str(date(2026, 9, 18)) == "2026-09-18")
    check("智能分组共 5 项", len(SMART_LISTS) == 5, f"实际 {SMART_LISTS}")
    check("配色共 12 种且都是 #RRGGBB",
          len(LIST_COLORS) == 12 and all(
              len(c) == 7 and c.startswith("#") for _, c in LIST_COLORS))
    check("图标共 20 个且无重复",
          len(LIST_ICONS) == 20 and len(set(LIST_ICONS)) == 20)


def test_alerts() -> None:
    section("[J] 到点提醒（时刻推算 / 该响不该响 / 稍后提醒 / 记录作废）")
    TODAY = "2026-09-18"

    # —— 纯函数 ——
    check("parse_moment 常规", parse_moment("2026-09-18 14:30")
          == datetime(2026, 9, 18, 14, 30))
    # 不走 strptime 就是为了这个：'9:05' 这种非零填充小时在有些平台解析不出来
    check("parse_moment 认单数字小时", parse_moment("2026-09-18 9:05")
          == datetime(2026, 9, 18, 9, 5))
    check("parse_moment 吃掉秒", parse_moment("2026-09-18 14:30:59")
          == datetime(2026, 9, 18, 14, 30))
    check("parse_moment 认 ISO 的 T", parse_moment("2026-09-18T14:30")
          == datetime(2026, 9, 18, 14, 30))
    check("parse_moment 只有日期 → None", parse_moment("2026-09-18") is None)
    check("parse_moment 空 → None", parse_moment("") is None)
    check("parse_moment 小时越界 → None", parse_moment("2026-09-18 25:00") is None)
    check("parse_moment 分钟越界 → None", parse_moment("2026-09-18 10:99") is None)
    check("moment_str 往返", parse_moment(moment_str(datetime(2026, 9, 18, 8, 5)))
          == datetime(2026, 9, 18, 8, 5))
    check("moment_str 补零", moment_str(datetime(2026, 9, 18, 8, 5))
          == "2026-09-18 08:05")

    db = fresh_db("alerts")
    L = lists_by_name(db)
    W, LI = L["工作"].id, L["生活"].id
    at = datetime(2026, 9, 18, 14, 0)

    def add(**kw):
        payload = {"list_id": W, "title": "T", "due_date": TODAY,
                   "due_time": "14:00", "skip_holidays": 0}
        payload.update(kw)
        return db.add_item(payload)

    a = add(title="到点的")
    check("alert_moment 拼出时刻", alert_moment(db.get_item(a)) == at)
    check("只设日期不参与提醒",
          alert_moment(db.get_item(add(title="没时间", due_time=""))) is None)
    check("只设时间不参与提醒",
          alert_moment(db.get_item(add(title="没日期", due_date=""))) is None)

    # —— 该响 / 不该响 ——
    r = db.pending_alerts(at)
    check("刚过点进 due", [i.id for i in r["due"]] == [a],
          f"实际 {[i.id for i in r['due']]}")
    check("刚过点不带 missed", not r["missed"])
    # 记账串带上档位：只存裸时刻的话，提前那一档记完账，到点那一档
    # 会被当成「已经响过」而永远不响
    check("moments 是带档位的记账串", r["moments"] == {a: "due|2026-09-18 14:00"},
          f"实际 {r['moments']}")
    check("stages 标出这一档是「到点」", r["stages"] == {a: ALERT_STAGE_DUE},
          f"实际 {r['stages']}")
    check("差一分钟还不到点",
          not db.pending_alerts(at - timedelta(minutes=1))["due"])
    tomorrow = add(title="明天的", due_date="2026-09-19")
    check("未来日期不参与提醒",
          tomorrow not in db.pending_alerts(at)["moments"])

    # —— 响过就不再响 ——
    db.mark_alerted(r["moments"])
    check("记账落库（带档位）", db.get_item(a).alerted_for == "due|2026-09-18 14:00")
    check("同一轮不再挑出来", not db.pending_alerts(at)["due"])
    check("过一会儿也不重复", not db.pending_alerts(at + timedelta(minutes=5))["due"])

    # —— 刚过点 vs 早已过点 ——
    db.update_item(a, {"due_time": "09:00"})
    check("改时间让提醒记录作废", db.get_item(a).alerted_for == "")
    late = datetime(2026, 9, 18, 12, 0)          # 晚了 3 小时
    check("超出宽限归 missed",
          [i.id for i in db.pending_alerts(late)["missed"]] == [a])
    check("超出宽限不进 due", not db.pending_alerts(late)["due"])
    near = datetime(2026, 9, 18, 9, 30)          # 晚了 30 分钟，在宽限内
    check("宽限之内仍弹窗",
          [i.id for i in db.pending_alerts(near)["due"]] == [a]
          and not db.pending_alerts(near)["missed"])
    check("宽限是 60 分钟", ALERT_GRACE_MINUTES == 60)
    check("正好卡在宽限边上仍算 due",
          bool(db.pending_alerts(datetime(2026, 9, 18, 10, 0))["due"]))

    # —— 稍后提醒 ——
    nxt = db.snooze(a, SNOOZE_MINUTES, now=near)
    check("snooze 返回时刻", nxt == "2026-09-18 09:40", nxt)
    check("snooze 落库", db.get_item(a).snooze_until == "2026-09-18 09:40")
    check("打盹时刻覆盖原定时点",
          alert_moment(db.get_item(a)) == datetime(2026, 9, 18, 9, 40))
    check("打盹未到不响",
          not db.pending_alerts(datetime(2026, 9, 18, 9, 35))["due"])
    woke = db.pending_alerts(datetime(2026, 9, 18, 9, 40))
    check("打盹到点重新响", [i.id for i in woke["due"]] == [a],
          f"实际 {[i.id for i in woke['due']]}")
    db.mark_alerted(woke["moments"])
    check("打盹响过再不响",
          not db.pending_alerts(datetime(2026, 9, 18, 9, 41))["due"])
    check("默认打盹 10 分钟", SNOOZE_MINUTES == 10)

    # 逾期很久才按「稍后提醒」：必须从当刻起算，否则推后 10 分钟仍在过去，
    # 下次巡检判成 missed，这条就再也弹不出来了
    db.update_item(a, {"due_time": "09:00"})
    evening = datetime(2026, 9, 18, 18, 0)
    check("逾期后从当刻起算",
          db.snooze(a, 10, now=evening) == "2026-09-18 18:10")
    check("逾期后打盹到点能再响",
          [i.id for i in db.pending_alerts(evening + timedelta(minutes=10))["due"]]
          == [a])

    # —— 勾选与提醒记录的联动 ——
    db.set_completed(a, True)
    check("已完成的提醒不再响",
          not db.pending_alerts(datetime(2026, 9, 18, 18, 20))["due"])
    db.set_completed(a, False)
    check("取消完成清掉打盹", db.get_item(a).snooze_until == "")
    check("取消完成后重新参与判定",
          [i.id for i in db.pending_alerts(
              datetime(2026, 9, 18, 18, 20))["missed"]] == [a])

    # —— 顺延与重复推进都要清掉提醒记录 ——
    moved = add(title="逾期两天", due_date="2026-09-16", skip_holidays=0)
    db.mark_alerted({moved: "due|2026-09-16 14:00"})
    db.rollover(today=TODAY)
    # 不写死「等于 TODAY」：顺延的目标是「今天或今天之后的第一个工作日」，
    # 恰好落在假期就会再往后挪一格 —— 那是正确行为，写死只会假红
    check("顺延后日期确实变了", db.get_item(moved).due_date != "2026-09-16")
    check("顺延让提醒记录作废", db.get_item(moved).alerted_for == "")

    daily = add(title="每天的", due_time="09:00", repeat_rule="daily")
    db.mark_alerted({daily: "due|2026-09-18 09:00"})
    db.set_completed(daily, True, today=TODAY)
    check("重复项勾完推进到下一周期", db.get_item(daily).due_date != TODAY)
    check("重复项推进让提醒记录作废", db.get_item(daily).alerted_for == "")

    # —— 快照与其它清单 ——
    snap = add(title="快照", list_id=LI)
    db.conn.execute("UPDATE todo_items SET completed = 1, is_repeat_copy = 1 "
                    "WHERE id = ?", (snap,))
    db.conn.commit()
    check("已完成快照不参与提醒",
          snap not in db.pending_alerts(at + timedelta(minutes=1))["moments"])

    # —— 老库自动补列（SQLite 没有 ADD COLUMN IF NOT EXISTS）——
    legacy_dir = Path(tempfile.mkdtemp(prefix="todo_legacy_"))
    _TMP.append(legacy_dir)
    legacy = legacy_dir / "old.db"
    conn = sqlite3.connect(str(legacy))
    conn.execute(
        """CREATE TABLE todo_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, list_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            due_date TEXT NOT NULL DEFAULT '', due_time TEXT NOT NULL DEFAULT '',
            repeat_rule TEXT NOT NULL DEFAULT 'none',
            repeat_interval INTEGER NOT NULL DEFAULT 1,
            repeat_unit TEXT NOT NULL DEFAULT 'week',
            repeat_until TEXT NOT NULL DEFAULT '',
            skip_holidays INTEGER NOT NULL DEFAULT 1,
            priority INTEGER NOT NULL DEFAULT 0,
            flagged INTEGER NOT NULL DEFAULT 0, tags TEXT NOT NULL DEFAULT '[]',
            completed INTEGER NOT NULL DEFAULT 0, completed_at TEXT NOT NULL DEFAULT '',
            is_repeat_copy INTEGER NOT NULL DEFAULT 0,
            rollover_count INTEGER NOT NULL DEFAULT 0,
            original_due_date TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.execute("INSERT INTO todo_items (list_id, title, created_at, updated_at) "
                 "VALUES (1, '老条目', '2020-01-01', '2020-01-01')")
    conn.commit()
    conn.close()

    old_db = TodoDB(legacy)
    columns = {r["name"] for r in old_db.conn.execute("PRAGMA table_info(todo_items)")}
    check("老库补上了 alerted_for", "alerted_for" in columns)
    check("老库补上了 snooze_until", "snooze_until" in columns)
    check("老库补上了 advance_minutes", "advance_minutes" in columns)
    check("老库的数据还在", old_db.conn.execute(
        "SELECT COUNT(1) FROM todo_items").fetchone()[0] == 1)
    check("老条目能读出来且提醒字段为空",
          old_db.get_item(1).alerted_for == "" and old_db.get_item(1).snooze_until == "")
    check("老条目的提前量缺省为 0", old_db.get_item(1).advance_minutes == 0,
          old_db.get_item(1).advance_minutes)
    TodoDB(legacy)   # 列已存在，二次打开不该报错
    check("二次打开老库不报错", True)


# ===========================================================================
# L. 提前提醒（提前 N 分钟 / 两档各记各的账）
# ===========================================================================
def test_advance_alerts() -> None:
    section("[L] 提前提醒（两档排程 / 只响最靠后档 / 提前档打盹）")
    TODAY = "2026-09-18"
    at = datetime(2026, 9, 18, 14, 0)

    # —— 纯函数：提前量的说法 ——
    check("提前 0 分钟就是「无」", advance_label(0) == "无", advance_label(0))
    check("提前 30 分钟的说法", advance_label(30) == "提前 30 分钟", advance_label(30))
    check("提前 1440 分钟说成 1 天", advance_label(1440) == "提前 1 天",
          advance_label(1440))
    check("认不出的提前量退回「无」", advance_label(7) == "无", advance_label(7))
    check("空值也算「无」", advance_label(None) == "无", advance_label(None))
    check("选项第一项是不提前", ADVANCE_CHOICES[0] == (0, "无"),
          f"实际 {ADVANCE_CHOICES[0]}")
    check("最大提前量 = 1 天", MAX_ADVANCE_MINUTES == 1440, MAX_ADVANCE_MINUTES)
    check("每个选项都是 (分钟, 说法) 且分钟数互不相同",
          len({m for m, _ in ADVANCE_CHOICES}) == len(ADVANCE_CHOICES)
          and all(isinstance(m, int) and isinstance(s, str)
                  for m, s in ADVANCE_CHOICES),
          f"实际 {ADVANCE_CHOICES}")

    # —— 记账串 ——
    check("记账串带档位", alert_stage_key(ALERT_STAGE_EARLY, at)
          == "early|2026-09-18 14:00", alert_stage_key(ALERT_STAGE_EARLY, at))
    check("拆开提前档", parse_alert_key("early|2026-09-18 14:00")
          == (ALERT_STAGE_EARLY, "2026-09-18 14:00"))
    check("拆开到点档", parse_alert_key("due|2026-09-18 14:00")
          == (ALERT_STAGE_DUE, "2026-09-18 14:00"))
    # 老库里存的是上一版的裸时刻（那时只有到点提醒这一档）。升级之后必须按
    # 「到点档」认 —— 否则格式一变，每条历史记录都对不上，全库重响一遍
    check("老库裸时刻按到点档认", parse_alert_key("2026-09-18 14:00")
          == (ALERT_STAGE_DUE, "2026-09-18 14:00"))
    check("空串拆不出档位", parse_alert_key("") is None)
    check("None 拆不出档位", parse_alert_key(None) is None)

    db = fresh_db("advance")
    L = lists_by_name(db)
    W = L["工作"].id

    def add(**kw):
        payload = {"list_id": W, "title": "T", "due_date": TODAY,
                   "due_time": "14:00", "skip_holidays": 0}
        payload.update(kw)
        return db.add_item(payload)

    # —— 排程 ——
    plain = add(title="不提前")
    soon = add(title="提前30分", advance_minutes=30)
    check("不设提前量就只有到点一档",
          alert_instants(db.get_item(plain)) == [(ALERT_STAGE_DUE, at)],
          alert_instants(db.get_item(plain)))
    check("设了提前量就是两档、按时间升序",
          alert_instants(db.get_item(soon))
          == [(ALERT_STAGE_EARLY, datetime(2026, 9, 18, 13, 30)),
              (ALERT_STAGE_DUE, at)],
          alert_instants(db.get_item(soon)))
    check("提前量读回来还在", db.get_item(soon).advance_minutes == 30)
    check("没设过的默认 0", db.get_item(plain).advance_minutes == 0)
    check("没日期或时间就不排程",
          alert_instants(db.get_item(add(title="没时间", due_time=""))) == [])
    neg = add(title="负提前量", advance_minutes=-30)
    check("提前量是负数按 0 算（不排提前档）",
          alert_instants(db.get_item(neg)) == [(ALERT_STAGE_DUE, at)],
          alert_instants(db.get_item(neg)))

    # —— 该响哪一档 ——
    r = db.pending_alerts(datetime(2026, 9, 18, 13, 30))
    check("13:30 响的是提前档", [i.id for i in r["due"]] == [soon],
          f"实际 {[i.id for i in r['due']]}")
    check("提前档的记账串", r["moments"].get(soon) == "early|2026-09-18 13:30",
          r["moments"].get(soon))
    check("提前档标 stage", r["stages"].get(soon) == ALERT_STAGE_EARLY,
          r["stages"].get(soon))
    check("没提前量的那条还不到点", plain not in r["moments"])
    db.mark_alerted(r["moments"])
    check("提前档记账落库",
          db.get_item(soon).alerted_for == "early|2026-09-18 13:30")

    # 提前档响过之后，到点那一刻还要再响一次 —— 这正是「两档各记各的账」的
    # 意义。只存一个时刻的话，14:00 一到就会被判成「已经响过」而永远不响
    r2 = db.pending_alerts(at)
    check("14:00 到点档照样响",
          {i.id for i in r2["due"]} == {plain, soon, neg},
          f"实际 {[i.id for i in r2['due']]}")
    check("到点档 stage 是 due", r2["stages"].get(soon) == ALERT_STAGE_DUE)
    check("到点档的记账串", r2["moments"].get(soon) == "due|2026-09-18 14:00",
          r2["moments"].get(soon))
    db.mark_alerted(r2["moments"])
    check("两档都响过就安静了", not db.pending_alerts(at)["due"])
    check("过一会儿也不重复",
          not db.pending_alerts(at + timedelta(minutes=5))["due"])

    # —— 关机一整天：只响最靠后那一档 ——
    # 人已经错过「还有 30 分钟」了，这时候再说「快到时间了」没有意义，
    # 直接说「到时间了」才对；而且也不该两档各弹一次
    shut = add(title="关机一天", advance_minutes=30)
    r3 = db.pending_alerts(datetime(2026, 9, 19, 9, 0))
    check("关机一天只挑到点那一档",
          r3["moments"].get(shut) == "due|2026-09-18 14:00",
          r3["moments"].get(shut))
    check("关机一天算 missed 不算 due",
          shut in [i.id for i in r3["missed"]]
          and shut not in [i.id for i in r3["due"]])

    # —— 跨日提前：提前 1 天意味着「今天就得看上明天的条目」——
    tomorrow = add(title="明天的", due_date="2026-09-19", due_time="09:00",
                   advance_minutes=1440)
    r4 = db.pending_alerts(datetime(2026, 9, 18, 9, 5))
    check("提前一天在今天早上就命中",
          r4["moments"].get(tomorrow) == "early|2026-09-18 09:00",
          r4["moments"].get(tomorrow))
    check("提前一天这条也进了 due",
          [i.id for i in r4["due"]] == [tomorrow],
          f"实际 {[i.id for i in r4['due']]}")
    db.mark_alerted(r4["moments"])

    # —— 提前档打盹：只推后提前档，不能把到点那一档吃掉 ——
    nap = add(title="提前档打盹", advance_minutes=60)      # 提前 1 小时 → 13:00
    r5 = db.pending_alerts(datetime(2026, 9, 18, 13, 0))
    check("13:00 响提前档", r5["stages"].get(nap) == ALERT_STAGE_EARLY,
          r5["stages"].get(nap))
    db.mark_alerted(r5["moments"])
    nxt = db.snooze(nap, 10, now=datetime(2026, 9, 18, 13, 0), early=True)
    check("提前档打盹推后到 13:10", nxt == "2026-09-18 13:10", nxt)
    check("打盹后重新排程：提前档变 13:10、到点档仍在",
          alert_instants(db.get_item(nap))
          == [(ALERT_STAGE_EARLY, datetime(2026, 9, 18, 13, 10)),
              (ALERT_STAGE_DUE, at)],
          alert_instants(db.get_item(nap)))
    check("打盹未到不响",
          db.pending_alerts(datetime(2026, 9, 18, 13, 5))["stages"].get(nap) is None)
    r6 = db.pending_alerts(datetime(2026, 9, 18, 13, 10))
    check("打盹到点仍是提前档",
          r6["moments"].get(nap) == "early|2026-09-18 13:10",
          r6["moments"].get(nap))
    db.mark_alerted(r6["moments"])
    r7 = db.pending_alerts(at)
    check("提前档打盹没有吃掉到点档",
          r7["moments"].get(nap) == "due|2026-09-18 14:00",
          r7["moments"].get(nap))
    db.mark_alerted(r7["moments"])

    # —— 提前档打盹越过到点时刻：不记（让到点照常响）——
    over = add(title="打盹越过到点", due_time="09:00", advance_minutes=5)
    db.mark_alerted({over: "early|2026-09-18 08:55"})
    check("提前档打盹会拖过到点就不记",
          db.snooze(over, 10, now=datetime(2026, 9, 18, 8, 53), early=True) == "")
    check("不记就还是没打盹的样子", db.get_item(over).snooze_until == "")
    check("到点那一档照常排着",
          alert_instants(db.get_item(over))[-1]
          == (ALERT_STAGE_DUE, datetime(2026, 9, 18, 9, 0)),
          alert_instants(db.get_item(over)))
    check("到点时刻仍会响",
          db.pending_alerts(datetime(2026, 9, 18, 9, 0))["moments"].get(over)
          == "due|2026-09-18 09:00")

    # —— 改提前量 ——
    swap = add(title="改提前量", advance_minutes=30)
    db.mark_alerted({swap: "early|2026-09-18 13:30"})
    db.update_item(swap, {"advance_minutes": 60})
    check("改提前量后排程换成新的提前时刻",
          alert_instants(db.get_item(swap))
          == [(ALERT_STAGE_EARLY, datetime(2026, 9, 18, 13, 0)),
              (ALERT_STAGE_DUE, at)],
          alert_instants(db.get_item(swap)))
    # 旧那档的记账串里带着旧时刻，与新时刻天然不相等 —— 所以新时刻照样能响，
    # 不必特意去清 alerted_for（清反而会把「同一时刻」也放出来，重复打扰）
    check("改成提前 1 小时之后 13:00 这一档仍会响",
          db.pending_alerts(datetime(2026, 9, 18, 13, 0))["moments"].get(swap)
          == "early|2026-09-18 13:00")
    # 反过来：把提前量收掉，就只剩到点一档
    db.update_item(swap, {"advance_minutes": 0})
    check("提前量收掉后只剩到点一档",
          alert_instants(db.get_item(swap)) == [(ALERT_STAGE_DUE, at)],
          alert_instants(db.get_item(swap)))
    db.close()

    # —— 侧栏角标：数字数未完成，「红不红」看逾期 ——
    bdb = fresh_db("advance_badge")
    BL = lists_by_name(bdb)
    X, Y = BL["工作"].id, BL["生活"].id
    done = bdb.add_item({"list_id": X, "title": "已经逾期", "due_date": "2026-09-10",
                         "skip_holidays": 0})
    bdb.add_item({"list_id": X, "title": "今天到期", "due_date": TODAY,
                  "skip_holidays": 0})
    bdb.add_item({"list_id": X, "title": "没日期的"})
    bdb.add_item({"list_id": Y, "title": "别人的活", "due_date": "2026-09-30",
                  "skip_holidays": 0})

    open_cnt = bdb.open_count_by_list()
    late_cnt = bdb.overdue_count_by_list(today=TODAY)
    check("角标数字 = 未完成数", open_cnt.get(X) == 3, f"实际 {open_cnt}")
    check("没有逾期的清单不出现在红名单里", Y not in late_cnt, f"实际 {late_cnt}")
    check("有逾期的清单才标红", late_cnt.get(X) == 1, f"实际 {late_cnt}")
    check("红名单只数未完成的逾期项",
          sum(late_cnt.values()) == bdb.count_by_scope(today=TODAY)["overdue"],
          f"实际 {late_cnt} / {bdb.count_by_scope(today=TODAY)}")
    # 逾期那条勾完，红标记就该消失
    bdb.set_completed(done, True)
    check("逾期项做完就不再标红",
          bdb.overdue_count_by_list(today=TODAY).get(X) is None,
          f"实际 {bdb.overdue_count_by_list(today=TODAY)}")
    check("角标数字跟着减一", bdb.open_count_by_list().get(X) == 2,
          f"实际 {bdb.open_count_by_list()}")
    bdb.close()


# ===========================================================================
# K. 清单拖动排序
# ===========================================================================
def test_reorder() -> None:
    section("[K] 清单拖动排序（保序去重 / 缺漏接末尾 / sort_order 连续）")
    db = fresh_db("reorder")
    db.seed_default_lists()

    order = lambda: [l.id for l in db.fetch_lists()]
    names = lambda: [l.name for l in db.fetch_lists()]

    check("默认三个清单", len(order()) == 3, names())

    start = order()
    db.reorder_lists(list(reversed(start)))
    check("整体反转生效", order() == list(reversed(start)), names())
    check("名称跟着反了", names() == ["生活", "工作", "提醒事项"], names())

    cur = order()
    db.reorder_lists([cur[2]] + cur[:2])
    check("末尾项提到最前", order() == [cur[2], cur[0], cur[1]], names())

    # 少传了谁，谁就按原序接在末尾 —— 不能把清单弄丢
    cur = order()
    db.reorder_lists([cur[1]])
    rest = [i for i in cur if i != cur[1]]
    check("没点名的接在末尾而不是消失", order() == [cur[1]] + rest, names())
    check("清单总数不变", len(order()) == 3, len(order()))

    cur = order()
    db.reorder_lists([9999, cur[0]])
    check("未知 id 被忽略", order() == cur, names())

    cur = order()
    db.reorder_lists([cur[0], cur[0], cur[1], cur[2]])
    check("重复 id 去重", order() == cur, names())

    cur = order()
    db.reorder_lists([])
    check("空列表不动顺序", order() == cur, names())

    raw = [r[0] for r in db.conn.execute(
        "SELECT sort_order FROM todo_lists ORDER BY sort_order").fetchall()]
    check("sort_order 被重写成连续整数", raw == [0, 1, 2], raw)

    check("返回值 = 清单数", db.reorder_lists(order()) == 3)

    marked = names()
    path = db.db_path
    db.close()
    # 重开一次：顺序得是从库里读出来的，而不是留在内存里的
    db2 = TodoDB(path)
    check("重开库后顺序保持", [l.name for l in db2.fetch_lists()] == marked,
          [l.name for l in db2.fetch_lists()])
    db2.add_list("新清单")
    check("新建清单排在末尾",
          [l.name for l in db2.fetch_lists()] == marked + ["新清单"],
          [l.name for l in db2.fetch_lists()])
    db2.close()


def main_test() -> None:
    print("=" * 78)
    print("待办模块回归测试：数据层 + 节假日引擎")
    print("=" * 78)
    test_helpers()
    test_holidays()
    test_repeat_rules()
    test_rollover()
    test_workday_notice()
    test_complete()
    test_scopes()
    test_show_completed()
    test_alerts()
    test_advance_alerts()
    test_crud()
    test_reorder()


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
