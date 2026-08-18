param(
    [int]$Port = 20128,
    [switch]$Background,
    [switch]$ShowLogs
)

$command = Get-Command 9router.cmd -ErrorAction Stop
$arguments = @("--port", "$Port", "--host", "127.0.0.1", "--no-browser", "--skip-update")
if ($ShowLogs) {
    $arguments += "--log"
}

if ($Background) {
    $process = Start-Process -FilePath $command.Source -ArgumentList $arguments -WindowStyle Hidden -PassThru
    Write-Output "9Router started on http://127.0.0.1:$Port (PID $($process.Id))"
    exit 0
}

& $command.Source @arguments
exit $LASTEXITCODE
