param(
    [switch]$SkipWeb
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path (Split-Path -Parent $RepoRoot) "hermes-agent-data"
$HermesHome = if ($env:HERMES_HOME) {
    $env:HERMES_HOME
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "hermes"
} else {
    Join-Path $HOME ".hermes"
}
Set-Location $RepoRoot

Write-Host "=== Hermes Personal Setup ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "python")) {
    throw "Python 3.10-3.13 is required."
}
$version = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
$parts = $version.Split('.')
if ([int]$parts[0] -ne 3 -or [int]$parts[1] -lt 10 -or [int]$parts[1] -ge 14) {
    throw "Python 3.10-3.13 is required (found $version)."
}

$hasUv = Test-Command "uv"
if (-not (Test-Path "$RepoRoot\.venv\Scripts\python.exe")) {
    Write-Host "Creating repo-local .venv..."
    if ($hasUv) { & uv venv .venv } else { & python -m venv .venv }
}
$Python = "$RepoRoot\.venv\Scripts\python.exe"

Write-Host "Installing this repository editable..."
if ($hasUv) {
    & uv pip install --python $Python -e ".[dev]"
} else {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -e ".[dev]"
}
if ($LASTEXITCODE -ne 0) {
    throw "Editable installation failed."
}

if (-not $SkipWeb -and (Test-Command "node") -and (Test-Path "$RepoRoot\web\package.json")) {
    Push-Location "$RepoRoot\web"
    try {
        if (Test-Path "package-lock.json") {
            & npm ci --no-audit --no-fund
        } else {
            & npm install --no-audit --no-fund
        }
        if ($LASTEXITCODE -ne 0) { throw "Web dependency installation failed." }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path "$RepoRoot\.env")) {
    Copy-Item "$RepoRoot\.env.example" "$RepoRoot\.env"
    Write-Host ".env created from .env.example; credentials remain empty." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
& $Python "$RepoRoot\scripts\configure_canonical_runtime.py" `
    --repo-root $RepoRoot `
    --hermes-home $HermesHome `
    --data-dir $DataDir `
    --env-file "$RepoRoot\.env"
if ($LASTEXITCODE -ne 0) {
    throw "Canonical runtime configuration failed."
}

$verificationCode = "import importlib.util,pathlib; root=pathlib.Path(r'$RepoRoot').resolve(); names=('cli','hermes','hermes_cli','run_agent'); paths=[pathlib.Path(importlib.util.find_spec(name).origin).resolve() for name in names]; print(';'.join(map(str,paths))); raise SystemExit(0 if all(path == root or root in path.parents for path in paths) else 1)"
$verification = & $Python -I -c $verificationCode
if ($LASTEXITCODE -ne 0) {
    throw "Hermes imports do not resolve from this repository: $verification"
}

Write-Host "Setup complete." -ForegroundColor Green
Write-Host "CLI: $RepoRoot\.venv\Scripts\hermes.exe"
Write-Host "Data: $DataDir"
Write-Host "Config/state: $HermesHome"
Write-Host "Run .\start.ps1"
