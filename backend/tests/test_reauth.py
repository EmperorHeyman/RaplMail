"""Signing an OAuth account in again after its token died.

The trigger was an M365 tenant switching on 2FA after an audit: Azure revoked
every refresh token (AADSTS50173) and sync failed forever with only a traceback
in the log. Health now flags it as "needs sign-in", and a re-auth endpoint swaps
a fresh token into the SAME account - refusing a different mailbox.
"""
import uuid

from sqlmodel import Session

from app.api import accounts as accounts_api
from app.core.db import get_engine
from app.core.security import get_secret_store
from app.models import Account, Provider
from app.providers import oauth

REVOKED = ("failed to acquire Microsoft token for ['https://outlook.office365.com/IMAP.AccessAsUser.All']: "
           "AADSTS50173: The provided grant has expired due to it being revoked, a fresh auth token is needed.")


def _account(email: str) -> int:
    with Session(get_engine()) as s:
        a = Account(email=email, display_name=email, provider=Provider.m365, use_oauth=True,
                    secret_key=f"account:{email}:{uuid.uuid4().hex[:8]}", enabled=False,
                    aliases=["Sales <sales-alias@corp.example>"])
        s.add(a); s.commit(); s.refresh(a)
        return a.id


def _unlock():
    store = get_secret_store()
    if not store.is_unlocked:
        try:
            store.initialize("test-pass-1234")
        except Exception:
            store.unlock("test-pass-1234")
    return store


def test_signin_needed_recognises_dead_tokens_only():
    assert oauth.signin_needed(REVOKED)
    assert oauth.signin_needed("invalid_grant: Token has been expired or revoked.")
    assert oauth.signin_needed("no cached Microsoft account; re-authentication required")
    assert not oauth.signin_needed("timed out")
    assert not oauth.signin_needed("AADSTS501730: something else")   # word boundary
    assert not oauth.signin_needed(None)


def test_health_flags_needs_signin(client):
    aid = _account("reauth-health@corp.example")
    client.app.state.sync._set_health(aid, status="error", last_error=REVOKED)
    row = next(r for r in client.get("/accounts/health").json() if r["id"] == aid)
    assert row["needs_signin"] is True
    client.app.state.sync._set_health(aid, status="error", last_error="connection reset")
    row = next(r for r in client.get("/accounts/health").json() if r["id"] == aid)
    assert row["needs_signin"] is False


def test_reauth_swaps_the_token_for_the_same_mailbox(client, monkeypatch):
    store = _unlock()
    aid = _account("reauth-ok@corp.example")
    with Session(get_engine()) as s:
        key = s.get(Account, aid).secret_key
    store.set(key, "old-cache")
    monkeypatch.setattr(oauth, "ms_complete_device_flow", lambda flow: ("Reauth-OK@corp.example", "new-cache"))
    accounts_api._pending_ms_flows["f-ok"] = {"x": 1}
    r = client.post(f"/accounts/{aid}/reauth/ms", json={"flow_id": "f-ok"})
    assert r.status_code == 200, r.text
    assert store.get(key) == "new-cache"


def test_reauth_accepts_an_alias_but_refuses_another_mailbox(client, monkeypatch):
    store = _unlock()
    aid = _account("reauth-guard@corp.example")
    with Session(get_engine()) as s:
        key = s.get(Account, aid).secret_key
    store.set(key, "old-cache")

    monkeypatch.setattr(oauth, "ms_complete_device_flow", lambda flow: ("someone.else@corp.example", "wrong"))
    accounts_api._pending_ms_flows["f-bad"] = {"x": 1}
    r = client.post(f"/accounts/{aid}/reauth/ms", json={"flow_id": "f-bad"})
    assert r.status_code == 400 and "someone.else@corp.example" in r.json()["detail"]
    assert store.get(key) == "old-cache"     # untouched

    monkeypatch.setattr(oauth, "ms_complete_device_flow", lambda flow: ("sales-alias@corp.example", "alias-cache"))
    accounts_api._pending_ms_flows["f-alias"] = {"x": 1}
    assert client.post(f"/accounts/{aid}/reauth/ms", json={"flow_id": "f-alias"}).status_code == 200
    assert store.get(key) == "alias-cache"
