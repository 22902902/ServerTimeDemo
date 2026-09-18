# -*- coding: utf-8 -*-
"""
修复 study_notes_window.py 的缩进错误，并把插入位置改为 def 前空行之后。
"""
FILE = r'F:\phpstudy_pro\WWW\ServerTimeDemo\study_notes_window.py'

# 1. 先把之前错误插入的 8 空格 def 行恢复成 4 空格
with open(FILE, 'rb') as f:
    data = f.read()

bad_line = b'        def _preview_markdown(self):'
good_line = b'    def _preview_markdown(self):'
if bad_line not in data:
    raise SystemExit('bad line not found (already fixed?)')
data = data.replace(bad_line, good_line, 1)
print('Fixed indentation of _preview_markdown.')

with open(FILE, 'wb') as f:
    f.write(data)

# 验证
try:
    import py_compile
    py_compile.compile(FILE, doraise=True)
    print('SYNTAX OK')
except py_compile.PyCompileError as e:
    print('Still has error:', e)