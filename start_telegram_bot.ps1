# Script to run Telegram Bot in background on Windows
param(
    [switch]$Stop,
    [switch]$Status
)

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "logs\runtime"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$LogFile = Join-Path $LogDir "telegram_bot.log"

if ($Status) {
    $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("telegram_bot.py") }
    if ($procs) {
        Write-Host "[OK] Telegram Bot is RUNNING in background:" -ForegroundColor Green
        foreach ($p in $procs) {
            Write-Host "   - Process ID (PID): $($p.ProcessId)"
        }
    } else {
        Write-Host "[INFO] Telegram Bot is NOT running." -ForegroundColor Yellow
    }
    exit 0
}

if ($Stop) {
    $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("telegram_bot.py") }
    if ($procs) {
        foreach ($p in $procs) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] Stopped Telegram Bot PID: $($p.ProcessId)" -ForegroundColor Green
        }
    } else {
        Write-Host "[INFO] No running Telegram Bot process found." -ForegroundColor Yellow
    }
    exit 0
}

# Stop existing instance if running
$oldProcs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("telegram_bot.py") }
foreach ($old in $oldProcs) {
    Stop-Process -Id $old.ProcessId -Force -ErrorAction SilentlyContinue
}

$proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "uv run python telegram_bot.py > logs\runtime\telegram_bot.log 2>&1" -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 3

$check = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("telegram_bot.py") }
if ($check) {
    Write-Host "[OK] Telegram Bot started in BACKGROUND successfully!" -ForegroundColor Green
    foreach ($c in $check) {
        Write-Host "   - Process ID (PID): $($c.ProcessId)" -ForegroundColor Cyan
    }
    Write-Host "   - Log File: $LogFile" -ForegroundColor Gray
} else {
    Write-Host "[FAIL] Telegram Bot process exited. Please check log: $LogFile" -ForegroundColor Red
}
