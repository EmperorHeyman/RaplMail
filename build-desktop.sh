#!/usr/bin/env bash
# Build the RaplMail desktop app for macOS (.app + .dmg).
#
# Usage:
#   ./build-desktop.sh                 # bump patch (0.1.0 -> 0.1.1), then build
#   ./build-desktop.sh --bump minor    # 0.1.0 -> 0.2.0
#   ./build-desktop.sh --bump major    # 0.1.0 -> 1.0.0
#   ./build-desktop.sh --version 1.2.3 # set an exact version
#   ./build-desktop.sh --no-bump       # keep the current version
#   ./build-desktop.sh --sign          # also produce signed updater artifacts
#                                      # (needs frontend/src-tauri/.tauri-updater.key)
#
# Output: frontend/src-tauri/target/release/bundle/{macos,dmg}/...
#
# Windows equivalent: build-desktop.ps1
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.cargo/bin:$PATH"
triple="$(rustc -Vv | awk '/host:/ {print $2}')"

bump="patch"; version=""; no_bump=0; sign=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bump) bump="$2"; shift 2 ;;
    --version) version="$2"; shift 2 ;;
    --no-bump) no_bump=1; shift ;;
    --sign) sign=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

conf="$root/frontend/src-tauri/tauri.conf.json"
cargo_toml="$root/frontend/src-tauri/Cargo.toml"
pkg="$root/frontend/package.json"

# --- version ---------------------------------------------------------------
current="$(sed -nE 's/.*"version"[[:space:]]*:[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' "$conf" | head -1)"
[ -n "$current" ] || { echo "Could not read current version from tauri.conf.json" >&2; exit 1; }

if [ "$no_bump" = 1 ]; then
  new="$current"
elif [ -n "$version" ]; then
  echo "$version" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "--version must be x.y.z" >&2; exit 2; }
  new="$version"
else
  IFS=. read -r maj min pat <<<"$current"
  case "$bump" in
    major) maj=$((maj + 1)); min=0; pat=0 ;;
    minor) min=$((min + 1)); pat=0 ;;
    patch) pat=$((pat + 1)) ;;
    *) echo "--bump must be patch|minor|major" >&2; exit 2 ;;
  esac
  new="$maj.$min.$pat"
fi

if [ "$new" != "$current" ]; then
  echo "Version: $current -> $new"
  sed -i '' -E "s/(\"version\"[[:space:]]*:[[:space:]]*\")[0-9]+\.[0-9]+\.[0-9]+(\")/\1$new\2/" "$conf" "$pkg"
  # Cargo.toml: the [package] version is the only line that starts with `version =`
  sed -i '' -E "s/^(version[[:space:]]*=[[:space:]]*\")[0-9]+\.[0-9]+\.[0-9]+(\")/\1$new\2/" "$cargo_toml"
else
  echo "Version: $new (unchanged)"
fi

# Kill any running app / sidecar so we never bundle a stale, locked backend.
echo "Stopping any running RaplMail processes..."
pkill -f "raplmail-backend" 2>/dev/null || true
pkill -x "RaplMail" 2>/dev/null || true
sleep 1

# --- 1/3 freeze backend ------------------------------------------------------
# --clean wipes PyInstaller's cache every build. Without it the incremental
# cache can serve STALE bytecode for changed modules, silently shipping a
# backend that lacks your latest changes.
echo "[1/3] Freezing Python backend (PyInstaller)..."
(cd "$root/backend" && ./.venv/bin/python -m PyInstaller raplmail-backend.spec --noconfirm --clean)

# --- 2/3 place sidecar -------------------------------------------------------
echo "[2/3] Placing sidecar binary..."
mkdir -p "$root/frontend/src-tauri/binaries"
cp "$root/backend/dist/raplmail-backend" "$root/frontend/src-tauri/binaries/raplmail-backend-$triple"
chmod +x "$root/frontend/src-tauri/binaries/raplmail-backend-$triple"

# --- 3/3 build app -----------------------------------------------------------
# Updater signing: tauri.conf has createUpdaterArtifacts=true, so the build
# needs the signing key. By default we skip updater artifacts (no key needed);
# pass --sign to produce signed updater artifacts from the gitignored key file.
echo "[3/3] Building Tauri app (.app + .dmg)..."
cd "$root/frontend"
key_path="$root/frontend/src-tauri/.tauri-updater.key"
if [ "$sign" = 1 ] && [ -f "$key_path" ]; then
  echo "  (signing updater artifacts)"
  TAURI_SIGNING_PRIVATE_KEY="$(cat "$key_path")" \
  TAURI_SIGNING_PRIVATE_KEY_PASSWORD="" \
  npx tauri build
else
  [ "$sign" = 1 ] && echo "  (--sign given but no key at $key_path; building unsigned)"
  npx tauri build --config '{"bundle":{"createUpdaterArtifacts":false}}'
fi

echo
echo "Done (v$new). Bundles:"
find "$root/frontend/src-tauri/target/release/bundle" \( -name "*.dmg" -o -name "*.app" \) -maxdepth 3 2>/dev/null | sed 's/^/  /'
