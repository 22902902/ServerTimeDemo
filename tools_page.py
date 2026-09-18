# -*- coding: utf-8 -*-
"""
===============================================================================
工具包页面（重写版：分类+包管理、相对路径、图标抽取）
===============================================================================
- 顶部：包下拉（增删改）+ 搜索 + 设置 + 打开 Tools
- 分类栏：[+ 分类] 按钮 + 右键编辑/删除（带工具数检查）
- 主区：网格状工具图标（自动从 .exe 抽图标，存到 _icons/）
- 右侧：编辑面板（显示相对路径）
- 页面右上角：上下滚动按钮（▲/▼）绑定到图标面板
- 整个页面：支持拖入 .exe 快速添加工具
===============================================================================
"""

import os
import sys
import shutil
import hashlib
import logging
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Optional

import tools_db
from dialog_form_style import apply_dialog_form_style, create_form_checkbutton, create_form_entry, create_form_frame, create_form_label
from ui_theme import PACKAGE_ACCENT_COLORS, THEME, TOOLBOX_PALETTE

# ★ tkdnd 拖拽支持（全局导入，确保打包包含）
try:
    from tkinterdnd2 import DND_FILES
    HAS_TKDND = True
except Exception:
    HAS_TKDND = False
    DND_FILES = None

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# 模块 logger — 统一走 logging（此前本模块无日志设施，logger.exception 会直接 NameError）
logger = logging.getLogger(__name__)


# 颜色常量 — 统一映射到全局主题中的工具箱配色
COLOR_BG = TOOLBOX_PALETTE.bg
COLOR_CARD = TOOLBOX_PALETTE.surface
COLOR_CARD_HOVER = TOOLBOX_PALETTE.surface_alt
COLOR_BORDER = TOOLBOX_PALETTE.border
COLOR_BORDER_LIGHT = TOOLBOX_PALETTE.border_soft
COLOR_PRIMARY = TOOLBOX_PALETTE.accent
COLOR_DANGER = TOOLBOX_PALETTE.danger
COLOR_TEXT = TOOLBOX_PALETTE.text_primary
COLOR_TEXT_MUTED = TOOLBOX_PALETTE.text_secondary
COLOR_MUTED = TOOLBOX_PALETTE.text_secondary
COLOR_ACCENT = TOOLBOX_PALETTE.accent
COLOR_DROP_HOVER = TOOLBOX_PALETTE.button_hover
COLOR_SUCCESS = TOOLBOX_PALETTE.success
COLOR_WARNING = TOOLBOX_PALETTE.warn


def apply_tool_dialog_theme(window):
    """统一工具箱弹窗的底色与 ttk 样式。"""
    style_prefix = apply_dialog_form_style(window, TOOLBOX_PALETTE, style_prefix="ToolDialog")
    style = ttk.Style(window)
    THEME.configure_toolbox_button_style(style, TOOLBOX_PALETTE)
    style.configure("ToolDialogCard.TFrame", background=COLOR_CARD)
    return style_prefix


def create_tool_dialog_body(window, *, padding=12):
    body = ttk.Frame(window, padding=padding, style="ToolDialog.TFrame")
    body.pack(fill="both", expand=True)
    return body


def create_toolbox_listbox(parent, *, height=12, font=("", 10)):
    return tk.Listbox(
        parent,
        height=height,
        font=font,
        bg=COLOR_CARD,
        fg=COLOR_TEXT,
        selectbackground=COLOR_DROP_HOVER,
        selectforeground=COLOR_TEXT,
        highlightthickness=1,
        highlightbackground=COLOR_BORDER_LIGHT,
        highlightcolor=COLOR_BORDER,
        relief="solid",
        bd=1,
    )


# ============================================================================
# 敏感数据混淆（FTP 密码）
# ============================================================================
# 简单 XOR-base64 混淆，防误读不防破解；本地桌面应用场景足够
_FTP_OBFUSCATION_KEY = 0x5A  # 固定单字节密钥


def _obfuscate(plaintext: str) -> str:
    """★ 混淆存储：plaintext → '__obf__' + base64(XOR) + '__'"""
    if not plaintext:
        return ""
    data = bytes(b ^ _FTP_OBFUSCATION_KEY for b in plaintext.encode("utf-8"))
    import base64
    return "__obf__" + base64.b64encode(data).decode("ascii") + "__"


def _deobfuscate(obfuscated: str) -> str:
    """★ 读取时还原：检测 "__obf__" 前缀则解码，否则返回原文（兼容旧明文）"""
    if not obfuscated:
        return ""
    if obfuscated.startswith("__obf__") and obfuscated.endswith("__"):
        inner = obfuscated[7:-2]
        try:
            import base64
            data = base64.b64decode(inner)
            return bytes(b ^ _FTP_OBFUSCATION_KEY for b in data).decode("utf-8")
        except Exception:
            return ""
    return obfuscated  # 旧明文直接返回


def _make_rounded_image(pil_img: Image.Image, size: int, radius: int = 12) -> Image.Image:
    """★ 将图片转为圆角矩形（参考手机桌面图标风格）"""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    # 缩放目标尺寸
    pil_img = pil_img.resize((size, size), Image.LANCZOS)
    # 创建圆角遮罩
    mask = Image.new("L", (size, size), 0)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    # 应用遮罩
    output = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    output.paste(pil_img, (0, 0))
    output.putalpha(mask)
    return output


def _make_native_icon(pil_img: Image.Image, size: int) -> Image.Image:
    """★ Windows 原生图标风格：透明背景、保持比例、无圆角裁剪。

    与 _make_rounded_image 的区别：
    - 不强制正方形：按原图比例缩放，最大边不超过 size
    - 无圆角遮罩：完整显示图标内容
    - 背景透明：RGBA 模式，无填充色
    """
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    # 保持比例缩放
    w, h = pil_img.size
    scale = min(size / w, size / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
    # 居中放置到透明画布（方便 Label 对齐）
    output = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    paste_x = (size - new_w) // 2
    paste_y = (size - new_h) // 2
    output.paste(pil_img, (paste_x, paste_y), pil_img)
    return output


# ============================================================================
# 图标抽取（Windows .exe → .png）
# ============================================================================

def _get_icon_cache_path(exe_path: str, size: int, cache_dir: Path) -> Path:
    """生成图标缓存路径。基于 exe 文件名 + 文件 hash（mtime+size）+ 尺寸。"""
    exe = Path(exe_path)
    if not exe.exists():
        return cache_dir / f"{exe.stem}_unknown_{size}.png"
    # 用文件修改时间和大小做 hash，确保 exe 更新后重新抽取
    stat = exe.stat()
    file_hash = hashlib.md5(f"{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()[:8]
    return cache_dir / f"{exe.stem}_{file_hash}_{size}.png"


def extract_exe_icon(exe_path: str, out_png: str, size: int = 48,
                      cache_dir: Optional[Path] = None) -> bool:
    """从 .exe/.dll 抽取图标保存为 PNG。
    优先检查缓存，缓存命中直接复制；否则 ctypes 同步抽取，写入缓存永久保存。
    ★ ctypes 优先（同步、<1秒），失败才回退 PowerShell。"""
    exe = Path(exe_path)
    if not exe.exists():
        return False

    # ★ 确定缓存目录
    if cache_dir is None:
        try:
            cache_dir = exe.parent.parent.parent / "_图标"
        except Exception:
            cache_dir = exe.parent / "_图标"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # ★ 检查缓存
    cache_path = _get_icon_cache_path(exe_path, size, cache_dir)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        try:
            Path(out_png).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_path, out_png)
            return True
        except Exception:
            pass

    Path(out_png).parent.mkdir(parents=True, exist_ok=True)

    # ---- 方案 1: ctypes 同步抽取（★ 优先，<1秒完成，无 PS 启动开销）----
    if HAS_PIL and sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            shell32 = ctypes.windll.shell32
            shell32.ExtractIconExW.restype = wintypes.UINT
            shell32.ExtractIconExW.argtypes = [
                wintypes.LPCWSTR, wintypes.INT,
                ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON),
                wintypes.UINT
            ]

            large_icons = (wintypes.HICON * 1)()
            small_icons = (wintypes.HICON * 1)()
            n = shell32.ExtractIconExW(exe_path, 0, large_icons, small_icons, 1)
            if n == 0:
                raise RuntimeError("no icons")

            hicon = large_icons[0]
            if not hicon:
                raise RuntimeError("hicon null")

            gdi32 = ctypes.windll.gdi32
            user32 = ctypes.windll.user32

            class ICONINFO(ctypes.Structure):
                _fields_ = [
                    ("fIcon", wintypes.BOOL),
                    ("xHotspot", wintypes.DWORD),
                    ("yHotspot", wintypes.DWORD),
                    ("hbmMask", wintypes.HBITMAP),
                    ("hbmColor", wintypes.HBITMAP),
                ]

            info = ICONINFO()
            if not user32.GetIconInfo(hicon, ctypes.byref(info)):
                user32.DestroyIcon(hicon)
                raise RuntimeError("GetIconInfo failed")

            class BITMAP(ctypes.Structure):
                _fields_ = [
                    ("bmType", wintypes.LONG),
                    ("bmWidth", wintypes.LONG),
                    ("bmHeight", wintypes.LONG),
                    ("bmWidthBytes", wintypes.LONG),
                    ("bmPlanes", wintypes.WORD),
                    ("bmBitsPixel", wintypes.WORD),
                    ("bmBits", ctypes.c_void_p),
                ]
            bmp = BITMAP()
            gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bmp), ctypes.byref(bmp))
            w, h = bmp.bmWidth, bmp.bmHeight
            if w == 0 or h == 0:
                user32.DestroyIcon(hicon)
                if info.hbmColor: gdi32.DeleteObject(info.hbmColor)
                if info.hbmMask: gdi32.DeleteObject(info.hbmMask)
                raise RuntimeError("zero size")

            buf_len = w * h * 4
            buf = (ctypes.c_ubyte * buf_len)()
            gdi32.GetBitmapBits(info.hbmColor, buf_len, buf)

            img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
            if img.size != (size, size):
                img = img.resize((size, size), Image.LANCZOS)
            img.save(out_png, "PNG")

            user32.DestroyIcon(hicon)
            if info.hbmColor: gdi32.DeleteObject(info.hbmColor)
            if info.hbmMask: gdi32.DeleteObject(info.hbmMask)

            # ★ 保存到缓存（永久保存，下次直接用）
            try:
                shutil.copy2(out_png, cache_path)
            except Exception:
                pass
            return True
        except Exception:
            # 走到 PowerShell 兑底
            try:
                Path(out_png).unlink(missing_ok=True)
            except Exception:
                pass

    # ---- 方案 2: PowerShell + System.Drawing （兑底，案外锦上添花）----
    if sys.platform.startswith("win"):
        try:
            ps_script = (
                f"Add-Type -AssemblyName System.Drawing; "
                f"$icon = [System.Drawing.Icon]::ExtractAssociatedIcon('{exe_path}'); "
                f"if ($icon) {{ "
                f"  $bmp = $icon.ToBitmap(); "
                f"  $bmp.Save('{out_png}', [System.Drawing.Imaging.ImageFormat]::Png); "
                f"  $icon.Dispose(); $bmp.Dispose(); "
                f"  exit 0 "
                f"}} else {{ exit 1 }}"
            )
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                  "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True, timeout=15
            )
            if r.returncode == 0 and Path(out_png).exists() and Path(out_png).stat().st_size > 0:
                if HAS_PIL:
                    try:
                        img = Image.open(out_png)
                        if img.size != (size, size):
                            img = img.resize((size, size), Image.LANCZOS)
                            img.save(out_png, "PNG")
                    except Exception:
                        pass
                try:
                    shutil.copy2(out_png, cache_path)
                except Exception:
                    pass
                return True
        except Exception:
            pass

    return False


# ============================================================================
# 工具包页面
# ============================================================================

class ToolsPage(ttk.Frame):
    """工具包页面（增强版）"""

    def __init__(self, parent: ttk.Frame, db_conn, project_root: str = ""):
        super().__init__(parent)
        self.db_adapter = tools_db.ToolboxDatabaseAdapter.from_source(db_conn)
        self.db = self.db_adapter.connection
        self.project_root = Path(project_root) if project_root else Path.cwd()

        # 从设置读取
        self.current_package = "个人系统"
        self.current_category = "全部"
        self.selected_tool_id: Optional[int] = None
        self.icon_cache: dict[str, Optional[tk.PhotoImage]] = {}  # path → PhotoImage
        self.toolbar_buttons: list[ttk.Button] = []

        # ★ 定义拖入高亮样式
        try:
            style = ttk.Style()
            THEME.configure_toolbox_button_style(style, TOOLBOX_PALETTE)
        except tk.TclError:
            pass

        # 拖拽状态
        self._drag_data = {"tool_id": None, "from_toolbar": False, "widget": None}

        # 关键：先初始化表，再读设置
        self._init_db()
        self._load_settings()
        self._resolve_tools_mode()   # ★ 自检：判断用项目 Tools 还是 FTP
        self._build_ui()
        # ★ 不再启动时自动扫描 Tools 文件夹
        #   原因：用户希望手动控制入库（拖入/点+添加），避免无用 exe 占位
        #   如需全量入库，点击顶部「扫描」按钮即可
        self._refresh_all()

    # ------------------------------------------------------------------
    # 工具箱自检 & FTP 模式
    # ------------------------------------------------------------------
    # ★ 自检原理：对 tools_dir 里所有文件（递归）取 (relative_path, size, mtime) 做 SHA1，
    #    存到 tool_settings._tools_manifest_hash。
    #    - 启动时对比 hash：相同→项目内置 Tools；不同→用户有自定义内容或从 FTP 下载过
    #    - FTP 下载时跳过引用路径（URL / UNC / 指向 Tools 外的绝对路径）

    def _compute_tools_manifest(self, tools_dir: Path) -> str:
        """计算 tools_dir 的内容指纹（不含 _icons 子目录和 .bak 文件）"""
        if not tools_dir.exists():
            return ""
        entries = []
        for root, dirs, files in os.walk(tools_dir):
            # 跳过 _icons 和 .bak
            dirs[:] = [d for d in dirs if d != "_icons"]
            for fname in sorted(files):
                if fname.endswith(".bak"):
                    continue
                fpath = Path(root) / fname
                rel = fpath.relative_to(tools_dir)
                size = fpath.stat().st_size
                mtime = int(fpath.stat().st_mtime)
                entries.append(f"{rel}|{size}|{mtime}")
        content = "|".join(entries)
        return hashlib.sha1(content.encode("utf-8", "ignore")).hexdigest()[:16]

    def _is_reference_path(self, path: str) -> bool:
        """判断 path 是否为"引用路径"（不应被 FTP 下载覆盖）"""
        if not path:
            return False
        p = path.strip()
        # URL
        if p.lower().startswith(("http://", "https://", "ftp://")):
            return True
        # UNC 网络路径
        if p.startswith("\\\\") or p.startswith("//"):
            return True
        # 指向 Tools 外的绝对路径（用户手动填的外部 exe）
        try:
            abs_p = Path(p).resolve()
            if abs_p.is_absolute() and not str(abs_p).startswith(str(self.tools_dir.resolve())):
                return True
        except Exception:
            pass
        return False

    def _get_ftp_settings(self) -> dict:
        """从 tool_settings 读取 FTP 配置"""
        s = tools_db.get_all_settings(self.db)
        return {
            "host": s.get("ftp_host", "").strip(),
            "port": int(s.get("ftp_port", "21") or 21),
            "user": s.get("ftp_user", "").strip(),
            "pass": _deobfuscate(s.get("ftp_pass", "")),
            "remote_path": s.get("ftp_remote_path", "/Tools").strip(),
            "enabled": s.get("ftp_enabled", "0") == "1",
        }

    def _sync_from_ftp(self, ftp_conf: dict, progress_cb=None) -> tuple[int, int]:
        """
        从 FTP 下载工具到 self.tools_dir。
        - 跳过 _icons 子目录
        - 跳过引用路径的工具（tool_items 里 path 为 URL/UNC/外部路径）
        返回 (downloaded, skipped)
        """
        try:
            import ftplib
        except ImportError:
            return 0, 0

        host = ftp_conf["host"]
        port = ftp_conf["port"]
        user = ftp_conf["user"]
        password = ftp_conf["pass"]
        remote_base = ftp_conf["remote_path"]

        downloaded = 0
        skipped = 0

        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=15)
            ftp.login(user, password)
            ftp.cwd(remote_base)
        except Exception as e:
            if progress_cb:
                progress_cb(f"FTP 连接失败: {e}")
            return 0, 0

        # 收集所有引用路径的工具（这些不下载覆盖）
        ref_paths = set()
        for tool in tools_db.list_tools(self.db, include_deleted=False):
            p = tool.get("path", "")
            if self._is_reference_path(p):
                ref_paths.add(Path(p).name.lower())

        def download_tree(remote_dir: str, local_dir: Path, depth=0):
            nonlocal downloaded, skipped
            try:
                entries = ftp.nlst(remote_dir)
            except ftplib.error_perm:
                return
            for entry in entries:
                if entry in (".", ".."):
                    continue
                if entry == "_icons":
                    continue  # 跳过图标缓存
                remote_path = f"{remote_dir}/{entry}"
                local_path = local_dir / entry
                try:
                    ftp.cwd(remote_path)
                    # 是目录
                    if not local_path.exists():
                        local_path.mkdir(parents=True)
                    download_tree(remote_path, local_path, depth + 1)
                    ftp.cwd("..")
                except ftplib.error_perm:
                    # 是文件，下载
                    fname_lower = entry.lower()
                    if fname_lower in ref_paths:
                        skipped += 1
                        continue
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with open(local_path, "wb") as f:
                            ftp.retrbinary(f"RETR {remote_path}", f.write)
                        downloaded += 1
                    except Exception:
                        pass

        download_tree(remote_base, self.tools_dir)
        ftp.quit()
        return downloaded, skipped

    def _resolve_tools_mode(self):
        """
        ★ 工具箱自检：判断使用"项目 Tools"还是"FTP 下载"
        规则：
        1. 启动时计算当前 tools_dir 的 manifest hash
        2. 与 tool_settings._tools_manifest_hash 对比：
           - 相同 → 项目内置 Tools，直接使用
           - 不同 → 用户有自定义内容或从 FTP 下载过
             → 若 FTP 已启用：自动从 FTP 下载同步
             → 若 FTP 未启用：保留现有内容（用户可能手动加了工具）
        """
        current_hash = self._compute_tools_manifest(self.tools_dir)
        stored_hash = tools_db.get_setting(self.db, "_tools_manifest_hash", "")

        # 首次：无 hash → 初始化 hash 并记录项目内置状态
        if not stored_hash:
            tools_db.set_setting(self.db, "_tools_manifest_hash", current_hash)
            return  # 首次使用，直接用项目 Tools

        if current_hash == stored_hash:
            # hash 相同：项目内置 Tools，不动
            return

        # hash 不同：内容被改过
        ftp = self._get_ftp_settings()
        if ftp["enabled"] and ftp["host"]:
            # FTP 模式：从 FTP 同步
            def log(msg):
                print(f"[FTP Sync] {msg}")
            downloaded, skipped = self._sync_from_ftp(ftp, progress_cb=log)
            if downloaded > 0 or skipped > 0:
                print(f"[FTP Sync] 完成: 下载 {downloaded} 个，跳过引用路径 {skipped} 个")
            else:
                print("[FTP Sync] FTP 连接失败或无可用文件，保留现有 tools_dir 内容")
        else:
            # 无 FTP：用户手动加了工具，保留
            print("[Tools Self-Check] 检测到自定义内容（hash 变化），保留现有 Tools（无 FTP 配置）")

    # ------------------------------------------------------------------
    # 设置加载
    # ------------------------------------------------------------------

    def _load_settings(self):
        """从 DB 加载路径/包等设置
        ★ tools_dir 多级 fallback：
           1) DB 设置的路径（存在则用）
           2) project_root/Tools（开发模式默认）
           3) exe 同级 Tools（打包模式默认）
           4) exe 同级上层/Tools（坚果云同步场景）"""
        s = tools_db.get_all_settings(self.db)
        tools_dir_str = s.get("tools_dir", "").strip()
        candidates = []
        if tools_dir_str:
            candidates.append(Path(tools_dir_str))
        candidates.append(self.project_root / "Tools")
        # 打包场景：exe 同级、exe 同级的上层 ../Tools
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / "Tools")
            candidates.append(exe_dir.parent / "Tools")
        self.tools_dir = next((p for p in candidates if p.exists()), candidates[0])
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        # ★ 记录解析结果到日志，便于调试
        # print(f"[tools_dir] resolved to: {self.tools_dir}")

        self.use_relative_path = s.get("use_relative_path", "1") == "1"
        self.default_run_mode = s.get("default_run_mode", "normal")
        try:
            self.icon_size = int(s.get("icon_size", "48"))
        except ValueError:
            self.icon_size = 48
        try:
            self.grid_cols = int(s.get("grid_cols", "6"))
        except ValueError:
            self.grid_cols = 6

        # 加载包
        pkgs = tools_db.list_packages(self.db)
        self.packages = [p["name"] for p in pkgs]
        if not self.packages:
            self.packages = ["个人系统"]

    def _save_settings(self, **kwargs):
        for k, v in kwargs.items():
            tools_db.set_setting(self.db, k, str(v))
        self._load_settings()

    # ------------------------------------------------------------------
    # DB 初始化
    # ------------------------------------------------------------------

    def _init_db(self):
        tools_db.init_all_tool_tables(self.db)

    # ------------------------------------------------------------------
    # UI 布局
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_top_bar()
        self._build_category_bar()
        self._build_main_area()
        # ★ 整个页面注册为 drop target（拖入 .exe 即可快速添加）
        self._register_drop_target(self)

    def _build_top_bar(self):
        """顶部工具栏 — 黑白极简风格，紧凑布局"""
        # 主容器：白色背景
        top = tk.Frame(self, bg=COLOR_BG, padx=12, pady=8)
        top.pack(fill="x")

        # 左侧组：包选择 + 搜索
        left_group = tk.Frame(top, bg=COLOR_BG)
        left_group.pack(side="left", fill="y")

        # 包选择行
        pkg_row = tk.Frame(left_group, bg=COLOR_BG)
        pkg_row.pack(fill="x", pady=(0, 6))

        tk.Label(pkg_row, text="包", bg=COLOR_BG, fg=COLOR_TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left", padx=(0, 6))

        self.package_var = tk.StringVar(value=self.current_package)
        self.package_combo = ttk.Combobox(pkg_row, textvariable=self.package_var,
                                          width=16, values=self.packages, state="readonly")
        self.package_combo.pack(side="left", padx=(0, 4))
        self.package_combo.bind("<<ComboboxSelected>>", lambda e: self._on_package_change())

        # 包色块（小圆点）
        self._package_swatch = tk.Frame(pkg_row, width=12, height=12, bg=COLOR_MUTED,
                                         highlightthickness=1, highlightbackground=COLOR_BORDER_LIGHT)
        self._package_swatch.pack(side="left", padx=(4, 0))
        self._package_swatch.bind("<Button-1>", lambda e: self._on_package_swatch_click())

        # 编辑按钮（小）
        self._btn_edit_pkg = self._create_tool_btn(pkg_row, "✎", self._show_package_manager, width=2)
        self._btn_edit_pkg.pack(side="left", padx=(4, 0))

        # 搜索行
        search_row = tk.Frame(left_group, bg=COLOR_BG)
        search_row.pack(fill="x")

        tk.Label(search_row, text="搜索", bg=COLOR_BG, fg=COLOR_TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left", padx=(0, 6))

        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_row, textvariable=self.search_var, width=30,
                                bg=COLOR_BG, fg=COLOR_TEXT, relief="solid",
                                highlightthickness=1, highlightbackground=COLOR_BORDER_LIGHT)
        search_entry.pack(side="left", padx=(0, 4))
        self.search_var.trace_add("write", lambda *_: self._refresh_grid())

        self._btn_search = self._create_tool_btn(search_row, "🔍", lambda: None, width=2)
        self._btn_search.pack(side="left", padx=(0, 12))

        # 右侧组：工具按钮（紧凑排列）
        right_group = tk.Frame(top, bg=COLOR_BG)
        right_group.pack(side="right", fill="y")

        btn_specs = [
            ("+ 添加", self._show_add_dialog),
            ("⟳ 扫描", self._initial_scan),
            ("🧹 清空无效", self._clean_invalid_tools),
            ("📁 目录", self._open_tools_folder),
            ("⚙ 设置", self._show_settings),
        ]
        for text, cmd in btn_specs:
            btn = self._create_tool_btn(right_group, text, cmd)
            btn.pack(side="left", padx=(0, 6))

    def _create_tool_btn(self, parent, text, command, width=None):
        """创建统一风格的工具按钮 — 白色底、淡灰边框、黑色文字"""
        btn = tk.Label(parent, text=text, bg=COLOR_BG, fg=COLOR_TEXT,
                       font=("Microsoft YaHei", 9),
                       padx=8 if width is None else 4, pady=3,
                       relief="raised", bd=1,
                       highlightthickness=1, highlightbackground=COLOR_BORDER_LIGHT,
                       cursor="hand2")
        if width:
            btn.configure(width=width)
        # ★ 修复：点击时凹陷，释放时执行命令+恢复，避免阻塞导致按钮卡住
        btn.bind("<Button-1>", lambda e: btn.configure(relief="sunken"))
        btn.bind("<ButtonRelease-1>", lambda e: (btn.configure(relief="raised"), command()))
        # 悬停效果
        btn.bind("<Enter>", lambda e: btn.configure(bg="#f5f5f5"))
        btn.bind("<Leave>", lambda e: btn.configure(bg=COLOR_BG))
        return btn

    def _build_category_bar(self):
        """分类栏 — 黑白极简风格，支持横向滚动"""
        cat_frame = tk.Frame(self, bg=COLOR_BG, padx=12, pady=6)
        cat_frame.pack(fill="x")

        tk.Label(cat_frame, text="分类", bg=COLOR_BG, fg=COLOR_TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left", padx=(0, 8))

        # ★ 分类按钮容器改为 Canvas + 横向滚动
        self._cat_canvas = tk.Canvas(cat_frame, bg=COLOR_BG, highlightthickness=0, height=28)
        self._cat_canvas.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # 滚动条（需要时才显示）
        self._cat_scroll = tk.Scrollbar(cat_frame, orient="horizontal", command=self._cat_canvas.xview,
                                         bg=COLOR_BG, troughcolor=COLOR_BG,
                                         highlightthickness=0, bd=0)
        self._cat_scroll.pack(side="bottom", fill="x")
        self._cat_canvas.configure(xscrollcommand=self._cat_scroll.set)

        # 内部 Frame 放按钮
        self.category_container = tk.Frame(self._cat_canvas, bg=COLOR_BG)
        self._cat_canvas.create_window((0, 0), window=self.category_container, anchor="nw")
        self.category_container.bind("<Configure>", lambda e: self._cat_canvas.configure(scrollregion=self._cat_canvas.bbox("all")))

        # + 分类按钮（小尺寸）
        add_cat_btn = self._create_tool_btn(cat_frame, "+", self._add_category_dialog, width=2)
        add_cat_btn.pack(side="right")

        self.category_buttons: list[tk.Label] = []

    def _build_main_area(self):
        """中间：左网格 + 中折叠按钮 + 右编辑（默认折叠 + 可展开）"""
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self._main_body = body

        body.rowconfigure(0, weight=1)
        # ★ 默认：col 0 填满，col 2 隐藏
        body.columnconfigure(0, weight=1, minsize=300)
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=0, minsize=0)

        # 左：网格容器（canvas+scrollbar）
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 2))

        # 中：折叠按钮
        self.toggle_btn = ttk.Button(
            body, text="▶", width=2,
            command=self._toggle_right_panel
        )
        self.toggle_btn.grid(row=0, column=1, sticky="ns", padx=2)

        # 右：编辑面板（默认隐藏）— 加滚动条以防内容超出
        right_container = ttk.Frame(body)
        self._right_container = right_container
        self._right_canvas = tk.Canvas(right_container, bg=COLOR_BG, highlightthickness=0)
        self._right_scroll = ttk.Scrollbar(right_container, orient="vertical",
                                            command=self._right_canvas.yview)
        self._right_canvas.configure(yscrollcommand=self._right_scroll.set)
        self._right_canvas.pack(side="left", fill="both", expand=True)
        self._right_scroll.pack(side="right", fill="y")
        # 内部 Frame 承载所有编辑控件
        self.right_panel = ttk.Frame(self._right_canvas, padding=8)
        self._right_window = self._right_canvas.create_window((0, 0), window=self.right_panel, anchor="nw")
        self.right_panel.bind("<Configure>",
                               lambda e: self._right_canvas.configure(scrollregion=self._right_canvas.bbox("all")))
        self._right_canvas.bind("<Configure>",
                                 lambda e: self._right_canvas.itemconfigure(self._right_window, width=e.width))
        # 鼠标滚轮
        self._right_canvas.bind("<Enter>", lambda e: self._right_canvas.bind_all("<MouseWheel>",
                                        lambda ev: self._right_canvas.yview_scroll(int(-1*(ev.delta/120)), "units")))
        self._right_canvas.bind("<Leave>", lambda e: self._right_canvas.unbind_all("<MouseWheel>"))
        self._right_visible = False
        self._right_default_width = 320

        canvas_frame = ttk.Frame(left)
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg=COLOR_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical",
                                        command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # ★ view_bar：上下滚动按钮（绑定 canvas 垂直滚动）
        view_bar = ttk.Frame(left)
        view_bar.place(relx=1.0, x=-36, y=4, anchor="ne")
        self.scroll_up_btn = ttk.Button(view_bar, text="▲", width=2,
                                        command=lambda: self.canvas.yview_scroll(-5, "units"))
        self.scroll_up_btn.pack(side="top", pady=(0, 2))
        self.scroll_down_btn = ttk.Button(view_bar, text="▼", width=2,
                                          command=lambda: self.canvas.yview_scroll(5, "units"))
        self.scroll_down_btn.pack(side="top")

        # 列表视图（隐藏）
        self.list_frame = ttk.Frame(canvas_frame)

        # 图标视图容器
        self.grid_frame = ttk.Frame(self.canvas, padding=8)
        self.canvas_window = self.canvas.create_window(0, 0, window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>",
                              lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        # ★ 图标面板空白处右键
        self.grid_frame.bind("<Button-3>", self._on_panel_right_click)
        self.canvas.bind("<Button-3>", lambda e: self._on_panel_right_click(e)
                         if e.widget == self.canvas else None)
        self.canvas.bind("<Configure>",
                          lambda e: (self.canvas.itemconfigure(self.canvas_window, width=e.width),
                                     self.after(0, self._update_scroll_btns)))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        # ★ 支持拖入 .exe（tkdnd）
        if HAS_TKDND and DND_FILES:
            try:
                self.canvas.drop_target_register(DND_FILES)
                self.canvas.dnd_bind("<<Drop>>", self._on_drop_files)
            except Exception:
                pass

    def _build_edit_panel(self, parent):
        """右侧编辑面板（首次展开时调用）"""
        ttk.Label(parent, text="工具详情", font=("", 11, "bold")).pack(anchor="w", pady=(0, 6))

        # 图标预览
        icon_frame = ttk.Frame(parent)
        icon_frame.pack(fill="x", pady=(0, 8))
        self.icon_preview_label = tk.Label(icon_frame, text="(无)", bg=COLOR_CARD,
                                            relief="solid", width=8, height=4)
        self.icon_preview_label.pack(side="left", padx=(0, 8))
        ttk.Button(icon_frame, text="抽图标",
                   command=self._extract_icon_for_selected, width=10).pack(side="left", pady=4)
        ttk.Button(icon_frame, text="选择...",
                   command=self._change_icon, width=10).pack(side="left", padx=(4, 0), pady=4)

        ttk.Label(parent, text="名称:").pack(anchor="w")
        self.edit_name_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.edit_name_var).pack(fill="x", pady=(0, 6))

        ttk.Label(parent, text="别称:").pack(anchor="w")
        self.edit_alias_var = tk.StringVar()
        alias_entry = ttk.Entry(parent, textvariable=self.edit_alias_var)
        alias_entry.pack(fill="x", pady=(0, 6))
        ttk.Label(parent, text='（可选，如 "F0"、"FF" 等简称，显示在名称下方）',
                  foreground=COLOR_MUTED, font=("", 8)).pack(anchor="w", pady=(0, 8))

        ttk.Label(parent, text="路径(相对 Tools):").pack(anchor="w")
        path_frame = ttk.Frame(parent)
        path_frame.pack(fill="x", pady=(0, 2))
        self.edit_path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self.edit_path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(path_frame, text="...", width=4,
                   command=self._browse_path).pack(side="left", padx=(2, 0))
        self.edit_path_display = ttk.Label(parent, text="", foreground=COLOR_MUTED, font=("", 8))
        self.edit_path_display.pack(anchor="w", pady=(0, 6))

        ttk.Label(parent, text="参数:").pack(anchor="w")
        self.edit_args_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.edit_args_var).pack(fill="x", pady=(0, 6))

        ttk.Label(parent, text="分类:").pack(anchor="w")
        self.edit_category_var = tk.StringVar()
        self.edit_category_combo = ttk.Combobox(parent, textvariable=self.edit_category_var)
        self.edit_category_combo.pack(fill="x", pady=(0, 6))

        self.edit_admin_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="以管理员身份运行",
                        variable=self.edit_admin_var).pack(anchor="w", pady=(0, 6))

        ttk.Label(parent, text="描述:").pack(anchor="w")
        self.edit_desc_text = tk.Text(parent, height=4, wrap="word")
        self.edit_desc_text.pack(fill="x", pady=(0, 8))

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="▶ 运行",
                   command=self._run_selected_tool).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="💾 保存",
                   command=self._save_selected_tool).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="📌 收藏/取消",
                   command=self._toggle_favorite).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="🗑 删除",
                   command=self._delete_selected_tool).pack(fill="x", pady=2)

    def _toggle_right_panel(self):
        """右侧编辑面板折叠/展开（默认折叠）"""
        if not self._right_visible:
            # 展开
            if not self.right_panel.winfo_children():
                self._build_edit_panel(self.right_panel)
            self._right_container.grid(row=0, column=2, sticky="nsew", padx=(2, 0))
            self._main_body.columnconfigure(0, weight=3)
            self._main_body.columnconfigure(2, minsize=self._right_default_width, weight=1)
            self.toggle_btn.configure(text="◀")
            self._right_visible = True
        else:
            # 折叠：col 0 占满，col 2 完全收起
            self._right_container.grid_forget()
            self._main_body.columnconfigure(0, weight=1, minsize=300)
            self._main_body.columnconfigure(2, minsize=0, weight=0)
            self.toggle_btn.configure(text="▶")
            self._right_visible = False
            if self.selected_tool_id and self.selected_tool_id in self.icon_widgets:
                self.icon_widgets[self.selected_tool_id].configure(
                    highlightbackground=COLOR_BORDER, highlightthickness=1)
            self.selected_tool_id = None

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def _initial_scan(self):
        """扫描 Tools 文件夹并入库。★ 分类=子文件夹名，自动建分类。
        ★ 去重：同一真实文件只入库一次（归一化绝对路径后比较）"""
        scanned = tools_db.scan_tools_folder(self.tools_dir)
        # ★ 收集所有需要创建的分类
        existing_cats = {c["name"] for c in tools_db.list_categories(self.db)}
        new_cats_needed = set()
        for tool in scanned:
            if tool["category"] not in existing_cats and tool["category"] != "未分类":
                new_cats_needed.add(tool["category"])
        for cat in new_cats_needed:
            try:
                tools_db.add_category(self.db, cat)
                self.tools_dir.joinpath(cat).mkdir(exist_ok=True)
            except Exception:
                pass
        # ★ 归一化去重：同一文件在多个路径下出现只入库一次
        seen_norm: set[str] = set()
        added = 0
        for tool in scanned:
            if not Path(tool["path"]).exists():
                continue
            norm = os.path.normcase(os.path.abspath(str(tool["path"])))
            if norm in seen_norm:
                continue
            seen_norm.add(norm)
            # ★ 优先用相对路径存储（如果文件在 tools_dir 下）
            try:
                rel = str(Path(tool["path"]).resolve().relative_to(self.tools_dir.resolve())).replace("\\", "/")
                store_path = rel
            except ValueError:
                store_path = tool["path"]
            tools_db.upsert_tool_by_path(
                self.db, path=store_path, name=tool["name"],
                category=tool["category"]
            )
            added += 1
        if added:
            self._refresh_all()

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------

    def _refresh_all(self):
        self._refresh_categories()
        self._refresh_grid()
        if hasattr(self, "list_tree"):
            self._refresh_list()

    # ★ _switch_view 已移除（列表视图功能保留，暂未绑定触发）

    def _build_list_view(self):
        """构建列表视图 Treeview"""
        self.list_scrollbar = ttk.Scrollbar(self.canvas.master, orient="vertical")
        cols = ("name", "category", "path", "admin")
        self.list_tree = ttk.Treeview(self.canvas.master, columns=cols,
                                       show="headings", yscrollcommand=self.list_scrollbar.set)
        self.list_scrollbar.configure(command=self.list_tree.yview)
        self.list_tree.heading("name", text="名称")
        self.list_tree.heading("category", text="分类")
        self.list_tree.heading("path", text="路径")
        self.list_tree.heading("admin", text="管理员")
        self.list_tree.column("name", width=160, anchor="w")
        self.list_tree.column("category", width=100, anchor="w")
        self.list_tree.column("path", width=300, anchor="w")
        self.list_tree.column("admin", width=60, anchor="center")
        # 绑定
        self.list_tree.bind("<<TreeviewSelect>>", self._on_list_select)
        self.list_tree.bind("<Double-Button-1>", self._on_list_double)
        self.list_tree.bind("<Button-3>", self._on_list_right_click)

    def _refresh_list(self):
        """刷新列表视图"""
        if not hasattr(self, "list_tree"):
            return
        for iid in self.list_tree.get_children():
            self.list_tree.delete(iid)
        keyword = self.search_var.get().strip()
        tools = tools_db.list_tools(self.db, category=self.current_category, keyword=keyword)
        for t in tools:
            self.list_tree.insert("", "end", iid=str(t["id"]),
                                   values=(t["name"], t["category"] or "", t["path"],
                                            "是" if t["run_as_admin"] else ""))

    def _on_list_select(self, _event):
        sel = self.list_tree.selection()
        if sel:
            self._select_tool(int(sel[0]))

    def _on_list_double(self, _event):
        sel = self.list_tree.selection()
        if sel:
            self._run_tool_by_id(int(sel[0]))

    def _on_list_right_click(self, event):
        sel = self.list_tree.identify_row(event.y)
        if sel:
            self.list_tree.selection_set(sel)
            self._on_list_select(None)
            self._show_tool_menu(event, int(sel))

    def _on_drop_files(self, event, prefill_category: str = ""):
        """拖入 .exe / 目录文件（tkdnd）
        ★ 打开 AddToolDialog 预填 name + path（不直接入库）
        ★ prefill_category：拖入指定分类按钮时，强制预填该分类"""
        files = self.tk.splitlist(event.data)
        if not files:
            return
        default_cat = prefill_category or (self.current_category if self.current_category != "全部" else "")
        # 解析第一个有效文件作为预填路径
        prefill_path = ""
        for raw in files:
            path = raw.strip("{}").strip()
            if not path or not Path(path).exists():
                continue
            p = Path(path)
            if p.is_dir():
                # 目录：取第一个 .exe
                exes = list(p.rglob("*.exe"))
                if exes:
                    prefill_path = str(exes[0])
                    break
            else:
                prefill_path = str(p)
                break
        if not prefill_path:
            return
        # 预填名称 = 文件名（去后缀）
        prefill_name = Path(prefill_path).stem
        # 打开 AddToolDialog
        dialog = AddToolDialog(self, self.db, self.tools_dir, self.use_relative_path,
                                prefill_name=prefill_name, prefill_path=prefill_path,
                                prefill_category=default_cat)
        self.wait_window(dialog)
        if dialog.result:
            if dialog.added_category and dialog.added_category != self.current_category:
                self.current_category = dialog.added_category
            self._refresh_all()
            if dialog.added_tool_id:
                self._select_tool(dialog.added_tool_id)

    def _add_one_tool(self, p: Path, category: str):
        """内部：添加一个工具（含去重 + 物理拷贝到分类文件夹）
        ★ 分类=子文件夹：拷贝到 Tools/<category>/<name>.exe"""
        if category not in {"全部"} and category:
            cat_dir = self.tools_dir / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            target = cat_dir / p.name
            try:
                import shutil
                if Path(p).resolve() != target.resolve():
                    shutil.copy2(str(p), str(target))
            except Exception as e:
                messagebox.showerror("错误", f"拷贝文件失败：\n{e}", parent=self)
                return
            store_path = f"{category}/{p.name}"
        else:
            try:
                store_path = str(p.relative_to(self.tools_dir)).replace("\\", "/")
            except ValueError:
                store_path = str(p)
        # 去重（按绝对路径比较）
        existing = self.db.execute(
            "SELECT id, category FROM tool_items WHERE is_deleted=0 AND path = ?", (store_path,)
        ).fetchone()
        if existing:
            return
        # 分类不存在则创建
        if category and category != "未分类":
            existing_cats = {c["name"] for c in tools_db.list_categories(self.db)}
            if category not in existing_cats:
                tools_db.add_category(self.db, category)
        tools_db.add_tool(self.db, name=p.stem, path=store_path, category=category or "未分类")

    def _refresh_categories(self):
        """重绘分类按钮 + 右键菜单（仅显示当前包下的分类）— 黑白极简风格"""
        for btn in self.category_buttons:
            btn.destroy()
        self.category_buttons.clear()

        # ★ 只取当前包下的分类（包→分类 联动）
        categories = tools_db.list_categories(self.db, package=self.current_package)

        for cat in categories:
            # 使用自定义样式按钮
            btn = tk.Label(self.category_container, text=cat["name"],
                           bg=COLOR_BG, fg=COLOR_TEXT,
                           font=("Microsoft YaHei", 9),
                           padx=10, pady=2,
                           relief="raised", bd=1,
                           highlightthickness=1, highlightbackground=COLOR_BORDER_LIGHT,
                           cursor="hand2")
            btn.pack(side="left", padx=(0, 6), pady=1)

            # 点击切换分类
            btn.bind("<Button-1>", lambda e, n=cat["name"]: self._switch_category(n))
            btn.bind("<Button-3>", lambda e, cid=cat["id"], n=cat["name"]: self._show_category_menu(e, cid, n))

            # 悬停效果
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#f5f5f5"))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=COLOR_BG))

            # 选中状态（当前分类）
            if cat["name"] == self.current_category:
                btn.configure(relief="sunken", bg="#e8e8e8")

            # ★ 拖入支持
            self._make_category_drop_target(btn, cat["id"], cat["name"])
            self.category_buttons.append(btn)

        # 同步到编辑区下拉
        if hasattr(self, "edit_category_combo"):
            self.edit_category_combo["values"] = [c["name"] for c in categories]
        # 同步到包下拉
        self._refresh_package_combo()

    def _refresh_package_combo(self):
        pkgs = tools_db.list_packages(self.db)
        self.packages = [p["name"] for p in pkgs]
        self.package_combo["values"] = self.packages
        if self.current_package not in self.packages and self.packages:
            self.current_package = self.packages[0]
            self.package_var.set(self.current_package)

    def _get_current_package_color(self) -> str:
        """取当前包的标识色（默认灰）。"""
        pkg = tools_db.get_package_by_name(self.db, self.current_package)
        if pkg and pkg.get("accent_color"):
            return pkg["accent_color"]
        return "#6b7280"

    def _refresh_package_swatch(self):
        """刷新顶部包标识色块。"""
        if not hasattr(self, "_package_swatch"):
            return
        color = self._get_current_package_color()
        try:
            self._package_swatch.configure(bg=color)
        except Exception:
            pass

    def _on_package_change(self):
        """切换包 → 重新过滤分类栏 + 工具列表。包→分类→工具 三级联动。"""
        new_pkg = self.package_var.get()
        if new_pkg == self.current_package:
            return
        self.current_package = new_pkg
        # 切包后重置为"全部"分类（当前分类可能不包下）
        self.current_category = "全部"
        # ★ 刷新顶部色块（让你一眼看出当前是哪个套件）
        self._refresh_package_swatch()
        # ★ 1. 刷新分类栏（只显示该包下的分类）
        self._refresh_categories()
        # ★ 2. 刷新工具列表（间接通过 package 过滤）
        self._refresh_grid()

    def _on_package_swatch_click(self):
        """点击顶部包标识色块 → 9 色选择。"""
        if self.current_package == "常用工具":
            messagebox.showinfo("提示", "“常用工具”是伪包，不能设置标识色。", parent=self)
            return
        dlg = _ColorPickerDialog(self, current_color=self._get_current_package_color())
        self.wait_window(dlg)
        if dlg.result:
            try:
                pkg = tools_db.get_package_by_name(self.db, self.current_package)
                if pkg:
                    tools_db.update_package(self.db, pkg["id"], None,
                                            accent_color=dlg.result)
                    self._refresh_package_swatch()
                    self._refresh_grid()
            except Exception as e:
                logger.exception("set package color failed: %s", e)
                messagebox.showerror("错误", f"设置失败：{e}", parent=self)

    def _switch_category(self, name: str):
        self.current_category = name
        # ★ 修复：tk.Label 没有 state 方法，直接改 relief
        for btn in self.category_buttons:
            btn.configure(relief="raised", bg=COLOR_BG)
        for btn in self.category_buttons:
            if btn.cget("text") == name:
                btn.configure(relief="sunken", bg="#e8e8e8")
        self._refresh_grid()

    def _refresh_grid(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.icon_widgets = {}
        # ★ 同步顶部色块（包切换、设置色后与卡片色条同步）
        self._refresh_package_swatch()

        keyword = self.search_var.get().strip()
        sort_key = tools_db.get_setting(self.db, "sort_key", "")
        tools = tools_db.list_tools(self.db, category=self.current_category, keyword=keyword,
                                    sort_key=sort_key, package=self.current_package)
        if not tools:
            ttk.Label(self.grid_frame,
                      text="(空) 把 .exe 拖入 Tools 文件夹，或点击 ➕ 添加工具",
                      foreground=COLOR_MUTED).pack(pady=40)
            self.after(0, self._update_scroll_btns)
            return

        cols = self.grid_cols
        for i, tool in enumerate(tools):
            row, col = divmod(i, cols)
            self._create_icon_card(self.grid_frame, tool, row, col)
        # ★ 布局完后再判断是否需要显示滚动按钮
        self.after(0, self._update_scroll_btns)

    def _update_scroll_btns(self):
        """根据内容溢出决定上下滚动按钮是否显示。
        溢出：内容高度 > 可见区域 → 显示
        未溢出：图标已铺满 → 隐藏（避免空跑）"""
        try:
            self.canvas.update_idletasks()
            bbox = self.canvas.bbox("all")
            if not bbox:
                return
            content_h = bbox[3] - bbox[1]
            view_h = self.canvas.winfo_height()
            need_scroll = content_h > view_h
        except Exception:
            need_scroll = False
        if hasattr(self, 'scroll_up_btn'):
            if need_scroll:
                try:
                    self.scroll_up_btn.master.place(relx=1.0, x=-36, y=4, anchor="ne")
                except tk.TclError:
                    pass
            else:
                try:
                    self.scroll_up_btn.master.place_forget()
                except tk.TclError:
                    pass

    def _create_icon_card(self, parent, tool: dict, row: int, col: int):
        # ★ 卡片尺寸 = icon_size + padding，扁平化圆角风格
        card_w = self.icon_size + 16
        card_h = self.icon_size + 44  # 图标区 + 名字区 + 间距
        tool_id = tool["id"]

        # 卡片容器：纯白背景，无边框，悬停效果
        card = tk.Frame(parent, bg=COLOR_BG, relief="flat", bd=0,
                         width=card_w, height=card_h)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        card.grid_propagate(False)

        # 图标
        # ★ 图标 Label 固定尺寸，防止图片过大撑破卡片
        icon_label = tk.Label(card, bg=COLOR_BG, cursor="hand2")
        self._load_tool_icon(tool, icon_label)
        icon_label.pack(pady=(6, 2))

        # 名称
        name_label = tk.Label(card, text=tool["name"], bg=COLOR_BG,
                               fg=COLOR_TEXT, font=("", 9),
                               wraplength=88, justify="center", cursor="hand2")
        name_label.pack(pady=(0, 4), padx=2)

        self.icon_widgets[tool_id] = card
        # ★ 同时存储子 widget 用于 hover 同步
        if not hasattr(self, 'icon_subwidgets'):
            self.icon_subwidgets = {}
        self.icon_subwidgets[tool_id] = (icon_label, name_label)

        for widget in (card, icon_label, name_label):
            widget.bind("<Button-1>",
                        lambda e, tid=tool_id: self._on_card_press(e, tid))
            widget.bind("<Double-Button-1>",
                        lambda e, tid=tool_id: self._run_tool_by_id(tid))
            widget.bind("<Button-3>",
                        lambda e, tid=tool_id: self._show_tool_menu(e, tid))
            widget.bind("<Enter>",
                        lambda e, w=card, tid=tool_id: self._on_card_hover(w, True, tid))
            widget.bind("<Leave>",
                        lambda e, w=card, tid=tool_id: self._on_card_hover(w, False, tid))

    def _get_icon_cache_path(self, exe_path: str, size: int) -> Path:
        """生成图标缓存路径。基于 exe 文件名 + 文件 hash（mtime+size）+ 尺寸。"""
        import hashlib
        exe = Path(exe_path)
        if not exe.exists():
            return self.tools_dir / "_图标" / f"{exe.stem}_unknown_{size}.png"
        stat = exe.stat()
        file_hash = hashlib.md5(f"{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()[:8]
        return self.tools_dir / "_图标" / f"{exe.stem}_{file_hash}_{size}.png"

    def _async_extract_icon(self, tool: dict, label: tk.Label):
        """异步抽取图标：
        1) 同步抽（ctypes 方案，<1秒），但在 UI 空闲后执行
        2) 抽成功后更新 DB + 刷新该 label
        """
        if not label.winfo_exists():
            return
        try:
            exe_path = tool.get("path", "")
            if not exe_path:
                return
            if not Path(exe_path).is_absolute():
                exe_path = str(self.tools_dir / exe_path)
            if not Path(exe_path).exists() or Path(exe_path).suffix.lower() != ".exe":
                return
            out_png = self.tools_dir / "_icons" / f"tool{tool['id']}.png"
            cache_dir = self.tools_dir / "_图标"
            if extract_exe_icon(exe_path, str(out_png), size=self.icon_size, cache_dir=cache_dir):
                if tool.get("id"):
                    try:
                        tools_db.update_tool(self.db, tool["id"], icon_path=str(out_png))
                    except Exception:
                        pass
                # ★ 清除缓存让新图标生效
                self.icon_cache.clear()
                # ★ 刷新该 label
                if label.winfo_exists():
                    self._load_tool_icon(tool, label)
        except Exception:
            pass

    def _load_tool_icon(self, tool: dict, label: tk.Label):
        """加载工具图标：
        1) 优先用数据库 icon_path（绝对路径直接用，相对路径基于 tools_dir）
        2) 缺失则从 _图标/ 缓存查找（按 exe hash）
        3) ★ 都没有则同步抽取一次（ctypes 方案，<1秒；仅 .exe）
        4) 全部失败才显示占位
        """
        icon_path = (tool.get("icon_path") or "").strip()

        # ★ 路径解析：相对路径转为基于 tools_dir 的绝对路径
        if icon_path:
            p = Path(icon_path)
            if not p.is_absolute():
                p = self.tools_dir / icon_path
            icon_path = str(p)

        # ★ 数据库路径不存在 → 从缓存目录查找
        if not icon_path or not Path(icon_path).exists():
            exe_path = tool.get("path", "")
            if exe_path:
                if not Path(exe_path).is_absolute():
                    exe_path = str(self.tools_dir / exe_path)
                cache_path = self._get_icon_cache_path(exe_path, self.icon_size)
                if cache_path.exists() and cache_path.stat().st_size > 0:
                    icon_path = str(cache_path)
                    # ★ 顺手修复 DB：写回绝对路径，下次不再走兑底
                    if tool.get("id"):
                        try:
                            tools_db.update_tool(self.db, tool["id"], icon_path=icon_path)
                        except Exception:
                            pass

        # ★ 依然没有图标 → 尝试同步抽取一次（仅 .exe，ctypes 方案 <1秒）
        if not icon_path or not Path(icon_path).exists():
            exe_path = tool.get("path", "")
            if exe_path:
                if not Path(exe_path).is_absolute():
                    exe_path = str(self.tools_dir / exe_path)
                exe_p = Path(exe_path)
                if exe_p.exists() and exe_p.suffix.lower() == ".exe":
                    # ★ 延迟 100ms 后异步抽取（不影响初始渲染）
                    label.after(100, lambda t=tool, l=label: self._async_extract_icon(t, l))

        # 没有图标 → 显示占位
        if not icon_path or not Path(icon_path).exists():
            label.configure(text="⚙", font=("Segoe UI Emoji", 22), image="")
            return

        # 加载缓存（Windows 原生风格：透明背景、保持比例）
        cache_key = f"{icon_path}_native_{self.icon_size}"
        if cache_key in self.icon_cache:
            img = self.icon_cache[cache_key]
        else:
            img = None
            if HAS_PIL:
                try:
                    pil = Image.open(icon_path)
                    # ★ Windows 原生图标风格（透明背景、保持比例）
                    pil = _make_native_icon(pil, self.icon_size)
                    img = ImageTk.PhotoImage(pil)
                except Exception:
                    img = None
            self.icon_cache[cache_key] = img

        if img:
            label.configure(image=img, text="")
            label.image = img
        else:
            label.configure(text="⚙", font=("Segoe UI Emoji", 22), image="")

    # ★ 快速启动栏已移除

    # ------------------------------------------------------------------
    # 选中 / 编辑
    # ------------------------------------------------------------------

    def _on_card_press(self, event, tool_id: int):
        """单击：选中 + 记录拖拽起点。拖拽+松开不发起选中在 _on_drag_release。"""
        self._select_tool(tool_id)
        self._drag_data = {
            "tool_id": tool_id, "from_toolbar": False, "widget": event.widget,
            "x": event.x_root, "y": event.y_root
        }

    def _on_card_hover(self, card, hover: bool, tool_id: int):
        # 选中态优先于 hover
        if self.selected_tool_id == tool_id:
            return
        if hover:
            # hover：加深背景色 + 加粗边框（不改变盒子大小/不调整 padding）
            card.configure(bg=COLOR_DROP_HOVER,
                           highlightbackground=COLOR_ACCENT,
                           highlightthickness=2)
            # ★ 同步子 widget 背景色（跳过 accent_bar，保留色钆）
            if hasattr(self, 'icon_subwidgets') and tool_id in self.icon_subwidgets:
                for w in self.icon_subwidgets[tool_id][:2]:
                    w.configure(bg=COLOR_DROP_HOVER)
        else:
            card.configure(bg=COLOR_BG,
                           highlightbackground=COLOR_BORDER,
                           highlightthickness=1)
            if hasattr(self, 'icon_subwidgets') and tool_id in self.icon_subwidgets:
                for w in self.icon_subwidgets[tool_id][:2]:
                    w.configure(bg=COLOR_BG)

    def _select_tool(self, tool_id: int):
        # ★ 选中时自动展开右栏
        if not self._right_visible:
            self._toggle_right_panel()
        # ★ 先清除旧的选中态
        if self.selected_tool_id and self.selected_tool_id in self.icon_widgets:
            old = self.icon_widgets[self.selected_tool_id]
            old.configure(highlightbackground=COLOR_BORDER, highlightthickness=1)

        self.selected_tool_id = tool_id
        tool = tools_db.get_tool(self.db, tool_id)
        if not tool:
            return
        # ★ 应用新的选中态
        if tool_id in self.icon_widgets:
            new = self.icon_widgets[tool_id]
            new.configure(highlightbackground=COLOR_PRIMARY, highlightthickness=2)

        self.edit_name_var.set(tool["name"])
        self.edit_alias_var.set(tool.get("alias") or "")
        path = tool["path"]
        if not Path(path).is_absolute():
            path = str((self.tools_dir / path).resolve())
        self.edit_path_var.set(path)
        self.edit_args_var.set(tool["args"] or "")
        self.edit_category_var.set(tool["category"] or "未分类")
        self.edit_admin_var.set(bool(tool["run_as_admin"]))
        self.edit_desc_text.delete("1.0", "end")
        self.edit_desc_text.insert("1.0", tool["description"] or "")

        if tool.get("icon_path") and Path(tool["icon_path"]).exists():
            self._set_preview_icon(tool["icon_path"])
        else:
            self.icon_preview_label.configure(text="(无)", image="")

        try:
            rel = Path(tool["path"])
            if rel.is_absolute():
                rel = rel.relative_to(self.tools_dir)
            self.edit_path_display.configure(text=f"→ 相对 Tools: {rel}")
        except ValueError:
            self.edit_path_display.configure(text="→ 不在 Tools 目录内（绝对路径）")

    def _set_preview_icon(self, icon_path: str):
        if not HAS_PIL or not Path(icon_path).exists():
            return
        try:
            pil = Image.open(icon_path)
            pil = pil.resize((64, 64), Image.LANCZOS)
            img = ImageTk.PhotoImage(pil)
            self.icon_preview_label.configure(image=img, text="")
            self.icon_preview_label.image = img
        except Exception:
            pass

    def _save_selected_tool(self):
        if not self.selected_tool_id:
            messagebox.showinfo("提示", "请先选中一个工具。", parent=self)
            return
        name = self.edit_name_var.get().strip()
        path = self.edit_path_var.get().strip()
        if not name or not path:
            messagebox.showwarning("提示", "名称和路径不能为空。", parent=self)
            return
        # 路径转相对（如果在 Tools 目录内）
        abs_path = Path(path)
        if abs_path.is_absolute() and self.use_relative_path:
            try:
                rel = abs_path.relative_to(self.tools_dir)
                store_path = str(rel).replace("\\", "/")
            except ValueError:
                store_path = str(abs_path)  # 不在 Tools 内，存绝对路径
        else:
            store_path = str(abs_path)

        tools_db.update_tool(
            self.db, self.selected_tool_id,
            name=name, path=store_path,
            alias=self.edit_alias_var.get().strip(),
            args=self.edit_args_var.get().strip(),
            category=self.edit_category_var.get().strip() or "未分类",
            run_as_admin=self.edit_admin_var.get(),
            description=self.edit_desc_text.get("1.0", "end").strip(),
        )
        self.icon_cache.clear()
        self._refresh_all()
        messagebox.showinfo("提示", "已保存。", parent=self)

    def _delete_selected_tool(self):
        if not self.selected_tool_id:
            return
        tool = tools_db.get_tool(self.db, self.selected_tool_id)
        if not tool:
            return
        # 查物理文件路径
        path = tool["path"]
        if not Path(path).is_absolute():
            path = str(self.tools_dir / path)
        path_obj = Path(path)
        del_file = False
        if path_obj.exists() and path_obj.is_relative_to(self.tools_dir):
            # 是 Tools 目录下的文件，询问是否同时删物理文件
            del_file = messagebox.askyesno(
                "删除工具",
                f"确定删除「{tool['name']}」吗？\n\n"
                f"勾选'是'同时删除物理文件：\n{path}\n\n"
                f"勾选'否'仅从数据库移除（物理文件保留）",
                parent=self
            )
        else:
            if not messagebox.askyesno("确认", f"确定删除「{tool['name']}」吗？", parent=self):
                return
        tools_db.delete_tool(self.db, self.selected_tool_id)
        if del_file and path_obj.exists():
            try:
                path_obj.unlink()
            except Exception as e:
                messagebox.showwarning("提示", f"数据库已删除，但物理文件删除失败：\n{e}", parent=self)
        self.selected_tool_id = None
        self._refresh_all()
        self.edit_name_var.set("")
        self.edit_path_var.set("")
        self.edit_args_var.set("")
        self.edit_category_var.set("")
        self.edit_admin_var.set(False)
        self.edit_desc_text.delete("1.0", "end")
        self.icon_preview_label.configure(text="(无)", image="")

    def _toggle_favorite(self):
        if not self.selected_tool_id:
            return
        tool = tools_db.get_tool(self.db, self.selected_tool_id)
        if not tool:
            return
        new_val = not bool(tool["is_favorite"])
        tools_db.update_tool(self.db, self.selected_tool_id, is_favorite=new_val)
        # ★ 快速启动栏已移除，不再联动

    def _run_selected_tool(self):
        if not self.selected_tool_id:
            messagebox.showinfo("提示", "请先选中一个工具。", parent=self)
            return
        self._run_tool_by_id(self.selected_tool_id)

    def _run_tool_by_id(self, tool_id: int):
        tool = tools_db.get_tool(self.db, tool_id)
        if not tool:
            return
        raw_path = tool["path"]
        if not Path(raw_path).is_absolute():
            abs_path = self.tools_dir / raw_path
        else:
            # ★ 绝对路径：支持引用模式下的系统工具（如 mstsc.exe 等）
            abs_path = Path(raw_path)

        # ★ URL 类型
        if raw_path.lower().startswith(("http://", "https://")):
            import webbrowser
            webbrowser.open(raw_path)
            return

        if not abs_path.exists():
            messagebox.showerror("错误", f"文件不存在：\n{abs_path}", parent=self)
            return

        try:
            args_str = tool.get("args") or ""
            # ★ 参数分裂：用 shlex.split 处理含空格路径
            import shlex
            args = shlex.split(args_str) if args_str else []

            if tool.get("run_as_admin"):
                # ★ 提权时用 list2cmdline 正确引用路径（含空格/单引号均安全）
                import subprocess as _sub
                safe_path = _sub.list2cmdline([str(abs_path)])
                safe_args = _sub.list2cmdline(args) if args else ""
                ps_parts = [f'Start-Process -FilePath {safe_path} -Verb RunAs']
                if safe_args:
                    ps_parts.append(f'-ArgumentList {safe_args}')
                ps_cmd = " ".join(ps_parts)
                _sub.Popen(["powershell.exe", "-Command", ps_cmd], shell=False)
            else:
                if hasattr(os, 'startfile') and not args:
                    # ★ startfile 体验最佳（用文件关联打开）
                    os.startfile(str(abs_path))
                else:
                    # ★ shell=False + 列表形式，避免命令注入
                    _sub.Popen([str(abs_path)] + args, shell=False)
        except Exception as e:
            messagebox.showerror("错误", f"启动失败：\n{e}", parent=self)

    def _show_tool_menu(self, event, tool_id: int):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="运行", command=lambda: self._run_tool_by_id(tool_id))
        menu.add_command(label="编辑", command=lambda: self._select_tool(tool_id))
        menu.add_separator()
        menu.add_command(label="抽图标",
                          command=lambda: (self._select_tool(tool_id),
                                            self._extract_icon_for_selected()))
        menu.add_separator()
        menu.add_command(label="删除",
                          command=lambda: (self._select_tool(tool_id),
                                            self._delete_selected_tool()))
        menu.tk_popup(event.x_root, event.y_root)

    # ★ _remove_from_toolbar 已删除（快速启动栏已移除）

    def _extract_icon_for_selected(self):
        if not self.selected_tool_id:
            messagebox.showinfo("提示", "请先选中一个工具。", parent=self)
            return
        tool = tools_db.get_tool(self.db, self.selected_tool_id)
        if not tool:
            return
        exe = tool["path"]
        if not Path(exe).is_absolute():
            exe = str(self.tools_dir / exe)
        if not Path(exe).lower().endswith(".exe"):
            messagebox.showinfo("提示", "仅 .exe 文件支持自动抽图标。", parent=self)
            return
        safe_name = "".join(c for c in tool["name"] if c.isalnum() or c in "._-")
        out = self.tools_dir / "_icons" / f"{safe_name}.png"
        cache_dir = self.tools_dir / "_图标"
        if extract_exe_icon(exe, str(out), self.icon_size, cache_dir=cache_dir):
            tools_db.update_tool(self.db, self.selected_tool_id, icon_path=str(out))
            self.icon_cache.clear()
            self._refresh_grid()
            self._set_preview_icon(str(out))
            messagebox.showinfo("提示", f"图标已保存：\n{out}", parent=self)
        else:
            messagebox.showerror("错误", "图标抽取失败。", parent=self)

    # ------------------------------------------------------------------
    # 分类管理
    # ------------------------------------------------------------------

    def _add_category_dialog(self):
        """新增分类对话框（★ 分类=文件夹，同时创建 Tools/<name>/）"""
        dlg = SimpleInputDialog(self, title=f"新增分类（归属包：{self.current_package}）",
                                label="分类名称:", default="")
        self.wait_window(dlg)
        if dlg.result:
            name = dlg.result.strip()
            if not name:
                return
            existing = {c["name"] for c in tools_db.list_categories(self.db)}
            if name in existing:
                messagebox.showwarning("提示", f"分类 '{name}' 已存在。", parent=self)
                return
            try:
                # ★ 归属当前包
                pkg = tools_db.list_packages(self.db)
                pkg_id = None
                for p in pkg:
                    if p["name"] == self.current_package:
                        pkg_id = p["id"]; break
                tools_db.add_category(self.db, name, package_id=pkg_id)
                # ★ 物理创建文件夹
                cat_dir = self.tools_dir / name
                cat_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                messagebox.showerror("错误", f"创建分类失败：\n{e}", parent=self)
                return
            self._refresh_categories()

    def _show_category_menu(self, event, category_id: int, name: str):
        """分类右键菜单：重命名/移动到包/删除"""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"重命名 '{name}'",
                          command=lambda: self._rename_category(category_id, name))
        # ★ 移动到其他包
        sub = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="移动到", menu=sub)
        for pkg in tools_db.list_packages(self.db):
            sub.add_command(
                label=pkg["name"],
                command=lambda pid=pkg["id"], pname=pkg["name"]:
                    self._move_category_to_package(category_id, name, pid, pname)
            )
        menu.add_separator()
        menu.add_command(label=f"删除 '{name}'",
                          command=lambda: self._delete_category(category_id, name))
        menu.tk_popup(event.x_root, event.y_root)

    def _rename_category(self, category_id: int, old_name: str):
        dlg = SimpleInputDialog(self, title="重命名分类", label="新名称:", default=old_name)
        self.wait_window(dlg)
        if dlg.result and dlg.result.strip() and dlg.result.strip() != old_name:
            tools_db.update_category(self.db, category_id, dlg.result.strip())
            if self.current_category == old_name:
                self.current_category = dlg.result.strip()
            self._refresh_categories()

    def _move_category_to_package(self, category_id: int, name: str, pkg_id: int, pkg_name: str):
        """把分类迁移到另一个包"""
        try:
            tools_db.update_category(self.db, category_id, package_id=pkg_id)
            # 如果当前就在该分类，则刷新
            self._refresh_categories()
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"移动分类失败：\n{e}", parent=self)

    def _delete_category(self, category_id: int, name: str):
        ok, msg = tools_db.delete_category(self.db, category_id)
        if not ok:
            messagebox.showwarning("无法删除", msg, parent=self)
            return
        if self.current_category == name:
            self.current_category = "全部"
        self._refresh_categories()
        messagebox.showinfo("提示", f"分类 '{name}' 已删除。", parent=self)

    # ------------------------------------------------------------------
    # 包（下拉菜单）管理
    # ------------------------------------------------------------------

    def _show_package_manager(self):
        """包管理对话框：增/改/删/启用"""
        PackageManagerDialog(self, self.db)

    # ------------------------------------------------------------------
    # 添加工具对话框
    # ------------------------------------------------------------------

    def _show_add_dialog(self):
        dialog = AddToolDialog(self, self.db, self.tools_dir, self.use_relative_path)
        self.wait_window(dialog)
        if dialog.result:
            # ★ 添加后切到新工具的分类
            if dialog.added_category and dialog.added_category != self.current_category:
                self.current_category = dialog.added_category
            self._refresh_all()
            if dialog.added_tool_id:
                self._select_tool(dialog.added_tool_id)

    # ------------------------------------------------------------------
    # 设置对话框
    # ------------------------------------------------------------------

    def _show_settings(self):
        SettingsDialog(self, self.db)

    # ------------------------------------------------------------------
    # 文件/路径
    # ------------------------------------------------------------------

    def _open_tools_folder(self):
        try:
            subprocess.Popen(["explorer", str(self.tools_dir.resolve())], shell=False)
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self)

    def _clean_invalid_tools(self):
        """清理 DB 里的无效工具记录：
        1. 物理文件不存在的
        2. 非可执行类型的脚本/快捷方式（.bat/.ps1/.cmd/.lnk）
           —— 这些从旧「批处理脚本」模式遗留，现在只保留手动入库的 exe/可执行文件
        """
        all_tools = tools_db.list_tools(self.db)
        invalid = []
        for t in all_tools:
            if t.get("is_deleted"):
                continue
            path = t.get("path", "")
            if not path:
                invalid.append(t)
                continue
            # ★ 路径解析：相对 Tools/ 的就走 tools_dir，绝对的直接用
            try:
                if Path(path).is_absolute():
                    abs_path = Path(path)
                else:
                    abs_path = (self.tools_dir / path).resolve()
            except Exception:
                abs_path = Path(path)
            if not abs_path.exists():
                invalid.append(t)
                continue
            # ★ 脚本类文件归档
            ext = abs_path.suffix.lower()
            if ext in (".bat", ".ps1", ".cmd", ".lnk", ".vbs"):
                invalid.append(t)
        if not invalid:
            messagebox.showinfo("清理", "数据库已是干净的，无需清理。", parent=self)
            return
        msg = "检测到 %d 条无效记录（文件不存在 / 脚本类残留），是否从 DB 删除？\n\n（仅软删除 is_deleted=1，物理文件不受影响）" % len(invalid)
        if not messagebox.askyesno("清理无效工具", msg, parent=self):
            return
        for t in invalid:
            try:
                tools_db.delete_tool(self.db, t["id"])
            except Exception:
                pass
        self._refresh_all()
        messagebox.showinfo("清理", "已清理 %d 条无效记录。" % len(invalid), parent=self)

    def _browse_path(self):
        path = filedialog.askopenfilename(
            parent=self, title="选择可执行文件",
            initialdir=str(self.tools_dir),
            filetypes=[("可执行", "*.exe *.bat *.cmd *.lnk *.py"),
                        ("所有", "*.*")])
        if path:
            self.edit_path_var.set(path)

    def _change_icon(self):
        path = filedialog.askopenfilename(
            parent=self, title="选择图标文件",
            filetypes=[("图片", "*.ico *.png *.jpg *.bmp"),
                        ("所有", "*.*")])
        if path and self.selected_tool_id:
            tools_db.update_tool(self.db, self.selected_tool_id, icon_path=path)
            self.icon_cache.clear()
            self._refresh_grid()
            self._set_preview_icon(path)

    # ------------------------------------------------------------------
    # 拖拽
    # ------------------------------------------------------------------

    def _on_drag_start(self, event, tool_id: int, from_toolbar: bool = False):
        self._drag_data = {
            "tool_id": tool_id, "from_toolbar": from_toolbar,
            "widget": event.widget
        }

    def _on_drag_motion(self, event):
        pass

    def _on_drag_release(self, event):
        # 判断拖拽距离：超过 5px 才算拖拽，否则保持选中不动作
        x0 = self._drag_data.get("x", event.x_root)
        y0 = self._drag_data.get("y", event.y_root)
        if abs(event.x_root - x0) < 5 and abs(event.y_root - y0) < 5:
            return  # 单击：已在 _on_card_press 选中过了
        widget = event.widget.winfo_containing(event.x_root, event.y_root)
        if not widget:
            return
        target = widget
        while target is not None:
            kind = getattr(target, '_drop_kind', None)
            if kind == "category":
                tool_id = self._drag_data.get("tool_id")
                if tool_id:
                    cat_name = getattr(target, '_drop_cat_name', None)
                    tool = tools_db.get_tool(self.db, tool_id)
                    if tool and cat_name and tool["category"] != cat_name:
                        tools_db.update_tool(self.db, tool_id, category=cat_name)
                        self._refresh_all()
                        messagebox.showinfo(
                            "已移动",
                            f"「{tool['name']}」已移到「{cat_name}」",
                            parent=self
                        )
                return
            target = target.master

    def _make_category_drop_target(self, widget, category_id: int, category_name: str):
        """把分类按钮注册为 drop target：拖动工具到该分类上可改变分类"""
        widget._drop_kind = "category"
        widget._drop_cat_id = category_id
        widget._drop_cat_name = category_name

        def on_enter(e, w=widget):
            try:
                # 高亮该分类（主色边框 + 浅蓝背景）
                w.configure(style="Accent.TButton")
            except tk.TclError:
                pass
        def on_leave(e, w=widget):
            try:
                w.configure(style="TButton")
            except tk.TclError:
                pass
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        # ★ 注册 drop target（拖入 .exe/目录→预填分类后打开 AddToolDialog）
        if HAS_TKDND and DND_FILES:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", lambda e, n=category_name: self._on_drop_files(e, prefill_category=n))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 面板空白处右键菜单
    # ------------------------------------------------------------------
    def _on_panel_right_click(self, event):
        """图标面板空白处右键 → 弹菜单（添加/查看/排序/操作）"""
        # 仅在 panel 空白处触发（不在 icon 上）
        widget = event.widget.winfo_containing(event.x_root, event.y_root)
        if widget is None:
            return
        # 碰上 icon card 就不弹
        if hasattr(self, 'icon_widgets') and widget in self.icon_widgets.values():
            return
        # 不在 grid_frame / canvas 子树内：不弹
        target = widget
        in_panel = False
        while target is not None:
            if target in (self.grid_frame, self.canvas):
                in_panel = True
                break
            target = getattr(target, 'master', None)
        if not in_panel:
            return

        menu = tk.Menu(self, tearoff=0)

        # ★ 添加
        menu.add_command(label="📄  添加文件", command=self._panel_add_file)
        menu.add_command(label="📁  添加文件夹", command=self._panel_add_folder)
        menu.add_command(label="🌐  添加网址", command=self._panel_add_url)
        menu.add_command(label="⚙  添加系统功能", command=self._panel_add_system)
        menu.add_separator()

        # ★ 图标大小
        size_menu = tk.Menu(menu, tearoff=0)
        current_cols = self.grid_cols
        for label, cols in [("大（每行 4）", 4), ("中（每行 6）", 6), ("小（每行 8）", 8)]:
            size_menu.add_command(
                label=label,
                command=lambda c=cols: self._set_grid_cols(c)
            )
        menu.add_cascade(label="图标大小", menu=size_menu)

        # ★ 查看方式（暂未实现多种视图）
        view_menu = tk.Menu(menu, tearoff=0)
        view_menu.add_command(label="图标（当前）", state="disabled")
        view_menu.add_command(label="列表", state="disabled")
        view_menu.add_command(label="详细信息", state="disabled")
        menu.add_cascade(label="查看方式", menu=view_menu)

        # ★ 排序方式
        sort_menu = tk.Menu(menu, tearoff=0)
        current_sort = tools_db.get_setting(self.db, "sort_key", "")
        sort_options = [
            ("默认（分类+s序）", ""),
            ("名称", "name"),
            ("最近添加", "id"),
        ]
        for label, key in sort_options:
            sort_menu.add_command(
                label=label + (" ✓" if key == current_sort else ""),
                command=lambda k=key: self._set_sort(k)
            )
        menu.add_cascade(label="排序方式", menu=sort_menu)
        menu.add_separator()

        menu.add_command(label="🔄  刷新本页图标", command=self._refresh_current_icons)
        menu.add_command(label="❌  清空本页应用", command=self._clear_current_category)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _panel_add_file(self):
        path = filedialog.askopenfilename(
            title="选择 .exe",
            filetypes=[("可执行文件", "*.exe"), ("快捷方式", "*.lnk"), ("所有文件", "*.*")],
            parent=self
        )
        if not path:
            return
        name = Path(path).stem
        dialog = AddToolDialog(self, self.db, self.tools_dir, self.use_relative_path,
                                prefill_name=name, prefill_path=path,
                                prefill_category=self.current_category)
        self.wait_window(dialog)
        if dialog.result:
            if dialog.added_category and dialog.added_category != self.current_category:
                self.current_category = dialog.added_category
            self._refresh_all()
            if dialog.added_tool_id:
                self._select_tool(dialog.added_tool_id)

    def _panel_add_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹（递归扫描 .exe）", parent=self)
        if not folder:
            return
        folder_path = Path(folder)
        cat_name = folder_path.name
        if cat_name not in [c["name"] for c in tools_db.list_categories(self.db)]:
            tools_db.add_category(self.db, cat_name)

        # ★ 递归扫描上限：避免扫 C:\Windows\System32 等巨型目录
        MAX_DEPTH = 8
        MAX_FILES = 2000
        added = 0
        scanned = 0
        for exe in folder_path.rglob("*.exe"):
            # depth 0 = 传入的 folder_path 本身
            depth = len(exe.relative_to(folder_path).parts) - 1
            if depth > MAX_DEPTH:
                continue
            scanned += 1
            if scanned > MAX_FILES:
                break
            try:
                tools_db.upsert_tool_by_path(
                    self.db, path=str(exe), name=exe.stem, category=cat_name
                )
                added += 1
            except Exception:
                pass

        msg = f"已扫描 {scanned} 个 .exe，加入 {added} 个工具到「{cat_name}」"
        if scanned >= MAX_FILES:
            msg += "\n（已达上限 2000 个，超出部分未处理）"
        elif added == 0:
            msg = "该文件夹下未发现 .exe 文件（或全部超出深度限制）。"
        messagebox.showinfo("完成" if added else "提示", msg, parent=self)
        if added:
            self.current_category = cat_name
            self._refresh_all()

    def _panel_add_url(self):
        url = tk.simpledialog.askstring("添加网址", "请输入 URL:", parent=self)
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        name = tk.simpledialog.askstring("添加网址", "请输入名称:", parent=self) or url
        # ★ 作为"系统工具"入库，path 存 URL（启动时 webbrowser.open 打开）
        tools_db.add_tool(self.db, name=name, path=url, category=self.current_category,
                          args="", description="网址快捷方式")
        self._refresh_all()
        messagebox.showinfo("完成", f"已添加网址「{name}」", parent=self)

    def _panel_add_system(self):
        # 复用 AddToolDialog（带"系统工具"按钮）
        dialog = AddToolDialog(self, self.db, self.tools_dir, self.use_relative_path,
                                prefill_category=self.current_category)
        self.wait_window(dialog)
        if dialog.result:
            if dialog.added_category and dialog.added_category != self.current_category:
                self.current_category = dialog.added_category
            self._refresh_all()

    def _set_grid_cols(self, n: int):
        self.grid_cols = n
        tools_db.set_setting(self.db, "grid_cols", str(n))
        self._refresh_grid()

    def _set_sort(self, key: str):
        tools_db.set_setting(self.db, "sort_key", key)
        self._refresh_grid()

    def _refresh_current_icons(self):
        """重新抽取当前分类下所有工具的图标"""
        keyword = self.search_var.get().strip()
        sort_key = tools_db.get_setting(self.db, "sort_key", "")
        tools = tools_db.list_tools(self.db, category=self.current_category, keyword=keyword,
                                    sort_key=sort_key, package=self.current_package)
        count = 0
        for t in tools:
            try:
                exe = t["path"]
                if not Path(exe).is_absolute():
                    exe = str(self.tools_dir / exe)
                if not Path(exe).lower().endswith(".exe"):
                    continue
                # 抽图标 → 存到 Tools/_icons/tool{id}.png（使用缓存目录）
                out_png = self.tools_dir / "_icons" / f"tool{t['id']}.png"
                cache_dir = self.tools_dir / "_图标"
                if extract_exe_icon(exe, str(out_png), size=48, cache_dir=cache_dir):
                    # 更新 DB 中 icon_path
                    rel_icon = str(out_png.relative_to(self.tools_dir))
                    tools_db.update_tool(self.db, t["id"], icon_path=rel_icon)
                    count += 1
            except Exception:
                pass
        self.icon_cache.clear()
        self._refresh_grid()
        messagebox.showinfo("完成", f"已刷新 {count}/{len(tools)} 个图标", parent=self)

    def _clear_current_category(self):
        cat = self.current_category
        if cat in ("全部", "未分类"):
            messagebox.showinfo("提示", f"不能在「{cat}」上执行此操作。", parent=self)
            return
        cnt = tools_db.count_tools_in_category(self.db, cat)
        if not cnt:
            messagebox.showinfo("提示", f"「{cat}」下没有工具。", parent=self)
            return
        if not messagebox.askyesno("确认", f"软删除「{cat}」下 {cnt} 个工具？\n（可从数据库/回收站恢复）", parent=self):
            return
        tools = tools_db.list_tools(self.db, category=cat)
        for t in tools:
            tools_db.update_tool(self.db, t["id"], is_deleted=1)
        self._refresh_all()
        messagebox.showinfo("完成", f"已清空「{cat}」下的 {cnt} 个工具。", parent=self)

    def _register_drop_target(self, widget):
        def on_enter(e, w=widget):
            try:
                w.configure(relief="ridge", bg=COLOR_DROP_HOVER)
            except tk.TclError:
                pass
        def on_leave(e, w=widget):
            try:
                w.configure(relief="flat", bg=COLOR_BG)
            except tk.TclError:
                pass
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        # ★ 注册 drop target（拖入 .exe/目录→打开 AddToolDialog）
        if HAS_TKDND and DND_FILES:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop_files)
            except Exception:
                pass

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ============================================================================
# 包标识色选择器（9 色网格）
# ============================================================================

class _ColorPickerDialog(tk.Toplevel):
    def __init__(self, parent, current_color: str = "#6b7280"):
        super().__init__(parent)
        self.title("选择包标识色")
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        apply_tool_dialog_theme(self)
        body = create_tool_dialog_body(self)
        ttk.Label(
            body,
            text="选个颜色，该包下的所有工具卡片\n左侧会显示同色 2px 色条作为归属标识。",
            justify="left",
            style="ToolDialog.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        grid = ttk.Frame(body, style="ToolDialog.TFrame")
        grid.pack()
        # 5 列 × 2 行 = 10 个位置，9 个颜色，第 10 个是清除按钮
        for i, color in enumerate(PACKAGE_ACCENT_COLORS):
            r, c = divmod(i, 5)
            sw = tk.Frame(grid, width=28, height=28, bg=color,
                           highlightthickness=(2 if color.lower() == current_color.lower() else 1),
                           highlightbackground=COLOR_BORDER if color.lower() != current_color.lower() else COLOR_PRIMARY,
                           cursor="hand2")
            sw.grid(row=r, column=c, padx=3, pady=3)
            sw.bind("<Button-1>", lambda e, col=color: self._pick(col))
        # 第 10 个：清除按钮
        clear_btn = ttk.Button(grid, text="清除", width=5,
                                command=lambda: self._pick(""))
        clear_btn.grid(row=1, column=4, padx=3, pady=3)
        btn_row = ttk.Frame(body, style="ToolDialog.TFrame")
        btn_row.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_row, text="取消", command=self.destroy).pack(side="right")
        self.update_idletasks()
        try:
            self.grab_set()
        except Exception:
            pass

    def _pick(self, color: str):
        self.result = color
        self.destroy()


# ============================================================================
# 简单输入对话框
# ============================================================================

class SimpleInputDialog(tk.Toplevel):
    """单行输入对话框"""
    def __init__(self, parent, title: str = "输入", label: str = "值:", default: str = ""):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.geometry("360x130")
        apply_tool_dialog_theme(self)
        body = create_tool_dialog_body(self)
        create_form_label(body, label, palette=TOOLBOX_PALETTE).pack(anchor="w", pady=(0, 4))
        self.var = tk.StringVar(value=default)
        e = create_form_entry(body, textvariable=self.var, palette=TOOLBOX_PALETTE)
        e.pack(fill="x")
        e.focus_set()
        e.select_range(0, "end")
        e.bind("<Return>", lambda ev: self._ok())
        btn = ttk.Frame(body, style="ToolDialog.TFrame")
        btn.pack(fill="x", pady=12)
        ttk.Button(btn, text="确定", command=self._ok).pack(side="right", padx=4)
        ttk.Button(btn, text="取消", command=self.destroy).pack(side="right")

    def _ok(self):
        self.result = self.var.get().strip()
        self.destroy()


# ============================================================================
# 添加工具对话框
# ============================================================================

class AddToolDialog(tk.Toplevel):
    """添加工具对话框（支持相对路径 + 系统工具引用模式）"""
    def __init__(self, parent, db_conn, tools_dir: Path, use_relative: bool = True,
                 prefill_name: str = "", prefill_path: str = "", prefill_category: str = ""):
        super().__init__(parent)
        self.title("添加工具")
        self.db_adapter = tools_db.ToolboxDatabaseAdapter.from_source(db_conn)
        self.db = self.db_adapter.connection
        self.tools_dir = tools_dir
        self.use_relative = use_relative
        self.result = False
        self.added_tool_id: Optional[int] = None
        self.added_category: str = ""
        self.geometry("540x520")
        self.transient(parent)
        self.grab_set()
        apply_tool_dialog_theme(self)
        body = create_tool_dialog_body(self)

        create_form_label(body, "工具名称:", palette=TOOLBOX_PALETTE).pack(anchor="w", pady=(0, 4))
        self.name_var = tk.StringVar(value=prefill_name)
        create_form_entry(body, textvariable=self.name_var, palette=TOOLBOX_PALETTE).pack(fill="x")

        create_form_label(body, "路径:", palette=TOOLBOX_PALETTE).pack(anchor="w", pady=(8, 4))
        path_frame = create_form_frame(body, palette=TOOLBOX_PALETTE)
        path_frame.pack(fill="x")
        self.path_var = tk.StringVar(value=prefill_path)
        create_form_entry(path_frame, textvariable=self.path_var, palette=TOOLBOX_PALETTE).pack(side="left", fill="x", expand=True)
        ttk.Button(path_frame, text="浏览...",
                   command=self._browse).pack(side="left", padx=(4, 0))
        ttk.Button(path_frame, text="💡 系统工具",
                   command=self._show_system_tools).pack(side="left", padx=(4, 0))

        create_form_label(body, "参数(可选):", palette=TOOLBOX_PALETTE).pack(anchor="w", pady=(8, 4))
        self.args_var = tk.StringVar()
        create_form_entry(body, textvariable=self.args_var, palette=TOOLBOX_PALETTE).pack(fill="x")

        create_form_label(body, "分类:", palette=TOOLBOX_PALETTE).pack(anchor="w", pady=(8, 4))
        default_cat = prefill_category or "未分类"
        self.category_var = tk.StringVar(value=default_cat)
        cats = [c["name"] for c in tools_db.list_categories(self.db)]
        ttk.Combobox(body, textvariable=self.category_var, values=cats, style="ToolDialog.TCombobox").pack(fill="x")

        self.admin_var = tk.BooleanVar()
        create_form_checkbutton(body, text="以管理员身份运行", variable=self.admin_var, palette=TOOLBOX_PALETTE).pack(anchor="w", pady=4)

        # ★ 引用模式复选框
        self.reference_var = tk.BooleanVar()
        self.ref_check = create_form_checkbutton(
            body,
            text="引用模式（不拷贝文件，直接调用原路径——适用于系统工具）",
            variable=self.reference_var,
            command=self._on_reference_toggle,
            palette=TOOLBOX_PALETTE,
            justify="left",
        )
        self.ref_check.pack(anchor="w", pady=4)

        self.path_hint = create_form_label(body, "", palette=TOOLBOX_PALETTE, muted=True)
        self.path_hint.pack(anchor="w")

        btn_frame = ttk.Frame(body, style="ToolDialog.TFrame")
        btn_frame.pack(fill="x", pady=12)
        ttk.Button(btn_frame, text="确定", command=self._ok).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="right")

        # 初始检测
        self.path_var.trace_add("write", lambda *_: self._auto_detect_reference())
        # ★ 预填路径后立即触发自动检测（系统目录→自动勾选引用模式）
        if prefill_path:
            self._auto_detect_reference()
            self._update_hint()

    def _browse(self):
        path = filedialog.askopenfilename(parent=self, initialdir=str(self.tools_dir))
        if path:
            self.path_var.set(path)
            if not self.name_var.get():
                self.name_var.set(Path(path).stem)
            self._update_hint()
            self._auto_detect_reference()

    def _auto_detect_reference(self):
        """自动检测路径是否在系统目录，如是自动勾选引用模式"""
        p = self.path_var.get().strip()
        if not p:
            return
        system_roots = [
            r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)",
            os.environ.get("SystemRoot", r"C:\Windows")
        ]
        p_lower = p.lower()
        for root in system_roots:
            if root and p_lower.startswith(root.lower()):
                self.reference_var.set(True)
                # 自动设分类
                if "system32" in p_lower:
                    self.category_var.set("系统工具")
                return

    def _on_reference_toggle(self):
        self._update_hint()

    def _show_system_tools(self):
        """打开系统工具快捷选择窗口"""
        win = tk.Toplevel(self)
        win.title("常用系统工具")
        win.geometry("400x500")
        win.transient(self)
        apply_tool_dialog_theme(win)
        body = create_tool_dialog_body(win)

        create_form_label(body, "双击添加:", palette=TOOLBOX_PALETTE, font=("", 10, "bold")).pack(pady=8)

        listbox = create_toolbox_listbox(body, font=("", 10))
        listbox.pack(fill="both", expand=True, pady=8)

        # 常用系统工具
        system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        common = [
            ("远程桌面", "mstsc.exe"),
            ("记事本", "notepad.exe"),
            ("画图", "mspaint.exe"),
            ("计算器", "calc.exe"),
            ("资源管理器", "explorer.exe"),
            ("命令提示符", "cmd.exe"),
            ("PowerShell", "powershell.exe"),
            ("注册表编辑器", "regedit.exe"),
            ("任务管理器", "taskmgr.exe"),
            ("服务管理", "services.msc"),
            ("设备管理器", "devmgmt.msc"),
            ("磁盘管理", "diskmgmt.msc"),
            ("系统信息", "msinfo32.exe"),
            ("截图工具", "snippingtool.exe"),
            ("字符映射表", "charmap.exe"),
            ("控制面板", "control.exe"),
        ]
        for label, fname in common:
            full = os.path.join(system32, fname)
            if os.path.exists(full) or "." in fname and "msc" in fname:
                listbox.insert("end", f"{label}  -  {fname}")
        listbox._common_map = {label: (label, fname) for label, fname in common}

        def on_double_click(_e):
            sel = listbox.curselection()
            if not sel:
                return
            text = listbox.get(sel[0])
            # 找对应项
            for label, fname in common:
                if text == f"{label}  -  {fname}":
                    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
                    full = os.path.join(system32, fname)
                    if os.path.exists(full):
                        self.path_var.set(full)
                        self.name_var.set(label)
                        self.reference_var.set(True)
                        self.category_var.set("系统工具")
                        self._update_hint()
                        win.destroy()
                        return
                    else:
                        # 路径型（如 .msc）
                        self.path_var.set(fname)
                        self.name_var.set(label)
                        self.reference_var.set(True)
                        self.category_var.set("系统工具")
                        self._update_hint()
                        win.destroy()
                        return

        listbox.bind("<Double-Button-1>", on_double_click)
        ttk.Button(body, text="关闭", command=win.destroy).pack(pady=8)

    def _update_hint(self):
        p = self.path_var.get().strip()
        if not p:
            self.path_hint.configure(text="")
            return
        if self.reference_var.get():
            self.path_hint.configure(text="→ 引用模式：使用原路径，不拷贝（适用于系统工具）", foreground=COLOR_SUCCESS)
        else:
            try:
                rel = Path(p).relative_to(self.tools_dir)
                self.path_hint.configure(text=f"→ 相对路径: {rel}", foreground=COLOR_MUTED)
            except ValueError:
                self.path_hint.configure(text="→ 不在 Tools 目录，将拷贝后存相对路径", foreground=COLOR_WARNING)

    def _ok(self):
        name = self.name_var.get().strip()
        path = self.path_var.get().strip()
        if not name or not path:
            messagebox.showwarning("提示", "名称和路径必填。", parent=self)
            return
        category = self.category_var.get().strip() or "未分类"
        # ★ 引用模式：直接存原路径，不拷贝
        if self.reference_var.get():
            target_store_path = path
        else:
            # 拷贝到分类目录
            src = Path(path)
            if not src.is_absolute():
                src = self.tools_dir / src
            target_store_path = path
            if src.exists() and src.is_file():
                cat_dir = self.tools_dir / category
                cat_dir.mkdir(parents=True, exist_ok=True)
                target = cat_dir / src.name
                try:
                    if src.resolve() != target.resolve():
                        import shutil
                        shutil.copy2(str(src), str(target))
                    target_store_path = f"{category}/{src.name}"
                except Exception as e:
                    messagebox.showerror("错误", f"拷贝文件到分类目录失败：\n{e}", parent=self)
                    return
            else:
                if self.use_relative and Path(path).is_absolute():
                    try:
                        target_store_path = str(Path(path).relative_to(self.tools_dir)).replace("\\", "/")
                    except ValueError:
                        target_store_path = path
        # ★ 查重：按 store_path
        existing = self.db.execute(
            "SELECT id, name, category FROM tool_items WHERE is_deleted=0 AND path = ?", (target_store_path,)
        ).fetchone()
        if existing:
            messagebox.showwarning(
                "工具已存在",
                f"该路径已在「{existing['category']}」分类中存在：\n\n"
                f"  名称: {existing['name']}\n"
                f"  路径: {target_store_path}\n\n"
                f"请勿重复添加。如需修改，请关闭后在主界面选中后编辑。",
                parent=self
            )
            self.added_tool_id = None
            self.result = False
            return
        # 分类不存在则创建
        if category not in {"未分类"}:
            existing_cats = {c["name"] for c in tools_db.list_categories(self.db)}
            if category not in existing_cats:
                tools_db.add_category(self.db, category)
        tools_db.add_tool(self.db, name=name, path=target_store_path,
                          category=category,
                          args=self.args_var.get().strip(),
                          run_as_admin=self.admin_var.get())
        row = self.db.execute("SELECT last_insert_rowid() AS id").fetchone()
        self.added_tool_id = row["id"] if row else None
        self.added_category = category

        # ★ 拖入即时抽图标：ctypes 同步抽，<1秒完成，不走 PowerShell
        if self.added_tool_id and Path(path).is_file() and Path(path).suffix.lower() == ".exe":
            try:
                self._auto_extract_icon_on_add(self.added_tool_id, path)
            except Exception:
                pass

        self.result = True
        self.destroy()

    def _auto_extract_icon_on_add(self, tool_id: int, exe_path: str):
        """拖入入库后同步抽图标（ctypes 方案，不走 PowerShell）
        ★ 抽后写入缓存 + 同步复制到 _icons/ 输出位置
        ★ DB 存绝对路径，不依赖 tools_dir 解析"""
        cache_dir = self.tools_dir / "_图标"
        # 缓存路径按 exe mtime+size 生成 hash
        out_png = self.tools_dir / "_icons" / f"tool{tool_id}.png"
        if extract_exe_icon(exe_path, str(out_png), size=48, cache_dir=cache_dir):
            # ★ 存绝对路径（不依赖 tools_dir 存在与否）
            tools_db.update_tool(self.db, tool_id, icon_path=str(out_png))


# ============================================================================
# 包管理对话框
# ============================================================================

class PackageManagerDialog(tk.Toplevel):
    """包（下拉菜单）管理"""
    def __init__(self, parent, db_conn):
        super().__init__(parent)
        self.title("包管理（下拉菜单）")
        self.db_adapter = tools_db.ToolboxDatabaseAdapter.from_source(db_conn)
        self.db = self.db_adapter.connection
        self.geometry("480x420")
        self.transient(parent)
        self.grab_set()
        apply_tool_dialog_theme(self)
        body = create_tool_dialog_body(self)

        ttk.Label(body, text="包列表（增/改/删）", style="ToolDialog.TLabel", font=("", 11, "bold")
                  ).pack(anchor="w", pady=(0, 6))

        list_frame = ttk.Frame(body, style="ToolDialog.TFrame")
        list_frame.pack(fill="both", expand=True)

        self.listbox = create_toolbox_listbox(list_frame, height=12, font=("", 10))
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._refresh_list()

        # 按钮
        btn_frame = ttk.Frame(body, style="ToolDialog.TFrame")
        btn_frame.pack(fill="x", pady=12)
        ttk.Button(btn_frame, text="+ 新增", command=self._add).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✎ 重命名", command=self._rename).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🎨 标识色", command=self._set_color).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🗑 删除", command=self._delete).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✓ 恢复", command=self._restore).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="关闭", command=self.destroy).pack(side="right", padx=4)

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        self._all_pkgs = tools_db.list_packages(self.db, include_inactive=True)
        for p in self._all_pkgs:
            mark = "✓" if p["is_active"] else "✗"
            self.listbox.insert("end", f"  {mark}  {p['name']}")

    def _selected(self) -> Optional[dict]:
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self._all_pkgs[sel[0]]

    def _add(self):
        dlg = SimpleInputDialog(self, title="新增包", label="包名:")
        self.wait_window(dlg)
        if dlg.result:
            tools_db.add_package(self.db, dlg.result.strip())
            self._refresh_list()

    def _rename(self):
        p = self._selected()
        if not p:
            return
        dlg = SimpleInputDialog(self, title="重命名包", label="新名称:", default=p["name"])
        self.wait_window(dlg)
        if dlg.result and dlg.result.strip():
            tools_db.update_package(self.db, p["id"], dlg.result.strip())
            self._refresh_list()

    def _set_color(self):
        p = self._selected()
        if not p:
            return
        dlg = _ColorPickerDialog(self, current_color=p.get("accent_color", "") or "#6b7280")
        self.wait_window(dlg)
        if dlg.result is not None:
            tools_db.update_package(self.db, p["id"], None, accent_color=dlg.result)
            self._refresh_list()

    def _delete(self):
        p = self._selected()
        if not p:
            return
        ok, msg = tools_db.delete_package(self.db, p["id"])
        if not ok:
            messagebox.showwarning("无法删除", msg, parent=self)
            return
        self._refresh_list()

    def _restore(self):
        p = self._selected()
        if not p or p["is_active"]:
            return
        tools_db.activate_package(self.db, p["id"])
        self._refresh_list()


# ============================================================================
# 设置对话框
# ============================================================================

class SettingsDialog(tk.Toplevel):
    """设置：路径/包/分类/权限等"""
    def __init__(self, parent, db_conn):
        super().__init__(parent)
        self.title("设置")
        self.db_adapter = tools_db.ToolboxDatabaseAdapter.from_source(db_conn)
        self.db = self.db_adapter.connection
        self.geometry("640x520")
        self.transient(parent)
        self.grab_set()
        apply_tool_dialog_theme(self)
        body = create_tool_dialog_body(self, padding=8)

        nb = ttk.Notebook(body)
        nb.pack(fill="both", expand=True)

        self._build_path_tab(nb)
        self._build_ftp_tab(nb)
        self._build_categories_tab(nb)
        self._build_packages_tab(nb)
        self._build_permission_tab(nb)

        action_row = ttk.Frame(body, style="ToolDialog.TFrame")
        action_row.pack(fill="x", pady=(8, 0))
        ttk.Button(action_row, text="关闭", command=self.destroy).pack(side="right")

    def _build_path_tab(self, nb):
        f = ttk.Frame(nb, padding=12, style="ToolDialog.TFrame")
        nb.add(f, text="路径")
        create_form_label(f, "Tools 根目录:", palette=TOOLBOX_PALETTE).pack(anchor="w")
        path_frame = create_form_frame(f, palette=TOOLBOX_PALETTE)
        path_frame.pack(fill="x", pady=(0, 8))
        self.path_var = tk.StringVar(value=tools_db.get_setting(self.db, "tools_dir", ""))
        create_form_entry(path_frame, textvariable=self.path_var, palette=TOOLBOX_PALETTE).pack(side="left", fill="x", expand=True)
        ttk.Button(path_frame, text="...",
                   command=self._browse_tools_dir).pack(side="left", padx=4)
        ttk.Button(path_frame, text="📁 打开",
                   command=self._open_tools_dir).pack(side="left")

        self.use_rel_var = tk.BooleanVar(value=tools_db.get_setting(self.db, "use_relative_path", "1") == "1")
        create_form_checkbutton(
            f,
            text="在 Tools 目录内时，使用相对路径存储",
            variable=self.use_rel_var,
            palette=TOOLBOX_PALETTE,
        ).pack(anchor="w", pady=4)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=8)
        create_form_label(f, "图标尺寸:", palette=TOOLBOX_PALETTE).pack(anchor="w")
        self.icon_size_var = tk.StringVar(value=tools_db.get_setting(self.db, "icon_size", "48"))
        ttk.Combobox(f, textvariable=self.icon_size_var, width=10, style="ToolDialog.TCombobox",
                      values=["32", "48", "64", "96"]).pack(anchor="w", pady=4)

        create_form_label(f, "网格列数:", palette=TOOLBOX_PALETTE).pack(anchor="w")
        self.cols_var = tk.StringVar(value=tools_db.get_setting(self.db, "grid_cols", "6"))
        ttk.Combobox(f, textvariable=self.cols_var, width=10, style="ToolDialog.TCombobox",
                      values=["4", "5", "6", "7", "8"]).pack(anchor="w", pady=4)

        ttk.Button(f, text="保存路径设置", command=self._save_path).pack(anchor="e", pady=12)

    def _build_ftp_tab(self, nb):
        """FTP 设置 tab"""
        frame = ttk.Frame(nb, padding=12, style="ToolDialog.TFrame")
        nb.add(frame, text="FTP 同步")

        create_form_label(frame, "用于同步 Tools 目录的 FTP 服务器（选填）", palette=TOOLBOX_PALETTE, muted=True).pack(anchor="w", pady=(0, 10))

        # 启用开关
        self.ftp_enabled_var = tk.BooleanVar(
            value=tools_db.get_setting(self.db, "ftp_enabled", "0") == "1")
        create_form_checkbutton(
            frame,
            text="启用 FTP 同步",
            variable=self.ftp_enabled_var,
            palette=TOOLBOX_PALETTE,
        ).pack(anchor="w", pady=4)

        row_cfg = {"sticky": "w", "padx": 4, "pady": 3}
        fields = [
            ("主机地址:", "ftp_host", "ftp_host_var", "例: 192.168.1.100 或 ftp.example.com"),
            ("端口:", "ftp_port", "ftp_port_var", "21"),
            ("用户名:", "ftp_user", "ftp_user_var", ""),
            ("密码:", "ftp_pass", "ftp_pass_var", ""),
            ("远程路径:", "ftp_remote_path", "ftp_remote_var", "/Tools"),
        ]
        for label_text, key, var_name, placeholder in fields:
            row = create_form_frame(frame, palette=TOOLBOX_PALETTE)
            row.pack(fill="x", pady=2)
            create_form_label(row, label_text, palette=TOOLBOX_PALETTE, width=9).pack(side="left")
            raw = tools_db.get_setting(self.db, key, "")
            # ★ 密码字段首次读取时尝试解密（兼容旧明文 + 新混淆格式）
            value = _deobfuscate(raw) if "pass" in key else raw
            var = tk.StringVar(value=value)
            setattr(self, var_name, var)
            show = "*" if "pass" in key else ""
            entry = create_form_entry(row, textvariable=var, width=38, show=show, palette=TOOLBOX_PALETTE)
            entry.pack(side="left", fill="x", expand=True)
            create_form_label(row, placeholder, palette=TOOLBOX_PALETTE, muted=True, font=("", 8)).pack(side="left", padx=(4, 0))

        # 测试连接按钮
        btn_row = ttk.Frame(frame, style="ToolDialog.TFrame")
        btn_row.pack(fill="x", pady=10)
        ttk.Button(btn_row, text="🧪 测试连接",
                   command=self._test_ftp).pack(side="left")
        ttk.Button(btn_row, text="💾 保存",
                   command=self._save_ftp).pack(side="right")

        # 说明
        note = ttk.Label(frame, text=(
            "说明：\n"
            "• FTP 用于多台电脑共享 Tools 目录内容\n"
            "• 工具箱自检时，若本地 Tools 内容与「项目内置」不一致，自动从 FTP 下载\n"
            "• 引用路径（URL/UNC/外部 exe）不会被 FTP 覆盖\n"
            "• 首次使用请先在「路径」Tab 确认 Tools 根目录"
        ), style="ToolDialogMuted.TLabel", justify="left", font=("", 9))
        note.pack(anchor="w", pady=(8, 0))

    def _test_ftp(self):
        host = getattr(self, "ftp_host_var").get().strip()
        port_str = getattr(self, "ftp_port_var").get().strip() or "21"
        user = getattr(self, "ftp_user_var").get().strip()
        pw = getattr(self, "ftp_pass_var").get()
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("错误", "端口必须是数字", parent=self)
            return
        try:
            import ftplib
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=8)
            ftp.login(user, pw)
            ftp.quit()
            messagebox.showinfo("成功", f"连接 {host}:{port} 成功！", parent=self)
        except Exception as e:
            messagebox.showerror("连接失败", str(e), parent=self)

    def _save_ftp(self):
        tools_db.set_setting(self.db, "ftp_enabled",
                             "1" if self.ftp_enabled_var.get() else "0")
        tools_db.set_setting(self.db, "ftp_host",
                             getattr(self, "ftp_host_var").get().strip())
        tools_db.set_setting(self.db, "ftp_port",
                             getattr(self, "ftp_port_var").get().strip() or "21")
        tools_db.set_setting(self.db, "ftp_user",
                             getattr(self, "ftp_user_var").get().strip())
        tools_db.set_setting(self.db, "ftp_pass",
                             _obfuscate(getattr(self, "ftp_pass_var").get()))
        tools_db.set_setting(self.db, "ftp_remote_path",
                             getattr(self, "ftp_remote_var").get().strip() or "/Tools")
        messagebox.showinfo("提示", "FTP 设置已保存。", parent=self)

    def _browse_tools_dir(self):
        d = filedialog.askdirectory(parent=self, title="选择 Tools 根目录")
        if d:
            self.path_var.set(d)

    def _open_tools_dir(self):
        d = self.path_var.get().strip()
        if not d:
            messagebox.showinfo("提示", "请先填写 Tools 目录。", parent=self)
            return
        if not Path(d).exists():
            Path(d).mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["explorer", str(Path(d).resolve())], shell=False)
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self)

    def _save_path(self):
        tools_db.set_setting(self.db, "tools_dir", self.path_var.get().strip())
        tools_db.set_setting(self.db, "use_relative_path", "1" if self.use_rel_var.get() else "0")
        tools_db.set_setting(self.db, "icon_size", self.icon_size_var.get().strip() or "48")
        tools_db.set_setting(self.db, "grid_cols", self.cols_var.get().strip() or "6")
        messagebox.showinfo("提示", "已保存。部分设置需要重新打开工具箱生效。", parent=self)

    def _build_categories_tab(self, nb):
        f = ttk.Frame(nb, padding=12, style="ToolDialog.TFrame")
        nb.add(f, text="分类")
        ttk.Label(f, text="管理工具分类（右键分类按钮也可增删改）",
                  style="ToolDialogMuted.TLabel").pack(anchor="w", pady=(0, 6))

        self.cat_listbox = create_toolbox_listbox(f, height=14, font=("", 10))
        sb = ttk.Scrollbar(f, orient="vertical", command=self.cat_listbox.yview)
        self.cat_listbox.configure(yscrollcommand=sb.set)
        self.cat_listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._refresh_cat_list()

        btn_frame = ttk.Frame(f, style="ToolDialog.TFrame")
        btn_frame.pack(side="right", fill="y", padx=(8, 0))
        ttk.Button(btn_frame, text="+ 新增", command=self._add_cat).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="✎ 重命名", command=self._rename_cat).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="🗑 删除", command=self._delete_cat).pack(fill="x", pady=2)

    def _refresh_cat_list(self):
        self.cat_listbox.delete(0, "end")
        self._all_cats = tools_db.list_categories(self.db)
        for c in self._all_cats:
            n = tools_db.count_tools_in_category(self.db, c["name"])
            self.cat_listbox.insert("end", f"  {c['name']}  ({n} 工具)")

    def _cat_selected(self) -> Optional[dict]:
        sel = self.cat_listbox.curselection()
        if not sel:
            return None
        return self._all_cats[sel[0]]

    def _add_cat(self):
        dlg = SimpleInputDialog(self, title="新增分类", label="分类名:")
        self.wait_window(dlg)
        if dlg.result:
            tools_db.add_category(self.db, dlg.result.strip())
            self._refresh_cat_list()

    def _rename_cat(self):
        c = self._cat_selected()
        if not c:
            return
        dlg = SimpleInputDialog(self, title="重命名分类", label="新名称:", default=c["name"])
        self.wait_window(dlg)
        if dlg.result and dlg.result.strip():
            tools_db.update_category(self.db, c["id"], dlg.result.strip())
            self._refresh_cat_list()

    def _delete_cat(self):
        c = self._cat_selected()
        if not c:
            return
        ok, msg = tools_db.delete_category(self.db, c["id"])
        if not ok:
            messagebox.showwarning("无法删除", msg, parent=self)
        else:
            self._refresh_cat_list()
            messagebox.showinfo("提示", "已删除。", parent=self)

    def _build_packages_tab(self, nb):
        f = ttk.Frame(nb, padding=12, style="ToolDialog.TFrame")
        nb.add(f, text="包")
        ttk.Label(f, text="管理顶部下拉菜单（个人系统 / 常用工具 等）",
                  style="ToolDialogMuted.TLabel").pack(anchor="w", pady=(0, 6))

        self.pkg_listbox = create_toolbox_listbox(f, height=14, font=("", 10))
        sb = ttk.Scrollbar(f, orient="vertical", command=self.pkg_listbox.yview)
        self.pkg_listbox.configure(yscrollcommand=sb.set)
        self.pkg_listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._refresh_pkg_list()

        btn_frame = ttk.Frame(f, style="ToolDialog.TFrame")
        btn_frame.pack(side="right", fill="y", padx=(8, 0))
        ttk.Button(btn_frame, text="+ 新增", command=self._add_pkg).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="✎ 重命名", command=self._rename_pkg).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="🗑 删除", command=self._delete_pkg).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="✓ 恢复", command=self._restore_pkg).pack(fill="x", pady=2)

    def _refresh_pkg_list(self):
        self.pkg_listbox.delete(0, "end")
        self._all_pkgs = tools_db.list_packages(self.db, include_inactive=True)
        for p in self._all_pkgs:
            mark = "✓" if p["is_active"] else "✗"
            self.pkg_listbox.insert("end", f"  {mark}  {p['name']}")

    def _pkg_selected(self) -> Optional[dict]:
        sel = self.pkg_listbox.curselection()
        if not sel:
            return None
        return self._all_pkgs[sel[0]]

    def _add_pkg(self):
        dlg = SimpleInputDialog(self, title="新增包", label="包名:")
        self.wait_window(dlg)
        if dlg.result:
            tools_db.add_package(self.db, dlg.result.strip())
            self._refresh_pkg_list()

    def _rename_pkg(self):
        p = self._pkg_selected()
        if not p:
            return
        dlg = SimpleInputDialog(self, title="重命名包", label="新名称:", default=p["name"])
        self.wait_window(dlg)
        if dlg.result and dlg.result.strip():
            tools_db.update_package(self.db, p["id"], dlg.result.strip())
            self._refresh_pkg_list()

    def _delete_pkg(self):
        p = self._pkg_selected()
        if not p:
            return
        ok, msg = tools_db.delete_package(self.db, p["id"])
        if not ok:
            messagebox.showwarning("无法删除", msg, parent=self)
        else:
            self._refresh_pkg_list()

    def _restore_pkg(self):
        p = self._pkg_selected()
        if not p or p["is_active"]:
            return
        tools_db.activate_package(self.db, p["id"])
        self._refresh_pkg_list()

    def _build_permission_tab(self, nb):
        f = ttk.Frame(nb, padding=12, style="ToolDialog.TFrame")
        nb.add(f, text="权限")
        create_form_label(f, "默认运行方式:", palette=TOOLBOX_PALETTE).pack(anchor="w", pady=(0, 4))
        self.mode_var = tk.StringVar(value=tools_db.get_setting(self.db, "default_run_mode", "normal"))
        tk.Radiobutton(
            f, text="普通权限", variable=self.mode_var, value="normal",
            bg=TOOLBOX_PALETTE.bg, fg=TOOLBOX_PALETTE.text_primary,
            activebackground=TOOLBOX_PALETTE.bg, activeforeground=TOOLBOX_PALETTE.text_primary,
            selectcolor=TOOLBOX_PALETTE.bg, highlightthickness=0,
        ).pack(anchor="w")
        tk.Radiobutton(
            f, text="管理员权限", variable=self.mode_var, value="admin",
            bg=TOOLBOX_PALETTE.bg, fg=TOOLBOX_PALETTE.text_primary,
            activebackground=TOOLBOX_PALETTE.bg, activeforeground=TOOLBOX_PALETTE.text_primary,
            selectcolor=TOOLBOX_PALETTE.bg, highlightthickness=0,
        ).pack(anchor="w")

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=12)
        create_form_label(f, "以管理员启动说明:", palette=TOOLBOX_PALETTE, font=("", 10, "bold")).pack(anchor="w", pady=(0, 4))
        create_form_label(
            f,
            "· PowerShell 调用 Start-Process -Verb RunAs\n· 需要用户点击 UAC 提示\n· 可在工具详情勾选'以管理员身份运行'覆盖此默认",
            palette=TOOLBOX_PALETTE,
            muted=True,
            justify="left",
        ).pack(anchor="w")
        ttk.Button(f, text="保存", command=self._save_mode).pack(anchor="e", pady=12)

    def _save_mode(self):
        tools_db.set_setting(self.db, "default_run_mode", self.mode_var.get())
        messagebox.showinfo("提示", "已保存。", parent=self)
