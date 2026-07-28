@echo off
cd /d "%~dp0"
if not exist "runtime_logs" mkdir "runtime_logs"

echo Starting Hermes Telegram Bot...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; Start-Process -FilePath 'python' -ArgumentList 'telegram_bot.py' -WorkingDirectory '%CD%' -RedirectStandardOutput 'runtime_logs\telegram_bot.stdout.log' -RedirectStandardError 'runtime_logs\telegram_bot.stderr.log' -WindowStyle Hidden"

echo Starting Hermes Job Worker...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8='1'; Start-Process -FilePath 'python' -ArgumentList '-m workers.job_worker' -WorkingDirectory '%CD%' -RedirectStandardOutput 'runtime_logs\worker.stdout.log' -RedirectStandardError 'runtime_logs\worker.stderr.log' -WindowStyle Hidden"

echo.
echo Da chay 2 tien trinh:
echo - Telegram Bot: runtime_logs\telegram_bot.stderr.log
echo - Worker: runtime_logs\worker.stderr.log
echo.
timeout /t 3 >nul
