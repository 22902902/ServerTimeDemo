# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\console_page.py', 'rb') as f:
    raw = f.read()
for m in re.finditer(b'"""', raw):
    line = raw[:m.start()].count(b'\n') + 1
    col = m.start() - raw.rfind(b'\n', 0, m.start())
    ctx = raw[max(0,m.start()-15):m.start()+20]
    print(f'pos {m.start()} L{line}: {ctx!r}')
