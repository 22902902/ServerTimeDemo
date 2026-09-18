import json
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .services.api_client import ApiClient
from .services.crypto_service import DESCryptoService
from .services.error_code_service import ErrorCodeService
from .services.icon_service import save_temp_icon
from .services.interface_service import InterfaceService
from .services.login_memory_service import LoginMemoryService
from ui_theme import ADMIN_TOOL_PALETTE, THEME

try:
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None


MEMBER_LABELS = {
    "supplier": "供货会员",
    "broker": "经济会员",
}

ENVIRONMENT_LABEL_TO_KEY = {
    "测试环境": "test",
    "正式环境": "prod",
}

SESSION_REFRESH_WINDOW = timedelta(minutes=25)
SESSION_EXPIRE_CODES = {
    "-998100000001",
    "-998310000000",
    "-998310000001",
    "-998310000002",
}
# 统一映射到全局后台工具主题
BG_APP = ADMIN_TOOL_PALETTE.bg
BG_SURFACE = ADMIN_TOOL_PALETTE.surface
BG_MUTED = ADMIN_TOOL_PALETTE.surface_alt
FG_PRIMARY = ADMIN_TOOL_PALETTE.text_primary
FG_SECONDARY = ADMIN_TOOL_PALETTE.text_secondary
FG_MUTED = ADMIN_TOOL_PALETTE.text_muted
BORDER_COLOR = ADMIN_TOOL_PALETTE.border
ACCENT_DARK = ADMIN_TOOL_PALETTE.accent
ACCENT_DARK_HOVER = ADMIN_TOOL_PALETTE.accent_hover
BUTTON_LIGHT = ADMIN_TOOL_PALETTE.button_bg
BUTTON_LIGHT_HOVER = ADMIN_TOOL_PALETTE.button_hover
STATUS_BLUE = ADMIN_TOOL_PALETTE.status


class ApiDemoWindow(tk.Toplevel):
    def __init__(self, master=None) -> None:
        super().__init__(master)
        self.title("接口测试 Demo")
        self.geometry("1380x880")
        self.minsize(1200, 760)
        self.configure(bg=BG_APP)
        self.configure_theme()
        self.apply_window_icon()

        self.crypto_service = DESCryptoService()
        self.error_code_service = ErrorCodeService()  # 内嵌，无需文件
        self.interface_service = InterfaceService()  # 内嵌，无需文件
        self.environments = self.interface_service.get_environments()
        self.default_environment_key = self.interface_service.get_default_environment_key()
        self.api_client = ApiClient(self.interface_service.get_endpoint(self.default_environment_key))

        self.member_interfaces: list[dict] = []
        self.current_interface_index: int | None = None
        self.session_context: dict = {}

        self.account_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.lt_var = tk.StringVar(value="web")
        self.member_type_var = tk.StringVar(value="supplier")
        self.environment_var = tk.StringVar(
            value=self.environments.get(self.default_environment_key, {}).get("label", "测试环境")
        )
        self.login_memory_service = LoginMemoryService()

        self.top_frame: ttk.Frame | None = None
        self.content_frame: ttk.Frame | None = None
        self.interface_listbox: tk.Listbox | None = None
        self.interface_name_var = tk.StringVar(value="未选择接口")
        self.interface_meta_var = tk.StringVar(value="")
        self.response_status_var = tk.StringVar(value="等待提交接口请求")
        self.top_info_var = tk.StringVar(value="")
        self.endpoint_info_var = tk.StringVar(value="")
        self.form_helper_summary_var = tk.StringVar(value="")
        self.form_helper_detail_var = tk.StringVar(value="")

        self.param_form_frame: ttk.Frame | None = None
        self.param_preview: ScrolledText | None = None
        self.request_viewer: ScrolledText | None = None
        self.response_viewer: ScrolledText | None = None
        self.encrypt_input: ScrolledText | None = None
        self.encrypt_output: ScrolledText | None = None
        self.current_field_vars: dict[str, tk.StringVar] = {}
        self.current_field_meta: list[dict] = []
        self.current_field_widgets: dict[str, object] = {}
        self.last_range_ids = {"MAXID": "", "MINID": "", "MAXBT": ""}

        self.load_login_memory()
        self.build_login_view()

    def apply_window_icon(self) -> None:
        try:
            icon_path = save_temp_icon()
            self.iconbitmap(default=str(icon_path))
        except Exception:
            pass

    def configure_theme(self) -> None:
        self.option_add("*Font", "{Microsoft YaHei UI} 10")
        style = ttk.Style(self)
        THEME.apply_admin_ttk_theme(
            style,
            palette=ADMIN_TOOL_PALETTE,
            title_size=22,
            section_size=12,
            topbar_bg=BG_SURFACE,
            include_notebook=True,
            include_status=True,
            include_app_label=True,
            include_app_muted=True,
            include_card_labelframe=True,
            include_card_frame=True,
            include_card_inset=True,
        )

        style.configure("TRadiobutton", background=BG_SURFACE, foreground=FG_PRIMARY, font=("Microsoft YaHei UI", 10))

        style.configure("TNotebook", background=BG_APP, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background="#e8e8e8",
            foreground=FG_SECONDARY,
            padding=(14, 8),
            font=("Microsoft YaHei UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_SURFACE), ("active", "#f0f0f0")],
            foreground=[("selected", FG_PRIMARY), ("active", FG_PRIMARY)],
        )

        style.configure("TPanedwindow", background=BG_APP, sashwidth=8)

    @staticmethod
    def style_text_widget(widget: ScrolledText | None, *, height: int) -> None:
        if not widget:
            return
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

    def build_login_section_card(self, parent: ttk.Frame, title: str, *, expand: bool = False) -> ttk.Frame:
        shell = ttk.Frame(parent, style="App.TFrame", padding=4)
        shell.pack(fill=tk.BOTH if expand else tk.X, expand=expand, pady=(12, 0))

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
        return body

    def build_section_card(
        self,
        parent,
        title: str,
        *,
        expand: bool = False,
        fill=tk.X,
        pady=0,
    ) -> ttk.Frame:
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

        if isinstance(parent, ttk.Panedwindow):
            parent.add(shell, weight=1 if expand else 0)
        else:
            shell.pack(fill=fill, expand=expand, pady=pady)
        return body

    def clear_root(self) -> None:
        for child in self.winfo_children():
            child.destroy()

    def load_login_memory(self) -> None:
        saved = self.login_memory_service.load()
        if not saved:
            return

        self.account_var.set(str(saved.get("account", "")))
        self.password_var.set(str(saved.get("password", "")))
        self.lt_var.set(str(saved.get("lt", "web")) or "web")
        self.member_type_var.set(str(saved.get("member_type", "supplier")) or "supplier")

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
            "member_type": context.get("member_type", "supplier"),
            "environment_label": context.get("environment_label", "测试环境"),
            }
        )

    def build_login_view(self) -> None:
        self.clear_root()
        container = ttk.Frame(self, style="App.TFrame", padding=28)
        container.pack(fill=tk.BOTH, expand=True)

        hero_shell = ttk.Frame(container, style="App.TFrame", padding=4)
        hero_shell.pack(fill=tk.X)
        hero = ttk.Frame(hero_shell, style="CardInset.TFrame", padding=(28, 24))
        hero.pack(fill=tk.X)
        title = ttk.Label(hero, text="接口测试 Demo", style="Title.TLabel")
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            hero,
            text="DES/CBC/PKCS7/Base64/UTF-8 加解密，先登录再调试接口。登录成功后会自动记住账号密码。",
            style="Muted.TLabel",
        )
        subtitle.pack(anchor=tk.W, pady=(8, 0))

        form = self.build_login_section_card(container, "登录信息")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="账号").grid(row=0, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Entry(form, textvariable=self.account_var, width=48).grid(row=0, column=1, sticky=tk.EW, pady=8)

        ttk.Label(form, text="密码").grid(row=1, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Entry(form, textvariable=self.password_var, width=48, show="*").grid(row=1, column=1, sticky=tk.EW, pady=8)

        ttk.Label(form, text="会员类型").grid(row=2, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        member_frame = ttk.Frame(form)
        member_frame.grid(row=2, column=1, sticky=tk.W, pady=8)
        ttk.Radiobutton(member_frame, text="供货会员登录", variable=self.member_type_var, value="supplier").pack(
            side=tk.LEFT
        )
        ttk.Radiobutton(member_frame, text="经济会员登录", variable=self.member_type_var, value="broker").pack(
            side=tk.LEFT, padx=(16, 0)
        )

        ttk.Label(form, text="登录类型 LT").grid(row=3, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        lt_combo = ttk.Combobox(form, textvariable=self.lt_var, values=["pc", "web"], width=12, state="readonly")
        lt_combo.grid(row=3, column=1, sticky=tk.W, pady=8)

        ttk.Label(form, text="请求环境").grid(row=4, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        environment_values = [item.get("label", key) for key, item in self.environments.items()]
        environment_combo = ttk.Combobox(
            form,
            textvariable=self.environment_var,
            values=environment_values,
            width=18,
            state="readonly",
        )
        environment_combo.grid(row=4, column=1, sticky=tk.W, pady=8)
        environment_combo.configure(foreground=FG_PRIMARY)

        action_frame = ttk.Frame(form)
        action_frame.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(16, 0))
        ttk.Button(action_frame, text="登录", command=self.handle_login, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(action_frame, text="退出", command=self.destroy).pack(side=tk.LEFT, padx=(12, 0))

        notice = self.build_login_section_card(container, "说明", expand=True)
        ttk.Label(
            notice,
            justify=tk.LEFT,
            style="Muted.TLabel",
            text=(
                "1. 密码会按 1g6n8n8t / 1g6n8n8t 做 DES CBC PKCS7 加密。\n"
                "2. 登录成功后，左侧按会员类型展示已配置接口，右侧可直接改参数后提交。\n"
                "3. 当前已预置登录接口示例，后续接口可继续写入 config/interfaces.json。"
            ),
        ).pack(anchor=tk.W)

    def build_main_view(self) -> None:
        self.clear_root()

        app_container = ttk.Frame(self, style="App.TFrame", padding=(22, 18))
        app_container.pack(fill=tk.BOTH, expand=True)

        self.top_frame = ttk.Frame(app_container, style="Topbar.TFrame", padding=(20, 16))
        self.top_frame.pack(fill=tk.X)
        self.top_info_var.set(self.build_top_info_text())
        ttk.Label(self.top_frame, textvariable=self.top_info_var, style="Topbar.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        ttk.Button(self.top_frame, text="重新登录", command=self.build_login_view).pack(side=tk.RIGHT)

        meta_shell = ttk.Frame(app_container, style="App.TFrame", padding=4)
        meta_shell.pack(fill=tk.X, pady=(10, 12))
        meta_card = ttk.Frame(meta_shell, style="CardInset.TFrame", padding=(18, 14))
        meta_card.pack(fill=tk.X)
        encrypted_text = f"加密密码：{self.session_context['encrypted_password']}"
        ttk.Label(meta_card, text=encrypted_text, style="Muted.TLabel").pack(anchor=tk.W)
        self.endpoint_info_var.set(f"当前地址：{self.api_client.endpoint}")
        ttk.Label(meta_card, textvariable=self.endpoint_info_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(6, 0))

        body = ttk.Panedwindow(app_container, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body, style="App.TFrame", padding=(0, 0, 10, 0))
        right = ttk.Frame(body, style="App.TFrame", padding=(10, 0, 0, 0))
        body.add(left, weight=1)
        body.add(right, weight=4)

        self.build_interface_sidebar(left)
        self.build_right_panel(right)
        self.load_member_interfaces()

    def build_interface_sidebar(self, parent: ttk.Frame) -> None:
        sidebar_card = self.build_section_card(parent, "接口列表", expand=True, fill=tk.BOTH)
        list_container = ttk.Frame(sidebar_card, style="Surface.TFrame")
        list_container.pack(fill=tk.BOTH, expand=True)
        self.interface_listbox = tk.Listbox(
            list_container,
            exportselection=False,
            font=("Consolas", 10),
            bg=BG_MUTED,
            fg=FG_PRIMARY,
            selectbackground=ACCENT_DARK,
            selectforeground=BG_SURFACE,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
        )
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.interface_listbox.yview)
        self.interface_listbox.configure(yscrollcommand=scrollbar.set)
        self.interface_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.interface_listbox.bind("<<ListboxSelect>>", self.on_interface_selected)

    def build_right_panel(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        debug_tab = ttk.Frame(notebook, style="App.TFrame", padding=14)
        crypto_tab = ttk.Frame(notebook, style="App.TFrame", padding=14)
        notebook.add(debug_tab, text="接口调试")
        notebook.add(crypto_tab, text="加解密工具")

        self.build_debug_tab(debug_tab)
        self.build_crypto_tab(crypto_tab)

    def build_debug_tab(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="App.TFrame")
        header.pack(fill=tk.X)
        ttk.Label(header, textvariable=self.interface_name_var, style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(header, textvariable=self.interface_meta_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(6, 12))

        btn_frame = ttk.Frame(parent, style="App.TFrame")
        btn_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Button(btn_frame, text="恢复默认参数", command=self.reset_current_payload).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="刷新请求 JSON", command=self.refresh_payload_preview).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_frame, text="接口说明", command=self.open_interface_description_window).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_frame, text="弹出查看请求信息", command=self.open_request_window).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_frame, text="弹出查看返回结果", command=self.open_response_window).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_frame, text="提交接口", command=self.submit_current_interface, style="Primary.TButton").pack(side=tk.RIGHT)

        parameter_frame = self.build_section_card(parent, "固定请求参数")
        parameter_frame.columnconfigure(0, weight=1)

        form_header = ttk.Frame(parameter_frame, style="Surface.TFrame")
        form_header.grid(row=0, column=0, sticky=tk.EW)
        form_header.columnconfigure(1, weight=1)
        ttk.Label(form_header, text="参数值", style="Muted.TLabel").grid(row=0, column=1, sticky=tk.W, padx=(0, 8))
        ttk.Label(form_header, text="说明", style="Muted.TLabel").grid(row=0, column=2, sticky=tk.W)

        self.param_form_frame = ttk.Frame(parameter_frame, style="Surface.TFrame")
        self.param_form_frame.grid(row=1, column=0, sticky=tk.EW, pady=(8, 0))
        self.param_form_frame.columnconfigure(1, weight=1)

        preview_frame = self.build_section_card(parent, "请求 JSON 预览", pady=(8, 0))
        self.param_preview = ScrolledText(preview_frame, height=10, font=("Consolas", 10))
        self.param_preview.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.param_preview, height=10)

        ttk.Label(parent, textvariable=self.response_status_var, style="Status.TLabel").pack(anchor=tk.W, pady=(10, 10))

        result_shell = ttk.Frame(parent, style="App.TFrame", padding=4)
        result_shell.pack(fill=tk.BOTH, expand=True)
        result_pane = ttk.Panedwindow(result_shell, orient=tk.VERTICAL)
        result_pane.pack(fill=tk.BOTH, expand=True)

        request_frame = self.build_section_card(result_pane, "请求参数与请求信息", expand=True, fill=tk.BOTH)
        self.request_viewer = ScrolledText(request_frame, height=10, font=("Consolas", 10))
        self.request_viewer.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.request_viewer, height=10)

        response_frame = self.build_section_card(result_pane, "返回结果", expand=True, fill=tk.BOTH)
        self.response_viewer = ScrolledText(response_frame, height=22, font=("Consolas", 10))
        self.response_viewer.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.response_viewer, height=22)

    def build_crypto_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="加密与解密参数：DES / CBC / PKCS7 / 密码 1g6n8n8t / 偏移量 1g6n8n8t / Base64 / UTF-8",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        input_frame = self.build_section_card(parent, "原文或密文", expand=True, fill=tk.BOTH)
        self.encrypt_input = ScrolledText(input_frame, height=14, font=("Consolas", 10))
        self.encrypt_input.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.encrypt_input, height=14)

        btn_frame = ttk.Frame(parent, style="App.TFrame")
        btn_frame.pack(fill=tk.X, pady=12)
        ttk.Button(btn_frame, text="加密", command=self.encrypt_text, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="解密", command=self.decrypt_text).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_frame, text="清空", command=self.clear_crypto_text).pack(side=tk.LEFT, padx=(8, 0))

        output_frame = self.build_section_card(parent, "结果", expand=True, fill=tk.BOTH)
        self.encrypt_output = ScrolledText(output_frame, height=14, font=("Consolas", 10))
        self.encrypt_output.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.encrypt_output, height=14)

    def build_top_info_text(self) -> str:
        return (
            f"账号：{self.session_context['account']}    "
            f"密码：{self.session_context['password']}    "
            f"会员类型：{self.session_context['member_label']}    "
            f"LT：{self.session_context['lt']}    "
            f"环境：{self.session_context['environment_label']}    "
            f"登录时间：{self.session_context.get('login_time_text', '未记录')}"
        )

    def handle_login(self) -> None:
        context = self.build_login_context_from_inputs()
        if not context:
            return

        success, _ = self.request_login(context, show_error=True)
        if success:
            self.build_main_view()

    def build_login_context_from_inputs(self) -> dict | None:
        account = self.account_var.get().strip()
        password = self.password_var.get()
        member_type = self.member_type_var.get()
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
            "member_type": member_type,
            "member_label": MEMBER_LABELS.get(member_type, member_type),
            "lt": lt,
            "environment_key": environment_key,
            "environment_label": environment_label,
            "endpoint": endpoint,
        }

    def request_login(self, context: dict, show_error: bool = True) -> tuple[bool, dict | None]:
        self.api_client.set_endpoint(context["endpoint"])
        request_context = dict(context)
        request_context["encrypted_password"] = self.crypto_service.encrypt(request_context["password"])

        login_interface = self.interface_service.get_login_interface()
        payload = self.interface_service.apply_context(login_interface["params"], request_context)

        try:
            result = self.api_client.send_request(
                payload=payload,
                request_mode=login_interface.get("request_mode", "form"),
                method=login_interface.get("method", "POST"),
            )
        except Exception as exc:
            if show_error:
                messagebox.showerror("登录失败", f"请求登录接口时发生异常：\n{exc}")
            return False, None

        retcode = self.extract_retcode(result["response_json"])
        if result["status_code"] >= 400:
            if show_error:
                messagebox.showerror("登录失败", self.format_http_error(result))
            return False, result

        if self.is_negative_retcode(retcode):
            if show_error:
                error_message = self.error_code_service.get_message(retcode)
                raw_result = self.pretty_dump(result["response_json"] or result["response_text"])
                request_info = self.pretty_dump(
                    {
                        "url": result["url"],
                        "method": result["method"],
                        "request_mode": result["request_mode"],
                        "payload": result["request_payload"],
                        "request_body": result["request_body"],
                        "encrypted_password": request_context["encrypted_password"],
                    }
                )
                messagebox.showerror(
                    "登录失败",
                    f"错误码：{retcode}\n错误信息：{error_message}\n\n请求信息：\n{request_info}\n\n返回结果：\n{raw_result}",
                )
            return False, result

        now = datetime.now()
        request_context["login_user_u"] = self.extract_login_user(data=result["response_json"], fallback=request_context["account"])
        request_context["login_retcode"] = self.extract_login_retcode(result["response_json"])
        request_context["retcode"] = request_context["login_retcode"]
        request_context["encrypted_password"] = request_context["encrypted_password"]
        request_context["login_time"] = now
        request_context["login_time_text"] = now.strftime("%Y-%m-%d %H:%M:%S")
        request_context["login_result"] = result
        self.session_context = request_context
        self.api_client.set_endpoint(request_context["endpoint"])
        self.save_login_memory(request_context)
        return True, result

    def load_member_interfaces(self) -> None:
        member_type = self.session_context["member_type"]
        self.member_interfaces = self.interface_service.get_member_interfaces(member_type)

        if not self.interface_listbox:
            return

        self.interface_listbox.delete(0, tk.END)
        for item in self.member_interfaces:
            self.interface_listbox.insert(tk.END, f"{item['name']} - {item['display_name']}")

        if self.member_interfaces:
            self.interface_listbox.selection_set(0)
            self.on_interface_selected()
        else:
            self.interface_name_var.set("当前会员类型没有配置接口")
            self.interface_meta_var.set("请在 config/interfaces.json 中补充接口定义。")

    def get_active_environment_key(self) -> str:
        if self.session_context.get("environment_key"):
            return str(self.session_context["environment_key"])
        environment_label = self.environment_var.get().strip() or "测试环境"
        return ENVIRONMENT_LABEL_TO_KEY.get(environment_label, self.default_environment_key)

    def get_interface_endpoint(self, interface: dict) -> str:
        return self.interface_service.resolve_interface_endpoint(interface, self.get_active_environment_key())

    @staticmethod
    def interface_requires_login(interface: dict) -> bool:
        return interface.get("name") != "logon" and not bool(interface.get("no_login"))

    def on_interface_selected(self, _event=None) -> None:
        if not self.interface_listbox:
            return

        selection = self.interface_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        self.current_interface_index = index
        interface = self.member_interfaces[index]
        interface_endpoint = self.get_interface_endpoint(interface)
        self.api_client.set_endpoint(interface_endpoint)
        self.endpoint_info_var.set(f"当前地址：{interface_endpoint}")

        self.interface_name_var.set(f"{interface['display_name']} ({interface['name']})")
        self.interface_meta_var.set(
            f"请求地址：{interface_endpoint}    请求方式：{interface.get('method', 'POST')}    "
            f"提交模式：{interface.get('request_mode', 'form')}    说明：{interface.get('description', '')}"
        )
        self.reset_current_payload()
        self.show_saved_interface_result(interface)

    def reset_current_payload(self) -> None:
        if self.current_interface_index is None or not self.param_form_frame:
            return

        interface = self.member_interfaces[self.current_interface_index]
        self.render_interface_form(interface)

    def submit_current_interface(self) -> None:
        if self.current_interface_index is None:
            messagebox.showwarning("提示", "请先选择接口。")
            return

        interface = self.member_interfaces[self.current_interface_index]
        if self.interface_requires_login(interface) and not self.ensure_login_session():
            return

        payload = self.collect_current_payload(interface)
        if not self.validate_payload(interface, payload):
            return

        interface_endpoint = self.get_interface_endpoint(interface)
        self.api_client.set_endpoint(interface_endpoint)
        self.endpoint_info_var.set(f"当前地址：{interface_endpoint}")

        try:
            result = self.api_client.send_request(
                payload=payload,
                request_mode=interface.get("request_mode", "form"),
                method=interface.get("method", "POST"),
            )
        except Exception as exc:
            messagebox.showerror("请求失败", f"接口调用异常：\n{exc}")
            return

        retcode = self.extract_retcode(result["response_json"])
        retried = False
        if self.interface_requires_login(interface) and self.should_refresh_session(retcode):
            if self.ensure_login_session(force=True):
                self.refresh_dynamic_fields()
                payload = self.collect_current_payload(interface)
                if not self.validate_payload(interface, payload):
                    return
                interface_endpoint = self.get_interface_endpoint(interface)
                self.api_client.set_endpoint(interface_endpoint)
                self.endpoint_info_var.set(f"当前地址：{interface_endpoint}")
                try:
                    result = self.api_client.send_request(
                        payload=payload,
                        request_mode=interface.get("request_mode", "form"),
                        method=interface.get("method", "POST"),
                    )
                    retcode = self.extract_retcode(result["response_json"])
                    retried = True
                except Exception as exc:
                    messagebox.showerror("请求失败", f"会话续期后重试失败：\n{exc}")
                    return

        status_text = f"HTTP {result['status_code']}"
        if self.is_negative_retcode(retcode):
            error_message = self.error_code_service.get_message(retcode)
            status_text += f"    RETCODE：{retcode}    错误信息：{error_message}"
        elif retcode is not None:
            status_text += f"    RETCODE：{retcode}"
        else:
            status_text += "    未识别到 RETCODE"
        if retried:
            status_text += "    已自动续期后重试"

        self.render_http_result(result, status_text)

    def encrypt_text(self) -> None:
        if not self.encrypt_input:
            return

        plain_text = self.encrypt_input.get("1.0", tk.END).strip()
        if not plain_text:
            messagebox.showwarning("提示", "请输入需要加密的原文。")
            return

        encrypted_text = self.crypto_service.encrypt(plain_text)
        self.write_text(self.encrypt_output, encrypted_text)

    def decrypt_text(self) -> None:
        if not self.encrypt_input:
            return

        cipher_text = self.encrypt_input.get("1.0", tk.END).strip()
        if not cipher_text:
            messagebox.showwarning("提示", "请输入需要解密的密文。")
            return

        try:
            plain_text = self.crypto_service.decrypt(cipher_text)
        except Exception as exc:
            messagebox.showerror("解密失败", f"密文解密失败：\n{exc}")
            return

        self.write_text(self.encrypt_output, plain_text)

    def clear_crypto_text(self) -> None:
        self.write_text(self.encrypt_input, "")
        self.write_text(self.encrypt_output, "")

    def get_interface_fields(self, interface: dict) -> list[dict]:
        configured_fields = interface.get("fields")
        if configured_fields:
            return configured_fields

        fields = []
        for name, value in interface.get("params", {}).items():
            fields.append(
                {
                    "name": name,
                    "label": name,
                    "description": "",
                    "widget": "entry",
                    "default": value,
                }
            )
        return fields

    def render_interface_form(self, interface: dict) -> None:
        if not self.param_form_frame:
            return

        for child in self.param_form_frame.winfo_children():
            child.destroy()

        self.current_field_vars = {}
        self.current_field_meta = self.get_interface_fields(interface)
        self.current_field_widgets = {}

        for row_index, field in enumerate(self.current_field_meta):
            field_name = field["name"]
            default_value = self.resolve_default_value(field.get("default", ""))
            field_var = tk.StringVar(value=default_value)
            self.current_field_vars[field_name] = field_var

            ttk.Label(self.param_form_frame, text=field.get("label", field_name)).grid(
                row=row_index, column=0, sticky=tk.W, padx=(0, 8), pady=4
            )

            widget_type = field.get("widget", "entry")
            if widget_type == "select":
                options = [option.get("value", option.get("label", "")) for option in field.get("options", [])]
                widget = ttk.Combobox(
                    self.param_form_frame,
                    textvariable=field_var,
                    values=options,
                    state="readonly",
                    width=32,
                )
            elif widget_type == "date" and DateEntry is not None:
                initial_date = self.parse_date_text(default_value) or datetime.now().date()
                # ★ 使用自定义 DateEntry 子类修复导航按钮问题
                widget = self._create_fixed_date_entry(
                    self.param_form_frame,
                    field_var,
                    initial_date,
                    interface.get("name"),
                    field_name,
                )
            else:
                widget = ttk.Entry(self.param_form_frame, textvariable=field_var, width=42)
                if field.get("readonly"):
                    widget.configure(state="readonly")

            self.current_field_widgets[field_name] = widget
            widget.grid(row=row_index, column=1, sticky=tk.EW, padx=(0, 8), pady=4)
            ttk.Label(
                self.param_form_frame,
                text=field.get("description", ""),
                justify=tk.LEFT,
                wraplength=420,
                foreground="#666666",
            ).grid(row=row_index, column=2, sticky=tk.W, pady=4)
            field_var.trace_add("write", lambda *_args: self.refresh_payload_preview())

        helper_row = len(self.current_field_meta)
        if interface.get("name") in {
            "broker_trade_query",
            "broker_trade_history_query",
            "broker_order_query",
            "broker_order_history_query",
            "broker_delivery_query",
            "broker_delivery_history_query",
            "broker_transfer_query",
            "broker_transfer_history_query",
            "broker_block_query",
            "broker_block_history_query",
            "broker_cash_flow",
            "broker_cash_history_flow",
        }:
            ttk.Separator(self.param_form_frame, orient=tk.HORIZONTAL).grid(
                row=helper_row, column=0, columnspan=3, sticky=tk.EW, pady=(8, 8)
            )
            ttk.Label(
                self.param_form_frame,
                textvariable=self.form_helper_summary_var,
                foreground="#004b8d",
                justify=tk.LEFT,
                wraplength=820,
            ).grid(row=helper_row + 1, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))
            ttk.Label(
                self.param_form_frame,
                textvariable=self.form_helper_detail_var,
                foreground="#666666",
                justify=tk.LEFT,
                wraplength=820,
            ).grid(row=helper_row + 2, column=0, columnspan=3, sticky=tk.W, pady=(0, 6))

            helper_btn_frame = ttk.Frame(self.param_form_frame)
            helper_btn_frame.grid(row=helper_row + 3, column=0, columnspan=3, sticky=tk.W)
            ttk.Button(
                helper_btn_frame,
                text="LTI 填入上次 MAXID",
                command=lambda: self.fill_lti_from_range("MAXID"),
            ).pack(side=tk.LEFT)
            ttk.Button(
                helper_btn_frame,
                text="LTI 填入上次 MINID",
                command=lambda: self.fill_lti_from_range("MINID"),
            ).pack(side=tk.LEFT, padx=(8, 0))
        elif interface.get("name") == "broker_user_query":
            ttk.Separator(self.param_form_frame, orient=tk.HORIZONTAL).grid(
                row=helper_row, column=0, columnspan=3, sticky=tk.EW, pady=(8, 8)
            )
            ttk.Label(
                self.param_form_frame,
                textvariable=self.form_helper_summary_var,
                foreground="#004b8d",
                justify=tk.LEFT,
                wraplength=820,
            ).grid(row=helper_row + 1, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))
            ttk.Label(
                self.param_form_frame,
                textvariable=self.form_helper_detail_var,
                foreground="#666666",
                justify=tk.LEFT,
                wraplength=820,
            ).grid(row=helper_row + 2, column=0, columnspan=3, sticky=tk.W, pady=(0, 6))

            helper_btn_frame = ttk.Frame(self.param_form_frame)
            helper_btn_frame.grid(row=helper_row + 3, column=0, columnspan=3, sticky=tk.W)
            ttk.Button(
                helper_btn_frame,
                text="BT 填入上次 MAXBT",
                command=self.fill_bt_from_range,
            ).pack(side=tk.LEFT)

        self.update_form_runtime_hints(interface)
        self.apply_date_constraints(interface)
        self.refresh_payload_preview()

    def resolve_default_value(self, default_value):
        if isinstance(default_value, (dict, list)):
            resolved = self.interface_service.apply_context(default_value, self.build_context())
            return json.dumps(resolved, ensure_ascii=False)
        if isinstance(default_value, str):
            return self.interface_service.apply_context(default_value, self.build_context())
        if default_value is None:
            return ""
        return str(default_value)

    def build_context(self) -> dict:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        return {
            **self.session_context,
            "today": today.strftime("%Y-%m-%d"),
            "yesterday": yesterday.strftime("%Y-%m-%d"),
        }

    def refresh_dynamic_fields(self) -> None:
        for field in self.current_field_meta:
            default_value = field.get("default", "")
            if not isinstance(default_value, str) or "{{" not in default_value:
                continue
            if (
                field.get("readonly")
                or "login_retcode" in default_value
                or "retcode" in default_value
                or "login_user_u" in default_value
            ):
                self.current_field_vars[field["name"]].set(self.resolve_default_value(default_value))
        if self.current_interface_index is not None:
            self.apply_date_constraints(self.member_interfaces[self.current_interface_index])
        self.refresh_payload_preview()

    def collect_current_payload(self, interface: dict) -> dict:
        payload = self.interface_service.apply_context(dict(interface.get("params", {})), self.build_context())
        for field in self.current_field_meta:
            payload[field["name"]] = self.current_field_vars[field["name"]].get().strip()
        return payload

    def refresh_payload_preview(self) -> None:
        if self.current_interface_index is None or not self.param_preview:
            return
        interface = self.member_interfaces[self.current_interface_index]
        self.update_form_runtime_hints(interface)
        payload = self.collect_current_payload(interface)
        self.write_text(self.param_preview, self.pretty_dump(payload))

    def on_date_changed(self, interface_name: str, changed_name: str) -> None:
        if self.current_interface_index is None:
            return
        interface = self.member_interfaces[self.current_interface_index]
        if interface.get("name") != interface_name:
            return
        self.apply_date_constraints(interface, changed_name=changed_name)
        self.refresh_payload_preview()

    def apply_date_constraints(self, interface: dict, changed_name: str | None = None) -> None:
        date_range = self.get_interface_date_range(interface)
        if not date_range or DateEntry is None:
            return

        start_field = date_range["start"]
        end_field = date_range["end"]
        max_months = date_range["max_months"]

        start_widget = self.current_field_widgets.get(start_field)
        end_widget = self.current_field_widgets.get(end_field)
        start_var = self.current_field_vars.get(start_field)
        end_var = self.current_field_vars.get(end_field)
        if not start_widget or not end_widget or not start_var or not end_var:
            return

        today = datetime.now().date()
        start_date = self.parse_date_text(start_var.get()) or today
        if start_date > today:
            start_date = today
        start_widget.configure(maxdate=today)
        if start_var.get() != start_date.strftime("%Y-%m-%d"):
            start_var.set(start_date.strftime("%Y-%m-%d"))
        start_widget.set_date(start_date)

        max_end_date = min(today, self.add_months(start_date, max_months))
        preferred_end_date = self.get_default_end_date(start_date, max_end_date)
        current_end_date = self.parse_date_text(end_var.get())
        if current_end_date is None:
            current_end_date = preferred_end_date

        if current_end_date < start_date or current_end_date > max_end_date:
            current_end_date = preferred_end_date
        elif changed_name == start_field and current_end_date > max_end_date:
            current_end_date = preferred_end_date

        end_widget.configure(mindate=start_date, maxdate=max_end_date)
        if end_var.get() != current_end_date.strftime("%Y-%m-%d"):
            end_var.set(current_end_date.strftime("%Y-%m-%d"))
        end_widget.set_date(current_end_date)

    @staticmethod
    def get_interface_date_range(interface: dict) -> dict | None:
        configured = interface.get("date_range")
        if isinstance(configured, dict):
            start_field = str(configured.get("start", "")).strip()
            end_field = str(configured.get("end", "")).strip()
            if not start_field or not end_field:
                return None
            try:
                max_months = int(configured.get("max_months", 3))
            except (TypeError, ValueError):
                max_months = 3
            return {
                "start": start_field,
                "end": end_field,
                "max_months": max_months,
            }

        if interface.get("name") in {
            "broker_trade_history_query",
            "broker_order_history_query",
            "broker_delivery_history_query",
            "broker_transfer_history_query",
            "broker_block_history_query",
            "broker_cash_history_flow",
        }:
            return {"start": "SDT", "end": "EDT", "max_months": 3}
        return None

    @staticmethod
    def get_default_end_date(start_date, max_end_date):
        yesterday = datetime.now().date() - timedelta(days=1)
        if start_date <= yesterday <= max_end_date:
            return yesterday
        return max_end_date

    def update_form_runtime_hints(self, interface: dict) -> None:
        if interface.get("name") not in {
            "broker_trade_query",
            "broker_trade_history_query",
            "broker_order_query",
            "broker_order_history_query",
            "broker_delivery_query",
            "broker_delivery_history_query",
            "broker_transfer_query",
            "broker_transfer_history_query",
            "broker_block_query",
            "broker_block_history_query",
            "broker_cash_flow",
            "broker_cash_history_flow",
            "broker_user_query",
        }:
            self.form_helper_summary_var.set("")
            self.form_helper_detail_var.set("")
            return

        if interface.get("name") == "broker_user_query":
            max_bt = self.last_range_ids.get("MAXBT", "") or "暂无"
            self.form_helper_summary_var.set("当前是客户列表增量查询模式：第一次 BT 传 0，后续查询建议使用上次返回的 MAXBT。")
            self.form_helper_detail_var.set(f"上次返回基准时间：MAXBT = {max_bt}")
            return

        rec_cnt_raw = self.current_field_vars.get("RECCNT", tk.StringVar(value="")).get().strip()
        try:
            rec_cnt = int(rec_cnt_raw or "0")
        except ValueError:
            rec_cnt = 0

        if rec_cnt > 0:
            mode_text = "当前是查最新记录模式：记录号 > LTI。继续向后查最新数据时，LTI 建议使用上次返回的 MAXID。"
        elif rec_cnt < 0:
            mode_text = "当前是查历史记录模式：记录号 < LTI。继续向前翻历史数据时，LTI 建议使用上次返回的 MINID。"
        else:
            mode_text = "RECCNT 不能为 0。大于 0 查最新记录，小于 0 查之前记录。"

        max_id = self.last_range_ids.get("MAXID", "") or "暂无"
        min_id = self.last_range_ids.get("MINID", "") or "暂无"
        self.form_helper_summary_var.set(mode_text)
        self.form_helper_detail_var.set(f"上次返回范围：MAXID = {max_id}，MINID = {min_id}")

    def validate_payload(self, interface: dict, payload: dict) -> bool:
        date_range = self.get_interface_date_range(interface)
        if date_range:
            return self.validate_history_query_payload(
                payload,
                date_range["start"],
                date_range["end"],
                date_range["max_months"],
            )
        return True

    def validate_history_query_payload(self, payload: dict, start_field: str, end_field: str, max_months: int) -> bool:
        start_text = str(payload.get(start_field, "")).strip()
        end_text = str(payload.get(end_field, "")).strip()
        if not start_text or not end_text:
            messagebox.showwarning("提示", "开始时间和结束时间不能为空。")
            return False

        try:
            start_date = datetime.strptime(start_text, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_text, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showwarning("提示", "日期格式必须为 YYYY-MM-DD，例如 2020-12-12。")
            return False

        if end_date < start_date:
            messagebox.showwarning("提示", "结束时间不能早于开始时间。")
            return False

        limit_date = self.add_months(start_date, max_months)
        if end_date > limit_date:
            messagebox.showwarning("提示", f"开始时间与结束时间区间不能超过 {max_months} 个月。")
            return False

        return True

    @staticmethod
    def add_months(source_date, months: int):
        month_index = source_date.month - 1 + months
        year = source_date.year + month_index // 12
        month = month_index % 12 + 1
        month_lengths = [31, 29 if ApiDemoWindow.is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        day = min(source_date.day, month_lengths[month - 1])
        return source_date.replace(year=year, month=month, day=day)

    @staticmethod
    def is_leap_year(year: int) -> bool:
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    @staticmethod
    def parse_date_text(value: str):
        try:
            return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def _create_fixed_date_entry(self, parent, textvariable, initial_date, interface_name, field_name):
        """★ 创建修复版的 DateEntry，解决三个问题：
        1. 点击输入框也能弹出日历
        2. 上个月/下个月按钮不会导致弹窗关闭
        3. 中文界面
        """
        from tkcalendar import Calendar

        # 主容器
        container = tk.Frame(parent)

        # 输入框 + 下拉按钮
        entry = ttk.Entry(container, textvariable=textvariable, width=30)
        entry.pack(side="left", fill="x", expand=True)

        btn = ttk.Button(container, text="▼", width=2)
        btn.pack(side="left", padx=(2, 0))

        # 日历弹窗
        cal_window = None
        cal = None

        def show_calendar():
            nonlocal cal_window, cal
            if cal_window is not None and cal_window.winfo_exists():
                cal_window.destroy()
                cal_window = None
                return

            # 解析当前日期
            try:
                current = datetime.strptime(textvariable.get(), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                current = datetime.now().date()

            # 创建弹窗
            cal_window = tk.Toplevel(container)
            cal_window.withdraw()  # 先隐藏，定位后再显示
            cal_window.overrideredirect(True)  # 无边框
            cal_window.transient(container.winfo_toplevel())

            # 中文月份和星期
            cal = Calendar(
                cal_window,
                selectmode="day",
                year=current.year,
                month=current.month,
                day=current.day,
                date_pattern="yyyy-mm-dd",
                locale='zh_CN',
                font=("Microsoft YaHei", 9),
                background="#ffffff",
                foreground="#333333",
                selectbackground="#0078d4",
                selectforeground="#ffffff",
                normalbackground="#ffffff",
                normalforeground="#333333",
                weekendbackground="#f5f5f5",
                weekendforeground="#333333",
                headersbackground="#f0f0f0",
                headersforeground="#333333",
            )
            cal.pack(padx=2, pady=2)

            # 定位到输入框下方
            container.update_idletasks()
            x = container.winfo_rootx()
            y = container.winfo_rooty() + container.winfo_height()
            cal_window.geometry(f"+{x}+{y}")
            cal_window.deiconify()

            # 选择日期后关闭
            def on_select(event=None):
                # 必须声明 nonlocal：否则下面的赋值会让 cal_window 被当作闭包局部变量，
                # 导致上一行 cal_window.destroy() 抛 UnboundLocalError
                nonlocal cal_window
                selected = cal.get_date()
                textvariable.set(selected)
                cal_window.destroy()
                cal_window = None
                # 触发回调
                self.on_date_changed(interface_name, field_name)

            cal.bind("<<CalendarSelected>>", on_select)

            # 点击外部关闭
            def on_click_outside(event):
                if cal_window is None or not cal_window.winfo_exists():
                    return
                # 检查点击位置是否在日历窗口外
                x, y = event.x_root, event.y_root
                cal_x = cal_window.winfo_rootx()
                cal_y = cal_window.winfo_rooty()
                cal_w = cal_window.winfo_width()
                cal_h = cal_window.winfo_height()
                if not (cal_x <= x <= cal_x + cal_w and cal_y <= y <= cal_y + cal_h):
                    cal_window.destroy()

            # 绑定到顶层窗口
            container.winfo_toplevel().bind("<Button-1>", on_click_outside, add="+")

        btn.config(command=show_calendar)
        entry.bind("<Button-1>", lambda e: (show_calendar(), "break")[1])

        return container

    def fill_lti_from_range(self, key: str) -> None:
        lti_var = self.current_field_vars.get("LTI")
        target_value = self.last_range_ids.get(key, "")
        if not lti_var:
            return
        if not target_value:
            messagebox.showwarning("提示", f"当前还没有可用的 {key}，请先成功查询一次成交记录。")
            return
        lti_var.set(str(target_value))

    def fill_bt_from_range(self) -> None:
        bt_var = self.current_field_vars.get("BT")
        target_value = self.last_range_ids.get("MAXBT", "")
        if not bt_var:
            return
        if not target_value:
            messagebox.showwarning("提示", "当前还没有可用的 MAXBT，请先成功查询一次客户列表。")
            return
        bt_var.set(str(target_value))

    def ensure_login_session(self, force: bool = False) -> bool:
        if not self.session_context:
            messagebox.showwarning("提示", "当前没有可用登录态，请先重新登录。")
            return False

        login_time = self.session_context.get("login_time")
        if not force and isinstance(login_time, datetime) and datetime.now() - login_time < SESSION_REFRESH_WINDOW:
            return True

        refresh_context = {
            "account": self.session_context["account"],
            "password": self.session_context["password"],
            "member_type": self.session_context["member_type"],
            "member_label": self.session_context["member_label"],
            "lt": self.session_context["lt"],
            "environment_key": self.session_context["environment_key"],
            "environment_label": self.session_context["environment_label"],
            "endpoint": self.session_context["endpoint"],
        }
        success, _ = self.request_login(refresh_context, show_error=False)
        if not success:
            messagebox.showwarning("登录已失效", "登录 RETCODE 已失效，请重新登录。")
            return False

        self.top_info_var.set(self.build_top_info_text())
        self.endpoint_info_var.set(f"当前地址：{self.api_client.endpoint}")
        self.refresh_dynamic_fields()
        return True

    def should_refresh_session(self, retcode) -> bool:
        return str(retcode) in SESSION_EXPIRE_CODES

    def show_saved_interface_result(self, interface: dict) -> None:
        if interface.get("name") == "logon" and self.session_context.get("login_result"):
            self.render_http_result(self.session_context["login_result"])
            return

        self.response_status_var.set("等待提交接口请求")
        self.write_text(self.request_viewer, "")
        self.write_text(self.response_viewer, "")
        self.update_form_runtime_hints(interface)

    def open_response_window(self) -> None:
        self.open_text_window("返回结果大图查看", self.response_viewer)

    def open_request_window(self) -> None:
        self.open_text_window("请求参数与请求信息大图查看", self.request_viewer)

    def open_interface_description_window(self) -> None:
        interface = self.get_current_interface()
        if not interface:
            messagebox.showwarning("提示", "请先选择接口。")
            return

        description = interface.get("response_description")
        if isinstance(description, list):
            content = "\n".join(str(item) for item in description)
        elif isinstance(description, str):
            content = description
        else:
            content = "当前接口暂未配置返回包说明。"

        # 调试：确保内容不为空
        if not content.strip():
            content = "（该接口暂无说明文档）"

        self.open_text_window(f"{interface.get('display_name', interface.get('name', '接口'))} - 接口说明", None, content)

    def get_current_interface(self) -> dict | None:
        if self.current_interface_index is None:
            return None
        if self.current_interface_index < 0 or self.current_interface_index >= len(self.member_interfaces):
            return None
        return self.member_interfaces[self.current_interface_index]

    def open_text_window(self, title: str, source_widget: ScrolledText | None, content_override: str | None = None) -> None:
        """打开文本查看窗口，支持 Markdown 风格的高亮渲染"""
        result_window = tk.Toplevel(self)
        result_window.title(title)
        result_window.geometry("1080x760")
        result_window.minsize(800, 600)
        result_window.configure(bg="#ffffff")
        result_window.transient(self)
        result_window.grab_set()

        # 使用 ScrolledText 简化布局
        from tkinter.scrolledtext import ScrolledText
        viewer = ScrolledText(
            result_window,
            font=("Consolas", 11),
            bg="#ffffff",
            fg="#000000",
            wrap=tk.WORD,
            padx=16,
            pady=16,
            relief=tk.FLAT,
            highlightthickness=0
        )
        viewer.pack(fill=tk.BOTH, expand=True)

        # 定义色彩标签
        viewer.tag_config("h1", font=("Microsoft YaHei UI", 16, "bold"), foreground="#1a1a2e", spacing1=12, spacing3=8)
        viewer.tag_config("h2", font=("Microsoft YaHei UI", 14, "bold"), foreground="#16213e", spacing1=10, spacing3=6)
        viewer.tag_config("h3", font=("Microsoft YaHei UI", 12, "bold"), foreground="#0f3460", spacing1=8, spacing3=4)
        viewer.tag_config("code", font=("Consolas", 10), foreground="#e94560", background="#fff5f5")
        viewer.tag_config("code_block", font=("Consolas", 10), foreground="#495057", background="#f1f3f5")
        viewer.tag_config("bold", font=("Consolas", 11, "bold"), foreground="#212529")
        viewer.tag_config("italic", font=("Consolas", 11, "italic"), foreground="#6c757d")
        viewer.tag_config("link", foreground="#0066cc", underline=True)
        viewer.tag_config("bullet", foreground="#e94560", font=("Consolas", 11, "bold"))
        viewer.tag_config("success", foreground="#28a745", font=("Consolas", 11, "bold"))
        viewer.tag_config("error", foreground="#dc3545", font=("Consolas", 11, "bold"))
        viewer.tag_config("warning", foreground="#ffc107", font=("Consolas", 11, "bold"))
        viewer.tag_config("info", foreground="#17a2b8", font=("Consolas", 11, "bold"))
        viewer.tag_config("key", foreground="#0f3460", font=("Consolas", 11, "bold"))
        viewer.tag_config("string", foreground="#28a745")
        viewer.tag_config("number", foreground="#fd7e14")
        viewer.tag_config("boolean", foreground="#e94560")
        viewer.tag_config("null", foreground="#6c757d")

        # 获取内容
        if content_override is not None:
            content = content_override
        elif source_widget is not None:
            content = source_widget.get("1.0", tk.END).strip()
        else:
            content = ""

        # 根据窗口类型决定渲染方式
        if not content or not content.strip():
            viewer.insert(tk.END, "（无内容）")
        elif "接口说明" in title:
            self._render_markdown(viewer, content)
        elif "请求" in title:
            self._render_json_with_highlight(viewer, content)
        elif "返回" in title or "响应" in title:
            self._render_json_with_highlight(viewer, content)
        else:
            viewer.insert(tk.END, content)
        
        viewer.config(state=tk.DISABLED)

    def _render_markdown(self, viewer: tk.Text, content: str) -> None:
        """渲染 Markdown 风格的内容"""
        # 先直接插入全部内容，确保能显示
        viewer.insert(tk.END, content)

    def _render_json_with_highlight(self, viewer: tk.Text, content: str) -> None:
        """渲染 JSON 并高亮键值对"""
        import json
        import re

        try:
            # 尝试解析并美化 JSON
            data = json.loads(content)
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            formatted = content

        # 简单的语法高亮
        lines = formatted.split('\n')
        for line in lines:
            # 键（冒号前的部分）
            key_match = re.match(r'^(\s*)("[^"]+")(:)', line)
            if key_match:
                viewer.insert(tk.END, key_match.group(1))  # 缩进
                viewer.insert(tk.END, key_match.group(2), "key")  # 键名
                viewer.insert(tk.END, key_match.group(3))  # 冒号
                rest = line[key_match.end():]

                # 值部分的高亮
                rest_stripped = rest.strip()
                if rest_stripped.startswith('"'):
                    viewer.insert(tk.END, rest, "string")
                elif rest_stripped in ('true', 'false'):
                    viewer.insert(tk.END, rest, "boolean")
                elif rest_stripped == 'null':
                    viewer.insert(tk.END, rest, "null")
                elif re.match(r'^-?\d', rest_stripped):
                    viewer.insert(tk.END, rest, "number")
                else:
                    viewer.insert(tk.END, rest)
            else:
                # 括号高亮
                for char in line:
                    if char in '{}[]':
                        viewer.insert(tk.END, char, "bold")
                    else:
                        viewer.insert(tk.END, char)
            viewer.insert(tk.END, '\n')

    def render_http_result(self, result: dict, status_text: str | None = None) -> None:
        retcode = self.extract_retcode(result["response_json"])

        if status_text is None:
            status_text = f"HTTP {result['status_code']}"
            if self.is_negative_retcode(retcode):
                error_message = self.error_code_service.get_message(retcode)
                status_text += f"    RETCODE：{retcode}    错误信息：{error_message}"
            elif retcode is not None:
                status_text += f"    RETCODE：{retcode}"
            else:
                status_text += "    未识别到 RETCODE"

        self.response_status_var.set(status_text)

        request_output = self.pretty_dump(
            {
                "url": result["url"],
                "method": result["method"],
                "request_mode": result["request_mode"],
                "headers": result["request_headers"],
                "payload": result["request_payload"],
                "request_body": result["request_body"],
            }
        )
        response_output = self.pretty_dump(
            {
                "status_code": result["status_code"],
                "headers": result["response_headers"],
                "retcode": retcode,
                "error_message": self.error_code_service.get_message(retcode) if self.is_negative_retcode(retcode) else "",
                "body": result["response_json"] if result["response_json"] is not None else result["response_text"],
            }
        )

        range_ids = self.extract_range_ids(result["response_json"])
        if range_ids["MAXID"]:
            self.last_range_ids["MAXID"] = range_ids["MAXID"]
        if range_ids["MINID"]:
            self.last_range_ids["MINID"] = range_ids["MINID"]
        if range_ids["MAXBT"]:
            self.last_range_ids["MAXBT"] = range_ids["MAXBT"]
        if self.current_interface_index is not None:
            self.update_form_runtime_hints(self.member_interfaces[self.current_interface_index])

        self.write_text(self.request_viewer, request_output)
        self.write_text(self.response_viewer, response_output)

    @staticmethod
    def extract_login_retcode(data):
        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                for key in ("RETCODE", "retCode", "returnCode", "code"):
                    if key in result:
                        return result[key]
            return ApiDemoWindow.extract_retcode(data)

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
                extracted = ApiDemoWindow.extract_login_user(value, "")
                if extracted:
                    return extracted
        if isinstance(data, list):
            for item in data:
                extracted = ApiDemoWindow.extract_login_user(item, "")
                if extracted:
                    return extracted
        return fallback

    @staticmethod
    def extract_range_ids(data) -> dict[str, str]:
        found = {"MAXID": "", "MINID": "", "MAXBT": ""}
        ApiDemoWindow.walk_range_ids(data, found)
        return found

    @staticmethod
    def walk_range_ids(data, found: dict[str, str]) -> None:
        if isinstance(data, dict):
            for key in ("MAXID", "maxId", "MaxID"):
                value = data.get(key)
                if value not in (None, ""):
                    found["MAXID"] = str(value)
                    break
            for key in ("MINID", "minId", "MinID"):
                value = data.get(key)
                if value not in (None, ""):
                    found["MINID"] = str(value)
                    break
            for key in ("MAXBT", "maxBt", "MaxBT"):
                value = data.get(key)
                if value not in (None, ""):
                    found["MAXBT"] = str(value)
                    break
            for value in data.values():
                if (found["MAXID"] and found["MINID"]) or found["MAXBT"]:
                    return
                ApiDemoWindow.walk_range_ids(value, found)
        elif isinstance(data, list):
            for item in data:
                if (found["MAXID"] and found["MINID"]) or found["MAXBT"]:
                    return
                ApiDemoWindow.walk_range_ids(item, found)

    @staticmethod
    def write_text(widget: ScrolledText | None, content: str) -> None:
        if not widget:
            return
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, content)

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
    def extract_retcode(data):
        if isinstance(data, dict):
            for key in ("RETCODE", "retCode", "returnCode", "code"):
                if key in data:
                    return data[key]
            for value in data.values():
                result = ApiDemoWindow.extract_retcode(value)
                if result is not None:
                    return result
        if isinstance(data, list):
            for item in data:
                result = ApiDemoWindow.extract_retcode(item)
                if result is not None:
                    return result
        return None

    @staticmethod
    def is_negative_retcode(retcode) -> bool:
        if retcode is None:
            return False
        try:
            return int(str(retcode)) < 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def format_http_error(result: dict) -> str:
        body = result["response_json"] if result["response_json"] is not None else result["response_text"]
        return (
            f"HTTP 状态码：{result['status_code']}\n"
            f"请求地址：{result['url']}\n\n"
            f"返回内容：\n{ApiDemoWindow.pretty_dump(body)}"
        )


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    window = ApiDemoWindow(root)
    window.mainloop()
