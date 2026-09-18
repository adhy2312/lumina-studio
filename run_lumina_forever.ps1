# Lumina Studio 24/7 Resilient Runner & Watchdog
# Keeps Python Server and Ngrok Tunnel persistently alive with automatic crash recovery.

$Host.UI.RawUI.WindowTitle = "Lumina Studio 24/7 Watchdog"
$LuminaDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $LuminaDir

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "   LUMINA STUDIO 24/7 PERSISTENT BACKGROUND ENGINE   " -ForegroundColor Yellow
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Directory: $LuminaDir"
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor DarkGray
Write-Host ""

$serverProcess = $null
$ngrokProcess = $null

function Start-Server {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting Lumina Python Server (Port 7070)..." -ForegroundColor Green
    $script:serverProcess = Start-Process python -ArgumentList "server.py" -PassThru -NoNewWindow
}

function Start-Ngrok {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting Ngrok Cloud Tunnel..." -ForegroundColor Green
    $script:ngrokProcess = Start-Process ngrok -ArgumentList "http 7070 --url https://epidermis-coliseum-masses.ngrok-free.dev" -PassThru -NoNewWindow
}

Start-Server
Start-Ngrok

try {
    while ($true) {
        Start-Sleep -Seconds 6

        # Check Python Server
        if ($null -eq $script:serverProcess -or $script:serverProcess.HasExited) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Python Server exited! Auto-restarting..." -ForegroundColor Red
            Start-Server
        }

        # Check Ngrok Tunnel
        if ($null -eq $script:ngrokProcess -or $script:ngrokProcess.HasExited) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Ngrok Tunnel exited! Auto-restarting..." -ForegroundColor Red
            Start-Ngrok
        }

        # Health ping test
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:7070/api/ping" -TimeoutSec 3 -ErrorAction SilentlyContinue
        } catch {
            # Transient server lag
        }
    }
} finally {
    Write-Host "`nStopping Lumina services..." -ForegroundColor Yellow
    if ($script:serverProcess -and !$script:serverProcess.HasExited) { Stop-Process -Id $script:serverProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($script:ngrokProcess -and !$script:ngrokProcess.HasExited) { Stop-Process -Id $script:ngrokProcess.Id -Force -ErrorAction SilentlyContinue }
}
