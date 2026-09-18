# -*- coding: utf-8 -*-
"""
===============================================================================
ADB 工具箱
===============================================================================
功能模块：
  1. 设备管理  - 列出/连接/断开/重启 adb server
  2. 应用管理  - 安装/卸载(含保留数据)/运行/停止/清除数据
  3. 文件传输  - 推送/拉取
  4. 日志查看  - logcat 实时/历史
  5. Shell     - 自定义 adb shell 命令
  6. 雷电模拟器 - 一键连接
  7. 工具集    - 禁用/启用/提取apk/软件信息/操作记录
===============================================================================
"""

import re
import shlex
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path
from datetime import datetime
from typing import Optional

import tools_db


# 颜色
COLOR_BG = "#f5f5f5"
COLOR_CARD = "#ffffff"
COLOR_BORDER = "#e0e0e0"
COLOR_OK = "#10b981"
COLOR_ERR = "#ef4444"
COLOR_WARN = "#f59e0b"
COLOR_MUTED = "#6b7280"

# 雷电模拟器常用端口
LD_PLAYER_PORTS = [5555, 5556, 5557, 5558, 5559, 5560, 5561, 5562, 5563, 5564, 5565]


class AdbPage(ttk.Frame):
    """ADB 工具箱主页面"""

    def __init__(self, parent: ttk.Frame, db_conn, project_root: str = ""):
        super().__init__(parent)
        self.db_adapter = tools_db.ToolboxDatabaseAdapter.from_source(db_conn)
        self.db = self.db_adapter.connection
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.adb_history_dir = self.project_root / "adb_history"
        self.adb_history_dir.mkdir(exist_ok=True)

        # 状态
        self.current_device: Optional[str] = None
        self.devices: list[dict] = []  # [{serial, state, model, android_ver}]
        self.installed_packages: list[dict] = []
        self.logcat_process: Optional[subprocess.Popen] = None
        self._logcat_running = False

        tools_db.init_all_tool_tables(self.db)

        self._build_ui()
        self._refresh_devices()

    # ------------------------------------------------------------------
    # UI 布局
    # ------------------------------------------------------------------

    def _build_ui(self):
        # 顶部：设备状态栏
        self._build_device_bar()
        # 主体：左侧功能导航 + 右侧工作区
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        body_pane = ttk.PanedWindow(body, orient="horizontal")
        body_pane.pack(fill="both", expand=True)

        left = ttk.Frame(body_pane, width=180)
        body_pane.add(left, weight=1)
        right = ttk.Frame(body_pane)
        body_pane.add(right, weight=4)

        self._build_func_nav(left)
        self.work_area = right
        self._show_page("devices")  # 默认显示设备页

    def _build_device_bar(self):
        """顶部设备状态栏"""
        bar = ttk.Frame(self, padding=(8, 6), relief="ridge")
        bar.pack(fill="x")

        ttk.Label(bar, text="设备:").pack(side="left", padx=(0, 4))
        self.device_var = tk.StringVar(value="(未连接)")
        self.device_combo = ttk.Combobox(bar, textvariable=self.device_var, width=30, state="readonly")
        self.device_combo.pack(side="left", padx=(0, 8))
        self.device_combo.bind("<<ComboboxSelected>>", lambda e: self._on_device_change())

        ttk.Button(bar, text="🔄 刷新设备", width=12,
                   command=self._refresh_devices).pack(side="left", padx=2)
        ttk.Button(bar, text="🔌 雷电模拟器", width=14,
                   command=self._connect_ld_player).pack(side="left", padx=2)
        ttk.Button(bar, text="🔌 手动连接", width=12,
                   command=self._show_connect_dialog).pack(side="left", padx=2)
        ttk.Button(bar, text="⏏ 断开全部", width=12,
                   command=self._disconnect_all).pack(side="left", padx=2)
        ttk.Button(bar, text="🛠 adb 版本", width=10,
                   command=self._show_adb_version).pack(side="left", padx=2)

        self.status_label = ttk.Label(bar, text="", foreground=COLOR_MUTED)
        self.status_label.pack(side="right", padx=8)

    def _build_func_nav(self, parent):
        """左侧功能导航"""
        ttk.Label(parent, text="功能", font=("", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 6))

        nav_items = [
            ("📱 设备管理", "devices"),
            ("📦 应用管理", "apps"),
            ("📁 文件传输", "files"),
            ("📜 日志查看", "logcat"),
            ("💻 Shell", "shell"),
            ("🧰 工具集", "tools"),
            ("📋 操作记录", "history"),
        ]
        self.nav_buttons = []
        for label, key in nav_items:
            btn = ttk.Button(parent, text=label, width=22,
                             command=lambda k=key: self._show_page(k))
            btn.pack(fill="x", padx=6, pady=2)
            self.nav_buttons.append((key, btn))

    def _show_page(self, key: str):
        """切换右侧工作区"""
        # 清理
        for w in self.work_area.winfo_children():
            w.destroy()

        # 高亮导航
        for k, btn in self.nav_buttons:
            if k == key:
                btn.state(["pressed"])
            else:
                btn.state(["!pressed"])

        # 创建页面
        page_builders = {
            "devices": self._build_devices_page,
            "apps": self._build_apps_page,
            "files": self._build_files_page,
            "logcat": self._build_logcat_page,
            "shell": self._build_shell_page,
            "tools": self._build_tools_page,
            "history": self._build_history_page,
        }
        builder = page_builders.get(key)
        if builder:
            builder(self.work_area)

    # ------------------------------------------------------------------
    # 设备管理页
    # ------------------------------------------------------------------

    def _build_devices_page(self, parent):
        ttk.Label(parent, text="📱 设备管理", font=("", 13, "bold")
                  ).pack(anchor="w", padx=8, pady=(8, 6))

        btn_bar = ttk.Frame(parent)
        btn_bar.pack(fill="x", padx=8)
        ttk.Button(btn_bar, text="重启 adb server",
                   command=self._restart_adb).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="重启设备",
                   command=self._reboot_device).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="recovery",
                   command=lambda: self._reboot_device("recovery")).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="bootloader",
                   command=lambda: self._reboot_device("bootloader")).pack(side="left", padx=2)

        # 设备列表
        cols = ("serial", "state", "model", "android", "sdk")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self.device_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        for col, text, w in [("serial", "序列号", 220), ("state", "状态", 100),
                              ("model", "型号", 200), ("android", "Android", 100),
                              ("sdk", "SDK", 80)]:
            self.device_tree.heading(col, text=text)
            self.device_tree.column(col, width=w, anchor="w")
        self.device_tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.device_tree.yview)
        sb.pack(side="right", fill="y")
        self.device_tree.configure(yscrollcommand=sb.set)
        self.device_tree.bind("<<TreeviewSelect>>", lambda e: self._on_device_tree_select())

        # 设备信息
        info_frame = ttk.LabelFrame(parent, text="设备信息", padding=8)
        info_frame.pack(fill="x", padx=8, pady=(0, 8))
        self.device_info_text = scrolledtext.ScrolledText(info_frame, height=10,
                                                            font=("Consolas", 9))
        self.device_info_text.pack(fill="both", expand=True)

    def _refresh_devices(self):
        """刷新设备列表"""
        code, out, err = self._run_adb("devices -l", timeout=10)
        self.devices.clear()
        device_serials = ["(无)"]

        if code == 0 and out:
            for line in out.strip().split("\n")[1:]:
                line = line.strip()
                if not line or line.startswith("*"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                serial = parts[0]
                state = parts[1]
                # 解析 model:xxx 等附加信息
                model = ""
                for p in parts[2:]:
                    if p.startswith("model:"):
                        model = p[6:]
                        break
                self.devices.append({
                    "serial": serial, "state": state, "model": model
                })
                device_serials.append(f"{serial} [{state}]")

        self.device_combo["values"] = device_serials
        if self.current_device and any(d["serial"] == self.current_device for d in self.devices):
            self.device_var.set(f"{self.current_device} [{next(d['state'] for d in self.devices if d['serial']==self.current_device)}]")
        elif self.devices:
            self.current_device = self.devices[0]["serial"]
            self.device_var.set(f"{self.current_device} [{self.devices[0]['state']}]")
        else:
            self.current_device = None
            self.device_var.set("(未连接)")

        # 刷新 device 树
        if hasattr(self, "device_tree"):
            for item in self.device_tree.get_children():
                self.device_tree.delete(item)
            for d in self.devices:
                # 获取详细信息
                android_ver = ""
                sdk = ""
                if d["state"] == "device":
                    ver_out = self._adb_shell("getprop ro.build.version.release", serial=d["serial"])
                    sdk_out = self._adb_shell("getprop ro.build.version.sdk", serial=d["serial"])
                    if ver_out:
                        android_ver = ver_out.strip()
                    if sdk_out:
                        sdk = sdk_out.strip()
                self.device_tree.insert("", "end", values=(
                    d["serial"], d["state"], d["model"], android_ver, sdk))

        # 状态栏
        ok_count = sum(1 for d in self.devices if d["state"] == "device")
        self.status_label.config(
            text=f"已连接 {ok_count} / 总数 {len(self.devices)}",
            foreground=COLOR_OK if ok_count > 0 else COLOR_MUTED
        )

    def _on_device_tree_select(self):
        sel = self.device_tree.selection()
        if not sel:
            return
        values = self.device_tree.item(sel[0])["values"]
        if not values:
            return
        serial = values[0]
        self.current_device = serial
        self._load_device_info()

    def _load_device_info(self):
        if not self.current_device:
            return
        info = []
        props = [
            ("设备型号", "ro.product.model"),
            ("制造商", "ro.product.manufacturer"),
            ("品牌", "ro.product.brand"),
            ("Android", "ro.build.version.release"),
            ("SDK", "ro.build.version.sdk"),
            ("CPU ABI", "ro.product.cpu.abi"),
            ("分辨率", "ro.product.screen.width x ro.product.screen.height"),
            ("电池", "dumpsys battery | grep level"),
            ("存储", "df /data | tail -1"),
        ]
        for label, prop in props:
            val = self._adb_shell(prop, serial=self.current_device, timeout=5)
            info.append(f"{label:12s}: {val.strip() if val else '(无)'}")
        self.device_info_text.delete("1.0", "end")
        self.device_info_text.insert("1.0", "\n".join(info))

    def _restart_adb(self):
        self._run_adb("kill-server")
        time.sleep(0.5)
        self._run_adb("start-server")
        self._refresh_devices()
        messagebox.showinfo("提示", "adb server 已重启。", parent=self)

    def _reboot_device(self, mode: str = ""):
        if not self.current_device:
            return
        cmd = f"reboot {mode}".strip()
        if not messagebox.askyesno("确认", f"确定对设备执行 {cmd} 吗？", parent=self):
            return
        self._run_adb(f"-s {self.current_device} {cmd}")
        time.sleep(1)
        self._refresh_devices()

    def _connect_ld_player(self):
        """尝试连接雷电模拟器"""
        found = []
        for port in LD_PLAYER_PORTS:
            code, out, err = self._run_adb(f"connect 127.0.0.1:{port}", timeout=3)
            if code == 0 and ("connected" in out.lower() or "already" in out.lower()):
                found.append(f"127.0.0.1:{port}")
        self._refresh_devices()
        if found:
            messagebox.showinfo("提示", f"已连接：\n{chr(10).join(found)}", parent=self)
        else:
            messagebox.showwarning("提示",
                                    "未找到雷电模拟器。\n请先启动雷电模拟器，或手动指定端口。",
                                    parent=self)

    def _show_connect_dialog(self):
        port = tk.simpledialog.askstring("手动连接", "输入 IP:端口（如 127.0.0.1:5555）",
                                          parent=self)
        if not port:
            return
        code, out, err = self._run_adb(f"connect {port}", timeout=5)
        if code == 0:
            messagebox.showinfo("提示", out or "已连接", parent=self)
            self._refresh_devices()
        else:
            messagebox.showerror("错误", err or out, parent=self)

    def _disconnect_all(self):
        self._run_adb("disconnect")
        self._refresh_devices()

    def _show_adb_version(self):
        code, out, err = self._run_adb("version")
        messagebox.showinfo("adb 版本", out or err, parent=self)

    # ------------------------------------------------------------------
    # 应用管理页
    # ------------------------------------------------------------------

    def _build_apps_page(self, parent):
        ttk.Label(parent, text="📦 应用管理", font=("", 13, "bold")
                  ).pack(anchor="w", padx=8, pady=(8, 6))

        # 工具栏
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8)
        ttk.Button(bar, text="🔄 刷新列表", command=self._load_packages).pack(side="left", padx=2)
        ttk.Button(bar, text="⬇ 安装 APK", command=self._install_apk).pack(side="left", padx=2)
        ttk.Button(bar, text="📤 提取 APK", command=self._extract_apk).pack(side="left", padx=2)
        ttk.Button(bar, text="▶ 启动", command=lambda: self._app_action("launch")).pack(side="left", padx=2)
        ttk.Button(bar, text="⏹ 强制停止", command=lambda: self._app_action("force_stop")).pack(side="left", padx=2)
        ttk.Button(bar, text="⏸ 禁用", command=lambda: self._app_action("disable")).pack(side="left", padx=2)
        ttk.Button(bar, text="▶ 启用", command=lambda: self._app_action("enable")).pack(side="left", padx=2)
        ttk.Button(bar, text="🗑 清除数据", command=lambda: self._app_action("clear")).pack(side="left", padx=2)
        ttk.Button(bar, text="❌ 卸载", command=lambda: self._app_action("uninstall")).pack(side="left", padx=2)
        ttk.Button(bar, text="📦 保留数据卸载", command=lambda: self._app_action("uninstall_keep")).pack(side="left", padx=2)

        # 搜索
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(search_frame, text="搜索:").pack(side="left")
        self.pkg_search_var = tk.StringVar()
        self.pkg_search_var.trace_add("write", lambda *_: self._filter_packages())
        ttk.Entry(search_frame, textvariable=self.pkg_search_var).pack(side="left", fill="x", expand=True, padx=4)

        # 列表
        cols = ("package", "type", "version", "target_sdk")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.pkg_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=18)
        for col, text, w in [("package", "包名", 350), ("type", "类型", 80),
                              ("version", "版本", 120), ("target_sdk", "Target", 80)]:
            self.pkg_tree.heading(col, text=text)
            self.pkg_tree.column(col, width=w, anchor="w")
        self.pkg_tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.pkg_tree.yview)
        sb.pack(side="right", fill="y")
        self.pkg_tree.configure(yscrollcommand=sb.set)
        self.pkg_tree.bind("<Double-Button-1>", lambda e: self._show_app_info())

    def _load_packages(self):
        if not self.current_device:
            messagebox.showinfo("提示", "请先连接设备。", parent=self)
            return
        self.status_label.config(text="加载应用列表中...")
        self.update_idletasks()
        # pm list packages -f
        code, out, _ = self._run_adb(f"-s {self.current_device} shell pm list packages -f", timeout=30)
        self.installed_packages.clear()
        if code == 0 and out:
            for line in out.strip().split("\n"):
                # package:/data/app/xxx/base.apk=com.xxx
                m = re.match(r"package:(\S+)=(\S+)", line)
                if m:
                    self.installed_packages.append({
                        "apk_path": m.group(1),
                        "package": m.group(2),
                    })
        # 获取版本号
        for pkg in self.installed_packages:
            ver_out = self._adb_shell(f"dumpsys package {pkg['package']} | grep versionName", timeout=5)
            m = re.search(r"versionName=([^\s]+)", ver_out or "")
            pkg["version"] = m.group(1) if m else "?"
            sdk_out = self._adb_shell(f"dumpsys package {pkg['package']} | grep targetSdk", timeout=5)
            m = re.search(r"targetSdk=(\d+)", sdk_out or "")
            pkg["target_sdk"] = m.group(1) if m else "?"
        # 区分系统/用户
        for pkg in self.installed_packages:
            pkg["type"] = "系统" if pkg["apk_path"].startswith("/system") or "/system/" in pkg["apk_path"] else "用户"
        self._filter_packages()
        self.status_label.config(text=f"已加载 {len(self.installed_packages)} 个应用")

    def _filter_packages(self):
        keyword = self.pkg_search_var.get().strip().lower() if hasattr(self, "pkg_search_var") else ""
        for item in self.pkg_tree.get_children():
            self.pkg_tree.delete(item)
        for pkg in self.installed_packages:
            if keyword and keyword not in pkg["package"].lower():
                continue
            self.pkg_tree.insert("", "end", values=(
                pkg["package"], pkg.get("type", ""),
                pkg.get("version", ""), pkg.get("target_sdk", "")
            ))

    def _get_selected_package(self) -> Optional[str]:
        sel = self.pkg_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一个应用。", parent=self)
            return None
        values = self.pkg_tree.item(sel[0])["values"]
        return values[0] if values else None

    def _app_action(self, action: str):
        pkg = self._get_selected_package()
        if not pkg:
            return
        if not self.current_device:
            return

        commands = {
            "launch": (f"shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1", "启动"),
            "force_stop": (f"shell am force-stop {pkg}", "强制停止"),
            "disable": (f"shell pm disable-user {pkg}", "禁用"),
            "enable": (f"shell pm enable {pkg}", "启用"),
            "clear": (f"shell pm clear {pkg}", "清除数据"),
            "uninstall": (f"uninstall {pkg}", "卸载"),
            "uninstall_keep": (f"shell pm uninstall -k {pkg}", "保留数据卸载"),
        }
        if action not in commands:
            return
        cmd, desc = commands[action]
        if action in ("uninstall", "uninstall_keep", "clear"):
            if not messagebox.askyesno("确认", f"确定对 [{pkg}] 执行 [{desc}] 吗？",
                                        parent=self):
                return
        code, out, err = self._run_adb(f"-s {self.current_device} {cmd}", timeout=20)
        success = code == 0
        tools_db.add_adb_history(
            self.db, command=cmd, device_serial=self.current_device or "",
            category="应用管理", success=success, note=f"{desc} {pkg}"
        )
        if success:
            messagebox.showinfo("提示", f"{desc} 成功。\n{out.strip()[:200]}", parent=self)
            if action == "uninstall" or action == "uninstall_keep":
                self._load_packages()
        else:
            messagebox.showerror("错误", f"{desc} 失败。\n{err or out}", parent=self)

    def _install_apk(self):
        path = filedialog.askopenfilename(parent=self, title="选择 APK",
                                           filetypes=[("APK", "*.apk"), ("所有", "*.*")])
        if not path or not self.current_device:
            return
        if not messagebox.askyesno("确认", f"安装 APK:\n{path}\n到设备 {self.current_device}？",
                                    parent=self):
            return
        self.status_label.config(text="安装中...")
        self.update_idletasks()
        code, out, err = self._run_adb(
            f"-s {self.current_device} install -r \"{path}\"", timeout=120
        )
        success = code == 0 and "Success" in out
        tools_db.add_adb_history(
            self.db, command=f"install {path}", device_serial=self.current_device,
            category="应用管理", success=success, note=Path(path).name
        )
        if success:
            messagebox.showinfo("提示", f"安装成功。\n{out}", parent=self)
            self._load_packages()
        else:
            messagebox.showerror("错误", f"安装失败。\n{err or out}", parent=self)
        self.status_label.config(text="")

    def _extract_apk(self):
        pkg = self._get_selected_package()
        if not pkg or not self.current_device:
            return
        # 查找 APK 路径
        code, out, _ = self._run_adb(f"-s {self.current_device} shell pm path {pkg}", timeout=10)
        if code != 0 or not out:
            messagebox.showerror("错误", "未找到 APK 路径。", parent=self)
            return
        m = re.search(r"package:(\S+)", out)
        if not m:
            return
        apk_path = m.group(1)
        # 拉取
        save_dir = filedialog.askdirectory(parent=self, title="选择保存目录")
        if not save_dir:
            return
        save_path = Path(save_dir) / f"{pkg}.apk"
        code, out, err = self._run_adb(
            f"-s {self.current_device} pull {apk_path} \"{save_path}\"", timeout=60
        )
        if code == 0:
            messagebox.showinfo("提示", f"已提取：\n{save_path}", parent=self)
            tools_db.add_adb_history(self.db, command=f"pull {apk_path}",
                                      device_serial=self.current_device,
                                      category="应用管理", success=True,
                                      note=f"extract {pkg}")
        else:
            messagebox.showerror("错误", err or out, parent=self)

    def _show_app_info(self):
        pkg = self._get_selected_package()
        if not pkg or not self.current_device:
            return
        out = self._adb_shell(f"dumpsys package {pkg}", timeout=15)
        # 弹窗显示关键信息
        win = tk.Toplevel(self)
        win.title(f"应用信息 - {pkg}")
        win.geometry("700x500")
        text = scrolledtext.ScrolledText(win, font=("Consolas", 9), wrap="word")
        text.pack(fill="both", expand=True)
        # 只保留关键字段
        keep_keys = ["versionName", "versionCode", "targetSdk", "minSdk",
                      "firstInstallTime", "lastUpdateTime", "userId", "codePath",
                      "primaryCpuAbi", "requested permissions", "install permissions"]
        filtered = []
        for line in (out or "").split("\n"):
            if any(k in line for k in keep_keys):
                filtered.append(line)
        text.insert("1.0", "\n".join(filtered) if filtered else out)
        tools_db.add_adb_history(self.db, command=f"dumpsys package {pkg}",
                                  device_serial=self.current_device,
                                  category="应用管理", success=True, note="info")

    # ------------------------------------------------------------------
    # 文件传输页
    # ------------------------------------------------------------------

    def _build_files_page(self, parent):
        ttk.Label(parent, text="📁 文件传输", font=("", 13, "bold")
                  ).pack(anchor="w", padx=8, pady=(8, 6))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8)
        ttk.Button(bar, text="🔄 刷新", command=lambda: self._refresh_remote_fs()
                   ).pack(side="left", padx=2)
        ttk.Button(bar, text="⬆ 推送文件", command=self._push_file
                   ).pack(side="left", padx=2)
        ttk.Button(bar, text="⬇ 拉取文件", command=self._pull_file
                   ).pack(side="left", padx=2)
        ttk.Button(bar, text="🔍 浏览路径", command=self._browse_remote_path
                   ).pack(side="left", padx=2)

        path_frame = ttk.Frame(parent)
        path_frame.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(path_frame, text="设备路径:").pack(side="left")
        self.remote_path_var = tk.StringVar(value="/sdcard/")
        ttk.Entry(path_frame, textvariable=self.remote_path_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(path_frame, text="转到", command=self._refresh_remote_fs).pack(side="left", padx=2)

        # 远程文件列表
        cols = ("name", "type", "size", "perms", "date")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.fs_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=18)
        for col, text, w in [("name", "名称", 280), ("type", "类型", 60),
                              ("size", "大小", 100), ("perms", "权限", 100),
                              ("date", "日期", 150)]:
            self.fs_tree.heading(col, text=text)
            self.fs_tree.column(col, width=w, anchor="w")
        self.fs_tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.fs_tree.yview)
        sb.pack(side="right", fill="y")
        self.fs_tree.configure(yscrollcommand=sb.set)
        self.fs_tree.bind("<Double-Button-1>", lambda e: self._on_fs_double_click())

        # 输出
        out_frame = ttk.LabelFrame(parent, text="输出", padding=4)
        out_frame.pack(fill="x", padx=8, pady=(0, 8))
        self.files_output = scrolledtext.ScrolledText(out_frame, height=6, font=("Consolas", 9))
        self.files_output.pack(fill="x")

    def _refresh_remote_fs(self):
        if not self.current_device:
            return
        path = self.remote_path_var.get().strip()
        out = self._adb_shell(f"ls -la {shlex.quote(path)}", timeout=10)
        for item in self.fs_tree.get_children():
            self.fs_tree.delete(item)
        if not out:
            return
        for line in out.strip().split("\n"):
            parts = line.split()
            if len(parts) < 7:
                continue
            perms = parts[0]
            name = parts[-1]
            if name in (".", ".."):
                continue
            size = parts[4] if len(parts) >= 7 else ""
            date = " ".join(parts[5:7]) if len(parts) >= 8 else ""
            ftype = "目录" if perms.startswith("d") else "文件"
            self.fs_tree.insert("", "end", values=(name, ftype, size, perms, date))

    def _on_fs_double_click(self):
        sel = self.fs_tree.selection()
        if not sel:
            return
        values = self.fs_tree.item(sel[0])["values"]
        if not values:
            return
        name, ftype = values[0], values[1]
        if ftype == "目录":
            current = self.remote_path_var.get().strip()
            if not current.endswith("/"):
                current += "/"
            self.remote_path_var.set(current + name)
            self._refresh_remote_fs()

    def _push_file(self):
        if not self.current_device:
            return
        local = filedialog.askopenfilename(parent=self, title="选择本地文件")
        if not local:
            return
        remote = self.remote_path_var.get().strip()
        if not remote.endswith("/"):
            remote += "/"
        code, out, err = self._run_adb(
            f"-s {self.current_device} push \"{local}\" {remote}{Path(local).name}",
            timeout=300
        )
        msg = out if out else err
        self.files_output.insert("end", f"\n[push] {msg}")
        tools_db.add_adb_history(self.db, command=f"push {local}",
                                  device_serial=self.current_device,
                                  category="文件传输", success=code == 0,
                                  note=f"-> {remote}")
        if code == 0:
            self._refresh_remote_fs()
            messagebox.showinfo("提示", "推送成功。", parent=self)

    def _pull_file(self):
        if not self.current_device:
            return
        sel = self.fs_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中文件。", parent=self)
            return
        values = self.fs_tree.item(sel[0])["values"]
        name = values[0]
        remote = self.remote_path_var.get().strip()
        if not remote.endswith("/"):
            remote += "/"
        remote_full = remote + name
        save = filedialog.askdirectory(parent=self, title="选择保存目录")
        if not save:
            return
        code, out, err = self._run_adb(
            f"-s {self.current_device} pull {remote_full} \"{save}\"", timeout=300
        )
        msg = out if out else err
        self.files_output.insert("end", f"\n[pull] {msg}")
        tools_db.add_adb_history(self.db, command=f"pull {remote_full}",
                                  device_serial=self.current_device,
                                  category="文件传输", success=code == 0)
        if code == 0:
            messagebox.showinfo("提示", f"已拉取到：\n{save}", parent=self)

    def _browse_remote_path(self):
        path = tk.simpledialog.askstring("浏览路径", "输入设备路径：", parent=self)
        if path:
            self.remote_path_var.set(path)
            self._refresh_remote_fs()

    # ------------------------------------------------------------------
    # 日志页
    # ------------------------------------------------------------------

    def _build_logcat_page(self, parent):
        ttk.Label(parent, text="📜 日志查看", font=("", 13, "bold")
                  ).pack(anchor="w", padx=8, pady=(8, 6))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8)
        self.logcat_start_btn = ttk.Button(bar, text="▶ 开始",
                                            command=self._start_logcat)
        self.logcat_start_btn.pack(side="left", padx=2)
        self.logcat_stop_btn = ttk.Button(bar, text="⏸ 停止",
                                           command=self._stop_logcat, state="disabled")
        self.logcat_stop_btn.pack(side="left", padx=2)
        ttk.Button(bar, text="🗑 清空", command=lambda: self.logcat_text.delete("1.0", "end")
                   ).pack(side="left", padx=2)
        ttk.Button(bar, text="💾 保存", command=self._save_logcat).pack(side="left", padx=2)
        ttk.Button(bar, text="导出全部日志",
                   command=self._dump_logcat).pack(side="left", padx=2)

        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(filter_frame, text="级别:").pack(side="left")
        self.log_level = tk.StringVar(value="V")
        ttk.Combobox(filter_frame, textvariable=self.log_level, width=6, state="readonly",
                     values=["V", "D", "I", "W", "E"]).pack(side="left", padx=4)
        ttk.Label(filter_frame, text="TAG:").pack(side="left", padx=(8, 0))
        self.log_tag = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.log_tag, width=20).pack(side="left", padx=4)
        ttk.Label(filter_frame, text="关键字:").pack(side="left", padx=(8, 0))
        self.log_keyword = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.log_keyword, width=20).pack(side="left", padx=4)

        self.logcat_text = scrolledtext.ScrolledText(parent, font=("Consolas", 9), height=22)
        self.logcat_text.pack(fill="both", expand=True, padx=8, pady=4)

    def _start_logcat(self):
        if not self.current_device:
            messagebox.showinfo("提示", "请先连接设备。", parent=self)
            return
        if self._logcat_running:
            return
        self._logcat_running = True
        self.logcat_start_btn.config(state="disabled")
        self.logcat_stop_btn.config(state="normal")
        level = self.log_level.get()
        tag = self.log_tag.get().strip()
        keyword = self.log_keyword.get().strip()

        cmd = ["adb", "-s", self.current_device, "logcat", "-v", "time", f"*:{level}"]
        if tag:
            cmd.extend([f"{tag}:{level}", "*:S"])
        try:
            self.logcat_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1
            )
            threading.Thread(target=self._read_logcat, args=(keyword,),
                             daemon=True).start()
            tools_db.add_adb_history(self.db, command=" ".join(cmd),
                                      device_serial=self.current_device,
                                      category="日志", success=True)
        except Exception as e:
            messagebox.showerror("错误", f"启动 logcat 失败：\n{e}", parent=self)
            self._logcat_running = False
            self.logcat_start_btn.config(state="normal")
            self.logcat_stop_btn.config(state="disabled")

    def _read_logcat(self, keyword: str):
        proc = self.logcat_process
        if not proc:
            return
        try:
            for line in proc.stdout:
                if not self._logcat_running:
                    break
                if keyword and keyword.lower() not in line.lower():
                    continue
                self.after(0, self._append_logcat, line)
        except Exception:
            pass
        finally:
            self.after(0, self._on_logcat_stopped)

    def _append_logcat(self, line: str):
        self.logcat_text.insert("end", line)
        # 限制行数
        line_count = int(self.logcat_text.index("end-1c").split(".")[0])
        if line_count > 5000:
            self.logcat_text.delete("1.0", "2000.0")
        self.logcat_text.see("end")

    def _on_logcat_stopped(self):
        self._logcat_running = False
        self.logcat_start_btn.config(state="normal")
        self.logcat_stop_btn.config(state="disabled")

    def _stop_logcat(self):
        self._logcat_running = False
        if self.logcat_process:
            try:
                self.logcat_process.terminate()
            except Exception:
                pass
            self.logcat_process = None

    def _save_logcat(self):
        content = self.logcat_text.get("1.0", "end")
        if not content.strip():
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".log",
                                             filetypes=[("Log", "*.log"), ("所有", "*.*")],
                                             initialfile=f"logcat_{datetime.now():%Y%m%d_%H%M%S}.log")
        if path:
            Path(path).write_text(content, encoding="utf-8")
            messagebox.showinfo("提示", f"已保存：\n{path}", parent=self)

    def _dump_logcat(self):
        """导出完整日志到文件"""
        if not self.current_device:
            return
        code, out, _ = self._run_adb(
            f"-s {self.current_device} logcat -d -v time", timeout=30
        )
        if code == 0 and out:
            path = self.adb_history_dir / f"logcat_full_{datetime.now():%Y%m%d_%H%M%S}.log"
            path.write_text(out, encoding="utf-8")
            messagebox.showinfo("提示", f"已保存：\n{path}\n共 {len(out)} 字符", parent=self)
            tools_db.add_adb_history(self.db, command="logcat -d",
                                      device_serial=self.current_device,
                                      category="日志", success=True,
                                      note=f"saved to {path.name}")
        else:
            messagebox.showerror("错误", "导出失败。", parent=self)

    # ------------------------------------------------------------------
    # Shell 页
    # ------------------------------------------------------------------

    def _build_shell_page(self, parent):
        ttk.Label(parent, text="💻 Shell", font=("", 13, "bold")
                  ).pack(anchor="w", padx=8, pady=(8, 6))

        # 常用命令
        presets = [
            ("查看前台 Activity", "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity' | head -3"),
            ("查看电池信息", "dumpsys battery"),
            ("查看内存", "cat /proc/meminfo | head -10"),
            ("查看 CPU 信息", "cat /proc/cpuinfo | head -20"),
            ("查看网络信息", "ip addr show"),
            ("查看 WiFi 信息", "dumpsys wifi | grep -E 'SSID|RSSI' | head -10"),
            ("查看已安装输入法", "ime list -s"),
            ("设置屏幕常亮", "settings put system screen_off_timeout 1800000"),
            ("显示全部应用", "pm list packages -3"),
            ("显示系统应用", "pm list packages -s"),
            ("查看启动器", "cmd shortcut get-default-launcher"),
            ("查看屏幕分辨率", "wm size"),
        ]
        preset_frame = ttk.LabelFrame(parent, text="常用命令（点击填充）", padding=4)
        preset_frame.pack(fill="x", padx=8, pady=4)
        for i in range(0, len(presets), 4):
            row_frame = ttk.Frame(preset_frame)
            row_frame.pack(fill="x", pady=1)
            for label, cmd in presets[i:i + 4]:
                ttk.Button(row_frame, text=label, width=18,
                           command=lambda c=cmd: self.shell_cmd_var.set(c)
                           ).pack(side="left", padx=2, pady=1)

        # 命令输入
        cmd_frame = ttk.Frame(parent)
        cmd_frame.pack(fill="x", padx=8, pady=8)
        ttk.Label(cmd_frame, text="命令:").pack(side="left")
        self.shell_cmd_var = tk.StringVar()
        ttk.Entry(cmd_frame, textvariable=self.shell_cmd_var,
                  font=("Consolas", 10)).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(cmd_frame, text="▶ 执行",
                   command=self._exec_shell).pack(side="left", padx=2)
        ttk.Button(cmd_frame, text="⏹ 终止",
                   command=self._kill_shell).pack(side="left", padx=2)

        # 输出
        self.shell_output = scrolledtext.ScrolledText(parent, font=("Consolas", 9), height=18)
        self.shell_output.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _exec_shell(self):
        if not self.current_device:
            messagebox.showinfo("提示", "请先连接设备。", parent=self)
            return
        cmd = self.shell_cmd_var.get().strip()
        if not cmd:
            return
        self.shell_output.insert("end", f"\n$ {cmd}\n")
        self.shell_output.see("end")
        out = self._adb_shell(cmd, timeout=30)
        self.shell_output.insert("end", out or "(无输出)\n")
        self.shell_output.see("end")
        tools_db.add_adb_history(self.db, command=f"shell {cmd}",
                                  device_serial=self.current_device,
                                  category="Shell", success=True)

    def _kill_shell(self):
        self.shell_output.insert("end", "\n[用户取消]\n")

    # ------------------------------------------------------------------
    # 工具集页
    # ------------------------------------------------------------------

    def _build_tools_page(self, parent):
        ttk.Label(parent, text="🧰 工具集", font=("", 13, "bold")
                  ).pack(anchor="w", padx=8, pady=(8, 6))

        # 第一组：软件信息
        grp1 = ttk.LabelFrame(parent, text="软件信息", padding=8)
        grp1.pack(fill="x", padx=8, pady=4)
        grp1_inner = ttk.Frame(grp1)
        grp1_inner.pack(fill="x")
        items1 = [
            ("应用列表", "pm list packages -3"),
            ("第三方应用", "pm list packages -3 -f"),
            ("系统应用", "pm list packages -s"),
            ("查看所有包信息", "dumpsys package | grep -E 'packageName|versionName' | head -30"),
            ("查看启动器", "cmd shortcut get-default-launcher"),
            ("查看前台", "dumpsys activity activities | grep mResumedActivity"),
        ]
        for i, (label, cmd) in enumerate(items1):
            ttk.Button(grp1_inner, text=label, width=18,
                       command=lambda c=cmd: self._quick_shell(c, "信息查询")
                       ).grid(row=i // 4, column=i % 4, padx=2, pady=2, sticky="ew")

        # 第二组：系统操作
        grp2 = ttk.LabelFrame(parent, text="系统操作", padding=8)
        grp2.pack(fill="x", padx=8, pady=4)
        items2 = [
            ("重启到正常", "reboot"),
            ("重启到 recovery", "reboot recovery"),
            ("重启到 bootloader", "reboot bootloader"),
            ("屏幕截图", "screencap -p /sdcard/screen.png"),
            ("录制屏幕", "screenrecord --time-limit 30 /sdcard/record.mp4"),
            ("查看系统属性", "getprop"),
            ("查看 SELinux 状态", "getenforce"),
            ("查看运行服务", "dumpsys activity services | head -30"),
        ]
        grp2_inner = ttk.Frame(grp2)
        grp2_inner.pack(fill="x")
        for i, (label, cmd) in enumerate(items2):
            ttk.Button(grp2_inner, text=label, width=18,
                       command=lambda c=cmd: self._quick_shell(c, "系统操作")
                       ).grid(row=i // 4, column=i % 4, padx=2, pady=2, sticky="ew")

        # 第三组：自定义命令
        grp3 = ttk.LabelFrame(parent, text="自定义命令", padding=8)
        grp3.pack(fill="both", expand=True, padx=8, pady=4)
        custom_frame = ttk.Frame(grp3)
        custom_frame.pack(fill="x")
        ttk.Label(custom_frame, text="命令:").pack(side="left")
        self.tool_cmd_var = tk.StringVar()
        ttk.Entry(custom_frame, textvariable=self.tool_cmd_var,
                  font=("Consolas", 10)).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(custom_frame, text="执行", command=self._exec_custom_tool_cmd
                   ).pack(side="left", padx=2)

        self.tool_output = scrolledtext.ScrolledText(grp3, font=("Consolas", 9), height=10)
        self.tool_output.pack(fill="both", expand=True, pady=(8, 0))

    def _quick_shell(self, cmd: str, category: str):
        if not self.current_device:
            messagebox.showinfo("提示", "请先连接设备。", parent=self)
            return
        out = self._adb_shell(cmd, timeout=15)
        self.tool_output.delete("1.0", "end")
        self.tool_output.insert("1.0", f"$ {cmd}\n\n{out or '(无输出)'}")
        tools_db.add_adb_history(self.db, command=cmd,
                                  device_serial=self.current_device,
                                  category=category, success=True)

    def _exec_custom_tool_cmd(self):
        cmd = self.tool_cmd_var.get().strip()
        if not cmd:
            return
        self._quick_shell(cmd, "自定义")

    # ------------------------------------------------------------------
    # 操作记录页
    # ------------------------------------------------------------------

    def _build_history_page(self, parent):
        ttk.Label(parent, text="📋 操作记录", font=("", 13, "bold")
                  ).pack(anchor="w", padx=8, pady=(8, 6))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8)
        ttk.Button(bar, text="🔄 刷新", command=self._refresh_history).pack(side="left", padx=2)
        ttk.Button(bar, text="🗑 清空记录",
                   command=self._clear_history).pack(side="left", padx=2)
        ttk.Label(bar, text="分类:").pack(side="left", padx=(16, 4))
        self.history_category = tk.StringVar(value="全部")
        ttk.Combobox(bar, textvariable=self.history_category, state="readonly",
                     values=["全部", "应用管理", "文件传输", "日志", "Shell",
                             "系统操作", "自定义", "信息查询"],
                     width=12).pack(side="left", padx=2)
        self.history_category.trace_add("write", lambda *_: self._refresh_history())

        cols = ("time", "device", "category", "command", "success", "note")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self.history_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=20)
        for col, text, w in [("time", "时间", 150), ("device", "设备", 160),
                              ("category", "分类", 100), ("command", "命令", 350),
                              ("success", "结果", 60), ("note", "备注", 200)]:
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=w, anchor="w")
        self.history_tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.history_tree.yview)
        sb.pack(side="right", fill="y")
        self.history_tree.configure(yscrollcommand=sb.set)
        self._refresh_history()

    def _refresh_history(self):
        if not hasattr(self, "history_tree"):
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        cat = self.history_category.get() if hasattr(self, "history_category") else "全部"
        rows = tools_db.list_adb_history(self.db, limit=500, category=cat)
        for r in rows:
            self.history_tree.insert("", "end", values=(
                r["executed_at"], r["device_serial"], r["category"],
                r["command"][:200], "✅" if r["success"] else "❌", r["note"]
            ))

    def _clear_history(self):
        if not messagebox.askyesno("确认", "清空所有操作记录？", parent=self):
            return
        tools_db.clear_adb_history(self.db)
        self._refresh_history()

    # ------------------------------------------------------------------
    # ADB 命令封装
    # ------------------------------------------------------------------

    def _run_adb(self, args: str, timeout: int = 30) -> tuple[int, str, str]:
        """执行 adb 命令，返回 (code, stdout, stderr)

        ★ 安全修复（2026-07-24）：将 shell=True 改为 shell=False，
        用 shlex.split 解析参数，避免命令注入。"""
        try:
            # ★ shell=False + 列表形式，彻底消除命令注入风险
            cmd_list = ["adb"] + shlex.split(args)
            result = subprocess.run(
                cmd_list, shell=False, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"超时（{timeout}s）"
        except FileNotFoundError:
            return 1, "", "未找到 adb.exe，请先安装 Android SDK 平台工具"
        except Exception as e:
            return 1, "", str(e)

    def _adb_shell(self, cmd: str, serial: str = "", timeout: int = 10) -> str:
        """执行 adb shell 命令"""
        prefix = f"-s {serial} " if serial else ""
        code, out, err = self._run_adb(f"{prefix}shell {cmd}", timeout=timeout)
        return out if code == 0 else (err or out)

    def _on_device_change(self):
        sel = self.device_var.get()
        if "[" in sel:
            serial = sel.split("[")[0].strip()
        else:
            serial = sel
        self.current_device = serial if serial != "(无)" else None
        if hasattr(self, "device_info_text") and self.current_device:
            self._load_device_info()
