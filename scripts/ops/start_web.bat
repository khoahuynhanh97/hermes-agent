@echo off
title Hermes Prompt Studio Web Server & Remote Tunnel
cd /d "%~dp0"

echo ======================================================================
echo 🚀 DANG KHOI DONG HERMES PROMPT STUDIO WEB SERVER...
echo ======================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [1/2] Dang mo Web Server local tai cong 8000...
start "" /b "%PYTHON_EXE%" web_studio.py

set /a WAIT_COUNT=0
:wait_for_server
curl.exe --silent --fail http://127.0.0.1:8000/ >nul 2>&1 && goto server_ready
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 20 goto server_failed
timeout /t 1 /nobreak >nul
goto wait_for_server

:server_failed
echo [LOI] Web Server khong phan hoi tai http://127.0.0.1:8000/
echo Kiem tra loi Python o phia tren roi thu lai.
pause
exit /b 1

:server_ready
echo [OK] Web Server da san sang tai http://127.0.0.1:8000/

echo.
echo [2/2] Dang tao duong link HTTPS bao mat de truy cap tu CONG TY / NOI XA...
echo Vui long cho trong 5-10 giay, duong link truy cap tu xa se hien ben duoi:
echo ----------------------------------------------------------------------

npx -y cloudflared tunnel --url http://127.0.0.1:8000
