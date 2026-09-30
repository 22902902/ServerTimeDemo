# -*- coding: utf-8 -*-
"""打包产物体检：exe 时间戳 / 体积 + **从归档里反向核对源码真的进去了**。

为什么需要它
------------------------------------------------------------------------------
PyInstaller 的 onefile 把源码编译进 exe，出了问题也不报错 —— 曾出现过
「源码改了、也重打包了，但用户手上跑的还是旧行为」的误会。事后靠翻
`build/ExpiryManager_fixed/warn-*.txt` 和归档才能确认，很费劲。

这里做的是**反向核对**：打开 exe 的 CArchive → 取内嵌的 PYZ → 把目标模块的
code object 解开、递归收集 ``co_names`` / ``co_consts``，逐个断言新函数名与
新常量真的在里面。顺带清点运行目录（随身包）下的运行期数据，保证打包脚本没把它们删掉
（``build.bat`` 就干过这种事，见项目记忆的硬规则 3）。

用法::

    python scripts/check_exe.py                  # 检查随身包里的 ExpiryManager_fixed.exe
    python scripts/check_exe.py 别的.exe
    python scripts/check_exe.py --selfcheck      # 只用本地源码核 EXPECTED（不打开 exe）

加新功能之后，把新的函数名 / 常量名补进 ``EXPECTED`` 就行 ——
**但先跑一次 ``--selfcheck``**：``_collect`` 收的是整条常量与 ``co_names``，
SQL 里嵌的列名、运行时现算的值都收不到，照抄一份清单必然假红。
"""

from __future__ import annotations

import marshal
import os
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 运行目录（随身包）——与 make_portable / export_sensitive 同一个约定。
# dist/ 已弃用删除，exe 的默认位置在这里。
PORTABLE_DIR = Path(os.environ.get("SERVERDEMO_PORTABLE_DIR",
                                   r"F:\ServerTimeDemo_随身包"))
EXE_NAME = "ExpiryManager_fixed.exe"

# 期望在归档里出现的符号（加功能时补这里）
EXPECTED = {
    "db_backup": [
        # 已在本地源码上预演过：这 11 个都能被 _collect 收到
        "BACKUP_DIR_NAME", "BACKUP_SUFFIX", "SNAPSHOT_MIN_INTERVAL",
        "ROLLBACK_KEEP_PREFIX", "backup_path", "is_write_sql", "snapshot",
        "verify", "restore", "connect", "_tracer_for",
    ],
    "todo_db": [
        "pending_alerts", "mark_alerted", "snooze", "alert_moment",
        "parse_moment", "moment_str", "ALERT_GRACE_MINUTES", "SNOOZE_MINUTES",
        "alerted_for", "snooze_until",
    ],
    "todo_page": [
        "TodoAlertDialog", "ALERT_WIDTH", "snooze_all", "complete_all",
        "_place_bottom_right",
    ],
    "app_version": ["APP_VERSION", "VERSION_HISTORY", "1.19.0"],
    "training_core": [
        "SRS_INTERVALS", "review_next_state", "streak_from_dates",
        "checkin_grid", "MASTERY_GOOD", "FEEDBACK_FORGOT",
        # v1.19.0：SM-2 / FSRS 两套新算法与可切换的唯一入口
        "advance_review", "normalize_algorithm", "algorithm_label",
        "sm2_next_state", "fsrs_next_state", "fsrs_retrievability",
        "fsrs_interval_for", "ALGORITHM_HINTS", "DEFAULT_ALGORITHM",
    ],
    "memory_db": [
        "MemoryPalaceDB", "PALACE_KINDS", "DEFAULT_PALACE_NAME",
        "format_item_line",
        # v1.18.0 题库项的「位置与四周」与实景截图（前者是 MemoryPalaceDB 的方法）
        "_ensure_memory_columns", "get_bank_item", "update_bank_item",
        # v1.19.0：算法选择落在 train_settings 表（**表名嵌在 SQL 字符串里，
        # _collect 收不到** —— 预演时确实报了「收不到」，所以只查读写它的两个方法）
        "get_algorithm", "set_algorithm",
    ],
    "cs2_seed": [
        # v1.18.0：七张比赛地图点位的单一数据源（宫殿与题库都由它生成）。
        # 地图码只在这里 —— memory_seed 是运行时现算的，它那边没有。
        "MAPS", "MIN_CALLOUTS", "MIRAGE_DETAILS", "counts", "validate",
        "TPL_CS2_DUST2", "BANK_CS2_DUST2", "TPL_CS2_INFERNO", "BANK_CS2_INFERNO",
        "TPL_CS2_NUKE", "BANK_CS2_NUKE", "TPL_CS2_ANCIENT", "BANK_CS2_ANCIENT",
        "TPL_CS2_ANUBIS", "BANK_CS2_ANUBIS", "TPL_CS2_TRAIN", "BANK_CS2_TRAIN",
        # 点位名嵌在 callouts 的元组里，靠 _collect 递归才看得见
        "B 隧道（Tunnels）", "香蕉道（Banana）", "CT 出生点（CT Spawn）",
    ],
    "memory_seed": [
        "SEED_NUMBER_PEGS", "SEED_PALACE_TEMPLATES", "TEACHING_CARDS",
        "MIN_CARDS", "validate",
        # v1.17.0 三套游戏训练包（桩名嵌在 loci 的元组里，靠 _collect 递归才看得见）
        "TPL_SUDOKU", "TPL_CS2_MIRAGE", "TPL_XIANGQI",
        "BANK_SUDOKU", "BANK_CS2_MIRAGE", "BANK_XIANGQI",
        "唯一余数 Naked Single", "马后炮", "T 出生点 T Spawn",
        # v1.18.0 另外六张图的宫殿 / 题库**由这两个函数现算**（地图码与点位名都在
        # cs2_seed，这里只查「生成器本身有没有打进包」）
        "_cs2_palace", "_cs2_bank",
    ],
    "memory_page": [
        "WalkSession", "VIEW_WORKBENCH", "VIEW_LIBRARY", "PalaceDialog",
        # v1.18.0 题库详情弹窗 + 实景截图（上传 / 粘贴入口是调用方补的）
        "BankItemDialog", "MemoryImageTools", "create_image_actions",
        "MEMORY_IMAGE_SUBDIR",
        # 真实字面量是「详情 / 位置与四周」，不是「位置与四周」
        # （_collect 收的是**整条**常量，所以不能拿子串去比对）
        "详情 / 位置与四周", "看详情",
        # v1.19.0：语音朗读（speech 是被 import 的模块名，出现在 co_names 里）
        "toggle_speech", "speech",
    ],
    "mindmap_db": [
        "MindmapDB", "DEFAULT_MAP_TITLE", "format_map_line",
        # v1.19.0：自由画布的手工坐标 + 训练算法选择
        "node_positions", "set_node_pos", "clear_node_positions",
        "get_algorithm", "set_algorithm",
    ],
    "mindmap_layout": [
        "blind_brief", "reveal_levels", "to_opml", "iter_nodes",
        "build_tree", "DEPTH_COLORS",
    ],
    "mindmap_seed": [
        "TEMPLATES", "TEACHING_CARDS", "validate", "template_categories",
        # v1.17.0 三张知识树（大纲是整块字符串常量，直接可见）
        "TPL_MM_SUDOKU", "TPL_MM_CS2", "TPL_MM_XIANGQI", "游戏训练",
    ],
    "mindmap_page": [
        "BlindSession", "VIEW_EDITOR", "VIEW_WALL", "TREE_MAP",
        "ZOOM_VALUES",
        # v1.19.0：自由画布拖拽 + 语音朗读
        "toggle_speech", "speech", "_on_canvas_press", "_on_canvas_release",
    ],
    "mindmap_image": [
        "render_png", "available", "pick_font", "FONT_CANDIDATES",
    ],
    "training_todo_bridge": [
        "TrainingTodoBridge", "review_payload", "KIND_MEMORY", "KIND_MINDMAP",
    ],
    # ── v1.19.0 新增模块 ────────────────────────────────────────────────
    "speech": [
        "is_available", "enabled", "set_enabled", "toggle", "speak", "stop",
    ],
    "mindmap_memory_bridge": ["plan", "convert", "source_key"],
    "excel_formula_hl": [
        "tokenize", "Token", "KINDS",
        # 六类 + text 就写在 KINDS 这个元组常量里，所以直接收得到
        "func", "string", "ref", "number", "operator", "paren",
    ],
    "excel_export": ["markdown_to_html", "print_document", "PRINT_STYLE"],
    "process_image_migrate": [
        "plan_step", "migrate", "normalize_rel", "SUBDIR_ROOT",
    ],
    "process_annotate": [
        "normalize_op", "normalize_ops", "clamp_box", "clamp_point",
        "arrow_head", "candidate_path", "apply_ops", "annotate_file",
        "SHAPE_LABELS", "SHAPE_ORDER", "COLORS", "SUFFIX",
    ],
    "process_annotate_dialog": [
        "ScreenshotAnnotator", "to_image", "to_canvas", "ask_string",
        "_redraw_ops", "VIEW_MAX", "MIN_DRAG",
    ],
    "process_todo_bridge": [
        "ProcessTodoBridge", "flow_todo_payload", "flow_todo_title",
        "step_titles", "FLOW_TODO_TAG",
    ],
    "process_terminal": [
        "choose_launcher", "launcher_argv", "send_to_terminal",
        "TERMINAL_CANDIDATES",
    ],
    # ── v1.19.0 改动到的既有模块 ────────────────────────────────────────
    "excel_db": ["functions_markdown", "export_functions_markdown", "heatmap"],
    "process_db": [
        "fetch_process_templates", "save_process_template",
        "delete_process_template",
    ],
    "process_page": [
        "CommandBlock", "ScreenshotStrip", "today_str",
        "annotate_step_image", "add_flow_to_todo", "send_command_to_terminal",
        "_save_annotation", "process_todo_bridge", "process_annotate",
    ],
    # main 是入口脚本，不在 PYZ 里，单独在 ENTRY_EXPECTED 核对
}
ENTRY_EXPECTED = [
    "todo_alert_check", "_run_todo_alerts", "show_todo_alert",
    "_close_todo_alert", "TODO_TICK_MS",
    # v1.16.0 训练模块接线
    "MemoryPalacePage", "MindMapPage", "TrainingTodoBridge",
    "memory_page_refresh", "mindmap_page_refresh",
    # v1.19.0 流程中心 P2 的接线：三个新模块 + 两个垫片方法
    "process_image_migrate", "process_todo_bridge", "process_terminal",
    "ProcessTodoBridge", "process_todo_hook", "send_to_terminal",
]

# 运行时数据：打包脚本**绝不能**删掉它们
DATA_PATHS = [
    # 主库必须排第一 —— 打包脚本丢了别的东西还能忍，丢了这个是丢全部
    "expiry_manager.db", "_backup",
    "ExpiryManager_Data", "login_memory.json", "account_images",
    "study_notes_images", "study_notes_attachments", "process_flow_images",
    "Tools", "excel", "study_demo",
]


def _collect(obj, acc: set) -> None:
    """递归收集标识符与常量字符串。

    ★ **必须递归进 tuple / list / frozenset。** 地点桩是 ``loci`` 列表里的二元组，
    字节码里整个元组列表是模块的**一个常量**（``BUILD_LIST`` 拿元组常量建列表），
    所以「桩名」是嵌在元组里面的字符串。只认 ``co_consts`` 里的直接字符串，
    就会一个桩名都收集不到 —— 然后得出「内容没打进包」的**错误结论**（本轮实测）。
    """
    if isinstance(obj, (bytes, bytearray)):
        try:
            obj = marshal.loads(obj)
        except Exception:                        # noqa: BLE001
            return
    if isinstance(obj, types.CodeType):
        acc.update(obj.co_names)
        acc.update(obj.co_varnames)
        for const in obj.co_consts:
            _collect(const, acc)
    elif isinstance(obj, str):
        acc.add(obj)
    elif isinstance(obj, (tuple, list, frozenset, set)):
        for item in obj:
            _collect(item, acc)


def symbols(code, acc: set) -> set:
    """递归收集 code object 里的标识符与常量字符串。

    ``repr(code)`` 只给出 ``<code object f at 0x...>`` —— 函数名在
    ``co_names`` 与 ``co_consts`` 里，必须自己走一遍。
    """
    _collect(code, acc)
    return acc


def selfcheck() -> int:
    """只用**本地源码**核一遍 EXPECTED / ENTRY_EXPECTED。

    为什么值得单独有个模式：清单写错和「没打进包」在体检输出里长得一模一样
    （都是「★缺 xxx」），而后者要重打包一分钟才验证得出来。预演一次就几秒：

    * SQL 里嵌的列名收不到（它只是大字符串常量的一部分）；
    * 运行时现算的值收不到（v1.18.0 有 6 个地图码被错记到 memory_seed 名下，
      而它们只存在于 cs2_seed）；
    * 名字干脆不存在（拼错）。

    返回非零即「清单写错了」，与打包无关。
    """
    bad = 0
    for module, attrs in EXPECTED.items():
        path = ROOT / f"{module}.py"
        if not path.exists():
            print(f"★ {module:<24} 本地找不到源码，清单里的模块名写错了？")
            bad += 1
            continue
        try:
            code = compile(path.read_text(encoding="utf-8"), str(path), "exec",
                           dont_inherit=True)
        except SyntaxError as exc:
            print(f"★ {module:<24} 本地源码编译不过：{exc}")
            bad += 1
            continue
        miss = [a for a in attrs if a not in symbols(code, set())]
        if miss:
            print(f"★ {module:<24} 本地源码里收不到：{miss}")
            bad += len(miss)
        else:
            print(f"  ok {module:<24} {len(attrs)} 个符号都在本地源码里")

    entry = ROOT / "main.py"
    if entry.exists():
        code = compile(entry.read_text(encoding="utf-8"), str(entry), "exec",
                       dont_inherit=True)
        found = symbols(code, set())
        miss = [a for a in ENTRY_EXPECTED if a not in found]
        if miss:
            print(f"★ {'main (entry)':<24} 本地源码里收不到：{miss}")
            bad += len(miss)
        else:
            print(f"  ok {'main (entry)':<24} {len(ENTRY_EXPECTED)} 个符号都在本地源码里")

    print()
    print("清单自检失败：先修 EXPECTED（这不是打包问题）" if bad
          else "清单自检通过：EXPECTED 全部收得到，可以去体检 exe 了")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if "--selfcheck" in argv:
        return selfcheck()
    exe = Path(argv[0]) if argv else next(
        (c for c in (PORTABLE_DIR / EXE_NAME, ROOT / "dist" / EXE_NAME)
         if c.exists()), PORTABLE_DIR / EXE_NAME)
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

    print(f"\n{exe.parent} 运行期数据:")
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
