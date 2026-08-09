param(
    [string]$RepositoryPath = "D:\HERMES\external\Douyin_TikTok_Download_API"
)

$ErrorActionPreference = "Stop"
$python = Join-Path $RepositoryPath ".venv\Scripts\python.exe"
$dataRoot = if ($env:HERMES_DATA_DIR) { $env:HERMES_DATA_DIR } else { "D:\HermesData" }
$logDir = Join-Path $dataRoot "logs"
$port = 5556
$baseUrl = "http://127.0.0.1:$port"

function Test-CompatibleCrawler {
    try {
        $schema = Invoke-RestMethod -Uri "$baseUrl/openapi.json" -TimeoutSec 3
        $route = $schema.paths.PSObject.Properties["/api/hybrid/video_data"]
        return $null -ne $route -and $null -ne $route.Value.get
    }
    catch {
        return $false
    }
}

if (Test-CompatibleCrawler) {
    Write-Host "TikTok crawler is already ready at $baseUrl"
    exit 0
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Crawler Python environment not found: $python"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutLog = Join-Path $logDir "tiktok-crawler.out.log"
$stderrLog = Join-Path $logDir "tiktok-crawler.err.log"
$arguments = @(
    "-m", "uvicorn", "app.main:app",
    "--host", "127.0.0.1",
    "--port", $port.ToString()
)

$process = Start-Process -FilePath $python `
    -ArgumentList $arguments `
    -WorkingDirectory $RepositoryPath `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden `
    -PassThru

for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) {
        $details = if (Test-Path $stderrLog) { Get-Content $stderrLog -Tail 20 | Out-String } else { "" }
        throw "TikTok crawler exited with code $($process.ExitCode). $details"
    }
    if (Test-CompatibleCrawler) {
        Write-Host "TikTok crawler ready at $baseUrl (PID $($process.Id))"
        Write-Host "Logs: $stdoutLog and $stderrLog"
        exit 0
    }
}

Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
throw "TikTok crawler started but did not expose the expected API within 15 seconds. See $stderrLog"
