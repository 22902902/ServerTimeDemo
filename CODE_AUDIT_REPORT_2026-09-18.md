# 全项目可读性 / 可维护性体检报告

**体检时间**：2026-09-18
**项目**：`F:\phpstudy_pro\WWW\ServerTimeDemo`（Python + Tkinter + SQLite 桌面版个人系统）
**代码规模**：69 个 `.py` 文件 / **26,343 行**（不含 `dist/`、`build/`）
**分析方式**：AST 结构分析 + pyflakes 静态检查 + 重复块哈希比对 + 人工核实

> 本文取代 `CODE_AUDIT_REPORT.md`（2026-07-31）。旧报告中若干结论已过时或与实测不符，对照见文末「附录 B」。

---

## 一、体检总览

### 1.1 分层现状

| 区域 | 文件数 | 行数 | 评价 |
|---|---|---|---|
| 根目录 | 45 | 19,851 | 平铺，无包结构 |
| `embedded_admin_tools/` | 9 | 4,171 | 已有分层意识 ✅ |
| `embedded_admin_tools/services/` | 8 | 2,073 | 服务层抽离 ✅ |
| `tmp_debug/` + 根目录 `_*.py` | 7 | 1,613 | 一次性脚本堆积 ❌ |

`embedded_admin_tools/` 已经是**正确的方向**：服务层（`crypto_service` / `interface_service` / `error_code_service` / `app_icon_service`）把数据和逻辑从窗口里抽了出来，`interface_service.py` 这类 6 行兼容包装也写了 docstring 说明用途。问题在**根目录没有跟上这个标准**。

### 1.2 三个结构性问题（一句话版）

1. **`main.py` 一个人扛了 5,166 行** —— 常量区 + 路径迁移 + 50 个游离函数 + 8 个类（含 2,122 行的 `ExpiryManagerApp` 和 1,107 行的 `Database`）。
2. **没有版本控制** —— 26K 行代码、11 个直接重写源码的脚本、4 个 `.bak` 文件，全裸奔。这是本次体检**最该先解决的一件事**。
3. **上层抽象存在但被绕过** —— `ui_theme.Palette/ThemeManager` 已建好，13 个文件已接入，但三个较新的模块继续手写颜色值。

---

## 二、P0 —— 立即处理

### 2.1 【真 Bug】四个未定义名 / 作用域错误 — ✅ 已全部修复

这些不是风格问题，是**点了就崩**的运行时错误。pyflakes 扫出后我逐处读了源码确认。

> **修复状态**：4 处已修复并逐项验证（见本节末尾的验证记录）。pyflakes 由 **72 条 → 64 条**，消失的 8 条正好是这 4 个 Bug 的全部条目，无新增。
>
> **⚠️ 本节初版的 Bug 2 改法是错的**，已在原处更正：`openpyxl` 并**没有** `BadZipFile` / `exceptions` 这两个属性，且模块级导入它会让启动慢 0.8 秒。写审计报告时未做实测，是本报告的一处教训。

#### Bug 1：`main.py:903` — `PIL` 未绑定

```python
# main.py:122  只导入了名字，没有绑定 PIL 这个模块名
from PIL import Image, ImageTk, UnidentifiedImageError

# main.py:897-905
try:
    stored_path = copy_account_image_to_store(source_path, self.image_subdir)
    ...
except (PIL.UnidentifiedImageError, OSError, Exception) as exc:   # ← NameError!
```

**后果**：账号截图上传只要出错，`except` 子句求值时先抛 `NameError: name 'PIL' is not defined`。用户看到的不是「上传截图失败」提示框，而是一段 traceback。**错误处理本身成了错误。**

还有个附带问题：`(PIL.UnidentifiedImageError, OSError, Exception)` 末尾挂了个 `Exception`，等价于 `except Exception` —— 本次「异常窄化」重构实际上**既没生效也没意义**。

**改法**（二选一）：

```python
# 方案 A：已导入 UnidentifiedImageError，直接用
except (UnidentifiedImageError, OSError) as exc:

# 方案 B：改用模块名绑定
import PIL
from PIL import Image, ImageTk
...
except (PIL.UnidentifiedImageError, OSError) as exc:
```

#### Bug 2：`main.py:4098` 与 `main.py:5015` — `openpyxl` 从未导入

```python
except (json.JSONDecodeError, openpyxl.BadZipFile,
        openpyxl.exceptions.InvalidFileException, OSError, Exception) as exc:
```

全文 `grep` 确认：`main.py` 里**没有任何 `openpyxl` 导入**，只有这两处引用。Excel 导入/导出遇到损坏文件 → `NameError`。

**⚠️ 本报告初版的改法有误，已更正。** 初版建议 `import openpyxl` 后用 `openpyxl.BadZipFile` 与 `openpyxl.exceptions.InvalidFileException`。实测（openpyxl 3.1.5）：

```
openpyxl.BadZipFile                            → AttributeError ❌ 属性不存在
openpyxl.exceptions                            → AttributeError ❌ 该子模块未挂到包上
openpyxl.utils.exceptions.InvalidFileException → OK ✅ 但导入它要 829 ms
import openpyxl                                → 800 ms
```

三个名字里**有两个根本不存在**；即使写对，把 `openpyxl` 提到模块级会让每次启动**慢 0.8 秒**——这正是原作者把 `load_workbook` 写成函数内导入的原因（`main.py:2286 / 2388 / 2432`）。

进一步用真实的损坏 xlsx（非 zip 的假文件 + 截断的 zip 各一个）喂给 `load_excel_assets` 与 `import_credential_items_from_excel`，实测**两者都抛 `zipfile.BadZipFile`**，`InvalidFileException` 并未触发（它属兜底情形）。

**改法**（✅ 已实施，`zipfile` 在 `main.py:89` 已导入，零额外成本）：

```python
except (zipfile.BadZipFile, OSError) as exc:
    # 实测：损坏或非 xlsx 的表格由 openpyxl 底层抛出 zipfile.BadZipFile
    messagebox.showerror(APP_TITLE, f"导入失败：{exc}", parent=self)
except Exception as exc:
    # 兜底：含 openpyxl.utils.exceptions.InvalidFileException、缺失依赖的 RuntimeError
    logger.exception("导入 Excel 资产失败：%s", file_path)
    messagebox.showerror(APP_TITLE, f"导入失败：{exc}", parent=self)
```

顺带去掉的 `json.JSONDecodeError`：两个加载函数都不解析 JSON，这个类型是复制粘贴残留，从未生效。

#### Bug 3：`tools_page.py:1183` — `logger` 未定义

```python
# tools_page.py 全文只有这一处出现 logger，既无 import logging 也无 getLogger
except Exception as e:
    logger.exception("set package color failed: %s", e)   # ← NameError
    messagebox.showerror("错误", f"设置失败：{e}", parent=self)
```

**后果**：设置包配色失败时，`logger.exception` 自身抛 `NameError`，下面的 `showerror` 永远执行不到 —— 用户点一下没反应。

**根因**：日志基建只在 `main.py` 里建了（`main.py:101-110`，含 `logger` + `_handler`）。其余 24 个模块**没有任何日志设施**，出现异常只能靠弹窗。这是「统一日志」重构只做了一半。

**改法**（✅ 已按最小改动修复）：在 `tools_page.py` 补齐模块级日志基建：

```python
import logging
...
# 模块 logger — 统一走 logging（此前本模块无日志设施，logger.exception 会直接 NameError）
logger = logging.getLogger(__name__)
```

初版本报告建议的 `log_setup.py`（全局日志配置 + 各模块 `get_logger()`）**方向正确但留作 P1**：终态确实应该是统一日志设施，但那是一次涉及 24 个模块的迁移，不该塞进「修 4 个 Bug」里做一半。当前 `main.py` 与 `tools_page.py` 各自持有 `logging.getLogger(__name__)`，消息经 root logger 汇总，行为一致。

#### Bug 4：`embedded_admin_tools/api_demo_window.py:1193` — 闭包变量未声明 `nonlocal`

```python
cal_window = tk.Toplevel(container)          # 1154 行，外层局部变量
...
def on_select(event=None):
    selected = cal.get_date()
    textvariable.set(selected)
    cal_window.destroy()                     # ← 1193 行 UnboundLocalError
    cal_window = None                        # ← 1194 行：这行赋值让 cal_window 变成 on_select 的局部变量
    self.on_date_changed(interface_name, field_name)   # 永远到不了
```

Python 规则：函数体内只要有赋值，该名字就是**本函数的局部变量**。所以 1193 行读取的是尚未赋值的局部变量 → `UnboundLocalError: cannot access local variable 'cal_window'`。

连带后果：1194 行的 `cal_window = None` 是永远执行不到的死代码，外层 `cal_window` 始终指向已销毁的窗口，于是 1201 行 `on_click_outside` 里 `if cal_window is None` 这个判断**永远为假**，会去 `winfo_exists()` 一个已销毁控件 → `TclError`。

**改法**：

```python
def on_select(event=None):
    nonlocal cal_window          # ← 补这一行
    cal.get_date() 后取值、set、destroy、置 None 全部生效
```

#### ✅ 修复验证记录

改动的 5 处代码位置：

| 位置 | 原写法 | 现写法 |
|---|---|---|
| `main.py:903` | `except (PIL.UnidentifiedImageError, OSError, Exception)` | `except (UnidentifiedImageError, OSError)` + `except Exception` 兜底 |
| `main.py:4098` | `except (json.JSONDecodeError, openpyxl.BadZipFile, openpyxl.exceptions.InvalidFileException, OSError, Exception)` | `except (zipfile.BadZipFile, OSError)` + `except Exception` 兜底 |
| `main.py:5015` | 同上 | 同上 |
| `tools_page.py:1183` | `logger` 未定义 | 补 `import logging` + 模块级 `logger` |
| `api_demo_window.py:1193` | `on_select` 缺 `nonlocal` | 补 `nonlocal cal_window` |

四道验证，全部通过：

**① 异常类型表达式真实求值** — 把全项目 49 个 `.py` 中 **210 个 `except` 类型表达式**全部抽出来真实 `eval`，0 个 NameError / AttributeError。同一脚本对修复前的版本（从 git `HEAD` 取原文件）跑出 **10 项 FAIL**，证明该检查有效而非橡皮图章。

**② 闭包作用域分析** — 按「被读后又赋值、未声明 `nonlocal`、且外层函数存在同名绑定」三条同时成立来判定，全项目 0 命中；修复前精确命中 `api_demo_window.py:1193`。

**③ 运行时冒烟测试（18 项全通过）** — 真实执行，非静态推断：

- 真实的失败复制（源文件不存在）抛 `FileNotFoundError` → 被修复后的 `(UnidentifiedImageError, OSError)` 捕获
- 真实构造损坏 xlsx（非 zip 的假文件 + 截断 zip），喂给两个加载函数 → 两者都抛 `zipfile.BadZipFile` → 被新处理器捕获
- `import tools_page` 后 `logger.exception()` 真实可调用
- **真实建出日期选择器、点开日历、触发选中事件** → 不再抛 `UnboundLocalError`，且 `on_date_changed('iface', 'field')` **真实被调用**（此前这条回调永远走不到）

**④ pyflakes 基线比对** — 72 条 → 64 条，删掉的 8 条与 4 个 Bug 一一对应，其余差异只是行号位移，零新增。全项目 58 个 `.py` 语法检查 0 错误。

> 复跑方式：`python scripts/check_name_scope.py`（检查 ①②，可对任意目录跑，传入路径参数即可对比修复前后）

---

### 2.2 没有版本控制，没有 `.gitignore` — ✅ 已完成

```
初始状态：.git → 不存在   .gitignore → 不存在
修复后：  .git → main 分支，2 个提交   .gitignore → 已建
```

这对一个 26K 行、且现场存在**直接重写源码文件的脚本**的项目来说是最高的单点风险。任何人（包括未来的你）手滑跑一次 `_fix_backup.py`，`main.py` 就被就地改写，且无法回退。

**已完成动作**：

| 项 | 结果 |
|---|---|
| 仓库 | `git init -b main` |
| 基线提交 | `dee267d` — 87 文件 / 34,462 行 |
| 清理提交 | `b19eed7` — 删 15 / 增 3 / 改 0 |
| `core.autocrlf` | `false`（源码 CRLF 26 / LF 33 / 混合 3，关闭转换避免改写行尾） |
| 身份 | 仓库级 `shaoy` / `shaoy@localhost`（未污染全局配置） |
| 忽略核对 | `git check-ignore` 逐一验证，索引 0 个敏感文件 |

`.gitignore` 已落盘（比下方草案更完整，含编辑器目录、Python 缓存、`_audit_out.txt` 等），要点：

```gitignore
# 凭据与个人隐私（绝不入库）
login_memory.json      # 含真实手机号 + DPAPI 密码密文
remember_me.json

# 运行期数据
ExpiryManager_Data/
*.db
Tools/  excel/  account_images/  process_flow_images/
study_notes_images/  study_notes_attachments/  study_demo/  adb_history/

# 构建产物
dist/  build/  *.toc  *.pkg  *.pyz

# 缓存与备份
__pycache__/  *.py[cod]  *.bak  *.bak.*
```

> ⚠️ **`login_memory.json` 里是真实手机号 `18640092818` 加密码密文，绝不能入库。** 已确认被忽略。
> 另外 `Tools/`（593 MB）、`dist/`（1.0 GB）、`build/`（40 MB）也已排除——首次提交仅 87 个文件，未把 1.6 GB 构建产物带进仓库。


---

### 2.3 「就地重写源码」的一次性脚本 — ✅ 已完成（含一次误删事故与完整恢复）

这是**可以直接损坏代码库的地雷**。以下是实测清单（`open(...,'wb')` 写回源码）：

| 脚本 | 行数 | 目标文件 |
|---|---|---|
| `_build_backup_ui.py` | 143 | `main.py` |
| `_fix_backup.py` | 88 | `main.py` |
| `_fix_backup_dialog.py` | 103 | `main.py` |
| `_fix_datetime.py` | 24 | `main.py` |
| `_fix_dt2.py` | 23 | `main.py` |
| `_fix_indent.py` | 34 | `main.py` |
| `_fix_lines.py` | 31 | `main.py` |
| `_migrate_data_dir.py` | 79 | `main.py` |
| `_insert_preview.py` | 27 | 硬编码路径 |
| `_strip_emoji.py` | 27 | 硬编码路径 |
| `_fix_output.py` | 80 | `study_demo_window.py` |
| `tmp_debug/_fix_console_encoding.py` | 45 | 源码 |
| `tmp_debug/_fix_dup.py` | 64 | 源码 |
| `tmp_debug/_check_dnd_fix.py` | 23 | 源码 |
| `_test_password_fix.py` | 39 | 源码 |

它们**没有任何一处被 import**（已逐一 grep 确认），是历史补丁的化石。里面还硬编码了绝对路径 `F:\phpstudy_pro\WWW\ServerTimeDemo\main.py`。

**已完成动作**：先建 git 安全网（见 2.2），再删除。**删 12 个补丁、迁 3 个生成器**。

### ⚠️ 本机 `git rm` 有环境级缺陷——不要用它删子目录文件

执行过程中触发了一次事故，值得单独记录，因为任何人照抄「用 `git rm` 清理」都会中招。

在 Windows + PortableGit 环境（系统 gitconfig 含 `core.fscache=true`）实测**可 100% 复现**：

```bash
git rm sub/keep.py    # → 整个 sub/ 被清空
                      #   连从未提及的 sub/deep/deeper.py 也一并删除 ❌
git rm top.py         # → 安全，只删 top.py ✔
rm sub/keep.py        # → 安全，只删该文件 ✔
```

**成因**：`git rm` 在路径含 `/` 时，会连带删掉该顶层目录下的全部已跟踪文件。
本次事故中 `git rm embedded_admin_tools/_gen_icon_service.py` 与 `git rm tmp_debug/*`
导致这两个目录下 **25 个文件**被误删（含 `embedded_admin_tools/__init__.py`、`services/*.py`）。

**恢复**：已提交过基线，`git checkout -- .` 一条命令完全恢复。

**安全操作规范（本机必须遵守）**：

```bash
# ✅ 正确：先 rm，再暂存
rm path/to/old_script.py && git add -A

# ❌ 禁止：会连带清空 path/to/ 整个目录
git rm path/to/old_script.py
```

1. 删除前必须先提交、确认 `git status` 无输出
2. 删除后立即 `git status --short` 核对，只应显示意图删除的文件
3. 出现意外删除立刻 `git checkout -- .`

**误删事件的完整验证记录**（证明恢复无损）：

```
git status --short              → 无输出（工作区干净）
git fsck                        → 仅 2 个 dangling blob，无损坏
文件数对账 dee267d → b19eed7    → 87 → 75（−15 删 +3 增），修改 0 个
pyflakes 重跑 vs 基线           → 72 条逐行完全一致
全项目语法检查                  → 58 个 .py，0 错误
```

### 12 个一次性补丁（已删除）

| 脚本 | 覆写目标 |
|---|---|
| `_build_backup_ui.py` / `_fix_backup.py` / `_fix_backup_dialog.py` | `main.py` |
| `_fix_datetime.py` / `_fix_dt2.py` / `_fix_indent.py` / `_fix_lines.py` | `main.py` |
| `_fix_output.py` | `study_demo_window.py` |
| `_insert_preview.py` / `_strip_emoji.py` | `study_notes_window.py` |
| `tmp_debug/_fix_console_encoding.py` | `console_page.py` |
| `tmp_debug/_test_overwrite.py` | 动态路径 |

### 3 个资产生成器（已迁至 `scripts/`，保留能力）

它们不是补丁而是必要工具——删掉就无法再生成图标资源。但原脚本用
`Path(__file__).parent` 定位资源，直接搬到 `scripts/` 会失效，因此同时修了路径：

| 原位置 | 新位置 | 作用 |
|---|---|---|
| `_gen_app_icon.py` | `scripts/gen_app_icon.py` | 生成 `app.ico` |
| `_gen_app_icon_service.py` | `scripts/gen_app_icon_service.py` | `app.ico` → `services/app_icon_service.py` |
| `embedded_admin_tools/_gen_icon_service.py` | `scripts/gen_icon_service.py` | `_ico_base64.txt` → `services/icon_service.py` |

**等价性已验证**（在内存中生成内容与磁盘文件逐行比对，未执行覆写）：

- `gen_app_icon_service.py` 输出与 `app_icon_service.py` **完全一致**
- `gen_icon_service.py` 输出与 `icon_service.py` 一致，**仅差在去掉了 BOM** ——
  原脚本以 `utf-8-sig` 写出，这正是 5.1 节 BOM 不一致问题的根源，新脚本已修正

### 尚未处理（P3，可后续一并清扫）

以下一次性脚本**只读、不改源码**，无风险，本次未动：

```
_check_all_db.py  _check_tq2.py  _check_triple_quotes.py  _find_all_paths.py
_inspect_tables.py  _scan_strings.py  _migrate_data_dir.py  _test_password_fix.py
embedded_admin_tools/_test_inline.py
tmp_debug/{_audit.py, _audit_dup.py, _check_dnd_fix.py, _fix_dup.py, _verify_db.py}
```

其中 `_migrate_data_dir.py` 的迁移映射表已内置在 `main.py:286`，是重复逻辑，可安全删除。

---

## 三、P1 —— 本周处理

### 3.1 `main.py` 拆分方案（5,166 行 → 目标 <500 行）

当前 `main.py` 顶层结构（AST 实测）：

| 区段 | 行号 | 内容 |
|---|---|---|
| 导入 + 常量区 | 1–537 | 15 个 `COLOR_*`、6 个 `FONT_*`、`TREE_COLUMNS`/`COLUMN_META` 等表格元数据、`PROCESS_FLOW_TEMPLATES`（153 行） |
| 路径与迁移 | 272–361 | `get_base_dir` / `_migrate_data_dir` / `DATA_DIR` |
| 游离函数 | 558–1159 | 约 30 个：日期解析、账号图片序列化（14 个 `*_account_image_*`）、密码哈希、单实例互斥 |
| `Database` | 1175–2281 | **1,107 行 / 56 方法** |
| Excel 导入导出 | 2284–2477 | `load_excel_assets`(100)、`import_credential_items_from_excel`(42)、`export_credential_rows_to_excel`(48) |
| 对话框 | 2488–2883 | `AccountEditDialog`(113)、`LoginDialog`(172)、`ChangePasswordDialog`(91) |
| 基础设施 | 2896–3006 | `TrayController`、`AppShutdownManager` |
| `ExpiryManagerApp` | 3027–5148 | **2,122 行 / 130 方法** |
| `main()` | 5151–5162 | 12 行（这个已经很好） |

**建议拆分（按依赖从底向上，每步独立可验证）**：

```
config.py              常量区 + 路径/数据目录迁移 + 单实例互斥     [150 行左右]
db/database.py         Database 类（见 3.2 再拆子表）              [1,100 行]
services/account_image.py  14 个 *_account_image_* 函数 + AccountImagePreview  [350 行]
services/date_parse.py parse_expiry_value / format_date / days_left / excel_serial_to_date  [90 行]
services/excel_io.py   三个 Excel 函数                            [200 行]
ui/dialogs/account.py  AccountEditDialog / LoginDialog / ChangePasswordDialog  [380 行]
ui/dialogs/*.py        其余对话框
ui/app_window.py       ExpiryManagerApp（见 3.3 再拆子页）
main.py                仅保留 main() + 组装                       [<100 行]
```

**为什么这个顺序**：先搬**无依赖的叶子**（常量、纯函数），再搬类。每搬一块立刻跑一次 `python -c "import main"` + 手工点一遍相关功能，风险最低。

**搬动注意**：`main.py` 现在有 ~15 处其他模块反向依赖它（`from main import ...`），搬动时要用兼容 shim 过渡，参考 `embedded_admin_tools/interface_service.py` 已有的做法：

```python
# 过渡期在新位置定义，旧位置保留一行转发
from services.account_image import *   # noqa: F401,F403
```

### 3.2 `Database` 类按表拆分（1,107 行 / 56 方法）

这是上次审计就挂账的 Step 5（`_task_2026-07-20_code_refactor.md` 里标记「暂缓，风险较高」）。观察到的表/领域：`assets`、`credentials`、`shared_accounts`、`process_flows`、`account_images`、`settings`。

**低风险拆法**：不拆连接管理，只把方法按表分到 Mixin：

```python
# db/repository_assets.py
class AssetRepository:
    """assets 表读写。依赖 self.conn，由宿主类提供。"""
    def list_assets(self): ...
    def upsert_asset(self, ...): ...

# db/database.py
class Database(AssetRepository, CredentialRepository, SettingsRepository):
    def __init__(self, db_path): self.conn = sqlite3.connect(db_path)
```

外部调用签名完全不变（`db.list_assets()` 照旧），**零调用方改动**，这是最划算的一刀。

### 3.3 `ExpiryManagerApp` 拆子页（2,122 行 / 130 方法）

这个类上次已经把 `build_ui` 从 524 行拆成 8 个 `_build_*` 方法（干得对），但**拆分只停在方法级，没下沉到类级**。现在 130 个方法仍然靠 `self.xxx` 共享 60+ 个实例属性。

**建议**：把每个 `_build_*` 配套的状态和回调一起抽成独立 `ttk.Frame` 子类，模式与已有的 `expiry_page.ExpiryPage` / `backend_page.BackendPage` **完全一致** —— 项目里已经有这个模式了，只是没贯彻。

```python
# 已有（✅ 正确示例）
class ExpiryPage(ttk.Frame): ...
class BackendPage(ttk.Frame): ...
class CredentialsPage(ttk.Frame): ...
class ProcessPage(ttk.Frame): ...

# 建议补上（当前仍内嵌在 ExpiryManagerApp 里）
class NotePage(ttk.Frame): ...        # main.py: _build_note_page
```

这是**一致性**问题而非能力问题——照抄项目里已跑通的 `ExpiryPage` 写法即可。

### 3.4 同构重复的建表迁移逻辑（`tools_db.py:104-135`）

同一段「检查列是否存在 → ALTER TABLE → commit → 静默吞异常」重复了 **5 次**：

```python
# 现状：5 份几乎一样的样板
cols = [r[1] for r in conn.execute("PRAGMA table_info(tool_items)").fetchall()]
if "is_deleted" not in cols:
    try:
        conn.execute("ALTER TABLE tool_items ADD COLUMN is_deleted INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
if "alias" not in cols:
    try:
        conn.execute("ALTER TABLE tool_items ADD COLUMN alias TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
# ... 还有 3 处
```

**改法**（声明式表驱动，顺带修掉 3.5 的注入问题）：

```python
# 新增列声明：(表名, 列名, 列定义)  —— 全部为字面量，不存在拼接
_SCHEMA_MIGRATIONS: list[tuple[str, str, str]] = [
    ("tool_items",      "is_deleted",   "INTEGER DEFAULT 0"),
    ("tool_items",      "alias",        "TEXT DEFAULT ''"),
    ("tool_categories", "package_id",   "INTEGER DEFAULT NULL"),
    ("tool_packages",   "icon_path",    "TEXT DEFAULT ''"),
    ("tool_packages",   "accent_color", "TEXT DEFAULT ''"),
]


def _apply_schema_migrations(conn) -> None:
    """为旧库补齐新增列。幂等：已存在的列会被跳过。"""
    for table, column, ddl in _SCHEMA_MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()
            logger.info("已补列 %s.%s", table, column)
        except sqlite3.OperationalError as exc:
            # 并发场景下另一个进程可能已补过，属预期
            logger.debug("补列 %s.%s 跳过：%s", table, column, exc)
```

**收益**：5 处 × 6 行 = 30 行 → 约 12 行；新增列只需加一行声明；`except Exception: pass` 收窄为 `sqlite3.OperationalError` 并落日志，不再静默吞掉真错误。

### 3.5 SQL 标识符拼接（7 处）

值全部走了参数化 ✅，但**标识符**（列名/表名）用 f-string 拼接，共 7 处：

| 位置 | 情况 | 风险 |
|---|---|---|
| `tools_db.py:131` | `DEFAULT '{default}'` **拼接了值** | 🔴 真注入点 |
| `tools_db.py:294` | `SET {set_clause}` | 🟡 列名，需白名单 |
| `tools_db.py:449` | `SET {set_clause}` | 🟡 同上 |
| `tools_db.py:517` | `{', '.join(fields)}` | 🟡 同上 |
| `main.py:1361` | `ADD COLUMN {column_name}` | 🟡 同上 |
| `study_demo_db.py:238` | `SET {set_clause}` | 🟡 同上 |
| `tmp_debug/_verify_db.py:19` | `FROM {t}` | ⚪ 弃用脚本，删除即可 |

**改法**：标识符不能参数化，必须**白名单校验**；值必须参数化。

```python
_ALLOWED_COLUMNS = frozenset({"name", "path", "alias", "icon_path", "accent_color"})

def _safe_column(name: str) -> str:
    """校验列名在白名单内，防止 SQL 标识符注入。"""
    if name not in _ALLOWED_COLUMNS:
        raise ValueError(f"非法列名：{name}")
    return name

# set_clause 构造时统一走 _safe_column
set_clause = ", ".join(f"{_safe_column(k)}=?" for k in fields)
```

`tools_db.py:131` 改为把 default 当参数传入（配合 3.4 的声明式迁移，默认值直接写死在 DDL 字面量里，问题自然消失）。

### 3.6 依赖清单不完整（`requirements.txt`）

当前只有 4 行：

```txt
openpyxl>=3.1.2
pystray>=0.19.5
Pillow>=10.3.0
pyinstaller>=6.10.0
```

实际第三方依赖（按 import 实测）：**另缺 5 个** —— `requests`（HTTP）、`pygments`（代码高亮，笔记模块）、`tkinterdnd2`（拖拽）、`tkcalendar`（`embedded_admin_tools` 日历控件）、`pycryptodome`（`Crypto`，DES 加解密）。

**后果**：新环境照 README 执行 `pip install -r requirements.txt` 后**跑不起来**。

**改法**：

```txt
# UI / 桌面
Pillow>=10.3.0
pystray>=0.19.5
tkinterdnd2>=0.3.0
tkcalendar>=1.6.1

# 数据
openpyxl>=3.1.2

# 网络与安全
requests>=2.31.0
pycryptodome>=3.20.0

# 展示
pygments>=2.17.0

# 打包
pyinstaller>=6.10.0
```

建议顺手固定版本（`pip freeze` 生成 `requirements.lock.txt`），避免某次 `pip install` 后界面崩了却查不出原因。

### 3.7 未使用导入 / 死抽象层（约 45 处）

pyflakes 实测（`tmp_debug/_pyflakes.txt` 有完整清单）。重点：

| 文件 | 数量 | 值得单独说的 |
|---|---|---|
| `main.py` | 15 | 从 `ui_components` 导入 5 个、从 `page_components` 导入 7 个，**全部未使用** |
| `study_notes_window.py` | 7 | `base64` / `json` / `os` / `subprocess` / `uuid` / `simpledialog` / `StudyNote` |
| `tools_page.py` | 6 | `struct` / `tempfile` / `colorchooser` / `simpledialog` / `datetime` / `TkinterDnD` |
| `study_demo_window.py` | 4 | `time` / `json` / `scrolledtext` |
| `study_demo_db.py` | 2 | `datetime` / `Path` |
| `qa_work_log_page.py` | 4 | 含 `qa_extras` 的 3 个函数 |
| 其余 6 个文件 | 7 | `api_demo_window` / `crypto_window` / `login_checker_window` / `market_quote_window` 各 2 个（`sys`、`Path`） |

**关于 `page_components` / `ui_components`**：这两个模块总计 160 行（88 + 72），`main.py` 一次性导入了其中 12 个函数却一个没用。要么是**抽了一半的抽象层**，要么是**已经废弃的中间产物**。建议二选一：
- 若模块里还有其他地方在用 → 保留，但把 `main.py` 的无用导入删掉；
- 若无人使用 → 整个删除，减少读者困惑（「这堆 create_xxx 到底谁在用？」）。

顺带修掉 `main.py:89` 与 `main.py:92` 的 **`threading` 重复导入**（`redefinition of unused 'threading'`）。

### 3.8 未使用的局部变量（7 处）

```
main.py:1942            cursor        赋值后未使用
tools_page.py:1954      current_cols  赋值后未使用
tools_page.py:2692      row_cfg       赋值后未使用
study_notes_window.py:1344  parent_cat 赋值后未使用
study_notes_window.py:1570  dlg       赋值后未使用
study_notes_window.py:1585  dlg       赋值后未使用
study_demo_window.py:396    start     赋值后未使用
```

`study_notes_window.py:1570/1585` 的 `dlg` 值得留意——对话框对象被赋值却不使用，可能原本要 `wait_window()` 或读 `dlg.result`，属于**疑似漏写逻辑**，建议逐个确认，不要直接删。

---

## 四、P2 —— 本月处理

### 4.1 超长方法（≥80 行）

| 行数 | 分支 | 位置 | 方法 | 备注 |
|---|---|---|---|---|
| 211 | 8 | `backend_page.py:30` | `BackendPage.build` | 全项目最长 |
| 181 | 13 | `embedded_admin_tools/market_quote_window.py:724` | `build_response_table_view` | |
| 151 | **30** | `tools_page.py:183` | `extract_exe_icon` | 分支最多，**最难读** |
| 149 | 0 | `study_notes_window.py:268` | `NoteEditorDialog.build_ui` | 纯 UI 堆叠，可拆 layout 函数 |
| 149 | 8 | `ui_theme.py:210` | `ThemeManager.apply_admin_ttk_theme` | |
| 138 | 4 | `main.py:3046` | `ExpiryManagerApp.__init__` | 构造器过长 |
| 132 | 10 | `embedded_admin_tools/api_demo_window.py:750` | `render_interface_form` | |
| 130 | 0 | `main.py:1204` | `Database.create_tables` | 0 分支，可改为 DDL 字符串列表 |
| 119 | 0 | `study_demo_window.py:212` | `StudyDemoPage._build_right_panel` | |
| 116 | 2 | `process_page.py:26` | `ProcessPage.build` | |
| 100 | **26** | `main.py:2284` | `load_excel_assets` | 解析逻辑，建议状态机化 |

**优先处理 `tools_page.py:183 extract_exe_icon`**（151 行 / 30 分支 / 嵌套 6 层）—— 单一方法里塞了「解析 PE 资源 → 解码 → 缩放到多尺寸 → 生成 ico → 写缓存」五件事，是全项目可读性最差的一段。建议按这五个职责切成五个函数。

**`Database.create_tables`（130 行 / 0 分支）** 是最容易的一刀：把每条 `CREATE TABLE` 抽成模块级常量列表，方法体变成循环。

```python
_CREATE_TABLE_STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS assets (...)""",
    """CREATE TABLE IF NOT EXISTS credentials (...)""",
    ...
]

def create_tables(self) -> None:
    """建表。幂等：均使用 IF NOT EXISTS。"""
    with self.conn:
        for ddl in _CREATE_TABLE_STATEMENTS:
            self.conn.execute(ddl)
```

### 4.2 重复代码块（25 组，跨文件）

自动比对出 25 组「连续 8 行归一化后完全一致」的代码。**最值得合并的一组** —— 同一份 40 行的主题配置在 4 个窗口里各抄了一遍：

```
configure_theme 流程重复 x3：
  embedded_admin_tools/api_demo_window.py:117
  embedded_admin_tools/login_checker_window.py:102
  embedded_admin_tools/market_quote_window.py:202

配套的字体/控件配置重复 x4：
  ...api_demo_window.py:158-160
  ...crypto_window.py:485-487
  ...login_checker_window.py:129
  ...market_quote_window.py:228-230
```

**改法**：在 `ui_theme.py` 里补一个 `ThemeManager.apply_tool_window_theme(window)`，四个窗口各调一行。收益：4 份 × 约 45 行 → 1 份。

其余较小的一组是 `_fix_backup.py` 与 `main.py:3219` 的 `asksaveasfilename` 流程重复——随 2.3 删除脚本后自然消失。

### 4.3 主题抽象被绕过（手写颜色值 99 处）

`ui_theme.py` 已经提供了 `Palette`（第 26 行）和 `ThemeManager`（第 151 行），**13 个文件已正确接入**。但三个较新的模块继续手写十六进制值：

| 文件 | 手写颜色数 |
|---|---|
| `embedded_admin_tools/api_demo_window.py` | 43 |
| `study_demo_window.py` | 31 |
| `study_notes_window.py` | 16 |
| `main.py` | 15 |
| `adb_page.py` | 7 |
| `tools_page.py` | 7 |
| `embedded_admin_tools/market_quote_window.py` | 5 |

（`ui_theme.py` 自身的 85 处是调色板定义，属合理。）

**为什么这是个问题**：想调主题色，得改 6 个文件、100 个位置，且必然漏。**收益**：接到 `Palette` 后，换肤只改 `ui_theme.py` 一处。

**建议**：先给 `Palette` 补上这三个模块实际用到的语义色（如 `weekend_bg`、`header_bg`、`select_bg`），再逐文件替换。不必一次做完，按文件切分即可。

### 4.4 文档覆盖率偏低

| 文件 | 覆盖率 | 无文档的类 |
|---|---|---|
| `embedded_admin_tools/market_quote_window.py` | **0%**（0/65） | `MarketQuoteToolWindow` |
| `embedded_admin_tools/login_checker_window.py` | **0%**（0/20） | `LoginCheckerWindow` |
| `embedded_admin_tools/crypto_window.py` | **0%**（0/19） | `CryptoToolWindow` |
| `embedded_admin_tools/api_demo_window.py` | 5%（4/74） | `ApiDemoWindow` |
| `embedded_admin_tools/services/*` | 0% | `ApiClient` / `DESCryptoService` / `LoginMemoryService` |
| `main.py` | 15%（44/284） | — |
| `account_windows.py` | 9%（3/32） | — |
| `tools_page.py` | 36%（52/144） | `_ColorPickerDialog` |

**不必追求全覆盖**。按「改动频率 × 理解成本」投入，优先给这四类补 docstring：
1. **数据库字段与业务规则**（`Database` 类 + 各 `*_db.py`）—— 半年后你会忘记 `assets.status` 的取值含义；
2. **对外部接口的封装**（`services/*`）—— 请求/响应字段映射必须写清；
3. **有副作用的函数**（写文件、发请求、改全局状态）；
4. **魔数集中的地方**（日期序列号转换、DES 密钥派生）。

对 `interface_service.py` / `error_code_service.py` 这类内嵌 JSON 的服务，重点是在类 docstring 里说明**数据来源与更新方式**。

### 4.5 超长行（约 180 处 >120 字符）

```
embedded_admin_tools/services/interface_service.py   102 处
main.py                                               29 处
ui_theme.py                                           19 处
system_toolbox_page.py                                16 处
tools_page.py                                          8 处
embedded_admin_tools/market_quote_window.py            7 处
```

`interface_service.py` 的 102 处几乎全是**内嵌 JSON 单行字符串**，属设计取舍，**建议不处理**（拆行反而更难维护）。`main.py` / `ui_theme.py` 的 48 处建议随各自重构顺手拆开。

---

## 五、P3 —— 持续改进

### 5.1 编码不一致（BOM）

两个文件带 UTF-8 BOM（`U+FEFF`），其余不带：

```
system_toolbox_page.py
embedded_admin_tools/services/icon_service.py
```

Python 解释器能容忍，但部分工具链（AST 解析、diff、`grep` 首行）会出现「第一行莫名匹配不上」的怪事。建议统一为 **UTF-8 无 BOM**。VS Code 右下角编码 → `Save with Encoding → UTF-8`。

### 5.2 遗留备份与数据文件

```
main.py.bak.20260722                  254 KB    ← 源码备份，git 可替代
system_toolbox_page.py.bak.20260722    26 KB    ← 同上
expiry_manager.db                     216 KB    ← 数据文件混在源码目录
study_demo.db                          24 KB
study_notes.db                          0 KB    ← 空文件
login_memory.json                     595 B     ← 含凭据，注意不要外泄
```

注意：`main.py` 现在 5,166 行 / 223 KB，而 `.bak` 是 254 KB —— **备份比现在的文件还大**，说明这份 `.bak` 早于上次重构，已无参考价值。

程序其实已经设计好了数据目录 `ExpiryManager_Data/`（`main.py:279`）并在首次启动自动迁移（`main.py:302`）。根目录这几个文件是迁移前的老位置残留。建议：`git init` 后删除 `.bak`，数据文件移入 `ExpiryManager_Data/` 并加进 `.gitignore`。

### 5.3 README 与实际功能脱节

`README.md`（62 行）只描述了「到期管理」一个模块，只提 `main.py` 和 `requirements.txt` 两个文件，而项目实际已有：工具包、ADB 工具箱、后台接口测试、加密解密、登录检测、行情查询、学习笔记、Q&A 工作日志、系统工具箱、百度网盘 —— 共 10+ 个模块。

**建议补上**：模块清单及对应文件、完整依赖、目录结构说明（哪些是数据目录、哪些可删）、打包命令（`ExpiryManager_fixed.spec` vs `ExpiryManager.spec` 的区别 —— 现在两份 spec 并存，README 只提了一份）。

### 5.4 根目录平铺 25+ 模块，无包结构

清理一次性脚本后，根目录仍有 25 个模块文件平铺。`embedded_admin_tools/` 证明了包结构可行。长期建议逐步收敛：

```
app/
  ui/          各 *_page.py / *_window.py / *_dialogs.py
  db/          各 *_db.py
  services/    业务逻辑
config.py
main.py        仅入口
```

**不必现在动**。等 3.1（`main.py` 拆分）完成、git 用起来之后再做，否则一次改动面太大。

### 5.5 缺失的工程基建

| 项目 | 现状 | 建议 |
|---|---|---|
| 版本控制 | ❌ 无 | `git init`（P0） |
| 依赖清单 | ⚠️ 缺 5 项 | 见 3.6 |
| 代码格式 | ❌ 无 | `ruff format` 或 `black`，一次定型后不再纠结 |
| 静态检查 | ❌ 无 | `ruff check`（见附录 A） |
| 类型检查 | ❌ 无 | `mypy --ignore-missing-imports`，先只对 `services/` 和 `*_db.py` 开 |
| 单元测试 | ❌ 无 | 优先给纯函数补：`parse_expiry_value`、`excel_serial_to_date`、`days_left`、`mask_account_text` |
| CI | ❌ 无 | 本地 git hook 即可，`pre-commit` 跑 ruff + pyflakes |

**测试的投入产出比**：`parse_expiry_value`（47 行 / `main.py:1063`）要处理中文日期、Excel 序列号、混合文本三种格式，是**最容易出错又最好测**的函数 —— 拿 20 个真实样本写参数化测试，以后改它就敢改了。

---

## 六、推荐执行顺序

| 阶段 | 动作 | 为什么这个顺序 |
|---|---|---|
| **第 1 步** | `git init` + `.gitignore` + 首次提交 | 后面所有改动都需要回退能力 | ✅ **已完成**（2.2） |
| **第 2 步** | 修 4 个真 Bug（2.1）；删改源码脚本（2.3） | 影响功能正确性与数据安全，且改动小、风险低 | 🟡 脚本清理 **已完成**；4 个真 Bug **待修** |
| **第 3 步** | 补 `requirements.txt`（3.6）+ 删未使用导入（3.7） | 半小时的事，立刻降低理解成本 |
| **第 4 步** | 抽 `log_setup.py`，全项目接入（2.1 Bug 3 的根因） | 后续所有异常排查都靠它 |
| **第 5 步** | `tools_db.py` 迁移逻辑表驱动（3.4）+ SQL 标识符白名单（3.5） | 改动集中在一个文件，收益明确 |
| **第 6 步** | 拆 `main.py`（3.1），每搬一块验一次 | 最大的一刀，有了 git 和日志才敢动 |
| **第 7 步** | `Database` Mixin 拆分（3.2）、主题接入（4.3）、抽公共窗口主题（4.2） | 结构收敛 |
| **第 8 步** | 补测试、上 ruff/mypy、清 P3 杂项 | 长期维护 |

---

## 附录 A：可复现的检查命令

本次体检用的工具（已装在隔离环境，不污染全局）：

```bash
PYBIN="C:/Users/shaoy/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 未使用导入 / 未定义名 / 未使用局部变量
$PYBIN -m pyflakes *.py embedded_admin_tools/*.py embedded_admin_tools/services/*.py

# 完整 AST 结构分析（函数长度、复杂度、重复块、文档覆盖率）
# 输出同时写入 scripts/_audit_out.txt
$PYBIN scripts/project_audit.py
```

本次 pyflakes 原始输出已存档：`scripts/pyflakes_baseline_2026-09-18.txt`（72 条）。修完后重跑对比，即可量化清理成果。

后续建议补充（需联网安装）：

```bash
$PYBIN -m pip install ruff
ruff check . --exclude dist,build --select F,E9,B,UP,SIM,RET,ARG --line-length 120
ruff format . --exclude dist,build
```

- `F` → pyflakes 全套（未定义名 / 未使用导入）
- `E9` → 语法级错误
- `B` → bugbear（可变默认参数、闭包陷阱 —— **会直接抓到 2.1 的 Bug 4**）
- `SIM` → 可简化写法
- `RET` → return 语句异味
- `ARG` → 未使用参数

## 附录 B：与旧报告 `CODE_AUDIT_REPORT.md`（2026-07-31）的对照

旧报告的方向是对的，但部分结论已过时或与实测不符，避免按错的地图施工：

| 旧报告结论 | 实测结果 | 结论 |
|---|---|---|
| 密码硬编码 `DEFAULT_ADMIN_PASS = "admin"`（列为 P0） | 全文搜索无此代码 | ✅ **已修，可从待办移除** |
| 「多处使用裸 except」 | 仅剩 2 处，其中 1 处在弃用脚本里（`study_demo_window.py:778`） | ✅ 基本已修，严重度被高估 |
| 「SQL 注入风险：部分拼接」（列为 P0） | 值全部参数化；仅 7 处**标识符**拼接，其中只有 `tools_db.py:131` 是拼接值 | 🟡 降级为 P1，见 3.5 |
| 「数据库连接未正确关闭」 | 需单独核实，本次未定性 | ⏳ 待确认 |
| `main.py` 6,038 行 | 现 5,166 行（上次重构已瘦身 872 行） | 🔄 有进展但仍为 P1，见 3.1 |
| 临时文件未清理 | 实为 31 个 / 1,613 行，**其中 11 个会就地重写源码** | 🔴 **严重度被低估**，升为 P0 |
| 「全局状态过多」（举 `logger` 为例） | `logger` 是标准做法，不是异味；真正的全局状态问题是 `main.py` 的模块级 `BASE_DIR`/`DATA_DIR`/`DB_PATH` 被所有模块隐式依赖 | 🔄 结论方向错，需重新定性 |
| 未提及 | **无 git 版本控制**（26K 行代码裸奔） | 🔴 旧报告最大遗漏，见 2.2 |
| 未提及 | **4 个未定义名 / 作用域 Bug** | 🔴 旧报告最大遗漏，见 2.1 |
| 未提及 | 未使用导入约 45 处、死抽象层 `ui_components`/`page_components` | 🟡 见 3.7 |
| 未提及 | 主题抽象被绕过（手写颜色 99 处） | 🟡 见 4.3 |
| 未提及 | `requirements.txt` 缺 5 个依赖 | 🟡 见 3.6 |

---

**体检结论**：项目功能是完整的，`embedded_admin_tools/` 已展示出正确的分层思路，上次重构也确实见效（`main.py` 从 6,038 行降到 5,166 行、裸 `except` 从多处降到 1 处、`build_ui` 从 524 行降到 18 行）。

当前最该做的不是继续重构，而是**先止损**：`git init` 拿到回退能力 ✅、删掉能就地重写源码的脚本 ✅、修掉 4 个点了就崩的真 Bug ✅。**三件止损事项已全部完成**，接下来按第六节的顺序推进结构性重构（从第 3 步补 `requirements.txt` 开始），每一步都安全可控。

**本轮已完成**：版本控制已建立（`dee267d` 基线 + `b19eed7` 清理，87 → 75 文件，修改 0 个），
12 个破坏性补丁已删、3 个生成器已迁入 `scripts/` 并修正路径。
过程中 `git rm` 触发了一次误删事故（见 2.3），已用 `git checkout -- .` 完全恢复并逐项验证无损——
这也再次印证了第 1 步的价值：**先有回退能力，才敢动刀。**

**特别提醒**：2.1 的 4 个 Bug 全部是上一轮「异常处理具体化 + 统一日志」重构引入或遗留的 **回归**（`PIL`/`openpyxl` 引用写进了 except 子句、`logger` 只加在 `main.py`）。这也印证了第六节第 4 步的必要性 —— 没有测试和静态检查兜底，重构本身就在制造新问题。
