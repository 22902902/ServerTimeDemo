# -*- coding: utf-8 -*-
import sqlite3, os

db = r'F:\phpstudy_pro\WWW\ServerTimeDemo\expiry_manager.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in cur.fetchall():
    print(row[0])

conn.close()
