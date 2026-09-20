# -*- coding: utf-8 -*-
"""资源详情弹窗回归测试。

旧版是一个 Text 倾倒「键：值」行 + 英文 OK/Cancel，既没有层级也不好复制。
重做后的约定（本测试逐条锁住）：

A. 纯函数层
   - describe_expiry 把剩余天数翻译成状态键 + 人话，边界（负 / 0 / 15 / 30）正确
   - _row_value 对缺列、None、数字都安全

B. 真实弹窗层（构造真实主窗口 + 真实打开弹窗）
   - 是 Toplevel，标题「资源详情」，正文只读但内容可读
   - 顶部表头给出 编号 / 平台 / 到期状态徽标
   - 正文按「资源信息 / 账号信息 / 到期 / 其他 / 账户信息」分组
   - 表头已展示的字段（编号、平台）不在正文重复
   - 没有 emoji、按钮是中文
   - 「复制全部」产出扁平文本，含全部详情字段与账户信息

用法：
    python scripts/test_detail_dialog.py
"""

import sqlite3
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import expiry_dialogs  # noqa: E402
from expiry_dialogs import DetailDialog, describe_expiry, _row_value  # noqa: E402


PASSED = 0
FAILED = 0

# 覆盖常见 emoji / 图形符号区段（与 test_notes_markdown 同一套判据）
EMOJI_RANGES = (
    (0x1F300, 0x1FAFF), (0x1F000, 0x1F2FF), (0x2600, 0x27BF),
    (0x2190, 0x21FF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F),
)


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


def has_emoji(text: str) -> bool:
    for ch in text or "":
        code = ord(ch)
        if any(low <= code <= high for low, high in EMOJI_RANGES):
            return True
    return False


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def collect_texts(root) -> list[str]:
    texts = []
    for widget in walk(root):
        try:
            value = widget.cget("text")
        except Exception:
            continue
        if value:
            texts.append(str(value))
    return texts


def test_pure_functions():
    print("\n[A] 纯函数层")

    cases = [
        (None, "unknown", "未设置到期"),
        (-1, "overdue", "已过期 1 天"),
        (-120, "overdue", "已过期 120 天"),
        (0, "soon", "今天到期"),
        (1, "soon", "1 天后到期"),
        (15, "soon", "15 天后到期"),
        (16, "upcoming", "16 天后到期"),
        (30, "upcoming", "30 天后到期"),
        (31, "normal", "31 天后到期"),
    ]
    bad = []
    for remain, want_key, want_text in cases:
        key, text = describe_expiry(remain)
        if (key, text) != (want_key, want_text):
            bad.append((remain, (key, text), (want_key, want_text)))
    check("describe_expiry 9 个边界都正确", not bad, f"偏差 {bad}")

    check("_row_value 缺列返回空串", _row_value({}, "no_such") == "")
    check("_row_value 把 None 归一成空串", _row_value({"a": None}, "a") == "")
    check("_row_value 数字转字符串", _row_value({"a": 12}, "a") == "12")
    check("_row_value 正常取值", _row_value({"a": "x"}, "a") == "x")


def test_real_dialog():
    print("\n[B] 真实弹窗层")

    db_path = ROOT / "expiry_manager.db"
    if not db_path.exists():
        check("数据库存在（缺失则跳过弹窗层）", True, "已跳过")
        return

    import main

    main.ExpiryManagerApp.prompt_login = lambda self: None
    main.ExpiryManagerApp.startup_sequence = lambda self: None
    main.ExpiryManagerApp.poll_external_commands = lambda self: None

    app = main.ExpiryManagerApp()
    app.withdraw()
    app.update_idletasks()

    # 挑一条「有共享账户 + 资源详情多行」的记录，覆盖最多分支
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        asset = conn.execute(
            "SELECT a.* FROM assets a "
            "JOIN shared_accounts s ON s.group_key = a.account_no "
            "ORDER BY a.id LIMIT 1"
        ).fetchone()
        if asset is None:
            asset = conn.execute("SELECT * FROM assets ORDER BY id LIMIT 1").fetchone()
    finally:
        conn.close()

    if asset is None:
        check("库里至少有一条记录（否则跳过）", True, "已跳过")
        app.destroy()
        return

    accounts = app.db.fetch_shared_accounts(asset["account_no"])
    dialog = DetailDialog(
        app,
        asset,
        accounts,
        detail_fields=main.DETAIL_FIELDS,
        format_account_identity=main.format_account_identity,
        remain_days=main.days_left(main.parse_expiry_date(asset["expiry_date"])),
    )
    app.update_idletasks()
    app.update()

    check("是 Toplevel 且标题为「资源详情」",
          isinstance(dialog, tk.Toplevel) and dialog.title() == "资源详情",
          f"实际 {dialog.title()!r}")

    dialog_text = dialog.body.get("1.0", "end")
    all_texts = collect_texts(dialog)
    joined = "\n".join(all_texts) + dialog_text

    check("没有任何 emoji / 图形符号", not has_emoji(joined),
          f"含 emoji 的文本 {[t for t in all_texts if has_emoji(t)]}")

    # -- 表头
    header_texts = collect_texts(dialog.winfo_children()[0])
    check("表头显示编号", any(asset["record_no"] in t for t in header_texts),
          f"表头文本 {header_texts}")
    check("表头显示平台", any(asset["platform"] in t for t in header_texts),
          f"表头文本 {header_texts}")
    want_state, want_label = describe_expiry(
        main.days_left(main.parse_expiry_date(asset["expiry_date"])))
    check("表头显示到期状态徽标", any(t == want_label for t in header_texts),
          f"期望 {want_label!r}，实际 {header_texts}")

    # -- 正文分组
    for title in ("资源信息", "账号信息", "到期", "其他", "账户信息"):
        check(f"正文有「{title}」分组", f"{title}\n" in dialog_text,
              f"正文片段 {dialog_text[:160]!r}")

    # -- 表头字段不在正文重复
    #    注意不能简单用 "编号\t" 做子串判断 —— 「主体账号编号」「资源主体编号」
    #    都含这个词；要判断「行首」才算资产级的那个字段。
    #    账户信息段里的「平台」是账户自己的字段，属于正常，所以只查该段之前。
    asset_section = dialog_text.split("账户信息\n")[0]
    duplicated = [line.split("\t")[0] for line in asset_section.splitlines()
                  if line.startswith(("编号\t", "平台\t"))]
    check("表头字段（编号 / 平台）不在正文重复", not duplicated,
          f"重复行 {duplicated}")

    # -- 字段值确实落在正文里
    for field, label in main.DETAIL_FIELDS:
        value = _row_value(asset, field).strip()
        if not value or field in ("record_no", "platform"):
            continue
        # 值可能是多行，取首段判断
        first = value.replace("\r", "\n").split("\n")[0].strip()
        check(f"正文含「{label}」的首段值", first in dialog_text,
              f"找不到 {first!r}")

    # -- 账户信息
    check("有共享账户时账户信息不为「无」",
          ("无\n" in dialog_text) != bool(accounts),
          f"accounts={len(accounts)}")
    if accounts:
        identity = main.format_account_identity(
            accounts[0]["account_no"] or "", accounts[0]["account_name"] or "")
        check("账户信息里有账户身份", identity in dialog_text, f"期望 {identity!r}")

    # -- 只读但可复制
    check("正文为只读（disabled）", str(dialog.body.cget("state")) == "disabled",
          f"实际 {dialog.body.cget('state')}")
    check("正文内容非空", len(dialog_text.strip()) > 0)
    check("正文设了 tab stop（标签列靠 tab 对齐）",
          bool(dialog.body.cget("tabs")), f"实际 {dialog.body.cget('tabs')!r}")

    # -- 按钮与复制
    buttons = [w for w in walk(dialog) if w.winfo_class() == "TButton"]
    button_texts = [str(b.cget("text")) for b in buttons]
    check("底部按钮是中文「复制全部」「关闭」",
          button_texts == ["复制全部", "关闭"] or set(button_texts) == {"复制全部", "关闭"},
          f"实际 {button_texts}")

    plain = dialog._plain_text()
    missing = [label for field, label in main.DETAIL_FIELDS
               if f"{label}：" not in plain]
    check("复制文本含全部详情字段", not missing, f"缺少 {missing}")
    check("复制文本含账户信息段", "账户信息：" in plain)

    dialog._copy_all()
    app.update_idletasks()
    copied = app.clipboard_get()
    check("复制到剪贴板的内容与 _plain_text 一致", copied == plain,
          f"剪贴板长度 {len(copied)} vs {len(plain)}")

    # -- Esc 关闭
    # 按键事件必须落到「有焦点的窗口」上：主窗口还是 withdraw 状态时
    # focus_get() 返回 None，event_generate 的 <Escape> 会被 Tk 直接丢弃 ——
    # 那是测试环境的问题，不是绑定没生效。所以这里先让主窗口真正显示出来。
    app.deiconify()
    app.update()
    dialog.focus_force()
    app.update()

    check("弹窗内能取到焦点（Esc 才有接收方）", app.focus_get() is not None,
          f"focus_get={app.focus_get()}")
    check("Escape 绑定挂在弹窗上、且弹窗在正文的 bindtags 链里",
          bool(dialog.bind("<Escape>")) and str(dialog) in dialog.body.bindtags(),
          f"bindtags={dialog.body.bindtags()}")

    dialog.event_generate("<Escape>", when="now")
    app.update()
    check("Esc 能关闭弹窗", not dialog.winfo_exists())

    app.destroy()


def main_test():
    print("=" * 78)
    print("资源详情弹窗：纯函数 + 真实弹窗")
    print("=" * 78)
    test_pure_functions()
    test_real_dialog()


if __name__ == "__main__":
    try:
        main_test()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILED += 1

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
