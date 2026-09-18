# -*- coding: utf-8 -*-
"""外壳回归测试：自绘侧栏 + 顶栏 + 主题 token 的运行时验证。

直接构造真实主窗口（屏蔽登录弹窗与外部命令轮询），逐项断言：

1. 侧栏渲染出全部 8 个模块行
2. 点击模块行 → switch_module 生效，且侧栏高亮同步
3. 反向：程序化 switch_module（如 open_account_ledger）→ 侧栏高亮也同步
4. 分组可折叠 / 展开（子行随之增删）
5. 选中态 / 悬停态配色符合敲定规则
6. 旧的黄色文件夹图标已彻底移除

用法：
    python scripts/test_shell_ui.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
from nav_sidebar import NAV_MODEL, SidebarNav  # noqa: E402
from ui_theme import MAIN_PALETTE  # noqa: E402


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


def expected_module_keys():
    keys = []

    def walk(nodes):
        for node in nodes:
            if node["kind"] == "module":
                keys.append(node["key"])
            if node.get("items"):
                walk(node["items"])

    walk(NAV_MODEL)
    return keys


def main_test():
    print("=" * 78)
    print("构造真实主窗口（屏蔽登录弹窗与轮询）")
    print("=" * 78)

    main.ExpiryManagerApp.prompt_login = lambda self: None
    main.ExpiryManagerApp.poll_external_commands = lambda self: None

    app = main.ExpiryManagerApp()
    app.withdraw()
    app.update_idletasks()

    palette = MAIN_PALETTE
    nav = getattr(app, "nav", None)

    # ---------------------------------------------------------------- 1
    print("\n[1] 侧栏渲染")
    check("app.nav 是 SidebarNav 实例", isinstance(nav, SidebarNav),
          f"实际类型 {type(nav).__name__}")
    if not isinstance(nav, SidebarNav):
        return

    want = expected_module_keys()
    check("渲染出的模块行数正确", len(nav._rows) >= len(want),
          f"rows={len(nav._rows)} 期望>={len(want)}")
    missing = [k for k in want if k not in nav._rows]
    check("每个模块都有对应导航行", not missing, f"缺失 {missing}")
    check("每个模块都能在 module_items 中查到",
          all(k in app.module_items for k in want),
          f"未注册的 key: {[k for k in want if k not in app.module_items]}")

    # ---------------------------------------------------------------- 2
    print("\n[2] 点击模块行 → 切换页面 + 高亮同步")
    target = "module_work_credentials"
    app.nav._on_click(target)
    app.update_idletasks()
    check(f"点击 {target} 后 current_module 已切换",
          app.current_module == target, f"实际 {app.current_module}")
    check("侧栏高亮跟随点击", nav.current() == target, f"实际 {nav.current()}")

    widgets = nav._rows[target]
    check("选中行底色 = sidebar_active",
          widgets["row"].cget("bg") == palette.sidebar_active,
          f"实际 {widgets['row'].cget('bg')}")
    check("选中行左侧强调条 = 近黑强调色",
          widgets["accent"].cget("bg") == palette.accent,
          f"实际 {widgets['accent'].cget('bg')}")
    check("选中行圆点 = 近黑强调色",
          widgets["dot"].cget("bg") == palette.accent,
          f"实际 {widgets['dot'].cget('bg')}")
    check("选中行文字加深为 text_primary",
          widgets["label"].cget("fg") == palette.text_primary,
          f"实际 {widgets['label'].cget('fg')}")

    # 未选中行应回到浅灰底
    other = nav._rows["module_ops_expiry"]
    check("未选中行底色 = sidebar_bg",
          other["row"].cget("bg") == palette.sidebar_bg,
          f"实际 {other['row'].cget('bg')}")

    # ---------------------------------------------------------------- 3
    print("\n[3] 悬停态")
    nav._on_enter("module_ops_expiry")
    check("悬停行底色 = sidebar_hover",
          nav._rows["module_ops_expiry"]["row"].cget("bg") == palette.sidebar_hover,
          f"实际 {nav._rows['module_ops_expiry']['row'].cget('bg')}")
    nav._hovered = None
    nav._refresh_states()

    # ---------------------------------------------------------------- 4
    print("\n[4] 程序化切换 → 侧栏高亮反向同步")
    app.open_account_ledger()
    app.update_idletasks()
    check("open_account_ledger 后侧栏高亮同步",
          nav.current() == "module_work_credentials", f"实际 {nav.current()}")

    app.switch_module("module_study_notes")
    app.update_idletasks()
    check("切到生活组模块后高亮同步",
          nav.current() == "module_study_notes", f"实际 {nav.current()}")

    # ---------------------------------------------------------------- 5
    print("\n[5] 分组折叠 / 展开")
    check("初始状态 后台接口测试 行存在",
          "module_admin_backend" in nav._rows)
    nav._on_click("grp_api")
    check("折叠 接口测试 后子行被移除",
          "module_admin_backend" not in nav._rows
          and "grp_wenpai" not in nav._rows)
    nav._on_click("grp_api")
    check("再次展开后子行恢复",
          "module_admin_backend" in nav._rows)
    nav._on_click("grp_wenpai")
    check("折叠嵌套组 文拍 只移除其子模块",
          "module_admin_backend" not in nav._rows
          and "grp_wenpai" in nav._rows)
    nav._on_click("grp_wenpai")
    check("嵌套组恢复展开", "module_admin_backend" in nav._rows)

    # ---------------------------------------------------------------- 6
    print("\n[6] 旧风格残留清理")
    check("已移除 nav_folder_icon（黄色文件夹）",
          not hasattr(app, "nav_folder_icon"))
    check("已移除 nav_file_icon", not hasattr(app, "nav_file_icon"))
    check("已移除 nav_tree（原生 Treeview）", not hasattr(app, "nav_tree"))

    print("\n[7] 顶栏")
    topbar_labels = []

    def collect(widget):
        for child in widget.winfo_children():
            topbar_labels.append(child)
            collect(child)

    collect(app)
    texts = [
        str(w.cget("text")) for w in topbar_labels
        if w.winfo_class() == "Label" and str(w.cget("text")) != ""
    ]
    for expected in ("修改密码", "备份", "恢复备份", "初始化密码"):
        check(f"顶栏含动作「{expected}」", expected in texts)

    app.destroy()


if __name__ == "__main__":
    print("=" * 78)
    print("外壳回归测试：自绘侧栏 / 顶栏 / 主题 token")
    print("=" * 78)
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
