# 代码审计报告

**审计时间**: 2026-07-31  
**审计范围**: main.py, tools_page.py, 及相关核心模块  
**代码规范参考**: 阿里巴巴 Java 开发手册（核心原则适配 Python）  
**总代码量**: ~16,674 行 Python

---

## 一、严重问题（Blocker）

### 1.1 单文件过大（God Class）

| 文件 | 行数 | 问题描述 |
|------|------|----------|
| `main.py` | 6,038 行 | **严重违反单一职责原则**。包含：主窗口类、数据库操作类、10+ 个对话框类、业务逻辑、UI 渲染。应按模块拆分为独立文件。 |
| `tools_page.py` | 2,684 行 | 工具页面过大，包含多个独立功能（ADB/截图/编码等），应拆分为子模块。 |

**阿里规范参考**: 单类行数不超过 200 行（推荐），不超过 500 行（强制）。

**建议**:
```
main.py → 拆分为：
  - ui/main_window.py      # 主窗口
  - ui/dialogs/*.py        # 各对话框
  - db/database.py         # 数据库操作
  - services/*.py          # 业务逻辑层
```

---

### 1.2 数据库连接未正确关闭（资源泄漏）

```python
# main.py 中 Database 类的问题示例
conn = sqlite3.connect(self.db_path)  # 连接创建
# ... 使用后未显式关闭 conn.close()
```

**风险**: SQLite 并发访问时可能出现 `database is locked`。

**阿里规范参考**: 资源必须在使用后关闭，推荐使用上下文管理器。

**建议修复**:
```python
# 使用上下文管理器
with sqlite3.connect(self.db_path) as conn:
    cursor = conn.cursor()
    # ... 操作
# 自动关闭
```

---

### 1.3 密码硬编码（安全风险）

```python
# main.py 中发现的硬编码
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "admin"  # 严重安全漏洞！
```

**阿里规范参考**: 禁止硬编码密码，应使用配置或首次启动强制修改。

---

## 二、高危问题（Critical）

### 2.1 异常处理不规范

```python
# 多处使用裸 except
try:
    # 操作
except:  # ❌ 捕获所有异常，包括 KeyboardInterrupt
    pass
```

**阿里规范参考**: 禁止捕获 `Throwable/Exception`，应捕获具体异常类型。

**建议修复**:
```python
try:
    # 操作
except (sqlite3.Error, ValueError) as e:  # ✅ 具体异常
    logger.error(f"操作失败: {e}")
    raise  # 或适当处理
```

---

### 2.2 SQL 注入风险

```python
# 发现字符串拼接 SQL
cursor.execute(f"SELECT * FROM assets WHERE id = {asset_id}")  # ❌ 危险！
```

**阿里规范参考**: 必须使用参数化查询，禁止字符串拼接 SQL。

**建议修复**:
```python
cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))  # ✅ 安全
```

---

### 2.3 空值检查缺失

```python
# 多处直接访问可能为 None 的值
value = some_dict[key]  # 可能 KeyError
result = obj.method()     # obj 可能为 None
```

**阿里规范参考**: 方法入参必须做空值检查（`@NonNull` 思想）。

**建议修复**:
```python
value = some_dict.get(key)  # 安全获取
if value is None:
    return default_value

# 或
if obj is None:
    raise ValueError("obj cannot be None")
result = obj.method()
```

---

## 三、中危问题（Major）

### 3.1 命名不规范

| 问题类型 | 示例 | 规范 | 建议 |
|----------|------|------|------|
| 常量命名 | `color_bg = "#fff"` | 全大写+下划线 | `COLOR_BG` ✅ 已符合 |
| 类命名 | `changePasswordDialog` | 大驼峰 | `ChangePasswordDialog` ✅ 已符合 |
| 方法命名 | `def BuildForm()` | 小写+下划线 | `def build_form()` |
| 变量命名 | `ID` | 小写+下划线 | `record_id` |
| 私有方法 | `def _internal()` | 单下划线前缀 | ✅ 已符合 |

---

### 3.2 魔法数字/字符串

```python
# 多处硬编码数值
width = 28
padx = 6
pady = 4
bg = "#fafafa"  # 重复多次
```

**阿里规范参考**: 魔法值必须定义为常量。

**建议**:
```python
# 在常量区定义
ENTRY_WIDTH = 28
PADDING_SMALL = 6
PADDING_TINY = 4
INPUT_BG_COLOR = "#fafafa"
```

---

### 3.3 重复代码（DRY 原则）

```python
# ChangePasswordDialog 中重复创建 Entry
tk.Entry(master, textvariable=self.old_var, show="*", width=28, bg="#fafafa", ...)
tk.Entry(master, textvariable=self.new_var, show="*", width=28, bg="#fafafa", ...)
tk.Entry(master, textvariable=self.confirm_var, show="*", width=28, bg="#fafafa", ...)
```

**阿里规范参考**: 重复代码必须抽取为方法。

**建议修复**:
```python
def _create_password_entry(self, master, textvariable):
    """创建统一的密码输入框。"""
    return tk.Entry(
        master, textvariable=textvariable, show="*", width=ENTRY_WIDTH,
        bg=INPUT_BG_COLOR, fg=COLOR_TEXT_STRONG, relief="solid",
        borderwidth=1, highlightthickness=1,
        highlightbackground="#cccccc", highlightcolor="#999999"
    )
```

---

### 3.4 方法过长

```python
# main.py 中多个方法超过 100 行
build_ui()          # ~200+ 行
_build_backend_page()  # ~150+ 行
```

**阿里规范参考**: 方法行数不超过 80 行（推荐），不超过 120 行（强制）。

---

## 四、低危问题（Minor）

### 4.1 注释不规范

```python
# 部分注释缺少空格
#这是注释  # ❌
# 这是注释  # ✅

# 方法缺少 docstring
def some_method(self):  # ❌ 无文档
    pass
```

**阿里规范参考**: 类/方法必须有 Javadoc 风格注释。

---

### 4.2 导入顺序混乱

```python
# 当前顺序：标准库 → 第三方 → 内部模块（基本正确）
# 但内部模块中混合了不同层级的导入
```

**建议顺序**:
1. 标准库
2. 第三方库
3. 内部模块（按层级：底层 → 高层）

---

### 4.3 类型注解缺失

```python
# 大量方法缺少类型注解
def process_data(data):  # ❌ 无类型
    pass
```

**建议**:
```python
from typing import Optional, List, Dict

def process_data(data: Dict[str, Any]) -> Optional[str]:  # ✅
    pass
```

---

## 五、代码异味（Code Smell）

### 5.1 临时文件未清理

```
_fix_dup.py
_audit.py
_audit_dup.py
_fix_console_encoding.py
_verify_db.py
_check_dnd_fix.py
_test_overwrite.py
```

**建议**: 临时脚本应放入 `scripts/` 或 `tools/` 目录，或清理。

---

### 5.2 全局状态过多

```python
# 多处使用全局变量
logger = logging.getLogger(__name__)  # 全局 logger
COLOR_BG = "#ffffff"  # 全局常量（可接受）
```

**建议**: 考虑使用依赖注入或配置类管理全局状态。

---

## 六、安全审计（Security）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| SQL 注入 | ⚠️ 风险 | 部分拼接，需全面检查 |
| 密码存储 | ✅ 良好 | 使用 bcrypt/SHA-256 |
| 路径遍历 | ⚠️ 风险 | `resource_path()` 需验证 |
| 命令注入 | ✅ 已修复 | 之前修复了 `adb_page` |
| 敏感信息日志 | ⚠️ 需检查 | 确认无密码打印到日志 |

---

## 七、性能审计（Performance）

| 检查项 | 状态 | 建议 |
|--------|------|------|
| 数据库连接池 | ❌ 缺失 | 高频操作应使用连接池 |
| 图片加载 | ⚠️ 需优化 | 大图未做异步加载 |
| Treeview 大数据 | ⚠️ 需优化 | 数据量大时考虑分页 |
| 内存泄漏 | ⚠️ 需检查 | Toplevel 关闭时确认销毁 |

---

## 八、修复优先级建议

### P0（立即修复）
1. 硬编码密码 → 改为配置或强制修改
2. SQL 注入风险 → 全面参数化查询
3. 数据库连接泄漏 → 使用上下文管理器

### P1（本周修复）
4. 异常处理规范化
5. 空值检查补充
6. 重复代码抽取

### P2（本月修复）
7. 单文件拆分（main.py）
8. 方法过长拆分
9. 类型注解补充

### P3（持续改进）
10. 注释规范
11. 临时文件清理
12. 单元测试补充

---

## 九、工具推荐

```bash
# Python 代码规范检查
pip install flake8 black isort mypy

# 使用
flake8 main.py --max-line-length=120
black main.py --check
isort main.py --check-only
mypy main.py --ignore-missing-imports
```

---

**审计结论**: 代码功能完整，但存在较多规范性问题。建议优先处理 P0/P1 级别问题，特别是安全和资源管理相关项。
