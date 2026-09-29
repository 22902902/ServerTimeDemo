# 个人系统

基于 `Python + Tkinter + SQLite` 的 Win10 桌面版个人系统，当前已集成：

- 服务器与云服务到期管理
- 后台接口测试
- 供货会员与经济会员接口
- 加密与解密工具
- 登录检测工具
- 行情查询工具

## 已实现功能

- 首次从 `服务器与云服务到期情况.xlsx` 导入数据到本地 SQLite
- 支持记录新增、编辑、删除、搜索
- 启动时弹窗提醒
- 托盘后台提醒
- `15` 天内到期项目每日提醒
- `30` 天内到期项目提示
- 自动识别中文日期、Excel 日期序列值、混合文本日期

## 文件说明

- `main.py`：主程序入口
- `expiry_manager.db`：运行后自动生成的本地数据库
- `requirements.txt`：依赖列表（含每项是 [硬] 还是 [可选] 依赖的标注）
- `requirements.lock.txt`：当前验证过的精确版本快照，复现环境时用
- `scripts/`：开发辅助脚本（体检、依赖盘点、图标生成、冒烟测试），不参与运行

## 本地运行

```bash
pip install -r requirements.txt
python main.py
```

> 需要 Python 3.12（与 `build.bat` 中使用的解释器一致）。

如果目录中存在 `服务器与云服务到期情况.xlsx`，程序首次启动会自动导入。


## 数据与私有配置（不进版本库）

公开仓库里只有代码，**运行数据一律不入库**：

| 内容 | 为什么不入库 |
| --- | --- |
| `*.db`、`login_memory.json`、`remember_me.json` | 数据库与登录凭据（含手机号、密码密文） |
| `build/`、`dist/` | 构建中间件与打包产物（运行目录「随身包」在仓库外，见下） |
| `Tools/` | 收集的工具软件（约 600 MB） |
| `excel/`、`account_images/`、`process_flow_images/` 等 | 业务表格与图片 |
| `embedded_admin_tools/config/interfaces.local.json` | **真实接口地址**（仓库里的 `interfaces.json` 只有 `example.com` 占位符） |

接口配置文件按这个顺序查找（先私有、后示例）：

1. 环境变量 `EXPIRY_INTERFACE_CONFIG` 指向的文件
2. 程序目录旁的 `interfaces.local.json`（打包成 exe 后走这条）
3. 同目录的 `interfaces.local.json`（源码运行走这条）
4. 同目录的 `interfaces.json`（仓库内的示例，只有占位地址）

所以本机放一份 `interfaces.local.json` 就能连真实环境，而且它被 `.gitignore`
排除、不会被提交。

### 换机器 / 拷 U 盘：随身包

运行需要的东西不止数据库 —— 还有 `excel/`（默认导入表）、`account_images/`
（账号与流程截图）、`Tools/`（工具箱）、`interfaces.local.json`（真实接口
地址）。它们本来散在好几个地方，拷的时候容易漏。

所以运行目录就是一个**自包含文件夹**：`F:\ServerTimeDemo_随身包\`
（可用环境变量 `SERVERDEMO_PORTABLE_DIR` 覆盖）。里面的
`ExpiryManager_fixed.exe` 双击即可运行，而 exe 同级目录就是程序的数据目录
—— 数据天然就在它旁边。**换机器时拷这一个文件夹就够了。**

它**特意放在仓库外面**：`dist/` 是 PyInstaller 的默认产物目录，历史上还有过
`build.bat` 首句 `rmdir /s /q dist` 的写法 —— 包放在里面随时可能被连根清掉，
而它装的是全部数据。

```bash
python scripts/make_portable.py --list           # 看包里有什么、护栏齐不齐
python scripts/make_portable.py                  # 维护护栏文件（幂等）
python scripts/make_portable.py --target X:\     # 整份增量同步到 U 盘
```

包里会放一份 `使用说明.txt`。有一点必须知道：包里
`ExpiryManager_Data/.migrated` 是个**不能删的空文件** —— 程序的
`_migrate_data_dir()` 只看它在不在；不在就会把数据根下的 db / 图片 / Tools
**复制一份**进 `ExpiryManager_Data/`。是复制不是搬，**数据不会丢**，但 Tools
有 599 MB，白白多占一块空间。

### 另存一份带校验的冷备

如果要留一份能核对的归档（含 SHA256 清单）：

```bash
python scripts/export_sensitive.py 目标目录                  # 含 Tools，约 600 MB
python scripts/export_sensitive.py 目标目录 --skip-tools      # 只要数据，约 5 MB
```

它同样是增量的，并在目标目录写 `备份清单.txt` 与 `恢复说明.txt`。

## 同步到 GitHub

仓库：<https://github.com/22902902/ServerTimeDemo>（Public）。远端已配好（SSH），
日常同步就是一条命令：

```bash
python scripts/sync_github.py                   # 先看：哪些没提交、哪些没推送
python scripts/sync_github.py -m "改了什么"      # 提交 + 推送
python scripts/sync_github.py --audit           # 全量体检（扫所有已跟踪文件）
```

提交前会自动跑一道**安全体检**，不通过就拒绝提交：

- **文件名红线** —— 数据库、表格、图片、登录凭据、`interfaces.local.json`、
  随身包、AI 工作记忆目录等一律拒绝。
- **内容红线** —— 公网 IP（私有段与 RFC 5737 文档保留段放行）、未放行域名。
- **业务串清单** —— 公司名、内部接口名这类中文串通用规则拦不住，清单放在
  **本机** `.redlines.local.txt`（已 gitignore，一行一个串，`#` 注释）。
  **换机器时记得把它一起带走**，否则这道闸会静默失效。

> ⚠️ 改工作区**删不掉已经推送出去的内容** —— 旧提交照样能被翻出来。
> 真发现敏感信息进了历史，只能重写历史再强推：
>
> ```bash
> git filter-repo --replace-text <替换表> --force   # 注意：会移除 origin，之后要重新 add
> git push -u origin main --force
> ```
>
> 替换值要与原值**等长**，否则会踩到基于像素宽度的截断断言（见
> `scripts/test_expiry_table.py`）。

## 打包为 exe

```bash
pyinstaller --clean --noconfirm ExpiryManager_fixed.spec --distpath "F:/ServerTimeDemo_随身包"
```

产物直接落进**运行目录**：`F:\ServerTimeDemo_随身包\ExpiryManager_fixed.exe`，
不用再手动拷 exe。数据不受影响 —— PyInstaller 只写自己那一个产物文件，
包里其它内容一律不动。

说明：

- 请优先使用 `.spec` 文件打包，里面已包含 `embedded_admin_tools` 的配置文件、返回码文件和图标资源。
- 如果直接执行 `pyinstaller main.py`，内嵌接口工具在打包版中可能找不到 `interfaces.json`、`returnCode.json` 等资源。
- 忘加 `--distpath` 时产物会落到 `dist/`，把 exe 拷进随身包即可。

## 当前提醒规则

- 启动程序时，弹窗展示已过期、15 天内到期、30 天内到期的项目
- 托盘提醒启用后，程序缩小或关闭窗口会转入后台运行
- 15 天内到期和已过期项目，每天提醒一次
- 30 天内到期项目，每天提醒一次

## 后续建议

- 增加“导出回 Excel”
- 增加“开机自启动”
- 增加“提醒时间设置”
- 增加“已处理/续费状态”
