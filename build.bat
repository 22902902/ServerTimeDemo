@echo off
chcp 65001 > nul
REM ============================================================
REM  ExpiryManager 打包 + 同步脚本
REM  - 编译 exe
REM  - 同步 DB / Tools 到 dist
REM  - 同步完整工程到坚果云（便携目录）
REM ============================================================

setlocal EnableDelayedExpansion

set "ROOT=F:\phpstudy_pro\WWW\ServerTimeDemo"
set "DIST=%ROOT%\dist"
set "NUTSTORE=G:\我的坚果云\我的坚果云\工作的临时存储\ServerTimeDemo"

REM =================== 清理临时脚本（可选，手动启用）====================
REM del /q "%ROOT%\_audit.py" 2>nul
REM del /q "%ROOT%\_test_overwrite.py" 2>nul
REM del /q "%ROOT%\_task_2026-07-20_code_refactor.md" 2>nul

cd /d "%ROOT%"

REM =================== 1. PyInstaller 打包 ===================
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

"C:\Users\shaoy\AppData\Local\Programs\Python\Python312\python.exe" -m PyInstaller ExpiryManager_fixed.spec --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller failed
    exit /b 1
)
echo [OK] PyInstaller complete

REM =================== 2. 同步 DB + Tools 到 dist ===================
copy /y "%ROOT%\expiry_manager.db" "%DIST%\expiry_manager.db" > nul
echo [OK] DB copied to dist

if exist "%ROOT%\Tools" (
    robocopy "%ROOT%\Tools" "%DIST%\Tools" /MIR /R:1 /W:1 /NJH /NJS /NC /NS > nul
    echo [OK] Tools dir synced to dist
)

REM =================== 3. 同步到坚果云（完整工程）====================
REM 排除 build / dist / __pycache__ / .bak / 临时脚本
robocopy "%ROOT%" "%NUTSTORE%" ^
    *.py *.spec *.txt *.md *.json *.db ^
    /E ^
    /XD build dist __pycache__ embedded_admin_tools ^
    /XF *.bak.* _audit.py _test_overwrite.py _task_*.md _fix_*.py _copy_new.py _install_new.py ^
    /R:1 /W:1 /NJH /NJS /NC /NS
echo [OK] Source synced to Nutstore

REM =================== 4. 同步 dist 到坚果云 ===================
robocopy "%DIST%" "%NUTSTORE%\dist" ^
    ExpiryManager_fixed.exe expiry_manager.db ^
    /E ^
    /XF ExpiryManager_fixed.exe.manifest *_fixed.pkg ^
    /R:1 /W:1 /NJH /NJS /NC /NS
echo [OK] dist synced to Nutstore

REM =================== 5. 显示结果 ===================
echo.
echo === Build Summary ===
for %%F in ("%DIST%\ExpiryManager_fixed.exe") do echo   dist\ExpiryManager_fixed.exe : %%~zF bytes
for %%F in ("%NUTSTORE%\ExpiryManager_fixed.exe") do echo   Nutstore\ExpiryManager_fixed.exe : %%~zF bytes
for %%F in ("%NUTSTORE%\expiry_manager.db") do echo   Nutstore\expiry_manager.db : %%~zF bytes
echo.
echo [DONE]
endlocal
