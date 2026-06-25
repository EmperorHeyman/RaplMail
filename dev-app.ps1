# RaplMail NATIVE dev mode: the real Tauri desktop window with frontend hot-reload
# and DevTools (right-click -> Inspect). This is the actual app, not a browser tab.
#
# It runs `tauri dev`, which: starts Vite, opens the native window, and spawns the
# bundled Python backend sidecar (with a per-launch token, exactly like production).
#
# NOTE: the sidecar is the *frozen* backend. If you change Python backend code,
# re-freeze it first:  .\build-desktop.ps1  (or just re-run this script, which
# rebuilds the sidecar when missing).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
$triple = "x86_64-pc-windows-msvc"
$sidecar = "$root\frontend\src-tauri\binaries\raplmail-backend-$triple.exe"

if (-not (Test-Path $sidecar)) {
  Write-Host "Sidecar missing - freezing backend first..." -ForegroundColor Yellow
  Push-Location "$root\backend"
  & .\.venv\Scripts\python.exe -m PyInstaller raplmail-backend.spec --noconfirm | Out-Null
  Pop-Location
  New-Item -ItemType Directory -Force "$root\frontend\src-tauri\binaries" | Out-Null
  Copy-Item "$root\backend\dist\raplmail-backend.exe" $sidecar -Force
}

Write-Host "Launching native app (tauri dev)... DevTools: right-click -> Inspect" -ForegroundColor Cyan
Push-Location "$root\frontend"
try { & npx tauri dev } finally { Pop-Location }
