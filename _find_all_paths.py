# -*- coding: utf-8 -*-
"""扫描所有需要迁移的路径引用，输出每个文件中的位置。"""
import re, os, sys
from pathlib import Path

BASE = Path(r'F:\phpstudy_pro\WWW\ServerTimeDemo')

# 要扫描的源文件
FILES = [
    BASE / 'main.py',
    BASE / 'study_notes_window.py',
    BASE / 'study_notes_db.py',
    BASE / 'tools_page.py',
    BASE / 'adb_page.py',
    BASE / 'embedded_admin_tools' / 'crypto_window.py',
    BASE / 'embedded_admin_tools' / 'login_checker_window.py',
    BASE / 'embedded_admin_tools' / 'api_demo_window.py',
]

# 旧目录名（直接引用字符串）
OLD_DIRS = [
    'account_images',
    'study_notes_images',
    'study_notes_attachments',
    'process_flow_images',
    'Tools',
    'excel',
    'study_demo',
    'adb_history',
]

# 旧数据库文件名
OLD_FILES = [
    'expiry_manager.db',
    'study_demo.db',
    'remember_me.json',
    'login_memory.json',
]

for fpath in FILES:
    if not fpath.exists():
        print(f'SKIP: {fpath} not found')
        continue
    with open(fpath, 'rb') as f:
        data = f.read()
    found = []
    for d in OLD_DIRS:
        for m in re.finditer(re.escape(d.encode()), data):
            line = data[:m.start()].count(b'\n') + 1
            ctx = data[max(0,m.start()-20):m.start()+40].decode('utf-8', errors='replace')
            found.append((line, d, ctx))
    for d in OLD_FILES:
        for m in re.finditer(re.escape(d.encode()), data):
            line = data[:m.start()].count(b'\n') + 1
            ctx = data[max(0,m.start()-20):m.start()+40].decode('utf-8', errors='replace')
            found.append((line, d, ctx))
    if found:
        print(f'\n=== {fpath.name} ===')
        for line, token, ctx in sorted(found):
            try: print(f'  L{line}: {repr(ctx)}')
            except: pass
