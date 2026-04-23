# StankBot one-command dev startup (Windows)
# Starts the Python backend in ENV=dev and the Vite frontend dev server.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

# Ensure ENV=dev is set
$env:ENV = "dev"

Write-Host "Starting StankBot in dev mode..." -ForegroundColor Cyan

# Start backend
$backend = Start-Process -FilePath "python" -ArgumentList "-m", "stankbot" -WorkingDirectory $repoRoot -PassThru -NoNewWindow

# Give backend a moment to boot
Start-Sleep -Seconds 2

# Start frontend
Set-Location "$repoRoot\src\stankbot\web\frontend"
try {
    npm run dev
} finally {
    Write-Host "Shutting down backend (PID $($backend.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
}
