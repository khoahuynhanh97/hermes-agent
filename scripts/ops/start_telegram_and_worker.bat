@echo off
setlocal

for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "PYTHONPATH=%REPO_ROOT%\src"

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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; $env:PYTHONPATH='%PYTHONPATH%'; Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList '-m hermes.channels.gateway.platforms.telegram.bot' -WorkingDirectory '%REPO_ROOT%' -RedirectStandardOutput 'runtime_logs\telegram_bot.stdout.log' -RedirectStandardError 'runtime_logs\telegram_bot.stderr.log' -WindowStyle Hidden"

echo Starting Hermes Knowledge Job Worker...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; $env:PYTHONPATH='%PYTHONPATH%'; Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'scripts\ops\run_job_worker.py' -WorkingDirectory '%REPO_ROOT%' -RedirectStandardOutput 'runtime_logs\knowledge_worker.stdout.log' -RedirectStandardError 'runtime_logs\knowledge_worker.stderr.log' -WindowStyle Hidden"

echo Starting Hermes Telegram Review Watcher...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; $env:PYTHONPATH='%PYTHONPATH%'; Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'scripts\ops\telegram_review_watcher.py' -WorkingDirectory '%REPO_ROOT%' -RedirectStandardOutput 'runtime_logs\telegram_review_watcher.stdout.log' -RedirectStandardError 'runtime_logs\telegram_review_watcher.stderr.log' -WindowStyle Hidden"

echo.
echo Da chay ngam 3 tien trinh:
echo - Hermes Telegram Bot: runtime_logs\telegram_bot.stderr.log
echo - Hermes Knowledge Job Worker: runtime_logs\knowledge_worker.stderr.log
echo - Hermes Telegram Review Watcher: runtime_logs\telegram_review_watcher.stderr.log
echo.
timeout /t 3 >nul
