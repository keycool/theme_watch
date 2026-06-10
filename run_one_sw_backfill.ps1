$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "py"
$logPath = Join-Path $scriptDir "sw_backfill_scheduler.log"

$command = @(
    ".\backfill_sw_daily_history.py"
    "--start-date", "20240101"
    "--end-date", "20260630"
    "--chunk-open-days", "5"
    "--max-new-fetches", "1"
    "--sleep-seconds", "0"
)

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] scheduled backfill start" | Out-File -FilePath $logPath -Append -Encoding utf8

Push-Location $scriptDir
try {
    & $python @command *>&1 | Tee-Object -FilePath $logPath -Append
    $exitCode = $LASTEXITCODE
    $endTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$endTimestamp] scheduled backfill exit_code=$exitCode" | Out-File -FilePath $logPath -Append -Encoding utf8
    exit $exitCode
} finally {
    Pop-Location
}
