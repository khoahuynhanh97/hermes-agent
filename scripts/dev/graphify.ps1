<#
.SYNOPSIS
Canonical Graphify wrapper for Hermes Agent Platform.

.DESCRIPTION
Executes Graphify operations targeting external caches in HERMES_DATA_DIR/caches/graphify-out/
without polluting the source repository root.
#>
param(
    [Parameter(Position = 0)]
    [string]$Command = "query",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DataDir = if ($env:HERMES_DATA_DIR) { $env:HERMES_DATA_DIR } else { Join-Path (Split-Path -Parent $RepoRoot) "hermes-agent-data" }
$CacheDir = Join-Path $DataDir "caches"
$GraphifyOut = Join-Path $CacheDir "graphify-out"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $GraphifyOut)) {
    New-Item -ItemType Directory -Path $GraphifyOut -Force | Out-Null
}

# Set Graphify environment indicators
Set-Content -Path (Join-Path $GraphifyOut ".graphify_root") -Value $RepoRoot -Encoding UTF8
Set-Content -Path (Join-Path $GraphifyOut ".graphify_python") -Value $Python -Encoding UTF8

$graphJson = Join-Path $GraphifyOut "graph.json"
$helperPy = Join-Path $RepoRoot "scripts\dev\graphify_graph_client.py"

if ($Command -eq "query") {
    $queryString = ($Args -join " ")
    Write-Host "[Graphify Query] Question: $queryString" -ForegroundColor Cyan
    Write-Host "[Graphify Cache] $graphJson" -ForegroundColor DarkGray
    if (-not (Test-Path $graphJson)) {
        Write-Warning "Graph JSON not found at $graphJson. Run build/update first."
        exit 1
    }
    Push-Location $CacheDir
    try {
        & $Python $helperPy "query" $graphJson $queryString
    } finally {
        Pop-Location
    }
} elseif ($Command -eq "explain") {
    $node = ($Args -join " ")
    Push-Location $CacheDir
    try {
        & $Python $helperPy "explain" $graphJson $node
    } finally {
        Pop-Location
    }
} elseif ($Command -eq "list_paths") {
    Push-Location $CacheDir
    try {
        & $Python $helperPy "list_paths" $graphJson
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Running Graphify $Command with args: $Args"
    Push-Location $CacheDir
    try {
        # General graphify execution
        Write-Host "Graphify cache ready at $GraphifyOut"
    } finally {
        Pop-Location
    }
}
