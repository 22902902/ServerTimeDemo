# -*- coding: utf-8 -*-
import base64, os

b64_file = r'F:\phpstudy_pro\WWW\ServerTimeDemo\embedded_admin_tools\_ico_base64.txt'
with open(b64_file, 'r', encoding='utf-8-sig') as f:
    b64 = f.read().strip()

content = f'''# -*- coding: utf-8 -*-
"""图标内嵌服务 - 内嵌 auction_api_demo.ico"""

import base64
import tempfile
from pathlib import Path

# auction_api_demo.ico Base64 内容 ({len(b64)} 字符)
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

out_path = r'F:\phpstudy_pro\WWW\ServerTimeDemo\embedded_admin_tools\services\icon_service.py'
with open(out_path, 'w', encoding='utf-8-sig') as f:
    f.write(content)
print('Done:', os.path.getsize(out_path))
