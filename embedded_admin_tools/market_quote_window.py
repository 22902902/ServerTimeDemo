import csv
import json
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .services.api_client import ApiClient
from .services.crypto_service import DESCryptoService
from .services.error_code_service import ErrorCodeService
from .services.icon_service import save_temp_icon
from .services.interface_service import InterfaceService
from .services.login_memory_service import LoginMemoryService
from ui_theme import ADMIN_TOOL_PALETTE, THEME

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None


ENVIRONMENT_LABEL_TO_KEY = {
    "测试环境": "test",
    "正式环境": "prod",
}

BG_APP = ADMIN_TOOL_PALETTE.bg
BG_SURFACE = ADMIN_TOOL_PALETTE.surface
BG_MUTED = ADMIN_TOOL_PALETTE.surface_alt
FG_PRIMARY = ADMIN_TOOL_PALETTE.text_primary
FG_SECONDARY = ADMIN_TOOL_PALETTE.text_secondary
FG_POSITIVE = "#c62828"
FG_NEGATIVE = "#1b7f46"
FG_NEUTRAL = ADMIN_TOOL_PALETTE.text_secondary
BORDER_COLOR = ADMIN_TOOL_PALETTE.border
ACCENT_DARK = ADMIN_TOOL_PALETTE.accent
ACCENT_DARK_HOVER = ADMIN_TOOL_PALETTE.accent_hover
BUTTON_LIGHT = ADMIN_TOOL_PALETTE.button_bg
BUTTON_LIGHT_HOVER = ADMIN_TOOL_PALETTE.button_hover

LOGIN_RESPONSE_DESCRIPTION = [
    "登录返回包说明：",
    "{",
    '  "name": "logon",',
    '  "RESULT": {',
    '    "RETCODE": "返回码，>=0 成功，其他为失败，错误描述在 MESSAGE 中",',
    '    "ARGS": "返回提示信息中的参数列表，使用 | 分割参数",',
    '    "SYI": "当前登录系统编号",',
    '    "JSI": "有权限的系统编号，多个用英文分号分隔，例如 201;301",',
    '    "FUT": "资金账户类型，0 主账户，1 附属账户",',
    '    "LT": "上次登录时间",',
    '    "LI": "上次登录 IP",',
    '    "CP": "是否需要修改密码，1 是，2 否",',
    '    "CFP": "是否需要修改资金密码，1 是，2 否",',
    '    "RST": "实名状态，0 未实名，1 审核中，2 已实名",',
    '    "I": "用户身份，0 客户，1 会员",',
    '    "N": "登录用户名称",',
    '    "NN": "昵称",',
    '    "ISNN": "是否设置过昵称，1 已设置，2 未设置",',
    '    "U": "登录用户ID",',
    '    "UT": "交易员类型，1 超级交易员，2 高级交易员，3 普通交易员",',
    '    "RK": "随机串",',
    '    "UPL": "用户头像图片地址",',
    '    "TR": "服务端登录过程中每个操作的耗时信息"',
    "  }",
    "}",
]

MARKET_INTERFACE = {
    "display_name": "交易界面行情信息查询",
    "name": "commodity_data_query",
    "method": "POST",
    "request_mode": "json",
    "description": "登录成功后，U 自动取登录返回的 U，SI 自动取登录返回的 RETCODE，COI 为空表示查询所有商品行情。",
    "response_description": [
        "交易界面行情信息查询返回包说明：",
        "{",
        '  "name": "commodity_data_query",',
        '  "RESULT": {',
        '    "RETCODE": "返回码>=0成功, 其他为失败，错误描述在MESSAGE",',
        '    "ARGS": "返回提示信息中的参数列表，| 分割参数",',
        '    "TTLREC": "总记录数"',
        "  },",
        '  "RESULTLIST": {',
        '    "REC": [',
        "      {",
        '        "COI": "商品统一代码",',
        '        "CON": "商品名称",',
        '        "HIGH": "最高",',
        '        "LOW": "最低",',
        '        "LAST": "最新",',
        '        "CHA": "涨跌(有正负)",',
        '        "BSL": [',
        "          {",
        '            "BS": {',
        '              "BQ": "买量",',
        '              "BP": "买价",',
        '              "SQ": "卖量",',
        '              "SP": "卖价"',
        "            }",
        "          }",
        "        ]",
        "      }",
        "    ]",
        "  }",
        "}",
    ],
    "fields": [
        {
            "name": "name",
            "label": "接口名",
            "description": "固定为行情信息查询接口标识。",
            "widget": "entry",
            "readonly": True,
            "default": "commodity_data_query",
        },
        {
            "name": "U",
            "label": "登录用户ID U",
            "description": "登录成功返回的 U，自动带入。",
            "widget": "entry",
            "readonly": True,
            "default": "{{login_user_u}}",
        },
        {
            "name": "COI",
            "label": "商品统一代码 COI",
            "description": "可为空；为空表示查询所有商品。",
            "widget": "entry",
            "default": "",
        },
        {
            "name": "SI",
            "label": "会话标识 SI",
            "description": "登录成功返回的 RETCODE，自动带入。",
            "widget": "entry",
            "readonly": True,
            "default": "{{login_retcode}}",
        },
    ],
    "params": {
        "name": "commodity_data_query",
        "U": "{{login_user_u}}",
        "COI": "",
        "SI": "{{login_retcode}}",
    },
}


class MarketQuoteToolWindow(tk.Toplevel):
    def __init__(self, master=None) -> None:
        super().__init__(master)
        self.title("行情查询工具")
        self.geometry("1320x900")
        self.minsize(1180, 780)
        self.configure(bg=BG_APP)

        self.crypto_service = DESCryptoService()
        self.error_code_service = ErrorCodeService()  # 内嵌，无需文件
        self.interface_service = InterfaceService()  # 内嵌，无需文件
        self.environments = self.interface_service.get_environments()
        self.default_environment_key = self.interface_service.get_default_environment_key()
        self.api_client = ApiClient(self.interface_service.get_endpoint(self.default_environment_key))
        self.login_interface = self.interface_service.get_login_interface()
        self.login_memory_service = LoginMemoryService()

        self.account_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.lt_var = tk.StringVar(value="web")
        self.environment_var = tk.StringVar(
            value=self.environments.get(self.default_environment_key, {}).get("label", "测试环境")
        )
        self.top_info_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="请先登录。")

        self.session_context: dict = {}
        self.current_field_vars: dict[str, tk.StringVar] = {}
        self.param_preview: ScrolledText | None = None
        self.request_viewer: ScrolledText | None = None
        self.response_viewer: ScrolledText | None = None
        self.description_viewer: ScrolledText | None = None
        self.form_frame: ttk.Frame | None = None
        self.latest_http_result: dict | None = None
        self.request_markdown = ""
        self.response_markdown = ""
        self.description_markdown = ""
        self.param_preview_markdown = ""
        self.auto_refresh_interval_var = tk.StringVar(value="5")
        self.auto_refresh_after_id = None
        self.auto_refresh_enabled = False
        self.last_refresh_at = ""
        self.refresh_failure_count = 0

        self.load_login_memory()
        self.configure_theme()
        self.apply_window_icon()
        self.protocol("WM_DELETE_WINDOW", self.handle_close)
        self.build_login_view()

    def configure_theme(self) -> None:
        self.option_add("*Font", "{Microsoft YaHei UI} 10")
        style = ttk.Style(self)
        THEME.apply_admin_ttk_theme(
            style,
            palette=ADMIN_TOOL_PALETTE,
            title_size=22,
            section_size=12,
            topbar_bg=ACCENT_DARK,
            include_notebook=True,
            include_status=True,
            include_app_label=False,
            include_app_muted=False,
            include_card_labelframe=True,
            include_card_frame=True,
        )

    def apply_window_icon(self) -> None:
        try:
            icon_path = save_temp_icon()
            self.iconbitmap(default=str(icon_path))
        except Exception:
            pass

    @staticmethod
    def style_text_widget(widget: ScrolledText, *, height: int) -> None:
        widget.configure(
            height=height,
            font=("Consolas", 10),
            bg=BG_MUTED,
            fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY,
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor="#bbbbbb",
            padx=10,
            pady=10,
            spacing1=2,
            spacing3=2,
        )
        MarketQuoteToolWindow.configure_markdown_tags(widget)

    @staticmethod
    def configure_markdown_tags(widget: ScrolledText) -> None:
        widget.tag_configure("md_h1", font=("Microsoft YaHei UI", 15, "bold"), spacing1=10, spacing3=6)
        widget.tag_configure("md_h2", font=("Microsoft YaHei UI", 13, "bold"), spacing1=8, spacing3=4)
        widget.tag_configure("md_h3", font=("Microsoft YaHei UI", 11, "bold"), spacing1=6, spacing3=3)
        widget.tag_configure("md_body", font=("Microsoft YaHei UI", 10), spacing1=1, spacing3=1)
        widget.tag_configure("md_bullet", font=("Microsoft YaHei UI", 10), lmargin1=10, lmargin2=28, spacing1=1, spacing3=1)
        widget.tag_configure(
            "md_code",
            font=("Consolas", 10),
            background="#efefef",
            lmargin1=10,
            lmargin2=10,
            spacing1=1,
            spacing3=1,
        )
        widget.tag_configure("md_quote", font=("Microsoft YaHei UI", 10), foreground=FG_SECONDARY, lmargin1=16, lmargin2=16)

    @staticmethod
    def render_markdown(widget: ScrolledText | None, markdown_text: str) -> None:
        if not widget:
            return
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        in_code_block = False
        for line in markdown_text.splitlines():
            stripped = line.rstrip("\n")
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                if not in_code_block:
                    widget.insert(tk.END, "\n")
                continue
            if in_code_block:
                widget.insert(tk.END, f"{stripped}\n", "md_code")
                continue
            if stripped.startswith("# "):
                widget.insert(tk.END, f"{stripped[2:].strip()}\n", "md_h1")
            elif stripped.startswith("## "):
                widget.insert(tk.END, f"{stripped[3:].strip()}\n", "md_h2")
            elif stripped.startswith("### "):
                widget.insert(tk.END, f"{stripped[4:].strip()}\n", "md_h3")
            elif stripped.startswith("- "):
                widget.insert(tk.END, f"• {stripped[2:].strip()}\n", "md_bullet")
            elif stripped.startswith("> "):
                widget.insert(tk.END, f"{stripped[2:].strip()}\n", "md_quote")
            elif not stripped.strip():
                widget.insert(tk.END, "\n", "md_body")
            else:
                widget.insert(tk.END, f"{stripped}\n", "md_body")
        widget.configure(state="disabled")

    @staticmethod
    def write_plain_text(widget: ScrolledText | None, content: str) -> None:
        if not widget:
            return
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def clear_root(self) -> None:
        for child in self.winfo_children():
            child.destroy()

    def build_section_card(self, parent, title: str, *, expand: bool = False, fill=tk.X):
        shell = ttk.Frame(parent, style="App.TFrame", padding=4)
        border = tk.Frame(shell, bg="#d9d9d9", bd=0, highlightthickness=0)
        border.pack(fill=tk.BOTH, expand=True)

        card = tk.Frame(border, bg=BG_SURFACE, bd=0, highlightthickness=0)
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        header = tk.Frame(card, bg=BG_SURFACE, bd=0, highlightthickness=0)
        header.pack(fill=tk.X, padx=18, pady=(14, 8))

        accent = tk.Frame(header, bg=ACCENT_DARK, width=4, height=20, bd=0, highlightthickness=0)
        accent.pack(side=tk.LEFT, padx=(0, 10))
        accent.pack_propagate(False)

        ttk.Label(header, text=title, style="SectionTitle.TLabel").pack(side=tk.LEFT)

        body = ttk.Frame(card, style="Surface.TFrame", padding=(30, 12, 22, 22))
        body.pack(fill=tk.BOTH, expand=True)
        shell.pack(fill=fill, expand=expand)
        return body

    def load_login_memory(self) -> None:
        saved = self.login_memory_service.load()
        if not saved:
            return

        self.account_var.set(str(saved.get("account", "")))
        self.password_var.set(str(saved.get("password", "")))
        self.lt_var.set(str(saved.get("lt", "web")) or "web")

        saved_environment = str(saved.get("environment_label", ""))
        valid_environment_labels = {item.get("label", key) for key, item in self.environments.items()}
        if saved_environment in valid_environment_labels:
            self.environment_var.set(saved_environment)

    def save_login_memory(self, context: dict) -> None:
        self.login_memory_service.save(
            {
                "account": context.get("account", ""),
                "password": context.get("password", ""),
                "lt": context.get("lt", "web"),
                "environment_label": context.get("environment_label", "测试环境"),
            }
        )

    def build_login_view(self) -> None:
        self.stop_auto_refresh(update_status=False)
        self.clear_root()
        container = ttk.Frame(self, style="App.TFrame", padding=28)
        container.pack(fill=tk.BOTH, expand=True)

        hero = self.build_section_card(container, "登录")
        ttk.Label(hero, text="行情查询工具", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            hero,
            text="独立工具，登录成功后仅提供交易界面行情信息查询，不和 auction_api_demo 混用。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))

        form = self.build_section_card(container, "登录参数")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="账号").grid(row=0, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Entry(form, textvariable=self.account_var, width=44).grid(row=0, column=1, sticky=tk.EW, pady=10)

        ttk.Label(form, text="密码").grid(row=1, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Entry(form, textvariable=self.password_var, width=44, show="*").grid(row=1, column=1, sticky=tk.EW, pady=10)

        ttk.Label(form, text="登录类型 LT").grid(row=2, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Combobox(form, textvariable=self.lt_var, values=["web", "pc"], width=12, state="readonly").grid(
            row=2,
            column=1,
            sticky=tk.W,
            pady=10,
        )

        ttk.Label(form, text="请求环境").grid(row=3, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Combobox(
            form,
            textvariable=self.environment_var,
            values=[item.get("label", key) for key, item in self.environments.items()],
            width=18,
            state="readonly",
        ).grid(row=3, column=1, sticky=tk.W, pady=10)

        action_frame = ttk.Frame(form)
        action_frame.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(16, 0))
        ttk.Button(action_frame, text="登录", command=self.handle_login, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(action_frame, text="退出", command=self.destroy).pack(side=tk.LEFT, padx=(14, 0))

        notice = self.build_section_card(container, "说明", expand=True, fill=tk.BOTH)
        ttk.Label(
            notice,
            justify=tk.LEFT,
            style="Muted.TLabel",
            text=(
                "1. 该工具独立存在，不会把行情接口补到 auction_api_demo 中。\n"
                "2. 登录成功后只显示一个接口：commodity_data_query。\n"
                "3. COI 可为空，为空表示查询所有商品行情。"
            ),
        ).pack(anchor=tk.W)

    def build_main_view(self) -> None:
        self.clear_root()
        container = ttk.Frame(self, style="App.TFrame", padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        topbar = ttk.Frame(container, style="Topbar.TFrame", padding=(18, 14))
        topbar.pack(fill=tk.X)
        self.top_info_var.set(
            f"账号：{self.session_context['account']}    "
            f"LT：{self.session_context['lt']}    "
            f"环境：{self.session_context['environment_label']}    "
            f"U：{self.session_context['login_user_u']}    "
            f"SI：{self.session_context['login_retcode']}"
        )
        ttk.Label(topbar, textvariable=self.top_info_var, style="Topbar.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        ttk.Button(topbar, text="重新登录", command=self.build_login_view).pack(side=tk.RIGHT)

        header = self.build_section_card(container, "唯一接口")
        ttk.Label(
            header,
            text=f"{MARKET_INTERFACE['display_name']} ({MARKET_INTERFACE['name']})",
            style="SectionTitle.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            header,
            text=MARKET_INTERFACE["description"],
            style="Muted.TLabel",
            wraplength=1080,
        ).pack(anchor=tk.W, pady=(6, 0))

        action_bar = ttk.Frame(container, style="App.TFrame")
        action_bar.pack(fill=tk.X, pady=(0, 12))
        ttk.Button(action_bar, text="恢复默认参数", command=self.reset_form).pack(side=tk.LEFT)
        ttk.Button(action_bar, text="刷新请求 JSON", command=self.refresh_payload_preview).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action_bar, text="查看请求信息", command=self.open_request_window).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action_bar, text="查看返回信息", command=self.open_response_window).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action_bar, text="查看接口说明", command=self.open_description_window).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(action_bar, text="自动刷新秒数").pack(side=tk.LEFT, padx=(16, 6))
        ttk.Entry(action_bar, textvariable=self.auto_refresh_interval_var, width=6).pack(side=tk.LEFT)
        ttk.Button(action_bar, text="开启自动刷新", command=self.start_auto_refresh).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action_bar, text="停止自动刷新", command=self.stop_auto_refresh).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action_bar, text="查询行情", command=self.submit_market_query, style="Primary.TButton").pack(side=tk.RIGHT)

        self.form_frame = self.build_section_card(container, "固定请求参数")
        self.form_frame.columnconfigure(1, weight=1)

        preview_frame = self.build_section_card(container, "请求 JSON 预览")
        self.param_preview = ScrolledText(preview_frame)
        self.style_text_widget(self.param_preview, height=8)
        self.param_preview.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, textvariable=self.status_var, style="Status.TLabel").pack(anchor=tk.W, pady=(10, 10))

        body_shell = ttk.Frame(container, style="App.TFrame", padding=4)
        body_shell.pack(fill=tk.BOTH, expand=True)
        body = ttk.Notebook(body_shell)
        body.pack(fill=tk.BOTH, expand=True)

        request_frame = ttk.Frame(body, style="App.TFrame", padding=4)
        request_card = self.build_section_card(request_frame, "请求信息", expand=True, fill=tk.BOTH)
        self.request_viewer = ScrolledText(request_card)
        self.style_text_widget(self.request_viewer, height=18)
        self.request_viewer.pack(fill=tk.BOTH, expand=True)
        body.add(request_frame, text="请求信息")

        response_frame = ttk.Frame(body, style="App.TFrame", padding=4)
        response_card = self.build_section_card(response_frame, "返回信息", expand=True, fill=tk.BOTH)
        self.response_viewer = ScrolledText(response_card)
        self.style_text_widget(self.response_viewer, height=20)
        self.response_viewer.pack(fill=tk.BOTH, expand=True)
        body.add(response_frame, text="返回信息")

        description_frame = ttk.Frame(body, style="App.TFrame", padding=4)
        description_card = self.build_section_card(description_frame, "接口说明", expand=True, fill=tk.BOTH)
        self.description_viewer = ScrolledText(description_card)
        self.style_text_widget(self.description_viewer, height=18)
        self.description_viewer.pack(fill=tk.BOTH, expand=True)
        body.add(description_frame, text="接口说明")

        self.reset_form()
        self.description_markdown = self.build_description_markdown()
        self.render_markdown(self.description_viewer, self.description_markdown)
        self.render_http_result(self.session_context["login_result"], prefix="登录请求")

    def build_login_context_from_inputs(self) -> dict | None:
        account = self.account_var.get().strip()
        password = self.password_var.get()
        lt = self.lt_var.get().strip() or "web"
        environment_label = self.environment_var.get().strip() or "测试环境"
        environment_key = ENVIRONMENT_LABEL_TO_KEY.get(environment_label, self.default_environment_key)
        endpoint = self.interface_service.get_endpoint(environment_key)
        if not account or not password:
            messagebox.showwarning("提示", "请先输入账号和密码。")
            return None
        return {
            "account": account,
            "password": password,
            "lt": lt,
            "environment_label": environment_label,
            "environment_key": environment_key,
            "endpoint": endpoint,
        }

    def handle_login(self) -> None:
        context = self.build_login_context_from_inputs()
        if not context:
            return

        self.api_client.set_endpoint(context["endpoint"])
        context["encrypted_password"] = self.crypto_service.encrypt(context["password"])
        payload = self.interface_service.apply_context(
            self.login_interface["params"],
            {
                "account": context["account"],
                "encrypted_password": context["encrypted_password"],
                "lt": context["lt"],
            },
        )

        try:
            result = self.api_client.send_request(
                payload=payload,
                request_mode=self.login_interface.get("request_mode", "json"),
                method=self.login_interface.get("method", "POST"),
            )
        except Exception as exc:
            messagebox.showerror("登录失败", f"请求登录接口时发生异常：\n{exc}")
            return

        retcode = self.extract_retcode(result["response_json"])
        if result["status_code"] >= 400:
            messagebox.showerror("登录失败", self.format_http_error(result))
            return

        if self.is_negative_retcode(retcode):
            error_message = self.error_code_service.get_message(retcode)
            messagebox.showerror("登录失败", f"错误码：{retcode}\n错误信息：{error_message}")
            return

        self.session_context = {
            **context,
            "encrypted_password": context["encrypted_password"],
            "login_user_u": self.extract_login_user(result["response_json"], fallback=context["account"]),
            "login_retcode": self.extract_login_retcode(result["response_json"]),
            "login_result": result,
        }
        self.save_login_memory(context)
        self.build_main_view()

    def reset_form(self) -> None:
        if not self.form_frame:
            return
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.current_field_vars = {}

        for row_index, field in enumerate(MARKET_INTERFACE["fields"]):
            field_name = field["name"]
            default_value = self.resolve_default_value(field.get("default", ""))
            field_var = tk.StringVar(value=default_value)
            self.current_field_vars[field_name] = field_var

            ttk.Label(self.form_frame, text=field.get("label", field_name)).grid(
                row=row_index, column=0, sticky=tk.W, padx=(0, 8), pady=4
            )
            entry = ttk.Entry(self.form_frame, textvariable=field_var, width=42)
            if field.get("readonly"):
                entry.configure(state="readonly")
            entry.grid(row=row_index, column=1, sticky=tk.EW, padx=(0, 8), pady=4)
            ttk.Label(
                self.form_frame,
                text=field.get("description", ""),
                justify=tk.LEFT,
                wraplength=420,
                foreground=FG_SECONDARY,
            ).grid(row=row_index, column=2, sticky=tk.W, pady=4)
            field_var.trace_add("write", lambda *_args: self.refresh_payload_preview())

        self.refresh_payload_preview()

    def resolve_default_value(self, default_value):
        if isinstance(default_value, str):
            return self.interface_service.apply_context(default_value, self.build_context())
        if default_value is None:
            return ""
        return str(default_value)

    def build_context(self) -> dict:
        return dict(self.session_context)

    def collect_payload(self) -> dict:
        payload = self.interface_service.apply_context(dict(MARKET_INTERFACE["params"]), self.build_context())
        for field in MARKET_INTERFACE["fields"]:
            payload[field["name"]] = self.current_field_vars[field["name"]].get().strip()
        return payload

    def refresh_payload_preview(self) -> None:
        if not self.param_preview:
            return
        payload_text = self.pretty_dump(self.collect_payload())
        self.write_plain_text(self.param_preview, payload_text)

    def submit_market_query(self, *, silent: bool = False) -> bool:
        payload = self.collect_payload()
        self.api_client.set_endpoint(self.session_context["endpoint"])

        try:
            result = self.api_client.send_request(
                payload=payload,
                request_mode=MARKET_INTERFACE.get("request_mode", "json"),
                method=MARKET_INTERFACE.get("method", "POST"),
            )
        except Exception as exc:
            self.refresh_failure_count += 1
            self.update_status_text(f"查询失败：{exc}")
            if not silent:
                messagebox.showerror("查询失败", f"行情接口调用异常：\n{exc}")
            return False

        retcode = self.extract_retcode(result["response_json"])
        status_text = f"HTTP {result['status_code']}"
        if self.is_negative_retcode(retcode):
            error_message = self.error_code_service.get_message(retcode)
            status_text += f"    RETCODE：{retcode}    错误信息：{error_message}"
        elif retcode is not None:
            status_text += f"    RETCODE：{retcode}"
        else:
            status_text += "    未识别到 RETCODE"

        if result["status_code"] >= 400 or self.is_negative_retcode(retcode):
            self.refresh_failure_count += 1
        else:
            self.refresh_failure_count = 0
            self.last_refresh_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.render_http_result(result, status_text)
        return True

    def render_http_result(self, result: dict, status_text: str | None = None, prefix: str = "行情请求") -> None:
        self.latest_http_result = result
        retcode = self.extract_retcode(result["response_json"])
        if status_text is None:
            status_text = f"{prefix}    HTTP {result['status_code']}"
            if retcode is not None:
                status_text += f"    RETCODE：{retcode}"
        self.update_status_text(status_text)

        self.request_markdown = self.build_request_markdown(result, prefix)
        self.response_markdown = self.build_response_markdown(result, retcode)
        self.render_markdown(self.request_viewer, self.request_markdown)
        self.render_markdown(self.response_viewer, self.response_markdown)

    def open_request_window(self) -> None:
        self.open_text_window("请求信息", self.request_markdown)

    def open_response_window(self) -> None:
        self.open_response_detail_window()

    def open_description_window(self) -> None:
        self.open_text_window("接口说明", self.description_markdown)

    def open_text_window(self, title: str, markdown_text: str) -> None:
        result_window = tk.Toplevel(self)
        result_window.title(title)
        result_window.geometry("1080x760")
        result_window.minsize(920, 640)
        try:
            result_window.iconbitmap(default=str(save_temp_icon()))
        except Exception:
            pass

        shell = ttk.Frame(result_window, style="App.TFrame", padding=12)
        shell.pack(fill=tk.BOTH, expand=True)
        viewer = ScrolledText(shell)
        self.style_text_widget(viewer, height=30)
        viewer.pack(fill=tk.BOTH, expand=True)
        self.render_markdown(viewer, markdown_text)

    def open_response_detail_window(self) -> None:
        result_window = tk.Toplevel(self)
        result_window.title("返回信息")
        result_window.geometry("1260x820")
        result_window.minsize(1080, 720)
        try:
            result_window.iconbitmap(default=str(save_temp_icon()))
        except Exception:
            pass

        shell = ttk.Frame(result_window, style="App.TFrame", padding=12)
        shell.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(shell)
        notebook.pack(fill=tk.BOTH, expand=True)

        table_tab = ttk.Frame(notebook, style="App.TFrame", padding=6)
        raw_tab = ttk.Frame(notebook, style="App.TFrame", padding=6)
        notebook.add(table_tab, text="表格视图")
        notebook.add(raw_tab, text="原始返回")

        self.build_response_table_view(table_tab)

        raw_card = ttk.LabelFrame(raw_tab, text="原始返回", padding=12, style="Card.TLabelframe")
        raw_card.pack(fill=tk.BOTH, expand=True)
        raw_viewer = ScrolledText(raw_card)
        self.style_text_widget(raw_viewer, height=30)
        raw_viewer.pack(fill=tk.BOTH, expand=True)
        self.write_plain_text(raw_viewer, self.build_response_raw_text())

    def handle_close(self) -> None:
        self.stop_auto_refresh(update_status=False)
        self.destroy()

    def build_response_table_view(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="行情结果表格", padding=12, style="Card.TLabelframe")
        card.pack(fill=tk.BOTH, expand=True)
        records = self.extract_market_records(self.latest_http_result)

        toolbar = ttk.Frame(card, style="Surface.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(toolbar, text="导出 CSV", command=lambda: self.export_quotes_csv(records)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="导出 Excel", command=lambda: self.export_quotes_excel(records)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(toolbar, text="搜索").pack(side=tk.LEFT, padx=(20, 6))
        search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=search_var, width=26).pack(side=tk.LEFT)

        summary_text = self.build_market_summary()
        ttk.Label(card, text=summary_text, style="Muted.TLabel", wraplength=1120).pack(anchor=tk.W, pady=(0, 10))

        columns = (
            "coi",
            "con",
            "high",
            "low",
            "last",
            "cha",
            "buy_qty",
            "buy_price",
            "sell_qty",
            "sell_price",
            "depth_count",
        )
        headings = {
            "coi": "商品代码",
            "con": "商品名称",
            "high": "最高",
            "low": "最低",
            "last": "最新",
            "cha": "涨跌",
            "buy_qty": "买量",
            "buy_price": "买价",
            "sell_qty": "卖量",
            "sell_price": "卖价",
            "depth_count": "盘口档数",
        }

        table_container = ttk.Panedwindow(card, orient=tk.VERTICAL)
        table_container.pack(fill=tk.BOTH, expand=True)

        tree_frame = ttk.Frame(table_container, style="Surface.TFrame")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=18)
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        tree.tag_configure("positive", foreground=FG_POSITIVE)
        tree.tag_configure("negative", foreground=FG_NEGATIVE)
        tree.tag_configure("neutral", foreground=FG_NEUTRAL)

        widths = {
            "coi": 180,
            "con": 180,
            "high": 100,
            "low": 100,
            "last": 100,
            "cha": 100,
            "buy_qty": 100,
            "buy_price": 100,
            "sell_qty": 100,
            "sell_price": 100,
            "depth_count": 90,
        }
        for column in columns:
            tree.heading(column, text=headings[column], command=lambda col=column: self.sort_treeview_column(tree, col, False))
            tree.column(column, width=widths[column], stretch=True, anchor=tk.CENTER)

        detail_frame = ttk.LabelFrame(table_container, text="买卖盘多档", padding=12, style="Card.TLabelframe")
        detail_frame.columnconfigure(0, weight=1)
        detail_label = ttk.Label(
            detail_frame,
            text="选中上方某一行后，这里显示该商品的多档买卖盘。",
            style="Muted.TLabel",
        )
        detail_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        depth_columns = ("level", "buy_qty", "buy_price", "sell_qty", "sell_price")
        depth_tree = ttk.Treeview(detail_frame, columns=depth_columns, show="headings", height=8)
        depth_vsb = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=depth_tree.yview)
        depth_hsb = ttk.Scrollbar(detail_frame, orient=tk.HORIZONTAL, command=depth_tree.xview)
        depth_tree.configure(yscrollcommand=depth_vsb.set, xscrollcommand=depth_hsb.set)
        depth_tree.grid(row=1, column=0, sticky="nsew")
        depth_vsb.grid(row=1, column=1, sticky="ns")
        depth_hsb.grid(row=2, column=0, sticky="ew")
        detail_frame.rowconfigure(1, weight=1)
        for column, heading, width in (
            ("level", "档位", 90),
            ("buy_qty", "买量", 140),
            ("buy_price", "买价", 140),
            ("sell_qty", "卖量", 140),
            ("sell_price", "卖价", 140),
        ):
            depth_tree.heading(column, text=heading)
            depth_tree.column(column, width=width, stretch=True, anchor=tk.CENTER)

        table_container.add(tree_frame, weight=3)
        table_container.add(detail_frame, weight=2)

        row_map = {}
        def insert_rows(keyword: str = "") -> None:
            for item in tree.get_children():
                tree.delete(item)
            row_map.clear()
            lowered_keyword = keyword.strip().lower()
            for record in records:
                coi = str(record.get("COI", "")).lower()
                con = str(record.get("CON", "")).lower()
                if lowered_keyword and lowered_keyword not in coi and lowered_keyword not in con:
                    continue
                item_id = tree.insert(
                    "",
                    tk.END,
                    values=(
                        record.get("COI", ""),
                        record.get("CON", ""),
                        record.get("HIGH", ""),
                        record.get("LOW", ""),
                        record.get("LAST", ""),
                        record.get("CHA", ""),
                        record.get("BQ", ""),
                        record.get("BP", ""),
                        record.get("SQ", ""),
                        record.get("SP", ""),
                        len(record.get("BSL_LEVELS", [])),
                    ),
                    tags=(self.get_change_tag(record.get("CHA", "")),),
                )
                row_map[item_id] = record

        if records:
            insert_rows()

            def on_select(_event=None):
                selection = tree.selection()
                if not selection:
                    return
                self.populate_depth_tree(depth_tree, detail_label, row_map.get(selection[0], {}))

            def on_double_click(_event=None):
                selection = tree.selection()
                if not selection:
                    return
                selected_record = row_map.get(selection[0], {})
                if selected_record:
                    self.open_quote_detail_window(selected_record)

            def on_search_change(*_args):
                insert_rows(search_var.get())
                current_items = tree.get_children()
                if current_items:
                    tree.selection_set(current_items[0])
                    self.populate_depth_tree(depth_tree, detail_label, row_map.get(current_items[0], {}))
                else:
                    self.populate_depth_tree(depth_tree, detail_label, {})

            tree.bind("<<TreeviewSelect>>", on_select)
            tree.bind("<Double-1>", on_double_click)
            search_var.trace_add("write", on_search_change)
            first_item = tree.get_children()
            if first_item:
                tree.selection_set(first_item[0])
                self.populate_depth_tree(depth_tree, detail_label, row_map.get(first_item[0], {}))
        else:
            empty_label = ttk.Label(
                card,
                text="当前返回中没有可展示的行情列表记录，可能现在显示的是登录返回，或接口未返回 RESULTLIST.REC。",
                style="Muted.TLabel",
                wraplength=1120,
            )
            empty_label.pack(anchor=tk.W, pady=(10, 0))

    def open_quote_detail_window(self, record: dict) -> None:
        detail_window = tk.Toplevel(self)
        detail_window.title(f"商品详情 - {record.get('CON', '')}")
        detail_window.geometry("980x760")
        detail_window.minsize(900, 680)
        try:
            detail_window.iconbitmap(default=str(save_temp_icon()))
        except Exception:
            pass

        shell = ttk.Frame(detail_window, style="App.TFrame", padding=12)
        shell.pack(fill=tk.BOTH, expand=True)

        summary_card = ttk.LabelFrame(shell, text="商品详情", padding=12, style="Card.TLabelframe")
        summary_card.pack(fill=tk.X)
        summary_viewer = ScrolledText(summary_card)
        self.style_text_widget(summary_viewer, height=14)
        summary_viewer.pack(fill=tk.BOTH, expand=True)
        self.render_markdown(summary_viewer, self.build_quote_detail_markdown(record))

        depth_card = ttk.LabelFrame(shell, text="买卖盘多档", padding=12, style="Card.TLabelframe")
        depth_card.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        depth_detail_label = ttk.Label(
            depth_card,
            text=f"当前商品：{record.get('CON', '')} ({record.get('COI', '')})    涨跌：{record.get('CHA', '')}",
            style="Muted.TLabel",
        )
        depth_detail_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        depth_tree = ttk.Treeview(depth_card, columns=("level", "buy_qty", "buy_price", "sell_qty", "sell_price"), show="headings")
        depth_vsb = ttk.Scrollbar(depth_card, orient=tk.VERTICAL, command=depth_tree.yview)
        depth_hsb = ttk.Scrollbar(depth_card, orient=tk.HORIZONTAL, command=depth_tree.xview)
        depth_tree.configure(yscrollcommand=depth_vsb.set, xscrollcommand=depth_hsb.set)
        depth_tree.grid(row=1, column=0, sticky="nsew")
        depth_vsb.grid(row=1, column=1, sticky="ns")
        depth_hsb.grid(row=2, column=0, sticky="ew")
        depth_card.rowconfigure(1, weight=1)
        depth_card.columnconfigure(0, weight=1)
        for column, heading, width in (
            ("level", "档位", 90),
            ("buy_qty", "买量", 160),
            ("buy_price", "买价", 160),
            ("sell_qty", "卖量", 160),
            ("sell_price", "卖价", 160),
        ):
            depth_tree.heading(column, text=heading)
            depth_tree.column(column, width=width, stretch=True, anchor=tk.CENTER)
        self.populate_depth_tree(depth_tree, depth_detail_label, record)

    def start_auto_refresh(self) -> None:
        interval = self.get_auto_refresh_interval()
        if interval is None:
            messagebox.showwarning("提示", "自动刷新秒数请输入大于等于 1 的整数。")
            return
        self.stop_auto_refresh(update_status=False)
        self.auto_refresh_enabled = True
        self.update_status_text(f"已开启自动刷新，每 {interval} 秒自动刷新一次。")
        self.auto_refresh_after_id = self.after(interval * 1000, self.run_auto_refresh)

    def run_auto_refresh(self) -> None:
        self.auto_refresh_after_id = None
        interval = self.get_auto_refresh_interval()
        if interval is None:
            return
        self.submit_market_query(silent=True)
        if self.winfo_exists():
            self.auto_refresh_after_id = self.after(interval * 1000, self.run_auto_refresh)

    def stop_auto_refresh(self, update_status: bool = True) -> None:
        self.auto_refresh_enabled = False
        if self.auto_refresh_after_id is not None:
            self.after_cancel(self.auto_refresh_after_id)
            self.auto_refresh_after_id = None
        if update_status:
            self.update_status_text("已停止自动刷新。")

    def get_auto_refresh_interval(self) -> int | None:
        try:
            interval = int(self.auto_refresh_interval_var.get().strip())
        except (TypeError, ValueError, AttributeError):
            return None
        if interval < 1:
            return None
        return interval

    def build_description_markdown(self) -> str:
        description_body = "\n".join(MARKET_INTERFACE["response_description"])
        return "\n".join(
            [
                "# 接口说明",
                "",
                f"- 接口名称：`{MARKET_INTERFACE['name']}`",
                f"- 展示名称：{MARKET_INTERFACE['display_name']}",
                f"- 说明：{MARKET_INTERFACE['description']}",
                "",
                "## 返回包定义",
                "",
                "```json",
                description_body,
                "```",
            ]
        )

    def build_request_markdown(self, result: dict, prefix: str) -> str:
        return "\n".join(
            [
                f"# {prefix}",
                "",
                f"- 请求地址：{result['url']}",
                f"- 请求方式：{result['method']}",
                f"- 提交模式：{result['request_mode']}",
                "",
                "## Headers",
                "",
                "```json",
                self.pretty_dump(result["request_headers"]),
                "```",
                "",
                "## Payload",
                "",
                "```json",
                self.pretty_dump(result["request_payload"]),
                "```",
                "",
                "## Request Body",
                "",
                "```json",
                str(result["request_body"]),
                "```",
            ]
        )

    def build_response_markdown(self, result: dict, retcode) -> str:
        response_body = result["response_json"] if result["response_json"] is not None else result["response_text"]
        error_message = self.error_code_service.get_message(retcode) if self.is_negative_retcode(retcode) else ""
        return "\n".join(
            [
                "# 返回信息",
                "",
                f"- HTTP 状态：{result['status_code']}",
                f"- RETCODE：{retcode if retcode is not None else '未识别'}",
                f"- 错误信息：{error_message or '无'}",
                "",
                "## Headers",
                "",
                "```json",
                self.pretty_dump(result["response_headers"]),
                "```",
                "",
                "## Body",
                "",
                "```json",
                self.pretty_dump(response_body),
                "```",
            ]
        )

    def build_response_raw_text(self) -> str:
        result = self.latest_http_result or {}
        response_body = result.get("response_json") if result.get("response_json") is not None else result.get("response_text", "")
        return self.pretty_dump(
            {
                "status_code": result.get("status_code", ""),
                "headers": result.get("response_headers", {}),
                "body": response_body,
            }
        )

    def build_quote_detail_markdown(self, record: dict) -> str:
        levels = record.get("BSL_LEVELS", [])
        return "\n".join(
            [
                "# 单商品详情",
                "",
                f"- 商品代码：{record.get('COI', '')}",
                f"- 商品名称：{record.get('CON', '')}",
                f"- 最新：{record.get('LAST', '')}",
                f"- 最高：{record.get('HIGH', '')}",
                f"- 最低：{record.get('LOW', '')}",
                f"- 涨跌：{record.get('CHA', '')}",
                f"- 多档数量：{len(levels)}",
                "",
                "## 原始商品记录",
                "",
                "```json",
                self.pretty_dump(record),
                "```",
            ]
        )

    def build_market_summary(self) -> str:
        result = self.latest_http_result or {}
        response_json = result.get("response_json")
        retcode = self.extract_retcode(response_json)
        total = self.extract_total_records(response_json)
        parts = [f"HTTP：{result.get('status_code', '')}"]
        if retcode is not None:
            parts.append(f"RETCODE：{retcode}")
        if total not in (None, ""):
            parts.append(f"总记录数：{total}")
        parts.append(f"接口：{MARKET_INTERFACE['name']}")
        if self.last_refresh_at:
            parts.append(f"上次刷新：{self.last_refresh_at}")
        parts.append(f"失败次数：{self.refresh_failure_count}")
        return "    ".join(parts)

    def update_status_text(self, base_text: str) -> None:
        parts = [base_text]
        if self.last_refresh_at:
            parts.append(f"上次刷新：{self.last_refresh_at}")
        parts.append(f"失败次数：{self.refresh_failure_count}")
        if self.auto_refresh_enabled:
            interval = self.get_auto_refresh_interval()
            if interval is not None:
                parts.append(f"自动刷新：每 {interval} 秒")
        self.status_var.set("    ".join(parts))

    @staticmethod
    def extract_total_records(data):
        if isinstance(data, dict):
            for key in ("TTLREC", "TC", "total", "totalCount"):
                if key in data:
                    return data[key]
            for value in data.values():
                result = MarketQuoteToolWindow.extract_total_records(value)
                if result not in (None, ""):
                    return result
        if isinstance(data, list):
            for item in data:
                result = MarketQuoteToolWindow.extract_total_records(item)
                if result not in (None, ""):
                    return result
        return None

    @staticmethod
    def extract_market_records(http_result: dict | None) -> list[dict]:
        if not http_result:
            return []
        data = http_result.get("response_json")
        if not isinstance(data, dict):
            return []

        records = []
        result_list = data.get("RESULTLIST") or data.get("resultList") or data.get("resultlist")
        if isinstance(result_list, dict):
            rec_items = result_list.get("REC") or result_list.get("rec") or []
            if isinstance(rec_items, list):
                records = rec_items

        flattened = []
        for item in records:
            if not isinstance(item, dict):
                continue
            quote = dict(item)
            buy_sell = quote.get("BSL")
            levels = []
            if isinstance(buy_sell, list):
                for index, level in enumerate(buy_sell, start=1):
                    if not isinstance(level, dict):
                        continue
                    current_bs = level.get("BS") or level.get("bs") or {}
                    if isinstance(current_bs, dict):
                        levels.append(
                            {
                                "level": index,
                                "BQ": current_bs.get("BQ", ""),
                                "BP": current_bs.get("BP", ""),
                                "SQ": current_bs.get("SQ", ""),
                                "SP": current_bs.get("SP", ""),
                            }
                        )
            quote["BSL_LEVELS"] = levels
            if levels:
                quote["BQ"] = levels[0].get("BQ", "")
                quote["BP"] = levels[0].get("BP", "")
                quote["SQ"] = levels[0].get("SQ", "")
                quote["SP"] = levels[0].get("SP", "")
            flattened.append(quote)
        return flattened

    @staticmethod
    def get_change_tag(change_value) -> str:
        parsed = MarketQuoteToolWindow.parse_number(change_value)
        if parsed is None:
            return "neutral"
        if parsed > 0:
            return "positive"
        if parsed < 0:
            return "negative"
        return "neutral"

    @staticmethod
    def parse_number(value):
        try:
            return float(str(value).strip())
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def populate_depth_tree(depth_tree: ttk.Treeview, detail_label: ttk.Label, record: dict) -> None:
        for item in depth_tree.get_children():
            depth_tree.delete(item)
        if not record:
            detail_label.configure(text="选中上方某一行后，这里显示该商品的多档买卖盘。")
            return

        detail_label.configure(
            text=f"当前商品：{record.get('CON', '')} ({record.get('COI', '')})    涨跌：{record.get('CHA', '')}"
        )
        levels = record.get("BSL_LEVELS", [])
        if not levels:
            depth_tree.insert("", tk.END, values=("无", "", "", "", ""))
            return
        for level in levels:
            depth_tree.insert(
                "",
                tk.END,
                values=(
                    f"买卖{level.get('level', '')}",
                    level.get("BQ", ""),
                    level.get("BP", ""),
                    level.get("SQ", ""),
                    level.get("SP", ""),
                ),
            )

    def export_quotes_csv(self, records: list[dict]) -> None:
        if not records:
            messagebox.showwarning("提示", "当前没有可导出的行情记录。")
            return
        file_path = filedialog.asksaveasfilename(
            title="导出 CSV",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialfile=f"auction_market_quotes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not file_path:
            return

        headers, rows = self.build_quote_export_rows(records)
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as exc:
            messagebox.showerror("导出失败", f"写入 CSV 文件失败：\n{exc}")
            return
        messagebox.showinfo("导出成功", f"CSV 已导出到：\n{file_path}")

    def export_quotes_excel(self, records: list[dict]) -> None:
        if not records:
            messagebox.showwarning("提示", "当前没有可导出的行情记录。")
            return
        if Workbook is None:
            messagebox.showerror("导出失败", "当前环境未安装 openpyxl，暂时无法导出 Excel。")
            return

        file_path = filedialog.asksaveasfilename(
            title="导出 Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx")],
            initialfile=f"auction_market_quotes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        if not file_path:
            return

        headers, rows = self.build_quote_export_rows(records)
        depth_headers, depth_rows = self.build_depth_export_rows(records)
        workbook = Workbook()
        quote_sheet = workbook.active
        quote_sheet.title = "行情总览"
        quote_sheet.append(headers)
        for row in rows:
            quote_sheet.append(row)

        depth_sheet = workbook.create_sheet("买卖盘多档")
        depth_sheet.append(depth_headers)
        for row in depth_rows:
            depth_sheet.append(row)

        for sheet in workbook.worksheets:
            for column_cells in sheet.columns:
                max_length = max(len(str(cell.value or "")) for cell in column_cells)
                sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 28)

        try:
            workbook.save(file_path)
        except OSError as exc:
            messagebox.showerror("导出失败", f"写入 Excel 文件失败：\n{exc}")
            return
        messagebox.showinfo("导出成功", f"Excel 已导出到：\n{file_path}")

    @staticmethod
    def build_quote_export_rows(records: list[dict]) -> tuple[list[str], list[list[str]]]:
        max_depth = max((len(record.get("BSL_LEVELS", [])) for record in records), default=0)
        headers = ["商品代码", "商品名称", "最高", "最低", "最新", "涨跌"]
        for index in range(1, max_depth + 1):
            headers.extend([f"买{index}量", f"买{index}价", f"卖{index}量", f"卖{index}价"])

        rows = []
        for record in records:
            row = [
                record.get("COI", ""),
                record.get("CON", ""),
                record.get("HIGH", ""),
                record.get("LOW", ""),
                record.get("LAST", ""),
                record.get("CHA", ""),
            ]
            levels = record.get("BSL_LEVELS", [])
            for index in range(max_depth):
                level = levels[index] if index < len(levels) else {}
                row.extend(
                    [
                        level.get("BQ", ""),
                        level.get("BP", ""),
                        level.get("SQ", ""),
                        level.get("SP", ""),
                    ]
                )
            rows.append(row)
        return headers, rows

    def sort_treeview_column(self, tree: ttk.Treeview, column: str, reverse: bool) -> None:
        items = [(tree.set(item, column), item) for item in tree.get_children("")]

        def sort_key(pair):
            raw_value = pair[0]
            number_value = self.parse_number(raw_value)
            if number_value is not None:
                return (0, number_value)
            return (1, str(raw_value).lower())

        items.sort(key=sort_key, reverse=reverse)
        for index, (_value, item) in enumerate(items):
            tree.move(item, "", index)
        tree.heading(column, command=lambda: self.sort_treeview_column(tree, column, not reverse))

    @staticmethod
    def build_depth_export_rows(records: list[dict]) -> tuple[list[str], list[list[str]]]:
        headers = ["商品代码", "商品名称", "档位", "买量", "买价", "卖量", "卖价"]
        rows = []
        for record in records:
            levels = record.get("BSL_LEVELS", [])
            if not levels:
                rows.append([record.get("COI", ""), record.get("CON", ""), "", "", "", "", ""])
                continue
            for level in levels:
                rows.append(
                    [
                        record.get("COI", ""),
                        record.get("CON", ""),
                        level.get("level", ""),
                        level.get("BQ", ""),
                        level.get("BP", ""),
                        level.get("SQ", ""),
                        level.get("SP", ""),
                    ]
                )
        return headers, rows

    @staticmethod
    def extract_retcode(data):
        if isinstance(data, dict):
            for key in ("RETCODE", "retCode", "returnCode", "code"):
                if key in data:
                    return data[key]
            for value in data.values():
                result = MarketQuoteToolWindow.extract_retcode(value)
                if result is not None:
                    return result
        if isinstance(data, list):
            for item in data:
                result = MarketQuoteToolWindow.extract_retcode(item)
                if result is not None:
                    return result
        return None

    @staticmethod
    def extract_login_retcode(data):
        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                for key in ("RETCODE", "retCode", "returnCode", "code"):
                    if key in result:
                        return result[key]
            return MarketQuoteToolWindow.extract_retcode(data)

    @staticmethod
    def extract_login_user(data, fallback: str = "") -> str:
        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                for key in ("U", "u", "USERID", "userId"):
                    value = result.get(key)
                    if value not in (None, ""):
                        return str(value)
            for key in ("U", "u", "USERID", "userId"):
                value = data.get(key)
                if value not in (None, ""):
                    return str(value)
            for value in data.values():
                extracted = MarketQuoteToolWindow.extract_login_user(value, "")
                if extracted:
                    return extracted
        if isinstance(data, list):
            for item in data:
                extracted = MarketQuoteToolWindow.extract_login_user(item, "")
                if extracted:
                    return extracted
        return fallback

    @staticmethod
    def is_negative_retcode(retcode) -> bool:
        if retcode is None:
            return False
        try:
            return int(str(retcode)) < 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def pretty_dump(data) -> str:
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except (TypeError, ValueError):
                return data
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def write_text(widget: ScrolledText | None, content: str) -> None:
        if not widget:
            return
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, content)

    @staticmethod
    def format_http_error(result: dict) -> str:
        response_body = result["response_json"] if result["response_json"] is not None else result["response_text"]
        return (
            f"HTTP 状态码：{result['status_code']}\n"
            f"请求地址：{result['url']}\n"
            f"请求方式：{result['method']}\n\n"
            f"返回结果：\n{MarketQuoteToolWindow.pretty_dump(response_body)}"
        )


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    window = MarketQuoteToolWindow(root)
    window.mainloop()
