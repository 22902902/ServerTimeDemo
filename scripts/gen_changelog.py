"""从 app_version.VERSION_HISTORY 生成仓库根目录的 CHANGELOG.md。

更新日志只维护一份数据源（app_version.py），这里是「导出」而不是「编辑」：
改了版本内容就重跑一次本脚本；scripts/test_release_meta.py 会比对
CHANGELOG.md 与 app_version.VERSION_HISTORY，漂移了就报错。

用法::

    python scripts/gen_changelog.py          # 写入 CHANGELOG.md
    python scripts/gen_changelog.py --check  # 只校验是否同步（不写文件）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app_version  # noqa: E402

TARGET = ROOT / "CHANGELOG.md"


def render() -> str:
    return app_version.changelog_header() + "\n" + app_version.changelog_markdown()


def main() -> int:
    expected = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current == expected:
            print(f"CHANGELOG.md 与 app_version.VERSION_HISTORY 同步"
                  f"（{len(app_version.VERSION_HISTORY)} 个版本）")
            return 0
        print("CHANGELOG.md 已过期 —— 跑 `python scripts/gen_changelog.py` 重新生成")
        return 1

    # 仓库里的 *.md 统一 LF（跟 UI_NOTES.md 等一致），别跟着应用源码用 CRLF
    TARGET.write_bytes(expected.replace("\r\n", "\n").encode("utf-8"))
    print(f"已写入 {TARGET.name}：v{app_version.APP_VERSION} + "
          f"{len(app_version.VERSION_HISTORY) - 1} 个历史版本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
