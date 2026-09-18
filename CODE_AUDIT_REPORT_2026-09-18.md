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

#### ✅ 已完成（2026-09-18）

补齐后的 `requirements.txt` 按**依赖强度**分组，而不是简单堆列表——这是本次补全才发现的信息：9 个依赖里有 5 个是**硬依赖**（代码里没加 `try`），缺一个程序直接起不来；另 4 个在 `try` 内，缺失只静默降级。分组依据是全项目 import 的静态盘点（`scripts/dep_inventory.py`）。

| 依赖 | 强度 | 位置 | 缺失后果 |
|---|---|---|---|
| `tkinterdnd2` | **硬** | `main.py:120`（未加 try） | **启动直接 ImportError** —— 新环境跑不起来的首要原因 |
| `Pillow` | **硬** | `main.py:122` | 图片预览/截图功能崩 |
| `requests` | **硬** | `services/api_client.py:4` | 接口工具不可用 |
| `pycryptodome` | **硬** | `services/crypto_service.py:3` | DES 加解密崩 |
| `tkcalendar` | **硬** | `api_demo_window.py:1124` | 日期选择器崩 |
| `openpyxl` | 可选 | 函数内导入 | Excel 导入导出不可用 |
| `pystray` | 可选 | `main.py:2920` | 无系统托盘 |
| `pygments` | 可选 | `study_demo_window.py:21` | 无语法高亮 |

关于 `requirements.lock.txt`：没有用 `pip freeze`，而是**只锁本项目的 9 个直接依赖**。因为这个解释器是全局环境，`pip freeze` 会把一堆与本项目无关的包写进去，那是误导而不是复现能力。

> ⚠️ **实测发现 `pygments` 当前并未安装**（`pip list` 无此项、`import pygments` 报 ModuleNotFoundError）。`study_demo_window.py:21` 的 try 保护让它静默降级——不报错，但没有语法高亮。已写进 `requirements.txt` 并标注，装上即可恢复。逐条 import 验证结果：8/9 可导入。

### 3.7 未使用导入 / 死抽象层（约 45 处） — ✅ 已完成

pyflakes 完整清单见 `scripts/pyflakes_baseline_2026-09-18.txt`（原始 72 条）。重点：

| 文件 | 数量 | 值得单独说的 |
|---|---|---|
| `main.py` | 15 | 从 `ui_components` 导入 5 个、从 `page_components` 导入 7 个，**全部未使用** |
| `study_notes_window.py` | 7 | `base64` / `json` / `os` / `subprocess` / `uuid` / `simpledialog` / `StudyNote` |
| `tools_page.py` | 6 | `struct` / `tempfile` / `colorchooser` / `simpledialog` / `datetime` / `TkinterDnD` |
| `study_demo_window.py` | 4 | `time` / `json` / `scrolledtext` |
| `study_demo_db.py` | 2 | `datetime` / `Path` |
| `qa_work_log_page.py` | 4 | 含 `qa_extras` 的 3 个函数 |
| 其余 6 个文件 | 7 | `api_demo_window` / `crypto_window` / `login_checker_window` / `market_quote_window` 各 2 个（`sys`、`Path`） |

**关于 `page_components` / `ui_components`**：这两个模块总计 160 行（88 + 72），`main.py` 一次性导入了其中 12 个函数却一个没用。

**✅ 已定论：两个模块都是活的，不能删。** 它们被 4 个页面模块使用：

```
process_page.py      from page_components import (...) / from ui_components import create_ttk_section_header
credentials_page.py  同上
backend_page.py      from ui_components import (...)
expiry_page.py       from page_components import add_toolbar_buttons, create_content_frame, ...
page_components.py   from ui_components import create_ttk_card
```

所以采取的是「保留模块，删掉 `main.py` 的无用导入」这一支。这也说明它**不是**抽了一半的废弃抽象层，而是一套在用的页面骨架组件 —— 只是 `main.py` 顺手多导了 12 个。

顺带修掉 `main.py:89` 与 `main.py:92` 的 **`threading` 重复导入**（`redefinition of unused 'threading'`）——去掉了第 89 行那个组合导入里的 `threading`，保留第 92 行（它带注释「系统托盘独立线程」，信息量更大）。

#### ✅ 已完成（2026-09-18）

**pyflakes 72 → 7 条**，清理 15 个文件、53 个导入名，**零新增**。消除的条目与预期完全对应，其余差异仅是行号位移。

删之前逐项排除了「看似未使用实为必要」的情况，这几条如果直接照搬 pyflakes 就会出事：

- `main.py:138` 的 `QAWorkLogDB` 确实没用，**但同一行导入的 `QAWorkLogDBExt` 在用**（第 3088 行）→ 只删前者。这种「一行里删一半」是机械删除最容易搞错的地方。
- `ToolsPage` / `AdbPage` 在 `main.py` 里没用，但由 `system_toolbox_page.py` 直接从各自模块导入 → 删 `main.py` 的导入不影响功能（已用绑定检查验证 `system_toolbox_page.ToolsPage is tools_page.ToolsPage`）。
- 全项目无 `from main import ...`、无 `__all__`、无 `globals()`/`eval` 动态取名 → 静态分析结论可信。

另外修掉 4 处无占位符的 f-string（`tools_page` / `adb_page` / `study_demo_window` / `console_page`）。修前逐个确认字符串内不含 `{{`/`}}` 转义 —— 若有转义，去掉 `f` 前缀会改变输出，不能盲改。

**做法上的一处改进**：没有手工改 15 个文件，而是写了 `scripts/prune_unused_imports.py` 按 pyflakes 结果做裁剪，**字节级保留行尾与 BOM**。原因是 `main.py` 是 CRLF+LF 混排，文本编辑会把 21 行的改动写成整文件重写（上一轮已经踩过一次）。这个脚本的语法安全校验当场拦下一个真 bug：单行分支没保留原缩进，会把 `try:` 块体挖空（`tools_page.py` 的 `try: from tkinterdnd2 import ...`）—— 修复后重跑才通过。

验证：33 个正式 `.py` 语法 0 错误；`check_name_scope.py` 0 FAIL；`runtime_smoke.py` 18/18；`main.py` 行尾 CRLF 5012→4994 与净删 18 行完全吻合，无任何整文件改写。

### 3.8 未使用的局部变量（7 处）— 已逐个人工定性，刻意保留

这是清理未使用导入后 pyflakes 仅剩的 7 条。**没有删除**，因为逐条查过之后，它们的成因各不相同，其中一处本报告原先的判断是错的。

| 位置 | 变量 | 定性 |
|---|---|---|
| `main.py:1930` | `cursor` | `conn.execute()` 的返回值本就无用，赋给变量是习惯写法。无害，删除价值低 |
| `study_demo_window.py:396` | `start` | 重构残留：下一行 `idx = "1.0"` 才是真正在用的起点 |
| `study_notes_window.py:1339` | `parent_cat` | 冗余：`pcat` 已持有同一对象，下一行用的是 `pcat.code` |
| `study_notes_window.py:1565` `:1580` | `dlg` | 见下 |
| `tools_page.py:1956` | `current_cols` | **未完成功能的痕迹**：右键菜单本应标出当前图标尺寸，取到了值却没用上 |
| `tools_page.py:2694` | `row_cfg` | 重构后被 `fields` 循环内联取代的孤儿配置字典 |

#### ⚠️ 更正：`study_notes_window.py` 的两处 `dlg` 不是漏写逻辑

本报告初版写的是「可能原本要 `wait_window()` 或读 `dlg.result`，属于疑似漏写逻辑」。**实测查证后这个判断不成立**，两点：

1. **`NoteEditorDialog` 保存后会自己刷新父窗口** —— `study_notes_window.py:1015` 有 `self.parent_window.refresh_notes()`。所以 `add_note` / `edit_note` 里创建完对话框就返回是**正确的**，不需要 `wait_window(dlg)` + 读结果。同文件另外三处（第 90、1354、1382 行）用了 `wait_window`，是因为那三个对话框是「取返回值再决定做什么」的模式，流程本就不同。
2. **保留赋值是有意的** —— 不持有 Toplevel 的 Python 引用，在 Tkinter 里是经典的踩坑点。虽然 `BaseWidget._setup` 会把控件登记进父级的 `children`，实践中一般不回收，但保留一个显式引用是更稳妥的写法。

唯一的小冗余是：`add_note`/`edit_note` 里紧跟的 `self.refresh_notes()` 会在对话框还开着时先刷一次（此时数据无变化，属空刷），保存后由对话框再刷一次。无害，但如果要动，应该删的是那行**多余的 refresh**，而不是 `dlg` 赋值。

### 3.9 日志基建（`log_setup.py`）— ✅ 已完成

原计划是「抽 `log_setup.py`，各模块统一改成 `logger = get_logger(__name__)`，24 个模块都接入」。**实际做下来发现那样是错的**，改成了更小也更有效的方案，理由如下。

#### 先纠正一个前提：不是 24 个模块，是 2 个

全项目实际使用日志的模块只有两个 —— `main.py`（8 处 `logger.exception`）和 `tools_page.py`（1 处）。其余 22 个模块从来没有一行日志调用。往这 22 个文件里各插一个 `logger = get_logger(__name__)` 只会造出 22 个空壳，是**新增死抽象层**，与 3.7 节刚清理的东西同类。

#### 真正没做完的事：发布版一条日志都留不下来

顺着「日志到底写到哪」查下去，发现了比「模块没接入」严重得多的问题：

```
ExpiryManager_fixed.spec:36   console=False
```

打包出来是**无控制台的窗口程序**，`sys.stderr` 没有可写目标。而原来的写法是：

```python
# main.py:104-108（改前）
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
_handler = logging.StreamHandler(sys.stderr)      # ← 发布版这里写向虚空
_handler.setFormatter(...)
logger.addHandler(_handler)
```

两个具体后果：

1. **那 9 处 `logger.exception` 在正式 exe 里全部丢失** —— 而它们的用途正是事后排查。上一个重构「统一异常日志」的目标在最关键的环境里没有达成。
2. **其余模块的日志也无处可去**。`logging.getLogger(__name__)` 是标准做法，但没配 root，消息只会落到 `logging.lastResort`（WARNING 级、无格式化、仅 stderr）—— 同样在发布版丢失。

（附带一处：main 的 logger 设成了 DEBUG，但它只调用 `logger.exception`（ERROR 级），这个 DEBUG 从未起过作用。）

#### 改法：配置 root，而不是逐模块接入

```python
# log_setup.py
def setup_logging(log_dir=None, level=None, *, console=None, filename="app.log"):
    """配置 root logger，重复调用幂等。"""
```

关键在「配 **root**」：只要入口调用一次，任意模块（包括将来新增的）用标准的 `logging.getLogger(__name__)` 就自动获得同一套 handler 和格式，**不需要任何模块改代码**。这才是「全项目接入」最省事也最不容易做错的方式。

配套的四点：

| 措施 | 为什么 |
|---|---|
| 加 `RotatingFileHandler` → `ExpiryManager_Data/logs/app.log`（1 MB × 4） | 发布版唯一可靠的落地点，日志能撑过多次运行 |
| 控制台 handler **先探测再挂** | `console=False` 时 `sys.stderr` 是 `None`，照旧装 StreamHandler 会在每次 emit 抛 `AttributeError` 并被 logging 自己吞掉 —— 表面平静、实际无输出。这类静默失败最难查 |
| 级别默认 INFO，支持 `EXPIRY_LOG_LEVEL` 环境变量覆盖 | 临时抓详细日志不用改代码；避免 DEBUG 淹没有效信息 |
| 目录创建失败只降级不抛异常 | 只读介质/权限不足时，日志基建不该成为程序起不来的原因 |

顺带把控制台流的编码错误策略设为 `replace`（`sys.stderr.reconfigure(errors="replace")`）—— 中文提示打到 cp936 控制台时，不会因为个别字符编码不了就丢掉整条日志。（项目里曾有一个专门修这个的临时脚本，说明这坑踩过。）

入口接入（`main.py`，仅 3 行）：

```python
import log_setup
...
def main():
    # 放在最前：应用构造阶段出的问题也要能落盘（发布版没有控制台可看）
    log_setup.setup_logging(DATA_DIR / "logs")
    mutex, already_exists = acquire_single_instance_mutex()
```

`main.py` 原有那 5 行自装 handler 的代码删除 —— **留着会导致重复输出**（自己的 handler + root 的 handler 各写一次）。`tools_page.py` **一行都不用改**，它的 `logging.getLogger(__name__)` 现在自动生效。

#### 验证（`scripts/test_log_setup.py`，17/17）

不是「能 import 就算过」，逐条都是真实写文件再读回：

- 配 root 后，`tools_page` 模块自己的 logger 和任意新模块的 logger 都落进同一个文件（证明「无需逐模块装 handler」这个核心承诺）
- 模拟 `sys.stderr = None`（打包版场景）：自动探测到无控制台、不挂 StreamHandler、日志仍落盘
- 幂等：重复调用 handler 数量不变，同一条日志只写一次
- **导入 `main` 不产生日志文件**（初始化只在入口 `main()` 里，import 无副作用）
- 日志目录不可写时降级不抛异常
- `RotatingFileHandler` 的尺寸/份数/utf-8 编码确实生效

另做端到端验证：按 `main()` 里那一行真实调用，日志确实落到 `ExpiryManager_Data/logs/app.log`，`main.py` 自己的 logger 与探针 logger 都写入同一文件。

`ExpiryManager_fixed.spec` 的 `hiddenimports` 已补上 `log_setup`，确保打包时一定带上（它会影响启动，值得显式列出而不是依赖自动分析）。

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
| **第 3 步** | 补 `requirements.txt`（3.6）+ 删未使用导入（3.7） | 半小时的事，立刻降低理解成本 | ✅ **已完成** |
| **第 4 步** | 抽 `log_setup.py`，全项目接入（3.9） | 后续所有异常排查都靠它 | ✅ **已完成** |
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

**P1 已完成（第六节第 3、4 步）**：

| 项 | 结果 |
|---|---|
| 3.6 依赖清单 | 4 → 9 个，按 [硬]/[可选] 标注；新增只锁直接依赖的 `requirements.lock.txt`；实测发现 `pygments` 未安装 |
| 3.7 未使用导入 | pyflakes **72 → 7 条**，15 个文件 53 个名字，零新增；`main.py` 行尾零改写 |
| 3.9 日志基建 | 新增 `log_setup.py`（配 root，不逐模块改），补上文件落盘 —— 原来 9 处 `logger.exception` 在 `console=False` 的发布版里**全部丢失** |

三件事的共同点值得记一笔：**都发现了报告初版没看到的事实** —— `ui_components`/`page_components` 是在用的活模块（不是废弃抽象层）、`pygments` 实际未安装、`study_notes_window` 的 `dlg` 不是漏写逻辑、以及最关键的那条：日志基建的缺口不在「模块没接入」，而在「接入的出口在发布版不存在」。**报告是地图，不是实景，施工前必须实地核对。**

**特别提醒**：2.1 的 4 个 Bug 全部是上一轮「异常处理具体化 + 统一日志」重构引入或遗留的 **回归**（`PIL`/`openpyxl` 引用写进了 except 子句、`logger` 只加在 `main.py`）。这也印证了第六节第 4 步的必要性 —— 没有测试和静态检查兜底，重构本身就在制造新问题。

**下一步（第六节第 5 步）**：`tools_db.py` 迁移逻辑表驱动（3.4，5 份几乎一样的建表样板）+ SQL 标识符白名单（3.5，7 处拼接）。改动集中在一个文件、收益明确，是敢动 `main.py` 那 5,166 行之前最合适的一刀。
