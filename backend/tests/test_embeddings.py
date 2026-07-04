"""Semantic search: vector pack/normalize, cosine ranking (numpy + pure-Python
fallback), incremental indexing, end-to-end search, and the AI/message endpoints
that expose it.

No live model is needed: a deterministic bag-of-words fake embedder stands in for
Ollama/OpenAI so the storage + ranking math is exercised exactly and repeatably.
"""
import math

import pytest
from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Account, Folder, Message, MessageEmbedding, Setting
from app.sync import embeddings

# Fixed vocabulary → each embedding is a bag-of-words count vector. Texts that
# share words have a high cosine; unrelated texts are orthogonal (score 0).
_VOCAB = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]


def _fake_vec(text: str) -> list[float]:
    words = (text or "").lower().split()
    return [float(words.count(v)) for v in _VOCAB]


def _fake_embed(cfg, texts):
    return [_fake_vec(t) for t in texts]


def _s():
    return Session(get_engine())


def _set_semantic(model: str, enabled: bool = True):
    with _s() as s:
        row = s.get(Setting, 1) or Setting(id=1, data={})
        data = dict(row.data or {})
        data.update({"semanticEnabled": enabled, "embedProvider": "ollama",
                     "embedModel": model, "embedBaseUrl": ""})
        row.data = data
        s.add(row)
        s.commit()


# --- vector helpers --------------------------------------------------------
def test_pack_unpack_roundtrip_and_normalization():
    vec = [3.0, 4.0, 0.0]           # length 5 → normalized to 0.6, 0.8, 0
    blob = embeddings._pack(vec)
    got = list(embeddings._unpack(blob))
    assert len(got) == 3
    assert math.isclose(got[0], 0.6, abs_tol=1e-6)
    assert math.isclose(got[1], 0.8, abs_tol=1e-6)
    # Unit length after normalization.
    assert math.isclose(math.sqrt(sum(x * x for x in got)), 1.0, abs_tol=1e-6)


def test_pack_zero_vector_is_safe():
    # A zero vector must not divide-by-zero; it stays all-zeros.
    assert list(embeddings._unpack(embeddings._pack([0.0, 0.0, 0.0]))) == [0.0, 0.0, 0.0]


def test_content_sig_stable_and_sensitive():
    a = embeddings._content_sig("Invoice", "please pay")
    assert a == embeddings._content_sig("Invoice", "please pay")   # deterministic
    assert a != embeddings._content_sig("Invoice", "different")     # snippet matters
    assert a != embeddings._content_sig("Receipt", "please pay")    # subject matters


# --- ranking (both backends) ----------------------------------------------
def _rank_ids(ids, vecs, qvec, limit=10):
    # Stored vectors are normalized on pack; _rank normalizes the query itself.
    if embeddings._np is not None:
        mat = embeddings._np.stack(
            [embeddings._np.frombuffer(embeddings._pack(v), dtype=embeddings._np.float32) for v in vecs])
    else:
        mat = [embeddings._unpack(embeddings._pack(v)) for v in vecs]
    return [mid for mid, _ in embeddings._rank(qvec, ids, mat, limit)]


def test_rank_orders_by_cosine_numpy():
    if embeddings._np is None:
        pytest.skip("numpy not installed")
    ids = [10, 20, 30]
    vecs = [_fake_vec("alpha beta"), _fake_vec("gamma delta"), _fake_vec("epsilon zeta")]
    order = _rank_ids(ids, vecs, _fake_vec("alpha beta text"))
    assert order[0] == 10


def test_rank_pure_python_fallback_matches(monkeypatch):
    # Force the numpy-less path and confirm the same ordering.
    monkeypatch.setattr(embeddings, "_np", None)
    ids = [10, 20, 30]
    vecs = [_fake_vec("alpha beta"), _fake_vec("gamma delta"), _fake_vec("epsilon zeta")]
    order = _rank_ids(ids, vecs, _fake_vec("gamma delta more"))
    assert order[0] == 20


# --- indexing + search end-to-end ------------------------------------------
def _seed_messages(model: str):
    """Three messages with distinct vocab; returns (account, {label: message_id})."""
    with _s() as s:
        acct = Account(email=f"sem-{model}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        folder = Folder(account_id=acct.id, name="INBOX", path="INBOX")
        s.add(folder); s.commit(); s.refresh(folder)
        rows = {
            "ab": Message(account_id=acct.id, folder_id=folder.id, uid=1,
                          message_id=f"<ab-{model}>", from_addr="a@x.com", subject="alpha beta"),
            "gd": Message(account_id=acct.id, folder_id=folder.id, uid=2,
                          message_id=f"<gd-{model}>", from_addr="b@x.com", subject="gamma delta"),
            "ez": Message(account_id=acct.id, folder_id=folder.id, uid=3,
                          message_id=f"<ez-{model}>", from_addr="c@x.com", subject="epsilon zeta"),
        }
        for m in rows.values():
            s.add(m)
        s.commit()
        return acct.id, {k: m.id for k, m in rows.items()}


def test_index_pending_and_search(client, monkeypatch):
    monkeypatch.setattr(embeddings, "_embed_batch", _fake_embed)
    embeddings._cache.update({"key": None, "ids": None, "mat": None})
    model = "test-index"
    _set_semantic(model)
    _, ids = _seed_messages(model)

    with _s() as s:
        n = embeddings.index_pending(s, limit=100)
    assert n >= 3   # at least our three (plus any bare rows from other tests)

    # Every seeded message now has a current-model vector.
    with _s() as s:
        for mid in ids.values():
            row = s.get(MessageEmbedding, mid)
            assert row is not None and row.model == model and row.dim == len(_VOCAB)

    # Search for a query closest to the "gamma delta" message.
    with _s() as s:
        hits = embeddings.search(s, "gamma delta please", limit=5)
    assert hits and hits[0] == ids["gd"]


def test_index_pending_skips_already_indexed(client, monkeypatch):
    calls = {"n": 0}

    def counting_embed(cfg, texts):
        calls["n"] += len(texts)
        return _fake_embed(cfg, texts)

    monkeypatch.setattr(embeddings, "_embed_batch", counting_embed)
    model = "test-skip"
    _set_semantic(model)
    _seed_messages(model)

    with _s() as s:
        embeddings.index_pending(s, limit=100)
    first = calls["n"]
    assert first >= 3
    with _s() as s:
        n2 = embeddings.index_pending(s, limit=100)
    assert n2 == 0                 # nothing new to embed
    assert calls["n"] == first     # and no wasted embed calls


def test_search_disabled_returns_empty(client):
    _set_semantic("test-off", enabled=False)
    with _s() as s:
        assert embeddings.search(s, "alpha beta") == []


def test_reachable_false_without_base():
    cfg = {"provider": "openai-compatible", "base_url": "", "model": "m", "key": ""}
    assert embeddings.reachable(cfg) is False


# --- endpoints --------------------------------------------------------------
def test_ollama_status_endpoint_shape(client):
    """The endpoint returns a well-formed payload whether or not Ollama is
    installed/running on the host (don't assume the dev box lacks it)."""
    r = client.get("/ai/ollama/status")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["installed"], bool)
    assert isinstance(body["running"], bool)
    assert isinstance(body["models"], list)
    assert "base_url" in body


def test_ai_status_ollama_is_keyless_configured(client):
    with _s() as s:
        row = s.get(Setting, 1) or Setting(id=1, data={})
        row.data = {**(row.data or {}), "aiProvider": "ollama", "aiApiKey": ""}
        s.add(row); s.commit()
    body = client.get("/ai/status").json()
    assert body["provider"] == "ollama"
    assert body["configured"] is True    # local, no key needed


def test_embed_status_endpoint(client):
    _set_semantic("test-status", enabled=False)
    body = client.get("/ai/embed/status").json()
    assert body["enabled"] is False
    assert "indexed" in body and "total" in body
    assert body["backend"] in ("numpy", "python")


def test_semantic_endpoint_empty_when_disabled(client):
    _set_semantic("test-endpoint-off", enabled=False)
    r = client.get("/messages/semantic?q=alpha")
    assert r.status_code == 200
    assert r.json() == []
