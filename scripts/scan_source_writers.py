# -*- coding: utf-8 -*-
"""源码写入扫描 —— 找出会「就地重写源码」的脚本（只读分析，绝不修改文件）。

用法：
    python scripts/scan_source_writers.py [扫描根目录] [排除目录,逗号分隔]

为什么需要它：
    本项目曾长期把一次性补丁脚本放在项目根目录（`_fix_xxx.py` 之类），
    它们硬编码绝对路径并以写模式 `open()` 直接覆写 main.py 等核心文件，
    误运行一次即可损坏源码。逐个读代码太慢，静态扫描可以一次性列全。

判定方式：
    用 AST 找所有写操作（`open(..., 'w')`、`.write_text()`、`.write_bytes()`），
    再把写入目标**沿变量绑定回溯**，看它是否落在 `.py` 文件上。例如

        OUTPUT_PATH = PROJECT_ROOT / "services" / "icon_service.py"   # 模块级绑定
        OUTPUT_PATH.write_text(...)                                    # ← 判定为写源码

    只做一层到三层的名字回溯，不去解析函数参数或运行时才知道的路径；
    这类无法静态判定的目标归入「B 级」，并在输出里明确标注为「未解析」，
    不会误报成阻断项。

分级：
    A 级（阻断，退出码 1）目标可解析且落在 .py 上 —— 会改源码
    B 级（提示）          有写操作，但目标不是 .py 或无法静态解析
    C 级（弱信号）        文件对象 `.write()`，目标需人工确认

退出码：0 = 无「未被豁免的」A 级；1 = 存在未被豁免的 A 级。
"""
import ast
import os
import re
import sys

# A 级豁免清单：这些脚本**故意**生成源码文件，是资产工具而非一次性补丁。
# 之所以显式列出来（而不是写个宽泛规则），是为了让豁免可见 —— 输出里会逐条
# 打印豁免原因，任何新增的写源码脚本仍然会被拦住。
ALLOWED = {
    "scripts/gen_app_icon_service.py":
        "生成 services/app_icon_service.py（应用图标 base64 内嵌模块）",
    "scripts/gen_icon_service.py":
        "生成 services/icon_service.py（界面图标 base64 内嵌模块）",
}

if len(sys.argv) > 1:
    ROOT = os.path.abspath(sys.argv[1])
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_EXCLUDES = ("dist", "build", "__pycache__", ".git", ".workbuddy",
                    "node_modules", "venv", ".venv", "Tools", "_icons")
if len(sys.argv) > 2:
    EXCLUDES = tuple(x.strip() for x in sys.argv[2].split(",") if x.strip())
else:
    EXCLUDES = DEFAULT_EXCLUDES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

WRITE_MODES = {"w", "wb", "a", "ab", "r+", "w+", "rb+", "wb+", "x", "xb"}
PY_LITERAL_RE = re.compile(r"""["'][^"']*\.py["']""")


def _collect_bindings(tree):
    """收集 name -> 赋值表达式节点（后出现的覆盖先出现的）。"""
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    bindings[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bindings[node.target.id] = node.value
    return bindings


def _resolves_to_py(expr, bindings, depth=0):
    """沿名字绑定回溯，判断该表达式最终是否指向 .py 文件。

    返回 True（确定是 .py）/ False（确定不是）/ None（无法静态判定）。
    """
    if expr is None or depth > 3:
        return None
    src = ast.unparse(expr)
    if ".py" in "".join(re.findall(r"""["'][^"']*["']""", src)):
        return True
    if isinstance(expr, ast.Name):
        if expr.id not in bindings:
            return None                      # 函数参数 / 导入名 / 运行时才知
        return _resolves_to_py(bindings[expr.id], bindings, depth + 1)
    return False                             # 字面量或表达式，且不含 .py


def scan(path):
    """返回 [(行号, 操作描述, 目标表达式, 是否 .py)]，不执行任何代码。"""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        src = fh.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [(exc.lineno or 0, "语法错误，无法分析", str(exc), None)]

    bindings = _collect_bindings(tree)
    hits = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = getattr(func, "attr", None) or getattr(func, "id", None)

        # 形式 1：open(<目标>, '<写模式>')
        if fname == "open":
            modes = [a.value for a in node.args[1:]
                     if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            modes += [kw.value.value for kw in node.keywords
                      if kw.arg == "mode" and isinstance(kw.value, ast.Constant)
                      and isinstance(kw.value.value, str)]
            if any(m in WRITE_MODES for m in modes):
                target = node.args[0] if node.args else None
                hits.append((node.lineno, f"open(..., {modes[0]!r})",
                             ast.unparse(target) if target else "?", 
                             _resolves_to_py(target, bindings)))

        # 形式 2：<目标>.write_text(...) / .write_bytes(...)
        elif fname in ("write_text", "write_bytes"):
            target = node.func.value if isinstance(node.func, ast.Attribute) else None
            hits.append((node.lineno, f".{fname}()",
                         ast.unparse(target) if target else "?",
                         _resolves_to_py(target, bindings)))

        # 形式 3：文件对象 .write() —— 需回溯赋值来源，这里只标记弱信号
        elif fname == "write":
            hits.append((node.lineno, ".write()", "(文件对象)", None))

    return hits


files = []
for root, dirs, names in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in EXCLUDES and not d.startswith(".")]
    files += [os.path.join(root, f) for f in names if f.endswith(".py")]

print("=" * 78)
print(f"扫描 {ROOT}")
print(f"排除：{', '.join(EXCLUDES)}")
print(f"共 {len(files)} 个 .py")
print("=" * 78)

tier_a, tier_b, tier_c = [], [], []
for path in sorted(files):
    hits = scan(path)
    if not hits:
        continue
    rel = os.path.relpath(path, ROOT)
    a = [h for h in hits if h[3] is True]
    c = [h for h in hits if h[1] == ".write()"]
    b = [h for h in hits if h[3] is not True and h[1] != ".write()"]
    if a:
        tier_a.append((rel, a))
    if b:
        tier_b.append((rel, b))
    if c:
        tier_c.append((rel, c))

print()
print("【A 级 —— 会写入 .py 源码】")
blocking = []
if tier_a:
    for rel, hits in tier_a:
        key = rel.replace("\\", "/")
        if key in ALLOWED:
            print(f"\n  [豁免] {rel}")
            print(f"         原因：{ALLOWED[key]}")
        else:
            print(f"\n  [阻断] {rel}")
            blocking.append(rel)
        for line, kind, target, _flag in hits:
            print(f"      第 {line} 行  {kind}  →  {target}")
else:
    print("  未发现")

print()
print("【B 级 —— 有写操作，但目标不是 .py 或无法静态解析（提示）】")
if tier_b:
    for rel, hits in tier_b:
        kinds = sorted({h[1] for h in hits})
        unresolved = sum(1 for h in hits if h[3] is None)
        extra = f"，其中 {unresolved} 处目标未解析（来自变量/参数）" if unresolved else ""
        print(f"  {rel}  （{', '.join(kinds)}）{extra}")
else:
    print("  无")

print()
print("【C 级 —— 文件对象 .write()（弱信号，需人工确认目标）】")
if tier_c:
    for rel, hits in tier_c:
        lines = ", ".join(str(h[0]) for h in hits[:8])
        print(f"  {rel}  第 {lines} 行")
else:
    print("  无")

print()
print(f"合计：扫描 {len(files)} 个 .py；A 级 {len(tier_a)} 个"
      f"（豁免 {len(tier_a) - len(blocking)}，阻断 {len(blocking)}），"
      f"B 级 {len(tier_b)} 个，C 级 {len(tier_c)} 个")
if blocking:
    print("阻断项：")
    for rel in blocking:
        print(f"  {rel}")
print("=" * 78)
sys.exit(1 if blocking else 0)
