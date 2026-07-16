"""Live IMAP/SMTP end-to-end test against a REAL throwaway mailbox (roadmap B4).

Exercises the app's own provider (app.providers.imap_smtp.ImapSmtpProvider) -
the exact code path the sync engine uses - not raw imaplib/smtplib:

    send -> poll until it arrives -> flag -> verify flag round-trip -> delete

Skipped (the default in CI/dev) unless a dedicated test mailbox is configured:

    RAPLMAIL_LIVE_EMAIL       login and From/To address
    RAPLMAIL_LIVE_PASSWORD    IMAP/SMTP password (never printed or logged)
    RAPLMAIL_LIVE_IMAP_HOST   IMAP server (implicit SSL)
    RAPLMAIL_LIVE_SMTP_HOST   SMTP server (STARTTLS; implicit SSL on port 465)
    RAPLMAIL_LIVE_IMAP_PORT   optional, default 993
    RAPLMAIL_LIVE_SMTP_PORT   optional, default 587

Use a THROWAWAY account: the test sends into, flags in, and deletes from its
inbox. The test message carries a unique random subject so it never touches
anything else in the mailbox.
"""

import os
import time
import uuid

import pytest

_REQUIRED = (
    "RAPLMAIL_LIVE_EMAIL",
    "RAPLMAIL_LIVE_PASSWORD",
    "RAPLMAIL_LIVE_IMAP_HOST",
    "RAPLMAIL_LIVE_SMTP_HOST",
)
_missing = [name for name in _REQUIRED if not os.environ.get(name)]

pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason=f"live mailbox not configured (missing env vars: {', '.join(_missing)})",
)

_ARRIVAL_TIMEOUT = 60.0     # seconds to wait for the self-sent message
_POLL_INTERVAL = 3.0


@pytest.fixture()
def provider():
    """The app's real IMAP/SMTP provider, built the same way build_provider()
    does for a plain-IMAP account (Auth mechanism 'plain')."""
    from app.providers.imap_smtp import Auth, ImapSmtpProvider

    auth = Auth(
        mechanism="plain",
        user=os.environ["RAPLMAIL_LIVE_EMAIL"],
        secret=os.environ["RAPLMAIL_LIVE_PASSWORD"],
    )
    p = ImapSmtpProvider(
        auth,
        os.environ["RAPLMAIL_LIVE_IMAP_HOST"],
        int(os.environ.get("RAPLMAIL_LIVE_IMAP_PORT", "993")),
        os.environ["RAPLMAIL_LIVE_SMTP_HOST"],
        int(os.environ.get("RAPLMAIL_LIVE_SMTP_PORT", "587")),
    )
    yield p
    p.close()


def _wait_for_arrival(provider, folder_path, min_uid, subject):
    """Poll fetch_headers until a message with `subject` shows up (or time out).
    Returns the HeaderInfo, or None on timeout."""
    deadline = time.monotonic() + _ARRIVAL_TIMEOUT
    while True:
        for h in provider.fetch_headers(folder_path, min_uid=min_uid):
            if h.subject == subject:
                return h
        if time.monotonic() >= deadline:
            return None
        time.sleep(_POLL_INTERVAL)


def test_live_send_receive_flag_delete(provider):
    email_addr = os.environ["RAPLMAIL_LIVE_EMAIL"]

    # 1. Connect and locate the inbox through the provider's folder listing.
    try:
        folders = provider.list_folders()
    except Exception as exc:
        pytest.fail(f"step 1 (IMAP connect / list_folders) failed: "
                    f"{type(exc).__name__}: {exc}")
    inbox = next((f for f in folders if f.role == "inbox"), None)
    assert inbox is not None, \
        f"step 1: no inbox among folders {[f.path for f in folders]}"

    # Baseline UID watermark so polling only looks at messages newer than now.
    baseline = provider.fetch_uids(inbox.path)
    min_uid = (max(baseline) + 1) if baseline else 1

    # 2. SMTP-send a uniquely-subjected message to the mailbox itself.
    from app.providers.base import OutgoingMessage
    subject = f"raplmail-live-{uuid.uuid4().hex}"
    outgoing = OutgoingMessage(
        from_addr=email_addr, to=[email_addr], subject=subject,
        text="RaplMail live integration test message - safe to delete.",
    )
    try:
        provider.send(outgoing)
    except Exception as exc:
        pytest.fail(f"step 2 (SMTP send) failed: {type(exc).__name__}: {exc}")

    # 3. Poll IMAP until it arrives.
    header = _wait_for_arrival(provider, inbox.path, min_uid, subject)
    assert header is not None, \
        (f"step 3: message {subject!r} did not arrive in {inbox.path} within "
         f"{_ARRIVAL_TIMEOUT:.0f}s (check that the account delivers self-sent "
         f"mail to the inbox)")
    uid = header.uid

    try:
        # 4. Fetch it back and sanity-check the round-tripped envelope + body.
        assert header.from_addr.lower() == email_addr.lower(), \
            f"step 4: unexpected From on fetched header: {header.from_addr!r}"
        raw = provider.fetch_raw(inbox.path, uid)
        assert b"safe to delete" in raw, \
            "step 4: fetched RFC822 body does not contain the sent text"

        # 5. Flag it and verify the flag round-trips through the server.
        provider.set_flags(inbox.path, uid, ["\\Flagged"], add=True)
        flags = provider.fetch_flags(inbox.path, [uid]).get(uid, [])
        assert "\\Flagged" in flags, \
            f"step 5: \\Flagged did not round-trip; server reports flags {flags}"
    finally:
        # 6. Clean up: delete the test message (runs even if 4/5 failed).
        provider.delete(inbox.path, uid)

    assert uid not in provider.fetch_uids(inbox.path), \
        "step 6: cleanup delete did not remove the message from the inbox"
