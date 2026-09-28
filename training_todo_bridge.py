# -*- coding: utf-8 -*-
"""
================================================================================
训练模块 · 待办联动桥（记忆宫殿 + 思维导图）
================================================================================
把「今天要复习 N 条记忆项 / 要盲画 N 张导图」变成待办列表里的一条真待办。

为什么两个模块共用一个桥，而不是各写一个
--------------------------------------------------------------------------------
它们的**不变量完全一样**（当天幂等、不许被顺延、只手动建），payload 也只是
词不一样。复制两份的唯一结果就是「改了一条忘了另一条」。与
``excel_todo_bridge`` 保持同一套写法，但把它俩收在一处。

三条硬约束（与 ``excel_todo_bridge`` 一致，由测试守着）
--------------------------------------------------------------------------------
1. **只在用户点击时建**，不做任何后台自动生成 —— 学习 / 训练工具不该变成催命符。
2. **当天幂等**：同标题、同日期、还没完成的待办已存在就返回 ``created=False``，
   连点两次不会堆两条。
3. **``skip_holidays=0``**：这是「今天要做的事」，周末 / 节假日照样落在今天。
   漏了这个参数，周六点一下会被 ``todo_db`` 的 ``shift_to_workday`` 顺延到周一 ——
   而周一你已经不记得周六要练什么了。

注入方式（页面**不 import main、不 import todo_db**）
--------------------------------------------------------------------------------
``main`` 建一个 ``TrainingTodoBridge(todo_db)``，把 ``make_hook("memory")`` /
``make_hook("mindmap")`` 的返回值分别注入两个页面。页面拿到的只是一个
``hook(due=..., suggested=...) -> (title, message)`` 可调用对象。
"""

from __future__ import annotations

import logging

import training_core as tc

logger = logging.getLogger(__name__)

KIND_MEMORY = "memory"
KIND_MINDMAP = "mindmap"

KINDS = {
    KIND_MEMORY: {
        "tag": "记忆宫殿",
        "unit": "条",
        "noun": "记忆项",
        "due_phrase": "今日待复习 {n} 条",
        "action": "复习记忆宫殿",
        "page": "个人系统 → 生活 → 记忆宫殿 → 今日训练",
        "empty_hint": "队列是空的，可以去「题库训练」导一包，或自己新建记忆项。",
        "suggest_hint": "今天还想加新的话，建议 {n} 条 —— 先把复习清干净。",
    },
    KIND_MINDMAP: {
        "tag": "思维导图",
        "unit": "张",
        "noun": "张导图",
        "due_phrase": "今日待盲画 {n} 张",
        "action": "盲画思维导图",
        "page": "个人系统 → 生活 → 思维导图 → 今日训练",
        "empty_hint": "队列是空的，可以去「训练模板」按范式建一张。",
        "suggest_hint": "今天还想画新的话，建议 {n} 张 —— 导图比记忆项重，别贪多。",
    },
}

# 中优先级：重要，但不该盖过真正的工作项
DEFAULT_PRIORITY = 2


def kind_config(kind) -> dict:
    """取某个训练模块的文案配置；不认识的 kind 退回记忆宫殿那套。"""
    return KINDS.get(str(kind or ""), KINDS[KIND_MEMORY])


def review_payload(*, kind, due, suggested=0, today=None) -> dict:
    """拼一条训练待办的标题与备注。**纯函数，测试直接打这里。**

    ``due``       —— 今天到期 / 待复习的数量
    ``suggested`` —— 今日建议新学量（写进备注，省得来回切视图）
    """
    config = kind_config(kind)
    count = max(0, int(due or 0))
    title = (f"{config['action']} {count} {config['unit']}" if count
             else config["action"])
    lines = [f"{config['due_phrase'].format(n=count)}（{config['tag']} · 今日训练）。"]
    if count == 0:
        lines.append(config["empty_hint"])
    new_count = max(0, int(suggested or 0))
    if new_count:
        lines.append(config["suggest_hint"].format(n=new_count))
    lines.append(f"打开：{config['page']}。")
    return {
        "title": title,
        "due_date": str(today or tc.today_str()),
        "notes": "\n".join(lines),
        "priority": DEFAULT_PRIORITY,
        "kind": str(kind or KIND_MEMORY),
    }


class TrainingTodoBridge:
    """「训练模块 → 待办」的写入胶水。构造时给自己一个 ``TodoDB`` 即可。"""

    def __init__(self, todo_db, *, priority: int = DEFAULT_PRIORITY):
        self.todo_db = todo_db
        self.priority = int(priority)

    # -- 查询 ----------------------------------------------------------
    def find_today_todo(self, *, title: str, due_date: str):
        """找当天那条同标题、还没完成的待办；没有就返回 ``None``。

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
    def create(self, payload: dict) -> dict:
        """建（或复用）一条训练待办。

        返回值统一成 ``{"created": bool, "item_id": int | None, "message": str}``，
        界面直接把 ``message`` 显示到状态栏，不用自己拼话术。
        """
        data = dict(payload or {})
        title = str(data.get("title", "") or "").strip()
        due_date = str(data.get("due_date", "") or "").strip()
        if not title or not due_date:
            return {"created": False, "item_id": None,
                    "message": "缺少标题或日期，没有建待办。"}

        existing = self.find_today_todo(title=title, due_date=due_date)
        if existing is not None:
            return {"created": False, "item_id": int(existing.id),
                    "message": f"「{title}」今天已经有一条还没完成，没有重复建。"}

        config = kind_config(data.get("kind"))
        try:
            item_id = self.todo_db.add_item({
                "title": title,
                "notes": str(data.get("notes", "") or ""),
                "due_date": due_date,
                "priority": int(data.get("priority") or self.priority),
                "tags": [config["tag"]],
                # 见模块头第 3 条：这是「今天的事」，不能被顺延到下一个工作日
                "skip_holidays": 0,
            })
        except Exception as exc:              # noqa: BLE001 - 让界面拿到一句话而不是堆栈
            logger.exception("写入训练待办失败")
            return {"created": False, "item_id": None,
                    "message": f"写待办失败：{exc}"}
        return {"created": True, "item_id": int(item_id),
                "message": f"已在待办里加上「{title}」（今天，中优先级）。"}

    # -- 注入给页面的钩子 ----------------------------------------------
    def make_hook(self, kind):
        """返回页面要的 ``hook(due=..., suggested=...) -> (title, message)``。

        两个页面（记忆宫殿 / 思维导图）的调用口径一致，所以这里只按 ``kind``
        把文案和标签固定住，页面完全不知道待办是怎么写进去的。
        """
        resolved = KIND_MINDMAP if str(kind) == KIND_MINDMAP else KIND_MEMORY

        def hook(*, due, suggested=0):
            payload = review_payload(kind=resolved, due=due, suggested=suggested)
            result = self.create(payload)
            return payload["title"], result["message"]

        return hook
