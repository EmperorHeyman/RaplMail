# PyInstaller spec for the RaplMail backend sidecar.
# Build:  pyinstaller raplmail-backend.spec --noconfirm
# Output: dist/raplmail-backend.exe  (onefile)

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = []
for pkg in ("uvicorn", "anyio", "app", "email", "encodings", "pgpy"):
    hiddenimports += collect_submodules(pkg)
hiddenimports += [
    "websockets", "websockets.legacy", "h11",
    "mailparser", "msal", "google.auth", "google.auth.transport.requests",
    "google_auth_oauthlib", "google_auth_oauthlib.flow", "requests_oauthlib",
    "imapclient", "aiosmtplib", "argon2", "cryptography",
    # OpenPGP (pgpy) — needs the stdlib `imghdr` module that was removed in
    # Python 3.13 and restored by the `standard-imghdr` backport.
    "pgpy", "imghdr",
]

datas = collect_data_files("certifi")

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
