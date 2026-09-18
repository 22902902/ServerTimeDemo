# -*- coding: utf-8 -*-
"""
ExpiryManager 数据目录迁移模块。
首次启动时将散落的旧文件迁移到 ExpiryManager_Data/ 统一管理。
"""
import os, shutil
from pathlib import Path

DATA_DIR = BASE_DIR / "ExpiryManager_Data"
MIGRATED_FILE = DATA_DIR / ".migrated"

# 旧位置 → 新子路径（相对 DATA_DIR）
_MIGRATION_MAP = [
    ("expiry_manager.db",        "expiry_manager.db"),
    ("study_demo.db",            "study_demo.db"),
    ("remember_me.json",         "remember_me.json"),
    ("login_memory.json",        "login_memory.json"),
    ("account_images",           "account_images"),
    ("study_notes_images",       "study_notes_images"),
    ("study_notes_attachments",  "study_notes_attachments"),
    ("process_flow_images",      "process_flow_images"),
    ("Tools",                   "Tools"),
    ("excel",                   "excel"),
    ("adb_history",             "adb_history"),
    ("study_demo",              "study_demo"),
]


def _migrate_data_dir():
    """将旧位置的文件/目录迁移到 ExpiryManager_Data/（仅首次执行）。"""
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
            # 目标已存在则以新目录优先（不覆盖已有数据）
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
    """确保 DATA_DIR 及所有子目录存在。"""
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
