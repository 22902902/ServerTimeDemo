# 流程中心 · 设计评审与重构方案

> 评审日期：2026-09-23　评审对象：`process_page.py` / `credential_process_dialogs.py` / `main.py`（流程相关约 350 行）/ `process_flows` + `process_steps` 两张表
> 结论一句话：**当前实现是"备案场景"的专用表单，不是"通用流程记录"。核心矛盾在于它把步骤定义成 7 个平铺字段，而运维流程的本质是"可复制执行的命令序列 + 校验点"。**

---

## 一、现状诊断

### 1.1 现有结构

| 层 | 位置 | 规模 |
|---|---|---|
| 数据表 | `main.py` L1325–1350（`process_flows` 7 列 / `process_steps` 11 列） | 2 张表 |
| 数据访问 | `main.py` L1725–1875（fetch/add/update/delete） | 约 150 行 |
| 界面类 | `process_page.py` | **152 行** |
| 业务逻辑 | `main.py` L4376–4735（选中/刷新/增删改/复制/打开链接） | **约 360 行** |
| 弹窗 | `credential_process_dialogs.py` L90–233 | 2 个 Dialog |
| 模板 | `main.py` L388–585 硬编码 3 个 dict | 约 200 行 |

**界面**：左 Treeview 流程列表（430px）+ 右「概览卡 → 步骤 Treeview（序号/标题/链接）→ 详情 ScrolledText → 截图预览（320px 卡片，260×170）」。

### 1.2 实测使用画像（本机真实数据，18 个步骤）

| 字段 | 填充 | 占比 | 判读 |
|---|---|---|---|
| `screenshot_path` | 18/18 | **100%** | **这才是记录的主体** |
| `title` | 18/18 | 100% | 必填，正常 |
| `link_url` | 10/18 | 55% | 有用 |
| `description_text` | 7/18 | 38% | 有用但不稳定 |
| `required_text` | 2/18 | **11%** | 备案表单语汇，形同虚设 |
| `note` | 2/18 | 11% | 边缘 |
| `optional_text` | 1/18 | **5%** | 形同虚设 |
| （多图步骤） | 7/18 | 39% | **近四成一步要好几张图** |

现有 3 个流程：`变更备案流程`(5 步) / `example.com 域名备案`(6 步) / `Linux - SSL 证书更新`(7 步)。

### 1.3 六个结构性问题

**① 字段语汇错配（最根本）**
`required_text="必填项说明"` / `optional_text="选填项说明"` 是**备案填表**的语言。运维场景真正需要的是**前置检查**与**预期结果**。证据：
> 流程#4 第 6 步「替换证书文件」，备注字段写着 `文件位置：/etc/nginx/conf.d/ssl` —— 这正是"前置检查"的内容，被挤进了 `note`。

**② 没有「命令」这个一等公民**
`description_text` 是纯文本，命令塞进去的后果：复制时中文说明一起带走、无等宽字体、无法标记语言、无法一键复制。而 Linux 运维 / git 部署 / 提交这类流程，**命令就是流程本身**。
实测：现有 18 步中**命令特征命中 0 条**——不是用户不需要，是**根本没地方放**。

**③ 截图与多图能力被埋没**
截图 100% 填、39% 是多图，但 UI 只给了一张 260×170 的小预览，多图靠「上一张 / 下一张」翻。**投入产出完全倒挂**——最该被看见的东西被摆在了角落。

**④ 搜索覆盖不到步骤**
`fetch_process_flows()`（main.py L1725）只 `LIKE` **流程表**的 title/category/platform/link_url/note。
→ 用户 38% 的步骤说明、55% 的步骤链接**完全搜不到**。"我上次那条命令记在哪个流程里"——无解。

**⑤ 没有「执行」概念**
记录的目的是"下次照着做"，但没有勾选、没有进度、没有执行留痕。且 `updated_at` 只覆盖最后一次修改，**流程改版后历史写法永久丢失**。

**⑥ 无法参数化**
SSL 更新流程里域名/证书路径/目标机器每次都不同，现在只能每次改文本。**一套流程无法服务 N 个域名 / N 台服务器**——这正是"避免重复劳动"失效的地方。

### 1.4 顺手发现的两个真实隐患

**隐患 A：图片存储目录三套并存，其中一套是死代码**
```
PROCESS_FLOW_IMAGE_DIR = BASE_DIR / "process_flow_images"   # L359 定义
ensure_process_flow_image_dir(flow_id)                      # L585 定义 —— 全项目零调用
```
实测：`ensure_process_flow_image_dir` 与 `PROCESS_FLOW_IMAGE_DIR` **从未被任何代码使用**（`process_flow_images/` 目录存在但空）。
而对话框传的是 `image_subdir="process_flows"`（走 `ACCOUNT_IMAGE_DIR`），**历史数据**却直接落在 `account_images/` 根目录 —— 与账号中心的图片混放。三种写法，无一是"按流程分目录"。

**隐患 B：删除流程 / 步骤不回收截图**
`delete_process_flow` / `delete_process_step` 只删 DB 行，图片文件永久留在磁盘 → 孤儿文件无限增长。
（注：`PRAGMA foreign_keys = ON` 在 `Database.__init__` L1231 已开，级联删除步骤本身是正常的，实测孤儿步骤 = 0，此项无误。）

---

## 二、设计目标

| 原则 | 含义 |
|---|---|
| **一份记录，三种形态** | 同一份流程要能"照着读"（图文）、"照着敲"（命令）、"照着验收"（检查点） |
| **记录成本趋近于零** | 边做边记：贴一张图 + 敲一句话。拒绝 6 字段弹窗 |
| **一次录入，多次复用** | 变量化 → 一套流程服务 N 个域名 / 机器 / 环境 |
| **可信** | 危险命令有标记，执行有留痕，历史可回看 |
| **不引入新依赖** | 全部基于现有 Tkinter + sqlite3 + PIL，不碰网络、不装第三方 |

**明确不做**（避免过度设计）：不做流程引擎、不做 DAG 编排、不做多人协作、不做 SSH 远程执行（风险与收益不匹配）。

---

## 三、核心设计

### 3.1 步骤块模型

把「步骤 = 7 个平铺字段」升级为「**步骤 = 若干有序的块**」：

| 块 | 字段 | 服务场景 | 状态 |
|---|---|---|---|
| 序号 + 标题 + 类型 | `step_no` / `title` / `kind` | 全部 | `kind` 新增 |
| 前置检查 | `precheck_text` | 运维、git（执行前必须满足什么） | **新增** |
| 说明 | `description_text` | 备案（点哪里、填什么），放开 Markdown | 复用 |
| **命令块** | `command_text` + `command_lang` | **运维、git、提交** | **新增** |
| 预期结果 | `expected_text` | 全部（怎么判断这一步成功了） | **新增** |
| 资产 | `screenshot_path`（多图，保持 JSON 存法） | 全部 | 复用 |
| 备注 | `note` | 全部 | 复用 |
| 危险标记 | `danger` | 运维 | **新增** |

`kind` 取值：`op`（操作型，默认）/ `cmd`（命令型）/ `check`（校验型）/ `note`（备注型）。
**`required_text` / `optional_text` 不删**（兼容历史），但在 UI 里降级到「更多字段」，默认不展示。

### 3.2 数据模型（建议）

```sql
-- 流程表新增 4 列
ALTER TABLE process_flows ADD COLUMN variables   TEXT DEFAULT '';   -- JSON: 变量定义
ALTER TABLE process_flows ADD COLUMN envs        TEXT DEFAULT '';   -- JSON: 环境列表 ["prod","staging"]
ALTER TABLE process_flows ADD COLUMN favorite    INTEGER DEFAULT 0;
ALTER TABLE process_flows ADD COLUMN sort_order  INTEGER DEFAULT 0;

-- 步骤表新增 5 列
ALTER TABLE process_steps ADD COLUMN kind          TEXT DEFAULT 'op';
ALTER TABLE process_steps ADD COLUMN command_text  TEXT DEFAULT '';
ALTER TABLE process_steps ADD COLUMN command_lang  TEXT DEFAULT 'shell';
ALTER TABLE process_steps ADD COLUMN precheck_text TEXT DEFAULT '';
ALTER TABLE process_steps ADD COLUMN expected_text TEXT DEFAULT '';
ALTER TABLE process_steps ADD COLUMN danger        INTEGER DEFAULT 0;

-- 执行留痕（P1）
CREATE TABLE IF NOT EXISTS process_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_id INTEGER NOT NULL,
    env TEXT DEFAULT '',
    variables_json TEXT DEFAULT '',   -- 执行时的变量快照，回看时能还原
    started_at TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    status TEXT DEFAULT 'running'     -- running / done / aborted
);
CREATE TABLE IF NOT EXISTS process_run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    step_id INTEGER NOT NULL,
    step_no INTEGER NOT NULL,
    done INTEGER DEFAULT 0,
    done_at TEXT DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES process_runs(id) ON DELETE CASCADE
);
```

**迁移策略**：沿用项目已有的「加列迁移」模式（`tools_db.py` 有先例），全部 `ALTER TABLE ... ADD COLUMN` + `DEFAULT`，**不动存量数据**；`screenshot_path` 的 JSON 存法保持不变（`parse_account_image_items` 已同时兼容单路径与 JSON 数组）。
`variables` 结构：
```json
[{"key": "域名", "label": "域名", "default": "example.com", "hint": "不含 www"},
 {"key": "证书目录", "label": "证书目录", "default": "/etc/nginx/conf.d/ssl"}]
```

### 3.3 变量与参数化（"适用各个场景"的关键）

- 命令块与说明中写 `{{域名}}`、`{{证书目录}}`、`{{分支}}`；
- 流程头部「变量栏」显示当前值，可随时改；
- **复制命令时按当前值渲染**，所见即所得；
- 执行留痕里存变量快照 → 半年后回看"上次这台机器是怎么更新的"能完整还原。

**git 提交流程示例**：
- 变量：`{{分支}}=main`、`{{提交说明}}`
- 第 2 步命令：`git add -A && git commit -m "{{提交说明}}"`
- 第 3 步命令：`git push origin {{分支}}`

### 3.4 执行模式（P1）

- 步骤卡左侧勾选框 → 顶部进度条 `3 / 7`；
- `开始执行` 落一条 `process_runs`，勾选即写 `process_run_steps.done_at`；
- 可中断、可续做（下次打开显示"上次执行到第 3 步，是否继续"）；
- **与待办模块的天然联动**：把「执行一次流程」生成一条待办，步骤成为子任务。待办模块（v1.10.0）已有清单分组能力，可复用。

### 3.5 界面布局

```
┌──────────┬────────────────────────────────────────────────┐
│ 流程列表  │ 流程头：标题 [分类] 平台        进度 3/7 ▓▓▓░░░  │
│ [搜索…]  │        [开始执行][编辑][导出MD][复制为脚本]      │
│          ├────────────────────────────────────────────────┤
│ ★收藏     │ 变量：域名=[example.com] 环境=[prod]      [改值]  │
│ 备案 (2)  ├────────────────────────────────────────────────┤
│ 运维 (3)  │ ☐ 2  点击控制台与 SSL 证书      [操作型]  🔗     │
│          │     点击控制台 → SSL 证书 → 申请证书            │
│          │     [缩略图][缩略图][+贴图]                     │
│          │ ┌────────────────────────────────────────────┐ │
│          │ │ ☑ 6  替换证书文件  [命令型][危险]           │ │
│          │ │   前置检查  确认目录存在，先备份旧证书       │ │
│          │ │   shell                            [复制]  │ │
│          │ │   cp /tmp/{{域名}}.crt {{证书目录}}/        │ │
│          │ │   预期结果  nginx -t 报 syntax is ok        │ │
│          │ └────────────────────────────────────────────┘ │
└──────────┴────────────────────────────────────────────────┘
```

关键变化：
1. **左栏 430 → 230px**。流程列表不需要 430px，把宽度让给步骤流。
2. **步骤从表格行 → 图文卡片流**（Canvas 滚动）。表格无法承载图文混排，右边一大片空白正是这个错配的外显。
   - 复用工具箱已跑通的 Canvas 方案与 `_sync_canvas_region` 归顶纪律（含 v1.10.1 修的滚轮 rubber-band 教训，见 `UI_NOTES.md` §10.4）。
3. **命令块专用渲染**：等宽字体、独立底色、右上角复制（复制**渲染后**的值）。
4. **多图横排缩略图**，点击开大图 —— 而不是"上一张/下一张"翻 4 张图。
5. **危险命令自动识别**（`rm -rf` / `git reset --hard` / `DROP TABLE` / `mkfs` / `dd of=` / `chmod 777`）→ 红色徽章，复制时二次确认。

### 3.6 录入流程（把成本压到最低）

现状：每步 → 打开 6 字段弹窗 → 点「添加图片」→ 走文件选择器。
**改造后（快速录入条）**：

| 动作 | 结果 |
|---|---|
| `Ctrl+V` 贴剪贴板截图 | 自动建步骤 + 附图 |
| 连续贴 N 张图 | 自动建 N 个步骤（截图顺序 = 步骤顺序） |
| 敲一行文字 + 回车 | 建步骤（填入标题） |
| `$ ` 开头输入 | 建**命令型**步骤，内容进 `command_text` |
| `! ` 开头输入 | 建**校验型**步骤，内容进 `expected_text` |
| 拖入图片文件 | 同上，批量 |

> **贴图能力现成**：`study_notes_window.py` L751 `_on_ctrl_v` 已实现「剪贴板读 image/png → 存盘 → 落库」，抽成 `image_clipboard.py` 后流程中心直接复用。目前流程步骤只能走 `filedialog.askopenfilename`，与"截图后直接粘"的习惯不符。

精细编辑（改 kind / 前置检查 / 预期结果）保留在详情弹窗里，按需打开。

### 3.7 三场景落地样例

**A. 备案类（现有场景，平滑升级）**
`kind=op`，说明 + 链接 + 多图。**行为与现在完全一致**，只是图文并排更好读。零迁移成本。

**B. Linux 运维（新增能力主战场）**
以现有「Linux - SSL 证书更新」7 步为原型，第 6 步改造为：

| 项 | 内容 |
|---|---|
| 前置检查 | 确认 `{{证书目录}}` 存在，`cp` 备份旧证书 |
| 命令 | `cp /tmp/{{域名}}.crt {{证书目录}}/`<br>`nginx -t && systemctl reload nginx` |
| 预期结果 | `nginx -t` 输出 `syntax is ok`，站点 HTTPS 可访问 |
| 危险 | 否（`systemctl reload` 为非破坏性） |

**C. Git 部署 / 提交流程**
| 步 | 类型 | 前置检查 | 命令 | 预期结果 |
|---|---|---|---|---|
| 1 | check | — | `git status` | 工作区 clean，无未提交文件 |
| 2 | check | 确认分支正确 | `git branch --show-current` | 输出 = `{{分支}}` |
| 3 | cmd | 已确认第 1–2 步 | `git add -A && git commit -m "{{提交说明}}"` | 提交成功 |
| 4 | cmd | **[危险]** 确认已提交 | `git push origin {{分支}}` | 远端收到新提交 |
| 5 | cmd | **[危险]** 部署机 | `git fetch --all && git reset --hard origin/{{分支}}` | `git log -1` = 目标 commit |

**「复制为脚本」**：把流程内所有 `command_text` 按 `step_no` 拼接、渲染变量、附注释头，一次复制成可粘贴的 shell 脚本 —— 运维最实用的一条。

### 3.8 检索

`fetch_process_flows` 改造为两级命中：
```sql
SELECT f.* FROM process_flows f
WHERE f.title LIKE ? OR f.category LIKE ? OR f.platform LIKE ?
   OR EXISTS (SELECT 1 FROM process_steps s WHERE s.flow_id = f.id
              AND (s.title LIKE ? OR s.description_text LIKE ?
                   OR s.command_text LIKE ? OR s.precheck_text LIKE ?))
```
结果树按「流程 → 命中的步骤」两级展开，**命中到命令级直接跳转并高亮**。
（工具箱已有全局搜索 + 标签检索的成熟做法，可对齐。）

### 3.9 导出

| 格式 | 用途 |
|---|---|
| 复制为纯文本 | 已有，保留 |
| **复制为脚本** | 命令块拼接（含变量渲染） |
| **导出 Markdown** | 含图片相对链接，可进笔记库 |
| **导出单页 HTML** | 图片内嵌 base64，单文件可分享/存档 |

### 3.10 模板数据化

现在 3 个模板**硬编码在 `main.py` L388–585**（约 200 行 dict），且"创建模板"只是复制一份预置内容。
**真正有价值的模板是用户自己积累的流程**。改造：
- `process_templates` 表存模板；预置 3 个作为初始数据；
- 「**从当前流程另存为模板**」——这才是"避免重复劳动"的正解；
- 模板导入 / 导出 JSON，可跨机器复用。

---

## 四、架构改造

当前流程中心是**唯一没跟上项目分层约定的旧模块**。对比：

| 模块 | 数据层 | 页面类 | 业务逻辑位置 |
|---|---|---|---|
| 待办 | `todo_db.py` (1709 行) | `todo_page.py` (2467 行) | 在页面类内 ✅ |
| 工具箱 | `tools_db.py` (767 行) | `tools_page.py` (4513 行) | 在页面类内 ✅ |
| 工作日志 | `qa_work_log_db.py` | `qa_work_log_page.py` | 在页面类内 ✅ |
| **流程中心** | **无（混在 main.py）** | `process_page.py` **仅 152 行** | **360 行堆在 main.py** ❌ |

**改造**：
1. 新建 `process_db.py` —— 从 `main.py` 迁出 L1725–1875 的数据访问 + 本次新增列/表的迁移。
2. `process_page.py` 改为 `class ProcessPage(ttk.Frame)` —— 把 `main.py` L4376–4735 的约 360 行业务逻辑搬进来（对齐 `todo_page.py` 的形态）。
3. `process_blocks.py`（可选）—— 命令块 / 步骤卡渲染组件。
4. **`main.py` 预期减少约 550 行**（360 业务 + 150 数据 + 200 硬编码模板）。
5. 新模块记得补进 `ExpiryManager_fixed.spec` 的 `hiddenimports`（`test_release_meta.py` 会盯）。

**公共能力抽离**：
- `image_clipboard.py` —— 剪贴板贴图（从 `study_notes_window.py` 抽出，笔记与流程共用）。
- 图片存储统一到 `process_flow_images/<flow_id>/`，**做一次迁移**：把 `account_images/` 下的流程截图搬到新目录并改写 DB 路径，消除与账号图混放、并清掉死代码 `ensure_process_flow_image_dir` 的方向歧义。
- 删除流程/步骤时提示"该流程有 N 张截图，是否一并删除"。

---

## 五、分阶段落地路线

### P0 —— 一次迭代，立竿见影
| # | 项 | 价值 |
|---|---|---|
| 1 | 加 6 列（kind / command_text / command_lang / precheck_text / expected_text / danger） | 地基 |
| 2 | 命令块渲染 + 一键复制 + 危险标记 | **运维场景从 0 到 1** |
| 3 | 步骤详情改图文混排 + 多图横排缩略图 | 修正 100% vs 角落预览的错配 |
| 4 | `Ctrl+V` 贴图 + 快速录入条 | 录入成本大幅下降 |
| 5 | 搜索覆盖步骤标题/说明/命令 | 检索可用 |
| 6 | 拆出 `process_db.py` | 不拆，后面长不大 |

**验收**：能完整录一条 git 提交流程并「复制为脚本」直接跑通；搜索命令关键词能命中。

### P1 —— 结构升级
7. 变量表 + `{{}}` 插值 + 变量栏 + 复制为脚本
8. 执行模式（勾选 + 进度 + `process_runs` 留痕）
9. 模板数据化 + 从流程另存为模板 + 导入导出 JSON
10. 导出 Markdown / HTML
11. 图片目录统一迁移 + 删除时回收
12. 拆出 `process_page.py` 页面类（main.py 减重）

### P2 —— 锦上添花
13. 截图标注（画圈/箭头，PIL 直出，不引新依赖）
14. 与待办联动（流程 → 待办 + 子任务）
15. 危险命令二次确认 + 命令块「发送到终端」

---

## 六、风险与取舍

| 风险 | 应对 |
|---|---|
| 存量 18 步数据不能坏 | 全部 ADD COLUMN + DEFAULT，不动存量；`required_text` 等字段保留仅降级展示 |
| 图片路径迁移可能失联 | 迁移前先整体备份 `account_images/`；DB 路径改写用批量 UPDATE + 事务；先跑 dry-run 统计 |
| 页面拆分会引入回归 | 拆分**与功能改动分两次提交**；每次跑 `scripts/run_all_tests.py`（当前基线 1175 项） |
| Canvas 滚动类 bug 复发 | 严格遵循 `UI_NOTES.md` §10.4 归顶纪律；首帧不排宽度相关版式 |
| 过度设计导致半途而废 | 严格按 P0 → P1 顺序；P0 独立可用，P1 不完成也不影响使用 |

---

## 七、一句话建议

**先做 P0 的第 2 项（命令块 + 复制）和第 4 项（贴图录入）**——它们分别解决"运维流程无处安放"和"录入太慢"这两个最痛的点，改动量却最小（加列 + 一个渲染组件 + 一个已有实现的复用）。
变量与执行模式是让流程中心从"笔记本"变成"工具箱"的关键，放在 P1。
