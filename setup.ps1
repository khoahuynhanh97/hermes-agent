# setup.ps1 — Hermes Personal bootstrap (idempotent)
# Usage:  .\setup.ps1
# Creates <repo>\.venv, installs THIS repo editable, installs web deps,
# copies .env.example -> .env if missing, ensures HERMES_DATA_DIR exists.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot
Write-Host "=== Hermes Personal setup ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

# --- 1. Tool prerequisites -------------------------------------------------
function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

if (-not (Test-Cmd python)) { Write-Error "Python >= 3.10 required. Install python and retry." }
$pyMajor = (& python -c "import sys;print(sys.version_info.major)")
if ([int]$pyMajor -lt 3) { Write-Error "Python 3 required (found $pyMajor)." }

# uv is preferred for fast venv/deps; fall back to python -m venv + pip
$hasUv = Test-Cmd uv
if (-not $hasUv) { Write-Host "uv not found - using python venv + pip." -ForegroundColor Yellow }

# Node only required for the web UI
$hasNode = Test-Cmd node
if (-not $hasNode) { Write-Host "Node not found - web UI skipped (backend still works)." -ForegroundColor Yellow }

# FFmpeg is an external dependency (used by video render/TTS mix). Doctor reports it.
$ffmpegFound = $false
$ffmpegCandidates = @(
  "$env:FFMPEG_PATH",
  "C:\HermesTools\ffmpeg\bin\ffmpeg.exe",
  "D:\HermesTools\ffmpeg\bin\ffmpeg.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if ($ffmpegCandidates.Count -gt 0) { $ffmpegFound = $true }

# --- 2. Python environment -------------------------------------------------
if (-not (Test-Path "$RepoRoot\.venv\Scripts\python.exe")) {
  Write-Host "Creating .venv..."
  if ($hasUv) { uv venv .venv } else { python -m venv .venv }
} else {
  Write-Host ".venv exists - reusing." -ForegroundColor Green
}
$Py = "$RepoRoot\.venv\Scripts\python.exe"

Write-Host "Installing this repo (editable) + dependencies..."
if ($hasUv) {
  uv pip install --python "$Py" -e . --no-deps
  uv pip install --python "$Py" -r requirements.txt
} else {
  & $Py -m pip install --upgrade pip | Out-Null
  & $Py -m pip install -e . --no-deps
  & $Py -m pip install -r requirements.txt
}
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed." }

# --- 3. Frontend (web UI) ---------------------------------------------------
if ($hasNode -and (Test-Path "$RepoRoot\web\package.json")) {
  Write-Host "Installing web dependencies..."
  Push-Location "$RepoRoot\web"
  if (Test-Path "package-lock.json") { npm ci --no-audit --no-fund } else { npm install --no-audit --no-fund }
  Pop-Location
}

# --- 4. Environment file ----------------------------------------------------
if (-not (Test-Path "$RepoRoot\.env")) {
  if (Test-Path "$RepoRoot\.env.example") {
    Copy-Item "$RepoRoot\.env.example" "$RepoRoot\.env"
    Write-Host ".env created from .env.example - edit it and add secrets." -ForegroundColor Yellow
  } else {
    Write-Warning ".env.example missing - create .env manually."
  }
} else {
  Write-Host ".env exists - not overwriting." -ForegroundColor Green
}

# --- 5. Data root -----------------------------------------------------------
$dataDir = $null
if (Test-Path "$RepoRoot\.env") {
  $line = (Get-Content "$RepoRoot\.env" | Where-Object { $_ -match '^HERMES_DATA_DIR=' } | Select-Object -First 1)
  if ($line) { $dataDir = $line.Substring($line.IndexOf('=') + 1).Trim().Trim('"',"'") }
}
if (-not $dataDir) { $dataDir = "D:\work\hermes-agent-data" }
try { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null; Write-Host "Data root: $dataDir" -ForegroundColor Green }
catch { Write-Warning "Cannot create data dir $dataDir : $_" }

# --- 6. Verify ---------------------------------------------------------------
Write-Host ""
Write-Host "=== Verification (no paid calls) ==="
& $Py -c "import sys; sys.path.insert(0, r'$RepoRoot'); import hermes, providers, mcp_servers, workers; print('  hermes  :', hermes.__file__); print('  import  : OK')"
if ($ffmpegFound) { Write-Host "  ffmpeg  : FOUND" -ForegroundColor Green } else { Write-Host "  ffmpeg  : MISSING (set FFMPEG_PATH or install ffmpeg)" -ForegroundColor Yellow }
Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Cyan
Write-Host "Next: edit .env for secrets, then run  .\start.ps1"
