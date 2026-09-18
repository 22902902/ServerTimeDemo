# 任务记录：main.py 代码优雅度重构 — 2026-07-20

## 目标
按审计报告 `_audit_code_elegance.md`（P0-P3 优先级）逐步改进 `main.py` 代码质量。

---

## 已完成

### Step 1 — UI 样式常量提取 ✅
- **问题**：颜色 `#xxx` 和字体元组散落 5800 行代码中
- **操作**：
  - 新增 6 个 `FONT_*` 常量 + 11 个 `COLOR_*` 常量（L150-L166）
  - 全局替换颜色魔法值
  - **Bug 修复**：机械替换把 `FONT_TITLE = ("微软雅黑", 14, "bold")` 错替换为 `FONT_TITLE = FONT_TITLE`（循环引用）。从 `_refactor_constants.py` 历史文件提取原始值后修复

### Step 3 — build_ui 拆分 ✅
- **问题**：`ExpiryManagerApp.build_ui` 长达 524 行，上帝方法
- **操作**：提取为 8 个辅助方法
  | 方法 | 行数 | 职责 |
  |---|---|---|
  | `_build_topbar` | 8 | 顶栏（标题/用户/密码管理） |
  | `_build_navigation` | 14 | 左侧导航树 |
  | `_build_right_panel` | 38 | 右侧面板框架（含 placeholder/工具箱初始化） |
  | `_build_note_page` | 14 | 简单笔记编辑器 |
  | `_build_backend_page` | 170 | 后台接口测试 dashboard |
  | `_build_credentials_page` | 125 | 凭证管理（账号中心） |
  | `_build_process_page` | 120 | 流程中心 |
  | `_build_expiry_page` | 46 | 到期管理表格 |
- **结果**：主 `build_ui` 从 524 行压至 18 行

### Step 4 — 异常处理具体化 + 统一日志 ✅
- **操作**：
  1. 添加 `import logging` + 全局 `logger = logging.getLogger(__name__)`
  2. 4 处 bare `pass` → `logger.exception(...)`
     - `parse_account_image_items`（L525）
     - `parse_expiry_value` 两处（原始 L946/L952）
     - `close_all_backend_windows`（L4603）
  3. 14 处 `except Exception` 窄化为具体异常类型
     - PIL：`PIL.UnidentifiedImageError, OSError`
     - 浏览器：`webbrowser.Error, OSError`
     - Excel：`openpyxl.BadZipFile, openpyxl.exceptions.InvalidFileException, OSError`
     - JSON：`json.JSONDecodeError, OSError`
  4. 3 处 defensive `return str(...)` 窄化为 `(OSError, ValueError, Exception)`

### Step 6 — 注释校准 ✅
- 修复 `build_form() / load_data() / validate_and_save()` 不存在方法的错误引用（L79, L2286）
- 改为 Tkinter Dialog 标准方法名：`body()` / `apply()`

---

## 未完成（Step 2, 5 — 已完成或暂缓）
| 步骤 | 状态 | 说明 |
|---|---|---|
| Step 2 (switch_module 循环化) | ✅ 已完成（上次会话） | `_page_registry` 字典 + `_show_page` 方法 |
| Step 5 (Database 按表拆分) | ⏸ 暂缓 | 风险较高，需充分测试 |

---

## 文件变更
| 文件 | 变更 |
|---|---|
| `main.py` | +22 行（常量区+logging），+8 个辅助方法；build_ui 524→18 行；编译验证通过 |
| 删除 | `_refactor_constants.py`, `_refactor_exceptions.py`, `_fix_bare_passes.py`, `_fix_last_pass.py`, `_fix_circular_fonts.py`, `_extract_build_ui.py`, `_audit_code_elegance.md`, `_REFACTOR_STATUS.md`, `_task_2026-07-17_cleanup_docstring_fix.md` |

## 打包输出
- **exe**：`F:\phpstudy_pro\WWW\ServerTimeDemo\dist\ExpiryManager_fixed.exe` — 31.88 MB
- **坚果云**：`G:\我的坚果云\我的坚果云\软件工具包（日常）\ExpiryManager_fixed.exe` — 31.88 MB
