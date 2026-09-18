# -*- coding: utf-8 -*-
"""依赖清单盘点 —— 静态提取全项目 import，分类为 标准库 / 第三方 / 项目内。

只读分析，不做任何修改。
"""
import ast
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) \
    if len(sys.argv) < 2 else os.path.abspath(sys.argv[1])

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EXCLUDES = ("dist", "build", "__pycache__", ".git", ".workbuddy",
            "node_modules", "venv", ".venv", "Tools", "_icons")

files = []
for root, dirs, names in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in EXCLUDES and not d.startswith(".")]
    files += [os.path.join(root, f) for f in names if f.endswith(".py")]

# 项目内模块名（用于分类）
local_mods = set()
for f in files:
    rel = os.path.relpath(f, ROOT).replace("\\", "/")
    local_mods.add(os.path.splitext(os.path.basename(rel))[0])
    parts = rel.split("/")
    if len(parts) > 1:
        local_mods.add(parts[0])
local_mods |= {"embedded_admin_tools"}

stdlib = set(sys.stdlib_module_names)

mods = defaultdict(set)        # 顶层模块名 -> 引用它的文件集合
guard = defaultdict(set)       # 顶层模块名 -> 处于 try/except 保护内的文件
hard = defaultdict(set)        # 顶层模块名 -> 硬依赖（非保护）的文件


def top_level(node):
    """提取 Import/ImportFrom 需要「记功」的模块名。

    Import        import a.b.c                → 记 a（顶层）
    ImportFrom    from pkg.sub.mod import X   → 记 pkg 和 mod
                    （只有当 pkg 是**项目内**包时才额外记 mod；
                      否则 from Crypto.Cipher import DES 会把 Cipher 记成
                      一个第三方模块，制造噪音）
    ImportFrom    from pkg.sub import X       → 同上
    相对导入      from .x import y            → 记 x
    """
    if isinstance(node, ast.Import):
        return [a.name.split(".")[0] for a in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level:
            return [node.module.split(".")[-1]] if node.module else []
        parts = (node.module or "").split(".")
        if not parts or not parts[0]:
            return []
        credited = {parts[0]}
        if len(parts) > 1 and parts[0] in local_mods:
            credited.add(parts[-1])       # 项目内包 → 子模块也记功
        return sorted(credited)
    return []


def collect(tree):
    """返回 [(模块名, 是否在 try 保护内)]。"""
    results = []

    def walk(node, in_try):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for m in top_level(child):
                    results.append((m, in_try))
                continue
            walk(child, in_try or isinstance(child, ast.Try))

    walk(tree, False)
    return results


for path in sorted(files):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        src = fh.read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    rel = os.path.relpath(path, ROOT)
    for mod, in_try in collect(tree):
        mods[mod].add(rel)
        (guard if in_try else hard)[mod].add(rel)

third = sorted(m for m in mods
               if m not in stdlib and m not in local_mods and not m.startswith("."))

print("=" * 78)
print("第三方依赖（按顶层 import 名）")
print("=" * 78)
for m in third:
    h = sorted(hard.get(m, ()))
    g = sorted(guard.get(m, ()))
    risk = "硬依赖" if h else "可选（仅在 try 内）"
    print(f"\n  {m}   [{risk}]")
    if h:
        print(f"      硬依赖处: {', '.join(h[:3])}" + (" ..." if len(h) > 3 else ""))
    if g:
        print(f"      保护处  : {', '.join(g[:3])}" + (" ..." if len(g) > 3 else ""))

print()
print("=" * 78)
print("项目内模块被引用次数（找出死模块）")
print("=" * 78)
dead = []
for m in sorted(local_mods):
    if m == "__init__":
        continue
    users = sorted(u for u in mods.get(m, ())
                   if os.path.splitext(os.path.basename(u))[0] != m
                   and os.path.splitext(m)[0] not in u)
    if not users:
        dead.append(m)
if dead:
    print(f"  无人引用 {len(dead)} 个：")
    for m in dead:
        print(f"      {m}")
else:
    print("  无死模块")

print()
print(f"共分析 {len(files)} 个 .py；第三方顶层模块 {len(third)} 个；"
      f"项目内模块名 {len(local_mods)} 个（含包名与子模块名）")
