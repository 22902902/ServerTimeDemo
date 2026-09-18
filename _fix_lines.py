# -*- coding: utf-8 -*-
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'rb') as f:
    lines = f.read().split(b'\n')

print(f'Total: {len(lines)}')

# Fix truncated lines using hex escapes for non-ASCII
# Line 3237 (index 3236) - messagebox.showerror for backup failure
print('3237 Before:', repr(lines[3236][:100]))
lines[3236] = b'                    self.after(0, lambda: messagebox.showerror("\xe5\xa4\x87\xe4\xbb\xbd\xe5\xa4\xb1\xe8\xb4\xa5", err, parent=self))'
print('3237 After:', repr(lines[3236]))

# Line 3243 (index 3242) - messagebox.showerror for backup error
print('3243 Before:', repr(lines[3242][:100]))
lines[3242] = b'            messagebox.showerror("\xe5\xa4\x87\xe4\xbb\xbd\xe9\x94\x99\xe8\xaf\xaf", str(ex) + "\\n" + traceback.format_exc(), parent=self)'
print('3243 After:', repr(lines[3242]))

# Line 3259 (index 3258) - messagebox.showinfo for backup success
print('3259 Before:', repr(lines[3258][:100]))
lines[3258] = b'        self.after(0, lambda: messagebox.showinfo("\xe5\xa4\x87\xe4\xbb\xbd\xe6\x88\x90\xe5\x8a\x9f", "\xe5\xb7\xb2\xe4\xbf\x9d\xe5\xad\x98\xe5\x88\xb0:\\n" + str(zip_path), parent=self))'
print('3259 After:', repr(lines[3258]))

with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'wb') as f:
    f.write(b'\n'.join(lines))

import py_compile
try:
    py_compile.compile(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', doraise=True)
    print('\nSYNTAX OK!')
except py_compile.PyCompileError as e:
    print('\nSYNTAX ERROR:', e)
