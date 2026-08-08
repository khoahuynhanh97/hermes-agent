# start.ps1 — Hermes Personal start (backend + worker, optional web UI)
# Usage:  .\start.ps1            (backend + worker)
#         .\start.ps1 -UI        (also start React dev server)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot
param([switch]$UI)

if (-not (Test-Path "$RepoRoot\.venv\Scripts\python.exe")) {
  Write-Error "No .venv found. Run  .\setup.ps1  first."
}
$Py = "$RepoRoot\.venv\Scripts\python.exe"

# Ensure .env loaded (python-dotenv handles it in entrypoints that support it)
if (-not (Test-Path "$RepoRoot\.env")) {
  Write-Warning ".env missing - copy .env.example to .env and add secrets."
}

Write-Host "=== Hermes Personal start ===" -ForegroundColor Cyan
Write-Host "Using: $Py"
Write-Host "Source: $RepoRoot"

# Verify the interpreter resolves THIS repo (editable install)
$here = (& $Py -c "import sys; sys.path.insert(0, r'$RepoRoot'); import hermes; print(hermes.__file__)")
Write-Host "hermes -> $here"
if ($here -notmatch [regex]::Escape($RepoRoot)) {
  Write-Warning "hermes resolved outside this repo ($here). The editable install may be stale."
}

# --- Worker (durable job execution) in background ----------------------------
$workerLog = Join-Path $RepoRoot "runtime_logs"
New-Item -ItemType Directory -Path $workerLog -Force | Out-Null
$workerProc = Start-Process -FilePath $Py -ArgumentList "-m","workers.job_worker" -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $workerLog "worker.out.log") -RedirectStandardError (Join-Path $workerLog "worker.err.log") -WindowStyle Hidden -PassThru
Write-Host "Worker started (PID $($workerProc.Id)) - logs in runtime_logs/"

# --- Backend (aiohttp: projects + Video Factory + media) ---------------------
$backendProc = Start-Process -FilePath $Py -ArgumentList "web_studio.py" -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $workerLog "backend.out.log") -RedirectStandardError (Join-Path $workerLog "backend.err.log") -WindowStyle Hidden -PassThru
Write-Host "Backend started (PID $($backendProc.Id)) -> http://127.0.0.1:8000"

# --- Optional web UI (React dev server) ---------------------------------------
if ($UI) {
  if (-not (Test-Path "$RepoRoot\web\node_modules")) {
    Write-Warning "web deps not installed - run .\setup.ps1 first, skipping UI."
  } else {
    Push-Location "$RepoRoot\web"
    $uiProc = Start-Process -FilePath "npm" -ArgumentList "run","dev" -WorkingDirectory "$RepoRoot\web" -RedirectStandardOutput (Join-Path $workerLog "ui.out.log") -RedirectStandardError (Join-Path $workerLog "ui.err.log") -WindowStyle Hidden -PassThru
    Pop-Location
    Write-Host "UI started (PID $($uiProc.Id)) -> http://127.0.0.1:3000"
  }
}

Write-Host ""
Write-Host "Started. Backend: http://127.0.0.1:8000  |  UI: http://127.0.0.1:3000 (if -UI)"
Write-Host "Stop: Stop-Process -Id $($workerProc.Id),$($backendProc.Id) $($uiProc.Id) -Force"
Write-Host ""
Write-Host "Note: a separate 'hermes' install is NOT required. This repo is the runtime."
