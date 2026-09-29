# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (r'C:\Users\shaoy\AppData\Local\Programs\Python\Python312\Lib\site-packages\tkinterdnd2',
         'tkinterdnd2'),
        ('app.ico', '.'),  # 窗口图标
    ],
    hiddenimports=['log_setup', 'tools_db', 'console_page', 'system_toolbox_page', 'adb_page', 'tools_page', 'app_version', 'markdown_view', 'todo_db', 'todo_page', 'todo_icons', 'process_db', 'process_page', 'credential_process_dialogs', 'image_clipboard', 'excel_db', 'excel_page', 'excel_todo_bridge', 'excel_note_bridge', 'startup_manager', 'excel_seed', 'excel_seed_schema', 'excel_seed_math', 'excel_seed_stat', 'excel_seed_lookup', 'excel_seed_text', 'excel_seed_date', 'excel_seed_misc', 'excel_seed_extra', 'training_core', 'training_todo_bridge', 'memory_seed', 'cs2_seed', 'memory_db', 'memory_page', 'mindmap_layout', 'mindmap_seed', 'mindmap_db', 'mindmap_page', 'mindmap_image', 'speech', 'mindmap_memory_bridge', 'excel_formula_hl', 'excel_export', 'process_image_migrate', 'PIL', 'tkinterdnd2', 'tkcalendar'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ExpiryManager_fixed',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)

