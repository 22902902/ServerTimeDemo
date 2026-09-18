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

## 打包为 exe

```bash
pyinstaller --noconfirm ExpiryManager_fixed.spec
```

打包后可执行文件位于 `dist/ExpiryManager_fixed.exe`。

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
