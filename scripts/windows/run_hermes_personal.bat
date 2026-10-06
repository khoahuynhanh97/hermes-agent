@echo off
chcp 65001 >nul
echo ====================================================================
echo   HERMES PERSONAL - RUNNER & SUPERVISOR KHỞI ĐỘNG HỆ THỐNG
echo ====================================================================
echo.

set HERMES_HOME=%USERPROFILE%\.hermes
set PYTHONPATH=%CD%

echo [*] Kiểm tra môi trường...
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
) else (
    set PYTHON_EXE=python
)

echo [*] Sử dụng Python: %PYTHON_EXE%
echo [*] HERMES_HOME: %HERMES_HOME%
echo.

if "%1"=="--wt" goto launch_wt
if "%1"=="--dev" goto launch_supervisor

:launch_supervisor
echo [*] Khởi động Process Supervisor (Gateway + App API + Worker + MCP Discovery)...
%PYTHON_EXE% -m hermes_personal.runtime.cli --mode development
goto end

:launch_wt
echo [*] Mở đa tiến trình trong 1 cửa sổ chia màn hình (Windows Terminal)...
where wt >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [CẢNH BÁO] Không tìm thấy Windows Terminal (wt.exe). Khởi chạy supervisor thông thường.
    goto launch_supervisor
)

wt -M ^
  new-tab --title "Supervisor & Gateway" cmd /k "chcp 65001 >nul && %PYTHON_EXE% -m hermes_personal.runtime.cli --mode development" ; ^
  split-pane -V --title "Outbox Worker" cmd /k "chcp 65001 >nul && %PYTHON_EXE% -m hermes_personal.workflows.worker --provider-mode configured" ; ^
  split-pane -H --title "Video CLI / Quick Actions" cmd /k "chcp 65001 >nul && echo Gõ lệnh: %PYTHON_EXE% -m hermes_cli personal video ... để thao tác"
goto end

:end
