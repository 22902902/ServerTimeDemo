# -*- coding: utf-8 -*-
"""开机自启动（startup_manager）回归测试 —— 纯数据层，**不 import tkinter**。

为什么单开一个套件：这个功能的正确性几乎全在「命令行怎么拼、怎么比、注册表怎么
读写、什么时候该动手自愈」这几件事上，全都跟界面无关。所以这里用**内存后端**把逻辑
跑透，不需要任何窗口。

只有第 8 节碰一次**真注册表**，而且用的是临时键路径
（``HKCU\\Software\\ServerTimeDemoTest\\...``），跑完逐层删掉 ——
**绝不碰真正的 Run 键**。

用法：
    python scripts/test_startup.py [项目根目录]

覆盖：
  1. 命令行拼装（打包版 / 源码版 / 带空格路径 / 启动标记）
  2. 命令行归一化比较（引号、大小写、空格、斜杠、环境变量）
  3. 内存后端：开关、幂等、回读校验
  4. 状态判定：enabled / stale / state() 快照
  5. 漂移自愈：只修「我们开的、而且没被改过」的那一种
  6. 启动标记解析：--autostart 大小写、带别的参数、干扰参数
  7. 凭据解析：正常 / 未勾记住 / 坏 JSON / 坏 base64 / 空字段 / 候选路径
  8. 真注册表后端（临时键路径）端到端
  9. 常量与接线：main 接上了、spec 登记了、登录框复用了同一套解析

退出码：0 = 全部通过；1 = 有失败项。
"""
import base64
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if len(sys.argv) > 1:
    ROOT = Path(os.path.abspath(sys.argv[1]))
else:
    ROOT = Path(__file__).resolve().parent.parent

if not (ROOT / "startup_manager.py").is_file():
    print(f"找不到 {ROOT / 'startup_manager.py'}")
    sys.exit(2)

sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from startup_manager import (          # noqa: E402
    AUTOSTART_FLAG,
    DictBackend,
    REMEMBER_FILE_NAME,
    RUN_KEY_PATH,
    STATE_COMMAND_KEY,
    STATE_INTENT_KEY,
    StartupManager,
    VALUE_NAME,
    WinRegBackend,
    build_command,
    executable_for_autostart,
    is_autostart_launch,
    load_remember_file,
    normalize_command,
    read_remembered_credentials,
)

passed, failed = [], []


def check(label, ok, detail=""):
    (passed if ok else failed).append(label)
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}" + (f"\n        {detail}" if detail else ""))


def section(title):
    print()
    print("=" * 76)
    print(title)
    print("=" * 76)


TMP = Path(tempfile.mkdtemp(prefix="startup_test_"))
EXE_SPACE = r"C:\Program Files\Personal System\PersonalSystem.exe"
EXE_PLAIN = r"D:\apps\PersonalSystem.exe"
SCRIPT = r"F:\phpstudy_pro\WWW\ServerTimeDemo\main.py"


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def write_remember(name: str, payload) -> Path:
    path = TMP / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def make_manager(executable=EXE_PLAIN, *, backend=None, frozen=True, script="", flag=AUTOSTART_FLAG):
    return StartupManager(backend=backend if backend is not None else DictBackend(),
                          frozen=frozen, executable=executable, script=script, flag=flag)


try:
    # =====================================================================
    section("1. 命令行拼装")
    # =====================================================================
    cmd_packed = build_command(frozen=True, executable=EXE_SPACE, script="")
    check("打包版：拉 exe 自己，不带脚本",
          cmd_packed == f'"{EXE_SPACE}" {AUTOSTART_FLAG}', cmd_packed)
    check("打包版：带空格的路径被引号包住",
          cmd_packed.startswith('"') and cmd_packed.count('"') == 2, cmd_packed)

    check("打包版：不带空格的路径也加引号（口径统一，比较才稳）",
          build_command(frozen=True, executable=EXE_PLAIN, script="") == f'"{EXE_PLAIN}" {AUTOSTART_FLAG}')

    cmd_source = build_command(frozen=False, executable=r"C:\Py\python.exe",
                               script=SCRIPT, flag=AUTOSTART_FLAG)
    check("源码版：命令行里同时有解释器和脚本",
          SCRIPT in cmd_source and "python" in cmd_source.lower(), cmd_source)
    check("源码版：脚本路径也被引号包住", f'"{SCRIPT}"' in cmd_source, cmd_source)

    check("flag 为空时不追加任何尾巴",
          build_command(frozen=True, executable=EXE_PLAIN, script="", flag="")
          == f'"{EXE_PLAIN}"')
    check("默认 flag 就是 --autostart",
          AUTOSTART_FLAG in build_command(frozen=True, executable=EXE_PLAIN, script=""))

    exe, script = executable_for_autostart(frozen=True, executable=EXE_PLAIN, script=SCRIPT)
    check("打包版忽略传进来的脚本路径", script == "" and exe == EXE_PLAIN)
    exe, script = executable_for_autostart(frozen=False, executable=r"C:\Py\python.exe",
                                          script=SCRIPT)
    check("源码版带上脚本", script == SCRIPT, f"{exe} / {script}")
    exe, script = executable_for_autostart(frozen=False, executable=r"C:\Py\python.exe",
                                          script="")
    check("源码版没有脚本时如实返回空（不瞎猜 main.py 在哪）", script == "", repr(script))
    exe, _ = executable_for_autostart(frozen=False, executable=r"C:\Py\python.exe",
                                     script=SCRIPT, pythonw=r"C:\Py\pythonw.exe")
    check("源码版显式指定 pythonw 时优先用它", exe == r"C:\Py\pythonw.exe", exe)

    # =====================================================================
    section("2. 命令行归一化比较")
    # =====================================================================
    expected = build_command(frozen=True, executable=EXE_SPACE, script="")
    same_cases = [
        (r'"c:\program files\personal system\personalsystem.exe"   --AUTOSTART', "大小写 + 多余空格"),
        (r"c:\program files\personal system\personalsystem.exe --autostart", "不加引号"),
        (r'"C:/Program Files/Personal System/PersonalSystem.exe" --autostart', "正斜杠"),
        (expected, "逐字相同"),
    ]
    for text, why in same_cases:
        check(f"归一化后判为同一条（{why}）",
              normalize_command(text) == normalize_command(expected), text)

    diff_cases = [
        (r'"C:\Program Files\Personal System\Other.exe" --autostart', "换了可执行文件"),
        (r'"C:\Program Files\Personal System\PersonalSystem.exe"', "少了启动标记"),
        (r'"C:\Program Files\Personal System\PersonalSystem.exe" --autostart --extra', "多了参数"),
        ("", "空内容"),
    ]
    for text, why in diff_cases:
        check(f"归一化后判为不同（{why}）",
              normalize_command(text) != normalize_command(expected), repr(text))

    check("空内容归一化成空串", normalize_command("") == "" and normalize_command(None) == "")

    os.environ["STD_AUTOSTART_PROBE"] = r"C:\Program Files\Personal System"
    env_variant = r'"%STD_AUTOSTART_PROBE%\PersonalSystem.exe" --autostart'
    check("环境变量形式会展开后再比（否则会被误判成「指向别处」）",
          normalize_command(env_variant) == normalize_command(expected), env_variant)

    check("全是空格也当归一化成空串", normalize_command("   ") == "")

    # =====================================================================
    section("3. 内存后端：开关、幂等、回读校验")
    # =====================================================================
    backend = DictBackend()
    manager = make_manager(backend=backend)
    check("新后端上：未开启", not manager.is_enabled() and not manager.is_stale())
    check("未开启时 read_command 是空串", manager.read_command() == "")

    ok, detail = manager.enable()
    check("enable 成功", ok, detail)
    check("enable 返回的就是写进去的那条命令", detail == manager.expected_command(), detail)
    check("enable 后 is_enabled 为真", manager.is_enabled())
    check("enable 后 is_stale 为假（两者互斥）", not manager.is_stale())
    check("值名用的是约定的 VALUE_NAME", VALUE_NAME in backend.values, list(backend.values))

    ok2, detail2 = manager.enable()
    check("重复 enable 仍然成功且结果一致",
          ok2 and detail2 == detail and len(backend.values) == 1)

    ok, detail = manager.disable()
    check("disable 成功且无错误说明", ok and detail == "", repr(detail))
    check("disable 后条目不存在", VALUE_NAME not in backend.values)
    check("disable 后 is_enabled 为假", not manager.is_enabled())
    ok, _ = manager.disable()
    check("条目本来就不存在时 disable 也算成功（用户要的结果是「关着」）", ok)

    def boom(name, value):
        raise OSError("注入的写入失败")

    backend.values.clear()
    backend.write = boom
    ok, detail = manager.enable()
    check("写入抛 OSError 时 enable 如实返回失败", not ok and "失败" in detail, detail)

    silent_backend = DictBackend()
    manager_silent = make_manager(backend=silent_backend)
    original_write = silent_backend.write
    silent_backend.write = lambda name, value: None      # 假装写成功但什么都没写
    ok, detail = manager_silent.enable()
    check("写入「成功」但回读不一致 → 判为失败（回读这一步不能省）",
          not ok and "回读" in detail, detail)
    silent_backend.write = original_write

    # =====================================================================
    section("4. 状态判定：enabled / stale / state() 快照")
    # =====================================================================
    backend2 = DictBackend()
    old_mgr = make_manager(EXE_PLAIN, backend=backend2)
    old_mgr.enable()
    moved_mgr = make_manager(r"E:\moved\PersonalSystem.exe", backend=backend2)
    state = moved_mgr.state()
    check("条目指着别处时 enabled 为假", state["enabled"] is False)
    check("条目指着别处时 stale 为真", state["stale"] is True)
    check("state() 原样给出注册表里的命令", state["command"] == old_mgr.expected_command(),
          state["command"])
    check("state() 给出本程序期望的命令", state["expected"] == moved_mgr.expected_command())
    check("state() 带出值名与键路径",
          state["value_name"] == VALUE_NAME and state["key_path"] == RUN_KEY_PATH)
    check("没有任何条目时 enabled / stale 都是假",
          make_manager(backend=DictBackend()).state()["stale"] is False)

    # =====================================================================
    section("5. 漂移自愈：只修该修的那一种")
    # =====================================================================
    backend3 = DictBackend()
    first = make_manager(r"C:\old\PersonalSystem.exe", backend=backend3)
    first.enable()
    remembered = first.expected_command()
    second = make_manager(r"C:\new\PersonalSystem.exe", backend=backend3)
    result = second.repair_drift(remembered)
    check("搬迁后自愈生效", result["repaired"] is True, result["message"])
    check("自愈后条目指向新位置", second.is_enabled())
    check("自愈后不再陈旧", not second.is_stale())

    result = second.repair_drift(remembered)
    check("已经一致时不再动手", result["repaired"] is False and result["message"] == "")

    third = make_manager(r"C:\third\PersonalSystem.exe", backend=backend3)
    result = third.repair_drift(remembered)
    check("记着的位置和注册表里对不上（被别人改过）→ 不修", result["repaired"] is False)
    check("不修的时候给出原因", bool(result["message"]), result["message"])

    backend4 = DictBackend()
    gone = make_manager(EXE_PLAIN, backend=backend4)
    result = gone.repair_drift(r'"C:\whatever.exe" --autostart')
    check("条目被删掉时不复活它（不跟用户的选择对着干）",
          result["repaired"] is False and backend4.values == {})

    backend5 = DictBackend()
    alien = make_manager(EXE_PLAIN, backend=backend5)
    backend5.write(VALUE_NAME, r'"C:\someone\else.exe" --whatever')
    result = alien.repair_drift(r'"C:\whatever.exe" --autostart')
    check("条目是别人的内容时一律不碰",
          result["repaired"] is False
          and backend5.read(VALUE_NAME) == r'"C:\someone\else.exe" --whatever')

    # =====================================================================
    section("6. 启动标记解析")
    # =====================================================================
    check("只有 --autostart 时命中", is_autostart_launch([AUTOSTART_FLAG]) is True)
    check("大小写混写也命中（用户手抄会写成 --AutoStart）",
          is_autostart_launch(["--AutoStart"]) is True)
    check("夹在别的参数中间也命中",
          is_autostart_launch(["--foo", AUTOSTART_FLAG, "--bar"]) is True)
    check("前后带空格的也命中", is_autostart_launch(["  --autostart  "]) is True)
    check("没有参数时不命中", is_autostart_launch([]) is False)
    check("别的参数不命中", is_autostart_launch(["--minimized", "-a"]) is False)
    check("--autostart=1 这种带等号的形式不命中（我们写的就是裸标记）",
          is_autostart_launch(["--autostart=1"]) is False)
    check("子串不命中（--autostartx）", is_autostart_launch(["--autostartx"]) is False)
    check("不传自定义 argv 时读进程自己的命令行（现在没带标记）",
          is_autostart_launch() is False)

    # =====================================================================
    section("7. 凭据解析")
    # =====================================================================
    good = write_remember("good.json", {"remember": True,
                                        "username": b64("admin"), "password": b64("p@ss")})
    data = load_remember_file(good)
    check("正常文件：解出三个字段",
          data == {"username": "admin", "password": "p@ss", "remember": True}, data)
    check("正常文件：严格取值拿到二元组",
          read_remembered_credentials([good]) == ("admin", "p@ss"))

    unremembered = write_remember("unremembered.json",
                                  {"remember": False, "username": b64("a"), "password": b64("b")})
    check("没勾「记住密码」→ 空字典", load_remember_file(unremembered) == {})
    check("没勾「记住密码」→ 拿不到凭据", read_remembered_credentials([unremembered]) is None)

    broken = write_remember("broken.json", "{not json at all")
    check("坏 JSON → 空字典且不抛异常", load_remember_file(broken) == {})

    notdict = write_remember("list.json", "[1, 2, 3]")
    check("JSON 是数组而不是对象 → 空字典", load_remember_file(notdict) == {})

    missing = TMP / "definitely_missing.json"
    check("文件不存在 → 空字典", load_remember_file(missing) == {})

    bad_b64 = write_remember("bad_b64.json", {"remember": True,
                                              "username": "A", "password": "@@@@"})
    bad_data = load_remember_file(bad_b64)
    check("坏 base64 → 不抛异常，字段退化成空串",
          isinstance(bad_data, dict) and bad_data.get("username") == ""
          and bad_data.get("password") == "", bad_data)
    check("坏 base64 → 严格取值拿不到凭据", read_remembered_credentials([bad_b64]) is None)

    empty_fields = write_remember("empty.json", {"remember": True, "username": "", "password": ""})
    empty_data = load_remember_file(empty_fields)
    check("勾了记住但字段是空的 → 原样给出空串"
          "（登录框的预填行为取决于这里，不能替它改成默认值）",
          empty_data == {"username": "", "password": "", "remember": True}, empty_data)
    check("字段为空 → 静默登录拿不到凭据（不能拿着空密码去撞运气）",
          read_remembered_credentials([empty_fields]) is None)

    second_good = write_remember("second.json", {"remember": True,
                                                 "username": b64("u2"), "password": b64("p2")})
    check("候选路径：第一个不存在就取第二个",
          read_remembered_credentials([missing, second_good]) == ("u2", "p2"))
    check("候选路径：第一个坏掉也继续往后找",
          read_remembered_credentials([broken, second_good]) == ("u2", "p2"))
    check("候选路径：全都不可用则返回 None",
          read_remembered_credentials([missing, broken, unremembered]) is None)
    check("候选路径：第一个可用就优先（不会被后面的覆盖）",
          read_remembered_credentials([good, second_good]) == ("admin", "p@ss"))
    check("单传一个路径（不是列表）也支持",
          read_remembered_credentials(good) == ("admin", "p@ss"))
    check("传空/None 时不炸", read_remembered_credentials([]) is None
          and read_remembered_credentials(None) is None)
    check("文件名常量就是 remember_me.json", REMEMBER_FILE_NAME == "remember_me.json")

    # =====================================================================
    section("8. 真注册表后端（临时键路径，跑完删干净）")
    # =====================================================================
    import winreg                                       # noqa: E402

    TEST_KEY_PATH = r"Software\ServerTimeDemoTest\AutostartProbe\Run"
    TEST_VALUE = "ServerTimeDemoAutostartProbe"

    def drop_test_key(path):
        parts = path.split("\\")
        for depth in range(len(parts), 0, -1):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, "\\".join(parts[:depth]))
            except OSError:
                pass

    drop_test_key(TEST_KEY_PATH)
    # ★ 先记下生产 Run 键里我们那条值名当前的样子，跑完再比一次 ——
    #   万一哪天测试不小心写到真键上，这条会立刻变红。
    probe_run = WinRegBackend(RUN_KEY_PATH)
    production_before = probe_run.read(VALUE_NAME)
    real_backend = WinRegBackend(TEST_KEY_PATH)
    real_mgr = StartupManager(backend=real_backend, value_name=TEST_VALUE,
                              key_path=TEST_KEY_PATH, frozen=True, executable=EXE_SPACE)
    try:
        check("临时键上初始读不到值（而且不抛异常）", real_mgr.read_command() == "")
        check("临时键上初始判定未开启", not real_mgr.is_enabled())

        ok, detail = real_mgr.enable()
        check("真注册表写入成功", ok, detail)
        check("真注册表回读一致", real_mgr.read_command() == real_mgr.expected_command(),
              real_mgr.read_command())

        handle = winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_PATH, 0, winreg.KEY_READ)
        try:
            raw = winreg.QueryValueEx(handle, TEST_VALUE)[0]
        finally:
            winreg.CloseKey(handle)
        check("真注册表里那条值的原文就是写入的命令", raw == real_mgr.expected_command(), raw)

        check("真注册表上 is_enabled 为真", real_mgr.is_enabled())
        ok, detail = real_mgr.disable()
        check("真注册表删除成功", ok, repr(detail))
        check("删除后读不到值", real_mgr.read_command() == "")
        ok, _ = real_mgr.disable()
        check("重复删除也算成功（幂等）", ok)

        check("全程没有碰真正的 Run 键（写的自始至终是临时键）",
              probe_run.read(VALUE_NAME) == production_before,
              f"跑前={production_before!r} 跑后={probe_run.read(VALUE_NAME)!r}")
    finally:
        drop_test_key(TEST_KEY_PATH)

    # 顺手确认清理干净了
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_PATH, 0, winreg.KEY_READ)
        leaked = True
    except FileNotFoundError:
        leaked = False
    check("临时键已彻底清理（不留垃圾）", not leaked)

    # =====================================================================
    section("9. 常量与接线")
    # =====================================================================
    main_src = (ROOT / "main.py").read_text(encoding="utf-8")
    spec_src = (ROOT / "ExpiryManager_fixed.spec").read_text(encoding="utf-8")
    dialog_src = (ROOT / "expiry_dialogs.py").read_text(encoding="utf-8")

    check("state 键名没有和已有键撞（autostart / autostart_command）",
          STATE_INTENT_KEY == "autostart" and STATE_COMMAND_KEY == "autostart_command")

    check("main.py 里构造了 StartupManager", "StartupManager(script=" in main_src)
    check("main.py 里读了启动标记", "is_autostart_launch()" in main_src)
    check("main.py 里用了静默登录", "def try_silent_login" in main_src
          and "self.try_silent_login()" in main_src)
    check("main.py 的 startup_sequence 支持 silent 开关",
          "def startup_sequence(self, silent: bool = False):" in main_src)
    check("静默路径不弹「到期汇总」模态框",
          "if not silent:\n            self.show_reminder_popup()" in main_src.replace("\r\n", "\n"))
    check("静默启动时窗口被 withdraw",
          "if self.autostart_silent:\n            self.withdraw()" in main_src.replace("\r\n", "\n"))
    check("启动时有自启动条目自检", "self.sync_autostart_on_startup()" in main_src)
    check("托盘菜单里有「开机自启动」",
          'pystray.MenuItem("开机自启动"' in main_src)
    check("托盘勾的状态是现算的（绑定到 autostart_checked）",
          "checked=self.autostart_checked" in main_src)
    check("开完开关会刷新托盘菜单", "def refresh_menu" in main_src)
    check("设置对话框把意愿交出来", 'dialog.result["autostart"]' in main_src)
    check("登录框复用了同一套凭据解析",
          "return load_remember_file(self.REMEMBER_FILE)" in main_src)
    check("登录框里不再自己解 base64（避免两套解析走岔）",
          "base64.b64decode(data.get(" not in main_src)

    check("设置对话框有「开机自启动」分组", 'text="开机自启动"' in dialog_src)
    check("设置对话框的勾选框是静默到托盘的说法",
          "静默运行到系统托盘" in dialog_src)
    check("设置对话框自己不碰注册表（不 import startup_manager）",
          "startup_manager" not in dialog_src, "对话框只收集意愿，落地归主窗口")
    check("文案标了「只对当前用户生效」", "只对当前用户生效" in dialog_src)

    check("spec 的 hiddenimports 登记了 startup_manager", "'startup_manager'" in spec_src)

    from app_version import APP_VERSION          # noqa: E402
    check("版本号是 1.15.x 或更高（本功能随次版本发布）",
          tuple(int(x) for x in APP_VERSION.split(".")) >= (1, 15, 0), APP_VERSION)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 76)
print(f"通过 {len(passed)} 项，失败 {len(failed)} 项")
for item in failed:
    print(f"  FAIL  {item}")
print("=" * 76)
sys.exit(1 if failed else 0)
