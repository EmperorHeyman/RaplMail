"""Provider abstraction.

A MailProvider hides the difference between generic IMAP/SMTP, Gmail (XOAUTH2),
and Microsoft 365 (XOAUTH2, or Graph fallback). The sync engine talks only to
this interface. All methods are synchronous and are expected to be called from a
worker thread (the engine wraps them with ``run_in_executor``) because the
underlying IMAP/SMTP libraries are blocking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class FolderInfo:
    name: str
    path: str
    role: str = "other"
    uidvalidity: int | None = None


@dataclass
class HeaderInfo:
    uid: int
    message_id: str
    subject: str
    from_addr: str
    from_name: str
    to_addrs: list[str] = field(default_factory=list)
    cc_addrs: list[str] = field(default_factory=list)
    date: datetime | None = None
    flags: list[str] = field(default_factory=list)
    size: int = 0
    has_attachments: bool = False
    snippet: str = ""


@dataclass
class OutgoingMessage:
    from_addr: str
    to: list[str]
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    subject: str = ""
    html: str = ""
    text: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    # Inline images: {"cid", "filename", "content_type", "data": bytes}
    inline_images: list[dict] = field(default_factory=list)
    # Regular attachments: {"filename", "content_type", "data": bytes}
    attachments: list[dict] = field(default_factory=list)


class MailProvider(Protocol):
    """Read/write access to a single account's mailbox."""

    def list_folders(self) -> list[FolderInfo]: ...

    def fetch_headers(self, folder_path: str, min_uid: int = 1, limit: int | None = None) -> list[HeaderInfo]:
        """Return header info for messages with UID >= ``min_uid``."""
        ...

    def fetch_uids(self, folder_path: str) -> list[int]:
        """All UIDs currently in the folder (for detecting deletions)."""
        ...

    def fetch_raw(self, folder_path: str, uid: int) -> bytes:
        """Full raw RFC822 message bytes."""
        ...

    def set_flags(self, folder_path: str, uid: int, flags: list[str], add: bool = True) -> None: ...

    def move(self, folder_path: str, uid: int, dest_path: str) -> None: ...

    def delete(self, folder_path: str, uid: int) -> None: ...

    def send(self, message: OutgoingMessage) -> None: ...

    def close(self) -> None: ...
