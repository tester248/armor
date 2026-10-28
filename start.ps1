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

# Auto-detect a Python that actually has the backend dependencies installed.
# A half-built .venv used to be picked blindly, which made the stack die silently.
$candidates = @(
    (Join-Path $BackendDir ".venv\Scripts\python.exe"),
    (Join-Path $Root ".venv\Scripts\python.exe"),
    "python"
)
$probeScript = Join-Path $RunDir "probe_deps.py"
Set-Content -Path $probeScript -Value "import uvicorn, fastapi, streamlit, ultralytics" -Encoding ascii

$pythonExe = $null
foreach ($cand in $candidates) {
    if ($cand -ne "python" -and -not (Test-Path $cand)) { continue }
    try {
        $probe = Start-Process -FilePath $cand `
            -ArgumentList $probeScript `
            -NoNewWindow -Wait -PassThru -ErrorAction Stop `
            -RedirectStandardOutput (Join-Path $RunDir "probe.log") `
            -RedirectStandardError (Join-Path $RunDir "probe.err.log")
        if ($probe.ExitCode -eq 0) { $pythonExe = $cand; break }
    } catch { }
}
if (-not $pythonExe) {
    Write-Host "No Python interpreter with ARMOR dependencies found." -ForegroundColor Red
    Write-Host "Install them with:" -ForegroundColor Yellow
    Write-Host "  python -m pip install -r armor-backend\requirements.txt" -ForegroundColor Yellow
    exit 1
}
Write-Host "Using Python: $pythonExe" -ForegroundColor DarkGray

$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$dashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "8501" }

$backendLog = Join-Path $RunDir "backend.log"
$dashboardLog = Join-Path $RunDir "dashboard.log"
$backendErrLog = Join-Path $RunDir "backend.err.log"

$backend = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m","uvicorn","backend.main:app","--host","0.0.0.0","--port",$backendPort `
    -WorkingDirectory $BackendDir -PassThru `
    -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrLog

# Wait until the gateway actually answers before reporting success.
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 750
    if ($backend.HasExited) { break }
    try {
        $null = Invoke-WebRequest "http://127.0.0.1:$backendPort/api/v1/health" -UseBasicParsing -TimeoutSec 2
        $ready = $true
        break
    } catch { }
}
if (-not $ready) {
    Write-Host "Backend failed to start on port $backendPort." -ForegroundColor Red
    foreach ($log in @($backendErrLog, $backendLog)) {
        if (Test-Path $log) {
            Write-Host "--- $log ---" -ForegroundColor DarkGray
            Get-Content $log -Tail 20
        }
    }
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
    exit 1
}

$env:ARMOR_API_URL = "http://127.0.0.1:$backendPort"
$dashboard = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m","streamlit","run","dashboard/app.py","--server.port",$dashboardPort,"--server.headless","true" `
    -WorkingDirectory $BackendDir -PassThru `
    -RedirectStandardOutput $dashboardLog -RedirectStandardError (Join-Path $RunDir "dashboard.err.log")

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
