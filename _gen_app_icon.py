# -*- coding: utf-8 -*-
"""生成主程序图标 app.ico（简化版）"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# 创建 256x256 图像
size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# 绘制圆角矩形背景
margin = size // 8
radius = size // 4
draw.rounded_rectangle(
    [margin, margin, size - margin, size - margin],
    radius=radius,
    fill="#2196F3",  # 蓝色背景
    outline="#1976D2",
    width=2,
)

# 绘制文字"个"
font_size = int(size * 0.5)
try:
    font = ImageFont.truetype("msyh.ttc", font_size)
except Exception:
    font = ImageFont.load_default()

text = "个"
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
x = (size - text_width) // 2
y = (size - text_height) // 2 - size // 16

draw.text((x, y), text, fill="white", font=font)

# 保存为 ICO（PIL 会自动生成多尺寸）
output_path = Path(__file__).parent / "app.ico"
img.save(output_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

actual_size = output_path.stat().st_size
print(f"OK: {output_path} ({actual_size} bytes)")
