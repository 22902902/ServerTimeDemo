# -*- coding: utf-8 -*-
"""未使用导入裁剪器 —— 依据 pyflakes 结果精确删除导入名，只读预览为默认。

用法：
    # 预览（不写文件）
    python scripts/prune_unused_imports.py [文件/目录 ...]

    # 实际写入
    python scripts/prune_unused_imports.py --apply [文件/目录 ...]

    # 指定 pyflakes 所在的解释器（默认用当前解释器）
    python scripts/prune_unused_imports.py --pyflakes-python <python.exe> [路径 ...]

为什么不用文本编辑器直接改：
    本项目 `main.py` 是 CRLF(5012) + LF(168) 混排行尾。用普通文本编辑写入会把
    整个文件统一成 LF，使几行改动变成数千行的 diff（已发生过一次）。本脚本
    读取 bytes → 只在目标语句的行范围内做替换 → 原样写回，未触碰的行字节不变。

处理范围（只动这两类 pyflakes 报告）：
    'mod.Name' imported but unused              删除该名字
    redefinition of unused 'X' from line N      删除第 N 行里那个被遮蔽的名字

不处理 unused local variable —— 那可能是漏写的逻辑（本项目的审计报告 3.8 节
就有两处 `dlg` 疑似漏调 wait_window），删之前需要人工判断。
"""
import ast
import os
import re
import subprocess
import sys

BOM = b"\xef\xbb\xbf"
EXCLUDES = ("dist", "build", "__pycache__", ".git", ".workbuddy",
            "node_modules", "venv", ".venv", "Tools", "_icons")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UNUSED_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):\d+: "
                       r"'(?P<name>[^']+)' imported but unused$")
REDEF_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):\d+: "
                      r"redefinition of unused '(?P<name>[^']+)' from line (?P<from>\d+)$")


# ---------------------------------------------------------------------------
# pyflakes 调用
# ---------------------------------------------------------------------------
def collect_files(args):
    out = []
    for a in args:
        if os.path.isdir(a):
            for root, dirs, names in os.walk(a):
                dirs[:] = [d for d in dirs if d not in EXCLUDES and not d.startswith(".")]
                out += [os.path.join(root, n) for n in names if n.endswith(".py")]
        elif a.endswith(".py"):
            out.append(a)
    return sorted(out)


def run_pyflakes(files, pybin):
    proc = subprocess.run([pybin, "-m", "pyflakes", *files],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    # pyflakes 把结果写在 stdout
    return (proc.stdout or "") + (proc.stderr or "")


def parse_findings(output):
    """返回 {文件绝对路径: {行号: [要删的名字, ...]}}。"""
    plan = {}
    for raw in output.splitlines():
        line = raw.strip()
        m = UNUSED_RE.match(line)
        target_line, name = None, None
        if m:
            target_line, name = int(m.group("line")), m.group("name")
        else:
            m = REDEF_RE.match(line)
            if m:
                # 被遮蔽的是「更早那次」导入 → 从那一行删
                target_line, name = int(m.group("from")), m.group("name")
        if target_line is None:
            continue
        path = os.path.abspath(m.group("path"))
        plan.setdefault(path, {}).setdefault(target_line, []).append(name)
    return plan


# ---------------------------------------------------------------------------
# 文本手术
# ---------------------------------------------------------------------------
def _alias_text(alias):
    return alias.name + (f" as {alias.asname}" if alias.asname else "")


def _matches(alias, module, want):
    """判断某个 alias 是否是 pyflakes 报告的那个名字。"""
    candidates = {alias.name}
    if module:
        candidates.add(f"{module}.{alias.name}")
    if alias.asname:
        candidates.add(alias.asname)
        if module:
            candidates.add(f"{module}.{alias.asname}")
    return want in candidates


def _split_comment(s):
    """把 `... # comment` 拆成 (code, comment)。只在注释确实在引号外时切。"""
    in_s = in_d = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            return s[:i].rstrip(), s[i:].rstrip()
    return s, ""


def _indent_of(line):
    return line[:len(line) - len(line.lstrip(" \t"))]


def apply_edits(path, removals):
    """returns (changed: bool, before_text, after_text, notes)"""
    raw = open(path, "rb").read()
    has_bom = raw.startswith(BOM)
    data = raw[len(BOM):] if has_bom else raw
    text = data.decode("utf-8")

    tree = ast.parse(text)
    parts = text.splitlines(keepends=True)
    default_eol = "\r\n" if "\r\n" in text else "\n"

    # 收集所有 import 语句（含嵌套在 try 里的）
    imports = [n for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))]

    edits = []          # (start_idx, end_idx, replacement, note)
    for lineno, wants in sorted(removals.items()):
        node = next((n for n in imports if n.lineno == lineno), None)
        if node is None:
            edits.append((lineno - 1, lineno, None,
                          f"第 {lineno} 行不是 import 语句（可能已被前面的删除改动），跳过"))
            continue

        module = getattr(node, "module", None)
        drop_idx = [i for i, a in enumerate(node.names)
                    if any(_matches(a, module, w) for w in wants)]
        if not drop_idx:
            edits.append((lineno - 1, lineno, None,
                          f"第 {lineno} 行找不到 {wants}，跳过"))
            continue

        keep = [a for i, a in enumerate(node.names) if i not in drop_idx]
        start, end = node.lineno - 1, node.end_lineno          # end 为独占
        block = "".join(parts[start:end])
        eol = "\r\n" if block.endswith("\r\n") else ("\n" if block.endswith("\n") else default_eol)

        dropped_names = [_alias_text(a) for i, a in enumerate(node.names) if i in drop_idx]

        if not keep:
            edits.append((start, end, "",
                          f"删除整条 import（{', '.join(dropped_names)} 全部未使用）"))
            continue

        is_multi = "\n" in block.rstrip("\r\n") or node.end_lineno > node.lineno
        head = ("import " if isinstance(node, ast.Import)
                else f"from {module} import ")
        base_indent = _indent_of(parts[start])

        if is_multi:
            if len(keep) == 1:
                new = f"{base_indent}{head}{_alias_text(keep[0])}{eol}"
                note = (f"折叠为单行，保留 {_alias_text(keep[0])}；"
                        f"删除 {', '.join(dropped_names)}")
            else:
                # 原位保留原有折行：只把被删的名字从它所在的那一行摘掉，
                # 其余行原样不动。这样最小化 diff，也保住作者的分组意图。
                joined = "".join(parts[start:end])
                lp, rp = joined.index("("), joined.rindex(")")
                inner_lines = joined[lp + 1:rp].split("\n")

                # 逐行按逗号切分，按出现顺序对应 node.names 的下标
                line_of = []          # 每个 alias 下标 -> 所在行号
                for li, line in enumerate(inner_lines):
                    for tok in line.split(","):
                        if tok.strip():
                            line_of.append(li)

                if len(line_of) != len(node.names):
                    # 切分与 AST 对不上（含嵌套括号等）→ 退回保险的展开写法
                    indent = base_indent + "    "
                    body = "".join(f"{indent}{_alias_text(a)},{eol}" for a in keep)
                    new = f"{base_indent}{head}({eol}{body}{base_indent}){eol}"
                    note = (f"保留 {len(keep)} 个名字（原折行无法安全保留，已重排）；"
                            f"删除 {', '.join(dropped_names)}")
                else:
                    keep_set = {i for i, a in enumerate(node.names) if a in keep}
                    per_line = {li: [i for i in keep_set if line_of[i] == li]
                                for li in range(len(inner_lines))}
                    emit = []
                    for li, idxs in per_line.items():
                        if not idxs:
                            continue
                        indent = inner_lines[li][:len(inner_lines[li])
                                                 - len(inner_lines[li].lstrip(" \t"))]
                        emit.append(indent + ", ".join(_alias_text(node.names[i])
                                                       for i in idxs) + ",")
                    if not emit:
                        edits.append((start, end, "",
                                      f"删除整条 import（{', '.join(dropped_names)} 全部未使用）"))
                        continue
                    body = eol.join(emit)
                    new = f"{base_indent}{head}({eol}{body}{eol}{base_indent}){eol}"
                    note = (f"保留 {len(keep)} 个名字（原位保留原折行）；"
                            f"删除 {', '.join(dropped_names)}")
        else:
            orig = parts[start]
            _code, comment = _split_comment(orig.rstrip("\r\n"))
            names = ", ".join(_alias_text(a) for a in keep)
            gap = "  " if comment else ""
            # 必须保留原缩进：缩进的 import 通常位于 try / if 块内，
            # 去掉缩进会把块体挖空（已由本脚本的语法校验拦下过一次）
            new = f"{base_indent}{head}{names}{gap}{comment}{eol}"
            note = (f"保留 {', '.join(_alias_text(a) for a in keep)}；"
                    f"删除 {', '.join(dropped_names)}")

        edits.append((start, end, new, note))

    if not edits:
        return False, text, text, []

    # 从后往前替换，避免行号位移
    new_parts = list(parts)
    notes = []
    for start, end, repl, note in sorted(edits, key=lambda e: -e[0]):
        new_parts[start:end] = [repl] if repl else []
        notes.append(note)

    after = "".join(new_parts)
    if after == text:
        return False, text, text, notes
    return True, text, after, notes


def print_diff(before, after, limit=40):
    import difflib
    diff = list(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        "before", "after", lineterm="", n=2))
    for line in diff[:limit]:
        print("      " + line)
    if len(diff) > limit:
        print(f"      ... 还有 {len(diff) - limit} 行差异")


# ---------------------------------------------------------------------------
def main():
    argv = sys.argv[1:]
    do_apply = "--apply" in argv
    argv = [a for a in argv if a != "--apply"]

    pybin = sys.executable
    if "--pyflakes-python" in argv:
        i = argv.index("--pyflakes-python")
        pybin = argv[i + 1]
        del argv[i:i + 2]

    targets = collect_files(argv) if argv else collect_files([ROOT])
    targets = [t for t in targets
               if "/scripts/" not in t.replace("\\", "/")
               and "/tmp_debug/" not in t.replace("\\", "/")
               and not os.path.basename(t).startswith("_")]

    if not targets:
        print("没有待检查的文件")
        return 2

    output = run_pyflakes(targets, pybin)
    plan = parse_findings(output)

    print("=" * 78)
    print(f"pyflakes 报告未使用导入的文件：{len(plan)} 个；"
          f"模式：{'写入' if do_apply else '预览（不写文件）'}")
    print("=" * 78)

    total_removed, changed_count, failed = 0, 0, []
    for path in sorted(plan):
        rel = os.path.relpath(path, ROOT)
        print(f"\n【{rel}】")
        try:
            changed, before, after, notes = apply_edits(path, plan[path])
        except Exception as exc:
            print(f"  处理失败：{type(exc).__name__}: {exc}")
            failed.append(rel)
            continue

        for note in notes:
            print(f"      - {note}")
        total_removed += sum(len(v) for v in plan[path].values())

        if not changed:
            print("      （无实际改动）")
            continue

        # 安全校验：改完必须仍能解析
        try:
            ast.parse(after)
        except SyntaxError as exc:
            print(f"  ✗ 改写后语法错误，已放弃该文件：{exc}")
            failed.append(rel)
            continue

        changed_count += 1
        print_diff(before, after)

        if do_apply:
            raw = open(path, "rb").read()
            has_bom = raw.startswith(BOM)
            payload = after.encode("utf-8")
            open(path, "wb").write((BOM if has_bom else b"") + payload)
            print(f"      ✓ 已写入（BOM={'保留' if has_bom else '无'}）")

    print()
    print("=" * 78)
    print(f"合计：涉及 {len(plan)} 个文件，删除 {total_removed} 个名字，"
          f"实际改写 {changed_count} 个文件"
          + (f"，失败 {len(failed)} 个" if failed else ""))
    if not do_apply and changed_count:
        print("这是预览。确认无误后加 --apply 写入。")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
