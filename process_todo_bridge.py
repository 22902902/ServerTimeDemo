# -*- coding: utf-8 -*-
"""
================================================================================
流程中心 · 待办联动桥（P2）
================================================================================
把「这周要做的服务器巡检」变成待办列表里的一条真待办，**步骤当子任务**。

为什么单独一个模块
--------------------------------------------------------------------------------
与 ``excel_todo_bridge.py`` / ``training_todo_bridge.py`` 同一个手法：
页面只拿到注入进来的可调用对象（``ProcessTodoBridge.create_flow_todo``），
``process_page`` 既不认识 ``todo_db``，也不认识 ``main``，写库全落在数据层这层胶水里。

为什么要有「步骤 → 子任务」这一层
--------------------------------------------------------------------------------
流程的步骤本来就是一份「按顺序要做的事」清单，而待办已经有 ``todo_subtasks``
这张表 —— 把步骤塞进去，走流程的人在待办页就能一行一行勾掉，不必来回切到流程中心
对着屏幕数到第几步了。这也是设计文档第 14 条写的「流程 → 待办 + 子任务」。

三条硬约束（由 ``scripts/test_process.py`` 的 [N] 节守着）
--------------------------------------------------------------------------------
1. **只在用户点击时建**，不做任何后台自动生成。没人希望点开软件多出十条待办。
2. **当天幂等**：同标题、同日期、还没完成的待办已存在就返回 ``created=False``，
   顺手把缺的子任务补齐 —— 连点两次不会堆两条待办、也不会漏掉新加的步骤。
3. **``skip_holidays=0``**：这是「今天开始做的事」，周末点一下不该被
   ``todo_db.add_item`` 顺延到下周一。（``ExcelTodoBridge`` 踩过同一个坑。）
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 加进待办时打的标签，方便在待办页按标签滤出「流程类」
FLOW_TODO_TAG = "流程"
# 中优先级：重要，但不该盖过真正的工作项
DEFAULT_PRIORITY = 2
# 标题过长会把待办列表撑变形；步骤子任务同理
TITLE_LIMIT = 40
SUBTASK_LIMIT = 30


def flow_todo_title(flow) -> str:
    """待办标题：``走一遍流程：换 SSL 证书``。"""
    name = ""
    if isinstance(flow, dict):
        name = str(flow.get("title") or "")
    else:
        try:
            name = str(flow["title"] or "")
        except (KeyError, IndexError, TypeError):
            name = ""
    name = name.strip() or "未命名流程"
    if len(name) > TITLE_LIMIT:
        name = name[:TITLE_LIMIT] + "…"
    return f"走一遍流程：{name}"


def step_titles(steps, *, limit: int = SUBTASK_LIMIT) -> list[str]:
    """步骤 → 子任务标题。**保持库里顺序**，带序号，超量截断。"""
    result = []
    for index, step in enumerate(steps or (), start=1):
        try:
            number = int(step["step_no"])
        except (KeyError, IndexError, TypeError, ValueError):
            number = index
        try:
            title = str(step["title"] or "").strip()
        except (KeyError, IndexError, TypeError):
            title = ""
        if not title:
            continue
        result.append(f"{number}. {title}")
        if len(result) >= int(limit):
            break
    return result


def flow_todo_payload(flow, steps, *, today, variables=None) -> dict:
    """拼一条待办（标题 / 备注 / 子任务）。**纯函数，测试直接打这里。**

    不读库、不看时间 —— ``today`` 由调用方给，所以「今天」这件事只有一个来源。
    """
    values = {str(k): str(v) for k, v in dict(variables or {}).items() if str(v).strip()}
    subtasks = step_titles(steps)

    def field(key, default=""):
        try:
            value = flow[key]
        except (KeyError, IndexError, TypeError):
            return default
        return default if value is None else str(value)

    lines = []
    category = field("category").strip()
    platform = field("platform").strip()
    if category or platform:
        lines.append("　".join(part for part in (
            f"分类：{category}" if category else "",
            f"平台：{platform}" if platform else "") if part))
    lines.append(f"共 {len(subtasks)} 个步骤，勾掉一个算一步。"
                 if subtasks else "这条流程还没有步骤。")
    if values:
        lines.append("变量：" + "　".join(f"{k}={v}" for k, v in values.items()))
    link = field("link_url").strip()
    if link:
        lines.append(f"入口：{link}")
    note = field("note").strip()
    if note:
        lines.append(f"备注：{note}")
    lines.append("打开：流程中心 → 选中这条流程 → 开始执行。")

    return {
        "title": flow_todo_title(flow),
        "due_date": str(today or ""),
        "notes": "\n".join(lines),
        "priority": DEFAULT_PRIORITY,
        "subtasks": subtasks,
    }


class ProcessTodoBridge:
    """「流程中心 → 待办」的写入胶水。构造时给自己一个 ``TodoDB`` 即可。"""

    def __init__(self, todo_db, *, tag: str = FLOW_TODO_TAG,
                 priority: int = DEFAULT_PRIORITY):
        self.todo_db = todo_db
        self.tag = tag
        self.priority = int(priority)

    # -- 查询 ----------------------------------------------------------
    def find_open_todo(self, *, title: str, due_date: str):
        """找当天那条同标题、还没完成的待办；没有就返回 ``None``。

        读失败一律当「没有」—— 宁可多建一条（用户可以自己删），也不该因为
        一次读异常就把「加了待办」这个按钮整个废掉。
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

    def existing_subtitles(self, item_id) -> list[str]:
        try:
            return [str(row.title) for row in self.todo_db.fetch_subtasks(int(item_id))]
        except Exception:                     # noqa: BLE001
            logger.exception("读取子任务失败，按「还没有」处理")
            return []

    # -- 写入 ----------------------------------------------------------
    def create_flow_todo(self, payload: dict) -> dict:
        """建（或复用）一条流程待办，并把步骤补成子任务。

        返回值统一成
        ``{"created": bool, "item_id": int | None, "subtasks": int, "message": str}``，
        界面直接把 ``message`` 贴到状态栏，不用自己拼话术。
        """
        data = dict(payload or {})
        title = str(data.get("title", "") or "").strip()
        due_date = str(data.get("due_date", "") or "").strip()
        if not title or not due_date:
            return {"created": False, "item_id": None, "subtasks": 0,
                    "message": "缺少标题或日期，没有建待办。"}
        wanted = [str(row) for row in (data.get("subtasks") or []) if str(row).strip()]

        existing = self.find_open_todo(title=title, due_date=due_date)
        if existing is not None:
            added = self._fill_subtasks(int(existing.id), wanted)
            if added:
                return {"created": False, "item_id": int(existing.id),
                        "subtasks": added,
                        "message": f"「{title}」今天已有一条，补上了 {added} 个子任务。"}
            return {"created": False, "item_id": int(existing.id), "subtasks": 0,
                    "message": f"「{title}」今天已经有一条还没完成，没有重复建。"}

        try:
            item_id = int(self.todo_db.add_item({
                "title": title,
                "notes": str(data.get("notes", "") or ""),
                "due_date": due_date,
                "priority": int(data.get("priority") or self.priority),
                "tags": [self.tag],
                # 见模块头第 3 条：这是「今天的事」，不能被顺延到下一个工作日
                "skip_holidays": 0,
            }))
        except Exception as exc:              # noqa: BLE001 - 让界面拿到一句话而不是堆栈
            logger.exception("写入流程待办失败")
            return {"created": False, "item_id": None, "subtasks": 0,
                    "message": f"写待办失败：{exc}"}

        added = self._fill_subtasks(item_id, wanted)
        tail = f"，含 {added} 个子任务" if added else ""
        return {"created": True, "item_id": item_id, "subtasks": added,
                "message": f"已在待办里加上「{title}」（今天，中优先级{tail}）。"}

    def _fill_subtasks(self, item_id: int, wanted: list[str]) -> int:
        """把还缺的子任务补上（已有的不重复加）。返回补了几条。"""
        have = set(self.existing_subtitles(item_id))
        added = 0
        for row in wanted:
            if row in have:
                continue
            try:
                self.todo_db.add_subtask(int(item_id), row)
            except Exception:                 # noqa: BLE001 - 一条子任务失败不该掀桌
                logger.exception("添加子任务失败：%s", row)
                continue
            have.add(row)
            added += 1
        return added
