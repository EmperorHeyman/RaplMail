"""End-to-end API harness: boots the real app and exercises the HTTP surface.

These run against a temp DB (see conftest) with no mail accounts, so they verify
routing, auth, persistence, and graceful-degradation paths without needing live
IMAP/SMTP. A future variant can point at a real test account via env vars.
"""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_settings_roundtrip(client):
    client.put("/settings", json={"data": {"hello": "world", "n": 3}})
    assert client.get("/settings").json() == {"hello": "world", "n": 3}


def test_accounts_empty(client):
    assert client.get("/accounts").json() == []
    assert client.get("/accounts/health").json() == []


def test_metrics_opt_in_and_auth(client):
    # Disabled by default → indistinguishable 404.
    client.put("/settings", json={"data": {}})
    assert client.get("/metrics").status_code == 404

    # Enable with a key.
    client.put("/settings", json={"data": {"localApiEnabled": True, "localApiKey": "k3y"}})
    assert client.get("/metrics", headers={"X-API-Key": "k3y"}).status_code == 200
    assert client.get("/metrics", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get("/metrics").status_code == 401  # missing key

    body = client.get("/metrics", headers={"X-API-Key": "k3y"}).json()
    for field in ("unread", "inbox", "total_messages", "accounts", "queue_pending"):
        assert field in body

    # Prometheus exposition.
    p = client.get("/metrics/prometheus?key=k3y")
    assert p.status_code == 200
    assert "raplmail_unread" in p.text


def test_ai_requires_key(client):
    client.put("/settings", json={"data": {}})
    assert client.get("/ai/status").json()["configured"] is False
    for path, payload in [("/ai/summarize", {"message_id": 1}),
                          ("/ai/draft", {"message_id": 1}),
                          ("/ai/digest", {}),
                          ("/ai/triage", {"limit": 5})]:
        assert client.post(path, json=payload).status_code == 400


def test_plus_aliases_empty(client):
    assert client.get("/messages/plus-aliases").json() == []


def test_messages_list_empty(client):
    rows = client.get("/messages?limit=10").json()
    assert isinstance(rows, list) and rows == []
