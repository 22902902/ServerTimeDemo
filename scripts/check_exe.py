# -*- coding: utf-8 -*-
"""打包产物体检：exe 时间戳 / 体积 + **从归档里反向核对源码真的进去了**。

为什么需要它
------------------------------------------------------------------------------
PyInstaller 的 onefile 把源码编译进 exe，出了问题也不报错 —— 曾出现过
「源码改了、也重打包了，但用户手上跑的还是旧行为」的误会。事后靠翻
`build/ExpiryManager_fixed/warn-*.txt` 和归档才能确认，很费劲。

这里做的是**反向核对**：打开 exe 的 CArchive → 取内嵌的 PYZ → 把目标模块的
code object 解开、递归收集 ``co_names`` / ``co_consts``，逐个断言新函数名与
新常量真的在里面。顺带清点 ``dist/`` 下的运行期数据，保证打包脚本没把它们删掉
（``build.bat`` 就干过这种事，见项目记忆的硬规则 3）。

用法::

    python scripts/check_exe.py                  # 检查 dist/ExpiryManager_fixed.exe
    python scripts/check_exe.py 别的.exe

加新功能之后，把新的函数名 / 常量名补进 ``EXPECTED`` 就行。
"""

from __future__ import annotations

import marshal
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 期望在归档里出现的符号（加功能时补这里）
EXPECTED = {
    "todo_db": [
        "pending_alerts", "mark_alerted", "snooze", "alert_moment",
        "parse_moment", "moment_str", "ALERT_GRACE_MINUTES", "SNOOZE_MINUTES",
        "alerted_for", "snooze_until",
    ],
    "todo_page": [
        "TodoAlertDialog", "ALERT_WIDTH", "snooze_all", "complete_all",
        "_place_bottom_right",
    ],
    "app_version": ["APP_VERSION", "VERSION_HISTORY", "1.8.0"],
    # main 是入口脚本，不在 PYZ 里，单独在 ENTRY_EXPECTED 核对
}
ENTRY_EXPECTED = [
    "todo_alert_check", "_run_todo_alerts", "show_todo_alert",
    "_close_todo_alert", "TODO_TICK_MS",
]

# 运行时数据：打包脚本**绝不能**删掉它们
DATA_PATHS = [
    "ExpiryManager_Data", "login_memory.json", "account_images",
    "study_notes_images", "study_notes_attachments", "process_flow_images",
    "Tools", "excel", "study_demo",
]


def symbols(code, acc: set) -> set:
    """递归收集 code object 里的标识符与常量字符串。

    ``repr(code)`` 只给出 ``<code object f at 0x...>`` —— 函数名在
    ``co_names`` 与 ``co_consts`` 里，必须自己走一遍。
    """
    if isinstance(code, (bytes, bytearray)):
        code = marshal.loads(code)
    if not isinstance(code, types.CodeType):
        return acc
    acc.update(code.co_names)
    acc.update(code.co_varnames)
    for const in code.co_consts:
        if isinstance(const, str):
            acc.add(const)
        elif isinstance(const, types.CodeType):
            symbols(const, acc)
    return acc


def main(argv: list[str]) -> int:
    exe = Path(argv[0]) if argv else ROOT / "dist" / "ExpiryManager_fixed.exe"
    if not exe.exists():
        print(f"找不到 {exe}")
        return 2

    stat = exe.stat()
    print(f"exe   {exe.name}")
    print(f"      体积 {stat.st_size:,} B（{stat.st_size / 1024 / 1024:.1f} MB）")
    print(f"      时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))}")

    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError:
        print("没装 PyInstaller，读不了归档")
        return 2

    reader = CArchiveReader(str(exe))
    names = list(reader.toc)
    pyz_name = next((n for n in names if "PYZ" in n), None)
    if not pyz_name:
        print("归档里没有 PYZ")
        return 1
    pyz = reader.open_embedded_archive(pyz_name)
    modules = set(pyz.toc)
    print(f"归档条目 {len(names)} 个，PYZ 模块 {len(modules)} 个")

    bad = 0
    for module, attrs in EXPECTED.items():
        if module not in modules:
            print(f"★ {module} 不在 PYZ 里")
            bad += 1
            continue
        found = symbols(pyz.extract(module), set())
        miss = [a for a in attrs if a not in found]
        print(f"      {module:<16} {'符号齐全' if not miss else f'★缺 {miss}★'}")
        bad += len(miss)

    entry = next((n for n in names if n == "main" or n.startswith("main.")), None)
    if entry is None:
        print("★ 没找到入口脚本条目")
        bad += 1
    else:
        found = symbols(reader.extract(entry), set())
        miss = [a for a in ENTRY_EXPECTED if a not in found]
        print(f"      {entry + ' (entry)':<16} "
              f"{'符号齐全' if not miss else f'★缺 {miss}★'}")
        bad += len(miss)

    print("\ndist 运行期数据:")
    for rel in DATA_PATHS:
        target = exe.parent / rel
        if target.is_dir():
            print(f"      {rel:<26} 目录，{sum(1 for _ in target.rglob('*'))} 个条目")
        elif target.exists():
            print(f"      {rel:<26} 文件，{target.stat().st_size:,} B")
        else:
            # 不存在不等于出问题（多数是还没被程序创建过），只是提醒一眼
            print(f"      {rel:<26} （不存在）")

    print()
    print("体检失败" if bad else "体检通过")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
