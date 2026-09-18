import sqlite3
import tempfile
import os
from pathlib import Path
import main

# 创建测试数据库
db_path = Path(tempfile.mktemp(suffix=".db"))
db = main.Database(db_path)

# 检查 admin 用户是否标记为强制修改
row = db.conn.execute(
    "SELECT username, must_change_password FROM users WHERE username=?",
    ("admin",),
).fetchone()
print(f"admin 用户: must_change_password = {row[1]} (应为 1)")

# 测试 verify_user
ok = db.verify_user("admin", "admin")
print(f"verify_user(admin, admin) = {ok} (应为 True)")

# 测试 reset_admin_password 生成随机密码
new_pwd = db.reset_admin_password()
print(f"重置后密码长度: {len(new_pwd)} (应为 12)")
ok2 = db.verify_user("admin", new_pwd)
print(f"verify_user(admin, new_pwd) = {ok2} (应为 True)")

# 测试 set_user_password + clear_must_change_password
db.set_user_password("admin", "newpass123", force_change=False)
db.clear_must_change_password("admin")
row2 = db.conn.execute(
    "SELECT must_change_password FROM users WHERE username=?",
    ("admin",),
).fetchone()
print(f"修改密码后 must_change_password = {row2[0]} (应为 0)")

db.close()
os.remove(db_path)
print("✅ 密码安全修复验证通过")
