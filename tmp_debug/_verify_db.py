import sqlite3, sys, os
sys.stdout.reconfigure(encoding='utf-8')

for label, path in [
    ("dist\expiry_manager.db", r'F:\phpstudy_pro\WWW\ServerTimeDemo\dist\expiry_manager.db'),
    ("ROOT\expiry_manager.db", r'F:\phpstudy_pro\WWW\ServerTimeDemo\expiry_manager.db'),
    ("TEMP backup", os.path.join(os.environ.get('TEMP', ''), 'ExpiryManager_dist_backup.db')),
    ("Backup2", r'F:\phpstudy_pro\WWW\ServerTimeDemo (2)\dist\expiry_manager.db'),
]:
    print(f"\n=== {label} ===")
    print(f"  Size: {os.path.getsize(path) if os.path.exists(path) else 'NOT FOUND'} bytes")
    if not os.path.exists(path):
        continue
    c = sqlite3.connect(path)
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"  Tables: {tables}")
    for t in ['assets','tool_items','tool_categories','tool_packages','tool_settings']:
        if t in tables:
            n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n}")
    c.close()
