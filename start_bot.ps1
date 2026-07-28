$env:PYTHONUTF8 = "1"
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

New-Item -ItemType Directory -Path "runtime_logs" -Force | Out-Null

Write-Host "Starting Hermes Telegram Bot..." -ForegroundColor Cyan
Start-Process python -ArgumentList "telegram_bot.py" -RedirectStandardOutput "runtime_logs\telegram_bot.stdout.log" -RedirectStandardError "runtime_logs\telegram_bot.stderr.log" -WindowStyle Hidden

Write-Host "Starting Hermes Job Worker..." -ForegroundColor Cyan
Start-Process python -ArgumentList "-m workers.job_worker" -RedirectStandardOutput "runtime_logs\worker.stdout.log" -RedirectStandardError "runtime_logs\worker.stderr.log" -WindowStyle Hidden

Write-Host ""
Write-Host "Da chay 2 tien trinh:" -ForegroundColor Green
Write-Host "  - Telegram Bot: runtime_logs\telegram_bot.stderr.log"
Write-Host "  - Worker: runtime_logs\worker.stderr.log"
