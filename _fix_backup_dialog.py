# -*- coding: utf-8 -*-
"""
将备份进度改为弹窗+进度条形式
"""
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'rb') as f:
    lines = f.read().split(b'\n')

print(f"Total: {len(lines)}")

# Find _backup_data (3216) and _do_backup (3246) and _restore_backup (3262)
backup_start = 3215  # 0-indexed
do_backup_start = 3245
restore_start = 3261

# New _backup_data - creates a progress dialog
backup_data_new = '''    def _backup_data(self):
        try:
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = filedialog.asksaveasfilename(
                title="保存备份文件",
                defaultextension=".zip",
                initialfile="ExpiryManager_Backup_{}.zip".format(ts),
                filetypes=[("ZIP 压缩包", "*.zip")],
                parent=self,
            )
            if not path:
                return
            # Create progress dialog
            dlg = tk.Toplevel(self)
            dlg.title("备份中...")
            dlg.geometry("400x120")
            dlg.transient(self)
            dlg.grab_set()
            dlg.resizable(False, False)
            # Center dialog
            dlg.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - dlg.winfo_width()) // 2
            y = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
            dlg.geometry(f"+{x}+{y}")
            
            ttk.Label(dlg, text="正在备份数据，请稍候...").pack(pady=(15, 10))
            progress_var = tk.DoubleVar(value=0)
            progress_bar = ttk.Progressbar(dlg, variable=progress_var, maximum=100, length=350)
            progress_bar.pack(pady=5)
            status_var = tk.StringVar(value="准备中...")
            status_label = ttk.Label(dlg, textvariable=status_var)
            status_label.pack(pady=5)
            
            def run():
                try:
                    self._do_backup(Path(path), progress_var, status_var, dlg)
                except Exception as ex:
                    import traceback
                    err = str(ex) + "\\n" + traceback.format_exc()
                    self.after(0, lambda: messagebox.showerror("备份失败", err, parent=self))
                    self.after(0, dlg.destroy)
            threading.Thread(target=run, daemon=True).start()
        except Exception as ex:
            import traceback
            messagebox.showerror("备份错误", str(ex) + "\\n" + traceback.format_exc(), parent=self)

'''.encode('utf-8')

# New _do_backup - updates progress dialog
do_backup_new = '''    def _do_backup(self, zip_path, progress_var, status_var, dlg):
        all_files = [p for p in DATA_DIR.rglob("*") if p.is_file()]
        total = len(all_files)
        if total == 0:
            self.after(0, lambda: status_var.set("没有文件需要备份"))
            self.after(1000, dlg.destroy)
            self.after(1000, lambda: messagebox.showinfo("备份完成", "数据目录为空，无需备份", parent=self))
            return
        
        for i, p in enumerate(all_files, 1):
            with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
                zf.write(p, str(p.relative_to(DATA_DIR)))
            progress = (i / total) * 100
            self.after(0, lambda p=progress: progress_var.set(p))
            self.after(0, lambda s=f"已备份 {i}/{total} 个文件": status_var.set(s))
        
        self.after(0, lambda: status_var.set("备份完成！"))
        self.after(500, dlg.destroy)
        self.after(500, lambda: messagebox.showinfo("备份成功", f"已保存到:\\n{zip_path}\\n\\n共备份 {total} 个文件", parent=self))

'''.encode('utf-8')

# Build new file
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
