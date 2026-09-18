# -*- coding: utf-8 -*-
"""读取 app.ico 并生成 base64 内嵌代码"""

import base64
from pathlib import Path

icon_path = Path(__file__).parent / "app.ico"
if not icon_path.exists():
    print("ERROR: app.ico not found")
    exit(1)

with open(icon_path, "rb") as f:
    data = f.read()

b64 = base64.b64encode(data).decode("ascii")
print(f"Icon size: {len(data)} bytes")
print(f"Base64 length: {len(b64)} chars")
print()

# 输出 Python 代码
output_path = Path(__file__).parent / "embedded_admin_tools" / "services" / "app_icon_service.py"
with open(output_path, "w", encoding="utf-8") as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('"""主程序图标内嵌服务"""\n\n')
    f.write('import base64\n')
    f.write('import tempfile\n')
    f.write('from pathlib import Path\n\n')
    f.write('# app.ico Base64 内容\n')
    f.write('_APP_ICON_B64 = """\n')
    # 分行输出（每行 76 字符）
    for i in range(0, len(b64), 76):
        f.write(b64[i:i+76] + "\n")
    f.write('"""\n\n')
    f.write('def save_temp_app_icon() -> Path:\n')
    f.write('    """将内嵌图标保存到临时文件并返回路径。"""\n')
    f.write('    data = base64.b64decode(_APP_ICON_B64)\n')
    f.write('    temp_path = Path(tempfile.gettempdir()) / "ExpiryManager_app.ico"\n')
    f.write('    with open(temp_path, "wb") as f:\n')
    f.write('        f.write(data)\n')
    f.write('    return temp_path\n')

print(f"OK: {output_path}")
