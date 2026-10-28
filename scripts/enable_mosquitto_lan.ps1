<#
.SYNOPSIS
  Make Mosquitto listen on all interfaces (including Windows hotspot 192.168.137.1)
  and allow anonymous connections. Run this script as Administrator.
#>
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$conf = "C:\Program Files\mosquitto\mosquitto.conf"
$backup = "$conf.bak"
if (-not (Test-Path $backup)) { Copy-Item $conf $backup }

# Remove any existing listener lines, then append a LAN listener
$lines = Get-Content $conf | Where-Object { $_ -notmatch '^\s*listener\s' -and $_ -notmatch '^\s*allow_anonymous\s' }
$lines += ""
$lines += "# ARMOR: listen on all interfaces for ESP32 on Windows hotspot"
$lines += "listener 1883 0.0.0.0"
$lines += "allow_anonymous true"
Set-Content -Path $conf -Value $lines -Encoding ascii

Restart-Service mosquitto
Start-Sleep -Seconds 2

# Firewall rules (idempotent)
$ruleName = "Mosquitto MQTT 1883"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -Profile Any
}
$ruleName2 = "ARMOR Backend 8000"
if (-not (Get-NetFirewallRule -DisplayName $ruleName2 -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName2 -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
}

Write-Host "Mosquitto now listening on 0.0.0.0:1883. ESP can connect to 192.168.137.1:1883." -ForegroundColor Green