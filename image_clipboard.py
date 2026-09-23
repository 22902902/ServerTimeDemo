# -*- coding: utf-8 -*-
"""
================================================================================
剪贴板贴图（公共能力）
================================================================================
「截图 → Ctrl+V → 落盘」这套动作原先只写在笔记编辑器里
（``study_notes_window._on_ctrl_v``），流程中心同样需要它 —— 用户记录备案
/ 运维流程的实际姿势就是**截完图直接粘**，而不是先存成文件再去文件选择器里找。

所以把它抽到这里，笔记与流程中心共用一份，避免两套实现慢慢长歪。

关键取舍
--------------------------------------------------------------------------------
* **读 ``image/png`` 失败要静默返回 None，不抛异常** —— 剪贴板里是纯文本时
  ``clipboard_get`` 会抛 ``TclError``，这是**正常情况**（用户就是想粘文字），
  调用方据此放行默认粘贴行为。把正常路径做成异常处理是本项目的既有约定。
* **文件名带秒级时间戳 + 序号** —— 同一秒内连贴多张不会互相覆盖（时间戳
  精度到秒，序号兜住并发）。
* **只落盘、不碰界面** —— 返回 ``Path``，插入文本 / 刷新列表由调用方决定，
  这样笔记（插 Markdown 语法）与流程（建步骤）能共用同一个函数。
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:            # 没有 Pillow 时贴图功能整体降级，但不影响程序启动
    HAS_PIL = False

# Windows/Tk 下剪贴板位图能读到的类型；按顺序试，第一个成功的就用
CLIPBOARD_IMAGE_TYPES = ("image/png",)

__all__ = [
    "HAS_PIL",
    "clipboard_image_bytes",
    "clipboard_has_image",
    "unique_image_path",
    "save_clipboard_image",
]


def clipboard_image_bytes(widget, types=CLIPBOARD_IMAGE_TYPES) -> bytes | None:
    """从剪贴板读图片字节；剪贴板里不是图片时返回 ``None``。

    不抛异常：调用方拿 ``None`` = 「这次粘贴不是图，走默认文本粘贴」。
    """
    for kind in types:
        try:
            data = widget.clipboard_get(type=kind)
        except Exception:
            continue
        if isinstance(data, (bytes, bytearray)) and data:
            return bytes(data)
    return None


def clipboard_has_image(widget, types=CLIPBOARD_IMAGE_TYPES) -> bool:
    """剪贴板里是不是图片（用于决定 Ctrl+V 要不要拦下来）。"""
    return clipboard_image_bytes(widget, types) is not None


_last_stamp = ""
_last_seq = 0


def unique_image_path(target_dir: Path, suffix: str = ".png") -> Path:
    """在 ``target_dir`` 里生成一个不重名的图片路径（目录会自动创建）。

    命名 ``YYYYMMDD_HHMMSS_微秒[_序号].png`` —— 与账号中心 / 流程截图的既有
    文件（``20260630_144209_370819.png``）同一种命名，排序即时间序。

    为什么要带进程内序号：**Windows 上 ``strftime('%f')`` 的微秒粒度实际只有
    毫秒级**，同一毫秒内连续调用会拿到完全相同的时间戳（实测 5 次连调撞 3 次）。
    只靠时间戳就会出现「连续预留多个名字却得到同一个路径」的覆盖风险。
    所以时间戳相同时自增序号；``exists()`` 再兜一层跨进程/历史文件的撞名。
    """
    global _last_stamp, _last_seq
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    if stamp == _last_stamp:
        _last_seq += 1
    else:
        _last_stamp = stamp
        _last_seq = 0
    candidate = (target_dir / f"{stamp}{suffix}" if _last_seq == 0
                 else target_dir / f"{stamp}_{_last_seq:03d}{suffix}")
    if not candidate.exists():
        return candidate
    for seq in range(1, 1000):
        alt = target_dir / f"{stamp}_{seq:03d}{suffix}"
        if not alt.exists():
            return alt
    return target_dir / f"{stamp}_{datetime.now().strftime('%f')}{suffix}"


def save_clipboard_image(widget, target_dir: Path, suffix: str = ".png") -> Path | None:
    """把剪贴板图片存到 ``target_dir`` 并返回路径。

    返回 ``None`` 表示剪贴板里没有图片（调用方应放行默认粘贴）；
    读取成功但存盘失败会抛 ``OSError`` / PIL 的 ``UnidentifiedImageError``，
    由调用方决定怎么提示 —— 这里不弹窗，避免公共模块反向依赖界面层。
    """
    data = clipboard_image_bytes(widget)
    if data is None:
        return None
    if not HAS_PIL:
        raise RuntimeError("未安装 Pillow，无法保存剪贴板图片")
    path = unique_image_path(Path(target_dir), suffix)
    Image.open(io.BytesIO(data)).save(path)
    return path
