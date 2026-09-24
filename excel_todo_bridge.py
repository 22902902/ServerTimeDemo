# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 待办联动桥（P1）
================================================================================
把「今天要复习 N 个函数」变成待办列表里的一条真待办。

为什么单独一个模块，而不是塞进 ``excel_page``
--------------------------------------------------------------------------------
1. **页面只管画界面。** 与 ``todo_db`` / ``excel_db`` 同一套分层约定：
   写库的动作留在数据层。这个桥就是数据层里那层胶水。
2. **页面不许反向 import main。** 页面拿到的是注入进来的可调用对象
   （``ExcelTodoBridge(todo_db).create_review_todo``），所以 ``excel_page``
   既不认识 ``todo_db``，也不认识 ``main`` —— 与 ``ExcelImageTools`` 同一个手法。

三条硬约束（由 ``scripts/test_excel.py`` 守着）
--------------------------------------------------------------------------------
1. **只在用户点击时建**，不做任何后台自动生成 —— 设计文档第七节写明
   「与待办联动……本轮明确不做（自动），避免打扰」。学习工具不该变成催命符。
2. **当天幂等**：同标题、同日期、还没完成的待办已经存在就返回
   ``created=False``，连点两次不会堆两条。
3. **``skip_holidays=0``**：这是「今天要做的事」，周末 / 节假日照样落在今天。
   漏了这个参数，周六点一下会被 ``todo_db.add_item`` 里的
   ``shift_to_workday`` 顺延到周一 —— 而周一你已经不记得周六要复习什么了。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 加进待办时打的标签，方便你在待办页按标签一眼滤出「学习类」
REVIEW_TODO_TAG = "Excel"
# 中优先级：重要，但不该盖过真正的工作项
DEFAULT_REVIEW_PRIORITY = 2


def review_todo_payload(*, due_count, today, extra_wrong=0,
                        note_hint="") -> dict:
    """拼一条复习待办的标题与备注。**纯函数，测试直接打这里。**

    ``due_count``  —— 今天到期的函数数（来自 ``ExcelDB.due_count``）
    ``extra_wrong``—— 错题本里还挂着几条（顺手写进备注，省得来回切视图）
    ``note_hint``  —— 「生成学习笔记」整理出来的笔记区在哪、有几篇。
        这是「待办 ⇄ 笔记」的反向那一半：从待办点进去的人，一眼就知道
        之前整理的那些笔记放在哪。没生成过笔记时传空串，这句话就不出现。
    """
    count = max(0, int(due_count or 0))
    title = f"复习 Excel 函数 {count} 个" if count else "复习 Excel 函数"
    lines = [f"今日待复习 {count} 个（Excel 宝典 · 今日复习）。"]
    if count == 0:
        lines.append("队列是空的，可以去「函数宝典」标几个不熟的，或做一轮自测。")
    if int(extra_wrong or 0) > 0:
        lines.append(f"错题本里还有 {int(extra_wrong)} 条没订正。")
    hint = str(note_hint or "").strip()
    if hint:
        lines.append(hint)
    lines.append("打开：个人系统 → 生活 → Excel 宝典 → 今日复习。")
    return {
        "title": title,
        "due_date": str(today or ""),
        "notes": "\n".join(lines),
        "priority": DEFAULT_REVIEW_PRIORITY,
    }


class ExcelTodoBridge:
    """「Excel 宝典 → 待办」的写入胶水。构造时给自己一个 ``TodoDB`` 即可。"""

    def __init__(self, todo_db, *, tag: str = REVIEW_TODO_TAG,
                 priority: int = DEFAULT_REVIEW_PRIORITY):
        self.todo_db = todo_db
        self.tag = tag
        self.priority = int(priority)

    # -- 查询 ----------------------------------------------------------
    def find_today_review_todo(self, *, title: str, due_date: str):
        """找当天那条同标题、还没完成的复习待办；没有就返回 None。

        读失败一律当「没有」处理 —— 宁可多建一条（用户可以自己删），
        也不要因为一次读异常就把「建待办」整个按钮废掉。
        """
        try:
            items = self.todo_db.fetch_items(scope="all")
        except Exception:                     # noqa: BLE001 - 读待办不该拖垮建待办
            logger.exception("读取待办列表失败，按「没有重复项」处理")
            return None
        for item in items:
            if (str(item.title) == title and str(item.due_date) == due_date
                    and not int(item.completed or 0)):
                return item
        return None

    # -- 写入 ----------------------------------------------------------
    def create_review_todo(self, payload: dict) -> dict:
        """建（或复用）一条复习待办。

        返回值统一成 ``{"created": bool, "item_id": int | None, "message": str}``，
        界面直接把这句 ``message`` 显示到状态栏，不用自己拼话术。
        """
        data = dict(payload or {})
        title = str(data.get("title", "") or "").strip()
        due_date = str(data.get("due_date", "") or "").strip()
        if not title or not due_date:
            return {"created": False, "item_id": None,
                    "message": "缺少标题或日期，没有建待办。"}

        existing = self.find_today_review_todo(title=title, due_date=due_date)
        if existing is not None:
            return {"created": False, "item_id": int(existing.id),
                    "message": f"「{title}」今天已经有一条还没完成，没有重复建。"}

        try:
            item_id = self.todo_db.add_item({
                "title": title,
                "notes": str(data.get("notes", "") or ""),
                "due_date": due_date,
                "priority": int(data.get("priority") or self.priority),
                "tags": [self.tag],
                # 见模块头第 3 条：这是「今天的事」，不能被顺延到下一个工作日
                "skip_holidays": 0,
            })
        except Exception as exc:              # noqa: BLE001 - 让界面拿到一句话而不是堆栈
            logger.exception("写入复习待办失败")
            return {"created": False, "item_id": None,
                    "message": f"写待办失败：{exc}"}
        return {"created": True, "item_id": int(item_id),
                "message": f"已在待办里加上「{title}」（今天，中优先级）。"}
