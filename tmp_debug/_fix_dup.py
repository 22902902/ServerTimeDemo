"""清理 tool_items 重复项
策略：同一真实文件只保留 1 条，优先保留有图标的。
被删的工具如果 path 还有效（文件存在），就保留 id 最大的"最新版本"。
"""
import sqlite3
import os
from pathlib import Path

conn = sqlite3.connect(r'F:\phpstudy_pro\WWW\ServerTimeDemo\dist\expiry_manager.db')
conn.row_factory = sqlite3.Row

def norm_path(p: str, tools_dir: str = r'F:\phpstudy_pro\WWW\ServerTimeDemo\dist\Tools') -> str:
    """归一化路径：相对路径转绝对，然后 resolve"""
    if not p:
        return ""
    p = p.strip()
    if os.path.isabs(p):
        return os.path.normcase(os.path.abspath(p))
    # 相对路径：相对于 tools_dir
    full = os.path.join(tools_dir, p.replace("/", os.sep))
    return os.path.normcase(os.path.abspath(full))

rows = conn.execute("SELECT * FROM tool_items WHERE is_deleted=0 ORDER BY id").fetchall()
groups: dict[str, list] = {}
for r in rows:
    n = norm_path(r['path'])
    if not n:
        continue
    groups.setdefault(n, []).append(dict(r))

to_delete = []
for n, items in groups.items():
    if len(items) > 1:
        # 优先保留：有图标的 > 有描述的 > 收藏的 > id 最大的
        items.sort(key=lambda x: (
            not bool(x.get('icon_path')),  # 有图标排前
            not bool(x.get('description')),
            not bool(x.get('is_favorite')),
            -x['id'],  # id 大的排前
        ))
        keep = items[0]
        for it in items[1:]:
            to_delete.append((it['id'], it['name'], it['path']))

print(f"发现 {len(to_delete)} 条重复待删除：")
for tid, n, p in to_delete:
    print(f"  id={tid} name={n} path={p}")

if to_delete:
    # 用软删除保留记录
    for tid, n, p in to_delete:
        conn.execute("UPDATE tool_items SET is_deleted=1 WHERE id=?", (tid,))
    conn.commit()
    print(f"\n已软删除 {len(to_delete)} 条重复。")

# 验证
print("\n=== 清理后状态 ===")
rows = conn.execute("SELECT id, name, path, icon_path FROM tool_items WHERE is_deleted=0 ORDER BY id").fetchall()
for r in rows:
    icon = '+' if r['icon_path'] else '-'
    print(f"  {icon} id={r['id']:2} name={r['name']:10} path={r['path']}")

conn.close()
print("\n[OK] DB 清理完成")
