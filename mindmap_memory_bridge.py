# -*- coding: utf-8 -*-
"""思维导图 → 记忆宫殿 一键转换。

路线怎么对上
------------------------------------------------------------------------------
记忆宫殿的载体是「一条路线」，导图的载体是「一棵树」。转换口径定成：

* 中心主题     -> 宫殿
* 一级分支     -> 地点桩（路线上的一站，按分支顺序走）
* 二级及以下   -> 记忆项，挂在它那条分支对应的桩上

记忆项的**答案写从根到它的完整路径**（``根 > 分支 > ... > 自己``）：光一个节点名
没有上下文，回忆的时候要能顺着绳子摸回去 —— 这正是导图比列表强的地方。

两条硬约束：
* **只有中心主题、没有分支的导图不转**。转出来是一座一个桩、零条目的空宫殿，
  界面上看着像成功了、其实什么都没有，不如当场说清楚为什么转不了。
* **幂等追加**：同一张导图转第二次不会翻倍。桩按名字认、项按「正面 + 所在桩」
  认，只补缺的，**绝不删用户后来手工加的东西** —— 转完再手工补的桩和条目是
  用户自己的劳动，不该被一次"重新转换"抹掉。

用法
------------------------------------------------------------------------------
    from mindmap_memory_bridge import plan, convert

    info = plan(mm_db, map_id)              # 只算不写，给确认框用
    result = convert(mem_db, mm_db, map_id) # 真转
"""

from __future__ import annotations

SOURCE_PREFIX = "mindmap:"      # 宫殿的 source_key 前缀：靠它认"这张已转过"
PATH_JOINER = " > "             # 记忆项答案里的路径分隔符


def source_key(map_id) -> str:
    """这张导图转出来的宫殿的 ``source_key``。"""
    return f"{SOURCE_PREFIX}{int(map_id)}"


def _walk(tree) -> list:
    """``[(node, depth, path)]``，``path`` 是**从根到它（不含自己）**的文本链。

    深度从 0 开始（0 = 中心主题）。空树返回空表。
    """
    out: list = []

    def rec(node, depth, path) -> None:
        if not isinstance(node, dict):
            return
        text = str(node.get("text") or "").strip()
        out.append((node, depth, list(path)))
        for child in node.get("children") or []:
            rec(child, depth + 1, path + ([text] if text else []))

    if isinstance(tree, dict):
        rec(tree, 0, [])
    return out


def plan(mindmap_db, map_id) -> dict:
    """只算不写：返回打算造出什么，给确认框用。**一个字都不改。**

    ``ok`` 为 False 时看 ``reason`` —— 那是转不了的原因，直接说给用户听，
    别让界面弹一个「转换完成：0 条」出来。
    """
    nodes = _walk(mindmap_db.load_tree(map_id))
    if not nodes:
        return {"ok": False, "reason": "这张导图是空的，没什么可转的。",
                "palace": "", "branches": 0, "items": 0}

    root_text = str(nodes[0][0].get("text") or "").strip()
    branches = [n for n in nodes
                if n[1] == 1 and str(n[0].get("text") or "").strip()]
    items = [n for n in nodes
             if n[1] >= 2 and str(n[0].get("text") or "").strip()]
    if not branches:
        return {
            "ok": False,
            "reason": ("这张导图只有中心主题、没有分支 —— 转出来是一座没有站点的"
                       "空宫殿。先给「" + (root_text or "这张图")
                       + "」加几条一级分支。"),
            "palace": root_text, "branches": 0, "items": len(items)}
    return {"ok": True, "reason": "", "palace": root_text or "（未命名导图）",
            "branches": len(branches), "items": len(items)}


def convert(memory_db, mindmap_db, map_id, *, palace_name=None) -> dict:
    """把一张导图转成一座记忆宫殿。**幂等**：转第二次只补缺的。

    返回 ``{"ok", "reason", "palace_id", "loci", "items", "created",
    "total_loci", "total_items"}`` —— ``loci`` / ``items`` 是**这次新建**的数量，
    ``total_*`` 是转完之后的规模（确认框要报后者，用户关心的是"我现在有什么"）。
    """
    info = plan(mindmap_db, map_id)
    if not info["ok"]:
        return {"ok": False, "reason": info["reason"], "palace_id": 0,
                "loci": 0, "items": 0, "created": False,
                "total_loci": 0, "total_items": 0}

    key = source_key(map_id)
    palace = memory_db.get_palace_by_source(key)
    created = palace is None
    if created:
        palace_id = memory_db.add_palace(
            palace_name or info["palace"], kind="导图转换",
            description=f"由思维导图「{info['palace']}」转换而来。",
            route_note="路线 = 导图的一级分支，按分支顺序走。",
            tags="思维导图", source_key=key)
    else:
        palace_id = int(palace["id"])

    # 已经有的桩 / 项：按「名字」「正面 + 所在桩」认，避免第二次转翻倍
    loci = {str(x.get("name") or "").strip(): int(x["id"])
            for x in memory_db.list_loci(palace_id)}
    seen = {(str(x.get("front") or "").strip(), int(x.get("locus_id") or 0))
            for x in memory_db.list_items(palace_id=palace_id)}

    made_loci = made_items = 0
    for node, depth, path in _walk(mindmap_db.load_tree(map_id)):
        text = str(node.get("text") or "").strip()
        if not text or depth == 0:
            continue
        if depth == 1:
            if text not in loci:
                loci[text] = memory_db.add_locus(palace_id, text)
                made_loci += 1
            continue
        # 二级及以下：挂到自己那条分支（path[1]）对应的桩上
        branch = str(path[1]).strip() if len(path) > 1 else ""
        locus_id = loci.get(branch, 0)
        if (text, locus_id) in seen:
            continue
        back = PATH_JOINER.join(p for p in path if str(p).strip())
        # ``memory_items.source_key`` 上有 UNIQUE 约束 —— 一整张导图共用一个
        # 键会直接报 IntegrityError。所以条目的键带上深度与完整路径。
        memory_db.add_item(front=text, back=back, palace_id=palace_id,
                           locus_id=locus_id,
                           source_key=f"{key}:{depth}:{back}{PATH_JOINER}{text}")
        seen.add((text, locus_id))
        made_items += 1

    return {"ok": True, "reason": "", "palace_id": palace_id,
            "loci": made_loci, "items": made_items, "created": created,
            "total_loci": len(loci), "total_items": len(seen)}
