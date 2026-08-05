param(
    [switch]$UI,
    [switch]$NoServices,
    [switch]$SkipRouterCheck,
    [switch]$ServicesOnly,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$HermesArgs
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$Python = "$RepoRoot\.venv\Scripts\python.exe"
$Hermes = "$RepoRoot\.venv\Scripts\hermes.exe"
if (-not (Test-Path $Python) -or -not (Test-Path $Hermes)) {
    throw "Repo-local Hermes runtime is missing. Run .\setup.ps1 first."
}

if (Test-Path "$RepoRoot\.env") {
    foreach ($line in Get-Content "$RepoRoot\.env") {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim().Trim('"', "'")
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}
if (-not $env:HERMES_DATA_DIR) {
    $env:HERMES_DATA_DIR = Join-Path (Split-Path -Parent $RepoRoot) "hermes-agent-data"
}
if (-not $env:HERMES_DB_PATH) {
    $env:HERMES_DB_PATH = Join-Path $env:HERMES_DATA_DIR "db\hermes.db"
}
New-Item -ItemType Directory -Path $env:HERMES_DATA_DIR -Force | Out-Null

$verificationCode = "import importlib.util,pathlib; root=pathlib.Path(r'$RepoRoot').resolve(); names=('cli','hermes','hermes_cli','run_agent'); paths=[pathlib.Path(importlib.util.find_spec(name).origin).resolve() for name in names]; print(';'.join(map(str,paths))); raise SystemExit(0 if all(path == root or root in path.parents for path in paths) else 1)"
$verification = & $Python -I -c $verificationCode
if ($LASTEXITCODE -ne 0) {
    throw "Hermes imports resolve outside this repository: $verification"
}

function Test-Router {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:20128/api/health" -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

if (-not $SkipRouterCheck -and -not (Test-Router)) {
    if (-not (Get-Command "9router.cmd" -ErrorAction SilentlyContinue)) {
        throw "9Router is unavailable on 127.0.0.1:20128 and 9router.cmd is not installed."
    }
    & "$RepoRoot\scripts\start_9router_local.ps1" -Background
    for ($attempt = 0; $attempt -lt 15 -and -not (Test-Router); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Router)) {
        throw "9Router did not become healthy on 127.0.0.1:20128."
    }
}

$ownedProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
$logDir = Join-Path $env:HERMES_DATA_DIR "logs\runtime"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

try {
    if (-not $NoServices) {
        $videoDb = Join-Path $env:HERMES_DATA_DIR "db\video.sqlite"
        $videoWs = Join-Path $env:HERMES_DATA_DIR "workspaces\video"
        $videoWorker = Start-Process -FilePath $Python -ArgumentList "-m", "workers.job_worker", "--daemon", "--db-path", $videoDb, "--workspace", $videoWs -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $logDir "video-worker.out.log") -RedirectStandardError (Join-Path $logDir "video-worker.err.log") -WindowStyle Hidden -PassThru
        $ownedProcesses.Add($videoWorker)

        $vfDb = Join-Path $env:HERMES_DATA_DIR "db\video_factory.sqlite"
        $vfWs = Join-Path $env:HERMES_DATA_DIR "workspaces\video-factory"
        $vfWorker = Start-Process -FilePath $Python -ArgumentList "-m", "workers.job_worker", "--daemon", "--db-path", $vfDb, "--workspace", $vfWs -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $logDir "video-factory-worker.out.log") -RedirectStandardError (Join-Path $logDir "video-factory-worker.err.log") -WindowStyle Hidden -PassThru
        $ownedProcesses.Add($vfWorker)

        $backend = Start-Process -FilePath $Python -ArgumentList "web_studio.py" -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $logDir "backend.out.log") -RedirectStandardError (Join-Path $logDir "backend.err.log") -WindowStyle Hidden -PassThru
        $ownedProcesses.Add($backend)
        Write-Host "Backend: http://127.0.0.1:8000 | Video worker PID: $($videoWorker.Id) | Video Factory worker PID: $($vfWorker.Id)"
    }

    if ($UI) {
        if (-not (Test-Path "$RepoRoot\web\node_modules")) {
            throw "Web dependencies are missing. Run .\setup.ps1 first."
        }
        $npm = (Get-Command "npm.cmd" -ErrorAction Stop).Source
        $uiProcess = Start-Process -FilePath $npm -ArgumentList "run", "dev" -WorkingDirectory "$RepoRoot\web" -RedirectStandardOutput (Join-Path $logDir "ui.out.log") -RedirectStandardError (Join-Path $logDir "ui.err.log") -WindowStyle Hidden -PassThru
        $ownedProcesses.Add($uiProcess)
        Write-Host "UI: http://127.0.0.1:3000"
    }

    if ($ServicesOnly) {
        Write-Host "Services are running. Press Ctrl+C to stop."
        while ($true) { Start-Sleep -Seconds 2 }
    } else {
        & $Hermes @HermesArgs
        exit $LASTEXITCODE
    }
} finally {
    foreach ($process in $ownedProcesses) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
