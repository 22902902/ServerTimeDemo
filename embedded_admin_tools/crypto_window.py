import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .services.crypto_service import DESCryptoService
from .services.icon_service import save_temp_icon
from ui_theme import ADMIN_TOOL_PALETTE, THEME


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

LANGUAGE_GUIDES = {
    "Python": {
        "library": "推荐库：pycryptodome",
        "tips": [
            "直接使用 DES CBC + pad/unpad 即可，和当前桌面工具完全一致。",
            "明文先按 UTF-8 编码，加密结果再做 Base64。",
            "如果解密报填充错误，优先检查密钥、偏移量和 Base64 是否一致。",
        ],
        "code": """from Crypto.Cipher import DES
from Crypto.Util.Padding import pad, unpad
import base64

KEY = b"1g6n8n8t"
IV = b"1g6n8n8t"

def encrypt(text: str) -> str:
    cipher = DES.new(KEY, DES.MODE_CBC, IV)
    encrypted = cipher.encrypt(pad(text.encode("utf-8"), DES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")

def decrypt(cipher_text: str) -> str:
    raw = base64.b64decode(cipher_text)
    cipher = DES.new(KEY, DES.MODE_CBC, IV)
    decrypted = cipher.decrypt(raw)
    return unpad(decrypted, DES.block_size).decode("utf-8")
""",
    },
    "Java": {
        "library": "推荐方案：JCE 标准库，使用 DES/CBC/PKCS5Padding",
        "tips": [
            "Java 的 PKCS5Padding 对 8 字节分组算法 DES 来说等价于 PKCS7Padding。",
            "密钥和 IV 都使用 UTF-8 字节串 1g6n8n8t。",
            "输出和输入统一走 Base64 字符串。",
        ],
        "code": """import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class DesDemo {
    private static final String KEY = "1g6n8n8t";
    private static final String IV = "1g6n8n8t";

    public static String encrypt(String text) throws Exception {
        Cipher cipher = Cipher.getInstance("DES/CBC/PKCS5Padding");
        SecretKeySpec keySpec = new SecretKeySpec(KEY.getBytes(StandardCharsets.UTF_8), "DES");
        IvParameterSpec ivSpec = new IvParameterSpec(IV.getBytes(StandardCharsets.UTF_8));
        cipher.init(Cipher.ENCRYPT_MODE, keySpec, ivSpec);
        byte[] encrypted = cipher.doFinal(text.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(encrypted);
    }

    public static String decrypt(String cipherText) throws Exception {
        Cipher cipher = Cipher.getInstance("DES/CBC/PKCS5Padding");
        SecretKeySpec keySpec = new SecretKeySpec(KEY.getBytes(StandardCharsets.UTF_8), "DES");
        IvParameterSpec ivSpec = new IvParameterSpec(IV.getBytes(StandardCharsets.UTF_8));
        cipher.init(Cipher.DECRYPT_MODE, keySpec, ivSpec);
        byte[] decoded = Base64.getDecoder().decode(cipherText);
        byte[] decrypted = cipher.doFinal(decoded);
        return new String(decrypted, StandardCharsets.UTF_8);
    }
}
""",
    },
    "PHP": {
        "library": "推荐方案：phpseclib 3；如必须用 openssl，请确认环境支持 des-cbc",
        "tips": [
            "PHP 8 + OpenSSL 3 的部分环境默认禁用 DES，客户环境不稳定时更建议 phpseclib。",
            "如果使用 openssl_encrypt，需要输出原始二进制再手动 Base64。",
            "字符串统一按 UTF-8 处理，不要先做 URL 编码。",
        ],
        "code": """<?php
require 'vendor/autoload.php';

use phpseclib3\\Crypt\\DES;

function encryptText(string $plainText): string
{
    $des = new DES('cbc');
    $des->setKey('1g6n8n8t');
    $des->setIV('1g6n8n8t');
    $des->enablePadding();
    return base64_encode($des->encrypt($plainText));
}

function decryptText(string $cipherText): string
{
    $des = new DES('cbc');
    $des->setKey('1g6n8n8t');
    $des->setIV('1g6n8n8t');
    $des->enablePadding();
    return $des->decrypt(base64_decode($cipherText));
}
""",
    },
    "Golang": {
        "library": "推荐库：Go 标准库 crypto/des + cipher",
        "tips": [
            "Go 标准库没有直接提供 PKCS7Padding，需要自己补 pad / unpad。",
            "CBC 加密前明文长度必须补齐到 8 的倍数。",
            "最终结果使用标准 Base64 编码。",
        ],
        "code": """package main

import (
    "bytes"
    "crypto/cipher"
    "crypto/des"
    "encoding/base64"
    "fmt"
)

var key = []byte("1g6n8n8t")
var iv = []byte("1g6n8n8t")

func pkcs7Pad(data []byte, blockSize int) []byte {
    padding := blockSize - len(data)%blockSize
    padText := bytes.Repeat([]byte{byte(padding)}, padding)
    return append(data, padText...)
}

func pkcs7Unpad(data []byte) []byte {
    length := len(data)
    unpadding := int(data[length-1])
    return data[:length-unpadding]
}

func encrypt(text string) (string, error) {
    block, err := des.NewCipher(key)
    if err != nil {
        return "", err
    }
    src := pkcs7Pad([]byte(text), block.BlockSize())
    dst := make([]byte, len(src))
    cipher.NewCBCEncrypter(block, iv).CryptBlocks(dst, src)
    return base64.StdEncoding.EncodeToString(dst), nil
}

func decrypt(cipherText string) (string, error) {
    block, err := des.NewCipher(key)
    if err != nil {
        return "", err
    }
    src, err := base64.StdEncoding.DecodeString(cipherText)
    if err != nil {
        return "", err
    }
    dst := make([]byte, len(src))
    cipher.NewCBCDecrypter(block, iv).CryptBlocks(dst, src)
    return string(pkcs7Unpad(dst)), nil
}

func main() {
    result, _ := encrypt("abcd1234")
    fmt.Println(result)
}
""",
    },
    "C++": {
        "library": "推荐库：Crypto++；如使用 OpenSSL，请确认客户环境可加载 legacy 算法",
        "tips": [
            "纯 C++ 手写 DES/CBC/PKCS7 容易出错，建议直接用成熟库。",
            "Crypto++ 的 DES + CBC_Mode + StreamTransformationFilter 实现最稳。",
            "如果结果不一致，优先检查是否把最终密文字节流做了 Base64。",
        ],
        "code": """#include <iostream>
#include <string>
#include <cryptopp/des.h>
#include <cryptopp/modes.h>
#include <cryptopp/filters.h>
#include <cryptopp/base64.h>

std::string encrypt(const std::string& plainText) {
    using namespace CryptoPP;
    std::string cipherText;
    std::string encoded;
    CBC_Mode<DES>::Encryption enc;
    enc.SetKeyWithIV(
        reinterpret_cast<const byte*>("1g6n8n8t"),
        DES::DEFAULT_KEYLENGTH,
        reinterpret_cast<const byte*>("1g6n8n8t")
    );

    StringSource ss1(
        plainText, true,
        new StreamTransformationFilter(enc, new StringSink(cipherText))
    );

    StringSource ss2(
        cipherText, true,
        new Base64Encoder(new StringSink(encoded), false)
    );
    return encoded;
}
""",
    },
    "Node.js": {
        "library": "推荐方案：Node crypto；注意新版本 OpenSSL 兼容性",
        "tips": [
            "算法名使用 des-cbc，输入输出编码要分清 utf8 / base64。",
            "部分 Node 版本若启用 OpenSSL 3，DES 可能受限制，需要确认运行参数。",
            "客户现场如版本不可控，建议用 Java / Python / Go 做服务端加解密。",
        ],
        "code": """const crypto = require('crypto');

const key = Buffer.from('1g6n8n8t', 'utf8');
const iv = Buffer.from('1g6n8n8t', 'utf8');

function encrypt(text) {
  const cipher = crypto.createCipheriv('des-cbc', key, iv);
  cipher.setAutoPadding(true);
  let encrypted = cipher.update(text, 'utf8', 'base64');
  encrypted += cipher.final('base64');
  return encrypted;
}

function decrypt(cipherText) {
  const decipher = crypto.createDecipheriv('des-cbc', key, iv);
  decipher.setAutoPadding(true);
  let decrypted = decipher.update(cipherText, 'base64', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}
""",
    },
}


class CryptoToolWindow(tk.Toplevel):
    def __init__(self, master=None) -> None:
        super().__init__(master)
        self.title("加密解密工具")
        self.geometry("1120x920")
        self.minsize(1020, 820)
        self.configure(bg=BG_APP)

        self.crypto_service = DESCryptoService()
        self.guide_language_var = tk.StringVar(value="Python")
        self.configure_theme()
        self.apply_window_icon()
        self.build_ui()

    def configure_theme(self) -> None:
        self.option_add("*Font", "{Microsoft YaHei UI} 10")
        style = ttk.Style(self)
        THEME.apply_admin_ttk_theme(
            style,
            palette=ADMIN_TOOL_PALETTE,
            title_size=20,
            section_size=11,
            topbar_bg=ACCENT_DARK,
            include_notebook=True,
            include_status=False,
            include_app_label=False,
            include_app_muted=False,
            include_card_labelframe=False,
            include_card_frame=True,
        )

    def apply_window_icon(self) -> None:
        try:
            icon_path = save_temp_icon()
            self.iconbitmap(default=str(icon_path))
        except Exception:
            pass

    def build_ui(self) -> None:
        root = ttk.Frame(self, style="App.TFrame", padding=24)
        root.pack(fill=tk.BOTH, expand=True)

        topbar = ttk.Frame(root, style="Topbar.TFrame", padding=(18, 14))
        topbar.pack(fill=tk.X)
        ttk.Label(
            topbar,
            text="DES / CBC / PKCS7 / Base64 / UTF-8 加密解密工具",
            style="Topbar.TLabel",
        ).pack(anchor=tk.W)

        hero_shell = ttk.Frame(root, style="App.TFrame", padding=4)
        hero_shell.pack(fill=tk.X, pady=(12, 0))
        hero = ttk.Frame(hero_shell, style="Card.TFrame", padding=(24, 20))
        hero.pack(fill=tk.X)
        ttk.Label(hero, text="加密解密工具", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            hero,
            text="固定参数：DES / CBC / PKCS7Padding / KEY 1g6n8n8t / IV 1g6n8n8t / Base64 / UTF-8",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(
            hero,
            text="适合客户直接验证密文，也适合开发同事参考多语言接入方式。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        crypto_tab = ttk.Frame(notebook, style="App.TFrame", padding=4)
        guide_tab = ttk.Frame(notebook, style="App.TFrame", padding=4)
        notebook.add(crypto_tab, text="加密解密")
        notebook.add(guide_tab, text="接入建议")

        self.build_crypto_panel(crypto_tab)
        self.build_guide_panel(guide_tab)

    def build_section_card(
        self,
        parent,
        title: str,
        *,
        expand: bool = False,
        fill=tk.X,
        use_grid: bool = False,
        row: int = 0,
        column: int = 0,
        sticky: str = tk.EW,
        pady=0,
    ):
        shell = ttk.Frame(parent, style="App.TFrame", padding=4)
        if use_grid:
            shell.grid(row=row, column=column, sticky=sticky, pady=pady)
        else:
            shell.pack(fill=fill, expand=expand, pady=pady)

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

    def build_crypto_panel(self, parent: ttk.Frame) -> None:
        content = ttk.Frame(parent, style="Card.TFrame", padding=(24, 20))
        content.pack(fill=tk.BOTH, expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=3)
        content.rowconfigure(3, weight=3)

        rule_frame = ttk.Frame(content, style="Surface.TFrame")
        rule_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 12))
        ttk.Label(rule_frame, text="使用规则", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            rule_frame,
            text=(
                "1. 明文使用 UTF-8 编码\n"
                "2. 加密模式固定 DES/CBC/PKCS7Padding\n"
                "3. KEY 与 IV 都固定为 1g6n8n8t\n"
                "4. 加密结果统一输出 Base64"
            ),
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        input_frame = self.build_section_card(
            content,
            "输入内容",
            expand=True,
            fill=tk.BOTH,
            use_grid=True,
            row=1,
            column=0,
            sticky=tk.NSEW,
        )
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(1, weight=1)
        ttk.Label(
            input_frame,
            text="可输入待加密明文，或待解密 Base64 密文。",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        self.input_text = ScrolledText(input_frame)
        self.style_text_widget(self.input_text, height=16)
        self.input_text.grid(row=1, column=0, sticky=tk.NSEW)

        btn_frame = ttk.Frame(content, style="Surface.TFrame")
        btn_frame.grid(row=2, column=0, sticky=tk.EW, pady=16)
        ttk.Button(btn_frame, text="加密", command=self.encrypt_text, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="解密", command=self.decrypt_text).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(btn_frame, text="复制结果", command=self.copy_output).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(btn_frame, text="交换输入输出", command=self.swap_text).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(btn_frame, text="清空", command=self.clear_text).pack(side=tk.RIGHT)

        output_frame = self.build_section_card(
            content,
            "结果",
            expand=True,
            fill=tk.BOTH,
            use_grid=True,
            row=3,
            column=0,
            sticky=tk.NSEW,
        )
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(1, weight=1)
        ttk.Label(
            output_frame,
            text="加密后输出 Base64，解密后输出 UTF-8 文本。",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        self.output_text = ScrolledText(output_frame)
        self.style_text_widget(self.output_text, height=16)
        self.output_text.grid(row=1, column=0, sticky=tk.NSEW)

    def build_guide_panel(self, parent: ttk.Frame) -> None:
        content = ttk.Frame(parent, style="Card.TFrame", padding=(24, 20))
        content.pack(fill=tk.BOTH, expand=True)

        summary = self.build_section_card(content, "通用接入建议")
        ttk.Label(
            summary,
            text=(
                "建议优先保证 5 个点一致：算法 DES、分组 CBC、填充 PKCS7、KEY/IV 都为 1g6n8n8t、最终结果做 Base64。\n"
                "如不同语言结果不一致，先用本工具对照同一明文的加密结果，再逐项排查字符集、填充方式和 Base64。"
            ),
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=860,
        ).pack(anchor=tk.W)

        language_bar = ttk.Frame(content, style="Surface.TFrame")
        language_bar.pack(fill=tk.X, pady=(16, 12))
        ttk.Label(language_bar, text="语言选择", style="SectionTitle.TLabel").pack(side=tk.LEFT)
        language_combo = ttk.Combobox(
            language_bar,
            textvariable=self.guide_language_var,
            values=list(LANGUAGE_GUIDES.keys()),
            width=16,
            state="readonly",
        )
        language_combo.pack(side=tk.LEFT, padx=(14, 0))
        language_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_guide())
        ttk.Button(language_bar, text="复制示例代码", command=self.copy_guide_code).pack(side=tk.LEFT, padx=(12, 0))

        tip_frame = self.build_section_card(content, "语言建议")
        self.guide_summary = ScrolledText(tip_frame)
        self.style_text_widget(self.guide_summary, height=9)
        self.guide_summary.pack(fill=tk.X, expand=False)

        code_frame = self.build_section_card(content, "示例代码", expand=True, fill=tk.BOTH, pady=(12, 0))
        self.guide_code = ScrolledText(code_frame)
        self.style_text_widget(self.guide_code, height=20)
        self.guide_code.pack(fill=tk.BOTH, expand=True)

        self.refresh_guide()

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

    def get_input_text(self) -> str:
        return self.input_text.get("1.0", tk.END).strip()

    def set_output_text(self, text: str) -> None:
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", text)

    def encrypt_text(self) -> None:
        source = self.get_input_text()
        if not source:
            messagebox.showwarning("提示", "请输入需要加密的内容。")
            return
        self.set_output_text(self.crypto_service.encrypt(source))

    def decrypt_text(self) -> None:
        source = self.get_input_text()
        if not source:
            messagebox.showwarning("提示", "请输入需要解密的内容。")
            return
        try:
            decrypted = self.crypto_service.decrypt(source)
        except Exception as exc:
            messagebox.showerror("解密失败", f"密文解密失败：\n{exc}")
            return
        self.set_output_text(decrypted)

    def copy_output(self) -> None:
        result = self.output_text.get("1.0", tk.END).strip()
        if not result:
            messagebox.showwarning("提示", "当前没有可复制的结果。")
            return
        self.clipboard_clear()
        self.clipboard_append(result)
        self.update()
        messagebox.showinfo("提示", "结果已复制到剪贴板。")

    def swap_text(self) -> None:
        source = self.input_text.get("1.0", tk.END).strip()
        result = self.output_text.get("1.0", tk.END).strip()
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", result)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", source)

    def clear_text(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)

    def refresh_guide(self) -> None:
        language = self.guide_language_var.get().strip() or "Python"
        guide = LANGUAGE_GUIDES.get(language, LANGUAGE_GUIDES["Python"])
        summary_lines = [guide["library"], "", "接入建议："]
        summary_lines.extend(f"{index}. {item}" for index, item in enumerate(guide["tips"], start=1))

        self.guide_summary.delete("1.0", tk.END)
        self.guide_summary.insert("1.0", "\n".join(summary_lines))
        self.guide_code.delete("1.0", tk.END)
        self.guide_code.insert("1.0", guide["code"])

    def copy_guide_code(self) -> None:
        language = self.guide_language_var.get().strip() or "Python"
        guide = LANGUAGE_GUIDES.get(language, LANGUAGE_GUIDES["Python"])
        self.clipboard_clear()
        self.clipboard_append(guide["code"])
        self.update()
        messagebox.showinfo("提示", f"{language} 示例代码已复制到剪贴板。")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    window = CryptoToolWindow(root)
    window.mainloop()
