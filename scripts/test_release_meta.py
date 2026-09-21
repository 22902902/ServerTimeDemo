"""发布元信息回归：版本号 / 更新日志 / CHANGELOG.md 是否一致。

背景：版本号以前是 main.py 里一行硬编码字符串，从建立版本控制起就没再改过，
于是不管重打包多少次，界面上的版本号都一模一样 —— 用户没法判断手上跑的是不是
新版。收口到 app_version.py 之后，这个套件负责盯住三件事不许再退化：

1. 版本号本身合法（x.y.z）、最新一版与 ``APP_VERSION`` 对得上、顺序是降序
2. 界面真的会显示它（main.py 引用 app_version.APP_TITLE，而不是又写死一串）
3. ``CHANGELOG.md`` 与 ``app_version.VERSION_HISTORY`` 没有漂移

用法::

    python scripts/test_release_meta.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import app_version  # noqa: E402


PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


def _version_key(text: str) -> tuple:
    return tuple(int(part) for part in text.split("."))


# ---------------------------------------------------------------------------
# [A] 版本号本身
# ---------------------------------------------------------------------------

def test_version_number():
    print("\n[A] 版本号")

    version = app_version.APP_VERSION
    check("版本号是 x.y.z 三段纯数字", bool(re.fullmatch(r"\d+\.\d+\.\d+", version)),
          repr(version))
    check("APP_TITLE 带着版本号（界面才能一眼看出新旧）",
          version in app_version.APP_TITLE
          and app_version.APP_NAME in app_version.APP_TITLE,
          app_version.APP_TITLE)
    check("发布日期是 YYYY-MM-DD",
          bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", app_version.APP_RELEASE_DATE)),
          repr(app_version.APP_RELEASE_DATE))

    history = app_version.VERSION_HISTORY
    check("更新日志非空", bool(history))
    if not history:
        return

    versions = [entry["version"] for entry in history]
    check("每个版本号都合法",
          all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in versions), str(versions))
    check("版本号不重复", len(set(versions)) == len(versions), str(versions))
    check("最新一条就是 APP_VERSION", versions[0] == version,
          f"{versions[0]} vs {version}")
    check("按版本号严格降序排列",
          all(_version_key(versions[i]) > _version_key(versions[i + 1])
              for i in range(len(versions) - 1)),
          str(versions))
    check("日期不早于下一版（越往上越新）",
          all(history[i]["date"] >= history[i + 1]["date"]
              for i in range(len(history) - 1)),
          str([e["date"] for e in history]))

    for entry in history:
        v = entry["version"]
        check(f"v{v} 的日期格式正确",
              bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["date"])), entry["date"])
        check(f"v{v} 有标题", bool(entry["title"].strip()))
        check(f"v{v} 有改动条目", len(entry["changes"]) > 0)
        check(f"v{v} 没有空条目",
              all(c.strip() for c in entry["changes"]))

    check("latest() 与首条一致", app_version.latest() is history[0])


# ---------------------------------------------------------------------------
# [B] Markdown 导出
# ---------------------------------------------------------------------------

def test_markdown_export():
    print("\n[B] Markdown 导出")

    md = app_version.changelog_markdown()
    check("导出内容以一级标题开头",
          md.startswith(f"# 更新日志 · {app_version.APP_NAME}"), md.splitlines()[0])
    check("导出内容带当前版本",
          f"v{app_version.APP_VERSION}" in md)
    for entry in app_version.VERSION_HISTORY:
        check(f"导出含 v{entry['version']} 的小节",
              f"## v{entry['version']}" in md)
        check(f"导出含 v{entry['version']} 的标题",
              entry["title"] in md)
        check(f"v{entry['version']} 的条目数对得上",
              md.count("- ") >= len(entry["changes"]))
    check("导出以单个换行结尾", md.endswith("\n") and not md.endswith("\n\n"))

    header = app_version.changelog_header()
    check("CHANGELOG 头部声明「不要手工编辑」",
          "不要手工编辑" in header and "gen_changelog" in header)


# ---------------------------------------------------------------------------
# [C] CHANGELOG.md 同步
# ---------------------------------------------------------------------------

def test_changelog_file():
    print("\n[C] CHANGELOG.md 同步")

    target = ROOT / "CHANGELOG.md"
    check("CHANGELOG.md 存在", target.exists())
    if not target.exists():
        return

    raw = target.read_bytes()
    check("CHANGELOG.md 用 LF（与仓库其它 .md 一致）",
          b"\r\n" not in raw, f"CRLF={raw.count(bytes([13, 10]))}")
    check("CHANGELOG.md 无 BOM", not raw.startswith(b"\xef\xbb\xbf"))

    expected = app_version.changelog_header() + "\n" + app_version.changelog_markdown()
    current = raw.decode("utf-8")
    check("CHANGELOG.md 与 VERSION_HISTORY 同步（没漂移）", current == expected,
          "跑 `python scripts/gen_changelog.py` 重新生成")


# ---------------------------------------------------------------------------
# [D] 界面真的显示版本号
# ---------------------------------------------------------------------------

def test_wired_into_ui():
    print("\n[D] 接进界面")

    main_src = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    check("main.py 导入 app_version", "import app_version" in main_src)
    check("APP_TITLE 取自 app_version（不再硬编码）",
          "APP_TITLE = app_version.APP_TITLE" in main_src,
          "main.py 里 APP_TITLE 又被写死了")
    check("main.py 里没有残留的硬编码版本号",
          not re.search(r'APP_TITLE\s*=\s*"[^"]*v\d+\.\d+\.\d+', main_src),
          "又出现了 `APP_TITLE = \"... v1.x.x\"` 这种写法")
    check("窗口标题用的是 APP_TITLE",
          "self.title(APP_TITLE)" in main_src)
    check("顶栏有「更新日志」入口",
          '"更新日志"' in main_src and "self.show_changelog" in main_src)
    check("更新日志弹窗复用 markdown_view 渲染",
          "import markdown_view" in main_src
          and "markdown_view.render(" in main_src)

    # 打包配置要把新模块带上：漏了的话运行版会 ImportError
    spec = ROOT / "ExpiryManager_fixed.spec"
    if spec.exists():
        spec_src = spec.read_text(encoding="utf-8", errors="replace")
        check("打包 spec 把新模块写进了 hiddenimports",
              "app_version" in spec_src and "markdown_view" in spec_src,
              "漏了的话运行版一进工具箱就 ImportError")
        # excludes 名单是「明确不打包」的意思，写进去等于自断经脉。
        # 注意：任何 spec 都有 `excludes=[]` 这一行，所以要取方括号里的内容判，
        # 不能只搜 "excludes" 这个词（上一版就是这么写错的，恒真无意义）
        m = re.search(r"excludes=\[(.*?)\]", spec_src, re.S)
        excluded = m.group(1) if m else ""
        check("新模块没被 excludes 排除",
              "app_version" not in excluded and "markdown_view" not in excluded,
              excluded.strip())


def main() -> int:
    print("=" * 78)
    print("发布元信息：版本号 / 更新日志 / CHANGELOG.md")
    print("=" * 78)

    test_version_number()
    test_markdown_export()
    test_changelog_file()
    test_wired_into_ui()

    print("\n" + "=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
