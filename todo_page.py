# -*- coding: utf-8 -*-
"""
================================================================================
待办事项模块 - 界面层（View Layer）
================================================================================
把苹果「提醒事项」的三栏结构翻译到桌面窗口：

    ┌──────────┬──────────────┬──────────────────────────────┐
    │ 智能分组  │  当前视图的   │   详情面板                    │
    │ 我的列表  │  待办条目     │   标题 / 备注 / 日期 / 重复…   │
    │（彩色图标）│  （圆形勾选） │   子任务                      │
    └──────────┴──────────────┴──────────────────────────────┘

设计取舍（与项目整体风格的对齐）
--------------------------------------------------------------------------------
* 左侧沿用全局的浅灰侧栏色（#f4f4f4），与主程序左侧导航同色，两块不打架。
* **彩色只出现在两处**：清单图标与「今天」标题。勾选框、按钮、正文一律走灰阶，
  这样既保住了「一眼看出这是哪个清单」的信息量，又不会把整屏染花。
* Tk 画不出圆角与阴影，因此圆形勾选框、清单图标全部用 ``todo_icons`` 里的
  Pillow 资产**自绘**；最终是「克制的桌面版苹果风」，不是像素级复刻。

编辑即保存
--------------------------------------------------------------------------------
标题与备注在失焦或切换条目时写库（``_flush_editor``），没有「保存」按钮 ——
与苹果一致。切换清单 / 搜索 / 勾选都会先 flush 一次，不会丢字。
"""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import font as tkfont, messagebox, simpledialog, ttk
from typing import Optional

import todo_icons
from app_icons import scaled_px
from todo_db import (
    ADVANCE_CHOICES,
    ALERT_STAGE_EARLY,
    LIST_COLORS,
    LIST_ICONS,
    PRIORITY_LABELS,
    REPEAT_RULES,
    REPEAT_UNITS,
    SMART_LISTS,
    SNOOZE_MINUTES,
    TodoDB,
    TodoItem,
    TodoList,
    advance_label,
    alert_moment,
    day_str,
    parse_day,
)
from ui_components import ScrollArea, create_flat_menu
from ui_theme import MAIN_PALETTE, TYPOGRAPHY

# 字体：页内大标题用 17pt 粗体（比全局 page_title 略大，用来和主壳标题区分层级）
FONT_PANE_TITLE = ("Microsoft YaHei UI", 17, "bold")
FONT_ROW_TITLE = ("Microsoft YaHei UI", 10)
FONT_ROW_META = ("Microsoft YaHei UI", 9)
FONT_SMALL_BOLD = ("Microsoft YaHei UI", 9, "bold")
FONT_DETAIL_TITLE = ("Microsoft YaHei UI", 12, "bold")

# 尺寸
SIDEBAR_WIDTH = 226
MIDDLE_WIDTH = 388
ICON_PX = 15          # 线性小图标逻辑尺寸（与导航图标一致）
TILE_PX = 15          # 清单图标逻辑尺寸
CHECK_PX = 18         # 勾选框逻辑尺寸
ROW_PAD_Y = 6

# 智能分组的配色（沿用苹果的语义色，但只落在图标上）
SMART_META = {
    "today": ("sun", "#007AFF"),
    "scheduled": ("calendar", "#FF3B30"),
    "all": ("list", "#8E8E93"),
    "flagged": ("flag", "#FF9500"),
    "completed": ("subtask", "#8E8E93"),
}
WEEKDAY_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
# 清单查不到时（数据异常、扩展名被手工改过）统一退回这个中灰，
# 避免在页面里到处散落颜色字面量
FALLBACK_COLOR = "#8E8E93"

# 到点提醒窗（贴屏幕右下角，像系统通知）
ALERT_WIDTH = 340          # 固定宽度：通知要一眼看完，不做自适应
ALERT_MIN_HEIGHT = 116
ALERT_MARGIN = 24          # 距屏幕右边 / 下边的留白
DRAG_THRESHOLD = 5         # 按住后纵向挪这么多像素才算「拖」，否则当点击
DROP_LINE_H = 2            # 拖动时插入指示线的高度
DROP_LINE_PAD = 8          # 插入线在侧栏里的左右留白
DRAG_EDGE = 22             # 拖到清单区上下边缘这么多像素内就开始自动滚
DRAG_SCROLL_MS = 40        # 自动滚的节拍（毫秒）
DRAG_SCROLL_STEP = 4       # 每拍滚多少像素
BADGE_H = 17               # 侧栏计数角标的高度（逻辑像素）
BADGE_PAD_X = 6            # 角标左右内边距，数字不贴边
ALERT_BOTTOM_GAP = 68      # 给任务栏留的位置


# =============================================================================
# 通用小组件
# =============================================================================

def tint(widget, bg: str):
    """把一棵控件树里所有 tk 控件的背景改成 bg（ttk 控件跳过）。

    自绘行要整体变底色就得逐个改，tk 没有继承背景的概念。
    """
    try:
        if isinstance(widget, tk.Frame) or isinstance(widget, tk.Label):
            widget.configure(bg=bg)
        elif isinstance(widget, tk.Canvas):
            widget.configure(bg=bg)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        tint(child, bg)

def compute_drop_order(ordered_ids, dragged_id, index):
    """把 dragged_id 挪到 index 号间隙后，返回新的顺序列表。

    ``index`` 是相对**原序列**的间隙号（0..len），被拖项自己不占位：

        [A, B, C] 把 C 拖到间隙 0 -> [C, A, B]
        [A, B, C] 把 A 拖到间隙 2 -> [B, A, C]

    抽成纯函数是因为「间隙号 -> 新顺序」这个换算是拖动里唯一算错会静默
    错位的地方（拖了没反应 / 跳错位置），单独钉住最好测。
    """
    rest = [item for item in ordered_ids if item != dragged_id]
    before = [item for item in ordered_ids[:index] if item != dragged_id]
    cut = len(before)
    return rest[:cut] + [dragged_id] + rest[cut:]


# 带删除线的字体缓存：键是 (字族, 字号, 字重...)，见 strike_font()
_STRIKE_FONTS: dict = {}


def strike_font(base, widget):
    """把元组字体转成带删除线的 ``tkinter.font.Font``。

    Tk 只有 ``Font`` 对象支持 ``overstrike``（``underline`` 同理），
    元组字体 ``("Microsoft YaHei UI", 10)`` 带不动 —— 「已完成」的
    那道横线只能走这条路。字号字重仍取自传入的字体常量，不新增样式。

    缓存有两个坑：
    * 键要带字族 / 字号 / 字重，否则 10pt 正文与 12pt 粗体会互相串用；
    * ``Font`` 绑在某个 Tk 解释器上，解释器换了（测试里 destroy 后重开
      root）旧对象就是废的，所以命中缓存后要 ``actual()`` 探一次活。
    """
    key = tuple(base)
    cached = _STRIKE_FONTS.get(key)
    if cached is not None:
        try:
            cached.actual()
            return cached
        except tk.TclError:
            _STRIKE_FONTS.pop(key, None)
    styles = tuple(base[2:])
    font = tkfont.Font(root=widget, family=base[0], size=base[1],
                       weight=("bold" if "bold" in styles else "normal"),
                       overstrike=1)
    _STRIKE_FONTS[key] = font
    return font


# =============================================================================
# 主页面
# =============================================================================

class TodoAlertDialog(tk.Toplevel):
    """到点提醒窗（苹果那一声「叮」的桌面版）。

    刻意**不像一个对话框**：贴在屏幕右下角、不抢键盘焦点、不 modal ——
    提醒不该把正在打字的人拽走。能做的三件事：点某条跳过去看它、推
    十分钟再来、或者一次全部完成；窗口标题栏的叉等于「知道了」。

    同时到点的多条排在同一个窗口里：蹦五个窗口比一个窗口里列五条烦得多。

    窗口本身不区分「提前」与「到点」两档 —— 区别体现在头部那句话和每条
    下面那行说明上（``stages`` 由调用方从 ``pending_alerts`` 带进来）。
    """

    def __init__(self, master, items, *, db, palette=MAIN_PALETTE,
                 typography=TYPOGRAPHY, snooze_minutes: int = SNOOZE_MINUTES,
                 stages: Optional[dict] = None,
                 on_changed=None, on_open=None):
        super().__init__(master)
        self.db = db
        self.palette = palette
        self.typography = typography
        self.snooze_minutes = snooze_minutes
        self.on_changed = on_changed
        self.on_open = on_open
        self.items = list(items)
        # item_id -> "early" / "due"；缺省全当「到点」（也能被单独构造，
        # 比如测试或将来别处复用这个窗口）
        self.stages = dict(stages or {})
        self._rows: dict[int, tk.Frame] = {}
        self._icon_px = scaled_px(self, ICON_PX)

        self.title("提醒事项")
        self.configure(bg=palette.surface)
        self.resizable(False, False)
        try:
            self.transient(master.winfo_toplevel() if master is not None else None)
        except Exception:
            pass
        # 浮在最上面（提醒本来就该压过别的窗口），但**不抢键盘焦点**
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        self._build()
        self._place_bottom_right()
        self.bind("<Escape>", lambda _e: self.destroy())

    # -- 构建 ----------------------------------------------------------
    def _build(self):
        palette = self.palette
        head = tk.Frame(self, bg=palette.surface)
        head.pack(fill="x", padx=16, pady=(14, 8))
        # 头部就一行：**窗口标题栏已经写着「提醒事项」**，内容区再来一个
        # 同名大标题等于同一句话说两遍（这条规矩在本项目里已经踩过一次）
        tk.Label(head, image=todo_icons.glyph_image(
            self._icon_px, "bell", palette.text_secondary),
            bg=palette.surface).pack(side="left", padx=(0, 6))
        tk.Label(head, text=self._subtitle_text(), bg=palette.surface,
                 fg=palette.text_secondary,
                 font=self.typography.caption).pack(side="left")

        self._holder = tk.Frame(self, bg=palette.surface)
        self._holder.pack(fill="x", padx=10)
        for item in self.items:
            self._add_row(item)

        footer = tk.Frame(self, bg=palette.surface)
        footer.pack(fill="x", padx=16, pady=(10, 14))
        ttk.Button(footer, text=f"稍后提醒 {self.snooze_minutes} 分钟",
                   style="Quiet.TButton",
                   command=self.snooze_all).pack(side="left")
        ttk.Button(footer, text="全部完成" if len(self.items) > 1 else "完成",
                   style="Primary.TButton",
                   command=self.complete_all).pack(side="right")

    def _subtitle_text(self) -> str:
        """头部那句话：提前档说「快到了」，到点档说「到时间了」。

        两档混在一个窗口里时（一条提前、另一条正好到点）说明张数，
        不硬凑一句话 —— 一句话里塞两种语义只会让人先读完再理解。
        """
        total = len(self.items)
        early = sum(1 for it in self.items
                    if self.stages.get(it.id) == ALERT_STAGE_EARLY)
        if early and early == total:
            tail = "快到时间了" if total == 1 else f"{total} 条快到时间了"
        elif early:
            tail = f"{total} 条提醒（{early} 条提前，{total - early} 条到点）"
        else:
            tail = "到时间了" if total == 1 else f"{total} 条到时间了"
        return f"提醒事项 · {tail}"

    def _add_row(self, item: TodoItem):
        palette = self.palette
        row = tk.Frame(self._holder, bg=palette.surface)
        row.pack(fill="x", pady=2)

        info = self.db.get_list(item.list_id)
        color = info.color if info else FALLBACK_COLOR
        dot = tk.Canvas(row, width=10, height=10, bg=palette.surface,
                        highlightthickness=0, bd=0)
        # anchor="n"：点子要贴标题第一行。默认的垂直居中会让它在「标题 +
        # 时刻」两行之间悬着，看着不知道该归属谁
        dot.pack(side="left", anchor="n", padx=(6, 8), pady=(6, 0))
        dot.create_oval(1, 1, 9, 9, fill=color, outline="")

        body = tk.Frame(row, bg=palette.surface)
        body.pack(side="left", fill="x", expand=True)
        tk.Label(body, text=item.title or "(无标题)", bg=palette.surface,
                 fg=palette.text_primary, font=FONT_ROW_TITLE,
                 anchor="w", justify="left",
                 wraplength=ALERT_WIDTH - 110).pack(anchor="w")
        tk.Label(body, text=self._when_text(item), bg=palette.surface,
                 fg=palette.text_muted, font=FONT_ROW_META,
                 anchor="w").pack(anchor="w")

        self._rows[item.id] = row
        if callable(self.on_open):
            for widget in (row, body, dot):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e, i=item: self._open(i))

    def _when_text(self, item: TodoItem) -> str:
        """每行下面那行小字。

        到点档只写时刻（条目的日期已经在它自己的列表里了）；提前档多写
        一句「还有多久」—— 提前提醒的全部意义就是那个余量。
        """
        moment = alert_moment(item)
        if moment is None:
            return ""
        clock = moment.strftime("%H:%M")
        if self.stages.get(item.id) != ALERT_STAGE_EARLY:
            return clock
        minutes = max(0, int((moment - datetime.now()).total_seconds() // 60))
        if minutes >= 60:
            hours, rest = divmod(minutes, 60)
            span = f"{hours} 小时" + (f" {rest} 分" if rest else "")
        else:
            span = f"{minutes} 分钟"
        return f"{clock} · 还有 {span}"

    # -- 动作 ----------------------------------------------------------
    def _open(self, item: TodoItem):
        if callable(self.on_open):
            self.on_open(item.id)
        self.destroy()

    def snooze_all(self):
        for item in self.items:
            # 提前档打盹只把提前那一档往后挪，当天的到点还得照响
            early = self.stages.get(item.id) == ALERT_STAGE_EARLY
            self.db.snooze(item.id, self.snooze_minutes, early=early)
        self._changed()

    def complete_all(self):
        for item in self.items:
            self.db.set_completed(item.id, True)
        self._changed()

    def _changed(self):
        if callable(self.on_changed):
            self.on_changed()
        self.destroy()

    # -- 摆位 ----------------------------------------------------------
    def _place_bottom_right(self):
        """贴屏幕右下角（像系统通知），**不**居中到主窗口上。

        主窗口可能已经缩进托盘了 —— 那种时候「居中」等于把提醒藏起来。
        """
        self.update_idletasks()
        width = ALERT_WIDTH
        height = max(ALERT_MIN_HEIGHT, self.winfo_reqheight())
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, screen_w - width - ALERT_MARGIN)
        y = max(0, screen_h - height - ALERT_BOTTOM_GAP)
        self.geometry(f"{width}x{height}+{x}+{y}")


class TodoPage(ttk.Frame):
    """待办 / 提醒事项页面。

    使用方式（由 main.py 构建一次，之后靠 pack/pack_forget 切换）::

        page = TodoPage(self.todo_page_container, self.todo_db)
        page.pack(fill="both", expand=True)
    """

    def __init__(self, master, todo_db: TodoDB, *,
                 palette=MAIN_PALETTE, typography=TYPOGRAPHY):
        super().__init__(master)
        self.palette = palette
        self.typography = typography
        self.db = todo_db

        # 视图状态
        self.current_scope = "today"     # 智能分组 key
        self.current_list_id: Optional[int] = None  # 选中的真实清单
        self.selected_item_id: Optional[int] = None
        self.keyword = ""
        # 「显示已完成」是持久偏好（落在 todo_state 里），不是一次性动作 ——
        # 苹果那个 Show Completed 也是记着的。开着时已完成项沉在列表末尾、
        # 带删除线，点圆圈可以恢复。
        self.show_completed = self.db.get_state("show_completed", "0") == "1"
        self._groups: dict[str, tk.Frame] = {}      # 侧栏行缓存
        self._row_widgets: dict[int, tk.Frame] = {}
        self._loading = False                        # 载入编辑器时抑制写库
        self._detail_area: Optional[ScrollArea] = None
        self._drag: Optional[dict] = None             # 清单拖动排序的进行态
        self._drop_line: Optional[tk.Frame] = None    # 插入位置那条横线
        self._empty_state: Optional[tk.Frame] = None
        self._auto_scroll_dir = 0                     # 拖动自动滚的方向 -1/0/1
        self._auto_scroll_job = None                  # 自动滚的 after 句柄

        self._icon_px = scaled_px(self, ICON_PX)
        self._tile_px = scaled_px(self, TILE_PX)
        self._check_px = scaled_px(self, CHECK_PX)
        self._badge_h = scaled_px(self, BADGE_H)
        self._badge_pad = scaled_px(self, BADGE_PAD_X)
        # 量角标宽度得用**真字体对象**：点数换算成像素随系统缩放而变，
        # 自己按「一个数字几像素」估会在高分屏上撑破胶囊
        self._badge_font = tkfont.Font(font=self.typography.badge, root=self)

        self._build()
        self.refresh_all()

    # ==================================================================
    # 构架
    # ==================================================================
    def _build(self):
        palette = self.palette
        panes = tk.Frame(self, bg=palette.surface)
        panes.pack(fill="both", expand=True)

        # —— 左：分组 + 清单 ——
        self.sidebar = tk.Frame(panes, bg=palette.sidebar_bg, width=SIDEBAR_WIDTH)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        tk.Frame(panes, bg=palette.border, width=1).pack(side="left", fill="y")

        # —— 中：条目列表 ——
        self.middle = tk.Frame(panes, bg=palette.surface, width=MIDDLE_WIDTH)
        self.middle.pack(side="left", fill="y")
        self.middle.pack_propagate(False)
        self._build_middle()

        tk.Frame(panes, bg=palette.border, width=1).pack(side="left", fill="y")

        # —— 右：详情（最后 pack，吃掉剩余宽度）——
        self.detail = tk.Frame(panes, bg=palette.surface)
        self.detail.pack(side="left", fill="both", expand=True)
        self._build_detail()

    # ------------------------------------------------------------------
    # 左侧栏
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        palette = self.palette
        wrap = tk.Frame(self.sidebar, bg=palette.sidebar_bg)
        wrap.pack(fill="both", expand=True, padx=10, pady=(10, 8))

        # 搜索框
        search_box = tk.Frame(wrap, bg=palette.chip_bg)
        search_box.pack(fill="x", pady=(0, 10))
        tk.Label(search_box, image=todo_icons.glyph_image(
            self._icon_px, "search", palette.text_muted),
            bg=palette.chip_bg).pack(side="left", padx=(8, 4), pady=5)
        self.search_var = tk.StringVar()
        entry = tk.Entry(search_box, textvariable=self.search_var, bd=0,
                         bg=palette.chip_bg, fg=palette.text_primary,
                         font=self.typography.body, insertbackground=palette.text_primary)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=5)
        entry.bind("<KeyRelease>", self._on_search_change)
        self._search_entry = entry
        self._search_placeholder = self._set_placeholder(entry, "搜索")

        # 智能分组
        for key, label in SMART_LISTS:
            self._make_side_row(wrap, kind="smart", key=key, label=label)

        tk.Frame(wrap, bg=palette.sidebar_bg, height=10).pack(fill="x")

        # 「我的列表」标题行 + 新建
        head = tk.Frame(wrap, bg=palette.sidebar_bg)
        head.pack(fill="x", pady=(6, 2))
        tk.Label(head, text="我的列表", bg=palette.sidebar_bg,
                 fg=palette.text_muted, font=self.typography.nav_group,
                 anchor="w").pack(side="left", padx=6)
        add_btn = tk.Label(head, text="＋", bg=palette.sidebar_bg,
                           fg=palette.text_muted, font=self.typography.body,
                           cursor="hand2", padx=6)
        add_btn.pack(side="right")
        add_btn.bind("<Button-1>", lambda _e: self.new_list_dialog())
        self._add_list_btn = add_btn

        # 清单多了要能滚：这一段独占剩余高度，滚动条**按需**出现
        # （只有三五条清单时不该在侧栏里杵一根灰条）。
        # 拖着重排时贴到上下边缘会自动滚，见 _sync_auto_scroll。
        area = ScrollArea(wrap, bg=palette.sidebar_bg, autohide_scrollbar=True)
        area.pack(fill="both", expand=True, pady=(4, 0))
        self._list_area = area
        self._list_canvas = area.canvas
        self._list_holder = area.inner

    def _make_side_row(self, parent, *, kind: str, key, label: str):
        """侧栏一行：图标 + 名称 + 右侧计数。kind 为 smart / list。"""
        palette = self.palette
        row = tk.Frame(parent, bg=palette.sidebar_bg, cursor="hand2")
        row.pack(fill="x")

        accent = tk.Frame(row, width=2, bg=palette.sidebar_bg)
        accent.pack(side="left", fill="y")

        icon_holder = tk.Frame(row, bg=palette.sidebar_bg, width=self._tile_px,
                               height=self._tile_px)
        icon_holder.pack(side="left", padx=(8, 8), pady=ROW_PAD_Y)
        icon_holder.pack_propagate(False)
        icon = tk.Label(icon_holder, bg=palette.sidebar_bg, bd=0,
                        highlightthickness=0)
        icon.pack(fill="both", expand=True)

        text = tk.Label(row, text=label, bg=palette.sidebar_bg,
                        fg=palette.nav_text, font=self.typography.nav_item,
                        anchor="w")
        text.pack(side="left", fill="x", expand=True, pady=ROW_PAD_Y)

        # 计数是个角标（圆角胶囊）：字重取 badge（比 caption 粗一档），
        # 底图与深浅由 _set_badge 按「有没有逾期」决定
        count = tk.Label(row, text="", bg=palette.sidebar_bg,
                         fg=palette.text_muted, font=self.typography.badge)
        count.pack(side="right", padx=(4, 10))

        for widget in (row, accent, icon_holder, icon, text, count):
            widget.bind("<Enter>", lambda _e, r=row: self._hover_side(r, kind, key))
            widget.bind("<Leave>", lambda _e, r=row: self._leave_side(r, kind, key))
        if kind == "list":
            # 清单行按住可以拖动重排。按下只记起点，真挪动过才算拖 ——
            # 没挪动就走单击（选中它），见 _list_drag_release。
            for widget in (row, accent, icon_holder, icon, text, count):
                widget.bind("<Button-1>",
                            lambda e, kk=key: self._list_drag_press(kk, e))
                widget.bind("<B1-Motion>",
                            lambda e, kk=key: self._list_drag_motion(kk, e))
                widget.bind("<ButtonRelease-1>",
                            lambda e, kk=key: self._list_drag_release(kk, e))
            row.bind("<Button-3>", lambda _e, kk=key: self._list_context_menu(kk))
        else:
            row.bind("<Button-1>", lambda _e, k=kind, kk=key: self._select_side(k, kk))
            for widget in (accent, icon_holder, icon, text, count):
                widget.bind("<Button-1>",
                            lambda _e, k=kind, kk=key: self._select_side(k, kk))

        if kind == "smart":
            self._groups[f"smart:{key}"] = row
            self._smart_rows = getattr(self, "_smart_rows", {})
            self._smart_rows[key] = {"row": row, "accent": accent,
                                     "icon_holder": icon_holder, "icon": icon,
                                     "text": text, "count": count}
        else:
            self._groups[f"list:{key}"] = row
            self._list_rows = getattr(self, "_list_rows", {})
            self._list_rows[key] = {"row": row, "accent": accent,
                                    "icon_holder": icon_holder, "icon": icon,
                                    "text": text, "count": count}

    def _hover_side(self, row, kind, key):
        # 拖动中鼠标会扫过别的行，别让 hover 把「拿起来」的视觉冲掉
        if self._drag and self._drag["moved"]:
            return
        if row.cget("bg") == self.palette.sidebar_active:
            return
        self._paint_side_row(kind, key, bg=self.palette.sidebar_hover)

    def _leave_side(self, row, kind, key):
        if self._drag and self._drag["moved"]:
            return
        state = self._row_state(kind, key)
        if state == "active":
            return
        self._paint_side_row(kind, key, bg=self.palette.sidebar_bg)

    def _row_state(self, kind, key) -> str:
        if kind == "smart" and self.current_list_id is None and self.current_scope == key:
            return "active"
        if kind == "list" and self.current_list_id == key:
            return "active"
        return "normal"

    def _paint_side_row(self, kind, key, *, bg=None):
        rows = self._smart_rows if kind == "smart" else self._list_rows
        widgets = rows.get(key)
        if not widgets:
            return
        state = self._row_state(kind, key)
        if bg is None:
            bg = self.palette.sidebar_active if state == "active" else self.palette.sidebar_bg
        fg = self.palette.text_primary if state == "active" else self.palette.nav_text
        font = (self.typography.nav_item_active if state == "active"
                else self.typography.nav_item)
        accent = self.palette.accent if state == "active" else bg
        for name in ("row", "icon_holder", "icon", "text", "count"):
            widgets[name].configure(bg=bg)
        widgets["accent"].configure(bg=accent)
        widgets["text"].configure(fg=fg, font=font)
        # 角标里的数字颜色跟着「底」走：标红的角标反白，灰角标沿用浅灰
        if widgets.get("badge_urgent"):
            count_fg = self.palette.accent_text
        else:
            count_fg = (self.palette.text_secondary if state == "active"
                        else self.palette.text_muted)
        widgets["count"].configure(fg=count_fg)
        widgets["icon"].configure(image=self._side_icon(kind, key))

    def _side_icon(self, kind, key):
        if kind == "smart":
            name, color = SMART_META.get(key, ("list", FALLBACK_COLOR))
            return todo_icons.glyph_image(self._icon_px, name, color)
        todo_list = self.db.get_list(int(key))
        if not todo_list:
            return todo_icons.tile_image(self._tile_px, FALLBACK_COLOR, "list")
        return todo_icons.tile_image(self._tile_px, todo_list.color, todo_list.icon)

    def _select_side(self, kind, key):
        self._flush_editor()
        if kind == "smart":
            self.current_scope = key
            self.current_list_id = None
        else:
            self.current_list_id = int(key)
            self.current_scope = "list"
        self.selected_item_id = None
        self.refresh_all()
        if self.current_list_id is not None:
            self._render_item_list()

    # -- 清单拖动排序 ---------------------------------------------------
    def _list_drag_press(self, list_id, event):
        widgets = self._list_rows.get(int(list_id))
        # 记下鼠标按在该行内的偏移：换位看的是被拖行的**中心线**，
        # 不是鼠标点 —— 否则按住行的下缘时会提前一整行换位，不跟手
        offset = (event.y_root - widgets["row"].winfo_rooty()) if widgets else 0.0
        self._stop_auto_scroll()
        self._drag = {"list_id": int(list_id), "start_y": event.y_root,
                      "offset": offset, "moved": False, "index": None,
                      "pointer_y": event.y_root}

    def _list_drag_motion(self, list_id, event):
        drag = self._drag
        if not drag:
            return
        if not drag["moved"]:
            # 手抖一两个像素不算拖，否则每次点清单都会变成重排
            if abs(event.y_root - drag["start_y"]) < DRAG_THRESHOLD:
                return
            drag["moved"] = True
            self._begin_drag_visual(drag["list_id"])
        drag["pointer_y"] = event.y_root
        self._refresh_drop_target()
        self._sync_auto_scroll()

    def _refresh_drop_target(self):
        """按指针当前位置重算插入间隙并画线。

        单独抽出来是因为**自动滚的时候也要重算** —— 内容一动，指针底下
        压着的行就换了，不重算的话插入线会停在一个早已不对的位置上。
        """
        drag = self._drag
        if not drag or not drag.get("moved"):
            return
        row = self._list_rows.get(drag["list_id"], {}).get("row")
        height = row.winfo_height() if row is not None else 0
        pointer = drag.get("pointer_y", drag["start_y"])
        drag["index"] = self._drop_index(pointer - drag["offset"] + height / 2)
        self._place_drop_line(drag["index"])

    def _sync_auto_scroll(self):
        """指针贴住清单区上下边缘时自动滚。

        只在方向**变了**的时候重启定时器：指针在边缘区里抖一下不必重开
        一个。滚不动了由 ``scroll_by`` 的返回值报停（见 _auto_scroll_tick）。
        """
        drag = self._drag
        if not drag or not drag.get("moved"):
            self._stop_auto_scroll()
            return
        canvas = self._list_canvas
        top = canvas.winfo_rooty()
        bottom = top + canvas.winfo_height()
        pointer = drag.get("pointer_y", 0)
        edge = scaled_px(self, DRAG_EDGE)
        if pointer < top + edge:
            direction = -1
        elif pointer > bottom - edge:
            direction = 1
        else:
            direction = 0
        if direction == self._auto_scroll_dir and self._auto_scroll_job is not None:
            return
        self._auto_scroll_dir = direction
        self._stop_auto_scroll_job()
        if direction:
            self._auto_scroll_job = self.after(DRAG_SCROLL_MS,
                                               self._auto_scroll_tick)

    def _auto_scroll_tick(self):
        """自动滚的一拍：滚一点、把落点重算一次、再排下一拍。"""
        self._auto_scroll_job = None
        drag = self._drag
        if not drag or not drag.get("moved") or not self._auto_scroll_dir:
            return
        step = scaled_px(self, DRAG_SCROLL_STEP) * self._auto_scroll_dir
        if not self._list_area.scroll_by(step):
            self._auto_scroll_dir = 0      # 已经滚到头，先停手
            return
        self._refresh_drop_target()
        self._auto_scroll_job = self.after(DRAG_SCROLL_MS,
                                           self._auto_scroll_tick)

    def _stop_auto_scroll(self):
        """停掉自动滚（幂等）：方向归零 + 取消定时器。"""
        self._auto_scroll_dir = 0
        self._stop_auto_scroll_job()

    def _stop_auto_scroll_job(self):
        job = getattr(self, "_auto_scroll_job", None)
        self._auto_scroll_job = None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _list_drag_release(self, list_id, event):
        drag = self._drag
        self._drag = None
        self._stop_auto_scroll()
        if not drag:
            return
        if not drag["moved"]:
            # 原地松手 = 单击：选清单
            self._select_side("list", int(list_id))
            return
        order = list(self._list_rows)
        index = drag["index"]
        if index is None:
            index = len(order)
        new_order = compute_drop_order(order, int(list_id), index)
        self._hide_drop_line()
        if new_order != order:
            self.db.reorder_lists(new_order)
        self.refresh_all()

    def _drop_index(self, center_y) -> int:
        """被拖行的中心线落在第几号间隙（0..清单数）。

        传进来的是**被拖行中心**的屏幕 y，不是鼠标点。统一换算到
        _list_holder 的局部坐标再比 —— 行是 pack 出来的，用行自己的
        winfo_y()/winfo_height() 算中线，不写死行高。

        换算直接减 ``_list_holder`` 的屏幕 y：行的 winfo_y() 本来就是相对
        holder 的局部坐标，而「清单区」是可滚动的内嵌帧 —— 滚动时 holder
        的屏幕位置自己会跟着挪，两边天然对齐。

        **不要走 canvas.canvasy()**：它只返回**整数**像素，
        center_y - canvas_rooty 算出 55.5 这种带小数的值会被进成 56，正好
        越过「贴在第 2 行中线上」的判定，插入线整体偏一行（实测踩过）。
        """
        order = list(self._list_rows)
        local_y = center_y - self._list_holder.winfo_rooty()
        for index, list_id in enumerate(order):
            row = self._list_rows[list_id]["row"]
            # 用 <=：中心线正好压在某行中线上时插到该行**之前** ——
            # 拖回自己原来的位置时结果就是「顺序不变」，不会抖一下
            if local_y <= row.winfo_y() + row.winfo_height() / 2:
                return index
        return len(order)

    def _begin_drag_visual(self, list_id):
        """被拖的那行压暗一档，表示「拿起来了」。"""
        widgets = self._list_rows.get(int(list_id))
        if not widgets:
            return
        # accent 是行左边那 2px 竖条，也要一起压暗，否则会留一道浅缝
        for name in ("row", "accent", "icon_holder", "icon", "text", "count"):
            widgets[name].configure(bg=self.palette.sidebar_hover)
        widgets["text"].configure(fg=self.palette.text_muted)
        widgets["count"].configure(fg=self.palette.text_muted)
        try:
            self._list_holder.configure(cursor="fleur")
        except tk.TclError:
            pass

    def _place_drop_line(self, index):
        """在目标间隙画一条强调色横线。

        用 place 定位而不是往 pack 序列里插控件 —— 插进去会把下面所有行
        推下去，行的 y 跟着变，插入位置就会自己抖起来。
        """
        order = list(self._list_rows)
        if not order:
            return
        if index <= 0:
            y = 0
        elif index >= len(order):
            y = self._list_holder.winfo_height() - DROP_LINE_H
        else:
            y = self._list_rows[order[index]]["row"].winfo_y() - 1
        line = self._drop_line
        if line is None:
            line = tk.Frame(self._list_holder, bg=self.palette.accent,
                            height=DROP_LINE_H)
            self._drop_line = line
        width = max(40, self._list_holder.winfo_width() - DROP_LINE_PAD * 2)
        line.place(x=DROP_LINE_PAD, y=max(0, y), width=width, height=DROP_LINE_H)
        line.lift()

    def _hide_drop_line(self):
        """收掉插入线并恢复鼠标形状（幂等）。"""
        self._stop_auto_scroll()
        line = self._drop_line
        self._drop_line = None
        try:
            self._list_holder.configure(cursor="")
        except tk.TclError:
            pass
        if line is not None:
            try:
                line.destroy()
            except tk.TclError:
                pass

    def _list_context_menu(self, list_id):
        self._show_menu([
            ("编辑列表…", lambda: self.new_list_dialog(int(list_id))),
            "---",
            ("删除列表", lambda: self.delete_list(int(list_id))),
        ])

    # ------------------------------------------------------------------
    # 中栏
    # ------------------------------------------------------------------
    def _build_middle(self):
        palette = self.palette

        header = tk.Frame(self.middle, bg=palette.surface)
        header.pack(side="top", fill="x", padx=16, pady=(14, 6))
        self.mid_title = tk.Label(header, text="今天", bg=palette.surface,
                                  fg=palette.text_primary, font=FONT_PANE_TITLE,
                                  anchor="w")
        self.mid_title.pack(side="left")
        self.mid_count = tk.Label(header, text="", bg=palette.surface,
                                  fg=palette.text_muted,
                                  font=self.typography.caption)
        self.mid_count.pack(side="left", padx=(8, 0), pady=(8, 0))

        more = tk.Label(header, text="⋯", bg=palette.surface,
                        fg=palette.text_secondary, font=("Microsoft YaHei UI", 14),
                        cursor="hand2", padx=6)
        more.pack(side="right")
        more.bind("<Button-1>", lambda _e: self._view_menu())

        helper = tk.Label(self.middle, text="", bg=palette.surface,
                          fg=palette.text_muted, font=self.typography.caption,
                          anchor="w", justify="left")
        helper.pack(side="top", fill="x", padx=16)
        self.mid_helper = helper

        # 底部快速新建（先 pack，占住底边）
        add_bar = tk.Frame(self.middle, bg=palette.surface)
        add_bar.pack(side="bottom", fill="x", padx=16, pady=(4, 12))
        tk.Frame(add_bar, bg=palette.border, height=1).pack(fill="x", pady=(0, 8))
        inner = tk.Frame(add_bar, bg=palette.surface)
        inner.pack(fill="x")
        tk.Label(inner, image=todo_icons.glyph_image(
            self._icon_px, "plus", FALLBACK_COLOR), bg=palette.surface).pack(side="left")
        self.quick_var = tk.StringVar()
        quick = tk.Entry(inner, textvariable=self.quick_var, bd=0,
                         bg=palette.surface, fg=palette.text_primary,
                         font=self.typography.body,
                         insertbackground=palette.text_primary)
        quick.pack(side="left", fill="x", expand=True, padx=(8, 0))
        quick.bind("<Return>", lambda _e: self.quick_add())
        self.quick_entry = quick
        self._quick_placeholder = self._set_placeholder(
            quick, "新提醒事项")

        self.list_area = ScrollArea(self.middle, bg=palette.surface)
        self.list_area.pack(side="top", fill="both", expand=True)

    def _view_menu(self):
        mark = "✓ " if self.show_completed else ""
        actions = [(f"{mark}显示已完成", self.toggle_show_completed),
                   "---",
                   ("按日期排序", lambda: self._noop("已按日期排序")),
                   ("按优先级排序", lambda: self._noop("已按优先级排序")),
                   "---"]
        if self.current_list_id is not None:
            actions.append(("编辑当前列表…",
                            lambda: self.new_list_dialog(self.current_list_id)))
            actions.append(("删除当前列表",
                            lambda: self.delete_list(self.current_list_id)))
        actions.append(("补充节假日日历…", self.manage_holidays_dialog))
        self._show_menu(actions)

    def _noop(self, text):
        self.mid_helper.configure(text=text)

    # ------------------------------------------------------------------
    # 右栏
    # ------------------------------------------------------------------
    def _build_detail(self):
        palette = self.palette
        self._empty_state = tk.Frame(self.detail, bg=palette.surface)
        tk.Label(self._empty_state, text="选择一条待办查看详情",
                 bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.body).pack(expand=True)
        self._empty_state.pack(fill="both", expand=True)

    def _ensure_detail_area(self) -> ScrollArea:
        if self._detail_area is None:
            self._detail_area = ScrollArea(self.detail, bg=self.palette.surface)
        return self._detail_area

    # ==================================================================
    # 数据 → 界面
    # ==================================================================
    def refresh_all(self):
        """重画侧栏计数 + 中栏列表 + 右栏详情。"""
        self._refresh_sidebar()
        self._render_item_list()
        self._render_detail()

    def _refresh_sidebar(self):
        counts = self.db.count_by_scope()
        overdue = int(counts.get("overdue") or 0)
        for key, _label in SMART_LISTS:
            widgets = self._smart_rows.get(key)
            if widgets:
                # 「今天」那一格的计数本来就含着逾期项，所以它标红的意思
                # 正是「今天要做的活里已经有过了期的」
                self._set_badge(widgets, counts.get(key, 0),
                                urgent=(key == "today" and overdue > 0))
        list_counts = self.db.open_count_by_list()
        overdue_lists = self.db.overdue_count_by_list()

        # 下面会把 _list_holder 的子控件全部销毁（包括拖动的插入线），
        # 引用要跟着清掉，否则会拿着一个已销毁的控件；自动滚的定时器
        # 同理 —— 不停掉，下一拍就会去摸已经没了的行
        self._drag = None
        self._drop_line = None
        self._stop_auto_scroll()

        for child in self._list_holder.winfo_children():
            child.destroy()
        self._list_rows = {}
        for todo_list in self.db.fetch_lists():
            self._make_side_row(self._list_holder, kind="list",
                                key=todo_list.id, label=todo_list.name)
            widgets = self._list_rows.get(todo_list.id)
            if widgets:
                self._set_badge(widgets, list_counts.get(todo_list.id, 0),
                                urgent=bool(overdue_lists.get(todo_list.id)))

        for key, _label in SMART_LISTS:
            self._paint_side_row("smart", key)
        for todo_list in self.db.fetch_lists():
            self._paint_side_row("list", todo_list.id)
        # 行数变了，滚动条该出现还是该收掉要重新判一次。判之前先把几何
        # 结算掉 —— 刚 pack 完 winfo_reqheight() 还是上一轮的旧值，直接判
        # 会让该收的滚动条留着（清单删到装得下时尤其明显）
        self._list_area.inner.update_idletasks()
        self._list_area._sync_scrollbar()

    def _set_badge(self, widgets, value: int, *, urgent: bool = False):
        """侧栏行右侧的计数角标（iCloud 那种圆角胶囊）。

        数字为 0 时整枚收掉 —— 挂一排「0」既没用又吵。有逾期时换强调色：
        角标是灰还是红，本身就是一条信息。

        圆角底交给 Pillow 画（tk.Canvas 画圆角会起毛边），数字仍写在 Label
        的 ``text`` 里、用 ``compound="center"`` 压上去 —— 于是
        ``cget("text")`` 读到的还是那个数，脚本与无障碍都拿得到。
        """
        label = widgets.get("count")
        if label is None:
            return
        text = str(int(value or 0)) if value else ""
        widgets["badge_urgent"] = bool(text) and bool(urgent)
        if not text:
            label.configure(image="", text="")
            return
        fill = (self.palette.danger if widgets["badge_urgent"]
                else self.palette.badge_bg)
        width = max(self._badge_h,
                    self._badge_font.measure(text) + self._badge_pad * 2)
        label.configure(image=todo_icons.badge_image(width, self._badge_h, fill),
                        text=text, compound="center")

    # -- 中栏列表 ---------------------------------------------------------
    def _current_list(self) -> Optional[TodoList]:
        if self.current_list_id is None:
            return None
        return self.db.get_list(self.current_list_id)

    def _default_list_id(self) -> int:
        if self.current_list_id:
            return self.current_list_id
        lists = self.db.fetch_lists()
        return lists[0].id if lists else 0

    def _fetch_current_items(self) -> list[TodoItem]:
        scope = self.current_scope
        # 开着「显示已完成」就把已完成项一并取回来；「已完成」视图由数据层
        # 自己认这个 scope，这个参数传什么都不影响它
        if self.current_list_id is not None:
            return self.db.fetch_items(scope="list", list_id=self.current_list_id,
                                       keyword=self.keyword,
                                       include_completed=self.show_completed)
        return self.db.fetch_items(scope=scope, keyword=self.keyword,
                                   include_completed=self.show_completed)

    def _render_item_list(self):
        palette = self.palette
        area = self.list_area
        area.clear()
        self._row_widgets.clear()

        todo_list = self._current_list()
        if todo_list is not None:
            title, color = todo_list.name, todo_list.color
        else:
            title = dict(SMART_LISTS).get(self.current_scope, "待办")
            color = palette.text_primary

        self.mid_title.configure(text=title, fg=color)
        self.mid_helper.configure(text="")

        items = self._fetch_current_items()
        self._subtask_summary_cache(items)
        open_items = [it for it in items if not it.completed]
        done_items = [it for it in items if it.completed]
        # 标题旁的数字跟左栏保持一致（都数未完成的）—— 「今天 4」和左栏的
        # 「今天 4」对不上会让人怀疑哪边算错了。已完成那一档有自己的数字
        # （见下面的小标题），不用并到标题上。「已完成」视图里全是已完成项，
        # 那里就照旧数全部。
        counter = len(items) if self.current_scope == "completed" else len(open_items)
        self.mid_count.configure(text=f"{counter}" if counter else "")
        list_map = {l.id: l for l in self.db.fetch_lists()}

        if not items:
            self._render_empty_list(area, title)
            return

        # 智能分组视图按清单分组显示（苹果的「今天」页就是这样）
        grouped = self.current_list_id is None and self.current_scope != "completed"
        if grouped:
            for list_id, bucket in self._bucket_by_list(open_items, list_map):
                info = list_map.get(list_id)
                self._make_group_header(area.inner, info, len(bucket))
                for item in bucket:
                    self._make_item_row(area.inner, item, info)
        else:
            for item in open_items:
                self._make_item_row(area.inner, item, todo_list)

        # 已完成的单独收在末尾（苹果也是这么分段的）：划掉的条目夹在没做的
        # 中间只会碍事。在「已完成」视图里这一整段就是全部内容，不必再挂标题。
        if done_items:
            if self.current_scope != "completed":
                self._make_done_header(area.inner, len(done_items))
            # 这个视图横跨几个清单时（没选中某个清单），已完成那一段**也**按
            # 清单分段：混在一起的一长串「做过什么」看不出是哪张清单清完了，
            # 也找不到「这周的工作我都做完了没有」
            if self.current_list_id is None:
                for list_id, bucket in self._bucket_by_list(done_items, list_map):
                    self._make_done_group_header(area.inner,
                                                 list_map.get(list_id),
                                                 len(bucket))
                    for item in bucket:
                        self._make_item_row(area.inner, item,
                                            list_map.get(item.list_id))
            else:
                for item in done_items:
                    self._make_item_row(area.inner, item, todo_list)

        area._on_inner_configure()

    @staticmethod
    def _bucket_by_list(items, list_map):
        """按清单分桶，返回 ``[(list_id, [条目, ...]), ...]``。

        桶的顺序跟着 ``list_map``（就是 ``fetch_lists()`` 的顺序，与左栏
        一致）—— 用「谁先出现谁在前」的话，中栏的分组顺序会随筛选结果
        变来变去，眼睛每次都得重新找一遍。查不到清单的条目兜在最后。
        """
        buckets: dict[int, list[TodoItem]] = {}
        for item in items:
            buckets.setdefault(item.list_id, []).append(item)
        ordered = [(list_id, buckets[list_id])
                   for list_id in list_map if list_id in buckets]
        ordered += [(list_id, bucket) for list_id, bucket in buckets.items()
                    if list_id not in list_map]
        return ordered

    def _render_empty_list(self, area: ScrollArea, title: str):
        palette = self.palette
        box = tk.Frame(area.inner, bg=palette.surface)
        box.pack(fill="x", pady=48)
        tk.Label(box, text=f"「{title}」里还没有待办", bg=palette.surface,
                 fg=palette.text_muted,
                 font=self.typography.body).pack()
        tk.Label(box, text="在下方输入框里写一条，回车即可", bg=palette.surface,
                 fg=palette.text_muted,
                 font=self.typography.caption).pack(pady=(6, 0))

    def _make_done_header(self, parent, count: int):
        """「已完成」小节的标题：灰勾 + 文字 + 条数。

        放在未完成项之后单独一段（苹果也是这么分的）。图标复用清单图标里
        的 check，颜色取中性灰 —— 这一段不该比上头的待办还抢眼。
        """
        palette = self.palette
        head = tk.Frame(parent, bg=palette.surface)
        head.pack(fill="x", padx=16, pady=(18, 2))
        tk.Label(head, image=todo_icons.tile_image(
            self._tile_px, FALLBACK_COLOR, "check"),
            bg=palette.surface).pack(side="left")
        tk.Label(head, text="已完成", bg=palette.surface,
                 fg=palette.text_secondary, font=self.typography.caption,
                 anchor="w").pack(side="left", padx=(6, 0))
        tk.Label(head, text=str(count), bg=palette.surface,
                 fg=palette.text_muted,
                 font=self.typography.caption).pack(side="right")

    def _make_done_group_header(self, parent, info: Optional[TodoList],
                               count: int):
        """「已完成」那一段里的二级分组头（按清单）。

        比未完成区的分组头更轻：不重复画清单图标，只用一枚该清单颜色的
        小圆点 + 名字 + 条数，再缩进一格 —— 让人一眼看出它是「已完成」
        这段里的下一级，而不是又一个并列的清单。
        """
        palette = self.palette
        head = tk.Frame(parent, bg=palette.surface)
        head.pack(fill="x", padx=16, pady=(10, 2))
        inner = tk.Frame(head, bg=palette.surface)
        inner.pack(fill="x", padx=(22, 0))
        dot = tk.Canvas(inner, width=8, height=8, bg=palette.surface,
                        highlightthickness=0, bd=0)
        dot.pack(side="left")
        dot.create_oval(1, 3, 6, 8, fill=(info.color if info else FALLBACK_COLOR),
                        outline="")
        tk.Label(inner, text=(info.name if info else "未分组"), bg=palette.surface,
                 fg=palette.text_muted, font=self.typography.caption,
                 anchor="w").pack(side="left", padx=(6, 0))
        tk.Label(inner, text=str(count), bg=palette.surface,
                 fg=palette.text_muted,
                 font=self.typography.caption).pack(side="right")

    def _make_group_header(self, parent, info: Optional[TodoList], count: int):
        palette = self.palette
        head = tk.Frame(parent, bg=palette.surface)
        head.pack(fill="x", padx=16, pady=(14, 2))
        color = info.color if info else FALLBACK_COLOR
        icon = info.icon if info else "list"
        tk.Label(head, image=todo_icons.tile_image(self._tile_px, color, icon),
                 bg=palette.surface).pack(side="left")
        tk.Label(head, text=(info.name if info else "未分组"), bg=palette.surface,
                 fg=palette.text_secondary, font=self.typography.caption,
                 anchor="w").pack(side="left", padx=(6, 0))
        tk.Label(head, text=str(count), bg=palette.surface,
                 fg=palette.text_muted, font=self.typography.caption).pack(side="right")

    def _make_item_row(self, parent, item: TodoItem, info: Optional[TodoList]):
        palette = self.palette

        row = tk.Frame(parent, bg=palette.surface, cursor="hand2")
        row.pack(fill="x")

        # 勾选框
        check_holder = tk.Frame(row, bg=palette.surface)
        check_holder.pack(side="left", padx=(16, 8), pady=ROW_PAD_Y, anchor="n")
        check = tk.Label(check_holder, bg=palette.surface, bd=0,
                         highlightthickness=0, cursor="hand2")
        check.pack()

        # 文本列
        text_col = tk.Frame(row, bg=palette.surface)
        text_col.pack(side="left", fill="x", expand=True, pady=ROW_PAD_Y)

        title = tk.Label(text_col, text=item.title or "新提醒事项",
                         bg=palette.surface, fg=palette.text_primary,
                         font=FONT_ROW_TITLE, anchor="w", justify="left")
        title.pack(fill="x", anchor="w")
        if item.completed:
            # 「已完成」的样子＝左侧勾上 + 标题中间划一道横线（与苹果一致）。
            # 只变灰太容易被看漏，尤其一屏里混着未完项的时候。
            title.configure(fg=palette.text_muted,
                            font=strike_font(FONT_ROW_TITLE, title))

        sub_parts = []
        if info is not None and (self.current_list_id is None
                                 and self.current_scope != "completed"):
            sub_parts.append(info.name)
        summary = self._subtask_summary_for(item.id)
        if summary:
            sub_parts.append(f"{summary[0]}/{summary[1]} 个子任务")
        elif item.notes:
            sub_parts.append(item.notes.splitlines()[0][:24])
        if item.rollover_count:
            sub_parts.append(f"已顺延 {item.rollover_count} 次")
        sub = None
        if sub_parts:
            sub = tk.Label(text_col, text=" · ".join(sub_parts), bg=palette.surface,
                           fg=palette.text_muted, font=FONT_ROW_META,
                           anchor="w", justify="left")
            sub.pack(fill="x", anchor="w", pady=(2, 0))

        # 右侧：日期 + 重复 / 优先级
        right = tk.Frame(row, bg=palette.surface)
        right.pack(side="right", padx=(8, 14), pady=ROW_PAD_Y, anchor="n")

        marks = []
        if item.priority:
            marks.append(item.priority_mark)
        if item.repeat_rule != "none":
            marks.append("↻")
        if marks:
            tk.Label(right, text=" ".join(marks), bg=palette.surface,
                     fg=palette.text_secondary, font=FONT_SMALL_BOLD).pack(anchor="e")

        due_text, due_color = self._due_text(item)
        if due_text:
            tk.Label(right, text=due_text, bg=palette.surface, fg=due_color,
                     font=FONT_ROW_META).pack(anchor="e", pady=(2, 0))

        # 交互
        for widget in (row, check_holder, check, text_col, title, right):
            widget.bind("<Enter>", lambda _e, r=row, i=item: self._hover_row(r, i, True))
            widget.bind("<Leave>", lambda _e, r=row, i=item: self._hover_row(r, i, False))
        check.bind("<Button-1>", lambda _e, i=item.id: self._on_check_click(i))
        check_holder.bind("<Button-1>", lambda _e, i=item.id: self._on_check_click(i))
        for widget in (row, text_col, title):
            widget.bind("<Button-1>", lambda _e, i=item.id: self.select_item(i))
        row.bind("<Button-3>", lambda _e, i=item: self._item_context_menu(i))
        if sub is not None:
            sub.bind("<Button-1>", lambda _e, i=item.id: self.select_item(i))

        self._row_widgets[item.id] = row
        self._paint_item_row(item, row, check)

    def _subtask_summary_for(self, item_id: int):
        cache = getattr(self, "_subtask_cache", None) or {}
        return cache.get(item_id)

    def _due_text(self, item: TodoItem):
        """日期文案与颜色：逾期红、今天近黑、未来灰。"""
        palette = self.palette
        due = parse_day(item.due_date)
        if due is None:
            return "", palette.text_muted
        if item.completed:
            # 已完成的不再喊「逾期」—— 事都做完了，红色只会干扰
            text = due.strftime("%m月%d日")
            if item.due_time:
                text += f" {item.due_time}"
            return text, palette.text_muted
        today = date.today()
        delta = (due - today).days
        if delta < 0:
            text = due.strftime("%m月%d日")
            return f"逾期 {text}", palette.danger
        if delta == 0:
            text = "今天"
        elif delta == 1:
            text = "明天"
        elif delta == 2:
            text = "后天"
        elif 0 < delta <= 6:
            text = WEEKDAY_CN[due.weekday()]
        else:
            text = due.strftime("%m月%d日")
        if item.due_time:
            text += f" {item.due_time}"
        color = palette.text_secondary if delta <= 6 else palette.text_muted
        return text, color

    def _paint_item_row(self, item: TodoItem, row: tk.Frame, check: tk.Label):
        palette = self.palette
        info = self.db.get_list(item.list_id) if self.current_list_id is None else self._current_list()
        color = info.color if info else FALLBACK_COLOR
        selected = self.selected_item_id == item.id
        bg = palette.sidebar_active if selected else palette.surface
        tint(row, bg)
        check.configure(image=todo_icons.checkbox_image(
            self._check_px, color,
            bool(item.completed)))

    def _hover_row(self, row: tk.Frame, item: TodoItem, entering: bool):
        if self.selected_item_id == item.id:
            return
        tint(row, self.palette.surface_alt if entering else self.palette.surface)

    def _item_context_menu(self, item: TodoItem):
        self._show_menu([
            ("旗标" if not item.flagged else "取消旗标",
             lambda: self.toggle_flag(item.id)),
            ("优先级：无", lambda: self._set_priority(item.id, 0)),
            ("优先级：叹号 !", lambda: self._set_priority(item.id, 1)),
            ("优先级：!!", lambda: self._set_priority(item.id, 2)),
            ("优先级：!!!", lambda: self._set_priority(item.id, 3)),
            "---",
            ("删除", lambda: self.delete_item(item.id)),
        ])

    # -- 右栏详情 ---------------------------------------------------------
    def _render_detail(self):
        palette = self.palette
        item = self.db.get_item(self.selected_item_id) if self.selected_item_id else None

        if item is None:
            if self._detail_area is not None:
                self._detail_area.pack_forget()
            self._empty_state.pack(fill="both", expand=True)
            return

        self._empty_state.pack_forget()
        area = self._ensure_detail_area()
        area.pack(fill="both", expand=True)
        area.clear()
        area.scroll_top()

        inner = area.inner
        pad = tk.Frame(inner, bg=palette.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=(16, 24))

        self._loading = True
        try:
            self._build_detail_header(pad, item)
            self._build_detail_body(pad, item)
        finally:
            self._loading = False
        area._on_inner_configure()

    def _build_detail_header(self, parent, item: TodoItem):
        palette = self.palette
        info = self.db.get_list(item.list_id)
        color = info.color if info else FALLBACK_COLOR

        head = tk.Frame(parent, bg=palette.surface)
        head.pack(fill="x")

        check = tk.Label(head, bg=palette.surface, cursor="hand2", bd=0,
                         highlightthickness=0,
                         image=todo_icons.checkbox_image(
                             scaled_px(self, 20), color, bool(item.completed)))
        check.pack(side="left", pady=(4, 0))
        check.bind("<Button-1>", lambda _e, i=item.id: self.toggle_complete(i))

        self.title_var = tk.StringVar(value=item.title)
        title = tk.Entry(head, textvariable=self.title_var, bd=0,
                         bg=palette.surface, fg=palette.text_primary,
                         font=FONT_DETAIL_TITLE, insertbackground=palette.text_primary)
        if item.completed:
            # 列表上划了、点进来又是正常字，会让人怀疑自己刚才勾没勾上
            title.configure(fg=palette.text_muted,
                            font=strike_font(FONT_DETAIL_TITLE, title))
        title.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0))
        title.bind("<FocusOut>", lambda _e: self._flush_editor())
        title.bind("<Return>", lambda _e: self._flush_editor())
        self.detail_title_entry = title

    def _build_detail_body(self, parent, item: TodoItem):
        palette = self.palette

        # —— 备注（多行，就是「点开有一个小型备忘录」）——
        tk.Label(parent, text="备注", bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.caption, anchor="w").pack(
            fill="x", pady=(14, 4))
        notes_wrap = tk.Frame(parent, bg=palette.surface_alt)
        notes_wrap.pack(fill="x")
        self.notes_text = tk.Text(notes_wrap, height=5, bd=0, wrap="word",
                                  bg=palette.surface_alt,
                                  fg=palette.text_primary,
                                  font=self.typography.body,
                                  insertbackground=palette.text_primary,
                                  padx=10, pady=8)
        self.notes_text.pack(fill="x")
        self.notes_text.insert("1.0", item.notes)
        self.notes_text.bind("<FocusOut>", lambda _e: self._flush_editor())
        self._notes_placeholder = None
        if not item.notes:
            self._apply_notes_placeholder()

        # —— 属性区 ——
        tk.Frame(parent, bg=palette.border, height=1).pack(fill="x", pady=(16, 6))

        meta = tk.Frame(parent, bg=palette.surface)
        meta.pack(fill="x")

        due = parse_day(item.due_date)
        due_label = self._format_due_long(due)
        self._make_meta_row(meta, "calendar", "日期", due_label or "无",
                            self._date_menu, value_color=(
                                palette.danger if due and due < date.today() else None))
        self._make_meta_row(meta, "clock", "时间", item.due_time or "无",
                            self._time_menu)
        # 提前量紧跟时间：两件事是一回事（没有时间，提前量无从谈起，
        # 所以那种情况明说一句，而不是让人选完发现没反应）
        advance_value = advance_label(item.advance_minutes)
        if item.advance_minutes and not item.due_time:
            advance_value += "（尚未设时间）"
        self._make_meta_row(meta, "bell", "提前", advance_value,
                            self._advance_menu)
        self._make_meta_row(meta, "repeat", "重复", item.repeat_label
                            + (f"（{item.repeat_interval}{self._unit_label(item.repeat_unit)}）"
                               if item.repeat_rule == "custom" else ""),
                            self._repeat_menu)
        self._make_meta_row(meta, "priority", "优先级",
                            (PRIORITY_LABELS.get(item.priority, "无")
                             + (f"  {item.priority_mark}" if item.priority else "")),
                            self._priority_menu)
        self._make_meta_row(meta, "flag", "旗标",
                            "已标记" if item.flagged else "无",
                            lambda _e, i=item: self.toggle_flag(i.id))
        info = self.db.get_list(item.list_id)
        self._make_meta_row(meta, "list", "列表",
                            info.name if info else "未分组", self._list_menu,
                            value_color=info.color if info else None)
        self._make_meta_row(meta, "tag", "标签",
                            " ".join(item.tags) if item.tags else "无",
                            self._tags_dialog)
        self._make_meta_row(meta, "sun", "跳过节假日",
                            "开启" if item.skip_holidays else "关闭",
                            lambda _e, i=item: self.toggle_skip_holidays(i.id))

        # —— 子任务 ——
        tk.Frame(parent, bg=palette.border, height=1).pack(fill="x", pady=(12, 6))
        sub_head = tk.Frame(parent, bg=palette.surface)
        sub_head.pack(fill="x")
        tk.Label(sub_head, image=todo_icons.glyph_image(
            self._icon_px, "subtask", palette.text_secondary),
            bg=palette.surface).pack(side="left")
        self._subtask_counter = tk.Label(sub_head, text="", bg=palette.surface,
                                         fg=palette.text_secondary,
                                         font=self.typography.caption)
        self._subtask_counter.pack(side="left", padx=(6, 0))
        self._subtask_holder = tk.Frame(parent, bg=palette.surface)
        self._subtask_holder.pack(fill="x", pady=(4, 0))
        self._render_subtasks(item)

        sub_add = tk.Frame(parent, bg=palette.surface)
        sub_add.pack(fill="x", pady=(6, 0))
        tk.Label(sub_add, image=todo_icons.glyph_image(
            self._icon_px, "plus", palette.text_muted),
            bg=palette.surface).pack(side="left")
        self.sub_var = tk.StringVar()
        sub_entry = tk.Entry(sub_add, textvariable=self.sub_var, bd=0,
                             bg=palette.surface, fg=palette.text_primary,
                             font=self.typography.body,
                             insertbackground=palette.text_primary)
        sub_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        sub_entry.bind("<Return>", lambda _e, i=item.id: self.add_subtask(i))
        self.sub_entry = sub_entry

        # —— 底部信息与删除 ——
        tk.Frame(parent, bg=palette.border, height=1).pack(fill="x", pady=(16, 8))
        footer = tk.Frame(parent, bg=palette.surface)
        footer.pack(fill="x")
        extra = []
        if item.rollover_count:
            extra.append(f"已顺延 {item.rollover_count} 次")
        if item.original_due_date:
            extra.append(f"原定 {item.original_due_date}")
        if item.completed_at:
            extra.append(f"完成于 {item.completed_at[:16].replace('T', ' ')}")
        tk.Label(footer, text="　".join(extra) or "　", bg=palette.surface,
                 fg=palette.text_muted, font=self.typography.caption,
                 anchor="w").pack(side="left")
        delete = tk.Label(footer, text="删除", bg=palette.surface,
                          fg=palette.danger, font=self.typography.caption,
                          cursor="hand2", padx=8)
        delete.pack(side="right")
        delete.bind("<Button-1>", lambda _e, i=item.id: self.delete_item(i))

    def _apply_notes_placeholder(self):
        """空备注时给一段灰色提示字（Tk 的 Text 没有原生 placeholder）。"""
        placeholder = "添加备注…"
        self.notes_text.insert("1.0", placeholder)
        self.notes_text.configure(fg=self.palette.text_muted)
        self._notes_placeholder = placeholder

        def clear(_event=None):
            if self._notes_placeholder and \
                    self.notes_text.get("1.0", "end-1c") == self._notes_placeholder:
                self.notes_text.delete("1.0", "end")
            self.notes_text.configure(fg=self.palette.text_primary)
            self.notes_text.unbind("<FocusIn>")

        def restore(_event=None):
            if not self.notes_text.get("1.0", "end-1c").strip():
                self.notes_text.insert("1.0", placeholder)
                self.notes_text.configure(fg=self.palette.text_muted)
                self._notes_placeholder = placeholder

        self.notes_text.bind("<FocusIn>", clear)
        self.notes_text.bind("<FocusOut>", restore, add="+")

    def _notes_value(self) -> str:
        if self._notes_placeholder is None:
            return self.notes_text.get("1.0", "end-1c")
        text = self.notes_text.get("1.0", "end-1c")
        return "" if text == self._notes_placeholder else text

    def _make_meta_row(self, parent, glyph: str, label: str, value: str,
                       command, *, value_color: Optional[str] = None):
        palette = self.palette
        row = tk.Frame(parent, bg=palette.surface, cursor="hand2")
        row.pack(fill="x")
        tk.Label(row, image=todo_icons.glyph_image(
            self._icon_px, glyph, palette.text_secondary),
            bg=palette.surface).pack(side="left", pady=6)
        tk.Label(row, text=label, bg=palette.surface, fg=palette.text_primary,
                 font=self.typography.body, anchor="w", width=9).pack(
            side="left", padx=(10, 0), pady=6)
        value_label = tk.Label(row, text=value, bg=palette.surface,
                               fg=value_color or palette.text_secondary,
                               font=self.typography.body, anchor="w")
        value_label.pack(side="left", fill="x", expand=True, pady=6)
        tk.Label(row, image=todo_icons.glyph_image(
            self._icon_px, "chevron_right", palette.text_muted),
            bg=palette.surface).pack(side="right", pady=6)

        def enter(_event=None):
            tint(row, palette.surface_alt)

        def leave(_event=None):
            tint(row, palette.surface)

        for widget in row.winfo_children():
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.bind("<Button-1>", command)
        row.bind("<Enter>", enter)
        row.bind("<Leave>", leave)
        row.bind("<Button-1>", command)
        return row

    def _render_subtasks(self, item: TodoItem):
        palette = self.palette
        for child in self._subtask_holder.winfo_children():
            child.destroy()
        subs = self.db.fetch_subtasks(item.id)
        done = sum(1 for s in subs if s.completed)
        self._subtask_counter.configure(
            text=f"子任务  {done}/{len(subs)}" if subs else "子任务")
        for sub in subs:
            row = tk.Frame(self._subtask_holder, bg=palette.surface)
            row.pack(fill="x")
            check = tk.Label(row, bg=palette.surface, cursor="hand2", bd=0,
                             highlightthickness=0,
                             image=todo_icons.checkbox_image(
                                 scaled_px(self, 15), FALLBACK_COLOR,
                                 bool(sub.completed)))
            check.pack(side="left", pady=4)
            text_label = tk.Label(row, text=sub.title, bg=palette.surface,
                                  fg=(palette.text_muted if sub.completed
                                      else palette.text_primary),
                                  font=(strike_font(self.typography.body, row)
                                        if sub.completed else self.typography.body),
                                  anchor="w")
            text_label.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=4)
            remove = tk.Label(row, text="✕", bg=palette.surface,
                              fg=palette.text_muted, font=self.typography.caption,
                              cursor="hand2", padx=6)
            remove.pack(side="right")
            check.bind("<Button-1>",
                       lambda _e, s=sub: self._toggle_subtask(item.id, s.id,
                                                              not s.completed))
            remove.bind("<Button-1>", lambda _e, s=sub: self._remove_subtask(item.id, s.id))

    # ==================================================================
    # 日期 / 时间的本地化显示
    # ==================================================================
    @staticmethod
    def _format_due_long(due: Optional[date]) -> str:
        if due is None:
            return ""
        today = date.today()
        delta = (due - today).days
        if delta == 0:
            return f"今天  周{WEEKDAY_CN[due.weekday()][1]}"
        if delta == 1:
            return f"明天  周{WEEKDAY_CN[due.weekday()][1]}"
        if delta == -1:
            return f"昨天  周{WEEKDAY_CN[due.weekday()][1]}"
        return f"{due.strftime('%Y年%m月%d日')}  {WEEKDAY_CN[due.weekday()]}"

    @staticmethod
    def _unit_label(unit: str) -> str:
        for key, label in REPEAT_UNITS:
            if key == unit:
                return label
        return unit

    # ==================================================================
    # 交互：勾选 / 选择 / 增删
    # ==================================================================
    def _subtask_summary_cache(self, items: list[TodoItem]):
        self._subtask_cache = self.db.subtask_summary([i.id for i in items])

    def toggle_show_completed(self):
        """切换「显示已完成」（苹果列表右上角的 Show Completed）。

        状态写进 todo_state 记着 —— 它是「我想怎么看列表」的偏好，
        不是一次性的视图动作。
        """
        self._flush_editor()
        self.show_completed = not self.show_completed
        self.db.set_state("show_completed", "1" if self.show_completed else "0")
        self.refresh_all()
        # 回执写在重画之后：_render_item_list() 会先把 helper 清空
        if not self.show_completed:
            self.mid_helper.configure(text="已隐藏已完成")
            return
        done_count = self.db.count_by_scope().get("completed", 0)
        if done_count:
            self.mid_helper.configure(
                text=f"已显示 {done_count} 条已完成（沉在列表末尾，点圆圈可恢复）")
        else:
            self.mid_helper.configure(text="已显示已完成 · 目前还没有已完成的待办")

    def _on_check_click(self, item_id: int):
        """点勾选框：未完成 → 完成；已完成 → 恢复。

        状态从库里现读，不用建行时捕获的 item —— 行控件在切选中态时会被
        重新着色而不重建，捕获下来的 completed 有可能是旧值。
        """
        fresh = self.db.get_item(item_id)
        if fresh is not None and fresh.completed:
            self.uncomplete(item_id)
        else:
            self.toggle_complete(item_id)

    def uncomplete(self, item_id: int):
        """取消勾选，恢复成未完成（苹果点一下已完成项的圆圈就是这个效果）。"""
        self._flush_editor()
        self.db.set_completed(item_id, False)
        self.refresh_all()
        self.mid_helper.configure(text="已恢复为未完成 · 它回到了原来的日期位置")

    def toggle_complete(self, item_id: int):
        self._flush_editor()
        result = self.db.set_completed(item_id, True)
        self.refresh_all()
        # 提示必须写在重画之后：_render_item_list() 会把 helper 清空，
        # 写在前面等于白写（原先的「重复项已完成」就是这么被吞掉的）。
        # 单次项勾完就从当前视图消失、只剩左栏计数 +1，这句是唯一的回执。
        if result.get("action") == "spawn" and result.get("next_due"):
            text = f"重复项已完成，下一次：{result['next_due']}"
            if self.show_completed:
                text += "（这一次的已收在下方「已完成」）"
            self.mid_helper.configure(text=text)
        elif result.get("action") == "done":
            # 开着「显示已完成」时它不会消失，就别说「去左侧找」
            if self.show_completed:
                self.mid_helper.configure(
                    text="已完成 · 已划掉，再点一次圆圈可以恢复")
            else:
                self.mid_helper.configure(text="已完成 · 可在左侧「已完成」里找到")

    def toggle_flag(self, item_id: int):
        self._flush_editor()
        self.db.toggle_flag(item_id)
        self.refresh_all()

    def toggle_skip_holidays(self, item_id: int):
        """切换「跳过节假日」。重新打开时立刻把落点挪到工作日。"""
        item = self.db.get_item(item_id)
        if item is None:
            return
        turning_on = not item.skip_holidays
        payload = {"skip_holidays": 1 if turning_on else 0}
        if turning_on and item.due_date:
            payload["due_date"] = self.db.shift_to_workday(item.due_date)
        self.db.update_item(item_id, payload)
        self.refresh_all()

    def _set_priority(self, item_id: int, level: int):
        self.db.update_item(item_id, {"priority": level})
        self.refresh_all()

    def select_item(self, item_id: int):
        if self.selected_item_id == item_id:
            return
        self._flush_editor()
        self.selected_item_id = item_id
        for iid, row in self._row_widgets.items():
            item = self.db.get_item(iid)
            if item:
                self._paint_item_row(item, row, self._find_check(row))
        self._render_detail()

    @staticmethod
    def _find_check(row: tk.Frame) -> tk.Label:
        try:
            holder = row.winfo_children()[0]
            return holder.winfo_children()[0]
        except Exception:
            return None

    def delete_item(self, item_id: int):
        if not messagebox.askyesno("删除待办", "确定删除这条待办吗？", parent=self):
            return
        self.db.delete_item(item_id)
        if self.selected_item_id == item_id:
            self.selected_item_id = None
        self.refresh_all()

    def quick_add(self):
        title = self.quick_var.get().strip()
        # 占位提示会被写进 textvariable，必须显式排除，
        # 否则点一下回车就会凭空多出一条名为「新提醒事项」的待办
        if not title or title == self._quick_placeholder:
            return
        payload = {"title": title, "list_id": self._default_list_id()}
        if self.current_list_id is None and self.current_scope in ("today", "scheduled"):
            payload["due_date"] = day_str(date.today())
        new_id = self.db.add_item(payload)
        self.quick_var.set("")
        self._restore_placeholder(self.quick_entry, self.quick_var,
                                  self._quick_placeholder)
        self.selected_item_id = new_id
        self.refresh_all()
        self._focus_quick()

    def _focus_quick(self):
        try:
            self.quick_entry.focus_set()
        except Exception:
            pass

    def add_subtask(self, item: TodoItem):
        title = self.sub_var.get().strip()
        if not title:
            return
        self.db.add_subtask(item.id, title)
        self.sub_var.set("")
        self._render_subtasks(item)
        self._refresh_current_rows()

    def _toggle_subtask(self, item_id: int, subtask_id: int, completed: bool):
        self.db.set_subtask_completed(subtask_id, completed)
        item = self.db.get_item(item_id)
        if item:
            self._render_subtasks(item)
        self._refresh_current_rows()

    def _remove_subtask(self, item_id: int, subtask_id: int):
        self.db.delete_subtask(subtask_id)
        item = self.db.get_item(item_id)
        if item:
            self._render_subtasks(item)
        self._refresh_current_rows()

    def _refresh_current_rows(self):
        """子任务变动后重画中栏（行上要显示 x/y 进度）。"""
        self._render_item_list()

    # ==================================================================
    # 编辑器写入
    # ==================================================================
    def _flush_editor(self):
        """把标题 / 备注写回数据库（失焦、切换条目、切换视图时调用）。"""
        if self._loading or not self.selected_item_id:
            return
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return
        title = self.title_var.get().strip() if hasattr(self, "title_var") else ""
        notes = self._notes_value() if hasattr(self, "notes_text") else ""
        payload = {}
        if title and title != item.title:
            payload["title"] = title
        if notes != item.notes:
            payload["notes"] = notes
        if payload:
            self.db.update_item(item.id, payload)
            row = self._row_widgets.get(item.id)
            if row:
                self._render_item_list()
        # 标题被清空时兜底，避免出现一条没有名字的待办
        if not title and not item.title:
            self.db.update_item(item.id, {"title": "新提醒事项"})

    # ==================================================================
    # 弹层：日期 / 时间 / 重复 / 优先级 / 列表 / 标签
    # ==================================================================
    def _show_menu(self, actions):
        """弹出扁平菜单。

        必须把菜单对象挂在 ``self`` 上留一个引用：tk_popup 只是把菜单交给
        Tk 显示、随即返回，Python 侧一旦没有引用，菜单对象会被 GC 回收并
        连带销毁，表现为「点了没反应」。
        """
        menu = create_flat_menu(self, actions)
        self._active_menu = menu
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()
        return menu

    def _popup(self, actions):
        self._show_menu(actions)

    def _set_due(self, item: TodoItem, day: Optional[date]):
        """写入日期的统一入口：按「跳过节假日」规则落到工作日。

        单次待办且开启跳过时，选到周末或法定节假日会自动挪到下一个工作日；
        重复项不在这里挪 —— 它每次推进时自己处理，两边都挪会跟周期日打架。
        """
        if day is None:
            self.db.update_item(item.id, {"due_date": ""})
            return
        value = day_str(day)
        if item.skip_holidays and item.repeat_rule == "none":
            value = self.db.shift_to_workday(value)
        self.db.update_item(item.id, {"due_date": value})

    def _date_menu(self, _event=None):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return
        today = date.today()
        weekend = today + timedelta(days=(5 - today.weekday()) % 7 or 7)

        self._popup([
            ("今天", lambda: self._set_due(item, today)),
            ("明天", lambda: self._set_due(item, today + timedelta(days=1))),
            ("本周末", lambda: self._set_due(item, weekend)),
            ("下个工作日", lambda: self._set_due(
                item, self.db.next_workday(today, include_self=False))),
            "---",
            ("自定…", lambda: self._pick_date_dialog(item.id)),
            ("清除日期", lambda: self._set_due(item, None)),
        ])

    def _pick_date_dialog(self, item_id: int):
        """自定日期：一个小月历，点日期即选。"""
        palette = self.palette
        item = self.db.get_item(item_id)
        if item is None:
            return
        current = parse_day(item.due_date) or date.today()

        dlg = tk.Toplevel(self)
        dlg.title("选择日期")
        dlg.configure(bg=palette.surface)
        dlg.transient(self.winfo_toplevel())
        dlg.resizable(False, False)
        self._center_on_parent(dlg, 300, 340)

        state = {"year": current.year, "month": current.month}

        header = tk.Frame(dlg, bg=palette.surface)
        header.pack(fill="x", padx=14, pady=(14, 6))
        title = tk.Label(header, bg=palette.surface, fg=palette.text_primary,
                         font=self.typography.subtitle, anchor="w")
        title.pack(side="left", fill="x", expand=True)
        # 月份切换放在标题行右侧（先 pack 下个月、再上个月，读起来就是「下 / 上」）
        for text, delta in (("下个月 ›", 1), ("‹ 上个月", -1)):
            btn = tk.Label(header, text=text, bg=palette.surface,
                           fg=palette.text_secondary,
                           font=self.typography.caption, cursor="hand2", padx=6)
            btn.pack(side="right")
            btn.bind("<Button-1>", lambda _e, d=delta: shift(d))

        grid_holder = tk.Frame(dlg, bg=palette.surface)
        grid_holder.pack(fill="x", padx=14)

        tk.Label(dlg, text="灰色日期为周末或节假日，选它会自动落到工作日",
                 bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.caption).pack(anchor="w", padx=14,
                                                    pady=(8, 12))

        def pick(day: date):
            self._set_due(item, day)
            dlg.destroy()
            self.refresh_all()

        def shift(delta: int):
            month = state["month"] + delta
            year = state["year"]
            if month < 1:
                month, year = 12, year - 1
            elif month > 12:
                month, year = 1, year + 1
            state.update({"year": year, "month": month})
            render()

        def render():
            title.configure(text=f"{state['year']} 年 {state['month']} 月")
            for child in grid_holder.winfo_children():
                child.destroy()
            for idx, name in enumerate(("一", "二", "三", "四", "五", "六", "日")):
                tk.Label(grid_holder, text=name, bg=palette.surface,
                         fg=palette.text_muted, font=self.typography.caption,
                         width=3).grid(row=0, column=idx, pady=(0, 4))
            first = date(state["year"], state["month"], 1)
            start = first.weekday()
            days = (date(state["year"] + (state["month"] == 12),
                         (state["month"] % 12) + 1, 1) - first).days
            for offset in range(days):
                day = first + timedelta(days=offset)
                r, c = divmod(start + offset, 7)
                is_work = self.db.is_workday(day)
                is_today = day == date.today()
                fg = palette.text_primary if is_work else palette.text_muted
                # 今天用一块浅灰底标出来：强调色与正文同为 #1c1c1c，
                # 只靠字色根本看不出哪天是今天
                base_bg = palette.sidebar_active if is_today else palette.surface
                cell = tk.Label(grid_holder, text=str(day.day), width=3, pady=5,
                                bg=base_bg, fg=fg,
                                font=(self.typography.nav_item_active if is_today
                                      else (self.typography.body if is_work
                                            else self.typography.caption)),
                                cursor="hand2")
                cell.grid(row=r + 1, column=c)
                cell.bind("<Enter>",
                          lambda _e, w=cell: w.configure(bg=palette.surface_alt))
                cell.bind("<Leave>",
                          lambda _e, w=cell, b=base_bg: w.configure(bg=b))
                cell.bind("<Button-1>", lambda _e, d=day: pick(d))

        render()

    def _time_menu(self, _event=None):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return

        def set_time(text: str):
            self.db.update_item(item.id, {"due_time": text})
            self.refresh_all()

        self._popup([
            ("上午 9:00", lambda: set_time("09:00")),
            ("中午 12:00", lambda: set_time("12:00")),
            ("下午 14:00", lambda: set_time("14:00")),
            ("下午 18:00", lambda: set_time("18:00")),
            "---",
            ("自定…", lambda: self._ask_time(item.id)),
            ("清除时间", lambda: set_time("")),
        ])

    def _ask_time(self, item_id: int):
        value = simpledialog.askstring("时间", "请输入时间（HH:MM，例如 08:30）",
                                       initialvalue="09:00", parent=self)
        if not value:
            return
        text = value.strip()
        try:
            parts = text.replace("：", ":").split(":")
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except Exception:
            messagebox.showwarning("格式不对", "时间格式应为 HH:MM，例如 08:30", parent=self)
            return
        self.db.update_item(item_id, {"due_time": f"{hour:02d}:{minute:02d}"})
        self.refresh_all()

    def _advance_menu(self, _event=None):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return

        def set_advance(minutes: int):
            self.db.update_item(item.id, {"advance_minutes": minutes})
            self.refresh_all()

        actions = []
        for minutes, label in ADVANCE_CHOICES:
            mark = "✓ " if int(item.advance_minutes or 0) == minutes else ""
            actions.append((f"{mark}{label}",
                            (lambda m=minutes: set_advance(m))))
        self._popup(actions)

    def _repeat_menu(self, _event=None):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return

        def set_rule(rule: str):
            self.db.update_item(item.id, {"repeat_rule": rule})
            self.refresh_all()

        actions = [(label, (lambda r=rule: set_rule(r)))
                   for rule, label in REPEAT_RULES]
        actions.append("---")
        actions.append(("重复结束于…", self._repeat_until_dialog))
        self._popup(actions)

    def _repeat_until_dialog(self):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return
        value = simpledialog.askstring(
            "重复结束", "重复到哪一天为止？（YYYY-MM-DD，留空表示永不结束）",
            initialvalue=item.repeat_until or "", parent=self)
        if value is None:
            return
        text = value.strip()
        if text and parse_day(text) is None:
            messagebox.showwarning("格式不对", "日期格式应为 YYYY-MM-DD", parent=self)
            return
        self.db.update_item(item.id, {"repeat_until": text})
        self.refresh_all()

    def _priority_menu(self, _event=None):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return

        def set_level(level: int):
            self.db.update_item(item.id, {"priority": level})
            self.refresh_all()

        actions = [("无", lambda: set_level(0)),
                   ("低  !", lambda: set_level(1)),
                   ("中  !!", lambda: set_level(2)),
                   ("高  !!!", lambda: set_level(3))]
        self._popup(actions)

    def _list_menu(self, _event=None):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return

        def move(list_id: int):
            self.db.update_item(item.id, {"list_id": list_id})
            self.refresh_all()

        actions = [(f"●  {l.name}", (lambda lid=l.id: move(lid)))
                   for l in self.db.fetch_lists()]
        self._popup(actions)

    def _tags_dialog(self, _event=None):
        item = self.db.get_item(self.selected_item_id)
        if item is None:
            return
        value = simpledialog.askstring(
            "标签", "多个标签用空格或逗号分隔", 
            initialvalue=" ".join(item.tags), parent=self)
        if value is None:
            return
        tags = [t.strip() for t in value.replace(",", " ").split() if t.strip()]
        self.db.update_item(item.id, {"tags": tags})
        self.refresh_all()

    # ==================================================================
    # 清单的新建 / 编辑 / 删除
    # ==================================================================
    def new_list_dialog(self, list_id: Optional[int] = None):
        """新建或编辑清单：名称 + 12 色盘 + 图标盘。"""
        palette = self.palette
        editing = self.db.get_list(list_id) if list_id else None
        state = {
            "color": editing.color if editing else LIST_COLORS[5][1],
            "icon": editing.icon if editing else LIST_ICONS[0],
        }

        dlg = tk.Toplevel(self)
        dlg.title("编辑列表" if editing else "新建列表")
        dlg.configure(bg=palette.surface)
        dlg.transient(self.winfo_toplevel())
        dlg.resizable(False, False)

        # 大图标预览
        preview_holder = tk.Frame(dlg, bg=palette.surface)
        preview_holder.pack(pady=(18, 8))
        preview = tk.Label(preview_holder, bg=palette.surface)
        preview.pack()

        tk.Label(dlg, text="列表名称", bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.caption).pack(anchor="w", padx=24, pady=(6, 4))
        name_var = tk.StringVar(value=editing.name if editing else "")
        name_entry = tk.Entry(dlg, textvariable=name_var, bd=0,
                              bg=palette.surface_alt, fg=palette.text_primary,
                              font=self.typography.body,
                              insertbackground=palette.text_primary)
        name_entry.pack(fill="x", padx=24, ipady=7)

        def refresh_preview():
            preview.configure(image=todo_icons.tile_image(
                scaled_px(self, 34), state["color"], state["icon"]))

        # 12 色盘
        tk.Label(dlg, text="颜色", bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.caption).pack(anchor="w", padx=24, pady=(16, 6))
        color_grid = tk.Frame(dlg, bg=palette.surface)
        color_grid.pack(padx=24)
        color_cells = {}

        def choose_color(value: str):
            state["color"] = value
            for key, cell in color_cells.items():
                cell.configure(highlightbackground=(palette.accent if key == value
                                                    else palette.surface))
            refresh_preview()
            refresh_icon_tiles()

        for idx, (_label, value) in enumerate(LIST_COLORS):
            r, c = divmod(idx, 6)
            # 用 Frame 而不是 Label 画色块：Label 的 width 以**字符**为单位，
            # 会跟着字体大小漂移，做不出稳定的正方形色盘。
            cell = tk.Frame(color_grid, bg=value, width=34, height=34,
                            highlightthickness=2,
                            highlightbackground=palette.surface,
                            cursor="hand2")
            cell.grid(row=r, column=c, padx=5, pady=5)
            cell.grid_propagate(False)
            cell.bind("<Button-1>", lambda _e, v=value: choose_color(v))
            color_cells[value] = cell

        # 图标盘
        tk.Label(dlg, text="图标", bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.caption).pack(anchor="w", padx=24, pady=(14, 6))
        icon_grid = tk.Frame(dlg, bg=palette.surface)
        icon_grid.pack(padx=24, pady=(0, 8))
        icon_cells = {}

        def choose_icon(value: str):
            state["icon"] = value
            for key, cell in icon_cells.items():
                cell.configure(highlightbackground=(palette.accent if key == value
                                                    else palette.surface))
            refresh_preview()

        def refresh_icon_tiles():
            """图标盘按当前颜色渲染。

            全用灰底的话，二十个一模一样的灰色小方块上压着白色细图形，
            肉眼几乎分不出来；上色之后既看得清，也顺手预览了成品效果。
            """
            for key, cell in icon_cells.items():
                cell.configure(image=todo_icons.tile_image(
                    scaled_px(self, 22), state["color"], key))

        for idx, name in enumerate(LIST_ICONS):
            r, c = divmod(idx, 10)
            cell = tk.Label(icon_grid, bg=palette.surface,
                            highlightthickness=2,
                            highlightbackground=palette.surface,
                            cursor="hand2", padx=3, pady=3)
            cell.grid(row=r, column=c)
            cell.bind("<Button-1>", lambda _e, v=name: choose_icon(v))
            icon_cells[name] = cell

        footer = tk.Frame(dlg, bg=palette.surface)
        footer.pack(fill="x", padx=24, pady=(14, 16))

        def save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("缺少名称", "请先给列表起个名字", parent=dlg)
                return
            if editing:
                self.db.update_list(editing.id, name=name,
                                    color=state["color"], icon=state["icon"])
            else:
                new_id = self.db.add_list(name, state["color"], state["icon"])
                self.current_list_id = new_id
                self.current_scope = "list"
            dlg.destroy()
            self.refresh_all()

        ttk.Button(footer, text="取消", style="Quiet.TButton",
                   command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="保存", style="Primary.TButton",
                   command=save).pack(side="right")

        choose_color(state["color"])
        choose_icon(state["icon"])
        self._autosize_dialog(dlg, 400)
        name_entry.focus_set()
        dlg.bind("<Return>", lambda _e: save())

    def delete_list(self, list_id: int):
        todo_list = self.db.get_list(list_id)
        if todo_list is None:
            return
        if len(self.db.fetch_lists()) <= 1:
            messagebox.showinfo("无法删除", "至少要保留一个列表。", parent=self)
            return
        if not messagebox.askyesno(
                "删除列表",
                f"确定删除「{todo_list.name}」吗？\n列表里的待办也会一并删除。",
                parent=self):
            return
        self.db.delete_list(list_id)
        if self.current_list_id == list_id:
            self.current_list_id = None
            self.current_scope = "today"
        self.selected_item_id = None
        self.refresh_all()

    # ------------------------------------------------------------------
    # 节假日日历管理
    # ------------------------------------------------------------------
    def manage_holidays_dialog(self):
        """查看 / 增删节假日日历（次年安排公布后可在这里补录）。"""
        palette = self.palette
        dlg = tk.Toplevel(self)
        dlg.title("节假日日历")
        dlg.configure(bg=palette.surface)
        dlg.transient(self.winfo_toplevel())
        self._center_on_parent(dlg, 460, 520)

        tk.Label(dlg, text="节假日日历", bg=palette.surface,
                 fg=palette.text_primary,
                 font=self.typography.subtitle).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(dlg, text="内置已公布的年份；次年安排公布后可在这里补录。"
                          "「调休上班」用于把某个周末标记成工作日。",
                 bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.caption, wraplength=420,
                 justify="left").pack(anchor="w", padx=18)

        area = ScrollArea(dlg, bg=palette.surface)
        area.pack(fill="both", expand=True, padx=18, pady=(10, 8))

        def reload():
            area.clear()
            entries = self.db.fetch_holidays()
            if not entries:
                tk.Label(area.inner, text="日历为空", bg=palette.surface,
                         fg=palette.text_muted,
                         font=self.typography.body).pack(pady=20)
            current_year = None
            for entry in entries:
                year = entry.day[:4]
                if year != current_year:
                    current_year = year
                    tk.Label(area.inner, text=f"{year} 年", bg=palette.surface,
                             fg=palette.text_muted,
                             font=self.typography.nav_group).pack(
                        anchor="w", pady=(8, 2))
                row = tk.Frame(area.inner, bg=palette.surface)
                row.pack(fill="x")
                tk.Label(row, text=entry.day, bg=palette.surface,
                         fg=palette.text_primary, font=self.typography.body,
                         width=12, anchor="w").pack(side="left", pady=3)
                kind_color = (palette.success if entry.kind == "workday"
                              else palette.text_secondary)
                tk.Label(row, text=("调休上班" if entry.kind == "workday" else "放假"),
                         bg=palette.surface, fg=kind_color,
                         font=self.typography.caption, width=8).pack(side="left")
                tk.Label(row, text=entry.name, bg=palette.surface,
                         fg=palette.text_muted, font=self.typography.caption,
                         anchor="w").pack(side="left", fill="x", expand=True)
                remove = tk.Label(row, text="✕", bg=palette.surface,
                                  fg=palette.text_muted,
                                  font=self.typography.caption, cursor="hand2",
                                  padx=6)
                remove.pack(side="right")
                remove.bind("<Button-1>",
                            lambda _e, d=entry.day: (self.db.delete_holiday(d), reload()))
            area._on_inner_configure()

        add_bar = tk.Frame(dlg, bg=palette.surface)
        add_bar.pack(fill="x", padx=18, pady=(0, 4))
        tk.Label(dlg, text="格式：日期 YYYY-MM-DD　名称（可留空）　类型",
                 bg=palette.surface, fg=palette.text_muted,
                 font=self.typography.caption).pack(anchor="w", padx=18,
                                                    pady=(0, 12))
        day_var = tk.StringVar()
        name_var = tk.StringVar()
        kind_var = tk.StringVar(value="放假")
        tk.Entry(add_bar, textvariable=day_var, bd=0, bg=palette.surface_alt,
                 fg=palette.text_primary, font=self.typography.body,
                 insertbackground=palette.text_primary, width=12).pack(
            side="left", ipady=6)
        tk.Entry(add_bar, textvariable=name_var, bd=0, bg=palette.surface_alt,
                 fg=palette.text_primary, font=self.typography.body,
                 insertbackground=palette.text_primary, width=10).pack(
            side="left", padx=6, ipady=6)
        combo = ttk.Combobox(add_bar, textvariable=kind_var, width=9,
                             state="readonly",
                             values=["放假", "调休上班"])
        combo.pack(side="left")

        def add():
            day = day_var.get().strip()
            if parse_day(day) is None:
                messagebox.showwarning("格式不对", "日期格式应为 YYYY-MM-DD", parent=dlg)
                return
            kind = "workday" if kind_var.get() == "调休上班" else "holiday"
            self.db.set_holiday(day, name_var.get().strip() or "自定义", kind)
            day_var.set("")
            name_var.set("")
            reload()

        ttk.Button(add_bar, text="添加", style="Quiet.TButton",
                   command=add).pack(side="left", padx=6)

        reload()

    # ------------------------------------------------------------------
    def _autosize_dialog(self, dlg: tk.Toplevel, width: int, min_height: int = 0):
        """按内容实际高度定尺寸。

        固定高度会让内容少的弹窗把按钮吊在半空（实测「新建列表」就是这样），
        所以让 Tk 先算完请求高度再定几何。
        """
        dlg.update_idletasks()
        height = max(min_height, dlg.winfo_reqheight())
        self._center_on_parent(dlg, width, height)

    def _center_on_parent(self, dlg: tk.Toplevel, width: int, height: int):
        root = self.winfo_toplevel()
        try:
            x = root.winfo_rootx() + (root.winfo_width() - width) // 2
            y = root.winfo_rooty() + (root.winfo_height() - height) // 3
            dlg.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        except Exception:
            dlg.geometry(f"{width}x{height}")

    # ------------------------------------------------------------------
    def _set_placeholder(self, entry: tk.Entry, text: str) -> str:
        """给无边框输入框加灰色占位提示，返回占位文案。

        返回值的用途很重要：占位字会被写进 ``textvariable``，
        读取时若不把它排除掉，就会把提示语当成用户输入。
        """
        entry.insert(0, text)
        entry.configure(fg=self.palette.text_muted)

        def on_focus_in(_event=None):
            if entry.get() == text:
                entry.delete(0, "end")
                entry.configure(fg=self.palette.text_primary)

        def on_focus_out(_event=None):
            self._restore_placeholder(entry, None, text)

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        return text

    def _restore_placeholder(self, entry: tk.Entry, var, text: str):
        """输入被清空后把占位提示放回去。"""
        if entry.get().strip():
            return
        entry.delete(0, "end")
        entry.insert(0, text)
        entry.configure(fg=self.palette.text_muted)

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def _on_search_change(self, _event=None):
        value = self.search_var.get().strip()
        # 占位提示「搜索」会被写进 textvariable，必须排除，
        # 否则一进页面就等于带着「搜索」这个关键词过滤
        if value == self._search_placeholder:
            value = ""
        if value == self.keyword:
            return
        self._flush_editor()
        self.keyword = value
        self._render_item_list()

    # ------------------------------------------------------------------
    # 对外：主壳切到本页时调用
    # ------------------------------------------------------------------
    def refresh(self):
        """进入页面时刷新：先做一次顺延，再重画。"""
        self.db.rollover()
        self._subtask_summary_cache(self._fetch_current_items())
        self.refresh_all()
