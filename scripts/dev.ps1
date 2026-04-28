# StankBot one-command dev startup (Windows)
# Starts the Python backend in ENV=dev-mock and the Vite frontend dev server.
# Uses health-check polling instead of a blind sleep for reliable startup.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".stankbot_backend.pid"

$env:ENV = "dev-mock"
$env:PYTHONPATH = "$repoRoot\src"

# ---- Cleanup handler ----
function Invoke-Cleanup {
    if (Test-Path $pidFile) {
        try {
            $savedPid = [int](Get-Content $pidFile -Raw -ErrorAction SilentlyContinue)
            if ($savedPid) {
                $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
                if ($proc) {
                    Write-Host "Shutting down backend (PID $savedPid)..." -ForegroundColor Yellow
                    Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
                }
            }
        } catch {}
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Starting StankBot in dev-mock mode..." -ForegroundColor Cyan

# Start backend
$backend = Start-Process -FilePath "python" -ArgumentList "-m", "stankbot" `
    -WorkingDirectory $repoRoot -PassThru -NoNewWindow
$backend.Id | Out-File -FilePath $pidFile
Write-Host "Backend PID: $($backend.Id)"

# Wait for backend to be ready via health check
Write-Host -NoNewline "Waiting for backend..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/healthz" `
            -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Write-Host " ready."
            $ready = $true
            break
        }
    } catch {}
    if ($backend.HasExited) {
        Write-Host ""
        Write-Host "ERROR: Backend process died during startup." -ForegroundColor Red
        exit 1
    }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    Write-Host ""
    Write-Host "ERROR: Backend did not become ready within 30s." -ForegroundColor Red
    exit 1
}

# Start frontend
Set-Location "$repoRoot\src\stankbot\web\frontend"
try {
    npm run dev
} finally {
    Invoke-Cleanup
}
