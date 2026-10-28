# Build the RaplMail desktop app + signed Windows installers.
#
# Usage:
#   .\build-desktop.ps1                 # bump patch (0.1.0 -> 0.1.1), then build
#   .\build-desktop.ps1 -Bump minor     # 0.1.0 -> 0.2.0
#   .\build-desktop.ps1 -Bump major     # 0.1.0 -> 1.0.0
#   .\build-desktop.ps1 -Version 1.2.3  # set an exact version
#   .\build-desktop.ps1 -NoBump         # keep the current version
#   .\build-desktop.ps1 -Version 1.2.3 -Release
#                                       # signed + staged for the website (site-dist/)
#
# Output: frontend/src-tauri/target/release/bundle/{nsis,msi}/...
# With -Release also site-dist/ (website + updates/latest.json + installers): upload
# it to raplmail.em-production.eu and every installed RaplMail offers the update.

param(
  [ValidateSet("patch", "minor", "major")] [string]$Bump = "patch",
  [string]$Version = "",
  [switch]$NoBump,
  [switch]$Sign,    # also produce signed updater artifacts (needs the signing key)
  [switch]$Release  # signed (required) + stage the website release (stage-release.py)
)
if ($Release) { $Sign = $true }

# NOTE: "Continue", not "Stop" -- PyInstaller/npx write progress to stderr, and
# under "Stop" PowerShell 5.1 turns the first stderr line into a fatal
# NativeCommandError. We check $LASTEXITCODE after each native command instead,
# and use -ErrorAction Stop on the cmdlets that matter.
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
$triple = "x86_64-pc-windows-msvc"

$confPath = "$root\frontend\src-tauri\tauri.conf.json"
$cargoPath = "$root\frontend\src-tauri\Cargo.toml"
$pkgPath = "$root\frontend\package.json"

# --- version --------------------------------------------------------------
$current = ([regex]'"version"\s*:\s*"([0-9]+\.[0-9]+\.[0-9]+)"').Match((Get-Content -Raw $confPath)).Groups[1].Value
if (-not $current) { throw "Could not read current version from tauri.conf.json" }

if ($NoBump) {
  $new = $current
}
elseif ($Version) {
  if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "-Version must be x.y.z" }
  $new = $Version
}
else {
  $p = $current.Split('.') | ForEach-Object { [int]$_ }
  switch ($Bump) {
    "major" { $p[0]++; $p[1] = 0; $p[2] = 0 }
    "minor" { $p[1]++; $p[2] = 0 }
    default { $p[2]++ }
  }
  $new = "$($p[0]).$($p[1]).$($p[2])"
}

# Write UTF-8 WITHOUT a BOM. PowerShell 5.1's `Set-Content -Encoding utf8` adds a
# BOM, which breaks JSON/TOML tooling (vite can't read "type":"module", etc.).
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-NoBom([string]$path, [string]$content) {
  [System.IO.File]::WriteAllText($path, $content, $utf8NoBom)
}

if ($new -ne $current) {
  Write-Host "Version: $current -> $new" -ForegroundColor Yellow
  $verRepl = '${1}' + $new + '${2}'
  Write-NoBom $confPath ((Get-Content -Raw $confPath) -replace '("version"\s*:\s*")[0-9]+\.[0-9]+\.[0-9]+(")', $verRepl)
  Write-NoBom $pkgPath ((Get-Content -Raw $pkgPath) -replace '("version"\s*:\s*")[0-9]+\.[0-9]+\.[0-9]+(")', $verRepl)
  # Cargo.toml: the [package] version is the only line that starts with `version =`
  Write-NoBom $cargoPath ((Get-Content -Raw $cargoPath) -replace '(?m)^(version\s*=\s*")[0-9]+\.[0-9]+\.[0-9]+(")', $verRepl)
}
else {
  Write-Host "Version: $new (unchanged)" -ForegroundColor Yellow
}

# Kill any running app / sidecar first. A leftover backend process - including
# the PyInstaller onefile CHILD, which is named "raplmail-backend-<triple>" -
# holds an open handle on the bundled sidecar exe. If it's locked when we copy
# the freshly-frozen binary over it, the OLD binary stays in place and the build
# silently ships a stale backend (e.g. missing new endpoints). Match the prefix
# so both the short name and the full triple-named child are killed.
Write-Host "Stopping any running RaplMail processes..." -ForegroundColor DarkCyan
Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like "raplmail*" } |
  ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {} }
Start-Sleep -Seconds 2

# --- 1/3 freeze backend ---------------------------------------------------
Write-Host "[1/3] Freezing Python backend (PyInstaller)..." -ForegroundColor Cyan
Push-Location "$root\backend"
# --clean wipes PyInstaller's cache every build. Without it the incremental
# cache can serve STALE bytecode for changed modules (e.g. an edited app/api
# file), silently shipping a backend that lacks your latest changes.
& .\.venv\Scripts\python.exe -m PyInstaller raplmail-backend.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "PyInstaller failed (exit $LASTEXITCODE)" }
Pop-Location

# --- 2/3 place sidecar ----------------------------------------------------
Write-Host "[2/3] Placing sidecar binary..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force "$root\frontend\src-tauri\binaries" | Out-Null
$sidecarSrc = "$root\backend\dist\raplmail-backend.exe"
$sidecarDst = "$root\frontend\src-tauri\binaries\raplmail-backend-$triple.exe"
$placed = $false
for ($i = 1; $i -le 8; $i++) {
  try { Copy-Item $sidecarSrc $sidecarDst -Force -ErrorAction Stop; $placed = $true; break }
  catch { Write-Host "  sidecar locked, retrying ($i)..." -ForegroundColor Yellow; Start-Sleep -Seconds 2 }
}
if (-not $placed) { throw "Could not replace the sidecar binary (locked). Close RaplMail and retry." }

# --- 3/3 build app --------------------------------------------------------
# The build itself never signs: with createUpdaterArtifacts on, `tauri build`
# decrypts the key and - since it reads an empty TAURI_SIGNING_PRIVATE_KEY_PASSWORD
# as "not set" - waits on a password prompt forever. So it builds plain
# installers, and -Sign / -Release sign them afterwards with `tauri signer sign`
# (the same signature: over the installer file, which is what the updater checks).
Write-Host "[3/3] Building Tauri app + installers..." -ForegroundColor Cyan
$keyPath = "$root\frontend\src-tauri\.tauri-updater.key"
if ($Sign -and -not (Test-Path $keyPath)) {
  if ($Release) { throw "-Release needs the signing key at $keyPath (installed apps only accept updates signed with it)" }
  Write-Host "  (-Sign given but no key at $keyPath; building unsigned)" -ForegroundColor DarkYellow
  $Sign = $false
}
Push-Location "$root\frontend"
try {
  $cfg = Join-Path $env:TEMP "raplmail-noupdater.json"
  '{"bundle":{"createUpdaterArtifacts":false}}' | Set-Content -Encoding ascii $cfg
  & npx tauri build --config $cfg
  if ($LASTEXITCODE -ne 0) { throw "tauri build failed (exit $LASTEXITCODE)" }

  if ($Sign) {
    # The key has an empty password. "--password=" (not -p "") because
    # PowerShell 5.1 drops an empty "" argument on the way to a native command.
    Write-Host "  Signing the installers for the updater..." -ForegroundColor DarkCyan
    $installers = Get-ChildItem "$root\frontend\src-tauri\target\release\bundle" -Recurse -Include *.msi, *-setup.exe |
      Where-Object { $_.Name -like "*_$($new)_*" }
    if (-not $installers) { throw "no $new installers found to sign" }
    foreach ($f in $installers) {
      Remove-Item "$($f.FullName).sig" -ErrorAction SilentlyContinue
      & npx tauri signer sign -f $keyPath "--password=" $f.FullName | Out-Null
      if ($LASTEXITCODE -ne 0 -or -not (Test-Path "$($f.FullName).sig")) { throw "signing $($f.Name) failed" }
      Write-Host "    signed $($f.Name)"
    }
  }
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Done (v$new). Installers:" -ForegroundColor Green
Get-ChildItem "$root\frontend\src-tauri\target\release\bundle" -Recurse -Include *.msi, *-setup.exe |
  Where-Object { $_.Name -like "*_$($new)_*" } |
  ForEach-Object { Write-Host "  $($_.FullName)" }

if ($Release) {
  # Checks the signatures against the app's public key and writes site-dist/.
  Write-Host ""
  Write-Host "Staging the website release..." -ForegroundColor Cyan
  & "$root\backend\.venv\Scripts\python.exe" "$root\stage-release.py" $new
  if ($LASTEXITCODE -ne 0) { throw "stage-release.py failed (exit $LASTEXITCODE)" }
}
