# RaplMail

A fast, local-first, feature-rich desktop mail client — built because Spark went
behind a paywall and Thunderbird makes adding a signature image take 20 steps.

- **Python backend** (FastAPI) — IMAP/SMTP + OAuth2 sync engine, rules, encrypted credential vault.
- **Rust/Tauri + Svelte frontend** — snappy UI with the Spark-style workflow.
- Talks over localhost HTTP + WebSocket; everything stays on your machine.

## Hero features

- **`e` to done + slider** — press `e` (or swipe a row right) to mark a message *done*; it
  slides out of the inbox. Flip the **Show done** slider to bring them back. Done is local
  state — the message stays in the inbox, just hidden.
- **Rules & domain blocking** — route mail by sender/domain to a folder, archive, delete,
  or block a domain (auto-quarantine). Live preview shows how many existing messages match.
- **One-drag signature** — drag an image straight into the signature box; it's embedded
  inline (Content-ID) so it renders for everyone you email.
- **Fast** — SQLite (WAL + FTS5 search), async background sync, virtualized lists.

## Project layout

```
backend/    FastAPI app, sync engine, providers, encrypted vault
frontend/   Vite + Svelte 5 UI (runs in browser today; Tauri shell is next)
```

## Run it (development)

You need **Python 3.11+** and **Node 18+**. (Rust is only needed later for the Tauri
desktop bundle — see below.)

**1. Backend**

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e .
# Optional: set OAuth client IDs (see below). Then:
RAPLMAIL_DEV=1 python -m uvicorn app.main:app --port 8765
```

`RAPLMAIL_DEV=1` disables the localhost shared-secret token so the browser dev server can
talk to it directly. API docs: http://127.0.0.1:8765/docs

**2. Frontend**

```bash
cd frontend
npm install
npm run dev        # http://localhost:1420  (proxies /api -> backend on :8765)
```

Open http://localhost:1420, set a master password, and add an account.

## OAuth setup (one-time)

Business Microsoft 365 tenants block basic IMAP auth, and Gmail requires OAuth too. These
are free, one-time registrations. Put the IDs in environment variables (or `backend/.env`).

### Microsoft 365 (device-code flow)
1. Go to the [Azure Portal](https://portal.azure.com) → **App registrations** → **New registration**.
2. Name it (e.g. "RaplMail"), set **Supported account types** to your needs, register.
3. Under **Authentication** → **Advanced settings**, enable **Allow public client flows** = Yes.
4. Under **API permissions**, add delegated permissions:
   `IMAP.AccessAsUser.All`, `SMTP.Send`, `offline_access`.
5. Copy the **Application (client) ID** → set `RAPLMAIL_MS_CLIENT_ID`.

### Gmail / Google Workspace
1. [Google Cloud Console](https://console.cloud.google.com) → create a project.
2. **APIs & Services** → enable the **Gmail API**.
3. **Credentials** → **Create credentials** → **OAuth client ID** → **Desktop app**.
4. Copy the client ID/secret → set `RAPLMAIL_GOOGLE_CLIENT_ID` and `RAPLMAIL_GOOGLE_CLIENT_SECRET`.

(Generic IMAP/SMTP accounts — Fastmail, iCloud, self-hosted — need no setup; just use an
app password.)

## Configuration (env vars, prefix `RAPLMAIL_`)

| Variable | Purpose |
| --- | --- |
| `RAPLMAIL_DEV` | `1` to disable the localhost token (dev only) |
| `RAPLMAIL_PORT` | Backend port (default 8765) |
| `RAPLMAIL_TOKEN` | Shared secret required on every request (injected by Tauri) |
| `RAPLMAIL_DATA_DIR` | Where the DB + encrypted vault live (default `%APPDATA%/RaplMail`) |
| `RAPLMAIL_MS_CLIENT_ID` | Azure app (client) ID |
| `RAPLMAIL_GOOGLE_CLIENT_ID` / `_SECRET` | Google OAuth desktop client |

## Desktop app (Tauri)

The Tauri shell wraps everything into a single native Windows app: on launch the Rust core
picks a free localhost port + a random per-launch token, starts the bundled Python backend
as a **sidecar** with those values, and the webview reads them via the `backend_config`
command. Closing the app kills the backend.

Prerequisites (already satisfied on this machine): **Rust** (rustup, MSVC toolchain),
**Visual Studio C++ build tools**, and the **WebView2 runtime** (built into Windows 11).

**Build the bundled backend (sidecar), then the app:**

```bash
# 1. Freeze the backend to a single exe and place it as the Tauri sidecar
cd backend
.venv/Scripts/python -m PyInstaller raplmail-backend.spec --noconfirm
cp dist/raplmail-backend.exe \
   ../frontend/src-tauri/binaries/raplmail-backend-x86_64-pc-windows-msvc.exe

# 2. Build the desktop app + installers
cd ../frontend
npx tauri build
```

Outputs:
- `frontend/src-tauri/target/release/raplmail.exe` — the app
- `…/target/release/bundle/msi/RaplMail_0.1.0_x64_en-US.msi` — MSI installer
- `…/target/release/bundle/nsis/RaplMail_0.1.0_x64-setup.exe` — NSIS installer

**Iterate quickly:** `npx tauri dev` runs Vite + the app with hot reload. Note: it still
spawns the *frozen* sidecar, so **rebuild the sidecar (step 1) whenever backend code
changes**. (For pure backend work, the standalone uvicorn flow above is faster.)

> The OAuth client IDs (`RAPLMAIL_MS_CLIENT_ID`, etc.) must be present in the sidecar's
> environment. For the packaged app, set them as user/system environment variables, or
> extend `src-tauri/src/main.rs` to inject them into the sidecar `.env(...)` calls.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest -q
```
