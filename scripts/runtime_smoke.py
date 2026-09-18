# -*- coding: utf-8 -*-
"""运行时冒烟测试 —— 真实执行关键代码路径，不依赖静态推断。

用法：
    python scripts/runtime_smoke.py [项目根目录]
    不传参时默认为本脚本所在目录的上一级（即项目根）。

背景：
    2026-09-18 修掉的 4 个 P0 Bug 有共同特征 —— 错误处理路径自身出错，
    静态检查未必覆盖得到。本脚本真实触发这些路径，防止回归：

      Bug 1  main.py 上传截图失败路径   真实的失败复制（源文件不存在）
      Bug 2  main.py Excel 导入失败路径 真实的损坏 xlsx 喂给两个加载函数
      Bug 3  tools_page.py 日志          import 后 logger 真实存在且可调用
      Bug 4  api_demo_window.py 日期选择器  真实建出控件并触发选中事件

    验证的是「异常被哪个处理器接住」和「回调是否真的被调用」，
    而不是代码里写了什么字。

退出码：0 = 全部通过；1 = 有失败项。
"""
import os
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path

if len(sys.argv) > 1:
    ROOT = os.path.abspath(sys.argv[1])
else:
    ROOT = str(Path(__file__).resolve().parent.parent)

if not os.path.isfile(os.path.join(ROOT, "main.py")):
    print(f"找不到 {os.path.join(ROOT, 'main.py')}，请把项目根目录作为第一个参数传入")
    sys.exit(2)

sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

passed, failed = [], []


def check(label, ok, detail=""):
    (passed if ok else failed).append(label)
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}"
          + (f"\n        {detail}" if detail else ""))


def make_corrupt_xlsx():
    p = os.path.join(tempfile.mkdtemp(), "corrupt.xlsx")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("这不是一个 Excel 文件")
    return p


# ---------------------------------------------------------------------------
print("=" * 74)
print("Bug 1 —— main.py 上传截图失败路径")
print("=" * 74)
try:
    import main

    check("main 可导入", True)
    check("main.UnidentifiedImageError 已绑定（PIL 的异常类）",
          isinstance(main.UnidentifiedImageError, type)
          and issubclass(main.UnidentifiedImageError, Exception),
          f"{main.UnidentifiedImageError!r}")
    check("旧写法 main.PIL 确实不可用（证明原 Bug 真实存在）",
          not hasattr(main, "PIL"))

    # 真实制造一次失败：源文件不存在
    try:
        main.copy_account_image_to_store(
            Path(os.path.join(tempfile.mkdtemp(), "not_exist.png")))
        raised = None
    except Exception as exc:
        raised = exc
    check("源文件不存在时 copy_account_image_to_store 抛出异常", raised is not None,
          f"{type(raised).__name__}: {raised}")
    if raised is not None:
        check("该异常被修复后的 (UnidentifiedImageError, OSError) 捕获",
              isinstance(raised, (main.UnidentifiedImageError, OSError)))
except ImportError as exc:
    check("main 可导入", False, f"ImportError（环境缺依赖，跳过运行测试）: {exc}")

# ---------------------------------------------------------------------------
print()
print("=" * 74)
print("Bug 2 —— main.py Excel 导入失败路径")
print("=" * 74)
try:
    corrupt = make_corrupt_xlsx()
    for fname, label in (("load_excel_assets", "资产导入"),
                         ("import_credential_items_from_excel", "账号导入")):
        fn = getattr(main, fname, None)
        if fn is None:
            check(f"{fname} 存在", False)
            continue
        try:
            fn(Path(corrupt))
            raised = None
        except Exception as exc:
            raised = exc
        check(f"{fname} 对损坏文件抛出异常（{label}）", raised is not None,
              f"{type(raised).__module__}.{type(raised).__name__}")
        check(f"{fname} 的异常被 (zipfile.BadZipFile, OSError) 捕获",
              raised is not None
              and isinstance(raised, (zipfile.BadZipFile, OSError)))
except NameError:
    check("main 已导入", False, "Bug1 阶段导入失败，跳过")

# ---------------------------------------------------------------------------
print()
print("=" * 74)
print("Bug 3 —— tools_page.py logger")
print("=" * 74)
try:
    import logging
    import tools_page

    check("tools_page 可导入", True)
    check("tools_page.logger 存在", hasattr(tools_page, "logger"))
    check("tools_page.logger 是 logging.Logger 实例",
          isinstance(getattr(tools_page, "logger", None), logging.Logger),
          f"name={getattr(getattr(tools_page, 'logger', None), 'name', None)}")
    try:
        tools_page.logger.exception("冒烟测试：这条日志应正常输出而非抛 NameError")
        callable_ok = True
    except Exception as exc:
        callable_ok = False
        check("logger.exception() 可调用", False, f"{type(exc).__name__}: {exc}")
    if callable_ok:
        check("logger.exception() 可调用（原为 NameError）", True)
except ImportError as exc:
    check("tools_page 可导入", False, f"ImportError: {exc}")

# ---------------------------------------------------------------------------
print()
print("=" * 74)
print("Bug 4 —— api_demo_window.py 日期选择器闭包")
print("=" * 74)
try:
    import tkinter as tk
    from tkinter import ttk

    from embedded_admin_tools.api_demo_window import ApiDemoWindow

    root = tk.Tk()
    root.withdraw()

    calls = []

    class FakeSelf:
        def on_date_changed(self, *args):
            calls.append(args)

    var = tk.StringVar(value="2026-09-18")
    container = ApiDemoWindow._create_fixed_date_entry(
        FakeSelf(), root, var, None, "iface", "field")
    container.pack()
    root.update()

    check("日期选择器容器创建成功", container.winfo_exists() == 1)

    btns = [w for w in container.winfo_children() if isinstance(w, ttk.Button)]
    check("找到下拉按钮", len(btns) == 1)

    btns[0].invoke()          # 触发 show_calendar()
    root.update()

    # 在整棵控件树里递归找 Calendar 组件
    # （实测 Toplevel 挂在 container 之下，不是 root 的直接子节点）
    def find_calendar(widget):
        for child in widget.winfo_children():
            if type(child).__name__ == "Calendar":
                return child
            found = find_calendar(child)
            if found is not None:
                return found
        return None

    cal = find_calendar(root)
    check("日历弹窗已弹出", cal is not None)

    if cal is not None:
        calls.clear()
        try:
            cal.event_generate("<<CalendarSelected>>")   # 触发 on_select
            root.update()
            err = None
        except Exception as exc:
            err = exc
        check("触发选中事件未抛异常（原为 UnboundLocalError）", err is None,
              f"{type(err).__name__}: {err}" if err else "")
        check("on_date_changed 回调被调用", len(calls) > 0, f"调用参数={calls}")
    root.destroy()
except Exception as exc:
    check("Bug 4 运行测试可执行", False,
          f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-500:]}")

# ---------------------------------------------------------------------------
print()
print("=" * 74)
print(f"通过 {len(passed)} 项，失败 {len(failed)} 项")
if failed:
    for f in failed:
        print(f"  FAIL  {f}")
print("=" * 74)
sys.exit(1 if failed else 0)
