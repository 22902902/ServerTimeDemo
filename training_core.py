# -*- coding: utf-8 -*-
"""共享训练内核：间隔重复（SRS）与打卡统计的**纯逻辑**。

为什么单独抽一个模块
------------------------------------------------------------------------------
「记忆宫殿」与「思维导图」两个训练模块需要**完全相同**的一套东西：

* 复习间隔阶梯（1 / 3 / 7 / 15 / 30 / 60 / 120 天）
* 三种反馈（熟练 / 模糊 / 忘了）如何改变「掌握度 / 连对 / 间隔」
* 打卡日历（按周一对齐）、连续天数、正确率

这份逻辑已经有实现 —— ``excel_db.py``（Excel 宝典，v1.12.0 起跑了很久）。
本轮**不合并**那份（不动已稳定的 1871 行数据层），而是把口径**逐字抄**到这里，
并加一条测试把两者钉在一起：同一组输入必须给出**同一结果**。
哪天要合并，那条测试就是安全网。

本模块的边界（很重要）
------------------------------------------------------------------------------
* **不 import tkinter** —— 纯数据与纯函数，可以在没有窗口的进程里单测。
* **不 import 任何 ``*_db``** —— 不认识数据库，只接受「一串日期」这种最原始的输入。
* 颜色返回的是十六进制串（``"#a3372f"``），不是 Tk 颜色对象 —— 界面拿去做 fg 即可。
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime, timedelta

# ======================================================================
# 复习反馈
# ======================================================================
FEEDBACK_KNOWN = "known"      # 熟练
FEEDBACK_VAGUE = "vague"      # 模糊
FEEDBACK_FORGOT = "forgot"    # 忘了
FEEDBACK_CHOICES = (
    (FEEDBACK_KNOWN, "熟练"),
    (FEEDBACK_VAGUE, "模糊"),
    (FEEDBACK_FORGOT, "忘了"),
)
FEEDBACK_LABELS = dict(FEEDBACK_CHOICES)

# 连续答对 1..7 次对应的复习间隔（天）。第 8 次起维持最后一档。
SRS_INTERVALS = (1, 3, 7, 15, 30, 60, 120)

# ======================================================================
# 掌握度
# ======================================================================
MASTERY_NEW = 0        # 未学
MASTERY_WEAK = 1       # 生疏
MASTERY_FAIR = 2       # 一般
MASTERY_GOOD = 3       # 熟练
MASTERY_CHOICES = (
    (MASTERY_NEW, "未学"),
    (MASTERY_WEAK, "生疏"),
    (MASTERY_FAIR, "一般"),
    (MASTERY_GOOD, "熟练"),
)
MASTERY_LABELS = dict(MASTERY_CHOICES)

# 与 excel_db 的同一套语气：灰 / 红 / 琥珀 / 绿
MASTERY_COLORS = {
    MASTERY_NEW: "#c9c9c9",
    MASTERY_WEAK: "#a3372f",
    MASTERY_FAIR: "#8a6a2f",
    MASTERY_GOOD: "#2e6b46",
}

# 打卡日历里「练过」的格子用什么色（与掌握度「熟练」同源，但更浅）
CHECKIN_FILL = "#dbeadf"
CHECKIN_TODAY_RING = "#2e6b46"

# 一天建议的新学量上限：超过这个数，一天之内根本记不住，反而伤信心
SUGGEST_NEW_PER_DAY = 8


# ======================================================================
# 日期工具
# ======================================================================
def parse_date(value) -> date | None:
    """把 ``YYYY-MM-DD`` 之类的串解析成 ``date``；解析不了返回 ``None``。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def today_str() -> str:
    return date.today().isoformat()


def shift_date(value, days: int) -> str:
    """把日期串往后推 ``days`` 天（负数往前），返回 ISO 串。"""
    base = parse_date(value) or date.today()
    return (base + timedelta(days=int(days))).isoformat()


def monday_of(value=None) -> date:
    """所在周的周一。**打卡日历按周一对齐**（表头是「一二三四五六日」）。"""
    day = parse_date(value) or date.today()
    return day - timedelta(days=day.isoweekday() - 1)


# ======================================================================
# 间隔重复
# ======================================================================
def interval_for(streak: int) -> int:
    """连续答对 ``streak`` 次之后，下次该隔多少天再来。"""
    index = max(0, min(int(streak) - 1, len(SRS_INTERVALS) - 1))
    return SRS_INTERVALS[index]


def review_next_state(mastery: int, streak: int, interval: int, feedback: str) -> dict:
    """按反馈算出新的「掌握度 / 连对次数 / 间隔」。**纯函数，不落库。**

    熟练 → 掌握度 +1（最高 3），连对 +1，间隔按连对档位往后跳
    模糊 → 掌握度不变（**但至少落个「生疏」**，否则「没学过」会一直是没学过），
           连对 -1，间隔砍半（最低 1 天）
    忘了 → 掌握度 -1（最低 1），连对归零，间隔回到 1 天
    """
    mastery = max(MASTERY_NEW, min(MASTERY_GOOD, int(mastery)))
    streak = max(0, int(streak))
    interval = max(0, int(interval))

    if feedback == FEEDBACK_KNOWN:
        mastery = min(MASTERY_GOOD, mastery + 1)
        streak += 1
        interval = interval_for(streak)
    elif feedback == FEEDBACK_VAGUE:
        # 「模糊」也是学过了：万一之前是未学，至少落个生疏，否则界面会显示成「没学过」
        mastery = max(MASTERY_WEAK, mastery)
        streak = max(0, streak - 1)
        interval = max(1, interval // 2) if interval else 1
    else:  # FEEDBACK_FORGOT
        mastery = max(MASTERY_WEAK, mastery - 1)
        streak = 0
        interval = 1

    return {"mastery": mastery, "correct_streak": streak, "interval_days": interval}


def next_review_date(feedback, *, today=None, mastery=0, streak=0, interval=0) -> str:
    """给一次反馈，算出「下次该复习的日子」（ISO 串）。"""
    state = review_next_state(mastery, streak, interval, feedback)
    return shift_date(today or today_str(), state["interval_days"])


def mastery_label(value) -> str:
    return MASTERY_LABELS.get(int(value or 0), "未学")


def mastery_color(value) -> str:
    return MASTERY_COLORS.get(int(value or 0), MASTERY_COLORS[MASTERY_NEW])


def feedback_label(value) -> str:
    return FEEDBACK_LABELS.get(str(value or ""), "未评")


def due_bucket(next_review_at, today=None) -> str:
    """把一条记录分成三档：``new``（没学过）/ ``due``（今天该复习）/ ``future``（还没到）。"""
    anchor = parse_date(today) or date.today()
    when = parse_date(next_review_at)
    if when is None:
        return "new"
    return "due" if when <= anchor else "future"


# ======================================================================
# 打卡统计
# ======================================================================
def accuracy(reviewed, correct) -> float:
    """正确率（0.0 ~ 1.0）。一道都没复习时返回 0.0，不返回 NaN。"""
    reviewed = int(reviewed or 0)
    correct = int(correct or 0)
    if reviewed <= 0:
        return 0.0
    return max(0.0, min(1.0, correct / reviewed))


def accuracy_percent(reviewed, correct) -> str:
    """正确率的显示串。没练过时显示「—」而不是「0%」（0% 看着像练砸了）。"""
    if int(reviewed or 0) <= 0:
        return "—"
    return f"{accuracy(reviewed, correct) * 100:.0f}%"


def _as_date_set(dates) -> set:
    out = set()
    for item in dates or ():
        parsed = parse_date(item)
        if parsed is not None:
            out.add(parsed)
    return out


def streak_from_dates(dates, today=None) -> int:
    """当前连续打卡天数。

    **今天还没打卡不算断**：今天没练、但昨天练了，仍接着从昨天往前数 ——
    否则每天凌晨一过连续天数就归零，看着像被惩罚。
    """
    anchor = parse_date(today) or date.today()
    marks = _as_date_set(dates)
    if not marks:
        return 0
    cursor = anchor if anchor in marks else anchor - timedelta(days=1)
    if cursor not in marks:
        return 0
    days = 0
    while cursor in marks:
        days += 1
        cursor -= timedelta(days=1)
    return days


def best_streak_from_dates(dates) -> int:
    """历史最长连续打卡天数。"""
    marks = sorted(_as_date_set(dates))
    if not marks:
        return 0
    best = 1
    run = 1
    for prev, cur in zip(marks, marks[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    return best


def checkin_grid(dates, *, today=None, weeks: int = 5) -> list[dict]:
    """打卡日历：**按周一对齐**，返回 ``weeks`` 行，每行 7 格（周一 → 周日）。

    每格：``{"date": date, "iso": str, "checked": bool, "is_today": bool,
    "is_future": bool, "is_current_week": bool}``
    最后一行是本周 —— 所以最上面那行是 ``weeks - 1`` 周之前那一周。
    """
    anchor = parse_date(today) or date.today()
    this_monday = monday_of(anchor)
    grid_start = this_monday - timedelta(days=7 * (max(1, int(weeks)) - 1))
    marks = _as_date_set(dates)

    rows: list[dict] = []
    for week_index in range(max(1, int(weeks))):
        week_monday = grid_start + timedelta(days=week_index * 7)
        cells = []
        for column in range(7):
            day = week_monday + timedelta(days=column)
            cells.append({
                "date": day,
                "iso": day.isoformat(),
                "checked": day in marks,
                "is_today": day == anchor,
                "is_future": day > anchor,
                "is_current_week": week_index == max(1, int(weeks)) - 1,
            })
        rows.append({
            "monday": week_monday,
            "label": week_monday.strftime("%m/%d"),
            "cells": cells,
        })
    return rows


def month_calendar(year: int, month: int) -> list[list[date]]:
    """整月日历，**按周一起**，前后用 ``None`` 补空。"""
    weeks: list[list[date | None]] = []
    for week in _calendar.Calendar(firstweekday=0).monthdatescalendar(int(year), int(month)):
        row: list[date | None] = []
        for day in week:
            row.append(day if day.month == int(month) else None)
        weeks.append(row)
    return weeks


WEEKDAY_LABELS = ("一", "二", "三", "四", "五", "六", "日")


def weekday_headers() -> tuple[str, ...]:
    return WEEKDAY_LABELS


def summarize(rows) -> dict:
    """把打卡行（每行含 minutes / items_new / items_reviewed / accuracy）汇总成统计卡。

    ``rows`` 可以是 dict 列表，也可以是有同名属性的对象列表。
    """
    def _get(row, key, default=0):
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)

    total_minutes = 0
    total_new = 0
    total_reviewed = 0
    days = 0
    for row in rows or ():
        days += 1
        total_minutes += int(_get(row, "minutes", 0) or 0)
        total_new += int(_get(row, "items_new", 0) or 0)
        total_reviewed += int(_get(row, "items_reviewed", 0) or 0)
    return {
        "days": days,
        "minutes": total_minutes,
        "items_new": total_new,
        "items_reviewed": total_reviewed,
        "avg_minutes": round(total_minutes / days, 1) if days else 0.0,
    }
