import ast, os, sys

FILES = [
    r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py',
    r'F:\phpstudy_pro\WWW\ServerTimeDemo\baidu_disk_window.py',
    r'F:\phpstudy_pro\WWW\ServerTimeDemo\study_notes_db.py',
    r'F:\phpstudy_pro\WWW\ServerTimeDemo\study_notes_window.py',
    r'F:\phpstudy_pro\WWW\ServerTimeDemo\qa_work_log_db.py',
    r'F:\phpstudy_pro\WWW\ServerTimeDemo\qa_work_log_page.py',
    r'F:\phpstudy_pro\WWW\ServerTimeDemo\system_toolbox_page.py',
]

for fp in FILES:
    with open(fp, 'r', encoding='utf-8') as f:
        src = f.read()
    tree = ast.parse(src)
    loc = len(src.splitlines())
    
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    funcs_top = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    
    # count methods
    methods = []
    for c in classes:
        for n in c.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append((c.name, n.name, n.lineno, n.end_lineno))
    
    # function/method length
    def length(n):
        return (n.end_lineno or n.lineno) - n.lineno + 1
    
    all_funcs = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_funcs.append((n.name, length(n), n.lineno))
    all_funcs.sort(key=lambda x: -x[1])
    
    print(f"\n=== {os.path.basename(fp)} ===")
    print(f"  LOC: {loc}")
    print(f"  Classes: {len(classes)}  Top-level funcs: {len(funcs_top)}  Methods: {len(methods)}")
    print(f"  Longest functions/methods (top 10):")
    for name, ln, lno in all_funcs[:10]:
        print(f"    {ln:4d} lines  L{lno:5d}  {name}")
    
    # bare excepts
    bare = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None)
    broad = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler) and n.type:
            # check for "Exception" or broad
            t = ast.unparse(n.type)
            if t in ('Exception', 'BaseException'):
                broad += 1
    print(f"  Bare except: {bare}  Broad (Exception): {broad}")
