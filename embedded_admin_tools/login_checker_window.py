import json
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .services.api_client import ApiClient
from .services.crypto_service import DESCryptoService
from .services.error_code_service import ErrorCodeService
from .services.icon_service import save_temp_icon
from .services.interface_service import InterfaceService
from .services.login_memory_service import LoginMemoryService
from ui_theme import ADMIN_TOOL_PALETTE, THEME


MEMBER_LABELS = {
    "supplier": "供货会员",
    "broker": "经济会员",
}

ENVIRONMENT_LABEL_TO_KEY = {
    "测试环境": "test",
    "正式环境": "prod",
}

BG_APP = ADMIN_TOOL_PALETTE.bg
BG_SURFACE = ADMIN_TOOL_PALETTE.surface
BG_MUTED = ADMIN_TOOL_PALETTE.surface_alt
FG_PRIMARY = ADMIN_TOOL_PALETTE.text_primary
FG_SECONDARY = ADMIN_TOOL_PALETTE.text_secondary
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


class LoginCheckerWindow(tk.Toplevel):
    def __init__(self, master=None) -> None:
        super().__init__(master)
        self.title("登录连通性检测工具")
        self.geometry("1180x860")
        self.minsize(1040, 760)
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
        self.member_type_var = tk.StringVar(value="supplier")
        self.environment_var = tk.StringVar(
            value=self.environments.get(self.default_environment_key, {}).get("label", "测试环境")
        )

        self.summary_var = tk.StringVar(value="输入账号密码后点击登录，用于快速验证账号可用性和接口连通性。")
        self.request_viewer: ScrolledText | None = None
        self.response_viewer: ScrolledText | None = None
        self.description_viewer: ScrolledText | None = None

        self.load_login_memory()
        self.configure_theme()
        self.apply_window_icon()
        self.build_login_view()

    def configure_theme(self) -> None:
        self.option_add("*Font", "{Microsoft YaHei UI} 10")
        style = ttk.Style(self)
        THEME.apply_admin_ttk_theme(
            style,
            palette=ADMIN_TOOL_PALETTE,
            title_size=22,
            section_size=12,
            topbar_bg=BG_SURFACE,
            include_notebook=False,
            include_status=False,
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
    def style_text_widget(widget: ScrolledText) -> None:
        widget.configure(
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

        if isinstance(parent, ttk.Panedwindow):
            parent.add(shell, weight=1 if expand else 0)
        else:
            shell.pack(fill=fill, expand=expand)
        return body

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

        hero = self.build_section_card(container, "登录检测")
        ttk.Label(hero, text="登录连通性检测工具", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            hero,
            text="仅用于测试账号能否登录、环境是否连通，以及查看登录请求和返回内容。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))

        form = self.build_section_card(container, "登录参数")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="账号").grid(row=0, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Entry(form, textvariable=self.account_var, width=44).grid(row=0, column=1, sticky=tk.EW, pady=10)

        ttk.Label(form, text="密码").grid(row=1, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Entry(form, textvariable=self.password_var, width=44, show="*").grid(row=1, column=1, sticky=tk.EW, pady=10)

        ttk.Label(form, text="会员类型").grid(row=2, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        member_frame = ttk.Frame(form)
        member_frame.grid(row=2, column=1, sticky=tk.W, pady=10)
        ttk.Radiobutton(member_frame, text="供货会员登录", variable=self.member_type_var, value="supplier").pack(side=tk.LEFT)
        ttk.Radiobutton(member_frame, text="经济会员登录", variable=self.member_type_var, value="broker").pack(
            side=tk.LEFT,
            padx=(16, 0),
        )

        ttk.Label(form, text="登录类型 LT").grid(row=3, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Combobox(form, textvariable=self.lt_var, values=["web", "pc"], width=12, state="readonly").grid(
            row=3,
            column=1,
            sticky=tk.W,
            pady=10,
        )

        ttk.Label(form, text="请求环境").grid(row=4, column=0, sticky=tk.W, padx=(0, 16), pady=10)
        ttk.Combobox(
            form,
            textvariable=self.environment_var,
            values=[item.get("label", key) for key, item in self.environments.items()],
            width=18,
            state="readonly",
        ).grid(row=4, column=1, sticky=tk.W, pady=10)

        action_frame = ttk.Frame(form)
        action_frame.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(16, 0))
        ttk.Button(action_frame, text="登录检测", command=self.handle_login, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(action_frame, text="退出", command=self.destroy).pack(side=tk.LEFT, padx=(14, 0))

        notice = self.build_section_card(container, "说明", expand=True, fill=tk.BOTH)
        ttk.Label(
            notice,
            justify=tk.LEFT,
            style="Muted.TLabel",
            text=(
                "1. 密码按 1g6n8n8t / 1g6n8n8t 做 DES CBC PKCS7 Base64 加密。\n"
                "2. 点击登录后，仅校验登录接口本身，不展示其他业务接口。\n"
                "3. 登录成功后会进入独立结果页，展示请求信息、返回信息和接口说明。"
            ),
        ).pack(anchor=tk.W)

    def build_result_view(self, context: dict, result: dict) -> None:
        self.clear_root()
        container = ttk.Frame(self, style="App.TFrame", padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        header = self.build_section_card(container, "登录结果")
        ttk.Label(header, text="登录成功", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text=(
                f"账号：{context['account']}    "
                f"会员类型：{MEMBER_LABELS.get(context['member_type'], context['member_type'])}    "
                f"LT：{context['lt']}    "
                f"环境：{context['environment_label']}"
            ),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(6, 0))

        button_bar = ttk.Frame(container, style="App.TFrame")
        button_bar.pack(fill=tk.X, pady=(12, 12))
        ttk.Button(button_bar, text="返回重新登录", command=self.build_login_view).pack(side=tk.LEFT)
        ttk.Button(button_bar, text="退出", command=self.destroy).pack(side=tk.LEFT, padx=(10, 0))

        self.summary_var.set(f"登录成功，RETCODE：{self.extract_retcode(result.get('response_json'))}")
        ttk.Label(container, textvariable=self.summary_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 10))

        body = ttk.Panedwindow(container, orient=tk.VERTICAL)
        body.pack(fill=tk.BOTH, expand=True)

        request_frame = self.build_section_card(body, "请求信息", expand=True, fill=tk.BOTH)
        self.request_viewer = ScrolledText(request_frame, height=12)
        self.request_viewer.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.request_viewer)

        response_frame = self.build_section_card(body, "返回信息", expand=True, fill=tk.BOTH)
        self.response_viewer = ScrolledText(response_frame, height=14)
        self.response_viewer.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.response_viewer)

        description_frame = self.build_section_card(body, "接口说明", expand=True, fill=tk.BOTH)
        self.description_viewer = ScrolledText(description_frame, height=14)
        self.description_viewer.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.description_viewer)

        request_info = {
            "url": result["url"],
            "method": result["method"],
            "request_mode": result["request_mode"],
            "headers": result["request_headers"],
            "payload": result["request_payload"],
            "request_body": result["request_body"],
            "encrypted_password": context["encrypted_password"],
        }
        response_info = {
            "status_code": result["status_code"],
            "headers": result["response_headers"],
            "retcode": self.extract_retcode(result["response_json"]),
            "error_message": "",
            "body": result["response_json"] if result["response_json"] is not None else result["response_text"],
        }

        self.write_text(self.request_viewer, self.pretty_dump(request_info))
        self.write_text(self.response_viewer, self.pretty_dump(response_info))
        self.write_text(self.description_viewer, self.get_login_description())

    def build_login_context_from_inputs(self) -> dict | None:
        account = self.account_var.get().strip()
        password = self.password_var.get()
        lt = self.lt_var.get().strip() or "web"
        member_type = self.member_type_var.get()
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
            "member_type": member_type,
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

        self.save_login_memory(context)
        messagebox.showinfo("登录成功", "登录成功，已切换到结果页。")
        self.build_result_view(context, result)

    def get_login_description(self) -> str:
        description = self.login_interface.get("response_description")
        if isinstance(description, list) and description:
            return "\n".join(str(item) for item in description)

        for member_type in ("supplier", "broker"):
            for interface in self.interface_service.get_member_interfaces(member_type):
                if interface.get("name") == "logon":
                    member_description = interface.get("response_description")
                    if isinstance(member_description, list) and member_description:
                        return "\n".join(str(item) for item in member_description)
                    if isinstance(member_description, str) and member_description.strip():
                        return member_description

        return "\n".join(LOGIN_RESPONSE_DESCRIPTION)

    @staticmethod
    def extract_retcode(data):
        if isinstance(data, dict):
            for key in ("RETCODE", "retCode", "returnCode", "code"):
                if key in data:
                    return data[key]
            for value in data.values():
                result = LoginCheckerWindow.extract_retcode(value)
                if result is not None:
                    return result
        if isinstance(data, list):
            for item in data:
                result = LoginCheckerWindow.extract_retcode(item)
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
            f"返回结果：\n{LoginCheckerWindow.pretty_dump(response_body)}"
        )


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    window = LoginCheckerWindow(root)
    window.mainloop()
