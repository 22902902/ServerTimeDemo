# -*- coding: utf-8 -*-
"""
================================================================================
学习笔记模块 - 数据层（Data Layer）
================================================================================
本模块封装了"视频课程资料库"所需的全部数据库操作，采用 SQLite 共享主程序数据库。
数据库文件路径由调用方传入（与主程序共用同一个 .db 文件），因此所有表之间互不干扰。

┌─────────────────────────────────────────────────────────────────────────────┐
│  数据表设计                                                                   │
├──────────────────┬──────────────────────────────────────────────────────────┤
│ baidu_disk_      │ 百度网盘资料表：存储视频课程的网盘链接、提取码、标签、备注     │
│ sources                                                                  │
├──────────────────┼──────────────────────────────────────────────────────────┤
│ study_categories │ 三级分类表：采用图书馆式编码（01/0101/010101），支持父子层级 │
├──────────────────┼──────────────────────────────────────────────────────────┤
│ study_notes      │ 学习笔记表：标题、正文（Markdown）、所属分类、标签、来源关联  │
└──────────────────┴──────────────────────────────────────────────────────────┘

「锁定分类」是什么
------------------------------------------------------------------------------
study_categories 上多了两列：

    locked      1 = 系统占用的分类，界面禁止改名 / 删除（例：「Excel 宝典」）
    source_key  锁定分类的归属标识（例："excel"），用来幂等地找回同一个分类

为什么要锁：有些分类是**别的模块的地盘** —— 「Excel 宝典」把一轮自测整理成
笔记模板，落在它自己的分类里。用户可以照常在自己的分类下随便增删改，但这个
地盘不能被改名或删掉（删了另一头就找不到落点）。锁定**只约束它自己**，
不影响任何其他分类 / 笔记的新增。

生成区标记
------------------------------------------------------------------------------
笔记正文里可以有一对被 HTML 注释圈起来的「自动生成」段落（见 GEN_START /
GEN_END）。渲染器认这对标记，把圈内的文字换成另一套样式 —— 于是「系统生成的」
和「你自己写的」在颜色、字体、排版上一眼能分开；重新生成时也只覆盖圈内，
圈外「我的补充」一个字都不会动。

作者：代可行
日期：2026-07-14
================================================================================
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import db_backup


# =============================================================================
# 辅助函数
# =============================================================================

def _norm(text) -> str:
    """
    将任意值规范化为非空字符串。
    用于从数据库读取字段时统一做 strip() 处理，避免 None 或多余空格导致的问题。

    参数:
        text: 任意类型的输入值
    返回:
        去除首尾空格后的字符串；输入为 None 时返回空字符串
    """
    if text is None:
        return ""
    return str(text).strip()


def _now() -> str:
    """
    返回当前时间的 ISO 格式字符串（精确到秒），用于 created_at / updated_at 字段。
    示例: "2026-07-14T11:30:00"
    """
    return datetime.now().isoformat(timespec="seconds")


# =============================================================================
# 笔记正文的「生成区」标记
# =============================================================================

# 有些笔记是系统生成的模板（「Excel 宝典」把一轮自测整理成一页）。正文里用
# 一对 HTML 注释把「自动生成的那一段」圈起来：
#
#   * 重新生成时**只覆盖这一对标记之间**的内容，标记之外的「我的补充」原样
#     保留 —— 用户二创过的东西永远不会被冲掉；
#   * markdown_view 认这对标记，把圈内的文字换成另一套样式（冷色底 / 宋体 /
#     缩进 / 小一号字），于是「生成的」和「自己写的」在颜色、字体、排版上
#     一眼能分开；
#   * 为什么是 HTML 注释：它在 Markdown 里天然不可见，复制到别处不会显示成
#     乱码，也不依赖任何渲染器扩展（多数 Markdown 实现都会忽略注释）。
#
# ★ 这两个字符串会随笔记正文**落库**。改一次就等于让所有老笔记的标记失配
#   （渲染器认不出、重新生成会把用户的补充当成生成区冲掉），所以视为永久
#   常量：真要改，必须同时提供一次全库迁移。
GEN_START = "<!-- gen:start -->"
GEN_END = "<!-- gen:end -->"


# =============================================================================
# 数据模型（Data Classes）
# =============================================================================

# 为方便 IDE 和读者理解，每个 dataclass 独立成块，包含完整的字段说明。
# 这些类均实现了 from_row() 类方法，负责将 sqlite3.Row 对象转换为实体实例。

@dataclass
class BaiduDiskSource:
    """
    百度网盘资料实体。

    字段说明:
        id           - 主键，自增整数
        title        - 资料标题（如"Python 进阶视频完整版"）
        link_url     - 百度网盘分享链接（支持 https://pan.baidu.com/... 格式）
        access_code  - 提取码（4位字母数字，如 "abcd"）
        tags         - 标签列表（用于检索，如 ["Python", "进阶", "2024"]）
        note         - 备注，可填写补充说明
        created_at   - 创建时间（ISO 格式）
        updated_at   - 最后修改时间（ISO 格式）
    """
    id: int = 0
    title: str = ""
    link_url: str = ""
    access_code: str = ""
    tags: list[str] = field(default_factory=list)
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    def tags_str(self) -> str:
        """
        将标签列表格式化为空格分隔的字符串，用于在表格列中显示。
        示例: ["Python", "进阶"] → "Python 进阶"
        """
        return " ".join(self.tags)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "BaiduDiskSource":
        """
        将数据库查询返回的 sqlite3.Row 对象转换为 BaiduDiskSource 实例。
        自动处理 tags 字段的 JSON 解析（兼容旧版本可能存储的字符串格式）。

        参数:
            row: sqlite3.Row 对象，来源于 SELECT * 查询
        返回:
            BaiduDiskSource 实体
        """
        tags_raw = row["tags"]

        # tags 字段在数据库中以 JSON 数组字符串存储（如 '["Python","进阶"]'）
        # 这里兼容三种情况：JSON 字符串、已解析的列表、其他异常
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except Exception:
                # 解析失败时按空格分割（兼容旧数据）
                tags = tags_raw.split() if tags_raw else []
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []

        return cls(
            id=int(row["id"]),
            title=_norm(row["title"]),
            link_url=_norm(row["link_url"]),
            access_code=_norm(row["access_code"]),
            tags=tags,
            note=_norm(row["note"]),
            created_at=_norm(row["created_at"]),
            updated_at=_norm(row["updated_at"]),
        )


@dataclass
class StudyCategory:
    """
    三级分类实体，采用图书馆式层次编码。

    编码规则:
        一级（大类）: 2 位数字，范围 01~99        示例: 01 技术、02 烹饪、03 健身
        二级（中类）: 4 位数字，前缀为父级代码       示例: 0101 编程语言、0102 前端技术
        三级（小类）: 6 位数字，前缀为父级代码       示例: 010101 Python、010102 JavaScript

    字段说明:
        id          - 主键，自增整数
        code        - 分类编码（全局唯一，如 "0101"）
        name        - 分类名称（如 "编程语言"）
        parent_code - 父级编码；顶级分类此字段为空字符串 ""
        level       - 层级深度：1=一级、2=二级、3=三级
        sort_order  - 同级排序序号，数字越小越靠前
        locked      - 1=系统锁定分类（界面禁止改名 / 删除），0=用户自己的分类
        source_key  - 锁定分类的归属标识（如 "excel"）；普通分类为空
        created_at  - 创建时间
        updated_at  - 最后修改时间

    关于 locked / source_key：这两个字段在老库里是**后加的**（见
    `_ensure_category_columns`），因此 `from_row` 对缺失列做了兜底 ——
    读不到就当「普通分类」，不会因为列不存在而炸。
    """
    id: int = 0
    code: str = ""
    name: str = ""
    parent_code: str = ""
    level: int = 1  # 1=一级 2=二级 3=三级
    sort_order: int = 0
    locked: int = 0
    source_key: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "StudyCategory":
        """
        将 sqlite3.Row 转换为 StudyCategory 实例。
        """
        # 老库可能还没有 locked / source_key 两列，用 keys() 判断再取，
        # 免得直接 row["locked"] 抛 IndexError。
        keys = row.keys()
        return cls(
            id=int(row["id"]),
            code=_norm(row["code"]),
            name=_norm(row["name"]),
            parent_code=_norm(row["parent_code"]),
            # 数据库中 level/sort_order 可能存为 NULL，做安全默认值兜底
            level=int(row["level"]) if row["level"] is not None else 1,
            sort_order=int(row["sort_order"]) if row["sort_order"] is not None else 0,
            locked=(int(row["locked"] or 0) if "locked" in keys else 0),
            source_key=(_norm(row["source_key"]) if "source_key" in keys else ""),
            created_at=_norm(row["created_at"]),
            updated_at=_norm(row["updated_at"]),
        )


@dataclass
class StudyNote:
    """
    学习笔记实体，核心内容载体。

    字段说明:
        id            - 主键，自增整数
        category_code - 所属分类编码（如 "0101"）；删除分类后置为空
        category_name - 所属分类名称（冗余存储，仅用于列表展示加速）
        title         - 笔记标题（必填）
        content       - 笔记正文，支持完整 Markdown 语法
        tags          - 标签列表
        source_id     - 关联的百度网盘资料 ID；0 表示无来源
        created_at    - 创建时间
        updated_at    - 最后修改时间（用于排序）
    """
    id: int = 0
    category_code: str = ""
    category_name: str = ""
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    source_id: int = 0
    created_at: str = ""
    updated_at: str = ""

    def tags_str(self) -> str:
        """将标签列表转为空格分隔字符串，用于表格列显示。"""
        return " ".join(self.tags)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "StudyNote":
        """
        将 sqlite3.Row 转换为 StudyNote 实例。
        tags 字段兼容 JSON 数组和逗号分隔字符串两种存储格式。
        """
        tags_raw = row["tags"]
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except Exception:
                # 逗号分隔格式兜底（如 "Python,进阶,2024"）
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []

        return cls(
            id=int(row["id"]),
            category_code=_norm(row["category_code"]),
            category_name=_norm(row["category_name"]),
            title=_norm(row["title"]),
            content=_norm(row["content"]),
            tags=tags,
            source_id=int(row["source_id"]) if row["source_id"] is not None else 0,
            created_at=_norm(row["created_at"]),
            updated_at=_norm(row["updated_at"]),
        )


# =============================================================================
# 数据库操作类
# =============================================================================

class StudyNotesDB:
    """
    学习笔记模块的数据库操作类。

    设计说明:
        - 复用主程序的 SQLite 数据库文件（传入 db_path），与主程序共享连接。
          这样数据存储在同一文件中，方便统一管理（备份、迁移等）。
        - check_same_thread=False 允许多线程安全访问（主程序 UI 线程与后台任务可能并发）。
        - PRAGMA foreign_keys = ON 开启外键约束，保证关联数据的完整性。
        - 数据库文件路径通过 __init__ 注入，类本身不依赖任何硬编码路径。

    使用示例:
        from study_notes_db import StudyNotesDB
        db = StudyNotesDB("C:/data/app.db")
        notes = db.fetch_notes(keyword="Python")
        db.close()  # 程序退出时调用
    """

    def __init__(self, db_path: Path):
        """
        初始化数据库连接，创建表结构，填充默认分类。

        参数:
            db_path: 主程序数据库文件路径（Path 对象），会在同级目录下创建
                     study_notes_images 子目录存放笔记截图。
        """
        self.db_path = db_path
        # check_same_thread=False：允许不同线程共用同一连接（Tkinter UI 线程 + 可能的后台线程）
        self.conn = db_backup.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 开启列名索引（row["column_name"]）
        self.conn.execute("PRAGMA foreign_keys = ON")  # 开启外键级联
        self.create_tables()    # 建表（如已存在则忽略）
        self._migrate_code_constraint()  # 迁移：放宽 code 长度限制到 8 位（支持四级分类）
        self._ensure_category_columns()  # 迁移：补齐 locked / source_key 两列
        self.seed_default_categories()  # 填充预设分类（仅首次）

    # --------------------------------------------------------------------------
    # 表结构
    # --------------------------------------------------------------------------

    # 「锁定分类」相关的两列。老库建表时没有它们，用 ALTER TABLE 补上。
    # 声明放在这里而不是散在方法里，是为了让「表到底有哪些列」一眼可见。
    CATEGORY_EXTRA_COLUMNS = {
        "locked": "INTEGER NOT NULL DEFAULT 0",
        "source_key": "TEXT NOT NULL DEFAULT ''",
    }

    def _ensure_category_columns(self):
        """迁移：给 study_categories 补上 locked / source_key 两列。

        SQLite 的 ALTER TABLE ADD COLUMN 可以带 NOT NULL，只要给了非空默认值。
        幂等：已经有的列直接跳过，所以每次启动跑一遍没有副作用。

        失败一律吞掉不阻断启动：真读不到这两列时 `StudyCategory.from_row` 会把
        它们当默认值（普通分类），分类树照样能用，只是「锁定」失效。
        """
        try:
            existing = {row["name"] for row in self.conn.execute(
                "PRAGMA table_info(study_categories)"
            ).fetchall()}
        except Exception:
            return  # 表都读不出信息，交给上层去报错
        for column, declaration in self.CATEGORY_EXTRA_COLUMNS.items():
            if column in existing:
                continue
            try:
                self.conn.execute(
                    f"ALTER TABLE study_categories ADD COLUMN {column} {declaration}"
                )
            except Exception:
                pass  # 加不上就退回「普通分类」，不影响笔记本身
        self.conn.commit()


    def create_tables(self):
        """
        创建本模块所需的三张表（IF NOT EXISTS，故重复调用安全）。

        表设计要点:
        - tags 列统一存 JSON 字符串，便于跨语言解析和扩展。
        - source_id = 0 表示无来源，不使用 NULL（简化 JavaScript 等外部处理逻辑）。
        - 所有 TEXT 字段默认 NOT NULL，防止空值带来的空字符串 vs NULL 判断问题。
        """
        self.conn.executescript("""
            /* 百度网盘资料表：存储所有视频课程的网盘分享链接 */
            CREATE TABLE IF NOT EXISTS baidu_disk_sources (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,       -- 资料标题（唯一标识，不可为空）
                link_url    TEXT    DEFAULT '',      -- 百度网盘分享 URL
                access_code TEXT    DEFAULT '',      -- 提取码（通常为4位）
                tags        TEXT    DEFAULT '[]',   -- 标签 JSON 数组
                note        TEXT    DEFAULT '',      -- 备注/补充说明
                created_at  TEXT    NOT NULL,       -- 创建时间（ISO 格式）
                updated_at  TEXT    NOT NULL        -- 更新时间（ISO 格式）
            );

            /* 分类表：三级树状结构，支持任意层级扩展 */
            CREATE TABLE IF NOT EXISTS study_categories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT    NOT NULL UNIQUE, -- 分类编码（如 0101），全局唯一
                name        TEXT    NOT NULL,        -- 分类名称
                parent_code TEXT    DEFAULT '',       -- 父级编码；空=顶级分类
                level       INTEGER NOT NULL DEFAULT 1, -- 层级深度：1/2/3
                sort_order  INTEGER NOT NULL DEFAULT 0, -- 同级排序号
                locked      INTEGER NOT NULL DEFAULT 0, -- 1=系统锁定分类（界面禁止改名/删除）
                source_key  TEXT    NOT NULL DEFAULT '', -- 锁定分类的归属标识（如 excel）
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL,
                CHECK (length(code) >= 2 AND length(code) <= 8)
            );

            /* 学习笔记表：Markdown 正文 + 分类 + 标签 + 来源关联 */
            CREATE TABLE IF NOT EXISTS study_notes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                category_code TEXT    NOT NULL DEFAULT '',   -- 所属分类编码
                category_name TEXT    DEFAULT '',            -- 分类名称（冗余存储，展示用）
                title         TEXT    NOT NULL,            -- 笔记标题
                content       TEXT    DEFAULT '',           -- Markdown 正文
                tags          TEXT    DEFAULT '[]',        -- 标签 JSON 数组
                source_id     INTEGER NOT NULL DEFAULT 0,  -- 关联百度网盘资料 ID
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            );
        """)
        self.conn.commit()

    # --------------------------------------------------------------------------
    def _migrate_code_constraint(self):
        """
        迁移：将 study_categories 表的 code 长度限制从 6 位放宽到 8 位。
        SQLite 不支持直接修改 CHECK 约束，需要重建表。
        """
        try:
            # 检查当前约束是否已经是 8 位
            row = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='study_categories'"
            ).fetchone()
            if not row or row["sql"] is None:
                return  # 表不存在，无需迁移
            
            current_sql = row["sql"]
            # 如果约束已经是 <= 8，跳过
            if "<= 8" in current_sql:
                return
            
            # 需要迁移：重建表
            self.conn.execute("BEGIN TRANSACTION")
            try:
                # 1. 创建新表
                self.conn.execute("""
                    CREATE TABLE study_categories_new (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        code        TEXT    NOT NULL UNIQUE,
                        name        TEXT    NOT NULL,
                        parent_code TEXT    DEFAULT '',
                        level       INTEGER NOT NULL DEFAULT 1,
                        sort_order  INTEGER NOT NULL DEFAULT 0,
                        locked      INTEGER NOT NULL DEFAULT 0,
                        source_key  TEXT    NOT NULL DEFAULT '',
                        created_at  TEXT    NOT NULL,
                        updated_at  TEXT    NOT NULL,
                        CHECK (length(code) >= 2 AND length(code) <= 8)
                    )
                """)
                # 2. 复制数据。★ 必须**显式列名**，不能 `SELECT *`：
                #    新表比老表多 locked / source_key 两列，按位置搬会对不上。
                self.conn.execute("""
                    INSERT INTO study_categories_new
                        (id, code, name, parent_code, level, sort_order,
                         created_at, updated_at)
                    SELECT id, code, name, parent_code, level, sort_order,
                           created_at, updated_at
                      FROM study_categories
                """)
                # 3. 删除旧表
                self.conn.execute("DROP TABLE study_categories")
                # 4. 重命名新表
                self.conn.execute("ALTER TABLE study_categories_new RENAME TO study_categories")
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        except Exception:
            # 迁移失败不阻断程序启动
            pass

    # 预设分类种子
    # --------------------------------------------------------------------------

    # 预设三级分类结构：
    #   大类(2位) → 中类(4位) → 小类(6位)
    # 用户可在程序内新增、编辑、删除任意分类。
    DEFAULT_CATEGORIES = [
        # ── 01 技术 ──────────────────────────────────────────────────────
        ("01",  "技术",    "",                   1, 1),
        ("0101", "编程语言",  "01",                2, 1),
        ("0102", "前端技术",  "01",                2, 2),
        ("0103", "后端技术",  "01",                2, 3),
        ("0104", "数据库",   "01",                2, 4),
        ("0105", "DevOps",  "01",                2, 5),
        # ── 02 烹饪 ──────────────────────────────────────────────────────
        ("02",  "烹饪",    "",                   1, 2),
        ("0201", "中餐",    "02",                2, 1),
        ("0202", "西餐",    "02",                2, 2),
        ("0203", "烘焙",    "02",                2, 3),
        ("0204", "饮品",    "02",                2, 4),
        # ── 03 健身 ──────────────────────────────────────────────────────
        ("03",  "健身",    "",                   1, 3),
        ("0301", "增肌",    "03",                2, 1),
        ("0302", "减脂",    "03",                2, 2),
        ("0303", "体能",    "03",                2, 3),
        # ── 04 设计 ──────────────────────────────────────────────────────
        ("04",  "设计",    "",                   1, 4),
        ("0401", "平面设计",  "04",                2, 1),
        ("0402", "UI/UX",   "04",                2, 2),
        # ── 05 语言 ──────────────────────────────────────────────────────
        ("05",  "语言",    "",                   1, 5),
        ("0501", "英语",    "05",                2, 1),
        ("0502", "日语",    "05",                2, 2),
        # ── 06 理财 ──────────────────────────────────────────────────────
        ("06",  "理财",    "",                   1, 6),
        # ── 07 摄影 ──────────────────────────────────────────────────────
        ("07",  "摄影",    "",                   1, 7),
        # ── 08 生活 ──────────────────────────────────────────────────────
        ("08",  "生活",    "",                   1, 8),
    ]

    def seed_default_categories(self):
        """
        首次初始化时填充 DEFAULT_CATEGORIES 预设分类。
        如果数据库中已有分类数据（用户自行添加过），则跳过，避免重复插入。
        """
        existing_count = self.conn.execute(
            "SELECT COUNT(1) FROM study_categories"
        ).fetchone()[0]
        if existing_count > 0:
            return  # 已有分类，不重复填充

        now = _now()
        records = [
            (code, name, parent_code, level, sort_order, now, now)
            for code, name, parent_code, level, sort_order in self.DEFAULT_CATEGORIES
        ]
        self.conn.executemany(
            """INSERT INTO study_categories
               (code, name, parent_code, level, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            records
        )
        self.conn.commit()

    # --------------------------------------------------------------------------
    # 分类 CRUD（增删改查）
    # --------------------------------------------------------------------------

    def fetch_all_categories(self) -> list[StudyCategory]:
        """
        获取所有分类，按 层级 → 排序号 → 编码 排序。
        用于渲染左侧分类树，确保父节点在子节点之前出现。
        """
        rows = self.conn.execute(
            "SELECT * FROM study_categories "
            "ORDER BY level ASC, sort_order ASC, code ASC"
        ).fetchall()
        return [StudyCategory.from_row(r) for r in rows]

    def get_category(self, cat_id: int) -> Optional[StudyCategory]:
        """根据分类主键 ID 获取单条分类记录。"""
        row = self.conn.execute(
            "SELECT * FROM study_categories WHERE id = ?", (cat_id,)
        ).fetchone()
        return StudyCategory.from_row(row) if row else None

    def get_category_by_code(self, code: str) -> Optional[StudyCategory]:
        """根据分类编码获取单条分类记录（用于新增子分类时查找父分类）。"""
        row = self.conn.execute(
            "SELECT * FROM study_categories WHERE code = ?", (code,)
        ).fetchone()
        return StudyCategory.from_row(row) if row else None

    def get_children_categories(self, parent_code: str) -> list[StudyCategory]:
        """
        获取指定父编码下的所有直接子分类。
        用于删除分类时统计子分类数量，以及渲染树时获取子节点列表。
        """
        rows = self.conn.execute(
            "SELECT * FROM study_categories "
            "WHERE parent_code = ? ORDER BY sort_order ASC, code ASC",
            (parent_code,)
        ).fetchall()
        return [StudyCategory.from_row(r) for r in rows]

    def add_category(self, code: str, name: str, parent_code: str = "",
                     level: int = 1, sort_order: int = 0,
                     locked: int = 0, source_key: str = ""):
        """
        新增一条分类记录。

        参数:
            code       - 分类编码（如 "0106"），需唯一，建议由 get_next_category_code() 生成
            name       - 分类名称（如 "人工智能"）
            parent_code- 父级编码；空字符串表示顶级分类
            level      - 层级：1=一级、2=二级、3=三级
            sort_order - 同级排序序号
            locked     - 1=系统锁定分类（界面禁止改名 / 删除）
            source_key - 锁定分类的归属标识；普通分类留空

        ``locked`` / ``source_key`` 平时不用手填 —— 外部模块走
        `ensure_locked_category` 就够了。
        """
        now = _now()
        self.conn.execute(
            """INSERT INTO study_categories
               (code, name, parent_code, level, sort_order, locked, source_key,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, name, parent_code, level, sort_order, int(locked or 0),
             _norm(source_key), now, now),
        )
        self.conn.commit()

    def update_category(self, cat_id: int, name: str, sort_order: int = 0) -> bool:
        """
        更新分类名称和排序号（不支持修改编码和层级，防止树结构被意外破坏）。

        参数:
            cat_id     - 分类主键 ID
            name       - 新的分类名称
            sort_order - 新的排序号

        返回:
            True = 改成功；False = 被拒绝（分类不存在，或是锁定分类）

        ★ 锁定分类**改不动**：它是别的模块的落点，名字被改掉之后那头的说明
        就跟界面文字对不上了。要在数据层拦一道，因为界面上的按钮状态可能
        被别处的刷新改掉 —— 界面拦是提示，这里拦才是保证。
        """
        cat = self.get_category(cat_id)
        if not cat or cat.locked:
            return False
        now = _now()
        self.conn.execute(
            "UPDATE study_categories SET name=?, sort_order=?, updated_at=? WHERE id=?",
            (name, sort_order, now, cat_id),
        )
        self.conn.commit()
        return True

    def delete_category(self, cat_id: int) -> tuple[int, int]:
        """
        删除指定分类，并处理关联影响：
          1. 该分类下所有笔记的 category_code 和 category_name 置为空（移至"未分类"）
          2. 删除所有直接子分类（一级）
          3. 删除自身

        注意：此方法不递归删除多级子分类（当前系统仅支持三级，故影响可控）。
              若未来扩展为任意层级，建议改为递归删除。

        返回:
            (受影响的笔记数量, 被删除的子分类数量)

        参数:
            cat_id - 分类主键 ID

        ★ 锁定分类不删，直接返回 (0, 0) —— 与「分类不存在」同一个返回值。
        界面会先看 `cat.locked` 给出人话提示，这里只是最后一道保险：
        哪怕界面判断漏了，也不会把别的模块的落点删掉。
        """
        cat = self.get_category(cat_id)
        if not cat or cat.locked:
            return 0, 0

        # ① 统计即将受影响的笔记和子分类数量
        note_count = self.conn.execute(
            "SELECT COUNT(1) FROM study_notes WHERE category_code = ?",
            (cat.code,)
        ).fetchone()[0]
        child_count = self.conn.execute(
            "SELECT COUNT(1) FROM study_categories WHERE parent_code = ?",
            (cat.code,)
        ).fetchone()[0]

        # ② 将归属此分类的笔记移至"未分类"（不删除笔记内容）
        self.conn.execute(
            "UPDATE study_notes SET category_code='', category_name='' WHERE category_code=?",
            (cat.code,)
        )

        # ③ 删除所有直接子分类
        self.conn.execute(
            "DELETE FROM study_categories WHERE parent_code = ?",
            (cat.code,)
        )

        # ④ 删除自身
        self.conn.execute(
            "DELETE FROM study_categories WHERE id = ?",
            (cat_id,)
        )

        self.conn.commit()
        return note_count, child_count

    def get_next_category_code(self, parent_code: str = "") -> str:
        """
        自动生成下一个可用的分类编码。

        规则：
          - 父分类为空（顶级）→ 取现有最大编码的前两位 + 1，格式化为 2 位（如 "09"）
          - 父分类非空（二/三级）→ 取现有最大编码的后两位 + 1，拼在父编码后（如父="01" → "0106"）

        示例：
          parent_code="" → 当前最大一级编码为 "08" → 返回 "09"
          parent_code="01" → 当前最大二级编码为 "0105" → 返回 "0106"

        这确保了新增分类时编码不会重复，同时保持编码的连续性。

        ★ **只认纯数字编码**。锁定分类有可能落到字母兜底码（如 "L09"，
        见 `_free_top_code`），旧写法 `int(last_code[:2])` 撞上它会直接
        ValueError —— 表现是「点新增分类没反应 / 弹报错」，而且只有装了
        锁定分类的机器才会遇到。所以这里把同级编码全捞回来自己挑数字，
        非数字的一律跳过。

        参数:
            parent_code - 父级编码；空字符串表示顶级分类
        """
        rows = self.conn.execute(
            "SELECT code FROM study_categories WHERE parent_code = ?",
            (parent_code or "",),
        ).fetchall()
        codes = [_norm(row["code"]) for row in rows]

        if not parent_code:
            # 顶级分类：只看长度 2 且全数字的编码
            numbers = [int(c) for c in codes if len(c) == 2 and c.isdigit()]
            return f"{max(numbers) + 1:02d}" if numbers else "01"

        # 子分类：只看「父编码 + 两位数字」这种形状
        numbers = []
        for code in codes:
            if not code.startswith(parent_code):
                continue
            tail = code[len(parent_code):]
            if len(tail) == 2 and tail.isdigit():
                numbers.append(int(tail))
        if numbers:
            return parent_code + f"{max(numbers) + 1:02d}"
        return parent_code + "01"

    # --------------------------------------------------------------------------
    # 锁定分类（系统占用的分类）
    # --------------------------------------------------------------------------

    def find_category_by_source_key(self, source_key: str) -> Optional[StudyCategory]:
        """按归属标识找回锁定分类；没有就返回 None。

        为什么不按编码找：编码只是主键，谁先占了就是谁的。外部模块认的是
        ``source_key``（如 "excel"），换台机器 / 换个编码都还能找回同一个分类。
        """
        key = _norm(source_key)
        if not key:
            return None
        row = self.conn.execute(
            "SELECT * FROM study_categories WHERE source_key = ? LIMIT 1", (key,)
        ).fetchone()
        return StudyCategory.from_row(row) if row else None

    def _free_top_code(self) -> str:
        """挑一个没被占用的顶级分类编码。

        从 "09" 往上找（预设分类只到 "08"）。全占满（90 个顶级分类，
        基本不可能）时退回字母码 —— `get_next_category_code` 会跳过它。
        """
        taken = {
            _norm(row["code"])
            for row in self.conn.execute(
                "SELECT code FROM study_categories WHERE parent_code = ''"
            ).fetchall()
        }
        for number in range(9, 100):
            code = f"{number:02d}"
            if code not in taken:
                return code
        return f"L{len(taken):02d}"

    def ensure_locked_category(self, *, source_key: str, name: str,
                               sort_order: int = 90) -> str:
        """幂等地拿到（必要时创建）一个锁定分类，返回它的编码。

        **按 source_key 找人**：找到就返回原编码，顺带把它重新标成 locked
        （万一被别的手段改回过）；找不到才新建一个。

        ``sort_order`` 默认 90：预设分类排 1~8，锁定分类落在末尾 —— 它是
        「系统地盘」，压在用户自己的分类下面比顶在最上面合适。

        这套「先查后建」是幂等的关键：同一个模块被初始化两次、或者用户连点
        两下按钮，都只会有一个分类。
        """
        key = _norm(source_key)
        if not key:
            raise ValueError("source_key 不能为空 —— 没有它就没法幂等地找回分类")
        existing = self.find_category_by_source_key(key)
        if existing:
            if not existing.locked:
                # 曾经被手工改回过：这里补一道，别再让它能被删掉
                self.conn.execute(
                    "UPDATE study_categories SET locked = 1 WHERE id = ?",
                    (existing.id,),
                )
                self.conn.commit()
            return existing.code
        code = self._free_top_code()
        self.add_category(code=code, name=_norm(name) or key, parent_code="",
                          level=1, sort_order=int(sort_order),
                          locked=1, source_key=key)
        return code

    # --------------------------------------------------------------------------
    # 笔记 CRUD
    # --------------------------------------------------------------------------

    def fetch_notes(
        self,
        keyword: str = "",
        category_code: str = "",
        tags: Optional[list[str]] = None,
    ) -> list[StudyNote]:
        """
        获取笔记列表，支持关键词搜索、分类过滤和标签过滤，结果按更新时间倒序。

        搜索范围：
          - keyword：模糊匹配标题（title）、正文（content）、标签（tags）三列
          - category_code：精确匹配该分类及其所有子分类（LIKE prefix%）
          - tags：列表中任意一个标签命中即保留（在 Python 层面过滤）

        参数:
            keyword       - 搜索关键词（模糊匹配）
            category_code - 分类编码（为空表示不限制）
            tags          - 标签列表（为空表示不限制；命中任一即保留）

        返回:
            符合条件的 StudyNote 列表
        """
        sql = "SELECT * FROM study_notes WHERE 1=1"  # 恒真，便于后续动态 AND
        params: list = []

        # 分类过滤：匹配该分类及其所有子分类（编码前缀匹配）
        if category_code:
            sql += " AND (category_code = ? OR category_code LIKE ?)"
            params.extend([category_code, category_code + "%"])

        # 关键词过滤：三列任意一列命中
        if keyword:
            like = f"%{keyword}%"
            sql += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
            params.extend([like, like, like])

        # 默认按更新时间倒序，最近修改的笔记排最前
        sql += " ORDER BY updated_at DESC, id DESC"

        rows = self.conn.execute(sql, params).fetchall()
        notes = [StudyNote.from_row(r) for r in rows]

        # 标签过滤在 Python 层做（因为 tags 存为 JSON 字符串，SQL 模糊匹配不够精确）
        if tags:
            notes = [
                n for n in notes
                if any(tag.lower() in [t.lower() for t in n.tags] for tag in tags)
            ]

        return notes

    def get_note(self, note_id: int) -> Optional[StudyNote]:
        """根据笔记 ID 获取单条笔记记录。"""
        row = self.conn.execute(
            "SELECT * FROM study_notes WHERE id = ?", (note_id,)
        ).fetchone()
        return StudyNote.from_row(row) if row else None

    def add_note(self, payload: dict) -> int:
        """
        新增一条笔记，返回新记录的自增主键 ID。

        payload 必需字段：title
        payload 可选字段：category_code, category_name, content, tags, source_id

        参数:
            payload - 包含笔记字段的字典
        返回:
            新增记录的自增 ID
        """
        now = _now()
        tags_json = json.dumps(payload.get("tags", []), ensure_ascii=False)

        cursor = self.conn.execute(
            """INSERT INTO study_notes
               (category_code, category_name, title, content, tags, source_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                payload.get("category_code", ""),
                payload.get("category_name", ""),
                payload.get("title", ""),
                payload.get("content", ""),
                tags_json,
                payload.get("source_id", 0),
                now, now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_note(self, note_id: int, payload: dict):
        """
        更新指定笔记的所有字段（字段缺失时使用默认值）。

        参数:
            note_id - 笔记主键 ID
            payload - 包含要更新字段的字典
        """
        now = _now()
        tags_json = json.dumps(payload.get("tags", []), ensure_ascii=False)
        self.conn.execute(
            """UPDATE study_notes
               SET category_code=?, category_name=?, title=?, content=?,
                   tags=?, source_id=?, updated_at=?
               WHERE id=?""",
            (
                payload.get("category_code", ""),
                payload.get("category_name", ""),
                payload.get("title", ""),
                payload.get("content", ""),
                tags_json,
                payload.get("source_id", 0),
                now, note_id,
            ),
        )
        self.conn.commit()

    def delete_note(self, note_id: int):
        """根据 ID 删除单条笔记（图片文件需由调用方单独清理）。"""
        self.conn.execute("DELETE FROM study_notes WHERE id = ?", (note_id,))
        self.conn.commit()

    def count_notes_by_category(self, category_code: str) -> int:
        """
        统计指定分类及其所有子分类下的笔记总数。
        用于分类树节点旁显示笔记数量。

        参数:
            category_code - 分类编码
        返回:
            笔记总数
        """
        return self.conn.execute(
            "SELECT COUNT(1) FROM study_notes "
            "WHERE category_code = ? OR category_code LIKE ?",
            (category_code, category_code + "%"),
        ).fetchone()[0]

    # --------------------------------------------------------------------------
    # 百度网盘资料 CRUD
    # --------------------------------------------------------------------------

    def fetch_baidu_sources(self, keyword: str = "") -> list[BaiduDiskSource]:
        """
        获取百度网盘资料列表，支持关键词搜索，按更新时间倒序。

        搜索范围：标题、标签、备注

        参数:
            keyword - 搜索关键词（模糊匹配）
        返回:
            符合条件的 BaiduDiskSource 列表
        """
        if keyword:
            like = f"%{keyword}%"
            rows = self.conn.execute(
                """SELECT * FROM baidu_disk_sources
                   WHERE title LIKE ? OR tags LIKE ? OR note LIKE ?
                   ORDER BY updated_at DESC""",
                (like, like, like),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM baidu_disk_sources ORDER BY updated_at DESC"
            ).fetchall()
        return [BaiduDiskSource.from_row(r) for r in rows]

    def get_baidu_source(self, source_id: int) -> Optional[BaiduDiskSource]:
        """根据 ID 获取单条网盘资料记录。"""
        row = self.conn.execute(
            "SELECT * FROM baidu_disk_sources WHERE id = ?", (source_id,)
        ).fetchone()
        return BaiduDiskSource.from_row(row) if row else None

    def add_baidu_source(self, payload: dict) -> int:
        """
        新增一条百度网盘资料记录，返回新记录自增 ID。

        payload 必需字段：title
        payload 可选字段：link_url, access_code, tags, note
        """
        now = _now()
        tags_json = json.dumps(payload.get("tags", []), ensure_ascii=False)
        cursor = self.conn.execute(
            """INSERT INTO baidu_disk_sources
               (title, link_url, access_code, tags, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                payload.get("title", ""),
                payload.get("link_url", ""),
                payload.get("access_code", ""),
                tags_json,
                payload.get("note", ""),
                now, now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_baidu_source(self, source_id: int, payload: dict):
        """
        更新指定网盘资料的所有字段。

        参数:
            source_id - 资料主键 ID
            payload   - 包含要更新字段的字典
        """
        now = _now()
        tags_json = json.dumps(payload.get("tags", []), ensure_ascii=False)
        self.conn.execute(
            """UPDATE baidu_disk_sources
               SET title=?, link_url=?, access_code=?, tags=?, note=?, updated_at=?
               WHERE id=?""",
            (
                payload.get("title", ""),
                payload.get("link_url", ""),
                payload.get("access_code", ""),
                tags_json,
                payload.get("note", ""),
                now, source_id,
            ),
        )
        self.conn.commit()

    def delete_baidu_source(self, source_id: int):
        """
        删除指定网盘资料。

        安全策略：删除前将所有引用此资料的笔记的 source_id 置为 0（解除关联），
        而不是级联删除笔记，保证数据安全。

        参数:
            source_id - 资料主键 ID
        """
        # 先解除关联（不清除笔记内容）
        self.conn.execute(
            "UPDATE study_notes SET source_id=0 WHERE source_id=?",
            (source_id,)
        )
        self.conn.execute(
            "DELETE FROM baidu_disk_sources WHERE id = ?",
            (source_id,)
        )
        self.conn.commit()

    def get_baidu_source_for_note(self, note_id: int) -> Optional[BaiduDiskSource]:
        """
        根据笔记 ID 查找其关联的网盘资料。

        参数:
            note_id - 笔记主键 ID
        返回:
            对应的 BaiduDiskSource 实例；笔记无来源或来源已删除时返回 None
        """
        note = self.get_note(note_id)
        if not note or not note.source_id:
            return None
        return self.get_baidu_source(note.source_id)

    def close(self):
        """
        关闭数据库连接。
        应在主程序退出时调用（由 main.py 的 exit_app 方法统一处理）。
        """
        self.conn.close()
