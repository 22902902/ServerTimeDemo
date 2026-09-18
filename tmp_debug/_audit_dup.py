"""查重审计"""
import sqlite3

conn = sqlite3.connect(r'F:\phpstudy_pro\WWW\ServerTimeDemo\dist\expiry_manager.db')
conn.row_factory = sqlite3.Row

print('=== tool_items (全部) ===')
for r in conn.execute('SELECT id, name, path, category, is_deleted, icon_path FROM tool_items ORDER BY is_deleted, id').fetchall():
    icon = '+' if r['icon_path'] else '-'
    delt = 'D' if r['is_deleted'] else ' '
    print(f'  [{delt}]{icon} id={r["id"]:2} name={r["name"]:10} cat={r["category"]:8} path={r["path"]}')

print()
print('=== 重复 path (is_deleted=0) ===')
rows = conn.execute('SELECT path, COUNT(*) c FROM tool_items WHERE is_deleted=0 GROUP BY path HAVING c > 1').fetchall()
for r in rows:
    print(f'  REPEAT: path={r["path"]} c={r["c"]}')

print()
print('=== 同名工具 (is_deleted=0, 名字相同但 path 不同) ===')
prev = None
for r in conn.execute('SELECT id, name, path, category FROM tool_items WHERE is_deleted=0 ORDER BY LOWER(name)').fetchall():
    if prev and prev['name'].lower() == r['name'].lower():
        print(f'  SAME NAME: id={prev["id"]} {prev["name"]} ({prev["path"]}) [{prev["category"]}]')
        print(f'              id={r["id"]} {r["name"]} ({r["path"]}) [{r["category"]}]')
    prev = r

print()
print('=== 软删除项目（可能被旧版 DB 残留）===')
for r in conn.execute('SELECT id, name, path, is_deleted FROM tool_items WHERE is_deleted=1').fetchall():
    print(f'  D id={r["id"]} name={r["name"]} path={r["path"]}')

conn.close()
