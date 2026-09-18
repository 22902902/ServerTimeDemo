# -*- coding: utf-8 -*-
"""
修复子进程输出捕获问题 - 改用 communicate() 更可靠
"""
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\study_demo_window.py', 'rb') as f:
    lines = f.read().split(b'\n')

print(f"Total: {len(lines)}")

# Find _wait_proc and replace it
wait_proc_start = None
for i, line in enumerate(lines):
    if b'def _wait_proc(self, proc, timeout=30):' in line:
        wait_proc_start = i
        print(f"Found _wait_proc at line {i+1}")
        break

if wait_proc_start is None:
    print("ERROR: _wait_proc not found")
    exit(1)

# Find where _wait_proc ends (next method at same indent level)
wait_proc_end = None
for i in range(wait_proc_start + 1, len(lines)):
    line = lines[i]
    stripped = line.lstrip()
    if stripped and not stripped.startswith(b'#') and not stripped.startswith(b'"""'):
        # Check if it's a method definition at class level (4 spaces indent)
        indent = len(line) - len(stripped)
        if indent <= 4 and stripped.startswith(b'def '):
            wait_proc_end = i
            print(f"_wait_proc ends at line {i+1}")
            break

if wait_proc_end is None:
    wait_proc_end = len(lines)

# New _wait_proc implementation using communicate()
new_wait_proc = '''    def _wait_proc(self, proc, timeout=30):
        """使用 communicate() 捕获输出，更可靠"""
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            if stdout:
                self._append_output(stdout, "stdout")
            if stderr:
                self._append_output(stderr, "stderr")
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            if stdout:
                self._append_output(stdout, "stdout")
            if stderr:
                self._append_output(stderr, "stderr")
            self._append_output(f"\\n[超时] 已终止（>{timeout}秒）\\n", "error")
            return

        rc = proc.returncode
        if rc == 0:
            self._append_output(f"\\n[完成] 退出码 0\\n", "ok")
        else:
            self._append_output(f"\\n[失败] 退出码 {rc}\\n", "error")

'''.encode('utf-8')

# Build new file
new_lines = lines[:wait_proc_start]
new_lines.append(new_wait_proc)
new_lines.extend(lines[wait_proc_end:])

print(f"New total: {len(new_lines)}")

with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\study_demo_window.py', 'wb') as f:
    f.write(b'\n'.join(new_lines))

import py_compile
try:
    py_compile.compile(r'F:\phpstudy_pro\WWW\ServerTimeDemo\study_demo_window.py', doraise=True)
    print("\nSYNTAX OK!")
except py_compile.PyCompileError as e:
    print("\nSYNTAX ERROR:", e)
