param(
    [int]$Interval = 180,
    [int]$Limit = 20,
    [ValidateSet("incoming", "outgoing", "all")]
    [string]$Direction = "all"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$ReportsDir = Join-Path $RepoRoot "reports"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = (Get-Command python).Source
}

$StdOut = Join-Path $ReportsDir "telegram_review_watcher.stdout.log"
$StdErr = Join-Path $ReportsDir "telegram_review_watcher.stderr.log"
$env:PYTHONUTF8 = "1"
$env:TELEGRAM_REVIEW_SUPPRESS_CONSOLE = "1"
$Args = @(
    "scripts\telegram_review_watcher.py",
    "--interval", $Interval,
    "--limit", $Limit,
    "--direction", $Direction,
    "--max-hours", 5,
    "--skip-history-on-first-run",
    "--log-file", $StdOut,
    "--error-log-file", $StdErr
)

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList $Args `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Telegram review watcher started. PID=$($Process.Id)"
Write-Host "Interval: $Interval seconds"
Write-Host "Direction: $Direction"
Write-Host "Stdout: $StdOut"
Write-Host "Stderr: $StdErr"
