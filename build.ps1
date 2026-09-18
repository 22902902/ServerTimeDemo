﻿# ExpiryManager Build + Sync
$ErrorActionPreference = 'Stop'
$ROOT = 'F:\phpstudy_pro\WWW\ServerTimeDemo'
$DIST = Join-Path $ROOT 'dist'
$NUTSTORE = 'G:\xe6\x88\x91\xe7\x9a\x84\xe5\x9b\xbd\xe6\x9e\x97\xe4\xba\x91\ xe6\x88\x91\xe7\x9a\x84\xe5\x9b\xbd\xe6\x9e\x97\xe4\xba\x91\ \xe5\xb7\xa5\xe4\xbd\x9c\xe7\x9a\x84\xe4\xb8\xb4\xe6\x97\xb6\xe5\xad\x98\xe5\x82\xa8\ServerTimeDemo'
$PY = 'C:\Users\shaoy\AppData\Local\Programs\Python\Python312\python.exe'
Set-Location $ROOT

# 0. Backup dist
$bakDB = Join-Path $env:TEMP 'ExpiryManager_dist_backup.db'
$bakTools = Join-Path $env:TEMP 'ExpiryManager_Tools_backup'
if (Test-Path (Join-Path $DIST 'expiry_manager.db')) {
    Copy-Item (Join-Path $DIST 'expiry_manager.db') $bakDB -Force
}
if (Test-Path (Join-Path $DIST 'Tools')) {
    if (Test-Path $bakTools) { Remove-Item $bakTools -Recurse -Force }
    Copy-Item (Join-Path $DIST 'Tools') $bakTools -Recurse -Force
}
Write-Host '[0/5] Backup done'

# 1. PyInstaller build
if (Test-Path (Join-Path $ROOT 'build')) { Remove-Item (Join-Path $ROOT 'build') -Recurse -Force }
$distExe = Join-Path $DIST 'ExpiryManager_fixed.exe'
if (Test-Path $distExe) { Remove-Item $distExe -Force }
Write-Host '[1/5] PyInstaller...' -ForegroundColor Cyan
& $PY -m PyInstaller ExpiryManager_fixed.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
Write-Host '  OK' -ForegroundColor Green

# 2. Restore dist if cleared
Write-Host '[2/5] DB + Tools -> dist' -ForegroundColor Cyan
$distDB = Join-Path $DIST 'expiry_manager.db'
$rootDB = Join-Path $ROOT 'expiry_manager.db'
if (-not (Test-Path $distDB) -and (Test-Path $bakDB)) {
    Write-Host '  [WARN] dist DB cleared, recovering...' -ForegroundColor Yellow
    Copy-Item $bakDB $distDB -Force
}
if (Test-Path $distDB) { Copy-Item $distDB $rootDB -Force }
$lm = Join-Path $DIST 'login_memory.json'
$lmRoot = Join-Path $ROOT 'login_memory.json'
if (Test-Path $lm) { Copy-Item $lm $lmRoot -Force -ErrorAction SilentlyContinue }
$distTools = Join-Path $DIST 'Tools'
$rootTools = Join-Path $ROOT 'Tools'
if (-not (Test-Path $distTools) -and (Test-Path $bakTools)) {
    Copy-Item $bakTools $distTools -Recurse -Force
}
if (Test-Path $distTools) {
    robocopy $distTools $rootTools /MIR /R:1 /W:1 /NJH /NJS /NC /NS | Out-Null
}
Write-Host '  OK' -ForegroundColor Green

# 3. Clean dist.bak
Write-Host '[3/5] Clean dist.bak...' -ForegroundColor Cyan
Get-ChildItem (Join-Path $DIST '*.bak*') -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host '  OK' -ForegroundColor Green

# 4. Sync source to Nutstore
Write-Host '[4/5] Source -> Nutstore' -ForegroundColor Cyan
if (-not (Test-Path $NUTSTORE)) { New-Item -ItemType Directory -Path $NUTSTORE -Force | Out-Null }
Remove-Item (Join-Path $NUTSTORE '_audit.py') -ErrorAction SilentlyContinue
Remove-Item (Join-Path $NUTSTORE '_test_overwrite.py') -ErrorAction SilentlyContinue
Remove-Item (Join-Path $NUTSTORE '_task_2026-07-20_code_refactor.md') -ErrorAction SilentlyContinue
Get-ChildItem (Join-Path $NUTSTORE '*.bak.*') -ErrorAction SilentlyContinue | Remove-Item -Force
robocopy $ROOT $NUTSTORE *.py *.spec *.txt *.md *.json /E /XD build dist __pycache__ embedded_admin_tools /XF *.bak.* _audit.py _test_overwrite.py _task_*.md _fix_*.py _copy_new.py _install_new.py build.bat build.ps1 /R:1 /W:1 /NJH /NJS /NC /NS | Out-Null
Write-Host '  OK' -ForegroundColor Green

# 5. Sync dist to Nutstore
Write-Host '[5/5] dist -> Nutstore' -ForegroundColor Cyan
$nutDist = Join-Path $NUTSTORE 'dist'
if (-not (Test-Path $nutDist)) { New-Item -ItemType Directory -Path $nutDist -Force | Out-Null }
Copy-Item (Join-Path $DIST 'ExpiryManager_fixed.exe') (Join-Path $nutDist 'ExpiryManager_fixed.exe') -Force
Copy-Item (Join-Path $DIST 'expiry_manager.db') (Join-Path $nutDist 'expiry_manager.db') -Force
if (Test-Path $distTools) {
    robocopy $distTools (Join-Path $nutDist 'Tools') /MIR /R:1 /W:1 /NJH /NJS /NC /NS | Out-Null
}
Write-Host '  OK' -ForegroundColor Green

# Summary
Write-Host ''
Write-Host '=== Build Summary ===' -ForegroundColor Yellow
$exe = Join-Path $DIST 'ExpiryManager_fixed.exe'
$nutExe = Join-Path $nutDist 'ExpiryManager_fixed.exe'
$nutDB = Join-Path $nutDist 'expiry_manager.db'
if (Test-Path $exe) { $s = Get-Item $exe; Write-Host ('  dist exe : ' + [math]::Round($s.Length/1KB,1) + ' KB  ' + $s.LastWriteTime.ToString('yyyy/MM/dd HH:mm')) }
if (Test-Path $nutExe) { $s = Get-Item $nutExe; Write-Host ('  Nut exe : ' + [math]::Round($s.Length/1KB,1) + ' KB') }
if (Test-Path $nutDB) { $s = Get-Item $nutDB; Write-Host ('  Nut db  : ' + [math]::Round($s.Length/1KB,1) + ' KB') }
Write-Host ''
Write-Host '[DONE]' -ForegroundColor Green
