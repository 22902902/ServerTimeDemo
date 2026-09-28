# -*- coding: utf-8 -*-
"""思维导图回归测试（布局算法 + 数据层 + 种子，纯逻辑、不碰 Tk）。

为什么单独成篇
------------------------------------------------------------------------------
这个模块里有几处算错了界面上**看不出来**：

* **``iter_nodes`` 必须产出树里真实的节点对象**。它曾经顺手调了一次
  ``normalize``（想补齐字段），结果 ``find_node`` / ``toggle_collapsed`` 改的是
  副本 —— **函数返回 True、树纹丝不动**，界面上双击节点毫无反应且不报错。
  所以 A 组用例专门去「就地改一个节点，再回来看它变了没有」。
* **``find_node(tree, None)`` 不许命中根节点**。根节点的 ``id`` 就是 ``None``，
  一旦匹配，「找一个还没入库的节点」会变成「翻转整张导图的根」。
* **折叠不该改变参与排布的节点数**：折叠是把子树从**排布**里摘出去，
  库里一个节点都不能少。把折叠实现成「删子树」的写法，界面上看着一模一样。
* **大纲文本重存必须保住 ``collapsed`` / ``note``**：这两个字段不在文本里，
  整树重存时若不搬运，「双击折叠了半天，改一行字回来全展开了」。
* **``record_review`` 一次调用只写一行流水**；``ensure_progress`` 不许写假流水
  （「标记已学过」不是一次盲画），否则正确率曲线会凭空多出一次作答。
* **``*_progress`` 懒创建** → 所有「今天该盲画哪张」的查询必须走 LEFT JOIN
  / 直接过滤缺失行，内连接会让「今日训练」首次打开是空的 —— 而那时候最该推新。
* **``add_map`` 必须把中心主题节点一起建出来**：否则 ``load_tree`` 落到
  「未命名导图」的兜底上，用户在新建对话框里填的名字，会在第一次编辑大纲时
  被那个兜底串覆盖掉。
* **OPML 的属性值必须用 ``quoteattr``**：``escape`` 不转双引号，节点里写一个
  ``"`` 就会导出成非法 XML（解析器直接拒收），而且不报错、只是打不开。
* **``indent_node(out=True)`` 对第一层分支要拦下**：否则会凭空冒出第二个根，
  再被 ``build_tree`` 兜回根的孩子 —— 返回 True 却什么都没变，还白动一次 seq。

另一类被锁死的是「有意设计」：
* 导图的对象是**整张图**，所以进度表的键是 ``map_id`` 而不是节点 id
* 「模板」灌进来的是**可编辑的普通导图**，不是只读资产
* ``create_from_template`` 出来的图，标题 = 模板大纲的首行（标题与中心主题本就是一回事）
* 折叠状态按 **DFS 顺序**搬运，两边必须走同一个遍历顺序

覆盖
------------------------------------------------------------------------------
A. 训练内核      与记忆宫殿共用一套 SRS（24 步反馈序列逐格一致）
B. 种子一致性    10 卡 / 13 模板 / 码唯一 / 装载自检
C. 建表与幂等    五张表 / 构造即灌模板 / 重开不重复 / 自建图不参与 source_key 唯一
D. 导图 CRUD     增改查删 / 改名同步中心主题 / 级联删 / 关键词与分类
E. 大纲 <-> 树   往返 / 相对缩进 / 项目符号 / Tab / id 认领三步 / 保住折叠与备注
F. 布局算法      叶子游标 / 不重叠 / 父居中 / 折叠收紧 / 缩略图尺寸
G. 结构操作      增删移缩进 / 边界 / 第一层反缩进被拦 / 每步后 tree 与库一致
H. 间隔重复      懒创建 / 一行流水 / marked_at 不被覆盖 / due_maps 防线 / 封顶 120
I. 打卡统计      同日更新 / None 不清零 / 周一对齐 / autofill 幂等 / stats 键
J. 导出          文本 / Markdown / OPML（含引号也要是合法 XML）/ MIME
K. 盲画          只给数量不给文字 / 逐级展开 / 层数 = max_depth
L. 折叠与搬运    真节点 / (None) 不匹配 / apply_collapsed 往返 / 文本重存不丢状态
M. 页面契约      页面用到的每个 db 入口与 ml 函数都存在、行字段齐全
N. 待办桥        盲画措辞 / 不被顺延 / 当天幂等 / 与记忆宫殿互不干扰
O. 游戏训练包    数独 / CS2 / 象棋 三张知识树：分类 / 分支数 / 往返一致 / 能建图

用法：
    python scripts/test_mindmap.py
"""

import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mindmap_db  # noqa: E402
import mindmap_layout as ml  # noqa: E402
import mindmap_seed  # noqa: E402
import todo_db  # noqa: E402
import training_core as tc  # noqa: E402
import training_todo_bridge as ttb  # noqa: E402
from memory_db import MemoryPalaceDB  # noqa: E402
from mindmap_db import MindmapDB  # noqa: E402

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


def fresh(name: str) -> MindmapDB:
    """带模板的库（构造时会自动灌 10 张模板导图）。"""
    d = Path(tempfile.mkdtemp(prefix="mm_test_"))
    _TMP.append(d)
    return MindmapDB(d / f"{name}.db")


def bare(name: str) -> MindmapDB:
    """把模板全删掉的空库：这些用例依赖「初始为空」。"""
    db = fresh(name)
    for item in db.list_maps():
        db.delete_map(item["id"])
    return db


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


def _ids(rows) -> list:
    return [int(r["id"]) for r in rows]


def _texts(tree, level=1) -> list:
    return [str(t) for t in ml.level_texts(tree, level)]


def _subtree_size(node) -> int:
    return 1 + sum(_subtree_size(c) for c in node.get("children") or ())


def _kids(tree, node) -> list:
    return list(node.get("children") or [])


# ══════════════════════════════════════════════════════════════════════════
# A. 训练内核
# ══════════════════════════════════════════════════════════════════════════
def test_srs_parity() -> None:
    section("[A] 训练内核：导图与记忆项共用同一套 SRS")
    check("阶梯 = 1/3/7/15/30/60/120",
          tuple(tc.SRS_INTERVALS) == (1, 3, 7, 15, 30, 60, 120), tc.SRS_INTERVALS)
    check("导图建议量比记忆项小（导图更「重」）",
          ml.SUGGEST_NEW_PER_DAY < tc.SUGGEST_NEW_PER_DAY,
          (ml.SUGGEST_NEW_PER_DAY, tc.SUGGEST_NEW_PER_DAY))

    md = MemoryPalaceDB(Path(tempfile.mkdtemp(prefix="mm_par_")) / "a.db")
    _TMP.append(Path(md.db_path).parent)
    mm = bare("parity")
    pid = md.add_palace("路线")
    lid = md.add_locus(pid, "桩")
    iid = md.add_item(front="要记的", palace_id=pid, locus_id=lid)
    mid = mm.add_map("要画的")

    seq = (["known", "known", "vague", "forgot", "known", "known", "known",
            "known", "vague", "vague", "forgot", "known"] * 2)
    bad = []
    for i, feedback in enumerate(seq):
        today = tc.shift_date("2026-10-01", i)
        a = md.record_review(iid, feedback, today=today)
        b = mm.record_review(mid, feedback, today=today)
        if (int(a["mastery"]), int(a["correct_streak"]), int(a["interval_days"]),
                a["next_review_at"]) != (int(b["mastery"]), int(b["correct_streak"]),
                                         int(b["interval_days"]), b["next_review_at"]):
            bad.append((i, feedback, a, b))
    check("24 步反馈序列：两边的三键与到期日逐格一致", not bad, bad[:2])
    check("两边各写了 24 行流水",
          len(md.list_reviews(item_id=iid)) == 24
          and len(mm.list_reviews(map_id=mid)) == 24,
          (len(md.list_reviews(item_id=iid)), len(mm.list_reviews(map_id=mid))))

    # 封顶：一路记得，间隔必须停在 120
    mid2 = mm.add_map("长跑")
    reached = []
    for i in range(16):
        mm.record_review(mid2, tc.FEEDBACK_KNOWN, today=tc.shift_date("2026-11-01", i))
        reached.append(int(mm.get_progress(mid2)["interval_days"]))
    check("一路记得：间隔单调不减并封顶 120",
          reached == sorted(reached) and reached[-1] == 120 and max(reached) == 120,
          reached)


# ══════════════════════════════════════════════════════════════════════════
# B. 种子一致性
# ══════════════════════════════════════════════════════════════════════════
def test_seed() -> None:
    section("[B] 种子一致性")
    counts = mindmap_seed.counts()
    check("教学卡 ≥ 8 张", counts["cards"] >= mindmap_seed.MIN_CARDS, counts)
    check("模板 ≥ 8 套", counts["templates"] >= mindmap_seed.MIN_TEMPLATES, counts)

    check("教学卡码唯一",
          len({c["code"] for c in mindmap_seed.TEACHING_CARDS})
          == len(mindmap_seed.TEACHING_CARDS))
    check("模板码唯一",
          len({t["code"] for t in mindmap_seed.TEMPLATES})
          == len(mindmap_seed.TEMPLATES))
    check("教学卡字段齐全",
          all({"code", "title", "category", "body", "tip", "practice"} <= set(c)
              for c in mindmap_seed.TEACHING_CARDS))
    check("模板字段齐全",
          all({"code", "name", "category", "description", "outline"} <= set(t)
              for t in mindmap_seed.TEMPLATES))
    check("模板码都带 TPL_ 前缀",
          all(str(t["code"]).startswith("TPL_") for t in mindmap_seed.TEMPLATES),
          [t["code"] for t in mindmap_seed.TEMPLATES])

    # 每个模板的大纲都要能解析成「有中心主题 + 至少两条分支」的树
    thin, bad = [], []
    for tpl in mindmap_seed.TEMPLATES:
        try:
            tree = ml.parse_outline(tpl["outline"])
        except Exception as exc:                     # noqa: BLE001
            bad.append((tpl["code"], f"{type(exc).__name__}: {exc}"))
            continue
        if not str(tree["text"]).strip() or len(_kids(tree, tree)) < 2:
            thin.append((tpl["code"], tree["text"], len(_kids(tree, tree))))
    check("每个模板大纲都能解析出中心主题与 ≥2 条分支", not bad and not thin,
          (bad[:2], thin[:2]))
    check("模板大纲首行非空且各不相同",
          len({t["outline"].splitlines()[0].strip() for t in mindmap_seed.TEMPLATES})
          == len(mindmap_seed.TEMPLATES))
    check("模板名与「大纲首行」允许不同（列表名可以更长）",
          any(t["name"] != t["outline"].splitlines()[0].strip()
              for t in mindmap_seed.TEMPLATES))

    check("card_categories 非空", len(mindmap_seed.card_categories()) > 0)
    check("template_categories 非空", len(mindmap_seed.template_categories()) > 0)
    check("get_card 命中 / 未命中",
          mindmap_seed.get_card(mindmap_seed.TEACHING_CARDS[0]["code"]) is not None
          and mindmap_seed.get_card("NOPE") is None)
    check("get_template 命中 / 未命中",
          mindmap_seed.get_template(mindmap_seed.TEMPLATES[0]["code"]) is not None
          and mindmap_seed.get_template("NOPE") is None)

    info = mindmap_seed.validate()
    check("装载自检返回统计且与 counts() 对得上",
          int(info["cards"]) == int(counts["cards"])
          and int(info["templates"]) == int(counts["templates"]), info)


# ══════════════════════════════════════════════════════════════════════════
# C. 建表与幂等
# ══════════════════════════════════════════════════════════════════════════
def test_schema() -> None:
    section("[C] 建表与幂等")
    import sqlite3
    db = fresh("schema")
    with sqlite3.connect(db.db_path) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    need = {"mindmap", "mindmap_nodes", "mindmap_progress", "mindmap_reviews",
            "mindmap_checkins"}
    check("五张表齐备", need <= names, sorted(need - names))

    check("构造时就灌好模板导图",
          db.count_maps() == len(mindmap_seed.TEMPLATES), db.count_maps())
    check("模板导图带 source_key（tpl: 前缀）",
          all(db.get_map_by_source(f"tpl:{t['code']}") is not None
              for t in mindmap_seed.TEMPLATES))
    check("重跑 seed_templates 不重复建", db.seed_templates() == 0)

    db2 = MindmapDB(db.db_path)
    check("重开一次总数不变",
          db2.count_maps() == len(mindmap_seed.TEMPLATES), db2.count_maps())

    # 自建导图 source_key 为空 -> 不参与部分唯一索引，同名可以建很多张
    a = db.add_map("同名")
    b = db.add_map("同名")
    check("自建同名导图不冲突（source_key 为空不进唯一索引）",
          a != b and len([m for m in db.list_maps(keyword="同名")]) == 2,
          len(db.list_maps(keyword="同名")))

    # 新图一建出来就有中心主题（load_tree 不该落到「未命名导图」兜底）
    m = db.get_map(a)
    check("add_map 后 title 与中心主题一致",
          db.load_tree(a)["text"] == m["title"] == "同名",
          (m["title"], db.load_tree(a)["text"]))
    check("新图恰好 1 个节点（只有中心主题）", db.node_count(a) == 1,
          db.node_count(a))
    check("空标题兜底为默认名",
          db.get_map(db.add_map("   "))["title"] == mindmap_db.DEFAULT_MAP_TITLE)

    # 老库（只有 mindmap 表）升级时不该被动
    old_dir = Path(tempfile.mkdtemp(prefix="mm_old_"))
    _TMP.append(old_dir)
    old_path = old_dir / "old.db"
    with sqlite3.connect(old_path) as conn:
        conn.execute("CREATE TABLE mindmap (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "title TEXT NOT NULL, root_note TEXT NOT NULL DEFAULT '', "
                     "category TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', "
                     "source_key TEXT NOT NULL DEFAULT '', "
                     "created_at TEXT NOT NULL DEFAULT '', "
                     "updated_at TEXT NOT NULL DEFAULT '')")
        conn.execute("INSERT INTO mindmap (title) VALUES ('老图')")
    old = MindmapDB(old_path)
    check("老库里老数据原封不动", old.get_map(1)["title"] == "老图")
    check("老库被补上新表", old.count_maps() >= 1)


# ══════════════════════════════════════════════════════════════════════════
# D. 导图 CRUD
# ══════════════════════════════════════════════════════════════════════════
def test_map_crud() -> None:
    section("[D] 导图 CRUD")
    db = bare("crud")
    check("空库没有导图", db.count_maps() == 0)

    mid = db.add_map("周计划", root_note="一周的方向", category="时间管理",
                     tags="计划|周")
    row = db.get_map(mid)
    check("新建导图字段齐全",
          row and row["title"] == "周计划" and row["category"] == "时间管理"
          and row["tags"] == "计划|周" and row["root_note"] == "一周的方向", row)
    check("get_map 找不到返回 None", db.get_map(99999) is None)

    check("update_map 生效并返回 True",
          db.update_map(mid, category="工作", tags="周") is True)
    check("update_map 读回来是新值",
          db.get_map(mid)["category"] == "工作" and db.get_map(mid)["tags"] == "周")
    check("update_map 空参数返回 False", db.update_map(mid) is False)
    check("update_map 不认的字段被忽略（不报错）",
          db.update_map(mid, 不存在的字段="x") is False)

    # 改名要同步中心主题（两者本就是一回事）
    check("rename_map 生效", db.rename_map(mid, "周计划 v2") is True)
    check("rename_map 同步中心主题",
          db.get_map(mid)["title"] == "周计划 v2"
          and db.root_node(mid)["text"] == "周计划 v2",
          db.root_node(mid)["text"])
    check("rename_map 空标题返回 False", db.rename_map(mid, "  ") is False)

    # 关键词命中 title / root_note / tags / 节点文字
    root = db.root_node(mid)
    db.add_node(mid, root["id"], "独特的节点文字")
    hit_node = db.add_map("另一张")
    check("关键词命中 title", mid in _ids(db.list_maps(keyword="周计划")))
    check("关键词命中 root_note", mid in _ids(db.list_maps(keyword="方向")))
    check("关键词命中 tags", mid in _ids(db.list_maps(keyword="周")))
    check("关键词命中节点文字", mid in _ids(db.list_maps(keyword="独特")))
    check("关键词不误伤别的图", mid not in _ids(db.list_maps(keyword="另一张")))

    check("按分类筛选", _ids(db.list_maps(category="工作")) == [mid],
          _ids(db.list_maps(category="工作")))
    check("categories 去重排序", db.categories() == ["工作"], db.categories())
    check("limit 生效", len(db.list_maps(limit=1)) == 1)

    # 列表行必须带 node_count / branch_count / 进度列
    item = next(m for m in db.list_maps() if int(m["id"]) == mid)
    check("list_maps 行带 node_count / branch_count / mastery / bucket",
          {"node_count", "branch_count", "mastery", "correct_streak",
           "interval_days", "next_review_at", "review_count", "bucket", "due"}
          <= set(item), sorted(item))
    tree = db.load_tree(mid)
    check("node_count 与库里一致", int(item["node_count"]) == db.node_count(mid))
    check("branch_count = 一级分支数",
          int(item["branch_count"]) == len(_kids(tree, tree)),
          (item["branch_count"], len(_kids(tree, tree))))
    check("新图 bucket=new（不是被内连接滤掉）",
          item["bucket"] == "new" and item["due"] is False,
          (item["bucket"], item["due"]))

    # 按模板新建：是可编辑的普通导图，改它不影响模板本体
    tpl_code = mindmap_seed.TEMPLATES[0]["code"]
    tpl_before = db.get_template(tpl_code)["outline"]
    made = db.create_from_template(tpl_code)
    check("create_from_template 出的图标题 = 模板大纲首行",
          db.get_map(made)["title"]
          == tpl_before.splitlines()[0].strip(), db.get_map(made)["title"])
    db.rename_map(made, "改过的")
    check("改模板图不影响模板本体",
          db.get_template(tpl_code)["outline"] == tpl_before)
    check("create_from_template 重复调用建出两张独立图",
          db.create_from_template(tpl_code) != made)
    try:
        db.create_from_template("NOPE")
        bad = False
    except KeyError:
        bad = True
    check("不存在的模板抛 KeyError", bad)

    # 删图要级联清掉节点 / 进度 / 流水
    db.record_review(mid, tc.FEEDBACK_KNOWN, today="2026-09-28")
    check("删前有节点与流水",
          db.node_count(mid) > 0 and len(db.list_reviews(map_id=mid)) == 1)
    check("delete_map 返回 True", db.delete_map(mid) is True)
    check("delete_map 级联清掉节点 / 进度 / 流水",
          db.node_count(mid) == 0 and len(db.list_reviews(map_id=mid)) == 0
          and db.get_progress(mid)["review_count"] == 0)
    check("delete_map 后再删返回 False", db.delete_map(mid) is False)
    check("剩下的图没被误删", int(hit_node) in _ids(db.list_maps()))


# ══════════════════════════════════════════════════════════════════════════
# E. 大纲 <-> 树
# ══════════════════════════════════════════════════════════════════════════
def test_outline() -> None:
    section("[E] 大纲 <-> 树")
    check("空输入给空树（默认名）",
          ml.count_nodes(ml.parse_outline("")) == 1
          and ml.parse_outline("")["text"] == "中心主题")
    check("空输入可用 root_text 指定中心主题",
          ml.parse_outline("   \n\n", root_text="我的").get("text") == "我的")

    # 两种缩进写法都认（缩进是相对的）
    tight = "标题\n  分支A\n  分支B\n    子A1"
    loose = "  标题\n    分支A\n    分支B\n      子A1"
    ta, tb = ml.parse_outline(tight), ml.parse_outline(loose)
    check("顶格写法与整体缩进写法结构等价",
          ml.outline_text(ta) == ml.outline_text(tb)
          and _texts(ta, 1) == ["分支A", "分支B"]
          and _texts(ta, 2) == ["子A1"],
          (ml.outline_text(ta), _texts(tb, 1)))

    # 缩进回退：深层节点缩进回到浅层，要挂到正确的祖先下
    tree = ml.parse_outline("根\n  A\n    A1\n    A2\n  B\n    B1")
    check("缩进回退后挂到正确祖先",
          _texts(tree, 1) == ["A", "B"] and _texts(tree, 2) == ["A1", "A2", "B1"],
          (_texts(tree, 1), _texts(tree, 2)))

    # 项目符号剥离 + 空行忽略（首行 # 当中心主题）
    tree = ml.parse_outline("# 根\n\n- A\n  * A1\n    1. A1a\n  + A2\n- B\n")
    check("项目符号（# - * + 序号）被剥掉",
          _texts(tree, 1) == ["A", "B"] and _texts(tree, 2) == ["A1", "A2"]
          and _texts(tree, 3) == ["A1a"],
          (_texts(tree, 1), _texts(tree, 2), _texts(tree, 3)))
    # Tab 按 4 空格展开：一个 Tab 是第 1 层，两个 Tab 是第 2 层
    tabbed = ml.parse_outline("根\n\tA\n\t\tB\n\tC")
    check("Tab 按 4 空格展开",
          _texts(tabbed, 1) == ["A", "C"] and _texts(tabbed, 2) == ["B"],
          (_texts(tabbed, 1), _texts(tabbed, 2)))

    # 往返：outline_text -> parse_outline -> outline_text 稳定
    src = ml.parse_outline(mindmap_seed.TEMPLATES[0]["outline"])
    once = ml.outline_text(src)
    check("大纲往返稳定",
          ml.outline_text(ml.parse_outline(once)) == once)
    check("往返后节点数不变",
          ml.count_nodes(ml.parse_outline(once)) == ml.count_nodes(src))
    check("indent_step 可调（第 2 行的前导空格数）",
          ml.outline_text(src, indent_step=4).splitlines()[1].startswith("    ")
          and ml.outline_text(src, indent_step=2).splitlines()[1].startswith("  ")
          and not ml.outline_text(src, indent_step=2).splitlines()[1].startswith("   "),
          (ml.outline_text(src, indent_step=4).splitlines()[:2],
           ml.outline_text(src, indent_step=2).splitlines()[:2]))

    # ── 落库：id 认领三步 ────────────────────────────────────────────
    db = bare("outline")
    mid = db.add_map("根")
    root = db.root_node(mid)
    a = db.add_node(mid, root["id"], "A")
    a1 = db.add_node(mid, a, "A1")
    b = db.add_node(mid, root["id"], "B")

    text = db.load_outline(mid)
    check("load_outline 首行是中心主题", text.splitlines()[0] == "根", text)
    stats = db.save_outline_text(mid, text)
    check("纯文本重存：文字没变就全部认回原行",
          int(stats["reused"]) == 4 and int(stats["inserted"]) == 0
          and int(stats["removed"]) == 0, stats)
    # list_nodes 的顺序是 depth, parent_id, seq, id —— 不是 id 升序，所以比集合
    check("重存后节点 id 一个都没换",
          set(_ids(db.list_nodes(mid)))
          == {int(root["id"]), int(a), int(a1), int(b)}
          and db.node_count(mid) == 4,
          _ids(db.list_nodes(mid)))

    stats = db.save_outline_text(mid, "根\n  A\n    A1\n  B\n  C")
    check("加一行 = 1 个 insert", int(stats["inserted"]) == 1, stats)
    check("加的那行挂成了第 3 条一级分支",
          _texts(db.load_tree(mid), 1) == ["A", "B", "C"],
          _texts(db.load_tree(mid), 1))

    stats = db.save_outline_text(mid, "根\n  A\n  C")
    check("删一行 = 1 个 removed（子树一起走）",
          int(stats["removed"]) == 2, stats)
    check("删完节点数与树一致",
          db.node_count(mid) == ml.count_nodes(db.load_tree(mid)) == 3,
          db.node_count(mid))

    # 改一行文字：改的那行认不出，其余保住
    before_ids = set(_ids(db.list_nodes(mid)))
    db.save_outline_text(mid, "根\n  A 改过\n  C")
    after_ids = set(_ids(db.list_nodes(mid)))
    check("改文字只换掉那一行的 id",
          len(after_ids) == 3 and len(before_ids & after_ids) == 2,
          (sorted(before_ids), sorted(after_ids)))

    # 标题与中心主题始终一致
    db.save_outline_text(mid, "新的中心主题\n  分支")
    check("save_outline 把标题与中心主题对齐",
          db.get_map(mid)["title"] == "新的中心主题"
          and db.root_node(mid)["text"] == "新的中心主题")

    check("load_tree 对没节点的图给兜底树",
          ml.count_nodes(db.load_tree(db.add_map("空图"))) == 1)


# ══════════════════════════════════════════════════════════════════════════
# F. 布局算法
# ══════════════════════════════════════════════════════════════════════════
def test_layout() -> None:
    section("[F] 布局算法")
    db = fresh("layout")
    mid = db.create_from_template("TPL_PYRAMID")
    tree = db.load_tree(mid)

    check("count_nodes 与库一致", ml.count_nodes(tree) == db.node_count(mid))
    check("max_depth = 0 层的根之外最深",
          ml.max_depth(tree) == max(d for _n, _p, d in ml.iter_nodes(tree)))
    check("width_of = 同层最多节点数",
          ml.width_of(tree) == max(
              sum(1 for _n, _p, d in ml.iter_nodes(tree) if d == level)
              for level in range(ml.max_depth(tree) + 1)))
    check("level_texts(0) 就是中心主题",
          _texts(tree, 0) == [tree["text"]], _texts(tree, 0))

    L = ml.layout(tree)
    check("未折叠时参与排布的节点数 = 树节点数",
          len(L["nodes"]) == ml.count_nodes(tree), len(L["nodes"]))
    check("edges = 节点数 - 1",
          len(L["edges"]) == ml.count_nodes(tree) - 1, len(L["edges"]))
    check("size 为正", L["size"][0] > 0 and L["size"][1] > 0, L["size"])
    check("bounds 与 size 对得上",
          abs((L["bounds"][2] - L["bounds"][0]) - L["size"][0]) < 1e-6
          and abs((L["bounds"][3] - L["bounds"][1]) - L["size"][1]) < 1e-6,
          (L["bounds"], L["size"]))
    check("by_iid 与 nodes 一一对应",
          len(L["by_iid"]) == len(L["nodes"])
          and all(L["by_iid"][r["iid"]] is r for r in L["nodes"]))
    check("layout_size 与 layout()['size'] 相同",
          ml.layout_size(tree) == L["size"])

    # 每层一列：同层 x 相同，且随 depth 递增
    by_depth: dict = {}
    for r in L["nodes"]:
        by_depth.setdefault(r["depth"], []).append(r)
    same_col = all(len({round(r["x"], 6) for r in rs}) == 1
                   for rs in by_depth.values())
    xs = [by_depth[d][0]["x"] for d in sorted(by_depth)]
    check("每层一列（同层 x 相同）", same_col, [sorted({round(r['x'], 3) for r in rs}) for rs in by_depth.values()][:3])
    check("x 随层级递增（列从左往右）", xs == sorted(xs) and len(set(xs)) == len(xs), xs)

    # 同层不重叠
    gap = ml.NODE_H + ml.V_GAP
    overlap = []
    for depth, rs in by_depth.items():
        ys = sorted(r["y"] for r in rs)
        for y1, y2 in zip(ys, ys[1:]):
            if y2 - y1 < gap - 1e-6:
                overlap.append((depth, y1, y2, y2 - y1))
    check("同层相邻节点不重叠（间距 ≥ 行高 + 纵向净距）", not overlap, overlap[:3])

    # 父节点居中于子树
    by_key = {r["key"]: r for r in L["nodes"] if r["key"] is not None}
    off = []
    for node, _p, _d in ml.iter_nodes(tree):
        kids = _kids(tree, node)
        if node.get("collapsed") or not kids:
            continue
        ys = [by_key[int(c["id"])]["y"] for c in kids]
        if abs(by_key[int(node["id"])]["y"] - (min(ys) + max(ys)) / 2.0) > 1e-6:
            off.append(node["text"])
    check("父节点正好居中于子树", not off, off[:3])

    # 折叠：参与排布的节点变少、高度收紧、该节点带「+n」徽标。
    # 必须挑一条**真的有孩子**的分支 —— 拿叶子节点折叠，什么都不会变
    # （TPL_PYRAMID 的第一条分支恰好就是叶子，这里曾经踩过）。
    branch = next(n for n in _kids(tree, tree) if _kids(tree, n))
    hidden = _subtree_size(branch) - 1
    db.set_collapsed(int(branch["id"]), True)
    folded = db.load_tree(mid)
    L2 = ml.layout(folded)
    check("折叠后参与排布的节点减少 = 子树大小 - 1",
          len(L2["nodes"]) == len(L["nodes"]) - hidden,
          (len(L["nodes"]), len(L2["nodes"]), hidden))
    check("折叠后总高度收紧", L2["size"][1] < L["size"][1],
          (L["size"][1], L2["size"][1]))
    rec = ml.find_node(folded, int(branch["id"]))
    check("折叠节点自己的 collapsed = True", rec.get("collapsed") is True)
    frec = next(r for r in L2["nodes"] if r["key"] == int(branch["id"]))
    check("折叠节点带 hidden_children 与徽标宽度",
          int(frec["hidden_children"]) == len(_kids(tree, branch))
          and int(frec["badge_w"]) == ml.COLLAPSED_BADGE_W
          and int(frec["w"]) > int(frec["text_w"]),
          (frec["hidden_children"], frec["badge_w"], frec["w"], frec["text_w"]))

    # 只有根：不炸
    only_root = ml.layout(ml.empty_tree("只有根"))
    check("只有中心主题时也不炸",
          len(only_root["nodes"]) == 1 and only_root["size"][1] == ml.NODE_H,
          only_root["size"])

    # 连线 / 颜色
    p = only_root["nodes"][0]
    check("只有中心主题时节点落在原点",
          float(p["x"]) == 0.0 and float(p["y"]) == 0.0, (p["x"], p["y"]))
    check("edge_points 从父右中点到子左中点",
          ml.edge_points({"x": 0, "y": 0, "w": 100, "h": 32},
                         {"x": 158, "y": 10, "w": 10, "h": 32})
          == (100, 16.0, 158, 26.0))
    pts = ml.curve_points(0, 0, 100, 50)
    check("curve_points 点数 = (steps+1)*2 且端点是 (x1,y1)/(x2,y2)",
          len(pts) == 26 and (pts[0], pts[1]) == (0, 0)
          and (pts[-2], pts[-1]) == (100, 50), (len(pts), pts[:2], pts[-2:]))
    check("层级配色不循环（深层取最后一档，不回春）",
          ml.depth_color(0) == ml.DEPTH_COLORS[0]
          and ml.depth_color(99) == ml.DEPTH_COLORS[-1]
          and ml.depth_color(999) != ml.DEPTH_COLORS[0])
    check("measure_text：汉字算 2 个半角宽、不低于最小宽",
          ml.measure_text("中") == ml.NODE_MIN_W
          and ml.measure_text("中文五个字啊啊啊") > ml.measure_text("aaaa"))


# ══════════════════════════════════════════════════════════════════════════
# G. 结构操作
# ══════════════════════════════════════════════════════════════════════════
def test_structure() -> None:
    section("[G] 结构操作")
    db = bare("struct")
    mid = db.add_map("根")
    root = db.root_node(mid)
    a = db.add_node(mid, root["id"], "A")
    a1 = db.add_node(mid, a, "A1")
    db.add_node(mid, a, "A2")
    b = db.add_node(mid, root["id"], "B")
    c = db.add_node(mid, root["id"], "C")
    check("初始结构", _texts(db.load_tree(mid), 1) == ["A", "B", "C"]
          and _texts(db.load_tree(mid), 2) == ["A1", "A2"])

    kid_seqs = [int(r["seq"]) for r in db.list_nodes(mid)
                if int(r["parent_id"]) == int(a)]
    check("add_node 作为最后一个孩子追加（seq 递增）",
          kid_seqs == [0, 1], kid_seqs)
    check("add_node 的 depth = 父 + 1（A 是 1 层，A1 就是 2 层）",
          int(db._node_row(a)["depth"]) == 1
          and int(db._node_row(a1)["depth"]) == 2
          and int(root["id"]) == int(db._node_row(int(a))["parent_id"])
          and int(a) == int(db._node_row(a1)["parent_id"]),
          (db._node_row(a)["depth"], db._node_row(a1)["depth"]))

    # update_node
    check("update_node 改文字", db.update_node(a1, text="A1 改") is True)
    check("update_node 空参数返回 False", db.update_node(a1) is False)
    check("update_node 不认的字段被忽略", db.update_node(a1, nope="x") is False)
    check("update_node collapsed 会被转成 0/1",
          db.update_node(a1, collapsed=True) is True
          and int(db._node_row(a1)["collapsed"]) == 1)
    db.update_node(a1, collapsed=False)

    # 移动
    check("move_node(-1) 与邻居换位", db.move_node(b, -1) is True
          and _texts(db.load_tree(mid), 1) == ["B", "A", "C"],
          _texts(db.load_tree(mid), 1))
    check("move_node 到顶返回 False", db.move_node(b, -1) is False)
    check("move_node 到底返回 False", db.move_node(c, 1) is False)
    check("移动不丢节点", db.node_count(mid) == 6, db.node_count(mid))

    # 缩进 / 反缩进
    check("第一条兄弟没法降级（返回 False）", db.indent_node(b, out=False) is False)
    check("非第一条降级：成为上一个兄弟的孩子",
          db.indent_node(a, out=False) is True
          and int(db._node_row(a)["parent_id"]) == b
          and _texts(db.load_tree(mid), 1) == ["B", "C"],
          (_texts(db.load_tree(mid), 1), db._node_row(a)["parent_id"]))
    check("降级不丢节点", db.node_count(mid) == 6, db.node_count(mid))

    check("**第一层反缩进被拦下**（不会凭空冒出第二个根）",
          db.indent_node(b, out=True) is False
          and _texts(db.load_tree(mid), 1) == ["B", "C"],
          (_texts(db.load_tree(mid), 1), db.list_nodes(mid)))
    check("反缩进到根后不存在 parent_id = 0 的多余根",
          len([r for r in db.list_nodes(mid) if int(r["parent_id"]) == 0]) == 1)
    check("第二层反缩进正常（A 从 B 下提到根）",
          db.indent_node(a, out=True) is True
          and int(db._node_row(a)["parent_id"]) == int(root["id"])
          and "A" in _texts(db.load_tree(mid), 1),
          _texts(db.load_tree(mid), 1))

    # 删除
    check("delete_node(默认) 连子孙一起删",
          db.delete_node(a) is True and db.node_count(mid) == 3,
          db.node_count(mid))
    d1 = db.add_node(mid, root["id"], "D")
    d1c = db.add_node(mid, d1, "D1")
    check("delete_node(keep_children=True) 孩子提一级",
          db.delete_node(d1, keep_children=True) is True
          and int(db._node_row(d1c)["parent_id"]) == int(root["id"])
          and db._node_row(d1) is None,
          (db._node_row(d1c), db._node_row(d1)))
    check("删不存在的节点返回 False", db.delete_node(999999) is False)

    # 每一步之后，库与树必须仍然一致。
    # 注意：树节点上**没有** depth（那是 mindmap_nodes 的列），
    # 所以要拿 DFS 算出来的层数去比库行，别去树节点上取。
    rows = db.list_nodes(mid)
    tree = db.load_tree(mid)
    depth_ok, seq_ok = True, True
    for node, parent, depth in ml.iter_nodes(tree):
        row = db._node_row(int(node["id"]))
        if int(row["depth"]) != depth:
            depth_ok = False
        siblings = _kids(tree, parent) if parent is not None else [tree]
        sib_ids = [int(c["id"]) for c in siblings]
        if int(row["seq"]) != sib_ids.index(int(node["id"])):
            seq_ok = False
    check("库与树一致：节点数 / depth / seq 都对得上",
          ml.count_nodes(tree) == db.node_count(mid) == len(rows)
          and depth_ok and seq_ok,
          (ml.count_nodes(tree), db.node_count(mid), len(rows), depth_ok, seq_ok))

    # _subtree_ids 是递归的（删一层再删一层会让孙子的 parent 悬空）
    big = db.add_node(mid, root["id"], "大枝")
    b1 = db.add_node(mid, big, "中枝")
    b2 = db.add_node(mid, b1, "小枝")
    check("_subtree_ids 一次查完三代",
          set(db._subtree_ids(big)) == {big, b1, b2}, db._subtree_ids(big))
    db.delete_node(big)
    check("删三代只留根与既有节点",
          db.node_count(mid) == db.node_count(mid)
          and all(db._node_row(x) is None for x in (big, b1, b2)))


# ══════════════════════════════════════════════════════════════════════════
# H. 间隔重复
# ══════════════════════════════════════════════════════════════════════════
def test_srs() -> None:
    section("[H] 间隔重复（对象是整张图）")
    db = bare("srs")
    mid = db.add_map("图")

    check("get_progress 不存在时给默认值（读操作无副作用）",
          db.get_progress(mid)["mastery"] == 0
          and db.get_progress(mid)["next_review_at"] == "")
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM mindmap_progress").fetchone()[0]
    check("只读不落库", n == 0, n)

    db.ensure_progress(mid)
    db.ensure_progress(mid)
    prog = db.get_progress(mid)
    check("ensure_progress 幂等且不写假流水",
          len(db.list_reviews(map_id=mid)) == 0 and int(prog["review_count"]) == 0,
          db.list_reviews(map_id=mid))
    check("ensure_progress 记下 marked_at", str(prog["marked_at"]).strip() != "")
    marked = prog["marked_at"]

    db.record_review(mid, tc.FEEDBACK_KNOWN, today="2026-09-01")
    p = db.get_progress(mid)
    check("记得：掌握度 1、连对 1、间隔 1 天、到期 09-02",
          (int(p["mastery"]), int(p["correct_streak"]), int(p["interval_days"]),
           p["next_review_at"]) == (1, 1, 1, "2026-09-02"), p)
    check("判过之后 marked_at 不被覆盖（它记的是「第一次标记」）",
          p["marked_at"] == marked, (marked, p["marked_at"]))
    check("review_count 累加到 1", int(p["review_count"]) == 1)

    db.record_review(mid, tc.FEEDBACK_KNOWN, today="2026-09-02")
    p = db.get_progress(mid)
    check("连对两次：间隔 3 天、到期 09-05",
          (int(p["correct_streak"]), int(p["interval_days"]),
           p["next_review_at"]) == (2, 3, "2026-09-05"), p)
    db.record_review(mid, tc.FEEDBACK_VAGUE, today="2026-09-05")
    p = db.get_progress(mid)
    check("模糊：连对 -1、间隔减半、掌握度不低于生疏",
          int(p["correct_streak"]) == 1 and int(p["interval_days"]) == 1
          and int(p["mastery"]) >= tc.MASTERY_WEAK, p)
    db.record_review(mid, tc.FEEDBACK_FORGOT, today="2026-09-06")
    p = db.get_progress(mid)
    check("忘了：连对归零、间隔回 1 天、掌握度 -1",
          (int(p["correct_streak"]), int(p["interval_days"]),
           int(p["mastery"])) == (0, 1, 1), p)
    check("一次调用恰好一行流水", len(db.list_reviews(map_id=mid)) == 4,
          len(db.list_reviews(map_id=mid)))
    check("review_count = 流水条数", int(p["review_count"]) == 4, p["review_count"])

    # 分支命中率随流水落库（盲画特有）
    mid2 = db.add_map("带分支统计")
    db.record_review(mid2, tc.FEEDBACK_KNOWN, today="2026-09-07",
                     branch_hit=4, branch_total=5)
    row = db.list_reviews(map_id=mid2)[0]
    check("branch_hit / branch_total 落库",
          int(row["branch_hit"]) == 4 and int(row["branch_total"]) == 5, row)
    acc = db.review_accuracy(days=400, today="2026-10-20")
    check("正确率 = 记得 / 总流水",
          acc["reviewed"] == len(db.list_reviews())
          and abs(acc["accuracy"] - acc["correct"] / max(1, acc["reviewed"])) < 1e-9,
          acc)

    # set_mastery：手动标记不写流水，标生疏即排到今天
    mid3 = db.add_map("手标")
    db.set_mastery(mid3, tc.MASTERY_WEAK, today="2026-09-28")
    p3 = db.get_progress(mid3)
    check("手动标生疏：排到今天（立刻进盲画队列）",
          p3["next_review_at"] == "2026-09-28", p3)
    check("手动标记不算一次盲画（不写流水）",
          len(db.list_reviews(map_id=mid3)) == 0
          and int(p3["review_count"]) == 0)
    db.set_mastery(mid3, 99)
    check("掌握度越界被夹到 3", int(db.get_progress(mid3)["mastery"]) == 3)
    db.set_mastery(mid3, -5)
    check("掌握度负数被夹到 0 且清空排期",
          int(db.get_progress(mid3)["mastery"]) == 0
          and db.get_progress(mid3)["next_review_at"] == "")

    # due 队列两把尺子（和记忆宫殿同一口径）
    db2 = bare("due")
    ids = [db2.add_map(f"图{i}") for i in range(3)]
    check("准备了三张互相独立的全新导图",
          len(ids) == 3 and len(set(ids)) == 3, ids)
    today_items = db2.due_maps(today="2026-09-28")
    check("**懒创建防线**：全新图全都进今日盲画队列（没被内连接滤掉）",
          len(today_items) == 3
          and all(m["bucket"] == "new" for m in today_items),
          [m["bucket"] for m in today_items])
    check("due_count 只数已到期：全新图不算 due（另有 new_candidates）",
          db2.due_count(today="2026-09-28") == 0
          and len(db2.new_candidates()) == 3,
          (db2.due_count(today="2026-09-28"), len(db2.new_candidates())))
    check("stats['due'] 就是 due_count",
          db2.stats(today="2026-09-28")["due"]
          == db2.due_count(today="2026-09-28"))
    check("新图排在已到期图之后（列表先后）",
          [m["bucket"] for m in db2.due_maps(today="2026-09-28")]
          == ["new", "new", "new"])

    first = int(today_items[0]["id"])
    db2.record_review(first, tc.FEEDBACK_KNOWN, today="2026-09-28")
    check("排到明天的那张，当天就退出队列",
          len(db2.due_maps(today="2026-09-28")) == 2
          and first not in _ids(db2.due_maps(today="2026-09-28")),
          _ids(db2.due_maps(today="2026-09-28")))
    check("第二天它变成「到期」，due_count 才 +1",
          db2.due_count(today="2026-09-29") == 1
          and len(db2.due_maps(today="2026-09-29")) == 3,
          (db2.due_count(today="2026-09-29"),
           len(db2.due_maps(today="2026-09-29"))))
    check("new_candidates 只给从没排过期的", len(db2.new_candidates()) == 2)
    check("掌握度分布以全部导图为分母",
          sum(db2.mastery_distribution().values()) == db2.count_maps(),
          (db2.mastery_distribution(), db2.count_maps()))
    check("suggest_new_count 有下限（不会归零到负数）",
          ml.suggest_new_count(due_total=0) == ml.SUGGEST_NEW_PER_DAY
          and ml.suggest_new_count(due_total=10**6) == 0
          and ml.suggest_new_count(due_total=1, target_new=7) == 7,
          [ml.suggest_new_count(due_total=x) for x in (0, 10, 30, 10**6)])
    check("mindmap_db.suggest_new_count 与布局层同源",
          mindmap_db.suggest_new_count(due_total=0)
          == ml.suggest_new_count(due_total=0))


# ══════════════════════════════════════════════════════════════════════════
# I. 打卡统计
# ══════════════════════════════════════════════════════════════════════════
def test_checkins() -> None:
    section("[I] 打卡统计")
    db = bare("checkins")
    db.add_map("图")

    rec = db.checkin("2026-09-28", minutes=25, maps_new=2, maps_reviewed=3,
                     accuracy=0.8, note="第一句")
    check("打卡字段齐全",
          rec and rec["check_date"] == "2026-09-28" and int(rec["minutes"]) == 25
          and int(rec["maps_new"]) == 2 and int(rec["maps_reviewed"]) == 3
          and abs(float(rec["accuracy"]) - 0.8) < 1e-9 and rec["note"] == "第一句",
          rec)

    db.checkin("2026-09-28", minutes=30)
    rec = db.get_checkin("2026-09-28")
    check("同日重复打卡是**更新**不是新增",
          len(db.list_checkins()) == 1 and int(rec["minutes"]) == 30, rec)
    check("只传 minutes 时其余字段不被清零",
          int(rec["maps_new"]) == 2 and int(rec["maps_reviewed"]) == 3
          and rec["note"] == "第一句", rec)

    db.checkin("2026-09-28", note="第二句")
    check("只传 note 时数字不被清零",
          int(db.get_checkin("2026-09-28")["minutes"]) == 30
          and db.get_checkin("2026-09-28")["note"] == "第二句")
    check("get_checkin 找不到返回 None", db.get_checkin("2000-01-01") is None)

    for day in ("2026-09-26", "2026-09-27", "2026-09-28"):
        db.checkin(day, minutes=10)
    check("checkin_dates 升序", db.checkin_dates() == ["2026-09-26", "2026-09-27",
                                                       "2026-09-28"],
          db.checkin_dates())
    st = db.stats(today="2026-09-28")
    check("连续天数 3 天", int(st["streak"]) == 3, st["streak"])
    check("今天没打卡不算断（从昨天数起）",
          int(db.stats(today="2026-09-29")["streak"]) == 3,
          db.stats(today="2026-09-29")["streak"])
    check("隔了一天就断",
          int(db.stats(today="2026-10-01")["streak"]) == 0,
          db.stats(today="2026-10-01")["streak"])

    # checkin_grid 每行是 {"monday", "label", "cells"}；格子在外层键 cells 里
    grid = tc.checkin_grid(db.checkin_dates(), today="2026-09-28", weeks=5)
    check("打卡日历 5 周 × 7 天",
          len(grid) == 5 and all(len(r["cells"]) == 7 for r in grid), len(grid))
    check("**按周一对齐**：每行第一格是周一",
          all(r["cells"][0]["date"].weekday() == 0 for r in grid),
          [r["cells"][0]["date"].isoformat() for r in grid])
    check("打过卡的日子被标出来（刚好 3 格）",
          sum(1 for r in grid for c in r["cells"] if c["checked"]) == 3,
          sum(1 for r in grid for c in r["cells"] if c["checked"]))
    check("未来的日子被标成 future（不画数字）",
          any(c["is_future"] for r in grid for c in r["cells"]))
    check("今天有且只有一格被标出来",
          sum(1 for r in grid for c in r["cells"] if c["is_today"]) == 1)
    check("周标题是 一..日",
          tc.weekday_headers() == ("一", "二", "三", "四", "五", "六", "日"))

    # autofill：按今天的实际流水补数字，minutes 留给用户填
    db2 = bare("autofill")
    a = db2.add_map("甲")
    b = db2.add_map("乙")
    db2.record_review(a, tc.FEEDBACK_KNOWN, today="2026-09-28")
    db2.record_review(b, tc.FEEDBACK_FORGOT, today="2026-09-28")
    rec = db2.autofill_today(today="2026-09-28")
    check("autofill：盲画 2 张、正确率 0.5",
          int(rec["maps_reviewed"]) == 2
          and abs(float(rec["accuracy"]) - 0.5) < 1e-9, rec)
    check("autofill 不动 minutes（那是用户自己填的）", int(rec["minutes"]) == 0,
          rec["minutes"])
    rec2 = db2.autofill_today(today="2026-09-28")
    check("autofill 幂等（还是 1 行打卡、数字不变）",
          len(db2.list_checkins()) == 1
          and int(rec2["maps_reviewed"]) == 2, rec2)
    check("new_today 数的是「今天新标记」的图", db2.new_today(today="2026-09-28") == 2,
          db2.new_today(today="2026-09-28"))

    st = db2.stats(today="2026-09-28")
    check("stats 键齐全",
          {"days", "minutes", "maps_new", "maps_reviewed", "avg_minutes",
           "streak", "best_streak", "accuracy", "reviewed", "correct",
           "mastery", "maps", "nodes", "due"} <= set(st), sorted(st))
    check("stats 的 maps 与库一致", int(st["maps"]) == db2.count_maps(), st["maps"])
    check("stats 的 nodes = 全库节点数之和",
          int(st["nodes"]) == sum(db2.node_count(m["id"])
                                  for m in db2.list_maps()), st["nodes"])


# ══════════════════════════════════════════════════════════════════════════
# J. 导出
# ══════════════════════════════════════════════════════════════════════════
def test_export() -> None:
    section("[J] 导出")
    db = bare("export")
    mid = db.add_map("导出图")
    root = db.root_node(mid)
    db.add_node(mid, root["id"], "分支一", note="备注一")
    tricky = db.add_node(mid, root["id"], '带引号"的分支 & 尖括号 <x> / 斜杠')
    db.add_node(mid, tricky, "子分支（括号）与 100%")
    tree = db.load_tree(mid)

    txt, ext, mime = ml.export_bytes(tree, "text")
    check("文本导出：扩展名与 MIME",
          ext == ".txt" and mime == "text/plain", (ext, mime))
    check("文本导出 = 缩进大纲", txt.decode("utf-8") == ml.outline_text(tree))
    check("文本导出可被 parse_outline 读回",
          ml.count_nodes(ml.parse_outline(txt.decode("utf-8"))) == ml.count_nodes(tree))

    md, ext, mime = ml.export_bytes(tree, "markdown")
    check("Markdown 导出：扩展名与 MIME",
          ext == ".md" and mime == "text/markdown", (ext, mime))
    md_text = md.decode("utf-8")
    check("Markdown：中心主题作一级标题、分支作缩进列表",
          md_text.startswith("# 导出图\n") and "\n- 分支一" in md_text
          and "  - " in md_text, md_text[:120])
    check("Markdown 带出节点备注", "—— 备注一" in md_text, md_text[:200])
    check("Markdown 行数 = 1 标题 + 空行 + 全部非根节点",
          len(md_text.rstrip("\n").splitlines())
          == 2 + ml.count_nodes(tree) - 1,
          len(md_text.rstrip("\n").splitlines()))

    opml, ext, mime = ml.export_bytes(tree, "opml")
    check("OPML 导出：扩展名与 MIME",
          ext == ".opml" and mime == "text/x-opml", (ext, mime))
    root_el = ET.fromstring(opml.decode("utf-8"))
    texts = [o.get("text") for o in root_el.iter("outline")]
    check("**OPML 属性值转义正确：含双引号也是合法 XML**",
          texts == [n["text"] for n, _p, _d in ml.iter_nodes(tree)],
          texts)
    check("OPML 根标题往返", root_el.find("head/title").text == tree["text"])
    check("OPML 带出备注（_note 属性）",
          any(o.get("_note") == "备注一" for o in root_el.iter("outline")))
    check("OPML 声明是 2.0", opml.decode("utf-8").startswith(
        '<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0">'))

    check("未知格式退回纯文本",
          ml.export_bytes(tree, "???")[1] == ".txt")

    # 大纲是「一行 = 一个节点」的格式，所以节点文字必须是**单行**：
    # 多行会被拆成两个节点、空文字会被跳过。这两种形状走不到界面上
    # （新建节点用的是占位串），但作为数据层契约要显式钉住。
    lossy = db.add_map("多行文字")
    lr = db.root_node(lossy)
    db.add_node(lossy, lr["id"], "上\n下")
    db.save_outline_text(lossy, db.load_outline(lossy))
    check("多行文字在纯文本往返里会被拆成两个节点（格式所限）",
          db.node_count(lossy) == 3, db.node_count(lossy))
    blank = db.add_map("空文字节点")
    br = db.root_node(blank)
    db.add_node(blank, br["id"], "")
    db.save_outline_text(blank, db.load_outline(blank))
    check("空文字节点在纯文本往返里会被丢掉（格式所限）",
          db.node_count(blank) == 1, db.node_count(blank))

    # 全部模板都要能导出成合法 XML
    db2 = fresh("export_tpl")
    bad = []
    for item in db2.list_maps():
        try:
            ET.fromstring(ml.to_opml(db2.load_tree(item["id"])))
        except Exception as exc:                     # noqa: BLE001
            bad.append((item["title"], f"{type(exc).__name__}: {exc}"))
    check("10 张模板导图的 OPML 全部合法", not bad, bad[:2])


# ══════════════════════════════════════════════════════════════════════════
# K. 盲画
# ══════════════════════════════════════════════════════════════════════════
def test_blind() -> None:
    section("[K] 盲画")
    db = fresh("blind")
    mid = db.create_from_template("TPL_SWOT")
    tree = db.load_tree(mid)

    brief = ml.blind_brief(tree)
    check("blind_brief 键固定为 root/branches/total/depth（**不给分支文字**）",
          set(brief) == {"root", "branches", "total", "depth"}, sorted(brief))
    check("blind_brief 数字对得上",
          brief["root"] == tree["text"]
          and int(brief["branches"]) == len(_kids(tree, tree))
          and int(brief["total"]) == ml.count_nodes(tree)
          and int(brief["depth"]) == ml.max_depth(tree),
          brief)
    check("blind_brief 里没有任何分支文字",
          all(str(v) not in _texts(tree, 1) for v in brief.values()), brief)

    levels = ml.reveal_levels(tree)
    check("reveal_levels 覆盖 1..max_depth",
          [x["level"] for x in levels] == list(range(1, ml.max_depth(tree) + 1)),
          [x["level"] for x in levels])
    check("每层文字与 level_texts 一致",
          all(x["texts"] == _texts(tree, x["level"]) for x in levels))
    check("第一层就是一级分支", levels[0]["texts"] == _texts(tree, 1))
    check("max_level 可以只展开第一层",
          [x["level"] for x in ml.reveal_levels(tree, max_level=1)] == [1])
    check("未折叠的树不藏任何节点",
          sum(len(x["texts"]) for x in levels) == ml.count_nodes(tree) - 1,
          (sum(len(x["texts"]) for x in levels), ml.count_nodes(tree)))

    # **有意设计**：盲画范围**不看** collapsed。折叠只是画布上「先收起这块」，
    # 不该顺手把自己的考试范围也缩小 —— 否则越折叠越容易过关。
    db.set_collapsed(int(_kids(tree, tree)[0]["id"]), True)
    folded = db.load_tree(mid)
    check("盲画范围不因折叠而缩小（折叠只影响画布排布）",
          len(ml.reveal_levels(folded)) == len(levels)
          and int(ml.blind_brief(folded)["total"])
          == int(ml.blind_brief(tree)["total"]),
          (len(ml.reveal_levels(folded)), len(levels)))


# ══════════════════════════════════════════════════════════════════════════
# L. 折叠与状态搬运
# ══════════════════════════════════════════════════════════════════════════
def test_collapse() -> None:
    section("[L] 折叠与状态搬运")
    db = bare("collapse")
    mid = db.add_map("根")
    root = db.root_node(mid)
    a = db.add_node(mid, root["id"], "A")
    a1 = db.add_node(mid, a, "A1")
    db.add_node(mid, a, "A2")
    b = db.add_node(mid, root["id"], "B")
    tree = db.load_tree(mid)

    # iter_nodes 必须给真节点：就地改一下要能看见
    first = next(ml.iter_nodes(tree))[0]
    first["collapsed"] = True
    check("**iter_nodes 产出真节点**（就地改能反映出来）",
          ml.find_node(tree, int(root["id"]))["collapsed"] is True)
    check("find_node 返回的也是真节点",
          ml.find_node(tree, a) is ml.find_node(tree, a))
    check("**find_node(tree, None) 不命中根节点**",
          ml.find_node(tree, None) is None)
    check("按文字查找（重名时取第一个）",
          ml.find_node(tree, "B", by="text")["id"] == b)
    check("按文字找不到给 None",
          ml.find_node(tree, "不存在", by="text") is None)
    check("toggle_collapsed 在内存树上来回翻",
          ml.toggle_collapsed(tree, a) is True
          and ml.find_node(tree, a)["collapsed"] is True
          and ml.toggle_collapsed(tree, a) is False)
    check("toggle 不存在的 id 返回 False", ml.toggle_collapsed(tree, 999999) is False)

    # 库级折叠
    res = db.toggle_collapsed(a)
    check("库级 toggle_collapsed 返回 {id, collapsed}",
          res == {"id": int(a), "collapsed": True}, res)
    check("库级折叠后读回来是 1", int(db._node_row(a)["collapsed"]) == 1)
    check("库级 set_collapsed 生效并返回 True",
          db.set_collapsed(a, False) is True
          and int(db._node_row(a)["collapsed"]) == 0)
    check("set_collapsed 不存在的 id 返回 False",
          db.set_collapsed(999999, True) is False)
    check("toggle_collapsed 不存在的 id 返回 None",
          db.toggle_collapsed(999999) is None)

    flags = [1, 0, 0, 1, 0]          # DFS: root, A, A1, A2, B
    db.restore_collapsed(mid, flags)
    check("restore_collapsed 往返一致",
          db.collapsed_flags(mid) == flags, db.collapsed_flags(mid))
    check("恢复折叠不改节点数", db.node_count(mid) == 5, db.node_count(mid))

    # apply_collapsed：多退少补、从不抛
    t = ml.normalize(db.load_tree(mid))
    t2 = ml.apply_collapsed(t, flags)
    check("apply_collapsed 往返一致",
          [1 if n["collapsed"] else 0 for n, _p, _d in ml.iter_nodes(t2)] == flags)
    check("apply_collapsed 标记多了就忽略、少了保持原值（不抛）",
          [1 if n["collapsed"] else 0
           for n, _p, _d in ml.iter_nodes(ml.apply_collapsed(t, []))]
          == [1 if n["collapsed"] else 0 for n, _p, _d in ml.iter_nodes(t)]
          and len(ml.apply_collapsed(t, flags + [1, 1, 1, 1])["children"]) >= 0)
    check("apply_collapsed 对 None / 空都给合法树",
          ml.count_nodes(ml.apply_collapsed(t, None)) == ml.count_nodes(t))

    # ★ 核心防线：折叠 + 备注 不在大纲文本里，纯文本重存必须搬运
    db.set_collapsed(a, True)
    db.update_node(a1, note="这条备注不许丢")
    before = db.collapsed_flags(mid)
    db.save_outline_text(mid, db.load_outline(mid))
    check("**纯文本重存后折叠状态还在**（改一行字回来不会全展开）",
          db.collapsed_flags(mid) == before
          and int(db._node_row(a)["collapsed"]) == 1,
          (before, db.collapsed_flags(mid)))
    check("**纯文本重存后备注还在**",
          db._node_row(a1)["note"] == "这条备注不许丢",
          db._node_row(a1)["note"])

    # carry_state：文字匹配 / 重名退位置 / 都不匹配则保留新树自己的值
    old = ml.parse_outline("根\n  甲\n  乙")
    for n, _p, _d in ml.iter_nodes(old):
        n["collapsed"] = True
    new = ml.parse_outline("根\n  甲\n  丙")
    carried = ml.carry_state(old, new, ("collapsed",))
    got = {n["text"]: bool(n["collapsed"]) for n, _p, _d in ml.iter_nodes(carried)}
    check("carry_state：文字相同的节点状态被搬过来",
          got["甲"] is True and got["根"] is True, got)
    # 文档写明的取舍：先按文字匹配，重名 / 配不上时**退回按位置匹配**。
    # 所以「在末尾新增一枝」会继承同位置那位兄弟的状态 —— 宁可偶尔串位，
    # 也不要让两支的状态互相搞混。只有路径在旧树里也不存在时才保留新值。
    check("carry_state：末尾新增按位置继承（有意的取舍）",
          got["丙"] is True, got)
    deep = ml.parse_outline("根\n  甲\n    新深层")
    deep_got = {n["text"]: bool(n["collapsed"]) for n, _p, _d
                in ml.iter_nodes(ml.carry_state(old, deep, ("collapsed",)))}
    check("carry_state：文字与路径都匹配不上时才保留新树自己的值",
          deep_got["新深层"] is False and deep_got["甲"] is True, deep_got)

    dup_old = ml.parse_outline("根\n  同名\n  同名")
    for index, (n, _p, _d) in enumerate(ml.iter_nodes(dup_old)):
        n["collapsed"] = index == 2          # 只有第二支折叠
    dup_new = ml.parse_outline("根\n  同名\n  同名")
    carried = ml.carry_state(dup_old, dup_new, ("collapsed",))
    seq = [(n["text"], bool(n["collapsed"])) for n, _p, _d in ml.iter_nodes(carried)]
    check("carry_state：重名时退回按位置匹配（不互相串）",
          seq == [("根", False), ("同名", False), ("同名", True)], seq)

    check("carry_state 对垃圾输入不抛",
          ml.carry_state(None, None) is not None
          and ml.count_nodes(ml.carry_state("垃圾", 123)) == 1)
    check("carry_state 不改动输入树",
          (lambda t: (ml.carry_state(t, ml.parse_outline("根")), 
                      all(not n["collapsed"] for n, _p, _d in ml.iter_nodes(t))))(
              ml.parse_outline("根\n  甲"))[1])


# ══════════════════════════════════════════════════════════════════════════
# M. 页面契约
# ══════════════════════════════════════════════════════════════════════════
def test_page_contracts() -> None:
    section("[M] 页面契约（mindmap_page 用到的每个入口）")
    db = fresh("page")

    src = (ROOT / "mindmap_page.py").read_text(encoding="utf-8")
    used = sorted(set(re.findall(r"self\.db\.([A-Za-z_][A-Za-z0-9_]*)", src)))
    missing = [n for n in used if not callable(getattr(db, n, None))]
    check("页面用到的每个 db 方法都存在", used and not missing,
          (missing, len(used)))

    used_ml = sorted(set(re.findall(r"\bml\.([A-Za-z_][A-Za-z0-9_]*)", src)))
    missing = [n for n in used_ml if not hasattr(ml, n)]
    check("页面用到的每个 ml 函数都存在", used_ml and not missing,
          (missing, len(used_ml)))

    check("页面用到的 mindmap_db 模块级函数存在",
          callable(getattr(mindmap_db, "suggest_new_count", None))
          and callable(getattr(mindmap_db, "split_tags", None))
          and callable(getattr(mindmap_db, "format_map_line", None)))

    mid = db.create_from_template("TPL_CORNELL")
    item = db.get_map(mid)
    check("导图行字段齐全",
          {"id", "title", "root_note", "category", "tags", "source_key",
           "created_at", "updated_at"} <= set(item), sorted(item))
    check("节点行字段齐全",
          {"id", "map_id", "parent_id", "seq", "depth", "text", "note",
           "collapsed"} <= set(db.list_nodes(mid)[0]), sorted(db.list_nodes(mid)[0]))
    check("模板行字段齐全",
          {"code", "name", "category", "description", "outline"}
          <= set(db.list_templates()[0]), sorted(db.list_templates()[0]))
    check("教学卡行字段齐全",
          {"code", "title", "category", "body", "tip", "practice"}
          <= set(db.list_cards()[0]), sorted(db.list_cards()[0]))
    check("进度行默认值字段齐全",
          {"map_id", "mastery", "correct_streak", "interval_days",
           "next_review_at", "review_count", "marked_at", "updated_at"}
          <= set(db.get_progress(99999)), sorted(db.get_progress(99999)))
    check("流水行字段齐全",
          (db.record_review(mid, tc.FEEDBACK_KNOWN, today="2026-09-28") or True)
          and {"id", "map_id", "review_date", "feedback", "mastery_after",
               "branch_hit", "branch_total", "created_at"}
          <= set(db.list_reviews(map_id=mid)[0]),
          sorted(db.list_reviews(map_id=mid)[0]))
    check("打卡行字段齐全",
          {"check_date", "minutes", "maps_new", "maps_reviewed", "accuracy",
           "note", "created_at"} <= set(db.checkin("2026-09-28")),
          sorted(db.checkin("2026-09-28")))
    check("format_map_line 带节点数",
          mindmap_db.format_map_line({"title": "图", "node_count": 5})
          == "图（5 个节点）"
          and mindmap_db.format_map_line({}) == "")
    check("split_tags 认 | , 、 ; 与空白",
          mindmap_db.split_tags("图|结构, 记忆、复述 ; 训练")
          == ["图", "结构", "记忆", "复述", "训练"]
          and mindmap_db.split_tags("") == []
          and mindmap_db.split_tags("a/b") == ["a/b"])


# ══════════════════════════════════════════════════════════════════════════
# N. 待办桥
# ══════════════════════════════════════════════════════════════════════════
def test_todo_bridge() -> None:
    section("[N] 盲画 → 待办")
    d = Path(tempfile.mkdtemp(prefix="mm_todo_"))
    _TMP.append(d)
    todo = todo_db.TodoDB(d / "todo.db")
    bridge = ttb.TrainingTodoBridge(todo)

    payload = ttb.review_payload(kind=ttb.KIND_MINDMAP, due=3, suggested=2,
                                 today="2026-09-28")
    check("标题用「盲画」（不是「复习」）",
          payload["title"] == "盲画思维导图 3 张", payload["title"])
    check("标题的单位是「张」", "3 张" in payload["title"], payload["title"])
    check("截止日期 = 今天", payload["due_date"] == "2026-09-28")
    check("备注里带建议新画量与入口路径",
          "建议 2 张" in payload["notes"] and "思维导图" in payload["notes"],
          payload["notes"])

    empty = ttb.review_payload(kind=ttb.KIND_MINDMAP, due=0, today="2026-09-28")
    check("队列为空时标题不带 0", empty["title"] == "盲画思维导图", empty["title"])

    hook = bridge.make_hook("mindmap")
    title, message = hook(due=3, suggested=2)
    items = todo.fetch_items(scope="all")
    check("真的写进了待办", len(items) == 1 and str(items[0].title) == title,
          (len(items), title))
    check("标签是思维导图", list(items[0].tags) == ["思维导图"], items[0].tags)
    check("**skip_holidays=0**：今天的事不许被顺延到工作日",
          int(getattr(items[0], "skip_holidays", 0)) == 0,
          getattr(items[0], "skip_holidays", None))

    title2, message2 = hook(due=3, suggested=2)
    check("**当天幂等**：连点两次不堆两条",
          len(todo.fetch_items(scope="all")) == 1 and "已经有一条" in message2,
          message2)

    memory_hook = bridge.make_hook("memory")
    memory_hook(due=7, suggested=3)
    all_items = todo.fetch_items(scope="all")
    check("两个模块的待办各自独立",
          len(all_items) == 2
          and {str(i.title) for i in all_items}
          == {"盲画思维导图 3 张", "复习记忆宫殿 7 条"},
          [str(i.title) for i in all_items])

    check("缺标题不建", bridge.create({"due_date": "2026-09-28"})["created"] is False)
    check("缺日期不建", bridge.create({"title": "x"})["created"] is False)

    class BrokenTodo:
        def fetch_items(self, **kw):
            raise RuntimeError("模拟读失败")

        def add_item(self, payload):
            return 777

    broken = ttb.TrainingTodoBridge(BrokenTodo())
    result = broken.create(ttb.review_payload(kind=ttb.KIND_MINDMAP, due=1))
    check("读待办失败时按「没有重复项」处理，照样建",
          result["created"] is True and result["item_id"] == 777, result)



# ══════════════════════════════════════════════════════════════════════════
# O. 游戏训练包（数独 / CS2 / 中国象棋）
# ══════════════════════════════════════════════════════════════════════════
# 三张知识树。这里锁的是「**大纲首行 = 中心主题**」和「往返一致」两件事 ——
# ``create_from_template`` 出来的图，标题取的是大纲首行，两者一旦不同步，
# 建出来的图会顶着另一个名字。
GAME_MAPS = [
    ("TPL_MM_SUDOKU", "数独解法体系", 5),
    ("TPL_MM_CS2", "CS2 知识树", 5),
    ("TPL_MM_XIANGQI", "中国象棋知识树", 5),
]


def test_game_maps() -> None:
    section("[O] 游戏训练包（数独 / CS2 / 象棋）")
    codes = {t["code"] for t in mindmap_seed.TEMPLATES}
    check("三个游戏模板都在", all(c in codes for c, _, _ in GAME_MAPS),
          [c for c, _, _ in GAME_MAPS if c not in codes])
    check("新增了「游戏训练」分类",
          "游戏训练" in mindmap_seed.template_categories(),
          mindmap_seed.template_categories())

    tmp = tempfile.mkdtemp(prefix="mm_game_")
    try:
        db = MindmapDB(Path(tmp) / "game.db")
        for code, topic, min_branches in GAME_MAPS:
            tpl = mindmap_seed.get_template(code)
            check(f"{code} 取得到", tpl is not None)
            if tpl is None:
                continue
            check(f"{code} 的分类是「游戏训练」",
                  tpl["category"] == "游戏训练", tpl["category"])
            first = tpl["outline"].splitlines()[0].strip()
            check(f"{code} 大纲首行就是中心主题 {topic!r}", first == topic, first)

            tree = ml.parse_outline(tpl["outline"])
            brief = ml.blind_brief(tree)
            check(f"{code} 至少 {min_branches} 条一级分支",
                  int(brief["branches"]) >= min_branches, brief)
            check(f"{code} 至少有层级（depth ≥ 2）", int(brief["depth"]) >= 2, brief)
            check(f"{code} 大纲往返一致",
                  ml.parse_outline(ml.outline_text(tree)) == tree)

            mid = db.create_from_template(code)
            loaded = db.load_tree(mid)
            after = ml.blind_brief(loaded)
            check(f"{code} 建成图后节点数与模板一致",
                  int(after["total"]) == int(brief["total"]),
                  (after["total"], brief["total"]))
            check(f"{code} 建成图的中心主题还是 {topic!r}",
                  after["root"] == topic, after["root"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main_test() -> None:
    test_srs_parity()
    test_seed()
    test_schema()
    test_map_crud()
    test_outline()
    test_layout()
    test_structure()
    test_srs()
    test_checkins()
    test_export()
    test_blind()
    test_collapse()
    test_game_maps()
    test_page_contracts()
    test_todo_bridge()


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
