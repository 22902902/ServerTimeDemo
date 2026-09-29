# -*- coding: utf-8 -*-
"""截图标注画布（Tk 交互层）。

职责边界
--------------------------------------------------------------------------------
只干三件事：**把图画出来（按视口缩放）→ 收鼠标拖拽成 ops → 把 ops 交给回调**。
落盘、改库、刷新列表全在 ``process_page`` 那边 —— 这个对话框不认识 ``ProcessDBMixin``，
也不认识 ``BASE_DIR``。这样它才测得起（见 ``scripts/test_process_ui.py``）。

两个容易踩的点
--------------------------------------------------------------------------------
1. **画布坐标 ≠ 图片坐标**。大图会缩到视口里显示，拖出来的两点必须除以缩放比
   才是图片上的坐标；忘了除，标注会缩到左上角一小块（看着像「画出来但位置不对」）。
2. **不弹模态窗做测试**。文字那一笔要输入内容，是 ``simpledialog.askstring``；
   套件里把它换掉（``dialog.ask_string = fake``），别真等在那里。

画完一笔立刻**重画预览**（不用 PIL 往返）：圆/方框/箭头/文字都用 Canvas 原生
图元画，既是「所见即所得」，也省掉了每拖一下都要重新编码 PNG 的开销。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from process_annotate import (
    COLORS,
    DEFAULT_COLOR,
    DEFAULT_WIDTH,
    SHAPE_ARROW,
    SHAPE_ELLIPSE,
    SHAPE_LABELS,
    SHAPE_ORDER,
    SHAPE_RECT,
    SHAPE_TEXT,
    normalize_ops,
)
from ui_theme import MAIN_PALETTE, TYPOGRAPHY

try:
    from PIL import Image, ImageTk, UnidentifiedImageError
    HAS_PIL = True
except ImportError:                     # 没有 Pillow 时整个标注入口降级为文字提示
    HAS_PIL = False

# 视口上限：再大就把窗口顶出屏幕了，缩着看也够用（要看清可以点开大图）
VIEW_MAX = (940, 620)
# 拖出来的「框」小于这个尺寸就算误点，不记一笔（鼠标抖一下不该多一道印子）
MIN_DRAG = 6


class ScreenshotAnnotator(tk.Toplevel):
    """在截图上画圈 / 方框 / 箭头 / 文字。

    用法::

        dialog = ScreenshotAnnotator(master, image_path, on_save=callback)
        dialog.grab_set()      # 模态与否由调用方决定（套件里不要 grab）
    """

    def __init__(self, master, image_path, *, on_save=None, app_title="标注截图",
                 palette=MAIN_PALETTE):
        super().__init__(master)
        self.title(f"{app_title} —— {Path(image_path).name}")
        self.app_title = app_title
        self.image_path = Path(image_path)
        self.on_save = on_save
        self.palette = palette

        self.ops: list[dict] = []
        self._photo = None                 # 挡住 PhotoImage 被 GC
        self._scale = 1.0
        self._start = None                 # 当前这一笔的起点（图片坐标）
        self._preview = None               # 拖拽中的临时图元 id
        self._pending_text = None          # 文字那一笔：起点，等输入框返回
        # 文字输入用可替换的钩子：套件里换掉它，就不会真弹输入框
        self.ask_string = simpledialog.askstring

        self.shape_var = tk.StringVar(value=SHAPE_ELLIPSE)
        self.color_var = tk.StringVar(value=DEFAULT_COLOR)
        self.width_var = tk.IntVar(value=DEFAULT_WIDTH)

        if not HAS_PIL:
            messagebox.showinfo(app_title, "未安装 Pillow，无法标注截图。", parent=self)
            self.destroy()
            return
        self._build()

    # ==================================================================
    # 构建
    # ==================================================================
    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", padx=10, pady=(8, 4))

        ttk.Label(bar, text="工具", font=TYPOGRAPHY.caption).pack(side="left")
        for shape in SHAPE_ORDER:
            ttk.Radiobutton(bar, text=SHAPE_LABELS[shape], value=shape,
                            variable=self.shape_var).pack(side="left", padx=(6, 0))

        ttk.Label(bar, text="颜色", font=TYPOGRAPHY.caption).pack(side="left", padx=(14, 0))
        for color in COLORS:
            swatch = tk.Label(bar, text="  ", bg=color, width=2, cursor="hand2",
                              relief="solid", bd=1)
            swatch.pack(side="left", padx=2)
            swatch.bind("<Button-1>", lambda e, c=color: self.color_var.set(c))

        ttk.Label(bar, text="粗细", font=TYPOGRAPHY.caption).pack(side="left", padx=(14, 0))
        ttk.Spinbox(bar, from_=1, to=12, width=3,
                    textvariable=self.width_var).pack(side="left")

        # 定尺寸控件先 pack，画布（expand）最后 —— 见 UI_NOTES.md §10 纪律 A
        actions = ttk.Frame(self)
        actions.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        ttk.Button(actions, text="保存标注", command=self.save).pack(side="right")
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(actions, text="清空", command=self.clear).pack(side="left")
        ttk.Button(actions, text="撤销", command=self.undo).pack(side="left", padx=6)
        self.hint_var = tk.StringVar(value="按住左键拖出范围；选「文字」后点一下再输入。")
        ttk.Label(actions, textvariable=self.hint_var,
                  font=TYPOGRAPHY.caption).pack(side="left", padx=(12, 0))

        holder = ttk.Frame(self)
        holder.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 4))
        self.canvas = tk.Canvas(holder, highlightthickness=0, bg="#202020",
                                width=VIEW_MAX[0], height=VIEW_MAX[1])
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self._load_image()

    def _load_image(self):
        try:
            with Image.open(self.image_path) as handle:
                source = handle.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            self.canvas.create_text(10, 10, anchor="nw", fill="#d4d4d4",
                                    text=f"打不开这张图：{exc}", width=VIEW_MAX[0] - 20)
            return
        self.image_size = source.size
        scale = min(1.0, VIEW_MAX[0] / max(1, source.width),
                    VIEW_MAX[1] / max(1, source.height))
        shown = source if scale >= 1.0 else source.resize(
            (max(1, int(source.width * scale)), max(1, int(source.height * scale))))
        self._scale = scale
        self._photo = ImageTk.PhotoImage(shown)
        self.canvas.configure(width=shown.width, height=shown.height)
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._redraw_ops()

    # ==================================================================
    # 坐标换算（拖拽出来的点 → 图片坐标）
    # ==================================================================
    def to_image(self, x, y) -> tuple[int, int]:
        scale = self._scale or 1.0
        return (int(round(float(x) / scale)), int(round(float(y) / scale)))

    def to_canvas(self, x, y) -> tuple[int, int]:
        scale = self._scale or 1.0
        return (int(round(float(x) * scale)), int(round(float(y) * scale)))

    # ==================================================================
    # 交互
    # ==================================================================
    def _on_press(self, event):
        self._start = self.to_image(event.x, event.y)
        if self.shape_var.get() == SHAPE_TEXT:
            self._pending_text = self._start
            self.after_idle(self._ask_text)

    def _on_drag(self, event):
        if self._start is None or self.shape_var.get() == SHAPE_TEXT:
            return
        if self._preview is not None:
            self.canvas.delete(self._preview)
        end = self.to_image(event.x, event.y)
        self._preview = self._draw_one({
            "kind": self.shape_var.get(),
            "color": self.color_var.get(),
            "width": max(1, int(self.width_var.get() or DEFAULT_WIDTH)),
            "x1": self._start[0], "y1": self._start[1],
            "x2": end[0], "y2": end[1],
        })

    def _on_release(self, event):
        if self._start is None or self.shape_var.get() == SHAPE_TEXT:
            return
        end = self.to_image(event.x, event.y)
        start, self._start = self._start, None
        if self._preview is not None:
            self.canvas.delete(self._preview)
            self._preview = None
        if max(abs(end[0] - start[0]), abs(end[1] - start[1])) < MIN_DRAG:
            return                              # 鼠标抖一下，不记一笔
        self.ops.append({
            "kind": self.shape_var.get(),
            "color": self.color_var.get(),
            "width": max(1, int(self.width_var.get() or DEFAULT_WIDTH)),
            "x1": start[0], "y1": start[1], "x2": end[0], "y2": end[1],
        })
        self._redraw_ops()
        self.hint_var.set(f"已画 {len(self.ops)} 笔。")

    def _ask_text(self):
        anchor = self._pending_text
        self._pending_text = None
        if anchor is None:
            return
        text = self.ask_string(self.app_title, "标注文字：", parent=self)
        if not (text or "").strip():
            return
        self.ops.append({
            "kind": SHAPE_TEXT, "text": str(text).strip(),
            "color": self.color_var.get(),
            "width": max(1, int(self.width_var.get() or DEFAULT_WIDTH)),
            "x1": anchor[0], "y1": anchor[1], "x2": anchor[0], "y2": anchor[1],
        })
        self._redraw_ops()
        self.hint_var.set(f"已画 {len(self.ops)} 笔。")

    def undo(self):
        if self.ops:
            self.ops.pop()
            self._redraw_ops()
            self.hint_var.set(f"已画 {len(self.ops)} 笔。")

    def clear(self):
        self.ops = []
        self._redraw_ops()
        self.hint_var.set("已清空。")

    # ==================================================================
    # 预览
    # ==================================================================
    def _redraw_ops(self):
        self.canvas.delete("op")
        for op in normalize_ops(self.ops):
            self._draw_one(op)

    def _draw_one(self, op):
        """按 ops 画一个图元（画布坐标），返回它的 id。"""
        color = op["color"]
        width = max(1, int(op.get("width") or DEFAULT_WIDTH))
        (x1, y1) = self.to_canvas(op["x1"], op["y1"])
        (x2, y2) = self.to_canvas(op.get("x2", op["x1"]), op.get("y2", op["y1"]))
        tags = ("op",)
        kind = op["kind"]
        if kind == SHAPE_ELLIPSE:
            return self.canvas.create_oval(x1, y1, x2, y2, outline=color,
                                           width=width, tags=tags)
        if kind == SHAPE_RECT:
            return self.canvas.create_rectangle(x1, y1, x2, y2, outline=color,
                                                width=width, tags=tags)
        if kind == SHAPE_ARROW:
            item = self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width,
                                           arrow="last", arrowshape=(12, 14, 4),
                                           tags=tags)
            return item
        if kind == SHAPE_TEXT:
            return self.canvas.create_text(x1, y1, anchor="nw", fill=color,
                                           text=op.get("text", ""), tags=tags)
        return None

    # ==================================================================
    # 保存
    # ==================================================================
    def save(self):
        ops = normalize_ops(self.ops)
        if not ops:
            messagebox.showinfo(self.app_title, "还没有画任何标注。", parent=self)
            return False
        if self.on_save is None:
            self.destroy()
            return False
        keep_open = bool(self.on_save(ops))
        if not keep_open:
            self.destroy()
        return keep_open
