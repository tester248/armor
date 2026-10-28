<#
.SYNOPSIS
  Start the ARMOR stack (FastAPI backend + Streamlit dashboard).
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "armor-backend"
$RunDir = Join-Path $Root ".run"
$PidFile = Join-Path $RunDir "pids.json"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

# Stale PID detection: verify if existing processes are actually alive
if (Test-Path $PidFile) {
    $stale = $true
    try {
        $existing = Get-Content $PidFile -Raw | ConvertFrom-Json
        $bRunning = if ($existing.backend) { (Get-Process -Id $existing.backend -ErrorAction SilentlyContinue) -ne $null } else { $false }
        $dRunning = if ($existing.dashboard) { (Get-Process -Id $existing.dashboard -ErrorAction SilentlyContinue) -ne $null } else { $false }
        if ($bRunning -or $dRunning) {
            $stale = $false
        }
    } catch {
        $stale = $true
    }

    if (-not $stale) {
        Write-Host "Stack is already running. Run .\stop.ps1 first, or visit:" -ForegroundColor Yellow
        Write-Host "  Backend:   http://127.0.0.1:$($existing.backend_port)"
        Write-Host "  Dashboard: http://127.0.0.1:$($existing.dashboard_port)"
        exit 1
    } else {
        Write-Host "Cleaning up stale pid file from previous session..." -ForegroundColor DarkGray
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

# Auto-detect Python executable (prefers virtualenv if available)
$pythonExe = "python"
$venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$rootVenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} elseif (Test-Path $rootVenvPython) {
    $pythonExe = $rootVenvPython
}

$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$dashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "8501" }

$backend = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m","uvicorn","backend.main:app","--host","0.0.0.0","--port",$backendPort `
    -WorkingDirectory $BackendDir -PassThru

$env:ARMOR_API_URL = "http://127.0.0.1:$backendPort"
$dashboard = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m","streamlit","run","dashboard/app.py","--server.port",$dashboardPort,"--server.headless","true" `
    -WorkingDirectory $BackendDir -PassThru

@{ backend = $backend.Id; dashboard = $dashboard.Id; backend_port = $backendPort; dashboard_port = $dashboardPort } |
    ConvertTo-Json | Set-Content -Path $PidFile -Encoding utf8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  A.R.M.O.R. System Online" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Backend Gateway:    http://127.0.0.1:$backendPort" -ForegroundColor White
Write-Host "  API Docs (Swagger): http://127.0.0.1:$backendPort/docs" -ForegroundColor White
Write-Host "  Operator Dashboard: http://127.0.0.1:$dashboardPort" -ForegroundColor White
Write-Host "  PIDs: backend=$($backend.Id) dashboard=$($dashboard.Id)" -ForegroundColor DarkGray
Write-Host "  Run .\stop.ps1 to shut down cleanly." -ForegroundColor DarkGray
