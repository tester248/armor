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

if (Test-Path $PidFile) {
    Write-Host "Stack appears to be running (pid file exists). Run stop.ps1 first." -ForegroundColor Yellow
    exit 1
}

$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$dashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "8501" }

$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m","uvicorn","backend.main:app","--host","0.0.0.0","--port",$backendPort `
    -WorkingDirectory $BackendDir -PassThru

$env:ARMOR_API_URL = "http://127.0.0.1:$backendPort"
$dashboard = Start-Process -FilePath "python" `
    -ArgumentList "-m","streamlit","run","dashboard/app.py","--server.port",$dashboardPort,"--server.headless","true" `
    -WorkingDirectory $BackendDir -PassThru -Environment @{ ARMOR_API_URL = "http://127.0.0.1:$backendPort" }

@{ backend = $backend.Id; dashboard = $dashboard.Id; backend_port = $backendPort; dashboard_port = $dashboardPort } |
    ConvertTo-Json | Set-Content -Path $PidFile -Encoding utf8

Write-Host "ARMOR started." -ForegroundColor Green
Write-Host "  Backend:   http://127.0.0.1:$backendPort"
Write-Host "  Dashboard: http://127.0.0.1:$dashboardPort"
Write-Host "  PIDs: backend=$($backend.Id) dashboard=$($dashboard.Id)"