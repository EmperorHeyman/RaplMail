#!/usr/bin/env bash
# RaplMail BROWSER dev mode (macOS/Linux): backend (no-auth dev token) + Vite UI
# in your browser. Best for fast iteration with Chrome/Safari DevTools.
# Opens http://localhost:1420.
#
# For the REAL native app window with hot reload, use:  ./dev-app.sh   (runs `tauri dev`)
# To produce the .app/.dmg:                             ./build-desktop.sh
#
# Windows equivalent: dev.ps1
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"

echo "Starting RaplMail backend (dev mode, no token)..."
# RAPLMAIL_DEV=1 -> backend skips the auth token so the Vite dev server can connect.
(
  cd "$root/backend"
  RAPLMAIL_DEV=1 exec ./.venv/bin/python -m uvicorn app.main:app --port 8765 --reload
) &
backend_pid=$!
trap 'echo "Shutting down backend..."; kill "$backend_pid" 2>/dev/null || true' EXIT

sleep 2
echo "Starting UI at http://localhost:1420 (Ctrl+C to stop both)..."
cd "$root/frontend"
node node_modules/vite/bin/vite.js --open
