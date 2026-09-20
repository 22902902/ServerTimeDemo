# -*- coding: utf-8 -*-
"""统一 UI 组件层。

提供黑白扁平化风格下常用的：
1. 顶部动作按钮
2. 扁平卡片/分组区块
3. 状态文本与指标卡片
4. 自绘圆角胶囊 RoundedChip（Tk 原生画不出圆角）
5. 悬停浮层 HoverTooltip（Tk 没有原生 tooltip）
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except ImportError:          # 没有 Pillow 时退回多边形画法（会略方，但不崩）
    HAS_PIL = False

from ui_theme import MAIN_PALETTE, TYPOGRAPHY


def create_flat_action_button(parent, text: str, command, *, side: str | None = None, padx: int = 4):
    """★ 统一风格：与工具栏按钮保持一致（Quiet 样式，浅底无边框）。"""
    button = ttk.Button(parent, text=text, command=command, style="Quiet.TButton", width=0)
    if side:
        button.pack(side=side, padx=padx)
    return button


def create_section_frame(parent, title: str, *, padding=(16, 14)):
    """★ 统一卡片：走 Card.TLabelframe 样式，与 create_ttk_card 同一套外观。

    原实现用 tk.LabelFrame(bd=1, relief="solid")，边框颜色由 Tk 系统默认值决定，
    palette 管不到 —— 在 Windows 下渲染成深灰/黑边，这正是页面「硬」的主因。
    """
    return ttk.LabelFrame(parent, text=title, padding=padding, style="Card.TLabelframe")


def create_info_label(
    parent,
    *,
    textvariable=None,
    text: str | None = None,
    tone: str = "muted",
    wraplength: int = 920,
    bg: str | None = None,
):
    color_map = {
        "primary": MAIN_PALETTE.text_primary,
        "muted": MAIN_PALETTE.text_muted,
        "secondary": MAIN_PALETTE.text_secondary,
        "link": MAIN_PALETTE.link,
        "success": MAIN_PALETTE.success,
        "warn": MAIN_PALETTE.warn,
        "danger": MAIN_PALETTE.danger,
    }
    label = tk.Label(
        parent,
        text=text or "",
        textvariable=textvariable,
        bg=bg or MAIN_PALETTE.bg,
        fg=color_map.get(tone, MAIN_PALETTE.text_muted),
        wraplength=wraplength,
        justify="left",
    )
    return label


def create_metric_card(parent, title: str, value_var, desc: str):
    card = create_section_frame(parent, title)
    tk.Label(
        card,
        textvariable=value_var,
        bg=MAIN_PALETTE.bg,
        fg=MAIN_PALETTE.text_primary,
        font=TYPOGRAPHY.metric,
    ).pack(anchor="w")
    create_info_label(card, text=desc, tone="muted", wraplength=210).pack(anchor="w", pady=6)
    return card


def create_ttk_card(parent, title: str | None = None, *, padding=(12, 10)):
    if title:
        return ttk.LabelFrame(parent, text=title, padding=padding, style="Card.TLabelframe")
    return ttk.Frame(parent, padding=padding, style="Card.TFrame")


def create_ttk_section_header(parent, text: str):
    return ttk.Label(parent, text=text, style="SectionTitle.TLabel")


# ----------------------------------------------------------------------
# 自绘圆角胶囊
# ----------------------------------------------------------------------
CHIP_RADIUS = 6                     # 小控件圆角（与 ui_theme 的约定一致）
CHIP_FONT = ("Microsoft YaHei", 9)
CHIP_PADX = 11
CHIP_PADY = 4


def _rgba(color):
    """``#rrggbb`` / ``#rgb`` → (r, g, b, 255)。"""
    value = str(color).lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return (int(value[0:2], 16), int(value[2:4], 16),
            int(value[4:6], 16), 255)


def rounded_rect_image(width, height, radius, color, *, supersample=4):
    """把圆角矩形渲成一张 PIL 图（外圈透明）。没有 Pillow 时返回 None。

    为什么不能只靠 ``create_polygon(smooth=True)``
    ------------------------------------------------------------------
    实测（把屏幕像素打成 ASCII 看形状）：smooth 样条的实际圆角半径远小于设定值 ——
    设定半径 6，实际只把角切掉 1~2 像素，看上去基本还是直角，这正是「按钮很硬」
    的根源。再加上 ``tk.Canvas`` 没有抗锯齿，直角处会留下明显阶梯。
    项目本来就依赖 Pillow，在 4 倍超采样画布上画好再降采样，边缘才干净。
    """
    if not HAS_PIL:
        return None
    scale = max(1, int(supersample))
    big = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    r = max(0.0, min(float(radius), width / 2.0, height / 2.0))
    draw.rounded_rectangle([0, 0, width * scale - 1, height * scale - 1],
                           radius=r * scale, fill=_rgba(color))
    return big.resize((width, height), Image.LANCZOS)


def rounded_rect_points(x1, y1, x2, y2, r):
    """圆角矩形的多边形顶点（配合 ``create_polygon(smooth=True)`` 使用）。

    ``tk.Canvas`` 没有圆角矩形图元，``tk.Label`` / ``ttk.Button`` 更画不出圆角，
    这就是本项目「圆角只能靠自绘」那条约定的由来。每个角给三个顶点，
    平滑样条就能把直角收成一段圆弧。
    """
    r = max(0.0, min(float(r), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [x1 + r, y1, x2 - r, y1, x2, y1,
            x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2,
            x1, y2 - r, x1, y1 + r, x1, y1]


class RoundedChip(tk.Canvas):
    """圆角胶囊（分类筛选、快捷启动都用它）。

    为什么不用 ttk.Button / tk.Label
    --------------------------------
    两者都是硬边矩形，摆一排就是「硬」。Canvas 自绘圆角 + 悬停/选中换底色才做得出
    轻巧的观感。另外必须把 ``highlightthickness`` 关掉 —— 它默认是 1，
    会在每颗胶囊外面加一圈边框，正是「按钮很硬」的来源之一。

    三种状态：常态 / 悬停 / 选中，另有 ``set_drop_highlight`` 供拖放高亮。
    颜色一律由调用方传入，本组件不绑定调色板。
    """

    def __init__(self, parent, text, *, bg, fg, canvas_bg=None,
                 hover_bg=None, hover_fg=None, active_bg=None, active_fg=None,
                 active=False, radius=CHIP_RADIUS, padx=CHIP_PADX,
                 pady=CHIP_PADY, font=CHIP_FONT, cursor="hand2", command=None):
        self._text = text
        self._bg, self._fg = bg, fg
        self._hover_bg = hover_bg or bg
        self._hover_fg = hover_fg or fg
        self._active_bg = active_bg or bg
        self._active_fg = active_fg or fg
        self._active = bool(active)
        self._hover = False
        self._drop = False
        self._radius = radius
        self._padx, self._pady = padx, pady
        self._font = tkfont.Font(font=font)
        self._command = command
        # 圆角底图按 (宽, 高, 半径, 颜色) 缓存：悬停/选中来回切成千上万次，
        # 不能每次都重渲一张图。缓存同时负责持有引用，否则位图会被 GC 回收。
        self._bg_cache: dict = {}

        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=canvas_bg or bg, cursor=cursor, takefocus=0)
        self._paint()

        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))
        if command is not None:
            self.bind("<Button-1>", self._invoke)

    # -- 对外状态 ----------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def text(self) -> str:
        """当前文案。Canvas 的文本是图元，没法像 tk.Label 那样 cget。"""
        return self._text

    @property
    def fill_color(self) -> str:
        """当前实际画出来的底色（断言与调试用）。"""
        return self._colors()[0]

    def set_active(self, value: bool):
        value = bool(value)
        if value != self._active:
            self._active = value
            self._paint()
        return self

    def set_text(self, text: str):
        if text != self._text:
            self._text = text
            self._paint()
        return self

    def set_hover(self, value: bool):
        value = bool(value)
        if value != self._hover:
            self._hover = value
            self._paint()
        return self

    def set_drop_highlight(self, value: bool):
        """拖放悬停态：借用选中配色，一眼能看出「松手就落到这个分类」。"""
        value = bool(value)
        if value != self._drop:
            self._drop = value
            self._paint()
        return self

    def _invoke(self, _event=None):
        if self._command is not None:
            self._command()

    # -- 绘制 --------------------------------------------------------
    def _colors(self):
        if self._drop or self._active:
            return self._active_bg, self._active_fg
        if self._hover:
            return self._hover_bg, self._hover_fg
        return self._bg, self._fg

    def _background(self, w, h, color):
        """取（并缓存）当前颜色的圆角底图。渲染失败返回 None → 退回多边形。"""
        key = (w, h, self._radius, color)
        photo = self._bg_cache.get(key)
        if photo is None:
            pil = rounded_rect_image(w, h, self._radius, color)
            if pil is None:
                return None
            try:
                # 显式绑 master：不传会取 tkinter._default_root，
                # 而那个 root 未必是本画布所在的解释器
                photo = ImageTk.PhotoImage(pil, master=self)
            except Exception:
                return None
            self._bg_cache[key] = photo
        return photo

    def _paint(self):
        self.delete("all")
        w = self._font.measure(self._text) + 2 * self._padx
        h = self._font.metrics("linespace") + 2 * self._pady
        self.configure(width=w, height=h)
        bg, fg = self._colors()
        image = self._background(w, h, bg)
        if image is not None:
            self.create_image(0, 0, anchor="nw", image=image)
        else:
            self.create_polygon(rounded_rect_points(0, 0, w, h, self._radius),
                                smooth=True, fill=bg, outline="")
        self.create_text(w / 2.0, h / 2.0, text=self._text, fill=fg,
                         font=self._font)


class HoverTooltip:
    """鼠标悬停在某个控件上时弹出的说明浮层。

    为什么需要一个自绘的
    ------------------------------------------------------------------
    Tk 没有原生 tooltip。纯粹的图标视图里没有文字，必须靠悬停把
    「这是什么」补上；而把它塞进状态条又离指针太远，眼睛要来回跑。

    为什么用深色
    ------------------------------------------------------------------
    页面本身是白底灰阶，浅色浮层压上去几乎看不出边界（这也是先前
    胶囊底色踩过的坑）。近黑是这套设计里唯一的强调色，拿它当浮层既
    清楚又不引入新颜色。颜色由调用方传入，深浅都可以。

    防抖要点
    ------------------------------------------------------------------
    Tk 里指针从父控件移到子控件会先给父控件一个 ``<Leave>``。
    卡片由「容器 + 图标 + 文字」多个控件拼成，若一收到 Leave 就关掉，
    浮层会在卡片内部移动时疯狂闪烁。所以真正关闭前要用
    ``winfo_pointerxy()`` 复核指针是否还在绑定的控件矩形内 ——
    浅底侧栏的悬停也是靠同一手法解决的。
    """

    def __init__(self, widget, text_fn, *, delay: int = 260,
                 bg: str = "#1c1c1c", fg: str = "#ffffff",
                 sub_fg: str = "#b9b9b9", offset=(16, 22)):
        self.widget = widget
        self.text_fn = text_fn          # 返回 (主标题, 副标题) 或单个字符串
        self.delay = delay
        self.bg = bg
        self.fg = fg
        self.sub_fg = sub_fg
        self.offset = offset
        self._tip = None
        self._title_label = None
        self._sub_label = None
        self._after_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")

    # ---- 对外 ----
    def watch(self, *widgets):
        """把更多控件纳入同一个浮层；「指示区」仍是构造时那个控件。

        一格由容器 + 图标 + 角标等多个控件拼成，Enter/Leave 是逐控件派发的：
        只绑外层容器的话，指针直接从格子外落到图标上时外层收不到 Enter，
        浮层就不出现。子控件绑上同一套回调后，进出一格都能正确开关；
        而「指针还在不在这一格」始终按容器矩形判定，所以卡内部移动不会闪。
        """
        for widget in widgets:
            if widget is None or widget is self.widget:
                continue
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
            widget.bind("<ButtonPress>", self._on_leave, add="+")
        return self

    def hide(self):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.withdraw()
            except tk.TclError:
                pass

    def destroy(self):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    # ---- 内部 ----
    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except (tk.TclError, ValueError):
                pass
            self._after_id = None

    def _pointer_inside(self):
        """指针是否还在绑定控件内 —— 用来把「移进子控件」当成仍在悬停。"""
        try:
            px, py = self.widget.winfo_pointerxy()
            x, y = self.widget.winfo_rootx(), self.widget.winfo_rooty()
            w, h = self.widget.winfo_width(), self.widget.winfo_height()
        except tk.TclError:
            return False
        if w <= 1 or h <= 1:
            return False
        return x <= px <= x + w and y <= py <= y + h

    def _on_enter(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _on_leave(self, _event=None):
        self._cancel()
        if self._pointer_inside():
            return          # 只是移到卡片内的另一个子控件，别关
        self.hide()

    def _on_destroy(self, _event=None):
        self.destroy()

    def _ensure_window(self):
        if self._tip is not None:
            return
        tip = tk.Toplevel(self.widget)
        tip.withdraw()
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(tip, bg=self.bg, highlightthickness=0, bd=0)
        frame.pack(fill="both", expand=True)
        self._title_label = tk.Label(frame, bg=self.bg, fg=self.fg,
                                     font=("Microsoft YaHei", 9), justify="left")
        self._title_label.pack(anchor="w", padx=10, pady=(7, 0))
        self._sub_label = tk.Label(frame, bg=self.bg, fg=self.sub_fg,
                                   font=("Microsoft YaHei", 8), justify="left")
        self._sub_label.pack(anchor="w", padx=10, pady=(0, 7))
        self._tip = tip

    def _show(self):
        self._after_id = None
        if not self.widget.winfo_exists():
            return
        try:
            content = self.text_fn()
        except tk.TclError:
            return
        if isinstance(content, (tuple, list)):
            title = content[0] if content else ""
            sub = content[1] if len(content) > 1 else ""
        else:
            title, sub = content, ""
        if not title and not sub:
            return

        self._ensure_window()
        if self._title_label is None or self._sub_label is None:
            return
        self._title_label.configure(text=title)
        if sub:
            self._sub_label.configure(text=sub)
            if not self._sub_label.winfo_ismapped():
                self._sub_label.pack(anchor="w", padx=10, pady=(0, 7))
        else:
            self._sub_label.pack_forget()

        tip = self._tip
        tip.update_idletasks()
        tw, th = tip.winfo_reqwidth(), tip.winfo_reqheight()
        px, py = self.widget.winfo_pointerxy()
        x, y = px + self.offset[0], py + self.offset[1]
        # 贴到屏幕右/下边缘时翻到另一侧，否则浮层会被切掉
        screen_w = tip.winfo_screenwidth()
        screen_h = tip.winfo_screenheight()
        if x + tw > screen_w - 4:
            x = max(screen_w - tw - 4, 4)
        if y + th > screen_h - 4:
            y = max(py - th - 10, 4)
        tip.geometry(f"{tw}x{th}+{int(x)}+{int(y)}")
        tip.deiconify()
        try:
            tip.lift()
        except tk.TclError:
            pass

