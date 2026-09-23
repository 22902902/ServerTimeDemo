# -*- coding: utf-8 -*-
"""流程中心回归测试（数据层 + 脚本生成 + 建表迁移，纯逻辑、不碰 Tk）。

为什么单独成篇
------------------------------------------------------------------------------
流程中心这一轮从「备案专用表单」改成了「通用操作流程记录」：步骤多了类型、
命令、前置检查、预期结果，流程多了变量，另外还加了执行留痕。这里面最容易
算错、又最不容易被肉眼发现的几件事：

* **建表迁移**：新列是「新库写进 CREATE TABLE、老库靠 ALTER 补上」两条路。
  只测一条就会漏 —— 老库补列失败的后果是启动直接崩，而新库路径测不出这个。
* **级联删除**：``process_steps`` 的外键要靠 ``PRAGMA foreign_keys = ON`` 才生效；
  这个 PRAGMA 是**每连接**的，忘了开就变成一堆孤儿行，界面上看不出来。
* **{{变量}} 插值**：值为空时必须**原样保留** ``{{键}}``，不能替换成空串 ——
  换成空串会生成 ``cd /www/`` 这种看着正常、实际删错目录的命令。
* **危险命令识别**：宁可漏报也不能大量误报，否则红标就没人看了；同时
  ``rm -rf`` 与 ``rm -r`` 必须区别对待（后者是日常操作）。
* **拼脚本**：只输出「有命令的步骤」，把说明型步骤跳过。

另一类被锁死的是「有意设计」：
* ``rm -rf`` 标红但**不阻断**（运维本来就要用）
* 变量定义用 JSON 落库，坏数据（非 JSON / 非列表 / 缺 key）一律降级为空表，
  不把整个流程页拦下来

覆盖：
A. 步骤类型    label_to_step_kind / step_kind_label 往返与兜底
B. 危险命令    danger_reasons / is_dangerous_command（正例 / 反例 / 去重）
C. 变量        parse / serialize / default / extract_variable_keys / render_template
D. 拼脚本      build_run_script（变量渲染 / 空命令跳过 / 无命令返回空）
E. 建表迁移    新库一次到位 / 幂等 / 老库补列不丢数据 / 级联删除
F. 流程 CRUD   增删改查 / 收藏 / 变量落库 / 排序
G. 步骤 CRUD   增删改查 / 序号 / 上下移动 / 重排 / 危险标记
H. 搜索        命中流程字段与步骤内容 / 不重复出行 / 命中步骤 id 集合
I. 执行留痕    开跑 / 勾选 / 计数 / 结束 / 历史 / 快照 / 级联

用法：
    python scripts/test_process.py
"""

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from process_db import (  # noqa: E402
    COMMAND_LANGS,
    FLOW_COLUMN_MIGRATIONS,
    RUN_STATUS_ABORTED,
    RUN_STATUS_DONE,
    RUN_STATUS_RUNNING,
    STEP_COLUMN_MIGRATIONS,
    STEP_KIND_CHECK,
    STEP_KIND_CHOICES,
    STEP_KIND_CMD,
    STEP_KIND_LABELS,
    STEP_KIND_NOTE,
    STEP_KIND_OP,
    ProcessDBMixin,
    build_run_script,
    danger_reasons,
    default_variable_values,
    extract_variable_keys,
    init_process_tables,
    is_dangerous_command,
    label_to_step_kind,
    parse_variables,
    render_template,
    serialize_variables,
    step_kind_label,
)

PASSED = 0
FAILED = 0
_TMP: list[Path] = []


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


class Host(ProcessDBMixin):
    """最小宿主：只提供 self.conn —— 这正是混入约定的全部依赖。"""

    def __init__(self, path=None):
        self.conn = sqlite3.connect(str(path or ":memory:"))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_process_tables(self.conn)


def fresh(name: str) -> Host:
    """每个小节一个独立库：这些用例大量依赖「初始状态」，共用会互相污染。"""
    d = Path(tempfile.mkdtemp(prefix="process_test_"))
    _TMP.append(d)
    return Host(d / f"{name}.db")


def cleanup() -> None:
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


def _titles(host: Host, flow_id: int) -> list:
    return [row["title"] for row in host.fetch_process_steps(flow_id)]


# ══════════════════════════════════════════════════════════════════════════
# A. 步骤类型
# ══════════════════════════════════════════════════════════════════════════
def test_step_kind() -> None:
    section("A. 步骤类型：中文标签 ↔ 内部 kind")
    for kind in (STEP_KIND_OP, STEP_KIND_CMD, STEP_KIND_CHECK, STEP_KIND_NOTE):
        check(f"往返 {kind} -> 标签 -> {kind}",
              label_to_step_kind(step_kind_label(kind)) == kind,
              step_kind_label(kind))
    check("认不出中文时兜底成操作型", label_to_step_kind("随手写的") == STEP_KIND_OP)
    check("空标签兜底成操作型", label_to_step_kind("") == STEP_KIND_OP)
    check("None 兜底成操作型", label_to_step_kind(None) == STEP_KIND_OP)
    check("也接受直接传内部 kind", label_to_step_kind("cmd") == STEP_KIND_CMD)
    check("未知 kind 转标签兜底成操作型", step_kind_label("nope") == "操作型")
    check("空 kind 转标签兜底成操作型", step_kind_label("") == "操作型")
    check("选项数 == 类型数", len(STEP_KIND_CHOICES) == len(STEP_KIND_LABELS))
    check("选项顺序与 STEP_KIND_LABELS 一致",
          STEP_KIND_CHOICES == [STEP_KIND_LABELS[k] for k in
                                (STEP_KIND_OP, STEP_KIND_CMD, STEP_KIND_CHECK, STEP_KIND_NOTE)])
    check("命令语言清单一律小写且含 shell",
          "shell" in COMMAND_LANGS and all(x == x.lower() for x in COMMAND_LANGS))


# ══════════════════════════════════════════════════════════════════════════
# B. 危险命令识别
# ══════════════════════════════════════════════════════════════════════════
DANGEROUS_SAMPLES = [
    ("rm -rf /var/www", "递归强制删除"),
    ("sudo rm -fr /tmp/site", "递归强制删除"),
    ("mkfs.ext4 /dev/sdb1", "格式化文件系统"),
    ("dd if=/dev/zero of=/dev/sda bs=1M", "裸写设备"),
    ("cat x.iso > /dev/sda", "覆盖磁盘设备"),
    ("git reset --hard HEAD~3", "丢弃工作区改动"),
    ("git clean -fd", "删除未跟踪文件"),
    ("git push --force origin main", "强制推送远端"),
    ("git push -f", "强制推送远端"),
    ("DROP TABLE process_steps", "删除数据库对象"),
    ("truncate table process_runs", "清空数据表"),
    ("DELETE FROM process_flows", "无条件的 DELETE"),
    ("chmod -R 777 /var/www", "放开全部权限"),
    ("chmod 777 upload.sh", "放开全部权限"),
    ("shutdown -h now", "关机 / 重启"),
    ("reboot", "关机 / 重启"),
    ("kill -9 1234", "强制杀进程"),
    ("systemctl stop nginx", "停止系统服务"),
    (":(){ :|:& };:", "fork 炸弹"),
]

SAFE_SAMPLES = [
    "ls -la /var/www",
    "rm -r build",                       # 没有 f：只是删目录，不拦
    "rm -f /tmp/onefile",                # 没有 r：只删文件
    "cd /www/site && npm run build",
    "git commit -m 'fix: 改样式'",
    "git push origin main",              # 没有 force
    "git reset --soft HEAD~1",
    "DELETE FROM process_flows WHERE id = 3",
    "chmod 755 deploy.sh",
    "systemctl status nginx",
    "systemctl restart nginx",
    "dd if=/dev/sda of=/backup/sda.img",  # 是读设备写文件，不是裸写设备
    "kill 1234",
    "nano /etc/nginx/nginx.conf",
    "mysql -u root -p -e 'SELECT 1'",
]


def test_danger() -> None:
    section("B. 危险命令识别：正例 / 反例 / 去重")
    for text, reason in DANGEROUS_SAMPLES:
        reasons = danger_reasons(text)
        check(f"命中「{reason}」：{text}", reason in reasons, reasons)
    for text in SAFE_SAMPLES:
        check(f"不误报：{text}", danger_reasons(text) == [], danger_reasons(text))
    check("空文本不命中", danger_reasons("", None) == [])
    check("多段文本一起判，命中任一即真",
          danger_reasons("ls", "rm -rf /data") == ["递归强制删除"])
    check("多个文本命中同一原因只报一次",
          danger_reasons("DROP TABLE a", "drop table b") == ["删除数据库对象"])
    check("一段文本命中两个原因都报",
          set(danger_reasons("rm -rf / && systemctl stop nginx"))
          == {"递归强制删除", "停止系统服务"})
    check("is_dangerous_command 与 danger_reasons 一致",
          is_dangerous_command("git reset --hard") is True
          and is_dangerous_command("git status") is False)


# ══════════════════════════════════════════════════════════════════════════
# C. 变量
# ══════════════════════════════════════════════════════════════════════════
def test_variables() -> None:
    section("C. 变量：解析 / 序列化 / 取值 / 占位符")

    # —— 解析的坏数据兜底 ——
    for bad, why in (("", "空串"), (None, "None"), ("   ", "纯空白"),
                     ("不是 JSON", "非法 JSON"), ('{"a": 1}', "是对象不是列表"),
                     ("[1, 2, 3]", "元素不是对象"), ('[{"label": "没键名"}]', "缺 key")):
        check(f"坏数据降级为空表（{why}）", parse_variables(bad) == [], parse_variables(bad))
    check("直接传 list 也接受",
          parse_variables([{"key": "域名"}]) ==
          [{"key": "域名", "label": "域名", "default": "", "hint": ""}])
    check("label 缺省时用 key 兜底",
          parse_variables([{"key": "env", "default": "prod"}])[0]["label"] == "env")
    check("key 两侧空白被裁掉",
          parse_variables([{"key": "  域名  "}])[0]["key"] == "域名")
    check("非字符串 default 会转成字符串",
          parse_variables([{"key": "n", "default": 80}])[0]["default"] == "80")

    # —— 序列化 ——
    check("空列表序列化成空串（占位而非空 JSON）", serialize_variables([]) == "")
    check("空列表序列化成空串（None）", serialize_variables(None) == "")
    raw = serialize_variables([{"key": "域名", "label": "域名", "default": "example.com"}])
    check("序列化结果是 JSON 数组", json.loads(raw)[0]["key"] == "域名")
    check("序列化用 ensure_ascii=False（中文可读）", "域名" in raw)
    check("序列化丢掉没键名的项",
          json.loads(serialize_variables([{"key": ""}, {"key": "ok"}])) ==
          [{"key": "ok", "label": "ok", "default": "", "hint": ""}])
    items = [{"key": "域名", "label": "域名", "default": "example.com", "hint": "不带协议"},
             {"key": "环境", "label": "部署环境", "default": "prod", "hint": ""}]
    check("解析 ∘ 序列化 = 恒等", parse_variables(serialize_variables(items)) == items)

    # —— 默认值与键抽取 ——
    check("default_variable_values 取默认值",
          default_variable_values(items) == {"域名": "example.com", "环境": "prod"})
    check("extract_variable_keys 抽出占位符",
          extract_variable_keys("cd /www/{{域名}}") == ["域名"])
    check("extract_variable_keys 去重保序",
          extract_variable_keys("{{b}} {{a}} {{b}}") == ["b", "a"])
    check("extract_variable_keys 跨文本去重",
          extract_variable_keys("{{a}}", "{{b}}", "{{a}}") == ["a", "b"])
    check("花括号里可以有空格",
          extract_variable_keys("{{ 域名 }}") == ["域名"])
    check("单花括号不是占位符", extract_variable_keys("{域名}") == [])
    check("空文本不报错", extract_variable_keys("", None) == [])

    # —— 渲染 ——
    check("有值时替换", render_template("cd /www/{{域名}}", {"域名": "a.com"}) == "cd /www/a.com")
    check("花括号带空格也能替换",
          render_template("{{ 域名 }}", {"域名": "a.com"}) == "a.com")
    check("值为空时**原样保留**占位符",
          render_template("cd /www/{{域名}}", {"域名": ""}) == "cd /www/{{域名}}")
    check("值只有空白也原样保留",
          render_template("{{域名}}", {"域名": "   "}) == "{{域名}}")
    check("键不存在时原样保留",
          render_template("{{没定义}}", {"别的": "x"}) == "{{没定义}}")
    check("values 传 None 不炸", render_template("{{a}}", None) == "{{a}}")
    check("空文本返回空串", render_template("", {"a": "1"}) == "")
    check("None 文本返回空串", render_template(None, {"a": "1"}) == "")
    check("同一占位符出现多次全部替换",
          render_template("{{a}}-{{a}}", {"a": "x"}) == "x-x")
    check("未定义与已定义混在一起互不影响",
          render_template("{{a}}/{{b}}", {"a": "1"}) == "1/{{b}}")


# ══════════════════════════════════════════════════════════════════════════
# D. 拼脚本
# ══════════════════════════════════════════════════════════════════════════
FAKE_STEPS = [
    {"step_no": 1, "title": "切到站点目录", "command_text": "cd /www/{{域名}}",
     "precheck_text": "确认 {{域名}} 已解析"},
    {"step_no": 2, "title": "说明步骤（没有命令）", "command_text": "",
     "precheck_text": ""},
    {"step_no": 3, "title": "备份旧证书", "command_text": "cp cert.pem cert.bak\ncp key.pem key.bak",
     "precheck_text": "确认有写权限"},
]


def test_run_script() -> None:
    section("D. 拼脚本：变量渲染 / 跳过空命令 / 无命令返回空")
    check("一个命令都没有时返回空串（界面据此提示而不是给个空壳）",
          build_run_script("空流程", [{"step_no": 1, "title": "x", "command_text": ""}], {}) == "")
    check("steps 传空列表也返回空串", build_run_script("空流程", [], {}) == "")
    check("steps 传 None 也返回空串", build_run_script("空流程", None, {}) == "")

    script = build_run_script("SSL 证书更新", FAKE_STEPS, {"域名": "example.com"}, env="prod")
    check("带 shebang", script.startswith("#!/usr/bin/env bash"))
    check("带流程名", "# SSL 证书更新" in script)
    check("带环境标记", "[环境: prod]" in script)
    check("带变量速查行", "域名=example.com" in script)
    check("带 set -e", "\nset -e\n" in script)
    check("命令里的变量已渲染", "cd /www/example.com" in script)
    check("命令里不再残留占位符", "{{域名}}" not in script)
    check("前置检查已渲染并作为注释", "# 前置检查：确认 example.com 已解析" in script)
    check("步骤号与标题进注释", "# ── [1] 切到站点目录" in script)
    check("空命令的步骤被整段跳过", "说明步骤" not in script)
    check("多行命令原样保留", "cp cert.pem cert.bak\ncp key.pem key.bak" in script)
    check("结尾是一个换行而非空行", script.endswith("\n") and not script.endswith("\n\n"))
    check("步骤顺序与 step_no 一致",
          script.index("[1]") < script.index("[3]"))

    no_env = build_run_script("流程", FAKE_STEPS, {"域名": "a.com"})
    check("env 为空时不写环境标记", "[环境:" not in no_env)
    check("values 为空时不写变量速查行",
          "# 变量：" not in build_run_script("流程", FAKE_STEPS, {}))
    check("values 里的空值不写进速查行",
          "环境" not in build_run_script("流程", FAKE_STEPS, {"环境": "", "域名": "a.com"}))
    check("命令里未填的变量仍原样保留（不生成半截路径）",
          "cd /www/{{域名}}" in build_run_script("流程", FAKE_STEPS, {}))

    # sqlite3.Row 也要能喂进去（页面就是这么给的）
    host = fresh("row")
    fid = host.add_process_flow({"title": "行对象流程"})
    host.add_process_step(fid, {"step_no": 1, "title": "第一步", "command_text": "echo hi"})
    rows = host.fetch_process_steps(fid)
    check("sqlite3.Row 可以直接喂给 build_run_script",
          "echo hi" in build_run_script("行对象流程", rows, {}))


# ══════════════════════════════════════════════════════════════════════════
# E. 建表与迁移
# ══════════════════════════════════════════════════════════════════════════
LEGACY_FLOWS = """
    CREATE TABLE process_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT,
        platform TEXT,
        link_url TEXT,
        note TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""
LEGACY_STEPS = """
    CREATE TABLE process_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flow_id INTEGER NOT NULL,
        step_no INTEGER NOT NULL,
        title TEXT NOT NULL,
        link_url TEXT,
        screenshot_path TEXT,
        description_text TEXT,
        required_text TEXT,
        optional_text TEXT,
        note TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (flow_id) REFERENCES process_flows(id) ON DELETE CASCADE
    )
"""


def test_schema() -> None:
    section("E. 建表与迁移：新库到位 / 幂等 / 老库补列 / 级联")
    host = fresh("schema")
    tables = {r[0] for r in host.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for name in ("process_flows", "process_steps", "process_runs", "process_run_steps"):
        check(f"新库建出 {name}", name in tables, sorted(tables))

    step_cols = {r[1] for r in host.conn.execute("PRAGMA table_info(process_steps)")}
    for column, _ in STEP_COLUMN_MIGRATIONS:
        check(f"process_steps 新列 {column} 一次到位", column in step_cols)
    flow_cols = {r[1] for r in host.conn.execute("PRAGMA table_info(process_flows)")}
    for column, _ in FLOW_COLUMN_MIGRATIONS:
        check(f"process_flows 新列 {column} 一次到位", column in flow_cols)
    check("新库不需要再 ALTER", init_process_tables(host.conn) == [])

    # —— 老库：只有旧列，且有数据 ——
    d = Path(tempfile.mkdtemp(prefix="process_legacy_"))
    _TMP.append(d)
    path = d / "legacy.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(LEGACY_FLOWS)
    conn.execute(LEGACY_STEPS)
    conn.execute("INSERT INTO process_flows (title, category, created_at, updated_at) "
                 "VALUES ('老流程', '备案', '2026-01-01T00:00:00', '2026-01-01T00:00:00')")
    conn.execute("INSERT INTO process_steps (flow_id, step_no, title, description_text, "
                 "created_at, updated_at) VALUES (1, 1, '老步骤', '老说明', "
                 "'2026-01-01T00:00:00', '2026-01-01T00:00:00')")
    conn.commit()

    added = init_process_tables(conn)
    check("老库补列有返回（便于自检）", len(added) == len(STEP_COLUMN_MIGRATIONS) + len(FLOW_COLUMN_MIGRATIONS),
          added)
    check("老库补列包含 kind", "kind" in added)
    check("老库补列包含 favorite", "favorite" in added)
    check("补列的默认值让老步骤落成操作型",
          conn.execute("SELECT kind FROM process_steps WHERE id = 1").fetchone()["kind"] == STEP_KIND_OP)
    check("补列的默认值让老步骤不标红",
          conn.execute("SELECT danger FROM process_steps WHERE id = 1").fetchone()["danger"] == 0)
    check("补列不影响老数据（流程还在）",
          conn.execute("SELECT COUNT(*) FROM process_flows").fetchone()[0] == 1)
    check("补列不影响老数据（步骤还在）",
          conn.execute("SELECT COUNT(*) FROM process_steps").fetchone()[0] == 1)
    check("老步骤的说明文本没丢",
          conn.execute("SELECT description_text FROM process_steps WHERE id = 1").fetchone()[0] == "老说明")

    # 补完列之后混入层就能正常读老库了
    legacy = Host.__new__(Host)
    legacy.conn = conn
    rows = legacy.fetch_process_flows("")
    check("混入层能读老库（返回 1 条）", len(rows) == 1, len(rows))
    check("老库流程读得到中文标题", rows[0]["title"] == "老流程")
    check("老库流程 favorite 默认 0", int(rows[0]["favorite"] or 0) == 0)

    # —— 级联：外键要真生效 ——
    host2 = fresh("cascade")
    fid = host2.add_process_flow({"title": "待删流程"})
    for i in (1, 2, 3):
        host2.add_process_step(fid, {"step_no": i, "title": f"步骤{i}"})
    run_id = host2.start_process_run(fid)
    check("删流程前有 3 个步骤", len(host2.fetch_process_steps(fid)) == 3)
    host2.delete_process_flow(fid)
    check("删流程后步骤被级联删掉（外键生效）",
          host2.conn.execute("SELECT COUNT(*) FROM process_steps").fetchone()[0] == 0)
    check("删流程后执行记录被级联删掉",
          host2.conn.execute("SELECT COUNT(*) FROM process_runs").fetchone()[0] == 0)
    check("删流程后执行明细被级联删掉",
          host2.conn.execute("SELECT COUNT(*) FROM process_run_steps").fetchone()[0] == 0)
    host2.delete_process_run(run_id)   # 已经级联没了，再删一次不该炸
    check("删已不存在的执行记录不报错", True)


# ══════════════════════════════════════════════════════════════════════════
# F. 流程 CRUD
# ══════════════════════════════════════════════════════════════════════════
def test_flow_crud() -> None:
    section("F. 流程：增删改查 / 收藏 / 变量落库 / 排序")
    host = fresh("flow")
    fid = host.add_process_flow({
        "title": "SSL 证书更新", "category": "运维", "platform": "Linux",
        "link_url": "https://www.example.com", "note": "每 90 天一次",
    })
    row = host.get_process_flow(fid)
    check("新增后取得到", row is not None)
    check("标题落库", row["title"] == "SSL 证书更新")
    check("分类落库", row["category"] == "运维")
    check("平台落库", row["platform"] == "Linux")
    check("链接落库", row["link_url"] == "https://www.example.com")
    check("备注落库", row["note"] == "每 90 天一次")
    check("created_at 已填", bool(row["created_at"]))
    check("updated_at 已填", bool(row["updated_at"]))
    check("新流程默认不收藏", int(row["favorite"] or 0) == 0)
    check("取不存在的流程返回 None", host.get_process_flow(999999) is None)

    # —— 变量落库 ——
    items = [{"key": "域名", "label": "域名", "default": "example.com", "hint": ""}]
    fid2 = host.add_process_flow({"title": "带变量的流程", "variables": items})
    check("新增时就带变量", parse_variables(host.get_process_flow(fid2)["variables"]) == items)
    returned = host.set_process_flow_variables(fid2, items + [
        {"key": "环境", "label": "部署环境", "default": "prod", "hint": ""}])
    check("set_process_flow_variables 返回落库 JSON", "环境" in returned)
    check("变量确实写进库",
          len(parse_variables(host.get_process_flow(fid2)["variables"])) == 2)
    host.set_process_flow_variables(fid2, [])
    check("清空变量后是空串而非 '[]'", host.get_process_flow(fid2)["variables"] == "")

    # —— 整行更新 ——
    host.update_process_flow(fid, {"title": "改名后", "category": "备案",
                                   "platform": "", "link_url": "", "note": ""})
    row = host.get_process_flow(fid)
    check("整行更新改到标题", row["title"] == "改名后")
    check("整行更新改到分类", row["category"] == "备案")
    check("整行更新清空了没传的", row["note"] == "")

    # —— partial 更新：只动传进来的键 ——
    host.update_process_flow(fid, {"title": "再改名", "category": "备案",
                                   "platform": "P", "link_url": "L", "note": "N"})
    host.update_process_flow(fid, {"note": "只改备注"}, partial=True)
    row = host.get_process_flow(fid)
    check("partial 更新改到目标字段", row["note"] == "只改备注")
    check("partial 更新没把标题清空", row["title"] == "再改名")
    check("partial 更新没把分类清空", row["category"] == "备案")

    # —— 收藏与排序 ——
    host.set_process_flow_favorite(fid, True)
    check("收藏置 1", int(host.get_process_flow(fid)["favorite"]) == 1)
    host.set_process_flow_favorite(fid, False)
    check("取消收藏置 0", int(host.get_process_flow(fid)["favorite"]) == 0)
    host.set_process_flow_favorite(fid2, True)
    listed = host.fetch_process_flows("")
    check("收藏的流程排在前面", listed[0]["id"] == fid2,
          [r["title"] for r in listed])
    check("不带关键词返回全部", len(listed) == 2)

    check("按标题精确查询",
          [r["id"] for r in host.fetch_process_flows_by_title("再改名")] == [fid])
    check("按标题查不存在的返回空", host.fetch_process_flows_by_title("没这个") == [])
    host.delete_process_flow(fid)
    check("删除后查不到", host.get_process_flow(fid) is None)
    check("删掉一个后还能查到另一个", len(host.fetch_process_flows("")) == 1)


# ══════════════════════════════════════════════════════════════════════════
# G. 步骤 CRUD
# ══════════════════════════════════════════════════════════════════════════
def test_step_crud() -> None:
    section("G. 步骤：字段 / 序号 / 上下移动 / 重排 / 危险标记")
    host = fresh("step")
    fid = host.add_process_flow({"title": "流程"})
    check("空流程的下一个序号是 1", host.get_next_process_step_no(fid) == 1)

    sid = host.add_process_step(fid, {
        "step_no": 1, "title": "替换证书文件", "kind": STEP_KIND_CMD,
        "command_text": "cp new.pem /etc/nginx/cert.pem", "command_lang": "shell",
        "precheck_text": "确认新证书已上传", "expected_text": "nginx -t 通过",
        "link_url": "https://example.com", "description_text": "覆盖式替换",
        "required_text": "身份证正反面", "optional_text": "营业执照",
        "note": "老流程遗留字段",
    })
    row = host.get_process_step(sid)
    check("kind 落库", row["kind"] == STEP_KIND_CMD)
    check("command_text 落库", row["command_text"] == "cp new.pem /etc/nginx/cert.pem")
    check("command_lang 落库", row["command_lang"] == "shell")
    check("precheck_text 落库", row["precheck_text"] == "确认新证书已上传")
    check("expected_text 落库", row["expected_text"] == "nginx -t 通过")
    check("description_text 落库", row["description_text"] == "覆盖式替换")
    check("required_text 留着（备案遗留字段不删）", row["required_text"] == "身份证正反面")
    check("optional_text 留着", row["optional_text"] == "营业执照")
    check("note 留着", row["note"] == "老流程遗留字段")
    check("普通命令不标红", int(row["danger"]) == 0)

    # —— 默认值 ——
    plain = host.add_process_step(fid, {"step_no": 2, "title": "普通步骤"})
    prow = host.get_process_step(plain)
    check("不传 kind 默认操作型", prow["kind"] == STEP_KIND_OP)
    check("不传 command_lang 默认 shell", prow["command_lang"] == "shell")
    check("不传 command_text 是空串", prow["command_text"] == "")
    check("不传 step_no 会被兜成 1（不能是 0）",
          host.get_process_step(host.add_process_step(fid, {"title": "x"}))["step_no"] == 1)
    check("下一个序号按最大值 +1", host.get_next_process_step_no(fid) == 3)

    # —— 危险标记自动识别 ——
    danger_id = host.add_process_step(fid, {
        "step_no": 4, "title": "清空目录",
        "command_text": "rm -rf /www/{{域名}}/cache"})
    check("危险命令自动标红", int(host.get_process_step(danger_id)["danger"]) == 1)
    safe_id = host.add_process_step(fid, {"step_no": 5, "title": "安全命令",
                                          "command_text": "ls -la"})
    check("安全命令不标红", int(host.get_process_step(safe_id)["danger"]) == 0)
    host.update_process_step(danger_id, {"step_no": 4, "title": "改成安全的",
                                         "command_text": "ls /www"})
    check("改成安全命令后红标被撤掉",
          int(host.get_process_step(danger_id)["danger"]) == 0)
    host.update_process_step(danger_id, {"step_no": 4, "title": "再改回危险",
                                         "command_text": "git reset --hard"})
    check("改回危险命令后重新标红",
          int(host.get_process_step(danger_id)["danger"]) == 1)
    explicit = host.add_process_step(fid, {"step_no": 6, "title": "手工标红",
                                           "command_text": "ls", "danger": 1})
    check("显式传 danger=1 时不因命令安全而被清掉",
          int(host.get_process_step(explicit)["danger"]) == 1)

    # —— 单列更新 ——
    host.update_process_step_screenshot(safe_id, "account_images/a.png")
    check("只改截图不动标题",
          host.get_process_step(safe_id)["screenshot_path"] == "account_images/a.png"
          and host.get_process_step(safe_id)["title"] == "安全命令")
    host.update_process_step_title(safe_id, "改过的标题")
    check("只改标题不动截图",
          host.get_process_step(safe_id)["title"] == "改过的标题"
          and host.get_process_step(safe_id)["screenshot_path"] == "account_images/a.png")

    # —— 排序与移动 ——
    host2 = fresh("order")
    f2 = host2.add_process_flow({"title": "排序流程"})
    a = host2.add_process_step(f2, {"step_no": 1, "title": "A"})
    host2.add_process_step(f2, {"step_no": 2, "title": "B"})
    c = host2.add_process_step(f2, {"step_no": 3, "title": "C"})
    check("按 step_no 顺序返回", _titles(host2, f2) == ["A", "B", "C"])
    check("第一个不能上移", host2.move_process_step(a, -1) is False)
    check("上移失败后顺序不变", _titles(host2, f2) == ["A", "B", "C"])
    check("最后一个不能下移", host2.move_process_step(c, 1) is False)
    check("下移失败后顺序不变", _titles(host2, f2) == ["A", "B", "C"])
    check("C 上移成功", host2.move_process_step(c, -1) is True)
    check("C 与 B 换了位", _titles(host2, f2) == ["A", "C", "B"])
    check("上移后序号仍是 1/2/3",
          [r["step_no"] for r in host2.fetch_process_steps(f2)] == [1, 2, 3])
    check("A 下移成功", host2.move_process_step(a, 1) is True)
    check("A 与 C 换了位", _titles(host2, f2) == ["C", "A", "B"])
    check("不存在的步骤移动返回 False", host2.move_process_step(999999, -1) is False)

    # —— 删除与重排 ——
    # 此刻顺序是 C(1) A(2) B(3)，删掉中间的 A，留出空号 2
    host2.delete_process_step(a)
    check("删除后只剩两个", len(host2.fetch_process_steps(f2)) == 2)
    check("删除会留下空号（数据层不自动重排）",
          [r["step_no"] for r in host2.fetch_process_steps(f2)] == [1, 3],
          [r["step_no"] for r in host2.fetch_process_steps(f2)])
    host2.add_process_step(f2, {"step_no": 9, "title": "D"})
    check("新增 9 号后序号断档更明显",
          [r["step_no"] for r in host2.fetch_process_steps(f2)] == [1, 3, 9])
    host2.renumber_process_steps(f2)
    check("重排后序号连续 1..N",
          [r["step_no"] for r in host2.fetch_process_steps(f2)] == [1, 2, 3])
    check("重排没改变标题顺序", _titles(host2, f2) == ["C", "B", "D"])
    host2.renumber_process_steps(f2)
    check("重复重排是幂等的",
          [r["step_no"] for r in host2.fetch_process_steps(f2)] == [1, 2, 3])
    check("fetch_all_process_steps 覆盖多个流程",
          len(host2.fetch_all_process_steps()) == 3)

    # 两个流程各自的序号互不干扰
    f3 = host2.add_process_flow({"title": "第二个流程"})
    host2.add_process_step(f3, {"step_no": 1, "title": "别的流程的第一步"})
    check("新流程的序号从 1 起（不与别的流程连号）",
          host2.get_next_process_step_no(f3) == 2)
    check("按流程过滤步骤",
          len(host2.fetch_process_steps(f3)) == 1)


# ══════════════════════════════════════════════════════════════════════════
# H. 搜索
# ══════════════════════════════════════════════════════════════════════════
def test_search() -> None:
    section("H. 搜索：覆盖流程字段与步骤内容、不重复出行")
    host = fresh("search")
    f1 = host.add_process_flow({"title": "域名备案", "category": "备案",
                                "platform": "阿里云", "note": "每年一次"})
    f2 = host.add_process_flow({"title": "SSL 更新", "category": "运维",
                                "platform": "Linux",
                                "link_url": "https://www.example.com"})
    host.add_process_step(f1, {"step_no": 1, "title": "提交主体信息",
                               "required_text": "身份证", "description_text": "在控制台提交"})
    host.add_process_step(f1, {"step_no": 2, "title": "等审核",
                               "note": "通常 3 个工作日"})
    # 同一流程里放两条都含「共享目录」的步骤：验证 EXISTS 不会把流程查成两行
    shared_a = host.add_process_step(f1, {"step_no": 3, "title": "上传材料甲",
                                          "note": "放进共享目录"})
    shared_b = host.add_process_step(f1, {"step_no": 4, "title": "上传材料乙",
                                          "note": "也放进共享目录"})
    s3 = host.add_process_step(f2, {"step_no": 1, "title": "上传新证书",
                                    "command_text": "scp new.pem root@host:/etc/nginx/"})
    s4 = host.add_process_step(f2, {"step_no": 2, "title": "reload",
                                    "precheck_text": "先 nginx -t",
                                    "expected_text": "reload 成功"})

    def hit_titles(keyword):
        return sorted(r["title"] for r in host.fetch_process_flows(keyword))

    check("命中流程标题", hit_titles("备案") == ["域名备案"])
    check("命中流程分类", hit_titles("运维") == ["SSL 更新"])
    check("命中流程平台", hit_titles("阿里云") == ["域名备案"])
    check("命中流程备注", hit_titles("每年一次") == ["域名备案"])
    check("命中流程链接（ASCII 大小写不敏感）", hit_titles("WJSPM") == ["SSL 更新"])
    check("命中步骤标题", hit_titles("提交主体信息") == ["域名备案"])
    check("命中步骤说明", hit_titles("在控制台提交") == ["域名备案"])
    check("命中步骤备注", hit_titles("3 个工作日") == ["域名备案"])
    check("命中步骤必填项（备案遗留字段也能搜）", hit_titles("身份证") == ["域名备案"])
    check("命中步骤命令", hit_titles("scp") == ["SSL 更新"])
    check("命中步骤前置检查", hit_titles("nginx -t") == ["SSL 更新"])
    check("命中步骤预期结果", hit_titles("reload 成功") == ["SSL 更新"])

    multi = host.fetch_process_flows("共享目录")
    check("同一流程两条步骤都命中时只返回一行", len(multi) == 1,
          [r["title"] for r in multi])
    check("返回的那行就是该流程",
          bool(multi) and multi[0]["title"] == "域名备案")
    check("EXISTS 子查询不会放大行数（id 不重复）",
          len({int(r["id"]) for r in multi}) == len(multi))

    check("搜不到时返回空", host.fetch_process_flows("绝不存在的词") == [])
    check("空关键词返回全部", len(host.fetch_process_flows("")) == 2)
    check("纯空白关键词按空处理（返回全部）", len(host.fetch_process_flows("   ")) == 2)
    check("关键词两侧空白被裁掉", hit_titles("  备案  ") == ["域名备案"])
    check("没命中任何流程时列表为空", hit_titles("绝不存在的词") == [])

    ids = host.fetch_matching_step_ids("共享目录")
    check("fetch_matching_step_ids 返回命中的两个步骤 id",
          ids == {int(shared_a), int(shared_b)}, sorted(ids))
    check("步骤 id 集合与流程搜索结论一致（同属一个流程）",
          len(host.fetch_process_flows("共享目录")) == 1)
    check("只在「预期结果」里命中也算",
          host.fetch_matching_step_ids("reload 成功") == {int(s4)})
    check("只命中流程字段时步骤命中集为空",
          host.fetch_matching_step_ids("备案") == set())
    check("命令列命中（scp）可被单独定位",
          host.fetch_matching_step_ids("scp") == {int(s3)})
    check("空关键词返回空集合", host.fetch_matching_step_ids("") == set())
    check("纯空白关键词返回空集合", host.fetch_matching_step_ids("  ") == set())
    check("搜不到返回空集合", host.fetch_matching_step_ids("绝不存在的词") == set())


# ══════════════════════════════════════════════════════════════════════════
# I. 执行留痕
# ══════════════════════════════════════════════════════════════════════════
def test_runs() -> None:
    section("I. 执行留痕：开跑 / 勾选 / 计数 / 结束 / 历史 / 快照")
    host = fresh("runs")
    fid = host.add_process_flow({"title": "部署流程"})
    ids = [host.add_process_step(fid, {"step_no": i, "title": f"步骤{i}", "kind": STEP_KIND_CMD,
                                       "command_text": f"echo {i}"}) for i in (1, 2, 3)]
    check("开跑前没有进行中的执行", host.get_active_process_run(fid) is None)

    run_id = host.start_process_run(fid, title="部署流程", env="prod",
                                    variables={"域名": "a.com"})
    run = host.get_process_run(run_id)
    check("执行记录已建", run is not None)
    check("初始状态是 running", run["status"] == RUN_STATUS_RUNNING)
    check("环境已存", run["env"] == "prod")
    check("变量快照已存",
          json.loads(run["variables_json"]) == {"域名": "a.com"})
    check("started_at 已填", bool(run["started_at"]))
    check("finished_at 初始为空", (run["finished_at"] or "") == "")
    check("进行中的执行能按流程查到", int(host.get_active_process_run(fid)["id"]) == run_id)

    snap = host.fetch_process_run_steps(run_id)
    check("执行明细按步骤数生成", len(snap) == 3)
    check("明细按 step_no 排序", [int(r["step_no"]) for r in snap] == [1, 2, 3])
    check("初始都没勾选", all(int(r["done"]) == 0 for r in snap))
    check("计数初始为 (0, 3)", host.count_process_run_done(run_id) == (0, 3))

    host.set_process_run_step_done(run_id, ids[0], True)
    check("勾第一个后计数 (1, 3)", host.count_process_run_done(run_id) == (1, 3))
    host.set_process_run_step_done(run_id, ids[2], True)
    check("勾第三个后计数 (2, 3)", host.count_process_run_done(run_id) == (2, 3))
    check("勾选写了 done_at",
          any((r["done_at"] or "") for r in host.fetch_process_run_steps(run_id)))
    host.set_process_run_step_done(run_id, ids[0], False)
    check("取消勾选后计数 (1, 3)", host.count_process_run_done(run_id) == (1, 3))
    check("取消勾选把 done_at 清掉",
          all((r["done_at"] or "") == "" for r in host.fetch_process_run_steps(run_id)
              if int(r["step_id"]) == ids[0]))

    host.finish_process_run(run_id)
    run = host.get_process_run(run_id)
    check("结束后状态是 done", run["status"] == RUN_STATUS_DONE)
    check("结束后 finished_at 已填", bool(run["finished_at"]))
    check("结束后不再是进行中", host.get_active_process_run(fid) is None)

    aborted = host.start_process_run(fid)
    host.finish_process_run(aborted, RUN_STATUS_ABORTED)
    check("可以标记为已中断",
          host.get_process_run(aborted)["status"] == RUN_STATUS_ABORTED)
    check("中断的执行也不占用「进行中」", host.get_active_process_run(fid) is None)

    hist = host.fetch_recent_process_runs(fid)
    check("历史按时间倒序（新的在前）", int(hist[0]["id"]) == aborted, [r["id"] for r in hist])
    check("历史包含两次执行", len(hist) == 2)
    check("limit 生效", len(host.fetch_recent_process_runs(fid, limit=1)) == 1)
    check("别的流程查不到这些执行",
          host.fetch_recent_process_runs(fid + 999) == [])

    # —— 指定步骤子集 ——
    sub = host.start_process_run(fid, step_ids=[ids[1]])
    check("指定步骤子集时只建一条明细", len(host.fetch_process_run_steps(sub)) == 1)
    check("子集明细的 step_no 从 1 编", 
          int(host.fetch_process_run_steps(sub)[0]["step_no"]) == 1)
    check("子集执行的计数是 (0, 1)", host.count_process_run_done(sub) == (0, 1))

    # —— 只传 step_ids 的那种执行，删掉它不会误伤别的 ——
    host.delete_process_run(sub)
    check("删除执行后明细一起走",
          host.conn.execute("SELECT COUNT(*) FROM process_run_steps WHERE run_id = ?",
                            (sub,)).fetchone()[0] == 0)
    check("删除执行不影响其它执行", len(host.fetch_recent_process_runs(fid)) == 2)

    host2 = fresh("run_flow_gone")
    f2 = host2.add_process_flow({"title": "会被删的流程"})
    host2.add_process_step(f2, {"step_no": 1, "title": "x"})
    host2.start_process_run(f2)
    host2.delete_process_flow(f2)
    check("删流程时执行留痕一并清掉（不留孤儿）",
          host2.conn.execute("SELECT COUNT(*) FROM process_runs").fetchone()[0] == 0)


def main_test() -> None:
    print("=" * 78)
    print("流程中心回归测试：数据层 + 脚本生成 + 建表迁移")
    print("=" * 78)
    test_step_kind()
    test_danger()
    test_variables()
    test_run_script()
    test_schema()
    test_flow_crud()
    test_step_crud()
    test_search()
    test_runs()


if __name__ == "__main__":
    try:
        main_test()
    except Exception:
        import traceback

        traceback.print_exc()
        FAILED += 1
    finally:
        cleanup()

    print()
    print("=" * 78)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 78)
    sys.exit(1 if FAILED else 0)
