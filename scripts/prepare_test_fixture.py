#!/usr/bin/env python3
"""准备回归测试的夹具库：把随身包里的库复制成仓库根的 `expiry_manager.db`。

为什么需要这一步
------------------------------------------------------------------------------
UI / 数据层套件读的是 `main.DB_PATH`（= `BASE_DIR / "expiry_manager.db"`）。
历史上仓库根躺着一份「开发库」当夹具，2026-09-29 起数据只留随身包一处，
那份老库删了 —— 于是这些套件看不到数据，报出**看着像功能坏了**的假红：

* `test_notes_editor` → 「FAIL 库里存在笔记　共 0 篇」
* `test_startup_ui` → `sqlite3.OperationalError: no such table: app_state`

所以开跑前按需生成一份。**它不是第二份需要人维护的数据**：每次都是随身包的
逐字节副本，被 `.gitignore` 覆盖，随时可删 —— 删了下次跑自动重建。

为什么要拷而不是直接指随身包：套件里确实有**写**（`test_startup_ui` 收尾会
`DELETE FROM app_state` 再灌回去）。夹具是派生品，写坏了重建就是；
写坏真实数据就没这么轻松了。

用法：
    python scripts/prepare_test_fixture.py          # 生成/刷新
    python scripts/prepare_test_fixture.py --check   # 只看状态，不写
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "expiry_manager.db"

# 与 make_portable / export_sensitive 同一个约定
PORTABLE_DIR = Path(os.environ.get("SERVERDEMO_PORTABLE_DIR",
                                   r"F:\ServerTimeDemo_随身包"))


def source_db() -> Path:
    return PORTABLE_DIR / "expiry_manager.db"


def prepare(quiet: bool = False) -> Path | None:
    """生成夹具库。成功返回路径；来源缺失时返回 None（不抛）。"""
    src = source_db()
    if not src.exists():
        if not quiet:
            print(f"夹具库来源不存在：{src}")
            print("  先设置环境变量 SERVERDEMO_PORTABLE_DIR，或确认随身包在位。")
        return None
    tmp = FIXTURE.with_name(FIXTURE.name + ".tmp")
    with src.open("rb") as fh, tmp.open("wb") as out:
        shutil.copyfileobj(fh, out)
    os.replace(tmp, FIXTURE)
    if not quiet:
        print(f"夹具库已就绪：{FIXTURE}")
        print(f"  {FIXTURE.stat().st_size:,} B，来源 {src}")
    return FIXTURE


def main(argv: list[str]) -> int:
    if "--check" in argv:
        src = source_db()
        print(f"来源　{src}　{'在' if src.exists() else '不在'}")
        print(f"夹具　{FIXTURE}　{'在' if FIXTURE.exists() else '不在'}"
              + (f"（{FIXTURE.stat().st_size:,} B）" if FIXTURE.exists() else ""))
        return 0
    return 0 if prepare() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
