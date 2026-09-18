# -*- coding: utf-8 -*-
"""去掉 emoji 字符，避免打包后字体兼容问题。"""
FILE = r'F:\phpstudy_pro\WWW\ServerTimeDemo\study_notes_window.py'

with open(FILE, 'rb') as f:
    data = f.read()

# 1) 按钮文字 "👁 显示效果" -> "显示效果"
old1 = '👁 显示效果'.encode('utf-8')
new1 = '显示效果'.encode('utf-8')
n1 = data.count(old1)
data = data.replace(old1, new1)
print(f'Replaced {n1} occurrences of emoji + display text')

# 2) _toggle_preview 里的 emoji 引用（用占位符实现：emoji 是 \U0001f441）
# 已通过上面替换完成，无需再次处理

with open(FILE, 'wb') as f:
    f.write(data)

# 验证
import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print('SYNTAX OK')
except py_compile.PyCompileError as e:
    print('Error:', e)