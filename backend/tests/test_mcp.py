"""MCP server: the protocol, the access levels, the tools on real (test) mail,
and the stdio relay's answers while RaplMail isn't running."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlmodel import Session

from app.core.db import get_engine
from app.mcp import endpoint, protocol
from app.mcp.tools import tools_for
from app.models import Account, Folder, FolderRole, Message, Setting
from app.providers import pool as pool_mod

BACKEND = Path(__file__).resolve().parents[1]


def _rpc(method, params=None, mid=1):
    msg = {"jsonrpc": "2.0", "method": method}
    if mid is not None:
        msg["id"] = mid
    if params is not None:
        msg["params"] = params
    return msg


def _handle(msg, enabled=True, access="read"):
    return asyncio.run(protocol.handle(msg, {"enabled": enabled, "access": access, "request": None}))


# --- protocol -----------------------------------------------------------------

def test_initialize_negotiates_the_version():
    r = _handle(_rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}}))["result"]
    assert r["protocolVersion"] == "2025-03-26"
    assert r["capabilities"] == {"tools": {"listChanged": False}}
    assert r["serverInfo"]["name"] == "raplmail"
    assert _handle(_rpc("initialize", {"protocolVersion": "1999-01-01"}))["result"]["protocolVersion"] == "2025-06-18"


def test_notifications_get_no_reply_and_ping_works():
    assert _handle(_rpc("notifications/initialized", mid=None)) is None
    assert _handle(_rpc("ping"))["result"] == {}
    assert _handle(_rpc("nope"))["error"]["code"] == -32601
    assert _handle({"id": 1, "method": "ping"})["error"]["code"] == -32600   # no jsonrpc field


def test_access_levels_decide_the_tools():
    names = lambda lvl: {t["name"] for t in tools_for(lvl)}
    assert "search_messages" in names("read") and "mark_done" not in names("read")
    assert "mark_done" in names("act") and "create_draft" in names("act") and "send_email" not in names("act")
    assert "send_email" in names("send")
    assert _handle(_rpc("tools/list"), enabled=False)["result"]["tools"] == []
    assert len(_handle(_rpc("tools/list"), access="act")["result"]["tools"]) == len(tools_for("act"))
    for t in tools_for("send"):
        assert t["inputSchema"]["type"] == "object" and t["description"]


def test_calls_outside_the_level_are_refused():
    r = _handle(_rpc("tools/call", {"name": "send_email", "arguments": {"to": ["a@b.c"], "body": "x"}}), access="act")
    assert r["result"]["isError"] and "Full" in r["result"]["content"][0]["text"]
    last = protocol.recent_activity()[0]          # the user sees what was refused
    assert last["tool"] == "send_email" and last["refused"] and not last["ok"]
    assert last["detail"] == {"to": "a@b.c", "subject": ""}          # never the body
    r = _handle(_rpc("tools/call", {"name": "search_messages", "arguments": {}}), enabled=False)
    assert r["result"]["isError"] and "turned off" in r["result"]["content"][0]["text"]
    assert _handle(_rpc("tools/call", {"name": "rm_rf", "arguments": {}}))["error"]["code"] == -32602


def test_batch():
    replies = _handle([_rpc("ping", mid=1), _rpc("notifications/initialized", mid=None), _rpc("ping", mid=2)])
    assert [r["id"] for r in replies] == [1, 2]


# --- over HTTP, on real (test) mail -------------------------------------------

def _settings(**patch):
    with Session(get_engine()) as s:
        row = s.get(Setting, 1)
        data = dict(row.data) if row and row.data else {}
        data.update(patch)
        if row is None:
            s.add(Setting(id=1, data=data))
        else:
            row.data = data
            s.add(row)
        s.commit()


_n = 0


@pytest.fixture
def mailbox():
    global _n
    _n += 1
    with Session(get_engine()) as s:
        a = Account(email=f"mcp{_n}@me.example", display_name="Me")
        s.add(a); s.commit(); s.refresh(a)
        inbox = Folder(account_id=a.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        other = Folder(account_id=a.id, name="Invoices", path="Invoices", role=FolderRole.other)
        s.add(inbox); s.add(other); s.commit(); s.refresh(inbox); s.refresh(other)
        m = Message(account_id=a.id, folder_id=inbox.id, uid=66000 + _n, message_id=f"<mcp-{_n}@x>",
                    from_addr="boss@corp.example", from_name="The Boss", to_addrs=["mcp@me.example"],
                    subject="Quarterly numbers mcpzz", snippet="Please send the Q3 report",
                    is_seen=False, thread_id=f"t-mcp-{_n}")
        s.add(m); s.commit(); s.refresh(m)
        ids = {"account": a.id, "inbox": inbox.id, "other": other.id, "msg": m.id}
    with Session(get_engine()) as s:
        row = s.get(Setting, 1)
        before = dict(row.data) if row and row.data else None
    _settings(mcpEnabled=True, mcpAccess="act")
    yield ids
    with Session(get_engine()) as s:
        row = s.get(Setting, 1)
        if before is None:
            if row is not None:
                s.delete(row)
        else:
            row.data = before
            s.add(row)
        s.commit()


def _call(client, name, args):
    r = client.post("/mcp", headers={"Authorization": f"Bearer {endpoint.key()}"},
                    json=_rpc("tools/call", {"name": name, "arguments": args}))
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return res, (json.loads(res["content"][0]["text"]) if not res["isError"] else res["content"][0]["text"])


def test_http_needs_the_key(client):
    assert client.post("/mcp", json=_rpc("ping")).status_code == 401
    assert client.post("/mcp", headers={"Authorization": "Bearer nope"}, json=_rpc("ping")).status_code == 401
    ok = client.post("/mcp", headers={"Authorization": f"Bearer {endpoint.key()}"}, json=_rpc("ping"))
    assert ok.status_code == 200 and ok.json()["result"] == {}
    note = client.post("/mcp", headers={"Authorization": f"Bearer {endpoint.key()}"},
                       json=_rpc("notifications/initialized", mid=None))
    assert note.status_code == 202


def test_search_read_and_organize(client, mailbox, monkeypatch):
    res, out = _call(client, "search_messages", {"query": "from:boss mcpzz"})
    assert not res["isError"] and [m["id"] for m in out["messages"]] == [mailbox["msg"]]
    assert out["messages"][0]["unread"] is True

    raw = (b"From: The Boss <boss@corp.example>\r\nTo: mcp@me.example\r\nSubject: Quarterly numbers mcpzz\r\n"
           b"Message-ID: <mcp-1@x>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPlease send the Q3 report by Friday.\r\n")
    monkeypatch.setattr(pool_mod.pool, "fetch_raw", lambda account, path, uid, trace=None: raw)
    res, msg = _call(client, "get_message", {"message_id": mailbox["msg"]})
    assert "Q3 report by Friday" in msg["body"] and msg["from"] == "The Boss <boss@corp.example>"
    with Session(get_engine()) as s:
        assert s.get(Message, mailbox["msg"]).is_seen is False      # reading doesn't mark read

    res, thr = _call(client, "get_thread", {"message_id": mailbox["msg"]})
    assert [m["id"] for m in thr["messages"]] == [mailbox["msg"]]

    _call(client, "mark_read", {"message_ids": [mailbox["msg"]]})
    _call(client, "flag", {"message_ids": [mailbox["msg"]]})
    _call(client, "mark_done", {"message_ids": [mailbox["msg"]]})
    with Session(get_engine()) as s:
        m = s.get(Message, mailbox["msg"])
        assert m.is_seen and m.is_flagged and m.is_done

    res, text = _call(client, "mark_read", {"message_ids": [999999]})
    assert res["isError"] and "no such message" in text
    assert any(a["tool"] == "mark_done" and a["ok"] for a in protocol.recent_activity())


def test_drafts_reply_threading(client, mailbox, monkeypatch):
    seen = {}

    def fake_save(body, replace_uid):
        seen.update(body)
        return {"uid": 1}
    monkeypatch.setattr("app.api.compose._save_draft_blocking", fake_save)
    monkeypatch.setattr("app.core.security.SecretStore.is_unlocked", property(lambda self: True))
    res, out = _call(client, "create_draft", {"to": ["boss@corp.example"], "body": "Here it is.\n\nThanks",
                                              "reply_to_message_id": mailbox["msg"]})
    assert not res["isError"], out
    assert seen["subject"] == "Re: Quarterly numbers mcpzz"
    assert seen["in_reply_to"] == f"<mcp-{_n}@x>" and seen["account_id"] == mailbox["account"]
    assert seen["html"] == "<p>Here it is.</p><p>Thanks</p>"


def test_send_needs_full_access(client, mailbox):
    res, text = _call(client, "send_email", {"to": ["x@y.example"], "body": "hi"})
    assert res["isError"] and "Full" in text


def test_info_for_settings(client):
    info = client.get("/mcp/info").json()
    assert info["command"] and info["args"] and isinstance(info["activity"], list)


# --- the stdio relay while RaplMail is closed ---------------------------------

def test_relay_offline_answers(tmp_path):
    env = {**os.environ, "RAPLMAIL_DATA_DIR": str(tmp_path)}      # no endpoint file there
    lines = [_rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}, mid=1),
             _rpc("notifications/initialized", mid=None),
             _rpc("tools/list", mid=2),
             _rpc("tools/call", {"name": "search_messages", "arguments": {}}, mid=3)]
    stdin = "".join(json.dumps(m) + "\n" for m in lines) + "not json\n"
    p = subprocess.run([sys.executable, str(BACKEND / "mcp_relay.py")], input=stdin.encode("utf-8"),
                       capture_output=True, env=env, timeout=60)
    replies = [json.loads(l) for l in p.stdout.decode("utf-8").splitlines() if l.strip()]
    assert [r.get("id") for r in replies] == [1, 2, 3, None]
    assert "isn't running" in replies[0]["result"]["instructions"]
    assert {t["name"] for t in replies[1]["result"]["tools"]} >= {"search_messages", "get_message"}
    assert replies[2]["result"]["isError"]
    assert replies[3]["error"]["code"] == -32700


def test_relay_left_behind_endpoint_file(tmp_path):
    # RaplMail was killed: its endpoint file is still there, nobody listens.
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    (tmp_path / "mcp-endpoint.json").write_text(json.dumps(
        {"url": f"http://127.0.0.1:{port}/mcp", "key": "old", "pid": 1, "version": ""}), encoding="utf-8")
    env = {**os.environ, "RAPLMAIL_DATA_DIR": str(tmp_path)}
    lines = [_rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}, mid=1),
             _rpc("tools/list", mid=2), _rpc("ping", mid=3)]
    p = subprocess.run([sys.executable, str(BACKEND / "mcp_relay.py")],
                       input="".join(json.dumps(m) + "\n" for m in lines).encode("utf-8"),
                       capture_output=True, env=env, timeout=60)
    replies = [json.loads(l) for l in p.stdout.decode("utf-8").splitlines() if l.strip()]
    assert [r.get("id") for r in replies] == [1, 2, 3]
    assert "isn't running" in replies[0]["result"]["instructions"]
    # Tried once, then answered straight away instead of waiting on it again.
    assert p.stderr.decode("utf-8", "replace").count("not reachable") == 1
