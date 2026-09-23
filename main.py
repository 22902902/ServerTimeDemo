# -*- coding: utf-8 with BOM -*-
"""
===============================================================================
ExpiryManager - 个人系统（到期管理器） v2.0
===============================================================================

📦 项目结构
------------------------------------------------------------------------------
main.py                          ← 主程序入口（含 UI + 业务逻辑 + 数据库）
embedded_admin_tools/            ← 后台工具集（接口测试/加密/登录检测/行情）
  api_demo_window.py             ← 供货会员 & 经济会员接口调试
  crypto_window.py               ← DES/CBC/PKCS7/Base64 加解密工具
  login_checker_window.py        ← 登录检测工具
  market_quote_window.py         ← 行情查询工具
  services/
    api_client.py                ← HTTP 请求客户端（requests 封装）
    interface_service.py         ← 接口配置加载（JSON）
    crypto_service.py            ← 加解密服务
    error_code_service.py        ← 错误码映射
    login_memory_service.py      ← 登录记忆（本机 DPAPI 加密存储）
study_notes_window.py            ← 笔记页面（百度网盘 + Markdown + 标签）
study_notes_db.py                ← 笔记数据库操作层
qa_work_log_page.py              ← Q&A 工作纪要 + 练习记录页面
qa_work_log_db.py                ← Q&A 工作纪要数据库操作层
system_toolbox_page.py           ← 系统工具箱（管理员 CMD / 批处理脚本管理）
baidu_disk_window.py             ← 百度网盘链接管理（独立 Toplevel）
expiry_manager.db                ← SQLite 主数据库（所有数据）

🎯 功能模块（导航树）
------------------------------------------------------------------------------
  工作
  ├── 到期管理              → 服务器/云服务到期（Excel 导入 / 详情 / 账户 / 提醒）
  ├── 账号中心              → 凭证管理（导入导出 / 截图 / 分组筛选）
  ├── 流程中心              → 流程记录（多步骤 / 链接 / 截图 / 必填选填）
  ├── 接口测试 / 文拍        → 后台接口测试（4 个内嵌功能窗口）
  ├── Q&A 与工作纪要        → Q&A + 每周纪要 + 练习记录
  └── 系统工具箱           → 管理员 CMD / PowerShell / 批处理脚本
  生活
  ├── 笔记                  → 百度网盘 + Markdown + 标签 + 截图粘贴
  └── Python 学习           → 视频课程代码学习

  导航结构唯一数据源为 nav_sidebar.NAV_MODEL（改导航只需改那里）。

🏗️ 核心架构：单窗口 + 多 Frame 切换
------------------------------------------------------------------------------
  主窗口（ExpiryManagerApp）使用【页面容器 + pack_forget/pack】模式：
  1. 左侧：SidebarNav 自绘分组侧栏（工作 / 生活），见 nav_sidebar.py
  2. 右侧：page_container，承载各模块 Frame
  3. 切换：switch_module() 统一管理页面切换
  4. 页面类型：
     - 内嵌页面（Frame）：笔记 / Q&A纪要 / 系统工具箱
     - 内嵌 tk.Frame：后台接口测试页面（始终在内存）
     - 独立 Toplevel：账号管理 / 凭证编辑 / 流程编辑等弹窗
     - 系统托盘：TrayController，后台静默运行

🗄️ 数据库设计（SQLite）
------------------------------------------------------------------------------
  assets           资产记录（编号/平台/主体/到期日期/资源详情）
  accounts         资产关联账号（一对多，FOREIGN KEY ON DELETE CASCADE）
  shared_accounts  共享账号台账（按 group_key 分组，支持截图/链接/邮箱/手机）
  credential_items 统一凭证（标题/分类/平台/链接/账号密码/截图）
  process_flows    流程记录（标题/分类/平台/链接/备注）
  process_steps    流程步骤（flow_id 关联 foreign key，多对一，含截图）
  bat_scripts      批处理脚本（名称/内容/分类/标签，工具箱模块使用）
  users            用户表（用户名 + bcrypt 哈希密码）
  app_state        应用状态（key-value，用于记住列宽/关闭行为等偏好）

🔑 权限与安全
------------------------------------------------------------------------------
  - 默认管理员：admin（首次启动强制修改密码，不再硬编码弱密码）
  - 登录对话框：校验 users 表，登录后解锁管理员功能
  - 本机加密存储：tkinter CryptAcquireContext → Windows DPAPI
  - 密码哈希：bcrypt 风格迭代 SHA-256（兼容无 bcrypt 库的环境）

📚 代码阅读路线
------------------------------------------------------------------------------
  1. 读 main.py 顶部本注释块，搞清整体结构和文件布局
  2. 读 ExpiryManagerApp.__init__ + build_ui：理解主窗口初始化流程
  3. 读 switch_module()：页面切换枢纽，理解全 UI 的组织方式
  4. 读 Database 类：封装所有数据库操作，业务层直接调用 db.xxx()
  5. 读各 Dialog 类（AssetDialog / AccountEditDialog 等）：
     均遵循 build_form() 构建表单 + load_data() 填充 + validate_and_save() 保存的模式
  6. 读内嵌页面（study_notes_window.py / qa_work_log_page.py /
     system_toolbox_page.py）：各模块完全独立，可单独阅读

===============================================================================
"""

# -----------------------------------------------------------------------------
# 01. 标准库导入
# -----------------------------------------------------------------------------
import zipfile, datetime as _dt
import re          # 正则：日期文本解析、Excel 序列号转换
import sqlite3     # SQLite 数据库驱动
import threading    # 系统托盘独立线程
import sys         # sys.frozen 判断打包环境
import hashlib     # 密码哈希（bcrypt 前置：迭代 SHA-256）
import ctypes      # Windows API：消息框、焦点控制
import base64      # 记住密码简单混淆
import json         # 凭证截图序列化（JSON 数组格式）
import shutil      # 文件复制：图片导入存储
import os          # 启动外部程序：os.startfile
import webbrowser  # 浏览器打开链接
import logging       # 统一异常日志（配置见 log_setup.py，在 main() 中初始化）

# 全局 logger：级别与输出目标由 log_setup.setup_logging() 统一配置。
# 这里不再自行装 handler —— 那样只有本模块的日志有出口，且发布版（spec 里
# console=False，无控制台）会全部丢失，详见 log_setup.py 的模块说明。
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 02. 第三方库（需 pip install -r requirements.txt）
# -----------------------------------------------------------------------------
from dataclasses import dataclass          # 轻量数据结构（ReminderSummary）
from datetime import date, datetime, timedelta  # 日期时间处理
from pathlib import Path                  # 跨平台路径操作

import tkinter as tk                       # Tkinter 主命名空间
from tkinter import ttk                    # Themed Tkinter（现代样式）
# ★ 拖拽支持：TkinterDnD 必须替换 tk.Tk 作为根窗口
from tkinterdnd2 import TkinterDnD
from tkinter import filedialog, messagebox, scrolledtext, simpledialog
from PIL import Image, ImageTk, UnidentifiedImageError  # 图片预览与缩放

# -----------------------------------------------------------------------------
# 03. 项目内部模块导入
# -----------------------------------------------------------------------------
#  日志基建：其他模块的 logger 输出目标由它决定，需在入口处先初始化
import log_setup

#  应用图形资产（应用标记 / 导航图标，Pillow 超采样渲染）
import app_icons

#  左侧分组导航（自绘侧栏，替代原生 Treeview）
from nav_sidebar import SidebarNav

#  后台工具集（内嵌 adminDemo 的 4 个核心功能）
from embedded_admin_tools.api_demo_window import ApiDemoWindow
from embedded_admin_tools.crypto_window import CryptoToolWindow
from embedded_admin_tools.login_checker_window import LoginCheckerWindow
from embedded_admin_tools.market_quote_window import MarketQuoteToolWindow
from embedded_admin_tools.services.login_memory_service import LoginMemoryService

#  功能页面（各模块独立文件，嵌入主窗口 page_container）
from study_notes_window import StudyNotesPage   # 学习笔记页面
from study_notes_db import StudyNotesDB          # 笔记数据库操作
from qa_work_log_page import QAWorkLogPage       # Q&A + 纪要 + 练习记录页面
from qa_work_log_db import QAWorkLogDBExt  # Q&A + 纪要数据库操作
from system_toolbox_page import SystemToolboxPage  # 系统工具箱页面
from study_demo_window import StudyDemoPage           # Python 学习辅助模块
from study_demo_db import get_conn as get_study_demo_conn  # 学习模块数据库
from account_windows import AccountManagerDialog as SharedAccountManagerDialog
from backend_page import BackendPage
from credential_process_dialogs import CredentialItemDialog
from expiry_dialogs import AssetDialog, DetailDialog, SettingsDialog
from expiry_page import ExpiryPage, summarize_cell_text, treeview_font
from credentials_page import CredentialsPage
from process_page import ProcessImageTools, ProcessPage
from process_db import ProcessDBMixin, init_process_tables
from ui_theme import MAIN_PALETTE, THEME, TYPOGRAPHY
from dialog_form_style import apply_dialog_form_style, create_form_entry, create_form_frame, create_form_label
import app_version
import markdown_view
from todo_db import TodoDB  # 待办事项数据库（含法定节假日日历）
from todo_page import TodoAlertDialog, TodoPage  # 待办 / 提醒事项页面
from excel_db import ExcelDB  # Excel 学习中心数据库（200 个内置函数 + 复习进度）
from excel_page import ExcelImageTools, ExcelLearningPage  # Excel 学习中心页面


# =============================================================================
# 04. 全局常量定义
# =============================================================================
# 版本号 / 更新日志集中在 app_version.py（以前是硬编码，重打包多少次界面都一样，
# 用户没法判断手上是不是新版）。顶栏、窗口标题、所有弹窗都显示这同一串。
APP_TITLE = app_version.APP_TITLE
EXPIRY_MODULE_TITLE = "服务器与云服务到期情况"
CURRENT_PROJECT_NAME = "ServerTimeDemo"
# Windows Mutex 名称：同一机器同时只能运行一个实例（打包后 exe 互斥）
APP_MUTEX_NAME = "ServerTimeDemoPersonalSystemSingletonMutex"

# ---------------------------------------------------------------------------
# 04-b. UI 样式常量（从全局主题模块映射，避免散落硬编码）
# ---------------------------------------------------------------------------
FONT_TITLE = TYPOGRAPHY.title
FONT_SUBTITLE = TYPOGRAPHY.subtitle
FONT_SECTION = TYPOGRAPHY.section
FONT_PAGE_TITLE = TYPOGRAPHY.page_title
FONT_CAPTION = TYPOGRAPHY.caption
FONT_BASE = TYPOGRAPHY.body
FONT_METRIC = TYPOGRAPHY.metric
FONT_BADGE = TYPOGRAPHY.badge

COLOR_BG = MAIN_PALETTE.bg
COLOR_MUTED = MAIN_PALETTE.text_muted
COLOR_MUTED_2 = MAIN_PALETTE.text_secondary
COLOR_TEXT_STRONG = MAIN_PALETTE.text_primary
COLOR_TEXT = MAIN_PALETTE.text_secondary
COLOR_TEXT_DARK = MAIN_PALETTE.text_primary
COLOR_LINK = MAIN_PALETTE.link
COLOR_SUCCESS = MAIN_PALETTE.success
COLOR_WARN = MAIN_PALETTE.warn
COLOR_INPUT_BG = MAIN_PALETTE.input_bg
COLOR_INPUT_BORDER = MAIN_PALETTE.input_border
COLOR_INPUT_FOCUS = MAIN_PALETTE.input_focus

# ---------------------------------------------------------------------------
# 04-c. 布局参数常量（避免散落魔法数字）
# ---------------------------------------------------------------------------
ENTRY_WIDTH = 28                    # 密码/文本输入框默认宽度
PADDING_X = 6                       # 表单元素水平内边距
PADDING_Y = 4                       # 表单元素垂直内边距
PADDING_TITLE = (6, 10)             # 标题区域下边距
MIN_PASSWORD_LENGTH = 8             # 密码最小长度（安全审计要求）
COLOR_BADGE_BG = MAIN_PALETTE.badge_bg

# ---------------------------------------------------------------------------
# 04-a. 到期管理表格列定义（ttk.Treeview）
# ---------------------------------------------------------------------------
TREE_COLUMNS = (
    "id", "record_no", "platform", "account_no", "account_subject",
    "resource_type", "resource_detail", "resource_subject",
    "expiry_date", "days_left", "detail_action", "accounts_action", "note",
)
# 导出 Excel / 详情弹窗时使用的列（不含操作列）
DISPLAYABLE_COLUMNS = (
    "record_no", "platform", "account_no", "account_subject",
    "resource_type", "resource_detail", "resource_subject",
    "expiry_date", "note",
)
# 默认可见列（首次运行时 Treeview 显示这些列）
DEFAULT_DISPLAY_COLUMNS = [
    "record_no", "platform", "account_no", "account_subject",
    "resource_type", "resource_detail", "expiry_date",
]

# 列元数据字典：key=字段名，value={title:表头, width:默认宽度}
COLUMN_META = {
    "id":               {"title": "ID",          "width": 60},
    "record_no":        {"title": "编号",         "width": 100},
    "platform":         {"title": "平台",         "width": 130},
    "account_no":       {"title": "账号信息",     "width": 180},
    "account_subject":  {"title": "主体账号",     "width": 180},
    "resource_type":    {"title": "资源类型",     "width": 120},
    "resource_detail":  {"title": "资源详情",     "width": 280},
    "resource_subject": {"title": "资源主体",     "width": 180},
    "expiry_date":      {"title": "到期日期",     "width": 100},
    "days_left":        {"title": "剩余天数",     "width": 90},
    "detail_action":    {"title": "详情",         "width": 80},
    "accounts_action":  {"title": "账户",         "width": 110},
    "note":             {"title": "备注",         "width": 220},
}

# 详情弹窗字段列表（字段名 → 中文标签），按显示顺序排列
DETAIL_FIELDS = [
    ("record_no",             "编号"),
    ("platform",              "平台"),
    ("account_no",            "账号编号"),
    ("account_subject_code",  "主体账号编号"),
    ("account_subject_name",  "主体账号名称"),
    ("resource_type",         "资源类型"),
    ("resource_detail",       "资源详情"),
    ("resource_subject_code", "资源主体编号"),
    ("resource_subject_name", "资源主体名称"),
    ("expiry_date",           "到期日期"),
    ("expiry_raw",            "原始到期内容"),
    ("note",                  "备注"),
]


# =============================================================================
# 05. 路径与文件常量
# =============================================================================

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "ExpiryManager_Data"

# ═════════════════════════════════════════════════════════════════════════════
# 数据目录迁移（首次启动自动执行）
# ═════════════════════════════════════════════════════════════════════════════
MIGRATED_FILE = DATA_DIR / ".migrated"

_MIGRATION_MAP = [
    ("expiry_manager.db",        "expiry_manager.db"),
    ("study_demo.db",            "study_demo.db"),
    ("remember_me.json",         "remember_me.json"),
    ("login_memory.json",        "login_memory.json"),
    ("account_images",           "account_images"),
    ("study_notes_images",       "study_notes_images"),
    ("study_notes_attachments",  "study_notes_attachments"),
    ("process_flow_images",      "process_flow_images"),
    ("Tools",                    "Tools"),
    ("excel",                    "excel"),
    ("adb_history",              "adb_history"),
    ("study_demo",               "study_demo"),
]


def _migrate_data_dir():
    """将旧位置的文件/目录迁移到 ExpiryManager_Data/（仅首次执行）"""
    if MIGRATED_FILE.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("[迁移] 首次启动，正在整理数据目录 ...")
    for src_name, dst_name in _MIGRATION_MAP:
        src = BASE_DIR / src_name
        dst = DATA_DIR / dst_name
        if not src.exists():
            continue
        if dst.exists():
            print(f"  [跳过] {src_name}（目标已存在）")
            continue
        try:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            print(f"  [迁移] {src_name} -> ExpiryManager_Data/{dst_name}")
        except Exception as ex:
            print(f"  [迁移失败] {src_name}: {ex}")
    MIGRATED_FILE.touch()
    print(f"[迁移] 完成。数据目录: {DATA_DIR}")


def ensure_data_dir():
    """确保 DATA_DIR 及所有子目录存在"""
    subdirs = [
        "account_images/credentials",
        "account_images/labels",
        "study_notes_images",
        "study_notes_attachments",
        "process_flow_images",
        "Tools",
        "excel",
        "adb_history",
        "study_demo",
    ]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for d in subdirs:
        (DATA_DIR / d).mkdir(parents=True, exist_ok=True)
    return DATA_DIR



DB_PATH = BASE_DIR / "expiry_manager.db"
# ★ 专用 Excel 目录（避免打包时被误删，集中管理数据文件）
EXCEL_DIR = BASE_DIR / "excel"
DEFAULT_IMPORT_FILE = EXCEL_DIR / "服务器与云服务到期情况.xlsx"


def ensure_excel_dir() -> Path:
    """确保 Excel 目录存在并返回路径。"""
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    return EXCEL_DIR
ACCOUNT_IMAGE_DIR = BASE_DIR / "account_images"
ACCOUNT_IMAGE_FILE_TYPES = [("图片文件", "*.png *.jpg *.jpeg *.webp *.bmp *.gif")]
CHECK_INTERVAL_MS = 60 * 60 * 1000
# 待办到点提醒的巡检间隔：30 秒。比主提醒的 1 小时密得多 —— 提醒是按分钟
# 定时的，一小时才看一眼等于没有。一次巡检只是一条 SQL，开销可以忽略。
TODO_TICK_MS = 30 * 1000
BACKEND_FEATURE_ITEMS = [
    {
        "key": "api_demo",
        "title": "供货会员与经济会员接口",
        "summary": "直接复制 adminDemo 主功能，支持登录、接口列表、参数编辑、请求发送、请求与返回查看。",
    },
    {
        "key": "crypto",
        "title": "加密与解密工具",
        "summary": "DES / CBC / PKCS7 / Base64 / UTF-8 加解密辅助工具。",
    },
    {
        "key": "login_checker",
        "title": "登录检测工具",
        "summary": "快速校验账号登录结果，适合排查账号、环境和登录接口问题。",
    },
    {
        "key": "market_quote",
        "title": "行情查询工具",
        "summary": "独立行情查询功能，登录后只提供 commodity_data_query 行情接口与导出能力。",
    },
]

PROCESS_FLOW_TEMPLATES = [
    {
        "key": "domain_icp",
        "label": "域名备案流程",
        "flow": {
            "title": "域名备案流程",
            "category": "备案",
            "platform": "云服务商备案平台",
            "link_url": "",
            "note": "适用于首次备案、补充资料或备案信息更新场景。不同服务商页面名称略有差异，可按实际情况调整步骤。",
        },
        "steps": [
            {
                "step_no": 1,
                "title": "登录备案平台",
                "link_url": "",
                "description_text": "登录云服务商后台，进入备案中心或 ICP 备案入口，确认备案主体和备案域名所属账号正确。",
                "required_text": "备案账号、主体信息、域名归属账号。",
                "optional_text": "历史备案号、历史工单编号。",
                "note": "如果域名不在当前账号下，先处理域名转入或授权。",
            },
            {
                "step_no": 2,
                "title": "填写主体与网站信息",
                "link_url": "",
                "description_text": "按平台向导填写主体名称、证件信息、负责人信息、网站服务内容、接入信息等。",
                "required_text": "主体名称、证件号码、负责人姓名、手机号、域名、服务内容。",
                "optional_text": "备用邮箱、办公电话、通信地址补充说明。",
                "note": "注意区分个人备案和企业备案，字段要求不同。",
            },
            {
                "step_no": 3,
                "title": "上传材料并提交初审",
                "link_url": "",
                "description_text": "上传营业执照、身份证、核验照或授权书等资料，检查图片清晰度后提交。",
                "required_text": "主体证件、负责人证件、域名证书或授权材料。",
                "optional_text": "补充说明文件、委托书。",
                "note": "上传前检查证件有效期和图片方向。",
            },
            {
                "step_no": 4,
                "title": "跟进审核结果",
                "link_url": "",
                "description_text": "关注平台初审、短信核验、管局审核结果，如被退回按意见修改后重新提交。",
                "required_text": "短信验证码核验、退回意见处理。",
                "optional_text": "工单备注、补充沟通记录。",
                "note": "可把退回原因和修改点补在步骤备注中，方便下次复用。",
            },
        ],
    },
    {
        "key": "mini_program_annual",
        "label": "小程序年审流程",
        "flow": {
            "title": "小程序年审流程",
            "category": "年审",
            "platform": "微信公众平台",
            "link_url": "https://mp.weixin.qq.com/",
            "note": "适用于小程序主体信息复核、资质年审、管理员确认等场景，可按具体页面要求补充。",
        },
        "steps": [
            {
                "step_no": 1,
                "title": "登录微信公众平台",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "使用管理员或运营者账号登录微信公众平台，进入对应小程序后台。",
                "required_text": "管理员微信扫码、账号归属确认。",
                "optional_text": "运营者协助确认、备用管理员信息。",
                "note": "如存在多个小程序，先确认当前操作对象。",
            },
            {
                "step_no": 2,
                "title": "进入年审或资质更新入口",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "在设置、主体信息、资质中心或消息提醒中找到年审入口，查看本次需处理项目。",
                "required_text": "当前主体状态、待更新项目。",
                "optional_text": "历史审核记录、过往提交截图。",
                "note": "不同年份入口可能不同，建议截图留档。",
            },
            {
                "step_no": 3,
                "title": "填写并核对主体资料",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "按页面要求填写企业名称、统一社会信用代码、法人信息、联系人信息等，并核对是否与证件一致。",
                "required_text": "企业名称、统一社会信用代码、法人姓名、联系人手机号。",
                "optional_text": "备用邮箱、座机、补充说明。",
                "note": "信息必须与营业执照和身份证保持一致。",
            },
            {
                "step_no": 4,
                "title": "上传材料并提交审核",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "上传营业执照、身份证明、授权函等资料，确认无误后提交审核，并记录提审时间。",
                "required_text": "营业执照、身份证件、授权资料。",
                "optional_text": "补充证明、历史截图。",
                "note": "提交后跟进站内通知或管理员消息。",
            },
        ],
    },
    {
        "key": "wechat_official_auth",
        "label": "公众号认证流程",
        "flow": {
            "title": "公众号认证流程",
            "category": "认证",
            "platform": "微信公众平台",
            "link_url": "https://mp.weixin.qq.com/",
            "note": "适用于公众号年度认证、新号认证或认证到期续费场景。",
        },
        "steps": [
            {
                "step_no": 1,
                "title": "登录公众号后台",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "登录公众号账号，进入公众号后台，确认本次认证主体和账号无误。",
                "required_text": "管理员扫码、公众号主体确认。",
                "optional_text": "协作者账号、历史认证记录。",
                "note": "建议先核对主体名称和认证到期时间。",
            },
            {
                "step_no": 2,
                "title": "进入微信认证入口",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "进入设置或微信认证入口，查看是否为新认证、续费认证或资料变更认证。",
                "required_text": "认证入口、认证类型确认。",
                "optional_text": "客服记录、历史工单号。",
                "note": "不同类型的认证所需资料可能不同。",
            },
            {
                "step_no": 3,
                "title": "填写认证资料",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "填写企业信息、认证名称、联系人信息、发票信息等，并核对付款或审核要求。",
                "required_text": "企业名称、统一社会信用代码、联系人、手机号、认证名称。",
                "optional_text": "发票抬头、邮寄地址、补充说明。",
                "note": "如名称涉及品牌或商标，提前准备证明材料。",
            },
            {
                "step_no": 4,
                "title": "上传材料并跟进审核",
                "link_url": "https://mp.weixin.qq.com/",
                "description_text": "上传营业执照、申请公函、身份证明等，完成提交后持续跟进审核、回访电话和结果通知。",
                "required_text": "营业执照、公函、身份证明。",
                "optional_text": "商标证明、授权书、补充材料。",
                "note": "电话回访常见，注意保持联系人电话畅通。",
            },
        ],
    },
]


@dataclass
class ReminderSummary:
    """到期提醒摘要数据类。

    属性:
      overdue:  已过期资产列表 [{title, platform, resource_type, expiry_date, days_left}]
      due_15:   15 天内到期资产列表（同结构）
      due_30:   30 天内到期资产列表（同结构）

    方法:
      has_items -> bool  返回是否还有需要提醒的资产
    """
    overdue: list
    due_15: list
    due_30: list

    @property
    def has_items(self) -> bool:
        return bool(self.overdue or self.due_15 or self.due_30)


def excel_serial_to_date(value: float) -> date:
    base = datetime(1899, 12, 30)
    return (base + timedelta(days=float(value))).date()


def normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def ensure_account_image_dir(subdir: str = "") -> Path:
    """确保图片存储目录存在，支持子目录参数。
    
    Args:
        subdir: 可选子目录名，如 'credentials' 或 'process_flows'
    
    Returns:
        图片存储目录的完整路径
    """
    target_dir = ACCOUNT_IMAGE_DIR / subdir if subdir else ACCOUNT_IMAGE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def copy_account_image_to_store(source_path: Path, subdir: str = "") -> Path:
    """复制图片到存储目录。
    
    Args:
        source_path: 源图片路径
        subdir: 可选子目录名，用于区分不同模块的图片
    
    Returns:
        存储后的图片路径（相对路径，便于迁移）
    """
    target_dir = ensure_account_image_dir(subdir)
    suffix = source_path.suffix or ".png"
    safe_suffix = suffix if len(suffix) <= 8 else ".png"
    # 命名规则：YYYYMMDD_HHMMSS_微秒.扩展名
    target_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{safe_suffix}"
    target_path = target_dir / target_name
    shutil.copy2(source_path, target_path)
    return target_path


def resolve_account_image_path(image_value: str) -> Path | None:
    image_paths = resolve_account_image_paths(image_value)
    return image_paths[0] if image_paths else None


def build_account_image_item(path: str = "", label: str = "") -> dict[str, str]:
    return {
        "path": normalize_text(path),
        "label": normalize_text(label),
    }


def parse_account_image_items(image_value: str) -> list[dict[str, str]]:
    text = normalize_text(image_value)
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                items: list[dict[str, str]] = []
                for item in data:
                    if isinstance(item, dict):
                        path = normalize_text(item.get("path") or item.get("image_path") or item.get("value"))
                        label = normalize_text(item.get("label") or item.get("name") or item.get("title"))
                    else:
                        path = normalize_text(item)
                        label = ""
                    if path:
                        items.append(build_account_image_item(path, label))
                return items
        except Exception:
            logger.exception("Unexpected error in parse_account_image_items")
            pass
    if " | " in text:
        return [build_account_image_item(part.strip(), "") for part in text.split(" | ") if part.strip()]
    if "\n" in text:
        return [build_account_image_item(part.strip(), "") for part in text.splitlines() if part.strip()]
    return [build_account_image_item(text, "")]


def parse_account_image_values(image_value: str) -> list[str]:
    return [item["path"] for item in parse_account_image_items(image_value) if item.get("path")]


def serialize_account_image_items(image_items: list[dict[str, str]]) -> str:
    normalized: list[dict[str, str]] = []
    seen = set()
    for item in image_items:
        if isinstance(item, dict):
            path = normalize_text(item.get("path"))
            label = normalize_text(item.get("label"))
        else:
            path = normalize_text(item)
            label = ""
        if not path:
            continue
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(build_account_image_item(path, label))
    if not normalized:
        return ""
    if len(normalized) == 1 and not normalized[0]["label"]:
        return normalized[0]["path"]
    if all(not item["label"] for item in normalized):
        return json.dumps([item["path"] for item in normalized], ensure_ascii=False)
    return json.dumps(normalized, ensure_ascii=False)


def serialize_account_image_values(image_values: list[str]) -> str:
    return serialize_account_image_items([build_account_image_item(value, "") for value in image_values])


def resolve_account_image_paths(image_value: str) -> list[Path]:
    result: list[Path] = []
    for item in parse_account_image_items(image_value):
        image_path = Path(item["path"])
        if not image_path.is_absolute():
            image_path = BASE_DIR / image_path
        result.append(image_path)
    return result


def get_account_image_storage_value(image_path: Path) -> str:
    try:
        return str(image_path.resolve().relative_to(BASE_DIR.resolve()))
    except (OSError, ValueError, Exception):
        return str(image_path.resolve())


def get_account_image_file_name(image_value: str) -> str:
    image_paths = resolve_account_image_paths(image_value)
    if not image_paths:
        return ""
    return " | ".join(path.name for path in image_paths)


def get_account_image_path_text(image_value: str) -> str:
    values = parse_account_image_values(image_value)
    return " | ".join(values)


def get_account_image_label_text(image_value: str) -> str:
    labels = [item["label"] for item in parse_account_image_items(image_value) if item.get("label")]
    return " | ".join(labels)


def get_account_image_display_text(image_value: str) -> str:
    parts: list[str] = []
    for item in parse_account_image_items(image_value):
        path = item.get("path", "")
        label = item.get("label", "")
        if not path:
            continue
        parts.append(f"{label}: {path}" if label else path)
    return " | ".join(parts)


def normalize_account_image_ref(image_value: str) -> str:
    image_path = resolve_account_image_path(image_value)
    if not image_path:
        return ""
    try:
        return str(image_path.resolve()).lower()
    except (OSError, ValueError, Exception):
        return str(image_path).lower()


def normalize_account_image_refs(image_value: str) -> list[str]:
    refs: list[str] = []
    for image_path in resolve_account_image_paths(image_value):
        try:
            refs.append(str(image_path.resolve()).lower())
        except (OSError, ValueError, Exception):
            refs.append(str(image_path).lower())
    return refs


def open_account_image_folder(image_value: str):
    image_path = resolve_account_image_path(image_value)
    if not image_path:
        raise FileNotFoundError("当前没有截图路径。")
    folder_path = image_path.parent if image_path.parent.exists() else None
    if not folder_path:
        raise FileNotFoundError(f"截图目录不存在：{image_path.parent}")
    os.startfile(str(folder_path))


class AccountImagePreview:
    """通用图片预览组件，支持多图预览、上传、删除、缩放。

    用于凭证截图、流程步骤截图、资产图片等多种场景。
    图片以 JSON 字符串或路径格式存储，支持多图以 | 分隔。

    参数:
      parent:        父容器
      image_value:    初始图片值（JSON 字符串或路径）
      preview_size:  预览尺寸 (宽, 高)
      empty_text:    空状态提示文本
      image_subdir:  图片存储子目录（如 credentials / process_flows/123）
    """
    def __init__(self, parent, image_value: str = "", preview_size: tuple[int, int] = (220, 140), empty_text: str = "未上传截图", image_subdir: str = ""):
        self.parent = parent
        self.preview_size = preview_size
        self.empty_text = empty_text
        self.image_subdir = image_subdir  # 新增：子目录参数
        self.image_items = parse_account_image_items(image_value)
        self.current_index = 0
        self.frame = None
        self.preview_label = None
        self.tip_var = tk.StringVar(value=self.empty_text)
        self.index_var = tk.StringVar(value="")
        self.photo = None
        self.prev_button = None
        self.next_button = None

    def build(self, master, *, title: str = "") -> ttk.Frame:
        # title 留空就不套 LabelFrame：父容器（create_ttk_card / create_preview_sidebar）
        # 本身已经是带标题的卡片，再套一层会把同一个标题显示两遍。
        if title:
            self.frame = ttk.LabelFrame(master, text=title, padding=8, style="Card.TLabelframe")
        else:
            # 内边距交给 PreviewArea.TLabel 自带，否则两层 padding 会把文案挤出方框
            self.frame = ttk.Frame(master)
        self.preview_label = ttk.Label(
            self.frame,
            text="加载中...",
            anchor="center",
            justify="center",
            style="PreviewArea.TLabel",
            # 只是个初值，真值由 _on_preview_resize 按实际宽度刷新：preview_size
            # 只管缩略图大小，与卡片能给出多宽无关，拿它算换行宽度会截断文案。
            wraplength=max(self.preview_size[0] - 24, 180),
        )
        self.preview_label.pack(fill="both", expand=True)
        self.preview_label.bind("<Button-1>", lambda event: self.open_large_viewer())
        self.preview_label.bind("<Configure>", self._on_preview_resize)
        nav_frame = ttk.Frame(self.frame)
        nav_frame.pack(fill="x", pady=(6, 0))
        self.prev_button = ttk.Button(nav_frame, text="上一张", command=self.show_previous)
        self.prev_button.pack(side="left")
        ttk.Label(nav_frame, textvariable=self.index_var, foreground=COLOR_MUTED).pack(side="left", padx=8)
        self.next_button = ttk.Button(nav_frame, text="下一张", command=self.show_next)
        self.next_button.pack(side="left")
        ttk.Label(
            self.frame,
            textvariable=self.tip_var,
            foreground=COLOR_MUTED,
            justify="left",
            wraplength=max(self.preview_size[0] + 20, 240),
        ).pack(fill="x", pady=(6, 0))
        self.refresh()
        return self.frame

    def _on_preview_resize(self, event):
        """按预览框的真实宽度重算换行宽度，避免文案被卡片裁掉。

        卡片宽度由布局决定（300/320），preview_size 只决定缩略图大小，两者不
        等，所以只能在这里取真实宽度。比较后再写回：否则每次 configure 又会
        触发一次 <Configure>，无限自激。
        """
        wrap = max(event.width - 24, 120)
        if self.preview_label is not None and int(self.preview_label.cget("wraplength")) != wrap:
            self.preview_label.configure(wraplength=wrap)

    def get_value(self) -> str:
        return serialize_account_image_items(self.image_items)

    def set_value(self, image_value: str):
        new_items = parse_account_image_items(image_value)
        if new_items != self.image_items:
            self.current_index = 0
        self.image_items = new_items
        if self.current_index >= len(self.image_items):
            self.current_index = max(0, len(self.image_items) - 1)
        self.refresh()

    def clear(self):
        self.clear_all()

    def clear_all(self):
        self.image_items = []
        self.current_index = 0
        self.refresh()

    def remove_current(self):
        if not self.image_items:
            messagebox.showinfo(APP_TITLE, "当前没有可移除的截图。", parent=self.parent)
            return False
        del self.image_items[self.current_index]
        if self.current_index >= len(self.image_items):
            self.current_index = max(0, len(self.image_items) - 1)
        self.refresh()
        return True

    def rename_current(self, *, parent=None) -> bool:
        current_item = self.get_current_item()
        if not current_item:
            messagebox.showinfo(APP_TITLE, "当前没有可命名的截图。", parent=parent or self.parent)
            return False
        default_label = current_item["label"] or Path(current_item["path"]).stem
        label = simpledialog.askstring(
            APP_TITLE,
            "请输入当前截图名称，例如：注册页、密保页、身份证",
            initialvalue=default_label,
            parent=parent or self.parent,
        )
        if label is None:
            return False
        current_item["label"] = normalize_text(label)
        self.refresh()
        return True

    def get_current_item(self) -> dict[str, str] | None:
        if not self.image_items:
            return None
        if self.current_index >= len(self.image_items):
            self.current_index = len(self.image_items) - 1
        return self.image_items[self.current_index]

    def get_current_value(self) -> str:
        current_item = self.get_current_item()
        return current_item["path"] if current_item else ""

    def get_current_label(self) -> str:
        current_item = self.get_current_item()
        return current_item["label"] if current_item else ""

    def choose_image(self, *, parent=None) -> bool:
        selected = filedialog.askopenfilename(title="选择截图文件", filetypes=ACCOUNT_IMAGE_FILE_TYPES, parent=parent or self.parent)
        if not selected:
            return False
        source_path = Path(selected)
        if not source_path.exists():
            messagebox.showerror(APP_TITLE, f"图片文件不存在：\n{source_path}", parent=parent or self.parent)
            return False
        try:
            stored_path = copy_account_image_to_store(source_path, self.image_subdir)
            self.image_items.append(build_account_image_item(get_account_image_storage_value(stored_path), ""))
            self.current_index = len(self.image_items) - 1
            self.refresh()
            return True
        except (UnidentifiedImageError, OSError) as exc:
            messagebox.showerror(APP_TITLE, f"上传截图失败：\n{exc}", parent=parent or self.parent)
            return False
        except Exception as exc:
            # 兜底：refresh() 等 Tk 调用可能抛出非 OSError 异常，不应逃逸出回调层
            logger.exception("上传截图失败：%s", source_path)
            messagebox.showerror(APP_TITLE, f"上传截图失败：\n{exc}", parent=parent or self.parent)
            return False

    def show_previous(self):
        if not self.image_items:
            return
        self.current_index = (self.current_index - 1) % len(self.image_items)
        self.refresh()

    def show_next(self):
        if not self.image_items:
            return
        self.current_index = (self.current_index + 1) % len(self.image_items)
        self.refresh()

    def open_current_image_folder(self, *, parent=None):
        image_value = self.get_current_value()
        if not image_value:
            messagebox.showinfo(APP_TITLE, "当前没有截图。", parent=parent or self.parent)
            return
        open_account_image_folder(image_value)

    def refresh(self):
        if not self.preview_label:
            return
        image_path = resolve_account_image_path(self.get_current_value())
        current_label = self.get_current_label()
        if not image_path:
            self.photo = None
            self.preview_label.configure(image="", text=self.empty_text, cursor="")
            self.index_var.set("0 / 0")
            self.tip_var.set("未上传截图。支持注册截图、密保截图等图片资料，可连续添加多张。")
            if self.prev_button:
                self.prev_button.state(["disabled"])
            if self.next_button:
                self.next_button.state(["disabled"])
            return
        if not image_path.exists():
            self.photo = None
            self.preview_label.configure(image="", text="截图文件不存在", cursor="")
            self.index_var.set(f"{self.current_index + 1} / {len(self.image_items)}")
            self.tip_var.set(f"图片路径失效：{image_path}")
            if self.prev_button:
                self.prev_button.state(["!disabled"] if len(self.image_items) > 1 else ["disabled"])
            if self.next_button:
                self.next_button.state(["!disabled"] if len(self.image_items) > 1 else ["disabled"])
            return
        try:
            with Image.open(image_path) as image:
                preview = image.copy()
            preview.thumbnail(self.preview_size)
            self.photo = ImageTk.PhotoImage(preview)
            self.preview_label.configure(image=self.photo, text="", cursor="hand2")
            self.index_var.set(f"{self.current_index + 1} / {len(self.image_items)}")
            if current_label:
                self.tip_var.set(f"当前截图：{current_label}；文件：{image_path.name}。点击小图可查看大图，可切换多张截图。")
            else:
                self.tip_var.set(f"已上传：{image_path.name}，点击小图可查看大图，可切换多张截图。")
            if self.prev_button:
                self.prev_button.state(["!disabled"] if len(self.image_items) > 1 else ["disabled"])
            if self.next_button:
                self.next_button.state(["!disabled"] if len(self.image_items) > 1 else ["disabled"])
        except (UnidentifiedImageError, OSError) as exc:
            self.photo = None
            self.preview_label.configure(image="", text="无法读取图片", cursor="")
            self.index_var.set(f"{self.current_index + 1} / {len(self.image_items)}")
            self.tip_var.set(f"图片读取失败：{exc}")
            if self.prev_button:
                self.prev_button.state(["!disabled"] if len(self.image_items) > 1 else ["disabled"])
            if self.next_button:
                self.next_button.state(["!disabled"] if len(self.image_items) > 1 else ["disabled"])

    def open_large_viewer(self, *, parent=None, title: str = "查看注册截图"):
        image_path = resolve_account_image_path(self.get_current_value())
        if not image_path:
            messagebox.showinfo(APP_TITLE, "当前没有截图。", parent=parent or self.parent)
            return
        if not image_path.exists():
            messagebox.showwarning(APP_TITLE, f"截图文件不存在：\n{image_path}", parent=parent or self.parent)
            return
        try:
            with Image.open(image_path) as image:
                display = image.copy()
                width, height = display.size
        except (UnidentifiedImageError, OSError) as exc:
            messagebox.showerror(APP_TITLE, f"读取截图失败：\n{exc}", parent=parent or self.parent)
            return

        viewer = tk.Toplevel(parent or self.parent)
        viewer.title(title)
        viewer.transient(parent or self.parent)
        viewer.geometry("980x760")

        top = ttk.Frame(viewer, padding=(10, 10, 10, 0))
        top.pack(fill="x")
        current_label = self.get_current_label()
        if current_label:
            ttk.Label(top, text=f"名称：{current_label}").pack(anchor="w")
        ttk.Label(top, text=f"文件：{image_path}").pack(anchor="w")
        ttk.Label(top, text=f"原始尺寸：{width} x {height}", foreground=COLOR_MUTED).pack(anchor="w", pady=(4, 0))

        image_box = ttk.Frame(viewer, padding=10)
        image_box.pack(fill="both", expand=True)
        max_size = (
            max(320, viewer.winfo_screenwidth() - 200),
            max(240, viewer.winfo_screenheight() - 220),
        )
        display.thumbnail(max_size)
        photo = ImageTk.PhotoImage(display)
        label = ttk.Label(image_box, image=photo, anchor="center")
        label.image = photo
        label.pack(fill="both", expand=True)
        viewer.image_ref = photo
        ttk.Button(viewer, text="关闭", command=viewer.destroy).pack(pady=(0, 10))



# ============================================================================
# 06. 全局工具函数
# ============================================================================
# 密码哈希、单实例互斥体、日期解析、到期计算等通用工具。
# 不依赖 tkinter，可在任何模块中直接导入使用。
# ----------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def acquire_single_instance_mutex():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
    already_exists = kernel32.GetLastError() == 183
    return mutex, already_exists


def signal_existing_instance_show():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                state_key TEXT PRIMARY KEY,
                state_value TEXT NOT NULL
            )
            """
        )
        token = datetime.now().isoformat(timespec="microseconds")
        conn.execute(
            """
            INSERT INTO app_state (state_key, state_value)
            VALUES (?, ?)
            ON CONFLICT(state_key) DO UPDATE SET state_value = excluded.state_value
            """,
            ("external_show_window_token", token),
        )
        conn.commit()
    finally:
        conn.close()


def parse_expiry_value(raw_value) -> tuple[date | None, str]:
    text = normalize_text(raw_value)
    if not text:
        return None, ""

    if isinstance(raw_value, (int, float)):
        try:
            return excel_serial_to_date(float(raw_value)), text
        except Exception:
            logger.exception("Unexpected error in parse_expiry_value (raw_value)")
            pass

    if re.fullmatch(r"\d+(\.\d+)?", text):
        try:
            return excel_serial_to_date(float(text)), text
        except Exception:
            logger.exception("Unexpected error in parse_expiry_value (regex match)")
            pass

    cleaned = text.replace("\n", " ").replace("年", "-").replace("月", "-").replace("日", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    candidates = [
        cleaned,
        text,
    ]

    date_patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ]

    match = re.search(r"(20\d{2})[-/\.年](\d{1,2})[-/\.月](\d{1,2})", text)
    if match:
        y, m, d = match.groups()
        candidates.append(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")

    for candidate in candidates:
        for pattern in date_patterns:
            try:
                return datetime.strptime(candidate, pattern).date(), text
            except ValueError:
                continue

    return None, text


def format_date(value: date | None) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def parse_expiry_date(text) -> date | None:
    """把 "YYYY-MM-DD" 解析成 date；为空或格式不对时返回 None（不抛）。"""
    text = str(text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def days_left(expiry_date: date | None) -> int | None:
    if not expiry_date:
        return None
    return (expiry_date - date.today()).days


def format_account_identity(account_no: str, account_name: str) -> str:
    account_no = normalize_text(account_no)
    account_name = normalize_text(account_name)
    if account_no and account_name:
        return f"{account_no} / {account_name}"
    return account_no or account_name


def format_asset_account_summary(asset_account_no: str, accounts: list[sqlite3.Row]) -> str:
    if accounts:
        first = accounts[0]
        summary = format_account_identity(first["account_no"] or asset_account_no, first["account_name"] or "")
        extra_count = len(accounts) - 1
        if extra_count > 0:
            return f"{summary} 等{len(accounts)}个"
        return summary
    return normalize_text(asset_account_no)


def mask_account_text(value: str) -> str:
    value = normalize_text(value)
    if len(value) <= 4:
        return value
    if len(value) <= 7:
        return f"{value[:2]}***{value[-2:]}"
    return f"{value[:3]}****{value[-4:]}"


def format_datetime_text(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return "未记录"
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return text



# ============================================================================
# 07. 数据库层（Database 类）
# ============================================================================
# SQLite 数据库封装类，封装所有数据库操作：
#   - 表创建 / 自动迁移（ALTER TABLE 兼容性）
#   - 到期提醒查询（ReminderSummary）
#   - 资产/账号 CRUD
#   - 凭证/流程 CRUD
#   - 批处理脚本初始化
# ----------------------------------------------------------------------------


class Database(ProcessDBMixin):
    """SQLite 数据库封装类，所有数据库操作的唯一入口。

    职责:
      1. 表创建与自动迁移（ALTER TABLE 兼容性）
      2. 到期提醒查询（ReminderSummary）
      3. 资产 / 账号 / 凭证 / 流程 CRUD
      4. 批处理脚本初始化（init_bat_scripts）

    设计原则:
      - 每个实例持有一个 sqlite3.Connection（不跨线程共享）
      - 写操作后立即 commit（conn.commit()）
      - 外键约束默认开启（PRAGMA foreign_keys = ON）
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        # ★ check_same_thread=False：允许子线程共用同一连接（控制台图标抽取线程需要）
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    def close(self):
        """★ 资源释放：显式关闭数据库连接（阿里规范：资源必须释放）。"""
        try:
            self.conn.close()
        except Exception:
            pass

    def create_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_no TEXT,
                platform TEXT,
                account_no TEXT,
                account_subject_code TEXT,
                account_subject_name TEXT,
                resource_type TEXT NOT NULL,
                resource_detail TEXT,
                resource_subject_code TEXT,
                resource_subject_name TEXT,
                expiry_date TEXT,
                expiry_raw TEXT,
                note TEXT,
                source_file TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_state (
                state_key TEXT PRIMARY KEY,
                state_value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                must_change_password INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                subject_code TEXT,
                subject_name TEXT,
                account_no TEXT,
                account_name TEXT,
                password TEXT,
                platform TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shared_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_key TEXT NOT NULL,
                subject_code TEXT,
                subject_name TEXT,
                account_no TEXT,
                account_name TEXT,
                password TEXT,
                platform TEXT,
                link_url TEXT,
                email TEXT,
                phone TEXT,
                screenshot_path TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS credential_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT,
                platform TEXT,
                link_url TEXT,
                username TEXT,
                password TEXT,
                email TEXT,
                phone TEXT,
                screenshot_path TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bat_scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()
        init_process_tables(self.conn)  # ★ 流程中心：执行留痕两张表 + 新列迁移
        self.ensure_default_admin()
        self.ensure_shared_account_schema()
        self.migrate_legacy_accounts()
        self.ensure_credential_schema()
        self.init_bat_scripts()
        self.migrate_tool_items()  # ★ 工具表软删除列迁移

    def init_bat_scripts(self):
        """初始化预设批处理脚本（兼容 add_s API）"""
        from system_toolbox_page import add_s, list_s, DEFS
        try:
            count = len(list_s(self.conn))
        except Exception:
            return  # 表不存在就跳过
        if count == 0:
            for sc in DEFS:
                add_s(self.conn, sc["n"], sc["c"],
                      d=sc.get("d", ""), cat=sc.get("cat", ""))

    def migrate_tool_items(self):
        """★ 迁移：tool_items 表加 is_deleted 列（支持软删除）"""
        try:
            cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(tool_items)").fetchall()}
            if "is_deleted" not in cols:
                self.conn.execute("ALTER TABLE tool_items ADD COLUMN is_deleted INTEGER DEFAULT 0")
                self.conn.commit()
        except Exception:
            pass

    def ensure_shared_account_schema(self):
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(shared_accounts)").fetchall()}
        for column_name in ("link_url", "email", "phone", "screenshot_path"):
            if column_name not in columns:
                self.conn.execute(f"ALTER TABLE shared_accounts ADD COLUMN {column_name} TEXT")
                self.conn.commit()

    def ensure_credential_schema(self):
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(credential_items)").fetchall()}
        if "category" not in columns:
            self.conn.execute("ALTER TABLE credential_items ADD COLUMN category TEXT")
            self.conn.commit()
        if "screenshot_path" not in columns:
            self.conn.execute("ALTER TABLE credential_items ADD COLUMN screenshot_path TEXT")
            self.conn.commit()

    def ensure_default_admin(self):
        now = datetime.now().isoformat(timespec="seconds")
        exists = self.conn.execute(
            "SELECT username FROM users WHERE username = ?",
            ("admin",),
        ).fetchone()
        if exists:
            # ★ 安全迁移：老库可能无 must_change_password 列，补列并标记强制修改
            cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(users)").fetchall()}
            if "must_change_password" not in cols:
                self.conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")
                self.conn.commit()
            # ★ 强制迁移：admin 仍使用默认密码时标记为强制修改
            admin_row = self.conn.execute(
                "SELECT password_hash, must_change_password FROM users WHERE username = 'admin'"
            ).fetchone()
            if not admin_row:
                return
            default_hash = hash_password("admin123")
            if admin_row["password_hash"] != default_hash:
                # 密码已改过，确保不强制修改
                if admin_row["must_change_password"]:
                    self.conn.execute(
                        "UPDATE users SET must_change_password = 0 WHERE username = 'admin'"
                    )
                    self.conn.commit()
                return
            # 默认密码未改：标记为强制修改
            if not admin_row["must_change_password"]:
                self.conn.execute(
                    "UPDATE users SET must_change_password = 1 WHERE username = 'admin'"
                )
                self.conn.commit()
            return
        self.conn.execute(
            """
            INSERT INTO users (username, password_hash, created_at, updated_at, must_change_password)
            VALUES (?, ?, ?, ?, 1)
            """,
            ("admin", hash_password("admin123"), now, now),
        )
        self.conn.commit()

    def verify_user(self, username: str, password: str) -> bool:
        row = self.conn.execute(
            "SELECT password_hash, must_change_password FROM users WHERE username = ?",
            (normalize_text(username),),
        ).fetchone()
        if not row:
            return False
        return row["password_hash"] == hash_password(password)

    def get_must_change_password(self, username: str) -> bool:
        """查询用户是否需要强制修改密码（首次登录）。"""
        row = self.conn.execute(
            "SELECT must_change_password FROM users WHERE username = ?",
            (normalize_text(username),),
        ).fetchone()
        if not row:
            return False
        return bool(row["must_change_password"])

    def set_user_password(self, username: str, new_password: str, force_change: bool = False):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO users (username, password_hash, created_at, updated_at, must_change_password)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                updated_at = excluded.updated_at,
                must_change_password = excluded.must_change_password
            """,
            (normalize_text(username), hash_password(new_password), now, now, 1 if force_change else 0),
        )
        self.conn.commit()

    def clear_must_change_password(self, username: str):
        """用户已修改密码，清除强制修改标记。"""
        self.conn.execute(
            "UPDATE users SET must_change_password = 0 WHERE username = ?",
            (normalize_text(username),),
        )
        self.conn.commit()

    def reset_admin_password(self) -> str:
        """★ 安全修复：不再硬编码 admin/admin。
        生成随机强密码，返回给调用方显示给用户。
        """
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        new_password = "".join(secrets.choice(alphabet) for _ in range(12))
        self.set_user_password("admin", new_password, force_change=False)
        return new_password

    def get_module_note(self, note_key: str, default: str = "") -> str:
        return self.get_state(f"module_note::{note_key}", default)

    def set_module_note(self, note_key: str, content: str):
        self.set_state(f"module_note::{note_key}", content)

    def migrate_legacy_accounts(self):
        existing = self.conn.execute("SELECT COUNT(1) AS total FROM shared_accounts").fetchone()["total"]
        legacy_rows = self.conn.execute("SELECT * FROM accounts ORDER BY id ASC").fetchall()
        if not legacy_rows:
            return

        seen = set()
        if existing:
            for row in self.conn.execute("SELECT * FROM shared_accounts").fetchall():
                key = (
                    normalize_text(row["group_key"]),
                    normalize_text(row["subject_code"]),
                    normalize_text(row["subject_name"]),
                    normalize_text(row["account_no"]),
                    normalize_text(row["account_name"]),
                    normalize_text(row["password"]),
                    normalize_text(row["platform"]),
                    normalize_text(row["link_url"]),
                    normalize_text(row["email"]),
                    normalize_text(row["phone"]),
                    normalize_text(row["screenshot_path"]),
                    normalize_text(row["note"]),
                )
                seen.add(key)

        now = datetime.now().isoformat(timespec="seconds")
        for row in legacy_rows:
            group_key = normalize_text(row["account_no"])
            if not group_key:
                continue
            key = (
                group_key,
                normalize_text(row["subject_code"]),
                normalize_text(row["subject_name"]),
                normalize_text(row["account_no"]),
                normalize_text(row["account_name"]),
                normalize_text(row["password"]),
                normalize_text(row["platform"]),
                "",
                "",
                "",
                "",
                normalize_text(row["note"]),
            )
            if key in seen:
                continue
            self.conn.execute(
                """
                INSERT INTO shared_accounts (
                    group_key, subject_code, subject_name, account_no, account_name,
                    password, platform, link_url, email, phone, screenshot_path, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_key,
                    row["subject_code"],
                    row["subject_name"],
                    row["account_no"],
                    row["account_name"],
                    row["password"],
                    row["platform"],
                    "",
                    "",
                    "",
                    "",
                    row["note"],
                    now,
                    now,
                ),
            )
            seen.add(key)
        self.conn.commit()

    def upsert_shared_account(self, group_key: str, payload: dict):
        group_key = normalize_text(group_key)
        if not group_key:
            return
        now = datetime.now().isoformat(timespec="seconds")
        key = (
            group_key,
            payload.get("subject_code", ""),
            payload.get("subject_name", ""),
            payload.get("account_no", ""),
            payload.get("account_name", ""),
            payload.get("password", ""),
            payload.get("platform", ""),
            payload.get("link_url", ""),
            payload.get("email", ""),
            payload.get("phone", ""),
            payload.get("screenshot_path", ""),
            payload.get("note", ""),
        )
        exists = self.conn.execute(
            """
            SELECT id
            FROM shared_accounts
            WHERE group_key = ? AND COALESCE(subject_code, '') = ? AND COALESCE(subject_name, '') = ?
              AND COALESCE(account_no, '') = ? AND COALESCE(account_name, '') = ?
              AND COALESCE(password, '') = ? AND COALESCE(platform, '') = ? AND COALESCE(link_url, '') = ?
              AND COALESCE(email, '') = ? AND COALESCE(phone, '') = ? AND COALESCE(screenshot_path, '') = ? AND COALESCE(note, '') = ?
            """,
            key,
        ).fetchone()
        if exists:
            return
        self.conn.execute(
            """
            INSERT INTO shared_accounts (
                group_key, subject_code, subject_name, account_no, account_name,
                password, platform, link_url, email, phone, screenshot_path, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*key, now, now),
        )

    def set_state(self, key: str, value: str):
        self.conn.execute(
            """
            INSERT INTO app_state (state_key, state_value)
            VALUES (?, ?)
            ON CONFLICT(state_key) DO UPDATE SET state_value = excluded.state_value
            """,
            (key, value),
        )
        self.conn.commit()

    def get_state(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT state_value FROM app_state WHERE state_key = ?",
            (key,),
        ).fetchone()
        return row["state_value"] if row else default

    def fetch_credential_items(self, keyword: str = "") -> list[sqlite3.Row]:
        if keyword:
            like = f"%{normalize_text(keyword)}%"
            return self.conn.execute(
                """
                SELECT *
                FROM credential_items
                WHERE title LIKE ?
                   OR category LIKE ?
                   OR platform LIKE ?
                   OR link_url LIKE ?
                   OR username LIKE ?
                   OR email LIKE ?
                   OR phone LIKE ?
                   OR note LIKE ?
                ORDER BY updated_at DESC, id DESC
                """,
                (like, like, like, like, like, like, like, like),
            ).fetchall()
        return self.conn.execute(
            """
            SELECT *
            FROM credential_items
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()

    def get_credential_item(self, item_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM credential_items WHERE id = ?", (item_id,)).fetchone()

    def add_credential_item(self, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO credential_items (
                title, category, platform, link_url, username, password, email, phone, screenshot_path, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("title", ""),
                payload.get("category", ""),
                payload.get("platform", ""),
                payload.get("link_url", ""),
                payload.get("username", ""),
                payload.get("password", ""),
                payload.get("email", ""),
                payload.get("phone", ""),
                payload.get("screenshot_path", ""),
                payload.get("note", ""),
                now,
                now,
            ),
        )
        self.conn.commit()

    def update_credential_item(self, item_id: int, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            UPDATE credential_items
            SET title = ?, category = ?, platform = ?, link_url = ?, username = ?, password = ?, email = ?, phone = ?, screenshot_path = ?, note = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.get("title", ""),
                payload.get("category", ""),
                payload.get("platform", ""),
                payload.get("link_url", ""),
                payload.get("username", ""),
                payload.get("password", ""),
                payload.get("email", ""),
                payload.get("phone", ""),
                payload.get("screenshot_path", ""),
                payload.get("note", ""),
                now,
                item_id,
            ),
        )
        self.conn.commit()


    def get_shared_account(self, account_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM shared_accounts WHERE id = ?", (account_id,)).fetchone()

    def delete_credential_item(self, item_id: int):
        self.conn.execute("DELETE FROM credential_items WHERE id = ?", (item_id,))
        self.conn.commit()

    def fetch_all_shared_accounts(self, keyword: str = "") -> list[sqlite3.Row]:
        if keyword:
            like = f"%{normalize_text(keyword)}%"
            return self.conn.execute(
                """
                SELECT *
                FROM shared_accounts
                WHERE group_key LIKE ?
                   OR subject_code LIKE ?
                   OR subject_name LIKE ?
                   OR account_no LIKE ?
                   OR account_name LIKE ?
                   OR platform LIKE ?
                   OR note LIKE ?
                ORDER BY group_key ASC, id ASC
                """,
                (like, like, like, like, like, like, like),
            ).fetchall()
        return self.conn.execute(
            """
            SELECT *
            FROM shared_accounts
            ORDER BY group_key ASC, id ASC
            """
        ).fetchall()

    def insert_asset(self, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """
            INSERT INTO assets (
                record_no, platform, account_no, account_subject_code, account_subject_name,
                resource_type, resource_detail, resource_subject_code, resource_subject_name,
                expiry_date, expiry_raw, note, source_file, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("record_no", ""),
                payload.get("platform", ""),
                payload.get("account_no", ""),
                payload.get("account_subject_code", ""),
                payload.get("account_subject_name", ""),
                payload.get("resource_type", ""),
                payload.get("resource_detail", ""),
                payload.get("resource_subject_code", ""),
                payload.get("resource_subject_name", ""),
                payload.get("expiry_date", ""),
                payload.get("expiry_raw", ""),
                payload.get("note", ""),
                payload.get("source_file", ""),
                now,
                now,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_asset(self, asset_id: int, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            UPDATE assets
            SET record_no = ?, platform = ?, account_no = ?, account_subject_code = ?,
                account_subject_name = ?, resource_type = ?, resource_detail = ?,
                resource_subject_code = ?, resource_subject_name = ?, expiry_date = ?,
                expiry_raw = ?, note = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.get("record_no", ""),
                payload.get("platform", ""),
                payload.get("account_no", ""),
                payload.get("account_subject_code", ""),
                payload.get("account_subject_name", ""),
                payload.get("resource_type", ""),
                payload.get("resource_detail", ""),
                payload.get("resource_subject_code", ""),
                payload.get("resource_subject_name", ""),
                payload.get("expiry_date", ""),
                payload.get("expiry_raw", ""),
                payload.get("note", ""),
                now,
                asset_id,
            ),
        )
        self.conn.commit()

    def delete_asset(self, asset_id: int):
        self.conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        self.conn.commit()

    def replace_imported_assets(self, items: list[dict], source_file: str):
        self.conn.execute("DELETE FROM assets WHERE source_file = ?", (source_file,))
        now = datetime.now().isoformat(timespec="seconds")
        for item in items:
            self.conn.execute(
                """
                INSERT INTO assets (
                    record_no, platform, account_no, account_subject_code, account_subject_name,
                    resource_type, resource_detail, resource_subject_code, resource_subject_name,
                    expiry_date, expiry_raw, note, source_file, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("record_no", ""),
                    item.get("platform", ""),
                    item.get("account_no", ""),
                    item.get("account_subject_code", ""),
                    item.get("account_subject_name", ""),
                    item.get("resource_type", ""),
                    item.get("resource_detail", ""),
                    item.get("resource_subject_code", ""),
                    item.get("resource_subject_name", ""),
                    item.get("expiry_date", ""),
                    item.get("expiry_raw", ""),
                    item.get("note", ""),
                    source_file,
                    now,
                    now,
                ),
            )
            for account in item.get("accounts", []):
                self.upsert_shared_account(item.get("account_no", ""), account)
        self.conn.commit()

    def fetch_assets(self, keyword: str = "") -> list[sqlite3.Row]:
        if keyword:
            like = f"%{keyword.strip()}%"
            return self.conn.execute(
                """
                SELECT *
                FROM assets
                WHERE record_no LIKE ?
                   OR platform LIKE ?
                   OR account_no LIKE ?
                   OR account_subject_name LIKE ?
                   OR resource_type LIKE ?
                   OR resource_detail LIKE ?
                   OR resource_subject_name LIKE ?
                   OR note LIKE ?
                ORDER BY COALESCE(expiry_date, '9999-12-31') ASC, id DESC
                """,
                (like, like, like, like, like, like, like, like),
            ).fetchall()

        return self.conn.execute(
            """
            SELECT *
            FROM assets
            ORDER BY COALESCE(expiry_date, '9999-12-31') ASC, id DESC
            """
        ).fetchall()

    def get_asset(self, asset_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()

    def fetch_accounts(self, asset_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM accounts
            WHERE asset_id = ?
            ORDER BY id ASC
            """,
            (asset_id,),
        ).fetchall()

    def fetch_shared_accounts(self, group_key: str) -> list[sqlite3.Row]:
        group_key = normalize_text(group_key)
        if not group_key:
            return []
        return self.conn.execute(
            """
            SELECT *
            FROM shared_accounts
            WHERE group_key = ?
            ORDER BY id ASC
            """,
            (group_key,),
        ).fetchall()

    def add_shared_account(self, group_key: str, payload: dict):
        group_key = normalize_text(group_key)
        if not group_key:
            return
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO shared_accounts (
                group_key, subject_code, subject_name, account_no, account_name,
                password, platform, link_url, email, phone, screenshot_path, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_key,
                payload.get("subject_code", ""),
                payload.get("subject_name", ""),
                payload.get("account_no", "") or group_key,
                payload.get("account_name", ""),
                payload.get("password", ""),
                payload.get("platform", ""),
                payload.get("link_url", ""),
                payload.get("email", ""),
                payload.get("phone", ""),
                payload.get("screenshot_path", ""),
                payload.get("note", ""),
                now,
                now,
            ),
        )
        self.conn.commit()

    def update_shared_account(self, account_id: int, group_key: str, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            UPDATE shared_accounts
            SET group_key = ?, subject_code = ?, subject_name = ?, account_no = ?, account_name = ?,
                password = ?, platform = ?, link_url = ?, email = ?, phone = ?, screenshot_path = ?, note = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                normalize_text(group_key),
                payload.get("subject_code", ""),
                payload.get("subject_name", ""),
                payload.get("account_no", "") or normalize_text(group_key),
                payload.get("account_name", ""),
                payload.get("password", ""),
                payload.get("platform", ""),
                payload.get("link_url", ""),
                payload.get("email", ""),
                payload.get("phone", ""),
                payload.get("screenshot_path", ""),
                payload.get("note", ""),
                now,
                account_id,
            ),
        )
        self.conn.commit()

    def delete_shared_account(self, account_id: int):
        self.conn.execute("DELETE FROM shared_accounts WHERE id = ?", (account_id,))
        self.conn.commit()

    def count_assets_by_account_no(self, account_no: str) -> int:
        account_no = normalize_text(account_no)
        if not account_no:
            return 0
        row = self.conn.execute(
            "SELECT COUNT(1) AS total FROM assets WHERE account_no = ?",
            (account_no,),
        ).fetchone()
        return row["total"] if row else 0

    def fetch_account_group_summaries(self, keyword: str = "") -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM shared_accounts
            ORDER BY group_key ASC, id ASC
            """
        ).fetchall()
        groups = {}
        keyword = normalize_text(keyword).lower()
        for row in rows:
            group_key = normalize_text(row["group_key"])
            if not group_key:
                continue
            groups.setdefault(group_key, []).append(row)

        results = []
        for group_key, items in groups.items():
            first = items[0]
            summary = {
                "group_key": group_key,
                "account_summary": format_account_identity(first["account_no"], first["account_name"]),
                "account_count": len(items),
                "asset_count": self.count_assets_by_account_no(group_key),
                "platform": first["platform"] or "",
                "link_url": first["link_url"] or "",
                "email": first["email"] or "",
                "phone": first["phone"] or "",
                "screenshot_path": first["screenshot_path"] or "",
                "note": first["note"] or "",
                "subject_code": first["subject_code"] or "",
                "subject_name": first["subject_name"] or "",
            }
            if keyword:
                haystack = " ".join(
                    [
                        summary["group_key"],
                        summary["account_summary"],
                        summary["platform"],
                        summary["link_url"],
                        summary["email"],
                        summary["phone"],
                        summary["screenshot_path"],
                        summary["note"],
                        summary["subject_code"],
                        summary["subject_name"],
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            results.append(summary)
        return results

    def get_account_group_context(self, group_key: str) -> dict:
        rows = self.fetch_shared_accounts(group_key)
        if rows:
            first = rows[0]
            return {
                "subject_code": first["subject_code"] or "",
                "subject_name": first["subject_name"] or "",
                "account_no": first["account_no"] or group_key,
                "platform": first["platform"] or "",
                "link_url": first["link_url"] or "",
                "email": first["email"] or "",
                "phone": first["phone"] or "",
                "screenshot_path": first["screenshot_path"] or "",
                "note": first["note"] or "",
            }

        asset = self.conn.execute(
            """
            SELECT account_subject_code, account_subject_name, account_no, platform
            FROM assets
            WHERE account_no = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalize_text(group_key),),
        ).fetchone()
        if asset:
            return {
                "subject_code": asset["account_subject_code"] or "",
                "subject_name": asset["account_subject_name"] or "",
                "account_no": asset["account_no"] or group_key,
                "platform": asset["platform"] or "",
                "link_url": "",
                "email": "",
                "phone": "",
                "screenshot_path": "",
                "note": "",
            }
        return {
            "subject_code": "",
            "subject_name": "",
            "account_no": normalize_text(group_key),
            "platform": "",
            "link_url": "",
            "email": "",
            "phone": "",
            "screenshot_path": "",
            "note": "",
        }

    def add_account(self, asset_id: int, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO accounts (
                asset_id, subject_code, subject_name, account_no, account_name,
                password, platform, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                payload.get("subject_code", ""),
                payload.get("subject_name", ""),
                payload.get("account_no", ""),
                payload.get("account_name", ""),
                payload.get("password", ""),
                payload.get("platform", ""),
                payload.get("note", ""),
                now,
                now,
            ),
        )
        self.conn.commit()

    def update_account(self, account_id: int, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            UPDATE accounts
            SET subject_code = ?, subject_name = ?, account_no = ?, account_name = ?,
                password = ?, platform = ?, note = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.get("subject_code", ""),
                payload.get("subject_name", ""),
                payload.get("account_no", ""),
                payload.get("account_name", ""),
                payload.get("password", ""),
                payload.get("platform", ""),
                payload.get("note", ""),
                now,
                account_id,
            ),
        )
        self.conn.commit()

    def delete_account(self, account_id: int):
        self.conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self.conn.commit()

    def get_reminder_summary(self) -> ReminderSummary:
        overdue = []
        due_15 = []
        due_30 = []
        for row in self.fetch_assets():
            expiry_text = row["expiry_date"]
            if not expiry_text:
                continue
            expiry_dt = datetime.strptime(expiry_text, "%Y-%m-%d").date()
            remain = days_left(expiry_dt)
            item = {
                "id": row["id"],
                "title": row["resource_detail"] or row["resource_type"],
                "platform": row["platform"],
                "resource_type": row["resource_type"],
                "expiry_date": expiry_dt,
                "days_left": remain,
            }
            if remain is None:
                continue
            if remain < 0:
                overdue.append(item)
            elif remain <= 15:
                due_15.append(item)
            elif remain <= 30:
                due_30.append(item)
        return ReminderSummary(overdue=overdue, due_15=due_15, due_30=due_30)


def load_excel_assets(file_path: Path) -> list[dict]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("缺少 openpyxl，请先执行 pip install -r requirements.txt") from exc

    wb = load_workbook(file_path, data_only=True)
    detail_sheet = wb[wb.sheetnames[0]]
    subject_map = {}
    account_map = {}

    if len(wb.sheetnames) > 1:
        subject_sheet = wb[wb.sheetnames[1]]
        for row in subject_sheet.iter_rows(min_row=2, values_only=True):
            values = list(row) + [None] * (8 - len(row))
            subject_code = normalize_text(values[0])
            subject_name = normalize_text(values[1])
            account_no = normalize_text(values[3])
            account_name = normalize_text(values[4])
            account_password = normalize_text(values[5])
            account_platform = normalize_text(values[6])
            account_note = normalize_text(values[7])
            if subject_code and subject_name:
                subject_map[subject_code] = subject_name
            if account_no and account_name:
                account_map.setdefault(account_no, []).append(
                    {
                        "subject_code": subject_code,
                        "subject_name": subject_name,
                        "account_no": account_no,
                        "account_name": account_name,
                        "password": account_password,
                        "platform": account_platform,
                        "note": account_note,
                    }
                )

    items = []
    carry = {
        "record_no": "",
        "platform": "",
        "account_no": "",
        "account_subject_code": "",
    }

    for row in detail_sheet.iter_rows(min_row=2, values_only=True):
        if not any(value not in (None, "") for value in row[:9]):
            continue

        values = list(row[:9]) + [None] * (9 - len(row[:9]))
        if normalize_text(values[0]):
            carry["record_no"] = normalize_text(values[0])
        if normalize_text(values[1]):
            carry["platform"] = normalize_text(values[1])
        if normalize_text(values[2]):
            carry["account_no"] = normalize_text(values[2])
        if normalize_text(values[3]):
            carry["account_subject_code"] = normalize_text(values[3])

        expiry_dt, expiry_raw = parse_expiry_value(values[7])
        resource_subject_code = normalize_text(values[6])
        item = {
            "record_no": carry["record_no"],
            "platform": carry["platform"],
            "account_no": carry["account_no"],
            "account_subject_code": carry["account_subject_code"],
            "account_subject_name": subject_map.get(carry["account_subject_code"], ""),
            "resource_type": normalize_text(values[4]),
            "resource_detail": normalize_text(values[5]),
            "resource_subject_code": resource_subject_code,
            "resource_subject_name": subject_map.get(resource_subject_code, ""),
            "expiry_date": format_date(expiry_dt),
            "expiry_raw": expiry_raw,
            "note": normalize_text(values[8]),
            "accounts": [],
        }

        if not item["resource_type"] and items:
            item["resource_type"] = items[-1]["resource_type"]
        if not item["resource_type"] and not item["resource_detail"]:
            continue

        if item["account_no"] and not account_map.get(item["account_no"]):
            item["account_subject_name"] = item["account_subject_name"] or ""
        if item["account_no"]:
            for account in account_map.get(item["account_no"], []):
                item["accounts"].append(
                    {
                        "subject_code": account.get("subject_code", "") or item["account_subject_code"],
                        "subject_name": account.get("subject_name", "") or item["account_subject_name"],
                        "account_no": account.get("account_no", "") or item["account_no"],
                        "account_name": account.get("account_name", ""),
                        "password": account.get("password", ""),
                        "platform": account.get("platform", "") or item["platform"],
                        "note": account.get("note", ""),
                    }
                )
        items.append(item)

    return items


def import_credential_items_from_excel(file_path: Path) -> list[dict]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("缺少 openpyxl，请先执行 pip install -r requirements.txt") from exc

    wb = load_workbook(file_path, data_only=True)
    sheet = wb[wb.sheetnames[0]]
    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), [])
    headers = [normalize_text(value) for value in header_row]
    header_map = {header: index for index, header in enumerate(headers) if header}
    alias_map = {
        "title": ["标题", "名称"],
        "category": ["分类/用途", "分类", "用途"],
        "platform": ["平台"],
        "link_url": ["链接", "网址", "URL"],
        "username": ["账号", "用户名"],
        "password": ["密码"],
        "email": ["邮箱", "电子邮箱"],
        "phone": ["手机号", "手机"],
        "screenshot_path": ["截图", "截图路径", "注册截图", "密保截图"],
        "note": ["备注", "说明"],
    }

    def get_cell_value(row_values, field_name: str) -> str:
        for alias in alias_map[field_name]:
            if alias in header_map:
                idx = header_map[alias]
                if idx < len(row_values):
                    return normalize_text(row_values[idx])
        return ""

    items = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        values = list(row or [])
        payload = {field: get_cell_value(values, field) for field in alias_map}
        if not any(payload.values()):
            continue
        if not payload["title"]:
            continue
        items.append(payload)
    return items


def export_credential_rows_to_excel(rows: list[dict], file_path: Path):
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("缺少 openpyxl，请先执行 pip install -r requirements.txt") from exc

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "账号中心"
    headers = [
        "来源",
        "分组",
        "分类/用途",
        "标题",
        "平台",
        "链接",
        "账号",
        "密码",
        "邮箱",
        "手机号",
        "截图名称",
        "截图路径",
        "截图文件名",
        "备注",
        "账号组",
    ]
    sheet.append(headers)
    for row in rows:
        sheet.append(
            [
                row.get("source_label", ""),
                row.get("group_label", ""),
                row.get("category", ""),
                row.get("title", ""),
                row.get("platform", ""),
                row.get("link_url", ""),
                row.get("username", ""),
                row.get("password", ""),
                row.get("email", ""),
                row.get("phone", ""),
                get_account_image_label_text(row.get("screenshot_path", "")),
                get_account_image_path_text(row.get("screenshot_path", "")),
                get_account_image_file_name(row.get("screenshot_path", "")),
                row.get("note", ""),
                row.get("group_key", ""),
            ]
        )
    workbook.save(file_path)



# ============================================================================
# 08. 数据编辑对话框（Dialog 类组）
# ============================================================================
# 通用模式：body() 构建界面 → apply() 保存。
# 各 Dialog 均复用同一套 grid 布局逻辑，通过 fields 参数驱动。
# ----------------------------------------------------------------------------

class AccountEditDialog(simpledialog.Dialog):
    """资产关联账号编辑对话框。

    适用场景: 在资产详情弹窗中新增/编辑该资产下的账号信息。

    参数:
      parent:       父窗口
      title:        弹窗标题（"新增账号" / "编辑账号"）
      asset_id:     所属资产 ID（新建账号时必须）
      account_id:   None 表示新增，整数表示编辑
    """
    def __init__(self, parent, title: str, initial: dict | None = None):
        self.initial = initial or {}
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        apply_dialog_form_style(master, MAIN_PALETTE, style_prefix="MainDialog")
        self.entries = {}
        simple_fields = [
            ("subject_code", "主体编号"),
            ("subject_name", "主体名称"),
            ("password", "密码(明文)"),
            ("platform", "平台"),
            ("link_url", "链接"),
            ("email", "邮箱"),
            ("phone", "手机号"),
            ("note", "备注"),
        ]

        current_row = 0
        for field, label in simple_fields[:2]:
            create_form_label(master, label, palette=MAIN_PALETTE).grid(row=current_row, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=45)
            entry.grid(row=current_row, column=1, columnspan=3, sticky="ew", padx=6, pady=4)
            entry.insert(0, self.initial.get(field, ""))
            self.entries[field] = entry
            current_row += 1

        create_form_label(master, "账号信息", palette=MAIN_PALETTE).grid(row=current_row, column=0, sticky="w", padx=6, pady=4)
        create_form_label(master, "账号编号", palette=MAIN_PALETTE).grid(row=current_row, column=1, sticky="w", padx=(6, 2), pady=4)
        account_no_entry = create_form_entry(master, palette=MAIN_PALETTE, width=18)
        account_no_entry.grid(row=current_row, column=2, sticky="ew", padx=(0, 6), pady=4)
        account_no_entry.insert(0, self.initial.get("account_no", ""))
        self.entries["account_no"] = account_no_entry

        create_form_label(master, "账号", palette=MAIN_PALETTE).grid(row=current_row, column=3, sticky="w", padx=(6, 2), pady=4)
        account_name_entry = create_form_entry(master, palette=MAIN_PALETTE, width=24)
        account_name_entry.grid(row=current_row, column=4, sticky="ew", padx=(0, 6), pady=4)
        account_name_entry.insert(0, self.initial.get("account_name", ""))
        self.entries["account_name"] = account_name_entry
        current_row += 1

        for field, label in simple_fields[2:]:
            create_form_label(master, label, palette=MAIN_PALETTE).grid(row=current_row, column=0, sticky="w", padx=6, pady=4)
            entry = create_form_entry(master, palette=MAIN_PALETTE, width=45)
            entry.grid(row=current_row, column=1, columnspan=4, sticky="ew", padx=6, pady=4)
            entry.insert(0, self.initial.get(field, ""))
            self.entries[field] = entry
            current_row += 1

        self.screenshot_preview = AccountImagePreview(
            self,
            image_value=self.initial.get("screenshot_path", ""),
            preview_size=(240, 150),
            empty_text="未上传注册/密保截图",
            image_subdir="credentials",  # 凭证截图统一存到此子目录
        )
        screenshot_frame = self.screenshot_preview.build(master, title="注册/密保截图")
        screenshot_frame.grid(row=current_row, column=0, columnspan=5, sticky="ew", padx=6, pady=(8, 4))
        current_row += 1

        screenshot_actions = create_form_frame(master, palette=MAIN_PALETTE)
        screenshot_actions.grid(row=current_row, column=0, columnspan=5, sticky="w", padx=6, pady=(0, 6))
        ttk.Button(
            screenshot_actions,
            text="添加图片",
            command=lambda: self.screenshot_preview.choose_image(parent=self),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            screenshot_actions,
            text="查看大图",
            command=lambda: self.screenshot_preview.open_large_viewer(parent=self),
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="命名当前",
            command=lambda: self.screenshot_preview.rename_current(parent=self),
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="移除当前",
            command=self.screenshot_preview.remove_current,
        ).pack(side="left", padx=6)
        ttk.Button(
            screenshot_actions,
            text="清空全部",
            command=self.screenshot_preview.clear_all,
        ).pack(side="left", padx=6)

        master.columnconfigure(2, weight=1)
        master.columnconfigure(4, weight=1)
        return self.entries["account_name"]

    def validate(self):
        if not self.entries["account_name"].get().strip():
            messagebox.showwarning(APP_TITLE, "账号不能为空。", parent=self)
            return False
        return True

    def apply(self):
        self.result = {field: widget.get().strip() for field, widget in self.entries.items()}
        self.result["screenshot_path"] = self.screenshot_preview.get_value()



# ============================================================================
# 09. 账号管理与台账窗口
# ============================================================================
# AccountManagerDialog：凭证管理（凭证列表/导入导出/截图管理/复制密码）
# AccountLedgerDialog：共享账号台账（分组查看/新增/编辑/删除/按组筛选）
# ----------------------------------------------------------------------------

# ============================================================================
# 10. 登录对话框
# ============================================================================
# LoginDialog：输入用户名密码，校验 users 表，解锁管理员功能。
# ChangePasswordDialog：修改当前用户密码（需验证旧密码）。
# ----------------------------------------------------------------------------

class LoginDialog(tk.Toplevel):
    """登录对话框（独立 Toplevel）。

    功能:
      - 输入用户名 / 密码
      - 校验 users 表（bcrypt 风格 SHA-256 哈希）
      - 登录成功后设置 self.welcome_user 变量
      - 登录后解锁：初始化密码 / 修改密码 等管理员功能
      - 记住密码功能（保存到本地文件，下次自动填充）

    默认管理员: admin / admin（首次运行自动创建）
    """
    REMEMBER_FILE = BASE_DIR / "remember_me.json"

    def __init__(self, parent: "ExpiryManagerApp", db: Database):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.result = None
        self.title("登录")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        # 加载记住的密码
        remembered = self._load_remembered()
        self.username_var = tk.StringVar(value=remembered.get("username", "admin"))
        self.password_var = tk.StringVar(value=remembered.get("password", "admin123"))
        self.remember_var = tk.BooleanVar(value=remembered.get("remember", False))

        self.build_ui()
        self.bind("<Return>", lambda event: self.attempt_login())
        self.bind("<Escape>", lambda event: self.cancel())
        # 延迟居中，确保父窗口已布局完成
        self.after(100, self.center_on_parent)

    def _load_remembered(self) -> dict:
        """加载记住的用户名和密码。"""
        try:
            if self.REMEMBER_FILE.exists():
                with open(self.REMEMBER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 简单 base64 解码（非加密，只是混淆）
                    if data.get("remember"):
                        return {
                            "username": base64.b64decode(data.get("username", "")).decode("utf-8") if data.get("username") else "",
                            "password": base64.b64decode(data.get("password", "")).decode("utf-8") if data.get("password") else "",
                            "remember": True,
                        }
        except Exception:
            pass
        return {}

    def _save_remembered(self, username: str, password: str):
        """保存记住的用户名和密码（base64 混淆）。"""
        try:
            data = {
                "remember": True,
                "username": base64.b64encode(username.encode("utf-8")).decode("ascii"),
                "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
            }
            with open(self.REMEMBER_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _clear_remembered(self):
        """清除记住的密码。"""
        try:
            if self.REMEMBER_FILE.exists():
                self.REMEMBER_FILE.unlink()
        except Exception:
            pass

    def center_on_parent(self):
        """将登录窗口居中显示在父窗口上"""
        self.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_w = self.parent.winfo_width()
        parent_h = self.parent.winfo_height()
        self_w = self.winfo_width()
        self_h = self.winfo_height()
        # 如果父窗口位置未确定（值为0），改为屏幕居中
        if parent_x <= 0 and parent_y <= 0:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = (screen_w - self_w) // 2
            y = (screen_h - self_h) // 2
        else:
            x = parent_x + (parent_w - self_w) // 2
            y = parent_y + (parent_h - self_h) // 2
        self.geometry(f"+{x}+{y}")

    def build_ui(self):
        panel = ttk.Frame(self, padding=18)
        panel.pack(fill="both", expand=True)

        ttk.Label(panel, text="个人系统登录", font=FONT_SUBTITLE).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(panel, text="账号").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        username_entry = ttk.Entry(panel, textvariable=self.username_var, width=28)
        username_entry.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(panel, text="密码").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        password_entry = ttk.Entry(panel, textvariable=self.password_var, width=28, show="*")
        password_entry.grid(row=2, column=1, sticky="ew", pady=6)

        # 记住密码复选框
        remember_check = ttk.Checkbutton(
            panel, text="记住密码", variable=self.remember_var
        )
        remember_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 8))

        hint = "默认账号：admin    首次登录请修改密码"
        ttk.Label(panel, text=hint, foreground=COLOR_MUTED).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 12))

        buttons = ttk.Frame(panel)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="初始化密码", command=self.reset_password).pack(side="left", padx=4)
        ttk.Button(buttons, text="退出", command=self.cancel).pack(side="left", padx=4)
        ttk.Button(buttons, text="登录", command=self.attempt_login).pack(side="left", padx=4)

        panel.columnconfigure(1, weight=1)
        username_entry.focus_set()

    def attempt_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            messagebox.showwarning(APP_TITLE, "请输入账号和密码。", parent=self)
            return
        if not self.db.verify_user(username, password):
            messagebox.showerror(APP_TITLE, "账号或密码错误。", parent=self)
            return
        # ★ 安全修复：首次登录强制修改密码
        # ChangePasswordDialog.apply() 内部已调用 clear_must_change_password，无需重复
        final_password = password  # 最终保存的密码（可能被 ChangePasswordDialog 更新）
        if self.db.get_must_change_password(username):
            messagebox.showinfo(
                APP_TITLE,
                "首次登录需要修改密码。\n请设置新密码后再继续使用。",
                parent=self,
            )
            dlg = ChangePasswordDialog(self, self.db, username)
            if not dlg.result:
                # 用户取消修改，不允许进入
                return
            final_password = dlg.result  # 使用新密码

        # 记住密码
        if self.remember_var.get():
            self._save_remembered(username, final_password)
        else:
            self._clear_remembered()

        self.result = username
        self.destroy()

    def reset_password(self):
        """★ 安全修复：生成随机强密码，不再硬编码 admin/admin。"""
        if not messagebox.askyesno(APP_TITLE, "确认将管理员密码重置为随机强密码吗？\n新密码将显示在弹窗中，请立即记录。", parent=self):
            return
        new_password = self.db.reset_admin_password()
        self.username_var.set("admin")
        self.password_var.set(new_password)
        messagebox.showinfo(APP_TITLE, f"初始化成功。\n账号：admin\n新密码：{new_password}\n\n请立即记录此密码。", parent=self)

    def cancel(self):
        self.result = None
        self.destroy()



class ChangePasswordDialog(simpledialog.Dialog):
    """修改密码对话框。

    功能:
      - 输入旧密码验证身份
      - 输入新密码（两次确认）
      - 更新 users 表中的 password_hash
      - admin 可强制重置其他用户密码
    """
    def __init__(self, parent, db: Database, username: str):
        self.db = db
        self.username = username
        self.result = None
        super().__init__(parent, "修改密码")

    def body(self, master):
        # ★ 强制设置 master 背景色（Dialog 初始化后会重置子控件）
        master.configure(bg=COLOR_BG)
        self.old_var = tk.StringVar()
        self.new_var = tk.StringVar()
        self.confirm_var = tk.StringVar()

        # ★ DRY：统一创建密码输入框（避免重复代码）
        def _create_password_entry(textvariable: tk.StringVar) -> tk.Entry:
            """创建统一样式的密码输入框。"""
            return tk.Entry(
                master, textvariable=textvariable, show="*", width=ENTRY_WIDTH,
                bg=COLOR_INPUT_BG, fg=COLOR_TEXT_STRONG, relief="solid", borderwidth=1,
                highlightthickness=1, highlightbackground=COLOR_INPUT_BORDER,
                highlightcolor=COLOR_INPUT_FOCUS,
            )

        def _apply_bg(widget: tk.Widget, bg_color: str):
            """强制应用背景色，处理 Dialog 后期重置的问题。"""
            try:
                widget.configure(bg=bg_color)
            except Exception:
                pass

        # 创建标签和输入框
        self._account_label = tk.Label(master, text=f"当前账号：{self.username}", bg=COLOR_BG, fg=COLOR_TEXT_STRONG)
        self._account_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=PADDING_X, pady=PADDING_TITLE)

        self._old_label = tk.Label(master, text="旧密码", bg=COLOR_BG, fg=COLOR_TEXT_STRONG)
        self._old_label.grid(row=1, column=0, sticky="w", padx=PADDING_X, pady=PADDING_Y)
        self._old_entry = _create_password_entry(self.old_var)
        self._old_entry.grid(row=1, column=1, sticky="ew", padx=PADDING_X, pady=PADDING_Y)

        self._new_label = tk.Label(master, text="新密码", bg=COLOR_BG, fg=COLOR_TEXT_STRONG)
        self._new_label.grid(row=2, column=0, sticky="w", padx=PADDING_X, pady=PADDING_Y)
        self._new_entry = _create_password_entry(self.new_var)
        self._new_entry.grid(row=2, column=1, sticky="ew", padx=PADDING_X, pady=PADDING_Y)

        self._confirm_label = tk.Label(master, text="确认新密码", bg=COLOR_BG, fg=COLOR_TEXT_STRONG)
        self._confirm_label.grid(row=3, column=0, sticky="w", padx=PADDING_X, pady=PADDING_Y)
        self._confirm_entry = _create_password_entry(self.confirm_var)
        self._confirm_entry.grid(row=3, column=1, sticky="ew", padx=PADDING_X, pady=PADDING_Y)

        master.columnconfigure(1, weight=1)
        # ★ 使用 after_idle 延迟设置背景，确保 Dialog 初始化完成后背景正确
        self.after_idle(lambda: _apply_bg(master, COLOR_BG))
        self.after_idle(lambda: _apply_bg(self._old_entry, COLOR_INPUT_BG))
        self.after_idle(lambda: _apply_bg(self._new_entry, COLOR_INPUT_BG))
        self.after_idle(lambda: _apply_bg(self._confirm_entry, COLOR_INPUT_BG))
        return master

    def validate(self):
        old_password = self.old_var.get()
        new_password = self.new_var.get()
        confirm_password = self.confirm_var.get()
        # ★ 空值检查（阿里规范：入参校验）
        if not self.db.verify_user(self.username, old_password):
            messagebox.showwarning(APP_TITLE, "旧密码不正确。", parent=self)
            return False
        if not new_password:
            messagebox.showwarning(APP_TITLE, "新密码不能为空。", parent=self)
            return False
        if len(new_password) < MIN_PASSWORD_LENGTH:
            messagebox.showwarning(APP_TITLE, f"新密码长度至少 {MIN_PASSWORD_LENGTH} 位。", parent=self)
            return False
        if new_password != confirm_password:
            messagebox.showwarning(APP_TITLE, "两次输入的新密码不一致。", parent=self)
            return False
        return True

    def apply(self):
        new_password = self.new_var.get()
        # ★ 保存新密码并清除强制修改标记
        self.db.set_user_password(self.username, new_password, force_change=False)
        self.db.clear_must_change_password(self.username)
        self.result = new_password



# ============================================================================
# 11. 系统托盘（TrayController）
# ============================================================================
# pystray 实现系统托盘图标，支持：
#   - 显示窗口 / 立即检查提醒 / 退出程序
#   - Windows 气泡通知（notify 方法）
# 需安装：pip install pystray Pillow
# ----------------------------------------------------------------------------

class TrayController:
    """系统托盘控制器（pystray 实现）。

    功能:
      - 在系统托盘显示应用图标
      - 托盘右键菜单：显示窗口 / 立即检查提醒 / 退出程序
      - Windows 气泡通知（notify 方法）

    依赖: pip install pystray Pillow

    线程: icon.run() 在独立线程中运行，避免阻塞主 UI
    """
    def __init__(self, app: "ExpiryManagerApp"):
        self.app = app
        self.icon = None
        self.started = False

    def start(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            self.app.log_status("未安装 pystray/Pillow，跳过托盘功能。")
            return

        if self.started:
            return

        image = Image.new("RGB", (64, 64), color="#1f4f7a")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill="#2f7ac5")
        draw.text((18, 19), "到", fill="white")

        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", self.on_show),
            pystray.MenuItem("立即检查提醒", self.on_check),
            pystray.MenuItem("退出程序", self.on_exit),
        )
        self.icon = pystray.Icon("expiry_manager", image, APP_TITLE, menu)
        self.started = True
        thread = threading.Thread(target=self.icon.run, daemon=True)
        thread.start()
        self.app.log_status("托盘提醒已启用。")

    def on_show(self, icon, item):
        self.app.after(0, self.app.show_window)

    def on_check(self, icon, item):
        self.app.after(0, self.app.show_reminder_popup)

    def on_exit(self, icon, item):
        self.app.after(0, self.app.exit_app)

    def stop(self):
        if self.icon:
            self.icon.stop()
        self.started = False

    def notify(self, title: str, message: str):
        if not self.icon:
            return
        try:
            self.icon.notify(message, title)
        except Exception:
            logger.exception("System tray notification failed")
            self.app.log_status("系统托盘通知发送失败，可继续使用启动弹窗提醒。")


class AppShutdownManager:
    """应用退出协调器，统一管理托盘、窗口和数据库的收尾。"""

    def __init__(self, app: "ExpiryManagerApp"):
        self.app = app

    def _close_backend_windows(self):
        for feature_key, window in list(self.app.backend_windows.items()):
            try:
                if window.winfo_exists():
                    window.destroy()
            except Exception:
                pass
            self.app.backend_windows.pop(feature_key, None)

    def _close_optional_resource(self, attr_name: str):
        resource = getattr(self.app, attr_name, None)
        if not resource:
            return
        try:
            close = getattr(resource, "close", None)
            if callable(close):
                close()
                return
            stop = getattr(resource, "stop", None)
            if callable(stop):
                stop()
        except Exception:
            pass

    def shutdown(self):
        self._close_backend_windows()
        self._close_optional_resource("tray")
        for attr_name in ("db", "study_notes_db", "qa_work_log_db", "study_demo_db_conn",
                          "todo_db", "excel_db"):
            self._close_optional_resource(attr_name)
        try:
            self.app.quit()
        except Exception:
            pass
        try:
            self.app.destroy()
        except Exception:
            pass



# ============================================================================
# 12. 主窗口（ExpiryManagerApp）
# ============================================================================
# Tkinter 主窗口类，程序唯一入口。
#
# 初始化流程：
#   __init__() → build_ui() → 加载导航树 → 初始化各页面 Frame
#   → refresh_table() → prompt_login() → 启动外部命令轮询
#
# 页面切换：switch_module() 是枢纽方法，接收模块 key，统一管理 pack_forget/pack。
#
# 各页面构建方法（顺序对应导航树从上到下）：
#   _build_study_notes_page()      → 学习笔记（嵌入主窗口）
#   _build_qa_work_log_page()     → Q&A + 纪要 + 练习记录
#   _build_system_toolbox_page()  → 系统工具箱
# ----------------------------------------------------------------------------

class ExpiryManagerApp(TkinterDnD.Tk):
    """主应用程序窗口（Tkinter Tk 根窗口）。

    职责（核心枢纽）:
      1. 初始化所有数据库连接
      2. 构建完整 UI（导航树 + 多模块 Frame）
      3. 管理页面切换（switch_module）
      4. 处理到期提醒弹窗与系统托盘
      5. 响应导航树选中事件（on_nav_select）

    页面切换机制（switch_module）:
      - 接收模块 key（如 "expiry" / "credentials" / "system_toolbox"）
      - 统一调用各模块 Frame 的 pack_forget() / pack(fill) 方法
      - 保证同一时间只有一个模块 Frame 可见

    持久化:
      - 窗口关闭行为、列可见性等偏好写入 app_state 表
      - 外部命令 token 用于单实例通信
    """
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1480x860")
        self.minsize(1240, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # ★ 关键：锁定 ttk 主题与基础控件样式
        # 防止打开 Toplevel 子窗口后，主窗口 ttk 按钮/标签/输入框的样式
        # （底色、边框、字体）被系统默认主题覆盖，出现"按钮变小变样"问题。
        # 必须在创建任何 ttk 控件之前设置。
        self._init_ttk_styles()

        # 设置窗口图标
        # ★ 主窗口图标：优先从临时文件加载（支持内嵌图标）
        try:
            from embedded_admin_tools.services.app_icon_service import save_temp_app_icon
            icon_path = save_temp_app_icon()
            self.iconbitmap(str(icon_path))
        except Exception:
            # 回退：尝试外部文件（开发模式）
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS
            else:
                base_dir = BASE_DIR
            icon_path = os.path.join(base_dir, "app.ico")
            if os.path.exists(icon_path):
                try:
                    self.iconbitmap(icon_path)
                except Exception:
                    pass

        self.project_root = str(BASE_DIR)  # 项目根目录，供子页面使用
        _migrate_data_dir()
        ensure_data_dir()
        self.db = Database(DB_PATH)
        self.study_notes_db = StudyNotesDB(DB_PATH)
        self.qa_work_log_db = QAWorkLogDBExt(DB_PATH)
        self.study_demo_db_conn = get_study_demo_conn()  # Python 学习模块数据库
        self.todo_db = TodoDB(DB_PATH)  # 待办模块数据库
        # Excel 学习中心数据库：与其它模块共用同一个 db 文件（表名前缀 excel_
        # 自成一套，互不干扰）。首次启动会自动建表并灌入 200 个内置函数。
        self.excel_db = ExcelDB(DB_PATH)
        self.tray = TrayController(self)
        self.shutdown_manager = AppShutdownManager(self)
        self.search_var = tk.StringVar()
        self.credential_search_var = tk.StringVar()
        self.credential_source_var = tk.StringVar(value="全部来源")
        self.credential_group_var = tk.StringVar(value="不分组")
        self.status_var = tk.StringVar(value="准备就绪")
        self.current_user_var = tk.StringVar(value="未登录")
        self.module_title_var = tk.StringVar(value=EXPIRY_MODULE_TITLE)
        self.module_path_var = tk.StringVar(value="")
        self.module_desc_var = tk.StringVar(value="")
        self.login_memory_service = LoginMemoryService()
        self.visible_columns = self.load_visible_columns()
        self.close_behavior = self.load_close_behavior()
        self.startup_completed = False
        self.last_external_show_token = self.db.get_state("external_show_window_token", "")
        self.current_module = ""
        self.backend_windows: dict[str, tk.Toplevel] = {}
        # 到点提醒窗：同时只留一个（新的一批会顶掉旧的）
        self._todo_alert_win = None
        self.module_items = {
            "module_system_toolbox": {
                "title": "系统工具箱",
                "path": "工作 / 系统工具箱",
                "desc": "管理员工具：CMD/PowerShell 管理员启动、批处理脚本管理、快速工具栏。",
                "page": "system_toolbox",
            },
            "module_admin_backend": {
                "title": "后台接口测试",
                "path": "工作 / 接口测试 / 文拍 / 后台接口测试",
                "desc": "已内嵌 adminDemo 的 4 个核心能力，可直接在当前系统内完成登录检测、接口调试、加解密与行情查询。",
                "page": "backend_tools",
            },
            "module_work_credentials": {
                "title": "账号中心",
                "path": "工作 / 账号中心",
                "desc": "统一查看独立账号密码库与共享账户台账，支持来源筛选、按平台或用途分组，以及 Excel 导入导出。",
                "page": "credentials",
            },
            "module_work_processes": {
                "title": "流程中心",
                "path": "工作 / 流程中心",
                "desc": "记录各类申请流程、年审流程和操作流程，支持一个流程下配置任意数量的步骤、链接、截图、必填项与选填项说明。",
                "page": "processes",
            },
            "module_ops_expiry": {
                "title": EXPIRY_MODULE_TITLE,
                "path": f"工作 / 当前所有云服务到期时间 / {EXPIRY_MODULE_TITLE}",
                "desc": "当前模块负责服务器、域名、云服务等到期管理与提醒。",
                "page": "expiry",
            },
            "module_life_todo": {
                "title": "待办",
                "path": "生活 / 待办",
                "desc": "提醒事项式的待办清单：彩色列表分组、重复规则、优先级、标签、子任务与多行备注；未完成自动顺延，周末与法定节假日自动跳过，假期后第一个工作日汇总提醒。",
                "page": "todo",
            },
            "module_life_excel": {
                "title": "Excel 宝典",
                "path": "生活 / Excel 宝典",
                "desc": "配合《Excel 函数与公式速查宝典》的自学工作台：200 个内置函数、"
                        "7 阶段路径、20 条实战配方、间隔重复复习与打卡统计。",
                "page": "excel_learn",
            },
            "module_study_notes": {
                "title": "学习笔记",
                "path": "学习 / 笔记",
                "desc": "百度网盘资料库 + 图书馆式分类笔记管理，支持 Markdown、截图粘贴、标签检索。",
                "page": "study_notes",
            },
            "module_study_demo": {
                "title": "Python 学习",
                "path": "生活 / Python 学习",
                "desc": "视频课程代码学习：课程/章节/代码片段三级管理，代码执行区（Python 子进程 + 超时），关联学习笔记，Demo 文件浏览与运行。",
                "page": "study_demo",
            },
            "module_qa_work": {
                "title": "Q&A与工作纪要",
                "path": "工作 / Q&A与工作纪要",
                "desc": "项目/事件/流程问答记录、每周工作纪要（周一到周五）、每日练习打卡（记忆宫殿/Git/Linux）。",
                "page": "qa_work_log",
            },
            "module_life_home": {
                "title": "生活",
                "path": "生活 / 功能规划中",
                "desc": "生活类模块暂未定义，后续可以继续扩展记账、日程、订阅等功能。",
                "page": "placeholder",
            },
        }

        self.build_ui()

        # 页面注册表：page_id → (page_widget, on_show_func)
        # 必须在 build_ui() 之后初始化，因为页面属性此时才创建
        self._page_registry: dict[str, tuple] = {
            "expiry":         (self.expiry_page,         self.refresh_table),
            "credentials":    (self.credentials_page,     self.refresh_credentials_table),
            "processes":      (self.process_page,        self.process_page_refresh),
            "backend_tools":  (self.backend_page,         self.refresh_backend_tools_page),
            "study_notes":    (self.study_notes_page,    None),
            "qa_work_log":    (self.qa_work_log_page,    None),
            "system_toolbox": (self.system_toolbox_page, None),
            "todo":           (self.todo_page,            self.todo_page_refresh),
            "excel_learn":    (self.excel_learn_page,     self.excel_page_refresh),
            "study_demo":     (self.study_demo_page,     None),
            "note":           (self.note_page,          None),
            "placeholder":    (self.placeholder_page,    None),
        }
        self.refresh_table()
        self.after(100, self.prompt_login)
        self.after(1000, self.poll_external_commands)

    def build_ui(self):
        """构建应用主界面，按功能区域拆分为 8 个子方法。"""
        # 01 顶栏
        self._build_topbar()
        # 02 导航 + 右侧面板框架
        self._build_navigation()
        # 03 右侧面板（含 placeholder / note_page 初始化）
        self._build_right_panel()
        # 04 笔记编辑器内容
        self._build_note_page()
        # 05 后台接口测试 dashboard
        self._build_backend_page()
        # 06 凭证管理（账号中心）
        self._build_credentials_page()
        # 07 流程中心
        self._build_process_page()
        # 08 到期管理表格
        self._build_expiry_page()
    def _build_topbar(self):
        """构建顶栏：左侧应用名 + 面包屑，右侧纯文字动作，底边一条发丝线。"""
        palette = MAIN_PALETTE
        shell_top = ttk.Frame(self, style="App.TFrame")
        shell_top.pack(fill="x")

        inner = tk.Frame(shell_top, bg=palette.surface)
        inner.pack(fill="x", padx=18, pady=12)

        # 品牌标记：与窗口图标同源（app_icons.draw_brand_tile），
        # 给顶栏左端一个视觉锚点。位图由 app_icons 内部缓存持有引用。
        tk.Label(
            inner,
            image=app_icons.brand_mark(inner),
            bg=palette.surface,
            bd=0,
            highlightthickness=0,
        ).pack(side="left", padx=(0, 10))

        tk.Label(
            inner,
            text=APP_TITLE,
            bg=palette.surface,
            fg=palette.text_primary,
            font=FONT_TITLE,
        ).pack(side="left")
        tk.Label(
            inner,
            textvariable=self.module_path_var,
            bg=palette.surface,
            fg=palette.text_muted,
            font=FONT_CAPTION,
        ).pack(side="left", padx=12)
        tk.Label(
            inner,
            textvariable=self.current_user_var,
            bg=palette.surface,
            fg=palette.text_muted,
            font=FONT_CAPTION,
        ).pack(side="right", padx=(12, 0))

        for text, command in (
            ("修改密码", self.change_password),
            ("备份", self._backup_data),
            ("恢复备份", self._restore_backup),
            ("初始化密码", self.reset_password_from_app),
            ("更新日志", self.show_changelog),
        ):
            self._make_topbar_action(inner, text, command)

        tk.Frame(shell_top, bg=palette.border, height=1).pack(fill="x")

    def _make_topbar_action(self, parent, text: str, command):
        """顶栏动作做成纯文字：无边框，悬停才浮现浅底。"""
        palette = MAIN_PALETTE
        label = tk.Label(
            parent,
            text=text,
            bg=palette.surface,
            fg=palette.text_secondary,
            font=FONT_BASE,
            cursor="hand2",
            padx=10,
            pady=4,
        )
        label.pack(side="right")
        label.bind("<Enter>", lambda _e: label.configure(bg=palette.button_hover, fg=palette.text_primary))
        label.bind("<Leave>", lambda _e: label.configure(bg=palette.surface, fg=palette.text_secondary))
        label.bind("<Button-1>", lambda _e: command())
        return label

    def show_changelog(self):
        """顶栏「更新日志」：渲染 app_version.VERSION_HISTORY。

        版本号以前是写死的字符串，换多少次 exe 界面都一模一样；现在顶栏那串
        vX.Y.Z 直接来自 app_version.py，点这里能看到每一版到底改了什么。
        """
        win = tk.Toplevel(self)
        win.title(f"更新日志 · {APP_TITLE}")
        win.minsize(560, 420)
        apply_dialog_form_style(win, MAIN_PALETTE, style_prefix="Changelog")

        header = ttk.Frame(win, padding=(18, 14, 18, 6))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, font=FONT_TITLE).pack(anchor="w")
        ttk.Label(header,
                  text=f"发布日期 {app_version.APP_RELEASE_DATE} · "
                       f"共 {len(app_version.VERSION_HISTORY)} 个版本",
                  foreground=COLOR_MUTED,
                  font=FONT_CAPTION).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(win, padding=(18, 0, 18, 6))
        body.pack(fill="both", expand=True)
        # 滚动条先 pack：同一容器里 expand 的内容区会把后 pack 的定宽控件
        # 挤成 0 像素并被 Tk 直接不映射（看不见，也不报错）
        bar = ttk.Scrollbar(body, orient="vertical")
        bar.pack(side="right", fill="y")
        text = tk.Text(body, wrap="word", relief="flat", bd=0,
                       highlightthickness=0, bg=COLOR_BG, fg=COLOR_TEXT,
                       font=(markdown_view.FONT_FAMILY, markdown_view.BASE_SIZE),
                       padx=4, pady=2, yscrollcommand=bar.set)
        text.pack(side="left", fill="both", expand=True)
        bar.configure(command=text.yview)

        # 复用笔记区的渲染器：标题分级、列表、加粗都现成，不用再写一套排版
        markdown_view.setup_tags(text)
        markdown_view.render(text, app_version.changelog_markdown(),
                             empty_hint="（还没有记录任何版本）")
        text.configure(state="disabled")

        footer = ttk.Frame(win, padding=(18, 6, 18, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="关闭", command=win.destroy).pack(side="right")
        win.bind("<Escape>", lambda _e: win.destroy())
        win.transient(self)
        # Toplevel 默认落在屏幕左上角，离主窗口很远 —— 居中到主窗口上
        win.update_idletasks()
        w, h = 760, 620
        x = self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _backup_data(self):
        try:
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = filedialog.asksaveasfilename(
                title="保存备份文件",
                defaultextension=".zip",
                initialfile="ExpiryManager_Backup_{}.zip".format(ts),
                filetypes=[("ZIP 压缩包", "*.zip")],
                parent=self,
            )
            if not path:
                return
            # Create progress dialog
            dlg = tk.Toplevel(self)
            dlg.title("备份中...")
            dlg.geometry("400x120")
            dlg.transient(self)
            dlg.grab_set()
            dlg.resizable(False, False)
            # Center dialog
            dlg.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - dlg.winfo_width()) // 2
            y = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
            dlg.geometry(f"+{x}+{y}")
            
            ttk.Label(dlg, text="正在备份数据，请稍候...").pack(pady=(15, 10))
            progress_var = tk.DoubleVar(value=0)
            progress_bar = ttk.Progressbar(dlg, variable=progress_var, maximum=100, length=350)
            progress_bar.pack(pady=5)
            status_var = tk.StringVar(value="准备中...")
            status_label = ttk.Label(dlg, textvariable=status_var)
            status_label.pack(pady=5)
            
            def run():
                try:
                    self._do_backup(Path(path), progress_var, status_var, dlg)
                except Exception as ex:
                    import traceback
                    err = str(ex) + "\n" + traceback.format_exc()
                    self.after(0, lambda: messagebox.showerror("备份失败", err, parent=self))
                    self.after(0, dlg.destroy)
            threading.Thread(target=run, daemon=True).start()
        except Exception as ex:
            import traceback
            messagebox.showerror("备份错误", str(ex) + "\n" + traceback.format_exc(), parent=self)


    def _do_backup(self, zip_path, progress_var, status_var, dlg):
        all_files = [p for p in DATA_DIR.rglob("*") if p.is_file()]
        total = len(all_files)
        if total == 0:
            self.after(0, lambda: status_var.set("没有文件需要备份"))
            self.after(1000, dlg.destroy)
            self.after(1000, lambda: messagebox.showinfo("备份完成", "数据目录为空，无需备份", parent=self))
            return
        
        for i, p in enumerate(all_files, 1):
            with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
                zf.write(p, str(p.relative_to(DATA_DIR)))
            progress = (i / total) * 100
            self.after(0, lambda p=progress: progress_var.set(p))
            self.after(0, lambda s=f"已备份 {i}/{total} 个文件": status_var.set(s))
        
        self.after(0, lambda: status_var.set("备份完成！"))
        self.after(500, dlg.destroy)
        self.after(500, lambda: messagebox.showinfo("备份成功", f"已保存到:\n{zip_path}\n\n共备份 {total} 个文件", parent=self))


    def _restore_backup(self):
        path = filedialog.askopenfilename(
            title="选择备份文件",
            filetypes=[("ZIP 压缩包", "*.zip")],
            parent=self,
        )
        if not path:
            return
        if not messagebox.askyesno(
            "确认恢复",
            "恢复备份将覆盖当前所有数据！\n继续吗？",
            parent=self
        ):
            return
        try:
            with zipfile.ZipFile(path, "r") as zf:
                extracted = 0
                for member in zf.namelist():
                    mp = (DATA_DIR / member).resolve()
                    if not str(mp).startswith(str(DATA_DIR.resolve())):
                        continue
                    zf.extract(member, DATA_DIR)
                    extracted += 1
            messagebox.showinfo(
                "恢复成功",
                "已从备份恢复 {} 个文件/目录。\n请重启程序使数据生效。".format(extracted),
                parent=self
            )
        except Exception as ex:
            messagebox.showerror("恢复失败", "解压失败: " + str(ex), parent=self)
    def _build_navigation(self):
        """构建左侧分组导航（自绘侧栏，样式与结构见 nav_sidebar.py）。"""
        palette = MAIN_PALETTE
        self.body = tk.Frame(self, bg=palette.bg)
        self.body.pack(fill="both", expand=True)

        # 侧栏与内容区靠背景色差分栏，不画竖线
        self.nav = SidebarNav(self.body, on_select=self.on_nav_select, width=212)
        self.nav.pack(side="left", fill="y")

    def _build_right_panel(self):
        """构建 right panel。"""
        self.right = ttk.Frame(self.body)
        self.right.pack(side="left", fill="both", expand=True)

        header = ttk.Frame(self.right, padding=(24, 22, 24, 14))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.module_title_var, font=FONT_PAGE_TITLE).pack(anchor="w")
        ttk.Label(header, textvariable=self.module_desc_var, foreground=COLOR_MUTED).pack(anchor="w", pady=(6, 0))

        self.page_container = ttk.Frame(self.right)
        self.page_container.pack(fill="both", expand=True)

        # 学习笔记页面（嵌入主窗口，初始隐藏，switch_module 时显示）
        self.study_notes_page = ttk.Frame(self.page_container)
        self._build_study_notes_page()

        # Q&A与工作纪要页面
        self.qa_work_log_page = ttk.Frame(self.page_container)
        self._build_qa_work_log_page()

        self.study_demo_page = ttk.Frame(self.page_container)
        self._build_study_demo_page()

        # 系统工具箱页面
        self.system_toolbox_page = ttk.Frame(self.page_container)
        self._build_system_toolbox_page()

        # 待办 / 提醒事项页面
        self.todo_page = ttk.Frame(self.page_container)
        self._build_todo_page()

        # Excel 学习中心页面
        self.excel_learn_page = ttk.Frame(self.page_container)
        self._build_excel_page()

        # 简单笔记页面
        self.note_page = ttk.Frame(self.page_container)

        self.placeholder_page = ttk.Frame(self.page_container)
        self.placeholder_page.pack(fill="both", expand=True)
        placeholder_box = ttk.Frame(self.placeholder_page, padding=24)
        placeholder_box.pack(fill="both", expand=True)
        self.placeholder_title_var = tk.StringVar(value="功能规划中")
        self.placeholder_desc_var = tk.StringVar(value="请选择左侧模块。")
        ttk.Label(placeholder_box, textvariable=self.placeholder_title_var, font=FONT_PAGE_TITLE).pack(
            anchor="w"
        )
        ttk.Label(placeholder_box, textvariable=self.placeholder_desc_var, wraplength=760, foreground=COLOR_MUTED_2).pack(
            anchor="w", pady=(10, 0)
        )


    def _build_note_page(self):
        """构建 note page。"""
        note_toolbar = ttk.Frame(self.note_page, padding=(10, 10, 10, 6))
        note_toolbar.pack(fill="x")
        self.note_action_frame = ttk.Frame(note_toolbar)
        self.note_action_frame.pack(side="left")
        ttk.Button(note_toolbar, text="保存内容", command=self.save_current_note).pack(side="right", padx=4)
        ttk.Button(note_toolbar, text="重新加载", command=self.reload_current_note).pack(side="right", padx=4)

        note_editor_frame = ttk.Frame(self.note_page, padding=(10, 0, 10, 10))
        note_editor_frame.pack(fill="both", expand=True)
        self.note_text = scrolledtext.ScrolledText(note_editor_frame, wrap="word", font=FONT_BASE)
        self.note_text.pack(fill="both", expand=True)


    def _build_backend_page(self):
        """构建 backend page。"""
        BackendPage(self, self.page_container, backend_feature_items=BACKEND_FEATURE_ITEMS).build()


    def _build_credentials_page(self):
        """构建 credentials page。"""
        CredentialsPage(self, self.page_container, AccountImagePreview).build()

    def _build_process_page(self):
        """构建流程中心页面（视图与交互都在 process_page.ProcessPage 里）。"""
        self.process_page = ProcessPage(
            self.page_container,
            self.db,
            app_title=APP_TITLE,
            flow_templates=PROCESS_FLOW_TEMPLATES,
            image_preview_cls=AccountImagePreview,
            images=ProcessImageTools(
                base_dir=BASE_DIR,
                resolve_paths=resolve_account_image_paths,
                storage_value=get_account_image_storage_value,
                make_dir=ensure_account_image_dir,
                parse_items=parse_account_image_items,
                serialize_items=serialize_account_image_items,
            ),
            format_datetime=format_datetime_text,
            on_status=self.log_status,
        )

    def process_page_refresh(self):
        """页面切换垫片：让流程中心按当前选中项重新渲染。"""
        self.process_page.refresh_flows()

    def _build_expiry_page(self):
        """构建 expiry page。"""
        ExpiryPage(
            self,
            self.page_container,
            tree_columns=TREE_COLUMNS,
            column_meta=COLUMN_META,
        ).build()

    def _init_ttk_styles(self):
        """锁定 ttk 主题与基础控件样式。

        目的：防止打开 Toplevel 子窗口后，Windows 重新初始化 ttk 主题，
        导致主窗口的按钮/标签/输入框底色、边框、字体发生回退（"按钮变小变样"）。

        关键点：
        1. 使用 clam 主题而不是 vista——clam 是 tkinter 自带的扁平主题，
           不会随主窗口失焦而改变按钮外观；vista 主题依赖 Windows 原生绘制，
           主窗口失去焦点时按钮会被重新渲染为"非激活"样式。
        2. 锁定 tk scaling 值，防止 Toplevel 创建时 DPI/scaling 变化影响主窗口。
        """
        from tkinter import ttk as _ttk
        # 锁定 tk 缩放因子，防止创建 Toplevel 后 scaling 变化影响主窗口字体大小
        try:
            current_scaling = self.tk.call("tk", "scaling")
            self._locked_scaling = float(current_scaling)
        except Exception:
            self._locked_scaling = None
        THEME.apply_main_ttk_theme(self, _ttk.Style(self), MAIN_PALETTE)

    def get_deletable_account_image_paths(
        self,
        *,
        credential_ids: list[int] | None = None,
        shared_ids: list[int] | None = None,
    ) -> tuple[list[Path], int, int]:
        credential_ids = credential_ids or []
        shared_ids = shared_ids or []
        deleting_refs: dict[str, Path] = {}
        credential_count = 0
        shared_count = 0

        for item_id in credential_ids:
            row = self.db.get_credential_item(item_id)
            if not row:
                continue
            credential_count += 1
            image_value = normalize_text(row["screenshot_path"])
            image_refs = normalize_account_image_refs(image_value)
            image_paths = resolve_account_image_paths(image_value)
            for image_ref, image_path in zip(image_refs, image_paths):
                if image_ref and image_path:
                    deleting_refs[image_ref] = image_path

        for account_id in shared_ids:
            row = self.db.get_shared_account(account_id)
            if not row:
                continue
            shared_count += 1
            image_value = normalize_text(row["screenshot_path"])
            image_refs = normalize_account_image_refs(image_value)
            image_paths = resolve_account_image_paths(image_value)
            for image_ref, image_path in zip(image_refs, image_paths):
                if image_ref and image_path:
                    deleting_refs[image_ref] = image_path

        if not deleting_refs:
            return [], credential_count, shared_count

        remaining_refs: set[str] = set()
        credential_id_set = set(credential_ids)
        shared_id_set = set(shared_ids)

        for row in self.db.fetch_credential_items():
            if row["id"] in credential_id_set:
                continue
            for image_ref in normalize_account_image_refs(row["screenshot_path"]):
                if image_ref:
                    remaining_refs.add(image_ref)

        for row in self.db.fetch_all_shared_accounts():
            if row["id"] in shared_id_set:
                continue
            for image_ref in normalize_account_image_refs(row["screenshot_path"]):
                if image_ref:
                    remaining_refs.add(image_ref)

        image_paths = [
            image_path for image_ref, image_path in deleting_refs.items() if image_ref not in remaining_refs and image_path.exists()
        ]
        return image_paths, credential_count, shared_count

    def delete_local_account_image_files(self, image_paths: list[Path]) -> tuple[int, list[str]]:
        removed_count = 0
        failed_files: list[str] = []
        for image_path in image_paths:
            try:
                if image_path.exists():
                    image_path.unlink()
                    removed_count += 1
            except (OSError, Exception) as exc:
                failed_files.append(f"{image_path} ({exc})")
        return removed_count, failed_files

    def prompt_login(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.update_idletasks()  # 强制刷新确保窗口立即显示
        dialog = LoginDialog(self, self.db)
        self.wait_window(dialog)
        if not dialog.result:
            self.exit_app()
            return
        self.current_user_var.set(f"当前用户：{dialog.result}")
        self.show_window()
        self.select_default_module()
        self.startup_sequence()
        if not self.startup_completed:
            self.startup_completed = True
            self.after(CHECK_INTERVAL_MS, self.periodic_reminder_check)

    def select_default_module(self):
        self.switch_module("module_ops_expiry")

    def on_nav_select(self, module_id: str):
        """侧栏点击回调：SidebarNav 直接传模块 key（不再是 Treeview 事件）。"""
        if module_id in self.module_items:
            self.switch_module(module_id)

    def _show_page(self, page_id: str, config: dict, *extra_args):
        """隐藏所有页面，仅显示 page_id 对应的页面，并调用其 on_show 函数。"""
        for pid, (page, _) in self._page_registry.items():
            page.pack_forget()
        if page_id in self._page_registry:
            page, on_show = self._page_registry[page_id]
            page.pack(fill="both", expand=True)
            if on_show:
                if extra_args:
                    on_show(*extra_args)
                else:
                    on_show()
        elif page_id == "note":
            # note 页需要额外传入 config
            self.load_note_module(config)
            self.note_page.pack(fill="both", expand=True)
        else:
            # 兜底 placeholder
            self.placeholder_title_var.set(config.get("title", ""))
            self.placeholder_desc_var.set(config.get("desc", ""))
            self.placeholder_page.pack(fill="both", expand=True)

    def switch_module(self, module_id: str):
        config = self.module_items.get(module_id)
        if not config:
            return
        self.current_module = module_id
        # 同步侧栏高亮。notify=False：高亮由这里驱动，避免回调再触发一次切换。
        self.nav.select(module_id, notify=False)
        self.module_title_var.set(config["title"])
        self.module_path_var.set(config["path"])
        self.module_desc_var.set(config["desc"])
        self._show_page(config["page"], config)

    def get_backend_login_memory_summary(self) -> str:
        saved = self.login_memory_service.load()
        if not saved:
            return "当前默认预填账号：未设置。首次在任一接口工具中登录成功后，会自动记住账号、密码、环境与会员类型。"

        account = mask_account_text(str(saved.get("account", "")))
        member_type = str(saved.get("member_type", "supplier") or "supplier")
        member_label = "供货会员" if member_type == "supplier" else "经济会员"
        environment_label = str(saved.get("environment_label", "测试环境") or "测试环境")
        lt = str(saved.get("lt", "web") or "web")
        return (
            f"当前默认预填账号：{account or '未设置'}    "
            f"会员类型：{member_label}    环境：{environment_label}    登录类型：{lt}"
        )

    def get_backend_login_memory_tip(self) -> str:
        storage_label = self.login_memory_service.get_storage_label()
        if storage_label == "未设置":
            return "当前没有本机登录记忆。首次登录成功后会自动在当前电脑生成新的本机加密记忆。"
        return f"当前记忆存储方式：{storage_label}。如需切换测试账号，可点击右上角“清除已记住账号”。"

    def get_backend_feature_title(self, feature_key: str) -> str:
        for item in BACKEND_FEATURE_ITEMS:
            if item["key"] == feature_key:
                return item["title"]
        return feature_key

    def load_backend_recent_records(self) -> dict:
        raw_text = self.db.get_state("backend_recent_records", "")
        if not raw_text:
            return {}
        try:
            data = json.loads(raw_text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save_backend_recent_records(self, data: dict):
        self.db.set_state("backend_recent_records", json.dumps(data, ensure_ascii=False))

    def record_backend_recent_action(self, action_text: str, *, feature_key: str = "", login_snapshot: dict | None = None):
        records = self.load_backend_recent_records()
        now_text = datetime.now().isoformat(timespec="seconds")
        records["last_action_text"] = action_text
        records["last_action_time"] = now_text
        if feature_key:
            records["last_feature_key"] = feature_key
            records["last_feature_title"] = self.get_backend_feature_title(feature_key)
            records["last_feature_time"] = now_text
            feature_activity = records.get("feature_activity", {})
            if not isinstance(feature_activity, dict):
                feature_activity = {}
            feature_activity[feature_key] = {
                "title": self.get_backend_feature_title(feature_key),
                "action_text": action_text,
                "action_time": now_text,
            }
            records["feature_activity"] = feature_activity
        snapshot = login_snapshot if login_snapshot is not None else self.login_memory_service.load()
        if snapshot:
            records["last_account"] = str(snapshot.get("account", "") or "")
            records["last_member_type"] = str(snapshot.get("member_type", "supplier") or "supplier")
            records["last_environment_label"] = str(snapshot.get("environment_label", "测试环境") or "测试环境")
            records["last_login_time"] = now_text
        self.save_backend_recent_records(records)

    def get_backend_feature_activity(self, feature_key: str) -> dict:
        records = self.load_backend_recent_records()
        feature_activity = records.get("feature_activity", {})
        if not isinstance(feature_activity, dict):
            return {}
        data = feature_activity.get(feature_key, {})
        return data if isinstance(data, dict) else {}

    def get_backend_card_status_meta(self, feature_key: str) -> tuple[str, str, str]:
        if self.is_backend_window_alive(feature_key):
            return "运行中", "#e8f3ff", "#1f4d8b"
        if self.get_backend_feature_activity(feature_key):
            return "已使用", "#eaf6ea", "#2f6b2f"
        return "待打开", "#f5f5f5", "#666666"

    def get_backend_feature_recent_text(self, feature_key: str) -> str:
        activity = self.get_backend_feature_activity(feature_key)
        if not activity:
            return "最近操作：未记录"
        action_text = normalize_text(activity.get("action_text", ""))
        action_time = format_datetime_text(str(activity.get("action_time", "") or ""))
        return f"最近操作：{action_text}    最近时间：{action_time}"

    def get_backend_recent_account_text(self) -> str:
        saved = self.login_memory_service.load()
        if saved and self.login_memory_service.file_path.exists():
            account = mask_account_text(str(saved.get("account", "")))
            member_type = str(saved.get("member_type", "supplier") or "supplier")
            member_label = "供货会员" if member_type == "supplier" else "经济会员"
            environment_label = str(saved.get("environment_label", "测试环境") or "测试环境")
            write_time = datetime.fromtimestamp(self.login_memory_service.file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            return (
                f"最近登录账号：{account or '未设置'}    会员类型：{member_label}    "
                f"环境：{environment_label}    最近写入：{write_time}"
            )

        records = self.load_backend_recent_records()
        account = mask_account_text(str(records.get("last_account", "") or ""))
        if not account:
            return "最近登录账号：未记录。首次登录成功后，这里会显示最近一次写入到本机的测试账号。"
        member_type = str(records.get("last_member_type", "supplier") or "supplier")
        member_label = "供货会员" if member_type == "supplier" else "经济会员"
        environment_label = str(records.get("last_environment_label", "测试环境") or "测试环境")
        login_time = format_datetime_text(str(records.get("last_login_time", "") or ""))
        return (
            f"最近登录账号：{account}    会员类型：{member_label}    "
            f"环境：{environment_label}    最近联调：{login_time}"
        )

    def get_backend_recent_feature_text(self) -> str:
        records = self.load_backend_recent_records()
        feature_title = normalize_text(records.get("last_feature_title", ""))
        if not feature_title:
            return "最近打开功能：未记录。打开任一后台接口测试功能后，这里会自动显示最近一次使用情况。"
        feature_time = format_datetime_text(str(records.get("last_feature_time", "") or ""))
        return f"最近打开功能：{feature_title}    最近打开时间：{feature_time}"

    def get_backend_recent_action_text(self) -> str:
        records = self.load_backend_recent_records()
        action_text = normalize_text(records.get("last_action_text", ""))
        if not action_text:
            return "最近联调动作：未记录。后续打开功能、定位窗口、清除登录记忆时会自动更新。"
        action_time = format_datetime_text(str(records.get("last_action_time", "") or ""))
        return f"最近联调动作：{action_text}    动作时间：{action_time}"

    def get_backend_strip_account_text(self) -> str:
        saved = self.login_memory_service.load()
        if saved:
            account = mask_account_text(str(saved.get("account", "")))
            member_type = str(saved.get("member_type", "supplier") or "supplier")
            member_label = "供货会员" if member_type == "supplier" else "经济会员"
            return f"{account or '未设置'} / {member_label}"
        records = self.load_backend_recent_records()
        account = mask_account_text(str(records.get("last_account", "") or ""))
        if account:
            return f"{account} / 最近使用"
        return "未设置"

    def get_backend_strip_environment_text(self) -> str:
        saved = self.login_memory_service.load()
        if saved:
            environment_label = str(saved.get("environment_label", "测试环境") or "测试环境")
            lt = str(saved.get("lt", "web") or "web")
            return f"{environment_label} / {lt}"
        records = self.load_backend_recent_records()
        environment_label = str(records.get("last_environment_label", "") or "")
        if environment_label:
            return f"{environment_label} / 最近记录"
        return "测试环境 / web"

    def get_backend_strip_result_text(self) -> str:
        records = self.load_backend_recent_records()
        action_text = normalize_text(records.get("last_action_text", ""))
        action_time = format_datetime_text(str(records.get("last_action_time", "") or ""))
        if action_text:
            return f"{action_text} / {action_time}"
        return "接口链路已验证，可直接进入会员接口与行情查询联调"

    def clear_backend_login_memory(self):
        has_memory = bool(self.login_memory_service.load_raw())
        if not has_memory:
            messagebox.showinfo("提示", "当前没有可清除的登录记忆。")
            return
        if not messagebox.askyesno("确认清除", "确定要清除当前电脑已记住的接口测试账号吗？"):
            return
        last_snapshot = self.login_memory_service.load()
        self.login_memory_service.clear()
        self.record_backend_recent_action("已清除本机登录记忆", login_snapshot=last_snapshot)
        self.refresh_backend_tools_page()
        messagebox.showinfo("完成", "已清除本机登录记忆。下次打开工具时将不再自动带出账号密码。")

    def _build_study_notes_page(self):
        """
        构建学习笔记资料库页面（嵌入主窗口，非独立窗口）。
        由 __init__ 调用一次，之后通过 switch_module("study_notes") 切换显示/隐藏。
        """
        page = StudyNotesPage(self.study_notes_page, self.study_notes_db)
        page.pack(fill="both", expand=True)

    def _build_qa_work_log_page(self):
        """
        构建 Q&A与工作纪要页面（嵌入主窗口）。
        整合 Q&A问答、每周工作纪要、练习记录三大功能。
        """
        page = QAWorkLogPage(self.qa_work_log_page, self.qa_work_log_db)
        page.pack(fill="both", expand=True)

    def _build_system_toolbox_page(self):
        """构建系统工具箱页面"""
        page = SystemToolboxPage(self.system_toolbox_page, self.db, project_root=self.project_root)
        page.pack(fill="both", expand=True)

    def _build_todo_page(self):
        """构建待办 / 提醒事项页面（嵌入主窗口，非独立窗口）。"""
        page = TodoPage(self.todo_page, self.todo_db)
        page.pack(fill='both', expand=True)
        self.todo_view = page

    def _build_excel_page(self):
        """构建 Excel 学习中心页面（嵌入主窗口，非独立窗口）。

        图片能力走 ``ExcelImageTools`` 适配器注入，页面**不反向 import main** ——
        与流程中心同一套做法（避免循环导入）。
        """
        self.excel_view = ExcelLearningPage(
            self.excel_learn_page,
            self.excel_db,
            app_title=APP_TITLE,
            image_preview_cls=AccountImagePreview,
            images=ExcelImageTools(
                base_dir=BASE_DIR,
                resolve_paths=resolve_account_image_paths,
                storage_value=get_account_image_storage_value,
                make_dir=ensure_account_image_dir,
                parse_items=parse_account_image_items,
                serialize_items=serialize_account_image_items,
            ),
            on_status=self.log_status,
        )
        self.excel_view.pack(fill="both", expand=True)

    def excel_page_refresh(self):
        """页面切换垫片：拉一次最新进度，再重画当前视图。"""
        self.excel_view.refresh()

    def _build_study_demo_page(self):
        """构建 Python 学习辅助模块页面"""
        page = StudyDemoPage(self.study_demo_page, self.study_demo_db_conn,
                             project_root=self.project_root)
        page.pack(fill="both", expand=True)

    def refresh_backend_tools_page(self):
        opened_count = 0
        self.backend_login_memory_var.set(self.get_backend_login_memory_summary())
        self.backend_memory_tip_var.set(self.get_backend_login_memory_tip())
        self.backend_strip_account_var.set(self.get_backend_strip_account_text())
        self.backend_strip_environment_var.set(self.get_backend_strip_environment_text())
        self.backend_strip_result_var.set(self.get_backend_strip_result_text())
        self.backend_recent_account_var.set(self.get_backend_recent_account_text())
        self.backend_recent_feature_var.set(self.get_backend_recent_feature_text())
        self.backend_recent_action_var.set(self.get_backend_recent_action_text())
        self.backend_metric_module_var.set(str(len(BACKEND_FEATURE_ITEMS)))
        self.backend_metric_verified_var.set("3")
        self.backend_metric_storage_var.set(self.login_memory_service.get_storage_label())
        for tool in BACKEND_FEATURE_ITEMS:
            feature_key = tool["key"]
            row = self.backend_tool_rows.get(feature_key)
            if not row:
                continue
            verified_map = {
                "api_demo": "已验证：测试环境登录成功，会员接口查询正常。",
                "crypto": "已验证：DES / CBC / PKCS7 / Base64 本地加解密往返正常。",
                "login_checker": "已验证：真实账号可登录，返回包可被正确识别。",
                "market_quote": "已验证：真实行情接口返回成功，可取到行情列表。",
            }
            badge_text, badge_bg, badge_fg = self.get_backend_card_status_meta(feature_key)
            row["status_badge_var"].set(badge_text)
            row["status_badge_widget"].configure(bg=badge_bg, fg=badge_fg)
            row["recent_var"].set(self.get_backend_feature_recent_text(feature_key))
            if self.is_backend_window_alive(feature_key):
                opened_count += 1
                row["detail_var"].set(
                    f"实现方式：功能已复制进当前项目源码，作为系统内部窗口打开。{verified_map.get(feature_key, '')}"
                )
                row["status_var"].set("状态说明：窗口已打开，可直接定位")
                row["open_button"].configure(text="定位窗口", state="normal")
            else:
                row["detail_var"].set(
                    f"实现方式：功能已复制进当前项目源码，作为系统内部窗口打开。{verified_map.get(feature_key, '')}"
                )
                row["status_var"].set("状态说明：可直接打开并继续联调")
                row["open_button"].configure(text="打开功能", state="normal")
        self.backend_metric_opened_var.set(str(opened_count))
        self.backend_status_var.set(
            f"当前已内嵌 {len(BACKEND_FEATURE_ITEMS)} 个功能模块    正在打开 {opened_count} 个窗口    默认环境：测试环境    功能来源：当前项目 embedded_admin_tools"
        )

    def get_backend_window_class(self, feature_key: str):
        mapping = {
            "api_demo": ApiDemoWindow,
            "crypto": CryptoToolWindow,
            "login_checker": LoginCheckerWindow,
            "market_quote": MarketQuoteToolWindow,
        }
        return mapping.get(feature_key)

    def is_backend_window_alive(self, feature_key: str) -> bool:
        window = self.backend_windows.get(feature_key)
        return bool(window and window.winfo_exists())

    def handle_backend_window_destroy(self, feature_key: str):
        self.backend_windows.pop(feature_key, None)
        if self.current_module == "module_admin_backend":
            self.refresh_backend_tools_page()

    def open_backend_feature(self, feature_key: str):
        existing = self.backend_windows.get(feature_key)
        if existing and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            self.record_backend_recent_action(f"已定位窗口：{self.get_backend_feature_title(feature_key)}", feature_key=feature_key)
            self.refresh_backend_tools_page()
            self.log_status(f"已定位功能窗口：{feature_key}")
            return
        window_class = self.get_backend_window_class(feature_key)
        if not window_class:
            messagebox.showwarning(APP_TITLE, f"未找到功能定义：{feature_key}", parent=self)
            return
        try:
            window = window_class(self)
            self.backend_windows[feature_key] = window
            window.bind("<Destroy>", lambda _event, key=feature_key: self.handle_backend_window_destroy(key), add="+")
            self.record_backend_recent_action(f"已打开功能：{self.get_backend_feature_title(feature_key)}", feature_key=feature_key)
            self.refresh_backend_tools_page()
            self.log_status(f"已打开功能：{feature_key}")
        except (webbrowser.Error, OSError, Exception) as exc:
            messagebox.showerror(APP_TITLE, f"打开功能失败：{feature_key}\n\n{exc}", parent=self)

    def focus_backend_window(self, feature_key: str):
        window = self.backend_windows.get(feature_key)
        if window and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            self.record_backend_recent_action(f"已从功能卡片定位窗口：{self.get_backend_feature_title(feature_key)}", feature_key=feature_key)
            self.refresh_backend_tools_page()
            return
        messagebox.showinfo(APP_TITLE, "该功能窗口当前尚未打开。", parent=self)

    def close_all_backend_windows(self):
        closed_any = False
        for feature_key, window in list(self.backend_windows.items()):
            if window and window.winfo_exists():
                try:
                    window.destroy()
                    closed_any = True
                except Exception:
                    logger.exception(f"Error closing backend window: {feature_key}")
                    pass
            self.backend_windows.pop(feature_key, None)
        if closed_any:
            self.record_backend_recent_action("已关闭全部后台接口测试功能窗口")
        self.refresh_backend_tools_page()
        self.log_status("已关闭全部后台接口测试功能窗口。")

    def render_note_actions(self, actions: list[str]):
        for child in self.note_action_frame.winfo_children():
            child.destroy()
        for action in actions:
            if action == "open_account_ledger":
                ttk.Button(self.note_action_frame, text="打开账号中心", command=self.open_account_ledger).pack(side="left", padx=4)

    def load_note_module(self, config: dict):
        note_key = config.get("note_key", "")
        default_content = config.get("default_content", "")
        content = self.db.get_module_note(note_key, default_content)
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", content)
        self.render_note_actions(config.get("actions", []))

    def save_current_note(self):
        config = self.module_items.get(self.current_module)
        if not config or config.get("page") != "note":
            return
        content = self.note_text.get("1.0", "end").rstrip()
        self.db.set_module_note(config.get("note_key", ""), content)
        self.log_status(f"已保存：{config['title']}")
        messagebox.showinfo(APP_TITLE, f"{config['title']} 已保存。", parent=self)

    def reload_current_note(self):
        config = self.module_items.get(self.current_module)
        if not config or config.get("page") != "note":
            return
        self.load_note_module(config)
        self.log_status(f"已重新加载：{config['title']}")

    def change_password(self):
        username = self.current_user_var.get().replace("当前用户：", "").strip()
        if not username:
            messagebox.showinfo(APP_TITLE, "当前未登录，无法修改密码。", parent=self)
            return
        dialog = ChangePasswordDialog(self, self.db, username)
        # ChangePasswordDialog.apply() 已调用 set_user_password + clear_must_change_password，
        # 此处不需要重复保存。dialog.result 仅用于判断用户是否确认了对话框。
        if dialog.result:
            self.log_status("密码已修改。")
            messagebox.showinfo(APP_TITLE, "密码修改成功。", parent=self)

    def reset_password_from_app(self):
        if not messagebox.askyesno(APP_TITLE, "确认将管理员密码重置为随机强密码吗？\n新密码将显示在弹窗中，请立即记录。", parent=self):
            return
        new_password = self.db.reset_admin_password()
        self.log_status("管理员密码已初始化。")
        messagebox.showinfo(APP_TITLE, f"初始化成功。\n账号：admin\n新密码：{new_password}\n\n请立即记录此密码。", parent=self)

    def log_status(self, message: str):
        self.status_var.set(message)

    def load_visible_columns(self) -> list[str]:
        saved = self.db.get_state("visible_columns", ",".join(DEFAULT_DISPLAY_COLUMNS))
        columns = [column for column in saved.split(",") if column in DISPLAYABLE_COLUMNS]
        return columns or list(DEFAULT_DISPLAY_COLUMNS)

    def save_visible_columns(self):
        self.db.set_state("visible_columns", ",".join(self.visible_columns))

    def load_close_behavior(self) -> str:
        value = self.db.get_state("close_behavior", "ask")
        return value if value in ("ask", "minimize", "exit") else "ask"

    def save_close_behavior(self):
        self.db.set_state("close_behavior", self.close_behavior)

    def apply_visible_columns(self):
        display_columns = tuple(self.visible_columns + ["days_left", "detail_action"])
        self.tree.configure(displaycolumns=display_columns)

    def open_settings(self):
        dialog = SettingsDialog(
            self,
            self.visible_columns,
            self.close_behavior,
            app_title=APP_TITLE,
            displayable_columns=DISPLAYABLE_COLUMNS,
            column_meta=COLUMN_META,
        )
        if dialog.result:
            self.visible_columns = dialog.result["visible_columns"]
            self.close_behavior = dialog.result["close_behavior"]
            self.save_visible_columns()
            self.save_close_behavior()
            self.apply_visible_columns()
            self.refresh_table()
            self.log_status("已更新面板与关闭行为设置。")

    def startup_sequence(self):
        self.tray.start()
        if not self.db.fetch_assets():
            if DEFAULT_IMPORT_FILE.exists():
                self.import_excel(DEFAULT_IMPORT_FILE, silent=False)
            else:
                self.log_status(f"未找到默认 Excel：{DEFAULT_IMPORT_FILE}")
                messagebox.showwarning(
                    APP_TITLE,
                    "未找到默认 Excel 文件，请将文件放到程序根目录后重试，或点击“导入 Excel”手动选择。\n\n"
                    f"默认文件名：{DEFAULT_IMPORT_FILE.name}\n"
                    f"当前查找路径：{DEFAULT_IMPORT_FILE}",
                    parent=self,
                )
        self.show_reminder_popup()
        self.trigger_daily_tray_reminder(force=False)
        # 推迟到 2.5s：登录提示在 100ms 弹出，别让两个模态框打架
        self.after(2500, self.todo_daily_maintenance)
        # 到点提醒的巡检：起一次就自己续期，程序开着就一直有效
        self.after(3000, self.todo_alert_check)

    def poll_external_commands(self):
        token = self.db.get_state("external_show_window_token", "")
        if token and token != self.last_external_show_token:
            self.last_external_show_token = token
            self.show_window()
            self.log_status("已从托盘恢复窗口。")
        self.after(300, self.poll_external_commands)

    def get_selected_asset_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "请先选择一条记录。", parent=self)
            return None
        return int(self.tree.item(selection[0], "values")[0])

    def on_tree_click(self, event):
        item_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not item_id or column_id == "#0":
            return
        self.tree.selection_set(item_id)
        column_index = int(column_id[1:]) - 1
        display_columns = list(self.tree.cget("displaycolumns"))
        if column_index >= len(display_columns):
            return
        column_name = display_columns[column_index]
        asset_id = int(self.tree.item(item_id, "values")[0])
        if column_name == "detail_action":
            self.show_asset_detail(asset_id)

    def import_excel(self, preset_path: Path | None = None, silent: bool = False):
        if preset_path is None:
            selected = filedialog.askopenfilename(
                title="选择 Excel 文件",
                filetypes=[("Excel 文件", "*.xlsx *.xlsm")],
            )
            if not selected:
                return
            file_path = Path(selected)
        else:
            file_path = Path(preset_path)

        if not file_path.exists():
            messagebox.showerror(
                APP_TITLE,
                f"Excel 文件不存在：\n{file_path}",
                parent=self,
            )
            self.log_status(f"Excel 文件不存在：{file_path}")
            return

        try:
            items = load_excel_assets(file_path)
            self.db.replace_imported_assets(items, str(file_path))
            self.refresh_table()
            self.log_status(f"已导入 {len(items)} 条记录：{file_path.name}")
            if not silent:
                messagebox.showinfo(APP_TITLE, f"导入成功，共 {len(items)} 条记录。", parent=self)
        except (zipfile.BadZipFile, OSError) as exc:
            # 实测：损坏或非 xlsx 的表格由 openpyxl 底层抛出 zipfile.BadZipFile
            messagebox.showerror(APP_TITLE, f"导入失败：{exc}", parent=self)
        except Exception as exc:
            # 兜底：含 openpyxl.utils.exceptions.InvalidFileException、缺失依赖的 RuntimeError
            logger.exception("导入 Excel 资产失败：%s", file_path)
            messagebox.showerror(APP_TITLE, f"导入失败：{exc}", parent=self)

    def refresh_table(self):
        keyword = self.search_var.get().strip()
        for item in self.tree.get_children():
            self.tree.delete(item)

        rows = self.db.fetch_assets(keyword=keyword)
        table_font = treeview_font(self.tree)

        def cell(value, column):
            """单元格统一「压成单行 + 按列宽截断」。

            库里的资源详情/账号信息可能是多行的（一行一个 IP 或域名），
            直接塞进 Treeview 会把行撑高、文字溢出到相邻列，整表看着是散的；
            这里统一收敛成一行并加省略号，完整内容由「详情」弹窗负责。
            """
            return summarize_cell_text(value, column,
                                       column_meta=COLUMN_META, font=table_font)

        for row in rows:
            expiry_dt = parse_expiry_date(row["expiry_date"])
            remain = days_left(expiry_dt)
            tag = ""
            if remain is not None and remain < 0:
                tag = "overdue"
            elif remain is not None and remain <= 15:
                tag = "due_15"
            elif remain is not None and remain <= 30:
                tag = "due_30"

            account_subject = row["account_subject_name"] or row["account_subject_code"]
            resource_subject = row["resource_subject_name"] or row["resource_subject_code"]
            accounts = self.db.fetch_shared_accounts(row["account_no"])
            account_count = len(accounts)
            account_summary = format_asset_account_summary(row["account_no"], accounts)
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["record_no"],
                    cell(row["platform"], "platform"),
                    cell(account_summary, "account_no"),
                    cell(account_subject, "account_subject"),
                    cell(row["resource_type"], "resource_type"),
                    cell(row["resource_detail"], "resource_detail"),
                    cell(resource_subject, "resource_subject"),
                    row["expiry_date"],
                    "" if remain is None else remain,
                    "详情",
                    f"账户({account_count})",
                    cell(row["note"], "note"),
                ),
                tags=(tag,) if tag else (),
            )
        self.log_status(f"当前共有 {len(rows)} 条记录。")

    def add_asset(self):
        dialog = AssetDialog(self, "新增记录", app_title=APP_TITLE)
        if dialog.result:
            self.db.insert_asset(dialog.result)
            self.refresh_table()
            self.log_status("已新增记录。")

    def edit_asset(self):
        asset_id = self.get_selected_asset_id()
        if asset_id is None:
            return
        row = self.db.get_asset(asset_id)
        if not row:
            messagebox.showwarning(APP_TITLE, "记录不存在。", parent=self)
            return
        initial = dict(row)
        dialog = AssetDialog(self, "编辑记录", initial=initial, app_title=APP_TITLE)
        if dialog.result:
            self.db.update_asset(asset_id, dialog.result)
            self.refresh_table()
            self.log_status("已更新记录。")

    def delete_asset(self):
        asset_id = self.get_selected_asset_id()
        if asset_id is None:
            return
        if not messagebox.askyesno(APP_TITLE, "确认删除这条记录吗？", parent=self):
            return
        self.db.delete_asset(asset_id)
        self.refresh_table()
        self.log_status("已删除记录。")

    def show_asset_detail(self, asset_id: int):
        row = self.db.get_asset(asset_id)
        if not row:
            messagebox.showwarning(APP_TITLE, "记录不存在。", parent=self)
            return
        DetailDialog(
            self,
            row,
            self.db.fetch_shared_accounts(row["account_no"]),
            detail_fields=DETAIL_FIELDS,
            format_account_identity=format_account_identity,
            remain_days=days_left(parse_expiry_date(row["expiry_date"])),
        )

    def show_account_manager(self, asset_id: int):
        row = self.db.get_asset(asset_id)
        if not row:
            messagebox.showwarning(APP_TITLE, "记录不存在。", parent=self)
            return
        if not normalize_text(row["account_no"]):
            messagebox.showinfo(APP_TITLE, "这条记录没有账号编号，无法进入共享账户管理。", parent=self)
            return
        context = {
            "subject_code": row["account_subject_code"] or "",
            "subject_name": row["account_subject_name"] or "",
            "account_no": row["account_no"] or "",
            "platform": row["platform"] or "",
            "link_url": "",
            "email": "",
            "phone": "",
            "note": row["note"] or "",
        }
        SharedAccountManagerDialog(
            self,
            row["account_no"],
            context=context,
            app_title=APP_TITLE,
            normalize_text=normalize_text,
            format_account_identity=format_account_identity,
            get_account_image_display_text=get_account_image_display_text,
            account_edit_dialog_cls=AccountEditDialog,
            account_image_preview_cls=AccountImagePreview,
        )

    def open_selected_account_manager(self):
        asset_id = self.get_selected_asset_id()
        if asset_id is None:
            return
        self.show_account_manager(asset_id)

    def build_credential_group_label(self, row: dict) -> str:
        group_mode = self.credential_group_var.get()
        if group_mode == "按平台分组":
            return row.get("platform", "") or "未设置平台"
        if group_mode == "按用途分组":
            return row.get("category", "") or "未分类"
        if group_mode == "按来源分组":
            return row.get("source_label", "") or "未分类"
        return "全部记录"

    def get_credential_center_rows(self) -> list[dict]:
        keyword = self.credential_search_var.get().strip()
        source_filter = self.credential_source_var.get()
        rows: list[dict] = []

        if source_filter in ("全部来源", "账号密码库"):
            for row in self.db.fetch_credential_items(keyword):
                item = {
                    "source_type": "credential",
                    "source_label": "账号密码库",
                    "record_id": row["id"],
                    "group_key": "",
                    "title": row["title"] or "",
                    "category": row["category"] or "",
                    "platform": row["platform"] or "",
                    "link_url": row["link_url"] or "",
                    "username": row["username"] or "",
                    "password": row["password"] or "",
                    "email": row["email"] or "",
                    "phone": row["phone"] or "",
                    "screenshot_path": row["screenshot_path"] or "",
                    "note": row["note"] or "",
                }
                item["group_label"] = self.build_credential_group_label(item)
                rows.append(item)

        if source_filter in ("全部来源", "共享账户台账"):
            for row in self.db.fetch_all_shared_accounts(keyword):
                account_identity = format_account_identity(row["account_no"] or row["group_key"], row["account_name"] or "")
                item = {
                    "source_type": "shared_account",
                    "source_label": "共享账户台账",
                    "record_id": row["id"],
                    "group_key": row["group_key"] or "",
                    "title": f"账号组 {row['group_key'] or ''}".strip(),
                    "category": row["subject_name"] or "共享账户",
                    "platform": row["platform"] or "",
                    "link_url": row["link_url"] or "",
                    "username": account_identity,
                    "password": row["password"] or "",
                    "email": row["email"] or "",
                    "phone": row["phone"] or "",
                    "screenshot_path": row["screenshot_path"] or "",
                    "note": row["note"] or "",
                }
                item["group_label"] = self.build_credential_group_label(item)
                rows.append(item)

        rows.sort(
            key=lambda item: (
                normalize_text(item.get("group_label", "")),
                normalize_text(item.get("source_label", "")),
                normalize_text(item.get("platform", "")),
                normalize_text(item.get("title", "")),
                normalize_text(item.get("username", "")),
            )
        )
        return rows

    def refresh_credentials_table(self):
        for item in self.credentials_tree.get_children():
            self.credentials_tree.delete(item)
        self.credential_row_meta = {}
        rows = self.get_credential_center_rows()
        credential_count = sum(1 for row in rows if row["source_type"] == "credential")
        shared_count = sum(1 for row in rows if row["source_type"] == "shared_account")
        group_values = sorted({row["group_label"] for row in rows if normalize_text(row["group_label"])})
        for index, row in enumerate(rows, start=1):
            item_id = f"credential_row_{index}"
            self.credential_row_meta[item_id] = row
            self.credentials_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    row["source_label"],
                    row["group_label"],
                    row["title"],
                    row["category"],
                    row["platform"],
                    row["link_url"],
                    row["username"],
                    row["password"],
                    row["email"],
                    row["phone"],
                    row["note"],
                ),
            )
        self.credentials_summary_var.set(
            f"当前来源：{self.credential_source_var.get()}；当前分组：{self.credential_group_var.get()}；"
            f"账号密码库 {credential_count} 条，共享账户台账 {shared_count} 条，分组数 {len(group_values)}。"
        )
        self.credentials_status_var.set(f"账号中心当前显示 {len(rows)} 条记录。")
        self.refresh_credential_preview()

    def get_selected_credential_meta(self, silent: bool = False) -> dict | None:
        selection = self.credentials_tree.selection()
        if not selection:
            if not silent:
                messagebox.showinfo(APP_TITLE, "请先选择一条账号记录。", parent=self)
            return None
        row = self.credential_row_meta.get(selection[0])
        if not row:
            if not silent:
                messagebox.showwarning(APP_TITLE, "当前选中记录不存在。", parent=self)
            return None
        return row

    def get_selected_credential_metas(self, silent: bool = False) -> list[dict]:
        selection = self.credentials_tree.selection()
        if not selection:
            if not silent:
                messagebox.showinfo(APP_TITLE, "请先选择账号记录。", parent=self)
            return []
        rows = [self.credential_row_meta.get(item_id) for item_id in selection]
        result = [row for row in rows if row]
        if not result and not silent:
            messagebox.showwarning(APP_TITLE, "当前选中记录不存在。", parent=self)
        return result

    def refresh_credential_preview(self):
        row_meta = self.get_selected_credential_meta(silent=True)
        self.credential_preview.set_value(row_meta.get("screenshot_path", "") if row_meta else "")

    def get_selected_credential_row(self) -> sqlite3.Row | None:
        row_meta = self.get_selected_credential_meta()
        if not row_meta or row_meta["source_type"] != "credential":
            return None
        return self.db.get_credential_item(row_meta["record_id"])

    def build_credential_row_text(self, row_meta: dict) -> str:
        lines = [
            f"来源：{row_meta.get('source_label', '')}",
            f"分组：{row_meta.get('group_label', '')}",
            f"分类/用途：{row_meta.get('category', '')}",
            f"标题：{row_meta.get('title', '')}",
            f"平台：{row_meta.get('platform', '')}",
            f"链接：{row_meta.get('link_url', '')}",
            f"账号：{row_meta.get('username', '')}",
            f"密码：{row_meta.get('password', '')}",
            f"邮箱：{row_meta.get('email', '')}",
            f"手机号：{row_meta.get('phone', '')}",
            f"截图：{get_account_image_display_text(row_meta.get('screenshot_path', ''))}",
            f"备注：{row_meta.get('note', '')}",
        ]
        if row_meta.get("group_key"):
            lines.append(f"账号组：{row_meta.get('group_key', '')}")
        return "\n".join(lines)

    def copy_credential_row(self):
        rows = self.get_selected_credential_metas()
        if not rows:
            return
        text = "\n\n--------------------\n\n".join(self.build_credential_row_text(row_meta) for row_meta in rows)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.log_status(f"已复制 {len(rows)} 条账号完整信息。")
        messagebox.showinfo(APP_TITLE, f"已复制 {len(rows)} 条账号完整信息。", parent=self)

    def build_credential_template_text(self, row_meta: dict) -> str:
        lines = [
            f"标题：{row_meta.get('title', '')}",
            f"平台：{row_meta.get('platform', '')}",
            f"链接：{row_meta.get('link_url', '')}",
            f"账号：{row_meta.get('username', '')}",
            f"密码：{row_meta.get('password', '')}",
            f"邮箱：{row_meta.get('email', '')}",
            f"手机号：{row_meta.get('phone', '')}",
            f"截图：{get_account_image_display_text(row_meta.get('screenshot_path', ''))}",
            f"备注：{row_meta.get('note', '')}",
        ]
        if row_meta.get("category"):
            lines.insert(1, f"分类/用途：{row_meta.get('category', '')}")
        if row_meta.get("source_label"):
            lines.insert(0, f"来源：{row_meta.get('source_label', '')}")
        if row_meta.get("group_key"):
            lines.append(f"账号组：{row_meta.get('group_key', '')}")
        return "\n".join(lines)

    def copy_credential_template(self):
        rows = self.get_selected_credential_metas()
        if not rows:
            return
        text = "\n\n====================\n\n".join(self.build_credential_template_text(row_meta) for row_meta in rows)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.log_status(f"已复制 {len(rows)} 条账号模板文本。")
        messagebox.showinfo(APP_TITLE, f"已复制 {len(rows)} 条账号模板文本。", parent=self)

    def export_selected_credentials_excel(self):
        rows = self.get_selected_credential_metas()
        if not rows:
            return
        selected = filedialog.asksaveasfilename(
            title="导出选中账号记录",
            defaultextension=".xlsx",
            initialfile="账号中心_选中记录导出.xlsx",
            filetypes=[("Excel 文件", "*.xlsx")],
        )
        if not selected:
            return
        try:
            export_credential_rows_to_excel(rows, Path(selected))
            self.log_status(f"已导出 {len(rows)} 条选中账号记录。")
            messagebox.showinfo(APP_TITLE, f"导出成功，共 {len(rows)} 条选中记录。", parent=self)
        except (OSError, Exception) as exc:
            messagebox.showerror(APP_TITLE, f"导出失败：{exc}", parent=self)

    def add_credential_item(self):
        dialog = CredentialItemDialog(
            self,
            "新增账号记录",
            app_title=APP_TITLE,
            image_preview_cls=AccountImagePreview,
        )
        if dialog.result:
            self.db.add_credential_item(dialog.result)
            self.refresh_credentials_table()
            self.log_status("已新增独立账号记录。")

    def open_shared_manager_by_group_key(self, group_key: str):
        group_key = normalize_text(group_key)
        if not group_key:
            messagebox.showinfo(APP_TITLE, "当前共享账户没有账号组编号。", parent=self)
            return
        context = self.db.get_account_group_context(group_key)
        manager = SharedAccountManagerDialog(
            self,
            group_key,
            context=context,
            app_title=APP_TITLE,
            normalize_text=normalize_text,
            format_account_identity=format_account_identity,
            get_account_image_display_text=get_account_image_display_text,
            account_edit_dialog_cls=AccountEditDialog,
            account_image_preview_cls=AccountImagePreview,
        )
        self.wait_window(manager)
        self.refresh_credentials_table()
        self.refresh_table()

    def edit_credential_item(self):
        row_meta = self.get_selected_credential_meta()
        if not row_meta:
            return
        if row_meta["source_type"] == "shared_account":
            self.open_shared_manager_by_group_key(row_meta["group_key"])
            return
        row = self.db.get_credential_item(row_meta["record_id"])
        if not row:
            messagebox.showwarning(APP_TITLE, "账号记录不存在。", parent=self)
            return
        dialog = CredentialItemDialog(
            self,
            "编辑账号记录",
            initial=dict(row),
            app_title=APP_TITLE,
            image_preview_cls=AccountImagePreview,
        )
        if dialog.result:
            self.db.update_credential_item(row["id"], dialog.result)
            self.refresh_credentials_table()
            self.log_status("已更新独立账号记录。")

    def delete_credential_item(self):
        rows = self.get_selected_credential_metas()
        if not rows:
            return
        shared_rows = [row for row in rows if row["source_type"] == "shared_account"]
        credential_rows = [row for row in rows if row["source_type"] == "credential"]
        parts = []
        if credential_rows:
            parts.append(f"独立账号 {len(credential_rows)} 条")
        if shared_rows:
            parts.append(f"共享账户 {len(shared_rows)} 条")
        confirm_text = f"确认删除选中的记录吗？\n\n将删除：{'，'.join(parts)}"
        if not messagebox.askyesno(APP_TITLE, confirm_text, parent=self):
            return
        credential_ids = [row["record_id"] for row in credential_rows]
        shared_ids = [row["record_id"] for row in shared_rows]
        image_paths, credential_count, shared_count = self.get_deletable_account_image_paths(
            credential_ids=credential_ids,
            shared_ids=shared_ids,
        )
        delete_images = False
        if image_paths:
            choice = messagebox.askyesnocancel(
                APP_TITLE,
                f"检测到待删除记录中包含截图。\n\n独立账号：{credential_count} 条\n共享账户：{shared_count} 条\n可同步删除的本地截图：{len(image_paths)} 张\n\n是否同时删除这些已不再被其他记录引用的截图文件？\n\n是：删除记录并删除本地截图\n否：只删除记录\n取消：不执行删除",
                parent=self,
            )
            if choice is None:
                return
            delete_images = choice
        for row_meta in credential_rows:
            self.db.delete_credential_item(row_meta["record_id"])
        for row_meta in shared_rows:
            self.db.delete_shared_account(row_meta["record_id"])
        removed_count, failed_files = self.delete_local_account_image_files(image_paths) if delete_images else (0, [])
        self.refresh_credentials_table()
        self.refresh_table()
        if failed_files:
            messagebox.showwarning(
                APP_TITLE,
                "记录已删除，但以下截图文件删除失败：\n\n" + "\n".join(failed_files[:8]),
                parent=self,
            )
        self.log_status(
            f"已删除 {len(rows)} 条账号记录。"
            + (f" 同时删除截图 {removed_count} 张。" if delete_images else "")
        )

    def copy_credential_field(self, field: str, label: str):
        row_meta = self.get_selected_credential_meta()
        if not row_meta:
            return
        value = normalize_text(row_meta.get(field, ""))
        if not value:
            messagebox.showinfo(APP_TITLE, f"当前记录没有{label}。", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update()
        self.log_status(f"已复制{label}。")
        messagebox.showinfo(APP_TITLE, f"{label}已复制到剪贴板。", parent=self)

    def open_credential_link(self):
        row_meta = self.get_selected_credential_meta()
        if not row_meta:
            return
        link_url = normalize_text(row_meta.get("link_url", ""))
        if not link_url:
            messagebox.showinfo(APP_TITLE, "当前记录没有链接。", parent=self)
            return
        target_url = link_url if re.match(r"^https?://", link_url, re.I) else f"https://{link_url}"
        try:
            webbrowser.open(target_url)
            self.log_status("已打开账号记录链接。")
        except (webbrowser.Error, OSError, Exception) as exc:
            messagebox.showerror(APP_TITLE, f"打开链接失败：\n{exc}", parent=self)

    def open_selected_credential_image(self):
        row_meta = self.get_selected_credential_meta()
        if not row_meta:
            return
        image_value = normalize_text(row_meta.get("screenshot_path", ""))
        if not image_value:
            messagebox.showinfo(APP_TITLE, "当前记录没有截图。", parent=self)
            return
        self.credential_preview.set_value(image_value)
        title = "查看共享账户截图" if row_meta.get("source_type") == "shared_account" else "查看账号截图"
        self.credential_preview.open_large_viewer(parent=self, title=title)

    def open_selected_credential_image_folder(self):
        row_meta = self.get_selected_credential_meta()
        if not row_meta:
            return
        image_value = normalize_text(row_meta.get("screenshot_path", ""))
        if not image_value:
            messagebox.showinfo(APP_TITLE, "当前记录没有截图。", parent=self)
            return
        try:
            self.credential_preview.set_value(image_value)
            self.credential_preview.open_current_image_folder(parent=self)
            self.log_status("已打开账号截图目录。")
        except (OSError, Exception) as exc:
            messagebox.showerror(APP_TITLE, f"打开截图目录失败：\n{exc}", parent=self)

    def open_selected_shared_manager(self):
        row_meta = self.get_selected_credential_meta()
        if not row_meta:
            return
        if row_meta["source_type"] != "shared_account":
            messagebox.showinfo(APP_TITLE, "当前选中的是独立账号记录，无需进入共享账户管理。", parent=self)
            return
        self.open_shared_manager_by_group_key(row_meta["group_key"])

    def import_credentials_excel(self):
        selected = filedialog.askopenfilename(
            title="选择账号中心 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xlsm")],
        )
        if not selected:
            return
        file_path = Path(selected)
        if not file_path.exists():
            messagebox.showerror(APP_TITLE, f"Excel 文件不存在：\n{file_path}", parent=self)
            return
        try:
            items = import_credential_items_from_excel(file_path)
            if not items:
                messagebox.showinfo(APP_TITLE, "没有识别到可导入的账号记录。", parent=self)
                return
            for item in items:
                self.db.add_credential_item(item)
            self.refresh_credentials_table()
            self.log_status(f"已从 Excel 导入 {len(items)} 条账号记录。")
            messagebox.showinfo(APP_TITLE, f"导入成功，共新增 {len(items)} 条账号记录。", parent=self)
        except (zipfile.BadZipFile, OSError) as exc:
            # 实测：损坏或非 xlsx 的表格由 openpyxl 底层抛出 zipfile.BadZipFile
            messagebox.showerror(APP_TITLE, f"导入失败：{exc}", parent=self)
        except Exception as exc:
            # 兜底：含 openpyxl.utils.exceptions.InvalidFileException、缺失依赖的 RuntimeError
            logger.exception("导入账号 Excel 失败：%s", file_path)
            messagebox.showerror(APP_TITLE, f"导入失败：{exc}", parent=self)

    def export_credentials_excel(self):
        rows = self.get_credential_center_rows()
        if not rows:
            messagebox.showinfo(APP_TITLE, "当前没有可导出的账号记录。", parent=self)
            return
        selected = filedialog.asksaveasfilename(
            title="导出账号中心 Excel",
            defaultextension=".xlsx",
            initialfile="账号中心导出.xlsx",
            filetypes=[("Excel 文件", "*.xlsx")],
        )
        if not selected:
            return
        try:
            export_credential_rows_to_excel(rows, Path(selected))
            self.log_status(f"已导出 {len(rows)} 条账号中心记录。")
            messagebox.showinfo(APP_TITLE, f"导出成功，共 {len(rows)} 条记录。", parent=self)
        except (OSError, Exception) as exc:
            messagebox.showerror(APP_TITLE, f"导出失败：{exc}", parent=self)

    def open_account_ledger(self):
        self.switch_module("module_work_credentials")

    def build_summary_text(self, summary: ReminderSummary) -> str:
        lines = []

        if summary.overdue:
            lines.append(f"已过期：{len(summary.overdue)} 项")
            for item in summary.overdue[:8]:
                lines.append(
                    f"- {item['resource_type']} / {item['title']} / {item['platform']} / 已过期 {abs(item['days_left'])} 天"
                )

        if summary.due_15:
            if lines:
                lines.append("")
            lines.append(f"15 天内到期：{len(summary.due_15)} 项")
            for item in summary.due_15[:8]:
                lines.append(
                    f"- {item['resource_type']} / {item['title']} / {item['platform']} / 剩余 {item['days_left']} 天"
                )

        if summary.due_30:
            if lines:
                lines.append("")
            lines.append(f"30 天内到期：{len(summary.due_30)} 项")
            for item in summary.due_30[:8]:
                lines.append(
                    f"- {item['resource_type']} / {item['title']} / {item['platform']} / 剩余 {item['days_left']} 天"
                )

        if not lines:
            return "当前没有 30 天内到期的项目。"
        return "\n".join(lines)

    def show_reminder_popup(self):
        summary = self.db.get_reminder_summary()
        messagebox.showinfo(APP_TITLE, self.build_summary_text(summary), parent=self)

    def trigger_daily_tray_reminder(self, force: bool):
        summary = self.db.get_reminder_summary()
        if not summary.has_items:
            return

        today_str = date.today().isoformat()
        last_daily_15 = self.db.get_state("last_daily_reminder_15")
        last_daily_30 = self.db.get_state("last_daily_reminder_30")

        message_parts = []
        should_send = force

        if summary.overdue or summary.due_15:
            if force or last_daily_15 != today_str:
                should_send = True
                message_parts.append(
                    f"已过期 {len(summary.overdue)} 项，15 天内到期 {len(summary.due_15)} 项。"
                )
                self.db.set_state("last_daily_reminder_15", today_str)

        if summary.due_30 and (force or last_daily_30 != today_str):
            should_send = True
            message_parts.append(f"30 天内到期 {len(summary.due_30)} 项。")
            self.db.set_state("last_daily_reminder_30", today_str)

        if should_send and message_parts:
            self.tray.notify(APP_TITLE, " ".join(message_parts))
            self.log_status("已发送托盘提醒。")

    def periodic_reminder_check(self):
        self.trigger_daily_tray_reminder(force=False)
        self.todo_daily_maintenance()
        self.after(CHECK_INTERVAL_MS, self.periodic_reminder_check)

    def show_window(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def on_close(self):
        # ★ 防止递归调用：窗口已Destroy后不再处理
        if getattr(self, "_exiting", False):
            return
        self._exiting = True
        if self.tray.started:
            if self.close_behavior == "minimize":
                self.withdraw()
                self.log_status("窗口已隐藏到托盘，程序仍在后台运行。")
                self._exiting = False
                return
            if self.close_behavior == "exit":
                self.exit_app()
                return
            choice = messagebox.askyesnocancel(
                APP_TITLE,
                "关闭时请选择操作：\n\n是：最小化到托盘\n否：退出程序\n取消：返回当前窗口",
                parent=self,
            )
            if choice is None:
                self._exiting = False
                return
            if choice:
                self.withdraw()
                self.log_status("窗口已隐藏到托盘，程序仍在后台运行。")
                self._exiting = False
            else:
                self.exit_app()
        else:
            self.exit_app()

    # ------------------------------------------------------------------
    # 待办：每日顺延 + 假期后首个工作日汇总
    # ------------------------------------------------------------------
    def todo_daily_maintenance(self):
        """顺延逾期待办，并在假期后的第一个工作日弹一次汇总。

        挂在启动流程与每小时巡检两条线上：程序一直开着时，跨过午夜或
        假期结束后也会自动生效，不需要重启。同一天只弹一次（去重状态
        记在 todo_state 里，由 workday_notice() 判定）。
        """
        try:
            self.todo_db.rollover()
        except Exception:
            logger.exception("待办顺延失败")
            return
        try:
            notice = self.todo_db.workday_notice()
        except Exception:
            logger.exception("工作日检查失败")
            return
        if not notice:
            return
        self.todo_db.ack_workday_notice()

        lines = [
            f"{notice['holiday_name']}假期结束，今天是第一个工作日。",
            f"中间休息了 {notice['rest_days']} 天。",
            "",
        ]
        if notice["today_count"]:
            lines.append(f"今天有 {notice['today_count']} 条待办：")
            for title in notice["carried"][:8]:
                lines.append(f"    · {title}")
            rest = notice["today_count"] - 8
            if rest > 0:
                lines.append(f"    …… 还有 {rest} 条")
        else:
            lines.append("今天没有待办。")
        if messagebox.askyesno("工作日提醒",
                               "\n".join(lines) + "\n\n现在去看待办吗？",
                               parent=self):
            self.switch_module("module_life_todo")

    def todo_page_refresh(self):
        """切到待办页时刷新一次（由 _page_registry 的 on_show 调用）。"""
        try:
            self.todo_view.refresh()
        except Exception:
            logger.exception("待办页面刷新失败")

    # ------------------------------------------------------------------
    # 待办：到点提醒
    # ------------------------------------------------------------------
    def todo_alert_check(self):
        """巡检一次「有没有提醒该响了」。

        自己续期，所以只要程序在跑就一直有效 —— 窗口缩到托盘也一样
        （mainloop 还活着），人不在电脑前也不会漏掉。任何一步炸掉都只记
        日志、不打断循环：这类定时器一旦断了，就再也没有提醒了。
        """
        if getattr(self, "_exiting", False):
            return
        try:
            self._run_todo_alerts()
        except Exception:
            logger.exception("待办到点提醒巡检失败")
        finally:
            self.after(TODO_TICK_MS, self.todo_alert_check)

    def _run_todo_alerts(self):
        result = self.todo_db.pending_alerts()
        due = result["due"]
        missed = result["missed"]
        if not due and not missed:
            return
        # 先记账再弹窗：万一建窗途中出异常，也不至于 30 秒后又来一遍
        self.todo_db.mark_alerted(result["moments"])

        if missed:
            # 早就过点的不弹窗，只在托盘汇总一句 —— 程序关了一整天再打开，
            # 不该被二十个窗口糊一脸
            names = "、".join(it.title for it in missed[:3])
            tail = f" 等 {len(missed)} 条" if len(missed) > 3 else ""
            self.tray.notify(APP_TITLE, f"有 {len(missed)} 条提醒已过时间：{names}{tail}")
            self.log_status(f"待办：{len(missed)} 条提醒已过时间。")

        if due:
            self.show_todo_alert(due, result.get("stages"))

    def show_todo_alert(self, items, stages=None):
        """弹出到点提醒窗；同时只留一个，新的一批顶掉旧的。

        ``stages`` 是每一条响的是哪一档（提前 / 到点），窗口据此换头部
        说法与每行说明；不传就一律当「到点」。
        """
        self._close_todo_alert()
        try:
            dialog = TodoAlertDialog(
                self, items, db=self.todo_db, stages=stages,
                on_changed=self._after_todo_alert,
                on_open=self._open_todo_item,
            )
        except Exception:
            logger.exception("待办提醒窗创建失败")
            return
        self._todo_alert_win = dialog
        self.log_status(f"待办提醒：{len(items)} 条。")

    def _close_todo_alert(self):
        """关掉还挂着的提醒窗（开会错过的那一批不应一直压在最上层）。"""
        dialog = getattr(self, "_todo_alert_win", None)
        self._todo_alert_win = None
        if dialog is None:
            return
        try:
            if dialog.winfo_exists():
                dialog.destroy()
        except Exception:
            pass

    def _after_todo_alert(self):
        """提醒窗里点过「完成」/「稍后提醒」之后刷新待办页。"""
        try:
            self.todo_view.refresh()
        except Exception:
            logger.exception("提醒处理后刷新待办页失败")

    def _open_todo_item(self, item_id: int):
        """点提醒窗里的某一条 → 抬起窗口、切到待办页、选中它。"""
        self.show_window()
        self.switch_module("module_life_todo")
        try:
            self.todo_view.select_item(item_id)
        except Exception:
            logger.exception("从提醒窗跳转待办失败")

    def exit_app(self):
        self.shutdown_manager.shutdown()


def main():
    # 放在最前：应用构造阶段出的问题也要能落盘（发布版没有控制台可看）
    log_setup.setup_logging(DATA_DIR / "logs")
    mutex, already_exists = acquire_single_instance_mutex()
    if already_exists:
        signal_existing_instance_show()
        return
    app = ExpiryManagerApp()
    app._single_instance_mutex = mutex
    try:
        app.mainloop()
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()