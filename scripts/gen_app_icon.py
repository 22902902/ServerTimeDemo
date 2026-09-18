# -*- coding: utf-8 -*-
"""生成主程序图标 app.ico（简化版占位图）。

注意：本脚本会**覆盖** <项目根>/app.ico。若当前 app.ico 是正式设计稿，
运行前先用 git 确认可回退（`git status` / `git diff --stat`）。

用法：
    python scripts/gen_app_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "app.ico"

SIZE = 256


def build_icon() -> Image.Image:
    """绘制一张 256x256 的圆角矩形 + 单字占位图标。"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = SIZE // 8
    draw.rounded_rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        radius=SIZE // 4,
        fill="#2196F3",
        outline="#1976D2",
        width=2,
    )

    font_size = int(SIZE * 0.5)
    try:
        font = ImageFont.truetype("msyh.ttc", font_size)
    except OSError:
        font = ImageFont.load_default()

    text = "个"
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (SIZE - (bbox[2] - bbox[0])) // 2
    y = (SIZE - (bbox[3] - bbox[1])) // 2 - SIZE // 16
    draw.text((x, y), text, fill="white", font=font)
    return img


def main() -> None:
    if OUTPUT_PATH.exists():
        print(f"[警告] 即将覆盖已存在的图标：{OUTPUT_PATH}")
    build_icon().save(
        OUTPUT_PATH,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"OK: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
