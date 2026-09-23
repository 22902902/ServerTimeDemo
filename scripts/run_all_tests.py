# -*- coding: utf-8 -*-
"""一条命令跑完全部回归套件，并汇总成一张表。

为什么需要它
------------------------------------------------------------------------------
本项目的套件分两类：纯逻辑的（test_todo、test_notes_markdown 的一部分）与
必须真开窗口的（test_todo_ui、test_shell_ui…）。**跑法不一样**：窗口类的
套件在托管 venv / Python 3.13 上会直接 `ModuleNotFoundError: tkinter`
（那两个都是便携构建，不带 tkinter），只有系统 Python 3.12 能跑。
于是「跑全量」这件事以前要手动分批、还容易漏掉一两个套件。

本脚本：
* 检查当前解释器有没有 tkinter，没有就直接说清楚该换哪个，不闷头跑出一片假红
* 挨个跑、抽出「通过 N 项，失败 M 项」汇总，最后给一行合计
* 某个套件崩了（没有汇总行）时打印它最后几行输出，而不是只报一个失败数

用法::

    python scripts/run_all_tests.py            # 全部
    python scripts/run_all_tests.py todo       # 只跑名字里含 todo 的
    python scripts/run_all_tests.py --json build/manual/test_baseline.json
                                               # 顺带把结果写成 JSON，供
                                               # make_python_manual 引用
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = [
    "test_notes_markdown",
    "test_notes_editor",
    "test_shell_ui",
    "test_tools_launcher",
    "test_log_setup",
    "test_expiry_table",
    "test_detail_dialog",
    "test_release_meta",
    "test_todo",
    "test_todo_ui",
    "test_process",
    "test_process_ui",
    "test_excel",
    "test_excel_ui",
]
SMOKE = "runtime_smoke"
SUMMARY_RE = re.compile(r"通过\s*(\d+)\s*项[，,]\s*失败\s*(\d+)\s*项")


def summarise(name: str, interpreter: str) -> tuple[int, int, str]:
    proc = subprocess.run(
        [interpreter, str(ROOT / "scripts" / f"{name}.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    match = SUMMARY_RE.search(out)
    if match:
        return int(match.group(1)), int(match.group(2)), ""
    tail = "\n".join(out.strip().splitlines()[-8:])
    return 0, 1, tail


def main(argv: list[str]) -> int:
    args = list(argv)
    json_out = None
    if "--json" in args:
        index = args.index("--json")
        if index + 1 >= len(args):
            print("--json 后面要跟一个输出路径，例如 --json build/manual/test_baseline.json")
            return 2
        json_out = args[index + 1]
        del args[index:index + 2]

    if not args:
        # 用 find_spec 探测而不是 import：pyflakes 不认 noqa（那是 flake8 的），
        # 真 import 进来又不用，会被报一条「imported but unused」
        if importlib.util.find_spec("tkinter") is None:
            print("当前解释器没有 tkinter，界面类套件跑不起来。")
            print(r"请改用系统 Python：C:\Users\shaoy\AppData\Local\Programs"
                  r"\Python\Python312\python.exe")
            return 2

    wanted = [s for s in SUITES
              if not args or any(a in s for a in args)]
    total_pass = total_fail = 0
    rows = []

    for name in wanted + ([SMOKE] if not args else []):
        if not (ROOT / "scripts" / f"{name}.py").exists():
            print(f"{name:<24} 找不到脚本，跳过")
            continue
        passed, failed, tail = summarise(name, sys.executable)
        total_pass += passed
        total_fail += failed
        rows.append({"name": name, "passed": passed, "failed": failed})
        print(f"{name:<24} 通过 {passed:>4} 项   失败 {failed}")
        if tail:
            print(tail)

    print("-" * 46)
    print(f"{'合计':<24} 通过 {total_pass:>4} 项   失败 {total_fail}")

    if json_out:
        target = Path(json_out)
        if not target.is_absolute():
            target = ROOT / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(json.dumps({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "interpreter": sys.executable,
            "suites": rows,
            "total_passed": total_pass,
            "total_failed": total_fail,
        }, ensure_ascii=False, indent=2).encode("utf-8"))
        print(f"结果已写入 {target}")

    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
