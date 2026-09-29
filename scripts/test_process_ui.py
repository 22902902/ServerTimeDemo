# -*- coding: utf-8 -*-
"""流程中心 UI 回归测试：真实窗口 + 样例数据 + 逐项断言。

为什么单独成篇（且必须有 tkinter，用系统 Python312 跑）
------------------------------------------------------------------------------
流程中心重写后，坑几乎全是「代码写了、界面上却没有」，光看源码看不出来：

* `def _build_process_page` 那一行被补丁吃掉过 —— 语法合法、py_compile 与
  pyflakes 全绿，只有真开窗口才炸 AttributeError。
* 进度数字（``progress_var``）曾经全文件只有一处 ``set("")``，进度条在动、
  数字永远是空的。
* 左栏 230px 装不下 4 列，最右边的「步」列被推出可视区 —— 列定义了、看不见。
* 先 pack 了 expand 的内容区，后面 pack 的固定高度控件只分到 0 像素、被 Tk
  **直接不映射**（不是「被裁掉一点」，是界面上根本不存在）。

这些只有把真窗口建出来、量过 ``winfo_ismapped`` / ``winfo_width`` 才发现。

本文件固化的口径（都是已经踩过的坑）
------------------------------------------------------------------------------
* 窗口必须真实可见：主窗口一旦 ``withdraw()``，连 pack 好的控件也全部变成
  「未映射」，断言会集体假红。所以这里不 withdraw。
* 「已映射」要同时满足 ``winfo_ismapped()`` **且** 宽高 > 1 —— 未映射的控件
  一律报 1x1，只看 ismapped 是看不出版式错的。
* 布局顺序：定宽控件先 pack、expand 控件最后 pack。状态栏 ``side="bottom"``。
* **不要真弹菜单/弹窗**（``tk_popup``、``simpledialog``）—— 本机没有真实
  桌面时会把主循环挂住。涉及弹窗的功能只验证「入口存在」。
* 期望值从数据层现算（``fetch_process_flows`` / ``fetch_process_steps``），
  不写死数字。

覆盖：
A. 骨架        左栏宽度 / 四列都在可视区内 / 工具栏按钮齐
B. 流程列表    行数、收藏星、步数列、默认选中
C. 步骤卡片    卡片数 == 步骤数、勾选框、类型徽章、危险标记
D. 布局纪律   定宽控件全部已映射且有真实高度；滚动区吃掉剩余空间
E. 执行进度    未开始/执行中/勾选/结束 四种状态下按钮与进度文案
F. 变量栏      有变量时列出键与值；无变量时给提示
G. 空状态      没有流程时的提示文案
H. 搜索        关键词过滤行数；清空恢复
I. 滚动        重排后卡片流回到顶部（内容变矮时旧 yOrigin 不会自己夹回来）
J. 截图回收    真删文件 / 缺失不报错 / **共用的那张始终不动**
L. 发送到终端  按钮 / 危险命令二次确认（取消就一个字都不发）/ 走注入的发送器
M. 加入待办    按钮 / payload 带步骤 / 日期是今天 / 没注入时退回复制
N. 截图标注    每张图下有「标注」/ 假对话框走完落盘 + 追加路径 / 原图不动

用法::

    python scripts/test_process_ui.py
"""

import shutil
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from tkinter import messagebox  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json  # noqa: E402
from datetime import date  # noqa: E402

import main as app  # noqa: E402
import process_page as PP  # noqa: E402  （按类型找命令块，不靠中文文案）
from ui_theme import MAIN_PALETTE, THEME  # noqa: E402

PASSED = 0
FAILED = 0


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


def settle(root: tk.Misc, rounds: int = 3) -> None:
    """让 Tk 把挂起的几何结算跑完；不投递额外事件循环。"""
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def mapped(widget) -> bool:
    """「真的在屏幕上」：已映射 **且** 有真实尺寸（未映射一律报 1x1）。"""
    try:
        return bool(widget.winfo_ismapped()) and widget.winfo_width() > 1 and widget.winfo_height() > 1
    except tk.TclError:
        return False


def texts_of(widget) -> list:
    """递归收集所有控件的 text / textvariable 当前值（原样，含两侧留白）。"""
    found = []
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return found
    for child in children:
        try:
            variable = child.cget("textvariable")
            if variable:
                try:
                    found.append(str(child.tk.globalgetvar(variable)))
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        try:
            value = child.cget("text")
            if value:
                found.append(str(value))
        except tk.TclError:
            pass
        found.extend(texts_of(child))
    return found


def joined(widget) -> str:
    """把所有文字拼成一行再判断。

    为什么不能整字相等比对：界面上很多文字是**拼出来的**（变量栏一行就是
    ``站点域名 = example.com``），徽章两侧还带留白（``' 命令型 '``）。用
    ``in`` 判断组合串才稳。
    """
    return " │ ".join(texts_of(widget))


def make_page(root, db):
    page = app.ProcessPage(
        root, db,
        app_title=app.APP_TITLE,
        flow_templates=app.PROCESS_FLOW_TEMPLATES,
        image_preview_cls=app.AccountImagePreview,
        images=app.ProcessImageTools(
            base_dir=app.BASE_DIR,
            resolve_paths=app.resolve_account_image_paths,
            storage_value=app.get_account_image_storage_value,
            make_dir=app.ensure_account_image_dir,
            parse_items=app.parse_account_image_items,
            serialize_items=app.serialize_account_image_items,
        ),
        format_datetime=app.format_datetime_text,
        on_status=lambda m: None,
    )
    page.pack(fill="both", expand=True)
    return page


def build_data(db):
    """两个流程：一个带变量与命令块（含危险命令），一个只有说明。"""
    general = db.add_process_flow({
        "title": "软件著作权申请", "category": "备案", "platform": "版权中心",
        "note": "每年一次", "variables": [],
    })
    db.add_process_step(general, {"step_no": 1, "title": "填写申请表",
                                  "kind": "op", "description_text": "在官网填表"})
    db.add_process_step(general, {"step_no": 2, "title": "上传材料",
                                  "kind": "op", "required_text": "身份证"})

    ops = db.add_process_flow({
        "title": "Linux · 证书续期", "category": "运维", "platform": "Nginx",
        "favorite": 1,
        "variables": [{"key": "域名", "label": "站点域名", "default": "example.com", "hint": ""},
                      {"key": "环境", "label": "部署环境", "default": "prod", "hint": ""}],
    })
    ids = [
        db.add_process_step(ops, {"step_no": 1, "title": "查看到期时间", "kind": "cmd",
                                  "precheck_text": "能 sudo",
                                  "command_text": "openssl x509 -noout -enddate",
                                  "expected_text": "看到 notAfter"}),
        db.add_process_step(ops, {"step_no": 2, "title": "替换证书并清缓存", "kind": "cmd",
                                  "command_text": "cp /tmp/c.pem /etc/nginx/\n"
                                                  "rm -rf /www/{{域名}}/cache"}),
        db.add_process_step(ops, {"step_no": 3, "title": "校验并重启", "kind": "check",
                                  "precheck_text": "上一步完成",
                                  "command_text": "nginx -t && nginx -s reload"}),
        db.add_process_step(ops, {"step_no": 4, "title": "记下新到期日", "kind": "note",
                                  "description_text": "填回到期管理"}),
    ]
    return general, ops, ids


# ══════════════════════════════════════════════════════════════════════════
# A. 骨架
# ══════════════════════════════════════════════════════════════════════════
def test_skeleton(page):
    section("A. 骨架：左栏宽度 / 列全部可见 / 工具栏")
    check("进度条已映射", mapped(page.progress_canvas))
    check("变量栏已映射", mapped(page.var_bar))
    check("步骤滚动区已映射", mapped(page.step_area))
    check("快速录入框已映射", mapped(page.quick_entry))
    check("运行按钮已映射", mapped(page.run_button))
    check("状态栏已映射", mapped(page.winfo_children()[-1]))

    left = page.flow_tree.master
    check(f"左栏宽度 == FLOW_LIST_WIDTH（{app.__dict__.get('FLOW_LIST_WIDTH', 'N/A')}）",
          abs(left.winfo_width() - 248) <= 12, left.winfo_width())

    # 四列合计必须塞得进左栏（扣掉 Treeview 自己的滚动条）
    columns = page.flow_tree["columns"] if isinstance(page.flow_tree["columns"], tuple) \
        else str(page.flow_tree["columns"]).split()
    star = int(page.flow_tree.column("#0", "width"))
    total = star + sum(int(page.flow_tree.column(col, "width")) for col in columns)
    usable = left.winfo_width() - 17
    check("四列宽度合计 <= 左栏可视宽度（否则最后一列被推出屏幕）",
          total <= usable, f"列合计 {total} vs 可视 {usable}")
    check("左栏确实有 4 列（★ + 流程名称 + 分类 + 步）",
          len(columns) == 3 and star > 0, f"#0={star} columns={columns}")

    toolbar_texts = texts_of(page.winfo_children()[0])
    for label in ("新增流程", "编辑流程", "删除流程", "新增步骤"):
        check(f"工具栏有「{label}」", label in toolbar_texts, toolbar_texts)


# ══════════════════════════════════════════════════════════════════════════
# B. 流程列表
# ══════════════════════════════════════════════════════════════════════════
def test_flow_list(page, db):
    section("B. 流程列表：行数 / 收藏星 / 步数 / 默认选中")
    rows = db.fetch_process_flows("")
    items = page.flow_tree.get_children()
    check("树行数 == 流程数", len(items) == len(rows), f"{len(items)} vs {len(rows)}")
    check("默认选中了一条", len(page.flow_tree.selection()) == 1)
    check("收藏的排在第一位",
          page.flow_tree.item(items[0], "text") == "★",
          page.flow_tree.item(items[0], "text"))
    check("非收藏行的星列为空",
          any(page.flow_tree.item(i, "text") == "" for i in items))

    counts = {}
    for step in db.fetch_all_process_steps():
        counts[int(step["flow_id"])] = counts.get(int(step["flow_id"]), 0) + 1
    seen = {}
    for iid in items:
        values = page.flow_tree.item(iid, "values")
        seen[values[0]] = int(values[2])
    for row in rows:
        check(f"「{row['title']}」的步数列 == 数据层计数",
              seen.get(row["title"]) == counts.get(int(row["id"]), 0),
              f"界面 {seen.get(row['title'])} vs 库 {counts.get(int(row['id']), 0)}")
    check("分类列有值", all(page.flow_tree.item(i, "values")[1] for i in items))


# ══════════════════════════════════════════════════════════════════════════
# C. 步骤卡片
# ══════════════════════════════════════════════════════════════════════════
def test_step_cards(page, db):
    section("C. 步骤卡片：数量 / 勾选框 / 徽章 / 危险标记")
    flow = page._selected_flow(silent=True)
    check("有选中流程", flow is not None)
    if flow is None:
        return
    want = len(db.fetch_process_steps(int(flow["id"])))
    cards = page.step_holder.winfo_children()
    check("卡片数 == 该流程步骤数", len(cards) == want, f"{len(cards)} vs {want}")
    check("每张卡都有内容", all(card.winfo_children() for card in cards))

    all_texts = []
    for card in cards:
        all_texts.extend(texts_of(card))
    blob = " │ ".join(all_texts)
    steps = db.fetch_process_steps(int(flow["id"]))
    for step in steps:
        check(f"卡片里有步骤标题「{step['title']}」", step["title"] in blob, blob[:60])
    check("类型徽章「命令型」出现", "命令型" in blob, blob[:120])
    check("类型徽章「操作型」/「校验型」/「备注型」至少出现其一",
          any(t in blob for t in ("操作型", "校验型", "备注型")), blob[:160])

    danger_steps = [s for s in steps if int(s["danger"] or 0)]
    check("样例数据里确实有一条危险命令（否则下面两条形同虚设）", danger_steps)
    if danger_steps:
        check("危险步骤有「危险」徽章", "危险" in blob, blob[:200])
        check("命令块提示了危险原因", "危险操作" in blob,
              [t for t in all_texts if "危险" in t][:5])

    check("卡片里出现「复制」按钮（命令块）", "复制" in blob)
    check("卡片里出现「贴图」「编辑」「删除」",
          all(t in blob for t in ("贴图", "编辑", "删除")))


# ══════════════════════════════════════════════════════════════════════════
# D. 布局纪律
# ══════════════════════════════════════════════════════════════════════════
def test_layout_discipline(page):
    section("D. 布局纪律：定宽控件没被饿死")
    # 先 pack 定宽、后 pack expand 的口径：这些固定高度控件必须都有真实高度
    for name, widget in (("进度条", page.progress_canvas),
                         ("变量栏", page.var_bar),
                         ("快速录入条", page.quick_entry.master),
                         ("状态栏", page.winfo_children()[-1]),
                         ("工具栏", page.winfo_children()[0])):
        check(f"{name} 已映射且有真实尺寸", mapped(widget),
              f"{widget.winfo_width()}x{widget.winfo_height()}"
              f" mapped={widget.winfo_ismapped()}")
    check("步骤滚动区高度 > 200（吃掉了剩余空间）",
          page.step_area.winfo_height() > 200, page.step_area.winfo_height())
    check("滚动区宽度与流程头对齐（同一父容器）",
          abs(page.step_area.winfo_width() - page.var_bar.winfo_width()) <= 4,
          f"{page.step_area.winfo_width()} vs {page.var_bar.winfo_width()}")
    # 右侧内容 + 左侧列表 必须都在窗口里
    check("右侧内容区在窗口内",
          0 < page.step_area.winfo_rootx() < page.winfo_rootx() + page.winfo_width())
    check("左栏在右侧内容区左边",
          page.flow_tree.master.winfo_rootx() < page.step_area.winfo_rootx())


# ══════════════════════════════════════════════════════════════════════════
# E. 执行进度
# ══════════════════════════════════════════════════════════════════════════
def test_run_progress(page, db):
    section("E. 执行进度：按钮文案 / 进度数字 / 勾选联动")
    general, ops, ids = page._demo if hasattr(page, "_demo") else (None, None, None)
    flow = page._selected_flow(silent=True)
    if flow is None:
        return
    flow_id = int(flow["id"])
    total = len(db.fetch_process_steps(flow_id))

    # 未执行
    check("未执行时按钮是「开始执行」", page.run_button.cget("text") == "开始执行")
    check("未执行时进度文案是「共 N 步 · 未开始」",
          page.progress_var.get() == f"共 {total} 步 · 未开始", page.progress_var.get())

    # 开始执行
    page.toggle_run()
    settle(page)
    check("开始后按钮变「结束执行」", page.run_button.cget("text") == "结束执行",
          page.run_button.cget("text"))
    check("开始后进度文案是「执行中 0 / N」",
          page.progress_var.get() == f"执行中 0 / {total}", page.progress_var.get())
    run = db.get_active_process_run(flow_id)
    check("数据层确实开了一次执行", run is not None)

    # 勾一步
    steps = db.fetch_process_steps(flow_id)
    check("步骤数 > 0", len(steps) > 0)
    if steps:
        page.set_step_done(int(steps[0]["id"]), True)
        settle(page)
        check("勾一步后进度文案是「执行中 1 / N」",
              page.progress_var.get() == f"执行中 1 / {total}", page.progress_var.get())
        page.set_step_done(int(steps[0]["id"]), False)
        settle(page)
        check("取消勾选后回到「执行中 0 / N」",
              page.progress_var.get() == f"执行中 0 / {total}", page.progress_var.get())

    # 结束
    page.toggle_run()
    settle(page)
    check("结束后按钮回到「开始执行」", page.run_button.cget("text") == "开始执行")
    check("结束后没有进行中的执行", db.get_active_process_run(flow_id) is None)
    check("结束后卡片流仍在（刷新没把内容清掉）",
          len(page.step_holder.winfo_children()) == total,
          len(page.step_holder.winfo_children()))


# ══════════════════════════════════════════════════════════════════════════
# F. 变量栏
# ══════════════════════════════════════════════════════════════════════════
def test_variable_bar(page, db):
    section("F. 变量栏：有变量时列键与值")
    flows = db.fetch_process_flows("")
    with_vars = [f for f in flows if f["variables"]]
    without = [f for f in flows if not f["variables"]]

    for row in with_vars:
        for iid, meta in page._flow_rows.items():
            if int(meta["id"]) == int(row["id"]):
                page.flow_tree.selection_set(iid)
                page.refresh_steps()
                settle(page)
                break
        bar = joined(page.var_bar)
        check(f"「{row['title']}」的变量栏列出「站点域名」", "站点域名" in bar, bar)
        check("变量栏列出默认值", "example.com" in bar, bar)
        check("变量栏有「改值」入口", "改值" in bar, bar)

    if without:
        for iid, meta in page._flow_rows.items():
            if int(meta["id"]) == int(without[0]["id"]):
                page.flow_tree.selection_set(iid)
                page.refresh_steps()
                settle(page)
                break
        labels = texts_of(page.var_bar)
        check("没有变量时给出「未定义变量」提示",
              any("未定义变量" in t for t in labels), labels)


# ══════════════════════════════════════════════════════════════════════════
# G. 空状态
# ══════════════════════════════════════════════════════════════════════════
def test_empty_state(root, tmpdir):
    section("G. 空状态：一条流程都没有时")
    empty_db = app.Database(tmpdir / "empty.db")
    holder = ttk.Frame(root)
    holder.pack(fill="both", expand=True)
    page = app.ProcessPage(
        holder, empty_db,
        app_title=app.APP_TITLE,
        flow_templates=app.PROCESS_FLOW_TEMPLATES,
        image_preview_cls=app.AccountImagePreview,
        images=app.ProcessImageTools(
            base_dir=app.BASE_DIR,
            resolve_paths=app.resolve_account_image_paths,
            storage_value=app.get_account_image_storage_value,
            make_dir=app.ensure_account_image_dir,
            parse_items=app.parse_account_image_items,
            serialize_items=app.serialize_account_image_items,
        ),
        format_datetime=app.format_datetime_text,
    )
    page.pack(fill="both", expand=True)
    settle(root)
    check("空库时流程树没有行", len(page.flow_tree.get_children()) == 0)
    empty_blob = joined(page.step_holder)
    check("空库时给出「还没有流程」类提示",
          ("还没有" in empty_blob and "流程" in empty_blob)
          or "新增流程" in empty_blob,
          empty_blob)
    check("空库时标题提示选中流程",
          page.flow_title_var.get() in ("请选择左侧流程", "还没有流程")
          or "没有" in page.flow_title_var.get(),
          page.flow_title_var.get())
    holder.destroy()
    empty_db.close()


# ══════════════════════════════════════════════════════════════════════════
# H. 搜索
# ══════════════════════════════════════════════════════════════════════════
def test_search(page, db):
    section("H. 搜索：关键词过滤行数")
    total = len(page.flow_tree.get_children())
    page.search_var.set("证书")
    page.refresh_flows()
    settle(page)
    filtered = page.flow_tree.get_children()
    check("关键词把行数减少了", 0 < len(filtered) < total, f"{len(filtered)} / {total}")
    check("命中的是运维那条",
          all("证书" in page.flow_tree.item(i, "values")[0] for i in filtered),
          [page.flow_tree.item(i, "values")[0] for i in filtered])

    page.search_var.set("绝不存在的词")
    page.refresh_flows()
    settle(page)
    check("搜不到时没有行", len(page.flow_tree.get_children()) == 0)

    page.search_var.set("")
    page.refresh_flows()
    settle(page)
    check("清空关键词后恢复全部", len(page.flow_tree.get_children()) == total)


# ══════════════════════════════════════════════════════════════════════════
# I. 滚动
# ══════════════════════════════════════════════════════════════════════════
def test_scroll_reset(page, db):
    section("I. 重排后卡片流回到顶部")
    flow = page._selected_flow(silent=True)
    if flow is None:
        return
    steps = db.fetch_process_steps(int(flow["id"]))
    if len(steps) < 2:
        check("步骤够多才能测滚动（跳过）", True)
        return
    page.step_area.canvas.yview_moveto(1.0)
    settle(page)
    page.render_steps(flow, steps)
    settle(page)
    first = page.step_holder.winfo_children()[0]
    offset = first.winfo_rooty() - page.step_area.winfo_rooty()
    check("重排后第一张卡贴在滚动区顶部（没被旧 yOrigin 顶出去）",
          abs(offset) <= 24, f"offset={offset}")


# ══════════════════════════════════════════════════════════════════════════
# J. 截图回收（真删文件）
# ══════════════════════════════════════════════════════════════════════════
class FakeImages:
    """只实现 ``resolve_paths``。

    为什么把真适配器换掉：真适配器以 ``app.BASE_DIR``（开发库）为根，而本项目的
    纪律是**测试对真实数据目录只读**。删文件的逻辑本身不受影响 —— 它只用
    ``resolve_paths`` 把存储值变成绝对路径。
    """

    def __init__(self, base):
        self.base = Path(base)

    def resolve_paths(self, value):
        if not value:
            return []
        path = Path(value)
        return [path if path.is_absolute() else self.base / path]


def test_screenshot_reclaim(page, db, tmproot):
    section("J. 截图回收：真删文件 / 缺失不报错 / 共用的那张始终不动")

    check("页面真的拿到了图片能力（真适配器上有 resolve_paths）",
          callable(getattr(page.images, "resolve_paths", None)))

    saved = page.images
    page.images = FakeImages(tmproot)
    try:
        rel_dir = Path("account_images") / "process_flows"
        (tmproot / rel_dir).mkdir(parents=True, exist_ok=True)
        shared = (rel_dir / "j_shared.png").as_posix()
        solo = (rel_dir / "j_solo.png").as_posix()
        (tmproot / rel_dir / "j_shared.png").write_bytes(b"x")
        (tmproot / rel_dir / "j_solo.png").write_bytes(b"y")

        flow = db.add_process_flow({"title": "回收用例", "category": "运维"})
        t1 = db.add_process_step(flow, {"step_no": 1, "title": "共用",
                                        "screenshot_path": shared})
        db.add_process_step(flow, {"step_no": 2, "title": "也共用",
                                   "screenshot_path": shared})
        t3 = db.add_process_step(flow, {"step_no": 3, "title": "独占",
                                        "screenshot_path": solo})

        # 顺序刻意写成「先 collect、再删行、最后删文件」—— 与页面里的调用一致
        reclaim = db.collect_orphan_screenshots([t1])
        db.delete_process_step(t1)
        n1 = page._reclaim_screenshots(reclaim)
        check("删共用步骤：回收 0 张（另一条步骤还引用着）", n1 == 0, n1)
        check("共用图还在磁盘上", (tmproot / shared).exists())

        reclaim = db.collect_orphan_screenshots([t3])
        db.delete_process_step(t3)
        n2 = page._reclaim_screenshots(reclaim)
        check("删独占步骤：回收 1 张", n2 == 1, n2)
        check("独占图真的被删掉了", not (tmproot / solo).exists())
        check("共用图自始至终没被动过", (tmproot / shared).exists())

        check("文件不存在时不报错也不计数",
              page._reclaim_screenshots([(rel_dir / "没这张.png").as_posix()]) == 0)
        check("空 / None → 0",
              page._reclaim_screenshots([]) == 0
              and page._reclaim_screenshots(None) == 0)

        db.delete_process_flow(flow)
    finally:
        page.images = saved


# ══════════════════════════════════════════════════════════════════════════
# L. 发送到终端
# ══════════════════════════════════════════════════════════════════════════
class quiet_dialogs:
    """把弹窗换成记录器。

    口径（见文件头第 6 条）：**不真弹模态窗**。这里连 ``askyesno`` 也一起换掉 ——
    危险命令二次确认是这一节的考点，不能靠「点了不会挂」糊过去。
    """

    NAMES = ("showinfo", "showwarning", "showerror")

    def __init__(self, askyesno=True):
        self.answer = askyesno
        self.calls: dict[str, list] = {}

    def __enter__(self):
        self._saved = {name: getattr(messagebox, name) for name in self.NAMES}
        self._saved["askyesno"] = messagebox.askyesno

        def record(name, answer=None):
            def fake(*args, **kwargs):
                self.calls.setdefault(name, []).append(
                    args[1] if len(args) > 1 else kwargs.get("message", ""))
                return answer
            return fake

        for name in self.NAMES:
            setattr(messagebox, name, record(name))
        messagebox.askyesno = record("askyesno", self.answer)
        return self

    def __exit__(self, *exc):
        for name in self.NAMES:
            setattr(messagebox, name, self._saved[name])
        messagebox.askyesno = self._saved["askyesno"]
        return False


def command_blocks(widget) -> list:
    """递归找出所有命令块（按类型找，不靠按钮上的中文）。"""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, PP.CommandBlock):
            found.append(child)
        found.extend(command_blocks(child))
    return found


def menu_labels(widget) -> list:
    """收集所有下拉菜单里的条目文案。

    菜单条目**不是控件**，``texts_of`` 看不到它们 —— 「更多」里的动作只能从
    ``Menu.entrycget`` 读，否则「加了但看不见」这类问题测不出来。
    """
    found = []
    menu = getattr(widget, "menu", None)
    if menu is not None:
        try:
            last = menu.index("end")
        except tk.TclError:
            last = None
        if last is not None:
            for index in range(int(last) + 1):
                try:
                    label = menu.entrycget(index, "label")
                except tk.TclError:
                    continue
                if label:
                    found.append(str(label))
    for child in widget.winfo_children():
        found.extend(menu_labels(child))
    return found


def test_send_to_terminal_ui(page, db, root):
    section("L. 发送到终端：按钮 / 危险命令二次确认 / 走注入的发送器")

    rows = [row for row in db.fetch_process_flows("") if "证书续期" in str(row["title"])]
    check("样例数据里有带命令的那条流程", bool(rows))
    if rows:
        page.refresh_flows(select_flow_id=int(rows[0]["id"]))
        settle(root, 3)
    check("卡片里出现「发送到终端」按钮", "发送到终端" in joined(page.step_holder))

    boxes = command_blocks(page.step_holder)
    check("找到了命令块", len(boxes) >= 2, len(boxes))
    check("命令块里的文本是渲染后的命令",
          any("openssl" in str(b.display_text) for b in boxes),
          [str(b.display_text)[:30] for b in boxes])
    check("**每个命令块都拿到了发送回调**（否则按钮是个摆设）",
          boxes and all(b.on_terminal for b in boxes), [bool(b.on_terminal) for b in boxes])

    sent = []
    page.terminal = lambda text: (sent.append(text)
                                  or {"reason": "已打开终端（测试替身）。", "opened": True})
    with quiet_dialogs() as quiet:
        page.send_command_to_terminal("openssl x509 -noout -enddate")
    check("普通命令直接发送，不弹确认", sent == ["openssl x509 -noout -enddate"], sent)
    check("没有弹过确认框", "askyesno" not in quiet.calls, quiet.calls)
    check("状态栏用的是发送器给的那句话",
          "已打开终端" in str(page.status_var.get()), page.status_var.get())

    sent.clear()
    with quiet_dialogs(askyesno=True) as quiet:
        page.send_command_to_terminal("rm -rf /www/x")
    check("**危险命令先问一句**", "askyesno" in quiet.calls, quiet.calls)
    check("确认之后才真的发送", sent == ["rm -rf /www/x"], sent)

    sent.clear()
    with quiet_dialogs(askyesno=False) as quiet:
        page.send_command_to_terminal("rm -rf /www/x")
    check("**取消就一个字都不发**", sent == [], sent)
    check("状态栏说明已取消", "取消" in str(page.status_var.get()), page.status_var.get())

    sent.clear()
    page.terminal = None
    with quiet_dialogs():
        page.send_command_to_terminal("openssl x509 -noout")
    check("没注入终端能力时退回剪贴板并说明",
          "剪贴板" in str(page.status_var.get()), page.status_var.get())

    sent.clear()
    with quiet_dialogs():
        page.send_command_to_terminal("   ")
    check("空命令什么都不做", sent == []
          and "没什么可发送" in str(page.status_var.get()), page.status_var.get())


# ══════════════════════════════════════════════════════════════════════════
# M. 加入待办
# ══════════════════════════════════════════════════════════════════════════
def test_add_flow_to_todo_ui(page, db, root):
    section("M. 加入待办：按钮 / payload 带步骤 / 状态栏 / 没注入时退回复制")

    check("流程头有「加入待办」按钮",
          "加入待办" in joined(page.run_button.master),
          joined(page.run_button.master)[:200])
    toolbar_entries = menu_labels(page.winfo_children()[0])
    check("工具栏「更多」里也有一份（菜单条目不是控件，得从 Menu 读）",
          any("加入待办" in entry for entry in toolbar_entries), toolbar_entries)

    captured = []
    page.todo_hook = lambda payload: (captured.append(payload)
                                      or {"created": True,
                                          "message": "已在待办里加上「x」（含 4 个子任务）。"})
    flow = page._selected_flow(silent=True)
    steps = [s for s in db.fetch_process_steps(int(flow["id"]))
             if str(s["title"] or "").strip()]

    page.add_flow_to_todo()
    check("todo_hook 收到一条 payload", len(captured) == 1, captured)
    payload = captured[0] if captured else {}
    check("标题是「走一遍流程：…」",
          str(payload.get("title", "")).startswith("走一遍流程："), payload.get("title"))
    check("**步骤变成了子任务，条数与库里的步骤数一致**",
          len(payload.get("subtasks") or []) == len(steps),
          f"{payload.get('subtasks')} vs {[s['title'] for s in steps]}")
    check("日期 == 今天（现算，不写死）",
          payload.get("due_date") == date.today().isoformat(), payload.get("due_date"))
    check("状态栏直接用桥给的那句话",
          "已在待办里加上" in str(page.status_var.get()), page.status_var.get())

    # 没注入 → 退回到「复制流程文本」，而不是点了没反应
    page.todo_hook = None
    copied = []
    saved_copy = page.copy_to_clipboard
    page.copy_to_clipboard = lambda text: copied.append(text)
    try:
        page.add_flow_to_todo()
    finally:
        page.copy_to_clipboard = saved_copy
    check("**没注入待办联动时退回复制，并说明原因**",
          copied and "剪贴板" in str(page.status_var.get()), page.status_var.get())


# ══════════════════════════════════════════════════════════════════════════
# N. 截图标注
# ══════════════════════════════════════════════════════════════════════════
class AnnotateImages:
    """带存储值转换的图片替身。

    真适配器以 ``app.BASE_DIR``（开发库）为根，而测试纪律是**对真实数据只读**，
    所以这里把根换到临时目录。序列化规则照抄真实现（全没标签 → 数组，有标签 →
    对象数组），否则「标注那条带没带标签」就测不出来了。
    """

    def __init__(self, base):
        self.base = Path(base)

    def resolve_paths(self, value):
        if not value:
            return []
        rows = self.parse_items(value)
        return [self.base / row["path"] for row in rows]

    def storage_value(self, path):
        try:
            return Path(path).resolve().relative_to(self.base.resolve()).as_posix()
        except (OSError, ValueError):
            return str(path).replace("\\", "/")

    def parse_items(self, value):
        text = str(value or "").strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                data = json.loads(text)
            except ValueError:
                return [{"path": text, "label": ""}]
            rows = []
            for item in data:
                path = item.get("path") if isinstance(item, dict) else item
                label = item.get("label", "") if isinstance(item, dict) else ""
                if path:
                    rows.append({"path": str(path), "label": str(label or "")})
            return rows
        return [{"path": text, "label": ""}]

    def serialize_items(self, items):
        rows = [row for row in items if str(row.get("path") or "").strip()]
        if not rows:
            return ""
        if all(not str(row.get("label") or "") for row in rows):
            if len(rows) == 1:
                return rows[0]["path"]
            return json.dumps([row["path"] for row in rows], ensure_ascii=False)
        return json.dumps(rows, ensure_ascii=False)


def test_annotate_ui(page, db, root, tmproot):
    section("N. 截图标注：每张图下有「标注」/ 假对话框走完保存链路 / 原图不动")
    from PIL import Image

    saved = page.images
    page.images = AnnotateImages(tmproot)
    try:
        folder = tmproot / "account_images" / "process_flows"
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / "n_src.png"
        Image.new("RGB", (140, 90), "white").save(source)
        original = source.read_bytes()

        flow = db.add_process_flow({"title": "标注用例", "category": "运维"})
        step_id = db.add_process_step(flow, {
            "step_no": 1, "title": "带图步骤",
            "screenshot_path": "account_images/process_flows/n_src.png"})
        page.refresh_flows(select_flow_id=flow)
        settle(root, 3)

        check("步骤卡里出现「标注」按钮", "标注" in joined(page.step_holder),
              joined(page.step_holder)[:200])

        opened = []

        class FakeDialog:
            """替身：不建画布，只把 (路径, 保存回调) 记下来。"""

            def __init__(self, master, path, *, on_save=None, app_title=""):
                opened.append({"path": Path(path), "on_save": on_save})

        page._annotate_dialog_cls = FakeDialog
        page.annotate_step_image(step_id, 0)
        check("对话框拿到的是这一张的**绝对路径**",
              opened and opened[0]["path"] == source, opened)
        check("保存回调给了对话框", opened and callable(opened[0]["on_save"]))

        keep = opened[0]["on_save"]([{"kind": "ellipse", "x1": 5, "y1": 5,
                                      "x2": 60, "y2": 40}])
        check("保存成功 → 告诉对话框可以关了", keep is False, keep)
        check("标注图落在同目录、名字带 _标注",
              (folder / "n_src_标注.png").exists(),
              sorted(p.name for p in folder.iterdir()))
        check("**原图一个字节没动**", source.read_bytes() == original)
        stored = str(db.get_process_step(step_id)["screenshot_path"])
        check("库里变成两条：原图 + 标注版",
              "n_src.png" in stored and "n_src_标注.png" in stored, stored)
        check("**标注那条带「标注」标签**（不然缩略图里两张看着一样）",
              '"label": "标注"' in stored or '"label":"标注"' in stored, stored)
        check("状态栏报了保存结果",
              "标注已保存" in str(page.status_var.get()), page.status_var.get())

        again = opened[0]["on_save"]([{"kind": "rect", "x1": 1, "y1": 1,
                                       "x2": 20, "y2": 20}])
        check("再标一次退到 _2，**不覆盖上一张**",
              again is False and (folder / "n_src_标注_2.png").exists(),
              sorted(p.name for p in folder.iterdir()))

        with quiet_dialogs() as quiet:
            keep_empty = opened[0]["on_save"]([])
        check("一笔都没画：不落盘、并让对话框留着接着画",
              keep_empty is True and not (folder / "n_src_标注_3.png").exists())
        check("并且提示了原因（不是静默失败）",
              quiet.calls.get("showwarning"), quiet.calls)

        # 没截图的步骤：给提示而不是崩
        blank = db.add_process_step(flow, {"step_no": 2, "title": "没图"})
        page.refresh_flows(select_flow_id=flow)
        settle(root, 2)
        with quiet_dialogs() as quiet:
            page.annotate_step_image(blank, 0)
        check("没有截图的步骤点标注 → 提示先贴一张",
              any("没有截图" in str(m) for m in quiet.calls.get("showinfo", [])),
              quiet.calls)

        page._annotate_dialog_cls = None
        db.delete_process_flow(flow)
    finally:
        page.images = saved


def main_test() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="process_ui_"))
    try:
        db = app.Database(tmpdir / "ui.db")
        build_data(db)

        root = tk.Tk()
        root.title("流程中心 UI 回归")
        root.geometry("1180x820+30+20")
        THEME.apply_main_ttk_theme(root, ttk.Style(root), MAIN_PALETTE)
        root.deiconify()
        container = ttk.Frame(root)
        container.pack(fill="both", expand=True)
        page = make_page(container, db)
        settle(root)

        try:
            test_skeleton(page)
            test_flow_list(page, db)
            test_step_cards(page, db)
            test_layout_discipline(page)
            test_run_progress(page, db)
            test_variable_bar(page, db)
            test_empty_state(root, tmpdir)
            test_search(page, db)
            test_scroll_reset(page, db)
            test_screenshot_reclaim(page, db, tmpdir)
            test_template_persists(root, page, db)
            test_send_to_terminal_ui(page, db, root)
            test_add_flow_to_todo_ui(page, db, root)
            test_annotate_ui(page, db, root, tmpdir)
        finally:
            db.close()
            root.destroy()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# K. 模板落库（**重开还在**）
# ══════════════════════════════════════════════════════════════════════════
def test_template_persists(root, page, db) -> None:
    section("K. 模板落库")
    flow_id = db.add_process_flow({"title": "换证书流程", "category": "运维",
                                   "platform": "", "link_url": "", "note": "n",
                                   "variables": ""})
    db.add_process_step(flow_id, {"step_no": 1, "title": "备份旧证书",
                                  "description_text": "d"})
    page.refresh_flows(select_flow_id=flow_id)
    settle(root, 3)

    before = len(page.flow_templates)
    page.save_as_template()
    settle(root, 2)
    check("另存之后模板多了一条", len(page.flow_templates) == before + 1,
          (before, len(page.flow_templates)))
    check("库里真的写了一行", len(db.fetch_process_templates()) == 1,
          db.fetch_process_templates())
    check("状态栏说了「已保存」（不然用户以为只在本次有效）",
          "已保存" in str(page.status_var.get()), page.status_var.get())

    # 关键：**另开一个页面** = 程序重启。内存里那份没了就没了
    again = make_page(root, db)
    again.pack(fill="both", expand=True)
    settle(root, 3)
    check("**重开之后模板还在**（这条才是本次的重点）",
          any(t.get("source") == "user" for t in again.flow_templates),
          [t.get("key") for t in again.flow_templates])
    check("重开后步骤也没丢",
          any(len(t.get("steps") or []) == 1
              for t in again.flow_templates if t.get("source") == "user"))
    again.destroy()


if __name__ == "__main__":
    import traceback

    print("=" * 78)
    print("流程中心 UI 回归测试：真实窗口 + 逐项断言")
    print("=" * 78)
    try:
        main_test()
    except Exception:
        traceback.print_exc()
        FAILED += 1

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
