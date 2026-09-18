# -*- coding: utf-8 -*-
"""后台首页页面类。"""

import tkinter as tk
from tkinter import ttk

from page_components import GUTTER
from ui_components import (
    create_flat_action_button,
    create_info_label,
    create_metric_card,
    create_section_frame,
)
from ui_theme import MAIN_PALETTE, TYPOGRAPHY


COLOR_BG = MAIN_PALETTE.bg
COLOR_MUTED = MAIN_PALETTE.text_muted
COLOR_TEXT = MAIN_PALETTE.text_secondary
COLOR_LINK = MAIN_PALETTE.link
COLOR_BADGE_BG = MAIN_PALETTE.badge_bg
FONT_BADGE = TYPOGRAPHY.badge


class BackendPage:
    def __init__(self, app, container, *, backend_feature_items):
        self.app = app
        self.container = container
        self.backend_feature_items = backend_feature_items

    def build(self):
        self.app.backend_page = tk.Frame(self.container, bg=COLOR_BG)

        backend_top = tk.Frame(self.app.backend_page, bg=COLOR_BG, padx=GUTTER, pady=10)
        backend_top.pack(fill="x")
        for button_text, button_command in [
            ("刷新概览", self.app.refresh_backend_tools_page),
            ("打开接口测试", lambda: self.app.open_backend_feature("api_demo")),
            ("打开登录检测", lambda: self.app.open_backend_feature("login_checker")),
            ("打开行情查询", lambda: self.app.open_backend_feature("market_quote")),
            ("关闭全部功能窗口", self.app.close_all_backend_windows),
        ]:
            create_flat_action_button(backend_top, button_text, button_command, side="left")
        create_flat_action_button(backend_top, "清除已记住账号", self.app.clear_backend_login_memory, side="right")

        self.app.backend_summary_var = tk.StringVar(
            value="已内嵌 adminDemo 的 4 个核心能力，可直接在当前系统内完成登录检测、接口调试、加解密与行情查询。"
        )
        create_info_label(
            self.app.backend_page,
            textvariable=self.app.backend_summary_var,
            tone="muted",
            wraplength=920,
        ).pack(anchor="w", padx=GUTTER, pady=(0, 8))

        self.app.backend_status_var = tk.StringVar(
            value="当前已内嵌 4 个功能模块    正在打开 0 个窗口    默认环境：测试环境    功能来源：当前项目 embedded_admin_tools"
        )
        create_info_label(
            self.app.backend_page,
            textvariable=self.app.backend_status_var,
            tone="muted",
        ).pack(anchor="w", padx=GUTTER, pady=(0, 8))

        backend_strip = tk.Frame(self.app.backend_page, bg=COLOR_BG, padx=GUTTER, pady=4)
        backend_strip.pack(fill="x")
        for strip_index in range(3):
            backend_strip.columnconfigure(strip_index, weight=1)
        self.app.backend_strip_account_var = tk.StringVar(value="未设置 / 请点击功能卡片开始联调")
        self.app.backend_strip_environment_var = tk.StringVar(value="测试环境 / web")
        self.app.backend_strip_result_var = tk.StringVar(value="接口链路已验证，可直接进入会员接口与行情查询联调")
        strip_items = [
            ("常用账号", self.app.backend_strip_account_var),
            ("当前环境", self.app.backend_strip_environment_var),
            ("最近联调结果", self.app.backend_strip_result_var),
        ]
        for index, (title, value_var) in enumerate(strip_items):
            strip_card = create_section_frame(backend_strip, title)
            strip_card.grid(row=0, column=index, sticky="nsew", padx=4)
            create_info_label(strip_card, textvariable=value_var, tone="primary", wraplength=280).pack(anchor="w")

        backend_metrics = tk.Frame(self.app.backend_page, bg=COLOR_BG, padx=GUTTER, pady=4)
        backend_metrics.pack(fill="x")
        for metric_index in range(4):
            backend_metrics.columnconfigure(metric_index, weight=1)
        self.app.backend_metric_module_var = tk.StringVar(value="4")
        self.app.backend_metric_opened_var = tk.StringVar(value="0")
        self.app.backend_metric_verified_var = tk.StringVar(value="3")
        self.app.backend_metric_storage_var = tk.StringVar(value="Windows 本机加密")
        metric_items = [
            ("内嵌功能数", self.app.backend_metric_module_var, "当前后台已内嵌 4 个核心功能"),
            ("已打开窗口", self.app.backend_metric_opened_var, "可快速定位当前已打开的内部窗口"),
            ("已验证链路", self.app.backend_metric_verified_var, "登录、会员接口、行情查询均已实测"),
            ("账号存储", self.app.backend_metric_storage_var, "用于展示当前登录记忆的本机保存方式"),
        ]
        for index, (title, value_var, desc) in enumerate(metric_items):
            card = create_metric_card(backend_metrics, title, value_var, desc)
            card.grid(row=0, column=index, sticky="nsew", padx=4)

        backend_overview = create_section_frame(self.app.backend_page, "联调概览")
        backend_overview.pack(fill="x", padx=GUTTER, pady=(0, 12))
        self.app.backend_login_memory_var = tk.StringVar(value="")
        self.app.backend_memory_tip_var = tk.StringVar(value="")
        self.app.backend_verified_var = tk.StringVar(
            value="已验证：测试环境登录成功，供货会员接口、经济会员接口、行情查询接口均返回成功。"
        )
        self.app.backend_recommend_var = tk.StringVar(
            value="建议顺序：先打开供货会员与经济会员接口查看会员接口，再打开行情查询工具查看最新行情。"
        )
        create_info_label(
            backend_overview,
            textvariable=self.app.backend_login_memory_var,
            tone="link",
            wraplength=920,
        ).pack(anchor="w")
        create_info_label(
            backend_overview,
            textvariable=self.app.backend_memory_tip_var,
            tone="warn",
            wraplength=920,
        ).pack(anchor="w", pady=6)
        create_info_label(
            backend_overview,
            textvariable=self.app.backend_verified_var,
            tone="success",
            wraplength=920,
        ).pack(anchor="w", pady=6)
        create_info_label(
            backend_overview,
            textvariable=self.app.backend_recommend_var,
            tone="muted",
            wraplength=920,
        ).pack(anchor="w", pady=6)

        backend_recent = create_section_frame(self.app.backend_page, "最近记录")
        backend_recent.pack(fill="x", padx=GUTTER, pady=(0, 12))
        self.app.backend_recent_account_var = tk.StringVar(value="最近登录账号：无    会员类型：-    环境：-    最近写入：-")
        self.app.backend_recent_feature_var = tk.StringVar(value="最近打开功能：无    最近打开时间：-")
        self.app.backend_recent_action_var = tk.StringVar(value="最近联调动作：无    动作时间：-")
        create_info_label(
            backend_recent,
            textvariable=self.app.backend_recent_account_var,
            tone="link",
            wraplength=920,
        ).pack(anchor="w")
        create_info_label(
            backend_recent,
            textvariable=self.app.backend_recent_feature_var,
            tone="success",
            wraplength=920,
        ).pack(anchor="w", pady=6)
        create_info_label(
            backend_recent,
            textvariable=self.app.backend_recent_action_var,
            tone="muted",
            wraplength=920,
        ).pack(anchor="w", pady=6)

        backend_quick = create_section_frame(self.app.backend_page, "常用入口")
        backend_quick.pack(fill="x", padx=GUTTER, pady=(0, 12))
        quick_grid = tk.Frame(backend_quick, bg=COLOR_BG)
        quick_grid.pack(fill="x")
        for quick_index in range(3):
            quick_grid.columnconfigure(quick_index, weight=1)
        quick_items = [
            ("供货与经济会员接口", "直接进入主接口调试窗口，适合连续联调会员接口。", "api_demo"),
            ("登录检测", "优先验证账号、环境、登录接口是否可用。", "login_checker"),
            ("行情查询", "快速进入 commodity_data_query 行情查询窗口。", "market_quote"),
        ]
        for index, (title, desc, feature_key) in enumerate(quick_items):
            card = create_section_frame(quick_grid, title)
            card.grid(row=0, column=index, sticky="nsew", padx=4)
            create_info_label(card, text=desc, tone="muted", wraplength=250).pack(anchor="w")
            ttk.Button(
                card,
                text="立即打开",
                command=lambda target_key=feature_key: self.app.open_backend_feature(target_key),
            ).pack(anchor="w", pady=(10, 0))

        backend_cards = tk.Frame(self.app.backend_page, bg=COLOR_BG, padx=GUTTER, pady=0)
        backend_cards.pack(fill="both", expand=True)
        self.app.backend_tool_rows = {}
        for tool in self.backend_feature_items:
            card = ttk.LabelFrame(
                backend_cards, text=tool["title"], padding=(16, 14), style="Card.TLabelframe"
            )
            card.pack(fill="x", pady=6)
            summary_var = tk.StringVar(value=tool["summary"])
            ttk.Label(card, textvariable=summary_var, foreground=COLOR_TEXT, wraplength=880, justify="left").grid(
                row=0, column=0, columnspan=3, sticky="w"
            )
            detail_var = tk.StringVar(value="")
            ttk.Label(card, textvariable=detail_var, foreground=COLOR_MUTED, wraplength=860, justify="left").grid(
                row=1, column=0, columnspan=3, sticky="w", pady=(6, 0)
            )
            status_var = tk.StringVar(value="")
            status_badge_var = tk.StringVar(value="")
            status_badge = tk.Label(
                card,
                textvariable=status_badge_var,
                bg=COLOR_BADGE_BG,
                fg=COLOR_LINK,
                padx=10,
                pady=3,
                font=FONT_BADGE,
            )
            status_badge.grid(row=2, column=0, sticky="w", pady=(8, 0))
            ttk.Label(card, textvariable=status_var, foreground=COLOR_MUTED).grid(
                row=2,
                column=1,
                sticky="w",
                padx=(8, 0),
                pady=(8, 0),
            )
            recent_var = tk.StringVar(value="")
            ttk.Label(card, textvariable=recent_var, foreground=COLOR_MUTED).grid(
                row=3,
                column=0,
                columnspan=3,
                sticky="w",
                pady=(6, 0),
            )
            open_button = ttk.Button(
                card,
                text="打开功能",
                command=lambda feature_key=tool["key"]: self.app.open_backend_feature(feature_key),
            )
            open_button.grid(row=4, column=1, sticky="e", padx=6, pady=(10, 0))
            focus_button = ttk.Button(
                card,
                text="定位已打开窗口",
                command=lambda feature_key=tool["key"]: self.app.focus_backend_window(feature_key),
            )
            focus_button.grid(row=4, column=2, sticky="e", pady=(10, 0))
            card.grid_columnconfigure(0, weight=1)
            self.app.backend_tool_rows[tool["key"]] = {
                "detail_var": detail_var,
                "status_var": status_var,
                "status_badge_var": status_badge_var,
                "status_badge_widget": status_badge,
                "recent_var": recent_var,
                "open_button": open_button,
            }
