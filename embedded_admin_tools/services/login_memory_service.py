import base64
import ctypes
import json
import sys
from pathlib import Path

from .crypto_service import DESCryptoService


LOGIN_MEMORY_FILE = "login_memory.json"
LOGIN_MEMORY_FIELD_ORDER = [
    "account",
    "password_cipher",
    "lt",
    "member_type",
    "environment_label",
    "password_format",
    "storage_version",
]
PASSWORD_FORMAT_DES = "des_base64"
PASSWORD_FORMAT_DPAPI = "windows_dpapi_base64"
LOGIN_MEMORY_STORAGE_VERSION = 3
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def get_login_memory_path() -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(sys.executable).resolve().parent
    else:
        base_path = Path(__file__).resolve().parent.parent
    return base_path / LOGIN_MEMORY_FILE


class LoginMemoryService:
    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = file_path or get_login_memory_path()
        self.crypto_service = DESCryptoService()

    def load(self) -> dict:
        if not self.file_path.exists():
            return {}
        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return self.deserialize(raw_data)

    def load_raw(self) -> dict:
        if not self.file_path.exists():
            return {}
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def save(self, updates: dict) -> None:
        existing = self.load()
        existing.update({key: value for key, value in updates.items() if value is not None})
        ordered_data = self.normalize(self.serialize(existing))
        try:
            self.file_path.write_text(json.dumps(ordered_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def clear(self) -> None:
        try:
            self.file_path.unlink(missing_ok=True)
        except OSError:
            pass

    def get_storage_label(self) -> str:
        raw_data = self.load_raw()
        password_format = str(raw_data.get("password_format", "") or "")
        if password_format == PASSWORD_FORMAT_DPAPI:
            return "Windows 本机加密"
        if password_format == PASSWORD_FORMAT_DES:
            return "项目兼容密文"
        if raw_data.get("password"):
            return "旧版明文"
        return "未设置"

    def serialize(self, data: dict) -> dict:
        password_cipher, password_format = self.encrypt_password(data.get("password", ""))
        serialized = {
            "account": data.get("account", ""),
            "lt": data.get("lt", "web"),
            "member_type": data.get("member_type", "supplier"),
            "environment_label": data.get("environment_label", "测试环境"),
            "password_format": password_format,
            "storage_version": LOGIN_MEMORY_STORAGE_VERSION,
        }
        serialized["password_cipher"] = password_cipher
        return serialized

    def deserialize(self, data: dict) -> dict:
        loaded = {
            "account": data.get("account", ""),
            "lt": data.get("lt", "web"),
            "member_type": data.get("member_type", "supplier"),
            "environment_label": data.get("environment_label", "测试环境"),
        }
        loaded["password"] = self.decrypt_password(data)
        return loaded

    def encrypt_password(self, password: object) -> tuple[str, str]:
        password_text = str(password or "")
        if not password_text:
            return "", PASSWORD_FORMAT_DPAPI
        if sys.platform.startswith("win"):
            try:
                protected = self.protect_with_windows(password_text.encode("utf-8"))
                return base64.b64encode(protected).decode("utf-8"), PASSWORD_FORMAT_DPAPI
            except Exception:
                pass
        try:
            return self.crypto_service.encrypt(password_text), PASSWORD_FORMAT_DES
        except Exception:
            return "", PASSWORD_FORMAT_DES

    def decrypt_password(self, data: dict) -> str:
        cipher_text = str(data.get("password_cipher", "") or "")
        password_format = str(data.get("password_format", "") or "")
        if cipher_text and password_format == PASSWORD_FORMAT_DPAPI and sys.platform.startswith("win"):
            try:
                decoded = base64.b64decode(cipher_text)
                return self.unprotect_with_windows(decoded).decode("utf-8")
            except Exception:
                pass
        if cipher_text and password_format == PASSWORD_FORMAT_DES:
            try:
                return self.crypto_service.decrypt(cipher_text)
            except Exception:
                pass
        return str(data.get("password", "") or "")

    @staticmethod
    def create_blob(raw: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
        buffer = ctypes.create_string_buffer(raw, len(raw))
        blob = DATA_BLOB(
            cbData=len(raw),
            pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        return blob, buffer

    @staticmethod
    def protect_with_windows(raw: bytes) -> bytes:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        in_blob, in_buffer = LoginMemoryService.create_blob(raw)
        out_blob = DATA_BLOB()
        description = "ServerTimeDemo Login Memory"
        success = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            description,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not success:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
            _ = in_buffer

    @staticmethod
    def unprotect_with_windows(raw: bytes) -> bytes:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        in_blob, in_buffer = LoginMemoryService.create_blob(raw)
        out_blob = DATA_BLOB()
        description = ctypes.c_wchar_p()
        success = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            ctypes.byref(description),
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not success:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            if description:
                kernel32.LocalFree(description)
            kernel32.LocalFree(out_blob.pbData)
            _ = in_buffer

    @staticmethod
    def normalize(data: dict) -> dict:
        ordered = {}
        for key in LOGIN_MEMORY_FIELD_ORDER:
            if key in data:
                ordered[key] = data[key]
        for key in sorted(data.keys()):
            if key not in ordered:
                ordered[key] = data[key]
        return ordered
