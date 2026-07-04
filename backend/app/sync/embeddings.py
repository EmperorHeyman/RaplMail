"""Local semantic search: dense-vector embeddings + cosine ranking.

Zero-cloud by default. Embeddings are produced by the user's own **local** model
server — Ollama (`/api/embeddings`) or any OpenAI-compatible `/v1/embeddings`
endpoint (LM Studio, llama.cpp server, vLLM, or a paid API if they insist). The
vectors are stored in SQLite (one BLOB per message) and never leave the machine.

Search is a brute-force cosine over the stored vectors. For a personal mailbox
(thousands to low-tens-of-thousands of messages) that's a single matrix–vector
product — milliseconds with numpy, still fine in pure Python as a fallback. This
deliberately avoids a native vector-index extension (sqlite-vec) and a bundled
ONNX runtime: both would bloat the frozen sidecar with hundreds of MB of native
code, and the embedding endpoint we already need for "local intelligence"
(Ollama) supplies embeddings for free.

Everything here is best-effort and opt-in: if semantic search is disabled or the
endpoint is unreachable, indexing silently no-ops and search returns nothing so
the caller can fall back to keyword search.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import ssl
import urllib.request
from array import array

from sqlmodel import Session, select

from app.models import Message, MessageEmbedding, Setting

log = logging.getLogger("raplmail.embeddings")

try:  # Fast path. Soft dependency — the pure-Python fallback keeps this working
    import numpy as _np  # (and tests green) in a numpy-less environment.
except Exception:  # noqa: BLE001
    _np = None

# Sensible defaults for the local-first path.
OLLAMA_DEFAULT_URL = "http://localhost:11434"
OLLAMA_DEFAULT_EMBED_MODEL = "nomic-embed-text"
OPENAI_DEFAULT_EMBED_MODEL = "text-embedding-3-small"

# How much text per message we feed the embedder. Subject+sender+snippet is
# always present and cheap; a slice of the cached body is folded in when we have
# it (see _message_text). Capped so a giant newsletter doesn't dominate cost.
_MAX_CHARS = 2000


def _embed_config(session: Session) -> dict:
    row = session.get(Setting, 1)
    data = dict(row.data) if row and row.data else {}
    provider = str(data.get("embedProvider") or "ollama").strip().lower()
    if provider not in ("ollama", "openai-compatible"):
        provider = "ollama"
    base = str(data.get("embedBaseUrl") or "").strip().rstrip("/")
    if provider == "ollama" and not base:
        base = OLLAMA_DEFAULT_URL
    model = str(data.get("embedModel") or "").strip() or (
        OLLAMA_DEFAULT_EMBED_MODEL if provider == "ollama" else OPENAI_DEFAULT_EMBED_MODEL)
    return {
        "enabled": bool(data.get("semanticEnabled")),
        "provider": provider,
        "base_url": base,
        "model": model,
        "key": str(data.get("embedApiKey") or "").strip(),
    }


# --- HTTP to the embedding endpoint ----------------------------------------
def _http_json(url: str, body: dict, headers: dict, timeout: int = 60) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"content-type": "application/json", **headers})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _embed_batch(cfg: dict, texts: list[str]) -> list[list[float]]:
    """Return one embedding per input text. Raises on transport/endpoint error."""
    if not texts:
        return []
    provider, base, model, key = cfg["provider"], cfg["base_url"], cfg["model"], cfg["key"]
    if not base:
        raise RuntimeError("No embeddings endpoint configured.")
    if provider == "ollama":
        # Ollama's /api/embeddings takes a single prompt and returns one vector.
        # It's the universally-supported endpoint (older builds lack /api/embed),
        # so we call it once per text. Local + on the loopback, so this is cheap.
        # keep_alive="30s": let the background indexer's model fall out of VRAM
        # shortly after a batch instead of pinning the GPU on Ollama's 5-min default.
        out: list[list[float]] = []
        for txt in texts:
            payload = _http_json(f"{base}/api/embeddings",
                                 {"model": model, "prompt": txt, "keep_alive": "30s"}, {})
            vec = payload.get("embedding") or []
            out.append([float(x) for x in vec])
        return out
    # openai-compatible: /v1/embeddings accepts a batch and returns data[].embedding.
    b = base if base.endswith("/v1") else base + "/v1"
    headers = {"authorization": f"Bearer {key}"} if key else {}
    payload = _http_json(f"{b}/embeddings", {"model": model, "input": texts}, headers)
    rows = payload.get("data") or []
    # Preserve request order (OpenAI returns an `index` on each row).
    rows = sorted(rows, key=lambda r: r.get("index", 0))
    return [[float(x) for x in (r.get("embedding") or [])] for r in rows]


def reachable(cfg: dict) -> bool:
    """Quick liveness probe of the embedding endpoint (no model load)."""
    base = cfg.get("base_url") or ""
    if not base:
        return False
    try:
        if cfg["provider"] == "ollama":
            req = urllib.request.Request(f"{base}/api/tags", method="GET")
            urllib.request.urlopen(req, timeout=4).close()
            return True
        # openai-compatible: a 1-D embed of "ping" is the cheapest real check.
        _embed_batch(cfg, ["ping"])
        return True
    except Exception:  # noqa: BLE001
        return False


# --- vector helpers --------------------------------------------------------
def _normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    if n <= 0:
        return vec
    return [x / n for x in vec]


def _pack(vec: list[float]) -> bytes:
    """Little-endian float32 bytes of an L2-normalized vector."""
    return array("f", _normalize(vec)).tobytes()


def _unpack(blob: bytes) -> array:
    a = array("f")
    a.frombytes(blob)
    return a


def _content_sig(subject: str, snippet: str) -> str:
    h = hashlib.sha1()  # noqa: S324 — not security; just change-detection
    h.update((subject or "").encode("utf-8", "ignore"))
    h.update(b"\x00")
    h.update((snippet or "").encode("utf-8", "ignore"))
    return h.hexdigest()


def _message_text(m: Message) -> str:
    """The text we embed for a message: subject + sender + snippet.

    Deliberately NOT the full body — that would mean decrypting every cached body
    during a background sweep, and most messages are never body-fetched anyway, so
    an index mixing "subject+body" and "subject-only" rows would rank inconsistently.
    Subject + sender + snippet is uniform, always present, needs no decryption, and
    never changes after sync (so a message is embedded exactly once)."""
    parts = [m.subject or "", m.from_name or m.from_addr or "", m.snippet or ""]
    text = "\n".join(p for p in parts if p).strip()
    return text[:_MAX_CHARS]


# --- indexing --------------------------------------------------------------
def index_pending(session: Session, cfg: dict | None = None, limit: int = 64) -> int:
    """Embed up to `limit` messages that are missing / stale in the vector index.

    A message needs (re)embedding when it has no vector, was embedded with a
    different model, or its embeddable text changed (e.g. the body got cached
    after first open). Returns the number newly embedded. Best-effort: a batch
    that fails to reach the endpoint just returns 0 and is retried next tick.
    """
    cfg = cfg or _embed_config(session)
    if not cfg["enabled"] or not cfg["base_url"]:
        return 0
    model = cfg["model"]
    # Messages with no vector for the current model, newest first (the mail you're
    # most likely to search for is indexed first). A NOT IN subquery keeps this
    # O(missing) rather than scanning every row every tick. Subject/snippet never
    # change after sync, so "has a current-model row" == "up to date".
    have = select(MessageEmbedding.message_id).where(MessageEmbedding.model == model)
    todo = list(session.exec(
        select(Message).where(Message.id.not_in(have))
        .order_by(Message.date.desc()).limit(limit)
    ))
    if not todo:
        return 0
    texts = [_message_text(m) for m in todo]
    try:
        vectors = _embed_batch(cfg, texts)
    except Exception as exc:  # noqa: BLE001
        log.info("embedding batch failed (will retry): %s", exc)
        return 0
    from app.models import utcnow
    n = 0
    for m, vec in zip(todo, vectors):
        if not vec:
            continue
        row = session.get(MessageEmbedding, m.id) or MessageEmbedding(message_id=m.id)
        row.model = model
        row.dim = len(vec)
        row.vec = _pack(vec)
        row.sig = _content_sig(m.subject, m.snippet)
        row.updated_at = utcnow()
        session.add(row)
        n += 1
    session.commit()
    return n


def indexed_count(session: Session, model: str | None = None) -> int:
    from sqlalchemy import func
    stmt = select(func.count()).select_from(MessageEmbedding)
    if model:
        stmt = stmt.where(MessageEmbedding.model == model)
    return int(session.exec(stmt).one())


def status(session: Session) -> dict:
    from sqlalchemy import func
    cfg = _embed_config(session)
    total = int(session.exec(select(func.count()).select_from(Message)).one())
    indexed = indexed_count(session, cfg["model"])
    return {
        "enabled": cfg["enabled"],
        "provider": cfg["provider"],
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "indexed": indexed,
        "total": total,
        "backend": "numpy" if _np is not None else "python",
    }


# --- search ----------------------------------------------------------------
# Small process cache of the vector matrix so repeated searches don't re-read +
# re-parse every BLOB. Invalidated when the row count or newest updated_at moves.
_cache: dict = {"key": None, "ids": None, "mat": None}


def _cache_key(session: Session, model: str) -> tuple:
    from sqlalchemy import func
    row = session.exec(
        select(func.count(), func.max(MessageEmbedding.updated_at))
        .where(MessageEmbedding.model == model)
    ).one()
    return (model, int(row[0] or 0), str(row[1] or ""))


def _load_matrix(session: Session, model: str):
    """(ids, matrix) for the given model. matrix is a numpy (N,D) array when
    numpy is available, else a list of `array('f')` rows."""
    key = _cache_key(session, model)
    if _cache["key"] == key and _cache["ids"] is not None:
        return _cache["ids"], _cache["mat"]
    ids: list[int] = []
    rows: list[bytes] = []
    for e in session.exec(
        select(MessageEmbedding.message_id, MessageEmbedding.vec)
        .where(MessageEmbedding.model == model)
    ):
        ids.append(e[0])
        rows.append(e[1])
    if _np is not None and rows:
        try:
            mat = _np.stack([_np.frombuffer(b, dtype=_np.float32) for b in rows])
        except Exception:  # noqa: BLE001 — ragged rows (mixed dims) → per-row path
            mat = [_unpack(b) for b in rows]
    else:
        mat = [_unpack(b) for b in rows]
    _cache.update({"key": key, "ids": ids, "mat": mat})
    return ids, mat


def embed_query(session: Session, q: str, cfg: dict | None = None) -> list[float] | None:
    cfg = cfg or _embed_config(session)
    if not cfg["base_url"]:
        return None
    try:
        vecs = _embed_batch(cfg, [q])
    except Exception as exc:  # noqa: BLE001
        log.info("query embed failed: %s", exc)
        return None
    return vecs[0] if vecs else None


def _rank(qvec: list[float], ids: list[int], mat, limit: int) -> list[tuple[int, float]]:
    """Top-`limit` (message_id, score) by cosine similarity. Stored vectors are
    already L2-normalized, so we only normalize the query and take dot products."""
    if not ids:
        return []
    qn = _normalize(qvec)
    if _np is not None and hasattr(mat, "shape"):
        qa = _np.asarray(qn, dtype=_np.float32)
        if qa.shape[0] != mat.shape[1]:
            return []  # dimension mismatch (model changed mid-index) → no results
        scores = mat @ qa
        top = _np.argsort(-scores)[:limit]
        return [(ids[i], float(scores[i])) for i in top]
    # Pure-Python fallback.
    scored: list[tuple[int, float]] = []
    for mid, vec in zip(ids, mat):
        if len(vec) != len(qn):
            continue
        scored.append((mid, sum(a * b for a, b in zip(qn, vec))))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]


def search(session: Session, q: str, limit: int = 60,
           min_score: float = 0.2) -> list[int]:
    """Return message ids ranked by semantic similarity to `q` (best first).
    Empty when semantic search is off, the endpoint is down, or nothing indexed."""
    cfg = _embed_config(session)
    if not cfg["enabled"] or not (q or "").strip():
        return []
    qvec = embed_query(session, q, cfg)
    if not qvec:
        return []
    ids, mat = _load_matrix(session, cfg["model"])
    ranked = _rank(qvec, ids, mat, limit)
    return [mid for mid, score in ranked if score >= min_score]
