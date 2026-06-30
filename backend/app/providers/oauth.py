"""OAuth2 flows and token management for Microsoft 365 and Gmail.

Both providers authenticate IMAP/SMTP via the XOAUTH2 SASL mechanism. We store a
refresh token (Google) or the serialized MSAL token cache (Microsoft) in the
encrypted secret store, and mint short-lived access tokens on demand.

Microsoft uses the OAuth2 *device-code* flow: the backend starts a flow and
returns a user code + verification URL to the UI; the user authenticates in a
browser; the backend polls for completion. No client secret is stored on-device.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass

import msal

from app.core.config import get_settings

# --- Microsoft 365 -----------------------------------------------------------
# Resource-scoped permissions for IMAP/SMTP access as the signed-in user.
MS_SCOPES = [
    "https://outlook.office365.com/IMAP.AccessAsUser.All",
    "https://outlook.office365.com/SMTP.Send",
]
MS_IMAP_HOST = "outlook.office365.com"
MS_SMTP_HOST = "smtp.office365.com"

# --- Gmail -------------------------------------------------------------------
GOOGLE_SCOPES = ["https://mail.google.com/"]
# Calendar write access (create/update/delete events) + email claim for display.
GCAL_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_SMTP_HOST = "smtp.gmail.com"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def xoauth2_string(user: str, access_token: str) -> str:
    """Build the base64 XOAUTH2 SASL initial-response string."""
    raw = f"user={user}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


# ----------------------------------------------------------------------------
# Microsoft (MSAL device-code)
# ----------------------------------------------------------------------------
@dataclass
class DeviceFlow:
    flow: dict           # opaque MSAL flow dict (passed back to complete)
    user_code: str
    verification_uri: str
    verification_uri_complete: str  # URL with the code pre-filled (when provided)
    message: str
    expires_in: int


def _ms_app(cache_blob: str | None = None) -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache]:
    settings = get_settings()
    if not settings.ms_client_id:
        raise RuntimeError("RAPLMAIL_MS_CLIENT_ID is not configured (Azure app registration required)")
    cache = msal.SerializableTokenCache()
    if cache_blob:
        cache.deserialize(cache_blob)
    app = msal.PublicClientApplication(
        settings.ms_client_id, authority=settings.ms_authority, token_cache=cache
    )
    return app, cache


def ms_start_device_flow() -> DeviceFlow:
    app, _ = _ms_app()
    flow = app.initiate_device_flow(scopes=MS_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"failed to start device flow: {flow.get('error_description', flow)}")
    return DeviceFlow(
        flow=flow,
        user_code=flow["user_code"],
        verification_uri=flow["verification_uri"],
        verification_uri_complete=flow.get("verification_uri_complete", ""),
        message=flow["message"],
        expires_in=flow.get("expires_in", 900),
    )


def ms_complete_device_flow(flow: dict) -> tuple[str, str]:
    """Block until the user finishes auth (or it times out).

    Returns (account_email, serialized_token_cache). Call from a worker thread.
    """
    app, cache = _ms_app()
    result = app.acquire_token_by_device_flow(flow)  # blocks, polling internally
    if "access_token" not in result:
        raise RuntimeError(f"device flow failed: {result.get('error_description', result)}")
    email = (result.get("id_token_claims") or {}).get("preferred_username", "")
    return email, cache.serialize()


def ms_access_token(cache_blob: str) -> tuple[str, str]:
    """Return (access_token, possibly-updated cache blob), refreshing silently."""
    app, cache = _ms_app(cache_blob)
    accounts = app.get_accounts()
    if not accounts:
        raise RuntimeError("no cached Microsoft account; re-authentication required")
    result = app.acquire_token_silent(MS_SCOPES, account=accounts[0])
    if not result or "access_token" not in result:
        raise RuntimeError("failed to refresh Microsoft token; re-authentication required")
    return result["access_token"], cache.serialize()


# ----------------------------------------------------------------------------
# Google (installed-app / loopback OAuth)
# ----------------------------------------------------------------------------
def google_run_installed_flow(scopes: list[str] | None = None) -> tuple[str, dict]:
    """Open a browser, run the loopback OAuth flow, return (email, token bundle).

    Blocks until the user authorizes. Call from a worker thread.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = get_settings()
    if not settings.google_client_id:
        raise RuntimeError("RAPLMAIL_GOOGLE_CLIENT_ID is not configured")
    client_config = {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes or GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    bundle = {
        "refresh_token": creds.refresh_token,
        "access_token": creds.token,
        "expires_at": creds.expiry.timestamp() if creds.expiry else 0,
    }
    # The granted email is in the id_token; fall back to userinfo if absent.
    email = ""
    if creds.id_token:
        import jwt  # PyJWT ships with google-auth deps; decode without verify for the claim

        with _suppress():
            email = jwt.decode(creds.id_token, options={"verify_signature": False}).get("email", "")
    return email, bundle


def google_access_token(bundle: dict) -> tuple[str, dict]:
    """Return (access_token, updated bundle), refreshing if expired."""
    if bundle.get("access_token") and bundle.get("expires_at", 0) > time.time() + 60:
        return bundle["access_token"], bundle

    import httpx

    settings = get_settings()
    resp = httpx.post(
        GOOGLE_TOKEN_URI,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": bundle["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    bundle = {
        **bundle,
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 3600),
    }
    return bundle["access_token"], bundle


class _suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


def serialize_bundle(bundle: dict) -> str:
    return json.dumps(bundle)


def deserialize_bundle(blob: str) -> dict:
    return json.loads(blob)
