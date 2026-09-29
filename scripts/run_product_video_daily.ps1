param(
    [Parameter(Mandatory = $true)]
    [string]$DbPath,
    [Parameter(Mandatory = $true)]
    [string]$InboxRoot,
    [string]$LogPath = "D:\work\hermes-agent-data\logs\product-video-daily.log",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Hermes Python runtime is missing: $python"
}

$logDirectory = Split-Path -Parent $LogPath
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$today = (Get-Date).ToString("yyyy-MM-dd")
$operation = if ($CheckOnly) { "completion check" } else { "intake" }
"[$(Get-Date -Format o)] Product Video daily $operation for $today" |
    Tee-Object -FilePath $LogPath -Append

Push-Location $repoRoot
$exitCode = 1
try {
    $ErrorActionPreference = "Continue"
    if ($CheckOnly) {
        & $python -m hermes_personal.product_video.cli `
            --db-path $DbPath daily-status --date $today --minimum 3 2>&1 |
            ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { $_ } } |
            Tee-Object -FilePath $LogPath -Append
    }
    else {
        & $python -m hermes_personal.product_video.cli `
            --db-path $DbPath --inbox-root $InboxRoot `
            start --auto --limit 5 --minimum-daily 3 --date $today `
            --provider-mode configured 2>&1 |
            ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { $_ } } |
            Tee-Object -FilePath $LogPath -Append
    }
    $exitCode = $LASTEXITCODE
}
catch {
    "[$(Get-Date -Format o)] Daily intake failed: $_" |
        Tee-Object -FilePath $LogPath -Append
}
finally {
    Pop-Location
}

"[$(Get-Date -Format o)] Product Video daily $operation exited with code $exitCode" |
    Tee-Object -FilePath $LogPath -Append
exit $exitCode
