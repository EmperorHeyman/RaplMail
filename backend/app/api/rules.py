"""Rule CRUD and a live-preview endpoint (match existing mail without acting)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Message, Rule, RuleAction, RuleField, RuleOp
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


class PreviewOut(BaseModel):
    match_count: int
    sample_subjects: list[str]


@router.post("/preview", response_model=PreviewOut)
def preview_rule(body: RuleIn, session: Session = Depends(get_session)) -> PreviewOut:
    """Count how many existing messages a (possibly unsaved) rule would match."""
    rule = Rule(**body.model_dump())
    stmt = select(Message)
    if rule.account_id is not None:
        stmt = stmt.where(Message.account_id == rule.account_id)
    matches = [m for m in session.exec(stmt.limit(2000))
               if rule_matches(rule, MessageFields.from_message(m))]
    return PreviewOut(match_count=len(matches),
                      sample_subjects=[m.subject for m in matches[:10]])
