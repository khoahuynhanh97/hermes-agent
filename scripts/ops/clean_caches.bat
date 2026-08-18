@echo off
:: Batch script to clean locked .pytest-* test cache directories with Administrator rights
title Don dep Test Caches Hermes Agent

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Dang yeu cau quyen Administrator de xoa cac thu muc bi khoa boi Admin/System...
    powershell -Command "Start-Process cmd -ArgumentList '/k \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

set "REPO=D:\work\hermes-agent"
echo [OK] Dang chay duoi quyen Administrator tai %REPO%
echo.

echo ========================================================
echo BƯỚC 1: Xóa bằng PowerShell với Full Permissions...
echo ========================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%REPO%' -Force -Directory | Where-Object { $_.Name -like '.pytest-*' -or $_.Name -like '.tmp-*' -or $_.Name -like 'workhermes-agent.tmp-*' -or $_.Name -like '.audit-pytest-*' } | ForEach-Object { Write-Host 'Xoa:' $_.FullName; try { & takeown.exe /F $_.FullName /R /D Y 2>$null; & icacls.exe $_.FullName /grant Everyone:(OI)(CI)F /T /C /Q 2>$null; Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Continue } catch { Write-Host 'Loi:' $_ } }"

echo.
echo ========================================================
echo BƯỚC 2: Xóa trực tiếp bằng CMD rmdir...
echo ========================================================
for /f "delims=" %%d in ('dir /b /ad "%REPO%\.pytest-*" 2^>nul') do (
    echo Dang xu ly: %%d
    takeown /f "%REPO%\%%d" /r /d y >nul 2>&1
    icacls "%REPO%\%%d" /grant Administrators:F /t /c /q >nul 2>&1
    icacls "%REPO%\%%d" /grant Everyone:F /t /c /q >nul 2>&1
    attrib -r -s -h "%REPO%\%%d" /s /d >nul 2>&1
    rmdir /s /q "%REPO%\%%d"
)

for /f "delims=" %%d in ('dir /b /ad "%REPO%\.audit-pytest-*" 2^>nul') do (
    echo Dang xu ly: %%d
    takeown /f "%REPO%\%%d" /r /d y >nul 2>&1
    icacls "%REPO%\%%d" /grant Administrators:F /t /c /q >nul 2>&1
    icacls "%REPO%\%%d" /grant Everyone:F /t /c /q >nul 2>&1
    rmdir /s /q "%REPO%\%%d"
)

for /f "delims=" %%d in ('dir /b /ad "%REPO%\workhermes-agent.tmp-*" 2^>nul') do (
    echo Dang xu ly: %%d
    takeown /f "%REPO%\%%d" /r /d y >nul 2>&1
    icacls "%REPO%\%%d" /grant Everyone:F /t /c /q >nul 2>&1
    rmdir /s /q "%REPO%\%%d"
)

if exist "%REPO%\.pytest_cache" (
    rmdir /s /q "%REPO%\.pytest_cache" >nul 2>&1
)

echo.
echo ========================================================
echo [HOAN TAT] Kiem tra lai danh sach:
dir /b /ad "%REPO%\.pytest-*" 2>nul
if %errorLevel% neq 0 (
    echo [THANH CONG] Khong con thu muc .pytest-* nao!
)
echo ========================================================
echo.
pause
