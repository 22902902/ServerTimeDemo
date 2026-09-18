import sqlite3, sys, os
sys.stdout.reconfigure(encoding='utf-8')
for root, dirs, files in os.walk(r'F:\phpstudy_pro\WWW\ServerTimeDemo'):
    for f in files:
        if f.endswith('.db'):
            path = os.path.join(root, f)
            size = os.path.getsize(path)
            c = sqlite3.connect(path)
            tables = sorted([r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
            has_tools = any(t.startswith('tool_') for t in tables)
            print(f"{path} ({size//1024}KB): tools={has_tools}, tables={tables}")
            c.close()
