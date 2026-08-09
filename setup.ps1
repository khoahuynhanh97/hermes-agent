# setup.ps1 — Hermes Personal bootstrap (idempotent)
# Usage:  .\setup.ps1
# Creates <repo>\.venv, installs THIS repo editable, installs web deps,
# copies .env.example -> .env if missing, ensures HERMES_DATA_DIR exists.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot
Write-Host "=== Hermes Personal Setup ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

# --- 1. Tool Prerequisite Checks --------------------------------------------
function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

if (-not (Test-Cmd python)) { Write-Error "Python >= 3.10 required. Install python and retry." }
$pyMajor = (& python -c "import sys;print(sys.version_info.major)")
if ([int]$pyMajor -lt 3) { Write-Error "Python 3 required (found $pyMajor)." }

$hasUv = Test-Cmd uv
if (-not $hasUv) { Write-Host "uv not found - using python venv + pip." -ForegroundColor Yellow }

$hasNode = Test-Cmd node
if (-not $hasNode) { Write-Host "Node not found - web UI skipped (backend still works)." -ForegroundColor Yellow }

$ffmpegFound = $false
$ffmpegCandidates = @(
  "$env:FFMPEG_PATH",
  "C:\HermesTools\ffmpeg\bin\ffmpeg.exe",
  "D:\HermesTools\ffmpeg\bin\ffmpeg.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if ($ffmpegCandidates.Count -gt 0) { $ffmpegFound = $true }

# --- 2. Python Environment & Editable Install -------------------------------
if (-not (Test-Path "$RepoRoot\.venv\Scripts\python.exe")) {
  Write-Host "Creating .venv..."
  if ($hasUv) { uv venv .venv } else { python -m venv .venv }
} else {
  Write-Host ".venv exists - reusing." -ForegroundColor Green
}
$Py = "$RepoRoot\.venv\Scripts\python.exe"

Write-Host "Installing this repository editable + dependencies..."
if ($hasUv) {
  uv pip install --python "$Py" -e ".[dev]"
} else {
  & $Py -m pip install --upgrade pip | Out-Null
  & $Py -m pip install -e ".[dev]"
}
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed." }

# --- 3. Frontend Dependencies (React / Vite UI) -----------------------------
if ($hasNode -and (Test-Path "$RepoRoot\web\package.json")) {
  Write-Host "Installing web UI dependencies..."
  Push-Location "$RepoRoot\web"
  if (Test-Path "package-lock.json") { npm ci --no-audit --no-fund } else { npm install --no-audit --no-fund }
  Pop-Location
}

# --- 4. Environment Configuration (.env) -------------------------------------
if (-not (Test-Path "$RepoRoot\.env")) {
  if (Test-Path "$RepoRoot\.env.example") {
    Copy-Item "$RepoRoot\.env.example" "$RepoRoot\.env"
    Write-Host ".env created from .env.example - edit it to configure secrets." -ForegroundColor Yellow
  } else {
    Write-Warning ".env.example missing - create .env manually."
  }
} else {
  Write-Host ".env exists - preserved." -ForegroundColor Green
}

# --- 5. Data Root Directory --------------------------------------------------
$dataDir = $null
if (Test-Path "$RepoRoot\.env") {
  $line = (Get-Content "$RepoRoot\.env" | Where-Object { $_ -match '^HERMES_DATA_DIR=' } | Select-Object -First 1)
  if ($line) { $dataDir = $line.Substring($line.IndexOf('=') + 1).Trim().Trim('"',"'") }
}
if (-not $dataDir) { $dataDir = "D:\work\hermes-agent-data" }
try { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null; Write-Host "Data root: $dataDir" -ForegroundColor Green }
catch { Write-Warning "Cannot create data dir $dataDir : $_" }

# --- 6. Verification (No Paid API Calls) -------------------------------------
Write-Host ""
Write-Host "=== Source Verification (No Paid Calls) ==="
& $Py -c "import sys; sys.path.insert(0, r'$RepoRoot'); import hermes, cli, run_agent, hermes_cli, providers, mcp_servers, workers; print('  hermes package :', hermes.__file__); print('  cli entrypoint :', cli.__file__); print('  hermes_cli     :', hermes_cli.__file__); print('  Import verification: PASSED')"
if ($ffmpegFound) { Write-Host "  FFmpeg         : FOUND" -ForegroundColor Green } else { Write-Host "  FFmpeg         : MISSING (set FFMPEG_PATH or install ffmpeg)" -ForegroundColor Yellow }
Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "Repo CLI: $RepoRoot\.venv\Scripts\hermes.exe"
Write-Host "Run  .\start.ps1  to launch services."
