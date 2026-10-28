<#
.SYNOPSIS
  Stop the ARMOR stack started by start.ps1.
#>
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root ".run\pids.json"

if (-not (Test-Path $PidFile)) {
    Write-Host "No pid file found; nothing to stop." -ForegroundColor Yellow
    exit 0
}

$pids = Get-Content $PidFile -Raw | ConvertFrom-Json
foreach ($id in @($pids.backend, $pids.dashboard)) {
    if ($id) {
        try { Stop-Process -Id $id -Force -ErrorAction Stop; Write-Host "Stopped process $id" }
        catch { Write-Host "Process $id not running." }
    }
}
Remove-Item $PidFile -Force
Write-Host "ARMOR stopped." -ForegroundColor Green