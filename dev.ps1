# RaplMail BROWSER dev mode: backend (no-auth dev token) + Vite UI in your browser.
# Best for fast iteration with Chrome/Edge DevTools. Opens http://localhost:1420.
#
# For the REAL native app window with hot reload, use:  .\dev-app.ps1   (runs `tauri dev`)
# To produce installers:                                .\build-desktop.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "Starting RaplMail backend (dev mode, no token)..." -ForegroundColor Cyan
$env:RAPLMAIL_DEV = "1"   # child process inherits this -> backend skips the auth token
$backend = Start-Process -PassThru -WindowStyle Minimized -WorkingDirectory "$root\backend" `
  -FilePath "$root\backend\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8765", "--reload"

Start-Sleep -Seconds 2
Write-Host "Starting UI at http://localhost:1420 (Ctrl+C to stop both)..." -ForegroundColor Cyan
Push-Location "$root\frontend"
try {
  & node "node_modules\vite\bin\vite.js" --open
} finally {
  Pop-Location
  Write-Host "Shutting down backend..." -ForegroundColor Cyan
  Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
}
