# -*- coding: utf-8 -*-
"""tools_launcher.py —— 工具启动器的纯逻辑层。

从 tools_page.py 里抽出的「不依赖 tkinter」的部分，目的是让启动器的核心行为
（即输即搜怎么排、卡片副标题怎么消歧、哪些工具重名）可以脱离窗口单测。

四块内容：
  1. fuzzy_score / score_tool / rank_tools —— 即输即搜的模糊排序（Listary 风格）
  2. tool_hint / tool_parent / tool_stem   —— 卡片副标题：用别名/分类/上级目录区分同名工具
  3. duplicate_groups / duplicate_id_set   —— 找出重名工具，驱动消歧与状态条提示
  4. split_tags / normalize_tags / popular_tags —— 标签：解析、规范化、按标签检索

约定：所有函数只读入 dict / sqlite3.Row，返回新对象，绝不修改入参。
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 检索字段与权重
# ---------------------------------------------------------------------------
# 名字最重；别名次之（用户手填的简称就是他心里的叫法）；标签紧跟其后 ——
# 标签本来就是用户自己起的检索词，比文件名（stem）更接近「我想找什么」；
# 文件名去后缀作为兜底（DB 名可能被改过）；分类权重最低，只在别处都没命中时救场。
FIELD_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("name", 1.00),
    ("alias", 0.96),
    ("tags", 0.94),
    ("stem", 0.88),
    ("category", 0.42),
)

# 分档分值：档与档之间留出足够间距，保证「同一档内排序」不会跨档乱序
SCORE_EXACT = 1000      # 完全相等
SCORE_PREFIX = 800      # 前缀命中
SCORE_WORD = 600        # 命中某个词的词首（"dg" 命中 "Disk Genius"）
SCORE_SUBSTR = 400      # 普通子串命中
SCORE_SUBSEQ = 200      # 只在子序列意义下命中（"dkgn" → "DiskGenius"）
CONSECUTIVE_BONUS = 18  # 子序列里每多一个连号
GAP_PENALTY = 6         # 子序列里每多一个断口
LENGTH_CAP = 40         # 长度惩罚上限，避免长路径把分值拉成负数
MIN_SCORE = 1

# 词边界：命中这些字符之后的字符，视为一个词的词首
BOUNDARY_CHARS = set(" _-./\\()[]+,")


# ---------------------------------------------------------------------------
# 字段读取
# ---------------------------------------------------------------------------

def field_text(tool, key: str) -> str:
    """安全取字段文本。

    sqlite3.Row 取不存在的列会抛 IndexError（不是 KeyError），
    dict 则可能抛 KeyError/TypeError，这里统一吞掉返回空串。
    """
    try:
        value = tool[key]
    except (KeyError, IndexError, TypeError):
        return ""
    return "" if value is None else str(value)


def tool_id(tool, default=None):
    """安全取 id（转 int）。取不到返回 default。"""
    try:
        return int(tool["id"])
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def tool_stem(tool) -> str:
    """文件名去扩展名 —— DB 里的 name 可能被改过，文件名是第二重保障。"""
    path = field_text(tool, "path").strip()
    if not path:
        return ""
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return base


def tool_parent(tool) -> str:
    """上级目录名 —— 同名工具散在不同目录时，这是最有效的区分信息。"""
    path = field_text(tool, "path").strip()
    if not path:
        return ""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    return parts[-2] if len(parts) >= 2 else ""


# ---------------------------------------------------------------------------
# 模糊匹配与排序
# ---------------------------------------------------------------------------

def fuzzy_score(query: str, text: str):
    """给一次「查询 vs 文本」打分；不命中返回 None。

    Listary 式的分档：完全相等 > 前缀 > 词首 > 子串 > 子序列。
    同档内越短、命中位置越靠前的排越前。
    """
    if not query:
        return 0
    if not text:
        return None
    q = query.casefold()
    t = text.casefold()

    if q == t:
        return SCORE_EXACT

    hit = t.find(q)
    if hit == 0:
        # 前缀命中：短名字优先（"cmd" 应排在 "cmd-tools-helper" 前面）
        return max(SCORE_PREFIX - min(len(t), LENGTH_CAP), MIN_SCORE)
    if hit > 0:
        base = SCORE_WORD if t[hit - 1] in BOUNDARY_CHARS else SCORE_SUBSTR
        penalty = min(hit, LENGTH_CAP) + min(len(t), LENGTH_CAP)
        return max(base - penalty, MIN_SCORE)

    # 子序列：逐字符按序查找，连号加分、断口扣分
    cursor = -1
    prev = -2
    runs = 0
    gaps = 0
    for ch in q:
        found = t.find(ch, cursor + 1)
        if found < 0:
            return None
        if found == prev + 1:
            runs += 1
        else:
            gaps += 1
        prev = found
        cursor = found
    penalty = gaps * GAP_PENALTY + min(len(t), LENGTH_CAP)
    return max(SCORE_SUBSEQ + runs * CONSECUTIVE_BONUS - penalty, MIN_SCORE)


def score_tool(query: str, tool):
    """跨字段取最高分；完全不命中返回 None。"""
    if not query:
        return 0
    best = None
    for key, weight in FIELD_WEIGHTS:
        if key == "stem":
            raw = fuzzy_score(query, tool_stem(tool))
        elif key == "tags":
            # 标签是一串「多个短词」，必须逐个比 —— 理由见 best_tag_score
            raw = best_tag_score(query, tool)
        else:
            raw = fuzzy_score(query, field_text(tool, key))
        if raw is None:
            continue
        weighted = int(raw * weight)
        if best is None or weighted > best:
            best = weighted
    return best


def rank_tools(tools, query: str):
    """按相关度排序返回新列表。

    query 为空 → 原顺序返回（保持 DB 给的排序）；
    排序用 (分值降序, 原下标升序)，保证同分时稳定、不会来回跳。
    """
    query = (query or "").strip()
    if not query:
        return list(tools)
    scored = []
    for index, tool in enumerate(tools):
        score = score_tool(query, tool)
        if score is None:
            continue
        scored.append((score, index, tool))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


# ---------------------------------------------------------------------------
# 标签（tags）
# ---------------------------------------------------------------------------
# 用户手输标签时的分隔符五花八门，中英文都要认：竖线、逗号、顿号、分号，
# 另外空白也算。存库前统一规范成 "a|b|c"，显示时再拆开。
# 注意**不把** "/" "+" "#" 当分隔符 —— "C/C++"、"C#" 这类标签很常见。
TAG_SEPARATOR_RE = re.compile(r"[|｜,，、;；\s]+")
TAG_JOIN = "|"
TAG_MAX = 24            # 单个工具的标签数上限，防止一行黏进上百个词


def split_tags(text) -> list[str]:
    """把用户输入拆成标签列表：去空段、按大小写不敏感去重、保持原顺序。

    空值 / None / 非字符串都返回空列表 —— 老库没有 tags 列时也是这个结果。
    """
    raw = "" if text is None else str(text)
    tags: list[str] = []
    seen: set[str] = set()
    for part in TAG_SEPARATOR_RE.split(raw):
        tag = part.strip()
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        if len(tags) >= TAG_MAX:
            break
        seen.add(key)
        tags.append(tag)
    return tags


def normalize_tags(text) -> str:
    """存库用的规范形态：`|` 连接、去重、去掉空段。

    "FTP、 网络 ftp" → "FTP|网络"（大小写不敏感去重，保留第一次出现的写法）
    """
    return TAG_JOIN.join(split_tags(text))


def tool_tags(tool) -> list[str]:
    """取一个工具的标签列表（老库缺 tags 列时安全返回空）。"""
    return split_tags(field_text(tool, "tags"))


def best_tag_score(query: str, tool):
    """按「单个标签」打分取最高分；没标签或没命中返回 None。

    为什么不拿 "ftp|网络" 整串去 fuzzy：那样 "ftp" 只是子串命中、还容易被
    相邻标签的字符干扰；而用户输入一个标签时想要的就是「按标签命中」，
    完全相等必须排最前。逐个标签比才有这个语义。
    """
    best = None
    for tag in tool_tags(tool):
        raw = fuzzy_score(query, tag)
        if raw is None:
            continue
        if best is None or raw > best:
            best = raw
    return best


def popular_tags(tools, limit: int = 0) -> list[tuple[str, int]]:
    """统计一批工具的标签使用次数：[(标签, 个数)]，个数降序、标签升序。

    标签栏只需要露出最常用的一小撮，长尾靠搜索框找就够了，所以带上 limit。
    同一个标签大小写不同的写法只算一个（以第一次出现的写法展示）。
    """
    counts: dict[str, int] = {}
    label: dict[str, str] = {}
    for tool in tools:
        for tag in tool_tags(tool):
            key = tag.casefold()
            counts[key] = counts.get(key, 0) + 1
            label.setdefault(key, tag)
    items = [(label[key], count) for key, count in counts.items()]
    items.sort(key=lambda item: (-item[1], item[0].casefold()))
    return items[:limit] if limit > 0 else items


# ---------------------------------------------------------------------------
# 卡片副标题（消歧）
# ---------------------------------------------------------------------------

# 消歧候选字段：从具体到宽泛。挑「本组内唯一」的那一个才真的能区分开。
def _hint_candidates(tool) -> tuple[str, str, str]:
    return (
        field_text(tool, "alias").strip(),
        tool_parent(tool).strip(),
        field_text(tool, "category").strip(),
    )


def tool_hint(tool, siblings=None) -> str:
    """卡片第二行的浅色小字。

    不重名时：别名 > 分类（「未分类」视为无信息，不显示）。
    重名时（siblings 传入含自己的同组工具）：从具体到宽泛挑第一个「组内唯一」的
    字段，否则退回别名/上级目录/分类。

    之所以要按组算，是因为别名也可能是共用的 —— 例如两个 simplewall 的别名都填了
    「simplewall防火墙」，光看别名分不开，得退到上级目录 X32/X64 才有意义。
    """
    alias, parent, category = _hint_candidates(tool)
    if category == "未分类":
        category = ""

    group = list(siblings) if siblings else []
    if len(group) <= 1:
        return alias or category

    for getter in (
        lambda t: field_text(t, "alias").strip(),
        lambda t: tool_parent(t).strip(),
    ):
        value = getter(tool)
        if value and sum(1 for s in group if getter(s) == value) == 1:
            return value
    return alias or parent or category


def compute_hints(tools) -> dict:
    """一次性算出 {tool_id: 卡片副标题}，重名的自动选可区分字段。

    网格刷新时调一次，免得每个卡片各自去遍历一遍同名组。
    """
    groups: dict[str, list] = {}
    for tool in tools:
        groups.setdefault(name_key(tool), []).append(tool)

    hints = {}
    for tool in tools:
        tid = tool_id(tool)
        if tid is None:
            continue
        siblings = groups.get(name_key(tool)) or [tool]
        hints[tid] = tool_hint(tool, siblings=siblings)
    return hints


# ---------------------------------------------------------------------------
# 置顶横条：收藏 / 最近使用
# ---------------------------------------------------------------------------

TRUTHY = {"1", "true", "yes", "on"}


def as_flag(value) -> bool:
    """把 DB 里 0/1、"True"/"False"、None 统一判成 bool。"""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().casefold() in TRUTHY


def favorite_tools(tools) -> list:
    """收藏工具，按名字排序 —— 顺序稳定，用户才能靠位置记忆。"""
    picked = [t for t in tools if as_flag(field_text(t, "is_favorite"))]
    picked.sort(key=lambda t: field_text(t, "name").casefold())
    return picked


def recent_tools(tools, limit: int = 8, *, exclude_ids=()) -> list:
    """最近使用过的工具（有 last_run_at 才算），按时间倒序取前 limit 个。"""
    exclude = {int(i) for i in exclude_ids if str(i).lstrip("-").isdigit()}
    runs = [
        t for t in tools
        if field_text(t, "last_run_at").strip() and tool_id(t) is not None
        and tool_id(t) not in exclude
    ]
    runs.sort(key=lambda t: field_text(t, "last_run_at"), reverse=True)
    return runs[:limit] if limit > 0 else runs


def strip_label(tool, *, max_len: int = 12) -> str:
    """横条 chip 上的短标签：优先别名（用户起的简称最短最好认）。"""
    alias = field_text(tool, "alias").strip()
    name = field_text(tool, "name").strip()
    text = alias or name
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


# ---------------------------------------------------------------------------
# 重名检测
# ---------------------------------------------------------------------------

def name_key(tool) -> str:
    """重名比较用的归一化名字（大小写、首尾空白不参与比较）。"""
    return field_text(tool, "name").strip().casefold()


def duplicate_groups(tools) -> dict[str, list]:
    """返回 {归一化名: [工具, ...]}，只保留真的重名的组。"""
    groups: dict[str, list] = {}
    for tool in tools:
        key = name_key(tool)
        if not key:
            continue
        groups.setdefault(key, []).append(tool)
    return {key: group for key, group in groups.items() if len(group) > 1}


def duplicate_id_set(tools) -> set:
    """需要「副标题消歧」的工具 id 集合。"""
    ids = set()
    for group in duplicate_groups(tools).values():
        for tool in group:
            tid = tool_id(tool)
            if tid is not None:
                ids.add(tid)
    return ids


def duplicate_names(tools) -> list[tuple[str, int]]:
    """[(显示名, 个数), ...]，按个数降序、名字升序 —— 供状态条提示。"""
    items = []
    for group in duplicate_groups(tools).values():
        items.append((field_text(group[0], "name"), len(group)))
    items.sort(key=lambda item: (-item[1], item[0].casefold()))
    return items
