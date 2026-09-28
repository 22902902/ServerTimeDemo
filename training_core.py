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
import math
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
    interval = max(0, int(interval))
    mastery, streak = _mastery_step(mastery, streak, feedback)

    if feedback == FEEDBACK_KNOWN:
        interval = interval_for(streak)
    elif feedback == FEEDBACK_VAGUE:
        # 「模糊」也是学过了：万一之前是未学，至少落个生疏，否则界面会显示成「没学过」
        interval = max(1, interval // 2) if interval else 1
    else:  # FEEDBACK_FORGOT
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
# 间隔重复 · 多算法（v1.19.0）
# ======================================================================
# 原来只有一套「阶梯」（1/3/7/15/30/60/120 天）。台阶的好处是**可解释**：
# 连对几次、隔几天，扳手指头都能算。缺点是对「难啃的卡」和「一眼过的卡」
# 一视同仁 —— 同一档位给同一个间隔。
#
# 这里补上两套成熟算法，都做成**纯函数**（不落库、不认识 DB）：
#   SM-2  —— SuperMemo-2，给每张卡维护一个 ease factor（难易系数）
#   FSRS  —— 用「记忆稳定度 / 难度」两维建模，间隔由目标保持率反推
# 默认仍是阶梯：三套里最容易解释，而且既有的卡片不用重新养。
ALGORITHM_STAIRS = "stairs"
ALGORITHM_SM2 = "sm2"
ALGORITHM_FSRS = "fsrs"
ALGORITHM_CHOICES = (
    (ALGORITHM_STAIRS, "阶梯（默认）"),
    (ALGORITHM_SM2, "SM-2"),
    (ALGORITHM_FSRS, "FSRS"),
)
ALGORITHM_LABELS = dict(ALGORITHM_CHOICES)
DEFAULT_ALGORITHM = ALGORITHM_STAIRS

# 下拉框旁边那句人话。**界面上只显示这一句**，用户不需要知道公式长什么样。
ALGORITHM_HINTS = {
    ALGORITHM_STAIRS: "按 1/3/7/15/30/60/120 天跳档，最好预测",
    ALGORITHM_SM2: "答对按难易系数拉长，答错退回第一天",
    ALGORITHM_FSRS: "按「还记得的概率」排下一次，最贴合节奏",
}
# 反查表：下拉框给的是中文名，得换回键才能落库。
# 不按 CHOCIES 的下标对齐 —— 以后中间插一套算法，下标就全错位了。
ALGORITHM_BY_LABEL = {label: key for key, label in ALGORITHM_CHOICES}


def normalize_algorithm(value) -> str:
    """认不出来的算法一律退回默认，**不抛异常**（老库里的空值也会走到这里）。"""
    text = str(value or "").strip().lower()
    return text if text in ALGORITHM_LABELS else DEFAULT_ALGORITHM


def algorithm_label(value) -> str:
    return ALGORITHM_LABELS[normalize_algorithm(value)]


def _mastery_step(mastery: int, streak: int, feedback: str) -> tuple:
    """三种反馈对「掌握度 / 连对」的作用 —— **与算法无关，三套共用**。

    掌握度只是**给人看的档位**（未学/生疏/一般/熟练），不参与排期计算。
    所以切成 SM-2 / FSRS 之后这条规则一个字都不改，界面上不会突然「跳档」。
    """
    mastery = max(MASTERY_NEW, min(MASTERY_GOOD, int(mastery)))
    streak = max(0, int(streak))
    if feedback == FEEDBACK_KNOWN:
        return min(MASTERY_GOOD, mastery + 1), streak + 1
    if feedback == FEEDBACK_VAGUE:
        return max(MASTERY_WEAK, mastery), max(0, streak - 1)
    return max(MASTERY_WEAK, mastery - 1), 0


# ---- SM-2 ------------------------------------------------------------
SM2_DEFAULT_EASE = 2.5      # 新卡的初始难易系数
SM2_MIN_EASE = 1.3          # 原版下限：低于它间隔会开始倒退
SM2_FIRST_INTERVAL = 1      # 第一次答对的间隔（天）
SM2_SECOND_INTERVAL = 6     # 第二次答对的间隔（天）
# 三种反馈映射成 SM-2 的质量分（0-5）。原版要求 >=3 才算「答对」。
FEEDBACK_QUALITY = {FEEDBACK_KNOWN: 5, FEEDBACK_VAGUE: 3, FEEDBACK_FORGOT: 1}


def sm2_next_state(mastery, streak, interval_days, ease, reps, feedback) -> dict:
    """SM-2 一步。返回 ``mastery / correct_streak / interval_days / ease_factor / reps``。

    质量分 >=3（熟练 / 模糊）算答对：间隔按 1 -> 6 -> 上次间隔xEF 递推，并按
    原版公式微调 EF；<3（忘了）连对清零、间隔回到 1 天，而 **EF 不动** ——
    原版就是这么定的，别自作聪明去罚它。
    """
    quality = FEEDBACK_QUALITY.get(str(feedback), 3)
    ease = float(ease or 0) or SM2_DEFAULT_EASE
    ease = max(SM2_MIN_EASE, ease)
    reps = max(0, int(reps or 0))
    interval = max(0, int(interval_days or 0))
    mastery, streak = _mastery_step(mastery, streak, feedback)

    if quality >= 3:
        if reps <= 0:
            interval = SM2_FIRST_INTERVAL
        elif reps == 1:
            interval = SM2_SECOND_INTERVAL
        else:
            interval = max(1, int(round(interval * ease)))
        reps += 1
        ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        ease = max(SM2_MIN_EASE, ease)
    else:
        reps = 0
        interval = 1

    return {"mastery": mastery, "correct_streak": streak,
            "interval_days": interval,
            "ease_factor": round(ease, 4), "reps": reps}


# ---- FSRS（4.5 版公式，公开默认权重） --------------------------------
# 用的是**公开的默认权重**，没有拿你的复习日志做参数拟合 —— 个人化训练要
# 几百条以上流水才有意义，而且会牵出「离线训练 + 权重版本」这条维护链。
# 先用默认值：间隔已经比阶梯细腻得多。
FSRS_WEIGHTS = (
    0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031,
    1.6474, 0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755,
)
FSRS_DECAY = -0.5
FSRS_FACTOR = 19.0 / 81.0       # ~0.23457，4.5 版拟合出来的常数
FSRS_RETENTION = 0.9            # 目标保持率：到点复习时「还记得」的概率
FSRS_MAX_INTERVAL = 3650        # 上限 10 年，防算飞出天际
FSRS_DIFFICULTY_DEFAULT = 5.0   # 未定难度时的中位值
# 三种反馈 -> FSRS 的四档评分（忘了=Again / 模糊=Hard / 熟练=Good）
FEEDBACK_RATING = {FEEDBACK_FORGOT: 1, FEEDBACK_VAGUE: 2, FEEDBACK_KNOWN: 3}


def _clamp(value, low, high):
    return max(low, min(high, float(value)))


def fsrs_retrievability(stability, elapsed_days) -> float:
    """到现在还记得的概率（0~1）。``stability`` 越大，同一天数下掉得越慢。"""
    stability = float(stability or 0)
    if stability <= 0:
        return 0.0
    elapsed = max(0.0, float(elapsed_days or 0))
    return _clamp((1.0 + FSRS_FACTOR * elapsed / stability) ** FSRS_DECAY, 0.0, 1.0)


def fsrs_interval_for(stability, retention=FSRS_RETENTION) -> int:
    """把稳定度换算成间隔天数 —— **恰好让到期时的保持率等于目标值**。

    当目标保持率是 0.9 时，结果约等于 stability 本身（这就是它可解释的地方：
    稳定度 10 天 -> 大约 10 天后再来）。
    """
    stability = float(stability or 0)
    if stability <= 0:
        return 1
    retention = _clamp(retention, 0.5, 0.99)
    raw = stability / FSRS_FACTOR * (retention ** (1.0 / FSRS_DECAY) - 1.0)
    return max(1, min(FSRS_MAX_INTERVAL, int(round(raw))))


def fsrs_initial_difficulty(rating) -> float:
    """第一次评分时的难度。**FSRS-4.5 用线性式**（指数式是 FSRS-5 才换的）。

    这里错配过一次：拿 4.5 的权重去跑 5 的指数式，``D0(3)`` 会算出 -5.54 被
    夹到下限 1.0 —— **「熟练」反倒成了最简单的一档**，于是 ``(11 - D)`` 恒等于
    10（增益拉满），间隔一路 4 -> 23 -> 109 -> 437 天飞出去，界面上却一切正常：
    数字有值、也没越界，只是这张卡从此再也不进「今日训练」。
    换回线性式后是 4 -> 15 -> 49 -> 146 天，才对得上 Anki 的手感。
    """
    w = FSRS_WEIGHTS
    return _clamp(w[4] - (int(rating) - 3) * w[5], 1.0, 10.0)


def fsrs_next_difficulty(difficulty, rating) -> float:
    """难度按评分增减，再朝初始值回归一点（``w[7]`` 是回归强度）—— 免得一路刷到天花板。"""
    w = FSRS_WEIGHTS
    value = _clamp(difficulty or FSRS_DIFFICULTY_DEFAULT, 1.0, 10.0)
    value = value - w[6] * (int(rating) - 3)
    value = w[7] * fsrs_initial_difficulty(3) + (1.0 - w[7]) * value
    return _clamp(value, 1.0, 10.0)


def fsrs_next_stability(stability, difficulty, retrievability, rating) -> float:
    """记起来之后的稳定度。忘了（rating<=1）走**另一条公式** —— 「忘了再学会」的曲线不同。"""
    w = FSRS_WEIGHTS
    stability = max(0.01, float(stability or 0))
    difficulty = _clamp(difficulty or FSRS_DIFFICULTY_DEFAULT, 1.0, 10.0)
    retrievability = _clamp(retrievability, 0.0, 1.0)
    if int(rating) <= 1:
        return (w[11] * (difficulty ** -w[12])
                * ((stability + 1.0) ** w[13] - 1.0)
                * math.exp(w[14] * (1.0 - retrievability)))
    hard_penalty = w[15] if int(rating) == 2 else 1.0
    easy_bonus = w[16] if int(rating) == 4 else 1.0
    return stability * (1.0 + math.exp(w[8]) * (11.0 - difficulty)
                        * (stability ** -w[9])
                        * (math.exp((1.0 - retrievability) * w[10]) - 1.0)
                        * hard_penalty * easy_bonus)


def fsrs_next_state(mastery, streak, stability, difficulty,
                    elapsed_days, feedback) -> dict:
    """FSRS 一步。返回 ``mastery / correct_streak / interval_days / stability / difficulty``。

    ``stability <= 0`` 视为**第一次学这张卡**，直接用初始稳定度（``w[0..3]`` 按评分取）。
    """
    rating = FEEDBACK_RATING.get(str(feedback), 3)
    mastery, streak = _mastery_step(mastery, streak, feedback)
    stability = float(stability or 0)
    difficulty = float(difficulty or 0)

    if stability <= 0:
        stability = max(0.01, float(FSRS_WEIGHTS[rating - 1]))
        difficulty = fsrs_initial_difficulty(rating)
    else:
        if difficulty <= 0:
            difficulty = FSRS_DIFFICULTY_DEFAULT
        seen = fsrs_retrievability(stability, elapsed_days)
        difficulty = fsrs_next_difficulty(difficulty, rating)
        stability = max(0.01, fsrs_next_stability(stability, difficulty, seen, rating))

    return {"mastery": mastery, "correct_streak": streak,
            "interval_days": fsrs_interval_for(stability),
            "stability": round(stability, 4),
            "difficulty": round(difficulty, 4)}


def advance_review(feedback, *, algorithm=DEFAULT_ALGORITHM, mastery=0, streak=0,
                   interval_days=0, ease=0, reps=0, stability=0.0,
                   difficulty=0.0, elapsed_days=0) -> dict:
    """**统一入口**：按所选算法推进一次复习，返回的键是三种算法的并集。

    调用方（``memory_db.record_review`` / ``mindmap_db.record_review``）只管把
    行里现有的参数丢进来、把结果写回去 —— 以后换算法不用改调用点。
    没用到的那几栏原样带回，所以来回切算法时已经养出来的参数不会丢。
    """
    algorithm = normalize_algorithm(algorithm)
    if algorithm == ALGORITHM_SM2:
        state = sm2_next_state(mastery, streak, interval_days, ease, reps, feedback)
    elif algorithm == ALGORITHM_FSRS:
        state = fsrs_next_state(mastery, streak, stability, difficulty,
                                elapsed_days, feedback)
    else:
        state = review_next_state(mastery, streak, interval_days, feedback)

    return {
        "algorithm": algorithm,
        "mastery": int(state["mastery"]),
        "correct_streak": int(state["correct_streak"]),
        "interval_days": max(0, int(state["interval_days"])),
        "ease_factor": round(float(state.get("ease_factor", ease) or SM2_DEFAULT_EASE), 4),
        "reps": max(0, int(state.get("reps", reps) or 0)),
        "stability": round(float(state.get("stability", stability) or 0.0), 4),
        "difficulty": round(float(state.get("difficulty", difficulty) or 0.0), 4),
    }


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
