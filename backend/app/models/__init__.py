"""SQLModel table definitions for RaplMail.

Local mail metadata + client-side state. Raw MIME bodies are cached on disk
(see sync engine); these tables hold the indexable/searchable metadata plus the
local-only state that makes the Spark-style workflow work (done, snooze, block).
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Provider(str, enum.Enum):
    imap = "imap"          # generic IMAP/SMTP (password or app password)
    gmail = "gmail"        # Google OAuth2 over IMAP/SMTP (XOAUTH2)
    m365 = "m365"          # Microsoft 365 OAuth2 (XOAUTH2, Graph fallback)


class FolderRole(str, enum.Enum):
    inbox = "inbox"
    archive = "archive"
    sent = "sent"
    drafts = "drafts"
    trash = "trash"
    junk = "junk"
    other = "other"


class RuleField(str, enum.Enum):
    from_addr = "from"
    from_domain = "from_domain"
    to_addr = "to"
    subject = "subject"
    body = "body"


class RuleOp(str, enum.Enum):
    contains = "contains"
    equals = "equals"
    ends_with = "ends_with"     # handy for domains
    regex = "regex"


class RuleAction(str, enum.Enum):
    move = "move"               # action_arg = folder path
    archive = "archive"
    delete = "delete"
    mark_read = "mark_read"
    mark_done = "mark_done"
    block = "block"             # block sender/domain: quarantine on arrival


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    display_name: str = ""
    provider: Provider = Provider.imap

    # IMAP/SMTP connection details (Gmail/M365 use well-known hosts but stored too).
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 465

    use_oauth: bool = False
    # Key under which this account's secret (password or token bundle) is stored
    # in the encrypted secret store.
    secret_key: str = ""

    color: str = "#4f8cff"      # UI accent for unified inbox
    enabled: bool = True
    sort_order: int = Field(default=0, index=True)   # manual order in the sidebar/UI
    # Extra send-as identities for this account, e.g. ["Sales <sales@co.com>",
    # "me+side@co.com"]. The primary `email` is always implicitly available.
    aliases: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Folder(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("account_id", "path", name="uq_folder_account_path"),)
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    name: str
    path: str                   # IMAP mailbox path
    role: FolderRole = FolderRole.other
    uidvalidity: int | None = None
    unread_count: int = 0
    total_count: int = 0


class Message(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("folder_id", "uid", name="uq_message_folder_uid"),)
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    folder_id: int = Field(foreign_key="folder.id", index=True)
    uid: int = Field(index=True)

    message_id: str = Field(default="", index=True)   # RFC 5322 Message-ID header
    thread_id: str = Field(default="", index=True)

    from_addr: str = Field(default="", index=True)
    from_name: str = ""
    to_addrs: list = Field(default_factory=list, sa_column=Column(JSON))
    cc_addrs: list = Field(default_factory=list, sa_column=Column(JSON))
    subject: str = ""
    snippet: str = ""
    date: datetime | None = Field(default=None, index=True)

    is_seen: bool = Field(default=False, index=True)
    is_flagged: bool = False
    is_answered: bool = False
    is_done: bool = Field(default=False, index=True)   # Spark "done" (local)
    category: str = Field(default="primary", index=True)  # primary|newsletters|social|updates|promotions
    snooze_until: datetime | None = None

    has_attachments: bool = False
    size: int = 0
    body_path: str = ""          # relative path to cached raw MIME on disk
    # Parsed body cache (filled on first open so re-opening is instant).
    body_html: str = ""
    body_text: str = ""
    body_fetched: bool = False
    unsubscribe: str = ""        # raw List-Unsubscribe header value (filled on body fetch)
    brand_domain: str = ""       # a prominent link domain from the body (Spark-style avatar fallback)
    auth_status: str = ""        # sender-auth verdict: ""=unchecked, pass|fail|none (anti-spoof shield)
    attachments: list = Field(default_factory=list, sa_column=Column(JSON))  # metadata, filled on body fetch
    snooze_presence: bool = False  # snoozed "until I'm back" — resurfaced by the idle monitor
    pinned: bool = False         # pinned to the top of the list (durable via MessageState)
    pending_action: str = Field(default="", index=True)  # queued archive/delete — hidden until flushed


class MessageState(SQLModel, table=True):
    """Durable local state keyed by RFC Message-ID so it survives re-sync,
    folder moves, and UID changes."""
    __table_args__ = (UniqueConstraint("account_id", "message_id", name="uq_state_account_msgid"),)
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    message_id: str = Field(index=True)
    is_done: bool = False
    is_blocked: bool = False
    snooze_until: datetime | None = None
    snooze_presence: bool = False
    is_pinned: bool = False
    updated_at: datetime = Field(default_factory=utcnow)


class MutedThread(SQLModel, table=True):
    """A conversation the user muted — new mail in it is auto-archived on arrival."""
    id: int | None = Field(default=None, primary_key=True)
    thread_key: str = Field(index=True, unique=True)
    # Lowercased sender addresses seen in the muted conversation, comma-joined.
    # New arrivals are auto-archived only if their sender is one of these, so a
    # shared/common subject ("Invoice", "Re: lunch?") doesn't mute strangers.
    # Empty = legacy mute (subject-only) for back-compat.
    participants: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Rule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int | None = Field(default=None, foreign_key="account.id", index=True)  # None = global
    name: str = ""
    enabled: bool = True
    order: int = 0
    match_field: RuleField = RuleField.from_domain
    match_op: RuleOp = RuleOp.contains
    match_value: str = ""
    action: RuleAction = RuleAction.move
    action_arg: str = ""         # e.g. target folder path for "move"
    created_at: datetime = Field(default_factory=utcnow)


class Signature(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int | None = Field(default=None, foreign_key="account.id", index=True)
    name: str = "Default"
    html: str = ""
    # Inline images referenced by the html via cid: — stored as a list of
    # {"cid": str, "filename": str, "content_type": str, "data_b64": str}.
    inline_images: list = Field(default_factory=list, sa_column=Column(JSON))
    is_default: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class ActionQueue(SQLModel, table=True):
    """Offline-resilient mutation queue. The UI applies changes instantly; a
    background worker flushes these to IMAP/SMTP and retries until it succeeds."""
    id: int | None = Field(default=None, primary_key=True)
    kind: str                    # "archive" | "delete" | "send"
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="pending", index=True)  # pending | failed
    attempts: int = 0
    last_error: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ScheduledSend(SQLModel, table=True):
    """A queued outgoing message to deliver at a future time (Send Later)."""
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))  # the SendIn body
    to_summary: str = ""          # for display in the Scheduled list
    subject: str = ""
    send_at: datetime = Field(index=True)
    status: str = Field(default="pending", index=True)  # pending|sent|failed
    created_at: datetime = Field(default_factory=utcnow)


class SenderCategory(SQLModel, table=True):
    """User override: always file mail from this sender under a given category."""
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    category: str
    created_at: datetime = Field(default_factory=utcnow)


class Setting(SQLModel, table=True):
    """Single-row store for the app's UI/behavior settings (persisted to the DB
    file so they survive restarts and can be exported)."""
    id: int | None = Field(default=1, primary_key=True)
    data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow)


class CalendarEvent(SQLModel, table=True):
    """A calendar event extracted from a meeting invite (text/calendar / .ics)."""
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    message_id: int | None = Field(default=None, foreign_key="message.id", index=True)
    uid: str = Field(default="", index=True)        # ICS UID (dedup key with account)
    summary: str = ""
    location: str = ""
    description: str = ""
    organizer: str = ""
    start: datetime | None = Field(default=None, index=True)
    end: datetime | None = None
    all_day: bool = False
    method: str = ""                                # REQUEST | CANCEL | REPLY | PUBLISH
    status: str = "needsAction"                     # needsAction|accepted|declined|tentative
    cancelled: bool = False
    source: str = Field(default="mail", index=True)  # "mail" | "ics" | "caldav"
    color: str = ""                                  # per-feed display color (hex), if any
    created_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (UniqueConstraint("account_id", "uid", name="uq_event_account_uid"),)


class Contact(SQLModel, table=True):
    """Smart address book entry. Auto-populated by scanning outgoing mail, with
    obvious junk addresses filtered out (see sync/contacts.py)."""
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str = ""
    times_sent: int = 0          # how often we emailed them
    times_received: int = 0      # how often they emailed us (two-way signal)
    last_contacted: datetime | None = Field(default=None, index=True)
    is_known_domain: bool = False
    favorite: bool = False
    source: str = "scanned"      # "scanned" | "manual"
    created_at: datetime = Field(default_factory=utcnow)


class OpenTrack(SQLModel, table=True):
    """A read-receipt tracking pixel embedded in an outgoing message. The pixel
    URL is fetched when the recipient opens the mail, recording the open here."""
    id: int | None = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)
    subject: str = ""
    recipient: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    open_count: int = 0
    first_open: datetime | None = None
    last_open: datetime | None = None
