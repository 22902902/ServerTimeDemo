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
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from pathlib import Path
from typing import Optional

import app_icons
import tools_db
import tools_launcher as launcher
from dialog_form_style import apply_dialog_form_style, create_form_checkbutton, create_form_entry, create_form_frame, create_form_label
from page_components import add_toolbar_buttons, create_page_toolbar, create_status_bar
from ui_components import RoundedChip
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
# 选中态 chip 用实心黑底 + 白字（比「凹陷边框」一眼可辨）
COLOR_ACCENT_TEXT = TOOLBOX_PALETTE.accent_text
# 分类胶囊 / 快捷条 chip 的底色。不用 surface_alt(#f7f7f7)：它与白底只差 3%，
# 圆角在这点对比度下根本看不出来，等于白做。
COLOR_CHIP_BG = TOOLBOX_PALETTE.chip_bg
COLOR_CHIP_BG_HOVER = TOOLBOX_PALETTE.chip_bg_hover

# ---- 启动器布局常量 ----
CARD_MIN_WIDTH = 104     # 卡片最小宽度：icon 48px 之外还留得下两行名字
CARD_TITLE_MAX = 16      # 标题最大字符数，超出截断，防止换行把卡片撑破
CARD_HINT_MAX = 11       # 副标题最大字符数
FAVORITE_LIMIT = 8       # 收藏横条最多显示几个
RECENT_LIMIT = 8         # 最近使用横条最多显示几个
LABEL_VPAD = 6           # tk.Label 单行 reqheight 比 linespace 多的那 6px（实测）


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


# 两类进程内缓存，都按 (路径, mtime, 大小) 作键 —— exe 一被替换就自动失效。
_usable_icon_cache: set = set()   # 已确认「这张 PNG 有内容」
_icon_miss_cache: set = set()     # 已确认「这个 exe 根本抽不出图标」

# PowerShell 兜底。路径里的单引号必须转成两个，否则路径含引号时脚本直接语法错。
_PS_ICON_SCRIPT = (
    "Add-Type -AssemblyName System.Drawing; "
    "$icon = [System.Drawing.Icon]::ExtractAssociatedIcon('{path}'); "
    "if ($icon) {{ $bmp = $icon.ToBitmap(); "
    "$bmp.Save('{out}', [System.Drawing.Imaging.ImageFormat]::Png); "
    "$icon.Dispose(); $bmp.Dispose(); exit 0 }} else {{ exit 1 }}"
)


def _file_stamp(path) -> tuple:
    """(规范化路径, mtime 纳秒, 大小)。取不到 stat 时退化成 (路径, -1, -1)。"""
    p = Path(path)
    try:
        st = p.stat()
        return (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(p), -1, -1)


def png_icon_is_usable(path) -> bool:
    """判断一张图标 PNG 到底有没有「内容」。

    只看「文件存在 + 大小 > 0」是不够的：全透明的空图同样是一张**合法 PNG**
    （48×48 实测只有 88 字节）。这种文件一旦被写进缓存就会被永久命中，
    图标再也显示不出来 —— 用户看到的就是「这个工具抽不到图标」。
    所以缓存命中时也要验一次 alpha。

    结果按 (路径, mtime, 大小) 缓存：网格每次刷新都会对同一批文件重复问同一句，
    而带 mtime 的键让文件被重写后缓存自动失效，不会拿着旧结论误判。
    """
    p = Path(path)
    stamp = _file_stamp(p)
    if stamp[2] <= 0:
        return False
    if stamp in _usable_icon_cache:
        return True
    if not HAS_PIL:
        return True      # 没有 Pillow 就没法验，乐观放行
    try:
        with Image.open(p) as im:
            if im.mode in ("RGBA", "LA", "PA"):
                if im.convert("RGBA").getchannel("A").getextrema()[1] == 0:
                    return False
    except Exception:
        return False
    _usable_icon_cache.add(stamp)
    return True


def _win_bitmap_api():
    """建立 shell32 / gdi32 / user32 的函数签名，返回 (u32, g32, sh32, HANDLE)。

    **必须显式声明 argtypes**：64 位下 HICON / HBITMAP 是 8 字节句柄，实际值经常
    超过 2^31，而 ctypes 在没有 argtypes 时按 c_int 转换，会直接抛
    ``OverflowError: int too long to convert``。老代码就在 DeleteObject(hbmMask)
    上踩过这个坑 —— 还被外层 except 吞掉，表现为「抽到一半静默失败」。
    """
    import ctypes
    from ctypes import wintypes

    handle = ctypes.c_void_p
    u32 = ctypes.windll.user32
    g32 = ctypes.windll.gdi32
    sh32 = ctypes.windll.shell32

    sh32.ExtractIconExW.restype = wintypes.UINT
    sh32.ExtractIconExW.argtypes = [
        wintypes.LPCWSTR, wintypes.INT, ctypes.POINTER(handle),
        ctypes.POINTER(handle), wintypes.UINT]
    u32.GetIconInfo.argtypes = [handle, ctypes.c_void_p]
    u32.GetIconInfo.restype = wintypes.BOOL
    u32.DestroyIcon.argtypes = [handle]
    u32.GetDC.argtypes = [handle]
    u32.GetDC.restype = handle
    u32.ReleaseDC.argtypes = [handle, handle]
    g32.GetObjectW.argtypes = [handle, ctypes.c_int, ctypes.c_void_p]
    g32.GetObjectW.restype = ctypes.c_int
    g32.DeleteObject.argtypes = [handle]
    g32.GetDIBits.argtypes = [handle, handle, wintypes.UINT, wintypes.UINT,
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    g32.GetDIBits.restype = ctypes.c_int
    return u32, g32, sh32, handle


def _extract_icon_image(exe_path: str, size: int):
    """用 shell32 抽出图标位图并转成 RGBA 图；抽不到或结果是空图时返回 None。

    为什么不能像老代码那样 GetBitmapBits 一把梭
    ------------------------------------------------------------------
    1. ``GetIconInfo`` 交回来的 ``hbmColor`` 是一张 **DIB 段**，而 GetBitmapBits
       只对 DDB 可靠；改走 GetDIBits、并按位图自身的色深取，才拿得稳。
    2. 真正的坑在这里：很多老 exe（PuTTY 0.6x、Delphi 编的屏幕吸色器）的图标是
       「32 位色但 alpha 通道全是 0」—— 透明度只存在于 **AND 蒙版位图**里。
       照 BGRA 直读就是一张全透明空图：文件照样写得出、大小也正常，显示出来却
       什么都没有。本机 Tools 目录实测 6 个 exe 栽在这上面。所以 alpha 全 0 时
       必须回退到蒙版推透明度（蒙版位 = 1 表示透明，= 0 表示保留颜色）。
    """
    if not (HAS_PIL and sys.platform.startswith("win")):
        return None
    try:
        import ctypes
        from ctypes import wintypes
        u32, g32, sh32, handle = _win_bitmap_api()
    except Exception:
        return None

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                    ("yHotspot", wintypes.DWORD),
                    ("hbmMask", handle), ("hbmColor", handle)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG),
                    ("bmHeight", wintypes.LONG), ("bmWidthBytes", wintypes.LONG),
                    ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                    ("bmBits", ctypes.c_void_p)]

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class BMI(ctypes.Structure):
        _fields_ = [("bmiHeader", BMIH), ("bmiColors", wintypes.DWORD * 256)]

    def read_dib(hdc, hbm, w, h, bpp, palette=None):
        """取位图数据（自上而下 / BI_RGB）。返回 (字节, 行跨距)，失败 (None, 0)。"""
        bi = BMI()
        bi.bmiHeader.biSize = ctypes.sizeof(BMIH)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h        # 负数 = top-down，省得自己再翻一次
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = bpp
        bi.bmiHeader.biCompression = 0
        for i, entry in enumerate(list(palette or [])[:256]):
            bi.bmiColors[i] = entry
        stride = ((w * bpp + 31) // 32) * 4
        buf = (ctypes.c_ubyte * (stride * h))()
        if g32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(bi), 0) == 0:
            return None, 0
        return bytes(buf), stride

    def palette_of(hdc, hbm, w, h, bpp):
        """把位图自带的调色板捞出来（BGRX 顺序的 DWORD 列表）。"""
        bi = BMI()
        bi.bmiHeader.biSize = ctypes.sizeof(BMIH)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = bpp
        bi.bmiHeader.biCompression = 0
        g32.GetDIBits(hdc, hbm, 0, 0, None, ctypes.byref(bi), 0)
        return [bi.bmiColors[i] for i in range(1 << bpp)]

    def palette_bytes(entries):
        out = bytearray()
        for entry in entries:
            out += bytes(((entry >> 16) & 0xFF, (entry >> 8) & 0xFF,
                          entry & 0xFF))
        return bytes(out)

    hdc = None
    hicon = None
    info = ICONINFO()
    try:
        hdc = u32.GetDC(None)
        large = (handle * 1)()
        small = (handle * 1)()
        if not sh32.ExtractIconExW(str(exe_path), 0, large, small, 1):
            return None
        hicon = large[0] or small[0]
        if not hicon:
            return None
        if not u32.GetIconInfo(hicon, ctypes.byref(info)) or not info.hbmColor:
            return None

        bm = BITMAP()
        if not g32.GetObjectW(info.hbmColor, ctypes.sizeof(bm),
                              ctypes.byref(bm)):
            return None
        w, h, bpp = bm.bmWidth, bm.bmHeight, bm.bmBitsPixel
        if not w or not h or not bpp:
            return None

        if bpp == 32:
            data, stride = read_dib(hdc, info.hbmColor, w, h, 32)
            if data is None:
                return None
            img = Image.frombytes("RGBA", (w, h), data, "raw", "BGRA", stride)
        elif bpp == 24:
            data, stride = read_dib(hdc, info.hbmColor, w, h, 24)
            if data is None:
                return None
            img = Image.frombytes("RGB", (w, h), data, "raw", "BGR",
                                  stride).convert("RGBA")
        elif bpp in (1, 4):
            # Pillow 的 raw 解码器只认每像素一个字节，1/4 位得自己拆
            entries = palette_of(hdc, info.hbmColor, w, h, bpp)
            data, stride = read_dib(hdc, info.hbmColor, w, h, bpp)
            if data is None:
                return None
            per_byte = 8 // bpp
            mask = (1 << bpp) - 1
            unpacked = bytearray(w * h)
            for y in range(h):
                row = data[y * stride:(y + 1) * stride]
                base = y * w
                for x in range(w):
                    byte = row[x // per_byte]
                    shift = 8 - bpp * (x % per_byte + 1)
                    unpacked[base + x] = (byte >> shift) & mask
            img = Image.frombytes("P", (w, h), bytes(unpacked))
            img.putpalette(palette_bytes(entries))
            img = img.convert("RGBA")
        elif bpp == 8:
            entries = palette_of(hdc, info.hbmColor, w, h, 8)
            data, stride = read_dib(hdc, info.hbmColor, w, h, 8)
            if data is None:
                return None
            img = Image.frombytes("P", (w, h), data, "raw", "P", stride)
            img.putpalette(palette_bytes(entries))
            img = img.convert("RGBA")
        else:
            return None       # 16bpp 之类极其罕见，不值得为它写分支

        # ★ 关键一步：alpha 全 0 说明透明度藏在 AND 蒙版里
        if img.getchannel("A").getextrema()[1] == 0:
            mb = BITMAP()
            if not info.hbmMask or not g32.GetObjectW(
                    info.hbmMask, ctypes.sizeof(mb), ctypes.byref(mb)):
                return None
            if mb.bmWidth != w or mb.bmHeight not in (h, 2 * h):
                return None
            mdata, mstride = read_dib(hdc, info.hbmMask, w, h, 1,
                                      palette=(0x00000000, 0x00FFFFFF))
            if mdata is None:
                return None
            alpha = bytearray(w * h)
            for y in range(h):
                row = mdata[y * mstride:(y + 1) * mstride]
                base = y * w
                for x in range(w):
                    bit = (row[x >> 3] >> (7 - (x & 7))) & 1
                    alpha[base + x] = 0 if bit else 255
            img.putalpha(Image.frombytes("L", (w, h), bytes(alpha)))

        if img.size != (size, size):
            img = img.resize((size, size), Image.LANCZOS)
        if img.getchannel("A").getextrema()[1] == 0:
            # 推完蒙版还是全透明 —— 宁可让调用方走兜底，也不要一张看不见的图
            return None
        return img
    finally:
        if hdc is not None:
            u32.ReleaseDC(None, hdc)
        if info.hbmColor:
            g32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            g32.DeleteObject(info.hbmMask)
        if hicon:
            u32.DestroyIcon(hicon)


def extract_exe_icon(exe_path: str, out_png: str, size: int = 48,
                     cache_dir: Optional[Path] = None) -> bool:
    """从 .exe/.dll 抽取图标保存为 PNG。

    顺序：内存负缓存 → 磁盘缓存（要验内容）→ ctypes 同步抽 → PowerShell 兜底。
    两条抽取路径都必须保证「结果不是全透明」，否则宁可返回 False 让界面显示占位
    底牌 —— 一张看不见的图比没有图更让人困惑。
    """
    exe = Path(exe_path)
    if not exe.exists():
        return False

    if cache_dir is None:
        try:
            cache_dir = exe.parent.parent.parent / "_图标"
        except Exception:
            cache_dir = exe.parent / "_图标"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        cache_dir = exe.parent

    # ★ 已知抽不到就别再抽了。没有这道闸，每次刷新网格都会为「本来就没有图标」
    #   的 exe 重新跑一遍 PowerShell，一个 exe 一秒起，界面会明显发滞。
    exe_stamp = _file_stamp(exe)
    if exe_stamp in _icon_miss_cache:
        return False

    cache_path = _get_icon_cache_path(exe_path, size, cache_dir)
    if cache_path.exists():
        if png_icon_is_usable(cache_path):
            try:
                Path(out_png).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cache_path, out_png)
                return True
            except Exception:
                pass
        else:
            # 旧版本在 alpha 全 0 的图标上会存下一张全透明空图。这种坏缓存必须
            # 删掉，否则每次都会命中它，图标永远出不来。
            try:
                cache_path.unlink()
            except OSError:
                pass

    try:
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    # ---- 方案 1：ctypes 同步抽取（<1 秒，无 PowerShell 启动开销）----
    try:
        img = _extract_icon_image(exe_path, size)
    except Exception:
        img = None
    if img is not None:
        try:
            img.save(out_png, "PNG")
            shutil.copy2(out_png, cache_path)
            _usable_icon_cache.add(_file_stamp(cache_path))
            return True
        except Exception:
            pass
    try:
        Path(out_png).unlink(missing_ok=True)
    except OSError:
        pass

    # ---- 方案 2：PowerShell + System.Drawing（兜底）----
    if sys.platform.startswith("win"):
        try:
            ps_script = _PS_ICON_SCRIPT.format(
                path=str(exe_path).replace("'", "''"),
                out=str(out_png).replace("'", "''"))
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True, timeout=15)
            if result.returncode == 0 and png_icon_is_usable(out_png):
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
                    _usable_icon_cache.add(_file_stamp(cache_path))
                except Exception:
                    pass
                return True
        except Exception:
            pass

    try:
        Path(out_png).unlink(missing_ok=True)
    except OSError:
        pass
    _icon_miss_cache.add(exe_stamp)
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

        # ★ 启动器状态
        self._all_tools: list[dict] = []            # 当前包下的全部工具（未过滤）
        self._visible_tools: list[dict] = []        # 网格里真正显示的工具（已排序）
        self._cursor_tool_id: Optional[int] = None  # 键盘光标所在卡片
        self._hover_tool_id: Optional[int] = None   # 鼠标悬停卡片
        self._category_chips: dict[str, tk.Label] = {}
        self._search_placeholder_on = True
        self.icon_widgets: dict[int, tk.Frame] = {}
        self.icon_subwidgets: dict[int, tuple] = {}
        self._star_labels: dict[int, tk.Label] = {}
        self._placeholder_cache: dict = {}      # (首字, 尺寸) → 无图标占位底牌
        # 按像素量文字用的字体对象：中英混排时「数几个字符」完全不准
        self._name_font = tkfont.Font(family="Microsoft YaHei", size=9)
        self._hint_font = tkfont.Font(family="Microsoft YaHei", size=8)

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
        self._build_quick_strips()
        self._build_main_area()
        # ★ 状态条最后 pack —— pack 是按调用顺序自上而下占位的
        self._build_status_bar()
        # ★ 整个页面注册为 drop target（拖入 .exe 即可快速添加）
        self._register_drop_target(self)
        self._show_placeholder()
        # 进页面就能直接打字 —— 启动器的第一步就该是输入框
        self.after(80, self._focus_search)

    def _build_top_bar(self):
        """顶部命令条：一条长搜索框 + 右边一组轻量动作。

        旧版把「包」「搜索」各占一行，后面再挂一排 emoji 按钮（✎ 🔍 🧹 📁 ⚙），
        占掉两行高度却没有任何明确的输入焦点，进页面还得先点一下搜索框。
        现在压成一行：左边直接就能打字，右边是需要时才去点的动作。

        动作按钮走 Toolbar.TButton —— 常态只看得到文字、悬停才浮出一层浅底。
        一排实心灰底按钮压在白色页面上又重又硬，还会跟搜索框抢视觉焦点。
        """
        bar = create_page_toolbar(self, padding=(24, 16, 24, 6))
        self._command_bar = bar

        # 先把右侧动作组放好，搜索框最后 pack 并 expand，让它自己吃掉中间的空白；
        # 原来写死 46 个字符宽，右边反而空出一大片。
        right = ttk.Frame(bar)
        right.pack(side="right")

        ttk.Label(right, text="包", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        self.package_var = tk.StringVar(value=self.current_package)
        self.package_combo = ttk.Combobox(right, textvariable=self.package_var, width=12,
                                          values=self.packages, state="readonly")
        self.package_combo.pack(side="left", padx=(0, 4))
        self.package_combo.bind("<<ComboboxSelected>>", lambda e: self._on_package_change())

        # 包标识色块：点一下改色（一眼看出当前在哪个套件）
        self._package_swatch = tk.Frame(right, width=12, height=12, bg=COLOR_MUTED,
                                        highlightthickness=1,
                                        highlightbackground=COLOR_BORDER_LIGHT,
                                        cursor="hand2")
        self._package_swatch.pack(side="left", padx=(2, 12))
        self._package_swatch.bind("<Button-1>", lambda e: self._on_package_swatch_click())

        add_toolbar_buttons(right, [
            ("添加工具", self._show_add_dialog, "Primary.TButton"),
            ("包管理", self._show_package_manager),
            ("扫描目录", self._initial_scan),
            ("打开目录", self._open_tools_folder),
            ("设置", self._show_settings),
        ], style="Toolbar.TButton")

        # ---- 搜索（吃掉剩余宽度）----
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        self.search_entry.bind("<Down>", lambda e: self._move_cursor(1))
        self.search_entry.bind("<Up>", lambda e: self._move_cursor(-1))
        self.search_entry.bind("<Return>", lambda e: self._on_search_enter())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())
        self.search_entry.bind("<Control-a>", self._select_all_search)
        self.search_var.trace_add("write", lambda *_: self._on_search_changed())

        ttk.Button(bar, text="清空", style="Toolbar.TButton", width=0,
                   command=self._clear_search).pack(side="left", padx=(6, 0))

        # 常显的快捷键提示：占位文案一聚焦就消失，这些得一直看得见
        ttk.Label(bar, text="↑↓ 选择 · 回车启动 · Esc 清空",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------
    # 搜索框（启动器主入口）
    # ------------------------------------------------------------------

    SEARCH_PLACEHOLDER = "搜索工具：支持名称 / 别名 / 分类 / 文件名"

    def _select_all_search(self, _event=None):
        self.search_entry.selection_range(0, "end")
        return "break"

    def _focus_search(self):
        try:
            self.search_entry.focus_set()
        except tk.TclError:
            pass

    def _show_placeholder(self):
        self._search_placeholder_on = True
        self.search_var.set(self.SEARCH_PLACEHOLDER)
        self.search_entry.configure(foreground=COLOR_MUTED)

    def _hide_placeholder(self):
        self._search_placeholder_on = False
        self.search_var.set("")
        self.search_entry.configure(foreground=COLOR_TEXT)

    def _current_keyword(self) -> str:
        """取用户真正输入的关键词（占位文案不算）。"""
        if self._search_placeholder_on:
            return ""
        return self.search_var.get().strip()

    def _on_search_focus_in(self, _event=None):
        if self._search_placeholder_on:
            self._hide_placeholder()

    def _on_search_focus_out(self, _event=None):
        if not self.search_var.get().strip():
            self._show_placeholder()

    def _on_search_changed(self):
        # 占位文案也会触发 write，此时不能当成用户在搜索
        if self._search_placeholder_on:
            return
        self._refresh_grid()

    def _clear_search(self):
        if self._search_placeholder_on:
            self._focus_search()
            return
        if self.search_var.get():
            self.search_var.set("")     # 触发 trace → 自动刷新
        else:
            self._refresh_grid()
        self._focus_search()

    def _on_search_enter(self, _event=None):
        """回车启动光标所在工具；没有光标就启动第一条命中（Listary 的手感）。"""
        target = self._cursor_tool_id
        if target is None and self._visible_tools:
            target = launcher.tool_id(self._visible_tools[0])
        if target is not None:
            self._run_tool_by_id(target)
        return "break"

    def _build_category_bar(self):
        """分类栏：只列「有工具」的分类，数量跟在名字后面。

        以前 13 个分类里有 5 个是空的，照样各占一颗按钮（还都是同样的灰底凹陷框），
        扫一遍全是噪音、也看不出哪个分类值得点。现在空分类不进栏，
        名字后面直接带数量；管理分类仍然走「设置 → 分类」。
        横向滚动条只在真的放不下时才出现 —— 常驻一条灰杠很脏。
        """
        bar = tk.Frame(self, bg=COLOR_BG, padx=24, pady=0)
        bar.pack(fill="x")
        self._category_bar = bar

        self._cat_canvas = tk.Canvas(bar, bg=COLOR_BG, highlightthickness=0, height=26)
        self._cat_canvas.pack(fill="x", expand=True)
        self._cat_scroll = ttk.Scrollbar(bar, orient="horizontal",
                                          command=self._cat_canvas.xview)
        self._cat_canvas.configure(xscrollcommand=self._cat_scroll.set)

        self.category_container = tk.Frame(self._cat_canvas, bg=COLOR_BG)
        self._cat_window = self._cat_canvas.create_window(
            (0, 0), window=self.category_container, anchor="nw")
        self.category_container.bind("<Configure>", lambda e: self._on_category_layout())

        self.category_buttons: list[tk.Label] = []
        self._category_chips: dict[str, tk.Label] = {}

    def _on_category_layout(self):
        bbox = self._cat_canvas.bbox("all")
        if not bbox:
            return
        self._cat_canvas.configure(scrollregion=bbox)
        # 让 canvas 高度贴着内容，避免上下留一圈白
        self._cat_canvas.configure(height=max(bbox[3] - bbox[1], 24))
        self._update_category_scroll()

    def _update_category_scroll(self):
        bbox = self._cat_canvas.bbox("all")
        if not bbox:
            return
        need = (bbox[2] - bbox[0]) > self._cat_canvas.winfo_width() + 1
        shown = bool(self._cat_scroll.winfo_ismapped())
        if need and not shown:
            self._cat_scroll.pack(fill="x")
        elif not need and shown:
            self._cat_scroll.pack_forget()

    def _create_category_chip(self, name: str, count: int, category_id=None):
        """一颗分类胶囊：圆角、常态浅灰、选中近黑底白字。

        改用自绘的 RoundedChip —— tk.Label 是硬边矩形，摆一排就是「硬」；
        而且 Canvas 之外的控件默认带 1px 的 highlightthickness，
        会在每颗胶囊外面再套一圈边框，正是「按钮很硬」的来源之一。

        底色用 COLOR_CHIP_BG 而不是 surface_alt：后者与白底只差 3%，
        自绘的圆角在那种对比度下看不出来。
        """
        active = (name == self.current_category)
        chip = RoundedChip(
            self.category_container, f"{name} {count}",
            canvas_bg=COLOR_BG,
            bg=COLOR_CHIP_BG, fg=COLOR_TEXT,
            hover_bg=COLOR_CHIP_BG_HOVER, hover_fg=COLOR_TEXT,
            active_bg=COLOR_ACCENT, active_fg=COLOR_ACCENT_TEXT,
            active=active, font=("Microsoft YaHei", 9))
        chip.pack(side="left", padx=(0, 6), pady=1)

        chip.bind("<Button-1>", lambda e, n=name: self._switch_category(n))
        if category_id is not None:
            chip.bind("<Button-3>", lambda e, cid=category_id, n=name:
                      self._show_category_menu(e, cid, n))
            self._make_category_drop_target(chip, category_id, name)

        self.category_buttons.append(chip)
        self._category_chips[name] = chip
        return chip

    # ------------------------------------------------------------------
    # 快捷横条：收藏 / 最近使用
    # ------------------------------------------------------------------

    def _build_quick_strips(self):
        """收藏 / 最近使用两条横条。没有内容时整块不占位（pack_forget）。"""
        self._strips_frame = tk.Frame(self, bg=COLOR_BG)

    def _refresh_strips(self, tools):
        for child in self._strips_frame.winfo_children():
            child.destroy()

        favourites = launcher.favorite_tools(tools)[:FAVORITE_LIMIT]
        fav_ids = {launcher.tool_id(t) for t in favourites}
        recents = launcher.recent_tools(tools, RECENT_LIMIT, exclude_ids=fav_ids)

        if not favourites and not recents:
            self._strips_frame.pack_forget()
            return

        # 必须 pack 在网格之前（pack_forget 后再 pack 会排到队尾）
        options = {"fill": "x", "padx": 24, "pady": (0, 6)}
        if getattr(self, "_main_body", None) is not None:
            options["before"] = self._main_body
        self._strips_frame.pack(**options)

        if favourites:
            self._build_strip_row("收藏", favourites)
        if recents:
            self._build_strip_row("最近", recents)

    def _build_strip_row(self, title, items):
        """一条快捷横条（收藏 / 最近）。单击即启动，悬停变近黑底作强提示。"""
        row = tk.Frame(self._strips_frame, bg=COLOR_BG)
        row.pack(fill="x", pady=(0, 2))
        tk.Label(row, text=title, bg=COLOR_BG, fg=COLOR_MUTED,
                 font=("Microsoft YaHei", 9), width=4, anchor="w").pack(side="left")
        for tool in items:
            tid = launcher.tool_id(tool)
            if tid is None:
                continue
            chip = RoundedChip(
                row, launcher.strip_label(tool), canvas_bg=COLOR_BG,
                bg=COLOR_CHIP_BG, fg=COLOR_TEXT,
                hover_bg=COLOR_ACCENT, hover_fg=COLOR_ACCENT_TEXT,
                active_bg=COLOR_ACCENT, active_fg=COLOR_ACCENT_TEXT,
                padx=9, pady=3, font=("Microsoft YaHei", 9),
                command=lambda i=tid: self._run_tool_by_id(i))
            chip.pack(side="left", padx=(0, 6))
            # 单击即启动 —— 横条存在的意义就是「一下点开」，不做二次确认
            chip.bind("<Button-3>", lambda e, i=tid: self._show_tool_menu(e, i))

    # ------------------------------------------------------------------
    # 状态条
    # ------------------------------------------------------------------

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="")
        self._status_bar = create_status_bar(self, self.status_var, padding=(24, 8))

    def _update_status(self, tools=None, matched=None, keyword="", extra=""):
        """状态条：数量 / 重名提醒 / 当前光标。"""
        if tools is None:
            tools = getattr(self, "_all_tools", [])
        if matched is None:
            matched = getattr(self, "_visible_tools", [])

        parts = []
        if keyword:
            parts.append(f"匹配 {len(matched)} / {len(tools)}")
        else:
            parts.append(f"共 {len(matched)} 个工具")

        # 重名是「工具多了就找不着」的头号原因，直接在这儿点名。
        # 只统计当前「看得见」的那批 —— 在「系统工具」分类下还念叨别处的重名，
        # 只会让人以为当前这个分类里有问题。
        dupes = launcher.duplicate_names(matched)
        if dupes:
            shown = "、".join(f"{name}×{count}" for name, count in dupes[:3])
            more = f" 等 {len(dupes)} 组" if len(dupes) > 3 else ""
            parts.append(f"重名：{shown}{more}")

        if extra:
            parts.append(extra)
        elif keyword and not matched:
            # 只在「搜了但没搜到」时提示换词；套件本来就空的时候这么说很奇怪
            parts.append("没有匹配项，试试别名或分类")

        self.status_var.set("  ·  ".join(parts))

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
                          lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        # 滚轮只在指针进入网格时才接管：原来裸 bind_all，在右侧编辑面板的文本框里
        # 滚动时滚的其实是背后的网格，很难受
        self.canvas.bind("<Enter>",
                          lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
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
            previous = self.selected_tool_id
            self.selected_tool_id = None
            if previous is not None:
                self._paint_card(previous)

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
        keyword = self._current_keyword()
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

    def _fetch_package_tools(self) -> list[dict]:
        """当前包下全部未删除工具（不按分类 / 关键词过滤）。"""
        return tools_db.list_tools(self.db, package=self.current_package)

    def _refresh_categories(self):
        """按「当前包 → 有工具的分类」重绘 chip 条，并带上数量。"""
        for chip in self.category_buttons:
            chip.destroy()
        self.category_buttons.clear()
        self._category_chips.clear()

        counts: dict[str, int] = {}
        for tool in self._fetch_package_tools():
            key = tool.get("category") or "未分类"
            counts[key] = counts.get(key, 0) + 1

        all_categories = tools_db.list_categories(self.db, package=self.current_package)
        entries = [("全部", sum(counts.values()), None)]
        for category in all_categories:
            if counts.get(category["name"], 0) > 0:
                entries.append((category["name"], counts[category["name"]], category["id"]))

        # 当前分类已被删空 / 移走时，自动退回「全部」，免得停在一个空页面上
        if self.current_category not in {name for name, _, _ in entries}:
            self.current_category = "全部"

        for name, count, category_id in entries:
            self._create_category_chip(name, count, category_id)

        # 同步到编辑区下拉（这里要保留空分类，用户可能正想把工具改进去）
        if hasattr(self, "edit_category_combo"):
            self.edit_category_combo["values"] = [c["name"] for c in all_categories]
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
        """切分类：只重涂胶囊，不重建（重建会闪，也会丢掉横向滚动位置）。"""
        if name == self.current_category:
            return
        self.current_category = name
        for category_name, chip in self._category_chips.items():
            chip.set_active(category_name == name)
        self._refresh_grid()

    def _refresh_grid(self):
        """重建网格：按包拉全量 → 按分类过滤 → 按关键词模糊排序。

        关键词过滤交给 tools_launcher.rank_tools，不用 SQL LIKE：
        否则 "dkgn" 这种子序列输入在 SQL 层就直接返回 0 条了。
        """
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.icon_widgets = {}
        self.icon_subwidgets = {}
        self._star_labels = {}
        self._cursor_tool_id = None
        self._hover_tool_id = None
        # ★ 同步顶部色块（包切换、设置色后与卡片色条同步）
        self._refresh_package_swatch()

        tools = self._fetch_package_tools()
        self._all_tools = tools
        if self.current_category != "全部":
            tools = [t for t in tools
                     if (t.get("category") or "未分类") == self.current_category]

        keyword = self._current_keyword()
        matched = launcher.rank_tools(tools, keyword)
        self._visible_tools = matched
        hints = launcher.compute_hints(self._all_tools)

        if not matched:
            self._render_empty_state(keyword)
        else:
            cols = max(int(self.grid_cols), 1)
            # uniform 让每列等宽 —— 否则一行里长名字的卡片会把短名字的挤扁
            for col in range(cols):
                self.grid_frame.columnconfigure(col, weight=1, uniform="toolcard")
            for index, tool in enumerate(matched):
                row, col = divmod(index, cols)
                self._create_icon_card(self.grid_frame, tool, row, col,
                                        hint=hints.get(launcher.tool_id(tool), ""))
            # 搜完自动把光标落在第一条命中上 —— 接着按回车就能启动
            if keyword:
                first = launcher.tool_id(matched[0])
                if first is not None:
                    self._set_cursor(first, quiet=True)

        self._refresh_strips(self._all_tools)
        self._update_status(self._all_tools, matched, keyword,
                            extra=self._cursor_label())

    def _render_empty_state(self, keyword: str):
        if keyword:
            text = f"没有匹配「{keyword}」的工具\n换个关键词，或按 Esc 清空搜索"
        elif not tools_db.list_categories(self.db, package=self.current_package):
            text = (f"「{self.current_package}」套件下还没有分类，所以这里是空的。\n"
                     f"到右上角「包管理」把分类分配到套件，或把「包」切回有内容的套件。")
        else:
            text = "这个分类下还没有工具。\n把 .exe 拖进来，或点右上角「添加工具」。"
        tk.Label(self.grid_frame, text=text, bg=COLOR_BG, fg=COLOR_MUTED,
                 font=("Microsoft YaHei", 10), justify="center").pack(pady=60)

    # ------------------------------------------------------------------
    # 键盘光标
    # ------------------------------------------------------------------

    def _cursor_label(self) -> str:
        if self._cursor_tool_id is None:
            return ""
        tool = next((t for t in self._visible_tools
                     if launcher.tool_id(t) == self._cursor_tool_id), None)
        return f"选中 {tool['name']}" if tool else ""

    def _set_cursor(self, tool_id, *, quiet: bool = False):
        if tool_id is None or tool_id == self._cursor_tool_id:
            return
        previous, self._cursor_tool_id = self._cursor_tool_id, tool_id
        for tid in (previous, tool_id):
            if tid is not None:
                self._paint_card(tid)
        self._scroll_card_into_view(tool_id)
        if not quiet:
            self._update_status(extra=self._cursor_label())

    def _move_cursor(self, step: int):
        """把光标在可见结果里上下移动；到边界就绕回去。"""
        ids = [launcher.tool_id(t) for t in self._visible_tools]
        ids = [i for i in ids if i is not None]
        if not ids:
            return "break"
        if self._cursor_tool_id in ids:
            index = (ids.index(self._cursor_tool_id) + step) % len(ids)
        else:
            index = 0 if step >= 0 else len(ids) - 1
        self._set_cursor(ids[index])
        return "break"

    def _scroll_card_into_view(self, tool_id):
        """键盘移动时把卡片滚进可见区，否则光标会跑到视野外。"""
        card = self.icon_widgets.get(tool_id)
        if card is None or not card.winfo_exists():
            return
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        content_h = max(bbox[3] - bbox[1], 1)
        top = card.winfo_y()
        bottom = top + card.winfo_height()
        view_top = self.canvas.canvasy(0)
        view_h = self.canvas.winfo_height()
        if top < view_top:
            self.canvas.yview_moveto(max(top, 0) / content_h)
        elif bottom > view_top + view_h:
            self.canvas.yview_moveto(max(bottom - view_h, 0) / content_h)

    # ------------------------------------------------------------------
    # 卡片
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_px(text: str, max_px: int, font) -> str:
        """按像素宽度截断：中英混排时「数几个字符」完全不可靠。

        二分找最长可放下前缀，再补省略号 —— 与到期表格用的是同一套思路。
        """
        text = (text or "").strip()
        if not text or max_px <= 0:
            return ""
        if font.measure(text) <= max_px:
            return text
        ellipsis = "…"
        room = max_px - font.measure(ellipsis)
        if room <= 0:
            return ellipsis
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.measure(text[:mid]) <= room:
                low = mid
            else:
                high = mid - 1
        return text[:low] + ellipsis

    def _create_icon_card(self, parent, tool: dict, row: int, col: int, *, hint: str = ""):
        """一张工具卡片：图标 / 名字 / 副标题 + 右上角星标。

        副标题是关键 —— 用户有 3 个 putty、2 个 simplewall，光看名字分不清；
        星标常显（不满 hover）是因为「能收藏」这件事本身需要被发现。
        """
        tool_id = launcher.tool_id(tool)
        card_w = max(self.icon_size + 56, CARD_MIN_WIDTH)
        name_lines = 2
        # tk.Label 单行 reqheight 实测 = linespace + 6（17 -> 23），别漏掉这个常数，
        # 否则卡片会比内容矮，标题第二行会被切掉
        name_h = name_lines * self._name_font.metrics("linespace") + LABEL_VPAD
        hint_h = self._hint_font.metrics("linespace") + LABEL_VPAD
        card_h = 6 + self.icon_size + 4 + name_h + 2 + hint_h + 6

        card = tk.Frame(parent, bg=COLOR_BG, relief="flat", bd=0,
                        width=card_w, height=card_h,
                        highlightthickness=1, highlightbackground=COLOR_BORDER_LIGHT)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        card.grid_propagate(False)

        # 星标：常显，点一下收藏/取消（不必再展开右侧面板找按钮）
        favourited = launcher.as_flag(tool.get("is_favorite"))
        star = tk.Label(card, bg=COLOR_BG, cursor="hand2",
                        text="★" if favourited else "☆",
                        fg=COLOR_WARNING if favourited else COLOR_BORDER,
                        font=("Microsoft YaHei", 10))
        star.place(relx=1.0, x=-3, y=1, anchor="ne")
        star.bind("<Button-1>", lambda e, i=tool_id: self._toggle_favorite_by_id(i))

        # 图标
        icon_label = tk.Label(card, bg=COLOR_BG, cursor="hand2")
        self._load_tool_icon(tool, icon_label)
        icon_label.pack(pady=(6, 2))

        # 名字：限制在两行高度内，否则换行会把固定高度的卡片撑破
        available = card_w - 16
        title = self._fit_px(tool.get("name") or "", available * name_lines, self._name_font)
        name_label = tk.Label(card, text=title, bg=COLOR_BG, fg=COLOR_TEXT,
                               font=self._name_font, wraplength=available,
                               justify="center", cursor="hand2")
        name_label.pack(padx=4)

        # 副标题：别名 / 分类 / 上级目录（重名时取能区分开的那一个）
        hint_text = hint or ""
        if launcher.as_flag(tool.get("run_as_admin")):
            hint_text = f"{hint_text} · 管理" if hint_text else "管理员"
        hint_label = tk.Label(card, text=self._fit_px(hint_text, available + 8, self._hint_font),
                               bg=COLOR_BG, fg=COLOR_MUTED,
                               font=self._hint_font, cursor="hand2")
        hint_label.pack(pady=(0, 2))

        self.icon_widgets[tool_id] = card
        self.icon_subwidgets[tool_id] = (icon_label, name_label, hint_label, star)
        self._star_labels[tool_id] = star

        for widget in (card, icon_label, name_label, hint_label):
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

    def _paint_card(self, tool_id):
        """按「键盘光标 > 编辑选中 > 鼠标悬停 > 常态」重涂一张卡片。

        以前 hover 和 selected 各自 configure 一遍子控件，互相盖掉是常事；
        统一成一个优先级判定后就不会打架了。
        """
        card = self.icon_widgets.get(tool_id)
        if card is None or not card.winfo_exists():
            return
        if tool_id == self._cursor_tool_id:
            bg, border, thickness = COLOR_CARD_HOVER, COLOR_ACCENT, 2
        elif tool_id == self.selected_tool_id:
            bg, border, thickness = COLOR_BG, COLOR_PRIMARY, 2
        elif tool_id == self._hover_tool_id:
            bg, border, thickness = COLOR_CARD_HOVER, COLOR_BORDER, 1
        else:
            bg, border, thickness = COLOR_BG, COLOR_BORDER_LIGHT, 1
        try:
            card.configure(bg=bg, highlightbackground=border, highlightthickness=thickness)
        except tk.TclError:
            return
        for widget in self.icon_subwidgets.get(tool_id, ()):
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass

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
        """加载工具图标。

        1) 数据库 icon_path（绝对路径直接用，相对路径基于 tools_dir）
        2) 缓存目录 _图标/ 里按 exe hash 找
        3) 都没有就同步抽一次（仅 .exe）
        4) 全失败 → 显示「首字底牌」

        每一层都用 png_icon_is_usable 而不是 exists()：旧版本会把全透明的空图
        当成「抽好了」写进 DB，此时文件确实存在，图标却什么都看不见。
        这种坏数据要能被识别出来并重新抽，而不是一直摆在那儿。
        """
        icon_path = (tool.get("icon_path") or "").strip()

        if icon_path:
            p = Path(icon_path)
            if not p.is_absolute():
                p = self.tools_dir / icon_path
            icon_path = str(p)

        if icon_path and not png_icon_is_usable(icon_path):
            icon_path = ""

        # ---- 兜底 1：缓存目录里按 exe hash 找 ----
        if not icon_path:
            exe_path = tool.get("path", "")
            if exe_path:
                if not Path(exe_path).is_absolute():
                    exe_path = str(self.tools_dir / exe_path)
                cache_path = self._get_icon_cache_path(exe_path, self.icon_size)
                if png_icon_is_usable(cache_path):
                    icon_path = str(cache_path)
                    # 顺手修 DB：写回可用路径，下次不再走兜底
                    if tool.get("id"):
                        try:
                            tools_db.update_tool(self.db, tool["id"],
                                                 icon_path=icon_path)
                        except Exception:
                            pass

        # ---- 兜底 2：现抽一次（仅 .exe；延迟 100ms 不挡首屏）----
        if not icon_path:
            exe_path = tool.get("path", "")
            if exe_path:
                if not Path(exe_path).is_absolute():
                    exe_path = str(self.tools_dir / exe_path)
                exe_p = Path(exe_path)
                if exe_p.exists() and exe_p.suffix.lower() == ".exe":
                    label.after(100, lambda t=tool, l=label:
                                self._async_extract_icon(t, l))

        if not icon_path:
            self._set_placeholder_icon(tool, label)
            return

        cache_key = f"{icon_path}_native_{self.icon_size}"
        if cache_key in self.icon_cache:
            img = self.icon_cache[cache_key]
        else:
            img = None
            if HAS_PIL:
                try:
                    pil = Image.open(icon_path)
                    # Windows 原生图标风格（透明背景、保持比例）
                    pil = _make_native_icon(pil, self.icon_size)
                    # ★ 显式绑 master：不传的话 ImageTk 取的是 tkinter._default_root，
                    #   而那个 root 未必是这张 label 所在的解释器（例如别的模块调过
                    #   ttk.Style()，它会偷偷造一个 root 并占住默认位），
                    #   结果就是 image "pyimage1" doesn't exist。
                    img = ImageTk.PhotoImage(pil, master=label)
                except Exception:
                    img = None
            self.icon_cache[cache_key] = img

        if img:
            label.configure(image=img, text="")
            label.image = img
        else:
            self._set_placeholder_icon(tool, label)

    def _set_placeholder_icon(self, tool: dict, label: tk.Label):
        """没有图标时给一张「首字底牌」。

        以前这里放的是一个 ⚙ emoji：与全项目的线性图标语言不一致，而且一屏几十个
        一模一样的齿轮根本没法扫读。换成带首字的圆角底牌后，既能靠字形认人，
        也能一眼看出「这个工具确实没有图标」而不是「程序抽图标坏了」。

        按「首字 + 尺寸」缓存：同一批无图标工具复用同一张位图，不必反复渲染。
        """
        name = (tool.get("name") or "?").strip() or "?"
        key = (name[:1].upper(), self.icon_size)
        photo = self._placeholder_cache.get(key, "miss")
        if photo == "miss":
            photo = None
            if HAS_PIL:
                try:
                    photo = ImageTk.PhotoImage(
                        app_icons.letter_tile(name, self.icon_size),
                        master=label)
                except Exception:
                    photo = None
            self._placeholder_cache[key] = photo
        if photo is not None:
            label.configure(image=photo, text="")
            label.image = photo     # 必须持有引用，否则被 GC 回收后图变空白
        else:
            label.configure(image="", text=name[:1].upper(),
                            font=("Microsoft YaHei", 16), fg=COLOR_MUTED)

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
        if hover:
            self._hover_tool_id = tool_id
        elif self._hover_tool_id == tool_id:
            self._hover_tool_id = None
        self._paint_card(tool_id)

    def _select_tool(self, tool_id: int):
        # ★ 选中时自动展开右栏
        if not self._right_visible:
            self._toggle_right_panel()
        # ★ 选中态交给统一画法：和 hover / 键盘光标按优先级重涂
        previous = self.selected_tool_id
        self.selected_tool_id = tool_id
        for tid in (previous, tool_id):
            if tid is not None:
                self._paint_card(tid)
        tool = tools_db.get_tool(self.db, tool_id)
        if not tool:
            return

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
            img = ImageTk.PhotoImage(pil, master=self.icon_preview_label)
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
        """右侧面板的收藏按钮 —— 直接复用卡片星标那条路径，行为保持一致。"""
        if not self.selected_tool_id:
            return
        self._toggle_favorite_by_id(self.selected_tool_id)

    def _toggle_favorite_by_id(self, tool_id: int):
        tool = tools_db.get_tool(self.db, tool_id)
        if not tool:
            return
        new_value = not launcher.as_flag(tool.get("is_favorite"))
        tools_db.update_tool(self.db, tool_id, is_favorite=new_value)
        # 同步内存快照：为了点一颗星就整表重查 + 重建网格，画面会闪
        for bucket in (self._all_tools, self._visible_tools):
            for item in bucket:
                if launcher.tool_id(item) == tool_id:
                    item["is_favorite"] = 1 if new_value else 0
        self._refresh_star(tool_id)
        self._refresh_strips(self._all_tools)
        self._update_status(extra=self._cursor_label())

    def _refresh_star(self, tool_id):
        star = self._star_labels.get(tool_id)
        if star is None or not star.winfo_exists():
            return
        favourited = any(launcher.as_flag(t.get("is_favorite"))
                         for t in self._all_tools if launcher.tool_id(t) == tool_id)
        star.configure(text="★" if favourited else "☆",
                       fg=COLOR_WARNING if favourited else COLOR_BORDER)

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
            self._after_tool_run(tool_id)
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
                safe_path = subprocess.list2cmdline([str(abs_path)])
                safe_args = subprocess.list2cmdline(args) if args else ""
                ps_parts = [f'Start-Process -FilePath {safe_path} -Verb RunAs']
                if safe_args:
                    ps_parts.append(f'-ArgumentList {safe_args}')
                subprocess.Popen(["powershell.exe", "-Command", " ".join(ps_parts)],
                                 shell=False)
            else:
                if hasattr(os, 'startfile') and not args:
                    # ★ startfile 体验最佳（用文件关联打开）
                    os.startfile(str(abs_path))
                else:
                    # ★ shell=False + 列表形式，避免命令注入
                    #   注意：这里以前写的是 _sub.Popen，而 _sub 只在上面提权分支里
                    #   才绑定 —— 「带参数 + 不提权」会直接 NameError。改用模块级 subprocess。
                    subprocess.Popen([str(abs_path)] + args, shell=False)
            self._after_tool_run(tool_id)
        except Exception as e:
            messagebox.showerror("错误", f"启动失败：\n{e}", parent=self)

    def _after_tool_run(self, tool_id: int):
        """启动成功后的收尾：记一次「最近使用」并刷新横条。"""
        tools_db.touch_tool_run(self.db, tool_id)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in self._all_tools:
            if launcher.tool_id(item) == tool_id:
                item["last_run_at"] = stamp
                item["run_count"] = int(item.get("run_count") or 0) + 1
        self._refresh_strips(self._all_tools)

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
        """把分类胶囊注册为 drop target：拖动工具到该分类上即改变分类。

        旧实现在 <Enter>/<Leave> 里 `configure(style="Accent.TButton")` 做高亮 ——
        那是 ttk.Button 才有的选项，落在 tk.Label 上会抛 TclError 再被静默吞掉，
        等于完全没有反馈。现在统一走组件自己的拖放高亮状态。
        """
        widget._drop_kind = "category"
        widget._drop_cat_id = category_id
        widget._drop_cat_name = category_name

        if HAS_TKDND and DND_FILES:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", lambda e, n=category_name:
                                self._on_drop_files(e, prefill_category=n))
                if hasattr(widget, "set_drop_highlight"):
                    widget.dnd_bind("<<DropEnter>>", lambda e, w=widget:
                                    w.set_drop_highlight(True))
                    widget.dnd_bind("<<DropLeave>>", lambda e, w=widget:
                                    w.set_drop_highlight(False))
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
        keyword = self._current_keyword()
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
