"""Pin a valid TLS CA bundle for the frozen (PyInstaller) sidecar.

In a onefile build, newer `certifi` resolves `cacert.pem` through
`importlib.resources`, which does not reliably materialise the file inside the
`_MEIxxxx` extraction dir. `requests` (used by `msal` for the M365 token /
tenant-discovery calls) then computes its default bundle path from that broken
location and dies with:

    OSError: Could not find a suitable TLS CA certificate bundle, invalid path:
    ...\\_MEIxxxx\\certifi\\cacert.pem

`httpx` (Gmail) survives because it goes through the stdlib ``ssl`` default
context, which is why one account syncs and another fails in the same cycle.

The bulletproof fix is to locate the CA bundle we actually shipped and export it
via the standard env vars *before* any of `requests` / `msal` / `ssl` /
`aioimaplib` import and cache their defaults. Call :func:`pin_ca_bundle` as the
very first thing in the frozen entrypoint.
"""

from __future__ import annotations

import os
import sys


def _candidate_paths() -> list[str]:
    paths: list[str] = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        # collect_data_files("certifi") lands here; the root copy is our fallback.
        paths.append(os.path.join(base, "certifi", "cacert.pem"))
        paths.append(os.path.join(base, "cacert.pem"))
    # Whatever certifi itself thinks - works in dev, sometimes in frozen too.
    try:
        import certifi

        paths.append(certifi.where())
    except Exception:  # noqa: BLE001 - certifi import must never break startup
        pass
    return paths


def pin_ca_bundle() -> str | None:
    """Point the TLS env vars at a real, existing CA bundle. Returns the path."""
    for path in _candidate_paths():
        if path and os.path.exists(path):
            # requests / curl-based libs, and the stdlib ssl default context.
            os.environ.setdefault("REQUESTS_CA_BUNDLE", path)
            os.environ.setdefault("CURL_CA_BUNDLE", path)
            os.environ.setdefault("SSL_CERT_FILE", path)
            # A stale SSL_CERT_DIR pointing into a previous _MEI dir would make
            # OpenSSL ignore SSL_CERT_FILE; clear it so our file wins.
            os.environ.pop("SSL_CERT_DIR", None)
            return path
    return None
