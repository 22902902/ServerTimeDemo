# -*- coding: utf-8 -*-
"""图标生成器等价性验证 —— 只读比对，不写入任何目标文件。

用法：
    python scripts/verify_icon_generators.py [项目根目录]

背景：
    scripts/ 下的三个生成器是 2026-09-18 从项目根目录迁入的（原名带 `_` 前缀）。
    迁移时同步修掉了硬编码路径与 utf-8-sig（BOM）写出问题，因此必须证明
    「搬家 + 修路径」没有改变生成结果。

    做法：在内存里按生成器模板拼出内容，与磁盘上现有文件逐行比对，
    绝不调用生成器的写入分支。这样即使生成器有 bug 也不会破坏源码。

退出码：0 = 等价；1 = 存在差异或环境缺依赖。
"""
import base64
import importlib.util
import os
import sys
from pathlib import Path

if len(sys.argv) > 1:
    ROOT = Path(os.path.abspath(sys.argv[1]))
else:
    ROOT = Path(__file__).resolve().parent.parent

if not (ROOT / "main.py").is_file():
    print(f"找不到 {ROOT / 'main.py'}，请把项目根目录作为第一个参数传入")
    sys.exit(2)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from PIL import Image  # noqa: F401  （生成器模板依赖，缺失则无法加载）
except ImportError as exc:
    print(f"缺少依赖 Pillow（{exc}），本验证需要与生成器相同的运行环境")
    sys.exit(1)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(text):
    return text.replace("\r\n", "\n").replace("\ufeff", "")


def compare(label, expected_text, target):
    actual_text = target.read_text(encoding="utf-8", errors="replace")
    if norm(expected_text) == norm(actual_text):
        bom_expected = expected_text.startswith("\ufeff")
        bom_actual = actual_text.startswith("\ufeff")
        extra = ""
        if bom_actual and not bom_expected:
            extra = "  [差异仅在于：现有文件带 BOM，新脚本已去掉]"
        print(f"  ✓ {label}")
        print(f"      目标: {target.relative_to(ROOT)}")
        print(f"      内容一致（忽略换行/BOM）{extra}")
        return True
    print(f"  ✗ {label} 内容不一致！")
    exp, act = norm(expected_text).splitlines(), norm(actual_text).splitlines()
    print(f"      期望 {len(exp)} 行，实际 {len(act)} 行")
    for i, (x, y) in enumerate(zip(exp, act)):
        if x != y:
            print(f"      首个差异 第{i + 1}行:")
            print(f"        期望: {x[:100]}")
            print(f"        实际: {y[:100]}")
            break
    return False


print("=" * 74)
print("验证 1：gen_app_icon_service.py  ->  services/app_icon_service.py")
print("=" * 74)
m1 = load("g1", ROOT / "scripts" / "gen_app_icon_service.py")
raw = m1.ICON_PATH.read_bytes()
b64 = base64.b64encode(raw).decode("ascii")
expected1 = m1.TEMPLATE.format(b64=m1.wrap_b64(b64))
ok1 = compare("app_icon_service", expected1,
              ROOT / "embedded_admin_tools" / "services" / "app_icon_service.py")

print()
print("=" * 74)
print("验证 2：gen_icon_service.py  ->  services/icon_service.py")
print("=" * 74)
m2 = load("g2", ROOT / "scripts" / "gen_icon_service.py")
raw2 = m2.B64_PATH.read_text(encoding="utf-8-sig").strip()
expected2 = m2.TEMPLATE.format(length=len(raw2), b64=raw2)
ok2 = compare("icon_service", expected2,
              ROOT / "embedded_admin_tools" / "services" / "icon_service.py")

print()
print("=" * 74)
print("验证 3：gen_app_icon.py 是否可导入（不执行生成）")
print("=" * 74)
m3 = load("g3", ROOT / "scripts" / "gen_app_icon.py")
print(f"  ✓ 导入成功，输出目标 = {m3.OUTPUT_PATH.relative_to(ROOT)}")
print(f"      当前 app.ico 存在: {m3.OUTPUT_PATH.exists()}, "
      f"{m3.OUTPUT_PATH.stat().st_size if m3.OUTPUT_PATH.exists() else 0} bytes")

print()
print("=" * 74)
print(f"结论：生成器等价性 {'全部通过' if (ok1 and ok2) else '存在问题，需修正'}")
print("=" * 74)
sys.exit(0 if (ok1 and ok2) else 1)
