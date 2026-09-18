# -*- coding: utf-8 -*-
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'rb') as f:
    lines = f.read().split(b'\n')

print(f"Total: {len(lines)}")

# Find _backup_data (line 3216) and _do_backup (line 3236)
# Replace both with improved versions

backup_data_new = '''    def _backup_data(self):
        try:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = filedialog.asksaveasfilename(
                title="保存备份文件",
                defaultextension=".zip",
                initialfile="ExpiryManager_Backup_{}.zip".format(ts),
                filetypes=[("ZIP 压缩包", "*.zip")],
                parent=self,
            )
            if not path:
                return
            sv = tk.StringVar(value="⏳ 正在备份 ...")
            lbl = ttk.Label(self, textvariable=sv, foreground="#888")
            lbl.place(relx=0.5, rely=0.98, anchor="s")
            def run():
                try:
                    self._do_backup(Path(path), sv)
                except Exception as ex:
                    import traceback
                    err = str(ex) + "\\n" + traceback.format_exc()
                    self.after(0, lambda: messagebox.showerror("备份失败", err, parent=self))
                finally:
                    self.after(0, lbl.destroy)
            threading.Thread(target=run, daemon=True).start()
        except Exception as ex:
            import traceback
            messagebox.showerror("备份错误", str(ex) + "\\n" + traceback.format_exc(), parent=self)

'''.encode('utf-8')

do_backup_new = '''    def _do_backup(self, zip_path, sv):
        all_files = [p for p in DATA_DIR.rglob("*") if p.is_file()]
        total = len(all_files)
        done = [0]
        def upd(n):
            sv.set("• 备份中 ... {}/{}".format(n, total))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in all_files:
                zf.write(p, str(p.relative_to(DATA_DIR)))
                done[0] += 1
                if done[0] % 20 == 0:
                    self.after(0, lambda n=done[0]: upd(n))
        self.after(0, lambda: sv.set("✓ 备份完成: " + zip_path.name))
        self.after(0, lambda: messagebox.showinfo("备份成功", "已保存到:\\n" + str(zip_path), parent=self))

'''.encode('utf-8')

# Find indices
backup_start = None
do_backup_start = None
restore_start = None
for i, line in enumerate(lines):
    if b'def _backup_data(self):' in line and i > 3000:
        backup_start = i
    if b'def _do_backup(self, zip_path' in line and i > 3000:
        do_backup_start = i
    if b'def _restore_backup(self):' in line and i > 3000:
        restore_start = i

print(f"backup_start: {backup_start+1}, do_backup_start: {do_backup_start+1}, restore_start: {restore_start+1}")

# Build new file: lines[0:backup_start] + backup_data_new + do_backup_new + lines[restore_start:]
new_lines = lines[:backup_start]
new_lines.append(backup_data_new)
new_lines.append(do_backup_new)
new_lines.extend(lines[restore_start:])

print(f"New total: {len(new_lines)}")

with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'wb') as f:
    f.write(b'\n'.join(new_lines))

import py_compile
try:
    py_compile.compile(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', doraise=True)
    print("\nSYNTAX OK!")
except py_compile.PyCompileError as e:
    print("\nSYNTAX ERROR:", e)
