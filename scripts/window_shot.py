# -*- coding: utf-8 -*-
"""把 Windows 窗口抓成 PNG —— 用 PrintWindow，不依赖桌面是否可见。

为什么不用 ImageGrab
------------------------------------------------------------------------------
本机（远程桌面断开 / 虚拟显示）用 ``ImageGrab.grab`` 抓到的**永远只有桌面
壁纸**（纯色 ``#00487E``，distinct 颜色数 == 1），窗口内容完全丢失。
``PrintWindow(hwnd, memdc, PW_RENDERFULLCONTENT)`` 是让窗口自己把界面画到
我们给的 DC 上，与前后台、与有没有真实桌面都无关。

**但跨进程抓图不能用这个标志**：``PW_RENDERFULLCONTENT(0x2)`` 对**本进程**窗口
没问题（WM_PRINT 同步处理），对**别的进程**的 Tk 窗口会抓到近空白（客户区纯白，
看图会以为程序没起来）。抓 exe 这类跨进程窗口必须传 ``flag=0``。实测见
``build/probe/grab_exe_flags.py``。

用法::

    from window_shot import shot_widget
    shot_widget(tk_window, "build/probe/alert.png")

    from window_shot import _grab          # 跨进程（如打包好的 exe）要 flag=0
    _grab(hwnd, flag=0).save("exe.png")

命令行::

    python scripts/window_shot.py            # 自检：建个窗口抓一张，验明可用
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

# PW_RENDERFULLCONTENT：让窗口渲染完整内容（含 DirectComposition 子控件），
# 不加这个标志在 Win10+ 上常抓到一片白
PW_RENDERFULLCONTENT = 0x00000002

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32


class CaptureFailed(RuntimeError):
    """抓图失败（窗口句柄不对、窗口已销毁、或抓到的是纯色空图）。"""


def _grab(hwnd: int, *, flag: int = PW_RENDERFULLCONTENT):
    """把窗口内容抓成 PIL.Image。

    ``flag`` 是 PrintWindow 的标志位。默认 ``PW_RENDERFULLCONTENT`` 适合**本进程**
    窗口；抓**别的进程**的窗口（打包好的 exe）必须传 ``flag=0``，否则客户区一片白
    （本机实测：flag=2 → 441 色、纯白；flag=0 → 793 色、界面完整）。
    """
    from PIL import Image

    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise CaptureFailed("GetWindowRect 失败，窗口可能已销毁")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise CaptureFailed(f"窗口尺寸异常：{width}x{height}")

    window_dc = _user32.GetWindowDC(hwnd)
    mem_dc = _gdi32.CreateCompatibleDC(window_dc)
    bitmap = _gdi32.CreateCompatibleBitmap(window_dc, width, height)
    _gdi32.SelectObject(mem_dc, bitmap)
    try:
        if not _user32.PrintWindow(hwnd, mem_dc, flag):
            raise CaptureFailed("PrintWindow 返回 0")

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height          # 负数 = 自上而下，省一次翻转
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0           # BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        if not _gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer,
                                ctypes.byref(header), 0):
            raise CaptureFailed("GetDIBits 返回 0")
        return Image.frombuffer("RGBA", (width, height), buffer,
                                "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        _gdi32.DeleteObject(bitmap)
        _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(hwnd, window_dc)


def shot_widget(widget, path, *, min_colors: int = 2):
    """把 Tk 控件所在窗口抓成 PNG。

    ``min_colors``：一张真界面至少有两种颜色。只抓到一种就一定失败了
    （典型症状是纯色壁纸 ``#00487E``），此时抛错而不是默默存一张空图 ——
    「以为拍到了」比「拍不到」更耽误事。
    """
    widget.update_idletasks()
    widget.update()
    hwnd = int(widget.winfo_id())
    # 顶层窗口的 winfo_id 是客户区，取真正的窗口句柄
    top = _user32.GetAncestor(hwnd, 2)   # GA_ROOT
    image = _grab(top or hwnd)
    colors = image.getcolors(maxcolors=1 << 20) or []
    if len(colors) < min_colors:
        raise CaptureFailed(
            f"只抓到 {len(colors)} 种颜色（{colors[:1]}）—— PrintWindow 没生效")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return image


def top_hwnd(widget) -> int:
    """控件的顶层窗口句柄（PrintWindow 要用它，不是客户区 id）。"""
    return _user32.GetAncestor(int(widget.winfo_id()), 2)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import tkinter as tk

    root = tk.Tk()
    root.title("截图自检")
    root.geometry("320x140+80+80")
    tk.Label(root, text="PrintWindow 自检", font=("Microsoft YaHei UI", 14)).pack(pady=30)
    root.update()
    out = Path(__file__).resolve().parent.parent / "build" / "probe" / "_shot_selftest.png"
    try:
        image = shot_widget(root, out)
        print(f"OK  抓到 {image.size[0]}x{image.size[1]}，"
              f"{len(image.getcolors(maxcolors=1 << 20) or [])} 种颜色 → {out}")
    finally:
        root.destroy()
