# -*- coding: utf-8 -*-
"""记忆宫殿 · 界面。

六视图，三栏骨架，与 ``excel_page.py`` 同一套做法：**页面对象只建一次**，
之后靠 ``pack`` / ``pack_forget`` 切换视图（这样滚动位置与选中状态都保得住）。

    1 今日训练   SRS 队列 + 开始「走一遍」
    2 宫殿工作台 左：地点桩序列；右：桩上的记忆项
    3 记忆项库   全部记忆项 + 筛选 + 详情
    4 联想法则   教学卡（Markdown 渲染）
    5 题库训练   内置题库 → 一键变成记忆项
    6 打卡统计   日历 + 掌握度分布 + 正确率

「走一遍」（``WalkSession``）是本模块的**核心动作**，它刻意做成一独立窗口：

* **先给提示、再给答案** —— 这是主动回忆（active recall）与「重读」的分界线。
  界面顺序一旦反过来（先看到答案），练习效果直接归零。
* 自评三档（记得 / 模糊 / 忘了）**只写一次**，写回 ``memory_db.record_review``。

能力注入（与 Excel 宝典同一手法，本模块**不 import main、不 import todo_db**）
------------------------------------------------------------------------------
``session`` 只认 ``on_grade`` 回调；``todo_hook`` 是「生成今日训练待办」的落库动作；
``markdown`` 是 ``markdown_view`` 模块（渲染教学卡）；``images`` 是图片能力的注入包
（``MemoryImageTools``），``image_preview_cls`` 是账号中心那套预览组件 ——
**题库里每一条都能贴自己在游戏里截的图**。注意那套组件本身只做「显示 + 翻页」，
上传 / 粘贴入口得由调用方补（见 ``create_image_actions``，两个弹窗共用）。都由
``main`` 注入。
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import image_clipboard
import memory_db
import speech
import training_core as tc
from dialog_form_style import (apply_dialog_form_style, create_form_entry,
                               create_form_label)
from page_components import (add_toolbar_buttons, create_menu_button,
                             create_page_toolbar, create_status_bar,
                             create_two_pane_layout)
from ui_components import (ScrollArea, create_flat_action_button,
                           create_metric_card, create_section_frame,
                           create_ttk_section_header)
from ui_theme import MAIN_PALETTE, TYPOGRAPHY

try:                                   # 缩略图只是加分项：没有 PIL 就退化成文件名
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:                    # pragma: no cover - 便携版没有 PIL
    HAS_PIL = False

# 实景图落在账号中心那套统一目录下（``ACCOUNT_IMAGE_DIR / memory_items``），
# 与流程截图、笔记截图同一个存储协议，搬机器时一起跟着走。
MEMORY_IMAGE_SUBDIR = "memory_items"

_THUMB_CACHE: dict = {}


def _load_thumbnail(path, size=(196, 128)):
    """读图并缩到指定尺寸；读不出来返回 ``None``（调用方退化成显示文件名）。"""
    if not HAS_PIL:
        return None
    key = (str(path), int(size[0]), int(size[1]))
    if key in _THUMB_CACHE:
        return _THUMB_CACHE[key]
    try:
        image = Image.open(str(path))
        image.thumbnail(size)
        photo = ImageTk.PhotoImage(image)
    except Exception:
        return None
    _THUMB_CACHE[key] = photo
    return photo


def _open_with_system(path) -> None:
    """用系统默认程序打开（双击缩略图 / 点「看大图」时用）。打不开就算了，不弹错。"""
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))      # noqa: S606 - Windows 桌面应用，用户自己点开的
    except Exception:
        pass


class MemoryImageTools:
    """图片能力的注入包（与 ``ExcelImageTools`` / ``ProcessImageTools`` 同构）。

    ``memory_page`` 不能 import main（会形成循环依赖），但截图又必须复用账号中心
    那套「相对路径 + 统一目录」的存储协议，所以把用得到的几个函数打成一个对象传进来。
    """

    def __init__(self, *, base_dir, resolve_paths, storage_value, make_dir,
                 parse_items, serialize_items):
        self.base_dir = base_dir
        self.resolve_paths = resolve_paths
        self.storage_value = storage_value
        self.make_dir = make_dir
        self.parse_items = parse_items
        self.serialize_items = serialize_items


def create_image_actions(parent, *, preview, app_title, images, host=None,
                         palette=MAIN_PALETTE):
    '''给实景图预览补一排动作按钮（上传 / 粘贴 / 看大图 / 移除当前）。

    **为什么必须补**：``AccountImagePreview`` 只做「显示 + 翻页」，上传入口是
    调用方的活（见 ``credential_process_dialogs`` 里那两处各 5 个按钮）。少了
    这一排，空状态文案里那句「点上传截图」就是个死链 —— 用户点不到任何东西。

    ``host`` 是弹窗自身（文件选择框 / 提示框的 parent），不传就退回 ``parent``。
    '''
    host = host if host is not None else parent
    row = tk.Frame(parent, bg=palette.bg)
    row.pack(anchor="w", pady=(6, 0))

    def add_from_file():
        preview.choose_image(parent=host)

    def add_from_clipboard():
        """游戏里 Win+Shift+S 截完直接粘 —— CS 玩家最顺手的一条路。

        剪贴板里没有图**不是错误**，只提示一句；读图/存盘失败也不许抛到
        Tk 回调外（会静默吞掉整次点击）。
        """
        path = None
        try:
            if images is not None:
                path = image_clipboard.save_clipboard_image(
                    host, images.make_dir(MEMORY_IMAGE_SUBDIR))
        except Exception:                    # noqa: BLE001 - 剪贴板不是图 / 存盘失败
            path = None
        if path is None:
            messagebox.showinfo(
                app_title,
                "剪贴板里没有图片。游戏里按 Win+Shift+S 截一张，再点这里。",
                parent=host)
            return
        items = list(images.parse_items(preview.get_value()))
        items.append({"path": images.storage_value(path), "label": ""})
        preview.set_value(images.serialize_items(items))

    for text, command in (("上传截图", add_from_file),
                          ("粘贴截图", add_from_clipboard),
                          ("查看大图", lambda: preview.open_large_viewer(parent=host)),
                          ("移除当前", preview.remove_current)):
        create_flat_action_button(row, text, command).pack(side="left", padx=(0, 6))
    return row


# ----------------------------------------------------------------------
# 视图
# ----------------------------------------------------------------------
VIEW_TODAY = "today"
VIEW_WORKBENCH = "workbench"
VIEW_LIBRARY = "library"
VIEW_METHODS = "methods"
VIEW_BANKS = "banks"
VIEW_STATS = "stats"
VIEW_CHOICES = (
    (VIEW_TODAY, "今日训练"),
    (VIEW_WORKBENCH, "宫殿工作台"),
    (VIEW_LIBRARY, "记忆项库"),
    (VIEW_METHODS, "联想法则"),
    (VIEW_BANKS, "题库训练"),
    (VIEW_STATS, "打卡统计"),
)
VIEW_LABELS = dict(VIEW_CHOICES)

TREE_VIEW, TREE_PALACE = "view", "palace"

GUTTER = 24
LEFT_WIDTH = 248
NAV_TREE_WIDTH = 190
NAV_COUNT_WIDTH = 44

MASTERY_FILTER_CHOICES = (("all", "全部掌握度"),) + tuple(
    (str(value), label) for value, label in tc.MASTERY_CHOICES)


# ======================================================================
# 对话框
# ======================================================================
class BankItemDialog(tk.Toplevel):
    """题库里某一条的**完整内容** —— 双击那一条打开。

    为什么要有它：题库表格的三列（序 / 题目 / 答案）天生装不下「答案 + 位置与四周」，
    列宽一拉就把别的列挤没了 —— 用户的原话是「最好能双击打开，要不然显示不全」。
    所以列表只做索引，**完整内容在弹窗里看**。

    这里能改的只有两样：``detail``（自己补的位置笔记）与 ``images``（游戏里截的图）。
    题目 / 答案 / 提示都由内置种子决定，不让就地改 —— 改了会被下次 ``seed_banks``
    覆盖回去，用户会以为「改了没用」。
    """

    def __init__(self, parent, *, app_title, item, images=None,
                 image_preview_cls=None, on_save=None, palette=MAIN_PALETTE,
                 typography=TYPOGRAPHY):
        super().__init__(parent)
        self.item = dict(item)
        self.app_title = app_title
        self.images = images
        self.image_preview_cls = image_preview_cls
        self.on_save = on_save
        self.palette = palette
        self.typography = typography
        self.saved = False

        self.title(f"第 {self.item.get('seq', '')} 条 · {self.item.get('question', '')}")
        self.configure(bg=palette.bg)
        self.geometry("740x640")
        self.minsize(560, 460)
        self._build()
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.bind("<Escape>", lambda _e: self.destroy())

    # -- 构建 -----------------------------------------------------------
    def _build(self):
        palette, font = self.palette, self.typography
        scroll = ScrollArea(self, bg=palette.bg)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        tk.Label(body, text=f"第 {self.item.get('seq', '')} 条 · {self.item.get('question', '')}",
                 bg=palette.bg, fg=palette.text_primary, font=font.title,
                 wraplength=640, justify="left").pack(anchor="w", pady=(0, 10))

        self._field(body, "答案", str(self.item.get("answer", "") or "—"))
        self._field(body, "记忆钩子", str(self.item.get("hint", "") or "—"))

        frame = create_section_frame(body, "位置与四周（可以自己补充）")
        frame.pack(fill="x", pady=(10, 0))
        self.detail_text = tk.Text(frame, height=6, wrap="word",
                                   highlightthickness=1,
                                   highlightbackground=palette.border_soft)
        self.detail_text.pack(fill="x")
        self.detail_text.insert("1.0", str(self.item.get("detail", "") or ""))

        shots = create_section_frame(body, "实景截图（游戏里截的图贴这儿最有用）")
        shots.pack(fill="x", pady=(10, 0))
        if self.image_preview_cls is not None and self.images is not None:
            self.image_preview = self.image_preview_cls(
                shots, str(self.item.get("images", "") or ""),
                preview_size=(220, 150),
                empty_text="还没有截图：点「上传截图」选一张，或在游戏里"
                           "Win+Shift+S 截完点「粘贴截图」。",
                image_subdir=MEMORY_IMAGE_SUBDIR)
            self.image_preview.build(shots).pack(fill="x")
            create_image_actions(shots, preview=self.image_preview,
                                 app_title=self.app_title, images=self.images,
                                 host=self)
        else:
            self.image_preview = None
            tk.Label(shots, text="图片功能没接线（images 未注入）。", bg=palette.bg,
                     fg=palette.text_muted, font=font.caption).pack(anchor="w")

        tk.Label(body, text="提示：图片存在账号图片目录的 memory_items 下，"
                            "换机器时跟其它截图一起搬。",
                 bg=palette.bg, fg=palette.text_muted, font=font.caption,
                 wraplength=640, justify="left").pack(anchor="w", pady=(10, 0))

        actions = tk.Frame(self, bg=palette.bg)
        actions.pack(side="bottom", fill="x", padx=20, pady=14)
        create_flat_action_button(actions, "保存", self._save).pack(side="right")
        create_flat_action_button(actions, "取消", self.destroy).pack(side="right", padx=6)

    def _field(self, parent, title, text):
        frame = create_section_frame(parent, title)
        frame.pack(fill="x", pady=(0, 8))
        tk.Label(frame, text=text, bg=self.palette.bg, fg=self.palette.text_primary,
                 font=self.typography.body, wraplength=640,
                 justify="left").pack(anchor="w")

    # -- 保存 -----------------------------------------------------------
    def _save(self):
        detail = self.detail_text.get("1.0", "end").strip()
        images = self.image_preview.get_value() if self.image_preview is not None \
            else str(self.item.get("images", "") or "")
        if self.on_save is not None:
            if not self.on_save(int(self.item["id"]), detail, images):
                return
        self.saved = True
        self.destroy()


class PalaceDialog(simpledialog.Dialog):
    """新建 / 编辑一座宫殿。"""

    def __init__(self, parent, title, *, app_title, initial=None):
        self.initial = dict(initial or {})
        self.app_title = app_title
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MemPalaceDialog")
        self.entries: dict[str, tk.Widget] = {}
        rows = [
            ("name", "名称", 30),
            ("route_note", "路线说明", 40),
            ("tags", "标签", 30),
        ]
        row_index = 0
        create_form_label(master, "类型", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="w", padx=6, pady=4)
        self.kind_var = tk.StringVar(value=str(self.initial.get("kind") or "自定义"))
        ttk.Combobox(master, textvariable=self.kind_var,
                     values=list(memory_db_kinds()), state="readonly", width=16).grid(
            row=row_index, column=1, sticky="w", padx=6, pady=4)
        row_index += 1

        for field, label, width in rows:
            create_form_label(master, label, palette=MAIN_PALETTE).grid(
                row=row_index, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=width)
            entry.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, str(self.initial.get(field, "") or ""))
            self.entries[field] = entry
            row_index += 1

        create_form_label(master, "简介", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="nw", padx=6, pady=4)
        self.desc_text = tk.Text(master, width=40, height=5, wrap="word")
        self.desc_text.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
        self.desc_text.insert("1.0", str(self.initial.get("description", "") or ""))

        master.columnconfigure(1, weight=1)
        return self.entries["name"]

    def validate(self):
        if not self.entries["name"].get().strip():
            messagebox.showwarning(self.app_title, "宫殿名称不能为空。", parent=self)
            return False
        return True

    def apply(self):
        self.result = {
            "name": self.entries["name"].get().strip(),
            "kind": self.kind_var.get().strip() or "自定义",
            "route_note": self.entries["route_note"].get().strip(),
            "tags": self.entries["tags"].get().strip(),
            "description": self.desc_text.get("1.0", "end").strip(),
        }


def memory_db_kinds():
    return ("住宅", "通勤", "虚拟", "自定义")


class ItemDialog(simpledialog.Dialog):
    """新建 / 编辑一条记忆项。"""

    def __init__(self, parent, title, *, app_title, palaces, loci,
                 initial=None, default_locus_id=0, images=None,
                 image_preview_cls=None):
        self.initial = dict(initial or {})
        self.app_title = app_title
        self.palaces = list(palaces or [])
        self.loci = list(loci or [])
        self.default_locus_id = int(default_locus_id or 0)
        self.images = images
        self.image_preview_cls = image_preview_cls
        self.image_preview = None
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MemItemDialog")
        self.entries: dict[str, tk.Widget] = {}
        row_index = 0

        create_form_label(master, "宫殿", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="w", padx=6, pady=4)
        self.palace_names = [p["name"] for p in self.palaces]
        current_palace = str(self.initial.get("palace_name") or "")
        if not current_palace and self.palaces:
            current_palace = self.palaces[0]["name"]
        self.palace_var = tk.StringVar(value=current_palace or "（未归档）")
        box = ttk.Combobox(master, textvariable=self.palace_var,
                           values=["（未归档）"] + self.palace_names,
                           state="readonly", width=28)
        box.grid(row=row_index, column=1, sticky="w", padx=6, pady=4)
        box.bind("<<ComboboxSelected>>", lambda _e: self._reload_loci())
        row_index += 1

        create_form_label(master, "地点桩", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="w", padx=6, pady=4)
        self.locus_var = tk.StringVar(value="（不指定）")
        self.locus_box = ttk.Combobox(master, textvariable=self.locus_var,
                                      values=["（不指定）"], state="readonly", width=28)
        self.locus_box.grid(row=row_index, column=1, sticky="w", padx=6, pady=4)
        row_index += 1

        for field, label, width in (
            ("front", "要记的（题面）", 40),
            ("back", "答案 / 解释", 40),
            ("imagery", "联想画面", 40),
            ("story", "故事链", 40),
            ("category", "分类", 24),
            ("tags", "标签", 24),
        ):
            create_form_label(master, label, palette=MAIN_PALETTE).grid(
                row=row_index, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=width)
            entry.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            entry.insert(0, str(self.initial.get(field, "") or ""))
            self.entries[field] = entry
            row_index += 1

        create_form_label(master, "详情 / 位置与四周", palette=MAIN_PALETTE).grid(
            row=row_index, column=0, sticky="nw", padx=6, pady=4)
        self.detail_text = tk.Text(master, width=40, height=4, wrap="word")
        self.detail_text.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
        self.detail_text.insert("1.0", str(self.initial.get("detail", "") or ""))
        row_index += 1

        if self.image_preview_cls is not None and self.images is not None:
            create_form_label(master, "实景图", palette=MAIN_PALETTE).grid(
                row=row_index, column=0, sticky="nw", padx=6, pady=4)
            holder = ttk.Frame(master)
            holder.grid(row=row_index, column=1, sticky="ew", padx=6, pady=4)
            self.image_preview = self.image_preview_cls(
                holder, str(self.initial.get("images", "") or ""),
                preview_size=(220, 150),
                empty_text="未贴截图（桩位的实景照片放这儿）：点「上传截图」"
                           "选文件，或截图后点「粘贴截图」。",
                image_subdir=MEMORY_IMAGE_SUBDIR)
            self.image_preview.build(holder).pack(fill="x")
            create_image_actions(holder, preview=self.image_preview,
                                 app_title=self.app_title, images=self.images,
                                 host=self)

        master.columnconfigure(1, weight=1)
        self._reload_loci()
        return self.entries["front"]

    def _selected_palace(self):
        name = self.palace_var.get().strip()
        for palace in self.palaces:
            if palace["name"] == name:
                return palace
        return None

    def _reload_loci(self):
        palace = self._selected_palace()
        loci = [l for l in self.loci
                if palace and int(l["palace_id"]) == int(palace["id"])]
        names = [f"{int(l['seq']) + 1}. {l['name']}" for l in loci]
        self.locus_box.configure(values=["（不指定）"] + names)
        target = 0
        for index, locus in enumerate(loci):
            if int(locus["id"]) == int(self.initial.get("locus_id") or 0):
                target = index + 1
                break
        else:
            for index, locus in enumerate(loci):
                if int(locus["id"]) == self.default_locus_id:
                    target = index + 1
                    break
        self.locus_var.set((["（不指定）"] + names)[min(target, len(names))])

    def validate(self):
        if not self.entries["front"].get().strip():
            messagebox.showwarning(self.app_title, "「要记的」不能为空。", parent=self)
            return False
        return True

    def apply(self):
        palace = self._selected_palace()
        locus_id = 0
        label = self.locus_var.get().strip()
        if label and label != "（不指定）" and palace:
            loci = [l for l in self.loci
                    if int(l["palace_id"]) == int(palace["id"])]
            for index, locus in enumerate(loci):
                if f"{int(locus['seq']) + 1}. {locus['name']}" == label:
                    locus_id = int(locus["id"])
                    break
        payload = {field: widget.get().strip()
                   for field, widget in self.entries.items()}
        payload["detail"] = self.detail_text.get("1.0", "end").strip()
        if self.image_preview is not None:
            payload["images"] = self.image_preview.get_value()
        payload["palace_id"] = int(palace["id"]) if palace else 0
        payload["locus_id"] = locus_id
        self.result = payload


# ======================================================================
# 走一遍（核心动作）
# ======================================================================
class WalkSession(tk.Toplevel):
    """逐桩回忆。

    **顺序不可颠倒**：先出「第 N 站 + 桩名 + 桩的提示」，用户在心里复述，
    按「显示答案」才给出记忆项内容。答案没展开之前，自评按钮是**禁用**的。

    本类不认识数据库：自评通过 ``on_grade(item, feedback)`` 回调交出去，
    这样测试可以注入一个假的记录器，验证「先提示后答案」与「只写一次」。
    """

    def __init__(self, master, items, *, app_title="个人系统", title="走一遍",
                 palette=MAIN_PALETTE, typography=TYPOGRAPHY, images=None,
                 on_grade=None, on_finish=None, on_close=None):
        super().__init__(master)
        self.title(title)
        self.configure(bg=palette.bg)
        self.geometry("760x560")
        self.minsize(620, 460)

        self.items = list(items or [])
        self.index = 0
        self.revealed = False
        self.graded = False          # 当前这一站是否已经评过（防止双击写两次）
        self.results: list[dict] = []
        self.on_grade = on_grade
        self.on_finish = on_finish
        self.on_close = on_close
        self.palette = palette
        self.typography = typography
        self.app_title = app_title
        self.images = images
        self.finished = False

        self._build()
        self._render_current()
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<space>", lambda _e: self._on_space())
        self.bind("<Key-1>", lambda _e: self.grade(tc.FEEDBACK_FORGOT))
        self.bind("<Key-2>", lambda _e: self.grade(tc.FEEDBACK_VAGUE))
        self.bind("<Key-3>", lambda _e: self.grade(tc.FEEDBACK_KNOWN))
        self.protocol("WM_DELETE_WINDOW", self.close)

    # -- 构建 -----------------------------------------------------------
    def _build(self):
        palette = self.palette
        self.head_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.head_var, bg=palette.bg,
                 fg=palette.text_muted, font=self.typography.caption).pack(
            anchor="w", padx=24, pady=(16, 4))

        self.station_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.station_var, bg=palette.bg,
                 fg=palette.text_primary, font=self.typography.title).pack(
            anchor="w", padx=24)

        self.hint_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.hint_var, bg=palette.bg,
                 fg=palette.text_muted, font=self.typography.body,
                 wraplength=680, justify="left").pack(anchor="w", padx=24, pady=(4, 10))

        # 答案区：**未展开时整块不 pack**，不是仅仅藏文字
        self.answer_frame = create_section_frame(self, "答案")
        self.front_var = tk.StringVar(value="")
        self.back_var = tk.StringVar(value="")
        self.imagery_var = tk.StringVar(value="")
        self.story_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")
        for var, font, tone in (
            (self.front_var, self.typography.subtitle, "primary"),
            (self.back_var, self.typography.body, "primary"),
            (self.imagery_var, self.typography.body, "muted"),
            (self.story_var, self.typography.body, "muted"),
            (self.detail_var, self.typography.body, "muted"),
        ):
            color = palette.text_primary if tone == "primary" else palette.text_muted
            tk.Label(self.answer_frame, textvariable=var, bg=palette.bg, fg=color,
                     font=font, wraplength=660, justify="left").pack(
                anchor="w", pady=2)

        # 实景图：**只在揭示答案之后出现**（先提示后答案的顺序不能破）
        self.shot_var = tk.StringVar(value="")
        tk.Label(self.answer_frame, textvariable=self.shot_var, bg=palette.bg,
                 fg=palette.text_muted, font=self.typography.caption).pack(anchor="w")
        self.shot_host = tk.Frame(self.answer_frame, bg=palette.bg)
        self.shot_host.pack(anchor="w", pady=(4, 0))

        buttons = tk.Frame(self, bg=palette.bg)
        buttons.pack(side="bottom", fill="x", padx=24, pady=16)
        self.reveal_button = create_flat_action_button(
            buttons, "显示答案（空格）", self.show_answer)
        self.reveal_button.pack(side="left")
        # 朗读在「走一遍」里最用得上：眼睛盯着桩位，耳朵听答案
        self.speech_button = create_flat_action_button(
            buttons, "朗读：关", self.toggle_speech)
        self.speech_button.pack(side="left", padx=(8, 0))

        self.grade_buttons: dict[str, tk.Widget] = {}
        for value, label in ((tc.FEEDBACK_KNOWN, "记得（3）"),
                             (tc.FEEDBACK_VAGUE, "模糊（2）"),
                             (tc.FEEDBACK_FORGOT, "忘了（1）")):
            button = create_flat_action_button(
                buttons, label, lambda v=value: self.grade(v))
            button.pack(side="right", padx=4)
            button.configure(state="disabled")
            self.grade_buttons[value] = button

    # -- 渲染 -----------------------------------------------------------
    # -- 朗读 -----------------------------------------------------------
    def toggle_speech(self):
        """开关朗读。**关掉时要把正在念的那句掐断**，不然会一路念到下一题。"""
        on = speech.toggle()
        self.speech_button.configure(text=f"朗读：{'开' if on else '关'}")
        # 机器上不能念时 toggle() 还是 False，按钮就照着返回值显示 ——
        # 用户不会看到「明明开了却没声音」。
        if on:
            self._speak_current()
        else:
            speech.stop()

    def _speak_current(self):
        """念当前这一站：**没揭示只念提示**，揭示了才连答案一起念（别剧透）。"""
        if not speech.enabled():
            return
        parts = [self.station_var.get(), self.hint_var.get()]
        if self.revealed:
            parts += [self.front_var.get(), self.back_var.get()]
        speech.speak("。".join(str(p).strip() for p in parts if str(p).strip()))

    def _render_current(self):
        if not self.items:
            self.head_var.set("没有可练的内容")
            self.station_var.set("先去「宫殿工作台」建几个桩、挂几条记忆项")
            self.hint_var.set("")
            self.reveal_button.configure(state="disabled")
            return
        if self.index >= len(self.items):
            self._render_summary()
            return

        item = self.items[self.index]
        station = int(item.get("station") or 0)
        locus = str(item.get("locus_name") or "（未分配桩）")
        self.head_var.set(f"第 {self.index + 1} / {len(self.items)} 站")
        self.station_var.set(f"第 {station} 站 · {locus}" if station else locus)
        self.hint_var.set(str(item.get("locus_hint") or ""))

        self.revealed = False
        self.graded = False
        self.front_var.set("")
        self.back_var.set("")
        self.imagery_var.set("")
        self.story_var.set("")
        self.detail_var.set("")
        self.shot_var.set("")
        self._clear_shots()
        self.answer_frame.pack_forget()
        self.reveal_button.configure(state="normal", text="显示答案（空格）")
        for button in self.grade_buttons.values():
            button.configure(state="disabled")
        self._speak_current()

    # -- 实景图 ---------------------------------------------------------
    def _clear_shots(self):
        for child in self.shot_host.winfo_children():
            child.destroy()

    def _shot_paths(self, item) -> list:
        if self.images is None:
            return []
        try:
            paths = list(self.images.resolve_paths(item.get("images") or ""))
        except Exception:
            return []
        return [p for p in paths if str(p) and os.path.exists(str(p))]

    def _render_shots(self, item):
        """这一桩的实景图缩略图。读不出图就退化成文件名，不弹错。"""
        self._clear_shots()
        paths = self._shot_paths(item)
        if not paths:
            self.shot_var.set("")
            return
        self.shot_var.set(f"实景图 {len(paths)} 张（双击看大图）：")
        for path in paths[:3]:
            thumb = _load_thumbnail(path)
            if thumb is None:
                tk.Label(self.shot_host, text=str(path), bg=self.palette.bg,
                         fg=self.palette.text_muted, anchor="w",
                         font=self.typography.caption).pack(side="left", padx=4)
                continue
            label = tk.Label(self.shot_host, image=thumb, bd=0, bg=self.palette.bg)
            label.image = thumb
            label.bind("<Double-1>", lambda _e, p=path: _open_with_system(p))
            label.pack(side="left", padx=4)

    def show_answer(self):
        """展开答案。**这是唯一会显示答案的路径。**"""
        if self.index >= len(self.items) or self.revealed:
            return
        item = self.items[self.index]
        self.front_var.set(f"要记的：{item.get('front', '')}")
        back = str(item.get("back") or "").strip()
        self.back_var.set(f"答案：{back}" if back else "")
        imagery = str(item.get("imagery") or "").strip()
        self.imagery_var.set(f"联想画面：{imagery}" if imagery else "")
        story = str(item.get("story") or "").strip()
        self.story_var.set(f"故事链：{story}" if story else "")
        detail = str(item.get("detail") or "").strip()
        self.detail_var.set(f"位置与四周：{detail}" if detail else "")
        self._render_shots(item)
        self.answer_frame.pack(fill="x", padx=24, pady=(6, 10))
        self.revealed = True
        self.reveal_button.configure(state="disabled")
        self._speak_current()
        for button in self.grade_buttons.values():
            button.configure(state="normal")

    def grade(self, feedback):
        """自评。**答案没展开不许评**；同一站**只写一次**。"""
        if not self.revealed or self.graded:
            return
        if self.index >= len(self.items):
            return
        item = self.items[self.index]
        self.graded = True
        for button in self.grade_buttons.values():
            button.configure(state="disabled")
        self.results.append({
            "item_id": item.get("id"), "feedback": feedback,
            "front": item.get("front", ""), "back": item.get("back", ""),
        })
        if self.on_grade is not None:
            self.on_grade(item, feedback)
        self.index += 1
        self._render_current()

    def _on_space(self):
        if self.revealed:
            self.grade(tc.FEEDBACK_KNOWN)
        else:
            self.show_answer()

    # -- 结算 -----------------------------------------------------------
    def summary(self) -> dict:
        reviewed = len(self.results)
        correct = sum(1 for r in self.results if r["feedback"] == tc.FEEDBACK_KNOWN)
        return {
            "total": len(self.items), "reviewed": reviewed, "correct": correct,
            "accuracy": tc.accuracy(reviewed, correct),
        }

    def _render_summary(self):
        self.finished = True
        data = self.summary()
        self.head_var.set("本轮结束")
        self.station_var.set(f"走了 {data['reviewed']} 站")
        self.hint_var.set(
            f"记得 {data['correct']} 条 · 正确率 {tc.accuracy_percent(data['reviewed'], data['correct'])}"
            f"　—— 记得的会越隔越久再出现，忘了的明天就会再来。")
        self.answer_frame.pack_forget()
        self.reveal_button.configure(state="disabled")
        for button in self.grade_buttons.values():
            button.configure(state="disabled")
        if self.on_finish is not None:
            self.on_finish(data)

    def close(self):
        speech.stop()   # 关了窗就别再念（PowerShell 进程活着就是在念）
        if self.on_close is not None:
            try:
                self.on_close(self.summary())
            except Exception:  # noqa: BLE001 - 关闭时的回调不该把窗口卡住
                pass
        self.destroy()


# ======================================================================
# 页面
# ======================================================================
class MemoryPalacePage(ttk.Frame):
    """记忆宫殿页面。由 ``main`` 建一次，之后靠 pack / pack_forget 切换。"""

    def __init__(self, master, db, *, app_title="个人系统",
                 on_status=None, todo_hook=None, markdown=None,
                 images=None, image_preview_cls=None,
                 palette=MAIN_PALETTE, typography=TYPOGRAPHY):
        super().__init__(master)
        self.db = db
        self.app_title = app_title
        self.on_status = on_status
        # 「生成今日训练待办」的落库动作，由 main 注入 —— 本模块不认识 todo_db
        self.todo_hook = todo_hook
        # markdown_view 模块，用来渲染教学卡；没注入就退化成纯文本
        self.markdown = markdown
        # 图片能力：`images` 是路径/落盘工具，`image_preview_cls` 是账号中心那套预览组件
        # —— 都由 main 注入，本模块不 import main。
        self.images = images
        self.image_preview_cls = image_preview_cls
        self.palette = palette
        self.typography = typography

        self.view_key = VIEW_TODAY
        self.current_palace_id: int | None = None
        self.current_locus_id: int | None = None
        self.selected_item_id: int | None = None
        self.selected_card_code: str | None = None
        self.selected_bank_id: int | None = None
        self.walk_window: WalkSession | None = None
        # 左栏重建签名：内容没变就不重建（重建会清掉选中 -> 触发选中事件 -> 自激）
        self._nav_signature: list | None = None

        self.search_var = tk.StringVar()
        self.mastery_var = tk.StringVar(value=MASTERY_FILTER_CHOICES[0][1])
        self.category_var = tk.StringVar(value="全部分类")
        self.title_var = tk.StringVar(value=VIEW_LABELS[VIEW_TODAY])
        self.meta_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="记忆宫殿已就绪。")
        self.today_due_var = tk.StringVar(value="0")
        self.today_new_var = tk.StringVar(value="0")
        self.today_streak_var = tk.StringVar(value="0")
        self.stats_minutes_var = tk.StringVar(value="0")
        self.stats_days_var = tk.StringVar(value="0")
        self.stats_accuracy_var = tk.StringVar(value="—")

        self._build()
        self.refresh()

    # ==================================================================
    # 构建
    # ==================================================================
    def _build(self):
        self._build_toolbar()
        _, left, right = create_two_pane_layout(
            self, left_width=LEFT_WIDTH, right_pad=(16, 0),
            padding=(GUTTER, 0, GUTTER, 16))
        self._build_nav(left)
        self._build_right(right)
        create_status_bar(self, self.status_var, padding=(GUTTER, 0, GUTTER, 16))

    def _build_toolbar(self):
        toolbar = create_page_toolbar(self)
        add_toolbar_buttons(toolbar, [
            ("开始今日训练", self.start_today_training, "Primary.TButton"),
            ("新建宫殿", self.add_palace),
            ("新建记忆项", self.add_item),
            ("走一遍", self.walk_current_palace),
        ])
        create_menu_button(toolbar, "更多", [
            ("导入内置宫殿模板", self.import_templates),
            ("导入 100 数字桩", self.import_pegs),
            "---",
            ("生成今日训练待办", self.make_today_todo),
            ("手动打卡", self.checkin_today),
            "---",
            ("导出记忆项为 Markdown", self.export_items_markdown),
        ])

    # -- 左栏 -----------------------------------------------------------
    def _build_nav(self, parent):
        create_ttk_section_header(parent, "训练 / 宫殿").pack(anchor="w", pady=(0, 6))
        self.nav_tree = ttk.Treeview(parent, columns=("count",),
                                     show="tree headings", height=26,
                                     selectmode="browse")
        self.nav_tree.heading("#0", text="视图 / 宫殿", anchor="w")
        self.nav_tree.heading("count", text="数", anchor="e")
        self.nav_tree.column("#0", width=NAV_TREE_WIDTH, minwidth=120,
                             stretch=True, anchor="w")
        self.nav_tree.column("count", width=NAV_COUNT_WIDTH, minwidth=36,
                             stretch=False, anchor="e")
        self.nav_tree.pack(fill="both", expand=True)
        self.nav_tree.bind("<<TreeviewSelect>>", self._on_nav_select)

    # -- 右栏 -----------------------------------------------------------
    def _build_right(self, parent):
        head = tk.Frame(parent, bg=self.palette.bg)
        head.pack(fill="x")
        tk.Label(head, textvariable=self.title_var, bg=self.palette.bg,
                 fg=self.palette.text_primary,
                 font=self.typography.subtitle).pack(side="left")
        tk.Label(head, textvariable=self.meta_var, bg=self.palette.bg,
                 fg=self.palette.text_muted,
                 font=self.typography.caption).pack(side="left", padx=12)

        # 六个视图帧**建一次**，切换只 pack / pack_forget
        self.views: dict[str, tk.Frame] = {}
        for key, builder in (
            (VIEW_TODAY, self._build_today_view),
            (VIEW_WORKBENCH, self._build_workbench_view),
            (VIEW_LIBRARY, self._build_library_view),
            (VIEW_METHODS, self._build_methods_view),
            (VIEW_BANKS, self._build_banks_view),
            (VIEW_STATS, self._build_stats_view),
        ):
            frame = tk.Frame(parent, bg=self.palette.bg)
            self.views[key] = frame
            builder(frame)

    # ---- 视图 1：今日训练 ---------------------------------------------
    def _build_today_view(self, parent):
        cards = tk.Frame(parent, bg=self.palette.bg)
        cards.pack(fill="x", pady=(12, 8))
        create_metric_card(cards, "今天到期", self.today_due_var,
                           "到点该复习的记忆项。别跳，跳过就等于重学。").pack(
            side="left", padx=(0, 10))
        create_metric_card(cards, "建议新学", self.today_new_var,
                           "想练得多，先把复习清干净。").pack(side="left", padx=10)
        create_metric_card(cards, "连续打卡", self.today_streak_var,
                           "今天没打卡不算断 —— 夜里过了点不会归零。").pack(
            side="left", padx=10)

        bar = tk.Frame(parent, bg=self.palette.bg)
        bar.pack(fill="x", pady=(4, 6))
        create_flat_action_button(bar, "开始今日训练", self.start_today_training).pack(
            side="left")
        create_flat_action_button(bar, "生成今日训练待办", self.make_today_todo).pack(
            side="left", padx=8)
        create_flat_action_button(bar, "手动打卡", self.checkin_today).pack(side="left")

        self.today_tree = self._make_item_tree(parent)

    # ---- 视图 2：宫殿工作台 -------------------------------------------
    def _build_workbench_view(self, parent):
        split = tk.Frame(parent, bg=self.palette.bg)
        split.pack(fill="both", expand=True, pady=(12, 0))

        left = tk.Frame(split, bg=self.palette.bg, width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        create_ttk_section_header(left, "地点桩（走一遍的顺序）").pack(anchor="w")
        self.locus_tree = ttk.Treeview(left, columns=("seq", "count"),
                                       show="tree headings", height=16,
                                       selectmode="browse")
        self.locus_tree.heading("#0", text="桩", anchor="w")
        self.locus_tree.heading("seq", text="序", anchor="e")
        self.locus_tree.heading("count", text="项", anchor="e")
        self.locus_tree.column("#0", width=170, anchor="w")
        self.locus_tree.column("seq", width=34, anchor="e", stretch=False)
        self.locus_tree.column("count", width=34, anchor="e", stretch=False)
        self.locus_tree.pack(fill="both", expand=True)
        self.locus_tree.bind("<<TreeviewSelect>>", self._on_locus_select)

        locus_actions = tk.Frame(left, bg=self.palette.bg)
        locus_actions.pack(fill="x", pady=6)
        for text, command in (("加桩", self.add_locus),
                              ("改名", self.rename_locus),
                              ("上移", lambda: self.move_locus(-1)),
                              ("下移", lambda: self.move_locus(1)),
                              ("删除", self.delete_locus)):
            create_flat_action_button(locus_actions, text, command).pack(
                side="left", padx=2)

        right = tk.Frame(split, bg=self.palette.bg)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        head = tk.Frame(right, bg=self.palette.bg)
        head.pack(fill="x")
        create_ttk_section_header(head, "这个桩上的记忆项").pack(side="left")
        create_flat_action_button(head, "走一遍本宫殿",
                                  self.walk_current_palace).pack(side="right")
        self.locus_item_tree = self._make_item_tree(right, compact=True)

    # ---- 视图 3：记忆项库 ---------------------------------------------
    def _build_library_view(self, parent):
        filters = tk.Frame(parent, bg=self.palette.bg)
        filters.pack(fill="x", pady=(12, 4))
        tk.Label(filters, text="掌握度", bg=self.palette.bg,
                 fg=self.palette.text_muted,
                 font=self.typography.caption).pack(side="left")
        self.mastery_box = ttk.Combobox(
            filters, textvariable=self.mastery_var,
            values=[label for _v, label in MASTERY_FILTER_CHOICES],
            state="readonly", width=12)
        self.mastery_box.pack(side="left", padx=(4, 12))
        self.mastery_box.bind("<<ComboboxSelected>>",
                              lambda _e: self._reload_library())
        tk.Label(filters, text="分类", bg=self.palette.bg,
                 fg=self.palette.text_muted,
                 font=self.typography.caption).pack(side="left")
        self.category_box = ttk.Combobox(filters, textvariable=self.category_var,
                                         values=["全部分类"], state="readonly", width=16)
        self.category_box.pack(side="left", padx=(4, 12))
        self.category_box.bind("<<ComboboxSelected>>",
                               lambda _e: self._reload_library())
        ttk.Entry(filters, textvariable=self.search_var, width=22).pack(side="left")
        create_flat_action_button(filters, "搜索", self._reload_library).pack(
            side="left", padx=6)
        create_flat_action_button(filters, "重置", self.reset_filters).pack(side="left")

        self.library_tree = self._make_item_tree(parent, with_palace=True)

    # ---- 视图 4：联想法则 ---------------------------------------------
    def _build_methods_view(self, parent):
        split = tk.Frame(parent, bg=self.palette.bg)
        split.pack(fill="both", expand=True, pady=(12, 0))
        left = tk.Frame(split, bg=self.palette.bg, width=260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        create_ttk_section_header(left, "教学卡").pack(anchor="w")
        self.card_tree = ttk.Treeview(left, columns=("cat",), show="tree headings",
                                      height=18, selectmode="browse")
        self.card_tree.heading("#0", text="卡片", anchor="w")
        self.card_tree.heading("cat", text="类", anchor="e")
        self.card_tree.column("#0", width=200, anchor="w")
        self.card_tree.column("cat", width=48, anchor="e", stretch=False)
        self.card_tree.pack(fill="both", expand=True)
        self.card_tree.bind("<<TreeviewSelect>>", self._on_card_select)

        right = tk.Frame(split, bg=self.palette.bg)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        # 教学卡正文用 tk.Text 本体滚动即可，不必再套一层 ScrollArea
        # （套两层滚动条是纯多余，还得处理两个 canvas 的宽度同步）
        self.card_body = tk.Text(right, wrap="word", height=24,
                                 relief="flat", bd=0, bg=self.palette.bg,
                                 highlightthickness=0, padx=2, pady=2)
        self.card_body.pack(fill="both", expand=True)
        self.card_body.configure(state="disabled")

    # ---- 视图 5：题库训练 ---------------------------------------------
    def _build_banks_view(self, parent):
        split = tk.Frame(parent, bg=self.palette.bg)
        split.pack(fill="both", expand=True, pady=(12, 0))
        left = tk.Frame(split, bg=self.palette.bg, width=260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        create_ttk_section_header(left, "题库").pack(anchor="w")
        self.bank_tree = ttk.Treeview(left, columns=("count",), show="tree headings",
                                      height=18, selectmode="browse")
        self.bank_tree.heading("#0", text="题库", anchor="w")
        self.bank_tree.heading("count", text="条", anchor="e")
        self.bank_tree.column("#0", width=190, anchor="w")
        self.bank_tree.column("count", width=40, anchor="e", stretch=False)
        self.bank_tree.pack(fill="both", expand=True)
        self.bank_tree.bind("<<TreeviewSelect>>", self._on_bank_select)

        right = tk.Frame(split, bg=self.palette.bg)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        head = tk.Frame(right, bg=self.palette.bg)
        head.pack(fill="x")
        self.bank_desc_var = tk.StringVar(value="选一个题库看看内容。")
        tk.Label(head, textvariable=self.bank_desc_var, bg=self.palette.bg,
                 fg=self.palette.text_muted, font=self.typography.caption,
                 wraplength=520, justify="left").pack(side="left", anchor="w")
        create_flat_action_button(head, "导入到宫殿…",
                                  self.import_selected_bank).pack(side="right")
        create_flat_action_button(head, "看详情",
                                  self.open_selected_bank_item).pack(side="right", padx=6)
        self.bank_item_hint_var = tk.StringVar(
            value="双击某一条看完整内容（答案 / 位置与四周）—— 表格装不下那两段字，"
                  "打开的窗口里还能贴自己在游戏里截的图。")
        tk.Label(right, textvariable=self.bank_item_hint_var, bg=self.palette.bg,
                 fg=self.palette.text_muted, font=self.typography.caption,
                 wraplength=560, justify="left").pack(anchor="w", pady=(8, 0))
        self.bank_item_tree = ttk.Treeview(right, columns=("seq", "q", "a", "extra"),
                                           show="headings", height=16,
                                           selectmode="browse")
        for key, text, width in (("seq", "序", 44), ("q", "题目", 236),
                                 ("a", "答案", 200), ("extra", "资料", 92)):
            self.bank_item_tree.heading(key, text=text, anchor="w")
            self.bank_item_tree.column(key, width=width, anchor="w")
        self.bank_item_tree.pack(fill="both", expand=True, pady=(6, 0))
        self.bank_item_tree.bind("<Double-1>", self._on_bank_item_open)

    # ---- 视图 6：打卡统计 ---------------------------------------------
    def _build_stats_view(self, parent):
        scroll = ScrollArea(parent, bg=self.palette.bg)
        scroll.pack(fill="both", expand=True, pady=(12, 0))
        host = scroll.inner

        cards = tk.Frame(host, bg=self.palette.bg)
        cards.pack(fill="x")
        create_metric_card(cards, "累计分钟", self.stats_minutes_var,
                           "30 天内累计练习时长。").pack(side="left", padx=(0, 10))
        create_metric_card(cards, "打卡天数", self.stats_days_var,
                           "30 天内打过卡的天数。").pack(side="left", padx=10)
        create_metric_card(cards, "正确率", self.stats_accuracy_var,
                           "30 天内复习「记得」的比例。").pack(side="left", padx=10)

        # 间隔重复算法是**全局训练设置**（不是某一项的属性），所以放在统计页
        create_ttk_section_header(host, "间隔重复算法").pack(
            anchor="w", pady=(16, 6))
        algo_bar = tk.Frame(host, bg=self.palette.bg)
        algo_bar.pack(anchor="w", fill="x")
        self.algorithm_var = tk.StringVar(value=tc.DEFAULT_ALGORITHM)
        self.algorithm_box = ttk.Combobox(
            algo_bar, textvariable=self.algorithm_var, state="readonly",
            values=[label for _key, label in tc.ALGORITHM_CHOICES], width=16)
        self.algorithm_box.pack(side="left")
        self.algorithm_box.bind("<<ComboboxSelected>>",
                                lambda _e: self._on_algorithm_change())
        self.algorithm_hint = tk.Label(
            algo_bar, text="", bg=self.palette.bg, fg=self.palette.text_muted,
            font=self.typography.caption, anchor="w")
        self.algorithm_hint.pack(side="left", padx=(10, 0))

        create_ttk_section_header(host, "打卡日历（按周一对齐）").pack(
            anchor="w", pady=(16, 6))
        self.calendar_host = tk.Frame(host, bg=self.palette.bg)
        self.calendar_host.pack(fill="x")

        create_ttk_section_header(host, "掌握度分布").pack(anchor="w", pady=(16, 6))
        self.mastery_host = tk.Frame(host, bg=self.palette.bg)
        self.mastery_host.pack(fill="x")

        create_ttk_section_header(host, "最近复习流水").pack(anchor="w", pady=(16, 6))
        self.review_tree = ttk.Treeview(host, columns=("date", "item", "feedback"),
                                        show="headings", height=8, selectmode="browse")
        for key, text, width in (("date", "日期", 100), ("item", "记忆项", 320),
                                 ("feedback", "自评", 80)):
            self.review_tree.heading(key, text=text, anchor="w")
            self.review_tree.column(key, width=width, anchor="w")
        self.review_tree.pack(fill="x")

    # -- 公共：记忆项表格 -----------------------------------------------
    def _make_item_tree(self, parent, *, compact=False, with_palace=False):
        columns = ("station", "front", "back", "mastery", "due")
        if with_palace:
            columns = ("palace",) + columns
        tree = ttk.Treeview(parent, columns=columns, show="headings",
                            height=10 if compact else 14, selectmode="browse")
        if with_palace:
            tree.heading("palace", text="宫殿", anchor="w")
            tree.column("palace", width=130, anchor="w")
        for key, text, width in (("station", "桩", 110), ("front", "要记的", 260),
                                 ("back", "答案", 220), ("mastery", "掌握度", 70),
                                 ("due", "到期", 90)):
            tree.heading(key, text=text, anchor="w")
            tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True, pady=(6, 0))
        tree.tag_configure("due", foreground="#a3372f")
        tree.bind("<<TreeviewSelect>>", self._on_item_select)
        tree.bind("<Double-1>", lambda _e: self.edit_item())
        return tree

    # ==================================================================
    # 视图切换与刷新
    # ==================================================================
    def show_view(self, key: str):
        if key not in self.views:
            return
        for frame in self.views.values():
            frame.pack_forget()
        self.views[key].pack(fill="both", expand=True, pady=(10, 0))
        self.view_key = key
        self.title_var.set(VIEW_LABELS.get(key, key))
        self.refresh()

    def refresh(self):
        """整页刷新：左栏 + 当前视图。"""
        self._reload_nav()
        self._reload_today_metrics()
        if self.view_key == VIEW_TODAY:
            self._reload_today()
        elif self.view_key == VIEW_WORKBENCH:
            self._reload_workbench()
        elif self.view_key == VIEW_LIBRARY:
            self._reload_library()
        elif self.view_key == VIEW_METHODS:
            self._reload_methods()
        elif self.view_key == VIEW_BANKS:
            self._reload_banks()
        elif self.view_key == VIEW_STATS:
            self._reload_stats()
        self._refresh_meta()

    def _refresh_meta(self):
        palaces = self.db.list_palaces()
        items = self.db.count_items()
        self.meta_var.set(f"{len(palaces)} 座宫殿 · {items} 条记忆项 · "
                          f"今日待复习 {self.db.due_count()}")

    # -- 左栏 -----------------------------------------------------------
    def _reload_nav(self):
        tree = self.nav_tree
        selected = self.current_palace_id
        palaces = self.db.list_palaces()
        # 第一道闸：内容没变就别重建。``tree.delete()`` 会把选中项一起清掉，
        # 于是每轮刷新都得重设一次选中 —— 而 Tk 的 ``selection_set`` 是**无条件**
        # 投递 ``<<TreeviewSelect>>`` 的，事件回来又触发刷新，能自激成死循环
        # （实测：切到「记忆项库」后整个窗口卡死，faulthandler 栈停在
        # _on_nav_select -> refresh -> _reload_nav 上）。
        signature = [(p["id"], p["name"], p["item_count"]) for p in palaces]
        if signature != self._nav_signature:
            self._nav_signature = signature
            tree.delete(*tree.get_children())
            for key, label in VIEW_CHOICES:
                tree.insert("", "end", iid=f"{TREE_VIEW}:{key}", text=f"  {label}",
                            values=("",))
            for palace in palaces:
                tree.insert(
                    "", "end", iid=f"{TREE_PALACE}:{palace['id']}",
                    text=f"  {palace['name']}",
                    values=(palace["item_count"],))
        # 第二道闸：目标节点不存在就不要设选中（«撞空»，<<TreeviewSelect>> 下一轮
        # 才投递，布尔守卫拦不住延迟事件）；已选中同一项则一个字都别写。
        if selected is not None:
            self._select_only(tree, f"{TREE_PALACE}:{selected}")
        elif not tree.selection():
            # 第三道闸（首屏）：一座宫殿都没选时导航里一个选中项都没有，而
            # ``show_view()`` 是**唯一**会 pack 视图帧的地方 —— 于是右栏会一直
            # 空着（数据都读好了，只是那块帧没装上）。把选中指到当前视图节点，
            # 那条延迟投递的 ``<<TreeviewSelect>>`` 正好替我们 pack 一次；
            # 顺带让左栏高亮与 ``view_key`` 恒等。只在「一个选中都没有」时动手，
            # 绝不改写已有选区。
            self._select_only(tree, f"{TREE_VIEW}:{self.view_key}")

    def _on_nav_select(self, _event=None):
        selection = self.nav_tree.selection()
        if not selection:
            return
        iid = selection[0]
        kind, _, value = iid.partition(":")
        if kind == TREE_VIEW:
            self.current_palace_id = None
            self.show_view(value)
            return
        self.current_palace_id = int(value)
        self.current_locus_id = None
        if self.view_key not in (VIEW_WORKBENCH, VIEW_LIBRARY):
            self.show_view(VIEW_WORKBENCH)
        else:
            self.refresh()

    # -- 视图 1 ---------------------------------------------------------
    def _reload_today_metrics(self):
        stats = self.db.stats()
        self.today_due_var.set(str(stats["due"]))
        self.today_new_var.set(str(memory_db_suggest(stats["due"])))
        self.today_streak_var.set(str(stats["streak"]))

    def _reload_today(self):
        rows = self.db.due_items()
        self._fill_item_tree(self.today_tree, rows[:200], with_palace=False)

    # -- 视图 2 ---------------------------------------------------------
    def _reload_workbench(self):
        tree = self.locus_tree
        tree.delete(*tree.get_children())
        palace_id = self.current_palace_id
        if palace_id is None:
            palaces = self.db.list_palaces()
            palace_id = int(palaces[0]["id"]) if palaces else None
            self.current_palace_id = palace_id
        if palace_id is None:
            self.locus_item_tree.delete(*self.locus_item_tree.get_children())
            return
        counts = self.db.item_counts_by_locus(palace_id)
        for locus in self.db.list_loci(palace_id):
            tree.insert("", "end", iid=f"locus:{locus['id']}",
                        text=f"  {locus['name']}",
                        values=(int(locus["seq"]) + 1,
                                counts.get(int(locus["id"]), 0)))
        if self.current_locus_id is not None:
            self._select_only(tree, f"locus:{self.current_locus_id}")
        self._reload_locus_items()

    def _on_locus_select(self, _event=None):
        selection = self.locus_tree.selection()
        if not selection:
            return
        self.current_locus_id = int(selection[0].split(":")[1])
        self._reload_locus_items()

    def _reload_locus_items(self):
        palace_id = self.current_palace_id
        locus_id = self.current_locus_id
        if palace_id is None or locus_id is None:
            self.locus_item_tree.delete(*self.locus_item_tree.get_children())
            return
        rows = self.db.list_items(palace_id=palace_id, locus_id=locus_id)
        self._fill_item_tree(self.locus_item_tree, rows, with_palace=False)

    # -- 视图 3 ---------------------------------------------------------
    def _reload_library(self):
        self.category_box.configure(
            values=["全部分类"] + self.db.categories())
        mastery_label_value = self.mastery_var.get()
        mastery = None
        for value, label in MASTERY_FILTER_CHOICES:
            if label == mastery_label_value and value != "all":
                mastery = int(value)
        category = self.category_var.get()
        rows = self.db.list_items(
            mastery=mastery,
            category=None if category in ("", "全部分类") else category,
            keyword=self.search_var.get())
        self._fill_item_tree(self.library_tree, rows, with_palace=True)

    def reset_filters(self):
        self.search_var.set("")
        self.mastery_var.set(MASTERY_FILTER_CHOICES[0][1])
        self.category_var.set("全部分类")
        self._reload_library()

    # -- 视图 4 ---------------------------------------------------------
    def _reload_methods(self):
        tree = self.card_tree
        tree.delete(*tree.get_children())
        for card in self.db.list_cards():
            tree.insert("", "end", iid=f"card:{card['code']}",
                        text=f"  {card['title']}", values=(card["category"],))
        if self.selected_card_code is None:
            codes = [c["code"] for c in self.db.list_cards()]
            self.selected_card_code = codes[0] if codes else None
        if self.selected_card_code:
            self._select_only(tree, f"card:{self.selected_card_code}")
        self._render_card()

    def _on_card_select(self, _event=None):
        selection = self.card_tree.selection()
        if not selection:
            return
        self.selected_card_code = selection[0].split(":", 1)[1]
        self._render_card()

    def _render_card(self):
        widget = self.card_body
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        card = self.db.get_card(self.selected_card_code) if self.selected_card_code else None
        if not card:
            widget.insert("1.0", "选一张左边的教学卡。")
        else:
            text = f"# {card['title']}\n\n{card['body']}\n\n---\n\n**练一下**：{card['practice']}\n\n**口诀**：{card['tip']}\n"
            if self.markdown is not None:
                try:
                    self.markdown.render(widget, text, empty_hint="")
                except Exception:  # noqa: BLE001 - 渲染失败不该让整页打不开
                    widget.configure(state="normal")
                    widget.delete("1.0", "end")
                    widget.insert("1.0", text)
            else:
                widget.insert("1.0", text)
        widget.configure(state="disabled")

    # -- 视图 5 ---------------------------------------------------------
    def _reload_banks(self):
        tree = self.bank_tree
        tree.delete(*tree.get_children())
        for bank in self.db.list_banks():
            tree.insert("", "end", iid=f"bank:{bank['id']}",
                        text=f"  {bank['name']}", values=(bank["item_count"],))
        if self.selected_bank_id is None:
            banks = self.db.list_banks()
            self.selected_bank_id = int(banks[0]["id"]) if banks else None
        if self.selected_bank_id is not None:
            self._select_only(tree, f"bank:{self.selected_bank_id}")
        self._reload_bank_items()

    def _on_bank_select(self, _event=None):
        selection = self.bank_tree.selection()
        if not selection:
            return
        self.selected_bank_id = int(selection[0].split(":")[1])
        self._reload_bank_items()

    @staticmethod
    def _media_label(entry) -> str:
        """列表里只提示「有没有更多内容」，正文留给双击后的弹窗。"""
        has_place = bool(str(entry.get("detail") or "").strip())
        has_image = bool(str(entry.get("images") or "").strip())
        if has_place and has_image:
            return "位置 · 图"
        if has_place:
            return "位置"
        if has_image:
            return "图"
        return "—"

    def _reload_bank_items(self):
        tree = self.bank_item_tree
        tree.delete(*tree.get_children())
        if self.selected_bank_id is None:
            self.bank_desc_var.set("选一个题库看看内容。")
            return
        bank = self.db.get_bank(self.selected_bank_id)
        if bank:
            self.bank_desc_var.set(str(bank["description"]))
        for entry in self.db.list_bank_items(self.selected_bank_id):
            tree.insert("", "end", iid=f"bitem:{entry['id']}",
                        values=(entry["seq"], entry["question"], entry["answer"],
                                self._media_label(entry)))

    def open_selected_bank_item(self):
        """「看详情」按钮：与双击同一个动作，方便用键盘的人。"""
        if not self.bank_item_tree.selection():
            messagebox.showinfo(self.app_title,
                                "先在右边选一条，或者直接双击它。", parent=self)
            return
        self._on_bank_item_open()

    def _on_bank_item_open(self, _event=None):
        """双击题库某一条 → 打开完整内容（题目 / 答案 / 位置与四周 / 实景图）。"""
        selection = self.bank_item_tree.selection()
        if not selection:
            return "break"
        try:
            item_id = int(str(selection[0]).split(":")[1])
        except (IndexError, ValueError):
            return "break"
        item = self.db.get_bank_item(item_id)
        if not item:
            return "break"
        BankItemDialog(self, app_title=self.app_title, item=item,
                       images=self.images, image_preview_cls=self.image_preview_cls,
                       on_save=self._save_bank_item)
        return "break"

    def _save_bank_item(self, item_id, detail, images) -> bool:
        """只写用户自己的两栏（位置笔记 / 截图）—— 题干答案由种子决定。"""
        if not self.db.update_bank_item(item_id, detail=detail, images=images):
            return False
        self._reload_bank_items()
        self._status("已保存这一条的位置笔记与截图。")
        return True

    # -- 视图 6 ---------------------------------------------------------
    # -- 间隔重复算法（全局训练设置） ----------------------------------
    def _sync_algorithm(self):
        """把库里的算法选择同步进下拉框。"""
        key = self.db.get_algorithm()
        self.algorithm_var.set(tc.algorithm_label(key))
        self.algorithm_hint.config(text=tc.ALGORITHM_HINTS.get(key, ""))

    def _on_algorithm_change(self):
        """切换间隔重复算法。**只改设置**：已经养出来的参数原样留着。"""
        key = tc.ALGORITHM_BY_LABEL.get(self.algorithm_var.get().strip())
        if not key:
            # 下拉框里出现了不认识的值：按「什么都没选」处理，别把空串写进库
            self._sync_algorithm()
            return
        self.db.set_algorithm(key)
        self.algorithm_hint.config(text=tc.ALGORITHM_HINTS.get(key, ""))

    def _reload_stats(self):
        self._sync_algorithm()
        stats = self.db.stats()
        self.stats_minutes_var.set(str(stats["minutes"]))
        self.stats_days_var.set(str(stats["days"]))
        self.stats_accuracy_var.set(
            tc.accuracy_percent(stats["reviewed"], stats["correct"]))

        for child in self.calendar_host.winfo_children():
            child.destroy()
        palette = self.palette
        header = tk.Frame(self.calendar_host, bg=palette.bg)
        header.pack(anchor="w")
        tk.Label(header, text="", width=6, bg=palette.bg).pack(side="left")
        for label in tc.weekday_headers():
            tk.Label(header, text=label, width=4, bg=palette.bg,
                     fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")
        for row in tc.checkin_grid(self.db.checkin_dates()):
            line = tk.Frame(self.calendar_host, bg=palette.bg)
            line.pack(anchor="w")
            tk.Label(line, text=row["label"], width=6, bg=palette.bg,
                     fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")
            for cell in row["cells"]:
                fill = tc.CHECKIN_FILL if cell["checked"] else palette.bg
                text = "·" if cell["is_future"] else str(cell["date"].day)
                label = tk.Label(line, text=text, width=4, bg=fill,
                                 fg=palette.text_primary,
                                 font=self.typography.caption,
                                 relief="solid" if cell["is_today"] else "flat",
                                 bd=1 if cell["is_today"] else 0)
                label.pack(side="left", padx=1, pady=1)

        for child in self.mastery_host.winfo_children():
            child.destroy()
        distribution = self.db.mastery_distribution()
        total = max(1, sum(distribution.values()))
        for value, text in tc.MASTERY_CHOICES:
            count = int(distribution.get(value, 0))
            line = tk.Frame(self.mastery_host, bg=palette.bg)
            line.pack(fill="x", pady=1)
            tk.Label(line, text=f"{text}", width=6, anchor="w", bg=palette.bg,
                     fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")
            bar = tk.Frame(line, bg=tc.mastery_color(value),
                           width=int(260 * count / total), height=12)
            bar.pack(side="left")
            tk.Label(line, text=f" {count}", bg=palette.bg, fg=palette.text_muted,
                     font=self.typography.caption).pack(side="left")

        self.review_tree.delete(*self.review_tree.get_children())
        for row in self.db.list_reviews(limit=50):
            item = self.db.get_item(row["item_id"]) or {}
            self.review_tree.insert(
                "", "end",
                values=(row["review_date"], item.get("front", ""),
                        tc.feedback_label(row["feedback"])))

    # -- 公共填充 -------------------------------------------------------
    def _select_only(self, tree, iid) -> bool:
        """只在「选中项确实不同」时才写 selection，返回是否真的写了。

        踩过的坑：Tk 的 ``tree.selection_set()`` 是**无条件**投递
        ``<<TreeviewSelect>>`` 的（并不是文档暗示的「选择变化才发」），
        而 ``tree.delete()`` 又会把选中项一并清掉。于是
        「刷新 -> 重设选中 -> 事件 -> 再刷新」可以自激成死循环。

        判据必须是**把当前选区读回来比较**；围着 selection_set 设布尔守卫
        拦不住 —— ``<<TreeviewSelect>>`` 要等下一轮事件循环才投递，事件到达时
        守卫早已复位。
        """
        if iid is None or iid not in tree.get_children():
            return False
        if tuple(tree.selection()) == (iid,):
            return False
        tree.selection_set(iid)
        return True

    def _fill_item_tree(self, tree, rows, *, with_palace=False):
        tree.delete(*tree.get_children())
        for item in rows:
            # list_items 不带 station（那是 walk_order 才有的），序号要从 locus_seq 推
            locus_seq = int(item.get("locus_seq", -1) or -1)
            station = locus_seq + 1 if locus_seq >= 0 else 0
            locus = str(item.get("locus_name") or "")
            station_text = f"{station}. {locus}" if station else (locus or "（未分配）")
            due_text = tc.due_bucket(item.get("next_review_at"), None)
            due_text = {"new": "未学", "due": "今天", "future": str(
                item.get("next_review_at") or "")}[due_text]
            values = [station_text, item.get("front", ""), item.get("back", ""),
                      tc.mastery_label(item.get("mastery"))]
            if with_palace:
                values = [item.get("palace_name", "")] + values
            values.append(due_text)
            tags = ("due",) if item.get("due") else ()
            tree.insert("", "end", iid=f"item:{item['id']}", values=tuple(values),
                        tags=tags)

    def _on_item_select(self, event=None):
        tree = event.widget if event is not None else None
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            return
        self.selected_item_id = int(selection[0].split(":")[1])

    # ==================================================================
    # 动作
    # ==================================================================
    def _status(self, text: str) -> None:
        self.status_var.set(text)
        if self.on_status is not None:
            try:
                self.on_status(text)
            except Exception:  # noqa: BLE001
                pass

    # -- 宫殿 -----------------------------------------------------------
    def add_palace(self):
        dialog = PalaceDialog(self, "新建宫殿", app_title=self.app_title)
        if not dialog.result:
            return
        palace_id = self.db.add_palace(**dialog.result)
        self.current_palace_id = palace_id
        self.show_view(VIEW_WORKBENCH)
        self._status(f"已新建宫殿「{dialog.result['name']}」，接着把地点桩加进去。")

    def import_templates(self):
        ids = self.db.import_all_templates()
        self._status(f"内置宫殿模板已就绪（共 {len(ids)} 座，重复导入不会重复建）。")
        self.refresh()

    def import_pegs(self):
        palace_id = self.db.import_number_pegs()
        self.current_palace_id = palace_id
        self._status("100 个数字桩已导入。建议先背熟 00–19，再往下加。")
        self.show_view(VIEW_WORKBENCH)

    # -- 地点桩 ---------------------------------------------------------
    def _require_palace(self):
        if self.current_palace_id is None:
            messagebox.showinfo(self.app_title,
                                "先在左栏选一座宫殿（没有的话点「导入内置宫殿模板」）。",
                                parent=self)
            return None
        return self.current_palace_id

    def add_locus(self):
        palace_id = self._require_palace()
        if palace_id is None:
            return
        name = simpledialog.askstring("加桩", "地点桩的名字（如「鞋柜」「第三个红绿灯」）：",
                                      parent=self)
        if not name:
            return
        hint = simpledialog.askstring("加桩", "提示语（可留空，走一遍时会显示）：",
                                      parent=self) or ""
        locus_id = self.db.add_locus(palace_id, name, hint=hint)
        self.current_locus_id = locus_id
        self._reload_workbench()
        self._status(f"已加桩「{name}」。")

    def rename_locus(self):
        if self.current_locus_id is None:
            messagebox.showinfo(self.app_title, "先在左边选一个桩。", parent=self)
            return
        locus = self.db.get_locus(self.current_locus_id)
        if not locus:
            return
        name = simpledialog.askstring("改桩名", "新名字：", initialvalue=locus["name"],
                                      parent=self)
        if not name:
            return
        hint = simpledialog.askstring("改提示", "提示语（可留空）：",
                                      initialvalue=locus["hint"], parent=self)
        self.db.update_locus(self.current_locus_id, name=name, hint=hint or "")
        self._reload_workbench()

    def move_locus(self, delta):
        if self.current_locus_id is None:
            return
        if self.db.move_locus(self.current_locus_id, delta):
            self._reload_workbench()
            self._status("走一遍的顺序是地点桩的顺序 —— 顺序变了，画面串也跟着变。")

    def delete_locus(self):
        if self.current_locus_id is None:
            return
        locus = self.db.get_locus(self.current_locus_id)
        if not locus:
            return
        if not messagebox.askyesno(
                self.app_title,
                f"删除桩「{locus['name']}」？\n\n"
                "桩上的记忆项**不会丢**，会变成「未归档」，可以再挂到别的桩上。",
                parent=self):
            return
        self.db.delete_locus(self.current_locus_id)
        self.current_locus_id = None
        self._reload_workbench()

    # -- 记忆项 ---------------------------------------------------------
    def add_item(self):
        dialog = ItemDialog(self, "新建记忆项", app_title=self.app_title,
                            palaces=self.db.list_palaces(),
                            loci=self._all_loci(),
                            initial={"palace_id": self.current_palace_id or 0},
                            default_locus_id=self.current_locus_id or 0,
                            images=self.images,
                            image_preview_cls=self.image_preview_cls)
        if not dialog.result:
            return
        self.db.add_item(**dialog.result)
        self.refresh()
        self._status("已加入。**别省联想画面** —— 那一步才是练的部分。")

    def edit_item(self):
        if self.selected_item_id is None:
            return
        item = self.db.get_item(self.selected_item_id)
        if not item:
            return
        dialog = ItemDialog(self, "编辑记忆项", app_title=self.app_title,
                            palaces=self.db.list_palaces(),
                            loci=self._all_loci(), initial=item,
                            images=self.images,
                            image_preview_cls=self.image_preview_cls)
        if not dialog.result:
            return
        self.db.update_item(self.selected_item_id, **dialog.result)
        self.refresh()

    def _all_loci(self):
        loci: list[dict] = []
        for palace in self.db.list_palaces():
            loci.extend(self.db.list_loci(palace["id"]))
        return loci

    # -- 走一遍 ---------------------------------------------------------
    def walk_current_palace(self):
        palace_id = self._require_palace()
        if palace_id is None:
            return
        items = self.db.walk_order(palace_id)
        if not items:
            messagebox.showinfo(self.app_title,
                                "这座宫殿还没有挂记忆项。加几条再走。", parent=self)
            return
        self._open_walk(items)

    def start_today_training(self):
        items = self.db.due_items(limit=None)
        if not items:
            self._status("今天没有到期的内容。可以去「题库训练」导一包新的。")
            messagebox.showinfo(self.app_title,
                                "今天没有该复习的，也没有没学过的 —— 干净。\n"
                                "想多练就去「题库训练」导一个题库。", parent=self)
            return
        self._open_walk(items)

    def _open_walk(self, items):
        if self.walk_window is not None and self.walk_window.winfo_exists():
            self.walk_window.lift()
            return
        self.walk_window = WalkSession(
            self, items, app_title=self.app_title, title="走一遍 · 记忆宫殿",
            palette=self.palette, typography=self.typography, images=self.images,
            on_grade=self._grade_item, on_finish=self._finish_walk,
            on_close=lambda _summary: self._after_walk_closed())

    def _grade_item(self, item, feedback):
        """写回 SRS。**每次自评恰好一行流水**。"""
        item_id = item.get("id")
        if item_id is None:
            return
        self.db.record_review(int(item_id), feedback)

    def _finish_walk(self, summary):
        self._status(
            f"本轮：走了 {summary['reviewed']} 站，记得 {summary['correct']} 条，"
            f"正确率 {tc.accuracy_percent(summary['reviewed'], summary['correct'])}。")

    def _after_walk_closed(self):
        self.walk_window = None
        self.db.autofill_today()
        self.refresh()

    # -- 题库 -----------------------------------------------------------
    def import_selected_bank(self):
        if self.selected_bank_id is None:
            messagebox.showinfo(self.app_title, "先在左边选一个题库。", parent=self)
            return
        bank = self.db.get_bank(self.selected_bank_id)
        if not bank:
            return
        palaces = self.db.list_palaces()
        if not palaces:
            messagebox.showinfo(self.app_title,
                                "还没有宫殿。先点「导入内置宫殿模板」。", parent=self)
            return
        names = [p["name"] for p in palaces]
        choice = simpledialog.askstring(
            "导入到宫殿",
            f"把「{bank['name']}」导入到哪座宫殿？\n\n可选：{'、'.join(names)}\n"
            "（留空 = 只入库，不挂桩）", parent=self)
        palace_id = 0
        if choice and choice.strip():
            for palace in palaces:
                if palace["name"] == choice.strip():
                    palace_id = int(palace["id"])
                    break
            else:
                messagebox.showinfo(self.app_title, f"没找到叫「{choice}」的宫殿。",
                                    parent=self)
                return
        result = self.db.import_bank(bank["code"], palace_id)
        self._status(f"「{bank['name']}」：新增 {result['created']} 条，"
                     f"已存在 {result['skipped']} 条（重复导入不会重复挂）。")
        self.refresh()

    # -- 打卡与待办 -----------------------------------------------------
    def checkin_today(self):
        record = self.db.autofill_today()
        minutes = simpledialog.askstring(
            "打卡", f"今天练了多少分钟？（复习 {record['items_reviewed']} 条）",
            initialvalue=str(record["minutes"] or 20), parent=self)
        if minutes is not None:
            try:
                record = self.db.checkin(minutes=int(minutes or 0))
            except ValueError:
                messagebox.showwarning(self.app_title, "分钟数要填数字。", parent=self)
                return
        self._status(f"已打卡：{record['items_reviewed']} 条复习、"
                     f"{record['items_new']} 条新学。")
        self.refresh()

    def make_today_todo(self):
        if self.todo_hook is None:
            messagebox.showinfo(self.app_title, "待办联动没有接上。", parent=self)
            return
        due = self.db.due_count()
        suggested = memory_db_suggest(due)
        title, message = self.todo_hook(due=due, suggested=suggested)
        self._status(message or f"已生成今日训练待办：{title}")

    # -- 导出 -----------------------------------------------------------
    def export_items_markdown(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="导出记忆项", defaultextension=".md",
            initialfile="记忆宫殿导出.md",
            filetypes=[("Markdown", "*.md"), ("所有文件", "*.*")])
        if not path:
            return
        lines = ["# 记忆宫殿导出", ""]
        for palace in self.db.list_palaces():
            lines.append(f"## {palace['name']}")
            lines.append("")
            if palace.get("route_note"):
                lines.append(f"> {palace['route_note']}")
                lines.append("")
            for item in self.db.list_items(palace_id=palace["id"]):
                station = int(item.get("locus_seq", -1)) + 1
                locus = item.get("locus_name") or "（未分配）"
                lines.append(f"- **第 {station} 站 · {locus}**：{item['front']}")
                if item.get("back"):
                    lines.append(f"  - 答案：{item['back']}")
                if item.get("imagery"):
                    lines.append(f"  - 联想：{item['imagery']}")
                if item.get("story"):
                    lines.append(f"  - 故事：{item['story']}")
            lines.append("")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        self._status(f"已导出到 {path}")


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def memory_db_suggest(due_total) -> int:
    """今天建议新学几条（由待复习量反推）。"""
    return memory_db.suggest_new_count(due_total=due_total)
