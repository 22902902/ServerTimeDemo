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
| `dist/`、`build/` | 打包产物与构建中间件 |
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

`scripts/make_portable.py` 把它们**收进一个自包含文件夹** `dist/随身包/`：
里面的 `ExpiryManager_fixed.exe` 双击即可运行，而 exe 同级目录就是程序的
数据目录 —— 数据天然就在它旁边。**换机器时拷这一个文件夹就够了。**

```bash
python scripts/make_portable.py --list          # 先看会收哪些东西
python scripts/make_portable.py --full          # 首次建包（约 635 MB）
python scripts/make_portable.py                 # 以后只刷 exe（几秒）
python scripts/make_portable.py --target E:\    # 直接写到 U 盘
```

包里会放一份 `使用说明.txt`。有一点必须知道：包里
`ExpiryManager_Data/.migrated` 是个**不能删的空文件** —— 程序靠它判断
「数据已经整理好」，删掉会让下次启动把数据搬到别的位置。

### 另存一份带校验的冷备

如果要留一份能核对的归档（含 SHA256 清单）：

```bash
python scripts/export_sensitive.py 目标目录                  # 含 Tools，约 600 MB
python scripts/export_sensitive.py 目标目录 --skip-tools      # 只要数据，约 5 MB
```

它同样是增量的，并在目标目录写 `备份清单.txt` 与 `恢复说明.txt`。

## 打包为 exe

```bash
pyinstaller --noconfirm ExpiryManager_fixed.spec --distpath "dist/随身包"
```

产物直接落在 `dist/随身包/ExpiryManager_fixed.exe` —— 也就是**运行目录**。
这样 `dist/` 下只有一个文件夹，不会出现「exe 在这头、数据在那头」的两份。
（旧命令不带 `--distpath` 时会输出到 `dist/`，那种情况下需要再执行一次
`python scripts/make_portable.py` 把 exe 同步进包。）

说明：

- 请优先使用 `.spec` 文件打包，里面已包含 `embedded_admin_tools` 的配置文件、返回码文件和图标资源。
- 如果直接执行 `pyinstaller main.py`，内嵌接口工具在打包版中可能找不到 `interfaces.json`、`returnCode.json` 等资源。

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
