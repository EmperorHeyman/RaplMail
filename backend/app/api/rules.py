"""Rule CRUD and a live-preview endpoint (match existing mail without acting)."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import (ActionQueue, Folder, FolderRole, Message, MessageState,
                        Rule, RuleAction, RuleField, RuleOp)
from app.sync.rules import MessageFields, rule_matches

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=[Depends(verify_token)])


class RuleIn(BaseModel):
    account_id: int | None = None
    name: str = ""
    enabled: bool = True
    order: int = 0
    match_field: RuleField = RuleField.from_domain
    match_op: RuleOp = RuleOp.contains
    match_value: str = ""
    action: RuleAction = RuleAction.move
    action_arg: str = ""


class RuleOut(RuleIn):
    id: int


def _to_out(r: Rule) -> RuleOut:
    return RuleOut(id=r.id, account_id=r.account_id, name=r.name, enabled=r.enabled,
                   order=r.order, match_field=r.match_field, match_op=r.match_op,
                   match_value=r.match_value, action=r.action, action_arg=r.action_arg)


@router.get("", response_model=list[RuleOut])
def list_rules(account_id: int | None = None, session: Session = Depends(get_session)) -> list[RuleOut]:
    stmt = select(Rule)
    if account_id is not None:
        stmt = stmt.where((Rule.account_id == account_id) | (Rule.account_id == None))  # noqa: E711
    return [_to_out(r) for r in session.exec(stmt.order_by(Rule.order))]


@router.post("", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, session: Session = Depends(get_session)) -> RuleOut:
    rule = Rule(**body.model_dump())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _to_out(rule)


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleIn, session: Session = Depends(get_session)) -> RuleOut:
    rule = session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    for k, v in body.model_dump().items():
        setattr(rule, k, v)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _to_out(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, session: Session = Depends(get_session)) -> None:
    rule = session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    session.delete(rule)
    session.commit()


# How many messages we're willing to scan when a rule needs Python-side matching
# (regex, to-address lists). Ordered newest-first so recent mail is always covered.
_SCAN_CAP = 20000


def _sql_condition(rule: Rule):
    """A SQL condition equivalent to the matcher for the common single-column,
    non-regex cases (subject / body / category / sender). Returns None when the
    match needs Python (regex, recipient lists) so the caller scans instead.

    This is the fix for 'rules match nothing': the old code scanned only the first
    2000 rows with NO ordering, so recent mail (a daily report) was never even
    looked at. Matching in SQL covers the WHOLE mailbox, accurately and fast."""
    v, op = rule.match_value, rule.match_op
    if op == RuleOp.regex or not v:
        return None

    def like(col):
        if op == RuleOp.contains:
            return col.ilike(f"%{v}%")
        if op == RuleOp.ends_with:
            return col.ilike(f"%{v}")
        if op == RuleOp.equals:
            return func.lower(col) == v.lower()
        return None

    fld = rule.match_field
    if fld == RuleField.subject:
        return like(Message.subject)
    if fld == RuleField.body:
        return like(Message.snippet)
    if fld == RuleField.category:
        return like(Message.category)
    if fld == RuleField.from_addr:   # "from" = display name OR address
        return or_(like(Message.from_addr), like(Message.from_name))
    return None   # from_domain / to_addr → Python fallback


def _matched_messages(session: Session, rule: Rule, cap: int = _SCAN_CAP) -> list[Message]:
    """Existing (still-visible) messages a rule matches, over the whole mailbox."""
    if not rule.match_value:
        return []
    stmt = select(Message).where(Message.pending_action == "")
    if rule.account_id is not None:
        stmt = stmt.where(Message.account_id == rule.account_id)
    cond = _sql_condition(rule)
    if cond is not None:
        return list(session.exec(stmt.where(cond).limit(cap)))
    # Python fallback (regex / recipient lists): scan newest-first so recent mail
    # is never skipped by the cap.
    return [m for m in session.exec(stmt.order_by(Message.date.desc()).limit(cap))
            if rule_matches(rule, MessageFields.from_message(m))]


class PreviewOut(BaseModel):
    match_count: int
    sample_subjects: list[str]


@router.post("/preview", response_model=PreviewOut)
def preview_rule(body: RuleIn, session: Session = Depends(get_session)) -> PreviewOut:
    """Count how many existing messages a (possibly unsaved) rule would match."""
    matches = _matched_messages(session, Rule(**body.model_dump()))
    return PreviewOut(match_count=len(matches),
                      sample_subjects=[m.subject for m in matches[:10]])


def _persist_done(session: Session, m: Message) -> None:
    """Durably mark a message done (survives re-sync), like the triage 'Done'."""
    if not m.message_id:
        return
    st = session.exec(select(MessageState).where(
        MessageState.account_id == m.account_id,
        MessageState.message_id == m.message_id)).first()
    if st is None:
        st = MessageState(account_id=m.account_id, message_id=m.message_id)
        session.add(st)
    st.is_done = True


class ApplyOut(BaseModel):
    applied: int
    note: str = ""


@router.post("/apply", response_model=ApplyOut)
def apply_rule(body: RuleIn, request: Request, session: Session = Depends(get_session)) -> ApplyOut:
    """Apply a rule to EXISTING messages right now. Rules otherwise only run on
    newly-arrived mail, so a freshly-created rule appears to 'do nothing' to mail
    already in the box — this is what makes it act on what's already there.
    Local-state actions (mark done/read) apply immediately; move/archive/delete/
    block queue an IMAP move that flushes in the background (offline-resilient).
    Notification-only / webhook / script actions have no meaning for old mail."""
    rule = Rule(**body.model_dump())
    msgs = _matched_messages(session, rule)
    if not msgs:
        return ApplyOut(applied=0)
    act, ids = rule.action, [m.id for m in msgs]

    if act == RuleAction.mark_done:
        for m in msgs:
            m.is_done = True
            session.add(m)
            _persist_done(session, m)
        session.commit()
        return ApplyOut(applied=len(msgs))
    if act == RuleAction.mark_read:
        for m in msgs:
            m.is_seen = True
            session.add(m)
        session.commit()
        return ApplyOut(applied=len(msgs))
    if act in (RuleAction.archive, RuleAction.delete):
        kind = "archive" if act == RuleAction.archive else "delete"
        for m in msgs:
            m.pending_action = kind
            session.add(m)
        session.add(ActionQueue(kind=kind, payload={"ids": ids}))
        session.commit()
        request.app.state.sync.request_sync()
        return ApplyOut(applied=len(ids))
    if act in (RuleAction.move, RuleAction.block):
        # Move to the rule's target folder (by path), or to Junk for a block.
        # An IMAP move is per-account, so resolve the destination per account.
        by_acct: dict[int, list[Message]] = defaultdict(list)
        for m in msgs:
            by_acct[m.account_id].append(m)
        applied = 0
        for aid, group in by_acct.items():
            if act == RuleAction.move:
                dest = session.exec(select(Folder).where(
                    Folder.account_id == aid, Folder.path == rule.action_arg)).first()
            else:
                dest = session.exec(select(Folder).where(
                    Folder.account_id == aid, Folder.role == FolderRole.junk)).first()
            if not dest:
                continue
            gids = [m.id for m in group]
            for m in group:
                m.pending_action = "move"
                session.add(m)
            session.add(ActionQueue(kind="move", payload={"ids": gids, "folder_id": dest.id}))
            applied += len(gids)
        session.commit()
        if applied:
            request.app.state.sync.request_sync()
        return ApplyOut(applied=applied)
    # mute_notifications / webhook / run_script only make sense as mail arrives.
    return ApplyOut(applied=0, note="This action only applies to newly arriving mail.")
