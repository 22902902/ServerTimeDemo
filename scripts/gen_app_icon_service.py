# -*- coding: utf-8 -*-
"""由 app.ico 生成内嵌图标的服务模块。

读取 <项目根>/app.ico，转 base64，写出
<项目根>/embedded_admin_tools/services/app_icon_service.py。

注意：本脚本会**覆盖**目标服务文件。该文件当前内容与本脚本模板一致，
但若你手工改过它，先 `git diff` 确认再运行。

设计取舍：base64 内嵌是为了让 PyInstaller 打包后仍能取到图标，
不必依赖外部资源文件。

用法：
    python scripts/gen_app_icon_service.py
"""
import base64
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = PROJECT_ROOT / "app.ico"
OUTPUT_PATH = (PROJECT_ROOT / "embedded_admin_tools" / "services"
               / "app_icon_service.py")

LINE_WIDTH = 76

TEMPLATE = '''# -*- coding: utf-8 -*-
"""主程序图标内嵌服务"""

import base64
import tempfile
from pathlib import Path

# app.ico Base64 内容
_APP_ICON_B64 = """
{b64}
"""

def save_temp_app_icon() -> Path:
    """将内嵌图标保存到临时文件并返回路径。"""
    data = base64.b64decode(_APP_ICON_B64)
    temp_path = Path(tempfile.gettempdir()) / "ExpiryManager_app.ico"
    with open(temp_path, "wb") as f:
        f.write(data)
    return temp_path
'''


def wrap_b64(b64: str, width: int = LINE_WIDTH) -> str:
    """按固定宽度折行，便于 diff 时稳定对比。"""
    return "\n".join(b64[i:i + width] for i in range(0, len(b64), width))


def main() -> None:
    if not ICON_PATH.exists():
        raise SystemExit(f"ERROR: 找不到图标文件 {ICON_PATH}")

    raw = ICON_PATH.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    print(f"图标大小: {len(raw)} bytes")
    print(f"Base64 长度: {len(b64)} chars")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(TEMPLATE.format(b64=wrap_b64(b64)), encoding="utf-8")
    print(f"OK: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
