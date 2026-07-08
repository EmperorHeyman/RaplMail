# PyInstaller spec for the RaplMail backend sidecar.
# Build:  pyinstaller raplmail-backend.spec --noconfirm
# Output: dist/raplmail-backend.exe  (onefile)

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = []
for pkg in ("uvicorn", "anyio", "app", "email", "encodings", "pgpy",
            # oletools/olevba (deep macro analysis) + its runtime deps. These pull
            # in submodules PyInstaller won't discover on its own.
            "oletools", "olefile", "pcodedmp", "msoffcrypto"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
hiddenimports += [
    "websockets", "websockets.legacy", "h11",
    "mailparser", "msal", "google.auth", "google.auth.transport.requests",
    "google_auth_oauthlib", "google_auth_oauthlib.flow", "requests_oauthlib",
    "imapclient", "argon2", "cryptography", "orjson",
    # OpenPGP (pgpy) — needs the stdlib `imghdr` module that was removed in
    # Python 3.13 and restored by the `standard-imghdr` backport.
    "pgpy", "imghdr",
    # tzdata supplies the IANA timezone database used by zoneinfo to convert
    # calendar event times (Windows has no system tz database).
    "tzdata",
]

import os

datas = collect_data_files("certifi")
# Also drop cacert.pem at the bundle root as a stable fallback: newer certifi
# resolves its bundle via importlib.resources, which doesn't reliably land in the
# onefile _MEI dir, so app/core/certs.py looks here too (fixes the frozen M365
# "Could not find a suitable TLS CA certificate bundle" crash).
try:
    import certifi as _certifi
    if os.path.exists(_certifi.where()):
        datas += [(_certifi.where(), ".")]
except Exception:
    pass
# The timezone database is pure data — collect its files so zoneinfo can find them.
datas += collect_data_files("tzdata")
# oletools ships data files (signatures, thirdparty tables) it reads at runtime.
for _pkg in ("oletools", "pcodedmp"):
    try:
        datas += collect_data_files(_pkg)
    except Exception:
        pass
# Bake the local .env (OAuth client IDs, etc.) into the bundle so the packaged
# app is configured out of the box. Users can override it with a .env next to
# the exe or in %APPDATA%/RaplMail without rebuilding (see core/config.py).
if os.path.exists(".env"):
    datas += [(".env", ".")]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="raplmail-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # keep a console so backend logs are visible; flip to False later
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
