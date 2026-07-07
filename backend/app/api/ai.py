"""Bring-your-own-key AI helpers (thread summaries, "Catch me up").

Privacy-first: there is no RaplMail server. The user's own API key lives in the
local settings blob and calls go straight from this backend to the provider the
user chose. Nothing is sent anywhere unless the user explicitly asks for it and
has configured a key. Uses stdlib urllib — no SDK dependency.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import threading
import time
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
log = logging.getLogger("raplmail.ai")

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
    if provider == "ollama":
        # Route local Ollama chat through our hidden serve if one is up, so the
        # model-runner console windows never flash (see _effective_base).
        base = _effective_base(base)
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


class ScreenIn(BaseModel):
    message_id: int
    force: bool = False   # re-run even if a verdict was already cached on the message


_SCREEN_VERDICTS = ("safe", "suspicious", "dangerous")


def _parse_screen(raw: str) -> tuple[str, str]:
    """Pull a (verdict, reason) out of the model's reply. Robust to models that
    ignore the exact format: falls back to keyword sniffing, defaulting to 'safe'
    (conservative — we don't want a chatty model to flag normal mail)."""
    text = raw or ""
    vm = re.search(r"verdict\s*[:\-]?\s*(safe|suspicious|dangerous)", text, re.I)
    verdict = vm.group(1).lower() if vm else ""
    rm = re.search(r"reason\s*[:\-]\s*(.+)", text, re.I | re.S)
    reason = (rm.group(1).strip() if rm else "").splitlines()[0].strip() if rm else ""
    if not verdict:
        low = text.lower()
        if any(w in low for w in ("dangerous", "phishing", "scam", "malicious")):
            verdict = "dangerous"
        elif any(w in low for w in ("suspicious", "caution", "spoof", "spam")):
            verdict = "suspicious"
        else:
            verdict = "safe"
    if not reason:
        reason = re.sub(r"\s+", " ", re.sub(r"verdict\s*[:\-]?\s*\w+", "", text, flags=re.I)).strip()[:240]
    return verdict, reason[:240]


@router.post("/screen")
def screen_message(body: ScreenIn, session: Session = Depends(get_session)) -> dict:
    """Ask the configured model whether a message looks like phishing / a scam /
    spoofing. Returns {verdict: safe|suspicious|dangerous, reason, model, cached}.
    The verdict is cached on the message so "automatic" screening never re-spends
    tokens re-checking the same mail on each open (pass force=true to re-run)."""
    m = session.get(Message, body.message_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    if not body.force and m.ai_verdict:
        return {"verdict": m.ai_verdict, "reason": m.ai_reason, "model": cfg_model(session), "cached": True}
    cfg = _require_key(session)
    text = _message_text(session, m, fetch=True)
    header = (f"From name: {m.from_name or '(none)'}\n"
              f"From address: {m.from_addr or '(none)'}\n"
              f"Subject: {m.subject or '(none)'}\n"
              f"Sender authentication (SPF/DKIM/DMARC): {m.auth_status or 'unchecked'}\n")
    system = (
        "You are an email security analyst inside a mail client. Decide whether the "
        "message is a phishing, scam, or spoofing attempt. Weigh: a sender display "
        "name that doesn't match the address, lookalike or throwaway sender domains, "
        "failed authentication, false urgency or threats, requests for credentials / "
        "payments / gift cards, and links whose visible text differs from their "
        "target. Reply with EXACTLY two lines: 'VERDICT: <safe|suspicious|dangerous>' "
        "then 'REASON: <one short sentence>'. Be conservative — normal legitimate "
        "mail is 'safe'." + _LANG_RULE
    )
    raw = _call_provider(cfg, system, header + "\n" + (text or "")[:8000], max_tokens=200)
    verdict, reason = _parse_screen(raw)
    m.ai_verdict, m.ai_reason = verdict, reason
    session.add(m)
    session.commit()
    return {"verdict": verdict, "reason": reason, "model": cfg["model"], "cached": False}


def cfg_model(session: Session) -> str:
    try:
        return _ai_config(session)["model"]
    except Exception:
        return ""


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


# Small models (mistral 7b especially) ignore "output ONLY the text" and wrap the
# result in a ```code fence```, surrounding quotes, and/or a "Sure, here's the
# rewritten text:" preamble. Strip those wrappers so the composer gets clean text.
_PREAMBLE_RE = re.compile(
    r"^\s*(?:sure|certainly|of course|okay|here(?:'s| is| are)|here you go|"
    r"the (?:rewritten|revised|translated|corrected) [a-z ]+|translation|result|"
    r"zde je|zde m[aá]te|jist[eě]|samoz[rř]ejm[eě]|p[rř]eklad|v[yý]sledek)"
    r"[^\n:]{0,60}:\s*\n+", re.IGNORECASE)
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("“", "”"), ("„", "“"), ("«", "»"))


def _unwrap_output(text: str) -> str:
    """Strip the wrappers small models add around an 'output only X' reply: a
    fenced code block, a single leading preamble line, and matched surrounding
    quotes. Conservative — only removes obvious, whole-output wrappers."""
    if not text:
        return text
    s = text.strip()
    fence = re.match(r"^```[^\n]*\n(.*)\n```$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    s = _PREAMBLE_RE.sub("", s, count=1).strip()
    for a, b in _QUOTE_PAIRS:
        if len(s) >= 2 and s[0] == a and s[-1] == b and b not in s[1:-1]:
            s = s[1:-1].strip()
            break
    return s or text.strip()


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
    return {"result": _unwrap_output(result), "model": cfg["model"]}


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
# Agent: answer questions about RaplMail AND run mailbox actions on request
# ---------------------------------------------------------------------------
# A short guide the assistant can quote when the user asks how to use the app —
# so "how do I mark something done?" gets a real answer, not a shrug.
_APP_GUIDE = (
    "RaplMail is a fast, local-first desktop email client (this very app). It runs "
    "entirely on the user's machine; mail and the AI key never leave it.\n"
    "How to use it:\n"
    "- Triage (Spark-style): press E to mark a message DONE — it leaves the inbox view "
    "but stays on the server. The 'Show done' switch at the top of the list brings it back.\n"
    "- Keyboard: Up/Down move through the list and open the mail, Enter opens, R reply, "
    "F forward, A archive, U toggle read/unread, Delete deletes, / focuses search, "
    "Ctrl+K command palette, Ctrl+N compose.\n"
    "- Smart Inbox groups newsletters / social / updates / promotions into tidy cards; "
    "the 'See all' button shows one flat list. Snooze hides mail until later; Pin keeps "
    "it on top; VIP senders float up; the Screener holds first-time senders.\n"
    "- Rules (Settings -> Rules) auto-file, archive, delete, mark-done or block by "
    "sender / domain / subject. Signatures support a drag-in inline image.\n"
    "- This AI assistant: add emails as context, ask questions, draft replies, summarize, "
    "and run the mailbox actions below.\n"
)

# The mailbox actions the assistant may PROPOSE. Each maps to POST /messages/bulk;
# the frontend confirms with the user before anything actually runs.
_AGENT_OPS = {
    "mark_seen": "seen", "mark_read": "seen",
    "mark_unseen": "unseen", "mark_unread": "unseen",
    "mark_done": "done",
    "mark_undone": "undone",
    "flag": "flag", "star": "flag",
    "unflag": "unflag",
    "archive": "archive",
    "delete": "delete",
}

_AGENT_CAP = 2000   # never resolve more than this many messages for one action

_AGENT_SYSTEM = (
    "You are the assistant built into RaplMail, a local email client. You can do three "
    "things, and you pick EXACTLY ONE per reply:\n"
    "1) Answer a question - about the user's emails (given as context below) or about how "
    "to use RaplMail (use the guide below). This is the default.\n"
    "2) Do an action - when the user asks you to CHANGE or ORGANIZE their mail right now, "
    "propose ONE action using the ACTION format below.\n"
    "3) Set up a rule - when the user wants mail handled AUTOMATICALLY / from now on / every "
    "time, propose ONE rule using the RULE format below.\n\n"
    "When - and only when - the user asks you to DO something to their mailbox now, reply with "
    "a SINGLE line and nothing else, in exactly this form:\n"
    "ACTION: <op> <filters>\n"
    "Ops: mark_seen, mark_unseen, mark_done, mark_undone, flag, unflag, archive, delete.\n"
    "Filters (space-separated, all optional, they narrow the selection together): "
    "unread, read, flagged, from:TEXT, subject:TEXT. With no filter the action targets "
    "every message currently in the inbox.\n"
    "Examples:\n"
    "  'mark every unread email as read'        -> ACTION: mark_seen unread\n"
    "  'archive everything from noreply@x.com'  -> ACTION: archive from:noreply@x.com\n"
    "  'mark all as done'                       -> ACTION: mark_done\n\n"
    "When the user wants an AUTOMATIC rule, reply with a SINGLE line and nothing else, exactly:\n"
    'RULE: {"field": F, "op": O, "value": V, "action": A, "arg": ARG, "name": N}\n'
    "  field: from | from_domain | to | subject | body | category\n"
    "  op:    contains | equals | ends_with | regex\n"
    "  action: mark_done | mark_read | archive | delete | move | block | mute_notifications\n"
    "  value: the text (for regex, a Python re pattern, matched case-insensitively with re.search)\n"
    "  arg:   destination folder path (only for the move action; otherwise \"\")\n"
    "  name:  a short human name for the rule\n"
    "It must be valid JSON on that one line (escape backslashes in regex). When a subject "
    "just has a fixed part plus a changing part (dates, numbers), prefer op 'contains' on the "
    "fixed part - it is simpler and robust; use regex only when genuinely needed.\n"
    "Examples:\n"
    "  'automatically mark the ZERV daily report as done'\n"
    "    -> RULE: {\"field\":\"subject\",\"op\":\"contains\",\"value\":\"[ZERV] Daily Report\",\"action\":\"mark_done\",\"arg\":\"\",\"name\":\"ZERV daily report\"}\n"
    "  'always archive newsletters from mailchimp'\n"
    "    -> RULE: {\"field\":\"from\",\"op\":\"contains\",\"value\":\"mailchimp\",\"action\":\"archive\",\"arg\":\"\",\"name\":\"Mailchimp newsletters\"}\n\n"
    "Never invent an action or rule the user didn't ask for. Questions, summaries, drafts "
    "and small talk are ALWAYS a plain answer: reply with just the answer text, with NO "
    "'ANSWER:' prefix, and never write the words 'ACT:', 'ACTION:', 'RULE:' or 'MAKE A RULE:' "
    "unless it is a real single-line ACTION:/RULE: directive exactly as specified above. "
    "Pick ONE mode only: either a plain answer, OR one ACTION: line, OR one RULE: line - "
    "never more than one, and never mix a plain answer with an ACTION or RULE."
    + _LANG_RULE
    + "\n=== RAPLMAIL GUIDE ===\n" + _APP_GUIDE + "=== END GUIDE ==="
)

# Valid rule vocabulary (mirrors the RuleField/RuleOp/RuleAction enums).
_RULE_FIELDS = {"from", "from_domain", "to", "subject", "body", "category"}
_RULE_OPS = {"contains", "equals", "ends_with", "regex"}
_RULE_ACTIONS = {"mark_done", "mark_read", "archive", "delete", "move", "block",
                 "mute_notifications", "mark_unread"}


def _parse_rule(raw: str) -> dict | None:
    """If the model proposed a filtering RULE, parse + validate it into a RuleIn-
    shaped dict; else None. Only fires when the FIRST non-empty line starts RULE:."""
    if not raw:
        return None
    cleaned = raw.replace("```", "")
    first = next((ln for ln in cleaned.splitlines() if ln.strip()), "")
    if not re.match(r"\s*RULE\s*:", first, re.IGNORECASE):
        return None
    obj = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not obj:
        return None
    try:
        d = json.loads(obj.group(0))
    except Exception:  # noqa: BLE001
        return None
    field = str(d.get("field", "")).strip().lower()
    op = str(d.get("op", "")).strip().lower()
    action = str(d.get("action", "")).strip().lower()
    value = str(d.get("value", "") or "")
    if action == "mark_unread":
        action = "mark_read"   # not a rule action; fold to the closest valid one
    if field not in _RULE_FIELDS or op not in _RULE_OPS or action not in _RULE_ACTIONS or not value:
        return None
    if op == "regex":   # reject a pattern that won't compile
        try:
            re.compile(value)
        except re.error:
            return None
    return {"match_field": field, "match_op": op, "match_value": value,
            "action": action, "action_arg": str(d.get("arg", "") or ""),
            "name": str(d.get("name", "") or "").strip()}


def _parse_filters(arg: str) -> dict:
    """Parse the filter tail of an ACTION line into a dict of selectors."""
    f: dict = {}
    arg = arg or ""
    for m in re.finditer(r'(from|subject|to)\s*:\s*(?:"([^"]*)"|(\S+))', arg, re.IGNORECASE):
        val = (m.group(2) if m.group(2) is not None else (m.group(3) or "")).strip()
        if val:
            f[m.group(1).lower()] = val
    rest = re.sub(r'(from|subject|to)\s*:\s*(?:"[^"]*"|\S+)', " ", arg, flags=re.IGNORECASE)
    for tok in rest.lower().split():
        if tok in ("unread", "unseen"):
            f["unread"] = True
        elif tok in ("read", "seen"):
            f["seen"] = True
        elif tok in ("flagged", "starred", "star"):
            f["flagged"] = True
    return f


def _parse_action(raw: str) -> dict | None:
    """If the model's reply is an ACTION directive, parse it; else None. Only the
    FIRST non-empty line is considered, so the word 'ACTION:' buried in a normal
    answer can't silently trigger a mailbox change."""
    if not raw:
        return None
    cleaned = raw.replace("```", "")
    first = next((ln for ln in cleaned.splitlines() if ln.strip()), "")
    m = re.match(r"\s*ACTION\s*:\s*([a-z_]+)\s*(.*)$", first, re.IGNORECASE)
    if not m:
        return None
    op = m.group(1).lower()
    if op not in _AGENT_OPS:
        return None
    return {"op": op, "action": _AGENT_OPS[op], "filters": _parse_filters(m.group(2))}


# A weak local model sometimes parrots the ANSWER/ACT/RULE labels from the prompt
# into a plain answer, and even tacks on rules nobody asked for. Real ACTION/RULE
# directives are parsed from the FIRST line (above); any other reply is an answer,
# so scrub this leaked scaffolding before we show it verbatim.
_ANSWER_LABEL_RE = re.compile(r"^\s*(?:ANSWER|RESPONSE|ODPOV[EĚ]D[ě]?)\s*:\s*",
                              re.IGNORECASE)
_DIRECTIVE_LINE_RE = re.compile(
    r"[ \t]*(?:ACTION|ACT|AKCE|RULE|PRAVIDLO|MAKE\s+A\s+RULE|MAKE\s+RULE|"
    r"UD[EĚ]LEJ\s+PRAVIDLO|VYTVO[RŘ]\s+PRAVIDLO)\b[ \t]*:", re.IGNORECASE)


def _clean_answer(raw: str) -> str:
    """Return the model's prose answer with leaked protocol scaffolding removed. A
    normal request ('summarize my mail') must never surface 'ACT:', 'RULE: {...}'
    or 'MAKE A RULE:' lines, nor an 'ANSWER:' prefix, even when a small model echoes
    the prompt's labels. We only clean text that will be shown as-is."""
    if not raw:
        return raw
    kept = [ln for ln in raw.splitlines() if not _DIRECTIVE_LINE_RE.match(ln)]
    text = _ANSWER_LABEL_RE.sub("", "\n".join(kept).strip(), count=1)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or raw.strip()


def _resolve_action_targets(session: Session, plan: dict) -> tuple[list[int], list[dict]]:
    """Resolve which inbox messages an ACTION applies to. Scoped to inbox-role
    folders (never Sent/Trash) and to still-visible mail. Returns (ids, sample)."""
    f = plan["filters"]
    stmt = select(Message).where(Message.pending_action == "")
    inbox_ids = [fld.id for fld in session.exec(
        select(Folder).where(Folder.role == FolderRole.inbox))]
    if inbox_ids:
        stmt = stmt.where(Message.folder_id.in_(inbox_ids))
    if f.get("unread"):
        stmt = stmt.where(Message.is_seen == False)   # noqa: E712
    if f.get("seen"):
        stmt = stmt.where(Message.is_seen == True)     # noqa: E712
    if f.get("flagged"):
        stmt = stmt.where(Message.is_flagged == True)  # noqa: E712
    if f.get("from"):
        pat = f"%{f['from']}%"
        stmt = stmt.where(Message.from_addr.ilike(pat) | Message.from_name.ilike(pat))
    if f.get("subject"):
        stmt = stmt.where(Message.subject.ilike(f"%{f['subject']}%"))
    # Don't re-touch already-done mail unless the op is specifically un-doning it.
    if plan["op"] != "mark_undone":
        stmt = stmt.where(Message.is_done == False)    # noqa: E712
    msgs = list(session.exec(stmt.order_by(Message.date.desc())))
    ids = [m.id for m in msgs]
    sample = [{"from": (m.from_name or m.from_addr or "?"), "subject": (m.subject or "")}
              for m in msgs[:5]]
    return ids, sample


class AgentIn(BaseModel):
    instruction: str
    message_ids: list[int] = []
    history: list[dict] = []


@router.post("/agent")
def agent(body: AgentIn, session: Session = Depends(get_session)) -> dict:
    """The assistant with hands: answers questions about the mailbox and about
    RaplMail itself, and - when asked to change mail - returns a resolved ACTION
    (op + matching message ids + a small sample) for the UI to confirm before it
    runs. Nothing is mutated here; execution goes through /messages/bulk once the
    user confirms."""
    cfg = _require_key(session)
    instruction = (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ask me something.")
    transcript = _context_text(session, body.message_ids, "")
    system = _AGENT_SYSTEM
    if transcript:
        system += ("\n\n=== EMAILS IN CONTEXT ===\n" + transcript[:40000]
                   + "\n=== END EMAILS ===")
    turns = [{"role": t.get("role", "user"), "content": str(t.get("content", ""))}
             for t in (body.history or [])
             if t.get("role") in ("user", "assistant") and t.get("content")][-12:]
    turns.append({"role": "user", "content": instruction})
    raw = _call_chat(cfg, system, turns, max_tokens=1500)
    rule = _parse_rule(raw)
    if rule:
        return {"kind": "rule", "rule": rule, "model": cfg["model"]}
    plan = _parse_action(raw)
    if plan:
        ids, sample = _resolve_action_targets(session, plan)
        return {"kind": "action", "op": plan["op"], "action": plan["action"],
                "filters": plan["filters"], "count": len(ids),
                "ids": ids[:_AGENT_CAP], "capped": len(ids) > _AGENT_CAP,
                "sample": sample, "model": cfg["model"]}
    return {"kind": "answer", "answer": _clean_answer(raw), "model": cfg["model"]}


# ---------------------------------------------------------------------------
# Ollama: first-class local model server (detect / list / pull / install)
# ---------------------------------------------------------------------------
def _ollama_base(session: Session, override: str = "") -> str:
    """The Ollama URL to talk to: an explicit override (the settings field the
    user is editing), else the configured AI base when the provider is Ollama,
    else the loopback default."""
    if override.strip():
        return override.strip().rstrip("/")   # an explicit URL is checked as-is
    cfg = _ai_config(session)   # base_url already routed to our hidden serve if up
    if cfg["provider"] == "ollama" and cfg["base_url"]:
        return cfg["base_url"]
    return _effective_base("")


@router.get("/ollama/status")
def ollama_status(base: str = "", session: Session = Depends(get_session)) -> dict:
    """Detect a local Ollama: is the CLI installed, is the server up, which models
    are pulled. Drives the one-click setup card in Settings."""
    b = _ollama_base(session, base)
    installed = shutil.which("ollama") is not None
    # Union the models visible on the serve we'd actually use (b — maybe our hidden
    # managed serve) AND the user's raw configured/tray serve. Otherwise a model
    # pulled to the real Ollama shows as "not installed" whenever the managed serve
    # reads a different models directory — the "I pulled it but it says not pulled"
    # bug. Model presence must not depend on which of the two local serves answers.
    bases = [b]
    if not base.strip():
        raw = _raw_ollama_base(session) or _OLLAMA_URL
        if raw and raw not in bases:
            bases.append(raw)
    models_set: set[str] = set()
    running, version = False, ""
    for bb in bases:
        got = _ollama_models(bb)
        if got is None:
            continue
        running = True
        models_set |= got
        if not version:
            try:
                vreq = urllib.request.Request(f"{bb}/api/version", method="GET")
                with urllib.request.urlopen(vreq, timeout=4) as vr:
                    version = str(json.loads(vr.read().decode("utf-8")).get("version") or "")
            except Exception:  # noqa: BLE001
                pass
    return {"installed": installed or running, "running": running,
            "base_url": b, "models": sorted(m for m in models_set if m), "version": version}


def _ollama_is_up(base: str) -> bool:
    """True if the Ollama HTTP API answers at `base` right now."""
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        urllib.request.urlopen(req, timeout=3).close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _no_window_kwargs() -> dict:
    """Popen/run kwargs that suppress ALL console windows on Windows. CREATE_NO_WINDOW
    (not DETACHED_PROCESS): a detached process has no console, so each console-mode
    child Ollama spawns (the model runners) would pop its OWN black window. With
    CREATE_NO_WINDOW the process gets a hidden console its children inherit, so
    nothing flashes. No-op on other platforms."""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return {"creationflags": 0x08000000, "startupinfo": si}  # CREATE_NO_WINDOW


def _ollama_app_path() -> str | None:
    """Path to the Ollama desktop app ('ollama app.exe'), which runs the server as
    a proper windowless background service. `ollama serve` from the CLI, by
    contrast, spawns model-runner subprocesses that pop up black console windows
    on Windows — so we prefer the app when it's installed."""
    if os.name != "nt":
        return None
    exe = shutil.which("ollama")
    candidates = []
    if exe:
        candidates.append(os.path.join(os.path.dirname(exe), "ollama app.exe"))
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
                 os.environ.get("ProgramW6432", ""), os.environ.get("ProgramFiles(x86)", "")):
        if base:
            candidates.append(os.path.join(base, "Programs", "Ollama", "ollama app.exe"))
            candidates.append(os.path.join(base, "Ollama", "ollama app.exe"))
    # Last resort: the install path recorded in the uninstall registry key.
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Ollama") as k:
                    loc = winreg.QueryValueEx(k, "InstallLocation")[0]
                    if loc:
                        candidates.append(os.path.join(loc, "ollama app.exe"))
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _spawn_ollama_serve() -> bool:
    """Start the Ollama server with no visible console windows. Prefer the desktop
    app (windowless service); fall back to a hidden `ollama serve`."""
    app = _ollama_app_path()
    if app:
        try:
            subprocess.Popen([app], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **_no_window_kwargs())
            return True
        except Exception:  # noqa: BLE001
            pass
    exe = shutil.which("ollama")
    if not exe:
        return False
    try:
        subprocess.Popen([exe, "serve"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         **_no_window_kwargs())
        return True
    except Exception:  # noqa: BLE001
        return False


def start_ollama(base: str, wait: float = 8.0) -> bool:
    """Ensure the Ollama server is up. If it isn't, start it and poll until it
    answers (up to `wait` seconds). Returns True if the API is reachable."""
    if _ollama_is_up(base):
        return True
    if not _spawn_ollama_serve():
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        if _ollama_is_up(base):
            return True
        time.sleep(0.4)
    return _ollama_is_up(base)


def _stop_ollama() -> None:
    """Kill the running Ollama processes (used by restart). Includes the model
    runner (llama-server.exe): killing `ollama.exe` alone ORPHANS the runner it
    spawned — it keeps holding VRAM — so we kill it too."""
    if os.name == "nt":
        for name in ("ollama app.exe", "ollama.exe", "llama-server.exe"):
            try:
                subprocess.run(["taskkill", "/F", "/IM", name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10, **_no_window_kwargs())
            except Exception:  # noqa: BLE001
                pass
    else:
        try:
            subprocess.run(["pkill", "-f", "ollama"], timeout=10)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Managed hidden Ollama server — kills the model-runner console-window flashes
# ---------------------------------------------------------------------------
# On Windows, Ollama's model runner (llama-server.exe) briefly FLASHES a console
# window every time a model loads into / unloads from VRAM — but only when the
# `ollama serve` that spawned it was itself launched with a visible console, which
# the Ollama desktop tray app (auto-started at login) does. A serve WE launch with
# CREATE_NO_WINDOW spawns the runner into a hidden console, so nothing flashes.
# So for a LOCAL Ollama we run our own hidden serve on a private port and route all
# of RaplMail's traffic to it, leaving the user's tray Ollama untouched — it just
# goes idle, and idle = no runner = no flash. Toggle via the "ollamaManaged"
# setting (default on; no-op off-Windows / for a remote Ollama).
_MANAGED_PORT = 11500          # preferred private port; falls back to a free one
_managed: dict = {"pid": None, "base": None}   # our hidden serve, once adopted


def _is_local_base(base: str) -> bool:
    """A base URL that points at THIS machine (so a local hidden serve applies).
    A remote Ollama we never manage or reroute."""
    b = (base or "").strip().lower()
    return (not b) or "localhost" in b or "127.0.0.1" in b or "[::1]" in b or "//0.0.0.0" in b


def _effective_base(configured: str) -> str:
    """Where RaplMail should actually send local Ollama traffic: our hidden serve
    if it's been adopted and the configured base is local; else the configured base."""
    mb = _managed.get("base")
    if mb and _is_local_base(configured):
        return mb
    return (configured or _OLLAMA_URL).rstrip("/")


def _free_loopback_port() -> int:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def _kill_pid_tree(pid: int | None) -> None:
    """Kill a PID and its children — our serve plus the llama-server runner it
    spawned (which would otherwise orphan). Hidden, best-effort."""
    if not pid:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, **_no_window_kwargs())
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            os.kill(pid, 15)
        except Exception:  # noqa: BLE001
            pass


def _running_ollama_pids() -> list[int]:
    """PIDs of running ollama.exe processes (Windows), via tasklist."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ollama.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10, **_no_window_kwargs()).stdout
    except Exception:  # noqa: BLE001
        return []
    pids = []
    for line in out.splitlines():
        cells = [c.strip().strip('"') for c in line.split('","')]
        if len(cells) >= 2 and cells[1].strip('"').isdigit():
            pids.append(int(cells[1].strip('"')))
    return pids


def _process_env(pid: int) -> dict:
    """Read another process's environment block via the PEB (Windows x64).
    Best-effort: returns {} on any failure (permissions, wrong arch, layout)."""
    if os.name != "nt":
        return {}
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        h = k32.OpenProcess(0x0400 | 0x0010, False, pid)  # QUERY_INFORMATION | VM_READ
        if not h:
            return {}
        try:
            class PBI(ctypes.Structure):
                _fields_ = [("Reserved1", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p),
                            ("Reserved2", ctypes.c_void_p * 2), ("UniqueProcessId", ctypes.c_void_p),
                            ("Reserved3", ctypes.c_void_p)]
            pbi = PBI(); rl = ctypes.c_ulong(0)
            if ntdll.NtQueryInformationProcess(h, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), ctypes.byref(rl)) != 0:
                return {}
            def rd(addr, size):
                buf = ctypes.create_string_buffer(size); n = ctypes.c_size_t(0)
                if k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)) and n.value:
                    return buf.raw[:n.value]
                return None
            peb = pbi.PebBaseAddress
            pp_raw = rd(peb + 0x20, 8) if peb else None            # PEB->ProcessParameters
            if not pp_raw:
                return {}
            env_raw = rd(int.from_bytes(pp_raw, "little") + 0x80, 8)  # ->Environment
            if not env_raw:
                return {}
            env_addr = int.from_bytes(env_raw, "little")
            block = None
            for size in (65536, 32768, 16384, 8192, 4096):
                block = rd(env_addr, size)
                if block:
                    break
            if not block:
                return {}
            out = {}
            for entry in block.decode("utf-16-le", "ignore").split("\x00"):
                if entry == "":
                    break                       # double-null terminates the block
                if entry[0] == "=":
                    continue                    # skip "=C:=..." drive pseudo-vars
                k, sep, v = entry.partition("=")
                if sep and k:
                    out[k] = v
            return out
        finally:
            k32.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return {}


def _running_ollama_env() -> dict:
    """The explicitly-set OLLAMA_* env of the already-running Ollama serve, so our
    hidden serve behaves identically — same models directory (OLLAMA_MODELS), GPU
    backend (OLLAMA_VULKAN), context length, etc. Excludes OLLAMA_HOST (we set the
    port). {} if it can't be read (then we just inherit our own environment)."""
    for pid in _running_ollama_pids():
        env = _process_env(pid)
        keys = [k for k in env if k.startswith("OLLAMA_") and k != "OLLAMA_HOST"]
        if keys:
            return {k: env[k] for k in keys}
    return {}


def _spawn_hidden_serve(port: int, extra_env: dict | None = None) -> int | None:
    """Launch `ollama serve` on a private loopback port with a HIDDEN console.
    `extra_env` replicates the running serve's OLLAMA_* config (see
    _running_ollama_env). Returns the child PID, or None if it couldn't start."""
    exe = shutil.which("ollama")
    if not exe:
        return None
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
    try:
        p = subprocess.Popen([exe, "serve"], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             **_no_window_kwargs())
        return p.pid
    except Exception:  # noqa: BLE001
        return None


def _ollama_models(base: str) -> set[str] | None:
    """Model names the serve at `base` can see, or None if it isn't reachable."""
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {m.get("name") for m in (data.get("models") or []) if m.get("name")}
    except Exception:  # noqa: BLE001
        return None


def start_managed_ollama(configured_base: str = "") -> bool:
    """Ensure RaplMail's own hidden Ollama serve is up and SAFE to use, and point
    `_managed["base"]` at it so traffic reroutes there. Idempotent. Windows-only.

    Safety net: only adopt the hidden serve if it can see the same models the
    user's configured serve has — otherwise a custom OLLAMA_MODELS the tray app
    knows about (but we didn't inherit) would make models silently disappear. In
    that case we leave the configured serve in charge (flashes, but correct)."""
    if os.name != "nt" or not shutil.which("ollama"):
        return False
    if _managed.get("base") and _ollama_is_up(_managed["base"]):
        return True
    base, pid = None, None
    reuse = f"http://127.0.0.1:{_MANAGED_PORT}"
    if _ollama_is_up(reuse):
        base = reuse   # a hidden serve left from a previous RaplMail run — reuse it
    else:
        # Replicate the running serve's OLLAMA_* config (models dir, GPU backend…)
        # so our hidden serve sees the SAME models — even a custom OLLAMA_MODELS the
        # tray app injected from its own settings (not our environment).
        serve_env = _running_ollama_env()
        for port in (_MANAGED_PORT, _free_loopback_port()):
            pid = _spawn_hidden_serve(port, serve_env)
            if not pid:
                continue
            cand = f"http://127.0.0.1:{port}"
            deadline = time.time() + 12
            while time.time() < deadline:
                if _ollama_is_up(cand):
                    base = cand
                    break
                time.sleep(0.3)
            if base:
                break
            _kill_pid_tree(pid); pid = None
    if not base:
        return False
    cfg_base = (configured_base or "").rstrip("/")
    # The serve the user actually pulls to: their configured local base, or the
    # default tray port when they haven't set one.
    real_base = cfg_base if (_is_local_base(configured_base) and cfg_base) else _OLLAMA_URL
    if real_base and real_base != base:
        theirs, ours = _ollama_models(real_base), _ollama_models(base)
        verified = theirs is not None and ours is not None and theirs.issubset(ours)
        if not verified:
            # Either our hidden serve is missing models the real serve has, or the
            # real serve was unreachable so we couldn't confirm the model
            # directories match. Rerouting anyway is what made models "vanish"
            # depending on boot order, so we DON'T — the real serve stays in charge
            # (it may flash a console, but a model that disappears is far worse).
            missing = sorted(theirs - ours) if (theirs and ours) else "unverified"
            log.info("not adopting hidden Ollama serve %s (missing/%s vs real %s) — "
                     "using %s instead.", base, missing, real_base, real_base)
            _kill_pid_tree(pid)   # don't leave the just-spawned serve orphaned
            return False          # fall back to the real serve (correctness first)
    _managed.update({"pid": pid, "base": base})
    log.info("managed hidden Ollama serve active at %s (pid %s)", base, pid)
    return True


def shutdown_managed_ollama() -> None:
    """Stop the hidden serve we started (and its runner child). Called on backend
    shutdown and when the user turns managed mode off."""
    _kill_pid_tree(_managed.get("pid"))
    _managed.update({"pid": None, "base": None})


@router.post("/ollama/start")
def ollama_start(base: str = "", session: Session = Depends(get_session)) -> dict:
    """Start the local Ollama server if it isn't already running."""
    b = _ollama_base(session, base)
    return {"running": start_ollama(b), "base_url": b}


def _raw_ollama_base(session: Session) -> str:
    """The Ollama base as CONFIGURED (before any managed rerouting)."""
    row = session.get(Setting, 1)
    data = dict(row.data) if row and row.data else {}
    return str(data.get("aiBaseUrl") or "").strip().rstrip("/")


@router.post("/ollama/restart")
def ollama_restart(base: str = "", session: Session = Depends(get_session)) -> dict:
    """Stop then start the Ollama server (recover a stuck server). When RaplMail
    manages a hidden serve, this restarts THAT (not the user's tray Ollama)."""
    raw = base.strip().rstrip("/") or _raw_ollama_base(session)
    if _managed.get("base") or (os.name == "nt" and _is_local_base(raw) and shutil.which("ollama")):
        shutdown_managed_ollama()
        time.sleep(1.0)
        ok = start_managed_ollama(raw)
        return {"running": ok or _ollama_is_up(_effective_base(raw)), "base_url": _effective_base(raw)}
    b = _ollama_base(session, base)
    _stop_ollama()
    time.sleep(1.2)   # let the port free up before we bind again
    return {"running": start_ollama(b), "base_url": b}


@router.post("/ollama/managed")
def ollama_managed(enabled: bool = True, session: Session = Depends(get_session)) -> dict:
    """Turn RaplMail's hidden managed serve on/off at runtime (mirrors the
    ollamaManaged setting). On → start it; off → stop it and fall back to the
    configured/tray serve (which flashes, but is what the user asked for)."""
    if enabled:
        ok = start_managed_ollama(_raw_ollama_base(session))
        return {"managed": bool(_managed.get("base")), "base": _managed.get("base"), "ok": ok}
    shutdown_managed_ollama()
    return {"managed": False, "base": None, "ok": True}


def autostart_ollama_if_configured() -> None:
    """On app launch (background thread, never delays startup): for a LOCAL Ollama
    with managed mode on (default), bring up RaplMail's own hidden serve so the
    model-runner console windows never flash. Otherwise honor the legacy "Start
    Ollama with RaplMail" opt-in. Safe no-op if the provider isn't Ollama."""
    try:
        from app.core.db import get_engine
        with Session(get_engine()) as session:
            row = session.get(Setting, 1)
            data = dict(row.data) if row and row.data else {}
        if str(data.get("aiProvider") or "").strip().lower() != "ollama":
            return
        base = str(data.get("aiBaseUrl") or "").strip().rstrip("/")
        if data.get("ollamaManaged", True) and os.name == "nt" and _is_local_base(base):
            if start_managed_ollama(base):
                return   # hidden serve adopted — done
            # couldn't take over (spawn failed / models mismatch): fall through so
            # AI still works via the configured/tray serve.
        if data.get("ollamaAutostart"):
            start_ollama(base or _OLLAMA_URL)
    except Exception:  # noqa: BLE001
        pass


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
    # Download into the user's REAL serve when it's reachable, so the model lands
    # in the directory their Ollama actually reads (and survives restarts) rather
    # than our hidden serve's possibly-different directory — which is what made
    # freshly pulled models "disappear".
    if not body.base.strip():
        raw = _raw_ollama_base(session) or _OLLAMA_URL
        if raw and raw != base and _ollama_is_up(raw):
            base = raw
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
            capture_output=True, text=True, timeout=900, **_no_window_kwargs())
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
    # ONLY unload what /api/ps says is actually loaded. The old fallback pinged the
    # configured model when nothing was loaded — but a generate request LOADS the
    # model (spawning a runner process, i.e. a console window flash) just to unload
    # it again. If nothing's loaded there's nothing to free.
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
    # If we manage a hidden serve but it isn't up yet (startup race), DON'T warm via
    # the configured/tray serve — that would flash a runner window AND pin the model
    # in the tray's VRAM (keep_alive=-1). Skip; our serve comes up momentarily.
    row = session.get(Setting, 1)
    data = dict(row.data) if row and row.data else {}
    raw = str(data.get("aiBaseUrl") or "").strip().rstrip("/")
    if (data.get("ollamaManaged", True) and os.name == "nt"
            and _is_local_base(raw) and not _managed.get("base")):
        return {"warmed": False, "pending": True}
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
