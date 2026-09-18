# -*- coding: utf-8 -*-
"""修改 main.py: DATA_DIR、迁移、备份/恢复按钮和方法。"""
import py_compile
from pathlib import Path

BASE = Path(r'F:\phpstudy_pro\WWW\ServerTimeDemo')
MAIN = BASE / 'main.py'

with open(MAIN, 'rb') as f:
    data = f.read()

# A: BASE_DIR 后插入 DATA_DIR + import
old1 = b'BASE_DIR = get_base_dir()\r\n'
new1 = b'BASE_DIR = get_base_dir()\r\nDATA_DIR = BASE_DIR / "ExpiryManager_Data"\r\nfrom _migrate_data_dir import _migrate_data_dir, ensure_data_dir\r\n'
assert old1 in data, 'A: BASE_DIR not found'
data = data.replace(old1, new1, 1)
print("A: OK")

# B: Database() 前插入迁移调用
old2 = b'        self.db = Database(DB_PATH)\r\n'
new2 = b'        _migrate_data_dir()\r\n        ensure_data_dir()\r\n        self.db = Database(DB_PATH)\r\n'
assert old2 in data, 'B: Database not found'
data = data.replace(old2, new2, 1)
print("B: OK")

# C: study_demo_db_conn 前
old3 = b'self.study_demo_db_conn = get_study_demo_conn()'
new3 = b'ensure_data_dir()\r\n        self.study_demo_db_conn = get_study_demo_conn()'
assert old3 in data, 'C: study_demo not found'
data = data.replace(old3, new3, 1)
print("C: OK")

# D: 顶部插入 zipfile import
if b'import zipfile' not in data:
    import re
    m = re.search(rb'^(import|from)\s', data, re.MULTILINE)
    pos = data.find(b'\n', m.start())
    data = data[:pos+1] + b'import zipfile, threading, datetime as _dt\r\n' + data[pos+1:]
    print("D: OK")
else:
    print("D: skip")

# E: 右上角加按钮
old5 = b'        create_flat_action_button(shell_top, "\xe4\xbf\xae\xe6\x94\xb9\xe5\xaf\x86\xe7\xa0\x81", self.change_password, side="right")\r\n'
new5 = (
    b'        create_flat_action_button(shell_top, "\xe4\xbf\xae\xe6\x94\xb9\xe5\xaf\x86\xe7\xa0\x81", self.change_password, side="right")\r\n'
    b'        create_flat_action_button(shell_top, "\xe5\xa4\x87\xe4\xbb\xbd", self._backup_data, side="right")\r\n'
    b'        create_flat_action_button(shell_top, "\xe6\x81\xa2\xe5\xa4\x8d\xe5\xa4\x87\xe4\xbb\xbd", self._restore_backup, side="right")\r\n'
)
assert old5 in data, 'E: button not found'
data = data.replace(old5, new5, 1)
print("E: OK")

# F: _build_navigation 之前插入方法
old6 = b'    def _build_navigation(self):\r\n'
assert old6 in data, 'F: _build_navigation not found'

# 方法代码（纯ASCII，Unicode全用\uXXXX转义）
methods_code = (
    '''
    # ─── 备份 / 恢复备份 ───────────────────────────────────
    def _backup_data(self):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title="\u4fdd\u5b58\u5907\u4efd\u6587\u4ef6",
            defaultextension=".zip",
            initialfile="ExpiryManager_Backup_{}.zip".format(ts),
            filetypes=[("ZIP \u538b\u7f29\u5305", "*.zip")],
            parent=self,
        )
        if not path:
            return
        sv = tk.StringVar(value="\u23f3 \u6b63\u5728\u5907\u4efd ...")
        lbl = ttk.Label(self, textvariable=sv, foreground="#888")
        lbl.place(relx=0.5, rely=0.98, anchor="s")
        def run():
            try:
                self._do_backup(Path(path), sv)
            finally:
                self.after(0, lbl.destroy)
        threading.Thread(target=run, daemon=True).start()

    def _do_backup(self, zip_path, sv):
        DATA_DIR = BASE_DIR / "ExpiryManager_Data"
        all_files = [p for p in DATA_DIR.rglob("*") if p.is_file()]
        total = len(all_files)
        done = [0]
        def upd(n):
            sv.set("\u2022 \u5907\u4efd\u4e2d ... {}/{}".format(n, total))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in all_files:
                zf.write(p, str(p.relative_to(DATA_DIR)))
                done[0] += 1
                if done[0] % 20 == 0:
                    self.after(0, lambda n=done[0]: upd(n))
        self.after(0, lambda: sv.set("\u2713 \u5907\u4efd\u5b8c\u6210: " + zip_path.name))

    def _restore_backup(self):
        path = filedialog.askopenfilename(
            title="\u9009\u62e9\u5907\u4efd\u6587\u4ef6",
            filetypes=[("ZIP \u538b\u7f29\u5305", "*.zip")],
            parent=self,
        )
        if not path:
            return
        if not messagebox.askyesno(
            "\u786e\u8ba4\u6062\u590d",
            "\u6062\u590d\u5907\u4efd\u5c06\u8986\u76d6\u5f53\u524d\u6240\u6709\u6570\u636e\uff01\n\n\u7ee7\u7eed\u5417\uff1f",
            parent=self
        ):
            return
        DATA_DIR = BASE_DIR / "ExpiryManager_Data"
        try:
            with zipfile.ZipFile(path, "r") as zf:
                extracted = 0
                for member in zf.namelist():
                    mp = (DATA_DIR / member).resolve()
                    if not str(mp).startswith(str(DATA_DIR.resolve())):
                        continue
                    zf.extract(member, DATA_DIR)
                    extracted += 1
            messagebox.showinfo(
                "\u6062\u590d\u6210\u529f",
                "\u5df2\u4ece\u5907\u4efd\u6062\u590d {} \u4e2a\u6587\u4ef6/\u76ee\u5f55\u3002\n\u8bf7\u91cd\u542f\u7a0b\u5e8f\u4f7f\u6570\u636e\u751f\u6548\u3002".format(extracted),
                parent=self
            )
        except Exception as ex:
            messagebox.showerror("\u6062\u590d\u5931\u8d25", "\u89e3\u538b\u5931\u8d25: " + str(ex), parent=self)

'''.encode('utf-8'))

data = data.replace(old6, methods_code + old6, 1)
print("F: OK")

with open(MAIN, 'wb') as f:
    f.write(data)
print("main.py written")

try:
    py_compile.compile(str(MAIN), doraise=True)
    print("SYNTAX OK")
except py_compile.PyCompileError as e:
    print("SYNTAX ERROR:", e)
