# -*- coding: utf-8 -*-
"""由 base64 文本生成内嵌图标的服务模块。

读取 <项目根>/embedded_admin_tools/_ico_base64.txt，
写出 <项目根>/embedded_admin_tools/services/icon_service.py。

注意：本脚本会**覆盖**目标服务文件。运行前先 `git diff` 确认无手改内容。

编码说明：原脚本以 utf-8-sig 写出，导致目标文件带 BOM（U+FEFF），
与项目其余文件不一致；本版改为无 BOM 的 utf-8。

用法：
    python scripts/gen_icon_service.py
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
B64_PATH = PROJECT_ROOT / "embedded_admin_tools" / "_ico_base64.txt"
OUTPUT_PATH = (PROJECT_ROOT / "embedded_admin_tools" / "services"
               / "icon_service.py")

TEMPLATE = '''# -*- coding: utf-8 -*-
"""图标内嵌服务 - 内嵌 auction_api_demo.ico"""

import base64
import tempfile
from pathlib import Path

# auction_api_demo.ico Base64 内容 ({length} 字符)
_ICON_BASE64 = """{b64}"""

def get_icon_bytes() -> bytes:
    """返回 ICO 文件原始字节"""
    return base64.b64decode(_ICON_BASE64)

def save_temp_icon() -> Path:
    """解压到临时文件，返回路径（由调用方负责清理）"""
    tmp = tempfile.NamedTemporaryFile(suffix=".ico", delete=False)
    tmp.write(get_icon_bytes())
    tmp.close()
    return Path(tmp.name)
'''


def main() -> None:
    if not B64_PATH.exists():
        raise SystemExit(f"ERROR: 找不到 base64 源文件 {B64_PATH}")

    b64 = B64_PATH.read_text(encoding="utf-8-sig").strip()
    print(f"Base64 长度: {len(b64)} chars")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        TEMPLATE.format(length=len(b64), b64=b64), encoding="utf-8"
    )
    print(f"OK: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
