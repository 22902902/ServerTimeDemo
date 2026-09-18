# -*- coding: utf-8 -*-
"""名字与作用域检查 —— 只读分析，不修改任何被检查文件。

补 pyflakes 覆盖面之外的两类问题，两者都基于「真实执行」而非模式匹配：

  检查 1  except 异常类型表达式求值
          把每个 `except` 的类型表达式抽出来，在只装了「标准库 + 第三方库导入」
          的命名空间里真实 eval。原故障形态就是类型表达式求值时才抛
          NameError / AttributeError（例如 `except PIL.UnidentifiedImageError`
          而 PIL 这个模块名从未绑定），静态扫描容易漏。

  检查 2  闭包作用域（UnboundLocalError 成因）
          找出「在闭包里被读、之后才赋值、又未声明 nonlocal、且外层函数存在
          同名绑定」的局部变量。名字一旦被赋值就成为函数局部变量，先前的读取
          会命中尚未绑定的局部槽位，抛 UnboundLocalError。

用法：
    python scripts/check_name_scope.py                # 检查本文件所在项目
    python scripts/check_name_scope.py <目录>          # 检查指定目录

退出码：0 = 全部通过，1 = 有命中（可直接用于 CI / 提交前检查）。

已知局限：检查 2 用「行号先后」近似控制流，跨分支/循环的先读后写可能漏报或
误报；它定位的是典型成因，不替代测试。
"""
import ast
import os
import sys

EXCLUDE_DIRS = {"dist", "build", "__pycache__", ".git", ".workbuddy", "node_modules",
                "venv", ".venv", "Tools", "_icons", "tmp_debug", "scripts"}

# 项目内模块：不加载，相关名字出现时报 SKIP 而不是 FAIL
PROJECT_MODULES = {
    "tools_db", "ui_theme", "dialog_form_style", "page_components", "ui_components",
    "adb_page", "console_page", "expiry_dialogs", "tools_page", "main",
    "embedded_admin_tools", "log_setup", "study_demo_db", "study_notes_db",
    "qa_work_log_db", "qa_extras", "account_windows", "backend_page", "process_page",
}


# ---------------------------------------------------------------------------
# 检查 1：except 类型表达式真实求值
# ---------------------------------------------------------------------------
def build_namespace(tree):
    """执行 Import / ImportFrom（跳过项目内模块），返回 (命名空间, 已跳过名字)。"""
    ns, skipped = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                stmt = f"import {a.name}" + (f" as {a.asname}" if a.asname else "")
                try:
                    exec(stmt, ns)
                except Exception:
                    skipped.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module in PROJECT_MODULES:
                skipped.update(a.asname or a.name for a in node.names)
                continue
            for a in node.names:
                if a.name == "*":
                    continue
                stmt = (f"from {node.module} import {a.name}"
                        + (f" as {a.asname}" if a.asname else ""))
                try:
                    exec(stmt, ns)
                except Exception:
                    skipped.add(a.asname or a.name)
    return ns, skipped


def check_except_clauses(path):
    src = open(path, encoding="utf-8-sig", errors="replace").read()
    tree = ast.parse(src)
    ns, skipped = build_namespace(tree)
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        expr = ast.unparse(node.type)
        try:
            value = eval(expr, ns)
            items = value if isinstance(value, tuple) else (value,)
            bad = [repr(i) for i in items
                   if not (isinstance(i, type) and issubclass(i, BaseException))]
            if bad:
                results.append((node.lineno, expr, "FAIL", f"不是异常类型：{', '.join(bad)}"))
            else:
                results.append((node.lineno, expr, "OK", ""))
        except NameError as exc:
            missing = str(exc).split("'")[1] if "'" in str(exc) else "?"
            status = "SKIP" if missing in skipped else "FAIL"
            results.append((node.lineno, expr, status, f"{missing} 未绑定"))
        except AttributeError as exc:
            results.append((node.lineno, expr, "FAIL", f"属性不存在：{exc}"))
        except Exception as exc:
            results.append((node.lineno, expr, "FAIL", f"{type(exc).__name__}: {exc}"))
    return results


# ---------------------------------------------------------------------------
# 检查 2：闭包作用域
# ---------------------------------------------------------------------------
def own_scope_names(func):
    """收集函数自身作用域的名字（不进入嵌套函数 / lambda / 推导式）。"""
    stores, loads = {}, {}

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                continue
            if isinstance(child, ast.Name):
                if isinstance(child.ctx, ast.Store):
                    stores.setdefault(child.id, child.lineno)
                elif isinstance(child.ctx, ast.Load):
                    loads.setdefault(child.id, child.lineno)
            visit(child)

    visit(func)
    declared = set()
    for child in func.body:
        if isinstance(child, (ast.Nonlocal, ast.Global)):
            declared.update(child.names)
    params = {a.arg for a in list(func.args.args) + list(func.args.kwonlyargs)
              + list(func.args.posonlyargs)}
    if func.args.vararg:
        params.add(func.args.vararg.arg)
    if func.args.kwarg:
        params.add(func.args.kwarg.arg)
    for name in list(params) + list(declared):
        stores.pop(name, None)   # 参数与 nonlocal/global 名字都不由本函数绑定
    return stores, loads, declared


def collect_functions(tree):
    """返回 (函数节点, 其外层函数节点列表) 的扁平列表。"""
    out = []

    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((child, list(stack)))
                walk(child, stack + [child])
            else:
                walk(child, stack)

    walk(tree, [])
    return out


def check_closure_scope(path):
    src = open(path, encoding="utf-8-sig", errors="replace").read()
    tree = ast.parse(src)
    funcs = collect_functions(tree)
    own = {id(f): own_scope_names(f)[0] for f, _ in funcs}
    findings = []
    for func, stack in funcs:
        stores, loads, declared = own_scope_names(func)
        for name, store_line in stores.items():
            if name in declared:
                continue
            load_line = loads.get(name)
            if load_line is None or load_line > store_line:
                continue
            outer = [f for f in stack if name in own.get(id(f), {})]
            if not outer:
                continue
            findings.append((func.name, name, load_line, store_line,
                             outer[-1].name, outer[-1].lineno))
    return findings


# ---------------------------------------------------------------------------
def iter_python_files(root):
    files = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        files += [os.path.join(dirpath, f) for f in names if f.endswith(".py")]
    return sorted(files)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = iter_python_files(root)
    fails = []

    print("=" * 78)
    print(f"检查 1 —— except 异常类型表达式真实求值（{len(files)} 个 .py）")
    print("=" * 78)
    total = skips = 0
    for path in files:
        rel = os.path.relpath(path, root)
        try:
            for lineno, expr, status, detail in check_except_clauses(path):
                total += 1
                if status == "FAIL":
                    fails.append(f"{rel}:{lineno}  {expr}  -> {detail}")
                elif status == "SKIP":
                    skips += 1
        except SyntaxError as exc:
            fails.append(f"{rel}:{exc.lineno}  语法错误 -> {exc}")
    print(f"  求值 {total} 个表达式，SKIP {skips} 个（引用了项目内模块）")
    print("  ok    全部可求值，无 NameError / AttributeError" if not fails
          else f"  FAIL  {len(fails)} 个问题（见下）")

    print()
    print("=" * 78)
    print("检查 2 —— 闭包作用域（UnboundLocalError 成因）")
    print("=" * 78)
    scope_fails = []
    for path in files:
        rel = os.path.relpath(path, root)
        try:
            for fname, name, ll, sl, outer, dl in check_closure_scope(path):
                scope_fails.append(
                    f"{rel}:{ll}  {fname}() 第 {ll} 行读 `{name}`、第 {sl} 行才赋值，"
                    f"未声明 nonlocal（外层绑定：{outer}() 第 {dl} 行）")
        except SyntaxError:
            pass
    print("  ok    未发现「先读后写且遮蔽外层变量」的闭包" if not scope_fails
          else f"  FAIL  {len(scope_fails)} 个命中（见下）")

    all_fails = fails + scope_fails
    if all_fails:
        print()
        print("=" * 78)
        print("问题明细")
        print("=" * 78)
        for line in all_fails:
            print(f"  {line}")

    print()
    print("=" * 78)
    print(f"总计 FAIL = {len(all_fails)}")
    print("=" * 78)
    return 1 if all_fails else 0


if __name__ == "__main__":
    sys.exit(main())
