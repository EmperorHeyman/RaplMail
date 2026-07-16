"""Read-receipt pixel dedupe (roadmap D3): the pixel token is minted once per
logical message and reused on every delivery attempt - queued/scheduled send
retries must never mint a fresh tracker id (which would double-count opens or
count them against a dead id)."""
import re

from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, OpenTrack, ScheduledSend

_TOKEN_RE = re.compile(r"/track/o/([A-Za-z0-9_\-]+)\.png")

_n = 0


def _seed_account():
    global _n
    _n += 1
    with Session(get_engine()) as s:
        acct = Account(email=f"pixel{_n}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        return acct.id


class _FakeProvider:
    """Captures the outgoing HTML instead of talking SMTP."""
    def __init__(self, sent):
        self.sent = sent

    def send(self, message):
        self.sent.append(message.html)
        return b"raw-mime"

    def append_to_folder(self, path, raw, seen=True):
        pass

    def close(self):
        pass


def _deliver_twice(payload, monkeypatch):
    """Run the real delivery path twice on the same payload (a retry), with a
    fake SMTP transport, and return the HTML each attempt actually sent."""
    sent: list[str] = []
    import app.sync.engine as eng
    monkeypatch.setattr(eng, "build_provider", lambda acct: _FakeProvider(sent), raising=False)
    from app.api.compose import _deliver_blocking
    _deliver_blocking(dict(payload))
    _deliver_blocking(dict(payload))
    return sent


def _unlock_store():
    """/compose/send requires an unlocked secret store; init one for the test DB."""
    from app.core.security import get_secret_store
    store = get_secret_store()
    if not store.exists:
        store.initialize("test-master")
    elif not store.is_unlocked:
        store.unlock("test-master")


def test_legacy_queued_payload_reuses_one_pixel_token(client, monkeypatch):
    # Payloads queued before receipt_token existed carry request_receipt but no
    # embedded pixel - each retry used to mint a fresh tracker row.
    acct_id = _seed_account()
    payload = {"account_id": acct_id, "to": ["rcpt@example.com"],
               "subject": "legacy retry", "html": "<p>hello</p>",
               "request_receipt": True}
    sent = _deliver_twice(payload, monkeypatch)
    assert len(sent) == 2
    tokens = [_TOKEN_RE.search(h).group(1) for h in sent]
    assert tokens[0] == tokens[1]                       # same pixel id both attempts
    assert sent[0].count("/track/o/") == 1              # embedded exactly once
    with Session(get_engine()) as s:
        rows = s.exec(select(OpenTrack).where(OpenTrack.token == tokens[0])).all()
        assert len(rows) == 1                           # one tracker row total


def test_scheduled_send_stores_token_in_payload_and_retries_reuse_it(client, monkeypatch):
    _unlock_store()
    acct_id = _seed_account()
    r = client.post("/compose/send", json={
        "account_id": acct_id, "to": ["rcpt2@example.com"], "subject": "sched pixel",
        "html": "<p>later</p>", "request_receipt": True,
        "send_at": "2099-01-01T00:00:00Z"})
    assert r.status_code == 202 and r.json().get("scheduled") is True
    with Session(get_engine()) as s:
        sched = s.exec(select(ScheduledSend).where(ScheduledSend.subject == "sched pixel")).first()
        assert sched is not None
        payload = dict(sched.payload)
    # The pixel id was minted at compose time and rides along in the payload.
    token = payload.get("receipt_token")
    assert token
    assert payload["html"].count("/track/o/") == 1
    assert f"/track/o/{token}.png" in payload["html"]
    # Delivering (and retrying) that payload keeps the very same pixel id.
    sent = _deliver_twice(payload, monkeypatch)
    assert [_TOKEN_RE.search(h).group(1) for h in sent] == [token, token]
    assert all(h.count("/track/o/") == 1 for h in sent)
    with Session(get_engine()) as s:
        rows = s.exec(select(OpenTrack).where(OpenTrack.token == token)).all()
        assert len(rows) == 1
