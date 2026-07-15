#!/usr/bin/env bash
# RaplMail NATIVE dev mode (macOS/Linux): the real Tauri desktop window with
# frontend hot-reload and DevTools (right-click -> Inspect). This is the actual
# app, not a browser tab.
#
# It runs `tauri dev`, which: starts Vite, opens the native window, and spawns
# the bundled Python backend sidecar (with a per-launch token, exactly like
# production).
#
# NOTE: the sidecar is the *frozen* backend. If you change Python backend code,
# re-freeze it first:  ./build-desktop.sh  (or just re-run this script, which
# rebuilds the sidecar when missing).
#
# Windows equivalent: dev-app.ps1
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.cargo/bin:$PATH"

triple="$(rustc -Vv | awk '/host:/ {print $2}')"
sidecar="$root/frontend/src-tauri/binaries/raplmail-backend-$triple"

if [ ! -f "$sidecar" ]; then
  echo "Sidecar missing - freezing backend first..."
  (cd "$root/backend" && ./.venv/bin/python -m PyInstaller raplmail-backend.spec --noconfirm)
  mkdir -p "$root/frontend/src-tauri/binaries"
  cp "$root/backend/dist/raplmail-backend" "$sidecar"
  chmod +x "$sidecar"
fi

echo "Launching native app (tauri dev)... DevTools: right-click -> Inspect"
cd "$root/frontend"
npx tauri dev
