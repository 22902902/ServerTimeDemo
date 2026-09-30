# -*- coding: utf-8 -*-
"""开机自启动的 UI 接线测试 —— 用一个**真实的**主窗口跑，而且这个窗口是
「被开机自启动拉起来的那一次」（argv 里带 --autostart）。

为什么只能建一个窗口：同一个进程里建第二个 ``tk.Tk()`` 会撞上 Tk 的经典问题
（``image "pyimage1" doesn't exist`` —— 第一张 PhotoImage 跟着已销毁的解释器走了）。
``test_shell_ui.py`` 也是这么处理的。所以分工是：

* 本套件：**带 --autostart** 的那条路（静默、托盘、开关落地）。
* ``test_shell_ui.py``：**不带 --autostart** 的那条路（顺带断言「不自作静默」）。
* ``test_startup.py``：纯数据层，不建窗口。

★ 只读 / 不越界纪律：

* 注册表全程用 ``DictBackend``（内存字典），**真注册表一个字节都不碰**。
* 跑完把 ``app_state`` 整表还原（``apply_autostart`` 会往里记账）。

用法：
    python scripts/test_startup_ui.py
"""
import base64
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from startup_manager import (      # noqa: E402
    DictBackend,
    STATE_COMMAND_KEY,
    STATE_INTENT_KEY,
    StartupManager,
    VALUE_NAME,
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


def snapshot_state(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return {k: v for k, v in conn.execute(
            "SELECT state_key, state_value FROM app_state")}
    finally:
        conn.close()


def restore_state(db_path, snapshot):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DELETE FROM app_state")
        conn.executemany(
            "INSERT INTO app_state (state_key, state_value) VALUES (?, ?)",
            list(snapshot.items()))
        conn.commit()
    finally:
        conn.close()


import main  # noqa: E402

# ---------------------------------------------------------------------------
# 夹具库：本套件**自己造**一份，不用真实的开发库 / 随身包
# ---------------------------------------------------------------------------
# 两个理由：
#   1. 仓库根的老库已删（数据只留随身包一处），指着它只会 OperationalError；
#   2. 收尾要 ``DELETE FROM app_state`` 再灌回去 —— 这是**写**操作，
#      落在真实数据上是不能接受的。自建之后，写坏了也只是坏一份探针文件。
# ``build/`` 已被 gitignore，所以它不会进仓库。
FIXTURE_DB = ROOT / "build" / "probe" / "__startup_ui_fixture.db"
FIXTURE_DB.parent.mkdir(parents=True, exist_ok=True)
if FIXTURE_DB.exists():
    FIXTURE_DB.unlink()          # 每次重建，状态确定

_fx = main.Database(FIXTURE_DB)  # 顺带把全部表建出来
_fx.conn.execute(
    "INSERT INTO assets (record_no, platform, resource_type, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?)",
    ("__probe__", "__probe__", "__probe__", "2026-01-01T00:00:00",
     "2026-01-01T00:00:00"))
_fx.conn.commit()
_fx.close()

# ★ 必须在构造 App **之前**改：ExpiryManagerApp.__init__ 里
#   ``self.db = Database(DB_PATH)`` 是运行时取模块全局，改早了才生效。
main.DB_PATH = FIXTURE_DB

snapshot = snapshot_state(main.DB_PATH)
app = None

try:
    # ---------------------------------------------------------------------
    section("构造：模拟「开机自启动拉起」的那一次进程")
    # ---------------------------------------------------------------------
    # prompt_login / poll_external_commands 都换成空操作：登录弹窗是模态的，
    # 会在 wait_window 上把测试挂住；而这里本来就要**手工**调 try_silent_login
    # 去逐条验它。这跟 test_shell_ui.py 的手法一致。
    main.ExpiryManagerApp.prompt_login = lambda self: None
    main.ExpiryManagerApp.poll_external_commands = lambda self: None

    saved_argv = sys.argv
    sys.argv = [saved_argv[0], "--autostart"]
    try:
        app = main.ExpiryManagerApp()
    finally:
        sys.argv = saved_argv
    app.update_idletasks()

    check("带 --autostart 时 autostart_silent 为真", app.autostart_silent is True)
    check("窗口是 withdraw 的（开机时不弹脸）",
          app.winfo_ismapped() == 0 and app.state() == "withdrawn",
          f"state={app.state()} mapped={app.winfo_ismapped()}")
    check("startup_manager 已就绪", isinstance(app.startup_manager, StartupManager))
    check("期望命令里带着 --autostart 标记",
          "--autostart" in app.startup_manager.expected_command(),
          app.startup_manager.expected_command())

    # ---------------------------------------------------------------------
    section("开关落地（内存后端，不碰真注册表）")
    # ---------------------------------------------------------------------
    fake = DictBackend()
    app.startup_manager = StartupManager(frozen=True,
                                         executable=r"C:\App\PersonalSystem.exe",
                                         backend=fake)
    check("初始：未开启也不陈旧",
          not app.startup_manager.is_enabled() and not app.startup_manager.is_stale())
    check("初始说明是「未设置」", app.autostart_note() == "当前记录：未设置",
          app.autostart_note())

    ok, message, changed = app.apply_autostart(True)
    check("开启成功且报告「改了」", ok and changed, message)
    check("后端里真的写进了命令", fake.read(VALUE_NAME) != "", fake.read(VALUE_NAME))
    check("写进去的就是当前期望的那条",
          fake.read(VALUE_NAME) == app.startup_manager.expected_command())
    check("app_state 记下了意图", app.db.get_state(STATE_INTENT_KEY, "") == "1")
    check("app_state 记下了命令",
          app.db.get_state(STATE_COMMAND_KEY, "") == app.startup_manager.expected_command())
    check("开启后 is_enabled 为真", app.startup_manager.is_enabled())
    check("开启后说明显示真实命令",
          app.autostart_note() == f"当前记录：{app.startup_manager.expected_command()}",
          app.autostart_note())

    ok, message, changed = app.apply_autostart(True)
    check("再点一次开启：不重复写注册表（changed 为假）", ok and not changed, message)

    ok, message, changed = app.apply_autostart(False)
    check("关闭成功且报告「改了」", ok and changed, message)
    check("后端里的条目已删除", fake.read(VALUE_NAME) is None)
    check("app_state 意图清零", app.db.get_state(STATE_INTENT_KEY, "") == "0")

    ok, message, changed = app.apply_autostart(False)
    check("再点一次关闭：不动作（changed 为假）", ok and not changed, message)

    # 程序搬到别处 -> 条目变「陈旧」，说明文案要点明
    app.startup_manager = StartupManager(frozen=True,
                                         executable=r"E:\moved\PersonalSystem.exe",
                                         backend=fake)
    fake.write(VALUE_NAME, app.startup_manager.expected_command())
    app.startup_manager = StartupManager(frozen=True,
                                         executable=r"E:\moved2\PersonalSystem.exe",
                                         backend=fake)
    check("搬家后判为陈旧", app.startup_manager.is_stale())
    check("陈旧时说明点出「指向别处」", "指向别处" in app.autostart_note(),
          app.autostart_note())

    # ---------------------------------------------------------------------
    section("启动自检：漂移自愈与「不该动手时不动手」")
    # ---------------------------------------------------------------------
    fake2 = DictBackend()
    origin = StartupManager(frozen=True, executable=r"C:\Old\PersonalSystem.exe",
                            backend=fake2)
    origin.enable()
    app.db.set_state(STATE_INTENT_KEY, "1")
    app.db.set_state(STATE_COMMAND_KEY, origin.expected_command())
    app.startup_manager = StartupManager(frozen=True,
                                         executable=r"C:\Moved\PersonalSystem.exe",
                                         backend=fake2)
    check("自检前：条目指着老位置", app.startup_manager.is_stale())
    app.sync_autostart_on_startup()
    check("自检后：条目改到了新位置", app.startup_manager.is_enabled())
    check("自检后：app_state 里的命令同步更新",
          app.db.get_state(STATE_COMMAND_KEY, "") == app.startup_manager.expected_command())

    fake2.write(VALUE_NAME, r'"C:\Someone\Else.exe" --whatever')
    app.sync_autostart_on_startup()
    check("条目被别人改成别的内容时一律不碰",
          fake2.read(VALUE_NAME) == r'"C:\Someone\Else.exe" --whatever',
          fake2.read(VALUE_NAME))

    fake2.delete(VALUE_NAME)
    app.sync_autostart_on_startup()
    check("条目被删掉时不偷偷加回来（不跟用户的选择对着干）",
          fake2.read(VALUE_NAME) is None)

    app.db.set_state(STATE_INTENT_KEY, "0")
    fake2.write(VALUE_NAME, origin.expected_command())
    app.sync_autostart_on_startup()
    check("意图是「关」时自检不动注册表",
          fake2.read(VALUE_NAME) == origin.expected_command())

    # ---------------------------------------------------------------------
    section("托盘菜单")
    # ---------------------------------------------------------------------
    app.startup_manager = StartupManager(frozen=True,
                                         executable=r"C:\App\PersonalSystem.exe",
                                         backend=DictBackend())
    app.tray.start()
    app.update_idletasks()
    check("托盘挂起来了（pystray 可用）", app.tray.started)
    if app.tray.started:
        labels = [str(item.text) for item in app.tray.icon.menu]
        check("菜单里有「开机自启动」", "开机自启动" in labels, f"菜单={labels}")
        check("原有三项都还在",
              {"显示窗口", "立即检查提醒", "退出程序"} <= set(labels), f"菜单={labels}")
        check("顺序：自启动排在「退出程序」之前",
              labels.index("开机自启动") < labels.index("退出程序"), f"菜单={labels}")
        target = [it for it in app.tray.icon.menu
                  if str(it.text) == "开机自启动"][0]
        # pystray 的 MenuItem.checked 是**属性**：取的时候已经把 callable 求过值了，
        # 这也正是「改完必须 update_menu()」的根源。
        check("未开启时菜单勾为假", target.checked is False)
        app.startup_manager.backend.write(VALUE_NAME,
                                          app.startup_manager.expected_command())
        check("开启后菜单勾为真（现算，不缓存）", target.checked is True)
        check("「显示窗口」被标成了默认项（双击托盘图标即打开）",
              any(getattr(it, "default", False) and str(it.text) == "显示窗口"
                  for it in app.tray.icon.menu))

        # refresh_menu 的作用是把菜单重画一遍；直接数它有没有真的调到 update_menu
        calls = []
        original_update = app.tray.icon.update_menu
        app.tray.icon.update_menu = lambda: calls.append(1)
        try:
            app.tray.refresh_menu()
        finally:
            app.tray.icon.update_menu = original_update
        check("refresh_menu 真的去重画了菜单（否则勾会停在旧状态）", calls == [1],
              f"调用 {len(calls)} 次")

        idle = main.TrayController(app)
        idle.refresh_menu()
        check("还没挂图标时 refresh_menu 直接返回、不报错", idle.icon is None)
    app.tray.stop()

    # ---------------------------------------------------------------------
    section("静默登录：三道闸")
    # ---------------------------------------------------------------------
    original_remember = main.LoginDialog.REMEMBER_FILE
    original_verify = app.db.verify_user
    original_must = app.db.get_must_change_password
    try:
        # 闸 1：没有凭据
        main.LoginDialog.REMEMBER_FILE = ROOT / "build" / "probe" / "__no_such_remember.json"
        check("没有「记住密码」文件时静默登录失败", app.try_silent_login() is False)
        check("失败后窗口依然没显示（等 prompt_login 去 deiconify）",
              app.winfo_ismapped() == 0)

        # 闸 2：凭据失效
        # 夹具**自己造**，不要指 dist/ —— 那个目录随随身包方案已删，
        # 指着它会让后面 4 条断言恒红，而且看着像静默登录坏了。
        # 格式与 LoginDialog._save_remembered 一致（base64 混淆）。
        probe_remember = ROOT / "build" / "probe" / "__remember_ui.json"
        probe_remember.parent.mkdir(parents=True, exist_ok=True)
        probe_remember.write_text(json.dumps({
            "remember": True,
            "username": base64.b64encode(b"probe_user").decode("ascii"),
            "password": base64.b64encode(b"probe_pass").decode("ascii"),
        }), encoding="utf-8")
        main.LoginDialog.REMEMBER_FILE = probe_remember
        app.db.verify_user = lambda u, p: False
        check("记住的凭据过不了 verify_user 时失败", app.try_silent_login() is False)

        # 闸 3：需要强制改密码
        app.db.verify_user = lambda u, p: True
        app.db.get_must_change_password = lambda u: True
        check("账号需要先改密码时失败", app.try_silent_login() is False)

        # 三道闸都过
        app.db.get_must_change_password = lambda u: False
        # 保险：万一库里没资产，别让它真去导入 Excel（那是一次真实写库）。
        # 不拦 fetch_assets —— 它还被 refresh_table(keyword=...) 用着，打桩反而会炸。
        imported = []
        app.import_excel = lambda *a, **kw: imported.append((a, kw))
        check("（前置）库里本来就有资产，不会走导入分支", bool(app.db.fetch_assets()))
        popups = []
        app.show_reminder_popup = lambda: popups.append("popup")
        ok = app.try_silent_login()
        check("三道闸都过时静默登录成功", ok is True)
        check("静默登录后窗口仍是 withdraw 的（真的没弹脸）",
              app.winfo_ismapped() == 0, f"state={app.state()}")
        check("静默启动时不弹「到期汇总」模态框", popups == [], f"popups={popups}")
        check("静默启动没有偷偷导入 Excel", imported == [], f"imported={imported}")
        check("静默启动把托盘拉起来了", app.tray.started)
        check("静默启动也把周期巡检接上了（startup_completed 为真）",
              app.startup_completed is True)
        check("状态栏留下了可发现的提示（否则用户不知道它起来了）",
              "托盘" in app.status_var.get(), app.status_var.get())
    finally:
        main.LoginDialog.REMEMBER_FILE = original_remember
        app.db.verify_user = original_verify
        app.db.get_must_change_password = original_must
        app.tray.stop()
finally:
    if app is not None:
        try:
            app.tray.stop()
        except Exception:
            pass
        try:
            app.destroy()
        except Exception:
            pass
    restore_state(main.DB_PATH, snapshot)
    print("\n  app_state 已还原")

print()
print("=" * 76)
print(f"通过 {len(passed)} 项，失败 {len(failed)} 项")
for item in failed:
    print(f"  FAIL  {item}")
print("=" * 76)
sys.exit(1 if failed else 0)
