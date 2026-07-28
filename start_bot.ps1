# Hermes - Telegram Bot + Worker
# Usage: .\start_bot.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   HERMES - Telegram Bot + Worker" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found. Install Python 3.12+" -ForegroundColor Red
    exit 1
}

# Check .env
if (-not (Test-Path ".env")) {
    Write-Host "[WARNING] .env not found. Copying from .env.example..." -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    } else {
        Write-Host "[ERROR] No .env or .env.example" -ForegroundColor Red
        exit 1
    }
}

# Activate venv if exists
if (Test-Path "venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
}

Write-Host ""
Write-Host "[1/2] Starting Telegram Bot..." -ForegroundColor Cyan
Write-Host "[2/2] Starting Worker in background..." -ForegroundColor Cyan
Write-Host ""

# Start worker in background job
$workerJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    python -m workers.job_worker
}

# Start bot in foreground
try {
    python telegram_bot.py
} finally {
    Write-Host ""
    Write-Host "[INFO] Bot stopped. Stopping worker..." -ForegroundColor Yellow
    Stop-Job -Job $workerJob -ErrorAction SilentlyContinue
    Remove-Job -Job $workerJob -ErrorAction SilentlyContinue
    Write-Host "[OK] Done." -ForegroundColor Green
}
