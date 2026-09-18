# -*- coding: utf-8 -*-
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'rb') as f:
    data = f.read()

# Fix _dt.now() -> _dt.datetime.now()
old = b'_dt.now().strftime'
new = b'_dt.datetime.now().strftime'

if old in data:
    data = data.replace(old, new)
    print(f'Replaced: {old} -> {new}')
else:
    print(f'Not found: {old}')

with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'wb') as f:
    f.write(data)

import py_compile
try:
    py_compile.compile(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', doraise=True)
    print('SYNTAX OK!')
except py_compile.PyCompileError as e:
    print('SYNTAX ERROR:', e)
