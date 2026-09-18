# -*- coding: utf-8 -*-
"""console_page.py - 控制台页面(日志输出 + 命令执行 + 工具维护)"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import sys
import threading
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
import tools_db

# 颜色常量
COLOR_BG = "#f5f5f5"
COLOR_CONSOLE_BG = "#1e1e1e"
COLOR_CONSOLE_FG = "#d4d4d4"
COLOR_SUCCESS = "#4ec9b0"
COLOR_ERROR = "#f14c4c"
COLOR_WARNING = "#cca700"
COLOR_INFO = "#3794ff"


class ConsolePage(ttk.Frame):
    """控制台页面 - 日志输出 + 命令执行 + 工具维护"""

    def __init__(self, parent, db, project_root: str = "",
                 tools_dir: Optional[Path] = None,
                 on_icon_extract_complete: Optional[Callable] = None):
        super().__init__(parent)
        self.db_adapter = tools_db.ToolboxDatabaseAdapter.from_source(db)
        self.db = self.db_adapter.connection
        self.project_root = project_root
        self.tools_dir = tools_dir or Path(project_root) / "Tools"
        self.on_icon_extract_complete = on_icon_extract_complete
        self._extracting = False  # * 防重入
        self._extract_thread: Optional[threading.Thread] = None  # * 当前抽取线程
        self._build_ui()

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=8, pady=8)

        ttk.Label(toolbar, text="控制台", font=("", 12, "bold")).pack(side="left")

        # 功能按钮
        btn_frame = ttk.Frame(toolbar)
        btn_frame.pack(side="right")

        ttk.Button(btn_frame, text="抽取所有图标",
                   command=self._extract_all_icons).pack(side="left", padx=4)
        self.extract_btn = btn_frame.winfo_children()[-1]  # * 记录按钮引用
        self.stop_btn = ttk.Button(btn_frame, text="终止",
                   command=self._stop_extract, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="⚠ 杀PowerShell",
                   command=self._kill_powershell).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="清空日志",
                   command=self._clear_log).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="导出日志",
                   command=self._export_log).pack(side="left", padx=4)

        # * 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self, variable=self.progress_var, maximum=100
        )
        self.progress_bar.pack(side="bottom", fill="x", padx=8, pady=(0, 4))

        # 控制台输出区(黑色背景)
        console_frame = ttk.Frame(self)
        console_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.log_text = scrolledtext.ScrolledText(
            console_frame,
            bg=COLOR_CONSOLE_BG,
            fg=COLOR_CONSOLE_FG,
            font=("Consolas", 10),
            wrap="word",
            state="disabled"
        )
        self.log_text.pack(fill="both", expand=True)

        # 配置颜色标签
        self.log_text.tag_configure("success", foreground=COLOR_SUCCESS)
        self.log_text.tag_configure("error", foreground=COLOR_ERROR)
        self.log_text.tag_configure("warning", foreground=COLOR_WARNING)
        self.log_text.tag_configure("info", foreground=COLOR_INFO)

        # 命令输入区
        cmd_frame = ttk.Frame(self)
        cmd_frame.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Label(cmd_frame, text="命令:").pack(side="left", padx=(0, 4))

        self.cmd_entry = ttk.Entry(cmd_frame)
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.cmd_entry.bind("<Return>", self._execute_command)

        ttk.Button(cmd_frame, text="执行",
                   command=self._execute_command).pack(side="left", padx=4)

        # 模式选择
        mode_frame = ttk.Frame(cmd_frame)
        mode_frame.pack(side="right", padx=4)

        self.mode_var = tk.StringVar(value="ps")
        ttk.Radiobutton(mode_frame, text="PowerShell", variable=self.mode_var,
                        value="ps").pack(side="left", padx=2)
        ttk.Radiobutton(mode_frame, text="CMD", variable=self.mode_var,
                        value="cmd").pack(side="left", padx=2)

        # 初始日志
        self.log("控制台已启动", "success")

    def log(self, message: str, level: str = "info"):
        """写入日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        """清空日志"""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log("日志已清空", "info")

    def _export_log(self):
        """导出日志到文件"""
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
            initialfile=f"console_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        if not file_path:
            return
        try:
            content = self.log_text.get("1.0", "end")
            Path(file_path).write_text(content, encoding="utf-8")
            self.log(f"日志已导出: {file_path}", "success")
        except Exception as e:
            self.log(f"导出失败: {e}", "error")

    def _execute_command(self, event=None):
        """执行命令"""
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return

        mode = self.mode_var.get()
        self.log(f"> {cmd}", "info")

        def _run():
            try:
                if mode == "ps":
                    proc = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-NonInteractive",
                         "-ExecutionPolicy", "Bypass", "-Command", cmd],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                else:
                    proc = subprocess.run(
                        ["cmd.exe", "/c", cmd],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                if proc.stdout:
                    for line in proc.stdout.strip().split("\n"):
                        if line:
                            self.log(line, "success")
                if proc.stderr:
                    for line in proc.stderr.strip().split("\n"):
                        if line:
                            self.log(line, "error")
                if proc.returncode == 0:
                    self.log("命令执行成功", "success")
                else:
                    self.log(f"退出码: {proc.returncode}", "warning")

            except subprocess.TimeoutExpired:
                self.log("命令超时(30秒)", "error")
            except Exception as e:
                self.log(f"执行失败: {e}", "error")

        threading.Thread(target=_run, daemon=True).start()
        self.cmd_entry.delete(0, "end")

    def _extract_all_icons(self):
        """批量抽取所有工具图标(* 防重入 + 进度条 + 可终止 + 全主线程UI)"""
        if self._extracting:
            self._log_main("抽取进行中,请等待...", "warning")
            return

        self._extracting = True
        self._log_main("开始抽取工具图标...", "info")
        self.extract_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress_var.set(0)

        def _extract():
            import traceback
            try:
                import tools_db

                # * self.db 已统一为 Connection,直接使用
                tools = tools_db.list_tools(self.db, include_deleted=False)
                if not tools:
                    self._log_main("没有工具需要抽取图标", "warning")
                    self._extracting = False
                    self._finish_extract()
                    return

                self._log_main(f"共 {len(tools)} 个工具", "info")

                success_count = 0
                fail_count = 0
                skip_count = 0

                for i, tool in enumerate(tools, 1):
                    # * 检测终止信号
                    if not self._extracting:
                        self._log_main(f"用户终止抽取", "warning")
                        break

                    name = tool["name"]
                    icon_path = (tool.get("icon_path") or "").strip()

                    # 已有图标则跳过
                    if icon_path and Path(icon_path).exists():
                        self._log_main(f"[{i}/{len(tools)}] {name}: 已有图标,跳过", "info")
                        skip_count += 1
                    else:
                        safe_name = "".join(c for c in name if c.isalnum() or c in "._-")
                        target_png = self.tools_dir / "_icons" / f"{safe_name}.png"
                        target_png.parent.mkdir(parents=True, exist_ok=True)

                        exe_path = tool["path"]
                        if not Path(exe_path).is_absolute():
                            exe_path = self.tools_dir / exe_path

                        if not Path(exe_path).exists():
                            self._log_main(f"[{i}/{len(tools)}] {name}: 文件不存在,跳过", "warning")
                            skip_count += 1
                        else:
                            self._log_main(f"[{i}/{len(tools)}] {name}: 抽取中...", "info")
                            # * 在 UI 线程中调用,避免日志冲突
                            self.after(0, lambda v=(i/len(tools))*100: self.progress_var.set(v))
                            # * 使用缓存目录永久保存图标
                            cache_dir = self.tools_dir / "_图标"
                            if self._extract_one_icon(str(exe_path), str(target_png), cache_dir=cache_dir):
                                tools_db.update_tool(self.db, tool["id"], icon_path=str(target_png))
                                self._log_main(f"[{i}/{len(tools)}] {name}: ✓ 成功", "success")
                                success_count += 1
                            else:
                                self._log_main(f"[{i}/{len(tools)}] {name}: ✗ 失败", "error")
                                fail_count += 1

                    # * 实时更新进度
                    progress = (i / len(tools)) * 100
                    self.after(0, lambda v=progress: self.progress_var.set(v))

                self._log_main(f"抽取完成: 成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}",
                         "success" if fail_count == 0 else "warning")
            except Exception as e:
                # * 关键:捕获子线程所有异常,否则静默死掉
                self._log_main(f"✗ 抽取线程崩溃: {type(e).__name__}: {e}", "error")
                self._log_main(traceback.format_exc(), "error")
            finally:
                self._finish_extract()
                if self.on_icon_extract_complete:
                    try:
                        self.after(0, self.on_icon_extract_complete)
                    except Exception:
                        pass

        self._extract_thread = threading.Thread(target=_extract, daemon=True)
        self._extract_thread.start()

    def _log_main(self, message: str, level: str = "info"):
        """* 线程安全:子线程调此函数,自动调度到主线程"""
        self.after(0, lambda: self.log(message, level))

    def _finish_extract(self):
        """恢复按钮状态(主线程)"""
        self.progress_var.set(100)
        self._extracting = False
        self.extract_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def _stop_extract(self):
        """终止抽取"""
        if not self._extracting:
            return
        self._extracting = False  # * 发送终止信号
        self.log("正在终止抽取(等待当前项完成)...", "warning")

    def _kill_powershell(self):
        """* 强制杀死所有 powershell.exe 进程(紧急恢复卡死状态)"""
        try:
            if sys.platform.startswith("win"):
                r = subprocess.run(
                    ["taskkill", "/F", "/IM", "powershell.exe"],
                    capture_output=True, text=True, timeout=5
                )
                self.log(f"taskkill 返回: {r.stdout.strip() or r.stderr.strip()}", "warning")
            else:
                self.log("仅 Windows 平台支持", "warning")
        except Exception as e:
            self.log(f"杀进程失败: {e}", "error")



    def _ps_safe(self, s: str) -> str:
        """Escape single quotes and dollar signs for PowerShell strings.
        ' becomes '' and $ becomes `$ in single-quoted strings.
        """
        return s.replace("'", "''").replace("`", "``").replace("${", "`${").replace("$(", "`$(")
    def _get_icon_cache_path(self, exe_path: str, size: int, cache_dir: Path) -> Path:
        """生成图标缓存路径。基于 exe 文件名 + 文件 hash（mtime+size）+ 尺寸。"""
        import hashlib
        exe = Path(exe_path)
        if not exe.exists():
            return cache_dir / f"{exe.stem}_unknown_{size}.png"
        stat = exe.stat()
        file_hash = hashlib.md5(f"{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()[:8]
        return cache_dir / f"{exe.stem}_{file_hash}_{size}.png"

    def _extract_one_icon(self, exe_path: str, out_png: str, size: int = 48,
                          cache_dir: Optional[Path] = None) -> bool:
        """抽取单个图标(PowerShell 方案)
        * 单次超时 5 秒,避免卡死
        * 检查缓存：命中直接复制，未命中抽取后写入缓存永久保存
        """
        if not Path(exe_path).exists():
            return False

        # ★ 确定缓存目录（默认 Tools/_图标）
        if cache_dir is None:
            cache_dir = self.tools_dir / "_图标"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # ★ 检查缓存
        cache_path = self._get_icon_cache_path(exe_path, size, cache_dir)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            try:
                shutil.copy2(cache_path, out_png)
                return True
            except Exception:
                pass  # 复制失败，继续抽取

        safe_exe = self._ps_safe(exe_path)
        safe_out = self._ps_safe(out_png)
        ps_script = (
            f"try {{ "
            f"Add-Type -AssemblyName System.Drawing; "
            f"$icon = [System.Drawing.Icon]::ExtractAssociatedIcon('{safe_exe}'); "
            f"$bmp = $icon.ToBitmap(); "
            f"$bmp.Save('{safe_out}', [System.Drawing.Imaging.ImageFormat]::Png); "
            f"$icon.Dispose(); $bmp.Dispose(); "
            f"exit 0; "
            f"}} catch {{ exit 1 }}"
        )

        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                timeout=5
            )
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

        success = result.returncode == 0 and Path(out_png).exists()
        if success:
            # ★ 保存到缓存永久保存
            try:
                shutil.copy2(out_png, cache_path)
            except Exception:
                pass
        return success

