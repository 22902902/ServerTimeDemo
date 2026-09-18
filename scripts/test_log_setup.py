# -*- coding: utf-8 -*-
"""log_setup 回归测试 —— 真实写文件、真实读回，逐条断言。

用法：
    python scripts/test_log_setup.py [项目根目录]

覆盖：
  1. 配置 root 后，**其他模块**的 logger 输出也能落盘
     （这是「全项目接入」的核心承诺：各模块不需要各自装 handler）
  2. 打包版场景：spec 里 console=False，sys.stderr 不可用 —— 日志仍要落盘
  3. 幂等性：重复调用不会重复挂 handler、不会重复输出
  4. 导入 main 不应产生日志文件（只有入口 main() 才初始化）
  5. 日志目录不可写时降级而不抛异常
  6. 文件轮转策略确实生效（RotatingFileHandler + 尺寸/份数）

退出码：0 = 全部通过；1 = 有失败项。
"""
import importlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if len(sys.argv) > 1:
    ROOT = os.path.abspath(sys.argv[1])
else:
    ROOT = str(Path(__file__).resolve().parent.parent)

if not os.path.isfile(os.path.join(ROOT, "log_setup.py")):
    print(f"找不到 {os.path.join(ROOT, 'log_setup.py')}")
    sys.exit(2)

sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

passed, failed = [], []


def check(label, ok, detail=""):
    (passed if ok else failed).append(label)
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}"
          + (f"\n        {detail}" if detail else ""))


import log_setup  # noqa: E402

tmp_root = Path(tempfile.mkdtemp(prefix="log_setup_test_"))

# ---------------------------------------------------------------------------
print("=" * 76)
print("1. 配置 root 后，其他模块的 logger 也能落盘")
print("=" * 76)
log_dir = tmp_root / "logs"
log_setup.setup_logging(log_dir, level=logging.INFO, console=False)

check("log_setup.is_configured() 为真", log_setup.is_configured())
check("日志文件已创建", (log_dir / log_setup.LOG_FILENAME).exists())

# 关键断言：不碰 main.py，直接用 tools_page 模块自己的 logger
import tools_page  # noqa: E402

tools_page.logger.error("来自 tools_page 的测试日志 %s", "SMOKE-A")
logging.getLogger("some.new.module").error("来自新模块的测试日志 SMOKE-B")

content = (log_dir / log_setup.LOG_FILENAME).read_text(encoding="utf-8")
check("tools_page 的日志出现在日志文件中（证明无需逐模块装 handler）",
      "SMOKE-A" in content, content.strip().splitlines()[-1] if content.strip() else "(空)")
check("任意新模块的 logger 也能落盘", "SMOKE-B" in content)
check("格式含时间/级别/logger 名",
      " [ERROR] tools_page: " in content,
      [l for l in content.splitlines() if "SMOKE-A" in l][:1].__str__())

# ---------------------------------------------------------------------------
print()
print("=" * 76)
print("2. 打包版场景（console=False，sys.stderr 不可用）仍能落盘")
print("=" * 76)
log_setup._reset_for_tests()
log_dir2 = tmp_root / "logs_noconsole"

real_stderr = sys.stderr
sys.stderr = None                      # 模拟 PyInstaller 窗口程序
try:
    root = log_setup.setup_logging(log_dir2, console=None)
    stderr_handlers = [h for h in root.handlers
                       if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, logging.FileHandler)]
    check("自动探测到无控制台，未挂 StreamHandler", len(stderr_handlers) == 0,
          f"h=StreamHandler({[type(h.stream).__name__ for h in stderr_handlers]})")
    logging.getLogger("noconsole").error("无控制台时的日志 SMOKE-C")
    c2 = (log_dir2 / log_setup.LOG_FILENAME).read_text(encoding="utf-8")
    check("仍然写入了文件", "SMOKE-C" in c2)
finally:
    sys.stderr = real_stderr

# ---------------------------------------------------------------------------
print()
print("=" * 76)
print("3. 幂等性：重复调用不重复挂 handler")
print("=" * 76)
log_setup._reset_for_tests()
log_dir3 = tmp_root / "logs_idem"
log_setup.setup_logging(log_dir3, console=False)
count_first = len(logging.getLogger().handlers)
log_setup.setup_logging(log_dir3, console=False)
log_setup.setup_logging(log_dir3 / "other", console=False)
count_after = len(logging.getLogger().handlers)
check("handler 数量不变", count_first == count_after == 1,
      f"{count_first} -> {count_after}")

logging.getLogger("idem").error("幂等测试 SMOKE-D")
lines = [l for l in (log_dir3 / log_setup.LOG_FILENAME).read_text(encoding="utf-8")
         .splitlines() if "SMOKE-D" in l]
check("同一条日志只写一次（无重复 handler）", len(lines) == 1, f"出现 {len(lines)} 次")

# ---------------------------------------------------------------------------
print()
print("=" * 76)
print("4. 导入 main 不产生日志文件（只有入口 main() 才初始化）")
print("=" * 76)
# 用「导入前后状态比对」而不是「假定目录不存在」：
# 日志目录可能因真实运行过而早已存在，断言应描述「无副作用」而非「不存在」。
probe_log_file = Path(ROOT) / "ExpiryManager_Data" / "logs" / log_setup.LOG_FILENAME


def _log_file_state():
    if not probe_log_file.exists():
        return (False, None, None)
    stat = probe_log_file.stat()
    return (True, stat.st_size, stat.st_mtime_ns)


before_state = _log_file_state()
probe = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, r'%s'); import log_setup, main; "
     "print('CONFIGURED=' + str(log_setup.is_configured()))" % ROOT],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    cwd=ROOT)
out = (probe.stdout or "") + (probe.stderr or "")
check("导入 main 后 log_setup 仍未配置",
      "CONFIGURED=False" in out,
      out.strip().splitlines()[-1] if out.strip() else "(无输出)")
check("导入 main 未改动日志文件（无初始化副作用）",
      _log_file_state() == before_state,
      f"导入前={before_state} 导入后={_log_file_state()}")

# ---------------------------------------------------------------------------
print()
print("=" * 76)
print("5. 日志目录不可写时降级而不抛异常")
print("=" * 76)
log_setup._reset_for_tests()
# 用一个「父路径是文件」的目录，mkdir 必然失败
blocker = tmp_root / "not_a_dir"
blocker.write_text("x", encoding="utf-8")
try:
    log_setup.setup_logging(blocker / "logs", console=False)
    crashed = None
except Exception as exc:
    crashed = exc
check("未抛异常（日志基建不该让程序起不来）", crashed is None,
      f"{type(crashed).__name__}: {crashed}" if crashed else "")
check("仍标记为已配置", log_setup.is_configured())

# ---------------------------------------------------------------------------
print()
print("=" * 76)
print("6. 轮转策略确实生效")
print("=" * 76)
log_setup._reset_for_tests()
log_dir6 = tmp_root / "logs_rotate"
log_setup.setup_logging(log_dir6, console=False)
handlers = [h for h in logging.getLogger().handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)]
check("使用 RotatingFileHandler", len(handlers) == 1)
if handlers:
    h = handlers[0]
    check(f"单文件上限 {log_setup.MAX_BYTES} 字节（模块常量）",
          h.maxBytes == log_setup.MAX_BYTES)
    check(f"保留 {log_setup.BACKUP_COUNT} 份历史", h.backupCount == log_setup.BACKUP_COUNT)
    check("按 utf-8 编码写出（中文不丢）",
          h.encoding and h.encoding.lower().replace("-", "") == "utf8",
          f"encoding={h.encoding}")

# ---------------------------------------------------------------------------
log_setup._reset_for_tests()
shutil.rmtree(tmp_root, ignore_errors=True)

print()
print("=" * 76)
print(f"通过 {len(passed)} 项，失败 {len(failed)} 项")
for f in failed:
    print(f"  FAIL  {f}")
print("=" * 76)
sys.exit(1 if failed else 0)
