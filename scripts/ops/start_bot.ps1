# start_bot.ps1 - Hermes Telegram Knowledge Auto Start
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $RepoRoot "src"
$Py = "$RepoRoot\.venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Error "No .venv found at $Py. Run .\scripts\ops\install.ps1 first."
}

New-Item -ItemType Directory -Path "runtime_logs" -Force | Out-Null

Write-Host "=== Starting Hermes Telegram Knowledge Stack ===" -ForegroundColor Cyan
Write-Host "Using interpreter: $Py"

$botProc = Start-Process -FilePath $Py -ArgumentList "-m hermes.channels.gateway.platforms.telegram.bot" -WorkingDirectory $RepoRoot -RedirectStandardOutput "runtime_logs\telegram_bot.stdout.log" -RedirectStandardError "runtime_logs\telegram_bot.stderr.log" -WindowStyle Hidden -PassThru
Write-Host "Telegram Bot started (PID $($botProc.Id)) -> logs: runtime_logs\telegram_bot.stderr.log" -ForegroundColor Green

$workerProc = Start-Process -FilePath $Py -ArgumentList "scripts\ops\run_job_worker.py" -WorkingDirectory $RepoRoot -RedirectStandardOutput "runtime_logs\knowledge_worker.stdout.log" -RedirectStandardError "runtime_logs\knowledge_worker.stderr.log" -WindowStyle Hidden -PassThru
Write-Host "Knowledge Job Worker started (PID $($workerProc.Id)) -> logs: runtime_logs\knowledge_worker.stderr.log" -ForegroundColor Green

$watcherProc = Start-Process -FilePath $Py -ArgumentList "scripts\ops\telegram_review_watcher.py" -WorkingDirectory $RepoRoot -RedirectStandardOutput "runtime_logs\telegram_review_watcher.stdout.log" -RedirectStandardError "runtime_logs\telegram_review_watcher.stderr.log" -WindowStyle Hidden -PassThru
Write-Host "Telegram Review Watcher started (PID $($watcherProc.Id)) -> logs: runtime_logs\telegram_review_watcher.stderr.log" -ForegroundColor Green

Write-Host ""
Write-Host "Processes online. Stop command: Stop-Process -Id $($botProc.Id),$($workerProc.Id),$($watcherProc.Id) -Force" -ForegroundColor Yellow
