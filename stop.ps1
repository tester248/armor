<#
.SYNOPSIS
  Stop the ARMOR stack started by start.ps1 or lingering on ports 8000/8501.
#>
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root ".run\pids.json"

$stoppedCount = 0

if (Test-Path $PidFile) {
    try {
        $pids = Get-Content $PidFile -Raw | ConvertFrom-Json
        foreach ($id in @($pids.backend, $pids.dashboard)) {
            if ($id) {
                try {
                    Stop-Process -Id $id -Force -ErrorAction Stop
                    Write-Host "Stopped process $id" -ForegroundColor Green
                    $stoppedCount++
                } catch {
                    Write-Host "Process $id was not running." -ForegroundColor DarkGray
                }
            }
        }
    } catch {}
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# Also ensure lingering processes on ports 8000 and 8501 are cleared
$ports = @(8000, 8501)
foreach ($p in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess -and $c.OwningProcess -ne $PID) {
            try {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
                Write-Host "Stopped lingering process on port $p (PID $($c.OwningProcess))" -ForegroundColor Green
                $stoppedCount++
            } catch {}
        }
    }
}

if ($stoppedCount -gt 0) {
    Write-Host "ARMOR stopped ($stoppedCount process(es) terminated)." -ForegroundColor Green
} else {
    Write-Host "ARMOR stack is not running. Nothing to stop." -ForegroundColor Yellow
}
