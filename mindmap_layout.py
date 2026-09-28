"""思维导图 · 纯布局算法（不 import tkinter、不 import 任何 *_db）。

设计取舍：**大纲驱动，自动布局**。
手拖节点对「练结构」没有增量，却要吃掉大量实现与调试成本 —— 所以只做
「缩进 = 层级」的大纲，画布坐标全部由这里算出来。改的是**关系**，不是**位置**。

对外只暴露纯函数：

* ``parse_outline`` / ``outline_text``  —— 大纲文本 <-> 树（互为逆运算）
* ``build_tree`` / ``flatten``         —— 数据库扁平行 <-> 树
* ``layout``                            —— 树 -> 坐标（本模块的核心）
* ``to_markdown`` / ``to_opml`` / ``to_text`` —— 导出
* ``depth_color`` / ``DEPTH_COLORS``    —— 层级配色

树节点的统一形状（dict）::

    {"id": int | None, "text": str, "note": str,
     "collapsed": bool, "children": [ ... ]}

``id`` 为 ``None`` 表示「还没入库」；``parent_id=0`` 的习惯只出现在数据库层。
"""
from __future__ import annotations

import re
import xml.sax.saxutils as _sax

# ----------------------------------------------------------------------
# 几何常量
# ----------------------------------------------------------------------
NODE_MIN_W = 104          # 节点最小宽度（像素）
NODE_H = 32
H_GAP = 58                # 层间横向净距
V_GAP = 14                # 同层相邻叶子间纵向净距
CHAR_W = 7.6              # 半角字符估算宽度
CJK_FACTOR = 2            # 汉字按 2 个半角宽算
PAD_X = 26                # 节点左右内边距合计

# 折叠时画一个「+ n」的小标记，留出宽度
COLLAPSED_BADGE_W = 30

# 层级配色：中心主题最深，越深一层越亮（同一条蓝紫渐变，浅底上对比都够）
DEPTH_COLORS = (
    "#0f172a",   # 0 中心主题
    "#1d4ed8",
    "#4338ca",
    "#6d28d9",
    "#9333ea",
    "#a21caf",
    "#be185d",
)


def depth_color(depth, colors=None):
    """层级 -> 颜色。超出调色板长度就取最后一个，不循环（否则深层会「回春」）。"""
    ramp = colors or DEPTH_COLORS
    if not ramp:
        return "#0f172a"
    index = max(0, min(int(depth), len(ramp) - 1))
    return ramp[index]


# ----------------------------------------------------------------------
# 基本度量
# ----------------------------------------------------------------------
def char_width(ch: str) -> int:
    """汉字 / 全角算 2，其余算 1。"""
    if ord(ch) > 0x2E80:
        return CJK_FACTOR
    return 1


def measure_text(text, *, min_w=NODE_MIN_W) -> int:
    """节点宽度估算（纯函数，方便测试与跨平台一致）。"""
    units = sum(char_width(ch) for ch in str(text or ""))
    return max(int(min_w), int(units * CHAR_W) + PAD_X)


def empty_tree(text="中心主题") -> dict:
    return {"id": None, "text": text, "note": "", "collapsed": False, "children": []}


def new_node(text) -> dict:
    return {"id": None, "text": str(text or ""), "note": "",
            "collapsed": False, "children": []}


def normalize(node) -> dict:
    """补齐缺失字段，保证后续代码可以无条件取键。"""
    if not isinstance(node, dict):
        node = {"text": str(node or "")}
    out = {
        "id": node.get("id"),
        "text": str(node.get("text") or ""),
        "note": str(node.get("note") or ""),
        "collapsed": bool(node.get("collapsed")),
        "children": [],
    }
    for child in node.get("children") or ():
        out["children"].append(normalize(child))
    return out


# ----------------------------------------------------------------------
# 大纲文本 <-> 树
# ----------------------------------------------------------------------
_BULLET_RE = re.compile(r"^(?:[-*+•]\s+|\d+[.)]\s+|#+\s*)")


def _outline_lines(text):
    """(缩进宽度, 正文) 序列。缩进按 Tab=4 空格展开；项目符号剥掉。"""
    rows = []
    for raw in str(text or "").splitlines():
        if not raw.strip():
            continue
        expanded = raw.replace("\t", "    ")
        indent = len(expanded) - len(expanded.lstrip(" "))
        content = _BULLET_RE.sub("", expanded.strip()).strip()
        if not content:
            continue
        rows.append((indent, content))
    return rows


def parse_outline(text, *, root_text=None) -> dict:
    """把缩进大纲解析成树。

    **第一行就是中心主题**；之后每一行挂在「最近一个缩进更浅」的节点下。
    缩进是**相对**的：第一行之后任何一行的缩进若不比根深，就直接挂在根下，
    这样「标题顶格 + 分支缩进 2」和「标题也缩进 2、分支缩进 4」两种写法都对，
    不必逼用户去数空格。

    空输入返回一棵空树（``text`` 取 ``root_text`` 或 ``"中心主题"``）。
    """
    rows = _outline_lines(text)
    if not rows:
        return empty_tree(root_text or "中心主题")

    root = new_node(rows[0][1])
    stack = [(rows[0][0], root)]
    for indent, content in rows[1:]:
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        node = new_node(content)
        stack[-1][1]["children"].append(node)
        stack.append((indent, node))
    return root


def outline_text(tree, *, indent_step=2) -> str:
    """树 -> 缩进大纲。与 :func:`parse_outline` 互为逆运算（结构层面）。"""
    lines = []

    def walk(node, depth):
        lines.append(" " * (indent_step * depth) + str(node.get("text") or ""))
        for child in node.get("children") or ():
            walk(child, depth + 1)

    walk(normalize(tree), 0)
    return "\n".join(lines)


def iter_nodes(tree):
    """DFS 产出 ``(node, parent, depth)``；``parent`` 对根为 ``None``。

    **产出的是树里真实的节点对象，不是副本。** 这一条是硬要求：
    :func:`find_node` / :func:`toggle_collapsed` 全靠拿到真节点就地改。
    这里曾经调过一次 ``normalize``（图省事补齐字段），结果「翻转折叠」改的是
    副本 —— 函数返回 ``True``、树却纹丝不动，界面上双击节点毫无反应，
    而且**一声不响**（不抛异常）。查这个 bug 花了很久。

    只读的调用方（``count_nodes`` / ``max_depth`` / ``width_of`` /
    ``level_texts``）一律用 ``.get()`` 取字段，所以不补字段也安全。
    """
    def walk(node, parent, depth):
        if not isinstance(node, dict):
            return
        yield node, parent, depth
        for child in node.get("children") or ():
            yield from walk(child, node, depth + 1)

    yield from walk(tree, None, 0)


def count_nodes(tree) -> int:
    return sum(1 for _ in iter_nodes(tree))


def max_depth(tree) -> int:
    depth = 0
    for _node, _parent, d in iter_nodes(tree):
        depth = max(depth, d)
    return depth


def width_of(tree) -> int:
    """最大「同层节点数」，可用来估算画布需要的竖向空间。"""
    per_depth = {}
    for _node, _parent, d in iter_nodes(tree):
        per_depth[d] = per_depth.get(d, 0) + 1
    return max(per_depth.values()) if per_depth else 0


def level_texts(tree, level=1) -> list:
    """第 ``level`` 层的文字（``level=0`` 是中心主题）。盲画时用来报「有几个分支」。"""
    out = []
    for node, _parent, d in iter_nodes(tree):
        if d == level:
            out.append(str(node.get("text") or ""))
    return out


def find_node(tree, key, *, by="id"):
    """按 ``id``（或 ``by="text"``）找节点，找不到返回 ``None``。

    **返回的是树里的真节点**（可以就地改）；``id`` 为 ``None`` 时**一律不匹配** ——
    否则 ``find_node(tree, None)`` 会命中根节点，把「找一个还没入库的节点」
    变成「翻转整张导图的根」。
    """
    for node, _parent, _d in iter_nodes(tree):
        if by == "text":
            if node.get("text") == key:
                return node
        elif key is not None and node.get("id") == key:
            return node
    return None


def toggle_collapsed(tree, node_id) -> bool:
    """翻转某个节点的折叠态，返回翻转后的值（找不到就返回 ``False``）。"""
    node = find_node(tree, node_id)
    if node is None:
        return False
    node["collapsed"] = not bool(node.get("collapsed"))
    return node["collapsed"]


_MISSING = object()


def carry_state(old_tree, new_tree, fields=("collapsed",)) -> dict:
    """按文字把旧树上的若干标量字段搬到新树上，返回**归一化后的新树**。

    为什么需要：大纲编辑器提交的是**纯文本**，解析出来的新树里没有任何 ``id``，
    也没有 ``collapsed`` / ``note`` 这些「不在文本里」的字段。直接整树重存会
    把它们全丢掉 —— 而折叠是用户一个个双击出来的，丢了下次进来还得重点一遍。

    匹配策略（先精确、后退让）：

    1. **按文字匹配** —— 只认在旧树里**唯一**的文字。用户改一行内容时，其余
       节点的状态原样保留，这是绝大多数编辑动作的情形。
    2. 文字在旧树里重复（比如两支都叫「其他」）就作废该项，**退回按位置匹配**
       （从根数下来的子节点下标）。在中间插一行会让后面兄弟的状态串位一格 ——
       这是有意的取舍：宁可偶尔串位，也不要把两支的状态互相搞混。
    3. 都匹配不上就不赋值，**新树自己的值原样保留**。

    ``fields`` 里的字段从 ``old`` 搬到 ``new``；``collapsed`` 会被强转成
    ``bool``（它只可能是这个类型），其余字段按原值搬。

    **返回值才是结果**：输入树不会被改动。

    这套搬运属于「能保住就保住」的尽力而为 —— **从不抛异常**，
    因为它跑在每次保存的路径上，不该有让用户存不了盘的理由。
    """
    wanted = tuple(fields or ())
    old = normalize(old_tree)
    new = normalize(new_tree)
    if not wanted:
        return new

    by_text: dict = {}
    by_path: dict = {}

    def scan(node, path):
        text = str(node.get("text") or "")
        snapshot = {key: node.get(key) for key in wanted}
        if text in by_text:
            by_text[text] = _MISSING          # 重名 -> 作废，改走位置匹配
        else:
            by_text[text] = snapshot
        by_path[tuple(path)] = snapshot
        for index, child in enumerate(node.get("children") or ()):
            scan(child, path + (index,))

    scan(old, ())

    def apply(node, path):
        text = str(node.get("text") or "")
        snapshot = by_text.get(text, _MISSING)
        if snapshot is _MISSING:
            snapshot = by_path.get(tuple(path), _MISSING)
        if snapshot is not _MISSING:
            for key in wanted:
                value = snapshot.get(key)
                node[key] = bool(value) if key == "collapsed" else value
        for index, child in enumerate(node.get("children") or ()):
            apply(child, path + (index,))

    apply(new, ())
    return new


def carry_collapsed(old_tree, new_tree) -> dict:
    """只搬 ``collapsed``（:func:`carry_state` 的常用简写）。"""
    return carry_state(old_tree, new_tree, ("collapsed",))


def apply_collapsed(tree, flags) -> dict:
    """按 **DFS 顺序**把一串折叠标记贴回树上，返回**归一化后的树**。

    ``flags`` 是 :meth:`MindmapDB.collapsed_flags` 那种 ``[0/1, ...]`` 快照。
    两者必须走同一个遍历顺序（``iter_nodes`` 的前序 DFS）—— 顺序一旦不一致，
    「双击折叠了半天，存一次全展开」就会重新出现。

    多出来的标记忽略、少了的保持原值：**从不抛异常**，它跑在保存路径上。
    """
    values = list(flags or ())
    out = normalize(tree)
    for index, (node, _parent, _depth) in enumerate(iter_nodes(out)):
        if index >= len(values):
            break
        node["collapsed"] = bool(values[index])
    return out


def build_tree(rows, *, root_id=0) -> dict:
    """把 ``(id, parent_id, seq, text, note, collapsed)`` 扁平行拼成树。

    容错三则（数据是怎么坏的就怎么防）：
      * ``parent_id`` 指向不存在的行 -> 当成根的孩子，**不丢**（否则整枝消失）
      * 出现环 -> 检测到就截断，不会无限递归
      * 根有多条 -> 取 ``seq`` 最小的那条当中心主题，其余挂到它下面
    """
    rows = [dict(r) for r in (rows or [])]
    by_id = {}
    for row in rows:
        by_id[int(row["id"])] = {
            "id": int(row["id"]),
            "text": str(row.get("text") or ""),
            "note": str(row.get("note") or ""),
            "collapsed": bool(row.get("collapsed")),
            "seq": int(row.get("seq") or 0),
            "parent_id": int(row.get("parent_id") or 0),
            "children": [],
        }
    if not rows:
        return empty_tree("中心主题")

    roots = [n for n in by_id.values() if n["parent_id"] not in by_id
             or n["parent_id"] == 0 or n["parent_id"] == root_id]
    roots.sort(key=lambda n: (n["seq"], n["id"]))
    root = roots[0]

    # 悬挂 / 成环的行先全部挂到根下，保证不丢
    for node in by_id.values():
        if node is root:
            continue
        parent = by_id.get(node["parent_id"])
        if parent is None or parent is root and node in roots:
            node["parent_id"] = root["id"]
            root["children"].append(node)
            continue
        parent["children"].append(node)

    # 排序 + 断环（DFS 时若撞到祖先就摘掉）
    def fix(node, seen):
        if node["id"] in seen:
            node["children"] = []
            return
        seen = seen | {node["id"]}
        node["children"].sort(key=lambda n: (n["seq"], n["id"]))
        node["children"] = [c for c in node["children"] if c["id"] not in seen]
        for child in node["children"]:
            fix(child, seen)

    fix(root, frozenset())
    return normalize(root)


def flatten(tree, *, map_id=0, keep_ids=True) -> list:
    """树 -> 可写库的扁平行 ``{id, map_id, parent_id, seq, text, note, collapsed}``。

    ``keep_ids=False`` 时把所有 ``id`` 抹成 ``None``（整体重存一遍时用）。
    """
    tree = normalize(tree)
    root_id = tree.get("id") if keep_ids else None
    rows = []

    def walk(node, parent_id, seq, depth):
        node_id = node.get("id") if keep_ids else None
        rows.append({
            "id": node_id, "map_id": map_id, "parent_id": parent_id or 0,
            "seq": seq, "depth": depth, "text": node.get("text") or "",
            "note": node.get("note") or "", "collapsed": 1 if node.get("collapsed") else 0,
        })
        for index, child in enumerate(node.get("children") or ()):
            walk(child, node_id, index, depth + 1)

    walk(tree, 0, 0, 0)
    if rows:
        rows[0]["id"] = root_id
    return rows


# ----------------------------------------------------------------------
# 布局（本模块的核心）
# ----------------------------------------------------------------------
def layout(tree, *, h_gap=H_GAP, v_gap=V_GAP, node_h=NODE_H,
           min_w=NODE_MIN_W, x0=0.0, y0=0.0) -> dict:
    """大纲树 -> 画布坐标。

    形态：**左右双向树**（中心在最左，分支一律向右；一级分支上下均分）。
    算法是最经典的「叶子游标 + 父节点取子节点中点」：

      1. 后序 DFS。碰到叶子就把当前游标当成它的 ``y``，游标下移 ``node_h + v_gap``；
         碰到内部节点，``y`` = 第一个孩子与最后一个孩子的中点。
      2. 层层累加：第 ``d`` 层的 ``x`` = 前面所有层「该层最宽节点 + h_gap」之和。

    这个方案保证 **同层兄弟不重叠**、**父节点正好居中于子树**，而且节点数是
    线性的，几千个节点也一帧算完。

    返回::

        {"nodes": [...], "edges": [...], "size": (w, h), "bounds": (x, y, w, h),
         "by_iid": {iid: node}}

    每个节点带 ``iid``（画布 tag）、``depth``、``x/y/w/h``、``collapsed``、
    ``hidden_children``（折叠时藏了几个孩子，用来画「+n」）。
    """
    tree = normalize(tree)
    nodes = []
    edges = []
    cursor = [float(y0)]

    def place(node, depth, parent_iid):
        iid = f"n{len(nodes)}"
        text = node.get("text") or ""
        collapsed = bool(node.get("collapsed"))
        kids = [] if collapsed else list(node.get("children") or ())
        width = measure_text(text, min_w=min_w)
        badge = 0
        if collapsed and node.get("children"):
            badge = COLLAPSED_BADGE_W
        record = {
            "iid": iid, "key": node.get("id"), "text": text, "note": node.get("note") or "",
            "depth": depth, "w": width + badge, "h": node_h, "collapsed": collapsed,
            "hidden_children": len(node.get("children") or ()) if collapsed else 0,
            "text_w": width, "badge_w": badge, "x": 0.0, "y": 0.0,
        }
        index = len(nodes)
        nodes.append(record)
        if parent_iid is not None:
            edges.append((parent_iid, iid))

        if not kids:
            record["y"] = cursor[0]
            cursor[0] += node_h + v_gap
        else:
            ys = [place(child, depth + 1, iid) for child in kids]
            record["y"] = (ys[0] + ys[-1]) / 2.0
        assert nodes[index] is record
        return record["y"]

    place(tree, 0, None)

    # 逐层横向累加：每层用「该层最宽节点」对齐，列才会齐
    per_depth_max = {}
    for record in nodes:
        d = record["depth"]
        per_depth_max[d] = max(per_depth_max.get(d, min_w), record["w"])
    column_x = {}
    acc = float(x0)
    for d in sorted(per_depth_max):
        column_x[d] = acc
        acc += per_depth_max[d] + h_gap
    for record in nodes:
        record["x"] = column_x[record["depth"]]

    # 归一化：最上（最左）顶到 y0/x0
    if nodes:
        min_y = min(r["y"] for r in nodes)
        for record in nodes:
            record["y"] = record["y"] - min_y + y0
    width = max((r["x"] + r["w"] for r in nodes), default=0.0) - x0
    height = max((r["y"] + r["h"] for r in nodes), default=0.0) - y0
    bounds = (min((r["x"] for r in nodes), default=x0),
              min((r["y"] for r in nodes), default=y0),
              max((r["x"] + r["w"] for r in nodes), default=x0),
              max((r["y"] + r["h"] for r in nodes), default=y0))
    return {
        "nodes": nodes, "edges": edges,
        "size": (max(1.0, width), max(1.0, height)),
        "bounds": bounds, "by_iid": {r["iid"]: r for r in nodes},
    }


def layout_size(tree, **kwargs):
    """只要画布尺寸（缩略图墙用，省得拿着整份坐标）。"""
    return layout(tree, **kwargs)["size"]


def edge_points(parent, child):
    """一条连线的端点：父节点右中点 -> 子节点左中点。"""
    return (parent["x"] + parent["w"], parent["y"] + parent["h"] / 2.0,
            child["x"], child["y"] + child["h"] / 2.0)


def curve_points(x1, y1, x2, y2, *, steps=12):
    """三次贝塞尔（水平把手），给画布画平滑连线用。返回点串。"""
    dx = max(12.0, (x2 - x1) * 0.5)
    points = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        bx = (mt ** 3) * x1 + 3 * (mt ** 2) * t * (x1 + dx) \
            + 3 * mt * (t ** 2) * (x2 - dx) + (t ** 3) * x2
        by = (mt ** 3) * y1 + 3 * (mt ** 2) * t * y1 \
            + 3 * mt * (t ** 2) * y2 + (t ** 3) * y2
        points.extend((bx, by))
    return points


# ----------------------------------------------------------------------
# 导出
# ----------------------------------------------------------------------
def to_text(tree) -> str:
    """纯文本大纲（就是 :func:`outline_text`，导出菜单里单列一项）。"""
    return outline_text(tree)


def to_markdown(tree) -> str:
    """中心主题作一级标题，分支作嵌套无序列表。"""
    tree = normalize(tree)
    lines = [f"# {tree.get('text') or '中心主题'}", ""]

    def walk(node, depth):
        for child in node.get("children") or ():
            text = str(child.get("text") or "")
            if child.get("note"):
                text = f"{text} —— {child['note']}"
            lines.append("  " * depth + f"- {text}")
            walk(child, depth + 1)

    walk(tree, 0)
    return "\n".join(lines) + "\n"


def to_opml(tree, *, title=None) -> str:
    """OPML 2.0，方便导进别的导图软件。"""
    tree = normalize(tree)
    head = _sax.escape(str(title or tree.get("text") or "思维导图"))

    def render(node, depth):
        pad = "  " * depth
        # 属性值必须用 quoteattr：escape 不转双引号，而这里正是双引号属性，
        # 节点里写一个 " 就会把 OPML 变成非法 XML（解析器直接拒收）。
        attrs = [f"text={_sax.quoteattr(str(node.get('text') or ''))}"]
        if node.get("note"):
            attrs.append(f"_note={_sax.quoteattr(str(node['note']))}")
        kids = node.get("children") or []
        if not kids:
            return [f"{pad}<outline {' '.join(attrs)}/>"]
        out = [f"{pad}<outline {' '.join(attrs)}>"]
        for child in kids:
            out.extend(render(child, depth + 1))
        out.append(f"{pad}</outline>")
        return out

    body = render(tree, 2)
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "  <head>",
        f"    <title>{head}</title>",
        "  </head>",
        "  <body>",
        *body,
        "  </body>",
        "</opml>",
        "",
    ])


def export_bytes(tree, fmt, *, title=None):
    """按格式返回 ``(bytes, 默认扩展名, 默认 MIME)``。PNG 由页面层抓画布，不在这里。"""
    fmt = (fmt or "text").lower()
    if fmt == "markdown":
        return to_markdown(tree).encode("utf-8"), ".md", "text/markdown"
    if fmt == "opml":
        return to_opml(tree, title=title).encode("utf-8"), ".opml", "text/x-opml"
    return to_text(tree).encode("utf-8"), ".txt", "text/plain"


# ----------------------------------------------------------------------
# 盲画辅助
# ----------------------------------------------------------------------
def blind_brief(tree) -> dict:
    """盲画第一屏要的信息：中心主题、一级分支数量、总节点数、最大层数。

    **故意不给分支文字** —— 盲画的意义就是让用户自己回忆出来。
    """
    tree = normalize(tree)
    return {
        "root": tree.get("text") or "",
        "branches": len(tree.get("children") or ()),
        "total": count_nodes(tree),
        "depth": max_depth(tree),
    }


def reveal_levels(tree, *, max_level=None) -> list:
    """盲画逐级展开：``[{"level": 1, "texts": [...]}, ...]``。"""
    top = max_depth(tree) if max_level is None else min(max_level, max_depth(tree))
    return [{"level": level, "texts": level_texts(tree, level)}
            for level in range(1, top + 1)]


SUGGEST_NEW_PER_DAY = 3      # 导图比记忆项「重」得多，建议量故意压小


def suggest_new_count(*, due_total, target_new=None) -> int:
    """今日建议新学几张。到期越多越少加新（和记忆宫殿同一口径）。"""
    if target_new is not None:
        return max(0, int(target_new))
    base = SUGGEST_NEW_PER_DAY
    if due_total >= base * 6:
        return 0
    if due_total >= base * 3:
        return 1
    if due_total >= base:
        return 2
    return base
