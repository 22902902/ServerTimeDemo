# -*- coding: utf-8 -*-
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'rb') as f:
    data = f.read()

# Fix datetime.datetime.now() -> _dt.now()
# The import is: import zipfile, threading, datetime as _dt
old = b'datetime.datetime.now().strftime'
new = b'_dt.now().strftime'

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
