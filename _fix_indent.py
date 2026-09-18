# -*- coding: utf-8 -*-
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'rb') as f:
    lines = f.read().split(b'\n')

print(f"Total: {len(lines)}")

# Find _migrate_data_dir() and ensure_data_dir() calls
migrate_calls = []
ensure_calls = []
for i, line in enumerate(lines):
    if b'_migrate_data_dir()' in line and b'def ' not in line:
        migrate_calls.append(i)
    if b'ensure_data_dir()' in line and b'def ' not in line:
        ensure_calls.append(i)

print(f"_migrate_data_dir() calls at: {[i+1 for i in migrate_calls]}")
print(f"ensure_data_dir() calls at: {[i+1 for i in ensure_calls]}")

# Keep first of each, remove duplicates
remove_idx = set(migrate_calls[1:] + ensure_calls[1:])
print(f"Removing: {[i+1 for i in remove_idx]}")

new_lines = [line for i, line in enumerate(lines) if i not in remove_idx]
print(f"New total: {len(new_lines)}")

with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'wb') as f:
    f.write(b'\n'.join(new_lines))

import py_compile
try:
    py_compile.compile(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', doraise=True)
    print("\nSYNTAX OK!")
except py_compile.PyCompileError as e:
    print("\nSYNTAX ERROR:", e)
