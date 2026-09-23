# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 种子数据字段规范
================================================================================
内置函数库分片（``excel_seed_*.py``）都用这里的 ``F()`` 构造条目，好处有三：

1. **字段名只写一遍** —— 五个分片、一百多个条目，靠一个构造函数收口，
   不会出现这个文件写 ``example``、那个文件写 ``example_formula``。
2. **缺字段立刻炸** —— ``F()`` 校验必填项，写漏一个键在 import 期就报错，
   而不是等到界面渲染时 KeyError。
3. **长短字段有默认值** —— ``pitfalls`` / ``use_cases`` / ``related`` 这类
   不是每个函数都有的字段给空串兜底，分片里只写有内容的。

字段一览
--------------------------------------------------------------------------------
code             函数名，大写，**全库唯一**（种子按它 INSERT OR IGNORE，幂等靠它）
name_cn          中文名 / 一句话别名，如 VLOOKUP → 垂直查找
category         官方分类，与速查书章节对齐（见 excel_seed.CATEGORIES）
tags             '|' 分隔的横切标签，如 动态数组|365新增|必学
syntax           语法原型，参数可选部分用 [ ] 包起来
args_desc        参数逐条说明，多行（\n 分隔），每行「参数名：解释」
returns          返回值说明
description      一句话用途
example_formula  示例公式（真实可用的写法）
example_result   示例公式的期望结果 / 怎么读它
pitfalls         易错点，多行；**这是本工具最值钱的字段**，书上常一笔带过
use_cases        '；' 分隔的适用场景，场景反查靠它命中
related          '|' 分隔的相关函数名（必须是库里存在的 code）
min_version      最低可用版本，如 Excel 2003 / Excel 2019 / Excel 365
difficulty       1 入门 / 2 常用 / 3 进阶 / 4 高级
importance       1 了解 / 2 常用 / 3 核心

难度与重要性的口径
--------------------------------------------------------------------------------
* ``difficulty`` 说的是**这个函数的用法本身有多绕**，不是它有多冷门。
  ``INDIRECT`` 写起来很短，但它会让公式不可追踪，所以是 3。
* ``importance`` 说的是**在真实工作里出现的频率**。一个 3 分的函数没掌握，
  日常报表基本写不动；1 分的函数不会也不影响干活。
"""

from __future__ import annotations

# 必填字段：漏了就在 import 期炸掉，别等到界面渲染
REQUIRED_KEYS = (
    "code",
    "name_cn",
    "category",
    "syntax",
    "args_desc",
    "description",
)

# 选填字段及默认值
OPTIONAL_KEYS = {
    "tags": "",
    "returns": "",
    "example_formula": "",
    "example_result": "",
    "pitfalls": "",
    "use_cases": "",
    "related": "",
    "min_version": "Excel 2016",
    "difficulty": 2,
    "importance": 2,
}


def F(**kw) -> dict:
    """构造一条函数库条目（见模块头的字段一览）。"""
    missing = [key for key in REQUIRED_KEYS if not str(kw.get(key, "")).strip()]
    if missing:
        raise ValueError(f"种子条目缺少必填字段 {missing}：{kw.get('code', '?')}")
    unknown = set(kw) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS)
    if unknown:
        raise ValueError(f"种子条目出现未知字段 {sorted(unknown)}：{kw.get('code', '?')}")
    item = dict(OPTIONAL_KEYS)
    item.update({key: str(kw[key]).strip() for key in REQUIRED_KEYS})
    item.update({key: value for key, value in kw.items() if key not in REQUIRED_KEYS})
    item["code"] = item["code"].upper()
    for key in ("difficulty", "importance"):
        value = int(item[key])
        if key == "difficulty" and not 1 <= value <= 4:
            raise ValueError(f"{item['code']} 的 difficulty 必须在 1~4：{value}")
        if key == "importance" and not 1 <= value <= 3:
            raise ValueError(f"{item['code']} 的 importance 必须在 1~3：{value}")
        item[key] = value
    return item


def codes(items) -> list[str]:
    """取一批条目的 code 列表（做自检用）。"""
    return [item["code"] for item in items]
