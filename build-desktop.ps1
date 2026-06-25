# Build the RaplMail desktop app + Windows installers.
# Produces frontend/src-tauri/target/release/raplmail.exe and installers under
# frontend/src-tauri/target/release/bundle/.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
$triple = "x86_64-pc-windows-msvc"

Write-Host "[1/3] Freezing Python backend (PyInstaller)..." -ForegroundColor Cyan
Push-Location "$root\backend"
& .\.venv\Scripts\python.exe -m PyInstaller raplmail-backend.spec --noconfirm | Out-Null
Pop-Location

Write-Host "[2/3] Placing sidecar binary..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force "$root\frontend\src-tauri\binaries" | Out-Null
Copy-Item "$root\backend\dist\raplmail-backend.exe" `
  "$root\frontend\src-tauri\binaries\raplmail-backend-$triple.exe" -Force

Write-Host "[3/3] Building Tauri app + installers..." -ForegroundColor Cyan
Push-Location "$root\frontend"
& npx tauri build
Pop-Location

Write-Host "`nDone. Installers:" -ForegroundColor Green
Get-ChildItem "$root\frontend\src-tauri\target\release\bundle" -Recurse -Include *.msi, *-setup.exe |
  ForEach-Object { Write-Host "  $($_.FullName)" }
