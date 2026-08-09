@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay Python virtualenv:
    echo "%PYTHON_EXE%"
    echo.
    echo Hay cai dependencies truoc:
    echo python -m venv .venv
    echo .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "runtime_logs" mkdir "runtime_logs"

echo Starting Hermes Telegram Bot...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'telegram_bot.py' -WorkingDirectory '%CD%' -RedirectStandardOutput 'runtime_logs\telegram_bot.stdout.log' -RedirectStandardError 'runtime_logs\telegram_bot.stderr.log' -WindowStyle Hidden"

echo Starting Hermes Job Worker...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'scripts\run_job_worker.py' -WorkingDirectory '%CD%' -RedirectStandardOutput 'runtime_logs\job_worker.stdout.log' -RedirectStandardError 'runtime_logs\job_worker.stderr.log' -WindowStyle Hidden"

echo.
echo Da chay ngam 2 tien trinh:
echo - Hermes Telegram Bot: runtime_logs\telegram_bot.stderr.log
echo - Hermes Job Worker: runtime_logs\job_worker.stderr.log
echo.
timeout /t 3 >nul
