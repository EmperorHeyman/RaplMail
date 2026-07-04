"""Bring-your-own-key AI helpers (thread summaries, "Catch me up").

Privacy-first: there is no RaplMail server. The user's own API key lives in the
local settings blob and calls go straight from this backend to the provider the
user chose. Nothing is sent anywhere unless the user explicitly asks for it and
has configured a key. Uses stdlib urllib — no SDK dependency.
"""

from __future__ import annotations

import json
import re
import shutil
import ssl
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Folder, FolderRole, Message, Setting

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(verify_token)])

# BYOK, any provider. Default model per provider (used when the user leaves the
# model field blank). "openai-compatible" covers Groq / OpenRouter / Together /
# LM Studio / vLLM etc.; "ollama" is a first-class, keyless local server that also
# speaks the OpenAI chat API (at /v1/chat/completions) — both fully offline.
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "openai-compatible": "gpt-4o-mini",
    "ollama": "llama3.2",
}
_PROVIDERS = ("anthropic", "openai", "openai-compatible", "ollama")
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_URL = "https://api.openai.com"
_OLLAMA_URL = "http://localhost:11434"
# Default chat base URL for the OpenAI-shaped providers (blank = user must set one).
_DEFAULT_BASE = {"openai": _OPENAI_URL, "ollama": _OLLAMA_URL}


def _ai_config(session: Session) -> dict:
    row = session.get(Setting, 1)
    data = dict(row.data) if row and row.data else {}
    provider = str(data.get("aiProvider") or "anthropic").strip().lower()
    if provider not in _PROVIDERS:
        provider = "anthropic"
    base = str(data.get("aiBaseUrl") or "").strip().rstrip("/")
    if provider == "ollama" and not base:
        base = _OLLAMA_URL   # keyless local default
    return {
        "provider": provider,
        "key": str(data.get("aiApiKey") or "").strip(),
        "model": str(data.get("aiModel") or "").strip() or DEFAULT_MODELS[provider],
        "base_url": base,
        # How long Ollama keeps the model in VRAM after a request. Short → frees the
        # GPU sooner when you're not actively chatting. "-1" keeps it loaded. In
        # "adaptive" mode the frontend warms on focus / unloads on blur, so chat
        # requests keep the model resident (-1) and the blur handler unloads it.
        "keep_alive": _keep_alive(str(data.get("ollamaKeepAlive") or "5m").strip()),
    }


def _keep_alive(setting: str):
    """Ollama's keep_alive: duration strings ("30s", "5m") must keep their unit,
    but 0 / -1 have to be sent as JSON *numbers* — "0"/"-1" as strings fail with
    'missing unit in duration'. "adaptive" keeps the model loaded (-1); the app
    unloads it on blur. Returns an int for 0/-1, else the duration string."""
    if setting in ("adaptive", "-1"):
        return -1
    if setting == "0":
        return 0
    return setting


# Appended to every generative prompt: match the user's language. Small local
# models otherwise default to English even when the user writes in Czech. The
# example is symmetric so it doesn't bias toward any one language.
_LANG_RULE = (" Always write your response in the SAME LANGUAGE as the user's "
              "message (Czech in → Czech out, English in → English out). ")


def _openai_chat_url(base: str) -> str:
    """Normalize a user-supplied base URL to the chat-completions endpoint."""
    b = (base or _OPENAI_URL).rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    if b.endswith("/v1"):
        return b + "/chat/completions"
    return b + "/v1/chat/completions"


def _call_chat(cfg: dict, system: str, turns: list[dict], max_tokens: int = 700) -> str:
    """Provider-agnostic chat call. `turns` is a list of {role, content} (roles
    "user"/"assistant"), enabling multi-turn conversations (the AI assistant) as
    well as one-shot prompts. Branches on cfg['provider'] for request shape, auth,
    and response parsing; shares timeout + error handling."""
    provider, key, model = cfg.get("provider", "anthropic"), cfg["key"], cfg["model"]
    if provider == "anthropic":
        url = _ANTHROPIC_URL
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = json.dumps({
            "model": model, "max_tokens": max_tokens, "system": system, "messages": turns,
        }).encode("utf-8")
    elif provider == "ollama":
        # Native /api/chat (not the OpenAI-compat shim) so we can pass keep_alive —
        # the lever that frees the GPU after a short idle instead of Ollama's 5-min
        # default. Keyless on the loopback; send Authorization only if one is set.
        base = cfg.get("base_url") or _OLLAMA_URL
        url = base.rstrip("/") + "/api/chat"
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        body = json.dumps({
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system}, *turns],
            "keep_alive": cfg.get("keep_alive", "5m"),
            "options": {"num_predict": max_tokens},
        }).encode("utf-8")
    else:  # openai / openai-compatible (OpenAI chat API)
        base = cfg.get("base_url") or _DEFAULT_BASE.get(provider, "")
        if not base:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Set the API base URL for the OpenAI-compatible provider in "
                                "Settings → General → AI assistant.")
        url = _openai_chat_url(base)
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        body = json.dumps({
            "model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *turns],
        }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI provider error ({e.code}): {detail}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't reach the AI provider: {e}")
    if provider == "anthropic":
        parts = payload.get("content") or []
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
    if provider == "ollama":
        return ((payload.get("message") or {}).get("content") or "").strip()
    try:
        return (payload["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


def _call_provider(cfg: dict, system: str, prompt: str, max_tokens: int = 700) -> str:
    """One-shot convenience wrapper around _call_chat (single user turn)."""
    return _call_chat(cfg, system, [{"role": "user", "content": prompt}], max_tokens)


# How many message bodies we'll fetch over IMAP to build a transcript. Bodies are
# only cached on first open, so an AI query over unopened mail would otherwise see
# just the subject + snippet (the exact "it only sees who it's from" complaint).
_BODY_FETCH_CAP = 20


def _message_text(session: Session, m: Message, fetch: bool = True) -> str:
    """The best available body text for a message. Uses the cached body if present,
    otherwise fetches + caches it over IMAP (like opening it) so the model sees the
    real content, not just the snippet. Best-effort; falls back to the snippet."""
    from app.core.atrest import decrypt_field, encrypt_field
    if m.body_fetched and m.body_text:
        return (decrypt_field(m.body_text) or m.snippet or "").strip()
    if not fetch:
        return (m.snippet or "").strip()
    try:
        from app.api.messages import _fetch_body
        from app.models import Account, Folder
        acct = session.get(Account, m.account_id)
        fld = session.get(Folder, m.folder_id)
        if not acct or not fld:
            return (m.snippet or "").strip()
        html, text_body, *_ = _fetch_body(acct, fld, m.uid)
        body = (text_body or "").strip()
        if not body and html:
            body = re.sub(r"<[^>]+>", " ", html)
            body = re.sub(r"\s+", " ", body).strip()
        if body:
            m.body_html, m.body_text = encrypt_field(html or ""), encrypt_field(text_body or body)
            m.body_fetched = True
            session.add(m)
            session.commit()
        return body or (m.snippet or "").strip()
    except Exception:  # noqa: BLE001
        return (m.snippet or "").strip()


def _thread_text(session: Session, thread_id: str, fallback_id: int | None) -> tuple[str, str]:
    """Build a transcript for the model. Returns (subject, transcript)."""
    msgs: list[Message] = []
    if thread_id:
        msgs = list(session.exec(select(Message).where(Message.thread_id == thread_id)))
    if not msgs and fallback_id is not None:
        m = session.get(Message, fallback_id)
        if m:
            msgs = [m]
    # thread_id is account-scoped by construction ("<account_id>|<subject>"), but
    # keep the transcript to a single account defensively so a future thread-key
    # scheme can't leak one mailbox's content into another's AI prompt.
    if msgs:
        acct = msgs[0].account_id
        msgs = [m for m in msgs if m.account_id == acct]
    msgs.sort(key=lambda m: m.date.timestamp() if m.date else 0.0)
    subject = msgs[0].subject if msgs else ""
    lines = []
    for i, m in enumerate(msgs):
        who = m.from_name or m.from_addr or "?"
        when = m.date.strftime("%Y-%m-%d %H:%M") if m.date else ""
        text = _message_text(session, m, fetch=i < _BODY_FETCH_CAP)
        lines.append(f"--- From: {who}  ({when})\nSubject: {m.subject}\n{text[:4000]}")
    return subject, "\n\n".join(lines)


def _context_text(session: Session, message_ids: list[int], thread_id: str = "") -> str:
    """Build a transcript from an explicit set of messages (the AI assistant's
    context tray) and/or a whole thread — oldest first. Fetches + caches missing
    bodies (capped) so the assistant sees real content, not just subject/snippet."""
    msgs: dict[int, Message] = {}
    for mid in (message_ids or []):
        m = session.get(Message, mid)
        if m:
            msgs[m.id] = m
    if thread_id:
        for m in session.exec(select(Message).where(Message.thread_id == thread_id)):
            msgs[m.id] = m
    ordered = sorted(msgs.values(), key=lambda m: m.date.timestamp() if m.date else 0.0)
    lines = []
    for i, m in enumerate(ordered):
        who = m.from_name or m.from_addr or "?"
        to = ", ".join(m.to_addrs or [])
        when = m.date.strftime("%Y-%m-%d %H:%M") if m.date else ""
        text = _message_text(session, m, fetch=i < _BODY_FETCH_CAP)
        lines.append(f"--- From: {who}  To: {to}  ({when})\nSubject: {m.subject}\n{text[:4000]}")
    return "\n\n".join(lines)


class SummarizeIn(BaseModel):
    message_id: int | None = None
    thread_id: str | None = None


def _configured(cfg: dict) -> bool:
    # Ollama needs no key (local, keyless), so it's "configured" as soon as it's
    # selected; every other provider needs the user's API key.
    return bool(cfg["key"]) or cfg["provider"] == "ollama"


@router.get("/status")
def ai_status(session: Session = Depends(get_session)) -> dict:
    cfg = _ai_config(session)
    return {"configured": _configured(cfg), "model": cfg["model"], "provider": cfg["provider"]}


@router.post("/summarize")
def summarize(body: SummarizeIn, session: Session = Depends(get_session)) -> dict:
    cfg = _require_key(session)
    subject, transcript = _thread_text(session, body.thread_id or "", body.message_id)
    if not transcript.strip():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing to summarize.")
    system = (
        "You are an assistant inside an email client. Summarize the email thread "
        "for a busy professional. Be concise. Output: a one-line TL;DR, then 2-5 "
        "bullet points of key facts/decisions, then a short 'Action items' list "
        "(or 'No action needed'). Use plain text, no preamble." + _LANG_RULE
    )
    summary = _call_provider(cfg, system,
                              f"Thread subject: {subject}\n\n{transcript[:24000]}")
    return {"summary": summary, "model": cfg["model"]}


def _require_key(session: Session) -> dict:
    cfg = _ai_config(session)
    if not _configured(cfg):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No AI API key set. Add one in Settings → General → AI assistant.")
    return cfg


# Small local models rarely emit the exact "###CHIPS###" marker we ask for —
# they write "###CHIPS|", "## CHIPS:", "CHIPS: ", etc. Match those forms (marker
# must have a '#' prefix OR a ':'/'|' right after, so a reply that merely contains
# the word "chips" isn't truncated) so the chips never leak into the reply body.
_CHIPS_RE = re.compile(r"(?:#{1,3}\s*CHIPS|CHIPS\s*[:|])[#:\-–—|\s]*", re.IGNORECASE)


def _split_chips(raw: str) -> tuple[str, list[str]]:
    """Return (reply_body, quick_reply_chips) from the model's raw output."""
    m = _CHIPS_RE.search(raw or "")
    if not m:
        return (raw or "").strip(), []
    draft = raw[:m.start()].strip()
    chip_str = raw[m.end():]
    chips = [c.strip(" -–—|*•\t") for c in re.split(r"[|\n]", chip_str)]
    chips = [c for c in chips if c][:3]
    return draft, chips


class DraftIn(BaseModel):
    message_id: int | None = None
    thread_id: str | None = None
    instruction: str = ""        # optional steer, e.g. "decline politely", "ask for a call"


@router.post("/draft")
def draft_reply(body: DraftIn, session: Session = Depends(get_session)) -> dict:
    """Draft a reply in the user's voice + a few one-tap quick replies. Never sends."""
    cfg = _require_key(session)
    subject, transcript = _thread_text(session, body.thread_id or "", body.message_id)
    if not transcript.strip():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing to reply to.")
    steer = f"\n\nThe user wants the reply to: {body.instruction}" if body.instruction.strip() else ""
    system = (
        "You draft email replies for the user (the most recent recipient of the thread). "
        "Write a complete, ready-to-send reply body — natural, concise, matching the thread's "
        "tone. IMPORTANT: write the reply in the SAME LANGUAGE as the email you're replying to "
        "(e.g. reply in Czech to a Czech email). Do NOT include a subject line, quoted history, "
        "or a signature. After the reply, add a line that starts with the token CHIPS: followed "
        "by 2-3 very short (2-5 word) quick-reply options separated by ' | '. Output plain text."
    )
    raw = _call_provider(cfg, system,
                          f"Thread subject: {subject}\n\n{transcript[:24000]}{steer}", max_tokens=900)
    draft, chips = _split_chips(raw)
    return {"draft": draft, "chips": chips, "model": cfg["model"]}


def build_inbox_digest(session: Session, cfg: dict) -> dict:
    """Shared digest builder used by the endpoint and the scheduled morning brief."""
    inbox_ids = list(session.exec(select(Folder.id).where(Folder.role == FolderRole.inbox)))
    rows = session.exec(
        select(Message).where(
            Message.folder_id.in_(inbox_ids or [-1]),
            Message.is_seen == False,  # noqa: E712
            Message.is_done == False,  # noqa: E712
            Message.pending_action == "",
        ).order_by(Message.date.desc()).limit(40)
    ).all()
    if not rows:
        return {"digest": "Your inbox is clear — no unread mail. 🎉", "count": 0, "model": cfg["model"]}
    lines = []
    for m in rows:
        who = m.from_name or m.from_addr or "?"
        lines.append(f"- [{m.id}] {who}: {m.subject} — {(m.snippet or '')[:160]}")
    system = (
        "You are triaging a busy person's unread inbox. Given the list of unread messages, "
        "produce a short briefing: group by urgency. Start with '🔴 Needs attention' (things "
        "that look time-sensitive or personally addressed), then '🟡 Worth a look', then "
        "'⚪ Low priority / newsletters'. One concise line per item, newest context first. "
        "Skip empty groups. Plain text, no preamble."
    )
    digest = _call_provider(cfg, system,
                             "Unread messages:\n" + "\n".join(lines), max_tokens=1000)
    return {"digest": digest, "count": len(rows), "model": cfg["model"]}


def generate_scheduled_digest() -> dict | None:
    """Called by the sync engine for the morning brief. Returns None if AI isn't
    configured (so the scheduler can silently skip)."""
    from app.core.db import get_engine
    with Session(get_engine()) as session:
        cfg = _ai_config(session)
        if not cfg["key"]:
            return None
        return build_inbox_digest(session, cfg)


@router.post("/digest")
def inbox_digest(session: Session = Depends(get_session)) -> dict:
    """A prioritized 'catch me up' digest of recent unread inbox mail."""
    cfg = _require_key(session)
    return build_inbox_digest(session, cfg)


class TriageIn(BaseModel):
    limit: int = 20


@router.post("/triage")
def triage_priority(body: TriageIn, session: Session = Depends(get_session)) -> dict:
    """Score the top unread inbox messages 0-100 by importance, with a one-line reason."""
    cfg = _require_key(session)
    inbox_ids = list(session.exec(select(Folder.id).where(Folder.role == FolderRole.inbox)))
    rows = session.exec(
        select(Message).where(
            Message.folder_id.in_(inbox_ids or [-1]),
            Message.is_seen == False,  # noqa: E712
            Message.is_done == False,  # noqa: E712
            Message.pending_action == "",
        ).order_by(Message.date.desc()).limit(max(1, min(body.limit, 40)))
    ).all()
    if not rows:
        return {"scores": [], "model": cfg["model"]}
    lines = [f"[{m.id}] from {m.from_name or m.from_addr}: {m.subject} — {(m.snippet or '')[:140]}"
             for m in rows]
    system = (
        "Score each email's importance 0-100 for a busy professional (100 = urgent/personal, "
        "0 = bulk/newsletter). Return ONLY a JSON array of objects "
        '{"id": <message id>, "score": <0-100>, "reason": "<=8 words"}. No other text.'
    )
    raw = _call_provider(cfg, system, "\n".join(lines), max_tokens=1500)
    try:
        start, end = raw.find("["), raw.rfind("]")
        scores = json.loads(raw[start:end + 1]) if start >= 0 else []
    except Exception:
        scores = []
    return {"scores": scores, "model": cfg["model"]}


# ---------------------------------------------------------------------------
# Compose helper: rewrite / transform the text the user is writing
# ---------------------------------------------------------------------------
# Per-action instruction appended to the shared system prompt. "custom" uses the
# user's freeform instruction verbatim.
_REWRITE_ACTIONS = {
    "rephrase":     "Rephrase the text so it reads better while keeping the same meaning and tone.",
    "improve":      "Improve the writing: clearer, more natural and polished, same meaning and intent.",
    "shorten":      "Make the text more concise — cut the fluff, keep every important point.",
    "expand":       "Expand the text with a little more detail and courtesy, without padding or repetition.",
    "grammar":      "Fix spelling, grammar and punctuation only. Do NOT change wording, tone or meaning otherwise.",
    "professional": "Rewrite in a polished, professional tone.",
    "friendly":     "Rewrite in a warm, friendly, approachable tone.",
    "formal":       "Rewrite in a formal, respectful tone.",
    "concise":      "Rewrite to be as concise and direct as possible.",
    "confident":    "Rewrite in a confident, assertive tone (never rude).",
    "translate":    "Translate the text into {arg}. Output only the translation.",
}


class RewriteIn(BaseModel):
    text: str
    action: str = "rephrase"
    instruction: str = ""     # target language for "translate"; the whole prompt for "custom"


@router.post("/rewrite")
def rewrite(body: RewriteIn, session: Session = Depends(get_session)) -> dict:
    """Transform the draft (or a selected fragment) in the composer: rephrase,
    fix grammar, change tone, translate, shorten/expand, or a freeform instruction.
    Returns ONLY the rewritten text so the UI can drop it straight in."""
    cfg = _require_key(session)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to rewrite.")
    action = (body.action or "rephrase").lower()
    if action == "custom":
        task = (body.instruction or "").strip() or "Improve the text."
    else:
        task = _REWRITE_ACTIONS.get(action, _REWRITE_ACTIONS["rephrase"])
        if action == "translate":
            task = task.replace("{arg}", (body.instruction or "English").strip())
    system = (
        "You are a writing assistant editing an email the user is composing. "
        f"{task}\n\n"
        "Rules: reply with ONLY the resulting text — no preamble, no explanations, no "
        "surrounding quotes, no markdown code fences. Preserve the original language "
        "unless asked to translate. Keep any greeting/sign-off the user already wrote. "
        "Do not invent facts, names, links, dates or numbers that aren't in the input."
    )
    result = _call_provider(cfg, system, text, max_tokens=2000)
    return {"result": result.strip(), "model": cfg["model"]}


# ---------------------------------------------------------------------------
# Ask: freeform Q&A / tasks over one or many messages (reader + AI assistant)
# ---------------------------------------------------------------------------
class AskIn(BaseModel):
    instruction: str
    message_ids: list[int] = []
    thread_id: str | None = None
    history: list[dict] = []      # prior turns [{role: "user"|"assistant", content}]


@router.post("/ask")
def ask(body: AskIn, session: Session = Depends(get_session)) -> dict:
    """Answer a freeform question or perform a task over a set of emails held as
    context (the open message, a whole thread, or several messages the user added
    to the AI assistant). Multi-turn via `history`. Never sends anything."""
    cfg = _require_key(session)
    instruction = (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ask me something.")
    transcript = _context_text(session, body.message_ids, body.thread_id or "")
    if transcript:
        system = (
            "You are an assistant inside an email client. The user has given you the "
            "following email(s) as context. Use them to answer or to carry out the task. "
            "Be concise and accurate; if the answer isn't in the emails, say so rather "
            "than inventing it. Plain text, no preamble." + _LANG_RULE + "\n\n"
            "=== EMAILS ===\n" + transcript[:48000] + "\n=== END EMAILS ==="
        )
    else:
        system = ("You are a helpful assistant inside an email client. Be concise and "
                  "practical. Plain text, no preamble." + _LANG_RULE)
    # Keep only well-formed prior turns, capped so the request stays bounded.
    turns = [{"role": t.get("role", "user"), "content": str(t.get("content", ""))}
             for t in (body.history or [])
             if t.get("role") in ("user", "assistant") and t.get("content")][-12:]
    turns.append({"role": "user", "content": instruction})
    answer = _call_chat(cfg, system, turns, max_tokens=1500)
    return {"answer": answer, "model": cfg["model"]}


class AiSearchIn(BaseModel):
    q: str


@router.post("/search")
def ai_search(body: AiSearchIn, session: Session = Depends(get_session)) -> dict:
    """Turn a plain-language request ("find the email about the Audi crash plate")
    into a short keyword search query the mail client can run. Returns just the
    query string; the frontend runs the actual search with it. Needs a provider."""
    cfg = _require_key(session)
    q = (body.q or "").strip()
    if not q:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to search for.")
    system = (
        "You convert a user's natural-language request to FIND an email into a short "
        "search query for a mail client. Output ONLY the 2-6 most distinctive keywords "
        "(the names, subjects, and nouns most likely to appear in that email) — no "
        "explanation, no quotes, no sentence. You MAY use these operators if clearly "
        "implied: from:NAME, subject:WORD, has:attachment, is:unread. Keep the original "
        "language of the keywords. Example: request 'najdi email kde se jedná o audi "
        "crash plate' → 'audi crash plate'."
    )
    raw = _call_provider(cfg, system, q, max_tokens=60)
    # Take just the first line and strip stray quotes/backticks the model may add.
    query = (raw or "").strip().splitlines()[0].strip().strip('"\'`').strip() if raw.strip() else ""
    return {"query": query, "model": cfg["model"]}


# ---------------------------------------------------------------------------
# Ollama: first-class local model server (detect / list / pull / install)
# ---------------------------------------------------------------------------
def _ollama_base(session: Session, override: str = "") -> str:
    """The Ollama URL to talk to: an explicit override (the settings field the
    user is editing), else the configured AI base when the provider is Ollama,
    else the loopback default."""
    if override.strip():
        return override.strip().rstrip("/")
    cfg = _ai_config(session)
    if cfg["provider"] == "ollama" and cfg["base_url"]:
        return cfg["base_url"]
    return _OLLAMA_URL


@router.get("/ollama/status")
def ollama_status(base: str = "", session: Session = Depends(get_session)) -> dict:
    """Detect a local Ollama: is the CLI installed, is the server up, which models
    are pulled. Drives the one-click setup card in Settings."""
    b = _ollama_base(session, base)
    installed = shutil.which("ollama") is not None
    running, models, version = False, [], ""
    try:
        req = urllib.request.Request(f"{b}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        running = True
        models = [m.get("name") for m in (data.get("models") or []) if m.get("name")]
    except Exception:  # noqa: BLE001 — not running / not installed
        pass
    if running:
        try:
            vreq = urllib.request.Request(f"{b}/api/version", method="GET")
            with urllib.request.urlopen(vreq, timeout=4) as vr:
                version = str(json.loads(vr.read().decode("utf-8")).get("version") or "")
        except Exception:  # noqa: BLE001
            pass
    return {"installed": installed or running, "running": running,
            "base_url": b, "models": models, "version": version}


def _parse_library_names(html: str) -> list[str]:
    """Extract model names from an ollama.com search/library page. Each model card
    links to /library/<name>; we dedupe, preserving order."""
    names, seen = [], set()
    for m in re.finditer(r'href="/library/([a-z0-9][a-z0-9._-]*)"', html or ""):
        n = m.group(1)
        if n not in seen:
            seen.add(n)
            names.append(n)
    return names


def _fetch_text(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers={"user-agent": "RaplMail"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return resp.read().decode("utf-8", "ignore")


@router.get("/ollama/search")
def ollama_search(q: str = "") -> dict:
    """Search Ollama's model library LIVE (so it's never stale — gemma3, gemma4,
    etc. show up as they're published). Scrapes ollama.com/search and returns the
    matching model names. Best-effort: returns [] (with an error note) if the site
    can't be reached — the curated recommendations still cover the offline case."""
    q = q.strip()
    if not q:
        return {"models": []}
    try:
        html = _fetch_text(f"https://ollama.com/search?q={urllib.parse.quote(q)}")
        return {"models": _parse_library_names(html)[:40]}
    except Exception as exc:  # noqa: BLE001
        return {"models": [], "error": str(exc)[:200]}


# Background job state for the long-running pull/install (polled by the UI).
_jobs: dict[str, dict] = {"pull": {}, "install": {}}


def _pull_worker(base: str, model: str) -> None:
    job = _jobs["pull"] = {"active": True, "model": model, "status": "starting",
                           "percent": 0, "error": "", "done": False}
    try:
        body = json.dumps({"model": model, "stream": True}).encode("utf-8")
        req = urllib.request.Request(f"{base}/api/pull", data=body, method="POST",
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=None) as resp:  # NDJSON stream
            for raw in resp:
                line = raw.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if d.get("status"):
                    job["status"] = str(d["status"])
                total, completed = d.get("total"), d.get("completed", 0)
                if total:
                    job["percent"] = max(0, min(100, int(100 * completed / total)))
                if d.get("error"):
                    job["error"] = str(d["error"])
        if not job["error"]:
            job["percent"] = 100
            job["status"] = "success"
    except Exception as exc:  # noqa: BLE001
        job["error"] = str(exc)
    finally:
        job["active"] = False
        job["done"] = True


class OllamaPullIn(BaseModel):
    model: str
    base: str = ""


@router.post("/ollama/pull")
def ollama_pull(body: OllamaPullIn, session: Session = Depends(get_session)) -> dict:
    """Download a model into Ollama (e.g. 'llama3.2', 'nomic-embed-text'). Runs in
    the background; poll /ai/ollama/pull-status for progress."""
    if _jobs["pull"].get("active"):
        raise HTTPException(status.HTTP_409_CONFLICT, "A model download is already running.")
    model = (body.model or "").strip()
    if not model:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No model name given.")
    base = _ollama_base(session, body.base)
    threading.Thread(target=_pull_worker, args=(base, model), daemon=True,
                     name="ollama-pull").start()
    return {"started": True, "model": model}


@router.get("/ollama/pull-status")
def ollama_pull_status() -> dict:
    return _jobs["pull"] or {"active": False, "done": False}


def _winget_worker(action: str) -> None:
    """Install or upgrade Ollama via winget (Windows). Shares the "install" job
    slot since the two are mutually exclusive from the UI's point of view."""
    verb = "upgrade" if action == "upgrade" else "install"
    job = _jobs["install"] = {"active": True, "status": "starting", "action": action,
                              "error": "", "done": False, "ok": False}
    try:
        # winget is the least-surprising unattended installer/updater. It may still
        # surface a UAC prompt; if winget is absent or declines, the UI falls back
        # to the manual download link.
        job["status"] = f"running winget {verb}…"
        proc = subprocess.run(  # noqa: S603,S607 — fixed, non-user args
            ["winget", verb, "--id", "Ollama.Ollama", "-e", "--silent",
             "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=True, text=True, timeout=900)
        out = (proc.stdout or "") + (proc.stderr or "")
        # `winget upgrade` returns non-zero (0x8A15002B) when nothing needs
        # upgrading — treat "no applicable upgrade / newest version" as success.
        if proc.returncode == 0:
            job["ok"] = True
            job["status"] = "installed" if verb == "install" else "updated"
        elif verb == "upgrade" and ("No applicable" in out or "no available upgrade" in out.lower()
                                    or "newer version" in out.lower() or "8A15002B" in out):
            job["ok"] = True
            job["status"] = "already up to date"
        else:
            job["error"] = out.strip()[:300] or f"winget exited {proc.returncode}"
    except FileNotFoundError:
        job["error"] = "winget isn't available on this system."
    except subprocess.TimeoutExpired:
        job["error"] = "The installer took too long. Try the manual download."
    except Exception as exc:  # noqa: BLE001
        job["error"] = str(exc)
    finally:
        job["active"] = False
        job["done"] = True


def _start_winget(action: str) -> dict:
    import sys
    if not sys.platform.startswith("win"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Automatic install/update is Windows-only — get Ollama from ollama.com.")
    if _jobs["install"].get("active"):
        raise HTTPException(status.HTTP_409_CONFLICT, "An install/update is already running.")
    threading.Thread(target=_winget_worker, args=(action,), daemon=True,
                     name=f"ollama-{action}").start()
    return {"started": True, "action": action}


@router.post("/ollama/install")
def ollama_install() -> dict:
    """Best-effort one-click install of Ollama via winget (Windows). Background job;
    poll /ai/ollama/install-status. The UI also offers the manual download link."""
    return _start_winget("install")


@router.post("/ollama/update")
def ollama_update() -> dict:
    """Update Ollama in place via `winget upgrade` (Windows). Same job slot +
    status endpoint as install."""
    return _start_winget("upgrade")


@router.get("/ollama/install-status")
def ollama_install_status() -> dict:
    return _jobs["install"] or {"active": False, "done": False}


@router.post("/ollama/unload")
def ollama_unload(session: Session = Depends(get_session)) -> dict:
    """Evict Ollama's loaded model(s) from VRAM/GPU right now (keep_alive=0), so it
    stops using the GPU while you're not actively asking. Ollama otherwise keeps a
    model resident for a few minutes after each request for fast follow-ups."""
    b = _ollama_base(session, "")
    try:
        req = urllib.request.Request(f"{b}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            loaded = [m.get("name") or m.get("model")
                      for m in (json.loads(resp.read().decode("utf-8")).get("models") or [])]
    except Exception:  # noqa: BLE001
        loaded = []
    if not loaded:                       # nothing reported → try the configured model
        cfg = _ai_config(session)
        loaded = [cfg["model"]] if cfg["model"] else []
    unloaded = []
    for m in [x for x in loaded if x]:
        try:
            body = json.dumps({"model": m, "keep_alive": 0}).encode("utf-8")
            req = urllib.request.Request(f"{b}/api/generate", data=body, method="POST",
                                         headers={"content-type": "application/json"})
            urllib.request.urlopen(req, timeout=15).close()
            unloaded.append(m)
        except Exception:  # noqa: BLE001
            continue
    return {"unloaded": unloaded}


@router.post("/ollama/warm")
def ollama_warm(session: Session = Depends(get_session)) -> dict:
    """Preload the configured model into VRAM (and keep it resident) so it's ready
    the instant the user asks. Used by "adaptive" mode: the app warms on focus and
    unloads on blur. No-op unless the provider is Ollama."""
    cfg = _ai_config(session)
    if cfg["provider"] != "ollama" or not cfg["model"]:
        return {"warmed": False}
    b = _ollama_base(session, "")
    try:
        # /api/generate with a model + no prompt just loads it; keep_alive=-1 (a
        # NUMBER — "-1" as a string fails with 'missing unit') keeps it resident
        # until we explicitly unload on blur.
        body = json.dumps({"model": cfg["model"], "keep_alive": -1}).encode("utf-8")
        req = urllib.request.Request(f"{b}/api/generate", data=body, method="POST",
                                     headers={"content-type": "application/json"})
        urllib.request.urlopen(req, timeout=60).close()
        return {"warmed": True, "model": cfg["model"]}
    except Exception:  # noqa: BLE001
        return {"warmed": False}


# ---------------------------------------------------------------------------
# Semantic search index (local embeddings)
# ---------------------------------------------------------------------------
@router.get("/embed/status")
def embed_status(session: Session = Depends(get_session)) -> dict:
    """Semantic-search index health: enabled?, model, how many messages embedded."""
    from app.sync import embeddings
    st = embeddings.status(session)
    st["reachable"] = embeddings.reachable(embeddings._embed_config(session)) if st["enabled"] else False
    st["indexing"] = _jobs.get("reindex", {}).get("active", False)
    return st


def _reindex_worker() -> None:
    job = _jobs["reindex"] = {"active": True, "done": False, "indexed": 0, "error": ""}
    try:
        from app.core.db import get_engine
        from app.sync import embeddings
        with Session(get_engine()) as session:
            cfg = embeddings._embed_config(session)
            if not cfg["enabled"] or not embeddings.reachable(cfg):
                job["error"] = "Embeddings endpoint isn't reachable."
                return
            # Loop batches until the whole mailbox is embedded (bounded by the
            # NOT-IN query shrinking each pass).
            while True:
                n = embeddings.index_pending(session, cfg, limit=64)
                if n == 0:
                    break
                job["indexed"] += n
    except Exception as exc:  # noqa: BLE001
        job["error"] = str(exc)
    finally:
        job["active"] = False
        job["done"] = True


@router.post("/embed/reindex")
def embed_reindex(session: Session = Depends(get_session)) -> dict:
    """Embed every not-yet-indexed message in the background (poll /ai/embed/status)."""
    from app.sync import embeddings
    cfg = embeddings._embed_config(session)
    if not cfg["enabled"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Turn on semantic search first (Settings → General → Semantic search).")
    if _jobs.get("reindex", {}).get("active"):
        return {"started": False, "already": True}
    threading.Thread(target=_reindex_worker, daemon=True, name="embed-reindex").start()
    return {"started": True}
