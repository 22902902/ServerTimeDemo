# -*- coding: utf-8 -*-
"""system_toolbox_page.py - Tab容器版"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from datetime import datetime
from pathlib import Path
import subprocess
from tools_page import ToolsPage
from adb_page import AdbPage
from console_page import ConsolePage
from tools_db import ToolboxDatabaseAdapter

BAT = """CREATE TABLE IF NOT EXISTS bat_scripts (id INTEGER PRIMARY KEY,name TEXT,content TEXT,description TEXT,category TEXT,tags TEXT,created_at TEXT,updated_at TEXT)"""

def init_t(conn): conn.execute(BAT); conn.commit()
def add_s(conn,n,c,d="",cat="",t=""):
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur=conn.execute("INSERT INTO bat_scripts VALUES(NULL,?,?,?,?,?,?,?)",(n,c,d,cat,t,now,now)); conn.commit(); return cur.lastrowid
def upd_s(conn,sid,n,c,d="",cat="",t=""):
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE bat_scripts SET name=?,content=?,description=?,category=?,tags=?,updated_at=? WHERE id=?",(n,c,d,cat,t,now,sid)); conn.commit()
def del_s(conn,sid): conn.execute("DELETE FROM bat_scripts WHERE id=?",(sid,)); conn.commit()
def get_s(conn,sid): r=conn.execute("SELECT * FROM bat_scripts WHERE id=?",(sid,)).fetchone(); return dict(r) if r else None
def list_s(conn,kw="",cat=""):
    sql="SELECT * FROM bat_scripts WHERE 1=1"; p=[]
    if kw: sql+=" AND (name LIKE ? OR description LIKE ? OR content LIKE ? OR tags LIKE ?)"; k=f"%{kw}%"; p.extend([k,k,k,k])
    if cat: sql+=" AND category=?"; p.append(cat)
    sql+=" ORDER BY updated_at DESC"
    return [dict(r) for r in conn.execute(sql,p).fetchall()]
def list_cat(conn): return [r["category"] for r in conn.execute("SELECT DISTINCT category FROM bat_scripts WHERE category!='' ORDER BY category").fetchall()]

DEFS=[
    {"n":"IP配置刷新","c":"@echo off\nchcp 65001 >nul\nipconfig /flushdns\nipconfig /release\nipconfig /renew\nnetsh winsock reset\npause","d":"刷新DNS/IP/Winsock","cat":"网络工具"},
    {"n":"系统信息","c":"@echo off\nchcp 65001 >nul\nsysteminfo | findstr /B /C:\"OS\"\nipconfig | findstr /B /C:\"IPv4\"\nwmic logicaldisk get caption,size,freespace\npause","d":"系统+网络+磁盘","cat":"系统维护"},
    {"n":"端口检查","c":"@echo off\nchcp 65001 >nul\nnetstat -ano | findstr LISTENING\npause","d":"端口监听","cat":"网络工具"},
    {"n":"一键清理","c":"@echo off\nchcp 65001 >nul\ndel /f /s /q %WINDIR%\\Temp\\*.* >nul 2>nul\ndel /f /s /q %TEMP%\\*.* >nul 2>nul\nipconfig /flushdns >nul\necho done\npause","d":"清理临时文件","cat":"系统维护"},
    {"n":"网络诊断","c":"@echo off\nchcp 65001 >nul\nset /p t=目标:\nif \"%t%\"==\"\" set t=baidu.com\nping %t%\nnslookup %t%\npause","d":"Ping+DNS","cat":"网络工具"},
]

class CmdToolboxPage(ttk.Frame):
    def __init__(self,parent,db,project_root=""):
        super().__init__(parent)
        self.db_adapter = ToolboxDatabaseAdapter.from_source(db)
        self.db = self.db_adapter.connection
        self.root=project_root; self._cur=None; self._map={}
        init_t(self.db); self._build(); self._ensure()

    def _build(self):
        lp=ttk.Frame(self,width=360); lp.pack(side="left",fill="y",padx=(8,4),pady=8); lp.pack_propagate(False)
        rp=ttk.Frame(self); rp.pack(side="left",fill="both",expand=True,padx=(4,8),pady=8)
        qf=ttk.LabelFrame(lp,text="系统工具",padding=8); qf.pack(fill="x",pady=(0,8))
        ttk.Button(qf,text="CMD 管理员",command=lambda:self._sp("cmd.exe")).pack(pady=2,fill="x")
        ttk.Button(qf,text="PS 管理员",command=lambda:self._sp("powershell.exe")).pack(pady=2,fill="x")
        ttk.Button(qf,text="打开脚本文件夹",command=self._open_f).pack(pady=2,fill="x")
        sf=ttk.Frame(lp); sf.pack(fill="x",pady=(0,6))
        ttk.Label(sf,text="搜索:").pack(side="left")
        self._srch=tk.StringVar()
        ttk.Entry(sf,textvariable=self._srch,width=28).pack(side="left",padx=(4,0))
        self._srch.trace_add("write",lambda *_:self._ref())
        cf=ttk.Frame(lp); cf.pack(fill="x",pady=(0,6))
        ttk.Label(cf,text="分类:").pack(side="left")
        self._cvar=tk.StringVar(value="全部")
        self._ccb=ttk.Combobox(cf,textvariable=self._cvar,width=24,state="readonly"); self._ccb.pack(side="left",padx=(4,0))
        self._cvar.trace_add("write",lambda *_:self._ref())
        lf=ttk.LabelFrame(lp,text="批处理脚本",padding=4); lf.pack(fill="both",expand=True)
        tf=ttk.Frame(lf); tf.pack(fill="both",expand=True)
        self._tr=ttk.Treeview(tf,columns=("n",),show="headings",height=14); self._tr.heading("n",text="名称"); self._tr.column("n",width=310)
        self._tr.pack(side="left",fill="both",expand=True); self._tr.bind("<<TreeviewSelect>>",lambda e:self._sel())
        af=ttk.Frame(lf); af.pack(fill="x",pady=(4,0))
        ttk.Button(af,text="+",command=self._new,width=4).pack(side="left",padx=1)
        ttk.Button(af,text="x",command=self._del,width=4).pack(side="left",padx=1)
        ttk.Button(af,text="运行",command=self._run_s,width=8).pack(side="right",padx=1)
        nf=ttk.Frame(rp); nf.pack(fill="x",pady=(0,6))
        ttk.Label(nf,text="名称:").pack(side="left")
        self._nvar=tk.StringVar()
        ttk.Entry(nf,textvariable=self._nvar).pack(side="left",padx=(4,0),fill="x",expand=True)
        mf=ttk.Frame(rp); mf.pack(fill="x",pady=(0,6))
        ttk.Label(mf,text="分类:").pack(side="left")
        self._scvar=tk.StringVar()
        ttk.Combobox(mf,textvariable=self._scvar,width=16).pack(side="left",padx=(4,12))
        ttk.Label(mf,text="标签:").pack(side="left")
        self._tvar=tk.StringVar()
        ttk.Entry(mf,textvariable=self._tvar).pack(side="left",padx=(4,0),fill="x",expand=True)
        self._ed=scrolledtext.ScrolledText(rp,wrap="none",font=("Consolas",10),height=18); self._ed.pack(fill="both",expand=True,pady=(0,6))
        df=ttk.Frame(rp); df.pack(fill="x",pady=(0,6))
        ttk.Label(df,text="说明:").pack(side="left")
        self._dvar=tk.StringVar()
        ttk.Entry(df,textvariable=self._dvar).pack(side="left",padx=(4,0),fill="x",expand=True)
        ef=ttk.Frame(rp); ef.pack(fill="x")
        ttk.Button(ef,text="保存",command=self._save,width=12).pack(side="left",padx=2)
        ttk.Button(ef,text="导出",command=self._exp,width=10).pack(side="left",padx=2)
        ttk.Button(ef,text="运行",command=self._run_c,width=10).pack(side="left",padx=2)
        ttk.Button(ef,text="清空",command=self._new,width=10).pack(side="right",padx=2)

    def _ensure(self):
        if not list_s(self.db): [add_s(self.db,s["n"],s["c"],s["d"],s["cat"]) for s in DEFS]
        self._ref()

    def _sp(self,app):
        try: subprocess.Popen(["powershell.exe","-Command",f"Start-Process {app} -Verb RunAs"],shell=False)
        except Exception as e: messagebox.showerror("错误",str(e),parent=self)

    def _open_f(self):
        f=Path(self.project_root)/"bat_scripts" if self.root else Path.cwd()/"bat_scripts"
        f.mkdir(exist_ok=True)
        try: subprocess.Popen(["explorer",str(f.resolve())],shell=False)
        except Exception as e: messagebox.showerror("错误",str(e),parent=self)

    def _ref(self):
        kw=self._srch.get().strip(); cat=self._cvar.get().strip()
        if cat=="全部": cat=""
        ss=list_s(self.db,kw,cat)
        cats=list_cat(self.db); vals=["全部"]+cats
        self._ccb["values"]=vals
        if self._cvar.get() not in vals: self._cvar.set("全部")
        for i in self._tr.get_children(): self._tr.delete(i)
        self._map.clear()
        for s in ss:
            iid=self._tr.insert("","end",values=(s["name"],)); self._map[iid]=s["id"]
        ch=self._tr.get_children()
        if ch:
            self._tr.selection_set(ch[0]); self._tr.see(ch[0]); self._sel()

    def _sel(self):
        sel=self._tr.selection()
        if not sel: return
        sid=self._map.get(sel[0])
        if not sid: return
        sc=get_s(self.db,sid)
        if not sc: return
        self._cur=sid
        self._nvar.set(sc["name"]); self._scvar.set(sc["category"] or "")
        self._tvar.set(sc["tags"] or ""); self._dvar.set(sc["description"] or "")
        self._ed.delete("1.0","end"); self._ed.insert("1.0",sc["content"])

    def _new(self):
        self._cur=None
        for v in(self._nvar,self._scvar,self._tvar,self._dvar): v.set("")
        self._ed.delete("1.0","end"); self._ed.focus_set()

    def _save(self):
        n=self._nvar.get().strip(); c=self._ed.get("1.0","end").strip()
        if not n or not c:
            messagebox.showwarning("提示","名称和内容必填。",parent=self); return False
        try:
            if self._cur: upd_s(self.db,self._cur,n,c,self._dvar.get().strip(),self._scvar.get().strip(),self._tvar.get().strip())
            else: self._cur=add_s(self.db,n,c,self._dvar.get().strip(),self._scvar.get().strip(),self._tvar.get().strip())
            self._ref(); return True
        except Exception as e: messagebox.showerror("错误",str(e),parent=self); return False

    def _del(self):
        sel=self._tr.selection()
        if not sel: return
        sid=self._map.get(sel[0])
        if sid and messagebox.askyesno("确认","删除？",parent=self):
            del_s(self.db,sid)
            if self._cur==sid: self._new()
            self._ref()

    def _run_s(self):
        sel=self._tr.selection()
        if not sel or not self._save(): return
        sid=self._map.get(sel[0])
        sc=get_s(self.db,sid)
        if sc: self._do_run(sc["name"],sc["content"])

    def _run_c(self):
        if not self._save(): return
        self._do_run(self._nvar.get() or "temp",self._ed.get("1.0","end").strip())

    def _do_run(self,n,c):
        try:
            f=Path(self.project_root)/"bat_scripts" if self.root else Path.cwd()/"bat_scripts"
            f.mkdir(exist_ok=True)
            safe="".join(x for x in n if x.isalnum() or x in " _-") or "temp"
            p=f/f"{safe}_{datetime.now():%H%M%S}.bat"
            p.write_text(c,encoding="utf-8")
            subprocess.Popen(["powershell.exe","-Command",f"Start-Process '{p.resolve()}' -Verb RunAs"],shell=False)
        except Exception as e: messagebox.showerror("错误",str(e),parent=self)

    def _exp(self):
        if not self._save(): return
        c=self._ed.get("1.0","end").strip()
        if not c: return
        n=self._nvar.get() or "unnamed"
        safe="".join(x for x in n if x.isalnum() or x in " _-") or "unnamed"
        path=filedialog.asksaveasfilename(parent=self,defaultextension=".bat",initialfile=f"{safe}.bat",filetypes=[("bat","*.bat")])
        if path:
            try:
                Path(path).write_text(c,encoding="utf-8")
                messagebox.showinfo("提示",f"已导出：{path}",parent=self)
            except Exception as e: messagebox.showerror("错误",str(e),parent=self)


class SystemToolboxPage(ttk.Frame):
    """系统工具箱：4个Tab"""
    def __init__(self,parent,db,project_root=""):
        super().__init__(parent)
        self.db_adapter = ToolboxDatabaseAdapter.from_source(db)
        self.db_adapter.ensure_ready()
        self.db=self.db_adapter.connection; self.root=project_root; self._build()

    def _build(self):
        h=ttk.Frame(self,padding=(8,6)); h.pack(fill="x")
        ttk.Label(h,text="系统工具箱",font=("",13,"bold")).pack(side="left")
        ttk.Label(h,text="  工具管理/批处理脚本/ADB调试/控制台",foreground="#6b7280").pack(side="left",padx=8)
        nb=ttk.Notebook(self); nb.pack(fill="both",expand=True,padx=24,pady=(0,8))
        self.tools_page=ToolsPage(nb,self.db_adapter,project_root=self.root)
        nb.add(self.tools_page,text="工具包")
        self.cmd_page=CmdToolboxPage(nb,self.db_adapter,project_root=self.root)
        nb.add(self.cmd_page,text="CMD 工具箱")
        self.adb_page=AdbPage(nb,self.db_adapter,project_root=self.root)
        nb.add(self.adb_page,text="ADB 工具箱")
        self.console_page=ConsolePage(nb,self.db_adapter,project_root=self.root,
                                       tools_dir=self.tools_page.tools_dir,
                                       on_icon_extract_complete=self._on_icons_extracted)
        nb.add(self.console_page,text="控制台")

    def _on_icons_extracted(self):
        """图标抽取完成后刷新工具包页面"""
        if hasattr(self.tools_page, "_refresh_all"):
            self.tools_page._refresh_all()
