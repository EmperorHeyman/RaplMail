"""Microsoft Graph helpers - currently just sending mail.

Used when a tenant has SMTP client authentication disabled (the common
"SmtpClientAuthentication is disabled for the Tenant" 535 error). Graph's
sendMail accepts a full MIME message (base64, Content-Type: text/plain) and
delivers it, saving a copy to Sent Items automatically - so we reuse the exact
MIME we already build for SMTP and skip the separate Sent append.
"""

from __future__ import annotations

import base64

import httpx

GRAPH_SEND = "https://graph.microsoft.com/v1.0/me/sendMail"


class GraphSendError(RuntimeError):
    """Graph rejected the send. Carries the HTTP status so callers can tell a
    permanent permission problem (401/403) from a transient failure (5xx)."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def send_mime(access_token: str, raw_mime: bytes) -> None:
    """Send a raw MIME message via Graph. Raises GraphSendError on a Graph
    rejection; network errors propagate as ordinary httpx exceptions."""
    b64 = base64.b64encode(raw_mime).decode("ascii")
    r = httpx.post(
        GRAPH_SEND,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "text/plain"},
        content=b64,
        timeout=30,
    )
    if r.status_code not in (200, 202):
        detail = ""
        try:
            detail = r.json().get("error", {}).get("message", "")
        except Exception:
            detail = r.text[:300]
        raise GraphSendError(r.status_code, f"Graph sendMail failed (HTTP {r.status_code}): {detail}")
