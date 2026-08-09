# start.ps1 — Hermes Unified Start (Backend + Worker, optional React UI)
# Usage:  .\start.ps1            (backend + worker)
#         .\start.ps1 -UI        (also start React dev server)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot
param([switch]$UI)

if (-not (Test-Path "$RepoRoot\.venv\Scripts\python.exe")) {
  Write-Error "No .venv found in repo. Run .\setup.ps1 first."
}
$Py = "$RepoRoot\.venv\Scripts\python.exe"

if (-not (Test-Path "$RepoRoot\.env")) {
  Write-Warning ".env missing - copy .env.example to .env and configure secrets."
}

Write-Host "=== Starting Hermes (Unified Runtime) ===" -ForegroundColor Cyan
Write-Host "Interpreter: $Py"
Write-Host "Source Root: $RepoRoot"

# Verify interpreter imports from THIS repo
$verifyScript = "import sys; sys.path.insert(0, r'$RepoRoot'); import hermes, cli; print(f'hermes={hermes.__file__}\ncli={cli.__file__}')"
$verifyOutput = (& $Py -c $verifyScript)
Write-Host $verifyOutput
if ($verifyOutput -notmatch [regex]::Escape($RepoRoot)) {
  Write-Error "CRITICAL: Hermes is resolving outside this repo ($verifyOutput). Run .\setup.ps1 to fix editable installation."
}

# --- Runtime Logs Directory --------------------------------------------------
$logDir = Join-Path $RepoRoot "runtime_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

# --- Worker Process (Durable Job Execution) ----------------------------------
$workerProc = Start-Process -FilePath $Py -ArgumentList "-m","workers.job_worker" -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $logDir "worker.out.log") -RedirectStandardError (Join-Path $logDir "worker.err.log") -WindowStyle Hidden -PassThru
Write-Host "Worker started (PID $($workerProc.Id)) -> logs in runtime_logs/worker.*.log"

# --- Backend Process (aiohttp / Web Studio API) -----------------------------
$backendProc = Start-Process -FilePath $Py -ArgumentList "web_studio.py" -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $logDir "backend.out.log") -RedirectStandardError (Join-Path $logDir "backend.err.log") -WindowStyle Hidden -PassThru
Write-Host "Backend started (PID $($backendProc.Id)) -> http://127.0.0.1:8000"

# --- Optional Frontend Process (React / Vite UI) -----------------------------
if ($UI) {
  if (-not (Test-Path "$RepoRoot\web\node_modules")) {
    Write-Warning "web UI dependencies missing - run .\setup.ps1 first. Skipping UI."
  } else {
    Push-Location "$RepoRoot\web"
    $uiProc = Start-Process -FilePath "npm" -ArgumentList "run","dev" -WorkingDirectory "$RepoRoot\web" -RedirectStandardOutput (Join-Path $logDir "ui.out.log") -RedirectStandardError (Join-Path $logDir "ui.err.log") -WindowStyle Hidden -PassThru
    Pop-Location
    Write-Host "UI started (PID $($uiProc.Id)) -> http://127.0.0.1:3000"
  }
}

Write-Host ""
Write-Host "Services online. Backend: http://127.0.0.1:8000 | CLI: $RepoRoot\.venv\Scripts\hermes.exe" -ForegroundColor Green
Write-Host "Stop processes command: Stop-Process -Id $($workerProc.Id),$($backendProc.Id) -Force"
