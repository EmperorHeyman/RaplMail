"""Bring-your-own-key AI helpers (thread summaries, "Catch me up").

Privacy-first: there is no RaplMail server. The user's own API key lives in the
local settings blob and calls go straight from this backend to the provider the
user chose. Nothing is sent anywhere unless the user explicitly asks for it and
has configured a key. Uses stdlib urllib — no SDK dependency.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Message, Setting

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(verify_token)])

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def _ai_config(session: Session) -> dict:
    row = session.get(Setting, 1)
    data = dict(row.data) if row and row.data else {}
    return {
        "key": str(data.get("aiApiKey") or "").strip(),
        "model": str(data.get("aiModel") or "").strip() or DEFAULT_MODEL,
    }


def _call_anthropic(key: str, model: str, system: str, prompt: str, max_tokens: int = 700) -> str:
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(_ANTHROPIC_URL, data=body, method="POST", headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI provider error ({e.code}): {detail}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't reach the AI provider: {e}")
    parts = payload.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


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
    for m in msgs:
        who = m.from_name or m.from_addr or "?"
        when = m.date.strftime("%Y-%m-%d %H:%M") if m.date else ""
        text = (m.body_text or m.snippet or "").strip()
        lines.append(f"--- From: {who}  ({when})\nSubject: {m.subject}\n{text[:4000]}")
    return subject, "\n\n".join(lines)


class SummarizeIn(BaseModel):
    message_id: int | None = None
    thread_id: str | None = None


@router.get("/status")
def ai_status(session: Session = Depends(get_session)) -> dict:
    cfg = _ai_config(session)
    return {"configured": bool(cfg["key"]), "model": cfg["model"]}


@router.post("/summarize")
def summarize(body: SummarizeIn, session: Session = Depends(get_session)) -> dict:
    cfg = _ai_config(session)
    if not cfg["key"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No AI API key set. Add one in Settings → General → AI assistant.")
    subject, transcript = _thread_text(session, body.thread_id or "", body.message_id)
    if not transcript.strip():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing to summarize.")
    system = (
        "You are an assistant inside an email client. Summarize the email thread "
        "for a busy professional. Be concise. Output: a one-line TL;DR, then 2-5 "
        "bullet points of key facts/decisions, then a short 'Action items' list "
        "(or 'No action needed'). Use plain text, no preamble."
    )
    summary = _call_anthropic(cfg["key"], cfg["model"], system,
                              f"Thread subject: {subject}\n\n{transcript[:24000]}")
    return {"summary": summary, "model": cfg["model"]}


def _require_key(session: Session) -> dict:
    cfg = _ai_config(session)
    if not cfg["key"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No AI API key set. Add one in Settings → General → AI assistant.")
    return cfg


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
        "tone. Do NOT include a subject line, quoted history, or a signature. Then, on a final "
        "line, output exactly: ###CHIPS### followed by up to 3 very short (2-5 word) quick-reply "
        "options separated by ' | '. Output plain text."
    )
    raw = _call_anthropic(cfg["key"], cfg["model"], system,
                          f"Thread subject: {subject}\n\n{transcript[:24000]}{steer}", max_tokens=900)
    draft, chips = raw, []
    if "###CHIPS###" in raw:
        draft, chip_str = raw.split("###CHIPS###", 1)
        chips = [c.strip() for c in chip_str.replace("\n", " ").split("|") if c.strip()][:3]
    return {"draft": draft.strip(), "chips": chips, "model": cfg["model"]}


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
    digest = _call_anthropic(cfg["key"], cfg["model"], system,
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
    raw = _call_anthropic(cfg["key"], cfg["model"], system, "\n".join(lines), max_tokens=1500)
    try:
        start, end = raw.find("["), raw.rfind("]")
        scores = json.loads(raw[start:end + 1]) if start >= 0 else []
    except Exception:
        scores = []
    return {"scores": scores, "model": cfg["model"]}
