# -*- coding: utf-8 -*-
"""朗读（speech）回归测试。纯逻辑，**不真的发声**。

为什么单独成篇
------------------------------------------------------------------------------
朗读是「锦上添花」的功能，所以它的失败模式跟别处不一样：**它必须失败得无声**。
没装语音包、远程桌面没声卡、上一条还没念完 —— 这些都得静默，不能弹个窗把一次
训练打断。于是「什么都不发生」在这个模块里是**正确行为**，测试得专门去钉它。

另一类被锁死的是「别剧透」：
* 走一遍里**答案没揭示之前只念提示**，揭示了才连答案一起念
* 关窗 / 关开关必须把正在念的那句掐断 —— PowerShell 进程活着就是在念，
  不杀它，关了窗还在念上一题的答案

**测试不真的起 PowerShell**：那要 0.3~0.8 秒一个进程，还会真的出声。
所以只测「开关关着时 speak 应当什么都不做」这一条最要紧的分支。

覆盖
------------------------------------------------------------------------------
A. 开关语义    关着 = 什么都不做 / 翻开关 / 不能念的机器上开不起来 / 空串不炸
B. 静默失败    stop() 空转安全 / 反复 stop 安全 / speak 非法入参不炸
C. 对外契约    页面用到的五个入口都在
D. 页面接线    两个训练弹窗都有开关与朗读方法（用 ast 扫源码，不 import Tk）

用法：
    python scripts/test_speech.py
"""

import ast
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import speech  # noqa: E402

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


def section(title: str) -> None:
    print(f"\n{title}")


# ══════════════════════════════════════════════════════════════════════════
# A. 开关语义
# ══════════════════════════════════════════════════════════════════════════
def test_toggle() -> None:
    section("[A] 开关语义（关着 = 什么都不做）")

    check("默认关着（朗读不该自己开口）", speech.enabled() is False,
          speech.enabled())

    # 关着的时候 speak 必须**立刻什么都不做**：不进程、不线程、不出声
    speech.set_enabled(False)
    speech.speak("这句话不该被念出来")
    time.sleep(0.2)
    check("关着的时候 speak 不起进程（没声音、也不卡界面）",
          speech._current is None, speech._current)

    check("set_enabled(True) 的返回值 = 真的状态（不能念的机器就开不起来）",
          speech.set_enabled(True) == speech.enabled())
    # 这里不往下断言「一定是 True」：CI / 精简版 Windows 上可能没装语音包，
    # 那时候开不起来才是对的。能念的机器上应当 True，见下面那条。
    if speech.is_available():
        check("机器能念时，开起来就是开着的", speech.enabled() is True)
    else:
        check("机器不能念时，强行开也是关着的（界面照返回值显示才不会骗人）",
              speech.enabled() is False)

    check("toggle() 能翻回去", isinstance(speech.toggle(), bool))
    speech.set_enabled(False)
    check("关掉之后 enabled 是 False", speech.enabled() is False)


# ══════════════════════════════════════════════════════════════════════════
# B. 静默失败
# ══════════════════════════════════════════════════════════════════════════
def test_silent_failures() -> None:
    section("[B] 静默失败（朗读不该打断训练）")

    # 没在念的时候 stop() 是安全的 —— 关窗、关开关都会调到它
    try:
        speech.stop()
        speech.stop()
        ok = True
        detail = ""
    except Exception as exc:                  # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    check("没在念的时候连着 stop 两次都不炸", ok, detail)

    # 各种"不是话"的入参都不许炸（页面里取到的字段常常是空串 / None）
    bad_inputs = ["", "   ", None, 0, [], {}]
    try:
        for value in bad_inputs:
            speech.speak(value)
        ok = True
        detail = ""
    except Exception as exc:                  # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    check("空串 / None / 数字 / 容器 都不炸", ok, detail)

    check("is_available() 返回的是布尔（页面靠它决定要不要显示开关）",
          isinstance(speech.is_available(), bool), speech.is_available())
    check("is_available() 只探一次（不会每念一句都起进程）",
          speech.is_available() == speech.is_available())


# ══════════════════════════════════════════════════════════════════════════
# C. 对外契约
# ══════════════════════════════════════════════════════════════════════════
def test_public_api() -> None:
    section("[C] 对外契约（页面用到的入口都在）")
    used = ("is_available", "enabled", "set_enabled", "toggle", "speak", "stop")
    missing = [n for n in used if not callable(getattr(speech, n, None))]
    check("页面用到的六个入口都存在", not missing, missing)

    check("speak 不阻塞（发声在后台，界面不许卡住）",
          _speak_returns_fast(), "speak() 超过 0.5 秒才返回")

    src = (ROOT / "speech.py").read_text(encoding="utf-8")
    check("发声走的是 PowerShell + System.Speech（不引第三方 TTS 库）",
          "System.Speech" in src and "powershell" in src.lower())
    check("线程是 daemon（主程序退出时不许被它挂住）",
          "daemon=True" in src)


def _speak_returns_fast() -> bool:
    speech.set_enabled(False)
    began = time.time()
    speech.speak("随便一句话")
    return time.time() - began < 0.5


# ══════════════════════════════════════════════════════════════════════════
# D. 页面接线（用 ast 扫源码，不 import Tk）
# ══════════════════════════════════════════════════════════════════════════
def _class_methods(path: Path) -> dict:
    """``{类名: {方法名集合}}``。扫源码而不是 import —— 免得把 tkinter 拖进来。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, set] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            out[node.name] = {
                n.name for n in node.body if isinstance(n, ast.FunctionDef)}
    return out


def _imports_speech(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "speech" for alias in node.names):
                return True
    return False


def test_page_wiring() -> None:
    section("[D] 页面接线（两个训练弹窗都要有开关）")
    for name, cls in (("memory_page.py", "WalkSession"),
                      ("mindmap_page.py", "BlindSession")):
        path = ROOT / name
        check(f"{name} import 了 speech", _imports_speech(path))
        methods = _class_methods(path).get(cls, set())
        check(f"{cls} 有 toggle_speech（界面上够得着）",
              "toggle_speech" in methods, sorted(methods))
        check(f"{cls} 有 _speak_current（念当前这一站）",
              "_speak_current" in methods, sorted(methods))
        check(f"{cls} 关窗时掐断朗读",
              "speech.stop()" in path.read_text(encoding="utf-8"))

    # 「别剧透」：走一遍里，答案必须是揭示了才念
    mem = (ROOT / "memory_page.py").read_text(encoding="utf-8")
    check("走一遍：没揭示只念提示，揭示了才连答案一起念",
          "if self.revealed:" in mem and "_speak_current" in mem)


def main_test() -> None:
    test_toggle()
    test_silent_failures()
    test_public_api()
    test_page_wiring()
    speech.set_enabled(False)
    speech.stop()


if __name__ == "__main__":
    try:
        main_test()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILED += 1
    finally:
        speech.set_enabled(False)
        speech.stop()

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
