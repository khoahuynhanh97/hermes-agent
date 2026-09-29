# Daily Product-Intelligence to Exchange Inbox Publisher
# Runs gatekeeper validation and publishes READY batch for Hermes Product Video

$ErrorActionPreference = "Stop"

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$VENV = Join-Path $REPO_ROOT ".venv"
$PYTHON = Join-Path $VENV "Scripts\python.exe"

if (-not (Test-Path $PYTHON)) {
    Write-Error "Python virtual environment not found at: $VENV"
    exit 1
}

$SOURCE_ROOT = "D:\work\Personal\Product-Intelligence\data\daily_runs"
$INBOX_ROOT = "D:\work\Personal\hermes-product-video-exchange\inbox"

Write-Host "Publishing Product-Intelligence daily batch with gatekeeper..." -ForegroundColor Cyan
Write-Host "  Source: $SOURCE_ROOT" -ForegroundColor Gray
Write-Host "  Inbox:  $INBOX_ROOT" -ForegroundColor Gray

& $PYTHON -m hermes_personal.product_video.automation.publisher `
    --source-root $SOURCE_ROOT `
    --inbox-root $INBOX_ROOT `
    --cooldown-days 30 `
    --limit 5

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "`n✓ Daily batch published successfully" -ForegroundColor Green
    
    # Optionally trigger auto-start coordinator
    $AUTO_START = $env:HERMES_AUTO_START_AFTER_PUBLISH
    if ($AUTO_START -eq "1") {
        Write-Host "`nStarting Product Video workflows..." -ForegroundColor Cyan
        & $PYTHON -m hermes_personal.product_video.cli start-auto --limit 5
    }
} else {
    Write-Host "`n✗ Daily batch publishing failed" -ForegroundColor Red
    exit $exitCode
}
