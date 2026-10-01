"""Rule matching and action execution.

Rules run against each newly-synced message. A rule has a single condition
(field + operator + value) and a single action. Block rules mark the sender/
domain blocked and quarantine the message (move to Junk, or delete).

"Put in group" rules are the exception to first-match-wins: they don't act on
the mail, they classify it, so they run as part of categorizing (see
`group_for`) and every other rule still gets its turn afterwards - seeing the
group as the message's category.

Matching is intentionally simple and predictable - the kind of thing a user can
reason about from the Rules UI's live preview.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import Message, Rule, RuleField, RuleOp, RuleAction


@dataclass
class MessageFields:
    from_addr: str
    to_addrs: list[str]
    subject: str
    body: str = ""
    category: str = ""
    from_name: str = ""

    @property
    def from_domain(self) -> str:
        return self.from_addr.rsplit("@", 1)[-1].lower() if "@" in self.from_addr else ""

    @property
    def sender(self) -> list[str]:
        # People think of "from" as the whole sender, so match the display name
        # AND the address: a rule "from contains ZERV Reporter" (a display name)
        # should hit even though the name isn't in the email address. Each part
        # is matched on its own as well as joined - "equals hrms@a123systems.cz"
        # against the joined "Robee - A123 Systems hrms@a123systems.cz" could
        # never be true, which silently broke every equals-sender rule (mute,
        # block, "put in group") for anyone with a display name.
        parts = [p for p in (self.from_addr, self.from_name) if p]
        joined = f"{self.from_name} {self.from_addr}".strip()
        return parts + ([joined] if len(parts) > 1 else [])

    @classmethod
    def from_message(cls, m: Message) -> "MessageFields":
        return cls(from_addr=m.from_addr or "", to_addrs=list(m.to_addrs or []),
                   subject=m.subject or "", body=m.snippet or "",
                   category=m.category or "", from_name=m.from_name or "")


def _field_value(rule: Rule, f: MessageFields) -> str | list[str]:
    return {
        RuleField.from_addr: f.sender,
        RuleField.from_domain: f.from_domain,
        RuleField.to_addr: f.to_addrs,
        RuleField.subject: f.subject,
        RuleField.body: f.body,
        RuleField.category: f.category,
    }[rule.match_field]


def _op_match(op: RuleOp, haystack: str, needle: str) -> bool:
    h, n = haystack.lower(), needle.lower()
    if op == RuleOp.contains:
        return n in h
    if op == RuleOp.equals:
        return h == n
    if op == RuleOp.ends_with:
        return h.endswith(n)
    if op == RuleOp.regex:
        try:
            return re.search(needle, haystack, re.I) is not None
        except re.error:
            return False
    return False


def rule_matches(rule: Rule, f: MessageFields) -> bool:
    if not rule.enabled or not rule.match_value:
        return False
    value = _field_value(rule, f)
    if isinstance(value, list):
        return any(_op_match(rule.match_op, v, rule.match_value) for v in value)
    return _op_match(rule.match_op, value, rule.match_value)


def first_matching_action(rules: list[Rule], f: MessageFields) -> Rule | None:
    """Return the first (lowest-order) enabled rule that matches, or None.
    Group rules are skipped: they already ran when the message was categorized."""
    for rule in sorted(rules, key=lambda r: r.order):
        if rule.action != RuleAction.set_group and rule_matches(rule, f):
            return rule
    return None


def group_for(rules: list[Rule], f: MessageFields) -> str | None:
    """The Smart Inbox group the first matching "put in group" rule files this
    message under, or None. `f.category` should be the heuristic/sender-override
    category, so a rule can regroup e.g. "category equals newsletters"."""
    for rule in sorted(rules, key=lambda r: r.order):
        if rule.action == RuleAction.set_group and rule.action_arg and rule_matches(rule, f):
            return rule.action_arg
    return None
