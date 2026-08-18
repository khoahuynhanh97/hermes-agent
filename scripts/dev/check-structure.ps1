<#
.SYNOPSIS
Repository structure guard wrapper for Hermes.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Script = Join-Path $RepoRoot "scripts\dev\check_repository_structure.py"

& $Python $Script
exit $LASTEXITCODE
