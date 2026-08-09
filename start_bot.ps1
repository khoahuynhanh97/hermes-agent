# start_bot.ps1 — Hermes Telegram Bot + Worker Start
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$env:PYTHONUTF8 = "1"
$Py = "$RepoRoot\.venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Error "No .venv found. Run .\setup.ps1 first."
}

New-Item -ItemType Directory -Path "runtime_logs" -Force | Out-Null

Write-Host "=== Starting Hermes Telegram Bot + Job Worker ===" -ForegroundColor Cyan
Write-Host "Using interpreter: $Py"

$botProc = Start-Process -FilePath $Py -ArgumentList "telegram_bot.py" -WorkingDirectory $RepoRoot -RedirectStandardOutput "runtime_logs\telegram_bot.stdout.log" -RedirectStandardError "runtime_logs\telegram_bot.stderr.log" -WindowStyle Hidden -PassThru
Write-Host "Telegram Bot started (PID $($botProc.Id)) -> logs: runtime_logs\telegram_bot.stderr.log" -ForegroundColor Green

$workerProc = Start-Process -FilePath $Py -ArgumentList "-m","workers.job_worker" -WorkingDirectory $RepoRoot -RedirectStandardOutput "runtime_logs\worker.stdout.log" -RedirectStandardError "runtime_logs\worker.stderr.log" -WindowStyle Hidden -PassThru
Write-Host "Job Worker started (PID $($workerProc.Id)) -> logs: runtime_logs\worker.stderr.log" -ForegroundColor Green

Write-Host ""
Write-Host "Both processes online. Stop command: Stop-Process -Id $($botProc.Id),$($workerProc.Id) -Force" -ForegroundColor Yellow
