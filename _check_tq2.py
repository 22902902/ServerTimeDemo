# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\console_page.py', 'rb') as f:
    raw = f.read()

# Find the _ps_safe docstring region
for m in re.finditer(b'"""', raw):
    line = raw[:m.start()].count(b'\n') + 1
    ctx = raw[max(0,m.start()-5):m.start()+30]
    if 319 <= line <= 327:
        print(f'L{line} pos {m.start()}: {ctx!r}')
