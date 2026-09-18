import base64

from Crypto.Cipher import DES
from Crypto.Util.Padding import pad, unpad


class DESCryptoService:
    def __init__(self, key: str = "1g6n8n8t", iv: str = "1g6n8n8t") -> None:
        self.key = key.encode("utf-8")
        self.iv = iv.encode("utf-8")

    def encrypt(self, plain_text: str) -> str:
        cipher = DES.new(self.key, DES.MODE_CBC, self.iv)
        encrypted = cipher.encrypt(pad(plain_text.encode("utf-8"), DES.block_size))
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt(self, cipher_text: str) -> str:
        raw = base64.b64decode(cipher_text)
        cipher = DES.new(self.key, DES.MODE_CBC, self.iv)
        decrypted = cipher.decrypt(raw)
        return unpad(decrypted, DES.block_size).decode("utf-8")
