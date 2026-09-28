# -*- coding: utf-8 -*-
"""朗读（TTS）：走 Windows 自带的 System.Speech，不引第三方依赖。

为什么不用 pyttsx3 / gTTS
------------------------------------------------------------------------------
* ``pyttsx3`` 要拖进 pywin32 和一层 COM 封装，而这个程序**只在 Windows 上跑**，
  为了「念出一行字」多挂一条依赖链不划算；
* ``gTTS`` 要联网，离线机器上直接哑掉。

Windows 自带 ``System.Speech.Synthesis.SpeechSynthesizer``，PowerShell 一句话就
能调。代价是**每念一句要起一个 PowerShell 进程**（约 0.3~0.8 秒），所以：

* 发声走**后台线程**，绝不卡住界面；
* 「关」= 直接终止那个进程 —— 这是唯一能把话掐断的办法；
* 失败一律**静默**：没装语音包、远程桌面没声卡、上一条还没念完，都很常见。
  朗读是锦上添花，**不该因为它打断一次训练**。

用法
------------------------------------------------------------------------------
    import speech

    speech.set_enabled(True)      # 开关（只在能朗读的机器上才真打开）
    speech.speak("要念出来的这句话")
    speech.stop()                 # 把正在念的这句掐掉
"""

from __future__ import annotations

import os
import subprocess
import threading

# 开关是**会话内**的：朗读是即时动作，没必要写进库里记住
_enabled = False
_lock = threading.Lock()
_current: subprocess.Popen | None = None
_available: bool | None = None

# PowerShell 一句话发声。``-STA`` 是因为 SpeechSynthesizer 是 COM 组件，
# 不加它在部分机器上直接抛「无法创建 ActiveX 组件」。
_PS = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak([Console]::In.ReadToEnd())"
)
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW：别闪一个黑框出来
_TIMEOUT = 60            # 一句念超过 60 秒一定是卡住了


def _flags() -> int:
    """``creationflags`` 只有 Windows 认，别的平台给 0。"""
    return _NO_WINDOW if os.name == "nt" else 0


def is_available() -> bool:
    """这台机器能不能朗读。**只探一次**，免得每念一句都先起一个进程试。"""
    global _available
    if _available is not None:
        return _available
    if os.name != "nt":
        _available = False
        return False
    try:
        probe = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command",
             "Add-Type -AssemblyName System.Speech"],
            capture_output=True, timeout=15, creationflags=_flags())
        _available = probe.returncode == 0
    except Exception:
        _available = False
    return _available


def enabled() -> bool:
    return _enabled


def set_enabled(value: bool) -> bool:
    """打开 / 关闭朗读，返回**真的生效之后**的开关状态。

    机器上不能朗读时，就算传 True 也是 False —— 让界面照着返回值显示，
    用户才不会看到「开了却没声音」。
    """
    global _enabled
    _enabled = bool(value) and is_available()
    if not _enabled:
        stop()
    return _enabled


def toggle() -> bool:
    """翻一下开关，返回新的状态。绑定按钮最省事。"""
    return set_enabled(not _enabled)


def speak(text: str) -> None:
    """念一句。**立刻返回**，发声在后台跑。

    开关关着、机器上不能念、或者这句话是空的 —— 都直接什么都不做。
    """
    global _current
    body = str(text or "").strip()
    if not _enabled or not body or not is_available():
        return

    def _run() -> None:
        global _current
        proc = None
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-STA", "-Command", _PS],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=_flags())
            with _lock:
                _current = proc
            # 同步等它念完：进程活着 = 正在念，所以 stop() 杀进程就能掐断
            proc.communicate(input=body.encode("utf-8"), timeout=_TIMEOUT)
        except Exception:
            pass
        finally:
            with _lock:
                if proc is not None and _current is proc:
                    _current = None

    threading.Thread(target=_run, daemon=True).start()


def stop() -> None:
    """把正在念的这句掐掉。**没在念的时候调用是安全的**。"""
    global _current
    with _lock:
        proc, _current = _current, None
    if proc is None:
        return
    try:
        proc.kill()
    except Exception:
        pass
