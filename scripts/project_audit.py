# -*- coding: utf-8 -*-
"""项目静态审计脚本 — 只读分析，不修改任何被分析文件。

输出：函数长度、复杂度、异常处理、重复代码、魔法值、文档覆盖率等。
"""
import ast
import os
import re
import sys
import hashlib
from collections import defaultdict, Counter

EXCLUDE_DIRS = {'dist', 'build', '__pycache__', '.git', '.workbuddy',
                'node_modules', 'tmp_debug', 'scripts', 'venv', '.venv'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def iter_py():
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
        for f in sorted(files):
            if f.endswith('.py'):
                yield os.path.join(root, f)


def rel(p):
    return os.path.relpath(p, ROOT).replace('\\', '/')


def read(p):
    with open(p, encoding='utf-8', errors='replace') as fh:
        return fh.read()


# ---------- 1. 结构与函数指标 ----------
class FuncVisitor(ast.NodeVisitor):
    def __init__(self, src_lines):
        self.src = src_lines
        self.funcs = []          # (name, lineno, end, lines, branches, depth, kind)
        self.classes = []        # (name, lineno, end, lines, nmethods)
        self._class_stack = []

    def visit_ClassDef(self, node):
        end = getattr(node, 'end_lineno', node.lineno)
        methods = [n for n in node.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        bases = ','.join(ast.unparse(b) for b in node.bases) or '-'
        self.classes.append((node.name, node.lineno, end, end - node.lineno + 1,
                             len(methods), bases))
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node):
        self._handle_func(node)

    def visit_AsyncFunctionDef(self, node):
        self._handle_func(node)

    def _handle_func(self, node):
        end = getattr(node, 'end_lineno', node.lineno)
        branches = 0
        max_depth = 0

        class V(ast.NodeVisitor):
            def visit_If(self, n):
                nonlocal branches
                branches += 1
                self._d(n)
                self.generic_visit(n)
            visit_For = visit_While = visit_If

            def visit_Try(self, n):
                nonlocal branches
                branches += len(n.handlers)
                self._d(n)
                self.generic_visit(n)

            def visit_BoolOp(self, n):
                nonlocal branches
                branches += len(n.values) - 1
                self.generic_visit(n)

            def _d(self, n):
                nonlocal max_depth
                d = 0
                cur = n
                # 粗略用列缩进估算嵌套深度
                line = self_src[n.lineno - 1] if 0 < n.lineno <= len(self_src) else ''
                d = max(0, (len(line) - len(line.lstrip(' '))) // 4)
                max_depth = max(max_depth, d)

        self_src = self.src
        V().visit(node)
        kind = 'method' if self._class_stack else 'function'
        qual = f"{self._class_stack[-1]}.{node.name}" if self._class_stack else node.name
        self.funcs.append((qual, node.lineno, end, end - node.lineno + 1,
                           branches, max_depth, kind))
        self.generic_visit(node)


def analyze_structure():
    all_funcs, all_classes = [], []
    per_file = {}
    for p in iter_py():
        src = read(p)
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            print(f'  [语法错误] {rel(p)}: {e}')
            continue
        v = FuncVisitor(lines)
        v.visit(tree)
        all_funcs += [(rel(p),) + f for f in v.funcs]
        all_classes += [(rel(p),) + c for c in v.classes]
        per_file[rel(p)] = (len(lines), len(v.funcs), len(v.classes))
    return all_funcs, all_classes, per_file


# ---------- 2. 异常处理 ----------
def analyze_exceptions():
    pat_bare = re.compile(r'^\s*except\s*:')
    pat_exc = re.compile(r'^\s*except\s+Exception\b')
    pat_pass = re.compile(r'^\s*pass\s*$')
    res = defaultdict(lambda: {'bare': [], 'broad': [], 'swallow': []})
    for p in iter_py():
        lines = read(p).splitlines()
        for i, ln in enumerate(lines):
            if pat_bare.match(ln):
                res[rel(p)]['bare'].append(i + 1)
            elif pat_exc.match(ln):
                res[rel(p)]['broad'].append(i + 1)
                # 看下一非注释行是否 pass / return None
                for j in range(i + 1, min(i + 3, len(lines))):
                    s = lines[j].strip()
                    if not s or s.startswith('#'):
                        continue
                    if pat_pass.match(lines[j]) or s in ('return None', 'continue', 'return'):
                        res[rel(p)]['swallow'].append(i + 1)
                    break
    return res


# ---------- 3. 重复代码 ----------
def analyze_dup(min_lines=8):
    norm_map = defaultdict(list)
    for p in iter_py():
        lines = read(p).splitlines()
        norm = []
        for ln in lines:
            s = ln.strip()
            if not s or s.startswith('#'):
                norm.append('')
            else:
                norm.append(re.sub(r'\s+', ' ', s))
        for i in range(len(norm) - min_lines + 1):
            win = norm[i:i + min_lines]
            if sum(1 for w in win if w) < min_lines:
                continue
            key = hashlib.md5('\n'.join(win).encode()).hexdigest()
            norm_map[key].append((rel(p), i + 1, win[0][:60]))
    dups = {k: v for k, v in norm_map.items() if len(v) > 1}
    groups = []
    seen = set()
    for k, v in dups.items():
        sig = tuple(sorted({x[0] for x in v}))
        if sig in seen:
            continue
        seen.add(sig)
        groups.append(v)
    return sorted(groups, key=lambda g: -len(g))


# ---------- 4. 魔法值与风格 ----------
STYLE_RE = {
    'hardcoded_color': re.compile(r'#[0-9a-fA-F]{6}\b'),
    'mutable_default': re.compile(r'def\s+\w+\s*\([^)]*=\s*(\[\]|\{\})'),
    'star_import': re.compile(r'^\s*from\s+[\w.]+\s+import\s+\*'),
    'todo': re.compile(r'#\s*(TODO|FIXME|XXX|HACK|BUG)\b', re.I),
    'print_call': re.compile(r'(?<![\w.])print\s*\('),
    'eval_exec': re.compile(r'(?<![\w.])(eval|exec)\s*\('),
    'shell_true': re.compile(r'shell\s*=\s*True'),
    'global_stmt': re.compile(r'^\s*global\s+'),
    'type_ignore': re.compile(r'#\s*type:\s*ignore'),
    'chinese_ident': re.compile(r'\bdef\s+[\u4e00-\u9fff]'),
}


def analyze_style():
    res = defaultdict(lambda: defaultdict(int))
    samples = defaultdict(lambda: defaultdict(list))
    for p in iter_py():
        lines = read(p).splitlines()
        for i, ln in enumerate(lines):
            for name, rx in STYLE_RE.items():
                if rx.search(ln):
                    res[rel(p)][name] += 1
                    if len(samples[rel(p)][name]) < 3:
                        samples[rel(p)][name].append((i + 1, ln.strip()[:90]))
        # 长行
        longl = [i + 1 for i, ln in enumerate(lines) if len(ln) > 120]
        res[rel(p)]['line>120'] = len(longl)
    return res, samples


# ---------- 5. 文档覆盖率 ----------
def analyze_docs():
    res = {}
    for p in iter_py():
        src = read(p)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        total = 0
        documented = 0
        undoc = []
        if ast.get_docstring(tree):
            documented += 1
        total += 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                total += 1
                if ast.get_docstring(node):
                    documented += 1
                elif node.col_offset == 0 and isinstance(node, ast.ClassDef):
                    undoc.append((node.lineno, node.name))
        res[rel(p)] = (total, documented, undoc)
    return res


# ---------- 6. 导入与依赖 ----------
def analyze_imports():
    per_file = {}
    third = Counter()
    stdlib = set(sys.stdlib_module_names)
    for p in iter_py():
        src = read(p)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split('.')[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    mods.append(node.module.split('.')[0])
        per_file[rel(p)] = mods
        for m in mods:
            if m not in stdlib and m not in ('embedded_admin_tools',) and not m.startswith('_'):
                third[m] += 1
    return per_file, third


def main():
    out = []
    P = out.append

    funcs, classes, per_file = analyze_structure()
    exc = analyze_exceptions()
    dups = analyze_dup()
    style, samples = analyze_style()
    docs = analyze_docs()
    imports, third = analyze_imports()

    P('=' * 78)
    P('1. 超长函数 / 方法  (行数 >= 80)')
    P('=' * 78)
    for f in sorted(funcs, key=lambda x: -x[4])[:35]:
        if f[4] < 80:
            break
        P(f'{f[4]:>5} 行 | 分支~{f[5]:<3} | 嵌套~{f[6]} | {f[0]}:{f[2]}  {f[1]}')

    P('')
    P('=' * 78)
    P('2. 上帝类  (方法数 >= 15 或行数 >= 400)')
    P('=' * 78)
    for c in sorted(classes, key=lambda x: -x[4]):
        if c[5] < 15 and c[4] < 400:
            continue
        P(f'{c[4]:>5} 行 | {c[5]:>3} 方法 | 基类 {c[6]} | {c[0]}:{c[2]}  class {c[1]}')

    P('')
    P('=' * 78)
    P('3. 异常处理')
    P('=' * 78)
    for f, d in sorted(exc.items(), key=lambda x: -(len(x[1]['bare']) + len(x[1]['broad']))):
        if not d['bare'] and not d['broad']:
            continue
        P(f'{f}:  裸except={len(d["bare"])} {d["bare"][:6]}   '
          f'exceptException={len(d["broad"])}  疑似静默吞异常={len(d["swallow"])} {d["swallow"][:6]}')

    P('')
    P('=' * 78)
    P('4. 重复代码块  (连续 8 行归一化后完全一致)')
    P('=' * 78)
    shown = 0
    for g in dups:
        if shown >= 20:
            break
        files = {x[0] for x in g}
        P(f'--- 重复 x{len(g)}  (跨 {len(files)} 文件)  首行样例: {g[0][2]}')
        for f, ln, _ in g[:6]:
            P(f'      {f}:{ln}')
        shown += 1
    P(f'  (重复组总数: {len(dups)})')

    P('')
    P('=' * 78)
    P('5. 风格 / 坏味道统计  (按严重度排序)')
    P('=' * 78)
    keys = ['bare_exc', 'hardcoded_color', 'line>120', 'print_call', 'global_stmt',
            'star_import', 'mutable_default', 'eval_exec', 'shell_true', 'todo', 'type_ignore']
    rows = []
    for f, d in style.items():
        score = (d.get('hardcoded_color', 0) * 1 + d.get('print_call', 0) * 2 +
                 d.get('line>120', 0) + d.get('global_stmt', 0) * 3 +
                 d.get('star_import', 0) * 5 + d.get('eval_exec', 0) * 8 +
                 d.get('shell_true', 0) * 5 + d.get('mutable_default', 0) * 4)
        rows.append((score, f, d))
    for score, f, d in sorted(rows, reverse=True)[:22]:
        parts = ', '.join(f'{k}={d[k]}' for k in keys if d.get(k))
        P(f'{score:>6} 分 | {f}')
        P(f'         {parts}')

    P('')
    P('=' * 78)
    P('6. 示例片段')
    P('=' * 78)
    for f in list(samples)[:60]:
        for k, v in samples[f].items():
            if k in ('eval_exec', 'shell_true', 'star_import', 'mutable_default', 'global_stmt', 'todo'):
                for ln, txt in v:
                    P(f'[{k}] {f}:{ln}')
                    P(f'        {txt}')

    P('')
    P('=' * 78)
    P('7. 文档覆盖率  (模块+类+函数 有 docstring 的比例)')
    P('=' * 78)
    for f, (t, d, undoc) in sorted(docs.items(), key=lambda x: (x[1][1] / max(x[1][0], 1))):
        if t < 5:
            continue
        pct = 100 * d / t
        if pct < 40:
            P(f'{pct:>5.0f}%  ({d}/{t})  {f}   无文档类: {[u[1] for u in undoc][:8]}')

    P('')
    P('=' * 78)
    P('8. 第三方依赖 (被 import 的次数)')
    P('=' * 78)
    for m, c in third.most_common():
        P(f'  {m:<22} {c}')

    txt = '\n'.join(out)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_audit_out.txt'),
              'w', encoding='utf-8') as fh:
        fh.write(txt)
    print(txt)


if __name__ == '__main__':
    main()
